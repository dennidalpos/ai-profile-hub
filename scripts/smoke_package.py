"""Verify a native package against synthetic data and a harmless local CLI shim."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from profile_switch.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', nargs='?', type=Path)
    args = parser.parse_args()
    binary = (args.executable or Path('dist/latest-native.txt').read_text(encoding='utf-8-sig').strip())
    binary = Path(binary).resolve()
    root = (Path('dist/package-smoke') / uuid4().hex).resolve()
    root.mkdir(parents=True)
    env = os.environ.copy()
    env.update(LOCALAPPDATA=str(root / 'local'), XDG_DATA_HOME=str(root / 'xdg'),
               HOME=str(root / 'home'), AI_HUB_SMOKE_MARKER=str(root / 'client-marker.txt'))
    Path(env['HOME']).mkdir()
    if sys.platform == 'win32':
        data = Path(env['LOCALAPPDATA']) / 'AIProfileSwitch'
        shim = root / 'synthetic client.cmd'
        shim.write_text('@echo off\n> "%AI_HUB_SMOKE_MARKER%" echo %CLAUDE_CONFIG_DIR%\nexit /b 0\n', encoding='utf-8')
    else:
        data = (Path(env['HOME']) / 'Library/Application Support/AI Profile Switch' if sys.platform == 'darwin'
                else Path(env['XDG_DATA_HOME']) / 'ai-profile-switch')
        shim = root / 'synthetic client'
        shim.write_text('#!/bin/sh\nprintf "%s\\n" "$CLAUDE_CONFIG_DIR" > "$AI_HUB_SMOKE_MARKER"\n', encoding='utf-8')
        shim.chmod(0o700)
    store = Store(data)
    identifier = store.save('claude', 'Synthetic package smoke', 'cli', executable=str(shim), workdir=str(root))
    evidence = {'platform': sys.platform, 'binary': str(binary), 'checks': []}
    for name, arguments in [('help', ['--help']), ('GUI startup', ['--smoke-test']),
                            ('bundled CLI session', ['--session', identifier])]:
        result = subprocess.run([str(binary), *arguments], env=env, cwd=root, input='',
                                text=True, capture_output=True, timeout=60)
        evidence['checks'].append({'name': name, 'returncode': result.returncode,
                                   'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            raise RuntimeError(f'{name} failed: {result.stdout}\n{result.stderr}')
    marker = Path(env['AI_HUB_SMOKE_MARKER'])
    expected = store.directory(store.profile(identifier)) / 'claude-code'
    if not marker.exists() or Path(marker.read_text(encoding='utf-8').strip()) != expected:
        raise RuntimeError('The bundled CLI did not pass the isolated profile directory to the synthetic client.')
    evidence['profile_directory_verified'] = True
    report = root / 'report.json'
    report.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(f'Native package smoke passed. Evidence: {report}')


if __name__ == '__main__':
    main()
