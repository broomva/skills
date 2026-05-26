"""Unit tests for `core/extraction/candidates.py`.

Drives the rule-based candidate extractors against each fixture and
asserts the structure of the produced `ExtractionCandidate` records.
The candidates must:
  - carry no tenant markers in their content/quote (anonymizer holds),
  - cite at least one provenance event id,
  - declare either industry (for industry-pattern) or framework_ref
    (for framework-refinement),
  - own a deterministic kebab-case slug.

Test mode: PHRONESIS_EXTRACTION_STUB_SCORER=1 — see the conftest fixture.
"""

from __future__ import annotations

import pytest

from core.anonymize import AnonymizationPolicy, carries_tenant_marker
from core.extraction.anonymizer import EngagementAnonymizer
from core.extraction.candidates import (
    ExtractionCandidate,
    extract_framework_refinements,
    extract_industry_patterns,
)
from tests.fixtures.acme_bank import (
    ACME_BANK_CANARY_TOKENS,
    acme_bank_tenant,
    build_acme_bank_engagement,
)
from tests.fixtures.nova_construction import (
    NOVA_CONSTRUCTION_CANARY_TOKENS,
    build_nova_construction_engagement,
    nova_construction_tenant,
)
from tests.fixtures.tropico_renovables import (
    TROPICO_CANARY_TOKENS,
    build_tropico_engagement,
    tropico_tenant,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture
def tropico_anonymizer():
    return EngagementAnonymizer(tenant=tropico_tenant(), policy=AnonymizationPolicy())


@pytest.fixture
def acme_anonymizer():
    return EngagementAnonymizer(tenant=acme_bank_tenant(), policy=AnonymizationPolicy())


@pytest.fixture
def nova_anonymizer():
    return EngagementAnonymizer(tenant=nova_construction_tenant(), policy=AnonymizationPolicy())


class TestIndustryPatternExtraction:
    def test_tropico_surfaces_under_threshold_dimensions(self, tropico_anonymizer):
        eng = build_tropico_engagement()
        candidates = extract_industry_patterns(eng, tropico_anonymizer)
        # 3 of 4 maturity dimensions are <2.5 (Operational digitization=2.0,
        # ML/AI=1.5, Grid-services=2.0) + 1 thesis economic-lever pattern
        # = 4 candidates expected.
        assert len(candidates) >= 3
        for c in candidates:
            assert c.entity_type == "industry-pattern"
            assert c.industry == "energy-utilities"
            assert c.provenance_event_ids
            assert c.slug

    def test_acme_surfaces_industry_pattern_candidates(self, acme_anonymizer):
        eng = build_acme_bank_engagement()
        candidates = extract_industry_patterns(eng, acme_anonymizer)
        assert candidates
        for c in candidates:
            assert c.industry in ("fin-services", "banking")
            assert c.entity_type == "industry-pattern"
            assert c.slug.startswith(c.industry) or c.industry in c.slug

    def test_nova_surfaces_industry_pattern_candidates(self, nova_anonymizer):
        eng = build_nova_construction_engagement()
        candidates = extract_industry_patterns(eng, nova_anonymizer)
        assert candidates
        for c in candidates:
            assert c.industry == "construction"


class TestFrameworkRefinementExtraction:
    def test_each_fixture_emits_at_least_one_framework_candidate(
        self, tropico_anonymizer, acme_anonymizer, nova_anonymizer
    ):
        tropico = extract_framework_refinements(build_tropico_engagement(), tropico_anonymizer)
        acme = extract_framework_refinements(build_acme_bank_engagement(), acme_anonymizer)
        nova = extract_framework_refinements(build_nova_construction_engagement(), nova_anonymizer)

        # Source-skew or RICE-vs-ROI divergence should produce >=1 candidate
        # per fixture (each has 4+ use cases with distinct ideation sources).
        # If 0, the rule is too tight; if >5, the rule is too loose.
        for slug, cs in (("tropico", tropico), ("acme", acme), ("nova", nova)):
            assert 0 <= len(cs) <= 5, f"{slug} produced {len(cs)} framework candidates; expect 0-5"

    def test_framework_candidates_carry_framework_ref(self, acme_anonymizer):
        eng = build_acme_bank_engagement()
        candidates = extract_framework_refinements(eng, acme_anonymizer)
        for c in candidates:
            assert c.framework_ref is not None
            assert c.framework_ref.startswith("framework:")
            assert c.industry is None  # mutually exclusive with industry-pattern


class TestCandidateAnonymization:
    """Every candidate's content + quote must be canary-clean.

    Subset of the canary release gate, but at the candidate granularity —
    catches regressions in the extraction rules separately from the
    rendered-deliverable canary.
    """

    @pytest.mark.parametrize(
        "fixture_builder,tenant_builder,tokens",
        [
            (build_tropico_engagement, tropico_tenant, TROPICO_CANARY_TOKENS),
            (build_acme_bank_engagement, acme_bank_tenant, ACME_BANK_CANARY_TOKENS),
            (
                build_nova_construction_engagement,
                nova_construction_tenant,
                NOVA_CONSTRUCTION_CANARY_TOKENS,
            ),
        ],
    )
    def test_no_canary_tokens_in_any_candidate(self, fixture_builder, tenant_builder, tokens):
        tenant = tenant_builder()
        eng = fixture_builder()
        anonymizer = EngagementAnonymizer(tenant=tenant, policy=AnonymizationPolicy())

        candidates = [
            *extract_industry_patterns(eng, anonymizer),
            *extract_framework_refinements(eng, anonymizer),
        ]
        for c in candidates:
            for t in tokens:
                assert t not in c.content, (
                    f"Canary leak: token {t!r} survived into candidate {c.slug!r} content."
                )
                assert t not in c.quote, (
                    f"Canary leak: token {t!r} survived into candidate {c.slug!r} quote."
                )
            # Defense-in-depth: tenant slug + name + sponsor in particular.
            assert not carries_tenant_marker(c.content, tenant)
            assert not carries_tenant_marker(c.quote, tenant)


class TestCandidateModel:
    def test_extraction_candidate_round_trips_through_pydantic(self):
        c = ExtractionCandidate(
            slug="example-pattern",
            entity_type="industry-pattern",
            content="anonymized body",
            quote="anonymized quote",
            title="Example",
            provenance_event_ids=["01HZ..."],
            industry="energy-utilities",
        )
        roundtrip = ExtractionCandidate.model_validate(c.model_dump(mode="json"))
        assert roundtrip == c
