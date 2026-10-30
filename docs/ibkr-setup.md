# Interactive Brokers — pulling your stock holdings automatically

The **Direct Stock Holdings** table can be mirrored from IBKR instead of typed
in by hand. It uses the **Flex Web Service**: a read-only, token-based HTTPS
feed. Nothing has to stay running — no TWS, no IB Gateway, no daily 2FA.

Flex statements are **end-of-day**, so a sync during Tuesday's session gives you
Monday's close.

## What the sync does

- **Direct stocks are mirrored to IBKR.** Positions are added and updated, and
  rows for anything you no longer hold at IBKR are **deleted**. IBKR is the
  source of truth for this table.
- **`portfolio` (your ETFs) is never written.** ETF positions found at IBKR are
  listed in the confirmation dialog and otherwise left alone, so the
  look-through holdings data is untouched.
- **FX rates are refreshed** from the statement's own conversion rates, for the
  currencies it quotes. Hand-set rows such as `GBp` are left as they are.
- **Every sync backs up the whole store first** into `backups/store-<timestamp>.json`, keeping the last 10.

Because it deletes, the button always runs a **dry run** first and shows you
exactly what would be added, updated and removed before anything is written.

---

## 1. Create the Flex Query

In [IBKR Account Management](https://www.interactivebrokers.co.uk/sso/Login):

1. **Performance & Reports → Flex Queries → Activity Flex Query → +**
2. Name it e.g. `Dashboard Positions`.
3. Under **Sections**, enable:
   - **Open Positions** — set *Options* to **Summary** (one row per instrument,
     not one per tax lot). Tick at least: `Symbol`, `Description`, `Asset Class`,
     `Currency`, `Quantity`, `Mark Price`, `Position Value`, `Cost Basis`,
     `Unrealized P/L`, `Con ID`, `Security ID`/`ISIN`, `Account ID`,
     `Report Date`.

     `ISIN` matters here: it's how an ETF is recognised even when IBKR's symbol
     differs from the one in the app (e.g. `CSP1` vs `CSPX`).
   - **Conversion Rates** — used to refresh the FX table.
4. **Date / period:** `Last Business Day`.
5. **Format:** `XML`. **Version:** `3`.
6. Save, then note the **Query ID** (6–7 digits).

Holding across several IBKR accounts? Set the query's **Account** to
*"All accounts"* so one sync covers them all.

## 2. Create the token

**Performance & Reports → Flex Queries → Flex Web Service Configuration → Create.**

Copy it immediately — IBKR shows it once. Tokens last a year; an expired one
appears as `IBKR Flex error 1012`. The token is **read-only** for statements:
it cannot trade, move money, or change settings.

## 3. Point the app at it

Either export environment variables before `python app.py`:

```bash
export IBKR_FLEX_TOKEN=123456789012345678901
export IBKR_FLEX_QUERY_ID=1234567
```

…or create `.ibkr.json` in the project folder (git-ignored):

```json
{
  "token": "123456789012345678901",
  "queryId": "1234567",
  "baseCurrency": "GBP"
}
```

Keep that file out of any backup or share — it is a live credential.

## 4. Use it

```bash
python3 ibkr.py          # check the connection from the terminal
python3 app.py           # then open http://localhost:5050
```

Open **Direct Stock Holdings** and press **⬇ Sync from IBKR**. The button only
appears when a token is configured.

---

## Notes

- **Rate limiting.** IBKR rejects rapid repeat requests (error 1018). Statements
  are cached for 5 minutes.
- **Empty statement guard.** If the statement contains no open positions the
  sync refuses to run rather than deleting every stock — that pattern almost
  always means the query's account or date period is wrong.
- **Restoring a backup.** With the server stopped:
  `python -c "import json, store; store.get_store().set_many(json.load(open('backups/store-<timestamp>.json')))"`
