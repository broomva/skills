"""The check-in journal: one JSON object per date in an owner-only JSONL file (BRO-3751).

The journal holds the most sensitive data the skill touches (mood, symptoms, the user's
own words), so the rules the CheckIn workflow states live here as code, not prose:

- **One object per date.** Recording a date merges into that date's object: new keys win
  and old keys stay, so a late follow-up never erases the first answers.
- **Single writer.** Every write takes an exclusive ``flock`` on ``journal.lock`` (bounded
  wait), reads every line, merges, writes a temp file in the same directory, fsyncs it and
  ``os.replace``s it over the journal. A scheduled check-in and an on-demand one cannot
  interleave, duplicate a date or leave half a line.
- **Nothing is dropped.** A line that does not parse is kept verbatim, in place, and reported.
- **Owner-only.** The directory is 0700 and the file 0600. A user-chosen location is
  accepted only if :func:`private_dir_problems` finds nothing wrong with it.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import math
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

__all__ = ["JournalLockTimeout", "JsonlJournal", "parse_value", "private_dir_problems"]

# Path fragments of folders that sync to a cloud (macOS iCloud Drive, File Provider mounts,
# the usual desktop sync clients). A journal must not live under one.
_CLOUD_MARKERS = (
    "/nextcloud/",
    "/owncloud/",
    "/pcloud drive/",
    "/megasync/",
    "/sync.com/",
    "/syncthing/",
    "/seafile/",
    "/library/mobile documents/",
    "/library/cloudstorage/",
    "/icloud drive/",
    "/dropbox/",
    "/google drive/",
    "/onedrive/",
    "/box sync/",
)


_ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _is_iso_day(day: object) -> bool:
    """A real calendar date written YYYY-MM-DD (``2026-02-30`` is not)."""
    if not isinstance(day, str) or not _ISO_DAY.fullmatch(day) or not day.isascii():
        return False
    try:
        date.fromisoformat(day)
    except ValueError:
        return False
    return True


class JournalLockTimeout(TimeoutError):
    """Another writer held the journal lock past the timeout. Nothing was written."""


def parse_value(key: str, raw: str) -> Any:
    """Store answers verbatim. Only ``*_score`` keys become numbers and ``safety_stop`` a boolean.

    A label such as "Yes" or a note such as "No" stays text: the journal keeps the user's
    words, not a guess at their type. A score must be a finite number.
    """
    text = raw.strip()
    if key.endswith("_score"):
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"{key} must be a number") from None
        if not math.isfinite(value) or not 0 <= value <= 10:
            raise ValueError(f"{key} must be a number from 0 to 10")
        return int(value) if value.is_integer() else value
    if key == "safety_stop":
        if text.lower() not in ("yes", "true", "1"):
            raise ValueError("safety_stop can only be set to yes")
        return True
    return raw


def private_dir_problems(path: Path) -> list[str]:
    """Why ``path`` is not a safe home for the journal (empty list: it is).

    Checks the three things a sensitive file must not be: readable by others, inside a git
    work tree (one ``git add -A`` from a commit), or inside a cloud-synced folder.
    """
    problems: list[str] = []
    if path.expanduser().is_symlink():
        problems.append(f"{path} is a symlink; give the real folder")
    p = path.expanduser().resolve()
    if p.exists() and p.stat().st_mode & 0o077:
        problems.append(
            f"{p} is readable by other users (mode {oct(p.stat().st_mode & 0o777)}); needs 0700"
        )
    for parent in (p, *p.parents):
        if (parent / ".git").exists():
            problems.append(f"{p} is inside the git work tree {parent}")
            break
    probe = str(p).lower() + "/"
    synced_by_marker = any(m in probe for m in _CLOUD_MARKERS)
    # Sync clients that mark their root with a file. Only folders strictly below HOME are
    # checked: HOME itself holds client config (~/.dropbox, ~/.sync), not a sync root.
    home = Path.home().resolve()
    below_home = [q for q in (p, *p.parents) if home in q.parents]
    synced_by_root = any(
        (parent / mark).exists()
        for parent in below_home
        for mark in (".stfolder", ".sync", ".nextcloudsync.log", ".owncloudsync.log", ".dropbox")
    )
    if synced_by_marker or synced_by_root:
        problems.append(f"{p} is inside a known cloud-synced folder")
    return problems


@dataclass
class JsonlJournal:
    path: Path
    lock_timeout_s: float = 10.0
    unparsed: list[str] = field(default_factory=list, init=False)

    def read(self) -> dict[str, dict[str, Any]]:
        """Entries by date. Lines that do not parse are kept in ``self.unparsed``."""
        entries, _ = self._read_ordered()
        return {k: v for k, v in entries.items() if isinstance(v, dict)}

    def recent(self, n: int) -> list[dict[str, Any]]:
        entries = self.read()
        return [entries[d] for d in sorted(entries)[-n:]]

    def record(self, day: str, fields: dict[str, Any], *, at: str | None = None) -> dict[str, Any]:
        """Merge ``fields`` into ``day``'s entry and persist atomically. Returns the merged entry."""
        if not _is_iso_day(day):
            raise ValueError("date must be a real YYYY-MM-DD date")
        if "safety_stop" in fields:
            if fields["safety_stop"] is not True:
                raise ValueError("safety_stop can only be True")
            if set(fields) != {"safety_stop"}:
                raise ValueError("safety_stop is recorded alone, with no other answers")
        if self.path.exists() and not self.path.is_file():
            raise ValueError(f"{self.path} exists and is not a regular file")
        if self.path.is_symlink():
            raise ValueError(f"{self.path} is a symlink; the journal must be a regular file")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.path.parent, 0o700)
        lock_flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        lock_fd = os.open(self.path.parent / "journal.lock", lock_flags, 0o600)
        with os.fdopen(lock_fd, "w") as lock:
            self._acquire(lock)
            try:
                entries, order = self._read_ordered()
                merged = dict(entries.get(day) or {})
                merged.update(fields)
                merged["date"] = day
                if at:
                    merged["at"] = at
                if day not in entries:
                    order.append(day)
                entries[day] = merged
                self._replace(entries, order)
                return merged
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    # ── internals ────────────────────────────────────────────────────────────

    def _acquire(self, lock: Any) -> None:
        deadline = time.monotonic() + self.lock_timeout_s
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise JournalLockTimeout(
                        f"journal lock held for more than {self.lock_timeout_s}s; nothing written"
                    ) from None
                time.sleep(0.05)

    def _read_ordered(self) -> tuple[dict[str, Any], list[str]]:
        """Entries keyed by date (unparsed lines keyed ``~line-N``) and their file order."""
        self.unparsed = []
        entries: dict[str, Any] = {}
        order: list[str] = []
        try:
            text = self.path.read_text(encoding="utf-8", errors="surrogateescape")
        except FileNotFoundError:
            return entries, order
        # Split strictly on LF (trimming a trailing CR), never str.splitlines(): Unicode
        # line separators (\u2028, \u2029, \x85) inside JSON strings are valid JSONL content
        # and must not split a record into corrupt fragments.
        lines = [ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n")]
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                day = obj["date"] if isinstance(obj, dict) else None
                if not isinstance(day, str) or not _is_iso_day(day):
                    raise ValueError("no real ISO date")
                json.dumps(obj, allow_nan=False)  # a line we could not write back is kept as is
            except (ValueError, KeyError):
                key = f"~line-{i:06d}"
                self.unparsed.append(line)
                entries[key] = line
                order.append(key)
                continue
            if day not in entries:
                order.append(day)
            entries[day] = {**entries.get(day, {}), **obj}  # a duplicated date merges
        return entries, order

    def _replace(self, entries: dict[str, Any], order: list[str]) -> None:
        dated = sorted(k for k in order if not k.startswith("~"))
        it = iter(dated)
        # Dated entries come out sorted; an unparsed line keeps its slot among them.
        rows = [
            entries[k]
            if k.startswith("~")
            else json.dumps(entries[next(it)], ensure_ascii=False, allow_nan=False)
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
            .replace("\x85", "\\u0085")
            for k in order
        ]
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".journal-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as fh:
                fh.write("".join(r + "\n" for r in rows))
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
