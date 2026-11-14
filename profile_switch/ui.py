"""Single desktop interface for web, terminal and native app profiles."""

from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .app import ERRORS
from .catalog import SERVICES, TARGETS
from .launch import executable, open_profile
from .store import Store, data_root, duo_directory

BG = "#101622"
PANEL = "#192335"
FG = "#F1F5FC"
MUTED = "#AAB8D0"
ACCENT = "#B4CEFF"


class Launcher:
    def __init__(self, root, store):
        self.root = root
        self.store = store
        self.rows = {}
        root.title("AI Profile Hub")
        root.geometry("920x570")
        root.minsize(710, 480)
        root.configure(background=BG)
        self.configure_style()
        menu = tk.Menu(root)
        settings = tk.Menu(menu, tearoff=False)
        settings.add_command(label="Seleziona Chrome o Chromium…", command=self.choose_browser)
        if sys.platform == "win32" and duo_directory().is_dir():
            settings.add_command(label="Collega il secondo profilo di Claude Desktop Duo…", command=self.import_duo)
        menu.add_cascade(label="Impostazioni", menu=settings)
        root.configure(menu=menu)

        frame = ttk.Frame(root, padding=(30, 26))
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="AI Profile Hub", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Claude Code, Codex e Antigravity / Gemini", style="Muted.TLabel").pack(anchor="w", pady=(3, 20))
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 12))
        self.filter = tk.StringVar(value="Tutti i prodotti")
        filters = ttk.Combobox(toolbar, textvariable=self.filter, state="readonly", width=24,
                               values=["Tutti i prodotti", *SERVICES.values()])
        filters.pack(side="left")
        filters.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Button(toolbar, text="Nuovo profilo", style="Primary.TButton", command=self.edit).pack(side="right")

        table_frame = ttk.Frame(frame)
        table_frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table_frame, columns=("name", "service", "client"), show="headings", selectmode="extended")
        for key, label, width in (("name", "Profilo", 210), ("service", "Prodotto", 165), ("client", "Client", 300)):
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
        actions.pack(fill="x", pady=(13, 0))
        self.open_button = ttk.Button(actions, text="Apri profilo", style="Primary.TButton", command=self.launch)
        self.open_button.pack(side="right")
        self.login_button = ttk.Button(actions, text="Accedi", command=lambda: self.launch(login=True))
        self.login_button.pack(side="right", padx=(0, 8))
        self.edit_button = ttk.Button(actions, text="Modifica", command=lambda: self.edit(self.selected()))
        self.edit_button.pack(side="left")
        self.delete_button = ttk.Button(actions, text="Elimina", command=self.delete)
        self.delete_button.pack(side="left", padx=(8, 0))
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status, style="Muted.TLabel", wraplength=650).pack(anchor="w", pady=(12, 0))
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

    def refresh(self, selected=None):
        self.rows = {p.id: p for p in self.store.profiles()
                     if self.filter.get() in ("Tutti i prodotti", SERVICES[p.service])}
        self.table.delete(*self.table.get_children())
        for profile in self.rows.values():
            target = TARGETS[profile.service][profile.mode]
            self.table.insert("", "end", iid=profile.id, values=(profile.name, SERVICES[profile.service], target.display))
        if self.rows:
            selected = selected if selected in self.rows else next(iter(self.rows))
            self.table.selection_set(selected)
            self.table.focus(selected)
            self.table.see(selected)
        self.update_actions()
        self.status.set("Invio per aprire. Tieni premuto Ctrl (⌘ su Mac) per selezionare più profili." if self.rows else
                        "Crea un profilo per scegliere il client e accedere al tuo account.")

    def update_actions(self, _event=None):
        profile = self.selected()
        count = len(self.selection())
        self.open_button.configure(state="normal" if count else "disabled",
                                   text="Apri selezione" if count > 1 else "Apri profilo")
        state = "normal" if profile else "disabled"
        for button in (self.edit_button, self.delete_button):
            button.configure(state=state)
        target = TARGETS[profile.service][profile.mode] if profile else None
        login = target is not None and target.kind != "web"
        self.login_button.configure(state="normal" if login else "disabled")

    def open_clicked(self, event):
        row = self.table.identify_row(event.y)
        if row:
            self.table.selection_set(row)
            self.launch()

    def launch(self, login=False):
        profiles = self.selection()
        if not profiles or (login and len(profiles) != 1):
            return
        started = []
        failed = []
        for profile in profiles:
            try:
                open_profile(self.store, profile, login)
            except ERRORS as error:
                failed.append(f"{profile.name} ({SERVICES[profile.service]})\n{error}")
            else:
                started.append(profile)
        if failed:
            messagebox.showerror("Apertura dei profili", "\n\n".join(failed), parent=self.root)
        if started:
            names = ", ".join(f"«{profile.name}»" for profile in started)
            desktop = any(TARGETS[p.service][p.mode].kind == "desktop" for p in started)
            detail = " Verifica l’account nelle finestre desktop." if desktop else ""
            self.status.set(f"Avvio richiesto per {names}.{detail}")

    def delete(self):
        profile = self.selected()
        if profile is None:
            return
        detail = ("La sessione originale di Claude Desktop Duo resta nella sua cartella." if profile.legacy_duo else
                  "Verranno rimossi i dati locali di questo profilo. L’account online resta attivo.")
        if not messagebox.askyesno("Elimina profilo", f"Eliminare «{profile.name}»?\n\n{detail}",
                                   default=messagebox.NO, icon=messagebox.WARNING, parent=self.root):
            return
        try:
            self.store.delete(profile)
        except ERRORS as error:
            messagebox.showerror("Elimina profilo", str(error), parent=self.root)
            return
        self.refresh()
        self.status.set(f"Profilo «{profile.name}» eliminato.")

    def choose_browser(self):
        value = filedialog.askopenfilename(parent=self.root, title="Seleziona l’eseguibile di Chrome o Chromium")
        if not value:
            return
        try:
            path = Path(value)
            if not executable(path):
                raise ValueError("Seleziona un file eseguibile.")
            self.store.save_browser(path)
        except ERRORS as error:
            messagebox.showerror("Browser", str(error), parent=self.root)
            return
        self.status.set(f"Browser configurato: {path.name}.")

    def import_duo(self):
        try:
            identifier = self.store.save("claude", "Claude Desktop Duo", "desktop", legacy_duo=True)
        except ERRORS as error:
            messagebox.showerror("Claude Desktop Duo", str(error), parent=self.root)
            return
        self.filter.set(SERVICES["claude"])
        self.refresh(identifier)

    def edit(self, profile=None):
        ProfileEditor(self, profile)


class ProfileEditor:
    def __init__(self, launcher, profile):
        self.launcher = launcher
        self.profile = profile
        self.dialog = tk.Toplevel(launcher.root, background=BG)
        self.dialog.title("Modifica profilo" if profile else "Nuovo profilo")
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
        self.label("Nome")
        name = ttk.Entry(self.form, textvariable=self.name, width=58)
        name.pack(fill="x", pady=(3, 10))
        self.label("Prodotto")
        products = ttk.Combobox(self.form, textvariable=self.product, state="disabled" if profile else "readonly",
                                values=list(SERVICES.values()))
        products.pack(fill="x", pady=(3, 10))
        self.label("Client")
        self.targets = ttk.Combobox(self.form, textvariable=self.target, state="disabled" if profile else "readonly")
        self.targets.pack(fill="x", pady=(3, 10))
        self.local = ttk.Frame(self.form)
        self.path_row("Eseguibile locale (facoltativo)", self.binary, self.pick_binary)
        self.path_row("Cartella di lavoro (facoltativa)", self.workdir, self.pick_workdir)
        self.hint = ttk.Label(self.form, style="Muted.TLabel", wraplength=440)
        self.hint.pack(anchor="w", pady=(0, 9))
        buttons = ttk.Frame(self.form)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Salva", style="Primary.TButton", command=self.save).pack(side="right")
        ttk.Button(buttons, text="Annulla", command=self.dialog.destroy).pack(side="right", padx=(0, 8))
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
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Sfoglia…", command=picker).pack(side="right", padx=(6, 0))

    def pick_binary(self):
        value = filedialog.askopenfilename(parent=self.dialog, title="Seleziona l’eseguibile installato")
        if value:
            self.binary.set(value)

    def pick_workdir(self):
        value = filedialog.askdirectory(parent=self.dialog, title="Seleziona la cartella di lavoro")
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
            text = ("Per il primo login usa Accedi con le altre istanze desktop chiuse. Verifica l’account nel client."
                    if target.kind == "desktop" else
                    "Il client si apre con una home dedicata. Verifica l’account mostrato nel terminale.")
        elif target.kind == "web":
            text = "Il sito si apre in una finestra Chrome o Chromium con una sessione propria."
        else:
            text = "Il client installato si apre in un terminale dedicato."
        self.hint.configure(text=text)

    def save(self, _event=None):
        service = self.products[self.product.get()]
        mode = self.modes[self.target.get()]
        local = TARGETS[service][mode].kind != "web"
        try:
            identifier = self.launcher.store.save(service, self.name.get(), mode,
                                                   executable=self.binary.get().strip() if local else "",
                                                   workdir=self.workdir.get().strip() if local else "",
                                                   previous=self.profile,
                                                   legacy_duo=bool(self.profile and self.profile.legacy_duo))
        except ERRORS as error:
            messagebox.showerror("Profilo", str(error), parent=self.dialog)
            return
        self.dialog.destroy()
        if self.launcher.filter.get() != "Tutti i prodotti":
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
