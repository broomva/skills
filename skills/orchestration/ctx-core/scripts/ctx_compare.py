"""ctx doctor --compare: the core's phase-1 exit comparison (core spec §9).

Board rows that are live, against in-scope sessions from `claude agents --json
--all` whose top-level transcript was modified in the same window. At least 95%
of each set must appear in the other, and every difference is listed with its
reason. Read-only on the store: the board is rebuilt in memory, and none of
events.jsonl, events.lock, board.json or board-snapshot.json is written. The
one write is a summary line appended to <store>/compare.jsonl, so the three
days of the criterion stay on disk.

Matching is on the full session id, never on counts: a compaction and a resume
each publish a session.start, so start counts overstate sessions.

Reasons, a fixed list (a new one is a code change with a test). The first four
describe what the comparator can see, not the hooks, and are left out of the
95%; the rest count against it because in them the board is wrong or the gap
is unexplained:

    no-transcript        board row; its session id has no transcript anywhere
                         (a session started from another session's Bash saves
                         none, while its hooks still fire)
    ended                board row; a transcript exists, but claude agents no
                         longer lists the session
    pre-registration     listed session with no transcript entry after the
                         hooks were registered
    died                 the row's latest event is session.died and nothing
                         came after it: the board is right, and the transcript
                         counted on the session side is the death itself
    died-then-continued  the row's latest event is session.died, but the
                         session is listed with a transcript entry more than
                         GRACE_S after it
    no-event             no event at all for a listed session
    stale-event          a listed session active in the window whose latest
                         event is older than the window (a long turn: until
                         phase 2 the board hears only at SessionStart, Stop and
                         StopFailure)
    unexplained          any other board-only row

Three of these (died, stale-event, unexplained) are this build's additions to
the spec's five, pending the spec (broomva/workspace#842).

No evidence is not a pass: an unreadable transcript directory or an empty
listing is an error, and a side with nothing left to count after the
exclusions reads as NO EVIDENCE, which fails.

Placed in `ctx_compare.py` rather than inside ctx.py (where the spec puts it)
so ctx.py's diff stays to the doctor dispatch; it uses ctx.py's own readers.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ctx

EXCLUDED = ("no-transcript", "ended", "pre-registration", "died")
COUNTED = ("died-then-continued", "no-event", "stale-event", "unexplained")
REASONS = EXCLUDED + COUNTED
THRESHOLD = 0.95
#: Transcript writes this soon after a death belong to it (as in fleet-reconcile).
GRACE_S = 120


def load_listing(path: Optional[str] = None, timeout: float = 30.0) -> List[Dict[str, Any]]:
    """The session listing, from `claude agents --json --all` or a captured
    file. Raises RuntimeError when it can't be read."""
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        claude = os.environ.get("CTX_CLAUDE_BIN") or "claude"
        try:
            proc = subprocess.run([claude, "agents", "--json", "--all"], stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("claude agents: %s" % exc)
        if proc.returncode != 0:
            raise RuntimeError("claude agents exited %d" % proc.returncode)
        text = proc.stdout.decode("utf-8", "replace")
    rows = json.loads(text)
    if not isinstance(rows, list):
        raise RuntimeError("claude agents: not a JSON array")
    rows = [r for r in rows if isinstance(r, dict) and isinstance(r.get("sessionId"), str)]
    if not rows:
        raise RuntimeError("claude agents listed no session (it lists at least the one asking)")
    return rows


def transcript_times() -> Dict[str, float]:
    """{session id: mtime of its top-level transcript}, across every project.
    Raises RuntimeError when the projects directory can't be read: that is no
    evidence, not an empty set."""
    out: Dict[str, float] = {}
    root = ctx._claude_projects_dir()
    try:
        pdirs = [p for p in root.iterdir() if p.is_dir()]
    except OSError as exc:
        raise RuntimeError("%s: %s" % (root, exc.strerror or exc))
    for pdir in pdirs:
        try:
            entries = list(os.scandir(pdir))
        except OSError:
            continue
        for e in entries:
            if e.name.endswith(".jsonl"):
                try:
                    mt = e.stat().st_mtime
                except OSError:
                    continue
                sid = e.name[:-6]
                out[sid] = max(out.get(sid, 0.0), mt)
    return out


def _live(row: Dict[str, Any], cut: str) -> bool:
    """ctx.is_live with the window as a parameter: the latest event is within
    the window and is not session.died."""
    return row.get("state") != "died" and str(row.get("last_ts") or "") >= cut


def compare(scope_id: str, listing: List[Dict[str, Any]], transcripts: Dict[str, float], now: float,
            hours: float = 6.0, registered: Optional[float] = None) -> Dict[str, Any]:
    scopes = ctx.load_scopes()
    repos = {r for r, s in scopes.by_repo.items() if s == scope_id}
    sc = ctx.Scope(id=scope_id, store=ctx.state_root() / scope_id, where=None)
    board = ctx.rebuild(scope_id, ctx.read_log(sc))
    rows = board["sessions"]
    if registered is None:
        firsts = [ctx.parse_ts(r["first_ts"]) for r in rows.values() if r.get("first_ts")]
        registered = min(firsts) if firsts else now
    window = now - hours * 3600
    cut = ctx.now_ts(window)

    board_live = {sid for sid, r in rows.items() if _live(r, cut)}
    listed = {r["sessionId"]: r for r in listing}
    session_side, unplaced = set(), 0
    for sid, r in listed.items():
        mt = transcripts.get(sid)
        if mt is None or mt < window:
            continue
        cwd = r.get("cwd") if isinstance(r.get("cwd"), str) else ""
        exists = bool(cwd) and os.path.isdir(cwd)
        where = ctx.locate(cwd, timeout=2.0) if exists else None
        if where is not None:
            repo = where.common_dir
        elif not exists and sid in rows:  # a worktree removed after merge: its row says where it was
            repo = rows[sid].get("repo")
        else:
            unplaced += 1
            continue
        if repo in repos:
            session_side.add(sid)

    both = board_live & session_side
    diffs: List[Dict[str, str]] = []
    for sid in sorted(board_live - session_side):
        if sid not in transcripts:
            reason = "no-transcript"
        elif sid not in listed:
            reason = "ended"
        else:
            reason = "unexplained"
        diffs.append({"session_id": sid, "side": "board", "reason": reason})
    for sid in sorted(session_side - board_live):
        row = rows.get(sid)
        if row is None:
            reason = "pre-registration" if transcripts[sid] < registered else "no-event"
        elif row.get("state") == "died":
            died = ctx.parse_ts(row["died_ts"]) if row.get("died_ts") else None
            reason = "died-then-continued" if died is not None and transcripts[sid] > died + GRACE_S else "died"
        else:
            reason = "stale-event"
        diffs.append({"session_id": sid, "side": "sessions", "reason": reason})

    def frac(side: str, total: int) -> Tuple[Optional[float], Optional[float]]:
        """(raw, adjusted); None where there is nothing to count."""
        excl = sum(1 for d in diffs if d["side"] == side and d["reason"] in EXCLUDED)
        raw = len(both) / total if total else None
        adj = len(both) / (total - excl) if total - excl > 0 else None
        return raw, adj

    b_raw, b_adj = frac("board", len(board_live))
    s_raw, s_adj = frac("sessions", len(session_side))
    evidence = b_adj is not None and s_adj is not None
    counts = {r: sum(1 for d in diffs if d["reason"] == r) for r in REASONS}
    return {
        "v": 1, "ts": ctx.now_ts(now), "scope": scope_id, "hours": hours,
        "registered": ctx.now_ts(registered), "board_live": len(board_live), "sessions": len(session_side),
        "both": len(both), "board_pct": _r(b_adj), "session_pct": _r(s_adj),
        "board_raw_pct": _r(b_raw), "session_raw_pct": _r(s_raw), "reasons": counts,
        "unplaced_listed": unplaced, "evidence": evidence,
        "pass": evidence and b_adj >= THRESHOLD and s_adj >= THRESHOLD, "differences": diffs,
    }


def _r(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(v, 4)


def render(res: Dict[str, Any]) -> str:
    pct = lambda v: "-" if v is None else "%.0f%%" % (v * 100)  # noqa: E731
    lines = [
        "compare   scope %s, window %gh, hooks registered %s" % (res["scope"], res["hours"], res["registered"]),
        "  board     %d live rows (an event in the window, not session.died)" % res["board_live"],
        "  sessions  %d listed sessions in scope with a transcript modified in the window (%d more could not "
        "be placed)" % (res["sessions"], res["unplaced_listed"]),
        "  both      %d" % res["both"],
        "  figures   board side %s, session side %s (raw %s, %s); %s of each set must appear in the other, "
        "without the reasons %s" % (pct(res["board_pct"]), pct(res["session_pct"]), pct(res["board_raw_pct"]),
                                    pct(res["session_raw_pct"]), pct(THRESHOLD), ", ".join(EXCLUDED)),
        "  result    %s" % ("PASS" if res["pass"] else "FAIL" if res["evidence"] else
                            "NO EVIDENCE (a side has nothing left to count), which fails"),
    ]
    for d in res["differences"]:
        lines.append("  %-9s %s  %s%s" % (d["side"], d["session_id"], d["reason"],
                                           " (not counted)" if d["reason"] in EXCLUDED else ""))
    return "\n".join(lines)


def append_summary(scope_id: str, res: Dict[str, Any]) -> Path:
    path = ctx.state_root() / scope_id / "compare.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    line = {k: v for k, v in res.items() if k != "differences"}
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(line, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return path


def run_for_scope(scope_id: str, hours: float = 6.0, as_json: bool = False, listing_file: Optional[str] = None,
                  registered: Optional[str] = None, now: Optional[float] = None) -> int:
    """Print the comparison, append its summary line; exit 1 under 95% or when
    the listing can't be read."""
    now = time.time() if now is None else now
    try:
        listing = load_listing(listing_file)
        transcripts = transcript_times()
    except (RuntimeError, OSError, ValueError) as exc:
        print("compare   the session listing or the transcripts could not be read: %s" % exc)
        return 1
    reg = ctx.parse_ts(registered) if registered else None
    res = compare(scope_id, listing, transcripts, now, hours, reg)
    append_summary(scope_id, res)
    print(json.dumps(res, indent=1, sort_keys=True) if as_json else render(res))
    return 0 if res["pass"] else 1
