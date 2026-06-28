"""Obsidian daily-note projection — the default `ProjectionTarget`.

Writes a `DailyProjection` to a Markdown daily note at
``<vault_health_dir>/YYYY-MM-DD.md`` using YAML frontmatter + prose.

Frontmatter-only-overwrite semantics
------------------------------------
The user owns the prose. The skill owns the frontmatter. This split is
non-negotiable: if a re-emit clobbered the user's prose, the daily-sync
loop would silently destroy hand-written context every time it ran, and
the integration would become hostile.

Concretely, ``emit_daily`` behaves as:

* **New file** — write ``---\\n<frontmatter>\\n---\\n\\n## Notes\\n\\n<scaffold>\\n``,
  ``chmod 0o644``.
* **Existing file with frontmatter** — parse the region between the first
  ``---`` line and the next ``---`` line at column 0; replace ONLY that
  region; leave every byte after the closing ``---`` untouched.
* **Existing file without frontmatter** — prepend
  ``---\\n<frontmatter>\\n---\\n\\n`` above the existing content; do not
  modify the original bytes.

All writes are atomic via a sibling ``.tmp`` file + ``os.replace`` —
a crash mid-write leaves the original file intact.

Not in scope for v1
-------------------
* Writing into Obsidian's graph database / SQLite cache directly.
* Two-way sync (reading user prose back into the trace store).
* YAML round-trip with comments / multi-line strings — frontmatter
  fields are restricted to scalars + a flat list-of-strings.
"""

from __future__ import annotations

import contextlib
import os
import stat
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from broomva_health.domain.results import DailyProjection
from broomva_health.domain.source import Source

__all__ = ["ObsidianDailyNoteProjection"]


_FRONTMATTER_FENCE = "---"
_DEFAULT_PROSE_SCAFFOLD = "## Notes\n\n<!-- prose section — written by the user, not the skill -->\n"
# Field-order is the on-disk YAML order. Keep it stable across versions —
# downstream Dataview queries diff line-by-line and noisy reorders cause
# unrelated commits in the vault git history.
_FIELD_ORDER: tuple[str, ...] = (
    "date",
    "schema_version",
    "source",
    "sources_synced",
    "hrv_overnight_ms",
    "hrv_cv_30d",
    "rhr_bpm",
    "sleep_hours",
    "sleep_score",
    "training_load_ctl",
    "training_load_atl",
    "tsb",
    "vo2_max",
    "body_battery",
    "activities_count",
    "last_activity_type",
    "last_activity_distance_km",
)
# Map the (canonical) frontmatter key onto the DailyProjection attribute.
# Most are identity; `tsb` is the on-disk shorthand for
# `training_load_tsb` (the domain field name) — keeping the YAML compact
# matches what users actually want to query in Dataview.
_FIELD_TO_ATTR: dict[str, str] = {
    "date": "date",
    "schema_version": "schema_version",
    "sources_synced": "sources_synced",
    "hrv_overnight_ms": "hrv_overnight_ms",
    "hrv_cv_30d": "hrv_cv_30d",
    "rhr_bpm": "rhr_bpm",
    "sleep_hours": "sleep_hours",
    "sleep_score": "sleep_score",
    "training_load_ctl": "training_load_ctl",
    "training_load_atl": "training_load_atl",
    "tsb": "training_load_tsb",
    "vo2_max": "vo2_max",
    "body_battery": "body_battery",
    "activities_count": "activities_count",
    "last_activity_type": "last_activity_type",
    "last_activity_distance_km": "last_activity_distance_km",
}
# The package version stamped into the `source:` line — read from the
# package metadata so a release bump propagates without code edits.
try:  # pragma: no cover - importlib.metadata path is environment-dependent
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        _PKG_VERSION = _pkg_version("broomva-health")
    except PackageNotFoundError:
        _PKG_VERSION = "0.1.0"
except ImportError:  # pragma: no cover - importlib.metadata exists on 3.12+
    _PKG_VERSION = "0.1.0"


class ObsidianDailyNoteProjection:
    """Write `DailyProjection`s as Obsidian daily-note Markdown.

    Parameters
    ----------
    vault_health_dir:
        Directory the daily notes live in. Created if missing
        (``parents=True, exist_ok=True``). Typically
        ``~/broomva-vault/07-Health/`` resolved via ``HealthPaths``.
    """

    def __init__(self, vault_health_dir: Path) -> None:
        self._vault_health_dir = Path(vault_health_dir)

    @property
    def vault_health_dir(self) -> Path:
        return self._vault_health_dir

    def emit_daily(self, day: date, projection: DailyProjection) -> Path:
        """Render `projection` into ``<vault_health_dir>/YYYY-MM-DD.md``.

        Idempotent: re-emitting for the same day rewrites only the
        frontmatter region and preserves the user's prose verbatim.
        """
        self._vault_health_dir.mkdir(parents=True, exist_ok=True)
        target = self._vault_health_dir / f"{day.isoformat()}.md"

        frontmatter_body = self._render_frontmatter(projection)
        frontmatter_block = f"{_FRONTMATTER_FENCE}\n{frontmatter_body}{_FRONTMATTER_FENCE}\n"

        is_new = not target.exists()
        if is_new:
            content = f"{frontmatter_block}\n{_DEFAULT_PROSE_SCAFFOLD}"
        else:
            existing = target.read_text(encoding="utf-8")
            content = self._replace_or_prepend_frontmatter(existing, frontmatter_block)

        self._atomic_write(target, content, set_mode=is_new)
        return target

    # ------------------------------------------------------------------
    # Frontmatter parsing / splicing
    # ------------------------------------------------------------------

    @staticmethod
    def _replace_or_prepend_frontmatter(existing: str, frontmatter_block: str) -> str:
        """Splice `frontmatter_block` into `existing` content.

        * If `existing` starts with ``---\\n`` and has a matching closing
          fence, replace ONLY the region between the fences.
        * Otherwise prepend the frontmatter block above the existing
          content (with a blank-line separator so the body still reads).
        """
        lines = existing.splitlines(keepends=True)
        if lines and lines[0].rstrip("\r\n") == _FRONTMATTER_FENCE:
            # find closing fence at column 0
            for idx in range(1, len(lines)):
                if lines[idx].rstrip("\r\n") == _FRONTMATTER_FENCE:
                    body = "".join(lines[idx + 1 :])
                    return frontmatter_block + body
            # No closing fence — treat the whole file as prose and prepend.
        # No frontmatter at all (or unterminated frontmatter) — prepend a
        # fresh block and keep the original bytes immediately after.
        separator = "" if existing.startswith("\n") or existing == "" else "\n"
        return frontmatter_block + separator + existing

    # ------------------------------------------------------------------
    # YAML serialization (scalar + flat list only)
    # ------------------------------------------------------------------

    @classmethod
    def _render_frontmatter(cls, projection: DailyProjection) -> str:
        """Serialize `projection` to YAML frontmatter lines (trailing \\n)."""
        values = cls._collect_values(projection)
        lines: list[str] = []
        for key in _FIELD_ORDER:
            if key not in values:
                continue
            raw = values[key]
            if raw is None:
                # Omit None values entirely — Dataview treats absent and
                # null differently and the user-spec is "omit, not null".
                continue
            lines.append(f"{key}: {cls._format_scalar(raw)}\n")
        return "".join(lines)

    @classmethod
    def _collect_values(cls, projection: DailyProjection) -> dict[str, Any]:
        """Build the (canonical-key -> value) dict the frontmatter renders from."""
        out: dict[str, Any] = {}
        for key in _FIELD_ORDER:
            if key == "source":
                # Always-present stamp: `broomva-health vX.Y.Z` — provenance
                # so a future bookkeeping audit can tell which version of
                # the skill wrote the note.
                out[key] = f"broomva-health v{_PKG_VERSION}"
                continue
            attr = _FIELD_TO_ATTR[key]
            out[key] = getattr(projection, attr)
        return out

    @classmethod
    def _format_scalar(cls, value: Any) -> str:
        """Render a single YAML value (scalar or flat list)."""
        if isinstance(value, bool):
            # bool BEFORE int — bool is a subclass of int in Python and
            # would otherwise be printed as 0/1.
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            # 3-decimal precision per spec. Avoids YAML "0.08299999..."
            # noise that would otherwise spam the vault git history.
            return f"{value:.3f}"
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Source):
            return value.value
        if isinstance(value, str):
            return cls._format_string(value)
        if isinstance(value, (list, tuple)):
            return cls._format_list(value)
        # Defensive: surface unsupported types loudly rather than emit
        # corrupt YAML.
        msg = f"ObsidianDailyNoteProjection cannot serialize {type(value).__name__}: {value!r}"
        raise TypeError(msg)

    @classmethod
    def _format_list(cls, items: Iterable[Any]) -> str:
        """Flat inline list: ``[a, b, c]`` with comma-space separators."""
        rendered = [cls._format_scalar(item) for item in items]
        return "[" + ", ".join(rendered) + "]"

    @staticmethod
    def _format_string(value: str) -> str:
        """Quote strings only when they need it — keep ``easy_run`` and
        ``broomva-health v0.1.0`` bare; quote anything with YAML-active
        punctuation (``:#&*!|>{}[],``) or leading control chars."""
        # YAML reserved tokens that look like scalars but aren't.
        reserved = {"true", "false", "null", "yes", "no", "on", "off", "~", ""}
        if value == "":
            return '""'
        if value.lower() in reserved:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        # Characters whose presence forces quoting because they have
        # syntactic meaning in YAML scalars.
        unsafe_chars = set(":#&*!|>{}[],\"'`\n\r\t")
        if any(ch in unsafe_chars for ch in value):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        # Leading character restrictions.
        if value[0] in "-?@%":
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return value

    # ------------------------------------------------------------------
    # Atomic write
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write(target: Path, content: str, *, set_mode: bool) -> None:
        """Write `content` to `target` atomically.

        Uses sibling ``<target>.tmp`` + ``os.replace`` (POSIX-atomic on
        the same filesystem). On failure the tmp file is cleaned up so we
        never leave half-written droppings next to the real note.
        """
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)
        except BaseException:
            # `os.replace` can raise; clean up the tmp so a retry starts
            # from a clean slate. We swallow the unlink error so the
            # original exception is what bubbles up.
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise
        if set_mode:
            try:
                os.chmod(target, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            except OSError:
                # Filesystem may not support chmod (e.g., FAT). Mode is a
                # nice-to-have, never load-bearing for correctness.
                pass
