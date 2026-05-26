"""Unit tests for Layer 4 (StageReview) + Layer 5 (TenantContext, FrameworkSelection)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.types import (
    FrameworkSelection,
    StageReview,
    TenantContext,
)

pytestmark = pytest.mark.unit


class TestStageReview:
    def test_pending_review(self):
        r = StageReview(
            stage="intake",
            summary="Stakeholder map + data request list ready.",
            artifacts=["engagements/acme-bank/findings/intake-summary.md"],
            open_questions=["Is the CDO the right sponsor?"],
            proposed_next_actions=["Run maturity scan with MIT CISR + Gartner AI"],
        )
        assert r.decision is None
        assert r.reviewer is None

    def test_approved_review(self):
        r = StageReview(
            stage="intake",
            summary="Approved.",
            artifacts=[],
            open_questions=[],
            proposed_next_actions=[],
            reviewer="Carolina Pérez",
            decision="approved",
            reviewer_notes="Looks good.",
            reviewed_at=datetime(2026, 5, 7, tzinfo=UTC),
        )
        assert r.decision == "approved"

    def test_invalid_stage_rejected(self):
        with pytest.raises(ValidationError):
            StageReview(
                stage="not-a-stage",  # type: ignore[arg-type]
                summary="x",
                artifacts=[],
                open_questions=[],
                proposed_next_actions=[],
            )


class TestTenantContext:
    def test_tenant_context(self):
        t = TenantContext(
            tenant_slug="acme-bank",
            name="Acme Bank",
            industry="banking",
            region="CO",
            revenue_band="100M-1B",
            headcount_band="500-5000",
            sponsor="Carolina Pérez",
            sponsor_role="CDO",
            engagement_scope="AI maturity + Tier-1 ticket deflection — 8-week pilot",
            starts_at=datetime(2026, 5, 6, tzinfo=UTC),
            target_duration_weeks=8,
        )
        assert t.industry == "banking"
        assert t.region == "CO"

    def test_energy_utilities_industry(self):
        # Engagement-driven addition (Tropico Renovables synthetic, 2026-05-06):
        # renewable IPPs / utilities don't fit any prior literal. Verify the
        # variant is accepted so framework_selector (M1) can key on it.
        t = TenantContext(
            tenant_slug="tropico-renovables",
            name="Tropico Renovables S.A.S.",
            industry="energy-utilities",
            region="CO",
            revenue_band="<10M",
            headcount_band="50-500",
            sponsor="Catalina Vélez",
            sponsor_role="COO",
            engagement_scope="62 MW renewable portfolio control-engineering uplift",
            starts_at=datetime(2026, 5, 6, tzinfo=UTC),
            target_duration_weeks=10,
        )
        assert t.industry == "energy-utilities"

    def test_tech_industry(self):
        # Engagement-driven addition (Broomva Silicon synthetic, 2026-05-07):
        # AI-infra / runtime / library / chip-design tenants don't fit any
        # prior literal. BRO-1031. Unblocks framework_selector tech preference
        # map (BRO-1032) and CHAOSS framework selection (BRO-1033).
        t = TenantContext(
            tenant_slug="broomva-silicon",
            name="Broomva Silicon",
            industry="tech",
            region="US",
            revenue_band="<10M",
            headcount_band="<50",
            sponsor="Carlos Escobar",
            sponsor_role="Founder/CEO",
            engagement_scope="Spec E agent-loop runtime + multi-backend fan-out",
            starts_at=datetime(2026, 5, 7, tzinfo=UTC),
            target_duration_weeks=2,
        )
        assert t.industry == "tech"


class TestFrameworkSelection:
    def test_selection(self):
        s = FrameworkSelection(
            framework_ref="frameworks/maturity/mit-cisr-digital.yaml",
            selected_at_stage="intake",
            rationale="Industry-standard digital maturity; familiar to enterprise IT leadership.",
            selected_by="Carlos Escobar",
        )
        assert s.framework_ref.endswith(".yaml")
