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


def signed(text):
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return (base64.b64encode(key.sign(text.encode("utf-8"))).decode(), base64.b64encode(public).decode())


def test_signed_manifest_is_loaded_and_tampering_or_a_missing_key_is_refused():
    text = json.dumps({"version": "1.2.0", "assets": {}})
    signature, public = signed(text)
    assert updates.load_manifest(text, signature, public).version == "1.2.0"
    with pytest.raises(ValueError):
        updates.load_manifest(text.replace("1.2.0", "9.9.9"), signature, public)
    with pytest.raises(ValueError):
        updates.load_manifest(text, "not base64!", public)
    with patch.object(updates, "UPDATE_PUBLIC_KEY", ""), pytest.raises(ValueError, match="signing key"):
        updates.load_manifest(text, signature)


def test_sign_manifest_script_round_trip(tmp_path, capsys):
    from scripts import sign_manifest
    private, manifest = tmp_path / "key", tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")
    assert sign_manifest.main(["keygen", str(private)]) == 0
    public = capsys.readouterr().out.strip()
    assert sign_manifest.main(["keygen", str(private)]) == 1  # never overwrites a key
    capsys.readouterr()
    assert sign_manifest.main(["sign", str(private), str(manifest)]) == 0
    signature = capsys.readouterr().out.strip()
    assert updates.load_manifest(manifest.read_text(encoding="utf-8"), signature, public).version == "1.0.0"
