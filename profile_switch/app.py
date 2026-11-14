"""Shared entry point for the GUI and terminal sessions."""

import argparse
import sqlite3
import subprocess
import sys

from .launch import run_cli
from .store import Store, data_root

ERRORS = (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError)


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI Profile Hub")
    parser.add_argument("--session", metavar="ID", help="open a CLI profile in the current terminal")
    parser.add_argument("--login", action="store_true", help="start the client’s sign-in flow")
    options = parser.parse_args(argv)
    if options.login and not options.session:
        parser.error("--login requires --session")
    if options.session:
        try:
            store = Store(data_root())
            code = run_cli(store, store.profile(options.session), options.login)
            if not code:
                return 0
            print(f"Il client è uscito con codice {code}.", file=sys.stderr)
        except ERRORS as error:
            print(f"Errore: {error}", file=sys.stderr)
            code = 1
        if sys.stdin.isatty():
            input("Premi Invio per chiudere.")
        return code
    from .ui import run
    return run()
