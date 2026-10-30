# 04 · Portfolio and exposure (`portfolio.py`, exposure code in `static/app.js`)

## Purpose

This module values each position in GBP and looks through each ETF to the
companies it holds. It merges those companies with the direct holdings, then
breaks the result down by sector and country against a benchmark.

The **server** half (`portfolio.py`) does three things:
- values positions;
- serves the look-through inputs as a single `/api/summary` document;
- seeds the store.

The **browser** half aggregates the summary into company rows, sectors and
countries. Toggles therefore re-render with no round trip.

## Valuation

- **ETF value** = `shares × last_price_gbp`. ETF prices are stored in GBP (see 05).
- **Stock value** = `quantity × last_price × fx[currency]`. `fx` gives GBP per
  unit; `GBp` is 0.01 and `GBP` is 1. An unknown currency counts as 1.
- **Grand total** = the sum of ETF values plus the sum of stock values.

## `/api/summary` (server)

The response is a list with one entry per ETF, sorted by ticker:

```
{ticker, shares, last_price_gbp, last_price_date,
 total_covered_pct = round(Σ weight of ALL rows, 2),      # coverage
 is_direct: false,
 holdings: top 50 rows by weight, each
   {holding_name: display_name(name), holding_ticker, weight_pct, as_of_date, source}}
```

If there are any stocks, it ends with **one synthetic `DIRECT` entry**. It is
shaped like an ETF so the browser can treat both the same way:

```
{ticker: "DIRECT", is_direct: true, shares: Σ stock values (GBP, 2 dp),
 last_price_gbp: 1.0, total_covered_pct: 100, position_count,
 holdings: stocks by value desc, each {holding_name: name, holding_ticker: ticker,
           weight_pct = value / Σ values × 100 (4 dp), source: "manual"}}
```

With this shape, the value of any holding inside any entry is
`weight_pct/100 × shares × last_price_gbp`.

## Company rows (browser: `buildExposureRows({scaled})`)

For each entry `E` and each holding `h` in it:

1. Skip bond lines, meaning any name matching `\d+\.\d+%`.
2. Compute the key `k = companyKey(h.holding_name)`.
3. Compute the scale factor `f`:
   - when `scaled` is on, `f = 100 / E.total_covered_pct` for an ETF with
     coverage > 0;
   - otherwise `f = 1`.
4. Compute the value: `gbp = h.weight_pct/100 × E.shares × E.last_price_gbp × f`.
   If the price is unknown, `gbp = 0`.
5. Add `gbp` to `rows[k].direct` when `E` is DIRECT. Otherwise add it to
   `rows[k].etfExp`, and record `E.ticker` in `rows[k].sources`.
6. **Choose the display name.** A DIRECT name always wins. Otherwise the name
   with the higher `nameRank` wins:
   `nameRank(n) = (has "(digits)" ? 0 : 2000) + (has any "(…)" ? 0 : 1000) + length`.

Then set `total = direct + etfExp`, drop rows where `total ≤ 0`, and sort by
total, largest first.

**Scaled mode** spreads each ETF's unpublished remainder in the same proportions
as its visible holdings. That is exact for a single-country fund, and an
approximation for a broad one. The Countries tab offers it as a toggle (off by
default). The scenarios always use it.

### Worked example (it is also a test)

- ETF AAA: 100 shares at £50. Holdings: Apple Inc 10%, Microsoft Corp 5%, so
  coverage is 15%.
- Stocks: AAPL "Apple" 10 shares at $200 with `fx.USD = 0.75`, worth £1,500.
  AZN "AstraZeneca" 5 shares at £100, worth £500.
- DIRECT shares = £2,000, with weights AAPL 75% and AZN 25%.

| key | direct | etfExp | total |
|---|---|---|---|
| apple | 1,500 | 10% × 100 × 50 = 500 | 2,000 |
| astrazeneca | 500 | 0 | 500 |
| microsoft | 0 | 250 | 250 |

The grand total is £5,000 + £2,000 = £7,000. Apple is 2,000 / 7,000, or 28.6%
of the portfolio.

## Exposure table columns

| Column | Definition |
|---|---|
| Direct (£) | Value of the company held directly. |
| ETF Exp. (£) | The sum over ETFs of `weight/100 × shares × price`. |
| TOTAL (£) | Direct + ETF exposure. |
| % Combined | `total / grand total × 100`. |
| Sources | The ETFs that hold the company. |
| Notes | "Direct + ETF", "Direct only" or "ETF only". |
| Sector, Country | As defined in 03. |
| Momentum /20, Quality /20 and the fundamentals | As defined in 05. |
| AI Maturity /20, Compute /20 | As defined in 12. |

There are four filters: All, Direct + ETF (both > 0), Direct (direct > 0) and
ETF only (direct = 0). Search matches the name, ticker, label, Yahoo symbol,
industry, sector, country and sources.

## Sector breakdown (browser)

1. Take the 200 largest unscaled rows (`SECTOR_LIMIT`). Map each to
   `sectorOf(key)` (see 03) and sum the totals per sector.
2. **Portfolio weight**: `w_p(s) = Σ total in s / Σ total` over every row
   included. Commodities and cash are included.
3. **Benchmark weight**: `w_b(s) = sectors[s] / Σ sectors × 100`, for the
   selected benchmark.
4. **Active weight**: `w_p(s) − w_b(s)`, in percentage points, for **every**
   sector in either set. A sector missing from one side counts as 0 there. The
   app never shows "not in index"; it always does the maths.

## Country breakdown (browser)

1. Take the rows, with scaled mode as toggled, and group them by
   `countryOf(key)`.
2. `Unknown`, `Commodities` and `Cash` (`NON_COUNTRY`) are shown separately and
   do not count in the comparison.
3. **Equity total** = the sum over equity countries. The portfolio weight is
   `total(c) / equity total × 100`.
4. The benchmark weight is `countries[c]`, normalised to 100.
5. The difference is `w_p(c) − w_b(c)` for every country. Index countries the
   portfolio does not hold are listed too, at 0%.
6. Regions come from `COUNTRY_META` and are summed the same way. A benchmark's
   `Other` bucket (small markets it does not list individually) belongs to no
   region. The benchmark's region total is therefore `100 − Other`, and a note
   says so. KPIs show the largest country, the United Kingdom, emerging markets
   (EM + Frontier) and the value outside equities.
7. The note under the table states how much of the portfolio is "seen", that
   is, the sum of rows compared with the grand total.

## Seeding and writes (server)

- **`seed(store, path=data/demo.json)`** writes `etfs`, `stocks`, `fx` (merged
  over the defaults) and one `holdings:<ETF>` document per fund.
- **`is_empty(store)`** is true when there are no `etfs` and no `stocks`. The
  app seeds from the demo on the first request to an empty store.
- **`set_etfs([{ticker, shares, yahoo?}])`** replaces the list. Tickers are
  upper-cased. It keeps each existing ETF's price and `added_at`.
- **`set_holdings(ticker, [{name, ticker, weight, as_of_date}])`** stores rows
  with weight > 0, with `source = "manual"`.
- **`set_stocks([...])`** replaces the list. It keeps each existing stock's
  `isin` and `yahoo` fields.
- **`set_fx({ccy: rate})`** merges new rates into the stored ones.
- **`positions(store)`** returns `[{id, name, kind: etf|stock|cash, symbol,
  value}]` for the risk model (06).

## Acceptance checks

1. The worked example above holds.
2. On the demo seed, the DIRECT weights sum to 100 (± 0.001).
3. `set_etfs` keeps the price of an ETF that is still held. A new, unmapped
   ticker `NEW1` is priced as `NEW1.L`.
4. Sector weights sum to 100. Country equity weights sum to 100.
