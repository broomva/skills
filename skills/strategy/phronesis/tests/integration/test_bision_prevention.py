"""Bision empirical-failure-mode prevention — RELEASE GATE.

This is THE acceptance test. If any of these fail, no release ships.

Each test constructs an engagement that VIOLATES exactly one Bision-observed
failure mode (L1-L5) and asserts the linter rejects it with severity=error
on the corresponding rule.

Plus: the canonical Tropico fixture passes the linter cleanly (no L-errors).

Bision empirical frequencies (source: Bision Consulting C-Level slide,
Bogotá 2026):
  L1 — Sin tesis estratégica           — 100% observed
  L2 — Casos de uso mal priorizados    — 87%
  L3 — Datos no preparados             — 74%
  L4 — Desconexión negocio-tecnología  — 61%
  L5 — Sin medición de ROI             — 48%
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.engagement import Engagement, EngagementJournal
from core.linter import lint_engagement
from core.types import EventKind, TenantContext
from tests.fixtures.tropico_renovables import build_tropico_engagement

pytestmark = [pytest.mark.integration, pytest.mark.bision_prevention]


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="acme-broken",
        name="Acme Broken Co",
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


def _empty(tenant: TenantContext) -> Engagement:
    return Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))


def _propose_uc(eng: Engagement, uc_id: str, source: str, band: str = "pilot-ready") -> None:
    eng.emit(
        EventKind.USE_CASE_PROPOSED,
        "ideate",
        {
            "use_case_id": uc_id,
            "expected_value": "100",
            "cost_estimate": "10",
            "ideation_source": source,
            "data_readiness_band": band,
        },
    )


# ----------------------------------------------------------------------------
# Canonical clean fixture — must NEVER fail the linter
# ----------------------------------------------------------------------------


class TestCleanFixturePassesLinter:
    """The Tropico Renovables fixture is the proof-of-life for the entire
    Phase 1 substrate. If this test fails, the substrate is broken."""

    def test_tropico_fixture_zero_l_errors(self):
        eng = build_tropico_engagement()
        result = lint_engagement(eng)
        assert not result.has_errors, (
            f"Tropico fixture must lint clean. Got: "
            f"{[(v.rule, v.message) for v in result.violations]}"
        )
        assert result.violations == []


# ----------------------------------------------------------------------------
# L1 — STRATEGIC_THESIS_REQUIRED (Bision Failure 1, 100% observed)
# ----------------------------------------------------------------------------


class TestL1RejectsEngagementWithoutThesis:
    def test_intake_closed_without_thesis_blocks(self, tenant: TenantContext):
        # An engagement that closes intake without declaring a thesis.
        # Bision Failure 1: 'sin tesis estratégica' / 'hagamos algo de IA'.
        eng = _empty(tenant)
        eng.emit(
            EventKind.ENGAGEMENT_STARTED,
            "intake",
            {
                "tenant_slug": "acme-broken",
                "scope": "do AI",  # vague — the failure mode itself
                "sponsor": "x",
                "target_duration_weeks": 8,
            },
        )
        eng.emit(
            EventKind.INTAKE_COMPLETED,
            "intake",
            {"thesis_id": "", "frameworks_selected": ["rice"]},
        )

        result = lint_engagement(eng)
        l1_errors = result.errors_for_rule("L1")
        assert len(l1_errors) >= 1
        assert "STRATEGIC_THESIS_REQUIRED" in l1_errors[0].message
        assert "Bision Failure 1" in l1_errors[0].message


# ----------------------------------------------------------------------------
# L2 — DIVERSE_IDEATION_SOURCES (Bision Failure 2, 87%)
# ----------------------------------------------------------------------------


class TestL2RejectsHighNoveltyOrThinSourceMix:
    def test_too_few_distinct_sources_blocks(self, tenant: TenantContext):
        eng = _empty(tenant)
        # 2 use cases, 1 source — fails distinct-sources floor
        _propose_uc(eng, "uc-1", "business-pain")
        _propose_uc(eng, "uc-2", "business-pain")

        result = lint_engagement(eng)
        l2_errors = result.errors_for_rule("L2")
        assert any("distinct" in v.message for v in l2_errors)

    def test_majority_novelty_blocks(self, tenant: TenantContext):
        eng = _empty(tenant)
        # 5 use cases, 3 NOVELTY (60%) but 3 distinct sources — isolates the
        # novelty share rule from the diversity rule
        _propose_uc(eng, "uc-1", "business-pain")
        _propose_uc(eng, "uc-2", "data-opportunity")
        _propose_uc(eng, "uc-3", "novelty")
        _propose_uc(eng, "uc-4", "novelty")
        _propose_uc(eng, "uc-5", "novelty")

        result = lint_engagement(eng)
        l2_errors = result.errors_for_rule("L2")
        assert any("NOVELTY share" in v.message for v in l2_errors)


# ----------------------------------------------------------------------------
# L3 — DATA_READINESS_GATE (Bision Failure 3, 74%)
# ----------------------------------------------------------------------------


class TestL3RejectsBlockingDataReadiness:
    def test_blocking_use_case_blocks(self, tenant: TenantContext):
        eng = _empty(tenant)
        # Diverse-enough sources to NOT trip L2; one UC marked blocking
        _propose_uc(eng, "uc-1", "business-pain")
        _propose_uc(eng, "uc-2", "data-opportunity")
        _propose_uc(eng, "uc-3", "regulatory-pressure", band="blocking")
        _propose_uc(eng, "uc-4", "competitive-response")

        result = lint_engagement(eng)
        l3_errors = result.errors_for_rule("L3")
        assert any("uc-3" in v.location for v in l3_errors)
        assert any("blocking" in v.message for v in l3_errors)


# ----------------------------------------------------------------------------
# L4 — ADOPTION_METRIC_REQUIRED (Bision Failure 4, 61%)
# ----------------------------------------------------------------------------


class TestL4RejectsPilotWithoutAdoptionMetricInDeliverable:
    def test_pilot_without_pilot_plan_render_blocks(self, tenant: TenantContext):
        eng = _empty(tenant)
        # Capture baseline first (so L5 doesn't also fire) then start pilot
        # WITHOUT rendering pilot-plan — L4 catches that the adoption metric
        # never reaches the deliverable layer.
        eng.emit(
            EventKind.BASELINE_CAPTURED,
            "roadmap",
            {
                "metric_name": "P95 latency",
                "baseline_value": "4.2",
                "captured_by": "VP Ops",
                "measurement_date": "2026-04-01",
            },
        )
        eng.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "2026-Q3",
                "duration_weeks": 16,
            },
        )

        result = lint_engagement(eng)
        l4_errors = result.errors_for_rule("L4")
        assert len(l4_errors) >= 1
        assert "Bision Failure 4" in l4_errors[0].message


# ----------------------------------------------------------------------------
# L5 — BASELINE_REQUIRED (Bision Failure 5, 48%)
# ----------------------------------------------------------------------------


class TestL5RejectsPilotWithoutBaseline:
    def test_pilot_without_prior_baseline_blocks(self, tenant: TenantContext):
        eng = _empty(tenant)
        # Pilot started with zero prior BASELINE_CAPTURED events.
        eng.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "2026-Q3",
                "duration_weeks": 16,
            },
        )

        result = lint_engagement(eng)
        l5_errors = result.errors_for_rule("L5")
        assert len(l5_errors) >= 1
        assert "BASELINE_REQUIRED" in l5_errors[0].message
        assert "no retroactive baselines" in l5_errors[0].message

    def test_baseline_after_pilot_does_not_satisfy(self, tenant: TenantContext):
        """Order matters — BASELINE_CAPTURED after PILOT_STARTED is exactly
        the retroactive-baseline anti-pattern Bision Failure 5 names."""
        eng = _empty(tenant)
        eng.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "2026-Q3",
                "duration_weeks": 16,
            },
        )
        eng.emit(
            EventKind.BASELINE_CAPTURED,
            "roadmap",
            {
                "metric_name": "P95 latency",
                "baseline_value": "4.2",
                "captured_by": "VP Ops",
                "measurement_date": "2026-04-01",
            },
        )

        result = lint_engagement(eng)
        l5_errors = result.errors_for_rule("L5")
        assert len(l5_errors) >= 1


# ----------------------------------------------------------------------------
# Compound — multiple failure modes in one engagement
# ----------------------------------------------------------------------------


class TestCompoundFailures:
    def test_engagement_with_multiple_failures_collects_all_rules(self, tenant: TenantContext):
        """A worst-case engagement that violates L1 + L4 + L5 simultaneously.
        The linter must surface all three so the operator sees the full picture
        rather than fixing one at a time."""
        eng = _empty(tenant)
        eng.emit(
            EventKind.INTAKE_COMPLETED,
            "intake",
            {"thesis_id": "", "frameworks_selected": []},
        )
        eng.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": "uc-1",
                "pilot_design_ref": "pd-1",
                "start_date": "2026-Q3",
                "duration_weeks": 16,
            },
        )

        result = lint_engagement(eng)
        rules_fired = {v.rule for v in result.violations}
        assert "L1" in rules_fired
        assert "L4" in rules_fired
        assert "L5" in rules_fired
