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
    assert "C6-drawbacks-without-cost" in checks(run(tmp_path, body))
    # required on adr -> blocking; merely recommended on spec -> advisory
    assert "C6-drawbacks-without-cost" in fails(run(tmp_path, body, profile="adr"))
    assert "C6-drawbacks-without-cost" not in fails(run(tmp_path, body))


def test_r1_b4_gate_is_monotone_in_honesty(tmp_path):
    """Adding a real section must never flip a passing doc to failing. When a
    vacuous section hard-failed and an ABSENT one only warned, the gate rewarded
    deleting drawbacks and acceptance — the opposite of what it exists to do."""
    without = GOOD.replace(
        "\n## Acceptance criteria\n- p50 latency <= 200ms.\n- `make check` passes.\n",
        "\n")
    with_vacuous = without.replace(
        "\n## Open issues",
        "\n## Acceptance criteria\n- Billing should feel responsive.\n\n## Open issues")
    assert not fails(run(tmp_path, without))
    assert not fails(run(tmp_path, with_vacuous)), (
        "adding an honest-but-unmeasurable section must not be worse than "
        "omitting it entirely")
    assert "C8-unmeasurable-acceptance" in checks(run(tmp_path, with_vacuous))


def test_r1_nb2_a_combined_heading_satisfies_both_classes(tmp_path):
    """'Alternatives and drawbacks' scored as one class, dropping the other and
    leaving renaming as the only remedy — which SKILL.md calls gaming."""
    body = GOOD.replace("## Drawbacks", "## Alternatives and drawbacks")
    rep = run(tmp_path, body, profile="adr")
    assert "drawbacks" in rep.sections and "alternatives" in rep.sections


def test_r1_nb3_validation_is_not_an_acceptance_section(tmp_path):
    """A spec section about INPUT validation used to trigger a hard C8."""
    body = GOOD.replace("## Acceptance criteria", "## Validation")
    assert "acceptance" not in run(tmp_path, body).sections


def test_r1_b5_status_must_be_a_field_not_prose(tmp_path):
    """'HTTP status: 200 is returned on success.' discharged C2's only blocking
    arm."""
    body = GOOD.replace(
        "Status: accepted", "HTTP status: 200 is returned on success.")
    assert "C2-no-status" in fails(run(tmp_path, body))


def test_r1_b5_make_spec_meta_line_is_still_readable(tmp_path):
    """make-spec emits one meta LINE with middot separators. Pure line-anchoring
    would have made this checker unable to read its own composition partner."""
    body = GOOD.replace(
        "Status: accepted",
        "Author: agent · Generated: 2026-09-16 · Status: accepted")
    assert "C2-no-status" not in checks(run(tmp_path, body))


def test_r1_b6_a_literal_door_is_not_a_reversal_declaration(tmp_path):
    """REVERSAL_LINE matched the bare word 'door', so a sentence about a door
    satisfied the one check --strict promotes to blocking."""
    body = GOOD.replace(
        "Reversal cost: one-way door — the storage engine is not swappable "
        "after launch.", "The door was left open.")
    assert "C3-no-reversal-cost" in fails(run(tmp_path, body, strict=True))


def test_r1_b6_an_inline_door_phrase_still_counts(tmp_path):
    body = GOOD.replace(
        "Reversal cost: one-way door — the storage engine is not swappable "
        "after launch.",
        "Picking the storage engine is a one-way door for this service.")
    assert "C3-no-reversal-cost" not in checks(run(tmp_path, body))


def test_r1_b10_html_comment_front_matter_survives(tmp_path):
    """The workspace's HTML docs carry YAML front matter in a leading HTML
    comment; the catch-all tag strip erased it, and 41 of 67 real documents were
    reported status-less as a result."""
    body = ('<!DOCTYPE html>\n<!--\n---\ntitle: T\nstatus: draft\n---\n-->\n'
            '<h1>T</h1><h2>Design</h2><p>we chose A instead of B</p>')
    assert "C2-no-status" not in checks(run(tmp_path, body, name="d.html",
                                            profile="note"))


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
    assert "C8-unmeasurable-acceptance" in checks(run(tmp_path, body))
    # required on plan (a plan with no definition of done is a wish list)
    assert "C8-unmeasurable-acceptance" in fails(run(tmp_path, body, profile="plan"))


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

@pytest.mark.parametrize("path,expected", [
    ("docs/adrs/2026-01-01-adr-cache.md", "adr"),
    ("docs/plans/2026-01-01-rollout.html", "plan"),
    ("docs/rfd/0001-process.md", "rfd"),
    ("docs/specs/2026-01-01-cache.html", "spec"),
    ("docs/specs/tiny.md", "spec"),
])
def test_profile_inference(path, expected):
    assert sc.infer_profile(Path(path)) == expected


def test_r1_b2_short_docs_get_no_automatic_exemption(tmp_path):
    """A word-count downgrade to `note` meant the cheapest way to pass the gate
    was to delete words. A thirteen-word implementation manual committing a
    one-way door exited 0."""
    tiny = ("# Rewrite Billing In Erlang\n\nStatus: accepted\n\n"
            "## Design\nWe will rewrite billing in Erlang.\n")
    d = tmp_path / "2026-09-16-billing.md"
    d.write_text(tiny, encoding="utf-8")
    rep = sc.check(d, None, False, False)
    assert rep.profile == "spec", "short docs must not self-downgrade"
    assert fails(rep), "a 13-word implementation manual must not pass"


def test_r1_b2_note_profile_is_still_available_explicitly(tmp_path):
    """`note` is right for a short design-bearing doc — but as a choice someone
    makes and a reviewer can see, not a silent property of word count."""
    tiny = "# T\n\nStatus: accepted\n\n## Design\nAdd a flag behind a config key.\n"
    assert not fails(run(tmp_path, tiny, profile="note"))


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


# ==========================================================================
# Regression: every blocker from the P20 cross-model review (round 1, 3/10).
#
# Each test below is the reviewer's own reproduction input, verbatim. These are
# not paraphrases of the findings — they are the failing cases, so a future
# refactor that reintroduces any of them turns this suite red rather than
# quietly restoring a bypass.
# ==========================================================================

ALT_BLOCK = ("- Redis: an extra process to operate, and the network hop eats "
             "the win.\n"
             "- Firestore: durable, but the platform lock-in was not worth it.\n")


def alts(new: str) -> str:
    return GOOD.replace(ALT_BLOCK, new)


def acceptance(new: str) -> str:
    return GOOD.replace("- p50 latency <= 200ms.\n- `make check` passes.", new)


def test_r1_b2_subheading_and_its_prose_are_one_alternative(tmp_path):
    """'### Redis / Too expensive.' counted as TWO options — the heading and the
    paragraph were both scored as names."""
    assert "C5-thin-alternatives" in fails(
        run(tmp_path, alts("### Redis\nToo expensive.\n")))


def test_r1_b2b_each_alternative_needs_its_own_justification(tmp_path):
    """One reason on the first option used to cover every option after it."""
    assert "C5-unjustified-alternative" in fails(
        run(tmp_path, alts("- Redis: too expensive\n- Firestore\n")))


def test_r1_b3_butterfly_is_not_a_rejection_reason(tmp_path):
    """`\\b(?:but|...)` with no closing boundary matched 'Butterfly'."""
    assert fails(run(tmp_path, alts("- Butterfly\n- Redis\n")))


def test_r1_b3_negative_but_still_matches_as_a_word(tmp_path):
    """Fixing the boundary must not stop 'but' matching when it IS the word."""
    assert "C5-no-rejection-reason" not in checks(run(tmp_path, GOOD))


@pytest.mark.parametrize("criterion,why", [
    ("- 3 ministers should like it.", "'min' matched the prefix of 'ministers'"),
    ("- p50 latency should feel fast.", "a percentile NAME is not a target"),
    ("- 5 stakeholders signed off.", "a count of people is not a threshold"),
    ("- Signed off by 2026/09/16.", "a date is not a measurement"),
])
def test_r1_b4_unit_lookalikes_are_not_measurements(tmp_path, criterion, why):
    assert "C8-unmeasurable-acceptance" in checks(
        run(tmp_path, acceptance(criterion))), why


@pytest.mark.parametrize("criterion", [
    "- 99.9% uptime.",            # '%' is not a word char: no trailing \b
    "- p50 latency <= 200ms.",
    "- Cold start under 3 s.",
    "- 500 req/s sustained.",
    "- `pytest tests/` is green.",
])
def test_r1_b4_real_measurements_still_pass(tmp_path, criterion):
    assert "C8-unmeasurable-acceptance" not in checks(
        run(tmp_path, acceptance(criterion)))


def test_r1_b6_a_fenced_example_is_not_the_document(tmp_path):
    """A file that is nothing but a fenced sample of a good doc parsed as that
    good doc and returned zero findings."""
    assert fails(run(tmp_path, "```markdown\n" + GOOD + "\n```"))


def test_r1_b6_fence_stripping_does_not_eat_real_sections(tmp_path):
    body = GOOD.replace("## Design\n", "## Design\n\n```go\ntype Store interface{}\n```\n\n")
    assert fails(run(tmp_path, body)) == set()


def test_r1_b7a_successor_must_be_on_the_status_line(tmp_path):
    """An unrelated URL two lines down used to satisfy the pointer."""
    assert "C2-dangling-supersede" in fails(run(tmp_path, GOOD.replace(
        "Status: accepted", "Status: superseded\nAuthor: https://example.com/alice")))


def test_r1_b7b_emphasis_does_not_bypass_the_pointer(tmp_path):
    """`Status: **superseded**` fell out of the known set into a warning, which
    skipped successor enforcement entirely."""
    assert "C2-dangling-supersede" in fails(
        run(tmp_path, GOOD.replace("Status: accepted", "Status: **superseded**")))


def test_r1_b8_a_placeholder_is_not_an_answer(tmp_path):
    """--strict promoted only ABSENCE, so 'TBD' converted a blocking omission
    into a pass without supplying anything."""
    body = GOOD.replace(
        "Reversal cost: one-way door — the storage engine is not swappable "
        "after launch.", "Reversal cost: TBD")
    assert "C3-no-reversal-cost" in fails(run(tmp_path, body, strict=True))


@pytest.mark.parametrize("filler", ["TBD", "TODO", "?", "n/a", "unknown"])
def test_r1_b8_placeholder_variants(tmp_path, filler):
    body = GOOD.replace(
        "Reversal cost: one-way door — the storage engine is not swappable "
        "after launch.", f"Reversal cost: {filler}")
    assert "C3-no-reversal-cost" in checks(run(tmp_path, body))


MANUAL = "# X\n\nStatus: accepted\n\n## Design\n" + ("We will add a handler. " * 60)


def test_r1_b9_the_recommended_door_line_does_not_disable_c9(tmp_path):
    """C3's own recommended boilerplate contains trade-off vocabulary. One hit
    used to be enough, so the house style switched off the best check."""
    assert "C9-implementation-manual" in fails(run(
        tmp_path,
        MANUAL.replace("Status: accepted",
                       "Status: accepted\nReversal cost: two-way door"),
        profile="note"))


def test_r1_b9_an_empty_tradeoffs_heading_is_not_a_tradeoff(tmp_path):
    assert "C9-implementation-manual" in fails(
        run(tmp_path, MANUAL + "\n\n## Trade-offs\n", profile="note"))


def test_r1_b9_real_tradeoff_prose_still_clears_c9(tmp_path):
    assert "C9-implementation-manual" not in checks(run(tmp_path, GOOD))


def test_r1_b10_make_spec_scaffolds_Decision_so_adr_must_know_it(tmp_path):
    """make-spec's ADR variant emits '## Decision'. The design class did not
    list it, so the advertised composition rejected its own scaffold."""
    assert "C1-missing-section" not in fails(
        run(tmp_path, GOOD.replace("## Design", "## Decision"), profile="adr"))


def test_r1_nb4_typographic_apostrophe_does_not_evade_c4(tmp_path):
    body = GOOD.replace(
        "- A general-purpose reusable cache. This one makes app-specific "
        "assumptions.", "- The system shouldn’t crash")
    assert "C4-negated-goal" in checks(run(tmp_path, body))


def test_r1_nb4_numeric_entity_heading_still_classifies():
    sections, _ = sc.parse("<h2>Obj&#101;ctive</h2><p>x</p>", True)
    sc.attach_subtrees(sections)
    sc.classify(sections)
    assert sections[0].cls == "objective"


# --- B5: the two entry surfaces must agree on identical documents -------------

HTML_DOC = (
    '<h1>D</h1><p>Status: accepted</p>'
    '<h2>Objective</h2><p>x</p>'
    '<h2>Design</h2><p>we chose A instead of B rather than C</p>'
    '<h2>Non-goals</h2><ul><li>No albums</li></ul>'
    '<h2>Alternatives considered</h2>'
    '<ul><li>B: it is too slow for this</li><li>C: painful lock-in here</li></ul>'
    '<h2>Acceptance</h2><p><code>make check</code> passes</p>'
)


def test_r1_b5_html_code_element_is_a_runnable_command(tmp_path):
    """<code>make check</code> is the HTML spelling of `make check`; stripping
    the tag before C8 ran made the surfaces disagree."""
    assert "C8-unmeasurable-acceptance" not in checks(
        run(tmp_path, HTML_DOC, name="d.html"))


def test_r1_b5_html_href_is_a_successor(tmp_path):
    body = HTML_DOC.replace(
        "Status: accepted",
        'Status: superseded (<a href="next.md">replacement</a>)')
    assert "C2-dangling-supersede" not in checks(
        run(tmp_path, body, name="s.html"))


def test_r1_b5_href_urls_survive_stripping_for_link_checking():
    """--check-links issued zero requests on HTML because href was dropped."""
    assert sc.URL_RE.search(
        sc._strip_html('<a href="https://example.invalid/y">r</a>'))


def test_r1_b5_pre_blocks_are_not_document_structure():
    sections, _ = sc.parse(
        "<h1>T</h1><pre><h2>Fake</h2></pre><h2>Design</h2><p>x</p>", True)
    assert [s.title for s in sections] == ["T", "Design"]


# --- NB3: C11 had no controls at all -----------------------------------------

def test_r1_nb3_check_links_reports_a_dead_link(tmp_path, monkeypatch):
    import urllib.error
    import urllib.request

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 404, "gone", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    body = GOOD + "\n\nSee https://example.invalid/missing for detail.\n"
    assert "C11-dead-link" in fails(run(tmp_path, body, check_links=True))


def test_r1_nb3_check_links_tolerates_bot_blocking(tmp_path, monkeypatch):
    """403/405/429 mean 'blocked to bots', not 'dead'."""
    import urllib.error
    import urllib.request

    def blocked(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 403, "forbidden", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    body = GOOD + "\n\nSee https://example.invalid/blocked for detail.\n"
    assert "C11-dead-link" not in checks(run(tmp_path, body, check_links=True))


def test_r1_nb3_links_are_not_checked_by_default(tmp_path, monkeypatch):
    """The default gate must stay hermetic — CI has no network contract."""
    import urllib.request

    def fail(req, timeout=0):
        raise AssertionError("network touched without --check-links")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    run(tmp_path, GOOD + "\n\nhttps://example.invalid/x\n")


# --- NB1: a prose claim in SKILL.md that the table contradicted ---------------

def test_r1_nb1_skill_md_alternatives_claim_matches_the_table():
    """SKILL.md claimed alternatives is required in every profile but `note`.
    The `plan` profile did not require it. A claim no test enforces is the
    defect; this test is what makes the corrected wording true."""
    skill = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text()
    for prof in ("adr", "spec", "rfd"):
        assert "alternatives" in sc.PROFILES[prof]["required"], prof
    assert "alternatives" not in sc.PROFILES["plan"]["required"]
    assert "alternatives" not in sc.PROFILES["note"]["required"]
    assert "required in every profile but `note`" not in skill, (
        "SKILL.md still carries the claim the table contradicts")


def test_r1_b8_documented_check_ids_match_the_code():
    """Three different numbers shipped in the first cut: the code emitted 18
    finding ids, the SKILL.md table documented 16, and its prose said fourteen.
    CLAUDE.md's self-documenting standards make count coherence a rule; this is
    the rule made executable."""
    import re
    src = (Path(__file__).resolve().parents[1] / "scripts" / "spec_check.py").read_text()
    skill = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text()
    emitted = set(re.findall(r'"(C\d+-[a-z-]+)"', src))
    documented = set(re.findall(r"`(C\d+-[a-z-]+)`", skill))
    assert emitted - documented == set(), f"undocumented: {emitted - documented}"
    assert documented - emitted == set(), f"documented but dead: {documented - emitted}"
    rows = len(re.findall(r"^\| `C\d+-", skill, re.M))
    claimed = set(re.findall(r"(\d+) findings", skill))
    assert claimed, "SKILL.md states no finding count"
    assert claimed == {str(rows)}, (
        f"prose claims {claimed} findings, the table has {rows} rows")


# --- gaps the mutation sweep exposed (mutants that survived round 1) ---------

def test_c9_a_single_tradeoff_expression_is_below_the_floor(tmp_path):
    """MIN_TRADEOFF_HITS exists because ONE token was enough for the metadata
    line this skill recommends to switch the detector off. Nothing tested the
    floor itself, so lowering it back to 1 survived the suite."""
    one = ("# X\n\nStatus: accepted\n\n## Design\n"
           + ("We will add a handler and wire the route. " * 50)
           + "\nWe chose it.\n")
    assert "C9-implementation-manual" in fails(run(tmp_path, one, profile="note"))
    two = one + "\nWe considered a queue instead of a handler.\n"
    assert "C9-implementation-manual" not in checks(run(tmp_path, two, profile="note"))


def test_c9_ignores_the_metadata_block(tmp_path):
    """C9 must read PROSE. Reading the raw text let `Reversal cost: two-way
    door` — a line this skill tells authors to write — satisfy the detector."""
    meta_only = ("# X\n\nStatus: accepted\nReversal cost: two-way door\n"
                 "Decision-class: trade-off\n\n## Design\n"
                 + ("We will add a handler and wire the route. " * 50))
    assert "C9-implementation-manual" in fails(
        run(tmp_path, meta_only, profile="note"))


def test_html_commented_out_headings_are_not_sections(tmp_path):
    """A section deleted by commenting it out still satisfied C1, so the HTML
    path and the markdown path disagreed about which sections a document has."""
    body = ('<h1>D</h1><h2>Design</h2><p>we chose A instead of B rather than C</p>'
            '<!-- <h2>Alternatives considered</h2><ul><li>B: too slow</li></ul> -->')
    sections, _ = sc.parse(body, True)
    assert [s.title for s in sections] == ["D", "Design"], (
        "a commented-out heading must not count as a section")
    rep = run(tmp_path, body, name="d.html")
    assert "C1-missing-section" in fails(rep)


def test_markdown_and_html_agree_on_commented_out_headings():
    """Both surfaces must reach the same answer on the same deletion."""
    md, _ = sc.parse("# D\n\n## Design\nx\n\n<!-- ## Alternatives considered -->\n",
                     False)
    html, _ = sc.parse('<h1>D</h1><h2>Design</h2><p>x</p>'
                       '<!-- <h2>Alternatives considered</h2> -->', True)
    assert [s.title for s in md] == [s.title for s in html] == ["D", "Design"]


# ==========================================================================
# Regression: P20 round 2. Each of these is a defect the round-1 FIXES
# introduced or left, found by attacking the fixes themselves.
# ==========================================================================

def test_r2_hidden_front_matter_cannot_shadow_a_visible_status(tmp_path):
    """The front-matter hoist prepended, so `status: accepted` in an HTML
    comment overrode a visible `Status: superseded` — the invisible value won
    and the supersession pointer was never demanded."""
    body = ('<!--\n---\nstatus: accepted\n---\n-->\n'
            '<h1>D</h1><p>Status: superseded</p>'
            '<h2>Design</h2><p>we chose A instead of B</p>')
    assert "C2-dangling-supersede" in fails(
        run(tmp_path, body, name="d.html", profile="note"))


def test_r2_front_matter_still_resolves_when_it_is_the_only_status(tmp_path):
    body = ('<!--\n---\nstatus: draft\n---\n-->\n'
            '<h1>D</h1><h2>Design</h2><p>we chose A instead of B</p>')
    assert "C2-no-status" not in checks(
        run(tmp_path, body, name="d.html", profile="note"))


def test_r2_one_heading_cannot_discharge_three_required_classes():
    """'Design goals and non-goals' matched design + goals + non_goals, so a
    single heading satisfied three required classes at once."""
    sections, _ = sc.parse("# T\n\n## Design goals and non-goals\nx\n", False)
    sc.attach_subtrees(sections)
    sc.classify(sections)
    cls = sections[1].classes
    assert "design" not in cls, f"incidental word match leaked in: {cls}"
    assert len(cls) <= 2, "two conjunction segments, at most two classes"


def test_r2_a_genuine_conjunction_still_answers_both():
    for title, expected in [
        ("Goals and non-goals", {"goals", "non_goals"}),
        ("Alternatives and drawbacks", {"alternatives", "drawbacks"}),
    ]:
        sections, _ = sc.parse(f"# T\n\n## {title}\nx\n", False)
        sc.attach_subtrees(sections)
        sc.classify(sections)
        assert set(sections[1].classes) == expected, title


@pytest.mark.parametrize("block,why", [
    ("- Redis\n  it is an extra process to operate and the hop eats the win\n"
     "- Firestore\n  durable, but the platform lock-in was not worth it\n",
     "space-indented continuation"),
    ("- Redis\n\tit is an extra process to operate and the hop eats the win\n"
     "- Firestore\n\tdurable, but the platform lock-in was not worth it\n",
     "tab-indented continuation"),
])
def test_r2_indented_continuation_is_the_option_s_justification(tmp_path, block, why):
    """A reason written on a continuation line rather than after a colon was
    dropped entirely, so an ordinary authoring form read as an unargued option."""
    body = GOOD.replace(ALT_BLOCK, block)
    assert "C5-unjustified-alternative" not in checks(run(tmp_path, body)), why


def test_r2_tab_indented_detail_is_not_a_separate_option(tmp_path):
    body = GOOD.replace(
        ALT_BLOCK,
        "- Redis: an extra process to operate, and the hop eats the win\n"
        "\t- benchmarked at 3ms\n"
        "- Firestore: durable, but the lock-in was not worth it\n")
    sections, _ = sc.parse(body, False)
    sc.attach_subtrees(sections)
    sc.classify(sections)
    alts = [s for s in sections if "alternatives" in s.classes]
    assert [lbl for lbl, _ in sc.alternative_entries(sections, alts)] == [
        "Redis", "Firestore"]


# ==========================================================================
# Regression: P20 round 2, Strata B (5/10). Five blockers, each an attack on a
# round-1 fix. Inputs are the reviewer's, verbatim.
# ==========================================================================

def test_r2b_markdown_comments_are_stripped_too(tmp_path):
    """The comment strip lived only in the HTML branch, so a markdown doc could
    hide its non-goals and alternatives inside <!-- --> and exit 0 while a
    reader saw an unargued one-way door."""
    body = GOOD.replace("## Non-goals", "<!--\n## Non-goals").replace(
        "- Location-aware caching. Useful later, out of scope for v1.",
        "- Location-aware caching. Useful later, out of scope for v1.\n-->")
    assert fails(run(tmp_path, body))


@pytest.mark.parametrize("raw,is_html", [
    ('<h1>D</h1><!-- <h2>Design</h2><p>x</p>', True),
    ("# D\n\n<!--\n## Design\nx\n", False),
])
def test_r2b_an_unterminated_comment_hides_the_rest(raw, is_html):
    """`(?s)<!--.*?-->` needs a terminator; HTML5 does not. An unterminated
    `<!--` comments out the rest of the document — a browser honours it, so the
    checker must too, or it reads sections no reader can see."""
    sections, _ = sc.parse(raw, is_html)
    assert [s.title for s in sections] == ["D"]


def test_r2b_a_pre_token_inside_a_comment_erases_nothing(tmp_path):
    """The tag strip ran BEFORE the comment strip, so the word "<pre>" inside an
    editor note matched the tag stripper and erased every section up to the next
    real </pre>. A document that renders perfectly took four C1 failures."""
    body = ('<h1>Widget Cache</h1>'
            '<!-- editor note: leave the <pre> blocks unstyled -->'
            '<h2>Objective</h2><p>x</p>'
            '<h2>Design</h2><p>we chose A instead of B</p>'
            '<h2>Non-goals</h2><ul><li>No albums</li></ul>'
            '<h2>Alternatives considered</h2>'
            '<ul><li>B: too slow here</li><li>C: painful lock-in issues</li></ul>'
            '<pre>store.Get(k)</pre>')
    sections, _ = sc.parse(body, True)
    assert [s.title for s in sections] == [
        "Widget Cache", "Objective", "Design", "Non-goals",
        "Alternatives considered"]


def test_r2b_html_lists_do_not_lose_their_first_item():
    """`<li>` lowered without a leading newline glued the first item of every
    list to the preceding text, so it parsed one indent deeper than its siblings
    and was discarded as a continuation line.

    This suite's OWN `HTML_DOC` fixture had exactly one alternative reaching the
    checker — the HTML tests were passing for the wrong reason."""
    sections, _ = sc.parse(HTML_DOC, True)
    sc.attach_subtrees(sections)
    sc.classify(sections)
    alts = [s for s in sections if "alternatives" in s.classes]
    assert [lbl for lbl, _ in sc.alternative_entries(sections, alts)] == ["B", "C"]


def test_r2b_both_surfaces_find_the_same_alternatives(tmp_path):
    """The markdown twin of HTML_DOC must reach the same verdict."""
    md = ("# D\n\nStatus: accepted\n\n## Objective\nx\n\n"
          "## Design\nwe chose A instead of B rather than C\n\n"
          "## Non-goals\n- No albums\n\n"
          "## Alternatives considered\n- B: it is too slow for this\n"
          "- C: painful lock-in here\n\n"
          "## Acceptance\n`make check` passes\n")
    assert fails(run(tmp_path, md, profile="note")) == fails(
        run(tmp_path, HTML_DOC, name="d.html", profile="note"))


def test_r2b_a_status_that_names_no_state_does_not_discharge_c2(tmp_path):
    """`- Status: 200 on success` in body prose satisfied C2's only blocking
    arm. A status a document cannot be superseded FROM is not a status."""
    body = GOOD.replace("Status: accepted\n", "").replace(
        "## Design", "## Design\n- Status: 200 on success\n")
    assert "C2-no-status" in fails(run(tmp_path, body))


def test_r2b_a_real_status_later_in_the_doc_still_counts(tmp_path):
    """Scanning every candidate must not mean the first mention wins."""
    body = GOOD.replace(
        "Status: accepted",
        "The endpoint returns HTTP status: 200 on success.\nStatus: accepted")
    assert "C2-no-status" not in checks(run(tmp_path, body))


def test_r2b_front_matter_needs_a_recognisable_status(tmp_path):
    """A deploy snippet in a leading comment ("status: enabled") suppressed
    C2-no-status on a doc with no visible status at all."""
    body = ('<!--\n  deploy snippet:\n    service: widget\n    status: enabled\n-->\n'
            '<h1>D</h1><h2>Design</h2><p>we chose A instead of B</p>')
    assert "C2-no-status" in fails(run(tmp_path, body, name="d.html",
                                       profile="note"))


def test_r2b_a_three_question_heading_keeps_all_three():
    """A hard cap of two truncated a genuine three-segment title, so a plan with
    "Objective, goals and acceptance criteria" hard-failed for an objective it
    plainly has — a false negative traded for a false positive."""
    sections, _ = sc.parse(
        "# T\n\n## Objective, goals and acceptance criteria\nx\n", False)
    sc.attach_subtrees(sections)
    sc.classify(sections)
    assert set(sections[1].classes) == {"objective", "goals", "acceptance"}


@pytest.mark.parametrize("body,name", [
    ('<h1>D</h1><h2>Objective</h2><p>x</p><h2>Design</h2><p>we chose A '
     'instead of B</p><!-- <h2>Non-goals</h2><ul><li>No albums</li></ul>'
     '<h2>Alternatives considered</h2><ul><li>B: too slow</li>'
     '<li>C: lock-in</li></ul>', "u.html"),
    ("# D\n\nStatus: accepted\n\n## Objective\nx\n\n## Design\n"
     "we chose A instead of B\n\n<!--\n## Non-goals\n- No albums\n\n"
     "## Alternatives considered\n- B: too slow\n- C: lock-in\n", "u.md"),
])
def test_r3_unterminated_comment_produces_missing_section(tmp_path, body, name):
    """The exact falsifier Strata B named for its round-2 prediction.

    Its prediction was that round 3 would strip terminated comments on the
    markdown branch and stop there, leaving an unterminated `<!--` parsing every
    heading and exiting 0 on both surfaces. `strip_comments` handles the
    unterminated form on both, and this asserts the consequence the prediction
    said would not hold: the hidden sections are MISSING, not present.
    """
    assert "C1-missing-section" in fails(run(tmp_path, body, name=name))


# --- the invariant behind the comment handling ------------------------------

def test_the_checker_sees_what_a_browser_would_render():
    """A raw `<!--` inside `<pre>` hides the rest of the document — in the
    checker AND in a browser.

    `<pre>` is a normal element in HTML5, not a raw-text element like `<script>`
    or `<style>`, so its contents are parsed and `<!--` opens a comment there
    exactly as it does anywhere else. The checker agreeing with the renderer is
    the property worth having; disagreeing in either direction is how a section
    gets counted that no reader can see, which was round-2 blocker 1.

    An author who means a literal marker writes `&lt;!--`, and that case is
    below — it must NOT hide anything.
    """
    tail = ('<h2>Non-goals</h2><ul><li>No albums</li></ul>'
            '<h2>Alternatives considered</h2>'
            '<ul><li>B: too slow</li><li>C: lock-in</li></ul>')
    raw_marker = '<h1>D</h1><h2>Design</h2><pre><!-- sample</pre>' + tail
    escaped = '<h1>D</h1><h2>Design</h2><pre>&lt;!-- sample</pre>' + tail
    in_code = ('<h1>D</h1><h2>Design</h2><p>write <code>&lt;!--</code></p>' + tail)

    assert [s.title for s in sc.parse(raw_marker, True)[0]] == ["D", "Design"], (
        "a raw <!-- in <pre> opens a comment for the browser too")
    for body, why in [(escaped, "escaped marker"), (in_code, "marker in <code>")]:
        assert [s.title for s in sc.parse(body, True)[0]] == [
            "D", "Design", "Non-goals", "Alternatives considered"], why
