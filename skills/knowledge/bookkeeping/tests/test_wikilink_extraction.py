"""Tests for wikilink extraction (MD and HTML) and resolution (BRO-1976)."""
import pytest
from bookkeeping import (
    extract_wikilinks_md,
    extract_wikilinks_html,
    wikilink_slug,
    _catalog_extract_links,
)


class TestExtractWikilinksMD:
    def test_single_wikilink(self):
        text = "See [[concept/foo]] for details."
        assert extract_wikilinks_md(text) == [("concept/foo", "references")]

    def test_multiple_wikilinks(self):
        text = "See [[concept/foo]] and [[pattern/bar]]."
        assert extract_wikilinks_md(text) == [
            ("concept/foo", "references"),
            ("pattern/bar", "references"),
        ]

    def test_pipe_alias_stripped(self):
        text = "See [[concept/foo|Foo Concept]]."
        assert extract_wikilinks_md(text) == [("concept/foo", "references")]

    def test_skip_html_comments(self):
        text = "Before <!-- [[ignored/link]] --> after [[real/link]]."
        assert extract_wikilinks_md(text) == [("real/link", "references")]

    def test_empty_text(self):
        assert extract_wikilinks_md("") == []

    def test_no_wikilinks(self):
        assert extract_wikilinks_md("Just plain prose.") == []


class TestExtractWikilinksHTML:
    def test_single_typed_link(self):
        html = '<p>See <a href="../concept/foo.md" data-relation="references">foo</a></p>'
        assert extract_wikilinks_html(html) == [("concept/foo", "references")]

    def test_multiple_typed_links_different_edges(self):
        html = '''
        <a href="../concept/foo.md" data-relation="extends">foo</a>
        <a href="../pattern/bar.md" data-relation="contradicts">bar</a>
        '''
        assert extract_wikilinks_html(html) == [
            ("concept/foo", "extends"),
            ("pattern/bar", "contradicts"),
        ]

    def test_html_target_paths(self):
        html = '<a href="../concept/foo.html" data-relation="references">foo</a>'
        assert extract_wikilinks_html(html) == [("concept/foo", "references")]

    def test_skip_untyped_anchors(self):
        html = '<a href="https://example.com">external</a><a href="../concept/foo.md" data-relation="references">foo</a>'
        assert extract_wikilinks_html(html) == [("concept/foo", "references")]

    def test_absolute_href_ignored(self):
        html = '<a href="https://example.com" data-relation="references">link</a>'
        assert extract_wikilinks_html(html) == []

    def test_empty_text(self):
        assert extract_wikilinks_html("") == []

    def test_single_quoted_attrs(self):
        """Renderer-agnostic: accept both " and ' as attribute delimiters."""
        html = "<a href='../concept/foo.md' data-relation='references'>foo</a>"
        assert extract_wikilinks_html(html) == [("concept/foo", "references")]

    def test_mixed_quote_styles(self):
        """One attr double-quoted, the other single-quoted — both work."""
        html = '<a href="../concept/foo.md" data-relation=\'references\'>foo</a>'
        assert extract_wikilinks_html(html) == [("concept/foo", "references")]


class TestWikilinkSlug:
    """BRO-1976: type-qualified [[type/slug]] links must resolve to the bare stem
    (they were miscounted as dangling because slugify() drops the '/')."""

    def test_type_qualified_strips_qualifier(self):
        assert wikilink_slug("concept/knowledge-graph") == "knowledge-graph"

    def test_bare_slug_unchanged(self):
        assert wikilink_slug("bookkeeping") == "bookkeeping"

    def test_qualifier_plus_alias(self):
        assert wikilink_slug("concept/foo|Display Text") == "foo"

    def test_qualifier_plus_anchor(self):
        assert wikilink_slug("concept/foo#a-heading") == "foo"

    def test_slugify_still_applies(self):
        assert wikilink_slug("Foo Bar") == "foo-bar"

    def test_regression_slugify_alone_would_break(self):
        """The exact bug: slugify() alone collapses the '/' into a phantom slug."""
        from bookkeeping import slugify
        assert slugify("concept/knowledge-graph") == "conceptknowledge-graph"  # the bug
        assert wikilink_slug("concept/knowledge-graph") == "knowledge-graph"     # the fix


class TestCatalogExtractLinksTypeQualifier:
    """BRO-1976: catalog edge extraction must also strip the type qualifier so
    edges connect to their node instead of dangling."""

    def test_type_qualified_resolves_to_stem(self):
        assert _catalog_extract_links("[[concept/foo]] and [[bar]]") == ["foo", "bar"]

    def test_alias_anchor_and_qualifier_all_stripped(self):
        assert _catalog_extract_links("[[tool/x|X]] [[pattern/y#z]]") == ["x", "y"]


class TestRemediationPlanTypeQualifier:
    """BRO-1976 site 4: build_remediation_plan groups broken wikilinks by the
    bare stem, so type-qualified refs to the same missing entity count as ONE
    entity-to-create (not one per type qualifier)."""

    def test_type_qualified_broken_links_group_by_stem(self):
        from bookkeeping import build_remediation_plan, LintError
        errs = [
            LintError("a.md", "wikilink",
                      "Broken wikilink: [[concept/new-thing]] (slug 'conceptnew-thing' not found)", "warning"),
            LintError("b.md", "wikilink",
                      "Broken wikilink: [[tool/new-thing]] (slug 'toolnew-thing' not found)", "warning"),
            LintError("c.md", "wikilink",
                      "Broken wikilink: [[new-thing]] (slug 'new-thing' not found)", "warning"),
        ]
        plan = build_remediation_plan(errs)
        step = next(s for s in plan if s["category"] == "broken-wikilink-targets")
        assert step["count"] == 1, step        # one missing entity, not three
        assert step["leverage"] == 3           # unblocks 3 dangling refs
        assert "new-thing" in step["detail"] and "conceptnew-thing" not in step["detail"]
