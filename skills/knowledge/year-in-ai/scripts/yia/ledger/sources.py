"""Turn readers: each store's prompts and final replies as ledger rows.

Every reader returns ``(SourceReport, iterator of rows)``, tolerates a missing
store, a locked database or a torn last line, and is listed in :data:`REGISTRY`.
The report fills in as the iterator is consumed.

**The identity contract.** Every row a reader emits carries an *occurrence*
identity (see :func:`yia.ledger.occurrence_key`): the store's own message id
where it has one, otherwise ``(session, timestamp, role, text hash, n)``, where
``n`` counts earlier identical occurrences in that session. Either way it is:

* stable: harvesting the same store twice gives the same ids;
* distinct: two occurrences never share an id, even with identical text and
  timestamp;
* local: pruning older records or inserting new ones leaves every other id
  unchanged, with one disclosed exception: occurrences identical in session,
  timestamp, role and text, in a store without message ids, are told apart
  only by their order, so pruning or inserting one of them can relabel the
  others. Their *count* in the ledger is still right: an append-only ledger
  keeps every occurrence it has seen and adds one for each new one;
* revisions: a message edited in place is a new row for the same occurrence
  (``o``), and the fold keeps its latest revision.

``tests/test_reader_contract.py`` runs the same contract cases against every
reader in :data:`REGISTRY`, and fails if a reader is added without a fixture.
Identity says nothing about *equivalence*: whether two occurrences are one
turn is decided later, on evidence, by :mod:`yia.ledger.attention`.

Attribution, per store:

* T3 records ``createdBy`` on every user message, so its authors are exact.
* Claude Code records an ``entrypoint``: ``cli`` is a person at a terminal,
  ``sdk-cli`` is ``claude -p``, ``sdk-ts`` is an app driving the SDK.
* Codex records an ``originator`` and a ``source``; ``codex_exec`` is a script.
* Bridged markdown and exports record no author; their rows are ``unknown``.

Every external scalar passes through :func:`yia.ledger.ext_str` before use.
"""

from __future__ import annotations

import collections
import datetime as _dt
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

from ..model import SourceReport
from . import ext_str, harness_label, is_injected, make_row, occurrence_key, text_hash, unwrap_command

Rows = Iterator[dict]

_UTC = _dt.timezone.utc


def _iso(raw) -> Optional[float]:
    raw = ext_str(raw)
    if not raw or raw == "other":
        return None
    text = raw.strip()
    if "T" not in text:
        text = text.replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.timestamp()


def _sid(value) -> Optional[str]:
    """A session or message id from a store: strings and numbers are kept; anything else is unusable."""
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        return str(value)
    return None


def _text(value) -> Optional[str]:
    return value if isinstance(value, str) else None


def _observe(report: SourceReport, ts: float) -> None:
    report.observe(_dt.datetime.fromtimestamp(ts, _UTC))


def _absent(name: str, reason: str) -> Tuple[SourceReport, Rows]:
    return SourceReport(name, False, reason=reason), iter(())


def _ro_sqlite(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)


class ContentKeys:
    """Content-anchored occurrence keys for stores without message ids."""

    def __init__(self) -> None:
        self._seen: Dict[tuple, int] = collections.Counter()

    def __call__(self, session: Optional[str], ts: float, role: str, text: str) -> str:
        base = (session, f"{ts:.3f}", role, text_hash(text))
        n = self._seen[base]
        self._seen[base] += 1
        return occurrence_key(*base, n)


def pair_turns(events, *, src: str, session: Optional[str], harness, author, attr=None,
               report: Optional[SourceReport] = None) -> Rows:
    """Turn a time-ordered stream of ``(role, ts, text, native_id)`` into prompt and reply rows.

    ``role`` is ``"prompt"``, ``"reply"`` or ``"boundary"`` (an excluded
    prompt: it ends the current turn, and replies until the next prompt are
    dropped); ``native_id`` is the store's
    message id, or a precomputed content key, or ``None`` (then the key is
    content-anchored here). A reply row is the last reply before the next
    prompt, tied to that prompt's row id, and carries the identity of that
    reply message, so a harvest made mid-turn and a later one record two
    revisions rather than overwriting. ``harness``, ``author`` and ``attr`` may
    be callables, evaluated at the first prompt. Holds one pending reply in
    memory, never the session.
    """
    keys = ContentKeys()
    prompt_id = None
    final = None
    resolved = None

    def reply_row(item):
        ts, text, occ = item
        return make_row(src=src, harness=resolved[0], kind="reply", ts=ts, text=text, session=session,
                        author=resolved[1], turn=prompt_id, occurrence=occ)

    for role, ts, text, native in events:
        if role == "boundary":
            # An excluded prompt (harness-injected, a bare command) still ends the
            # current turn: its reply is not the previous prompt's.
            if final and prompt_id:
                yield reply_row(final)
            final = None
            prompt_id = None
            continue
        if not text or not text.strip():
            continue
        if report is not None:
            _observe(report, ts)
        occ = occurrence_key(native) if native else keys(session, ts, role, text)
        if role == "prompt":
            if resolved is None:
                resolved = (harness() if callable(harness) else harness,
                            author() if callable(author) else author,
                            attr() if callable(attr) else attr)
            if final and prompt_id:
                yield reply_row(final)
            final = None
            row = make_row(src=src, harness=resolved[0], kind="prompt", ts=ts, text=text, session=session,
                           author=resolved[1], attr=resolved[2], occurrence=occ, key=native)
            prompt_id = row["id"]
            yield row
        elif prompt_id:
            final = (ts, text, occ)
    if final and prompt_id:
        yield reply_row(final)


# --------------------------------------------------------------------------- T3


def read_t3(db: Optional[Path], since: Optional[float]) -> Tuple[SourceReport, Rows]:
    """T3's orchestration store. Subagent threads are skipped; fork threads skip their copied history."""
    name = "t3"
    if db is None or not db.is_file():
        return _absent(name, "no T3 state database on this machine")
    report = SourceReport(name, True, root=str(db))

    def stream() -> Rows:
        try:
            con = _ro_sqlite(db)
            threads = {
                tid: (ext_str(lin) or "top", ext_str(prov), _iso(created))
                for tid, lin, prov, created in con.execute(
                    "select thread_id, json_extract(payload_json,'$.lineage.relationshipToParent'), "
                    "default_provider, created_at from orchestration_v2_projection_threads"
                )
            }
            cutoff = (
                _dt.datetime.fromtimestamp(since, _UTC).strftime("%Y-%m-%dT%H:%M:%S") if since else ""
            )
            rows = con.execute(
                "select message_id, thread_id, run_id, role, created_at, json_extract(payload_json,'$.createdBy'), "
                "json_extract(payload_json,'$.creationSource'), json_extract(payload_json,'$.text') "
                "from orchestration_v2_projection_messages where streaming=0 and created_at >= ? "
                "order by created_at, message_id",
                (cutoff,),
            )
        except sqlite3.Error as exc:
            report.available = False
            report.reason = f"T3 database unreadable: {exc}"
            return
        report.files = 1
        runs: Dict[Tuple[str, str], dict] = {}
        for message_id, thread, run, role, created, created_by, creation_source, text in rows:
            lineage, provider, thread_created = threads.get(thread, ("top", None, None))
            text = _text(text)
            message_id = _sid(message_id)
            if lineage == "subagent" or not text or not message_id:
                continue
            ts = _iso(created)
            if ts is None:
                continue
            # A fork carries its parent's history; messages older than the fork are copies.
            if lineage == "fork" and thread_created is not None and ts < thread_created:
                continue
            _observe(report, ts)
            harness = harness_label("t3", provider, "provider")
            state = runs.setdefault((thread, run), {"prompt": None, "author": None, "last": None})
            if role == "user":
                if is_injected(text):
                    continue
                created_by = ext_str(created_by)
                author = {"user": "human", "agent": "agent"}.get(created_by, "unknown")
                row = make_row(
                    src=name, harness=harness, kind="prompt", ts=ts, text=text, session=thread, author=author,
                    attr={"created_by": created_by, "creation_source": creation_source, "lineage": lineage},
                    occurrence=occurrence_key(message_id), key=message_id,
                )
                if state["prompt"] is None:
                    state["prompt"], state["author"] = row["id"], author
                yield row
            elif role == "assistant":
                state["last"] = (ts, text, harness, message_id)
        for (thread, _run), state in runs.items():
            if state["last"] and state["prompt"]:
                ts, text, harness, message_id = state["last"]
                yield make_row(src=name, harness=harness, kind="reply", ts=ts, text=text, session=thread,
                               author=state["author"], turn=state["prompt"],
                               occurrence=occurrence_key(message_id))
        con.close()

    return report, stream()


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
                "select id, session_id, role, content, created_at from session_messages order by created_at, id"
            )
        except sqlite3.Error as exc:
            report.available = False
            report.reason = f"Conductor database unreadable: {exc}"
            return
        report.files = 1
        # The prompt each session is answering *now*. A reply belongs to the
        # prompt current when it was read, never to the session's last prompt.
        current: Dict[str, str] = {}
        last: Dict[str, Tuple[float, str, str, str]] = {}
        for message_id, session, role, content, created in rows:
            ts = _iso(created)
            content, message_id, session = _text(content), _sid(message_id), _sid(session)
            if ts is None or (since and ts < since) or not content or not message_id:
                continue
            _observe(report, ts)
            if role == "user":
                if is_injected(content):
                    current.pop(session, None)  # its reply is not the previous prompt's
                    continue
                row = make_row(src=name, harness="conductor", kind="prompt", ts=ts, text=content,
                               session=session, author="human", occurrence=occurrence_key(message_id),
                               key=message_id)
                current[session] = row["id"]
                yield row
            elif role == "assistant" and session in current:
                try:
                    message = json.loads(content)
                except ValueError:
                    continue
                if not isinstance(message, dict) or message.get("type") != "assistant":
                    continue
                inner = message.get("message") if isinstance(message.get("message"), dict) else {}
                parts = inner.get("content") if isinstance(inner.get("content"), list) else []
                text = "\n".join(p["text"] for p in parts if isinstance(p, dict) and p.get("type") == "text"
                                 and isinstance(p.get("text"), str))
                if text.strip():
                    last[current[session]] = (ts, text, session, message_id)
        for prompt_id, (ts, text, session, message_id) in last.items():
            yield make_row(src=name, harness="conductor", kind="reply", ts=ts, text=text, session=session,
                           author="human", turn=prompt_id, occurrence=occurrence_key(message_id))
        con.close()

    return report, stream()


# --------------------------------------------------------------------- Claude Code

#: An archived revision's name, made by :mod:`yia.ledger.archive`: ``<name>.rev-<n>.jsonl[.zst]``.
_ARCHIVE_REVISION = re.compile(r"\.rev-[0-9]+\.jsonl(\.zst)?$")


def is_archive_revision(name: str) -> bool:
    """Is this file a revision the archive kept beside a diverged transcript?

    Revisions are preserved so a recap can quote them, and are never ledger
    input: replaying stored versions of one transcript is what made every
    harvest re-append them. The ledger reads live files and base archive files.
    """
    return bool(_ARCHIVE_REVISION.search(name))

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
        runtime = data.get("runtimeInfo") if isinstance(data, dict) else None
        sid = _sid(runtime.get("sessionId")) if isinstance(runtime, dict) else None
        if sid:
            ids.add(sid)
    return ids


def _claude_text(content) -> Optional[str]:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        return "\n".join(b["text"] for b in content
                         if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return None


def read_claude_projects(
    roots: List[Path], since: Optional[float], paseo_ids: Optional[Set[str]] = None
) -> Tuple[SourceReport, Rows]:
    """Claude Code transcripts. The largest copy of each session wins, so live and archived roots can overlap.

    Every record has a ``uuid``, and a resumed session copies records with the
    original one, so a copied turn has the same occurrence id as its original.
    """
    name = "claude_code"
    roots = [r for r in roots if r and r.is_dir()]
    if not roots:
        return _absent(name, "no Claude Code transcript directory on this machine")
    report = SourceReport(name, True, root=", ".join(str(r) for r in roots))
    paseo_ids = paseo_ids or set()

    def stream() -> Rows:
        files: Dict[str, Tuple[tuple, Path]] = {}
        for root_index, root in enumerate(roots):
            for path in root.glob("*/*.jsonl"):
                try:
                    st = path.stat()
                except OSError:
                    continue
                if since and st.st_mtime < since:
                    continue
                if is_archive_revision(path.name):
                    continue  # kept by the archive for quoting, never counted
                # Live and archived copies share a name. The larger wins; on a tie the
                # newer write, then the earlier root (live before archive).
                rank = (st.st_size, st.st_mtime_ns, -root_index)
                if path.stem not in files or rank > files[path.stem][0]:
                    files[path.stem] = (rank, path)
        for sid in sorted(files):
            report.files += 1
            yield from _claude_session(files[sid][1], sid, since, paseo_ids, report)

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
                if not isinstance(rec, dict):
                    continue
                state["entry"] = state["entry"] or ext_str(rec.get("entrypoint"))
                if rec.get("isSidechain") or rec.get("isMeta") or rec.get("isCompactSummary"):
                    continue
                uid = _sid(rec.get("uuid"))
                if not uid or uid in seen:
                    continue
                seen.add(uid)
                ts = _iso(rec.get("timestamp"))
                if ts is None or (since and ts < since):
                    continue
                message = rec.get("message") if isinstance(rec.get("message"), dict) else {}
                text = _claude_text(message.get("content"))
                if not text or not text.strip():
                    continue
                if rec.get("type") == "user":
                    typed = None if is_injected(text) else unwrap_command(text)
                    if typed is None:
                        yield "boundary", ts, None, None
                        continue
                    yield "prompt", ts, typed, uid
                elif rec.get("type") == "assistant":
                    yield "reply", ts, text, uid

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
        keys = ContentKeys()
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                stamp = rec.get("timestamp")
                display = _text(rec.get("display")) or ""
                if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not display.strip():
                    continue
                ts = stamp / 1000.0
                if since and ts < since:
                    continue
                # A menu-bar usage probe sends /usage every few minutes; it is nobody typing.
                if "CodexBar" in (ext_str(rec.get("project")) or ""):
                    continue
                if display.strip().startswith("/") and len(display) < 60:
                    continue
                _observe(report, ts)
                pasted_map = rec.get("pastedContents") if isinstance(rec.get("pastedContents"), dict) else {}
                pasted = [v.get("content") for v in pasted_map.values()
                          if isinstance(v, dict) and isinstance(v.get("content"), str)]
                full = "\n".join([display] + pasted)
                session = _sid(rec.get("sessionId"))
                yield make_row(src=name, harness="claude-cli", kind="prompt", ts=ts, text=full, session=session,
                               author="human", authored=display,
                               occurrence=keys(session, ts, "prompt", full))

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
        # Live and archived copies share a name. Pick one per name before reading:
        # the larger, then the newer write, then the earlier root (live first).
        chosen: Dict[str, Tuple[tuple, Path, str]] = {}
        for root_index, root in enumerate(roots):
            for dirpath, dirs, names in os.walk(root):
                dirs.sort()
                for fname in sorted(names):
                    if ".jsonl" not in fname or is_archive_revision(fname):
                        continue  # revisions are kept by the archive for quoting, never counted
                    path = Path(dirpath) / fname
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    if since and st.st_mtime < since:
                        continue
                    base = fname[: -len(".zst")] if fname.endswith(".zst") else fname
                    rank = (st.st_size, st.st_mtime_ns, -root_index)
                    if base not in chosen or rank > chosen[base][0]:
                        chosen[base] = (rank, path, fname.split(".")[0][-36:])
        for base in sorted(chosen):
            _rank, path, sid = chosen[base]
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
            if isinstance(rec, dict) and rec.get("type") == "session_meta":
                meta = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
                break
    if meta is None:
        return
    source = meta.get("source")
    if not isinstance(source, str):
        for _ in lines:  # drain, so the decompressor exits cleanly
            pass
        return  # a subagent spawned by another Codex thread
    originator = ext_str(meta.get("originator")) or ""
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
            if not isinstance(rec, dict) or rec.get("type") != "event_msg":
                continue
            ts = _iso(rec.get("timestamp"))
            if ts is None or (since and ts < since):
                continue
            payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
            kind = payload.get("type")
            if kind == "user_message":
                yield "prompt", ts, _text(payload.get("message")), None
            elif kind == "agent_message":
                yield "reply", ts, _text(payload.get("message")), None
            elif kind == "task_complete":
                yield "reply", ts, _text(payload.get("last_agent_message")), None

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
        keys = ContentKeys()
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                ts = rec.get("ts")
                text = _text(rec.get("text")) or ""
                if not isinstance(ts, (int, float)) or isinstance(ts, bool) or (since and ts < since) \
                        or not text.strip():
                    continue
                _observe(report, ts)
                session = _sid(rec.get("session_id"))
                yield make_row(src=name, harness="codex:history", kind="prompt", ts=float(ts), text=text,
                               session=session, author="human",
                               occurrence=keys(session, float(ts), "prompt", text))

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
                if not isinstance(data, dict):
                    continue
                report.files += 1
                sid = _sid(data.get("sessionId")) or path.stem
                messages = data.get("messages") if isinstance(data.get("messages"), list) else []

                def events(messages=messages):
                    for msg in messages:
                        if not isinstance(msg, dict):
                            continue
                        ts = _iso(msg.get("timestamp"))
                        content = msg.get("content")
                        if isinstance(content, list):
                            content = "\n".join(c["text"] for c in content
                                                if isinstance(c, dict) and isinstance(c.get("text"), str))
                        content = _text(content)
                        if ts is None or (since and ts < since) or not content:
                            continue
                        role = {"user": "prompt", "gemini": "reply"}.get(ext_str(msg.get("type")))
                        if role:
                            yield role, ts, content, _sid(msg.get("id"))

                yield from pair_turns(events(), src=name, session=sid, report=report, harness="gemini-cli",
                                      author="human")

    return report, stream()


# ---------------------------------------------------------- Bridged markdown sessions

_BRIDGE_HEADER = re.compile(r"^> \[!(?:quote|info)\] \*\*(User|Assistant)\*\*(?: \((\d\d):(\d\d)\))?")


def read_bridged(
    roots: List[Path], since: Optional[float], utc_offset_hours: float = -5.0
) -> Tuple[SourceReport, Rows]:
    """Session transcripts rendered to markdown by a conversation bridge.

    The markdown keeps every turn but not who typed it, so every row is
    ``unknown``. Times are wall-clock minutes in the bridge host's zone.
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
                yield from pair_turns(_bridge_events(body, day, zone), src=name, session=sid, report=report,
                                      harness="bridged", author="unknown")

    return report, stream()


def _bridge_events(body: str, day: _dt.datetime, zone):
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
    for role, hh, mm, lines in blocks:
        if hh:
            hour_minute = (int(hh), int(mm))
        ts = day.replace(hour=hour_minute[0], minute=hour_minute[1], tzinfo=zone).timestamp()
        text = "\n".join(lines).strip()
        if not text:
            continue
        if role == "User" and is_injected(text):
            yield "boundary", ts, None, None
            continue
        yield ("prompt" if role == "User" else "reply"), ts, text, None


# ------------------------------------------------------ Exported conversation datasets


def read_exports(paths: List[Path], since: Optional[float]) -> Tuple[SourceReport, Rows]:
    """A ``conversations.jsonl`` export: one session per line with a JSON ``turns`` list.

    Exports carry a date per session but no time per turn, so turns are placed
    at 17:00 UTC on that date plus their position in seconds, for ordering only.
    Occurrence keys use the date, not the position, so they survive pruning.
    Authors are ``unknown``.
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
                    except (ValueError, KeyError, TypeError, AttributeError):
                        continue
                    if since and day < since:
                        continue
                    sid = _sid(rec.get("session_id"))
                    keys = ContentKeys()

                    def events(turns=turns, day=day, sid=sid, keys=keys):
                        for i, turn in enumerate(turns if isinstance(turns, list) else []):
                            if not isinstance(turn, dict):
                                continue
                            text = _text(turn.get("content")) or ""
                            role = {"user": "prompt", "assistant": "reply"}.get(ext_str(turn.get("role")))
                            if not role or not text.strip():
                                continue
                            if role == "prompt" and is_injected(text):
                                yield "boundary", day + i, None, None
                                continue
                            # The day, not the position: positions shift when turns are pruned.
                            yield role, day + i, text, keys(sid, day, role, text)

                    yield from pair_turns(events(), src=name, session=sid, report=report, harness="claude-code",
                                          author="unknown")

    return report, stream()


#: Every reader, by store name. The reader contract suite runs against each.
REGISTRY: Dict[str, Callable] = {
    "t3": read_t3,
    "conductor": read_conductor,
    "claude_code": read_claude_projects,
    "claude_history": read_claude_history,
    "codex": read_codex_sessions,
    "codex_history": read_codex_history,
    "gemini": read_gemini,
    "bridged": read_bridged,
    "export": read_exports,
}


def expand(paths) -> List[Path]:
    """Expand ``~``, variables and globs into existing paths."""
    out: List[Path] = []
    for raw in paths or []:
        pattern = os.path.expandvars(os.path.expanduser(str(raw)))
        matches = glob.glob(pattern) if any(c in pattern for c in "*?[") else [pattern]
        out.extend(Path(m) for m in matches if os.path.exists(m))
    return out
