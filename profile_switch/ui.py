
"""Unified Qt desktop workspace for client-specific AI profiles."""

from dataclasses import replace
from pathlib import Path
import sys

from threading import Event

from PySide6.QtCore import QItemSelectionModel, QSortFilterProxyModel, QThreadPool, QTimer, Qt
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent, QAction, QIcon, QKeySequence, QTextOption
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTableView, QVBoxLayout, QWidget)

from .app import ERRORS
from .catalog import SERVICES, TARGETS
from .claude_links import ClaudeSignInRelay, forward_profile_link, handler_selected, log_event, refresh_handler_command, server_name
from .launch import browser_path, executable, resolve_executable, resolve_workdir
from .qt_support import HeadingLabel, NavigationButton, ProfileModel, ProgressRelay, Worker, apply_theme
from .services import Availability, ProfileService
from .store import Store, data_root
from .transfer import EXPORT, IMPORT, TransferCancelled, format_size


APP_ICON = Path(__file__).with_name("assets") / "app-icon.svg"


def label(text, heading=False, muted=False):
    widget = HeadingLabel(text) if heading else QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if heading:
        widget.setObjectName("heading")
    if muted:
        widget.setProperty("muted", True)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.setProperty("primary", primary)
    widget.clicked.connect(callback)
    return widget


def announce(widget, message):
    QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(widget, message))


def status_badge(text=""):
    widget = label(text)
    widget.setWordWrap(False)
    widget.setObjectName("statusBadge")
    return widget


class ProfileFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.query = self.service = self.kind = ""
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def filterAcceptsRow(self, row, parent):
        profile = self.sourceModel().profiles[row]
        target = TARGETS[profile.service][profile.mode]
        text = f"{profile.name} {SERVICES[profile.service]} {target.label}".casefold()
        return (self.query in text and (not self.service or profile.service == self.service)
                and (not self.kind or target.kind == self.kind))


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
        self.claude_relay = None
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
        rail.setFixedWidth(166)
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
        self.pages.addWidget(self.details_page)
        self.statusBar().setSizeGripEnabled(False)
        self.shortcut("New profile", QKeySequence.StandardKey.New, self.new_profile)
        self.shortcut("Find profile", QKeySequence.StandardKey.Find, self.focus_search)
        self.shortcut("Open selection", "Return", self.open_from_keyboard)
        self.shortcut("Refresh detection", QKeySequence.StandardKey.Refresh, self.refresh_detection)
        self.refresh()
        self.show_profiles()
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
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)
        heading = QHBoxLayout()
        heading.addWidget(label("Profiles", heading=True))
        heading.addStretch()
        self.new_button = button("New profile", self.new_profile, True)
        heading.addWidget(self.new_button)
        layout.addLayout(heading)
        layout.addWidget(label("Your accounts, ready in the client you choose.", muted=True))
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
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeader().setStretchLastSection(True)
        for column, width in enumerate((170, 130, 220, 90)):
            self.table.setColumnWidth(column, width)
        self.table.doubleClicked.connect(lambda _index: self.launch())
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        self.splitter = QSplitter()
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.table)
        self.inspector = QFrame()
        self.inspector.setObjectName("inspector")
        self.inspector.setMinimumWidth(280)
        self.inspector.setMaximumWidth(350)
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
        self.reset_filters_button = button("Clear filters", self.clear_filters)
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
        self.result_scroll.setMaximumHeight(115)
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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self.detail_title = label("Select a profile", heading=True)
        self.detail_title.setObjectName("section")
        layout.addWidget(self.detail_title)
        self.detail_meta = label("Client and session details appear here.", muted=True)
        layout.addWidget(self.detail_meta)
        self.detail_badge = status_badge()
        layout.addWidget(self.detail_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        self.detail_state = label("", muted=True)
        layout.addWidget(self.detail_state)
        self.refresh_button = button("Refresh detection", self.refresh_detection)
        layout.addWidget(self.refresh_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.import_settings_button = button("Import settings from original…",
                                             lambda: self.transfer_settings(IMPORT))
        self.export_settings_button = button("Transfer settings to original…",
                                             lambda: self.transfer_settings(EXPORT))
        layout.addWidget(self.import_settings_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.export_settings_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.detail_path = QPlainTextEdit()
        self.detail_path.setReadOnly(True)
        self.detail_path.setTabChangesFocus(True)
        self.detail_path.setAccessibleName("Profile paths")
        self.detail_path.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.detail_path.setMinimumHeight(100)
        self.detail_path.setMaximumHeight(180)
        layout.addWidget(self.detail_path)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for text in (self.detail_title, self.detail_meta, self.detail_state):
            text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            text.setMinimumWidth(0)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        footer = QVBoxLayout()
        footer.setContentsMargins(20, 8, 20, 20)
        footer.setSpacing(8)
        self.login_button = button("Sign in", lambda: self.launch(login=True))
        self.edit_button = button("Edit profile", self.edit_profile)
        self.delete_button = button("Remove profile", self.remove_profile)
        for control in (self.login_button, self.edit_button, self.delete_button):
            footer.addWidget(control)
        footer.addWidget(label("Sign-in and account verification happen in the external client.", muted=True))
        outer.addLayout(footer)

    def build_settings(self):
        self.settings_page = QWidget()
        layout = QVBoxLayout(self.settings_page)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(20)
        layout.addWidget(label("Settings", heading=True))
        layout.addWidget(label("Appearance"))
        self.theme_combo = QComboBox()
        self.theme_combo.setAccessibleName("Appearance")
        self.theme_combo.addItems(["System", "Light", "Dark"])
        self.theme_combo.setCurrentText(self.theme)
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        layout.addWidget(self.theme_combo)
        browser_heading = QHBoxLayout()
        browser_heading.addWidget(label("Browser"))
        self.browser_status = status_badge("Not checked")
        browser_heading.addWidget(self.browser_status)
        browser_heading.addStretch()
        layout.addLayout(browser_heading)
        self.browser_label = label("", muted=True)
        self.browser_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.browser_label)
        browser_actions = QHBoxLayout()
        self.browser_choose = button("Choose Chrome or Chromium…", self.choose_browser)
        self.browser_reset = button("Use auto-detection", self.reset_browser)
        browser_actions.addWidget(self.browser_choose)
        browser_actions.addWidget(self.browser_reset)
        browser_actions.addStretch()
        layout.addLayout(browser_actions)
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
            self.report_error(error)
            return
        self.theme = value
        self.apply_appearance()

    def show_profiles(self):
        self.move_inspector()
        self.pages.setCurrentWidget(self.profiles_page)
        self.profiles_nav.setChecked(True)
        self.table.setFocus()

    def show_settings(self):
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
        if not self.selection():
            return
        self.details_page.layout().addWidget(self.inspector, 1)
        self.inspector.setMaximumWidth(16777215)
        self.inspector.show()
        self.pages.setCurrentWidget(self.details_page)

    def move_inspector(self):
        if self.inspector.parent() != self.splitter:
            self.splitter.addWidget(self.inspector)
        self.inspector.setMaximumWidth(350)
        self.inspector.setVisible(self.width() >= 1060 and self.proxy.rowCount() > 0)
        self.details_button.setVisible(self.width() < 1060 and self.proxy.rowCount() > 0)
        self.table.setColumnHidden(3, self.width() < 1060)

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

    def refresh(self, identifier=None):
        profiles = self.store.profiles()
        self.model.sync(profiles)
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
            self.detail_meta.setText(f"{SERVICES[profile.service]}\n{target.display}\n"
                                     + "Managed by AI Profile Hub")
            self.detail_path.setPlainText("Session folder\n" + str(self.store.directory(profile))
                                     + (f"\n\nWorking directory\n{profile.workdir}" if profile.workdir else ""))
            self.detail_badge.setText("Checking…")
            self.detail_badge.show()
            self.detail_state.hide()
            self.pending_inspection = generation, profile
            self.discovery_timer.start()
        else:
            self.discovery_timer.stop()
            self.detail_title.setText(f"{len(profiles)} profiles selected" if profiles else "Select a profile")
            self.detail_meta.setText("Open the selected profiles together." if profiles else "Client and session details appear here.")
            self.detail_badge.hide()
            self.detail_state.hide()
            self.detail_path.clear()
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
        self.detail_badge.setText(status)
        self.detail_state.setText(f"{result.message}\n{result.recovery}" if not result.available else "")
        self.detail_state.setVisible(not result.available)
        if result.path:
            self.detail_path.setPlainText(self.detail_path.toPlainText() + f"\n\nClient executable\n{result.path}")
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
        self.details_button.setEnabled(bool(profiles))
        for control in (self.new_button, self.browser_choose, self.browser_reset):
            control.setEnabled(idle)
        local = profile is not None and TARGETS[profile.service][profile.mode].kind != "web"
        self.import_settings_button.setEnabled(idle and local)
        self.export_settings_button.setEnabled(idle and local)
        self.edit_button.setEnabled(idle and profile is not None)
        self.delete_button.setEnabled(idle and profile is not None)
        self.login_button.setEnabled(idle and profile is not None and TARGETS[profile.service][profile.mode].kind != "web")
        self.refresh_button.setEnabled(profile is not None)
        self.retry_button.setEnabled(idle and bool(self.last_failed))
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
        self.last_login = login
        claude_sign_in = (login and sys.platform == "win32"
                          and (profiles[0].service, profiles[0].mode) == ("claude", "desktop"))
        self.mutate("Starting sign-in…" if login else "Opening profiles…",
                    lambda: self.service.launch(profiles, login),
                    lambda results: self.launch_finished(results, claude_sign_in))

    def launch_finished(self, results, claude_sign_in=False):
        if claude_sign_in and results[0].succeeded and handler_selected():
            try:
                if self.claude_relay is None:
                    self.claude_relay = ClaudeSignInRelay(server_name(), self.store.root / "locks" / "claude-link.lock",
                                                        self.forward_claude_return)
                armed = self.claude_relay.arm(results[0].profile_id)
            except ERRORS:
                armed = False
            if armed:
                results = [replace(results[0], message="Sign-in requested. Choose Continue with Google in Claude Desktop. "
                                   "Keep Hub open until Chrome returns to Claude. The link is routed for five minutes.")]
        self.last_failed = [result.profile_id for result in results if not result.succeeded]
        self.result_text.setText("\n\n".join(f"{r.name}: {r.message}" + (f"\n{r.recovery}" if r.recovery else "") for r in results))
        self.result_scroll.show()
        self.retry_button.setVisible(bool(self.last_failed))
        message = f"Launch requested: {sum(r.succeeded for r in results)}. Failed: {len(self.last_failed)}."
        self.statusBar().showMessage(message)
        announce(self.statusBar(), message)
        self.update_actions()

    def forward_claude_return(self, profile_id, link):
        try:
            forward_profile_link(self.store, profile_id, link)
        except ERRORS:
            self.statusBar().showMessage("Could not send the Google return to Claude Desktop. Start Sign in again.")
            raise
        self.statusBar().showMessage("Google return sent to the selected Claude Desktop profile. Verify the account in Claude.")

    def retry_failed(self):
        profiles = [p for p in self.store.profiles() if p.id in self.last_failed]
        self.launch(login=self.last_login, profiles=profiles)

    def new_profile(self):
        if not self.busy:
            self.show_editor(None)

    def edit_profile(self):
        profile = self.selected()
        if profile and not self.busy:
            self.show_editor(profile)

    def show_editor(self, profile):
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
        self.clear_filters()
        self.refresh(identifier)
        self.show_profiles()
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
        self.statusBar().showMessage("Profile removed.")

    def choose_browser(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Choose Chrome or Chromium")
        if not path:
            return
        if not executable(Path(path)):
            self.report_error(ValueError("Choose an executable file."))
            return
        self.check_browser(lambda: self.store.save_browser(Path(path)))

    def reset_browser(self):
        self.check_browser(self.store.clear_browser)

    def check_browser(self, update=None):
        if self.busy or self.closing:
            return
        self.browser_status.setText("Checking…")

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
        self.browser_status.setText(status)
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
        self.browser_status.setText("Check failed")
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


DISCLAIMER = (
    "Before you continue:\n"
    "• This is a copy of one moment in time. Afterwards the profile and the original client diverge: new chats, "
    "MCP servers and settings are not synchronised.\n"
    "• MCP servers can contain tokens or keys in plain text (env, headers). They are copied as they are.\n"
    "• Sign-in credentials are never copied; each profile needs its own login.\n"
    "• Chat history is tied to the repository path. If the working directory differs, history may not be found.\n"
    "• Do not use the same account or desktop session in the original client and in a profile at the same time: "
    "the provider may sign you out or invalidate tokens.\n"
    "• Skills, plugins and history are duplicated and use extra disk space; third-party plugins keep their permissions.\n"
    "• Nothing in the destination is overwritten. Changed files are backed up first and can be restored from the "
    "diagnostics folder.\n"
    "• Account isolation is not guaranteed for every client, and using several accounts may be restricted by the "
    "provider's terms. This project is not affiliated with the providers; you are responsible for your use.")


class TransferProgressDialog(QDialog):
    """Modal progress for measuring and copying; closing it asks the running job to stop."""

    def __init__(self, parent, title, cancel):
        super().__init__(parent)
        self.cancel_event = cancel
        self.finished_work = False
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        self.text = label("", muted=True)
        layout.addWidget(self.text)
        self.bar = QProgressBar()
        self.bar.setAccessibleName("Transfer progress")
        layout.addWidget(self.bar)
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_button = button("Cancel", self.reject)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)

    def show_busy(self, text):
        self.bar.setRange(0, 0)
        self.text.setText(text)
        self.show()

    def show_progress(self, files, total, size, total_size):
        self.bar.setRange(0, max(total, 1))
        self.bar.setValue(min(files, total))
        self.text.setText(f"{min(files, total)} of {total} files · {format_size(size)} of {format_size(total_size)}")
        self.show()

    def reject(self):
        if not self.finished_work and not self.cancel_event.is_set():
            self.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.text.setText("Cancelling…")

    def finish(self):
        self.finished_work = True
        self.hide()
        self.deleteLater()


class TransferDialog(QDialog):
    def __init__(self, launcher, profile, found, direction):
        super().__init__(launcher)
        importing = direction == IMPORT
        self.setWindowTitle("Import settings from original" if importing else "Transfer settings to original")
        layout = QVBoxLayout(self)
        layout.addWidget(label(f"Profile: {profile.name}. " + (
            "Copy configuration from the original client into this profile." if importing else
            "Copy configuration from this profile back into the original client. Close the original client first."),
            muted=True))
        self.boxes = []
        for category in found:
            box = QCheckBox(category.label + (" (may contain secrets)" if category.sensitive else ""))
            box.setChecked(category.key in ("mcp", "settings", "desktop-mcp", "instructions", "ide"))
            box.setProperty("key", category.key)
            layout.addWidget(box)
            self.boxes.append(box)
        layout.addWidget(label(DISCLAIMER, muted=True))
        self.agree = QCheckBox("I understand")
        layout.addWidget(self.agree)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Cancel", self.reject))
        self.start = button("Import" if importing else "Transfer", self.accept, True)
        self.start.setEnabled(False)
        self.agree.toggled.connect(self.start.setEnabled)
        actions.addWidget(self.start)
        layout.addLayout(actions)

    def chosen(self):
        return [box.property("key") for box in self.boxes if box.isChecked()]


class ProfileEditor(QWidget):
    def __init__(self, launcher, profile):
        super().__init__()
        self.launcher, self.profile = launcher, profile
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(16)
        layout.addWidget(label("Edit profile" if profile else "New profile", heading=True))
        if not profile:
            layout.addWidget(label("Create one profile for each account you want to use.", muted=True))
        form = QFormLayout()
        form.setVerticalSpacing(16)
        self.product = QComboBox()
        self.product.setAccessibleName("Product")
        for key, value in SERVICES.items():
            self.product.addItem(value, key)
        self.target = QComboBox()
        self.target.setAccessibleName("Client")
        self.name = QLineEdit(profile.name if profile else "")
        self.name.setAccessibleName("Profile name")
        self.name.setMaxLength(48)
        self.name.setPlaceholderText("For example, Work or Personal")
        form.addRow("Product", self.product)
        form.addRow("Client", self.target)
        form.addRow("Name", self.name)
        layout.addLayout(form)
        self.advanced = QCheckBox("Advanced settings")
        layout.addWidget(self.advanced)
        self.local = QWidget()
        local_form = QFormLayout(self.local)
        local_form.setContentsMargins(0, 0, 0, 0)
        self.binary = QLineEdit(profile.executable if profile else "")
        self.binary.setAccessibleName("Local executable")
        self.binary.setPlaceholderText("Auto-detect installed client")
        self.workdir = QLineEdit(profile.workdir if profile else "")
        self.workdir.setAccessibleName("Working directory")
        self.workdir.setPlaceholderText("Use your home directory")
        local_form.addRow("Executable", self.path_control(self.binary, False))
        local_form.addRow("Working directory", self.path_control(self.workdir, True))
        layout.addWidget(self.local)
        self.hint = label("", muted=True)
        layout.addWidget(self.hint)
        if profile:
            layout.addWidget(label("Create a new profile to use a different product or client.", muted=True))
        self.error = label("")
        self.invalid_field = None
        layout.addWidget(self.error)
        layout.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Cancel", launcher.show_profiles))
        self.save_button = button("Save profile", self.save, True)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self.product.currentIndexChanged.connect(self.update_products)
        self.target.currentIndexChanged.connect(self.update_target)
        self.advanced.toggled.connect(self.update_target)
        if profile:
            self.product.setCurrentIndex(self.product.findData(profile.service))
        self.update_products()
        if profile:
            self.target.setCurrentIndex(self.target.findData(profile.mode))
            self.product.setEnabled(False)
            self.target.setEnabled(False)
        self.advanced.setChecked(bool(profile and (profile.executable or profile.workdir)))
        self.update_target()

    def path_control(self, entry, directory):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(entry, 1)
        def browse():
            value = (QFileDialog.getExistingDirectory(self, "Choose working directory") if directory else
                     QFileDialog.getOpenFileName(self, "Choose client executable")[0])
            if value:
                entry.setText(value)
        browse_button = button("Browse…", browse)
        browse_button.setAccessibleName("Browse for working directory" if directory else "Browse for executable")
        layout.addWidget(browse_button)
        return row

    def update_products(self):
        self.target.blockSignals(True)
        self.target.clear()
        for mode, target in TARGETS[self.product.currentData()].items():
            self.target.addItem(target.display, mode)
        self.target.blockSignals(False)
        self.update_target()

    def update_target(self):
        mode = self.target.currentData()
        if mode is None:
            return
        target = TARGETS[self.product.currentData()][mode]
        self.advanced.setVisible(target.kind != "web")
        self.local.setVisible(target.kind != "web" and self.advanced.isChecked())
        self.hint.setText("Opens in a dedicated Chrome or Chromium session. Sign in on the website." if target.kind == "web" else
                          "Opens the installed client in a terminal with its own profile settings." if target.kind == "cli" else
                          "Experimental desktop isolation. For sign-in, quit other instances first and verify the account in the client.")

    def save(self):
        if self.launcher.busy:
            return
        if self.invalid_field is not None:
            self.invalid_field.setAccessibleDescription("")
            self.invalid_field = None
        self.error.clear()
        name = self.name.text().strip()
        if not name or not name.isprintable():
            self.show_error("Enter a name between 1 and 48 characters.", self.name)
            return
        service, mode = self.product.currentData(), self.target.currentData()
        local = TARGETS[service][mode].kind != "web"
        binary = self.binary.text().strip() if local else ""
        workdir = self.workdir.text().strip() if local else ""
        def save():
            for field, value, title, resolver in (("binary", binary, "Executable", resolve_executable),
                                                   ("workdir", workdir, "Working directory", resolve_workdir)):
                if value:
                    try:
                        if not Path(value).expanduser().is_absolute():
                            raise ValueError(f"{title}: enter an absolute path.")
                        resolver(value)
                    except ERRORS as error:
                        return None, str(error), field
            try:
                identifier = self.launcher.store.save(service, name, mode, executable=binary, workdir=workdir, previous=self.profile)
                return identifier, None, None
            except ERRORS as error:
                return None, str(error), None
        def finished(result):
            identifier, error, field = result
            if error:
                if field:
                    self.advanced.setChecked(True)
                self.show_error(error, getattr(self, field) if field else None)
            else:
                self.launcher.saved(identifier)
        self.launcher.mutate("Saving profile…", save, finished)

    def show_error(self, message, field=None):
        self.error.setText(message)
        self.invalid_field = field
        if field is not None:
            field.setAccessibleDescription(message)
        if self.launcher.pages.currentWidget() != self:
            self.launcher.report_error(message)
            return
        self.launcher.statusBar().showMessage("Profile not saved. Correct the form details and retry.")
        if field is not None:
            field.setFocus()
        announce(self.error, message)


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
        except OSError as error:
            log_event(f"handler-path-update-failed {type(error).__name__} winerror={getattr(error, 'winerror', None)}")
    window.show()
    if smoke_test:
        QTimer.singleShot(500, window.close)
    return app.exec()
