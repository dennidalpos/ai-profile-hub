"""Keep every test away from the real user profile, data folder and registry-backed locations."""

import os
from pathlib import Path
import tempfile

_ROOT = Path(tempfile.mkdtemp(prefix="ai-hub-tests-"))
for _name, _folder in (("HOME", "home"), ("USERPROFILE", "home"), ("LOCALAPPDATA", "local"),
                       ("APPDATA", "roaming"), ("XDG_DATA_HOME", "xdg")):
    (_ROOT / _folder).mkdir(exist_ok=True)
    os.environ[_name] = str(_ROOT / _folder)
