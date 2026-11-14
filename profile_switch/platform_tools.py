"""Process, terminal and file-lock primitives for each operating system."""

from contextlib import contextmanager
import os
from pathlib import Path
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
    archive = getattr(sys.modules[__name__].__loader__, "archive", None)
    if archive:
        return Path(archive).resolve()
    return Path(__file__).resolve().parent.parent / "main.py"


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
    raise OSError("Installa un terminale supportato, ad esempio GNOME Terminal, Konsole o xterm.")


def open_terminal(profile_id, login=False):
    command = [sys.executable, str(application_entry()), "--session", profile_id]
    if login:
        command.append("--login")
    return detached(terminal_command(command), console=sys.platform == "win32")


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
            raise OSError("Chiudi il terminale di questo profilo, poi riprova.") from error
        try:
            yield
        finally:
            if sys.platform == "win32":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
