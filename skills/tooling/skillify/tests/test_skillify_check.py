"""Tests for skillify_check.py — the skillify doctor.

skillify enforces "every skill ships with tests"; it must therefore ship with
tests itself (dogfood). Hermetic: every fixture is built in a tmp dir.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "skillify_check.py"
_spec = importlib.util.spec_from_file_location("skillify_check", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# --- fixture builders --------------------------------------------------------

def _skill(tmp: Path, *, name="demo", scripts=True, tests=True, latent=False,
           desc="A demo skill.", tier=None) -> Path:
    d = tmp / name
    (d / "scripts").mkdir(parents=True, exist_ok=True)
    (d / "tests").mkdir(parents=True, exist_ok=True)
    fm = f"---\nname: {name}\ndescription: {desc}\n"
    if latent:
        fm += "latent_only: true\n"
    if tier is not None:
        fm += f"tier: {tier}\n"
    fm += "---\n# body\n"
    (d / "SKILL.md").write_text(fm, encoding="utf-8")
    if scripts:
        (d / "scripts" / "do.py").write_text("print('hi')\n", encoding="utf-8")
    if tests:
        (d / "tests" / "test_do.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    return d


# --- unit: checklist logic ---------------------------------------------------

def test_complete_skill_passes(tmp_path):
    d = _skill(tmp_path)
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False)
    by_step = {r["step"]: r for r in res}
    assert by_step[1]["status"] == "PASS"   # SKILL.md
    assert by_step[2]["status"] == "PASS"   # code
    assert by_step[3]["status"] == "PASS"   # tests
    assert not [r for r in res if r["status"] == "FAIL" and r["required"]]


def test_scripts_without_tests_fails(tmp_path):
    d = _skill(tmp_path, tests=False)
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False)
    step3 = next(r for r in res if r["step"] == 3)
    assert step3["status"] == "FAIL" and step3["required"]


def test_latent_only_no_longer_buys_a_blanket_exemption(tmp_path):
    """BRO-2190: `latent_only: true` used to SKIP step 2 and step 3, so the branch
    built to accommodate non-deterministic skills gated NOTHING. It must now still
    satisfy a tier (J or L)."""
    d = _skill(tmp_path, scripts=False, tests=False, latent=True)
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False)
    step2 = next(r for r in res if r["step"] == 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "cannot classify" in step2["detail"]


def test_latent_only_with_a_real_tier_passes(tmp_path):
    """The loosening is real: the same skill declaring tier L with a routing eval
    passes, so closing the amnesty did not just make the gate stricter."""
    d = _skill(tmp_path, scripts=False, tests=False, latent=True, tier="L")
    _routing_eval(d)
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False)
    step2 = next(r for r in res if r["step"] == 2)
    assert step2["status"] == "PASS"
    assert not [r for r in res if r["status"] == "FAIL" and r["required"]]


def test_missing_skill_md_fails(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False)
    step1 = next(r for r in res if r["step"] == 1)
    assert step1["status"] == "FAIL" and step1["required"]


def test_resolver_eval_detected(tmp_path):
    d = _skill(tmp_path, name="demo")
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "demo.eval.yaml").write_text("lens: demo\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=roles, registry=None, entities_dir=None, strict=False)
    step7 = next(r for r in res if r["step"] == 7)
    assert step7["status"] == "PASS"


def test_registry_trigger_detected(tmp_path):
    d = _skill(tmp_path, name="demo")
    reg = tmp_path / "AGENTS.md"
    reg.write_text("| demo | does demo things |\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=reg, entities_dir=None, strict=False)
    step6 = next(r for r in res if r["step"] == 6)
    assert step6["status"] == "PASS"


def test_strict_promotes_warnings_to_required(tmp_path):
    d = _skill(tmp_path, name="demo")
    reg = tmp_path / "AGENTS.md"
    reg.write_text("nothing here\n", encoding="utf-8")  # name NOT registered
    res = mod.run_checklist(d, roles_dir=None, registry=reg, entities_dir=None, strict=True)
    step6 = next(r for r in res if r["step"] == 6)
    assert step6["status"] == "FAIL" and step6["required"]


# --- integration: the CLI ----------------------------------------------------

def _run(*args: str) -> tuple[int, str, str]:
    r = subprocess.run([sys.executable, str(SCRIPT), *args],
                       capture_output=True, text=True, env={**os.environ})
    return r.returncode, r.stdout, r.stderr


def test_cli_complete_skill_exit_0(tmp_path):
    d = _skill(tmp_path)
    rc, out, err = _run(str(d))
    assert rc == 0, f"{out}\n{err}"
    assert "PASS" in out


def test_cli_incomplete_skill_exit_1(tmp_path):
    d = _skill(tmp_path, tests=False)
    rc, out, err = _run(str(d))
    assert rc == 1
    assert "Not a skill yet" in out


def test_cli_json(tmp_path):
    d = _skill(tmp_path)
    rc, out, err = _run(str(d), "--json")
    assert rc == 0
    payload = json.loads(out)
    assert payload["failed"] == 0
    assert len(payload["results"]) == 13  # ten steps + 1b + 1c + 2t (tier declaration)


def test_cli_bad_dir_exit_2(tmp_path):
    rc, out, err = _run(str(tmp_path / "nope"))
    assert rc == 2


# --- P20 adversarial regression tests (every one was a confirmed false-pass) ---

def _step(res, n):
    return next(r for r in res if r["step"] == n)


def test_empty_test_file_fails_step3(tmp_path):  # H1
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "test_empty.py").write_text("", encoding="utf-8")  # zero-byte
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 3)["status"] == "FAIL"


def test_garbage_test_file_fails_step3(tmp_path):  # H1
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "test_x.py").write_text("# just a comment, no test here\nx = 1\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 3)["status"] == "FAIL"


def test_syntax_broken_script_fails_step2(tmp_path):  # H1
    d = _skill(tmp_path)
    (d / "scripts" / "do.py").write_text("def broken( (( syntax error\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 2)["status"] == "FAIL"


def test_data_fixture_is_not_a_test(tmp_path):  # H2
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "fixtures.test.json").write_text('{"k": 1}\n', encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 3)["status"] == "FAIL"  # json fixture ≠ test


def test_latent_only_with_code_is_contradiction(tmp_path):  # H3
    d = _skill(tmp_path, latent=True, tests=False)  # latent_only AND ships scripts/do.py
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    s2 = _step(res, 2)
    assert s2["status"] == "FAIL" and s2["required"]


def test_folded_description_parses_cleanly(tmp_path):  # M2
    d = tmp_path / "fold"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: fold\ndescription: >-\n  this is a folded\n  multi-line description\n---\n# body\n",
        encoding="utf-8")
    fm = mod.parse_frontmatter(d / "SKILL.md")
    assert fm["name"] == "fold"
    assert "folded" in fm["description"] and fm["description"] != ">-"
    assert "USE WHEN" not in fm  # no bogus keys manufactured from prose colons


def test_nested_tests_detected(tmp_path):  # L1
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "unit").mkdir()
    (d / "tests" / "unit" / "test_deep.py").write_text("def test_z():\n    assert 1\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 3)["status"] == "PASS"


def test_prose_mention_is_not_registered(tmp_path):  # M3
    d = _skill(tmp_path, name="demo")
    reg = tmp_path / "AGENTS.md"
    reg.write_text("In the old days demo was a thing we removed.\n", encoding="utf-8")  # prose only
    res = mod.run_checklist(d, roles_dir=None, registry=reg, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 6)["status"] == "FAIL"


def test_strict_without_paths_fails_the_gate(tmp_path):  # M1 (round 3)
    # --strict must not PASS while skipping the checks strict exists for.
    d = _skill(tmp_path)
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=True, run_tests=False)
    s6 = _step(res, 6)
    assert s6["status"] == "FAIL" and s6["required"]
    rc, out, err = _run(str(d), "--strict")  # exit code, not just status
    assert rc == 1, f"strict without paths must exit 1, got {rc}\n{out}"


def test_backticked_name_in_prose_not_registered(tmp_path):  # M3 (round 3)
    d = _skill(tmp_path, name="demo")
    reg = tmp_path / "AGENTS.md"
    reg.write_text("We removed the old `demo` integration last year.\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=reg, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 6)["status"] == "FAIL"  # backtick-in-prose ≠ registered


def test_table_row_and_list_item_are_registered(tmp_path):  # M3 positive
    d = _skill(tmp_path, name="demo")
    for content in ("| demo | does things |\n", "- `demo` — a skill\n", "* demo: a skill\n"):
        reg = tmp_path / "AGENTS.md"
        reg.write_text(content, encoding="utf-8")
        res = mod.run_checklist(d, roles_dir=None, registry=reg, entities_dir=None, strict=False, run_tests=False)
        assert _step(res, 6)["status"] == "PASS", f"should register: {content!r}"


def test_construct_word_in_string_is_not_a_test(tmp_path):  # N1 (round 3)
    d = _skill(tmp_path, tests=False)
    # 'def test_' and 'assert' only appear inside string literals — not a real test
    (d / "tests" / "test_fake.py").write_text(
        'TODO = "remember to add a def test_ and an assert"\nx = 1\n', encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 3)["status"] == "FAIL"


def test_real_python_test_detected_via_ast(tmp_path):  # N1 positive
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "test_real.py").write_text("def test_thing():\n    assert 1 == 1\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 3)["status"] == "PASS"


# --- round-3 final-review bypasses (shape-not-substance regressions) ----------

def _reg_status(tmp_path, line, name="demo"):
    d = _skill(tmp_path, name=name)
    reg = tmp_path / "AGENTS.md"
    reg.write_text(line, encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=reg, entities_dir=None, strict=False, run_tests=False)
    return _step(res, 6)["status"]


def test_bulleted_prose_not_registered(tmp_path):  # M3 round-3
    assert _reg_status(tmp_path, "- we removed `demo` last year\n") == "FAIL"


def test_pipe_prose_not_registered(tmp_path):  # M3 round-3
    assert _reg_status(tmp_path, "Deprecated | we removed demo last year\n") == "FAIL"


def test_stray_pipe_prose_not_registered(tmp_path):  # M3 final (8→9 residual)
    # a single stray '|' with the name first in the segment must NOT register
    assert _reg_status(tmp_path, "The | demo and other stuff\n") == "FAIL"
    assert _reg_status(tmp_path, "see table below | demo is great\n") == "FAIL"


def test_markdown_link_table_cell_registered(tmp_path):  # M3 positive (real _index.md shape)
    assert _reg_status(tmp_path, "| [demo](demo.md) | candidate | _meta |\n") == "PASS"


def test_js_string_tokens_not_a_test(tmp_path):  # N1 round-3 (non-python)
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "fake.test.js").write_text('const x = "it( describe( assert here";\n', encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 3)["status"] == "FAIL"


def test_js_real_test_detected(tmp_path):  # N1 positive (non-python)
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "real.test.js").write_text("test('does x', () => { expect(1).toBe(1); });\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 3)["status"] == "PASS"


def test_skillsh_frontmatter_gotcha_detected(tmp_path):  # v0.2 — skills.sh parser killer
    d = tmp_path / "g"
    (d / "scripts").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "SKILL.md").write_text(
        '---\nname: g\ndescription: a skill\ntriggers:\n  - "@a", "@b", "@c"\n---\n# body\n', encoding="utf-8")
    issue = mod._skillsh_frontmatter_issue(d)
    assert issue is not None and '"@a"' in issue
    # step 1 must FAIL — the skill would silently not install via skills.sh
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 1)["status"] == "FAIL"


def test_skillsh_clean_frontmatter_passes(tmp_path):  # v0.2 — one quoted string is fine
    d = _skill(tmp_path, name="ok")
    # add a single-quoted-string list item (allowed) to ensure no false positive
    (d / "SKILL.md").write_text(
        '---\nname: ok\ndescription: a skill\ntriggers:\n  - "one quoted string"\n  - plain, commas, fine\n---\n# body\n',
        encoding="utf-8")
    assert mod._skillsh_frontmatter_issue(d) is None
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 1)["status"] == "PASS"


def _fm_issue(tmp_path, frontmatter_body: str):
    d = tmp_path / "fm"
    d.mkdir(exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: fm\ndescription: x\n{frontmatter_body}\n---\n# body\n", encoding="utf-8")
    return mod._skillsh_frontmatter_issue(d)


def test_skillsh_frontmatter_matrix(tmp_path):  # v0.2 P20 round-2 — live-parser-verified matrix
    # BREAKS → must be flagged (quoted scalar then comma in a block-seq item)
    assert _fm_issue(tmp_path, 'k:\n  - "@a", "@b", "@c"') is not None
    assert _fm_issue(tmp_path, 'k:\n  - "a", "b"') is not None
    assert _fm_issue(tmp_path, 'k:\n  - "a", b') is not None          # false-pass fix: 1 quote + comma still breaks
    # INSTALLS FINE → must NOT be flagged
    assert _fm_issue(tmp_path, 'k:\n  - x, "b"') is None              # bareword first, no quote-then-comma
    assert _fm_issue(tmp_path, 'k:\n  - "one quoted string"') is None  # single quoted string
    assert _fm_issue(tmp_path, 'k:\n  - plain, commas, fine') is None  # plain comma list
    assert _fm_issue(tmp_path, 'desc2: |\n  - "foo" and "bar"') is None  # false-fail fix: prose in a block scalar
    assert _fm_issue(tmp_path, 'k:\n  - "one"  # a "two" comment') is None  # comment, no quote-then-comma


def test_list_output_has_rejects_sibling_description(tmp_path):  # v0.2 P20 round-2 — step-9 false-pass fix
    # name listed as an entry → True
    assert mod._list_output_has("│    skillify\n│      A skillify description here.", "skillify")
    # name ONLY inside a sibling's description prose → False (not actually listed)
    assert not mod._list_output_has("│    health\n│      about skillify and wellness", "skillify")
    # name only in an error message → False
    assert not mod._list_output_has("Error: could not find skillify in repo", "skillify")


def test_skills_sh_step9_required_when_flag_set(tmp_path, monkeypatch):  # v0.2 — --skills-sh gates step 9
    d = _skill(tmp_path, name="demo")
    monkeypatch.setattr(mod, "_skillsh_list_has", lambda target, name: (False, "stub: not found"))
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None,
                            strict=False, run_tests=False, skills_sh="broomva/demo")
    s9 = _step(res, 9)
    assert s9["status"] == "FAIL" and s9["required"]
    monkeypatch.setattr(mod, "_skillsh_list_has", lambda target, name: (True, "stub: found"))
    res2 = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None,
                             strict=False, run_tests=False, skills_sh="broomva/demo")
    assert _step(res2, 9)["status"] == "PASS"


def test_ast_does_not_overmatch_testimony(tmp_path):  # N1 round-3 (AST tightening)
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "test_t.py").write_text(
        "def testimony():\n    return 1\nclass Testimonials:\n    pass\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=False)
    assert _step(res, 3)["status"] == "FAIL"  # neither is a real test


def test_run_tests_executes_pytest(tmp_path):  # H1 strongest form
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "test_real.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False, run_tests=True)
    assert _step(res, 3)["status"] == "PASS"


# --- BRO-1561: installable-layout gate (step 1) ------------------------------

def _git_init(d: Path):
    subprocess.run(["git", "init", "-q", str(d)], check=True)


def test_repo_root_with_bundled_dirs_warns_not_fails(tmp_path):
    # A skill that IS a git repo root carrying scripts/ hits skills.sh#1523 on
    # remote install — BUT top-level is standard-valid, so this is a non-required
    # WARN (step 1b), NOT a required FAIL. Step 1 (contract) still PASSes.
    d = _skill(tmp_path)
    _git_init(d)
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False)
    step1 = next(r for r in res if r["step"] == 1)
    assert step1["status"] == "PASS"  # frontmatter is fine — layout doesn't fail the contract
    step1b = next(r for r in res if r["step"] == "1b")
    assert step1b["status"] == "WARN" and not step1b["required"]
    assert "repo root" in step1b["detail"] and "1523" in step1b["detail"]
    # and it must NOT contribute a required FAIL
    assert not [r for r in res if r["status"] == "FAIL" and r["required"]]


def test_skills_subdir_layout_passes(tmp_path):
    # Same skill, but in `skills/<name>/` of a repo root → correct layout, 1b PASS.
    repo = tmp_path / "myrepo"
    repo.mkdir()
    _git_init(repo)
    d = _skill(repo / "skills", name="demo")  # → myrepo/skills/demo/
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False)
    step1b = next(r for r in res if r["step"] == "1b")
    assert step1b["status"] == "PASS", step1b["detail"]


def test_unit_repo_root_bundled_dirs_issue(tmp_path):
    # Direct unit: repo-root + scripts/ → message; non-repo-root → None.
    d = _skill(tmp_path)
    assert mod._repo_root_bundled_dirs_issue(d) is None    # not a repo root yet
    _git_init(d)
    msg = mod._repo_root_bundled_dirs_issue(d)
    assert msg and "scripts" in msg


# --- step 1c: internal-reference integrity -----------------------------------

def _rc(d):
    return mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False)


def test_ref_integrity_fails_on_missing_script_ref(tmp_path):
    # SKILL.md advertises a script that does not exist → 1c FAIL (the #1 defect).
    d = _skill(tmp_path)
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: x\n---\n"
        "Run the analysis with `scripts/missing_analyzer.py`.\n", encoding="utf-8")
    res = _rc(d)
    assert _step(res, "1c")["status"] == "FAIL"
    assert _step(res, "1c")["required"]
    assert [r for r in res if r["status"] == "FAIL" and r["required"]]  # gate fails


def test_ref_integrity_existing_ref_passes(tmp_path):
    d = _skill(tmp_path)  # ships scripts/do.py
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: x\n---\nRuns `scripts/do.py`.\n", encoding="utf-8")
    assert _step(_rc(d), "1c")["status"] == "PASS"


def test_ref_integrity_planned_marker_exempts(tmp_path):
    d = _skill(tmp_path)
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: x\n---\n"
        "**Status:** Planned — `scripts/future.py` is not yet shipped. Do not invoke.\n",
        encoding="utf-8")
    assert _step(_rc(d), "1c")["status"] == "PASS"


def test_ref_integrity_ignores_fenced_examples(tmp_path):
    # Refs inside ``` fences are example commands / File-Structure trees, not claims.
    d = _skill(tmp_path)
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: x\n---\nExample:\n"
        "```bash\npython3 scripts/example_only.py --flag\n```\n", encoding="utf-8")
    assert _step(_rc(d), "1c")["status"] == "PASS"


def test_ref_integrity_skill_json_entrypoint_must_exist(tmp_path):
    d = _skill(tmp_path)
    (d / "skill.json").write_text(
        '{"name": "demo", "entrypoint": "scripts/nope.py"}', encoding="utf-8")
    assert _step(_rc(d), "1c")["status"] == "FAIL"


def test_ref_integrity_scaffold_template_output_satisfies(tmp_path):
    # A skill that WRITES files into a target repo ships them under assets/templates/.
    d = _skill(tmp_path)
    tdir = d / "assets" / "templates" / "scripts" / "harness"
    tdir.mkdir(parents=True)
    (tdir / "lint.sh").write_text("#!/usr/bin/env bash\necho lint\n", encoding="utf-8")
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: x\n---\n"
        "The bootstrap writes `scripts/harness/lint.sh` into your repo.\n", encoding="utf-8")
    assert _step(_rc(d), "1c")["status"] == "PASS"


def test_ref_integrity_yaml_template_script_ref(tmp_path):
    # templates/*.yaml that point an executor at a missing script → 1c FAIL.
    d = _skill(tmp_path)
    (d / "templates").mkdir(exist_ok=True)
    (d / "templates" / "loop.yaml").write_text(
        "evaluator:\n  command: python3 scripts/eval_missing.py --egri\n", encoding="utf-8")
    assert _step(_rc(d), "1c")["status"] == "FAIL"


# --- step 3: bash test suites are recognized ---------------------------------

def test_bash_test_suite_counts_as_real(tmp_path):
    d = _skill(tmp_path, tests=False)  # ships scripts/do.py, no python tests
    (d / "tests" / "demo.test.sh").write_text(
        "#!/usr/bin/env bash\nPASS=0\nFAIL=0\n"
        "ok() { PASS=$((PASS + 1)); }\nfail() { FAIL=$((FAIL + 1)); }\n"
        "[ 1 = 1 ] && ok 'one' || fail 'one'\n", encoding="utf-8")
    res = _rc(d)
    assert _step(res, 3)["status"] == "PASS"   # bash suite recognized as a real test


def test_non_test_bash_script_not_counted(tmp_path):
    # A plain bash script (no test constructs) must NOT count as a test.
    d = _skill(tmp_path, tests=False)
    (d / "tests" / "helper.test.sh").write_text(
        "#!/usr/bin/env bash\necho 'just a helper'\ncp a b\n", encoding="utf-8")
    assert mod._is_real_test(d / "tests" / "helper.test.sh") is False


def test_ref_integrity_entrypoint_counted_once(tmp_path):  # CodeRabbit: no double-count
    d = _skill(tmp_path)
    (d / "skill.json").write_text(
        '{"name": "demo", "entrypoint": "scripts/nope.py"}', encoding="utf-8")
    s1c = _step(_rc(d), "1c")
    assert s1c["status"] == "FAIL"
    assert s1c["detail"].startswith("1 broken")  # exactly one issue, not two


def test_ref_integrity_yaml_non_script_prefix(tmp_path):  # CodeRabbit: all 4 prefixes
    # A templates/*.yaml ref to references/ (not just scripts/) is also checked.
    d = _skill(tmp_path)
    (d / "templates").mkdir(exist_ok=True)
    (d / "templates" / "loop.yaml").write_text(
        "doc: references/missing_guide.md\n", encoding="utf-8")
    assert _step(_rc(d), "1c")["status"] == "FAIL"


# --- step 5: trigger evals (BRO-2005) ----------------------------------------
# Regression guard for the gate's own vacuity: step 5 used to pass on
# `(skill_dir / "evals").is_dir()` alone, so an EMPTY evals/ dir scored
# "present". That is how a stack reports ~10% eval coverage with ZERO trigger
# assertions. Each test below fails against the old presence-only check.

def _step5(d):
    return next(r for r in mod.run_checklist(
        d, roles_dir=None, registry=None, entities_dir=None, strict=False) if r["step"] == 5)


def test_step5_empty_evals_dir_is_not_coverage(tmp_path):
    # THE mutation the old check could not survive: bare dir, no content.
    d = _skill(tmp_path)
    (d / "evals").mkdir()
    s5 = _step5(d)
    assert s5["status"] == "WARN"
    assert "none" in s5["detail"]


def test_step5_eval_artifact_without_trigger_assertions_warns(tmp_path):
    # An eval file that asserts nothing about triggering leaves the latent half
    # ungated — distinct message from "no evals at all".
    d = _skill(tmp_path)
    (d / "evals").mkdir()
    (d / "evals" / "prompts.json").write_text(
        json.dumps({"skill": "demo", "cases": [{"id": "a", "prompt": "hi"}]}), encoding="utf-8")
    s5 = _step5(d)
    assert s5["status"] == "WARN"
    assert "trigger" in s5["detail"]
    assert "1 eval artifact" in s5["detail"]


def test_step5_real_trigger_eval_passes(tmp_path):
    d = _skill(tmp_path)
    (d / "evals").mkdir()
    (d / "evals" / "prompts.json").write_text(json.dumps({
        "skill": "demo",
        "cases": [{"id": "a", "prompt": "hi", "should_trigger": True},
                  {"id": "b", "prompt": "bye", "should_trigger": False}],
    }), encoding="utf-8")
    s5 = _step5(d)
    assert s5["status"] == "PASS"
    assert "trigger eval" in s5["detail"]


def test_step5_trigger_key_must_be_a_key_not_prose(tmp_path):
    # A README describing should_trigger is documentation, not an assertion.
    d = _skill(tmp_path)
    (d / "evals").mkdir()
    (d / "evals" / "prompts.json").write_text(
        json.dumps({"notes": "each case carries should_trigger: true"}), encoding="utf-8")
    assert _step5(d)["status"] == "WARN"


def test_step5_role_x_resolver_eval_schema_counts(tmp_path):
    # role-x's should_fire/should_not_fire schema is a trigger eval too.
    d = _skill(tmp_path)
    (d / "evals").mkdir()
    (d / "evals" / "cases.yaml").write_text(
        "cases:\n  - prompt: do a thing\n    should_fire: true\n", encoding="utf-8")
    assert _step5(d)["status"] == "PASS"


def test_step5_unparseable_json_is_not_coverage(tmp_path):
    d = _skill(tmp_path)
    (d / "evals").mkdir()
    (d / "evals" / "prompts.json").write_text("{ not json should_trigger", encoding="utf-8")
    assert _step5(d)["status"] == "WARN"


def test_step5_nested_trigger_key_is_found(tmp_path):
    d = _skill(tmp_path)
    (d / "evals").mkdir()
    (d / "evals" / "p.json").write_text(
        json.dumps({"suites": [{"group": {"cases": [{"should_trigger": False}]}}]}), encoding="utf-8")
    assert _step5(d)["status"] == "PASS"


def test_step5_empty_file_in_evals_dir_is_not_coverage(tmp_path):
    d = _skill(tmp_path)
    (d / "evals").mkdir()
    (d / "evals" / "prompts.json").write_text("", encoding="utf-8")
    assert _step5(d)["status"] == "WARN"


def test_step5_is_advisory_never_blocks(tmp_path):
    # Deliberate: step 5 stays required=False. Flipping it to required is a
    # governance change (BRO-2009), gated on trigger-eval coverage existing first.
    d = _skill(tmp_path)
    (d / "evals").mkdir()
    s5 = _step5(d)
    assert s5["status"] == "WARN"
    assert s5.get("required") is not True


# ===========================================================================
# Tiers — D / J / L (BRO-2190)
# ===========================================================================

def _routing_eval(d: Path, *, both_polarities=True) -> Path:
    """A tier-L core: an eval asserting the skill fires and stays silent."""
    (d / "evals").mkdir(parents=True, exist_ok=True)
    cases = [{"prompt": "do the thing", "should_fire": True}]
    if both_polarities:
        cases.append({"prompt": "unrelated", "should_not_fire": True})
    f = d / "evals" / "prompts.json"
    f.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return f


def _judgment_evals(d: Path, *, admission="admitted", rubric=True, held_out=1,
                    judge_model="gpt-5", under_model="haiku",
                    floor=0.7, measured=True) -> None:
    """A complete tier-J core, with each part individually removable."""
    (d / "evals").mkdir(parents=True, exist_ok=True)
    if admission is not None:
        (d / "evals" / "admission.md").write_text(
            f"---\noutcome: {admission}\n---\n\n"
            "Two agents, same input, both outputs judged valid by a third reader.\n",
            encoding="utf-8")
    if rubric:
        (d / "evals" / "rubric.md").write_text("# Rubric\n\n- engages the argument\n",
                                               encoding="utf-8")
    judge = {"model": judge_model}
    if floor is not None:
        judge["agreement_floor"] = floor
        if measured:
            judge["agreement_measured"] = {
                "value": floor, "method": "3 judges x 40 held-out cases, Krippendorff alpha",
                "date": "2026-08-19"}
    blob = {
        "cases": [{"prompt": f"case {i}", "held_out": True} for i in range(held_out)],
        "judge": judge,
        "execution_contract": {"model": under_model},
    }
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")


def _step(res, step):
    return next(r for r in res if r["step"] == step)


def _check(d, **kw):
    kw.setdefault("roles_dir", None)
    kw.setdefault("registry", None)
    kw.setdefault("entities_dir", None)
    kw.setdefault("strict", False)
    return mod.run_checklist(d, **kw)


# --- tier D ------------------------------------------------------------------

def test_tier_d_declared_with_code_passes(tmp_path):
    d = _skill(tmp_path, tier="D")
    res = _check(d)
    assert _step(res, 2)["status"] == "PASS"
    assert "declared" in _step(res, 2)["detail"]


def test_tier_d_declared_without_code_fails(tmp_path):
    """Declaring a tier whose core you did not ship is the one thing the gate
    must not permit — otherwise `tier:` is a self-issued exemption."""
    d = _skill(tmp_path, scripts=False, tests=False, tier="D")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "no scripts" in step2["detail"]


def test_tests_required_whenever_code_ships_regardless_of_tier(tmp_path):
    """The old expression routed step 3 through latent_only, so a skill could ship
    scripts and buy out of testing them. Tier L + scripts must still need tests."""
    d = _skill(tmp_path, tests=False, tier="L")
    _routing_eval(d)
    step3 = _step(_check(d), 3)
    assert step3["status"] == "FAIL" and step3["required"]


# --- tier J ------------------------------------------------------------------

def test_tier_j_complete_passes(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d)
    res = _check(d)
    assert _step(res, 2)["status"] == "PASS", _step(res, 2)["detail"]
    assert not [r for r in res if r["status"] == "FAIL" and r["required"]]


def test_tier_j_without_admission_record_fails(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d, admission=None)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "admission" in step2["detail"]


def test_tier_j_self_judging_fails(tmp_path):
    """A judge sharing the generator's substrate inflates confidence rather than
    testing it — identical model is the degenerate case and must not pass."""
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d, judge_model="haiku", under_model="haiku")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL"
    assert "self-judging" in step2["detail"]


def test_tier_j_same_family_judge_warns_but_does_not_block(tmp_path):
    """Distinct names, correlated substrate. The gate cannot honestly prove
    cross-vendor from a bare string, so it warns rather than pretending."""
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d, judge_model="opus", under_model="haiku")
    res = _check(d)
    assert _step(res, 2)["status"] == "PASS"
    warn = _step(res, "2j")
    assert warn["status"] == "WARN" and "family" in warn["detail"]


def test_tier_j_floor_without_measurement_fails(tmp_path):
    """The whole point: an agreement floor nobody measured is an authored number.
    This is the clamp the post-mortem that produced these tiers asked for."""
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d, measured=False)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL"
    assert "agreement_measured" in step2["detail"]


def test_tier_j_missing_floor_fails(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d, floor=None)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL"
    assert "agreement_floor" in step2["detail"]


def test_tier_j_without_held_out_cases_fails(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d, held_out=0)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL"
    assert "held-out" in step2["detail"]


def test_tier_j_without_rubric_fails(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d, rubric=False)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL"
    assert "rubric" in step2["detail"]


def test_judge_execution_is_never_reported_as_a_pass(tmp_path):
    """The anti-vacuity assertion. The LLM judge is a declared, unbuilt seam
    (checks.py make_judge_check raises). A tier that certified itself through an
    unimplemented judge would be exactly the false PASS this gate exists to stop —
    so the judge RUN is a named SKIP even when every artifact is perfect."""
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d)
    row = _step(_check(d), "2j*")
    assert row["status"] == "SKIP"
    assert row["status"] != "PASS"
    assert "make_judge_check" in row["detail"]
    assert not row["required"]


# --- tier L ------------------------------------------------------------------

def test_tier_l_with_routing_eval_passes(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    _routing_eval(d)
    res = _check(d)
    assert _step(res, 2)["status"] == "PASS"
    assert not [r for r in res if r["status"] == "FAIL" and r["required"]]


def test_tier_l_without_routing_eval_fails(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "no routing eval" in step2["detail"]


def test_tier_l_requires_resolver_eval_when_roles_dir_given(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    _routing_eval(d)
    roles = tmp_path / "roles"
    roles.mkdir()
    step7 = _step(_check(d, roles_dir=roles), 7)
    assert step7["status"] == "FAIL" and step7["required"]
    (roles / "demo.eval.yaml").write_text("cases: []\n", encoding="utf-8")
    assert _step(_check(d, roles_dir=roles), 7)["status"] == "PASS"


def test_tier_l_resolver_eval_not_required_without_roles_dir(tmp_path):
    """Absence of a FLAG must never be scored as absence of an EVAL."""
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    _routing_eval(d)
    step7 = _step(_check(d), 7)
    assert step7["status"] == "SKIP" and not step7["required"]


# --- classification ----------------------------------------------------------

def test_unclassifiable_skill_still_fails(tmp_path):
    """Inference decides WHICH gate, never WHETHER one applies. A skill with no
    code, no eval and no admission record is as ungated as before and must fail."""
    d = _skill(tmp_path, scripts=False, tests=False)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]


def test_unclassifiable_message_names_the_procedure_residue(tmp_path):
    """The 41/94 uncarved skills are procedure skills; telling them to pick one of
    three tiers that do not fit would be confidently wrong advice (BRO-2192)."""
    d = _skill(tmp_path, scripts=False, tests=False)
    assert "BRO-2192" in _step(_check(d), 2)["detail"]


def test_inferred_tier_warns(tmp_path):
    d = _skill(tmp_path)  # ships code, no tier: declared
    row = _step(_check(d), "2t")
    assert row["status"] == "WARN" and not row["required"]
    assert "inferred" in row["detail"]


def test_declared_tier_emits_no_inference_warning(tmp_path):
    d = _skill(tmp_path, tier="D")
    assert not [r for r in _check(d) if r["step"] == "2t"]


def test_invalid_tier_value_fails(tmp_path):
    d = _skill(tmp_path, tier="X")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "not one of D/J/L" in step2["detail"]


def test_latent_only_with_scripts_is_still_a_contradiction(tmp_path):
    d = _skill(tmp_path, latent=True)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "contradiction" in step2["detail"]


# --- survey ------------------------------------------------------------------

def test_survey_tallies_by_tier(tmp_path):
    _skill(tmp_path, name="ddd", tier="D")
    lll = _skill(tmp_path, name="lll", scripts=False, tests=False, tier="L")
    _routing_eval(lll)
    _skill(tmp_path, name="nope", scripts=False, tests=False)
    rep = mod.survey(tmp_path, roles_dir=None, registry=None, entities_dir=None, strict=False)
    assert rep["total"] == 3
    assert rep["by_tier"]["D"] == 1
    assert rep["by_tier"]["L"] == 1
    assert rep["by_tier"]["unclassified (inferred)"] == 1
    assert rep["passing"] == 2 and rep["failing"] == 1


def test_survey_reports_but_does_not_gate(tmp_path):
    """A survey over a roster with known debt must not turn every CI run red — the
    per-skill invocation is the gate."""
    _skill(tmp_path, name="nope", scripts=False, tests=False)
    rc, out, err = _run("--survey", str(tmp_path))
    assert rc == 0
    assert "1 skill(s)" in out and "0 pass" in out


def test_trigger_eval_alone_does_not_infer_a_lens(tmp_path):
    """The backfill's finding, pinned. Inferring L from "no code + a trigger eval"
    labelled `autonomous`, `handoff` and `checkit` as lenses; all three run
    pipelines. A routing eval is tier L's core, not its signature — every tier can
    carry one — so L must be declared, never inferred (BRO-2192)."""
    d = _skill(tmp_path, scripts=False, tests=False)
    _routing_eval(d)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "must be declared" in step2["detail"]


def test_latent_only_plus_scripts_still_requires_tests(tmp_path):
    """Pins `require_tests = bool(code)`. The old expression was
    `bool(code) and not latent_only or (latent_only and code)`; routing step 3
    through latent_only at all is what let a skill ship scripts and buy out of
    testing them. Step 2 also fails here (contradiction) — this asserts step 3
    independently, so reverting the expression cannot pass unnoticed."""
    d = _skill(tmp_path, tests=False, latent=True)
    step3 = _step(_check(d), 3)
    assert step3["status"] == "FAIL" and step3["required"]


# ===========================================================================
# P20 round 1 — every blocker and major from two adversarial strata, as fixtures.
# Each test names the finding it pins. All were reproduced as PASSes before the fix.
# ===========================================================================

def _j(tmp_path, **kw):
    d = _skill(tmp_path, scripts=False, tests=False, tier="J")
    _judgment_evals(d, **kw)
    return d


def _l(tmp_path, cases):
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    (d / "evals").mkdir(parents=True, exist_ok=True)
    (d / "evals" / "prompts.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return d


# --- the coverage regression (Strata B blocker 4) -----------------------------

def test_syntax_check_applies_to_every_tier_not_just_d(tmp_path):
    """THE regression this round found. `_script_syntax_error` was called only inside
    the tier-D arm, so `tier: L` bought a skill out of a syntax check origin/main
    applied unconditionally. Declaring a tier must never reduce coverage."""
    d = _l(tmp_path, [{"should_fire": True}, {"should_not_fire": True}])
    (d / "scripts").mkdir(exist_ok=True)
    (d / "scripts" / "do.py").write_text("def f(:\n    return 1\n", encoding="utf-8")
    (d / "tests").mkdir(exist_ok=True)
    (d / "tests" / "test_do.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "syntax error" in step2["detail"]


def test_empty_script_is_not_a_deterministic_core(tmp_path):
    """codex blocker 1: py_compile is happy with 0 bytes, so `touch scripts/noop.py`
    satisfied tier D."""
    d = _skill(tmp_path, tests=False, tier="D")
    (d / "scripts" / "do.py").write_text("", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "empty script" in step2["detail"]


def test_extensionless_executable_counts_as_code(tmp_path):
    """codex blocker 6: `scripts/run` with a shebang shipped untested, because
    'code' keyed off five suffixes."""
    d = _l(tmp_path, [{"should_fire": True}, {"should_not_fire": True}])
    (d / "scripts").mkdir(exist_ok=True)
    run = d / "scripts" / "run"
    run.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
    run.chmod(0o755)
    for t in (d / "tests").glob("*"):
        t.unlink()
    step3 = _step(_check(d), 3)
    assert step3["status"] == "FAIL" and step3["required"]


# --- tier L polarity (codex blocker 2, Strata B blocker 5) --------------------

def test_null_valued_trigger_key_does_not_satisfy_tier_l(tmp_path):
    """The weak-check-made-load-bearing defect, repeated from a sibling PR's step-5
    finding because tier L made the weak check *required*."""
    step2 = _step(_check(_l(tmp_path, [{"should_fire": None}])), 2)
    assert step2["status"] == "FAIL" and step2["required"]


def test_positive_only_routing_eval_fails_tier_l(tmp_path):
    """Both SKILL.md tables claim 'both polarities'; nothing enforced it. A
    positive-only suite structurally cannot see over-triggering."""
    step2 = _step(_check(_l(tmp_path, [{"should_fire": True}])), 2)
    assert step2["status"] == "FAIL"
    assert "negative" in step2["detail"]


def test_negative_only_routing_eval_fails_tier_l(tmp_path):
    step2 = _step(_check(_l(tmp_path, [{"should_not_fire": True}])), 2)
    assert step2["status"] == "FAIL"
    assert "positive" in step2["detail"]


def test_both_polarities_passes_tier_l(tmp_path):
    d = _l(tmp_path, [{"should_fire": True}, {"should_not_fire": True}])
    assert _step(_check(d), 2)["status"] == "PASS"


def test_should_trigger_false_counts_as_the_negative_polarity(tmp_path):
    """Schmid's convention expresses the negative as should_trigger:false rather than
    a separate key; that must satisfy the negative arm."""
    d = _l(tmp_path, [{"should_trigger": True}, {"should_trigger": False}])
    assert _step(_check(d), 2)["status"] == "PASS"


# --- judge shadowing + opt-out (codex blocker 3, Strata B blockers 2 and 3) ---

def test_decoy_blob_cannot_shadow_the_real_execution_contract(tmp_path):
    """codex blocker 3: first-match `_dig` read `judge` from one file and
    `execution_contract` from another, so it compared two configs that never meet."""
    d = _j(tmp_path, judge_model="gpt-5", under_model="gpt-5")
    (d / "evals" / "00-decoy.json").write_text(
        json.dumps({"execution_contract": {"model": "haiku"}}), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL"
    assert "self-judging" in step2["detail"]


def test_two_judge_configs_are_ambiguous_not_first_wins(tmp_path):
    """Strata B blocker 3 in its sharper form: a decoy `judge` sorting first hid the
    real self-judging one entirely."""
    d = _j(tmp_path)
    (d / "evals" / "00-decoy.json").write_text(
        json.dumps({"judge": {"model": "gpt-5", "agreement_floor": 0.8,
                              "agreement_measured": {"value": 0.9, "method": "40 dual-labelled cases"}}}),
        encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL"
    assert "ambiguous" in step2["detail"]


def test_missing_execution_contract_fails_rather_than_warns(tmp_path):
    """Strata B blocker 2: the cross-model requirement was opt-out — omit the
    comparison target and the whole gate degraded to a WARN."""
    d = _j(tmp_path)
    blob = json.loads((d / "evals" / "suite.json").read_text())
    del blob["execution_contract"]
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "nothing to compare" in step2["detail"]


def test_non_mapping_judge_fails_cleanly(tmp_path):
    d = _j(tmp_path)
    (d / "evals" / "suite.json").write_text(json.dumps({"judge": "gpt-5"}), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "not a mapping" in step2["detail"]


# --- the measurement clamp (codex blocker 5, Strata B major 7) ----------------

def test_blank_floor_and_whitespace_measurement_fail(tmp_path):
    """codex blocker 5: `agreement_floor: ""` with whitespace value/method passed."""
    d = _j(tmp_path)
    blob = json.loads((d / "evals" / "suite.json").read_text())
    blob["judge"]["agreement_floor"] = ""
    blob["judge"]["agreement_measured"] = {"value": " ", "method": " "}
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL"


def test_a_measured_agreement_of_zero_is_a_real_measurement(tmp_path):
    """Strata B major 7, the inverse direction. Truthiness got this pair backwards:
    a genuine 0 was reported as 'no measurement' while 'unmeasured' passed."""
    d = _j(tmp_path)
    blob = json.loads((d / "evals" / "suite.json").read_text())
    blob["judge"]["agreement_measured"] = {"value": 0, "method": "40 dual-labelled cases, Krippendorff alpha"}
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


def test_non_numeric_floor_fails(tmp_path):
    d = _j(tmp_path)
    blob = json.loads((d / "evals" / "suite.json").read_text())
    blob["judge"]["agreement_floor"] = "high"
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "must be a number" in step2["detail"]


# --- admission record (codex blocker 4, Strata B major 3) ---------------------

def test_unreadable_admission_fails_closed_without_a_traceback(tmp_path):
    """codex major 2 / Strata B major 5: an uncaught PermissionError instead of a
    structured FAIL. A traceback is worse than a verdict."""
    d = _j(tmp_path)
    f = d / "evals" / "admission.md"
    f.chmod(0o000)
    try:
        step2 = _step(_check(d), 2)
        assert step2["status"] == "FAIL" and step2["required"]
    finally:
        f.chmod(0o644)


# --- rubric + held-out (Strata B majors 1 and 2) -----------------------------

def test_empty_rubric_file_does_not_satisfy_the_rubric_check(tmp_path):
    d = _j(tmp_path)
    (d / "evals" / "rubric.md").write_text("", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "rubric" in step2["detail"]


def test_heading_only_rubric_does_not_count(tmp_path):
    d = _j(tmp_path)
    (d / "evals" / "rubric.md").write_text("# Rubric\n\n## Dimensions\n", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "rubric" in step2["detail"]


def test_a_real_held_out_case_file_counts(tmp_path):
    d = _j(tmp_path, held_out=0)
    ho = d / "evals" / "held-out"
    ho.mkdir(parents=True, exist_ok=True)
    (ho / "case-01.md").write_text("Critique this API design.\n", encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


# --- fail-closed on unparseable artifacts (codex major 1, Strata B major 4) ---

def test_unparseable_eval_artifact_fails_closed_for_tier_j(tmp_path):
    d = _j(tmp_path)
    (d / "evals" / "broken.json").write_text("{not: valid json", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "unparseable" in step2["detail"]


def test_unparseable_eval_artifact_fails_closed_for_tier_l(tmp_path):
    """An unverifiable routing eval is not a routing eval — and the message must say
    'could not parse', not 'no routing eval'."""
    d = _l(tmp_path, [{"should_fire": True}, {"should_not_fire": True}])
    (d / "evals" / "broken.json").write_text("{not: valid json", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "could not be parsed" in step2["detail"]


# --- survey robustness (Strata B major 5, codex minor 1) ---------------------

def test_survey_isolates_a_failing_skill_and_still_reports_the_rest(tmp_path):
    good = _skill(tmp_path, name="good", tier="D")
    bad = _skill(tmp_path, name="bad", tier="D")
    (bad / "scripts" / "do.py").chmod(0o000)
    try:
        rep = mod.survey(tmp_path, roles_dir=None, registry=None, entities_dir=None, strict=False)
        assert rep["total"] == 2
        assert any(r["skill"] == "good" and r["ok"] for r in rep["rows"])
        assert any(r["skill"] == "bad" and not r["ok"] for r in rep["rows"])
    finally:
        (bad / "scripts" / "do.py").chmod(0o644)


def test_survey_plus_positional_is_rejected_not_silently_ignored(tmp_path):
    d = _skill(tmp_path, name="x", tier="D")
    rc, out, err = _run(str(d), "--survey", str(tmp_path))
    assert rc == 2 and "different modes" in err


# --- mutation survivors from the round-1 proof -------------------------------
# Both tests below exist because a mutant SURVIVED: the tests written alongside the
# fix passed for a reason other than the one they claimed to pin.

def test_non_boolean_trigger_values_do_not_establish_polarity(tmp_path):
    """M10 survived: `{"should_fire": null}` fails for the wrong reason (None is
    falsy, so the positive arm stays unset either way). The value that actually
    distinguishes a real-boolean check from a truthiness check is a non-boolean
    truthy/falsy PAIR — under a truthiness reading `1`/`0` looks like both polarities.
    A YAML author writing `should_fire: 1` must not buy a lens gate."""
    d = _l(tmp_path, [{"should_fire": 1}, {"should_fire": 0}])
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "no routing eval" in step2["detail"]


def test_comment_only_script_is_not_a_deterministic_core(tmp_path):
    """Round-2 blocker 1: the round-1 empty-file fix rejected only zero-byte and
    whitespace files, so `# TODO: implement core` still satisfied tier D. A floor on
    substance — NOT a judgement about whether the code is useful, which is undecidable."""
    d = _skill(tmp_path, tier="D")
    (d / "scripts" / "do.py").write_text("#!/usr/bin/env python3\n# TODO: implement core\n",
                                         encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "empty script" in step2["detail"]


def test_unrelated_nested_metadata_does_not_supply_polarity(tmp_path):
    """Round-2 blocker 2: `_polarity_seen` walked the whole document, so
    `{"metadata": {"should_fire": true}, "judge": {"should_trigger": false}}` passed
    tier L with no routing cases at all."""
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    (d / "evals").mkdir(parents=True, exist_ok=True)
    (d / "evals" / "metadata.json").write_text(
        json.dumps({"metadata": {"should_fire": True}, "judge": {"should_trigger": False}}),
        encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]


def test_malformed_decoy_judge_still_counts_as_ambiguity(tmp_path):
    """Round-2 blocker 3: dropping malformed declarations meant a decoy
    `{"judge": "not-a-mapping"}` was ignored, so 'declare exactly one' was unenforced."""
    d = _j(tmp_path)
    (d / "evals" / "decoy.json").write_text(
        json.dumps({"judge": "not-a-mapping"}), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "ambiguous" in step2["detail"]


def test_null_execution_contract_model_is_rejected_not_skipped(tmp_path):
    d = _j(tmp_path)
    (d / "evals" / "decoy.json").write_text(
        json.dumps({"execution_contract": {"model": None}}), encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"  # None means absent, which is fine
    (d / "evals" / "decoy.json").write_text(
        json.dumps({"execution_contract": {"model": ""}}), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "non-empty string" in step2["detail"]


def test_nan_agreement_floor_is_not_a_number(tmp_path):
    """Round-2 blocker 5: NaN passes isinstance(float) but is not a coefficient."""
    d = _j(tmp_path)
    (d / "evals" / "suite.yaml").write_text(
        "judge:\n  model: gpt-5\n  agreement_floor: .nan\n"
        "  agreement_measured:\n    value: 0.9\n    method: 40 dual-labelled cases\n"
        "execution_contract:\n  model: haiku\n", encoding="utf-8")
    (d / "evals" / "suite.json").unlink()
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "must be a number" in step2["detail"]


def test_invalid_utf8_in_skill_md_fails_closed_without_a_traceback(tmp_path):
    """Round-2 blocker 7: one 0xFF byte aborted the entire --survey run."""
    d = tmp_path / "badbytes"
    d.mkdir()
    (d / "SKILL.md").write_bytes(b"---\nname: x\ndescription: \xff\xfe bad\n---\n# body\n")
    res = _check(d)
    step1 = _step(res, 1)
    assert step1["status"] in ("PASS", "FAIL")  # a verdict, not an exception
    rep = mod.survey(tmp_path, roles_dir=None, registry=None, entities_dir=None, strict=False)
    assert rep["total"] == 1


# ===========================================================================
# P20 round 3 — the tier-L gate was proven only against its own fixture shape.
# ===========================================================================

REAL_ROLE_EVAL = """# Resolver-eval fixture in the shape this repo actually ships (roles/*.eval.yaml).
lens: demo

should_fire:
  - "agentic-vps"
  - "set up a vps for autonomous agents"
  - intent: "audit this provisioning script"
    touched_files: ["skills/agentic-vps/scripts/provision.sh"]

should_not_fire:
  - "summarize this PDF in 3 bullets"
  - "fix the bug in foo.rs"
"""


def test_tier_l_accepts_the_real_roles_eval_shape(tmp_path):
    """Round-3 blocker 4, and the most important test in this file. The 14 real
    `roles/*.eval.yaml` fixtures express polarity as top-level keys mapping to LISTS
    of prompts. Requiring booleans would have rejected every one of them — while
    step 5 reported the same file as a valid trigger eval, so the gate contradicted
    itself about one file. Tier L had been proven only against a shape that existed
    nowhere but these tests."""
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    (d / "evals").mkdir(parents=True, exist_ok=True)
    (d / "evals" / "demo.eval.yaml").write_text(REAL_ROLE_EVAL, encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "PASS", step2["detail"]


def test_tier_l_rejects_the_real_shape_when_one_polarity_is_missing(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    (d / "evals").mkdir(parents=True, exist_ok=True)
    (d / "evals" / "demo.eval.yaml").write_text(
        REAL_ROLE_EVAL.split("should_not_fire:")[0], encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "negative" in step2["detail"]


def test_empty_polarity_lists_do_not_count(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    (d / "evals").mkdir(parents=True, exist_ok=True)
    (d / "evals" / "demo.eval.yaml").write_text(
        "lens: demo\nshould_fire: []\nshould_not_fire: []\n", encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "FAIL"


def test_one_self_contradictory_case_does_not_satisfy_both_polarities(tmp_path):
    """Round-3 blocker 3: nothing required the two arms to come from distinct cases,
    so a single case asserting both passed."""
    d = _l(tmp_path, [{"prompt": "x", "should_fire": True, "should_not_fire": True}])
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]


def test_top_level_list_eval_is_visible_not_invisible(tmp_path):
    """Round-3 major 1: keeping only dicts made a well-formed top-level-list prompt
    set invisible, and the gate then reported 'no routing eval' about a file that was
    present and correct."""
    d = _skill(tmp_path, scripts=False, tests=False, tier="L")
    (d / "evals").mkdir(parents=True, exist_ok=True)
    (d / "evals" / "r.json").write_text(json.dumps(
        [{"prompt": "a", "should_fire": True}, {"prompt": "b", "should_not_fire": True}]),
        encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


def test_extensionless_python_script_is_syntax_checked(tmp_path):
    """Round-3 blocker 5: making extensionless files COUNT as code without extending
    the syntax check meant the gate printed `syntax ok` about a file nothing examined."""
    d = _skill(tmp_path, tier="D")
    run = d / "scripts" / "run"
    run.write_text("#!/usr/bin/env python3\ndef f(:\n    pass\n", encoding="utf-8")
    run.chmod(0o755)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "syntax error" in step2["detail"]


def test_fish_shebang_is_not_checked_with_bash(tmp_path):
    """Round-3 major 5: `"sh" in shebang` substring-matched fish and zsh."""
    d = _skill(tmp_path, tier="D")
    run = d / "scripts" / "run"
    run.write_text("#!/usr/bin/env fish\nfunction hi\n  echo hi\nend\n", encoding="utf-8")
    run.chmod(0o755)
    res = _check(d)
    step2 = _step(res, 2)
    assert step2["status"] == "PASS", step2["detail"]
    # and it must NOT claim it checked what it could not check
    assert "syntax ok" not in step2["detail"]
    assert "unchecked" in step2["detail"]


def test_unreadable_template_yaml_fails_closed(tmp_path):
    """Round-3 major 2: three call sites bypassed `_read`'s fail-closed contract."""
    d = _skill(tmp_path, tier="D")
    t = d / "templates"
    t.mkdir(exist_ok=True)
    y = t / "t.yaml"
    y.write_text("script: scripts/do.py\n", encoding="utf-8")
    y.chmod(0o000)
    try:
        res = _check(d)  # must return a verdict, not raise
        assert any(r["step"] == "1c" for r in res)
    finally:
        y.chmod(0o644)


def test_survey_does_not_tally_a_crashed_skill_as_unclassified(tmp_path):
    """Round-3 major 3: a gate bug inflated the very roster bucket the docs quote."""
    good = _skill(tmp_path, name="good", tier="D")
    bad = _skill(tmp_path, name="bad", tier="D")
    (bad / "scripts" / "do.py").chmod(0o000)
    try:
        rep = mod.survey(tmp_path, roles_dir=None, registry=None, entities_dir=None, strict=False)
        assert rep["by_tier"].get("unclassified (inferred)", 0) == 0
    finally:
        (bad / "scripts" / "do.py").chmod(0o644)


# ===========================================================================
# P20 verify round — 4 blockers, one of them a false FAIL introduced in round 3.
# ===========================================================================

def test_docstring_only_script_is_not_a_deterministic_core(tmp_path):
    """Verify-round blocker 1: the round-2 fix checked line PREFIXES, and a module
    docstring's body lines carry none, so a docstring-only file read as executable."""
    d = _skill(tmp_path, tier="D")
    (d / "scripts" / "do.py").write_text(
        '"""Module documentation only.\n\nTODO: implement later.\n"""\n', encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "empty script" in step2["detail"]


def test_a_real_python_script_with_a_docstring_still_counts(tmp_path):
    """Paired control: the fix must not reject a normal module that opens with a
    docstring and then does something."""
    d = _skill(tmp_path, tier="D")
    (d / "scripts" / "do.py").write_text(
        '"""Does a thing."""\n\n\ndef go():\n    return 1\n', encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


def test_comment_only_shell_script_is_not_a_deterministic_core(tmp_path):
    """The non-Python branch of `_has_executable_content`. After the verify round
    Python routes through AST, leaving the line-prefix loop covered by nothing —
    mutant M19 survived until this test existed."""
    d = _skill(tmp_path, tier="D")
    for f in (d / "scripts").glob("*"):
        f.unlink()
    (d / "scripts" / "do.sh").write_text("#!/bin/bash\n# TODO: implement\n", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "empty script" in step2["detail"]


def test_a_real_shell_script_still_counts(tmp_path):
    d = _skill(tmp_path, tier="D")
    for f in (d / "scripts").glob("*"):
        f.unlink()
    (d / "scripts" / "do.sh").write_text("#!/bin/bash\n# does a thing\necho hi\n", encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


# ===========================================================================
# CONTROL TABLES. The final review's sharpest point was methodological: each
# previous fix was pinned by the ONE sentence from the report, so the next round
# found seven more shapes of the same defect. These tables assert the CLASS.
# ===========================================================================

_RECORD = ("Two independent agents received the same design and a third party found "
           "both answers valid under the written rubric.\n")




# ===========================================================================
# The simplification: prose heuristics deleted. These pin the new contract AND
# stand as permanent regression guards for the eight false-reject classes that
# five rounds of patching kept reintroducing.
# ===========================================================================

# Every one of these was rejected by some earlier draft of the placeholder or
# admission heuristics. They are ordinary things an honest author writes.
FORMERLY_FALSE_REJECTED_METHODS = [
    "Cohen's kappa over 40 held-out cases, excluding 3 with unknown labels",
    "excluded 3 cases with unknown labels",
    "n/a for the control arm",
    "pending review by a second labeller",
    "we guessed nothing: every label was adjudicated",
    "placeholder rows were removed before scoring",
    "Unknown cause.",
    "Write me a concise incident report from these logs.",
    "TBD is not an acceptable answer; explain why.",
]


def test_no_method_prose_is_ever_false_rejected(tmp_path):
    """The regression guard for the whole class. A gate that refuses honest work
    trains people to write for the regex; five rounds of trying to detect evasive
    prose produced a new false reject every time, so the detection was deleted."""
    for i, method in enumerate(FORMERLY_FALSE_REJECTED_METHODS):
        d = _j(tmp_path / f"fm{i}")
        blob = json.loads((d / "evals" / "suite.json").read_text())
        blob["judge"]["agreement_measured"] = {"value": 0.84, "method": method}
        (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "PASS", f"false-rejected {method!r}: {step2['detail']}"


def test_measurement_fields_are_checked_structurally_only(tmp_path):
    """What survives: present and non-empty. `TBD` now PASSES, deliberately — whether
    a filled-in field is honest is the review layer's job, and SKILL.md says so."""
    d = _j(tmp_path)
    blob = json.loads((d / "evals" / "suite.json").read_text())
    blob["judge"]["agreement_measured"] = {"value": 0.9, "method": "TBD"}
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"
    for bad in ("", "   ", None):
        blob["judge"]["agreement_measured"] = {"value": 0.9, "method": bad}
        (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
        assert _step(_check(d), 2)["status"] == "FAIL", f"accepted method={bad!r}"


# --- the declared-outcome contract -------------------------------------------

def _admission(d, text):
    (d / "evals" / "admission.md").write_text(text, encoding="utf-8")


_BODY = "\nTwo agents got the same brief; a third reader judged both answers valid.\n"


def test_declared_outcome_admitted_passes(tmp_path):
    d = _j(tmp_path)
    _admission(d, "---\noutcome: admitted\n---\n" + _BODY)
    assert _step(_check(d), 2)["status"] == "PASS"


def test_declared_outcome_rejected_blocks(tmp_path):
    d = _j(tmp_path)
    _admission(d, "---\noutcome: rejected\n---\n" + _BODY)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "rejected" in step2["detail"]


def test_missing_outcome_field_fails_with_the_template(tmp_path):
    d = _j(tmp_path)
    _admission(d, "# Admission\n" + _BODY)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "outcome: admitted" in step2["detail"]


def test_invalid_outcome_value_fails(tmp_path):
    d = _j(tmp_path)
    _admission(d, "---\noutcome: maybe\n---\n" + _BODY)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "must be" in step2["detail"]


def test_declared_outcome_with_an_empty_body_fails(tmp_path):
    d = _j(tmp_path)
    _admission(d, "---\noutcome: admitted\n---\n\n")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "records nothing" in step2["detail"]


def test_prose_that_broke_every_earlier_scanner_now_passes(tmp_path):
    """The other half of the regression guard. Each body below false-FAILed under some
    earlier draft: a verdict with justification, a quoted rejection from another skill,
    a results table, a body opening "The planned protocol", a backticked verdict."""
    bodies = [
        "Outcome: admitted — both outputs were judged valid; neither was rejected.\n",
        "For comparison, the legacy skill recorded \u201cOutcome: rejected\u201d after its two agents disagreed.\n",
        "| Test | Outcome | Reason |\n|---|---|---|\n| Same prompt | Admitted | Both met the rubric |\n",
        "The planned protocol was completed: two agents, one brief, both answers valid.\n",
        "Result: `admitted`.\n",
        "Neither candidate was rejected by the judge.\n",
    ]
    for i, body in enumerate(bodies):
        d = _j(tmp_path / f"pr{i}")
        _admission(d, "---\noutcome: admitted\n---\n\n" + body)
        step2 = _step(_check(d), 2)
        assert step2["status"] == "PASS", f"false-rejected {body!r}: {step2['detail']}"


# ===========================================================================
# Coverage the simplification orphaned. Deleting the prose heuristics also deleted
# the tests that happened to exercise these still-live checks — five mutants went
# SURVIVED and one MISSED, which is how the gap surfaced.
# ===========================================================================

def test_gitkeep_and_readme_are_not_held_out_cases(tmp_path):
    """`touch evals/held-out/.gitkeep` must not satisfy a held-out case set. Still
    live after the simplification; its former test went with the placeholder logic."""
    d = _j(tmp_path, held_out=0)
    ho = d / "evals" / "held-out"
    ho.mkdir(parents=True, exist_ok=True)
    (ho / ".gitkeep").write_text("", encoding="utf-8")
    (ho / "README.md").write_text("cases go here\n", encoding="utf-8")
    (ho / "notes.log").write_text("scratch output\n", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "held-out" in step2["detail"]


def test_an_empty_held_out_case_file_is_not_a_case(tmp_path):
    d = _j(tmp_path, held_out=0)
    ho = d / "evals" / "held-out"
    ho.mkdir(parents=True, exist_ok=True)
    (ho / "case-01.md").write_text("   \n", encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "FAIL"


def test_held_out_marker_object_without_an_input_is_not_a_case(tmp_path):
    """`cases: [{"held_out": true}]` is a marker, not a case."""
    d = _j(tmp_path, held_out=0)
    blob = json.loads((d / "evals" / "suite.json").read_text())
    blob["cases"] = [{"held_out": True}]
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "held-out" in step2["detail"]


def test_agreement_measured_is_still_required(tmp_path):
    """The clamp that survives the simplification: a floor must carry a measurement
    record. Its fields are checked structurally, but they must be there."""
    d = _j(tmp_path)
    blob = json.loads((d / "evals" / "suite.json").read_text())
    del blob["judge"]["agreement_measured"]
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "agreement_measured" in step2["detail"]


# `_strip_fences` is no longer used by the admission check, but step 1c still relies
# on it: a `scripts/…` path inside a fenced EXAMPLE is not a contract claim.

def _skill_with_fenced_ref(tmp_path, name, fence):
    d = _skill(tmp_path, name=name, tier="D")
    body = (d / "SKILL.md").read_text(encoding="utf-8")
    (d / "SKILL.md").write_text(body + f"\nExample usage:\n\n{fence}\n", encoding="utf-8")
    return d


def test_fenced_example_reference_does_not_break_step_1c(tmp_path):
    for i, fence in enumerate(("```\npython3 scripts/not_shipped.py --flag\n```",
                               "~~~\npython3 scripts/not_shipped.py --flag\n~~~")):
        d = _skill_with_fenced_ref(tmp_path, f"fenced{i}", fence)
        step = _step(_check(d), "1c")
        assert step["status"] == "PASS", f"fence form {i} not stripped: {step['detail']}"


def test_unterminated_fence_still_hides_a_reference(tmp_path):
    d = _skill_with_fenced_ref(tmp_path, "unterm", "```\npython3 scripts/not_shipped.py")
    assert _step(_check(d), "1c")["status"] == "PASS"


def test_html_comment_reference_does_not_break_step_1c(tmp_path):
    d = _skill_with_fenced_ref(tmp_path, "htmlc", "<!--\nscripts/not_shipped.py\n-->")
    assert _step(_check(d), "1c")["status"] == "PASS"


def test_a_real_missing_reference_still_fails_step_1c(tmp_path):
    """Paired control: stripping must not swallow live claims."""
    d = _skill(tmp_path, name="liveref", tier="D")
    body = (d / "SKILL.md").read_text(encoding="utf-8")
    (d / "SKILL.md").write_text(body + "\nRun scripts/not_shipped.py to do the thing.\n",
                                encoding="utf-8")
    step = _step(_check(d), "1c")
    assert step["status"] == "FAIL" and step["required"]


def test_unterminated_html_comment_reference_does_not_break_step_1c(tmp_path):
    """M36 survived because the earlier test used a CLOSED `<!-- -->`, which the first
    regex handles — the unterminated-comment strip was never exercised."""
    d = _skill_with_fenced_ref(tmp_path, "untermhtml", "<!--\nscripts/not_shipped.py")
    assert _step(_check(d), "1c")["status"] == "PASS"


# ===========================================================================
# Round 6. Both strata converged here: the refactor is right and the false-reject
# surface is empirically gone, but the ONE substance floor the deletion left
# standing did not hold.
# ===========================================================================

def test_non_canonical_closing_fences_do_not_defeat_the_body_check(tmp_path):
    """The blocker both strata found. The body strip required a newline AFTER the
    closing fence while the frontmatter parser did not, so on any non-canonical close
    the strip silently missed, `body` became the whole file, and the emptiness test
    passed over 30 bytes containing no record.

    The mutation proof could not see it: M49 mutates the `if not body.strip():`
    consequent and is killed, because the PATTERN was wrong, not the predicate. Six
    variants, one test."""
    for i, raw in enumerate(["---\noutcome: admitted\n---",
                             "---\noutcome: admitted\n--- \n",
                             "---\noutcome: admitted\n---\t\n",
                             "---\noutcome: admitted\n---   ",
                             "---\noutcome: admitted\n---\n",
                             "---\noutcome: admitted\n---\n\n   \n"]):
        d = _j(tmp_path / f"fence{i}")
        (d / "evals" / "admission.md").write_text(raw, encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "FAIL", f"empty record passed for {raw!r}"
        assert "records nothing" in step2["detail"]


def test_a_real_body_after_a_non_canonical_fence_still_passes(tmp_path):
    """Paired control: tightening the pattern must not eat real records."""
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---\noutcome: admitted\n--- \nTwo agents, one brief; a third reader judged "
        "both answers valid.\n", encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


def test_utf8_bom_does_not_hide_frontmatter(tmp_path):
    """A BOM'd record was told to add the frontmatter it visibly already had. Strata B
    measured this as a REGRESSION the refactor introduced — the old prose scanner
    passed the same file."""
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_bytes(
        "﻿---\noutcome: admitted\n---\n\nTwo agents, one brief; both valid.\n"
        .encode("utf-8"))
    assert _step(_check(d), 2)["status"] == "PASS"


def test_the_documented_template_parses_without_pyyaml(tmp_path, monkeypatch):
    """The gate rejected the template it prints itself. `outcome: admitted # or:
    rejected` is the form in `_ADMISSION_TEMPLATE` and in SKILL.md, and the stdlib
    fallback never stripped the YAML comment — so an author copying the remediation
    message was told to add what they already had."""
    # `parse_frontmatter` does a LOCAL `import yaml`, so patching the module
    # attribute does not reach it — an earlier version of this test passed through
    # pyyaml and never exercised the fallback at all (mutant M53 survived on it).
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(mod, "yaml", None)
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---\noutcome: admitted   # or: rejected\n---\n\nTwo agents, one brief.\n",
        encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


def test_a_hash_inside_a_quoted_value_is_not_a_comment(tmp_path, monkeypatch):
    """Control on the comment strip: YAML only starts a comment at ` #` on a PLAIN
    scalar, so a quoted value keeps its hash."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(mod, "yaml", None)
    d = _skill(tmp_path, name="hashy", tier="D")
    (d / "SKILL.md").write_text(
        '---\nname: hashy\ndescription: "issue #42 handling"\ntier: D\n---\n# b\n',
        encoding="utf-8")
    got = mod.parse_frontmatter(d / "SKILL.md")
    assert got["description"] == "issue #42 handling"


def test_duplicate_contradictory_outcome_declarations_fail(tmp_path):
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---\noutcome: rejected\noutcome: admitted\n---\n\nTwo agents, one brief.\n",
        encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "declares `outcome` 2 times" in step2["detail"]


def test_outcome_key_is_matched_case_insensitively(tmp_path):
    """The value was already compared case-insensitively; the key was not, so
    `Outcome: admitted` failed with "declares no outcome"."""
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---\nOutcome: Admitted\n---\n\nTwo agents, one brief; both valid.\n",
        encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


def test_empty_outcome_value_reports_what_the_author_typed(tmp_path):
    """YAML coercion round-tripped through str(), so an empty `outcome:` was reported
    back as the token 'none', which the author never wrote."""
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---\noutcome:\n---\n\nTwo agents, one brief.\n", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "empty `outcome`" in step2["detail"]


def test_unreadable_template_reference_fails_step_1c_closed(tmp_path):
    """Step 1c treated an unreadable artifact as an empty one and PASSed — a
    fail-OPEN on a file nothing could verify."""
    d = _skill(tmp_path, name="unreadtpl", tier="D")
    t = d / "templates"; t.mkdir(exist_ok=True)
    y = t / "t.yaml"
    y.write_text("script: scripts/do.py\n", encoding="utf-8")
    y.chmod(0o000)
    try:
        step = _step(_check(d), "1c")
        assert step["status"] == "FAIL" and "unreadable" in step["detail"]
    finally:
        y.chmod(0o644)


def test_unreadable_eval_artifact_is_reported_as_unverifiable_not_absent(tmp_path):
    """`_load_data`'s OSError path returned None, so an unreadable judge.json was
    invisible and the gate said "no judge config" about a file that exists — the very
    misdiagnosis `_Unparseable` was introduced to prevent."""
    d = _j(tmp_path)
    j = d / "evals" / "suite.json"
    j.chmod(0o000)
    try:
        step2 = _step(_check(d), 2)
        assert step2["status"] == "FAIL" and "unparseable" in step2["detail"]
    finally:
        j.chmod(0o644)


def test_malformed_closing_fence_fails_closed_not_open(tmp_path):
    """The reachable path for the body-extraction `else` branch, which mutant M51
    survived on until this test existed.

    Trailing junk on the closing fence (`---xyz`) is malformed frontmatter. It used to
    be parsed by a laxer second matcher, which let the OUTCOME parse while the body
    match missed — and the old code then returned the input unchanged (fail-OPEN).

    With a single matcher the diagnosis is both accurate and fail-closed: there is no
    valid frontmatter here, so the gate says so rather than inventing a body."""
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---\noutcome: admitted\n---xyz\nTwo agents, one brief; both valid.\n",
        encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and step2["required"]
    assert "outcome" in step2["detail"]


# ===========================================================================
# Round 7. Both blockers were the same shape — a fix applied at one site while its
# sibling kept the old behaviour. Eighth instance in this arc, so the fix is
# structural: ONE frontmatter matcher, and these tests hold it to that.
# ===========================================================================

def test_bom_reaches_the_second_frontmatter_parser_too(tmp_path):
    """THE one-site bug, again. The BOM fix went into `parse_frontmatter`, and
    `_skillsh_frontmatter_issue` kept its own `^---` match — so a BOM'd SKILL.md
    slipped past the skills.sh gotcha detector entirely and step 1 reported
    `skills.sh-parseable` about a file that would not install."""
    d = tmp_path / "bomskill"
    d.mkdir()
    (d / "SKILL.md").write_bytes(
        '﻿---\nname: demo\ndescription: demo\ntags:\n  - "one", "two"\n---\n# body\n'
        .encode("utf-8"))
    assert mod._skillsh_frontmatter_issue(d) is not None
    step1 = _step(_check(d), 1)
    assert step1["status"] == "FAIL" and "skills.sh parser" in step1["detail"]


def test_every_frontmatter_call_site_shares_one_matcher(tmp_path):
    """Guards the structural fix rather than its three symptoms: a BOM'd file must be
    seen identically by the frontmatter parser, the skills.sh detector, and the
    admission reader. Three near-copies of the same regex is what let a fix land at
    one of them twice."""
    src = SCRIPT.read_text(encoding="utf-8")
    # Catch the PATTERN, not one spelling of it: `re.match(...)`, `re.compile(...)`
    # and a BOM-prefixed variant are all ways to reintroduce a second matcher.
    live = [ln for ln in src.splitlines()
            if "---" in ln and re.search(r'r"[^"]*---', ln)
            and not ln.lstrip().startswith("#")
            and "_FRONTMATTER_RE = " not in ln
            and "There used to be" not in ln]
    assert live == [], f"a second frontmatter pattern reappeared: {live}"


def test_duplicate_top_level_outcome_declarations_fail(tmp_path):
    """Duplicates are counted structurally. Case and quoting are not part of a key;
    indentation IS, because it means nesting.

    An earlier version of this test asserted that an INDENTED `  outcome: rejected`
    counted as a duplicate — it encoded the bug rather than the contract, and shipped
    a false reject of a perfectly valid nested key."""
    for i, block in enumerate(['outcome: admitted\nOutcome: rejected',
                               'outcome: admitted\n"Outcome": rejected',
                               "outcome: admitted\n'outcome': admitted",
                               "OUTCOME: admitted\noutcome: admitted"]):
        d = _j(tmp_path / f"dup{i}")
        (d / "evals" / "admission.md").write_text(
            f"---\n{block}\n---\n\nTwo agents, one brief; both valid.\n", encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "FAIL", f"accepted duplicate declarations: {block!r}"
        assert "declares `outcome`" in step2["detail"]


def test_a_nested_outcome_key_is_not_a_duplicate(tmp_path):
    """THE false reject this round found, and it was self-inflicted: making duplicate
    detection indent-insensitive turned a valid nested key into a contradiction."""
    for i, block in enumerate(["outcome: admitted\nmetadata:\n  outcome: rejected",
                               "outcome: admitted\nprior_run:\n  outcome: rejected\n  date: 2026-08-01"]):
        d = _j(tmp_path / f"nest{i}")
        (d / "evals" / "admission.md").write_text(
            f"---\n{block}\n---\n\nTwo agents, one brief; both valid.\n", encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "PASS", f"false-rejected nested key: {step2['detail']}"


def test_a_malformed_closing_fence_does_not_run_on_to_a_later_one(tmp_path):
    """`---xyz` is not a closing fence, so the match ran on to the next real `---`
    and swallowed body text as frontmatter."""
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---\noutcome: admitted\n---xyz\nrecord\n---\nmore record\n", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "malformed frontmatter" in step2["detail"]


def test_empty_outcome_message_is_reachable_without_pyyaml(tmp_path, monkeypatch):
    """On the stdlib path an empty `outcome:` yielded "", indistinguishable from an
    absent key, so the accurate message was unreachable exactly where the fallback
    parser is in use."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(mod, "yaml", None)
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---\noutcome:\n---\n\nTwo agents received the same brief.\n", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "empty `outcome`" in step2["detail"]


def test_frontmatter_without_an_outcome_key_fails(tmp_path):
    """M47 survived: the existing test's file has NO frontmatter at all, so it exits
    at the earlier "has no frontmatter block" guard and never reaches the
    missing-key branch. Valid frontmatter that simply lacks `outcome` is the input
    that exercises it."""
    d = _j(tmp_path)
    _admission(d, "---\nauthor: someone\n---\n" + _BODY)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "declares no `outcome`" in step2["detail"]


def test_a_file_with_no_frontmatter_at_all_fails_distinctly(tmp_path):
    """Paired control: the two failure modes must report differently, or the message
    sends the author looking in the wrong place."""
    d = _j(tmp_path)
    _admission(d, "# Admission\n" + _BODY)
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "no frontmatter block" in step2["detail"]
