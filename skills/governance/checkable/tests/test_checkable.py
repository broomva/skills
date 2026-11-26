"""Tests for checkable.py.

Each invariant has a test that breaks it and expects that invariant's code,
and a nearby legitimate statement that must still pass. A test that only saw
passes could not tell a working gate from one that never looks.
"""
from __future__ import annotations

import copy
import json
import os
import signal
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
        lambda d: d.pop("checkable"),
        lambda d: d.pop("problem"),
        lambda d: d.pop("performers"),
        lambda d: d.pop("claims"),
        lambda d: d["claims"][0].pop("rung"),
        lambda d: d["actions"][0].pop("text"),
        lambda d: d["feeds"][0].pop("from"),
        lambda d: d.update(problem=" "),
        lambda d: d.update(performers=[]),
        lambda d: d.update(performers=["claude"]),
        lambda d: d.update(performers=["code"]),
        lambda d: d.update(performers=["model:"]),
        lambda d: d.update(performers=["sensor:probe"]),
        lambda d: d.update(claims=[]),
        lambda d: d["claims"][0].pop("text"),
        lambda d: d["claims"][3].pop("id"),
        lambda d: d["actions"][0].pop("id"),
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
    doc["claims"][0].update(status="refuted", receipt={"revision": "abc", "replay": "true", "result": "fail"})
    assert codes(doc) == set()


def test_c2_a_refuted_claim_cannot_carry_a_passing_receipt():
    doc = good()
    doc["claims"][0].update(status="refuted", receipt={"revision": "abc", "replay": "true", "result": "pass"})
    assert "C2" in codes(doc)


def test_c2_the_receipt_of_a_command_claim_names_that_claims_check():
    doc = good()
    doc["claims"][0].update(status="accepted", receipt={"revision": "abc", "replay": "exit 0", "result": "pass"})
    assert "C2" in codes(doc)


def test_c2_the_receipt_of_a_judgment_says_how_to_look_again():
    doc = good()
    doc["claims"][1].update(status="accepted", receipt={"revision": "abc", "replay": "read review 12 on the pull request", "result": "pass"})
    assert codes(doc) == set()


# --- C3 the check can fail ------------------------------------------------

COMPLETE_VERIFIER = {
    "proof": {"origin": "code", "check": "true", "rejects": "false"},
    "replay": {"origin": "code", "check": "true", "rejects": "false"},
    "measurement": {"origin": "sensor:probe", "sensor": "s", "positive_control": "p", "falsification_criterion": "f"},
    "judgment": {"origin": "model:openai", "rubric": "r", "pass_rule": "p"},
    "track-record": {"origin": "code", "prediction_recorded": "2026-11-01", "scored_by": "s"},
}


def test_the_ladder_table_covers_every_rung_with_a_check():
    assert set(COMPLETE_VERIFIER) == set(checkable.FALSIFIER) == set(checkable.RUNGS) - {"none"}


@pytest.mark.parametrize("rung, field", [(rung, field) for rung, fields in checkable.FALSIFIER.items() for field in fields])
def test_c3_every_field_the_ladder_names_is_required(rung, field):
    doc = good()
    doc["claims"].append({"id": "extra", "text": "x", "rung": rung, "verifier": dict(COMPLETE_VERIFIER[rung])})
    assert codes(doc) == set()
    del doc["claims"][-1]["verifier"][field]
    assert codes(doc) == {"C3"}


def test_c3_track_record_needs_the_prediction_written_first():
    doc = good()
    doc["claims"].append({"id": "forecast", "text": "Cash stays above zero.", "rung": "track-record", "verifier": {"origin": "code", "scored_by": "next month's balance"}})
    assert "C3" in codes(doc)
    doc["claims"][-1]["verifier"]["prediction_recorded"] = "2026-11-01"
    assert codes(doc) == set()


def test_a_prediction_carries_a_date_not_a_promise():
    doc = good()
    doc["claims"].append({"id": "forecast", "text": "Cash stays above zero.", "rung": "track-record", "verifier": {"origin": "code", "scored_by": "next month's balance", "prediction_recorded": "after I see the result"}})
    assert codes(doc) == {"C0"}


# --- C4 independence ------------------------------------------------------

def test_c4_a_performer_cannot_judge_its_own_work():
    doc = good()
    doc["claims"][1]["verifier"]["origin"] = "model:anthropic"
    assert "C4" in codes(doc)


def test_c4_a_judgment_is_not_made_by_a_sensor():
    doc = good()
    doc["claims"][1]["verifier"]["origin"] = "sensor:probe"
    assert "C4" in codes(doc)


def test_c4_a_judgment_is_not_made_by_code():
    doc = good()
    doc["claims"][1]["verifier"]["origin"] = "code"
    assert "C4" in codes(doc)


def test_c4_origin_is_required():
    doc = good()
    del doc["claims"][0]["verifier"]["origin"]
    assert "C4" in codes(doc)


@pytest.mark.parametrize("origin", ["somebody", "model: anthropic", "Model:Anthropic", "model:", " model:openai", "human:the owner"])
def test_an_origin_that_is_not_in_canonical_form_is_refused(origin):
    # "model: anthropic" and "model:anthropic" would name one performer twice.
    doc = good()
    doc["claims"][1]["verifier"]["origin"] = origin
    assert codes(doc) == {"C0"}


def test_c4_a_human_reviewer_is_independent_of_a_model_performer():
    doc = good()
    doc["claims"][1]["verifier"]["origin"] = "human:reviewer"
    assert codes(doc) == set()


# --- C5 order -------------------------------------------------------------

def test_c5_two_actions_need_a_declared_order():
    doc = good()
    del doc["flow"]
    assert "C5" in codes(doc)


def test_c5_two_reversible_actions_need_a_declared_order():
    doc = good()
    doc["actions"][1] = {"id": "tag", "text": "Tag it", "reversibility": "reversible", "reach": "a tag", "undo": "delete the tag"}
    del doc["flow"]
    assert "C5" in codes(doc)


def test_c5_a_required_claim_is_in_the_steps():
    doc = good()
    doc["flow"]["steps"].remove("tests")
    assert "C5" in codes(doc)


def test_c5_a_flow_reference_stays_in_the_statements_folder(tmp_path: Path):
    doc = good()
    outside = tmp_path / "outside.yaml"
    outside.write_text("flow: x\n")
    folder = tmp_path / "statements"
    folder.mkdir()
    for ref in (str(outside), "../outside.yaml"):
        doc["flow"]["ref"] = ref
        assert "C5" in {f["invariant"] for f in checkable.check(doc, PINNED, folder)}


def test_c5_one_irreversible_action_needs_a_declared_order():
    doc = good()
    doc["actions"] = [doc["actions"][1]]
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


def test_c5_an_empty_flow_declares_nothing():
    doc = good()
    doc["flow"] = {"steps": []}
    assert "C5" in codes(doc)


def test_c5_a_flow_reference_does_not_replace_the_steps():
    doc = good()
    doc["flow"] = {"ref": "flows/checkable.yaml"}
    assert "C5" in codes(doc)


def test_c5_a_flow_reference_must_be_a_file(tmp_path: Path):
    doc = good()
    doc["flow"]["ref"] = "flow.yaml"
    assert "C5" in {f["invariant"] for f in checkable.check(doc, PINNED, tmp_path)}
    (tmp_path / "flow.yaml").write_text("flow: x\n")
    assert checkable.check(doc, PINNED, tmp_path) == []


def test_c5_a_step_is_listed_once():
    doc = good()
    doc["flow"]["steps"].append("push")
    assert "C5" in codes(doc)


def test_c5_a_required_claim_comes_before_its_action():
    doc = good()
    doc["flow"]["steps"] = ["push", "deploy", "tests", "review", "live"]
    assert "C5" in codes(doc)


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


def test_c6_requires_names_a_known_claim():
    doc = good()
    doc["actions"][1]["requires"].append("ghost")
    assert "C6" in codes(doc)


def test_c6_a_gate_claim_is_also_required():
    doc = good()
    doc["actions"][1].update(gate="claim:tests", requires=["review"])
    assert "C6" in codes(doc)


def test_c6_an_unchecked_claim_guards_only_reversible_actions():
    doc = good()
    doc["actions"][1]["requires"].append("taste")
    assert "C6" in codes(doc)
    doc = good()
    doc["actions"][0]["requires"] = ["taste"]
    assert codes(doc) == set()


def test_c6_an_unchecked_claim_cannot_guard_a_compensable_action():
    doc = good()
    doc["actions"][0].update(reversibility="compensable", requires=["taste"])
    assert "C6" in codes(doc)


@pytest.mark.parametrize("gate", ["model:openai", "sensor:probe", "code", "claim:review", "claim:live", "claim:taste", "claim:nothing"])
def test_c6_only_a_person_or_a_command_claim_gates_an_irreversible_action(gate):
    doc = good()
    doc["actions"][1]["gate"] = gate
    assert "C6" in codes(doc)


def test_c6_the_performer_is_not_its_own_gate():
    doc = good()
    doc["performers"].append("human:owner")
    assert "C6" in codes(doc)
    doc["actions"][1]["gate"] = "human:reviewer"
    assert codes(doc) == set()


def test_coverage_counts_only_gates_that_hold():
    doc = good()
    assert checkable.coverage(doc)["actions_irreversible_gated"] == 1
    doc["actions"][1]["gate"] = "nobody"
    assert checkable.coverage(doc)["actions_irreversible_gated"] == 0


def test_coverage_counts():
    numbers = checkable.coverage(good())
    assert numbers["claims"] == 4
    assert numbers["claims_with_a_check_that_can_fail"] == 3
    assert numbers["claims_accepted"] == 0
    assert numbers["claims_by_rung"] == {"proof": 0, "replay": 1, "measurement": 1, "judgment": 1, "track-record": 0, "none": 1}
    assert numbers["actions"] == 2 and numbers["actions_irreversible"] == 1
    doc = good()
    del doc["claims"][0]["verifier"]["rejects"]
    doc["claims"][1].update(status="accepted")
    numbers = checkable.coverage(doc)
    assert numbers["claims_with_a_check_that_can_fail"] == 2 and numbers["claims_accepted"] == 1


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


def test_a_hop_names_both_ends():
    doc = good()
    del doc["feeds"][0]["to"]
    assert codes(doc) == {"C0"}


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


def test_c8_the_list_is_required_even_when_every_claim_has_a_check():
    doc = good()
    doc["claims"].pop()
    del doc["unverified"]
    assert "C8" in codes(doc)


def test_c8_a_claim_id_inside_another_word_does_not_name_the_claim():
    doc = good()
    doc["claims"][3]["id"] = "c"
    doc["unverified"] = ["receipts are verified"]
    assert "C8" in codes(doc)
    for near_miss in ("cc: another claim", "c whatever", "c-1: another claim", "C: upper case"):
        doc["unverified"] = [near_miss]
        assert "C8" in codes(doc), near_miss
    doc["unverified"] = ["c: whether the design is right"]
    assert codes(doc) == set()
    doc["unverified"] = ["c"]
    assert codes(doc) == set()


def test_c3_a_claim_with_no_check_carries_no_verifier():
    doc = good()
    doc["claims"][3]["verifier"] = {"origin": "code", "check": "true", "rejects": "false"}
    assert "C3" in codes(doc)


def test_c6_a_human_gate_names_someone():
    doc = good()
    doc["actions"][1]["gate"] = "human:"
    assert "C6" in codes(doc)
    doc["actions"][1]["gate"] = "anyone"
    assert "C6" in codes(doc)


# --- one spelling: an id, an origin or a date has exactly one written form ---

def _set(path, value):
    def edit(doc):
        target = doc
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value(target[path[-1]]) if callable(value) else value
    return edit


CANONICAL_FIELDS = {
    "claim id": ["claims", 0, "id"],
    "action id": ["actions", 0, "id"],
    "performer": ["performers", 0],
    "verifier origin": ["claims", 1, "verifier", "origin"],
    "required claim": ["actions", 1, "requires", 0],
    "flow step": ["flow", "steps", 0],
    "hop check": ["feeds", 0, "check"],
}
VARIANTS = {
    "trailing newline": lambda s: s + "\n",
    "leading newline": lambda s: "\n" + s,
    "trailing space": lambda s: s + " ",
    "leading space": lambda s: " " + s,
    "trailing tab": lambda s: s + "\t",
    "upper case": lambda s: s.upper(),
    "inner space": lambda s: s[:1] + " " + s[1:],
    "trailing carriage return": lambda s: s + "\r",
    "zero width space": lambda s: s + "\u200b",
    "non-ascii digit": lambda s: s + "\u0661",
}


@pytest.mark.parametrize("field", CANONICAL_FIELDS)
@pytest.mark.parametrize("variant", VARIANTS)
def test_a_canonical_field_has_exactly_one_spelling(field, variant):
    # Round 2 of the review passed "model:alpha\\n" as an origin: it matched the
    # pattern and still differed from the performer "model:alpha".
    doc = good()
    _set(CANONICAL_FIELDS[field], VARIANTS[variant])(doc)
    assert codes(doc) == {"C0"}, f"{field} with {variant} was not refused as malformed"


@pytest.mark.parametrize("variant", VARIANTS)
def test_an_independent_origin_cannot_be_respelled_into_the_performer(variant):
    doc = good()
    doc["claims"][1]["verifier"]["origin"] = VARIANTS[variant]("model:anthropic")
    assert "FAIL" in {f["level"] for f in checkable.check(doc, PINNED)}


@pytest.mark.parametrize("value", ["2026-11-01\n", "2026-11-01X", " 2026-11-01", "2026-11-1", "26-11-01", "2026/11/01", "\u0662\u0660\u0662\u0666-11-01", "9999-99-99", "2026-02-30", "2026-13-01", "20261101", "2026-W45-3", "2026-11-01T00:00:00"])
def test_a_date_has_exactly_one_spelling(value):
    doc = good()
    doc["claims"].append({"id": "forecast", "text": "x", "rung": "track-record", "verifier": {"origin": "code", "scored_by": "y", "prediction_recorded": value}})
    assert codes(doc) == {"C0"}


@pytest.mark.parametrize("gate", ["human:owner\n", "human:Owner", "human: owner", " human:owner", "human:"])
def test_a_gate_has_exactly_one_spelling(gate):
    doc = good()
    doc["actions"][1]["gate"] = gate
    assert "C6" in codes(doc)


@pytest.mark.parametrize(
    "predicate, accepted, refused",
    [
        ("_id", ["a", "tests", "a-1", "0x"], ["", "-a", "A", "a_b", "a b", "a\n", 1, None, ["a"]]),
        ("_origin", ["code", "model:openai", "sensor:http-probe", "human:the.owner_1"], ["", "code:x", "model:", "tool:x", "model:a b", "code\n", "CODE", "model:Openai", "model:-x", "model:_x", "model:.x", 1, None]),
        ("_performer", ["model:anthropic", "human:owner"], ["code", "sensor:x", "model:", "model:A", "human:owner\n", None]),
        ("_date", ["2026-11-01"], ["2026-11-1", "2026-11-01\n", "x2026-11-01", 20261101, None]),
        ("_whole", [0, 1, 127], [True, False, "1", 1.0, None]),
        ("_text", ["x", " x "], ["", "   ", "\n", 1, None, ["x"]]),
        ("_mapping", [{}, {"a": 1}], [[], "x", None, 1]),
        ("_mappings", [[], [{}], [{"a": 1}, {}]], [{}, [1], ["x"], [{}, "x"], None, "x"]),
    ],
)
def test_each_shape_predicate_accepts_and_refuses(predicate, accepted, refused):
    test = getattr(checkable, predicate)
    assert [value for value in accepted if not test(value)] == []
    assert [value for value in refused if test(value)] == []


# --- shape: nothing is skipped ---------------------------------------------

@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["actions"].append("delete production"),
        lambda d: d["claims"].append("an unchecked claim"),
        lambda d: d["performers"].append(42),
        lambda d: d.update(actions="deploy"),
        lambda d: d.update(feeds={"from": "a", "to": "b"}),
        lambda d: d.update(unverified="everything"),
        lambda d: d.update(unverified=[["nested"]]),
        lambda d: d.update(claims=None),
        lambda d: d.update(flow=["tests", "deploy"]),
        lambda d: d["flow"].update(steps="tests"),
        lambda d: d["claims"][0].update(verifier="pytest"),
        lambda d: d["claims"][0].update(receipt="it passed"),
        lambda d: d["claims"][0].update(id=7),
        lambda d: d["claims"][0].update(id="Tests"),
        lambda d: d["actions"][1].update(requires="tests"),
        lambda d: d["claims"][0]["verifier"].update(rejects_exit="1"),
        lambda d: d["claims"][0]["verifier"].update(rejects_exit=True),
        lambda d: d.update(learning="fix it"),
        lambda d: d.update(checkable=True),
    ],
)
def test_a_value_of_the_wrong_type_is_refused_not_skipped(mutate):
    doc = good()
    mutate(doc)
    assert codes(doc) == {"C0"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(notes="free text"),
        lambda d: d["claims"][0].update(owner="me"),
        lambda d: d["claims"][0]["verifier"].update(command="true"),
        lambda d: d["claims"][0].update(receipt={"revision": "a", "replay": "b", "result": "pass", "by": "me"}),
        lambda d: d["actions"][0].update(reversable="yes"),
        lambda d: d["flow"].update(order=["tests"]),
        lambda d: d["feeds"][0].update(note="x"),
        lambda d: d["learning"].update(owner="me"),
    ],
)
def test_a_key_outside_the_format_is_refused(mutate):
    doc = good()
    mutate(doc)
    assert codes(doc) == {"C0"}


def test_shape_errors_are_reported_alone():
    doc = good()
    doc["actions"].append("delete production")
    del doc["unverified"]
    assert {f["invariant"] for f in checkable.check(doc, UNKNOWN)} == {"C0"}


def test_a_key_written_twice_is_refused(tmp_path: Path):
    twice = tmp_path / "s.json"
    twice.write_text('{"checkable": 1, "problem": "a", "problem": "b"}')
    with pytest.raises(checkable.InputError, match="appears twice"):
        checkable.load_doc(twice)
    assert checkable.main(["check", str(twice)]) == checkable.EXIT_INVALID


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


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d["actions"][1].update(reversibility="reversible", undo="roll back"),
        lambda d: d["actions"][1].pop("requires"),
        lambda d: d["performers"].append("model:openai"),
        lambda d: d["unverified"].pop(),
        lambda d: d["flow"]["steps"].reverse(),
        lambda d: d["feeds"].pop(),
        lambda d: d["learning"].update(on_correction="ignore it"),
        lambda d: d.update(domain=["finance"]),
        lambda d: d["actions"][0].update(reach="everything"),
        lambda d: d.update(problem="A different problem."),
        lambda d: d["claims"][0].update(text="Something else."),
        lambda d: d["claims"][0].update(rung="proof"),
        lambda d: d["claims"].pop(1),
    ],
)
def test_pin_covers_the_whole_statement(repo: Path, edit):
    path = repo / "statement.json"
    doc = good()
    edit(doc)
    path.write_text(json.dumps(doc))
    assert checkable.pin_state(path, "main", doc)[0] == "changed"


def test_base_on_the_command_line(repo: Path, capsys):
    path = repo / "statement.json"
    assert checkable.main(["check", str(path), "--base", "main"]) == checkable.EXIT_OK
    assert "pin: pinned" in capsys.readouterr().out
    doc = good()
    doc["claims"][0]["verifier"]["check"] = "echo trust me"
    path.write_text(json.dumps(doc))
    assert checkable.main(["check", str(path), "--base", "main"]) == checkable.EXIT_FINDING
    assert "pin: changed" in capsys.readouterr().out


@pytest.mark.parametrize("base", ["", "   "])
def test_an_empty_base_is_a_base_that_cannot_be_compared(repo: Path, base):
    path = repo / "statement.json"
    assert checkable.pin_state(path, base, good())[0] == "unknown"
    assert checkable.main(["check", str(path), "--base", base]) == checkable.EXIT_NO_COMPARISON


def test_a_statement_that_is_not_on_the_base_exits_3_when_a_base_is_given(repo: Path):
    path = repo / "new.json"
    path.write_text(json.dumps(good()))
    assert checkable.main(["check", str(path), "--base", "main"]) == checkable.EXIT_NO_COMPARISON
    assert checkable.main(["check", str(path)]) == checkable.EXIT_OK


def test_pin_does_not_pass_an_option_to_git_as_a_revision(repo: Path):
    path = repo / "statement.json"
    assert checkable.pin_state(path, "--output=/tmp/x", good())[0] == "unknown"


def test_pin_is_unknown_for_a_link_that_leaves_the_repository(repo: Path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "statement.json"
    outside.write_text(json.dumps(good()))
    link = repo / "linked.json"
    link.symlink_to(outside)
    assert checkable.pin_state(link, "main", good())[0] == "unknown"


def test_pin_sees_a_verifier_field_added_to_a_claim(repo: Path):
    path = repo / "statement.json"
    doc = good()
    doc["claims"][0]["verifier"]["rejects_exit"] = 1
    path.write_text(json.dumps(doc))
    assert checkable.pin_state(path, "main", doc)[0] == "changed"


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
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_INVALID
    assert rows[0]["verdict"] == "INVALID" and "known-good case was refused" in rows[0]["why"]


def test_replay_a_known_bad_case_that_could_not_run_proves_nothing(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"]["rejects"] = "a-command-that-does-not-exist-zzz"
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_INVALID
    assert rows[0]["verdict"] == "INVALID" and "could not run" in rows[0]["why"]


@pytest.mark.parametrize("command", ["exit 126", "sh -c 'kill -SEGV $$'; exit $?", "exit 255"])
def test_replay_a_known_bad_case_ended_by_a_signal_proves_nothing(tmp_path: Path, command):
    doc = good()
    doc["claims"][0]["verifier"]["rejects"] = command
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_INVALID and rows[0]["verdict"] == "INVALID"


def test_replay_accepts_a_high_exit_status_when_the_statement_states_it(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"].update(rejects="exit 255", rejects_exit=255)
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_OK and rows[0]["verdict"] == "PASS"


def test_replay_holds_the_known_bad_case_to_its_stated_exit(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"].update(rejects="exit 3", rejects_exit=1)
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_INVALID
    assert rows[0]["verdict"] == "INVALID" and "not the stated 1" in rows[0]["why"]
    doc["claims"][0]["verifier"]["rejects_exit"] = 3
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_OK and rows[0]["verdict"] == "PASS"


def test_replay_and_route_refuse_a_malformed_statement(tmp_path: Path, capsys):
    doc = good()
    doc["actions"].append("delete production")
    path = tmp_path / "s.json"
    path.write_text(json.dumps(doc))
    assert checkable.main(["replay", str(path)]) == checkable.EXIT_INVALID
    assert checkable.main(["route", str(path)]) == checkable.EXIT_INVALID
    assert "malformed" in capsys.readouterr().err


def test_replay_a_check_that_hangs_is_a_failure(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"]["check"] = "sleep 30"
    rows, code = checkable.replay(doc, tmp_path, 1)
    assert code == checkable.EXIT_FINDING and rows[0]["verdict"] == "FAIL"


def test_replay_reports_the_first_invalid_claim_and_still_runs_the_rest(tmp_path: Path):
    doc = good()
    doc["claims"].append({"id": "second", "text": "x", "rung": "proof", "verifier": {"origin": "code", "check": "false", "rejects": "false"}})
    doc["claims"][0]["verifier"]["rejects"] = "true"
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert [r["verdict"] for r in rows] == ["INVALID", "FAIL"] and code == checkable.EXIT_INVALID


def test_replay_a_claim_without_its_commands_is_invalid(tmp_path: Path):
    doc = good()
    del doc["claims"][0]["verifier"]["rejects"]
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert rows[0]["verdict"] == "INVALID" and code == checkable.EXIT_INVALID


def test_replay_with_nothing_to_run_is_invalid_not_a_pass(tmp_path: Path):
    doc = good()
    doc["claims"] = doc["claims"][1:]
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert rows == [] and code == checkable.EXIT_INVALID


def test_replay_a_known_bad_case_that_hangs_is_invalid(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"]["rejects"] = "sleep 30"
    rows, code = checkable.replay(doc, tmp_path, 1)
    assert code == checkable.EXIT_INVALID
    assert rows[0]["verdict"] == "INVALID" and "timed out" in rows[0]["why"]


def test_a_timeout_also_stops_what_the_command_started(tmp_path: Path):
    import time

    started = time.monotonic()
    code, tail = checkable._run("sh -c 'sleep 30' & wait", tmp_path, 1)
    assert code is None and "timed out" in tail
    assert time.monotonic() - started < 10


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


def test_route_and_json_on_the_command_line(tmp_path: Path, capsys):
    statement = tmp_path / "s.json"
    statement.write_text(json.dumps(good()))
    index = tmp_path / "index.json"
    index.write_text(json.dumps(INDEX))
    assert checkable.main(["route", str(statement), "--index", str(index)]) == checkable.EXIT_OK
    out = capsys.readouterr().out
    assert "verifiers   judge[judgment]" in out and "shield      sandbox" in out
    assert "ontology    (nothing indexed for these domains)" in out
    assert checkable.main(["route", str(statement), "--index", str(index), "--json"]) == checkable.EXIT_OK
    assert json.loads(capsys.readouterr().out)["verifiers"] == [{"name": "judge", "kind": "skill", "rungs": ["judgment"]}]
    assert checkable.main(["check", str(statement), "--json"]) == checkable.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["checkable"] is True and report["coverage"]["claims"] == 4
    doc = good()
    del doc["unverified"]
    statement.write_text(json.dumps(doc))
    assert checkable.main(["check", str(statement), "--json"]) == checkable.EXIT_FINDING
    report = json.loads(capsys.readouterr().out)
    assert report["checkable"] is False
    assert {f["invariant"] for f in report["findings"] if f["level"] == "FAIL"} == {"C8"}
    assert checkable.main(["replay", str(statement), "--cwd", str(tmp_path), "--json"]) == checkable.EXIT_OK
    assert json.loads(capsys.readouterr().out)["rows"][0]["verdict"] == "PASS"


GOOD_ENTRY = {"name": "x", "kind": "skill", "parts": ["claims"], "domains": ["any"]}


@pytest.mark.parametrize(
    "entries, no_role",
    [
        ([{**GOOD_ENTRY, "kind": "tool"}], []),
        ([{**GOOD_ENTRY, "parts": ["claims", "magic"]}], []),
        ([{**GOOD_ENTRY, "parts": ["verifiers"], "rungs": ["vibes"]}], []),
        ([{**GOOD_ENTRY, "parts": []}], []),
        ([{**GOOD_ENTRY, "parts": ["verifiers"]}], []),
        ([{**GOOD_ENTRY, "domains": []}], []),
        ([{**GOOD_ENTRY, "kind": "service"}], []),
        ([GOOD_ENTRY, GOOD_ENTRY], []),
        ([GOOD_ENTRY], ["x"]),
    ],
)
def test_each_index_rule_refuses(entries, no_role):
    report, code = checkable.index_report({"entries": entries, "no_role": no_role}, None)
    assert report["problems"] and code == checkable.EXIT_FINDING


def test_an_index_that_leaves_a_part_empty_is_refused():
    report, code = checkable.index_report({"entries": [GOOD_ENTRY], "no_role": []}, None)
    assert report["problems"] == []
    assert "verifiers" in report["empty_parts"] and "claims" not in report["empty_parts"]
    assert code == checkable.EXIT_FINDING


def test_a_sound_index_passes():
    entries = [{"name": part, "kind": "service", "parts": [part], "domains": ["any"], "where": "here", **({"rungs": ["proof"]} if part == "verifiers" else {})} for part in checkable.PARTS]
    report, code = checkable.index_report({"entries": entries, "no_role": ["set-aside"]}, None)
    assert report == {"entries": 9, "no_role": 1, "problems": [], "empty_parts": [], "roster_checked": False}
    assert code == checkable.EXIT_OK


def test_the_flow_definition_runs_check_then_replay():
    _yaml_or_skip()
    import yaml

    flow = yaml.safe_load((SKILL / "assets" / "flows" / "checkable.yaml").read_text())
    assert flow["flow"] == "checkable" and list(flow["nodes"]) == ["pin", "statement", "replay"]
    assert flow["nodes"]["statement"]["needs"] == ["pin"] and flow["nodes"]["replay"]["needs"] == ["statement"]
    assert " check " in flow["nodes"]["statement"]["run"][2] and "--base" in flow["nodes"]["statement"]["run"][2]
    assert " replay " in flow["nodes"]["replay"]["run"][2]
    assert flow["nodes"]["replay"]["snapshot"] == "{{params.head}}"


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


@pytest.mark.parametrize("name", ["ship-checkable.json", "monthly-close.json"])
def test_the_shipped_examples_break_no_invariant(name):
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


# --- the exit status is the contract: never a traceback --------------------

def test_a_base_that_cannot_be_compared_exits_3(repo: Path, capsys):
    path = repo / "statement.json"
    assert checkable.main(["check", str(path), "--base", "origin/not-fetched"]) == checkable.EXIT_NO_COMPARISON
    assert "could not be compared" in capsys.readouterr().err
    assert checkable.main(["check", str(path), "--base", "main"]) == checkable.EXIT_OK
    assert checkable.main(["check", str(path)]) == checkable.EXIT_OK


def test_a_finding_outranks_a_comparison_that_could_not_be_made(repo: Path):
    path = repo / "statement.json"
    doc = good()
    del doc["unverified"]
    path.write_text(json.dumps(doc))
    assert checkable.main(["check", str(path), "--base", "origin/not-fetched"]) == checkable.EXIT_FINDING


@pytest.mark.parametrize(
    "name, content",
    [
        ("bytes.json", b"\xff\xfe not text"),
        ("deep.json", b"[" * 100000),
        ("list.json", b"[1, 2, 3]"),
        ("empty.json", b""),
    ],
)
def test_input_that_cannot_be_read_exits_2(tmp_path: Path, name, content):
    path = tmp_path / name
    path.write_bytes(content)
    for command in ("check", "replay", "route"):
        assert checkable.main([command, str(path)]) == checkable.EXIT_INVALID


@pytest.mark.parametrize("name", ["s.yaml", "s.yml", "S.YAML"])
def test_a_yaml_statement_is_not_read(tmp_path: Path, name, capsys):
    path = tmp_path / name
    path.write_text(json.dumps(good()))
    for command in ("check", "replay", "route"):
        assert checkable.main([command, str(path)]) == checkable.EXIT_INVALID
    assert "statements are JSON" in capsys.readouterr().err


def test_a_statement_has_a_size_limit(tmp_path: Path):
    doc = good()
    doc["problem"] = "x" * (checkable.MAX_BYTES + 1)
    path = tmp_path / "s.json"
    path.write_text(json.dumps(doc))
    assert checkable.main(["check", str(path)]) == checkable.EXIT_INVALID
    with pytest.raises(checkable.InputError, match="larger than"):
        checkable.parse(json.dumps(doc), "inline")
    doc["problem"] = "x" * 1000
    assert checkable.parse(json.dumps(doc), "inline")["problem"] == "x" * 1000


def test_the_base_copy_has_the_same_size_limit(repo: Path):
    path = repo / "statement.json"
    doc = good()
    doc["problem"] = "x" * (checkable.MAX_BYTES + 1)
    path.write_text(json.dumps(doc))
    _git(repo, "add", "statement.json")
    _git(repo, "commit", "-q", "-m", "an oversized statement on the base")
    small = good()
    path.write_text(json.dumps(small))
    state, why = checkable.pin_state(path, "main", small)
    assert state == "unknown" and "larger than" in why
    assert checkable.main(["check", str(path), "--base", "main"]) == checkable.EXIT_NO_COMPARISON


def test_the_base_copy_is_read_by_the_same_strict_reader(repo: Path):
    path = repo / "statement.json"
    path.write_text('{"checkable": 1, "problem": "a", "problem": "b"}')
    _git(repo, "add", "statement.json")
    _git(repo, "commit", "-q", "-m", "a key written twice on the base")
    path.write_text(json.dumps(good()))
    state, why = checkable.pin_state(path, "main", good())
    assert state == "unknown" and "appears twice" in why


def test_the_pin_gives_up_when_git_does_not_answer(repo: Path, monkeypatch):
    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=kwargs.get("timeout"))

    monkeypatch.setattr(checkable.subprocess, "run", hang)
    state, why = checkable.pin_state(repo / "statement.json", "main", good())
    assert state == "unknown" and "did not answer" in why


def _replay_process(tmp_path: Path, note: Path) -> subprocess.Popen:
    doc = good()
    doc["claims"][0]["verifier"]["check"] = f"echo $$ > {note}; exec sleep 60"
    statement = tmp_path / "s.json"
    statement.write_text(json.dumps(doc))
    return subprocess.Popen(
        [sys.executable, str(SKILL / "scripts" / "checkable.py"), "replay", str(statement), "--cwd", str(tmp_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _wait_until_gone(pid: int) -> bool:
    import time

    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


@pytest.mark.parametrize("signum, status", [(signal.SIGTERM, 143), (signal.SIGHUP, 129), (signal.SIGINT, 130)])
def test_a_signal_to_replay_stops_the_command_it_started(tmp_path: Path, signum, status):
    import time

    note = tmp_path / "command.pid"
    tool = _replay_process(tmp_path, note)
    try:
        for _ in range(200):
            if note.exists() and note.read_text().strip():
                break
            time.sleep(0.05)
        else:
            pytest.fail("the replayed command never started")
        command = int(note.read_text())
        tool.send_signal(signum)
        _out, err = tool.communicate(timeout=30)
        assert tool.returncode == status, err
        assert b"Traceback" not in err
        if not _wait_until_gone(command):
            os.kill(command, 9)
            pytest.fail(f"the replayed command outlived signal {signum}")
    finally:
        if tool.poll() is None:
            tool.kill()


def test_stop_on_signal_restores_the_handlers_it_replaced():
    before = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGHUP)
    with checkable.stop_on_signal():
        assert signal.getsignal(signal.SIGTERM) is not before[0]
    assert (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGHUP)) == before


def test_replay_in_a_folder_that_does_not_exist_exits_2(tmp_path: Path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps(good()))
    assert checkable.main(["replay", str(path), "--cwd", str(tmp_path / "gone")]) == checkable.EXIT_INVALID


def test_replay_survives_output_that_is_not_text(tmp_path: Path):
    doc = good()
    doc["claims"][0]["verifier"]["check"] = "printf '\\377\\376'; false"
    rows, code = checkable.replay(doc, tmp_path, 30)
    assert code == checkable.EXIT_FINDING and rows[0]["verdict"] == "FAIL"


def test_what_a_command_started_is_dead_after_a_timeout(tmp_path: Path):
    import time

    note = tmp_path / "child.pid"
    code, _ = checkable._run(f"sh -c 'echo $$ > {note}; exec sleep 30' & wait", tmp_path, 2)
    assert code is None
    child = int(note.read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        pytest.fail("the command's child was still running after the timeout")


def test_a_replayed_command_reads_nothing_from_standard_input(tmp_path: Path):
    program = (
        "import sys; sys.path.insert(0, sys.argv[1]); import checkable; from pathlib import Path; "
        "print(checkable._run('grep -q poison', Path(sys.argv[2]), 10)[0])"
    )
    done = subprocess.run(
        [sys.executable, "-c", program, str(SKILL / "scripts"), str(tmp_path)],
        input="poison\n", capture_output=True, text=True, timeout=60,
    )
    assert done.stdout.strip() == "1", done.stdout + done.stderr


def test_an_interrupt_does_not_leave_the_command_running(tmp_path: Path, monkeypatch):
    import time

    note = tmp_path / "child.pid"

    def interrupted(self, *args, **kwargs):
        for _ in range(100):
            if note.exists() and note.read_text().strip():
                break
            time.sleep(0.05)
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess.Popen, "communicate", interrupted)
    with pytest.raises(KeyboardInterrupt):
        checkable._run(f"echo $$ > {note}; exec sleep 30", tmp_path, 20)
    # The command replaced its shell, so it is this process's own child. A
    # killed child stays as a zombie until its parent collects it; collecting
    # it here is the proof that it ended.
    child = int(note.read_text())
    for _ in range(50):
        ended, _status = os.waitpid(child, os.WNOHANG)
        if ended == child:
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        pytest.fail("the command was still running after the interrupt")


@pytest.mark.parametrize("seconds", ["0", "-5", "999999999999999999999"])
def test_a_timeout_outside_its_range_exits_2(tmp_path: Path, seconds):
    path = tmp_path / "s.json"
    path.write_text(json.dumps(good()))
    assert checkable.main(["replay", str(path), "--timeout", seconds]) == checkable.EXIT_INVALID


def test_replay_from_a_folder_that_was_deleted_exits_2(tmp_path: Path, monkeypatch):
    path = tmp_path / "s.json"
    path.write_text(json.dumps(good()))
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    assert checkable.main(["replay", str(path)]) == checkable.EXIT_INVALID


def test_a_malformed_statement_is_not_compared_with_its_base(repo: Path, monkeypatch):
    path = repo / "statement.json"
    doc = good()
    doc["actions"].append("delete production")
    path.write_text(json.dumps(doc))

    def never(*args, **kwargs):
        raise AssertionError("pin_state ran on a malformed statement")

    monkeypatch.setattr(checkable, "pin_state", never)
    assert checkable.main(["check", str(path), "--base", "main"]) == checkable.EXIT_FINDING


def test_the_pin_does_not_depend_on_the_locale(tmp_path: Path):
    _git(tmp_path, "init", "-q", "-b", "main")
    doc = good()
    doc["problem"] = "Cerrar la conciliación del mes."
    path = tmp_path / "statement.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    _git(tmp_path, "add", "statement.json")
    _git(tmp_path, "commit", "-q", "-m", "state the problem")
    env = {**os.environ, "LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0"}
    done = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "checkable.py"), "check", str(path), "--base", "main"],
        capture_output=True, env=env, timeout=60,
    )
    assert done.returncode == checkable.EXIT_OK, done.stdout + done.stderr
    assert b"pin: pinned" in done.stdout


def test_a_finding_is_still_exit_1_when_a_key_cannot_be_printed(tmp_path: Path):
    path = tmp_path / "s.json"
    path.write_text('{"\\ud800": 1, "checkable": 1, "problem": "x", "performers": ["model:a"], "claims": [{"id": "c", "text": "t", "rung": "none"}]}')
    done = subprocess.run([sys.executable, str(SKILL / "scripts" / "checkable.py"), "check", str(path)], capture_output=True, timeout=60)
    assert done.returncode == checkable.EXIT_FINDING, done.stdout + done.stderr
    assert b"NOT CHECKABLE" in done.stdout


def test_the_default_timeout_is_five_minutes():
    args = checkable.build_parser().parse_args(["replay", "s.json"])
    assert args.timeout == 300


def test_a_timeout_is_a_bound_even_when_a_child_leaves_the_group(tmp_path: Path):
    import time

    leaver = f"{sys.executable} -c 'import os, time; os.setsid(); time.sleep(30)' & sleep 30"
    started = time.monotonic()
    code, tail = checkable._run(leaver, tmp_path, 1)
    assert code is None and "timed out" in tail
    assert time.monotonic() - started < 15


def test_a_timeout_survives_a_group_that_cannot_be_signalled(tmp_path: Path, monkeypatch):
    def refuse(pid, sig):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(checkable.os, "killpg", refuse)
    code, tail = checkable._run("sleep 2", tmp_path, 1)
    assert code is None and "timed out" in tail


@pytest.mark.parametrize(
    "index",
    [
        {"entries": ["x"], "no_role": []},
        {"entries": [{"kind": "skill", "parts": ["claims"], "domains": ["any"]}], "no_role": []},
        {"entries": [{"name": "x", "kind": "skill", "parts": "claims", "domains": ["any"]}], "no_role": []},
        {"entries": [], "no_role": [1]},
        {"entries": [{"name": "x", "parts": ["claims"], "domains": ["any"]}], "no_role": []},
        {"entries": {}, "no_role": []},
    ],
)
def test_a_malformed_index_exits_2(tmp_path: Path, index):
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index))
    statement = tmp_path / "s.json"
    statement.write_text(json.dumps(good()))
    assert checkable.main(["index", "--index", str(path)]) == checkable.EXIT_INVALID
    assert checkable.main(["route", str(statement), "--index", str(path)]) == checkable.EXIT_INVALID


def _tiny_repository(tmp_path: Path, indexed: list[str]) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "lint_skill_catalog.py").write_text("")
    for name in ("alpha", "beta"):
        folder = tmp_path / "skills" / "bucket" / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("x")
    entries = [
        {"name": part, "kind": "service", "parts": [part], "domains": ["any"], "where": "here", **({"rungs": ["proof"]} if part == "verifiers" else {})}
        for part in checkable.PARTS
    ]
    index = tmp_path / "skills" / "bucket" / "alpha" / "index.json"
    index.write_text(json.dumps({"entries": entries, "no_role": indexed}))
    return index


def test_index_finds_the_roster_by_walking_up_and_passes(tmp_path: Path):
    index = _tiny_repository(tmp_path, ["alpha", "beta"])
    assert checkable.find_root(index.parent) == tmp_path
    assert checkable.roster(tmp_path) == {"alpha", "beta"}
    assert checkable.main(["index", "--index", str(index), "--require-roster"]) == checkable.EXIT_OK
    assert checkable.main(["index", "--index", str(index), "--root", str(tmp_path)]) == checkable.EXIT_OK


def test_index_refuses_a_roster_with_an_untagged_or_a_dangling_skill(tmp_path: Path, capsys):
    index = _tiny_repository(tmp_path, ["alpha", "gone"])
    assert checkable.main(["index", "--index", str(index), "--require-roster"]) == checkable.EXIT_FINDING
    out = capsys.readouterr().out
    assert "untagged: beta" in out and "dangling: gone" in out
    assert "fix: give each untagged skill an entry in" in out and "fix: remove each dangling name from" in out


def test_an_error_is_one_line(tmp_path: Path, capsys):
    path = tmp_path / "s.json"
    path.write_text('{\n  "checkable": 1,\n  "problem": [\n    "unclosed"\n')
    assert checkable.main(["check", str(path)]) == checkable.EXIT_INVALID
    assert capsys.readouterr().err.count("\n") == 1


def test_the_flow_pin_step_refuses_an_uncommitted_statement(repo: Path):
    _yaml_or_skip()
    import yaml

    flow = yaml.safe_load((SKILL / "assets" / "flows" / "checkable.yaml").read_text())
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    params = {"repo": str(repo), "head": head, "statement": "statement.json", "tool": "statement.json"}

    def pin() -> int:
        argv = [part.replace("{{params.", "{").replace("}}", "}").format(**params) for part in flow["nodes"]["pin"]["run"]]
        return subprocess.run(argv, capture_output=True).returncode

    assert pin() == 0
    doc = good()
    doc["claims"][0]["verifier"]["check"] = "echo trust me"
    (repo / "statement.json").write_text(json.dumps(doc))
    assert pin() == 1
    params["head"] = "0" * 40
    assert pin() == 1


def test_the_flow_pin_step_refuses_an_untracked_statement_or_tool(repo: Path):
    _yaml_or_skip()
    import yaml

    flow = yaml.safe_load((SKILL / "assets" / "flows" / "checkable.yaml").read_text())
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (repo / "untracked.json").write_text(json.dumps(good()))

    def pin(statement: str, tool: str) -> int:
        params = {"repo": str(repo), "head": head, "statement": statement, "tool": tool}
        argv = [part.replace("{{params.", "{").replace("}}", "}").format(**params) for part in flow["nodes"]["pin"]["run"]]
        return subprocess.run(argv, capture_output=True).returncode

    assert pin("statement.json", "statement.json") == 0
    assert pin("untracked.json", "statement.json") == 1
    assert pin("statement.json", "untracked.json") == 1
    assert pin("statement.json", "missing.json") == 1


def test_index_with_a_root_that_has_no_skills_exits_2(tmp_path: Path):
    assert checkable.main(["index", "--root", str(tmp_path)]) == checkable.EXIT_INVALID


@pytest.mark.skipif(ROOT is None, reason="installed outside the monorepo: there is no roster to compare")
def test_an_untagged_skill_is_reported_with_the_file_to_edit(capsys):
    fixture = SKILL / "tests" / "fixtures" / "index-missing-a-skill.json"
    assert checkable.main(["index", "--index", str(fixture), "--root", str(ROOT)]) == checkable.EXIT_FINDING
    out = capsys.readouterr().out
    assert "untagged:" in out and "fix: give each untagged skill an entry in" in out


def test_index_without_a_roster_exits_3_when_one_is_required(tmp_path: Path):
    lone = tmp_path / "index.json"
    lone.write_text(json.dumps({"entries": [], "no_role": []}))
    assert checkable.main(["index", "--index", str(lone), "--require-roster"]) == checkable.EXIT_NO_COMPARISON
