"""One tick's observation (spec §5.3 "Observe"): the session listing, the
background job files, Paseo's records, the core's board, transcript times,
GitHub for the scope's repos, and the scheduled-work inventory, joined per
session. Deterministic code only; no model reads anything here.

Every surface records whether it was read. A surface that failed is reported,
never read as empty: a listing at or over the cap is treated as possibly
truncated and fails closed (the 6-vs-30 error of the 09-26 run came from a
list cut at its limit), and a repo whose slug or PR list can't be read has no
PR count at all, not zero.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import ctx

from . import common, config, ledger, parsers, scheduled
from .sources import SourceError, Sources


def _surface(ok: bool, **kw: Any) -> Dict[str, Any]:
    out = {"ok": ok}
    out.update(kw)
    return out


def _err(exc: Exception) -> str:
    return common.safe_text(str(exc), 200)


def fleet_shaped(name: str, scope_id: str) -> bool:
    """<scope>-<repo>-pr<N> (a driver) or <scope>-jan-<hash> (a janitor), §5.3."""
    return bool(re.fullmatch(r"%s-(?:[A-Za-z0-9._-]+-pr\d+|jan-[0-9a-f]{6,64})" % re.escape(scope_id), name or ""))


def place(cwd: Optional[str], board_row: Optional[Dict[str, Any]], job: Optional[Dict[str, Any]],
          by_repo: Dict[str, Optional[str]]) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """(scope id, repo common dir, branch, how it was placed) by the core's
    rule (§5.1 of the core: the realpath of the git common dir). A cwd that no
    longer exists (a worktree removed after merge) falls back to the board
    row's repo, then to the repo holding a .claude/worktrees/ path."""
    w = ctx.locate(cwd, timeout=2.0) if cwd else None
    if w is not None:
        return by_repo.get(w.common_dir), w.common_dir, w.branch, "cwd"
    if cwd and os.path.isdir(cwd):
        return None, None, None, "no-repo"  # it exists and is in no repo: no hook placed it either
    if board_row and board_row.get("repo"):
        return by_repo.get(board_row["repo"]), board_row["repo"], board_row.get("branch"), "board"
    for p in (cwd, (job or {}).get("worktree_path")):
        i = (p or "").find("/.claude/worktrees/")
        if i > 0:
            w = ctx.locate(p[:i], timeout=2.0)
            if w is not None:
                return by_repo.get(w.common_dir), w.common_dir, (job or {}).get("worktree_branch"), "worktree-parent"
    return None, None, None, "unplaced"


def _board_rows(scope_ids: List[str]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Every scope's board, rebuilt in memory from its log (read-only: no
    cache write). {session id: row + its scope}."""
    rows: Dict[str, Dict[str, Any]] = {}
    status: Dict[str, Any] = {}
    for sid in scope_ids:
        sc = ctx.Scope(id=sid, store=ctx.state_root() / sid, where=None)
        try:
            board = ctx.rebuild(sid, ctx.read_log(sc))
        except OSError as exc:
            status[sid] = _surface(False, error=_err(exc))
            continue
        status[sid] = _surface(True, rows=len(board["sessions"]), events=board["events"],
                               skipped_lines=board["skipped_lines"])
        for r in board["sessions"].values():
            rows[r["session_id"]] = dict(r, scope=sid)
    return rows, status


def _board_view(r: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not r:
        return None
    t = lambda k: ctx.parse_ts(r[k]) if isinstance(r.get(k), str) else None  # noqa: E731
    return {"scope": r.get("scope"), "state": r.get("state"), "last_event": r.get("last_event"),
            "last_ts": t("last_ts"), "died_ts": t("died_ts"), "died_error": r.get("died_error"),
            "arc_status": r.get("arc_status"), "arc_ts": t("arc_ts"), "repo": r.get("repo"),
            "branch": r.get("branch")}


def _job_view(j: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not j:
        return None
    return {"job_id": j["job_id"], "state": j["state"], "detail": common.safe_text(j["detail"], 100),
            "needs": common.safe_text(j["needs"], 100), "suggested_reply": j["suggested_reply"],
            "limit_text": j["limit_text"], "reset_text": j["reset_text"],
            "worktree_path": common.safe_path(j["worktree_path"]),
            "worktree_branch": common.safe_text(j["worktree_branch"], 120) or None, "updated_at": j["updated_at"],
            "settings_path": j["settings_path"]}


def observe(sec: Dict[str, Any], src: Sources, tick: int, now: Optional[float] = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    scope_id = sec["scope"]
    snap: Dict[str, Any] = {"v": common.SCHEMA_VERSION, "scope": scope_id, "tick": tick, "ts": common.ts(now),
                            "now": now, "pinned_cc_version": parsers.PINNED_CC_VERSION, "surfaces": {},
                            "drift": []}
    surf = snap["surfaces"]

    scopes = ctx.load_scopes()
    by_repo = scopes.by_repo
    scope_ids = sorted({s for s in by_repo.values() if s})
    snap["scope_repos"] = sorted(r for r, s in by_repo.items() if s == scope_id)

    # Claude Code version --------------------------------------------------
    try:
        v = parsers.cc_version(src.claude_version())
        snap["cc_version"] = v
        surf["claude_version"] = _surface(v is not None, version=v)
        if v and v != parsers.PINNED_CC_VERSION:
            snap["drift"].append("Claude Code %s is running; the parsers were captured on %s"
                                 % (v, parsers.PINNED_CC_VERSION))
    except SourceError as exc:
        snap["cc_version"] = None
        surf["claude_version"] = _surface(False, error=_err(exc))

    # Background job files ---------------------------------------------------
    # A file that doesn't parse (one read mid-write, say) degrades only its
    # own session (job_unread), not every background session.
    jobs: Dict[str, Dict[str, Any]] = {}
    job_ids: List[str] = []
    bad_jobs: List[str] = []
    try:
        for job_id, text in src.job_states():
            job_ids.append(job_id)
            try:
                j = parsers.parse_job_state(text, job_id)
            except parsers.ParseError:
                bad_jobs.append(job_id)
                continue
            jobs[j["session_id"]] = j
            if not j["state_known"]:
                snap["drift"].append("job file: state %r" % j["state"])
        surf["jobs"] = _surface(True, files=len(job_ids), unparsed=len(bad_jobs))
    except (SourceError, OSError) as exc:
        surf["jobs"] = _surface(False, error=_err(exc))

    # The session listing ---------------------------------------------------
    # `claude agents --json --all` has no limit parameter, but it lists every
    # background job ever run, so it can legitimately pass the cap. At or over
    # the cap the listing counts as complete only when every job file on disk
    # appears in it (a second reading); otherwise it may be truncated and
    # nothing is classified (the 09-26 run's 6-vs-30 error came from a list cut
    # at its limit).
    rows: List[Dict[str, Any]] = []
    try:
        rows, drift = parsers.parse_listing(src.agents_listing())
        snap["drift"].extend(drift)
        listed = {r["session_id"][:8] for r in rows}
        at_cap = len(rows) >= sec["listing_cap"]
        proven = at_cap and surf["jobs"]["ok"] and bool(job_ids) and set(job_ids) <= listed
        if at_cap and not proven:
            surf["listing"] = _surface(False, rows=len(rows), failed_closed=True,
                                       error="%d rows, at or over the cap of %d, and the job files don't show it "
                                             "complete: it may be truncated, so nothing is classified"
                                             % (len(rows), sec["listing_cap"]))
            rows = []
        else:
            surf["listing"] = _surface(True, rows=len(rows), **({"completeness": "every job file is listed"}
                                                               if at_cap else {}))
    except (SourceError, parsers.ParseError) as exc:
        surf["listing"] = _surface(False, error=_err(exc))

    # Transcripts -----------------------------------------------------------
    try:
        transcripts = src.transcript_index()
        surf["transcripts"] = _surface(True, sessions=len(transcripts))
    except SourceError as exc:
        transcripts = {}
        surf["transcripts"] = _surface(False, error=_err(exc))

    # Paseo records (read-only; the bearer's field is never extracted) ------
    paseo: Dict[str, Dict[str, Any]] = {}
    records: List[Dict[str, Any]] = []
    bad_records = 0
    try:
        for where, text in src.paseo_records():
            try:
                rec = parsers.parse_paseo_record(text, where)
            except parsers.ParseError:
                bad_records += 1
                continue
            records.append(rec)
            sid = rec["session_id"]
            if sid and (sid not in paseo or (paseo[sid]["archived"] and not rec["archived"])
                        or (paseo[sid]["archived"] == rec["archived"]
                            and (rec["updated_at"] or 0) > (paseo[sid]["updated_at"] or 0))):
                paseo[sid] = rec
        surf["paseo_records"] = _surface(True, records=len(records), unparsed=bad_records,
                                         not_archived=sum(1 for r in records if not r["archived"]))
    except (SourceError, OSError) as exc:
        surf["paseo_records"] = _surface(False, error=_err(exc))

    # How gh authenticated this tick (tick.sh says; never the token itself) --
    surf["gh_auth"] = _surface(True, mode=common.safe_text(os.environ.get("FLEET_GH_AUTH") or "keyring", 80))

    # The core's board (every scope, for placement) --------------------------
    board, surf["board"] = _board_rows(scope_ids)

    # The fleet's own sessions: the ledger's spawns and the adopted list -----
    recs, corrupt = ledger.read(config.state_dir(sec))
    surf["ledger"] = _surface(corrupt == 0, records=len(recs), corrupt=corrupt)
    spawned = ledger.spawned(recs)
    fleet_ids = {sid: key for key, ids in spawned.items() for sid in ids}
    adopted = set(config.adopted_ids(sec))

    # Sessions ----------------------------------------------------------------
    sessions = []
    for r in rows:
        sid = r["session_id"]
        job = jobs.get(sid)
        brow = board.get(sid)
        scope, repo, branch, how = place(r["cwd"], brow, job, by_repo)
        tr = transcripts.get(sid) or {}
        name_ok = common.safe_text(r["name"], 80)
        key = None
        if sid in adopted:
            key = "adopt:%s" % sid
        elif sid in fleet_ids and fleet_ids[sid] == r["name"]:
            key = r["name"]
        p = paseo.get(sid)
        limit_line = None
        if brow and brow.get("state") == "died" and brow.get("died_error") == "rate_limit" and not (
                job and job.get("reset_text")):
            limit_line = common.safe_text(src.limit_text(sid, tr), 100) or None
        sessions.append({
            "session_id": sid, "name": name_ok, "kind": r["kind"],
            "cwd": common.safe_path(r["cwd"]) or common.WITHHELD, "cwd_exists": how in ("cwd", "no-repo"),
            "bg_id": r["bg_id"], "state": r["state"], "pid": r["pid"], "status": r["status"],
            "waiting_for": r["waiting_for"], "started_at": r["started_at"],
            "job": _job_view(job), "board": _board_view(brow),
            "paseo": None if p is None else {k: p[k] for k in ("agent_id", "archived", "labels", "last_status",
                                                                "updated_at", "last_activity_at", "workspace_id",
                                                                "session_id_from")},
            "transcript": {"found": "mtime" in tr, "mtime": tr.get("mtime"), "sub": tr.get("sub")},
            "limit_text": limit_line,
            "scope": scope, "repo": repo, "branch": common.safe_text(branch, 120) or None, "placement": how,
            "fleet_key": key, "adopted": sid in adopted,
            "job_unread": r["kind"] == "background" and sid[:8] in bad_jobs,
            "fleet_shaped": fleet_shaped(r["name"], scope_id),
        })
    snap["sessions"] = sessions

    # Paseo records for the count check (not archived only) ------------------
    snap["paseo_open"] = []
    for rec in records:
        if rec["archived"]:
            continue
        scope, _, _, how = place(rec["cwd"], board.get(rec["session_id"] or ""), None, by_repo)
        snap["paseo_open"].append({"agent_id": rec["agent_id"], "session_id": rec["session_id"],
                                   "session_id_from": rec["session_id_from"], "title": rec["title"],
                                   "last_status": rec["last_status"], "scope": scope, "placement": how,
                                   "cwd": common.safe_path(rec["cwd"]) or common.WITHHELD,
                                   "labels": rec["labels"]})

    # GitHub ------------------------------------------------------------------
    snap["repos"] = [observe_repo(cd, sec, src) for cd in snap["scope_repos"]]

    # Claims: published by the core's phase 2; none yet ------------------------
    snap["claims"] = {"published": False, "by_session": {}}

    # Scheduled work (report-only seam) -----------------------------------------
    snap["scheduled"] = scheduled.inventory(sec, src, by_repo, now)
    snap["drift"] = sorted(set(snap["drift"]))
    return snap


def observe_repo(common_dir: str, sec: Dict[str, Any], src: Sources) -> Dict[str, Any]:
    """One repo's slug, effective rules and open PRs. Any failure fails the
    repo's observation, with the reason; it never reads as zero PRs."""
    out: Dict[str, Any] = {"repo": common_dir, "ok": False, "slug": None, "error": None}
    try:
        url = src.origin_url(common_dir)
    except SourceError as exc:
        out["error"] = "origin remote: %s" % _err(exc)
        return out
    slug = parsers.parse_remote_slug(url)
    if slug is None:
        out["error"] = "origin remote is not a GitHub slug"
        return out
    out["slug"] = slug
    try:
        branch = src.default_branch(slug)
        if not branch:
            raise SourceError("empty default branch")
        out["default_branch"] = branch
        out["rules"] = parsers.evaluate_rules(parsers.parse_rules(src.rules(slug, branch), slug),
                                              sec["actions_app_id"])
        prs = parsers.parse_pr_list(src.open_prs(slug, sec["pr_list_cap"]), slug)
    except (SourceError, parsers.ParseError) as exc:
        out["error"] = _err(exc)
        return out
    if len(prs) >= sec["pr_list_cap"]:
        out["error"] = "%d open PRs, at or over the cap of %d: the list may be truncated" % (
            len(prs), sec["pr_list_cap"])
        return out
    out["ok"] = True
    out["prs"] = prs
    return out
