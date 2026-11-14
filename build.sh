#!/usr/bin/env sh
set -eu
cd -- "$(dirname -- "$0")"
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python build.py "$@"
fi
exec "${PYTHON:-python3}" build.py "$@"
