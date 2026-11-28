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

import base64
import binascii
from dataclasses import dataclass
import json
import re
import sys

from . import __version__

# Raw Ed25519 public key (32 bytes, base64) of the release signer; the private key is kept outside the repository.
# With an empty key every manifest is refused. `scripts/sign_manifest.py keygen` creates a pair.
UPDATE_PUBLIC_KEY = "v5J/dQbjIBklUtBpV41JymwWV1PrdQrbJiXz+lAxfOU="
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


def verify_signature(text, signature, public_key=None):
    """Raise ValueError unless `signature` (base64, Ed25519) matches the exact bytes of the manifest text."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    public_key = UPDATE_PUBLIC_KEY if public_key is None else public_key
    if not public_key:
        raise ValueError("No update signing key is configured, so the manifest cannot be trusted.")
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True))
        key.verify(base64.b64decode(signature, validate=True), text.encode("utf-8"))
    except (InvalidSignature, ValueError, binascii.Error) as error:
        raise ValueError("The release manifest signature is not valid.") from error


def load_manifest(text, signature, public_key=None):
    """Verify the signature over the manifest text first, then parse it. Use this for any downloaded manifest."""
    verify_signature(text, signature, public_key)
    return parse_manifest(text)


def parse_manifest(text):
    """Parse a manifest without checking who produced it; downloaded manifests go through load_manifest."""
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
