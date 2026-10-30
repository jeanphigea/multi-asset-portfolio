"""
Market data from Yahoo Finance (yfinance): prices and FX, per-company
fundamentals, and a multi-year quality score built from financial statements.

Each refresh fetches in parallel, builds its result in memory and writes it to
the store once. A `deadline` (epoch seconds) stops new fetches when a
serverless time limit is near; whatever finished by then is still saved.
"""
from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import portfolio as pf
import reference as ref
from names import company_key

WORKERS = 8


def yf():
    """yfinance, with its timezone cache in a writable temp folder (the
    default lives in the home directory, which is read-only on Vercel)."""
    import yfinance
    yfinance.set_tz_cache_location(os.path.join(tempfile.gettempdir(), "yfinance"))
    return yfinance


def _price(info: dict):
    return info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")


def _parallel(fn, items, deadline=None) -> dict:
    """{item: fn(item) or the Exception it raised}; items not started before the deadline are left out."""
    out = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(_guarded, fn, it, deadline): it for it in items}
        for f in as_completed(futures):
            res = f.result()
            if res is not _SKIPPED:
                out[futures[f]] = res
    return out


_SKIPPED = object()


def _guarded(fn, item, deadline):
    if deadline and time.time() > deadline:
        return _SKIPPED
    try:
        return fn(item)
    except Exception as e:          # one bad symbol must not sink the whole refresh
        return e


# ── Prices ───────────────────────────────────────────────────────────────────

def refresh_prices(store, deadline=None) -> dict:
    """Mark every position to market: FX first, then direct stocks in their own
    listing currency, then ETFs converted to GBP using the quote currency Yahoo
    reports (LSE lines are a mix of GBP and GBp; assuming either one is wrong)."""
    y = yf()
    p = pf.load(store)
    stamp = pf.now()
    stock_syms = {s["ticker"]: pf.stock_symbol(s) for s in p["stocks"]}
    etf_syms = {e["ticker"]: pf.etf_symbol(e) for e in p["etfs"]}
    symbols = set(ref.FX_PAIRS.values()) | {v for v in [*stock_syms.values(), *etf_syms.values()] if v}
    infos = _parallel(lambda s: y.Ticker(s).info, sorted(symbols), deadline)
    updated, errors = {"fx": 0, "stocks": 0, "etfs": 0}, []

    def quote(sym):
        info = infos.get(sym)
        if isinstance(info, Exception):
            raise info
        px = _price(info or {})
        if not px:
            raise ValueError("no price")
        return float(px), (info or {}).get("currency")

    fx = dict(p["fx"])
    for ccy, pair in ref.FX_PAIRS.items():
        try:
            fx[ccy] = quote(pair)[0]
            updated["fx"] += 1
        except Exception as e:
            errors.append(f"FX {ccy}: {e}")
    fx.update({"GBP": 1.0, "GBp": 0.01})          # GBp is a unit of GBP, not a traded currency

    stocks = []
    for s in p["stocks"]:
        sym = stock_syms[s["ticker"]]
        try:
            if not sym:
                raise ValueError("no Yahoo symbol")
            px, ccy = quote(sym)
            # Reconcile a quote-unit mismatch (Yahoo GBp vs stored GBP)
            if ccy and ccy != s["currency"]:
                if {ccy, s["currency"]} != {"GBP", "GBp"}:
                    raise ValueError(f"currency {ccy} != stored {s['currency']}")
                px = px * 100 if s["currency"] == "GBp" else px / 100
            s = {**s, "last_price": px, "updated_at": stamp}
            updated["stocks"] += 1
        except Exception as e:
            errors.append(f"{s['ticker']}: {e}")
        stocks.append(s)

    etfs = []
    for e in p["etfs"]:
        sym = etf_syms[e["ticker"]]
        try:
            if not sym:
                raise ValueError("no Yahoo symbol")
            px, ccy = quote(sym)
            e = {**e, "last_price_gbp": px * fx.get(ccy, 1.0), "last_price_date": stamp[:10], "updated_at": stamp}
            updated["etfs"] += 1
        except Exception as ex:
            errors.append(f"{e['ticker']}: {ex}")
        etfs.append(e)

    store.set_many({"fx": fx, "stocks": stocks, "etfs": etfs})
    mark(store, "prices", stamp)
    return {"ok": True, "updated": updated, "errors": errors, "as_of": stamp}


def mark(store, part, stamp):
    store.set("meta", {**store.get("meta", {}), f"{part}_at": stamp})


# ── Which companies to score ─────────────────────────────────────────────────

# Exchange suffixes to try when a constituent list gives a bare local code.
# Ordered by how often the portfolio's ETFs hold each market.
YAHOO_SUFFIXES = [".L", ".PA", ".DE", ".AS", ".SW", ".MI", ".NS", ".SA", ".TO", ".HK",
                  ".MC", ".ST", ".SI", ".AX", ".CO", ".OL", ".HE", ".BR", ".VI"]


def name_agrees(expected_key: str, yahoo_name: str | None) -> bool:
    """
    Guard for tickers taken from ETF constituent lists, which often omit the
    exchange suffix: bare "CL" is crude oil in a commodity list but
    Colgate-Palmolive on Yahoo. Requiring the fetched name to agree with the
    company we meant turns a silent wrong-data bug into a skipped row.

    Lenient about spacing and legal forms, strict otherwise: a miss costs one
    blank row, a false match corrupts a company's fundamentals.
    """
    got = company_key(yahoo_name or "")
    if not got:
        return False
    strip_the = lambda x: x[4:] if x.startswith("the ") else x
    a, b = strip_the(expected_key).replace(" ", ""), strip_the(got).replace(" ", "")
    return a == b or a.startswith(b) or b.startswith(a)


def resolve_yahoo_ticker(key: str, base: str, y) -> str | None:
    """Try the bare code, then each exchange suffix, accepting the first whose
    company name agrees with `key`. None when nothing verifies."""
    for suffix in ("", *YAHOO_SUFFIXES):
        try:
            info = y.Ticker(base + suffix).info
        except Exception:
            continue
        if name_agrees(key, info.get("longName") or info.get("shortName")):
            return base + suffix
    return None


def scoring_universe(store) -> dict[str, tuple[str, bool]]:
    """
    company key -> (Yahoo symbol, derived) for everything worth scoring.

    The curated COMPANY_YAHOO map covers the largest holdings and always wins:
    it carries the right exchange suffix. Beyond it, every constituent of a held
    equity ETF that has a ticker is added as "derived", meaning its name must be
    verified before its data is trusted. A symbol resolved on an earlier run
    replaces the guess; a known-unresolvable one is dropped.
    """
    universe = {k: (v, False) for k, v in ref.COMPANY_YAHOO.items()}
    curated = set(ref.COMPANY_YAHOO.values())
    for s in store.get("stocks", []):           # a direct holding added by hand
        sym, key = pf.stock_symbol(s), company_key(s["name"])
        if sym and key and sym not in curated and key not in universe and s["ticker"] not in ref.CASH_TICKERS:
            universe[key] = (sym, False)
    held = [e["ticker"].upper() for e in store.get("etfs", []) if e["ticker"].upper() not in ref.NON_EQUITY_ETFS]
    for doc in pf.holdings(store, held).values():
        for r in doc.get("rows", []):
            key, t = company_key(r["name"]), (r.get("ticker") or "").strip().upper()
            # Numeric-only codes ("005930") need a suffix the list does not give.
            if key and t and key not in universe and not t.isdigit():
                universe[key] = (t, True)
    for key, r in store.get("yahoo_resolution", {}).items():
        if key in universe and universe[key][1]:
            if r.get("ok") and r.get("yahoo_ticker"):
                universe[key] = (r["yahoo_ticker"], False)
            else:
                universe.pop(key)
    return universe


# ── Fundamentals ─────────────────────────────────────────────────────────────

def fundamentals_from_info(info: dict) -> dict:
    """Scoring inputs from a yfinance .info dict, in percent / ratio units."""
    pct = lambda v: v * 100 if v is not None else None
    fcf, rev = info.get("freeCashflow"), info.get("totalRevenue")
    tgt, cur = info.get("targetMeanPrice"), info.get("currentPrice")
    de = info.get("debtToEquity")                    # Yahoo gives % (30.2 -> 0.30x)
    return {
        "roe": pct(info.get("returnOnEquity")),
        "fcf_margin": fcf / rev * 100 if fcf is not None and rev else None,
        "de": de / 100 if de is not None else None,
        "eps_growth": pct(info.get("earningsGrowth")),
        "net_margin": pct(info.get("profitMargins")),
        "div_yield": info.get("dividendYield"),      # already in % in yfinance >= 0.2.5x
        "beta": info.get("beta"),
        "pe": info.get("trailingPE"),
        "gross_margin": pct(info.get("grossMargins")),
        "rev_growth": pct(info.get("revenueGrowth")),
        "peg": info.get("trailingPegRatio"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "payout": pct(info.get("payoutRatio")),
        "m12_change": pct(info.get("52WeekChange")),
        "target_upside": (tgt / cur - 1) * 100 if tgt and cur else None,
        "rec_mean": info.get("recommendationMean"),  # 1 = strong buy ... 5 = sell
        "sector": info.get("sector"), "industry": info.get("industry"), "country": info.get("country"),
    }


def refresh_fundamentals(store, deadline=None) -> dict:
    y = yf()
    stamp = pf.now()
    universe = scoring_universe(store)

    def fetch(key):
        yt, derived = universe[key]
        info = y.Ticker(yt).info
        resolution = None
        if derived and not name_agrees(key, info.get("longName") or info.get("shortName")):
            found = resolve_yahoo_ticker(key, yt.split(".")[0], y)
            resolution = {"yahoo_ticker": found, "ok": bool(found), "resolved_at": stamp}
            if not found:
                return resolution, ValueError(f"no Yahoo symbol verified for {yt}, skipped")
            yt, info = found, y.Ticker(found).info
        if not info or all(info.get(k) is None for k in ("trailingPE", "returnOnEquity", "beta")):
            return resolution, ValueError(f"{yt}: no data returned")
        return resolution, {"key": key, "yahoo_ticker": yt, **fundamentals_from_info(info), "updated_at": stamp}

    results = _parallel(fetch, list(universe), deadline)
    fund, resolved, errors = store.get("fundamentals", {}), store.get("yahoo_resolution", {}), []
    for key, res in results.items():
        if isinstance(res, Exception):
            errors.append(f"{universe[key][0]}: {res}")
            continue
        resolution, row = res
        if resolution:
            resolved[key] = resolution
        if isinstance(row, Exception):
            errors.append(str(row))
        else:
            fund[key] = row
    store.set_many({"fundamentals": fund, "yahoo_resolution": resolved})
    mark(store, "fundamentals", stamp)
    done = sum(1 for r in results.values() if not isinstance(r, Exception) and not isinstance(r[1], Exception))
    return {"ok": True, "refreshed": done, "errors": errors, "skipped": len(universe) - len(results)}


# ── Quality (multi-year, from statements) ────────────────────────────────────
# A Buffett-style score: durable economics over the 4-5 years of annual
# statements yfinance provides. Definitions in spec/05-market-data.md.

ASSUMED_WACC = 9.0        # % - crude but consistent across companies
DEFAULT_TAX = 0.21


def _row(df, *names):
    """A statement row by the first matching label; newest year first."""
    if df is None or df.empty:
        return []
    for n in names:
        if n in df.index:
            return [None if v != v else float(v) for v in df.loc[n].tolist()]
    return []


def band(v, cuts, higher_is_better=True):
    """cuts = [c4, c3, c2, c1]: 4 points at or beyond c4 ... 0 points short of c1."""
    if v is None:
        return None
    for pts, c in zip((4, 3, 2, 1), cuts):
        if (v >= c) if higher_is_better else (v <= c):
            return pts
    return 0


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def quality_metrics(rev, gp, ni, ebit, taxr, intex, invcap, equity, debt, netdebt, shares, fcf) -> dict:
    """The ratios behind the quality score, from statement rows (newest first)."""
    d = {}
    roics = []
    for i in range(min(len(ebit), len(invcap))):
        e, ic = ebit[i], invcap[i]
        if e is None or not ic:
            continue
        tr = taxr[i] if i < len(taxr) and taxr[i] is not None else DEFAULT_TAX
        tr = tr if 0 <= tr < 1 else DEFAULT_TAX
        roics.append(e * (1 - tr) / ic * 100)
    d["roic"] = roics[0] if roics else None
    d["roic_min"] = min(roics) if roics else None
    d["roic_spread"] = d["roic"] - ASSUMED_WACC if d["roic"] is not None else None
    d["roe"] = ni[0] / equity[0] * 100 if ni and equity and ni[0] is not None and equity[0] else None

    gms = [gp[i] / rev[i] * 100 for i in range(min(len(gp), len(rev))) if gp[i] is not None and rev[i]]
    d["gross_margin"] = gms[0] if gms else None
    d["gm_trend"] = gms[0] - gms[-1] if len(gms) >= 2 else None
    if len(gms) >= 3:
        mean = sum(gms) / len(gms)
        d["gm_cv"] = (sum((x - mean) ** 2 for x in gms) / len(gms)) ** 0.5 / abs(mean) if mean else None
    else:
        d["gm_cv"] = None

    # Worst year-over-year revenue change: does the business shrink in bad
    # years? Unlike variance, it tells steady growth from a boom/bust swing.
    chg = [(rev[i] / rev[i + 1] - 1) * 100 for i in range(len(rev) - 1) if rev[i] is not None and rev[i + 1]]
    d["rev_worst"] = min(chg) if chg else None

    fv = [v for v in fcf if v is not None]
    d["fcf_years"], d["fcf_total"] = sum(1 for v in fv if v > 0), len(fv)
    d["fcf_ratio"] = d["fcf_years"] / d["fcf_total"] if d["fcf_total"] else None

    d["de"] = debt[0] / equity[0] if debt and equity and equity[0] and debt[0] is not None else None
    ie = abs(intex[0]) if intex and intex[0] else None
    d["int_cov"] = ebit[0] / ie if ie and ebit and ebit[0] is not None else None
    d["net_cash"] = netdebt[0] < 0 if netdebt and netdebt[0] is not None else None

    sh = [v for v in shares if v]
    d["share_chg"] = ((sh[0] / sh[-1]) ** (1 / (len(sh) - 1)) - 1) * 100 if len(sh) >= 2 else None  # +ve = dilution
    d["years"] = len(rev)
    return d


def quality_pillars(d: dict) -> dict:
    return {
        "Returns on capital": _avg([band(d["roic"], [20, 15, 10, 7]), band(d["roe"], [20, 15, 10, 7]),
                                    band(d["roic_spread"], [10, 6, 3, 0])]),
        "Consistency": _avg([band(d["gm_cv"], [0.05, 0.10, 0.20, 0.35], higher_is_better=False),
                             band(d["fcf_ratio"], [1.0, 0.75, 0.5, 0.25]),
                             band(d["roic_min"], [15, 10, 5, 0]), band(d["rev_worst"], [5, 0, -10, -25])]),
        "Moat": _avg([band(d["gross_margin"], [50, 35, 25, 15]), band(d["gm_trend"], [2, 0, -2, -5])]),
        "Balance sheet": _avg([band(d["de"], [0.3, 0.6, 1.0, 2.0], higher_is_better=False),
                               band(d["int_cov"], [15, 8, 4, 2]),
                               (4 if d["net_cash"] else 2) if d["net_cash"] is not None else None]),
        # Reinvestment only creates value above the cost of capital, hence ROIC again.
        "Capital allocation": _avg([band(d["share_chg"], [-2, 0, 1, 3], higher_is_better=False),
                                    band(d["roic"], [20, 15, 10, 7])]),
    }


def quality_score(d: dict) -> dict | None:
    pillars = quality_pillars(d)
    vals = [v for v in pillars.values() if v is not None]
    if not vals:
        return None
    # A score built on missing pillars or a short history is not comparable
    # to a complete one: flag it rather than silently rank it.
    d = {**d, "pillars_available": len(vals), "low_confidence": len(vals) < 5 or (d.get("years") or 0) < 4}
    return {"q_score": sum(vals) / len(vals) * 5,
            "p_returns": pillars["Returns on capital"], "p_consistency": pillars["Consistency"],
            "p_moat": pillars["Moat"], "p_balance": pillars["Balance sheet"],
            "p_capital": pillars["Capital allocation"], "detail": d, "years": d.get("years")}


def quality_from_statements(fin, bs, cf) -> dict | None:
    return quality_score(quality_metrics(
        rev=_row(fin, "Total Revenue", "Operating Revenue"), gp=_row(fin, "Gross Profit"),
        ni=_row(fin, "Net Income", "Net Income Common Stockholders"), ebit=_row(fin, "EBIT", "Operating Income"),
        taxr=_row(fin, "Tax Rate For Calcs"), intex=_row(fin, "Interest Expense", "Interest Expense Non Operating"),
        invcap=_row(bs, "Invested Capital"), equity=_row(bs, "Stockholders Equity", "Common Stock Equity"),
        debt=_row(bs, "Total Debt"), netdebt=_row(bs, "Net Debt"),
        shares=_row(bs, "Ordinary Shares Number", "Share Issued"), fcf=_row(cf, "Free Cash Flow")))


def refresh_quality(store, deadline=None) -> dict:
    y = yf()
    stamp = pf.now()
    verified = store.get("fundamentals", {})
    # A derived symbol is used only once the fundamentals refresh has verified it.
    targets = {k: yt for k, (yt, derived) in scoring_universe(store).items() if not derived or k in verified}

    def fetch(key):
        t = y.Ticker(targets[key])
        q = quality_from_statements(t.financials, t.balance_sheet, t.cashflow)
        if not q:
            raise ValueError("no statement data")
        return {"key": key, "yahoo_ticker": targets[key], **q, "updated_at": stamp}

    results = _parallel(fetch, list(targets), deadline)
    qual, errors = store.get("quality", {}), []
    for key, res in results.items():
        if isinstance(res, Exception):
            errors.append(f"{targets[key]}: {res}")
        else:
            qual[key] = res
    store.set("quality", qual)
    mark(store, "quality", stamp)
    return {"ok": True, "refreshed": sum(not isinstance(r, Exception) for r in results.values()),
            "errors": errors, "skipped": len(targets) - len(results)}
