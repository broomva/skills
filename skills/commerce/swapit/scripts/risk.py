"""Swapit exposure-risk engine.

The job of this module is *prioritization*, not alarm. A scratched non-stick pan used
daily at high heat should rank far above an unopened plastic bin in the garage — even
though both "contain plastic". The score multiplies the things that actually drive
exposure:

    hazard_risk = severity x presence x evidence x exposure_relevance x frequency x condition

* **severity**            (0-3)   how harmful the hazard is at realistic exposures
* **presence**            (0-1)   how reliably this item-class carries the hazard
* **evidence**            (0-1)   established / emerging / contested down-weight
* **exposure_relevance**  (0-1)   does the way the item is *used* activate the hazard's route?
* **frequency**           (0-1)   how often it is used
* **condition**           (mult)  damaged / scratched coatings leach more

Item score = scaled sum of per-hazard risk, bucketed into low / medium / high. The
ranked list this produces is the "swap-first" intelligence — the analogue of procurer's
"dominant failure mode": fix the 5% that drives 80% of the exposure first.
"""
from __future__ import annotations

# --- tunable constants ------------------------------------------------------------
FREQ_WEIGHT = {
    "daily": 1.0,
    "weekly": 0.7,
    "monthly": 0.45,
    "occasional": 0.3,
    "rare": 0.15,
    "unused": 0.05,
}
CONDITION_MULT = {
    "damaged": 1.4,
    "scratched": 1.4,
    "worn": 1.25,
    "aging": 1.15,
    "good": 1.0,
    "new": 0.95,
    "sealed": 0.7,
}
EVIDENCE_WEIGHT = {"established": 1.0, "emerging": 0.7, "contested": 0.5}

SCALE = 11  # maps raw sum (~0-12) onto a ~0-100 display score
BAND_HIGH = 55
BAND_MEDIUM = 18

# categories where a route is naturally "active"
_DERMAL_CATEGORIES = {"personal-care", "bathroom", "textiles", "baby-kids"}
_AIRBORNE_CATEGORIES = {"cleaning", "furniture", "bedroom", "flooring", "textiles", "misc"}
_FOOD_CATEGORIES = {"kitchen", "food-packaging"}


def exposure_relevance(routes: list[str] | None, usage: dict | None, category: str) -> float:
    """How strongly the item's *use* activates a hazard's exposure routes (0-1)."""
    route_set = set(routes or [])
    usage = usage or {}
    score = 0.15  # baseline — some relevance even when use is unknown

    if {"ingestion", "food-contact-heat"} & route_set:
        if usage.get("food_contact"):
            score = max(score, 0.6)
            if usage.get("heat") and "food-contact-heat" in route_set:
                score = max(score, 1.0)
        elif category in _FOOD_CATEGORIES:
            score = max(score, 0.5)

    if "dermal" in route_set:
        score = max(score, 0.8 if category in _DERMAL_CATEGORIES else 0.3)

    if {"inhalation", "dust"} & route_set:
        score = max(score, 0.7 if category in _AIRBORNE_CATEGORIES else 0.3)

    if usage.get("child_contact"):
        score = min(1.0, score * 1.25 + 0.1)

    return round(min(score, 1.0), 3)


def hazard_risk(hazard: dict, usage: dict | None, condition: str | None, category: str) -> float:
    severity = float(hazard.get("severity", 1) or 0)
    presence = float(hazard.get("presence_likelihood", 0.5) or 0)
    evidence = EVIDENCE_WEIGHT.get(hazard.get("evidence_strength", "established"), 1.0)
    exposure = exposure_relevance(hazard.get("exposure_routes"), usage, category)
    freq = FREQ_WEIGHT.get((usage or {}).get("frequency", "occasional"), 0.3)
    cond = CONDITION_MULT.get((condition or "good"), 1.0)
    return severity * presence * evidence * exposure * freq * cond


def score_item(item: dict, hazards: list[dict], category: str) -> dict:
    """Compute the full risk breakdown for one item against its resolved hazards.

    ``hazards`` are item-class hazard records already annotated with
    ``presence_likelihood`` + ``rationale`` (see ``knowledge.hazards_for_class``).
    """
    usage = item.get("usage")
    condition = item.get("condition")
    contribs = []
    for hz in hazards:
        r = hazard_risk(hz, usage, condition, category)
        contribs.append(
            {
                "hazard_id": hz.get("id"),
                "name": hz.get("name"),
                "severity": hz.get("severity"),
                "presence_likelihood": hz.get("presence_likelihood"),
                "evidence_strength": hz.get("evidence_strength"),
                "rationale": hz.get("rationale", ""),
                "risk": round(r, 3),
            }
        )
    contribs.sort(key=lambda c: c["risk"], reverse=True)
    raw = sum(c["risk"] for c in contribs)
    score = min(100, round(raw * SCALE))
    band = "high" if score >= BAND_HIGH else "medium" if score >= BAND_MEDIUM else "low"
    return {"raw": round(raw, 3), "score": score, "band": band, "contributions": contribs}


def reduction_for_alternative(risk_result: dict, alternative: dict) -> dict:
    """Estimate the fraction of an item's exposure removed by adopting an alternative."""
    avoided = set(alternative.get("avoids_hazards", []))
    removed = sum(
        c["risk"] for c in risk_result.get("contributions", []) if c["hazard_id"] in avoided
    )
    raw = risk_result.get("raw", 0) or 1e-9
    return {
        "alternative_id": alternative.get("id"),
        "name": alternative.get("name"),
        "removed_raw": round(removed, 3),
        "pct": min(100, round(100 * removed / raw)),
    }


def band_emoji(band: str) -> str:
    return {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(band, "⚪")
