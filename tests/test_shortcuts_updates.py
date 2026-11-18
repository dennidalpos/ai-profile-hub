import json
import sys
from unittest.mock import patch

import pytest

from profile_switch import shortcuts, updates


def test_shortcut_name_is_a_safe_file_name():
    assert shortcuts.shortcut_name('a/b:c*"d') == "a-b-c--d"
    assert shortcuts.shortcut_name("...") == "AI Profile Hub"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launchers")
def test_shortcut_is_executable_never_overwrites_and_quotes_arguments(tmp_path):
    first = shortcuts.create_shortcut("My Hub", shortcuts.profile_arguments("a" * 32), tmp_path, ["/opt/hub app/run"])
    second = shortcuts.create_shortcut("My Hub", (), tmp_path, ["/opt/hub app/run"])
    assert first != second and first.exists() and second.exists()
    text = first.read_text(encoding="utf-8")
    assert "hub app/run" in text and "--launch" in text and ("a" * 32) in text
    assert first.stat().st_mode & 0o111


def test_windows_shortcut_passes_target_and_arguments_to_powershell(tmp_path):
    with patch.object(shortcuts.sys, "platform", "win32"), patch.object(shortcuts, "powershell") as run:
        path = shortcuts.create_shortcut("It's", ["--launch", "x y"], tmp_path, [r"C:\Hub\hub.exe"])
    script = run.call_args.args[0]
    assert path.suffix == ".lnk" and r"TargetPath = 'C:\Hub\hub.exe'" in script
    assert "'--launch \"x y\"'" in script and "It''s" in script


def test_manifest_selects_this_platforms_asset_and_compares_versions():
    digest = "a" * 64
    release = updates.parse_manifest(json.dumps({"version": "1.2.0", "assets": {
        "windows": {"url": "https://example.test/w.zip", "sha256": digest}}}))
    assert updates.update_available(release, "1.1.9", "win32")
    assert not updates.update_available(release, "1.2.0", "win32")
    assert not updates.update_available(release, "1.1.9", "linux")


@pytest.mark.parametrize("asset", [{"url": "http://x", "sha256": "a" * 64}, {"url": "https://x", "sha256": "zz"}])
def test_manifest_rejects_insecure_or_unverifiable_assets(asset):
    with pytest.raises(ValueError):
        updates.parse_manifest(json.dumps({"version": "1.0.0", "assets": {"linux": asset}}))
