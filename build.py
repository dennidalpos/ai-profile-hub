"""Compile-check and build the portable launcher without external dependencies."""

import compileall
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipapp


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
        shutil.copytree(ROOT / "profile_switch", stage / "profile_switch",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        if not compileall.compile_dir(stage, quiet=1):
            raise SystemExit("Python syntax check failed.")
        archive = temp / output.name
        zipapp.create_archive(stage, archive, compressed=True,
                              filter=lambda path: "__pycache__" not in path.parts)
        subprocess.run([sys.executable, str(archive), "--help"], check=True, stdout=subprocess.DEVNULL)
        archive.replace(output)
    print(output)


if __name__ == "__main__":
    main()
