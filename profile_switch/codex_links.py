"""Windows Codex links and the short-lived handoff to a Hub profile."""

import os
import re
import subprocess
from urllib.parse import quote, urlsplit

from .claude_links import MAX_LINK_BYTES, ClaudeSignInRelay, _notify_handler_change, log_event, send_to_relay
from .launch import Command, client_environment, find_binary, local_command, start_chatgpt_desktop
from .platform_tools import application_command, windows_user_sid
from .store import Profile

APP_NAME = "AI Profile Hub Codex Links"
PROG_ID = "AIProfileHub.CodexLink"
SCHEMES = ("codex", "chatgpt")
CAPABILITIES = r"Software\AIProfileHub\CodexLinks\Capabilities"
REGISTERED_APPLICATIONS = r"Software\RegisteredApplications"
COMMAND_KEY = rf"Software\Classes\{PROG_ID}\shell\open\command"


def _handler_command(application):
    return subprocess.list2cmdline([*application, "--codex-link"]) + ' "%1"'


def register_handler():
    import winreg

    def set_value(key_path, name, value):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    classes = rf"Software\Classes\{PROG_ID}"
    set_value(classes, "", APP_NAME)
    set_value(classes, "URL Protocol", "")
    set_value(COMMAND_KEY, "", _handler_command(application_command()))
    set_value(CAPABILITIES, "ApplicationName", APP_NAME)
    set_value(CAPABILITIES, "ApplicationDescription", "Open Codex links and route a pending desktop sign-in.")
    for scheme in SCHEMES:
        set_value(CAPABILITIES + r"\URLAssociations", scheme, PROG_ID)
    set_value(REGISTERED_APPLICATIONS, APP_NAME, CAPABILITIES)
    _notify_handler_change()
    os.startfile("ms-settings:defaultapps?registeredAppUser=" + quote(APP_NAME))


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
    log_event("codex-handler-path-updated")


def handler_selected():
    """True when Hub is the default for every Codex link scheme."""
    import ctypes
    from ctypes import wintypes

    query = ctypes.windll.shlwapi.AssocQueryStringW
    query.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                      wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    query.restype = ctypes.c_long

    def selected(scheme):
        value = ctypes.create_unicode_buffer(256)
        length = wintypes.DWORD(len(value))
        # ASSOCF_IS_PROTOCOL, ASSOCSTR_PROGID
        return query(0x1000, 20, scheme, None, value, ctypes.byref(length)) == 0 and value.value == PROG_ID

    return all(selected(scheme) for scheme in SCHEMES)


def server_name():
    return "AIProfileHub.CodexLink.v1." + windows_user_sid()


def parse_codex_link(link):
    if len(link.encode("utf-8")) > MAX_LINK_BYTES or re.search(r'[\x00-\x20\x7f"\\]', link):
        raise ValueError("Invalid Codex link.")
    parsed = urlsplit(link)
    if parsed.scheme not in SCHEMES or not (parsed.netloc or parsed.path):
        raise ValueError("Invalid Codex link.")
    return parsed


class CodexSignInRelay(ClaudeSignInRelay):
    def accepts(self, link):
        parse_codex_link(link)
        return True


def forward_profile_link(store, profile_id, link):
    profile = store.profile(profile_id)
    if (profile.service, profile.mode) != ("chatgpt", "desktop"):
        raise ValueError("The Codex desktop profile is unavailable.")
    command = local_command(store, profile)
    start_chatgpt_desktop(Command([*command.argv, link], command.env, command.cwd))


def forward_link(link):
    log_event("codex-activation-received")
    parse_codex_link(link)
    outcome = send_to_relay(server_name(), link)
    if outcome == b"routed":
        return
    if outcome != b"fallback":
        raise OSError("The Codex link could not be delivered to Hub.")
    binary = find_binary(Profile("", "chatgpt", "", "desktop"))
    start_chatgpt_desktop(Command([str(binary), link], client_environment("chatgpt"), binary.parent))
    log_event("codex-default-dispatched")
