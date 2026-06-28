"""Revision protocol — replay-safe stage revision.

Closes Gap #19 from the Tropico Renovables synthetic engagement.

When a sponsor sends a stage back via STAGE_REVIEW_REVISED, the work events
that the stage previously emitted must be retracted from the journal so the
stage can be re-executed with new inputs. The revision marker itself
(STAGE_REVIEW_REVISED, REQUESTED, APPROVED) is preserved as audit trail —
P5 mandates no silent retractions.

Phase 3 mapping: this is a journal compaction op. In lago, retractions
become tombstone records that the replay function skips. Phase 1 simplifies
by physically removing the events; lossy but adequate for synthetic
engagements where the journal is local. Phase 3 will switch to tombstones.
"""

from __future__ import annotations

from core.engagement import Engagement
from core.types import EventKind, JournalEvent

# Review-marker kinds are preserved across revisions — they are the audit
# trail of who approved/revised when, and discarding them would lose P5.
_REVIEW_MARKER_KINDS = frozenset(
    {
        EventKind.STAGE_REVIEW_REQUESTED,
        EventKind.STAGE_REVIEW_APPROVED,
        EventKind.STAGE_REVIEW_REVISED,
    }
)


def retract_to_revision_point(eng: Engagement, stage: str) -> int:
    """Remove all work events at `stage` while preserving review markers.

    Returns the count of events removed. Caller emits new events for the
    stage afterward — replay reconstructs state from the trimmed journal.

    Cross-stage events are untouched: revising stage `scan` does not affect
    intake-stage events. This preserves the invariant that revision is
    locally scoped.
    """
    keep: list[JournalEvent] = []
    removed = 0
    for ev in eng.journal.events:
        is_target_stage = ev.stage == stage
        is_review_marker = ev.kind in _REVIEW_MARKER_KINDS
        if is_target_stage and not is_review_marker:
            removed += 1
            continue
        keep.append(ev)
    eng.journal.events = keep
    return removed
