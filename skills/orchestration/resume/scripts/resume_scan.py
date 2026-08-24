#!/usr/bin/env python3
"""resume_scan.py — forensic reconstruction of an arc that died mid-flight.

Claude Code sessions die on external faults (API 529/500, ENOTFOUND,
ConnectionRefused, expired login). The operator restarts and types `resume`.
Nothing was written down in advance, so state must be *reconstructed*.

Two load-bearing facts, neither obvious, both measured rather than assumed:

1.  **Subagents launch ASYNCHRONOUSLY.** The spawn's tool_result is ALWAYS
    "Async agent launched successfully" — it means *launched*, never
    *finished*. Completion arrives later as a separate <task-notification>.
    So a dead agent leaves NO orphaned tool_use; matching tool_use->tool_result
    finds nothing. The detector is spawn-id -> completion-notification.

2.  **Background shells are a different species.** `run_in_background` Bash
    commands are separate OS processes announced as "Command running in
    background with ID: …". They are the ONLY class that can outlive the
    parent, so they are the only class the liveness guard can meaningfully
    apply to. An earlier version tracked only in-process agents and therefore
    could never fire the guard it advertised.

Dead workers' transcripts survive on disk and reach ~1.5 MB, so they are
digested under a hard character budget and never read whole.

Exit codes: 0 = scan completed, 2 = usage/input error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# Every bound in one place. Two review rounds found caps duplicated at the use
# site (the 1200 char cap lived at three lines despite a commit claiming to
# single-source it) and constants that no test could falsify — widening them
# changed behaviour with the suite green. A literal at a use site is a bound
# nobody can check; these are named, imported, and asserted in tests/.
LIMITS = {
    "digest_chars": 1200,       # recovered prose per worker
    "digest_tail_records": 400, # how deep into a worker's log to read
    "prompt_render_chars": 4000,# prompt shown in the text render
    "summary_chars": 300,       # a completion notice's summary
    "command_chars": 400,       # a background shell's command line
    "evidence_chars": 160,      # window after a termination match
    "last_words_lines": 12,     # lines of recovered prose shown
    "files_listed": 20,         # files_touched entries kept
    "file_path_chars": 200,     # each entry's length
    "cwd_probe_lines": 40,      # records read to confirm a transcript's cwd
    "live_window_s": 90,        # recent-output window for liveness
    "termination_tail": 400,    # records scanned back for a termination
}

# --- in-process agents -------------------------------------------------
AGENT_ID_RE = re.compile(r"agentId:\s*([A-Za-z0-9_-]+)")
OUTPUT_FILE_RE = re.compile(r"output_file:\s*(\S+)")
ASYNC_LAUNCH_RE = re.compile(r"Async agent launched successfully", re.I)

# --- background shells (separate OS processes) -------------------------
BG_LAUNCH_RE = re.compile(r"Command running in background with ID:\s*([A-Za-z0-9_-]+)")
BG_OUTPUT_RE = re.compile(r"[Oo]utput is being written to:\s*(\S+)")

NOTIF_RE = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
NOTIF_ID_RE = re.compile(r"<task-id>\s*([^<]+?)\s*</task-id>")
NOTIF_TOOLUSE_RE = re.compile(r"<tool-use-id>\s*([^<]+?)\s*</tool-use-id>")
NOTIF_STATUS_RE = re.compile(r"<status>\s*([^<]+?)\s*</status>")
NOTIF_SUMMARY_RE = re.compile(r"<summary>\s*(.*?)\s*</summary>", re.S)

# `Task` is retained though it is unattested in the local corpus: it costs
# nothing and an absent alias is cheaper than a missed spawn.
AGENT_TOOLS = ("Agent", "Task", "Workflow")
# These run inside the parent process and CANNOT outlive it.
IN_PROCESS_TOOLS = AGENT_TOOLS
BG_TOOLS = ("Bash",)

# A completion whose status is not success is not an all-clear.
OK_STATUSES = ("completed", "success", "succeeded", "done")

ERROR_PREFIX_RE = re.compile(
    r"^\s*(?:API Error\b|\[Request interrupted|Login expired|"
    r"Claude usage limit|Usage limit reached|You've hit your|"
    r"Failed to authenticate|Prompt is too long|Your computer went to sleep)", re.I)

TERMINATION_SIGNATURES = [
    # 'OAuth session expired' is the real noun; 'token' matched nothing, so
    # the /login remedy could never fire on a genuine auth death.
    ("auth_expired",  re.compile(r"Login expired|Please run /login|authentication_error|invalid[_ ]api[_ ]key|Failed to authenticate|OAuth (session|token) expired|OAuth token has expired|\b401\b", re.I)),
    # `resets Aug 10 at 7am` is the dominant production form (53 of 61 sampled
    # api-error records). An earlier signature required the literal "resets at"
    # and matched none of them — the fixtures had been written to satisfy the
    # regex rather than copied from what the harness emits.
    # Copied from what the harness emits, not written to satisfy the regex.
    # 'session limit' alone is 39 of 801 sampled api-error records, and
    # 'resets 1:50pm' has no 'at'.
    ("usage_limit",   re.compile(r"usage limit|limit reached|hit your \w+[\w-]* limit|resets\s+\S|credit balance", re.I)),
    ("rate_limited",  re.compile(r"rate.?limit|\b429\b", re.I)),
    ("api_overload",  re.compile(r"\b529\b|Overloaded", re.I)),
    ("api_5xx",       re.compile(r"\b5(00|02|03)\b|Internal server error|Bad gateway|Service unavailable", re.I)),
    ("network",       re.compile(r"ENOTFOUND|ECONNRESET|ETIMEDOUT|ConnectionRefused|Connection error|Connection lost|Connection closed mid-response|Response stalled mid-stream|socket hang up|fetch failed|Unable to connect|Can't reach the API|\b52[0-4]\b", re.I)),
    ("user_interrupt", re.compile(r"\[Request interrupted|Interrupted by user", re.I)),
    # SKILL.md names "a laptop that slept" as a target cause; it was unclassified.
    ("machine_slept", re.compile(r"computer went to sleep|machine went to sleep", re.I)),
    ("context_too_long", re.compile(r"Prompt is too long|context length exceeded", re.I)),
    ("stalled",       re.compile(r"response stopped arriving|stopped responding", re.I)),
]

# Recovered text is printed into an agent's context and then, per SKILL.md
# step 6, summarised into a report. Transcripts demonstrably contain
# credentials, so anything secret-shaped is masked on the way out. This is a
# blunt instrument and is documented as one: it reduces obvious leakage, it
# does not make the output safe to publish.
SECRET_PATTERNS = [
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")),
    # sk-proj-/sk-svcacct- carry hyphens, so a [A-Za-z0-9]+ class misses them.
    # Needs the vendor prefix or a long opaque run: a bare `sk-` followed by
    # ordinary words was masking prose and URLs.
    ("openai-key",    re.compile(r"\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{20,}"
                                 r"|\bsk-[A-Za-z0-9]{32,}")),
    ("github-token",  re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("github-pat",    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("gitlab-token",  re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}")),
    ("npm-token",     re.compile(r"\bnpm_[A-Za-z0-9]{30,}")),
    ("aws-key",       re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack-token",   re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("google-key",    re.compile(r"\bAIza[A-Za-z0-9_\-]{30,}")),
    # The scheme sits BETWEEN the header and the credential
    # ("Authorization: Bearer <tok>"), so a pattern demanding the delimiter
    # immediately after the keyword matched neither production form.
    ("auth-header",   re.compile(
        r"(?i)\bauthorization\s*[:=]\s*(?:bearer|basic|token)?\s*[A-Za-z0-9._+/=\-]{12,}")),
    ("bearer",        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._+/=\-]{12,}")),
    ("pem",           re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


def redact(text: str) -> tuple[str, list[str]]:
    """Mask secret-shaped substrings. Returns (masked, kinds_found)."""
    found = []
    for kind, pat in SECRET_PATTERNS:
        text, n = pat.subn(f"[REDACTED:{kind}]", text)
        if n:
            found.append(kind)
    return text, found


# ---------------------------------------------------------------- locating

def mangle(path: str) -> str:
    """Claude Code's project-dir encoding: every non-alphanumeric char -> '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path))


def _all_jsonl(d: str) -> list[str]:
    """Transcripts directly under `d`. Not recursive: a session's own
    `subagents/` sit one level down and are not the parent session."""
    try:
        return [e.path for e in os.scandir(d) if e.name.endswith(".jsonl")]
    except OSError:
        return []


def _mtime(p: str) -> float:
    try:
        return os.stat(p).st_mtime
    except OSError:
        return -1.0


def find_sessions(cwd: str, projects_dir: str = PROJECTS_DIR) -> list[str]:
    """Every transcript belonging to `cwd`, newest first.

    A list rather than one file, because of a defect that made the tool
    useless in its own headline scenario: after a crash the operator starts a
    NEW session, whose transcript is newest by mtime, so auto-selection
    returned the live (near-empty) session and cheerfully reported "nothing
    died mid-flight". The caller needs to see the alternatives.

    Every candidate is checked against the `cwd` recorded inside it: `mangle`
    collapses `/`, `.`, `_` and `-` alike, so distinct paths can share a
    project dir and the mangled dir alone is not proof of ownership.
    """
    target = os.path.abspath(cwd)
    found: list[str] = []

    primary = os.path.join(projects_dir, mangle(cwd))
    for f in _all_jsonl(primary):
        if _declares_cwd(f, target):
            found.append(f)

    if os.path.isdir(projects_dir):
        try:
            entries = list(os.scandir(projects_dir))
        except OSError:
            entries = []
        for entry in entries:
            if not entry.is_dir() or os.path.abspath(entry.path) == os.path.abspath(primary):
                continue
            for f in _all_jsonl(entry.path):
                if _declares_cwd(f, target):
                    found.append(f)

    return sorted(set(found), key=_mtime, reverse=True)


def find_session(cwd: str, projects_dir: str = PROJECTS_DIR, skip: int = 0) -> str | None:
    """The (skip)th newest transcript for `cwd`. skip=1 is "the previous one"."""
    sessions = find_sessions(cwd, projects_dir)
    return sessions[skip] if len(sessions) > skip else None


def _declares_cwd(path: str, target: str, probe_lines: int | None = None) -> bool:
    probe_lines = LIMITS["cwd_probe_lines"] if probe_lines is None else probe_lines
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
                if not isinstance(rec, dict):
                    continue
                c = rec.get("cwd")
                if c:
                    return os.path.abspath(c) == target
    except OSError:
        return False
    return False


def _assert_readable_regular(path: str) -> None:
    """Refuse anything that is not a regular file.

    A directory raises IsADirectoryError deep inside the reader and a FIFO
    blocks forever with no timeout; both surfaced as tracebacks against the
    documented "0 or 2" contract. Failing here keeps that contract true.
    """
    try:
        st = os.stat(path)
    except OSError as e:
        raise ValueError(f"cannot read {path}: {e.strerror}") from None
    if not stat.S_ISREG(st.st_mode):
        raise ValueError(f"not a regular file: {path}")


def load(path: str) -> tuple[list[dict], int]:
    """Parse a transcript -> (dict records, unusable line count).

    The count is NOT cosmetic. This tool runs after a crash, and a crash
    truncates the line it was mid-write on. If that line carried the terminal
    API error or a <task-notification>, dropping it silently yields a
    confident wrong answer. Evidence loss must be visible.

    Non-dict JSON is counted as unusable rather than kept: background-shell
    `.output` files are raw stdout, where a bare `381` from `wc -l` is valid
    JSON and became `'int' object has no attribute 'get'` on 11% of real
    files. Type is checked at the boundary, once.
    """
    _assert_readable_regular(path)
    recs: list[dict] = []
    bad = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    bad += 1
                    continue
                if isinstance(obj, dict):
                    recs.append(obj)
                else:
                    bad += 1
    except OSError as e:
        raise ValueError(f"cannot read {path}: {e.strerror}") from None
    return recs, bad


# ---------------------------------------------------------------- extraction

def _blocks(rec):
    if not isinstance(rec, dict):
        return
    msg = rec.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
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


def record_text(rec) -> str:
    return " ".join(_text_of(b) for b in _blocks(rec))


def find_spawns(recs: list[dict]) -> list[dict]:
    """Async workers: in-process agents AND background shells."""
    pending: dict[str, dict] = {}
    spawns: list[dict] = []
    for idx, rec in enumerate(recs):
        for b in _blocks(rec):
            if b.get("type") == "tool_use" and b.get("name") in AGENT_TOOLS + BG_TOOLS:
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                # The tool CALL is authoritative about intent; the result text
                # is not. A foreground Bash whose stdout merely contains
                # "Command running in background with ID: ..." — a grep over
                # this very corpus does exactly that — was classified as a live
                # background worker. Trust the input flag, not the echo.
                if b.get("name") in BG_TOOLS and not inp.get("run_in_background"):
                    continue
                if b.get("id") is None:
                    continue  # an id-less call cannot be paired with a result
                pending[b.get("id")] = {
                    "tool_use_id": b.get("id"),
                    "tool": b.get("name"),
                    "kind": "background-shell" if b.get("name") in BG_TOOLS else "agent",
                    "description": inp.get("description") or inp.get("name") or "",
                    "command": str(inp.get("command") or "")[:LIMITS["command_chars"]],
                    "prompt": inp.get("prompt") if isinstance(inp.get("prompt"), str) else "",
                    "subagent_type": inp.get("subagent_type") or "",
                    "spawned_at": (rec.get("timestamp") or "")[:19],
                    "index": idx,
                }
            elif b.get("type") == "tool_result":
                if b.get("tool_use_id") is None:
                    continue
                meta = pending.pop(b.get("tool_use_id"), None)
                if not meta:
                    continue
                s = _text_of(b)
                aid = out = None
                if ASYNC_LAUNCH_RE.search(s):
                    m, o = AGENT_ID_RE.search(s), OUTPUT_FILE_RE.search(s)
                    aid, out = (m.group(1) if m else None), (o.group(1) if o else None)
                elif BG_LAUNCH_RE.search(s):
                    m, o = BG_LAUNCH_RE.search(s), BG_OUTPUT_RE.search(s)
                    aid, out = m.group(1), (o.group(1) if o else None)
                else:
                    # Synchronous return: it already reported. Not in flight.
                    continue
                meta = dict(meta)
                meta["worker_id"] = aid
                meta["output_file"] = out
                spawns.append(meta)
    return spawns


def find_completions(recs: list[dict]) -> dict[str, dict]:
    """Completion notices, from EVERY record shape that carries them.

    Measured: in one production session the 37 notifications split
    queue-operation 23 / attachment 7 / user 7. Reading only
    message.content — the `user` shape — missed 37% of completions across the
    corpus and reported finished agents as dead, which is the wasteful
    outcome this skill's own anti-rationalization table names. The record is
    therefore searched whole rather than through one accessor.
    """
    done: dict[str, dict] = {}
    for rec in recs:
        # An ASSISTANT record containing this markup is prose ABOUT the format
        # — a transcript discussing it (this repo's own fixtures do) could
        # otherwise forge a completion. The harness emits notifications on
        # queue-operation / attachment / user records.
        if rec.get("type") == "assistant":
            continue
        try:
            text = json.dumps(rec)
        except (TypeError, ValueError):
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
                "status": (status.group(1) if status else "unknown").strip(),
                "summary": (summary.group(1) if summary else "").replace("\\n", " ")[:LIMITS["summary_chars"]],
                "tool_use_id": tu.group(1) if tu else None,
            }
    return done


def _termination_text(rec: dict) -> str:
    """Text that may legitimately testify to a termination.

    Anchored, not fuzzy. An error *pattern* is not an error: a tool_result
    echoing a ticket body about "529 Overloaded", or prose analysing past
    failures, must not be read as this session dying. Both were measured as
    real false positives.
    """
    if rec.get("isApiErrorMessage"):
        return record_text(rec)
    parts = []
    for b in _blocks(rec):
        if b.get("type") != "text":
            continue
        raw = b.get("text")
        t = raw.lstrip() if isinstance(raw, str) else ""
        if t and ERROR_PREFIX_RE.match(t):
            parts.append(t)
    return "\n".join(parts)


def find_termination(recs: list[dict], tail: int | None = None) -> dict:
    tail = LIMITS["termination_tail"] if tail is None else tail
    for rec in reversed(recs[-tail:]):
        text = _termination_text(rec)
        if not text.strip():
            continue
        for kind, pat in TERMINATION_SIGNATURES:
            m = pat.search(text)
            if m:
                ev, _ = redact(text[max(0, m.start() - 60): m.start() + LIMITS["evidence_chars"]])
                return {"kind": kind, "evidence": ev.replace("\n", " ").strip(),
                        "at": (rec.get("timestamp") or "")[:19]}
    # An api-error record we could not classify must NOT read as "ended
    # cleanly" — that is the wrap-up framing this skill exists to prevent.
    # Say "an error we do not recognise" and show it.
    for rec in reversed(recs[-tail:]):
        if rec.get("isApiErrorMessage"):
            ev, _ = redact(record_text(rec)[:220])
            return {"kind": "api_error_unclassified",
                    "evidence": ev.replace("\n", " ").strip(),
                    "at": (rec.get("timestamp") or "")[:19]}
    return {"kind": "clean_or_unknown", "evidence": "", "at": ""}


def _last_timestamp(recs: list[dict]) -> float | None:
    """Epoch seconds of the last timestamped record — when the session stopped."""
    for rec in reversed(recs):
        ts = rec.get("timestamp")
        if not ts:
            continue
        if not isinstance(ts, str):
            continue
        try:
            from datetime import datetime
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError, AttributeError):
            continue
    return None


# ---------------------------------------------------------------- recovery

def durable_transcript(session_path: str, worker_id: str | None) -> str | None:
    """A subagent's DURABLE transcript, if the harness kept one.

    The launch receipt's `output_file:` points into /private/tmp, which is
    exactly what a reboot or tmp-sweep removes — measured, 92% of unreported
    spawns reported "output file no longer on disk". The harness ALSO writes
    `<project>/<session-id>/subagents/agent-<id>.jsonl`, which survives; 509
    such files existed on the machine this was written on while the tmp copies
    were being reaped. Prefer the durable one.
    """
    if not worker_id:
        return None
    base, ext = os.path.splitext(session_path)
    if ext != ".jsonl":
        return None
    cand = os.path.join(base, "subagents", f"agent-{worker_id}.jsonl")
    if os.path.exists(cand):
        return cand
    # Workflow workers land under subagents/workflows/ — 160 artifacts across
    # 17 sessions here — so not searching it left the durable claim true for
    # plain agents only.
    import glob as _glob
    hits = _glob.glob(os.path.join(base, "subagents", "workflows", "**",
                                   f"agent-{worker_id}.jsonl"), recursive=True)
    return hits[0] if hits else None


def digest_output(path: str, max_chars: int | None = None,
                  tail_records: int | None = None) -> dict:
    """Bounded, redacted digest of a dead worker's surviving output.

    NEVER returns the whole file: these reach ~1.5 MB and the harness warns
    that reading one raw overflows the parent's context.
    """
    max_chars = LIMITS["digest_chars"] if max_chars is None else max_chars
    tail_records = LIMITS["digest_tail_records"] if tail_records is None else tail_records
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    if not path:
        return {"recoverable": False, "reason": "no output path recorded"}
    try:
        st = os.stat(path)
    except OSError:
        return {"recoverable": False, "reason": "output file no longer on disk"}
    if not stat.S_ISREG(st.st_mode):
        return {"recoverable": False, "reason": "output path is not a regular file"}
    if st.st_size == 0:
        return {"recoverable": False, "reason": "empty (worker produced nothing before dying)"}

    from collections import deque
    window: deque = deque(maxlen=tail_records)
    n_lines = 0
    plain: list[str] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                n_lines += 1
                line = line.rstrip("\n")
                if line.strip():
                    window.append(line)
    except OSError as e:
        return {"recoverable": False, "reason": str(e)}

    texts: list[str] = []
    tools: dict[str, int] = {}
    files: set[str] = set()
    for line in window:
        obj = None
        try:
            obj = json.loads(line.strip())
        except ValueError:
            pass
        if not isinstance(obj, dict):
            # Raw stdout (a background shell's log) — keep the line as prose.
            plain.append(line)
            continue
        if obj.get("type") == "assistant":
            for b in _blocks(obj):
                if b.get("type") == "text" and (b.get("text") or "").strip():
                    texts.append(b["text"].strip())
        for b in _blocks(obj):
            if b.get("type") == "tool_use":
                name = b.get("name") or "?"
                tools[name] = tools.get(name, 0) + 1
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                fp = inp.get("file_path") or inp.get("notebook_path")
                if fp:
                    files.add(str(fp))

    source = texts if texts else plain
    final = ""
    for t in reversed(source):
        if final and len(final) + len(t) + 2 > max_chars:
            break
        final = (t + "\n\n" + final) if final else t

    final, secrets = redact(final[:max_chars])
    return {
        "recoverable": bool(final or files or tools),
        "bytes": st.st_size,
        "records": n_lines,
        "shape": "transcript" if texts else "raw-stdout",
        "truncated_window": n_lines > tail_records,
        "final_text": final,
        "redacted": secrets,
        "tool_counts": dict(sorted(tools.items(), key=lambda kv: -kv[1])),
        # Bounded like final_text: 40 unbounded paths serialized to 16 KB in
        # a payload whose cap was advertised as 1200 chars.
        "files_touched": [f[:LIMITS["file_path_chars"]]
                          for f in sorted(files)[:LIMITS["files_listed"]]],
        "mtime_age_s": int(time.time() - st.st_mtime),
    }


def scan(session_path: str, max_chars: int | None = None,
         live_window_s: int | None = None) -> dict:
    max_chars = LIMITS["digest_chars"] if max_chars is None else max_chars
    live_window_s = LIMITS["live_window_s"] if live_window_s is None else live_window_s
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    recs, unparsable = load(session_path)
    spawns = find_spawns(recs)
    done = find_completions(recs)
    died_at = _last_timestamp(recs)

    by_tool_use = {v.get("tool_use_id"): v for v in done.values() if v.get("tool_use_id")}

    for s in spawns:
        wid = s.get("worker_id")
        info = done.get(wid) if wid else None
        if info is None:
            info = by_tool_use.get(s.get("tool_use_id"))
        if info:
            status = (info.get("status") or "unknown").lower()
            s["status"] = info.get("status")
            s["summary"] = info.get("summary")
            # A completion is not automatically an all-clear. A worker that
            # reported FAILURE reported — and still needs the operator's
            # attention, so it is not folded into the silent "reported" bucket.
            s["state"] = "reported" if status in OK_STATUSES else "reported_failed"
            if s["state"] == "reported_failed":
                durable = durable_transcript(session_path, s.get("worker_id"))
                s["durable_transcript"] = durable
                s["digest"] = digest_output(durable or s.get("output_file"),
                                            max_chars=max_chars)
        else:
            s["state"] = "unreported"
            durable = durable_transcript(session_path, s.get("worker_id"))
            s["durable_transcript"] = durable
            s["digest"] = digest_output(durable or s.get("output_file"),
                                        max_chars=max_chars)
            age = s["digest"].get("mtime_age_s")
            # Liveness is a property of the spawn KIND first. Agent/Task/
            # Workflow run in-process and cannot outlive the parent, so a
            # recent mtime on one of those means the PARENT died recently —
            # not that the worker lives. Flagging them was a guaranteed false
            # positive on fast resumes, which is when resumes happen.
            if s["tool"] in IN_PROCESS_TOOLS:
                s["liveness"] = "dead-with-parent"
            elif age is None:
                s["liveness"] = "unknown-no-output-file"
            else:
                # Measure against the session's death, not the wall clock: an
                # operator who takes ten minutes to restart must not turn every
                # dead worker into a "maybe alive".
                since_death = (time.time() - died_at) if died_at else None
                wrote_after_death = (
                    since_death is not None and age < since_death - 5
                )
                s["liveness"] = ("possibly-live" if (wrote_after_death or
                                 (since_death is None and age < live_window_s))
                                 else "dead")
            s["possibly_live"] = s["liveness"] == "possibly-live"
            s["recent_write_s"] = age

    return {
        "session": session_path,
        "records": len(recs),
        "unparsable_records": unparsable,
        "died_at_epoch": died_at,
        "termination": find_termination(recs),
        "spawns_total": len(spawns),
        "unreported": [s for s in spawns if s["state"] == "unreported"],
        "reported_failed": [s for s in spawns if s["state"] == "reported_failed"],
        "reported": [s for s in spawns if s["state"] == "reported"],
    }


# ---------------------------------------------------------------- rendering

def _emit_worker(out: list[str], s: dict, header: str) -> None:
    d = s.get("digest") or {}
    out.append("")
    label = s.get("description") or (s.get("command") or "")[:60] or "(no description)"
    out.append(f"• {header}  {s['tool']}  {label}")
    out.append(f"  spawned    : {s['spawned_at']}   kind: {s.get('kind')}   id: {s.get('worker_id')}")
    if s.get("subagent_type"):
        out.append(f"  type       : {s['subagent_type']}")
    if s.get("status"):
        out.append(f"  status     : {s['status']}   {s.get('summary','')}")
    live = s.get("liveness")
    if live == "possibly-live":
        out.append("  liveness   : ** POSSIBLY STILL RUNNING — a separate process that")
        out.append("               wrote AFTER the session died. Check before re-running:")
        out.append("               re-running a live deploy or migration is worse than waiting.")
    elif live == "dead-with-parent":
        out.append("  liveness   : dead — runs in-process, died with the parent")
    elif live == "unknown-no-output-file":
        out.append("  liveness   : ** UNKNOWN — no output file, so liveness cannot be")
        out.append("               determined. Verify before re-running anything with side effects.")
    if not d.get("recoverable"):
        out.append(f"  recovery   : NONE — {d.get('reason', 'no digest')}")
    else:
        out.append(f"  transcript : {d['bytes']:,}B / {d['records']} records ({d.get('shape')})"
                   f", last write {d['mtime_age_s']}s ago")
        if d.get("redacted"):
            out.append(f"  ** redacted secret-shaped values: {', '.join(sorted(set(d['redacted'])))}")
        if d.get("tool_counts"):
            tc = ", ".join(f"{k}×{v}" for k, v in list(d["tool_counts"].items())[:6])
            out.append(f"  did        : {tc}")
        if d.get("files_touched"):
            out.append(f"  files      : {', '.join(d['files_touched'][:6])}"
                       + (" …" if len(d["files_touched"]) > 6 else ""))
        if d.get("final_text"):
            out.append("  last words :")
            for ln in d["final_text"].splitlines()[:LIMITS["last_words_lines"]]:
                out.append(f"    | {ln[:110]}")
    out.append("  triage     : does the above show the work FINISHED (fold in, do not")
    out.append("               re-spawn), PARTIAL (re-spawn the remainder), or too little")
    out.append("               to tell (re-spawn from the prompt)? — SKILL.md step 4")
    if s.get("prompt"):
        # Round 1 cut this at 2,000 chars silently. Round 2 cut it at 880 (8
        # lines x 110) and LABELLED IT COMPLETE, and a test asserted the word
        # "complete" — so the suite pinned the false claim. Measured: 46 of 46
        # real prompts exceeded that budget, so the label was wrong every
        # single time. Either it is whole, or the render says it is not.
        prompt = s["prompt"]
        budget = LIMITS["prompt_render_chars"]
        shown = prompt[:budget]
        if len(prompt) <= budget:
            out.append(f"  orig prompt ({len(prompt)} chars, complete):")
        else:
            out.append(f"  orig prompt ({len(prompt)} chars, TRUNCATED to {budget} "
                       f"for display — re-spawn from --json, which carries it whole):")
        for ln in shown.splitlines():
            out.append(f"    > {ln}")
        if len(prompt) > budget:
            out.append(f"    > [... {len(prompt) - budget} more chars — use --json ...]")
    elif s.get("command"):
        out.append(f"  command    : {s['command'][:200]}")


def render(result: dict) -> str:
    out: list[str] = []
    term = result["termination"]
    out.append("=" * 68)
    out.append("RESUME SCAN")
    out.append("=" * 68)
    out.append(f"session      : {result['session']}")
    out.append(f"records      : {result['records']}")

    if result["records"] == 0:
        out.append("")
        out.append("** NO PARSEABLE RECORDS. This is not an all-clear — it means the scan")
        out.append("   could read nothing. Wrong file, wrong format, or a transcript")
        out.append("   destroyed by the crash. Do NOT conclude the arc from this.")
        if result.get("unparsable_records"):
            out.append(f"   ({result['unparsable_records']} unusable line(s) seen.)")
        return "\n".join(out)

    if result.get("unparsable_records"):
        out.append(f"  ** {result['unparsable_records']} UNUSABLE record(s) — evidence may be missing.")
        out.append("     A crash truncates the line it was writing. If that line held the")
        out.append("     terminal error or a completion notice, what follows is incomplete")
        out.append("     rather than wrong. Treat an absence here as unknown, not as clear.")

    out.append(f"terminated   : {term['kind']}" + (f"  @ {term['at']}" if term["at"] else ""))
    if term["evidence"]:
        out.append(f"  evidence   : {term['evidence'][:200]}")
    out.append("")
    out.append(f"async workers: {result['spawns_total']}  "
               f"({len(result['reported'])} reported ok, "
               f"{len(result['reported_failed'])} REPORTED FAILURE, "
               f"{len(result['unreported'])} UNREPORTED)")

    if not result["unreported"] and not result["reported_failed"]:
        out.append("")
        out.append("No unreported or failed workers in THIS session. Continue the arc from")
        out.append("the last completed step. (This is not a signal to wrap up.)")
        others = result.get("other_sessions") or []
        if len(others) > 1 and result["spawns_total"] == 0:
            out.append("")
            out.append("** This session shows no workers at all. If the crash dropped you into")
            out.append("   a FRESH session, the one that died is a different file. Re-run with")
            out.append("   --previous, or --list-sessions to choose:")
            for c in others[1:4]:
                out.append(f"     {c}")
        return "\n".join(out)

    if result["reported_failed"]:
        out.append("")
        out.append("-" * 68)
        out.append("REPORTED FAILURE — these came back, and came back broken.")
        out.append("-" * 68)
        for s in result["reported_failed"]:
            _emit_worker(out, s, "FAILED")

    if result["unreported"]:
        out.append("")
        out.append("-" * 68)
        out.append("UNREPORTED — these never returned. Recover, then re-spawn what is dead.")
        out.append("-" * 68)
        for s in result["unreported"]:
            _emit_worker(out, s, "UNREPORTED")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reconstruct an arc that died mid-flight.")
    ap.add_argument("--session", help="path to a session .jsonl (default: newest for --cwd)")
    ap.add_argument("--cwd", default=os.getcwd(), help="working dir whose session to find")
    ap.add_argument("--projects-dir", default=PROJECTS_DIR)
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    ap.add_argument("--max-chars", type=int, default=LIMITS["digest_chars"],
                    help="hard cap on recovered text per worker (must be >= 1)")
    ap.add_argument("--live-window", type=int, default=LIMITS["live_window_s"],
                    help="seconds of recent output that may indicate a live process")
    ap.add_argument("--previous", action="store_true",
                    help="scan the session BEFORE the newest — use when the crash "
                         "dropped you into a fresh session, so the newest transcript "
                         "is the one you are sitting in rather than the one that died")
    ap.add_argument("--list-sessions", action="store_true",
                    help="list every transcript for this cwd, newest first, and exit")
    args = ap.parse_args(argv)

    if args.max_chars < 1:
        print("resume_scan: --max-chars must be >= 1", file=sys.stderr)
        return 2
    if args.live_window < 0:
        print("resume_scan: --live-window must be >= 0", file=sys.stderr)
        return 2

    candidates = [] if args.session else find_sessions(args.cwd, args.projects_dir)
    if args.list_sessions:
        if not candidates:
            print(f"resume_scan: no session transcript found for {args.cwd}", file=sys.stderr)
            return 2
        for i, c in enumerate(candidates):
            age = int(time.time() - _mtime(c))
            print(f"[{i}] {c}   (last write {age}s ago)"
                  + ("   <- default" if i == 0 else "   <- --previous" if i == 1 else ""))
        return 0

    if args.session and (args.previous or args.list_sessions):
        print("resume_scan: --session overrides --previous/--list-sessions",
              file=sys.stderr)
    session = args.session or (candidates[args.previous:] or [None])[0]
    if not session:
        which = "previous session" if args.previous else "session transcript"
        print(f"resume_scan: no {which} found for {args.cwd}", file=sys.stderr)
        return 2
    try:
        result = scan(session, max_chars=args.max_chars, live_window_s=args.live_window)
    except ValueError as e:
        print(f"resume_scan: {e}", file=sys.stderr)
        return 2

    if not args.json and len(candidates) > 1:
        result["other_sessions"] = candidates[:5]
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
