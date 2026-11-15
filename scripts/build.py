"""Build a self-contained Qt package at setups/ai-profile-hub."""

import argparse
import compileall
import configparser
from importlib import metadata
import os
from pathlib import Path
import shutil
from struct import pack
import subprocess
import sys
import sysconfig
from tempfile import NamedTemporaryFile

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='print the deployment command without compiling')
    args = parser.parse_args()
    if not compileall.compile_dir(ROOT / 'profile_switch', quiet=1):
        raise SystemExit('Python syntax check failed.')
    stage = ROOT / 'deployment' / 'native'
    reset_build_directory(stage)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, stage / name)
    for name in ('main.py', 'pysidedeploy.spec'):
        shutil.copy2(SCRIPTS / name, stage / name)
    shutil.copytree(ROOT / 'profile_switch', stage / 'profile_switch', ignore=shutil.ignore_patterns('__pycache__'))
    windows_notices = os.name == 'nt' and sys.version_info[:3] == (3, 13, 17)
    ignored_notices = ['pdf']
    if not windows_notices:
        ignored_notices.append('windows')
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
    licenses = stage / 'licenses'
    for dependency in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6'):
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
