"""End-to-end test — synthetic Acme Bank engagement (M6).

Drives the acme-bank fixture through all 5 stages + render orchestrator
and asserts the expected deliverable counts hold within ±10% tolerance.
Also asserts the linter passes (L1-L5 + P3/P7/P8 — zero errors).

This is the regression suite — when frameworks/prompts/templates change,
this test catches breakage at engagement scale.

Sister test to test_bision_prevention.py (L-rule rejection) and
test_anonymization_canary.py (tenant-marker leak). Together the three
acceptance tests cover: typed-primitive integrity + L-rule enforcement +
tenant data isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.linter import lint_engagement
from core.orchestrator import DELIVERABLE_SLUGS, render_all
from core.types import EventKind
from tests.fixtures.acme_bank import (
    build_acme_bank_engagement,
    deliverable_extras,
    findings_for_test,
)

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


# Expected deliverable counts (per M6 handoff). Tolerance lets the
# fixture evolve without immediately breaking — but the SHAPE is locked.
EXPECTED_DELIVERABLE_COUNT = 7
EXPECTED_FINDINGS = 25  # ±10% → 22-28 acceptable
EXPECTED_USE_CASES = 12  # ±10% → 10-13
EXPECTED_PRIORITIZED = 5  # top-5 (handoff spec)
EXPECTED_PILOTS = 1  # acme-bank designs 1 (chatbot)
EXPECTED_ROADMAP_STEPS = 5
TOLERANCE = 0.10


def _within(observed: int, expected: int, tolerance: float = TOLERANCE) -> bool:
    """±tolerance band test."""
    lo = int(expected * (1.0 - tolerance))
    hi = int(expected * (1.0 + tolerance)) + 1
    return lo <= observed <= hi


class TestAcmeBankEngagementShape:
    """The fixture exercises all 5 stages and concludes cleanly."""

    def test_engagement_concludes(self):
        eng = build_acme_bank_engagement()
        state = eng.state()
        assert state.is_concluded, "Acme Bank fixture must reach concluded state"
        assert state.thesis_id is not None, "L1 — thesis must be declared"
        assert state.current_stage == "concluded"

    def test_all_5_stages_emit_review_requested(self):
        eng = build_acme_bank_engagement()
        review_stages = {
            ev.payload["stage"]
            for ev in eng.journal.events
            if ev.kind == EventKind.STAGE_REVIEW_REQUESTED
        }
        assert review_stages == {"intake", "scan", "ideate", "prioritize", "roadmap"}

    def test_intake_emits_5_interviews_and_3_documents(self):
        eng = build_acme_bank_engagement()
        interviews = [ev for ev in eng.journal.events if ev.kind == EventKind.INTERVIEW_LOGGED]
        documents = [ev for ev in eng.journal.events if ev.kind == EventKind.DOCUMENT_INGESTED]
        assert len(interviews) == 5, "Acme spec: 5 interviews (CDO/CFO/CTO/HoCS/LDE)"
        assert len(documents) == 3, "Acme spec: 3 documents (org, IT arch, incident)"


class TestAcmeBankDeliverableCounts:
    """Within-tolerance counts for the bigger downstream deliverables."""

    def test_use_case_count_within_tolerance(self):
        eng = build_acme_bank_engagement()
        use_cases = eng.state().use_cases
        assert _within(len(use_cases), EXPECTED_USE_CASES), (
            f"Use-case count {len(use_cases)} outside ±{int(TOLERANCE * 100)}% "
            f"of expected {EXPECTED_USE_CASES}"
        )

    def test_prioritized_count_within_tolerance(self):
        eng = build_acme_bank_engagement()
        prioritized = eng.state().use_cases_prioritized
        assert _within(len(prioritized), EXPECTED_PRIORITIZED), (
            f"Prioritized count {len(prioritized)} outside ±{int(TOLERANCE * 100)}% "
            f"of expected {EXPECTED_PRIORITIZED}"
        )

    def test_roadmap_step_count(self):
        eng = build_acme_bank_engagement()
        steps = [ev for ev in eng.journal.events if ev.kind == EventKind.ROADMAP_STEP_PROPOSED]
        assert _within(len(steps), EXPECTED_ROADMAP_STEPS), (
            f"Roadmap-step count {len(steps)} outside ±{int(TOLERANCE * 100)}% "
            f"of expected {EXPECTED_ROADMAP_STEPS}"
        )

    def test_pilot_design_count(self):
        eng = build_acme_bank_engagement()
        pilots = [ev for ev in eng.journal.events if ev.kind == EventKind.PILOT_STARTED]
        assert len(pilots) == EXPECTED_PILOTS, (
            f"Pilot count {len(pilots)} — Acme spec designs {EXPECTED_PILOTS}"
        )

    def test_findings_count_within_tolerance(self):
        """findings_for_test() exposes the synthetic findings list (~25
        spread across 4 maturity dimensions + per-UC risks)."""
        findings = findings_for_test()
        assert _within(len(findings), EXPECTED_FINDINGS), (
            f"Findings count {len(findings)} outside ±{int(TOLERANCE * 100)}% "
            f"of expected {EXPECTED_FINDINGS}"
        )


class TestAcmeBankLinterPasses:
    """The engagement lints CLEAN against L1-L5 + P3/P7/P8.

    If this test fails after a substrate change, the linter is no longer
    a backstop for the canonical engagement shape and the failure mode
    must be investigated before merge.
    """

    def test_zero_lint_errors(self):
        eng = build_acme_bank_engagement()
        result = lint_engagement(eng)
        assert not result.has_errors, (
            f"Acme Bank fixture must lint clean. Got: "
            f"{[(v.rule, v.message) for v in result.violations]}"
        )

    def test_no_lint_violations_at_all(self):
        eng = build_acme_bank_engagement()
        result = lint_engagement(eng)
        assert result.violations == []


class TestAcmeBankRendersAllDeliverables:
    """The full render orchestrator produces all 7 markdown deliverables."""

    def test_all_7_deliverables_render(self, tmp_path: Path):
        eng = build_acme_bank_engagement()
        ctx = deliverable_extras()
        paths, lint_result = render_all(eng, tmp_path, extra_context=ctx)

        # 7 deliverables, slugs match the locked orchestrator order
        assert len(paths) == EXPECTED_DELIVERABLE_COUNT
        assert set(paths.keys()) == set(DELIVERABLE_SLUGS)

        # Each file is a real, non-empty markdown document
        for slug, path in paths.items():
            assert path.exists(), f"{slug} missing on disk"
            content = path.read_text()
            assert content, f"{slug} rendered empty"
            assert content.startswith("#"), f"{slug} missing top-level heading"

    def test_render_with_zero_lint_errors(self, tmp_path: Path):
        eng = build_acme_bank_engagement()
        ctx = deliverable_extras()
        _paths, lint_result = render_all(eng, tmp_path, extra_context=ctx)
        assert not lint_result.has_errors

    def test_maturity_report_carries_thesis(self, tmp_path: Path):
        """The strategic-thesis economic-lever must appear in maturity-report —
        ensures the typed primitive flows through the template."""
        eng = build_acme_bank_engagement()
        ctx = deliverable_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)
        content = paths["maturity-report"].read_text()
        assert "Tier-1" in content or "SME" in content
        assert "Mariana Restrepo" in content  # raw rendering — anonymization is separate

    def test_pilot_plan_carries_adoption_metric_and_baseline(self, tmp_path: Path):
        eng = build_acme_bank_engagement()
        ctx = deliverable_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)
        content = paths["pilot-plan"].read_text()
        # L4 — adoption metric section header (template line)
        assert "L4 — Adoption metric" in content
        # L5 — baseline section header
        assert "L5 — Baselines declared BEFORE pilot start" in content
        # Specific adoption metric content
        assert "Tier-1" in content


class TestAcmeBankBaselineDiscipline:
    """L5 invariant — every PILOT_STARTED preceded by ≥1 BASELINE_CAPTURED.
    The acme-bank fixture captures BOTH chatbot AND SME credit baselines
    (2 baselines), then starts 1 pilot — proving the substrate handles
    multi-baseline engagements cleanly."""

    def test_baselines_captured_before_pilots(self):
        eng = build_acme_bank_engagement()
        events = eng.journal.events
        first_pilot_idx = next(
            i for i, ev in enumerate(events) if ev.kind == EventKind.PILOT_STARTED
        )
        baselines_before = [
            ev for ev in events[:first_pilot_idx] if ev.kind == EventKind.BASELINE_CAPTURED
        ]
        assert len(baselines_before) >= 1, "L5 — at least one baseline before first pilot"

    def test_two_baselines_captured(self):
        """Acme spec captures 2 baselines (chatbot deflection + SME cycle time)."""
        eng = build_acme_bank_engagement()
        baselines = [ev for ev in eng.journal.events if ev.kind == EventKind.BASELINE_CAPTURED]
        assert len(baselines) == 2
