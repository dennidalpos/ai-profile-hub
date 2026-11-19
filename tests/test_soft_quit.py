"""Soft quit of one profile's desktop client: process tree selection and escalation without force kill."""

import subprocess
from unittest.mock import patch

import pytest

from profile_switch import platform_tools


@pytest.fixture
def win32():
    with (patch.object(platform_tools.sys, "platform", "win32"),
          patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True)):
        yield


def test_profile_process_tree_includes_descendants_of_matching_roots(win32):
    folder = r"C:\Hub\p1\desktop"
    rows = "\n".join([
        "10\t1\t" + rf'"C:\App\X.exe" --user-data-dir={folder}',
        "11\t10\t" + r'"C:\App\X.exe" --type=gpu',
        "12\t11\tcodex.exe app-server",
        "20\t1\t" + r'"C:\App\X.exe" --user-data-dir=C:\Hub\p2\desktop',
    ])
    with patch.object(platform_tools, "powershell", return_value=rows):
        assert platform_tools.profile_process_tree(folder) == [10, 11, 12]


def test_quit_processes_escalates_from_close_to_session_end_and_never_kills(win32):
    sent = []

    def alive(pids):
        return list(pids) if platform_tools.WM_ENDSESSION not in sent else []

    with (patch.object(platform_tools, "_signal_windows", side_effect=lambda pids, message, wparam=0: sent.append(message)),
          patch.object(platform_tools.time, "sleep"),
          patch.object(platform_tools.time, "monotonic", side_effect=iter(range(0, 1000, 3)))):
        assert platform_tools.quit_processes([5], alive, wait=5) == []
    assert sent[0] == platform_tools.WM_CLOSE and platform_tools.WM_ENDSESSION in sent


def test_quit_processes_reports_survivors_without_terminating(win32):
    with (patch.object(platform_tools, "_signal_windows"), patch.object(platform_tools.time, "sleep"),
          patch.object(platform_tools.time, "monotonic", side_effect=iter(range(0, 1000, 3))),
          patch.object(platform_tools.subprocess, "run") as run):
        assert platform_tools.quit_processes([5], lambda pids: list(pids), wait=5) == [5]
    assert not run.called
