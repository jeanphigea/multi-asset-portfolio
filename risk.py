"""
Historical risk for the Risk tab.

Takes today's positions and replays them through up to ten years of real prices:
what would *this* portfolio have done? That is the standard "current holdings"
backtest. It says nothing about the trades you actually made, and it keeps the
weights constant (daily rebalanced), so it measures the risk of the mix, not of
your timing.

Prices come from Yahoo and are kept in the store for up to 18 hours, one
document per symbol. Everything is converted to GBP before returns are taken,
so currency risk is part of the result, as it is for a sterling investor.

Conventions
  * Volatility, beta, VaR and correlation use WEEKLY (Friday) returns. Holdings
    trade in Hong Kong, Europe and New York on different clocks; daily returns
    across time zones understate correlation and so understate risk.
  * A holding with no history yet (a recent IPO, a new ETF) is left out on those
    days and the others are re-weighted; `coverage` reports how much of the
    portfolio had a price at the start of each window.
  * Cash-like holdings earn the risk-free rate instead of their own short history.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

MAX_AGE = timedelta(hours=18)
YEARS = (1, 3, 5, 10)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Price history ────────────────────────────────────────────────────────────
# Stored as history:<symbol> = {currency, fetched, dates: [...], close: [...]}.

def _fetch(symbol: str) -> dict:
    from market import yf
    t = yf().Ticker(symbol)
    h = t.history(period="10y", auto_adjust=True)
    if h is None or h.empty:
        raise ValueError("no price history")
    close = h["Close"]
    # Exchange-local trading days, without time zones, so markets line up by date.
    dates = [d.isoformat() for d in close.index.date]
    keep = {d: round(float(v), 6) for d, v in zip(dates, close.tolist())}   # last of any duplicate day
    return {"currency": (t.history_metadata or {}).get("currency"),
            "fetched": _utcnow().isoformat(timespec="seconds"),
            "dates": list(keep), "close": list(keep.values())}


def _safe_fetch(s):
    try:
        return _fetch(s)
    except Exception as e:        # one bad symbol must not sink the whole refresh
        return e


def _series(doc: dict) -> dict:
    return {"currency": doc["currency"], "fetched": doc["fetched"],
            "close": pd.Series(doc["close"], index=pd.to_datetime(doc["dates"]), dtype=float)}


def history(store, symbols: list[str], force: bool = False, fetch: bool = True) -> tuple[dict, list[str]]:
    """Daily closes for every symbol, re-downloading those older than MAX_AGE
    (all of them with force). fetch=False only reads what is stored."""
    docs = store.get_many([f"history:{s}" for s in symbols])
    cache = {s: docs[f"history:{s}"] for s in symbols if f"history:{s}" in docs}
    now = _utcnow()
    stale = [s for s in symbols if force or s not in cache
             or now - datetime.fromisoformat(cache[s]["fetched"]) > MAX_AGE] if fetch else []
    errors = []
    if stale:
        fresh = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            for s, res in zip(stale, ex.map(_safe_fetch, stale)):
                if isinstance(res, Exception):
                    errors.append(f"{s}: {res}")
                else:
                    fresh[s] = res
        store.set_many({f"history:{s}": d for s, d in fresh.items()})
        cache.update(fresh)
    return {s: _series(d) for s, d in cache.items()}, errors


def history_as_of(hist: dict) -> str | None:
    return max(v["fetched"] for v in hist.values()) if hist else None


# ── GBP price series ─────────────────────────────────────────────────────────

def gbp_prices(sym: str, hist: dict, fx_pairs: dict) -> pd.Series | None:
    """Close in GBP. Pence vs pounds only rescales, so it cannot change a return,
    but it is converted anyway so the levels are honest."""
    h = hist.get(sym)
    if not h:
        return None
    ccy, s = h["currency"], h["close"]
    if ccy in ("GBp", "GBX"):
        return s / 100
    if ccy == "GBP":
        return s
    pair = fx_pairs.get(ccy)
    if not pair or pair not in hist:
        return None
    fx = hist[pair]["close"].reindex(s.index.union(hist[pair]["close"].index)).ffill()
    return (s * fx.reindex(s.index)).dropna()


def _daily_index(series: list[pd.Series]) -> pd.DatetimeIndex:
    idx = series[0].index
    for s in series[1:]:
        idx = idx.union(s.index)
    return idx[idx.dayofweek < 5]


def portfolio_returns(positions: list[dict], hist: dict, fx_pairs: dict, rf: float):
    """
    Daily GBP returns of today's mix, plus a per-day coverage share.
    positions: [{id, symbol, value, kind}] with kind 'cash' for cash-likes.
    """
    prices, weights, cash, missing = {}, {}, [], []
    for p in positions:
        if p["value"] <= 0:
            continue
        if p["kind"] == "cash":
            cash.append(p["id"]); weights[p["id"]] = p["value"]; continue
        s = gbp_prices(p["symbol"], hist, fx_pairs) if p["symbol"] else None
        if s is None or s.empty:
            missing.append(p["id"]); continue
        prices[p["id"]] = s
        weights[p["id"]] = p["value"]
    idx = _daily_index(list(prices.values()))
    px = pd.DataFrame({k: v.reindex(idx).ffill(limit=5) for k, v in prices.items()}, index=idx)
    # A holding's first price must not be ffilled backwards; pct_change keeps NaN there.
    rets = px.pct_change(fill_method=None)
    daily_rf = (1 + rf / 100) ** (1 / 252) - 1
    for c in cash:
        rets[c] = daily_rf
    w = pd.Series(weights)
    rets = rets[w.index]
    avail = rets.notna()
    wsum = (avail * w).sum(axis=1)
    port = (rets.fillna(0) * w).sum(axis=1) / wsum.replace(0, np.nan)
    coverage = wsum / w.sum()
    ok = port.notna()
    return port[ok], coverage[ok], rets[ok], w / w.sum(), missing


def single_returns(sym: str, hist: dict, fx_pairs: dict) -> pd.Series:
    s = gbp_prices(sym, hist, fx_pairs)
    idx = s.index[s.index.dayofweek < 5]
    return s.reindex(idx).pct_change(fill_method=None).dropna()


# ── Metrics ──────────────────────────────────────────────────────────────────

def _nav(r: pd.Series) -> pd.Series:
    return (1 + r).cumprod()


def _weekly(nav: pd.Series) -> pd.Series:
    return nav.resample("W-FRI").last().pct_change().dropna()


def _monthly(nav: pd.Series) -> pd.Series:
    return nav.resample("ME").last().pct_change().dropna()


def drawdown_stats(nav: pd.Series) -> dict:
    dd = nav / nav.cummax() - 1
    trough = dd.idxmin()
    peak = nav[:trough].idxmax()
    after = nav[trough:]
    rec = after[after >= nav[peak]]
    recovery = rec.index[0] if len(rec) else None
    return {"max_drawdown": float(dd.min() * 100),
            "peak": peak.date().isoformat(), "trough": trough.date().isoformat(),
            "recovery": recovery.date().isoformat() if recovery is not None else None,
            "days_to_trough": int((trough - peak).days),
            "days_to_recover": int((recovery - trough).days) if recovery is not None else None,
            "current_drawdown": float(dd.iloc[-1] * 100)}


def metrics(r: pd.Series, rf: float) -> dict:
    nav = _nav(r)
    years = max((nav.index[-1] - nav.index[0]).days / 365.25, 1e-9)
    wk, mo = _weekly(nav), _monthly(nav)
    cagr = nav.iloc[-1] ** (1 / years) - 1
    vol = wk.std() * math.sqrt(52)
    rf_w = (1 + rf / 100) ** (1 / 52) - 1
    downside = math.sqrt((np.minimum(wk - rf_w, 0) ** 2).mean()) * math.sqrt(52)
    q = wk.quantile(0.05)
    return {
        "total_return": float((nav.iloc[-1] - 1) * 100),
        "cagr": float(cagr * 100),
        "volatility": float(vol * 100),
        "sharpe": float((cagr - rf / 100) / vol) if vol else None,
        "sortino": float((cagr - rf / 100) / downside) if downside else None,
        "var95_week": float(-q * 100),
        "cvar95_week": float(-wk[wk <= q].mean() * 100),
        "worst_week": float(wk.min() * 100),
        "worst_month": float(mo.min() * 100) if len(mo) else None,
        "best_month": float(mo.max() * 100) if len(mo) else None,
        "positive_months": float((mo > 0).mean() * 100) if len(mo) else None,
        **drawdown_stats(nav),
    }


def relative(rp: pd.Series, rb: pd.Series) -> dict:
    wp, wb = _weekly(_nav(rp)), _weekly(_nav(rb))
    wp, wb = wp.align(wb, join="inner")
    mp, mb = _monthly(_nav(rp)).align(_monthly(_nav(rb)), join="inner")
    up, down = mb > 0, mb < 0
    return {
        "beta": float(wp.cov(wb) / wb.var()) if wb.var() else None,
        "correlation": float(wp.corr(wb)),
        "tracking_error": float((wp - wb).std() * math.sqrt(52) * 100),
        "up_capture": float(mp[up].mean() / mb[up].mean() * 100) if up.any() else None,
        "down_capture": float(mp[down].mean() / mb[down].mean() * 100) if down.any() else None,
    }


def risk_contributions(rets: pd.DataFrame, w: pd.Series, rb: pd.Series) -> list[dict]:
    """Each position's share of portfolio variance, from weekly returns:
    RC_i = w_i (Σw)_i / wᵀΣw. Sums to 100%; a holding can take more risk than its weight."""
    navs = (1 + rets.fillna(0)).cumprod().where(rets.notna().cummax())
    wk = navs.resample("W-FRI").last().pct_change(fill_method=None)
    cov = wk.cov(min_periods=26) * 52
    keep = [c for c in cov.columns if cov[c].notna().sum() == len(cov)]
    cov = cov.loc[keep, keep]
    wv = w[keep] / w[keep].sum()
    marg = cov.values @ wv.values
    var = float(wv.values @ marg)
    wb = _weekly(_nav(rb))
    out = []
    for i, k in enumerate(keep):
        a, b = wk[k].align(wb, join="inner")
        ok = a.notna() & b.notna()
        out.append({"id": k, "weight": float(wv[k] * 100),
                    "risk_share": float(wv[k] * marg[i] / var * 100) if var else None,
                    "volatility": float(math.sqrt(cov.loc[k, k]) * 100),
                    "beta": float(a[ok].cov(b[ok]) / b[ok].var()) if ok.sum() > 26 else None})
    return sorted(out, key=lambda x: -(x["risk_share"] or 0))


def episode(r: pd.Series, coverage: pd.Series, start: str, end: str) -> dict | None:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    win = r[(r.index > s) & (r.index <= e)]
    if win.empty:
        return None
    nav = pd.concat([pd.Series([1.0], index=[r.index[r.index <= s][-1]]), _nav(win)]) \
        if (r.index <= s).any() else _nav(win)
    return {"return": float((nav.iloc[-1] - 1) * 100),
            "max_drawdown": float((nav / nav.cummax() - 1).min() * 100),
            "coverage": float(coverage[win.index[0]] * 100),   # share priced at the start
            "path": [[d.date().isoformat(), round(float(v) * 100, 2)] for d, v in nav.items()]}


# ── Report for the Risk tab ──────────────────────────────────────────────────

def report(store, positions: list[dict], bench: dict, years: int, rf: float, fx_pairs: dict,
           episodes: list[dict], refresh: bool = False, fetch: bool = True) -> dict:
    """Everything the Risk tab shows for one benchmark and look-back window."""
    symbols = sorted({p["symbol"] for p in positions if p["symbol"] and p["kind"] != "cash"}
                     | set(fx_pairs.values()) | {bench["ticker"]})
    hist, errors = history(store, symbols, force=refresh, fetch=fetch)
    if bench["ticker"] not in hist or not any(p["symbol"] in hist for p in positions):
        return {"ok": False, "error": "No price history stored yet — refresh market data first.",
                "errors": errors}

    rp_all, cov_all, rets_all, w, missing = portfolio_returns(positions, hist, fx_pairs, rf)
    rb_all = single_returns(bench["ticker"], hist, fx_pairs)
    rp_all, rb_all = rp_all.align(rb_all, join="inner")
    cov_all = cov_all.reindex(rp_all.index)

    end = rp_all.index[-1]
    start = max(end - pd.DateOffset(years=years), rp_all.index[0])
    sel = rp_all.index > start
    rp, rb = rp_all[sel], rb_all[sel]
    navp, navb = _nav(rp), _nav(rb)

    names = {p["id"]: p["name"] for p in positions}
    contrib = risk_contributions(rets_all[rets_all.index.isin(rp.index)], w, rb)
    for c in contrib:
        c["name"] = names.get(c["id"], c["id"])

    eps = []
    for e in episodes:
        p = episode(rp_all, cov_all, e["start"], e["end"])
        b = episode(rb_all, pd.Series(1.0, index=rb_all.index), e["start"], e["end"])
        if p and b:
            eps.append({**e, "portfolio": p, "benchmark": {k: v for k, v in b.items() if k != "coverage"}})

    return {
        "ok": True, "rf": rf, "history_as_of": history_as_of(hist),
        "window": {"start": rp.index[0].date().isoformat(), "end": end.date().isoformat(), "years": years},
        "coverage_start": float(cov_all[rp.index[0]] * 100),
        "portfolio": metrics(rp, rf), "benchmark_metrics": metrics(rb, rf), "relative": relative(rp, rb),
        "series": {"dates": [d.date().isoformat() for d in navp.index],
                   "portfolio": [round(float(x), 5) for x in navp], "benchmark": [round(float(x), 5) for x in navb]},
        "contributions": contrib, "episodes": eps, "missing": missing, "errors": errors,
    }
