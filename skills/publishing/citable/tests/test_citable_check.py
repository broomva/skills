#!/usr/bin/env python3
"""Tests for citable_check.

Every check gets both arms: a case that must trip it and a case that must not.
A gate only tested on the failing side can be vacuously strict; one only tested
on the passing side can be inert. Both directions or it proves nothing.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import citable_check as cc  # noqa: E402

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "citable_check.py"


def statuses(text, surface="prose", entities=None):
    rep = cc.run(text, surface, entities or [])
    return {c.name: c.status for c in rep.checks}


def detail(text, name, surface="prose", entities=None):
    rep = cc.run(text, surface, entities or [])
    return next(c.detail for c in rep.checks if c.name == name)


# ── math-alpha unicode ───────────────────────────────────────────────────────

def test_math_alpha_fails():
    # U+1D5D7 etc — the fake-bold range LinkedIn authors use.
    assert statuses("\U0001D5D7\U0001D5EE\U0001D601\U0001D5EE Leader at Acme")["math-alpha-unicode"] == "FAIL"


def test_plain_text_passes():
    assert statuses("Data Leader at Acme")["math-alpha-unicode"] == "PASS"


def test_accented_latin_is_not_math_alpha():
    """Bogotá must not trip the unicode check — a false positive here would
    push authors to strip legitimate Spanish orthography."""
    assert statuses("Based in Bogotá and working remotely")["math-alpha-unicode"] == "PASS"


def test_emoji_is_not_math_alpha():
    assert statuses("Shipping it 🚀 today")["math-alpha-unicode"] == "PASS"


# ── length budgets ───────────────────────────────────────────────────────────

def test_headline_over_limit_fails():
    assert statuses("x" * 221, surface="headline")["length"] == "FAIL"


def test_headline_at_limit_passes():
    assert statuses("x" * 220, surface="headline")["length"] == "PASS"


def test_services_under_minimum_fails():
    assert statuses("too short", surface="services")["length"] == "FAIL"


def test_article_under_target_fails():
    assert statuses(" ".join(["word"] * 100), surface="article")["length"] == "FAIL"


def test_article_in_range_passes():
    assert statuses(" ".join(["word"] * 900), surface="article")["length"] == "PASS"


def test_post_over_word_budget_fails():
    assert statuses(" ".join(["word"] * 400), surface="post")["length"] == "FAIL"


def test_prose_skips_length():
    assert statuses("anything at all")["length"] == "SKIP"


# ── technical specificity ────────────────────────────────────────────────────

def test_no_numbers_fails():
    assert statuses("AI is transforming how we think about data pipelines.")["technical-specificity"] == "FAIL"


def test_dense_numbers_pass():
    text = ("After running 200 Airflow DAGs we saw 3 failure modes, "
            "with p95 latency at 240ms and a 12% error rate.")
    assert statuses(text)["technical-specificity"] == "PASS"


# ── named entities ───────────────────────────────────────────────────────────

def test_expected_entities_found():
    text = "We compared Notion versus Linear versus Asana for teams over 50."
    assert statuses(text, entities=["Notion", "Linear", "Asana"])["named-entities"] == "PASS"


def test_missing_expected_entities_warns():
    text = "There are several great project management tools on the market."
    assert statuses(text, entities=["Notion", "Linear", "Asana"])["named-entities"] == "WARN"


def test_entity_autodetect_without_list():
    text = "We run Databricks and Azure behind a Rust service."
    assert statuses(text)["named-entities"] == "PASS"


# ── link in comments ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "Link in comments.",
    "the link is in the first comment",
    "See comments for the link",
    "Enlace en los comentarios",
])
def test_link_in_comments_variants_warn(phrase):
    assert statuses(phrase)["link-in-comments"] == "WARN"


def test_self_contained_post_passes():
    assert statuses("Here is the whole argument, in the post.")["link-in-comments"] == "PASS"


# ── FAQ shape ────────────────────────────────────────────────────────────────

def test_faq_heading_warns():
    assert statuses("## Q: what is this?\nAn answer.")["faq-structure"] == "WARN"


def test_normal_heading_passes():
    assert statuses("## What actually worked\nThree things.")["faq-structure"] == "PASS"


# ── AI tells ─────────────────────────────────────────────────────────────────

def test_em_dashes_flagged():
    text = "This — that — the other — again — more — still — yet — on."
    assert statuses(text)["ai-tells"] == "FAIL"


def test_no_em_dashes_passes():
    assert statuses("This, that, and the other.")["ai-tells"] == "PASS"


def test_sparse_em_dash_warns_not_fails():
    text = "One em dash — here." + " word" * 900
    assert statuses(text)["ai-tells"] == "WARN"


# ── exit codes and CLI ───────────────────────────────────────────────────────

def test_clean_text_exits_zero(tmp_path):
    f = tmp_path / "ok.txt"
    f.write_text("We ran 200 Airflow DAGs on Databricks with Rust tooling and saw 3 failures.")
    r = subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_dirty_text_exits_one(tmp_path):
    f = tmp_path / "bad.txt"
    f.write_text("\U0001D5D7\U0001D5EE\U0001D601\U0001D5EE Leader, no specifics here at all.")
    r = subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True)
    assert r.returncode == 1


def test_stdin_is_accepted():
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--surface", "prose"],
        input="We shipped 3 fixes across 2 repos using Rust and Databricks.",
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_json_output_is_valid(tmp_path):
    import json
    f = tmp_path / "x.txt"
    f.write_text("We ran 12 tests on Rust and Databricks pipelines.")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), str(f), "--json"], capture_output=True, text=True
    )
    payload = json.loads(r.stdout)
    assert payload["surface"] == "prose"
    assert {c["name"] for c in payload["checks"]} >= {"math-alpha-unicode", "ai-tells"}


def test_empty_input_is_usage_error(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("   \n")
    r = subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True)
    assert r.returncode == 2


def test_missing_file_is_usage_error():
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "/nonexistent/nope.txt"], capture_output=True, text=True
    )
    assert r.returncode == 2


# ── effect provenance ────────────────────────────────────────────────────────

def test_effects_carry_a_source():
    """Every quantified effect must name the study. A number without provenance
    is exactly the failure mode this whole skill exists to prevent."""
    rep = cc.run("We ran 5 tests on Rust.", "prose", [])
    quantified = [c for c in rep.checks if "%" in c.effect]
    assert quantified, "expected at least one quantified effect"
    for c in quantified:
        assert "Scrunch" in c.effect or "Semrush" in c.effect, c


# ── regressions found by dogfooding the skill on real drafts ─────────────────

def test_headline_skips_specificity_density():
    """A 192-char headline carrying no digits is not a defect. Requiring one
    produced a false FAIL on a perfectly good headline."""
    hl = ("I build the control layer that makes coding agents safe to run "
          "unattended, Lead AI at Stimulus, control theory for autonomous software")
    assert statuses(hl, surface="headline")["technical-specificity"] == "SKIP"


def test_headline_still_fails_on_unicode():
    """The SKIP above must not make the headline surface permissive overall."""
    assert statuses("\U0001D5D7\U0001D5EE\U0001D601\U0001D5EE Leader", surface="headline")[
        "math-alpha-unicode"] == "FAIL"


def test_spelled_out_numbers_count_as_specificity():
    """'nine iterations, seven of them' is exactly as concrete as '9' and '7'.
    Counting only digits marked a real draft sparse when it was not."""
    text = ("Nine iterations, nine merged pull requests, and a second model found "
            "a blocking defect in seven of them. One review ran to twelve rounds.")
    assert statuses(text)["technical-specificity"] == "PASS"


def test_prose_with_no_quantities_still_fails():
    """The spelled-out fix must not make the check vacuous."""
    assert statuses("AI is transforming how we think about pipelines and teams.")[
        "technical-specificity"] == "FAIL"


def test_specificity_breakdown_is_reported():
    d = detail("We ran three tests and 4 builds.", "technical-specificity")
    assert "spelled-out" in d and "numeric" in d


# ── fixture pair: real content, both arms ────────────────────────────────────
#
# exemplar-article.md is an ACTUAL drafted article, not a string written to
# satisfy the assertion. If a future change to the linter starts rejecting real
# publishable content, this is what catches it. The degenerate counterpart
# guards the other direction, so neither arm can go vacuous alone.

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_exemplar_article_passes():
    text = (FIXTURES / "exemplar-article.md").read_text(encoding="utf-8")
    rep = cc.run(text, "article", ["Linear", "pytest", "Claude", "git", "CI"])
    failures = [c.name for c in rep.checks if c.status == "FAIL"]
    assert not failures, f"real publishable content was rejected: {failures}"


def test_degenerate_post_is_caught():
    text = (FIXTURES / "degenerate-post.md").read_text(encoding="utf-8")
    rep = cc.run(text, "prose", [])
    tripped = {c.name for c in rep.checks if c.status in ("FAIL", "WARN")}
    # Every anti-pattern this skill exists to catch is present in that fixture.
    assert {"math-alpha-unicode", "technical-specificity",
            "link-in-comments", "faq-structure"} <= tripped, tripped


def test_fixtures_disagree():
    """Guard against both fixtures drifting to the same verdict, which would
    make the pair prove nothing."""
    good = cc.run((FIXTURES / "exemplar-article.md").read_text(encoding="utf-8"), "article", [])
    bad = cc.run((FIXTURES / "degenerate-post.md").read_text(encoding="utf-8"), "prose", [])
    assert good.failed is False and bad.failed is True
