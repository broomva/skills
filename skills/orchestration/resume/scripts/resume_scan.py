#!/usr/bin/env python3
"""resume_scan.py — forensic reconstruction of an arc that died mid-flight.

Claude Code sessions die on external faults (API 529/500, ENOTFOUND,
ConnectionRefused, expired login). The operator restarts and types `resume`.
Nothing was written down in advance, so state must be *reconstructed*.

The load-bearing fact this script encodes, which is not obvious and which a
first-principles guess gets wrong:

    Subagents launch ASYNCHRONOUSLY. The spawn's tool_result is ALWAYS
    "Async agent launched successfully" — it means *launched*, never
    *finished*. Completion arrives later as a separate <task-notification>
    record. So a dead agent leaves NO orphaned tool_use; matching
    tool_use->tool_result finds nothing. The correct detector is
    spawn-id -> completion-notification, and a spawn whose id never appears
    in a completion is the thing that died.

    The dead agent's full transcript SURVIVES on disk at
    <session-dir>/tasks/<id>.output. Its work is recoverable rather than
    lost. Those files reach 1.3 MB, so they are digested under a hard
    character budget here and never read whole.

Exit codes: 0 = scan completed (regardless of findings), 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# A spawn result carries the agent id and where its transcript lives.
AGENT_ID_RE = re.compile(r"agentId:\s*([A-Za-z0-9_-]+)")
OUTPUT_FILE_RE = re.compile(r"output_file:\s*(\S+)")
ASYNC_LAUNCH_RE = re.compile(r"Async agent launched successfully", re.I)

# Completion notifications are emitted as an XML-ish block in record content.
NOTIF_RE = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
NOTIF_ID_RE = re.compile(r"<task-id>\s*([^<]+?)\s*</task-id>")
NOTIF_TOOLUSE_RE = re.compile(r"<tool-use-id>\s*([^<]+?)\s*</tool-use-id>")
NOTIF_STATUS_RE = re.compile(r"<status>\s*([^<]+?)\s*</status>")
NOTIF_SUMMARY_RE = re.compile(r"<summary>\s*(.*?)\s*</summary>", re.S)

SPAWN_TOOLS = ("Agent", "Task", "Workflow")

# The harness RENDERS a termination with a fixed prefix. Anchoring on that
# prefix — rather than on proximity to the start — is what separates a session
# that died from a session merely *discussing* deaths. See _termination_text.
ERROR_PREFIX_RE = re.compile(
    r"^\s*(?:API Error\b|\[Request interrupted|Login expired|"
    r"Claude usage limit|Usage limit reached)", re.I)

# Ordered most-specific first: the first match wins, so "usage limit" is not
# swallowed by the generic "limit" in a rate-limit pattern.
TERMINATION_SIGNATURES = [
    ("auth_expired",  re.compile(r"Login expired|Please run /login|authentication_error|invalid[_ ]api[_ ]key|OAuth token has expired|\b401\b", re.I)),
    ("usage_limit",   re.compile(r"usage limit|limit reached|resets at|credit balance", re.I)),
    ("rate_limited",  re.compile(r"rate.?limit|\b429\b", re.I)),
    ("api_overload",  re.compile(r"\b529\b|Overloaded", re.I)),
    ("api_5xx",       re.compile(r"\b5(00|02|03)\b|Internal server error|Bad gateway|Service unavailable", re.I)),
    ("network",       re.compile(r"ENOTFOUND|ECONNRESET|ETIMEDOUT|ConnectionRefused|Connection error|Connection lost|socket hang up|fetch failed|Unable to connect|Can't reach the API", re.I)),
    ("user_interrupt", re.compile(r"\[Request interrupted|Interrupted by user", re.I)),
]


# ---------------------------------------------------------------- locating

def mangle(path: str) -> str:
    """Claude Code's project-dir encoding: every non-alphanumeric char -> '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path))


def find_session(cwd: str, projects_dir: str = PROJECTS_DIR) -> str | None:
    """Most-recently-modified transcript for `cwd`.

    Primary: the mangled-path project dir. Fallback: scan project dirs for a
    transcript whose records declare this cwd — worktrees and renamed dirs do
    not always mangle to what you expect, and a wrong-session scan is worse
    than a slow one.
    """
    cand = os.path.join(projects_dir, mangle(cwd))
    best = _newest_jsonl(cand)
    if best:
        return best

    target = os.path.abspath(cwd)
    newest, newest_m = None, -1.0
    if not os.path.isdir(projects_dir):
        return None
    for entry in os.scandir(projects_dir):
        if not entry.is_dir():
            continue
        f = _newest_jsonl(entry.path)
        if not f:
            continue
        try:
            m = os.stat(f).st_mtime
        except OSError:
            continue
        if m <= newest_m:
            continue
        if _declares_cwd(f, target):
            newest, newest_m = f, m
    return newest


def _newest_jsonl(d: str) -> str | None:
    if not os.path.isdir(d):
        return None
    best, best_m = None, -1.0
    for entry in os.scandir(d):
        if not entry.name.endswith(".jsonl"):
            continue
        try:
            m = entry.stat().st_mtime
        except OSError:
            continue
        if m > best_m:
            best, best_m = entry.path, m
    return best


def _declares_cwd(path: str, target: str, probe_lines: int = 40) -> bool:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= probe_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                c = rec.get("cwd")
                if c:
                    return os.path.abspath(c) == target
    except OSError:
        return False
    return False


def load(path: str) -> list[dict]:
    recs = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except ValueError:
                continue
    return recs


# ---------------------------------------------------------------- extraction

def _blocks(rec: dict):
    """Yield content blocks of a record, tolerating string-valued content."""
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                yield b
    elif isinstance(content, str) and content:
        yield {"type": "text", "text": content}


def _text_of(block: dict) -> str:
    t = block.get("type")
    if t == "text":
        return block.get("text") or ""
    if t == "tool_result":
        c = block.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return ""


def record_text(rec: dict) -> str:
    return " ".join(_text_of(b) for b in _blocks(rec))


def find_spawns(recs: list[dict]) -> list[dict]:
    """Async spawns, keyed by the agentId in their launch receipt."""
    pending: dict[str, dict] = {}
    spawns: list[dict] = []
    for idx, rec in enumerate(recs):
        for b in _blocks(rec):
            if b.get("type") == "tool_use" and b.get("name") in SPAWN_TOOLS:
                inp = b.get("input") or {}
                pending[b.get("id")] = {
                    "tool_use_id": b.get("id"),
                    "tool": b.get("name"),
                    "description": inp.get("description") or inp.get("name") or "",
                    "prompt": (inp.get("prompt") or "")[:2000],
                    "subagent_type": inp.get("subagent_type") or "",
                    "spawned_at": rec.get("timestamp", "")[:19],
                    "index": idx,
                }
            elif b.get("type") == "tool_result":
                meta = pending.get(b.get("tool_use_id"))
                if not meta:
                    continue
                s = _text_of(b)
                if not ASYNC_LAUNCH_RE.search(s):
                    # Synchronous return: it already reported. Not in flight.
                    pending.pop(b.get("tool_use_id"), None)
                    continue
                aid = AGENT_ID_RE.search(s)
                out = OUTPUT_FILE_RE.search(s)
                meta = dict(meta)
                meta["agent_id"] = aid.group(1) if aid else None
                meta["output_file"] = out.group(1) if out else None
                spawns.append(meta)
                pending.pop(b.get("tool_use_id"), None)
    return spawns


def find_completions(recs: list[dict]) -> dict[str, dict]:
    """task-id -> completion info, from <task-notification> blocks."""
    done: dict[str, dict] = {}
    for rec in recs:
        text = record_text(rec)
        if "<task-notification>" not in text:
            continue
        for body in NOTIF_RE.findall(text):
            tid = NOTIF_ID_RE.search(body)
            if not tid:
                continue
            status = NOTIF_STATUS_RE.search(body)
            summary = NOTIF_SUMMARY_RE.search(body)
            tu = NOTIF_TOOLUSE_RE.search(body)
            done[tid.group(1)] = {
                "status": status.group(1) if status else "unknown",
                "summary": (summary.group(1) if summary else "").replace("\\n", " ")[:300],
                "tool_use_id": tu.group(1) if tu else None,
            }
    return done


def _termination_text(rec: dict) -> str:
    """Text that may legitimately testify to a termination.

    Deliberately narrow, and anchored rather than fuzzy. An error *pattern* is
    not an error: a tool_result echoing a ticket body about "529 Overloaded",
    or prose analysing past failures, must not be read as this session dying.
    Both were measured as real false positives — the second survived a
    head-of-message window and was caught only by a unit test.

    Admissible: records the harness itself flagged (`isApiErrorMessage`), and
    text blocks whose OPENING matches how the harness renders a failure
    ("API Error: ...", "[Request interrupted...", "Login expired ..."). Never
    tool_result content, and never a mention buried in prose.
    """
    if rec.get("isApiErrorMessage"):
        return record_text(rec)
    parts = []
    for b in _blocks(rec):
        if b.get("type") != "text":
            continue
        t = (b.get("text") or "").lstrip()
        if t and ERROR_PREFIX_RE.match(t):
            parts.append(t)
    return "\n".join(parts)


def find_termination(recs: list[dict], tail: int = 400) -> dict:
    """Classify how the session stopped, scanning backwards from the end."""
    for rec in reversed(recs[-tail:]):
        text = _termination_text(rec)
        if not text.strip():
            continue
        for kind, pat in TERMINATION_SIGNATURES:
            m = pat.search(text)
            if m:
                return {
                    "kind": kind,
                    "evidence": text[max(0, m.start() - 60): m.start() + 160].replace("\n", " ").strip(),
                    "at": rec.get("timestamp", "")[:19],
                }
    return {"kind": "clean_or_unknown", "evidence": "", "at": ""}


# ---------------------------------------------------------------- recovery

def digest_output(path: str, max_chars: int = 1200, tail_records: int = 400) -> dict:
    """Bounded digest of a dead agent's surviving transcript.

    NEVER returns the whole file: these reach 1.3 MB and the harness warns
    that reading one raw overflows the parent's context. Keeps a rolling
    window of the last `tail_records` records and reports only the final
    assistant prose plus a file/tool tally.
    """
    if not path or not os.path.exists(path):
        return {"recoverable": False, "reason": "output file no longer on disk"}
    try:
        size = os.path.getsize(path)
    except OSError as e:
        return {"recoverable": False, "reason": str(e)}
    if size == 0:
        return {"recoverable": False, "reason": "empty (agent produced nothing before dying)"}

    from collections import deque
    window: deque = deque(maxlen=tail_records)
    n_lines = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                n_lines += 1
                line = line.strip()
                if line:
                    window.append(line)
    except OSError as e:
        return {"recoverable": False, "reason": str(e)}

    texts: list[str] = []
    tools: dict[str, int] = {}
    files: set[str] = set()
    for line in window:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") == "assistant":
            for b in _blocks(rec):
                if b.get("type") == "text" and b.get("text", "").strip():
                    texts.append(b["text"].strip())
        for b in _blocks(rec):
            if b.get("type") == "tool_use":
                name = b.get("name") or "?"
                tools[name] = tools.get(name, 0) + 1
                inp = b.get("input") or {}
                fp = inp.get("file_path") or inp.get("notebook_path")
                if fp:
                    files.add(str(fp))

    final = ""
    for t in reversed(texts):
        if len(final) + len(t) > max_chars:
            if not final:
                final = t[:max_chars]
            break
        final = (t + "\n\n" + final) if final else t

    return {
        "recoverable": bool(final or files or tools),
        "bytes": size,
        "records": n_lines,
        "truncated_window": n_lines > tail_records,
        "final_text": final[:max_chars],
        "tool_counts": dict(sorted(tools.items(), key=lambda kv: -kv[1])),
        "files_touched": sorted(files)[:40],
        "mtime_age_s": int(time.time() - os.path.getmtime(path)),
    }


def scan(session_path: str, max_chars: int = 1200, live_window_s: int = 90) -> dict:
    recs = load(session_path)
    spawns = find_spawns(recs)
    done = find_completions(recs)

    # A spawn is matched by agentId or by its originating tool_use_id: the
    # notification keys on task-id, which equals the agent id for subagents
    # and a separate task id for background shells.
    done_tool_use = {v.get("tool_use_id") for v in done.values() if v.get("tool_use_id")}

    for s in spawns:
        aid = s.get("agent_id")
        info = done.get(aid) if aid else None
        if info is None and s.get("tool_use_id") in done_tool_use:
            info = next(v for v in done.values() if v.get("tool_use_id") == s["tool_use_id"])
        if info:
            s["state"] = "reported"
            s["status"] = info.get("status")
            s["summary"] = info.get("summary")
        else:
            s["state"] = "unreported"
            s["digest"] = digest_output(s.get("output_file"), max_chars=max_chars)
            age = s["digest"].get("mtime_age_s")
            # A file still being written means the process outlived the parent
            # (background shells do; in-process subagents do not).
            s["possibly_live"] = age is not None and age < live_window_s

    return {
        "session": session_path,
        "records": len(recs),
        "termination": find_termination(recs),
        "spawns_total": len(spawns),
        "unreported": [s for s in spawns if s["state"] == "unreported"],
        "reported": [s for s in spawns if s["state"] == "reported"],
    }


# ---------------------------------------------------------------- rendering

def render(result: dict) -> str:
    out: list[str] = []
    term = result["termination"]
    out.append("=" * 68)
    out.append("RESUME SCAN")
    out.append("=" * 68)
    out.append(f"session      : {result['session']}")
    out.append(f"records      : {result['records']}")
    out.append(f"terminated   : {term['kind']}" + (f"  @ {term['at']}" if term["at"] else ""))
    if term["evidence"]:
        out.append(f"  evidence   : {term['evidence'][:200]}")
    out.append("")
    out.append(f"async spawns : {result['spawns_total']}  "
               f"({len(result['reported'])} reported, {len(result['unreported'])} UNREPORTED)")

    if not result["unreported"]:
        out.append("")
        out.append("No unreported agents. Nothing died mid-flight — continue the arc from")
        out.append("the last completed step. (This is not a signal to wrap up.)")
        return "\n".join(out)

    out.append("")
    out.append("-" * 68)
    out.append("UNREPORTED — these never returned. Recover, then re-spawn what is dead.")
    out.append("-" * 68)
    for s in result["unreported"]:
        d = s.get("digest", {})
        live = "  [POSSIBLY STILL RUNNING — check before re-spawning]" if s.get("possibly_live") else ""
        out.append("")
        out.append(f"• {s['tool']}  {s['description'] or '(no description)'}{live}")
        out.append(f"  spawned    : {s['spawned_at']}   agent_id: {s.get('agent_id')}")
        if s.get("subagent_type"):
            out.append(f"  type       : {s['subagent_type']}")
        if not d.get("recoverable"):
            out.append(f"  recovery   : NONE — {d.get('reason', 'no digest')}")
            out.append("  action     : re-spawn from scratch (prompt below)")
        else:
            out.append(f"  transcript : {d['bytes']:,}B / {d['records']} records"
                       f" (last write {d['mtime_age_s']}s ago)")
            if d.get("tool_counts"):
                tc = ", ".join(f"{k}×{v}" for k, v in list(d["tool_counts"].items())[:6])
                out.append(f"  did        : {tc}")
            if d.get("files_touched"):
                out.append(f"  files      : {', '.join(d['files_touched'][:6])}"
                           + (" …" if len(d["files_touched"]) > 6 else ""))
            if d.get("final_text"):
                out.append("  last words :")
                for ln in d["final_text"].splitlines()[:12]:
                    out.append(f"    | {ln[:110]}")
            out.append("  action     : fold the above into the arc; re-spawn ONLY the unfinished part")
        if s.get("prompt"):
            out.append("  orig prompt:")
            for ln in s["prompt"].splitlines()[:6]:
                out.append(f"    > {ln[:110]}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reconstruct an arc that died mid-flight.")
    ap.add_argument("--session", help="path to a session .jsonl (default: newest for --cwd)")
    ap.add_argument("--cwd", default=os.getcwd(), help="working dir whose session to find")
    ap.add_argument("--projects-dir", default=PROJECTS_DIR)
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    ap.add_argument("--max-chars", type=int, default=1200,
                    help="hard cap on recovered text per dead agent")
    args = ap.parse_args(argv)

    session = args.session or find_session(args.cwd, args.projects_dir)
    if not session or not os.path.exists(session):
        print(f"resume_scan: no session transcript found for {args.cwd}", file=sys.stderr)
        return 2

    result = scan(session, max_chars=args.max_chars)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
