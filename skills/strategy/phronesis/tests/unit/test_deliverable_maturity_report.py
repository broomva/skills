"""Maturity Report deliverable — D.1 worked template.

Each Phase D deliverable test mirrors this shape:
  - context fixture (tenant + thesis + typed-primitive list)
  - test that render produces expected text
  - test that key fields propagate
  - test that missing-var raises UndefinedError (strict-undefined enforced)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from jinja2.exceptions import UndefinedError

from core.render import render
from core.types import (
    Citation,
    MaturityDimension,
    Score,
    StrategicThesis,
    TenantContext,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def context() -> dict[str, object]:
    cite = Citation(kind="evidence", ref="i:coo:Q2", confidence="high")
    bench = Citation(kind="evidence", ref="bench:peer-2025", confidence="medium")
    tenant = TenantContext(
        tenant_slug="tropico-renovables",
        name="Tropico Renovables S.A.S.",
        industry="energy-utilities",
        region="CO",
        revenue_band="<10M",
        headcount_band="50-500",
        sponsor="Catalina Vélez",
        sponsor_role="COO",
        engagement_scope="62 MW renewable portfolio",
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=10,
    )
    thesis = StrategicThesis(
        economic_lever="Recover 4% CF on 62 MW",
        lever_kind="revenue",
        magnitude_estimate=Decimal("640000"),
        magnitude_basis="62 MW × 8760 h × 0.04 ΔCF × $79/MWh × 0.37",
        strategic_horizon="h1-now",
        decision_rights_owner="Catalina Vélez (COO)",
        measured_in="USD/yr",
        evidence=[cite],
    )
    dim = MaturityDimension(
        name="Operational digitization",
        framework_ref="framework:gartner-ai",
        current_score=Score(
            dimension="ops",
            value=2.0,
            scale=(1.0, 5.0),
            rubric_ref="cisr",
            rationale="Open-loop dispatch",
            evidence=[cite],
        ),
        target_score=Score(
            dimension="ops",
            value=4.0,
            scale=(1.0, 5.0),
            rubric_ref="cisr",
            rationale="MPC-led benchmarked vs LATAM peer iPPs",
            evidence=[bench],
        ),
        gap_summary="Open-loop dispatch; needs MPC + forecast wiring",
        key_actions=["Stand up MPC test bench", "Wire 14-day forecast"],
        evidence=[cite],
    )
    return {
        "tenant": tenant,
        "thesis": thesis,
        "dimensions": [dim],
        "frameworks_applied": ["mit-cisr-digital", "gartner-ai", "rice"],
        "generated_at": "2026-05-07",
    }


class TestMaturityReportRender:
    def test_renders_without_error(self, context: dict[str, object]):
        out = render("maturity-report", context)
        assert "Maturity Report" in out
        assert "Tropico Renovables" in out

    def test_tenant_metadata_present(self, context: dict[str, object]):
        out = render("maturity-report", context)
        assert "tropico-renovables" in out
        assert "Catalina Vélez" in out
        assert "COO" in out
        assert "energy-utilities" in out

    def test_thesis_appears_verbatim(self, context: dict[str, object]):
        out = render("maturity-report", context)
        assert "Recover 4% CF on 62 MW" in out
        assert "$640,000" in out  # magnitude formatted via as_currency
        assert "h1-now" in out
        assert "Catalina Vélez (COO)" in out

    def test_dimensions_rendered(self, context: dict[str, object]):
        out = render("maturity-report", context)
        assert "Operational digitization" in out
        assert "Stand up MPC test bench" in out
        assert "2.0" in out and "4.0" in out

    def test_frameworks_applied_listed(self, context: dict[str, object]):
        out = render("maturity-report", context)
        # join(", ") produces "mit-cisr-digital, gartner-ai, rice"
        assert "mit-cisr-digital, gartner-ai, rice" in out

    def test_strict_undefined_raises_on_missing(self, context: dict[str, object]):
        bad = {**context}
        del bad["thesis"]
        with pytest.raises(UndefinedError):
            render("maturity-report", bad)

    def test_strict_undefined_raises_on_missing_dimensions(self, context: dict[str, object]):
        bad = {**context}
        del bad["dimensions"]
        with pytest.raises(UndefinedError):
            render("maturity-report", bad)

    def test_p3_invariant_footer_present(self, context: dict[str, object]):
        out = render("maturity-report", context)
        assert "P3 ✓" in out
        assert "P7 ✓" in out
