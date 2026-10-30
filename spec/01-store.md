# 01 · Store (`store.py`)

## Purpose

`store.py` persists every piece of state as JSON documents under string keys. One
interface has two backends:
- a local file, for personal use without any service;
- Upstash Redis, for serverless hosting, where there is no persistent disk.

## Interface

```python
class Store:
    prefix: str
    get(key, default=None)          # one document, or default
    get_many(keys) -> dict          # {key: value} for the keys that exist
    set(key, value)                 # replace one document
    set_many({key: value})          # replace several in one round trip
    delete(key)
    keys(prefix="") -> list[str]    # sorted, WITHOUT the store prefix
    dump() -> dict                  # every document (used for backups)

get_store() -> Store                # process-wide singleton chosen from the environment
```

Values are anything `json.dumps` accepts. They are stored compactly, with
separators `(",", ":")`.

**Writes replace whole documents.** Nothing patches part of a document
server-side. A refresh builds its result in memory and writes it once at the end,
so a reader never sees a half-written document.

## Backends

**FileStore(path, prefix)**
- Uses one SQLite table: `kv(key TEXT PRIMARY KEY, value TEXT NOT NULL)`.
- Every connection sets `PRAGMA journal_mode=MEMORY`. iCloud and network
  folders reject SQLite's on-disk rollback journal with a "disk I/O error".
- `keys(prefix)` matches by `substr(key,1,len) = prefix`, never by `LIKE`,
  because `_` is a `LIKE` wildcard.
- A thread lock serialises writes. The connection timeout is 30 s.

**RedisStore(url, token, prefix, session=None)**
- Uses the Upstash REST API: `POST {url}/pipeline` with header
  `Authorization: Bearer {token}`. The body is a JSON list of commands, and the
  response is a list of `{"result": …}` or `{"error": …}`. Any error raises.
- `get_many` is one `MGET`, `set_many` is one pipeline of `SET`s, and `delete`
  is `DEL`.
- `keys` loops over `SCAN cursor MATCH prefix* COUNT 500` until the cursor is
  `"0"`.
- `session` can be injected, so tests can supply a fake.

**get_store()**
- Uses `RedisStore` when both a URL and a token are set, from either
  `UPSTASH_REDIS_REST_*` or `KV_REST_API_*`.
- Otherwise it uses `FileStore(STORE_PATH or .data/store.db)`.
- The prefix is `STORE_PREFIX`, default `map:`.

## Key schema

| Key | Value |
|---|---|
| `etfs` | `[{ticker, shares, last_price_gbp, last_price_date, yahoo?, added_at, updated_at}]` |
| `stocks` | `[{ticker, name, quantity, last_price, currency, cost_basis_local, isin?, yahoo?, updated_at}]` |
| `holdings:<ETF>` | `{as_of, source: "db"\|"manual"\|"live", rows: [{name, ticker, weight}]}`. `weight` is % of the fund. |
| `fx` | `{currency: rate_to_gbp}` |
| `fundamentals` | `{company_key: {key, yahoo_ticker, roe, …, sector, industry, country, updated_at}}` (see 05) |
| `quality` | `{company_key: {key, yahoo_ticker, q_score, p_returns, p_consistency, p_moat, p_balance, p_capital, detail, years, updated_at}}` |
| `ai_maturity`, `compute_asset` | Hand-researched scores (see 12) |
| `yahoo_resolution` | `{company_key: {yahoo_ticker, ok, resolved_at}}`, recording symbols verified (or rejected) for ETF constituents |
| `history:<SYMBOL>` | `{currency, fetched, dates: ["YYYY-MM-DD", …], close: [float, …]}` |
| `meta` | `{prices_at, history_at, fundamentals_at, quality_at}` |

The ETF ticker in `holdings:<ETF>` is upper-case.

## Edge cases

- Keys that are missing are simply absent from `get_many`. They are never `None`.
- The same database can hold several datasets, separated by prefix (for
  example `demo:` and `preview:`).
- 10 years of daily closes for one symbol is about 50 KB of JSON. That is far
  below Upstash's request limit, so history is stored one document per symbol.

## Acceptance checks

1. Each backend passes this contract test:
   - `get("missing","d") == "d"`;
   - `set` then `get` round-trips;
   - `get_many(["fx","nope"]) == {"fx": …}`;
   - `keys("holdings:")` is sorted and has no prefix;
   - `delete` removes the key;
   - `dump()` returns every key.
2. Two FileStores on the same file with prefixes `demo:` and `preview:` do not
   see each other's keys.
3. `RedisStore.set("fx", {"USD": 0.75})` sends `SET p:fx {"USD":0.75}`.
