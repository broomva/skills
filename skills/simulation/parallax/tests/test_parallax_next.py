"""Unit tests for the parallax skill's deterministic core.

Run from the skill's own directory (relative on purpose -- this skill has three
homes and no absolute path is correct in all of them):

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "parallax_next.py"
CODES = SKILL / "references" / "error-codes.txt"

spec = importlib.util.spec_from_file_location("parallax_next", SCRIPT)
assert spec and spec.loader
pn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pn)


def _status(state: str, **kw):
    base = {"state": state, "readable": True, "cwd": "/w", "head": None, "accepted": [], "runs": []}
    base.update(kw)
    return base


def _head(ref="94c50e77db74", open_qs=(1,)):
    return {
        "ref": ref,
        "blockingRemaining": [
            {"n": n, "slot": f"slot{n}", "question": f"q{n}?"} for n in open_qs
        ],
    }


# ---------------------------------------------------------------- remedies


def _fixture_codes() -> set[str]:
    return {
        line.strip()
        for line in CODES.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def test_remedy_table_covers_exactly_the_captured_code_set():
    """No invented codes, and no code left without a remedy.

    This is the check that keeps the skill honest: a remedy for a code Parallax
    cannot return sends a caller somewhere for no reason, and a real code with no
    remedy is the case the agent has to improvise, which is what the script exists
    to prevent.
    """
    assert set(pn.REMEDIES) == _fixture_codes()


def test_the_fixture_is_not_empty():
    # A fixture that silently parsed to nothing would make the test above vacuous:
    # set() == set() passes and proves nothing.
    #
    # The count is hardcoded ON PURPOSE, as a tripwire. Deriving it from the file
    # it is checking would make this test agree with any fixture, including an
    # empty one. Adding a code to the runtime is supposed to land here and make
    # someone write the remedy -- which is exactly what it did when the
    # business-data ingress gained COLUMNS_REQUIRED, INVALID_ROW_COUNT and
    # ORIGIN_REQUIRED (46 -> 49).
    assert len(_fixture_codes()) == 52


def test_unknown_code_is_reported_as_unknown_not_guessed():
    assert pn.remedy("NOT_A_REAL_CODE") is None


def test_reconciliation_remedy_orders_the_two_steps():
    """The one remedy a plain reading of `reason` does not produce."""
    fix = pn.remedy("RECONCILIATION_UNACKNOWLEDGED")
    assert fix is not None
    assert "TELL THE HUMAN FIRST" in fix
    assert fix.index("unmappedFromContext") < fix.index("acknowledgeUnmapped")


def test_workspace_denied_warns_that_it_looks_like_an_empty_directory():
    fix = pn.remedy("WORKSPACE_DENIED")
    assert fix is not None and "EMPTY DIRECTORY" in fix


def test_unexpected_is_named_a_defect_not_a_refusal():
    fix = pn.remedy("UNEXPECTED")
    assert fix is not None and "DEFECT" in fix


# ---------------------------------------------------------------- next step


@pytest.mark.parametrize(
    "state,expected_command",
    [
        ("IDLE", "parallax propose"),
        ("READY", "parallax accept"),
        ("ACCEPTED", "parallax run"),
        ("RAN", "parallax receipt"),
    ],
)
def test_each_state_routes_to_its_command(state, expected_command):
    head = _head(open_qs=()) if state == "READY" else None
    step = pn.next_step(_status(state, head=head))
    assert step is not None
    assert step[0].startswith(expected_command)


def test_proposed_and_partial_both_route_to_answer():
    for state in ("PROPOSED", "PARTIAL"):
        step = pn.next_step(_status(state, head=_head(open_qs=(1, 2))))
        assert step is not None
        assert step[0].startswith("parallax answer")


def test_answer_command_carries_the_ref_and_the_first_open_question_number():
    step = pn.next_step(_status("PARTIAL", head=_head(ref="abc123def456", open_qs=(3, 4))))
    assert step is not None
    assert "--proposal abc123def456" in step[0]
    assert "--answer 3=" in step[0]


def test_partial_and_proposed_differ_in_their_reason_not_their_command():
    a = pn.next_step(_status("PROPOSED", head=_head()))
    b = pn.next_step(_status("PARTIAL", head=_head()))
    assert a and b and a[0] == b[0]
    assert "no answers recorded yet" in a[1]
    assert "some answers already recorded" in b[1]


def test_ready_warns_that_the_reconciliation_refusal_is_the_gate_working():
    step = pn.next_step(_status("READY", head=_head(open_qs=())))
    assert step is not None
    assert "RECONCILIATION_UNACKNOWLEDGED" in step[1]


def test_ran_forbids_restating_a_number():
    """The discipline most likely to be dropped, so it rides on the state machine."""
    step = pn.next_step(_status("RAN", runs=[{"runId": "r1"}]))
    assert step is not None
    assert "restate" in step[1].lower()


def test_unreadable_workspace_short_circuits_every_state():
    # readable:false must win even when the state field says something actionable.
    step = pn.next_step(_status("IDLE", readable=False))
    assert step is not None
    assert "DENIED" in step[1]


def test_unreadable_workspace_returns_no_command_rather_than_looping():
    """It must NOT return `parallax status` -- the command that produced this result.

    An agent following the router mechanically would retry it in the same workspace
    forever. Nothing Parallax offers fixes an unreadable directory.
    """
    step = pn.next_step(_status("IDLE", readable=False))
    assert step is not None
    assert step[0] is None, f"expected no command, got {step[0]!r}"


def test_unknown_state_returns_none_rather_than_a_default():
    assert pn.next_step(_status("SOMETHING_NEW")) is None


def test_missing_head_does_not_crash_a_state_that_expects_one():
    step = pn.next_step(_status("PROPOSED", head=None))
    assert step is not None
    assert "<ref>" in step[0]


# ---------------------------------------------------------------- envelopes


def test_envelope_is_unwrapped_for_both_polarities():
    assert pn._unwrap({"ok": True, "value": {"state": "IDLE"}}) == {"state": "IDLE"}
    assert pn._unwrap({"ok": False, "error": {"code": "X"}}) == {"code": "X"}


def test_a_bare_document_passes_through_unwrap():
    assert pn._unwrap({"state": "IDLE"}) == {"state": "IDLE"}


# ---------------------------------------------------------------- cli


def _run(args, stdin=""):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_status_from_stdin_exits_zero_and_names_the_command():
    r = _run(["--status", "-"], json.dumps({"ok": True, "value": _status("IDLE")}))
    assert r.returncode == 0
    assert "parallax propose" in r.stdout


def test_cli_error_from_stdin_prints_the_remedy():
    r = _run(["--error", "-"], json.dumps({"code": "NO_ACCEPTED_ONTOLOGY", "reason": "x"}))
    assert r.returncode == 0
    assert "Accept a proposal first" in r.stdout


def test_cli_json_mode_is_parseable():
    r = _run(["--status", "-", "--json"], json.dumps(_status("ACCEPTED")))
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["known"] is True and out["next"] == "parallax run"


def test_cli_unknown_code_exits_3_not_0():
    r = _run(["--error", "-"], json.dumps({"code": "MADE_UP"}))
    assert r.returncode == 3


def test_cli_unknown_state_exits_3_not_0():
    r = _run(["--status", "-"], json.dumps(_status("MADE_UP")))
    assert r.returncode == 3


def test_cli_malformed_json_exits_2():
    r = _run(["--status", "-"], "not json")
    assert r.returncode == 2


def test_cli_non_object_exits_2():
    r = _run(["--status", "-"], "[1,2,3]")
    assert r.returncode == 2


def test_cli_error_mode_on_a_document_with_no_code_exits_2():
    r = _run(["--error", "-"], json.dumps({"state": "IDLE"}))
    assert r.returncode == 2


def test_cli_requires_exactly_one_mode():
    assert _run([]).returncode == 2
    assert _run(["--status", "-", "--error", "-"]).returncode == 2
