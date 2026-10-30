# 12 · Research scores: AI maturity and Compute as asset (`scores.py`, cells in `static/app.js`)

## Purpose

These are two /20 scores in the Company exposure table that **cannot be
computed from market data**. Each comes from reading a company's filings and
disclosures, so the scores are written through the API (by hand, or by an
agent doing the research) and stored. They are not refreshed automatically.
Every score carries its source and an as-of month.

| store key | value |
|---|---|
| `ai_maturity` | `{company_key: {score5, dims: [8] or null, provenance: "published"\|"estimated", source, as_of}}` |
| `compute_asset` | `{company_key: {cap, pwr, pipe, price, mult, source, as_of}}` |

The browser re-keys both through `companyKey`, like every other per-company
lookup (see 02).

## AI maturity

This uses the framework by Paul-Antoine Tual, *"Top 10 CAC 40 et Nasdaq : la
taille ne dit pas la maturité IA"* (20 July 2026,
<https://paulantoinetual.fr/blog/cac-40-vs-nasdaq-top-10>). It scores eight
dimensions from 1 to 5:

| # | Dimension | Weight |
|---|---|---|
| D1 | Strategy & value creation | 15% |
| D2 | Governance & accountability | 15% |
| D3 | Data | 12% |
| D4 | Technology & industrialisation | 12% |
| D5 | Talent, culture & organisation | 12% |
| D6 | Deployment & realised value | 12% |
| D7 | Risk, compliance & controls | 12% |
| D8 | Financial & stakeholder communication | 10% |

- `score5 = round(Σ dim_i × w_i, 2)`, and `score20 = score5 × 4`.
- **Levels** on the /5 scale:
  - more than 4.2: Transformational;
  - 3.5 or more: Integrated;
  - 2.6 or more: Structured;
  - 1.8 or more: Exploratory;
  - otherwise: Emerging.
- **Provenance**:
  - `published` is the framework author's own score, which may have no
    dimension breakdown;
  - `estimated` is our reading of the same framework from public sources. It is
    flagged with ‡ in the UI, because it is not comparable in rigour to a
    published score.
- **Caveat** from the source: the framework measures *documented* maturity, not
  audited capability. The internal dimensions (D3–D5) are under-documented, so
  they are biased downward.

**Worked example** (also a test). With dims `[4, 4, 3.5, 3.5, 4.5, 3.5, 3, 3]`:
- `score5 = 0.6 + 0.6 + 0.42 + 0.42 + 0.54 + 0.42 + 0.36 + 0.30 = 3.66`;
- that is **14.64 / 20**, at level Integrated.

## Compute as asset

This measures how much **sellable** compute capacity a company owns. It is an
exposure axis, deliberately separate from quality.

| Pillar | Max | Meaning |
|---|---|---|
| `cap`, owned capacity | 40 | Critical IT power owned or long-leased, plus the installed accelerator fleet. Bands: ≥5 GW = 40 · 2–5 GW = 32 · 0.5–2 GW = 22 · 100–500 MW = 12 · <100 MW = 5 · none = 0. |
| `pwr`, secured power | 25 | Contracted generation, PPAs and grid interconnects. |
| `pipe`, funded pipeline | 20 | Announced capacity compared with current capacity, and whether it is financed. |
| `price`, pricing power | 15 | Utilisation, contract length, and the ability to raise $/GPU-hour. |
| `mult`, monetisation multiplier | 0–1 | 1.00 pure merchant · 0.85 major merchant plus internal use · 0.50 mostly captive · 0.25 captive only · 0 owns no compute. |

- `score20 = (cap + pwr + pipe + price) × mult / 5`.
- The multiplier is a **gate**, not a component. A vast captive fleet that sells
  nothing scores 0. Chip suppliers score 0, because they own no capacity they
  can charge rent on.

**Worked example** (also a test). Alphabet with 36 + 22 + 18 + 12 = 88 and
`mult` 0.85 gives `88 × 0.85 / 5` = **14.96 / 20**.

## API (see 09)

- `GET /api/ai-maturity` and `GET /api/compute-asset` return the stored
  documents.
- `POST /api/ai-maturity` takes `{key, dims: [8 × 1–5]}` for an own assessment,
  or `{key, score5}` for a published one, plus optional `provenance`, `source`
  and `as_of` (default: this month). It returns the row with `score20` and
  `level`. Bad input returns 400.
- `POST /api/compute-asset` takes `{key, cap, pwr, pipe, price, mult, source?,
  as_of?}`. Each pillar is range-checked. It returns the row with `score20`.
- Both POST routes are blocked in demo mode (403).

## UI

- These are the third and fourth score columns, after Momentum and Quality. They
  use the same colour bands: ≥16, ≥12, ≥8, below.
- The AI maturity cell shows `score20`, plus ‡ for an estimate. Its tooltip lists
  each dimension's score and weight, the level, the provenance, the basis and the
  as-of month.
- The compute cell's tooltip shows each pillar out of its maximum, the
  multiplier, and the score out of 100 and out of 20.
- An empty cell explains why it is empty: not yet assessed, or owns no sellable
  compute.

## Acceptance checks

1. The two worked examples hold.
2. `dims` with 7 values, or with a value of 6, is rejected. A missing key is
   rejected.
3. The demo seed includes scores for the demo companies, and the columns render.
