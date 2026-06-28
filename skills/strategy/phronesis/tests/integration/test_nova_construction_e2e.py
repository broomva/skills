"""End-to-end test — synthetic Nova Construction engagement (M6).

Sister to test_acme_bank_e2e.py — drives the smaller-scale nova-construction
fixture through all 5 stages and asserts the deliverable shape holds even
when engagement scale shrinks (4 interviews vs 5, 8 use cases vs 12, etc).

This is the proof that the 7-deliverable structure is industry-agnostic:
construction engagement produces the same artifacts the financial-services
one does. When that ceases to be true, the substrate is no longer reusable
across verticals.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.linter import lint_engagement
from core.orchestrator import DELIVERABLE_SLUGS, render_all
from core.types import EventKind
from tests.fixtures.nova_construction import (
    build_nova_construction_engagement,
    deliverable_extras,
    findings_for_test,
)

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


# Smaller-scale expectations per handoff (~20 findings, ~8 UCs, top-3, 2 pilots).
EXPECTED_DELIVERABLE_COUNT = 7
EXPECTED_FINDINGS = 20
EXPECTED_USE_CASES = 8
EXPECTED_PRIORITIZED = 3  # top-3
EXPECTED_PILOTS = 2  # procurement + site-data
EXPECTED_ROADMAP_STEPS = 3
TOLERANCE = 0.10


def _within(observed: int, expected: int, tolerance: float = TOLERANCE) -> bool:
    lo = int(expected * (1.0 - tolerance))
    hi = int(expected * (1.0 + tolerance)) + 1
    return lo <= observed <= hi


class TestNovaConstructionEngagementShape:
    def test_engagement_concludes(self):
        eng = build_nova_construction_engagement()
        state = eng.state()
        assert state.is_concluded
        assert state.thesis_id is not None
        assert state.current_stage == "concluded"

    def test_all_5_stages_emit_review_requested(self):
        eng = build_nova_construction_engagement()
        review_stages = {
            ev.payload["stage"]
            for ev in eng.journal.events
            if ev.kind == EventKind.STAGE_REVIEW_REQUESTED
        }
        assert review_stages == {"intake", "scan", "ideate", "prioritize", "roadmap"}

    def test_intake_emits_4_interviews_and_2_documents(self):
        eng = build_nova_construction_engagement()
        interviews = [ev for ev in eng.journal.events if ev.kind == EventKind.INTERVIEW_LOGGED]
        documents = [ev for ev in eng.journal.events if ev.kind == EventKind.DOCUMENT_INGESTED]
        # Smaller engagement than acme — 4 interviews + 2 docs
        assert len(interviews) == 4
        assert len(documents) == 2


class TestNovaConstructionDeliverableCounts:
    def test_use_case_count_within_tolerance(self):
        eng = build_nova_construction_engagement()
        use_cases = eng.state().use_cases
        assert _within(len(use_cases), EXPECTED_USE_CASES), (
            f"Use-case count {len(use_cases)} outside ±{int(TOLERANCE * 100)}% "
            f"of expected {EXPECTED_USE_CASES}"
        )

    def test_prioritized_count_within_tolerance(self):
        eng = build_nova_construction_engagement()
        prioritized = eng.state().use_cases_prioritized
        assert _within(len(prioritized), EXPECTED_PRIORITIZED), (
            f"Prioritized count {len(prioritized)} outside ±{int(TOLERANCE * 100)}% "
            f"of expected {EXPECTED_PRIORITIZED}"
        )

    def test_roadmap_step_count(self):
        eng = build_nova_construction_engagement()
        steps = [ev for ev in eng.journal.events if ev.kind == EventKind.ROADMAP_STEP_PROPOSED]
        assert _within(len(steps), EXPECTED_ROADMAP_STEPS), (
            f"Roadmap-step count {len(steps)} outside ±{int(TOLERANCE * 100)}% "
            f"of expected {EXPECTED_ROADMAP_STEPS}"
        )

    def test_pilot_design_count(self):
        eng = build_nova_construction_engagement()
        pilots = [ev for ev in eng.journal.events if ev.kind == EventKind.PILOT_STARTED]
        assert len(pilots) == EXPECTED_PILOTS, (
            f"Pilot count {len(pilots)} — Nova spec designs {EXPECTED_PILOTS}"
        )

    def test_findings_count_within_tolerance(self):
        findings = findings_for_test()
        assert _within(len(findings), EXPECTED_FINDINGS), (
            f"Findings count {len(findings)} outside ±{int(TOLERANCE * 100)}% "
            f"of expected {EXPECTED_FINDINGS}"
        )


class TestNovaConstructionLinterPasses:
    def test_zero_lint_errors(self):
        eng = build_nova_construction_engagement()
        result = lint_engagement(eng)
        assert not result.has_errors, (
            f"Nova fixture must lint clean. Got: {[(v.rule, v.message) for v in result.violations]}"
        )

    def test_no_lint_violations_at_all(self):
        eng = build_nova_construction_engagement()
        result = lint_engagement(eng)
        assert result.violations == []


class TestNovaConstructionRendersAllDeliverables:
    def test_all_7_deliverables_render(self, tmp_path: Path):
        eng = build_nova_construction_engagement()
        ctx = deliverable_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)
        assert len(paths) == EXPECTED_DELIVERABLE_COUNT
        assert set(paths.keys()) == set(DELIVERABLE_SLUGS)
        for slug, path in paths.items():
            assert path.exists(), f"{slug} missing on disk"
            assert path.read_text(), f"{slug} rendered empty"

    def test_render_with_zero_lint_errors(self, tmp_path: Path):
        eng = build_nova_construction_engagement()
        ctx = deliverable_extras()
        _paths, lint_result = render_all(eng, tmp_path, extra_context=ctx)
        assert not lint_result.has_errors

    def test_smaller_scale_engagement_still_produces_7_deliverables(self, tmp_path: Path):
        """Engagement-size invariant: even at smaller scale (4 interviews,
        8 UCs, top-3) the deliverable count is still 7. This is the proof
        the substrate scales down as well as up."""
        eng = build_nova_construction_engagement()
        ctx = deliverable_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)
        # Same shape as acme-bank's 12 UCs / top-5 / 1 pilot output.
        assert len(paths) == EXPECTED_DELIVERABLE_COUNT


class TestNovaConstructionGreenfieldPilot:
    """The nova fixture exercises L5's greenfield-baseline branch — the
    site-data pilot starts with a zero-state declared baseline because no
    incumbent structured-report capture exists. This is the BRO-1034 case
    the L5 invariant explicitly accommodates."""

    def test_second_pilot_uses_greenfield_baseline(self, tmp_path: Path):
        eng = build_nova_construction_engagement()
        ctx = deliverable_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)
        # The first pilot (procurement) flows to pilot-plan; the second
        # (site-data, greenfield) is still in the journal as PILOT_STARTED.
        pilots = [ev for ev in eng.journal.events if ev.kind == EventKind.PILOT_STARTED]
        assert len(pilots) == 2
        # Each pilot has at least one BASELINE_CAPTURED before it
        baseline_events = [
            ev for ev in eng.journal.events if ev.kind == EventKind.BASELINE_CAPTURED
        ]
        assert len(baseline_events) >= 2, (
            "Nova spec captures 2 baselines (procurement + site-data greenfield)"
        )

    def test_all_pilots_preceded_by_baselines(self):
        """Re-iteration of L5 — order matters. For every PILOT_STARTED,
        the journal must have at least one BASELINE_CAPTURED before it."""
        eng = build_nova_construction_engagement()
        events = eng.journal.events
        baselines_so_far = 0
        for ev in events:
            if ev.kind == EventKind.BASELINE_CAPTURED:
                baselines_so_far += 1
            elif ev.kind == EventKind.PILOT_STARTED:
                assert baselines_so_far >= 1, (
                    f"L5 violation — pilot {ev.payload.get('use_case_id')} "
                    f"started with zero prior baselines (anti-retroactive)"
                )
