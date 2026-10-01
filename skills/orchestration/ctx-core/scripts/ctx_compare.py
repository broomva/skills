"""ctx doctor --compare: the core's phase-1 exit comparison (core spec §9, as
merged in broomva/workspace#842 at 007f05a98).

Board rows that are live (an event in the window, not session.died), against
in-scope sessions from `claude agents --json --all` that have a timestamped
transcript entry in the same window. The pass bar is ≥95% each way on the RAW
sets; the reasons explain differences and remove none. Matching is on the full
session id, never on counts.

Read-only on the store: the board is rebuilt in memory, and the one write is a
summary line appended to <store>/compare.jsonl. The registration time is
passed once (--registered) and kept in that file's first line, because the
log's first event can predate registration; a later --registered that
disagrees with it is refused.

Transcript mtime isn't used anywhere: Claude Code moves it with untimestamped
records (last-prompt, cost-state) long after a turn. "An entry" is a line
with a timestamp.

Reasons, tried in this order (a new one is a code change with a test):

    board rows the session side lacks
      no-transcript        no transcript for the session id anywhere
      ended                a transcript, and claude agents no longer lists it
    listed sessions the board lacks
      pre-registration     no transcript entry after --registered
      died                 latest event session.died, no entry after it (the board is right)
      died-then-continued  latest event session.died, entries after it
      stale-in-turn        latest event older than the window, entries after it (one long turn)
      no-event             no event for the session id at all
    anything else          unexplained

Plus, uncounted: in-scope transcripts with an entry in the window that are on
neither side (a finished claude -p isn't listed, so a headless run that left no
event never becomes a difference).

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

BOARD_REASONS = ("no-transcript", "ended")
SESSION_REASONS = ("pre-registration", "died", "died-then-continued", "stale-in-turn", "no-event")
REASONS = BOARD_REASONS + SESSION_REASONS + ("unexplained",)
THRESHOLD = 0.95


class CompareError(RuntimeError):
    pass


def load_listing(path: Optional[str] = None, timeout: float = 30.0) -> List[Dict[str, Any]]:
    """The session listing, from `claude agents --json --all` or a captured
    file. Raises CompareError when it can't be read or is empty (it lists at
    least the session asking)."""
    try:
        if path:
            text = Path(path).read_text(encoding="utf-8")
        else:
            claude = os.environ.get("CTX_CLAUDE_BIN") or "claude"
            proc = subprocess.run([claude, "agents", "--json", "--all"], stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=timeout)
            if proc.returncode != 0:
                raise CompareError("claude agents exited %d" % proc.returncode)
            text = proc.stdout.decode("utf-8", "replace")
        rows = json.loads(text)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise CompareError("the session listing: %s" % exc)
    if not isinstance(rows, list):
        raise CompareError("the session listing is not a JSON array")
    rows = [r for r in rows if isinstance(r, dict) and isinstance(r.get("sessionId"), str)]
    if not rows:
        raise CompareError("claude agents listed no session")
    return rows


def last_entry_ts(path: str, max_bytes: int = 128 * 1024) -> Optional[float]:
    """The time of a transcript's last entry that carries a timestamp, or None.
    Reads only the tail, and only the `timestamp` field of each line."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - max_bytes))
            tail = fh.read()
    except OSError:
        return None
    for raw in reversed(tail.split(b"\n")):
        if b'"timestamp"' not in raw:
            continue
        try:
            ts = json.loads(raw.decode("utf-8")).get("timestamp")
        except (ValueError, UnicodeDecodeError, AttributeError):
            continue
        if isinstance(ts, str) and len(ts) >= 19 and ts[4:5] == "-" and ts[10:11] == "T":
            frac = ts[20:23] if ts[19:20] == "." else "000"
            try:
                return ctx.parse_ts("%s.%sZ" % (ts[:19], frac.ljust(3, "0")))
            except ValueError:
                continue
    return None


def transcripts() -> Dict[str, Tuple[float, str]]:
    """{session id: (mtime, path)} of each session's newest top-level
    transcript. Raises CompareError when the projects directory can't be read:
    that is no evidence, not an empty set. The mtime is used only to skip files
    last written before the window (an entry is never newer than its file)."""
    out: Dict[str, Tuple[float, str]] = {}
    root = ctx._claude_projects_dir()
    try:
        pdirs = [p for p in root.iterdir() if p.is_dir()]
    except OSError as exc:
        raise CompareError("%s: %s" % (root, exc.strerror or exc))
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
                if mt >= out.get(e.name[:-6], (0.0, ""))[0]:
                    out[e.name[:-6]] = (mt, e.path)
    return out


def _live(row: Dict[str, Any], cut: str) -> bool:
    return row.get("state") != "died" and str(row.get("last_ts") or "") >= cut


def compare(scope_id: str, listing: List[Dict[str, Any]], files: Dict[str, Tuple[float, str]], now: float,
            registered: float, hours: float = 6.0) -> Dict[str, Any]:
    scopes = ctx.load_scopes()
    repos = {r for r, s in scopes.by_repo.items() if s == scope_id}
    sc = ctx.Scope(id=scope_id, store=ctx.state_root() / scope_id, where=None)
    rows = ctx.rebuild(scope_id, ctx.read_log(sc))["sessions"]
    window = now - hours * 3600
    cut = ctx.now_ts(window)
    entry_cache: Dict[str, Optional[float]] = {}

    def last(sid: str) -> Optional[float]:
        if sid not in entry_cache:
            f = files.get(sid)
            entry_cache[sid] = last_entry_ts(f[1]) if f else None
        return entry_cache[sid]

    def placed(sid: str, cwd: str) -> Optional[str]:
        exists = bool(cwd) and os.path.isdir(cwd)
        where = ctx.locate(cwd, timeout=2.0) if exists else None
        if where is not None:
            return where.common_dir
        if not exists and sid in rows:  # a worktree removed after merge: its row says where it was
            return rows[sid].get("repo")
        return None

    board_live = {sid for sid, r in rows.items() if _live(r, cut)}
    listed = {r["sessionId"]: r for r in listing}
    session_side, unplaced = set(), 0
    for sid, r in listed.items():
        f = files.get(sid)
        if not f or f[0] < window or (last(sid) or 0.0) < window:
            continue
        repo = placed(sid, r.get("cwd") if isinstance(r.get("cwd"), str) else "")
        if repo is None:
            unplaced += 1
        elif repo in repos:
            session_side.add(sid)

    both = board_live & session_side
    diffs: List[Dict[str, str]] = []
    for sid in sorted(board_live - session_side):
        reason = "no-transcript" if sid not in files else "ended" if sid not in listed else "unexplained"
        diffs.append({"session_id": sid, "side": "board", "reason": reason})
    for sid in sorted(session_side - board_live):
        row, entry = rows.get(sid), last(sid)
        if entry is not None and entry < registered:
            reason = "pre-registration"
        elif row is not None and row.get("state") == "died":
            died = ctx.parse_ts(row["died_ts"]) if row.get("died_ts") else None
            reason = "died-then-continued" if died is not None and entry is not None and entry > died else "died"
        elif row is not None and str(row.get("last_ts") or "") < cut:
            reason = "stale-in-turn"
        elif row is None:
            reason = "no-event"
        else:
            reason = "unexplained"
        diffs.append({"session_id": sid, "side": "sessions", "reason": reason})

    # Uncounted: in-scope transcripts with an entry in the window, on neither side.
    neither = []
    for sid, (mt, path) in sorted(files.items()):
        if mt < window or sid in listed or sid in board_live or (last(sid) or 0.0) < window:
            continue
        cwd = ctx._transcript_cwd(Path(path)) or ""
        if placed(sid, cwd) in repos:
            neither.append(sid)

    b = len(both) / len(board_live) if board_live else None
    s = len(both) / len(session_side) if session_side else None
    evidence = b is not None and s is not None
    return {
        "v": 1, "ts": ctx.now_ts(now), "scope": scope_id, "hours": hours, "registered": ctx.now_ts(registered),
        "board_live": len(board_live), "sessions": len(session_side), "both": len(both),
        "board_pct": None if b is None else round(b, 4), "session_pct": None if s is None else round(s, 4),
        "reasons": {r: sum(1 for d in diffs if d["reason"] == r) for r in REASONS},
        "unplaced_listed": unplaced, "neither": len(neither), "evidence": evidence,
        "pass": evidence and b >= THRESHOLD and s >= THRESHOLD, "differences": diffs, "neither_ids": neither,
    }


def render(res: Dict[str, Any]) -> str:
    pct = lambda v: "-" if v is None else "%.0f%%" % (v * 100)  # noqa: E731
    lines = [
        "compare   scope %s, window %gh, hooks registered %s" % (res["scope"], res["hours"], res["registered"]),
        "  board     %d live rows (an event in the window, not session.died)" % res["board_live"],
        "  sessions  %d listed sessions in scope with a timestamped transcript entry in the window (%d more "
        "could not be placed)" % (res["sessions"], res["unplaced_listed"]),
        "  both      %d" % res["both"],
        "  figures   board side %s, session side %s; %s of each set must appear in the other"
        % (pct(res["board_pct"]), pct(res["session_pct"]), pct(THRESHOLD)),
        "  result    %s" % ("PASS" if res["pass"] else "FAIL" if res["evidence"] else
                            "NO EVIDENCE (a side is empty), which fails"),
    ]
    for d in res["differences"]:
        lines.append("  %-9s %s  %s" % (d["side"], d["session_id"], d["reason"]))
    if res["neither_ids"]:
        lines.append("  uncounted: %d in-scope transcript(s) with an entry in the window on neither side "
                     "(a finished claude -p isn't listed): %s" % (res["neither"], ", ".join(res["neither_ids"][:10])))
    return "\n".join(lines)


def _path(scope_id: str) -> Path:
    return ctx.state_root() / scope_id / "compare.jsonl"


def registered_on_file(scope_id: str) -> Optional[str]:
    try:
        with _path(scope_id).open(encoding="utf-8") as fh:
            first = fh.readline()
        return json.loads(first).get("registered") if first.strip() else None
    except (OSError, ValueError, AttributeError):
        return None


def append_summary(scope_id: str, line: Dict[str, Any]) -> Path:
    path = _path(scope_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(line, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return path


def run_for_scope(scope_id: str, hours: float = 6.0, as_json: bool = False, listing_file: Optional[str] = None,
                  registered: Optional[str] = None, now: Optional[float] = None) -> int:
    """Print the comparison and append its summary line. Exit 1 under 95%, with
    no evidence, or when the listing or transcripts can't be read (that too is
    written, so the latest line never shows an old pass); exit 2 when there is
    no registration time, or --registered disagrees with the file's."""
    now = time.time() if now is None else now
    on_file = registered_on_file(scope_id)
    if registered and on_file and registered != on_file:
        print("compare   --registered %s disagrees with compare.jsonl's first line (%s); refused. Move the file "
              "aside to start over." % (registered, on_file))
        return 2
    reg_text = on_file or registered
    if not reg_text:
        print("compare   no registration time: pass --registered <UTC YYYY-MM-DDTHH:MM:SS.mmmZ> once; it is "
              "kept in %s" % _path(scope_id))
        return 2
    try:
        reg = ctx.parse_ts(reg_text)
    except (ValueError, IndexError):
        print("compare   --registered %r is not UTC YYYY-MM-DDTHH:MM:SS.mmmZ" % reg_text)
        return 2
    try:
        listing = load_listing(listing_file)
        files = transcripts()
    except CompareError as exc:
        append_summary(scope_id, {"v": 1, "ts": ctx.now_ts(now), "scope": scope_id, "hours": hours,
                                  "registered": reg_text, "evidence": False, "pass": False,
                                  "error": str(exc)[:200]})
        print("compare   could not be read: %s" % exc)
        return 1
    res = compare(scope_id, listing, files, now, reg, hours)
    append_summary(scope_id, {k: v for k, v in res.items() if k not in ("differences", "neither_ids")})
    print(json.dumps(res, indent=1, sort_keys=True) if as_json else render(res))
    return 0 if res["pass"] else 1
