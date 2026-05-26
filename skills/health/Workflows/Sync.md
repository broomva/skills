# Sync — incremental pull from a source

**When invoked:** the user asks for fresh data, or any health-domain workflow needs a current trace store and the last sync is older than the freshness budget (default: 60 minutes).

## Command

```bash
health sync --source garmin [--since 2026-05-22T00:00:00Z] [--profile default] [--format json]
```

If `--since` is omitted, the adapter resumes from `repo.last_sample_ts(source, metric)` for each metric — the trace DB *is* the cursor.

## Expected runtime

- **Incremental** (typical 5–60 minute gap): **~5–30 seconds** end-to-end.
- **Multi-day gap** (≤ 14 days): 30–120 seconds; the adapter chunks day-at-a-time so each chunk respects the per-source rate budget.
- **Anything longer:** use [Backfill](Backfill.md) instead. `sync` is not a backfill tool — it has no cold-start optimization.

## Output (success)

```json
{
  "source": "garmin",
  "started_at": "2026-05-22T14:03:11.812Z",
  "finished_at": "2026-05-22T14:03:24.117Z",
  "samples_ingested": 1437,
  "workouts_ingested": 1,
  "errors": [],
  "rate_limit_remaining_s": 879.4
}
```

Derived properties available in `human` format:
- `succeeded` — `len(errors) == 0`
- `duration_s` — `finished_at - started_at`

## Failure modes & responses

| Error code | Exit | Trigger | Agent action |
|---|---|---|---|
| `auth_required` | 2 | No valid token, or 401 from source | Instruct user: *"Re-run `health auth login --source garmin` with your password + MFA code."* Do **not** retry until user confirms. |
| `mfa_needed` | 2 | Step-up MFA mid-login | Surface the prompt; if env-MFA is configured (`BROOMVA_HEALTH_MFA_CODE`), the adapter consumes it once. |
| `rate_limited` | 1 | First 429 from source | Read `retry_after_s` from the exception. Schedule retry **after** `retry_after_s + 60s` jitter. Apply Wait (P9) — drain other queue work meanwhile. |
| `rate_limited` (repeat within 10min) | 1 | Second 429 | **Hard halt.** Do NOT retry. Notify user and offer to re-schedule for ≥ 6 hours later. Account-scoped 48–72h lockouts are documented — see [References/rate-limit-discipline.md](../References/rate-limit-discipline.md). |
| `source_unavailable` | 1 | Network / 5xx | Exponential backoff (1m, 2m, 4m, 8m, max 5 attempts). If all fail, surface the underlying error. |
| `repository_error` | 1 | Disk full, schema mismatch, lock contention | Suggest `health doctor`. Do not retry sync. |

## Rate-limit handling

The Sync use case acquires a per-source rate-limiter slot **before** any network I/O:

```python
self.rate_limiter.acquire(f"{source.name.value}:sync")
```

On success: `record_success(key)` resets backoff. On a 429: `record_429(key, retry_after_s=exc.retry_after_s)` extends the back-off window for the next call. The default Garmin policy is a 15-minute minimum poll interval — *not* a guess, it's `python-garminconnect` maintainer guidance documented in [References/rate-limit-discipline.md](../References/rate-limit-discipline.md).

## P15 reflex pairing

After Sync completes, the next agent reflex is typically [DailyNote](DailyNote.md) (emit today's projection) and then [Status](Status.md) (confirm rate budget remains healthy for the next call).

## Example end-to-end

```bash
$ health sync --source garmin --format human
            SyncResult
┌──────────────────────────┬─────────────────────────┐
│ key                      │ value                   │
├──────────────────────────┼─────────────────────────┤
│ source                   │ garmin                  │
│ started_at               │ 2026-05-22T14:03:11Z    │
│ finished_at              │ 2026-05-22T14:03:24Z    │
│ samples_ingested         │ 1437                    │
│ workouts_ingested        │ 1                       │
│ errors                   │ []                      │
│ rate_limit_remaining_s   │ 879.4                   │
└──────────────────────────┴─────────────────────────┘
```

Subsequent `health daily-note` consumes the freshly-written rows; subsequent `health status` confirms the rate budget for the next cycle.
