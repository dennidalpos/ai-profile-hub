"""Move the data folder of an older release to its current name."""

import sqlite3
import subprocess

from .platform_tools import process_arguments
from .store import current_data_root, legacy_data_root
from .transfer import rebase_threads


def migrate_data_root():
    """Rename the legacy data folder; returns "migrated", "deferred" (kept as is) or None when nothing applies.

    The rename is skipped, not forced, while any process mentions the folder (a running client) or the
    rename fails; the legacy folder then stays in use and the next start tries again.
    """
    current, legacy = current_data_root(), legacy_data_root()
    if current.exists() or not legacy.is_dir():
        return None
    try:
        if str(legacy).casefold() in process_arguments().casefold():
            return "deferred"
        legacy.rename(current)
    except (OSError, subprocess.SubprocessError):
        return "deferred"
    # Codex databases hold absolute paths to their rollout files; point them at the new location.
    for database in (current / "sessions").glob("*/codex/state_*.sqlite"):
        try:
            rebase_threads(database, database.parent, remove=False)
        except (OSError, sqlite3.Error):
            continue
    return "migrated"
