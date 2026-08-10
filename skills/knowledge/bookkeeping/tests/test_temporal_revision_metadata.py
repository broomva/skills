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


_ABSENT = object()  # probe sentinel: "remove this key entirely"


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

    def test_an_unparseable_supplied_valid_from_is_reported_under_verbose(
            self, temp_entities, frozen_today, capsys):
        # Dropping it is correct; dropping it silently hides a broken upstream
        # emitter that thinks it is supplying claim-effective time.
        scored = _scored(metadata={"valid_from": "last Tuesday"})
        promote_item(scored, "noisy-effective-date", entity_type="concept",
                     verbose=True)
        out = capsys.readouterr().out
        assert "unparseable metadata.valid_from" in out and "last Tuesday" in out

    def test_a_valid_supplied_date_produces_no_such_warning(
            self, temp_entities, frozen_today, capsys):
        scored = _scored(metadata={"valid_from": "2026-03-01"})
        promote_item(scored, "quiet-effective-date", entity_type="concept",
                     verbose=True)
        assert "unparseable" not in capsys.readouterr().out

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

    def test_crlf_page_keeps_its_closing_fence(self):
        # On a CRLF page the fence line is `---\r`, which an anchored
        # `---[ \t]*$` never matches — the block regex would then treat it as a
        # list continuation and swallow it into the frontmatter.
        text = ("---\r\nslug: x\r\ntags:\r\n  - a\r\n  - b\r\n---\r\n\r\n# Body\r\n")
        out = _set_frontmatter_scalar(text, "tags", '["c"]')
        parsed, body = bookkeeping.parse_frontmatter(out)
        assert parsed["slug"] == "x" and parsed["tags"] == ["c"]
        assert "# Body" in body

    def test_blank_line_inside_a_block_list_does_not_orphan_items(self):
        text = ('---\nslug: x\nsupersedes:\n  - "[[a]]"\n\n  - "[[b]]"\n'
                'related: []\n---\nbody\n')
        out = _set_frontmatter_scalar(text, "supersedes", '["[[new]]"]')
        parsed, _ = bookkeeping.parse_frontmatter(out)
        assert parsed["supersedes"] == ["[[new]]"]
        assert parsed["related"] == []
        assert '"[[b]]"' not in out, "the second item must not survive as orphaned YAML"

    def test_duplicate_keys_collapse_to_one_authoritative_value(self):
        # PyYAML resolves duplicates to the LAST occurrence, so replacing only
        # the first would parse back as if the write never happened.
        text = ('---\nslug: x\nsupersedes: ["[[a]]"]\nrelated: []\n'
                'supersedes: ["[[b]]"]\n---\nbody\n')
        out = _set_frontmatter_scalar(text, "supersedes", '["[[new]]"]')
        fm, _ = _split_frontmatter(out)
        assert fm.count("supersedes:") == 1
        parsed, _ = bookkeeping.parse_frontmatter(out)
        assert parsed["supersedes"] == ["[[new]]"]

    def test_a_key_that_prefixes_another_key_is_not_matched(self):
        text = '---\nslug: x\nrecorded_at_note: keep me\n---\nbody\n'
        out = _set_frontmatter_scalar(text, "recorded_at", '"2026-08-10"')
        parsed, _ = bookkeeping.parse_frontmatter(out)
        assert parsed["recorded_at_note"] == "keep me"
        assert str(parsed["recorded_at"]) == "2026-08-10"


class TestYamlEscaping:
    def test_a_revision_link_cannot_inject_frontmatter(
            self, temp_entities, frozen_today):
        # Naive f-string quoting lets a link close its own scalar and open a new
        # document: `x"\n---\nforged: ...`.
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        hostile = 'x"\n---\nforged_key: injected\n'
        cmd_revise(_revise_args("new-belief", ["old-belief"], link=hostile))
        fm, body = bookkeeping.parse_frontmatter(path.read_text())
        assert fm, "the page must still parse"
        assert "forged_key" not in fm
        assert fm["revision_link"] == [hostile.strip()]
        assert "Body text." in body

    def test_a_revision_link_with_quotes_and_unicode_round_trips(
            self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        link = 'decisión: "final" \\ escape'
        cmd_revise(_revise_args("new-belief", ["old-belief"], link=link))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert fm["revision_link"] == [link]


class TestMalformedExistingEnvelopeIsRefused:
    @pytest.mark.parametrize("extra", [
        'supersedes:\n  - bare-slug\n',          # not wikilink form
        'supersedes:\n  - "[[broken"\n',         # truncated wikilink
        'supersedes: 7\n',                       # not a list
        'supersedes:\n  - 7\n',                  # non-string entry
        'supersedes: ["[[a]]"]\nrevision_link:\n  - 7\n',  # non-string link
    ])
    def test_revise_refuses_rather_than_repairing(
            self, temp_entities, frozen_today, extra, capsys):
        _write_entity(temp_entities, "old-belief")
        _write_entity(temp_entities, "a")
        path = _write_entity(temp_entities, "new-belief", extra=extra)
        before = path.read_text()
        with pytest.raises(SystemExit) as exc:
            cmd_revise(_revise_args("new-belief", ["old-belief"]))
        assert exc.value.code != 0
        assert path.read_text() == before, \
            "corrupt provenance must never be silently rewritten"
        assert "malformed revision envelope" in capsys.readouterr().err

    @pytest.mark.parametrize("key", ["supersedes", "revision_link", "recorded_at"])
    def test_revise_refuses_a_duplicated_envelope_key(
            self, temp_entities, frozen_today, key, capsys):
        # PyYAML keeps the LAST duplicate, so a read-then-write would silently
        # destroy whatever the earlier one held.
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(
            temp_entities, "new-belief",
            extra=f'{key}: "x"\nrelated: []\n{key}: "y"\n')
        before = path.read_text()
        with pytest.raises(SystemExit) as exc:
            cmd_revise(_revise_args("new-belief", ["old-belief"]))
        assert exc.value.code != 0
        assert "only the last" in capsys.readouterr().err
        assert path.read_text() == before

    def test_a_quoted_duplicate_key_is_still_a_duplicate(
            self, temp_entities, frozen_today, capsys):
        # A `^supersedes:` line match never sees `"supersedes":`, so the second
        # (authoritative) value would be silently shadowed.
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(
            temp_entities, "new-belief",
            extra='supersedes: ["[[old-belief]]"]\n"supersedes": ["[[other]]"]\n')
        before = path.read_text()
        with pytest.raises(SystemExit):
            cmd_revise(_revise_args("new-belief", ["old-belief"]))
        assert "only the last" in capsys.readouterr().err
        assert path.read_text() == before

    def test_an_envelope_key_inside_a_multiline_scalar_is_not_a_duplicate(
            self, temp_entities, frozen_today):
        # The mirror-image failure: refusing a legal page because a quoted
        # scalar happens to contain a line that looks like a key.
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(
            temp_entities, "new-belief",
            extra='note: "a paragraph\\nsupersedes: prose, not a key"\n')
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert fm["supersedes"] == ["[[old-belief]]"]
        assert "prose, not a key" in fm["note"]

    def test_revise_refuses_a_blank_existing_revision_link_entry(
            self, temp_entities, frozen_today, capsys):
        # Dropping the blank on rewrite would be the same silent repair the
        # strict supersedes parser refuses.
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(
            temp_entities, "new-belief",
            extra='supersedes: ["[[old-belief]]"]\nrevision_link: ["", "ticket://A"]\n')
        before = path.read_text()
        with pytest.raises(SystemExit):
            cmd_revise(_revise_args("new-belief", ["old-belief"]))
        assert "blank entry" in capsys.readouterr().err
        assert path.read_text() == before

    def test_an_envelope_without_a_stamp_is_not_already_recorded(
            self, temp_entities, frozen_today):
        # The unchanged early-return must not fire when the mechanical field is
        # still missing, or the first explicit revision never gets stamped.
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(
            temp_entities, "new-belief",
            extra='supersedes: ["[[old-belief]]"]\n'
                  'revision_link: ["https://example.test/decision/1"]\n')
        assert "recorded_at" not in path.read_text()
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert str(fm["recorded_at"]) == TODAY

    def test_revise_refuses_a_page_without_frontmatter(
            self, temp_entities, frozen_today, capsys):
        _write_entity(temp_entities, "old-belief")
        path = temp_entities / "concept" / "bodyonly.md"
        path.write_text("# Just a body\n")
        with pytest.raises(SystemExit) as exc:
            cmd_revise(_revise_args("bodyonly", ["old-belief"]))
        assert exc.value.code != 0
        assert "no YAML frontmatter" in capsys.readouterr().err
        assert path.read_text() == "# Just a body\n"


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
        assert fm["revision_link"] == ["https://example.test/decision/1"]
        assert str(fm["recorded_at"]) == TODAY
        assert str(fm["updated"]) == TODAY

    def test_revise_is_idempotent_on_replay(self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        first = path.read_text()
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        assert path.read_text() == first, "re-applying a revision must not churn"

    def test_revise_is_idempotent_ACROSS_DAYS(self, temp_entities, monkeypatch):
        # The dangerous case: same command, later date. Re-stamping `updated`
        # and `recorded_at` would report a substantive change that did not
        # happen, and rewrite the file on every replay forever.
        monkeypatch.setattr(bookkeeping, "today_str", lambda: "2026-08-10")
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        first = path.read_text()
        monkeypatch.setattr(bookkeeping, "today_str", lambda: "2026-11-30")
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        assert path.read_text() == first
        assert '"2026-11-30"' not in first

    def test_a_genuinely_new_revision_on_a_later_day_does_restamp(
            self, temp_entities, monkeypatch):
        # Control for the test above: the early return must not swallow real work.
        monkeypatch.setattr(bookkeeping, "today_str", lambda: "2026-08-10")
        _write_entity(temp_entities, "old-a")
        _write_entity(temp_entities, "old-b")
        path = _write_entity(temp_entities, "current")
        cmd_revise(_revise_args("current", ["old-a"], link="ticket://BRO-1"))
        monkeypatch.setattr(bookkeeping, "today_str", lambda: "2026-11-30")
        cmd_revise(_revise_args("current", ["old-b"], link="ticket://BRO-2"))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert str(fm["recorded_at"]) == "2026-11-30"
        assert fm["supersedes"] == ["[[old-a]]", "[[old-b]]"]

    def test_a_new_valid_from_alone_is_a_substantive_change(
            self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        cmd_revise(_revise_args("new-belief", ["old-belief"]))
        cmd_revise(_revise_args("new-belief", ["old-belief"], valid_from="2026-04-15"))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert str(fm["valid_from"]) == "2026-04-15"

    def test_a_second_revision_unions_rather_than_replaces(
            self, temp_entities, frozen_today):
        _write_entity(temp_entities, "old-a")
        _write_entity(temp_entities, "old-b")
        path = _write_entity(temp_entities, "current")
        cmd_revise(_revise_args("current", ["old-a"], link="ticket://BRO-1"))
        cmd_revise(_revise_args("current", ["old-b"], link="ticket://BRO-2"))
        fm, _ = bookkeeping.parse_frontmatter(path.read_text())
        assert fm["supersedes"] == ["[[old-a]]", "[[old-b]]"], \
            "a later revision must not drop what an earlier one recorded"
        assert fm["revision_link"] == ["ticket://BRO-1", "ticket://BRO-2"], \
            "a later revision must not reattribute what an earlier one authorized"

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

    def test_revise_output_passes_the_repo_s_own_default_lint(
            self, temp_entities, frozen_today):
        # Caught by dogfooding the MERGED artifact, not by the suite: writing
        # `updated` bare un-quoted a page that already had it quoted, so every
        # revised page picked up an unquoted-date warning — the writer failing
        # the gate it is supposed to satisfy.
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        path.write_text(path.read_text().replace(
            "created: 2026-01-01\nupdated: 2026-01-01\n",
            'created: "2026-01-01"\nupdated: "2026-01-01"\n'))
        cmd_revise(_revise_args("new-belief", ["old-belief"], valid_from="2026-04-15"))
        text = path.read_text()
        assert f'updated: "{TODAY}"' in text
        dates = [e for e in lint_entity_page(path) if "unquoted date" in e.message]
        assert not dates, f"revise must not emit unquoted dates, got: {dates}"

    def test_valid_from_lands_next_to_recorded_at(self, temp_entities, frozen_today):
        # `after="recorded_at"` only resolves if recorded_at is already present;
        # set earlier, the field silently fell to the end of the frontmatter.
        _write_entity(temp_entities, "old-belief")
        path = _write_entity(temp_entities, "new-belief")
        cmd_revise(_revise_args("new-belief", ["old-belief"], valid_from="2026-04-15"))
        fm, _ = _split_frontmatter(path.read_text())
        keys = [ln.split(":")[0] for ln in fm.splitlines() if ln[:1].isalpha()]
        assert keys.index("valid_from") == keys.index("recorded_at") + 1

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
        assert fm["revision_link"] == ["research/entities/tool/dupe.md"], \
            "the tombstone is the record that authorized the merge"
        assert str(fm["recorded_at"]) == TODAY

    def test_merge_revision_link_can_be_overridden(self, temp_entities, frozen_today):
        canon = self._write(temp_entities, "kept")
        self._write(temp_entities, "dupe")
        cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False,
                                     revision_link="ticket://BRO-1442"))
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert fm["revision_link"] == ["ticket://BRO-1442"]

    def test_merge_dry_run_leaves_the_canonical_untouched(
            self, temp_entities, frozen_today):
        canon = self._write(temp_entities, "kept")
        self._write(temp_entities, "dupe")
        before = canon.read_text()
        cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=True))
        assert canon.read_text() == before

    def test_merged_canonical_lints_clean_including_the_temporal_audit(
            self, temp_entities, frozen_today):
        canon = self._write(temp_entities, "kept")
        self._write(temp_entities, "dupe")
        cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        hard = [e for e in lint_entity_page(canon) if e.severity == "error"]
        assert not hard, f"merged canonical must lint clean, got: {hard}"
        # Default lint cannot see the envelope at all, so checking only errors
        # would pass on a corrupt one. The audit is what actually inspects it.
        envelope = [e for e in
                    bookkeeping._lint_temporal_entity_page(canon, audit_date=AUDIT_DATE)
                    if e.field in ("temporal_supersedes", "temporal_revision_link",
                                   "temporal_recorded_at", "temporal_valid_from")]
        assert not envelope, f"merge must emit a well-formed envelope, got: {envelope}"

    def test_merge_aborts_on_a_malformed_pre_existing_envelope(
            self, temp_entities, frozen_today, capsys):
        # Tombstoning the dup while skipping the supersession would leave a
        # merged record whose provenance says nothing — a broken intermediate
        # state. The merge is not urgent; the corrupt page is.
        canon = self._write(temp_entities, "kept")
        canon.write_text(canon.read_text().replace(
            "---\n# kept", 'supersedes:\n  - bare-slug\n---\n# kept'))
        canon_before = canon.read_text()
        dup = self._write(temp_entities, "dupe")
        dup_before = dup.read_text()
        with pytest.raises(SystemExit) as exc:
            cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        assert exc.value.code != 0
        assert "malformed revision envelope" in capsys.readouterr().err
        assert canon.read_text() == canon_before
        assert dup.read_text() == dup_before, "the dup must not be tombstoned"

    def test_an_aborted_merge_leaves_referrers_untouched(
            self, temp_entities, frozen_today):
        # The abort path must not corrupt: repointing referrers first and
        # validating afterwards left third pages pointing at a canonical that
        # never got merged.
        canon = self._write(temp_entities, "kept")
        canon.write_text(canon.read_text().replace(
            "---\n# kept", 'supersedes:\n  - bare-slug\n---\n# kept'))
        self._write(temp_entities, "dupe")
        referrer = temp_entities / "concept" / "linker.md"
        referrer.write_text(
            '---\nslug: linker\ntype: concept\nstatus: entity\n'
            'core_claim: "A claim about linking."\nsources:\n  - s\n---\n'
            "# linker\nSee [[dupe]] for details.\n")
        before = referrer.read_text()
        with pytest.raises(SystemExit):
            cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        assert referrer.read_text() == before, \
            "an abort must not leave referrers repointed at an unmerged canonical"
        assert "[[dupe]]" in referrer.read_text()

    def test_merge_aborts_when_the_canonical_has_no_frontmatter(
            self, temp_entities, frozen_today, capsys):
        canon = temp_entities / "tool" / "kept.md"
        canon.write_text("# kept\nbody only\n")
        dup = self._write(temp_entities, "dupe")
        dup_before = dup.read_text()
        with pytest.raises(SystemExit) as exc:
            cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        assert exc.value.code != 0
        assert "no YAML frontmatter" in capsys.readouterr().err
        assert dup.read_text() == dup_before

    def test_merge_falls_back_to_the_tombstone_on_a_blank_link_override(
            self, temp_entities, frozen_today):
        canon = self._write(temp_entities, "kept")
        self._write(temp_entities, "dupe")
        cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False,
                                     revision_link="   "))
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert fm["revision_link"] == ["research/entities/tool/dupe.md"], \
            "a blank override must not become an unauthorized envelope"


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

    def test_a_list_valued_revision_link_satisfies_the_requirement(self):
        assert _lint_envelope({
            "slug": "current", "supersedes": ["[[old]]"],
            "revision_link": ["ticket://BRO-1", "ticket://BRO-2"],
        }) == []

    def test_an_all_blank_revision_link_list_does_not(self):
        errors = _lint_envelope({
            "slug": "current", "supersedes": ["[[old]]"], "revision_link": ["", "  "],
        })
        assert "temporal_revision_link" in _fields(errors)

    def test_two_cleared_optional_lists_are_not_an_orphaned_link(self):
        # `supersedes: []` with `revision_link: []` is a pair of cleared fields,
        # not a link pointing at nothing — there is no link.
        assert _lint_envelope({
            "slug": "current", "supersedes": [], "revision_link": [],
        }) == []

    @pytest.mark.parametrize("links,expected", [
        ([7, "ticket://BRO-1"], "is not a string"),
        (["", "ticket://BRO-1"], "blank entry"),
        ([None, "ticket://BRO-1"], "is not a string"),
    ])
    def test_a_partially_malformed_link_list_still_warns(self, links, expected):
        # One usable entry must not launder the rest: the writer refuses such a
        # page, so the audit that precedes the writer has to see it.
        errors = _lint_envelope({
            "slug": "current", "supersedes": ["[[old]]"], "revision_link": links,
        })
        assert any(expected in e.message for e in errors)
        assert {e.severity for e in errors} == {"warning"}

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


class TestBackfillRecordedMerges:
    """`backfill-revisions` replays merges the graph already recorded (gh-160)."""

    def _merged_pair(self, entities, canon="kept", dup="dupe", merged_at="2026-06-09",
                     type_dir="tool"):
        c = _write_entity(entities, canon, type_dir=type_dir)
        (entities / type_dir / f"{dup}.md").write_text(
            f"---\nslug: {dup}\ntype: {type_dir}\nstatus: merged\n"
            f'merged_into: {canon}\nmerged_at: "{merged_at}"\n'
            f'core_claim: "Merged into [[{canon}]]."\n---\n\n# {dup}\n\nTombstone.\n')
        return c

    def _args(self, apply=True, dry_run=False):
        return argparse.Namespace(apply=apply, dry_run=dry_run)

    def test_backfill_records_the_historical_merge_date_not_today(
            self, temp_entities, frozen_today):
        # `recorded_at` is when the graph recorded the supersession. Stamping the
        # migration date would assert the graph learned a June merge in August —
        # exactly the temporal flattening the envelope exists to prevent.
        canon = self._merged_pair(temp_entities, merged_at="2026-06-09")
        bookkeeping.cmd_backfill_revisions(self._args())
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert str(fm["recorded_at"]) == "2026-06-09"
        assert str(fm["updated"]) == TODAY, "the file IS being edited today"
        assert fm["supersedes"] == ["[[dupe]]"]
        assert fm["revision_link"] == ["research/entities/tool/dupe.md"]

    def test_backfill_dry_run_writes_nothing(self, temp_entities, frozen_today):
        canon = self._merged_pair(temp_entities)
        before = canon.read_text()
        bookkeeping.cmd_backfill_revisions(self._args(apply=False))
        assert canon.read_text() == before

    def test_backfill_is_idempotent(self, temp_entities, frozen_today):
        canon = self._merged_pair(temp_entities)
        bookkeeping.cmd_backfill_revisions(self._args())
        first = canon.read_text()
        bookkeeping.cmd_backfill_revisions(self._args())
        assert canon.read_text() == first

    def test_one_canonical_accumulates_several_recorded_merges(
            self, temp_entities, frozen_today):
        canon = self._merged_pair(temp_entities, dup="dupe-a", merged_at="2026-06-09")
        self._merged_pair(temp_entities, dup="dupe-b", merged_at="2026-07-04")
        bookkeeping.cmd_backfill_revisions(self._args())
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert fm["supersedes"] == ["[[dupe-a]]", "[[dupe-b]]"]
        assert len(fm["revision_link"]) == 2, "each merge keeps its own record"

    def test_a_tombstone_with_no_date_is_reported_not_guessed(
            self, temp_entities, frozen_today, capsys):
        canon = self._write_undated(temp_entities)
        bookkeeping.cmd_backfill_revisions(self._args())
        out = capsys.readouterr().out
        assert "no parseable merged_at" in out
        assert "supersedes" not in canon.read_text(), \
            "no date means no honest recorded_at — skip, never invent one"

    def _write_undated(self, entities):
        canon = _write_entity(entities, "kept", type_dir="tool")
        (entities / "tool" / "dupe.md").write_text(
            '---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: kept\n'
            'core_claim: "Merged into [[kept]]."\n---\n\n# dupe\n\nTombstone.\n')
        return canon

    def test_a_tombstone_whose_canonical_vanished_is_reported(
            self, temp_entities, frozen_today, capsys):
        (temp_entities / "tool" / "dupe.md").write_text(
            '---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: gone\n'
            'merged_at: "2026-06-09"\ncore_claim: "Merged into [[gone]]."\n---\n\nT.\n')
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "has no entity file" in capsys.readouterr().out

    def test_backfill_never_redates_a_record_backwards(
            self, temp_entities, frozen_today):
        # `recorded_at` is a property of the WHOLE record, and a record can
        # aggregate supersessions recorded at different times. Replaying a June
        # merge onto a canonical that also carries an August revision must not
        # redate the August one — the honest aggregate is the LATEST moment at
        # which any part of the record was recorded.
        canon = self._merged_pair(temp_entities, merged_at="2026-06-09")
        canon.write_text(canon.read_text().replace(
            "related: []\n",
            'related: []\nsupersedes: ["[[other-old]]"]\n'
            'revision_link: ["ticket://AUG"]\n'
            'recorded_at: "2026-08-01"\n'))
        bookkeeping.cmd_backfill_revisions(self._args())
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert str(fm["recorded_at"]) == "2026-08-01", \
            "a newer stamp is correct and must survive the migration"
        assert fm["supersedes"] == ["[[other-old]]", "[[dupe]]"]

    def test_backfill_raises_a_stamp_that_predates_the_recorded_merge(
            self, temp_entities, frozen_today):
        # The other direction: an existing stamp OLDER than the merge is
        # corrected forward, so the migration still fixes an understated record.
        canon = self._merged_pair(temp_entities, merged_at="2026-06-09")
        canon.write_text(canon.read_text().replace(
            "related: []\n", 'related: []\nrecorded_at: "2026-01-01"\n'))
        bookkeeping.cmd_backfill_revisions(self._args())
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert str(fm["recorded_at"]) == "2026-06-09"

    def test_multi_tombstone_stamp_does_not_depend_on_visit_order(
            self, temp_entities, frozen_today):
        # Applied per tombstone, the surviving stamp would be whichever
        # tombstone the walk happened to reach last.
        canon = self._merged_pair(temp_entities, dup="aaa-dupe", merged_at="2026-07-04")
        self._merged_pair(temp_entities, dup="zzz-dupe", merged_at="2026-06-09")
        bookkeeping.cmd_backfill_revisions(self._args())
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert str(fm["recorded_at"]) == "2026-07-04", "the latest merge wins"

    @pytest.mark.parametrize("merged_into,reason", [
        ("*", "not a safe slug reference"),
        ("../../etc/passwd", "not a safe slug reference"),
        ("kept[1]", "not a safe slug reference"),
        (".hidden", "not a safe slug reference"),
    ])
    def test_backfill_refuses_a_pattern_as_a_canonical(
            self, temp_entities, frozen_today, merged_into, reason, capsys):
        # `_find_entity_file` globs, which turns the slug into a PATTERN: a
        # tombstone naming `*` would resolve to an arbitrary entity and have the
        # envelope written into it.
        victim = _write_entity(temp_entities, "innocent", type_dir="tool")
        before = victim.read_text()
        (temp_entities / "tool" / "dupe.md").write_text(
            f'---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: "{merged_into}"\n'
            f'merged_at: "2026-06-09"\ncore_claim: "Merged."\n---\n\nT.\n')
        bookkeeping.cmd_backfill_revisions(self._args())
        assert reason in capsys.readouterr().out
        assert victim.read_text() == before

    @pytest.mark.parametrize("slug", ["colfondos-s-a", "tp", "a-proof-publishes-its-frame"])
    def test_an_unfashionably_named_but_real_canonical_still_resolves(
            self, temp_entities, frozen_today, slug):
        # 42 of the live graph's 943 slugs fail `is_entity_shaped_slug`, which
        # decides whether to MINT a new slug — a different question from whether
        # a reference to an existing entity is safe to resolve. Using it here
        # would refuse 4.5% of legitimate merges.
        canon = _write_entity(temp_entities, slug, type_dir="tool")
        (temp_entities / "tool" / "dupe.md").write_text(
            f'---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: {slug}\n'
            f'merged_at: "2026-06-09"\ncore_claim: "Merged."\n---\n\nT.\n')
        bookkeeping.cmd_backfill_revisions(self._args())
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert fm["supersedes"] == ["[[dupe]]"]

    def test_backfill_refuses_a_tombstone_naming_itself_as_its_own_canonical(
            self, temp_entities, frozen_today, capsys):
        # The tombstone's own `slug` is written INTO the canonical, so it is
        # untrusted input too: `tool/old.md` declaring `slug: kept` alongside
        # `merged_into: kept` would give kept.md `supersedes: ["[[kept]]"]`.
        canon = _write_entity(temp_entities, "kept", type_dir="tool")
        before = canon.read_text()
        (temp_entities / "tool" / "old.md").write_text(
            '---\nslug: kept\ntype: tool\nstatus: merged\nmerged_into: kept\n'
            'merged_at: "2026-06-09"\ncore_claim: "Merged."\n---\n\nT.\n')
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "both the dup and the canonical" in capsys.readouterr().out
        assert canon.read_text() == before

    def test_backfill_refuses_an_unsafe_superseded_slug(
            self, temp_entities, frozen_today, capsys):
        canon = _write_entity(temp_entities, "kept", type_dir="tool")
        before = canon.read_text()
        (temp_entities / "tool" / "old.md").write_text(
            '---\nslug: "../../etc/passwd"\ntype: tool\nstatus: merged\n'
            'merged_into: kept\nmerged_at: "2026-06-09"\ncore_claim: "M."\n---\n\nT.\n')
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "not a safe slug reference" in capsys.readouterr().out
        assert canon.read_text() == before

    def test_backfill_refuses_a_canonical_with_an_unterminated_fence(
            self, temp_entities, frozen_today, capsys):
        # A leading `---` with no closing fence is not "no frontmatter": every
        # setter no-ops and the run would report the page as already recorded.
        canon = self._merged_pair(temp_entities)
        canon.write_text('---\nslug: kept\nsupersedes: ["[[old]]"]\n\nBody only.\n')
        before = canon.read_text()
        with pytest.raises(SystemExit):
            bookkeeping.cmd_backfill_revisions(self._args())
        assert "never closed" in capsys.readouterr().err
        assert canon.read_text() == before

    def test_a_quoted_status_marker_is_still_seen_on_a_broken_tombstone(
            self, temp_entities, frozen_today, capsys):
        _write_entity(temp_entities, "kept", type_dir="tool")
        (temp_entities / "tool" / "dupe.md").write_text(
            '---\nslug: dupe\nstatus: "merged"\nmerged_into: [unclosed\n---\n\nT.\n')
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "does not parse" in capsys.readouterr().out

    def test_a_quoted_status_KEY_is_still_a_key(
            self, temp_entities, frozen_today, capsys):
        _write_entity(temp_entities, "kept", type_dir="tool")
        (temp_entities / "tool" / "dupe.md").write_text(
            '---\nslug: dupe\n"status": merged\nmerged_into: [unclosed\n---\n\nT.\n')
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "does not parse" in capsys.readouterr().out

    def test_a_body_only_canonical_is_refused_not_reported_recorded(
            self, temp_entities, frozen_today, capsys):
        # A page with no frontmatter is not an entity page: every setter no-ops,
        # so the run would report it as "already recorded" having written nothing.
        canon = temp_entities / "tool" / "kept.md"
        canon.write_text("# kept\n\nBody only.\n")
        (temp_entities / "tool" / "dupe.md").write_text(
            '---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: kept\n'
            'merged_at: "2026-06-09"\ncore_claim: "Merged."\n---\n\nT.\n')
        with pytest.raises(SystemExit):
            bookkeeping.cmd_backfill_revisions(self._args())
        out = capsys.readouterr()
        assert "no YAML frontmatter" in out.err
        assert "[ok]" not in out.out, "no row may be reported as already recorded"
        assert "1 failed" in out.out
        assert canon.read_text() == "# kept\n\nBody only.\n"

    def test_one_disk_write_per_canonical_regardless_of_link_count(
            self, temp_entities, frozen_today, monkeypatch):
        # Pins the ONE-CALL contract: restoring a per-link loop would still
        # produce the right frontmatter, so asserting only the result cannot
        # detect the regression.
        canon = self._merged_pair(temp_entities, dup="dupe-a", merged_at="2026-06-09")
        self._merged_pair(temp_entities, dup="dupe-b", merged_at="2026-07-04")
        self._merged_pair(temp_entities, dup="dupe-c", merged_at="2026-07-05")
        calls = []
        real = bookkeeping._apply_revision_envelope
        monkeypatch.setattr(
            bookkeeping, "_apply_revision_envelope",
            lambda *a, **k: (calls.append(k.get("revision_link")), real(*a, **k))[1])
        bookkeeping.cmd_backfill_revisions(self._args())
        assert len(calls) == 1, f"expected one call for one canonical, got {len(calls)}"
        assert calls[0] == [
            "research/entities/tool/dupe-a.md",
            "research/entities/tool/dupe-b.md",
            "research/entities/tool/dupe-c.md",
        ]
        fm, _ = bookkeeping.parse_frontmatter(canon.read_text())
        assert len(fm["revision_link"]) == 3

    def test_a_code_fence_in_the_body_is_not_a_tombstone(
            self, temp_entities, frozen_today, capsys):
        # The marker scan is confined to the frontmatter block; a full-file
        # search would read documentation examples as records.
        _write_entity(temp_entities, "kept", type_dir="tool",
                      body="Example:\n\n```yaml\nstatus: merged\n```\n")
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "does not parse" not in capsys.readouterr().out

    def test_apply_and_dry_run_together_are_refused(
            self, temp_entities, frozen_today, capsys):
        canon = self._merged_pair(temp_entities)
        before = canon.read_text()
        with pytest.raises(SystemExit) as exc:
            bookkeeping.cmd_backfill_revisions(
                argparse.Namespace(apply=True, dry_run=True))
        assert exc.value.code != 0
        assert "contradict" in capsys.readouterr().err
        assert canon.read_text() == before

    def test_backfill_refuses_a_canonical_that_is_itself_a_tombstone(
            self, temp_entities, frozen_today, capsys):
        # An A -> B -> C chain must not write A's provenance onto merged-away B.
        _write_entity(temp_entities, "cee", type_dir="tool")
        (temp_entities / "tool" / "bee.md").write_text(
            '---\nslug: bee\ntype: tool\nstatus: merged\nmerged_into: cee\n'
            'merged_at: "2026-06-09"\ncore_claim: "Merged into [[cee]]."\n---\n\nT.\n')
        (temp_entities / "tool" / "ay.md").write_text(
            '---\nslug: ay\ntype: tool\nstatus: merged\nmerged_into: bee\n'
            'merged_at: "2026-06-09"\ncore_claim: "Merged into [[bee]]."\n---\n\nT.\n')
        before = (temp_entities / "tool" / "bee.md").read_text()
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "is itself a merged tombstone" in capsys.readouterr().out
        assert (temp_entities / "tool" / "bee.md").read_text() == before

    def test_backfill_refuses_an_ambiguous_cross_type_canonical(
            self, temp_entities, frozen_today, capsys):
        _write_entity(temp_entities, "twin", type_dir="tool")
        _write_entity(temp_entities, "twin", type_dir="concept")
        (temp_entities / "tool" / "dupe.md").write_text(
            '---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: twin\n'
            'merged_at: "2026-06-09"\ncore_claim: "Merged."\n---\n\nT.\n')
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "ambiguous across type dirs" in capsys.readouterr().out

    def test_backfill_refuses_a_future_merge_date(
            self, temp_entities, frozen_today, capsys):
        canon = self._merged_pair(temp_entities, merged_at="2099-01-01")
        before = canon.read_text()
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "is in the future" in capsys.readouterr().out
        assert canon.read_text() == before, \
            "a future stamp would be flagged by this command's own audit"

    def test_an_unparseable_tombstone_is_reported_not_invisible(
            self, temp_entities, frozen_today, capsys):
        _write_entity(temp_entities, "kept", type_dir="tool")
        (temp_entities / "tool" / "dupe.md").write_text(
            '---\nslug: dupe\nstatus: merged\nmerged_into: [unclosed\n---\n\nT.\n')
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "does not parse" in capsys.readouterr().out

    def test_backfill_refuses_a_canonical_with_unparseable_frontmatter(
            self, temp_entities, frozen_today, capsys):
        # parse_frontmatter returns {} on a YAML error, which reads as "no
        # supersessions" — so the rewrite would replace the broken line and lose
        # whatever it held.
        canon = self._merged_pair(temp_entities)
        canon.write_text(canon.read_text().replace(
            "related: []\n", 'supersedes: ["[[old]]"\n'))
        before = canon.read_text()
        with pytest.raises(SystemExit) as exc:
            bookkeeping.cmd_backfill_revisions(self._args())
        assert exc.value.code != 0, "a refused record must not exit clean"
        err = capsys.readouterr().err
        assert "does not parse as YAML" in err
        assert canon.read_text() == before
        assert "[[old]]" in canon.read_text()

    def test_aliases_are_not_treated_as_supersessions(
            self, temp_entities, frozen_today):
        # 88 of the live graph's aliases are `aka` search synonyms, not merges.
        # Deriving supersessions from them would be the prose inference the whole
        # envelope refuses.
        canon = _write_entity(temp_entities, "kept", type_dir="tool",
                              extra="aliases:\n  - some-old-name\n")
        bookkeeping.cmd_backfill_revisions(self._args())
        assert "supersedes" not in canon.read_text()


class TestSafeSlugReference:
    """The charset that guards a slug used as a filesystem REFERENCE."""

    @pytest.mark.parametrize("slug", [
        "*", "?", "**", "[a-z]", "kept[1]",          # glob metacharacters
        "../../etc/passwd", "a/b", "a\\b",            # path traversal
        ".hidden", "-lead", "", " kept", "kept ",     # shape
        "kept\n", "kept\nother",                      # trailing/embedded newline
    ])
    def test_unsafe_references_are_refused(self, slug):
        assert not bookkeeping._SAFE_SLUG_REFERENCE_RE.match(slug), slug

    @pytest.mark.parametrize("slug", [
        # Real slugs from the live graph that the MINTING heuristic rejects.
        # Using that heuristic here refused 42 of 943 real entities.
        "colfondos-s-a", "tp", "a-proof-publishes-its-frame",
        "write-reachability-underdetermines-grounding", "the-three",
        "kronos", "lago-event-journal", "cryptographic-problem",
    ])
    def test_real_slugs_are_accepted(self, slug):
        assert bookkeeping._SAFE_SLUG_REFERENCE_RE.match(slug), slug


class TestEnvelopeChecksCanFire:
    """Positive controls: a checker that never fires scores like a correct one.

    The gh-160 calibration found ZERO findings across the real migrated corpus.
    That number only means something if each check is known to be able to fire —
    otherwise silence is indistinguishable from a gutted audit. One probe per
    defect class, each asserting the SPECIFIC field, so a check cannot be
    covered by some other check's finding.
    """

    BASE = {
        "slug": "current", "recorded_at": "2026-06-09",
        "supersedes": ["[[old]]"], "revision_link": ["research/entities/tool/old.md"],
    }

    def _probe(self, lookup=None, **overrides):
        fm = dict(self.BASE)
        for k, v in overrides.items():
            if v is _ABSENT:
                fm.pop(k, None)
            else:
                fm[k] = v
        return _lint_envelope(fm, lookup=lookup or (lambda _s: {}))

    def test_negative_control_a_well_formed_envelope_is_silent(self):
        assert self._probe() == [], "the corpus baseline must be genuinely clean"

    # Each probe names the SPECIFIC message its branch emits, not just the
    # field. Asserting the field alone is vacuous: `revision_link: [7]` also
    # trips the missing-link branch, so deleting the non-string check entirely
    # would still produce a `temporal_revision_link` finding and pass.
    @pytest.mark.parametrize("name,overrides,field,message", [
        ("supersedes_not_wikilink", {"supersedes": ["bare-slug"]},
         "temporal_supersedes", "not [[wikilink]] format"),
        ("supersedes_not_a_list", {"supersedes": "[[old]]"},
         "temporal_supersedes", "must be a list"),
        ("supersedes_non_string", {"supersedes": [7]},
         "temporal_supersedes", "is not a string"),
        ("supersedes_self", {"supersedes": ["[[current]]"]},
         "temporal_supersedes", "cannot supersede itself"),
        ("revision_link_missing", {"revision_link": _ABSENT},
         "temporal_revision_link", "no authorizing record"),
        ("revision_link_blank", {"revision_link": ["", "x"]},
         "temporal_revision_link", "blank entry"),
        ("revision_link_non_string", {"revision_link": [7]},
         "temporal_revision_link", "is not a string"),
        ("revision_link_orphan", {"supersedes": _ABSENT},
         "temporal_revision_link", "revises nothing"),
        ("recorded_at_unparseable", {"recorded_at": "2026-99-99"},
         "temporal_recorded_at", "not an ISO date"),
        ("recorded_at_future", {"recorded_at": "2099-01-01"},
         "temporal_recorded_at", "in the future"),
        ("valid_from_unparseable", {"valid_from": "someday"},
         "temporal_valid_from", "not an ISO date"),
    ])
    def test_each_defect_class_is_detected(self, name, overrides, field, message):
        hits = [e for e in self._probe(**overrides)
                if e.field == field and message in e.message]
        assert hits, f"{name}: no finding matched {field} / {message!r}"

    def test_supersedes_unresolvable_target_is_detected(self):
        hits = [e for e in self._probe(lookup=lambda _s: None)
                if e.field == "temporal_supersedes" and "unresolvable" in e.message]
        assert hits

    def test_timeline_inversion_is_detected(self):
        # The only HEURISTIC check, and the only one the real corpus cannot
        # exercise: it reads the superseded target's `recorded_at`, and merge
        # tombstones do not carry one.
        hits = [e for e in self._probe(lookup=lambda _s: {"recorded_at": "2099-01-01"})
                if e.field == "temporal_supersedes" and "timeline inversion" in e.message]
        assert hits


class TestDefaultLintIsUnchanged:
    def test_default_lint_output_is_identical_with_and_without_an_envelope(
            self, temp_entities, frozen_today):
        # The strong form: the FULL default-lint finding set for a page carrying
        # a (deliberately malformed) envelope must equal the set for the same
        # page without one. Asserting only "no temporal_* fields" would pass
        # even if the envelope introduced some other new default warning.
        envelope = ('supersedes:\n  - bare-slug\nrevision_link: ""\n'
                    'recorded_at: "2027-12-25"\nvalid_from: nonsense\n')
        with_env = _write_entity(temp_entities, "with-envelope", extra=envelope)
        without = _write_entity(temp_entities, "without-envelope")

        def signature(p):
            return sorted((e.field, e.severity, e.message) for e in lint_entity_page(p))

        assert signature(with_env) == signature(without), \
            "the envelope must be invisible to default lint"
        assert not [e for e in lint_entity_page(with_env) if e.severity == "error"]

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
        assert 'revision_link: ["https://example.test/decision/1"]' in text

    def test_cli_requires_a_revision_link(self, tmp_path):
        self._graph(tmp_path)
        result = self._run(
            ["revise", "--entity", "new-belief", "--supersedes", "old-belief"],
            tmp_path,
        )
        assert result.returncode != 0
        assert "revision-link" in result.stderr

    def test_cli_temporal_flag_actually_runs_envelope_validation(self, tmp_path):
        # Asserting rc==0 and "no ERROR" would pass even if --temporal were
        # ignored entirely. Feed a page whose envelope is deliberately broken
        # and require the specific warning to appear, and require the DEFAULT
        # run on the same file to stay silent about it.
        entities = self._graph(tmp_path)
        bad = entities / "new-belief.md"
        bad.write_text(bad.read_text().replace(
            "related: []\n", 'related: []\nsupersedes: ["[[ghost]]"]\n'))

        default = self._run(["lint", "--file", str(bad)], tmp_path)
        assert default.returncode == 0, default.stderr
        assert "temporal_" not in default.stdout

        temporal = self._run(["lint", "--file", str(bad), "--temporal"], tmp_path)
        assert temporal.returncode == 0, temporal.stderr
        assert "temporal_supersedes" in temporal.stdout
        assert "temporal_revision_link" in temporal.stdout
        assert "WARN" in temporal.stdout and "ERROR" not in temporal.stdout

    def test_cli_replaying_a_revision_reports_and_writes_nothing(self, tmp_path):
        entities = self._graph(tmp_path)
        args = ["revise", "--entity", "new-belief", "--supersedes", "old-belief",
                "--revision-link", "ticket://BRO-1"]
        assert self._run(args, tmp_path).returncode == 0
        first = (entities / "new-belief.md").read_text()
        second = self._run(args, tmp_path)
        assert second.returncode == 0, second.stderr
        assert "already recorded" in second.stdout
        assert (entities / "new-belief.md").read_text() == first

    def test_cli_rejects_a_blank_revision_link(self, tmp_path):
        entities = self._graph(tmp_path)
        before = (entities / "new-belief.md").read_text()
        result = self._run(
            ["revise", "--entity", "new-belief", "--supersedes", "old-belief",
             "--revision-link", "   "],
            tmp_path,
        )
        assert result.returncode != 0
        assert "must not be blank" in result.stderr
        assert (entities / "new-belief.md").read_text() == before
