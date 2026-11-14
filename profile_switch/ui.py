
"""Unified Qt desktop workspace for client-specific AI profiles."""

from pathlib import Path
import sys

from PySide6.QtCore import QItemSelectionModel, QSortFilterProxyModel, QThreadPool, QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence, QTextOption
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTableView, QVBoxLayout, QWidget)

from .app import ERRORS
from .catalog import LINKED_CLAUDE_PROFILE_NAME, SERVICES, TARGETS
from .launch import executable, resolve_executable, resolve_workdir
from .qt_support import ProfileModel, Worker, apply_theme
from .services import ProfileService
from .store import Store, data_root, duo_directory


def label(text, heading=False, muted=False):
    widget = QLabel(text)
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
        self.jobs = {}
        self.job_id = self.inspect_generation = 0
        self.inspected_profile = None
        self.last_failed = []
        self.last_login = False
        self.editor = None
        self.operations = QThreadPool(self)
        self.operations.setMaxThreadCount(1)
        self.discovery = QThreadPool(self)
        self.discovery.setMaxThreadCount(2)
        self.discovery_timer = QTimer(self)
        self.discovery_timer.setSingleShot(True)
        self.discovery_timer.setInterval(80)
        self.pending_inspection = None
        self.discovery_timer.timeout.connect(self.start_inspection)
        self.setWindowTitle("AI Profile Hub")
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
        self.profiles_nav = button("Profiles", self.show_profiles)
        self.settings_nav = button("Settings", self.show_settings)
        for nav in (self.profiles_nav, self.settings_nav):
            nav.setCheckable(True)
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
        self.error_message.setAccessibleName("Operation error")
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
        self.duo_notice = button("Claude Desktop session found. Link session…", self.link_existing)
        layout.addWidget(self.duo_notice)
        self.model = ProfileModel()
        self.proxy = ProfileFilter()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setAccessibleName("Profiles")
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
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
        empty_actions = QHBoxLayout()
        self.empty_clear = button("Clear filters", self.clear_filters)
        empty_actions.addWidget(self.empty_clear)
        self.empty_new = button("New profile", self.new_profile, True)
        empty_actions.addWidget(self.empty_new)
        empty_actions.addStretch()
        empty_layout.addLayout(empty_actions)
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
        self.detail_title = label("Select a profile")
        self.detail_title.setObjectName("section")
        layout.addWidget(self.detail_title)
        self.detail_meta = label("Client and session details appear here.", muted=True)
        layout.addWidget(self.detail_meta)
        self.detail_state = label("", muted=True)
        layout.addWidget(self.detail_state)
        self.detail_path = QPlainTextEdit()
        self.detail_path.setReadOnly(True)
        self.detail_path.setTabChangesFocus(True)
        self.detail_path.setAccessibleName("Profile paths")
        self.detail_path.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.detail_path.setMinimumHeight(100)
        self.detail_path.setMaximumHeight(180)
        layout.addWidget(self.detail_path)
        self.refresh_button = button("Refresh detection", self.refresh_detection)
        layout.addWidget(self.refresh_button)
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
        layout.addWidget(label("Browser"))
        self.browser_label = label("", muted=True)
        layout.addWidget(self.browser_label)
        browser_actions = QHBoxLayout()
        self.browser_choose = button("Choose Chrome or Chromium…", self.choose_browser)
        self.browser_reset = button("Use auto-detection", self.reset_browser)
        browser_actions.addWidget(self.browser_choose)
        browser_actions.addWidget(self.browser_reset)
        browser_actions.addStretch()
        layout.addLayout(browser_actions)
        layout.addWidget(label("Existing sessions"))
        layout.addWidget(label("Link a previously configured Claude Desktop session on Windows. Its original folder stays in place.", muted=True))
        self.link_button = button("Link existing session…", self.link_existing)
        self.link_button.setEnabled(sys.platform == "win32")
        layout.addWidget(self.link_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        layout.addWidget(label("Profiles store settings for one client each. Desktop isolation is experimental; verify the account in each client.", muted=True))
        self.pages.addWidget(self.settings_page)
        self.update_browser_label()

    def update_browser_label(self):
        self.browser_label.setText(str(self.store.browser() or "Auto-detect Chrome or Chromium on the next web launch."))

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
        self.settings_nav.setChecked(False)
        self.table.setFocus()

    def show_settings(self):
        self.pages.setCurrentWidget(self.settings_page)
        self.profiles_nav.setChecked(False)
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
        self.details_button.setVisible(self.width() < 1060)
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
        self.duo_notice.setVisible(sys.platform == "win32" and duo_directory().is_dir()
                                   and not any(p.legacy_duo for p in profiles))
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
        self.reset_filters_button.setVisible(filtered and visible > 0)
        self.splitter.setVisible(bool(visible))
        self.table.setVisible(bool(visible))
        self.empty_page.setVisible(not visible)
        self.empty_clear.setVisible(filtered)
        self.empty_title.setText("No matching profiles" if total else "Add your first profile")
        self.empty_notice.setText("Create a profile or link an existing session to get started." if not total else
                                 "No matching profiles. Clear the filters or create a profile." if not visible else "")
        self.empty_notice.setVisible(not visible)
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
                                     + ("Linked session · original data preserved" if profile.legacy_duo else "Managed by AI Profile Hub"))
            self.detail_path.setPlainText("Session folder\n" + str(duo_directory() if profile.legacy_duo else self.store.directory(profile))
                                     + (f"\n\nWorking directory\n{profile.workdir}" if profile.workdir else ""))
            self.detail_state.setText("Checking client availability…")
            self.pending_inspection = generation, profile
            self.discovery_timer.start()
        else:
            self.discovery_timer.stop()
            self.detail_title.setText(f"{len(profiles)} profiles selected" if profiles else "Select a profile")
            self.detail_meta.setText("Open the selected profiles together." if profiles else "Client and session details appear here.")
            self.detail_state.clear()
            self.detail_path.clear()
        self.update_actions()

    def start_inspection(self):
        generation, profile = self.pending_inspection
        self.submit(lambda: self.service.inspect(profile),
                    lambda result: self.inspection_finished(generation, result), discovery=True)

    def inspection_finished(self, generation, result):
        if generation != self.inspect_generation:
            return
        self.detail_state.setText(result.message + (f"\n{result.recovery}" if not result.available else ""))
        if result.path:
            self.detail_path.setPlainText(self.detail_path.toPlainText() + f"\n\nClient executable\n{result.path}")

    def refresh_detection(self):
        self.service.invalidate()
        self.inspected_profile = None
        self.selection_changed()
        self.statusBar().showMessage("Client detection refreshed.")

    def update_actions(self):
        profiles, profile = self.selection(), self.selected()
        idle = not self.busy
        self.open_button.setText("Open selected" if len(profiles) > 1 else "Open profile")
        self.open_button.setEnabled(idle and bool(profiles))
        self.details_button.setEnabled(bool(profiles))
        for control in (self.new_button, self.empty_new, self.browser_choose, self.browser_reset, self.duo_notice):
            control.setEnabled(idle)
        self.link_button.setEnabled(idle and sys.platform == "win32")
        self.edit_button.setEnabled(idle and profile is not None)
        self.delete_button.setEnabled(idle and profile is not None)
        self.delete_button.setText("Remove link" if profile and profile.legacy_duo else "Remove profile")
        self.login_button.setEnabled(idle and profile is not None and TARGETS[profile.service][profile.mode].kind != "web")
        self.refresh_button.setEnabled(profile is not None)
        self.retry_button.setEnabled(idle and bool(self.last_failed))
        if self.editor:
            self.editor.save_button.setEnabled(idle)

    def submit(self, function, completed, discovery=False):
        self.job_id += 1
        identifier = self.job_id
        worker = Worker(identifier, function)
        self.jobs[identifier] = (worker, completed, discovery)
        worker.signals.finished.connect(self.job_finished)
        (self.discovery if discovery else self.operations).start(worker)

    def job_finished(self, identifier, result, error):
        job = self.jobs.pop(identifier, None)
        if job is None:
            return
        _worker, callback, discovery = job
        if not discovery:
            self.busy = False
            self.update_actions()
        if error:
            if not discovery:
                self.report_error(error)
            else:
                self.statusBar().showMessage(f"Client check failed: {error}. Refresh detection to retry.")
            return
        callback(result)

    def mutate(self, notice, function, completed):
        if self.busy:
            return
        self.busy = True
        self.statusBar().showMessage(notice)
        self.update_actions()
        self.submit(function, completed)

    def report_error(self, error):
        self.statusBar().showMessage(f"Operation failed: {error}")
        self.error_message.setText(f"Operation failed: {error}")
        self.error_banner.show()

    def launch(self, _checked=False, login=False, profiles=None):
        profiles = profiles if profiles is not None else self.selection()
        if not profiles or (login and len(profiles) != 1):
            return
        self.last_login = login
        self.mutate("Starting sign-in…" if login else "Opening profiles…",
                    lambda: self.service.launch(profiles, login), self.launch_finished)

    def launch_finished(self, results):
        self.last_failed = [result.profile_id for result in results if not result.succeeded]
        self.result_text.setText("\n\n".join(f"{r.name}: {r.message}" + (f"\n{r.recovery}" if r.recovery else "") for r in results))
        self.result_scroll.show()
        self.retry_button.setVisible(bool(self.last_failed))
        self.statusBar().showMessage(f"Launch requested: {sum(r.succeeded for r in results)}. Failed: {len(self.last_failed)}.")
        self.update_actions()

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

    def show_editor(self, profile, link=False):
        if self.editor:
            self.pages.removeWidget(self.editor)
            self.editor.deleteLater()
        self.editor = ProfileEditor(self, profile, link)
        self.pages.addWidget(self.editor)
        self.pages.setCurrentWidget(self.editor)
        self.editor.name.setFocus()

    def link_existing(self):
        if self.busy:
            return
        existing = next((p for p in self.store.profiles() if p.legacy_duo), None)
        if existing:
            self.clear_filters()
            self.refresh(existing.id)
            self.show_profiles()
            self.statusBar().showMessage("The Claude Desktop session is already linked.")
        elif sys.platform != "win32" or not duo_directory().is_dir():
            self.report_error(ValueError("No existing Claude Desktop session was found. On Windows, restore the original session folder and retry."))
        else:
            self.show_editor(None, link=True)

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
        detail = ("The original Claude Desktop session and its data stay in their folder." if profile.legacy_duo else
                  "The profile and its local settings, sign-in data and session files will be removed. Your online account stays active. Close this profile's client windows or terminal first.")
        reply = QMessageBox.question(self, "Remove link" if profile.legacy_duo else "Remove profile",
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
        self.mutate("Saving browser…", lambda: self.store.save_browser(Path(path)), lambda _result: self.browser_changed())

    def reset_browser(self):
        self.mutate("Resetting browser…", self.store.clear_browser, lambda _result: self.browser_changed())

    def browser_changed(self):
        self.service.invalidate()
        self.inspected_profile = None
        self.update_browser_label()
        self.selection_changed()
        self.statusBar().showMessage("Browser settings saved.")

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
            self.statusBar().showMessage("Wait for the current operation to finish before closing.")
            return
        self.discovery.clear()
        self.discovery_timer.stop()
        self.discovery.waitForDone()
        event.accept()


class ProfileEditor(QWidget):
    def __init__(self, launcher, profile, link=False):
        super().__init__()
        self.launcher, self.profile, self.link = launcher, profile, link
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(16)
        layout.addWidget(button("Back to profiles", launcher.show_profiles), alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(label("Link existing session" if link else "Edit profile" if profile else "New profile", heading=True))
        if not profile and not link:
            layout.addWidget(label("Create one profile for each account you want to use.", muted=True))
            if sys.platform == "win32" and duo_directory().is_dir():
                layout.addWidget(button("Link existing Claude Desktop session…", launcher.link_existing),
                                 alignment=Qt.AlignmentFlag.AlignLeft)
        form = QFormLayout()
        form.setVerticalSpacing(16)
        self.product = QComboBox()
        self.product.setAccessibleName("Product")
        for key, value in SERVICES.items():
            self.product.addItem(value, key)
        self.target = QComboBox()
        self.target.setAccessibleName("Client")
        self.name = QLineEdit(profile.name if profile else LINKED_CLAUDE_PROFILE_NAME if link else "")
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
        if link:
            layout.addWidget(label(f"Original session folder\n{duo_directory()}\n\nThe folder stays in place. Removing this link preserves its data.", muted=True))
        elif profile:
            layout.addWidget(label("Create a new profile to use a different product or client.", muted=True))
        self.error = label("")
        self.error.setAccessibleName("Profile validation error")
        layout.addWidget(self.error)
        layout.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Cancel", launcher.show_profiles))
        self.save_button = button("Link session" if link else "Save profile", self.save, True)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self.product.currentIndexChanged.connect(self.update_products)
        self.target.currentIndexChanged.connect(self.update_target)
        self.advanced.toggled.connect(self.update_target)
        if profile:
            self.product.setCurrentIndex(self.product.findData(profile.service))
        self.update_products()
        if profile or link:
            self.target.setCurrentIndex(self.target.findData(profile.mode if profile else "desktop"))
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
        layout.addWidget(button("Browse…", browse))
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
        name = self.name.text().strip()
        if not name or not name.isprintable():
            self.error.setText("Enter a name between 1 and 48 characters.")
            self.name.setFocus()
            return
        service, mode = self.product.currentData(), self.target.currentData()
        local = TARGETS[service][mode].kind != "web"
        binary = self.binary.text().strip() if local else ""
        workdir = self.workdir.text().strip() if local else ""
        self.error.clear()
        def save():
            try:
                for value, title, resolver in ((binary, "Executable", resolve_executable), (workdir, "Working directory", resolve_workdir)):
                    if value:
                        if not Path(value).expanduser().is_absolute():
                            raise ValueError(f"{title}: enter an absolute path.")
                        resolver(value)
                identifier = (self.launcher.service.link_duo(name) if self.link else
                              self.launcher.store.save(service, name, mode, executable=binary, workdir=workdir,
                                  previous=self.profile, legacy_duo=bool(self.profile and self.profile.legacy_duo)))
                return identifier, None
            except ERRORS as error:
                return None, str(error)
        def finished(result):
            identifier, error = result
            if error:
                self.error.setText(error)
                self.launcher.statusBar().showMessage("Profile not saved. Correct the form details and retry.")
            else:
                self.launcher.saved(identifier)
        self.launcher.mutate("Saving profile…", save, finished)


def run(smoke_test=False):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("AI Profile Hub")
    app.setOrganizationName("AI Profile Hub")
    app.setStyle("Fusion")
    try:
        window = Launcher(Store(data_root()))
    except ERRORS as error:
        QMessageBox.critical(None, "AI Profile Hub", str(error))
        return 1
    window.show()
    if smoke_test:
        QTimer.singleShot(500, window.close)
    return app.exec()
