"""Tests for spec_check.

Every check gets BOTH a positive control (a document that must trip it) and a
negative control (a document that must not). A check with only a negative
control is indistinguishable from a check that never fires — which is the state
C4 was in when this suite was written: it found nothing across 105 real
documents, and nothing is what a dead regex also finds.

Fixtures are built from the product of the two entry surfaces (markdown, HTML)
wherever the parse is what is under test, because a guard on one of two doors
guards nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import spec_check as sc  # noqa: E402


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def run(tmp_path: Path, body: str, name: str = "doc.md", **kw) -> sc.Report:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    kw.setdefault("profile", "spec")
    kw.setdefault("strict", False)
    kw.setdefault("check_links", False)
    return sc.check(p, **kw)


def checks(rep: sc.Report) -> set[str]:
    return {f.check for f in rep.findings}


def fails(rep: sc.Report) -> set[str]:
    return {f.check for f in rep.findings if f.severity == "fail"}


# A document that clears every required check. Each positive-control test
# mutates exactly one thing away from this baseline, so a finding can only be
# attributed to that mutation.
GOOD = """# Widget Cache

Status: accepted
Reversal cost: one-way door — the storage engine is not swappable after launch.

## Objective
Cut median page load by caching the hot 3% of rows.

## Background
Page loads grew from 100ms to 600ms over three years. Investigation showed that
database lookups account for roughly eighty percent of that time, and that the
same three percent of rows serve almost every request. That access pattern is
what makes a cache worth building here rather than sharding the database or
buying a larger instance, both of which cost more and help less.

## Goals
- Increase user-perceived responsiveness.

## Non-goals
- A general-purpose reusable cache. This one makes app-specific assumptions.
- Location-aware caching. Useful later, out of scope for v1.

## Design
An in-process LRU in front of Postgres, behind a Store interface. We chose
in-process rather than a separate service at the cost of a cold cache on deploy.
The interface is the seam: the server holds a Store, the cache implements Store
and wraps the real database, and every read that misses forwards through. That
keeps the blast radius of this change to one struct field and one constructor,
which is why the wrapper shape was preferred over threading a cache handle down
through the call sites by hand.

## Alternatives considered
- Redis: an extra process to operate, and the network hop eats the win.
- Firestore: durable, but the platform lock-in was not worth it.

## Drawbacks
The cache doubles resident memory and we give up cross-process sharing.

## Acceptance criteria
- p50 latency <= 200ms.
- `make check` passes.

## Open issues
- RAM sizing. Proposed solution: 128GB untested. Next step: ask the tech lead.
"""


def test_baseline_document_passes(tmp_path):
    rep = run(tmp_path, GOOD)
    assert fails(rep) == set(), [f.message for f in rep.findings]


# --------------------------------------------------------------------------
# parse: both entry surfaces
# --------------------------------------------------------------------------

MD_EQUIV = "# T\n\n## Design\nbody one\n\n### Nested\nbody two\n"
HTML_EQUIV = (
    "<html><body><h1>T</h1><h2>Design</h2><p>body one</p>"
    "<h3>Nested</h3><p>body two</p></body></html>"
)


@pytest.mark.parametrize("raw,is_html", [(MD_EQUIV, False), (HTML_EQUIV, True)])
def test_both_surfaces_parse_the_same_sections(raw, is_html):
    sections, _ = sc.parse(raw, is_html)
    assert [s.title for s in sections] == ["T", "Design", "Nested"]
    assert [s.level for s in sections] == [1, 2, 3]


@pytest.mark.parametrize("raw,is_html", [(MD_EQUIV, False), (HTML_EQUIV, True)])
def test_subtree_spans_nested_sections(raw, is_html):
    """Regression: the first cut read `body`, so a section whose content sat in
    a subsection scored as empty. The Little Moments SLOs live under `### Latency`
    beneath `## Service level objectives`, and were read as saying nothing."""
    sections, _ = sc.parse(raw, is_html)
    sc.attach_subtrees(sections)
    design = next(s for s in sections if s.title == "Design")
    assert "body one" in design.subtree
    assert "body two" in design.subtree, "subtree must include nested sections"
    assert "body two" not in design.body, "body must remain the section's own"


def test_html_slos_in_subsections_are_measurable(tmp_path):
    """The exact shape that produced the false C8 on the gold-standard doc."""
    html = (
        "<h1>D</h1><p>Status: accepted</p><h2>Objective</h2><p>x</p>"
        "<h2>Design</h2><p>we chose A instead of B</p>"
        "<h2>Non-goals</h2><ul><li>No support for albums</li></ul>"
        "<h2>Alternatives considered</h2><ul><li>B: too slow</li>"
        "<li>C: lock-in</li></ul>"
        "<h2>Service level objectives</h2><h3>Latency</h3><p>p50 &lt;= 200ms</p>"
    )
    rep = run(tmp_path, html, name="d.html")
    assert "C8-unmeasurable-acceptance" not in checks(rep)


# --------------------------------------------------------------------------
# C1 required vs recommended
# --------------------------------------------------------------------------

def test_c1_missing_required_fails(tmp_path):
    rep = run(tmp_path, GOOD.replace("## Alternatives considered", "## Misc"))
    assert "C1-missing-section" in fails(rep)


def test_c1_missing_recommended_only_warns(tmp_path):
    rep = run(tmp_path, GOOD.replace("## Drawbacks", "## Zzz"))
    assert "C1-missing-section" not in fails(rep)
    assert "C1-missing-recommended" in checks(rep)


def test_c1_synonym_headings_satisfy_the_class(tmp_path):
    """A corpus does not use canonical names; 'Missing features' is a non-goal."""
    rep = run(tmp_path, GOOD.replace("## Non-goals", "## Missing features"))
    assert "C1-missing-section" not in fails(rep)


# --------------------------------------------------------------------------
# C2 status / supersession (NYGARD)
# --------------------------------------------------------------------------

def test_c2_positive_no_status(tmp_path):
    rep = run(tmp_path, GOOD.replace("Status: accepted\n", ""))
    assert "C2-no-status" in fails(rep)


def test_c2_negative_status_present(tmp_path):
    assert "C2-no-status" not in checks(run(tmp_path, GOOD))


def test_c2_superseded_without_pointer_fails(tmp_path):
    rep = run(tmp_path, GOOD.replace("Status: accepted", "Status: superseded"))
    assert "C2-dangling-supersede" in fails(rep)


def test_c2_superseded_with_pointer_passes(tmp_path):
    rep = run(tmp_path, GOOD.replace(
        "Status: accepted", "Status: superseded by docs/adrs/2026-02-01-next.md"))
    assert "C2-dangling-supersede" not in checks(rep)


def test_c2_unknown_status_warns_not_fails(tmp_path):
    rep = run(tmp_path, GOOD.replace("Status: accepted", "Status: marinating"))
    assert "C2-bad-status" in checks(rep)
    assert "C2-bad-status" not in fails(rep)


# --------------------------------------------------------------------------
# C3 reversal cost (LYNCH)
# --------------------------------------------------------------------------

def test_c3_positive_missing_reversal_cost(tmp_path):
    body = GOOD.replace(
        "Reversal cost: one-way door — the storage engine is not swappable "
        "after launch.\n", "")
    assert "C3-no-reversal-cost" in checks(run(tmp_path, body))


def test_c3_strict_promotes_to_failure(tmp_path):
    body = GOOD.replace(
        "Reversal cost: one-way door — the storage engine is not swappable "
        "after launch.\n", "")
    assert "C3-no-reversal-cost" in fails(run(tmp_path, body, strict=True))
    assert "C3-no-reversal-cost" not in fails(run(tmp_path, body, strict=False))


def test_c3_negative_graded_reversal_cost(tmp_path):
    assert "C3-no-reversal-cost" not in checks(run(tmp_path, GOOD))
    assert "C3-vague-reversal-cost" not in checks(run(tmp_path, GOOD))


def test_c3_ungraded_reversal_cost_warns(tmp_path):
    body = GOOD.replace("Reversal cost: one-way door — the storage engine is "
                        "not swappable after launch.",
                        "Reversal cost: considered")
    assert "C3-vague-reversal-cost" in checks(run(tmp_path, body))


# --------------------------------------------------------------------------
# C4 negated goals (GOOGLE) — the check that found nothing in 105 real docs
# --------------------------------------------------------------------------

@pytest.mark.parametrize("item", [
    "The system shouldn't crash",
    "Must not lose data",
    "Will not be slow",
    "Never blocks the main thread",
])
def test_c4_positive_negated_requirement_is_flagged(tmp_path, item):
    """POSITIVE CONTROL. Without these the rule's silence proves nothing."""
    body = GOOD.replace(
        "- A general-purpose reusable cache. This one makes app-specific "
        "assumptions.", f"- {item}")
    assert "C4-negated-goal" in checks(run(tmp_path, body)), item


@pytest.mark.parametrize("item", [
    "No support for albums",
    "Location-aware caching",
    "A general-purpose reusable cache",
    "No calendar view",
    "Not a replacement for the audit log",
])
def test_c4_negative_real_non_goal_is_not_flagged(tmp_path, item):
    """A non-goal may be phrased negatively as long as it names the declined
    capability — every one of these is lifted from a real design doc."""
    body = GOOD.replace(
        "- A general-purpose reusable cache. This one makes app-specific "
        "assumptions.", f"- {item}")
    assert "C4-negated-goal" not in checks(run(tmp_path, body)), item


# --------------------------------------------------------------------------
# C5 alternatives (RUST / GOOGLE / LYNCH)
# --------------------------------------------------------------------------

def test_c5_positive_single_alternative(tmp_path):
    body = GOOD.replace(
        "- Redis: an extra process to operate, and the network hop eats the win.\n"
        "- Firestore: durable, but the platform lock-in was not worth it.\n",
        "- Redis: an extra process to operate.\n")
    assert "C5-thin-alternatives" in fails(run(tmp_path, body))


def test_c5_positive_no_rejection_reason(tmp_path):
    body = GOOD.replace(
        "- Redis: an extra process to operate, and the network hop eats the win.\n"
        "- Firestore: durable, but the platform lock-in was not worth it.\n",
        "- Redis.\n- Firestore.\n- Memcached.\n")
    assert "C5-no-rejection-reason" in fails(run(tmp_path, body))


def test_c5_negative_two_alternatives_with_reasons(tmp_path):
    assert not {"C5-thin-alternatives", "C5-no-rejection-reason"} & checks(
        run(tmp_path, GOOD))


def test_c5_pro_con_idiom_counts_as_a_reason(tmp_path):
    """The Little Moments doc rejects seven SMTP vendors entirely in Pro/Con
    bullets; reading that as 'no stated reason' was a false positive."""
    body = GOOD.replace(
        "- Redis: an extra process to operate, and the network hop eats the win.\n"
        "- Firestore: durable, but the platform lock-in was not worth it.\n",
        "- Redis\n  - Pro: fast\n  - Con: another process to operate\n"
        "- Firestore\n  - Pro: durable\n  - Con: platform lock-in\n")
    assert "C5-no-rejection-reason" not in checks(run(tmp_path, body))


def test_c5_subheading_alternatives_are_counted(tmp_path):
    body = GOOD.replace(
        "## Alternatives considered\n"
        "- Redis: an extra process to operate, and the network hop eats the win.\n"
        "- Firestore: durable, but the platform lock-in was not worth it.\n",
        "## Alternatives considered\n### Redis\nAn extra process; rejected.\n"
        "### Firestore\nDurable but lock-in; rejected.\n")
    assert not {"C5-thin-alternatives", "C5-no-rejection-reason"} & checks(
        run(tmp_path, body))


# --------------------------------------------------------------------------
# C6 drawbacks (RUST / NYGARD)
# --------------------------------------------------------------------------

def test_c6_positive_drawbacks_section_states_no_cost(tmp_path):
    body = GOOD.replace(
        "The cache doubles resident memory and we give up cross-process sharing.",
        "This design is clean and the team likes it.")
    assert "C6-drawbacks-without-cost" in fails(run(tmp_path, body))


def test_c6_negative_drawbacks_state_a_cost(tmp_path):
    assert "C6-drawbacks-without-cost" not in checks(run(tmp_path, GOOD))


# --------------------------------------------------------------------------
# C7 open questions (LYNCH)
# --------------------------------------------------------------------------

def test_c7_positive_open_question_without_next_step(tmp_path):
    body = GOOD.replace(
        "- RAM sizing. Proposed solution: 128GB untested. Next step: ask the "
        "tech lead.", "- How much RAM should the cache get?")
    assert "C7-open-question-without-next-step" in checks(run(tmp_path, body))


def test_c7_negative_next_step_present(tmp_path):
    assert "C7-open-question-without-next-step" not in checks(run(tmp_path, GOOD))


def test_c7_none_is_not_a_missing_next_step(tmp_path):
    body = GOOD.replace(
        "- RAM sizing. Proposed solution: 128GB untested. Next step: ask the "
        "tech lead.", "- None")
    assert "C7-open-question-without-next-step" not in checks(run(tmp_path, body))


# --------------------------------------------------------------------------
# C8 measurable acceptance (LYNCH SLOs)
# --------------------------------------------------------------------------

def test_c8_positive_adjectives_only(tmp_path):
    body = GOOD.replace(
        "- p50 latency <= 200ms.\n- `make check` passes.",
        "- The system should feel fast.\n- Users should be happy.")
    assert "C8-unmeasurable-acceptance" in fails(run(tmp_path, body))


@pytest.mark.parametrize("criterion", [
    "- p50 latency <= 200ms.",
    "- 99.9% uptime.",
    "- `pytest tests/` is green.",
    "- Cold start under 3 s.",
])
def test_c8_negative_concrete_criteria(tmp_path, criterion):
    body = GOOD.replace("- p50 latency <= 200ms.\n- `make check` passes.",
                        criterion)
    assert "C8-unmeasurable-acceptance" not in checks(run(tmp_path, body))


# --------------------------------------------------------------------------
# C9 implementation-manual detector (GOOGLE)
# --------------------------------------------------------------------------

def test_c9_positive_no_tradeoff_language_anywhere(tmp_path):
    body = (
        "# Build It\n\nStatus: accepted\n\n## Objective\nShip the thing.\n\n"
        "## Design\n" + ("We will add a module and wire the handler. " * 60) +
        "\n\n## Non-goals\n- Mobile support\n\n"
        "## Alternatives considered\n- Nothing; skipped.\n- Later; skipped.\n"
    )
    assert "C9-implementation-manual" in fails(run(tmp_path, body))


def test_c9_negative_short_docs_are_exempt(tmp_path):
    """Below the word floor the signal is absence-of-text, not absence-of-thought."""
    body = "# Tiny\n\nStatus: draft\n\n## Design\nAdd a flag.\n"
    assert "C9-implementation-manual" not in checks(run(tmp_path, body))


def test_c9_negative_tradeoff_language_present(tmp_path):
    assert "C9-implementation-manual" not in checks(run(tmp_path, GOOD))


# --------------------------------------------------------------------------
# C10 size (GOOGLE 10-20 pages)
# --------------------------------------------------------------------------

def test_c10_positive_oversized_warns(tmp_path):
    body = GOOD + "\n\n## Appendix\n" + ("filler word " * 11000)
    rep = run(tmp_path, body)
    assert "C10-oversized" in checks(rep)
    assert "C10-oversized" not in fails(rep), "size is advisory, never blocking"


def test_c10_positive_stub_warns(tmp_path):
    rep = run(tmp_path, "# S\n\nStatus: draft\n\n## Design\nA flag.\n")
    assert "C10-stub" in checks(rep)


def test_c10_negative_right_sized(tmp_path):
    assert not {"C10-oversized", "C10-stub"} & checks(run(tmp_path, GOOD))


# --------------------------------------------------------------------------
# profile inference
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path,words,expected", [
    ("docs/adrs/2026-01-01-adr-cache.md", 5000, "adr"),
    ("docs/plans/2026-01-01-rollout.html", 5000, "plan"),
    ("docs/rfd/0001-process.md", 5000, "rfd"),
    ("docs/specs/2026-01-01-cache.html", 5000, "spec"),
    ("docs/specs/2026-01-01-cache.html", 300, "note"),
])
def test_profile_inference(path, words, expected):
    assert sc.infer_profile(Path(path), words) == expected


def test_every_profile_names_only_known_classes():
    for name, spec in sc.PROFILES.items():
        for cls in spec["required"] + spec["recommended"]:
            assert cls in sc.SECTION_CLASSES, f"{name} names unknown class {cls}"


def test_required_and_recommended_are_disjoint():
    for name, spec in sc.PROFILES.items():
        overlap = set(spec["required"]) & set(spec["recommended"])
        assert not overlap, f"{name}: {overlap} is both required and recommended"


# --------------------------------------------------------------------------
# CLI contract
# --------------------------------------------------------------------------

def test_cli_exit_zero_on_clean_doc(tmp_path, capsys):
    p = tmp_path / "ok.md"
    p.write_text(GOOD, encoding="utf-8")
    assert sc.main([str(p), "--profile", "spec"]) == 0


def test_cli_exit_one_on_failure(tmp_path, capsys):
    p = tmp_path / "bad.md"
    p.write_text("# X\n\n## Design\nnothing\n", encoding="utf-8")
    assert sc.main([str(p), "--profile", "spec"]) == 1


def test_cli_exit_two_on_missing_file(tmp_path):
    assert sc.main([str(tmp_path / "nope.md")]) == 2


def test_cli_json_is_parseable(tmp_path, capsys):
    import json
    p = tmp_path / "ok.md"
    p.write_text(GOOD, encoding="utf-8")
    sc.main([str(p), "--profile", "spec", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["profile"] == "spec"
    assert "findings" in payload[0]
