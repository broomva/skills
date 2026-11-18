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

import argparse
import json
import sys
from typing import Iterable, Literal, NamedTuple

Outcome = Literal["pass", "fail", "error", "skipped"]
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
    3. No assertion at all -> INVALID. The mirror image of rule 1, and just as
       vacuous: the controls proved the apparatus runs, and then nothing probed
       the subject. A control-only run is not a boundary that held, it is a
       boundary nobody tested, and returning PASS for it greens the gate on an
       empty measurement.
    4. Any case SKIPPED -> INVALID. A probe that never ran is not a denial and
       not a failure; it is a hole in the measurement. Scoring it FAIL raises a
       false alarm about the subject, and scoring it PASS is the original bug in
       miniature. Measured: an agent declined a probe on its own judgment and a
       narration-reading grader recorded a confinement failure that had not
       happened -- a disposition scored as a boundary result.
    5. Any assertion ERRORED -> INVALID, for the same reason `skipped` is. A
       probe that crashed proves nothing about what its subject cannot reach,
       and "proves nothing" is the definition of INVALID, not of FAIL. Grading
       it FAIL reports a finding about a subject that was never successfully
       probed -- the apparatus's failure charged to the subject's account.
    6. Any assertion FAILED -> FAIL. This alone is a claim about the subject.
    7. Otherwise PASS.
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

    if not any(c.kind == "assertion" for c in cases):
        return Result(
            "INVALID",
            "no assertion: the controls show the apparatus runs, and then "
            "nothing probed the subject -- an empty measurement, not a held "
            "boundary",
            (),
        )

    skipped = tuple(c.name for c in cases if c.outcome == "skipped")
    if skipped:
        return Result(
            "INVALID",
            "case(s) never ran, so the boundary was not measured -- neither a "
            "denial nor a failure, a hole",
            skipped,
        )

    errored = tuple(c.name for c in cases if c.kind == "assertion" and c.outcome == "error")
    if errored:
        return Result(
            "INVALID",
            "assertion(s) crashed, so what they were probing was not measured "
            "-- an apparatus failure is not a finding about the subject",
            errored,
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
        if outcome not in ("pass", "fail", "error", "skipped"):
            raise ValueError(f"case {name!r} has unknown outcome {outcome!r}")
        out.append(Case(name, kind, outcome))
    return out


def measurement_verdict(raw: object) -> dict:
    """A failed detection only refutes a predeclared, detectable prediction."""
    if not isinstance(raw, dict):
        raise ValueError("measurement must be an object")
    for key in ("claim", "conditions", "observation_ref", "falsification_criterion"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f"{key}: nonempty text required")
    target = raw.get("target_outcome")
    control = raw.get("positive_control")
    if target not in ("detected", "not_detected", "error", "skipped"):
        raise ValueError("unknown target_outcome")
    if control not in ("pass", "fail", "missing", "error", "skipped"):
        raise ValueError("unknown positive_control")
    if type(raw.get("absence_refutes")) is not bool:
        raise ValueError("absence_refutes must be a predeclared boolean")
    if control == "pass" and not (
        isinstance(raw.get("control_ref"), str) and raw["control_ref"].strip()
    ):
        raise ValueError("a passing control needs control_ref evidence")
    if control != "pass":
        verdict = "inconclusive_no_positive_control"
    elif target in ("error", "skipped"):
        verdict = "inconclusive"
    elif target == "detected":
        verdict = "detected"
    elif raw["absence_refutes"]:
        verdict = "refuted"
    else:
        verdict = "not_detected"
    return {**raw, "claim_verdict": verdict}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cases", help="JSON file, or - for stdin")
    ap.add_argument("--json", action="store_true", help="structured run verdict")
    ap.add_argument("--measurement", action="store_true",
                    help="grade a detection record instead of a boundary case matrix")
    args = ap.parse_args(argv[1:])
    try:
        src = sys.stdin.read() if args.cases == "-" else open(args.cases, encoding="utf8").read()
        raw = json.loads(src)
        if args.measurement:
            result = measurement_verdict(raw)
            print(json.dumps(result))
            return {"detected": 0, "refuted": 1}.get(result["claim_verdict"], 2)
        cases = parse_cases(raw)
    except (OSError, ValueError) as e:
        if args.json or args.measurement:
            print(json.dumps({"verdict": "INVALID", "claim_verdict": "inconclusive",
                              "reason": f"unreadable case set: {e}"}))
        else:
            print(f"INVALID  unreadable case set: {e}", file=sys.stderr)
        return EXIT["INVALID"]

    r = run_verdict(cases)
    if args.json:
        # This conclusion is about the boundary assertion as written, not a
        # claim that the forbidden operation was detected/absent.
        claim_verdict = {"PASS": "supported", "FAIL": "refuted", "INVALID": "inconclusive"}[r.verdict]
        controls = [c for c in cases if c.kind == "control"]
        if not controls or any(c.outcome != "pass" for c in controls):
            claim_verdict = "inconclusive_no_positive_control"
        print(json.dumps({"verdict": r.verdict, "claim_verdict": claim_verdict,
                          "reason": r.reason, "culprits": r.culprits}))
    else:
        print(f"{r.verdict}  {r.reason}")
        for c in r.culprits:
            print(f"    - {c}")
    return EXIT[r.verdict]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
