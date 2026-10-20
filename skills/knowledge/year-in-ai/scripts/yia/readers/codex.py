"""Reader for Codex sessions (``~/.codex/sessions``).

Two on-disk formats coexist and both are read:

``modern``
    ``<year>/<month>/<day>/rollout-<iso>-<uuid>.jsonl`` — one JSON record per
    line, each with its own top-level ``timestamp`` and a ``payload``.

``legacy`` (2025-04)
    ``rollout-<date>-<uuid>.json`` flat in the sessions root — a single JSON
    object of ``{"session": {...}, "items": [...]}``.  Items carry no
    timestamps of their own, so every event inherits the session timestamp.
    That is a real loss of resolution, and it is why the legacy branch
    contributes to totals and rankings but never to the hour-of-day rhythm.

Codex records the model on ``turn_context`` and the working directory on
``session_meta``, both separate from the messages they describe, so the reader
threads a small amount of per-file state forward as it streams.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from ..model import Event, SourceReport, Window
from ._common import file_may_be_in_window, iter_records, parse_ts, truncate, walk_files

NAME = "codex"

#: Originators that mean a script, not a person.
_AUTOMATED_ORIGINATORS = ("exec", "sdk", "omnara")


def _is_interactive(originator: object, source: object) -> bool:
    """A person at a terminal, or a programmatic run?

    ``source`` is a bare string for human sessions (``cli``, ``vscode``) and a
    nested object for subagent spawns, so a non-string source is automation.
    """
    name = str(originator or "").lower()
    if any(marker in name for marker in _AUTOMATED_ORIGINATORS):
        return False
    if not isinstance(source, str):
        return False
    return source.lower() != "exec"


def _text_of(content: object) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = [
        c.get("text", "")
        for c in content
        if isinstance(c, dict) and c.get("type") in ("input_text", "output_text", "text")
    ]
    joined = "\n".join(p for p in parts if p)
    return joined or None


def _tokens(info: dict) -> dict[str, int] | None:
    usage = info.get("last_token_usage")
    if not isinstance(usage, dict):
        return None
    tokens = {
        "input": int(usage.get("input_tokens") or 0),
        "output": int(usage.get("output_tokens") or 0),
        "cache_read": int(usage.get("cached_input_tokens") or 0),
        "cache_write": int(usage.get("cache_write_input_tokens") or 0),
    }
    return tokens if any(tokens.values()) else None


def _emit_modern(path: Path, window: Window, report: SourceReport) -> Iterator[Event]:
    state: dict[str, object] = {
        "session": None, "project": None, "model": None, "branch": None, "interactive": False,
    }
    for ts, record in iter_records(path, window):
        report.observe(ts)
        payload = record.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        rtype = record.get("type")
        ptype = payload.get("type")

        if rtype == "session_meta":
            state["session"] = payload.get("session_id") or payload.get("id")
            state["project"] = payload.get("cwd")
            state["interactive"] = _is_interactive(
                payload.get("originator"), payload.get("source")
            )
            git = payload.get("git")
            if isinstance(git, dict):
                state["branch"] = git.get("branch") or git.get("ref")
            continue
        if rtype == "turn_context":
            state["model"] = payload.get("model") or state["model"]
            state["project"] = payload.get("cwd") or state["project"]
            continue

        base = {
            "ts": ts,
            "source": NAME,
            "session": state["session"],
            "project": state["project"],
            "branch": state["branch"],
            "interactive": bool(state["interactive"]),
        }

        # ``response_item`` is the canonical conversation history. ``event_msg``
        # mirrors much of it for the UI, so messages are taken only from the
        # former to avoid counting every assistant turn twice.
        if rtype == "response_item":
            if ptype == "message":
                role = payload.get("role")
                if role == "user":
                    yield Event(kind="user", text=truncate(_text_of(payload.get("content"))), **base)
                elif role == "assistant":
                    yield Event(kind="assistant", model=state["model"], **base)
            elif ptype == "agent_message":
                yield Event(kind="assistant", model=state["model"], **base)
            elif ptype in ("custom_tool_call", "function_call", "local_shell_call"):
                yield Event(kind="tool", tool=payload.get("name") or ptype, **base)
        elif rtype == "event_msg":
            if ptype == "token_count":
                info = payload.get("info")
                tokens = _tokens(info) if isinstance(info, dict) else None
                if tokens:
                    yield Event(kind="meta", tokens=tokens, model=state["model"], **base)
            elif ptype == "mcp_tool_call_end":
                inv = payload.get("invocation")
                if isinstance(inv, dict):
                    server, tool = inv.get("server"), inv.get("tool")
                    if server or tool:
                        yield Event(kind="meta", mcp_tool=f"{server}.{tool}", **base)


def _emit_legacy(path: Path, window: Window, report: SourceReport) -> Iterator[Event]:
    try:
        blob = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return
    if not isinstance(blob, dict):
        return
    session = blob.get("session") if isinstance(blob.get("session"), dict) else {}
    ts = parse_ts(session.get("timestamp") or "")
    if ts is None or not window.contains(ts):
        return
    base = {
        "ts": ts,
        "source": NAME,
        "session": session.get("id"),
        "project": session.get("cwd"),
        "branch": None,
        "interactive": True,
    }
    for item in blob.get("items") or []:
        if not isinstance(item, dict):
            continue
        report.observe(ts)
        itype, role = item.get("type"), item.get("role")
        if itype == "message" and role == "user":
            yield Event(kind="user", text=truncate(_text_of(item.get("content"))), **base)
        elif itype == "message" and role == "assistant":
            yield Event(kind="assistant", **base)
        elif itype in ("function_call", "custom_tool_call", "local_shell_call"):
            yield Event(kind="tool", tool=item.get("name") or itype, **base)


def read(root: Path | None, window: Window) -> tuple[SourceReport, Iterator[Event]]:
    """Return a coverage report and a lazy event stream for the Codex store."""
    if root is None:
        return SourceReport(NAME, False, reason="no ~/.codex/sessions on this machine"), iter(())
    if not root.is_dir():
        return SourceReport(NAME, False, reason=f"{root} is not a directory"), iter(())

    report = SourceReport(NAME, True, root=str(root))

    def stream() -> Iterator[Event]:
        for path in walk_files(root, (".jsonl", ".json")):
            if not path.name.startswith("rollout-"):
                continue
            if not file_may_be_in_window(path, window):
                continue
            report.files += 1
            if path.suffix == ".jsonl":
                yield from _emit_modern(path, window, report)
            else:
                yield from _emit_legacy(path, window, report)

    return report, stream()
