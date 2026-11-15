# Unified desktop verification

## Observed on Windows

On 2026-11-14, a clean checkout at `231554f` passed the README setup and build steps with Python 3.13.17, PySide6 6.10.1 and Nuitka 2.8.9. Source startup used `run.cmd --smoke-test` with a synthetic data directory. The test suite reported `36 passed in 9.44s`. The native build, package smoke test and capture command succeeded. The capture produced 11 PNGs at a device pixel ratio of 1.5.

- The subsequent working tree with the Google authentication and pytest changes reported `43 passed, 14 subtests passed in 8.82s` with pytest 9.0.3. The new tests cover gateway refusal and preservation of managed settings.
- Filtering 1,000 synthetic profiles with a combined text/product filter took approximately 26 ms in the final local test (acceptance budget: 150 ms). This is a local measurement, not a cross-platform benchmark or comparison against the previous UI.
- A five-second synthetic operation left a 50 ms UI timer active and navigation available.
- A standalone Windows package passed `--help`, Qt startup/close, and `--session` against a harmless CLI shim with an isolated data root. The shim received the expected per-profile `CLAUDE_CONFIG_DIR`; the executable ran from outside the source tree.
- Windows build `20261114T215041Z-22fb87` excluded the unused Qt PDF image plugin (`qpdf.dll`) and its library (`qt6pdf.dll`). The package inventory and Nuitka report both confirmed the exclusion, and the standalone smoke checks passed again.
- On 2026-11-15, a fresh Windows source snapshot of `5ea95fb` passed the README virtual environment setup, dependency installation and launcher smoke test with Python 3.13.17. Build `20261114T232248Z-abcadb` also passed the package smoke test and shipped the updated third-party notices without the Qt PDF binaries or their notices.
- The app includes system/light/dark appearance, searchable/filterable profiles, incremental list updates, persistent recoverable errors, retry of failed batch entries and contextual details. The compact layout places details on a separate page.
- Real Qt screenshots use only synthetic profile content and fixtures. The two material review findings (empty-state composition and modal routine errors) were resolved; the follow-up review accepted those fixes within the reviewed Windows UI scope.

Local reports, native packages, screenshot matrices and synthetic databases are kept in ignored `dist/` directories. No production profile database was migrated during verification.

## Automated coverage and remaining qualification

The CI configuration runs tests on Python 3.11 / 3.13 for Windows, macOS and Linux, and native builds/package smoke tests on 3.13. Qt tests use the offscreen platform in CI. Manual qualification run `43611594432` used workflow revision `231554f` to check out application source `341e1c7`: all six jobs passed 36 tests each, and all three native package smoke steps passed. Push run `43611594501` for `231554f` passed the same checks. These successful results were observed before the historical runs were removed; local summaries remain in ignored `dist/ci-verification/`. Subsequent authentication and pytest changes have local Windows verification; those earlier runs do not qualify the newer changes.

Native macOS/Linux interactive operation remains unqualified. CI verifies package compilation and offscreen startup, while terminal behavior, Qt dialogs, theme changes and keyboard shortcuts still require interactive checks on the actual systems. The baseline 36 tests also passed locally on Python 3.11.18 on Windows.

Real provider authentication and multi-account isolation remain unqualified. Tests substitute clients and credentials; they do not demonstrate that a provider accepts or respects the configured home/data directories. Use two test accounts, verify identity after sign-in and after restarting each profile, and record the client version and OS.

The [Google authentication audit](google-authentication.md) records the reviewed versions, inherited credential selectors, gateway refusal and administrator-policy handling. Synthetic tests additionally verify separate Google process homes and Cloud SDK directories. Real identity and shared-keyring qualification remain pending.

## Reproduce

Start with the virtual environment from [Quick start](../README.md#quick-start). Use the Windows commands below from the repository root.

```powershell
.\run.cmd --smoke-test
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q --junitxml=dist/evidence/tests.xml
.\.venv\Scripts\python scripts\capture_ui.py
.\setup.cmd
.\.venv\Scripts\python scripts\smoke_package.py
```

On macOS and Linux, use the shell launcher and the virtual environment's Python.

```sh
./run.sh --smoke-test
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q --junitxml=dist/evidence/tests.xml
.venv/bin/python scripts/capture_ui.py
./setup.sh
.venv/bin/python scripts/smoke_package.py
```

The source smoke test opens and closes the GUI. It uses the normal profile data directory, so run it with a fresh data directory if you want to avoid migrating an existing database. The capture script creates a fresh synthetic store under `dist/visual-fixture/` and saves Dark screenshots of each provider's new-profile form, the six-profile overview and browser settings. It writes the PNGs and `capture.json` to `dist/evidence/ui/` by default. Use `--output` to choose a separate folder. `QT_SCALE_FACTOR` multiplies native display scaling. Read the resulting device pixel ratio in `capture.json`.

The browser settings screenshot was captured on Windows on 2026-11-15 from the Qt application at `5ea95fb` using the updated capture script. It shows the browser picker and auto-detection with a synthetic store at a device pixel ratio of 1.5.

On a headless Linux runner, use `QT_QPA_PLATFORM=offscreen` for Qt tests and smoke checks. Use the native Qt platform plugin for interactive validation. The saved macOS and Linux CI runs cover dependency installation, unit tests, the launcher help, builds and offscreen package smoke checks. The source GUI smoke and capture commands above were rerun on Windows for this guide.

Each build retains a fresh staging directory and writes the executable path to `dist/latest-native.txt`. The package smoke script checks help, GUI startup and a CLI session with a synthetic client. Signing, notarization, byte reproducibility and automatic updates remain unqualified.
