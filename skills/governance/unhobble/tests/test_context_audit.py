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
        "The script must exit non-zero on a missing path.",
        "This always renders the disclaimer at the end.",
        "The hook never fires on read-only tools.",
    ],
)
def test_third_person_description_is_not_a_directive(sentence):
    assert classify_sentence(sentence) == "descriptive"


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
    text = "Never do X here. You must do Y always. Prefer Z over W."
    counts, dominant = polarity_profile(text)
    assert counts["prohibition"] == 1
    assert counts["mandate"] == 1
    assert counts["judgment"] == 1
    assert dominant in {"prohibition", "mandate", "judgment"}


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


def test_find_duplicates_skips_tiny_sections():
    a = split_sections("## A\nsame short text\n", "one.md")[0]
    b = split_sections("## B\nsame short text\n", "two.md")[0]
    for s in (a, b):
        s.tokens = estimate_tokens(s.text)
    assert find_duplicates([a, b], threshold=0.25, min_tokens=40) == []


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


def test_contradiction_requires_two_different_sections():
    secs = split_sections(
        "## Both\nNever add documentation here. Leave documentation as appropriate.\n",
        "f.md",
    )
    assert find_contradictions(secs) == []


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
