"""Both backends honour the same contract (spec/01-store.md)."""
import json
import os

import pytest

from store import FileStore, RedisStore


class FakeUpstash:
    """Just enough of the Upstash REST pipeline endpoint to run RedisStore."""

    def __init__(self):
        self.data, self.headers = {}, {}

    def post(self, url, json=None, timeout=None):
        assert url.endswith("/pipeline") and self.headers["Authorization"] == "Bearer tok"
        return _Resp([{"result": self._run(*cmd)} for cmd in json])

    def _run(self, op, *args):
        if op == "MGET":
            return [self.data.get(k) for k in args]
        if op == "SET":
            self.data[args[0]] = args[1]
            return "OK"
        if op == "DEL":
            return int(self.data.pop(args[0], None) is not None)
        if op == "SCAN":
            prefix = args[2].rstrip("*")
            return ["0", [k for k in self.data if k.startswith(prefix)]]
        raise AssertionError(op)


class _Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def backends(tmp_path):
    yield FileStore(tmp_path / "s.db", prefix="p:")
    yield RedisStore("https://example.upstash.io", "tok", prefix="p:", session=FakeUpstash())
    if os.environ.get("UPSTASH_REDIS_REST_URL"):          # the real thing, when configured
        yield RedisStore(os.environ["UPSTASH_REDIS_REST_URL"], os.environ["UPSTASH_REDIS_REST_TOKEN"],
                         prefix=f"pytest-{os.getpid()}:")


@pytest.mark.parametrize("i", range(3))
def test_contract(tmp_path, i):
    stores = list(backends(tmp_path))
    if i >= len(stores):
        pytest.skip("UPSTASH_REDIS_REST_URL not set")
    s = stores[i]
    assert s.get("missing", "dflt") == "dflt"
    s.set("etfs", [{"ticker": "VUSA", "shares": 1.5}])
    s.set_many({"holdings:VUSA": {"rows": []}, "holdings:EMIM": {"rows": [1]}, "fx": {"USD": 0.75}})
    assert s.get("etfs") == [{"ticker": "VUSA", "shares": 1.5}]
    assert s.get_many(["fx", "nope"]) == {"fx": {"USD": 0.75}}
    assert s.keys("holdings:") == ["holdings:EMIM", "holdings:VUSA"]
    s.delete("holdings:EMIM")
    assert s.keys("holdings:") == ["holdings:VUSA"]
    assert set(s.dump()) == {"etfs", "holdings:VUSA", "fx"}
    for k in s.keys():
        s.delete(k)


def test_prefix_isolates_datasets(tmp_path):
    a = FileStore(tmp_path / "s.db", prefix="demo:")
    b = FileStore(tmp_path / "s.db", prefix="preview:")
    a.set("etfs", [1])
    assert b.get("etfs") is None and b.keys() == []


def test_redis_stores_compact_json():
    fake = FakeUpstash()
    RedisStore("https://x", "tok", prefix="p:", session=fake).set("fx", {"USD": 0.75})
    assert fake.data == {"p:fx": json.dumps({"USD": 0.75}, separators=(",", ":"))}
