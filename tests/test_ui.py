
"""Interaction and responsiveness tests with synthetic profiles and clients."""

from pathlib import Path
from threading import Event, get_ident
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent, QKeySequence
from PySide6.QtWidgets import QMessageBox, QPushButton

from profile_switch import codex_links, launch, ui
from profile_switch.qt_support import ElidedLabel, HeadingLabel
from profile_switch.transfer import Estimate, Plan, Report, Volume
from profile_switch.services import Availability, OperationResult, ProfileService
from profile_switch.launch import ClientRunningError
from profile_switch.store import Profile, Store


@pytest.fixture
def window(qtbot, tmp_path):
    store = Store(tmp_path / "synthetic data")
    store.save("claude", "Editorial review", "cli")
    store.save("chatgpt", "Research", "web")
    service = ProfileService(store)
    service.inspect = Mock(return_value=Availability(True, "Synthetic client available", "/synthetic/client"))
    widget = ui.Launcher(store, service)
    qtbot.addWidget(widget)
    widget.show()
    yield widget
    qtbot.waitUntil(lambda: not widget.busy and not widget.jobs)


def test_combined_filters_and_keyboard_find(window, qtbot):
    shortcut = QKeySequence(QKeySequence.StandardKey.Find)[0]
    qtbot.keyClick(window, shortcut.key(), modifier=shortcut.keyboardModifiers())
    assert window.search.hasFocus()
    qtbot.keyClicks(window.search, "review")
    assert window.proxy.rowCount() == 1
    window.kind_filter.setCurrentIndex(window.kind_filter.findData("web"))
    assert window.proxy.rowCount() == 0
    assert window.empty_notice.isVisible()
    window.clear_filters()
    assert window.proxy.rowCount() == 2
    assert not window.empty_notice.isVisible()


def test_tab_leaves_the_profile_table_in_both_directions(window, qtbot):
    window.resize(760, 560)
    window.show_profiles()
    qtbot.keyClick(window.windowHandle(), Qt.Key.Key_Down)
    assert window.selected()
    qtbot.keyClick(window.windowHandle(), Qt.Key.Key_Tab)
    assert window.details_button.hasFocus()
    qtbot.keyClick(window.windowHandle(), Qt.Key.Key_Tab, modifier=Qt.KeyboardModifier.ShiftModifier)
    assert window.table.hasFocus()
    qtbot.keyClick(window.windowHandle(), Qt.Key.Key_Tab, modifier=Qt.KeyboardModifier.ShiftModifier)
    assert window.focusWidget() is window.kind_filter


def test_browse_buttons_have_distinct_accessible_names(window):
    window.new_profile()
    editor = window.editor
    names = {control.accessibleName() for control in editor.local.findChildren(QPushButton)}
    assert names == {"Browse for executable", "Browse for working directory"}


def test_headings_and_current_destination_are_accessible(window):
    profiles = QAccessible.queryAccessibleInterface(window.profiles_nav)
    settings = QAccessible.queryAccessibleInterface(window.settings_nav)
    assert profiles.role() == settings.role() == QAccessible.Role.RadioButton
    assert profiles.state().checked and not settings.state().checked

    action = settings.actionInterface()
    action.doAction(action.pressAction())
    assert window.pages.currentWidget() is window.settings_page
    assert settings.state().checked and not profiles.state().checked
    action.doAction(action.pressAction())
    assert settings.state().checked

    window.new_profile()
    assert profiles.state().checked and not settings.state().checked
    heading = window.editor.findChild(HeadingLabel)
    accessible = QAccessible.queryAccessibleInterface(heading)
    assert accessible.role() == QAccessible.Role.Heading
    assert accessible.text(QAccessible.Text.Name) == "New profile"


def test_create_edit_validation_and_preserve_identity(window, qtbot):
    window.new_profile()
    editor = window.editor
    editor.name.setText("  New work  ")
    editor.save_button.click()
    qtbot.waitUntil(lambda: not window.busy)
    profile = window.selected()
    assert profile.name == "New work"
    assert window.pages.currentWidget() == window.profiles_page
    window.edit_profile()
    editor = window.editor
    assert not editor.product.isEnabled() and not editor.target.isEnabled()
    editor.name.setText("Renamed")
    editor.save_button.click()
    qtbot.waitUntil(lambda: not window.busy)
    assert window.selected().id == profile.id
    assert window.selected().name == "Renamed"
    window.new_profile()
    window.editor.name.clear()
    window.editor.save()
    assert "Enter a name" in window.editor.error.text()


def test_validation_failure_keeps_form_values(window, qtbot):
    window.new_profile()
    editor = window.editor
    editor.target.setCurrentIndex(editor.target.findData("cli"))
    editor.name.setText("Invalid path")
    editor.advanced.setChecked(True)
    editor.binary.setText("relative/client")
    editor.advanced.setChecked(False)
    editor.save()
    qtbot.waitUntil(lambda: not window.busy)
    assert window.pages.currentWidget() == editor
    assert editor.name.text() == "Invalid path"
    assert "absolute path" in editor.error.text()
    assert editor.local.isVisible() and editor.binary.hasFocus()
    assert editor.binary.accessibleDescription() == editor.error.text()
    assert editor.save_button.isEnabled()


def test_errors_expose_and_announce_the_message(window, monkeypatch):
    announcements = []

    def record_event(event):
        if isinstance(event, QAccessibleAnnouncementEvent):
            announcements.append(event.message())

    monkeypatch.setattr(QAccessible, "updateAccessibility", record_event)
    window.new_profile()
    editor = window.editor
    editor.save()
    message = editor.error.text()
    assert editor.name.accessibleDescription() == message
    assert QAccessible.queryAccessibleInterface(editor.error).text(QAccessible.Text.Name) == message
    window.report_error(ValueError("Synthetic operation error."))
    banner = window.error_message
    assert QAccessible.queryAccessibleInterface(banner).text(QAccessible.Text.Name) == banner.text()
    assert announcements == [message, banner.text()]


def test_background_batch_remains_responsive_and_retries_only_failures(window, qtbot):
    entered, release = Event(), Event()
    main_thread = get_ident()
    profiles = list(window.model.profiles)
    calls = []
    def launch(selected, login):
        assert get_ident() != main_thread
        calls.append([p.id for p in selected])
        entered.set()
        assert release.wait(5)
        return [OperationResult(p.id, p.name, p == profiles[0], "Synthetic result") for p in selected]
    window.service.launch = launch
    window.table.selectAll()
    window.launch()
    try:
        qtbot.waitUntil(entered.is_set)
        assert not window.open_button.isEnabled()
        window.search.setText("Research")
        assert window.proxy.rowCount() == 1
        window.show_settings()
        assert window.pages.currentWidget() == window.settings_page
        fired = []
        QTimer.singleShot(0, lambda: fired.append(True))
        qtbot.waitUntil(lambda: bool(fired))
    finally:
        release.set()
    qtbot.waitUntil(lambda: not window.busy)
    assert window.last_failed == [profiles[1].id]
    window.retry_failed()
    qtbot.waitUntil(lambda: not window.busy)
    assert set(calls[0]) == {p.id for p in profiles}
    assert calls[1] == [profiles[1].id]


def test_remove_preserves_unselected_profile(window, qtbot, monkeypatch):
    profile = window.model.profiles[0]
    window.select_id(profile.id)
    monkeypatch.setattr(ui.QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.remove_profile()
    qtbot.waitUntil(lambda: not window.busy)
    assert len(window.store.profiles()) == 1
    assert window.store.profiles()[0].id != profile.id


def test_incremental_refresh_preserves_selection_and_does_not_reset_model(window, qtbot):
    profile = window.model.profiles[0]
    window.select_id(profile.id)
    resets = []
    window.model.modelReset.connect(lambda: resets.append(True))
    window.store.save(profile.service, "Renamed", profile.mode, previous=profile)
    window.refresh()
    assert window.selected().id == profile.id
    assert window.selected().name == "Renamed"
    assert resets == []


def test_narrow_details_and_settings_theme(window, qtbot):
    window.select_id(window.model.profiles[0].id)
    window.resize(800, 600)
    qtbot.waitUntil(lambda: window.details_button.isVisible())
    window.show_details()
    assert window.pages.currentWidget() == window.details_page
    assert window.inspector.isVisible()
    title = QAccessible.queryAccessibleInterface(window.detail_title)
    assert title.role() == QAccessible.Role.Heading
    assert title.text(QAccessible.Text.Name) == window.selected().name
    window.show_profiles()
    assert window.inspector.isHidden()
    window.resize(1220, 760)
    qtbot.waitUntil(lambda: window.inspector.isVisible())
    window.theme_combo.setCurrentText("Dark")
    assert window.store.setting("theme") == "Dark"
    window.theme_combo.setCurrentText("Light")


def test_thousand_profiles_filter_budget(window, qtbot, record_property):
    profiles = [Profile(f"{n:032x}", "claude" if n % 2 else "chatgpt", f"Synthetic profile {n:04}", "cli") for n in range(1000)]
    window.model.sync(profiles)
    start = perf_counter()
    window.search.setText("profile 099")
    window.product_filter.setCurrentIndex(window.product_filter.findData("claude"))
    qtbot.wait(1)
    duration = perf_counter() - start
    record_property("filter_ms", duration * 1000)
    assert window.proxy.rowCount() == 5
    assert duration < .15


def test_late_discovery_does_not_replace_new_selection(window, qtbot):
    entered, release = Event(), Event()
    original, second = window.model.profiles
    def inspect(profile):
        if profile.id == original.id:
            entered.set()
            assert release.wait(5)
        return Availability(True, "Client available", f"/synthetic/{profile.name}")
    window.service.inspect = inspect
    window.select_id(original.id)
    try:
        qtbot.waitUntil(entered.is_set)
        window.select_id(second.id)
        qtbot.waitUntil(lambda: window.detail_badge.text() == "Available")
    finally:
        release.set()
    qtbot.waitUntil(lambda: not window.jobs)
    assert f"/synthetic/{second.name}" in window.detail_executable.value.full_text()
    assert f"/synthetic/{original.name}" not in window.detail_executable.value.full_text()


@pytest.mark.parametrize("found", [True, False], ids=["found", "missing"])
def test_browser_auto_detection_reports_result(window, qtbot, tmp_path, monkeypatch, found):
    browser = tmp_path / "synthetic Chromium.exe"
    browser.write_bytes(b"MZ")
    browser.chmod(0o700)
    window.store.save_browser(Path("/synthetic/old-browser.exe"))
    monkeypatch.setattr(launch, "browser_candidates", lambda: iter([browser] if found else []))
    window.show_settings()
    window.browser_reset.click()
    assert window.browser_status.isVisible()
    assert window.browser_status.text() == "Checking…"
    qtbot.waitUntil(lambda: not window.busy)
    assert window.store.browser() is None
    assert window.browser_status.text() == ("Found" if found else "Not found")
    assert window.browser_label.text().startswith("Automatic detection")
    assert (browser.name if found else "Install Google Chrome or Chromium") in window.browser_label.text()
    assert window.browser_label.toolTip() == (str(browser) if found else "")


def test_browser_setting_error_leaves_checkable_state(window, qtbot, monkeypatch):
    window.show_settings()
    window.store.clear_browser = Mock(side_effect=OSError("Synthetic settings write failed"))
    window.browser_reset.click()
    qtbot.waitUntil(lambda: not window.busy)
    assert window.browser_status.text() == "Check failed"
    assert window.browser_reset.isEnabled()
    assert "Synthetic settings write failed" in window.error_message.text()


def test_close_stays_responsive_and_cancels_pending_discovery(window, qtbot):
    started, release = Event(), Event()
    queued, callbacks, ticks = [], [], []
    window.discovery.setMaxThreadCount(1)

    def inspect():
        started.set()
        assert release.wait(4)
        return "Late result"

    window.submit(inspect, callbacks.append, discovery=True)
    try:
        qtbot.waitUntil(started.is_set)
        window.submit(lambda: queued.append(True), callbacks.append, discovery=True)
        assert not window.close()
        assert window.isVisible()
        QTimer.singleShot(0, lambda: ticks.append(True))
        qtbot.waitUntil(lambda: bool(ticks))
    finally:
        release.set()

    qtbot.waitUntil(lambda: not window.isVisible())
    assert not window.close_timer.isActive()
    assert not window.jobs
    assert not queued and not callbacks


def test_empty_state_and_recoverable_error_stay_in_workspace(window, qtbot, monkeypatch):
    window.search.setText("No matching profile")
    assert window.empty_page.isVisible()
    assert not window.splitter.isVisible()
    assert window.reset_filters_button.isVisible()
    assert window.new_button.isVisible()
    assert not window.open_button.isVisible()
    window.reset_filters_button.click()
    assert window.splitter.isVisible()
    assert not window.reset_filters_button.isVisible()
    monkeypatch.setattr(ui.QMessageBox, "warning", lambda *a: pytest.fail("Routine errors must not open a modal"))
    window.show_settings()
    window.report_error(ValueError("Synthetic missing folder. Restore it and retry."))
    assert window.error_banner.isVisible()
    assert "Restore it" in window.error_message.text()


def test_five_second_operation_does_not_block_ui(window, qtbot):
    ticks = []
    timer = QTimer(window)
    timer.setInterval(50)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start()
    def operation():
        Event().wait(5)
    window.mutate("Synthetic five-second operation", operation, lambda _result: None)
    window.show_settings()
    qtbot.waitUntil(lambda: not window.busy, timeout=6500)
    timer.stop()
    assert len(ticks) >= 40
    assert window.pages.currentWidget() == window.settings_page


class AcceptingDialog:
    def __init__(self, *args):
        pass

    def exec(self):
        return ui.QDialog.DialogCode.Accepted

    def chosen(self):
        return ["mcp"]


def prepare_transfer(window, monkeypatch, free):
    monkeypatch.setattr(ui, "TransferDialog", AcceptingDialog)
    plan = Plan([Estimate("mcp", "MCP servers", 2, 2048)], [Volume(Path("D:/"), free, 1_000_000)])
    window.service.transfer_categories = Mock(return_value=[object()])
    window.service.transfer_plan = Mock(return_value=plan)
    window.service.transfer = Mock(return_value=Report())
    window.select_id(next(p.id for p in window.store.profiles() if p.service == "claude"))
    return plan


def test_transfer_shows_sizes_and_asks_before_copying(window, qtbot, monkeypatch):
    prepare_transfer(window, monkeypatch, free=50_000_000)
    shown = []

    def answer(box):
        shown.append(box.text())
        box.buttons()[0].click()

    monkeypatch.setattr(QMessageBox, "exec", answer)
    window.transfer_settings(ui.IMPORT)
    qtbot.waitUntil(lambda: window.service.transfer.called and not window.busy, timeout=5000)
    assert "Provider: Claude Code" in shown[0] and "MCP servers: 2 files, 2.0 KB" in shown[0]
    assert "47.7 MB free" in shown[0]
    assert window.service.transfer_plan.call_args.args[1:3] == (["mcp"], ui.IMPORT)


def test_transfer_declined_copies_nothing(window, qtbot, monkeypatch):
    prepare_transfer(window, monkeypatch, free=50_000_000)
    monkeypatch.setattr(QMessageBox, "exec", lambda box: box.buttons()[1].click())
    window.transfer_settings(ui.IMPORT)
    qtbot.waitUntil(lambda: window.service.transfer_plan.called and not window.busy, timeout=5000)
    assert not window.service.transfer.called


def test_transfer_is_blocked_when_the_disk_is_too_small(window, qtbot, monkeypatch):
    prepare_transfer(window, monkeypatch, free=1000)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args[2]))
    window.transfer_settings(ui.IMPORT)
    qtbot.waitUntil(lambda: bool(warned), timeout=5000)
    assert "1000 B free" in warned[0]
    assert not window.service.transfer.called


def test_badge_tone_follows_client_availability(window, qtbot):
    cli = next(p for p in window.model.profiles if p.mode == "cli")
    window.select_id(cli.id)
    qtbot.waitUntil(lambda: window.detail_badge.text() == "Available")
    assert window.detail_badge.property("tone") == "success"
    window.service.inspect = Mock(return_value=Availability(False, "Client not found", ""))
    window.service.invalidate()
    window.inspected_profile = None
    window.selection_changed()
    qtbot.waitUntil(lambda: window.detail_badge.text() == "Unavailable")
    assert window.detail_badge.property("tone") == "danger"


def test_experimental_badge_only_for_experimental_clients(window, qtbot):
    window.store.save("chatgpt", "Desktop", "desktop")
    window.refresh()
    desktop = next(p for p in window.model.profiles if p.mode == "desktop")
    cli = next(p for p in window.model.profiles if p.mode == "cli")
    window.select_id(desktop.id)
    assert not window.detail_experimental.isHidden()
    window.select_id(cli.id)
    assert window.detail_experimental.isHidden()


def test_more_menu_actions_track_the_selection(window, qtbot):
    window.table.clearSelection()
    window.selection_changed()
    assert not window.more_button.isEnabled()
    web = next(p for p in window.model.profiles if ui.TARGETS[p.service][p.mode].kind == "web")
    cli = next(p for p in window.model.profiles if p.mode == "cli")
    window.select_id(web.id)
    assert window.more_button.isEnabled() and window.refresh_action.isEnabled()
    assert not window.import_action.isEnabled() and not window.export_action.isEnabled()
    window.select_id(cli.id)
    assert window.import_action.isEnabled() and window.export_action.isEnabled()


def test_long_paths_are_shortened_but_keep_the_full_text(qtbot):
    path = "C:\\Users\\Someone\\AppData\\Local\\Vendor\\Application\\Sessions\\0123456789abcdef0123456789abcdef"
    shortened = ElidedLabel(path)
    qtbot.addWidget(shortened)
    shortened.resize(120, 20)
    shortened.show()
    assert shortened.full_text() == path and shortened.toolTip() == path
    assert shortened.text() != path and "\u2026" in shortened.text()


def test_busy_launch_shortcut_keeps_the_retry_mode(window, qtbot):
    window.last_login = True
    window.busy = True
    window.table.selectAll()
    window.launch()
    assert window.last_login is True
    window.busy = False


def test_retry_is_hidden_when_failed_profiles_are_removed(window, qtbot):
    window.last_failed = [window.model.profiles[0].id]
    window.retry_button.show()
    window.store.delete(window.model.profiles[0])
    window.removed()
    assert window.last_failed == []
    assert not window.retry_button.isVisible()


def test_editor_draft_is_kept_until_discard_is_confirmed(window, qtbot, monkeypatch):
    window.new_profile()
    window.editor.name.setText("Draft")
    answer = [QMessageBox.StandardButton.Cancel]
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: answer[0])
    window.focus_search()
    assert window.pages.currentWidget() == window.editor
    assert window.editor.name.text() == "Draft"
    answer[0] = QMessageBox.StandardButton.Discard
    window.show_profiles()
    assert window.pages.currentWidget() == window.profiles_page


def test_saved_profile_is_selected_after_find_and_new(window, qtbot):
    window.focus_search()
    window.new_profile()
    window.editor.name.setText("Fresh")
    window.editor.save_button.click()
    qtbot.waitUntil(lambda: not window.busy)
    assert window.selected() is not None and window.selected().name == "Fresh"
    assert window.open_button.isEnabled()


def test_multiple_selection_keeps_open_selected_and_skips_details(window):
    window.resize(760, 560)
    window.show_profiles()
    window.table.selectAll()
    assert window.open_button.text() == "Open selected"
    assert window.open_button.isEnabled()
    assert not window.details_button.isEnabled()
    window.show_details()
    assert window.pages.currentWidget() == window.profiles_page


def test_compact_details_shows_sign_in_failure_and_retry(window, qtbot):
    window.resize(760, 560)
    profile = window.model.profiles[0]
    window.select_id(profile.id)
    window.show_details()
    calls = []
    def launch(selected, login):
        calls.append(login)
        return [OperationResult(p.id, p.name, False, "Synthetic sign-in failure", "Try again") for p in selected]
    window.service.launch = launch
    window.launch(login=True)
    qtbot.waitUntil(lambda: not window.busy)
    assert window.pages.currentWidget() == window.details_page
    assert "Synthetic sign-in failure" in window.details_result.text()
    assert window.details_retry.isVisible() and window.details_retry.isEnabled()
    window.details_retry.click()
    qtbot.waitUntil(lambda: not window.busy)
    assert calls == [True, True]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_settings_scrolls_with_error_banner_at_minimum_size(window, theme):
    window.resize(760, 560)
    window.theme = "Light" if theme == "light" else "Dark"
    window.apply_appearance()
    window.show_settings()
    window.report_error(OSError("Synthetic " + "long recovery guidance " * 20))
    assert isinstance(window.settings_page, ui.QScrollArea)
    assert window.settings_page.horizontalScrollBar().maximum() == 0


def test_theme_selector_reverts_when_saving_fails(window, monkeypatch):
    window.show_settings()
    monkeypatch.setattr(window.store, "save_setting", Mock(side_effect=OSError("Synthetic write failure")))
    window.theme_combo.setCurrentText("Light")
    assert window.theme_combo.currentText() == window.theme
    assert "Synthetic write failure" in window.error_message.text()


def test_text_file_with_exe_suffix_is_not_an_executable(tmp_path, monkeypatch):
    fake, real = tmp_path / "fake.exe", tmp_path / "real.exe"
    fake.write_text("not a program")
    real.write_bytes(b"MZ\x90\x00")
    script = tmp_path / "client.cmd"
    script.write_text("@echo off")
    for path in (fake, real, script):
        path.chmod(0o700)
    monkeypatch.setattr(launch.sys, "platform", "win32")
    assert not launch.executable(fake)
    assert launch.executable(real)
    assert launch.executable(script)


class FakeRelay:
    """Records arming without opening a local socket or touching the registry."""

    def __init__(self, *args):
        self.armed = []
        self.cleanup = None

    def arm(self, profile_id, cleanup=None):
        self.armed.append(profile_id)
        self.cleanup = cleanup
        return True

    def close(self):
        pass


def saved(window, *args):
    return window.store.profile(window.store.save(*args))


def sign_in_result(profile, **fields):
    return OperationResult(profile.id, profile.name, True, "Sign-in requested.", **fields)


@pytest.fixture
def windows_sign_in(window, monkeypatch):
    """A Launcher that behaves as on Windows, with the handler and the relays replaced by fakes."""
    calls = SimpleNamespace(default_apps=[], created=[])
    monkeypatch.setattr(ui, "sys", SimpleNamespace(platform="win32", argv=[]))
    monkeypatch.setattr(ui, "ClaudeSignInRelay", FakeRelay)
    monkeypatch.setattr(codex_links, "CodexSignInRelay", FakeRelay)
    monkeypatch.setattr(ui, "server_name", lambda: "claude-test")
    monkeypatch.setattr(codex_links, "server_name", lambda: "codex-test")
    monkeypatch.setattr(ui.claude_links, "ensure_handler", lambda: calls.created.append("claude") or True)
    monkeypatch.setattr(codex_links, "ensure_handler", lambda: calls.created.append("codex") or True)
    monkeypatch.setattr(ui, "handler_selected", lambda: False)
    monkeypatch.setattr(codex_links, "handler_selected", lambda: False)
    monkeypatch.setattr(ui.claude_links, "open_default_apps", lambda: calls.default_apps.append("claude"))
    monkeypatch.setattr(codex_links, "open_default_apps", lambda: calls.default_apps.append("codex"))
    return calls


def test_claude_sign_in_arms_the_relay_and_points_to_default_apps(window, windows_sign_in):
    profile = saved(window, "claude", "Desktop account", "desktop")
    window.launch_finished([sign_in_result(profile)], claude_sign_in=True, login=True)
    assert window.claude_relay.armed == [profile.id]
    assert window.claude_relay.cleanup is ui.claude_links.unregister_handler
    assert windows_sign_in.default_apps == ["claude"]
    assert "CLAUDE link type" in window.result_text.text()
    assert window.codex_relay is None


def test_codex_sign_in_arms_the_relay_and_points_to_default_apps(window, windows_sign_in):
    profile = saved(window, "chatgpt", "Codex account", "desktop")
    window.launch_finished([sign_in_result(profile)], login=True)
    assert window.codex_relay.armed == [profile.id]
    assert window.codex_relay.cleanup is codex_links.unregister_handler
    assert windows_sign_in.default_apps == ["codex"]
    assert "CODEX and CHATGPT link types" in window.result_text.text()
    assert window.claude_relay is None


def test_selected_handler_skips_the_default_apps_hint(window, windows_sign_in, monkeypatch):
    monkeypatch.setattr(codex_links, "handler_selected", lambda: True)
    profile = saved(window, "chatgpt", "Codex account", "desktop")
    window.launch_finished([sign_in_result(profile)], login=True)
    assert window.codex_relay.armed == [profile.id]
    assert windows_sign_in.default_apps == []
    assert "Default apps" not in window.result_text.text()


def test_other_launches_arm_no_relay(window, windows_sign_in):
    cli = saved(window, "claude", "Terminal account", "cli")
    window.launch_finished([sign_in_result(cli)], login=True)
    plain = saved(window, "chatgpt", "Plain launch", "desktop")
    window.launch_finished([sign_in_result(plain)], login=False)
    assert window.claude_relay is None and window.codex_relay is None
    assert windows_sign_in.created == []


def running_result(profile):
    return OperationResult(profile.id, profile.name, False, "Already running.", processes=((4242, "Codex.exe"),))


def test_running_client_lists_processes_and_closes_only_after_yes(window, qtbot, monkeypatch):
    profile = saved(window, "chatgpt", "Codex account", "desktop")
    asked = []

    def question(_parent, title, text, *_buttons):
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(ui.QMessageBox, "question", question)
    window.service.close_client = Mock(return_value=[4242])
    window.service.launch = Mock(return_value=[sign_in_result(profile)])
    window.launch_finished([running_result(profile)], login=True)
    qtbot.waitUntil(lambda: window.service.launch.called and not window.busy, timeout=5000)
    assert "Codex.exe (PID 4242)" in asked[0] and "Unsaved work" in asked[0]
    window.service.close_client.assert_called_once_with(profile)
    assert window.service.launch.call_args.args[1] is True


def test_running_client_cancel_closes_nothing(window, qtbot, monkeypatch):
    profile = saved(window, "chatgpt", "Codex account", "desktop")
    monkeypatch.setattr(ui.QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    window.service.close_client = Mock()
    window.service.launch = Mock()
    window.launch_finished([running_result(profile)], login=True)
    assert not window.busy
    assert not window.service.close_client.called and not window.service.launch.called


@pytest.mark.parametrize("direction", [ui.IMPORT, ui.EXPORT])
def test_transfer_with_a_running_client_offers_to_close_and_does_not_copy(window, qtbot, monkeypatch, direction):
    prepare_transfer(window, monkeypatch, free=50_000_000)
    window.service.transfer_plan = Mock(side_effect=ClientRunningError("Client running.", [(4242, "Claude.exe")]))
    asked = []
    monkeypatch.setattr(ui.QMessageBox, "question",
                        lambda _p, _t, text, *_b: asked.append(text) or QMessageBox.StandardButton.Cancel)
    window.transfer_settings(direction)
    qtbot.waitUntil(lambda: bool(asked) and not window.busy, timeout=5000)
    assert "Claude.exe (PID 4242)" in asked[0]
    assert not window.service.transfer.called


def test_transfer_closes_the_client_after_yes_and_asks_to_start_again(window, qtbot, monkeypatch):
    prepare_transfer(window, monkeypatch, free=50_000_000)
    window.service.transfer_plan = Mock(side_effect=ClientRunningError("Client running.", [(4242, "Claude.exe")]))
    window.service.close_client = Mock(return_value=[4242])
    monkeypatch.setattr(ui.QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.transfer_settings(ui.IMPORT)
    qtbot.waitUntil(lambda: window.service.close_client.called and not window.busy, timeout=5000)
    assert "Start the transfer again" in window.statusBar().currentMessage()
    assert not window.service.transfer.called


def test_restore_links_removes_hub_handlers_and_opens_default_apps(window, qtbot, monkeypatch):
    calls = []
    monkeypatch.setattr(ui.claude_links, "unregister_handler", lambda: calls.append("claude"))
    monkeypatch.setattr(ui.codex_links, "unregister_handler", lambda: calls.append("codex"))
    monkeypatch.setattr(ui.claude_links, "open_default_apps_page", lambda: calls.append("settings"))
    window.restore_links_button.setEnabled(True)

    qtbot.mouseClick(window.restore_links_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.busy)

    assert calls == ["claude", "codex", "settings"]
    assert "Hub entries removed" in window.statusBar().currentMessage()


def test_restore_links_reports_errors(window, qtbot, monkeypatch):
    def fail():
        raise OSError("registry locked")

    monkeypatch.setattr(ui.claude_links, "unregister_handler", fail)
    window.restore_links_button.setEnabled(True)

    qtbot.mouseClick(window.restore_links_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.busy)

    assert "registry locked" in window.error_message.text()


def test_text_and_fixed_sizes_follow_a_larger_system_font(qapp):
    from PySide6.QtGui import QFont
    from profile_switch import qt_support
    original = QFont(qapp.font())
    try:
        qapp.setFont(QFont(original.family(), 21))
        qt_support.apply_theme(qapp, "Dark")
        assert qt_support.THEME["scale"] == 2.0
        assert qt_support.scaled(166) == 332
        assert "font-size: 21.0pt" in qapp.styleSheet() and "min-height: 56px" in qapp.styleSheet()
        qapp.setFont(QFont(original.family(), 8))
        qt_support.apply_theme(qapp, "Dark")
        assert qt_support.THEME["scale"] == 1.0 and qt_support.scaled(166) == 166
    finally:
        qapp.setFont(original)
        qt_support.apply_theme(qapp, "System")


def test_inspector_badges_wrap_and_nothing_is_clipped(window, qtbot):
    from PySide6.QtCore import QPoint
    window.resize(1100, 600)
    window.select_id(window.model.profiles[0].id)
    qtbot.waitUntil(lambda: window.inspector.isVisible() and window.selected() is not None)
    window.inspection_finished(window.inspect_generation, Availability(True, "ok", "/synthetic/client"))
    for badge in (window.detail_badge, window.detail_running, window.detail_experimental, window.detail_managed):
        badge.show()
    window.detail_folder.set_value("C:/Users/synthetic/AppData/Local/AIProfileSwitch/sessions/" + "a" * 32)
    window.inspector.setFixedWidth(260)
    qtbot.wait(50)
    width = window.inspector.width()
    for widget in (window.detail_badge, window.detail_running, window.detail_experimental, window.detail_managed,
                   window.detail_folder.copy_button):
        right = widget.mapTo(window.inspector, QPoint(widget.width(), 0)).x()
        assert right <= width, f"{widget.text()} is clipped at {right} of {width}"
    rows = {widget.mapTo(window.inspector, QPoint(0, 0)).y() for widget in
            (window.detail_badge, window.detail_running, window.detail_experimental, window.detail_managed)}
    assert len(rows) > 1  # four badges cannot share one 260 px row
