"""Each parser against the copies captured on Claude Code 2.1.280 (and Paseo
0.9.2), the Claude Code surfaces captured on the pinned version, and the
shapes that must fail the surface."""
from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest
from conftest import FAKE_BEARER, FIXTURE, PINNED_FIXTURE

from fleetlib import parsers


def _read(rel: str) -> str:
    return (FIXTURE / rel).read_text()


# --------------------------------------------------------------------------
# The pin

def test_the_pinned_capture_was_taken_on_the_pinned_version():
    meta = json.loads((PINNED_FIXTURE / "meta.json").read_text())
    assert parsers.cc_version((PINNED_FIXTURE / "claude" / "version.txt").read_text()) == parsers.PINNED_CC_VERSION
    assert meta["claude_version"] == parsers.PINNED_CC_VERSION
    assert PINNED_FIXTURE.name == "cc-%s" % parsers.PINNED_CC_VERSION


def test_the_scenario_capture_is_the_2_1_280_one(meta):
    assert meta["claude_version"] == "2.1.280" == parsers.cc_version(_read("claude/version.txt"))


def test_the_pinned_listing_parses_with_no_drift():
    text = (PINNED_FIXTURE / "claude" / "agents.json").read_text()
    rows, drift = parsers.parse_listing(text)
    assert drift == []
    assert rows and len(rows) == len(json.loads(text))


def test_every_pinned_job_file_parses_and_one_was_written_by_the_pinned_version():
    parsed = [parsers.parse_job_state(p.read_text(), p.parent.name)
              for p in sorted((PINNED_FIXTURE / "claude" / "jobs").glob("*/state.json"))]
    assert parsed and all(j["state_known"] for j in parsed)
    assert parsers.PINNED_CC_VERSION in {j["cli_version"] for j in parsed}
    for j in parsed:
        assert j["job_id"] == j["session_id"][:8] and j["updated_at"]


def test_cc_version_reads_the_cli_banner():
    assert parsers.cc_version("2.1.280 (Claude Code)\n") == "2.1.280"
    assert parsers.cc_version("garbage") is None


# --------------------------------------------------------------------------
# claude agents --json --all

def test_the_captured_listing_parses_with_no_drift():
    rows, drift = parsers.parse_listing(_read("claude/agents.json"))
    assert drift == []
    assert len(rows) == len(json.loads(_read("claude/agents.json")))
    kinds = collections.Counter(r["kind"] for r in rows)
    assert set(kinds) == {"interactive", "background"}
    for r in rows:
        if r["kind"] == "background":
            assert r["bg_id"] == r["session_id"][:8] and r["state"] in parsers.LISTING_STATES
        else:
            assert r["state"] is None and r["pid"] is not None and r["status"] in parsers.LISTING_STATUSES
        if r["status"] == "waiting":
            assert r["waiting_for"]
        assert r["started_at"] > 1e9  # epoch seconds, from milliseconds


@pytest.mark.parametrize("drop", ["sessionId", "kind", "cwd", "name", "startedAt"])
def test_a_listing_row_missing_a_required_field_fails_the_surface(drop):
    rows = json.loads(_read("claude/agents.json"))
    del rows[0][drop]
    with pytest.raises(parsers.ParseError):
        parsers.parse_listing(json.dumps(rows))


def test_a_listing_that_is_not_an_array_or_not_json_fails():
    for text in ('{"agents": []}', "not json", ""):
        with pytest.raises(parsers.ParseError):
            parsers.parse_listing(text)


def test_new_fields_and_unfamiliar_enum_values_are_kept_and_reported_as_drift():
    rows = json.loads(_read("claude/agents.json"))
    rows[0]["needs"] = "something new"
    rows[1]["status"] = "sleeping"
    out, drift = parsers.parse_listing(json.dumps(rows))
    assert len(out) == len(rows)
    assert any("new field" in d and "needs" in d for d in drift)
    assert any("sleeping" in d for d in drift)


# --------------------------------------------------------------------------
# ~/.claude/jobs/<id>/state.json

def _jobs():
    for p in sorted((FIXTURE / "claude" / "jobs").glob("*/state.json")):
        yield p.parent.name, p.read_text()


def test_every_captured_job_file_parses():
    parsed = [parsers.parse_job_state(t, jid) for jid, t in _jobs()]
    assert len(parsed) >= 40
    states = collections.Counter(j["state"] for j in parsed)
    assert set(states) <= set(parsers.JOB_STATES) and "blocked" in states and "done" in states
    for j in parsed:
        assert j["job_id"] == j["session_id"][:8]


def test_the_limit_text_is_recognised_and_its_reset_read():
    limited = [parsers.parse_job_state(t, jid) for jid, t in _jobs()]
    limited = [j for j in limited if j["limit_text"]]
    assert limited, "the capture holds usage-limit deaths"
    for j in limited:  # Claude Code's own text, kept verbatim by the capture
        assert j["state"] == "blocked" and parsers.RESET_RE.fullmatch(j["reset_text"])
        assert parsers.reset_epoch(j["reset_text"], j["updated_at"]) > j["updated_at"]
    # 10am in Bogota (UTC-5) is 15:00Z; from 16:00Z the next one is tomorrow.
    base = 1790784000.0  # 2026-09-30T16:00:00Z
    t = parsers.reset_epoch("resets 10am (America/Bogota)", base)
    assert t is not None and t > base and (t - base) == pytest.approx(23 * 3600)
    assert parsers.reset_epoch("resets 9:50am (America/Bogota)", base - 4 * 3600) == pytest.approx(
        base - 4 * 3600 + 2 * 3600 + 50 * 60)
    # 16:00Z is 11:00 in Bogota; 10:50pm there is 11h50m later.
    assert parsers.reset_epoch("resets 10:50pm (America/Bogota)", base) == pytest.approx(base + 11 * 3600 + 50 * 60)
    assert parsers.reset_epoch("no time here", base) is None
    assert parsers.reset_epoch("resets 10am (Not/AZone)", base) is None


def test_every_captured_job_file_gives_its_update_time():
    # 2.1.280 writes updatedAt as an ISO string (P20 round 1: it was read as
    # epoch ms only, so every real job's time was None).
    for jid, text in _jobs():
        raw = json.loads(text)["updatedAt"]
        j = parsers.parse_job_state(text, jid)
        assert isinstance(raw, str) and j["updated_at"] is not None and j["updated_at"] > 1.7e9
    ms = {"state": "done", "sessionId": "abcd1234-0000-4000-8000-000000000001", "updatedAt": 1790784000000}
    assert parsers.parse_job_state(json.dumps(ms), "abcd1234")["updated_at"] == 1790784000.0


def test_a_dated_reset_is_read_as_that_date():
    base = 1790784000.0  # 2026-09-30T16:00:00Z, 11:00 in Bogota
    assert parsers.reset_epoch("hit your weekly limit · resets Oct 3, 10am (America/Bogota)", base) == \
        pytest.approx(base + 3 * 86400 - 3600)
    assert parsers.reset_epoch("resets Oct 3 at 9:30pm (America/Bogota)", base) == \
        pytest.approx(base + 3 * 86400 + 10.5 * 3600)
    assert parsers.reset_epoch("resets Foo 3, 10am (America/Bogota)", base) is None


def test_an_unfamiliar_waiting_for_value_is_drift():
    rows = json.loads(_read("claude/agents.json"))
    live = [r for r in rows if "pid" in r][0]
    live.update(status="waiting", waitingFor="some new prompt")
    _, drift = parsers.parse_listing(json.dumps(rows))
    assert any("waitingFor" in d and "some new prompt" in d for d in drift)


def test_a_job_file_never_carries_env_output_or_inline_settings_into_the_parse():
    for jid, text in _jobs():
        j = parsers.parse_job_state(text, jid)
        blob = json.dumps(j)
        assert "FIXTURE_ENV" not in blob and "crossSessionInbound" not in blob
        assert j["settings_path"] is None  # the captured flags carry inline JSON, never a path
    flags = {"state": "working", "sessionId": "abcd1234-0000-4000-8000-000000000001",
             "respawnFlags": ["--settings", "/Users/x/.local/state/fleet/driver.json"]}
    assert parsers.parse_job_state(json.dumps(flags), "abcd1234")["settings_path"] == \
        "/Users/x/.local/state/fleet/driver.json"


def test_a_job_file_without_state_or_session_id_fails():
    for d in ({"sessionId": "abcd1234-0000-4000-8000-000000000001"}, {"state": "done"}, []):
        with pytest.raises(parsers.ParseError):
            parsers.parse_job_state(json.dumps(d), "abcd1234")


# --------------------------------------------------------------------------
# Paseo agent records

def _records():
    for p in sorted((FIXTURE / "paseo" / "agents").glob("*/*.json")):
        yield str(p), p.read_text()


def test_every_captured_record_parses_and_the_bearer_is_never_extracted():
    assert FAKE_BEARER in "".join(t for _, t in _records()), "the fixture plants a fake bearer"
    parsed = [parsers.parse_paseo_record(t, w) for w, t in _records()]
    blob = json.dumps(parsed)
    assert FAKE_BEARER not in blob and "Authorization" not in blob and "6767" not in blob
    assert any(r["archived"] for r in parsed) and any(not r["archived"] for r in parsed)
    assert all(r["session_id"] for r in parsed)


def test_a_record_falls_back_to_the_persistence_session_id():
    rec = json.loads(next(_records())[1])
    rec["runtimeInfo"]["sessionId"] = None
    out = parsers.parse_paseo_record(json.dumps(rec))
    assert out["session_id_from"] == "persistence"
    rec["persistence"]["sessionId"] = None
    assert parsers.parse_paseo_record(json.dumps(rec))["session_id"] is None


def test_label_values_are_kept_only_for_id_like_keys():
    rec = json.loads(next(_records())[1])
    rec["labels"] = {"coordinator": "f5307ce7", "note": "free text that is not kept", "source": "granola-bridge"}
    out = parsers.parse_paseo_record(json.dumps(rec))
    assert out["labels"] == {"coordinator": "f5307ce7", "note": "", "source": "granola-bridge"}


# --------------------------------------------------------------------------
# Paseo schedules

def test_every_captured_schedule_parses_without_its_prompt_or_output():
    scheds = [parsers.parse_schedule(p.read_text(), p.name)
              for p in sorted((FIXTURE / "paseo" / "schedules").glob("*.json"))]
    assert len(scheds) == 5
    assert collections.Counter(s["status"] for s in scheds) == {"active": 3, "paused": 2}
    assert sum(1 for s in scheds if s["max_runs"] == 1) == 3
    blob = json.dumps(scheds)
    assert "prompt (not read)" not in blob and "output (not read)" not in blob


# --------------------------------------------------------------------------
# GitHub

@pytest.mark.parametrize("url,slug", [
    ("https://github.com/broomva/skills.git", "broomva/skills"),
    ("https://github.com/broomva/skills", "broomva/skills"),
    ("git@github.com:broomva/broomva.tech.git", "broomva/broomva.tech"),
    ("ssh://git@github.com/GetOrg/repo-name.git", "GetOrg/repo-name"),
    ("https://gitlab.com/broomva/skills.git", None),
    ("https://example.invalid/client/sri.git", None),
    ("", None),
    (None, None),
])
def test_the_slug_comes_from_a_github_origin_or_not_at_all(url, slug):
    assert parsers.parse_remote_slug(url) == slug


def _rules(repo: str):
    return parsers.parse_rules(_read("gh/%s/rules.json" % repo))


def test_the_captured_rulesets_evaluate_as_the_spec_describes():
    ws = parsers.evaluate_rules(_rules("broomva__workspace"), 15368)
    assert ws["driver_eligible"] and ws["flags"] == [] and ws["approvals"] == 0
    bs = parsers.evaluate_rules(_rules("broomva__bstack"), 15368)
    assert bs["driver_eligible"]
    sk = parsers.evaluate_rules(_rules("broomva__skills"), 15368)
    assert not sk["driver_eligible"] and sk["flags"] == ["no pull_request rule"]
    bt = parsers.evaluate_rules(_rules("broomva__broomva.tech"), 15368)
    assert not bt["driver_eligible"]
    assert set(bt["flags"]) == {"no pull_request rule", "no required status checks",
                                "force-push to the default branch not blocked"}


def test_skills_becomes_eligible_once_its_pull_request_rule_lands():
    # Owner decision 2026-09-30 (§8 Q1): skills gets a pull_request rule. The
    # check reads the effective rules every tick, so nothing else changes.
    rules = json.loads(_read("gh/broomva__skills/rules.json"))
    rules.append({"type": "pull_request", "parameters": {"required_approving_review_count": 0}})
    out = parsers.evaluate_rules(parsers.parse_rules(json.dumps(rules)), 15368)
    assert out["driver_eligible"] and out["flags"] == []


def test_a_required_check_not_pinned_to_github_actions_is_flagged():
    rules = json.loads(_read("gh/broomva__workspace/rules.json"))
    for r in rules:
        if r["type"] == "required_status_checks":
            r["parameters"]["required_status_checks"][0].pop("integration_id", None)
            r["parameters"]["required_status_checks"].append({"context": "Other App", "integration_id": 1})
    out = parsers.evaluate_rules(parsers.parse_rules(json.dumps(rules)), 15368)
    assert not out["driver_eligible"]
    assert out["unpinned"] == ["Merge Gate", "Other App"]
    assert any("not pinned" in f for f in out["flags"])


def test_rules_that_are_not_an_array_fail():
    with pytest.raises(parsers.ParseError):
        parsers.parse_rules('{"message": "Not Found"}')


def test_the_captured_pr_lists_parse():
    for repo in ("broomva__workspace", "broomva__skills"):
        prs = parsers.parse_pr_list(_read("gh/%s/prs.json" % repo))
        assert prs and all(isinstance(p["number"], int) and p["head"] for p in prs)
    fake = [{"number": 1, "title": "bump x", "headRefName": "dependabot/npm/x", "isDraft": False,
             "author": {"login": "app/dependabot", "is_bot": True}, "labels": [{"name": "hold"}]}]
    p = parsers.parse_pr_list(json.dumps(fake))[0]
    assert p["dependabot"] and p["bot"] and p["labels"] == ["hold"] and p["fork"] is False  # absent reads as not-a-fork
    forked = parsers.parse_pr_list(json.dumps([dict(fake[0], number=2, isCrossRepository=True)]))[0]
    assert forked["fork"] is True


# --------------------------------------------------------------------------
# launchd

def test_the_captured_launchctl_print_parses():
    kg = parsers.parse_launchctl_print(_read("launchd/com.broomva.kg-compile.print.txt"))
    assert kg["loaded"] and kg["running"] is False and isinstance(kg["runs"], int)
    assert kg["last_exit"] == 0
    never = parsers.parse_launchctl_print("gui/501/x = {\n\tstate = not running\n\tlast exit code = (never exited)\n}")
    assert never["last_exit"] == "(never exited)"


def test_a_named_exit_code_is_read_as_its_number():
    named = parsers.parse_launchctl_print("x = {\n\tstate = not running\n\tlast exit code = 78: EX_CONFIG\n}")
    assert named["last_exit"] == 78
