"""Tests for scripts/lint_skill_md.py — the registry-wide SKILL.md linter.

The ratchet is gate logic, so it ships with tests proving each of its four rules
can actually FAIL. A gate whose rules cannot fail is green for the wrong reason.
Hermetic: every fixture is a tmp dir; the real `skills/` tree is touched by exactly
one test (test_real_repo_is_clean), which is the dogfood.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "lint_skill_md.py"
_spec = importlib.util.spec_from_file_location("lint_skill_md", SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules["lint_skill_md"] = mod
_spec.loader.exec_module(mod)

CAP = mod.MAX_DESC


def _skill(root: Path, name: str, *, desc: str | None = None, extra: str = "",
           fm_name: str | None = None) -> Path:
    """Build skills/<cat>/<name>/SKILL.md under `root`."""
    d = root / "cat" / name
    d.mkdir(parents=True, exist_ok=True)
    desc = "A demo skill." if desc is None else desc
    fm = f"---\nname: {fm_name or name}\ndescription: {desc}\n{extra}---\n# body\n"
    (d / "SKILL.md").write_text(fm, encoding="utf-8")
    return d / "SKILL.md"


def _key(name: str) -> str:
    return f"cat/{name}/SKILL.md"


# --- baseline ----------------------------------------------------------------

def test_conforming_skill_passes(tmp_path):
    _skill(tmp_path, "demo")
    errors, backlog, n = mod.lint(tmp_path, grandfathered={})
    assert errors == [] and backlog == [] and n == 1


def test_description_at_cap_passes(tmp_path):
    _skill(tmp_path, "demo", desc="u" * CAP)
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert errors == []


# --- ratchet rule 1: new debt is rejected ------------------------------------

def test_new_over_cap_skill_fails(tmp_path):
    _skill(tmp_path, "demo", desc="u" * (CAP + 1))
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert len(errors) == 1
    assert f"{CAP + 1} chars > {CAP} max" in errors[0]


def test_silent_band_is_named_in_the_error(tmp_path):
    """1025-1536 renders in full and is still invalid; the message must say so,
    or the next author reads 'it renders' as 'it is fine'."""
    _skill(tmp_path, "demo", desc="u" * ((CAP + mod.RENDER_CAP) // 2))
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert "silent band" in errors[0]


# --- ratchet rule 2: grandfathered entries may only shrink -------------------

def test_grandfathered_skill_is_backlogged_not_failed(tmp_path):
    _skill(tmp_path, "demo", desc="u" * 1200)
    errors, backlog, _ = mod.lint(tmp_path, grandfathered={_key("demo"): 1200})
    assert errors == []
    assert backlog == [(_key("demo"), 1200, 1200)]


def test_grandfathered_skill_may_shrink(tmp_path):
    _skill(tmp_path, "demo", desc="u" * 1100)
    errors, backlog, _ = mod.lint(tmp_path, grandfathered={_key("demo"): 1200})
    assert errors == []
    assert backlog == [(_key("demo"), 1100, 1200)]


def test_grandfathered_skill_may_not_grow(tmp_path):
    _skill(tmp_path, "demo", desc="u" * 1300)
    errors, _, _ = mod.lint(tmp_path, grandfathered={_key("demo"): 1200})
    assert len(errors) == 1
    assert "grew 1200 -> 1300" in errors[0]


# --- ratchet rule 3: a fixed entry must be removed (no rot) ------------------

def test_fixed_skill_still_listed_fails(tmp_path):
    """Without this the list rots: every entry stays forever and the ratchet
    silently stops measuring anything."""
    _skill(tmp_path, "demo", desc="u" * 500)
    errors, _, _ = mod.lint(tmp_path, grandfathered={_key("demo"): 1200})
    assert len(errors) == 1
    assert "now conforms" in errors[0] and "remove" in errors[0]


# --- ratchet rule 4: stale entries are rejected ------------------------------

def test_stale_grandfathered_path_fails(tmp_path):
    _skill(tmp_path, "demo")
    errors, _, _ = mod.lint(tmp_path, grandfathered={"cat/deleted/SKILL.md": 1200})
    assert len(errors) == 1
    assert "matches no linted skill" in errors[0]


# --- spec rules --------------------------------------------------------------

@pytest.mark.parametrize("bad", ["Demo", "demo--x", "-demo", "demo-", "demo_x"])
def test_bad_name_fails(tmp_path, bad):
    _skill(tmp_path, "demo", fm_name=bad)
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert errors, f"{bad!r} must be rejected"


def test_name_must_match_parent_dir(tmp_path):
    _skill(tmp_path, "demo", fm_name="other")
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert len(errors) == 1 and "does not match parent dir" in errors[0]


def test_over_long_name_fails(tmp_path):
    long = "a" * (mod.MAX_NAME + 1)
    _skill(tmp_path, long)
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert any(f"exceeds {mod.MAX_NAME}" in e for e in errors)


def test_over_long_compatibility_fails(tmp_path):
    _skill(tmp_path, "demo", extra="compatibility: " + "c" * (mod.MAX_COMPATIBILITY + 1) + "\n")
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert any("compatibility" in e for e in errors)


def test_missing_description_fails(tmp_path):
    d = tmp_path / "cat" / "demo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: demo\n---\n# body\n", encoding="utf-8")
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert any("missing required field `description`" in e for e in errors)


@pytest.mark.parametrize("text,expect", [
    ("no frontmatter at all\n", "missing YAML frontmatter"),
    ("---\nname: demo\n", "unclosed YAML frontmatter"),
    ("---\nname: [unclosed\n---\n", "malformed YAML"),
    ("---\njust a string\n---\n", "not a mapping"),
])
def test_malformed_frontmatter_fails(tmp_path, text, expect):
    d = tmp_path / "cat" / "demo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert any(expect in e for e in errors), errors


# --- P20 round 1 (CodeRabbit) ------------------------------------------------

@pytest.mark.parametrize("name", ["1password", "7zip", "0x", "1-2-3"])
def test_leading_digit_names_are_legal(tmp_path, name):
    """Spec §Name allows [a-z0-9-]; a leading digit is legal. The old pattern
    required a leading letter, which also made this linter DISAGREE with
    skillify_check.SPEC_NAME_RE — two validators, one contract."""
    _skill(tmp_path, name)
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert errors == [], errors


def test_name_regex_matches_skillify_check():
    """The two validators must enforce byte-identical name patterns, or a skill
    passes one gate and fails the other."""
    gate = REPO / "skills" / "tooling" / "skillify" / "scripts" / "skillify_check.py"
    spec = importlib.util.spec_from_file_location("skillify_check", gate)
    assert spec and spec.loader
    sk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sk)
    assert sk.SPEC_NAME_RE.pattern == mod.NAME_RE.pattern
    for here, there in [("MAX_NAME", "SPEC_MAX_NAME"),
                        ("MAX_DESC", "SPEC_MAX_DESCRIPTION"),
                        ("MAX_COMPATIBILITY", "SPEC_MAX_COMPATIBILITY"),
                        ("RENDER_CAP", "OBSERVED_RENDER_CAP")]:
        assert getattr(mod, here) == getattr(sk, there), f"{here} != {there}"


@pytest.mark.parametrize("text", [
    "---invalid\nname: demo\ndescription: d\n---\n",
    "--- \nname: demo\ndescription: d\n---trailing\n",
])
def test_partial_delimiter_lines_are_rejected(tmp_path, text):
    """`startswith('---')` accepted `---invalid`; `find('\\n---')` let a body
    line close the block early."""
    d = tmp_path / "cat" / "demo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert errors, "malformed delimiters must not parse as valid frontmatter"


def test_body_horizontal_rule_does_not_truncate_frontmatter(tmp_path):
    """A `---` inside a fenced block or as a body rule must not be mistaken for
    the closing delimiter of a still-open frontmatter."""
    d = tmp_path / "cat" / "demo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: real desc\n---\n# body\n\n---\n\nmore\n", encoding="utf-8")
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert errors == [], errors


def test_empty_compatibility_is_rejected(tmp_path):
    _skill(tmp_path, "demo", extra='compatibility: ""\n')
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert any("present but empty" in e for e in errors), errors


def test_valid_compatibility_passes(tmp_path):
    _skill(tmp_path, "demo", extra="compatibility: Requires git and jq\n")
    errors, _, _ = mod.lint(tmp_path, grandfathered={})
    assert errors == []


def test_grandfathered_skill_with_bad_description_reports_once(tmp_path):
    """`seen` was populated only after the description validated, so a
    grandfathered skill with a missing description ALSO reported as a stale
    grandfather entry — two errors, one of them pointing at the wrong problem."""
    d = tmp_path / "cat" / "demo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: demo\n---\n# b\n", encoding="utf-8")
    errors, _, _ = mod.lint(tmp_path, grandfathered={_key("demo"): 1200})
    assert len(errors) == 1, errors
    assert "missing required field `description`" in errors[0]


# --- discovery ---------------------------------------------------------------

@pytest.mark.parametrize("vendor", [".venv", "node_modules", "site-packages", "venv"])
def test_vendored_skills_are_not_linted(tmp_path, vendor):
    """Third-party skills inside a virtualenv are gitignored, so CI never sees
    them; excluding them is what makes a local run reproduce CI."""
    _skill(tmp_path, "demo")
    bad = tmp_path / "cat" / "demo" / vendor / "pkg" / "skills" / "theirs"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_text("---\nname: WRONG\n---\n", encoding="utf-8")
    errors, _, n = mod.lint(tmp_path, grandfathered={})
    assert errors == [] and n == 1


def test_extensions_are_not_linted(tmp_path):
    _skill(tmp_path, "demo")
    ext = tmp_path / "cat" / "demo" / "extensions" / "sub"
    ext.mkdir(parents=True)
    (ext / "SKILL.md").write_text("---\nname: WRONG\n---\n", encoding="utf-8")
    errors, _, n = mod.lint(tmp_path, grandfathered={})
    assert errors == [] and n == 1


def test_empty_tree_is_an_error(tmp_path):
    errors, _, n = mod.lint(tmp_path, grandfathered={})
    assert n == 0 and any("no SKILL.md found" in e for e in errors)


# --- the ratchet baseline itself (BLOCKER 1) ---------------------------------

def _src(entries: dict[str, int]) -> str:
    return "GRANDFATHERED: dict[str, int] = " + repr(entries) + "\n"


def test_extract_grandfathered_reads_the_literal():
    assert mod.extract_grandfathered(_src({"a/SKILL.md": 1100})) == {"a/SKILL.md": 1100}
    assert mod.extract_grandfathered(
        Path(mod.__file__).read_text(encoding="utf-8")) == mod.GRANDFATHERED


def test_extract_grandfathered_rejects_source_without_it():
    with pytest.raises(ValueError):
        mod.extract_grandfathered("X = 1\n")


def test_ratchet_rejects_a_newly_frozen_entry():
    """Without this the ratchet does not ratchet: a PR legalises its own new
    over-cap debt by appending an entry, and every other check stays green."""
    errs = mod.compare_ratchet(_src({"a/SKILL.md": 1100}),
                               _src({"a/SKILL.md": 1100, "b/SKILL.md": 1500}))
    assert len(errs) == 1 and "gained 'b/SKILL.md'" in errs[0]


def test_ratchet_rejects_a_raised_frozen_length():
    errs = mod.compare_ratchet(_src({"a/SKILL.md": 1100}), _src({"a/SKILL.md": 1300}))
    assert len(errs) == 1 and "raised 'a/SKILL.md' 1100 -> 1300" in errs[0]


@pytest.mark.parametrize("head", [
    {"a/SKILL.md": 1100},              # unchanged
    {"a/SKILL.md": 1050},              # shrunk
    {},                                # fully burned down
])
def test_ratchet_allows_only_tightening(head):
    assert mod.compare_ratchet(_src({"a/SKILL.md": 1100}), _src(head)) == []


def test_ratchet_rejects_multiple_bindings():
    """Returning the FIRST binding let a benign decoy shadow a second assignment
    carrying new debt — compare_ratchet clears the decoy, lint() uses the real one."""
    two = _src({"a/SKILL.md": 1100}) + _src({"a/SKILL.md": 1100, "b/SKILL.md": 1500})
    with pytest.raises(ValueError, match="assigned 2 times"):
        mod.extract_grandfathered(two)


@pytest.mark.parametrize("mutation", [
    'GRANDFATHERED["b/SKILL.md"] = 1500\n',
    'GRANDFATHERED.update({"b/SKILL.md": 1500})\n',
    'GRANDFATHERED.setdefault("b/SKILL.md", 1500)\n',
    'GRANDFATHERED |= {"b/SKILL.md": 1500}\n',        # augmented assignment
    'GRANDFATHERED["a/SKILL.md"] += 500\n',           # augmented SUBSCRIPT assignment
    'GRANDFATHERED.pop("a/SKILL.md")\n',
    'GRANDFATHERED.clear()\n',
])
def test_ratchet_rejects_post_assignment_mutation(mutation):
    src = _src({"a/SKILL.md": 1100}) + mutation
    with pytest.raises(ValueError, match="mutated after assignment"):
        mod.extract_grandfathered(src)


@pytest.mark.parametrize("benign", [
    'x = GRANDFATHERED.get("a/SKILL.md")\n',      # pure reads must not abort
    'y = GRANDFATHERED.copy()\n',
    'z = GRANDFATHERED.items()\n',
    'w = GRANDFATHERED.fromkeys(["x"], 0)\n',    # returns a NEW dict; not a mutation
    'def f():\n    GRANDFATHERED = {}\n    return GRANDFATHERED\n',  # local shadow
])
def test_ratchet_tolerates_reads_and_local_shadows(benign):
    """Flagging every attribute call made `.get()` abort the comparison, and a
    scope-blind walk counted a function-local shadow as a second baseline."""
    src = _src({"a/SKILL.md": 1100}) + benign
    assert mod.extract_grandfathered(src) == {"a/SKILL.md": 1100}


# `node_modules` is deliberately absent: the underscore makes it an illegal skill
# name anyway, so it cannot exercise the ancestor-vs-component boundary.
@pytest.mark.parametrize("skill_name", ["venv", "extensions", "site-packages"])
def test_a_skill_may_be_named_like_a_vendored_dir(tmp_path, skill_name):
    """The exclusion boundary is ANCESTORS ONLY. Matching every component would
    silently unlint a legitimately-named skill — it would look healthy while
    being invisible to the registry gate."""
    _skill(tmp_path, skill_name)
    errors, _, n = mod.lint(tmp_path, grandfathered={})
    assert errors == [] and n == 1, f"{skill_name} must still be linted"


def test_vendored_ancestor_still_excluded_with_same_names(tmp_path):
    """The complement of the test above: as an ANCESTOR the same name excludes."""
    _skill(tmp_path, "demo")
    bad = tmp_path / "cat" / "demo" / "venv" / "pkg" / "theirs"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_text("---\nname: WRONG\n---\n", encoding="utf-8")
    errors, _, n = mod.lint(tmp_path, grandfathered={})
    assert errors == [] and n == 1


def test_ratchet_baseline_is_not_executed():
    """The baseline comes from another commit; it must be parsed, never imported."""
    poisoned = "raise SystemExit('baseline executed')\n" + _src({"a/SKILL.md": 1100})
    assert mod.compare_ratchet(poisoned, _src({"a/SKILL.md": 1100})) == []


# --- dogfood: the real registry ---------------------------------------------

def test_real_repo_is_clean():
    """The shipped GRANDFATHERED list must exactly describe the real tree — no
    new debt, no stale entries, no fixed-but-listed rot."""
    errors, backlog, n = mod.lint(REPO / "skills")
    assert errors == [], "\n".join(errors)
    assert n > 50, f"discovery looks broken: only {n} skills found"
    assert len(backlog) == len(mod.GRANDFATHERED)
