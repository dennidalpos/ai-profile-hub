
"""Unified Qt desktop workspace for client-specific AI profiles."""

from dataclasses import replace
from pathlib import Path
import sys

from threading import Event

from PySide6.QtCore import QEvent, QItemSelectionModel, QSortFilterProxyModel, QThreadPool, QTimer, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTableView, QVBoxLayout, QWidget)

from .app import ERRORS
from .catalog import SERVICES, TARGETS
from . import claude_links, codex_links, shortcuts
from .claude_links import ClaudeSignInRelay, forward_profile_link, handler_selected, log_event, refresh_handler_command, server_name
from .launch import ClientRunningError, browser_path, executable
from .qt_support import (scaled, FlowLayout, NavigationButton, ProfileModel, ProgressRelay, StatusPillDelegate, Worker, apply_theme)
from .services import Availability, ProfileService
from .store import Store, data_root
from .transfer import EXPORT, IMPORT, TransferCancelled, format_size


APP_ICON = Path(__file__).with_name("assets") / "app-icon.svg"
from .ui_editor import ProfileEditor
from .ui_transfer import TransferDialog, TransferProgressDialog
from .ui_widgets import DetailRow, ProfileFilter, announce, button, label, section, set_badge, status_badge


class Launcher(QMainWindow):
    def __init__(self, store, service=None):
        super().__init__()
        self.store = store
        self.service = service or ProfileService(store)
        self.busy = False
        self.closing = False
        self.jobs = {}
        self.job_id = self.inspect_generation = 0
        self.inspected_profile = None
        self.last_failed = []
        self.last_login = False
        self.transfer_profile = None
        self.claude_relay = None
        self.codex_relay = None
        self.editor = None
        self.progress_dialog = None
        self.transfer_cancel = Event()
        self.transfer_total = self.transfer_size = 0
        self.progress_relay = ProgressRelay(self)
        self.progress_relay.changed.connect(self.show_progress)
        self.operations = QThreadPool(self)
        self.operations.setMaxThreadCount(1)
        self.discovery = QThreadPool(self)
        self.discovery.setMaxThreadCount(2)
        self.discovery_timer = QTimer(self)
        self.discovery_timer.setSingleShot(True)
        self.discovery_timer.setInterval(80)
        self.pending_inspection = None
        self.running_probe = False
        self.running_timer = QTimer(self)
        self.running_timer.setInterval(10000)
        self.running_timer.timeout.connect(self.refresh_running_if_visible)
        self.discovery_timer.timeout.connect(self.start_inspection)
        self.close_timer = QTimer(self)
        self.close_timer.setInterval(50)
        self.close_timer.timeout.connect(self.close)
        self.setWindowTitle("AI Profile Hub")
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1220, 760)
        self.setMinimumSize(760, 560)
        self.theme = store.setting("theme", "System")
        self.apply_appearance()
        QApplication.instance().styleHints().colorSchemeChanged.connect(self.system_theme_changed)
        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(scaled(166))
        navigation = QVBoxLayout(rail)
        navigation.setContentsMargins(16, 24, 16, 20)
        brand = label("AI Profile\nHub")
        brand.setObjectName("section")
        navigation.addWidget(brand)
        navigation.addSpacing(32)
        self.profiles_nav = NavigationButton("Profiles")
        self.profiles_nav.clicked.connect(self.show_profiles)
        self.settings_nav = NavigationButton("Settings")
        self.settings_nav.clicked.connect(self.show_settings)
        destinations = QButtonGroup(self)
        for nav in (self.profiles_nav, self.settings_nav):
            nav.setCheckable(True)
            destinations.addButton(nav)
            navigation.addWidget(nav)
        navigation.addStretch()
        navigation.addWidget(label("Web, terminal\nand desktop", muted=True))
        shell_layout.addWidget(rail)
        self.pages = QStackedWidget()
        self.pages.setObjectName("workspace")
        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        self.error_banner = QFrame()
        error_layout = QHBoxLayout(self.error_banner)
        self.error_message = label("")
        error_layout.addWidget(self.error_message, 1)
        error_layout.addWidget(button("Dismiss", self.error_banner.hide))
        self.error_banner.hide()
        workspace_layout.addWidget(self.error_banner)
        workspace_layout.addWidget(self.pages, 1)
        shell_layout.addWidget(workspace, 1)
        self.setCentralWidget(shell)
        self.build_profiles()
        self.build_settings()
        self.details_page = QWidget()
        details_layout = QVBoxLayout(self.details_page)
        details_layout.addWidget(button("Back to profiles", self.show_profiles), alignment=Qt.AlignmentFlag.AlignLeft)
        self.details_result = label("", muted=True)
        self.details_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_result_scroll = QScrollArea()
        self.details_result_scroll.setWidgetResizable(True)
        self.details_result_scroll.setWidget(self.details_result)
        self.details_result_scroll.setMaximumHeight(scaled(115))
        self.details_result_scroll.hide()
        details_layout.addWidget(self.details_result_scroll)
        self.details_retry = button("Retry failed", self.retry_failed)
        self.details_retry.hide()
        details_layout.addWidget(self.details_retry, alignment=Qt.AlignmentFlag.AlignLeft)
        self.pages.addWidget(self.details_page)
        self.statusBar().setSizeGripEnabled(False)
        self.shortcut("New profile", QKeySequence.StandardKey.New, self.new_profile)
        self.shortcut("Find profile", QKeySequence.StandardKey.Find, self.focus_search)
        self.shortcut("Open selection", "Return", self.open_from_keyboard)
        self.shortcut("Refresh detection", QKeySequence.StandardKey.Refresh, self.refresh_detection)
        self.refresh()
        self.show_profiles()
        self.running_timer.start()
        self.statusBar().showMessage("Select a profile to open it. Account identity is verified in the client.")

    def shortcut(self, name, key, callback):
        action = QAction(name, self)
        action.setShortcut(key)
        action.triggered.connect(callback)
        self.addAction(action)

    def apply_appearance(self):
        apply_theme(QApplication.instance(), self.theme)

    def system_theme_changed(self, _scheme):
        if self.theme == "System":
            self.apply_appearance()

    def build_profiles(self):
        self.profiles_page = QWidget()
        layout = QVBoxLayout(self.profiles_page)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        heading.setSpacing(12)
        heading.addWidget(label("Profiles", heading=True))
        heading.addWidget(label("Your accounts, ready in the client you choose.", muted=True), 1,
                          Qt.AlignmentFlag.AlignBottom)
        self.new_button = button("New profile", self.new_profile, True)
        heading.addWidget(self.new_button)
        layout.addLayout(heading)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search profiles")
        self.search.setAccessibleName("Search profiles")
        self.search.setClearButtonEnabled(True)
        self.product_filter = QComboBox()
        self.product_filter.setAccessibleName("Filter by product")
        self.product_filter.addItem("All products", "")
        for key, name in SERVICES.items():
            self.product_filter.addItem(name, key)
        self.kind_filter = QComboBox()
        self.kind_filter.setAccessibleName("Filter by client type")
        for name, value in (("All clients", ""), ("Web", "web"), ("Terminal", "cli"), ("Desktop", "desktop")):
            self.kind_filter.addItem(name, value)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.product_filter)
        filters.addWidget(self.kind_filter)
        layout.addLayout(filters)
        self.model = ProfileModel()
        self.proxy = ProfileFilter()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setAccessibleName("Profiles")
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setTabKeyNavigation(False)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(scaled(34))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setItemDelegateForColumn(ProfileModel.STATUS, StatusPillDelegate(self.table))
        for column, width in enumerate((180, 120, 170, 90, 90)):
            self.table.setColumnWidth(column, scaled(width))
        self.table.doubleClicked.connect(lambda _index: self.launch())
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        self.splitter = QSplitter()
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.table)
        self.inspector = QFrame()
        self.inspector.setObjectName("inspector")
        self.inspector.setMinimumWidth(scaled(280))
        self.inspector.setMaximumWidth(scaled(420))
        self.build_inspector()
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setSizes([650, 300])
        layout.addWidget(self.splitter, 1)
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.addStretch()
        self.empty_title = label("No matching profiles")
        self.empty_title.setObjectName("section")
        empty_layout.addWidget(self.empty_title)
        self.empty_notice = label("", muted=True)
        empty_layout.addWidget(self.empty_notice)
        empty_layout.addStretch()
        layout.addWidget(self.empty_page, 1)
        bottom = QHBoxLayout()
        self.count_label = label("", muted=True)
        bottom.addWidget(self.count_label)
        self.reset_filters_button = button("Clear filters", self.clear_filters, role="flat")
        bottom.addWidget(self.reset_filters_button)
        bottom.addStretch()
        self.details_button = button("Details", self.show_details)
        bottom.addWidget(self.details_button)
        self.open_button = button("Open profile", self.launch, True)
        bottom.addWidget(self.open_button)
        layout.addLayout(bottom)
        self.result_text = label("", muted=True)
        self.result_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result_scroll = QScrollArea()
        self.result_scroll.setWidgetResizable(True)
        self.result_scroll.setWidget(self.result_text)
        self.result_scroll.setMaximumHeight(scaled(115))
        self.result_scroll.hide()
        layout.addWidget(self.result_scroll)
        self.retry_button = button("Retry failed", self.retry_failed)
        self.retry_button.hide()
        layout.addWidget(self.retry_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.search.textChanged.connect(self.filter_profiles)
        self.product_filter.currentIndexChanged.connect(self.filter_profiles)
        self.kind_filter.currentIndexChanged.connect(self.filter_profiles)
        self.pages.addWidget(self.profiles_page)

    def build_inspector(self):
        outer = QVBoxLayout(self.inspector)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(8)
        self.detail_title = label("Select a profile", heading=True)
        self.detail_title.setObjectName("section")
        layout.addWidget(self.detail_title)
        self.detail_meta = label("Client and session details appear here.", muted=True)
        layout.addWidget(self.detail_meta)
        badges = FlowLayout(spacing=6)
        self.detail_badge = status_badge()
        self.detail_experimental = status_badge("Experimental", "warning")
        self.detail_managed = status_badge("Managed", "info")
        self.detail_running = status_badge("Running", "success")
        self.detail_running.hide()
        for badge in (self.detail_badge, self.detail_running, self.detail_experimental, self.detail_managed):
            badges.addWidget(badge)
        layout.addLayout(badges)
        self.detail_state = label("", muted=True)
        layout.addWidget(self.detail_state)
        self.detail_product = DetailRow("Product")
        self.detail_client = DetailRow("Client")
        self.detail_folder = DetailRow("Session folder", copy=True)
        self.detail_workdir = DetailRow("Working directory", copy=True)
        self.detail_executable = DetailRow("Executable", copy=True)
        self.detail_rows = (self.detail_product, self.detail_client, self.detail_folder, self.detail_workdir,
                            self.detail_executable)
        for row in self.detail_rows:
            layout.addWidget(row)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for text in (self.detail_title, self.detail_meta, self.detail_state):
            text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            text.setMinimumWidth(0)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(16, 6, 16, 14)
        footer.setSpacing(6)
        self.login_button = button("Sign in", lambda: self.launch(login=True))
        self.edit_button = button("Edit", self.edit_profile)
        self.edit_button.setAccessibleName("Edit profile")
        self.delete_button = button("Remove", self.remove_profile, role="danger")
        self.delete_button.setAccessibleName("Remove profile")
        self.more_button = QPushButton("More")
        self.more_button.setProperty("menu", True)
        menu = QMenu(self.more_button)
        self.refresh_action = menu.addAction("Refresh detection", self.refresh_detection)
        self.import_action = menu.addAction("Import settings from original…", lambda: self.transfer_settings(IMPORT))
        self.export_action = menu.addAction("Transfer settings to original…", lambda: self.transfer_settings(EXPORT))
        self.quit_action = menu.addAction("Quit this profile's client", self.quit_client)
        self.shortcut_action = menu.addAction("Create desktop shortcut", self.create_profile_shortcut)
        self.repair_action = menu.addAction("Repair imported sessions…", self.repair_sessions)
        self.more_button.setMenu(menu)
        for control in (self.login_button, self.edit_button, self.delete_button):
            footer.addWidget(control)
        footer.addStretch()
        footer.addWidget(self.more_button)
        outer.addLayout(footer)

    def build_settings(self):
        content = QWidget()
        self.settings_page = QScrollArea()
        self.settings_page.setWidgetResizable(True)
        self.settings_page.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_page.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(20)
        layout.addWidget(label("Settings", heading=True))
        layout.addWidget(section("Appearance"))
        self.theme_combo = QComboBox()
        self.theme_combo.setAccessibleName("Appearance")
        self.theme_combo.addItems(["System", "Light", "Dark"])
        self.theme_combo.setMaximumWidth(scaled(240))
        self.theme_combo.setCurrentText(self.theme)
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        layout.addWidget(self.theme_combo, alignment=Qt.AlignmentFlag.AlignLeft)
        browser_heading = QHBoxLayout()
        browser_heading.addWidget(section("Browser"))
        self.browser_status = status_badge("Not checked")
        browser_heading.addWidget(self.browser_status)
        browser_heading.addStretch()
        layout.addLayout(browser_heading)
        self.browser_label = label("", muted=True)
        self.browser_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.browser_label)
        browser_actions = QVBoxLayout()
        browser_actions.setSpacing(8)
        self.browser_choose = button("Choose Chrome or Chromium…", self.choose_browser)
        self.browser_reset = button("Use auto-detection", self.reset_browser)
        browser_actions.addWidget(self.browser_choose, alignment=Qt.AlignmentFlag.AlignLeft)
        browser_actions.addWidget(self.browser_reset, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(browser_actions)
        layout.addWidget(section("Desktop shortcut"))
        layout.addWidget(label("Add a shortcut to the desktop that opens AI Profile Hub.", muted=True))
        self.hub_shortcut_button = button("Create desktop shortcut", self.create_hub_shortcut)
        layout.addWidget(self.hub_shortcut_button, alignment=Qt.AlignmentFlag.AlignLeft)
        links_heading = section("Link handlers")
        links_note = label("Remove the AI Profile Hub entries for CLAUDE, CODEX and CHATGPT links so Windows returns them to the original apps, then open Default apps to confirm.", muted=True)
        self.restore_links_button = button("Restore original link handlers", self.restore_links)
        self.restore_links_button.setEnabled(sys.platform == "win32")
        layout.addWidget(links_heading)
        layout.addWidget(links_note)
        layout.addWidget(self.restore_links_button, alignment=Qt.AlignmentFlag.AlignLeft)
        # Link handlers are a Windows Default apps feature; other systems have nothing to restore.
        for widget in (links_heading, links_note, self.restore_links_button):
            widget.setVisible(sys.platform == "win32")
        layout.addStretch()
        layout.addWidget(label("Profiles store settings for one client each. Desktop isolation is experimental; verify the account in each client.", muted=True))
        self.pages.addWidget(self.settings_page)
        saved = self.store.browser()
        self.set_browser_details(f"Manual selection · {saved.name}" if saved else
                                 "Automatic detection looks for Chrome or Chromium.", saved)

    def set_browser_details(self, message, path):
        self.browser_label.setText(message)
        self.browser_label.setToolTip(str(path) if path else "")
        self.browser_label.setAccessibleDescription(str(path) if path else "")

    def change_theme(self, value):
        try:
            self.store.save_setting("theme", value)
        except ERRORS as error:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentText(self.theme)
            self.theme_combo.blockSignals(False)
            self.report_error(error)
            return
        self.theme = value
        self.apply_appearance()

    def leave_editor(self):
        """Ask before discarding unsaved editor values; True when navigation may continue."""
        if self.editor is None or self.pages.currentWidget() != self.editor or not self.editor.modified():
            return True
        reply = QMessageBox.question(self, "Discard changes?", "The profile has unsaved changes. Discard them?",
                                     QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        return reply == QMessageBox.StandardButton.Discard

    def show_profiles(self):
        if not self.leave_editor():
            self.profiles_nav.setChecked(False)
            return
        self.move_inspector()
        self.pages.setCurrentWidget(self.profiles_page)
        self.profiles_nav.setChecked(True)
        self.table.setFocus()

    def show_settings(self):
        if not self.leave_editor():
            self.settings_nav.setChecked(False)
            self.profiles_nav.setChecked(True)
            return
        self.pages.setCurrentWidget(self.settings_page)
        self.settings_nav.setChecked(True)

    def focus_search(self):
        self.show_profiles()
        self.search.setFocus()
        self.search.selectAll()

    def open_from_keyboard(self):
        if self.pages.currentWidget() == self.profiles_page and (self.table.hasFocus() or self.search.hasFocus()):
            self.launch()

    def show_details(self):
        if self.selected() is None:
            return
        self.details_page.layout().insertWidget(1, self.inspector, 1)
        self.details_result_scroll.hide()
        self.details_retry.hide()
        self.inspector.setMaximumWidth(16777215)
        self.inspector.show()
        self.pages.setCurrentWidget(self.details_page)

    def move_inspector(self):
        if self.inspector.parent() != self.splitter:
            self.splitter.addWidget(self.inspector)
        self.inspector.setMaximumWidth(scaled(420))
        self.inspector.setVisible(self.width() >= 1060 and self.proxy.rowCount() > 0)
        self.details_button.setVisible(self.width() < 1060 and self.proxy.rowCount() > 0)
        self.table.setColumnHidden(4, self.width() < 1060)
        self.update_status_column()

    def update_status_column(self):
        """The Status column only earns its width while some profile is running."""
        self.table.setColumnHidden(ProfileModel.STATUS, not self.model.running)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "inspector") and self.pages.currentWidget() != getattr(self, "details_page", None):
            self.move_inspector()

    def selection(self):
        return [self.proxy.data(index, Qt.ItemDataRole.UserRole)
                for index in self.table.selectionModel().selectedRows()]

    def selected(self):
        profiles = self.selection()
        return profiles[0] if len(profiles) == 1 else None

    def select_id(self, identifier):
        for row, profile in enumerate(self.model.profiles):
            if profile.id == identifier:
                index = self.proxy.mapFromSource(self.model.index(row, 0))
                if index.isValid():
                    self.table.selectionModel().select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect |
                                                      QItemSelectionModel.SelectionFlag.Rows)
                    self.table.setCurrentIndex(index)
                    self.table.scrollTo(index)
                break

    def watching(self):
        """False while the window is minimized or hidden, when nobody can see the pills."""
        return self.isVisible() and not self.isMinimized()

    def update_running_badge(self):
        profile = self.selected()
        self.detail_running.setVisible(profile is not None and profile.id in self.model.running)

    def refresh_running_if_visible(self):
        if self.watching():
            self.refresh_running()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.watching() and hasattr(self, "running_timer"):
            self.refresh_running()

    def refresh_running(self):
        """Probe in the background which profiles are running and show it as a pill in the table."""
        if self.closing or self.running_probe:
            return
        self.running_probe = True
        profiles = list(self.model.profiles)

        def finished(result):
            self.running_probe = False
            self.model.set_running(result)
            self.update_status_column()
            self.update_running_badge()

        def failed(_error):
            self.running_probe = False

        self.submit(lambda: self.service.running_profiles(profiles), finished, discovery=True, on_error=failed)

    def refresh(self, identifier=None):
        profiles = self.store.profiles()
        self.model.sync(profiles)
        self.refresh_running()
        if identifier:
            self.select_id(identifier)
        self.update_counts()
        self.selection_changed()

    def filter_profiles(self):
        self.proxy.beginFilterChange()
        self.proxy.query = self.search.text().strip().casefold()
        self.proxy.service = self.product_filter.currentData()
        self.proxy.kind = self.kind_filter.currentData()
        self.proxy.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        self.update_counts()
        self.selection_changed()

    def clear_filters(self):
        self.search.clear()
        self.product_filter.setCurrentIndex(0)
        self.kind_filter.setCurrentIndex(0)

    def update_counts(self):
        total, visible = self.model.rowCount(), self.proxy.rowCount()
        self.count_label.setText(f"{visible} of {total} profiles")
        filtered = bool(self.search.text() or self.product_filter.currentIndex() or self.kind_filter.currentIndex())
        self.reset_filters_button.setVisible(filtered)
        self.open_button.setVisible(bool(visible))
        self.splitter.setVisible(bool(visible))
        self.table.setVisible(bool(visible))
        self.empty_page.setVisible(not visible)
        self.empty_title.setText("No matching profiles" if total else "Add your first profile")
        if total:
            self.empty_notice.setText("Try a different search or clear the filters.")
        else:
            self.empty_notice.setText("Choose a product and client to create a separate session.")
        self.move_inspector()

    def selection_changed(self, *_args):
        profiles, profile = self.selection(), self.selected()
        if profile is not None and profile == self.inspected_profile:
            self.update_actions()
            return
        self.inspected_profile = profile
        self.inspect_generation += 1
        generation = self.inspect_generation
        if profile:
            target = TARGETS[profile.service][profile.mode]
            self.detail_title.setText(profile.name)
            self.detail_meta.hide()
            self.detail_product.set_value(SERVICES[profile.service])
            self.detail_client.set_value(target.label)
            self.detail_folder.set_value(str(self.store.directory(profile)))
            self.detail_workdir.set_value(profile.workdir)
            self.detail_executable.set_value("")
            set_badge(self.detail_badge, "Checking…", "warning")
            self.detail_badge.show()
            self.detail_experimental.setVisible(target.experimental)
            self.detail_managed.show()
            self.update_running_badge()
            self.detail_state.hide()
            self.pending_inspection = generation, profile
            self.discovery_timer.start()
        else:
            self.discovery_timer.stop()
            self.detail_title.setText(f"{len(profiles)} profiles selected" if profiles else "Select a profile")
            self.detail_meta.setText("Open the selected profiles together." if profiles else "Client and session details appear here.")
            self.detail_meta.show()
            for badge in (self.detail_badge, self.detail_running, self.detail_experimental, self.detail_managed):
                badge.hide()
            self.detail_state.hide()
            for row in self.detail_rows:
                row.set_value("")
        self.update_actions()

    def start_inspection(self):
        generation, profile = self.pending_inspection
        self.submit(lambda: self.service.inspect(profile),
                    lambda result: self.inspection_finished(generation, result), discovery=True,
                    on_error=lambda error: self.inspection_finished(generation, Availability(False, str(error)),
                                                                   failed=True))

    def inspection_finished(self, generation, result, failed=False):
        if generation != self.inspect_generation:
            return
        status = "Check failed" if failed else "Available" if result.available else "Unavailable"
        set_badge(self.detail_badge, status, "danger" if failed or not result.available else "success")
        self.detail_state.setText(f"{result.message}\n{result.recovery}" if not result.available else "")
        self.detail_state.setVisible(not result.available)
        if result.path:
            self.detail_executable.set_value(str(result.path))
        if self.detail_badge.isVisible():
            announce(self.detail_badge, result.message)

    def refresh_detection(self):
        if self.pages.currentWidget() == self.settings_page:
            self.check_browser()
            return
        if self.selected() is None:
            return
        self.service.invalidate()
        self.inspected_profile = None
        self.selection_changed()

    def update_actions(self):
        profiles, profile = self.selection(), self.selected()
        idle = not self.busy
        self.open_button.setText("Open selected" if len(profiles) > 1 else "Open profile")
        self.open_button.setEnabled(idle and bool(profiles))
        self.details_button.setEnabled(profile is not None)
        for control in (self.new_button, self.browser_choose, self.browser_reset):
            control.setEnabled(idle)
        local = profile is not None and TARGETS[profile.service][profile.mode].kind != "web"
        self.import_action.setEnabled(idle and local)
        self.export_action.setEnabled(idle and local)
        self.edit_button.setEnabled(idle and profile is not None)
        self.delete_button.setEnabled(idle and profile is not None)
        self.login_button.setEnabled(idle and profile is not None and TARGETS[profile.service][profile.mode].kind != "web")
        self.refresh_action.setEnabled(profile is not None)
        self.shortcut_action.setEnabled(idle and profile is not None)
        self.quit_action.setEnabled(idle and profile is not None and TARGETS[profile.service][profile.mode].kind == "desktop")
        self.repair_action.setEnabled(idle and profile is not None and profile.service == "chatgpt" and local)
        self.more_button.setEnabled(profile is not None)
        self.retry_button.setEnabled(idle and bool(self.last_failed))
        self.details_retry.setEnabled(idle and bool(self.last_failed))
        if self.editor:
            self.editor.save_button.setEnabled(idle)

    def submit(self, function, completed, discovery=False, on_error=None):
        if self.closing:
            return
        self.job_id += 1
        identifier = self.job_id
        worker = Worker(identifier, function)
        self.jobs[identifier] = (worker, completed, discovery, on_error)
        worker.signals.finished.connect(self.job_finished)
        (self.discovery if discovery else self.operations).start(worker)

    def job_finished(self, identifier, result, error):
        job = self.jobs.pop(identifier, None)
        if job is None:
            return
        _worker, callback, discovery, on_error = job
        if not discovery:
            self.busy = False
            self.update_actions()
        if error:
            if on_error:
                on_error(error)
            elif not discovery:
                self.report_error(error)
            else:
                self.statusBar().showMessage(f"Client check failed: {error}. Refresh detection to retry.")
            return
        callback(result)

    def mutate(self, notice, function, completed, on_error=None):
        if self.busy or self.closing:
            return
        self.busy = True
        self.statusBar().showMessage(notice)
        self.update_actions()
        self.submit(function, completed, on_error=on_error)

    def report_error(self, error):
        message = f"Operation failed: {error}"
        self.statusBar().showMessage(message)
        self.error_message.setText(message)
        self.error_banner.show()
        announce(self.error_message, message)

    def launch(self, _checked=False, login=False, profiles=None):
        profiles = profiles if profiles is not None else self.selection()
        if not profiles or (login and len(profiles) != 1):
            return
        claude_sign_in = (login and sys.platform == "win32"
                          and (profiles[0].service, profiles[0].mode) == ("claude", "desktop"))
        self.mutate("Starting sign-in…" if login else "Opening profiles…",
                    lambda: self.service.launch(profiles, login),
                    lambda results: self.launch_finished(results, claude_sign_in, login))

    def launch_finished(self, results, claude_sign_in=False, login=False):
        self.last_login = login
        if any(result.succeeded for result in results):
            QTimer.singleShot(3000, self, self.refresh_running)
        if claude_sign_in and results[0].succeeded:
            try:
                created = claude_links.ensure_handler()
                if self.claude_relay is None:
                    self.claude_relay = ClaudeSignInRelay(server_name(), self.store.root / "locks" / "claude-link.lock",
                                                        self.forward_claude_return)
                armed = self.claude_relay.arm(results[0].profile_id,
                                              claude_links.unregister_handler if created else None)
                if armed and not handler_selected():
                    claude_links.open_default_apps()
            except ERRORS:
                armed = False
            if armed:
                message = ("Sign-in requested. Choose Continue with Google in Claude Desktop. "
                           "Keep Hub open until Chrome returns to Claude. The link is routed for five minutes.")
                if not handler_selected():
                    message += (" In Default apps, assign the CLAUDE link type to AI Profile Hub Claude Links. "
                                "Hub removes the entry when the sign-in ends.")
                results = [replace(results[0], message=message)]
        if login and sys.platform == "win32" and len(results) == 1 and results[0].succeeded:
            try:
                profile = self.store.profile(results[0].profile_id)
                armed = False
                if (profile.service, profile.mode) == ("chatgpt", "desktop"):
                    created = codex_links.ensure_handler()
                    if self.codex_relay is None:
                        self.codex_relay = codex_links.CodexSignInRelay(
                            codex_links.server_name(), self.store.root / "locks" / "codex-link.lock",
                            self.forward_codex_return)
                    armed = self.codex_relay.arm(profile.id, codex_links.unregister_handler if created else None)
                    if armed and not codex_links.handler_selected():
                        codex_links.open_default_apps()
            except ERRORS:
                armed = False
            if armed:
                message = ("Sign-in requested. Finish it in the browser, then confirm the link prompt. "
                           "Keep Hub open until the Codex window of this profile comes forward. "
                           "The link is routed for five minutes.")
                if not codex_links.handler_selected():
                    message += (" In Default apps, assign the CODEX and CHATGPT link types to AI Profile Hub Codex Links. "
                                "Hub removes the entry when the sign-in ends.")
                results = [replace(results[0], message=message)]
        self.last_failed = [result.profile_id for result in results if not result.succeeded]
        self.result_text.setText("\n\n".join(f"{r.name}: {r.message}" + (f"\n{r.recovery}" if r.recovery else "") for r in results))
        self.result_scroll.show()
        self.retry_button.setVisible(bool(self.last_failed))
        if self.pages.currentWidget() == self.details_page:
            self.details_result.setText(self.result_text.text())
            self.details_result_scroll.show()
            self.details_retry.setVisible(bool(self.last_failed))
        message = f"Launch requested: {sum(r.succeeded for r in results)}. Failed: {len(self.last_failed)}."
        self.statusBar().showMessage(message)
        announce(self.statusBar(), message)
        self.update_actions()
        if login and len(results) == 1 and results[0].processes:
            profile = self.store.profile(results[0].profile_id)
            self.offer_close(profile, results[0].processes, lambda: self.launch(login=True, profiles=[profile]))

    def offer_close(self, profile, processes, retry):
        listing = "\n".join(f"• {name} (PID {pid})" for pid, name in processes)
        reply = QMessageBox.question(
            self, "Client already running",
            f"{TARGETS[profile.service][profile.mode].label} is already running:\n\n{listing}\n\n"
            "Force close these processes and try again? Unsaved work in their windows is lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            self.mutate("Closing client processes…", lambda: self.service.close_client(profile),
                        lambda _closed: retry(), on_error=self.report_error)

    def forward_codex_return(self, profile_id, link):
        try:
            codex_links.forward_profile_link(self.store, profile_id, link)
        except ERRORS:
            self.statusBar().showMessage("Could not send the Codex link to the selected profile. Start Sign in again.")
            raise
        self.statusBar().showMessage("Codex link sent to the selected desktop profile. Verify the account in Codex.")

    def forward_claude_return(self, profile_id, link):
        try:
            forward_profile_link(self.store, profile_id, link)
        except ERRORS:
            self.statusBar().showMessage("Could not send the Google return to Claude Desktop. Start Sign in again.")
            raise
        self.statusBar().showMessage("Google return sent to the selected Claude Desktop profile. Verify the account in Claude.")

    def retry_failed(self):
        profiles = [p for p in self.store.profiles() if p.id in self.last_failed]
        if not profiles:
            self.last_failed = []
            self.retry_button.hide()
            self.details_retry.hide()
            self.statusBar().showMessage("The failed profiles no longer exist. Nothing to retry.")
            return
        self.launch(login=self.last_login, profiles=profiles)

    def new_profile(self):
        if not self.busy:
            self.show_editor(None)

    def edit_profile(self):
        profile = self.selected()
        if profile and not self.busy:
            self.show_editor(profile)

    def show_editor(self, profile):
        if not self.leave_editor():
            return
        if self.editor:
            self.pages.removeWidget(self.editor)
            self.editor.deleteLater()
        self.editor = ProfileEditor(self, profile)
        self.pages.addWidget(self.editor)
        self.pages.setCurrentWidget(self.editor)
        self.profiles_nav.setChecked(True)
        self.editor.name.setFocus()

    def transfer_settings(self, direction):
        profile = self.selected()
        if not profile or self.busy:
            return
        found = self.service.transfer_categories(profile, direction)
        if not found:
            self.report_error(ValueError("No configuration was found to transfer for this profile."))
            return
        dialog = TransferDialog(self, profile, found, direction)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.chosen():
            return
        keys = dialog.chosen()
        self.transfer_profile = profile
        self.transfer_cancel = Event()
        self.transfer_total = 0
        self.transfer_size = 0
        self.progress_dialog = TransferProgressDialog(self, "Import settings" if direction == IMPORT else "Transfer settings",
                                                      self.transfer_cancel)
        self.progress_dialog.show_busy("Measuring the files to copy…")
        self.mutate("Measuring files…",
                    lambda: self.service.transfer_plan(profile, keys, direction, self.progress_relay.changed.emit,
                                                       self.transfer_cancel),
                    lambda plan: self.confirm_transfer(profile, keys, direction, plan),
                    on_error=self.transfer_failed)

    def show_progress(self, files, size):
        dialog = self.progress_dialog
        if dialog is None:
            return
        if self.transfer_total:
            dialog.show_progress(files, self.transfer_total, size, self.transfer_size)
        else:
            dialog.show_busy(f"Measuring the files to copy… {files} files, {format_size(size)}")

    def close_progress(self):
        if self.progress_dialog is not None:
            self.progress_dialog.finish()
            self.progress_dialog = None

    def transfer_failed(self, error):
        self.close_progress()
        if isinstance(error, TransferCancelled):
            self.statusBar().showMessage("Transfer cancelled. Nothing was copied.")
        elif isinstance(error, ClientRunningError) and self.transfer_profile is not None:
            self.offer_close(self.transfer_profile, error.processes,
                             lambda: self.statusBar().showMessage("Client closed. Start the transfer again."))
        else:
            self.report_error(error)

    def confirm_transfer(self, profile, keys, direction, plan):
        self.close_progress()
        if self.transfer_cancel.is_set():
            self.statusBar().showMessage("Transfer cancelled. Nothing was copied.")
            return
        if not plan.files:
            QMessageBox.information(self, "Nothing to copy",
                                    "Everything selected is already present at the destination.")
            return
        lines = [f"Provider: {SERVICES[profile.service]} ({TARGETS[profile.service][profile.mode].label})", ""]
        lines += [f"• {estimate.label}: {estimate.files} files, {format_size(estimate.size)}"
                  for estimate in plan.estimates if estimate.files]
        lines += ["", f"Total: {plan.files} files, {format_size(plan.size)}", ""]
        lines += [f"Disk {volume.anchor}: {format_size(volume.free)} free, about {format_size(volume.required)} needed"
                  for volume in plan.volumes]
        if not plan.enough:
            QMessageBox.warning(self, "Not enough disk space",
                                "\n".join(lines) + "\n\nFree some space or choose fewer categories, then try again.")
            return
        box = QMessageBox(QMessageBox.Icon.Question, "Continue?", "\n".join(lines), parent=self)
        proceed = box.addButton("Import" if direction == IMPORT else "Transfer", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not proceed:
            self.statusBar().showMessage("Transfer cancelled. Nothing was copied.")
            return
        self.transfer_cancel = Event()
        self.transfer_total, self.transfer_size = plan.files, plan.size
        self.progress_dialog = TransferProgressDialog(self, "Import settings" if direction == IMPORT else "Transfer settings",
                                                      self.transfer_cancel)
        self.progress_dialog.show_progress(0, plan.files, 0, plan.size)
        self.mutate("Transferring settings…",
                    lambda: self.service.transfer(profile, keys, direction, self.progress_relay.changed.emit,
                                                  self.transfer_cancel),
                    self.transfer_finished, on_error=self.transfer_failed)

    def transfer_finished(self, report):
        self.close_progress()
        self.transfer_total = 0
        details = report.summary()
        for title, entries in (("Conflicts kept (not overwritten)", report.conflicts), ("Errors", report.errors)):
            if entries:
                details += f"\n\n{title}:\n" + "\n".join(entries[:20])
        self.result_text.setText(details)
        self.result_scroll.show()
        self.statusBar().showMessage("Transfer finished. Restart the client to see the changes.")
        announce(self.statusBar(), "Transfer finished.")

    def saved(self, identifier):
        self.service.invalidate()
        self.editor.mark_saved()
        self.clear_filters()
        self.refresh(identifier)
        self.show_profiles()
        self.select_id(identifier)
        self.selection_changed()
        self.statusBar().showMessage("Profile saved. Open it to continue in the client.")

    def remove_profile(self):
        profile = self.selected()
        if not profile or self.busy:
            return
        detail = ("The profile and its local settings, sign-in data and session files will be removed. Your online account stays active. Close this profile's client windows or terminal first. "
                  "Transfer anything you want to keep to the original client first.")
        reply = QMessageBox.question(self, "Remove profile",
                                     f'Remove “{profile.name}”?\n\n{detail}',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.mutate("Removing profile…", lambda: self.store.delete(profile), lambda _result: self.removed())

    def removed(self):
        self.service.invalidate()
        self.refresh()
        known = {profile.id for profile in self.model.profiles}
        self.last_failed = [identifier for identifier in self.last_failed if identifier in known]
        self.retry_button.setVisible(bool(self.last_failed))
        self.statusBar().showMessage("Profile removed.")

    def choose_browser(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Choose Chrome or Chromium")
        if not path:
            return
        if not executable(Path(path)):
            self.report_error(ValueError("Choose an executable file."))
            return
        self.check_browser(lambda: self.store.save_browser(Path(path)))

    def create_hub_shortcut(self, _checked=False):
        self.make_shortcut("AI Profile Hub", ())

    def create_profile_shortcut(self, _checked=False):
        profile = self.selected()
        if profile:
            self.make_shortcut(f"{profile.name} (AI Profile Hub)", shortcuts.profile_arguments(profile.id))

    def make_shortcut(self, title, arguments):
        self.mutate("Creating shortcut…", lambda: shortcuts.create_shortcut(title, arguments),
                    lambda path: self.statusBar().showMessage(f"Shortcut created: {path}"), on_error=self.report_error)

    def quit_client(self, _checked=False):
        """Soft quit of this profile's desktop client only; it also stops apps that stay in the tray."""
        profile = self.selected()
        if not profile or self.busy:
            return

        def done(remaining):
            if remaining:
                message = ("The client did not quit: it may be asking about unsaved work. "
                           "Close it from its own window or tray icon, then refresh.")
            else:
                message = "Client quit."
            self.statusBar().showMessage(message)
            announce(self.statusBar(), message)
            self.refresh_running()

        self.mutate("Quitting client…", lambda: self.service.quit_profile(profile), done, on_error=self.report_error)

    def repair_sessions(self, _checked=False):
        profile = self.selected()
        if not profile or self.busy:
            return
        reply = QMessageBox.question(
            self, "Repair imported sessions",
            "Close Codex for this profile first.\n\nThreads copied from the original are pointed at this profile's "
            "own session files, and threads whose file is missing are removed from the list. A backup is kept.")
        if reply != QMessageBox.StandardButton.Yes:
            return

        def done(result):
            rewritten, removed, _backup = result
            self.statusBar().showMessage(f"Sessions repaired: {rewritten} re-pointed, {removed} removed.")

        self.mutate("Repairing sessions…", lambda: self.service.repair_sessions(profile), done, on_error=self.report_error)

    def restore_links(self, _checked=False):
        def restore():
            claude_links.unregister_handler()
            codex_links.unregister_handler()
            claude_links.open_default_apps_page()

        message = "Hub entries removed. In Default apps, confirm CLAUDE, CODEX and CHATGPT point to the original apps."
        self.mutate("Restoring link handlers…", restore, lambda _result: self.statusBar().showMessage(message),
                    on_error=self.report_error)

    def reset_browser(self):
        self.check_browser(self.store.clear_browser)

    def check_browser(self, update=None):
        if self.busy or self.closing:
            return
        set_badge(self.browser_status, "Checking…", "warning")

        def check():
            if update is not None:
                update()
            saved = self.store.browser()
            try:
                return saved, Availability(True, "Browser available", str(browser_path(self.store)))
            except OSError as error:
                return saved, Availability(False, str(error))

        self.mutate("Checking browser…", check, lambda result: self.browser_checked(*result),
                    on_error=self.browser_check_failed)

    def browser_checked(self, saved, result):
        self.service.invalidate()
        self.inspected_profile = None
        mode = "Manual selection" if saved else "Automatic detection"
        status = "Found" if result.available else "Unavailable" if saved else "Not found"
        set_badge(self.browser_status, status, "success" if result.available else "danger")
        if result.available:
            path = Path(result.path)
            self.set_browser_details(f"{mode} · {path.name}", path)
        else:
            self.set_browser_details(f"{mode}. {result.message}", saved)
        self.selection_changed()
        self.statusBar().clearMessage()
        if self.browser_status.isVisible():
            announce(self.browser_status, result.message)

    def browser_check_failed(self, error):
        set_badge(self.browser_status, "Check failed", "danger")
        self.report_error(error)

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
            self.statusBar().showMessage("Wait for the current operation to finish before closing.")
            return
        if not self.closing:
            self.closing = True
            if self.claude_relay:
                self.claude_relay.close()
            if self.codex_relay:
                self.codex_relay.close()
            self.discovery_timer.stop()
            self.discovery.clear()
            self.jobs.clear()
            if self.discovery.activeThreadCount():
                self.statusBar().showMessage("Finishing client checks before closing…")
                self.setEnabled(False)
        if self.discovery.activeThreadCount():
            event.ignore()
            if not self.close_timer.isActive():
                self.close_timer.start()
            return
        self.close_timer.stop()
        event.accept()


def run(smoke_test=False):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("AI Profile Hub")
    app.setOrganizationName("AI Profile Hub")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    app.setStyle("Fusion")
    try:
        window = Launcher(Store(data_root()))
    except ERRORS as error:
        QMessageBox.critical(None, "AI Profile Hub", str(error))
        return 1
    if smoke_test and window.windowIcon().pixmap(16, 16).isNull():
        print("The application icon could not be loaded.", file=sys.stderr)
        return 1
    if sys.platform == "win32" and not smoke_test:
        try:
            refresh_handler_command()
            codex_links.refresh_handler_command()
        except OSError as error:
            log_event(f"handler-path-update-failed {type(error).__name__} winerror={getattr(error, 'winerror', None)}")
    window.show()
    if smoke_test:
        QTimer.singleShot(500, window.close)
    return app.exec()
