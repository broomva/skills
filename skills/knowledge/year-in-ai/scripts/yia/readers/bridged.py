"""Reader for bridged session files (``docs/conversations/session-*.md``).

These are rendered summaries written by a session hook, so they reach further
back than the raw transcripts but carry less per-turn detail.  They are the
only store that records **wall-clock duration**, which is what makes a
"time spent" card possible at all.

Because their window overlaps the transcript stores, this reader contributes
only duration and session identity.  Message and tool counts are deliberately
left to the higher-fidelity readers so the same session is never counted twice.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..model import SourceReport, Window
from ._common import parse_ts

NAME = "bridged_sessions"

_ROW = re.compile(r"^\|\s*\*\*(?P<key>[^*]+)\*\*\s*\|\s*(?P<value>.*?)\s*\|\s*$", re.MULTILINE)
_FM_FIELD = re.compile(r"^(?P<key>[a-z_]+):\s*(?P<value>.+?)\s*$", re.MULTILINE)
_DURATION = re.compile(r"(?:(?P<h>\d+)\s*h)?\s*(?:(?P<m>\d+)\s*m)?(?:\s*(?P<s>\d+)\s*s)?", re.I)


def parse_duration(text: str) -> int | None:
    """Parse ``"1h 23m"`` / ``"17m"`` / ``"45s"`` into whole minutes.

    Returns ``None`` rather than ``0`` for an unparseable value: a session of
    unknown length must not be silently averaged in as a zero-length one.
    """
    text = (text or "").strip().strip("`")
    if not text:
        return None
    match = _DURATION.fullmatch(text)
    if match is None or not any(match.groupdict().values()):
        return None
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m") or 0)
    seconds = int(match.group("s") or 0)
    total = hours * 60 + minutes + seconds // 60
    return total if (hours or minutes or seconds) else None


@dataclass(slots=True)
class BridgedSession:
    """One bridged session summary."""

    session_id: str | None
    title: str | None
    date: str | None
    branch: str | None
    duration_minutes: int | None
    turns: int | None
    messages: int | None
    path: str


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'")


def parse_session_file(path: Path) -> BridgedSession | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    head = text[:4000]
    front = {m.group("key"): _strip_quotes(m.group("value")) for m in _FM_FIELD.finditer(head)}
    rows = {m.group("key").strip().lower(): m.group("value").strip() for m in _ROW.finditer(head)}

    def as_int(value: str | None) -> int | None:
        if not value:
            return None
        digits = re.sub(r"[^\d]", "", value)
        return int(digits) if digits else None

    return BridgedSession(
        session_id=front.get("session_id") or rows.get("session", "").strip("`") or None,
        title=front.get("title") or None,
        date=front.get("created") or rows.get("date") or None,
        branch=front.get("branch") or (rows.get("branch") or "").strip("`") or None,
        duration_minutes=parse_duration(rows.get("duration", "")),
        turns=as_int(rows.get("turns")),
        messages=as_int(rows.get("messages")),
        path=str(path),
    )


def read(roots: list[Path], window: Window) -> tuple[SourceReport, list[BridgedSession]]:
    """Collect bridged sessions from every discovered ``docs/conversations`` root."""
    if not roots:
        return SourceReport(NAME, False, reason="no docs/conversations directories found"), []

    report = SourceReport(NAME, True, root=", ".join(str(r) for r in roots[:3]))
    sessions: list[BridgedSession] = []
    seen: set[str] = set()

    for root in roots:
        for path in sorted(root.glob("session-*.md")):
            parsed = parse_session_file(path)
            if parsed is None:
                continue
            ts = parse_ts(parsed.date or "")
            if ts is None or not window.contains(ts):
                continue
            # The same session is bridged into several worktrees of one repo;
            # dedupe on session id so durations are not multiply counted.
            key = parsed.session_id or parsed.path
            if key in seen:
                continue
            seen.add(key)
            report.files += 1
            report.observe(ts)
            sessions.append(parsed)

    return report, sessions
