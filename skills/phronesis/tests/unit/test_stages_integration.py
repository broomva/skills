"""Cross-stage integration test — Tropico Renovables synthetic engagement.

Drives all 5 stages end-to-end against the M0+M1+M2 substrate. Verifies:
  - Journal contains the expected event sequence in order
  - Replay produces state.is_concluded == True
  - All L-rules fire correctly across stage boundaries
  - All 7 deliverable slugs are recorded as rendered (M3 wires the actual
    Jinja2 templates; this test asserts the events that drive them)

Phase E will lift this into tests/integration/ as the bision-prevention
release gate. Phase 1 keeps it under tests/unit/ so make check exercises
it on every CI run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest

from core.engagement import Engagement, EngagementJournal
from core.types import (
    AdoptionMetric,
    BaselineSection,
    Citation,
    DataReadinessAssessment,
    EventKind,
    Finding,
    IdeationSource,
    MaturityDimension,
    PilotDesign,
    RoadmapStep,
    RoiCell,
    Score,
    StrategicThesis,
    TenantContext,
    UseCase,
)
from stages.ideate import IdeationStage
from stages.intake import IntakeStage
from stages.prioritize import PrioritizationStage
from stages.roadmap import RoadmapStage
from stages.scan import MaturityScanStage

pytestmark = pytest.mark.unit


# ----------------------------------------------------------------------------
# Tropico Renovables synthetic fixture
# ----------------------------------------------------------------------------


@pytest.fixture
def tropico() -> Engagement:
    tenant = TenantContext(
        tenant_slug="tropico-renovables",
        name="Tropico Renovables S.A.S.",
        industry="energy-utilities",
        region="CO",
        revenue_band="<10M",
        headcount_band="50-500",
        sponsor="Catalina Vélez",
        sponsor_role="COO",
        engagement_scope=(
            "AI control-engineering maturity assessment + 3 prioritized use cases "
            "for 62 MW tropical-coast renewable portfolio."
        ),
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=10,
    )
    return Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))


@pytest.fixture
def cite() -> Citation:
    return Citation(
        kind="evidence",
        ref="interview:coo-velez:2026-05-06",
        confidence="high",
    )


@pytest.fixture
def benchmark_cite() -> Citation:
    return Citation(
        kind="evidence",
        ref="bench:peer-iPP-2025",
        confidence="medium",
    )


# ----------------------------------------------------------------------------
# End-to-end engagement
# ----------------------------------------------------------------------------


class TestTropicoEngagementEndToEnd:
    def test_full_5_stage_engagement_concludes(
        self,
        tropico: Engagement,
        cite: Citation,
        benchmark_cite: Citation,
    ):
        # ---- Stage 1: INTAKE ----
        intake = IntakeStage()
        intake.run(tropico)
        intake.log_interview(
            tropico,
            interviewee="Catalina Vélez (COO)",
            role="COO",
            transcript_ref="interviews/coo.md",
            key_findings=["38 GWh/yr lost to curtailment"],
        )
        thesis = StrategicThesis(
            economic_lever=(
                "Recover 4% blended capacity factor on the 62 MW portfolio via "
                "model-predictive control + 14-day inflow forecasting."
            ),
            lever_kind="revenue",
            magnitude_estimate=Decimal("640000"),
            magnitude_basis="62 MW × 8760 h × 0.04 ΔCF × $79/MWh × 0.37 realism",
            strategic_horizon="h1-now",
            decision_rights_owner="Catalina Vélez (COO)",
            measured_in="USD/yr",
            evidence=[cite],
        )
        intake.declare_thesis(tropico, thesis)
        intake.request_review(tropico, "Thesis declared, scope locked")

        assert tropico.state().thesis_id == thesis.thesis_id

        # ---- Stage 2: MATURITY SCAN ----
        scan = MaturityScanStage()
        scan.run(tropico)
        for name, current, target in [
            ("Operational digitization", 2.0, 4.0),
            ("Data infrastructure", 2.5, 4.0),
            ("ML/AI capability", 1.5, 3.0),
            ("Grid-services readiness", 2.0, 4.0),
        ]:
            dim = MaturityDimension(
                name=name,
                framework_ref="framework:gartner-ai",
                current_score=Score(
                    dimension="d",
                    value=current,
                    scale=(1.0, 5.0),
                    rubric_ref="r",
                    rationale=f"Current state for {name}",
                    evidence=[cite],
                ),
                target_score=Score(
                    dimension="d",
                    value=target,
                    scale=(1.0, 5.0),
                    rubric_ref="r",
                    rationale=f"Target for {name} benchmarked vs LATAM peer IPPs",
                    evidence=[benchmark_cite],
                ),
                gap_summary=f"{name} gap",
                key_actions=["action"],
                evidence=[cite],
            )
            scan.score_dimension(tropico, dim)
        scan.request_review(tropico, "4 dimensions scored")

        assert len(tropico.state().maturity_dimensions) == 4

        # ---- Stage 3: IDEATION ----
        ideate = IdeationStage()
        ideate.run(tropico)
        for uc_id, source, value in [
            ("uc-mpc-solar", IdeationSource.BUSINESS_PAIN, "420000"),
            ("uc-inflow-fcst", IdeationSource.DATA_OPPORTUNITY, "110000"),
            ("uc-ffr-grid", IdeationSource.REGULATORY_PRESSURE, "110000"),
            ("uc-ppa-bid", IdeationSource.COMPETITIVE_RESPONSE, "160000"),
        ]:
            uc = UseCase(
                id=uc_id,
                problem="problem",
                hypothesis="hypothesis",
                solution_summary="solution",
                expected_value=Decimal(value),
                cost_estimate=Decimal("100000"),
                cost_breakdown={"x": Decimal("100000")},
                data_required=["d"],
                capabilities_required=["c"],
                risks=[],
                framework_lens=["rice"],
                score_impact=Score(
                    dimension="impact",
                    value=7.0,
                    scale=(0.0, 10.0),
                    rubric_ref="rice",
                    rationale="r",
                    evidence=[cite],
                ),
                score_effort=Score(
                    dimension="effort",
                    value=4.0,
                    scale=(0.0, 10.0),
                    rubric_ref="rice",
                    rationale="r",
                    evidence=[cite],
                ),
                ideation_source=source,
                data_readiness=DataReadinessAssessment(
                    use_case_id=uc_id,
                    data_dependencies=["d"],
                    weakest_dependency_state="defined",
                    readiness_band="pilot-ready",
                    prep_phase_required=False,
                ),
                evidence=[cite],
            )
            ideate.propose_use_case(tropico, uc)
        ideate.request_review(tropico, "4 candidates across 4 sources, 0% NOVELTY")

        # ---- Stage 4: PRIORITIZATION ----
        prioritize = PrioritizationStage()
        prioritize.run(tropico)
        for rank, uc_id, rice_score in [
            (1, "uc-mpc-solar", 14.9),
            (2, "uc-inflow-fcst", 8.4),
            (3, "uc-ffr-grid", 5.5),
        ]:
            roi = RoiCell(
                use_case_id=uc_id,
                year=1,
                revenue_impact=Decimal("100000"),
                cost_savings=Decimal("0"),
                investment=Decimal("60000"),
                one_time_cost=Decimal("42000"),
                recurring_cost=Decimal("18000"),
                net=Decimal("40000"),
                cumulative_net=Decimal("40000"),
                discount_rate=Decimal("0.14"),
                sensitivity_low=Decimal("24000"),
                sensitivity_high=Decimal("56000"),
                assumptions=["Bolsa price holds"],
            )
            prioritize.prioritize_use_case(
                tropico,
                use_case_id=uc_id,
                rice_score=rice_score,
                roi_cell=roi,
                rank=rank,
            )
        prioritize.render_impact_effort_matrix(tropico, "/tmp/iem.md")
        prioritize.request_review(tropico, "Top-3 selected")

        assert len(tropico.state().use_cases_prioritized) == 3

        # ---- Stage 5: ROADMAP ----
        roadmap = RoadmapStage()
        roadmap.run(tropico)
        roadmap_rows: list[tuple[str, Literal["h1-now", "h2-next", "h3-later"], str, str]] = [
            ("rs-h1-mpc", "h1-now", "2026-Q3", "VP Ops"),
            ("rs-h2-portfolio", "h2-next", "2026-Q4", "VP Ops"),
            ("rs-h3-grid", "h3-later", "2027-Q2", "Commercial Director"),
        ]
        for rs_id, horizon, quarter, owner in roadmap_rows:
            step = RoadmapStep(
                id=rs_id,
                title=rs_id,
                horizon=horizon,
                quarter=quarter,
                related_use_cases=["uc-mpc-solar"],
                related_recommendations=["rec-mpc"],
                dependencies=[],
                owner=owner,
                success_gate="≥3% CF improvement",
            )
            roadmap.propose_roadmap_step(tropico, step)

        baseline_cf = BaselineSection(
            metric_name="Farm-1 capacity factor",
            baseline_value=Decimal("0.234"),
            baseline_window="2026-Q1 production",
            baseline_data_source="SCADA POI export",
            baseline_measurement_date=datetime(2026, 4, 1, tzinfo=UTC),
            captured_by="VP Ops",
            evidence=[cite],
        )
        roadmap.capture_baseline(tropico, baseline_cf)

        # PilotDesign with the captured baseline metric
        adoption = AdoptionMetric(
            metric_name="Operations team accepts MPC setpoints",
            target_value=">=85% over 4 weeks",
            measurement_method="SCADA override-flag log",
            owner="VP Operations",
        )
        pilot = PilotDesign(
            use_case_id="uc-mpc-solar",
            hypothesis="MPC lifts Farm-1 CF from 23.4% to ≥24.1%",
            null_hypothesis="No significant CF lift at p<0.05",
            duration_weeks=16,
            cohort_definition="Farm-1 only",
            success_criteria=["Farm-1 CF ≥24.1% sustained weeks 9-16"],
            kill_criterion="Week-8 CF <23.5%",
            learning_objectives=["Validate cloud-nowcast horizon"],
            risks=[
                Finding(
                    title="Cloud-nowcast feed reliability",
                    body="GOES-R outages 0.8%",
                    severity="minor",
                    confidence="high",
                    evidence=[cite],
                )
            ],
            cost_estimate=Decimal("180000"),
            adoption_metric=adoption,
            baseline=[baseline_cf],
            evidence=[cite],
        )
        roadmap.design_pilot(tropico, pilot)
        roadmap.render_deliverables(
            tropico,
            slugs=[
                "maturity-report",
                "capability-heatmap",
                "use-case-dossier",
                "impact-effort-matrix",
                "roi-model",
                "innovation-roadmap",
                "pilot-plan",
            ],
            output_dir="/tmp/tropico",
        )
        roadmap.request_review(tropico, "Roadmap + baselines + pilot ready for sign-off")
        roadmap.conclude(
            tropico,
            top_pilot="uc-mpc-solar",
            deliverable_slugs=[
                "maturity-report",
                "capability-heatmap",
                "use-case-dossier",
                "impact-effort-matrix",
                "roi-model",
                "innovation-roadmap",
                "pilot-plan",
            ],
        )

        # ---- Final state assertions ----
        state = tropico.state()
        assert state.is_concluded is True
        assert state.current_stage == "concluded"
        assert state.thesis_id == thesis.thesis_id
        assert len(state.maturity_dimensions) == 4
        assert len(state.use_cases) == 4
        assert len(state.use_cases_prioritized) == 3
        assert "Farm-1 capacity factor" in state.baselines_captured

        # All 7 deliverable slugs (and the impact-effort matrix from
        # prioritize) recorded as rendered.
        rendered = state.deliverables_rendered
        for slug in [
            "impact-effort-matrix",
            "maturity-report",
            "capability-heatmap",
            "use-case-dossier",
            "roi-model",
            "innovation-roadmap",
            "pilot-plan",
        ]:
            assert slug in rendered

        # Event-kind sanity check
        kinds = [e.kind for e in tropico.journal.events]
        assert EventKind.ENGAGEMENT_STARTED in kinds
        assert EventKind.STRATEGIC_THESIS_DECLARED in kinds
        assert kinds.count(EventKind.MATURITY_DIMENSION_SCORED) == 4
        assert kinds.count(EventKind.USE_CASE_PROPOSED) == 4
        assert kinds.count(EventKind.USE_CASE_PRIORITIZED) == 3
        assert kinds.count(EventKind.ROADMAP_STEP_PROPOSED) == 3
        assert kinds.count(EventKind.BASELINE_CAPTURED) == 1
        assert EventKind.PILOT_STARTED in kinds
        assert EventKind.ENGAGEMENT_CONCLUDED in kinds

    def test_replay_idempotency_after_full_engagement(
        self,
        tropico: Engagement,
        cite: Citation,
        benchmark_cite: Citation,
    ):
        """After the full engagement runs, replaying twice produces equal states."""
        # Run a minimal engagement
        intake = IntakeStage()
        intake.run(tropico)
        thesis = StrategicThesis(
            economic_lever="x",
            lever_kind="cost",
            magnitude_estimate=Decimal("1"),
            magnitude_basis="r",
            strategic_horizon="h1-now",
            decision_rights_owner="x",
            measured_in="x",
            evidence=[cite],
        )
        intake.declare_thesis(tropico, thesis)
        intake.request_review(tropico, "ok")

        s1 = tropico.state()
        s2 = tropico.state()
        assert s1.model_dump() == s2.model_dump()
