# Manual qualification checklist

These checks need a real machine or account and cannot be automated. Record the edition, version, build, architecture and exact executable for each run, then add the result to [verification.md](verification.md).

## Clean Windows machine (Windows 10 minimum and a supported Windows 11 x64)
- [ ] Copy only `ai-profile-hub.exe` to a fresh Windows user profile without Python or Qt.
- [ ] Run `ai-profile-hub.exe --smoke-test` from PowerShell.
- [ ] Open the app normally, save a synthetic profile, close and reopen it.
- [ ] ARM64: test separately before claiming support.

## Claude Desktop with Google sign-in (test account)
- [ ] Record the Claude Desktop and browser versions.
- [ ] With default Claude Desktop running, confirm **Sign in** asks you to quit it.
- [ ] Quit it from the notification area, start **Sign in** from Hub and complete the Google browser return.
- [ ] If the default Claude window opens, complete the email code flow in the Hub-launched window.
- [ ] Reopen the same profile and confirm the account is retained.

## Codex Desktop sign-in link handler (test account)
- [ ] Record the Codex Desktop and browser versions.
- [ ] Start **Sign in** on a Codex Desktop profile and confirm Hub registers **AI Profile Hub Codex Links** and shows the Default apps hint.
- [ ] Assign the CODEX and CHATGPT link types to the Hub handler, finish the browser sign-in and confirm the Codex window of that profile comes forward.
- [ ] Confirm Hub removes the entry when the sign-in ends and record what Windows shows for the CODEX and CHATGPT choices afterwards.
- [ ] With a Hub entry still registered, click **Restore original link handlers** in Settings and confirm the Hub entries are gone and Windows Default apps opens with CLAUDE, CODEX and CHATGPT on the original apps.
- [ ] Confirm the Claude and Codex relay log events can be told apart.

## Running client popup
- [ ] With a desktop client running, start **Sign in**, an import and an export in turn: each lists the process names and PIDs.
- [ ] Choose Cancel and confirm nothing is closed. Choose Yes and confirm only the listed processes close and the action continues or asks to start again.

## Import of an empty client database
- [ ] Close the client, import settings into a Codex profile and start it: the imported chats and memories appear after a restart.
- [ ] Keep the client open on its database and import: Hub asks to close the client instead of replacing the file.

## Antigravity
- [ ] Without the `RUNASADMIN` compatibility setting, launch a profile and confirm it starts.
- [ ] With the setting, confirm Hub shows the administrator-rights message instead of a raw Windows error.

## macOS and Linux
- [ ] Follow the README setup, run `run.sh --smoke-test` and the test suite.
- [ ] Launch a profile and confirm the dedicated data directory is used.
