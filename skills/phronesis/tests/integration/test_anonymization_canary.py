"""Anonymization canary — RELEASE GATE.

Drives every fixture engagement through `render_all`, then runs every
rendered deliverable through `anonymize()`, and asserts that ZERO
tenant-identifying markers leak into the output.

M6 extended the canary from a single Tropico Renovables check to a
3-fixture matrix — Tropico (energy-utilities) + Acme Bank (financial
services) + Nova Construction (construction). Each fixture ships its own
canary-token list. A leak in ANY fixture blocks the push: tenant data
leaking through anonymization is a release-gate failure regardless of
which engagement it came from.

If this test fails, no engagement extracts can flow back into the
knowledge graph (research/entities/) — tenant data would leak.

Per design spec §7.2: anonymized output should read like Bloomberg
"industry color" — preserves learning, identity-free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.anonymize import AnonymizationPolicy, anonymize, carries_tenant_marker
from core.orchestrator import render_all
from tests.fixtures.acme_bank import (
    ACME_BANK_CANARY_TOKENS,
    acme_bank_tenant,
    build_acme_bank_engagement,
)
from tests.fixtures.acme_bank import deliverable_extras as acme_bank_extras
from tests.fixtures.nova_construction import (
    NOVA_CONSTRUCTION_CANARY_TOKENS,
    build_nova_construction_engagement,
    nova_construction_tenant,
)
from tests.fixtures.nova_construction import (
    deliverable_extras as nova_construction_extras,
)
from tests.fixtures.tropico_renovables import (
    TROPICO_CANARY_TOKENS,
    build_tropico_engagement,
    deliverable_extras,
    tropico_tenant,
)

pytestmark = [pytest.mark.integration, pytest.mark.canary]


class TestAnonymizationCanary:
    def test_tropico_canary_token_count_is_14(self):
        """M7 release-gate convention: 14 canary tokens per fixture."""
        assert len(TROPICO_CANARY_TOKENS) == 14, (
            f"Tropico fixture must declare exactly 14 canary tokens for the "
            f"M7 14×3 release gate convention. Got {len(TROPICO_CANARY_TOKENS)}."
        )

    def test_no_canary_tokens_in_anonymized_deliverables(self, tmp_path: Path):
        """The 14-canary release gate: zero leaks across all 7 Tropico
        deliverables. This mirrors Acme/Nova canary checks and is the
        primary release gate for M7."""
        eng = build_tropico_engagement()
        ctx = deliverable_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)

        policy = AnonymizationPolicy()
        tenant = tropico_tenant()

        leaks: dict[str, list[str]] = {}
        for slug, path in paths.items():
            redacted = anonymize(path.read_text(), policy, tenant)
            leaked_tokens = [t for t in TROPICO_CANARY_TOKENS if t in redacted]
            if leaked_tokens:
                leaks[slug] = leaked_tokens

        assert not leaks, (
            "Tropico canary-token leak. The anonymizer let one or more "
            "fixture-declared canary tokens through. "
            f"Per-slug leaks: {leaks}. Tighten core.anonymize coverage."
        )

    def test_anonymized_deliverables_carry_no_tenant_markers(self, tmp_path: Path):
        # 1) Build the canonical Tropico engagement — full 5-stage pipeline.
        eng = build_tropico_engagement()
        ctx = deliverable_extras()

        # 2) Render all 7 deliverables.
        paths, lint_result = render_all(eng, tmp_path, extra_context=ctx)
        assert not lint_result.has_errors, (
            "Canary cannot run on a lint-broken engagement. "
            f"Got: {[v.message for v in lint_result.violations]}"
        )

        # 3) Run each rendered deliverable through anonymization.
        policy = AnonymizationPolicy()
        tenant = tropico_tenant()

        leaks: list[tuple[str, list[str]]] = []
        for slug, path in paths.items():
            raw = path.read_text()
            redacted = anonymize(raw, policy, tenant)
            markers = carries_tenant_marker(redacted, tenant)
            if markers:
                leaks.append((slug, markers))

        # 4) Assert zero leaks. Failure message lists the offending slugs +
        #    markers so the operator sees exactly what to fix.
        assert not leaks, (
            "Anonymization canary FAILED — tenant markers leaked through "
            f"redaction. Check core.anonymize policy against the design spec "
            f"§7.2 and expand redact_terms / personal-name regex coverage. "
            f"Leaks: {leaks}"
        )

    def test_currency_amounts_redacted_to_bands(self, tmp_path: Path):
        """Dollar amounts in deliverables should not leak verbatim — they
        bucket to magnitude bands. $640,000 in the thesis is the canonical
        check."""
        eng = build_tropico_engagement()
        ctx = deliverable_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)

        policy = AnonymizationPolicy()
        tenant = tropico_tenant()

        # Maturity Report carries the magnitude estimate
        raw = paths["maturity-report"].read_text()
        redacted = anonymize(raw, policy, tenant)

        # The $640,000 magnitude should be bucketed; the literal value should
        # NOT survive into anonymized output.
        assert "$640,000" not in redacted
        assert "low-6-figures USD" in redacted

    def test_dates_redacted_to_relative_tokens(self, tmp_path: Path):
        """ISO dates and quarters should bucket to relative tokens."""
        eng = build_tropico_engagement()
        ctx = deliverable_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)

        policy = AnonymizationPolicy()
        tenant = tropico_tenant()

        raw = paths["pilot-plan"].read_text()
        redacted = anonymize(raw, policy, tenant)

        # 2026-04-01 (the baseline measurement date) should be redacted
        assert "2026-04-01" not in redacted
        assert "<engagement-date>" in redacted or "<engagement-year>" in redacted

    def test_opt_out_bypasses_redaction(self, tmp_path: Path):
        """Sanity check: a fully-permissive policy preserves raw markers
        (so we know the redaction is actually removing things, not just
        absence)."""
        eng = build_tropico_engagement()
        ctx = deliverable_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)

        permissive = AnonymizationPolicy(
            strip_tenant_slug=False,
            strip_tenant_name=False,
            strip_personal_names=False,
            replace_currency_with_bands=False,
            replace_dates_with_relative=False,
            replace_locations_with_regions=False,
        )
        tenant = tropico_tenant()
        raw = paths["maturity-report"].read_text()
        out = anonymize(raw, permissive, tenant)

        # With everything off, the tenant slug survives (proving the strict
        # policy in test_anonymized_deliverables_carry_no_tenant_markers
        # was actually doing work).
        assert tenant.tenant_slug in out


# ----------------------------------------------------------------------------
# M6 — Acme Bank canary
# ----------------------------------------------------------------------------


class TestAcmeBankAnonymizationCanary:
    """Acme Bank fixture canary — financial-services tenant. Verifies that
    the 14 canary tokens declared in tests/fixtures/acme_bank.py never leak
    through the anonymizer."""

    def test_no_tenant_markers_in_anonymized_deliverables(self, tmp_path: Path):
        eng = build_acme_bank_engagement()
        ctx = acme_bank_extras()

        paths, lint_result = render_all(eng, tmp_path, extra_context=ctx)
        assert not lint_result.has_errors, (
            "Canary cannot run on a lint-broken Acme engagement. "
            f"Got: {[v.message for v in lint_result.violations]}"
        )

        policy = AnonymizationPolicy()
        tenant = acme_bank_tenant()

        leaks: list[tuple[str, list[str]]] = []
        for slug, path in paths.items():
            raw = path.read_text()
            redacted = anonymize(raw, policy, tenant)
            markers = carries_tenant_marker(redacted, tenant)
            if markers:
                leaks.append((slug, markers))

        assert not leaks, (
            "Acme Bank anonymization canary FAILED — tenant markers leaked. "
            f"Check core.anonymize policy against design spec §7.2. "
            f"Leaks: {leaks}"
        )

    def test_no_canary_tokens_in_anonymized_deliverables(self, tmp_path: Path):
        """Stronger check: every token in ACME_BANK_CANARY_TOKENS (sponsor,
        other people, product names, branch cities, sensitive currency
        amounts) must be absent from every anonymized deliverable."""
        eng = build_acme_bank_engagement()
        ctx = acme_bank_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)

        policy = AnonymizationPolicy()
        tenant = acme_bank_tenant()

        leaks: dict[str, list[str]] = {}
        for slug, path in paths.items():
            redacted = anonymize(path.read_text(), policy, tenant)
            leaked_tokens = [t for t in ACME_BANK_CANARY_TOKENS if t in redacted]
            if leaked_tokens:
                leaks[slug] = leaked_tokens

        assert not leaks, (
            "Acme Bank canary-token leak. The anonymizer let one or more "
            "fixture-declared canary tokens through. "
            f"Per-slug leaks: {leaks}. Tighten core.anonymize coverage."
        )

    def test_currency_amounts_bucketed(self, tmp_path: Path):
        """$4.2M magnitude in the thesis should bucket — verbatim must not
        survive."""
        eng = build_acme_bank_engagement()
        ctx = acme_bank_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)
        policy = AnonymizationPolicy()
        tenant = acme_bank_tenant()
        redacted = anonymize(paths["maturity-report"].read_text(), policy, tenant)
        assert "$4.2M" not in redacted
        assert "$4,200,000" not in redacted
        assert "low-7-figures USD" in redacted or "low-6-figures USD" in redacted


# ----------------------------------------------------------------------------
# M6 — Nova Construction canary
# ----------------------------------------------------------------------------


class TestNovaConstructionAnonymizationCanary:
    """Nova Construction fixture canary — construction tenant. Verifies the
    10 canary tokens declared in tests/fixtures/nova_construction.py never
    leak through the anonymizer."""

    def test_no_tenant_markers_in_anonymized_deliverables(self, tmp_path: Path):
        eng = build_nova_construction_engagement()
        ctx = nova_construction_extras()

        paths, lint_result = render_all(eng, tmp_path, extra_context=ctx)
        assert not lint_result.has_errors, (
            "Canary cannot run on a lint-broken Nova engagement. "
            f"Got: {[v.message for v in lint_result.violations]}"
        )

        policy = AnonymizationPolicy()
        tenant = nova_construction_tenant()

        leaks: list[tuple[str, list[str]]] = []
        for slug, path in paths.items():
            raw = path.read_text()
            redacted = anonymize(raw, policy, tenant)
            markers = carries_tenant_marker(redacted, tenant)
            if markers:
                leaks.append((slug, markers))

        assert not leaks, (
            f"Nova Construction anonymization canary FAILED — tenant markers leaked. Leaks: {leaks}"
        )

    def test_no_canary_tokens_in_anonymized_deliverables(self, tmp_path: Path):
        eng = build_nova_construction_engagement()
        ctx = nova_construction_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)

        policy = AnonymizationPolicy()
        tenant = nova_construction_tenant()

        leaks: dict[str, list[str]] = {}
        for slug, path in paths.items():
            redacted = anonymize(path.read_text(), policy, tenant)
            leaked_tokens = [t for t in NOVA_CONSTRUCTION_CANARY_TOKENS if t in redacted]
            if leaked_tokens:
                leaks[slug] = leaked_tokens

        assert not leaks, (
            "Nova Construction canary-token leak. "
            f"Per-slug leaks: {leaks}. Tighten core.anonymize coverage."
        )

    def test_currency_amounts_bucketed(self, tmp_path: Path):
        """The thesis magnitude $680K should bucket — verbatim absent."""
        eng = build_nova_construction_engagement()
        ctx = nova_construction_extras()
        paths, _ = render_all(eng, tmp_path, extra_context=ctx)
        policy = AnonymizationPolicy()
        tenant = nova_construction_tenant()
        redacted = anonymize(paths["maturity-report"].read_text(), policy, tenant)
        assert "$680,000" not in redacted
        # 680K → mid-5-figures threshold check
        assert (
            "low-6-figures USD" in redacted
            or "mid-5-figures USD" in redacted
            or "low-5-figures USD" in redacted
        )


# ----------------------------------------------------------------------------
# M7 release gate — 14 tokens × 3 fixtures = 42 tokens, ZERO leaks.
# ----------------------------------------------------------------------------


class TestM7CanaryReleaseGate:
    """Aggregate release-gate test — every fixture, every token, every
    deliverable. A leak anywhere blocks the M7 release."""

    def test_release_gate_14x3_tokens_zero_leaks(self, tmp_path: Path):
        """Run every fixture's full 7-deliverable render through the
        anonymizer, then check every token from every fixture against every
        rendered output. 14 × 3 = 42 tokens; total checks across 7
        deliverables × 3 fixtures = 21 anonymized files; expected leak
        count is 0."""
        fixture_runs = [
            (
                "tropico-renovables",
                build_tropico_engagement(),
                deliverable_extras(),
                tropico_tenant(),
                TROPICO_CANARY_TOKENS,
            ),
            (
                "acme-bank",
                build_acme_bank_engagement(),
                acme_bank_extras(),
                acme_bank_tenant(),
                ACME_BANK_CANARY_TOKENS,
            ),
            (
                "nova-construction",
                build_nova_construction_engagement(),
                nova_construction_extras(),
                nova_construction_tenant(),
                NOVA_CONSTRUCTION_CANARY_TOKENS,
            ),
        ]

        # Sanity: 14 × 3 tokens declared.
        token_counts = {slug: len(tokens) for slug, _, _, _, tokens in fixture_runs}
        assert token_counts == {
            "tropico-renovables": 14,
            "acme-bank": 14,
            "nova-construction": 14,
        }, (
            "M7 release gate convention: each fixture declares EXACTLY 14 "
            f"canary tokens (14 × 3 = 42 release-gate tokens). Got: {token_counts}"
        )

        policy = AnonymizationPolicy()
        all_leaks: dict[str, dict[str, list[str]]] = {}
        total_anonymized_files = 0

        for fixture_slug, eng, ctx, tenant, canary_tokens in fixture_runs:
            fixture_dir = tmp_path / fixture_slug
            paths, lint = render_all(eng, fixture_dir, extra_context=ctx)
            assert not lint.has_errors, (
                f"M7 release gate cannot run on lint-broken {fixture_slug} — "
                f"got: {[v.message for v in lint.violations]}"
            )
            for slug, path in paths.items():
                total_anonymized_files += 1
                redacted = anonymize(path.read_text(), policy, tenant)
                leaked_tokens = [t for t in canary_tokens if t in redacted]
                if leaked_tokens:
                    all_leaks.setdefault(fixture_slug, {})[slug] = leaked_tokens

        assert total_anonymized_files == 21, (
            f"Expected 7 deliverables × 3 fixtures = 21 anonymized files; "
            f"got {total_anonymized_files}."
        )
        assert not all_leaks, (
            "M7 RELEASE GATE FAILED — anonymization canary breach. "
            "One or more of the 42 release-gate tokens leaked into "
            "anonymized output. This blocks the push.\n"
            f"  Per-fixture leaks: {all_leaks}\n"
            "  Tighten core.anonymize policy + redact_terms before retrying."
        )
