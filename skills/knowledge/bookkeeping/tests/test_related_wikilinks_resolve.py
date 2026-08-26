"""`related:` edges must be RESOLVED, not merely well-formed (BRO-2350).

The linter already did two adjacent things and not the third:

  format   `related:` entries must match ^\\[\\[.+\\]\\]$        -> ERROR
  resolve  body wikilinks must name an existing slug          -> warning
  resolve  `related:` wikilinks must name an existing slug     -> NOTHING

So a `related:` pointing at a slug nobody ever created sat green forever, while
the identical mistake one line lower in the same file was caught. Found by
writing an entity whose `related:` named `[[opsis]]` — a design doc, not an
entity — and watching `lint --file` report "No errors found".

WARNING, not error, and deliberately so: a `related:` legitimately points
outside the entity graph. Skills ([[bookkeeping]], [[checkit]]) and auto-memory
slugs ([[maestro-build-arc]]) are real referents with no entity page. Measured
over the corpus when this landed: 112 unresolved targets across 73 of 1043
files, mostly that deliberate kind. Erroring would red-line CI on 73 files this
change has nothing to do with.
"""

from pathlib import Path

from bookkeeping import lint_entity_page

PAGE = """---
slug: {slug}
type: pattern
status: candidate
core_claim: "A page written only to exercise related-edge resolution."
sources:
  - "synthetic fixture"
related:
{related}
created: "2026-08-26"
updated: "2026-08-26"
tags:
  - verification
---

## Body

No body wikilinks here on purpose, so nothing can be confused for a related edge.
"""


def _tree(root: Path, pages: dict) -> Path:
    d = root / "research" / "entities" / "pattern"
    d.mkdir(parents=True, exist_ok=True)
    for slug, targets in pages.items():
        rel = "\n".join(f'  - "[[{t}]]"' for t in targets) if targets else "  []"
        (d / f"{slug}.md").write_text(PAGE.format(slug=slug, related=rel),
                                      encoding="utf-8")
    return d


def _related_errors(path: Path) -> list:
    # `.field == "related"`, and the format rule uses the SAME field name, so
    # filter on the message too — otherwise a malformed-format error would be
    # indistinguishable from an unresolved one and either test could pass for
    # the wrong reason.
    return [e for e in lint_entity_page(path)
            if e.field == "related" and "Broken related wikilink" in e.message]


def test_an_unresolved_related_edge_is_reported(tmp_path):
    """The arm that had no coverage at all."""
    d = _tree(tmp_path, {"referrer": ["nobody-created-this"], "sibling": []})
    errors = _related_errors(d / "referrer.md")
    assert errors, "a related: edge naming a missing slug must be reported"
    assert "nobody-created-this" in errors[0].message


def test_a_resolving_related_edge_is_silent(tmp_path):
    """Polarity control. Without it, the test above is satisfied by a rule that
    reports EVERY related edge broken — which is exactly what the first draft of
    the manual probe for this change did, against a corpus it could not resolve."""
    d = _tree(tmp_path, {"referrer": ["sibling"], "sibling": []})
    assert _related_errors(d / "referrer.md") == []


def test_an_unresolved_related_edge_is_a_WARNING_not_an_error(tmp_path):
    """Severity is the whole design decision; pin it so a later tightening is a
    deliberate act rather than a drive-by."""
    d = _tree(tmp_path, {"referrer": ["nobody-created-this"], "sibling": []})
    errors = _related_errors(d / "referrer.md")
    assert errors
    assert all(e.severity == "warning" for e in errors), \
        "erroring here red-lines pre-existing files that point outside the graph"


def test_a_malformed_related_entry_does_not_abort_the_lint(tmp_path):
    """The strict writer helper RAISES on a non-canonical entry. A linter must
    report and keep going: one malformed edge must not mask the rest of the file."""
    d = _tree(tmp_path, {"referrer": ["nobody-created-this"], "sibling": []})
    p = d / "referrer.md"
    p.write_text(p.read_text().replace('  - "[[nobody-created-this]]"',
                                       '  - "not-a-wikilink"\n  - "[[still-missing]]"'),
                 encoding="utf-8")
    errors = lint_entity_page(p)          # must not raise
    assert any("still-missing" in e.message for e in errors), \
        "a valid edge after a malformed one must still be resolved"
