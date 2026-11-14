import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from profile_switch import launch, platform_tools, store
from profile_switch.catalog import CLI_NAMES, TARGETS, URLS


class HubTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = store.Store(self.root / "data with spaces")
        self.client = self.root / "Client executable"
        self.client.touch()

    def add(self, service, mode, name="Lavoro", **kwargs):
        return self.store.profile(self.store.save(service, name, mode, **kwargs))

    def test_each_web_target_opens_an_isolated_browser_directory(self):
        profiles = [self.add(*key) for key in URLS]
        with (patch.object(launch, "browser_path", return_value=self.client),
              patch.object(launch, "detached") as spawn):
            for profile in profiles:
                launch.open_profile(self.store, profile)
        commands = [call.args[0] for call in spawn.call_args_list]
        for profile, command in zip(profiles, commands, strict=True):
            self.assertIn(f"--user-data-dir={self.store.directory(profile) / 'browser'}", command)
            self.assertIn(f"--app={URLS[profile.service, profile.mode]}", command)
        self.assertEqual(len(set(p.id for p in profiles)), len(profiles))

    def test_browser_reset_restores_detection_without_saving_the_detected_path(self):
        stale = self.root / "missing browser"
        self.store.save_browser(stale)
        with (patch.object(launch, "browser_candidates", return_value=[self.client]) as candidates,
              patch.object(launch, "executable", side_effect=lambda path: path == self.client)):
            with self.assertRaisesRegex(OSError, "use browser auto-detection"):
                launch.browser_path(self.store)
            candidates.assert_not_called()

            self.store.clear_browser()
            self.assertEqual(launch.browser_path(self.store), self.client)
            self.assertIsNone(self.store.browser())
            self.assertEqual(launch.browser_path(self.store), self.client)
            self.assertEqual(candidates.call_count, 2)

    def test_documented_cli_homes_and_independent_codex_login(self):
        first = self.add("chatgpt", "cli", "Lavoro", workdir=str(self.root))
        second = self.add("chatgpt", "cli", "Personale")
        claude = self.add("claude", "cli")
        gemini = self.add("gemini", "gemini-cli")
        with (patch.object(launch, "find_binary", return_value=self.client),
              patch.dict(os.environ, {"ANTHROPIC_API_KEY": "example", "OPENAI_API_KEY": "example", "GEMINI_API_KEY": "example"})):
            work = launch.local_command(self.store, first, login=True)
            personal = launch.local_command(self.store, second)
            anthropic = launch.local_command(self.store, claude, login=True)
            google = launch.local_command(self.store, gemini, login=True)
        self.assertEqual(work.argv[1:], ["login", "--device-auth"])
        self.assertEqual(work.cwd, self.root)
        self.assertNotEqual(work.env["CODEX_HOME"], personal.env["CODEX_HOME"])
        for command in (work, personal):
            self.assertNotIn("OPENAI_API_KEY", command.env)
            self.assertEqual(command.env["CODEX_HOME"], command.env["CODEX_SQLITE_HOME"])
            self.assertIn('cli_auth_credentials_store = "file"', (Path(command.env["CODEX_HOME"]) / "config.toml").read_text())
        self.assertEqual(anthropic.argv[1:], ["auth", "login"])
        self.assertEqual(Path(anthropic.env["CLAUDE_CONFIG_DIR"]), self.store.directory(claude) / "claude-code")
        self.assertNotIn("ANTHROPIC_API_KEY", anthropic.env)
        self.assertEqual(Path(google.env["GEMINI_CLI_HOME"]), self.store.directory(gemini) / "google-home")
        self.assertEqual(google.env["GEMINI_FORCE_FILE_STORAGE"], "true")
        self.assertNotIn("GEMINI_API_KEY", google.env)

    def test_all_desktop_targets_build_a_command_on_each_platform(self):
        for system in ("win32", "darwin", "linux"):
            for service, entries in TARGETS.items():
                for mode, target in entries.items():
                    if target.kind != "desktop":
                        continue
                    with self.subTest(system=system, service=service, mode=mode):
                        profile = self.add(service, mode, system, workdir=str(self.root))
                        with (patch.object(launch, "find_binary", return_value=self.client),
                              patch.object(launch.sys, "platform", system)):
                            command = launch.local_command(self.store, profile)
                        folder = self.store.directory(profile)
                        state = folder / ("claude-desktop" if service == "claude" else "desktop")
                        self.assertIn(f"--user-data-dir={state}", command.argv)
                        self.assertTrue(state.is_dir())
                        if service == "claude" and system == "darwin":
                            self.assertEqual(command.env["CLAUDE_USER_DATA_DIR"], str(state))
                        if mode == "ide":
                            self.assertIn(f"--extensions-dir={folder / 'extensions'}", command.argv)
                            self.assertEqual(command.argv[-1], str(self.root))

    def test_google_advanced_clients_use_a_per_profile_home(self):
        first = self.add("gemini", "cli", "Personale")
        second = self.add("gemini", "cli", "Lavoro")
        with patch.object(launch, "find_binary", return_value=self.client):
            a = launch.local_command(self.store, first)
            b = launch.local_command(self.store, second)
        self.assertNotEqual(a.env["HOME"], b.env["HOME"])
        self.assertEqual(Path(a.env["HOME"]), self.store.directory(first) / "google-home")
        self.assertIn(("gemini", "cli"), CLI_NAMES)

    def test_migrates_existing_web_and_desktop_sessions_without_changing_paths(self):
        old = self.root / "legacy"
        old.mkdir()
        first_id, second_id = "a" * 32, "b" * 32
        with sqlite3.connect(old / "profiles.sqlite3") as db:
            db.executescript("""
                CREATE TABLE profiles (id TEXT PRIMARY KEY, service TEXT, name TEXT, name_key TEXT,
                    mode TEXT CHECK (mode IN ('web','desktop')), archived INTEGER DEFAULT 0);
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
                INSERT INTO settings VALUES ('browser', '/old/chrome');
            """)
            db.execute("INSERT INTO profiles VALUES (?, 'claude', 'Personale', 'personale', 'web', 1)", (first_id,))
            db.execute("INSERT INTO profiles VALUES (?, 'claude', 'Desktop', 'desktop', 'desktop', 0)", (second_id,))
        db.close()
        browser = old / "sessions" / first_id / "browser"
        browser.mkdir(parents=True)
        (browser / "state").touch()
        migrated = store.Store(old)
        self.assertEqual(migrated.profile(first_id).mode, "chat")
        self.assertEqual(migrated.profile(second_id).mode, "desktop")
        self.assertTrue((migrated.directory(migrated.profile(first_id)) / "browser" / "state").is_file())
        self.assertEqual(migrated.browser(), Path("/old/chrome"))
        self.assertEqual(store.Store(old).profiles(), migrated.profiles())
        self.assertTrue(migrated.save("claude", "Personale", "web"))

    def test_duo_link_reuses_existing_session_and_delete_leaves_it_intact(self):
        original = self.root / "SecondProfile"
        original.mkdir()
        marker = original / "Local State"
        marker.touch()
        with (patch.object(store.sys, "platform", "win32"),
              patch.object(store, "duo_directory", return_value=original),
              patch.object(launch, "duo_directory", return_value=original),
              patch.object(launch, "find_binary", return_value=self.client)):
            profile = self.add("claude", "desktop", legacy_duo=True)
            self.assertIn(f"--user-data-dir={original}", launch.local_command(self.store, profile).argv)
            with self.assertRaisesRegex(ValueError, "already linked"):
                self.add("claude", "desktop", "Altro", legacy_duo=True)
        self.store.delete(profile)
        self.assertTrue(marker.exists())
        self.assertEqual(self.store.profiles(), [])

    def test_cannot_delete_a_cli_profile_while_its_lock_is_held(self):
        profile = self.add("claude", "cli")
        with self.store.lock(profile), self.assertRaisesRegex(OSError, "Close the terminal"):
            self.store.delete(profile)
        self.store.delete(profile)
        self.assertEqual(self.store.profiles(), [])

    def test_open_cli_hands_profile_to_terminal(self):
        profile = self.add("chatgpt", "cli")
        with (patch.object(launch, "find_binary", return_value=self.client),
              patch.object(launch, "open_terminal") as terminal):
            launch.open_profile(self.store, profile, login=True)
        terminal.assert_called_once_with(profile.id, True)

    def test_open_cli_reports_invalid_paths_before_opening_terminal(self):
        missing = self.root / "missing"
        cases = (
            ({"executable": str(missing)}, "Executable unavailable"),
            ({"workdir": str(missing)}, "Working directory unavailable"),
        )
        for index, (paths, message) in enumerate(cases):
            with self.subTest(message=message):
                profile = self.add("chatgpt", "cli", f"Profile {index}")
                self.store.save(profile.service, profile.name, profile.mode, previous=profile, **paths)
                with (patch.object(launch, "binary_candidates", return_value=[self.client]),
                      patch.object(launch, "executable", side_effect=lambda path: path == self.client),
                      patch.object(launch, "open_terminal") as terminal,
                      self.assertRaisesRegex(OSError, message)):
                    launch.open_profile(self.store, profile)
                terminal.assert_not_called()

    def test_desktop_login_refuses_another_instance_of_same_product(self):
        profile = self.add("claude", "desktop")
        with (patch.object(launch, "find_binary", return_value=self.client),
              patch.object(launch, "process_arguments", return_value='"C:\\Apps\\Claude.exe"'),
              patch.object(launch, "detached") as spawn, self.assertRaisesRegex(OSError, "other desktop instances")):
            launch.open_profile(self.store, profile, login=True)
        spawn.assert_not_called()

    def test_claude_msix_falls_back_to_activation_when_direct_start_is_denied(self):
        binary = self.root / "WindowsApps" / "Claude" / "app" / "Claude.exe"
        args = [str(binary), f"--user-data-dir={self.root / 'profile'}"]
        command = launch.Command(args, {}, self.root)
        with (patch.object(launch.sys, "platform", "win32"),
              patch.object(launch, "detached", side_effect=PermissionError),
              patch.object(launch, "activate_claude_msix") as activate):
            launch.start_claude_desktop(command)
        activate.assert_called_once_with(args[1:])

    def test_native_codex_settings_are_not_overwritten(self):
        profile = self.add("chatgpt", "cli")
        folder = self.store.directory(profile)
        home = Path(launch.codex_home(folder))
        config = home / "config.toml"
        config.write_text('cli_auth_credentials_store = "keyring"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cli_auth_credentials_store"):
            launch.codex_home(folder)
        self.assertIn('"keyring"', config.read_text())

    def test_terminal_commands_preserve_arguments_and_spaces(self):
        argv = [str(self.client), "--session", "a" * 32, "--login"]
        with patch.object(platform_tools.sys, "platform", "win32"):
            self.assertEqual(platform_tools.terminal_command(argv), argv)
        with patch.object(platform_tools.sys, "platform", "darwin"):
            self.assertIn(f"'{self.client}'", platform_tools.terminal_command(argv)[-1])
        with (patch.object(platform_tools.sys, "platform", "linux"),
              patch.object(platform_tools.shutil, "which", side_effect=lambda name: "/usr/bin/xterm" if name == "xterm" else None)):
            self.assertEqual(platform_tools.terminal_command(argv), ["/usr/bin/xterm", "-e", *argv])


if __name__ == "__main__":
    unittest.main()
