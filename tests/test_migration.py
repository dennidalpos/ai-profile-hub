from contextlib import closing
import sqlite3
import subprocess
from unittest.mock import patch

from profile_switch import migration


def folders(tmp_path):
    return tmp_path / "old", tmp_path / "new"


def run(tmp_path, running="", error=None):
    old, new = folders(tmp_path)
    with (patch.object(migration, "legacy_data_root", return_value=old),
          patch.object(migration, "current_data_root", return_value=new),
          patch.object(migration, "process_arguments", side_effect=error, return_value=running)):
        return migration.migrate_data_root()


def test_nothing_to_do_without_a_legacy_folder_or_when_the_new_one_exists(tmp_path):
    assert run(tmp_path) is None
    old, new = folders(tmp_path)
    old.mkdir()
    new.mkdir()
    assert run(tmp_path) is None and old.exists()


def test_legacy_folder_is_renamed_and_codex_paths_follow(tmp_path):
    old, new = folders(tmp_path)
    codex = old / "sessions" / ("a" * 32) / "codex"
    (codex / "sessions").mkdir(parents=True)
    (codex / "sessions" / "r.jsonl").write_text("{}", encoding="utf-8")
    with closing(sqlite3.connect(codex / "state_5.sqlite")) as db, db:
        db.execute("CREATE TABLE threads (id TEXT, rollout_path TEXT)")
        db.execute("INSERT INTO threads VALUES ('t', ?)", (str(codex / "sessions" / "r.jsonl"),))
    assert run(tmp_path) == "migrated"
    assert not old.exists()
    moved = new / "sessions" / ("a" * 32) / "codex"
    with closing(sqlite3.connect(moved / "state_5.sqlite")) as db:
        assert db.execute("SELECT rollout_path FROM threads").fetchone()[0] == str(moved / "sessions" / "r.jsonl")


def test_migration_is_deferred_while_something_uses_the_folder_or_the_check_fails(tmp_path):
    old, new = folders(tmp_path)
    old.mkdir()
    assert run(tmp_path, running=f'Claude.exe --user-data-dir="{old / "sessions" / "x"}"') == "deferred"
    assert run(tmp_path, error=subprocess.SubprocessError("x")) == "deferred"
    assert old.exists() and not new.exists()
    with patch.object(type(old), "rename", side_effect=PermissionError("locked")):
        assert run(tmp_path) == "deferred"


def test_data_root_keeps_the_legacy_folder_until_it_is_migrated(tmp_path):
    from profile_switch import store
    old, new = folders(tmp_path)
    with (patch.object(store, "legacy_data_root", return_value=old),
          patch.object(store, "current_data_root", return_value=new)):
        assert store.data_root() == new
        old.mkdir()
        assert store.data_root() == old
        new.mkdir()
        assert store.data_root() == new
