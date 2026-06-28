"""Tests for bookkeeping render subcommand."""
import pytest
from pathlib import Path
from render import render_markdown_to_html


class TestRenderCore:
    def test_basic_md_to_html(self):
        md = "---\ntitle: Hello\n---\n# Heading\n\nParagraph."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        assert "<!DOCTYPE html>" in html
        assert "<h1>Heading</h1>" in html
        assert "<p>Paragraph.</p>" in html
        assert "<style>" in html

    def test_title_from_frontmatter(self):
        md = "---\ntitle: Custom Title\n---\nBody."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        assert "<title>Custom Title</title>" in html

    def test_title_fallback_to_slug(self):
        md = "---\nslug: my-slug\n---\nBody."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        assert "<title>my-slug</title>" in html

    def test_canonical_link_present(self):
        md = "Body."
        html = render_markdown_to_html(md, source_path=Path("research/notes/x.md"))
        assert 'rel="canonical"' in html
        assert "x.md" in html

    def test_frontmatter_in_comment(self):
        md = "---\ntype: synthesis\nscore: 7\n---\nBody."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        assert "<!--" in html
        assert "type: synthesis" in html
        assert "score: 7" in html
        assert "canonical:" in html  # injected

    def test_determinism(self):
        md = "---\ntitle: T\n---\n# H\n\nP."
        h1 = render_markdown_to_html(md, source_path=Path("note.md"))
        h2 = render_markdown_to_html(md, source_path=Path("note.md"))
        h3 = render_markdown_to_html(md, source_path=Path("note.md"))
        assert h1 == h2 == h3


class TestRenderWikilinkRewrite:
    def test_md_target_default(self):
        md = "See [[concept/foo]] for context."
        html = render_markdown_to_html(md, source_path=Path("research/notes/x.md"))
        assert 'href="../concept/foo.md"' in html
        assert 'data-relation="references"' in html
        assert ">foo<" in html  # display text is the leaf segment

    def test_html_target_with_flag(self):
        md = "See [[concept/foo]]."
        html = render_markdown_to_html(
            md, source_path=Path("research/notes/x.md"), link_html=True
        )
        assert 'href="../concept/foo.html"' in html
        assert "concept/foo.md" not in html

    def test_pipe_alias_used_as_display(self):
        md = "See [[concept/foo|Foo Concept]]."
        html = render_markdown_to_html(md, source_path=Path("research/notes/x.md"))
        assert ">Foo Concept<" in html
        assert 'href="../concept/foo.md"' in html

    def test_bare_slug_no_path(self):
        # No slash → treated as a same-folder reference
        md = "See [[foo]]."
        html = render_markdown_to_html(md, source_path=Path("research/notes/x.md"))
        assert 'href="./foo.md"' in html

    # --- Code-span safety (I2) ---

    def test_wikilink_in_fenced_code_block_preserved(self):
        md = "```\n[[concept/foo]]\n```"
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        # The literal [[concept/foo]] appears in the rendered <pre>/<code>
        # mistune escapes < > in code, but the wikilink syntax itself stays literal
        assert "[[concept/foo]]" in html
        # No anchor was emitted
        assert 'data-relation="references"' not in html or \
            "concept/foo" not in html.replace("[[concept/foo]]", "")

    def test_wikilink_in_inline_code_preserved(self):
        md = "Use `[[concept/foo]]` syntax."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        # The literal [[concept/foo]] appears inside <code>
        assert "[[concept/foo]]" in html

    def test_wikilink_outside_code_still_rewrites(self):
        # Sanity: a wikilink inside ` and one outside — only the outer rewrites
        md = "Use `[[concept/foo]]` like [[pattern/bar]]."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        assert "[[concept/foo]]" in html  # inline-code preserved
        assert 'href="../pattern/bar.md"' in html  # outside-code rewritten

    # --- Malformed-wikilink fallback (I3) ---

    def test_empty_target_falls_back_to_literal(self):
        md = "Malformed: [[]] here."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        assert "[[]]" in html  # left literal
        assert 'data-relation="references"' not in html

    def test_trailing_slash_target_falls_back_to_literal(self):
        md = "Malformed: [[concept/foo/]] here."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        assert "[[concept/foo/]]" in html  # left literal
        assert 'href="../concept/foo/.md"' not in html

    def test_slash_only_target_falls_back_to_literal(self):
        md = "Malformed: [[/]] here."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        assert "[[/]]" in html  # left literal


class TestRenderXSSEscaping:
    def test_malicious_title_escaped(self):
        md = "---\ntitle: '<script>alert(1)</script>'\n---\nBody."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        # The literal <script> tag must not appear in the rendered <title> location
        assert "<title>&lt;script&gt;alert(1)&lt;/script&gt;</title>" in html
        # The raw <script>...</script> may legitimately appear inside the
        # leading HTML comment (YAML frontmatter block) where it cannot
        # execute. The active document body must not contain it.
        body_start = html.index("<body>")
        assert "<script>alert(1)</script>" not in html[body_start:]
        # And the <head> region (after frontmatter comment) must not contain it.
        head_start = html.index("<head>")
        assert "<script>alert(1)</script>" not in html[head_start:]

    def test_malicious_wikilink_alias_escaped(self):
        md = "See [[concept/foo|</a><script>alert(1)</script>]]."
        html = render_markdown_to_html(md, source_path=Path("note.md"))
        # Alias text is escaped — angle brackets become entities
        assert "&lt;/a&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "<script>alert(1)</script>" not in html

    def test_canonical_href_with_quote_escaped(self):
        # Source path with a " character in the name should not break out of href=""
        md = "Body."
        html = render_markdown_to_html(md, source_path=Path('weird"name.md'))
        # Quote becomes &quot;
        assert 'href="weird&quot;name.md"' in html or 'href="./weird&quot;name.md"' in html
