"""Process, terminal and file-lock primitives for each operating system."""

from contextlib import contextmanager
from functools import cache
import os
import ntpath
import posixpath
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time


def windows_powershell():
    root = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    return Path(root) / "System32/WindowsPowerShell/v1.0/powershell.exe"


def powershell(script):
    prefix = "$ErrorActionPreference = 'Stop'; [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
    # A GUI launched without a console can have an invalid standard input handle.
    return subprocess.run([str(windows_powershell()), "-NoProfile", "-NonInteractive", "-Command", prefix + script],
                          check=True, stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8-sig", errors="replace",
                          timeout=12, creationflags=subprocess.CREATE_NO_WINDOW).stdout


class ProfileDirectoryAccessError(PermissionError):
    pass


@cache
def windows_user_sid():
    sid = powershell("[Security.Principal.WindowsIdentity]::GetCurrent().User.Value").strip()
    if not re.fullmatch(r"S-1-(?:\d+-)*\d+", sid):
        raise OSError("Could not determine the Windows user for profile data.")
    return sid


def create_windows_private_directory(path):
    import ctypes
    from ctypes import wintypes

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p), ("inherit_handle", wintypes.BOOL)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create_directory = kernel.CreateDirectoryW
    create_directory.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(SecurityAttributes))
    create_directory.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel.LocalFree.restype = ctypes.c_void_p
    convert = ctypes.WinDLL("advapi32", use_last_error=True).ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)
    convert.restype = wintypes.BOOL

    # An elevated token can create a directory owned by Administrators. Grant access to
    # the user SID directly so that the same account can reopen it without elevation.
    acl = f"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;{windows_user_sid()})"
    descriptor = ctypes.c_void_p()
    if not convert(acl, 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        if not create_directory(str(path.absolute()), ctypes.byref(attributes)):
            error = ctypes.get_last_error()
            if error != 183 or not path.is_dir():  # ERROR_ALREADY_EXISTS
                raise ctypes.WinError(error)
    finally:
        kernel.LocalFree(descriptor)


def private_directory(path):
    try:
        if os.name == "nt":
            if not path.is_dir():
                path.parent.mkdir(parents=True, exist_ok=True)
                create_windows_private_directory(path)
        else:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            # mkdir leaves an existing folder's mode alone, so tighten one created loosely.
            info = path.stat()
            if info.st_mode & 0o077:
                if info.st_uid != os.getuid():
                    raise PermissionError(f"Profile data folder belongs to another user: {path}")
                path.chmod(0o700)
    except PermissionError as error:
        if os.name == "nt":
            raise ProfileDirectoryAccessError(f"Windows denied access to the profile data folder: {path}") from error
        raise
    return str(path)


def process_arguments():
    if sys.platform == "win32":
        return powershell("$session = (Get-Process -Id $PID).SessionId; "
                          'Get-CimInstance Win32_Process -Filter "SessionId = $session" | '
                          "ForEach-Object { $_.CommandLine }")
    return subprocess.run(["ps", "-axww", "-o", "command="], check=True, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=8).stdout


def desktop_processes():
    """Main (non-helper) processes of this login session as (pid, name, command line)."""
    if sys.platform == "win32":
        output = powershell("$session = (Get-Process -Id $PID).SessionId; "
                            'Get-CimInstance Win32_Process -Filter "SessionId = $session" | '
                            "Where-Object { $_.CommandLine -cnotmatch '(?:^|\\s)--type=' } | "
                            "ForEach-Object { '{0}{2}{1}{2}{3}' -f $_.ProcessId, $_.Name, [char]9, $_.ExecutablePath }")
        rows = [(line.split("\t", 2) + [""])[:3] for line in output.splitlines() if "\t" in line]
        # The third field is the executable path (empty when Windows does not report it).
        return [(int(pid), name.strip(), path.strip()) for pid, name, path in rows if pid.strip().isdecimal()]
    output = subprocess.run(["ps", "-axww", "-o", "pid=", "-o", "command="], check=True, capture_output=True,
                            encoding="utf-8", errors="replace", timeout=8).stdout
    rows = [line.strip().partition(" ") for line in output.splitlines()]
    return [(int(pid), "", command.strip()) for pid, _, command in rows if pid.isdecimal()]


def terminate_processes(pids, wait=6):
    """Force close processes and their children, then report which ones are still alive."""
    pids = [pid for pid in pids if pid != os.getpid()]
    for pid in pids:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + wait
    alive = list(pids)
    while alive and time.monotonic() < deadline:
        running = {row[0] for row in desktop_processes()}
        alive = [pid for pid in alive if pid in running]
        if alive and sys.platform != "win32" and time.monotonic() > deadline - wait / 2:
            for pid in alive:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if alive:
            time.sleep(0.4)
    return alive


def profile_process_tree(folder):
    """Every process of this login session that belongs to the client started with this profile folder.

    Roots are the processes whose command line carries a matching --user-data-dir; their descendants
    (helpers, bundled servers) are included. Other profiles and the original client are never listed.
    """
    if sys.platform == "win32":
        output = powershell("$session = (Get-Process -Id $PID).SessionId; "
                            'Get-CimInstance Win32_Process -Filter "SessionId = $session" | '
                            "ForEach-Object { '{0}{2}{1}{2}{3}' -f $_.ProcessId, $_.ParentProcessId, [char]9, $_.CommandLine }")
    else:
        output = subprocess.run(["ps", "-axww", "-o", "pid=", "-o", "ppid=", "-o", "command="], check=True,
                                capture_output=True, encoding="utf-8", errors="replace", timeout=8).stdout
    rows = {}
    for line in output.splitlines():
        parts = line.split("\t", 2) if sys.platform == "win32" else line.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].strip().isdecimal() and parts[1].strip().isdecimal():
            rows[int(parts[0])] = (int(parts[1]), parts[2] if len(parts) > 2 else "")
    found = {pid for pid, (_, command) in rows.items() if uses_profile_directory(command, folder)}
    grew = True
    while grew:
        grew = False
        for pid, (parent, _) in rows.items():
            if parent in found and pid not in found and pid != parent:
                found.add(pid)
                grew = True
    return sorted(found - {os.getpid()})


WM_CLOSE, WM_QUERYENDSESSION, WM_ENDSESSION = 0x0010, 0x0011, 0x0016


def _windows_of(pids):
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL("user32")
    handles = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def collect(handle, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value in pids:
            handles.append(handle)
        return True

    user.EnumWindows(callback_type(collect), 0)
    return user, handles


def _signal_windows(pids, message, wparam=0):
    user, handles = _windows_of(set(pids))
    for handle in handles:
        user.PostMessageW(handle, message, wparam, 0)
    return len(handles)


def quit_processes(pids, alive, wait=8):
    """Ask a client to quit without killing it; return the pids that are still alive afterwards.

    `alive` is a callable returning the live subset of `pids`. Windows first gets WM_CLOSE (what the
    window's X does), then the session-end messages, which Electron apps that hide to the tray honour
    by really exiting. POSIX gets SIGTERM. Nothing is ever force killed here.
    """
    pids = [pid for pid in pids if pid != os.getpid()]
    steps = []
    if sys.platform == "win32":
        steps = [lambda: _signal_windows(pids, WM_CLOSE),
                 lambda: (_signal_windows(pids, WM_QUERYENDSESSION, 0), _signal_windows(pids, WM_ENDSESSION, 1))]
    else:
        def terminate():
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        steps = [terminate]
    remaining = alive(pids)
    for step in steps:
        if not remaining:
            break
        step()
        deadline = time.monotonic() + wait
        while remaining and time.monotonic() < deadline:
            time.sleep(0.4)
            remaining = alive(pids)
    return remaining


USER_ENVIRONMENT_JOURNAL = "user-environment-journal.json"


def _restore_user_environment(key, saved):
    import winreg
    for name, old in saved.items():
        try:
            if old is None:
                winreg.DeleteValue(key, name)
            else:
                winreg.SetValueEx(key, name, 0, old[1], old[0])
        except FileNotFoundError:
            pass


def restore_user_environment(journal):
    """Undo a temporary user environment that a crashed or killed Hub left behind; True when something was restored."""
    import json
    import winreg
    journal = Path(journal)
    try:
        saved = {name: (None if old is None else (old[0], old[1]))
                 for name, old in json.loads(journal.read_text(encoding="utf-8")).items()}
    except FileNotFoundError:
        return False
    except (OSError, ValueError, TypeError, IndexError):
        journal.unlink(missing_ok=True)  # unreadable journal: nothing trustworthy to restore
        return False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
        _restore_user_environment(key, saved)
    journal.unlink(missing_ok=True)
    return True


@contextmanager
def temporary_user_environment(values, hold=5, journal=None):
    """Expose variables through the HKCU Environment key while a packaged app starts, then restore the old values.

    Packaged Windows apps are activated by the system and do not receive the caller's environment.
    The original values are written to the journal file first, so the next start of Hub can restore them after a crash.
    """
    import json
    import winreg
    saved = {}
    if journal is not None:
        # A journal left by a crashed run holds the real originals; undo it first so it is never
        # overwritten with values this feature wrote itself.
        restore_user_environment(journal)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
        try:
            for name in values:
                try:
                    saved[name] = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    saved[name] = None
            if journal is not None:
                journal = Path(journal)
                journal.parent.mkdir(parents=True, exist_ok=True)
                journal.write_text(json.dumps(saved), encoding="utf-8")
            for name, value in values.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            yield
            time.sleep(hold)
        finally:
            _restore_user_environment(key, saved)
            if journal is not None:
                Path(journal).unlink(missing_ok=True)


def detached(command, *, env=None, cwd=None, console=False):
    kwargs = {"env": env, "cwd": cwd}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE if console else subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    if not console:
        kwargs.update(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return subprocess.Popen(command, **kwargs)
    except OSError as error:
        if getattr(error, "winerror", None) == 740:  # ERROR_ELEVATION_REQUIRED
            raise OSError(error.errno, f"Windows requires administrator rights to start {Path(str(command[0])).name}. "
                          "Remove the Run as administrator compatibility setting from the application, then try again.") from error
        raise


def application_entry():
    return Path(__file__).resolve().parents[1] / "scripts" / "main.py"


def terminal_command(command):
    if sys.platform == "win32":
        return command
    if sys.platform == "darwin":
        script = 'on run argv\n tell application "Terminal"\n do script (item 1 of argv)\n activate\n end tell\nend run'
        return ["/usr/bin/osascript", "-e", script, shlex.join(command)]
    for name, flag in (("gnome-terminal", "--"), ("konsole", "-e"), ("xfce4-terminal", "-x"),
                       ("xterm", "-e"), ("kitty", None), ("alacritty", "-e"), ("x-terminal-emulator", "-e")):
        terminal = shutil.which(name)
        if terminal:
            return [terminal, *([flag] if flag else []), *command]
    raise OSError("Install a supported terminal such as GNOME Terminal, Konsole or xterm.")


def open_terminal(profile_id, login=False):
    command = application_command() + ["--session", profile_id]
    if login:
        command.append("--login")
    return detached(terminal_command(command), console=sys.platform == "win32")


def application_command():
    # Nuitka and frozen builds re-enter the bundled executable, not a source path.
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return [sys.executable if getattr(sys, "frozen", False) else str(Path(sys.argv[0]).resolve())]
    return [sys.executable, str(application_entry())]


def prepare_session_console():
    """Windowed packages still need interactive standard streams for CLI profiles."""
    if sys.platform != "win32":
        return
    import ctypes
    kernel = ctypes.windll.kernel32
    if not kernel.GetConsoleWindow():
        kernel.AllocConsole()
    # Preserve redirected pipes used by package smoke tests and automation.
    for name, device, mode in (("stdin", "CONIN$", "r"), ("stdout", "CONOUT$", "w"), ("stderr", "CONOUT$", "w")):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, open(device, mode, encoding="utf-8"))


def uses_profile_directory(arguments, folder):
    """Compare only user-data-dir arguments, with platform path semantics."""
    normalize = ntpath.normcase if sys.platform == "win32" else posixpath.normcase
    normpath = ntpath.normpath if sys.platform == "win32" else posixpath.normpath
    separator = "\\" if sys.platform == "win32" else "/"
    root = normalize(normpath(str(folder))).rstrip(separator)
    # Accept --flag=value, --flag value, and a quoted whole --flag=value token.
    pattern = r'''(?:^|\s)(?:"--user-data-dir=([^"\r\n]+)"|'--user-data-dir=([^'\r\n]+)'|--user-data-dir(?:=|\s+)(?:"([^"\r\n]+)"|'([^'\r\n]+)'|([^\s"']+)))'''
    for match in re.finditer(pattern, arguments, re.MULTILINE):
        value = normalize(normpath(next(part for part in match.groups() if part is not None))).rstrip(separator)
        if value == root or value.startswith(root + separator):
            return True
    return False


@contextmanager
def profile_lock(path):
    """Hold one OS lock per profile while its interactive CLI is running."""
    private_directory(path.parent)
    with path.open("a+b") as stream:
        stream.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise OSError("Close the terminal for this profile, then try again.") from error
        try:
            yield
        finally:
            if sys.platform == "win32":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
