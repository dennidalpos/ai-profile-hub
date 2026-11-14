"""Launch user-installed clients with per-profile state."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
from uuid import UUID

from .catalog import CLI_NAMES, TARGETS, URLS
from .platform_tools import detached, open_terminal, powershell, process_arguments
from .store import duo_directory


@dataclass(frozen=True)
class Command:
    argv: list[str]
    env: dict[str, str]
    cwd: Path


def executable(path):
    return path.is_file() and os.access(path, os.X_OK)


def browser_candidates():
    if sys.platform == "darwin":
        for base in (Path("/Applications"), Path.home() / "Applications"):
            for name in ("Google Chrome", "Chromium"):
                yield base / f"{name}.app" / "Contents" / "MacOS" / name
    elif sys.platform == "win32":
        for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(key)
            if base:
                yield Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
                yield Path(base) / "Chromium" / "Application" / "chrome.exe"
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            path = shutil.which(name)
            if path:
                yield Path(path)


def browser_path(store):
    saved = store.browser()
    if saved:
        if executable(saved):
            return saved
        raise OSError("Il browser configurato non è disponibile. Selezionalo di nuovo dal menu.")
    browser = next((path for path in browser_candidates() if executable(path)), None)
    if browser is None:
        raise OSError("Installa Google Chrome o Chromium, oppure seleziona l’eseguibile dal menu.")
    store.save_browser(browser)
    return browser


def client_environment(service):
    env = os.environ.copy()
    credentials = {
        "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"),
        "chatgpt": ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"),
        "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"),
    }
    for name in credentials[service]:
        env.pop(name, None)
    return env


MAC_BUNDLES = {
    ("claude", "desktop"): (("Claude", "Claude"),),
    ("chatgpt", "desktop"): (("Codex", "Codex"), ("ChatGPT", "ChatGPT")),
    ("gemini", "ide"): (("Antigravity IDE", "Antigravity IDE"), ("Antigravity IDE", "Electron")),
    ("gemini", "desktop"): (("Antigravity", "Antigravity"), ("Antigravity", "Electron")),
}
WINDOWS_DESKTOP = {
    ("claude", "desktop"): ("AnthropicClaude/Claude.exe", "Programs/Claude/Claude.exe"),
    ("chatgpt", "desktop"): ("Programs/OpenAI/Codex/Codex.exe", "Programs/Codex/Codex.exe"),
    ("gemini", "ide"): ("Programs/Antigravity/Antigravity IDE.exe", "Programs/Antigravity IDE/Antigravity IDE.exe"),
    ("gemini", "desktop"): ("Programs/Antigravity/Antigravity.exe",),
}
LINUX_DESKTOP = {
    ("claude", "desktop"): ("claude-desktop",),
    ("chatgpt", "desktop"): ("codex-desktop", "chatgpt-desktop", "chatgpt"),
    ("gemini", "ide"): ("antigravity-ide",),
    ("gemini", "desktop"): ("antigravity",),
}


def windows_package(key):
    package = {("claude", "desktop"): "Claude", ("chatgpt", "desktop"): "OpenAI.Codex"}.get(key)
    if not package:
        return None
    response = powershell(f"Get-AppxPackage -Name '{package}' | Sort-Object Version -Descending | "
                          "Select-Object -First 1 | ForEach-Object { $_.InstallLocation; $_.Version }")
    lines = response.strip().splitlines()
    if len(lines) < 2:
        return None
    location, version = lines[:2]
    if package == "Claude" and version.split(".")[:2] == ["2", "42304"]:
        raise ValueError("Aggiorna Claude Desktop. La versione MSIX 2.42304.x può ignorare il profilo separato.")
    names = ("Claude.exe",) if package == "Claude" else ("ChatGPT.exe", "Codex.exe")
    return next((path for name in names if (path := Path(location) / "app" / name).is_file()), None)


def activate_claude_msix(argv):
    # The package's default activation can accept arguments when direct exec is blocked.
    entries = powershell("Get-StartApps | ForEach-Object { $_.AppID }")
    app_id = next((line.strip() for line in entries.splitlines()
                   if re.fullmatch(r"Claude_[a-z0-9]+![a-z0-9_.-]+", line.strip(), re.IGNORECASE)), None)
    if not app_id:
        raise OSError("Impossibile trovare l’identità dell’app Claude Desktop nel menu Start.")
    import ctypes
    ole = ctypes.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoCreateInstance.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                                    ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    ole.CoCreateInstance.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = ()
    ole.CoUninitialize.restype = None

    def check(result):
        if result < 0:
            raise OSError(f"Attivazione Claude Desktop non riuscita (0x{result & 0xFFFFFFFF:08X}).")

    clsid = ctypes.create_string_buffer(UUID("45ba127d-10a8-46ea-8ab7-56ea9078943c").bytes_le, 16)
    iid = ctypes.create_string_buffer(UUID("2e941141-7f97-4756-ba1d-9decde894a3d").bytes_le, 16)
    check(ole.CoInitializeEx(None, 2))
    try:
        manager = ctypes.c_void_p()
        check(ole.CoCreateInstance(clsid, None, 4, iid, ctypes.byref(manager)))
        vtable = ctypes.cast(manager, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
        try:
            activate = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                         ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong))(vtable[3])
            pid = ctypes.c_ulong()
            check(activate(manager, app_id, subprocess.list2cmdline(argv), 0, ctypes.byref(pid)))
        finally:
            release(manager)
    finally:
        ole.CoUninitialize()


def is_windows_package(path):
    return sys.platform == "win32" and "windowsapps" in (part.casefold() for part in path.parts)


def binary_candidates(key):
    if key in CLI_NAMES:
        name = CLI_NAMES[key]
        command = shutil.which(name)
        if command:
            yield Path(command)
        home = Path.home()
        if sys.platform == "win32":
            yield home / ".local" / "bin" / f"{name}.exe"
            local = Path(os.environ["LOCALAPPDATA"])
            yield local / "Programs/OpenAI/Codex/bin" / f"{name}.exe"
            if name == "agy":
                yield local / "agy/bin/agy.exe"
            if os.environ.get("APPDATA"):
                yield Path(os.environ["APPDATA"]) / "npm" / f"{name}.cmd"
        else:
            for parent in (home / ".local/bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
                yield parent / name
        return
    if sys.platform == "darwin":
        for base in (Path("/Applications"), Path.home() / "Applications"):
            for bundle, binary in MAC_BUNDLES[key]:
                yield base / f"{bundle}.app" / "Contents" / "MacOS" / binary
    elif sys.platform == "win32":
        package = windows_package(key)
        if package:
            yield package
        for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
            if base:
                for name in WINDOWS_DESKTOP[key]:
                    yield Path(base) / name
    else:
        for name in LINUX_DESKTOP[key]:
            path = shutil.which(name)
            if path:
                yield Path(path)
        if key == ("gemini", "ide"):
            yield Path("/usr/share/antigravity-ide/antigravity-ide")


def find_binary(profile):
    if profile.executable:
        path = Path(profile.executable).expanduser()
        if sys.platform == "darwin" and path.is_dir() and path.suffix == ".app":
            import plistlib
            with (path / "Contents/Info.plist").open("rb") as stream:
                binary = plistlib.load(stream).get("CFBundleExecutable", "")
            if not binary or Path(binary).name != binary:
                raise ValueError("Il bundle macOS non indica un eseguibile valido.")
            path = path / "Contents" / "MacOS" / binary
        if executable(path):
            return path
        raise OSError(f"Executable unavailable: {path}. Choose another executable in the profile editor.")
    key = (profile.service, profile.mode)
    candidate = next((path for path in binary_candidates(key)
                      if executable(path) or (key == ("claude", "desktop") and is_windows_package(path))), None)
    if candidate:
        return candidate
    raise OSError("Client not found. Install it or select its executable in the profile editor.")


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return str(path)


def codex_home(folder):
    home = folder / "codex"
    private_directory(home)
    config = home / "config.toml"
    try:
        descriptor = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        with config.open("rb") as stream:
            saved = tomllib.load(stream)
        if saved.get("cli_auth_credentials_store") != "file":
            raise ValueError(f'Imposta cli_auth_credentials_store = "file" in {config} per questo profilo.')
    else:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write('cli_auth_credentials_store = "file"\n')
    return str(home)


def google_home(env, folder):
    home = private_directory(folder / "google-home")
    env.update(HOME=home, GEMINI_CLI_HOME=home)
    if sys.platform == "win32":
        drive, path = os.path.splitdrive(home)
        env.update(USERPROFILE=home, HOMEDRIVE=drive, HOMEPATH=path,
                   APPDATA=private_directory(folder / "google-home" / "AppData" / "Roaming"),
                   LOCALAPPDATA=private_directory(folder / "google-home" / "AppData" / "Local"))
    else:
        env.update(XDG_CONFIG_HOME=private_directory(folder / "google-home" / "config"),
                   XDG_DATA_HOME=private_directory(folder / "google-home" / "data"),
                   XDG_STATE_HOME=private_directory(folder / "google-home" / "state"),
                   XDG_CACHE_HOME=private_directory(folder / "google-home" / "cache"))


def resolve_local_client(profile):
    binary = find_binary(profile)
    cwd = Path(profile.workdir).expanduser() if profile.workdir else Path.home()
    if not cwd.is_dir():
        raise OSError(f"Working directory unavailable: {cwd}. Choose another folder in the profile editor.")
    return binary, cwd


def local_command(store, profile, login=False):
    target = TARGETS[profile.service][profile.mode]
    binary, cwd = resolve_local_client(profile)
    if login and target.kind != "cli":
        raise ValueError("Per accedere usa la finestra del client desktop.")
    folder = store.directory(profile)
    private_directory(folder)
    env = client_environment(profile.service)
    args = []
    if profile.service == "claude":
        env["CLAUDE_CONFIG_DIR"] = private_directory(folder / "claude-code")
        if login:
            args = ["auth", "login"]
    elif profile.service == "chatgpt":
        env["CODEX_HOME"] = codex_home(folder)
        env["CODEX_SQLITE_HOME"] = env["CODEX_HOME"]
        if login:
            args = ["login", "--device-auth"]
    else:
        if profile.mode == "gemini-cli":
            env["GEMINI_CLI_HOME"] = private_directory(folder / "google-home")
            env["GEMINI_FORCE_FILE_STORAGE"] = "true"
        else:
            google_home(env, folder)
    if target.kind == "desktop":
        data = duo_directory() if profile.legacy_duo else folder / (
            "claude-desktop" if profile.service == "claude" else "desktop")
        if profile.legacy_duo and not data.is_dir():
            raise OSError("La cartella del profilo Duo non è più disponibile.")
        args = [f"--user-data-dir={private_directory(data)}"]
        if profile.service == "claude" and sys.platform == "darwin":
            env["CLAUDE_USER_DATA_DIR"] = str(data)
        if profile.mode == "ide":
            args.append(f"--extensions-dir={private_directory(folder / 'extensions')}")
            if profile.workdir:
                args.append(str(cwd))
    return Command([str(binary), *args], env, cwd)


def ensure_only_desktop_profile(profile, binary):
    # OAuth protocol handlers can route to the first open window on some builds.
    lines = process_arguments().splitlines()
    aliases = {"claude": r"Claude(?:[ -]Desktop)?", "chatgpt": r"Codex(?:-Desktop)?|ChatGPT(?:-Desktop)?",
               "gemini": r"Antigravity(?:[ -]IDE)?"}
    names = aliases[profile.service] + "|" + re.escape(binary.stem)
    apps = re.compile(rf'(?:^|[/\\"])(?:{names})(?:\.exe|\.app/|"?(?=\s|$))', re.IGNORECASE)
    if any(apps.search(line) and "--type=" not in line for line in lines):
        raise OSError("Esci dalle altre istanze desktop di questo client, poi riprova il primo accesso.")


def open_profile(store, profile, login=False):
    target = TARGETS[profile.service][profile.mode]
    if target.kind == "cli":
        # Check the saved profile before handing off to a separate terminal process.
        # The terminal rechecks it under its session lock before starting the client.
        resolve_local_client(store.profile(profile.id))
        return open_terminal(profile.id, login)
    browser = browser_path(store) if target.kind == "web" else None
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        store.require_profile(db, profile)
        if browser:
            data = private_directory(store.directory(profile) / "browser")
            return detached([str(browser), f"--user-data-dir={data}", "--no-first-run",
                             "--no-default-browser-check", f"--app={URLS[profile.service, profile.mode]}"])
        command = local_command(store, profile)
        if login:
            ensure_only_desktop_profile(profile, Path(command.argv[0]))
        if profile.service == "claude":
            return start_claude_desktop(command)
        return detached(command.argv, env=command.env, cwd=command.cwd)


def start_claude_desktop(command):
    if is_windows_package(Path(command.argv[0])):
        try:
            return detached(command.argv, env=command.env, cwd=command.cwd)
        except (FileNotFoundError, PermissionError):
            # Windows activation forwards the data flag but cannot pass our environment.
            return activate_claude_msix(command.argv[1:])
    if sys.platform != "darwin":
        return detached(command.argv, env=command.env, cwd=command.cwd)
    processes = subprocess.run(["/bin/ps", "-axww", "-o", "pid=", "-o", "command="],
                               capture_output=True, text=True, check=True, timeout=5).stdout
    target = " ".join(command.argv)
    for line in processes.splitlines():
        pid, _, running = line.strip().partition(" ")
        if running.lstrip() == target and pid.isdecimal():
            script = ("ObjC.import('AppKit'); "
                      f"var app = $.NSRunningApplication.runningApplicationWithProcessIdentifier({int(pid)}); "
                      "app.unhide; if (!app.activateWithOptions(2)) throw new Error('Activation failed');")
            return subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                                  capture_output=True, check=True, timeout=5)
    return detached(command.argv, env=command.env, cwd=command.cwd)


def run_cli(store, profile, login):
    if TARGETS[profile.service][profile.mode].kind != "cli":
        raise ValueError("Il profilo selezionato non è un client da terminale.")
    with store.lock(profile):
        profile = store.profile(profile.id)
        command = local_command(store, profile, login)
        # Npm on Windows installs .cmd shims. Pass the executable and fixed arguments
        # through PowerShell variables so the path is never interpolated as code.
        argv = command.argv
        if sys.platform == "win32" and Path(argv[0]).suffix.lower() in (".cmd", ".bat"):
            from .platform_tools import windows_powershell
            import json
            command.env["AI_HUB_PROGRAM"] = argv[0]
            command.env["AI_HUB_ARGS"] = json.dumps(argv[1:])
            argv = [str(windows_powershell()), "-NoProfile", "-Command",
                    "$a = @(ConvertFrom-Json $env:AI_HUB_ARGS); & $env:AI_HUB_PROGRAM @a; exit $LASTEXITCODE"]
        print(f"{TARGETS[profile.service][profile.mode].label} · {profile.name}", flush=True)
        return subprocess.run(argv, env=command.env, cwd=command.cwd, check=False).returncode
