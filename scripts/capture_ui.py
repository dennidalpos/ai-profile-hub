"""Capture the Qt screens used in the README and setup guide, in dark, light, narrow and large-text variants."""

import argparse
import json
from pathlib import Path
import sys
from time import monotonic
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QItemSelectionModel
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from profile_switch.services import Availability, ProfileService
from profile_switch.store import Store
from profile_switch.ui import Launcher


DEMO_CLIENT = r'C:\Program Files\Demo Client\client.exe'


EXAMPLES = (
    ('gemini', 'cli', 'Antigravity', 'antigravity'),
    ('chatgpt', 'cli', 'Codex', 'codex'),
    ('claude', 'cli', 'Claude', 'claude'),
)


def capture(window, output, filename):
    window.statusBar().clearMessage()
    QApplication.processEvents()
    if not window.grab().save(str(output / filename)):
        raise OSError(f'Could not save {filename}.')


def save_profile(window):
    window.editor.save_button.click()
    deadline = monotonic() + 5
    while window.busy and monotonic() < deadline:
        QTest.qWait(20)
    if window.pages.currentWidget() is not window.profiles_page:
        raise RuntimeError('The profile editor did not return to the profile list after saving.')


VARIANTS = {
    # name: (theme, file suffix, system font in points or None, overview size, details size)
    'dark': ('Dark', 'dark', None, (1360, 700), (1360, 700)),
    'light': ('Light', 'light', None, (1360, 700), (1360, 700)),
    'narrow': ('Dark', 'dark-narrow', None, (900, 620), (900, 620)),
    'large': ('Dark', 'dark-large-text', 15.75, (1360, 760), (1360, 760)),
}
FORM_CAPTURES = {'dark'}


def run_variant(name, output):
    theme, suffix, font_points, overview, details = VARIANTS[name]
    if font_points:
        app = QApplication.instance()
        font = QFont(app.font())
        font.setPointSizeF(font_points)
        app.setFont(font)
    store = Store(Path('dist/visual-fixture') / uuid4().hex)
    store.save_setting('theme', theme)
    service = ProfileService(store)
    demo_running = lambda profiles: {p.id for p in profiles if p.name in ('Claude Work', 'Codex Personal')}
    with (patch.object(service, 'inspect', return_value=Availability(True, 'Client available', DEMO_CLIENT)),
          patch.object(service, 'running_profiles', side_effect=demo_running)):
        window = Launcher(store, service=service)
        window.resize(1100, 600)
        window.show()
        for product, client, prefix, filename in EXAMPLES:
            for who in ('Work', 'Personal'):
                window.new_profile()
                editor = window.editor
                editor.product.setCurrentIndex(editor.product.findData(product))
                editor.target.setCurrentIndex(editor.target.findData(client))
                editor.name.setText(f'{prefix} {who}')
                if who == 'Personal' and name in FORM_CAPTURES:
                    capture(window, output, f'new-{filename}-profile-dark.png')
                save_profile(window)
        if len(store.profiles()) != 6:
            raise RuntimeError('Expected six saved demo profiles.')
        window.resize(*overview)
        if overview[0] >= 1360:
            window.table.setColumnWidth(0, 176)
            window.table.setColumnWidth(1, 160)
            window.table.setColumnWidth(2, 266)
        selection = window.table.selectionModel()
        selection.clearSelection()
        for row in range(window.proxy.rowCount()):
            index = window.proxy.index(row, 0)
            if index.data().startswith('Codex '):
                selection.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        if len(window.selection()) != 2:
            raise RuntimeError('Expected both Codex profiles to be selected.')
        selection.setCurrentIndex(selection.selectedRows()[0], QItemSelectionModel.SelectionFlag.NoUpdate)
        window.model.set_running(demo_running(window.model.profiles))
        window.update_status_column()
        capture(window, output, f'profiles-{suffix}.png')
        overview_size = [window.width(), window.height()]
        selection.clearSelection()
        for row in range(window.proxy.rowCount()):
            index = window.proxy.index(row, 0)
            if index.data() == 'Claude Work':
                selection.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
        if len(window.selection()) != 1:
            raise RuntimeError('Expected one selected profile for the details capture.')
        QTest.qWait(50)
        # Deliver the mocked availability directly so the capture does not depend on thread timing.
        window.inspection_finished(window.inspect_generation, Availability(True, 'Client available', DEMO_CLIENT))
        if window.details_button.isVisible():
            window.details_button.click()
            QApplication.processEvents()
            if window.pages.currentWidget() is not window.details_page:
                raise RuntimeError('Expected the Details page in the narrow layout.')
        capture(window, output, f'profile-details-{suffix}.png')
        if window.pages.currentWidget() is window.details_page:
            window.show_profiles()
        window.resize(*details)
        window.show_settings()
        if name == 'dark':
            window.resize(1100, 720)
            capture(window, output, 'browser-settings-dark.png')
            capture(window, output, 'settings-dark.png')
        else:
            capture(window, output, f'settings-{suffix}.png')
        (output / ('capture.json' if name == 'dark' else f'capture-{suffix}.json')).write_text(json.dumps({
            'platform': sys.platform,
            'device_pixel_ratio': window.devicePixelRatioF(),
            'logical_size': overview_size,
            'browser_settings_logical_size': [window.width(), window.height()],
            'appearance': window.theme,
            'system_font_points': font_points,
            'data': 'synthetic profiles',
        }, indent=2) + '\n', encoding='utf-8')
        window.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('dist/evidence/ui'))
    parser.add_argument('--variant', action='append', choices=sorted(VARIANTS) + ['all'],
                        help='dark (default), light, narrow or large; repeat or use all')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    names = args.variant or ['dark']
    if 'all' in names:
        names = list(VARIANTS)
    app = QApplication([])
    app.setStyle('Fusion')
    default_font = QFont(app.font())
    for name in names:
        app.setFont(default_font)
        run_variant(name, args.output)


if __name__ == '__main__':
    main()
