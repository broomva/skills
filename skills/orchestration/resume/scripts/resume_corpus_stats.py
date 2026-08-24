#!/usr/bin/env python3
"""resume_corpus_stats.py — regenerate the statistics SKILL.md cites.

SKILL.md argues from measured numbers (how often a resume turn follows an API
error, how often subagents were in flight, how often the agent restored them).
A number stated in prose and a number produced by a sweep render identically,
so the claim is only worth as much as the script that reproduces it. This is
that script.

It answers, over a corpus of Claude Code transcripts:

  * how many resume-class user turns exist
  * what immediately preceded each one (API error / interrupt / neither)
  * how many had an async subagent or workflow in flight at that moment
  * what the agent did next — re-spawned, queried the running tasks, ran
    ordinary tools, or emitted no tool calls at all
  * how many acknowledged an agent death without restoring it
  * how often `resume` had to be typed again

Usage:
    python3 resume_corpus_stats.py                       # ~/.claude/projects
    python3 resume_corpus_stats.py --root <dir> --json
    python3 resume_corpus_stats.py --limit 200           # cap files scanned

Exit codes: 0 = scan completed, 2 = corpus not found.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# A resume-class turn: short, opens with continuation vocabulary.
RESUME_RE = re.compile(
    r"^\s*(resume|continue|keep going|go on|carry on|pick up|please continue|"
    r"please resume|/resume|/continue|proceed|keep working|continue working|"
    r"as you were)\b",
    re.I,
)
MAX_TURN_CHARS = 120

# Harness injections that are not human turns.
INJECTED = ("<system-reminder>", "<local-command-caveat>", "Caveat:")

SPAWN_TOOLS = ("Agent", "Task", "Workflow")
QUERY_TOOLS = ("TaskOutput", "SendMessage", "TaskStop")

PRECEDING = {
    "api_error": re.compile(
        r"API Error|Connection error|Connection lost|fetch failed|ECONNRESET|"
        r"ETIMEDOUT|ENOTFOUND|ConnectionRefused|socket hang up|Overloaded|"
        r"Internal server error|\b52[09]\b|\b50[023]\b", re.I),
    "auth": re.compile(r"Login expired|Please run /login|authentication_error|\b401\b", re.I),
    "interrupt": re.compile(r"\[Request interrupted|Interrupted by user", re.I),
    "usage_limit": re.compile(r"usage limit|limit reached|resets at", re.I),
}

DEATH_RE = re.compile(
    r"\b(died|killed|dead|mid-flight|mid-review|mid-call|never (returned|reported)|"
    r"hit (an|the) .{0,25}limit)\b", re.I)


def _blocks(rec):
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                yield b
    elif isinstance(content, str) and content:
        yield {"type": "text", "text": content}


def _text(rec) -> str:
    out = []
    for b in _blocks(rec):
        t = b.get("type")
        if t == "text":
            out.append(b.get("text") or "")
        elif t == "tool_result":
            c = b.get("content")
            if isinstance(c, str):
                out.append(c)
            elif isinstance(c, list):
                out.extend(x.get("text", "") for x in c if isinstance(x, dict))
    return " ".join(out)


def _user_prose(rec) -> str | None:
    """The typed text of a human turn, or None if this is not one."""
    if rec.get("type") != "user" or rec.get("isSidechain"):
        return None
    parts = []
    for b in _blocks(rec):
        if b.get("type") == "text":
            parts.append(b.get("text") or "")
    s = " ".join(parts).strip()
    if not s or any(m in s for m in INJECTED):
        return None
    return s


def load(path: str) -> list[dict]:
    recs = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return recs


def analyse_file(path: str) -> list[dict]:
    recs = load(path)
    hits = []
    for i, rec in enumerate(recs):
        prose = _user_prose(rec)
        if prose is None or len(prose) > MAX_TURN_CHARS or not RESUME_RE.match(prose):
            continue

        # --- what immediately preceded it
        back = " || ".join(_text(r) if not r.get("isApiErrorMessage")
                           else "API Error " + _text(r)
                           for r in recs[max(0, i - 6):i])
        preceded = [k for k, p in PRECEDING.items() if p.search(back)]

        # --- was anything in flight
        inflight = 0
        for r in recs[max(0, i - 120):i]:
            for b in _blocks(r):
                if b.get("type") == "tool_use" and b.get("name") in SPAWN_TOOLS:
                    inflight += 1

        # --- what the agent did next, until the next human turn
        tools, after_text = [], ""
        for j in range(i + 1, min(len(recs), i + 80)):
            nxt = recs[j]
            if _user_prose(nxt):
                break
            if nxt.get("type") != "assistant":
                continue
            for b in _blocks(nxt):
                if b.get("type") == "tool_use":
                    tools.append(b.get("name"))
                elif b.get("type") == "text":
                    after_text += b.get("text") or ""

        # --- did the operator have to say it again
        retyped = False
        for j in range(i + 1, min(len(recs), i + 40)):
            p2 = _user_prose(recs[j])
            if p2 is None:
                continue
            if len(p2) <= 60 and RESUME_RE.match(p2):
                retyped = True
            break

        ts = set(tools)
        hits.append({
            "text": prose,
            "preceded_by": preceded,
            "inflight_spawns": inflight,
            "respawned": bool(ts & set(SPAWN_TOOLS)),
            "queried_tasks": bool(ts & set(QUERY_TOOLS)),
            "no_tools": not tools,
            "acknowledged_death": bool(DEATH_RE.search(after_text)),
            "retyped": retyped,
        })
    return hits


def summarise(hits: list[dict], files: int) -> dict:
    n = len(hits)
    ack_no_restore = sum(1 for h in hits if h["acknowledged_death"] and not h["respawned"])
    ack_restore = sum(1 for h in hits if h["acknowledged_death"] and h["respawned"])
    return {
        "files_scanned": files,
        "resume_turns": n,
        "bare_resume": sum(1 for h in hits if h["text"].strip().lower().rstrip(".!") == "resume"),
        "preceded_by_api_error": sum(1 for h in hits if "api_error" in h["preceded_by"]),
        "preceded_by_auth": sum(1 for h in hits if "auth" in h["preceded_by"]),
        "preceded_by_interrupt": sum(1 for h in hits if "interrupt" in h["preceded_by"]),
        "had_inflight_spawn": sum(1 for h in hits if h["inflight_spawns"] > 0),
        "respawned_after": sum(1 for h in hits if h["respawned"]),
        "queried_running_tasks": sum(1 for h in hits if h["queried_tasks"]),
        "no_tool_calls_at_all": sum(1 for h in hits if h["no_tools"]),
        "acknowledged_death_not_restored": ack_no_restore,
        "acknowledged_death_and_restored": ack_restore,
        "retyped_within_40_records": sum(1 for h in hits if h["retyped"]),
        "distinct_surface_forms": len({h["text"].strip().lower().rstrip(".!") for h in hits}),
    }


def render(s: dict) -> str:
    n = max(s["resume_turns"], 1)
    def pct(v):
        return f"{round(v * 100 / n)}%"
    rows = [
        ("transcripts scanned", s["files_scanned"], ""),
        ("resume-class turns", s["resume_turns"], f"{s['bare_resume']} bare 'resume'"),
        ("distinct surface forms", s["distinct_surface_forms"], ""),
        ("preceded by an API error", s["preceded_by_api_error"], pct(s["preceded_by_api_error"])),
        ("preceded by an auth failure", s["preceded_by_auth"], pct(s["preceded_by_auth"])),
        ("preceded by a user interrupt", s["preceded_by_interrupt"], pct(s["preceded_by_interrupt"])),
        ("had a spawn IN FLIGHT at death", s["had_inflight_spawn"], pct(s["had_inflight_spawn"])),
        ("re-spawned an agent afterwards", s["respawned_after"], pct(s["respawned_after"])),
        ("queried the running tasks", s["queried_running_tasks"], pct(s["queried_running_tasks"])),
        ("NO tool calls at all", s["no_tool_calls_at_all"], pct(s["no_tool_calls_at_all"])),
        ("ack'd a death, did NOT restore", s["acknowledged_death_not_restored"], ""),
        ("ack'd a death AND restored", s["acknowledged_death_and_restored"], ""),
        ("resume retyped within 40 records", s["retyped_within_40_records"], pct(s["retyped_within_40_records"])),
    ]
    w = max(len(r[0]) for r in rows)
    out = ["=" * (w + 20), "RESUME CORPUS STATISTICS", "=" * (w + 20)]
    for label, val, note in rows:
        out.append(f"{label.ljust(w)}  {str(val).rjust(6)}  {note}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Regenerate the statistics SKILL.md cites.")
    ap.add_argument("--root", default=PROJECTS_DIR, help="corpus root (default ~/.claude/projects)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="cap files scanned (0 = no cap)")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        print(f"resume_corpus_stats: no corpus at {args.root}", file=sys.stderr)
        return 2

    files = sorted(glob.glob(os.path.join(args.root, "**", "*.jsonl"), recursive=True))
    if args.limit:
        files = files[: args.limit]

    hits = []
    for f in files:
        hits.extend(analyse_file(f))

    summary = summarise(hits, len(files))
    print(json.dumps(summary, indent=2) if args.json else render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
