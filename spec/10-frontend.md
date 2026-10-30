# 10 · Front end (`templates/index.html`, `static/app.css`, `static/app.js`)

## Purpose

The front end is one static page, written in plain JS with no build step. It
loads the JSON documents and does all per-company aggregation itself (see 04,
05 and 07), so tab switches and toggles need no round trip.

## Loading

1. `index.html` loads, in order:
   - Chart.js 4.5.0 from jsDelivr, pinned with SRI;
   - Inter from Google Fonts;
   - `/static/app.css?v=…`;
   - `/reference.js?v=…`, which defines `window.REF`;
   - `/static/app.js?v=…`.
2. `app.js` reads its constants from `REF` (see 09).
3. **`load()`** fetches `/api/summary`, `/api/fundamentals`, `/api/quality`,
   `/api/ai-maturity` and `/api/compute-asset` in parallel, then calls `render()`.
   - If loading fails, it retries twice with back-off.
   - On final failure it shows a **stale-data banner**. It never shows old
     numbers as if they were fresh.

## Shell

- **Top bar** shows the brand ("Multi-Asset Portfolio"), with a subtitle of
  `N ETFs · M direct positions · updated HH:MM`. Its actions are:
  - **ETFs**: a modal for ticker and shares;
  - **Direct holdings**: a modal for stocks, FX rates and the IBKR sync button;
  - **Refresh market data**: runs `prices`, reloads, then runs `fundamentals`
    and `quality`, showing per-stage progress on the button;
  - **Theme toggle**.
- **KPI strip:**

  | KPI | Content |
  |---|---|
  | Total portfolio | The total, plus how long ago prices were marked, flagged when that is more than 24 h |
  | ETFs | £ value and % |
  | Direct stocks | £ value and % |
  | Look-through | The "seen" value as % of the total, and the number of holdings identified |
  | Largest exposure | The biggest company row that is not a commodity or cash |

- **Tabs**: Portfolio (1), Company exposure (2), Sectors (3), Countries (4) and
  Risk (5).
  - The number keys switch tabs. `/` focuses the exposure search, and `Esc`
    closes a modal.
  - The active tab is kept in the URL hash and in localStorage.
- **Toasts** (`setStatus`) hide themselves after a few seconds. Messages
  starting with ⏳, ❌ or ⚠ stay until replaced. A thin progress bar runs while
  data is busy.
- **Demo mode**: `<body class="demo">` hides every `.edit-only` control (the
  three top-bar actions and Refresh history) and shows the read-only banner,
  with a "Run your own copy" link when `REPO_URL` is set. Cards hide their
  Edit link and the manual holdings box.

## Tabs

**Portfolio**
- One card per ETF, plus a Direct card. Each card shows:
  - the value and its % of the portfolio;
  - shares × price;
  - the data source and as-of date.
- Each card has two views:
  - **Holdings**: the top 3 rows, expandable to all;
  - **Chart**: a bar chart of the holdings.
- A card with no holdings offers manual entry, one `Name, Weight%` per line,
  posted to `/api/holdings/<ETF>`.
- **Holdings across funds**: every position, merged by `normalizeName` (share
  classes are kept separate here). It shows a column of weight and value per
  fund, with rows held in two or more places in bold.

**Company exposure**
- One row per company (see 04). Two columns stay pinned while the table scrolls
  sideways, and columns can be resized.
- Every header has a tooltip definition from `COL_DEFS`, the single source for
  column names and their explanations.
- The score columns are Momentum /20, Quality /20 (see 05), AI Maturity /20 and
  Compute /20 (see 12). Each has a detailed tooltip. The fundamentals columns are ROE, FCF margin, D/E, EPS growth, net
  margin, ROIC, dividend yield, beta and P/E, coloured as described in 05.
- A footer shows when fundamentals were last refreshed.

**Sectors**
- Two doughnuts: the portfolio and the benchmark.
- A difference table covering every sector in either set, with a bar for each
  difference.
- A note explaining that commodities and cash are compared with 0%.

**Countries**
- KPIs: the largest country, the United Kingdom, emerging markets, and the
  value outside equities.
- A horizontal bar chart of the largest countries against the benchmark.
- A region doughnut and table.
- A table of all countries, where clicking a row expands the companies behind it.
- A toggle, **Scale each ETF to 100%**, stored in localStorage.

**Risk**
- Controls: the shared benchmark selector, a look-back of 1Y, 3Y (default), 5Y
  or 10Y, and Refresh history.
- KPIs: max drawdown (with the benchmark's and its date), volatility, beta,
  1-week VaR 95% (in % and £), and Sharpe.
- Charts:
  - **Growth of £100** for the portfolio against the benchmark;
  - **Drawdown**.
- **Stress scenarios**: switch between Plausible today and Historical replays.
  - A horizontal bar chart compares the portfolio with the benchmark.
  - A clickable list sits beside it.
  - The detail pane shows the impact in % and £, the difference from the
    benchmark, the biggest hits and cushions, the P&L by sector, and the
    scenario's parameters as chips.
  - In the forward mode, a severity slider runs from 50% to 150%.
- A risk metrics table (portfolio, benchmark and difference), and a "Where the
  risk comes from" list of risk contributions.
- Results are cached per (benchmark, years) for the session. The cache is
  cleared on reload.

**The benchmark selector** (`.bench-select`) appears on Sectors, Countries and
Risk. One choice, `setBenchmark(k)`, is shared by all three, stored in
localStorage, and redraws the active tab.

## Design system

- **CSS tokens** live on `:root` (`--bg --surface --text --sub --muted --line
  --accent --accent-soft --pos --neg --warn --s0..--s3 --radius --shadow`).
  - They are redefined for dark mode under `prefers-color-scheme: dark`, unless
    `data-theme="light"` is set.
  - They are defined again under `[data-theme="dark"]`.
  - The theme is applied before first paint, from localStorage.
- **Score fills** `--s0..--s3` (very good, good, not great, bad) are shared by
  every score and fundamentals cell.
- **Charts** read their colours from the CSS variables. Changing theme redraws
  them.
- Icons are an inline SVG sprite (`<symbol id="i-…">`).
- The layout works at phone width: the KPIs wrap, and the tables scroll
  sideways.

## Acceptance checks

1. All five tabs render with no console errors, both on the demo seed and on an
   empty fundamentals document.
2. Switching the benchmark on Sectors changes the Countries and Risk selection
   too.
3. In demo mode, no edit or refresh control is visible, and the banner shows.
4. When the reload fails after a save, the toast says "saved, but the page
   could not reload".
