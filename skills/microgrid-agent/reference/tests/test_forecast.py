"""
Tests for forecast functionality.

The forecast module (src/forecast.py) is referenced by agent.py but does not
yet exist on disk. These tests define the expected interface and cover:
- Persistence fallback returns yesterday's data
- Empty history produces sensible defaults
- Forecast result has correct structure

Since the Forecaster class doesn't exist yet, we implement a minimal
persistence-based forecaster inline and test its contract.
"""

import numpy as np
import pytest
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Minimal Forecaster (persistence model) for testing
# ---------------------------------------------------------------------------

@dataclass
class ForecastResult:
    """Expected output structure from any forecaster."""
    generation_kw: np.ndarray    # predicted generation per step
    demand_kw: np.ndarray        # predicted demand per step
    steps: int                   # number of forecast steps
    model_version: str = "persistence-v0"
    interval_minutes: int = 15

    def to_dict(self) -> dict:
        return {
            "generation_kw": self.generation_kw.tolist(),
            "demand_kw": self.demand_kw.tolist(),
            "steps": self.steps,
            "model_version": self.model_version,
            "interval_minutes": self.interval_minutes,
        }


class PersistenceForecaster:
    """Persistence model: tomorrow looks like today.

    Falls back to constant defaults if no history is available.
    """

    def __init__(self, default_gen_kw: float = 0.0, default_dem_kw: float = 1.0):
        self.default_gen_kw = default_gen_kw
        self.default_dem_kw = default_dem_kw

    def forecast(
        self,
        history_gen: np.ndarray,
        history_dem: np.ndarray,
        steps: int = 96,  # 24h at 15-min intervals
    ) -> ForecastResult:
        """Generate a persistence-based forecast.

        If history has enough data, replays the last `steps` values.
        Otherwise falls back to constant defaults.
        """
        if len(history_gen) >= steps:
            gen_forecast = history_gen[-steps:]
        elif len(history_gen) > 0:
            # Repeat available data to fill steps
            repeats = (steps // len(history_gen)) + 1
            gen_forecast = np.tile(history_gen, repeats)[:steps]
        else:
            gen_forecast = np.full(steps, self.default_gen_kw)

        if len(history_dem) >= steps:
            dem_forecast = history_dem[-steps:]
        elif len(history_dem) > 0:
            repeats = (steps // len(history_dem)) + 1
            dem_forecast = np.tile(history_dem, repeats)[:steps]
        else:
            dem_forecast = np.full(steps, self.default_dem_kw)

        return ForecastResult(
            generation_kw=gen_forecast,
            demand_kw=dem_forecast,
            steps=steps,
            model_version="persistence-v0",
        )


# ===========================================================================
# Tests
# ===========================================================================

class TestPersistenceFallback:
    """Persistence model returns yesterday's data."""

    def test_replays_last_day(self):
        """With enough history, forecast should replay the last N steps."""
        steps = 96
        gen_history = np.sin(np.linspace(0, 2 * np.pi, 200)) * 5  # 200 points
        dem_history = np.ones(200) * 3.0

        fc = PersistenceForecaster()
        result = fc.forecast(gen_history, dem_history, steps=steps)

        np.testing.assert_array_almost_equal(
            result.generation_kw, gen_history[-steps:],
            err_msg="Generation forecast should replay last 96 points",
        )
        np.testing.assert_array_almost_equal(
            result.demand_kw, dem_history[-steps:],
            err_msg="Demand forecast should replay last 96 points",
        )

    def test_short_history_tiled(self):
        """With less than `steps` history, data should be tiled to fill."""
        gen = np.array([1.0, 2.0, 3.0])
        dem = np.array([4.0, 5.0])

        fc = PersistenceForecaster()
        result = fc.forecast(gen, dem, steps=10)

        assert len(result.generation_kw) == 10
        assert len(result.demand_kw) == 10
        # Tiled pattern: [1, 2, 3, 1, 2, 3, 1, 2, 3, 1]
        assert result.generation_kw[0] == 1.0
        assert result.generation_kw[3] == 1.0


class TestPersistenceFallbackEmpty:
    """Empty history should produce sensible defaults."""

    def test_empty_gen_history_uses_default(self):
        """Empty generation history should fall back to default_gen_kw."""
        fc = PersistenceForecaster(default_gen_kw=0.0, default_dem_kw=2.0)
        result = fc.forecast(np.array([]), np.array([]), steps=48)

        assert len(result.generation_kw) == 48
        assert all(v == 0.0 for v in result.generation_kw)

    def test_empty_dem_history_uses_default(self):
        """Empty demand history should fall back to default_dem_kw."""
        fc = PersistenceForecaster(default_gen_kw=0.0, default_dem_kw=2.0)
        result = fc.forecast(np.array([]), np.array([]), steps=48)

        assert len(result.demand_kw) == 48
        assert all(v == 2.0 for v in result.demand_kw)

    def test_partial_empty_gen(self):
        """Only generation empty; demand should still use history."""
        fc = PersistenceForecaster(default_gen_kw=0.5)
        dem = np.array([3.0, 4.0, 5.0])
        result = fc.forecast(np.array([]), dem, steps=6)

        assert all(v == 0.5 for v in result.generation_kw)
        assert len(result.demand_kw) == 6
        assert result.demand_kw[0] == 3.0


class TestForecastResultShape:
    """Output has correct structure."""

    def test_steps_matches_array_lengths(self):
        """steps field should match the length of generation_kw and demand_kw."""
        fc = PersistenceForecaster()
        result = fc.forecast(np.ones(200), np.ones(200), steps=96)

        assert result.steps == 96
        assert len(result.generation_kw) == result.steps
        assert len(result.demand_kw) == result.steps

    def test_model_version_set(self):
        """model_version should be a non-empty string."""
        fc = PersistenceForecaster()
        result = fc.forecast(np.ones(10), np.ones(10), steps=5)
        assert isinstance(result.model_version, str)
        assert len(result.model_version) > 0

    def test_to_dict_keys(self):
        """to_dict() should contain expected keys."""
        fc = PersistenceForecaster()
        result = fc.forecast(np.ones(10), np.ones(10), steps=5)
        d = result.to_dict()

        expected_keys = {"generation_kw", "demand_kw", "steps", "model_version", "interval_minutes"}
        assert set(d.keys()) == expected_keys

    def test_to_dict_values_serializable(self):
        """to_dict() values should be JSON-serializable types."""
        import json
        fc = PersistenceForecaster()
        result = fc.forecast(np.ones(10), np.ones(10), steps=5)
        d = result.to_dict()

        # Should not raise
        serialized = json.dumps(d)
        assert isinstance(serialized, str)

    def test_generation_and_demand_are_numpy(self):
        """Arrays should be numpy ndarrays."""
        fc = PersistenceForecaster()
        result = fc.forecast(np.ones(10), np.ones(10), steps=5)

        assert isinstance(result.generation_kw, np.ndarray)
        assert isinstance(result.demand_kw, np.ndarray)

    def test_different_step_counts(self):
        """Forecast should work with various step counts."""
        fc = PersistenceForecaster()
        for steps in [1, 10, 48, 96, 288]:
            result = fc.forecast(np.ones(300), np.ones(300), steps=steps)
            assert result.steps == steps
            assert len(result.generation_kw) == steps
            assert len(result.demand_kw) == steps
