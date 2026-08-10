"""Tests for the typed temporal revision envelope — PRODUCER side (gh-156).

The shipped `lint --temporal` audit is a detector. This phase builds the write
path that gives it something typed to check, under one governing rule: no
envelope field may be produced by reading prose.

Coverage mirrors the acceptance contract on gh-156 — creation, update,
correction, malformed links, and idempotent replay — plus the negative
invariants that keep the schema honest: `valid_from` is never guessed,
`supersedes` is never inferred, default lint is unchanged, and every new
finding is a warning.
"""
import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

import bookkeeping
from bookkeeping import (
    RawItem,
    ScoredItem,
    _lint_temporal_drift,
    _render_updated_entity,
    _set_frontmatter_scalar,
    _split_frontmatter,
    _strip_volatile_fields,
    _supplied_valid_from,
    _update_entity_page_if_changed,
    cmd_merge,
    cmd_revise,
    lint_entity_page,
    promote_item,
)


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bookkeeping.py"
AUDIT_DATE = date(2026, 8, 10)
TODAY = "2026-08-10"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_entities(tmp_path, monkeypatch):
    """research/entities/ under tmp_path, with the module globals patched."""
    entities = tmp_path / "research" / "entities"
    for et in bookkeeping.ENTITY_TYPES:
        (entities / et).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
    monkeypatch.setattr(bookkeeping, "NOTES_DIR", tmp_path / "research" / "notes")
    return entities


@pytest.fixture
def frozen_today(monkeypatch):
    """Pin system time so `recorded_at` is assertable and replay is byte-stable."""
    monkeypatch.setattr(bookkeeping, "today_str", lambda: TODAY)
    return TODAY


def _scored(content="A novel claim about arcan and lago memory.", metadata=None,
            timestamp="2026-05-28T00:00:00+00:00"):
    item = RawItem(
        item_id="abcd1234",
        source_id="2026-05-28-test-raw",
        source_type="research",
        content=content,
        quote="quoted",
        author="",
        timestamp=timestamp,
        metadata=metadata if metadata is not None else {},
    )
    return ScoredItem(
        item=item,
        novelty=2, specificity=2, relevance=2, total=6,
        promote=True,
        candidate_entities=["test-entity"],
        scoring_method="heuristic",
        reasoning={},
    )


def _write_entity(entities, slug, type_dir="concept", extra="", body="Body text.\n",
                  claim="A claim about the system."):
    """Write a minimal, lint-clean entity page. `extra` goes into frontmatter."""
    p = entities / type_dir / f"{slug}.md"
    p.write_text(
        f"---\nslug: {slug}\ntype: {type_dir}\nstatus: entity\n"
        f'core_claim: "{claim}"\n'
        f"sources:\n  - 2026-01-01-source\n"
        f"related: []\ncreated: 2026-01-01\nupdated: 2026-01-01\n{extra}"
        f"tags:\n  - {type_dir}\n  - bookkeeping\n---\n\n# {slug}\n\n{body}"
    )
    return p


def _fields(errors):
    return sorted(e.field for e in errors)


def _lint_envelope(fm, *, lookup=None, audit_date=AUDIT_DATE):
    """Run the opt-in temporal audit on frontmatter alone, with a hermetic lookup."""
    return _lint_temporal_drift(
        "entity.md", fm, "",
        audit_date=audit_date,
        entity_lookup=lookup if lookup is not None else (lambda _slug: {}),
    )


# ── Creation: recorded_at is mechanical, valid_from is supplied ───────────────

class TestCreationProducer:
    def test_promotion_stamps_recorded_at_with_system_time(
            self, temp_entities, frozen_today):
        path = promote_item(_scored(), "typed-envelope", entity_type="concept")
        assert path is not None
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert str(fm["recorded_at"]) == TODAY

    def test_recorded_at_is_emitted_quoted_so_it_round_trips(
            self, temp_entities, frozen_today):
        # An unquoted YAML date re-serializes to a full timestamp on the next
        # edit; the existing unquoted-date lint would flag it as a new warning
        # on every promoted page.
        path = promote_item(_scored(), "quoted-stamp", entity_type="concept")
        assert f'recorded_at: "{TODAY}"' in path.read_text()
        dates = [e for e in lint_entity_page(path) if "unquoted date" in e.message]
        assert not [e for e in dates if e.field == "recorded_at"], \
            "recorded_at must not trip the unquoted-date lint"

    def test_promotion_omits_valid_from_when_the_source_supplies_none(
            self, temp_entities, frozen_today):
        path = promote_item(_scored(), "envelope-without-effective-date", entity_type="concept")
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert "valid_from" not in fm
        assert "valid_from" not in path.read_text()

    def test_promotion_writes_an_explicitly_supplied_valid_from(
            self, temp_entities, frozen_today):
        scored = _scored(metadata={"valid_from": "2026-03-01"})
        path = promote_item(scored, "effective-date-supplied", entity_type="concept")
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert str(fm["valid_from"]) == "2026-03-01"
        assert 'valid_from: "2026-03-01"' in path.read_text()

    def test_valid_from_is_never_inferred_from_prose_or_ingest_time(
            self, temp_entities, frozen_today):
        # The content is saturated with dates and the item carries an ingest
        # timestamp. NONE of it may become a claim-effective time.
        scored = _scored(
            content="Effective 2025-01-01, superseding the 2024-06-06 decision; "
                    "as of 2026-02-02 this is current.",
            timestamp="2026-05-28T00:00:00+00:00",
        )
        path = promote_item(scored, "prose-date-saturation", entity_type="concept")
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert "valid_from" not in fm

    def test_malformed_supplied_valid_from_is_dropped_not_coerced(
            self, temp_entities, frozen_today):
        scored = _scored(metadata={"valid_from": "last Tuesday"})
        path = promote_item(scored, "malformed-effective-date", entity_type="concept")
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert "valid_from" not in fm, "an unparseable value must be omitted, not guessed"

    def test_supplied_valid_from_reads_only_the_canonical_metadata_key(self):
        item = _scored(metadata={"validFrom": "2026-03-01",
                                 "effective_date": "2026-03-01"}).item
        assert _supplied_valid_from(item) is None, \
            "near-miss keys must not be fuzzily accepted — that is guessing"

    def test_promotion_never_claims_a_supersession(
            self, temp_entities, frozen_today):
        scored = _scored(content="This supersedes the earlier arcan decision "
                                 "and replaces lago-event-journal entirely.")
        path = promote_item(scored, "supersession-prose", entity_type="concept")
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert "supersedes" not in fm and "revision_link" not in fm

    def test_promoted_page_lints_clean_by_default(self, temp_entities, frozen_today):
        path = promote_item(_scored(), "clean-page", entity_type="concept")
        hard = [e for e in lint_entity_page(path) if e.severity == "error"]
        assert not hard, f"promoted page must lint clean, got: {hard}"


# ── Update path: no churn, no backfill ───────────────────────────────────────

class TestUpdatePathAndIdempotentReplay:
    def test_recorded_at_is_volatile_for_the_content_identity_guard(self):
        a = '---\nslug: x\nupdated: 2026-01-01\nrecorded_at: "2026-01-01"\n---\nbody\n'
        b = '---\nslug: x\nupdated: 2026-08-10\nrecorded_at: "2026-08-10"\n---\nbody\n'
        assert _strip_volatile_fields(a) == _strip_volatile_fields(b)

    def test_replay_of_an_unchanged_page_writes_nothing(
            self, temp_entities, frozen_today):
        path = promote_item(_scored(), "replay-target", entity_type="concept")
        first = path.read_text()
        second = promote_item(_scored(), "replay-target", entity_type="concept")
        assert second is None, "a no-delta update must report no write"
        assert path.read_text() == first, "replay must be byte-identical"

    def test_replay_on_a_later_day_still_writes_nothing(
            self, temp_entities, monkeypatch):
        monkeypatch.setattr(bookkeeping, "today_str", lambda: "2026-08-10")
        path = promote_item(_scored(), "replay-later", entity_type="concept")
        first = path.read_text()
        monkeypatch.setattr(bookkeeping, "today_str", lambda: "2026-09-30")
        assert promote_item(_scored(), "replay-later", entity_type="concept") is None
        assert path.read_text() == first, \
            "recorded_at must track substantive change, not the run date"

    def test_render_restamps_recorded_at_when_present(self, frozen_today):
        existing = '---\nslug: x\nupdated: 2026-01-01\nrecorded_at: "2026-01-01"\n---\nbody\n'
        out = _render_updated_entity(existing)
        assert f'recorded_at: "{TODAY}"' in out
        assert f"updated: {TODAY}" in out

    def test_render_does_not_backfill_recorded_at_onto_a_legacy_page(
            self, frozen_today):
        # Asserted on the seam itself, not through the content-identity guard:
        # the guard strips `recorded_at` as volatile, so it would mask a
        # backfill on a no-delta page and only leak it onto pages that happen
        # to acquire an unrelated edit — mis-stamping today as the system time
        # of a claim recorded long before.
        existing = '---\nslug: x\nupdated: 2026-01-01\n---\nbody\n'
        out = _render_updated_entity(existing)
        assert "recorded_at" not in out
        assert f"updated: {TODAY}" in out

    def test_legacy_page_without_recorded_at_is_not_backfilled(
            self, temp_entities, frozen_today):
        # A backfill here would be a semantic delta on every pre-envelope page
        # at once, rewriting the whole graph and stamping today as the system
        # time of claims recorded long ago.
        path = _write_entity(temp_entities, "legacy")
        before = path.read_text()
        assert _update_entity_page_if_changed(path) is False
        assert path.read_text() == before
        assert "recorded_at" not in path.read_text()

    def test_real_semantic_delta_still_writes(self, temp_entities, frozen_today):
        path = _write_entity(temp_entities, "delta", extra='recorded_at: "2026-01-01"\n')
        # A change the renderer WOULD introduce is what the guard exists to
        # detect; simulate one by pointing the seam at a body-touching render.
        original = _render_updated_entity
        try:
            bookkeeping._render_updated_entity = (
                lambda text: original(text) + "\nAppended semantic content.\n")
            assert _update_entity_page_if_changed(path) is True
        finally:
            bookkeeping._render_updated_entity = original
        text = path.read_text()
        assert f'recorded_at: "{TODAY}"' in text and f"updated: {TODAY}" in text


# ── Frontmatter surgery must never corrupt the document ──────────────────────

class TestFrontmatterWriter:
    def test_insert_before_closing_fence_does_not_swallow_a_trailing_block_list(self):
        text = ('---\nslug: x\ntags:\n  - a\n  - b\n---\n\n# Body\n')
        out = _set_frontmatter_scalar(text, "recorded_at", '"2026-08-10"')
        fm, body = _split_frontmatter(out)
        assert fm.count("---") == 2, f"fence corrupted: {out!r}"
        assert body.strip() == "# Body"
        parsed, _ = bookkeeping.parse_frontmatter(out)
        assert parsed["tags"] == ["a", "b"]
        assert str(parsed["recorded_at"]) == "2026-08-10"

    def test_replacing_a_block_list_key_does_not_orphan_its_items(self):
        text = ('---\nslug: x\nsupersedes:\n  - "[[old-a]]"\n  - "[[old-b]]"\n'
                'related: []\n---\nbody\n')
        out = _set_frontmatter_scalar(text, "supersedes", '["[[new]]"]')
        parsed, _ = bookkeeping.parse_frontmatter(out)
        assert parsed["supersedes"] == ["[[new]]"]
        assert parsed["related"] == []

    def test_a_body_line_starting_with_the_key_is_preserved(self):
        text = '---\nslug: x\nupdated: 2026-01-01\n---\nrecorded_at: not frontmatter\n'
        out = _set_frontmatter_scalar(text, "recorded_at", '"2026-08-10"')
        assert out.endswith("recorded_at: not frontmatter\n")

    def test_document_without_frontmatter_is_returned_unchanged(self):
        text = "# Just a body\n"
        assert _set_frontmatter_scalar(text, "recorded_at", '"2026-08-10"') == text


# ── Explicit correction flow ─────────────────────────────────────────────────

def _revise_args(entity, supersedes, link="https://example.test/decision/1",
                 valid_from=None, dry_run=False):
    return argparse.Namespace(
        entity=entity, supersedes=supersedes, revision_link=link,
        valid_from=valid_from, dry_run=dry_run,
    )


class TestReviseCommand:
    def test_revise_emits_supersedes_and_revision_link(
            self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert fm["supersedes"] == ["[[old-belief]]"]
        assert fm["revision_link"] == "https://example.test/decision/1"
        assert str(fm["recorded_at"]) == TODAY
        assert str(fm["updated"]) == TODAY

    def test_revise_is_idempotent_on_replay(self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        first = path.read_text()
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        assert path.read_text() == first, "re-applying a revision must not churn"

    def test_a_second_revision_unions_rather_than_replaces(
            self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-a")
        _write_entity(temp_entities, "old-b")
        path = _write_entity(temp_entities, "current")
        cmd_revise(_revise_args("current", ["old-a"]))
        cmd_revise(_revise_args("current", ["old-b"], link="ticket://BRO-2"))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert fm["supersedes"] == ["[[old-a]]", "[[old-b]]"], \
            "a later revision must not drop what an earlier one recorded"
        assert fm["revision_link"] == "ticket://BRO-2"

    def test_revise_writes_an_operator_supplied_valid_from(
            self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        cmd_revise(_revise_args("new-belief", ["old-belief"], valid_from="2026-04-15"))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert str(fm["valid_from"]) == "2026-04-15"

    def test_revise_omits_valid_from_when_the_flag_is_absent(
            self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert "valid_from" not in fm

    def test_revise_backfills_recorded_at_on_a_legacy_page(
            self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "legacy-current")
        assert "recorded_at" not in path.read_text()
        cmd_revise(_revise_args("legacy-current", ["old-belief"]))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert str(fm["recorded_at"]) == TODAY, \
            "an explicit revision is the sanctioned path to acquire the envelope"

    def test_revise_accepts_comma_separated_and_repeated_slugs(
            self, temp_entities, frozen_today):
        for slug in ("old-a", "old-b", "old-c"):
            _write_entity(temp_entities, slug)
        path = _write_entity(temp_entities, "current")
        cmd_revise(_revise_args("current", ["old-a,old-b", "old-c"]))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert fm["supersedes"] == ["[[old-a]]", "[[old-b]]", "[[old-c]]"]

    def test_revise_preserves_body_and_lints_clean(self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief", body="Load-bearing prose.\n")
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        text = path.read_text()
        assert "Load-bearing prose." in text
        hard = [e for e in lint_entity_page(path) if e.severity == "error"]
        assert not hard, f"revised page must lint clean, got: {hard}"

    def test_revise_dry_run_writes_nothing(self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        before = path.read_text()
        cmd_revise(_revise_args("new-belief", ["old-belief"], dry_run=True))
        assert path.read_text() == before

    @pytest.mark.parametrize("entity,targets,valid_from", [
        ("missing-entity", ["old-belief"], None),   # revising entity absent
        ("new-belief", ["nonexistent"], None),      # superseded target absent
        ("new-belief", ["new-belief"], None),       # self-supersession
        ("new-belief", ["old-belief"], "someday"),  # unparseable valid_from
        ("new-belief", [","], None),                # no usable slug
    ])
    def test_revise_refuses_unresolvable_or_malformed_input(
            self, temp_entities, frozen_today, entity, targets, valid_from):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        before = path.read_text()
        with pytest.raises(SystemExit) as exc:
            cmd_revise(_revise_args(entity, targets, valid_from=valid_from))
        assert exc.value.code != 0
        assert path.read_text() == before, "a refused revision must not write"


class TestMergeRecordsTypedRevision:
    def _write(self, entities, slug, type_dir="tool", status="entity"):
        p = entities / type_dir / f"{slug}.md"
        p.write_text(
            f"---\nslug: {slug}\ntype: {type_dir}\nstatus: {status}\n"
            f'core_claim: "A claim about {slug}."\nsources:\n  - 2026-01-01-s\n'
            f"---\n# {slug}\nbody\n"
        )
        return p

    def test_merge_records_the_supersession_on_the_canonical(
            self, temp_entities, frozen_today):
        canon = self._write(temp_entities, "kept")
        self._write(temp_entities, "dupe")
        cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert fm["supersedes"] == ["[[dupe]]"]
        assert fm["revision_link"] == "research/entities/tool/dupe.md", \
            "the tombstone is the record that authorized the merge"
        assert str(fm["recorded_at"]) == TODAY

    def test_merge_revision_link_can_be_overridden(self, temp_entities, frozen_today):
        canon = self._write(temp_entities, "kept")
        self._write(temp_entities, "dupe")
        cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False,
                                     revision_link="ticket://BRO-1442"))
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert fm["revision_link"] == "ticket://BRO-1442"

    def test_merge_dry_run_leaves_the_canonical_untouched(
            self, temp_entities, frozen_today):
        canon = self._write(temp_entities, "kept")
        self._write(temp_entities, "dupe")
        before = canon.read_text()
        cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=True))
        assert canon.read_text() == before

    def test_merged_canonical_lints_clean(self, temp_entities, frozen_today):
        canon = self._write(temp_entities, "kept")
        self._write(temp_entities, "dupe")
        cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        hard = [e for e in lint_entity_page(canon) if e.severity == "error"]
        assert not hard, f"merged canonical must lint clean, got: {hard}"


# ── Warning-only supersession validation (opt-in) ────────────────────────────

class TestEnvelopeAudit:
    def test_a_well_formed_envelope_is_clean(self):
        assert _lint_envelope({
            "slug": "current",
            "recorded_at": "2026-08-01",
            "valid_from": "2026-07-01",
            "supersedes": ["[[old]]"],
            "revision_link": "ticket://BRO-1",
        }, lookup=lambda _s: {"recorded_at": "2026-06-01"}) == []

    def test_absent_envelope_produces_no_findings(self):
        assert _lint_envelope({"slug": "plain", "updated": "2026-08-01"}) == []

    def test_malformed_supersedes_entry_warns(self):
        errors = _lint_envelope({
            "slug": "current", "supersedes": ["old-slug"],
            "revision_link": "ticket://BRO-1",
        })
        assert _fields(errors) == ["temporal_supersedes"]
        assert "not [[wikilink]] format" in errors[0].message

    def test_non_list_supersedes_warns(self):
        errors = _lint_envelope({
            "slug": "current", "supersedes": "[[old]]",
            "revision_link": "ticket://BRO-1",
        })
        assert any("must be a list" in e.message for e in errors)

    def test_unresolvable_supersedes_target_warns(self):
        errors = _lint_envelope({
            "slug": "current", "supersedes": ["[[ghost]]"],
            "revision_link": "ticket://BRO-1",
        }, lookup=lambda _s: None)
        assert _fields(errors) == ["temporal_supersedes"]
        assert "unresolvable" in errors[0].message

    def test_self_supersession_warns(self):
        errors = _lint_envelope({
            "slug": "current", "supersedes": ["[[current]]"],
            "revision_link": "ticket://BRO-1",
        })
        assert any("cannot supersede itself" in e.message for e in errors)

    def test_supersedes_without_revision_link_warns(self):
        errors = _lint_envelope({"slug": "current", "supersedes": ["[[old]]"]})
        assert "temporal_revision_link" in _fields(errors)

    def test_blank_revision_link_does_not_satisfy_the_requirement(self):
        errors = _lint_envelope({
            "slug": "current", "supersedes": ["[[old]]"], "revision_link": "   ",
        })
        assert "temporal_revision_link" in _fields(errors)

    def test_revision_link_without_supersedes_warns(self):
        errors = _lint_envelope({"slug": "current", "revision_link": "ticket://BRO-1"})
        assert _fields(errors) == ["temporal_revision_link"]
        assert "revises nothing" in errors[0].message

    def test_timeline_inversion_warns(self):
        errors = _lint_envelope({
            "slug": "current", "recorded_at": "2026-06-01",
            "supersedes": ["[[old]]"], "revision_link": "ticket://BRO-1",
        }, lookup=lambda _s: {"recorded_at": "2026-07-01"})
        assert any("timeline inversion" in e.message for e in errors)

    def test_equal_recorded_at_is_not_an_inversion(self):
        assert _lint_envelope({
            "slug": "current", "recorded_at": "2026-06-01",
            "supersedes": ["[[old]]"], "revision_link": "ticket://BRO-1",
        }, lookup=lambda _s: {"recorded_at": "2026-06-01"}) == []

    def test_future_recorded_at_warns(self):
        errors = _lint_envelope({"slug": "x", "recorded_at": "2026-12-25"})
        assert _fields(errors) == ["temporal_recorded_at"]
        assert "future" in errors[0].message

    def test_unparseable_recorded_at_warns(self):
        errors = _lint_envelope({"slug": "x", "recorded_at": "2026-99-99"})
        assert _fields(errors) == ["temporal_recorded_at"]

    def test_unparseable_valid_from_warns(self):
        errors = _lint_envelope({"slug": "x", "valid_from": "sometime in 2026"})
        assert _fields(errors) == ["temporal_valid_from"]

    def test_future_valid_from_is_allowed(self):
        # A claim can be effective from a future date; that is a scheduled
        # change, not a defect.
        assert _lint_envelope({"slug": "x", "valid_from": "2027-01-01"}) == []

    def test_every_envelope_finding_is_warning_severity(self):
        errors = _lint_envelope({
            "slug": "current",
            "recorded_at": "2026-12-25",
            "valid_from": "not-a-date",
            "supersedes": ["bare", "[[current]]", 7],
        }, lookup=lambda _s: None)
        assert errors, "the fixture must actually produce findings"
        assert {e.severity for e in errors} == {"warning"}


class TestDefaultLintIsUnchanged:
    def test_default_lint_ignores_a_malformed_envelope(
            self, temp_entities, frozen_today):
        path = _write_entity(
            temp_entities, "malformed",
            extra='supersedes:\n  - bare-slug\nrevision_link: ""\n'
                  'recorded_at: "2027-12-25"\nvalid_from: nonsense\n',
        )
        errors = lint_entity_page(path)
        assert not [e for e in errors if e.field.startswith("temporal_")], \
            "envelope findings must require --temporal"
        assert not [e for e in errors if e.severity == "error"]

    def test_temporal_audit_surfaces_what_default_lint_skipped(
            self, temp_entities, frozen_today):
        path = _write_entity(
            temp_entities, "malformed",
            extra='supersedes:\n  - bare-slug\nrevision_link: ""\n',
        )
        errors = bookkeeping._lint_temporal_entity_page(path, audit_date=AUDIT_DATE)
        fields = _fields(errors)
        assert "temporal_supersedes" in fields
        assert "temporal_revision_link" in fields
        assert {e.severity for e in errors} == {"warning"}


# ── End-to-end CLI ───────────────────────────────────────────────────────────

class TestReviseCLI:
    def _graph(self, tmp_path):
        entities = tmp_path / "research" / "entities" / "concept"
        entities.mkdir(parents=True)
        for slug in ("old-belief", "new-belief"):
            (entities / f"{slug}.md").write_text(
                f"---\nslug: {slug}\ntype: concept\nstatus: entity\n"
                f'core_claim: "A claim about {slug}."\nsources:\n  - 2026-01-01-s\n'
                f"related: []\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
                f"tags:\n  - concept\n  - bookkeeping\n---\n\n# {slug}\n\nbody\n"
            )
        return entities

    def _run(self, args, tmp_path):
        env = {
            **os.environ,
            "KG_ROOT": str(tmp_path),
            "KG_ENTITIES_DIR": str(tmp_path / "research" / "entities"),
            "KG_NO_POLICY": "1",
        }
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
        )

    def test_revise_via_the_real_cli(self, tmp_path):
        entities = self._graph(tmp_path)
        result = self._run(
            ["revise", "--entity", "new-belief", "--supersedes", "old-belief",
             "--revision-link", "https://example.test/decision/1"],
            tmp_path,
        )
        assert result.returncode == 0, result.stderr
        text = (entities / "new-belief.md").read_text()
        assert 'supersedes: ["[[old-belief]]"]' in text
        assert 'revision_link: "https://example.test/decision/1"' in text

    def test_cli_requires_a_revision_link(self, tmp_path):
        self._graph(tmp_path)
        result = self._run(
            ["revise", "--entity", "new-belief", "--supersedes", "old-belief"],
            tmp_path,
        )
        assert result.returncode != 0
        assert "revision-link" in result.stderr

    def test_cli_lint_temporal_reports_the_supersession_as_a_warning(self, tmp_path):
        entities = self._graph(tmp_path)
        self._run(
            ["revise", "--entity", "new-belief", "--supersedes", "old-belief",
             "--revision-link", "ticket://BRO-1"],
            tmp_path,
        )
        result = self._run(
            ["lint", "--file", str(entities / "new-belief.md"), "--temporal"],
            tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert "ERROR" not in result.stdout
