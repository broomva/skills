"""Engagement aggregate root + journal replay + JSONL persistence.

Closes Gap #12 (EngagementJournal replay) + Gap #13 (Engagement aggregate root)
from the Tropico Renovables synthetic engagement (2026-05-06).

EngagementJournal is the persistence boundary — append-only event log.
EngagementState is derived by replaying the journal — never mutated directly.
Engagement is the aggregate root: tenant + journal + emit().

JSONL persistence (Phase E):
- save_jsonl(path) writes one line per event (newline-delimited JSON).
- load_jsonl(tenant, path) reconstructs the journal. Missing path → empty.
- Phase 1 rewrites the whole file on save; Phase 3 will switch to true
  append-only writes once we move to lago.

Phase 3 mapping: this struct mirrors lago's `Aggregate<E, S>` shape, where
events becomes Vec<Record<E>> and replay() is the fold (`events.iter().fold(S::initial(), apply)`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from core.types import EventKind, JournalEvent, TenantContext


class EngagementState(BaseModel):
    """Derived state from replaying an EngagementJournal. Read-only.

    Stages mutate engagement state via emit() — never by setting fields here.
    EngagementState is rebuilt fresh on every replay() call.
    """

    current_stage: Literal["intake", "scan", "ideate", "prioritize", "roadmap", "concluded"] = (
        "intake"
    )
    thesis_id: str | None = None
    frameworks_active: list[str] = Field(default_factory=list)
    maturity_dimensions: list[str] = Field(default_factory=list)
    use_cases: dict[str, dict[str, object]] = Field(default_factory=dict)
    use_cases_prioritized: list[str] = Field(default_factory=list)
    baselines_captured: list[str] = Field(default_factory=list)
    deliverables_rendered: list[str] = Field(default_factory=list)
    review_pending: str | None = None
    is_concluded: bool = False


class EngagementJournal(BaseModel):
    """Append-only event log scoped to one tenant engagement.

    Persistence path: engagements/<tenant_slug>/journal.jsonl (P6 — gitignored).
    """

    tenant: TenantContext
    events: list[JournalEvent] = Field(default_factory=list)

    def append(self, event: JournalEvent) -> None:
        """Append an event. Caller is responsible for ULID monotonicity
        (which Engagement.emit() handles via JournalEvent's default_factory)."""
        self.events.append(event)

    def replay(self) -> EngagementState:
        """Reconstruct EngagementState by folding events in journal order.

        Pure function — calling .replay() twice returns equal states.
        Phase 3 mirror: events.iter().fold(EngagementState::default(), apply).
        """
        state = EngagementState()
        for ev in self.events:
            state = _apply(state, ev)
        return state

    def save_jsonl(self, path: Path) -> None:
        """Write the journal to `path` as newline-delimited JSON.

        One event per line. Caller chooses where to write (typically
        `engagements/<tenant_slug>/journal.jsonl`). Parent dirs created
        if missing. Existing file is overwritten — the journal is the
        source of truth, and every emit() rewrites the whole file.

        Phase 3 will switch to true append-only writes; Phase 1 simplicity
        preferred for synthetic-fixture-driven workflows.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [ev.model_dump_json(exclude_none=True) for ev in self.events]
        path.write_text("\n".join(lines) + ("\n" if lines else ""))

    @classmethod
    def load_jsonl(cls, tenant: TenantContext, path: Path) -> EngagementJournal:
        """Reconstruct an EngagementJournal from an on-disk JSONL file.

        Missing file returns an empty journal — that's the natural startup
        case for a fresh engagement. Empty lines are skipped. Malformed
        lines raise ValidationError (don't silently drop events).
        """
        events: list[JournalEvent] = []
        if path.exists():
            for line in path.read_text().splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                events.append(JournalEvent.model_validate_json(stripped))
        return cls(tenant=tenant, events=events)


_STAGE_ORDER = ["intake", "scan", "ideate", "prioritize", "roadmap"]


def _next_stage(approved_stage: str) -> str:
    try:
        i = _STAGE_ORDER.index(approved_stage)
    except ValueError:
        return approved_stage
    if i + 1 < len(_STAGE_ORDER):
        return _STAGE_ORDER[i + 1]
    return "concluded"


def _apply(state: EngagementState, ev: JournalEvent) -> EngagementState:
    """Pure event-application. Returns a new state — never mutates input."""
    next_state = state.model_copy(deep=True)

    if ev.kind == EventKind.STRATEGIC_THESIS_DECLARED:
        thesis_id = ev.payload.get("thesis_id")
        if isinstance(thesis_id, str):
            next_state.thesis_id = thesis_id

    elif ev.kind == EventKind.INTAKE_COMPLETED:
        fw = ev.payload.get("frameworks_selected", [])
        if isinstance(fw, list):
            next_state.frameworks_active = [str(x) for x in fw]
        # current_stage transitions on STAGE_REVIEW_APPROVED, not here.

    elif ev.kind == EventKind.MATURITY_DIMENSION_SCORED:
        name = ev.payload.get("dimension_name")
        if isinstance(name, str):
            next_state.maturity_dimensions.append(name)

    elif ev.kind == EventKind.USE_CASE_PROPOSED:
        uc_id = ev.payload.get("use_case_id")
        if isinstance(uc_id, str):
            next_state.use_cases[uc_id] = dict(ev.payload)

    elif ev.kind == EventKind.USE_CASE_PRIORITIZED:
        uc_id = ev.payload.get("use_case_id")
        if isinstance(uc_id, str):
            next_state.use_cases_prioritized.append(uc_id)

    elif ev.kind == EventKind.BASELINE_CAPTURED:
        m = ev.payload.get("metric_name")
        if isinstance(m, str):
            next_state.baselines_captured.append(m)

    elif ev.kind == EventKind.DELIVERABLE_RENDERED:
        slug = ev.payload.get("slug")
        if isinstance(slug, str):
            next_state.deliverables_rendered.append(slug)

    elif ev.kind == EventKind.STAGE_REVIEW_REQUESTED:
        st = ev.payload.get("stage")
        if isinstance(st, str):
            next_state.review_pending = st

    elif ev.kind == EventKind.STAGE_REVIEW_APPROVED:
        next_state.review_pending = None
        st = ev.payload.get("stage")
        if isinstance(st, str):
            next_state.current_stage = _next_stage(st)  # type: ignore[assignment]

    elif ev.kind == EventKind.ENGAGEMENT_CONCLUDED:
        next_state.is_concluded = True
        next_state.current_stage = "concluded"

    return next_state


class Engagement(BaseModel):
    """Aggregate root: tenant + journal + emit().

    Closes Gap #13 — the Tropico engagement had to manually couple
    TenantContext + journal + deliverables, losing invariants. Engagement
    forces all mutation through emit() so replay stays deterministic.
    """

    tenant: TenantContext
    journal: EngagementJournal

    def state(self) -> EngagementState:
        """Replay the journal to derive current state. Pure function."""
        return self.journal.replay()

    def emit(
        self,
        kind: EventKind,
        stage: str,
        payload: dict[str, object],
        actor: str = "phronesis",
        parent_event_id: str | None = None,
    ) -> str:
        """Emit a journal event. Returns the event_id (ULID).

        Construction goes through JournalEvent's model_validator (Phase A.3),
        which re-validates the payload against the kind's schema. Bad
        payloads raise ValidationError before append.

        Reflexive M7 hook: when `kind == ENGAGEMENT_CONCLUDED`, the
        extraction pipeline fires automatically (per
        `feedback_bookkeeping_reflexive.md`). Disable via env var
        `PHRONESIS_EXTRACTION_ENABLED=0` (interactive-debug use only —
        the default ON path is the autonomous-arc contract).
        """
        ev = JournalEvent(
            kind=kind,
            actor=actor,
            stage=stage,
            payload=payload,
            parent_event_id=parent_event_id,
        )
        self.journal.append(ev)

        if kind == EventKind.ENGAGEMENT_CONCLUDED:
            self._fire_extraction_hook()

        return ev.event_id

    def _fire_extraction_hook(self) -> None:
        """Trigger M7 extraction pipeline on ENGAGEMENT_CONCLUDED.

        Imported lazily to avoid a circular import (extraction depends on
        Engagement). Best-effort: any exception in the hook is swallowed
        with a stderr warning — the engagement journal is the source of
        truth, and the extraction pipeline must not block emit().
        """
        try:
            from core.extraction.pipeline import on_engagement_concluded

            on_engagement_concluded(self)
        except Exception as exc:  # pragma: no cover — hook is fire-and-forget
            import sys

            print(
                f"[phronesis][warn] extraction-hook failed for "
                f"{self.tenant.tenant_slug!r}: {exc!r}",
                file=sys.stderr,
            )
