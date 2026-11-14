# AI Profile Hub

AI Profile Hub is a desktop launcher for **Windows, macOS and Linux**. If you use several AI accounts or clients, create a profile for each client you want to open. Find profiles for Claude Code, Codex and Antigravity / Gemini in one searchable list. On Windows you can also link an existing Claude Desktop Duo second session.

![Light theme with four sample profiles, search and filters, and the selected Research profile's client and session details.](docs/screenshots/profiles-light.png)

## Quick start

Download or clone the source and open a terminal in the repository root. Install Python 3.11 or later. You also need Chrome or Chromium for a web profile, or the provider's installed client for a terminal or desktop profile.

On Windows, run these commands in PowerShell with the Python launcher installed.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\run.cmd
```

On macOS and Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run.sh
```

On Windows you can double-click `run.cmd` after setup. On Linux, install the Qt runtime libraries for your distribution if Qt fails to load. The Ubuntu CI runner uses `libegl1` and `libopengl0`. Opening a terminal profile also requires a supported terminal such as GNOME Terminal, Konsole or xterm. On macOS, allow Automation access to Terminal if prompted.

## Create and open profiles

1. Choose **New profile**, pick a product and client, and enter a name such as **Work**. Under **Advanced settings**, leave the executable blank to let Hub find it, or set an absolute path for a terminal or desktop client. You can also set an existing working directory. Choose **Save profile**.
2. Select the profile and choose **Open profile** or press Enter. For a web profile, sign in in the browser window that opens. For a terminal profile, choose **Sign in** or follow the client's sign-in instructions. The Codex CLI button uses device code authentication, which your account or workspace must allow. [Codex authentication](https://learn.chatgpt.com/docs/auth)
3. For a desktop profile, close other instances of the same client before choosing **Sign in**. Verify the account in the new client window.

To open several profiles, hold Ctrl (Command on macOS) while selecting rows and choose **Open selected**.

## Manage profiles and browser settings

- Search by profile, product or client name; combine product and client filters. **Clear filters** returns to the complete list.
- Select a profile for its full name, source, session folder and client availability. In a compact window, choose **Details**. Client detection is cached for up to 30 seconds; **Refresh detection** checks again.
- Use **Edit profile** to change the name or paths. Create a new profile to use a different product or client. Invalid values stay in the form with an explanation so you can correct and save them.
- Close the associated windows or terminal before choosing **Remove profile**. The confirmation describes the local data removed. **Remove link** preserves the original Claude Desktop Duo folder. Your online account stays active.
- Use **Settings → Choose Chrome or Chromium…** to set a browser executable. **Use auto-detection** clears the override, including when the saved executable is unavailable.
- Choose **System**, **Light** or **Dark** appearance in Settings. Ctrl+N / Command+N creates a profile; Ctrl+F / Command+F focuses search; Enter in the list opens the selection.
- During an operation you can continue searching and navigating. Failed batch launches list each affected profile with guidance; **Retry failed** retries only those entries. A launch request does not prove sign-in or account isolation.

### Screenshots

**Create a profile**

![New profile form with Claude Code on the web selected, Work in the Name field, and the Save profile button.](docs/screenshots/qt-profile-editor.png)

**Dark appearance**

![Dark theme with the Research profile selected and its client and session details visible.](docs/screenshots/profiles-dark.png)

Captured from AI Profile Hub on Windows on 2026-11-14 using the Qt interface from revision `231554f` and synthetic data. [Capture instructions](docs/verification.md#reproduce).

## Reuse existing profiles

- **AI Profile Switch** uses the same local directory. On startup, AI Profile Hub updates the SQLite schema and reuses the existing profile IDs and folders. Existing Claude and ChatGPT web profiles still open their original websites. Create a separate profile for the new Claude Code and Codex destinations. To keep the option of returning to the earlier version, back up `profiles.sqlite3` before opening AI Profile Hub.
- **Claude Desktop Duo for Windows**. If `%LOCALAPPDATA%\ClaudeDesktopDuo\SecondProfile` exists, use the discovered-session prompt, **New profile → Link existing session…**, or **Settings → Link existing session…**. Review the original folder before confirming. The app reuses it without moving credentials. Repeating the action selects the existing link. Removing the link leaves the Duo data in its original folder. This integration covers the behavior already supported in Hub, rather than undocumented functions of the original Duo app.

## Available clients and limitations

| Product | Web | Locally installed clients |
| --- | --- | --- |
| Claude Code | Claude Code on the web, Claude on the web | Claude Code CLI (`claude`), Claude Desktop † |
| Codex | Codex on the web, ChatGPT on the web | Codex CLI (`codex`), Codex Desktop † |
| Antigravity / Gemini | Gemini on the web | Antigravity CLI (`agy`) †, Gemini CLI (`gemini`), Antigravity IDE †, Antigravity App † |

† Experimental. Availability varies by operating system and provider. Desktop apps can ignore the profile directory, reuse a running instance or route sign-in through the operating system. Verify the account in each client window. [Codex desktop and platforms](https://learn.chatgpt.com/docs/app) · [Community Codex desktop workaround](https://github.com/phoem/Codex-Profile-Launcher) · [Antigravity download](https://antigravity.google/download) · [Antigravity IDE forum](https://discuss.ai.google.dev/t/how-do-user-data-dir-and-profile-work/137054)

### Profile data

- The browser receives a separate `--user-data-dir` for each profile. [Chromium documentation](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md)
- Claude Code receives `CLAUDE_CONFIG_DIR`. Anthropic documents this setting for signing in with different accounts. [Claude Code authentication](https://code.claude.com/docs/en/authentication)
- Codex receives `CODEX_HOME` and `CODEX_SQLITE_HOME`. The profile's `file` setting stores credentials in `auth.json`. Organization-managed authentication rules take precedence. [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-advanced) · [Credential storage](https://learn.chatgpt.com/docs/auth)
- Local Google clients receive a dedicated process home, `GEMINI_CLI_HOME` and Cloud SDK directory. Inherited credential selectors are removed. An inherited Google gateway or custom-header override blocks launch with an explanation; ask your administrator to resolve managed configurations. System settings pointers remain available to the client. Google documents `~/.gemini/antigravity-cli/settings.json` and migration from Gemini CLI. Full `agy` authentication isolation still requires verification, including its shared keyring. See the [versioned authentication audit and limits](docs/google-authentication.md). [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/v0.68.0/docs/cli/enterprise.md) · [Antigravity CLI settings](https://antigravity.google/docs/cli/using/) · [Google migration guide](https://antigravity.google/docs/cli/gcli-migration)
- On Windows, the launcher passes a dedicated profile folder to Claude Desktop. Update MSIX builds in the `2.42304.x` series, which can ignore this folder. Keeping one instance open for the first sign-in helps the browser return to the intended window. [MSIX issue](https://github.com/anthropics/claude-code/issues/103068)

Profile data is stored under `%LOCALAPPDATA%\AIProfileSwitch` on Windows, `~/Library/Application Support/AI Profile Switch` on macOS and `~/.local/share/ai-profile-switch` on Linux. On Linux, an absolute `XDG_DATA_HOME` overrides `~/.local/share`. The launcher leaves authentication files under the client's control. Clients run as the same operating system user and can access the same projects and system services.

## Build and test

The build uses `pyside6-deploy` and Nuitka to create a standalone folder or a macOS `.app`. Use the `.venv` from Quick start. Windows requires Visual Studio C++ Build Tools, macOS requires Xcode Command Line Tools, and Linux requires a supported C compiler and the Qt system libraries. Build on the operating system you want to package for.

On Windows, with the Python launcher installed:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
.\build.cmd
.\.venv\Scripts\python tools\smoke_package.py
```

On macOS and Linux:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
./build.sh
.venv/bin/python tools/smoke_package.py
```

Each build uses a fresh folder under `dist/native-builds/`. Open `dist/latest-native.txt` for the path to the executable. Keep the complete package folder or macOS app bundle together when moving it. The package includes Python, Qt and license notices. The browser and provider clients are separate installations.

The package smoke test checks help, GUI startup and a bundled CLI session using a synthetic client. For CI coverage, interactive testing and account isolation, see [verification status](docs/verification.md).

## Get help

For launcher problems, include your operating system, Python version, client version and steps to reproduce. Share only redacted error text and synthetic profile data. [AI Profile Hub issues](https://github.com/dennidalpos/ai-profile-hub/issues)

Independent project. [MIT license](LICENSE).
