"""Distribution replacement and failed-build regression checks."""

from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import build


@pytest.fixture
def build_workspace(tmp_path, monkeypatch):
    source = build.ROOT
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(source / name, tmp_path / name)
    shutil.copytree(source / 'docs' / 'licenses', tmp_path / 'docs' / 'licenses')
    (tmp_path / 'profile_switch').mkdir()
    (tmp_path / 'profile_switch' / '__init__.py').touch()
    shutil.copytree(source / 'profile_switch' / 'assets', tmp_path / 'profile_switch' / 'assets')
    monkeypatch.setattr(build, 'ROOT', tmp_path)
    monkeypatch.setattr(build.sys, 'argv', ['build.py'])
    return tmp_path


def test_repeated_build_replaces_same_complete_distribution(build_workspace, monkeypatch):
    root = build_workspace
    historical = root / 'dist' / 'native-builds' / 'historical'
    historical.mkdir(parents=True)
    (historical / 'keep.txt').write_text('historical evidence')

    def fake_deploy(command, **kwargs):
        if '--force' in command:
            stage = root / 'deployment' / 'native'
            package = stage / 'package'
            mode = command[command.index('--mode') + 1]
            config = build.configparser.ConfigParser()
            config.read(stage / 'pysidedeploy.spec')
            assert config['nuitka']['mode'] == mode
            if mode == 'onefile':
                (package / 'ai-profile-hub.exe').touch()
                assert '--include-data-dir=licenses=licenses' in config['nuitka']['extra_args']
                return
            package /= 'app.dist'
            if build.sys.platform == 'darwin':
                package = package / 'app.app' / 'Contents' / 'MacOS'
            package.mkdir(parents=True)
            (package / 'ai-profile-hub').touch()
            (package / 'bundled-runtime').write_text('synthetic runtime')

    monkeypatch.setattr(build.subprocess, 'run', fake_deploy)
    build.main()
    pointer = root / 'dist' / 'latest-native.txt'
    binary = Path(pointer.read_text())
    destination = root / 'setups' / 'ai-profile-hub'
    other_setup = destination.parent / 'another-setup.exe'
    other_setup.touch()
    (destination / 'obsolete.dll').touch()
    build.main()
    assert Path(pointer.read_text()) == binary
    assert binary.is_file()
    if build.sys.platform == 'win32':
        assert list(destination.iterdir()) == [destination / 'ai-profile-hub.exe']
    else:
        assert (binary.parent / 'bundled-runtime').is_file()
        assert (binary.parent / 'licenses' / 'PYTHON-LICENSE.txt').is_file()
        assert (binary.parent / 'LICENSE').is_file()
    assert not (destination / 'obsolete.dll').exists()
    assert other_setup.is_file()
    assert (historical / 'keep.txt').read_text() == 'historical evidence'
    assert [path.name for path in (root / 'deployment').iterdir()] == ['native']


def test_failed_build_preserves_previous_distribution(build_workspace, monkeypatch):
    root = build_workspace
    destination = root / 'setups' / 'ai-profile-hub'
    destination.mkdir(parents=True)
    (destination / 'previous.exe').write_text('previous working build')
    pointer = root / 'dist' / 'latest-native.txt'
    pointer.parent.mkdir()
    pointer.write_text('previous.exe')

    def fail_deploy(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(build.subprocess, 'run', fail_deploy)
    with pytest.raises(subprocess.CalledProcessError):
        build.main()
    assert (destination / 'previous.exe').read_text() == 'previous working build'
    assert pointer.read_text() == 'previous.exe'


def test_reset_refuses_unowned_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(build, 'ROOT', tmp_path)
    evidence = tmp_path / 'dist' / 'evidence'
    evidence.mkdir(parents=True)
    with pytest.raises(RuntimeError, match='unexpected build directory'):
        build.reset_build_directory(evidence)
    assert evidence.is_dir()
