"""UI-independent application operations and short-lived client discovery."""

from dataclasses import dataclass
import shutil
import sys
from threading import Lock
from time import monotonic

from .app import ERRORS
from .catalog import LINKED_CLAUDE_PROFILE_NAME, TARGETS
from .launch import browser_path, ensure_only_desktop_profile, find_binary, open_profile, resolve_workdir
from .platform_tools import ProfileDirectoryAccessError, process_arguments, uses_profile_directory
from .store import duo_directory
from .transfer import EXPORT, categories, copy_session, restore, transfer


@dataclass(frozen=True)
class Availability:
    available: bool
    message: str
    path: str = ""
    recovery: str = "Edit the profile paths or refresh detection."


@dataclass(frozen=True)
class OperationResult:
    profile_id: str
    name: str
    succeeded: bool
    message: str
    recovery: str = ""


class ProfileService:
    def __init__(self, store):
        self.store = store
        self.cache = {}
        self.cache_lock = Lock()
        self.cache_generation = 0

    def invalidate(self):
        with self.cache_lock:
            self.cache.clear()
            self.cache_generation += 1

    def inspect(self, profile):
        key = (profile.service, profile.mode, profile.executable, profile.workdir)
        with self.cache_lock:
            cached = self.cache.get(key)
            generation = self.cache_generation
        if cached and monotonic() - cached[0] < 30:
            return cached[1]
        target = TARGETS[profile.service][profile.mode]
        try:
            path = browser_path(self.store) if target.kind == "web" else find_binary(profile)
            if target.kind != "web":
                resolve_workdir(profile.workdir)
            result = Availability(True, "Client available", str(path))
        except ERRORS as error:
            result = Availability(False, str(error))
        with self.cache_lock:
            if generation == self.cache_generation:
                self.cache[key] = monotonic(), result
        return result

    def launch(self, profiles, login=False):
        results = []
        for profile in profiles:
            try:
                open_profile(self.store, profile, login)
                message = "Sign-in requested." if login else "Launch requested."
                if login and sys.platform == "win32" and (profile.service, profile.mode) == ("claude", "desktop"):
                    message += (" In this Claude Desktop window, choose Continue with email. "
                                "Open the email link on another device and enter the code in this window. "
                                "Continue with Google can open the default Claude window.")
                elif TARGETS[profile.service][profile.mode].kind == "desktop":
                    message += " Verify the account in the client."
                results.append(OperationResult(profile.id, profile.name, True, message))
            except ProfileDirectoryAccessError as error:
                results.append(OperationResult(profile.id, profile.name, False, str(error),
                                               "Restore your Windows user's access to the existing profile folder, then retry. See Windows profile folder permissions in the README."))
            except ERRORS as error:
                self.invalidate()
                results.append(OperationResult(profile.id, profile.name, False, str(error),
                                               "Check the profile paths and client installation, then retry. For desktop sign-in, quit other client instances."))
        return results

    def import_duo(self, name=LINKED_CLAUDE_PROFILE_NAME):
        """Copy the old Claude Desktop Duo session into a new profile; the original folder is left untouched."""
        source = duo_directory()
        if sys.platform != "win32" or not source.is_dir():
            raise OSError("The existing Claude Desktop session folder is unavailable.")
        if uses_profile_directory(process_arguments(), source):
            raise OSError("Close the old Claude Desktop Duo window before importing its session.")
        identifier = self.store.save("claude", name, "desktop")
        try:
            copy_session(source, self.store.directory(self.store.profile(identifier)) / "claude-desktop")
        except BaseException:
            shutil.rmtree(self.store.directory(self.store.profile(identifier)), ignore_errors=True)
            self.store.delete(self.store.profile(identifier))
            raise
        self.store.save_setting("duo_imported", "1")
        self.invalidate()
        return identifier

    def transfer_categories(self, profile, direction):
        return [c for c in categories(profile, self.store.directory(profile)) if c.exists(direction)]

    def transfer(self, profile, keys, direction):
        """Copy the chosen categories between the original client configuration and this profile."""
        if direction == EXPORT and TARGETS[profile.service][profile.mode].kind == "desktop":
            ensure_only_desktop_profile(profile, find_binary(profile))
        selected = [c for c in self.transfer_categories(profile, direction) if c.key in keys]
        with self.store.lock(profile):
            return transfer(selected, direction, self.store.root / "diagnostics" / "backups")

    def restore_transfer(self, backup):
        return restore(backup)
