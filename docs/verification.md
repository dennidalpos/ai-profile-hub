# Unified desktop verification

## Observed on Windows

Verified on 2026-11-14 using Python 3.13.17 and 3.11.18, PySide6 / Qt 6.10.1 and Nuitka 2.8.9 (native package built with Python 3.13).

- 36 tests pass: previous backend behavior, database/session migration, client commands, linked Duo preservation, normalized deletion guards, inherited Gemini overrides, Qt interaction, error recovery and worker responsiveness.
- Filtering 1,000 synthetic profiles with a combined text/product filter took approximately 26 ms in the final local test (acceptance budget: 150 ms). This is a local measurement, not a cross-platform benchmark or comparison against the previous UI.
- A five-second synthetic operation left a 50 ms UI timer active and navigation available.
- A standalone Windows package passed `--help`, Qt startup/close, and `--session` against a harmless CLI shim with an isolated data root. The shim received the expected per-profile `CLAUDE_CONFIG_DIR`; the executable ran from outside the source tree.
- The app includes system/light/dark appearance, searchable/filterable profiles, incremental list updates, persistent recoverable errors, retry of failed batch entries and contextual details. The compact layout places details on a separate page.
- Real Qt screenshots use only synthetic profile content and fixtures. The two material review findings (empty-state composition and modal routine errors) were resolved; the follow-up review accepted those fixes within the reviewed Windows UI scope.

Local reports, native packages, screenshot matrices and synthetic databases are kept in ignored `dist/` directories. No production profile database was migrated during verification.

## Automated coverage and remaining qualification

The CI configuration runs tests on Python 3.11 / 3.13 for Windows, macOS and Linux, and native builds/package smoke tests on 3.13. Qt tests use the offscreen platform in CI. Local verification does not establish a remote CI result; inspect the workflow run for the exact published commit before qualifying the matrix.

Native macOS/Linux interactive operation and packaging have not been observed in this Windows session. Test their terminal behavior, Qt dialogs, theme changes, keyboard shortcuts and packaged startup on the actual systems before qualifying those distributions. All 36 tests also passed locally on Python 3.11.18 on Windows.

Real provider authentication and multi-account isolation remain unqualified. Tests substitute clients and credentials; they do not demonstrate that a provider accepts or respects the configured home/data directories. Use two test accounts, verify identity after sign-in and after restarting each profile, and record the client version and OS.

The inherited Gemini environment filter additionally removes `GOOGLE_CLOUD_ACCESS_TOKEN`, `GOOGLE_GENAI_USE_GCA`, `GOOGLE_GENAI_USE_VERTEXAI` and `GEMINI_CLI_USE_COMPUTE_ADC`. Parent environment variables and client-managed policy files are unchanged. A complete version-specific authentication inventory and live identity checks remain pending.

## Reproduce

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q --junitxml=dist/evidence/tests.xml
python tools/capture_ui.py
python build.py
python tools/smoke_package.py
```

Use the virtual environment's Python. `QT_SCALE_FACTOR` multiplies the screen's native scaling; each capture writes its actual device pixel ratio to `capture.json`. Adjust that multiplier to inspect 100%, 150% and 200% scaling. On Linux CI use `QT_QPA_PLATFORM=offscreen`; interactive desktop validation must also use the normal native platform plugin.

Each build retains a fresh staging directory and writes the executable path to `dist/latest-native.txt`. Build byte reproducibility, code signing, notarization, publication and automatic updates are not qualified or performed by this change.
