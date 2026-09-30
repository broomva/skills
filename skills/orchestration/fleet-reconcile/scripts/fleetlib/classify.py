"""The class table (spec §5.4), the overlap pass and the count check (§5.3).

Classes are tried in order and the first match wins. Each rule is one entry
of RULES; tests/mutation_check.py deletes each entry and swaps each pair that
can both match, and a test must fail every time.

Activity is always a transcript's modification time (the session's own or a
subagent's), never Paseo's updatedAt or lastActivityAt, which a label write
moves (spike P8). Phase 1 only reports: `action` is what phase 3 would do.

Choices the spec leaves open, pending the spec (broomva/workspace#842):
- Class 2 also reads a background job file whose state is blocked and whose
  detail carries Claude Code's usage-limit text, since the core's board keeps
  only the error class (rate_limit) and no reset time.
- A board session.died or ARC-STATUS row counts only while nothing happened
  after it: a transcript entry more than GRACE_S later means the session went
  on (the "died-then-continued" case the core measured on 2026-09-30), and an
  ARC-STATUS is current only when its Stop is the row's latest event.
- "idle" is status idle, or a background session with no process whose state
  is done or stopped (resume's case in §5.3).
- A terminal status on a repo whose PRs could not be read is unknown, not
  closed: "the PR (if any) merged or closed" can't be checked.
"""
from __future__ import annotations

from collections import namedtuple
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from . import common, parsers

RUNNING_S = 2 * 3600    # classes 5 and 6
STALL_S = 3600          # classes 9 and 9a
GRACE_S = 120           # transcript writes this soon after an event belong to it
LIMIT_ERRORS = ("rate_limit",)
TRANSIENT_ERRORS = ("server_error", "overloaded", "api_error", "network_error", "timeout", "max_output_tokens")
TERMINAL = ("MERGED", "CLOSED", "DONE")
PROMPT_WAITS = ("permission prompt", "dialog open")


class Stop(str):
    """A predicate's verdict that the session is unknown; classification stops."""


Match = Union[None, str, Stop]
Rule = namedtuple("Rule", "id name test act")


class Env:
    def __init__(self, scope: str, now: float, repos: List[Dict[str, Any]]) -> None:
        self.scope = scope
        self.now = now
        self.repo_ok = {r["repo"]: bool(r.get("ok")) for r in repos}
        self.open_prs: Dict[Tuple[str, str], List[int]] = {}
        for r in repos:
            for p in r.get("prs") or []:
                self.open_prs.setdefault((r["repo"], p["head"]), []).append(p["number"])


# --------------------------------------------------------------------------
# Readings shared by the rules

def activity(s: Dict[str, Any]) -> Optional[float]:
    t = s.get("transcript") or {}
    vals = [v for v in (t.get("mtime"), t.get("sub")) if isinstance(v, (int, float))]
    return max(vals) if vals else None


def went_on_after(s: Dict[str, Any], t: Optional[float]) -> bool:
    a = activity(s)
    return t is not None and a is not None and a > t + GRACE_S


def current_arc(s: Dict[str, Any]) -> Optional[str]:
    b = s.get("board") or {}
    if not b.get("arc_status") or b.get("arc_ts") is None:
        return None
    if b.get("last_ts") is not None and b["arc_ts"] < b["last_ts"]:
        return None
    if went_on_after(s, b["arc_ts"]):
        return None
    return b["arc_status"]


def ours(s: Dict[str, Any]) -> bool:
    return bool(s.get("fleet_key"))


def idle(s: Dict[str, Any]) -> bool:
    return s.get("status") == "idle" or (s.get("kind") == "background" and s.get("pid") is None
                                         and s.get("status") is None and s.get("state") in ("done", "stopped"))


def bg_question(s: Dict[str, Any]) -> bool:
    """A background session blocked on a question to its own user (§5.4 class 7)."""
    j = s.get("job") or {}
    return (s.get("kind") == "background" and j.get("state") == "blocked" and not j.get("limit_text")
            and bool(j.get("needs") or j.get("suggested_reply"))
            and s.get("waiting_for") not in PROMPT_WAITS)


#: When no reset time can be read (an interactive session's limit text lives
#: only in its transcript, and may have scrolled out of the tail read), the
#: reset is assumed this long after the death: the session limit's window.
ASSUMED_RESET_S = 5 * 3600


def limit_reset(s: Dict[str, Any]) -> Tuple[Optional[float], str]:
    """(epoch, "stated" | "assumed" | "unknown") for a class-2 session."""
    j = s.get("job") or {}
    b = s.get("board") or {}
    base = j.get("updated_at") or b.get("died_ts") or s.get("started_at") or 0.0
    t = parsers.reset_epoch(j.get("reset_text") or s.get("limit_text"), base)
    if t:
        return t, "stated"
    died = b.get("died_ts") or j.get("updated_at")
    if died:
        return died + ASSUMED_RESET_S, "assumed"
    return None, "unknown"


def _t(v: Optional[float]) -> str:
    return common.ts(v)[:16] + "Z" if v else "?"


# --------------------------------------------------------------------------
# The rules. Each test returns None (no match), the evidence (a match), or a
# Stop (unknown, with the reason).

def _out_of_scope(s: Dict[str, Any], env: Env) -> Match:
    if s.get("scope") == env.scope:
        return None
    if s.get("placement") == "unplaced":
        return "cwd gone and no board row or worktree parent to place it"
    return "placed in scope %s by %s" % (s.get("scope") or "none", s.get("placement"))


def _dead_limit(s: Dict[str, Any], env: Env) -> Match:
    b = s.get("board") or {}
    j = s.get("job") or {}
    if b.get("state") == "died" and b.get("died_error") in LIMIT_ERRORS and not went_on_after(s, b.get("died_ts")):
        ev = "board: session.died (%s) at %s" % (b["died_error"], _t(b.get("died_ts")))
    elif j.get("state") == "blocked" and j.get("limit_text") and not went_on_after(s, j.get("updated_at")):
        ev = "job file: %s" % (j.get("detail") or j.get("needs"))
    else:
        return None
    t, how = limit_reset(s)
    return "%s; reset %s %s%s" % (ev, how, _t(t), " (passed)" if t and t <= env.now else "")


def _waiting(s: Dict[str, Any], env: Env) -> Match:
    if s.get("status") == "waiting" and s.get("waiting_for") and not bg_question(s):
        return "listing: status waiting, waitingFor %r" % s["waiting_for"]
    return None


def _error(s: Dict[str, Any], env: Env) -> Match:
    if s.get("state") == "failed":
        return "listing: state failed" + (" (%s)" % (s["job"]["detail"]) if s.get("job") and s["job"].get("detail")
                                          else "")
    b = s.get("board") or {}
    if b.get("state") == "died" and b.get("died_error") not in LIMIT_ERRORS and not went_on_after(s, b.get("died_ts")):
        return "board: session.died (%s) at %s%s" % (b.get("died_error"), _t(b.get("died_ts")),
                                                     ", transient" if b.get("died_error") in TRANSIENT_ERRORS else "")
    return None


def _running(s: Dict[str, Any], env: Env) -> Match:
    a = activity(s)
    if s.get("status") == "busy" and a is not None and env.now - a <= RUNNING_S:
        return "busy; transcript modified %s ago" % common.age(env.now - a)
    return None


def _hung(s: Dict[str, Any], env: Env) -> Match:
    a = activity(s)
    if s.get("status") == "busy" and a is not None and env.now - a > RUNNING_S:
        return "busy; nothing modified for %s" % common.age(env.now - a)
    return None


def _blocked_owner(s: Dict[str, Any], env: Env) -> Match:
    if current_arc(s) == "BLOCKED":
        return "board: ARC-STATUS BLOCKED at %s" % _t((s.get("board") or {}).get("arc_ts"))
    if bg_question(s):
        return "job file: blocked on a question to its user (%s)" % (s["job"].get("needs") or s["job"].get("detail"))
    return None


def _closed(s: Dict[str, Any], env: Env) -> Match:
    arc = current_arc(s)
    if arc not in TERMINAL:
        return None
    repo, branch = s.get("repo"), s.get("branch")
    if not env.repo_ok.get(repo or "", False):
        return Stop("ARC-STATUS %s, but the PRs of its repo could not be read" % arc)
    open_ = env.open_prs.get((repo, branch or ""), [])
    if open_:
        return None
    return "board: ARC-STATUS %s; no open PR on %s" % (arc, branch or "its branch")


def _stalled(s: Dict[str, Any], env: Env) -> Match:
    a = activity(s)
    if ours(s) and idle(s) and current_arc(s) not in TERMINAL and a is not None and env.now - a >= STALL_S:
        return "ours (%s), idle, transcript unmodified for %s" % (s["fleet_key"], common.age(env.now - a))
    return None


def _idle_recent(s: Dict[str, Any], env: Env) -> Match:
    a = activity(s)
    if ours(s) and idle(s) and current_arc(s) not in TERMINAL and a is not None and env.now - a < STALL_S:
        return "ours (%s), idle, transcript modified %s ago" % (s["fleet_key"], common.age(env.now - a))
    return None


def _unmanaged(s: Dict[str, Any], env: Env) -> Match:
    if ours(s):
        return None
    if s.get("fleet_shaped"):
        return "no fleet key: a fleet-shaped name the ledger doesn't hold"
    return "no fleet key, not adopted" + (" (Paseo agent)" if s.get("paseo") else "")


# What phase 3 would do: for fleet and adopted sessions the class's action;
# for the owner's and other tools' sessions, a report (§5.4, the paragraph
# after the table).
def _act(fleet: str, other: str = "report") -> Callable[[Dict[str, Any]], str]:
    return lambda s: fleet if ours(s) else other


ACTIONS = {
    "1": _act("nothing", "nothing"),
    "2": _act("resume after the reset; no spawns in the scope until then",
              "report; no spawns in the scope until the reset"),
    "3": _act("ask; the coordinator never approves", "ask; the coordinator never approves"),
    "4": _act("report; one resume for a transient 5xx or network error"),
    "5": _act("nothing", "nothing"),
    "6": _act("report; one mail"),
    "7": _act("carry the ask forward", "carry the ask forward"),
    "8": _act("report what a janitor would remove"),
    "9": _act("one mail per 6 h, from fixed templates"),
    "9a": _act("nothing", "nothing"),
    "10": _act("report only", "report only"),
}

# One rule per line: the mutation check deletes and swaps lines.
RULES: List[Rule] = [
    Rule("1", "out of scope", _out_of_scope, ACTIONS["1"]),
    Rule("2", "dead: limit", _dead_limit, ACTIONS["2"]),
    Rule("3", "waiting at a prompt", _waiting, ACTIONS["3"]),
    Rule("4", "error", _error, ACTIONS["4"]),
    Rule("5", "running", _running, ACTIONS["5"]),
    Rule("6", "hung", _hung, ACTIONS["6"]),
    Rule("7", "blocked on the owner", _blocked_owner, ACTIONS["7"]),
    Rule("8", "closed", _closed, ACTIONS["8"]),
    Rule("9", "stalled", _stalled, ACTIONS["9"]),
    Rule("9a", "idle, recent", _idle_recent, ACTIONS["9a"]),
    Rule("10", "unmanaged", _unmanaged, ACTIONS["10"]),
]
ORDER = [r.id for r in RULES] + ["unknown"]
NAMES = dict([(r.id, r.name) for r in RULES] + [("unknown", "unknown")])


def classify(s: Dict[str, Any], env: Env) -> Dict[str, str]:
    for rule in RULES:
        got = rule.test(s, env)
        if isinstance(got, Stop):
            return {"class": "unknown", "name": "unknown", "evidence": str(got), "action": "report only"}
        if got:
            return {"class": rule.id, "name": rule.name, "evidence": got, "action": rule.act(s)}
    t = s.get("transcript") or {}
    why = "transcript missing" if not t.get("found") else "no class matched (state %s, status %s)" % (
        s.get("state") or "-", s.get("status") or "-")
    return {"class": "unknown", "name": "unknown", "evidence": why, "action": "report only"}


def matching(s: Dict[str, Any], env: Env) -> List[str]:
    """Every rule that matches, in table order: the tests' view of overlaps."""
    return [r.id for r in RULES if (lambda g: bool(g) and not isinstance(g, Stop))(r.test(s, env))]


# --------------------------------------------------------------------------
# The overlap pass (after classification and independent of it)

def overlap_pass(sessions: List[Dict[str, Any]], claims: Dict[str, List[Dict[str, Any]]],
                 scope: str) -> Dict[str, Any]:
    """Every pair of live sessions in the scope whose claims share a repo and
    path. A fleet session would be mailed once per overlap, naming the other
    and the paths; an unmanaged one gets only the core's in-session line.
    Claims recorded as unknown are ignored here (they block driver
    eligibility instead, §5.5)."""
    by_id = {s["session_id"]: s for s in sessions}
    live = {sid for sid, s in by_id.items() if s.get("pid") is not None and s.get("scope") == scope}
    holders: Dict[Tuple[str, str], List[str]] = {}
    for sid, cl in sorted(claims.items()):
        if sid not in live:
            continue
        for c in cl:
            if c.get("unknown") or not c.get("repo") or not c.get("path"):
                continue
            ids = holders.setdefault((c["repo"], c["path"]), [])
            if sid not in ids:
                ids.append(sid)
    pairs: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for (repo, path), ids in sorted(holders.items()):
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                pairs.setdefault(tuple(sorted((a, b))), []).append((repo, path))
    out = []
    for (a, b), paths in sorted(pairs.items()):
        mails = [x for x in (a, b) if ours(by_id[x])]
        out.append({"sessions": [a, b], "paths": [p for _, p in paths], "repo": paths[0][0],
                    "would_mail": mails})
    return {"overlaps": out}


# --------------------------------------------------------------------------
# The count check (§5.3)

def count_check(snap: Dict[str, Any]) -> Dict[str, Any]:
    scope = snap["scope"]
    surf = snap["surfaces"]
    if not surf.get("listing", {}).get("ok"):
        return {"ran": False, "reason": "the session listing was not read (%s)"
                % surf.get("listing", {}).get("error", "?")}
    sessions = snap["sessions"]
    live = {s["session_id"] for s in sessions if s.get("pid") is not None}
    out: Dict[str, Any] = {"ran": True}
    if surf.get("paseo_records", {}).get("ok"):
        recs = [r for r in snap["paseo_open"] if r["scope"] == scope]
        out["records_without_process"] = [
            {"agent_id": r["agent_id"], "session_id": r["session_id"], "title": r["title"],
             "last_status": r["last_status"], "why": "no session id in the record" if not r["session_id"]
             else "claude agents lists no live process for it"}
            for r in recs if not r["session_id"] or r["session_id"] not in live]
        out["records_unplaced"] = sum(1 for r in snap["paseo_open"] if r["placement"] == "unplaced"
                                      and (not r["session_id"] or r["session_id"] not in live))
    else:
        out["records_without_process"] = None
        out["records_reason"] = "Paseo's records were not read"
    out["unmanaged"] = [
        {"session_id": s["session_id"], "name": s["name"], "kind": s["kind"], "live": s.get("pid") is not None,
         "fleet_shaped": s.get("fleet_shaped")}
        for s in sessions if s.get("scope") == scope and not s.get("paseo") and not s.get("fleet_key")]
    return out


def classify_all(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    env = Env(snap["scope"], snap["now"], snap.get("repos") or [])
    return [dict(classify(s, env), session_id=s["session_id"]) for s in snap["sessions"]]


def spawn_pause(snap: Dict[str, Any], results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Class 2's pause applies whoever hit the limit, since the limit is shared."""
    by_id = {s["session_id"]: s for s in snap["sessions"]}
    resets = [(limit_reset(by_id[r["session_id"]]), r["session_id"]) for r in results
              if r["class"] == "2" and by_id[r["session_id"]].get("scope") == snap["scope"]]
    if not resets:
        return None
    known = [(t, how) for (t, how), _ in resets if t]
    until, how = max(known) if known else (None, "unknown")
    return {"until": until, "how": how, "sessions": [sid for _, sid in resets],
            "active": until is None or until > snap["now"]}
