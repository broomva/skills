"""Tool calls must have RUN to count as evidence (scripts/skill_evals/, BRO-2016).

Every tool-side evidence predicate graded `tool_use` blocks — the agent's *claim* to
have called something — and never looked at the matching `tool_result`. So a `Write`
the Read-before-Edit hook rejected still proved `documents_finding`, and a `Skill`
call whose launch came back `success: false` still counted as a trigger. In a sample
of real transcripts, 28 of 84 `Write` results and 17 of 915 `Bash` results carry
`is_error: true`, so this is not a hypothetical shape.

The fix is one root predicate, `Transcript.executed_successfully`, applied at the
single funnel every affected check already passes through.

THE OVERSHOOT THIS FILE GUARDS AGAINST. The naive rule — "evidence requires a
present, non-error result" — was measured to break 9 existing tests, because a
transcript that models no results at all is not evidence that its calls failed. That
carve-out (`resolves_tool_results`) is the difference between a fix and a
false-negative machine, and `test_a_transcript_that_models_no_results_is_not_condemned`
is what holds it in place. Each tightening below is paired with its false-positive
control in the same file.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals import checks as checks_mod  # noqa: E402
from skill_evals import runner as R  # noqa: E402
from skill_evals.transcript import Transcript  # noqa: E402

from test_runner import (  # noqa: E402
    ev_init,
    ev_result,
    ev_text,
    ev_tool_result,
    ev_tool_use,
    ndjson,
)


def ev_ok(tid, content="done"):
    """A successful result in the shape the CLI most often emits: no `is_error`."""
    return {"type": "user",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": content}]}}


def ev_err(tid, content="Error: Exit code 1"):
    return {"type": "user",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "is_error": True,
                 "content": content}]},
            "tool_use_result": content}


def ctx_for(stream, *, case_prompt="do the thing", skill="demo", workspace=None):
    t = Transcript.from_ndjson(stream)
    return checks_mod.CheckContext(
        case={"id": "c1", "prompt": case_prompt, "should_trigger": True,
              "artifact_aliases": []},
        skill=skill,
        transcript=t,
        workspace=workspace,
    )


# ---------------------------------------------------------------------------
# the linkage
# ---------------------------------------------------------------------------


def test_tool_results_are_paired_by_id_not_by_order():
    """Parallel calls were observed live resolving OUT OF ORDER (A, B issued; B, A
    returned). Any positional pairing attributes one call's outcome to another —
    worse than not checking, because it is wrong in both directions at once."""
    t = Transcript.from_ndjson(ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": "a.py"}, tid="toolu_A"),
        ev_tool_use("Read", {"file_path": "b.py"}, tid="toolu_B"),
        ev_err("toolu_B"),
        ev_ok("toolu_A"),
        ev_result("done"),
    ))
    results = t.tool_results()
    assert results["toolu_A"].is_error is False
    assert results["toolu_B"].is_error is True


def test_absent_is_error_means_success():
    """375 of 1327 successful results in a real sample omit the key entirely."""
    t = Transcript.from_ndjson(ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": "a.py"}, tid="toolu_01"),
        ev_ok("toolu_01"),
        ev_result("done"),
    ))
    assert t.executed_successfully(t.tool_uses()[0]) is True


def test_the_string_false_is_not_a_failure():
    """`bool("False")` is True, so a shape change from bool to string under a naive
    predicate would condemn every successful call at once."""
    from skill_evals.transcript import _is_error_flag

    assert _is_error_flag(None) is False
    assert _is_error_flag(False) is False
    assert _is_error_flag("False") is False
    assert _is_error_flag("false") is False
    assert _is_error_flag(True) is True
    assert _is_error_flag("true") is True


def test_an_errored_call_did_not_execute():
    t = Transcript.from_ndjson(ndjson(
        ev_init(),
        ev_tool_use("Write", {"file_path": "notes.md", "content": "x"}, tid="toolu_01"),
        ev_err("toolu_01", "<tool_use_error>File has not been read yet</tool_use_error>"),
        ev_result("done"),
    ))
    assert t.executed_successfully(t.tool_uses()[0]) is False


# ---------------------------------------------------------------------------
# the anti-overshoot carve-outs — each one is a measured false-negative closed
# ---------------------------------------------------------------------------


def test_a_transcript_that_models_no_results_is_not_condemned():
    """THE anti-overshoot test. Absence of result modelling is not evidence of
    failure — the naive rule broke 9 existing tests on exactly this shape."""
    t = Transcript.from_ndjson(ndjson(
        ev_init(),
        ev_tool_use("WebFetch", {"url": "https://example.invalid/paper.pdf"}, tid="toolu_01"),
        ev_tool_use("Bash", {"command": "ls -la"}, tid="toolu_02"),
        ev_result("done"),
    ))
    assert t.resolves_tool_results() is False
    assert all(t.executed_successfully(tu) for tu in t.tool_uses())


def test_a_resolved_transcript_condemns_its_own_unresolved_calls():
    """The other side of the same coin: a transcript that demonstrably records
    outcomes, and recorded none for this call, says the call never finished."""
    stream = ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": "a.py"}, tid="toolu_01"),
        ev_ok("toolu_01"),
        ev_tool_use("Write", {"file_path": "notes.md", "content": "x"}, tid="toolu_02"),
        ev_result("done"),
    )
    t = Transcript.from_ndjson(stream)
    assert t.resolves_tool_results() is True
    by_id = {tu.id: tu for tu in t.tool_uses()}
    assert t.executed_successfully(by_id["toolu_01"]) is True
    assert t.executed_successfully(by_id["toolu_02"]) is False

    # GREEN companion: remove the ONLY result and the same unresolved call is no
    # longer condemned, because now the transcript resolves nothing at all.
    t2 = Transcript.from_ndjson(ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": "a.py"}, tid="toolu_01"),
        ev_tool_use("Write", {"file_path": "notes.md", "content": "x"}, tid="toolu_02"),
        ev_result("done"),
    ))
    assert all(t2.executed_successfully(tu) for tu in t2.tool_uses())


def test_subagent_tool_calls_are_not_condemned_for_being_unresolved():
    """Whether stream-json routes subagent results into the same stream is
    UNMEASURED — the sampled corpus contained none. Condemning on unmeasured
    plumbing is how a gate starts rejecting correct runs."""
    sub = ev_tool_use("Write", {"file_path": "notes.md", "content": "x"},
                      tid="toolu_sub", parent="toolu_parent")
    t = Transcript.from_ndjson(ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": "a.py"}, tid="toolu_01"),
        ev_ok("toolu_01"),
        sub,
        ev_result("done"),
    ))
    assert t.resolves_tool_results() is True
    by_id = {tu.id: tu for tu in t.tool_uses()}
    assert by_id["toolu_sub"].is_subagent is True
    assert t.executed_successfully(by_id["toolu_sub"]) is True


# ---------------------------------------------------------------------------
# the checks, through the shared funnel
# ---------------------------------------------------------------------------


def test_documents_finding_rejects_a_write_the_tool_rejected():
    """The real shape: a Read-before-Edit hook rejection. The agent claimed to
    write the finding; the write never happened."""
    stream = ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": "a.py"}, tid="toolu_00"),
        ev_ok("toolu_00"),
        ev_tool_use("Write", {"file_path": "research/notes/finding.md", "content": "x"},
                    tid="toolu_01"),
        ev_err("toolu_01", "<tool_use_error>File has not been read yet</tool_use_error>"),
        ev_text("All set."),
        ev_result("All set."),
    )
    res = checks_mod.CHECK_REGISTRY["documents_finding"](ctx_for(stream))
    assert not res.passed, res.detail


def test_documents_finding_still_passes_on_a_write_that_landed():
    """FALSE-POSITIVE control for the test above — same stream, successful result."""
    stream = ndjson(
        ev_init(),
        ev_tool_use("Write", {"file_path": "research/notes/finding.md", "content": "x"},
                    tid="toolu_01"),
        ev_ok("toolu_01", "File created successfully."),
        ev_text("All set."),
        ev_result("All set."),
    )
    res = checks_mod.CHECK_REGISTRY["documents_finding"](ctx_for(stream))
    assert res.passed, res.detail


def test_walks_repo_rejects_a_failed_traversal():
    stream = ndjson(
        ev_init(),
        ev_tool_use("Bash", {"command": "ls -la /nope"}, tid="toolu_01"),
        ev_err("toolu_01", "Exit code 1\nls: /nope: No such file or directory"),
        ev_text("Looked around."),
        ev_result("Looked around."),
    )
    res = checks_mod.CHECK_REGISTRY["walks_repo_tree_and_canonical_files"](ctx_for(stream))
    assert not res.passed, res.detail


def test_walks_repo_still_passes_on_a_traversal_that_ran():
    stream = ndjson(
        ev_init(),
        ev_tool_use("Bash", {"command": "find . -name '*.rs' | head -40"}, tid="toolu_01"),
        ev_ok("toolu_01", "src/lib.rs\nsrc/main.rs"),
        ev_text("Looked around."),
        ev_result("Looked around."),
    )
    res = checks_mod.CHECK_REGISTRY["walks_repo_tree_and_canonical_files"](ctx_for(stream))
    assert res.passed, res.detail


# ---------------------------------------------------------------------------
# trigger detection and the RECOVERED classifier
# ---------------------------------------------------------------------------


def test_a_rejected_skill_launch_is_not_a_trigger():
    """Detector A was the model's REQUEST and Detector B the CLI's confirmation,
    unioned — so a rejected launch scored as a firing off Detector A alone."""
    stream = ndjson(
        ev_init(),
        ev_tool_use("Skill", {"skill": "demo", "args": ""}, tid="toolu_01"),
        {"type": "user",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "toolu_01", "is_error": True,
              "content": "skill not found"}]},
         "tool_use_result": {"success": False, "commandName": "demo"}},
        ev_text("Could not run it."),
        ev_result("Could not run it."),
    )
    t = Transcript.from_ndjson(stream)
    assert t.skill_invocations() == ["demo"], "raw-claim semantics must be preserved"
    assert t.triggered("demo") is False
    assert not checks_mod.CHECK_REGISTRY["skill_triggered"](ctx_for(stream)).passed


def test_a_successful_skill_launch_is_still_a_trigger():
    """FALSE-POSITIVE control. Also covers the common shape where the launch result
    carries no `is_error` at all."""
    stream = ndjson(
        ev_init(),
        ev_tool_use("Skill", {"skill": "demo", "args": ""}, tid="toolu_01"),
        ev_tool_result("toolu_01", "demo"),
        ev_text("Done."),
        ev_result("Done."),
    )
    t = Transcript.from_ndjson(stream)
    assert t.triggered("demo") is True
    assert checks_mod.CHECK_REGISTRY["skill_triggered"](ctx_for(stream)).passed


def test_a_retried_skill_call_still_counts_as_a_trigger():
    """One rejected attempt followed by a good one is a trigger, not a miss."""
    stream = ndjson(
        ev_init(),
        ev_tool_use("Skill", {"skill": "demo", "args": ""}, tid="toolu_01"),
        ev_err("toolu_01", "transient failure"),
        ev_tool_use("Skill", {"skill": "demo", "args": ""}, tid="toolu_02"),
        ev_tool_result("toolu_02", "demo"),
        ev_result("Done."),
    )
    assert Transcript.from_ndjson(stream).triggered("demo") is True


def test_a_rejected_skill_md_read_is_not_recovery():
    """Nothing was recovered. Moves the trial from RECOVERED to FAIL — both
    non-PASS, so this can sharpen the diagnosis and can never green anything."""
    ws = "/tmp/ws"
    stream = ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": f"{ws}/.claude/skills/demo/SKILL.md"},
                    tid="toolu_01"),
        ev_err("toolu_01", "<tool_use_error>File does not exist</tool_use_error>"),
        ev_text("I could not find it."),
        ev_result("I could not find it."),
    )
    t = Transcript.from_ndjson(stream)
    assert t.read_skill_content("demo", ws) is False

    case = R.Case(id="c1", prompt="p", should_trigger=True,
                  expected_checks=["final_answer_non_empty"])
    assert R.grade_trial(case, t, "demo", workspace=ws).outcome == R.FAIL


def test_a_successful_skill_md_read_is_still_recovery():
    """FALSE-POSITIVE control — the leak this outcome exists to catch."""
    ws = "/tmp/ws"
    stream = ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": f"{ws}/.claude/skills/demo/SKILL.md"},
                    tid="toolu_01"),
        ev_ok("toolu_01", "---\nname: demo\n---\n"),
        ev_text("Here is the answer."),
        ev_result("Here is the answer."),
    )
    t = Transcript.from_ndjson(stream)
    assert t.read_skill_content("demo", ws) is True

    case = R.Case(id="c1", prompt="p", should_trigger=True,
                  expected_checks=["final_answer_non_empty"])
    assert R.grade_trial(case, t, "demo", workspace=ws).outcome == R.RECOVERED


# ---------------------------------------------------------------------------
# the committed fixtures must keep exercising the tool arm
# ---------------------------------------------------------------------------


def test_every_committed_fixture_resolves_every_tool_call():
    """SILENT COVERAGE LOSS guard. Under this fix an unresolved call in a
    result-modelling transcript stops being evidence — so if the fixtures kept
    their old shape (a result for the Skill call only), the cases would still PASS
    on their text arms while quietly measuring nothing through the tool arm.
    """
    root = REPO / "tests" / "skill_evals" / "fixtures" / "harness-selftest" / "cases"
    trials = sorted(root.glob("*/trial-*.jsonl"))
    assert trials, "no committed fixtures found"
    for path in trials:
        t = Transcript.from_ndjson(path.read_text(encoding="utf-8"))
        unresolved = [tu.name for tu in t.tool_uses() if not t.executed_successfully(tu)]
        assert not unresolved, f"{path.parent.name}/{path.name}: unresolved {unresolved}"
