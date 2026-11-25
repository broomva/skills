"""Tests for checkable.py.

Each invariant has a test that breaks it and expects that invariant's code,
and a nearby legitimate statement that must still pass. A test that only saw
passes could not tell a working gate from one that never looks.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

import checkable  # noqa: E402

PINNED = ("pinned", "claims match the base")
UNKNOWN = ("unknown", "no --base revision was given")


def good() -> dict:
    return {
        "checkable": 1,
        "problem": "Ship a change that keeps the totals correct.",
        "domain": ["code"],
        "performers": ["model:anthropic"],
        "claims": [
            {
                "id": "tests",
                "text": "The unit tests pass.",
                "rung": "replay",
                "verifier": {"origin": "code", "check": "true", "rejects": "false", "accepts": "true"},
                "status": "open",
            },
            {
                "id": "review",
                "text": "A different model scores the change 7 or above.",
                "rung": "judgment",
                "verifier": {"origin": "model:openai", "rubric": "the review rubric", "pass_rule": "score >= 7"},
            },
            {
                "id": "live",
                "text": "The deployed page returns 200.",
                "rung": "measurement",
                "verifier": {
                    "origin": "sensor:http-probe",
                    "sensor": "curl the page",
                    "positive_control": "the probe fetches a page known to be up",
                    "falsification_criterion": "any status other than 200",
                },
            },
            {"id": "taste", "text": "The design is the right one.", "rung": "none"},
        ],
        "actions": [
            {"id": "push", "text": "Push the branch", "reversibility": "reversible", "reach": "a feature branch", "undo": "delete the branch"},
            {
                "id": "deploy",
                "text": "Deploy to production",
                "reversibility": "irreversible",
                "reach": "every user",
                "gate": "human:owner",
                "requires": ["tests", "review"],
            },
        ],
        "flow": {"steps": ["tests", "push", "review", "deploy", "live"]},
        "feeds": [{"from": "the build", "to": "the deploy", "check": "tests"}],
        "learning": {"on_correction": "a repeated mistake becomes a failing test"},
        "unverified": ["taste: whether the design is the right one"],
    }


def codes(doc: dict, pin=PINNED, level: str = "FAIL") -> set[str]:
    return {f["invariant"] for f in checkable.check(doc, pin) if f["level"] == level}


def test_a_good_statement_has_no_findings():
    assert checkable.check(good(), PINNED) == []


# --- C0 shape -------------------------------------------------------------

@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(checkable=2),
        lambda d: d.update(problem=" "),
        lambda d: d.update(performers=[]),
        lambda d: d.update(performers=["claude"]),
        lambda d: d.update(claims=[]),
        lambda d: d["claims"][0].pop("text"),
        lambda d: d["claims"][0].update(rung="vibes"),
        lambda d: d["claims"][0].update(status="done"),
        lambda d: d["claims"].append(copy.deepcopy(d["claims"][0])),
        lambda d: d["actions"][0].update(id="tests"),
    ],
)
def test_c0_malformed_statement_is_refused(mutate):
    doc = good()
    mutate(doc)
    assert "C0" in codes(doc)


# --- C1 pin ---------------------------------------------------------------

def test_c1_changed_claims_are_refused():
    assert "C1" in codes(good(), ("changed", "claims differ from origin/main"))


def test_c1_unpinned_draft_only_warns():
    assert "C1" not in codes(good(), UNKNOWN)
    assert "C1" in codes(good(), UNKNOWN, level="WARN")


def test_c1_accepting_a_claim_needs_a_pin():
    doc = good()
    doc["claims"][0].update(status="accepted", receipt={"revision": "abc123", "replay": "true", "result": "pass"})
    assert "C1" in codes(doc, UNKNOWN)
    assert "C1" in codes(doc, ("absent", "not at the base"))
    assert codes(doc, PINNED) == set()


# --- C2 receipts ----------------------------------------------------------

def test_c2_accepted_without_receipt_is_refused():
    doc = good()
    doc["claims"][0]["status"] = "accepted"
    assert "C2" in codes(doc)


def test_c2_accepted_with_a_failing_receipt_is_refused():
    doc = good()
    doc["claims"][0].update(status="accepted", receipt={"revision": "abc", "replay": "true", "result": "fail"})
    assert "C2" in codes(doc)


def test_c2_a_claim_with_no_check_cannot_be_accepted():
    doc = good()
    doc["claims"][3].update(status="accepted", receipt={"revision": "abc", "replay": "n/a", "result": "pass"})
    assert "C2" in codes(doc)


def test_c2_a_refuted_claim_carries_its_failing_receipt():
    doc = good()
    doc["claims"][0].update(status="refuted", receipt={"revision": "abc", "replay": "false", "result": "fail"})
    assert codes(doc) == set()


# --- C3 the check can fail ------------------------------------------------

@pytest.mark.parametrize(
    "claim, field",
    [(0, "rejects"), (0, "check"), (1, "rubric"), (1, "pass_rule"), (2, "positive_control"), (2, "falsification_criterion")],
)
def test_c3_a_check_that_cannot_fail_is_refused(claim, field):
    doc = good()
    del doc["claims"][claim]["verifier"][field]
    assert "C3" in codes(doc)


def test_c3_track_record_needs_the_prediction_written_first():
    doc = good()
    doc["claims"].append({"id": "forecast", "text": "Cash stays above zero.", "rung": "track-record", "verifier": {"origin": "code", "scored_by": "next month's balance"}})
    assert "C3" in codes(doc)
    doc["claims"][-1]["verifier"]["prediction_recorded"] = "2026-11-01"
    assert codes(doc) == set()


# --- C4 independence ------------------------------------------------------

def test_c4_a_performer_cannot_judge_its_own_work():
    doc = good()
    doc["claims"][1]["verifier"]["origin"] = "model:anthropic"
    assert "C4" in codes(doc)


def test_c4_a_judgment_is_not_made_by_code():
    doc = good()
    doc["claims"][1]["verifier"]["origin"] = "code"
    assert "C4" in codes(doc)


def test_c4_origin_is_required_and_typed():
    doc = good()
    doc["claims"][0]["verifier"]["origin"] = "somebody"
    assert "C4" in codes(doc)


def test_c4_a_human_reviewer_is_independent_of_a_model_performer():
    doc = good()
    doc["claims"][1]["verifier"]["origin"] = "human:reviewer"
    assert codes(doc) == set()


# --- C5 order -------------------------------------------------------------

def test_c5_two_actions_need_a_declared_order():
    doc = good()
    del doc["flow"]
    assert "C5" in codes(doc)


def test_c5_every_action_is_in_the_order():
    doc = good()
    doc["flow"]["steps"].remove("deploy")
    assert "C5" in codes(doc)


def test_c5_steps_name_known_ids():
    doc = good()
    doc["flow"]["steps"].append("ship-it")
    assert "C5" in codes(doc)


def test_c5_a_flow_reference_is_enough():
    doc = good()
    doc["flow"] = {"ref": "flows/checkable.yaml"}
    assert codes(doc) == set()


def test_c5_one_reversible_action_needs_no_flow():
    doc = good()
    doc["actions"] = [doc["actions"][0]]
    del doc["flow"]
    assert codes(doc) == set()


# --- C6 confinement -------------------------------------------------------

def test_c6_every_action_has_a_reversibility_class():
    doc = good()
    del doc["actions"][0]["reversibility"]
    assert "C6" in codes(doc)


def test_c6_a_reversible_action_says_how_it_is_undone():
    doc = good()
    del doc["actions"][0]["undo"]
    assert "C6" in codes(doc)


def test_c6_an_irreversible_action_needs_a_gate():
    doc = good()
    del doc["actions"][1]["gate"]
    assert "C6" in codes(doc)


def test_c6_a_judgment_cannot_gate_an_irreversible_action_alone():
    doc = good()
    doc["actions"][1]["gate"] = "claim:review"
    assert "C6" in codes(doc)


def test_c6_a_replay_claim_can_gate_an_irreversible_action():
    doc = good()
    doc["actions"][1]["gate"] = "claim:tests"
    assert codes(doc) == set()


def test_c6_an_unchecked_claim_guards_only_reversible_actions():
    doc = good()
    doc["actions"][1]["requires"].append("taste")
    assert "C6" in codes(doc)
    doc = good()
    doc["actions"][0]["requires"] = ["taste"]
    assert codes(doc) == set()


def test_c6_reach_is_stated():
    doc = good()
    del doc["actions"][1]["reach"]
    assert "C6" in codes(doc)


# --- C7 contraction -------------------------------------------------------

def test_c7_feeds_must_be_declared():
    doc = good()
    del doc["feeds"]
    assert "C7" in codes(doc)


def test_c7_a_hop_names_the_claim_that_checks_it():
    doc = good()
    doc["feeds"][0]["check"] = "nothing"
    assert "C7" in codes(doc)


def test_c7_an_unchecked_claim_cannot_guard_a_hop():
    doc = good()
    doc["feeds"][0]["check"] = "taste"
    assert "C7" in codes(doc)


def test_c7_a_correction_needs_somewhere_to_go():
    doc = good()
    del doc["learning"]
    assert "C7" in codes(doc)


def test_c7_no_hops_is_a_legitimate_answer():
    doc = good()
    doc["feeds"] = []
    assert codes(doc) == set()


# --- C8 the declared remainder --------------------------------------------

def test_c8_the_unverified_list_is_required():
    doc = good()
    del doc["unverified"]
    assert "C8" in codes(doc)


def test_c8_an_unchecked_claim_is_named_as_unverified():
    doc = good()
    doc["unverified"] = ["something else entirely"]
    assert "C8" in codes(doc)


def test_c8_an_empty_list_needs_a_reason():
    doc = good()
    doc["claims"].pop()
    doc["unverified"] = []
    assert "C8" in codes(doc)
    doc["nothing_unverified_because"] = "every claim is decided by a proof on the artifact"
    assert codes(doc) == set()


# --- pin_state against a real repository ----------------------------------

def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "statement.json").write_text(json.dumps(good()))
    _git(tmp_path, "add", "statement.json")
    _git(tmp_path, "commit", "-q", "-m", "state the problem")
    return tmp_path


def test_pin_matches_the_base(repo: Path):
    path = repo / "statement.json"
    assert checkable.pin_state(path, "main", checkable.load_doc(path))[0] == "pinned"


def test_pin_ignores_status_and_receipts(repo: Path):
    path = repo / "statement.json"
    doc = good()
    doc["claims"][0].update(status="accepted", receipt={"revision": "abc", "replay": "true", "result": "pass"})
    path.write_text(json.dumps(doc))
    assert checkable.pin_state(path, "main", doc)[0] == "pinned"


def test_pin_sees_an_edited_claim(repo: Path):
    path = repo / "statement.json"
    doc = good()
    doc["claims"][0]["verifier"]["check"] = "echo trust me"
    path.write_text(json.dumps(doc))
    assert checkable.pin_state(path, "main", doc)[0] == "changed"


def test_pin_reports_a_statement_missing_at_the_base(repo: Path):
    path = repo / "new.json"
    path.write_text(json.dumps(good()))
    assert checkable.pin_state(path, "main", good())[0] == "absent"


def test_pin_is_unknown_without_a_base_or_with_a_bad_one(repo: Path):
    path = repo / "statement.json"
    assert checkable.pin_state(path, None, good())[0] == "unknown"
    assert checkable.pin_state(path, "no-such-rev", good())[0] == "unknown"


# --- replay ---------------------------------------------------------------

def test_replay_passes_when_controls_behave_and_the_check_passes(tmp_path: Path):
    rows, code = checkable.replay(good(), tmp_path, 30)
    assert code == checkable.EXIT_OK
    assert [r["verdict"] for r in rows] == ["PASS"]


def test_replay_reports_a_failing_check(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"]["check"] = "false"
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_FINDING
    assert rows[0]["verdict"] == "FAIL"


def test_replay_is_invalid_when_the_known_bad_case_passes(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"]["rejects"] = "true"
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_INVALID
    assert rows[0]["verdict"] == "INVALID"
    assert "check_exit" not in rows[0]


def test_replay_is_invalid_when_the_known_good_case_is_refused(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"]["accepts"] = "false"
    _, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_INVALID


def test_replay_with_nothing_to_run_is_invalid_not_a_pass(tmp_path: Path):
    doc = good()
    doc["claims"] = doc["claims"][1:]
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert rows == [] and code == checkable.EXIT_INVALID


def test_replay_treats_a_timeout_as_invalid(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"]["rejects"] = "sleep 5"
    _, code = checkable.replay(doc, tmp_path, 1)
    assert code == checkable.EXIT_INVALID


# --- route ----------------------------------------------------------------

INDEX = {
    "entries": [
        {"name": "judge", "kind": "skill", "parts": ["verifiers"], "rungs": ["judgment"], "domains": ["any"]},
        {"name": "prover", "kind": "skill", "parts": ["verifiers"], "rungs": ["proof"], "domains": ["any"]},
        {"name": "ledger", "kind": "skill", "parts": ["ontology"], "domains": ["finance"]},
        {"name": "sandbox", "kind": "service", "parts": ["shield"], "domains": ["code"], "where": "somewhere"},
    ],
    "no_role": [],
}


def test_route_filters_by_domain_and_by_rung():
    routed = checkable.route(good(), INDEX)
    assert [r["name"] for r in routed["verifiers"]] == ["judge"]
    assert routed["verifiers"][0]["rungs"] == ["judgment"]
    assert routed["ontology"] == []
    assert [r["name"] for r in routed["shield"]] == ["sandbox"]


def test_route_follows_the_statement_domain():
    doc = good()
    doc["domain"] = ["finance"]
    assert [r["name"] for r in checkable.route(doc, INDEX)["ontology"]] == ["ledger"]


# --- the shipped index and examples ---------------------------------------

ROOT = checkable.find_root(SKILL)


def test_the_monorepo_roster_is_found_when_required():
    if os.environ.get("CHECKABLE_REQUIRE_ROSTER") == "1":
        assert ROOT is not None, "CI must run this suite inside the monorepo"


def test_the_shipped_index_is_internally_consistent():
    report, _ = checkable.index_report(checkable.load_index(checkable.default_index()), None)
    assert report["problems"] == []
    assert report["empty_parts"] == []


@pytest.mark.skipif(ROOT is None, reason="installed outside the monorepo: there is no roster to compare")
def test_every_skill_on_disk_is_indexed_or_set_aside():
    report, code = checkable.index_report(checkable.load_index(checkable.default_index()), ROOT)
    assert report["untagged"] == []
    assert report["dangling"] == []
    assert code == checkable.EXIT_OK


@pytest.mark.skipif(ROOT is None, reason="installed outside the monorepo: there is no roster to compare")
def test_an_index_missing_a_skill_is_refused():
    index = checkable.load_index(checkable.default_index())
    index["no_role"] = index["no_role"][1:]
    report, code = checkable.index_report(index, ROOT)
    assert len(report["untagged"]) == 1 and code == checkable.EXIT_FINDING


@pytest.mark.skipif(ROOT is None, reason="installed outside the monorepo: there is no roster to compare")
def test_an_index_naming_a_skill_that_is_gone_is_refused():
    index = checkable.load_index(checkable.default_index())
    index["no_role"].append("a-skill-that-was-deleted")
    report, code = checkable.index_report(index, ROOT)
    assert report["dangling"] == ["a-skill-that-was-deleted"] and code == checkable.EXIT_FINDING


def test_an_index_entry_without_a_part_is_refused():
    index = {"entries": [{"name": "x", "kind": "skill", "parts": [], "domains": ["any"]}], "no_role": []}
    report, code = checkable.index_report(index, None)
    assert report["problems"] and code == checkable.EXIT_FINDING


def _yaml_or_skip():
    if os.environ.get("CHECKABLE_REQUIRE_YAML") == "1":
        import yaml  # noqa: F401  (CI must have it; an ImportError here is the failure)
    else:
        pytest.importorskip("yaml")


@pytest.mark.parametrize("name", ["ship-checkable.yaml", "monthly-close.yaml"])
def test_the_shipped_examples_break_no_invariant(name):
    _yaml_or_skip()
    doc = checkable.load_doc(SKILL / "examples" / name)
    fails = [f for f in checkable.check(doc, PINNED) if f["level"] == "FAIL"]
    assert fails == []


def test_the_broken_fixture_is_refused_on_the_command_line(capsys):
    code = checkable.main(["check", str(SKILL / "tests" / "fixtures" / "broken.json")])
    assert code == checkable.EXIT_FINDING
    assert "NOT CHECKABLE" in capsys.readouterr().out


def test_a_passing_replay_prints_no_command_output(tmp_path: Path, capsys):
    doc = good()
    doc["claims"][0]["verifier"]["check"] = "echo a-line-that-changes-every-run"
    path = tmp_path / "s.json"
    path.write_text(json.dumps(doc))
    assert checkable.main(["replay", str(path), "--cwd", str(tmp_path)]) == checkable.EXIT_OK
    assert capsys.readouterr().out == "PASS    tests (replay)\n"


def test_a_failing_replay_prints_the_command_output(tmp_path: Path, capsys):
    doc = good()
    doc["claims"][0]["verifier"]["check"] = "echo the-reason-it-failed; false"
    path = tmp_path / "s.json"
    path.write_text(json.dumps(doc))
    assert checkable.main(["replay", str(path), "--cwd", str(tmp_path)]) == checkable.EXIT_FINDING
    assert "the-reason-it-failed" in capsys.readouterr().out


def test_unreadable_input_exits_2(tmp_path: Path, capsys):
    bad = tmp_path / "s.json"
    bad.write_text("{not json")
    assert checkable.main(["check", str(bad)]) == checkable.EXIT_INVALID
    assert checkable.main(["check", str(tmp_path / "missing.json")]) == checkable.EXIT_INVALID


def test_index_without_a_roster_exits_3_when_one_is_required(tmp_path: Path):
    lone = tmp_path / "index.json"
    lone.write_text(json.dumps({"entries": [], "no_role": []}))
    assert checkable.main(["index", "--index", str(lone), "--require-roster"]) == checkable.EXIT_NO_COMPARISON
