#!/usr/bin/env python3
"""Developer-only parity oracle for the standalone Codex lineage scanner.

This script deliberately requires a separately installed CodexBar binary. The
skill's production scanner never imports or executes CodexBar.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SCANNER = Path(__file__).with_name("audit_harness_usage.py")


def run_json(command: list[str], *, env: dict[str, str] | None = None) -> Any:
    result = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
    return json.loads(result.stdout)


def codexbar_totals(payload: Any) -> tuple[int, float]:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError("CodexBar did not return its expected JSON array")
    daily = payload[0].get("daily")
    if not isinstance(daily, list):
        raise ValueError("CodexBar JSON did not contain daily usage")
    tokens = sum(int(row.get("totalTokens", 0)) for row in daily if isinstance(row, dict))
    cost = sum(float(row.get("totalCost", 0)) for row in daily if isinstance(row, dict))
    return tokens, cost


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--codexbar-bin", default="codexbar")
    args = parser.parse_args()

    home = args.codex_home.expanduser().resolve()
    native = run_json([
        sys.executable,
        str(SCANNER),
        "--provider", "codex",
        "--days", str(args.days),
        "--path", f"codex={home}",
        "--format", "json",
    ])
    oracle_env = os.environ.copy()
    oracle_env["CODEX_HOME"] = str(home)
    oracle = run_json([
        args.codexbar_bin,
        "cost",
        "--provider", "codex",
        "--format", "json",
        "--refresh",
        "--days", str(args.days),
    ], env=oracle_env)

    oracle_tokens, oracle_cost = codexbar_totals(oracle)
    native_tokens = int(native["overall"]["total_tokens"])
    native_cost_value = native["overall"]["estimated_cost_usd"]
    if native_cost_value is None:
        raise ValueError("Standalone report has incomplete pricing coverage")
    native_cost = float(native_cost_value)
    receipt = {
        "schema_version": 1,
        "days": args.days,
        "tokens": {
            "standalone": native_tokens,
            "codexbar": oracle_tokens,
            "delta": native_tokens - oracle_tokens,
        },
        "estimated_cost_usd": {
            "standalone": native_cost,
            "codexbar": oracle_cost,
            "delta": native_cost - oracle_cost,
        },
    }
    receipt["match"] = receipt["tokens"]["delta"] == 0 and math.isclose(
        native_cost, oracle_cost, rel_tol=0, abs_tol=1e-9
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
