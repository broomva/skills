"""Tests for adapters.projections.obsidian.

These tests pin the public contract of `ObsidianDailyNoteProjection`:

* New file: full template (frontmatter + ``## Notes`` scaffold).
* Existing file with frontmatter: frontmatter region replaced, prose
  byte-for-byte preserved.
* Existing file without frontmatter: frontmatter prepended; original
  content unchanged.
* ``None`` values omit the key entirely (not ``key: null``).
* Re-emit is idempotent — the prose survives every subsequent run.
* Floats clamp to 3 decimal places.
* ``sources_synced`` serializes as an inline list (``[garmin, oura]``).
* Write is atomic — a crash in ``os.replace`` leaves the original file
  untouched and the ``.tmp`` sibling cleaned up.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from broomva_health.adapters.projections.obsidian import ObsidianDailyNoteProjection
from broomva_health.domain.results import DailyProjection
from broomva_health.domain.source import Source

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _projection(**overrides: object) -> DailyProjection:
    """Build a fully-populated DailyProjection; overrides win field-by-field."""
    defaults: dict[str, object] = {
        "date": date(2026, 5, 22),
        "sources_synced": [Source.GARMIN],
        "hrv_overnight_ms": 58.0,
        "hrv_cv_30d": 0.083,
        "rhr_bpm": 47.0,
        "sleep_hours": 7.4,
        "sleep_score": 81.0,
        "training_load_ctl": 71.0,
        "training_load_atl": 64.0,
        "training_load_tsb": 7.0,
        "vo2_max": 56.0,
        "body_battery": 64.0,
        "activities_count": 1,
        "last_activity_type": "easy_run",
        "last_activity_distance_km": 8.2,
    }
    defaults.update(overrides)
    return DailyProjection(**defaults)  # type: ignore[arg-type]


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_lines_without_fences, body_after_closing_fence)."""
    lines = text.splitlines(keepends=True)
    assert lines[0].rstrip("\r\n") == "---", f"file does not start with fence: {lines[:1]!r}"
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\r\n") == "---":
            return "".join(lines[1:idx]), "".join(lines[idx + 1 :])
    raise AssertionError(f"no closing fence in:\n{text}")


# ---------------------------------------------------------------------------
# New-file behavior
# ---------------------------------------------------------------------------


def test_new_file_creates_frontmatter_and_scaffold(tmp_path: Path) -> None:
    target_dir = tmp_path / "vault" / "07-Health"
    projection = _projection()

    adapter = ObsidianDailyNoteProjection(target_dir)
    written = adapter.emit_daily(projection.date, projection)

    assert written == target_dir / "2026-05-22.md"
    assert written.exists(), "emit_daily must create the file"
    content = written.read_text(encoding="utf-8")

    fm, body = _split_frontmatter(content)
    # frontmatter contains every populated field. Float precision is
    # `f"{value:.3f}"` per the spec — including integer-valued floats
    # like rhr_bpm=47.0 → "47.000". The `int` rendering only applies to
    # actual `int` fields (activities_count, schema_version).
    assert "date: 2026-05-22\n" in fm
    assert "schema_version: 1\n" in fm
    assert "source: broomva-health v" in fm
    assert "sources_synced: [garmin]\n" in fm
    assert "hrv_overnight_ms: 58.000\n" in fm
    assert "hrv_cv_30d: 0.083\n" in fm
    assert "rhr_bpm: 47.000\n" in fm
    assert "sleep_hours: 7.400\n" in fm
    assert "sleep_score: 81.000\n" in fm
    assert "training_load_ctl: 71.000\n" in fm
    assert "training_load_atl: 64.000\n" in fm
    assert "tsb: 7.000\n" in fm
    assert "vo2_max: 56.000\n" in fm
    assert "body_battery: 64.000\n" in fm
    assert "activities_count: 1\n" in fm
    assert "last_activity_type: easy_run\n" in fm
    assert "last_activity_distance_km: 8.200\n" in fm

    # scaffold body present, anchored on the canonical heading
    assert "## Notes" in body
    assert "<!-- prose section" in body


def test_new_file_has_0o644_mode(tmp_path: Path) -> None:
    adapter = ObsidianDailyNoteProjection(tmp_path / "vault")
    projection = _projection()
    written = adapter.emit_daily(projection.date, projection)

    mode = written.stat().st_mode & 0o777
    # 0o644 is the documented contract; tolerate filesystems that mask
    # group/other bits but the owner-write bit must hold.
    assert mode & 0o600 == 0o600, f"expected owner rw, got {mode:o}"


def test_creates_vault_directory_if_missing(tmp_path: Path) -> None:
    target_dir = tmp_path / "nested" / "vault" / "07-Health"
    assert not target_dir.exists()

    adapter = ObsidianDailyNoteProjection(target_dir)
    adapter.emit_daily(date(2026, 5, 22), _projection())

    assert target_dir.is_dir()


# ---------------------------------------------------------------------------
# Existing-file behavior
# ---------------------------------------------------------------------------


def test_existing_file_with_frontmatter_updates_only_frontmatter(tmp_path: Path) -> None:
    target_dir = tmp_path / "vault"
    target_dir.mkdir()
    note = target_dir / "2026-05-22.md"
    # Pre-existing file with custom prose the user has written.
    note.write_text(
        "---\n"
        "date: 2026-05-22\n"
        "rhr_bpm: 99\n"
        "---\n\n"
        "## Notes\n\n"
        "Felt great after the long run. PR'd the 5k segment.\n"
        "Heart rate dipped in the last mile — likely caffeine timing.\n",
        encoding="utf-8",
    )

    adapter = ObsidianDailyNoteProjection(target_dir)
    adapter.emit_daily(date(2026, 5, 22), _projection(rhr_bpm=47.0))

    new_text = note.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(new_text)

    # frontmatter took the new value (rendered via :.3f)
    assert "rhr_bpm: 47.000\n" in fm
    assert "rhr_bpm: 99\n" not in fm
    assert "rhr_bpm: 99.000\n" not in fm
    # prose is preserved exactly — including blank-line spacing
    assert body == (
        "\n## Notes\n\n"
        "Felt great after the long run. PR'd the 5k segment.\n"
        "Heart rate dipped in the last mile — likely caffeine timing.\n"
    )


def test_existing_file_without_frontmatter_prepends(tmp_path: Path) -> None:
    target_dir = tmp_path / "vault"
    target_dir.mkdir()
    note = target_dir / "2026-05-22.md"
    original = (
        "# Random journal entry\n\n"
        "I started writing here before installing the skill.\n"
        "Nothing structured yet.\n"
    )
    note.write_text(original, encoding="utf-8")

    adapter = ObsidianDailyNoteProjection(target_dir)
    adapter.emit_daily(date(2026, 5, 22), _projection())

    text = note.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "frontmatter must be prepended"
    # Original content survives verbatim somewhere after the closing fence.
    _, body = _split_frontmatter(text)
    assert original in body


def test_existing_file_with_unterminated_frontmatter_prepends(tmp_path: Path) -> None:
    """A leading `---` with no closing fence is treated as raw prose."""
    target_dir = tmp_path / "vault"
    target_dir.mkdir()
    note = target_dir / "2026-05-22.md"
    original = "---\nthis was never closed\nand should be left alone\n"
    note.write_text(original, encoding="utf-8")

    adapter = ObsidianDailyNoteProjection(target_dir)
    adapter.emit_daily(date(2026, 5, 22), _projection())

    text = note.read_text(encoding="utf-8")
    # Must have a fresh frontmatter block on top and a closing fence.
    assert text.startswith("---\n")
    _, body = _split_frontmatter(text)
    assert original in body


# ---------------------------------------------------------------------------
# Value-shaping rules
# ---------------------------------------------------------------------------


def test_none_values_are_omitted_from_frontmatter(tmp_path: Path) -> None:
    adapter = ObsidianDailyNoteProjection(tmp_path / "vault")
    projection = _projection(
        hrv_overnight_ms=None,
        hrv_cv_30d=None,
        vo2_max=None,
    )

    written = adapter.emit_daily(projection.date, projection)
    text = written.read_text(encoding="utf-8")
    fm, _ = _split_frontmatter(text)

    # The dropped keys must not appear at all — neither as `key: null`
    # nor as `key:`.
    assert "hrv_overnight_ms" not in fm
    assert "hrv_cv_30d" not in fm
    assert "vo2_max" not in fm
    # ... but the populated keys still survive.
    assert "rhr_bpm: 47.000\n" in fm


def test_idempotent_re_emit_preserves_prose(tmp_path: Path) -> None:
    adapter = ObsidianDailyNoteProjection(tmp_path / "vault")
    projection = _projection()

    written = adapter.emit_daily(projection.date, projection)

    # Simulate the user editing the prose.
    text = written.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    user_prose = body + "\n- Additional context the user typed.\n"
    written.write_text(f"---\n{fm}---\n{user_prose}", encoding="utf-8")

    # Re-emit with a slightly different projection.
    adapter.emit_daily(projection.date, _projection(rhr_bpm=48.0))

    after = written.read_text(encoding="utf-8")
    fm_after, body_after = _split_frontmatter(after)

    # Frontmatter reflects the new value (rendered via :.3f).
    assert "rhr_bpm: 48.000\n" in fm_after
    # Prose is preserved exactly.
    assert body_after == user_prose

    # A second re-emit with the SAME projection must be byte-stable.
    adapter.emit_daily(projection.date, _projection(rhr_bpm=48.0))
    stable = written.read_text(encoding="utf-8")
    assert stable == after, "third emit must equal second emit"


def test_floats_have_stable_precision(tmp_path: Path) -> None:
    adapter = ObsidianDailyNoteProjection(tmp_path / "vault")
    projection = _projection(hrv_cv_30d=0.0831234)

    written = adapter.emit_daily(projection.date, projection)
    text = written.read_text(encoding="utf-8")

    assert "hrv_cv_30d: 0.083\n" in text
    assert "0.0831234" not in text


def test_sources_synced_serialized_inline(tmp_path: Path) -> None:
    adapter = ObsidianDailyNoteProjection(tmp_path / "vault")
    projection = _projection(sources_synced=[Source.GARMIN, Source.OURA])

    written = adapter.emit_daily(projection.date, projection)
    text = written.read_text(encoding="utf-8")

    assert "sources_synced: [garmin, oura]\n" in text


def test_single_source_still_inline_list(tmp_path: Path) -> None:
    """Even a one-element list uses inline `[x]` form."""
    adapter = ObsidianDailyNoteProjection(tmp_path / "vault")
    projection = _projection(sources_synced=[Source.WHOOP])

    written = adapter.emit_daily(projection.date, projection)
    text = written.read_text(encoding="utf-8")

    assert "sources_synced: [whoop]\n" in text


def test_empty_sources_synced_serialized_as_empty_list(tmp_path: Path) -> None:
    adapter = ObsidianDailyNoteProjection(tmp_path / "vault")
    projection = _projection(sources_synced=[])

    written = adapter.emit_daily(projection.date, projection)
    text = written.read_text(encoding="utf-8")

    assert "sources_synced: []\n" in text


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


def test_atomic_write_no_partial_file_on_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing `os.replace` must leave the original file intact and clean up the tmp."""
    target_dir = tmp_path / "vault"
    target_dir.mkdir()
    note = target_dir / "2026-05-22.md"

    original_content = "---\nschema_version: 1\nrhr_bpm: 50\n---\n\n## Notes\n\nOriginal prose.\n"
    note.write_text(original_content, encoding="utf-8")
    original_bytes = note.read_bytes()

    # Monkeypatch os.replace inside the adapter module to raise after the
    # tmp file has been written and fsynced.
    import broomva_health.adapters.projections.obsidian as mod

    def boom(_src: object, _dst: object) -> None:
        msg = "simulated disk failure"
        raise OSError(msg)

    monkeypatch.setattr(mod.os, "replace", boom)

    adapter = ObsidianDailyNoteProjection(target_dir)

    with pytest.raises(OSError, match="simulated disk failure"):
        adapter.emit_daily(date(2026, 5, 22), _projection(rhr_bpm=99.0))

    # The original file must be byte-identical — no partial overwrite.
    assert note.read_bytes() == original_bytes

    # The .tmp sibling must have been cleaned up so a retry starts fresh.
    leftovers = [p.name for p in target_dir.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == [], f"orphaned tmp files: {leftovers}"


def test_returns_written_path(tmp_path: Path) -> None:
    adapter = ObsidianDailyNoteProjection(tmp_path / "vault")
    projection = _projection()

    written = adapter.emit_daily(projection.date, projection)

    assert isinstance(written, Path)
    assert written == tmp_path / "vault" / "2026-05-22.md"
