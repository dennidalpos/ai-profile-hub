# Changelog

## 0.1.1 - 2026-11-19

### Added
- Signed release manifests: `updates.load_manifest` verifies a detached Ed25519 signature before parsing, and `scripts/sign_manifest.py` creates keys and signatures. Every manifest is refused until a public key is configured.
- Hub renames its data folder to `AIProfileHub` (`AI Profile Hub` on macOS, `ai-profile-hub` on Linux) when the window starts and nothing uses the old folder; Codex session paths are re-pointed. Until then the old folder stays in use, and nothing is lost if the rename is deferred.
- A copy of the profile database (`profiles.sqlite3.vN.bak`) before a schema upgrade.
- **Running** status pill in the profile list and details, refreshed at startup, every 10 seconds while the window is visible and after each launch.
- Desktop shortcuts for Hub and for a single profile (`--launch ID` starts a profile without opening the window).
- **Repair imported sessions** for Codex profiles.
- `profile_switch.__version__` and `profile_switch.updates`: release-manifest parsing and version comparison for future desktop updates on Windows, macOS and Linux. Nothing is downloaded or installed yet; see `docs/updates.md`.
- `release-manifest.json` (version, commit, platform, digest of `SHA256SUMS`) written by `scripts/release_evidence.py` for each release-candidate package.

### Changed
- Codex history import re-points `threads.rollout_path` at the profile's own rollout files, drops rows with no file, merges `session_index.jsonl` by id and discovers database files by pattern (`state_*`, `thread_history_*`, `memories*`, `goals_*`, `queue_*`).
- Original client folders honour `CODEX_HOME`, `CLAUDE_CONFIG_DIR` and `GEMINI_CLI_HOME`; TOML with a byte-order mark is read; a malformed `config.toml` reports a clear error.
- Settings page uses section headings; the New profile form is narrower with the client hint above Advanced settings; Link handlers appear only on Windows.
- Text, controls, rail and rows scale with the system font (the 14 px design size is the minimum).
- Detail rows share one layout, Edit is an outlined button and Copy is underlined with a 24 px target.

### Fixed
- **Restore from backup** keeps any file changed after the transfer and lists it, and refuses a damaged backup before touching files.
- Importing history no longer removes Codex rows when the copy was cancelled or had errors; the report states how many rows were removed.
- Databases are copied through a temporary file, checked and swapped in only if the client has not opened the target meanwhile.
- A leftover environment journal is restored before a new temporary environment is written, so the original values are never lost.
- Closing a desktop client for sign-in no longer matches the terminal client (`claude`, `codex`, `agy`).
- Imported Codex sessions that could not be deleted and appeared in clone profiles.
