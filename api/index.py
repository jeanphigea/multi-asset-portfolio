"""Vercel entry point (see vercel.json). The rewritten path is restored inside
app.py, so this works whether Vercel loads this file or app.py directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: E402,F401
