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
        _app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])  # keep alive for the event loop
        try:
            forward_link(argv[1])
        except ERRORS as error:
            # The link can contain a one-time authorization code. Keep it out of diagnostics.
            log_event(f"activation-failed {type(error).__name__} winerror={getattr(error, 'winerror', None)}")
            return 1
        return 0
    if argv and argv[0] == "--codex-link":
        if sys.platform != "win32" or len(argv) != 2:
            return 2
        from PySide6.QtCore import QCoreApplication
        from .claude_links import log_event
        from .codex_links import forward_link
        _app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])  # keep alive for the event loop
        try:
            forward_link(argv[1])
        except ERRORS as error:
            log_event(f"codex-activation-failed {type(error).__name__} winerror={getattr(error, 'winerror', None)}")
            return 1
        return 0
    parser = argparse.ArgumentParser(description="AI Profile Hub")
    parser.add_argument("--session", metavar="ID", help="open a CLI profile in the current terminal")
    parser.add_argument("--launch", metavar="ID", help="start a profile without opening the Hub window")
    parser.add_argument("--login", action="store_true", help="start the client's sign-in flow")
    parser.add_argument("--smoke-test", action="store_true", help="open and close the GUI to verify a native package")
    if sys.platform == "win32":
        parser.add_argument("--register-claude-links", action="store_true", help="add Hub to Windows Default apps for Claude links")
        parser.add_argument("--unregister-claude-links", action="store_true", help="remove the Hub handler for Claude links")
        parser.add_argument("--unregister-codex-links", action="store_true", help="remove the Hub handler for Codex links")
        parser.add_argument("--register-codex-links", action="store_true", help="add Hub to Windows Default apps for Codex links")
    options = parser.parse_args(argv)
    for flag, module in (("unregister_claude_links", "claude_links"), ("unregister_codex_links", "codex_links")):
        if getattr(options, flag, False):
            import importlib
            importlib.import_module(f"profile_switch.{module}").unregister_handler()
            return 0
    if getattr(options, "register_codex_links", False):
        from .codex_links import register_handler
        try:
            register_handler()
        except OSError as error:
            print(f"Could not register the Codex link handler: {error}", file=sys.stderr)
            return 1
        return 0
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
    if options.launch and (options.session or options.smoke_test or options.login):
        parser.error("--launch cannot be combined with other actions")
    if options.smoke_test and options.session:
        parser.error("--smoke-test cannot be combined with --session")
    if options.launch:
        from .services import ProfileService
        try:
            store = Store(data_root())
            result = ProfileService(store).launch([store.profile(options.launch)])[0]
        except ERRORS as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
        if not result.succeeded:
            print(f"{result.message} {result.recovery}".strip(), file=sys.stderr)
        return 0 if result.succeeded else 1
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
    from .migration import migrate_data_root
    migrate_data_root()  # only the window migrates: terminal and link starts can run beside an open Hub
    if sys.platform == "win32":
        from .claude_links import log_event
        from .platform_tools import USER_ENVIRONMENT_JOURNAL, restore_user_environment
        try:
            if restore_user_environment(data_root() / USER_ENVIRONMENT_JOURNAL):
                log_event("user-environment-restored")
        except OSError as error:
            log_event(f"user-environment-restore-failed {type(error).__name__}")
    from .ui import run
    return run(smoke_test=options.smoke_test)
