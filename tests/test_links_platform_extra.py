from pathlib import PurePosixPath
import subprocess
from unittest.mock import patch

import pytest

from profile_switch import claude_links, launch, platform_tools, store


def test_claude_link_validation_and_google_return():
    good = "claude://login/google-auth?code=a&hop_nonce=b"
    assert claude_links.is_google_return(claude_links.parse_claude_link(good))
    for bad in ("https://x", "claude://", "claude://login/x y", 'claude://a"b', "claude://" + "a" * 9000):
        with pytest.raises(ValueError):
            claude_links.parse_claude_link(bad)
    for other in ("claude://login/google-auth?code=a", "claude://login/google-auth?code=a&code=b&hop_nonce=c",
                  "claude://login/other?code=a&hop_nonce=b", good + "#frag"):
        assert not claude_links.is_google_return(claude_links.parse_claude_link(other))


def test_forward_link_routes_through_the_relay_or_falls_back(tmp_path):
    link = "claude://login/google-auth?code=a&hop_nonce=b"
    client = tmp_path / "Claude.exe"
    with (patch.object(claude_links, "log_event"), patch.object(claude_links, "server_name", return_value="n"),
          patch.object(claude_links, "start_claude_desktop") as start):
        with patch.object(claude_links, "send_to_relay", return_value=b"routed"):
            claude_links.forward_link(link)
        start.assert_not_called()
        with patch.object(claude_links, "send_to_relay", return_value=b"failed"), pytest.raises(OSError, match="delivered"):
            claude_links.forward_link(link)
        with (patch.object(claude_links, "send_to_relay", return_value=b"fallback"),
              patch.object(claude_links, "find_binary", return_value=client),
              patch.object(claude_links, "client_environment", return_value={})):
            claude_links.forward_link(link)
        assert start.call_args.args[0].argv == [str(client), link]
        # Links that are not the Google return skip the relay entirely.
        with (patch.object(claude_links, "send_to_relay") as relay, patch.object(claude_links, "find_binary", return_value=client),
              patch.object(claude_links, "client_environment", return_value={})):
            claude_links.forward_link("claude://open/chat")
        relay.assert_not_called()


def test_profile_link_needs_a_claude_desktop_profile(tmp_path):
    data = store.Store(tmp_path / "s")
    desktop = data.profile(data.save("claude", "D", "desktop"))
    other = data.profile(data.save("claude", "W", "web"))
    command = launch.Command(["claude", "--user-data-dir=x"], {}, tmp_path)
    with (patch.object(claude_links, "local_command", return_value=command),
          patch.object(claude_links, "start_claude_desktop") as start):
        claude_links.forward_profile_link(data, desktop.id, "claude://x/y")
    assert start.call_args.args[0].argv[-1] == "claude://x/y"
    with pytest.raises(ValueError, match="unavailable"):
        claude_links.forward_profile_link(data, other.id, "claude://x/y")


def test_handler_command_quotes_the_application_path():
    assert claude_links._handler_command(["C:\\Program Files\\Hub\\hub.exe"]).endswith('--claude-link "%1"')


def test_diagnostics_log_never_raises(tmp_path):
    with patch.object(claude_links, "data_root", return_value=tmp_path):
        claude_links.log_event("sample")
    assert "sample" in (tmp_path / "diagnostics" / "claude-links.log").read_text(encoding="utf-8")
    with patch.object(claude_links, "private_directory", side_effect=OSError):
        claude_links.log_event("ignored")


# ---------------------------------------------------------------- platform tools


def test_terminal_command_per_platform():
    command = ["hub", "--session", "id"]
    with patch.object(platform_tools.sys, "platform", "win32"):
        assert platform_tools.terminal_command(command) == command
    with patch.object(platform_tools.sys, "platform", "darwin"):
        argv = platform_tools.terminal_command(command)
        assert argv[0] == "/usr/bin/osascript" and argv[-1] == "hub --session id"
    with (patch.object(platform_tools.sys, "platform", "linux"),
          patch.object(platform_tools.shutil, "which", side_effect=lambda n: "/bin/konsole" if n == "konsole" else None)):
        assert platform_tools.terminal_command(command) == ["/bin/konsole", "-e", *command]
    with (patch.object(platform_tools.sys, "platform", "linux"), patch.object(platform_tools.shutil, "which", return_value=None),
          pytest.raises(OSError, match="supported terminal")):
        platform_tools.terminal_command(command)


@pytest.mark.parametrize("arguments, expected", [
    ("app --user-data-dir=/p/s/ID/x", True),
    ("app --user-data-dir /p/s/ID", True),
    ('app "--user-data-dir=/p/s/ID/x"', True),
    ("app --user-data-dir='/p/s/ID/my data'", True),
    ("app --user-data-dir=/p/s/ID2", False),
    ("app --other=/p/s/ID", False),
])
def test_profile_directory_detection_matches_only_user_data_dir(arguments, expected):
    with patch.object(platform_tools.sys, "platform", "linux"):
        assert platform_tools.uses_profile_directory(arguments, PurePosixPath("/p/s/ID")) is expected


def test_profile_lock_refuses_a_second_holder(tmp_path):
    path = tmp_path / "locks" / "a.lock"
    with platform_tools.profile_lock(path):
        with pytest.raises(OSError, match="Close the terminal"), platform_tools.profile_lock(path):
            pass
    with platform_tools.profile_lock(path):
        pass  # released after the first holder left


def test_detached_explains_a_required_elevation():
    error = OSError(740, "elevation")
    error.winerror = 740
    with patch.object(platform_tools.subprocess, "Popen", side_effect=error), pytest.raises(OSError, match="administrator"):
        platform_tools.detached(["C:/x/app.exe"])
    with patch.object(platform_tools.subprocess, "Popen", side_effect=FileNotFoundError("x")), pytest.raises(FileNotFoundError):
        platform_tools.detached(["nope"])


def test_application_command_for_source_and_frozen_builds():
    assert platform_tools.application_command()[0] == platform_tools.sys.executable
    with patch.object(platform_tools.sys, "frozen", True, create=True):
        assert platform_tools.application_command() == [platform_tools.sys.executable]
    assert platform_tools.application_entry().name == "main.py"


def test_terminate_processes_skips_itself_and_reports_survivors():
    with (patch.object(platform_tools.sys, "platform", "linux"), patch.object(platform_tools.os, "kill") as kill,
          patch.object(platform_tools, "desktop_processes", return_value=[]),
          patch.object(platform_tools.signal, "SIGTERM", 15, create=True)):
        assert platform_tools.terminate_processes([platform_tools.os.getpid(), 4242]) == []
    assert [call.args[0] for call in kill.call_args_list] == [4242]


def test_powershell_failures_surface_as_subprocess_errors():
    with (patch.object(platform_tools.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "x")),
          patch.object(platform_tools.subprocess, "CREATE_NO_WINDOW", 0, create=True),
          pytest.raises(subprocess.CalledProcessError)):
        platform_tools.powershell("exit 1")
