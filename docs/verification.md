# Unified desktop verification

## Windows download compatibility

The [system requirements](../README.md#system-requirements) describe the bundled runtime baseline and the operating systems tested with Hub. The Windows sign-in check queries `Win32_Process` in the current Windows session and uses the executable name even when Windows does not expose the command line. The check does not depend on a particular Chrome profile, installation path, or user name. Windows and the provider handle the browser return. [Microsoft Win32_Process documentation](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-process) · [Windows URI activation](https://learn.microsoft.com/en-us/windows/apps/develop/launch/launch-default-app)

On 2026-11-15, the rebuilt x64 EXE passed the single-file help, GUI startup and synthetic CLI smoke checks on Windows 11 Pro 26H2 (build 26300.9974). The test copied only the executable to an empty folder, used a system-only `PATH` and cleared Python and Qt environment overrides. The source suite passed 71 tests and 14 subtests. Process detection identified a running Claude Desktop 5.11492.5.0 without an administrator token. Clean-machine testing and the live browser return with Google remain pending.

On the same Windows release, paired synthetic Hub profiles opened two simultaneous windows for Codex desktop (Store package 26.1111.2228.0) and two for Claude Desktop (Store package 5.11492.5.0). All four dedicated desktop directories contained app data. The Codex launcher supplied a separate `CODEX_ELECTRON_USER_DATA_PATH` and `CODEX_HOME` to each instance. The Antigravity App 2.32.1 launch was blocked by Windows error 740 because the local installation has a machine-wide `RUNASADMIN` compatibility setting. Account isolation, browser return, and settings persistence after restart still require real sign-in tests.

The Windows profile permission regression test reads the ACL of a new synthetic session folder and verifies that the current user's SID has inheritable access. The documented repair command also passed on a synthetic folder with an existing settings file, whose contents were preserved. Repairing an existing folder created under elevation requires an administrator session under the same Windows account. [Windows profile folder permissions](../README.md#windows-profile-folder-permissions)

A user reported that Chrome showed the external-app prompt after Google sign-in, and that the Claude Desktop profile opened by Hub remained signed out after the prompt. The installed Claude 5.11492.5.0 package registers the `claude` protocol with Windows at the application level. The Hub sign-in result directs Windows users to the provider's email code flow in the original Claude Desktop window. Verify that flow with test accounts before qualifying desktop sign-in. [Claude sign-in help](https://support.claude.com/en/articles/13189465-log-in-to-your-claude-account)

The packaged Windows link handler forwarded a synthetic Google return to the selected profile of two running Claude Desktop 5.11492.5.0 instances. Only that profile logged receipt, and Claude rejected the synthetic code as expected. The named-pipe tests cover a competing relay, expiration, closing Hub, and one-time delivery. The handler registration and real Google sign-in still need a user acceptance test. [Setup instructions](../README.md#google-sign-in-for-claude-desktop-on-windows)

During user testing, Windows identified Hub as the selected handler, while the managed Claude session directory rejected access from a standard Windows token. The revised relay dispatches Claude from the already-running Hub process. A synthetic return reached only the selected Claude window with separate Hub and browser data roots. The browser-side helper did not open a profile database, and the diagnostic log contained event names without callback data.

The portable registration tests cover an existing handler with a moved EXE, a current path, an unregistered profile, and a source checkout. A packaged Windows 11 startup from a different folder also updated the real registered command, and the Windows association API continued to report Hub as the selected handler. Selecting the handler in Windows is a separate, one-time user action.

For clean-machine verification, copy only the x64 EXE to a fresh Windows environment without Python or Qt installed. Test Windows 10 at the stated minimum and a supported Windows 11 x64 version. Record the edition, version, build, architecture and exact executable tested. On each system, run `ai-profile-hub.exe --smoke-test` from PowerShell in a fresh Windows user profile and open the app normally. Confirm a synthetic profile can be saved and reopened. Test ARM64 separately before claiming support there.

For Claude Desktop, record the installed client and browser versions. With default Claude Desktop running, confirm that Hub's **Sign in** asks you to quit it. After quitting from the notification area, start **Sign in** from Hub and verify the Google browser return with a test account. If it opens the default Claude window, verify the email code flow in the Hub-launched window. Reopen the same profile and verify the retained account. Record the result separately from standalone startup.

## Qt 6.12.0 and Nuitka 4.3.5 on 2026-11-15

Commit `ba886b7` moved the source to PySide6 6.12.0 (Essentials, Addons and Shiboken, without the `PySide6` meta package, which 6.12 extends with unused PDF and WebEngine wheels) and Nuitka 4.3.5. On Windows 11 with Python 3.13.17 the source suite passed 72 tests and 14 subtests, `setup.cmd` built the single-file EXE and `scripts/smoke_package.py` passed. The GitHub workflow run for `ba886b7` passed all seven jobs (lint and dependency audit, plus the tests on Windows, macOS and Ubuntu with Python 3.11 and 3.13, and the native package smoke on 3.13). The package contains the same Qt modules and plugins as the 6.10.1 build.

The Qt 6.12.0 component notice review followed on the same day (inventory under `docs/licenses/qt-6.12.0/`). It observed libjpeg-turbo 3.2.0, libpng 1.6.58 and PCRE2 10.48 in the binaries; FreeType, HarfBuzz, libtiff, libwebp and the smaller components follow the Qt source attribution only. A legal review of Nuitka 4's AGPLv3 license with its Runtime Library Exception, the unresolved component versions and the LGPLv3 route are still open. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Do not distribute a standalone package before they are closed. The system requirements in the README follow the Qt 6.12 supported-platforms page (macOS 14.4 or later; Windows 10 1809 or later, the last Qt release to support Windows 10); they were not retested on those systems. The records below describe earlier builds and keep their original versions.

## Stable Windows distribution on 2026-11-15

The stable distribution build passed with Python 3.13.17, PySide6 6.10.1 and Nuitka 2.8.9. `setup.cmd` produced `dist/ai-profile-hub/ai-profile-hub.exe`, with compilation files under `deployment/native/`. The package smoke passed help, GUI startup and a synthetic CLI session from a separate working directory with a system-only PATH and Python/Qt overrides removed. The suite passed 71 tests and 14 subtests, including repeated output replacement, obsolete-file removal, historical-evidence preservation and preservation of the previous distribution after compilation failure. These checks do not substitute for qualification on a clean target machine or interactive macOS/Linux testing.

## Windows verification at `97adcd4`

On 2026-11-15, a clean Windows clone at `97adcd4` passed the setup and verification commands below with Python 3.13.17, PySide6 6.10.1 and Nuitka 2.8.9.

| Command | Result |
| --- | --- |
| `py -3 -m venv .venv` and `python -m pip install -r requirements.txt` using the virtual environment | Environment created and runtime dependencies installed. |
| `run.cmd --smoke-test` | GUI opened and closed successfully and created a fresh SQLite database in a synthetic data directory. |
| `python -m pip install -r requirements-dev.txt` | Development dependencies installed. |
| `python -m pytest -q --junitxml=dist/evidence/tests.xml` | `49 passed, 14 subtests passed in 16.82s` |
| `python scripts/capture_ui.py` | Produced five PNGs and `capture.json` from the Windows Qt app with synthetic profiles. |
| `setup.cmd` | Built standalone package `20261115T115514Z-38d5a9`. |
| `python scripts/smoke_package.py` | `Native package smoke passed.` Help, GUI startup and the synthetic bundled CLI session all exited successfully. |

## Earlier Windows checks

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

The [CI workflow](../.github/workflows/test.yml) runs tests on Python 3.11 and 3.13 for Windows, macOS and Linux, and native builds and package smoke tests on 3.13. Qt tests use the offscreen platform. Manual qualification run `43611594432` used workflow revision `231554f` and application source `341e1c7`. All six jobs passed 36 tests each, and all three native package smoke steps passed. Push run `43611594501` for `231554f` passed the same checks. The historical runs were removed after the results were recorded. Local summaries remain in ignored `dist/ci-verification/`.

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

The overview and browser settings screenshots were captured on Windows on 2026-11-15 from AI Profile Hub at `97adcd4`. The three editor screenshots were refreshed after consolidating the editor actions. All five use synthetic profiles, Dark appearance and a device pixel ratio of 1.5. The six-profile overview is 2040 × 1050 pixels, the three new-profile forms are 1650 × 900 pixels, and the browser settings screen is 1650 × 840 pixels.

On a headless Linux runner, use `QT_QPA_PLATFORM=offscreen` for Qt tests and smoke checks. Use the native Qt platform plugin for interactive validation. The saved macOS and Linux CI runs cover dependency installation, unit tests, the launcher help, builds and offscreen package smoke checks. The source GUI smoke and capture commands above were rerun on Windows for this guide.

Each build reuses `deployment/native/` for staging. After compilation and the executable help check succeed, Windows atomically replaces the EXE in `setups/ai-profile-hub/`. macOS and Linux replace the complete distribution directory. A Windows regression test holds the destination open as another process's working directory during the copy. Another test verifies that a locked executable leaves both the previous EXE and the compiled EXE available. After successful placement, the build writes the executable path to `dist/latest-native.txt` for the smoke script. The complete distribution includes the Python and Qt runtimes. On Windows the smoke script copies only the executable to an empty temporary directory. On all platforms it checks help, GUI startup and a CLI session with a synthetic client from outside the source tree, with a system-only PATH and Python/Qt environment overrides removed. Archived Windows compilation reports are under `dist/evidence/legacy-build-reports/`. Signing, notarization, byte reproducibility and automatic updates remain unqualified.
