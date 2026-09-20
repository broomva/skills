"""The Nous gate's per-axis floor.

A sum-only gate admits an item that scores 0 on an axis, because 3+2+0 still
clears 5. Measured on the live corpus at the time this landed: 140 of 283
scored items (49.5%) had promoted with a zero axis.

The floor covers novelty and specificity but deliberately NOT relevance,
because `heuristic_score` computes relevance as
`min(3, <count of LIFE_OS_TERMS substrings>)` — a jargon-conformance counter,
not a relevance measurement. 133 of those 140 were relevance=0 and include
plainly-relevant external material. Gating on that proxy would invert the
gate's purpose, so these tests pin the exemption as intentional: if someone
later "fixes" the asymmetry without fixing the scorer, `test_relevance_zero_
still_promotes` fails and points at why.
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


class TestSumThresholdStillApplies:
    def test_below_threshold_rejected(self):
        assert bk.passes_nous_gate(1, 1, 1) is False  # total 3 < 5

    def test_at_threshold_promotes(self):
        assert bk.passes_nous_gate(2, 2, 1) is True  # total 5

    def test_above_threshold_promotes(self):
        assert bk.passes_nous_gate(3, 3, 3) is True


class TestPerAxisFloor:
    def test_zero_novelty_blocked_even_when_sum_clears(self):
        # n=0 s=3 r=3 -> total 6, clears the sum gate, but "we already know
        # this". This is the anima.md / praxis.md case.
        assert 0 + 3 + 3 >= bk.PROMOTE_THRESHOLD
        assert bk.passes_nous_gate(0, 3, 3) is False

    def test_zero_specificity_blocked_even_when_sum_clears(self):
        assert 3 + 0 + 3 >= bk.PROMOTE_THRESHOLD
        assert bk.passes_nous_gate(3, 0, 3) is False

    def test_floor_is_exactly_one(self):
        assert bk.AXIS_FLOOR == 1
        assert bk.passes_nous_gate(1, 3, 1) is True
        assert bk.passes_nous_gate(0, 3, 3) is False


class TestRelevanceExemption:
    def test_relevance_zero_still_promotes(self):
        """The load-bearing exemption.

        n=3 s=3 r=0 is entities/discovery/jeff-dean.md — relevant material
        that merely fails to contain LIFE_OS_TERMS. It must still promote
        while relevance is a jargon counter.
        """
        assert bk.passes_nous_gate(3, 3, 0) is True

    def test_exemption_is_flagged_not_accidental(self):
        assert bk.RELEVANCE_EXEMPT_FROM_FLOOR is True

    def test_flipping_the_flag_enables_the_relevance_floor(self):
        """Proves the flag is wired, not decorative."""
        original = bk.RELEVANCE_EXEMPT_FROM_FLOOR
        try:
            bk.RELEVANCE_EXEMPT_FROM_FLOOR = False
            assert bk.passes_nous_gate(3, 3, 0) is False
        finally:
            bk.RELEVANCE_EXEMPT_FROM_FLOOR = original
        # and restored
        assert bk.passes_nous_gate(3, 3, 0) is True

    def test_relevance_scorer_is_still_a_jargon_counter(self):
        """Guards the premise of the exemption.

        If someone fixes heuristic_score to measure real relevance, this test
        fails — which is the signal to revisit the exemption rather than let
        it persist unexamined.
        """
        src = _SCRIPT.read_text()
        assert "relevance = min(3, known_hits)" in src, (
            "relevance scorer changed; re-evaluate RELEVANCE_EXEMPT_FROM_FLOOR"
        )


class TestEveryPromoteSiteRoutesThroughTheGate:
    """A guard at one of N doors is not a guard.

    There were three `promote=total >= PROMOTE_THRESHOLD` sites. If a fourth
    promote site is ever added without routing through passes_nous_gate, the
    floor silently stops covering it.
    """

    def test_no_sum_only_promote_sites_remain(self):
        src = _SCRIPT.read_text()
        assert "promote=total >= PROMOTE_THRESHOLD" not in src

    def test_all_promote_sites_use_the_predicate(self):
        src = _SCRIPT.read_text()
        routed = src.count("promote=passes_nous_gate(")
        total_sites = len([
            ln for ln in src.splitlines() if ln.strip().startswith("promote=")
        ])
        assert routed == total_sites, (
            f"{total_sites - routed} promote site(s) bypass passes_nous_gate"
        )
        assert routed == 3, f"expected 3 promote sites, found {routed}"


@pytest.mark.parametrize(
    "n,s,r,expected",
    [
        (3, 3, 3, True),
        (2, 2, 1, True),
        (3, 3, 0, True),   # relevance exempt
        (0, 3, 3, False),  # zero novelty
        (3, 0, 3, False),  # zero specificity
        (1, 1, 1, False),  # sum too low
        (0, 0, 0, False),
    ],
)
def test_gate_truth_table(n, s, r, expected):
    assert bk.passes_nous_gate(n, s, r) is expected
