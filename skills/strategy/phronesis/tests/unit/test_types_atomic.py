"""Unit tests for Layer 1 atomic primitives in core.types.

Each test maps to a principle (P3, P8) or a Bision-failure linter rule (L1-L5).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from core.types import (
    AdoptionMetric,
    BaselineSection,
    Citation,
    DataReadinessAssessment,
    Finding,
    IdeationSource,
    Recommendation,
    Score,
    StrategicThesis,
)

pytestmark = pytest.mark.unit


# ---- Citation ---------------------------------------------------------------


class TestCitation:
    def test_evidence_citation_round_trip(self, sample_citation_kwargs):
        c = Citation(**sample_citation_kwargs)
        assert c.kind == "evidence"
        assert c.confidence == "high"

    def test_framework_citation(self):
        c = Citation(kind="framework", ref="framework:rice", confidence="high", excerpt=None)
        assert c.kind == "framework"

    def test_entity_citation(self):
        c = Citation(kind="entity", ref="entity:concept/jtbd", confidence="medium", excerpt=None)
        assert c.kind == "entity"

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            Citation(kind="hearsay", ref="someone said", confidence="low")  # type: ignore[arg-type]

    def test_invalid_confidence_rejected(self):
        with pytest.raises(ValidationError):
            Citation(kind="evidence", ref="x", confidence="absolute")  # type: ignore[arg-type]


# ---- Score ------------------------------------------------------------------


class TestScore:
    def test_score_construction(self, sample_citation_kwargs):
        s = Score(
            dimension="data-readiness",
            value=2.5,
            scale=(0.0, 5.0),
            rubric_ref="frameworks/maturity/mit-cisr-digital.yaml",
            rationale="Data lakes exist but no governance.",
            evidence=[Citation(**sample_citation_kwargs)],
        )
        assert s.value == 2.5

    def test_score_evidence_can_be_empty(self):
        s = Score(
            dimension="x",
            value=1.0,
            scale=(0.0, 5.0),
            rubric_ref="r",
            rationale="r",
            evidence=[],
        )
        assert s.evidence == []

    def test_score_value_must_be_within_scale(self):
        # Out-of-range above hi
        with pytest.raises(ValidationError, match="outside scale"):
            Score(dimension="x", value=11.0, scale=(0.0, 10.0), rubric_ref="r", rationale="r")
        # Out-of-range below lo
        with pytest.raises(ValidationError, match="outside scale"):
            Score(dimension="x", value=-0.1, scale=(0.0, 10.0), rubric_ref="r", rationale="r")
        # Boundary cases (inclusive) accepted
        Score(dimension="x", value=0.0, scale=(0.0, 10.0), rubric_ref="r", rationale="r")
        Score(dimension="x", value=10.0, scale=(0.0, 10.0), rubric_ref="r", rationale="r")

    def test_score_scale_must_be_ordered(self):
        with pytest.raises(ValidationError, match="lo < hi"):
            Score(dimension="x", value=1.0, scale=(5.0, 5.0), rubric_ref="r", rationale="r")
        with pytest.raises(ValidationError, match="lo < hi"):
            Score(dimension="x", value=1.0, scale=(10.0, 0.0), rubric_ref="r", rationale="r")


# ---- Finding (P3 enforcement) -----------------------------------------------


class TestFinding:
    def test_finding_with_evidence(self, sample_citation_kwargs):
        f = Finding(
            title="Tier-1 SLA breached 3x in Q1",
            body="Audit logs show 3 SLA breaches in Q1 driven by manual triage.",
            severity="major",
            confidence="high",
            evidence=[Citation(**sample_citation_kwargs)],
        )
        assert f.severity == "major"

    def test_finding_without_evidence_rejected_P3(self):
        with pytest.raises(ValidationError, match="evidence"):
            Finding(
                title="x",
                body="y",
                severity="major",
                confidence="high",
                evidence=[],
            )


# ---- Recommendation (P8 + L4 enforcement) -----------------------------------


class TestRecommendation:
    def _build_kwargs(self, sample_citation_kwargs: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": "Deploy Spanish Tier-1 deflection chatbot",
            "description": "Wire Claude through a Tier-1 deflection workflow targeting password resets and balance inquiries.",
            "value": Decimal("82000"),
            "value_basis": "12K tickets/mo x 35% deflection x $4.20 cost/ticket x 12mo, less platform $42K",
            "value_currency": "USD",
            "owner": "Carolina Pérez (CDO)",
            "timeline_weeks": 12,
            "success_metric": "Tier-1 ticket-volume reaching human agent",
            "success_target": ">=35% deflection by week 8",
            "kill_criterion": "<15% deflection by week 4 OR CSAT drop > 5pts",
            "adoption_metric": AdoptionMetric(
                metric_name="weekly active CS reps using the AI assist surface",
                target_value=">=40% by week 6",
                measurement_method="UI telemetry tagged by rep role",
                owner="Head of Customer Service",
            ),
            "evidence": [Citation(**sample_citation_kwargs)],
        }

    def test_recommendation_round_trip(self, sample_citation_kwargs):
        r = Recommendation(**self._build_kwargs(sample_citation_kwargs))
        assert r.value == Decimal("82000")

    def test_recommendation_requires_value_P8(self, sample_citation_kwargs):
        kwargs = self._build_kwargs(sample_citation_kwargs)
        del kwargs["value"]
        with pytest.raises(ValidationError, match="value"):
            Recommendation(**kwargs)

    def test_recommendation_requires_owner_P8(self, sample_citation_kwargs):
        kwargs = self._build_kwargs(sample_citation_kwargs)
        del kwargs["owner"]
        with pytest.raises(ValidationError, match="owner"):
            Recommendation(**kwargs)

    def test_recommendation_requires_kill_criterion_P8(self, sample_citation_kwargs):
        kwargs = self._build_kwargs(sample_citation_kwargs)
        del kwargs["kill_criterion"]
        with pytest.raises(ValidationError, match="kill_criterion"):
            Recommendation(**kwargs)

    def test_recommendation_requires_adoption_metric_L4(self, sample_citation_kwargs):
        """L4: ADOPTION_METRIC_REQUIRED — kills Bision Failure 4 (61% observed)."""
        kwargs = self._build_kwargs(sample_citation_kwargs)
        del kwargs["adoption_metric"]
        with pytest.raises(ValidationError, match="adoption_metric"):
            Recommendation(**kwargs)


# ---- IdeationSource enum (L2 support) ---------------------------------------


class TestIdeationSource:
    def test_all_five_sources(self):
        assert IdeationSource.BUSINESS_PAIN.value == "business-pain"
        assert IdeationSource.DATA_OPPORTUNITY.value == "data-opportunity"
        assert IdeationSource.REGULATORY_PRESSURE.value == "regulatory-pressure"
        assert IdeationSource.COMPETITIVE_RESPONSE.value == "competitive-response"
        assert IdeationSource.NOVELTY.value == "novelty"


# ---- AdoptionMetric (L4 support) --------------------------------------------


class TestAdoptionMetric:
    def test_adoption_metric_construction(self):
        a = AdoptionMetric(
            metric_name="weekly active users",
            target_value=">=40% by week 6",
            measurement_method="UI telemetry tagged by user role",
            owner="Head of Customer Service",
        )
        assert a.target_value == ">=40% by week 6"


# ---- BaselineSection (L5 support) -------------------------------------------


class TestBaselineSection:
    def test_baseline_section_construction(self, sample_citation_kwargs):
        b = BaselineSection(
            metric_name="Tier-1 ticket volume reaching human agent",
            baseline_value=Decimal("11700"),
            baseline_window="30-day rolling avg pre-pilot",
            baseline_data_source="Ticketing system audit log",
            baseline_measurement_date=datetime(2026, 5, 6, tzinfo=UTC),
            captured_by="Carolina Pérez (CDO)",
            evidence=[Citation(**sample_citation_kwargs)],
        )
        assert b.baseline_value == Decimal("11700")
        # Default: not greenfield
        assert b.is_greenfield is False

    def test_greenfield_baseline_explicit(self, sample_citation_kwargs):
        # BRO-1034 — greenfield pilots declare zero-state explicitly. baseline_value
        # is still required (Decimal('0') canonical) so renderers + downstream
        # tooling have a numeric value to work with. is_greenfield=True is the
        # marker that distinguishes 'we have zero traffic today' from 'we measured
        # zero traffic today'.
        b = BaselineSection(
            metric_name="vLLM-backend tokens/sec on reference workload",
            baseline_value=Decimal("0"),
            baseline_window="2026-Q2 baseline (zero-state — no production backend)",
            baseline_data_source="Pre-engagement assessment",
            baseline_measurement_date=datetime(2026, 5, 7, tzinfo=UTC),
            captured_by="Carlos Escobar (Founder/CEO)",
            evidence=[Citation(**sample_citation_kwargs)],
            is_greenfield=True,
        )
        assert b.is_greenfield is True
        assert b.baseline_value == Decimal("0")
        # The metric_name + baseline_window are where the operator declares
        # the greenfield framing in human-readable form
        assert "zero-state" in b.baseline_window


# ---- StrategicThesis (L1 support) -------------------------------------------


class TestStrategicThesis:
    def test_strategic_thesis_construction(self, sample_citation_kwargs):
        t = StrategicThesis(
            economic_lever="Reduce Tier-1 ticket cost via Spanish-LLM deflection",
            lever_kind="cost",
            magnitude_estimate=Decimal("400000"),
            magnitude_basis="12K tickets/mo x $8/ticket x 35% deflection x 12mo",
            strategic_horizon="h1-now",
            decision_rights_owner="Carolina Pérez (CDO)",
            measured_in="$ saved per year",
            evidence=[Citation(**sample_citation_kwargs)],
        )
        assert t.lever_kind == "cost"

    def test_strategic_thesis_requires_evidence_P3(self):
        with pytest.raises(ValidationError, match="evidence"):
            StrategicThesis(
                economic_lever="x",
                lever_kind="cost",
                magnitude_estimate=Decimal("1"),
                magnitude_basis="r",
                strategic_horizon="h1-now",
                decision_rights_owner="x",
                measured_in="x",
                evidence=[],
            )

    def test_strategic_thesis_id_auto_generated(self, sample_citation_kwargs):
        # thesis_id auto-generates so journal events can stably reference the
        # thesis even after revisions. ULID = 26-char Crockford base32.
        t = StrategicThesis(
            economic_lever="x",
            lever_kind="cost",
            magnitude_estimate=Decimal("1"),
            magnitude_basis="r",
            strategic_horizon="h1-now",
            decision_rights_owner="x",
            measured_in="x",
            evidence=[Citation(**sample_citation_kwargs)],
        )
        assert isinstance(t.thesis_id, str)
        assert len(t.thesis_id) == 26
        # Two theses constructed in succession must have distinct ids.
        t2 = StrategicThesis(
            economic_lever="y",
            lever_kind="cost",
            magnitude_estimate=Decimal("1"),
            magnitude_basis="r",
            strategic_horizon="h1-now",
            decision_rights_owner="x",
            measured_in="x",
            evidence=[Citation(**sample_citation_kwargs)],
        )
        assert t2.thesis_id != t.thesis_id


# ---- DataReadinessAssessment (L3 support) -----------------------------------


class TestDataReadinessAssessment:
    def test_pilot_ready(self):
        d = DataReadinessAssessment(
            use_case_id="uc-001",
            data_dependencies=["cap-001"],
            weakest_dependency_state="managed",
            readiness_band="pilot-ready",
            prep_phase_required=False,
            prep_phase_estimated_weeks=None,
            prep_phase_owner=None,
        )
        assert d.readiness_band == "pilot-ready"

    def test_blocking_requires_prep(self):
        d = DataReadinessAssessment(
            use_case_id="uc-001",
            data_dependencies=["cap-001"],
            weakest_dependency_state="absent",
            readiness_band="blocking",
            prep_phase_required=True,
            prep_phase_estimated_weeks=12,
            prep_phase_owner="Lead Data Engineer",
        )
        assert d.prep_phase_required is True
