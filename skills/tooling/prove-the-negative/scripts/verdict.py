#!/usr/bin/env python3
"""Compute a run verdict that cannot mistake a dead apparatus for a passing one.

The whole skill reduces to one pure function. Its job is to refuse the single
inference that keeps being wrong:

    every probe returned "denied"  ->  the boundary holds

That inference is invalid, because "everything is denied" and "nothing ran at
all" are the SAME OBSERVATION. Only a control that must SUCCEED separates them.
So a run whose controls did not pass is INVALID -- not PASS, and not FAIL
either, because a failed control means the run measured nothing and its other
results carry no information in either direction.

Usage:
    verdict.py cases.json          # or: cat cases.json | verdict.py -

Exit codes are the contract: 0 PASS, 1 FAIL, 2 INVALID. INVALID is deliberately
distinct from FAIL -- a caller that collapses them re-creates the bug, treating
"we learned nothing" as "we found a problem" and eventually as noise to ignore.
"""

from __future__ import annotations

import json
import sys
from typing import Iterable, Literal, NamedTuple

Outcome = Literal["pass", "fail", "error"]
Kind = Literal["control", "assertion"]
Verdict = Literal["PASS", "FAIL", "INVALID"]


class Case(NamedTuple):
    name: str
    kind: Kind
    outcome: Outcome


class Result(NamedTuple):
    verdict: Verdict
    reason: str
    #: Cases responsible for the verdict, for the report.
    culprits: tuple[str, ...]


EXIT = {"PASS": 0, "FAIL": 1, "INVALID": 2}


def run_verdict(cases: Iterable[Case]) -> Result:
    """PASS / FAIL / INVALID for a probe matrix.

    Order matters and is the point:

    1. No control at all -> INVALID. A suite made entirely of denials is
       unfalsifiable; it reports success when its subject is switched off. This
       is checked FIRST because a suite with zero controls and zero failures
       looks maximally healthy and is worth exactly nothing.
    2. Any control not passing -> INVALID. Includes `error`: an apparatus that
       crashed did not demonstrate liveness either.
    3. Any assertion failing OR erroring -> FAIL. An errored assertion is never
       a pass, even when the assertion is a denial: a probe that could not run
       proves nothing about what its subject cannot reach.
    4. Otherwise PASS.
    """
    cases = list(cases)
    controls = [c for c in cases if c.kind == "control"]

    if not controls:
        return Result(
            "INVALID",
            "no positive control: a suite of denials cannot distinguish a held "
            "boundary from an apparatus that never ran",
            (),
        )

    dead = tuple(c.name for c in controls if c.outcome != "pass")
    if dead:
        return Result(
            "INVALID",
            "positive control(s) did not pass, so every other result in this run "
            "is uninformative -- fix the apparatus before reading the denials",
            dead,
        )

    broken = tuple(c.name for c in cases if c.kind == "assertion" and c.outcome != "pass")
    if broken:
        return Result("FAIL", "assertion(s) did not hold", broken)

    return Result("PASS", f"{len(cases)} case(s) passed, controls green", ())


def parse_cases(raw: object) -> list[Case]:
    """Parse and VALIDATE. An unknown kind or outcome is rejected rather than
    coerced: defaulting an unrecognised outcome to "pass" would silently green a
    run, and defaulting a mistyped kind to "assertion" would drop the only
    control and make the suite unfalsifiable without saying so."""
    if not isinstance(raw, list):
        raise ValueError("cases must be a JSON array")
    out: list[Case] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"case {i} is not an object")
        name = item.get("name")
        kind = item.get("kind")
        outcome = item.get("outcome")
        if not isinstance(name, str) or not name:
            raise ValueError(f"case {i} has no name")
        if kind not in ("control", "assertion"):
            raise ValueError(f"case {name!r} has unknown kind {kind!r}")
        if outcome not in ("pass", "fail", "error"):
            raise ValueError(f"case {name!r} has unknown outcome {outcome!r}")
        out.append(Case(name, kind, outcome))
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    src = sys.stdin.read() if argv[1] == "-" else open(argv[1], encoding="utf8").read()
    try:
        cases = parse_cases(json.loads(src))
    except (ValueError, json.JSONDecodeError) as e:
        print(f"INVALID  unreadable case set: {e}", file=sys.stderr)
        return EXIT["INVALID"]

    r = run_verdict(cases)
    print(f"{r.verdict}  {r.reason}")
    for c in r.culprits:
        print(f"    - {c}")
    return EXIT[r.verdict]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
