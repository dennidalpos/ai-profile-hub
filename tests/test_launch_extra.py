from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
from unittest.mock import patch

import pytest

from profile_switch import launch, platform_tools, shortcuts, store, transfer
from profile_switch.store import Profile


# ---------------------------------------------------------------- shortcuts


def test_desktop_directory_prefers_the_system_answer_and_falls_back_to_home(tmp_path):
    with patch.object(shortcuts.sys, "platform", "win32"), patch.object(shortcuts, "powershell", return_value=f" {tmp_path}\n"):
        assert shortcuts.desktop_directory() == tmp_path
    with patch.object(shortcuts.sys, "platform", "win32"), patch.object(shortcuts, "powershell", side_effect=OSError):
        assert shortcuts.desktop_directory() == Path.home() / "Desktop"
    done = subprocess.CompletedProcess([], 0, stdout=f"{tmp_path}\n")
    with patch.object(shortcuts.sys, "platform", "linux"), patch.object(shortcuts.subprocess, "run", return_value=done):
        assert shortcuts.desktop_directory() == tmp_path
    done = subprocess.CompletedProcess([], 0, stdout=f"{Path.home()}\n")
    with patch.object(shortcuts.sys, "platform", "linux"), patch.object(shortcuts.subprocess, "run", return_value=done):
        assert shortcuts.desktop_directory() == Path.home() / "Desktop"
    with patch.object(shortcuts.sys, "platform", "linux"), patch.object(shortcuts.subprocess, "run", side_effect=OSError):
        assert shortcuts.desktop_directory() == Path.home() / "Desktop"
    with patch.object(shortcuts.sys, "platform", "darwin"):
        assert shortcuts.desktop_directory() == Path.home() / "Desktop"


def test_desktop_entry_escapes_arguments_and_never_overwrites(tmp_path):
    assert shortcuts.exec_escape('a"b$c`d\\e%f') == 'a\\"b\\$c\\`d\\\\e%%f'
    assert shortcuts.profile_arguments("x") == ["--launch", "x"]
    with patch.object(shortcuts.sys, "platform", "linux"):
        first = shortcuts.create_shortcut("Work", ["--launch", "id"], tmp_path, ["/opt/hub app"])
        second = shortcuts.create_shortcut("Work", [], tmp_path, ["/opt/hub"])
    assert first.name == "Work.desktop" and second.name == "Work (2).desktop"
    text = first.read_text(encoding="utf-8")
    assert 'Exec="/opt/hub app" "--launch" "id"' in text and "Terminal=false" in text


def test_macos_shortcut_is_an_executable_script(tmp_path):
    with patch.object(shortcuts.sys, "platform", "darwin"):
        path = shortcuts.create_shortcut("Mac", ["--launch", "id"], tmp_path, ["/Apps/Hub app"])
    assert path.suffix == ".command"
    assert path.read_text(encoding="utf-8") == "#!/bin/sh\nexec '/Apps/Hub app' --launch id\n"


# ---------------------------------------------------------------- launch helpers


def test_windows_executable_needs_a_program_header(tmp_path):
    real, fake, script = tmp_path / "a.exe", tmp_path / "b.exe", tmp_path / "c.cmd"
    real.write_bytes(b"MZ\x90")
    fake.write_bytes(b"text")
    script.write_text("@echo off", encoding="utf-8")
    with patch.object(launch.sys, "platform", "win32"):
        assert launch.executable(real) and launch.executable(script) and not launch.executable(fake)
        assert not launch.executable(tmp_path / "missing.exe")


def test_browser_candidates_per_platform(tmp_path, monkeypatch):
    with patch.object(launch.sys, "platform", "darwin"):
        assert any("Google Chrome" in str(path) for path in launch.browser_candidates())
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    with patch.object(launch.sys, "platform", "win32"):
        assert any(str(tmp_path) in str(path) for path in launch.browser_candidates())
    with patch.object(launch.sys, "platform", "linux"), patch.object(launch.shutil, "which", side_effect=lambda n: f"/bin/{n}"):
        assert Path("/bin/chromium") in list(launch.browser_candidates())


def test_browser_path_reports_missing_or_stale_browsers(tmp_path):
    database = store.Store(tmp_path / "s")
    with patch.object(launch, "browser_candidates", return_value=[]), pytest.raises(OSError, match="Install"):
        launch.browser_path(database)
    database.save_browser(tmp_path / "gone")
    with pytest.raises(OSError, match="unavailable"):
        launch.browser_path(database)


def test_client_environment_drops_credentials_and_refuses_google_gateways(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert "ANTHROPIC_API_KEY" not in launch.client_environment("claude")
    assert "OPENAI_API_KEY" not in launch.client_environment("chatgpt")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://gateway.test")
    with pytest.raises(ValueError, match="GOOGLE_GEMINI_BASE_URL"):
        launch.client_environment("gemini")


def test_resolve_executable_and_workdir_errors(tmp_path):
    with pytest.raises(OSError, match="unavailable"):
        launch.resolve_executable(tmp_path / "missing")
    with pytest.raises(OSError, match="Working directory"):
        launch.resolve_workdir(str(tmp_path / "missing"))
    assert launch.resolve_workdir("") == Path.home()
    with pytest.raises(OSError, match="Client not found"), patch.object(launch, "binary_candidates", return_value=[]):
        launch.find_binary(Profile("a" * 32, "claude", "n", "cli"))


def test_macos_app_bundle_resolves_to_its_executable(tmp_path):
    bundle = tmp_path / "Claude.app"
    binary = bundle / "Contents" / "MacOS" / "Claude"
    binary.parent.mkdir(parents=True)
    binary.touch()
    binary.chmod(0o755)
    import plistlib
    (bundle / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Claude"}))
    with patch.object(launch.sys, "platform", "darwin"), patch.object(launch, "executable", return_value=True):
        assert launch.resolve_executable(str(bundle)) == binary
    (bundle / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "../evil"}))
    with patch.object(launch.sys, "platform", "darwin"), pytest.raises(ValueError):
        launch.resolve_executable(str(bundle))


def test_codex_home_creates_repairs_and_refuses_conflicting_config(tmp_path):
    home = Path(launch.codex_home(tmp_path / "p"))
    assert 'cli_auth_credentials_store = "file"' in (home / "config.toml").read_text(encoding="utf-8")
    launch.codex_home(tmp_path / "p")  # idempotent
    (home / "config.toml").write_text('model = "m"\n[mcp_servers.a]\ncommand = "a"\n', encoding="utf-8")
    launch.codex_home(tmp_path / "p")
    assert (home / "config.toml").read_text(encoding="utf-8").startswith('cli_auth_credentials_store = "file"\nmodel')
    (home / "config.toml").write_text('cli_auth_credentials_store = "keyring"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="file"):
        launch.codex_home(tmp_path / "p")
    (home / "config.toml").write_text("= broken", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid TOML"):
        launch.codex_home(tmp_path / "p")


# ---------------------------------------------------------------- desktop conflicts


def test_posix_conflicts_ignore_the_terminal_client_and_helpers(tmp_path):
    desktop = tmp_path / "app" / "Claude"
    cli = tmp_path / "bin" / "claude"
    for path in (desktop, cli):
        path.parent.mkdir()
        path.touch()
    profile = Profile("a" * 32, "claude", "n", "desktop")
    rows = [(1, "", str(desktop)), (2, "", str(cli) + " --resume"), (3, "", str(desktop) + " --type=renderer")]
    with (patch.object(launch.sys, "platform", "linux"), patch.object(launch, "desktop_processes", return_value=rows),
          patch.object(launch, "binary_candidates", side_effect=lambda key: [cli] if key == ("claude", "cli") else [])):
        found = launch.desktop_conflicts(profile, desktop)
    assert [pid for pid, _ in found] == [1]


def test_windows_conflicts_ignore_the_terminal_client_by_path(tmp_path):
    cli = tmp_path / "claude.exe"
    cli.touch()
    desktop = tmp_path / "app" / "Claude.exe"
    profile = Profile("a" * 32, "claude", "n", "desktop")
    rows = [(1, "claude.exe", str(cli)), (2, "Claude.exe", str(desktop)), (3, "Claude.exe", "")]
    with (patch.object(launch.sys, "platform", "win32"), patch.object(launch, "desktop_processes", return_value=rows),
          patch.object(launch, "binary_candidates", side_effect=lambda key: [cli] if key == ("claude", "cli") else [])):
        found = launch.desktop_conflicts(profile, desktop)
    assert [pid for pid, _ in found] == [2, 3]


def test_windows_process_listing_reports_executable_paths():
    output = "5\tClaude.exe\tC:\\Apps\\Claude.exe\r\n6\tx.exe\r\n"
    with patch.object(platform_tools.sys, "platform", "win32"), patch.object(platform_tools, "powershell", return_value=output):
        assert platform_tools.desktop_processes() == [(5, "Claude.exe", "C:\\Apps\\Claude.exe"), (6, "x.exe", "")]


# ---------------------------------------------------------------- store and transfer hardening


def test_old_profile_database_is_copied_before_it_is_upgraded(tmp_path):
    database = tmp_path / "profiles.sqlite3"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE profiles (id TEXT PRIMARY KEY, service TEXT, name TEXT, name_key TEXT, mode TEXT)")
        db.execute("INSERT INTO profiles VALUES ('a', 'claude', 'Work', 'work', 'web')")
        db.execute("PRAGMA user_version = 2")
    profiles = store.Store(tmp_path).profiles()
    assert [p.name for p in profiles] == ["Work"]
    backup = tmp_path / "profiles.sqlite3.v2.bak"
    with closing(sqlite3.connect(backup)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    store.Store(tmp_path)  # current schema: no new copy
    assert [p.name for p in tmp_path.glob("*.bak")] == [backup.name]


def test_database_copy_is_atomic_and_refuses_a_target_in_use(tmp_path):
    source, target = tmp_path / "s.sqlite", tmp_path / "t.sqlite"
    for path, value in ((source, "new"), (target, "old")):
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE t (v)")
            db.execute("INSERT INTO t VALUES (?)", (value,))
    holder = sqlite3.connect(target)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(OSError, match="in use"):
            transfer.copy_database(source, target)
    finally:
        holder.rollback()
        holder.close()
    with closing(sqlite3.connect(target)) as db:
        assert db.execute("SELECT v FROM t").fetchone()[0] == "old"
    assert not list(tmp_path.glob("*.tmp"))
    transfer.copy_database(source, target)
    with closing(sqlite3.connect(target)) as db:
        assert db.execute("SELECT v FROM t").fetchone()[0] == "new"


def test_claude_msix_activation_needs_the_start_menu_identity():
    with patch.object(launch, "powershell", return_value="Other_abc!App\r\n"), pytest.raises(OSError, match="app identity"):
        launch.activate_claude_msix(["--user-data-dir=x"])


def test_windows_package_blocks_the_known_bad_claude_version(tmp_path):
    with (patch.object(launch, "powershell", return_value=f"{tmp_path}\n2.42304.1.0\n"),
          pytest.raises(ValueError, match="Update Claude Desktop")):
        launch.windows_package(("claude", "desktop"))
    with patch.object(launch, "powershell", return_value=""):
        assert launch.windows_package(("claude", "desktop")) is None
    assert launch.windows_package(("gemini", "ide")) is None
