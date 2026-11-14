"""Persist profile metadata and reuse sessions from AI Profile Switch."""

from contextlib import closing, contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from uuid import uuid4

from .catalog import TARGETS
from .platform_tools import process_arguments, profile_lock, uses_profile_directory

COLUMNS = "id, service, name, mode, executable, workdir, legacy_duo"
SCHEMA = """
CREATE TABLE profiles (
    id TEXT PRIMARY KEY, service TEXT NOT NULL, name TEXT NOT NULL,
    name_key TEXT NOT NULL, mode TEXT NOT NULL, executable TEXT NOT NULL DEFAULT '',
    workdir TEXT NOT NULL DEFAULT '', legacy_duo INTEGER NOT NULL DEFAULT 0,
    UNIQUE (service, mode, name_key)
)
"""


@dataclass(frozen=True)
class Profile:
    id: str
    service: str
    name: str
    mode: str
    executable: str = ""
    workdir: str = ""
    legacy_duo: bool = False


def data_root():
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "AI Profile Switch"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "AIProfileSwitch"
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", ""))
    return (xdg_data if xdg_data.is_absolute() else home / ".local" / "share") / "ai-profile-switch"


def duo_directory():
    return data_root().parent / "ClaudeDesktopDuo" / "SecondProfile"


class Store:
    def __init__(self, root):
        self.root = root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.database = root / "profiles.sqlite3"
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(profiles)")}
            if not columns:
                db.execute(SCHEMA)
            elif "legacy_duo" not in columns:
                db.execute("ALTER TABLE profiles RENAME TO profiles_v1")
                db.execute(SCHEMA)
                db.execute("""
                    INSERT INTO profiles (id, service, name, name_key, mode)
                    SELECT id, service, name, name_key,
                           CASE WHEN mode = 'web' AND service IN ('claude', 'chatgpt') THEN 'chat' ELSE mode END
                    FROM profiles_v1
                """)
                db.execute("DROP TABLE profiles_v1")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_duo_profile ON profiles(legacy_duo) WHERE legacy_duo = 1")
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.database, timeout=20)) as db, db:
            yield db

    def profiles(self):
        with self.connection() as db:
            rows = db.execute(f"SELECT {COLUMNS} FROM profiles ORDER BY service, name_key, mode").fetchall()
        return [Profile(*row) for row in rows]

    def profile(self, identifier):
        with self.connection() as db:
            row = db.execute(f"SELECT {COLUMNS} FROM profiles WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("This profile has been deleted.")
        return Profile(*row)

    def save(self, service, name, mode, *, executable="", workdir="", previous=None, legacy_duo=False):
        name = name.strip()
        if not name or len(name) > 48 or not name.isprintable():
            raise ValueError("Enter a name between 1 and 48 characters.")
        if mode not in TARGETS.get(service, {}):
            raise ValueError("Unknown product or client.")
        if previous and (service, mode, legacy_duo) != (previous.service, previous.mode, previous.legacy_duo):
            raise ValueError("Create a new profile to use a different client.")
        if legacy_duo and (sys.platform != "win32" or (service, mode) != ("claude", "desktop")
                           or not duo_directory().is_dir()):
            raise ValueError("The existing Claude Desktop session folder is unavailable.")
        for value, label in ((executable, "the executable"), (workdir, "the working directory")):
            if value and not Path(value).expanduser().is_absolute():
                raise ValueError(f"Use an absolute path for {label}.")
        identifier = previous.id if previous else uuid4().hex
        try:
            with self.connection() as db:
                if previous:
                    updated = db.execute("UPDATE profiles SET name = ?, name_key = ?, executable = ?, workdir = ? "
                                         "WHERE id = ?", (name, name.casefold(), executable, workdir, identifier))
                    if not updated.rowcount:
                        raise ValueError("This profile has been deleted.")
                else:
                    db.execute("INSERT INTO profiles (id, service, name, name_key, mode, executable, workdir, legacy_duo) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (identifier, service, name, name.casefold(), mode, executable, workdir, legacy_duo))
        except sqlite3.IntegrityError as error:
            message = "The Claude Desktop session is already linked." if "profiles.legacy_duo" in str(error) else (
                "A profile with this name already exists for this client.")
            raise ValueError(message) from error
        return identifier

    def require_profile(self, db, profile):
        if db.execute("SELECT 1 FROM profiles WHERE id = ?", (profile.id,)).fetchone() is None:
            raise ValueError("This profile has been deleted.")

    def directory(self, profile):
        if not re.fullmatch(r"[a-f0-9]{32}", profile.id):
            raise ValueError("Invalid profile ID.")
        return self.root / "sessions" / profile.id

    def lock(self, profile):
        folder = self.directory(profile)
        return profile_lock(self.root / "locks" / f"{folder.name}.lock")

    def delete(self, profile):
        folder = self.directory(profile)
        with self.lock(profile), self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_profile(db, profile)
            if folder.exists():
                if TARGETS[profile.service][profile.mode].kind != "cli":
                    try:
                        running = process_arguments()
                    except (OSError, subprocess.SubprocessError) as error:
                        raise OSError("Could not check for open windows. Try again.") from error
                    if uses_profile_directory(running, folder):
                        raise OSError("Close all windows for this profile, then try again.")
                try:
                    shutil.rmtree(folder)
                except OSError as error:
                    raise OSError("Could not delete the local data. Close the client and try again.") from error
            db.execute("DELETE FROM profiles WHERE id = ?", (profile.id,))

    def browser(self):
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'browser'").fetchone()
        return Path(row[0]) if row else None

    def save_browser(self, path):
        with self.connection() as db:
            db.execute("INSERT INTO settings VALUES ('browser', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                       (str(path),))

    def clear_browser(self):
        with self.connection() as db:
            db.execute("DELETE FROM settings WHERE key = 'browser'")

    def setting(self, key, default=""):
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def save_setting(self, key, value):
        with self.connection() as db:
            db.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                       (key, value))
