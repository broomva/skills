"""Unit tests for core.anonymize — the redaction primitives."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.anonymize import (
    AnonymizationPolicy,
    _currency_band,
    anonymize,
    carries_tenant_marker,
)
from core.types import TenantContext

pytestmark = pytest.mark.unit


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(
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


@pytest.fixture
def strict_policy() -> AnonymizationPolicy:
    return AnonymizationPolicy()


# ----------------------------------------------------------------------------
# Currency banding
# ----------------------------------------------------------------------------


class TestCurrencyBand:
    def test_low_5_figures(self):
        assert _currency_band(Decimal("12345")) == "mid-5-figures USD"

    def test_low_6_figures(self):
        assert _currency_band(Decimal("640000")) == "low-6-figures USD"

    def test_low_7_figures(self):
        assert _currency_band(Decimal("4500000")) == "low-7-figures USD"


# ----------------------------------------------------------------------------
# Tenant slug + name stripping
# ----------------------------------------------------------------------------


class TestTenantStripping:
    def test_strips_tenant_slug(self, tenant: TenantContext, strict_policy: AnonymizationPolicy):
        text = "Engagement: tropico-renovables started in 2026"
        out = anonymize(text, strict_policy, tenant)
        assert "tropico-renovables" not in out
        assert "<tenant>" in out

    def test_strips_tenant_name(self, tenant: TenantContext, strict_policy: AnonymizationPolicy):
        text = "Tropico Renovables S.A.S. operates 62 MW"
        out = anonymize(text, strict_policy, tenant)
        assert "Tropico Renovables S.A.S." not in out

    def test_opt_out_keeps_tenant_slug(self, tenant: TenantContext):
        text = "tropico-renovables"
        policy = AnonymizationPolicy(strip_tenant_slug=False)
        out = anonymize(text, policy, tenant)
        assert "tropico-renovables" in out


# ----------------------------------------------------------------------------
# Personal-name redaction
# ----------------------------------------------------------------------------


class TestPersonalNames:
    def test_sponsor_name_explicit_strip(
        self, tenant: TenantContext, strict_policy: AnonymizationPolicy
    ):
        text = "Sponsor: Catalina Vélez (COO) approved the thesis."
        out = anonymize(text, strict_policy, tenant)
        assert "Catalina Vélez" not in out
        assert "<person>" in out

    def test_two_word_capitalized_redacted(
        self, tenant: TenantContext, strict_policy: AnonymizationPolicy
    ):
        text = "Maria Rodriguez and Juan Pérez attended."
        out = anonymize(text, strict_policy, tenant)
        assert "Maria Rodriguez" not in out
        assert "Juan Pérez" not in out

    def test_framework_names_in_allowlist_preserved(
        self, tenant: TenantContext, strict_policy: AnonymizationPolicy
    ):
        text = "Frameworks applied: Three Horizons, Wardley Mapping, MIT CISR."
        out = anonymize(text, strict_policy, tenant)
        # These ARE multi-word capitalized but they're framework names,
        # not personal names — keep them.
        assert "Three Horizons" in out
        assert "Wardley Mapping" in out
        assert "MIT CISR" in out


# ----------------------------------------------------------------------------
# Currency banding in text
# ----------------------------------------------------------------------------


class TestCurrencyInText:
    def test_dollar_amount_replaced_with_band(
        self, tenant: TenantContext, strict_policy: AnonymizationPolicy
    ):
        text = "Year-1 net was $640,000 against $180,000 investment."
        out = anonymize(text, strict_policy, tenant)
        assert "$640,000" not in out
        assert "$180,000" not in out
        assert "low-6-figures USD" in out

    def test_dollar_with_M_suffix(self, tenant: TenantContext, strict_policy: AnonymizationPolicy):
        text = "Magnitude: $4.5M revenue lever."
        out = anonymize(text, strict_policy, tenant)
        assert "$4.5M" not in out
        assert "low-7-figures USD" in out


# ----------------------------------------------------------------------------
# Date replacement
# ----------------------------------------------------------------------------


class TestDateReplacement:
    def test_iso_date_replaced(self, tenant: TenantContext, strict_policy: AnonymizationPolicy):
        text = "Baseline measured 2026-04-01."
        out = anonymize(text, strict_policy, tenant)
        assert "2026-04-01" not in out
        assert "<engagement-date>" in out

    def test_quarter_replaced(self, tenant: TenantContext, strict_policy: AnonymizationPolicy):
        text = "Pilot starts 2026-Q3."
        out = anonymize(text, strict_policy, tenant)
        assert "2026-Q3" not in out
        assert "<engagement-quarter>" in out


# ----------------------------------------------------------------------------
# Location replacement
# ----------------------------------------------------------------------------


class TestLocationReplacement:
    def test_co_city_replaced(self, tenant: TenantContext, strict_policy: AnonymizationPolicy):
        text = "Operations centered in Bogotá and Cartagena."
        out = anonymize(text, strict_policy, tenant)
        assert "Bogotá" not in out
        assert "Cartagena" not in out
        assert "<latam-region>" in out


# ----------------------------------------------------------------------------
# Caller-supplied redact_terms
# ----------------------------------------------------------------------------


class TestRedactTerms:
    def test_arbitrary_terms_replaced(self, tenant: TenantContext):
        policy = AnonymizationPolicy(redact_terms=["TopSecret-Project-X", "internal-codename-foo"])
        text = "Internal: TopSecret-Project-X uses internal-codename-foo."
        out = anonymize(text, policy, tenant)
        assert "TopSecret-Project-X" not in out
        assert "internal-codename-foo" not in out
        assert "<redacted>" in out


# ----------------------------------------------------------------------------
# Forensic carries_tenant_marker helper
# ----------------------------------------------------------------------------


class TestCarriesTenantMarker:
    def test_clean_text_returns_empty(self, tenant: TenantContext):
        assert carries_tenant_marker("nothing here", tenant) == []

    def test_finds_tenant_slug_leak(self, tenant: TenantContext):
        markers = carries_tenant_marker("see tropico-renovables for details", tenant)
        assert any("tenant_slug" in m for m in markers)

    def test_finds_sponsor_name_leak(self, tenant: TenantContext):
        markers = carries_tenant_marker("Catalina Vélez signed off", tenant)
        assert any("sponsor" in m for m in markers)
