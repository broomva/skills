#!/usr/bin/env python3
"""Check capability tiers before dispatch. No operation is executed by this tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def required(row: dict, key: str) -> None:
    if not isinstance(row.get(key), str) or not row[key].strip():
        raise ValueError(f"{key}: nonempty evidence/reference required")


def validate(plan: object) -> list[str]:
    if not isinstance(plan, list) or not plan:
        raise ValueError("plan must be a nonempty array")
    executable = []
    seen = set()
    for row in plan:
        if not isinstance(row, dict):
            raise ValueError("operation must be an object")
        for key in ("id", "operation", "owner", "settling_observation"):
            required(row, key)
        if row["id"] in seen:
            raise ValueError("duplicate operation id")
        seen.add(row["id"])
        tier = row.get("tier")
        if tier == "executable_now":
            for key in (
                "catalog_ref",
                "input_schema_ref",
                "output_schema_ref",
                "readiness_evidence",
            ):
                required(row, key)
            if row.get("authorized") is not True:
                raise ValueError("executable_now requires current authorization")
            executable.append(row["id"])
        elif tier == "request_quote":
            for key in ("substrate_ref", "missing_prerequisite", "promotion_check"):
                required(row, key)
        elif tier == "send_out":
            for key in ("external_executor", "handoff_artifact", "return_evidence"):
                required(row, key)
        else:
            raise ValueError("tier must be executable_now, request_quote or send_out")
    return executable


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan", type=Path)
    args = ap.parse_args()
    try:
        executable = validate(json.loads(args.plan.read_text()))
    except (ValueError, OSError, TypeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 2
    print(
        json.dumps(
            {
                "valid": True,
                "executable_now": executable,
                "scope": "structure only; verify live evidence before dispatch",
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
