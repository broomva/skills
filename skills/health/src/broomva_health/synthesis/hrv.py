"""HRV coefficient-of-variation synthesis.

**Why HRV-CV and not raw HRV?**

The 2026 Galpin/WHOOP paper update on HRV interpretation (see
`References/validation-evidence.md`) makes the key point that absolute HRV
values are noisy and highly individual — comparing your 64 ms RMSSD to
someone else's 78 ms tells you nothing. What *is* actionable is the
*coefficient of variation* (CV) of your own overnight HRV over a stable
window (typically 30 days):

    HRV-CV = stdev(overnight_hrv[-30:]) / mean(overnight_hrv[-30:])

A *stable* HRV-CV (low value, broadly < 0.10) indicates your autonomic
nervous system is well-regulated. A *rising* HRV-CV signals systemic
disturbance — overtraining, illness onset, sleep debt accumulation,
psychological stress. CV is the actionable signal; the absolute number
is noise.

This module is pure and uses only the stdlib `statistics` package — we
intentionally do not pull numpy/pandas into the project dependencies.
The synthesis layer should remain a thin, dependency-light computation
layer over the trace store.
"""

from __future__ import annotations

from datetime import timedelta
from statistics import mean, stdev

from broomva_health.domain.samples import QuantitySample

__all__ = ["compute_hrv_cv"]

_MIN_SAMPLES = 7
"""Minimum overnight HRV samples required to produce a CV.

Below 7 the stdev estimate is too noisy to be meaningful; we return None
instead of a misleading number. Seven days is also the canonical "look
at trends, not single readings" floor used by WHOOP, Oura and Garmin.
"""


def compute_hrv_cv(
    samples: list[QuantitySample], *, window_days: int = 30
) -> float | None:
    """Coefficient of variation of overnight HRV over the trailing window.

    Args:
        samples: Overnight HRV samples (typically metric=HRV_OVERNIGHT).
            The function does NOT filter by metric — pass the already-filtered
            list. Order does not matter; we sort internally by `end_ts`.
        window_days: Length of the trailing window. Default 30 days follows
            Galpin/WHOOP's recommended trend window.

    Returns:
        `stdev(values) / mean(values)` over the window, or None if:
        - fewer than 7 samples fall inside the window
        - the mean of the window is 0 (degenerate — would divide by zero)

    Notes:
        - The window is anchored to `max(end_ts)` across the input — the
          "now" of the dataset, not wall-clock now. This makes the function
          deterministic and testable without freezing time.
        - We do NOT pre-filter for sleep nights with valid HRV — that's an
          adapter concern. We trust the caller to pass clean overnight HRV.
        - Values are taken as-is (we assume the canonical unit "ms" per
          METRIC_UNITS).
    """
    if not samples:
        return None

    sorted_samples = sorted(samples, key=lambda s: s.end_ts)
    anchor = sorted_samples[-1].end_ts
    cutoff = anchor - timedelta(days=window_days)

    values = [s.value for s in sorted_samples if s.end_ts > cutoff]

    if len(values) < _MIN_SAMPLES:
        return None

    avg = mean(values)
    if avg == 0:
        # Degenerate: a series of zeros has undefined CV.
        return None

    return stdev(values) / avg
