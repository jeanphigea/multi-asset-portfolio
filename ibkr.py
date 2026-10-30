"""
Interactive Brokers Flex Web Service client.

Pulls the *current open positions* of one or more IBKR accounts without any
gateway, desktop app or daily 2FA login: you generate a read-only Flex token
in Account Management, point this module at a saved "Positions" Flex Query,
and it fetches an XML statement over HTTPS.

Configuration (first match wins):

    1. Environment:  IBKR_FLEX_TOKEN, IBKR_FLEX_QUERY_ID
    2. JSON file:    .ibkr.json next to this module (git-ignored)
                     { "token": "...", "queryId": "...", "baseCurrency": "GBP" }

See docs/ibkr-setup.md for how to create the token and query.

The two-step Flex protocol:

    SendRequest(token, queryId)  -> ReferenceCode + statement URL
    GetStatement(token, refCode) -> the statement XML (may need a short wait
                                    while IBKR generates it)

Stdlib only — no `requests` dependency.

The bottom of this module turns a snapshot into a change to the stored direct
holdings (`plan`, `apply`). IBKR is the source of truth for direct stocks, so a
sync adds, updates and REMOVES them; ETF positions are reported but never
written, because the ETF list carries the look-through data.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# Overridable so the integration can be exercised against a local fake.
FLEX_BASE = os.environ.get(
    "IBKR_FLEX_BASE_URL",
    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService",
).rstrip("/")
SEND_REQUEST_URL = f"{FLEX_BASE}/SendRequest"
GET_STATEMENT_URL = f"{FLEX_BASE}/GetStatement"
FLEX_VERSION = "3"

CONFIG_FILE = Path(__file__).parent / ".ibkr.json"
CACHE_FILE = Path(__file__).parent / ".ibkr_cache.json"

# IBKR rejects requests that come in too fast (error 1018). Serving the cache
# inside this window keeps a trigger-happy dashboard from locking us out.
MIN_REFETCH_SECONDS = 300

# GetStatement returns "1019 statement generation in progress" until ready.
POLL_ATTEMPTS = 6
POLL_DELAY_SECONDS = 5

DEFAULT_TARGET_CURRENCY = "GBP"


class IbkrError(RuntimeError):
    """Any failure talking to, or parsing a response from, the Flex service."""

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.code = code


class IbkrNotConfigured(IbkrError):
    """No usable token/query — the user has to fix something locally."""


@dataclass
class IbkrConfig:
    token: str
    query_id: str
    base_currency: str = DEFAULT_TARGET_CURRENCY


def load_config() -> IbkrConfig | None:
    """Read Flex credentials from the environment, then from .ibkr.json."""
    token = os.environ.get("IBKR_FLEX_TOKEN", "").strip()
    query_id = os.environ.get("IBKR_FLEX_QUERY_ID", "").strip()
    currency = os.environ.get("IBKR_BASE_CURRENCY", "").strip()

    if not (token and query_id) and CONFIG_FILE.exists():
        try:
            raw = json.loads(CONFIG_FILE.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise IbkrError(f"Could not read {CONFIG_FILE.name}: {exc}") from exc
        token = token or str(raw.get("token", "")).strip()
        query_id = query_id or str(raw.get("queryId", "")).strip()
        currency = currency or str(raw.get("baseCurrency", "")).strip()

    if not (token and query_id):
        return None
    return IbkrConfig(token, query_id, currency or DEFAULT_TARGET_CURRENCY)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Position:
    accountId: str
    symbol: str
    description: str
    assetCategory: str
    currency: str
    conid: str
    isin: str
    quantity: float
    markPrice: float
    value: float            # in the position's own currency
    valueGBP: float | None  # None when no FX rate was available
    costBasis: float | None
    unrealizedPnl: float | None
    reportDate: str | None


@dataclass
class Account:
    accountId: str
    alias: str
    reportDate: str | None
    totalGBP: float | None
    positions: list[Position] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _get(url: str, params: dict[str, str], timeout: int = 30) -> bytes:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": "wealthtrack/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise IbkrError(f"IBKR returned HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise IbkrError(f"Could not reach IBKR: {exc.reason}") from exc


def _parse_xml(payload: bytes) -> ET.Element:
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        snippet = payload[:200].decode("utf-8", "replace")
        raise IbkrError(f"Unparseable response from IBKR: {snippet}") from exc


def _check_status(root: ET.Element) -> None:
    """Raise if the Flex service reported a Fail/Warn status."""
    status = (root.findtext("Status") or "").strip()
    if status and status.lower() != "success":
        code = (root.findtext("ErrorCode") or "").strip() or None
        message = (root.findtext("ErrorMessage") or "").strip() or "unknown error"
        raise IbkrError(f"IBKR Flex error {code or '?'}: {message}", code=code)


def request_statement(cfg: IbkrConfig) -> bytes:
    """Run the two-step Flex protocol and return the statement XML."""
    root = _parse_xml(_get(SEND_REQUEST_URL, {
        "t": cfg.token, "q": cfg.query_id, "v": FLEX_VERSION,
    }))
    _check_status(root)

    reference = (root.findtext("ReferenceCode") or "").strip()
    if not reference:
        raise IbkrError("IBKR accepted the request but returned no reference code")
    url = (root.findtext("Url") or "").strip() or GET_STATEMENT_URL

    for attempt in range(POLL_ATTEMPTS):
        payload = _get(url, {"t": cfg.token, "q": reference, "v": FLEX_VERSION})
        statement = _parse_xml(payload)
        # A ready statement is <FlexQueryResponse>; a not-yet-ready one comes
        # back as <FlexStatementResponse> with warning code 1019.
        if statement.tag == "FlexQueryResponse":
            return payload
        code = (statement.findtext("ErrorCode") or "").strip()
        if code != "1019":
            _check_status(statement)
            raise IbkrError("IBKR returned an unexpected statement response")
        if attempt < POLL_ATTEMPTS - 1:
            time.sleep(POLL_DELAY_SECONDS)

    raise IbkrError(
        "IBKR is still generating the statement after "
        f"{POLL_ATTEMPTS * POLL_DELAY_SECONDS}s — try again in a minute"
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _num(el: ET.Element, *names: str) -> float | None:
    """First attribute in `names` that parses as a number."""
    for name in names:
        raw = el.get(name)
        if raw not in (None, "", "--"):
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _cost_basis(el: ET.Element, quantity: float) -> float | None:
    """
    Total cost of the position. Flex reports either a money total or a per-share
    price depending on which columns the query selects, so derive the total from
    the price when the money column is absent.
    """
    money = _num(el, "costBasisMoney")
    if money is not None:
        return money
    price = _num(el, "costBasisPrice")
    return round(price * quantity, 2) if price is not None else None


def _build_fx(root: ET.Element, target: str) -> dict[str, float]:
    """
    Map currency -> rate into `target`, from the statement's ConversionRates
    section (present when the Flex query includes "Conversion Rates").

    Rates are quoted into the account's base currency. When base == target the
    rates are used directly; otherwise each is rebased through the target's own
    rate, so a USD position still converts correctly on a EUR-base account.
    """
    rows: list[tuple[str, str, float]] = []
    for el in root.iter("ConversionRate"):
        src = (el.get("fromCurrency") or "").upper()
        dst = (el.get("toCurrency") or "").upper()
        rate = _num(el, "rate")
        if src and dst and rate:
            rows.append((src, dst, rate))

    fx: dict[str, float] = {target.upper(): 1.0}
    if not rows:
        return fx

    direct = {src: rate for src, dst, rate in rows if dst == target.upper()}
    if direct:
        fx.update(direct)
        return fx

    # No rates quoted into the target: rebase via the statement's base currency.
    base = rows[0][1]
    into_base = {src: rate for src, dst, rate in rows if dst == base}
    into_base.setdefault(base, 1.0)  # IBKR omits the base->base identity row
    target_rate = into_base.get(target.upper())
    if not target_rate:
        return fx
    for src, rate in into_base.items():
        fx[src] = rate / target_rate
    return fx


def parse_statement(
    payload: bytes,
    target_currency: str = DEFAULT_TARGET_CURRENCY,
) -> tuple[list[Account], dict[str, float]]:
    """
    Turn a Flex statement into per-account position lists valued in
    `target_currency`, plus the currency -> target FX map the statement carried.
    """
    root = _parse_xml(payload)
    if root.tag != "FlexQueryResponse":
        _check_status(root)
        raise IbkrError(f"Expected a Flex statement, got <{root.tag}>")

    target = target_currency.upper()
    fx = _build_fx(root, target)
    accounts: dict[str, Account] = {}

    for statement in root.iter("FlexStatement"):
        stmt_account = statement.get("accountId") or ""
        report_date = statement.get("toDate") or statement.get("whenGenerated")

        open_positions = list(statement.iter("OpenPosition"))
        if not open_positions and not stmt_account:
            continue

        for el in open_positions:
            account_id = el.get("accountId") or stmt_account
            if not account_id:
                continue
            currency = (el.get("currency") or target).upper()
            quantity = _num(el, "position", "quantity") or 0.0
            mark = _num(el, "markPrice", "closePrice") or 0.0
            value = _num(el, "positionValue", "value")
            if value is None:
                value = quantity * mark
            rate = fx.get(currency)

            account = accounts.setdefault(
                account_id,
                Account(accountId=account_id, alias=statement.get("accountAlias") or "",
                        reportDate=report_date, totalGBP=0.0),
            )
            account.positions.append(Position(
                accountId=account_id,
                symbol=el.get("symbol") or "",
                description=el.get("description") or "",
                assetCategory=el.get("assetCategory") or "",
                currency=currency,
                conid=el.get("conid") or "",
                isin=(el.get("isin") or el.get("securityID") or "").upper(),
                quantity=quantity,
                markPrice=mark,
                value=round(value, 2),
                valueGBP=round(value * rate, 2) if rate is not None else None,
                costBasis=_cost_basis(el, quantity),
                unrealizedPnl=_num(el, "fifoPnlUnrealized"),
                reportDate=el.get("reportDate") or report_date,
            ))

        # An account with a statement but no open positions is still worth
        # listing, so it can be linked in the UI before it holds anything.
        if stmt_account:
            accounts.setdefault(
                stmt_account,
                Account(accountId=stmt_account, alias=statement.get("accountAlias") or "",
                        reportDate=report_date, totalGBP=0.0),
            )

    for account in accounts.values():
        converted = [p.valueGBP for p in account.positions if p.valueGBP is not None]
        # Partial conversion would understate the account, so only total up when
        # every position has a rate.
        account.totalGBP = (
            round(sum(converted), 2)
            if len(converted) == len(account.positions) else None
        )
        account.positions.sort(key=lambda p: p.valueGBP or 0, reverse=True)

    return list(accounts.values()), fx


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def read_cache() -> dict | None:
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(snapshot: dict) -> None:
    try:
        CACHE_FILE.write_text(json.dumps(snapshot, indent=2))
    except OSError:
        pass  # a cache we can't persist is not worth failing the request over


def _cache_age_seconds(snapshot: dict | None) -> float | None:
    if not snapshot or not snapshot.get("fetchedAt"):
        return None
    try:
        fetched = datetime.fromisoformat(snapshot["fetchedAt"])
    except ValueError:
        return None
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched).total_seconds()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def fetch_positions(force: bool = False) -> dict:
    """
    Return the current IBKR snapshot:

        { accounts: [...], fetchedAt, baseCurrency, stale, source }

    Serves the cache when it is fresher than MIN_REFETCH_SECONDS (unless
    `force`), and falls back to it — flagged `stale` — when IBKR is unreachable.
    """
    cfg = load_config()
    if cfg is None:
        raise IbkrNotConfigured("IBKR is not configured — see docs/ibkr-setup.md")

    cached = read_cache()
    age = _cache_age_seconds(cached)
    if cached and age is not None and age < MIN_REFETCH_SECONDS and not force:
        return {**cached, "stale": False, "source": "cache", "cacheAgeSeconds": round(age)}

    try:
        accounts, fx = parse_statement(request_statement(cfg), cfg.base_currency)
    except IbkrError:
        if cached:
            return {**cached, "stale": True, "source": "cache",
                    "cacheAgeSeconds": round(age) if age is not None else None}
        raise

    snapshot = {
        "accounts": [asdict(a) for a in accounts],
        "fxRates": fx,
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "baseCurrency": cfg.base_currency,
    }
    write_cache(snapshot)
    return {**snapshot, "stale": False, "source": "ibkr", "cacheAgeSeconds": 0}


# ---------------------------------------------------------------------------
# Mirroring into the store
# ---------------------------------------------------------------------------
# IBKR's LSE symbols carry a lowercase venue suffix ("AZNl") and its US/EU ones
# occasionally differ from the Yahoo-style codes the app keys on. Map the ones
# that differ; everything else passes through unchanged.
TICKER_ALIASES = {"AZNL": "AZN", "BAL": "BA."}


def _aliases() -> dict:
    import local
    return local.merge("IBKR_TICKER_ALIASES", dict(TICKER_ALIASES))


def _app_ticker(symbol: str, currency: str, known: set[str]) -> str:
    """Translate an IBKR symbol into the ticker this app uses."""
    alias = _aliases().get(symbol.upper())
    if alias:
        return alias
    # General LSE rule: "XYZl" -> "XYZ", but only when the shortened form is
    # already tracked, so an unrelated symbol is never mangled.
    if currency.upper() == "GBP" and symbol.endswith("l") and symbol[:-1].upper() in known:
        return symbol[:-1]
    return symbol


def plan(snapshot: dict, stocks: list[dict], etf_tickers: set[str], etf_isins: set[str]) -> dict:
    """
    Work out what a sync would change, without touching anything.

    Splits IBKR positions into stocks (mirrored) and ETFs (reported only), then
    diffs the stock side against the stored stocks. ISIN is the stable identity:
    it survives the ticker renames and venue suffixes that would otherwise make
    a held position look like a sale plus a purchase.
    """
    from names import canonical_company_name
    positions = [p for a in snapshot.get("accounts", []) for p in a.get("positions", [])]
    existing = {s["ticker"].upper(): s for s in stocks}
    by_isin = {s["isin"].upper(): s for s in stocks if s.get("isin")}
    out, etfs = [], []

    for p in positions:
        symbol = (p.get("symbol") or "").strip()
        if not symbol:
            continue
        isin = (p.get("isin") or "").upper()
        if symbol.upper() in etf_tickers or isin in etf_isins:
            etfs.append({"ticker": symbol, "name": p.get("description") or "",
                         "quantity": p.get("quantity"), "currency": p.get("currency")})
            continue
        ticker = _app_ticker(symbol, p.get("currency") or "", set(existing))
        prev = by_isin.get(isin) or existing.get(ticker.upper()) or {}
        out.append({
            **{k: prev[k] for k in ("yahoo",) if k in prev},
            "ticker": prev.get("ticker", ticker),          # keep the spelling already in use
            "isin": isin or prev.get("isin"),
            # Fall back to what is stored rather than blanking a name or a cost
            # basis the statement did not include.
            "name": canonical_company_name(p.get("description") or "", isin) or prev.get("name") or symbol,
            "quantity": float(p.get("quantity") or 0),
            "last_price": float(p.get("markPrice") or 0),
            "currency": (p.get("currency") or "USD").upper(),
            "cost_basis_local": p["costBasis"] if p.get("costBasis") is not None else prev.get("cost_basis_local"),
        })

    seen = {s["ticker"].upper() for s in out}
    return {
        "stocks": out, "etfs": etfs,
        "toAdd": [s for s in out if s["ticker"].upper() not in existing],
        "toUpdate": [s for s in out if s["ticker"].upper() in existing],
        "toDelete": [s for t, s in existing.items() if t not in seen],
        "fxRates": snapshot.get("fxRates", {}),
        "fetchedAt": snapshot.get("fetchedAt"), "stale": snapshot.get("stale", False),
        "warnings": [] if positions else [
            "The statement contained no open positions — refusing to sync, as that would delete "
            "every stock. Check the Flex query's account and date period."],
        "safe": bool(positions),
    }


def apply(store, sync_plan: dict, backup_dir: Path, keep: int = 10) -> Path:
    """Replace the stored stocks with the plan's, after saving a JSON backup of
    the whole store. Only the currencies IBKR quoted are updated in `fx`."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"store-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    dest.write_text(json.dumps(store.dump()))
    for old in sorted(backup_dir.glob("store-*.json"))[:-keep]:
        old.unlink(missing_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.set_many({
        "stocks": [{**s, "updated_at": stamp} for s in sync_plan["stocks"]],
        "fx": {**store.get("fx", {}), **{c: float(r) for c, r in sync_plan["fxRates"].items()}},
    })
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Fetch IBKR positions via Flex Web Service")
    ap.add_argument("--force", action="store_true", help="ignore the local cache")
    ap.add_argument("--json", action="store_true", help="print the raw snapshot")
    args = ap.parse_args()

    try:
        snap = fetch_positions(force=args.force)
    except IbkrError as err:
        raise SystemExit(f"error: {err}")

    if args.json:
        print(json.dumps(snap, indent=2))
    else:
        print(f"fetched {snap['fetchedAt']} via {snap['source']}"
              f"{' (STALE)' if snap['stale'] else ''}")
        for acct in snap["accounts"]:
            total = acct["totalGBP"]
            total_str = f"£{total:,.2f}" if total is not None else "n/a"
            print(f"\n{acct['accountId']} {acct['alias']}  {total_str}  ({acct['reportDate']})")
            for p in acct["positions"]:
                gbp = p["valueGBP"]
                print(f"  {p['symbol']:<12} {p['quantity']:>12,.4f} "
                      f"{p['currency']} {p['value']:>14,.2f}"
                      f"  →  {'£%s' % format(gbp, ',.2f') if gbp is not None else 'no FX'}")
