from pathlib import Path
from unittest.mock import patch

import pytest

from profile_switch import codex_links, launch, store


def database(tmp_path, service="chatgpt", mode="desktop"):
    data = store.Store(tmp_path / "s")
    return data, data.profile(data.save(service, "Work", mode))


def test_ensure_handler_registers_only_when_missing():
    with patch.object(codex_links, "registered", return_value=True), patch.object(codex_links, "register_handler") as register:
        assert codex_links.ensure_handler() is False
        register.assert_not_called()
    with patch.object(codex_links, "registered", return_value=False), patch.object(codex_links, "register_handler") as register:
        assert codex_links.ensure_handler() is True
        register.assert_called_once_with(open_settings=False)


def test_unregister_removes_the_hub_keys_and_logs():
    with (patch.object(codex_links, "unregister_handler_keys") as keys, patch.object(codex_links, "log_event") as log):
        codex_links.unregister_handler()
    keys.assert_called_once_with(codex_links.PROG_ID, codex_links.CAPABILITIES, codex_links.APP_NAME)
    log.assert_called_once_with("codex-handler-removed")


def test_profile_link_goes_only_to_a_codex_desktop_profile(tmp_path):
    data, profile = database(tmp_path)
    command = launch.Command(["codex", "--user-data-dir=x"], {"A": "1"}, tmp_path)
    with (patch.object(codex_links, "local_command", return_value=command),
          patch.object(codex_links, "start_chatgpt_desktop") as start):
        codex_links.forward_profile_link(data, profile.id, "codex://auth?code=1")
    assert start.call_args.args[0].argv == ["codex", "--user-data-dir=x", "codex://auth?code=1"]
    other = data.profile(data.save("claude", "Other", "desktop"))
    with pytest.raises(ValueError, match="unavailable"):
        codex_links.forward_profile_link(data, other.id, "codex://auth")


def test_forward_link_uses_the_relay_then_falls_back_to_the_default_app(tmp_path):
    client = tmp_path / "Codex.exe"
    with (patch.object(codex_links, "server_name", return_value="name"), patch.object(codex_links, "log_event"),
          patch.object(codex_links, "start_chatgpt_desktop") as start,
          patch.object(codex_links, "send_to_relay", return_value=b"routed")):
        codex_links.forward_link("codex://auth?code=1")
        start.assert_not_called()
    with (patch.object(codex_links, "server_name", return_value="name"), patch.object(codex_links, "log_event"),
          patch.object(codex_links, "send_to_relay", return_value=b"failed"), pytest.raises(OSError, match="delivered")):
        codex_links.forward_link("codex://auth?code=1")
    with (patch.object(codex_links, "server_name", return_value="name"), patch.object(codex_links, "log_event"),
          patch.object(codex_links, "send_to_relay", return_value=b"fallback"),
          patch.object(codex_links, "find_binary", return_value=client),
          patch.object(codex_links, "client_environment", return_value={}),
          patch.object(codex_links, "start_chatgpt_desktop") as start):
        codex_links.forward_link("codex://auth?code=1")
    assert start.call_args.args[0].argv == [str(client), "codex://auth?code=1"]
    with pytest.raises(ValueError):
        codex_links.forward_link("https://not-a-codex-link")


def test_relay_accepts_any_valid_codex_link():
    relay = codex_links.CodexSignInRelay("n", Path("l"), lambda *_: None)
    assert relay.accepts("codex://auth?code=1")
    with pytest.raises(ValueError):
        relay.accepts("javascript:alert(1)")
