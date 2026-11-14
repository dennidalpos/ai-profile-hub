"""Process, terminal and file-lock primitives for each operating system."""

from contextlib import contextmanager
import os
import ntpath
import posixpath
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


def windows_powershell():
    return Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"


def powershell(script):
    prefix = "$ErrorActionPreference = 'Stop'; [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
    return subprocess.run([str(windows_powershell()), "-NoProfile", "-NonInteractive", "-Command", prefix + script],
                          check=True, capture_output=True, encoding="utf-8-sig", errors="replace",
                          timeout=12, creationflags=subprocess.CREATE_NO_WINDOW).stdout


def process_arguments():
    if sys.platform == "win32":
        return powershell("$session = (Get-Process -Id $PID).SessionId; "
                          'Get-CimInstance Win32_Process -Filter "SessionId = $session" | '
                          "ForEach-Object { $_.CommandLine }")
    return subprocess.run(["ps", "-axww", "-o", "command="], check=True, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=8).stdout


def detached(command, *, env=None, cwd=None, console=False):
    kwargs = {"env": env, "cwd": cwd}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE if console else subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    if not console:
        kwargs.update(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.Popen(command, **kwargs)


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
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
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
