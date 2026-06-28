"""Tests for the resolver-eval harness + BRO-1338 phrase-matching fix.

Two layers (skillify steps 3 + 4):
  - unit  : _kw_matches / _score_lens / _select_lenses pure functions
  - integ : the `eval` subcommand end-to-end via subprocess over a seeded
            roles/ dir with .eval.yaml fixtures
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "role-x.py"

# --- load the hyphenated module for pure-function unit tests ---
_spec = importlib.util.spec_from_file_location("role_x_mod", SCRIPT)
role_x = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(role_x)


# ──────────────────────────────────────────────────────────────────────────
# Unit — BRO-1338: multi-word / punctuated keywords must match (skillify §3)
# ──────────────────────────────────────────────────────────────────────────

def test_kw_matches_phrase_substring():
    # phrase keyword matches as substring of the raw prompt
    assert role_x._kw_matches("check this out", set(), "yo check this out dude")
    assert not role_x._kw_matches("check this out", {"check", "this", "out"}, "")


def test_kw_matches_slash_token():
    # "/checkit" tokenizes to "checkit" (slash stripped) — must match via prompt_lc
    assert role_x._kw_matches("/checkit", {"checkit"}, "please run /checkit now")


def test_kw_matches_apostrophe_phrase():
    assert role_x._kw_matches("let's research this", set(), "ok let's research this paper")


def test_kw_matches_clean_token_unchanged():
    # clean single token keeps word-boundary set-membership semantics (no regression)
    assert role_x._kw_matches("rust", {"rust", "tokio"}, "rust tokio")
    assert not role_x._kw_matches("rust", {"trust"}, "i trust you")  # no false substring hit


def test_score_lens_phrase_via_prompt_lc():
    lens = {"signals": {"prompt_keywords": ["check this out", "wdyt"]}}
    tokens = role_x._tokenize_prompt("check this out wow")
    b = role_x._score_lens(lens, "", [], tokens, "check this out wow")
    assert b["prompt_keywords"] == 1  # the phrase hit
    # without prompt_lc (legacy direct call) the phrase silently scores 0
    b0 = role_x._score_lens(lens, "", [], tokens)
    assert b0["prompt_keywords"] == 0


# ──────────────────────────────────────────────────────────────────────────
# Unit — _select_lenses honors include_statuses (candidate lenses testable)
# ──────────────────────────────────────────────────────────────────────────

_META = """---
name: _meta
status: active
default_mode: augment
---
# meta
"""

_CANDIDATE_LENS = """---
name: probe
status: candidate
extends: _meta
threshold: 1
signals:
  prompt_keywords:
    - "check this out"
    - "wdyt"
---
# probe lens
"""


def _seed_roles(tmp_path: Path) -> Path:
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "_meta.md").write_text(_META, encoding="utf-8")
    (roles / "probe.md").write_text(_CANDIDATE_LENS, encoding="utf-8")
    return roles


def test_select_excludes_candidate_by_default(tmp_path):
    roles = _seed_roles(tmp_path)
    sel = role_x._select_lenses(roles, {"branch": "", "touched_files": []}, "check this out")
    assert "probe" not in sel["lenses_selected"]  # candidate not scored by default


def test_select_includes_candidate_when_asked(tmp_path):
    roles = _seed_roles(tmp_path)
    sel = role_x._select_lenses(
        roles, {"branch": "", "touched_files": []}, "check this out",
        include_statuses=("active", "candidate"),
    )
    assert "probe" in sel["lenses_selected"]  # phrase fix + status override → fires


# ──────────────────────────────────────────────────────────────────────────
# Integration — the `eval` subcommand end-to-end
# ──────────────────────────────────────────────────────────────────────────

def _run(*args: str, cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(cwd),
        env={**os.environ},
    )
    return r.returncode, r.stdout, r.stderr


def _seed_eval_workspace(tmp_path: Path, fixture: str) -> Path:
    roles = _seed_roles(tmp_path)
    (roles / "probe.eval.yaml").write_text(fixture, encoding="utf-8")
    return roles


def test_eval_passes_when_routing_correct(tmp_path):
    roles = _seed_eval_workspace(tmp_path, (
        "lens: probe\n"
        "should_fire:\n"
        "  - \"check this out https://x.y\"\n"
        "  - \"wdyt about this\"\n"
        "should_not_fire:\n"
        "  - \"summarize this pdf in 3 bullets\"\n"
    ))
    rc, out, err = _run("eval", "--roles-dir", str(roles), cwd=tmp_path)
    assert rc == 0, f"expected pass, rc={rc}\n{out}\n{err}"
    assert "0 failed" in out


def test_eval_fails_on_false_negative(tmp_path):
    # declares a should_fire intent with NO matching keyword → must FAIL (rc 1)
    roles = _seed_eval_workspace(tmp_path, (
        "lens: probe\n"
        "should_fire:\n"
        "  - \"totally unrelated request about the weather\"\n"
    ))
    rc, out, err = _run("eval", "--roles-dir", str(roles), cwd=tmp_path)
    assert rc == 1, f"expected fail rc=1, got {rc}\n{out}"
    assert "FAIL" in out


def test_eval_fails_on_false_positive(tmp_path):
    roles = _seed_eval_workspace(tmp_path, (
        "lens: probe\n"
        "should_not_fire:\n"
        "  - \"check this out\"\n"  # this DOES fire → should_not_fire violated
    ))
    rc, out, err = _run("eval", "--roles-dir", str(roles), cwd=tmp_path)
    assert rc == 1, f"expected fail rc=1, got {rc}\n{out}"


def test_eval_json_output(tmp_path):
    roles = _seed_eval_workspace(tmp_path, (
        "lens: probe\n"
        "should_fire:\n  - \"check this out\"\n"
    ))
    rc, out, err = _run("eval", "--roles-dir", str(roles), "--json", cwd=tmp_path)
    assert rc == 0
    payload = json.loads(out)
    assert payload["passed"] == 1 and payload["failed"] == 0
    assert payload["results"][0]["lens"] == "probe"


def test_eval_no_fixtures_is_clean(tmp_path):
    roles = _seed_roles(tmp_path)  # no .eval.yaml
    rc, out, err = _run("eval", "--roles-dir", str(roles), cwd=tmp_path)
    assert rc == 0


def test_eval_missing_roles_dir(tmp_path):
    rc, out, err = _run("eval", "--roles-dir", str(tmp_path / "nope"), cwd=tmp_path)
    assert rc == 2


# --- CodeRabbit role-x#7: malformed cases must fail loudly, not silently drop ---

def test_eval_fails_on_malformed_case(tmp_path):
    roles = _seed_eval_workspace(tmp_path, (
        "lens: probe\n"
        "should_fire:\n"
        "  - 42\n"                       # int → not a valid case → must FAIL, not drop
        "  - \"check this out\"\n"
    ))
    rc, out, err = _run("eval", "--roles-dir", str(roles), cwd=tmp_path)
    assert rc == 1, f"malformed case must fail, got rc={rc}\n{out}\n{err}"
    assert "malformed" in (out + err).lower()


def test_eval_fails_on_non_mapping_root(tmp_path):
    roles = _seed_roles(tmp_path)
    (roles / "probe.eval.yaml").write_text("- a\n- b\n", encoding="utf-8")  # list, not mapping
    rc, out, err = _run("eval", "--roles-dir", str(roles), cwd=tmp_path)
    assert rc == 1, f"non-mapping root must fail, got rc={rc}\n{out}\n{err}"
    assert "mapping" in (out + err).lower()


def test_eval_json_stdout_clean_on_failure(tmp_path):
    # a failing case with --json must keep stdout pure JSON (log lines → stderr)
    roles = _seed_eval_workspace(tmp_path, (
        "lens: probe\n"
        "should_fire:\n  - \"totally unrelated weather request\"\n"  # will FAIL
    ))
    rc, out, err = _run("eval", "--roles-dir", str(roles), "--json", cwd=tmp_path)
    assert rc == 1
    payload = json.loads(out)  # must parse despite the failure
    assert payload["failed"] == 1
