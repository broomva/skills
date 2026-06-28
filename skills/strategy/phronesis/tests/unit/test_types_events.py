"""Unit tests for Layer 3 event-sourced journal primitives."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.types import EventKind, JournalEvent

pytestmark = pytest.mark.unit


class TestEventKind:
    def test_canonical_event_kinds(self):
        assert EventKind.ENGAGEMENT_STARTED.value == "engagement.started"
        assert EventKind.STRATEGIC_THESIS_DECLARED.value == "strategic_thesis.declared"
        assert EventKind.BASELINE_CAPTURED.value == "baseline.captured"
        assert EventKind.PILOT_STARTED.value == "pilot.started"
        assert EventKind.STAGE_REVIEW_APPROVED.value == "stage.review.approved"
        assert EventKind.ENGAGEMENT_CONCLUDED.value == "engagement.concluded"

    def test_kind_count_matches_design(self):
        # Design spec §4.3 mandates 16 canonical kinds.
        assert len(list(EventKind)) == 16


_VALID_INTAKE_PAYLOAD: dict[str, object] = {
    "tenant_slug": "acme-bank",
    "scope": "Tier-1 deflection — 8w pilot",
    "sponsor": "Carolina Pérez",
    "target_duration_weeks": 8,
}

_VALID_REVISED_PAYLOAD: dict[str, object] = {
    "stage": "intake",
    "reviewer": "Carolina Pérez",
    "revisions_requested": ["thesis was vague"],
    "original_event_id": "01HZBQ8X4ABCDEF0123456789",
}

_VALID_INTAKE_COMPLETED_PAYLOAD: dict[str, object] = {
    "thesis_id": "01HZ...",
    "frameworks_selected": ["mit-cisr-digital", "rice"],
}


class TestJournalEvent:
    def test_event_construction(self):
        e = JournalEvent(
            event_id="01HZBQ8X4ABCDEF0123456789",
            timestamp=datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC),
            kind=EventKind.ENGAGEMENT_STARTED,
            actor="Carlos Escobar",
            stage="intake",
            payload=_VALID_INTAKE_PAYLOAD,
            parent_event_id=None,
        )
        assert e.kind == EventKind.ENGAGEMENT_STARTED
        assert e.parent_event_id is None

    def test_revision_event_carries_parent(self):
        e = JournalEvent(
            event_id="01HZBQ8X4REV0123456789ABCD",
            timestamp=datetime(2026, 5, 6, 13, 0, 0, tzinfo=UTC),
            kind=EventKind.STAGE_REVIEW_REVISED,
            actor="Carlos Escobar",
            stage="intake",
            payload=_VALID_REVISED_PAYLOAD,
            parent_event_id="01HZBQ8X4ABCDEF0123456789",
        )
        assert e.parent_event_id is not None

    def test_event_id_auto_generated(self):
        # Regression: callers should not need to know ulid-py's API surface.
        # ulid.ULID() is a buffer constructor (extends MemoryView); the safe
        # path is the default_factory wired in core.types.
        e = JournalEvent(
            kind=EventKind.ENGAGEMENT_STARTED,
            actor="t",
            stage="intake",
            payload=_VALID_INTAKE_PAYLOAD,
        )
        # ULID strings are 26-char Crockford base32.
        assert isinstance(e.event_id, str)
        assert len(e.event_id) == 26
        assert e.timestamp.tzinfo is not None
        # Two events constructed in succession must have distinct ids.
        # (Strict monotonic ordering is not guaranteed within the same ms by
        # ulid-py — only uniqueness + time-prefix sortability across ms.)
        e2 = JournalEvent(
            kind=EventKind.INTAKE_COMPLETED,
            actor="t",
            stage="intake",
            payload=_VALID_INTAKE_COMPLETED_PAYLOAD,
        )
        assert e2.event_id != e.event_id

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            JournalEvent(
                event_id="01HZBQ8X4ABCDEF0123456789",
                timestamp=datetime(2026, 5, 6, tzinfo=UTC),
                kind="not.a.real.kind",  # type: ignore[arg-type]
                actor="x",
                stage="intake",
                payload=_VALID_INTAKE_PAYLOAD,
                parent_event_id=None,
            )

    def test_payload_validates_against_kind_schema(self):
        """Phase A.3 — JournalEvent.payload must satisfy the kind's schema."""
        # Valid: payload matches kind's schema
        e = JournalEvent(
            kind=EventKind.ENGAGEMENT_STARTED,
            actor="t",
            stage="intake",
            payload=_VALID_INTAKE_PAYLOAD,
        )
        assert e.payload["tenant_slug"] == "acme-bank"

    def test_payload_missing_required_field_rejected(self):
        """target_duration_weeks is required for ENGAGEMENT_STARTED."""
        with pytest.raises(ValidationError, match="target_duration_weeks"):
            JournalEvent(
                kind=EventKind.ENGAGEMENT_STARTED,
                actor="t",
                stage="intake",
                payload={"tenant_slug": "x", "scope": "y", "sponsor": "z"},
            )

    def test_payload_kind_mismatch_rejected(self):
        """An ENGAGEMENT_STARTED-shaped payload sent under MATURITY_DIMENSION_SCORED
        must be rejected (different schemas)."""
        with pytest.raises(ValidationError):
            JournalEvent(
                kind=EventKind.MATURITY_DIMENSION_SCORED,
                actor="t",
                stage="scan",
                payload=_VALID_INTAKE_PAYLOAD,  # wrong shape for this kind
            )
