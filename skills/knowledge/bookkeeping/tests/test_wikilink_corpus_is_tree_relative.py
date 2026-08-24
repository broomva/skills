"""The wikilink check must resolve against the tree it is linting (BRO-2304).

`ENTITIES_DIR` is resolved once from config. The wikilink rule consulted it
while operating on a file given by an arbitrary `--file` path, so it answered
about a different tree entirely. That is not a corner case here: the workspace
mandates git worktrees for substantive work, so an agent linting an entity in
its worktree had links resolved against whatever branch the main checkout
happened to be sitting on — measured at 264 pattern entities against the
worktree's 283, on an unrelated branch.

Both directions are wrong and the quiet one is worse:

  false POSITIVE  a link to an entity present in the tree under edit is flagged
                  broken. Noisy, visible, merely annoying.
  false NEGATIVE  a link to an entity present ONLY in the configured root
                  PASSES, then breaks the moment the branch merges. Silent, and
                  it defeats the check — a rule reporting clean about a corpus
                  that is not the one being changed.

Nothing covered the second arm, which is why it survived.
"""

from pathlib import Path

import bookkeeping
from bookkeeping import entities_dir_for, existing_entity_slugs, lint_entity_page

PAGE = """---
slug: {slug}
type: pattern
status: candidate
core_claim: "A page written only to exercise the wikilink corpus resolution rule."
sources:
  - "synthetic fixture"
created: "2026-08-24"
updated: "2026-08-24"
tags:
  - verification
---

## Body

This links to [[{target}]] and nothing else.
"""


def _tree(root: Path, pages: dict) -> Path:
    """A minimal research/entities/pattern/ tree holding `pages`."""
    d = root / "research" / "entities" / "pattern"
    d.mkdir(parents=True, exist_ok=True)
    for slug, target in pages.items():
        (d / f"{slug}.md").write_text(PAGE.format(slug=slug, target=target),
                                      encoding="utf-8")
    return d


def _wikilink_errors(path: Path) -> list:
    # `.field`, not `.rule`. The first draft of this helper used `.rule`, which
    # does not exist — and the two tests asserting an EMPTY result still passed,
    # because a comprehension over an empty list never evaluates its condition.
    # Green for the wrong reason, in the helper written to test for exactly that.
    return [e for e in lint_entity_page(path) if e.field == "wikilink"]


def test_a_link_to_a_sibling_in_the_same_tree_resolves(tmp_path):
    """The false-POSITIVE arm: the target is right there."""
    d = _tree(tmp_path / "A", {"referrer": "the-target", "the-target": "referrer"})
    assert _wikilink_errors(d / "referrer.md") == []


def test_a_link_to_an_entity_only_in_another_tree_is_broken(tmp_path, monkeypatch):
    """The false-NEGATIVE arm, and the one that had no coverage.

    `only-over-there` exists in tree B, which is what ENTITIES_DIR points at.
    The page under lint is in tree A. Before this fix the rule consulted B and
    reported clean, so a link that breaks on merge passed the gate.
    """
    a = _tree(tmp_path / "A", {"referrer": "only-over-there"})
    b = _tree(tmp_path / "B", {"only-over-there": "only-over-there"})
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", b.parent, raising=False)

    errors = _wikilink_errors(a / "referrer.md")
    assert errors, "a link to an entity absent from this tree must be reported"
    assert "only-over-there" in errors[0].message


def test_the_configured_root_does_not_rescue_a_missing_target(tmp_path, monkeypatch):
    """Polarity control for the test above: with the SAME configured root, a
    target that is present in tree A resolves. Without this, the previous test
    is satisfied by a rule that reports every link broken."""
    a = _tree(tmp_path / "A", {"referrer": "here-too", "here-too": "referrer"})
    b = _tree(tmp_path / "B", {"unrelated": "unrelated"})
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", b.parent, raising=False)

    assert _wikilink_errors(a / "referrer.md") == []


class TestEntitiesDirFor:
    def test_it_finds_the_enclosing_corpus(self, tmp_path):
        d = _tree(tmp_path / "A", {"x": "x"})
        assert entities_dir_for(d / "x.md") == d.parent

    def test_it_falls_back_to_the_configured_root_outside_any_corpus(
        self, tmp_path, monkeypatch
    ):
        """A path with no `research/entities/` ancestor has no tree to prefer,
        so the configured root is the only answer available."""
        stray = tmp_path / "loose" / "page.md"
        stray.parent.mkdir(parents=True)
        stray.write_text(PAGE.format(slug="page", target="whatever"), encoding="utf-8")
        monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", tmp_path / "configured",
                            raising=False)
        assert entities_dir_for(stray) == tmp_path / "configured"

    def test_it_is_not_confused_by_a_bare_entities_dir(self, tmp_path):
        """`entities/` alone is not a corpus — the marker is `research/entities/`.
        Matching on the leaf name would bind to any directory called entities."""
        d = tmp_path / "somewhere" / "entities" / "pattern"
        d.mkdir(parents=True)
        page = d / "x.md"
        page.write_text(PAGE.format(slug="x", target="y"), encoding="utf-8")
        assert entities_dir_for(page) == bookkeeping.ENTITIES_DIR


def test_existing_entity_slugs_defaults_to_the_configured_root(tmp_path, monkeypatch):
    """Backward compatibility: the no-argument form is unchanged, because six
    other call sites still use it."""
    b = _tree(tmp_path / "B", {"only-over-there": "x"})
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", b.parent, raising=False)
    assert "only-over-there" in existing_entity_slugs()
