# 08 · IBKR sync (`ibkr.py`), optional

## Purpose

This module mirrors **direct stock holdings** from Interactive Brokers through
the Flex Web Service. It needs a read-only token and a saved "Positions" Flex
Query, and no gateway or daily login. IBKR is treated as the source of truth for
stocks, so a sync **adds, updates and removes** them.

ETF positions are reported but never written, because the ETF list carries the
look-through holdings. The sync is disabled in demo mode. Setup steps are in
`docs/ibkr-setup.md`.

## Configuration

The first source found wins:
1. the environment variables `IBKR_FLEX_TOKEN`, `IBKR_FLEX_QUERY_ID` and
   `IBKR_BASE_CURRENCY` (default GBP);
2. the file `.ibkr.json` next to the module (git-ignored), containing
   `{"token", "queryId", "baseCurrency"}`.

If neither is set, the sync is disabled. If the file cannot be parsed, an
`IbkrError` is raised, and the status endpoint reports it.

## Flex protocol

1. `SendRequest(token, queryId)` returns a reference code.
2. `GetStatement(token, refCode)` returns the statement XML. If IBKR answers
   "statement generation in progress", retry with back-off.
3. Parse each `OpenPosition` into:
   - `symbol`, `description`, `isin`, `quantity`, `markPrice`, `currency`,
     `costBasis` and `value`;
   - per-account totals.
4. Build FX to the base currency from the statement's conversion rates.
5. The snapshot is `{accounts:[{accountId, alias, reportDate, totalGBP,
   positions:[…]}], fxRates, fetchedAt, baseCurrency}`. It is cached in
   `.ibkr_cache.json`.
6. Within `MIN_REFETCH_SECONDS` of the last fetch, the cache is served unless
   `force` is set. If IBKR is unreachable, the cache is returned flagged as
   `stale`.

## Plan: `plan(snapshot, stocks, etf_tickers, etf_isins)`

1. **Split** the positions. A position is an ETF when its symbol is in
   `etf_tickers`, or its ISIN is in `etf_isins`. `etf_tickers` is every
   `ISIN_MAP` key plus every held ETF's ticker. ETFs are reported only.
2. **Translate tickers** for stocks:
   - `TICKER_ALIASES` maps AZNL→AZN and BAL→BA., plus any private additions
     (`IBKR_TICKER_ALIASES`, see the private overlay in 03).
   - For GBP lines, a trailing lower-case "l" is dropped, but only when the
     shortened ticker is already stored.
3. **Match** against stored stocks by ISIN first, then by ticker. ISIN survives
   renames and venue changes. A match keeps the stored ticker spelling and its
   `yahoo` field.
4. **Build each stock**:
   - `name = canonical_company_name(description, isin)`, falling back to the
     stored name, then to the symbol;
   - `last_price = markPrice` and `currency = upper(currency)`;
   - `cost_basis_local = costBasis`, falling back to the stored value.
5. **Diff**: `toAdd` (not stored), `toUpdate` (stored) and `toDelete` (stored
   but absent from IBKR).
6. **Safety check**: when the statement has **no positions at all**,
   `safe = false` and a warning is added. Applying such a plan would delete
   every stock.

## Apply: `apply(store, plan, backup_dir, keep=10)`

1. Write `backups/store-YYYYmmdd-HHMMSS.json` containing `store.dump()`. Keep
   the newest 10 backups.
2. Replace `stocks` with the plan's stocks, each stamped with `updated_at`.
3. Merge the statement's FX rates into `fx`. Rates IBKR did not quote are kept,
   for example the hand-set GBp rate.

## API (see 09)

- `GET /api/ibkr/status` returns the configuration state plus the last cached
  statement's accounts. It never calls IBKR.
- `POST /api/ibkr/sync` with `{dry_run: 1}` returns the plan. Without `dry_run`,
  it backs up, applies, and returns `{…plan, applied: true, backup}`.
  - It returns 409 if the plan is unsafe.
  - It returns 400 if IBKR is not configured.
  - It returns 502 on an IBKR error.

The UI always runs a dry run first, shows the Add, Update and REMOVE lists, and
asks for confirmation before applying.

## Acceptance checks

1. A position whose ISIN matches a stored stock with a different ticker updates
   that stock. It does not delete it and add a new one.
2. "AZNl" in GBP maps to `AZN`.
3. An empty statement produces `safe = false` and HTTP 409, and changes nothing.
4. `apply` writes a backup file before it changes the store.
