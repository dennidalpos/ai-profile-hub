"""Qt presentation models, worker bridge and application palette."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QAccessible, QColor, QPalette
from PySide6.QtWidgets import QAccessibleWidget, QLabel, QPushButton, QSizePolicy

from .catalog import SERVICES, TARGETS


class HeadingLabel(QLabel):
    pass


class ElidedLabel(QLabel):
    """Single-line label that shortens the middle of long text and keeps the full text in its tooltip."""

    def __init__(self, text=""):
        super().__init__()
        self.full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.set_full_text(text)

    def set_full_text(self, text):
        self.full = text
        self.setToolTip(text)
        self.setAccessibleDescription(text)
        self.refit()

    def full_text(self):
        return self.full

    def refit(self):
        self.setText(self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideMiddle, max(self.width(), 24)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refit()


def set_property(widget, name, value):
    """Change a style-sheet property and re-apply the style so the new look shows immediately."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class NavigationButton(QPushButton):
    pass


class AccessibleHeading(QAccessibleWidget):
    def __init__(self, widget):
        super().__init__(widget, QAccessible.Role.Heading)

    def text(self, kind):
        return self.object().text() if kind == QAccessible.Text.Name else super().text(kind)


class AccessibleNavigationButton(QAccessibleWidget):
    def __init__(self, widget):
        super().__init__(widget, QAccessible.Role.RadioButton, widget.text())

    def state(self):
        state = super().state()
        state.checkable = True
        state.checked = self.object().isChecked()
        return state

    def actionNames(self):
        return [self.pressAction(), *super().actionNames()] if self.object().isEnabled() else []

    def doAction(self, action):
        if action == self.pressAction():
            self.object().click()
        else:
            super().doAction(action)


def accessible_widget(_class_name, widget):
    if isinstance(widget, HeadingLabel):
        return AccessibleHeading(widget)
    if isinstance(widget, NavigationButton):
        return AccessibleNavigationButton(widget)
    return None


QAccessible.installFactory(accessible_widget)


class ProfileModel(QAbstractTableModel):
    headers = ("Profile", "Product", "Client", "Source")

    def __init__(self):
        super().__init__()
        self.profiles = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.profiles)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        profile = self.profiles[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return profile
        target = TARGETS[profile.service][profile.mode]
        if role == Qt.ItemDataRole.DisplayRole:
            return (profile.name, SERVICES[profile.service], target.label, "Managed")[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return (profile.name, SERVICES[profile.service], target.display, "Managed")[index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None

    def sync(self, profiles):
        wanted = {p.id for p in profiles}
        for row in range(len(self.profiles) - 1, -1, -1):
            if self.profiles[row].id not in wanted:
                self.beginRemoveRows(QModelIndex(), row, row)
                self.profiles.pop(row)
                self.endRemoveRows()
        positions = {p.id: i for i, p in enumerate(self.profiles)}
        for profile in profiles:
            row = positions.get(profile.id)
            if row is None:
                row = len(self.profiles)
                self.beginInsertRows(QModelIndex(), row, row)
                self.profiles.append(profile)
                self.endInsertRows()
                positions[profile.id] = row
            elif self.profiles[row] != profile:
                self.profiles[row] = profile
                self.dataChanged.emit(self.index(row, 0), self.index(row, 3))


class WorkerSignals(QObject):
    finished = Signal(int, object, object)


class ProgressRelay(QObject):
    """Carries progress from a worker thread to the window; connect it to a method of a QObject."""
    changed = Signal(int, int)


class Worker(QRunnable):
    def __init__(self, identifier, function):
        super().__init__()
        self.identifier = identifier
        self.function = function
        self.signals = WorkerSignals()

    def run(self):
        try:
            result, error = self.function(), None
        except Exception as exception:
            result, error = None, exception
        self.signals.finished.emit(self.identifier, result, error)


def apply_theme(app, preference):
    dark = preference == "Dark" or (preference == "System" and
            app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    colors = ({"canvas": "#15191F", "surface": "#1D232C", "text": "#EEF1F6", "muted": "#B0BAC8",
               "border": "#394352", "accent": "#8DB7FF", "selected": "#2C4264", "buttonText": "#15191F",
               "controlBorder": "#738198", "disabledButtonBorder": "#515D6E", "buttonPressed": "#38537D",
               "primaryHover": "#AECBFF", "primaryPressed": "#6E9DEB",
               "okText": "#8EE0A8", "okBg": "#1F3A2B", "okBorder": "#34624A",
               "warnText": "#F4C97A", "warnBg": "#3E3220", "warnBorder": "#65502B",
               "errText": "#FF9E9E", "errBg": "#442528", "errBorder": "#6F3F42",
               "infoText": "#A3C6FF", "infoBg": "#223652", "infoBorder": "#35507A"}
              if dark else
              {"canvas": "#F5F6F8", "surface": "#FFFFFF", "text": "#202631", "muted": "#596474",
               "border": "#D7DDE5", "accent": "#2458B8", "selected": "#E2EBFC", "buttonText": "#FFFFFF",
               "controlBorder": "#7B8799", "disabledButtonBorder": "#B4BFCE", "buttonPressed": "#CEDDF9",
               "primaryHover": "#19478F", "primaryPressed": "#14376F",
               "okText": "#14683A", "okBg": "#E2F4E9", "okBorder": "#A5D5B8",
               "warnText": "#7D5200", "warnBg": "#FFF0D0", "warnBorder": "#E6C888",
               "errText": "#A8211A", "errBg": "#FDE6E5", "errBorder": "#E7ADA9",
               "infoText": "#1B4C9A", "infoBg": "#E2EBFC", "infoBorder": "#B4CBF1"})
    palette = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "canvas"), (QPalette.ColorRole.Base, "surface"),
                      (QPalette.ColorRole.AlternateBase, "canvas"), (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.ButtonText, "text"),
                      (QPalette.ColorRole.Button, "surface"), (QPalette.ColorRole.Highlight, "selected"),
                      (QPalette.ColorRole.HighlightedText, "text"), (QPalette.ColorRole.ToolTipBase, "surface"),
                      (QPalette.ColorRole.ToolTipText, "text"), (QPalette.ColorRole.PlaceholderText, "muted")):
        palette.setColor(role, QColor(colors[key]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(colors["muted"]))
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget { font-size: 14px; }
        QMainWindow, QWidget#workspace { background: %(canvas)s; }
        QLabel#heading { font-size: 22px; font-weight: 600; }
        QLabel#section { font-size: 18px; font-weight: 600; }
        QLabel[muted="true"] { color: %(muted)s; }
        QLabel#statusBadge { background: %(selected)s; color: %(text)s; border: 1px solid %(border)s;
            border-radius: 9px; padding: 1px 9px; font-size: 12px; font-weight: 600; }
        QLabel#statusBadge[tone="success"] { background: %(okBg)s; color: %(okText)s; border-color: %(okBorder)s; }
        QLabel#statusBadge[tone="warning"] { background: %(warnBg)s; color: %(warnText)s; border-color: %(warnBorder)s; }
        QLabel#statusBadge[tone="danger"] { background: %(errBg)s; color: %(errText)s; border-color: %(errBorder)s; }
        QLabel#statusBadge[tone="info"] { background: %(infoBg)s; color: %(infoText)s; border-color: %(infoBorder)s; }
        QLabel[caption="true"] { color: %(muted)s; font-size: 12px; }
        QFrame#rail { background: %(surface)s; border-right: 1px solid %(border)s; }
        QFrame#inspector { background: %(surface)s; border: 1px solid %(border)s; border-radius: 6px; }
        QPushButton, QComboBox, QLineEdit { min-height: 28px; padding: 1px 10px;
            border: 1px solid %(controlBorder)s; border-radius: 6px; background: %(surface)s; color: %(text)s; }
        QLineEdit { placeholder-text-color: %(muted)s; }
        QPushButton:checked { background: %(selected)s; font-weight: 600; }
        QPushButton:enabled:hover { background: %(selected)s; border-color: %(accent)s; }
        QPushButton:enabled:pressed { background: %(buttonPressed)s; border-color: %(text)s; }
        QPushButton[primary="true"] { font-weight: 600; }
        QPushButton[primary="true"]:enabled { background: %(accent)s; color: %(buttonText)s; border-color: %(primaryPressed)s; }
        QPushButton[primary="true"]:enabled:hover { background: %(primaryHover)s; }
        QPushButton[primary="true"]:enabled:pressed { background: %(primaryPressed)s; }
        QPushButton:disabled { color: %(muted)s; background: %(canvas)s; border-color: %(disabledButtonBorder)s; }
        QPushButton[role="flat"] { border-color: transparent; background: transparent; }
        QPushButton[role="flat"]:disabled { border-color: transparent; background: transparent; }
        QPushButton[role="small"] { min-height: 20px; padding: 0 6px; font-size: 12px; border-color: transparent;
            background: transparent; color: %(accent)s; }
        QPushButton[role="small"]:disabled { border-color: transparent; background: transparent; }
        QPushButton[role="danger"] { color: %(errText)s; border-color: %(errBorder)s; }
        QPushButton[role="danger"]:enabled:hover { background: %(errBg)s; border-color: %(errText)s; }
        QPushButton[role="danger"]:disabled { color: %(muted)s; border-color: %(disabledButtonBorder)s; }
        QPushButton::menu-indicator { subcontrol-position: right center; subcontrol-origin: padding; right: 6px; }
        QPushButton[menu="true"] { padding-right: 20px; }
        QPushButton:enabled:focus, QComboBox:focus, QLineEdit:focus, QTableView:focus { border: 2px solid %(accent)s; }
        QPushButton[primary="true"]:enabled:focus { border-color: %(text)s; }
        QTableView { background: %(surface)s; border: 1px solid %(border)s; border-radius: 6px;
            gridline-color: %(border)s; selection-background-color: %(selected)s; selection-color: %(text)s; }
        QHeaderView::section { background: %(canvas)s; color: %(muted)s; padding: 8px 8px;
            border: 0; border-bottom: 1px solid %(border)s; font-weight: 600; text-align: left; }
        QTableView::item { padding: 4px 8px; }
        QScrollArea { border: 0; background: transparent; }
        QPlainTextEdit { background: %(surface)s; color: %(muted)s; border: 1px solid %(border)s; border-radius: 4px; padding: 6px; }
        QPlainTextEdit:focus { border: 2px solid %(accent)s; }
        QStatusBar { border-top: 1px solid %(border)s; padding: 6px 12px; }
    """ % colors)
