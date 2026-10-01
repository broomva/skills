#!/usr/bin/env python3
"""Spec A2's bars, read off one run directory (BRO-2674 pre-flip, workspace#840 §10
with #850's fallback rule).

    python3 scripts/skill_evals/ctx_ablation/a2.py --out DIR [--json]

Every interval is the harness's task-clustered one (``metrics._task_ci``: a t-interval
over per-task differences in pass rate), between any two arms, over the tasks both ran.
Harm tasks are never pooled: they get their own table.

The bars, as the spec states them (§10 A2):
* reflex − bare CI > 0 over A2's tasks;
* reflex ≥ qbar on the p9 tasks and on branch-first (pass counts);
* reflex − qbar CI > 0 on the rest;
* the router does not ship if reflex − qbar is entirely < 0 on a p9 task or on the
  P14 / P11 / P3 regression tasks;
* qbar becomes the default only if, in the same opus run, qbar − bare CI > 0 over A2's
  tasks and qbar − rolex is not entirely < 0 on the p9 and branch-first tasks (#850).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))

from skill_evals.ctx_ablation import metrics as m  # noqa: E402
from skill_evals.ctx_ablation import run as run_mod  # noqa: E402

P9_RE = re.compile(r"p9-(watch|change)")
BRANCH_FIRST_RE = re.compile(r"branch-first")
REGRESSION_RE = re.compile(r"^reg-p(14|11|3)-")


def _rates(rows: Sequence[Mapping[str, Any]], arm: str, tasks: set[str]) -> dict[str, float]:
    return {t: r for t, r in m._task_rates([x for x in rows if x["arm"] == arm]).items() if t in tasks}


def _counts(rows: Sequence[Mapping[str, Any]], arm: str, tasks: set[str]) -> tuple[int, int]:
    graded = [r for r in rows if r["arm"] == arm and r["task"] in tasks and r["outcome"] not in m.NON_OUTCOMES]
    return sum(1 for r in graded if r["outcome"] == m.PASS), len(graded)


def diff(rows, a: str, b: str, tasks: set[str]) -> dict[str, Any]:
    ra, rb = _rates(rows, a, tasks), _rates(rows, b, tasks)
    both = sorted(set(ra) & set(rb))
    mean = sum(ra[t] - rb[t] for t in both) / len(both) if both else None
    return {"a": a, "b": b, "tasks": len(both), "mean": None if mean is None else round(mean, 4),
            "ci": m._task_ci({t: ra[t] for t in both}, {t: rb[t] for t in both}),
            "a_count": _counts(rows, a, set(both)), "b_count": _counts(rows, b, set(both))}


def _above(d: Mapping[str, Any]) -> bool | None:
    return None if d["ci"] is None else d["ci"][0] > 0


def _below(d: Mapping[str, Any]) -> bool | None:
    return None if d["ci"] is None else d["ci"][1] < 0


def bars(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    graded = [r for r in rows if r["outcome"] not in m.NON_OUTCOMES]
    arms = sorted({r["arm"] for r in graded})
    a2 = {r["task"] for r in graded if r.get("class") != "harm"}
    p9 = {t for t in a2 if P9_RE.search(t)}
    bf = {t for t in a2 if BRANCH_FIRST_RE.search(t)}
    reg = {t for t in a2 if REGRESSION_RE.search(t)}
    rest = a2 - p9 - bf - reg
    out: dict[str, Any] = {"arms": arms, "tasks": {"a2": sorted(a2), "p9": sorted(p9), "branch_first": sorted(bf),
                                                   "regression": sorted(reg), "rest": sorted(rest)}}
    pairs = [("reflex", "bare"), ("qbar", "bare"), ("rolex", "bare"), ("reflex", "qbar"), ("reflex", "rolex"),
             ("qbar", "rolex")]
    out["pooled"] = [diff(rows, a, b, a2) for a, b in pairs if a in arms and b in arms]
    if not {"reflex", "bare", "qbar"} <= set(arms):
        out["verdict"] = "not shown: the run lacks reflex, bare or qbar"
        return out
    rb = diff(rows, "reflex", "bare", a2)
    rq_rest = diff(rows, "reflex", "qbar", rest) if rest else None
    p9_bf = []
    for t in sorted(p9 | bf):
        (rp, rn), (qp, qn) = _counts(rows, "reflex", {t}), _counts(rows, "qbar", {t})
        p9_bf.append({"task": t, "reflex": [rp, rn], "qbar": [qp, qn], "reflex_ge_qbar": rp * qn >= qp * rn})
    per_task_rq = []
    for t in sorted(p9 | reg):
        (rp, rn), (qp, qn) = _counts(rows, "reflex", {t}), _counts(rows, "qbar", {t})
        # one task: the trial-level Newcombe interval the harness reports for lifts
        ci = m.ablation_mod.newcombe_difference(rp, rn, qp, qn) if rn and qn else None
        per_task_rq.append({"task": t, "reflex": [rp, rn], "qbar": [qp, qn],
                            "ci": None if ci is None else [round(ci[0], 4), round(ci[1], 4)],
                            "entirely_below": ci is not None and ci[1] < 0})
    rq_reg = diff(rows, "reflex", "qbar", reg) if reg else None
    fails = [x["task"] for x in per_task_rq if x["entirely_below"]]
    if rq_reg and _below(rq_reg):
        fails.append("P14/P11/P3 pooled")
    out["router"] = {
        "reflex_minus_bare": rb, "reflex_minus_bare_ci_above_0": _above(rb),
        "reflex_ge_qbar_on_p9_and_branch_first": p9_bf,
        "reflex_minus_qbar_rest": rq_rest, "reflex_minus_qbar_rest_ci_above_0": _above(rq_rest) if rq_rest else None,
        "reflex_minus_qbar_regression": rq_reg,
        "per_task_reflex_vs_qbar": per_task_rq,
        "does_not_ship_because": fails,
    }
    if "rolex" in arms:
        qb = diff(rows, "qbar", "bare", a2)
        qr = diff(rows, "qbar", "rolex", p9 | bf)
        out["qbar_fallback"] = {"qbar_minus_bare": qb, "qbar_minus_bare_ci_above_0": _above(qb),
                                "qbar_minus_rolex_p9_bf": qr, "qbar_minus_rolex_entirely_below_0": _below(qr),
                                "qbar_may_become_default": bool(_above(qb)) and _below(qr) is False}
    ok = (_above(rb) and all(x["reflex_ge_qbar"] for x in p9_bf)
          and (rq_rest is None or _above(rq_rest)) and not fails)
    out["verdict"] = "router bars met" if ok else "router bars not met"
    return out


def harm_table(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, list[int]]]:
    out: dict[str, dict[str, list[int]]] = {}
    for r in rows:
        if r.get("class") != "harm" or r["outcome"] in m.NON_OUTCOMES:
            continue
        cell = out.setdefault(r["task"], {}).setdefault(r["arm"], [0, 0])
        cell[0] += r["outcome"] == m.PASS
        cell[1] += 1
    return out


def _fmt(d: Mapping[str, Any] | None) -> str:
    if not d:
        return "n/a"
    ci = d["ci"]
    ci_s = f"[{ci[0]:+.2f}, {ci[1]:+.2f}]" if ci else "n/a (< 2 tasks)"
    (ap, an), (bp, bn) = d["a_count"], d["b_count"]
    return f"{d['a']} {ap}/{an} vs {d['b']} {bp}/{bn} over {d['tasks']} tasks: mean {d['mean']:+.2f}, CI {ci_s}"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path, help="a run directory (results.jsonl)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = list(run_mod.latest_by_key(run_mod.load_results(args.out)).values())
    res = {"bars": bars(rows), "harm": harm_table(rows)}
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    b = res["bars"]
    print(f"A2 tasks: {', '.join(b['tasks']['a2'])}\n")
    for d in b.get("pooled", []):
        print("- " + _fmt(d))
    if "router" in b:
        r = b["router"]
        print("\nrouter:")
        print(f"- reflex - bare CI > 0: {r['reflex_minus_bare_ci_above_0']}")
        for x in r["reflex_ge_qbar_on_p9_and_branch_first"]:
            print(f"- {x['task']}: reflex {x['reflex'][0]}/{x['reflex'][1]} vs qbar {x['qbar'][0]}/{x['qbar'][1]}"
                  f" -> reflex >= qbar: {x['reflex_ge_qbar']}")
        print(f"- rest: {_fmt(r['reflex_minus_qbar_rest'])}")
        print(f"- regression: {_fmt(r['reflex_minus_qbar_regression'])}")
        print(f"- does not ship because: {r['does_not_ship_because'] or 'nothing'}")
    if "qbar_fallback" in b:
        q = b["qbar_fallback"]
        print(f"\nqbar fallback (#850): may become default: {q['qbar_may_become_default']}")
        print(f"- {_fmt(q['qbar_minus_bare'])}\n- {_fmt(q['qbar_minus_rolex_p9_bf'])}")
    print(f"\nverdict: {b['verdict']}")
    for task, cells in res["harm"].items():
        print(f"\nharm {task}: " + ", ".join(f"{a} {p}/{n}" for a, (p, n) in sorted(cells.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
