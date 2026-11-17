"""Entry point branches of profile_switch.app, run on every platform by patching sys.platform."""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from profile_switch import app, claude_links, codex_links


@pytest.fixture
def win32():
    # A real QCoreApplication would collide with the QApplication of the UI tests.
    with patch.object(app.sys, "platform", "win32"), patch("PySide6.QtCore.QCoreApplication"):
        yield


@pytest.mark.parametrize("flag", ["--claude-link", "--codex-link"])
def test_link_flag_needs_windows_and_one_url(flag):
    with patch.object(app.sys, "platform", "linux"):
        assert app.main([flag, "x://y"]) == 2
    with patch.object(app.sys, "platform", "win32"):
        assert app.main([flag]) == 2
        assert app.main([flag, "a", "b"]) == 2


@pytest.mark.parametrize("flag, module, event", [("--claude-link", claude_links, "activation-failed"),
                                                 ("--codex-link", codex_links, "codex-activation-failed")])
def test_link_flag_forwards_and_reports(win32, flag, module, event):
    with patch.object(module, "forward_link") as forward, patch.object(claude_links, "log_event") as log:
        assert app.main([flag, "secret://code"]) == 0
        forward.assert_called_once_with("secret://code")
        forward.side_effect = OSError("boom")
        assert app.main([flag, "secret://code"]) == 1
    message = log.call_args.args[0]
    assert message.startswith(event) and "secret" not in message


def test_register_and_unregister_flags(win32):
    with patch.object(claude_links, "unregister_handler") as claude, patch.object(codex_links, "unregister_handler") as codex:
        assert app.main(["--unregister-claude-links"]) == 0
        assert app.main(["--unregister-codex-links"]) == 0
    claude.assert_called_once_with()
    codex.assert_called_once_with()
    for flag, module in (("--register-claude-links", claude_links), ("--register-codex-links", codex_links)):
        with patch.object(module, "register_handler") as register:
            assert app.main([flag]) == 0
            register.assert_called_once_with()
        with patch.object(module, "register_handler", side_effect=OSError("denied")):
            assert app.main([flag]) == 1


@pytest.mark.parametrize("argv", [["--login"], ["--smoke-test", "--session", "x"]])
def test_invalid_option_combinations_exit(argv):
    with pytest.raises(SystemExit) as info:
        app.main(argv)
    assert info.value.code == 2


def test_session_runs_client_and_reports_exit_code(capsys):
    store = MagicMock()
    with (patch.object(app, "Store", return_value=store), patch.object(app, "data_root"),
          patch("profile_switch.platform_tools.prepare_session_console"),
          patch.object(app, "run_cli", return_value=0) as run_cli):
        assert app.main(["--session", "p1", "--login"]) == 0
    run_cli.assert_called_once_with(store, store.profile.return_value, True)
    with (patch.object(app, "Store", return_value=store), patch.object(app, "data_root"),
          patch("profile_switch.platform_tools.prepare_session_console"),
          patch.object(app, "run_cli", return_value=3), patch.object(app.sys, "stdin", None)):
        assert app.main(["--session", "p1"]) == 3
    assert "exited with code 3" in capsys.readouterr().err


def test_session_error_waits_for_enter_on_a_terminal(capsys):
    stdin = MagicMock()
    stdin.isatty.return_value = True
    with (patch.object(app, "Store", side_effect=sqlite3.Error("bad")), patch.object(app, "data_root"),
          patch("profile_switch.platform_tools.prepare_session_console"),
          patch.object(app.sys, "stdin", stdin), patch("builtins.input") as prompt):
        assert app.main(["--session", "p1"]) == 1
    prompt.assert_called_once()
    assert "Error: bad" in capsys.readouterr().err


def test_gui_start_restores_environment_on_windows(win32, tmp_path):
    with (patch.object(app, "data_root", return_value=tmp_path), patch("profile_switch.ui.run", return_value=0) as run,
          patch("profile_switch.platform_tools.restore_user_environment", return_value=True),
          patch.object(claude_links, "log_event") as log):
        assert app.main(["--smoke-test"]) == 0
        log.assert_called_once_with("user-environment-restored")
        run.assert_called_once_with(smoke_test=True)
    with (patch.object(app, "data_root", return_value=tmp_path), patch("profile_switch.ui.run", return_value=0),
          patch("profile_switch.platform_tools.restore_user_environment", side_effect=OSError("x")),
          patch.object(claude_links, "log_event") as log):
        assert app.main([]) == 0
        log.assert_called_once_with("user-environment-restore-failed OSError")
