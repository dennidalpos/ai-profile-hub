import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
from unittest.mock import patch

import pytest

from profile_switch import launch, platform_tools, services
from profile_switch.services import ProfileService
from profile_switch.store import Profile, Store


def test_windows_claude_desktop_sign_in_shows_the_email_code_flow(tmp_path):
    service = ProfileService(Store(tmp_path / 'hub'))
    profile = Profile('synthetic', 'claude', 'Work', 'desktop')
    with (patch.object(services.sys, 'platform', 'win32'), patch.object(services, 'open_profile') as launch_profile):
        sign_in, = service.launch([profile], login=True)
        opened, = service.launch([profile])
    assert sign_in.succeeded and 'Continue with email' in sign_in.message
    assert 'enter the code in this window' in sign_in.message
    assert opened.succeeded and 'Continue with email' not in opened.message
    launch_profile.assert_any_call(service.store, profile, True)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows standard handles')
def test_windows_powershell_works_with_invalid_parent_stdin():
    # Change the OS handle in an isolated process, not in the test runner.
    script = dedent('''
        from ctypes import WinDLL, wintypes
        from profile_switch.platform_tools import powershell

        kernel = WinDLL("kernel32", use_last_error=True)
        kernel.SetStdHandle.argtypes = (wintypes.DWORD, wintypes.HANDLE)
        kernel.SetStdHandle.restype = wintypes.BOOL
        assert kernel.SetStdHandle(wintypes.DWORD(-10), wintypes.HANDLE(0x12341234))
        print(powershell("Write-Output 'synthetic-powershell-ok'").strip())
    ''')
    result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True,
                            text=True, timeout=20, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'synthetic-powershell-ok'


def test_windows_cli_discovery_without_local_app_data(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    expected = tmp_path / "roaming" / "npm" / "codex.cmd"
    profile = Profile("synthetic", "chatgpt", "Work", "cli")
    with (patch.object(launch.sys, "platform", "win32"),
          patch.object(launch.Path, "home", return_value=tmp_path),
          patch.object(launch.shutil, "which", return_value=None),
          patch.object(launch, "executable", side_effect=lambda path: path == expected)):
        assert launch.find_binary(profile) == expected
        with pytest.raises(OSError, match="Client not found. Install it"):
            launch.find_binary(Profile("synthetic", "gemini", "Work", "cli"))


@pytest.mark.parametrize("argument", [
    '--user-data-dir="C:\\Data With Spaces\\sessions\\aaa\\browser"',
    '"--user-data-dir=C:/Data With Spaces/sessions/aaa/browser"',
    '--user-data-dir "c:/data with spaces/sessions/aaa/browser"',
    '--user-data-dir=C:/Data/../Data/sessions/aaa/browser',
])
def test_windows_process_paths(argument):
    folder = "C:/Data/sessions/aaa" if "With Spaces" not in argument and "with spaces" not in argument else "C:/Data With Spaces/sessions/aaa"
    with patch.object(platform_tools.sys, "platform", "win32"):
        assert platform_tools.uses_profile_directory('client.exe ' + argument, folder)


def test_unrelated_profile_and_case_sensitive_unix_paths():
    with patch.object(platform_tools.sys, "platform", "linux"):
        assert not platform_tools.uses_profile_directory('client --user-data-dir=/data/aaab/browser', '/data/aaa')
        assert not platform_tools.uses_profile_directory('client --user-data-dir=/Data/aaa/browser', '/data/aaa')
        assert platform_tools.uses_profile_directory('client --user-data-dir="/data/with spaces/aaa/browser"', '/data/with spaces/aaa')


def test_removal_refuses_normalized_active_path(tmp_path):
    store = Store(tmp_path / 'synthetic')
    profile = store.profile(store.save('claude', 'Synthetic', 'web'))
    folder = store.directory(profile)
    folder.mkdir(parents=True)
    state = folder / 'marker'
    state.touch()
    with patch('profile_switch.store.process_arguments', return_value=f'client --user-data-dir="{folder.as_posix()}/browser"'):
        with pytest.raises(OSError, match='Close all windows'):
            store.delete(profile)
    assert state.exists() and store.profile(profile.id) == profile


def test_google_inherited_credentials_removed_without_mutating_parent():
    overrides = {'GOOGLE_CLOUD_ACCESS_TOKEN': 'synthetic', 'GOOGLE_GENAI_USE_GCA': 'true',
                 'GOOGLE_GENAI_USE_VERTEXAI': 'true', 'GEMINI_CLI_USE_COMPUTE_ADC': 'true',
                 'CLOUD_SHELL': 'true', 'AGY_ADC_AUTH': 'true',
                 'GEMINI_CLI_AUTH_OVERRIDE': 'compute-default-credentials'}
    with patch.dict(os.environ, overrides):
        env = launch.client_environment('gemini')
        assert not set(overrides).intersection(env)
        assert os.environ['GOOGLE_CLOUD_ACCESS_TOKEN'] == 'synthetic'


def test_google_lowercase_adc_override_is_removed_on_unix():
    with patch.object(launch.os, 'environ', {'google_application_credentials': '/synthetic/adc.json'}):
        assert 'google_application_credentials' not in launch.client_environment('gemini')


@pytest.mark.parametrize('name', [
    'GOOGLE_GEMINI_BASE_URL', 'GOOGLE_VERTEX_BASE_URL', 'GEMINI_CLI_CUSTOM_HEADERS',
])
def test_google_gateway_conflict_blocks_launch_without_disclosing_value(name):
    value = 'synthetic-private-value'
    with patch.dict(os.environ, {name: value}):
        with pytest.raises(ValueError, match=name) as error:
            launch.client_environment('gemini')
        assert value not in str(error.value)
        assert os.environ[name] == value
        assert launch.client_environment('claude')[name] == value


@pytest.mark.parametrize('system', ['win32', 'darwin', 'linux'])
def test_google_profile_homes_isolate_adc_and_preserve_system_policy(tmp_path, system):
    policy = tmp_path / 'managed-settings.json'
    policy.write_text('{"security":{"auth":{"enforcedType":"oauth-personal"}}}', encoding='utf-8')
    policy_content = policy.read_bytes()
    store = Store(tmp_path / 'hub')
    parent = {'CLOUDSDK_CONFIG': str(tmp_path / 'external-credentials'),
              'GEMINI_CLI_SYSTEM_SETTINGS_PATH': str(policy),
              'GEMINI_CLI_SYSTEM_DEFAULTS_PATH': str(tmp_path / 'managed-defaults.json'),
              'GOOGLE_CLOUD_PROJECT': 'synthetic-managed-project'}
    with (patch.dict(os.environ, parent),
          patch.object(launch.sys, 'platform', system),
          patch.object(launch, 'find_binary', return_value=Path('/synthetic/client'))):
        commands = []
        for mode in ('gemini-cli', 'cli'):
            profile = store.profile(store.save('gemini', mode, mode, workdir=str(tmp_path)))
            command = launch.local_command(store, profile)
            home = store.directory(profile) / 'google-home'
            assert Path(command.env['HOME']) == home
            assert Path(command.env['GEMINI_CLI_HOME']) == home
            assert Path(command.env['CLOUDSDK_CONFIG']) == home / 'gcloud'
            if system == 'win32':
                assert Path(command.env['USERPROFILE']) == home
                assert Path(command.env['APPDATA']) == home / 'AppData' / 'Roaming'
            else:
                assert Path(command.env['XDG_CONFIG_HOME']) == home / 'config'
            for name in parent.keys() - {'CLOUDSDK_CONFIG'}:
                assert command.env[name] == parent[name]
            commands.append(command)
        assert commands[0].env['CLOUDSDK_CONFIG'] != commands[1].env['CLOUDSDK_CONFIG']
        assert os.environ['CLOUDSDK_CONFIG'] == parent['CLOUDSDK_CONFIG']
    assert policy.read_bytes() == policy_content


def test_frozen_terminal_reenters_executable_without_source_file():
    with patch.object(platform_tools.sys, 'frozen', True, create=True):
        assert platform_tools.application_command() == [platform_tools.sys.executable]


def test_nuitka_terminal_reenters_bundle_and_preserves_session_arguments(tmp_path):
    binary = tmp_path / 'AI Profile Hub' / 'ai-profile-hub.exe'
    with (patch.object(platform_tools, '__compiled__', object(), create=True),
          patch.object(platform_tools.sys, 'argv', [str(binary)]),
          patch.object(platform_tools, 'terminal_command', side_effect=lambda command: command),
          patch.object(platform_tools, 'detached') as spawn):
        platform_tools.open_terminal('a' * 32, login=True)
    assert spawn.call_args.args[0] == [str(binary.resolve()), '--session', 'a' * 32, '--login']


def test_discovery_cached_and_invalidated(tmp_path):
    store = Store(tmp_path / 'data')
    profile = store.profile(store.save('claude', 'Synthetic', 'cli'))
    service = ProfileService(store)
    with patch.object(services, 'find_binary', return_value=Path('/synthetic/client')) as detect:
        assert service.inspect(profile).available
        assert service.inspect(profile).available
        assert detect.call_count == 1
        service.invalidate()
        service.inspect(profile)
        assert detect.call_count == 2


def test_duo_link_is_idempotent_and_removal_preserves_original(tmp_path):
    from profile_switch import store as storage
    original = tmp_path / 'SecondProfile'
    original.mkdir()
    marker = original / 'synthetic-marker'
    marker.touch()
    store = Store(tmp_path / 'data')
    service = ProfileService(store)
    with patch.object(storage.sys, 'platform', 'win32'), patch.object(storage, 'duo_directory', return_value=original):
        identifier = service.link_duo()
        assert service.link_duo() == identifier
    store.delete(store.profile(identifier))
    assert marker.exists()


def test_detached_explains_windows_elevation_error():
    error = OSError(22, 'requires elevation')
    error.winerror = 740
    with patch.object(platform_tools.subprocess, 'Popen', side_effect=error):
        with pytest.raises(OSError, match='administrator rights.*app.exe'):
            platform_tools.detached(['C:/x/app.exe'])
    with patch.object(platform_tools.subprocess, 'Popen', side_effect=FileNotFoundError('missing')):
        with pytest.raises(FileNotFoundError):
            platform_tools.detached(['C:/x/app.exe'])


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX permission bits')
def test_private_directory_tightens_an_existing_loose_folder(tmp_path):
    folder = tmp_path / 'sessions'
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    platform_tools.private_directory(folder)
    assert folder.stat().st_mode & 0o777 == 0o700
