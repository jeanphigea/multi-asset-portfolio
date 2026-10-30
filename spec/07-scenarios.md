# 07 · Stress scenarios (scenario code in `static/app.js`, `SCENARIOS` in `reference.py`)

## Purpose

This module shows how the portfolio, and the chosen benchmark, would react to a
crash that is plausible **today**. It applies one set of hand-written shocks
to every company in the look-through and to the benchmark, using the same
rules for both.

The shocks are **judgement calls** sized to historical analogues. They are not
forecasts. They live in `reference.py` so they can be read, argued with and
edited in one place.

The Risk tab has two modes:
- **Plausible today**: the shocks defined in this spec.
- **Historical replays**: today's holdings run through real episodes. That data
  comes from `/api/risk` (see 06).

## Scenario definition

Each scenario has these fields (see 03):
- `market`: % applied to every equity;
- `sectors`, `countries` and `tags`: % added on top;
- `commodities`: % per commodity type;
- `fx`: % move of a currency against GBP, where negative means the currency
  falls, which hurts a sterling investor holding it.

| key | name | horizon | market | analogue |
|---|---|---|---|---|
| ai_bust | AI capex bust | 3–9 months | −15 | Dot-com bust 2000–02; DeepSeek day, Jan 2025 |
| hard_landing | US hard landing and credit event | 6–12 months | −25 | 2008 (milder); COVID crash 2020 |
| bond_revolt | Bond-market revolt and inflation comeback | 3–6 months | −16 | 2022 rate shock |
| taiwan | Taiwan Strait crisis | 1–6 months | −20 | No close analogue; Russia sanctions 2022 |
| hormuz | Gulf conflict and oil shock | 1–4 months | −12 | Gulf War 1990; energy shock 2022 |
| trade_war | Global tariff war escalation | 2–6 months | −15 | Tariff shock, Feb–Apr 2025 |
| crypto | Crypto collapse | 1–3 months | −4 | Crypto winter 2022 |
| gilt_crisis | UK gilt and sterling crisis | weeks | −2 | Mini-budget, Sep 2022 |

`reference.py` holds the full parameters, together with each scenario's story.

## Themes (tags) of a company: `companyTags(key)`

Let `label` be the company's `COMPANY_ESTIMATES` label and `industry` its Yahoo
industry, both lower-cased. A company gets each tag below when either test
matches:

| tag | test on label | test on industry |
|---|---|---|
| semis | contains "semi" | contains "semiconductor" |
| ai_megacap | the key is in `AI_MEGACAPS` | |
| gold_miners | gold or silver | gold or precious |
| defence | defence or defense | "aerospace & defense" |
| bitcoin | bitcoin | |
| banks | bank | starts with "banks" |
| autos | auto | "auto manufacturers" |

## FX leg: `fxFor(ccy, sc)`

This gives the % move of `ccy` against GBP. The first rule that applies wins:

1. GBP, or no currency, gives 0.
2. `sc.fx[ccy]`, if it is defined.
3. HKD follows USD (the currency is pegged).
4. `sc.fx[group]`, where the group is `CCY_GROUP[ccy]`; "EM" is its own group.
5. Otherwise 0.

## One company: `holdingShock(key, sc, k)`

This gives the GBP return in %, at severity `k`. The severity slider runs from
0.5 to 1.5, with a default of 1.

1. **Cash** (sector Cash & Money Market, or country Cash) → **0**.
2. **Commodities** (sector Commodities):
   - `local = sc.commodities[COMMODITY_SECTORS[key]] ?? 0`;
   - the currency is USD.
3. **Equities**:
   - `local = sc.market + sc.sectors[sector] + sc.countries[country] + Σ sc.tags[t]`
     over the company's tags;
   - the currency is `COUNTRY_CCY[country]`, defaulting to USD.
4. Scale by severity, with a floor: `local = max(−95, local × k)`.
5. Convert to GBP:
   `GBP = ((1 + local/100) × (1 + k × fxFor(ccy)/100) − 1) × 100`.

## The portfolio: `runScenario(sc, k)`

1. Take the company rows in **scaled** mode (see 04), so that whole funds are
   shocked, not just their published top holdings.
2. For each row: `shock = holdingShock(key)` and `pnl = total × shock / 100`.
3. **Portfolio %** = `Σ pnl / Σ total × 100`.
4. **£ impact** = `portfolio % / 100 × grand total`.
5. Also report the P&L summed by sector, the 8 biggest losses and the 5 biggest
   gains.

## The benchmark: `benchShock(bkey, sc, k)`

The benchmark is described only by its weights (see 03). Every one of its
weights is normalised to sum to 1.

1. **Sector adjustment**: `sAdj = Σ_s w_s × sc.sectors[s]`.
2. **Theme adjustment**: `tAdj = Σ_t (tags[t] / 100) × sc.tags[t]`. Tag weights
   are % of the index.
3. For each benchmark country `c` with weight `w_c`:
   - `local_c = max(−95, k × (sc.market + sAdj + tAdj + (c == "Other" ? 0 : sc.countries[c])))`;
   - `GBP_c = (1 + local_c/100) × (1 + k × fxFor(COUNTRY_CCY[c] or "EM")/100) − 1`.
4. **Benchmark %** = `Σ w_c × GBP_c / Σ w_c × 100`.

The benchmark has no commodities or cash, so those parts of the portfolio are
compared against nothing.

### Worked example

Take scenario `market = −15`, `sectors.IT = −10`, `countries.Taiwan = −12`,
`tags.semis = −15`, `fx.EM = −3`, with `CCY_GROUP.TWD = EM`, at severity 1.

For TSMC (Information Technology, Taiwan, semis):
- `local = −15 − 10 − 12 − 15 = −52`;
- `GBP = (0.48 × 0.97 − 1) × 100 = −53.44%`.

A £1,000 look-through exposure therefore loses £534.40. At severity 1.5:
- `local = −78`;
- `GBP = (0.22 × 0.955 − 1) × 100 = −78.99%`.

## Adding a scenario

Append a dict to `SCENARIOS` with every field in the definition above. Use
GICS sector names, `COUNTRY_META` country names, tag names from the themes
table, and commodity types from `COMMODITY_SECTORS`. Bump `SCENARIOS_AS_OF`.
No code change is needed.

## Acceptance checks

1. The TSMC example gives −53.44 at k = 1 and −78.99 at k = 1.5.
2. Cash shocks to 0 in every scenario.
3. With an all-zero scenario, the portfolio and the benchmark both give 0.
4. A benchmark with 100% United States and no tags, under `{market: −10,
   fx: {USD: −5}}`, gives `(0.9 × 0.95 − 1) × 100 = −14.5`.
