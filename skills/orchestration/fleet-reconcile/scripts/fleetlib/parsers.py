"""One parser per observed surface. Each takes the raw text a surface gave and
returns normalized, typed records, or raises ParseError.

The Claude Code surfaces (the session listing and the background job file) are
undocumented and change between versions, so their parsers are pinned: the
tests run them against copies captured on PINNED_CC_VERSION (tests/fixtures/),
and the tick reports any other running version as drift. A missing or mistyped
required field fails the whole surface; an unfamiliar enum value is kept and
reported as drift.

What each parser does NOT extract is part of its contract. json.loads reads a
whole file; these fields are dropped before anything is kept:
- a Paseo agent record's persistence.metadata, which holds the Paseo MCP
  bearer (spec §2a: 323 of 325 records);
- a job file's providerEnv, output and the values of respawnFlags (an inline
  --settings JSON can carry env);
- a schedule's prompt and its runs' output;
- the bookkeeping run log's source_files (they can name crm/ paths).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import ctx

from . import common

PINNED_CC_VERSION = "2.1.280"

LISTING_KINDS = ("interactive", "background")
LISTING_STATES = ("working", "done", "blocked", "failed", "stopped")
LISTING_STATUSES = ("idle", "busy", "waiting")
#: waitingFor values seen on 2.1.280 (evidence files and captures). Class 3
#: versus class 7 reads this field, so an unfamiliar value is drift.
WAITING_FOR = ("permission prompt", "dialog open", "input needed")
JOB_STATES = LISTING_STATES


class ParseError(ValueError):
    pass


def _json(text: Any, what: str) -> Any:
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    if not isinstance(text, str):
        raise ParseError("%s: no text" % what)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ParseError("%s: not JSON (%s)" % (what, exc))


def _req(d: Dict[str, Any], key: str, typ: Any, what: str) -> Any:
    v = d.get(key)
    if not isinstance(v, typ) or isinstance(v, bool):
        raise ParseError("%s: %s missing or not %s" % (what, key, getattr(typ, "__name__", typ)))
    return v


def cc_version(text: str) -> Optional[str]:
    """`claude --version` prints e.g. `2.1.280 (Claude Code)`."""
    m = re.match(r"\s*(\d+\.\d+\.\d+)\b", text or "")
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# claude agents --json --all

def parse_listing(text: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Rows of the session listing, and drift notes.

    Measured on 2.1.280: every row has sessionId, kind, cwd, name, startedAt
    (epoch ms). Background rows have id (the first 8 hex of the session id) and
    state; a row with a live process has pid and status, and waitingFor when
    status is waiting. Interactive rows carry no state.
    """
    data = _json(text, "listing")
    if not isinstance(data, list):
        raise ParseError("listing: not a JSON array")
    rows, drift = [], []
    for i, r in enumerate(data):
        what = "listing row %d" % i
        if not isinstance(r, dict):
            raise ParseError("%s: not an object" % what)
        sid = _req(r, "sessionId", str, what)
        if not ctx.SESSION_ID_RE.match(sid):
            raise ParseError("%s: sessionId has an unexpected shape" % what)
        kind = _req(r, "kind", str, what)
        started = _req(r, "startedAt", int, what)
        row = {
            "session_id": sid,
            "kind": kind,
            "cwd": _req(r, "cwd", str, what),
            "name": _req(r, "name", str, what),
            "started_at": started / 1000.0,
            "bg_id": r.get("id") if isinstance(r.get("id"), str) else None,
            "state": r.get("state") if isinstance(r.get("state"), str) else None,
            "pid": r.get("pid") if type(r.get("pid")) is int else None,
            "status": r.get("status") if isinstance(r.get("status"), str) else None,
            "waiting_for": r.get("waitingFor") if isinstance(r.get("waitingFor"), str) else None,
        }
        if kind not in LISTING_KINDS:
            drift.append("listing: kind %r" % kind)
        if row["state"] is not None and row["state"] not in LISTING_STATES:
            drift.append("listing: state %r" % row["state"])
        if row["waiting_for"] is not None and row["waiting_for"] not in WAITING_FOR:
            drift.append("listing: waitingFor %r" % row["waiting_for"])
        if row["status"] is not None and row["status"] not in LISTING_STATUSES:
            drift.append("listing: status %r" % row["status"])
        extra = set(r) - {"sessionId", "kind", "cwd", "name", "startedAt", "id", "state", "pid", "status",
                          "waitingFor"}
        if extra:
            drift.append("listing: new field(s) %s" % ", ".join(sorted(extra)))
        rows.append(row)
    return rows, sorted(set(drift))


# --------------------------------------------------------------------------
# ~/.claude/jobs/<id>/state.json

#: The usage-limit text Claude Code writes into a background job's detail and
#: needs: "You've hit your session limit · resets 10am (America/Bogota)". A
#: limit that resets on another day names the date: "resets Oct 3, 10am (…)".
LIMIT_RE = re.compile(r"hit your (?:[a-z0-9-]+ )?limit", re.IGNORECASE)
RESET_RE = re.compile(r"resets\s+(?:([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2}),?\s+(?:at\s+)?)?"
                      r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*\(([A-Za-z_]+(?:/[A-Za-z_+-]+)*)\)",
                      re.IGNORECASE)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def parse_job_state(text: Any, job_id: str) -> Dict[str, Any]:
    what = "job %s" % job_id
    d = _json(text, what)
    if not isinstance(d, dict):
        raise ParseError("%s: not an object" % what)
    state = _req(d, "state", str, what)
    sid = _req(d, "sessionId", str, what)
    flags = d.get("respawnFlags") if isinstance(d.get("respawnFlags"), list) else []
    settings_path = None
    for i, f in enumerate(flags[:-1]):
        if f == "--settings" and isinstance(flags[i + 1], str) and flags[i + 1].startswith("/"):
            settings_path = common.safe_path(flags[i + 1])  # a path, never inline JSON
    detail = d.get("detail") if isinstance(d.get("detail"), str) else ""
    needs = d.get("needs") if isinstance(d.get("needs"), str) else ""
    return {
        "job_id": job_id,
        "session_id": sid,
        "state": state,
        "state_known": state in JOB_STATES,
        "detail": detail,
        "needs": needs,
        "suggested_reply": bool(d.get("suggestedReply")),
        "limit_text": bool(LIMIT_RE.search(detail) or LIMIT_RE.search(needs)),
        "reset_text": _reset_text(detail) or _reset_text(needs),
        "worktree_path": d.get("worktreePath") if isinstance(d.get("worktreePath"), str) else None,
        "worktree_branch": d.get("worktreeBranch") if isinstance(d.get("worktreeBranch"), str) else None,
        "name": d.get("name") if isinstance(d.get("name"), str) else None,
        "cli_version": d.get("cliVersion") if isinstance(d.get("cliVersion"), str) else None,
        "updated_at": _epoch(d.get("updatedAt")),
        "settings_path": settings_path,
    }


def _epoch(v: Any) -> Optional[float]:
    """A job file's time: an ISO string on 2.1.280 (every captured file), or
    epoch milliseconds."""
    if type(v) is int:
        return v / 1000.0
    return common.parse_iso(v)


def _reset_text(s: str) -> Optional[str]:
    m = RESET_RE.search(s or "")
    return m.group(0) if m else None


def reset_epoch(reset_text: Optional[str], after: float) -> Optional[float]:
    """When the limit resets: for "resets 9:50am (America/Bogota)" the first
    such moment at or after `after`; for "resets Oct 3, 10am (…)" that date,
    in the year that puts it nearest after `after`. None when unreadable."""
    m = RESET_RE.search(reset_text or "")
    if not m:
        return None
    try:
        from zoneinfo import ZoneInfo
        import datetime as dt

        tz = ZoneInfo(m.group(6))
    except Exception:
        return None
    hour = int(m.group(3)) % 12 + (12 if m.group(5).lower() == "pm" else 0)
    minute = int(m.group(4) or 0)
    base = dt.datetime.fromtimestamp(after, tz)
    if m.group(1):
        mon = m.group(1).lower()
        if mon not in _MONTHS:
            return None
        try:
            cand = base.replace(month=_MONTHS.index(mon) + 1, day=int(m.group(2)), hour=hour, minute=minute,
                                second=0, microsecond=0)
        except ValueError:
            return None
        if cand.timestamp() < after - 180 * 86400:
            cand = cand.replace(year=cand.year + 1)
        return cand.timestamp()
    cand = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if cand.timestamp() < after:
        cand = cand + dt.timedelta(days=1)
    return cand.timestamp()


# --------------------------------------------------------------------------
# ~/.paseo/agents/<project>/<id>.json (read-only; the bearer's field is never extracted)

#: Label keys whose values are ids or short tags, safe to keep.
PASEO_LABEL_VALUES = ("coordinator", "source", "fleet", "paseo.schedule-id", "paseo.parent-agent-id", "probe")


def parse_paseo_record(text: Any, where: str = "record") -> Dict[str, Any]:
    d = _json(text, where)
    if not isinstance(d, dict):
        raise ParseError("%s: not an object" % where)
    agent_id = _req(d, "id", str, where)
    labels = d.get("labels") if isinstance(d.get("labels"), dict) else {}
    runtime = d.get("runtimeInfo") if isinstance(d.get("runtimeInfo"), dict) else {}
    persistence = d.get("persistence") if isinstance(d.get("persistence"), dict) else {}
    sid, sid_from = None, None
    for src, holder in (("runtimeInfo", runtime), ("persistence", persistence)):
        v = holder.get("sessionId")
        if isinstance(v, str) and ctx.SESSION_ID_RE.match(v):
            sid, sid_from = v, src
            break
    return {
        "agent_id": agent_id,
        "provider": d.get("provider") if isinstance(d.get("provider"), str) else None,
        "cwd": d.get("cwd") if isinstance(d.get("cwd"), str) else None,
        "workspace_id": d.get("workspaceId") if isinstance(d.get("workspaceId"), str) else None,
        "title": common.safe_text(d.get("title"), 60),
        "labels": {k: (common.safe_text(v, 40) if k in PASEO_LABEL_VALUES else "")
                   for k, v in labels.items() if isinstance(k, str) and common.safe_text(k, 80) == k},
        "last_status": d.get("lastStatus") if isinstance(d.get("lastStatus"), str) else None,
        "archived": bool(d.get("archivedAt")),
        "updated_at": common.parse_iso(d.get("updatedAt")),
        "last_activity_at": common.parse_iso(d.get("lastActivityAt")),
        "requires_attention": bool(d.get("requiresAttention")),
        "session_id": sid,
        "session_id_from": sid_from,
        "has_error": bool(d.get("lastError")),
    }


# --------------------------------------------------------------------------
# ~/.paseo/schedules/<id>.json

def parse_schedule(text: Any, where: str = "schedule") -> Dict[str, Any]:
    d = _json(text, where)
    if not isinstance(d, dict):
        raise ParseError("%s: not an object" % where)
    cadence = d.get("cadence") if isinstance(d.get("cadence"), dict) else {}
    target = d.get("target") if isinstance(d.get("target"), dict) else {}
    tcfg = target.get("config") if isinstance(target.get("config"), dict) else {}
    runs = [r for r in d.get("runs") or [] if isinstance(r, dict)]
    last = runs[-1] if runs else None
    return {
        "id": _req(d, "id", str, where),
        "name": common.safe_text(d.get("name"), 72),
        "cadence": {k: cadence.get(k) for k in ("type", "expression", "timezone") if isinstance(cadence.get(k), str)},
        "status": d.get("status") if isinstance(d.get("status"), str) else None,
        "cwd": tcfg.get("cwd") if isinstance(tcfg.get("cwd"), str) else None,
        "next_run": common.parse_iso(d.get("nextRunAt")),
        "last_run": common.parse_iso(d.get("lastRunAt")),
        "paused_at": common.parse_iso(d.get("pausedAt")),
        "expires_at": common.parse_iso(d.get("expiresAt")),
        "max_runs": d.get("maxRuns") if type(d.get("maxRuns")) is int else None,
        "runs": len(runs),
        "last_run_status": last.get("status") if last and isinstance(last.get("status"), str) else None,
        "last_run_ended": common.parse_iso(last.get("endedAt")) if last else None,
        "failed_runs": sum(1 for r in runs if r.get("status") == "failed"),
    }


# --------------------------------------------------------------------------
# GitHub

_SLUG = re.compile(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                   r"([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


def parse_remote_slug(url: Any) -> Optional[str]:
    """owner/name from a GitHub origin URL, or None (the repo's observation
    then fails; it never reads as zero PRs)."""
    m = _SLUG.match((url or "").strip()) if isinstance(url, str) else None
    return "%s/%s" % (m.group(1), m.group(2)) if m else None


def parse_rules(text: Any, what: str = "rules") -> List[Dict[str, Any]]:
    """GET repos/<r>/rules/branches/<b>: the effective rules on the branch."""
    d = _json(text, what)
    if not isinstance(d, list) or not all(isinstance(r, dict) and isinstance(r.get("type"), str) for r in d):
        raise ParseError("%s: want a JSON array of rules" % what)
    return [{"type": r["type"], "parameters": r.get("parameters") if isinstance(r.get("parameters"), dict) else {}}
            for r in d]


def evaluate_rules(rules: List[Dict[str, Any]], actions_app_id: int) -> Dict[str, Any]:
    """Whether the branch's rules bound a driver's merge (spec §5.1, §5.5): a
    pull_request rule, and required checks each pinned to GitHub Actions."""
    types = {r["type"] for r in rules}
    checks: List[Dict[str, Any]] = []
    for r in rules:
        if r["type"] == "required_status_checks":
            for c in r["parameters"].get("required_status_checks") or []:
                if isinstance(c, dict) and isinstance(c.get("context"), str):
                    checks.append({"context": c["context"],
                                   "integration_id": c.get("integration_id") if type(c.get("integration_id")) is int
                                   else None})
    unpinned = [c["context"] for c in checks if c["integration_id"] != actions_app_id]
    approvals = None
    for r in rules:
        if r["type"] == "pull_request":
            v = r["parameters"].get("required_approving_review_count")
            approvals = v if type(v) is int else approvals
    flags = []
    if "pull_request" not in types:
        flags.append("no pull_request rule")
    if not checks:
        flags.append("no required status checks")
    if unpinned:
        flags.append("required check(s) not pinned to app %d: %s" % (actions_app_id, ", ".join(sorted(unpinned))))
    if "non_fast_forward" not in types:
        flags.append("force-push to the default branch not blocked")
    return {
        "types": sorted(types),
        "pull_request": "pull_request" in types,
        "approvals": approvals,
        "checks": checks,
        "unpinned": sorted(unpinned),
        "driver_eligible": "pull_request" in types and bool(checks) and not unpinned,
        "flags": flags,
    }


PR_FIELDS = "number,title,headRefName,baseRefName,isDraft,author,labels,url,updatedAt,mergeStateStatus"


def parse_pr_list(text: Any, what: str = "prs") -> List[Dict[str, Any]]:
    d = _json(text, what)
    if not isinstance(d, list):
        raise ParseError("%s: want a JSON array" % what)
    out = []
    for i, p in enumerate(d):
        w = "%s[%d]" % (what, i)
        if not isinstance(p, dict):
            raise ParseError("%s: not an object" % w)
        author = p.get("author") if isinstance(p.get("author"), dict) else {}
        login = author.get("login") if isinstance(author.get("login"), str) else ""
        out.append({
            "number": _req(p, "number", int, w),
            "title": common.safe_text(p.get("title"), 72),
            "head": _req(p, "headRefName", str, w),
            "base": p.get("baseRefName") if isinstance(p.get("baseRefName"), str) else None,
            "draft": bool(p.get("isDraft")),
            "author": common.safe_text(login, 40),
            "bot": bool(author.get("is_bot")) or login.startswith("app/") or login.endswith("[bot]"),
            "dependabot": "dependabot" in login.lower(),
            "labels": [common.safe_text(lb.get("name"), 40) for lb in p.get("labels") or []
                       if isinstance(lb, dict) and isinstance(lb.get("name"), str)],
            "updated_at": common.parse_iso(p.get("updatedAt")),
            "merge_state": p.get("mergeStateStatus") if isinstance(p.get("mergeStateStatus"), str) else None,
        })
    return out


# --------------------------------------------------------------------------
# launchd

def parse_launchctl_print(text: str) -> Dict[str, Any]:
    """The few top-level lines of `launchctl print gui/<uid>/<label>` the
    inventory uses. Not a documented format; tested against a capture."""
    out: Dict[str, Any] = {"loaded": True, "running": None, "runs": None, "last_exit": None, "pid": None}
    for line in (text or "").splitlines():
        if line.startswith("\t") and not line.startswith("\t\t"):
            key, _, value = line.strip().partition(" = ")
            if key == "state":
                out["running"] = value.strip() == "running"
            elif key == "runs" and value.strip().isdigit():
                out["runs"] = int(value.strip())
            elif key == "last exit code":
                v = value.strip()
                m = re.match(r"(-?\d+)\b", v)  # "0", or "78: EX_CONFIG"
                out["last_exit"] = int(m.group(1)) if m else v
            elif key == "pid" and value.strip().isdigit():
                out["pid"] = int(value.strip())
    return out
