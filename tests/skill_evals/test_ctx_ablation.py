"""Tests for the context-ablation harness (scripts/skill_evals/ctx_ablation/).

The danger in this harness is not a crash. It is a number that looks like a result:
an arm that silently injected nothing and scores like bare ("role-x adds nothing"),
a grader that passes a run with the control removed, a lift computed against a
defaulted zero. So most of these tests are VACUITY tests, each of which fails if
one of those holes opens:

* every committed task fails a null run, fails its control-removed exemplar and
  passes its pass exemplar (``test_every_task_grader_needs_its_control``);
* validation refuses the three static shapes of a vacuous grader;
* a live trial whose arm did not deliver its injection is void, not graded;
* calibration retains a task only if the bare arm failed it, and ``run`` refuses to
  run without a calibration;
* the stubs reproduce the traps they stand for (list_agents' defaults, an
  unpinned merge), so a task graded on them measures the real reflex.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals.ctx_ablation import arms as A  # noqa: E402
from skill_evals.ctx_ablation import fixture as F  # noqa: E402
from skill_evals.ctx_ablation import graders as G  # noqa: E402
from skill_evals.ctx_ablation import metrics as M  # noqa: E402
from skill_evals.ctx_ablation import run as R  # noqa: E402
from skill_evals.ctx_ablation import tasks as T  # noqa: E402
from skill_evals.transcript import Transcript  # noqa: E402

TASK_FILE = REPO / "scripts" / "skill_evals" / "ctx_ablation" / "tasks" / "pilot.json"
TASKS, _DOC = T.load_tasks(TASK_FILE)
BY_ID = {t.id: t for t in TASKS}


@pytest.fixture
def corpus(tmp_path) -> F.Corpus:
    """An empty corpus: the graders never read the knowledge snapshot itself."""
    return F.Corpus(tmp_path / "no-corpus")


def _case(tmp_path, fixture=None) -> F.Case:
    return F.build_case(tmp_path / "case", fixture or {}, F.Corpus(tmp_path / "no-corpus"), link_auth=False)


def _raw(task: T.Task) -> dict:
    return next(r for r in _DOC["tasks"] if r["id"] == task.id)


# ---------------------------------------------------------------------------
# THE vacuity test: a grader must fail when its control is removed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task", TASKS, ids=[t.id for t in TASKS])
def test_every_task_grader_needs_its_control(task, tmp_path, corpus):
    """For every committed task: the run with the control removed (the fail
    exemplar: what a session without the injection does) FAILS, a run that did
    nothing FAILS, and the informed run PASSES. A grader that cannot tell the first
    from the last measures nothing, whatever the live numbers say."""
    null_ok, null_res = T.null_run(task, corpus, tmp_path / "null")
    assert not null_ok, f"{task.id}: a run that did nothing passed: {[r.to_dict() for r in null_res]}"
    fail_ok, fail_res = T.run_exemplar(task, "fail", corpus, tmp_path / "fail")
    assert not fail_ok, f"{task.id}: the control-removed run passed: {[r.to_dict() for r in fail_res]}"
    pass_ok, pass_res = T.run_exemplar(task, "pass", corpus, tmp_path / "pass")
    assert pass_ok, f"{task.id}: the informed run failed: {[r.to_dict() for r in pass_res if not r.passed]}"


def test_removing_the_control_from_a_passing_run_flips_the_verdict(tmp_path, corpus):
    """The same list_agents run, with and without the two arguments the memory rule
    supplies: only the version with them returns the whole fleet and passes."""
    task = BY_ID["reflex-paseo-list-agents-fleet"]
    case = F.build_case(tmp_path / "a", task.fixture, corpus, link_auth=False)
    with_ctl = T._perform(case, [{"mcp": "paseo", "tool": "list_agents", "arguments": {"cwd": "/", "limit": 200}}])
    assert T.grade_synthetic(task, case, with_ctl, "57 agents")[0]
    for args in ({"cwd": "/"}, {"limit": 200}, {}):
        case = F.build_case(tmp_path / f"b{len(args)}{sorted(args)}", task.fixture, corpus, link_auth=False)
        without = T._perform(case, [{"mcp": "paseo", "tool": "list_agents", "arguments": args}])
        assert not T.grade_synthetic(task, case, without, "57 agents")[0], args


def test_the_committed_task_file_covers_every_class_and_target():
    assert {t.cls for t in TASKS} == set(T.TASK_CLASSES)
    assert {tg for t in TASKS for tg in t.targets} == set(T.TARGETS)
    assert all(t.rationale and t.origin.get("ref") for t in TASKS)


# ---------------------------------------------------------------------------
# static validation: the three vacuous shapes
# ---------------------------------------------------------------------------


def _mutated(task_id: str, **changes) -> dict:
    raw = json.loads(json.dumps(_raw(BY_ID[task_id])))
    raw.update(changes)
    return raw


def test_a_task_with_no_assertions_is_invalid():
    errors = T.validate_task(_mutated("retrieval-deepseek-harness-cordis", assertions=[]))
    assert any("assertions" in e for e in errors)


def test_a_positive_regex_that_matches_nothing_is_invalid():
    errors = T.validate_task(_mutated("retrieval-deepseek-harness-cordis",
                                      assertions=[{"kind": "answer", "re": ".*"}]))
    assert any("empty string" in e for e in errors)


def test_an_answer_regex_that_matches_the_prompt_is_invalid():
    errors = T.validate_task(_mutated("retrieval-deepseek-harness-cordis",
                                      assertions=[{"kind": "answer", "re": "deepseek"}]))
    assert any("PROMPT" in e for e in errors)


def test_the_empty_regex_rule_reaches_inside_any():
    errors = T.validate_task(_mutated("retrieval-deepseek-harness-cordis", assertions=[
        {"kind": "any", "of": [{"kind": "answer", "re": "Cordis"}, {"kind": "bash", "re": "x?"}]}]))
    assert any("empty string" in e for e in errors)


def test_a_negative_only_task_is_caught_by_the_null_run(tmp_path, corpus):
    """Static validation cannot see this one: "did not run rm" is a fine assertion,
    and a task made only of such assertions passes a run that did nothing."""
    raw = _mutated("reflex-trash-scratch-dirs", assertions=[{"kind": "no_bash", "re": "rm\\s+-rf"}])
    assert T.validate_task(raw) == []
    ok, _ = T.null_run(T.parse_task(raw), corpus, tmp_path / "n")
    assert ok, "the null run is what must expose this task"


def test_a_retrieval_task_must_name_its_source_and_a_coordination_task_its_peer():
    r = _mutated("retrieval-deepseek-harness-cordis", source_paths=[])
    assert any("source_paths" in e for e in T.validate_task(r))
    c = _mutated("coord-anyone-else-before-pull", fixture={})
    assert any("ctx_peers" in e for e in T.validate_task(c))


def test_exemplars_are_required():
    assert any("exemplars" in e for e in T.validate_task(_mutated("reflex-bun-biome-scaffold", exemplars={})))


# ---------------------------------------------------------------------------
# arms: explicit settings, the only thing that differs between them
# ---------------------------------------------------------------------------

RT = A.HookRuntime(python="/usr/bin/python3", pythonuserbase="/u/base")


def _hooks(arm_id: str) -> dict:
    return A.build_settings(A.parse_arm(arm_id), Path("/case"), RT)


def test_bare_injects_nothing_but_keeps_the_delete_gate():
    s = _hooks("bare")
    assert s["autoMemoryEnabled"] is False
    assert set(s["hooks"]) == {"PreToolUse"}
    assert "delete_gate.py" in s["hooks"]["PreToolUse"][0]["hooks"][0]["command"]


@pytest.mark.parametrize("arm_id,memory,events", [
    ("memory", True, {"PreToolUse"}),
    ("rolex", False, {"PreToolUse", "UserPromptSubmit"}),
    ("ctx", False, {"PreToolUse", "SessionStart"}),
    ("all", True, {"PreToolUse", "SessionStart", "UserPromptSubmit"}),
    ("rolex-top2", False, {"PreToolUse", "UserPromptSubmit"}),
])
def test_each_arm_registers_exactly_its_injections(arm_id, memory, events):
    s = _hooks(arm_id)
    assert s["autoMemoryEnabled"] is memory
    assert set(s["hooks"]) == events


def test_the_role_x_arm_runs_this_branch_s_hook_with_its_pyyaml():
    cmd = _hooks("rolex")["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert str(A.ROLEX_SCRIPTS / "role-x-intake-hook.sh") in cmd
    assert "PYTHONUSERBASE=/u/base" in cmd  # without it role-x prints nothing in the jail
    assert "ROLE_X_TASK_ENTITY_TOP_N" not in cmd


def test_the_compression_arm_sets_the_role_x_cap():
    cmd = _hooks("rolex-top2")["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "ROLE_X_TASK_ENTITY_TOP_N=2" in cmd
    assert A.parse_arm("rolex-top0").rolex_top_n == 0


def test_the_ctx_arm_runs_the_real_hook():
    cmd = _hooks("ctx")["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert str(A.CTX_SCRIPTS / "ctx-hook.sh") in cmd and cmd.endswith("session-start")


def test_unknown_arms_are_refused():
    for bad in ("nope", "rolex-top99", "rolex-topx"):
        with pytest.raises(ValueError):
            A.parse_arm(bad)


def test_no_arm_touches_the_user_settings_file():
    for arm_id in A.DEFAULT_ARMS:
        assert ".claude/settings.json" not in json.dumps(_hooks(arm_id))


def test_the_cli_argv_loads_only_project_settings_plus_the_arm(tmp_path):
    layout = F.CaseLayout(tmp_path)
    s = type("S", (), {"cli": "claude", "model": "haiku", "timeout": 60})()
    argv = R._argv(s, "hello there friend", layout)
    assert argv[argv.index("--setting-sources") + 1] == "project"
    assert argv[argv.index("--settings") + 1] == str(layout.settings)
    assert "--strict-mcp-config" in argv


# ---------------------------------------------------------------------------
# per-trial proof that the arm delivered its injections
# ---------------------------------------------------------------------------


def _transcript(cwd: str, session_start: str = "") -> Transcript:
    events = [{"type": "system", "subtype": "init", "cwd": cwd, "skills": []}]
    if session_start:
        events.insert(0, {"type": "system", "subtype": "hook_response", "hook_event": "SessionStart",
                          "hook_name": "SessionStart:startup", "output": session_start, "exit_code": 0})
    events.append({"type": "result", "subtype": "success", "is_error": False, "result": "ok"})
    return Transcript(events=events)


def _log_intake(case: F.Case, prompt: str, session: str = "live-session") -> None:
    import hashlib
    path = case.layout.home / ".config" / "broomva" / "role" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps({"event": "intake", "session": session,
                             "prompt_digest": "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()}) + "\n")


PROMPT = "what the deepseek harness architecture?"
BLOCK = "[role-x intake — P17 reflex applied]\nMode: augment"


def test_a_json_hook_counts_only_the_context_the_model_sees():
    wrapped = json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "Shared board facts: x"}})
    t = _transcript("/w", wrapped)
    assert M.hook_outputs(t)[0]["text"] == "Shared board facts: x"
    assert M.hook_outputs(_transcript("/w", "plain text"))[0]["chars"] == len("plain text")


def test_a_ctx_arm_without_the_brief_is_void(tmp_path):
    case = _case(tmp_path)
    t = _transcript(str(case.layout.workspace))
    assert R._outcome_for_injections(A.ARM_REGISTRY["ctx"], case, t, "", PROMPT)[0] == M.INJECTION_MISSING
    t_ok = _transcript(str(case.layout.workspace), A.CTX_MARKER + " (ctx scope broomva)")
    assert R._outcome_for_injections(A.ARM_REGISTRY["ctx"], case, t_ok, "", PROMPT) == ("", "")


def test_the_brief_in_an_arm_without_ctx_is_a_leak(tmp_path):
    case = _case(tmp_path)
    t = _transcript(str(case.layout.workspace), A.CTX_MARKER + " (ctx scope broomva)")
    assert R._outcome_for_injections(A.ARM_REGISTRY["bare"], case, t, "", PROMPT)[0] == M.LEAKED


def test_a_role_x_arm_needs_the_live_hook_to_have_logged_this_prompt(tmp_path):
    case = _case(tmp_path)
    t = _transcript(str(case.layout.workspace))
    arm = A.ARM_REGISTRY["rolex"]
    assert R._outcome_for_injections(arm, case, t, BLOCK, PROMPT)[0] == M.INJECTION_MISSING
    _log_intake(case, PROMPT, session=R.OFFLINE_SESSION)  # the offline run does not count
    assert R._outcome_for_injections(arm, case, t, BLOCK, PROMPT)[0] == M.INJECTION_MISSING
    _log_intake(case, "a different prompt entirely")  # nor does another prompt
    assert R._outcome_for_injections(arm, case, t, BLOCK, PROMPT)[0] == M.INJECTION_MISSING
    _log_intake(case, PROMPT)
    assert R._outcome_for_injections(arm, case, t, BLOCK, PROMPT) == ("", "")
    assert R._outcome_for_injections(A.ARM_REGISTRY["bare"], case, t, "", PROMPT)[0] == M.LEAKED


def test_a_role_x_carve_out_is_graded_not_voided(tmp_path):
    """role-x prints nothing for a two-word prompt in production too; that trial is
    real evidence about the role-x arm, not a failed injection."""
    case = _case(tmp_path)
    t = _transcript(str(case.layout.workspace))
    assert R._outcome_for_injections(A.ARM_REGISTRY["rolex"], case, t, "", "Merge 1857") == ("", "")


def test_a_session_in_another_cwd_is_void_because_its_memory_key_differs(tmp_path):
    case = _case(tmp_path)
    t = _transcript("/somewhere/else")
    assert R._outcome_for_injections(A.ARM_REGISTRY["memory"], case, t, "", PROMPT)[0] == M.ERROR


# ---------------------------------------------------------------------------
# calibration: the control-absent rule
# ---------------------------------------------------------------------------


def _row(task, outcome, arm="bare", trial=1):
    return {"task": task, "arm": arm, "trial": trial, "outcome": outcome, "detail": ""}


def test_calibration_drops_a_task_the_bare_arm_passed_even_once():
    rows = [_row("t", M.FAIL, trial=1), _row("t", M.PASS, trial=2), _row("t", M.FAIL, trial=3)]
    assert R.calibration_verdicts(rows, ["t"], 3)["t"]["verdict"] == R.CALIBRATION_VACUOUS


def test_calibration_retains_a_task_the_bare_arm_always_failed():
    rows = [_row("t", M.FAIL, trial=i) for i in (1, 2, 3)]
    assert R.calibration_verdicts(rows, ["t"], 3)["t"]["verdict"] == R.CALIBRATION_RETAINED


def test_calibration_never_retains_a_task_it_could_not_grade():
    rows = [_row("t", M.ERROR, trial=1), _row("t", M.INJECTION_MISSING, trial=2), _row("t", M.FAIL, trial=3)]
    assert R.calibration_verdicts(rows, ["t"], 3)["t"]["verdict"] == R.CALIBRATION_NO_SIGNAL
    assert R.calibration_verdicts([], ["t"], 3)["t"]["verdict"] == R.CALIBRATION_NO_SIGNAL


def test_calibration_trials_never_become_the_run_s_bare_arm(tmp_path):
    """The run resumes from results.jsonl in its directory. Calibration writes
    elsewhere, so the tasks it selected for failing in bare get a FRESH bare sample
    in the run instead of inheriting 0/3 by construction."""
    assert R.calibration_dir(tmp_path) != tmp_path
    (R.calibration_dir(tmp_path)).mkdir()
    (R.calibration_dir(tmp_path) / "results.jsonl").write_text(json.dumps(_row("t", M.FAIL)) + "\n")
    assert R.load_results(tmp_path) == []


def test_the_pilot_subset_is_round_robin_by_primary_target():
    picked = R.select_round_robin(TASKS, 6)
    firsts = [t.targets[0] for t in picked]
    assert sorted(firsts) == ["ctx", "ctx", "memory", "memory", "rolex", "rolex"]
    assert [t.id for t in picked] == [t.id for t in TASKS if t in picked]  # file order kept
    assert R.select_round_robin(TASKS, 99) == list(TASKS)


def test_run_refuses_without_a_calibration(tmp_path, capsys):
    code = R.main(["run", "--out", str(tmp_path), "--dry-run"])
    assert code == R.EXIT_USAGE
    assert "calibrat" in capsys.readouterr().err


def test_run_drops_tasks_the_calibration_did_not_retain(tmp_path, capsys):
    cal = {"tasks": {t.id: {"verdict": R.CALIBRATION_VACUOUS} for t in TASKS}}
    cal["tasks"]["reflex-bun-biome-scaffold"] = {"verdict": R.CALIBRATION_RETAINED}
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(cal))
    code = R.main(["run", "--out", str(tmp_path), "--calibration", str(path), "--arms", "bare,all", "--dry-run"])
    err = capsys.readouterr().err
    assert code == R.EXIT_OK
    assert "1 tasks x 2 arms" in err
    assert "dropping retrieval-deepseek-harness-cordis: calibration verdict vacuous" in err


# ---------------------------------------------------------------------------
# metrics: never a defaulted zero
# ---------------------------------------------------------------------------


def _res(arm, task, outcome, ctx_tok, **kw):
    return {"arm": arm, "task": task, "trial": kw.pop("trial", 1), "outcome": outcome,
            "context_tokens": ctx_tok, **kw}


def test_injected_tokens_are_measured_against_bare_per_task():
    rows = [_res("bare", "a", M.FAIL, 18000), _res("bare", "b", M.FAIL, 18100),
            _res("all", "a", M.PASS, 29000), _res("all", "b", M.FAIL, 29300)]
    table = {r.arm: r for r in M.aggregate(rows, ["bare", "all"])}
    assert table["all"].injected_tokens == pytest.approx(11100)
    assert table["all"].lift == pytest.approx(0.5)
    assert table["all"].lift_per_1k == pytest.approx(0.5 / 11.1, abs=1e-4)
    assert table["bare"].lift is None


def test_without_a_bare_arm_nothing_is_defaulted_to_zero():
    rows = [_res("all", "a", M.PASS, 29000), _res("all", "b", M.FAIL, 29300)]
    row = M.aggregate(rows, ["all"])[0]
    assert row.injected_tokens is None and row.lift is None and row.lift_per_1k is None


def test_void_trials_are_counted_but_never_graded():
    rows = [_res("bare", "a", M.FAIL, 18000), _res("rolex", "a", M.INJECTION_MISSING, 18000),
            _res("rolex", "a", M.PASS, 21000, trial=2)]
    rolex = {r.arm: r for r in M.aggregate(rows, ["bare", "rolex"])}["rolex"]
    assert (rolex.trials, rolex.graded, rolex.passes) == (2, 1, 1)
    assert rolex.non_outcomes == {M.INJECTION_MISSING: 1}


def test_usage_is_read_from_the_stream():
    t = Transcript(events=[
        {"type": "assistant", "message": {"usage": {"input_tokens": 10, "cache_creation_input_tokens": 7000,
                                                    "cache_read_input_tokens": 11000}}},
        {"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {
            "five_hour": {"utilization": 0.4}, "seven_day": {"utilization": 0.7}}}},
        {"type": "result", "usage": {"input_tokens": 30, "cache_creation_input_tokens": 9000,
                                     "cache_read_input_tokens": 40000, "output_tokens": 800}},
    ])
    assert M.context_tokens(t) == 18010
    assert M.result_usage(t) == {"total_input_tokens": 49030, "output_tokens": 800}
    assert M.rate_limit_utilization(t) == 0.7


# ---------------------------------------------------------------------------
# graders
# ---------------------------------------------------------------------------


def _ctx(case: F.Case, calls, answer="") -> G.GradeContext:
    t = T.synthetic_transcript(calls, answer, str(case.layout.workspace))
    return G.GradeContext(t, case.layout, case.env, case.variables, F.read_stub_logs(case.layout))


def test_listing_a_file_is_not_reading_it(tmp_path):
    case = _case(tmp_path)
    spec = {"kind": "read_source", "paths": ["ws:research/entities/tool/x.md"]}
    ls = _ctx(case, [{"name": "Bash", "input": {"command": "ls research/entities/tool/x.md"}}])
    cat = _ctx(case, [{"name": "Bash", "input": {"command": "cat research/entities/tool/x.md"}}])
    read = _ctx(case, [{"name": "Read", "input": {"file_path": f"{case.layout.workspace}/research/entities/tool/x.md"}}])
    assert not G.run_assertion(ls, spec).passed
    assert G.run_assertion(cat, spec).passed and G.run_assertion(read, spec).passed


def test_a_refused_call_is_not_evidence(tmp_path):
    case = _case(tmp_path)
    ctx = _ctx(case, [{"name": "Read", "input": {"file_path": f"{case.layout.workspace}/a.md"},
                       "refused": True}])
    assert not G.run_assertion(ctx, {"kind": "read_source", "paths": ["ws:a.md"]}).passed


def test_one_unpinned_merge_fails_every_stub_even_beside_a_pinned_one(tmp_path):
    task = BY_ID["reflex-merge-pinned-to-head"]
    case = F.build_case(tmp_path / "c", task.fixture, F.Corpus(tmp_path / "x"), link_auth=False)
    sha = case.variables["sha:feat/bro-1857-gate-docs"]
    calls = T._perform(case, [{"bash": "gh pr merge 1857 --squash"},
                              {"bash": f"gh pr merge 1857 --squash --match-head-commit {sha}"}])
    assert not T.grade_synthetic(task, case, calls, "")[0]


def test_an_unknown_template_variable_fails_the_assertion_instead_of_matching_everything(tmp_path):
    case = _case(tmp_path)
    res = G.run_assertion(_ctx(case, [], "anything"), {"kind": "answer", "re": "${nope}"})
    assert not res.passed and "unknown template variable" in res.detail


def test_grading_against_no_assertions_is_a_failure(tmp_path):
    """Validation refuses an empty assertion list; grade() must too, on its own, so a
    task that reaches it by another road (a filtered list) cannot pass by asserting
    nothing."""
    case = _case(tmp_path)
    passed, results = G.grade(_ctx(case, [], "anything"), [])
    assert passed is False and results == []


def test_a_broken_assertion_is_a_failure_not_a_pass(tmp_path):
    case = _case(tmp_path)
    res = G.run_assertion(_ctx(case, []), {"kind": "git", "args": ["rev-parse", "main"]})
    assert not res.passed and "raised" in res.detail


# ---------------------------------------------------------------------------
# stubs and fixture: the traps are reproduced, and state stays in the case
# ---------------------------------------------------------------------------


def _mcp(case: F.Case, args: dict) -> int:
    call = T._call_mcp(case, {"mcp": "paseo", "tool": "list_agents", "arguments": args})
    return json.loads(call["output"])["count"]


def test_list_agents_reproduces_the_caller_cwd_and_limit_defaults(tmp_path):
    task = BY_ID["reflex-paseo-list-agents-fleet"]
    case = F.build_case(tmp_path / "c", task.fixture, F.Corpus(tmp_path / "x"), link_auth=False)
    assert _mcp(case, {}) == 4
    assert _mcp(case, {"cwd": "/"}) == 50
    assert _mcp(case, {"cwd": "/", "limit": 200}) == 57
    assert _mcp(case, {"cwd": "/", "limit": 200, "includeArchived": True}) == 63


def test_gh_refuses_a_merge_pinned_to_the_wrong_head(tmp_path):
    task = BY_ID["reflex-merge-pinned-to-head"]
    case = F.build_case(tmp_path / "c", task.fixture, F.Corpus(tmp_path / "x"), link_auth=False)
    wrong = subprocess.run(["gh", "pr", "merge", "1857", "--match-head-commit", "0" * 40],
                           cwd=case.layout.workspace, env=case.env, capture_output=True, text=True)
    assert wrong.returncode == 1 and "Head branch was modified" in wrong.stderr
    right = subprocess.run(["gh", "pr", "merge", "1857", "--squash", "--match-head-commit",
                            case.variables["sha:feat/bro-1857-gate-docs"]],
                           cwd=case.layout.workspace, env=case.env, capture_output=True, text=True)
    assert right.returncode == 0 and "Squashed and merged" in right.stdout


def test_the_stubs_shadow_the_real_binaries_and_trash_stays_in_the_case(tmp_path):
    case = _case(tmp_path)
    which = subprocess.run(["sh", "-c", "command -v gh trash p9"], env=case.env, capture_output=True, text=True)
    assert all(line.startswith(str(case.layout.local_bin)) for line in which.stdout.split())
    target = case.layout.home / "scratch" / "d"
    target.mkdir(parents=True)
    subprocess.run(["trash", str(target)], env=case.env, check=True)
    assert not target.exists() and (case.layout.home / ".Trash" / "d").is_dir()


@pytest.mark.parametrize("cmd,blocked", [
    ("rm -rf ~/scratch/a", True), ("rm -r x", True), ("find . -name x -delete", True),
    ("python3 -c 'import shutil; shutil.rmtree(\"x\")'", True), ("git clean -fdx", True),
    ("rm file.txt", False), ("trash ~/scratch/a", False), ("mv a ~/.Trash/", False),
])
def test_the_delete_gate_blocks_irreversible_deletes_only(cmd, blocked, tmp_path):
    case = _case(tmp_path)
    proc = subprocess.run([sys.executable, "-I", str(A.STUBS_DIR / "delete_gate.py")],
                          input=json.dumps({"tool_input": {"command": cmd}}),
                          env={**case.env, "CTXABL_CASE_ROOT": str(case.layout.root)},
                          capture_output=True, text=True)
    assert ('"decision": "block"' in proc.stdout) is blocked


def test_the_ctx_fixture_is_folded_by_ctx_itself(tmp_path):
    task = BY_ID["coord-handoff-live-originator"]
    case = F.build_case(tmp_path / "c", task.fixture, F.Corpus(tmp_path / "x"), link_auth=False)
    assert case.ctx_sessions == len(F.BASELINE_PEERS) + 1


def test_a_peer_that_breaks_the_event_schema_fails_the_build(tmp_path):
    bad = {"ctx_peers": [{"session_id": "has spaces, not an id", "branch": "main", "age_min": 3}]}
    with pytest.raises(F.FixtureError, match="event schema"):
        _case(tmp_path, bad)


def test_the_memory_key_is_the_cli_s_slug_of_the_workspace(tmp_path):
    layout = F.CaseLayout(tmp_path)
    assert layout.memory_dir.parent.name == F.project_slug(layout.workspace)
    assert F.project_slug("/Users/x/broomva") == "-Users-x-broomva"


def test_the_case_home_is_the_jail_and_the_workspace_lives_under_it(tmp_path):
    case = _case(tmp_path)
    assert case.env["HOME"] == str(case.layout.home)
    assert case.layout.workspace.parent == case.layout.home
    assert "ANTHROPIC_API_KEY" not in case.env
