"""UI-independent application operations and short-lived client discovery."""

from dataclasses import dataclass
import sys
from threading import Lock
from time import monotonic

from .app import ERRORS
from .catalog import LINKED_CLAUDE_PROFILE_NAME, TARGETS
from .launch import browser_path, find_binary, open_profile, resolve_workdir
from .platform_tools import ProfileDirectoryAccessError
from .store import duo_directory


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
        key = (profile.service, profile.mode, profile.executable, profile.workdir, profile.legacy_duo)
        with self.cache_lock:
            cached = self.cache.get(key)
            generation = self.cache_generation
        if cached and monotonic() - cached[0] < 30:
            return cached[1]
        target = TARGETS[profile.service][profile.mode]
        try:
            if profile.legacy_duo and not duo_directory().is_dir():
                raise OSError("The linked Claude Desktop session folder is missing. Restore its original folder or remove this link.")
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

    def link_duo(self, name=LINKED_CLAUDE_PROFILE_NAME):
        existing = next((p for p in self.store.profiles() if p.legacy_duo), None)
        return existing.id if existing else self.store.save("claude", name, "desktop", legacy_duo=True)
