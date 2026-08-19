"""Tests for format_lint.

Two invariants this suite must actually hold (an earlier version claimed the first and
did not have it, which a cross-model review caught):

1. EVERY rule has both polarities — a realistic positive and a plausible adjacent
   negative. A suite that only proves firing cannot distinguish a working linter from
   one that flags everything.
2. Severity follows the ledger GRADE. Only `refuted` may ERROR; `unverified` must not,
   because "I could not find a source" is a claim about a search, not about the world.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import format_lint as fl  # noqa: E402

LEDGER = fl.load_ledger()
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "format_lint.py"
RULES = LEDGER["refuted"] + LEDGER["folklore"] + LEDGER["hypothesis_as_fact"]


def ids(text):
    return {f["id"] for f in fl.lint_text(text, LEDGER)}


def find(text, rid):
    return [f for f in fl.lint_text(text, LEDGER) if f["id"] == rid]


# ---------- ledger integrity ----------

def test_every_rule_is_graded():
    valid = set(fl.GRADE_SEVERITY)
    for r in RULES:
        assert r.get("grade") in valid, f"{r['id']} has no valid grade"


def test_every_rule_has_message_pattern_and_instead():
    for r in RULES:
        assert r["id"] and r["pattern"] and r["message"]
        assert r.get("instead"), f"{r['id']} lacks corrective guidance"


def test_only_refuted_is_error():
    for r in RULES:
        sev = fl.GRADE_SEVERITY[r["grade"]]
        assert (sev == "ERROR") == (r["grade"] == "refuted"), r["id"]


def test_citation_markers_are_resolvable_forms_only():
    """A self-authored tag like [HIGH] is not a source. Regression on a real finding."""
    for mk in LEDGER["precision_without_source"]["citation_markers"]:
        assert any(t in mk for t in ("http", "doi", "arxiv", "pubmed", "PMC")), mk


# ---------- POSITIVE + NEGATIVE for every rule ----------

POS_NEG = {
    "sends-3-5x-likes": (
        "Sends are weighted 3-5x more than likes on Reels.",
        "Send the newsletter 3-5x per month to your list.",
    ),
    "polished-aesthetic-dead": (
        "Mosseri announced the polished, perfect aesthetic is dead.",
        "The polished aesthetic is still what most brands ship.",
    ),
    "bornstein-208-studies": (
        "A meta-analysis of 208 studies found the effect robust.",
        "The review covered 134 studies reporting 208 contrasts.",
    ),
    "mere-exposure-r-026": (
        "The pooled effect was r = .26 across the literature.",
        "The pooled effect was r = .265 in the newer sample.",
    ),
    "subliminal-stronger": (
        "Subliminal exposure produces stronger effects than conscious exposure.",
        "Subliminal exposure was measured under flash suppression.",
    ),
    "algorithm-favorites-list": (
        "The algorithm keeps a favorites list of formats it rewards.",
        "Add the creator to your Instagram Favorites feed to see them first.",
    ),
    "three-second-hook": (
        "You must nail the first 3 seconds hook or you lose them.",
        "The opening shot sets up the rest of the piece.",
    ),
    "post-daily": (
        "Posting every day is how you grow reach.",
        "Posting every day burned me out and changed nothing.",
    ),
    "algorithm-punishes": (
        "The algorithm punishes accounts that go quiet.",
        "The recommender scores each item by predicted engagement.",
    ),
    "embedding-variance-asserted": (
        "Format consistency lowers embedding variance and lifts retrieval.",
        "We reduced embedding variance in our retrieval benchmark by tuning the loss.",
    ),
    "pollutes-embeddings": (
        "A mismatched viral hit pollutes your embeddings for months.",
        "Adversarial actors can poison embeddings in a shared vector index.",
    ),
}


def test_every_rule_has_a_polarity_fixture():
    assert set(POS_NEG) == {r["id"] for r in RULES}, "a rule is missing its fixture pair"


def test_positives_fire():
    for rid, (pos, _) in POS_NEG.items():
        assert rid in ids(pos), f"{rid} did not fire on its positive: {pos!r}"


def test_negatives_stay_quiet():
    for rid, (_, neg) in POS_NEG.items():
        assert rid not in ids(neg), f"{rid} over-matched its negative control: {neg!r}"


# ---------- negation guard ----------

NEGATED = [
    "Sends are not weighted 3-5x more than likes; that claim is unfounded.",
    "It is a myth that the algorithm punishes accounts that go quiet.",
    "Posting every day is not how you grow reach.",
    "The claim that the polished, perfect aesthetic is dead is a misquotation.",
]


def test_corrections_do_not_fire():
    """The linter must not punish the very corrections it exists to promote."""
    for text in NEGATED:
        assert fl.lint_text(text, LEDGER) == [], f"fired on a correction: {text!r}"


# ---------- exemptions, and their bypasses ----------

def test_fenced_block_is_skipped():
    assert "sends-3-5x-likes" not in ids("x\n```\nSends are 3-5x more than likes.\n```\ny\n")


def test_unclosed_fence_is_reported():
    assert "unclosed-fence" in ids("```\nSends are 3-5x more than likes.\n")


def test_wellformed_frontmatter_is_exempt():
    text = "---\nname: x\ndescription: triggers on 'is the algorithm punishing me'\n---\nBody.\n"
    assert "algorithm-punishes" not in ids(text)


def test_horizontal_rule_is_not_frontmatter():
    """A leading `---` with no closing marker must NOT exempt the whole document."""
    text = "---\n\nThe algorithm punishes quiet accounts.\n"
    assert "algorithm-punishes" in ids(text)


def test_frontmatter_needs_a_key_line():
    text = "---\njust prose, no keys\n---\nThe algorithm punishes quiet accounts.\n"
    assert "algorithm-punishes" in ids(text)


def test_frontmatter_exemption_does_not_leak_into_body():
    assert "algorithm-punishes" in ids("---\nname: x\n---\nThe algorithm punishes you.\n")


def test_inline_allow_suppresses_only_that_line():
    text = "Sends are 3-5x likes. <!-- format-lint: allow=sends-3-5x-likes -->\n"
    assert "sends-3-5x-likes" not in ids(text)


def test_allow_marker_does_not_bleed_to_next_line():
    """One marker must not excuse two separate assertions."""
    text = (
        "Sends are 3-5x likes. <!-- format-lint: allow=sends-3-5x-likes -->\n"
        "Sends are weighted 3-5x more than likes again.\n"
    )
    assert len(find(text, "sends-3-5x-likes")) == 1


def test_allow_marker_only_suppresses_named_rule():
    text = (
        "Sends are 3-5x likes and a meta-analysis of 208 studies agrees. "
        "<!-- format-lint: allow=sends-3-5x-likes -->\n"
    )
    found = ids(text)
    assert "sends-3-5x-likes" not in found
    assert "bornstein-208-studies" in found


def test_disable_region_works_and_resumes():
    text = (
        "intro\n<!-- format-lint: disable -->\nSends are 3-5x likes.\n"
        "<!-- format-lint: enable -->\nA meta-analysis of 208 studies.\n"
    )
    found = ids(text)
    assert "sends-3-5x-likes" not in found
    assert "bornstein-208-studies" in found


def test_unclosed_disable_is_an_error():
    assert "unclosed-disable" in ids("<!-- format-lint: disable -->\nSends are 3-5x likes.\n")


def test_nested_disable_is_an_error():
    text = (
        "<!-- format-lint: disable -->\na\n<!-- format-lint: disable -->\nb\n"
        "<!-- format-lint: enable -->\nc\n"
    )
    assert "nested-disable" in ids(text)


def test_whole_file_disable_is_an_error():
    """A CLOSED region covering the document is still a total bypass."""
    body = "\n".join(f"Sends are 3-5x likes line {i}." for i in range(12))
    text = f"<!-- format-lint: disable -->\n{body}\n<!-- format-lint: enable -->\n"
    assert "whole-file-disable" in ids(text)


def test_control_must_be_a_standalone_comment():
    """Prose mentioning the directive must not switch the linter off."""
    text = "You can write format-lint: disable to suppress.\nSends are 3-5x likes.\n"
    assert "sends-3-5x-likes" in ids(text)


# ---------- precision without source ----------

def test_unsourced_precision_fires():
    assert "unsourced-precision" in ids("Completion sits at 45% for most creators.\n")


def test_precision_with_url_is_quiet():
    assert "unsourced-precision" not in ids("Completion is 45%.\nhttps://example.org/p\n")


def test_self_authored_tag_is_not_a_source():
    """[HIGH] and 'verbatim' are the author's own assertion, not a citation."""
    assert "unsourced-precision" in ids("Median attention is 82% [HIGH] verified by grep.\n")


def test_grouped_numerals_are_matched_whole():
    f = find("The study covered 1,200 participants.\n", "unsourced-precision")
    assert f and "1,200" in f[0]["matched"]


def test_numbered_list_item_is_not_a_citation_marker():
    assert "unsourced-precision" in ids("10. Completion sits at 45% for creators.\n")


# ---------- severity + CLI ----------

def test_unverified_is_warn_not_error():
    f = find("Sends are weighted 3-5x more than likes.", "sends-3-5x-likes")[0]
    assert f["grade"] == "unverified" and f["severity"] == "WARN"


def test_refuted_is_error():
    f = find("Mosseri announced the polished, perfect aesthetic is dead.", "polished-aesthetic-dead")[0]
    assert f["severity"] == "ERROR"


def _run(tmp_path, text, *extra):
    p = tmp_path / "d.md"
    p.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), str(p), *extra],
                          capture_output=True, text=True)


def test_cli_exit_1_on_error(tmp_path):
    r = _run(tmp_path, "Mosseri announced the polished, perfect aesthetic is dead.\n")
    assert r.returncode == 1


def test_cli_exit_0_on_warn_but_1_under_strict(tmp_path):
    warn = "Sends are weighted 3-5x more than likes.\n"
    assert _run(tmp_path, warn).returncode == 0
    assert _run(tmp_path, warn, "--strict").returncode == 1


def test_cli_exit_0_on_clean(tmp_path):
    assert _run(tmp_path, "Pick a format and repeat it.\n").returncode == 0


def test_cli_json_shape(tmp_path):
    r = _run(tmp_path, "A meta-analysis of 208 studies.\n", "--json")
    (findings,) = json.loads(r.stdout).values()
    assert findings[0]["id"] == "bornstein-208-studies"
    assert findings[0]["grade"] == "contested"


def test_cli_missing_file_exits_2(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "nope.md")],
                       capture_output=True, text=True)
    assert r.returncode == 2


# ---------- round-2 review regressions ----------

def test_unrelated_negation_earlier_in_line_does_not_suppress():
    """Regression: a line-scoped guard let 'This is not complicated.' excuse a live claim."""
    text = "This is not complicated. Sends are weighted 3-5x more than likes.\n"
    assert "sends-3-5x-likes" in ids(text)


def test_negation_in_the_same_sentence_still_suppresses():
    assert "sends-3-5x-likes" not in ids("Sends are not weighted 3-5x more than likes.\n")


def test_unknown_grade_fails_loudly(tmp_path):
    """A typo in a grade must not silently downgrade an ERROR to WARN."""
    import copy
    bad = copy.deepcopy(LEDGER)
    bad["refuted"][0]["grade"] = "refutde"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    try:
        fl.load_ledger(p)
    except SystemExit as e:
        assert "unknown grade" in str(e)
    else:
        raise AssertionError("bad grade was accepted")


def test_malformed_r_value_does_not_match():
    assert "mere-exposure-r-026" not in ids("The coefficient was r=026 in the table.\n")


def test_instagram_favorites_feed_is_not_flagged():
    assert "algorithm-favorites-list" not in ids("Add them to your Instagram Favorites list.\n")


def test_algorithm_favorites_list_of_formats_still_flags():
    assert "algorithm-favorites-list" in ids("The algorithm's secret favorites list decides reach.\n")


def test_unicode_multiplication_sign_matches():
    assert "sends-3-5x-likes" in ids("Sends are weighted 3–5× more than likes.\n")


def test_tilde_fence_is_exempt_and_unclosed_is_reported():
    assert "sends-3-5x-likes" not in ids("~~~\nSends are 3-5x more than likes.\n~~~\n")
    assert "unclosed-fence" in ids("~~~\nSends are 3-5x more than likes.\n")


def test_directive_inside_a_fence_does_not_control_the_linter():
    """Documenting the directive must not switch the gate off for live prose."""
    text = (
        "```\n<!-- format-lint: disable -->\n```\n"
        "Mosseri announced the polished, perfect aesthetic is dead.\n"
    )
    assert "polished-aesthetic-dead" in ids(text)


def test_short_whole_file_disable_is_still_an_error():
    """The coverage guard previously exempted files under six lines."""
    text = "<!-- format-lint: disable -->\nSends are 3-5x likes.\n<!-- format-lint: enable -->\n"
    assert "whole-file-disable" in ids(text)


def test_bare_scheme_is_not_a_citation():
    assert "unsourced-precision" in ids("Completion is 45%.\nsee https:// for details\n")


def test_bare_pmc_substring_is_not_a_citation():
    assert "unsourced-precision" in ids("Completion is 45%.\nPMC has it somewhere\n")


def test_resolvable_doi_is_a_citation():
    assert "unsourced-precision" not in ids("Completion is 45%.\nhttps://doi.org/10.1145/3613904.3642433\n")


# ---------- dogfood regressions (found by running the linter on a real article) ----------

def test_claim_wrapped_across_lines_is_caught():
    """Real markdown hard-wraps. A per-line matcher missed the exact fabrication this
    linter exists to catch, on the very article it was traced to."""
    text = (
        "Sends per reach is the strongest signal for new audiences, with sends\n"
        "carrying roughly three to five times more weight than likes when ranking.\n"
    )
    assert "sends-3-5x-likes" in ids(text)


def test_wrapping_does_not_join_across_a_blank_line():
    """Paragraph joining must stop at blank lines, or unrelated sentences fuse."""
    text = "Sends are important and so are\n\nthree to five times more likes.\n"
    assert "sends-3-5x-likes" not in ids(text)


def test_marker_comment_does_not_match_itself():
    """A rule id like `sends-3-5x-likes` contains the pattern it names."""
    text = "Nothing to see here. <!-- format-lint: allow=sends-3-5x-likes -->\n"
    assert fl.lint_text(text, LEDGER) == []


def test_hook_variant_first_one_to_three_seconds():
    assert "three-second-hook" in ids("Lead with a strong hook in the first one to three seconds.\n")


def test_reported_line_is_where_the_claim_starts():
    text = "intro line\nSends carrying roughly three to five\ntimes more weight than likes.\n"
    f = find(text, "sends-3-5x-likes")
    assert f and f[0]["line"] == 2


# ---------- markdown structural boundaries (round-3 blocker) ----------

def test_adjacent_list_items_do_not_fuse():
    """`- polished aesthetic` + `- minimalism is dead` must not read as one claim."""
    text = "- Embrace a polished aesthetic\n- Minimalism is dead\n"
    assert "polished-aesthetic-dead" not in ids(text)


def test_negation_in_one_bullet_does_not_excuse_the_next():
    text = "- This is not a myth\n- The algorithm punishes quiet accounts\n"
    assert "algorithm-punishes" in ids(text)


def test_heading_does_not_fuse_with_following_prose():
    text = "## The polished aesthetic\nis dead, some say.\n"
    assert "polished-aesthetic-dead" not in ids(text)


def test_table_rows_do_not_fuse():
    text = "| a | polished aesthetic |\n| b | is dead |\n"
    assert "polished-aesthetic-dead" not in ids(text)


def test_wrapped_prose_still_joins_after_structural_fix():
    """The structural boundary must not undo the wrapped-prose fix."""
    text = (
        "Sends per reach is the strongest signal, with sends carrying roughly three to five\n"
        "times more weight than likes when ranking.\n"
    )
    assert "sends-3-5x-likes" in ids(text)


def test_numbered_list_items_do_not_fuse():
    text = "1. Embrace a polished aesthetic\n2. Minimalism is dead\n"
    assert "polished-aesthetic-dead" not in ids(text)


# ---------- fence delimiters (round-4: a fence is a char AND a length) ----------

def test_inner_shorter_fence_does_not_close_an_outer_fence():
    """A ```` block quoting ``` must stay exempt to its real end.

    Tracking only "starts with ``` " closed the block at the inner line, so everything
    after it was linted as prose while the author believed it was quoted.
    """
    text = (
        "````\n"
        "```\n"
        "Sends are 3-5x more than likes.\n"
        "```\n"
        "````\n"
        "Live prose: sends are 3-5x more than likes.\n"
    )
    hits = find(text, "sends-3-5x-likes")
    assert len(hits) == 1, "only the line outside the ```` block may fire"
    assert hits[0]["line"] == 6


def test_a_tilde_run_cannot_close_a_backtick_fence():
    text = "```\nSends are 3-5x more than likes.\n~~~\n"
    got = ids(text)
    assert "unclosed-fence" in got
    assert "sends-3-5x-likes" not in got


def test_a_closing_run_must_be_at_least_as_long_as_the_opener():
    text = "````\nSends are 3-5x more than likes.\n```\n"
    assert "unclosed-fence" in ids(text)


def test_a_run_with_an_info_string_does_not_close():
    text = "```\nSends are 3-5x more than likes.\n```python\n"
    assert "unclosed-fence" in ids(text)


def test_unclosed_fence_reports_the_delimiter_it_saw():
    assert find("~~~~\nSends are 3-5x likes.\n", "unclosed-fence")[0]["matched"] == "~~~~"
    assert find("```\nSends are 3-5x likes.\n", "unclosed-fence")[0]["matched"] == "```"


def test_a_backtick_run_with_backticks_after_it_is_prose_not_a_fence():
    """CommonMark: a backtick opener's info string may not contain a backtick."""
    text = "```code``` — sends are 3-5x more than likes.\n"
    assert "sends-3-5x-likes" in ids(text)


def test_indented_fence_up_to_three_spaces_still_opens():
    assert "sends-3-5x-likes" not in ids("   ```\n   Sends are 3-5x likes.\n   ```\n")


def test_a_deeply_indented_fence_inside_a_list_is_still_a_fence():
    """CommonMark caps fence indent at 3 spaces; a fence nested in a list exceeds that.

    Mutation testing caught this: bounding the indent to {0,3} changed no test, i.e. the
    bound was unproven either way. For a gate that ERRORs, linting quoted code as prose is
    the worse failure, so indentation is unbounded and that choice is now pinned.
    """
    text = "- item\n\n      ```\n      Sends are 3-5x more than likes.\n      ```\n"
    assert "sends-3-5x-likes" not in ids(text)


# ---------- paraphrase coverage (round-4) ----------
# Every widening below was a documented known-open: the claim was made in different words
# and passed clean. Each positive is paired with an adjacent negative, because a widened
# pattern is exactly where a fix opens the next defect.

def test_anthropomorphic_verbs_beyond_punish_are_caught():
    for verb in ("demotes", "suppresses", "throttles", "shadowbans", "buries",
                 "deprioritises", "penalises"):
        assert "algorithm-punishes" in ids(f"The algorithm {verb} inconsistent formats.\n"), verb


def test_a_documented_demotion_can_still_be_written_with_attribution():
    """Instagram's originality gate IS a real demotion — the negation guard must let it through."""
    text = "Instagram claims that its algorithm demotes primarily non-original accounts.\n"
    assert "algorithm-punishes" not in ids(text)


def test_a_neutral_ranking_sentence_does_not_trip_the_widened_verbs():
    assert "algorithm-punishes" not in ids(
        "Ranking is a weighted sum; a low predicted value simply loses the auction.\n"
    )


def test_cadence_folklore_in_other_phrasings():
    for phrasing in ("Posting each day is how you grow.",
                     "Posting every single day drives reach.",
                     "Posting seven days a week feeds the algorithm."):
        assert "post-daily" in ids(phrasing + "\n"), phrasing


def test_a_cadence_sentence_without_a_growth_claim_is_clean():
    assert "post-daily" not in ids("I post daily because I enjoy it.\n")


def test_variance_hypothesis_in_other_verbs():
    for verb in ("shrinks", "narrows", "tightens", "compresses", "decreases"):
        assert "embedding-variance-asserted" in ids(
            f"Format consistency {verb} item embedding variance.\n"
        ), verb


def test_variance_sentence_labelled_as_hypothesis_is_clean():
    assert "embedding-variance-asserted" not in ids(
        "It is not established that format consistency reduces embedding variance.\n"
    )


def test_word_form_multipliers_count_as_precision():
    assert "unsourced-precision" in ids("Sends carry a fivefold weighting.\n")


def test_a_cited_word_form_multiplier_is_clean():
    text = (
        "Sends carry a fivefold weighting.\n"
        "Source: https://doi.org/10.1145/3613904.3642433\n"
    )
    assert "unsourced-precision" not in ids(text)


def test_the_enumeration_idiom_is_not_a_multiplier():
    """"The problem is threefold:" enumerates; it does not measure.

    The first version of the word-form widening fired on exactly this, twice in a
    3327-file sweep — 2 of its 3 new hits were this idiom. See scripts/corpus_sweep.py.
    """
    for idiom in ("The non-tautological content is threefold: (i) one, (ii) two.",
                  "Your job is twofold: bootstrap, then maintain.",
                  "The benefit here is fivefold and hard to summarise."):
        assert "unsourced-precision" not in ids(idiom + "\n"), idiom


def test_a_multiplier_in_a_measurement_context_still_fires():
    for claim in ("Sends carry a fivefold weighting.",
                  "Carousels get a threefold increase in reach.",
                  "Consistency boosts reach by fourfold."):
        assert "unsourced-precision" in ids(claim + "\n"), claim


# ---------- frontmatter / fence ordering (round-4, found by edge probing) ----------

def test_a_fence_inside_frontmatter_does_not_swallow_the_document():
    """The worst failure this gate has: a silent FALSE NEGATIVE on a live claim.

    A bare ``` in a YAML value opened a fence that no `---` could close, so every line
    after the frontmatter was exempt and the document came back clean.
    """
    text = (
        "---\nname: x\nexample:\n  ```\n---\n"
        "Mosseri said the polished, perfect aesthetic is dead.\n"
    )
    got = ids(text)
    assert "polished-aesthetic-dead" in got, "the live claim after frontmatter must fire"
    assert "unclosed-fence" not in got, "a ``` inside frontmatter is a value, not a fence"


def test_a_real_fence_after_frontmatter_still_exempts():
    text = (
        "---\nname: x\n---\n"
        "```\nMosseri said the polished, perfect aesthetic is dead.\n```\n"
    )
    assert "polished-aesthetic-dead" not in ids(text)


def test_an_unclosed_fence_after_frontmatter_is_still_reported():
    text = "---\nname: x\n---\n```\nMosseri said the polished, perfect aesthetic is dead.\n"
    assert "unclosed-fence" in ids(text)


def test_a_malformed_document_fails_loudly_rather_than_silently():
    """An unclosed fence swallowing an enable directive must not read as a clean file."""
    text = (
        "<!-- format-lint: disable -->\n```\nquoted\n<!-- format-lint: enable -->\n"
        "Mosseri said the polished, perfect aesthetic is dead.\n"
    )
    findings = fl.lint_text(text, LEDGER)
    assert any(f["severity"] == "ERROR" for f in findings), "silence here would hide a claim"


def test_crlf_input_behaves_identically_to_lf():
    dirty = "Mosseri said the polished, perfect aesthetic is dead."
    assert ids(dirty + "\r\n") == ids(dirty + "\n")
    assert ids("```\r\n" + dirty + "\r\n```\r\n") == ids("```\n" + dirty + "\n```\n")
    assert "unclosed-fence" in ids("```\r\n" + dirty + "\r\n")


def test_a_closer_with_trailing_whitespace_still_closes():
    dirty = "Mosseri said the polished, perfect aesthetic is dead."
    assert "unclosed-fence" not in ids("```\n" + dirty + "\n```   \n")


def test_cadence_folklore_in_the_past_tense():
    """"...is how the account grew" is the same claim; only the tense differed."""
    for phrasing in ("Posting each day is how the account grew.",
                     "The account grew because I was posting every day."):
        assert "post-daily" in ids(phrasing + "\n"), phrasing


def test_past_tense_widening_does_not_flag_an_unrelated_growth_sentence():
    assert "post-daily" not in ids("The account grew after I switched to one format.\n")


# ---------- citation suppression (round-4, found by the cross-model reviewer) ----------

def test_a_cited_attributed_true_claim_does_not_read_as_folklore():
    """The reviewer's counter-example: this sentence is true, sourced, and was flagged.

    A WARN-grade rule asserts "this circulates with no located source". Supplying the
    source is the correction the rule's own `instead` asks for.
    """
    text = (
        "According to Instagram, its algorithm demotes primarily non-original accounts:\n"
        "https://about.instagram.com/blog/announcements/original-content\n"
    )
    assert "algorithm-punishes" not in ids(text)


def test_the_same_claim_without_a_citation_still_fires():
    assert "algorithm-punishes" in ids("The algorithm demotes accounts that switch formats.\n")


def test_a_citation_does_not_suppress_a_refuted_claim():
    """A misquotation with a link attached is still a misquotation — ERROR must survive."""
    text = (
        "Mosseri said the polished, perfect aesthetic is dead.\n"
        "Source: https://www.threads.net/@mosseri/post/abc\n"
    )
    hits = find(text, "polished-aesthetic-dead")
    assert hits and hits[0]["severity"] == "ERROR"


def test_citation_suppression_reaches_across_a_hard_wrap():
    text = (
        "Posting each day is how the\n"
        "account grew.\n"
        "See https://example.com/study/12345\n"
    )
    assert "post-daily" not in ids(text)


def test_an_unresolvable_marker_does_not_suppress():
    """"https://" alone or a bare "PMC" is not a citation — that is the marker_regex's job."""
    assert "algorithm-punishes" in ids(
        "The algorithm demotes inconsistent formats. Source: https://\n"
    )


def test_a_url_in_a_different_paragraph_does_not_suppress():
    """Block-scoped, not line-windowed.

    A +/-3-line window let a URL in a different paragraph — even one ABOVE the claim —
    silence it, which turns "cite your source" into "put a link somewhere nearby".
    """
    for text in (
        "The algorithm punishes inconsistent formats.\n\nSee my portfolio: https://example.com/about\n",
        "The algorithm punishes inconsistent formats.\n\n- Follow me: https://example.com/me\n",
        "Read more at https://example.com/x\n\nThe algorithm punishes inconsistent formats.\n",
    ):
        assert "algorithm-punishes" in ids(text), text


def test_precision_rule_keeps_its_own_line_window():
    """The precision rule's +/-3-line window is unchanged; only claim rules were narrowed."""
    text = "Reels get a threefold increase in reach.\n\nSource: https://doi.org/10.1145/3613904.3642433\n"
    assert "unsourced-precision" not in ids(text)
