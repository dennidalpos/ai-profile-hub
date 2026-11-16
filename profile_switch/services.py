"""UI-independent application operations and short-lived client discovery."""

from dataclasses import dataclass
import sys
from threading import Lock
from time import monotonic

from .app import ERRORS
from .catalog import TARGETS
from .launch import ClientRunningError, browser_path, close_desktop_client, ensure_only_desktop_profile, find_binary, open_profile, resolve_workdir
from .platform_tools import ProfileDirectoryAccessError
from .transfer import EXPORT, categories, measure, restore, transfer


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
    processes: tuple = ()


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
            except ClientRunningError as error:
                results.append(OperationResult(profile.id, profile.name, False, str(error),
                                               "Close the listed processes to continue.", error.processes))
            except ERRORS as error:
                self.invalidate()
                results.append(OperationResult(profile.id, profile.name, False, str(error),
                                               "Check the profile paths and client installation, then retry. For desktop sign-in, quit other client instances."))
        return results

    def close_client(self, profile):
        """Force close the running desktop client of this profile's product."""
        return close_desktop_client(profile, find_binary(profile))

    def transfer_categories(self, profile, direction):
        return [c for c in categories(profile, self.store.directory(profile)) if c.exists(direction)]

    def selected_categories(self, profile, keys, direction):
        return [c for c in self.transfer_categories(profile, direction) if c.key in keys]

    def transfer_plan(self, profile, keys, direction, progress=None, cancel=None):
        """Measure what a transfer would copy and whether the destination disk has room for it."""
        return measure(self.selected_categories(profile, keys, direction), direction,
                       self.store.root / "diagnostics" / "backups", progress, cancel)

    def transfer(self, profile, keys, direction, progress=None, cancel=None):
        """Copy the chosen categories between the original client configuration and this profile."""
        if direction == EXPORT and TARGETS[profile.service][profile.mode].kind == "desktop":
            ensure_only_desktop_profile(profile, find_binary(profile))
        selected = self.selected_categories(profile, keys, direction)
        with self.store.lock(profile):
            return transfer(selected, direction, self.store.root / "diagnostics" / "backups", progress, cancel)

    def restore_transfer(self, backup):
        return restore(backup)
