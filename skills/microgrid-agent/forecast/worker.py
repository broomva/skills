"""ML Worker — subprocess called by the Rust kernel for forecasting.

Protocol: reads JSON request from stdin, writes JSON response to stdout.
The kernel spawns this process when it needs a forecast (every 15-60 min).
If this process crashes, the kernel continues with a persistence fallback.

Usage (by kernel):
    echo '{"type":"forecast","history":[...]}' | python ml/worker.py

Usage (standalone test):
    python ml/worker.py --test
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from forecast import TFLiteForecaster


def handle_request(request: dict, forecaster: TFLiteForecaster) -> dict:
    req_type = request.get("type", "forecast")

    if req_type == "forecast":
        history = request.get("history", [])
        result = forecaster.predict(history)
        return {
            "status": "ok",
            "generation_kw": result.generation_kw,
            "demand_kw": result.demand_kw,
            "horizon_hours": result.horizon_hours,
        }
    elif req_type == "health":
        return {"status": "ok", "model_loaded": forecaster.model is not None}
    else:
        return {"status": "error", "message": f"Unknown request type: {req_type}"}


def main():
    model_dir = Path("data/models")
    forecaster = TFLiteForecaster(model_dir)

    if "--test" in sys.argv:
        # Self-test mode
        result = handle_request({"type": "health"}, forecaster)
        print(json.dumps(result))
        return

    # Subprocess mode: read JSON from stdin, write JSON to stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request, forecaster)
        except Exception as e:
            response = {"status": "error", "message": str(e)}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
