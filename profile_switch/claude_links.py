"""Windows Claude links and the short-lived handoff to a Hub profile."""

from contextlib import ExitStack
from datetime import datetime, timezone
import os
import re
import sqlite3
import subprocess
from time import monotonic
from urllib.parse import parse_qs, quote, urlsplit

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .launch import Command, client_environment, find_binary, local_command, start_claude_desktop
from .platform_tools import application_command, private_directory, profile_lock, windows_user_sid
from .store import Profile, data_root


APP_NAME = "AI Profile Hub Claude Links"
PROG_ID = "AIProfileHub.ClaudeLink"
CAPABILITIES = r"Software\AIProfileHub\ClaudeLinks\Capabilities"
REGISTERED_APPLICATIONS = r"Software\RegisteredApplications"
COMMAND_KEY = rf"Software\Classes\{PROG_ID}\shell\open\command"
SIGN_IN_SECONDS = 300
MAX_LINK_BYTES = 8192


def log_event(event):
    try:
        folder = data_root() / "diagnostics"
        private_directory(folder)
        with (folder / "claude-links.log").open("a", encoding="utf-8") as log:
            log.write(f"{datetime.now(timezone.utc).isoformat()} {event}\n")
    except (OSError, subprocess.SubprocessError):
        pass


def _handler_command(application):
    return subprocess.list2cmdline([*application, "--claude-link"]) + ' "%1"'


def _notify_handler_change():
    import ctypes

    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED


def registered(app_name, applications=REGISTERED_APPLICATIONS):
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, applications) as apps:
            winreg.QueryValueEx(apps, app_name)
        return True
    except FileNotFoundError:
        return False


def _delete_tree(root, path):
    import winreg

    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(root, path + "\\" + child)
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def unregister_handler_keys(prog_id, capabilities, app_name):
    """Remove a link handler registration that Hub created, leaving other applications untouched."""
    import winreg

    _delete_tree(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}")
    _delete_tree(winreg.HKEY_CURRENT_USER, capabilities.rsplit("\\", 1)[0])
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, capabilities.split("\\")[0] + "\\" + capabilities.split("\\")[1])
    except OSError:
        pass  # Still holds another Hub registration, or is already gone.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTERED_APPLICATIONS, 0, winreg.KEY_SET_VALUE) as apps:
            winreg.DeleteValue(apps, app_name)
    except FileNotFoundError:
        pass
    _notify_handler_change()


def unregister_handler():
    unregister_handler_keys(PROG_ID, CAPABILITIES, APP_NAME)
    log_event("handler-removed")


def open_default_apps():
    os.startfile("ms-settings:defaultapps?registeredAppUser=" + quote(APP_NAME))


def ensure_handler():
    """Register the handler for one sign-in. Returns True when Hub created it, False when it already existed."""
    if registered(APP_NAME):
        return False
    register_handler(open_settings=False)
    return True


def register_handler(open_settings=True):
    import winreg

    def set_value(key_path, name, value):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    classes = rf"Software\Classes\{PROG_ID}"
    set_value(classes, "", APP_NAME)
    set_value(classes, "URL Protocol", "")
    set_value(COMMAND_KEY, "", _handler_command(application_command()))
    set_value(CAPABILITIES, "ApplicationName", APP_NAME)
    set_value(CAPABILITIES, "ApplicationDescription", "Open Claude links and route a pending desktop sign-in.")
    set_value(CAPABILITIES + r"\URLAssociations", "claude", PROG_ID)
    set_value(REGISTERED_APPLICATIONS, APP_NAME, CAPABILITIES)
    _notify_handler_change()
    if open_settings:
        open_default_apps()


def refresh_handler_command():
    """Update an opted-in portable EXE's command without changing the user's default."""
    import winreg

    application = application_command()
    if len(application) != 1:  # Development runs leave the portable EXE registered.
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTERED_APPLICATIONS) as apps:
            if winreg.QueryValueEx(apps, APP_NAME) != (CAPABILITIES, winreg.REG_SZ):
                return
        command = _handler_command(application)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, COMMAND_KEY) as key:
            if winreg.QueryValueEx(key, "") == (command, winreg.REG_SZ):
                return
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, COMMAND_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
    except FileNotFoundError:
        return
    _notify_handler_change()
    log_event("handler-path-updated")


def handler_selected():
    import ctypes
    from ctypes import wintypes

    query = ctypes.windll.shlwapi.AssocQueryStringW
    query.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                      wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    query.restype = ctypes.c_long
    value = ctypes.create_unicode_buffer(256)
    length = wintypes.DWORD(len(value))
    # ASSOCF_IS_PROTOCOL, ASSOCSTR_PROGID
    return query(0x1000, 20, "claude", None, value, ctypes.byref(length)) == 0 and value.value == PROG_ID


def server_name():
    return "AIProfileHub.ClaudeLink.v2." + windows_user_sid()


class ClaudeSignInRelay:
    def __init__(self, name, lock_path, forward):
        self.server = QLocalServer()
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.deliver)
        self.name = name
        self.lock_path = lock_path
        self.lock = ExitStack()
        self.forward = forward
        self.pending = None
        self.cleanup = None
        self.timer = QTimer(self.server)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)

    def accepts(self, link):
        return is_google_return(parse_claude_link(link))

    def arm(self, profile_id, cleanup=None):
        self.cleanup = self.cleanup or cleanup
        if not self.server.isListening():
            try:
                self.lock.enter_context(profile_lock(self.lock_path))
            except OSError:
                return False
            if not self.server.listen(self.name):
                self.lock.close()
                return False
        self.pending = (profile_id, monotonic() + SIGN_IN_SECONDS)
        self.timer.start(SIGN_IN_SECONDS * 1000)
        log_event("sign-in-armed")
        return True

    def deliver(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.setReadBufferSize(MAX_LINK_BYTES + 1)
            socket.disconnected.connect(socket.deleteLater)
            socket.readyRead.connect(lambda socket=socket: self.receive(socket))
            QTimer.singleShot(15000, socket, socket.abort)
            self.receive(socket)

    def receive(self, socket):
        if not socket.canReadLine() or socket.property("handled"):
            return
        socket.setProperty("handled", True)
        result = b"failed"
        try:
            link = bytes(socket.readLine(MAX_LINK_BYTES + 2)).rstrip(b"\n").decode("utf-8")
            if self.accepts(link):
                ticket = self.pending
                self.close()
                result = b"fallback"
                if ticket and monotonic() < ticket[1]:
                    self.forward(ticket[0], link)
                    log_event("profile-dispatched")
                    result = b"routed"
        except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as error:
            log_event(f"profile-failed {type(error).__name__} winerror={getattr(error, 'winerror', None)}")
            result = b"failed"
        socket.write(result + b"\n")
        socket.flush()

    def close(self):
        self.pending = None
        self.timer.stop()
        self.server.close()
        self.lock.close()
        cleanup, self.cleanup = self.cleanup, None
        if cleanup:
            try:
                cleanup()
            except OSError as error:
                log_event(f"handler-cleanup-failed {type(error).__name__} winerror={getattr(error, 'winerror', None)}")


def send_to_relay(name, link):
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(1000):
        log_event("relay-unavailable")
        return b"fallback" if socket.error() == QLocalSocket.LocalSocketError.ServerNotFoundError else b"failed"
    socket.write(link.encode("utf-8") + b"\n")
    socket.flush()
    if socket.bytesToWrite():
        socket.waitForBytesWritten(1000)
    if not socket.canReadLine():
        socket.waitForReadyRead(12000)
    if not socket.canReadLine():
        log_event("relay-no-response")
        return b"failed"
    return bytes(socket.readLine(16)).rstrip(b"\r\n")


def parse_claude_link(link):
    if len(link.encode("utf-8")) > MAX_LINK_BYTES or not link.startswith("claude://") or re.search(r'[\x00-\x20\x7f"\\]', link):
        raise ValueError("Invalid Claude link.")
    parsed = urlsplit(link)
    if not parsed.netloc:
        raise ValueError("Invalid Claude link.")
    return parsed


def is_google_return(parsed):
    if parsed.netloc == "login" and parsed.path == "/google-auth" and not parsed.fragment:
        query = parse_qs(parsed.query, max_num_fields=32)
        return len(query.get("code", ())) == len(query.get("hop_nonce", ())) == 1
    return False


def forward_profile_link(store, profile_id, link):
    profile = store.profile(profile_id)
    if (profile.service, profile.mode) != ("claude", "desktop"):
        raise ValueError("The Claude Desktop profile is unavailable.")
    command = local_command(store, profile)
    start_claude_desktop(Command([*command.argv, link], command.env, command.cwd))


def forward_link(link):
    log_event("activation-received")
    parsed = parse_claude_link(link)
    if is_google_return(parsed):
        log_event("google-activation")
        outcome = send_to_relay(server_name(), link)
        if outcome == b"routed":
            return
        if outcome != b"fallback":
            raise OSError("The Google return could not be delivered to Hub.")
    binary = find_binary(Profile("", "claude", "", "desktop"))
    start_claude_desktop(Command([str(binary), link], client_environment("claude"), binary.parent))
    log_event("default-dispatched")
