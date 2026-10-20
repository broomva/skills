"""Reader for the Claude Code prompt history (``~/.claude/history.jsonl``).

This store reaches further back than the transcripts and holds the verbatim
text of everything typed, but nothing about the reply.  It is therefore the
source for phrase and first-prompt cards, and is deliberately *not* counted
towards message or token totals — the transcript reader already owns those,
and adding these would double-count the overlapping window.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from ..model import Event, SourceReport, Window
from ._common import truncate

NAME = "prompt_history"


def read(path: Path | None, window: Window) -> tuple[SourceReport, Iterator[Event]]:
    if path is None:
        return SourceReport(NAME, False, reason="no ~/.claude/history.jsonl on this machine"), iter(())
    if not path.is_file():
        return SourceReport(NAME, False, reason=f"{path} is not a file"), iter(())

    report = SourceReport(NAME, True, root=str(path))

    def stream() -> Iterator[Event]:
        import datetime as dt

        report.files = 1
        try:
            handle = path.open("r", encoding="utf-8", errors="ignore")
        except OSError:
            return
        with handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict):
                    continue
                raw = record.get("timestamp")
                if not isinstance(raw, (int, float)):
                    continue
                # Milliseconds since epoch above ~2001; seconds below.
                seconds = raw / 1000 if raw > 1e11 else raw
                try:
                    ts = dt.datetime.fromtimestamp(seconds, dt.timezone.utc)
                except (OverflowError, OSError, ValueError):
                    continue
                if not window.contains(ts):
                    continue
                report.observe(ts)
                yield Event(
                    ts=ts,
                    source=NAME,
                    kind="meta",
                    session=record.get("sessionId"),
                    project=record.get("project"),
                    text=truncate(record.get("display")),
                )

    return report, stream()
