# Status — reflexive snapshot of all sources

**When invoked:** at the start of every health-domain conversation. This is the **Snapshot (P15)** reflex applied to the health domain. The agent never answers a health question without first knowing whether the trace store is current.

## Command

```bash
health status [--format json|jsonl|csv|tsv|human]
```

`status` queries every registered source's `status()` method (per the `TraceSource` protocol), which is **non-throwing** — every adapter returns a populated `SourceStatus` even when authentication is broken.

## Output

```json
[
  {
    "source": "garmin",
    "last_sync": "2026-05-22T14:03:24Z",
    "last_error": null,
    "rate_limit_resets_at": "2026-05-22T14:18:24Z",
    "token_valid": true,
    "token_expires_at": "2026-06-21T14:03:24Z"
  }
]
```

## Decision tree

```
token_valid = false?
  → user must run `health auth login --source <name>` (exit 2 on next sync attempt)

last_sync = null OR (now - last_sync) > 24h?
  → stale; recommend `health sync --source <name>` before answering

last_error != null?
  → surface the error; do not attempt sync until the user acknowledges

rate_limit_resets_at > now?
  → in cooldown; do NOT call `health sync` — schedule for after reset

all green?
  → proceed with the requested workflow
```

## Composition with other workflows

| Subsequent workflow | Status preflight check |
|---|---|
| [Sync](Sync.md) | `token_valid && rate_limit_resets_at < now` |
| [Backfill](Backfill.md) | `token_valid && rate_limit_resets_at < now` (and confirm long-running OK) |
| [DailyNote](DailyNote.md) | `last_sync` within last 24h, otherwise sync first |
| [TrainingLoad](TrainingLoad.md) | `last_sync` within last 24h |
| [RecoveryReview](RecoveryReview.md) | `last_sync` within last 24h |
| [VO2maxArc](VO2maxArc.md) | `last_sync` within last 7d (VO2max updates infrequently) |

## Example

```bash
$ health status --format human
                                     SourceStatus
┌──────────┬──────────────────────┬──────────────┬──────────────────────┬─────────────┬──────────────────────┐
│ source   │ last_sync            │ last_error   │ rate_limit_resets_at │ token_valid │ token_expires_at     │
├──────────┼──────────────────────┼──────────────┼──────────────────────┼─────────────┼──────────────────────┤
│ garmin   │ 2026-05-22T14:03:24Z │              │ 2026-05-22T14:18:24Z │ True        │ 2026-06-21T14:03:24Z │
└──────────┴──────────────────────┴──────────────┴──────────────────────┴─────────────┴──────────────────────┘
```

Followed by the actual workflow. Never skip the snapshot.
