# 09 · HTTP API (`app.py`)

## Purpose

`app.py` contains only routes. Each route reads the store, calls one module
function and returns JSON. The app is stateless between requests, apart from
the store singleton, so it runs as a serverless function unchanged.

**First request to an empty store.** If `etfs` and `stocks` are both missing,
`data/demo.json` is seeded (see 04).

**Demo mode** (`DEMO_MODE=1`):
- Every request whose method is not GET, HEAD or OPTIONS gets **403**
  `{ok: false, error: "This is a read-only demo."}`. The only exception is
  `/api/cron/refresh`.
- `/api/risk` never downloads. It reads stored history only, and ignores
  `refresh=1`.
- IBKR is reported as not configured.

## Endpoints

| Method and path | Body / query | Response |
|---|---|---|
| `GET /` | | The page. The template receives `demo`, `repo_url` and the asset version `v`. |
| `GET /reference.js` | `?v=` (cache buster) | `window.REF = {…};` (see below). Cached for 1 day. |
| `GET /api/summary` | | The ETF and DIRECT entries (see 04). |
| `POST /api/portfolio` | `[{ticker, shares, yahoo?}]` | `{ok, etfs}`. Replaces the ETF list. |
| `POST /api/holdings/<ETF>` | `[{name, ticker, weight, as_of_date}]` | `{ok, count}`. Replaces the fund's holdings. |
| `GET /api/stocks` | | `[{…stock, market_value_gbp}]`, sorted by ticker. |
| `POST /api/stocks` | `[{ticker, name, quantity, last_price, currency, cost_basis_local}]` | `{ok, count}`. Replaces the list. |
| `GET /api/fx` | | `{ccy: rate}`, the defaults merged with the stored rates. |
| `POST /api/fx` | `{ccy: rate}` | `{ok}`. Merges the rates. |
| `GET /api/fundamentals` | | The `fundamentals` document (see 05). |
| `GET /api/quality` | | The `quality` document (see 05). |
| `GET\|POST /api/ai-maturity`, `GET\|POST /api/compute-asset` | see 12 | The scores, or the written row with `score20`. Bad input returns 400. |
| `POST /api/refresh?part=prices\|history\|fundamentals\|quality` | | That part's result: `{ok, refreshed or updated, errors, skipped?}`. Any other `part` returns 400. |
| `GET\|POST /api/cron/refresh` | header `Authorization: Bearer $CRON_SECRET` | `{prices, history, fundamentals, quality}`, each a summary with an error *count*. Returns 401 if the secret is missing or wrong, or if `CRON_SECRET` is unset. |
| `GET /api/risk?benchmark=<key>&years=1\|3\|5\|10[&refresh=1]` | | The risk report (see 06) plus `benchmark {key, name, ticker, note}`. An unknown benchmark or lookback returns 400. |
| `GET /api/ibkr/status` | | `{configured, error, fetchedAt, accounts}` (see 08). |
| `POST /api/ibkr/sync` | `{dry_run}` | The plan, or the applied plan (see 08). |

**The `history` part** refreshes, with `force=True`, every held symbol that is
not cash, every `FX_PAIRS` symbol and every benchmark ticker. It then sets
`meta.history_at`.

**The cron job** runs `prices → history → fundamentals → quality` with a shared
deadline of `now + CRON_BUDGET_SECONDS` (default 270 s, under Vercel's 300 s
limit). A part that starts after the deadline is reported as skipped. Each
part's result is saved as soon as that part finishes. The secret is compared in
constant time.

## `/reference.js`

`window.REF` contains:
- `DEMO` and `IBKR` (booleans);
- `NAME_ALIASES`, `COMMODITY_SECTORS`;
- `GICS_FROM_YAHOO`, `GICS_FROM_LABEL`, `GICS_ORDER`;
- `COMPANY_ESTIMATES`, `COMPANY_PROFILES`, `CASH_SECTOR`, `COUNTRY_META`;
- `MSCI_WORLD_AS_OF`, `MSCI_ACWI_AS_OF`, `MSCI_ACWI_SOURCE`;
- `BENCHMARKS`, with `{name, note, sectors, countries, tags}` per key;
- `SCENARIOS`, `SCENARIOS_AS_OF`, `COUNTRY_CCY`, `CCY_GROUP`, `AI_MEGACAPS`;
- `RISK_FREE_RATE`, `AI_DIMENSIONS`.

The script is built once, at import time. **Asset versioning**: `v` is the
first 10 hex characters of the SHA-1 of the reference script, `static/app.js`
and `static/app.css`. The page loads all three with `?v=`, so each deploy busts
the browser's cache, and long caching is safe.

## Acceptance checks

1. The first `GET /api/summary` on an empty store returns 8 entries: 7 ETFs
   plus DIRECT.
2. `/reference.js` starts with `window.REF = {` and contains `"BENCHMARKS"`.
3. In demo mode:
   - `POST /api/portfolio` returns 403;
   - `POST /api/refresh` returns 403;
   - the page body has `class="demo"`;
   - the IBKR status says not configured.
4. `/api/cron/refresh` returns 401 without the secret, and 401 with a wrong one.
5. Outside demo mode, `POST /api/portfolio [{VUSA,3}]` makes the summary list
   `[VUSA, DIRECT]`.
6. `/api/risk` with no stored history returns `ok: false`, with an explanation.
