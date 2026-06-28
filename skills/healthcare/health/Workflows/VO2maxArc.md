# VO2maxArc — long-window cardiorespiratory fitness trajectory

**When invoked:** quarterly review, longevity tracking, "what's my VO2max trend", "am I getting fitter year-over-year".

## Command

```bash
health context --metric vo2_max --bucket {month|quarter|year} [--format json]
```

Computed by `synthesis.vo2max.compute_vo2max_arc` — buckets raw VO2max samples by quarter (default), month, or year, and returns the mean per bucket. Single-day VO2max readings on a wearable fluctuate ±2 ml/kg/min depending on the recent activity mix — the actionable signal is the **long-window arc**, not any one reading.

## Why this matters (Attia framing)

Per Peter Attia's longevity framework (*Outlive*, chapter 11): of all the modifiable markers with decent epidemiology, **VO2max is the single most powerful predictor of all-cause mortality.**

Moving from the bottom 25th percentile to the top 25th percentile of VO2max is associated with roughly a **5× reduction in all-cause mortality risk** — a larger effect than smoking cessation, statins, or any single dietary intervention studied to date.

Source: Mandsager K. et al., *Association of Cardiorespiratory Fitness With Long-term Mortality Among Adults Undergoing Exercise Treadmill Testing*. JAMA Network Open, 2018. https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2707428

Discussed extensively in Peter Attia, *Outlive: The Science and Art of Longevity* (2023), and on The Drive podcast (peterattiamd.com).

Confidence: **[HIGH]** — see [validation-evidence.md](../References/validation-evidence.md) §VO2max.

## Output

```json
{
  "bucket": "quarter",
  "series": {
    "2024-Q1": 49.2,
    "2024-Q2": 50.1,
    "2024-Q3": 51.4,
    "2024-Q4": 51.0,
    "2025-Q1": 51.9,
    "2025-Q2": 52.4,
    "2025-Q3": 52.1,
    "2025-Q4": 52.7,
    "2026-Q1": 52.9,
    "2026-Q2": 52.1
  }
}
```

## Semantics

- Bucket means are computed from raw values — no outlier removal, no detrending.
- Empty buckets (quarters with no readings) are **not** zero-filled; the dict skips them. Downstream consumers needing a continuous time series should fill gaps explicitly.
- The synthesis layer is intentionally thin — plotting, trend-fitting, percentile-lookup are projection-layer or analysis-layer concerns.

## Composition

- For percentile context (am I top-25% for my age/sex?), join the bucket means against the Cooper Clinic or FRIEND reference tables — *not* implemented in v1. The skill returns the raw arc; percentile lookup is a downstream analysis task.
- For DailyNote integration, the latest VO2max sample for the day is surfaced as `vo2_max` in the frontmatter — but the arc itself is a separate read (the daily note is point-in-time; the arc is window-aggregated).
- For Telos GOALS integration, a quarterly VO2max bucket can be checked against a long-arc GOAL value (e.g. "VO2max ≥ 55 by 2027-Q1") with the bucket key as the time axis.

## Failure modes

| Symptom | Cause | Action |
|---|---|---|
| Empty `series` | No VO2max samples in history | Garmin estimates VO2max only after sufficient outdoor running with HR; ensure your activity history populates it. |
| Wildly oscillating quarterly means | Inconsistent measurement (FIT-imported manual values mixed with watch estimates) | Verify the source of VO2max samples — adapter should flag manual vs estimated in `metadata`. |
| Single-quarter buckets only | Backfill incomplete | Run a longer [Backfill](Backfill.md) to populate prior quarters. |

## Example

```bash
$ health context --metric vo2_max --bucket quarter --format human
            VO2max Arc (quarterly mean)
┌─────────────┬────────────────────────┐
│ bucket      │ vo2_max (ml/kg/min)    │
├─────────────┼────────────────────────┤
│ 2024-Q1     │ 49.2                   │
│ 2024-Q2     │ 50.1                   │
│ 2024-Q3     │ 51.4                   │
│ 2024-Q4     │ 51.0                   │
│ 2025-Q1     │ 51.9                   │
│ 2025-Q2     │ 52.4                   │
│ 2025-Q3     │ 52.1                   │
│ 2025-Q4     │ 52.7                   │
│ 2026-Q1     │ 52.9                   │
│ 2026-Q2     │ 52.1                   │
└─────────────┴────────────────────────┘
```
