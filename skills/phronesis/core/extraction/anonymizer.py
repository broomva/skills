"""Engagement-shaped anonymization wrapper.

Thin adapter over `core/anonymize.py` that takes a `TenantContext` +
engagement-derived `redact_terms` (e.g. project codenames, interviewee
non-sponsor names) and produces canary-clean text suitable for the
knowledge-graph layer.

Why wrap `anonymize()`? The extraction pipeline always operates on the
same shape (engagement journal payloads + tenant context), and we want a
single place where the policy defaults + the engagement-specific
redact_terms come together. Callers in `pipeline.py` and the test
harness use this wrapper, not the lower-level `anonymize()` directly.

The 14-canary-token release gate
(`tests/integration/test_anonymization_canary.py`) drives the underlying
`core/anonymize.py::anonymize()` directly because the canary asserts the
policy itself works — not just our wrapper. The wrapper is a convenience
layer for the extraction pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from core.anonymize import AnonymizationPolicy, anonymize, carries_tenant_marker
from core.engagement import Engagement
from core.types import TenantContext


class EngagementAnonymizer(BaseModel):
    """Tenant-bound anonymizer for engagement-derived text.

    Built once per engagement; reused across every candidate emitted by
    the extraction pipeline.

    Attributes:
        tenant: the engagement tenant — name + slug + sponsor stripped.
        policy: the anonymization policy (defaults to strict — every
            transform on, no caller-supplied redact_terms unless the
            engagement surfaces project codenames).
    """

    tenant: TenantContext
    policy: AnonymizationPolicy

    def redact(self, text: str) -> str:
        """Anonymize `text` against this engagement's tenant + policy."""
        return anonymize(text, self.policy, self.tenant)

    def carries_marker(self, text: str) -> list[str]:
        """Forensic — list tenant markers still present in `text`. Empty
        list means clean. Used by the pipeline to assert post-redaction
        before emitting a candidate."""
        return carries_tenant_marker(text, self.tenant)


def _collect_engagement_redact_terms(engagement: Engagement) -> list[str]:
    """Walk the engagement journal for project codenames + non-sponsor
    interviewee names that the strict policy might miss.

    These get added to `policy.redact_terms`. Conservative bias toward
    over-redaction — the canary catches leaks, not over-redaction.

    Heuristics (Phase 1):
      - `INTERVIEW_LOGGED.interviewee` → strip the human name (modulo the
        sponsor, which `core/anonymize.py` already handles).
      - `ROADMAP_STEP_PROPOSED.title` may contain project codenames —
        Phase 2 will add NER + per-tenant project-codename declarations.
        For now, we trust the strict policy + the canary list.
    """
    from core.types import EventKind

    redact: list[str] = []
    for ev in engagement.journal.events:
        if ev.kind == EventKind.INTERVIEW_LOGGED:
            interviewee = ev.payload.get("interviewee", "")
            if not isinstance(interviewee, str) or not interviewee:
                continue
            # Strip any "(Role)" suffix — we only want the name itself.
            name = interviewee.split("(")[0].strip()
            # Don't redact the sponsor here; `anonymize()` already does it.
            if engagement.tenant.sponsor and engagement.tenant.sponsor in name:
                continue
            if name and name not in redact:
                redact.append(name)

    return redact


def anonymize_engagement_text(
    text: str,
    engagement: Engagement,
    *,
    extra_redact_terms: Iterable[str] = (),
    policy: AnonymizationPolicy | None = None,
) -> str:
    """Anonymize `text` using engagement-derived redaction terms.

    The convenience entry point for one-shot redactions (e.g. extracting
    a single finding into an industry-pattern candidate). The pipeline
    builds an `EngagementAnonymizer` once and calls `.redact()` repeatedly
    — that's the hot path. This function is the cold path for ad-hoc
    callers.

    Args:
        text: the raw text to anonymize.
        engagement: the engagement the text was derived from (for tenant
            context + journal-derived redact terms).
        extra_redact_terms: caller-supplied terms in addition to the
            journal-derived ones (e.g. a project codename surfaced in a
            specific journal payload).
        policy: optional policy override; default is strict.

    Returns:
        Anonymized text with all tenant markers + journal-derived
        identifying names + caller-supplied terms redacted.
    """
    if policy is None:
        policy = AnonymizationPolicy()

    journal_terms = _collect_engagement_redact_terms(engagement)
    combined_terms = list(
        dict.fromkeys([*policy.redact_terms, *journal_terms, *extra_redact_terms])
    )

    effective_policy = policy.model_copy(update={"redact_terms": combined_terms})
    return anonymize(text, effective_policy, engagement.tenant)


__all__ = [
    "EngagementAnonymizer",
    "anonymize_engagement_text",
]
