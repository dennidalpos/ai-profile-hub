#!/usr/bin/env sh
set -eu
cd -- "$(dirname -- "$0")"
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python scripts/build.py "$@"
fi
exec "${PYTHON:-python3}" scripts/build.py "$@"
