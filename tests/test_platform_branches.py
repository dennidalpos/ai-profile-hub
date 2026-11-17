"""Windows branches of platform_tools, exercised on every platform with mocked system calls."""

import os
import subprocess
from unittest.mock import patch

import pytest

from profile_switch import platform_tools


@pytest.fixture
def win32():
    with (patch.object(platform_tools.sys, "platform", "win32"),
          patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True)):
        yield


def test_windows_user_sid_accepts_only_a_well_formed_sid():
    platform_tools.windows_user_sid.cache_clear()
    with patch.object(platform_tools, "powershell", return_value=" S-1-5-21-1-2-3-1001\n"):
        assert platform_tools.windows_user_sid() == "S-1-5-21-1-2-3-1001"
    platform_tools.windows_user_sid.cache_clear()
    with patch.object(platform_tools, "powershell", return_value="not a sid"):
        with pytest.raises(OSError, match="Windows user"):
            platform_tools.windows_user_sid()
    platform_tools.windows_user_sid.cache_clear()


def test_windows_process_listings_are_parsed(win32):
    with patch.object(platform_tools, "powershell", return_value="1\tClaude.exe\r\nbad line\r\nx\tNope\r\n2\tCodex.exe\r\n"):
        assert platform_tools.desktop_processes() == [(1, "Claude.exe", ""), (2, "Codex.exe", "")]
    with patch.object(platform_tools, "powershell", return_value="cmd one\ncmd two") as run:
        assert platform_tools.process_arguments() == "cmd one\ncmd two"
    assert "Win32_Process" in run.call_args.args[0]


def test_terminate_processes_uses_taskkill_on_windows_and_skips_self(win32):
    calls = []
    states = iter([[(5, "", "")], []])
    with (patch.object(platform_tools.subprocess, "run", side_effect=lambda cmd, **kw: calls.append(cmd)),
          patch.object(platform_tools, "desktop_processes", side_effect=lambda: next(states)),
          patch.object(platform_tools.time, "sleep")):
        assert platform_tools.terminate_processes([5, os.getpid()], wait=5) == []
    assert calls == [["taskkill", "/PID", "5", "/T", "/F"]]


@pytest.mark.skipif(os.name == "nt", reason="POSIX signals")
def test_terminate_processes_escalates_to_sigkill_on_posix():
    sent = []
    clock = iter(float(tick) for tick in range(1000))
    with (patch.object(platform_tools.os, "kill", side_effect=lambda pid, sig: sent.append((pid, sig))),
          patch.object(platform_tools, "desktop_processes", return_value=[(9, "", "")]),
          patch.object(platform_tools.time, "monotonic", side_effect=lambda: next(clock)),
          patch.object(platform_tools.time, "sleep")):
        assert platform_tools.terminate_processes([9], wait=6) == [9]
    assert sent[0] == (9, platform_tools.signal.SIGTERM)
    assert (9, platform_tools.signal.SIGKILL) in sent
