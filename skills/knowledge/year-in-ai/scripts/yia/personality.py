"""A four-axis collaboration personality, in the shape of Spotify's own.

Spotify's most-shared artefact was never a number — it was a *label* you could
claim.  This is the same move applied to a working style, with one deliberate
difference: Spotify can say "you are in the top 0.5% of listeners" because it
holds the whole population.  A local corpus holds exactly one person, so no
percentile here would mean anything.  The axes are therefore scored against
**fixed, published thresholds**, and the report says so rather than inventing
a rank.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Tools that change the world vs. tools that survey it.
BUILD_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit", "apply_patch", "patch", "str_replace"}
EXPLORE_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "WebFetch", "LS", "ls", "find", "view"}
DELEGATE_TOOLS = {"Agent", "Task", "spawn_agent", "wait_agent", "send_message", "followup_task"}

#: Phrases that mark a turn as corrective rather than additive.
CORRECTION_MARKERS = (
    "that's wrong", "thats wrong", "you didn't", "you did not", "not what i asked",
    "incorrect", "revert", "undo", "still broken", "still failing", "try again",
    "no, ", "nope", "actually,", "that's not", "thats not", "wrong ", "you missed",
    "doesn't work", "does not work", "re-run", "rerun", "fix it", "you forgot",
)

#: Fixed decision thresholds. Published so a reader can disagree with them.
THRESHOLDS = {
    "build_ratio": 0.35,
    "median_session_minutes": 20.0,
    "delegations_per_session": 0.5,
    "correction_rate": 0.12,
}

AXES = (
    ("B", "Builder", "E", "Explorer", "build_ratio"),
    ("M", "Marathon", "S", "Sprint", "median_session_minutes"),
    ("D", "Delegating", "F", "Flying solo", "delegations_per_session"),
    ("P", "Probing", "T", "Trusting", "correction_rate"),
)

TYPE_NAMES = {
    "BMDP": "The Foreman", "BMDT": "The General Contractor",
    "BMFP": "The Perfectionist", "BMFT": "The Craftsman",
    "BSDP": "The Dispatcher", "BSDT": "The Delegator",
    "BSFP": "The Sniper", "BSFT": "The Hotfixer",
    "EMDP": "The Investigator", "EMDT": "The Expedition Lead",
    "EMFP": "The Auditor", "EMFT": "The Cartographer",
    "ESDP": "The Scout Master", "ESDT": "The Dispatcher-at-large",
    "ESFP": "The Interrogator", "ESFT": "The Browser",
}


@dataclass(slots=True)
class Personality:
    code: str
    name: str
    axes: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "axes": self.axes,
            "thresholds": dict(THRESHOLDS),
            "basis": (
                "Axes are scored against fixed thresholds, not percentiles: a local "
                "corpus contains one person, so there is no population to rank against."
            ),
        }


def _axis(measured: float | None, threshold: float, hi: tuple[str, str], lo: tuple[str, str],
          label: str) -> dict[str, Any]:
    if measured is None:
        return {"axis": label, "measured": None, "threshold": threshold,
                "letter": None, "pole": None, "known": False}
    letter, pole = hi if measured >= threshold else lo
    return {"axis": label, "measured": round(measured, 4), "threshold": threshold,
            "letter": letter, "pole": pole, "known": True}


def classify(signals: dict[str, float | None]) -> Personality | None:
    """Score the four axes. Returns ``None`` when any axis is unmeasurable.

    A partial code would read as a claim about a dimension that was never
    observed, so an incomplete result is withheld entirely.
    """
    axes = [
        _axis(signals.get(key), THRESHOLDS[key], (hi_l, hi_n), (lo_l, lo_n), key)
        for hi_l, hi_n, lo_l, lo_n, key in AXES
    ]
    if any(not a["known"] for a in axes):
        return None
    code = "".join(str(a["letter"]) for a in axes)
    return Personality(code=code, name=TYPE_NAMES.get(code, "The Unclassified"), axes=axes)


def is_correction(text: str | None) -> bool:
    """Does this prompt push back on the previous turn?"""
    if not text:
        return False
    lowered = text.lower().lstrip()
    return any(marker in lowered for marker in CORRECTION_MARKERS)
