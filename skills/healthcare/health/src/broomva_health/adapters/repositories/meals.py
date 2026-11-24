"""Private meal log: one JSON line per meal in ``<data_dir>/meals.jsonl``.

The file is created 0600 inside a 0700 directory and is only ever appended to.
A meal photo, when given, is copied into ``<data_dir>/meal-photos/`` (0600);
the original is left where it was.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

from broomva_health.domain.nutrition import Meal

__all__ = ["MealLog"]

_PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".heic", ".webp"})


class MealLog:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / "meals.jsonl"
        self.photos_dir = data_dir / "meal-photos"

    def _ensure_dir(self, directory: Path) -> None:
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
        dst, n = self.photos_dir / f"{stem}{suffix}", 1
        while dst.exists():
            dst, n = self.photos_dir / f"{stem}-{n}{suffix}", n + 1
        shutil.copyfile(src, dst)
        os.chmod(dst, 0o600)
        return str(dst.relative_to(self.data_dir))

    def append(self, meal: Meal) -> None:
        self._ensure_dir(self.data_dir)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(meal.model_dump(mode="json"), ensure_ascii=False) + "\n")
        os.chmod(self.path, 0o600)

    def read(self, *, since: date | None = None, until: date | None = None) -> list[Meal]:
        if not self.path.exists():
            return []
        meals = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            meal = Meal.model_validate_json(line)
            if (since is None or meal.day >= since) and (until is None or meal.day <= until):
                meals.append(meal)
        return sorted(meals, key=lambda m: (m.day, m.at.isoformat() if m.at else ""))

    def last_days(self, days: int, *, today: date) -> list[Meal]:
        return self.read(since=today - timedelta(days=days - 1), until=today)
