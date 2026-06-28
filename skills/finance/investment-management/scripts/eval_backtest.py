#!/usr/bin/env python3
"""
EGRI Evaluator Wrapper — bridges backtest.py to autoany.

Thin wrapper that runs a backtest and outputs a structured EGRI Outcome.
Used as the evaluator in strategy-optimization and screen-evolution
problem specs. Validates constraints and formats results for the
autoany EGRI loop.

Usage:
    python3 eval_backtest.py --strategy-file strategy.yaml --period 10y
    python3 eval_backtest.py --strategy-file strategy.yaml --period 10y \
        --max-drawdown -15 --min-sharpe 0.5

    # With constraint overrides from problem spec:
    python3 eval_backtest.py --strategy-file strategy.yaml --period 10y \
        --constraints "max_drawdown_pct > -15, max_position_weight <= 0.25"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_backtest(strategy_file: str, period: str) -> dict:
    """Run backtest.py and parse the EGRI output."""
    script = Path(__file__).parent / "backtest.py"
    cmd = [
        sys.executable, str(script),
        "--strategy-file", strategy_file,
        "--period", period,
        "--egri",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        return {
            "score": 0,
            "constraints_passed": False,
            "violations": [f"backtest failed: {result.stderr.strip()[:200]}"],
            "metrics": {},
        }

    return json.loads(result.stdout)


def check_constraints(outcome: dict, constraints: list[str]) -> dict:
    """Apply additional constraints to the EGRI outcome."""
    metrics = outcome.get("metrics", {})
    violations = list(outcome.get("violations", []))
    passed = outcome.get("constraints_passed", True)

    for constraint in constraints:
        constraint = constraint.strip()
        if not constraint:
            continue

        # Parse constraint: "metric_name op value"
        for op in ["<=", ">=", "<", ">", "=="]:
            if op in constraint:
                parts = constraint.split(op)
                if len(parts) == 2:
                    metric_name = parts[0].strip()
                    try:
                        threshold = float(parts[1].strip())
                    except ValueError:
                        continue

                    actual = metrics.get(metric_name)
                    if actual is None:
                        continue

                    violated = False
                    if op == "<=" and actual > threshold:
                        violated = True
                    elif op == ">=" and actual < threshold:
                        violated = True
                    elif op == "<" and actual >= threshold:
                        violated = True
                    elif op == ">" and actual <= threshold:
                        violated = True
                    elif op == "==" and abs(actual - threshold) > 0.001:
                        violated = True

                    if violated:
                        violations.append(f"{metric_name}={actual} violates {constraint}")
                        passed = False
                break

    outcome["constraints_passed"] = passed
    outcome["violations"] = violations
    return outcome


def main():
    parser = argparse.ArgumentParser(
        description="EGRI evaluator wrapper for strategy backtesting",
    )
    parser.add_argument("--strategy-file", required=True, help="Path to strategy YAML artifact")
    parser.add_argument("--period", default="10y", help="Backtest period")
    parser.add_argument("--constraints", default="", help="Comma-separated constraint expressions")
    parser.add_argument("--max-drawdown", type=float, help="Max drawdown constraint (e.g. -15)")
    parser.add_argument("--min-sharpe", type=float, help="Min Sharpe ratio constraint")
    args = parser.parse_args()

    # Run backtest
    outcome = run_backtest(args.strategy_file, args.period)

    # Build constraint list
    constraints = [c.strip() for c in args.constraints.split(",") if c.strip()]
    if args.max_drawdown is not None:
        constraints.append(f"max_drawdown_pct > {args.max_drawdown}")
    if args.min_sharpe is not None:
        constraints.append(f"sharpe_ratio >= {args.min_sharpe}")

    # Apply constraints
    if constraints:
        outcome = check_constraints(outcome, constraints)

    print(json.dumps(outcome, indent=2))


if __name__ == "__main__":
    main()
