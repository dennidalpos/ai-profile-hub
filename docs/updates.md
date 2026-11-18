# Desktop updates (preparation)

AI Profile Hub does not download or install updates yet. This page records what is in place and what a future update feature has to add, so that Windows, macOS and Linux can follow one design.

## What exists

- **One version source:** `__version__` in `profile_switch/__init__.py`. `scripts/build.py` prints it and `scripts/release_evidence.py` records it.
- **Release manifest format** (`profile_switch/updates.py`): JSON with `version`, optional `notes` and per-platform `assets` (`windows`, `macos`, `linux`), each with an `https` URL and a SHA-256 digest. `parse_manifest` rejects other schemes and bad digests; `update_available` is true only when the release is newer and has an asset for the running platform.
- **Evidence manifest:** the release-candidate workflow writes `release-manifest.json` next to `SHA256SUMS` for each operating system (version, commit, platform, digest of `SHA256SUMS`, and the single-file asset hash on Windows). It has no URL because nothing is published. Publishing turns it into the update manifest by adding the URL of each uploaded asset.
- **Nothing runs by default:** no network request is made and no update prompt appears.

## What a future feature must add

1. **Transport:** a configured manifest URL, fetched on a user action or a slow schedule, verified over HTTPS, with the asset digest checked before use.
2. **Replacement step per system** (all keep the previous version until the new one starts):
   - **Windows:** a running EXE cannot overwrite itself. Download beside it, then a small helper waits for the process to exit and swaps the file (`os.replace`), restarting Hub. `scripts/build.py` already uses an atomic replace for the single-file EXE.
   - **macOS:** replace the whole `.app` bundle directory by renaming the old one aside and moving the new one in. Unsigned or un-notarized bundles are quarantined by Gatekeeper, so signing comes first.
   - **Linux:** replace the distribution directory the same way. Packages installed by a distribution package manager must be updated by that manager, not by Hub.
3. **Trust:** code signing (Windows Authenticode, macOS notarization) and, optionally, the provenance attestation the workflow already produces.
4. **Safety:** never update while a profile is being transferred or a client of a profile is launching; keep profile data untouched (it lives outside the package).

Signing, notarization and automatic updates remain unqualified.
