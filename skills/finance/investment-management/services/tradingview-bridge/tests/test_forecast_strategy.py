"""Tests for ForecastStrategy + the Forecaster Protocol (forecast.py).

The forecaster is faked (deterministic) so CI never imports torch/Kronos. The full
pipeline integration (walk_forward + score on a ForecastStrategy) is exercised here.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence

import pytest

from tradingview_bridge.barsource import synthetic_bars
from tradingview_bridge.evaluation.score import score_walk_forward
from tradingview_bridge.evaluation.walk_forward import walk_forward
from tradingview_bridge.strategy.forecast import Forecaster, ForecastStrategy
from tradingview_bridge.strategy.types import Bar, MarketState

_TORCH = importlib.util.find_spec("torch") is not None


class _FakeForecaster:
    """Deterministic forecaster. `fn(n_bars) -> predicted_return` lets a test make it
    stateful (e.g. long early, exit late) without any model."""

    def __init__(self, fn, name: str = "fake") -> None:
        self._fn = fn
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def predict_return(self, bars: Sequence[Bar], horizon: int) -> float:
        return self._fn(len(bars))


def _state(n: int) -> MarketState:
    return MarketState(symbol="X", asset_class="stock", bars=tuple(synthetic_bars(n)))


def test_protocol_runtime_check() -> None:
    assert isinstance(_FakeForecaster(lambda _n: 0.0), Forecaster)


def test_enter_long_above_threshold() -> None:
    strat = ForecastStrategy(_FakeForecaster(lambda _n: 0.02), threshold_bps=100, min_bars=10)
    assert strat.signal(_state(50)).action == "enter_long"  # +2% > 1%


def test_exit_below_negative_threshold() -> None:
    strat = ForecastStrategy(_FakeForecaster(lambda _n: -0.02), threshold_bps=100, min_bars=10)
    assert strat.signal(_state(50)).action == "exit"


def test_hold_within_band() -> None:
    strat = ForecastStrategy(_FakeForecaster(lambda _n: 0.005), threshold_bps=100, min_bars=10)
    assert strat.signal(_state(50)).action == "hold"  # +0.5% within ±1%


def test_hold_during_warmup() -> None:
    strat = ForecastStrategy(_FakeForecaster(lambda _n: 0.05), min_bars=120)
    assert strat.signal(_state(30)).action == "hold"  # < min_bars → warmup hold


def test_name_encodes_params() -> None:
    strat = ForecastStrategy(
        _FakeForecaster(lambda _n: 0.0, name="kronos-small"), horizon=5, threshold_bps=150
    )
    assert strat.name == "forecast-kronos-small-h5-t150bps"


def test_validation() -> None:
    f = _FakeForecaster(lambda _n: 0.0)
    with pytest.raises(ValueError, match="horizon"):
        ForecastStrategy(f, horizon=0)
    with pytest.raises(ValueError, match="threshold"):
        ForecastStrategy(f, threshold_bps=-1)
    with pytest.raises(ValueError, match="min_bars"):
        ForecastStrategy(f, min_bars=0)


def test_integration_walk_forward_and_score() -> None:
    """A ForecastStrategy runs through the SAME walk_forward + score as any strategy —
    the whole point: an (ML) forecaster is judged by our honest harness. Fake forecaster
    goes long for the first half, exits in the second → a complete round-trip."""
    bars = synthetic_bars(300)
    fake = _FakeForecaster(lambda n: 0.03 if n < 150 else -0.03, name="fake")
    strat = ForecastStrategy(fake, horizon=5, threshold_bps=100, min_bars=20)
    wf = walk_forward(strat, bars, symbol="X", asset_class="stock", n_windows=4)
    assert wf.full.n_trades >= 1  # it actually traded
    score = score_walk_forward(wf)
    assert 0.0 <= score.overall <= 1.0  # produces a valid, honest score


def test_confidence_is_a_gradient() -> None:
    """enter_long confidence scales with signal strength (~0.5 just past the threshold →
    1.0 at 2x threshold), not a constant — regression guard against the dead-1.0 calc."""
    weak = ForecastStrategy(_FakeForecaster(lambda _n: 0.0101), threshold_bps=100, min_bars=10)
    strong = ForecastStrategy(_FakeForecaster(lambda _n: 0.02), threshold_bps=100, min_bars=10)
    s_weak = weak.signal(_state(50))
    s_strong = strong.signal(_state(50))
    assert s_weak.action == "enter_long"
    assert s_strong.action == "enter_long"
    assert s_weak.confidence < s_strong.confidence  # gradient, not constant
    assert s_strong.confidence == 1.0  # 0.02 / (2 * 0.01)
    assert 0.5 <= s_weak.confidence < 0.6  # ~0.505


@pytest.mark.skipif(_TORCH, reason="torch installed; the not-installed path can't be exercised")
def test_kronos_adapter_requires_extra() -> None:
    """Without the [kronos] extra (no torch), constructing KronosForecaster raises a
    clear, actionable error — not a bare ImportError."""
    from tradingview_bridge.strategy.kronos_adapter import KronosForecaster

    with pytest.raises(RuntimeError, match="kronos"):
        KronosForecaster()


@pytest.mark.skipif(
    not _TORCH or importlib.util.find_spec("pandas") is None,
    reason="predict_return needs torch+pandas (the [kronos] extra); CI never installs it",
)
def test_kronos_predict_return_math_with_fake_predictor() -> None:
    """Exercise KronosForecaster.predict_return's MATH — timestamp synthesis, the return
    calc, and the guards — WITHOUT loading a real model (inject a fake predictor). The
    fake-forecaster tests above bypass this method entirely, so this is its only coverage.
    Skipped in CI (which never installs the [kronos] extra)."""
    import pandas as pd

    from tradingview_bridge.strategy.kronos_adapter import KronosForecaster

    # Bypass __init__ (which loads HF models) — set only what predict_return reads.
    fc = object.__new__(KronosForecaster)
    fc._sample_count = 1
    fc._temperature = 1.0
    fc._top_p = 0.9
    fc._lookback = 400
    fc._seed = 0

    class _FakePredictor:
        def predict(self, *, df, y_timestamp, pred_len, **kw):  # type: ignore[no-untyped-def]
            last = float(df["close"].to_numpy()[-1])
            # forecast close = +10% over the last input close, for every horizon step
            return pd.DataFrame({"close": [last * 1.10] * pred_len})

    fc._predictor = _FakePredictor()

    bars = synthetic_bars(50)
    pred = fc.predict_return(bars, horizon=5)
    assert abs(pred - 0.10) < 1e-6  # +10% forecast close → +0.10 fractional return

    # <2-bar guard returns 0.0 without calling the predictor
    assert fc.predict_return(bars[:1], horizon=5) == 0.0
