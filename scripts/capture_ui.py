"""Capture the real Qt UI with persistent, synthetic-only fixture data."""

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from profile_switch.store import Store
from profile_switch.ui import Launcher
from profile_switch.services import Availability, OperationResult


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('dist/evidence/ui'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle('Fusion')
    store = Store(Path('dist/visual-fixture'))
    duo = Path('dist/visual-fixture/SecondProfile')
    duo.mkdir(exist_ok=True)
    # Discovery references only synthetic fixture folders during capture.
    patches = [patch('profile_switch.ui.duo_directory', return_value=duo),
               patch('profile_switch.store.duo_directory', return_value=duo),
               patch('profile_switch.services.duo_directory', return_value=duo)]
    for replacement in patches:
        replacement.start()
    if not store.profiles():
        store.save('claude', 'Editorial review', 'desktop', executable=str(Path('dist/visual-fixture/missing-claude.exe').absolute()))
        store.save('claude', 'Research', 'cli')
        store.save('chatgpt', 'Sandbox', 'web')
        store.save('gemini', 'Experiments', 'gemini-cli')
    window = Launcher(store)
    window.resize(1360, 880)
    window.table.setColumnWidth(1, 172)
    window.show()
    (args.output / 'capture.json').write_text(json.dumps({
        'platform': sys.platform, 'device_pixel_ratio': window.devicePixelRatioF(),
        'logical_size': [window.width(), window.height()], 'data': 'synthetic fixtures only',
    }, indent=2), encoding='utf-8')
    release = Event()
    selected = next(p for p in store.profiles() if p.name == 'Research')
    def synthetic_availability(_profile):
        return Availability(True, 'Client available', 'Synthetic client fixture')
    # Capture selected and operational states against deterministic synthetic clients.
    window.service.inspect = synthetic_availability
    def synthetic_launch(profiles, login):
        release.wait(5)
        return [OperationResult(p.id, p.name, False, 'Synthetic client is unavailable.', 'Edit the executable path, then choose Retry failed.') for p in profiles]
    window.service.launch = synthetic_launch
    def profiles():
        window.change_theme('Light')
        window.clear_filters()
        window.select_id(selected.id)
        QTimer.singleShot(150, themed_profiles)
    def themed_profiles():
        window.grab().save(str(args.output / 'profiles-light.png'))
        window.change_theme('Dark')
        app.processEvents()
        window.grab().save(str(args.output / 'profiles-dark.png'))
        window.change_theme('Light')
        window.new_profile()
        window.editor.name.setText('Work')
        QTimer.singleShot(150, editor)
    def editor():
        window.grab().save(str(args.output / 'profile-editor.png'))
        window.show_profiles()
        window.search.setText('No matching synthetic profile')
        app.processEvents()
        window.grab().save(str(args.output / 'empty-filter.png'))
        window.clear_filters()
        window.resize(800, 600)
        app.processEvents()
        window.grab().save(str(args.output / 'profiles-compact.png'))
        window.show_settings()
        app.processEvents()
        window.grab().save(str(args.output / 'settings.png'))
        window.resize(1220, 760)
        window.show_profiles()
        window.select_id(selected.id)
        QTimer.singleShot(200, inspector)
    def inspector():
        window.grab().save(str(args.output / 'profile-details.png'))
        window.resize(800, 600)
        window.show_details()
        QTimer.singleShot(150, narrow_details)
    def narrow_details():
        window.grab().save(str(args.output / 'profile-details-compact.png'))
        window.show_profiles()
        window.launch()
        QTimer.singleShot(150, loading)
    def loading():
        window.grab().save(str(args.output / 'opening-profiles.png'))
        release.set()
        QTimer.singleShot(200, failed)
    def failed():
        window.grab().save(str(args.output / 'launch-failure.png'))
        window.show_settings()
        window.report_error(ValueError('Synthetic session folder is unavailable. Restore the folder and retry linking.'))
        QTimer.singleShot(150, error)
    def error():
        window.grab().save(str(args.output / 'settings-error.png'))
        window.close()
        app.quit()
    QTimer.singleShot(200, profiles)
    app.exec()
    for replacement in patches:
        replacement.stop()


if __name__ == '__main__':
    main()
