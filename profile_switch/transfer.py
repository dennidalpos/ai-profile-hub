"""Copy settings, MCP servers and history between a profile and the client's original configuration.

Both directions are additive: existing files and keys are never overwritten, credentials are never
copied, and every pre-existing file that gets modified is backed up first so it can be restored.
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tomllib

from .catalog import TARGETS
from .platform_tools import private_directory

IMPORT, EXPORT = "import", "export"
DENIED_NAMES = {
    ".credentials.json", "auth.json", "credentials.json", "oauth_creds.json", "google_accounts.json",
    "installation_id", "cap_sid", "ant-did", "mcp-needs-auth-cache.json", ".update.lock", ".last-cleanup",
}
DATABASES = {".sqlite", ".sqlite3", ".db"}
# Settings that would re-introduce credentials or force another login into an isolated profile.
SETTINGS_SKIPPED = {"env", "apiKeyHelper", "awsAuthRefresh", "awsCredentialExport", "forceLoginMethod",
                    "forceLoginOrgUUID"}
PROJECT_KEYS = ("mcpServers", "enabledMcpjsonServers", "disabledMcpjsonServers", "hasTrustDialogAccepted")
ATOMIC_KEYS = {"mcpServers"}
TOML_NESTED = {"mcp_servers", "projects", "profiles", "model_providers"}
TOML_SKIPPED = {"cli_auth_credentials_store"}
SECRET_KEY = re.compile(r"token|secret|api_key|password", re.IGNORECASE)


@dataclass(frozen=True)
class Item:
    native: Path
    profile: Path
    kind: str = "tree"          # tree | json | toml
    keys: tuple = ()            # json: only these top-level keys (empty means every key except skipped ones)


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    items: tuple
    sensitive: bool = False

    def exists(self, direction):
        return any((item.native if direction == IMPORT else item.profile).exists() for item in self.items)


@dataclass
class Report:
    added: list = field(default_factory=list)
    merged: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    backup: Path | None = None
    files: int = 0
    size: int = 0
    progress: object = None
    cancel: object = None
    cancelled: bool = False
    removed: int = 0

    def advance(self, size):
        self.files += 1
        self.size += size
        if self.progress:
            self.progress(self.files, self.size)

    def stopped(self):
        if self.cancel is not None and self.cancel.is_set():
            self.cancelled = True
        return self.cancelled

    def summary(self):
        text = (f"{len(self.added)} added, {len(self.merged)} merged, {len(self.skipped)} already present, "
                f"{len(self.conflicts)} conflicts kept, {len(self.errors)} errors.")
        if self.removed:
            text += f" {self.removed} history rows without a session file were removed (see the backup)."
        if self.cancelled:
            text += " Cancelled: files already copied were kept and are covered by the backup."
        return text + (f" Backup: {self.backup}" if self.backup else "")


def denied(name):
    lowered = name.lower()
    return (lowered in DENIED_NAMES or lowered.endswith((".lock", ".tmp", "-wal", "-shm", ".bak"))
            or ".tmp-" in lowered or lowered.startswith((".sandbox", ".codex-provisioning", "..codex")))


def system_paths(home=None):
    home = Path(home) if home else Path.home()
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        appdata = home / "Library" / "Application Support"
    else:
        appdata = home / ".config"
    return home, appdata


def native_roots(home, explicit):
    """Original config folders; honours the clients' own environment overrides unless a home is given."""
    def env(name):
        value = os.environ.get(name, "").strip()
        return Path(value).expanduser() if value and not explicit else None
    claude = env("CLAUDE_CONFIG_DIR")
    gemini = env("GEMINI_CLI_HOME")
    return {
        "claude": claude or home / ".claude",
        "claude_json": (claude / ".claude.json") if claude else home / ".claude.json",
        "codex": env("CODEX_HOME") or home / ".codex",
        "gemini": (gemini / ".gemini") if gemini else home / ".gemini",
    }


CODEX_DATABASES = ("state_*.sqlite", "thread_history_*.sqlite", "memories*.sqlite", "goals_*.sqlite",
                   "queue_*.sqlite")


def codex_databases(*folders):
    """Codex bumps its database file numbers, so names are discovered instead of pinned."""
    names = {file.name for folder in folders if folder.is_dir() for pattern in CODEX_DATABASES
             for file in folder.glob(pattern)}
    return tuple(sorted(names))


def claude_desktop_root(home, appdata):
    candidates = [appdata / "Claude"]
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        candidates += sorted(local.glob("Packages/Claude_*/LocalCache/Roaming/Claude"))
    return next((path for path in candidates if (path / "claude_desktop_config.json").is_file()), candidates[0])


def categories(profile, folder, home=None):
    """Transferable categories for a profile; web profiles hold no local configuration."""
    explicit = home is not None
    home, appdata = system_paths(home)
    roots = native_roots(home, explicit)
    folder = Path(folder)
    result = []
    if TARGETS[profile.service][profile.mode].kind == "web":
        return result
    if profile.service == "claude":
        native, config = roots["claude"], folder / "claude-code"
        result += [
            Category("mcp", "MCP servers (Claude Code, user and per-project)",
                     (Item(roots["claude_json"], config / ".claude.json", "json", ("mcpServers", "projects")),), True),
            Category("settings", "Settings and CLAUDE.md",
                     (Item(native / "settings.json", config / "settings.json", "json"),
                      Item(native / "CLAUDE.md", config / "CLAUDE.md"))),
            Category("extensions", "Skills, agents, commands and plugins",
                     tuple(Item(native / name, config / name) for name in ("skills", "agents", "commands", "plugins"))),
            Category("history", "Chat history, plans and file history",
                     tuple(Item(native / name, config / name) for name in (
                         "projects", "history.jsonl", "file-history", "plans", "sessions", "session-env",
                         "shell-snapshots", "todos"))),
        ]
        if profile.mode == "desktop":
            root, data = claude_desktop_root(home, appdata), folder / "claude-desktop"
            result += [
                Category("desktop-mcp", "MCP servers (Claude Desktop)",
                         (Item(root / "claude_desktop_config.json", data / "claude_desktop_config.json", "json",
                               ("mcpServers",)),), True),
                Category("desktop-history", "Claude Desktop sessions",
                         tuple(Item(root / name, data / name) for name in
                               ("claude-code-sessions", "local-agent-mode-sessions"))),
            ]
    elif profile.service == "chatgpt":
        native, config = roots["codex"], folder / "codex"
        result += [
            Category("mcp", "MCP servers and settings (config.toml)",
                     (Item(native / "config.toml", config / "config.toml", "toml"),), True),
            Category("instructions", "AGENTS.md, skills, prompts and plans",
                     (Item(native / "AGENTS.md", config / "AGENTS.md"),) + tuple(
                         Item(native / name, config / name) for name in ("skills", "prompts", "plans", "automations"))),
            Category("history", "Chat history and memories",
                     (Item(native / "session_index.jsonl", config / "session_index.jsonl", "index"),)
                     + tuple(Item(native / name, config / name) for name in (
                         "sessions", "archived_sessions", "memories", "memories_v2", "attachments", "worktrees")
                         + codex_databases(native, config))),
        ]
    elif profile.service == "gemini":
        native, config = roots["gemini"], folder / "google-home" / ".gemini"
        result += [
            Category("mcp", "MCP servers and settings (Gemini CLI, Antigravity)",
                     (Item(native / "settings.json", config / "settings.json", "json"),
                      Item(native / "antigravity" / "mcp_config.json", config / "antigravity" / "mcp_config.json",
                           "json")), True),
            Category("instructions", "GEMINI.md and project list",
                     (Item(native / "GEMINI.md", config / "GEMINI.md"),
                      Item(native / "projects.json", config / "projects.json"))),
            Category("history", "Conversations, knowledge and history",
                     tuple(Item(native / name, config / name) for name in (
                         "history", "tmp", "antigravity/conversations", "antigravity/brain", "antigravity/knowledge",
                         "antigravity/annotations", "antigravity/conversation_summaries.db"))),
        ]
        if profile.mode in ("ide", "desktop"):
            user, data = appdata / "Antigravity" / "User", folder / "desktop" / "User"
            result.append(Category("ide", "Antigravity editor settings, keybindings and snippets",
                                   tuple(Item(user / name, data / name) for name in
                                         ("settings.json", "keybindings.json", "snippets"))))
    return result


# ---------------------------------------------------------------- backup


class Backup:
    def __init__(self, root):
        self.directory = Path(root) / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.entries = []

    def before_write(self, path):
        path = Path(path)
        if path.is_file():
            target = self.directory / f"{len(self.entries)}.bak"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            self.entries.append({"path": str(path), "backup": target.name})
        else:
            self.entries.append({"path": str(path), "backup": None})

    def save(self):
        if self.entries:
            for entry in self.entries:
                entry["after"] = fingerprint(entry["path"])
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / "manifest.json").write_text(json.dumps(self.entries, indent=1), encoding="utf-8")
            return self.directory
        return None


def fingerprint(path):
    """Size and modification time of a file, or None when it does not exist."""
    try:
        info = Path(path).stat()
    except OSError:
        return None
    return [info.st_size, info.st_mtime_ns]


class Restored(int):
    """Number of files put back; `skipped` lists files left alone because they changed after the transfer."""

    skipped = ()


def restore(directory):
    """Undo a transfer: put back modified files and remove the ones it created.

    A file that was changed after the transfer finished is kept and reported in `skipped`,
    so later edits are never discarded. Every entry is validated before anything is touched.
    """
    directory = Path(directory)
    entries = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("The backup manifest is damaged.")
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                or not (entry.get("backup") is None or (isinstance(entry["backup"], str)
                                                         and Path(entry["backup"]).name == entry["backup"]
                                                         and (directory / entry["backup"]).is_file()))):
            raise ValueError("The backup manifest is damaged or a backup file is missing.")
    restored, skipped = 0, []
    # Judge every file before touching any, because one path can appear in several entries.
    changed = {entry["path"] for entry in entries
               if entry.get("after", "unknown") != "unknown" and fingerprint(entry["path"]) != entry["after"]}
    for entry in reversed(entries):
        path = Path(entry["path"])
        if entry["path"] in changed:
            if str(path) not in skipped:
                skipped.append(str(path))
            continue
        if entry["backup"]:
            shutil.copy2(directory / entry["backup"], path)
        else:
            path.unlink(missing_ok=True)
        restored += 1
    result = Restored(restored)
    result.skipped = tuple(skipped)
    return result


def write_atomic(path, text, backup):
    backup.before_write(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.transfer.tmp")
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


# ---------------------------------------------------------------- merging


def merge_mapping(source, target, conflicts, path="", depth=0):
    """Add keys missing from target; equal values are fine, different ones are reported and kept."""
    changed = False
    for key, value in source.items():
        label = f"{path}{key}"
        if key not in target:
            target[key] = value
            changed = True
        elif isinstance(value, dict) and isinstance(target[key], dict):
            merge = merge_atomic if key in ATOMIC_KEYS and depth == 0 else merge_mapping
            nested = (merge(value, target[key], conflicts, label + ".") if merge is merge_atomic
                      else merge(value, target[key], conflicts, label + ".", depth + 1))
            changed = nested or changed
        elif isinstance(value, list) and isinstance(target[key], list):
            for entry in value:
                if entry not in target[key]:
                    target[key].append(entry)
                    changed = True
        elif target[key] != value:
            conflicts.append(label)
    return changed


def merge_atomic(source, target, conflicts, path):
    changed = False
    for name, value in source.items():
        if name not in target:
            target[name] = value
            changed = True
        elif target[name] != value:
            conflicts.append(path + name)
    return changed


def merge_json(source, target, keys, conflicts):
    selected = {key: source[key] for key in (keys or source) if key in source and key not in SETTINGS_SKIPPED}
    changed = False
    for key, value in selected.items():
        if key == "projects" and isinstance(value, dict):
            projects = target.setdefault("projects", {})
            for project, data in value.items():
                if not isinstance(data, dict):
                    continue
                wanted = {name: data[name] for name in PROJECT_KEYS if name in data}
                if wanted:
                    current = projects.setdefault(project, {})
                    changed = merge_mapping(wanted, current, conflicts, f"projects.{project}.") or changed
        else:
            changed = merge_mapping({key: value}, target, conflicts) or changed
    return changed


def toml_sections(text):
    lines = text.splitlines()
    header = re.compile(r"^\s*\[\[?\s*([^\[\]]+?)\s*\]\]?\s*(?:#.*)?$")
    starts = [index for index, line in enumerate(lines) if header.match(line)]
    preamble = lines[:starts[0]] if starts else lines
    sections = []
    for number, start in enumerate(starts):
        end = starts[number + 1] if number + 1 < len(starts) else len(lines)
        sections.append((header.match(lines[start]).group(1), lines[start:end]))
    return preamble, sections, starts[0] if starts else len(lines)


def table_identity(name):
    parts = [part.strip().strip("\"'") for part in re.findall(r'"[^"]*"|\'[^\']*\'|[^.\s]+', name)]
    return tuple(parts[:2] if parts[0] in TOML_NESTED else parts[:1])


def merge_toml(source_text, target_text):
    """Append tables and top-level keys absent from the target, leaving its text untouched."""
    target = tomllib.loads(target_text) if target_text.strip() else {}
    tomllib.loads(source_text)
    preamble, sections, _ = toml_sections(source_text)
    statements, current = [], None
    for line in preamble:
        match = re.match(r"^([A-Za-z0-9_\-]+)\s*=", line)
        if match:
            current = [match.group(1), [line]]
            statements.append(current)
        elif current and line.strip() and not line.lstrip().startswith("#"):
            current[1].append(line)
    new_keys = [line for key, lines in statements
                if key not in target and key not in TOML_SKIPPED and not SECRET_KEY.search(key) for line in lines]
    new_tables = []
    for name, lines in sections:
        identity = table_identity(name)
        existing = target
        for part in identity:
            existing = existing.get(part, None) if isinstance(existing, dict) else None
        if existing is None:
            new_tables.append(lines)
    if not new_keys and not new_tables:
        return target_text, False
    boundary = toml_sections(target_text)[2]
    target_lines = target_text.splitlines()
    head = target_lines[:boundary] + new_keys
    tail = target_lines[boundary:]
    for lines in new_tables:
        tail += [""] + lines
    text = "\n".join(head + ([""] if tail and head and head[-1].strip() else []) + tail).rstrip("\n") + "\n"
    tomllib.loads(text)
    return text, True


# ---------------------------------------------------------------- copying


def copy_database(source, target):
    """Copy a database through a temporary file, so the target is never half written."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    reader = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        writer = sqlite3.connect(temporary)
        try:
            reader.backup(writer)
            if writer.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError(f"The copy of {source.name} failed its integrity check.")
        finally:
            writer.close()
        # The target may have been opened by its client since the caller checked it.
        if target.exists() and database_in_use(target):
            raise OSError("The database is in use. Close the client of this profile and import again.")
        for suffix in ("-wal", "-shm"):
            # Leftovers of the replaced database would be applied to the new file.
            target.with_name(target.name + suffix).unlink(missing_ok=True)
        os.replace(temporary, target)
    finally:
        reader.close()
        temporary.unlink(missing_ok=True)


def blank_database(path):
    """True for a database a client created at startup that holds no user data yet."""
    try:
        db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            names = [name for (name,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "AND name NOT LIKE '%migration%'")]
            counts = {name: db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}
        finally:
            db.close()
    except sqlite3.Error:
        return False
    return counts["threads"] == 0 if "threads" in counts else not any(counts.values())


def replaceable(source, target):
    """A client's empty startup database is replaced by the original's, because rows cannot be merged additively."""
    return (target.exists() and source.suffix.lower() in DATABASES and target.suffix.lower() in DATABASES
            and blank_database(target) and not blank_database(source))


def database_in_use(path):
    try:
        db = sqlite3.connect(path, timeout=0.3)
        try:
            db.execute("BEGIN EXCLUSIVE")
            db.rollback()
        finally:
            db.close()
    except sqlite3.OperationalError:
        return True
    return False


def copy_file(source, target, backup, report):
    if target.exists():
        if not replaceable(source, target):
            report.skipped.append(str(target))
            return
        if database_in_use(target):
            raise OSError("The database is in use. Close the client of this profile and import again.")
    backup.before_write(target)
    if source.suffix.lower() in DATABASES:
        copy_database(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    report.added.append(str(target))
    report.advance(target.stat().st_size)


def tree_files(source):
    """Yield (file, relative path) for every file copy_tree would consider."""
    if source.is_symlink() or not source.exists() or denied(source.name):
        return
    if source.is_file():
        yield source, Path()
        return
    for current, directories, files in os.walk(source):
        directories[:] = [name for name in directories if not denied(name) and not (Path(current) / name).is_symlink()]
        relative = Path(current).relative_to(source)
        for name in files:
            file = Path(current) / name
            if not denied(name) and not file.is_symlink():
                yield file, relative / name


def copy_tree(source, target, backup, report):
    for file, relative in tree_files(source):
        if report.stopped():
            return
        try:
            copy_file(file, target / relative, backup, report)
        except (OSError, sqlite3.Error) as error:
            report.errors.append(f"{file}: {error}")


def merge_index(source_text, target_text):
    """Append session index lines whose id is absent from the target; existing lines are untouched."""
    def identity(line):
        try:
            value = json.loads(line)
        except ValueError:
            return None
        return value.get("id") if isinstance(value, dict) else None

    lines = target_text.splitlines()
    known = {identity(line) for line in lines} - {None}
    added = [line for line in source_text.splitlines()
             if line.strip() and identity(line) is not None and identity(line) not in known]
    if not added:
        return target_text, False
    return "\n".join(lines + added) + "\n", True


ROLLOUT_FOLDERS = ("sessions", "archived_sessions")


def rollout_location(value, home):
    """Where a thread's rollout lives inside this Codex home, whatever absolute path the row was copied with."""
    text = str(value or "").replace("\\", "/")
    if text.startswith("//?/"):
        text = text[4:]
    parts = [part for part in text.split("/") if part]
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] in ROLLOUT_FOLDERS:
            return Path(home).joinpath(*parts[index:])
    return None


def rebase_threads(database, home, backup=None, remove=True):
    """Point every thread of a Codex state database at this home's rollout files; drop rows with no file.

    A copied database keeps the original's absolute paths, so Codex cannot delete, resume or archive the
    thread and the row stays visible as a ghost. Returns (rewritten, removed).
    """
    database, home = Path(database), Path(home)
    try:
        db = sqlite3.connect(database, timeout=2)
    except sqlite3.Error:
        return 0, 0
    rewritten = removed = 0
    try:
        columns = {row[1] for row in db.execute("PRAGMA table_info(threads)")}
        if "rollout_path" not in columns:
            return 0, 0
        rows = db.execute("SELECT id, rollout_path FROM threads").fetchall()
        updates, deletes = [], []
        for identifier, current in rows:
            wanted = rollout_location(current, home)
            if wanted is None or not wanted.is_file():
                if remove:
                    deletes.append((identifier,))
            elif str(wanted) != str(current):
                updates.append((str(wanted), identifier))
        if (updates or deletes) and backup is not None:
            backup.before_write(database)
        db.executemany("UPDATE threads SET rollout_path = ? WHERE id = ?", updates)
        db.executemany("DELETE FROM threads WHERE id = ?", deletes)
        db.commit()
        rewritten, removed = len(updates), len(deletes)
    except sqlite3.Error:
        db.rollback()
        return 0, 0
    finally:
        db.close()
    return rewritten, removed


def repair_codex_home(home, backup_root):
    """Fix ghost and foreign-path threads in an existing Codex home; returns (rewritten, removed, backup)."""
    home, backup = Path(home), Backup(backup_root)
    rewritten = removed = 0
    for database in sorted(home.glob("state_*.sqlite")):
        if database_in_use(database):
            raise OSError("The database is in use. Close Codex for this profile and repair again.")
        fixed, dropped = rebase_threads(database, home, backup)
        rewritten, removed = rewritten + fixed, removed + dropped
    return rewritten, removed, backup.save()


def merge_item(item, source, target, backup, report):
    text = source.read_text(encoding="utf-8-sig")
    if item.kind == "toml":
        existing = target.read_text(encoding="utf-8-sig") if target.is_file() else ""
        merged, changed = merge_toml(text, existing)
        if changed:
            write_atomic(target, merged, backup)
            report.merged.append(str(target))
        return
    if item.kind == "index":
        merged, changed = merge_index(text, target.read_text(encoding="utf-8-sig") if target.is_file() else "")
        if changed:
            write_atomic(target, merged, backup)
            report.merged.append(str(target))
        return
    data = json.loads(text)
    current = json.loads(target.read_text(encoding="utf-8-sig")) if target.is_file() else {}
    conflicts = []
    if not isinstance(data, dict) or not isinstance(current, dict):
        raise ValueError("Unexpected JSON structure.")
    if merge_json(data, current, item.keys, conflicts):
        write_atomic(target, json.dumps(current, indent=2, ensure_ascii=False) + "\n", backup)
        report.merged.append(str(target))
    report.conflicts += [f"{target}: {name}" for name in conflicts]


def rebase_copied_databases(report, backup):
    """Codex state databases copied in this run must reference the rollout files of their new home.

    Rows without a rollout file are dropped only when the whole copy finished cleanly; after a
    cancellation or an error the missing file may simply not be copied yet, so the rows stay.
    """
    complete = not report.cancelled and not report.errors
    for added in report.added:
        path = Path(added)
        if path.suffix.lower() == ".sqlite" and path.name.startswith("state_"):
            try:
                _, dropped = rebase_threads(path, path.parent, backup, remove=complete)
                report.removed += dropped
            except (OSError, sqlite3.Error) as error:
                report.errors.append(f"{path}: {error}")


def transfer(selected, direction, backup_root, progress=None, cancel=None):
    """Apply the selected categories; returns a Report. Never raises for a single bad item.

    progress(files, bytes) is called after every file; setting the cancel event stops between files.
    """
    report, backup = Report(progress=progress, cancel=cancel), Backup(backup_root)
    for category in selected:
        for item in category.items:
            if report.stopped():
                break
            source, target = (item.native, item.profile) if direction == IMPORT else (item.profile, item.native)
            if not source.exists():
                continue
            try:
                if direction == IMPORT:
                    private_directory(item.profile.parent)
                if item.kind == "tree":
                    copy_tree(source, target, backup, report)
                else:
                    merge_item(item, source, target, backup, report)
                    report.advance(source.stat().st_size)
            except (OSError, ValueError, sqlite3.Error, tomllib.TOMLDecodeError) as error:
                report.errors.append(f"{source}: {error}")
    rebase_copied_databases(report, backup)
    report.backup = backup.save()
    return report


# ---------------------------------------------------------------- measuring before a transfer

SAFETY_FACTOR = 1.1
SAFETY_MARGIN = 16 * 1024 * 1024


class TransferCancelled(Exception):
    pass


@dataclass
class Estimate:
    key: str
    label: str
    files: int = 0
    size: int = 0


@dataclass
class Volume:
    anchor: Path
    free: int
    required: int

    @property
    def enough(self):
        return self.free >= self.required


@dataclass
class Plan:
    estimates: list
    volumes: list

    @property
    def files(self):
        return sum(e.files for e in self.estimates)

    @property
    def size(self):
        return sum(e.size for e in self.estimates)

    @property
    def enough(self):
        return all(volume.enough for volume in self.volumes)


def format_size(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def existing_parent(path):
    path = Path(path)
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def device_of(path):
    try:
        return path.stat().st_dev
    except OSError:
        return None


def measure(selected, direction, backup_root, progress=None, cancel=None):
    """Count the files and bytes a transfer would copy (what is not already at the destination), per category."""
    estimates, needed = [], {}
    files = size = 0
    for category in selected:
        estimate = Estimate(category.key, category.label)
        for item in category.items:
            source, target = (item.native, item.profile) if direction == IMPORT else (item.profile, item.native)
            if not source.exists():
                continue
            if item.kind == "tree":
                found = ((file, target / relative) for file, relative in tree_files(source))
            else:
                found = [(source, target)]
            for file, destination in found:
                if cancel is not None and cancel.is_set():
                    raise TransferCancelled()
                if item.kind == "tree" and destination.exists() and not replaceable(file, destination):
                    continue
                try:
                    length = file.stat().st_size
                except OSError:
                    continue
                estimate.files += 1
                estimate.size += length
                files, size = files + 1, size + length
                anchor = existing_parent(destination)
                needed.setdefault(device_of(anchor), [anchor, 0])[1] += length
                if progress and files % 50 == 0:
                    progress(files, size)
        estimates.append(estimate)
    if progress:
        progress(files, size)
    if needed:
        anchor = existing_parent(backup_root)
        needed.setdefault(device_of(anchor), [anchor, 0])
    volumes = []
    for anchor, length in needed.values():
        try:
            free = shutil.disk_usage(anchor).free
        except OSError:
            free = 0
        volumes.append(Volume(anchor, free, int(length * SAFETY_FACTOR) + SAFETY_MARGIN))
    return Plan(estimates, volumes)
