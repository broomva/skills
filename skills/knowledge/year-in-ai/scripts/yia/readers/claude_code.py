"""Reader for Claude Code transcripts (``~/.claude/projects/**/*.jsonl``).

This is the highest-fidelity store available locally: every message, tool call,
token count, model, skill attribution and git branch is recorded per turn.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ..model import Event, SourceReport, Window
from ._common import file_may_be_in_window, iter_records, truncate, walk_files

NAME = "claude_code"

#: Only the plain CLI is a person typing; ``sdk-cli`` and ``sdk-ts`` are
#: programmatic sessions that also record ``userType: external``.
_INTERACTIVE_ENTRYPOINTS = {"cli"}
_AUTOMATED_PROMPT_SOURCES = {"sdk", "system"}


def _message_text(message: dict) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    joined = "\n".join(p for p in parts if p)
    return joined or None


def _tokens(usage: dict) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None
    tokens = {
        "input": int(usage.get("input_tokens") or 0),
        "output": int(usage.get("output_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
    }
    return tokens if any(tokens.values()) else None


def read(root: Path | None, window: Window) -> tuple[SourceReport, Iterator[Event]]:
    """Return a coverage report and a lazy event stream for this store."""
    if root is None:
        return SourceReport(NAME, False, reason="no ~/.claude/projects on this machine"), iter(())
    if not root.is_dir():
        return SourceReport(NAME, False, reason=f"{root} is not a directory"), iter(())

    report = SourceReport(NAME, True, root=str(root))

    def stream() -> Iterator[Event]:
        for path in walk_files(root, (".jsonl",)):
            if not file_may_be_in_window(path, window):
                continue
            report.files += 1
            for ts, record in iter_records(path, window):
                report.observe(ts)
                kind_raw = record.get("type")
                base = {
                    "ts": ts,
                    "source": NAME,
                    "session": record.get("sessionId"),
                    "project": record.get("cwd"),
                    "branch": record.get("gitBranch") or None,
                    "skill": record.get("attributionSkill") or None,
                    "mcp_tool": record.get("attributionMcpTool") or None,
                }
                message = record.get("message")
                message = message if isinstance(message, dict) else {}
                base["interactive"] = (
                    record.get("entrypoint") in _INTERACTIVE_ENTRYPOINTS
                    and record.get("promptSource") not in _AUTOMATED_PROMPT_SOURCES
                )

                if kind_raw == "user":
                    # Sidechain turns are subagent traffic, not the operator talking.
                    if record.get("isSidechain"):
                        continue
                    yield Event(kind="user", text=truncate(_message_text(message)), **base)
                elif kind_raw == "assistant":
                    yield Event(
                        kind="assistant",
                        model=message.get("model"),
                        tokens=_tokens(message.get("usage") or {}),
                        **base,
                    )
                    for item in message.get("content") or []:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            yield Event(kind="tool", tool=item.get("name"), **base)
                elif base["skill"] or base["mcp_tool"]:
                    # Attribution can land on a record that is not itself a message;
                    # keep it rather than lose the signal.
                    yield Event(kind="meta", **base)

    return report, stream()
