"""Tests for wikilink extraction (MD and HTML)."""
import pytest
from bookkeeping import extract_wikilinks_md, extract_wikilinks_html


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
