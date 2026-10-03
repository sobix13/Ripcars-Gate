#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x .venv/bin/python ]; then PYTHON_BIN=.venv/bin/python; fi
if [ "${1:-}" != "--offline" ]; then
    "$PYTHON_BIN" scripts/preflight.py --code-only
fi
"$PYTHON_BIN" -m compileall -q .
"$PYTHON_BIN" -m unittest discover -s tests -p 'test_*.py' -v
