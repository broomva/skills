# TrainingLoad — Coggan CTL/ATL/TSB analysis

**When invoked:** the user asks about freshness, fatigue, race readiness, "should I push harder this week", "am I overreached", or any training-load framing.

## Command

```bash
health context --metric ctl,atl,tsb --days 90 [--format json]
```

This pulls the daily CTL/ATL/TSB series for the last 90 days, computed by `synthesis.training_load.compute_ctl_atl_tsb` from the raw `Workout.training_stress_score` values in the trace DB.

## The model (one-line summary)

| Metric | Window | Proxy for | Rule of thumb |
|---|---|---|---|
| **CTL** — Chronic Training Load | 42-day EWMA of daily TSS | **Fitness** | Rises slowly with sustained load; falls slowly when you taper |
| **ATL** — Acute Training Load | 7-day EWMA of daily TSS | **Fatigue** | Rises fast with hard weeks; recovers in days |
| **TSB** — Training Stress Balance | `CTL − ATL` | **Freshness** | Positive = rested; negative = fatigued; -10 to -30 = overreached |

EWMA constant: `α = 2 / (N + 1)` — `α_ctl = 2/43 ≈ 0.0465`, `α_atl = 2/8 = 0.25`. Each day's update: `ctl[t] = ctl[t-1] + α × (tss[t] - ctl[t-1])`. The synthesis layer warms up over a 60-day pre-window so the initial-zero seed has decayed before any value is reported.

## TSB interpretation table

| TSB range | Common label | What it means |
|---|---|---|
| **+25 and up** | "Detraining risk" | Fresh but losing fitness — fine for race day, costly for weeks |
| **+5 to +25** | "Race-ready" | Peak performance window |
| **−10 to +5** | "Productive training" | Building fitness without digging a hole |
| **−10 to −30** | "Overreaching" | Functional in the short term; planned recovery needed within 1–2 weeks |
| **Below −30** | "Overtraining risk" | Sustained → injury / illness / non-functional overreaching |

Numbers are heuristic. Individual tolerance varies; the curves matter more than any single value.

## Reference

Andy Coggan & Hunter Allen, *Training and Racing with a Power Meter* (3rd ed., VeloPress 2019). The Performance Management Chart formalism (CTL/ATL/TSB EWMA-from-TSS) is the canonical training-load model in endurance sports literature and is what TrainingPeaks, Intervals.icu, and many open-source tools implement.

URL: https://www.trainingpeaks.com/learn/articles/the-science-of-the-performance-manager/

## Why not vendor scores?

Garmin's "Training Load" is a black-box composite — it bundles TSS-like load with HR variability, recovery time estimates, and other inputs. It's not directly comparable across people, devices, or even firmware versions. CTL/ATL/TSB are transparent, auditable, standardized across the literature. The synthesis layer recomputes them from raw `training_stress_score` per workout rather than ingesting any vendor "load" number.

If the trace has workouts without a `training_stress_score` (e.g. yoga, walks without power data), those are silently skipped. This is correct — they don't contribute to TSS-based load — but it does mean "load" here is a *training-stress* proxy, not an *energy-expenditure* proxy.

## Composition

- After a [Sync](Sync.md), CTL/ATL/TSB in the [DailyNote](DailyNote.md) frontmatter reflect today's values.
- For longer arcs (90d window plotted), use `health context --metric ctl,atl,tsb --days 90 --format csv` and pipe to your plotter of choice.
- Telos integration: `MODELS.md` references Coggan PMC; agent should treat CTL/ATL/TSB as **[HIGH]**-confidence per [References/validation-evidence.md](../References/validation-evidence.md).

## Failure modes

| Symptom | Cause | Action |
|---|---|---|
| CTL/ATL/TSB all 0 | No workouts with `training_stress_score` in history | Verify the source actually populates TSS (Garmin does for activities with power data; not for steps/walks). |
| TSB jumps wildly day-to-day | Insufficient warmup history | Backfill ≥ 60 days; the synthesis seeds CTL=0, ATL=0 and walks forward — recent EWMA values stabilize after ~30 days of history. |
| Numbers don't match TrainingPeaks | Different TSS source (Garmin's vs. uploaded power-based) | Confirm which TSS Garmin is reporting; we read whatever the API returns. |

## Example

```bash
$ health context --metric ctl,atl,tsb --days 7 --format human
                       Training Load (Coggan)
┌────────────┬──────────────┬──────────────┬──────────────┐
│ date       │ ctl (tss/d)  │ atl (tss/d)  │ tsb (tss/d)  │
├────────────┼──────────────┼──────────────┼──────────────┤
│ 2026-05-16 │ 52.1         │ 64.3         │ -12.2        │
│ 2026-05-17 │ 52.4         │ 68.7         │ -16.3        │
│ 2026-05-18 │ 52.7         │ 69.1         │ -16.4        │
│ 2026-05-19 │ 53.0         │ 65.2         │ -12.2        │
│ 2026-05-20 │ 53.4         │ 72.5         │ -19.1        │
│ 2026-05-21 │ 53.8         │ 73.0         │ -19.2        │
│ 2026-05-22 │ 54.2         │ 71.8         │ -17.6        │
└────────────┴──────────────┴──────────────┴──────────────┘
```
