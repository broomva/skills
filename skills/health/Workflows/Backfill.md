# Backfill — historical pull over a date range

**When invoked:** the user wants more than the incremental sync horizon — typically the cold start of a new install, recovery from a multi-week sync gap, or rebuilding a corrupted local DB.

## Two paths

### Path A — GDPR export tarball (preferred for cold start)

**Always prefer this for cold-start ingest.** Garmin's "Export Your Data" produces a complete account dump with no rate-limit cost to your account. Generation time: hours-to-days (Garmin's queue). Once delivered:

1. Download the tarball from the Garmin email link.
2. Place under `~/broomva-health/exports/garmin/raw/<request-id>.zip`.
3. Run:

```bash
health backfill --source garmin --from 2018-01-01 --to 2026-05-22 --strategy gdpr-tarball
```

The adapter unpacks the tarball, walks the per-day JSON / FIT files, and writes the trace DB in batches. Zero API calls. Duration: minutes (disk-bound, not network-bound).

URLs / references:
- Garmin Connect → Settings → Account Information → "Export Your Data"
- See [References/garmin-api-landscape-2026.md](../References/garmin-api-landscape-2026.md) §GDPR-export for the file layout.

### Path B — API-driven backfill (fallback)

When the GDPR tarball is not available (gap fill, partial range, recently-deleted account):

```bash
health backfill --source garmin --from 2026-04-01 --to 2026-05-22
```

This walks the API day-by-day, *respecting the rate-limit floor*. Expected duration:

| Range | Approx API calls | Wall time (at 15-min floor) |
|---|---|---|
| 7 days | ~50 | ~10–15 min |
| 30 days | ~210 | ~45–60 min |
| 90 days | ~640 | ~2.5 hours |
| 1 year | ~2,500 | ~10–12 hours |

**The 15-minute poll floor is non-negotiable.** Multi-day API backfills MUST run as a background job that respects the limiter. Do NOT bypass — the floor exists because the second 429 within 10 minutes triggers an account-scoped 48–72h soft-ban that has been observed on the python-garminconnect issue tracker. See [References/rate-limit-discipline.md](../References/rate-limit-discipline.md).

## Output (success)

```json
{
  "source": "garmin",
  "range_start": "2026-04-01",
  "range_end": "2026-05-22",
  "samples_ingested": 41872,
  "workouts_ingested": 28,
  "errors": []
}
```

## Failure modes

- **Validation:** `end < start` raises `ValueError` before any network I/O.
- **Mid-run 429:** the use case records the 429 and re-raises. The CLI prints `retry_after_s` and the recommended resume command (`health backfill --source garmin --from <last_complete_day> --to <end>`).
- **Partial completion:** rows already written to the trace DB are kept (upsert is idempotent on `(source, metric, start_ts)`). Resume picks up where you left off.

## Persist (P12) pairing for long backfills

For a year-scale backfill, wrap the call in a Persist loop so each iteration is a fresh agent context and the trace DB itself is the state:

```bash
persist iterate skills/Health/backfill.md
```

The `backfill.md` PROMPT contains the range + `--strategy api-incremental --chunk-days 7`. Each iteration syncs one week, sleeps until the rate-limiter clears, exits cleanly. The next iteration spawns fresh.

## P15 reflex after Backfill

After a multi-day API backfill, `health status` should show a healthy rate budget (we paced for it) and a recent `last_sync`. If `rate_limit_resets_at` is far in the future or `last_error` is populated, **stop** and re-check before running anything else.

## Example end-to-end

```bash
$ health backfill --source garmin --from 2026-04-01 --to 2026-05-22 --format json
{
  "source": "garmin",
  "range_start": "2026-04-01",
  "range_end": "2026-05-22",
  "samples_ingested": 41872,
  "workouts_ingested": 28,
  "errors": []
}

$ health daily-note --date 2026-04-15   # now possible — was empty before
/Users/<you>/broomva-vault/07-Health/2026-04-15.md
```
