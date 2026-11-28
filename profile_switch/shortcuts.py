"""Desktop shortcuts that open the Hub or launch one profile, for Windows, macOS and Linux."""

from pathlib import Path
import re
import shlex
import subprocess
import sys

from .platform_tools import application_command, powershell

INVALID_NAME = re.compile(r'[<>:"/\|?*\x00-\x1f]')


def shortcut_name(title):
    name = INVALID_NAME.sub("-", title).strip(" .-") or "AI Profile Hub"
    return name[:80]


def desktop_directory():
    """The user's real desktop folder, including redirected ones (OneDrive, XDG)."""
    if sys.platform == "win32":
        try:
            found = powershell("[Environment]::GetFolderPath('Desktop')").strip()
            if found:
                return Path(found)
        except (OSError, subprocess.SubprocessError):
            pass
    elif sys.platform != "darwin":
        try:
            found = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5,
                                   check=True).stdout.strip()
            if found and Path(found) != Path.home():
                return Path(found)
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / "Desktop"


def profile_arguments(profile_id):
    return ["--launch", profile_id]


def exec_escape(part):
    """Escape one argument for a quoted Exec= value of a .desktop file."""
    escaped = part.replace(chr(92), chr(92) * 2)
    for special in ('"', "$", "`"):
        escaped = escaped.replace(special, chr(92) + special)
    return escaped.replace("%", "%%")


def _unique(path):
    """Never overwrite a file the user may have edited."""
    candidate, number = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate


def create_shortcut(title, arguments=(), directory=None, command=None):
    """Write a launcher for the Hub (no arguments) or a profile; returns the new file's path."""
    argv = list(command if command is not None else application_command()) + list(arguments)
    directory = Path(directory) if directory else desktop_directory()
    directory.mkdir(parents=True, exist_ok=True)
    name = shortcut_name(title)
    if sys.platform == "win32":
        path = _unique(directory / f"{name}.lnk")
        quote = lambda text: str(text).replace("'", "''")
        powershell(
            "$shell = New-Object -ComObject WScript.Shell; "
            f"$link = $shell.CreateShortcut('{quote(path)}'); "
            f"$link.TargetPath = '{quote(argv[0])}'; "
            f"$link.Arguments = '{quote(subprocess.list2cmdline(argv[1:]))}'; "
            f"$link.WorkingDirectory = '{quote(Path(argv[0]).parent)}'; "
            f"$link.Description = '{quote(title)}'; $link.Save()")
    elif sys.platform == "darwin":
        path = _unique(directory / f"{name}.command")
        path.write_text("#!/bin/sh\nexec " + shlex.join(argv) + "\n", encoding="utf-8")
        path.chmod(0o755)
    else:
        path = _unique(directory / f"{name}.desktop")
        exec_line = " ".join('"' + exec_escape(part) + '"' for part in argv)
        path.write_text("[Desktop Entry]\nType=Application\nVersion=1.0\n"
                        f"Name={title.replace(chr(10), ' ')}\nExec={exec_line}\nTerminal=false\nCategories=Utility;\n",
                        encoding="utf-8")
        path.chmod(0o755)
    return path
