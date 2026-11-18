"""Qt presentation models, worker bridge and application palette."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPoint, QRect, QRunnable, QSize, Qt, Signal
from PySide6.QtGui import QAccessible, QColor, QFont, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import QAccessibleWidget, QLabel, QLayout, QPushButton, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QApplication

from .catalog import SERVICES, TARGETS


class FlowLayout(QLayout):
    """Lays widgets out left to right and wraps to a new row when the width runs out."""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self.items = []
        self.gap = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.arrange(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def arrange(self, rect, apply):
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, row = area.x(), area.y(), 0
        for item in self.items:
            if item.widget() is not None and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x, y, row = area.x(), y + row + self.gap, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.gap
            row = max(row, hint.height())
        return y + row - rect.y() + margins.bottom()


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
    headers = ("Profile", "Product", "Client", "Status", "Source")
    STATUS = 3

    def __init__(self):
        super().__init__()
        self.profiles = []
        self.running = frozenset()

    def set_running(self, identifiers):
        identifiers = frozenset(identifiers)
        if identifiers != self.running:
            self.running = identifiers
            if self.profiles:
                self.dataChanged.emit(self.index(0, self.STATUS), self.index(len(self.profiles) - 1, self.STATUS))

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
            running = "Running" if profile.id in self.running else ""
            return (profile.name, SERVICES[profile.service], target.label, running, "Managed")[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            running = "Running now" if profile.id in self.running else ""
            return (profile.name, SERVICES[profile.service], target.display, running, "Managed")[index.column()]
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


THEME = {}  # the active palette from apply_theme, shared with custom-painted widgets
BODY_POINTS = 10.5  # 14 px at 96 dpi


def scaled(pixels):
    """A design pixel size multiplied by the text scale of the system font (1.0 at the default size)."""
    return round(pixels * THEME.get("scale", 1.0))


class StatusPillDelegate(QStyledItemDelegate):
    """Draws a non-empty status text as a green pill."""

    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text:
            return super().paint(painter, option, index)
        plain = QStyleOptionViewItem(option)
        self.initStyleOption(plain, index)
        plain.text = ""
        style = plain.widget.style() if plain.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, plain, painter, plain.widget)
        # Same ok* roles as the green status badges, so the pill matches in both appearances.
        text_color = QColor(THEME.get("okText", "#14683A"))
        fill = QColor(THEME.get("okBg", "#E2F4E9"))
        border = QColor(THEME.get("okBorder", "#A5D5B8"))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(option.font)
        font.setPointSizeF(BODY_POINTS * THEME.get("scale", 1.0) * 12 / 14)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        width = min(option.rect.width() - 8, metrics.horizontalAdvance(text) + 20)
        height = min(option.rect.height() - 10, metrics.height() + 6)
        rect = option.rect.adjusted(4, 0, 0, 0)
        rect.setWidth(width)
        rect.setHeight(height)
        rect.moveTop(option.rect.top() + (option.rect.height() - height) // 2)
        painter.setPen(border)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, height / 2, height / 2)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


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
    # Follow the system font: the design's 14 px body (10.5 pt) is the floor, a larger system font scales the
    # text and every size derived from it (controls, rail, rows) with it.
    system_size = app.font().pointSizeF()
    body = max(BODY_POINTS, system_size if system_size > 0 else BODY_POINTS)
    THEME.clear()
    THEME.update(colors)
    THEME["scale"] = body / BODY_POINTS
    sizes = {"body": round(body, 1), "heading": round(body * 22 / 14, 1), "sectionSize": round(body * 18 / 14, 1),
             "small": round(body * 12 / 14, 1), "control": scaled(28), "controlSmall": scaled(24)}
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
        QWidget { font-size: %(body)spt; }
        QMainWindow, QWidget#workspace { background: %(canvas)s; }
        QLabel#heading { font-size: %(heading)spt; font-weight: 600; }
        QLabel#section { font-size: %(sectionSize)spt; font-weight: 600; }
        QLabel[muted="true"] { color: %(muted)s; }
        QLabel#statusBadge { background: %(selected)s; color: %(text)s; border: 1px solid %(border)s;
            border-radius: 9px; padding: 1px 9px; font-size: %(small)spt; font-weight: 600; }
        QLabel#statusBadge[tone="success"] { background: %(okBg)s; color: %(okText)s; border-color: %(okBorder)s; }
        QLabel#statusBadge[tone="warning"] { background: %(warnBg)s; color: %(warnText)s; border-color: %(warnBorder)s; }
        QLabel#statusBadge[tone="danger"] { background: %(errBg)s; color: %(errText)s; border-color: %(errBorder)s; }
        QLabel#statusBadge[tone="info"] { background: %(infoBg)s; color: %(infoText)s; border-color: %(infoBorder)s; }
        QLabel[caption="true"] { color: %(muted)s; font-size: %(small)spt; }
        QFrame#rail { background: %(surface)s; border-right: 1px solid %(border)s; }
        QFrame#inspector { background: %(surface)s; border: 1px solid %(border)s; border-radius: 6px; }
        QPushButton, QComboBox, QLineEdit { min-height: %(control)spx; padding: 1px 10px;
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
        QPushButton[role="small"] { min-height: %(controlSmall)spx; padding: 0 6px; font-size: %(small)spt; border-color: transparent;
            background: transparent; color: %(accent)s; text-decoration: underline; }
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
    """ % {**colors, **sizes})
