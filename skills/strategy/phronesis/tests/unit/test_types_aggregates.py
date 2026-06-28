"""Unit tests for Layer 2 deliverable aggregates."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from core.types import (
    AdoptionMetric,
    BaselineSection,
    CapabilityCell,
    Citation,
    DataReadinessAssessment,
    IdeationSource,
    MaturityDimension,
    PilotDesign,
    RoadmapStep,
    RoiCell,
    Score,
    UseCase,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def cite() -> Citation:
    return Citation(kind="evidence", ref="interview:cfo:Q3", confidence="high")


@pytest.fixture
def adoption() -> AdoptionMetric:
    return AdoptionMetric(
        metric_name="reps using assist",
        target_value=">=40% by week 6",
        measurement_method="UI telemetry",
        owner="Head of CS",
    )


@pytest.fixture
def baseline(cite: Citation) -> BaselineSection:
    return BaselineSection(
        metric_name="ticket volume",
        baseline_value=Decimal("11700"),
        baseline_window="30-day rolling avg",
        baseline_data_source="Ticketing audit log",
        baseline_measurement_date=datetime(2026, 5, 6, tzinfo=UTC),
        captured_by="CDO",
        evidence=[cite],
    )


# ---- UseCase ----------------------------------------------------------------


class TestUseCase:
    def test_use_case_construction(self, cite: Citation):
        uc = UseCase(
            id="uc-001",
            problem="Tier-1 ticket cost is high; manual triage breaches SLA.",
            hypothesis="Spanish-LLM deflection cuts cost 30%+.",
            solution_summary="Wire Claude to a deflection workflow for password resets and balance inquiries.",
            expected_value=Decimal("400000"),
            cost_estimate=Decimal("160000"),
            cost_breakdown={
                "build": Decimal("80000"),
                "platform": Decimal("42000"),
                "ops": Decimal("38000"),
            },
            data_required=["ticket-history", "rep-actions"],
            capabilities_required=["LLM-spanish-routing", "real-time-data-pipeline"],
            risks=[],
            framework_lens=["jtbd", "rice"],
            score_impact=Score(
                dimension="impact",
                value=2.0,
                scale=(0.0, 3.0),
                rubric_ref="rice",
                rationale="high per-ticket impact",
                evidence=[cite],
            ),
            score_effort=Score(
                dimension="effort",
                value=3.0,
                scale=(0.5, 12.0),
                rubric_ref="rice",
                rationale="3 person-months",
                evidence=[cite],
            ),
            ideation_source=IdeationSource.BUSINESS_PAIN,
            data_readiness=DataReadinessAssessment(
                use_case_id="uc-001",
                data_dependencies=["cap-data-001"],
                weakest_dependency_state="defined",
                readiness_band="needs-prep",
                prep_phase_required=True,
                prep_phase_estimated_weeks=4,
                prep_phase_owner="Lead Data Engineer",
            ),
            evidence=[cite],
        )
        assert uc.ideation_source == IdeationSource.BUSINESS_PAIN
        assert uc.expected_value == Decimal("400000")
        assert uc.status == "proposed"
        assert uc.status_rationale is None

    def _minimal_uc_kwargs(self, cite: Citation) -> dict[str, Any]:
        return dict(
            id="uc-001",
            problem="p",
            hypothesis="h",
            solution_summary="s",
            expected_value=Decimal("1"),
            cost_estimate=Decimal("1"),
            cost_breakdown={"x": Decimal("1")},
            data_required=[],
            capabilities_required=[],
            risks=[],
            framework_lens=["rice"],
            score_impact=Score(
                dimension="impact",
                value=1.0,
                scale=(0.0, 10.0),
                rubric_ref="r",
                rationale="r",
                evidence=[cite],
            ),
            score_effort=Score(
                dimension="effort",
                value=1.0,
                scale=(0.0, 10.0),
                rubric_ref="r",
                rationale="r",
                evidence=[cite],
            ),
            ideation_source=IdeationSource.BUSINESS_PAIN,
            data_readiness=DataReadinessAssessment(
                use_case_id="uc-001",
                data_dependencies=["d"],
                weakest_dependency_state="defined",
                readiness_band="pilot-ready",
                prep_phase_required=False,
            ),
            evidence=[cite],
        )

    def test_dropped_use_case_requires_rationale(self, cite: Citation):
        kwargs = self._minimal_uc_kwargs(cite)
        kwargs["status"] = "dropped"
        with pytest.raises(ValidationError, match="status_rationale"):
            UseCase(**kwargs)

    def test_deferred_use_case_requires_rationale(self, cite: Citation):
        kwargs = self._minimal_uc_kwargs(cite)
        kwargs["status"] = "deferred"
        with pytest.raises(ValidationError, match="status_rationale"):
            UseCase(**kwargs)

    def test_dropped_with_rationale_accepted(self, cite: Citation):
        kwargs = self._minimal_uc_kwargs(cite)
        kwargs["status"] = "dropped"
        kwargs["status_rationale"] = "Too small (<$30k value); COO killed at prioritization gate."
        uc = UseCase(**kwargs)
        assert uc.status == "dropped"
        assert uc.status_rationale is not None


# ---- MaturityDimension ------------------------------------------------------


class TestMaturityDimension:
    def test_maturity_dimension_construction(self, cite: Citation):
        md = MaturityDimension(
            name="Data Architecture",
            framework_ref="frameworks/maturity/mit-cisr-digital.yaml",
            current_score=Score(
                dimension="data-architecture",
                value=2.0,
                scale=(0.0, 4.0),
                rubric_ref="mit-cisr",
                rationale="Silos and Spaghetti",
                evidence=[cite],
            ),
            target_score=Score(
                dimension="data-architecture",
                value=3.0,
                scale=(0.0, 4.0),
                rubric_ref="mit-cisr",
                rationale="Optimized Core target",
                evidence=[cite],
            ),
            gap_summary="Move from siloed ETL to a governed core data layer.",
            key_actions=[
                "Establish data-product owners",
                "Standardize schemas across LOBs",
            ],
            evidence=[cite],
        )
        assert md.current_score.value == 2.0

    def test_target_score_evidence_required(self, cite: Citation):
        # Target without evidence is wishful thinking — must reject.
        with pytest.raises(ValidationError, match="target_score.evidence is\\s+empty"):
            MaturityDimension(
                name="Data Architecture",
                framework_ref="frameworks/maturity/mit-cisr-digital.yaml",
                current_score=Score(
                    dimension="d",
                    value=2.0,
                    scale=(0.0, 4.0),
                    rubric_ref="r",
                    rationale="r",
                    evidence=[cite],
                ),
                target_score=Score(
                    dimension="d",
                    value=3.0,
                    scale=(0.0, 4.0),
                    rubric_ref="r",
                    rationale="r",
                    evidence=[],
                ),
                gap_summary="g",
                key_actions=[],
                evidence=[cite],
            )

    def test_current_score_evidence_required(self, cite: Citation):
        with pytest.raises(ValidationError, match="current_score.evidence is\\s+empty"):
            MaturityDimension(
                name="x",
                framework_ref="r",
                current_score=Score(
                    dimension="d",
                    value=2.0,
                    scale=(0.0, 4.0),
                    rubric_ref="r",
                    rationale="r",
                    evidence=[],
                ),
                target_score=Score(
                    dimension="d",
                    value=3.0,
                    scale=(0.0, 4.0),
                    rubric_ref="r",
                    rationale="r",
                    evidence=[cite],
                ),
                gap_summary="g",
                key_actions=[],
                evidence=[cite],
            )


# ---- CapabilityCell ---------------------------------------------------------


class TestCapabilityCell:
    def test_cell_construction(self, cite: Citation):
        c = CapabilityCell(
            capability="Real-time data ingestion",
            category="data",
            current_state="ad-hoc",
            target_state="managed",
            criticality="foundational",
            evidence=[cite],
        )
        assert c.category == "data"


# ---- RoiCell ----------------------------------------------------------------


class TestRoiCell:
    def test_roi_cell_construction(self):
        cell = RoiCell(
            use_case_id="uc-001",
            year=1,
            revenue_impact=Decimal("0"),
            cost_savings=Decimal("400000"),
            investment=Decimal("160000"),
            one_time_cost=Decimal("80000"),
            recurring_cost=Decimal("80000"),
            net=Decimal("240000"),
            cumulative_net=Decimal("240000"),
            discount_rate=Decimal("0.10"),
            sensitivity_low=Decimal("80000"),
            sensitivity_high=Decimal("420000"),
            assumptions=["35% deflection rate sustains", "Spanish LLM stable cost-per-call"],
        )
        assert cell.net == Decimal("240000")


# ---- RoadmapStep ------------------------------------------------------------


class TestRoadmapStep:
    def test_roadmap_step_construction(self):
        s = RoadmapStep(
            id="rs-001",
            title="Pilot Tier-1 Spanish deflection",
            horizon="h1-now",
            quarter="2026-Q3",
            related_use_cases=["uc-001"],
            related_recommendations=["rec-001"],
            dependencies=[],
            owner="Carolina Pérez (CDO)",
            success_gate=">=35% deflection sustained over 4 weeks",
        )
        assert s.horizon == "h1-now"


# ---- PilotDesign (L4 + L5 enforcement) --------------------------------------


class TestPilotDesign:
    def _build(
        self, cite: Citation, adoption: AdoptionMetric, baseline: BaselineSection
    ) -> dict[str, Any]:
        return {
            "use_case_id": "uc-001",
            "hypothesis": "Spanish-LLM deflection lifts efficiency 30%+.",
            "null_hypothesis": "Deflection rate < 15% indicates the approach fails.",
            "duration_weeks": 8,
            "cohort_definition": "Internal CS reps for Tier-1 tickets in Spanish.",
            "success_criteria": [
                ">=35% deflection by week 8",
                "CSAT does not drop > 5pts",
            ],
            "kill_criterion": "<15% deflection by week 4 OR CSAT drop > 5pts",
            "learning_objectives": [
                "Validate deflection rate in Spanish",
                "Measure rep adoption velocity",
            ],
            "risks": [],
            "cost_estimate": Decimal("80000"),
            "adoption_metric": adoption,
            "baseline": [baseline],
            "evidence": [cite],
        }

    def test_pilot_design_construction(
        self, cite: Citation, adoption: AdoptionMetric, baseline: BaselineSection
    ):
        p = PilotDesign(**self._build(cite, adoption, baseline))
        assert p.duration_weeks == 8

    def test_pilot_requires_baseline_L5(
        self, cite: Citation, adoption: AdoptionMetric, baseline: BaselineSection
    ):
        kwargs = self._build(cite, adoption, baseline)
        kwargs["baseline"] = []
        with pytest.raises(ValidationError, match="baseline"):
            PilotDesign(**kwargs)

    def test_pilot_requires_adoption_metric_L4(
        self, cite: Citation, adoption: AdoptionMetric, baseline: BaselineSection
    ):
        kwargs = self._build(cite, adoption, baseline)
        del kwargs["adoption_metric"]
        with pytest.raises(ValidationError, match="adoption_metric"):
            PilotDesign(**kwargs)
