"""
Private additions to the reference data, kept out of git.

The public reference data covers the demo portfolio. Your own holdings usually
need more: Yahoo symbols for your stocks and ETFs, sector/country profiles for
companies only your funds reach, broker ISIN overrides. Put those in
.data/reference.json (git-ignored) and they are merged in at start-up, so the
repo never reveals what you own.

    {"YAHOO_STOCK": {"PG": "PG"}, "COMPANY_PROFILES": {"procter & gamble": ["Consumer Staples", "United States"]}}

Each top-level name is one of the tables merged at the bottom of reference.py,
names.py or ibkr.py: dicts are merged over the public ones, lists are added
to sets. LOCAL_REFERENCE overrides the path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PATH = Path(os.environ.get("LOCAL_REFERENCE", Path(__file__).with_name(".data") / "reference.json"))

_data: dict | None = None


def _load() -> dict:
    global _data
    if _data is None:
        try:
            _data = json.loads(PATH.read_text())
        except FileNotFoundError:
            _data = {}
    return _data


def merge(name: str, base, tuples: bool = False):
    """Extend `base` in place with the private entries for `name`; returns it."""
    extra = _load().get(name)
    if not extra:
        return base
    if isinstance(base, dict):
        base.update({k: tuple(v) if tuples else v for k, v in extra.items()})
    else:                                   # set
        base.update(extra)
    return base
