"""Unit tests for the unhobble deterministic core."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from context_audit import (  # noqa: E402
    Section,
    audit,
    audit_prompt,
    classify_sentence,
    count_examples,
    count_outbound_links,
    disclosure_check,
    estimate_tokens,
    find_contradictions,
    find_duplicates,
    is_derivable,
    jaccard,
    mechanism_refs,
    polarity_profile,
    rules_ratio,
    sentences,
    shingles,
    split_sections,
)


# ---------------------------------------------------------------- segmentation


def test_split_sections_captures_preamble():
    secs = split_sections("intro prose here\n\n## First\nbody\n", "f.md")
    assert [s.heading for s in secs] == ["(preamble)", "First"]
    # Pin the preamble range too — asserting only headings left it free to drift.
    assert (secs[0].start_line, secs[0].end_line) == (1, 2)
    assert (secs[1].start_line, secs[1].end_line) == (3, 4)


def test_four_backtick_fence_is_not_closed_by_an_inner_three():
    # SKILL.md files wrap markdown examples in 4-backtick fences, and SKILL.md
    # is a first-class audit target.
    text = "# A\n````\n```\n# inner heading?\n```\n````\n# B\nreal\n"
    assert [s.heading for s in split_sections(text, "t.md")] == ["A", "B"]


def test_tilde_and_backtick_fences_do_not_close_each_other():
    text = "# A\n```\n~~~\n# inner?\n~~~\n```\n# B\nreal\n"
    assert [s.heading for s in split_sections(text, "t.md")] == ["A", "B"]


def test_split_sections_line_ranges_are_contiguous():
    secs = split_sections("## A\na\n## B\nb\n## C\nc\n", "f.md")
    assert [(s.start_line, s.end_line) for s in secs] == [(1, 2), (3, 4), (5, 6)]


def test_hash_inside_fenced_block_is_not_a_heading():
    text = "## Real\n```bash\n# not a heading\nls\n```\ntail\n"
    secs = split_sections(text, "f.md")
    assert [s.heading for s in secs] == ["Real"]


def test_tilde_fence_also_suppresses_headings():
    text = "## Real\n~~~\n# not a heading\n~~~\n"
    assert [s.heading for s in split_sections(text, "f.md")] == ["Real"]


def test_empty_document_yields_no_sections():
    assert split_sections("", "f.md") == []


def test_section_tokens_are_populated():
    secs = split_sections("## A\n" + "word " * 200, "f.md")
    assert secs[0].tokens > 50


# ------------------------------------------------------------------- polarity


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("Never write multi-paragraph docstrings in this repo.", "prohibition"),
        ("You must not commit directly to main branch.", "prohibition"),
        ("Do NOT add comments to generated files.", "prohibition"),
        ("Avoid stating the obvious in documentation.", "prohibition"),
        ("Every work unit must be tracked in Linear.", "mandate"),
        ("Always run the janitor after merging a branch.", "mandate"),
        ("Leave documentation as appropriate for the change.", "permission"),
        ("Use your judgement on the comment density here.", "permission"),
        ("Write code that reads like the surrounding code.", "judgment"),
        ("Prefer bun over npm for new projects.", "judgment"),
        ("Default to a worktree unless the change is a typo.", "judgment"),
        ("The vault at ~/broomva-vault symlinks into this workspace.", "descriptive"),
    ],
)
def test_classify_sentence(sentence, expected):
    assert classify_sentence(sentence) == expected


def test_prohibition_beats_mandate_on_must_not():
    # "must not" contains "must"; the more specific class has to win.
    assert classify_sentence("Agents must not bypass the gate.") == "prohibition"


# --- use vs mention: a doc that discusses rules is not issuing them ---------


@pytest.mark.parametrize(
    "sentence",
    [
        'The old rule was "Never write docstrings" before the rewrite.',
        'We replaced “do not add comments” with a judgement frame.',
        "The deleted line said `always run the janitor` verbatim.",
    ],
)
def test_quoted_rule_is_a_mention_not_a_directive(sentence):
    assert classify_sentence(sentence) == "descriptive"


@pytest.mark.parametrize(
    "sentence",
    [
        'It never says "delete" anywhere in the output.',
        "The hook never fires on read-only tools.",
        "It always renders the disclaimer at the end.",
        "They cannot reach the producer of that signal.",
    ],
)
def test_third_person_description_is_not_a_directive(sentence):
    assert classify_sentence(sentence) == "descriptive"


@pytest.mark.parametrize(
    "sentence,expected",
    [
        # English does not distinguish "the script must exit 0" (describing)
        # from "the file must be committed" (instructing). Suppressing the
        # must-family costs real directives, so it is never suppressed: the
        # heuristic fails OPEN, because under-counting rules is the reading
        # that wrongly says "your surface is already fine".
        ("The script must exit non-zero on a missing path.", "mandate"),
        ("The file must be committed before the runtime exits.", "mandate"),
        ("The test must not be skipped in CI.", "prohibition"),
        # `there` / `this` are directive subjects far too often to suppress.
        ("There must be a Linear ticket for every work unit.", "mandate"),
        ("This must be done before every merge.", "mandate"),
    ],
)
def test_must_family_is_never_suppressed(sentence, expected):
    assert classify_sentence(sentence) == expected


@pytest.mark.parametrize(
    "sentence,expected",
    [
        # An apostrophe pair must not forge a quoted span and swallow the rule.
        ("Claude's output must never contain the user's raw API key.", "prohibition"),
        ("The agent's worktree must always be clean before it's reused.", "mandate"),
        # A genuine single-quoted citation still reads as a mention.
        ("The line said 'never merge red' before we cut it.", "descriptive"),
    ],
)
def test_possessives_do_not_forge_quoted_spans(sentence, expected):
    assert classify_sentence(sentence) == expected


def test_url_slug_is_not_a_directive():
    s = "See https://example.com/docs/never-merge-red for the rationale."
    assert classify_sentence(s) == "descriptive"


@pytest.mark.parametrize(
    "sentence,expected",
    [
        # An actor subject is genuine constraint language — still a directive.
        ("The agent must not bypass the control gate.", "prohibition"),
        # A relative "that" must not swallow the judgement framing.
        ("Write code that reads like the surrounding code.", "judgment"),
        # Keyword outside the quotes is still a real directive.
        ('Never run `rm -rf` against the vault.', "prohibition"),
        ('Always quote the "topic" field in the payload.', "mandate"),
    ],
)
def test_real_directives_survive_the_use_mention_filter(sentence, expected):
    assert classify_sentence(sentence) == expected


def test_falls_through_to_a_later_unquoted_keyword():
    # First hit is quoted; a genuine directive later in the sentence wins.
    s = 'The old rule "never add comments" is gone, so prefer local idiom now.'
    assert classify_sentence(s) == "judgment"


def test_sentences_skips_fenced_code():
    text = "Never do this thing here.\n```\nnever run this command line\n```\n"
    assert len(sentences(text)) == 1


def test_sentences_ignores_short_fragments():
    assert sentences("ok\nfine\n") == []


def test_polarity_profile_and_dominant():
    # Weighted so `dominant` has one correct answer; the earlier 1-1-1 tie made
    # the assertion accept every outcome it could produce.
    text = (
        "Never do X here. Never do V either. Never touch U.\n"
        "You must do Y always. Prefer Z over W."
    )
    counts, dominant = polarity_profile(text)
    assert counts["prohibition"] == 3
    assert counts["mandate"] == 1
    assert counts["judgment"] == 1
    assert dominant == "prohibition"


def test_rules_ratio_all_hard():
    counts = {
        "prohibition": 3,
        "mandate": 1,
        "permission": 0,
        "judgment": 0,
        "descriptive": 9,
    }
    assert rules_ratio(counts) == 1.0


def test_rules_ratio_ignores_descriptive():
    counts = {
        "prohibition": 1,
        "mandate": 0,
        "permission": 0,
        "judgment": 1,
        "descriptive": 50,
    }
    assert rules_ratio(counts) == 0.5


def test_rules_ratio_no_directives_is_zero_not_error():
    counts = {
        "prohibition": 0,
        "mandate": 0,
        "permission": 0,
        "judgment": 0,
        "descriptive": 4,
    }
    assert rules_ratio(counts) == 0.0


# ------------------------------------------------------------------- examples


def test_count_examples_counts_fence_pairs_not_lines():
    assert count_examples("```py\na\n```\n```sh\nb\n```\n") == 2


def test_count_examples_counts_flavoured_table_rows():
    text = "| Excuse | Reality |\n|---|---|\n| example of a bad thing | no |\n"
    assert count_examples(text) >= 1


def test_count_examples_zero_on_plain_prose():
    assert count_examples("Just some ordinary prose without any samples.") == 0


def test_count_examples_counts_prose_example_lines():
    # The dominant form in prompts: examples as lines, not table rows.
    text = (
        "Example: if you see a raw SQL concat, flag it.\n"
        "Example: if you see a missing null check, flag it.\n"
        "- For instance: an empty test file.\n"
    )
    assert count_examples(text) == 3


def test_count_examples_ignores_example_mid_sentence():
    # Only a leading example marker counts; the word in passing does not.
    assert count_examples("This is not an example of a problem we care about.") == 0


# ------------------------------------------------------------------ derivable


def test_is_derivable_flags_a_directory_listing():
    sec = Section(
        "f.md",
        "Project Structure",
        2,
        1,
        6,
        "## Project Structure\nsrc/\ntests/\ndocs/\nscripts/\n",
    )
    assert is_derivable(sec) is True


def test_is_derivable_false_for_prose_under_structural_heading():
    sec = Section(
        "f.md",
        "Structure",
        2,
        1,
        4,
        "## Structure\nThe project is organised around a single control loop.\n",
    )
    assert is_derivable(sec) is False


def test_is_derivable_false_for_empty_body():
    assert is_derivable(Section("f.md", "Structure", 2, 1, 1, "## Structure\n")) is False


def test_is_derivable_generic_branch_without_a_structural_heading():
    # Exercises the ratio>=0.7 branch; every prior case exited via the heading
    # branch, leaving this one dead to the suite.
    sec = Section(
        "f.md",
        "Where Things Live",
        2,
        1,
        7,
        "## Where Things Live\nsrc/core/\nsrc/api/\ntests/unit/\ntests/e2e/\nscripts/ci/\n",
    )
    assert is_derivable(sec) is True


def test_is_derivable_generic_branch_needs_enough_lines():
    sec = Section("f.md", "Where Things Live", 2, 1, 3, "## Where Things Live\nsrc/\napi/\n")
    assert is_derivable(sec) is False


# ------------------------------------------------------------------ mechanism


def test_markdown_reference_never_anchors(tmp_path):
    (tmp_path / "AGENTS.md").write_text("x")
    sec = Section("f.md", "H", 2, 1, 2, "See `AGENTS.md` for the full rule.")
    assert mechanism_refs(sec, tmp_path) == []


def test_existing_script_is_an_anchored_candidate(tmp_path):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "gate.sh").write_text("#!/bin/sh\n")
    sec = Section("f.md", "H", 2, 1, 2, "Enforced by `hooks/gate.sh` on every call.")
    refs = mechanism_refs(sec, tmp_path)
    assert refs == [{"ref": "hooks/gate.sh", "kind": "path", "exists_on_disk": True}]


def test_missing_script_is_referenced_but_not_anchored(tmp_path):
    sec = Section("f.md", "H", 2, 1, 2, "Enforced by `hooks/ghost.sh` somewhere.")
    refs = mechanism_refs(sec, tmp_path)
    assert refs[0]["exists_on_disk"] is False


def test_commands_never_claim_disk_existence(tmp_path):
    sec = Section("f.md", "H", 2, 1, 2, "Run `make control-audit` before merging.")
    refs = mechanism_refs(sec, tmp_path)
    assert refs[0]["kind"] == "command"
    assert refs[0]["exists_on_disk"] is False


def test_mechanism_refs_deduplicates(tmp_path):
    sec = Section("f.md", "H", 2, 1, 3, "`a/b.py` then again `a/b.py` here.")
    assert len(mechanism_refs(sec, tmp_path)) == 1


def test_prose_in_backticks_is_not_a_mechanism(tmp_path):
    sec = Section("f.md", "H", 2, 1, 2, "The `--dry-run` flag is the default.")
    assert mechanism_refs(sec, tmp_path) == []


def test_absolute_path_outside_the_repo_never_anchors(tmp_path):
    # `repo_root / "/abs/x.sh"` silently discards repo_root, which would mark a
    # section anchored against a file that is not in the audited surface.
    outside = tmp_path.parent / "outside_anchor_probe.sh"
    outside.write_text("#!/bin/sh\n")
    try:
        sec = Section("f.md", "H", 2, 1, 2, f"Anchored by `{outside}`.")
        refs = mechanism_refs(sec, tmp_path)
        assert all(r["exists_on_disk"] is False for r in refs)
    finally:
        outside.unlink()


def test_parent_traversal_never_anchors(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    escapee = tmp_path / "escape.sh"
    escapee.write_text("#!/bin/sh\n")
    sec = Section("f.md", "H", 2, 1, 2, "Anchored by `../escape.sh`.")
    refs = mechanism_refs(sec, root)
    assert all(r["exists_on_disk"] is False for r in refs)


# ----------------------------------------------------------------- duplication


def test_jaccard_identical_and_disjoint():
    assert jaccard({1, 2}, {1, 2}) == 1.0
    assert jaccard({1}, {2}) == 0.0
    assert jaccard(set(), {1}) == 0.0


def test_shingles_short_text_degrades_gracefully():
    assert shingles("only three words", k=8) == {("only", "three", "words")}


def test_find_duplicates_catches_repeated_section():
    body = " ".join(f"policy statement number {i} about branching" for i in range(30))
    a = split_sections(f"## A\n{body}\n", "one.md")[0]
    b = split_sections(f"## B\n{body}\n", "two.md")[0]
    for s in (a, b):
        s.tokens = estimate_tokens(s.text)
    dups = find_duplicates([a, b], threshold=0.25)
    assert len(dups) == 1
    assert dups[0]["similarity"] > 0.9


def test_find_duplicates_ignores_unrelated_sections():
    a = split_sections("## A\n" + "alpha beta gamma delta " * 20, "one.md")[0]
    b = split_sections("## B\n" + "zulu yankee xray whiskey " * 20, "two.md")[0]
    for s in (a, b):
        s.tokens = estimate_tokens(s.text)
    assert find_duplicates([a, b], threshold=0.25) == []


def test_min_tokens_is_what_excludes_the_pair():
    # The pair must be genuinely near-identical, so the ONLY thing separating
    # the two assertions is min_tokens. The earlier version used two 6-token
    # bodies that shingled to Jaccard 0.0 — it passed for an unrelated reason
    # and left the filter untested.
    body = " ".join(f"shared policy clause {i} about branch hygiene" for i in range(6))
    a = split_sections(f"## A\n{body}\n", "one.md")[0]
    b = split_sections(f"## B\n{body}\n", "two.md")[0]
    for s in (a, b):
        s.tokens = estimate_tokens(s.text)
    assert 0 < a.tokens < 100, "fixture must sit between the two thresholds"
    assert find_duplicates([a, b], threshold=0.25, min_tokens=0), "should pair"
    assert find_duplicates([a, b], threshold=0.25, min_tokens=1000) == []


# --------------------------------------------------------------- contradiction


def test_finds_the_articles_own_contradiction():
    secs = split_sections(
        "## Comments\nNever add documentation comments to generated modules.\n"
        "## Style\nLeave documentation comments as appropriate for the reader.\n",
        "f.md",
    )
    hits = find_contradictions(secs)
    assert "documentation" in {c["topic"] for c in hits}


def test_mandate_counts_as_the_hard_side_of_a_contradiction():
    # A mandate colliding with a permission is as real a conflict as a
    # prohibition colliding with one; both must pair.
    secs = split_sections(
        "## A\nEvery migration must include a rollback script.\n"
        "## B\nInclude a rollback script for migrations as appropriate.\n",
        "f.md",
    )
    hits = find_contradictions(secs)
    assert "rollback" in {c["topic"] for c in hits}
    assert {c["hard"]["polarity"] for c in hits} == {"mandate"}


def test_contradiction_inside_one_section_still_counts_but_is_flagged():
    # The article's own example is a LOCAL collision. Excluding same-section
    # pairs also made prompt mode (one section) permanently blind.
    secs = split_sections(
        "## Both\nNever add documentation here. Leave documentation as appropriate.\n",
        "f.md",
    )
    hits = find_contradictions(secs)
    assert "documentation" in {c["topic"] for c in hits}
    assert all(c["same_section"] for c in hits)


def test_cross_section_collisions_rank_above_local_ones():
    secs = split_sections(
        "## A\nNever use the legacy exporter for anything.\n"
        "## B\nUse the legacy exporter as appropriate.\n"
        "## C\nNever enable telemetry. Enable telemetry if needed.\n",
        "f.md",
    )
    hits = find_contradictions(secs)
    by_topic = {c["topic"]: c for c in hits}
    assert by_topic["exporter"]["same_section"] is False
    assert by_topic["telemetry"]["same_section"] is True
    # Cross-section pairs sort first.
    assert hits.index(by_topic["exporter"]) < hits.index(by_topic["telemetry"])


def test_no_contradiction_when_polarities_agree():
    secs = split_sections(
        "## A\nNever add documentation comments.\n"
        "## B\nDo not add documentation comments either.\n",
        "f.md",
    )
    assert find_contradictions(secs) == []


def test_contradictions_report_one_row_per_topic():
    secs = split_sections(
        "## A\nNever use the deprecated migration helper here.\n"
        "## B\nUse the deprecated migration helper as appropriate.\n"
        "## C\nThe deprecated migration helper may be used if needed.\n",
        "f.md",
    )
    topics = [c["topic"] for c in find_contradictions(secs)]
    assert len(topics) == len(set(topics))


# ------------------------------------------------------------------ disclosure


def test_disclosure_none_when_under_threshold(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("short")
    assert disclosure_check(p, "short", 100, 2500) is None


def test_disclosure_flags_upfront_surface(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("body")
    d = disclosure_check(p, "body with no links at all", 5000, 2500)
    assert d is not None and d["defers"] is False


def test_disclosure_satisfied_by_references_dir(tmp_path):
    (tmp_path / "references").mkdir()
    p = tmp_path / "SKILL.md"
    p.write_text("body")
    d = disclosure_check(p, "body", 5000, 2500)
    assert d is not None and d["defers"] is True


def test_disclosure_satisfied_by_outbound_links(tmp_path):
    p = tmp_path / "CLAUDE.md"
    text = "see [a](a.md) and [b](docs/b.md) and [c](c.md)"
    p.write_text(text)
    d = disclosure_check(p, text, 5000, 2500)
    assert d is not None and d["defers"] is True


def test_docs_dir_alone_does_not_satisfy_disclosure(tmp_path):
    # Nearly every repo has docs/; counting it would make the check vacuous.
    (tmp_path / "docs").mkdir()
    p = tmp_path / "CLAUDE.md"
    p.write_text("body")
    d = disclosure_check(p, "body", 5000, 2500)
    assert d is not None and d["defers"] is False


def test_count_outbound_links_deduplicates():
    assert count_outbound_links("[a](x.md) and [again](x.md)") == 1


@pytest.mark.parametrize(
    "links,expected",
    [(0, False), (1, False), (2, False), (3, True), (4, True)],
)
def test_disclosure_link_threshold_is_pinned_either_side(tmp_path, links, expected):
    # Only 0 and 3 were exercised before, leaving 1 and 2 free to drift.
    p = tmp_path / "CLAUDE.md"
    text = " ".join(f"[d{i}](doc{i}.md)" for i in range(links))
    p.write_text(text)
    d = disclosure_check(p, text, 5000, 2500)
    assert d is not None and d["defers"] is expected


# ------------------------------------------------------------------- end-to-end


def test_audit_end_to_end(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "# Repo\n\n## Rules\nNever commit to main directly.\n"
        "## Style\nPrefer bun over npm for new projects.\n"
    )
    report = audit([str(tmp_path)], budget=100, repo_root=tmp_path)
    assert report["budget"]["actual"] > 0
    assert report["files"][0]["path"].endswith("CLAUDE.md")
    assert report["polarity_total"]["prohibition"] == 1
    assert report["polarity_total"]["judgment"] == 1
    assert report["rules_ratio"] == 0.5


def test_audit_walks_a_directory_for_known_surfaces(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# a\ntext here for the audit\n")
    nested = tmp_path / "sub"
    nested.mkdir()
    (nested / "SKILL.md").write_text("# b\nmore text here for the audit\n")
    (tmp_path / "README.md").write_text("# ignored\n")
    report = audit([str(tmp_path)], repo_root=tmp_path)
    names = {Path(f["path"]).name for f in report["files"]}
    assert names == {"CLAUDE.md", "SKILL.md"}


def test_audit_missing_path_raises():
    with pytest.raises(FileNotFoundError):
        audit(["/nonexistent/path/xyz"])


def test_audit_prompt_reports_without_budget():
    report = audit_prompt("Never do X here. Prefer Y instead of Z always.")
    assert "budget" not in report
    assert report["tokens"] > 0
    assert report["rules_ratio"] > 0


def test_estimate_tokens_monotonic():
    assert estimate_tokens("word " * 100) > estimate_tokens("word " * 10)


def test_fallback_estimator_constant_is_pinned(monkeypatch):
    """The no-tiktoken path is a CI job; nothing pinned its constant.

    Monotonicity holds for any length-proportional estimator, so a 4x-wrong
    constant passed the whole suite.
    """
    import context_audit as ca

    monkeypatch.setitem(sys.modules, "tiktoken", None)
    assert ca.tokenizer_name().startswith("estimate")
    assert ca.estimate_tokens("x" * 4100) == 1000
    # And the constant stays inside the band the docstring claims.
    assert 3.6 <= ca._CHARS_PER_TOKEN <= 4.6
