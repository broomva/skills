"""RCS Lyapunov functions for the microgrid testbed — construct-validity fix.

The original microRCS testbed used proxy quantities (e.g. step counters, action
diffs) as stand-ins for Lyapunov functions. Those proxies cannot be checked
against the paper's analytic stability margins λᵢ at L0/L1/L2/L3 because they
have no physical meaning.

This module replaces the proxies with **real Lyapunov functions** — physical,
non-negative scalars that are zero at the system setpoint and grow with
deviation from it. Each Vᵢ is measurable from the microgrid simulation
(`scenario.HourState`, `controllers.DispatchAction`, `metrics.SimMetrics`) so
that, after a perturbation event, the recovery trajectory of Vᵢ(t) can be
fitted to V(0)·exp(-λ̂t) and λ̂ᵢ compared to the paper's

    λ₀ ≈ 1.455   (plant)
    λ₁ ≈ 0.411   (autonomic / three-pillar)
    λ₂ ≈ 0.069   (EGRI / parameter mutation)
    λ₃ ≈ 0.006   (governance)

`research/rcs/data/parameters.toml`. The construct-correct way to estimate λ̂ᵢ
is `fit_perturbation_recovery`, which fits ONLY on the recovery branch of a
trajectory after a perturbation event — fitting a stationary signal yields
spurious near-zero λ̂.

Pure stdlib + numpy. No I/O, no logging, no side effects.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

# A common floor for ratios that should be safe for division.
_EPS = 1e-12


# -----------------------------------------------------------------------------
# L0 — plant Lyapunov function
# -----------------------------------------------------------------------------


def v0(state: Any, action: Any, site: Any, soc_setpoint: float = 50.0) -> float:
    """L0 Lyapunov: battery SOC deviation from setpoint, normalized.

    .. math::

        V_0 = \\left(\\frac{SOC - SOC^{*}}{50}\\right)^2
              + \\left(\\frac{P_{\\text{shed}}}{P_{\\text{peak}}}\\right)^2

    Physical mapping:
      - First term: squared SOC deviation in units of half-tank. Reaches 1.0
        when the battery is empty (SOC=0) or full (SOC=100) given a 50% setpoint.
      - Second term: squared load-shed fraction relative to site peak load.
        Reaches 1.0 only when shedding equals the entire peak load.

    Range: roughly [0, ~2]. Zero IFF SOC is at setpoint AND no load shedding.
    The recovery rate of V₀ after a perturbation (cloud burst, load spike,
    diesel outage) IS the physical quantity that the paper's λ₀ ≈ 1.455 claims
    to govern.

    Args:
        state: An object with ``battery_soc_pct`` attribute (e.g. ``HourState``).
        action: An object with ``load_shed_kw`` attribute (e.g. ``DispatchAction``).
        site: An object with ``peak_load_kw`` attribute (e.g. ``SiteProfile``).
        soc_setpoint: Target SOC in percent (default 50.0).

    Returns:
        Non-negative scalar V₀.

    Examples:
        >>> class S: pass
        >>> st = S(); st.battery_soc_pct = 50.0
        >>> ac = S(); ac.load_shed_kw = 0.0
        >>> si = S(); si.peak_load_kw = 40.0
        >>> v0(st, ac, si)  # at setpoint, no shed
        0.0
        >>> st.battery_soc_pct = 0.0  # battery empty
        >>> round(v0(st, ac, si), 4)
        1.0
        >>> # monotonic in SOC deviation
        >>> st.battery_soc_pct = 25.0
        >>> a = v0(st, ac, si)
        >>> st.battery_soc_pct = 10.0
        >>> b = v0(st, ac, si)
        >>> b > a
        True
    """
    soc = float(getattr(state, "battery_soc_pct", soc_setpoint))
    shed = float(getattr(action, "load_shed_kw", 0.0))
    peak = float(getattr(site, "peak_load_kw", 1.0))
    peak = peak if peak > _EPS else 1.0

    soc_term = ((soc - soc_setpoint) / 50.0) ** 2
    shed_term = (max(0.0, shed) / peak) ** 2
    return float(soc_term + shed_term)


# -----------------------------------------------------------------------------
# L1 — autonomic / three-pillar Lyapunov function
# -----------------------------------------------------------------------------


def v1(rolling_state: dict) -> float:
    """L1 Lyapunov: rolling unserved load + battery cycle stress + mode churn.

    .. math::

        V_1 = \\left(\\frac{E_{\\text{unserved,24h}}}{50}\\right)^2
              + \\sigma_{\\text{cycle}}^2
              + \\left(\\frac{N_{\\text{mode,24h}}}{5}\\right)^2

    Physical mapping (autonomic three-pillar state — operational, energetic,
    cognitive):
      - ``unserved_24h_kwh / 50``: 50 kWh/24h is the order-of-magnitude budget
        for "marginal service" at small ZNI sites. Squared.
      - ``cycle_stress``: dimensionless [0,1] battery cycle-stress index already
        normalised by C-rate × DoD. Squared.
      - ``mode_switches_24h / 5``: per-day mode churn budget; >5 switches/day
        indicates the controller is hunting. Squared.

    Range: roughly [0, ~3]. Zero IFF no unserved load, no cycle stress, no
    mode churn. Recovery rate after perturbation is the L1 analogue measured
    against the paper's λ₁ ≈ 0.411.

    Missing keys default to 0.0 so callers can pass partial state.

    Examples:
        >>> v1({'unserved_24h_kwh': 0.0, 'cycle_stress': 0.0, 'mode_switches_24h': 0})
        0.0
        >>> # monotonic in unserved energy
        >>> a = v1({'unserved_24h_kwh': 5.0, 'cycle_stress': 0.1, 'mode_switches_24h': 1})
        >>> b = v1({'unserved_24h_kwh': 25.0, 'cycle_stress': 0.1, 'mode_switches_24h': 1})
        >>> b > a
        True
    """
    unserved = float(rolling_state.get("unserved_24h_kwh", 0.0))
    cycle_stress = float(rolling_state.get("cycle_stress", 0.0))
    mode_switches = float(rolling_state.get("mode_switches_24h", 0.0))

    unserved_term = (unserved / 50.0) ** 2
    cycle_term = cycle_stress ** 2
    mode_term = (mode_switches / 5.0) ** 2
    return float(unserved_term + cycle_term + mode_term)


# -----------------------------------------------------------------------------
# L2 — EGRI / parameter-mutation Lyapunov function
# -----------------------------------------------------------------------------


def v2(meta_state: dict) -> float:
    """L2 Lyapunov: parameter drift + mutation-effectiveness deficit.

    .. math::

        V_2 = \\| \\theta - \\theta_0 \\|_2 + (1 - p_{\\text{shadow}})^2

    Physical mapping (EGRI's job: explore parameters that improve the diesel
    objective without drifting too far from baseline):
      - ``param_drift_l2norm``: Euclidean drift of the active parameter vector
        from baseline θ₀ (e.g. SOC thresholds, hysteresis widths).
      - ``shadow_pass_rate ∈ [0, 1]``: fraction of mutations whose shadow
        evaluation improved on the diesel/cost objective. ``(1 - rate)²``
        penalises low effectiveness quadratically.
      - ``mutation_acceptance_rate`` is accepted as an input field but does
        not directly appear in V₂; it is recorded for diagnostics by callers.

    Range: roughly [0, ∞). Zero IFF parameters at baseline AND every mutation
    helps. Recovery rate after a deliberate parameter perturbation should
    match the paper's λ₂ ≈ 0.069.

    Examples:
        >>> v2({'param_drift_l2norm': 0.0, 'shadow_pass_rate': 1.0,
        ...     'mutation_acceptance_rate': 1.0})
        0.0
        >>> # monotonic in parameter drift
        >>> a = v2({'param_drift_l2norm': 0.1, 'shadow_pass_rate': 0.8,
        ...         'mutation_acceptance_rate': 0.5})
        >>> b = v2({'param_drift_l2norm': 1.0, 'shadow_pass_rate': 0.8,
        ...         'mutation_acceptance_rate': 0.5})
        >>> b > a
        True
    """
    drift = float(meta_state.get("param_drift_l2norm", 0.0))
    shadow_pass = float(meta_state.get("shadow_pass_rate", 1.0))
    # Clamp shadow_pass to [0, 1] for safety; outside that range the squared
    # deficit term loses its physical meaning.
    shadow_pass = max(0.0, min(1.0, shadow_pass))

    drift_term = max(0.0, drift)
    eff_term = (1.0 - shadow_pass) ** 2
    return float(drift_term + eff_term)


# -----------------------------------------------------------------------------
# L3 — governance Lyapunov function
# -----------------------------------------------------------------------------


def v3(governance_state: dict) -> float:
    """L3 Lyapunov: governance setpoint deviation + safety-floor breaches.

    .. math::

        V_3 = \\frac{(r - r^{*})^2}{(r^{*})^2} + N_{\\text{breach}}^2

    Physical mapping (governance's job: maintain mutation cadence at the
    desired rate with no safety violations):
      - First term: squared relative deviation of the observed mutation rate
        per week from the governance target (e.g. 1.0 mutations/week). The
        normalisation by ``target²`` makes it scale-free.
      - Second term: count of safety-floor breaches (squared). A single breach
        contributes 1; two contribute 4. Quadratic penalty so any breach
        dominates the steady-state cadence term.

    Range: roughly [0, ∞). Zero IFF mutation rate exactly on target AND zero
    safety breaches. Recovery rate matches the paper's λ₃ ≈ 0.006 — the
    narrowest stability margin in the hierarchy.

    Examples:
        >>> v3({'mutation_rate_per_week': 1.0, 'mutation_rate_target': 1.0,
        ...     'safety_floor_breaches': 0})
        0.0
        >>> # any safety breach dominates a small cadence drift
        >>> a = v3({'mutation_rate_per_week': 1.1, 'mutation_rate_target': 1.0,
        ...         'safety_floor_breaches': 0})
        >>> b = v3({'mutation_rate_per_week': 1.0, 'mutation_rate_target': 1.0,
        ...         'safety_floor_breaches': 1})
        >>> b > a
        True
    """
    rate = float(governance_state.get("mutation_rate_per_week", 0.0))
    target = float(governance_state.get("mutation_rate_target", 1.0))
    breaches = float(governance_state.get("safety_floor_breaches", 0))

    target_sq = target * target
    if target_sq < _EPS:
        # Degenerate target — fall back to absolute squared deviation.
        cadence_term = (rate - target) ** 2
    else:
        cadence_term = ((rate - target) ** 2) / target_sq
    breach_term = breaches ** 2
    return float(cadence_term + breach_term)


# -----------------------------------------------------------------------------
# Estimators — fit V(t) = V(0)·exp(-λ·t) on a recovery branch
# -----------------------------------------------------------------------------


def _coerce_arrays(times: list[float], v_values: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """Coerce inputs to numpy arrays, dropping non-finite samples."""
    t = np.asarray(times, dtype=float)
    v = np.asarray(v_values, dtype=float)
    if t.shape != v.shape:
        n = min(t.size, v.size)
        t = t[:n]
        v = v[:n]
    mask = np.isfinite(t) & np.isfinite(v)
    return t[mask], v[mask]


def fit_lambda(times: list[float], v_values: list[float]) -> tuple[float, float]:
    """Fit V(t) = V(0)·exp(-λ·t) by OLS on log(V) and bootstrap residuals.

    The log-linear OLS estimator is the standard one used to compare measured
    λ̂ against the paper's analytic λ. Bootstrap (200 resamples over fitted
    residuals) yields a standard error.

    Edge cases (returns ``(nan, nan)``):
      - Fewer than 3 finite samples.
      - All V values equal (slope undefined).
      - Any non-positive V after filtering (log undefined).
      - Time axis variance is zero.

    Examples:
        >>> import math
        >>> t = [0.0, 1.0, 2.0, 3.0]
        >>> v = [1.0, math.exp(-0.5), math.exp(-1.0), math.exp(-1.5)]
        >>> lam, se = fit_lambda(t, v)
        >>> abs(lam - 0.5) < 1e-6
        True
        >>> # constant V → nan
        >>> lam, se = fit_lambda([0.0, 1.0, 2.0], [1.0, 1.0, 1.0])
        >>> math.isnan(lam) and math.isnan(se)
        True
        >>> # too few points → nan
        >>> lam, se = fit_lambda([0.0], [1.0])
        >>> math.isnan(lam) and math.isnan(se)
        True
    """
    nan_pair: tuple[float, float] = (float("nan"), float("nan"))

    t, v = _coerce_arrays(times, v_values)
    if t.size < 3:
        return nan_pair

    # Drop non-positive V (log undefined). A common case is V=0 at the
    # setpoint; we let the recovery extractor cut the trajectory before then.
    pos = v > 0.0
    t = t[pos]
    v = v[pos]
    if t.size < 3:
        return nan_pair

    log_v = np.log(v)
    if float(np.var(log_v)) < _EPS:
        return nan_pair  # constant V
    if float(np.var(t)) < _EPS:
        return nan_pair  # zero time-axis variance

    # OLS: log V = a - λ t  ⇒  slope = -λ
    A = np.column_stack([np.ones_like(t), t])
    try:
        coef, *_ = np.linalg.lstsq(A, log_v, rcond=None)
    except np.linalg.LinAlgError:
        return nan_pair
    intercept, slope = float(coef[0]), float(coef[1])
    lambda_hat = -slope

    # Bootstrap standard error over residuals.
    fitted = intercept + slope * t
    residuals = log_v - fitted
    if residuals.size < 2:
        return float(lambda_hat), float("nan")

    rng = np.random.default_rng(seed=0)
    n_boot = 200
    estimates = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        resampled = fitted + rng.choice(residuals, size=residuals.size, replace=True)
        try:
            c, *_ = np.linalg.lstsq(A, resampled, rcond=None)
            estimates[i] = -float(c[1])
        except np.linalg.LinAlgError:
            estimates[i] = np.nan

    estimates = estimates[np.isfinite(estimates)]
    if estimates.size < 2:
        return float(lambda_hat), float("nan")
    std_err = float(np.std(estimates, ddof=1))
    return float(lambda_hat), std_err


def fit_perturbation_recovery(
    times: list[float],
    v_values: list[float],
    perturbation_t: float,
) -> tuple[float, float]:
    """Fit V(t) = V(0)·exp(-λ·t) on the recovery branch ONLY.

    Filters samples to ``t > perturbation_t``, then re-zeroes the time axis at
    the perturbation event before delegating to :func:`fit_lambda`. This is
    the construct-correct way to measure λᵢ: only fit on the recovery branch,
    not stationary signal. Fitting all-time data of a stationary trajectory
    would yield λ̂ ≈ 0 even when the underlying system has fast recovery.

    Returns ``(nan, nan)`` if fewer than 3 samples remain after filtering.

    Examples:
        >>> import math
        >>> # Build a trajectory: stationary, then perturbation at t=10, then
        >>> # recovery with λ=1.45 (the paper's L0).
        >>> t_pre = [i * 0.5 for i in range(20)]      # 0..9.5, stationary
        >>> v_pre = [0.0] * len(t_pre)                # at setpoint
        >>> t_post = [10.0 + i * 0.1 for i in range(20)]  # recovery
        >>> v_post = [math.exp(-1.45 * (ti - 10.0)) for ti in t_post]
        >>> times = t_pre + t_post
        >>> values = v_pre + v_post
        >>> lam, se = fit_perturbation_recovery(times, values, perturbation_t=10.0)
        >>> abs(lam - 1.45) < 1e-3
        True
    """
    nan_pair: tuple[float, float] = (float("nan"), float("nan"))

    t, v = _coerce_arrays(times, v_values)
    if t.size == 0:
        return nan_pair

    mask = t > perturbation_t
    t_post = t[mask]
    v_post = v[mask]
    if t_post.size < 3:
        return nan_pair

    # Re-zero the time axis at the perturbation so V(0) corresponds to the
    # first recovery sample. This is required for the slope to be -λ.
    t_zeroed = t_post - perturbation_t
    return fit_lambda(t_zeroed.tolist(), v_post.tolist())


# -----------------------------------------------------------------------------
# Convenience helpers
# -----------------------------------------------------------------------------


def battery_recovery_window(
    soc_history: list[tuple[float, float]],
    perturbation_t: float,
    steady_state_window: float = 1800.0,
    soc_setpoint: float = 50.0,
) -> tuple[list[float], list[float]]:
    """Extract the recovery branch of SOC after a perturbation.

    Given a list of ``(time_seconds, soc_pct)`` samples, returns
    ``(times, V₀_values)`` covering the recovery branch suitable for
    :func:`fit_perturbation_recovery`. The returned slice:

      1. Starts at the first sample with ``t > perturbation_t``.
      2. Ends at the FIRST of:
         - the time SOC returns within 1% of ``soc_setpoint`` (recovery done);
         - ``steady_state_window`` seconds after the perturbation.

    V₀ is computed as the SOC term of :func:`v0` only (no load-shed, no site)
    since the helper is meant to characterise the battery-level recovery in
    isolation.

    Examples:
        >>> import math
        >>> # Build SOC history: at setpoint, perturb at t=100 to 30%, recover
        >>> # exponentially with rate 1.0/s back toward 50%.
        >>> hist = []
        >>> for i in range(10):
        ...     hist.append((i * 1.0, 50.0))   # stationary
        >>> for i in range(60):
        ...     ti = 100.0 + i * 1.0
        ...     soc = 50.0 - 20.0 * math.exp(-1.0 * (ti - 100.0))
        ...     hist.append((ti, soc))
        >>> ts, vs = battery_recovery_window(hist, perturbation_t=100.0)
        >>> len(ts) >= 3 and len(ts) == len(vs)
        True
        >>> ts[0] > 100.0 and all(v >= 0 for v in vs)
        True
    """
    if not soc_history:
        return [], []

    end_t = perturbation_t + steady_state_window
    out_t: list[float] = []
    out_v: list[float] = []

    for ti, soc in soc_history:
        try:
            ti_f = float(ti)
            soc_f = float(soc)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(ti_f) and math.isfinite(soc_f)):
            continue
        if ti_f <= perturbation_t:
            continue
        if ti_f > end_t:
            break

        # SOC term of V₀ only.
        v_val = ((soc_f - soc_setpoint) / 50.0) ** 2
        out_t.append(ti_f)
        out_v.append(v_val)

        # Cut off when SOC returns within 1% of setpoint (recovery done).
        if abs(soc_f - soc_setpoint) <= 1.0:
            break

    return out_t, out_v
