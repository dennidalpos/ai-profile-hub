"""Qt presentation models, worker bridge and application palette."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QColor, QPalette

from .catalog import SERVICES, TARGETS


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
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return (profile.name, SERVICES[profile.service], TARGETS[profile.service][profile.mode].display,
                    "Linked" if profile.legacy_duo else "Managed")[index.column()]
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
               "border": "#394352", "accent": "#8DB7FF", "selected": "#2C4264", "buttonText": "#15191F"}
              if dark else
              {"canvas": "#F5F6F8", "surface": "#FFFFFF", "text": "#202631", "muted": "#596474",
               "border": "#D7DDE5", "accent": "#2458B8", "selected": "#E2EBFC", "buttonText": "#FFFFFF"})
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
        QLabel#heading { font-size: 28px; font-weight: 600; }
        QLabel#section { font-size: 18px; font-weight: 600; }
        QLabel[muted="true"] { color: %(muted)s; }
        QFrame#rail { background: %(surface)s; border-right: 1px solid %(border)s; }
        QFrame#inspector { background: %(surface)s; border: 1px solid %(border)s; border-radius: 6px; }
        QPushButton, QComboBox, QLineEdit { min-height: 32px; padding: 2px 10px;
            border: 1px solid %(border)s; border-radius: 6px; background: %(surface)s; color: %(text)s; }
        QPushButton:hover { background: %(selected)s; }
        QPushButton:checked { background: %(selected)s; font-weight: 600; }
        QPushButton[primary="true"] { background: %(accent)s; color: %(buttonText)s; border-color: %(accent)s; font-weight: 600; }
        QPushButton:disabled { color: %(muted)s; background: %(canvas)s; }
        QPushButton:focus, QComboBox:focus, QLineEdit:focus, QTableView:focus { border: 2px solid %(accent)s; }
        QTableView { background: %(surface)s; border: 1px solid %(border)s; border-radius: 6px;
            gridline-color: %(border)s; selection-background-color: %(selected)s; selection-color: %(text)s; }
        QHeaderView::section { background: %(canvas)s; color: %(muted)s; padding: 12px 8px;
            border: 0; border-bottom: 1px solid %(border)s; font-weight: 600; text-align: left; }
        QTableView::item { padding: 8px; }
        QScrollArea { border: 0; background: transparent; }
        QPlainTextEdit { background: %(surface)s; color: %(muted)s; border: 1px solid %(border)s; border-radius: 4px; padding: 6px; }
        QPlainTextEdit:focus { border: 2px solid %(accent)s; }
        QStatusBar { border-top: 1px solid %(border)s; padding: 6px 12px; }
    """ % colors)
