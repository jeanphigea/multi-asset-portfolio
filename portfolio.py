"""
Positions and their look-through.

The store holds two position lists:

  etfs    [{ticker, shares, last_price_gbp, last_price_date, yahoo?}]
          ETF prices are always kept in GBP.
  stocks  [{ticker, name, quantity, last_price, currency, cost_basis_local, isin?, yahoo?}]
          Direct holdings are priced in their own listing currency and converted
          with `fx` (1 unit -> GBP; "GBp" is pence, 0.01).

plus one `holdings:<ETF>` document per fund: {as_of, source, rows: [{name, ticker, weight}]},
weight in percent of the fund. Providers publish only their largest holdings, so
the rows usually sum to less than 100.

The browser does the company-level aggregation (see spec/04); this module
serves the inputs in one call and values positions for the risk model.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import reference as ref
from names import display_name

DEMO_FILE = Path(__file__).with_name("data") / "demo.json"
DEFAULT_FX = {"GBP": 1.0, "GBp": 0.01, "USD": 0.79, "EUR": 0.843, "HKD": 0.098}
SUMMARY_HOLDINGS = 50          # rows per ETF sent to the browser


def now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


# ── Reading ──────────────────────────────────────────────────────────────────

def load(store) -> dict:
    d = store.get_many(["etfs", "stocks", "fx"])
    return {"etfs": d.get("etfs", []), "stocks": d.get("stocks", []),
            "fx": {**DEFAULT_FX, **d.get("fx", {})}}


def holdings(store, tickers: list[str]) -> dict[str, dict]:
    docs = store.get_many([f"holdings:{t.upper()}" for t in tickers])
    return {t: docs.get(f"holdings:{t.upper()}") or {"rows": []} for t in tickers}


def stock_value_gbp(s: dict, fx: dict) -> float:
    return (s.get("quantity") or 0) * (s.get("last_price") or 0) * fx.get(s.get("currency"), 1.0)


def etf_symbol(e: dict) -> str:
    """A UCITS ETF bought by a sterling investor is almost always London-listed,
    so an unmapped ticker is tried as <ticker>.L."""
    t = e["ticker"].upper()
    return e.get("yahoo") or ref.YAHOO_ETF.get(t) or f"{t}.L"


def stock_symbol(s: dict) -> str | None:
    return s.get("yahoo") or ref.YAHOO_STOCK.get(s["ticker"])


def summary(store) -> list[dict]:
    """
    Every ETF with its holdings, plus one synthetic "DIRECT" fund for the
    direct stocks. DIRECT is shaped like an ETF (weight % of a basket whose
    "shares" is its GBP value at a price of 1) so the browser can look through
    both with the same code: value of a holding = weight/100 x shares x price.
    """
    p = load(store)
    docs = holdings(store, [e["ticker"] for e in p["etfs"]])
    out = []
    for e in sorted(p["etfs"], key=lambda e: e["ticker"]):
        doc = docs[e["ticker"]]
        rows = sorted(doc.get("rows", []), key=lambda r: -r["weight"])
        out.append({
            "ticker": e["ticker"], "shares": e["shares"],
            "last_price_gbp": e.get("last_price_gbp"), "last_price_date": e.get("last_price_date"),
            "total_covered_pct": round(sum(r["weight"] for r in rows), 2),
            "is_direct": False,
            # Display names are canonicalised on the way out so an ETF constituent
            # reads the same as the equivalent direct holding ("Samsung
            # Electronics Co., Ltd." -> "Samsung Electronics").
            "holdings": [{"holding_name": display_name(r["name"]), "holding_ticker": r.get("ticker") or "",
                          "weight_pct": r["weight"], "as_of_date": doc.get("as_of"),
                          "source": doc.get("source", "db")} for r in rows[:SUMMARY_HOLDINGS]],
        })

    if p["stocks"]:
        items = sorted(((s, stock_value_gbp(s, p["fx"])) for s in p["stocks"]), key=lambda x: -x[1])
        total = sum(v for _, v in items)
        out.append({
            "ticker": "DIRECT", "shares": round(total, 2), "last_price_gbp": 1.0, "last_price_date": None,
            "total_covered_pct": 100.0, "is_direct": True, "position_count": len(items),
            "holdings": [{"holding_name": s["name"], "holding_ticker": s["ticker"],
                          "weight_pct": round(v / total * 100, 4) if total > 0 else 0,
                          "as_of_date": None, "source": "manual"} for s, v in items],
        })
    return out


def stocks_view(store) -> list[dict]:
    p = load(store)
    return [{**s, "market_value_gbp": round(stock_value_gbp(s, p["fx"]), 2)}
            for s in sorted(p["stocks"], key=lambda s: s["ticker"])]


def positions(store) -> list[dict]:
    """Every position with its GBP value and Yahoo symbol, for the risk model."""
    p = load(store)
    out = [{"id": e["ticker"], "name": e["ticker"], "kind": "etf", "symbol": etf_symbol(e),
            "value": (e.get("shares") or 0) * (e.get("last_price_gbp") or 0)} for e in p["etfs"]]
    out += [{"id": s["ticker"], "name": s["name"],
             "kind": "cash" if s["ticker"] in ref.CASH_TICKERS else "stock",
             "symbol": stock_symbol(s), "value": stock_value_gbp(s, p["fx"])} for s in p["stocks"]]
    return out


# ── Writing ──────────────────────────────────────────────────────────────────

def set_etfs(store, items: list[dict]) -> list[dict]:
    """Replace the ETF list with [{ticker, shares}], keeping known prices."""
    prev = {e["ticker"]: e for e in store.get("etfs", [])}
    out = []
    for it in items:
        t = str(it.get("ticker", "")).strip().upper()
        if not t:
            continue
        e = {**prev.get(t, {"ticker": t, "added_at": now()}), "shares": float(it.get("shares") or 0),
             "updated_at": now()}
        if it.get("yahoo"):
            e["yahoo"] = it["yahoo"]
        out.append(e)
    store.set("etfs", out)
    return out


def set_holdings(store, ticker: str, items: list[dict], source: str = "manual") -> int:
    rows = [{"name": h["name"], "ticker": h.get("ticker") or "", "weight": float(h["weight"])}
            for h in items if h.get("name") and float(h.get("weight") or 0) > 0]
    as_of = next((h.get("as_of_date") for h in items if h.get("as_of_date")), now()[:10])
    store.set(f"holdings:{ticker.upper()}", {"as_of": as_of, "source": source, "rows": rows})
    return len(rows)


def set_stocks(store, items: list[dict]) -> int:
    prev = {s["ticker"]: s for s in store.get("stocks", [])}
    out = []
    for s in items:
        old = prev.get(s["ticker"], {})
        out.append({**{k: old[k] for k in ("isin", "yahoo") if k in old},
                    "ticker": s["ticker"], "name": s["name"], "quantity": float(s["quantity"]),
                    "last_price": float(s.get("last_price") or 0), "currency": s["currency"],
                    "cost_basis_local": s.get("cost_basis_local"), "updated_at": now()})
    store.set("stocks", out)
    return len(out)


def set_fx(store, rates: dict) -> None:
    store.set("fx", {**store.get("fx", DEFAULT_FX), **{str(k): float(v) for k, v in rates.items()}})


# ── Seeding ──────────────────────────────────────────────────────────────────

def is_empty(store) -> bool:
    return not store.get_many(["etfs", "stocks"])


def seed(store, path: str | Path = DEMO_FILE) -> None:
    """Load a portfolio file: {etfs, stocks, fx, holdings: {ETF: {as_of, source, rows}},
    ai_maturity?, compute_asset?}."""
    data = json.loads(Path(path).read_text())
    docs = {"etfs": data["etfs"], "stocks": data["stocks"], "fx": {**DEFAULT_FX, **data.get("fx", {})}}
    docs.update({f"holdings:{t.upper()}": h for t, h in data.get("holdings", {}).items()})
    docs.update({k: data[k] for k in ("ai_maturity", "compute_asset") if k in data})
    store.set_many(docs)
