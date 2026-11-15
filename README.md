# AI Profile Hub

AI Profile Hub is a desktop launcher for **Windows, macOS and Linux**. Use it to save and reopen work and personal profiles for Claude Code, Codex and Antigravity / Gemini. Pick a web, terminal or desktop client for each profile. You sign in and confirm the account in that client.

![AI Profile Hub in Dark appearance with six work and personal profiles. The two Codex profiles are selected.](docs/screenshots/profiles-dark.png)

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

## Set up two profiles

Follow the [work and personal profile guide](docs/two-profiles.md) to create a pair for the same client and check both accounts after reopening them.

### Create and open any profile

1. In **Profiles**, choose **New profile**, select a product and client, and enter a name such as **Work**. For terminal and desktop clients, **Advanced settings** lets you set absolute paths for the executable and an existing working directory. Leave them blank for automatic detection and your home directory. Choose **Save profile**.
2. Select the saved profile and choose **Open profile**, or press Enter when the list has focus. For a web profile, sign in in the browser window. For a terminal or desktop profile, select one row and choose **Sign in** in the profile details. Quit other instances of the same desktop client before starting its sign-in flow.
3. Check the account or workspace in the client. After signing in, close the session and reopen it from Hub to check which account it kept.

To open several profiles, hold Ctrl (Command on macOS) while selecting rows and choose **Open selected**.

## Manage profiles and browser settings

- Search by profile, product or client name. Combine the product filter with the client type filter (**Web**, **Terminal**, **Desktop**). **Clear filters** returns to the complete list.
- Select a profile for its full name, source, session folder and client availability. In a compact window, choose **Details**. After installing a client or changing its path, choose **Refresh detection** in the details to check again without waiting for the 30-second cache to expire.
- Use **Edit profile** to change the name or paths. Create a new profile to use a different product or client. If a path fails validation, Hub opens **Advanced settings** and focuses the field to correct.
- Close the associated windows or terminal before choosing **Remove profile**. The confirmation describes the local data removed. **Remove link** preserves the original Claude Desktop session folder. Your online account stays active.
- Use **Settings → Choose Chrome or Chromium…** to set a browser executable. **Use auto-detection** clears the override, checks for Chrome or Chromium immediately, and shows the result next to **Browser**.
- Choose **System**, **Light** or **Dark** appearance in **Settings**. Use Ctrl+N (Command+N on macOS) to create a profile, Ctrl+F (Command+F on macOS) to focus search, and Tab or Shift+Tab to move between controls.
- Launch results show which requests succeeded or failed. **Retry failed** repeats the last open or sign-in request for its failed profiles. The result reports the request to start the client. Confirm the actual account in the client window or terminal.

## Reuse existing profiles

On Windows, Hub can link a compatible Claude Desktop session. If **Claude Desktop session found. Link session…** appears in **Profiles**, choose it, review the folder shown, and choose **Link session**. You can also start from **Settings → Link existing session…**. **Remove link** preserves the original session folder.

For the ChatGPT desktop app, Antigravity App and Antigravity IDE, create a profile for the installed client and sign in from its window. For desktop profiles, **Refresh detection** checks the executable and working directory.

## Available clients and limitations

| Product | Web | Locally installed clients |
| --- | --- | --- |
| Claude Code | Claude Code on the web, Claude on the web | Claude Code CLI (`claude`), Claude Desktop † |
| Codex | Codex on the web, ChatGPT on the web | Codex CLI (`codex`), ChatGPT desktop app † |
| Antigravity / Gemini | Gemini on the web | Gemini CLI (`gemini`), Antigravity CLI (`agy`) †, Antigravity IDE †, Antigravity App † |

† Experimental. Availability varies by operating system and provider. Desktop apps can ignore the profile directory, reuse a running instance or route sign-in through the operating system. Verify the account in each client window. [ChatGPT desktop app](https://learn.chatgpt.com/docs/app) · [Community Codex desktop workaround](https://github.com/phoem/Codex-Profile-Launcher) · [Antigravity download](https://antigravity.google/download) · [Antigravity IDE forum](https://discuss.ai.google.dev/t/how-do-user-data-dir-and-profile-work/137054)

### Profile data

- The browser receives a separate `--user-data-dir` for each profile. [Chromium documentation](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md)
- Claude Code receives `CLAUDE_CONFIG_DIR`. Anthropic documents this setting for signing in with different accounts. [Claude Code authentication](https://code.claude.com/docs/en/authentication)
- Codex receives `CODEX_HOME` and `CODEX_SQLITE_HOME`. The profile's `file` setting stores credentials in `auth.json`. Organization-managed authentication rules take precedence. [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-advanced) · [Credential storage](https://learn.chatgpt.com/docs/auth)
- Local Google clients receive a dedicated process home, `GEMINI_CLI_HOME` and Cloud SDK directory. Inherited credential selectors are removed. An inherited Google gateway or custom-header override blocks launch with an explanation; ask your administrator to resolve managed configurations. System settings pointers remain available to the client. Google documents `~/.gemini/antigravity-cli/settings.json` and migration from Gemini CLI. Full `agy` authentication isolation still requires verification, including its shared keyring. See the [versioned authentication audit and limits](docs/google-authentication.md). [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/v0.68.0/docs/cli/enterprise.md) · [Antigravity CLI settings](https://antigravity.google/docs/cli/using/) · [Google migration guide](https://antigravity.google/docs/cli/gcli-migration)
- On Windows, the launcher passes a dedicated profile folder to Claude Desktop. Update MSIX builds in the `2.42304.x` series, which can ignore this folder. Keeping one instance open for the first sign-in helps the browser return to the intended window. [MSIX issue](https://github.com/anthropics/claude-code/issues/103068)

To find a profile's session folder, select it and open **Details**. The launcher leaves authentication files under the client's control. Clients run as the same operating system user and can access the same projects and system services.

## Build and test

Use `setup.cmd` on Windows or `setup.sh` on macOS and Linux to generate a self-contained package. The setup scripts use `pyside6-deploy` and Nuitka to produce one executable on Windows, an `.app` on macOS, and a package folder on Linux. Use the `.venv` from Quick start. Windows requires Visual Studio C++ Build Tools, macOS requires Xcode Command Line Tools, and Linux requires a supported C compiler and the Qt system libraries. Build on the operating system you want to package for. The build configuration and support scripts live in `scripts/`.

On Windows, with the Python launcher installed:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
.\setup.cmd
.\.venv\Scripts\python scripts\smoke_package.py
```

On macOS and Linux:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
./setup.sh
.venv/bin/python scripts/smoke_package.py
```

Ready-to-copy packages go in `setups/`. Each successful build replaces `setups/ai-profile-hub/`. On Windows, copy or run `setups/ai-profile-hub/ai-profile-hub.exe` by itself. It extracts its embedded Python and Qt libraries to a temporary directory at startup. On macOS and Linux, copy the complete app bundle or package folder. The browser and provider clients are separate installations. Compilation files stay under `deployment/native/` and verification evidence under `dist/`.

The package smoke test checks help, GUI startup and a bundled CLI session using a synthetic client. For CI coverage, interactive testing and account isolation, see [verification status](docs/verification.md).

See the [third-party notices](THIRD_PARTY_NOTICES.md) for the reviewed standalone dependencies and the remaining checks before redistributing a binary.

## Get help

For launcher problems, include your operating system, Python version, client version and steps to reproduce. Share only redacted error text and synthetic profile data. [AI Profile Hub issues](https://github.com/dennidalpos/ai-profile-hub/issues)

Independent project. [MIT license](LICENSE).
