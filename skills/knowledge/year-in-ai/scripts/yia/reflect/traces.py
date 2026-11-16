"""Per-session metadata and tool traces, read from the same stores as the ledger.

The ledger readers keep only prompts and final replies. An episode also needs
where the work happened (directory, repository, branch), what was invoked
(skills, slash commands, tools), where the person interrupted the agent, and
which pull requests the harness itself linked. This module reads those for the
sessions an episode needs, and nothing else.

Like :mod:`yia.ledger.sources`, it finds files only through ``list_files``,
reads them only through ``read_lines``/``read_text``, checks roots with
``present`` and chooses between live and archived copies with ``pick_copies``;
every failure goes through ``SourceReport.skip``. ``tests/test_reflect.py``
holds this module to the same structural rule as the readers.

Session keys match the ledger's: the opaque hash of the id each reader passes
as ``session`` (a Claude transcript's file stem, a Codex rollout's id, a T3
thread id, a Conductor session id, a bridged session id).
"""

from __future__ import annotations

import collections
import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..ledger import ext_str, opaque
from ..ledger.sources import (
    SourceReport,
    _iso,
    _ro_sqlite,
    list_files,
    pick_copies,
    present,
    read_lines,
    read_text,
)

#: Slash commands that are housekeeping, not a choice of workflow.
TRIVIAL_COMMANDS = {
    "/clear", "/compact", "/model", "/mcp", "/exit", "/login", "/logout", "/resume", "/usage", "/cost",
    "/config", "/status", "/help", "/rename", "/context", "/doctor", "/permissions", "/memory", "/ide",
    "/vim", "/terminal-setup", "/hooks", "/agents", "/plugin", "/add-dir", "/init", "/statusline",
    "/fast", "/effort", "/output-style",
}

#: Most trace events kept per session before sampling.
MAX_EVENTS = 400

_COMMAND_NAME = re.compile(r"<command-name>\s*(/[^<\s]+)\s*</command-name>")
_EXIT = re.compile(r"(?:Exit code:?|exit_code\"?:)\s*(-?[0-9]+)")


def new_meta() -> dict:
    return {
        "cwd": None, "repo": None, "branch": None, "title": None, "project": None,
        "prs": {},  # url -> {"state": ..., "title": ...}
        "skills": collections.Counter(), "commands": collections.Counter(),
        "tools": 0, "tool_errors": 0, "interrupts": [], "subagents": 0,
        "events": [],  # [ts, label, error]
    }


def _short(value, n: int = 110) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _tail_path(value) -> str:
    if not isinstance(value, str):
        return ""
    parts = [p for p in value.split("/") if p]
    return "/".join(parts[-2:])


def tool_label(name: str, args) -> str:
    """A one-line label for a tool call: the tool and the argument that says what it did."""
    args = args if isinstance(args, dict) else {}
    if name in ("Bash", "exec_command", "shell", "local_shell"):
        cmd = args.get("command") or args.get("cmd")
        if isinstance(cmd, list):
            cmd = " ".join(str(c) for c in cmd[-1:])
        return f"$ {_short(cmd or '', 100)}"
    if name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        return f"{name} {_tail_path(args.get('file_path') or args.get('notebook_path'))}"
    if name == "Skill":
        return f"Skill {ext_str(args.get('skill')) or ''}"
    if name in ("Agent", "Task"):
        return f"{name}: {_short(args.get('description') or args.get('subagent_type') or '', 70)}"
    if name in ("Grep", "Glob"):
        return f"{name} {_short(args.get('pattern') or '', 60)}"
    for key in ("url", "query", "description", "title", "skill", "path"):
        if isinstance(args.get(key), str):
            return f"{name} {_short(args[key], 70)}"
    return name


def _event(meta: dict, ts: Optional[float], label: str, error: bool = False) -> None:
    meta["tools"] += 1
    if error:
        meta["tool_errors"] += 1
    events = meta["events"]
    if len(events) < MAX_EVENTS:
        events.append([ts, label, error])
    else:  # keep the head and a rolling tail
        events[MAX_EVENTS // 2:] = events[MAX_EVENTS // 2 + 1:] + [[ts, label, error]]


def repo_from_cwd(cwd: Optional[str]) -> Optional[str]:
    """A repository name from a working directory, with agent worktree suffixes removed."""
    if not cwd:
        return None
    path = re.sub(r"/\.(claude|codex|conductor)/worktrees/.*$", "", cwd)
    path = re.sub(r"/\.worktrees/.*$", "", path)
    match = re.search(r"/\.t3/worktrees/([^/]+)", path) or re.search(r"/dot-t3/worktrees/([^/]+)", path)
    if match:
        return match.group(1)
    parts = [p for p in path.split("/") if p]
    return parts[-1] if parts else None


def _repo_from_url(url: Optional[str]) -> Optional[str]:
    if not isinstance(url, str) or not url:
        return None
    name = url.rstrip("/").split("/")[-1].split(":")[-1]
    return name[:-4] if name.endswith(".git") else name


# ----------------------------------------------------------------- Claude Code


def claude_meta(path: Path, report: SourceReport) -> dict:
    meta = new_meta()
    branches: collections.Counter = collections.Counter()
    pending: Dict[str, int] = {}
    for line in read_lines(path, report):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("isSidechain"):
            continue
        kind = rec.get("type")
        if kind == "pr-link":
            url = ext_str(rec.get("prUrl"))
            if url and url.startswith("https://"):
                meta["prs"].setdefault(url, {"state": None, "title": None})
            continue
        if kind == "ai-title" and isinstance(rec.get("aiTitle"), str):
            meta["title"] = rec["aiTitle"][:140]
            continue
        if kind not in ("user", "assistant"):
            continue
        cwd = ext_str(rec.get("cwd"))
        if cwd and cwd != "other" and not meta["cwd"]:
            meta["cwd"] = cwd
        branch = ext_str(rec.get("gitBranch"))
        if branch and branch not in ("HEAD", "other"):
            branches[branch] += 1
        ts = _iso(rec.get("timestamp"))
        message = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        content = message.get("content")
        if kind == "user":
            texts = [content] if isinstance(content, str) else [
                b.get("text") for b in content or [] if isinstance(b, dict) and isinstance(b.get("text"), str)
            ] if isinstance(content, list) else []
            for text in texts:
                if text.lstrip().startswith("[Request interrupted"):
                    meta["interrupts"].append(ts)
                for name in _COMMAND_NAME.findall(text):
                    if name not in TRIVIAL_COMMANDS:
                        meta["commands"][name] += 1
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                        index = pending.get(ext_str(block.get("tool_use_id")) or "")
                        meta["tool_errors"] += 1
                        if index is not None and index < len(meta["events"]):
                            meta["events"][index][2] = True
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = ext_str(block.get("name")) or "tool"
                args = block.get("input") if isinstance(block.get("input"), dict) else {}
                if name == "Skill" and isinstance(args.get("skill"), str):
                    meta["skills"][args["skill"]] += 1
                if name in ("Agent", "Task"):
                    meta["subagents"] += 1
                _event(meta, ts, tool_label(name, args))
                pending[ext_str(block.get("id")) or ""] = len(meta["events"]) - 1
    if branches:
        meta["branch"] = branches.most_common(1)[0][0]
    meta["repo"] = repo_from_cwd(meta["cwd"])
    return meta


# ----------------------------------------------------------------------- Codex


def codex_meta(path: Path, report: SourceReport) -> dict:
    meta = new_meta()
    for line in read_lines(path, report):
        if '"session_meta"' not in line and '"response_item"' not in line and '"event_msg"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        ts = _iso(rec.get("timestamp"))
        if rec.get("type") == "session_meta":
            meta["cwd"] = ext_str(payload.get("cwd"))
            git = payload.get("git") if isinstance(payload.get("git"), dict) else {}
            meta["branch"] = ext_str(git.get("branch"))
            meta["repo"] = _repo_from_url(git.get("repository_url")) or repo_from_cwd(meta["cwd"])
            continue
        kind = payload.get("type")
        if kind in ("function_call", "custom_tool_call"):
            name = ext_str(payload.get("name")) or "tool"
            raw = payload.get("arguments") if kind == "function_call" else payload.get("input")
            try:
                args = json.loads(raw) if isinstance(raw, str) and raw.startswith("{") else {}
            except ValueError:
                args = {}
            label = tool_label(name, args) if args else f"{name} {_short(raw or '', 90)}"
            _event(meta, ts, label)
        elif kind in ("function_call_output", "custom_tool_call_output"):
            match = _EXIT.search(_short(payload.get("output") or "", 400))
            if match and match.group(1) != "0" and meta["events"]:
                meta["events"][-1][2] = True
                meta["tool_errors"] += 1
        elif kind == "turn_aborted":
            meta["interrupts"].append(ts)
    return meta


# -------------------------------------------------------------------------- T3


def t3_meta(db: Path, wanted: Set[str], report: SourceReport) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    try:
        con = _ro_sqlite(db)
        projects = {pid: (title, root) for pid, title, root in
                    con.execute("select project_id, title, workspace_root from projection_projects")}
        threads = []
        for tid, pid, title, payload in con.execute(
                "select thread_id, project_id, title, payload_json from orchestration_v2_projection_threads"):
            if opaque(str(tid)) in wanted:
                threads.append((tid, pid, title, payload))
        for tid, pid, title, payload in threads:
            meta = new_meta()
            try:
                data = json.loads(payload) if isinstance(payload, str) else {}
            except ValueError:
                data = {}
            data = data if isinstance(data, dict) else {}
            meta["title"] = ext_str(title)
            meta["branch"] = ext_str(data.get("branch"))
            meta["cwd"] = ext_str(data.get("worktreePath"))
            project_title, root = projects.get(pid, (None, None))
            meta["project"] = ext_str(project_title)
            meta["repo"] = repo_from_cwd(ext_str(root)) or repo_from_cwd(meta["cwd"])
            prs = data.get("pullRequests") if isinstance(data.get("pullRequests"), list) else []
            linked = data.get("linkedPullRequest")
            for pr in prs + ([linked] if isinstance(linked, dict) else []):
                if not isinstance(pr, dict) or not isinstance(pr.get("url"), str):
                    continue
                snap = pr.get("snapshot") if isinstance(pr.get("snapshot"), dict) else {}
                meta["prs"][pr["url"]] = {"state": ext_str(snap.get("state")), "title": ext_str(snap.get("title")),
                                          "branch": ext_str(snap.get("headBranch"))}
            for kind, status, updated, item in con.execute(
                    "select type, status, updated_at, payload_json from orchestration_v2_projection_turn_items "
                    "where thread_id = ? and type in ('command_execution','dynamic_tool','file_change','error',"
                    "'subagent','run_interrupt_request','web_search') order by ordinal", (tid,)):
                try:
                    item = json.loads(item) if isinstance(item, str) else {}
                except ValueError:
                    item = {}
                item = item if isinstance(item, dict) else {}
                ts = _iso(item.get("startedAt")) or _iso(updated)
                failed = status == "failed"
                if kind == "run_interrupt_request":
                    meta["interrupts"].append(ts)
                elif kind == "command_execution":
                    cmd = item.get("input") if isinstance(item.get("input"), str) else item.get("title")
                    code = item.get("exitCode")
                    error = failed or (isinstance(code, int) and not isinstance(code, bool) and code != 0)
                    _event(meta, ts, f"$ {_short(cmd or '', 100)}", error)
                elif kind == "dynamic_tool":
                    name = ext_str(item.get("toolName")) or "tool"
                    raw = item.get("input")
                    args = {}
                    if isinstance(raw, str) and raw.startswith("{"):
                        try:
                            args = json.loads(raw)
                        except ValueError:
                            args = {}
                    elif isinstance(raw, dict):
                        args = raw
                    if name == "Skill" and isinstance(args.get("skill"), str):
                        meta["skills"][args["skill"]] += 1
                    _event(meta, ts, tool_label(name, args) if args else f"{name} {_short(item.get('title') or '', 70)}",
                           failed)
                elif kind == "file_change":
                    _event(meta, ts, f"edit {_tail_path(item.get('fileName'))}", failed)
                elif kind == "error":
                    _event(meta, ts, f"error: {_short(item.get('title') or '', 90)}", True)
                elif kind == "subagent":
                    meta["subagents"] += 1
                    _event(meta, ts, f"subagent: {_short(item.get('title') or '', 70)}", failed)
                elif kind == "web_search":
                    _event(meta, ts, f"web search {_short(item.get('title') or '', 70)}", failed)
            out[opaque(str(tid))] = meta
        con.close()
    except sqlite3.Error as exc:
        report.skip(f"T3 database unreadable: {exc}")
    return out


# ------------------------------------------------------------------- Conductor


def conductor_meta(db: Path, wanted: Set[str], report: SourceReport) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    try:
        con = _ro_sqlite(db)
        rows = con.execute(
            "select s.id, s.title, w.branch, w.workspace_path, w.directory_name, r.name, r.remote_url "
            "from sessions s left join workspaces w on w.id = s.workspace_id "
            "left join repos r on r.id = w.repository_id")
        for sid, title, branch, wpath, dirname, repo, remote in rows:
            if opaque(str(sid)) not in wanted:
                continue
            meta = new_meta()
            meta["title"] = ext_str(title)
            meta["branch"] = ext_str(branch)
            meta["cwd"] = ext_str(wpath) or ext_str(dirname)
            meta["repo"] = ext_str(repo) or _repo_from_url(remote) or repo_from_cwd(meta["cwd"])
            out[opaque(str(sid))] = meta
        con.close()
    except sqlite3.Error as exc:
        report.skip(f"Conductor database unreadable: {exc}")
    return out


# --------------------------------------------------------------------- Bridged


def bridged_meta(roots: List[Path], wanted: Set[str], report: SourceReport) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for root in roots:
        for path in list_files(root, report, depth=1):
            if not (path.name.startswith("session-") and path.suffix == ".md"):
                continue
            body = read_text(path, report)
            if body is None:
                continue
            report.files += 1
            head = body[:3000]
            sid = re.search(r"^session_id: (\S+)", head, re.M)
            key = opaque(sid.group(1) if sid else path.stem)
            if key not in wanted or key in out:
                continue
            meta = new_meta()
            branch = re.search(r"^branch: (\S+)", head, re.M)
            project = re.search(r"^project: (\S+)", head, re.M)
            meta["branch"] = branch.group(1) if branch else None
            meta["project"] = project.group(1) if project else None
            meta["repo"] = meta["project"]
            out[key] = meta
    return out


# ------------------------------------------------------------------------ all


def merge(into: dict, other: dict) -> dict:
    """Combine two metas of one session (a transcript and its bridged or T3 view)."""
    for key in ("cwd", "repo", "branch", "title", "project"):
        into[key] = into[key] or other[key]
    for url, info in other["prs"].items():
        current = into["prs"].setdefault(url, dict(info))
        for k, v in info.items():
            current[k] = current.get(k) or v
    into["skills"].update(other["skills"])
    into["commands"].update(other["commands"])
    for key in ("tools", "tool_errors", "subagents"):
        into[key] += other[key]
    into["interrupts"] += other["interrupts"]
    if len(other["events"]) > len(into["events"]):
        into["events"] = other["events"]
    return into


def session_meta(roots: Dict[str, List[Path]], wanted: Set[str]) -> (Dict[str, dict], List[dict]):
    """Metadata for every wanted session key, and one report per store read."""
    metas: Dict[str, dict] = {}
    reports: List[SourceReport] = []

    def add(key: str, meta: dict) -> None:
        metas[key] = merge(metas[key], meta) if key in metas else meta

    claude_roots, blocked = present(roots.get("claude_projects", []), "dir")
    report = SourceReport("claude_code", bool(claude_roots or blocked))
    for _ in range(blocked):
        report.skip("store not accessible")

    def claude_candidates(root: Path):
        for path in list_files(root, report, depth=2):
            if path.suffix == ".jsonl" and opaque(path.stem) in wanted:
                yield path.stem, path

    for sid, path in pick_copies(claude_roots, claude_candidates, report, None, append_only=True):
        report.files += 1
        add(opaque(sid), claude_meta(path, report))
    reports.append(report)

    codex_roots, blocked = present(roots.get("codex_sessions", []), "dir")
    report = SourceReport("codex", bool(codex_roots or blocked))
    for _ in range(blocked):
        report.skip("store not accessible")

    def codex_candidates(root: Path):
        for path in list_files(root, report):
            name = path.name
            if ".jsonl" not in name:
                continue
            base = name[: -len(".zst")] if name.endswith(".zst") else name
            if opaque(base.split(".")[0][-36:]) in wanted:
                yield base, path

    for base, path in pick_copies(codex_roots, codex_candidates, report, None, append_only=True):
        report.files += 1
        add(opaque(base.split(".")[0][-36:]), codex_meta(path, report))
    reports.append(report)

    for key, store, reader in (("t3_db", "t3", t3_meta), ("conductor_db", "conductor", conductor_meta)):
        found, blocked = present(roots.get(key, []), "file")
        report = SourceReport(store, bool(found or blocked))
        for _ in range(blocked):
            report.skip("store not accessible")
        for db in found:
            report.files += 1
            for sess, meta in reader(db, wanted, report).items():
                add(sess, meta)
        reports.append(report)

    found, blocked = present(roots.get("bridged", []), "dir")
    report = SourceReport("bridged", bool(found or blocked))
    for _ in range(blocked):
        report.skip("store not accessible")
    for sess, meta in bridged_meta(found, wanted, report).items():
        add(sess, meta)
    reports.append(report)
    return metas, [r.to_dict() for r in reports]
