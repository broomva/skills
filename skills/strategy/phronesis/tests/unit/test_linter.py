"""Linter rules — L1-L5 release-gate scanners.

Each rule is tested with:
  - a positive case: deliberately broken engagement → rule fires
  - a negative case: clean engagement → rule passes (zero violations of that rule)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.engagement import Engagement, EngagementJournal
from core.linter import (
    LintViolation,
    l1_strategic_thesis_required,
    l2_diverse_ideation_sources,
    l3_data_readiness_gate,
    l4_adoption_metric_required,
    l5_baseline_required,
    lint_engagement,
)
from core.types import EventKind, TenantContext

pytestmark = pytest.mark.unit


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="acme",
        name="Acme",
        industry="banking",
        region="CO",
        revenue_band="100M-1B",
        headcount_band="500-5000",
        sponsor="x",
        sponsor_role="CDO",
        engagement_scope="s",
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=8,
    )


@pytest.fixture
def engagement(tenant: TenantContext) -> Engagement:
    return Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))


# ----------------------------------------------------------------------------
# L1 STRATEGIC_THESIS_REQUIRED
# ----------------------------------------------------------------------------


class TestL1StrategicThesisRequired:
    def test_intake_closed_without_thesis_fires(self, engagement: Engagement):
        # Emit INTAKE_COMPLETED without a prior STRATEGIC_THESIS_DECLARED
        engagement.emit(
            EventKind.INTAKE_COMPLETED,
            "intake",
            {"thesis_id": "", "frameworks_selected": []},
        )
        violations = l1_strategic_thesis_required(engagement)
        assert any(v.rule == "L1" for v in violations)
        assert any(v.severity == "error" for v in violations)

    def test_passes_when_thesis_declared_first(self, engagement: Engagement):
        engagement.emit(
            EventKind.STRATEGIC_THESIS_DECLARED,
            "intake",
            {
                "thesis_id": "01HZ000",
                "economic_lever": "x",
                "lever_kind": "cost",
                "magnitude_estimate": "1",
                "horizon": "h1-now",
                "owner": "x",
            },
        )
        engagement.emit(
            EventKind.INTAKE_COMPLETED,
            "intake",
            {"thesis_id": "01HZ000", "frameworks_selected": []},
        )
        violations = l1_strategic_thesis_required(engagement)
        assert violations == []

    def test_passes_on_empty_journal(self, engagement: Engagement):
        # An engagement that hasn't reached intake.completed yet doesn't
        # violate L1 — the rule fires AT intake closure.
        violations = l1_strategic_thesis_required(engagement)
        assert violations == []


# ----------------------------------------------------------------------------
# L2 DIVERSE_IDEATION_SOURCES
# ----------------------------------------------------------------------------


def _propose(engagement: Engagement, uc_id: str, source: str) -> None:
    engagement.emit(
        EventKind.USE_CASE_PROPOSED,
        "ideate",
        {
            "use_case_id": uc_id,
            "expected_value": "100",
            "cost_estimate": "10",
            "ideation_source": source,
            "data_readiness_band": "pilot-ready",
        },
    )


class TestL2DiverseIdeationSources:
    def test_too_few_distinct_sources_fires(self, engagement: Engagement):
        _propose(engagement, "uc-1", "business-pain")
        _propose(engagement, "uc-2", "business-pain")
        violations = l2_diverse_ideation_sources(engagement)
        assert any(v.rule == "L2" and "distinct" in v.message for v in violations)

    def test_high_novelty_share_fires(self, engagement: Engagement):
        _propose(engagement, "uc-1", "business-pain")
        _propose(engagement, "uc-2", "data-opportunity")
        _propose(engagement, "uc-3", "novelty")
        _propose(engagement, "uc-4", "novelty")
        _propose(engagement, "uc-5", "novelty")
        violations = l2_diverse_ideation_sources(engagement)
        assert any(v.rule == "L2" and "NOVELTY share" in v.message for v in violations)

    def test_passes_with_diverse_low_novelty(self, engagement: Engagement):
        _propose(engagement, "uc-1", "business-pain")
        _propose(engagement, "uc-2", "data-opportunity")
        _propose(engagement, "uc-3", "regulatory-pressure")
        _propose(engagement, "uc-4", "competitive-response")
        violations = l2_diverse_ideation_sources(engagement)
        assert violations == []

    def test_passes_on_empty_use_cases(self, engagement: Engagement):
        violations = l2_diverse_ideation_sources(engagement)
        assert violations == []


# ----------------------------------------------------------------------------
# L3 DATA_READINESS_GATE
# ----------------------------------------------------------------------------


class TestL3DataReadinessGate:
    def test_blocking_band_fires(self, engagement: Engagement):
        engagement.emit(
            EventKind.USE_CASE_PROPOSED,
            "ideate",
            {
                "use_case_id": "uc-1",
                "expected_value": "100",
                "cost_estimate": "10",
                "ideation_source": "business-pain",
                "data_readiness_band": "blocking",
            },
        )
        violations = l3_data_readiness_gate(engagement)
        assert any(v.rule == "L3" and "blocking" in v.message for v in violations)

    def test_pilot_ready_passes(self, engagement: Engagement):
        engagement.emit(
            EventKind.USE_CASE_PROPOSED,
            "ideate",
            {
                "use_case_id": "uc-1",
                "expected_value": "100",
                "cost_estimate": "10",
                "ideation_source": "business-pain",
                "data_readiness_band": "pilot-ready",
            },
        )
        violations = l3_data_readiness_gate(engagement)
        assert violations == []

    def test_needs_prep_passes(self, engagement: Engagement):
        engagement.emit(
            EventKind.USE_CASE_PROPOSED,
            "ideate",
            {
                "use_case_id": "uc-1",
                "expected_value": "100",
                "cost_estimate": "10",
                "ideation_source": "business-pain",
                "data_readiness_band": "needs-prep",
            },
        )
        violations = l3_data_readiness_gate(engagement)
        assert violations == []


# ----------------------------------------------------------------------------
# L4 ADOPTION_METRIC_REQUIRED
# ----------------------------------------------------------------------------


class TestL4AdoptionMetricRequired:
    def test_pilot_without_pilot_plan_render_fires(self, engagement: Engagement):
        # Capture baseline (so L5 doesn't fire) then start pilot WITHOUT
        # rendering pilot-plan. L4 fires because adoption metric never
        # reaches the deliverable layer.
        engagement.emit(
            EventKind.BASELINE_CAPTURED,
            "roadmap",
            {
                "metric_name": "P95 latency",
                "baseline_value": "4.2",
                "captured_by": "VP Ops",
                "measurement_date": "2026-04-01",
            },
        )
        engagement.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "2026-Q3",
                "duration_weeks": 16,
            },
        )
        violations = l4_adoption_metric_required(engagement)
        assert any(v.rule == "L4" for v in violations)

    def test_pilot_with_pilot_plan_passes(self, engagement: Engagement):
        engagement.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "2026-Q3",
                "duration_weeks": 16,
            },
        )
        engagement.emit(
            EventKind.DELIVERABLE_RENDERED,
            "roadmap",
            {
                "slug": "pilot-plan",
                "output_path": "/tmp/pilot-plan.md",
                "linter_passed": True,
                "lint_warnings": [],
            },
        )
        violations = l4_adoption_metric_required(engagement)
        assert violations == []

    def test_no_pilots_passes(self, engagement: Engagement):
        violations = l4_adoption_metric_required(engagement)
        assert violations == []


# ----------------------------------------------------------------------------
# L5 BASELINE_REQUIRED
# ----------------------------------------------------------------------------


class TestL5BaselineRequired:
    def test_pilot_without_baseline_fires(self, engagement: Engagement):
        engagement.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "2026-Q3",
                "duration_weeks": 16,
            },
        )
        violations = l5_baseline_required(engagement)
        assert any(v.rule == "L5" for v in violations)

    def test_pilot_with_prior_baseline_passes(self, engagement: Engagement):
        # Order matters: BASELINE_CAPTURED before PILOT_STARTED.
        engagement.emit(
            EventKind.BASELINE_CAPTURED,
            "roadmap",
            {
                "metric_name": "P95 latency",
                "baseline_value": "4.2",
                "captured_by": "VP Ops",
                "measurement_date": "2026-04-01",
            },
        )
        engagement.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "2026-Q3",
                "duration_weeks": 16,
            },
        )
        violations = l5_baseline_required(engagement)
        assert violations == []

    def test_baseline_after_pilot_does_not_satisfy(self, engagement: Engagement):
        """No retroactive baselines: BASELINE_CAPTURED after PILOT_STARTED
        does NOT satisfy the rule."""
        engagement.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "2026-Q3",
                "duration_weeks": 16,
            },
        )
        engagement.emit(
            EventKind.BASELINE_CAPTURED,
            "roadmap",
            {
                "metric_name": "P95 latency",
                "baseline_value": "4.2",
                "captured_by": "VP Ops",
                "measurement_date": "2026-04-01",
            },
        )
        violations = l5_baseline_required(engagement)
        assert any(v.rule == "L5" for v in violations)


# ----------------------------------------------------------------------------
# Aggregate runner
# ----------------------------------------------------------------------------


class TestLintEngagement:
    def test_clean_engagement_zero_violations(self, engagement: Engagement):
        # Emit a minimal but L-clean sequence
        engagement.emit(
            EventKind.STRATEGIC_THESIS_DECLARED,
            "intake",
            {
                "thesis_id": "01HZ000",
                "economic_lever": "x",
                "lever_kind": "cost",
                "magnitude_estimate": "1",
                "horizon": "h1-now",
                "owner": "x",
            },
        )
        engagement.emit(
            EventKind.INTAKE_COMPLETED,
            "intake",
            {"thesis_id": "01HZ000", "frameworks_selected": ["rice"]},
        )
        result = lint_engagement(engagement)
        assert not result.has_errors
        assert result.violations == []

    def test_broken_engagement_collects_multiple_violations(self, engagement: Engagement):
        # Closed intake without thesis → L1
        engagement.emit(
            EventKind.INTAKE_COMPLETED,
            "intake",
            {"thesis_id": "", "frameworks_selected": []},
        )
        # Pilot without baseline → L5
        engagement.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "x",
                "duration_weeks": 16,
            },
        )
        result = lint_engagement(engagement)
        assert result.has_errors
        rules_fired = {v.rule for v in result.violations}
        assert "L1" in rules_fired
        assert "L5" in rules_fired
        # And L4 because PILOT_STARTED has no pilot-plan deliverable
        assert "L4" in rules_fired

    def test_errors_for_rule_filter(self, engagement: Engagement):
        engagement.emit(
            EventKind.INTAKE_COMPLETED,
            "intake",
            {"thesis_id": "", "frameworks_selected": []},
        )
        result = lint_engagement(engagement)
        l1_errors = result.errors_for_rule("L1")
        assert len(l1_errors) == 1
        assert all(isinstance(e, LintViolation) for e in l1_errors)
