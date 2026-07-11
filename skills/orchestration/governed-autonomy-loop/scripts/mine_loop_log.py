#!/usr/bin/env python3
"""mine_loop_log — distill a running loop's operational history into knowledge.

A governed autonomy loop writes an append-only `loop-log.jsonl` of every decision
it makes. That log is the loop's LIVED EXPERIENCE — and a skill that freezes at
authoring time throws it away. This script closes that gap: point it at any
running instance's `loop-log.jsonl` and it produces

  1. a TAXONOMY report — what the loop actually does (action histogram, the
     reconcile_skip / resume_skip reason distributions, in-flight WIP), so the
     controller prose can be grounded in observed behavior instead of guessed;
  2. scenario FIXTURES — the distinct observed decision shapes (action + reason),
     each with a count and a redacted example (controlled fields only — no free
     text), ready to ground the scenario evals in real cases;
  3. a DRIFT check — any reason a live loop emits that the skill's contract
     (loop_state.RECONCILE_SKIP_REASONS / RESUME_SKIP_REASONS) does not know. An
     unknown reason is the signal to update the contract: the loop learned
     something the skill hasn't. This is the skill-self-evolution hook.

Run it against a live instance (local or over ssh) to keep the skill learning:
    python3 mine_loop_log.py taxonomy ~/.config/broomva/ticket-dispatch/loop-log.jsonl
    ssh host 'cat .../loop-log.jsonl' | python3 mine_loop_log.py taxonomy -

Redaction: fixtures + reports carry only controlled fields (action, reason,
ticket id, pr number, integer ages) — never unit titles / bodies / free-text
(those are DATA, and untrusted; invariant 3). So a mined report is safe to commit.

Pure stdlib. Zero network (reads a file or stdin). Deterministic.
"""
from __future__ import annotations

import collections
import json
import sys

import loop_state as ls  # same scripts/ dir

# Controlled (safe-to-emit) fields only — never free text.
_SAFE_FIELDS = ("action", "reason", "ticket", "pr", "turn", "generation",
                "pid_alive", "last_commit_age_s", "last_log_age_s", "why", "state")


def _redact(record: dict) -> dict:
    """Keep only controlled fields (invariant 3: log free text is untrusted DATA)."""
    return {k: record[k] for k in _SAFE_FIELDS if k in record}


def _base_action(action: str) -> str:
    """Strip the dry-run suffix so `reconcile_skip` and `reconcile_skip_dry` fold."""
    return action[:-4] if action.endswith("_dry") else action


def action_histogram(records: list[dict]) -> collections.Counter:
    return collections.Counter(_base_action(r.get("action", "?")) for r in records)


def reason_taxonomy(records: list[dict], action: str) -> collections.Counter:
    """Reason histogram for a given base action (e.g. reconcile_skip)."""
    c: collections.Counter = collections.Counter()
    for r in records:
        if _base_action(r.get("action", "")) == action:
            c[r.get("reason", "<none>")] += 1
    return c


def unknown_reasons(records: list[dict]) -> dict[str, list[str]]:
    """Reasons a live loop emitted that the skill's contract does not know — the
    drift signal that the skill should learn a new case. Empty dict == in sync."""
    known = {
        "reconcile_skip": set(ls.RECONCILE_SKIP_REASONS),
        "resume_skip": set(ls.RESUME_SKIP_REASONS),
    }
    out: dict[str, set] = {"reconcile_skip": set(), "resume_skip": set()}
    for r in records:
        a = _base_action(r.get("action", ""))
        if a in known:
            reason = r.get("reason")
            if reason and reason not in known[a]:
                out[a].add(reason)
    return {a: sorted(v) for a, v in out.items() if v}


def decision_fixtures(records: list[dict]) -> list[dict]:
    """Distinct observed decision shapes: (action, reason) → count + a redacted
    example. These are the raw material for grounding scenario evals in real cases,
    ranked by frequency (the common decisions matter more than the dramatic ones)."""
    groups: dict[tuple, dict] = {}
    for r in records:
        a = _base_action(r.get("action", ""))
        key = (a, r.get("reason", ""))
        g = groups.setdefault(key, {"action": a, "reason": r.get("reason", ""),
                                    "count": 0, "example": None})
        g["count"] += 1
        if g["example"] is None:
            g["example"] = _redact(r)
    return sorted(groups.values(), key=lambda g: -g["count"])


def summarize(records: list[dict]) -> dict:
    return {
        "total_records": len(records),
        "actions": dict(action_histogram(records).most_common()),
        "reconcile_skip_reasons": dict(reason_taxonomy(records, "reconcile_skip").most_common()),
        "resume_skip_reasons": dict(reason_taxonomy(records, "resume_skip").most_common()),
        "in_flight": sorted(ls.in_flight(records)),
        "unknown_reasons": unknown_reasons(records),
    }


def _load(path: str) -> list[dict]:
    if path == "-":
        out = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out
    return ls.load_jsonl(path)


def _print_report(rep: dict) -> None:
    print(f"loop-log report — {rep['total_records']} records\n")
    print("actions:")
    for a, n in rep["actions"].items():
        print(f"  {n:>6}  {a}")
    print("\nreconcile_skip reasons (the 'why NOT close' taxonomy):")
    for r, n in rep["reconcile_skip_reasons"].items() or [("<none>", 0)]:
        mark = "" if r in ls.RECONCILE_SKIP_REASONS or r == "<none>" else "  ⚠ UNKNOWN"
        print(f"  {n:>6}  {r}{mark}")
    print("\nresume_skip reasons:")
    for r, n in rep["resume_skip_reasons"].items() or [("<none>", 0)]:
        mark = "" if r in ls.RESUME_SKIP_REASONS or r == "<none>" else "  ⚠ UNKNOWN"
        print(f"  {n:>6}  {r}{mark}")
    print(f"\nin-flight WIP: {len(rep['in_flight'])} {rep['in_flight'] or ''}")
    if rep["unknown_reasons"]:
        print("\n⚠ DRIFT — reasons this loop emits that the skill contract does NOT know:")
        for a, rs in rep["unknown_reasons"].items():
            print(f"  {a}: {rs}  → add to loop_state.{a.upper()}_REASONS")
    else:
        print("\n✓ no drift — every reason is in the skill's contract vocabulary.")


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: mine_loop_log.py {taxonomy|fixtures|report} <loop-log.jsonl|->",
              file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd in ("taxonomy", "fixtures", "report"):
        if len(argv) < 2:
            print(f"{cmd}: need a loop-log path (or - for stdin)", file=sys.stderr)
            return 2
        path = argv[1]
    else:  # allow `mine_loop_log.py <path>` as a shorthand for report
        cmd, path = "report", argv[0]

    records = _load(path)
    if cmd == "fixtures":
        json_out = "--json" in argv
        fixtures = decision_fixtures(records)
        if json_out:
            print(json.dumps(fixtures, indent=2))
        else:
            for f in fixtures:
                print(f"  {f['count']:>6}  {f['action']}/{f['reason'] or '-'}  e.g. {f['example']}")
        return 0

    rep = summarize(records)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
    else:
        _print_report(rep)
    # Exit 3 on drift so a CI/cron caller can gate on "the loop learned something new".
    return 3 if rep["unknown_reasons"] else 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
