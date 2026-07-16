#!/usr/bin/env python3
"""Deterministic wait-time calculator for the Alkosto promo workflow."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from statistics import mean, stdev
from typing import Any

HMS_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
EPSILON = 1e-9


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round2(value: float) -> float:
    return round(value, 2)


def parse_hms_to_seconds(value: str) -> int | None:
    match = HMS_RE.match(value)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or "0")
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    return hour * 3600 + minute * 60 + second


def parse_iso_to_minutes(value: str) -> float:
    fixed = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(fixed)
    return parsed.timestamp() / 60.0


def parse_timestamps_to_minutes(timestamps: list[str]) -> list[float]:
    if len(timestamps) < 2:
        raise ValueError("winner_timestamps necesita minimo 2 timestamps.")

    hms_values = [parse_hms_to_seconds(item) for item in timestamps]
    if all(item is not None for item in hms_values):
        timeline_seconds: list[int] = []
        current = hms_values[0] or 0
        timeline_seconds.append(current)
        for item in hms_values[1:]:
            candidate = item or 0
            while candidate <= current:
                candidate += 24 * 3600
            timeline_seconds.append(candidate)
            current = candidate
        return [sec / 60.0 for sec in timeline_seconds]

    timeline = [parse_iso_to_minutes(item) for item in timestamps]
    for idx in range(1, len(timeline)):
        if timeline[idx] <= timeline[idx - 1]:
            raise ValueError("timestamps ISO deben estar ordenados ascendentemente.")
    return timeline


def intervals_from_timeline_minutes(timeline: list[float]) -> list[float]:
    return [timeline[idx] - timeline[idx - 1] for idx in range(1, len(timeline))]


def threshold_from_day(is_weekend_or_holiday: bool) -> int:
    return 50 if is_weekend_or_holiday else 25


def probability_uniform(interval_minutes: float, wait_minutes: float) -> float:
    if interval_minutes <= 0:
        return 1.0
    return clamp(wait_minutes / interval_minutes, 0.0, 1.0)


def probability_exponential(mean_interval: float, wait_minutes: float) -> float:
    if mean_interval <= 0:
        return 1.0
    return 1.0 - math.exp(-wait_minutes / mean_interval)


def maybe_economics(
    payload: dict[str, Any],
    probability_within_wait: float,
    mean_interval: float,
    max_wait: float,
    optimal_wait: float,
) -> dict[str, Any] | None:
    expected_bonus = payload.get("expected_bonus_value")
    value_per_min = payload.get("time_value_per_minute")
    if not isinstance(expected_bonus, (int, float)):
        return None
    if not isinstance(value_per_min, (int, float)):
        return None
    if expected_bonus < 0 or value_per_min < 0:
        return None

    expected_value = probability_within_wait * expected_bonus
    time_cost = optimal_wait * value_per_min
    net = expected_value - time_cost
    value_expected_per_min = expected_bonus / max(mean_interval, EPSILON)
    break_even = max_wait if value_per_min == 0 else clamp(expected_bonus / value_per_min, 0.0, max_wait)

    return {
        "expected_value_for_optimal_wait": round2(expected_value),
        "expected_time_cost_for_optimal_wait": round2(time_cost),
        "net_expected_value_for_optimal_wait": round2(net),
        "value_expected_per_minute": round2(value_expected_per_min),
        "break_even_wait_minutes": round2(break_even),
    }


def run_purchase_rate(payload: dict[str, Any]) -> dict[str, Any]:
    required = [
        "is_weekend_or_holiday",
        "model",
        "observed_purchases",
        "observed_minutes",
        "observed_lanes",
    ]
    for key in required:
        if key not in payload:
            raise ValueError(f"Falta campo requerido: {key}")

    is_weekend = bool(payload["is_weekend_or_holiday"])
    model = payload["model"]
    observed_purchases = float(payload["observed_purchases"])
    observed_minutes = float(payload["observed_minutes"])
    observed_lanes = float(payload["observed_lanes"])
    total_open_lanes = payload.get("total_open_lanes")
    max_wait = max(float(payload.get("max_wait_minutes", 30.0)), 1.0)
    confidence_buffer = clamp(float(payload.get("confidence_buffer", 0.2)), 0.0, 0.9)
    target_probability = clamp(float(payload.get("target_hit_probability", 0.75)), 0.5, 0.99)

    if observed_purchases <= 0 or observed_minutes <= 0 or observed_lanes <= 0:
        raise ValueError("observed_purchases/observed_minutes/observed_lanes deben ser > 0.")
    if model not in {"global", "per_lane"}:
        raise ValueError("model debe ser 'global' o 'per_lane'.")

    k = threshold_from_day(is_weekend)
    lambda_obs = observed_purchases / observed_minutes
    lane_scale = 1.0
    if model == "global" and isinstance(total_open_lanes, (int, float)) and total_open_lanes >= observed_lanes:
        lane_scale = float(total_open_lanes) / observed_lanes

    lambda_est = lambda_obs * lane_scale if model == "global" else lambda_obs / observed_lanes
    lambda_cons = lambda_est * (1.0 - confidence_buffer)
    interval = k / max(lambda_cons, EPSILON)
    expected_wait = interval / 2.0
    optimal_wait = clamp(interval * target_probability, 1.0, max_wait)
    probability_within = probability_uniform(interval, optimal_wait)

    result = {
        "mode": "purchase_rate",
        "k_threshold_clients": k,
        "probability_win_per_attempt": round(1.0 / k, 4),
        "rates": {
            "purchases_per_minute_observed": round2(lambda_obs),
            "purchases_per_minute_estimated": round2(lambda_est),
            "purchases_per_minute_conservative": round2(lambda_cons),
            "lane_scale_factor": round2(lane_scale),
        },
        "wait_estimates_minutes": {
            "mean_interval_between_winners": round2(interval),
            "expected_wait_to_next_winner": round2(expected_wait),
            "p50_wait_to_next_winner": round2(interval * 0.5),
            "p75_wait_to_next_winner": round2(interval * 0.75),
            "p90_wait_to_next_winner": round2(interval * 0.9),
        },
        "recommendation": {
            "optimal_wait_minutes": round2(optimal_wait),
            "probability_next_winner_within_optimal_wait": round(probability_within, 4),
            "decision_rule": "Si no sale ganador en este tiempo, remide 2 minutos y recalcula.",
        },
    }

    economics = maybe_economics(payload, probability_within, interval, max_wait, optimal_wait)
    if economics is not None:
        result["economics"] = economics

    return result


def run_winner_timestamps(payload: dict[str, Any]) -> dict[str, Any]:
    timestamps = payload.get("winner_timestamps")
    if not isinstance(timestamps, list) or len(timestamps) < 2:
        raise ValueError("winner_timestamps debe ser una lista con minimo 2 elementos.")
    if not all(isinstance(item, str) for item in timestamps):
        raise ValueError("winner_timestamps solo acepta strings.")

    max_wait = max(float(payload.get("max_wait_minutes", 30.0)), 1.0)
    target_probability = clamp(float(payload.get("target_hit_probability", 0.75)), 0.5, 0.99)
    elapsed = max(float(payload.get("elapsed_since_last_winner_minutes", 0.0)), 0.0)

    timeline = parse_timestamps_to_minutes(timestamps)
    intervals = intervals_from_timeline_minutes(timeline)
    mu = mean(intervals)
    sigma = stdev(intervals) if len(intervals) > 1 else 0.0
    cv = sigma / max(mu, EPSILON)

    if cv < 0.4:
        cadence_model = "regular"
    elif cv > 0.7:
        cadence_model = "random"
    else:
        cadence_model = "mixed"

    regular_remaining = max(mu - elapsed, 0.0)
    random_wait_target = -mu * math.log(1.0 - target_probability)

    if cadence_model == "regular":
        optimal_wait = regular_remaining
    elif cadence_model == "random":
        optimal_wait = random_wait_target
    else:
        optimal_wait = (regular_remaining + random_wait_target) / 2.0
    optimal_wait = clamp(optimal_wait, 0.0, max_wait)

    regular_prob = 1.0 if regular_remaining <= EPSILON else clamp(optimal_wait / regular_remaining, 0.0, 1.0)
    random_prob = probability_exponential(mu, optimal_wait)
    if cadence_model == "regular":
        probability_within = regular_prob
    elif cadence_model == "random":
        probability_within = random_prob
    else:
        probability_within = (regular_prob + random_prob) / 2.0

    if cadence_model == "regular":
        wait_estimates = {
            "mean_interval_between_winners": round2(mu),
            "expected_wait_to_next_winner": round2(regular_remaining),
            "p50_wait_to_next_winner": round2(regular_remaining),
            "p75_wait_to_next_winner": round2(regular_remaining),
            "p90_wait_to_next_winner": round2(regular_remaining),
        }
    elif cadence_model == "random":
        wait_estimates = {
            "mean_interval_between_winners": round2(mu),
            "expected_wait_to_next_winner": round2(mu),
            "p50_wait_to_next_winner": round2(-mu * math.log(1.0 - 0.5)),
            "p75_wait_to_next_winner": round2(-mu * math.log(1.0 - 0.75)),
            "p90_wait_to_next_winner": round2(-mu * math.log(1.0 - 0.9)),
        }
    else:
        wait_estimates = {
            "mean_interval_between_winners": round2(mu),
            "expected_wait_to_next_winner": round2((regular_remaining + mu) / 2.0),
            "p50_wait_to_next_winner": round2((regular_remaining + (-mu * math.log(1.0 - 0.5))) / 2.0),
            "p75_wait_to_next_winner": round2((regular_remaining + (-mu * math.log(1.0 - 0.75))) / 2.0),
            "p90_wait_to_next_winner": round2((regular_remaining + (-mu * math.log(1.0 - 0.9))) / 2.0),
        }

    result: dict[str, Any] = {
        "mode": "winner_timestamps",
        "cadence_analysis": {
            "intervals_minutes": [round2(interval) for interval in intervals],
            "interval_mean_minutes": round2(mu),
            "interval_std_minutes": round2(sigma),
            "interval_cv": round2(cv),
            "cadence_model": cadence_model,
        },
        "wait_estimates_minutes": wait_estimates,
        "recommendation": {
            "optimal_wait_minutes": round2(optimal_wait),
            "probability_next_winner_within_optimal_wait": round(probability_within, 4),
            "decision_rule": "Si no escuchas ganador antes del corte, agrega 2-3 timestamps y recalcula.",
        },
    }

    if "is_weekend_or_holiday" in payload:
        k = threshold_from_day(bool(payload["is_weekend_or_holiday"]))
        result["k_threshold_clients"] = k
        result["probability_win_per_attempt"] = round(1.0 / k, 4)

    economics = maybe_economics(payload, probability_within, mu, max_wait, optimal_wait)
    if economics is not None:
        result["economics"] = economics

    return result


def run(payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("mode")
    if mode == "purchase_rate":
        return run_purchase_rate(payload)
    if mode == "winner_timestamps":
        return run_winner_timestamps(payload)
    raise ValueError("mode debe ser 'purchase_rate' o 'winner_timestamps'.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate Alkosto waiting-time estimates.")
    parser.add_argument("--input-json", required=True, help="JSON string with mode and inputs.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.input_json)
    result = run(payload)
    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
