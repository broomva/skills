#!/usr/bin/env python3
"""loop_state — the deterministic state machine of a governed autonomy loop.

Skillify's load-bearing idea is the *latent-vs-deterministic split*: precision
work that has one right answer for a given input must live in tested code, not in
latent-space reasoning. The ticket-dispatch governor (BRO-1740 + BRO-1833) proved
the loop; this module extracts the parts of it that are *arithmetic*, so a new
instance inherits them tested instead of re-deriving them in prose:

  1. in_flight()        — the WIP authority: fold the append-only loop-log JSONL
                          into the set of tickets currently in flight.
  2. reseed_decision()  — the P5 rot-reseed gate: turn/generation → resume | reseed
                          | escalate (the Persist-P12 context-rot bound).
  3. resume_skip_reason() — the busy-guard: never resume a live-or-sessionless arc.
  4. validate_arc_status() — the typed arc↔governor IPC contract (arc-status.json).

Everything here is a pure function of its inputs (no clock, no network, no fs
except the thin CLI wrappers at the bottom) — so it is unit-testable to the exact
boundary conditions that a prose controller silently gets wrong.

The *decisions* that need judgment (which candidate to dispatch, whether a
`needs_decision` question is answerable, the P20 review verdict) stay latent in
the runner-prompt template — this module never tries to make them.

Pure stdlib. Zero network. Deterministic.
"""
from __future__ import annotations

import json
import sys
from typing import Iterable

# ── the arc-status contract (BRO-1833 P1) ────────────────────────────────────
# One typed file per arc at <worktree>/.claude/arc-status.json, written as the
# arc's last action each turn. The governor reads it to route the arc. Field
# presence is CONDITIONAL-REQUIRED so a deterministic reader can rely on it.
ARC_STATES = ("working", "awaiting_ci", "needs_decision", "blocked_human", "complete")
# States that require a PR (every non-`working` stop has opened a PR first).
_PR_REQUIRED = ("awaiting_ci", "needs_decision", "blocked_human", "complete")
# States that require a `question` (the human/decision-facing prompt).
_QUESTION_REQUIRED = ("needs_decision", "blocked_human")

# ── the resume_skip reason vocabulary (busy-guard + routing outcomes) ────────
RESUME_SKIP_REASONS = (
    "complete", "ci_pending", "busy", "no_session_id", "no_status",
    "needs_decision_escalated", "blocked_human", "awaiting_human",
    "merge_not_authorized", "working_but_dead",
)

# ── the reconcile_skip reason vocabulary (the "why NOT close" taxonomy) ───────
# This is the single most common governor decision in practice: across the two
# reference production loops (Mac ticket-dispatch + VPS Life-governor), reconcile_skip
# is ~65% of all records. The reasons below are the OBSERVED vocabulary (mined via
# mine_loop_log.py from ~1.9K live records); the CLASSIFICATION into one of them is a
# latent Step-A judgment, but the vocabulary is a contract a reader can rely on.
RECONCILE_SKIP_REASONS = (
    "no_pr",             # in-progress unit has no matching artifact (PR) — not loop-dispatched
    "open_pr",           # matching artifact still open — work in flight, not done
    "recently_active",   # unit touched inside RECONCILE_QUIET_HOURS — shields multi-artifact arcs
    "arc_live",          # a live arc is working it — never close regardless of quiet window
    "epic_in_progress",  # matching merged artifact is only a partial slice; the unit's roadmap is open
    "phases_open",       # child/phase artifacts still open — the parent is not complete
)

# The three outcomes of the reseed gate.
RESEED_RESUME, RESEED_RESEED, RESEED_ESCALATE = "resume", "reseed", "escalate"


# ── 1. in-flight WIP authority ───────────────────────────────────────────────

def in_flight(records: Iterable[dict]) -> set[str]:
    """Return the set of tickets currently in flight per the append-only log.

    WIP is ticket-level, not process-level: a ticket is in flight iff the log
    contains a `dispatch`/`dispatch_intent` record for it with **no later**
    `reconcile_done`/`abandoned` record for the same ticket. Records marked dry
    (`dry_run: true`, or an action ending in `_dry`) are IGNORED — a dry run can
    never consume or free a live slot. `arc_exit` (process death) does NOT free
    the slot: a dead arc with an un-Done ticket still owns its slot (this bounds
    concurrent processes AND open-PR accumulation).

    Records are processed in order; the LAST relevant record for a ticket wins,
    so this is a strict left-fold and callers must pass the log in write order.
    """
    state: dict[str, bool] = {}
    for r in records:
        if not isinstance(r, dict):
            continue
        if r.get("dry_run") is True:
            continue
        action = r.get("action", "")
        if action.endswith("_dry"):
            continue
        ticket = r.get("ticket")
        if not ticket:
            continue
        if action in ("dispatch", "dispatch_intent"):
            state[ticket] = True
        elif action in ("reconcile_done", "abandoned"):
            state[ticket] = False
    return {t for t, live in state.items() if live}


def in_flight_count(records: Iterable[dict]) -> int:
    return len(in_flight(records))


def load_jsonl(path: str) -> list[dict]:
    """Parse an append-only JSONL log, skipping blank/corrupt lines (fail-open
    to a partial log rather than crashing the whole tick on one bad line)."""
    out: list[dict] = []
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return out
    with f:
        for line in f:
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


# ── 2. the P5 rot-reseed gate ────────────────────────────────────────────────

def reseed_decision(turn: int, generation: int, cap: int, max_generations: int) -> str:
    """Decide how to advance a resumed arc: resume | reseed | escalate.

    The rot-reseed gate (BRO-1833 P5) bounds context rot the way Persist (P12)
    does — state lives in the git checkpoint, so an aging `-r` session past the
    ~1h / >100K-token "dumb zone" is thrown away and a FRESH session is seeded
    from the committed work instead.

      turn < cap                       → RESUME  (continue the same `-r` session)
      turn >= cap, generation >= max   → ESCALATE (runaway guard: reseeds keep
                                          hitting the cap without finishing →
                                          hand to a human, reason reseed_exhausted)
      turn >= cap, generation < max    → RESEED  (fresh --session-id from the
                                          checkpoint; turn resets to 1, gen→gen+1)

    `generation` is the count of reseeds already done in the CURRENT epoch (since
    the ticket's most recent dispatch — a re-dispatch resets it). `max_generations
    == 0` means "never auto-reseed": at the cap it escalates immediately.

    Non-integer / negative inputs are coerced defensively (a bad knob must fall to
    the conservative branch, never throw inside the control loop).
    """
    turn = _nonneg_int(turn)
    generation = _nonneg_int(generation)
    cap = max(1, _nonneg_int(cap, default=1))
    max_generations = _nonneg_int(max_generations)
    if turn < cap:
        return RESEED_RESUME
    if generation >= max_generations:
        return RESEED_ESCALATE
    return RESEED_RESEED


def _nonneg_int(value, default: int = 0) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= 0 else default


# ── 3. the busy-guard (never resume a live-or-sessionless arc) ────────────────

def resume_skip_reason(*, has_session: bool, pid_alive: bool, has_status: bool,
                       state: str | None, pending_resume_intent: bool = False) -> str | None:
    """Return the resume_skip reason if this in-flight arc must NOT be resumed on
    an inner tick, or None if it is a resume candidate (the governor then routes
    by `state`).

    The guard order is load-bearing and matches the reference governor's busy-guard:
      - no resumable session id (legacy pre-P2 arc) → no_session_id
      - the arc process is still alive (mid-turn)   → busy   (never double-drive)
      - an unconfirmed resume_intent (a `resume_intent` with no later `resume` —
        a crash mid-spawn) → busy  (the BRO-1833 crash-window guard: a second `-r`
        on the same session id the pid check alone misses because the first spawn
        may not have a live pid yet)
      - no typed status file yet                    → no_status
      - state complete                              → complete (leave for reconcile)

    A `working` status with a DEAD pid is the one subtle case: `working` is an
    advisory heartbeat, never a liveness guarantee, so a dead arc last seen
    `working` is surfaced as working_but_dead (GOVERN/stall territory), not
    resumed. Everything else (awaiting_ci / needs_decision / blocked_human) is a
    genuine resume candidate and returns None.
    """
    if not has_session:
        return "no_session_id"
    if pid_alive or pending_resume_intent:
        return "busy"
    if not has_status:
        return "no_status"
    if state == "complete":
        return "complete"
    if state == "working":
        return "working_but_dead"
    return None


# ── 4. the arc-status.json typed contract validator ──────────────────────────

def validate_arc_status(obj) -> tuple[bool, list[str]]:
    """Validate a parsed arc-status.json against the typed contract.

    Returns (ok, errors). The contract (BRO-1833 P1) is deterministic so the
    governor never has to guess: exact JSON types, conditional-required presence.
    A `"#"`-prefixed or object-valued field is a contract violation a real reader
    rejects — this function is that reader's spec, executable.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return False, ["arc-status is not a JSON object"]

    state = obj.get("state")
    if state not in ARC_STATES:
        errors.append(f"state {state!r} not in {ARC_STATES}")

    if state in _PR_REQUIRED:
        pr = obj.get("pr")
        if not isinstance(pr, int) or isinstance(pr, bool):
            errors.append(f"pr must be a bare integer for state {state!r} (got {pr!r})")

    if state in _QUESTION_REQUIRED:
        q = obj.get("question")
        if not isinstance(q, str) or not q.strip():
            errors.append(f"question (non-empty string) required for state {state!r}")

    if "evidence" in obj and not isinstance(obj["evidence"], str):
        errors.append("evidence must be a one-line string, never a nested object/array")

    if "turn" in obj and (not isinstance(obj["turn"], int) or isinstance(obj["turn"], bool)):
        errors.append("turn must be a bare integer")

    return (not errors), errors


# ── thin CLI (so the shell scheduler + smoke test can call the arithmetic) ────

def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: loop_state.py {in-flight <jsonl> | reseed --turn N --gen N "
              "--cap N --max N | validate-status <json>}", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]

    if cmd == "in-flight":
        if not rest:
            print("in-flight: need a JSONL path", file=sys.stderr)
            return 2
        print(in_flight_count(load_jsonl(rest[0])))
        return 0

    if cmd == "reseed":
        kv = _parse_flags(rest)
        print(reseed_decision(kv.get("turn", 0), kv.get("gen", 0),
                              kv.get("cap", 8), kv.get("max", 3)))
        return 0

    if cmd == "validate-status":
        if not rest:
            print("validate-status: need a JSON path", file=sys.stderr)
            return 2
        try:
            obj = json.load(open(rest[0], encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"unreadable: {e}", file=sys.stderr)
            return 2
        ok, errs = validate_arc_status(obj)
        if ok:
            print("valid")
            return 0
        for e in errs:
            print(f"invalid: {e}", file=sys.stderr)
        return 1

    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


def _parse_flags(rest: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    i = 0
    while i < len(rest) - 1:
        if rest[i].startswith("--"):
            out[rest[i][2:]] = _nonneg_int(rest[i + 1])
            i += 2
        else:
            i += 1
    return out


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
