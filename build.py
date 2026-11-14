"""Build a standalone Qt package in a fresh, ignored staging directory."""

import argparse
import compileall
import configparser
from datetime import datetime, timezone
from importlib import metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
from uuid import uuid4

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='print the deployment command without compiling')
    args = parser.parse_args()
    if not compileall.compile_dir(ROOT / 'profile_switch', quiet=1):
        raise SystemExit('Python syntax check failed.')
    token = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6]
    stage = ROOT / 'dist' / 'native-builds' / token
    stage.mkdir(parents=True)
    for name in ('main.py', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'pysidedeploy.spec'):
        shutil.copy2(ROOT / name, stage / name)
    shutil.copytree(ROOT / 'profile_switch', stage / 'profile_switch', ignore=shutil.ignore_patterns('__pycache__'))
    windows_notices = os.name == 'nt' and sys.version_info[:3] == (3, 13, 17)
    ignored_notices = [] if windows_notices else ['windows']
    if os.name != 'nt' or metadata.version('PySide6') != '6.10.1':
        ignored_notices.append('qt-6.10.1')
    shutil.copytree(ROOT / 'docs' / 'licenses', stage / 'licenses',
                    ignore=shutil.ignore_patterns(*ignored_notices))
    python_license = next((path for path in (
        Path(sys.base_prefix) / 'LICENSE.txt',
        Path(sys.base_prefix) / 'LICENSE',
        Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt',
    ) if path.is_file()), None)
    if python_license is None:
        raise SystemExit('The build Python has no license file in its installation. Use a Python installation that includes its license.')
    shutil.copy2(python_license, stage / 'licenses' / 'PYTHON-LICENSE.txt')
    nuitka = metadata.distribution('Nuitka')
    nuitka_license = next((nuitka.locate_file(item) for item in nuitka.files or ()
                           if item.parent.name == 'licenses' and item.name == 'LICENSE.txt'
                           and item.parent.parent.name.endswith('.dist-info')), None)
    if nuitka_license is None or not nuitka_license.is_file():
        raise SystemExit('The Nuitka installation is missing its runtime license text.')
    shutil.copy2(nuitka_license, stage / 'licenses' / 'NUITKA-LICENSE.txt')
    config = configparser.ConfigParser()
    config.read(stage / 'pysidedeploy.spec')
    config['app']['project_dir'] = str(stage)
    config['app']['exec_directory'] = str(stage / 'package')
    config['python']['python_path'] = sys.executable
    config['nuitka']['extra_args'] += ' --report=compilation-report.xml'
    if sys.platform == 'win32':
        config['nuitka']['extra_args'] += ' --windows-console-mode=attach --msvc=latest'
    with (stage / 'pysidedeploy.spec').open('w', encoding='utf-8') as stream:
        config.write(stream)
    deploy = Path(sys.executable).parent / ('pyside6-deploy.exe' if os.name == 'nt' else 'pyside6-deploy')
    if not deploy.is_file():
        raise SystemExit('Install requirements-dev.txt in a virtual environment before building.')
    command = [str(deploy), '-c', str(stage / 'pysidedeploy.spec'), '--force', '--mode', 'standalone',
               '--keep-deployment-files', '--extra-ignore-dirs=tests,docs,dist,.venv']
    if args.dry_run:
        command.append('--dry-run')
    subprocess.run(command, cwd=stage, check=True)
    if args.dry_run:
        return
    package = stage / 'package'
    candidates = list(package.rglob('ai-profile-hub.exe' if os.name == 'nt' else 'ai-profile-hub'))
    if not candidates:
        raise SystemExit('Deployment did not produce the expected executable. Inspect the retained staging files.')
    binary = candidates[0]
    licenses = binary.parent / 'licenses'
    shutil.copytree(stage / 'licenses', licenses, dirs_exist_ok=True)
    for dependency in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6'):
        distribution = metadata.distribution(dependency)
        for item in distribution.files or ():
            if any('license' in part.lower() or 'copying' in part.lower() for part in item.parts):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    destination = licenses / dependency / Path(*item.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        destination = binary.parent / name
        if not destination.is_file():
            shutil.copy2(stage / name, destination)
    subprocess.run([str(binary), '--help'], check=True, timeout=30)
    print(f'Package executable: {binary}')
    (ROOT / 'dist' / 'latest-native.txt').write_text(str(binary), encoding='utf-8')


if __name__ == '__main__':
    main()
