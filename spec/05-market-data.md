# 05 · Market data and scores (`market.py`, Momentum score in `static/app.js`)

## Purpose

This module pulls everything market-derived from Yahoo Finance through
`yfinance`:
- prices and FX;
- per-company fundamentals, which feed the **Momentum /20** score;
- 4–5 years of annual statements, which feed the **Quality /20** score.

## Fetching rules

- Use `yfinance`, with its timezone cache set to `<tmp>/yfinance` because the
  home directory is read-only on serverless hosts.
- **Fetch in parallel**, with 8 workers. A failed symbol becomes an error string
  and never aborts the whole refresh.
- **Accept a deadline.** A `deadline` (epoch seconds) stops new fetches once it
  passes. Whatever finished by then is still saved, and the response reports
  how many were `skipped`.
- **Write once.** Each refresh writes its result to the store once at the end,
  then sets `meta.<part>_at`.

## Prices: `refresh_prices(store)`

A quote's price is `currentPrice`, falling back to `regularMarketPrice`, then
to `previousClose`.

1. **FX.** For each `FX_PAIRS` currency, `fx[ccy] = price(pair)`. Then force
   `fx.GBP = 1` and `fx.GBp = 0.01`.
2. **Stocks.** Use the symbol from the stock's `yahoo` field, or `YAHOO_STOCK`.
   Store the price in the **stock's own currency**.
   - If Yahoo quotes GBP and the stock is stored in GBp, or the reverse,
     multiply or divide by 100.
   - Any other currency mismatch is an error, and the price is left unchanged.
3. **ETFs.** Use the symbol from the ETF's `yahoo` field, or `YAHOO_ETF`, or
   `<ticker>.L`. Store
   `last_price_gbp = price × fx[quote currency]`, so a GBp quote is divided by
   100. Set `last_price_date` to today.
4. The response is `{ok, updated: {fx, stocks, etfs}, errors: [..], as_of}`.

## Which companies are scored: `scoring_universe(store)`

The result maps `company_key → (yahoo_symbol, derived)`. It is built from:

1. The curated `COMPANY_YAHOO` entries, with `derived = False`.
2. Direct stocks with a Yahoo symbol that is not already curated, using their
   name's key, with `derived = False`.
3. Constituents of every **held** equity ETF (anything not in
   `NON_EQUITY_ETFS`) whose ticker is non-empty and not purely digits, with
   `derived = True`. Purely numeric codes such as "005930" need an exchange
   suffix that the constituent list does not give.
4. Overrides from `yahoo_resolution`. A derived key with `ok = true` uses the
   resolved symbol and becomes non-derived. A derived key with `ok = false` is
   dropped, so it is not retried every time.

**Name check** (`name_agrees(key, yahoo_name)`). Let `a = key` and
`b = company_key(yahoo_name)`, each with a leading "the " and all spaces
removed. They agree when `a == b`, or one starts with the other.

**Symbol search** (`resolve_yahoo_ticker`). This is used when a derived symbol
fails the name check. Try `base`, then `base` + each suffix in order: .L .PA .DE
.AS .SW .MI .NS .SA .TO .HK .MC .ST .SI .AX .CO .OL .HE .BR .VI. Accept the
first symbol whose name agrees. Record the outcome in `yahoo_resolution`.

The reasoning: bare "CL" is crude oil in a commodity list but Colgate-Palmolive
on Yahoo. A missed match costs one blank row; a false match corrupts a
company's data.

## Fundamentals: `refresh_fundamentals(store)`

Each key's Yahoo `.info` is reduced to the fields below. A row is rejected when
`trailingPE`, `returnOnEquity` and `beta` are all missing. Rows that are not
refreshed keep their previous values.

| field | definition (Yahoo field) | unit |
|---|---|---|
| roe | returnOnEquity × 100 | % |
| fcf_margin | freeCashflow / totalRevenue × 100 | % |
| de | debtToEquity / 100 | × (Yahoo reports %) |
| eps_growth | earningsGrowth × 100 | % |
| net_margin | profitMargins × 100 | % |
| div_yield | dividendYield (already in %) | % |
| beta | beta | |
| pe | trailingPE | × |
| gross_margin | grossMargins × 100 | % |
| rev_growth | revenueGrowth × 100 | % |
| peg | trailingPegRatio | |
| ev_ebitda | enterpriseToEbitda | |
| payout | payoutRatio × 100 | % |
| m12_change | 52WeekChange × 100 | % |
| target_upside | (targetMeanPrice / currentPrice − 1) × 100 | % |
| rec_mean | recommendationMean (1 = strong buy … 5 = sell) | |
| sector, industry, country | as given | |

## Momentum /20 (browser: `computeScore`)

The score has five pillars. Each metric earns points by band:

- **Higher is better:** 4 if `v ≥ t1`, 3 if `v ≥ t2`, 1 if `v ≥ t3`, else 0.
- **Lower is better:** 4 if `v ≤ t1`, 3 if `v ≤ t2`, 1 if `v ≤ t3`, else 0.

| Pillar | Metric (direction, cut-offs t1 / t2 / t3) |
|---|---|
| Profitability | roe (hi 25/15/8) · ROIC from estimates (hi 20/12/6) · net_margin (hi 25/12/5) · gross_margin (hi 50/35/20) |
| Growth | rev_growth (hi 15/7/0) · eps_growth (hi 25/10/0) |
| Balance sheet | de (lo 0.3/1.0/2.0) · fcf_margin (hi 20/10/0) · payout (lo 40/60/80), only when > 0 |
| Valuation | pe (lo 15/25/40), only when > 0 · peg (lo 1/1.5/2.5), only when > 0 |
| Momentum | m12_change (hi 25/10/0) · target_upside (hi 20/10/0) · rec_mean (lo 1.8/2.3/3.0) |

- A pillar's value is the mean of its available metrics' points, on a 0–4 scale.
- **Score** = the mean of the available pillars × 5, so 0–20.
- The score is **low confidence**, shown with `*`, when fewer than 70% of the
  14 metrics are available.
- It is computed only when live fundamentals exist for the company.

**Colour bands**, shared by every /20 score: ≥16 very good (blue), ≥12 good
(green), ≥8 not great (orange), otherwise bad (red).

The fundamentals cells have their own cut-offs, given as [blue, green, orange],
with anything else red:
- ROE hi [25, 15, 8];
- FCF margin hi [20, 10, 0];
- D/E lo [0.3, 1, 2];
- EPS growth hi [25, 10, 0];
- net margin hi [25, 12, 5];
- ROIC hi [20, 12, 6];
- dividend yield hi [4, 2, 0.5];
- beta lo [0.8, 1.1, 1.5];
- P/E lo [15, 25, 40], with no colour when ≤ 0.

Live values are shown in the normal text colour, and static estimates in grey.

## Quality /20: `quality_from_statements(financials, balance_sheet, cashflow)`

This is a Buffett-style durability score, built from up to 4–5 years of annual
statements, newest first. It deliberately excludes momentum and analyst views.

**Inputs.** Each statement row is read by the first label that exists:
- Total Revenue | Operating Revenue
- Gross Profit
- Net Income | Net Income Common Stockholders
- EBIT | Operating Income
- Tax Rate For Calcs
- Interest Expense | Interest Expense Non Operating
- Invested Capital
- Stockholders Equity | Common Stock Equity
- Total Debt
- Net Debt
- Ordinary Shares Number | Share Issued
- Free Cash Flow

NaN is read as missing.

**Ratios** (`quality_metrics`). `WACC = 9%` and the default tax rate is 0.21.
A tax rate outside [0, 1) is replaced by the default.

| ratio | definition |
|---|---|
| roic (per year i) | EBIT_i × (1 − tax_i) / InvestedCapital_i × 100. `roic` is the latest year, and `roic_min` the minimum over the years. |
| roic_spread | roic − 9 |
| roe | NetIncome_0 / Equity_0 × 100 |
| gross_margin (per year) | GrossProfit / Revenue × 100. `gross_margin` is the latest year. |
| gm_trend | gm_latest − gm_oldest (pp), needing ≥ 2 years |
| gm_cv | population std(gm) / \|mean(gm)\|, needing ≥ 3 years |
| rev_worst | the minimum year-over-year revenue change, (Rev_i / Rev_{i+1} − 1) × 100 |
| fcf_ratio | the number of years with FCF > 0, divided by the number of years with FCF data |
| de | Debt_0 / Equity_0 |
| int_cov | EBIT_0 / \|InterestExpense_0\| |
| net_cash | NetDebt_0 < 0 |
| share_chg | ((Shares_0 / Shares_oldest)^(1/(n−1)) − 1) × 100, where positive means dilution |
| years | the number of revenue years |

**Band function** `band(v, [c4, c3, c2, c1], higher_is_better)` gives 4 points
at or beyond c4, then 3, 2, 1, and 0 when short of c1. Missing data gives no
points.

| Pillar (mean of its available bands, 0–4) | Bands |
|---|---|
| Returns on capital | roic [20,15,10,7] · roe [20,15,10,7] · roic_spread [10,6,3,0] |
| Consistency | gm_cv lower-better [0.05,0.10,0.20,0.35] · fcf_ratio [1,0.75,0.5,0.25] · roic_min [15,10,5,0] · rev_worst [5,0,−10,−25] |
| Moat | gross_margin [50,35,25,15] · gm_trend [2,0,−2,−5] |
| Balance sheet | de lower-better [0.3,0.6,1.0,2.0] · int_cov [15,8,4,2] · net cash → 4, net debt → 2 |
| Capital allocation | share_chg lower-better [−2,0,1,3] · roic [20,15,10,7] |

- **q_score** = the mean of the available pillars × 5.
- `detail.low_confidence` is true when fewer than 5 pillars are available, or
  there are fewer than 4 years of data.
- The stored document is `{key, yahoo_ticker, q_score, p_returns,
  p_consistency, p_moat, p_balance, p_capital, detail: {…ratios,
  pillars_available, low_confidence}, years, updated_at}`.

**Which companies are scored.** `refresh_quality` scores every key in the
universe that is non-derived, or that already has a fundamentals row (meaning
its symbol was verified).

### Worked example (it is also a test)

| | Y0 | Y1 | Y2 | Y3 |
|---|---|---|---|---|
| revenue | 1200 | 1100 | 1000 | 900 |
| gross profit | 600 | 540 | 480 | 430 |
| net income | 200 | 180 | 160 | 140 |
| EBIT | 300 | 270 | 240 | 210 |
| tax rate | 0.2 | 0.2 | 0.2 | 0.2 |
| invested capital | 1000 | 950 | 900 | 850 |
| equity | 800 | 760 | 720 | 680 |
| debt | 200 | … | | |
| net debt | −50 | … | | |
| shares | 98 | 99 | 100 | 101 |
| FCF | 180 | 160 | 140 | −5 |

Interest expense is −10 every year.

**Ratios:**
- roic = 24, roic_min = 19.76, spread = 15
- roe = 25, gross margin = 50
- rev_worst = +9.09% (1200/1100)
- fcf_ratio = 3/4
- de = 0.25, int_cov = 30, net cash = yes
- share_chg = −1.0%/yr

**Pillars and score:**
- Returns = 4
- Consistency = (4 + 3 + 4 + 4) / 4 = 3.75
- Moat = 4
- Balance = 4
- Capital = (3 + 4) / 2 = 3.5
- **q_score = 19.25**, with high confidence.

## Acceptance checks

1. `band(25,[20,15,10,7]) = 4`, `band(15,…) = 3`, `band(3,…) = 0`, and
   `band(None,…)` is None.
2. The quality worked example gives 19.25.
3. `name_agrees("asml holding", "ASML Holding N.V.")` is true.
   `name_agrees("wti crude oil", "Colgate-Palmolive Company")` is false.
4. `fundamentals_from_info({"debtToEquity": 30.2})["de"] == 0.302`.
5. A refresh with a deadline already in the past fetches nothing, and reports
   every key as `skipped`.
