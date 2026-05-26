"""VO2max arc synthesis — long-window aggregation of cardiorespiratory fitness.

**Why a VO2max arc?**

Per Peter Attia's longevity framework (Outlive ch. 11): of all the
modifiable markers we have decent epidemiology on, VO2max is the single
most powerful predictor of all-cause mortality. Moving from the bottom
25th percentile to the top 25th percentile is associated with roughly a
5× reduction in all-cause mortality risk — a larger effect than smoking
cessation, statins, or any single dietary intervention studied to date.

Single VO2max readings on a wearable are noisy (Garmin's estimate
fluctuates ±2 ml/kg/min day-to-day depending on the recent activity mix).
The actionable signal is the long-window arc — quarterly or yearly
aggregates that smooth the noise and reveal the multi-year trajectory.

This module buckets raw VO2max samples by quarter (or month/year) and
returns the mean per bucket. We do NOT do any smoothing beyond bucket-
averaging — downstream projection layers can plot the arc or fit a
trend line if needed.

**Bucket key format** (sortable lexicographically):
- `"month"` → `"2026-01"`, `"2026-02"`, …
- `"quarter"` → `"2026-Q1"`, `"2026-Q2"`, …
- `"year"` → `"2026"`, `"2027"`, …
"""

from __future__ import annotations

from statistics import mean
from typing import Literal

from broomva_health.domain.samples import QuantitySample

__all__ = ["compute_vo2max_arc"]

Bucket = Literal["month", "quarter", "year"]


def _bucket_key(sample: QuantitySample, bucket: Bucket) -> str:
    """Map a sample to its bucket key. Uses `start_ts` (UTC)."""
    ts = sample.start_ts
    if bucket == "year":
        return f"{ts.year:04d}"
    if bucket == "month":
        return f"{ts.year:04d}-{ts.month:02d}"
    # quarter
    quarter = (ts.month - 1) // 3 + 1
    return f"{ts.year:04d}-Q{quarter}"


def compute_vo2max_arc(
    samples: list[QuantitySample], *, bucket: Bucket = "quarter"
) -> dict[str, float]:
    """Bucket VO2max samples and return the mean per bucket.

    Args:
        samples: VO2_MAX samples. Filter at the call site by metric;
            this function does NOT inspect `sample.metric`.
        bucket: Aggregation granularity. Default `"quarter"` matches the
            Attia quarterly-tracking cadence.

    Returns:
        `{bucket_key: mean_vo2max}` sorted by key (Python 3.7+ dict
        insertion order preserves the chronological sort).
        Empty input → empty dict.

    Notes:
        - Bucket means are computed from raw values — no outlier removal,
          no detrending. The synthesis layer is intentionally thin.
        - Empty buckets are not represented (no zero-fill for quarters
          with no readings). Downstream consumers that need a continuous
          time series should fill gaps themselves.
    """
    if not samples:
        return {}

    buckets: dict[str, list[float]] = {}
    for s in samples:
        key = _bucket_key(s, bucket)
        buckets.setdefault(key, []).append(s.value)

    # Sort by key (year-first format → chronological).
    return {k: mean(buckets[k]) for k in sorted(buckets)}
