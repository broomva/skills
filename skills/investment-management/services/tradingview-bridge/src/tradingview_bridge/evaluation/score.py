"""score — a single 0-1 trustworthiness score per strategy, anti-overfit by design.

The orchestration layer ranks strategies on ``overall``. The decomposition is
deliberate: **consistency + robustness weigh half the score**, so a strategy with
a dazzling mean Sharpe but inconsistent windows or high dispersion scores LOW.
That is the anti-overfitting discipline made numeric — the system refuses to be
seduced by one lucky backtest.
"""

from __future__ import annotations

from dataclasses import dataclass

from .walk_forward import WalkForwardResult

# Default component weights (sum to 1.0). Consistency + robustness = 0.50.
DEFAULT_WEIGHTS: dict[str, float] = {
    "risk_adjusted": 0.35,
    "consistency": 0.30,
    "robustness": 0.20,
    "drawdown_safety": 0.15,
}


@dataclass(frozen=True)
class StrategyScore:
    """A strategy's trustworthiness, 0-1 overall, decomposed for inspection."""

    strategy: str
    risk_adjusted: float
    consistency: float
    robustness: float
    drawdown_safety: float
    overall: float
    rationale: str


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_walk_forward(
    wf: WalkForwardResult,
    *,
    sharpe_target: float = 2.0,
    dispersion_ref: float = 20.0,
    drawdown_ref: float = 30.0,
    weights: dict[str, float] | None = None,
) -> StrategyScore:
    """Score a walk-forward result. Higher = more trustworthy (0-1).

    Args:
        sharpe_target: Sharpe at which risk_adjusted saturates to 1.0.
        dispersion_ref: window-return std at which robustness hits 0.
        drawdown_ref: worst-window drawdown % at which drawdown_safety hits 0.
        weights: component weights (default DEFAULT_WEIGHTS). Must contain exactly
            the four DEFAULT_WEIGHTS keys; normalized to sum 1.0 before use so
            ``overall`` is guaranteed to stay in [0, 1].
    """
    if sharpe_target <= 0 or dispersion_ref <= 0 or drawdown_ref <= 0:
        raise ValueError("sharpe_target, dispersion_ref, and drawdown_ref must be > 0")
    raw = DEFAULT_WEIGHTS if weights is None else weights
    if set(raw) != set(DEFAULT_WEIGHTS):
        raise ValueError(f"weights must contain exactly these keys: {sorted(DEFAULT_WEIGHTS)}")
    total_weight = sum(raw.values())
    if total_weight <= 0:
        raise ValueError("weights must sum to a positive value")
    # Normalize so a convex combination of clamped [0,1] components stays in [0,1].
    w = {key: raw[key] / total_weight for key in DEFAULT_WEIGHTS}

    risk_adjusted = _clamp(wf.mean_sharpe / sharpe_target)
    consistency = _clamp(float(wf.consistency_pct) / 100.0)
    robustness = _clamp(1.0 - wf.return_std / dispersion_ref)
    worst_dd = float(wf.worst_window_drawdown_pct)
    drawdown_safety = _clamp(1.0 - worst_dd / drawdown_ref)

    # Clamp the final sum too: a convex combination of [0,1] components is
    # mathematically in [0,1], but float rounding can nudge it to 1.0000000002 —
    # clamp so the advertised 0-1 contract holds exactly.
    overall = _clamp(
        risk_adjusted * w["risk_adjusted"]
        + consistency * w["consistency"]
        + robustness * w["robustness"]
        + drawdown_safety * w["drawdown_safety"]
    )

    rationale = (
        f"sharpe {wf.mean_sharpe:.2f} (→{risk_adjusted:.2f}), "
        f"consistency {float(wf.consistency_pct):.0f}% (→{consistency:.2f}), "
        f"dispersion {wf.return_std:.1f} (→robustness {robustness:.2f}), "
        f"worst-DD {worst_dd:.1f}% (→{drawdown_safety:.2f})"
    )
    return StrategyScore(
        strategy=wf.strategy,
        risk_adjusted=risk_adjusted,
        consistency=consistency,
        robustness=robustness,
        drawdown_safety=drawdown_safety,
        overall=overall,
        rationale=rationale,
    )
