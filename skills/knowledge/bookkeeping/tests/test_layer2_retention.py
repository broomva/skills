"""Layer-2 raw-extract retention window (BRO-1991).

CLAUDE.md has always specified "Layer 2 — Raw Extracts ... Retained 30 days,
then archived", but nothing implemented it. Measured on the live workspace when
this landed: 20 of 26 extracts were past the window, the oldest at 111 days, and
7 of the 9 notes feeding the most recent auto-mint batch were stale (58-111d).

The consequence was a loop with no exit: every scheduled run re-ingested the
April notes and re-promoted fragments from them, so deleting the minted entity
pages never stuck.
"""
from datetime import date

import pytest

import bookkeeping
from bookkeeping import raw_extract_age_days, run_archive

TODAY = date(2026, 7, 26)


def _note(notes_dir, name: str, body: str = "---\nsource: test\n---\n\n# note\n"):
    p = notes_dir / name
    p.write_text(body)
    return p


@pytest.fixture
def notes_dir(tmp_path, monkeypatch):
    d = tmp_path / "research" / "notes"
    d.mkdir(parents=True)
    monkeypatch.setattr(bookkeeping, "NOTES_DIR", d)
    return d


class TestAgeDerivation:
    def test_age_from_filename_date(self, notes_dir):
        p = _note(notes_dir, "2026-04-06-social-insights-raw.md")
        assert raw_extract_age_days(p, today=TODAY) == 111

    def test_filename_date_beats_mtime(self, notes_dir):
        """The logical date must win — mtime changes on checkout/rebase/copy,
        which would make retention depend on git operations."""
        p = _note(notes_dir, "2026-04-06-social-insights-raw.md")
        import os
        os.utime(p, (0, 0))  # mtime = 1970
        assert raw_extract_age_days(p, today=TODAY) == 111

    def test_undated_falls_back_to_mtime(self, notes_dir):
        p = _note(notes_dir, "notes-raw.md")
        # This branch intentionally derives age from the file's real mtime.
        # Comparing that mtime to the historical fixture date makes the test
        # go negative as soon as wall-clock time advances past TODAY.
        age = raw_extract_age_days(p, today=date.today())
        assert age is not None and age >= 0

    def test_impossible_date_returns_none(self, notes_dir):
        """An unparseable date must NOT be archived by guesswork."""
        p = _note(notes_dir, "2026-13-45-bogus-raw.md")
        assert raw_extract_age_days(p, today=TODAY) is None


class TestArchiveWindow:
    def test_dry_run_moves_nothing(self, notes_dir):
        old = _note(notes_dir, "2026-04-06-old-raw.md")
        aged = run_archive(days=30, apply=False, notes_dir=notes_dir, today=TODAY)
        assert [p.name for p, _ in aged] == ["2026-04-06-old-raw.md"]
        assert old.exists(), "dry-run must not move files"
        assert not (notes_dir / "archive").exists()

    def test_apply_moves_only_aged(self, notes_dir):
        old = _note(notes_dir, "2026-04-06-old-raw.md")
        fresh = _note(notes_dir, "2026-07-20-fresh-raw.md")
        run_archive(days=30, apply=True, notes_dir=notes_dir, today=TODAY)
        assert not old.exists()
        assert (notes_dir / "archive" / "2026-04-06-old-raw.md").exists()
        assert fresh.exists(), "a note inside the window must be left alone"

    def test_boundary_is_strictly_greater(self, notes_dir):
        """Exactly at the window is retained; one day past is archived."""
        at = _note(notes_dir, "2026-06-26-at-window-raw.md")   # exactly 30d
        past = _note(notes_dir, "2026-06-25-past-window-raw.md")  # 31d
        assert raw_extract_age_days(at, today=TODAY) == 30
        assert raw_extract_age_days(past, today=TODAY) == 31
        run_archive(days=30, apply=True, notes_dir=notes_dir, today=TODAY)
        assert at.exists()
        assert not past.exists()

    def test_archives_move_never_delete(self, notes_dir):
        body = "---\nsource: test\n---\n\nirreplaceable content\n"
        _note(notes_dir, "2026-04-06-old-raw.md", body)
        run_archive(days=30, apply=True, notes_dir=notes_dir, today=TODAY)
        assert (notes_dir / "archive" / "2026-04-06-old-raw.md").read_text() == body

    def test_existing_archived_note_is_not_clobbered(self, notes_dir):
        (notes_dir / "archive").mkdir()
        (notes_dir / "archive" / "2026-04-06-old-raw.md").write_text("ORIGINAL")
        _note(notes_dir, "2026-04-06-old-raw.md", "NEWER DUPLICATE")
        run_archive(days=30, apply=True, notes_dir=notes_dir, today=TODAY)
        assert (notes_dir / "archive" / "2026-04-06-old-raw.md").read_text() == "ORIGINAL"

    def test_only_raw_extracts_are_touched(self, notes_dir):
        """Layer-4 synthesis notes are permanent — retention applies to Layer 2."""
        synth = _note(notes_dir, "2026-04-06-topic-synthesis.md")
        run_archive(days=30, apply=True, notes_dir=notes_dir, today=TODAY)
        assert synth.exists()

    def test_undated_file_is_left_alone(self, notes_dir):
        p = _note(notes_dir, "2026-13-45-bogus-raw.md")
        run_archive(days=30, apply=True, notes_dir=notes_dir, today=TODAY)
        assert p.exists(), "an unparseable name must never be archived by guesswork"


class TestProvenanceSurvivesArchiving:
    """The claim made in BRO-1991: archiving cannot break entity provenance,
    because `sources:` values are note BASENAMES, not paths. Pinned here so a
    future change to provenance format cannot silently invalidate it."""

    def test_sources_are_basenames_not_paths(self, notes_dir, tmp_path, monkeypatch):
        entities = tmp_path / "research" / "entities"
        for et in bookkeeping.ENTITY_TYPES:
            (entities / et).mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
        monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
        monkeypatch.setattr(bookkeeping, "CONFIG_DIR", tmp_path / ".config")
        monkeypatch.setattr(bookkeeping, "RUN_LOG", tmp_path / ".config" / "run-log.jsonl")
        monkeypatch.setattr(bookkeeping, "STATUS_CACHE", tmp_path / ".config" / "status.json")

        # Dated recently so it scores above threshold (the scorer penalises
        # stale sources); aged past the window below via an explicit `today`,
        # so this test exercises ARCHIVING rather than scoring.
        _note(
            notes_dir,
            "2026-07-20-fresh-raw.md",
            "---\nsource: test\n---\n\n"
            "## Item 1 — @someone (web)\n\n"
            "**Score**: 7/9 — novelty:3 specificity:2 relevance:2\n\n"
            "**Our angle**: The arcan agent loop uses bi-temporal event sourcing "
            "because the soul file must replay deterministically; this means the "
            "promotion gate and memory provenance stay consistent across 1000 runs.\n",
        )
        bookkeeping.run_pipeline(verbose=False)
        pages = list(entities.rglob("*.md"))
        assert pages, "fixture must promote at least one entity"

        before = {p: p.read_text() for p in pages}
        for text in before.values():
            assert "2026-07-20-fresh-raw" in text
            assert "research/notes" not in text, (
                "provenance recorded a PATH — archiving would break it"
            )

        # 43 days after the note's date — past the window.
        run_archive(days=30, apply=True, notes_dir=notes_dir, today=date(2026, 9, 1))
        assert (notes_dir / "archive" / "2026-07-20-fresh-raw.md").exists()

        for p, text in before.items():
            assert p.read_text() == text, "archiving must not rewrite entity pages"


class TestStructuralFragmentRejected:
    """A claim opening with a structural glyph is a document fragment the
    markdown stripper failed to shed, not a proposition (BRO-1991).

    Observed live: `pattern/environment-contract` carried
    "→ In our taxonomy: an arm-B system."

    Measured against all 804 committed pages before shipping: 0 flagged. That
    is why this is safe as a hard gate, whereas the semantic "does the claim
    mention its slug?" check — 36% flagged on the same corpus — is not.
    """

    FRAGMENTS = [
        "→ In our taxonomy: an arm-B system.",
        "» continuation of the previous point about substrates.",
        "- a bullet that was never a sentence in the first place.",
        "* another bullet masquerading as a claim here.",
        "• a third bullet form that should also be refused.",
        "| cell one | cell two | cell three | cell four |",
        "> a blockquote lifted straight out of the source document.",
        "# A heading that is not a claim about anything at all.",
        "1. the first item of an enumerated list of things.",
    ]

    @pytest.mark.parametrize("frag", FRAGMENTS)
    def test_fragment_is_not_an_acceptable_claim(self, frag):
        assert not bookkeeping._claim_is_acceptable(frag, bookkeeping._CORE_CLAIM_MAX)

    def test_real_claims_still_accepted(self):
        """Control — the gate must not eat legitimate claims."""
        good = [
            "A gate whose producer can trivially satisfy it verifies nothing.",
            "Firecracker is the only agent-sandbox substrate where snapshot-restore ships.",
            "2026-era agents need per-level observability to lift the asymptote.",
        ]
        for c in good:
            assert bookkeeping._claim_is_acceptable(c, bookkeeping._CORE_CLAIM_MAX), c

    def test_derive_skips_fragment_and_finds_the_real_sentence(self):
        body = (
            "→ In our taxonomy: an arm-B system.\n\n"
            "Arm-B systems delegate verification to an out-of-band observer, "
            "which is what keeps the judgement independent of the actor.\n"
        )
        claim = bookkeeping.derive_core_claim(body)
        assert claim is not None
        assert not claim.startswith("→")
        assert "out-of-band observer" in claim
