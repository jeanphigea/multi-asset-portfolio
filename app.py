"""
Multi-Asset Portfolio: Flask app.

Routes only: each one reads the store, calls a module and returns JSON.
  portfolio.py  positions, look-through summary, seeding
  market.py     prices, FX, fundamentals, quality (Yahoo Finance)
  risk.py       historical risk metrics and price history
  scores.py     hand-researched AI maturity and compute scores
  ibkr.py       optional Interactive Brokers sync
  reference.py  static taxonomy, benchmarks, scenarios, symbols

Run locally:  python app.py   ->  http://localhost:5050
Environment:  see .env.example
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request

import ibkr
import market
import portfolio as pf
import reference as ref
import risk
import scores
from names import COMMODITY_SECTORS, NAME_ALIASES
from store import get_store

ROOT = Path(__file__).parent
DEMO = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
# Leave headroom under the serverless limit (Vercel maxDuration = 300 s).
CRON_BUDGET = float(os.environ.get("CRON_BUDGET_SECONDS", "270"))

app = Flask(__name__)


def store():
    s = get_store()
    if pf.is_empty(s):            # first run: start from the demo portfolio
        pf.seed(s)
    return s


@app.before_request
def read_only_demo():
    if DEMO and request.method not in ("GET", "HEAD", "OPTIONS") and request.endpoint != "cron_refresh":
        return jsonify({"ok": False, "error": "This is a read-only demo."}), 403


@app.errorhandler(404)
def not_found(_):
    """JSON 404 naming the path the app saw and the commit serving it, so a
    routing problem on the host can be diagnosed from outside."""
    env = request.environ
    return jsonify({"ok": False, "error": "Not found", "path": request.path,
                    "build": os.environ.get("VERCEL_GIT_COMMIT_SHA", "local")[:7],
                    # TEMPORARY routing diagnostics
                    "script_name": env.get("SCRIPT_NAME"), "raw_uri": env.get("RAW_URI") or env.get("REQUEST_URI"),
                    "query": env.get("QUERY_STRING")}), 404


# ─── Page and reference data ─────────────────────────────────────────────────

def ibkr_enabled() -> bool:
    try:
        return not DEMO and ibkr.load_config() is not None
    except ibkr.IbkrError:
        return False


def _reference_js() -> str:
    """Static reference data as a script. NAME_ALIASES is sent rather than
    duplicated in the JS: the server keys fundamentals with it, so the two
    must not drift."""
    data = {
        "DEMO": DEMO, "IBKR": ibkr_enabled(),
        "NAME_ALIASES": NAME_ALIASES, "COMMODITY_SECTORS": COMMODITY_SECTORS,
        "GICS_FROM_YAHOO": ref.GICS_FROM_YAHOO, "GICS_FROM_LABEL": ref.GICS_FROM_LABEL,
        "GICS_ORDER": ref.GICS_ORDER, "COMPANY_ESTIMATES": ref.COMPANY_ESTIMATES,
        "MSCI_WORLD_AS_OF": ref.MSCI_WORLD_AS_OF, "MSCI_ACWI_AS_OF": ref.MSCI_ACWI_AS_OF,
        "MSCI_ACWI_SOURCE": ref.MSCI_ACWI_SOURCE,
        "COMPANY_PROFILES": ref.COMPANY_PROFILES, "CASH_SECTOR": ref.CASH_SECTOR,
        "COUNTRY_META": ref.COUNTRY_META,
        "BENCHMARKS": {k: {f: v[f] for f in ("name", "note", "sectors", "countries", "tags")}
                       for k, v in ref.BENCHMARKS.items()},
        "SCENARIOS": ref.SCENARIOS, "SCENARIOS_AS_OF": ref.SCENARIOS_AS_OF,
        "COUNTRY_CCY": ref.COUNTRY_CCY, "CCY_GROUP": ref.CCY_GROUP, "AI_MEGACAPS": ref.AI_MEGACAPS,
        "RISK_FREE_RATE": ref.RISK_FREE_RATE, "AI_DIMENSIONS": scores.AI_DIMENSIONS,
    }
    return f"window.REF = {json.dumps(data, ensure_ascii=False)};"


REFERENCE_JS = _reference_js()


def _asset_version() -> str:
    """Content hash of everything the page loads, so a deploy that changes any
    of it gets fresh URLs and long browser caching is safe."""
    h = hashlib.sha1(REFERENCE_JS.encode())
    for f in ("static/app.js", "static/app.css"):
        h.update((ROOT / f).read_bytes())
    return h.hexdigest()[:10]


ASSET_VERSION = _asset_version()


@app.route("/")
def index():
    return render_template("index.html", demo=DEMO, repo_url=os.environ.get("REPO_URL", ""), v=ASSET_VERSION)


@app.route("/reference.js")
def reference_js():
    return Response(REFERENCE_JS, mimetype="application/javascript",
                    headers={"Cache-Control": "public, max-age=86400"})


# ─── Positions ───────────────────────────────────────────────────────────────

@app.route("/api/summary")
def api_summary():
    return jsonify(pf.summary(store()))


@app.route("/api/portfolio", methods=["POST"])
def api_portfolio_set():
    """Replace the ETF list: [{ticker, shares}]."""
    return jsonify({"ok": True, "etfs": pf.set_etfs(store(), request.get_json(force=True))})


@app.route("/api/holdings/<ticker>", methods=["POST"])
def api_holdings_set(ticker):
    """Replace an ETF's holdings: [{name, ticker, weight, as_of_date}]."""
    return jsonify({"ok": True, "count": pf.set_holdings(store(), ticker, request.get_json(force=True))})


@app.route("/api/stocks", methods=["GET", "POST"])
def api_stocks():
    if request.method == "POST":
        return jsonify({"ok": True, "count": pf.set_stocks(store(), request.get_json(force=True))})
    return jsonify(pf.stocks_view(store()))


@app.route("/api/fx", methods=["GET", "POST"])
def api_fx():
    if request.method == "POST":
        pf.set_fx(store(), request.get_json(force=True))
        return jsonify({"ok": True})
    return jsonify(pf.load(store())["fx"])


@app.route("/api/fundamentals")
def api_fundamentals():
    return jsonify(store().get("fundamentals", {}))


@app.route("/api/quality")
def api_quality():
    return jsonify(store().get("quality", {}))


# ─── Research scores (AI maturity, compute as asset) ─────────────────────────

def _research(key: str, setter):
    if request.method == "POST":
        try:
            return jsonify({"ok": True, **setter(store(), request.get_json(force=True) or {})})
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify(store().get(key, {}))


@app.route("/api/ai-maturity", methods=["GET", "POST"])
def api_ai_maturity():
    return _research("ai_maturity", scores.set_ai_maturity)


@app.route("/api/compute-asset", methods=["GET", "POST"])
def api_compute_asset():
    return _research("compute_asset", scores.set_compute)


# ─── Market data refresh ─────────────────────────────────────────────────────

def _refresh_history(s, deadline=None):
    symbols = {p["symbol"] for p in pf.positions(s) if p["symbol"] and p["kind"] != "cash"}
    symbols |= set(ref.FX_PAIRS.values()) | {b["ticker"] for b in ref.BENCHMARKS.values()}
    _, errors = risk.history(s, sorted(symbols), force=True)
    market.mark(s, "history", pf.now())
    return {"ok": True, "refreshed": len(symbols) - len(errors), "errors": errors}


REFRESH = {"prices": market.refresh_prices, "history": _refresh_history,
           "fundamentals": market.refresh_fundamentals, "quality": market.refresh_quality}


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    part = request.args.get("part", "prices")
    if part not in REFRESH:
        abort(400, f"part must be one of {', '.join(REFRESH)}")
    return jsonify(REFRESH[part](store()))


@app.route("/api/cron/refresh", methods=["GET", "POST"])
def cron_refresh():
    """Every refresh in turn, for a scheduler. Vercel Cron sends
    `Authorization: Bearer $CRON_SECRET`. Stops starting new fetches when the
    time budget runs out; each finished part is already saved."""
    sent = request.headers.get("Authorization", "")
    if not CRON_SECRET or not hmac.compare_digest(sent, f"Bearer {CRON_SECRET}"):
        return jsonify({"ok": False, "error": "unauthorised"}), 401
    deadline = time.time() + CRON_BUDGET
    s, out = store(), {}
    for part, fn in REFRESH.items():
        if time.time() > deadline:
            out[part] = {"ok": False, "error": "skipped: out of time"}
            continue
        try:
            res = fn(s, deadline)
            out[part] = {k: v for k, v in res.items() if k != "errors"} | {"errors": len(res.get("errors", []))}
        except Exception as e:
            out[part] = {"ok": False, "error": str(e)}
    return jsonify(out)


# ─── Risk ────────────────────────────────────────────────────────────────────

@app.route("/api/risk")
def api_risk():
    bkey = request.args.get("benchmark", "acwi")
    bench = ref.BENCHMARKS.get(bkey)
    years = int(request.args.get("years", 3))
    if not bench or years not in risk.YEARS:
        return jsonify({"ok": False, "error": "unknown benchmark or lookback"}), 400
    s = store()
    out = risk.report(s, pf.positions(s), bench, years, ref.RISK_FREE_RATE, ref.FX_PAIRS,
                      ref.HISTORICAL_EPISODES, refresh=request.args.get("refresh") == "1" and not DEMO,
                      fetch=not DEMO)          # the demo reads only what its cron stored
    out["benchmark"] = {"key": bkey, **{k: bench[k] for k in ("name", "ticker", "note")}}
    return jsonify(out)


# ─── Interactive Brokers ─────────────────────────────────────────────────────

@app.route("/api/ibkr/status")
def api_ibkr_status():
    """Config state plus a summary of the last cached statement. Never calls IBKR."""
    try:
        configured, error = not DEMO and ibkr.load_config() is not None, None
    except ibkr.IbkrError as exc:
        configured, error = False, str(exc)
    cached = (ibkr.read_cache() or {}) if configured else {}
    return jsonify({"configured": configured, "error": error, "fetchedAt": cached.get("fetchedAt"),
                    "accounts": [{"accountId": a.get("accountId"), "reportDate": a.get("reportDate"),
                                  "positionCount": len(a.get("positions") or [])}
                                 for a in cached.get("accounts", [])]})


@app.route("/api/ibkr/sync", methods=["POST"])
def api_ibkr_sync():
    """Mirror direct stocks from IBKR. dry_run=1 previews without writing;
    otherwise the store is backed up to backups/ and the plan applied."""
    args = request.get_json(silent=True) or {}
    dry_run = str(args.get("dry_run", request.args.get("dry_run", ""))).lower() in ("1", "true", "yes")
    try:
        snapshot = ibkr.fetch_positions(force=True)
    except ibkr.IbkrNotConfigured as exc:
        return jsonify({"error": str(exc), "code": None}), 400
    except ibkr.IbkrError as exc:
        return jsonify({"error": str(exc), "code": exc.code}), 502

    s = store()
    etf_tickers = {t.upper() for t in ref.ISIN_MAP} | {e["ticker"].upper() for e in s.get("etfs", [])}
    plan = ibkr.plan(snapshot, s.get("stocks", []), etf_tickers, {i.upper() for i in ref.ISIN_MAP.values()})
    if not plan["safe"]:
        return jsonify({**plan, "applied": False}), 409
    if dry_run:
        return jsonify({**plan, "applied": False, "dryRun": True})
    backup = ibkr.apply(s, plan, ROOT / "backups")
    return jsonify({**plan, "applied": True, "backup": backup.name})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"\n✅  Multi-Asset Portfolio running at http://localhost:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False)
