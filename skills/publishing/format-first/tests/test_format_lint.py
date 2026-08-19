"""Tests for format_lint.

Every rule gets BOTH polarities: a positive (the rule fires on the bad string) and a
negative control (the rule stays quiet on adjacent-but-legitimate text). A suite that
only proves firing cannot distinguish a working linter from one that flags everything.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import format_lint as fl  # noqa: E402

LEDGER = fl.load_ledger()
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "format_lint.py"


def ids(text):
    return {f["id"] for f in fl.lint_text(text, LEDGER)}


# ---------- ledger integrity ----------

def test_ledger_has_all_categories():
    for k in ("refuted", "folklore", "hypothesis_as_fact", "precision_without_source"):
        assert k in LEDGER, f"ledger missing {k}"
    assert len(LEDGER["refuted"]) >= 6


def test_every_rule_has_message_and_id():
    for cat in ("refuted", "folklore", "hypothesis_as_fact"):
        for rule in LEDGER[cat]:
            assert rule["id"] and rule["message"], f"incomplete rule in {cat}"
            assert "pattern" in rule


# ---------- positive: each refuted claim fires ----------

def test_sends_3_5x_fires():
    assert "sends-3-5x-likes" in ids("Sends are weighted 3-5x more than likes.")
    assert "sends-3-5x-likes" in ids("sends carry roughly three to five times more weight")


def test_polished_aesthetic_fires():
    assert "polished-aesthetic-dead" in ids("Mosseri said the polished, perfect aesthetic is dead.")


def test_208_studies_fires():
    assert "bornstein-208-studies" in ids("A meta-analysis of 208 studies found the effect robust.")


def test_r_026_fires():
    assert "mere-exposure-r-026" in ids("effect size of r = 0.26 across the literature")
    assert "mere-exposure-r-026" in ids("with r=.26 reported")


def test_subliminal_fires():
    assert "subliminal-stronger" in ids("Subliminal exposure produces stronger effects than conscious.")


def test_favorites_list_fires():
    assert "algorithm-favorites-list" in ids("The algorithm keeps a favorites list of formats.")


def test_folklore_fires():
    assert "three-second-hook" in ids("You must nail the first 3 seconds hook.")
    assert "post-daily" in ids("Posting every day is how you grow reach.")
    assert "algorithm-punishes" in ids("The algorithm punishes accounts that go quiet.")


def test_hypothesis_as_fact_fires():
    assert "embedding-variance-asserted" in ids(
        "Consistency lowers embedding variance, so retrieval improves."
    )
    assert "pollutes-embeddings" in ids("A mismatched hit pollutes your embeddings.")


# ---------- negative controls: adjacent-but-legitimate text stays quiet ----------

def test_clean_text_is_clean():
    clean = (
        "Choose a format rather than a topic.\n"
        "Repeat it, and rotate when engagement decays.\n"
        "Calibrate the hook to what the audience already knows.\n"
    )
    assert fl.lint_text(clean, LEDGER) == []


def test_correctly_stated_claims_do_not_fire():
    """The accurate phrasings must NOT trip their own rules — otherwise the linter
    punishes the very corrections it exists to promote."""
    ok = (
        "Mosseri says likes matter slightly more for connected reach.\n"
        "It is 134 studies reporting 208 contrasts.\n"
        "Repetition increases liking up to a point.\n"
    )
    found = ids(ok)
    assert "sends-3-5x-likes" not in found
    assert "bornstein-208-studies" not in found
    assert "mere-exposure-r-026" not in found


def test_hypothesis_labelled_as_hypothesis_still_flags():
    """Deliberate: the rule fires on the mechanism phrasing regardless of hedging,
    because the phrase itself is what propagates. The author resolves it by rewording."""
    assert "embedding-variance-asserted" in ids(
        "One hypothesis is that consistency lowers embedding variance."
    )


# ---------- fenced blocks are exempt ----------

def test_fenced_block_is_skipped():
    text = "Do not write this:\n```\nSends are weighted 3-5x more than likes.\n```\nEnd.\n"
    assert "sends-3-5x-likes" not in ids(text)


def test_fence_reopens_after_close():
    text = "```\nsends 3-5x likes\n```\nSends are weighted 3-5x more than likes.\n"
    assert "sends-3-5x-likes" in ids(text)


# ---------- precision without source ----------

def test_unsourced_precision_fires():
    assert "unsourced-precision" in ids("Completion sits at 45% for most creators.\n")


def test_precision_with_nearby_url_is_quiet():
    text = "Completion sits at 45% for most creators.\nSource: https://example.org/paper\n"
    assert "unsourced-precision" not in ids(text)


def test_precision_with_confidence_tag_is_quiet():
    text = "Median attention is 82% [HIGH] verified by grep.\n"
    assert "unsourced-precision" not in ids(text)


def test_precision_far_from_citation_still_fires():
    text = "Completion sits at 45%.\n" + "\n" * 8 + "https://example.org/paper\n"
    assert "unsourced-precision" in ids(text)


# ---------- severity + exit codes ----------

def test_refuted_is_error_folklore_is_warn():
    f = fl.lint_text("Sends are weighted 3-5x more than likes.", LEDGER)[0]
    assert f["severity"] == "ERROR"
    g = fl.lint_text("Nail the first 3 seconds hook.", LEDGER)[0]
    assert g["severity"] == "WARN"


def _run(tmp_path, text, *extra):
    p = tmp_path / "draft.md"
    p.write_text(text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(p), *extra], capture_output=True, text=True
    )


def test_cli_exit_1_on_error(tmp_path):
    r = _run(tmp_path, "Sends are weighted 3-5x more than likes.\n")
    assert r.returncode == 1
    assert "sends-3-5x-likes" in r.stdout


def test_cli_exit_0_on_clean(tmp_path):
    r = _run(tmp_path, "Pick a format and repeat it.\n")
    assert r.returncode == 0
    assert "clean" in r.stdout


def test_cli_exit_0_on_warn_only_but_1_under_strict(tmp_path):
    warn_only = "Nail the first 3 seconds hook.\n"
    assert _run(tmp_path, warn_only).returncode == 0
    assert _run(tmp_path, warn_only, "--strict").returncode == 1


def test_cli_json_shape(tmp_path):
    r = _run(tmp_path, "A meta-analysis of 208 studies.\n", "--json")
    payload = json.loads(r.stdout)
    (findings,) = payload.values()
    assert findings[0]["id"] == "bornstein-208-studies"
    assert "line" in findings[0] and "instead" in findings[0]


def test_cli_missing_file_exits_2(tmp_path):
    r = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.md")], capture_output=True, text=True
    )
    assert r.returncode == 2


# ---------- exemptions (added after dogfooding the linter on its own SKILL.md) ----------

def test_yaml_frontmatter_is_exempt():
    """Trigger phrases in `description:` are words a user types, not claims the doc makes."""
    text = "---\nname: x\ndescription: triggers on 'is the algorithm punishing me'\n---\nBody.\n"
    assert "algorithm-punishes" not in ids(text)


def test_frontmatter_exemption_does_not_leak_into_body():
    text = "---\nname: x\n---\nThe algorithm punishes quiet accounts.\n"
    assert "algorithm-punishes" in ids(text)


def test_inline_allow_marker_suppresses_named_rule():
    text = "Sends are weighted 3-5x more than likes. <!-- format-lint: allow=sends-3-5x-likes -->\n"
    assert "sends-3-5x-likes" not in ids(text)


def test_allow_marker_on_preceding_line_works():
    text = "<!-- format-lint: allow=sends-3-5x-likes -->\nSends are weighted 3-5x more than likes.\n"
    assert "sends-3-5x-likes" not in ids(text)


def test_allow_marker_only_suppresses_the_named_rule():
    """A marker must not become a blanket silencer."""
    text = (
        "<!-- format-lint: allow=sends-3-5x-likes -->\n"
        "Sends are 3-5x likes and a meta-analysis of 208 studies agrees.\n"
    )
    found = ids(text)
    assert "sends-3-5x-likes" not in found
    assert "bornstein-208-studies" in found


def test_allow_marker_suppresses_unsourced_precision():
    text = "Completion sits at 45%. <!-- format-lint: allow=unsourced-precision -->\n"
    assert "unsourced-precision" not in ids(text)


def test_no_frontmatter_means_no_skip():
    text = "The algorithm punishes quiet accounts.\n"
    assert "algorithm-punishes" in ids(text)


# ---------- block disable regions ----------

def test_disable_region_suppresses_everything_inside():
    text = (
        "Intro.\n<!-- format-lint: disable -->\n"
        "Sends are 3-5x likes. A meta-analysis of 208 studies.\n"
        "<!-- format-lint: enable -->\nOutro.\n"
    )
    assert ids(text) == set()


def test_rules_resume_after_enable():
    text = (
        "<!-- format-lint: disable -->\nSends are 3-5x likes.\n<!-- format-lint: enable -->\n"
        "A meta-analysis of 208 studies.\n"
    )
    found = ids(text)
    assert "bornstein-208-studies" in found
    assert "sends-3-5x-likes" not in found


def test_unclosed_disable_is_itself_an_error():
    """The gate must not be silently switchable-off for the rest of a file."""
    text = "<!-- format-lint: disable -->\nSends are 3-5x likes.\n"
    found = fl.lint_text(text, LEDGER)
    assert any(f["id"] == "unclosed-disable" and f["severity"] == "ERROR" for f in found)


def test_closed_disable_reports_no_control_error():
    text = "<!-- format-lint: disable -->\nx\n<!-- format-lint: enable -->\n"
    assert "unclosed-disable" not in ids(text)
