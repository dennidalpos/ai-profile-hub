"""Shared entry point for the GUI and terminal sessions."""

import argparse
import sqlite3
import subprocess
import sys

from .launch import run_cli
from .store import Store, data_root

ERRORS = (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--claude-link":
        if sys.platform != "win32" or len(argv) != 2:
            return 2
        from PySide6.QtCore import QCoreApplication
        from .claude_links import forward_link, log_event
        app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
        try:
            forward_link(argv[1])
        except ERRORS as error:
            # The link can contain a one-time authorization code. Keep it out of diagnostics.
            log_event(f"activation-failed {type(error).__name__} winerror={getattr(error, 'winerror', None)}")
            return 1
        return 0
    parser = argparse.ArgumentParser(description="AI Profile Hub")
    parser.add_argument("--session", metavar="ID", help="open a CLI profile in the current terminal")
    parser.add_argument("--login", action="store_true", help="start the client's sign-in flow")
    parser.add_argument("--smoke-test", action="store_true", help="open and close the GUI to verify a native package")
    if sys.platform == "win32":
        parser.add_argument("--register-claude-links", action="store_true", help="add Hub to Windows Default apps for Claude links")
    options = parser.parse_args(argv)
    if getattr(options, "register_claude_links", False):
        from .claude_links import register_handler
        try:
            register_handler()
        except OSError as error:
            print(f"Could not register the Claude link handler: {error}", file=sys.stderr)
            return 1
        return 0
    if options.login and not options.session:
        parser.error("--login requires --session")
    if options.smoke_test and options.session:
        parser.error("--smoke-test cannot be combined with --session")
    if options.session:
        from .platform_tools import prepare_session_console
        prepare_session_console()
        try:
            store = Store(data_root())
            code = run_cli(store, store.profile(options.session), options.login)
            if not code:
                return 0
            print(f"The client exited with code {code}.", file=sys.stderr)
        except ERRORS as error:
            print(f"Error: {error}", file=sys.stderr)
            code = 1
        if sys.stdin is not None and sys.stdin.isatty():
            input("Press Enter to close.")
        return code
    from .ui import run
    return run(smoke_test=options.smoke_test)
