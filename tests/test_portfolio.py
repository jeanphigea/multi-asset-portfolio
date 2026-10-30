"""Valuation and the look-through inputs (spec/04-portfolio-exposure.md)."""
import pytest

import portfolio as pf


def test_seed_loads_demo(demo_store):
    p = pf.load(demo_store)
    assert len(p["etfs"]) == 7 and len(p["stocks"]) == 14
    assert not pf.is_empty(demo_store)


def test_stock_value_converts_currency():
    fx = {"USD": 0.75, "GBp": 0.01}
    assert pf.stock_value_gbp({"quantity": 10, "last_price": 200, "currency": "USD"}, fx) == 1500
    # Pence: 1,000 shares at 250p = £2,500
    assert pf.stock_value_gbp({"quantity": 1000, "last_price": 250, "currency": "GBp"}, fx) == 2500


def test_summary_worked_example(store):
    """One ETF and two stocks: the numbers in the spec's worked example."""
    store.set_many({
        "etfs": [{"ticker": "AAA", "shares": 100, "last_price_gbp": 50.0}],
        "holdings:AAA": {"as_of": "2026-09-30", "source": "manual",
                         "rows": [{"name": "Apple Inc", "ticker": "AAPL", "weight": 10},
                                  {"name": "Microsoft Corp", "ticker": "MSFT", "weight": 5}]},
        "stocks": [{"ticker": "AAPL", "name": "Apple", "quantity": 10, "last_price": 200, "currency": "USD"},
                   {"ticker": "AZN", "name": "AstraZeneca", "quantity": 5, "last_price": 100, "currency": "GBP"}],
        "fx": {"USD": 0.75},
    })
    etf, direct = pf.summary(store)
    assert etf["total_covered_pct"] == 15
    # Look-through value of Apple in AAA = 10% x 100 shares x £50 = £500
    apple = next(h for h in etf["holdings"] if h["holding_ticker"] == "AAPL")
    assert apple["weight_pct"] / 100 * etf["shares"] * etf["last_price_gbp"] == 500
    # DIRECT is a basket worth £1,500 + £500 = £2,000 at a price of 1
    assert direct["shares"] == 2000 and direct["last_price_gbp"] == 1.0
    assert [h["weight_pct"] for h in direct["holdings"]] == [75.0, 25.0]


def test_direct_weights_sum_to_100(demo_store):
    direct = pf.summary(demo_store)[-1]
    assert direct["is_direct"]
    assert sum(h["weight_pct"] for h in direct["holdings"]) == pytest.approx(100, abs=1e-3)


def test_set_etfs_keeps_prices(demo_store):
    before = {e["ticker"]: e for e in demo_store.get("etfs")}
    pf.set_etfs(demo_store, [{"ticker": "vusa", "shares": 1}, {"ticker": "NEW1", "shares": 2}])
    after = {e["ticker"]: e for e in demo_store.get("etfs")}
    assert set(after) == {"VUSA", "NEW1"}
    assert after["VUSA"]["last_price_gbp"] == before["VUSA"]["last_price_gbp"]
    assert pf.etf_symbol(after["NEW1"]) == "NEW1.L"          # unmapped: assume London
    assert pf.etf_symbol(after["VUSA"]) == "VUSA.L"


def test_positions_mark_cash(demo_store):
    kinds = {p["id"]: p["kind"] for p in pf.positions(demo_store)}
    assert kinds["CSH2"] == "cash" and kinds["NVDA"] == "stock" and kinds["VUSA"] == "etf"
