import hashlib
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'release_evidence', Path(__file__).resolve().parent.parent / 'scripts' / 'release_evidence.py')
release_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_evidence)


def test_directory_checksums_match_sha256sum_format(tmp_path):
    package = tmp_path / 'pkg'
    (package / 'sub').mkdir(parents=True)
    (package / 'app').write_bytes(b'binary')
    (package / 'sub' / 'notes.txt').write_text('notice', encoding='utf-8')
    output = tmp_path / 'evidence'
    release_evidence.main([str(package), '--output', str(output), '--commit', 'abc123'])
    sums = (output / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()
    assert f'{hashlib.sha256(b"binary").hexdigest()}  app' in sums
    assert f'{hashlib.sha256(b"notice").hexdigest()}  sub/notes.txt' in sums
    inventory = (output / 'package-inventory.txt').read_text(encoding='utf-8')
    assert 'commit: abc123' in inventory and 'files: 2' in inventory


def test_single_file_package(tmp_path):
    exe = tmp_path / 'ai-profile-hub.exe'
    exe.write_bytes(b'exe')
    entries = release_evidence.write_evidence(exe, tmp_path / 'out', 'c')
    assert entries == [('ai-profile-hub.exe', 3, hashlib.sha256(b'exe').hexdigest())]


def test_missing_or_empty_package_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        release_evidence.package_files(tmp_path / 'missing')
    (tmp_path / 'empty').mkdir()
    with pytest.raises(SystemExit):
        release_evidence.package_files(tmp_path / 'empty')
