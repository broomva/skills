# RecoveryReview — 7-day recovery composite

**When invoked:** weekly review, after illness or hard block, when the user asks "am I recovering well", "should I push this week", "what's my readiness trend" — any *recovery* framing.

## Command

```bash
health context --window 7d --metric hrv_cv,rhr,sleep [--format json]
```

This pulls a 7-day rollup composing four signals — three [HIGH]-confidence per-component, plus a custom composite — described below.

## The four signals

### 1. HRV-CV (30-day, anchored to today)

Coefficient of variation of overnight HRV over the trailing 30 days, computed by `synthesis.hrv.compute_hrv_cv`.

```
HRV-CV = stdev(overnight_hrv[-30d:]) / mean(overnight_hrv[-30d:])
```

- **Low and stable (< 0.10)** — autonomic nervous system well-regulated. Good baseline.
- **Rising trend** — systemic disturbance. Possible: overtraining, illness onset, sleep debt, psychological stress.
- **< 7 samples in window** → returns `None`. We refuse to lie when underdetermined.

Confidence: **[HIGH]** — see [validation-evidence.md](../References/validation-evidence.md) §Galpin/WHOOP-2026.

### 2. RHR trend (7-day median)

Resting heart rate, median over the last 7 days. A rising RHR (5+ bpm above 30-day baseline) often precedes detectable illness by 24–48 hours and is a classic overreaching marker.

Confidence: **[HIGH]** — widely replicated in athlete-monitoring literature.

### 3. Sleep architecture (7-day rollup)

| Component | Metric | Confidence |
|---|---|---|
| Sleep duration | `SLEEP_DURATION` median (hours) | **[HIGH]** — total time is reliable |
| Sleep score | `SLEEP_SCORE` median | **[MED]** — vendor composite |
| Sleep stages | `SLEEP_STAGE` (deep, REM, light, awake) durations | **[MED]** — wearable staging is 51.5% accurate for slow-wave detection in validation studies |

We surface sleep duration and a *qualitative* stage breakdown, but flag the staging accuracy explicitly to the user.

### 4. Custom recovery composite

A transparent linear combination — **our own**, not a vendor score:

```
recovery_composite = (
    1.0 * z_score(hrv_overnight)         # acute HRV vs. own baseline
  - 1.0 * z_score(rhr)                   # higher RHR = worse
  + 0.5 * z_score(sleep_hours)           # longer sleep = better
  + 0.5 * z_score(sleep_score)           # higher score = better
)
```

z-scores are computed against each athlete's own 60-day baseline. Output is in standard deviations — `+1.5` means "today is 1.5σ better than your trailing baseline."

**Explicit invariant: vendor recovery scores are stored as opaque.** Garmin's Body Battery, Training Readiness, Whoop Recovery, Oura Readiness — all are stored in the trace DB under their canonical `MetricCode` (e.g. `BODY_BATTERY`) but **we do not surface them as the answer** to "how recovered am I". Reasoning per Altini and others: vendor recovery scores are unvalidated "made up scores" — see [validation-evidence.md](../References/validation-evidence.md) §vendor-scores. We compute the composite above transparently so the agent can explain *why* the number is what it is.

## Output (success)

```json
{
  "window": "7d",
  "anchor": "2026-05-22",
  "hrv_cv_30d": 0.082,
  "hrv_cv_trend": "stable",
  "rhr_median_bpm": 51,
  "rhr_delta_vs_baseline_bpm": -1.2,
  "sleep_hours_median": 7.4,
  "sleep_score_median": 84,
  "recovery_composite_z": 0.6,
  "vendor_scores_opaque": {
    "body_battery_median": 64,
    "training_readiness_median": 71
  }
}
```

## P15 Snapshot preflight

Recovery analysis requires fresh data — run [Status](Status.md) first. If `last_sync` is older than 24h, sync before reviewing. A 7-day review against stale data is worse than no review (you'll act on yesterday's overreach as if it were today's).

## Composition

- For race readiness specifically, combine with [TrainingLoad](TrainingLoad.md) — TSB > 0 *and* recovery composite > 0 is the green-light pair.
- For VO2max trend over the same period, see [VO2maxArc](VO2maxArc.md) (but: VO2max moves on a much longer timescale; weekly variation is noise).
- For Telos integration, write a synthesis note under `research/notes/YYYY-MM-DD-recovery-synthesis.md` only when the rule-of-three concrete pattern triggers (e.g. "3 consecutive weeks of rising HRV-CV → illness"). Routine reviews stay ephemeral.

## Failure modes

| Symptom | Cause | Action |
|---|---|---|
| `hrv_cv_30d = null` | Fewer than 7 overnight HRV samples in trailing 30 days | Sync more history; wear the device to bed; if device has no HRV sensor, document the limitation. |
| `recovery_composite_z = null` | Fewer than 14 days of joint HRV + RHR baseline | Wait for baseline to fill (~2 weeks of consistent wear). |
| Trend label ("stable" / "rising" / "falling") wildly inconsistent | Adapter is supplying nap HRV instead of overnight | Re-check the source's HRV filter (Garmin returns night-only by default; some adapters expose all readings). |

## Example

```bash
$ health context --window 7d --metric hrv_cv,rhr,sleep --format human
                       7-Day Recovery Review
┌──────────────────────────────────┬──────────────────┐
│ key                              │ value            │
├──────────────────────────────────┼──────────────────┤
│ window                           │ 7d               │
│ anchor                           │ 2026-05-22       │
│ hrv_cv_30d                       │ 0.082            │
│ hrv_cv_trend                     │ stable           │
│ rhr_median_bpm                   │ 51               │
│ rhr_delta_vs_baseline_bpm        │ -1.2             │
│ sleep_hours_median               │ 7.4              │
│ sleep_score_median               │ 84               │
│ recovery_composite_z             │ 0.6              │
└──────────────────────────────────┴──────────────────┘
```
