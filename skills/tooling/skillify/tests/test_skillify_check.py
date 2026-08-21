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
    """An unverifiable routing eval is not a routing eval — and the message must say so,
    not 'no routing eval'.

    The wording is "could not be TRUSTED" rather than "could not be parsed": since the
    duplicate-key guard landed, this branch also fires for artifacts that parse
    perfectly and are merely ambiguous, and calling those a parse failure sent an author
    hunting for a syntax error that was not there."""
    d = _l(tmp_path, [{"should_fire": True}, {"should_not_fire": True}])
    (d / "evals" / "broken.json").write_text("{not: valid json", encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "could not be trusted" in step2["detail"]

    # and the reason must name the actual defect for the ambiguous case too
    d2 = _l(tmp_path / "dup", [{"should_fire": True}, {"should_not_fire": True}])
    (d2 / "evals" / "dup.json").write_text('{"a": 1, "a": 2}', encoding="utf-8")
    step2b = _step(_check(d2), 2)
    assert step2b["status"] == "FAIL" and "duplicate key" in step2b["detail"], step2b["detail"]


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
    """The stdlib fallback must still strip a plain-scalar YAML comment: the template
    this skill prints — `outcome: admitted   # or: rejected` — and `tier: J  # judgment`
    in a SKILL.md both hit that path.

    Tier J's admission record now requires pyyaml outright (a YAML contract cannot be
    gated without a YAML parser), so this asserts against `parse_frontmatter` directly
    rather than through the admission check."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(mod, "yaml", None)
    f = tmp_path / "SKILL.md"
    f.write_text("---\nname: demo\noutcome: admitted   # or: rejected\ntier: D  # deterministic\n---\n# b\n",
                 encoding="utf-8")
    fm = mod.parse_frontmatter(f)
    assert fm["outcome"] == "admitted"
    assert fm["tier"] == "D"



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
    assert step2["status"] == "FAIL" and "does not parse as YAML" in step2["detail"]


def test_tier_j_refuses_to_pass_frontmatter_it_cannot_parse(tmp_path, monkeypatch):
    """The FALSE ACCEPT that ended the review: without pyyaml the duplicate check was
    unavailable AND the hand-rolled parser resolved duplicates last-wins, so

        outcome: rejected
        outcome: admitted

    PASSED — a declared rejection admitted on a stdlib-only box. "Skip rather than
    guess" was right not to guess and wrong about the direction; the gate now refuses
    to pass what it cannot verify."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(mod, "yaml", None)
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---\noutcome: rejected\noutcome: admitted\n---\n\nTwo agents, one brief.\n",
        encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "pyyaml" in step2["detail"]



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


# ===========================================================================
# Round 9. The line-based key walker was replaced by the YAML parser. These are
# the false rejects it produced — every one is valid YAML an author could write.
# ===========================================================================

VALID_FRONTMATTER_MUST_PASS = [
    # a multi-line quoted scalar whose continuation line contains "outcome:"
    'notes: "The prior evaluator recorded\noutcome: rejected"\noutcome: admitted',
    # a key whose VALUE starts with --- (the old ---in-block rule false-rejected this)
    "outcome: admitted\n---source: author-record",
    # nested mappings, flow mappings, and list items are not top-level declarations
    "outcome: admitted\nmetadata:\n  outcome: rejected",
    "outcome: admitted\nprior: {outcome: rejected}",
    "outcome: admitted\nruns:\n  - outcome: rejected",
    "outcome: admitted\nhistory:\n  - {outcome: rejected, date: 2026-08-01}",
    # a block scalar whose body is unindented-looking
    "outcome: admitted\nlog: |\n  outcome: rejected was the first attempt",
]


def test_valid_yaml_frontmatter_is_never_false_rejected(tmp_path):
    """The regression guard for the whole class. A hand-rolled scanner cannot read a
    structured language — it counted keys inside quoted scalars, missed flow mappings
    and list items, and needed an indentation rule that broke on something else. Each
    of these is valid YAML that some earlier draft rejected."""
    for i, block in enumerate(VALID_FRONTMATTER_MUST_PASS):
        d = _j(tmp_path / f"vy{i}")
        (d / "evals" / "admission.md").write_text(
            f"---\n{block}\n---\n\nTwo agents, one brief; both valid.\n", encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "PASS", f"false-rejected valid YAML {block!r}: {step2['detail']}"


def test_duplicate_tier_check_degrades_without_pyyaml_rather_than_guessing(tmp_path, monkeypatch):
    """Honest degradation: with no parser the gate cannot answer the question, so it
    does not answer it. Guessing with a regex is what produced every false reject above.

    This test used to assert a bare `_count_top_level_key(...) is None` and nothing
    else, and its docstring claimed "the record is still read" — which stopped being
    true when tier J began failing closed. P20 round 12 (Strata B) called that out:
    the branch was production-dead and the test's only subject was the dead branch.
    Duplicate-`tier:` detection put it back on a live path, so the test now asserts
    what production actually does — a tier-D skill still passes without pyyaml, and
    the unanswerable duplicate question is skipped rather than guessed at."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(mod, "yaml", None)
    assert mod._count_top_level_key("outcome: admitted", "outcome") is None
    d = _skill(tmp_path, scripts=True, tests=True, tier="D")
    assert mod._duplicate_top_level_key_issue(d / "SKILL.md") is None
    assert _step(_check(d), 2)["status"] == "PASS"


def test_structured_values_are_substantive(tmp_path):
    """Final-round blockers 2 and 3: `_substantive` returned False for dicts and lists,
    so `method: {metric: …, judges: 3}` read as "missing a method" and
    `input: {messages: […]}` read as "not a case". Ordinary YAML, both refused."""
    d = _j(tmp_path, held_out=0)
    blob = json.loads((d / "evals" / "suite.json").read_text())
    blob["judge"]["agreement_measured"] = {
        "value": 0.84,
        "method": {"metric": "Krippendorff alpha", "judges": 3, "cases": 40}}
    blob["cases"] = [{"held_out": True,
                      "input": {"messages": [{"role": "user", "content": "Summarize."}]}}]
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "PASS", step2["detail"]


def test_empty_structured_values_are_not_substantive(tmp_path):
    """Paired control: accepting structure must not accept EMPTY structure."""
    assert mod._substantive({}) is False
    assert mod._substantive([]) is False
    assert mod._substantive({"a": 1}) is True


def test_trailing_whitespace_on_the_opening_fence_is_accepted(tmp_path):
    """Final-round major: `---  \n` is an ordinary opening fence and was refused as
    "has no frontmatter block"."""
    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_text(
        "---  \noutcome: admitted\n---\n\nTwo agents, one brief; both valid.\n",
        encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


def test_a_hollow_tier_j_core_does_not_pass(tmp_path):
    """P20 round 11, Strata A — the FALSE ACCEPT the previous round's own fix created.

    Round 10 fixed a false REJECT (`method: {metric: …, judges: 3}` read as "missing a
    method") by making `_substantive` return `bool(x)` for containers. That was too
    shallow by exactly one level, and it widened SEVEN call sites to fix two: every
    hollow-but-truthy structure then counted as content. A tier-J skill declaring no
    measurement value, no method, no rubric content and no case content passed as
    "rubric + 1 held-out case(s), cross-model judge with a measured floor".

    This is the whole hollow core in one fixture — the reproduction from the report,
    kept as a test so the class cannot come back one field at a time."""
    d = _j(tmp_path, held_out=0)
    (d / "evals" / "rubric.md").unlink()
    blob = json.loads((d / "evals" / "suite.json").read_text())
    blob["judge"]["agreement_measured"] = {"value": {"garbage": None}, "method": {"metric": ""}}
    blob["cases"] = [{"held_out": True, "input": {"messages": []}}]
    blob["rubric"] = {"criterion": {"label": None}}
    (d / "evals" / "suite.json").write_text(json.dumps(blob), encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "FAIL"


def test_substantive_control_table_both_directions():
    """The standing pattern from this arc: never fix the one sentence in the report.

    Every row was run against the shipped predicate. The must-pass column is the
    round-10 false-reject fix, which must survive; the must-fail column is the
    round-11 false-accept fix, which must bite. A future edit that satisfies one
    column by breaking the other fails here rather than in review."""
    must_pass = [
        {"metric": "Krippendorff alpha", "judges": 3, "cases": 40},   # real method
        {"messages": [{"role": "user", "content": "Summarize."}]},    # real case input
        {"a": {"b": {"c": "x"}}},                                     # one real leaf, deep
        {"k": [None, "", 0]},                                         # 0 is a value
        ["a", "b"], 0, 0.5, "text",
    ]
    must_fail = [
        {"garbage": None},                 # value with nothing in it
        {"metric": ""},                    # method with nothing in it
        {"messages": []},                  # case input with nothing in it
        {"criterion": {"label": None}},    # rubric with nothing in it
        {"a": {"b": [{}, [], ""]}},        # hollow all the way down
        {}, [], None, True, False, "   ",
    ]
    for v in must_pass:
        assert mod._substantive(v) is True, f"must pass: {v!r}"
    for v in must_fail:
        assert mod._substantive(v) is False, f"must fail: {v!r}"


def test_substantive_terminates_on_a_cyclic_structure():
    """Recursing to a leaf means a cycle must not become a RecursionError. YAML anchors
    build these, and the gate must fail closed on a cycle rather than crash — but a
    cycle that also holds a real leaf is still substantive."""
    cyclic = {}
    cyclic["self"] = cyclic
    assert mod._substantive(cyclic) is False
    cyclic_with_leaf = ["x"]
    cyclic_with_leaf.append(cyclic_with_leaf)
    assert mod._substantive(cyclic_with_leaf) is True


def test_fence_padding_accepts_typed_whitespace_and_rejects_control_characters(tmp_path):
    """P20 round 11, Strata A (minor). `[^\\S\\n]` also admits form-feed, vertical-tab
    and NBSP. Those matched the fence and then died inside PyYAML with a ReaderError,
    so the gate blamed the YAML for a fence it should never have accepted. Space, tab
    and CR must keep matching — CR because CRLF files are ordinary."""
    # BOTH fences. Round 11 tightened both and asserted only the opening one, so
    # mutant M72 — loosening the CLOSING fence alone — survived all 175 tests. A fix
    # applied at two sites needs a proof at two sites; that is the fourth time in this
    # arc that a one-site proof was written for a two-site fix.
    # NBSP is spelled \u00a0 deliberately: the first version of this test carried the
    # literal character, which is invisible in a diff.
    for ok in (" ", "\t", "  ", ""):
        for where, raw in (
            ("opening", f"---{ok}\noutcome: admitted\n---\n\nTwo agents, one brief.\n"),
            ("closing", f"---\noutcome: admitted\n---{ok}\n\nTwo agents, one brief.\n"),
            ("both",    f"---{ok}\noutcome: admitted\n---{ok}\n\nTwo agents, one brief.\n"),
        ):
            assert mod._frontmatter_match(raw), f"{where} fence must match padding {ok!r}"
    for bad in ("\f", "\v", "\u00a0", "\r"):   # \r joins them: unreachable after _read
        for where, raw in (
            ("opening", f"---{bad}\noutcome: admitted\n---\n\nTwo agents, one brief.\n"),
            ("closing", f"---\noutcome: admitted\n---{bad}\n\nTwo agents, one brief.\n"),
        ):
            assert not mod._frontmatter_match(raw), f"{where} fence must not match {bad!r}"


def test_a_duplicate_tier_declaration_is_ambiguous_not_last_wins(tmp_path):
    """P20 round 12, Strata B — the round-10 duplicate-key false accept, one level up.

    `tier:` decides WHICH gate runs, and YAML resolves duplicates last-wins silently.
    Measured before the fix: a SKILL.md whose line 4 said `tier: J` and line 5 said
    `tier: D` was reported as "tier D (declared)" and PASSED on scripts+tests alone —
    admission record, rubric, held-out cases and judge config never consulted, with
    pyyaml present. The detector already existed in this file; it had been pointed at
    only one of the two places the class occurs."""
    for front in ("tier: J\ntier: D", "tier: D\ntier: J", "tier: D\ntier: D"):
        d = _skill(tmp_path / front.replace("\n", "_").replace(":", ""),
                   scripts=True, tests=True, tier=None)
        raw = (d / "SKILL.md").read_text(encoding="utf-8")
        (d / "SKILL.md").write_text(raw.replace("---\n", f"---\n{front}\n", 1), encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "FAIL", f"{front!r} -> {step2['detail']}"
        assert "the same key twice" in step2["detail"], step2["detail"]


def test_a_nested_tier_key_is_not_a_duplicate_declaration(tmp_path):
    """Paired control for the check above: the question is TOP-LEVEL duplicates. A
    `tier:` nested under another mapping is ordinary YAML and must not trip it —
    this is the exact false-reject shape the deleted line-based key walker produced,
    and the reason the count comes from `yaml.compose()` rather than a scan."""
    d = _skill(tmp_path, scripts=True, tests=True, tier="D")
    raw = (d / "SKILL.md").read_text(encoding="utf-8")
    (d / "SKILL.md").write_text(raw.replace("tier: D", "tier: D\nmeta:\n  tier: J", 1),
                                encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "PASS"


def test_crlf_frontmatter_parses_because_reads_are_newline_normalised(tmp_path):
    """CRLF works, and round 11 credited the wrong mechanism for it.

    That commit kept `\\r` in the fence class "because CRLF files are ordinary". They
    are — but `_read` uses `read_text()`, whose universal-newline handling turns CRLF
    (and a lone CR) into `\\n` before the matcher ever runs, so the `\\r` could never
    match anything. P20 round 13 (Strata A) caught the consequence: the CRLF test was
    vacuous, staying green when its own fixture's CRLFs were replaced with LFs.

    The `\\r` is gone from the pattern and this asserts the real mechanism, so it fails
    if either half changes."""
    raw_bytes = b"---\r\noutcome: admitted\r\n---\r\n\r\nTwo agents, one brief; both valid.\r\n"
    f = tmp_path / "probe.md"
    f.write_bytes(raw_bytes)
    assert b"\r\n" in raw_bytes                       # the fixture really is CRLF on disk
    assert "\r" not in mod._read(f)                    # and _read is what removes it
    assert not mod._frontmatter_match(raw_bytes.decode("utf-8"))  # the regex alone would NOT match

    d = _j(tmp_path)
    (d / "evals" / "admission.md").write_bytes(raw_bytes)
    assert _step(_check(d), 2)["status"] == "PASS"


def test_any_duplicated_top_level_key_is_ambiguous_not_just_tier(tmp_path):
    """The FOURTH one-site fix for a several-site class, caught before a reviewer did.

    Round 12 closed duplicate `tier:`. Executed against that commit, three other
    gate-deciding keys were still resolved last-wins in silence. `latent_only` is the
    one that matters: its control — a single `latent_only: true` alongside shipped
    code — FAILs with "latent_only:true but 1 script(s) present — contradiction", and
    duplicating the key to flip it escapes that required FAIL outright.

    Keying the check to a list of names would have been the fifth one-site fix. The
    property is "declare each key once"."""
    for i, extra in enumerate(("latent_only: true\nlatent_only: false",
                               "name: other",
                               "description: A second description.")):
        d = _skill(tmp_path / f"case{i}", scripts=True, tests=True, tier="D")
        raw = (d / "SKILL.md").read_text(encoding="utf-8")
        (d / "SKILL.md").write_text(raw.replace("tier: D", f"tier: D\n{extra}", 1), encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "FAIL", f"{extra!r} -> {step2['detail']}"
        assert "the same key twice" in step2["detail"], step2["detail"]


def test_a_clean_frontmatter_has_no_duplicate_keys(tmp_path):
    """Paired control. Every real SKILL.md in this repo must keep passing: measured,
    0 of 96 carry a duplicate top-level key, so the blanket rule costs nothing."""
    d = _skill(tmp_path, scripts=True, tests=True, tier="D")
    assert mod._duplicate_top_level_key_issue(d / "SKILL.md") is None
    assert mod._duplicate_top_level_keys("a: 1\nb: 2\nc:\n  a: 3\n") == ("ok", [])
    assert mod._duplicate_top_level_keys("a: 1\nb: 2\na: 3\n") == ("ok", [("a", 2)])
    assert mod._duplicate_top_level_keys("a: 1\nb: 2\nA: 3\nb: 4\n") == ("ok", [("a", 2), ("b", 2)])


def test_a_malformed_line_cannot_disable_the_duplicate_check(tmp_path):
    """P20 round 13, Strata A — BLOCKER. Two readers of the same bytes disagreed.

    `parse_frontmatter` falls back to a hand-rolled scanner when YAML rejects a block,
    and that scanner resolves duplicates last-wins. The duplicate check used the YAML
    parser and reported "no duplicates" when compose raised. So ONE malformed line
    turned the check off while values kept flowing:

        tier: J
        tier: D
        broken: [

    -> step 2 PASS, "tier D (declared)", tier-J gate never run. A required gate
    bypassed by adding a broken line."""
    d = _skill(tmp_path, scripts=True, tests=True, tier=None)
    raw = (d / "SKILL.md").read_text(encoding="utf-8")
    (d / "SKILL.md").write_text(
        raw.replace("---\n", "---\ntier: J\ntier: D\nbroken: [\n", 1), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL", step2["detail"]
    assert "does not parse as YAML" in step2["detail"], step2["detail"]


def test_a_wellformed_frontmatter_is_not_called_unparseable(tmp_path):
    """Paired control for the above: the refusal must bite only on real malformation.
    Flow mappings, quoted keys and nested blocks are ordinary YAML and must survive —
    these are the shapes the deleted line-based key walker false-rejected."""
    for i, extra in enumerate((
        'aliases: {a: 1, b: 2}',
        '"quoted": yes',
        'nested:\n  tier: J\n  deep:\n    - 1\n    - 2',
        'anchored: &a hello\nreused: *a',
    )):
        d = _skill(tmp_path / f"ok{i}", scripts=True, tests=True, tier="D")
        raw = (d / "SKILL.md").read_text(encoding="utf-8")
        (d / "SKILL.md").write_text(raw.replace("tier: D", f"tier: D\n{extra}", 1),
                                    encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "PASS", f"{extra!r} -> {step2['detail']}"


def test_frontmatter_keys_are_matched_case_insensitively(tmp_path):
    """P20 round 13, Strata B — MAJOR, and the FIFTH product-level instance of this
    arc's dominant pattern: fixed at `outcome`, never at `tier`.

    `_count_top_level_key` has always lowercased; `_admission_issue` was fixed early to
    match, its comment naming the reason ("an undocumented asymmetry that reads as the
    gate not seeing what is plainly there"). `_tier_of` read `fm.get("tier")`, and there
    the asymmetry is a false ACCEPT rather than a false reject. Measured before the fix:

        Tier: J  + scripts, no J core  ->  PASS "tier D (inferred: ships scripts/ code)"
        tier: J  + scripts, no J core  ->  FAIL "tier J (declared): 4 gap(s)…"

    One capital letter and a declared tier-J skill passes on scripts alone."""
    for i, key in enumerate(("Tier", "TIER", "tIeR")):
        d = _skill(tmp_path / f"case{i}", scripts=True, tests=True, tier=None)
        raw = (d / "SKILL.md").read_text(encoding="utf-8")
        (d / "SKILL.md").write_text(raw.replace("---\n", f"---\n{key}: J\n", 1), encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "FAIL", f"{key} -> {step2['detail']}"
        assert "tier J (declared)" in step2["detail"], step2["detail"]


def test_case_insensitive_lookup_reaches_every_frontmatter_read(tmp_path):
    """Paired control, and the reason this is an accessor rather than a `tier` patch:
    fixing one key would have been the sixth one-site fix in this arc. `name`,
    `description` and `latent_only` must honour the same rule."""
    assert mod._fm({"Name": "x"}, "name") == "x"
    assert mod._fm({"DESCRIPTION": "d"}, "description") == "d"
    assert mod._fm({"Latent_Only": "true"}, "latent_only") == "true"
    assert mod._fm({"tier": "D"}, "tier") == "D"
    assert mod._fm({}, "tier", "fallback") == "fallback"
    assert mod._fm(None, "tier", "fallback") == "fallback"
    # a capitalised latent_only must still reach the contradiction check
    d = _skill(tmp_path, scripts=True, tests=True, tier=None)
    raw = (d / "SKILL.md").read_text(encoding="utf-8")
    (d / "SKILL.md").write_text(raw.replace("---\n", "---\nLatent_Only: true\n", 1), encoding="utf-8")
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "contradiction" in step2["detail"], step2["detail"]


def test_absurdly_nested_values_fail_closed_instead_of_raising(tmp_path):
    """P20 round 13, Strata B — a regression round 11 introduced with the recursion.

    `_substantive` shipped with a cycle guard but no depth cap, so a 1.4 KB
    evals/suite.json nested ~500 deep raised RecursionError out of `run_checklist`:
    a bare traceback and zero checklist lines, violating this file's own contract that
    an unverified artifact is reported, never thrown. Before round 11, `bool(x)` could
    not recurse at all, so this is strictly a defect of the fix."""
    def nest(n):
        v = "x"
        for _ in range(n):
            v = {"a": v}
        return v

    assert mod._substantive(nest(600)) is False     # fails closed, does not raise
    assert mod._substantive(nest(20)) is True       # control: real nesting still counts

    # End to end. The nested value is spliced in as TEXT rather than built with
    # json.dumps: encoding a deeply nested object recurses inside the encoder, and the
    # first version of this test — depth 2000 through json.dumps — passed locally on
    # 3.12 and raised RecursionError on CI's 3.11. The TEST blew the stack, not the
    # gate, which is the failure this very test exists to rule out. Depth 120 clears
    # the cap of 100 and depends on no interpreter's stack headroom.
    depth = 120
    deep_json = '{"a":' * depth + '"x"' + "}" * depth
    d = _j(tmp_path, held_out=0)
    blob = json.loads((d / "evals" / "suite.json").read_text())
    blob["judge"]["agreement_measured"] = {"value": 0.84, "method": "__DEEP__"}
    text = json.dumps(blob).replace('"__DEEP__"', deep_json)
    assert json.loads(text)["judge"]["agreement_measured"]["method"] != "__DEEP__"
    (d / "evals" / "suite.json").write_text(text, encoding="utf-8")
    assert _step(_check(d), 2)["status"] == "FAIL"


def test_the_nesting_cap_counts_depth_not_containers_visited():
    """The cap is `len(_seen) >= _MAX_NESTING`, and `_seen` is a frozenset rebuilt per
    call — every sibling receives the SAME parent set, so it measures depth along one
    path. Had it been a mutable accumulator shared across siblings it would count
    containers VISITED, and an ordinary wide suite would false-reject.

    That distinction is invisible in the source and would survive any test that only
    nests deeply, so it is pinned here: 501 siblings at depth 3 must pass, and a
    200-case held-out suite of realistic shape must pass."""
    wide = {"cases": [{"input": {"text": ""}} for _ in range(500)]
                     + [{"input": {"text": "real"}}]}
    assert mod._substantive(wide) is True
    assert mod._substantive({"cases": [{"input": {"text": ""}} for _ in range(500)]}) is False

    realistic = {"judge": {"model": "gpt-5", "agreement_floor": 0.7,
                           "agreement_measured": {"value": 0.84,
                                                  "method": {"metric": "alpha", "judges": 3}}},
                 "cases": [{"held_out": True,
                            "input": {"messages": [{"role": "user", "content": "Summarize."}]}}
                           for _ in range(200)]}
    assert mod._substantive(realistic) is True

    # and the boundary itself, so a silent off-by-one in the cap is visible
    def nest(n):
        v = "x"
        for _ in range(n):
            v = {"a": v}
        return v
    assert mod._substantive(nest(100)) is True
    assert mod._substantive(nest(101)) is False


def _demo(tmp: Path, front: str) -> Path:
    d = tmp / "demo"
    (d / "scripts").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "scripts" / "do.py").write_text("print('hi')\n", encoding="utf-8")
    (d / "tests" / "test_do.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (d / "SKILL.md").write_text(f"---\n{front}\n---\n# body\n", encoding="utf-8")
    return d


def test_a_yaml_tag_cannot_hide_a_tier_declaration(tmp_path):
    """P20 round 14, Strata B — BLOCKER, and the SEVENTH instance of this arc's pattern.

    Round 13 refused blocks where `yaml.compose` raised. But the hand-rolled scanner in
    `parse_frontmatter` is entered when **`yaml.safe_load`** raises or returns a
    non-mapping, which is a different and much larger condition: `compose` builds a node
    tree without CONSTRUCTING values, so a custom or unknown tag composes perfectly and
    `safe_load`s not at all.

        tier: J
        extra: {x: !!foo 1,
        tier: D
        }

    compose -> MappingNode, one top-level `tier`, value J. safe_load -> ConstructorError.
    So the duplicate check said "ok", the scanner took last-wins `tier: D`, and the whole
    gate exited 0 with "PASS — all required steps complete" while the only parser that
    parses the block declares tier J. The site here is not a call site — it is WHICH
    FAILURE CONDITION the refusal keys on."""
    for i, front in enumerate((
        "name: demo\ndescription: d\ntier: J\nextra: {x: !!foo 1,\ntier: D\n}",
        "name: demo\ndescription: d\ntier: J\ncfg: {region: !Ref AWS::Region,\ntier: D\n}",
        'name: demo\ndescription: d\ntier: J\nnote: "see\ntier: D\nend"\nmodel: !env MODEL',
        "- a\n- b",                                   # parses, but not to a mapping
    )):
        d = _demo(tmp_path / f"bypass{i}", front)
        step2 = _step(_check(d), 2)
        assert step2["status"] == "FAIL", f"{front!r} -> {step2['detail']}"
        assert "does not parse as YAML" in step2["detail"], step2["detail"]


def test_legitimate_yaml_still_parses_after_the_disagreement_refusal(tmp_path):
    """Paired control, and the one that matters: the refusal keys on `safe_load`
    failing, which is a BROAD condition. Every ordinary YAML shape must survive it —
    these are exactly the shapes the deleted line-based walker used to false-reject."""
    for i, front in enumerate((
        "name: demo\ndescription: d\ntier: D",
        "name: demo\ndescription: d\ntier: D\naliases: {a: 1, b: 2}",
        "name: demo\ndescription: d\ntier: D\nanchored: &a hi\nreused: *a",
        "name: demo\ndescription: d\ntier: D\nbase: &b {x: 1}\nm:\n  <<: *b",
        "name: demo\ndescription: d\ntier: D\nlong: >-\n  folded prose here",
        "name: demo\ndescription: d\ntier: D\nmeta:\n  tier: J",
        'name: demo\ndescription: d\ntier: D\n"quoted": yes',
    )):
        d = _demo(tmp_path / f"ok{i}", front)
        step2 = _step(_check(d), 2)
        assert step2["status"] == "PASS", f"{front!r} -> {step2['detail']}"


def test_a_yaml_tag_cannot_hide_a_rejected_admission(tmp_path):
    """The SECOND site of the same class, also from round 14. `outcome:` is read through
    `parse_frontmatter`, so a block `safe_load` rejects lets the scanner's last-wins
    value stand — a declared `outcome: rejected` was reported as admitted, which is the
    single most load-bearing declaration in tier J."""
    d = _j(tmp_path / "hidden")
    (d / "evals" / "admission.md").write_text(
        "---\noutcome: rejected\nmeta: {ref: !Ref x,\noutcome: admitted\n}\n---\n\n"
        "Two agents; the brief was ambiguous.\n", encoding="utf-8")
    assert mod.parse_frontmatter(d / "evals" / "admission.md")["outcome"] == "admitted"
    step2 = _step(_check(d), 2)
    assert step2["status"] == "FAIL" and "does not parse as YAML" in step2["detail"], step2["detail"]

    ok = _j(tmp_path / "ok")          # control: an ordinary admitted record still passes
    assert _step(_check(ok), 2)["status"] == "PASS"


def test_parse_frontmatter_status_names_which_reader_answered(tmp_path):
    """The status is the whole fix, so it is asserted directly rather than only through
    the gates. `FM_FALLBACK` must mean exactly "a parser exists and the scanner ran"."""
    def st(text):
        f = tmp_path / "probe.md"
        f.write_text(text, encoding="utf-8")
        return mod.parse_frontmatter_status(f)[0]
    assert st("---\na: 1\n---\nbody\n") == mod.FM_YAML
    # An EMPTY block is well-formed YAML that happens to be empty, and must not be
    # called a parse failure. Note the shape: `---\n---\n` does not match the fence
    # regex at all (it needs a line between the fences), so the reachable empty block
    # is `---\n\n---\n` — which is what the code's `data is None and not block.strip()`
    # branch actually sees.
    assert st("---\n---\nbody\n") == mod.FM_ABSENT
    assert st("---\n\n---\nbody\n") == mod.FM_YAML
    assert st("no frontmatter here\n") == mod.FM_ABSENT
    assert st("---\na: !!foo 1\n---\nbody\n") == mod.FM_FALLBACK
    assert st("---\nbroken: [\n---\nbody\n") == mod.FM_FALLBACK
    assert st("---\n- a\n- b\n---\nbody\n") == mod.FM_FALLBACK


def _jsuite(root: Path, suite_text: str, suffix: str = "yaml") -> Path:
    (root / "evals" / "held-out").mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: jdup\ndescription: A judgment skill.\ntier: J\n---\n# jdup\n", encoding="utf-8")
    (root / "evals" / "admission.md").write_text(
        "---\noutcome: admitted\n---\nTwo agents, one brief; a third judged both valid.\n",
        encoding="utf-8")
    (root / "evals" / "rubric.md").write_text("# Rubric\n- specificity\n", encoding="utf-8")
    (root / "evals" / "held-out" / "case1.md").write_text("A held-out case prompt.\n", encoding="utf-8")
    (root / "evals" / f"suite.{suffix}").write_text(suite_text, encoding="utf-8")
    return root


_DUP_YAML = """judge:
  model: gpt-5
  agreement_floor: 0.8
  agreement_measured: {value: 0.84, method: 40 hand-labelled cases, two raters}
execution_contract:
  model: gpt-5
execution_contract:
  model: claude-opus-4
"""
_CLEAN_YAML = _DUP_YAML.replace("execution_contract:\n  model: gpt-5\n", "", 1)
_JUDGE = ('{"judge": {"model":"gpt-5","agreement_floor":0.8,'
          '"agreement_measured":{"value":0.84,"method":"40 cases"}}, ')
_DUP_JSON = _JUDGE + '"execution_contract": {"model":"gpt-5"}, "execution_contract": {"model":"claude-opus-4"}}'
_CLEAN_JSON = _JUDGE + '"execution_contract": {"model":"claude-opus-4"}}'


def test_a_duplicate_key_in_an_eval_artifact_cannot_hide_a_self_judging_declaration(tmp_path):
    """The SEVENTH instance of this arc's pattern, and the one that reaches furthest.

    The duplicate-key class was fixed three times, each time in `SKILL.md`: `outcome:`,
    then `tier:`, then key-agnostically. The commit that made it key-agnostic said "a
    future gate-deciding key should be covered the day it is added rather than the day
    someone remembers to enumerate it" — and `evals/*`, the documents carrying tier J's
    ENTIRE contract, were still read with plain `safe_load`/`json.loads`, both last-wins
    and silent.

    Measured: a duplicated `execution_contract:` hid a self-judging declaration and the
    gate printed "cross-model judge with a measured floor". Its control — the same file
    with the discarded line removed — FAILs with "judge.model == a model under eval". So
    the bypass is a pass the gate would refuse if the hidden line were the only one."""
    for i, (text, suffix) in enumerate(((_DUP_YAML, "yaml"), (_DUP_JSON, "json"))):
        d = _jsuite(tmp_path / f"dup{i}", text, suffix)
        step2 = _step(_check(d), 2)
        assert step2["status"] == "FAIL", f"{suffix} -> {step2['detail']}"
        assert "duplicate key" in step2["detail"], step2["detail"]


def test_a_clean_eval_artifact_still_passes(tmp_path):
    """Paired control in both formats: the refusal must bite only on real duplicates."""
    for i, (text, suffix) in enumerate(((_CLEAN_YAML, "yaml"), (_CLEAN_JSON, "json"))):
        d = _jsuite(tmp_path / f"ok{i}", text, suffix)
        step2 = _step(_check(d), 2)
        assert step2["status"] == "PASS", f"{suffix} -> {step2['detail']}"


def test_a_capitalised_name_key_reports_instead_of_raising(tmp_path):
    """A regression I shipped, seven lines from the fix that was meant to prevent it.

    `f6b1bfc` converted the frontmatter GUARD to `_fm(fm, "name")` and left the REPORT
    three lines below reading `fm['name']`. A capitalised `Name:` then passed the guard
    and raised an uncaught KeyError — exit 1, zero bytes of stdout, a bare traceback
    where the parent commit printed a clean diagnosis. The commit message for that very
    edit claimed "every gate-affecting read goes here … there are no per-key
    exceptions"; there was one, in the same hunk."""
    d = _skill(tmp_path, scripts=True, tests=True, tier="D")
    raw = (d / "SKILL.md").read_text(encoding="utf-8")
    (d / "SKILL.md").write_text(raw.replace("name: demo", "Name: demo", 1), encoding="utf-8")
    res = _check(d)                                    # must not raise
    assert _step(res, 1)["status"] == "PASS"
    assert "name=demo" in _step(res, 1)["detail"]


def test_deeply_nested_artifacts_report_rather_than_throw(tmp_path):
    """Round 13 capped `_substantive` and left three siblings uncovered — `_load_data`'s
    json arm (`except ValueError` does not catch RecursionError, while the yaml arm's
    `except Exception` does), `_internal_ref_issues`' `skill.json` read, and its `_walk`,
    which had no cap at all. The file's own contract is that an unverified artifact is
    reported, never thrown."""
    # Two DIFFERENT guards, needing different depths to be reached — which the first
    # version of this test got wrong: it used 5000 for skill.json, `json.loads` parses
    # 5000 happily (it only raises around 10000+), so `_walk`'s cap fired and the
    # `except RecursionError` on the json read was never exercised. Mutant M90 SURVIVED
    # against it. Measured rather than assumed: json.loads depth 5000 -> parses;
    # 10000 / 20000 / 40000 -> RecursionError.
    for name, rel, depth in (
        ("suite_parse", "evals/suite.json", 20000),   # json.loads raises -> _load_data guard
        ("sj_parse",    "skill.json",       20000),   # json.loads raises -> skill.json guard
        ("sj_walk",     "skill.json",        5000),   # json.loads parses -> _walk depth cap
    ):
        d = _skill(tmp_path / name, scripts=True, tests=True, tier="D")
        (d / "evals").mkdir(exist_ok=True)
        (d / rel).write_text("[" * depth + "1" + "]" * depth, encoding="utf-8")
        res = _check(d)                                # must not raise
        assert isinstance(res, list) and res, f"{rel}@{depth}"


def test_camelcase_negative_polarity_is_recognised(tmp_path):
    """`shouldTrigger` was in `_POSITIVE_KEYS` and `TRIGGER_ASSERTION_KEYS`;
    `shouldNotTrigger` was in neither. So a legitimate camelCase routing eval was
    false-rejected for "asserts only one polarity" while step 5 called the same file a
    valid trigger eval — the self-contradiction `_blob_polarity`'s docstring warns
    about. One accommodation added at one of its two sites."""
    for keys in (("shouldTrigger", "shouldNotTrigger"),
                 ("should_trigger", "should_not_trigger")):
        d = _l(tmp_path / keys[0], cases=[])
        (d / "evals" / "prompts.json").write_text(
            json.dumps({keys[0]: ["review this diff for slop"],
                        keys[1]: ["what is the weather"]}), encoding="utf-8")
        step2 = _step(_check(d), 2)
        assert step2["status"] == "PASS", f"{keys} -> {step2['detail']}"


def test_no_reader_bypasses_the_shared_guards():
    """The answer to sixteen rounds of one-site fixes, made machine-checkable.

    Seven confirmed instances of "a fix landed at ONE site of a class with several",
    and a full reader inventory in round 16 found four MORE sites of two classes that
    had been declared closed one commit earlier. Patching each new site as it surfaces
    is what produced that sequence. So the guards now live in three helpers, and this
    test fails if any reader is added that does not go through them:

      * `_ext(path)`      — casefolded suffix. A `scripts/core.PY` used to skip the
                            tier-D syntax check AND the unit-test step; an
                            `evals/broken.YAML` made an unparseable eval invisible.
      * `_json_loads(txt)`— duplicate-key hook. A duplicated `entrypoint` in skill.json
                            hid a broken reference from the REQUIRED step 1c.
      * `_ast_parse(txt)` — folds RecursionError/MemoryError into SyntaxError, so a
                            generated script reports instead of printing a traceback.

    This is a source scan, which is a weaker instrument than a behavioural test — it
    can be fooled by aliasing or by `getattr`. It is here for the property no
    behavioural test can express: that a reader *not yet written* inherits the guard.
    The behavioural tests above cover the sites that exist today."""
    src = (Path(mod.__file__).read_text(encoding="utf-8")).splitlines()

    def offenders(needle: str, allowed_in: str) -> list[str]:
        out, current_def = [], ""
        for i, line in enumerate(src, 1):
            stripped = line.lstrip()
            if stripped.startswith("def "):
                current_def = stripped[4:].split("(")[0]
            if needle in line and not stripped.startswith("#"):
                if current_def == allowed_in:
                    continue
                out.append(f"{i}: {stripped[:90]}")
        return out

    assert not offenders(".suffix", "_ext"), (
        "raw .suffix outside _ext — case-sensitive extension matching is how "
        f"scripts/core.PY skipped two required steps:\n" + "\n".join(offenders(".suffix", "_ext")))
    assert not offenders("json.loads(", "_json_loads"), (
        "raw json.loads outside _json_loads — no duplicate-key hook:\n"
        + "\n".join(offenders("json.loads(", "_json_loads")))
    assert not offenders("ast.parse(", "_ast_parse"), (
        "raw ast.parse outside _ast_parse — RecursionError/MemoryError escape as "
        "tracebacks:\n" + "\n".join(offenders("ast.parse(", "_ast_parse")))


def test_the_shared_guards_actually_guard():
    """Paired control for the scan above: a source scan proves routing, not behaviour.
    These three assertions prove the helpers do the thing the scan assumes."""
    assert mod._ext(Path("a/core.PY")) == ".py"
    assert mod._ext(Path("a/broken.YAML")) == ".yaml"
    assert mod._ext(Path("a/noext")) == ""

    assert mod._json_loads('{"a": 1}') == {"a": 1}
    try:
        mod._json_loads('{"a": 1, "a": 2}')
        raise AssertionError("duplicate key must refuse")
    except ValueError as e:
        assert getattr(e, "key", None) == "a"

    assert mod._ast_parse("x = 1").body
    try:
        mod._ast_parse("x = " + "1+" * 100000 + "1")
        # some interpreters parse this fine; that is acceptable, the guard is for the
        # ones that do not
    except SyntaxError:
        pass
    except (RecursionError, MemoryError) as e:
        raise AssertionError(f"{type(e).__name__} escaped _ast_parse") from e


def _with_timeout(seconds, fn, *a, **kw):
    """Run `fn` under a hard wall-clock limit, raising TimeoutError if it does not
    return. Needed because the defect these tests cover is NON-TERMINATION: without a
    limit the mutant that removes the cycle guard would hang the suite instead of
    failing it, and a hung sweep reports nothing at all."""
    import signal
    if not hasattr(signal, "SIGALRM"):            # pragma: no cover - platform guard
        return fn(*a, **kw)

    def _boom(signum, frame):
        raise TimeoutError("did not terminate")

    old = signal.signal(signal.SIGALRM, _boom)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn(*a, **kw)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def test_a_recursive_yaml_anchor_terminates(tmp_path):
    """P20 round 16 — the worst defect of the arc, and mine.

    `_duplicate_key_in_node` walks the compose node graph. `yaml.compose` registers an
    anchor BEFORE composing its children, so

        cases: &x
          nested: *x

    yields a CYCLIC node graph. `safe_load` accepts the document; the walk popped the
    same MappingNode and pushed it back forever. No output, no exit code, no traceback
    — and `--survey` hung with it, because `survey()`'s per-skill `except Exception`
    cannot catch a loop that never raises. A fail-closed gate turned into a silent one,
    which is strictly worse than the last-wins bypass the function was added to close.

    `_substantive` twelve lines up has carried this exact guard since round 11, with a
    comment naming YAML anchors. It was not carried over — the eighth instance of this
    arc's dominant class, committed in the fix for the seventh."""
    cyclic = "cases: &x\n  nested: *x\n"
    assert _with_timeout(10, mod._duplicate_key_in_node, cyclic) is None

    d = _j(tmp_path)
    (d / "evals" / "cyc.yaml").write_text(cyclic, encoding="utf-8")
    res = _with_timeout(20, _check, d)
    assert isinstance(res, list) and res

    # control: a NON-recursive anchor is ordinary YAML and must still be walked
    assert _with_timeout(10, mod._duplicate_key_in_node, "a: &x {p: 1}\nb: *x\n") is None
    assert _with_timeout(10, mod._duplicate_key_in_node, "a: &x {p: 1}\nb: *x\na: 2\n") == "a"


def test_repeated_merge_keys_are_not_duplicates():
    """`<<` is the merge key. Repeating it is legal YAML and PyYAML merges the
    referents deterministically, so it is NOT last-wins — reporting it as a duplicate
    was both a false reject and a factually wrong message."""
    merged = ("defaults: &d\n  a: 1\nextra: &e\n  b: 2\n"
              "m:\n  <<: *d\n  <<: *e\n  c: 3\n")
    assert mod._duplicate_key_in_node(merged) is None
    import yaml as _y
    assert _y.safe_load(merged)["m"] == {"a": 1, "b": 2, "c": 3}   # the merge is real
    # control: an ordinary repeated key alongside merge keys is still caught
    assert mod._duplicate_key_in_node(merged.replace("  c: 3\n", "  c: 3\n  c: 4\n")) == "c"


def test_a_duplicate_entrypoint_in_skill_json_is_reported_not_swallowed(tmp_path):
    """The eighth-site fix, and its own first attempt was wrong in an instructive way.

    Adding `object_pairs_hook` made the duplicate RAISE — into an `except ValueError`
    that set `data = None`, which skips the entrypoint check entirely and PASSES. The
    defect was detected and then discarded. Detecting and dropping is worse than not
    detecting: the gate then holds evidence it is ignoring."""
    d = _skill(tmp_path / "dup", scripts=True, tests=True, tier="D")
    (d / "skill.json").write_text(
        '{"name": "d", "entrypoint": "scripts/nope.py", "entrypoint": "scripts/do.py"}',
        encoding="utf-8")
    step = _step(_check(d), "1c")
    assert step["status"] == "FAIL" and "twice" in step["detail"], step["detail"]

    ok = _skill(tmp_path / "ok", scripts=True, tests=True, tier="D")
    (ok / "skill.json").write_text('{"name": "ok", "entrypoint": "scripts/do.py"}', encoding="utf-8")
    assert _step(_check(ok), "1c")["status"] == "PASS"


def test_uppercase_extensions_are_the_same_kind_of_file(tmp_path):
    """`scripts/core.PY` was not code, so tier D never syntax-checked it and step 3 said
    "no code to test" — two REQUIRED steps bypassed by byte-identical content under a
    different filename. Note the fixtures need distinct DIRECTORIES: macOS is
    case-insensitive, so `ext-PY/` and `ext-py/` are one directory and an earlier
    version of this check silently compared a tree with itself."""
    verdicts = {}
    for label, ext in (("upper", "PY"), ("lower", "py")):
        d = _skill(tmp_path / label, scripts=False, tests=False, tier="L")
        (d / "scripts").mkdir(exist_ok=True)
        (d / "evals").mkdir(exist_ok=True)
        (d / "scripts" / f"core.{ext}").write_text("def broken(:\n", encoding="utf-8")
        (d / "evals" / "routing.json").write_text(
            json.dumps({"should_fire": ["a"], "should_not_fire": ["b"]}), encoding="utf-8")
        res = _check(d)
        verdicts[label] = (_step(res, 2)["status"], _step(res, 3)["status"])
    assert verdicts["upper"] == verdicts["lower"] == ("FAIL", "FAIL"), verdicts
