"""Small widgets and helpers shared by the Hub window."""



from PySide6.QtCore import QSortFilterProxyModel, QTimer, Qt
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from .catalog import SERVICES, TARGETS
from .qt_support import (ElidedLabel, HeadingLabel, set_property)




def label(text, heading=False, muted=False):
    widget = HeadingLabel(text) if heading else QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if heading:
        widget.setObjectName("heading")
    if muted:
        widget.setProperty("muted", True)
    return widget


def section(text):
    """Heading of a settings group, in the section style of the design system."""
    widget = label(text)
    widget.setObjectName("section")
    return widget


def button(text, callback, primary=False, role=None):
    """role: None (outlined), "flat" (no frame), "small" (link-like) or "danger" (destructive)."""
    widget = QPushButton(text)
    widget.setProperty("primary", primary)
    if role:
        widget.setProperty("role", role)
    widget.clicked.connect(callback)
    return widget


def announce(widget, message):
    QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(widget, message))


def status_badge(text="", tone="neutral"):
    """tone: neutral, success, warning, danger or info; the style sheet gives each its own colours."""
    widget = label(text)
    widget.setWordWrap(False)
    widget.setObjectName("statusBadge")
    widget.setProperty("tone", tone)
    return widget


def set_badge(widget, text, tone):
    widget.setText(text)
    set_property(widget, "tone", tone)


class DetailRow(QWidget):
    """One fact in the inspector; long values are shortened in the middle and can be copied."""

    def __init__(self, caption, copy=False):
        super().__init__()
        self.caption = label(caption)
        self.caption.setWordWrap(False)
        self.caption.setProperty("caption", True)
        self.value = ElidedLabel()
        self.value.setAccessibleName(caption)
        self.copy_button = None
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        head = QHBoxLayout()
        head.addWidget(self.caption)
        head.addStretch()
        if copy:
            self.copy_button = button("Copy", self.copy_value, role="small")
            self.copy_button.setAccessibleName(f"Copy {caption.lower()}")
            head.addWidget(self.copy_button)
        layout.addLayout(head)
        layout.addWidget(self.value)
        layout.setContentsMargins(0, 0, 0, 0)
        self.hide()

    def set_value(self, text):
        self.value.set_full_text(text)
        self.setVisible(bool(text))

    def copy_value(self):
        QApplication.clipboard().setText(self.value.full_text())
        self.copy_button.setText("Copied")
        QTimer.singleShot(1500, self, self.reset_copy)

    def reset_copy(self):
        self.copy_button.setText("Copy")


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
