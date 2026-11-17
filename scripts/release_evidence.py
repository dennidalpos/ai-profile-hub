"""Write the inventory and SHA-256 checksums of a built package for release evidence.

Usage: python scripts/release_evidence.py PACKAGE_PATH [--output DIR] [--commit SHA]

PACKAGE_PATH is a single executable or a package directory. The script writes
`package-inventory.txt` and `SHA256SUMS` to the output directory (default
`dist/evidence`). SHA256SUMS lists every file in the format of `sha256sum -c`.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256_of(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def package_files(package):
    package = Path(package)
    if package.is_file():
        return package.parent, [package]
    if not package.is_dir():
        raise SystemExit(f'Package not found: {package}')
    files = sorted(path for path in package.rglob('*') if path.is_file() and not path.is_symlink())
    if not files:
        raise SystemExit(f'Package directory is empty: {package}')
    return package, files


def write_evidence(package, output, commit):
    base, files = package_files(package)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    entries = [(path.relative_to(base).as_posix(), path.stat().st_size, sha256_of(path)) for path in files]
    (output / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, _, digest in entries),
                                       encoding='utf-8', newline='\n')
    lines = [f'commit: {commit}', f'files: {len(entries)}', f'bytes: {sum(size for _, size, _ in entries)}', '']
    lines += [f'{size:>12}  {digest}  {name}' for name, size, digest in entries]
    (output / 'package-inventory.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return entries


def current_commit():
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else 'unknown'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('--output', default=str(ROOT / 'dist' / 'evidence'))
    parser.add_argument('--commit', default=None)
    args = parser.parse_args(argv)
    entries = write_evidence(args.package, args.output, args.commit or current_commit())
    print(f'Recorded {len(entries)} files in {args.output}')


if __name__ == '__main__':
    sys.exit(main())
