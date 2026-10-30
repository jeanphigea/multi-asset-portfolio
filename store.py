"""
Key/value storage for every piece of state the app keeps.

The data is a handful of JSON documents (positions, ETF holdings, FX, scores,
price history), so a key/value store fits it better than tables. Two backends
share one interface:

  * RedisStore - Upstash Redis over its REST API. Used when
    UPSTASH_REDIS_REST_URL / _TOKEN (or Vercel's KV_REST_API_URL / _TOKEN) are
    set, which is how the Vercel demo runs: serverless functions have no
    persistent disk.
  * FileStore  - a single SQLite table in .data/store.db. The default for
    local use; needs no service.

Every key is prefixed with STORE_PREFIX (default "map:") so several datasets,
e.g. the demo and a preview deployment, can share one Redis database.

Writes replace a whole document. Refreshes build their result in memory and
write it once at the end, so readers never see a half-written document and no
long write transaction can block a page load.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path

import requests

DEFAULT_PATH = Path(__file__).with_name(".data") / "store.db"


class Store:
    """Interface. Values are anything json.dumps accepts."""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix

    def get(self, key: str, default=None):
        return self.get_many([key]).get(key, default)

    def get_many(self, keys: list[str]) -> dict:
        raise NotImplementedError

    def set(self, key: str, value) -> None:
        self.set_many({key: value})

    def set_many(self, items: dict) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def keys(self, prefix: str = "") -> list[str]:
        """Keys starting with `prefix`, without the store's own prefix."""
        raise NotImplementedError

    def dump(self) -> dict:
        """Every document, e.g. for a backup."""
        return self.get_many(self.keys())


class FileStore(Store):
    def __init__(self, path: str | Path = DEFAULT_PATH, prefix: str = ""):
        super().__init__(prefix)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as db:
            db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30)
        # iCloud and network folders reject sqlite's on-disk rollback journal
        # ("disk I/O error"); an in-memory journal sidesteps that. Not persisted
        # in the file, so it is set on every connection.
        conn.execute("PRAGMA journal_mode=MEMORY")
        return conn

    def get_many(self, keys):
        if not keys:
            return {}
        full = [self.prefix + k for k in keys]
        with self._conn() as db:
            rows = db.execute(f"SELECT key, value FROM kv WHERE key IN ({','.join('?' * len(full))})",
                              full).fetchall()
        n = len(self.prefix)
        return {k[n:]: json.loads(v) for k, v in rows}

    def set_many(self, items):
        with self._lock, self._conn() as db:
            db.executemany("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
                           [(self.prefix + k, json.dumps(v, separators=(",", ":"))) for k, v in items.items()])

    def delete(self, key):
        with self._lock, self._conn() as db:
            db.execute("DELETE FROM kv WHERE key = ?", (self.prefix + key,))

    def keys(self, prefix=""):
        p = self.prefix + prefix
        with self._conn() as db:
            rows = db.execute("SELECT key FROM kv WHERE substr(key, 1, ?) = ? ORDER BY key",
                              (len(p), p)).fetchall()
        return [r[0][len(self.prefix):] for r in rows]


class RedisStore(Store):
    """Upstash Redis through its REST API: one HTTPS POST per command batch,
    which suits serverless functions better than a pooled TCP connection."""

    def __init__(self, url: str, token: str, prefix: str = "", session=None):
        super().__init__(prefix)
        self.url = url.rstrip("/")
        self.http = session or requests.Session()
        self.http.headers["Authorization"] = f"Bearer {token}"

    def _pipeline(self, commands: list[list]) -> list:
        r = self.http.post(f"{self.url}/pipeline", json=commands, timeout=30)
        r.raise_for_status()
        out = []
        for item in r.json():
            if "error" in item:
                raise RuntimeError(f"Redis: {item['error']}")
            out.append(item.get("result"))
        return out

    def get_many(self, keys):
        if not keys:
            return {}
        (vals,) = self._pipeline([["MGET", *[self.prefix + k for k in keys]]])
        return {k: json.loads(v) for k, v in zip(keys, vals) if v is not None}

    def set_many(self, items):
        if items:
            self._pipeline([["SET", self.prefix + k, json.dumps(v, separators=(",", ":"))]
                            for k, v in items.items()])

    def delete(self, key):
        self._pipeline([["DEL", self.prefix + key]])

    def keys(self, prefix=""):
        out, cursor = [], "0"
        while True:
            ((cursor, batch),) = self._pipeline([["SCAN", cursor, "MATCH", self.prefix + prefix + "*",
                                                  "COUNT", "500"]])
            out += [k[len(self.prefix):] for k in batch]
            if str(cursor) == "0":
                return sorted(set(out))


_store: Store | None = None


def get_store() -> Store:
    """The process-wide store, chosen from the environment on first use."""
    global _store
    if _store is None:
        prefix = os.environ.get("STORE_PREFIX", "map:")
        url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL")
        token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN")
        if url and token:
            _store = RedisStore(url, token, prefix)
        else:
            _store = FileStore(os.environ.get("STORE_PATH", DEFAULT_PATH), prefix)
    return _store
