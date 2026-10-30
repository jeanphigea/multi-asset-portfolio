# 00 · Overview

## Purpose

The app is a single-user dashboard for a sterling investor who owns a mix of
**ETFs** and **individual stocks** (plus cash-like funds and commodity ETFs). It
answers four questions:

1. **What do I really own?** It looks *through* each ETF to its holdings and
   merges them with direct holdings, giving one row per company.
2. **How is that spread?** By GICS sector and by country, compared with a benchmark
   the user chooses.
3. **How good are those companies?** It gives two /20 scores: *Momentum*, from
   current fundamentals, and *Quality*, from 4–5 years of financial statements.
4. **How risky is the mix?** It reports history-based risk metrics against the
   benchmark, plus forward-looking crash scenarios.

It is not trading software and gives no advice.

## Architecture

```
Browser (static page)                     Server (Flask, stateless)            Storage
─────────────────────                     ─────────────────────────            ───────
templates/index.html                      app.py   routes, demo guard          store.py
static/app.js  ── fetch JSON ──────────►  portfolio.py  positions, summary  ─► FileStore (SQLite kv)
  look-through, sectors, countries,       market.py     Yahoo prices/scores     or
  momentum score, scenarios, charts       risk.py       history + metrics       RedisStore (Upstash REST)
/reference.js  ◄── static reference ───   reference.py / names.py
                                          ibkr.py       optional broker sync
                         Yahoo Finance (yfinance) ◄── market.py, risk.py
```

The work is split deliberately:

- **The server** does anything that needs network access, secrets or heavy
  numerical work: Yahoo downloads, scoring from statements, and pandas risk
  maths. It serves JSON.
- **The browser** does all per-company aggregation (look-through, sectors,
  countries, scenarios) from three JSON documents: summary, fundamentals and
  quality. Toggles and benchmark switches therefore re-render instantly,
  without a round trip.
- **Reference data** (taxonomy, benchmarks, scenarios, profiles) lives in
  Python. It is served to the browser once as `/reference.js`, so both sides
  share one copy.

## Data flow

1. Positions are entered by hand (ETF tickers and shares, stock rows), seeded
   from `data/demo.json`, or synced from IBKR.
2. ETF holdings are a list of `{name, ticker, weight%}` per fund, entered by
   hand or seeded. Providers publish only their top holdings, so the weights
   usually sum to less than 100%. This is called **coverage**.
3. **Refresh market data** has four parts, each saved as soon as it finishes:
   - `prices`: FX rates, stock prices and ETF prices.
   - `history`: up to 10 years of daily closes per symbol.
   - `fundamentals`: Yahoo's `.info` metrics per company.
   - `quality`: annual statements, turned into the Quality score.
4. The browser loads `/api/summary`, `/api/fundamentals` and `/api/quality`,
   then computes everything else. The Risk tab additionally calls `/api/risk`.

## Conventions

- **Base currency GBP.** Every value shown is in pounds. FX rates are stored as
  "1 unit of currency = x GBP". `GBp` (pence) is fixed at 0.01, and `GBP` at 1.
- **ETF prices are stored in GBP.** Stock prices are stored in the stock's own
  listing currency, and converted at display time.
- **Weekly returns** (Friday close) are used for volatility, beta, VaR and
  correlation. Holdings trade in different time zones, and daily returns across
  time zones understate correlation.
- **As-of dates everywhere.** Every static dataset carries an as-of date, and
  the UI shows it, so stale reference figures are never mistaken for live data.
- **Missing data is shown as missing.** A blank cell or a "low confidence" mark
  is preferred to a guess. A wrong match (for example the wrong company behind
  a ticker) is treated as worse than a gap.

## Tech stack

- Python 3.12, Flask 3, requests, yfinance, pandas, numpy. Versions are pinned in
  `requirements.txt`.
- Front end: one HTML page, vanilla JS, Chart.js 4.5 (CDN), and the Inter font.
  No build step.
- Storage: a key/value store, using either SQLite or Upstash Redis (see 01).
- Hosting: run locally (`python app.py`, port 5050) or on Vercel (see 11).

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | unset | Use Upstash Redis. `KV_REST_API_URL` / `KV_REST_API_TOKEN` also work. |
| `STORE_PATH` | `.data/store.db` | File store location, when Redis is not set. |
| `STORE_PREFIX` | `map:` | Prefix added to every key. |
| `DEMO_MODE` | off | `1` makes the app read-only (see 09 and 11). |
| `CRON_SECRET` | unset | Bearer token required by `/api/cron/refresh`. |
| `CRON_BUDGET_SECONDS` | 270 | The cron job stops starting new downloads after this long. |
| `REPO_URL` | unset | Link shown in the demo banner. |
| `IBKR_FLEX_TOKEN`, `IBKR_FLEX_QUERY_ID`, `IBKR_BASE_CURRENCY` | unset | Optional IBKR sync (see 08). |
| `PORT` | 5050 | Port for local runs. |

## Acceptance (whole app)

- A fresh checkout with no environment variables starts, seeds the demo
  portfolio, and renders all five tabs without console errors.
- `pytest` passes.
