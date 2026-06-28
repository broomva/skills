"""ForecastStrategy — turn any return-forecaster into a Strategy (BRO-1374).

A ``Forecaster`` predicts the fractional return of close over the next ``horizon``
bars; ``ForecastStrategy`` turns that into enter_long / exit / hold via a tunable
threshold. **Dep-free core**: the forecaster is a Protocol, so a fake (for tests) or a
foundation model (Kronos, via the optional adapter) plug in identically — and a
foundation-model forecaster is then judged by the SAME walk-forward + OOS holdout +
scheduler + roster as a rule-based strategy.

The honest point (BRO-1374 / tool/kronos): directional accuracy is not profit. A model
that forecasts direction 60% of the time may still fail to clear costs and the
generalization gate. ForecastStrategy is the bridge that lets our harness decide.

A ForecastStrategy is scored by the SAME ``walk_forward`` + ``score`` harness as any
Strategy (real + tested — see test_forecast_strategy.py). Its params are int-typed
(``horizon``, ``threshold_bps``) so a future optimize/schedule ``ParamSpace`` *can*
grid them — but that factory is **not wired yet**: unlike a rule-based strategy, a
ForecastStrategy can't be built from an int dict alone (it needs a live ``Forecaster``),
so the factory must supply the forecaster via closure. Tracked as a follow-up; today the
honest integration is harness scoring, not grid optimization.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from .base import Strategy
from .types import Bar, MarketState, Signal


@runtime_checkable
class Forecaster(Protocol):
    """Predicts the fractional return of close over a horizon. May be stochastic for
    ML models — adapters should seed for reproducibility (the Strategy contract wants
    same-state → same-signal)."""

    @property
    def name(self) -> str: ...

    def predict_return(self, bars: Sequence[Bar], horizon: int) -> float:
        """Predicted fractional return of close over the next ``horizon`` bars
        (e.g. 0.02 = +2%)."""
        ...


class ForecastStrategy(Strategy):
    """Wrap a return-Forecaster as a long-only Strategy via a basis-point threshold."""

    def __init__(
        self,
        forecaster: Forecaster,
        *,
        horizon: int = 5,
        threshold_bps: int = 100,
        min_bars: int = 120,
    ) -> None:
        if horizon < 1:
            raise ValueError("horizon must be >= 1")
        if threshold_bps < 0:
            raise ValueError("threshold_bps must be >= 0")
        if min_bars < 1:
            raise ValueError("min_bars must be >= 1")
        self._forecaster = forecaster
        self._horizon = horizon
        self._threshold_bps = threshold_bps
        self._threshold = threshold_bps / 10_000.0
        self._min_bars = min_bars

    @property
    def name(self) -> str:
        return f"forecast-{self._forecaster.name}-h{self._horizon}-t{self._threshold_bps}bps"

    @property
    def warmup(self) -> int:
        return self._min_bars

    def signal(self, state: MarketState) -> Signal:
        if len(state.bars) < self._min_bars:
            return Signal(action="hold", reason="warmup")
        pred = self._forecaster.predict_return(state.bars, self._horizon)
        if pred > self._threshold:
            # Confidence as a real gradient: ~0.5 just past the threshold → 1.0 at 2x
            # threshold (the naive abs(pred)/threshold saturates to a constant 1.0 since
            # pred>threshold already, which would carry no information).
            conf = min(1.0, abs(pred) / (2 * self._threshold)) if self._threshold > 0 else 1.0
            return Signal(
                action="enter_long",
                reason=f"forecast +{pred:.4f} > {self._threshold:.4f}",
                confidence=conf,
            )
        if pred < -self._threshold:
            return Signal(action="exit", reason=f"forecast {pred:.4f} < -{self._threshold:.4f}")
        return Signal(action="hold", reason=f"forecast {pred:.4f} within band")
