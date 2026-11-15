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

## Antigravity
- [ ] Without the `RUNASADMIN` compatibility setting, launch a profile and confirm it starts.
- [ ] With the setting, confirm Hub shows the administrator-rights message instead of a raw Windows error.

## macOS and Linux
- [ ] Follow the README setup, run `run.sh --smoke-test` and the test suite.
- [ ] Launch a profile and confirm the dedicated data directory is used.
