"""
Hand-researched company scores, shown beside the market-derived ones in the
Company exposure table:

  AI maturity       how well a company governs and deploys AI internally:
                    eight dimensions scored 1-5, weighted to a /5 total
  Compute as asset  how much sellable compute capacity a company owns:
                    four pillars (/100) times a monetisation multiplier

Neither can be computed from market data; each comes from reading filings and
disclosures. Scores are written through the API (POST) and kept in the store
under `ai_maturity` and `compute_asset`. Definitions in spec/12-research-scores.md.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Paul-Antoine Tual, "Top 10 CAC 40 et Nasdaq : la taille ne dit pas la
# maturité IA" (20 Jul 2026), https://paulantoinetual.fr/blog/cac-40-vs-nasdaq-top-10
AI_DIMENSIONS = (
    ("D1 Strategy & value creation", 0.15),
    ("D2 Governance & accountability", 0.15),
    ("D3 Data", 0.12),
    ("D4 Technology & industrialisation", 0.12),
    ("D5 Talent, culture & organisation", 0.12),
    ("D6 Deployment & realised value", 0.12),
    ("D7 Risk, compliance & controls", 0.12),
    ("D8 Financial & stakeholder comms", 0.10),
)
COMPUTE_PILLARS = (("cap", 40), ("pwr", 25), ("pipe", 20), ("price", 15))


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def ai_score5(dims: list[float]) -> float:
    """Weighted mean of the eight 1-5 dimension scores."""
    return round(sum(x * w for x, (_, w) in zip(dims, AI_DIMENSIONS)) + 1e-9, 2)


def ai_level(score5: float) -> str:
    return ("Transformational" if score5 > 4.2 else "Integrated" if score5 >= 3.5
            else "Structured" if score5 >= 2.6 else "Exploratory" if score5 >= 1.8 else "Emerging")


def set_ai_maturity(store, d: dict) -> dict:
    """{key, dims: 8 scores 1-5} for an own assessment, or {key, score5} for a
    published one without dimension detail; plus provenance, source, as_of."""
    key = str(d.get("key", "")).strip().lower()
    dims = d.get("dims")
    if not key:
        raise ValueError("key required")
    if dims is not None:
        if len(dims) != 8 or not all(1 <= float(x) <= 5 for x in dims):
            raise ValueError("dims must be eight scores between 1 and 5")
        dims = [float(x) for x in dims]
        score5 = ai_score5(dims)
    elif d.get("score5") is not None and 1 <= float(d["score5"]) <= 5:
        score5 = float(d["score5"])
    else:
        raise ValueError("dims (8 scores) or score5 (1-5) required")
    row = {"score5": score5, "dims": dims, "provenance": d.get("provenance") or ("estimated" if dims else "published"),
           "source": d.get("source", ""), "as_of": d.get("as_of") or _month()}
    store.set("ai_maturity", {**store.get("ai_maturity", {}), key: row})
    return {"key": key, **row, "score20": round(score5 * 4, 2), "level": ai_level(score5)}


def compute_score20(row: dict) -> float:
    """Asset base (0-100) x monetisation multiplier (0-1), on the /20 scale."""
    return sum(row[p] for p, _ in COMPUTE_PILLARS) * row["mult"] / 5


def set_compute(store, d: dict) -> dict:
    key = str(d.get("key", "")).strip().lower()
    if not key:
        raise ValueError("key required")
    try:
        row = {p: float(d[p]) for p, _ in COMPUTE_PILLARS} | {"mult": float(d["mult"])}
    except (KeyError, TypeError, ValueError):
        raise ValueError("cap, pwr, pipe, price and mult required") from None
    for p, cap in COMPUTE_PILLARS:
        if not 0 <= row[p] <= cap:
            raise ValueError(f"{p} must be between 0 and {cap}")
    if not 0 <= row["mult"] <= 1:
        raise ValueError("mult must be between 0 and 1")
    row |= {"source": d.get("source", ""), "as_of": d.get("as_of") or _month()}
    store.set("compute_asset", {**store.get("compute_asset", {}), key: row})
    return {"key": key, **row, "score20": compute_score20(row)}
