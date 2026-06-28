"""KronosForecaster — a Kronos foundation-model adapter for ForecastStrategy.

Optional (`[kronos]` extra: torch + huggingface_hub + …). The core strategy plane
never imports this; everything here is lazy-imported, so a CI/runtime without torch is
unaffected.

Packaging note: Kronos is **not pip-installable** (research code). Clone
github.com/shiyu-coder/Kronos and either install its `model/` on the path or pass
``kronos_repo_path`` so this adapter can `from model import …`.

Gut-check lesson (tool/kronos, 2026-06-04): always use probabilistic averaging
(``sample_count`` ≥ 5) and a short horizon — a single sample is noise. The forecaster
**seeds torch per call** so identical bars → identical forecast (the Strategy contract
wants determinism; an unseeded sampler would break backtest reproducibility). Kronos
sampling is pure-torch (``torch.multinomial``), so seeding torch is sufficient — there
is no numpy/python RNG to seed.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

from .types import Bar


class KronosForecaster:
    """Wraps a pretrained Kronos model as a ForecastStrategy ``Forecaster``."""

    def __init__(
        self,
        *,
        model_name: str = "Kronos-small",
        tokenizer_name: str = "Kronos-Tokenizer-base",
        sample_count: int = 5,
        temperature: float = 1.0,
        top_p: float = 0.9,
        max_context: int = 512,
        lookback: int = 400,
        device: str = "cpu",
        kronos_repo_path: str | None = None,
        hf_org: str = "NeoQuasar",
        seed: int = 0,
    ) -> None:
        if kronos_repo_path is not None and kronos_repo_path not in sys.path:
            sys.path.append(kronos_repo_path)
        try:
            import torch  # noqa: F401
            from model import Kronos, KronosPredictor, KronosTokenizer
        except ImportError as exc:  # pragma: no cover - exercised when the extra is absent
            raise RuntimeError(
                "KronosForecaster requires the optional 'kronos' extra (torch + "
                "huggingface_hub) AND the Kronos `model/` package on the path. Install "
                "`tradingview-bridge[kronos]` and clone github.com/shiyu-coder/Kronos, "
                "passing kronos_repo_path=<clone>."
            ) from exc

        self._name = f"kronos-{model_name.split('-')[-1].lower()}"
        self._sample_count = sample_count
        self._temperature = temperature
        self._top_p = top_p
        self._lookback = min(lookback, max_context)
        self._seed = seed
        tok = KronosTokenizer.from_pretrained(f"{hf_org}/{tokenizer_name}")
        mdl = Kronos.from_pretrained(f"{hf_org}/{model_name}")
        self._predictor = KronosPredictor(mdl, tok, max_context=max_context, device=device)

    @property
    def name(self) -> str:
        return self._name

    def predict_return(self, bars: Sequence[Bar], horizon: int) -> float:
        """Predicted fractional return of close over ``horizon`` bars (seeded → deterministic)."""
        import pandas as pd
        import torch

        torch.manual_seed(self._seed)  # same bars → same forecast (Strategy determinism)
        recent: list[Bar] = list(bars[-self._lookback :])
        if len(recent) < 2:
            return 0.0
        df = pd.DataFrame(
            {
                "open": [float(b.open) for b in recent],
                "high": [float(b.high) for b in recent],
                "low": [float(b.low) for b in recent],
                "close": [float(b.close) for b in recent],
                "volume": [float(b.volume) for b in recent],
            }
        )
        x_ts = pd.Series([b.ts for b in recent])
        deltas = [recent[i].ts - recent[i - 1].ts for i in range(1, len(recent))]
        step = sorted(deltas)[len(deltas) // 2]
        last_ts = recent[-1].ts
        y_ts = pd.Series([last_ts + step * (i + 1) for i in range(horizon)])

        pred: Any = self._predictor.predict(
            df=df,
            x_timestamp=x_ts,
            y_timestamp=y_ts,
            pred_len=horizon,
            T=self._temperature,
            top_p=self._top_p,
            sample_count=self._sample_count,
            verbose=False,
        )
        last_close = float(recent[-1].close)
        pred_close = float(pred["close"].to_numpy()[-1])
        if last_close <= 0:
            return 0.0
        return (pred_close - last_close) / last_close
