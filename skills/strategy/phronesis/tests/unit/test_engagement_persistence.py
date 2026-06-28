"""JSONL persistence tests for EngagementJournal.

Round-trip: save → load → replay → state_equal.
Edge cases: missing file, empty journal, idempotent save.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from core.engagement import Engagement, EngagementJournal
from core.types import EventKind, TenantContext

pytestmark = pytest.mark.unit


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="acme",
        name="Acme",
        industry="banking",
        region="CO",
        revenue_band="100M-1B",
        headcount_band="500-5000",
        sponsor="x",
        sponsor_role="CDO",
        engagement_scope="s",
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=8,
    )


def _seed_engagement(tenant: TenantContext) -> Engagement:
    e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
    e.emit(
        EventKind.ENGAGEMENT_STARTED,
        "intake",
        {
            "tenant_slug": tenant.tenant_slug,
            "scope": tenant.engagement_scope,
            "sponsor": tenant.sponsor,
            "target_duration_weeks": tenant.target_duration_weeks,
        },
    )
    e.emit(
        EventKind.STRATEGIC_THESIS_DECLARED,
        "intake",
        {
            "thesis_id": "01HZ000",
            "economic_lever": "x",
            "lever_kind": "cost",
            "magnitude_estimate": "400000",
            "horizon": "h1-now",
            "owner": "CDO",
        },
    )
    e.emit(
        EventKind.INTAKE_COMPLETED,
        "intake",
        {"thesis_id": "01HZ000", "frameworks_selected": ["rice"]},
    )
    return e


class TestSaveJsonl:
    def test_writes_one_line_per_event(self, tenant: TenantContext, tmp_path: Path):
        eng = _seed_engagement(tenant)
        path = tmp_path / "journal.jsonl"
        eng.journal.save_jsonl(path)
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        assert len(lines) == 3

    def test_empty_journal_writes_empty_file(self, tenant: TenantContext, tmp_path: Path):
        journal = EngagementJournal(tenant=tenant)
        path = tmp_path / "empty.jsonl"
        journal.save_jsonl(path)
        assert path.exists()
        assert path.read_text() == ""

    def test_creates_parent_dir(self, tenant: TenantContext, tmp_path: Path):
        eng = _seed_engagement(tenant)
        path = tmp_path / "nested" / "deeper" / "journal.jsonl"
        eng.journal.save_jsonl(path)
        assert path.exists()


class TestLoadJsonl:
    def test_missing_file_returns_empty_journal(self, tenant: TenantContext, tmp_path: Path):
        path = tmp_path / "does-not-exist.jsonl"
        loaded = EngagementJournal.load_jsonl(tenant, path)
        assert loaded.events == []
        assert loaded.tenant == tenant

    def test_empty_file_returns_empty_journal(self, tenant: TenantContext, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        loaded = EngagementJournal.load_jsonl(tenant, path)
        assert loaded.events == []

    def test_blank_lines_skipped(self, tenant: TenantContext, tmp_path: Path):
        eng = _seed_engagement(tenant)
        path = tmp_path / "with-blanks.jsonl"
        eng.journal.save_jsonl(path)
        # Inject blank lines
        original = path.read_text()
        path.write_text("\n\n" + original + "\n\n")
        loaded = EngagementJournal.load_jsonl(tenant, path)
        assert len(loaded.events) == 3

    def test_malformed_line_raises(self, tenant: TenantContext, tmp_path: Path):
        path = tmp_path / "corrupt.jsonl"
        path.write_text('{"this": "is not a JournalEvent"}\n')
        with pytest.raises(Exception):  # noqa: B017 — Pydantic ValidationError or json decode
            EngagementJournal.load_jsonl(tenant, path)


class TestRoundTrip:
    def test_save_load_replay_equal(self, tenant: TenantContext, tmp_path: Path):
        eng_orig = _seed_engagement(tenant)
        path = tmp_path / "rt.jsonl"
        eng_orig.journal.save_jsonl(path)

        loaded = EngagementJournal.load_jsonl(tenant, path)
        eng_loaded = Engagement(tenant=tenant, journal=loaded)

        # Replay produces identical state
        assert eng_orig.state().model_dump() == eng_loaded.state().model_dump()
        # Events are equal
        assert len(eng_loaded.journal.events) == len(eng_orig.journal.events)
        for orig, lo in zip(eng_orig.journal.events, eng_loaded.journal.events, strict=True):
            assert orig.event_id == lo.event_id
            assert orig.kind == lo.kind
            assert orig.payload == lo.payload

    def test_save_is_idempotent(self, tenant: TenantContext, tmp_path: Path):
        eng = _seed_engagement(tenant)
        path = tmp_path / "idem.jsonl"
        eng.journal.save_jsonl(path)
        first = path.read_text()
        eng.journal.save_jsonl(path)
        second = path.read_text()
        assert first == second

    def test_decimal_in_payload_roundtrips(self, tenant: TenantContext, tmp_path: Path):
        """Decimal-bearing fields are str-encoded in payloads (per A.2 design).
        Round-trip preserves the string representation."""
        eng = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        eng.emit(
            EventKind.STRATEGIC_THESIS_DECLARED,
            "intake",
            {
                "thesis_id": "t1",
                "economic_lever": "x",
                "lever_kind": "cost",
                "magnitude_estimate": str(Decimal("640000.50")),
                "horizon": "h1-now",
                "owner": "x",
            },
        )
        path = tmp_path / "decimal.jsonl"
        eng.journal.save_jsonl(path)
        loaded = EngagementJournal.load_jsonl(tenant, path)
        assert loaded.events[0].payload["magnitude_estimate"] == "640000.50"
