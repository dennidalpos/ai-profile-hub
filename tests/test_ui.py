
"""Interaction and responsiveness tests with synthetic profiles and clients."""

from pathlib import Path
from threading import Event, get_ident
from time import perf_counter
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent, QKeySequence
from PySide6.QtWidgets import QMessageBox, QPushButton

from profile_switch import launch, ui
from profile_switch.qt_support import HeadingLabel
from profile_switch.services import Availability, OperationResult, ProfileService
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
    assert f"/synthetic/{second.name}" in window.detail_path.toPlainText()
    assert f"/synthetic/{original.name}" not in window.detail_path.toPlainText()


@pytest.mark.parametrize("found", [True, False], ids=["found", "missing"])
def test_browser_auto_detection_reports_result(window, qtbot, tmp_path, monkeypatch, found):
    browser = tmp_path / "synthetic Chromium.exe"
    browser.touch()
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
