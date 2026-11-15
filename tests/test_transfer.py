import json
import sqlite3
import tomllib

from profile_switch import transfer
from profile_switch.store import Profile


def profile(service, mode):
    return Profile("d" * 32, service, "Test", mode)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def pick(home, folder, service, mode, key):
    return [c for c in transfer.categories(profile(service, mode), folder, home) if c.key == key]


def test_claude_mcp_import_is_additive_and_skips_identity(tmp_path):
    home, folder = tmp_path / "home", tmp_path / "profile"
    write(home / ".claude.json", json.dumps({
        "oauthAccount": {"email": "a@example.test"}, "userID": "u",
        "mcpServers": {"one": {"command": "x"}, "two": {"command": "y"}},
        "projects": {"/repo": {"mcpServers": {"p": {"command": "z"}}, "history": ["secret prompt"],
                               "hasTrustDialogAccepted": True}}}))
    write(folder / "claude-code" / ".claude.json", json.dumps({"mcpServers": {"one": {"command": "different"}}}))
    report = transfer.transfer(pick(home, folder, "claude", "cli", "mcp"), transfer.IMPORT, tmp_path / "backups")
    result = json.loads((folder / "claude-code" / ".claude.json").read_text(encoding="utf-8"))
    assert result["mcpServers"]["one"] == {"command": "different"}
    assert result["mcpServers"]["two"] == {"command": "y"}
    assert result["projects"]["/repo"] == {"mcpServers": {"p": {"command": "z"}}, "hasTrustDialogAccepted": True}
    assert "oauthAccount" not in result and "userID" not in result
    assert any("mcpServers.one" in item for item in report.conflicts)
    assert report.backup is not None


def test_history_copy_skips_credentials_and_existing_files(tmp_path):
    home, folder = tmp_path / "home", tmp_path / "profile"
    write(home / ".claude" / "projects" / "repo" / "a.jsonl", "new")
    write(home / ".claude" / "projects" / "repo" / ".credentials.json", "token")
    write(home / ".claude" / "history.jsonl", "source")
    write(folder / "claude-code" / "history.jsonl", "kept")
    report = transfer.transfer(pick(home, folder, "claude", "cli", "history"), transfer.IMPORT, tmp_path / "b")
    assert (folder / "claude-code" / "projects" / "repo" / "a.jsonl").read_text(encoding="utf-8") == "new"
    assert not (folder / "claude-code" / "projects" / "repo" / ".credentials.json").exists()
    assert (folder / "claude-code" / "history.jsonl").read_text(encoding="utf-8") == "kept"
    assert report.skipped


def test_codex_config_merge_keeps_credential_store_and_adds_servers(tmp_path):
    home, folder = tmp_path / "home", tmp_path / "profile"
    write(home / ".codex" / "config.toml", 'model = "m"\napi_token = "x"\n\n[mcp_servers.alpha]\ncommand = "a"\n'
          '[mcp_servers.alpha.env]\nKEY = "v"\n\n[mcp_servers.beta]\ncommand = "b"\n')
    write(folder / "codex" / "config.toml", 'cli_auth_credentials_store = "file"\n\n[mcp_servers.beta]\ncommand = "own"\n')
    transfer.transfer(pick(home, folder, "chatgpt", "cli", "mcp"), transfer.IMPORT, tmp_path / "b")
    merged = tomllib.loads((folder / "codex" / "config.toml").read_text(encoding="utf-8"))
    assert merged["cli_auth_credentials_store"] == "file"
    assert merged["model"] == "m" and "api_token" not in merged
    assert merged["mcp_servers"]["alpha"] == {"command": "a", "env": {"KEY": "v"}}
    assert merged["mcp_servers"]["beta"] == {"command": "own"}


def test_export_merges_into_original_and_backup_can_restore(tmp_path):
    home, folder = tmp_path / "home", tmp_path / "profile"
    write(home / ".claude.json", json.dumps({"mcpServers": {"old": {"command": "o"}}, "oauthAccount": {"a": 1}}))
    write(folder / "claude-code" / ".claude.json", json.dumps({"mcpServers": {"new": {"command": "n"}}}))
    before = (home / ".claude.json").read_text(encoding="utf-8")
    report = transfer.transfer(pick(home, folder, "claude", "cli", "mcp"), transfer.EXPORT, tmp_path / "b")
    merged = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    assert set(merged["mcpServers"]) == {"old", "new"} and merged["oauthAccount"] == {"a": 1}
    transfer.restore(report.backup)
    assert (home / ".claude.json").read_text(encoding="utf-8") == before


def test_sqlite_history_is_copied_with_backup_api(tmp_path):
    home, folder = tmp_path / "home", tmp_path / "profile"
    (home / ".codex").mkdir(parents=True)
    with sqlite3.connect(home / ".codex" / "state_5.sqlite") as db:
        db.execute("CREATE TABLE t (v)")
        db.execute("INSERT INTO t VALUES (1)")
    db.close()
    transfer.transfer(pick(home, folder, "chatgpt", "cli", "history"), transfer.IMPORT, tmp_path / "b")
    with sqlite3.connect(folder / "codex" / "state_5.sqlite") as copied:
        assert copied.execute("SELECT v FROM t").fetchone() == (1,)
    copied.close()


def test_web_profiles_have_nothing_to_transfer(tmp_path):
    assert transfer.categories(profile("claude", "chat"), tmp_path, tmp_path) == []


def test_launch_adds_credential_store_to_an_imported_codex_config(tmp_path):
    from profile_switch import launch
    home = tmp_path / "codex"
    write(home / "config.toml", 'model = "m"\n\n[mcp_servers.a]\ncommand = "x"\n')
    launch.codex_home(tmp_path)
    saved = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    assert saved["cli_auth_credentials_store"] == "file" and saved["mcp_servers"]["a"]["command"] == "x"
