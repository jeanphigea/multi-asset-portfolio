"""Risk metric definitions on synthetic series (spec/06-risk-metrics.md)."""
import math

import numpy as np
import pandas as pd
import pytest

import risk

DAYS = pd.bdate_range("2020-01-01", periods=520)


def test_constant_growth():
    r = pd.Series(0.0004, index=DAYS)            # no volatility at all
    m = risk.metrics(r, rf=0)
    years = (DAYS[-1] - DAYS[0]).days / 365.25
    assert m["cagr"] == pytest.approx(((1.0004 ** 520) ** (1 / years) - 1) * 100)
    # Weekly returns are not all equal (the first week is partial), so volatility
    # is tiny rather than zero.
    assert m["max_drawdown"] == 0 and m["volatility"] < 0.5


def test_drawdown_and_recovery():
    # +10%, -50%, then +100% back to the old high
    r = pd.Series([0.1, -0.5, 1.0, 0.0], index=DAYS[:4])
    dd = risk.drawdown_stats(risk._nav(r))
    assert dd["max_drawdown"] == pytest.approx(-50)
    assert dd["peak"] == DAYS[0].date().isoformat() and dd["trough"] == DAYS[1].date().isoformat()
    assert dd["recovery"] == DAYS[2].date().isoformat() and dd["current_drawdown"] == 0


def test_relative_against_itself_and_double():
    rng = np.random.default_rng(1)
    rb = pd.Series(rng.normal(0.0003, 0.01, len(DAYS)), index=DAYS)
    rel = risk.relative(rb, rb)
    assert rel["beta"] == pytest.approx(1) and rel["correlation"] == pytest.approx(1)
    assert rel["tracking_error"] == pytest.approx(0, abs=1e-9)
    assert risk.relative(2 * rb, rb)["beta"] == pytest.approx(2, rel=0.05)


def test_risk_contributions_sum_to_100():
    rng = np.random.default_rng(2)
    rets = pd.DataFrame({"A": rng.normal(0, 0.02, len(DAYS)), "B": rng.normal(0, 0.01, len(DAYS))}, index=DAYS)
    out = risk.risk_contributions(rets, pd.Series({"A": 0.5, "B": 0.5}), rets.mean(axis=1))
    assert sum(c["risk_share"] for c in out) == pytest.approx(100)
    assert out[0]["id"] == "A"                     # the more volatile half carries more risk


def test_portfolio_returns_weights_and_cash():
    hist = {s: {"currency": "GBP", "fetched": "", "close": pd.Series(px, index=DAYS[:3])}
            for s, px in {"X": [100, 110, 121], "Y": [100, 100, 100]}.items()}
    pos = [{"id": "x", "symbol": "X", "value": 75, "kind": "etf"},
           {"id": "y", "symbol": "Y", "value": 25, "kind": "stock"},
           {"id": "c", "symbol": None, "value": 0, "kind": "cash"}]
    port, cov, _, w, missing = risk.portfolio_returns(pos, hist, {}, rf=0)
    assert list(port.round(6)) == [0.075, 0.075]   # 75% x 10% + 25% x 0%
    assert missing == [] and math.isclose(w.sum(), 1)
