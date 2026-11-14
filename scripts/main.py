"""Start AI Profile Hub from the source tree or the native build stage."""

from pathlib import Path
import sys

if __name__ == "__main__":
    # The native build stages this entry point beside the application package.
    if Path(__file__).resolve().parent.name == "scripts":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from profile_switch.app import main

    raise SystemExit(main())
