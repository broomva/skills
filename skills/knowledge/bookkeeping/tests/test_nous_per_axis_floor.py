"""The Nous gate: one admission door, and why the per-axis floor is OFF.

Two separate things are pinned here.

STRUCTURAL (the fix that landed). Promotion used to be decided at three
independent `scored.total < PROMOTE_THRESHOLD` sites that never consulted the
gate — so `ScoredItem.promote` was computed and then ignored, and a policy
change had to be made in three places or it silently did nothing. An earlier
revision of this very file "verified" the gate by counting
`promote=passes_nous_gate(` constructor assignments, which is not an admission
decision: the tests passed while the gate controlled nothing. Cross-model
review caught that. The tests below assert on the admission path instead.

POLICY (deliberately not landed). AXIS_FLOOR is 0. Enabling it is blocked on
heuristic_score, where novelty and relevance are the same variable read in
opposite directions:

    known_hits = sum(1 for term in LIFE_OS_TERMS if term in text)
    if known_hits >= 4: novelty = 0     # more jargon -> LESS novel
    relevance  = min(3, known_hits)     # more jargon -> MORE relevant

A floor on either axis therefore penalises the corpus for its own vocabulary.
`test_novelty_and_relevance_are_the_same_variable` pins that premise: when
someone fixes the scorer, it fails, which is the signal to turn the floor on.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bookkeeping.py"
_spec = importlib.util.spec_from_file_location("bookkeeping_under_test", _SCRIPT)
bk = importlib.util.module_from_spec(_spec)
sys.modules["bookkeeping_under_test"] = bk
_spec.loader.exec_module(bk)

_SRC = _SCRIPT.read_text()


def _scored(n, s, r):
    """A ScoredItem carrying only what the admission path reads."""
    return bk.ScoredItem(
        item=None, novelty=n, specificity=s, relevance=r,
        total=n + s + r, promote=bk.passes_nous_gate(n, s, r),
        candidate_entities=[], scoring_method="heuristic",
    )


class TestAdmissionPathIsTheThingUnderTest:
    """Not constructor assignments — the decision the pipeline actually makes."""

    def test_no_raw_total_comparison_admission_sites_remain(self):
        assert "if scored.total < PROMOTE_THRESHOLD:" not in _SRC, (
            "an admission site compares .total directly and bypasses the gate"
        )

    def test_every_admission_site_calls_the_predicate(self):
        assert _SRC.count("if not scored_item_admitted(scored):") == 3

    def test_admission_helper_reads_axes_not_total(self):
        """A ScoredItem whose .total disagrees with its axes must follow the axes."""
        s = _scored(3, 3, 0)
        s.total = 0  # a stale/incorrect total must not decide admission
        assert bk.scored_item_admitted(s) is True

    def test_admission_rejects_below_threshold(self):
        assert bk.scored_item_admitted(_scored(1, 1, 1)) is False

    def test_admission_accepts_at_threshold(self):
        assert bk.scored_item_admitted(_scored(2, 2, 1)) is True


class TestSumThreshold:
    def test_below_threshold_rejected(self):
        assert bk.passes_nous_gate(1, 1, 1) is False

    def test_at_threshold_promotes(self):
        assert bk.passes_nous_gate(2, 2, 1) is True

    def test_zero_everything_rejected(self):
        assert bk.passes_nous_gate(0, 0, 0) is False


class TestFloorIsPresentButDisabled:
    def test_floor_is_off(self):
        assert bk.AXIS_FLOOR == 0, "floor must stay off until the scorer is fixed"

    def test_zero_axis_still_admitted_while_floor_is_off(self):
        # n=0 s=3 r=3 (anima.md / praxis.md) and n=3 s=3 r=0 (jeff-dean.md)
        assert bk.passes_nous_gate(0, 3, 3) is True
        assert bk.passes_nous_gate(3, 3, 0) is True

    def test_enabling_the_floor_engages_it(self):
        """Proves AXIS_FLOOR is wired, not decorative — the one-constant flip."""
        original = bk.AXIS_FLOOR
        try:
            bk.AXIS_FLOOR = 1
            assert bk.passes_nous_gate(0, 3, 3) is False   # novelty floor
            assert bk.passes_nous_gate(3, 0, 3) is False   # specificity floor
            assert bk.passes_nous_gate(3, 3, 0) is True    # relevance exempt
        finally:
            bk.AXIS_FLOOR = original
        assert bk.passes_nous_gate(0, 3, 3) is True

    def test_relevance_exemption_flag_is_wired(self):
        original_floor, original_exempt = bk.AXIS_FLOOR, bk.RELEVANCE_EXEMPT_FROM_FLOOR
        try:
            bk.AXIS_FLOOR = 1
            bk.RELEVANCE_EXEMPT_FROM_FLOOR = False
            assert bk.passes_nous_gate(3, 3, 0) is False
        finally:
            bk.AXIS_FLOOR, bk.RELEVANCE_EXEMPT_FROM_FLOOR = original_floor, original_exempt


class TestThePremiseThatKeepsTheFloorOff:
    """When these fail, the scorer was fixed — turn AXIS_FLOOR on."""

    def test_novelty_and_relevance_are_the_same_variable(self):
        assert "relevance = min(3, known_hits)" in _SRC
        assert "if known_hits >= 4:" in _SRC
        assert "known_hits = sum(1 for term in LIFE_OS_TERMS if term in text)" in _SRC

    def test_adding_jargon_lowers_novelty_and_raises_relevance(self):
        """The perverse incentive, executed rather than asserted in prose."""
        terms = bk.LIFE_OS_TERMS[:5]
        mk = lambda body: bk.RawItem(
            item_id="t", source_id="test", source_type="research", content=body,
            quote="", author="", timestamp="2026-09-19",
        )
        few = "A claim about " + " and ".join(terms[:2]) + " because it matters. " + "x" * 250
        many = "A claim about " + " and ".join(terms[:5]) + " because it matters. " + "x" * 250
        n_few, _, r_few = bk.heuristic_score(mk(few))
        n_many, _, r_many = bk.heuristic_score(mk(many))
        assert n_many <= n_few, "more jargon should not raise novelty"
        assert r_many >= r_few, "more jargon should not lower relevance"
        assert (n_few, r_few) != (n_many, r_many), "the two axes must actually move"


@pytest.mark.parametrize(
    "n,s,r,expected",
    [
        (3, 3, 3, True), (2, 2, 1, True),
        (3, 3, 0, True),   # relevance zero admitted (floor off)
        (0, 3, 3, True),   # novelty zero admitted (floor off)
        (1, 1, 1, False),  # sum too low
        (0, 0, 0, False),
    ],
)
def test_gate_truth_table(n, s, r, expected):
    assert bk.passes_nous_gate(n, s, r) is expected
