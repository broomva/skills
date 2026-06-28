"""Tests for the unquoted-date frontmatter lint + auto-fix (BRO-1449).

Unquoted YAML dates (`updated: 2026-05-30`) parse to native date objects that
many tools re-serialize into a full ISO timestamp on the next edit, breaking
`YYYY-MM-DD`-expecting queries. `lint_entity_page` warns on them (non-breaking);
`fix_entity_page` mechanically quotes them, idempotently.

See research/notes/2026-06-08-frontmatter-best-practices-synthesis.md.
"""

from bookkeeping import fix_unquoted_dates, lint_entity_page

UNQUOTED = """---
id: "concept/foo"
title: "Foo"
type: concept
status: entity
created: 2026-05-30
updated: 2026-05-30
core_claim: "A precise claim about foo."
sources:
  - type: internal-doc
    url: "x"
    extraction_date: "2026-05-21"
---

Body with no wikilinks.
"""

QUOTED = (
    UNQUOTED.replace("created: 2026-05-30", 'created: "2026-05-30"')
    .replace("updated: 2026-05-30", 'updated: "2026-05-30"')
)


def _write(tmp_path, body):
    p = tmp_path / "foo.md"
    p.write_text(body)
    return p


def _date_warnings(errs):
    return [e for e in errs if "unquoted date" in e.message]


def test_unquoted_dates_warn(tmp_path):
    errs = lint_entity_page(_write(tmp_path, UNQUOTED))
    warns = _date_warnings(errs)
    assert len(warns) == 2, [e.message for e in warns]
    assert all(e.severity == "warning" for e in warns)
    assert {e.field for e in warns} == {"created", "updated"}


def test_quoted_dates_clean(tmp_path):
    errs = lint_entity_page(_write(tmp_path, QUOTED))
    assert _date_warnings(errs) == []


def test_nested_quoted_date_not_flagged(tmp_path):
    # extraction_date is already quoted — must not be flagged.
    errs = lint_entity_page(_write(tmp_path, QUOTED))
    assert not any(e.field == "extraction_date" for e in _date_warnings(errs))


def test_fix_quotes_dates_idempotently(tmp_path):
    p = _write(tmp_path, UNQUOTED)
    n_fixed = fix_unquoted_dates(p)
    assert n_fixed == 2
    text = p.read_text()
    assert 'created: "2026-05-30"' in text
    assert 'updated: "2026-05-30"' in text
    # second pass is a no-op (idempotent)
    assert fix_unquoted_dates(p) == 0
    # and the page no longer warns
    assert _date_warnings(lint_entity_page(p)) == []


def test_fix_preserves_trailing_comment(tmp_path):
    body = UNQUOTED.replace("updated: 2026-05-30", "updated: 2026-05-30  # last touch")
    p = _write(tmp_path, body)
    fix_unquoted_dates(p)
    assert 'updated: "2026-05-30"  # last touch' in p.read_text()


def test_fix_entity_page_unchanged_on_dates(tmp_path):
    # The related: fixer must NOT touch dates — that's fix_unquoted_dates' job.
    from bookkeeping import fix_entity_page
    p = _write(tmp_path, UNQUOTED)
    n_related, _ = fix_entity_page(p)
    assert n_related == 0  # no related: violations here
    assert "created: 2026-05-30" in p.read_text()  # date left untouched by related fixer


def test_fix_preserves_all_other_content(tmp_path):
    # Whole-file equality except the two quoted date lines (byte-preservation).
    p = _write(tmp_path, UNQUOTED)
    fix_unquoted_dates(p)
    expected = (
        UNQUOTED.replace("created: 2026-05-30", 'created: "2026-05-30"')
        .replace("updated: 2026-05-30", 'updated: "2026-05-30"')
    )
    assert p.read_text() == expected


def test_date_with_time_component(tmp_path):
    body = UNQUOTED.replace("updated: 2026-05-30", "updated: 2026-05-30T10:30:00Z")
    p = _write(tmp_path, body)
    warns = _date_warnings(lint_entity_page(p))
    assert any(e.field == "updated" for e in warns)
    fix_unquoted_dates(p)
    assert 'updated: "2026-05-30T10:30:00Z"' in p.read_text()


def test_no_frontmatter_is_safe(tmp_path):
    p = _write(tmp_path, "Just a body, no frontmatter at all.\n")
    assert _date_warnings(lint_entity_page(p)) == []
    assert fix_unquoted_dates(p) == 0


def test_adjacent_hash_not_a_date(tmp_path):
    # `2026-05-30#x` (no space before #) is a YAML string, not a date+comment.
    # The regex must NOT match it, so it is neither flagged nor rewritten.
    body = UNQUOTED.replace("updated: 2026-05-30", "updated: 2026-05-30#x")
    p = _write(tmp_path, body)
    assert not any(e.field == "updated" for e in _date_warnings(lint_entity_page(p)))
    assert fix_unquoted_dates(p) == 1  # only `created` (still a clean unquoted date)
    assert "updated: 2026-05-30#x" in p.read_text()  # left untouched


def test_cli_single_file_fix_quotes_dates(tmp_path):
    # Regression for the B1 bug: `lint --fix --file <p>` must quote dates, not
    # just related: entries (the warning tells users to run exactly this).
    from argparse import Namespace
    from bookkeeping import cmd_lint
    p = _write(tmp_path, UNQUOTED)
    args = Namespace(file=str(p), all=False, fix=True, verbose=False, health=False)
    cmd_lint(args)  # warnings only → no sys.exit
    text = p.read_text()
    assert 'created: "2026-05-30"' in text
    assert 'updated: "2026-05-30"' in text
