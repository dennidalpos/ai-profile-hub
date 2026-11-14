"""Single desktop interface for web, terminal and native app profiles."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .app import ERRORS
from .catalog import SERVICES, TARGETS
from .launch import executable, open_profile, resolve_executable, resolve_workdir
from .store import Store, data_root, duo_directory

BG = "#101622"
PANEL = "#192335"
FG = "#F1F5FC"
MUTED = "#AAB8D0"
ACCENT = "#B4CEFF"
ALL_PRODUCTS = "All products"


def launch_profiles(store, profiles, login):
    started = []
    failed = []
    for profile in profiles:
        try:
            open_profile(store, profile, login)
        except ERRORS as error:
            target = TARGETS[profile.service][profile.mode]
            failed.append(f"{profile.name} ({target.label})\n{error}")
        else:
            started.append(profile)
    return started, failed


class Launcher:
    def __init__(self, root, store):
        self.root = root
        self.store = store
        self.rows = {}
        self.busy = False
        self.worker = ThreadPoolExecutor(max_workers=1)
        root.bind("<Destroy>", self.close_worker, add=True)
        root.title("AI Profile Hub")
        root.geometry("920x570")
        root.minsize(710, 540)
        root.configure(background=BG)
        self.configure_style()
        menu = tk.Menu(root)
        settings = tk.Menu(menu, tearoff=False)
        settings.add_command(label="Choose Chrome or Chromium…", command=self.choose_browser)
        settings.add_command(label="Use browser auto-detection", command=self.reset_browser)
        if sys.platform == "win32" and duo_directory().is_dir():
            settings.add_command(label="Link the second Claude Desktop Duo profile…", command=self.import_duo)
        menu.add_cascade(label="Settings", menu=settings)
        root.configure(menu=menu)

        frame = ttk.Frame(root, padding=(30, 26))
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="AI Profile Hub", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Claude Code, Codex and Antigravity / Gemini", style="Muted.TLabel").pack(anchor="w", pady=(3, 20))
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 12))
        self.filter = tk.StringVar(value=ALL_PRODUCTS)
        self.filters = ttk.Combobox(toolbar, textvariable=self.filter, state="readonly", width=24,
                                    values=[ALL_PRODUCTS, *SERVICES.values()])
        self.filters.pack(side="left")
        self.filters.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.show_all_button = ttk.Button(toolbar, text="Show all products", command=self.show_all_products)
        self.new_button = ttk.Button(toolbar, text="New profile", style="Primary.TButton", command=self.edit)
        self.new_button.pack(side="right")
        self.settings = settings

        table_frame = ttk.Frame(frame)
        self.table = ttk.Treeview(table_frame, columns=("name", "service", "client"), show="headings", selectmode="extended")
        for key, label, width in (("name", "Profile", 210), ("service", "Product", 165), ("client", "Client", 300)):
            self.table.heading(key, text=label, anchor="w")
            self.table.column(key, width=width, minwidth=110, anchor="w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self.update_actions)
        self.table.bind("<Return>", lambda _event: self.launch())
        self.table.bind("<Double-Button-1>", self.open_clicked)

        actions = ttk.Frame(frame)
        self.open_button = ttk.Button(actions, text="Open profile", style="Primary.TButton", command=self.launch)
        self.open_button.pack(side="right")
        self.login_button = ttk.Button(actions, text="Sign in", command=lambda: self.launch(login=True))
        self.login_button.pack(side="right", padx=(0, 8))
        self.edit_button = ttk.Button(actions, text="Edit", command=lambda: self.edit(self.selected()))
        self.edit_button.pack(side="left")
        self.delete_button = ttk.Button(actions, text="Delete", command=self.delete)
        self.delete_button.pack(side="left", padx=(8, 0))
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status, style="Muted.TLabel", wraplength=650).pack(
            side="bottom", fill="x", pady=(12, 0))
        actions.pack(side="bottom", fill="x", pady=(13, 0))
        self.selection_name = tk.StringVar()
        ttk.Label(frame, textvariable=self.selection_name, wraplength=620, justify="left").pack(
            side="bottom", fill="x", pady=(6, 0))
        table_frame.pack(fill="both", expand=True)
        modifier = "Command" if sys.platform == "darwin" else "Control"
        root.bind(f"<{modifier}-n>", lambda _event: self.edit())
        self.refresh()
        self.table.focus_set()

    def configure_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG, font=("TkDefaultFont", 11))
        style.configure("Title.TLabel", font=("TkDefaultFont", 28, "bold"))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TButton", background=PANEL, foreground=FG, bordercolor=PANEL, padding=(13, 8))
        style.map("TButton", background=[("disabled", BG), ("active", "#2B3952")],
                  foreground=[("disabled", "#8291AA")])
        style.configure("Primary.TButton", background=ACCENT, foreground="#182438", bordercolor=ACCENT)
        style.map("Primary.TButton", background=[("disabled", PANEL), ("active", "#D6E4FF")])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                        borderwidth=0, rowheight=39, font=("TkDefaultFont", 11))
        style.configure("Treeview.Heading", background="#26334C", foreground=FG, padding=(10, 8), relief="flat")
        style.map("Treeview", background=[("selected", "#34528C")], foreground=[("selected", "#FFFFFF")])
        style.map("Treeview.Heading", background=[("active", "#314260")])
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=5)

    def selected(self):
        profiles = self.selection()
        return profiles[0] if len(profiles) == 1 else None

    def selection(self):
        return [self.rows[row] for row in self.table.selection() if row in self.rows]

    def show_all_products(self):
        self.filter.set(ALL_PRODUCTS)
        self.refresh()
        self.table.focus_set()

    def refresh(self, selected=None):
        product = self.filter.get()
        self.rows = {p.id: p for p in self.store.profiles()
                     if product in (ALL_PRODUCTS, SERVICES[p.service])}
        self.table.delete(*self.table.get_children())
        for profile in self.rows.values():
            target = TARGETS[profile.service][profile.mode]
            self.table.insert("", "end", iid=profile.id, values=(profile.name, SERVICES[profile.service], target.display))
        if self.rows:
            selected = selected if selected in self.rows else next(iter(self.rows))
            self.table.selection_set(selected)
            self.table.focus(selected)
            self.table.see(selected)
        self.show_all_button.pack_forget()
        if self.rows:
            notice = "Press Enter to open. Hold Ctrl (⌘ on Mac) to select multiple profiles."
        elif product == ALL_PRODUCTS:
            notice = "Create a profile to choose a client and sign in to your account."
        else:
            notice = f"No profiles for {product}."
            self.show_all_button.pack(side="left", padx=(8, 0))
        self.update_actions()
        self.status.set(notice)

    def update_actions(self, _event=None):
        profile = self.selected()
        count = len(self.selection())
        idle = not self.busy
        self.selection_name.set(profile.name if profile else "")
        self.show_all_button.configure(state="normal" if idle else "disabled")
        self.open_button.configure(state="normal" if idle and count else "disabled",
                                   text="Open selected" if count > 1 else "Open profile")
        state = "normal" if idle and profile else "disabled"
        for button in (self.edit_button, self.delete_button):
            button.configure(state=state)
        target = TARGETS[profile.service][profile.mode] if profile else None
        login = idle and target is not None and target.kind != "web"
        self.login_button.configure(state="normal" if login else "disabled")
        self.filters.configure(state="readonly" if idle else "disabled")
        self.new_button.configure(state="normal" if idle else "disabled")
        for index in range(self.settings.index("end") + 1):
            self.settings.entryconfigure(index, state="normal" if idle else "disabled")

    def close_worker(self, event):
        if event.widget is self.root:
            self.worker.shutdown(wait=False)

    def start_operation(self, notice, operation, finished, *args):
        self.busy = True
        self.status.set(notice)
        self.update_actions()
        future = self.worker.submit(operation, *args)
        self.root.after(40, self.poll_operation, future, finished)

    def poll_operation(self, future, finished):
        if not future.done():
            self.root.after(40, self.poll_operation, future, finished)
            return
        self.busy = False
        self.update_actions()
        finished(future)

    def open_clicked(self, event):
        row = self.table.identify_row(event.y)
        if row and not self.busy:
            self.table.selection_set(row)
            self.launch()

    def launch(self, login=False):
        profiles = self.selection()
        if self.busy or not profiles or (login and len(profiles) != 1):
            return
        notice = "Starting sign-in…" if login else "Opening profiles…"
        self.start_operation(notice, launch_profiles, self.launch_finished, self.store, profiles, login)

    def launch_finished(self, future):
        started, failed = future.result()
        if len(started) == 1 and not failed:
            status = f"Launch requested for “{started[0].name}”."
        else:
            status = f"Launch requested: {len(started)}. Failed: {len(failed)}."
        if any(TARGETS[p.service][p.mode].kind == "desktop" for p in started):
            status += " Verify the account in the desktop client."
        self.status.set(status)
        if failed:
            messagebox.showerror("Profile launch", "\n\n".join(failed), parent=self.root)

    def delete(self):
        profile = self.selected()
        if self.busy or profile is None:
            return
        kind = TARGETS[profile.service][profile.mode].kind
        close = {
            "web": "Close all browser windows for this profile first.",
            "cli": "Close the terminal running this profile first.",
            "desktop": "Close all desktop client windows for this profile first.",
        }[kind]
        if profile.legacy_duo:
            detail = "This removes the profile from the launcher. The original Claude Desktop Duo session stays in its folder."
        else:
            data = {
                "web": "This removes the local browser session and its data.",
                "cli": "This removes the client's local settings and sign-in data for this profile.",
                "desktop": "This removes the local client data stored by the launcher for this profile.",
            }[kind]
            detail = f"{data} Your online account stays active."
        if not messagebox.askyesno("Delete profile", f"Delete “{profile.name}”?\n\n{close}\n\n{detail}",
                                   default=messagebox.NO, icon=messagebox.WARNING, parent=self.root):
            return
        self.start_operation(f"Deleting “{profile.name}”…", self.store.delete,
                             lambda future: self.delete_finished(profile, future), profile)

    def delete_finished(self, profile, future):
        try:
            future.result()
        except ERRORS as error:
            self.status.set(f"Could not delete “{profile.name}”.")
            messagebox.showerror("Delete profile", str(error), parent=self.root)
            return
        self.refresh()
        self.status.set(f"Deleted “{profile.name}”.")

    def choose_browser(self):
        value = filedialog.askopenfilename(parent=self.root, title="Choose the Chrome or Chromium executable")
        if not value:
            return
        try:
            path = Path(value)
            if not executable(path):
                raise ValueError("Choose an executable file.")
            self.store.save_browser(path)
        except ERRORS as error:
            messagebox.showerror("Browser", str(error), parent=self.root)
            return
        self.status.set(f"Browser configured: {path.name}.")

    def reset_browser(self):
        try:
            self.store.clear_browser()
        except ERRORS as error:
            messagebox.showerror("Browser", str(error), parent=self.root)
            return
        self.status.set("Browser auto-detection enabled for the next web launch.")

    def import_duo(self):
        try:
            identifier = self.store.save("claude", "Claude Desktop Duo", "desktop", legacy_duo=True)
        except ERRORS as error:
            messagebox.showerror("Claude Desktop Duo", str(error), parent=self.root)
            return
        self.filter.set(SERVICES["claude"])
        self.refresh(identifier)
        self.status.set("Linked the second Claude Desktop Duo profile.")

    def edit(self, profile=None):
        if not self.busy:
            ProfileEditor(self, profile)


class ProfileEditor:
    def __init__(self, launcher, profile):
        self.launcher = launcher
        self.profile = profile
        self.dialog = tk.Toplevel(launcher.root, background=BG)
        self.dialog.title("Edit profile" if profile else "New profile")
        self.dialog.transient(launcher.root)
        self.dialog.resizable(False, False)
        self.dialog.grab_set()
        self.form = ttk.Frame(self.dialog, padding=22)
        self.form.pack(fill="both", expand=True)
        self.name = tk.StringVar(value=profile.name if profile else "")
        self.product = tk.StringVar(value=SERVICES[profile.service] if profile else (
            launcher.filter.get() if launcher.filter.get() in SERVICES.values() else SERVICES["claude"]))
        self.target = tk.StringVar()
        self.binary = tk.StringVar(value=profile.executable if profile else "")
        self.workdir = tk.StringVar(value=profile.workdir if profile else "")
        self.products = {label: key for key, label in SERVICES.items()}
        self.label("Name")
        name = ttk.Entry(self.form, textvariable=self.name, width=58)
        name.pack(fill="x", pady=(3, 10))
        self.label("Product")
        products = ttk.Combobox(self.form, textvariable=self.product, state="disabled" if profile else "readonly",
                                values=list(SERVICES.values()))
        products.pack(fill="x", pady=(3, 10))
        self.label("Client")
        self.targets = ttk.Combobox(self.form, textvariable=self.target, state="disabled" if profile else "readonly")
        self.targets.pack(fill="x", pady=(3, 10))
        if profile:
            ttk.Label(self.form, text="Create a new profile to use a different product or client.",
                      style="Muted.TLabel", wraplength=440).pack(anchor="w", pady=(0, 10))
        self.local = ttk.Frame(self.form)
        self.binary_entry = self.path_row("Local executable (optional)", self.binary, self.pick_binary)
        self.workdir_entry = self.path_row("Working directory (optional)", self.workdir, self.pick_workdir)
        self.hint = ttk.Label(self.form, style="Muted.TLabel", wraplength=440)
        self.hint.pack(anchor="w", pady=(0, 9))
        buttons = ttk.Frame(self.form)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Save", style="Primary.TButton", command=self.save).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.dialog.destroy).pack(side="right", padx=(0, 8))
        products.bind("<<ComboboxSelected>>", self.update_products)
        self.targets.bind("<<ComboboxSelected>>", self.update_target)
        self.dialog.bind("<Return>", self.save)
        self.dialog.bind("<Escape>", lambda _event: self.dialog.destroy())
        self.update_products()
        name.focus_set()
        name.selection_range(0, "end")

    def label(self, text):
        ttk.Label(self.form, text=text).pack(anchor="w")

    def path_row(self, label, variable, picker):
        ttk.Label(self.local, text=label).pack(anchor="w")
        row = ttk.Frame(self.local)
        row.pack(fill="x", pady=(3, 10))
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=picker).pack(side="right", padx=(6, 0))
        return entry

    def pick_binary(self):
        value = filedialog.askopenfilename(parent=self.dialog, title="Choose the installed executable")
        if value:
            self.binary.set(value)

    def pick_workdir(self):
        value = filedialog.askdirectory(parent=self.dialog, title="Choose the working directory")
        if value:
            self.workdir.set(value)

    def update_products(self, _event=None):
        targets = TARGETS[self.products[self.product.get()]]
        self.modes = {target.display: mode for mode, target in targets.items()}
        self.targets.configure(values=list(self.modes))
        self.target.set(targets[self.profile.mode].display if self.profile else next(iter(self.modes)))
        self.update_target()

    def update_target(self, _event=None):
        target = TARGETS[self.products[self.product.get()]][self.modes[self.target.get()]]
        self.local.pack_forget()
        if target.kind != "web":
            self.local.pack(fill="x", before=self.hint)
        if target.experimental:
            text = ("For the first sign-in, close other instances of this client and choose Sign in. Verify the account in the client."
                    if target.kind == "desktop" else
                    "The client opens with its own home directory. Verify the account shown in the terminal.")
        elif target.kind == "web":
            text = "The site opens in Chrome or Chromium with its own browser session."
        else:
            text = "The installed client opens in a dedicated terminal."
        self.hint.configure(text=text)

    def save(self, _event=None):
        service = self.products[self.product.get()]
        mode = self.modes[self.target.get()]
        local = TARGETS[service][mode].kind != "web"
        binary = self.binary.get().strip() if local else ""
        workdir = self.workdir.get().strip() if local else ""
        for value, entry, label, resolve in (
            (binary, self.binary_entry, "Local executable", resolve_executable),
            (workdir, self.workdir_entry, "Working directory", resolve_workdir),
        ):
            if not value:
                continue
            try:
                if not Path(value).expanduser().is_absolute():
                    raise ValueError("Enter an absolute path.")
                resolve(value)
            except (OSError, ValueError, RuntimeError) as error:
                messagebox.showerror(label, str(error), parent=self.dialog)
                entry.focus_set()
                return
        try:
            identifier = self.launcher.store.save(service, self.name.get(), mode,
                                                   executable=binary, workdir=workdir,
                                                   previous=self.profile,
                                                   legacy_duo=bool(self.profile and self.profile.legacy_duo))
        except ERRORS as error:
            messagebox.showerror("Profile", str(error), parent=self.dialog)
            return
        self.dialog.destroy()
        if self.launcher.filter.get() != ALL_PRODUCTS:
            self.launcher.filter.set(SERVICES[service])
        self.launcher.refresh(identifier)
        self.launcher.table.focus_set()


def run():
    root = tk.Tk()
    try:
        Launcher(root, Store(data_root()))
    except ERRORS as error:
        root.withdraw()
        messagebox.showerror("AI Profile Hub", str(error), parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0
