"""Research scores (spec/12-research-scores.md)."""
import pytest

import scores


def test_ai_worked_example(store):
    # Eight dimension scores, weighted 15/15/12/12/12/12/12/10
    r = scores.set_ai_maturity(store, {"key": "Example Co", "dims": [4, 4, 3.5, 3.5, 4.5, 3.5, 3, 3]})
    assert r["score5"] == pytest.approx(0.6 + 0.6 + 0.42 + 0.42 + 0.54 + 0.42 + 0.36 + 0.30)   # 3.66
    assert r["score20"] == pytest.approx(14.64) and r["level"] == "Integrated"
    assert r["provenance"] == "estimated"
    assert store.get("ai_maturity")["example co"]["dims"][0] == 4


def test_ai_published_score_without_dims(store):
    r = scores.set_ai_maturity(store, {"key": "alphabet", "score5": 3.91, "source": "Tual 2026"})
    assert r["provenance"] == "published" and r["dims"] is None


@pytest.mark.parametrize("bad", [{"key": "x"}, {"key": "x", "dims": [3] * 7}, {"key": "x", "dims": [6] * 8},
                                 {"dims": [3] * 8}])
def test_ai_rejects_bad_input(store, bad):
    with pytest.raises(ValueError):
        scores.set_ai_maturity(store, bad)


def test_levels():
    assert [scores.ai_level(x) for x in (4.3, 3.5, 2.6, 1.8, 1.7)] == \
        ["Transformational", "Integrated", "Structured", "Exploratory", "Emerging"]


def test_compute_worked_example(store):
    # Alphabet: 36 + 22 + 18 + 12 = 88 / 100, x 0.85 = 74.8 / 100 -> 14.96 / 20
    r = scores.set_compute(store, {"key": "alphabet", "cap": 36, "pwr": 22, "pipe": 18, "price": 12, "mult": 0.85})
    assert r["score20"] == pytest.approx(14.96)


def test_compute_multiplier_gates(store):
    # A vast captive fleet that sells nothing scores nothing.
    assert scores.set_compute(store, {"key": "x", "cap": 40, "pwr": 25, "pipe": 20, "price": 15,
                                      "mult": 0})["score20"] == 0
    with pytest.raises(ValueError):
        scores.set_compute(store, {"key": "x", "cap": 41, "pwr": 0, "pipe": 0, "price": 0, "mult": 1})
