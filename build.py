"""Compile-check and build the portable launcher without external dependencies."""

import compileall
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent


def main():
    output = ROOT / "dist" / "ai-profile-hub.pyz"
    output.parent.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        temp = Path(temporary)
        stage = temp / "app"
        stage.mkdir()
        for name in ("__main__.py", "LICENSE"):
            shutil.copy2(ROOT / name, stage / name)
        package_source = ROOT / "profile_switch"
        (stage / package_source.name).mkdir()
        for source in package_source.glob("*.py"):
            shutil.copy2(source, stage / package_source.name / source.name)
        if not compileall.compile_dir(stage, quiet=1):
            raise SystemExit("Python syntax check failed.")
        archive = temp / output.name
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
            for source in sorted(stage.rglob("*")):
                relative = source.relative_to(stage)
                if source.is_file() and "__pycache__" not in relative.parts:
                    # ZipInfo defaults to the ZIP epoch, independent of source mtimes.
                    entry = ZipInfo(relative.as_posix())
                    entry.create_system = 3
                    entry.external_attr = 0o100644 << 16
                    package.writestr(entry, source.read_bytes(), compress_type=ZIP_DEFLATED)
        subprocess.run([sys.executable, str(archive), "--help"], check=True, stdout=subprocess.DEVNULL)
        archive.replace(output)
    print(output)


if __name__ == "__main__":
    main()
