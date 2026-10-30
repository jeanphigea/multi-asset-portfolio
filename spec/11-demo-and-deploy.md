# 11 · Demo and deployment (`data/demo.json`, `vercel.json`, `api/index.py`, CI)

## Demo portfolio (`data/demo.json`)

This is a fictional £100k portfolio, roughly 60% ETFs, 35% stocks and 5% cash.
It uses public ETF top-holdings data.

```
{etfs: [{ticker, shares, last_price_gbp, last_price_date}],
 stocks: [{ticker, name, quantity, last_price, currency, cost_basis_local: null}],
 fx: {ccy: rate},
 holdings: {ETF: {as_of, source: "db", rows: [{name, ticker, weight}]}},
 ai_maturity: {key: …}, compute_asset: {key: …}}     # scores for demo companies (see 12)
```

- **ETFs:**

  | ETF | Fund | Weight |
  |---|---|---|
  | VUSA | S&P 500 | 20% |
  | IWFQ | World Quality | 10% |
  | EMIM | EM IMI | 10% |
  | IAPD | Asia Pacific dividend | 5% |
  | INFR | Global infrastructure | 5% |
  | SGLN | Physical gold | 5% |
  | SMGB | Semiconductors | 5% |

- **Stocks:** NVDA, MSFT, AAPL, GOOG, AMZN, V, LLY, AZN, BA., RHM, ADYEN, 700
  (Tencent) and RACE, about 2.7% each. Every one has a Yahoo symbol and a
  company profile.
- **Cash:** CSH2.
- Share counts are rounded to two significant figures.

Prices in the file are only a starting point. The cron job re-marks them.

## Demo mode on Vercel

- `DEMO_MODE=1`: read-only (see 09). The page hides its edit controls.
- **Vercel Cron** calls `GET /api/cron/refresh` at `0 6 * * 1-5` (06:00 UTC on
  weekdays). Vercel adds `Authorization: Bearer $CRON_SECRET` automatically
  when the `CRON_SECRET` environment variable is set.
- `/api/risk` in demo mode reads the stored history only. Visitors therefore
  never trigger downloads from Yahoo.

## Vercel configuration

```
api/index.py        sys.path → project root; `from app import app` (WSGI)
vercel.json         functions["api/index.py"] = {maxDuration: 300,
                      includeFiles: "{templates,static,data}/**"}
                    rewrites: "/(.*)" → "/api/index"     (Flask routes everything)
                    crons: [{path: "/api/cron/refresh", schedule: "0 6 * * 1-5"}]
requirements.txt    pinned runtime deps (read by Vercel)
.python-version     3.12
.vercelignore       local data, tests, specs, scripts
```

The bundle (Flask, pandas, numpy, yfinance) is about 170 MB unzipped, within
Vercel's Python function limit. A full refresh of the demo takes about
2.5 minutes:

| Part | Time |
|---|---|
| Prices | ~10 s |
| History | ~10 s |
| Fundamentals | ~15 s for ~130 companies |
| Quality | ~2 min |

## Environments and data separation

| Vercel environment | `STORE_PREFIX` | `DEMO_MODE` | Purpose |
|---|---|---|---|
| Production (`main`) | `demo:` | 1 | The public demo |
| Preview (every other branch or PR) | `preview:` | 1 | Check a change before merging, without touching the demo's data |
| Local | `map:` (default) | off | Personal use with a file store |

All three can share one Upstash database.

## Setup steps (done by the owner, once)

1. **Upstash.** Create a Redis database. Either:
   - add it through Vercel's Marketplace integration, which sets
     `KV_REST_API_URL` and `KV_REST_API_TOKEN`; or
   - copy `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` by hand.
2. **GitHub.** Push the repo.
3. **Vercel.** Choose Add New → Project → Import the repo. Then set these
   environment variables:
   - `DEMO_MODE=1` and a random `CRON_SECRET`;
   - `STORE_PREFIX` as in the table above;
   - optionally `REPO_URL`.
4. **Seed and warm the demo** from a local machine, so the first visitor sees
   full data:

   ```
   UPSTASH_REDIS_REST_URL=… UPSTASH_REDIS_REST_TOKEN=… STORE_PREFIX=demo: \
     python scripts/seed.py --refresh
   ```

5. **Deploy.** It happens automatically on push (see below).

## CI/CD: from a push to a deployment

- **The Vercel GitHub integration** builds every push:
  - `main` deploys to **production**;
  - any other branch or PR gets a **preview** URL, which Vercel comments on
    the PR.
  - Deployments are immutable, and "Instant Rollback" restores an earlier one.
- **GitHub Actions** (`.github/workflows/test.yml`) runs `pytest` on every push
  and PR, on Python 3.12.
- **Branch protection on `main`** requires the `tests` check to pass before a
  merge. Vercel does not wait for GitHub checks, so the gate is the merge, not
  the deploy. Work on a branch, open a PR, check the preview, then merge.

## End-to-end acceptance

1. A fresh clone with no env vars:
   - `pip install -r requirements.txt`, then `python app.py`;
   - the demo is seeded;
   - all tabs render;
   - the Risk tab works after **Refresh market data** (or **Refresh history**).
2. With `DEMO_MODE=1`, `CRON_SECRET=s`, and a fresh store:
   - `curl -H "Authorization: Bearer s" /api/cron/refresh` fills prices,
     history, fundamentals and quality in under 270 s;
   - the Risk tab then renders without downloading anything;
   - any POST returns 403.
3. Pushing a branch produces a preview deployment. The production demo's data
   (prefix `demo:`) is unchanged.
4. `git ls-files` contains no `.db`, `.ibkr*.json`, `backups/`, `.data/` or
   `.env`.
