"""
One-off: copy a database from the old SQLite version of the app (etf.db) into
the key/value store. The SQLite file is only read, never changed.

    python scripts/migrate_sqlite.py path/to/etf.db [--to path/to/store.db]

Without --to it writes to the store selected by the environment (see
store.get_store), so pointing UPSTASH_REDIS_REST_URL/_TOKEN at a database
migrates straight into Redis.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import FileStore, get_store  # noqa: E402

FUND_COLS = ("yahoo_ticker", "roe", "fcf_margin", "de", "eps_growth", "net_margin", "div_yield", "beta", "pe",
             "gross_margin", "rev_growth", "peg", "ev_ebitda", "payout", "m12_change", "target_upside",
             "rec_mean", "sector", "industry", "country", "updated_at")


def rows(db, sql):
    try:
        return [dict(r) for r in db.execute(sql)]
    except sqlite3.OperationalError:          # table absent in an older database
        return []


def migrate(src: Path) -> dict:
    db = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    docs = {}

    docs["etfs"] = [{k: r[k] for k in ("ticker", "shares", "last_price_gbp", "last_price_date",
                                       "added_at", "updated_at")}
                    for r in rows(db, "SELECT * FROM portfolio ORDER BY ticker")]
    docs["stocks"] = [{k: r.get(k) for k in ("ticker", "name", "quantity", "last_price", "currency",
                                             "cost_basis_local", "isin", "updated_at")}
                      for r in rows(db, "SELECT * FROM stock_holdings ORDER BY ticker")]
    docs["fx"] = {r["currency"]: r["rate_to_gbp"] for r in rows(db, "SELECT * FROM fx_rates")}

    by_etf: dict[str, list] = {}
    for r in rows(db, "SELECT * FROM holdings ORDER BY etf_ticker, weight_pct DESC"):
        by_etf.setdefault(r["etf_ticker"].upper(), []).append(r)
    for etf, hs in by_etf.items():
        # The new model keeps one as-of date and source per fund: take the most common.
        docs[f"holdings:{etf}"] = {
            "as_of": Counter(h["as_of_date"] for h in hs).most_common(1)[0][0],
            "source": Counter(h["source"] for h in hs).most_common(1)[0][0],
            "rows": [{"name": h["holding_name"], "ticker": h["holding_ticker"] or "", "weight": h["weight_pct"]}
                     for h in hs]}

    docs["fundamentals"] = {r["key"]: {"key": r["key"], **{c: r.get(c) for c in FUND_COLS}}
                            for r in rows(db, "SELECT * FROM fundamentals")}
    docs["quality"] = {r["key"]: {**{k: r[k] for k in ("key", "yahoo_ticker", "q_score", "p_returns",
                                                       "p_consistency", "p_moat", "p_balance", "p_capital",
                                                       "years", "updated_at")},
                                  "detail": json.loads(r["detail"] or "{}")}
                       for r in rows(db, "SELECT * FROM quality")}
    docs["yahoo_resolution"] = {r["key"]: {"yahoo_ticker": r["yahoo_ticker"], "ok": bool(r["ok"]),
                                           "resolved_at": r["resolved_at"]}
                                for r in rows(db, "SELECT * FROM yahoo_resolution")}
    docs["ai_maturity"] = {r["key"]: {"score5": r["score5"], "dims": json.loads(r["dims"]) if r["dims"] else None,
                                      "provenance": r["provenance"], "source": r["source"], "as_of": r["as_of"]}
                           for r in rows(db, "SELECT * FROM ai_maturity WHERE score5 IS NOT NULL")}
    docs["compute_asset"] = {r["key"]: {k: r[k] for k in ("cap", "pwr", "pipe", "price", "mult", "source", "as_of")}
                             for r in rows(db, "SELECT * FROM compute_asset WHERE cap IS NOT NULL")}
    return docs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sqlite", type=Path)
    ap.add_argument("--to", type=Path, help="FileStore path (default: the environment's store)")
    args = ap.parse_args()
    docs = migrate(args.sqlite)
    store = FileStore(args.to, prefix=get_store().prefix) if args.to else get_store()
    store.set_many(docs)
    n_hold = sum(len(v["rows"]) for k, v in docs.items() if k.startswith("holdings:"))
    print(f"etfs {len(docs['etfs'])}, stocks {len(docs['stocks'])}, holdings rows {n_hold}, "
          f"fundamentals {len(docs['fundamentals'])}, quality {len(docs['quality'])} -> {type(store).__name__}")
