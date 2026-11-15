"""Turn readers: each store's prompts and final replies as ledger rows.

Every reader returns ``(SourceReport, iterator of rows)`` and tolerates a
missing store, a locked database or a torn last line. The report fills in as
the iterator is consumed.

Attribution is the hard part, and each store answers it differently:

* T3 records ``createdBy`` on every user message, so its authors are exact.
* Claude Code records an ``entrypoint``: ``cli`` is a person at a terminal,
  ``sdk-cli`` is ``claude -p``, ``sdk-ts`` is an app driving the SDK.
* Codex records an ``originator`` and a ``source``; ``codex_exec`` is a script.
* The bridge markdown and exported datasets record no author at all; their
  rows are ``unknown`` and the fold filters them.

A reply is the last assistant text before the next prompt of the same turn.
"""

from __future__ import annotations

import datetime as _dt
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from ..model import SourceReport
from . import harness_label, is_injected, make_row, unwrap_command

Rows = Iterator[dict]

_UTC = _dt.timezone.utc


def _iso(raw: str) -> Optional[float]:
    if not raw:
        return None
    text = raw.strip().replace(" ", "T", 1) if "T" not in raw else raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.timestamp()


def _observe(report: SourceReport, ts: float) -> None:
    report.observe(_dt.datetime.fromtimestamp(ts, _UTC))


def _absent(name: str, reason: str) -> Tuple[SourceReport, Rows]:
    return SourceReport(name, False, reason=reason), iter(())


def _ro_sqlite(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)


# --------------------------------------------------------------------------- T3


def read_t3(db: Optional[Path], since: Optional[float]) -> Tuple[SourceReport, Rows]:
    """T3's orchestration store. Subagent threads are skipped; their prompts are agent traffic."""
    name = "t3"
    if db is None or not db.is_file():
        return _absent(name, "no T3 state database on this machine")
    report = SourceReport(name, True, root=str(db))

    def stream() -> Rows:
        try:
            con = _ro_sqlite(db)
            threads = {
                tid: (lin or "top", prov)
                for tid, lin, prov in con.execute(
                    "select thread_id, json_extract(payload_json,'$.lineage.relationshipToParent'), "
                    "default_provider from orchestration_v2_projection_threads"
                )
            }
            cutoff = (
                _dt.datetime.fromtimestamp(since, _UTC).strftime("%Y-%m-%dT%H:%M:%S") if since else ""
            )
            rows = con.execute(
                "select thread_id, run_id, role, created_at, json_extract(payload_json,'$.createdBy'), "
                "json_extract(payload_json,'$.creationSource'), json_extract(payload_json,'$.text') "
                "from orchestration_v2_projection_messages where streaming=0 and created_at >= ? "
                "order by created_at",
                (cutoff,),
            )
        except sqlite3.Error as exc:
            report.available = False
            report.reason = f"T3 database unreadable: {exc}"
            return
        report.files = 1
        runs: Dict[Tuple[str, str], dict] = {}
        for thread, run, role, created, created_by, creation_source, text in rows:
            lineage, provider = threads.get(thread, ("top", None))
            if lineage == "subagent" or not text:
                continue
            ts = _iso(created)
            if ts is None:
                continue
            _observe(report, ts)
            harness = harness_label("t3", provider, "provider")
            state = runs.setdefault((thread, run), {"prompt": None, "author": None, "last": None})
            if role == "user":
                if is_injected(text):
                    continue
                author = "human" if created_by == "user" else "agent"
                row = make_row(
                    src=name, harness=harness, kind="prompt", ts=ts, text=text, session=thread,
                    author=author, attr={"created_by": created_by, "creation_source": creation_source,
                                         "lineage": lineage},
                )
                if state["prompt"] is None:
                    state["prompt"], state["author"] = row["id"], author
                yield row
            elif role == "assistant":
                state["last"] = (ts, text, harness)
        for (thread, _run), state in runs.items():
            if state["last"] and state["prompt"]:
                ts, text, harness = state["last"]
                yield make_row(src=name, harness=harness, kind="reply", ts=ts, text=text, session=thread,
                               author=state["author"], turn=state["prompt"])
        con.close()

    return report, stream()



def pair_turns(events, *, src: str, session: Optional[str], harness, author, attr=None,
               report: Optional[SourceReport] = None) -> Rows:
    """Turn a time-ordered stream of ``(role, ts, text)`` into prompt and reply rows, incrementally.

    ``role`` is ``"prompt"`` or ``"reply"``. A reply row is the last reply text
    before the next prompt, tied to that prompt's row id. ``harness``,
    ``author`` and ``attr`` may be callables, evaluated at the first prompt, so
    a reader can classify a session from fields it only sees while streaming.
    Holds one pending reply in memory, never the session.
    """
    prompt_id = None
    final = None
    resolved = None
    for role, ts, text in events:
        if not text or not text.strip():
            continue
        if report is not None:
            _observe(report, ts)
        if role == "prompt":
            if resolved is None:
                resolved = (harness() if callable(harness) else harness,
                            author() if callable(author) else author,
                            attr() if callable(attr) else attr)
            if final and prompt_id:
                yield make_row(src=src, harness=resolved[0], kind="reply", ts=final[0], text=final[1],
                               session=session, author=resolved[1], turn=prompt_id)
            final = None
            row = make_row(src=src, harness=resolved[0], kind="prompt", ts=ts, text=text, session=session,
                           author=resolved[1], attr=resolved[2])
            prompt_id = row["id"]
            yield row
        elif prompt_id:
            final = (ts, text)
    if final and prompt_id:
        yield make_row(src=src, harness=resolved[0], kind="reply", ts=final[0], text=final[1], session=session,
                       author=resolved[1], turn=prompt_id)


# ---------------------------------------------------------------------- Conductor


def read_conductor(db: Optional[Path], since: Optional[float]) -> Tuple[SourceReport, Rows]:
    name = "conductor"
    if db is None or not db.is_file():
        return _absent(name, "no Conductor database on this machine")
    report = SourceReport(name, True, root=str(db))

    def stream() -> Rows:
        try:
            con = _ro_sqlite(db)
            rows = con.execute(
                "select session_id, role, content, created_at, turn_id from session_messages order by created_at"
            )
        except sqlite3.Error as exc:
            report.available = False
            report.reason = f"Conductor database unreadable: {exc}"
            return
        report.files = 1
        # The prompt each session is answering *now*. A reply belongs to the
        # prompt current when it was read, never to the session's last prompt.
        current: Dict[str, str] = {}
        last: Dict[str, Tuple[float, str, str]] = {}
        for session, role, content, created, _turn in rows:
            ts = _iso(created or "")
            if ts is None or (since and ts < since) or not content:
                continue
            _observe(report, ts)
            if role == "user":
                if is_injected(content):
                    continue
                row = make_row(src=name, harness="conductor", kind="prompt", ts=ts, text=content,
                               session=session, author="human")
                current[session] = row["id"]
                yield row
            elif role == "assistant" and session in current:
                try:
                    message = json.loads(content)
                except ValueError:
                    continue
                if not isinstance(message, dict) or message.get("type") != "assistant":
                    continue
                parts = (message.get("message") or {}).get("content") or []
                text = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
                if text.strip():
                    last[current[session]] = (ts, text, session)
        for prompt_id, (ts, text, session) in last.items():
            yield make_row(src=name, harness="conductor", kind="reply", ts=ts, text=text, session=session,
                           author="human", turn=prompt_id)
        con.close()

    return report, stream()


# --------------------------------------------------------------------- Claude Code

#: Entry points where a person types into the session.
CLAUDE_HUMAN_ENTRYPOINTS = {"cli", "claude-desktop", "claude-vscode"}


def paseo_session_ids(agents_dir: Optional[Path]) -> Set[str]:
    """Claude session ids that Paseo launched. Measured as orchestrator traffic, not typing."""
    ids: Set[str] = set()
    if agents_dir is None or not agents_dir.is_dir():
        return ids
    for path in agents_dir.glob("*/*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sid = (data.get("runtimeInfo") or {}).get("sessionId")
        if sid:
            ids.add(sid)
    return ids


def _claude_text(content) -> Optional[str]:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return None


def read_claude_projects(
    roots: List[Path], since: Optional[float], paseo_ids: Optional[Set[str]] = None
) -> Tuple[SourceReport, Rows]:
    """Claude Code transcripts. The largest copy of each session wins, so live and archived roots can overlap."""
    name = "claude_code"
    roots = [r for r in roots if r and r.is_dir()]
    if not roots:
        return _absent(name, "no Claude Code transcript directory on this machine")
    report = SourceReport(name, True, root=", ".join(str(r) for r in roots))
    paseo_ids = paseo_ids or set()

    def stream() -> Rows:
        files: Dict[str, Path] = {}
        for root in roots:
            for path in root.glob("*/*.jsonl"):
                try:
                    if since and path.stat().st_mtime < since:
                        continue
                    size = path.stat().st_size
                except OSError:
                    continue
                sid = path.stem
                if sid not in files or size > files[sid].stat().st_size:
                    files[sid] = path
        for sid, path in files.items():
            report.files += 1
            yield from _claude_session(path, sid, since, paseo_ids, report)

    return report, stream()


def _claude_session(path: Path, sid: str, since: Optional[float], paseo_ids: Set[str],
                    report: SourceReport) -> Rows:
    state = {"entry": None}

    def events():
        seen: Set[str] = set()
        try:
            handle = path.open("r", encoding="utf-8", errors="ignore")
        except OSError:
            return
        with handle:
            for line in handle:
                # Cheap pre-filter before parsing, independent of JSON spacing.
                if '"user"' not in line and '"assistant"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                state["entry"] = state["entry"] or rec.get("entrypoint")
                if rec.get("isSidechain") or rec.get("isMeta") or rec.get("isCompactSummary"):
                    continue
                uid = rec.get("uuid")
                if uid in seen:
                    continue
                seen.add(uid)
                ts = _iso(rec.get("timestamp") or "")
                if ts is None or (since and ts < since):
                    continue
                text = _claude_text((rec.get("message") or {}).get("content"))
                if not text or not text.strip():
                    continue
                if rec.get("type") == "user":
                    if is_injected(text):
                        continue
                    typed = unwrap_command(text)
                    if typed is None:
                        continue
                    yield "prompt", ts, typed
                else:
                    yield "reply", ts, text

    def classify():
        entry = state["entry"]
        if sid in paseo_ids:
            return "paseo", "agent"
        if entry in CLAUDE_HUMAN_ENTRYPOINTS:
            return "claude-cli", "human"
        return harness_label("claude", entry or "unknown", "entrypoint"), ("agent" if entry == "sdk-cli" else "unknown")

    yield from pair_turns(events(), src="claude_code", session=sid, report=report,
                          harness=lambda: classify()[0], author=lambda: classify()[1],
                          attr=lambda: {"entrypoint": state["entry"]})


def read_claude_history(path: Optional[Path], since: Optional[float]) -> Tuple[SourceReport, Rows]:
    """Prompts typed into the interactive Claude Code CLI, kept long after transcripts are pruned."""
    name = "claude_history"
    if path is None or not path.is_file():
        return _absent(name, "no Claude Code prompt history on this machine")
    report = SourceReport(name, True, root=str(path), files=1)

    def stream() -> Rows:
        seen: Set[Tuple] = set()
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                stamp = rec.get("timestamp")
                if not isinstance(stamp, (int, float)):
                    continue
                ts = stamp / 1000.0
                if since and ts < since:
                    continue
                display = rec.get("display") or ""
                # A menu-bar usage probe sends /usage every few minutes; it is nobody typing.
                if "CodexBar" in (rec.get("project") or ""):
                    continue
                if display.strip().startswith("/") and len(display) < 60:
                    continue
                key = (rec.get("sessionId"), display, int(ts))
                if key in seen:
                    continue
                seen.add(key)
                _observe(report, ts)
                pasted = [v.get("content") or "" for v in (rec.get("pastedContents") or {}).values()
                          if isinstance(v, dict)]
                full = "\n".join([display] + pasted)
                typed = len(re.sub(r"\[Pasted text[^\]]*\]", "", display).strip())
                yield make_row(src=name, harness="claude-cli", kind="prompt", ts=ts, text=full,
                               session=rec.get("sessionId"), author="human", authored=min(typed, 4000))

    return report, stream()


# --------------------------------------------------------------------------- Codex

#: Codex originators that are a script or another app, never a person in Codex itself.
CODEX_NOT_INTERACTIVE = {"codex_exec", "T3 Code", "t3code_desktop", "codex_sdk_ts"}


def _codex_lines(path: Path) -> Iterator[str]:
    """Stream a rollout line by line, decompressing ``.zst`` through a pipe."""
    if path.name.endswith(".zst"):
        zstd = shutil.which("zstd")
        if not zstd:
            return
        try:
            proc = subprocess.Popen([zstd, "-dc", str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return
        try:
            for raw in proc.stdout:
                yield raw.decode("utf-8", errors="ignore")
        finally:
            proc.stdout.close()
            proc.wait()
        return
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            yield from handle
    except OSError:
        return


def read_codex_sessions(roots: List[Path], since: Optional[float]) -> Tuple[SourceReport, Rows]:
    name = "codex"
    roots = [r for r in roots if r and r.is_dir()]
    if not roots:
        return _absent(name, "no Codex session directory on this machine")
    report = SourceReport(name, True, root=", ".join(str(r) for r in roots))

    def stream() -> Rows:
        seen: Set[str] = set()
        for root in roots:
            for dirpath, _dirs, names in os.walk(root):
                for fname in names:
                    if ".jsonl" not in fname:
                        continue
                    sid = fname.split(".")[0][-36:]
                    if sid in seen:
                        continue
                    path = Path(dirpath) / fname
                    try:
                        if since and path.stat().st_mtime < since:
                            continue
                    except OSError:
                        continue
                    seen.add(sid)
                    report.files += 1
                    yield from _codex_file(path, sid, since, report)

    return report, stream()


def _codex_file(path: Path, sid: str, since: Optional[float], report: SourceReport) -> Rows:
    lines = _codex_lines(path)
    meta: Optional[dict] = None
    # session_meta is the first record; read up to it, then stream the rest.
    for line in lines:
        if '"session_meta"' in line:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") == "session_meta":
                meta = rec.get("payload") or {}
                break
    if not meta:
        return
    source = meta.get("source")
    if not isinstance(source, str):
        for _ in lines:  # drain, so the decompressor exits cleanly
            pass
        return  # a subagent spawned by another Codex thread
    originator = meta.get("originator") or ""
    if originator in CODEX_NOT_INTERACTIVE or source not in ("vscode", "cli"):
        author = "agent" if originator == "codex_exec" or source == "exec" else "unknown"
    else:
        author = "human"

    def events():
        for line in lines:
            if '"event_msg"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") != "event_msg":
                continue
            ts = _iso(rec.get("timestamp") or "")
            if ts is None or (since and ts < since):
                continue
            payload = rec.get("payload") or {}
            kind = payload.get("type")
            if kind == "user_message":
                yield "prompt", ts, payload.get("message") or ""
            elif kind == "agent_message":
                yield "reply", ts, payload.get("message") or ""
            elif kind == "task_complete" and payload.get("last_agent_message"):
                yield "reply", ts, payload["last_agent_message"]

    yield from pair_turns(events(), src="codex", session=sid, report=report,
                          harness=harness_label("codex", originator, "originator"), author=author,
                          attr={"originator": originator, "source": source})


def read_codex_history(path: Optional[Path], since: Optional[float]) -> Tuple[SourceReport, Rows]:
    """Prompts typed into the Codex TUI. Reaches back further than rollouts survive."""
    name = "codex_history"
    if path is None or not path.is_file():
        return _absent(name, "no Codex prompt history on this machine")
    report = SourceReport(name, True, root=str(path), files=1)

    def stream() -> Rows:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ts = rec.get("ts")
                text = rec.get("text") or ""
                if not isinstance(ts, (int, float)) or (since and ts < since) or not text.strip():
                    continue
                _observe(report, ts)
                yield make_row(src=name, harness="codex:history", kind="prompt", ts=float(ts), text=text,
                               session=rec.get("session_id"), author="human")

    return report, stream()


# -------------------------------------------------------------------------- Gemini


def read_gemini(roots: List[Path], since: Optional[float]) -> Tuple[SourceReport, Rows]:
    name = "gemini"
    roots = [r for r in roots if r and r.is_dir()]
    if not roots:
        return _absent(name, "no Gemini CLI chat directory on this machine")
    report = SourceReport(name, True, root=", ".join(str(r) for r in roots))

    def stream() -> Rows:
        for root in roots:
            for path in sorted(root.glob("*/chats/*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                report.files += 1
                sid = data.get("sessionId") or path.stem
                prompt_id = None
                final = None
                for msg in data.get("messages") or []:
                    ts = _iso(msg.get("timestamp") or "")
                    content = msg.get("content")
                    if isinstance(content, list):
                        content = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
                    if ts is None or (since and ts < since) or not content:
                        continue
                    _observe(report, ts)
                    if msg.get("type") == "user":
                        if final and prompt_id:
                            yield make_row(src=name, harness="gemini-cli", kind="reply", ts=final[0],
                                           text=final[1], session=sid, author="human", turn=prompt_id)
                        final = None
                        row = make_row(src=name, harness="gemini-cli", kind="prompt", ts=ts, text=content,
                                       session=sid, author="human")
                        prompt_id = row["id"]
                        yield row
                    elif msg.get("type") == "gemini" and prompt_id:
                        final = (ts, content)
                if final and prompt_id:
                    yield make_row(src=name, harness="gemini-cli", kind="reply", ts=final[0], text=final[1],
                                   session=sid, author="human", turn=prompt_id)

    return report, stream()


# ---------------------------------------------------------- Bridged markdown sessions

_BRIDGE_HEADER = re.compile(r"^> \[!(?:quote|info)\] \*\*(User|Assistant)\*\*(?: \((\d\d):(\d\d)\))?")


def read_bridged(
    roots: List[Path], since: Optional[float], utc_offset_hours: float = -5.0
) -> Tuple[SourceReport, Rows]:
    """Session transcripts rendered to markdown by a conversation bridge.

    The markdown keeps every turn but not who typed it, so every row is
    ``unknown``. Times are wall-clock in the bridge host's zone.
    """
    name = "bridged"
    roots = [r for r in roots if r and r.is_dir()]
    if not roots:
        return _absent(name, "no bridged session directory found")
    report = SourceReport(name, True, root=", ".join(str(r) for r in roots))
    zone = _dt.timezone(_dt.timedelta(hours=utc_offset_hours))

    def stream() -> Rows:
        for root in roots:
            for path in sorted(root.glob("session-*.md")):
                try:
                    body = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                created = re.search(r"^created: (\d{4}-\d{2}-\d{2})", body, re.M)
                sid_match = re.search(r"^session_id: (\S+)", body, re.M)
                if not created:
                    continue
                day = _dt.datetime.fromisoformat(created.group(1))
                if since and day.replace(tzinfo=_UTC).timestamp() < since - 86400:
                    continue
                report.files += 1
                sid = sid_match.group(1) if sid_match else path.stem
                yield from _bridge_turns(body, day, zone, sid, report)

    return report, stream()


def _bridge_turns(body: str, day: _dt.datetime, zone, sid: str, report: SourceReport) -> Rows:
    blocks: List[list] = []
    current = None
    for line in body.splitlines():
        header = _BRIDGE_HEADER.match(line)
        if header:
            current = [header.group(1), header.group(2), header.group(3), []]
            blocks.append(current)
            continue
        if current is None:
            continue
        if line.startswith("> "):
            current[3].append(line[2:])
        elif line.strip() == ">":
            current[3].append("")
        else:
            current = None
    hour_minute = (0, 0)
    prompt_id = None
    final = None
    for role, hh, mm, lines in blocks:
        if hh:
            hour_minute = (int(hh), int(mm))
        ts = day.replace(hour=hour_minute[0], minute=hour_minute[1], tzinfo=zone).timestamp()
        text = "\n".join(lines).strip()
        if not text:
            continue
        _observe(report, ts)
        if role == "User":
            if is_injected(text):
                continue
            if final and prompt_id:
                yield make_row(src="bridged", harness="bridged", kind="reply", ts=final[0], text=final[1],
                               session=sid, author="unknown", turn=prompt_id)
            final = None
            row = make_row(src="bridged", harness="bridged", kind="prompt", ts=ts, text=text, session=sid,
                           author="unknown")
            prompt_id = row["id"]
            yield row
        elif prompt_id:
            final = (ts, text)
    if final and prompt_id:
        yield make_row(src="bridged", harness="bridged", kind="reply", ts=final[0], text=final[1], session=sid,
                       author="unknown", turn=prompt_id)


# ------------------------------------------------------ Exported conversation datasets


def read_exports(paths: List[Path], since: Optional[float]) -> Tuple[SourceReport, Rows]:
    """A ``conversations.jsonl`` export: one session per line with a JSON ``turns`` list.

    Exports carry a date per session but no time per turn, so turns are placed
    at 17:00 UTC on that date in order. Authors are ``unknown``.
    """
    name = "export"
    paths = [p for p in paths if p and p.is_file()]
    if not paths:
        return _absent(name, "no conversation export configured")
    report = SourceReport(name, True, root=", ".join(str(p) for p in paths))

    def stream() -> Rows:
        for path in paths:
            report.files += 1
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    try:
                        rec = json.loads(line)
                        turns = json.loads(rec["turns"]) if isinstance(rec.get("turns"), str) else rec.get("turns")
                        day = _dt.datetime.fromisoformat(rec["date"]).replace(hour=17, tzinfo=_UTC).timestamp()
                    except (ValueError, KeyError, TypeError):
                        continue
                    if since and day < since:
                        continue
                    sid = rec.get("session_id")
                    prompt_id = None
                    final = None
                    for i, turn in enumerate(turns or []):
                        ts = day + i
                        text = (turn.get("content") or "") if isinstance(turn, dict) else ""
                        if not text.strip():
                            continue
                        _observe(report, ts)
                        if turn.get("role") == "user":
                            if is_injected(text):
                                continue
                            if final and prompt_id:
                                yield make_row(src=name, harness="claude-code", kind="reply", ts=final[0],
                                               text=final[1], session=sid, author="unknown", turn=prompt_id)
                            final = None
                            row = make_row(src=name, harness="claude-code", kind="prompt", ts=ts, text=text,
                                           session=sid, author="unknown")
                            prompt_id = row["id"]
                            yield row
                        elif turn.get("role") == "assistant" and prompt_id:
                            final = (ts, text)
                    if final and prompt_id:
                        yield make_row(src=name, harness="claude-code", kind="reply", ts=final[0], text=final[1],
                                       session=sid, author="unknown", turn=prompt_id)

    return report, stream()


def expand(paths) -> List[Path]:
    """Expand ``~``, variables and globs into existing paths."""
    out: List[Path] = []
    for raw in paths or []:
        pattern = os.path.expandvars(os.path.expanduser(str(raw)))
        matches = glob.glob(pattern) if any(c in pattern for c in "*?[") else [pattern]
        out.extend(Path(m) for m in matches if os.path.exists(m))
    return out
