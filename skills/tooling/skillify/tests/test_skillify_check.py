"""Tests for skillify_check.py — the skillify doctor.

skillify enforces "every skill ships with tests"; it must therefore ship with
tests itself (dogfood). Hermetic: every fixture is built in a tmp dir.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "skillify_check.py"
_spec = importlib.util.spec_from_file_location("skillify_check", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# --- fixture builders --------------------------------------------------------

def _skill(tmp: Path, *, name="demo", scripts=True, tests=True, latent=False,
           desc="A demo skill.") -> Path:
    d = tmp / name
    (d / "scripts").mkdir(parents=True, exist_ok=True)
    (d / "tests").mkdir(parents=True, exist_ok=True)
    fm = f"---\nname: {name}\ndescription: {desc}\n"
    if latent:
        fm += "latent_only: true\n"
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


def test_latent_only_skill_exempt_from_code(tmp_path):
    d = _skill(tmp_path, scripts=False, tests=False, latent=True)
    res = mod.run_checklist(d, roles_dir=None, registry=None, entities_dir=None, strict=False)
    step2 = next(r for r in res if r["step"] == 2)
    assert step2["status"] == "SKIP"  # composition skill — no scripts required
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
    assert len(payload["results"]) == 12  # ten steps + 1b (installable layout) + 1c (reference integrity)


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
