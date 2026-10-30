"""Scoring definitions (spec/05-market-data.md)."""
import pytest

import market


def test_band():
    cuts = [20, 15, 10, 7]
    assert [market.band(v, cuts) for v in (25, 15, 12, 7, 3, None)] == [4, 3, 2, 1, 0, None]
    assert market.band(0.25, [0.3, 0.6, 1.0, 2.0], higher_is_better=False) == 4
    assert market.band(2.5, [0.3, 0.6, 1.0, 2.0], higher_is_better=False) == 0


def test_quality_worked_example():
    """Four years of a steady, cash-generative, debt-light business (newest first)."""
    d = market.quality_metrics(
        rev=[1200, 1100, 1000, 900], gp=[600, 540, 480, 430], ni=[200, 180, 160, 140],
        ebit=[300, 270, 240, 210], taxr=[0.2, 0.2, 0.2, 0.2], intex=[-10, -10, -10, -10],
        invcap=[1000, 950, 900, 850], equity=[800, 760, 720, 680], debt=[200, 190, 180, 170],
        netdebt=[-50, -40, -30, -20], shares=[98, 99, 100, 101], fcf=[180, 160, 140, -5])
    assert d["roic"] == pytest.approx(24.0)                 # 300 x 0.8 / 1000
    assert d["roic_min"] == pytest.approx(19.7647, abs=1e-3)  # 210 x 0.8 / 850
    assert d["roe"] == pytest.approx(25.0)
    assert d["gross_margin"] == pytest.approx(50.0)
    assert d["gm_trend"] == pytest.approx(50 - 430 / 900 * 100)
    assert d["rev_worst"] == pytest.approx((1200 / 1100 - 1) * 100)   # smallest of +9.1%, +10%, +11.1%
    assert (d["fcf_years"], d["fcf_total"]) == (3, 4)
    assert d["de"] == pytest.approx(0.25) and d["int_cov"] == pytest.approx(30) and d["net_cash"] is True
    assert d["share_chg"] == pytest.approx(((98 / 101) ** (1 / 3) - 1) * 100)

    q = market.quality_score(d)
    assert q["p_returns"] == 4                     # ROIC 24, ROE 25, spread 15
    assert q["p_consistency"] == pytest.approx((4 + 3 + 4 + 4) / 4)   # gm_cv, FCF 3/4 years, ROIC min, rev worst
    assert q["p_moat"] == pytest.approx((4 + 4) / 2)
    assert q["p_balance"] == 4
    assert q["p_capital"] == 3.5                   # buybacks of 1%/yr score 3 (4 needs 2%), ROIC >= 20 scores 4
    assert q["q_score"] == pytest.approx((4 + 3.75 + 4 + 4 + 3.5) / 5 * 5)   # 19.25 / 20
    assert q["detail"]["low_confidence"] is False


def test_quality_flags_short_history():
    d = market.quality_metrics([100, 90], [50, 45], [10, 9], [15, 14], [], [], [100, 100], [80, 80],
                               [], [], [], [])
    assert market.quality_score(d)["detail"]["low_confidence"] is True


def test_name_agrees():
    assert market.name_agrees("asml holding", "ASML Holding N.V.")
    assert market.name_agrees("the southern", "The Southern Company")
    assert not market.name_agrees("wti crude oil", "Colgate-Palmolive Company")


def test_fundamentals_units():
    f = market.fundamentals_from_info({"returnOnEquity": 0.25, "debtToEquity": 30.2, "freeCashflow": 20,
                                       "totalRevenue": 100, "targetMeanPrice": 110, "currentPrice": 100})
    assert f["roe"] == 25 and f["de"] == pytest.approx(0.302) and f["fcf_margin"] == 20
    assert f["target_upside"] == pytest.approx(10)
