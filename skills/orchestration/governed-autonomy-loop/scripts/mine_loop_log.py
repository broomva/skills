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

A fourth mode — `health` — is a loop-health alarm (distinct from #3 drift): it
flags a WEDGED in-flight arc (dead + pinning a WIP slot for ≥N ticks, exit 3), the
silent-block condition that halts the loop. Wire it into a cron/watch to page when
a governor gets stuck (BRO-1851).

Run it against a live instance (local or over ssh) to keep the skill learning:
    python3 mine_loop_log.py taxonomy ~/.config/broomva/ticket-dispatch/loop-log.jsonl
    python3 mine_loop_log.py health   ~/.config/broomva/ticket-dispatch/loop-log.jsonl
    ssh host 'cat .../loop-log.jsonl' | python3 mine_loop_log.py taxonomy -

Redaction: fixtures + reports carry only controlled fields (action, ticket id, pr
number, integer ages, and vocab-VALIDATED reason/why/state) — never unit titles /
bodies / free-text (those are DATA, and untrusted; invariant 3). Crucially, a
field name is not trusted: `reason` is a vocab token on skip actions but FREE TEXT
on `label_apply`, so it is whitelist-validated (unknown value → redacted), making
"safe to commit" a mechanical guarantee, not an assumption.

Pure stdlib. Zero network (reads a file or stdin). Deterministic.
"""
from __future__ import annotations

import collections
import json
import re
import sys

import loop_state as ls  # same scripts/ dir

# Structurally-controlled fields (ids / ints / bools) — safe to pass through.
_SAFE_FIELDS = ("action", "reason", "ticket", "pr", "turn", "generation",
                "pid_alive", "last_commit_age_s", "last_log_age_s", "why", "state")

# CRITICAL: the field NAME is not enough. `reason` is a controlled vocab token on
# the skip actions, but FREE TEXT on `label_apply` (the eligibility rationale the
# governor forms by reading the UNTRUSTED unit body) and on some `dispatch_skip`
# records. Trusting the name leaks untrusted-derived free text into a committable
# report (invariant 3 violation). So vocab fields are whitelist-VALIDATED, not
# name-trusted (the BRO-1797 whitelist-of-one discipline): keep the value iff it is
# in the field's controlled vocab, else replace with a marker. Fails CLOSED.
_REDACTED = "<redacted:free-text>"
_ESCALATE_WHY = {"fork", "unsafe", "undeterminable", "governance", "re-raised",
                 "blocked_human", "reseed_exhausted"}
_CONTROLLED_REASONS = (set(ls.RECONCILE_SKIP_REASONS) | set(ls.RESUME_SKIP_REASONS)
                       | {"branch_exists", "wip_full"})  # fixed dispatch tokens
_FIELD_VOCAB = {"reason": _CONTROLLED_REASONS, "why": _ESCALATE_WHY,
                "state": set(ls.ARC_STATES)}
# A `ticket` must be a tracker id (e.g. BRO-1742) — never free text. Validating its
# STRUCTURE (not its name) closes the "trust the field name" class entirely.
_TICKET_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-\d+$")


def _safe_value(field: str, value):
    """A vocab-controlled field's value is kept iff it is in that vocab; a `ticket`
    iff it is a tracker id; any other string is dropped to the redaction marker
    (fails closed — an unrecognized value is treated as untrusted free text). The
    empty string passes through (an absent-reason field is '', not hidden text), and
    non-string fields (ints, bools) pass through unchanged."""
    if not isinstance(value, str) or value == "":
        return value
    if field == "ticket":
        return value if _TICKET_RE.match(value) else _REDACTED
    vocab = _FIELD_VOCAB.get(field)
    if vocab is not None and value not in vocab:
        return _REDACTED
    return value


def _redact(record: dict) -> dict:
    """Keep only controlled fields, whitelist-validating the vocab fields
    (invariant 3: a log's free text is untrusted DATA and must never reach a
    committable report). This is the safe-to-commit guarantee, mechanically."""
    return {k: _safe_value(k, record[k]) for k in _SAFE_FIELDS if k in record}


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
        # Redact the reason used in the GROUP KEY + label too — not just the
        # example — else a free-text label_apply reason leaks via the fixture label.
        reason = _safe_value("reason", r.get("reason", ""))
        key = (a, reason)
        g = groups.setdefault(key, {"action": a, "reason": reason,
                                    "count": 0, "example": None})
        g["count"] += 1
        if g["example"] is None:
            g["example"] = _redact(r)
    return sorted(groups.values(), key=lambda g: -g["count"])


def health(records: list[dict], min_ticks: int = 2) -> dict:
    """Detect WEDGED in-flight arcs — the silent-block condition (BRO-1851).

    An arc is WEDGED when it holds a WIP slot (in-flight) but its process is
    dead/stuck (`stall` / `arc_exit`, or `resume_skip` with reason `no_status` /
    `working_but_dead`) AND there has been no forward progress (dispatch/resume)
    for ≥ `min_ticks` tick_fires. The governor can neither route it (no typed
    status) nor reconcile it (PR not closed), so at a low WIP_CAP it blocks ALL
    dispatch — exactly the case that silently blocked the operator for ~8h
    (BRO-1481). This is loop HEALTH, orthogonal to the reason-drift check: drift
    asks "is the vocabulary complete?"; health asks "is the loop actually moving?"

    Deterministic: a forward-progress record (dispatch/resume) CLEARS a prior dead
    signal, so a re-dispatched arc is not falsely flagged.
    """
    live = ls.in_flight(records)
    tick_idx: list[int] = []
    last_progress: dict[str, int] = {}
    dead_signal: dict[str, tuple[int, str]] = {}
    for i, r in enumerate(records):
        if not isinstance(r, dict) or r.get("dry_run") is True:
            continue
        a = _base_action(r.get("action", ""))
        if a == "tick_fire":
            tick_idx.append(i)
            continue
        t = r.get("ticket")
        if not t:
            continue
        if a in ("dispatch", "dispatch_intent", "resume"):
            last_progress[t] = i
            dead_signal.pop(t, None)                       # progress clears a dead signal
        elif a == "resume_skip" and r.get("reason") == "complete":
            dead_signal.pop(t, None)                       # a `complete` arc is DONE, not
            # wedged — it is legitimately idle waiting for its PR to merge (mirrors the
            # governor's Step D `complete`/`blocked_human` stall carve-out). Clear any
            # earlier dead signal so a done-but-unmerged arc is not falsely flagged.
        elif a in ("stall", "arc_exit"):
            dead_signal[t] = (i, a)
        elif a == "resume_skip" and r.get("reason") in ("no_status", "working_but_dead"):
            dead_signal[t] = (i, "resume_skip:" + str(r.get("reason")))
    wedged = []
    for t in sorted(live):
        if t not in dead_signal:
            continue
        lp = last_progress.get(t, -1)
        ticks_since = sum(1 for ti in tick_idx if ti > lp)
        if ticks_since >= min_ticks:
            wedged.append({"ticket": t, "last_state": dead_signal[t][1],
                           "ticks_pinned": ticks_since})
    return {"in_flight": len(live), "min_ticks": min_ticks, "wedged": wedged}


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


def _flag_int(argv: list[str], name: str, default: int) -> int:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            try:
                return max(1, int(argv[i + 1]))
            except ValueError:
                pass
    return default


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: mine_loop_log.py {taxonomy|fixtures|health|report} <loop-log.jsonl|->",
              file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd in ("taxonomy", "fixtures", "health", "report"):
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

    if cmd == "health":
        rep = health(records, min_ticks=_flag_int(argv, "--min-ticks", 2))
        if "--json" in argv:
            print(json.dumps(rep, indent=2))
        elif rep["wedged"]:
            print(f"⚠ WEDGED — {len(rep['wedged'])} in-flight arc(s) pinned + dead for "
                  f"≥{rep['min_ticks']} ticks (of {rep['in_flight']} in flight):")
            for w in rep["wedged"]:
                print(f"  {w['ticket']}  {w['last_state']}  ({w['ticks_pinned']} ticks pinned)"
                      "  → escalate/abandon/merge its PR")
        else:
            print(f"✓ healthy — no wedged arcs ({rep['in_flight']} in flight).")
        # exit 3 on a wedge so a cron/CI caller can page (mirrors the drift exit code).
        return 3 if rep["wedged"] else 0

    rep = summarize(records)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
    else:
        _print_report(rep)
    # Exit 3 on drift so a CI/cron caller can gate on "the loop learned something new".
    return 3 if rep["unknown_reasons"] else 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
