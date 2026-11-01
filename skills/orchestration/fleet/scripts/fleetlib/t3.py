"""T3 Code's threads, scheduled tasks, runs and open user-input requests
(BRO-3376), read from T3's own state database.

The database is T3's, not ours: it is opened read-only (`mode=ro`, so WAL is
never checkpointed and nothing is written), and every column read is pinned in
COLUMNS. A missing table or column raises T3Unread, so the surface reads as
not read, never as empty. No model and no network.

What is NOT read is part of the contract: a scheduled task's prompt and its
webhook token and secret, a thread's messages, a request's payload (the
question text can carry anything). A thread's payload is parsed only for its
worktree path.

The rows feed two findings, keyed per thread (report.py raises them as asks):
- a scheduled thread whose run is waiting on a user-input request (Claude's
  AskUserQuestion, Codex's requestUserInput: T3 records both as `user_input`)
  for `t3_wait_ask_min` or longer. Its schedule keeps firing, and the fires
  queue behind the waiting run (2026-10-25: four ticks queued, the fleet idle
  3.5 h). Measured over T3's requests table, 2026-10-18 to 11-01: orchestrator
  threads held a request open past 60 min 21 times, the longest 478 min;
- a scheduled thread whose latest runs failed in a row.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from . import common

STATE_ENV = "FLEET_T3_STATE"

#: table -> the columns read. A table or column missing from T3's schema fails the surface.
COLUMNS = {
    "orchestration_v2_projection_threads": ("thread_id", "project_id", "title", "provider_instance_id",
                                            "updated_at", "archived_at", "deleted_at", "payload_json"),
    "orchestration_v2_projection_runs": ("thread_id", "ordinal", "status", "requested_at", "completed_at"),
    "orchestration_v2_projection_runtime_requests": ("runtime_request_id", "thread_id", "kind", "status",
                                                     "created_at", "resolved_at"),
    "scheduled_tasks": ("task_id", "title", "enabled", "schedule_json", "thread_id", "last_run_status",
                        "next_run_at"),
    "projection_projects": ("project_id", "workspace_root", "deleted_at"),
}

#: Bounds, so a tick's read stays small whatever the database holds. Only the threads a finding or the
#: report's table can name are read: scheduled, waiting on a request, or with a run active or queued. More
#: than MAX_THREADS of them fails the surface (it may be cut), as the session listing's cap does.
MAX_THREADS = 200
MAX_REQUESTS = 200
RUNS_PER_THREAD = 5

#: A request in one of these states is over; any other with no resolved_at is open.
CLOSED_REQUEST_STATES = ("resolved", "cancelled", "expired")

#: Runs in these states hold the thread: a fire of its schedule queues behind them.
ACTIVE_RUN_STATES = ("running", "starting", "preparing", "waiting")

#: Terminal run states that say nothing about whether the loop works: a person or the host stopped the
#: run, or T3 rolled it back. A failing streak skips them; `completed` ends it; `failed` counts.
NEUTRAL_RUN_STATES = ("interrupted", "cancelled", "rolled_back")


class T3Unread(RuntimeError):
    pass


def default_path() -> str:
    return os.environ.get(STATE_ENV) or str(common.home() / ".t3" / "userdata" / "statev2.sqlite")


def _check_schema(c: sqlite3.Connection) -> None:
    for table, cols in COLUMNS.items():
        have = {r[1] for r in c.execute("pragma table_info(%s)" % table)}
        if not have:
            raise T3Unread("T3 state: table %s is missing" % table)
        missing = [col for col in cols if col not in have]
        if missing:
            raise T3Unread("T3 state: %s lacks %s" % (table, ", ".join(missing)))


def _worktree(payload: Any) -> Optional[str]:
    try:
        d = json.loads(payload) if isinstance(payload, str) else None
    except ValueError:
        return None
    v = d.get("worktreePath") if isinstance(d, dict) else None
    return v if isinstance(v, str) and v else None


def read_state(path: str, now: float) -> str:  # noqa: ARG001 (now: the Sources signature; nothing here is aged)
    """The rows this module reads, as JSON text. Raises T3Unread when the
    database can't be opened or its schema lacks a pinned column. No database
    at all is a reading, not a failure: T3 is not installed on this host (the
    fleet also runs where T3 doesn't), so there are no threads to list."""
    if not os.path.exists(path):
        return json.dumps({"installed": False, "threads": [], "projects": {}, "schedules": [], "requests": [],
                           "runs": {}, "queued": {}, "active": {}})
    try:
        c = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)
    except sqlite3.Error as exc:
        raise T3Unread("T3 state: %s" % exc)
    try:
        _check_schema(c)
        schedules = [dict(zip(("task_id", "title", "enabled", "schedule_json", "thread_id", "last_run_status",
                                "next_run_at"), r))
                     for r in c.execute("select task_id, title, enabled, schedule_json, thread_id, last_run_status, "
                                        "next_run_at from scheduled_tasks where enabled = 1 and thread_id is not null")]
        # Only user inputs: a command approval is not a wait this module reports. One over the cap is
        # read, so a cut list fails the surface instead of reading as complete.
        requests = [dict(zip(("request_id", "thread_id", "kind", "status", "created_at"), r))
                    for r in c.execute("select runtime_request_id, thread_id, kind, status, created_at "
                                       "from orchestration_v2_projection_runtime_requests "
                                       "where kind = 'user_input' and resolved_at is null and status not in (%s) "
                                       "order by created_at limit ?" % ",".join("?" * len(CLOSED_REQUEST_STATES)),
                                       CLOSED_REQUEST_STATES + (MAX_REQUESTS + 1,))]
        if len(requests) > MAX_REQUESTS:
            raise T3Unread("T3 state: over %d open user-input requests: the read may be cut, so none is listed"
                           % MAX_REQUESTS)
        busy = [t for (t,) in c.execute("select distinct thread_id from orchestration_v2_projection_runs "
                                        "where status in (%s)" % ",".join("?" * (len(ACTIVE_RUN_STATES) + 1)),
                                        ACTIVE_RUN_STATES + ("queued",))]
        wanted = {s["thread_id"] for s in schedules} | {r["thread_id"] for r in requests} | set(busy)
        if len(wanted) > MAX_THREADS:
            raise T3Unread("T3 state: %d threads are scheduled, waiting or busy, over the cap of %d: the read "
                           "may be cut, so none is listed" % (len(wanted), MAX_THREADS))
        rows = c.execute("select thread_id, project_id, title, provider_instance_id, updated_at, payload_json "
                         "from orchestration_v2_projection_threads where deleted_at is null and archived_at is null "
                         "and thread_id in (%s)" % ",".join("?" * len(wanted)), tuple(sorted(wanted))).fetchall() \
            if wanted else []
        threads = [{"thread_id": t, "project_id": p, "title": ti, "provider": pr, "updated_at": u,
                    "worktree": _worktree(pj)} for t, p, ti, pr, u, pj in rows]
        projects = {p: root for p, root in c.execute(
            "select project_id, workspace_root from projection_projects where deleted_at is null")}
        # The latest terminal runs, read apart from active and queued ones, which would otherwise fill
        # the window and hide a failing streak.
        pending = ACTIVE_RUN_STATES + ("queued",)
        runs: Dict[str, List[Dict[str, Any]]] = {}
        for t in sorted(wanted):
            runs[t] = [dict(zip(("ordinal", "status", "requested_at", "completed_at"), r))
                       for r in c.execute("select ordinal, status, requested_at, completed_at "
                                          "from orchestration_v2_projection_runs where thread_id = ? "
                                          "and status not in (%s) order by ordinal desc limit ?"
                                          % ",".join("?" * len(pending)), (t,) + pending + (RUNS_PER_THREAD,))]
        queued = dict(c.execute("select thread_id, count(*) from orchestration_v2_projection_runs "
                                "where status = 'queued' group by thread_id"))
        active = dict(c.execute("select thread_id, count(*) from orchestration_v2_projection_runs "
                                "where status in (%s) group by thread_id" % ",".join("?" * len(ACTIVE_RUN_STATES)),
                                ACTIVE_RUN_STATES))
    except sqlite3.Error as exc:
        raise T3Unread("T3 state: %s" % exc)
    finally:
        c.close()
    return json.dumps({"installed": True, "threads": threads, "projects": projects, "schedules": schedules,
                       "requests": requests, "runs": runs, "queued": queued, "active": active})


def parse_state(text: str) -> Dict[str, Any]:
    """The JSON read_state wrote (or a fixture's copy), with its shape checked."""
    try:
        d = json.loads(text)
    except ValueError:
        raise T3Unread("T3 state: not JSON")
    if not isinstance(d, dict):
        raise T3Unread("T3 state: not an object")
    for key, typ in (("threads", list), ("projects", dict), ("schedules", list), ("requests", list),
                     ("runs", dict), ("queued", dict), ("active", dict)):
        if not isinstance(d.get(key), typ):
            raise T3Unread("T3 state: %s is not a %s" % (key, typ.__name__))
    return d


def _every_s(schedule_json: Any) -> Optional[float]:
    try:
        d = json.loads(schedule_json) if isinstance(schedule_json, str) else schedule_json
    except ValueError:
        return None
    ms = d.get("everyMs") if isinstance(d, dict) else None
    return ms / 1000.0 if isinstance(ms, (int, float)) and ms > 0 else None


def failing_streak(runs: List[Dict[str, Any]]) -> int:
    """Consecutive `failed` runs among the latest terminal ones, newest first. A neutral one (stopped,
    interrupted, rolled back) neither counts nor breaks it; `completed`, or any state not named, ends it."""
    n = 0
    for r in runs:
        st = r.get("status")
        if st in NEUTRAL_RUN_STATES or st == "queued" or st in ACTIVE_RUN_STATES:
            continue
        if st != "failed":
            break
        n += 1
    return n


def threads(state: Dict[str, Any], now: float) -> List[Dict[str, Any]]:
    """One row per thread worth a line: scheduled, waiting on a request, or with a run active or queued.
    The title is shown through the guard; nothing a thread said is read."""
    sched = {s["thread_id"]: s for s in state["schedules"]}
    waiting: Dict[str, Dict[str, Any]] = {}
    for r in state["requests"]:  # user inputs only: read_state keeps no other kind
        t0 = common.parse_iso(r.get("created_at"))
        if t0 is None:
            continue
        cur = waiting.get(r["thread_id"])
        if cur is None or t0 < cur["since"]:  # the oldest open request is how long the run has waited
            waiting[r["thread_id"]] = {"request_id": r["request_id"], "since": t0}
    out = []
    for t in state["threads"]:
        tid = t["thread_id"]
        runs = state["runs"].get(tid) or []
        active = int(state["active"].get(tid) or 0)
        queued = int(state["queued"].get(tid) or 0)
        if tid not in sched and tid not in waiting and not active and not queued:
            continue
        s = sched.get(tid)
        w = waiting.get(tid)
        out.append({
            "thread_id": tid, "title": common.safe_text(t.get("title"), 80), "provider": t.get("provider"),
            "path": t.get("worktree") or state["projects"].get(t.get("project_id")),
            "project_root": state["projects"].get(t.get("project_id")),
            "schedule": None if s is None else {"title": common.safe_text(s.get("title"), 80),
                                                "every_s": _every_s(s.get("schedule_json")),
                                                "last_run_status": s.get("last_run_status"),
                                                "next_run_at": s.get("next_run_at")},
            "last_runs": [r.get("status") for r in runs],
            "active": active, "queued": queued, "failing_streak": failing_streak(runs),
            "waiting": None if w is None else {"request_id": w["request_id"], "age_s": round(now - w["since"])},
        })
    out.sort(key=lambda r: (r["schedule"] is None, -(r["waiting"] or {}).get("age_s", -1), r["thread_id"]))
    return out


#: A scheduled thread's runs failing this many times in a row is an ask.
FAILS_TO_ASK = 2


def findings(rows: List[Dict[str, Any]], wait_ask_min: int) -> List[Dict[str, Any]]:
    """(kind, row) for each condition an ask is raised on: `wait` and `failing`, scheduled threads only."""
    out = []
    for r in rows:
        if r["schedule"] is None:
            continue
        if r["waiting"] and r["waiting"]["age_s"] >= wait_ask_min * 60:
            out.append({"kind": "wait", "row": r})
        if r["failing_streak"] >= FAILS_TO_ASK:
            out.append({"kind": "failing", "row": r})
    return out
