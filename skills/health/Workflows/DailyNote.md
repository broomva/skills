# DailyNote — emit today's Obsidian daily-note frontmatter

**When invoked:** after a successful [Sync](Sync.md), or when the user asks for "today's daily note", "today's health rollup", or anything that should compound into the Obsidian vault.

## Command

```bash
health daily-note [--date YYYY-MM-DD] [--format json|human]
```

If `--date` is omitted, defaults to **today (UTC)**. The output is the path to the written file, e.g. `/Users/<you>/broomva-vault/07-Health/2026-05-22.md`.

## Behavior

`RenderDailyNoteUseCase` queries the trace repository for the requested day across all sources, computes the synthesis values, and constructs a `DailyProjection`. The default `ProjectionTarget` is `ObsidianDailyNoteProjection`, which writes Markdown + YAML frontmatter to `~/broomva-vault/07-Health/YYYY-MM-DD.md`.

Idempotency: re-running for the same day either:
- overwrites the **frontmatter block** in place, or
- no-ops if the content hash is unchanged.

**Prose below the frontmatter is preserved.** The user adds notes, observations, prose under the frontmatter — subsequent emits leave that section untouched.

## Frontmatter schema

`DailyProjection.schema_version = 1` (versioned — bumps require downstream-consumer coordination, see [References/healthkit-data-model.md](../References/healthkit-data-model.md)).

```yaml
---
schema_version: 1
date: 2026-05-22
sources_synced: [garmin]
hrv_overnight_ms: 58.4
hrv_cv_30d: 0.082
rhr_bpm: 51
sleep_hours: 7.4
sleep_score: 84
training_load_ctl: 54.2
training_load_atl: 71.8
training_load_tsb: -17.6
vo2_max: 52.1
body_battery: 64
activities_count: 1
last_activity_type: running
last_activity_distance_km: 9.6
extras: {}
---

<!-- Prose below preserved across re-emits. -->

## Notes
- Felt good on the run, light legs despite the negative TSB.
- ...
```

## Field semantics

| Field | Source | Notes |
|---|---|---|
| `schema_version` | constant `1` in v1 | Bump on breaking change to consumers |
| `date` | the requested day (UTC) | Boundary: `[00:00 UTC, 24:00 UTC)` |
| `sources_synced` | sorted Source list seen in the day's window | Empty if no data |
| `hrv_overnight_ms` | latest `HRV_OVERNIGHT` sample on the day | unit: `ms` |
| `hrv_cv_30d` | `synthesis.hrv.compute_hrv_cv` over trailing 30d, anchored to this day | unitless ratio; `None` if < 7 samples |
| `rhr_bpm` | latest `RESTING_HEART_RATE` sample on the day | unit: `bpm` |
| `sleep_hours` | latest `SLEEP_DURATION` (seconds) ÷ 3600 | `None` if no sleep recorded |
| `sleep_score` | latest `SLEEP_SCORE` sample on the day | unit: `score_0_100`; vendor-derived |
| `training_load_ctl` / `_atl` / `_tsb` | `synthesis.training_load.compute_ctl_atl_tsb` over full history | unit: `tss/day`; Coggan EWMA |
| `vo2_max` | latest `VO2_MAX` sample on the day | unit: `ml/kg/min` |
| `body_battery` | latest `BODY_BATTERY` on the day | unit: `score_0_100`; **vendor opaque — see [validation-evidence.md](../References/validation-evidence.md)** |
| `activities_count` | count of workouts on the day | |
| `last_activity_type` | type of the last workout (sorted by `start_ts`) | |
| `last_activity_distance_km` | last workout's `distance_m` ÷ 1000 | `None` if not recorded |
| `extras` | dict for adapter-specific extras the schema doesn't capture | Forward-compatible escape hatch |

## Obsidian Dataview integration

Once a few days of notes exist, Dataview queries become trivial:

```dataview
TABLE date, hrv_overnight_ms, rhr_bpm, training_load_tsb
FROM "07-Health"
WHERE date >= date(today) - dur(30 days)
SORT date DESC
```

## Failure modes

| Error | Cause | Action |
|---|---|---|
| `ProjectionError` | Vault path not writable or symlink broken | Run `health doctor`; fix permissions on `~/broomva-vault/07-Health/`. |
| Empty frontmatter (all `null` fields) | No samples in the day's window | The note is still written (with `sources_synced: []`). Sync first via [Sync](Sync.md). |
| `schema_version` mismatch warning | A new emit's `schema_version` differs from the existing file | Re-emit overwrites; back up first if you've hand-edited the frontmatter. |

## Example end-to-end

```bash
$ health sync --source garmin
{"source": "garmin", "samples_ingested": 1437, ...}

$ health daily-note --format human
/Users/broomva/broomva-vault/07-Health/2026-05-22.md

$ head -22 /Users/broomva/broomva-vault/07-Health/2026-05-22.md
---
schema_version: 1
date: 2026-05-22
sources_synced: [garmin]
hrv_overnight_ms: 58.4
...
---
```
