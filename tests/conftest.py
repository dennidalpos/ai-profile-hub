"""Keep every test away from the real user profile, data folder and registry-backed locations."""

import os
from pathlib import Path
import tempfile

_ROOT = Path(tempfile.mkdtemp(prefix="ai-hub-tests-"))
for _name, _folder in (("HOME", "home"), ("USERPROFILE", "home"), ("LOCALAPPDATA", "local"),
                       ("APPDATA", "roaming"), ("XDG_DATA_HOME", "xdg")):
    (_ROOT / _folder).mkdir(exist_ok=True)
    os.environ[_name] = str(_ROOT / _folder)

# A developer shell may route its own client through a gateway; launches refuse those, so tests start without them.
for _name in ("ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "OPENAI_BASE_URL",
              "OPENAI_API_BASE", "GOOGLE_GEMINI_BASE_URL", "GOOGLE_VERTEX_BASE_URL", "GEMINI_CLI_CUSTOM_HEADERS"):
    os.environ.pop(_name, None)
