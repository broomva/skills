"""
Tests for the two bookkeeping engine fixes:

  Fix 1 — Promote/update content-identity guard: an update with no semantic
          delta must NOT rewrite the file or bump `updated:` (the date-bump
          churn pathology — 137 entities rewritten per run with no change).

  Fix 2 — `lint --fix` mechanical auto-repair of `related:` format violations
          (bare slug / path-form → [[wikilink]]), idempotent, scoped to the
          unambiguous classes only.
"""
import argparse

import pytest

import bookkeeping
from bookkeeping import (
    RawItem,
    ScoredItem,
    _canonicalize_related_value,
    _render_updated_entity,
    _split_frontmatter,
    _strip_volatile_fields,
    cmd_lint,
    fix_entity_page,
    promote_item,
)


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def temp_entities(tmp_path, monkeypatch):
    """research/entities/ under tmp_path, with the module globals patched."""
    root = tmp_path
    entities = root / "research" / "entities"
    for et in bookkeeping.ENTITY_TYPES:
        (entities / et).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", root)
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
    return entities


def _scored(content="A novel claim about arcan and lago memory.", quote="quoted"):
    item = RawItem(
        item_id="abcd1234",
        source_id="2026-05-28-test-raw",
        source_type="research",
        content=content,
        quote=quote,
        author="",
        timestamp="2026-05-28T00:00:00+00:00",
        metadata={},
    )
    return ScoredItem(
        item=item,
        novelty=2,
        specificity=2,
        relevance=2,
        total=6,
        promote=True,
        candidate_entities=["test-entity"],
        scoring_method="heuristic",
        reasoning={},
    )


# ── Fix 1: promote/update idempotency guard ────────────────────────────────────

class TestStripVolatileFields:
    def test_removes_updated_line(self):
        text = "---\nslug: x\nupdated: 2026-05-28\ncreated: 2026-01-01\n---\nBody\n"
        out = _strip_volatile_fields(text)
        assert "updated:" not in out
        assert "created: 2026-01-01" in out
        assert "slug: x" in out

    def test_two_dates_compare_equal_modulo_updated(self):
        a = "---\nslug: x\nupdated: 2026-05-11\n---\nBody\n"
        b = "---\nslug: x\nupdated: 2026-05-28\n---\nBody\n"
        assert _strip_volatile_fields(a) == _strip_volatile_fields(b)


class TestPromoteUpdateIdempotency:
    def test_create_then_update_is_byte_identical(self, temp_entities):
        """Create an entity, then re-run promote against the SAME item twice.

        The first update and the second must both be no-ops: zero file
        modifications, byte-identical content, no `updated:` bump.
        """
        scored = _scored()
        # First call: creates the page.
        created_path = promote_item(scored, "test-entity", entity_type="concept")
        assert created_path is not None and created_path.exists()
        original_bytes = created_path.read_bytes()

        # Force the stored `updated:` to a stale date so a naive bump WOULD
        # change the file — the guard must still skip because nothing else
        # differs.
        stale = created_path.read_text().replace(
            f"updated: {bookkeeping.today_str()}", "updated: 2026-05-11"
        )
        created_path.write_text(stale)
        stale_bytes = created_path.read_bytes()

        # Second call: existing entity → update path. No semantic delta, so
        # the guard must SKIP (return None, leave bytes untouched).
        ret = promote_item(scored, "test-entity", entity_type="concept")
        assert ret is None, "no-op update must return None (not counted as updated)"
        assert created_path.read_bytes() == stale_bytes, "file must be byte-identical"

        # Third call again — still a no-op.
        ret2 = promote_item(scored, "test-entity", entity_type="concept")
        assert ret2 is None
        assert created_path.read_bytes() == stale_bytes

        # And it never reverted to the freshly-created content either.
        assert created_path.read_bytes() != original_bytes  # we deliberately staled it

    def test_run_pipeline_second_pass_zero_modifications(self, temp_entities, tmp_path, monkeypatch):
        """End-to-end: two `run_pipeline` invocations over the same frozen raw
        extract must leave entity files unchanged on the second pass.
        """
        notes = tmp_path / "research" / "notes"
        notes.mkdir(parents=True)
        monkeypatch.setattr(bookkeeping, "NOTES_DIR", notes)
        # Point config dir at a temp location so we don't touch ~/.config.
        monkeypatch.setattr(bookkeeping, "CONFIG_DIR", tmp_path / ".config")
        monkeypatch.setattr(bookkeeping, "RUN_LOG", tmp_path / ".config" / "run-log.jsonl")
        monkeypatch.setattr(bookkeeping, "STATUS_CACHE", tmp_path / ".config" / "status.json")

        raw = notes / "2026-05-28-test-raw.md"
        # A high-signal item that will score >= threshold and resolve to a slug.
        raw.write_text(
            "---\nsource: test\n---\n\n"
            "## Item 1 — @someone (web)\n\n"
            "**Score**: 7/9 — novelty:3 specificity:2 relevance:2\n\n"
            "**Our angle**: The arcan agent loop uses bi-temporal event sourcing "
            "because the soul file must replay deterministically; this means the "
            "promotion gate and memory provenance stay consistent across 1000 runs.\n"
        )

        bookkeeping.run_pipeline(verbose=False)
        snapshot = {
            p: p.read_bytes()
            for p in temp_entities.rglob("*.md")
        }
        assert snapshot, "first pass should have created at least one entity"

        # Second pass over the SAME frozen raw extract.
        bookkeeping.run_pipeline(verbose=False)
        after = {p: p.read_bytes() for p in temp_entities.rglob("*.md")}

        assert set(after) == set(snapshot), "no entity files added/removed on 2nd pass"
        for p, b in snapshot.items():
            assert after[p] == b, f"{p.name} was rewritten on the idempotent 2nd pass"

    def test_real_semantic_delta_still_writes(self, temp_entities, monkeypatch):
        """If the would-be content differs for a reason other than `updated:`,
        the guard MUST write and bump `updated:`.

        The production update path is currently timestamp-only, so to exercise
        the write branch we monkeypatch the `_render_updated_entity` seam to
        also introduce a genuine body delta — modelling a future semantic
        merge. The guard must then write the candidate and return True.
        """
        scored = _scored()
        path = promote_item(scored, "test-entity", entity_type="concept")
        # Stale the stored date.
        path.write_text(path.read_text().replace(
            f"updated: {bookkeeping.today_str()}", "updated: 2026-05-11"
        ))
        before = path.read_text()

        real_render = bookkeeping._render_updated_entity

        def render_with_delta(existing):
            return real_render(existing) + "\nSEMANTIC DELTA\n"

        monkeypatch.setattr(bookkeeping, "_render_updated_entity", render_with_delta)
        wrote = bookkeeping._update_entity_page_if_changed(path, dry_run=False)

        assert wrote is True, "a real semantic delta must trigger a write"
        after = path.read_text()
        assert after != before
        assert "SEMANTIC DELTA" in after
        # `updated:` was bumped to today as part of the real write.
        assert f"updated: {bookkeeping.today_str()}" in after

    def test_dry_run_never_writes(self, temp_entities, monkeypatch):
        """Even with a real delta, dry_run must report-but-not-write."""
        scored = _scored()
        path = promote_item(scored, "test-entity", entity_type="concept")
        path.write_text(path.read_text().replace(
            f"updated: {bookkeeping.today_str()}", "updated: 2026-05-11"
        ))
        before = path.read_bytes()
        real_render = bookkeeping._render_updated_entity
        monkeypatch.setattr(
            bookkeeping, "_render_updated_entity",
            lambda existing: real_render(existing) + "\nDELTA\n",
        )
        wrote = bookkeeping._update_entity_page_if_changed(path, dry_run=True)
        assert wrote is True  # a write WOULD happen
        assert path.read_bytes() == before  # but dry_run wrote nothing


# ── Fix 2: lint --fix mechanical auto-repair ────────────────────────────────────

class TestCanonicalizeRelatedValue:
    def test_bare_slug(self):
        assert _canonicalize_related_value("foo-bar") == "[[foo-bar]]"

    def test_path_form_full(self):
        assert _canonicalize_related_value(
            "research/entities/project/lifed.md"
        ) == "[[lifed]]"

    def test_path_form_basename(self):
        assert _canonicalize_related_value("bar.md") == "[[bar]]"

    def test_already_wikilink_is_idempotent(self):
        assert _canonicalize_related_value("[[arcan]]") == "[[arcan]]"

    def test_quoted_bare_slug(self):
        assert _canonicalize_related_value('"foo-bar"') == "[[foo-bar]]"

    def test_value_with_space_is_not_fixable(self):
        assert _canonicalize_related_value("not a slug") is None

    def test_empty_is_not_fixable(self):
        assert _canonicalize_related_value("  ") is None


def _write_entity(entities, slug, related_block, core_claim='"a valid claim"'):
    path = entities / "concept" / f"{slug}.md"
    path.write_text(
        "---\n"
        f"slug: {slug}\n"
        "type: concept\n"
        "status: candidate\n"
        f"core_claim: {core_claim}\n"
        "sources:\n"
        "  - test-source\n"
        f"{related_block}"
        "created: 2026-01-01\n"
        "updated: 2026-01-01\n"
        "tags:\n"
        "  - concept\n"
        "---\n\n"
        "# Title\n\nBody\n"
    )
    return path


class TestFixEntityPageBlockForm:
    def test_repairs_bare_slug_and_path_form(self, temp_entities):
        path = _write_entity(
            temp_entities, "e1",
            "related:\n  - jepa-as-substrate\n  - research/entities/project/lifed.md\n",
        )
        n_fixed, unfixable = fix_entity_page(path)
        assert n_fixed == 2
        assert unfixable == []
        text = path.read_text()
        assert '- "[[jepa-as-substrate]]"' in text
        assert '- "[[lifed]]"' in text
        # Re-parse: related entries now pass the lint regex.
        fm, _ = bookkeeping.parse_frontmatter(text)
        import re
        for r in fm["related"]:
            assert re.match(r"^\[\[.+\]\]$", str(r))

    def test_idempotent(self, temp_entities):
        path = _write_entity(
            temp_entities, "e2", "related:\n  - jepa-as-substrate\n",
        )
        n1, _ = fix_entity_page(path)
        assert n1 == 1
        first = path.read_bytes()
        n2, _ = fix_entity_page(path)
        assert n2 == 0, "second fix run must apply no further changes"
        assert path.read_bytes() == first, "file must be byte-identical on 2nd fix"

    def test_already_canonical_is_noop(self, temp_entities):
        path = _write_entity(
            temp_entities, "e3", 'related:\n  - "[[arcan]]"\n',
        )
        before = path.read_bytes()
        n, unfixable = fix_entity_page(path)
        assert n == 0
        assert unfixable == []
        assert path.read_bytes() == before

    def test_preserves_other_frontmatter_and_body(self, temp_entities):
        path = _write_entity(
            temp_entities, "e4", "related:\n  - foo\n",
        )
        fix_entity_page(path)
        text = path.read_text()
        assert "core_claim: \"a valid claim\"" in text
        assert "created: 2026-01-01" in text
        assert "updated: 2026-01-01" in text  # fixer does NOT touch updated:
        assert "# Title" in text and "Body" in text


class TestFixEntityPageInlineForm:
    def test_inline_list_repaired(self, temp_entities):
        path = _write_entity(
            temp_entities, "e5", "related: [foo, bar.md]\n",
        )
        n, unfixable = fix_entity_page(path)
        assert n == 2
        text = path.read_text()
        assert '"[[foo]]"' in text and '"[[bar]]"' in text

    def test_empty_inline_untouched(self, temp_entities):
        path = _write_entity(temp_entities, "e6", "related: []\n")
        before = path.read_bytes()
        n, _ = fix_entity_page(path)
        assert n == 0
        assert path.read_bytes() == before


class TestLintFixDoesNotTouchCoreClaim:
    def test_long_core_claim_reported_not_fixed(self, temp_entities, capsys):
        long_claim = '"' + ("x" * 200) + '"'
        path = _write_entity(
            temp_entities, "e7", "related:\n  - foo\n", core_claim=long_claim,
        )
        # Drive the CLI path with --fix.
        args = argparse.Namespace(all=False, file=str(path), fix=True, verbose=False)
        with pytest.raises(SystemExit):
            cmd_lint(args)
        out = capsys.readouterr().out
        # The related entry was repaired ...
        assert "[[foo]]" in path.read_text()
        # ... but core_claim length is still reported as an unfixed error.
        assert "core_claim" in out
        # And the long core_claim was NOT rewritten/truncated by --fix.
        assert ("x" * 200) in path.read_text()


# ── P20 regression: frontmatter-anchored volatile strip (2026-05-28) ────────────
# Adversarial review of PR #8 found _strip_volatile_fields / _render_updated_entity
# ran their re.MULTILINE transforms over the WHOLE document, not just frontmatter.
# Latent vector: a future semantic-merge that appends a body line beginning
# "updated:" would be silently discarded as a no-op. These lock the fix.

_PAGE_WITH_BODY_UPDATED = (
    "---\n"
    "id: concept/x\n"
    "updated: 2026-05-11\n"
    "---\n"
    "\n"
    "## Timeline\n"
    "updated: a real fact appended by a future merge\n"
)


def test_split_frontmatter_separates_fences_and_body():
    fm, body = _split_frontmatter(_PAGE_WITH_BODY_UPDATED)
    assert fm.startswith("---\n") and fm.rstrip().endswith("---")
    assert "updated: 2026-05-11" in fm          # frontmatter field is in the fm block
    assert "## Timeline" in body                # body is separated
    assert "updated: a real fact" in body       # body 'updated:' line lives in body


def test_split_frontmatter_no_frontmatter_returns_empty_fm():
    fm, body = _split_frontmatter("plain body\nupdated: not frontmatter\n")
    assert fm == ""
    assert body == "plain body\nupdated: not frontmatter\n"


def test_strip_volatile_preserves_body_updated_line():
    """The frontmatter 'updated:' is stripped; a body line starting 'updated:' is NOT."""
    stripped = _strip_volatile_fields(_PAGE_WITH_BODY_UPDATED)
    assert "updated: 2026-05-11" not in stripped              # frontmatter field gone
    assert "updated: a real fact" in stripped                 # body line preserved


def test_guard_would_detect_body_only_change():
    """
    Two pages identical except for a body line beginning 'updated:' must compare
    DIFFERENT after volatile-stripping — i.e. the no-op guard would NOT fire and a
    real change is preserved. This is the exact P20 data-loss vector, now closed.
    """
    without = "---\nid: concept/x\nupdated: 2026-05-11\n---\n\n## Timeline\n"
    with_fact = without + "updated: a real fact appended by a future merge\n"
    assert _strip_volatile_fields(without) != _strip_volatile_fields(with_fact)


def test_render_updated_only_bumps_frontmatter(monkeypatch):
    monkeypatch.setattr(bookkeeping, "today_str", lambda: "2026-05-28")
    out = _render_updated_entity(_PAGE_WITH_BODY_UPDATED)
    fm, body = _split_frontmatter(out)
    assert "updated: 2026-05-28" in fm                         # frontmatter bumped
    assert "updated: a real fact" in body                      # body line untouched
    assert "updated: 2026-05-28" not in body                   # body NOT bumped


# ── Phase 1: persona entity type registered (2026-05-28) ────────────────────────

def test_persona_is_registered_entity_type():
    assert "persona" in bookkeeping.ENTITY_TYPES
    # drift fix: disk had these dirs but the list didn't
    assert "framework-refinement" in bookkeeping.ENTITY_TYPES
    assert "industry-pattern" in bookkeeping.ENTITY_TYPES


def test_lint_accepts_persona_type(tmp_path, monkeypatch):
    """A type: persona entity must lint WITHOUT a 'type not in' warning."""
    monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
    p = tmp_path / "persona-x.md"
    p.write_text(
        "---\n"
        "id: persona/railway-deploy-default\n"
        "title: Default Deploy Target Is Railway\n"
        "type: persona\n"
        "status: entity\n"
        "created: 2026-05-28\n"
        "updated: 2026-05-28\n"
        "tags: [persona, constraint, deploy]\n"
        "sources:\n"
        "  - type: explicit-statement\n"
        "    extraction_date: 2026-05-28\n"
        'core_claim: "Default deploy target is Railway; suggest AWS only on explicit ask."\n'
        "related: []\n"
        "---\n\n"
        "## Compiled Truth\nRailway-first; no US entity.\n\n---\n\n## Timeline\n- 2026-05-28 — seeded.\n"
    )
    errors = bookkeeping.lint_entity_page(p)
    type_warnings = [e for e in errors if e.field == "type"]
    assert not type_warnings, f"persona type should be accepted, got: {type_warnings}"


# ── Durable dedup: merge tombstone mechanism (BRO-1442) ────────────────────────

class TestMergeTombstone:
    """`bookkeeping merge` folds a dup into a canonical durably: repoint links,
    alias the canonical, tombstone the dup, exclude it from the catalog, and —
    the linchpin — make `promote` SKIP it so it never resurrects."""

    def _write(self, entities, type_dir, slug, status="entity", claim="A claim.", body="body"):
        p = entities / type_dir / f"{slug}.md"
        p.write_text(
            f"---\nslug: {slug}\ntype: {type_dir}\nstatus: {status}\n"
            f'core_claim: "{claim}"\n---\n# {slug}\n{body}\n'
        )
        return p

    def test_merge_tombstones_repoints_and_aliases(self, temp_entities):
        self._write(temp_entities, "tool", "kept", claim="The canonical thing.")
        self._write(temp_entities, "tool", "dupe", claim="A duplicate of kept.")
        linker = temp_entities / "concept" / "linker.md"
        linker.write_text(
            "---\nslug: linker\ntype: concept\nstatus: entity\n"
            'core_claim: "links to dupe."\nrelated:\n  - "[[dupe]]"\n---\n'
            "# linker\nSee [[dupe]] for details.\n"
        )
        bookkeeping.cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))

        dupe_text = (temp_entities / "tool" / "dupe.md").read_text()
        kept_text = (temp_entities / "tool" / "kept.md").read_text()
        linker_text = linker.read_text()

        # tombstone
        assert "status: merged" in dupe_text and "merged_into: kept" in dupe_text
        # canonical aliased
        assert "aliases:" in kept_text and "- dupe" in kept_text
        # inbound links repointed
        assert "[[kept]]" in linker_text and "[[dupe]]" not in linker_text
        # detector finds it
        assert bookkeeping._merged_tombstone_path("dupe") is not None

    def test_catalog_excludes_tombstone(self, temp_entities):
        self._write(temp_entities, "tool", "kept", claim="The canonical thing.")
        self._write(temp_entities, "tool", "dupe", status="merged", claim="Merged into [[kept]].")
        collected = bookkeeping._catalog_collect()
        assert "kept" in collected["nodes"]
        assert "dupe" not in collected["nodes"], "merged tombstone must not appear in catalog"

    def test_promote_skips_tombstone_but_creates_fresh(self, temp_entities):
        # tombstone for 'dupe'
        self._write(temp_entities, "tool", "dupe", status="merged", claim="Merged into [[kept]].")
        scored = _scored(content="A duplicate of kept.")

        # LINCHPIN: promote must SKIP the tombstoned slug (no resurrection).
        ret = promote_item(scored, "dupe", entity_type="tool")
        assert ret is None, "promote must skip a merged tombstone"
        assert "status: merged" in (temp_entities / "tool" / "dupe.md").read_text()

        # CONTROL: a fresh slug still promotes normally.
        ret2 = promote_item(scored, "brandnew", entity_type="tool")
        assert ret2 is not None and (temp_entities / "tool" / "brandnew.md").exists()

    def test_lint_accepts_merged_status(self, temp_entities):
        p = self._write(temp_entities, "tool", "dupe", status="merged", claim="Merged into [[kept]].")
        errors = bookkeeping.lint_entity_page(p)
        status_warnings = [e for e in errors if e.field == "status"]
        assert not status_warnings, f"status: merged must be valid, got: {status_warnings}"

    def test_merge_is_idempotent(self, temp_entities):
        self._write(temp_entities, "tool", "kept", claim="The canonical thing.")
        self._write(temp_entities, "tool", "dupe", claim="A duplicate of kept.")
        bookkeeping.cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        first = (temp_entities / "tool" / "dupe.md").read_text()
        # second merge is a no-op (already a tombstone)
        bookkeeping.cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        assert (temp_entities / "tool" / "dupe.md").read_text() == first


class TestMergeTombstoneReviewFixes:
    """Regressions for the P20 cross-review findings on the merge mechanism."""

    def _write(self, entities, type_dir, slug, status="entity", claim="A claim.",
               sources='  - 2026-01-01-x\n', extra=""):
        p = entities / type_dir / f"{slug}.md"
        src = f"sources:\n{sources}" if sources else ""
        p.write_text(
            f"---\nslug: {slug}\ntype: {type_dir}\nstatus: {status}\n"
            f'core_claim: "{claim}"\n{src}{extra}---\n# {slug}\nbody\n'
        )
        return p

    def test_tombstone_passes_lint_no_sources_error(self, temp_entities):
        # BLOCKER fix: a tombstone has no sources / pointer claim — must still lint clean.
        self._write(temp_entities, "tool", "kept", claim="canonical")
        self._write(temp_entities, "tool", "dupe", claim="dup of kept")
        bookkeeping.cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        errors = bookkeeping.lint_entity_page(temp_entities / "tool" / "dupe.md")
        hard = [e for e in errors if e.severity == "error"]
        assert not hard, f"tombstone must produce no lint errors, got: {hard}"

    def test_cross_type_same_slug_tombstone_does_not_block_promotion(self, temp_entities):
        # MAJOR fix: a merged tombstone in one type dir must not suppress a live
        # entity with the same slug in a DIFFERENT type dir.
        self._write(temp_entities, "concept", "foo", status="merged", claim="merged", sources="")
        scored = _scored(content="legit tool foo")
        ret = promote_item(scored, "foo", entity_type="tool")  # different dir
        assert ret is not None and (temp_entities / "tool" / "foo.md").exists(), \
            "live entity must be created despite a same-slug tombstone in another type dir"

    def test_alias_into_inline_flow_list_no_dup_key(self, temp_entities):
        # MAJOR fix: existing inline `aliases: [a, b]` must append, not duplicate the key.
        text = ('---\nslug: kept\ntype: tool\nstatus: entity\n'
                'aliases: [alpha, beta]\ncore_claim: "x"\n---\nbody\n')
        out = bookkeeping._add_alias_to_frontmatter(text, "dupe")
        assert out.count("aliases:") == 1, "must not create a second aliases: key"
        assert "alpha" in out and "beta" in out and "dupe" in out, "prior aliases preserved + new added"

    def test_refuse_merge_into_tombstone(self, temp_entities):
        # MAJOR fix: merging INTO an already-merged tombstone must be refused.
        self._write(temp_entities, "tool", "c", claim="canonical")
        self._write(temp_entities, "tool", "b", claim="b")
        bookkeeping.cmd_merge(argparse.Namespace(dup="b", canonical="c", dry_run=False))  # b → tombstone
        self._write(temp_entities, "tool", "a", claim="a")
        with pytest.raises(SystemExit) as exc:
            bookkeeping.cmd_merge(argparse.Namespace(dup="a", canonical="b", dry_run=False))
        assert exc.value.code != 0, "merging into a tombstone must exit non-zero"
        # 'a' must remain a live entity (not tombstoned)
        assert "status: entity" in (temp_entities / "tool" / "a.md").read_text()

    def test_repoint_covers_notes_dir(self, tmp_path, monkeypatch):
        # MINOR fix: synthesis notes (research/notes/) also get repointed.
        entities = tmp_path / "research" / "entities"
        notes = tmp_path / "research" / "notes"
        for et in bookkeeping.ENTITY_TYPES:
            (entities / et).mkdir(parents=True, exist_ok=True)
        notes.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
        monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
        monkeypatch.setattr(bookkeeping, "NOTES_DIR", notes)
        (entities / "tool" / "kept.md").write_text(
            '---\nslug: kept\ntype: tool\nstatus: entity\ncore_claim: "x"\nsources:\n  - s\n---\nbody\n')
        (entities / "tool" / "dupe.md").write_text(
            '---\nslug: dupe\ntype: tool\nstatus: entity\ncore_claim: "y"\nsources:\n  - s\n---\nbody\n')
        note = notes / "2026-01-01-synth.md"
        note.write_text("# synth\nReferences [[dupe]] in a note.\n")
        bookkeeping.cmd_merge(argparse.Namespace(dup="dupe", canonical="kept", dry_run=False))
        assert "[[kept]]" in note.read_text() and "[[dupe]]" not in note.read_text()


class TestCatalogAliasEmit:
    """BRO-1423: catalog emits `aka:` aliases; lint checks tombstone↔canonical."""

    def _block(self, slug, aliases=None, type_dir="tool"):
        node = {"fm": {"type": type_dir, "status": "entity",
                       "core_claim": "A claim.",
                       "aliases": aliases or []},
                "body": "body", "type_dir": type_dir,
                "path": str(bookkeeping.ENTITIES_DIR / type_dir / f"{slug}.md")}
        return bookkeeping._catalog_render_entity_block(slug, node, {}, {})

    def test_aliases_emitted_as_aka_segment(self, temp_entities):
        line3 = self._block("kept", aliases=["oldname", "synonym"]).splitlines()[2]
        assert "aka: oldname, synonym" in line3

    def test_no_aka_when_no_aliases(self, temp_entities):
        block = self._block("kept", aliases=[])
        assert "aka:" not in block

    def test_aliases_capped(self, temp_entities):
        # full preset caps at _CATALOG_TOP_ALIASES (5)
        many = [f"a{i}" for i in range(10)]
        line3 = self._block("kept", aliases=many).splitlines()[2]
        emitted = line3.split("aka: ")[1].split(" · ")[0].split(", ")
        assert len(emitted) == bookkeeping._CATALOG_TOP_ALIASES

    def test_lint_flags_tombstone_not_aliased_on_canonical(self, temp_entities):
        # canonical WITHOUT the dup alias → tombstone lint warns
        (temp_entities / "tool" / "canon.md").write_text(
            '---\nslug: canon\ntype: tool\nstatus: entity\ncore_claim: "c"\n'
            "sources:\n  - s\n---\nbody\n")
        (temp_entities / "tool" / "dupe.md").write_text(
            "---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: canon\n"
            'core_claim: "Merged into [[canon]]."\n---\nmerged\n')
        warns = [e for e in bookkeeping.lint_entity_page(temp_entities / "tool" / "dupe.md")
                 if e.field == "merged_into"]
        assert warns, "tombstone whose slug isn't a canonical alias must warn"

    def test_lint_ok_when_tombstone_aliased(self, temp_entities):
        (temp_entities / "tool" / "canon.md").write_text(
            '---\nslug: canon\ntype: tool\nstatus: entity\ncore_claim: "c"\n'
            "sources:\n  - s\naliases:\n  - dupe\n---\nbody\n")
        (temp_entities / "tool" / "dupe.md").write_text(
            "---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: canon\n"
            'core_claim: "Merged into [[canon]]."\n---\nmerged\n')
        warns = [e for e in bookkeeping.lint_entity_page(temp_entities / "tool" / "dupe.md")
                 if e.field == "merged_into"]
        assert not warns, f"correctly-aliased tombstone must not warn, got: {warns}"


class TestCatalogAliasSanitize:
    """BRO-1423 review fixes: alias emit sanitization + lint robustness."""

    def _block(self, slug, aliases, type_dir="tool"):
        node = {"fm": {"type": type_dir, "status": "entity", "core_claim": "c",
                       "aliases": aliases},
                "body": "b", "type_dir": type_dir,
                "path": str(bookkeeping.ENTITIES_DIR / type_dir / f"{slug}.md")}
        return bookkeeping._catalog_render_entity_block(slug, node, {}, {})

    def test_drops_alias_with_delimiters(self, temp_entities):
        line3 = self._block("kept", ["good", "bad·mid", "bad,comma"]).splitlines()[2]
        assert "aka: good" in line3
        assert "bad·mid" not in line3 and "bad,comma" not in line3

    def test_drops_self_alias(self, temp_entities):
        block = self._block("kept", ["kept", "kept", "real"])
        line3 = block.splitlines()[2]
        assert "aka: real" in line3
        # 'kept' (==slug) must not appear as an alias
        assert "aka: kept" not in line3

    def test_dedups_aliases(self, temp_entities):
        line3 = self._block("kept", ["x", "X", "x", "y"]).splitlines()[2]
        akas = line3.split("aka: ")[1].split(" · ")[0].split(", ")
        assert akas == ["x", "y"], f"deduped case-insensitively (got {akas})"

    def test_lint_case_insensitive_alias_match(self, temp_entities):
        (temp_entities / "tool" / "canon.md").write_text(
            '---\nslug: canon\ntype: tool\nstatus: entity\ncore_claim: "c"\n'
            "sources:\n  - s\naliases:\n  - Dupe\n---\nb\n")  # capital D
        (temp_entities / "tool" / "dupe.md").write_text(
            "---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: canon\n"
            'core_claim: "Merged into [[canon]]."\n---\nm\n')
        warns = [e for e in bookkeeping.lint_entity_page(temp_entities / "tool" / "dupe.md")
                 if e.field == "merged_into"]
        assert not warns, f"case-insensitive alias match must not warn, got: {warns}"

    def test_lint_tolerates_wikilink_merged_into(self, temp_entities):
        (temp_entities / "tool" / "canon.md").write_text(
            '---\nslug: canon\ntype: tool\nstatus: entity\ncore_claim: "c"\n'
            "sources:\n  - s\naliases:\n  - dupe\n---\nb\n")
        (temp_entities / "tool" / "dupe.md").write_text(
            "---\nslug: dupe\ntype: tool\nstatus: merged\nmerged_into: \"[[canon]]\"\n"
            'core_claim: "Merged into [[canon]]."\n---\nm\n')
        warns = [e for e in bookkeeping.lint_entity_page(temp_entities / "tool" / "dupe.md")
                 if e.field == "merged_into"]
        assert not warns, f"[[wikilink]] merged_into must resolve, got: {warns}"
