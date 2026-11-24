"""Private meal log: one JSON line per meal in ``<data_dir>/meals.jsonl``.

The file is created 0600 inside a 0700 directory and is only ever appended to.
The data directory itself may be a symlink (a user can keep it on another volume,
as with the trace store); ``meals.jsonl`` and ``meal-photos/`` inside it may not.
A meal photo, when given, is copied into ``<data_dir>/meal-photos/`` (0600);
the original is left where it was.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

from broomva_health.domain.nutrition import Meal

__all__ = ["MealLog"]


def _ends_without_newline(path: Path) -> bool:
    size = path.stat().st_size
    if size == 0:
        return False
    with path.open("rb") as fh:
        fh.seek(size - 1)
        return fh.read(1) != b"\n"


_log = logging.getLogger(__name__)

_PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".heic", ".webp"})


class MealLog:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / "meals.jsonl"
        self.photos_dir = data_dir / "meal-photos"

    def _ensure_dir(self, directory: Path) -> None:
        if directory != self.data_dir and directory.is_symlink():
            raise ValueError(f"{directory} is a symlink; refusing to write health data through it")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)

    def keep_photo(self, src: Path, meal: Meal) -> str:
        """Copy ``src`` into the private photo folder; return its path relative to data_dir."""
        if not src.is_file():
            raise FileNotFoundError(f"photo not found: {src}")
        suffix = src.suffix.lower()
        if suffix not in _PHOTO_SUFFIXES:
            raise ValueError(
                f"photo must be one of {sorted(_PHOTO_SUFFIXES)}, got {suffix or 'no suffix'!r}"
            )
        self._ensure_dir(self.photos_dir)
        stem = meal.day.isoformat() + (f"-{meal.at.strftime('%H%M')}" if meal.at else "")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        for n in range(1000):
            dst = self.photos_dir / (f"{stem}{suffix}" if n == 0 else f"{stem}-{n}{suffix}")
            try:
                fd = os.open(dst, flags, 0o600)  # never follows or overwrites an existing entry
            except FileExistsError:
                continue
            try:
                with os.fdopen(fd, "wb") as out, src.open("rb") as inp:
                    shutil.copyfileobj(inp, out)
            except BaseException:
                dst.unlink(missing_ok=True)  # no half-written photo left behind
                raise
            return str(dst.relative_to(self.data_dir))
        raise FileExistsError(f"too many photos named {stem} in {self.photos_dir}")

    def discard_photo(self, kept: str) -> None:
        """Remove a photo copied by ``keep_photo`` (used when the meal could not be saved)."""
        target = self.data_dir / kept
        if target.parent == self.photos_dir and not target.is_symlink():
            target.unlink(missing_ok=True)

    def append(self, meal: Meal) -> None:
        self._ensure_dir(self.data_dir)
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ValueError(f"{self.path} is a symlink; refusing to write through it") from exc
            raise
        try:
            os.fchmod(fd, 0o600)  # tighten a looser file before any data reaches it
            torn = _ends_without_newline(self.path)
        except BaseException:
            os.close(fd)
            raise
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            if torn:  # a previous write was cut short: close its line so ours stays whole
                fh.write("\n")
            # ASCII escapes keep U+2028 and friends out of the raw file, so one meal is one line.
            fh.write(json.dumps(meal.model_dump(mode="json"), ensure_ascii=True) + "\n")

    def read(self, *, since: date | None = None, until: date | None = None) -> list[Meal]:
        if not self.path.exists() and not self.path.is_symlink():
            return []
        meals = []
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ValueError(f"{self.path} is a symlink; refusing to read through it") from exc
            raise
        with os.fdopen(fd, "rb") as fh:
            raw_lines = fh.read().split(b"\n")  # bytes: a torn UTF-8 tail stays one bad line
        for number, raw in enumerate(raw_lines, 1):
            if not raw.strip():
                continue
            try:
                meal = Meal.model_validate_json(raw.decode("utf-8"))
            except ValueError:  # includes UnicodeDecodeError
                _log.warning("%s:%d is not a readable meal; skipped", self.path, number)
                continue
            if (since is None or meal.day >= since) and (until is None or meal.day <= until):
                meals.append(meal)
        return sorted(meals, key=lambda m: (m.day, m.at.isoformat() if m.at else ""))

    def last_days(self, days: int, *, today: date) -> list[Meal]:
        return self.read(since=today - timedelta(days=days - 1), until=today)
