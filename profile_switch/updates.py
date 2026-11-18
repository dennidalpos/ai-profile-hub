"""Release manifest handling for future desktop-client updates (Windows, macOS, Linux).

Nothing here downloads or installs anything. The Hub stays silent until a manifest URL is configured; the
helpers below parse a manifest, pick the asset for this platform and compare versions, so that a later change
only has to add the transport and the per-OS replacement step.

Manifest format (JSON):
    {"version": "1.2.0", "notes": "...", "assets": {
        "windows": {"url": "https://...", "sha256": "..."},
        "macos":   {"url": "https://...", "sha256": "..."},
        "linux":   {"url": "https://...", "sha256": "..."}}}
"""

from dataclasses import dataclass
import json
import re
import sys

from . import __version__

PLATFORMS = {"win32": "windows", "darwin": "macos", "linux": "linux"}
SHA256 = re.compile(r"[0-9a-fA-F]{64}")


@dataclass(frozen=True)
class Asset:
    url: str
    sha256: str


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    assets: dict

    def asset(self, platform=None):
        return self.assets.get(PLATFORMS.get(platform or sys.platform, ""))


def parse_version(text):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", str(text).strip())
    if not match:
        raise ValueError(f"Invalid version: {text!r}")
    return tuple(int(part) for part in match.groups())


def parse_manifest(text):
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("The release manifest must be a JSON object.")
    parse_version(data.get("version", ""))
    assets = {}
    for name, entry in (data.get("assets") or {}).items():
        if name not in PLATFORMS.values() or not isinstance(entry, dict):
            continue
        url, digest = str(entry.get("url", "")), str(entry.get("sha256", ""))
        if not url.startswith("https://") or not SHA256.fullmatch(digest):
            raise ValueError(f"The {name} asset needs an https URL and a SHA-256 digest.")
        assets[name] = Asset(url, digest.lower())
    return Release(str(data["version"]), str(data.get("notes", "")), assets)


def update_available(release, current=__version__, platform=None):
    """True when the release is newer than the running version and has an asset for this platform."""
    return parse_version(release.version) > parse_version(current) and release.asset(platform) is not None
