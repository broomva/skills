# ADR-0003: Event-sourced engagement journal (JSONL → lago)

**Status:** Accepted (2026-05-06)

## Context

An engagement runs over weeks with multiple stages, multiple participants, pause/resume workflows, and audit requirements. State could be stored as (a) mutable YAML/JSON files updated in place, or (b) an append-only event log from which state is replayed.

## Decision

Append-only event log of typed `JournalEvent` records persisted at `engagements/<tenant>/journal.jsonl`. Engagement state is *always* derived from replay; never mutated directly. Mirrors lago's `Record<E>` shape for clean Phase-3 transcription.

## Consequences

* Pause/resume is trivial: load the journal, replay, continue
* Audit trail is the persistence format
* Crash mid-command → resume from last event
* Phase 3 is a near-no-op: lago already implements this pattern in Rust
* L5 (BASELINE_REQUIRED) becomes verifiable at journal level: `BASELINE_CAPTURED` must precede `PILOT_STARTED`

## Alternatives considered

1. **Mutable state files.** Rejected — no audit, no pause/resume guarantee, no Phase-3 lago alignment
2. **SQLite.** Rejected — overkill for Phase 1; JSONL is human-inspectable and trivially replayable
3. **Direct lago integration in Phase 1.** Rejected — couples Phase 1 to Life infrastructure we haven't shipped yet
