# 06 · Risk metrics (`risk.py`)

## Purpose

This module answers: *how would today's portfolio have behaved?* It replays
today's positions through up to ten years of real prices, in GBP, and compares
the result with a benchmark ETF.

It is a **current-holdings backtest** with **constant weights, rebalanced
daily**. It measures the risk of the mix, not the investor's timing or trades.

## Price history

- `history:<SYMBOL>` holds `{currency, fetched, dates, close}`. Closes are
  auto-adjusted for dividends and splits, cover 10 years, and are keyed by the
  exchange-local date, without time zones.
- `history(store, symbols, force=False, fetch=True)` re-downloads a symbol when
  `force` is set, when it is missing, or when it is older than **18 hours**.
  Downloads run in parallel, with 8 workers. With `fetch=False` (demo mode) it
  only reads what is stored.
- **GBP conversion** (`gbp_prices`):
  - A `GBp` or `GBX` series is divided by 100. A `GBP` series is used as is.
  - Any other currency is multiplied by its FX pair's close, forward-filled
    onto the asset's dates.
  - If the FX pair is missing, the symbol is unusable.

## Portfolio returns: `portfolio_returns(positions, hist, fx_pairs, rf)`

Each position is `{id, symbol, value, kind}`, where `value` is in GBP (see 04).

1. Skip positions whose value is 0 or less.
2. **Cash** positions (`kind = "cash"`) earn the daily risk-free return,
   `(1 + rf/100)^(1/252) − 1`, every day.
3. Any other position without a usable GBP series is reported as **missing**.
4. **Index**: the union of all price dates, restricted to weekdays. Prices are
   forward-filled for at most 5 days. Daily returns are `pct_change`, with no
   back-fill before a holding's first price.
5. **Weights**: `w_i = value_i / Σ value`, held constant over the whole period.
6. **On each day**, average only the positions that have a return:
   `r_p = Σ_{i available} w_i r_i / Σ_{i available} w_i`.
   **Coverage** for that day is `Σ_{available} w_i / Σ w_i`.
   This renormalises around holdings that have no history yet, such as a recent
   IPO.
7. The output is `(r_p, coverage, returns by position, weights, missing ids)`.
   Days with no available position at all are dropped.

The benchmark's returns are the same single-series calculation applied to the
benchmark ticker. The portfolio and benchmark series are inner-joined on dates.

**Window**: `end` is the last common date. `start = max(end − years, first
date)`, where `years` is one of {1, 3, 5, 10}. The window is the days strictly
after `start`.

## Metrics: `metrics(r, rf)`

Here NAV = `cumprod(1 + r)`. Weekly returns use Friday closes of NAV, and
monthly returns use month-end closes. Let `T` be the calendar years from the
first to the last date.

| metric | definition |
|---|---|
| total_return | (NAV_end − 1) × 100 |
| cagr | (NAV_end^(1/T) − 1) × 100 |
| volatility | std(weekly) × √52 × 100 |
| sharpe | (cagr − rf) / volatility, using fractions |
| sortino | (cagr − rf) / downside, where downside = √mean(min(wk − rf_w, 0)²) × √52 and rf_w = (1 + rf)^(1/52) − 1 |
| var95_week | −(5th percentile of weekly returns) × 100, a positive loss |
| cvar95_week | −mean(weekly returns ≤ that percentile) × 100 |
| worst_week, worst_month, best_month | the minimum or maximum weekly or monthly return, in % |
| positive_months | the share of months with a return > 0, in % |
| max_drawdown | min(NAV / running max NAV − 1) × 100 |
| peak, trough | the date of the running max before the trough, and the date of the trough |
| recovery | the first date after the trough when NAV is back at or above the peak value; null if not yet |
| days_to_trough, days_to_recover | calendar days |
| current_drawdown | drawdown on the last day |

## Relative metrics: `relative(rp, rb)`

These use the weekly returns of both series, inner-joined:

| metric | definition |
|---|---|
| beta | cov(p, b) / var(b) |
| correlation | corr(p, b) |
| tracking_error | std(p − b) × √52 × 100 |
| up_capture | mean(p in months where b > 0) / mean(b in those months) × 100, using monthly returns |
| down_capture | the same, for months where b < 0 |

## Risk contributions: `risk_contributions(rets, w, rb)`

Each position's share of portfolio variance:

1. Build each position's NAV from its daily returns. Before the position's
   first return the NAV is undefined, not 1.
2. Take weekly returns and the annualised covariance matrix `Σ`, with at least
   26 weeks required. Keep only positions whose covariance row is complete.
3. Renormalise the weights over the kept positions: `w`.
4. `RC_i = w_i (Σw)_i / (wᵀΣw) × 100`. These **sum to 100%**, and a position
   can carry more risk than its weight.
5. Also report each position's own annualised volatility `√Σ_ii × 100`, and its
   beta to the benchmark when more than 26 overlapping weeks exist.
6. Sort by risk share, largest first.

## Historical episodes: `episode(r, coverage, start, end)`

For each entry in `HISTORICAL_EPISODES`:
- NAV starts at 1 on the last date at or before `start`;
- the path then compounds `r` over the days in `(start, end]`;
- report `return = (NAV_end − 1) × 100`, `max_drawdown` within the episode,
  `coverage` at the first day in %, and the `path` as `[date, NAV × 100]`.

The portfolio uses its coverage series, and the benchmark uses coverage 1. An
episode is listed only when both have data.

## Report: `report(...)`

`/api/risk` returns the following, with `benchmark` added by the route:

```
{ok, rf, history_as_of (latest fetched), window {start, end, years},
 coverage_start (% priced on the first day),
 portfolio: metrics, benchmark_metrics: metrics, relative,
 series {dates, portfolio NAV, benchmark NAV} (5 dp),
 contributions [{id, name, weight, risk_share, volatility, beta}],
 episodes [{key, name, start, end, portfolio, benchmark}],
 missing [ids], errors [..]}
```

When the benchmark or every position has no history, the report is
`{ok: false, error: "No price history stored yet — refresh market data first."}`.

## Acceptance checks

1. A constant daily return `g` over 520 weekdays:
   - `cagr = ((1+g)^520)^(1/T) − 1`;
   - `max_drawdown = 0`;
   - volatility is approximately 0 (not exactly, because the first week is
     partial).
2. Returns [+10%, −50%, +100%, 0] give `max_drawdown = −50`, with the peak on
   day 0, the trough on day 1 and recovery on day 2.
3. `relative(r, r)` gives beta 1, correlation 1 and tracking error 0.
   `relative(2r, r)` gives beta ≈ 2.
4. Risk contributions sum to 100. Of two equally weighted assets, the more
   volatile one carries more risk.
5. Weights 75/25 on returns of +10% and 0% give a portfolio return of 7.5% a day.
