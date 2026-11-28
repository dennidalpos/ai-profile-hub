"""Dialogs for importing and exporting client settings."""



from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QProgressBar, QVBoxLayout)

from .transfer import IMPORT, format_size


from .ui_widgets import button, label


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
