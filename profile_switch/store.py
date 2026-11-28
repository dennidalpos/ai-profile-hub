"""Persist profile metadata."""

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
from .platform_tools import private_directory, process_arguments, profile_lock, uses_profile_directory

SCHEMA_VERSION = 3
COLUMNS = "id, service, name, mode, executable, workdir"
SCHEMA = """
CREATE TABLE profiles (
    id TEXT PRIMARY KEY, service TEXT NOT NULL, name TEXT NOT NULL,
    name_key TEXT NOT NULL, mode TEXT NOT NULL, executable TEXT NOT NULL DEFAULT '',
    workdir TEXT NOT NULL DEFAULT '',
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


def _data_folder(name):
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / name["darwin"]
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / name["win32"]
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", ""))
    return (xdg_data if xdg_data.is_absolute() else home / ".local" / "share") / name["linux"]


def current_data_root():
    return _data_folder({"darwin": "AI Profile Hub", "win32": "AIProfileHub", "linux": "ai-profile-hub"})


def legacy_data_root():
    """Folder used before the product was named AI Profile Hub."""
    return _data_folder({"darwin": "AI Profile Switch", "win32": "AIProfileSwitch", "linux": "ai-profile-switch"})


def data_root():
    """The data folder in use: the current one, or the legacy one until migration moves it (never both)."""
    current, legacy = current_data_root(), legacy_data_root()
    return legacy if not current.exists() and legacy.is_dir() else current


class Store:
    def __init__(self, root):
        self.root = root
        private_directory(root)
        self.database = root / "profiles.sqlite3"
        self.backup_before_upgrade()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(profiles)")}
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if not columns:
                db.execute(SCHEMA)
            elif version < SCHEMA_VERSION:
                self.upgrade(db, columns)
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.recover_deletions()

    def backup_before_upgrade(self):
        """Keep a copy of an older profile database before its table is rebuilt; never overwrites a copy."""
        if not self.database.is_file():
            return
        with closing(sqlite3.connect(self.database, timeout=20)) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            has_table = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'profiles'").fetchone()
        copy = self.database.with_name(f"{self.database.name}.v{version}.bak")
        if has_table and version < SCHEMA_VERSION and not copy.exists():
            shutil.copy2(self.database, copy)

    def upgrade(self, db, columns):
        """Rebuild the table in the current layout; an older schema may carry an obsolete extra column."""
        has_duo_column = "legacy_duo" in columns
        db.execute("ALTER TABLE profiles RENAME TO profiles_old")
        db.execute("DROP INDEX IF EXISTS one_duo_profile")
        db.execute(SCHEMA)
        db.execute("""
            INSERT INTO profiles (id, service, name, name_key, mode, executable, workdir)
            SELECT id, service, name, name_key,
                   CASE WHEN mode = 'web' AND service IN ('claude', 'chatgpt') THEN 'chat' ELSE mode END,
                   %s
            FROM profiles_old
        """ % ("executable, workdir" if has_duo_column else "'', ''"))
        db.execute("DROP TABLE profiles_old")

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

    def save(self, service, name, mode, *, executable="", workdir="", previous=None):
        name = name.strip()
        if not name or len(name) > 48 or not name.isprintable():
            raise ValueError("Enter a name between 1 and 48 characters.")
        if mode not in TARGETS.get(service, {}):
            raise ValueError("Unknown product or client.")
        if previous and (service, mode) != (previous.service, previous.mode):
            raise ValueError("Create a new profile to use a different client.")
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
                    db.execute("INSERT INTO profiles (id, service, name, name_key, mode, executable, workdir) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (identifier, service, name, name.casefold(), mode, executable, workdir))
        except sqlite3.IntegrityError as error:
            raise ValueError("A profile with this name already exists for this client.") from error
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

    def tombstone(self, folder):
        return folder.with_name(folder.name + ".deleting")

    def delete(self, profile):
        """Remove a profile so a failure at any step leaves it either intact or finishable.

        The session folder is renamed aside first, then the record is deleted. A failure before the commit
        restores the folder; a failure after it leaves only a hidden folder that recover_deletions() removes.
        """
        folder = self.directory(profile)
        pending = self.tombstone(folder)
        with self.lock(profile):
            moved = False
            try:
                with self.connection() as db:
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
                            if pending.exists():
                                shutil.rmtree(pending)
                            folder.rename(pending)
                        except OSError as error:
                            raise OSError("Could not delete the local data. Close the client and try again.") from error
                        moved = True
                    db.execute("DELETE FROM profiles WHERE id = ?", (profile.id,))
            except BaseException:
                if moved and pending.exists() and not folder.exists():
                    try:
                        pending.rename(folder)
                    except OSError:
                        pass
                raise
            shutil.rmtree(pending, ignore_errors=True)

    def recover_deletions(self):
        """Finish or undo deletions that were interrupted; best effort and safe to repeat."""
        sessions = self.root / "sessions"
        if not sessions.is_dir():
            return
        known = {profile.id for profile in self.profiles()}
        for pending in sessions.glob("*.deleting"):
            identifier = pending.name.removesuffix(".deleting")
            if not re.fullmatch(r"[a-f0-9]{32}", identifier):
                continue
            try:
                with profile_lock(self.root / "locks" / f"{identifier}.lock"):
                    if identifier in known:
                        if not pending.with_name(identifier).exists():
                            pending.rename(pending.with_name(identifier))
                    else:
                        shutil.rmtree(pending, ignore_errors=True)
            except OSError:
                continue

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
