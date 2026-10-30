"""
Load a portfolio file into the store, and optionally fill it with market data.

    python scripts/seed.py                    # data/demo.json, only if the store is empty
    python scripts/seed.py --force            # overwrite positions even if some exist
    python scripts/seed.py --refresh          # then fetch prices, history, fundamentals, quality
    python scripts/seed.py --file mine.json   # a different portfolio file (same shape as demo.json)

The store comes from the environment (see store.get_store): set
UPSTASH_REDIS_REST_URL/_TOKEN and STORE_PREFIX to seed a Redis-backed demo from
your machine, where no serverless time limit applies.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portfolio as pf  # noqa: E402
from store import get_store  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", type=Path, default=pf.DEMO_FILE)
    ap.add_argument("--force", action="store_true", help="overwrite existing positions")
    ap.add_argument("--refresh", action="store_true", help="fetch all market data afterwards")
    args = ap.parse_args()

    store = get_store()
    where = f"{type(store).__name__} (prefix {store.prefix!r})"
    if pf.is_empty(store) or args.force:
        pf.seed(store, args.file)
        print(f"seeded {args.file.name} into {where}")
    else:
        print(f"{where} already has positions; use --force to overwrite")

    if args.refresh:
        from app import REFRESH          # imported late: app reads the environment
        for part, fn in REFRESH.items():
            t = time.time()
            res = fn(store)
            n = res.get("refreshed", res.get("updated"))
            print(f"{part:<13} {n}  ({len(res.get('errors', []))} errors, {time.time() - t:.0f}s)")
