from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from profile_switch import claude_links
from profile_switch.launch import Command
from profile_switch.store import Store


GOOGLE_LINK = "claude://login/google-auth?code=synthetic&hop_nonce=synthetic"


@pytest.mark.parametrize("state", ["moved", "current", "unregistered", "source"])
def test_launch_refreshes_only_an_existing_stale_portable_registration(state, monkeypatch):
    current = r"C:\New Folder\ai-profile-hub.exe"
    command = f'"{current}" --claude-link "%1"'
    registry = MagicMock(HKEY_CURRENT_USER=object(), REG_SZ=1, KEY_SET_VALUE=2)
    registry.OpenKey.side_effect = [MagicMock(), MagicMock(), MagicMock()]
    if state == "unregistered":
        registry.QueryValueEx.side_effect = FileNotFoundError
    else:
        registry.QueryValueEx.side_effect = [(claude_links.CAPABILITIES, registry.REG_SZ),
                                              (command if state == "current" else "old path", registry.REG_SZ)]
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(claude_links, "application_command", lambda: [sys.executable, "main.py"] if state == "source" else [current])
    notify = MagicMock()
    monkeypatch.setattr(claude_links, "_notify_handler_change", notify)
    monkeypatch.setattr(claude_links, "log_event", lambda event: None)

    claude_links.refresh_handler_command()

    if state == "moved":
        registry.OpenKey.assert_called_with(registry.HKEY_CURRENT_USER, claude_links.COMMAND_KEY, 0, registry.KEY_SET_VALUE)
        assert registry.SetValueEx.call_args.args[1:] == ("", 0, registry.REG_SZ, command)
        notify.assert_called_once_with()
    else:
        registry.SetValueEx.assert_not_called()
        notify.assert_not_called()
    registry.CreateKey.assert_not_called()


def test_sign_in_ticket_is_single_use_and_closing_discards_it(qtbot, tmp_path, monkeypatch):
    name = "ai-profile-hub-test-" + uuid4().hex
    forwarded = []
    monkeypatch.setattr(claude_links, "data_root", lambda: tmp_path)
    relay = claude_links.ClaudeSignInRelay(name, tmp_path / "claude-link.lock", lambda *args: forwarded.append(args))
    other = claude_links.ClaudeSignInRelay(name, tmp_path / "claude-link.lock", lambda *_: pytest.fail("Competing relay received a link"))
    profile_id = uuid4().hex
    now = 100
    monkeypatch.setattr(claude_links, "monotonic", lambda: now)
    def send():
        script = ("import sys; from PySide6.QtCore import QCoreApplication; "
                  "from profile_switch import claude_links; claude_links.log_event = lambda _: None; "
                  "app = QCoreApplication([]); print(claude_links.send_to_relay(*sys.argv[1:]).decode())")
        with subprocess.Popen([sys.executable, "-c", script, name, GOOGLE_LINK], stdout=subprocess.PIPE, text=True) as helper:
            qtbot.waitUntil(lambda: helper.poll() is not None, timeout=4000)
            return helper.communicate()[0].strip()

    try:
        assert relay.arm(profile_id)
        assert not other.arm(uuid4().hex)
        assert send() == "routed"
        assert forwarded == [(profile_id, GOOGLE_LINK)]
        assert send() == "fallback"
        assert relay.arm(profile_id)
        now += claude_links.SIGN_IN_SECONDS
        assert send() == "fallback"
        assert relay.arm(profile_id)
        relay.close()
        assert send() == "fallback"
        assert GOOGLE_LINK not in (tmp_path / "diagnostics" / "claude-links.log").read_text()
    finally:
        relay.close()
        other.close()


def test_only_google_return_uses_pending_profile(tmp_path, monkeypatch):
    store = Store(tmp_path / "hub")
    target = store.save("claude", "Synthetic A", "desktop")
    store.save("claude", "Synthetic B", "desktop")
    selected = []
    commands = []
    binary = Path("Claude.exe")
    monkeypatch.setattr(claude_links, "data_root", lambda: store.root)
    monkeypatch.setattr(claude_links, "server_name", lambda: "synthetic")
    def send(name, link):
        if selected:
            claude_links.forward_profile_link(store, selected.pop(), link)
            return b"routed"
        return b"fallback"
    monkeypatch.setattr(claude_links, "send_to_relay", send)
    monkeypatch.setattr(claude_links, "find_binary", lambda profile: binary)
    monkeypatch.setattr(claude_links, "local_command", lambda store, profile: Command(
        [str(binary), f"--user-data-dir={store.directory(profile) / 'claude-desktop'}"], {}, tmp_path))
    monkeypatch.setattr(claude_links, "start_claude_desktop", commands.append)

    selected.append(target)
    ordinary = "claude://claude.ai/new"
    claude_links.forward_link(ordinary)
    claude_links.forward_link(GOOGLE_LINK)
    claude_links.forward_link(GOOGLE_LINK)
    assert commands[0].argv == [str(binary), ordinary]
    assert commands[1].argv == [str(binary), f"--user-data-dir={store.directory(store.profile(target)) / 'claude-desktop'}", GOOGLE_LINK]
    assert commands[2].argv == [str(binary), GOOGLE_LINK]


def test_relay_failure_does_not_dispatch_the_link_to_another_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_links, "data_root", lambda: tmp_path)
    monkeypatch.setattr(claude_links, "server_name", lambda: "synthetic")
    monkeypatch.setattr(claude_links, "send_to_relay", lambda *args: b"failed")
    monkeypatch.setattr(claude_links, "find_binary", lambda *_: pytest.fail("Unexpected default launch"))
    with pytest.raises(OSError, match="could not be delivered"):
        claude_links.forward_link(GOOGLE_LINK)


@pytest.mark.parametrize("link", ["https://claude.ai/", 'claude://login/google-auth?code=" --login', "claude://"])
def test_invalid_link_is_rejected(link):
    with pytest.raises(ValueError, match="Invalid Claude link"):
        claude_links.parse_claude_link(link)
