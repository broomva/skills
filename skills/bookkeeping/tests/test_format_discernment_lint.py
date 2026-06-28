"""Tests for the four format-discernment lint checks."""
import os
import time
from pathlib import Path
import pytest
from bookkeeping import lint_format_discernment


class TestStaleProjection:
    def test_clean(self, tmp_path):
        md = tmp_path / "x-synthesis.md"
        html = tmp_path / "x-synthesis.html"
        md.write_text("---\nslug: x\n---\nBody")
        html.write_text("<!DOCTYPE html><html></html>")
        future = time.time() + 10
        os.utime(html, (future, future))
        errors = lint_format_discernment(tmp_path)
        assert [e for e in errors if e.field == "stale_projection"] == []

    def test_stale(self, tmp_path):
        md = tmp_path / "x-synthesis.md"
        html = tmp_path / "x-synthesis.html"
        md.write_text("---\nslug: x\n---\nBody")
        html.write_text("<!DOCTYPE html><html></html>")
        past = time.time() - 10
        os.utime(html, (past, past))
        errors = lint_format_discernment(tmp_path)
        stale = [e for e in errors if e.field == "stale_projection"]
        assert len(stale) == 1
        assert stale[0].severity == "warning"
        assert "x-synthesis.html" in stale[0].file_path


class TestBrokenCanonical:
    def test_clean(self, tmp_path):
        md = tmp_path / "x.md"
        html = tmp_path / "x.html"
        md.write_text("---\nslug: x\n---\nBody")
        html.write_text(
            "<!DOCTYPE html>\n<!--\n---\ncanonical: ./x.md\n---\n-->\n<html></html>"
        )
        errors = lint_format_discernment(tmp_path)
        assert [e for e in errors if e.field == "broken_canonical"] == []

    def test_canonical_points_to_missing_md(self, tmp_path):
        html = tmp_path / "x.html"
        html.write_text(
            "<!DOCTYPE html>\n<!--\n---\ncanonical: ./ghost.md\n---\n-->\n<html></html>"
        )
        errors = lint_format_discernment(tmp_path)
        broken = [e for e in errors if e.field == "broken_canonical"]
        assert len(broken) == 1
        assert broken[0].severity == "error"

    def test_canonical_points_to_non_sibling(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        md = sub / "real.md"
        md.write_text("---\nslug: real\n---\nBody")
        html = tmp_path / "x.html"
        html.write_text(
            "<!DOCTYPE html>\n<!--\n---\ncanonical: ./real.md\n---\n-->\n<html></html>"
        )
        errors = lint_format_discernment(tmp_path)
        broken = [e for e in errors if e.field == "broken_canonical"]
        assert len(broken) == 1


class TestSubstrateViolation:
    def test_clean(self, tmp_path):
        entities = tmp_path / "entities"
        entities.mkdir()
        (entities / "concept").mkdir()
        (entities / "concept" / "foo.md").write_text("---\nslug: foo\n---\nBody")
        errors = lint_format_discernment(tmp_path)
        assert [e for e in errors if e.field == "substrate_violation"] == []

    def test_html_under_entities_errors(self, tmp_path):
        entities = tmp_path / "entities"
        entities.mkdir()
        (entities / "concept").mkdir()
        (entities / "concept" / "foo.html").write_text("<!DOCTYPE html><html></html>")
        errors = lint_format_discernment(tmp_path)
        sub = [e for e in errors if e.field == "substrate_violation"]
        assert len(sub) == 1
        assert sub[0].severity == "error"
        assert "Category A is MD-only" in sub[0].message

    def test_other_non_md_under_entities_errors(self, tmp_path):
        entities = tmp_path / "entities"
        entities.mkdir()
        (entities / "concept").mkdir()
        (entities / "concept" / "data.json").write_text("{}")
        errors = lint_format_discernment(tmp_path)
        sub = [e for e in errors if e.field == "substrate_violation"]
        assert len(sub) == 1


class TestUnregisteredCategoryC:
    def test_clean_projection_pair(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "x-synthesis.md").write_text("---\nslug: x\n---\nBody")
        (notes / "x-synthesis.html").write_text(
            "<!DOCTYPE html>\n<!--\n---\ncanonical: ./x-synthesis.md\n---\n-->\n<html></html>"
        )
        errors = lint_format_discernment(tmp_path)
        assert [e for e in errors if e.field == "unregistered_c"] == []

    def test_html_without_frontmatter_or_sibling_warns(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "rogue.html").write_text("<!DOCTYPE html><html><body>orphan</body></html>")
        errors = lint_format_discernment(tmp_path)
        unreg = [e for e in errors if e.field == "unregistered_c"]
        assert len(unreg) == 1
        assert unreg[0].severity == "warning"

    def test_html_with_frontmatter_no_sibling_ok(self, tmp_path):
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "demo.html").write_text(
            "<!DOCTYPE html>\n<!--\n---\ntype: artifact\nslug: demo\n---\n-->\n<html></html>"
        )
        errors = lint_format_discernment(tmp_path)
        unreg = [e for e in errors if e.field == "unregistered_c"]
        assert unreg == []
