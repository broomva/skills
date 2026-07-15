"""Unit tests for `cmd_index` (dense LLM-loadable catalog generator).

Covers the parser/renderer helpers in isolation + the cmd_index end-to-end
behavior against a deterministic temp-dir substrate. Locks invariants that
the P20 cross-review (BRO-1223) flagged as risky:

- slug clashes deterministically resolved (sorted last-write wins)
- pipe-separated sources (commas inside source URLs preserved)
- path: field emitted with relative path (slug-clash routing fix)
- claim truncation at 220 chars
- top-N caps on out/in/tags/sources
- dry-run is byte-deterministic across runs (modulo `generated:` timestamp)
- unicode in claims / slugs preserved
- empty substrate exits nonzero
"""
from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Import the bookkeeping module under test
import bookkeeping  # noqa: E402  (path injected by conftest.py)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def write_entity(root: Path, type_dir: str, slug: str, *,
                 fm: dict | None = None, body: str = "Body text.") -> Path:
    """Create a research/entities/{type_dir}/{slug}.md fixture."""
    d = root / type_dir
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{slug}.md"
    fm = fm or {}
    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}:")
            for item in v:
                fm_lines.append(f"  - {item}")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(body)
    p.write_text("\n".join(fm_lines))
    return p


@pytest.fixture
def temp_substrate(tmp_path, monkeypatch):
    """Set up a research/entities/ tree under tmp_path and patch the module's
    BROOMVA_ROOT + ENTITIES_DIR + CATALOG_PATH to point at it.

    CATALOG_PATH is now a first-class resolved constant (the cmd_index write
    path), decoupled from BROOMVA_ROOT, so redirecting the data root means
    patching all three."""
    root = tmp_path
    entities = root / "research" / "entities"
    entities.mkdir(parents=True)
    docs = root / "docs"
    docs.mkdir()
    monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", root)
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
    monkeypatch.setattr(bookkeeping, "CATALOG_PATH", docs / "knowledge-index.md")
    return root


# ── Helper isolation tests ────────────────────────────────────────────────────

class TestCoerceStrList:
    def test_none_returns_empty(self):
        assert bookkeeping._catalog_coerce_str_list(None) == []

    def test_string_wraps(self):
        assert bookkeeping._catalog_coerce_str_list("foo") == ["foo"]

    def test_list_of_strings_passthrough(self):
        assert bookkeeping._catalog_coerce_str_list(["a", "b"]) == ["a", "b"]

    def test_list_of_dicts_takes_first_scalar(self):
        result = bookkeeping._catalog_coerce_str_list([{"url": "u", "ts": "t"}])
        assert result == ["u"]

    def test_mixed_list(self):
        result = bookkeeping._catalog_coerce_str_list(["plain", {"k": "v"}])
        assert result == ["plain", "v"]


class TestExtractLinks:
    def test_simple_wikilinks(self):
        out = bookkeeping._catalog_extract_links("see [[foo]] and [[bar]]")
        assert out == ["foo", "bar"]

    def test_display_text_stripped(self):
        out = bookkeeping._catalog_extract_links("[[slug|display text]]")
        assert out == ["slug"]

    def test_anchor_stripped(self):
        out = bookkeeping._catalog_extract_links("[[slug#section]]")
        assert out == ["slug"]

    def test_no_links(self):
        assert bookkeeping._catalog_extract_links("plain text") == []


class TestStripMd:
    def test_inline_code(self):
        assert bookkeeping._catalog_strip_md("a `code` b") == "a code b"

    def test_bold_and_italic(self):
        assert bookkeeping._catalog_strip_md("**bold** and *italic*") == "bold and italic"

    def test_md_link(self):
        assert bookkeeping._catalog_strip_md("[foo](url)") == "foo"

    def test_wikilink(self):
        assert bookkeeping._catalog_strip_md("[[slug]]") == "slug"

    def test_multispace_collapses(self):
        assert bookkeeping._catalog_strip_md("a  \n  b") == "a b"


class TestClaimFor:
    def test_uses_fm_core_claim_when_present(self):
        out = bookkeeping._catalog_claim_for({"core_claim": "explicit claim"}, "body")
        assert out == "explicit claim"

    def test_falls_back_to_first_body_paragraph(self):
        body = "# Heading\n\nFirst paragraph.\n\nSecond."
        out = bookkeeping._catalog_claim_for({}, body)
        assert out == "First paragraph."

    def test_truncates_long_claims(self):
        long_claim = "x" * 500
        out = bookkeeping._catalog_claim_for({"core_claim": long_claim}, "body")
        # Truncated to (max-1) chars + ellipsis; max is 220
        assert len(out) == 220
        assert out.endswith("…")

    def test_no_claim_no_body(self):
        assert bookkeeping._catalog_claim_for({}, "") == "(no claim)"


# ── End-to-end cmd_index tests ────────────────────────────────────────────────

def _run_index_dry_run(monkeypatch) -> str:
    """Helper: call cmd_index in dry-run mode, capture stdout."""
    import argparse
    import io

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    args = argparse.Namespace(dry_run=True)
    try:
        bookkeeping.cmd_index(args)
    finally:
        monkeypatch.undo()
    return buf.getvalue()


class TestCmdIndex:
    def test_writes_catalog_atomically(self, temp_substrate):
        write_entity(temp_substrate / "research" / "entities", "concept", "alpha",
                     fm={"type": "concept", "status": "entity", "core_claim": "Alpha is the first."})
        write_entity(temp_substrate / "research" / "entities", "pattern", "beta",
                     fm={"type": "pattern", "status": "candidate", "core_claim": "Beta is patterned."})

        import argparse
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False))

        catalog = temp_substrate / "docs" / "knowledge-index.md"
        assert catalog.exists()
        text = catalog.read_text()
        assert "alpha" in text
        assert "beta" in text
        assert "schema: dense-catalog-v2" in text
        assert "entity_count: 2" in text

    def test_empty_substrate_exits_nonzero(self, temp_substrate):
        import argparse
        with pytest.raises(SystemExit) as exc:
            bookkeeping.cmd_index(argparse.Namespace(dry_run=True))
        assert exc.value.code == 1

    def test_slug_clash_resolved_deterministically(self, temp_substrate, capsys):
        """If same slug in two type dirs, sorted last-write wins; path field
        identifies the winning file unambiguously."""
        entities = temp_substrate / "research" / "entities"
        write_entity(entities, "pattern", "anima",
                     fm={"type": "pattern", "status": "candidate", "core_claim": "Pattern claim."})
        write_entity(entities, "tool", "anima",
                     fm={"type": "tool", "status": "entity", "core_claim": "Tool claim."})

        import argparse
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False))
        catalog_text = (temp_substrate / "docs" / "knowledge-index.md").read_text()

        # Exactly one #### anima block (the later-sorted file wins — 'tool' > 'pattern')
        anima_headers = re.findall(r"^#### anima \[.+?\]", catalog_text, re.MULTILINE)
        assert len(anima_headers) == 1
        assert "[tool·entity]" in catalog_text  # tool wins (sorted alphabetically last)

        # And the path field disambiguates
        assert re.search(r"path:\s+tool/anima\.md", catalog_text)

    def test_path_field_present_for_every_entity(self, temp_substrate):
        entities = temp_substrate / "research" / "entities"
        write_entity(entities, "concept", "alpha",
                     fm={"type": "concept", "status": "entity", "core_claim": "A."})
        write_entity(entities, "pattern", "beta",
                     fm={"type": "pattern", "status": "entity", "core_claim": "B."})

        import argparse
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False))
        text = (temp_substrate / "docs" / "knowledge-index.md").read_text()

        # Count `path:` occurrences — should be 2 (one per entity)
        path_lines = re.findall(r"^path:\s+\S+", text, re.MULTILINE)
        assert len(path_lines) == 2
        assert "path: concept/alpha.md" in text
        assert "path: pattern/beta.md" in text

    def test_sources_use_pipe_separator(self, temp_substrate):
        """C3 fix — sources with commas in parens must NOT fragment."""
        entities = temp_substrate / "research" / "entities"
        write_entity(entities, "concept", "src-test",
                     fm={
                         "type": "concept", "status": "entity",
                         "core_claim": "Test.",
                         "sources": [
                             "https://example.com/a (note, with comma)",
                             "https://example.com/b",
                         ],
                     })

        import argparse
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False))
        text = (temp_substrate / "docs" / "knowledge-index.md").read_text()

        # Pipe-separated, NOT comma-split
        assert "https://example.com/a (note, with comma) | https://example.com/b" in text

    def test_tags_truncated_to_top_n(self, temp_substrate):
        entities = temp_substrate / "research" / "entities"
        write_entity(entities, "concept", "many-tags",
                     fm={"type": "concept", "status": "entity",
                         "core_claim": "Test.",
                         "tags": [f"tag{i}" for i in range(10)]})

        import argparse
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False))
        text = (temp_substrate / "docs" / "knowledge-index.md").read_text()

        # Top 4 tags only — bookkeeping._CATALOG_TOP_TAGS
        emitted_tags = re.findall(r"#tag\d+", text)
        assert len(emitted_tags) == bookkeeping._CATALOG_TOP_TAGS

    def test_unicode_in_claim_preserved(self, temp_substrate):
        entities = temp_substrate / "research" / "entities"
        write_entity(entities, "concept", "unicode-test",
                     fm={"type": "concept", "status": "entity",
                         "core_claim": "λ-stability, μ-control, π is irrational"})

        import argparse
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False))
        text = (temp_substrate / "docs" / "knowledge-index.md").read_text()
        assert "λ-stability, μ-control, π is irrational" in text

    def test_compact_mode_shrinks_catalog(self, temp_substrate):
        """`--compact` reduces per-entity caps; catalog tokens drop meaningfully.

        Locks the compact-mode behavior surfaced by the haystack benchmark
        (catalog tokens crossed 1M at 10k entities; compact buys ~15% back).
        """
        entities = temp_substrate / "research" / "entities"
        for i in range(50):
            write_entity(entities, "concept", f"entity-{i:03d}",
                         fm={"type": "concept", "status": "entity",
                             "core_claim": "Long claim that exceeds 100 chars but stays under 220 chars — this triggers the per-entity claim cap.",
                             "tags": [f"tag-{j}" for j in range(8)]},
                         body="Body text " * 30)

        import argparse
        # Full mode
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False, compact=False, no_compact=True))
        full_text = (temp_substrate / "docs" / "knowledge-index.md").read_text()
        # Compact mode
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False, compact=True, no_compact=False))
        compact_text = (temp_substrate / "docs" / "knowledge-index.md").read_text()

        assert "compact: false" in full_text
        assert "schema: dense-catalog-v2" in full_text
        assert "compact: true" in compact_text
        assert "schema: dense-catalog-v2-compact" in compact_text
        # Compact must be strictly smaller (claim truncation + fewer tags)
        assert len(compact_text) < len(full_text)

    def test_auto_compact_below_threshold(self, temp_substrate):
        """Auto-compact stays OFF when entity count is below threshold."""
        entities = temp_substrate / "research" / "entities"
        for i in range(10):
            write_entity(entities, "concept", f"e{i}",
                         fm={"type": "concept", "status": "entity",
                             "core_claim": f"Entity {i}"})

        import argparse
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False, compact=False, no_compact=False))
        text = (temp_substrate / "docs" / "knowledge-index.md").read_text()
        assert "compact: false" in text  # 10 < threshold → no auto-compact

    def test_dry_run_byte_deterministic_modulo_timestamp(self, temp_substrate, monkeypatch, capsys):
        """Same substrate → identical catalog output (modulo `generated:` line)."""
        entities = temp_substrate / "research" / "entities"
        for i in range(5):
            write_entity(entities, "concept", f"e{i}",
                         fm={"type": "concept", "status": "entity",
                             "core_claim": f"Entity {i}"})

        import argparse

        bookkeeping.cmd_index(argparse.Namespace(dry_run=True, compact=False, no_compact=False))
        out1 = capsys.readouterr().out

        bookkeeping.cmd_index(argparse.Namespace(dry_run=True, compact=False, no_compact=False))
        out2 = capsys.readouterr().out

        # Strip the generated: timestamp line for comparison
        def normalize(s: str) -> str:
            return re.sub(r"^generated:.*$", "generated: <ts>", s, flags=re.MULTILINE)

        assert normalize(out1) == normalize(out2)


# ── Tier-2 body-search regression test ───────────────────────────────────────
# Locks the behavior that fired when the benchmark surfaced a 30% recall gap
# (BRO-1223 follow-up): topics whose vocabulary appears only in entity bodies
# — not in catalog claim/tags/slug/links/sources — must still be recoverable
# via the tier-2 body-grep fallback. Without this test, future kg.py changes
# could regress the recall-1.0 guarantee that justifies the LLM-as-index
# token math.

class TestKgTier2BodyFallback:
    """The catalog has zero signal for the topic — body grep recovers it."""

    def test_topic_only_in_body_is_recovered(self, tmp_path, monkeypatch):
        # Substrate: one entity whose claim/tags/slug DON'T match the topic,
        # but whose body DOES. The topic word "obscurevocab" must not appear
        # in catalog fields so the catalog-only path returns 0 matches.
        entities = tmp_path / "research" / "entities"
        entities.mkdir(parents=True)
        docs = tmp_path / "docs"
        docs.mkdir()
        monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
        monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
        monkeypatch.setattr(bookkeeping, "CATALOG_PATH", docs / "knowledge-index.md")

        write_entity(
            entities, "concept", "carrier",
            fm={
                "type": "concept", "status": "entity",
                "core_claim": "A completely unrelated claim.",
                "tags": ["other"],
            },
            body=(
                "# Carrier entity\n\n"
                "The body of this entity mentions obscurevocab in its prose.\n"
                "The dense catalog will not see this term because it lives "
                "in the body, not the metadata."
            ),
        )
        write_entity(
            entities, "concept", "decoy",
            fm={"type": "concept", "status": "entity",
                "core_claim": "Decoy claim with no match.", "tags": ["other"]},
            body="Decoy body. Nothing of interest here.",
        )

        import argparse
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False))
        catalog_path = docs / "knowledge-index.md"
        catalog_text = catalog_path.read_text()

        # Test invariant: topic word must NOT appear in catalog
        # (otherwise the test wouldn't actually exercise the tier-2 path)
        assert "obscurevocab" not in catalog_text.lower(), (
            "Test invariant: topic word must NOT appear in catalog metadata"
        )

        # Locate kg.py: search known install + workspace-mirror locations.
        # Honors BROOMVA_ROOT (workspace root) and KG_PY (explicit override)
        # env vars per BRO-1223 follow-up — unblocks CI runners and
        # non-standard host layouts where ~/broomva isn't the workspace.
        # Hard-fail (NOT silent skip) when missing — silent skip = green CI
        # that hides regressions, the exact failure mode tests are meant to
        # prevent.
        import os as _os
        workspace_root = Path(_os.environ.get("BROOMVA_ROOT",
                                              Path.home() / "broomva"))
        candidate_paths: list[Path] = []
        if env_kg := _os.environ.get("KG_PY"):
            candidate_paths.append(Path(env_kg))
        candidate_paths.extend([
            Path.home() / ".claude" / "skills" / "kg" / "scripts" / "kg.py",
            workspace_root / "docs" / "skills" / "kg" / "kg.py",
        ])
        kg_path = next((p for p in candidate_paths if p.exists()), None)
        if kg_path is None:
            # Cross-skill integration test (kg lives in a separate repo). In the
            # full workspace (BROOMVA_ROOT set, or ~/broomva present) kg.py SHOULD
            # exist → hard-fail so a real regression stays loud (the author's
            # intent). In a standalone repo CI (kg legitimately absent) → skip
            # with a visible reason rather than fail the unrelated suite. A
            # reported skip is in the pytest summary, not silent.
            in_workspace = bool(_os.environ.get("BROOMVA_ROOT")) or (Path.home() / "broomva").exists()
            msg = (
                "TestKgTier2BodyFallback requires kg.py at one of:\n  "
                + "\n  ".join(str(p) for p in candidate_paths)
                + "\nInstall via `npx skills add broomva/kg`, "
                "or set BROOMVA_ROOT/KG_PY env vars."
            )
            if in_workspace:
                pytest.fail(msg)
            pytest.skip(msg + "\n(standalone CI — kg.py absent; cross-skill test skipped)")

        import importlib.util
        spec = importlib.util.spec_from_file_location("kg_under_test", str(kg_path))
        kg_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kg_mod)
        monkeypatch.setattr(kg_mod, "BROOMVA_ROOT", tmp_path)
        monkeypatch.setattr(kg_mod, "ENTITIES_DIR", entities)
        monkeypatch.setattr(kg_mod, "CATALOG_PATH", catalog_path)

        # Drive cmd_load with --body-search forced
        args = argparse.Namespace(
            topic="obscurevocab",
            n=5,
            type=None,
            json=True,
            no_bodies=True,
            body_search=True,
            quiet=False,  # capture stderr to assert tier-2 fired
        )

        import io, contextlib
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            rc = kg_mod.cmd_load(args)

        assert rc == 0, "tier-2 path should return matches (rc=0)"

        import json as json_mod
        payload = json_mod.loads(out_buf.getvalue())
        slugs = {m["slug"] for m in payload.get("matches", [])}
        assert "carrier" in slugs, (
            f"Tier-2 body-grep should have found 'carrier' "
            f"(obscurevocab in body). Got: {sorted(slugs)}"
        )
        # Also assert tier-2 actually fired (vs tier-1 accidentally succeeding).
        # Catalog has zero signal so tier-1 must have returned 0 matches.
        assert "tier-2 body search added" in err_buf.getvalue(), (
            f"Tier-2 path should have fired (tier-1 should find 0 hits "
            f"since topic word not in catalog). stderr: {err_buf.getvalue()!r}"
        )
