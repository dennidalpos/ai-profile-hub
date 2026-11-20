"""Profile editor form."""

from pathlib import Path


from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLineEdit, QVBoxLayout, QWidget)

from .app import ERRORS
from .catalog import SERVICES, TARGETS
from .launch import resolve_executable, resolve_workdir
from .qt_support import (scaled)


from .ui_widgets import announce, button, label


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
        for field in (self.product, self.target, self.name):
            field.setMaximumWidth(scaled(480))
        form.addRow("Product", self.product)
        form.addRow("Client", self.target)
        form.addRow("Name", self.name)
        layout.addLayout(form)
        self.hint = label("", muted=True)
        layout.addWidget(self.hint)
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
        self.mark_saved()

    def values(self):
        return (self.product.currentData(), self.target.currentData(), self.name.text().strip(),
                self.binary.text().strip(), self.workdir.text().strip())

    def mark_saved(self):
        self.baseline = self.values()

    def modified(self):
        return self.values() != self.baseline

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
        row.setMaximumWidth(scaled(720))
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
