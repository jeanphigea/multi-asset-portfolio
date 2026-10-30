#!/bin/bash
# Multi-Asset Portfolio launcher — uses a private Python (3.11+) environment outside iCloud
set -e
cd "$(dirname "$0")"
VENV="$HOME/.venvs/multi-asset-portfolio"

ok_py() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; }

# Recreate the environment if it was built with a Python older than 3.11
if [ -x "$VENV/bin/python" ] && ! ok_py "$VENV/bin/python"; then rm -rf "$VENV"; fi

if [ ! -x "$VENV/bin/python" ]; then
  PY=""
  for c in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3 \
           /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/3.1*/bin/python3 \
           "$HOME"/.pyenv/shims/python3 python3.13 python3.12 python3.11 python3; do
    p=$(command -v "$c" 2>/dev/null || true)
    if [ -n "$p" ] && ok_py "$p"; then PY="$p"; break; fi
  done
  if [ -z "$PY" ]; then
    echo "❌  Needs Python 3.11 or newer, but only $(python3 --version 2>&1) was found."
    echo "    Install one (e.g. 'brew install python' or python.org), then run this again."
    exit 1
  fi
  echo "Creating Python environment with $PY …"
  "$PY" -m venv "$VENV"
fi

if ! "$VENV/bin/python" -c "import flask, requests, yfinance" 2>/dev/null; then
  echo "Installing dependencies…"
  "$VENV/bin/python" -m pip install -q --upgrade pip
  "$VENV/bin/python" -m pip install -q -r requirements.txt
fi
echo ""
echo "🚀  Starting Multi-Asset Portfolio at http://localhost:5050"
echo "   Press Ctrl+C to stop"
echo ""
(sleep 2; open "http://localhost:5050") &
exec "$VENV/bin/python" app.py
