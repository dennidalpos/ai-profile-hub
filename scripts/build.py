"""Build a self-contained Qt package at setups/ai-profile-hub."""

import argparse
import compileall
import configparser
from importlib import metadata
import os
from pathlib import Path
import re
import shutil
from struct import pack
import subprocess
import sys
import sysconfig
from tempfile import NamedTemporaryFile

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
REVIEWED_WINDOWS_PYTHON = (3, 13, 17)
REVIEWED_QT = '6.12.0'


def write_windows_icon(source, destination):
    """Render the shared SVG into a Windows icon with multiple sizes."""
    from PySide6.QtCore import QBuffer, QIODevice, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise ValueError(f'Invalid application icon: {source}')
    sizes = (16, 20, 24, 32, 40, 48, 64, 256)
    offset = 6 + 16 * len(sizes)
    entries, frames = [], []
    for size in sizes:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        with QPainter(image) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, 'PNG'):
            raise OSError(f'Could not render the {size}-pixel application icon.')
        frame = bytes(buffer.data())
        dimension = size % 256  # The ICO directory encodes 256 as zero.
        entries.append(pack('<BBBBHHII', dimension, dimension, 0, 0, 1, 32, len(frame), offset))
        frames.append(frame)
        offset += len(frame)
    destination.write_bytes(b''.join([pack('<HHH', 0, 1, len(sizes)), *entries, *frames]))


def verify_build_directory(path):
    allowed = (ROOT / 'deployment' / 'native', ROOT / 'setups' / 'ai-profile-hub')
    if path not in allowed or path.resolve() != ROOT.resolve() / path.relative_to(ROOT):
        raise RuntimeError(f'Refusing to replace an unexpected build directory: {path}')


def reset_build_directory(path):
    """Replace only the two fixed, generated build directories."""
    verify_build_directory(path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def publish_windows_executable(binary, destination):
    verify_build_directory(destination)
    destination.mkdir(parents=True, exist_ok=True)
    installed = destination / 'ai-profile-hub.exe'
    with NamedTemporaryFile(prefix='.ai-profile-hub-', suffix='.tmp', dir=destination, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copy2(binary, temporary)
        try:
            os.replace(temporary, installed)
        except PermissionError as error:
            raise SystemExit(f'Could not replace {installed}. Close any running copy and check write permissions. '
                             f'The compiled executable is available at {binary}.') from error
    finally:
        temporary.unlink(missing_ok=True)
    return installed


def package_version():
    """The single version source, read without importing the package."""
    text = (ROOT / 'profile_switch' / '__init__.py').read_text(encoding='utf-8')
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else 'unknown'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='print the deployment command without compiling')
    args = parser.parse_args()
    print(f'Building AI Profile Hub {package_version()}')
    if not compileall.compile_dir(ROOT / 'profile_switch', quiet=1):
        raise SystemExit('Python syntax check failed.')
    stage = ROOT / 'deployment' / 'native'
    reset_build_directory(stage)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, stage / name)
    for name in ('main.py', 'pysidedeploy.spec'):
        shutil.copy2(SCRIPTS / name, stage / name)
    shutil.copytree(ROOT / 'profile_switch', stage / 'profile_switch', ignore=shutil.ignore_patterns('__pycache__'))
    ignored_notices = ['pdf']
    if os.name == 'nt':
        if sys.version_info[:3] != REVIEWED_WINDOWS_PYTHON:
            # The bundled notices describe the reviewed CPython build. Ship them anyway
            # rather than omit required texts, and flag that the versions need review.
            print('Warning: Windows component notices were reviewed for Python '
                  f'{".".join(map(str, REVIEWED_WINDOWS_PYTHON))}, not {sys.version.split()[0]}. '
                  'Review THIRD_PARTY_NOTICES.md before distributing this build.', file=sys.stderr)
    else:
        ignored_notices.append('windows')
    if os.name != 'nt':
        ignored_notices.append('qt-6.12.0')
    elif metadata.version('PySide6_Essentials') != REVIEWED_QT:
        # The Qt component inventory describes the reviewed release. Ship it anyway
        # rather than omit required texts, and flag that the inventory needs review.
        print(f'Warning: the Qt component notices were reviewed for {REVIEWED_QT}, not '
              f'{metadata.version("PySide6_Essentials")}. Compare them with the new package '
              'inventory and update THIRD_PARTY_NOTICES.md before distributing this build.', file=sys.stderr)
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
    # Nuitka 4 licenses its runtime under AGPLv3 with a Runtime Library Exception that
    # permits conveying the compiled program. Ship all three texts with the package.
    for name, target in (('LICENSE.txt', 'NUITKA-LICENSE.txt'), ('LICENSE-RUNTIME.txt', 'NUITKA-RUNTIME-LICENSE.txt'),
                         ('NOTICE.txt', 'NUITKA-NOTICE.txt')):
        source = next((nuitka.locate_file(item) for item in nuitka.files or ()
                       if item.parent.name == 'licenses' and item.name == name
                       and item.parent.parent.name.endswith('.dist-info')), None)
        if source is None or not source.is_file():
            raise SystemExit(f'The Nuitka installation is missing its license text {name}.')
        shutil.copy2(source, stage / 'licenses' / target)
    licenses = stage / 'licenses'
    for dependency in ('PySide6_Essentials', 'PySide6_Addons', 'shiboken6'):
        distribution = metadata.distribution(dependency)
        for item in distribution.files or ():
            if any('license' in part.lower() or 'copying' in part.lower() for part in item.parts):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    destination = licenses / dependency / Path(*item.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    mode = 'onefile' if sys.platform == 'win32' else 'standalone'
    package = stage / 'package'
    package.mkdir()
    config = configparser.ConfigParser()
    config.read(stage / 'pysidedeploy.spec')
    config['app']['project_dir'] = str(stage)
    config['app']['exec_directory'] = str(package)
    config['python']['python_path'] = sys.executable
    config['nuitka']['mode'] = mode
    config['nuitka']['extra_args'] += ' --report=compilation-report.xml'
    if mode == 'onefile':
        # PySide6 looks for main.exe and renames it to the configured title.
        config['app']['title'] = 'ai-profile-hub'
        icon = stage / 'app.ico'
        write_windows_icon(stage / 'profile_switch' / 'assets' / 'app-icon.svg', icon)
        config['app']['icon'] = str(icon)
        config['nuitka']['extra_args'] += ' --windows-console-mode=attach --msvc=latest --include-data-dir=licenses=licenses'
    else:
        config['nuitka']['extra_args'] += ' --output-filename=ai-profile-hub'
    with (stage / 'pysidedeploy.spec').open('w', encoding='utf-8') as stream:
        config.write(stream)
    deploy = Path(sys.executable).parent / ('pyside6-deploy.exe' if os.name == 'nt' else 'pyside6-deploy')
    if not deploy.is_file():
        raise SystemExit('Install requirements-dev.txt in a virtual environment before building.')
    command = [str(deploy), '-c', str(stage / 'pysidedeploy.spec'), '--force', '--mode', mode,
               '--keep-deployment-files', '--extra-ignore-dirs=tests,docs,dist,.venv']
    if args.dry_run:
        command.append('--dry-run')
    subprocess.run(command, cwd=stage, check=True)
    if args.dry_run:
        return
    pattern = 'ai-profile-hub.exe' if mode == 'onefile' else '**/ai-profile-hub'
    candidates = [path for path in package.glob(pattern) if path.is_file()]
    if not candidates:
        raise SystemExit('Deployment did not produce the expected executable. Inspect the retained staging files.')
    if len(candidates) != 1:
        raise SystemExit('Deployment produced multiple executables; refusing to select a package.')
    binary = candidates[0]
    if mode == 'standalone':
        shutil.copytree(licenses, binary.parent / 'licenses', dirs_exist_ok=True)
        for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
            destination = binary.parent / name
            if not destination.is_file():
                shutil.copy2(stage / name, destination)
    subprocess.run([str(binary), '--help'], check=True, timeout=30)
    destination = ROOT / 'setups' / 'ai-profile-hub'
    if mode == 'onefile':
        binary = publish_windows_executable(binary, destination)
    else:
        reset_build_directory(destination)
        package_root = binary.parent
        if sys.platform == 'darwin':
            package_root = next(parent for parent in binary.parents if parent.suffix == '.app')
        target = destination / package_root.name if sys.platform == 'darwin' else destination
        shutil.copytree(package_root, target, dirs_exist_ok=True, symlinks=True)
        binary = target / binary.relative_to(package_root)
    print(f'Package executable: {binary}')
    pointer = ROOT / 'dist' / 'latest-native.txt'
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(binary), encoding='utf-8')


if __name__ == '__main__':
    main()
