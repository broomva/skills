"""ML forecasting module for generation and demand prediction.

Loads TFLite models, produces 24h forecasts with uncertainty bands.
Falls back to persistence forecast if model inference fails.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    timestamps: list[float]  # epoch seconds for each forecast step
    generation_kw: np.ndarray  # shape (steps,)
    demand_kw: np.ndarray  # shape (steps,)
    generation_upper: np.ndarray  # 90th percentile
    generation_lower: np.ndarray  # 10th percentile
    demand_upper: np.ndarray
    demand_lower: np.ndarray
    model_version: str = "persistence"
    created_at: float = field(default_factory=time.time)

    @property
    def steps(self) -> int:
        return len(self.generation_kw)

    def net_power(self) -> np.ndarray:
        return self.generation_kw - self.demand_kw

    def to_dict(self) -> dict:
        return {
            "timestamps": self.timestamps,
            "generation_kw": self.generation_kw.tolist(),
            "demand_kw": self.demand_kw.tolist(),
            "generation_upper": self.generation_upper.tolist(),
            "generation_lower": self.generation_lower.tolist(),
            "demand_upper": self.demand_upper.tolist(),
            "demand_lower": self.demand_lower.tolist(),
            "model_version": self.model_version,
            "created_at": self.created_at,
        }


class Forecaster:
    """Runs TFLite inference for 24h generation + demand forecasting."""

    FORECAST_STEPS = 96  # 15-min intervals over 24h
    STEP_SECONDS = 900  # 15 minutes
    LOOKBACK_HOURS = 48
    LOOKBACK_STEPS = LOOKBACK_HOURS * 4

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self._interpreter = None
        self._model_path: Path | None = None
        self._model_mtime: float = 0.0

    def _find_model(self) -> Path | None:
        models = sorted(self.model_dir.glob("*.tflite"), key=lambda p: p.stat().st_mtime, reverse=True)
        return models[0] if models else None

    def _load_model(self):
        model_path = self._find_model()
        if model_path is None:
            log.info("No TFLite model found in %s, using persistence fallback", self.model_dir)
            self._interpreter = None
            return

        mtime = model_path.stat().st_mtime
        if self._model_path == model_path and self._model_mtime == mtime:
            return  # already loaded

        try:
            import tflite_runtime.interpreter as tflite
        except ImportError:
            try:
                import tensorflow.lite as tflite
            except ImportError:
                log.warning("Neither tflite_runtime nor tensorflow found; using persistence fallback")
                self._interpreter = None
                return

        try:
            self._interpreter = tflite.Interpreter(model_path=str(model_path))
            self._interpreter.allocate_tensors()
            self._model_path = model_path
            self._model_mtime = mtime
            log.info("Loaded TFLite model: %s", model_path.name)
        except Exception as e:
            log.error("Failed to load TFLite model %s: %s", model_path, e)
            self._interpreter = None

    def _prepare_features(
        self,
        history_gen: np.ndarray,
        history_demand: np.ndarray,
        weather: np.ndarray | None = None,
    ) -> np.ndarray:
        """Build input tensor from historical readings and weather features.

        Expected input shape: (1, lookback_steps, n_features)
        Features: [generation, demand, hour_sin, hour_cos, weather...]
        """
        n = min(len(history_gen), self.LOOKBACK_STEPS)
        gen = np.zeros(self.LOOKBACK_STEPS)
        dem = np.zeros(self.LOOKBACK_STEPS)
        gen[-n:] = history_gen[-n:]
        dem[-n:] = history_demand[-n:]

        # Time-of-day encoding
        now = time.time()
        hours = np.array([
            ((now - (self.LOOKBACK_STEPS - i) * self.STEP_SECONDS) % 86400) / 3600
            for i in range(self.LOOKBACK_STEPS)
        ])
        hour_sin = np.sin(2 * np.pi * hours / 24)
        hour_cos = np.cos(2 * np.pi * hours / 24)

        features = np.stack([gen, dem, hour_sin, hour_cos], axis=-1)  # (steps, 4)

        if weather is not None and len(weather) == self.LOOKBACK_STEPS:
            weather_2d = weather.reshape(self.LOOKBACK_STEPS, -1)
            features = np.concatenate([features, weather_2d], axis=-1)

        return features[np.newaxis, ...].astype(np.float32)

    async def forecast(
        self,
        history_gen: np.ndarray,
        history_demand: np.ndarray,
        weather: np.ndarray | None = None,
    ) -> ForecastResult:
        """Run forecast. Tries ML model first, falls back to persistence."""
        # Check for model updates (hot-swap)
        self._load_model()

        now = time.time()
        timestamps = [now + i * self.STEP_SECONDS for i in range(self.FORECAST_STEPS)]

        if self._interpreter is not None:
            try:
                return await self._ml_forecast(history_gen, history_demand, weather, timestamps)
            except Exception as e:
                log.error("ML forecast failed, falling back to persistence: %s", e)

        return self._persistence_forecast(history_gen, history_demand, timestamps)

    async def _ml_forecast(
        self,
        history_gen: np.ndarray,
        history_demand: np.ndarray,
        weather: np.ndarray | None,
        timestamps: list[float],
    ) -> ForecastResult:
        features = self._prepare_features(history_gen, history_demand, weather)

        # Run inference in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        gen_pred, dem_pred, gen_std, dem_std = await loop.run_in_executor(
            None, self._run_inference, features
        )

        return ForecastResult(
            timestamps=timestamps,
            generation_kw=gen_pred,
            demand_kw=dem_pred,
            generation_upper=gen_pred + 1.645 * gen_std,
            generation_lower=np.maximum(0, gen_pred - 1.645 * gen_std),
            demand_upper=dem_pred + 1.645 * dem_std,
            demand_lower=np.maximum(0, dem_pred - 1.645 * dem_std),
            model_version=self._model_path.name if self._model_path else "unknown",
        )

    def _run_inference(self, features: np.ndarray):
        """Execute TFLite model. Expects output shape (1, steps, 4): gen, dem, gen_std, dem_std."""
        input_details = self._interpreter.get_input_details()
        output_details = self._interpreter.get_output_details()

        self._interpreter.set_tensor(input_details[0]["index"], features)
        self._interpreter.invoke()
        output = self._interpreter.get_tensor(output_details[0]["index"])[0]

        gen_pred = output[:, 0]
        dem_pred = output[:, 1]
        gen_std = np.abs(output[:, 2]) if output.shape[1] > 2 else np.ones(len(gen_pred)) * 0.1
        dem_std = np.abs(output[:, 3]) if output.shape[1] > 3 else np.ones(len(dem_pred)) * 0.1

        return gen_pred, dem_pred, gen_std, dem_std

    def _persistence_forecast(
        self,
        history_gen: np.ndarray,
        history_demand: np.ndarray,
        timestamps: list[float],
    ) -> ForecastResult:
        """Yesterday = today forecast. Uses last 24h as the prediction."""
        steps = self.FORECAST_STEPS

        if len(history_gen) >= steps:
            gen = history_gen[-steps:].copy()
            dem = history_demand[-steps:].copy()
        else:
            # Repeat whatever history we have
            gen = np.tile(history_gen, (steps // max(len(history_gen), 1)) + 1)[:steps]
            dem = np.tile(history_demand, (steps // max(len(history_demand), 1)) + 1)[:steps]

        # Uncertainty grows with forecast horizon
        horizon_factor = np.linspace(0.05, 0.3, steps)
        gen_std = np.abs(gen) * horizon_factor + 0.01
        dem_std = np.abs(dem) * horizon_factor + 0.01

        return ForecastResult(
            timestamps=timestamps,
            generation_kw=gen,
            demand_kw=dem,
            generation_upper=gen + 1.645 * gen_std,
            generation_lower=np.maximum(0, gen - 1.645 * gen_std),
            demand_upper=dem + 1.645 * dem_std,
            demand_lower=np.maximum(0, dem - 1.645 * dem_std),
            model_version="persistence",
        )
