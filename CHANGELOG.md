# Changelog

## Unreleased

### Added
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
- Imported Codex sessions that could not be deleted and appeared in clone profiles.
