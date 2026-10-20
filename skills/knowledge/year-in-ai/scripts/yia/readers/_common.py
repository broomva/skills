"""Streaming helpers shared by the transcript readers.

A full local corpus runs to tens of gigabytes, so nothing here materialises a
file.  Two cheap filters do most of the work before any JSON is parsed:

* a file-level skip using the name or mtime, and
* a line-level skip that finds the ISO timestamp by substring and compares it
  lexicographically against the window bounds.

ISO-8601 with a fixed ``YYYY-MM-DDTHH:MM:SS`` prefix sorts identically as text
and as time, which is what makes the second filter sound.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from collections.abc import Iterator
from pathlib import Path

from ..model import Window

_TS_KEY = '"timestamp":"'
_TS_LEN = 19  # YYYY-MM-DDTHH:MM:SS


def parse_ts(raw: str) -> _dt.datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime."""
    if not raw:
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone(_dt.timezone.utc)


def _bound_prefix(dt: _dt.datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def iter_records(path: Path, window: Window) -> Iterator[tuple[_dt.datetime, dict]]:
    """Yield ``(timestamp, record)`` for in-window JSON lines of ``path``.

    Malformed lines are skipped rather than raised: these files are appended to
    by live processes, so a torn final line is normal and is not a corpus error.
    """
    lo = _bound_prefix(window.start)
    hi = _bound_prefix(window.end)
    try:
        handle = path.open("r", encoding="utf-8", errors="ignore")
    except OSError:
        return
    with handle:
        for line in handle:
            idx = line.find(_TS_KEY)
            if idx < 0:
                continue
            prefix = line[idx + len(_TS_KEY) : idx + len(_TS_KEY) + _TS_LEN]
            if len(prefix) < _TS_LEN or not prefix[:4].isdigit():
                continue
            # Lexicographic window test, before any JSON parsing.
            if lo is not None and prefix < lo:
                continue
            if hi is not None and prefix >= hi:
                continue
            try:
                record = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if not isinstance(record, dict):
                continue
            ts = parse_ts(record.get("timestamp") or "")
            if ts is None or not window.contains(ts):
                continue
            yield ts, record


def file_may_be_in_window(path: Path, window: Window) -> bool:
    """Cheap file-level skip.

    A file cannot contain records newer than its own mtime, so an mtime before
    the window start rules the whole file out.  The converse is not true — a
    recently-touched file may hold old records — so this only ever skips, and
    a failure to stat is treated as "cannot rule out".
    """
    if window.start is None:
        return True
    try:
        mtime = _dt.datetime.fromtimestamp(os.stat(path).st_mtime, _dt.timezone.utc)
    except OSError:
        return True
    return mtime >= window.start


def walk_files(root: Path, suffixes: tuple[str, ...]) -> Iterator[Path]:
    """Yield files under ``root`` whose name ends with one of ``suffixes``."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if name.endswith(suffixes):
                yield Path(dirpath) / name


def truncate(text: str | None, limit: int = 2000) -> str | None:
    """Bound prompt text so a corpus-wide scan stays memory-flat."""
    if text is None:
        return None
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
