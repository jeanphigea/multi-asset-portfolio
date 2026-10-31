"""HTTP surface and demo-mode rules (spec/09-api.md)."""
import importlib

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    def make(**env):
        monkeypatch.setenv("STORE_PATH", str(tmp_path / "s.db"))
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        import store
        store._store = None
        import app
        return importlib.reload(app).app.test_client()
    return make


def test_first_request_seeds_demo(client):
    c = client()
    s = c.get("/api/summary").get_json()
    assert [e["ticker"] for e in s][-1] == "DIRECT" and len(s) == 8


def test_reference_script(client):
    body = client().get("/reference.js").get_data(as_text=True)
    assert body.startswith("window.REF = {") and '"BENCHMARKS"' in body


def test_demo_is_read_only(client):
    c = client(DEMO_MODE="1", CRON_SECRET="s")
    assert c.post("/api/portfolio", json=[]).status_code == 403
    assert c.post("/api/refresh?part=prices").status_code == 403
    assert b'class="demo"' in c.get("/").data
    assert c.get("/api/ibkr/status").get_json()["configured"] is False


def test_cron_needs_secret(client):
    c = client(DEMO_MODE="1", CRON_SECRET="s")
    assert c.get("/api/cron/refresh").status_code == 401
    assert c.get("/api/cron/refresh", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_edits_when_not_demo(client):
    c = client(DEMO_MODE="")
    assert c.post("/api/portfolio", json=[{"ticker": "VUSA", "shares": 3}]).status_code == 200
    assert [e["ticker"] for e in c.get("/api/summary").get_json()] == ["VUSA", "DIRECT"]


def test_risk_without_history_explains(client):
    r = client(DEMO_MODE="1").get("/api/risk?years=3").get_json()
    assert r["ok"] is False and "price history" in r["error"]


def test_research_scores_round_trip(client):
    c = client(DEMO_MODE="")
    assert "alphabet" in c.get("/api/ai-maturity").get_json()          # seeded with the demo
    r = c.post("/api/ai-maturity", json={"key": "New Co", "dims": [3] * 8})
    assert r.status_code == 200 and r.get_json()["score5"] == 3
    assert c.post("/api/ai-maturity", json={"key": "x"}).status_code == 400
    assert c.post("/api/compute-asset", json={"key": "y", "cap": 1, "pwr": 1, "pipe": 1, "price": 1,
                                              "mult": 1}).get_json()["score20"] == 0.8


def test_demo_blocks_score_writes(client):
    assert client(DEMO_MODE="1").post("/api/ai-maturity", json={"key": "x", "score5": 3}).status_code == 403


def test_rewritten_path_is_restored(client):
    entry = client()                              # the Flask app itself, as Vercel may load it
    assert entry.get("/api/index?__path=").status_code == 200                      # the page
    r = entry.get("/api/index?__path=api/summary")
    assert r.status_code == 200 and r.get_json()[-1]["ticker"] == "DIRECT"
    r = entry.get("/api/index?years=7&__path=api/risk")                           # other params survive
    assert r.status_code == 400 and "lookback" in r.get_json()["error"]
    assert entry.get("/api/index?__path=static/app.css").status_code == 200
