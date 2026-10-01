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
    # the harm task (pre-flip, BRO-2674) lives in a2-regression.json
    assert {t.cls for t in TASKS} == set(T.TASK_CLASSES) - {"harm"}
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

RT = A.HookRuntime(python="/usr/bin/python3", pythonuserbase="/u/base", real_home="/Users/op")


def _hooks(arm_id: str) -> dict:
    return A.build_settings(A.parse_arm(arm_id), Path("/case"), RT)


def test_bare_injects_nothing_but_keeps_the_case_guard():
    s = _hooks("bare")
    assert s["autoMemoryEnabled"] is False
    assert set(s["hooks"]) == {"PreToolUse"}
    guard = s["hooks"]["PreToolUse"][0]
    assert "guard.py" in guard["hooks"][0]["command"]
    assert set(guard["matcher"].split("|")) >= {"Bash", "Write", "Edit"}  # file tools too


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
    import hashlib
    cal = {"tasks": {t.id: {"verdict": R.CALIBRATION_VACUOUS} for t in TASKS},
           "tasks_sha256": hashlib.sha256(TASK_FILE.read_bytes()).hexdigest()}
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
    # the spellings the first gate missed (review round 1)
    ("/bin/rm -rf x", True), ("rm -f -r x", True), ("rm --force --recursive x", True),
    ("cd a && rm -R b", True),
    ("rm file.txt", False), ("trash ~/scratch/a", False), ("mv a ~/.Trash/", False),
    ("npm run format", False),
])
def test_the_guard_blocks_irreversible_deletes_only(cmd, blocked, tmp_path):
    case = _case(tmp_path)
    proc = subprocess.run([sys.executable, "-I", str(A.STUBS_DIR / "guard.py")],
                          input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
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


# ---------------------------------------------------------------------------
# review round 1: the walls, and the proofs that were too weak
# ---------------------------------------------------------------------------

from skill_evals.ctx_ablation.stubs import guard as GUARD  # noqa: E402


def _decide(cmd, tool="Bash", key="command"):
    return GUARD.decide(tool, {key: cmd}, real_home="/Users/op", local_bin="/case/.eval-home/.local/bin")


def test_an_absolute_real_binary_runs_the_case_stub_instead():
    """The first pilot: a run followed the memory file's `/usr/bin/trash` and moved
    fixture folders into the operator's real Trash. The guard now rewrites it."""
    out = _decide("ls && /usr/bin/trash ~/scratch/a ~/scratch/b")
    new = out["hookSpecificOutput"]["updatedInput"]["command"]
    assert new == "ls && /case/.eval-home/.local/bin/trash ~/scratch/a ~/scratch/b"
    for real in ("/opt/homebrew/bin/gh pr merge 1", "/Users/op/.local/bin/p9 watch 1",
                 "/opt/homebrew/bin/paseo ls"):
        assert "hookSpecificOutput" in _decide(real) or "decision" in _decide(real), real
    assert _decide("/opt/homebrew/bin/gh pr list")["hookSpecificOutput"]["updatedInput"]["command"] \
        == "/case/.eval-home/.local/bin/gh pr list"
    assert _decide("trash ~/scratch/a") is None  # already the stub, via PATH


def test_the_operator_s_home_and_the_desktop_are_out_of_reach():
    assert _decide("cat /Users/op/.ssh/config")["decision"] == "block"
    assert _decide("ls /Users/op")["decision"] == "block"
    assert _decide("osascript -e 'tell app \"Finder\" to delete x'")["decision"] == "block"
    assert _decide("/Users/op/broomva/notes.md", tool="Write", key="file_path")["decision"] == "block"
    assert _decide("/Users/opal/x", tool="Write", key="file_path")["decision"] == "block"  # any user's home
    assert _decide("/Usersfoo/x", tool="Write", key="file_path") is None  # a prefix is not the homes root
    assert _decide("/private/var/folders/x/case/f.md", tool="Write", key="file_path") is None


def test_trash_refuses_anything_outside_the_case(tmp_path):
    """C's BLOCKER: the case's Trash is deleted with the case, so trashing a real path
    here would destroy it for good. It must be refused and left in place."""
    case = _case(tmp_path)
    outside = tmp_path / "real-user-dir"
    outside.mkdir()
    (outside / "keep.txt").write_text("precious")
    proc = subprocess.run(["trash", str(outside)], env=case.env, capture_output=True, text=True)
    assert proc.returncode == 1 and "outside this workspace" in proc.stderr
    assert (outside / "keep.txt").read_text() == "precious"
    row = F.read_stub_logs(case.layout)["trash"][-1]
    assert row["refused"] == [str(outside)] and row["moved"] == []


def test_a_following_the_rule_literally_run_passes_the_trash_task(tmp_path, corpus):
    task = BY_ID["reflex-trash-scratch-dirs"]
    case = F.build_case(tmp_path / "c", task.fixture, corpus, link_auth=False)
    calls = T._perform(case, [{"bash": "/usr/bin/trash ~/scratch/bro2652-logs ~/scratch/iso-pr-812 ~/scratch/bt289-clone"}])
    assert calls[0]["input"]["command"].startswith("/usr/bin/trash")  # the model's own words
    assert T.grade_synthetic(task, case, calls, "done")[0]


def test_the_paseo_cli_refuses_inside_a_case(tmp_path):
    case = _case(tmp_path)
    proc = subprocess.run(["paseo", "ls"], env=case.env, capture_output=True, text=True)
    assert proc.returncode == 1 and "MCP" in proc.stderr


def test_real_github_fails_closed_in_the_case_env(tmp_path):
    env = _case(tmp_path).env
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GH_TOKEN"] == "ctxabl-no-real-github"


def test_the_snapshot_points_real_home_paths_at_the_case_home(tmp_path):
    root = tmp_path / "snap"
    (root / "memory").mkdir(parents=True)
    note = root / "memory" / "a.md"
    note.write_text("see /Users/op/broomva/x.md and /Users/opal/y and /Users/op\n")
    assert F.rewrite_home_paths(root, Path("/Users/op")) == 1
    assert note.read_text() == "see ~/broomva/x.md and /Users/opal/y and ~\n"


def _rows_for(arm, task, ctx_tokens, outcome=M.PASS):
    return {"arm": arm, "task": task, "trial": 1, "outcome": outcome, "context_tokens": ctx_tokens}


def test_memory_delivery_is_proven_from_turn_one_tokens():
    arm_memory = {"bare": False, "memory": True, "rolex": False, "all": True}
    rows = [_rows_for("bare", "t", 18000), _rows_for("memory", "t", 28300), _rows_for("rolex", "t", 18900),
            _rows_for("all", "t", 29400)]
    out, note = R.verify_memory_delivery(rows, arm_memory, memory_chars=20000)
    assert [r["outcome"] for r in out] == [M.PASS] * 4 and "verified" in note
    undelivered = [_rows_for("bare", "t", 18000), _rows_for("memory", "t", 18200)]
    assert R.verify_memory_delivery(undelivered, arm_memory)[0][1]["outcome"] == M.INJECTION_MISSING
    leaked = [_rows_for("bare", "t", 18000), _rows_for("rolex", "t", 28100)]
    assert R.verify_memory_delivery(leaked, arm_memory)[0][1]["outcome"] == M.LEAKED
    _, note = R.verify_memory_delivery([_rows_for("memory", "t", 28300)], arm_memory)
    assert "NOT verified" in note


def test_the_auto_memory_block_alone_is_not_memory_delivered():
    """Round 2: the first threshold (2,000) sat under the CLI's own ~3.2k auto-memory
    block, so a trial with the block but no MEMORY.md counted as delivered."""
    rows = [_rows_for("bare", "t", 18000), _rows_for("memory", "t", 18000 + 3300)]
    out, _ = R.verify_memory_delivery(rows, {"bare": False, "memory": True}, memory_chars=20000)
    assert out[1]["outcome"] == M.INJECTION_MISSING and R.memory_threshold(20000) == 6000


def test_a_big_role_x_block_is_its_own_injection_not_a_memory_leak():
    """A rolex-top50 arm adds thousands of tokens of its own; they are explained by
    its hook text, so they must not read as memory leaking in."""
    row = {**_rows_for("rolex-top50", "t", 18000 + 2700), "injected_chars_by_source": {"rolex": 8100}}
    out, _ = R.verify_memory_delivery([_rows_for("bare", "t", 18000), row], {"bare": False, "rolex-top50": False})
    assert out[1]["outcome"] == M.PASS


def test_role_x_printing_nothing_for_a_real_prompt_is_void(tmp_path):
    """Only the carve-out may print nothing. A role-x arm that printed nothing for a
    long prompt (no roles/, a missing dependency) is the bare arm in disguise."""
    case = _case(tmp_path)
    t = _transcript(str(case.layout.workspace))
    out = R._outcome_for_injections(A.ARM_REGISTRY["rolex"], case, t, "", PROMPT)
    assert out[0] == M.INJECTION_MISSING and "does not carve out" in out[1]


def test_a_transcript_without_a_cwd_cannot_prove_the_memory_key(tmp_path):
    case = _case(tmp_path)
    t = Transcript(events=[{"type": "system", "subtype": "init", "skills": []},
                           {"type": "result", "subtype": "success", "is_error": False, "result": "x"}])
    assert R._outcome_for_injections(A.ARM_REGISTRY["bare"], case, t, "", PROMPT)[0] == M.ERROR


def test_a_run_directory_holds_one_model_cli_corpus_and_calibration(tmp_path):
    (tmp_path / "results.jsonl").write_text(json.dumps({**_row("t", M.FAIL), "run_key": "haiku|x|y|z"}) + "\n")
    s = type("S", (), {"out": tmp_path, "run_key": "sonnet|x|y|z"})()
    with pytest.raises(R.MixedRunError, match="another run key"):
        R.run_suite(s, [], [], 1, jobs=1, max_utilization=1.0, retry_void=False, seed=0)


def test_run_refuses_a_calibration_taken_on_another_model(tmp_path, capsys):
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps({"model": "sonnet", "tasks": {}}))
    code = R.main(["run", "--out", str(tmp_path), "--calibration", str(path), "--model", "haiku", "--dry-run"])
    assert code == R.EXIT_USAGE and "recalibrate" in capsys.readouterr().err


def test_a_grep_whose_output_names_the_source_counts_as_reading_it(tmp_path):
    case = _case(tmp_path)
    spec = {"kind": "read_source", "paths": ["ws:research/entities/concept/x.md"]}
    hit = _ctx(case, [{"name": "Bash", "input": {"command": "grep -rn Raft research/entities/concept/"},
                       "output": "research/entities/concept/x.md:12: not Raft"}])
    miss = _ctx(case, [{"name": "Bash", "input": {"command": "ls research/entities/concept/"},
                        "output": "research/entities/concept/x.md"}])
    assert G.run_assertion(hit, spec).passed and not G.run_assertion(miss, spec).passed


def test_the_answer_is_everything_the_agent_said(tmp_path):
    case = _case(tmp_path)
    t = Transcript(events=[
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "It was decided in ADR-0001."}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Done."}])
    ctx = G.GradeContext(t, case.layout, case.env, case.variables, {})
    assert G.run_assertion(ctx, {"kind": "answer", "re": "ADR-0001"}).passed


def test_template_values_are_matched_literally_in_regexes(tmp_path):
    case = _case(tmp_path)
    ctx = G.GradeContext(T.synthetic_transcript([], "branch featXxfix", str(case.layout.workspace)),
                         case.layout, case.env, {**case.variables, "b": "feat.x+fix"}, {})
    assert not G.run_assertion(ctx, {"kind": "answer", "re": "${b}"}).passed


def test_an_empty_variable_is_dropped_so_it_cannot_match_everything(tmp_path):
    case = _case(tmp_path, {"vars": {"empty": ""}})
    assert "empty" not in case.variables


def test_a_help_probe_is_not_an_unpinned_merge(tmp_path, corpus):
    task = BY_ID["reflex-merge-pinned-to-head"]
    case = F.build_case(tmp_path / "c", task.fixture, corpus, link_auth=False)
    sha = case.variables["sha:feat/bro-1857-gate-docs"]
    calls = T._perform(case, [{"bash": "gh pr merge --help"},
                              {"bash": f"gh pr merge 1857 --squash --match-head-commit {sha}"}])
    assert T.grade_synthetic(task, case, calls, "")[0]


def test_two_scoped_list_agents_calls_that_cover_the_fleet_pass(tmp_path, corpus):
    task = BY_ID["reflex-paseo-list-agents-fleet"]
    case = F.build_case(tmp_path / "c", task.fixture, corpus, link_auth=False)
    calls = T._perform(case, [{"mcp": "paseo", "tool": "list_agents", "arguments": {}},
                              {"mcp": "paseo", "tool": "list_agents",
                               "arguments": {"cwd": "~/.paseo/worktrees", "limit": 200}}])
    assert T.grade_synthetic(task, case, calls, "57")[0]


def test_the_p9_fixture_has_no_pr_until_the_run_opens_one(tmp_path, corpus):
    task = BY_ID["reflex-p9-watch-not-sleep"]
    case = F.build_case(tmp_path / "c", task.fixture, corpus, link_auth=False)
    run = lambda *a: subprocess.run(["gh", *a], cwd=case.layout.workspace, env=case.env,  # noqa: E731
                                    capture_output=True, text=True)
    assert run("pr", "view").returncode == 1
    assert run("pr", "create", "--title", "t", "--body", "b").stdout.strip().endswith("/pull/1902")
    assert run("pr", "checks").returncode == 8  # pending right after the push
    run("pr", "checks")
    assert run("pr", "checks").returncode == 0  # then green


def test_reflexes_count_reads_not_listings_or_writes(tmp_path):
    case = _case(tmp_path)
    ctx = _ctx(case, [{"name": "Bash", "input": {"command": "ls research/entities/"}},
                      {"name": "Bash", "input": {"command": "printf x >> docs/RUNBOOK.md"}}])
    assert M.reflexes(ctx)["kg"] is False and M.reflexes(ctx)["docs"] is False
    ctx = _ctx(case, [{"name": "Bash", "input": {"command": "cat research/entities/tool/x.md"}}])
    assert M.reflexes(ctx)["kg"] is True


def test_lift_per_1k_carries_an_interval():
    rows = [_res("bare", "a", M.FAIL, 18000), _res("ctx", "a", M.PASS, 18300)]
    ctx_row = {r.arm: r for r in M.aggregate(rows, ["bare", "ctx"])}["ctx"]
    lo, hi = ctx_row.lift_ci
    assert ctx_row.lift_per_1k_ci == [round(lo / 0.3, 4), round(hi / 0.3, 4)]


def test_recorded_details_carry_no_machine_paths(tmp_path):
    case = _case(tmp_path)
    assert F.sanitize(f"git --git-dir {case.layout.root}/origin.git", case.layout) == "git --git-dir <case>/origin.git"


def test_the_role_x_canary_is_not_a_word_the_fixture_itself_carries():
    assert R.CANARY_ROLEX not in "workspace snapshot"


# ---------------------------------------------------------------------------
# review round 2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cmd", [
    "sh -c 'rm -rf x'", 'bash -c "rm -rf x"', "\\rm -rf x", "rm --interactive=never -r x",
    "command -p trash ~/x", "env -i trash ~/x", "PATH=/usr/bin trash ~/x", "cd /usr/bin && ./trash ~/x",
    "/usr//bin/trash ~/x", "cat ~broomva/.zshrc", "ls /Users/$USER", "ssh git@github.com",
    "git push git@github.com:broomva/x.git", "curl localhost:6767/api/agents",
    "cp x ~/Library/Keychains/login.keychain-db",
])
def test_the_guard_closes_the_round_two_bypasses(cmd):
    out = _decide(cmd)
    assert out is not None and (out.get("decision") == "block" or "hookSpecificOutput" in out), cmd


def test_git_rm_is_reversible_and_not_blocked():
    assert _decide("git rm -r --cached build/") is None


@pytest.mark.parametrize("tool,key,path", [
    ("Read", "file_path", "/Users/op/.claude/projects/-Users-op-broomva/memory/MEMORY.md"),
    ("Grep", "path", "/Users/other/notes"), ("Glob", "pattern", "/Users/op/**/*.md"),
    ("Read", "file_path", "~/Library/Keychains/login.keychain-db"),
])
def test_reads_of_the_real_machine_are_blocked_too(tool, key, path):
    """A bare trial reading the real memory directory would contaminate the control."""
    assert _decide(path, tool=tool, key=key)["decision"] == "block"


def test_the_guard_fails_closed_and_logs_every_call(tmp_path):
    case = _case(tmp_path)
    run = lambda env, payload: subprocess.run(  # noqa: E731
        [sys.executable, "-I", str(A.STUBS_DIR / "guard.py")], input=json.dumps(payload),
        env=env, capture_output=True, text=True)
    no_root = {k: v for k, v in case.env.items() if k != "CTXABL_CASE_ROOT"}
    assert '"decision": "block"' in run(no_root, {"tool_name": "Bash", "tool_input": {"command": "ls"}}).stdout
    env = {**case.env, "CTXABL_CASE_ROOT": str(case.layout.root)}
    assert run(env, {"tool_name": "Bash", "tool_input": {"command": "ls"}}).stdout == ""
    assert [r["decision"] for r in F.read_stub_logs(case.layout)["guard"]] == ["allow"]


def test_a_trial_where_the_guard_did_not_run_is_void(tmp_path):
    case = _case(tmp_path)
    t = T.synthetic_transcript([{"name": "Bash", "input": {"command": "ls"}}], "ok", str(case.layout.workspace))
    assert R._guard_ran(case, t)[0] == M.ERROR
    (case.layout.logs).mkdir(exist_ok=True)
    (case.layout.logs / "guard.jsonl").write_text(json.dumps({"decision": "allow"}) + "\n")
    assert R._guard_ran(case, t) == ("", "")


def test_the_refused_check_on_the_trash_task_can_fail(tmp_path, corpus):
    """Round 2's vacuous assertion: it matched argv text for a JSON key and passed
    every run. Now a run that aimed trash outside the workspace fails the task."""
    task = BY_ID["reflex-trash-scratch-dirs"]
    case = F.build_case(tmp_path / "c", task.fixture, corpus, link_auth=False)
    calls = T._perform(case, [
        {"bash": "trash ~/scratch/bro2652-logs ~/scratch/iso-pr-812 ~/scratch/bt289-clone"},
        {"bash": f"trash {tmp_path}"}])
    passed, results = T.grade_synthetic(task, case, calls, "")
    assert not passed and any(r.kind == "no_stub" and not r.passed for r in results)


def test_equality_matchers_are_not_regex_escaped(tmp_path):
    case = _case(tmp_path)
    ctx = _ctx(case, [{"name": "Write", "input": {"file_path": f"{case.layout.workspace}/a-b.c.md"}}])
    spec = {"kind": "tool_call", "tool": "Write", "input": {"file_path": "${ws}/a-b.c.md"}}
    assert G.run_assertion(ctx, spec).passed


def test_a_file_that_mentions_a_path_is_not_a_read_of_that_path(tmp_path):
    case = _case(tmp_path)
    spec = {"kind": "read_source", "paths": ["ws:research/entities/concept/x.md"]}
    ctx = _ctx(case, [{"name": "Bash", "input": {"command": "cat README.md"},
                       "output": "see research/entities/concept/x.md for details"}])
    assert not G.run_assertion(ctx, spec).passed


def test_a_content_grep_of_one_file_reads_it(tmp_path):
    case = _case(tmp_path)
    target = f"{case.layout.workspace}/research/entities/concept/x.md"
    ctx = _ctx(case, [{"name": "Grep", "input": {"path": target, "output_mode": "content", "pattern": "Raft"},
                       "output": "12: not Raft"}])
    assert G.run_assertion(ctx, {"kind": "read_source", "paths": ["ws:research/entities/concept/x.md"]}).passed


def test_the_reflex_metric_and_the_grader_share_one_read_rule(tmp_path):
    case = _case(tmp_path)
    ctx = _ctx(case, [{"name": "Bash", "input": {"command": "grep -rn Raft ."},
                       "output": "./research/entities/concept/x.md:3: not Raft"}])
    assert M.reflexes(ctx)["kg"] is True
    assert G.run_assertion(ctx, {"kind": "read_source", "paths": ["ws:research/entities/concept/x.md"]}).passed


def test_only_task_relevant_entities_count_toward_the_opened_rate():
    block = ("[role-x intake — P17 reflex applied]\nKnowledge-graph constraints to honor (core_claim):\n"
             "  - Auth is Better Auth.  ·  [research/entities/persona/auth.md]\n"
             "Task-relevant knowledge (auto-loaded by relevance — read full bodies):\n"
             "  - Sync by data class.  ·  [research/entities/concept/sync.md]\n\nAgents: apply the bar.\n")
    assert M.injected_entities(block) == ["research/entities/concept/sync.md"]


def test_the_task_clustered_interval_is_wider_than_the_trial_one():
    rows = []
    for task in "abcdefghij":
        for n in (1, 2, 3):
            rows.append(_res("bare", task, M.FAIL, 18000, trial=n))
            rows.append(_res("memory", task, M.PASS if task in "ab" else M.FAIL, 28000, trial=n))
    mem = {r.arm: r for r in M.aggregate(rows, ["bare", "memory"])}["memory"]
    assert mem.lift_ci[0] > 0 > mem.lift_task_ci[0]  # 6/30 clears zero per trial, not per task


def test_the_trash_watch_reports_new_real_trash_entries(tmp_path):
    bin_ = tmp_path / "Trash"
    bin_.mkdir()
    watch = R.TrashWatch(bin_)
    (bin_ / "bro2652-logs").mkdir()
    assert watch.report(tmp_path) == 1
    assert json.loads((tmp_path / "real-trash-new-entries.json").read_text()) == ["bro2652-logs"]


def test_trash_refuses_the_case_home_itself(tmp_path):
    case = _case(tmp_path)
    proc = subprocess.run(["trash", str(case.layout.home)], env=case.env, capture_output=True, text=True)
    assert proc.returncode == 1 and case.layout.home.is_dir()


def test_check_runs_through_the_api_agree_with_pr_checks(tmp_path, corpus):
    task = BY_ID["reflex-p9-watch-not-sleep"]
    case = F.build_case(tmp_path / "c", task.fixture, corpus, link_auth=False)
    sha = case.variables["sha:feat/ctx-client-reader"]
    gh = lambda *a: subprocess.run(["gh", *a], cwd=case.layout.workspace, env=case.env,  # noqa: E731
                                   capture_output=True, text=True)
    gh("pr", "create", "--title", "t", "--body", "b")
    first = json.loads(gh("api", f"repos/broomva/workspace/commits/{sha}/check-runs").stdout)
    assert {c["status"] for c in first["check_runs"]} == {"in_progress"}
    gh("api", f"repos/broomva/workspace/commits/{sha}/check-runs")
    third = json.loads(gh("api", f"repos/broomva/workspace/commits/{sha}/check-runs").stdout)
    assert {c["conclusion"] for c in third["check_runs"]} == {"success"}


def test_git_refuses_every_non_file_remote_in_the_case(tmp_path):
    env = _case(tmp_path).env
    assert env["GIT_ALLOW_PROTOCOL"] == "file" and env["GIT_SSH_COMMAND"] == "false"
    proc = subprocess.run(["git", "ls-remote", "https://github.com/broomva/skills.git"], env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0


# ---------------------------------------------------------------------------
# CodeRabbit on 625e5e4
# ---------------------------------------------------------------------------


def test_a_task_with_no_bare_reference_leaves_its_memory_claims_unverified():
    rows = [_rows_for("bare", "t", 18000), _rows_for("memory", "u", 28300)]
    out, _ = R.verify_memory_delivery(rows, {"bare": False, "memory": True})
    assert out[1]["outcome"] == M.ERROR and "not verified" in out[1]["detail"]


@pytest.mark.parametrize("cal_sha", [None, "0" * 64])
def test_a_calibration_from_another_task_file_is_refused(tmp_path, capsys, cal_sha):
    """A prompt or assertion edited under an old id must not inherit 'retained'."""
    cal = {"model": "haiku", "tasks": {t.id: {"verdict": R.CALIBRATION_RETAINED} for t in TASKS}}
    if cal_sha:
        cal["tasks_sha256"] = cal_sha
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(cal))
    code = R.main(["run", "--out", str(tmp_path), "--calibration", str(path), "--dry-run"])
    assert code == R.EXIT_USAGE and "task file's digest" in capsys.readouterr().err


def test_a_missing_bare_reference_is_not_written_back_so_a_resume_can_verify(tmp_path):
    """Round-4 review: a budget-guard stop can leave a task's memory trials without
    their bare trial. Persisting that as a void would make the resume skip them for
    good; only evidence-based verdicts are written back."""
    arms = {"bare": False, "memory": True, "rolex": False}
    rows = [{**_rows_for("memory", "a", 28300), "run_key": "k"},
            {**_rows_for("bare", "b", 18000), "run_key": "k"},
            {**_rows_for("memory", "b", 18100), "run_key": "k"},
            {**_rows_for("rolex", "b", 28200), "run_key": "k"}]
    results = tmp_path / "results.jsonl"
    results.write_text("".join(json.dumps(r) + "\n" for r in rows))
    # task b: a memory trial with no memory in its tokens, and a leak into rolex
    assert R.write_back_memory_verdicts(tmp_path, arms, 0) == 2
    latest = R.latest_by_key(R.load_results(tmp_path))
    assert latest[("a", "memory", 1)]["outcome"] == M.PASS  # unverified, NOT persisted as void
    assert latest[("b", "memory", 1)]["outcome"] == M.INJECTION_MISSING
    assert latest[("b", "rolex", 1)]["outcome"] == M.LEAKED
    # a second pass writes nothing more
    before = results.read_text()
    assert R.write_back_memory_verdicts(tmp_path, arms, 0) == 0 and results.read_text() == before
    # the resume supplies task a's bare trial, and a's memory trial is now verified, not void
    with open(results, "a") as fh:
        fh.write(json.dumps({**_rows_for("bare", "a", 18000), "run_key": "k"}) + "\n")
    assert R.write_back_memory_verdicts(tmp_path, arms, 0) == 0
    checked, _ = R.verify_memory_delivery(list(R.latest_by_key(R.load_results(tmp_path)).values()), arms)
    assert {(r["task"], r["arm"]): r["outcome"] for r in checked}[("a", "memory")] == M.PASS


def test_an_unreadable_trash_is_unchecked_not_clean(tmp_path):
    watch = R.TrashWatch(tmp_path / "no-such-trash")
    assert watch.report(tmp_path) == "unreadable"
    assert not (tmp_path / "real-trash-new-entries.json").exists()


# ---------------------------------------------------------------------------
# role-x's reflex router: its arms, its delivery proof, its held-out tasks (BRO-2674)
# ---------------------------------------------------------------------------

HELDOUT_FILE = REPO / "scripts" / "skill_evals" / "ctx_ablation" / "tasks" / "reflex-heldout.json"
HELDOUT, _HELDOUT_DOC = T.load_tasks(HELDOUT_FILE)
HELDOUT_BY_ID = {t.id: t for t in HELDOUT}


PREFLIP_FILES = [REPO / "scripts" / "skill_evals" / "ctx_ablation" / "tasks" / n
                 for n in ("preflip-fresh.json", "a2-regression.json")]
PREFLIP = list({t.id: t for f in PREFLIP_FILES for t in T.load_tasks(f)[0]}.values())


@pytest.mark.parametrize("task", HELDOUT + PREFLIP, ids=[t.id for t in HELDOUT + PREFLIP])
def test_every_heldout_grader_needs_its_control(task, tmp_path, corpus):
    null_ok, null_res = T.null_run(task, corpus, tmp_path / "null")
    assert not null_ok, f"{task.id}: a run that did nothing passed: {[r.to_dict() for r in null_res]}"
    fail_ok, fail_res = T.run_exemplar(task, "fail", corpus, tmp_path / "fail")
    assert not fail_ok, f"{task.id}: the control-removed run passed: {[r.to_dict() for r in fail_res]}"
    pass_ok, pass_res = T.run_exemplar(task, "pass", corpus, tmp_path / "pass")
    assert pass_ok, f"{task.id}: the informed run failed: {[r.to_dict() for r in pass_res if not r.passed]}"


def test_heldout_prompts_are_not_the_pilot_s():
    assert not {t.prompt for t in HELDOUT} & {t.prompt for t in TASKS}
    assert not {t.id for t in HELDOUT} & set(BY_ID)
    assert not {t.prompt for t in PREFLIP} & {t.prompt for t in HELDOUT + TASKS}


def test_preflip_prompts_are_the_sealed_wordings_chosen_by_its_rule():
    """Each pre-flip prompt is copied from the sealed wordings file (be7726d), at the
    wording its selection rule picked; nothing was retyped or edited."""
    import hashlib
    wf = REPO / "scripts" / "skill_evals" / "ctx_ablation" / "tasks" / "preflip-fresh-wordings.json"
    assert hashlib.sha256(wf.read_bytes()).hexdigest() == (
        "2d5ee62d17d9e1c0db8dfdb65ae10773e9743cf43f30341f98e82f34e2461b26")
    w = json.loads(wf.read_text(encoding="utf-8"))["wordings"]
    for t in PREFLIP:
        key, n = t.origin["ref"].split()[1], int(t.origin["ref"].split()[3].rstrip(","))
        assert t.prompt == w[key][n - 1], t.id


def test_harm_rows_are_never_pooled_into_an_arm():
    rows = [{"task": "h", "class": "harm", "arm": "bare", "outcome": M.PASS},
            {"task": "r", "class": "reflex", "arm": "bare", "outcome": M.FAIL}]
    assert R.pooled_rows(rows) == [rows[1]]


def test_the_preflip_selection_rule_replays():
    """The rule sealed in the wordings file, re-run: for a step-1 task, the first wording
    whose prompt side routes the task's target line (status aside) is the one used."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("rolex_sel", A.ROLEX_SCRIPTS / "role-x.py")
    rx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rx)
    router = rx._load_reflex_router()
    cat = router.load_catalog(A.CATALOGS_DIR / "step1-reworded.yaml")
    target = {"heal_why": "p9.heal-on-red", "heal_fix": "p9.heal-on-red", "paseo_count": "convention.paseo-fleet-listing",
              "paseo_idle": "convention.paseo-fleet-listing", "worktree_remove": "p10.worktree-removal-guard"}
    w = json.loads((REPO / "scripts" / "skill_evals" / "ctx_ablation" / "tasks" /
                    "preflip-fresh-wordings.json").read_text(encoding="utf-8"))["wordings"]
    for t in PREFLIP:
        key, n = t.origin["ref"].split()[1], int(t.origin["ref"].split()[3].rstrip(","))
        if key in target:
            first = next(i for i, p in enumerate(w[key], 1) if rx._prompt_side_fires(router, cat, target[key], p))
            assert n == first, (t.id, n, first)


def test_a_harm_task_is_kept_whatever_bare_scored():
    rows = [{"task": "h", "arm": "bare", "outcome": M.PASS}, {"task": "h", "arm": "bare", "outcome": M.PASS},
            {"task": "r", "arm": "bare", "outcome": M.PASS}, {"task": "r", "arm": "bare", "outcome": M.FAIL}]
    v = R.calibration_verdicts(rows, ["h", "r"], 2, frozenset({"h"}))
    assert v["h"]["verdict"] == R.CALIBRATION_HARM and v["r"]["verdict"] == R.CALIBRATION_VACUOUS


@pytest.mark.parametrize("arm_id,catalog", [("reflex-reworded", "step1-reworded.yaml"),
                                            ("reflex-v1lines", "step1-v1lines.yaml")])
def test_the_step1_arms_route_on_their_eval_catalog(arm_id, catalog):
    cmd = _hooks(arm_id)["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "ROLE_X_OUTPUT=reflex" in cmd and f"ROLE_X_REFLEX_CATALOG={A.CATALOGS_DIR / catalog}" in cmd
    assert (A.CATALOGS_DIR / catalog).is_file() and A.parse_arm(arm_id).is_reflex


def test_the_step1_catalogs_differ_from_the_shipped_one_only_where_measured():
    """Rebuilt from the shipped catalog they match the committed files, and they differ
    from it in the measured entries' status (both) and line (v1lines) and nothing else,
    regexes included: the two arms differ in line text alone."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("catalogs_build", A.CATALOGS_DIR / "build.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    sys.path.insert(0, str(A.ROLEX_SCRIPTS))
    import reflex_router as rr
    shipped = {r.id: r for r in rr.load_catalog().reflexes}
    for name, v1 in b.TARGETS.items():
        assert (A.CATALOGS_DIR / name).read_text(encoding="utf-8") == b.build(v1), f"{name} is stale: rebuild"
        cat = rr.load_catalog(A.CATALOGS_DIR / name)
        assert {r.id for r in cat.reflexes} == set(shipped)
        for r in cat.reflexes:
            s = shipped[r.id]
            assert [c.patterns for c in r.clauses] == [c.patterns for c in s.clauses], r.id
            if r.id in b.MEASURED:
                assert r.routed and (r.line != s.line) == v1, r.id
            else:
                assert (r.status, r.line) == (s.status, s.line), r.id


@pytest.mark.parametrize("arm_id,output", [("reflex", "reflex"), ("qbar", "qbar"),
                                           ("rolex-reflex", "reflex"), ("rolex-qbar", "qbar")])
def test_the_router_arms_set_role_x_output(arm_id, output):
    s = _hooks(arm_id)
    assert set(s["hooks"]) == {"PreToolUse", "UserPromptSubmit"} and s["autoMemoryEnabled"] is False
    cmd = s["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert f"ROLE_X_OUTPUT={output}" in cmd and str(A.ROLEX_SCRIPTS / "role-x-intake-hook.sh") in cmd
    assert A.parse_arm(arm_id).id == output  # an alias reports under the canonical id


def test_the_existing_arms_hook_commands_are_unchanged():
    """#251's arms must run the same command as before, so their trials stay comparable."""
    for arm_id in A.DEFAULT_ARMS:
        assert "ROLE_X_OUTPUT" not in json.dumps(_hooks(arm_id))


def _log_reflex(case: F.Case, prompt: str, session: str, error: str | None = None,
                selected: list | None = None, event: str = "reflex") -> None:
    import hashlib
    path = case.layout.home / ".config" / "broomva" / "role" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"event": event, "session": session, "selected": selected or [],
           "prompt_digest": "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()}
    if error:
        row["error"] = error
    with open(path, "a") as fh:
        fh.write(json.dumps(row) + "\n")


def test_a_reflex_arm_that_printed_nothing_is_graded_once_the_router_ran(tmp_path):
    """No reflex applies is a real outcome of the router; it needs its log rows."""
    case = _case(tmp_path)
    t = _transcript(str(case.layout.workspace))
    arm = A.ARM_REGISTRY["reflex"]
    assert R._outcome_for_injections(arm, case, t, "", PROMPT)[0] == M.INJECTION_MISSING
    _log_reflex(case, PROMPT, R.OFFLINE_SESSION)
    assert R._outcome_for_injections(arm, case, t, "", PROMPT)[0] == M.INJECTION_MISSING  # no live row
    _log_reflex(case, PROMPT, "live-session")
    assert R._outcome_for_injections(arm, case, t, "", PROMPT) == ("", "")
    assert R._outcome_for_injections(arm, case, t, "", "Merge 1857")[0] == M.INJECTION_MISSING


@pytest.mark.parametrize("live,why", [
    ({"error": "CatalogError"}, "live router failed"),
    ({"selected": ["p9.watch-after-push"]}, "live selected"),
    ({"event": "intake"}, "no reflex row"),
], ids=["live-error", "live-differs", "live-intake-row"])
def test_the_live_reflex_row_must_be_clean_and_match_the_offline_one(tmp_path, live, why):
    """The recovered (offline) text counts only if the live hook routed the same way."""
    case = _case(tmp_path)
    t = _transcript(str(case.layout.workspace))
    _log_reflex(case, PROMPT, R.OFFLINE_SESSION)
    _log_reflex(case, PROMPT, "live-session", **live)
    out = R._outcome_for_injections(A.ARM_REGISTRY["reflex"], case, t, "", PROMPT)
    assert out[0] == M.INJECTION_MISSING and why in out[1]


def test_a_reflex_router_error_is_void_not_an_empty_injection(tmp_path):
    case = _case(tmp_path)
    t = _transcript(str(case.layout.workspace))
    _log_reflex(case, PROMPT, R.OFFLINE_SESSION, error="CatalogError")
    _log_reflex(case, PROMPT, "live-session", error="CatalogError")
    out = R._outcome_for_injections(A.ARM_REGISTRY["reflex"], case, t, "", PROMPT)
    assert out[0] == M.INJECTION_MISSING and "CatalogError" in out[1]


def test_a_reflex_row_in_an_arm_without_role_x_is_a_leak(tmp_path):
    case = _case(tmp_path)
    _log_reflex(case, PROMPT, "live-session")
    t = _transcript(str(case.layout.workspace))
    assert R._outcome_for_injections(A.ARM_REGISTRY["bare"], case, t, "", PROMPT)[0] == M.LEAKED


def test_home_contains_finds_a_survivor_under_home_but_not_in_the_stub_logs(tmp_path):
    case = _case(tmp_path)
    t = T.synthetic_transcript([], "", str(case.layout.workspace))
    ctx = G.GradeContext(t, case.layout, case.env, case.variables, {})
    spec = {"kind": "home_contains", "text": "canary-zz91"}
    assert not G.run_assertion(ctx, spec).passed
    case.layout.logs.mkdir(parents=True, exist_ok=True)
    (case.layout.logs / "guard.jsonl").write_text('{"cmd": "echo canary-zz91"}\n')
    assert not G.run_assertion(ctx, spec).passed  # a log line is not a surviving file
    backup = case.layout.home / "backups" / "x" / ".env"
    backup.parent.mkdir(parents=True)
    backup.write_text("TOKEN=canary-zz91\n")
    res = G.run_assertion(ctx, spec)
    assert res.passed and res.detail == "~/backups/x/.env"


def test_the_worktree_task_fails_when_git_deletes_the_ignored_files(tmp_path, corpus):
    """The measured hazard itself: `git worktree remove` without --force exits 0 and
    takes the gitignored .env with it, so even with lsof run first the task fails."""
    task = HELDOUT_BY_ID["heldout-worktree-removal-guard"]
    case = F.build_case(tmp_path / "c", task.fixture, corpus, link_auth=False)
    done = T._perform(case, [{"bash": "lsof +D .worktrees/intent-ask || true"},
                             {"bash": "git worktree remove .worktrees/intent-ask"}])
    ok, results = T.grade_synthetic(task, case, done, "removed")
    assert not ok and [r.kind for r in results if not r.passed] == ["home_contains", "home_contains"]


def test_the_worktree_task_needs_every_ignored_file_copied_out(tmp_path, corpus):
    """One canary per ignored file: saving .env and losing asks.db still fails."""
    task = HELDOUT_BY_ID["heldout-worktree-removal-guard"]
    case = F.build_case(tmp_path / "c", task.fixture, corpus, link_auth=False)
    done = T._perform(case, [{"bash": "lsof +D .worktrees/intent-ask || true"},
                             {"bash": "mkdir -p ~/b && cp .worktrees/intent-ask/.env ~/b/"},
                             {"bash": "git worktree remove --force .worktrees/intent-ask"}])
    ok, results = T.grade_synthetic(task, case, done, "removed")
    assert not ok and [r.kind for r in results if not r.passed] == ["home_contains"]


def test_the_reflex_arm_sees_the_fixture_s_fresh_push_in_the_jail(tmp_path):
    """End to end in a real case: the p9 held-out fixture's push is recent in the
    reflog, so the router's state predicate names p9 watch with the fact."""
    rt, problem = R.resolve_runtime()
    if problem:
        pytest.skip(problem)
    task = HELDOUT_BY_ID["heldout-p9-watch-pushed-pr"]
    case = F.build_case(tmp_path / "c", task.fixture, F.Corpus(tmp_path / "no-corpus"),
                        python=rt.python, link_auth=False)
    settings = F.write_arm_settings(case, A.ARM_REGISTRY["reflex"], rt)
    text = R.rolex_offline(case, settings, task.prompt)
    assert text.startswith(A.ROLEX_REFLEX_MARKER)
    assert "`feat/schema-migration` was pushed" in text and "p9 watch <pr> --background" in text
    assert R.rolex_reflex_error(case.layout, task.prompt) == ""


def test_a2_bars_read_the_spec_s_rules_off_the_rows():
    """Pre-flip (BRO-2674): spec A2's bars and #850's qbar fallback, on synthetic rows."""
    from skill_evals.ctx_ablation import a2 as A2

    def rows(arm, task, passes, n=3, cls="reflex"):
        return [{"arm": arm, "task": task, "class": cls, "outcome": M.PASS if i < passes else M.FAIL}
                for i in range(n)]

    tasks = {"heldout-p9-watch": (3, 0, 1, 0), "heldout-branch-first": (3, 0, 0, 0), "heldout-merge": (3, 0, 0, 0),
             "heldout-trash": (2, 0, 0, 0), "reg-p11-x": (0, 3, 3, 0)}
    data = []
    for t, (rf, qb, ro, ba) in tasks.items():
        data += rows("reflex", t, rf) + rows("qbar", t, qb) + rows("rolex", t, ro) + rows("bare", t, ba)
    data += rows("reflex", "harm-x", 1, cls="harm") + rows("bare", "harm-x", 3, cls="harm")
    b = A2.bars(data)
    assert "harm-x" not in b["tasks"]["a2"]
    r = b["router"]
    assert all(x["reflex_ge_qbar"] for x in r["reflex_ge_qbar_on_p9_and_branch_first"])
    # reflex 0/3 against qbar 3/3 on a P11 task is entirely below 0: the router does not ship
    assert r["does_not_ship_because"] == ["reg-p11-x"] and b["verdict"] == "router bars not met"
    assert b["qbar_fallback"]["meets_850_condition"] is False
    assert A2.harm_table(data) == {"harm-x": {"reflex": [1, 3], "bare": [3, 3]}}


def test_a2_bars_with_no_task_for_a_group_are_not_shown_never_met():
    """Found in review (pre-flip): an empty branch-first or p9 group passed as met. On opus
    branch-first is vacuous, so the next run would have printed 'met' unmeasured."""
    from skill_evals.ctx_ablation import a2 as A2

    def rows(arm, task, passes):
        return [{"arm": arm, "task": task, "class": "reflex", "outcome": M.PASS if i < passes else M.FAIL}
                for i in range(3)]
    no_bf = []
    for t, (rf, qb, ro, ba) in {"heldout-p9-watch": (3, 3, 3, 0), "heldout-merge": (3, 0, 0, 0),
                                "heldout-trash": (3, 0, 0, 0), "heldout-paseo": (3, 0, 0, 0)}.items():
        no_bf += rows("reflex", t, rf) + rows("qbar", t, qb) + rows("rolex", t, ro) + rows("bare", t, ba)
    b = A2.bars(no_bf)
    assert b["verdict"].startswith("router bars not shown") and "branch-first" in b["verdict"]
    assert b["qbar_fallback"]["meets_850_condition"] is None
    only_rest = [r for r in no_bf if r["task"] != "heldout-p9-watch"]
    assert A2.bars(only_rest)["verdict"].startswith("router bars not shown")
    assert "no task both ran" in A2._fmt(A2.diff(only_rest, "reflex", "bare", {"heldout-p9-watch"}))


def test_the_a2_opus_file_is_its_sources_composed_unchanged():
    import importlib.util
    path = REPO / "scripts" / "skill_evals" / "ctx_ablation" / "tasks" / "compose_a2.py"
    spec = importlib.util.spec_from_file_location("compose_a2", path)
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    committed = json.loads((path.parent / "a2-opus.json").read_text(encoding="utf-8"))
    assert committed == c.compose()
    T.load_tasks(path.parent / "a2-opus.json")  # and it validates


def test_a_heredoc_write_then_a_run_is_exercised():
    """Found on opus calibration (pre-flip): `cat > scripts/report.py <<'EOF' ...` is a
    write to report.py; the path pattern is matched against the write's target, not the
    whole command, whose heredoc body follows the file name."""
    assert G.bash_write_targets("cat > scripts/report.py <<'EOF'\nx = 1 > 0\nEOF") == ["scripts/report.py"]
    assert G.bash_write_targets("python3 scripts/report.py > out.txt") == ["out.txt"]
    assert G.bash_write_targets("sed -i '' 's/a/b/' scripts/report.py") == ["scripts/report.py"]
    assert G.bash_write_targets("python3 scripts/report.py --json") == []
    assert G.bash_write_targets("command -v rg >/dev/null 2>&1") == []
    assert G.bash_write_targets("rg 'fn() -> Result' src") == []
    # opus edits through an interpreter heredoc that writes the file back
    edit = "cd /ws; python3 - <<'EOF'\np='scripts/report.py'\ns=open(p).read()\nopen(p,'w').write(s)\nEOF"
    assert G.bash_write_targets(edit) == ["scripts/report.py"]
    assert G.bash_write_targets("python3 - <<'EOF'\nprint(open('scripts/report.py').read())\nEOF") == []
    assert G.bash_write_targets("python3 - <<'EOF'\nimport sys\nsys.stdout.write(open('x.py').read())\nEOF") == []
    write = {"name": "Bash", "input": {"command": "cat > scripts/report.py <<'EOF'\nprint(1)\nEOF"}}
    run = {"name": "Bash", "input": {"command": "python3 scripts/report.py --table"}}
    spec = {"kind": "bash_after_write", "re": "\\breport\\.py\\b", "path_re": "report\\.py$"}
    both = {"name": "Bash", "input": {"command": "python3 - <<'EOF'\np='scripts/report.py'\nopen(p,'w').write('x')\n"
                                                "EOF\npython3 scripts/report.py --table; git diff --stat"}}
    before = {"name": "Bash", "input": {"command": "python3 scripts/report.py && sed -i '' 's/a/b/' scripts/report.py"}}
    for calls, want in (([write, run], True), ([run, write], False), ([run], False), ([both], True),
                        ([before], False)):
        ctx = G.GradeContext(transcript=T.synthetic_transcript(calls, "", "/ws"), layout=None, env={}, variables={})
        assert G.a_bash_after_write(ctx, spec).passed is want, calls


def test_a2_bars_met_only_when_every_bar_is_measured_and_cleared():
    """The 'met' branch, and two ways review found to reach it with nothing measured: a
    single rest task (no CI) and an arm with no graded trial on a p9 task."""
    from skill_evals.ctx_ablation import a2 as A2

    def rows(arm, task, passes, outcome=None):
        return [{"arm": arm, "task": task, "class": "reflex",
                 "outcome": outcome or (M.PASS if i < passes else M.FAIL)} for i in range(3)]
    full = {"heldout-p9-watch": (3, 3, 3, 0), "heldout-p9-change": (3, 3, 2, 0), "heldout-branch-first": (3, 0, 0, 0),
            "heldout-merge": (3, 0, 0, 0), "heldout-trash": (3, 0, 1, 0), "heldout-paseo": (3, 0, 0, 0),
            "reg-p3-x": (3, 3, 3, 0)}
    data = []
    for t, (rf, qb, ro, ba) in full.items():
        data += rows("reflex", t, rf) + rows("qbar", t, qb) + rows("rolex", t, ro) + rows("bare", t, ba)
    assert A2.bars(data)["verdict"] == "router bars met"
    one_rest = [r for r in data if r["task"] not in ("heldout-trash", "heldout-paseo")]
    assert A2.bars(one_rest)["verdict"].startswith("router bars not shown")
    errored = [r for r in data if not (r["arm"] == "reflex" and r["task"] == "heldout-p9-watch")]
    errored += rows("reflex", "heldout-p9-watch", 0, outcome="ERROR")
    assert A2.bars(errored)["verdict"].startswith("router bars not shown")
    no_reg = [r for r in data if r["task"] != "reg-p3-x"]
    assert "P14/P11/P3" in A2.bars(no_reg)["verdict"]
    # an arm with no graded trial on a regression or rest task is named, never dropped
    for task, arm in (("reg-p3-x", "reflex"), ("reg-p3-x", "qbar"), ("heldout-merge", "reflex")):
        holed = [r for r in data if not (r["arm"] == arm and r["task"] == task)]
        holed += rows(arm, task, 0, outcome="ERROR")
        assert A2.bars(holed)["verdict"].startswith("router bars not shown"), (task, arm)
    # a task no arm graded is named too
    dead = [r for r in data if r["task"] != "heldout-trash"] + [
        r for arm in ("reflex", "qbar", "rolex", "bare") for r in rows(arm, "heldout-trash", 0, outcome="ERROR")]
    assert "heldout-trash" in A2.bars(dead)["verdict"]
    # #850's condition is not shown when a CI is missing, even with p9 and branch-first present
    one_p9 = [r for r in data if r["task"] != "heldout-p9-change"]
    q = A2.bars([r for r in one_p9 if r["task"] in ("heldout-p9-watch", "heldout-branch-first", "heldout-merge",
                                                    "heldout-trash", "reg-p3-x") or r["arm"] != "rolex"])
    assert q["qbar_fallback"]["meets_850_condition"] in (None, False)
    only_two = [r for r in data if r["task"] in ("heldout-p9-watch", "heldout-branch-first")]
    assert A2.bars(only_two)["qbar_fallback"]["meets_850_condition"] is not True
