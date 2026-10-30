# Multi-Asset Portfolio

A self-hosted dashboard for a sterling investor who owns a mix of **ETFs** and
**individual stocks**. It looks through every ETF to the companies inside,
merges them with your direct holdings, and shows four things:

- **What you really own.** It gives one row per company, combining direct
  holdings with ETF look-through. Each row carries four /20 scores: Momentum and
  a multi-year Quality score, both computed from Yahoo Finance, plus
  hand-researched **AI Maturity** and **Compute as asset** scores. It also shows
  the company's fundamentals.
- **Sector allocation.** Every holding is mapped to GICS and compared with a
  benchmark you choose: MSCI ACWI, MSCI World, S&P 500, FTSE 100 or Nasdaq-100.
- **Country exposure.** It shows countries and regions against the same
  benchmark, plus your DM/EM split and how much sits outside equities.
- **Risk.** It replays today's mix through up to 10 years of real prices in GBP
  and reports max drawdown, volatility, beta, VaR, Sharpe, capture ratios and
  risk contributions. It also runs eight **"plausible today" crash scenarios**
  (an AI capex bust, a Taiwan crisis, a gilt crisis, …) and seven historical
  sell-offs, each set against the benchmark.

> ⚠️ This is not investment advice. The benchmark weights and scenario shocks
> are static, approximate and dated. ETF providers publish only their top
> holdings, so the look-through covers part of each fund (the app shows how
> much).

## Quick start (local)

You need Python 3.11 or newer.

```bash
git clone <this repo> multi-asset-portfolio && cd multi-asset-portfolio
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                      # http://localhost:5050
```

On macOS, double-clicking **`Start Dashboard.command`** does the same. It keeps
its virtual environment in `~/.venvs/multi-asset-portfolio`.

On first run the app loads a **demo portfolio** (`data/demo.json`). To fill in
prices, history and scores, click **Refresh market data**; it takes about two
minutes. Then make the portfolio yours:

- **ETFs** button: set your tickers and shares. A new ETF's holdings are
  entered on its card as `Name, Weight%` lines.
- **Direct holdings** button: set your stocks (ticker, name, quantity, price,
  currency) and FX rates, or sync from Interactive Brokers
  (see [docs/ibkr-setup.md](docs/ibkr-setup.md)).

Prices come from Yahoo Finance. A position can carry its own `yahoo` symbol;
otherwise the app uses the maps in `reference.py`, and an unmapped ETF is tried
as `<ticker>.L`.

**Your data stays private.** Positions and scores live in `.data/store.db`.
Extra reference data for your own holdings (Yahoo symbols, sector and country
profiles, broker ISINs) goes in `.data/reference.json`; see `local.py`. Git
ignores both files. The public repo only describes the demo.

**AI Maturity and Compute scores** come from research, not market data. Add or
update one with:

```bash
curl -X POST localhost:5050/api/ai-maturity -H 'Content-Type: application/json' \
  -d '{"key": "nvidia", "dims": [3,3,2.5,3.5,2,3,2.5,2.5], "source": "10-K 2026", "as_of": "2026-10"}'
```

Methods and formulas are in [spec/12](spec/12-research-scores.md).

## How it works

```
static page (app.js) ──JSON──► Flask (app.py) ──► store.py ──► SQLite file  or  Upstash Redis
   look-through, sectors,        portfolio.py  positions, summary
   countries, scenarios          market.py     Yahoo prices, fundamentals, quality
                                 risk.py       price history, risk metrics
                                 reference.py  taxonomy, benchmarks, scenarios
```

- **The server** does the network calls and the numerical work.
- **The browser** aggregates per company, so toggles and benchmark switches are
  instant.
- **All state** is a handful of JSON documents in a key/value store: a local
  SQLite file by default, or Upstash Redis when its environment variables are
  set.

Every calculation is defined precisely in **[`spec/`](spec/README.md)**: the
look-through, the Momentum and Quality scores, every risk metric, and the
scenario model. Each comes with worked examples, which double as tests. The
specs are detailed enough to rebuild the app from scratch with Claude Code;
see `spec/README.md` for the prompt.

## Configuration

Copy `.env.example` to `.env`, or set the variables in your host:

| Variable | Purpose |
|---|---|
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | Use Upstash Redis instead of the local file. Vercel's `KV_REST_API_*` names also work. |
| `STORE_PREFIX` | Key namespace (default `map:`), so several datasets can share one database. |
| `DEMO_MODE=1` | Read-only: no edits, no refresh buttons, no on-demand downloads. |
| `CRON_SECRET` | Protects `/api/cron/refresh`. |
| `REPO_URL` | "Run your own copy" link in the demo banner. |
| `IBKR_FLEX_TOKEN`, `IBKR_FLEX_QUERY_ID` | Optional IBKR sync (local only). |

## Deploying a demo to Vercel with Upstash

1. **Create an Upstash Redis database.** The free tier is enough. The easiest
   route is Vercel → Storage → Marketplace → Upstash, which sets the environment
   variables for you.
2. **Import the GitHub repo** in Vercel (Add New → Project). No build settings
   are needed: `vercel.json` routes every request to the Flask app in
   `api/index.py`.
3. **Set the environment variables:**

   | | Production | Preview |
   |---|---|---|
   | `DEMO_MODE` | `1` | `1` |
   | `STORE_PREFIX` | `demo:` | `preview:` |
   | `CRON_SECRET` | a long random string | same |
   | `REPO_URL` | your GitHub URL | same |

4. **Seed and warm the demo** once, from your machine, so the first visitor
   sees full data:

   ```bash
   UPSTASH_REDIS_REST_URL=… UPSTASH_REDIS_REST_TOKEN=… STORE_PREFIX=demo: \
     python scripts/seed.py --refresh
   ```

5. **Daily refresh.** A Vercel Cron job (in `vercel.json`) calls
   `/api/cron/refresh` at 06:00 UTC on weekdays. It refreshes prices, history,
   fundamentals and quality within the function's 300-second limit.

### Automatic deployments

Once the repo is connected, Vercel's GitHub integration deploys every push:

- a push to **`main`** goes to **production**, the public demo;
- any other **branch or pull request** gets its own **preview URL**, which
  Vercel posts on the PR. Previews use the `preview:` prefix, so they never touch
  the demo's data.
- Every deployment is kept, and **Instant Rollback** restores an earlier one.

GitHub Actions runs the tests on every push and PR
(`.github/workflows/test.yml`). Turn on **branch protection** for `main` and
require the `tests` check, so only tested code is merged and deployed. The
workflow is: branch, then PR, then check the preview, then merge.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

| Path | Contents |
|---|---|
| `app.py` | Routes and demo-mode rules |
| `store.py` | Key/value store (file or Upstash) |
| `portfolio.py` | Positions, valuation, look-through summary, seeding |
| `market.py` | Yahoo prices, fundamentals, Quality score |
| `risk.py` | Price history and risk metrics |
| `reference.py` | GICS mapping, company profiles, benchmarks, scenarios, symbols |
| `names.py` | Company-name normalisation, shared with the browser |
| `scores.py` | AI maturity and compute-as-asset scores |
| `local.py` | Merges your private reference data (`.data/reference.json`) |
| `ibkr.py` | Optional Interactive Brokers sync |
| `templates/`, `static/` | The page |
| `data/demo.json` | Demo portfolio |
| `scripts/` | `seed.py` (load and refresh a store), `migrate_sqlite.py` (import from the old SQLite version) |
| `spec/` | Rebuild specs |
| `tests/` | pytest suite |

Reference data (benchmark weights, company profiles and scenarios) is
hand-maintained in `reference.py`. Each block has an as-of date that the UI
shows. Update the date when you update the figures.

## Licence

To be decided by the owner.
