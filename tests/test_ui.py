from threading import Event, get_ident
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

try:
    import tkinter as tk
    from profile_switch import ui
except ImportError:
    tk = None

from profile_switch.store import Profile


@unittest.skipIf(tk is None, "Tkinter is unavailable")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(self.root.destroy)
        self.first = Profile("first", "claude", "W" * 48, "cli")
        self.second = Profile("second", "claude", "Second", "web")
        self.profiles = [self.first, self.second]
        self.store = SimpleNamespace(profiles=self.profiles.copy)
        self.app = ui.Launcher(self.root, self.store)
        self.root.geometry("710x480")
        self.root.update()

    def pump(self, until):
        deadline = monotonic() + 3
        while not until():
            self.assertLess(monotonic(), deadline, self.app.status.get())
            self.root.update()
            sleep(0.01)

    def test_launch_stays_responsive_and_reports_latest_batch(self):
        entered, release = Event(), Event()
        ui_thread = get_ident()
        handed_off = []

        def open_profile(store, profile, login):
            self.assertNotEqual(get_ident(), ui_thread)
            handed_off.append(profile.id)
            entered.set()
            self.assertTrue(release.wait(3))
            if profile == self.second:
                raise OSError("Synthetic failure")

        self.app.table.selection_set(self.first.id, self.second.id)
        self.app.table.focus_force()
        self.root.update()
        with (patch.object(ui, "open_profile", side_effect=open_profile) as launch,
              patch.object(ui.messagebox, "showerror") as error):
            self.app.table.event_generate("<Return>")
            try:
                self.pump(entered.is_set)
                self.assertTrue(self.app.open_button.instate(["disabled"]))
                self.assertTrue(self.app.open_button.winfo_ismapped())
                self.assertEqual(self.app.status.get(), "Opening profiles…")
                self.app.table.event_generate("<Return>")
                timer = Event()
                self.root.after(0, timer.set)
                self.pump(timer.is_set)
                self.assertEqual(handed_off, [self.first.id])
            finally:
                release.set()
            self.pump(lambda: error.call_count == 1)
            self.assertEqual(self.app.status.get(), "Launch requested: 1. Failed: 1.")
            self.assertIn("Second", error.call_args.args[1])

            launch.side_effect = OSError("Synthetic total failure")
            self.app.open_button.invoke()
            self.pump(lambda: error.call_count == 2)
            self.assertEqual(self.app.status.get(), "Launch requested: 0. Failed: 2.")
            self.assertEqual(launch.call_count, 4)

    def test_delete_runs_off_thread_and_reports_failure_on_ui_thread(self):
        entered, release = Event(), Event()
        ui_thread = get_ident()

        def delete(profile):
            self.assertNotEqual(get_ident(), ui_thread)
            entered.set()
            self.assertTrue(release.wait(3))
            self.profiles.remove(profile)

        self.store.delete = Mock(side_effect=delete)
        with patch.object(ui.messagebox, "askyesno", return_value=True) as confirm:
            self.app.delete_button.invoke()
            try:
                self.pump(entered.is_set)
                self.app.delete()
                confirm.assert_called_once()
                self.assertTrue(self.app.delete_button.instate(["disabled"]))
                timer = Event()
                self.root.after(0, timer.set)
                self.pump(timer.is_set)
            finally:
                release.set()
            self.pump(lambda: len(self.app.rows) == 1)
            self.store.delete.assert_called_once_with(self.first)

            self.store.delete.side_effect = OSError("Synthetic busy profile")
            reporting_threads = []
            with patch.object(ui.messagebox, "showerror", side_effect=lambda *args, **kwargs:
                              reporting_threads.append(get_ident())):
                self.app.delete_button.invoke()
                self.pump(lambda: bool(reporting_threads))
            self.assertEqual(reporting_threads, [ui_thread])
            self.assertEqual(self.app.status.get(), "Could not delete “Second”.")
            self.assertEqual(self.app.selected(), self.second)
