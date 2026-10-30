# Rebuild specs

These files describe the whole app precisely enough to rebuild it from scratch,
for example with Claude Code. Each one covers a single module: what it does, its data,
**the exact definition of every calculation it makes**, edge cases, and
acceptance checks you can turn into tests.

The code in this repo is the reference implementation. Where the code and a spec disagree, the
code wins, and the spec should be fixed. The worked examples in the specs are
also unit tests in `tests/`, so most drift is caught.

| # | Spec | Module(s) |
|---|------|-----------|
| 00 | [Overview](00-overview.md) | architecture, conventions, environment |
| 01 | [Store](01-store.md) | `store.py` |
| 02 | [Company names](02-names.md) | `names.py`, `normalizeName`/`companyKey` in `static/app.js` |
| 03 | [Reference data](03-reference-data.md) | `reference.py` |
| 04 | [Portfolio and exposure](04-portfolio-exposure.md) | `portfolio.py`, exposure/sector/country code in `static/app.js` |
| 05 | [Market data and scores](05-market-data.md) | `market.py`, Momentum score in `static/app.js` |
| 06 | [Risk metrics](06-risk-metrics.md) | `risk.py` |
| 07 | [Stress scenarios](07-scenarios.md) | scenario code in `static/app.js`, `SCENARIOS` in `reference.py` |
| 08 | [IBKR sync](08-ibkr-sync.md) | `ibkr.py` |
| 09 | [HTTP API](09-api.md) | `app.py` |
| 10 | [Front end](10-frontend.md) | `templates/index.html`, `static/` |
| 11 | [Demo and deployment](11-demo-and-deploy.md) | `data/demo.json`, `vercel.json`, `api/index.py`, CI |
| 12 | [Research scores](12-research-scores.md) | `scores.py`, AI maturity and compute cells in `static/app.js` |

## Build order

Build the modules in this order, because each depends only on the ones before it:

1. **01 Store**, then **02 Names** and **03 Reference data**. These are pure data and helpers.
2. **04 Portfolio**, the server half (valuation, summary, seeding).
3. **05 Market data** (prices, fundamentals, quality).
4. **06 Risk**.
5. **09 API**, which wires 01–06 together.
6. **10 Front end**, then **04 exposure maths (browser half)**, then **07 Scenarios**.
7. **12 Research scores**.
8. **08 IBKR** (optional) and **11 Demo and deployment**.

## Prompt for Claude Code

Start a new project, copy `spec/` into it, and then for each step:

```
Read spec/00-overview.md and spec/NN-<name>.md. Implement that module exactly as
specified: same names, data shapes and formulas. Turn every worked example and
acceptance check in the spec into a pytest test (or a JS check for front-end
specs) and make them pass before moving on. Ask me before deviating from the spec.
```

To rebuild everything in one go:

```
Read every file in spec/ in order. Build the app module by module following the
build order in spec/README.md, running each module's acceptance checks before
starting the next. Finish with the end-to-end checks in spec/11-demo-and-deploy.md.
```

## Conventions used in the specs

- **%** values are percentages (25 means 25%), unless a unit says otherwise.
- **£** is GBP, the base currency. **GBp** is pence (1/100 of a pound), which is how
  many London-listed lines are quoted.
- A **company key** is the normalised company name defined in 02. Every
  per-company lookup is keyed by it.
- "Newest first" means index 0 is the latest year or day.
