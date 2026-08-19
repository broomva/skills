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
