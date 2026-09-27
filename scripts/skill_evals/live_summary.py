#!/usr/bin/env python3
"""live_summary — read a directory of live eval reports and say what they measured.

BRO-2030. A per-skill pass rate on its own is close to useless here, because the
same number arises from two opposite causes: a description that does not route, and
a description that routes fine into a run that cannot complete its deliverable. This
separates them, because the remedy for each is the opposite of the other.

    python3 scripts/skill_evals/live_summary.py /tmp/live-evals

For every skill it reports the TRIGGER rate (did the description route?) alongside
the outcome pass rate (did the run then do the thing?), plus which checks did the
failing, so a reader can tell "fix the description" from "fix the check or the
workspace" without opening a transcript.

Pure stdlib. Read-only.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    cases = report.get("cases") or []
    agg = report.get("aggregate") or {}
    positives = [c for c in cases if c.get("should_trigger")]
    pos_trials = [t for c in positives for t in (c.get("results") or [])]
    triggered = sum(1 for t in pos_trials if t.get("triggered"))

    failed_checks: collections.Counter = collections.Counter()
    outcomes: collections.Counter = collections.Counter()
    for c in cases:
        for t in c.get("results") or []:
            outcomes[t.get("outcome", "?")] += 1
            detail = t.get("detail", "")
            if "checks failed" in detail:
                for name in detail.split(":")[-1].split(","):
                    failed_checks[name.strip()] += 1

    n = len(pos_trials)
    return {
        "skill": report.get("skill", "?"),
        "positive_trials": n,
        "triggered": triggered,
        "trigger_rate": round(triggered / n, 4) if n else None,
        "positive_passes": (agg.get("positive") or {}).get("passes", 0),
        "positive_pass_rate": (agg.get("positive") or {}).get("pass_rate"),
        "negative_passes": (agg.get("negative") or {}).get("passes", 0),
        "negative_trials": (agg.get("negative") or {}).get("trials", 0),
        "errors": agg.get("errors", 0),
        "cost_usd": agg.get("total_cost_usd"),
        "outcomes": dict(outcomes),
        "failed_checks": dict(failed_checks.most_common()),
        # THE diagnostic. Which of the two questions failed decides the remedy, and
        # they point in opposite directions: a low trigger rate is a DESCRIPTION
        # problem, while a high trigger rate with failing checks is a problem with
        # the run, the check, or the workspace it runs in.
        "diagnosis": _diagnose(triggered, n, failed_checks),
    }


def _diagnose(triggered: int, n: int, failed_checks: collections.Counter) -> str:
    if not n:
        return "no positive trials — nothing measured"
    rate = triggered / n
    if rate < 0.5:
        return (
            f"DESCRIPTION does not route ({triggered}/{n} fired). The outcome checks "
            "are barely reached, so they say little either way."
        )
    if not failed_checks:
        return f"healthy — description routes ({triggered}/{n}) and the outcomes hold"
    top, count = failed_checks.most_common(1)[0]
    share = count / max(1, sum(failed_checks.values()))
    if share >= 0.6:
        return (
            f"DESCRIPTION routes ({triggered}/{n}); the failures are concentrated in "
            f"'{top}' ({count} of {sum(failed_checks.values())}). Suspect that check "
            "or the workspace it runs in before the skill."
        )
    return f"description routes ({triggered}/{n}); failures spread across {len(failed_checks)} checks"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("reports", type=Path, help="directory of *.json run reports")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    found = sorted(Path(args.reports).glob("*.json"))
    if not found:
        print(f"no reports under {args.reports}", file=sys.stderr)
        return 2

    rows = []
    for path in found:
        try:
            rows.append(summarize(json.loads(path.read_text(encoding="utf-8"))))
        except (ValueError, OSError) as exc:
            print(f"[live-summary] skipping {path.name}: {exc}", file=sys.stderr)

    if args.as_json:
        print(json.dumps(rows, indent=2))
        return 0

    print(f"\n{'skill':12}{'trigger':>10}{'positives':>11}{'negatives':>11}{'err':>5}{'cost':>8}")
    print("-" * 76)
    total = 0.0
    for r in rows:
        total += r["cost_usd"] or 0.0
        trig = f"{r['triggered']}/{r['positive_trials']}"
        pos = f"{r['positive_passes']}/{r['positive_trials']}"
        neg = f"{r['negative_passes']}/{r['negative_trials']}"
        print(f"{r['skill'][:11]:12}{trig:>10}{pos:>11}{neg:>11}"
              f"{r['errors']:>5}{(r['cost_usd'] or 0):>8.2f}")
    print("-" * 76)
    print(f"{'TOTAL':12}{'':>10}{'':>11}{'':>11}{'':>5}{total:>8.2f}\n")

    for r in rows:
        print(f"  {r['skill']}: {r['diagnosis']}")
        if r["failed_checks"]:
            print(f"      failing checks: {r['failed_checks']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
