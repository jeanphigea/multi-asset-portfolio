# 03 · Reference data (`reference.py`)

## Purpose

All the static judgement and taxonomy the app relies on lives in one module: the
sector mapping, company profiles, benchmarks, currencies, scenarios and symbols.
None of it is fetched. Each block carries an as-of date, which the UI shows.
The browser receives most of it once, through `/reference.js` (see 09).

## Sector taxonomy (GICS)

- **`MSCI_WORLD_SECTORS`** (as of `MSCI_WORLD_AS_OF`) gives the 11 GICS sectors
  with approximate MSCI World weights.
- **`GICS_ORDER`** is the display order: the 11 sectors, then `Commodities`,
  `Cash & Money Market`, then `Unclassified`.
- **`GICS_FROM_YAHOO`** maps Yahoo's sector names (lower-cased) to GICS. For
  example "technology" → Information Technology and "financial services" →
  Financials.
- **`GICS_FROM_LABEL`** maps the shorthand labels used in `COMPANY_ESTIMATES`
  (lower-cased) to GICS, for example "semis" → Information Technology and
  "gold mining" → Materials. Every GICS sector name also maps to itself.

**A company's sector** is decided by `gicsSector(key, label, yahooSector)` in
the browser. The first rule that applies wins:

1. If the key is in `COMMODITY_SECTORS`, the sector is `Commodities`.
2. If Yahoo's sector maps through `GICS_FROM_YAHOO`, use that.
3. Otherwise use the curated `COMPANY_PROFILES[key][0]`.
4. Otherwise map the shorthand label through `GICS_FROM_LABEL`, then through
   `GICS_FROM_YAHOO`.
5. Otherwise the sector is `Unclassified`.

Cash-like holdings get `CASH_SECTOR = "Cash & Money Market"` from their profile.

## Company profiles

**`COMPANY_PROFILES`** maps `{company_key: (GICS sector, country)}` for every
company the demo's look-through reaches, about 115 of them. The as-of date is
`COMPANY_PROFILES_AS_OF`. Country follows MSCI's classification where that is
unambiguous; otherwise it is the country of primary listing and incorporation.
For example, Tencent is China, not Hong Kong.

**A company's country** is decided by `countryOf(key)` in the browser:

1. If the key is in `COMMODITY_SECTORS`, the "country" is `Commodities`.
2. Otherwise use the profile's country.
3. Otherwise use Yahoo's `country`, after normalising its spelling (for example
   "Korea, Republic of" → South Korea).
4. Otherwise the country is `Unknown`.

**`COUNTRY_META`** maps each country to `(region, market class)`. The market
class is `DM`, `EM` or `Frontier`. "Commodities" and "Cash" map to
`("Non-equity", "—")`.

**`COMPANY_ESTIMATES`** maps `{key: [ticker, label, roe, fcf_margin, de,
eps_growth, net_margin, roic, div_yield, beta, pe]}`. The values are display
strings such as `'32.0%'`, `'0.08x'` and `'~23×'`; `'—'` means unknown. They
are static FY2024 estimates. They are shown in grey where Yahoo has no live
value, and they are the only source of ROIC.

## Benchmarks

`BENCHMARKS[key]` has the fields `name`, `ticker`, `note`, `sectors`,
`countries` and `tags`:

- `ticker` is a GBP-quoted ETF, used for the historical metrics.
- `sectors` and `countries` are approximate weights in %. The browser
  normalises them to sum to 100 before using them.
- `tags` gives the % of the index in each scenario theme: semis, ai_megacap,
  banks, gold_miners, defence, autos and bitcoin.

| key | name | ticker | countries |
|---|---|---|---|
| `acwi` | MSCI ACWI | SSAC.L | `MSCI_ACWI_COUNTRIES` (includes "Other" ≈ 2.85) |
| `world` | MSCI World | SWDA.L | ACWI minus EM, Frontier and Other, renormalised |
| `sp500` | S&P 500 | VUSA.L | United States 100 |
| `ftse100` | FTSE 100 | ISF.L | United Kingdom 100 |
| `nasdaq100` | Nasdaq-100 | EQQQ.L | United States 100 |

## Risk constants

- `RISK_FREE_RATE = 4.0` (% a year). It is used in Sharpe and Sortino, and as
  the return on cash.
- `CASH_TICKERS = {"CSH2"}`. These positions are valued like any other, but
  they earn the risk-free rate in the history and move 0% in a scenario.
- `HISTORICAL_EPISODES` is a list of `{key, name, start, end}`: Q4 2018, COVID
  crash, 2022 rates shock, UK mini-budget, yen carry unwind, DeepSeek day, and
  the 2025 tariff shock.

## Currencies

- `COUNTRY_CCY` gives the currency each country's equities trade in, for
  example United States → USD and Taiwan → TWD.
- `CCY_GROUP` falls back from a currency to a group: CAD, AUD, NZD and NOK →
  `commodity_fx`; BRL, MXN, CNY, TWD, KRW, INR, ZAR, SGD and ILS → `EM`; SEK
  and DKK → `EUR`.
- `AI_MEGACAPS` is the list of company keys tagged `ai_megacap`: alphabet,
  microsoft, amazon, meta platforms, apple, nvidia, broadcom and tesla.

## Scenarios

`SCENARIOS` (as of `SCENARIOS_AS_OF`) is a list of dicts. Spec 07 explains how
they are used.

```
{key, name, horizon, analog, story,
 market: %,                       # applied to every equity
 sectors: {GICS sector: %},       # added on top
 countries: {country: %},
 tags: {theme: %},
 commodities: {commodity type: %},
 fx: {USD|EUR|JPY|CHF|EM|commodity_fx|…: % move vs GBP}}
```

## Symbols

- **`ISIN_MAP`** maps ETF ticker → ISIN. It identifies a fund across brokers,
  for example CSPX and CSP1, which share an ISIN.
- **`YAHOO_ETF`** and **`YAHOO_STOCK`** map the app's ticker to a Yahoo symbol,
  for example `VUSA` → `VUSA.L` and `700` → `0700.HK`. A position's own
  `yahoo` field overrides these maps. An ETF in neither place is tried as
  `<ticker>.L`, since a sterling investor's UCITS ETFs are almost always
  London-listed.
- **`NON_EQUITY_ETFS`** lists funds whose holdings are futures, bullion or bonds
  (SGLN in the demo). They are never scored.
- **`FX_PAIRS`** maps each currency to its Yahoo GBP pair, for example
  `USD` → `USDGBP=X`, along with EUR, HKD, CHF, SEK and DKK.
- **`COMPANY_YAHOO`** maps company key → Yahoo symbol for the companies that
  are scored. It is curated and includes exchange suffixes.

## Private overlay (`local.py`)

The public tables cover the demo portfolio. A user's own holdings usually need
more: Yahoo symbols, profiles, estimates, broker ISIN overrides and IBKR
aliases. Those live in `.data/reference.json`, which git ignores, so a public
repo never reveals what anyone holds. Its path can be overridden with
`LOCAL_REFERENCE`. Its top-level names are the tables it extends:
- `COMPANY_PROFILES`, `COMPANY_ESTIMATES`, `COMPANY_YAHOO`;
- `YAHOO_STOCK`, `YAHOO_ETF`, `ISIN_MAP`;
- `GICS_FROM_LABEL`, `NON_EQUITY_ETFS`, `CASH_TICKERS`;
- `COMPANY_NAME_BY_ISIN`, `NAME_ALIASES`, `NAME_ACRONYMS`;
- `IBKR_TICKER_ALIASES`.

At import time, dicts are merged over the public tables and lists are added to
the public sets. Profiles are lists in JSON and become tuples.

## Acceptance checks

1. Every key in `COMPANY_PROFILES` is already a `company_key` of itself.
2. Every benchmark has non-empty `sectors` and `countries`.
3. Every GICS sector in `SCENARIOS[*].sectors` is in `MSCI_WORLD_SECTORS`.
