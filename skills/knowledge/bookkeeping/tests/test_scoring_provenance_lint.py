"""Tests for the Nous-gate scoring-provenance lint (BRO-2524).

`references/entity-schema.md` marks `scoring` Required and nothing enforced it.
Measured 2026-09-13 on the live corpus: 972 of 1226 entity pages carry no
scoring block, so requiring one outright would red-flag 79% of the graph.

The severity split is chosen against that baseline. An ABSENT block on a page
claiming `status: entity` is a warning (364 pages, legacy drift). A block that
CONTRADICTS ITSELF is an error (6 pages, all real defects) — because a
fabricated or careless score still has to add up. Provenance ("is this citation
real?") is undecidable at lint time; arithmetic is not.

Both directions are covered deliberately: a suite that only feeds the rule bad
input cannot fail for a rule that flags everything.
"""

import pytest
from bookkeeping import _lint_scoring_provenance, NOUS_GATE_THRESHOLD


# Provenance defaults so the arithmetic/threshold tests below isolate what they
# name. Without them every such fixture also trips the provenance warning, and a
# test asserting `errs == []` would be asserting two rules at once.
PROVENANCE_DEFAULTS = {
    "pass": "heuristic", "promoted_by": "test", "promoted_at": "2026-01-01",
    "blog_candidate": False, "priority": "low",
}


def fm(status="entity", **scoring):
    out = {"status": status}
    if scoring:
        out["scoring"] = {**PROVENANCE_DEFAULTS, **scoring}
    return out


def fields(errs):
    return [(e.field, e.severity) for e in errs]


# ── arithmetic: the unfakeable check ──────────────────────────────────────────

MISMATCHED = [
    # (novelty, specificity, relevance, raw_score) — every one from the live corpus
    (3, 2, 3, 7),   # bstack-generalizes-by-declaring-its-ontology
    (3, 3, 3, 8),   # colombia-regimen-tributario-comparison
    (2, 3, 3, 7),   # open-core-splits-discipline-from-runtime
    (2, 3, 3, 9),   # fast-slow-hierarchical-control — INFLATED, not merely stale
]


@pytest.mark.parametrize("n,s,r,raw", MISMATCHED)
def test_mismatched_raw_score_is_an_error(n, s, r, raw):
    errs = _lint_scoring_provenance(
        "x.md", fm(novelty=n, specificity=s, relevance=r, raw_score=raw, **{"pass": "heuristic"})
    )
    assert ("scoring", "error") in fields(errs)
    assert "does not add up" in errs[0].message
    # the message must carry BOTH numbers, or it cannot be acted on
    assert str(raw) in errs[0].message and str(n + s + r) in errs[0].message


@pytest.mark.parametrize("n,s,r", [(3, 2, 3), (1, 2, 2), (3, 3, 3), (0, 0, 0), (2, 2, 1)])
def test_consistent_raw_score_is_silent(n, s, r):
    """Negative control across the range, including a sub-threshold sum."""
    errs = _lint_scoring_provenance(
        "x.md", fm(status="candidate", novelty=n, specificity=s, relevance=r, raw_score=n + s + r)
    )
    assert errs == [], f"{n}+{s}+{r} should be silent, got {[e.message for e in errs]}"


# ── the promotion floor ───────────────────────────────────────────────────────

def test_entity_below_threshold_is_an_error():
    """A page promoted to Layer 3 while failing the gate it claims to have passed."""
    errs = _lint_scoring_provenance("x.md", fm(status="entity", novelty=1, specificity=1, relevance=2, raw_score=4))
    assert ("scoring", "error") in fields(errs)
    assert "below the Nous gate" in errs[0].message


def test_candidate_below_threshold_is_allowed():
    """`candidate` is the pre-promotion tier — a low score there is the normal case,
    and flagging it would make the rule fire on exactly the pages it should not."""
    assert _lint_scoring_provenance("x.md", fm(status="candidate", novelty=1, specificity=1, relevance=2, raw_score=4)) == []


def test_threshold_boundary_is_inclusive():
    """>= threshold passes. A suite on one side of a boundary cannot fail for the boundary."""
    at = fm(status="entity", novelty=2, specificity=2, relevance=1, raw_score=NOUS_GATE_THRESHOLD)
    below = fm(status="entity", novelty=2, specificity=1, relevance=1, raw_score=NOUS_GATE_THRESHOLD - 1)
    assert _lint_scoring_provenance("x.md", at) == []
    assert len(_lint_scoring_provenance("x.md", below)) == 1


# ── absence: warning, never error ─────────────────────────────────────────────

def test_entity_without_scoring_warns_not_errors():
    errs = _lint_scoring_provenance("x.md", {"status": "entity"})
    assert fields(errs) == [("scoring", "warning")]


@pytest.mark.parametrize("status", ["candidate", "raw", "synthesis", "archived", "merged", ""])
def test_absent_scoring_silent_for_non_entity(status):
    """Only a page CLAIMING promotion owes a score."""
    assert _lint_scoring_provenance("x.md", {"status": status}) == []


# ── malformed blocks ──────────────────────────────────────────────────────────

def test_missing_subfield_is_an_error_naming_the_field():
    errs = _lint_scoring_provenance("x.md", fm(novelty=3, relevance=3, raw_score=9))
    assert ("scoring", "error") in fields(errs)
    assert "specificity" in errs[0].message


def test_non_integer_scores_do_not_crash():
    errs = _lint_scoring_provenance("x.md", fm(novelty="three", specificity=3, relevance=3, raw_score=9))
    assert ("scoring", "error") in fields(errs)


@pytest.mark.parametrize("bad", [4, -1, 7])
def test_dimension_outside_range_is_an_error(bad):
    errs = _lint_scoring_provenance("x.md", fm(status="candidate", novelty=bad, specificity=1, relevance=1, raw_score=bad + 2))
    assert any("outside the 0-3 range" in e.message for e in errs)


def test_scoring_not_a_dict_is_treated_as_absent():
    """A scalar `scoring:` is malformed, but it must not crash the linter."""
    assert _lint_scoring_provenance("x.md", {"status": "candidate", "scoring": 7}) == []


# ── review round 1: CodeRabbit #221 ───────────────────────────────────────────
# Thread 2 (accepted in full): int() coerces "3", 3.0 and True, so a malformed
# block passed every numeric check below it. Zero live pages carry a non-int
# score, so strict typing costs nothing and closes the hole.
# Thread 1 (accepted in part): the schema marks pass/promoted_by/promoted_at/
# blog_candidate/priority Required, and 229 of 254 scored pages omit four of
# them. They are reported as warnings; erroring would red-flag 90% of the corpus,
# which is the same measured reason `scoring` itself is not required outright.

from bookkeeping import SCORING_PROVENANCE_FIELDS


def scored(**over):
    base = dict(novelty=2, specificity=2, relevance=1, raw_score=5)
    base.update({"pass": "heuristic", "promoted_by": "x", "promoted_at": "2026-01-01",
                 "blog_candidate": False, "priority": "low"})
    base.update(over)
    return {"status": "entity", "scoring": base}


@pytest.mark.parametrize("value", ["3", 3.0, True, False, None.__class__])
def test_coercible_non_integers_are_rejected(value):
    """int() would have accepted "3", 3.0 and True. Each must be an error."""
    errs = _lint_scoring_provenance("x.md", scored(novelty=value))
    assert any(e.severity == "error" and "must be integers" in e.message for e in errs), \
        f"{value!r} slipped through: {[e.message for e in errs]}"


def test_bool_is_not_accepted_as_int():
    """bool subclasses int, so an isinstance(v, int) check alone passes True."""
    errs = _lint_scoring_provenance("x.md", scored(relevance=True))
    assert any("must be integers" in e.message for e in errs)
    assert any("relevance=True" in e.message for e in errs)


def test_genuine_ints_still_pass():
    """Negative control — the strict check must not reject valid blocks."""
    assert _lint_scoring_provenance("x.md", scored()) == []


@pytest.mark.parametrize("field", SCORING_PROVENANCE_FIELDS)
def test_each_missing_provenance_field_is_reported(field):
    errs = _lint_scoring_provenance("x.md", scored(**{field: None}))
    warns = [e for e in errs if e.severity == "warning"]
    assert len(warns) == 1, f"{field} not reported"
    assert field in warns[0].message


@pytest.mark.parametrize("field", SCORING_PROVENANCE_FIELDS)
def test_missing_provenance_field_is_never_an_error(field):
    """The 90%-blast-radius decision, asserted rather than left to prose."""
    errs = _lint_scoring_provenance("x.md", scored(**{field: None}))
    assert [e for e in errs if e.severity == "error"] == []


def test_blog_candidate_false_is_present_not_absent():
    """A falsey-but-set value must not read as missing."""
    errs = _lint_scoring_provenance("x.md", scored(blog_candidate=False))
    assert errs == []


def test_arithmetic_error_still_fires_with_provenance_complete():
    """The error path must not be shadowed by the new warning path."""
    errs = _lint_scoring_provenance("x.md", scored(novelty=3, specificity=2, relevance=3, raw_score=7))
    assert any(e.severity == "error" and "does not add up" in e.message for e in errs)
