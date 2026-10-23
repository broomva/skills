"""BRO-3405, measured on the owner's Mac on 2026-10-22/23:

team@ was logged in again (login-headless, 22:06Z) and switched to (00:01Z). From 00:48Z its usage
endpoint answered 429 with Retry-After 3600 to every call, one call per window (00:48, 01:52, 02:53,
03:54, 04:57, 05:57Z), so `usage` showed THROTTLED with numbers 111, 237, 357 minutes old and the
balancer was blind on the active account. Claude Code 2.1.306 calls the same endpoint with the same
account from every session, so the per-account budget is spent before our one call lands.

The fixes, each proven both ways here:
- the probe's own response carries both usage windows (stream-json `rate_limit_event`); when the
  endpoint refuses the active account, one probe per half staleNumbersMinutes refreshes its numbers;
- when a backoff ends, exactly one process (machine-wide) gets the retry;
- a login clears the account's usage backoff;
- once the endpoint answers again, the next call after the window takes the numbers back.
"""

import json
import sys
import time
from pathlib import Path

import fake_anthropic
import pytest

from conftest import pm

pytestmark = pytest.mark.new_only

A = "a@example.com"
B = "b@example.com"

# The line 2.1.306 printed for a probe on team@ at 06:42Z on 2026-10-23 (ids trimmed).
MEASURED_EVENT = {"type": "rate_limit_event", "rate_limit_info": {
    "status": "allowed", "resetsAt": 1792752600, "rateLimitType": "five_hour", "overageStatus": "rejected",
    "overageDisabledReason": "org_level_disabled", "isUsingOverage": False, "unifiedWindows": {
        "five_hour": {"utilization": 0.05, "resetsAt": 1792752600},
        "seven_day": {"utilization": 0.1, "resetsAt": 1793311200}}}, "session_id": "x"}


def _usage_calls(email):
    return [c for c in fake_anthropic.calls("usage") if c["email"] == email]


def _probe_calls(email):
    return [c for c in fake_anthropic.calls("probe") if c["email"] == email]


def _age_cache(seconds=3600):
    path = Path(pm.USAGE_CACHE_PATH)
    data = json.loads(path.read_text())
    for entry in data.get("accounts", {}).values():
        entry["cachedAt"] = entry.get("cachedAt", 0) - seconds
    path.write_text(json.dumps(data))


def _age_numbers(account_id, seconds):
    path = Path(pm.USAGE_CACHE_PATH)
    data = json.loads(path.read_text())
    data["accounts"][account_id]["numbersAt"] -= seconds
    path.write_text(json.dumps(data))


def _end_backoff(account_id):
    pm.update_state(lambda s: s["telemetry"][account_id].update(backoffUntil=time.time() - 1))


def _rows():
    return {r["email"]: r for r in pm.fetch_all_usage()}


def _throttled_world(world, readout=True):
    world.add_account(A, five_hour=40.0, seven_day=20.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    pm.fetch_all_usage(force_refresh=True)
    world.set_usage(A, usage_mode="429", retry_after="3600", readout=readout)
    pm.fetch_all_usage(force_refresh=True)
    _age_numbers(world.accounts[A]["id"], 111 * 60)
    _age_cache()
    return world.accounts[A]["id"]


# -- the probe readout ----------------------------------------------------------------------------

def test_the_measured_2_1_306_rate_limit_event_reads_as_percent_numbers():
    lines = ['{"type":"system","subtype":"init"}', json.dumps(MEASURED_EVENT), '{"type":"result","is_error":false}']
    readout = pm._probe_readout(lines)
    assert readout["five_hour"] == {"utilization": 0.05, "resetsAt": 1792752600}
    entry = pm._readout_entry("x", readout, 1792737733.0, 1792737740.0)
    assert entry["five_hour"]["utilization"] == 5.0 and entry["seven_day"]["utilization"] == 10.0
    assert entry["five_hour"]["resets_at"].startswith("2026-10-23T") and entry["telemetry"] == "ok"
    assert entry["numbersAt"] == 1792737733.0 and entry["numbersSource"] == "probe"


@pytest.mark.parametrize("windows", [
    {"five_hour": {"utilization": 0.05, "resetsAt": 1}},                                   # a window missing
    {"five_hour": {"utilization": 5, "resetsAt": 1}, "seven_day": {"utilization": 0.1, "resetsAt": 1}},  # not 0-1
    {"five_hour": {"utilization": "x", "resetsAt": 1}, "seven_day": {"utilization": 0.1, "resetsAt": 1}},
    None,
])
def test_a_readout_that_is_not_the_measured_shape_is_never_a_guess(windows):
    ev = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "unifiedWindows": windows}}
    assert pm._probe_readout([json.dumps(ev)]) is None


def test_10_22_sequence_throttled_active_account_gets_fresh_numbers_from_one_probe(world, capsys, monkeypatch):
    acc = _throttled_world(world)
    rows = _rows()
    assert rows[A]["telemetry"] == "throttled" and rows[A]["numbersAgeSeconds"] >= 111 * 60
    usage_before = len(_usage_calls(A))

    res = pm.balance_accounts()
    assert res["reason"] == "within_budget" and "telemetryNote" not in res, res
    rows = _rows()
    assert rows[A]["telemetry"] == "ok" and rows[A]["numbersSource"] == "probe"
    assert rows[A]["numbersAgeSeconds"] < 60 and rows[A]["fiveHourUtil"] == 40.0
    assert len(_probe_calls(A)) == 1 and len(_usage_calls(A)) == usage_before, \
        "the readout is one probe; the endpoint stays untouched inside its backoff"
    assert world.events("telemetry.readout")[-1]["accountId"] == acc

    for _ in range(3):  # later evaluations inside the readout interval: no probe, numbers kept
        _age_cache()
        pm.balance_accounts()
    assert len(_probe_calls(A)) == 1
    assert _rows()[A]["numbersSource"] == "probe"

    import pm_cli
    monkeypatch.setattr("sys.argv", ["provider_manager.py", "usage"])
    pm_cli.main(pm)
    out = capsys.readouterr().out
    assert "OK (via probe, numbers 0m old, endpoint throttled, next try in" in out
    assert "balancing on numbers is paused" not in out


def test_without_a_readout_the_numbers_stay_stale_and_say_so(world):
    _throttled_world(world, readout=False)
    res = pm.balance_accounts()
    assert res["reason"] == "telemetry_unavailable" and "111m old" in res["telemetryNote"]
    assert _rows()[A]["telemetry"] == "throttled" and _rows()[A]["numbersSource"] is None
    assert not world.events("telemetry.readout")
    for _ in range(4):  # a probe that reads nothing is not re-run every evaluation
        _age_cache()
        pm.balance_accounts()
    assert len(_probe_calls(A)) == 1


def test_readout_numbers_are_refreshed_before_they_go_stale_and_never_held_past_it(world):
    acc = _throttled_world(world)
    pm.balance_accounts()
    assert len(_probe_calls(A)) == 1
    _age_numbers(acc, 16 * 60)  # past half of staleNumbersMinutes: the next evaluation re-reads them
    pm.update_state(lambda s: s["probes"][acc].update(at=s["probes"][acc]["at"] - 16 * 60))
    _age_cache()
    pm.balance_accounts()
    assert len(_probe_calls(A)) == 2 and _rows()[A]["numbersAgeSeconds"] < 60

    world.set_usage(A, readout=False)  # no readout any more: the probe numbers age out, honestly
    _age_numbers(acc, 31 * 60)
    _age_cache()
    rows = _rows()
    assert rows[A]["telemetry"] == "throttled" and rows[A]["numbersAgeSeconds"] >= 31 * 60


def test_a_readout_is_never_taken_when_the_store_changes_hands_during_the_probe(world, monkeypatch):
    _throttled_world(world)
    real = pm._run_probe

    def probe_then_switch():
        out = real()
        world.activate(B)  # someone ran /login meanwhile
        return out
    monkeypatch.setattr(pm, "_run_probe", probe_then_switch)
    pm.balance_accounts()
    assert not world.events("telemetry.readout")
    assert _rows()[A]["numbersSource"] != "probe"


def test_a_readout_is_never_taken_for_a_standby(world):
    world.add_account(A, five_hour=40.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    pm.fetch_all_usage(force_refresh=True)
    world.set_usage(B, usage_mode="429", retry_after="3600")
    pm.fetch_all_usage(force_refresh=True)
    _age_numbers(world.accounts[B]["id"], 111 * 60)
    _age_cache()
    pm.balance_accounts()
    assert _probe_calls(A) == [] and _probe_calls(B) == []
    assert _rows()[B]["telemetry"] == "throttled"


def test_a_rejected_readout_is_a_limit_the_probe_confirms_and_fails_over(world):
    _throttled_world(world)
    world.set_usage(A, exhausted=True, probe_five_hour=100.0)
    res = pm.balance_accounts(source="proactive_balance", automatic=True)
    assert res["action"] == "switched" and res["reason"] == "confirmed_rate_limited", res
    assert world.store_email() == B


# -- one retry per backoff window -----------------------------------------------------------------

def test_one_process_gets_the_retry_when_a_backoff_ends(world):
    acc = _throttled_world(world)
    now = time.time()
    assert pm._claim_usage_call(acc, now) is False, "inside the backoff nobody calls"
    _end_backoff(acc)
    claims = [pm._claim_usage_call(acc, time.time()) for _ in range(5)]
    assert claims == [True, False, False, False, False], "the retry is one call, whoever kicks"
    st = pm.load_state()["telemetry"][acc]
    assert st["claimedBy"] and st["backoffUntil"] > time.time()


def test_after_the_window_the_endpoint_is_called_once_and_429_renews_it(world):
    acc = _throttled_world(world)
    n = len(_usage_calls(A))
    _end_backoff(acc)
    for _ in range(6):  # six kicks from six sessions, all after the window ended
        _age_cache()
        pm.fetch_all_usage()
    assert len(_usage_calls(A)) == n + 1
    assert pm.load_state()["telemetry"][acc]["backoffUntil"] - time.time() > 3500


def test_once_the_endpoint_answers_the_numbers_come_back_from_it(world):
    acc = _throttled_world(world)
    pm.balance_accounts()
    assert _rows()[A]["numbersSource"] == "probe"
    world.set_usage(A, usage_mode="ok", five_hour=55.0)
    _end_backoff(acc)
    _age_cache()
    rows = _rows()
    assert rows[A]["telemetry"] == "ok" and rows[A]["numbersSource"] == "endpoint"
    assert rows[A]["fiveHourUtil"] == 55.0 and rows[A]["numbersAgeSeconds"] < 60
    assert acc not in (pm.load_state().get("telemetry") or {}), "a good read ends the backoff"


def test_a_failed_retry_holds_off_the_others_for_the_claim_lease(world):
    acc = _throttled_world(world)
    world.set_usage(A, usage_mode="500")
    _end_backoff(acc)
    n = len(_usage_calls(A))
    for _ in range(4):
        _age_cache()
        pm.fetch_all_usage()
    assert len(_usage_calls(A)) == n + 1


# -- a login ends the backoff ---------------------------------------------------------------------

def _login_world(world, monkeypatch, email):
    shim = world.bin / "node"
    shim.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, Path(__file__).parent / "fakeworld/fake_node.py"))
    shim.chmod(0o755)
    monkeypatch.setenv("FAKE_BROWSER_EMAIL", email)
    monkeypatch.setenv("FAKE_BROWSER_ORG", world.accounts[email]["org"])


def test_a_login_clears_that_accounts_usage_backoff(world, monkeypatch):
    acc = _throttled_world(world)
    world.set_usage(A, usage_mode="ok")
    _login_world(world, monkeypatch, A)
    assert pm.login_headless(email=A)["success"]
    assert acc not in (pm.load_state().get("telemetry") or {})
    _age_cache()
    rows = _rows()
    assert rows[A]["telemetry"] == "ok" and rows[A]["numbersSource"] == "endpoint" and rows[A]["numbersAgeSeconds"] < 60


def test_another_accounts_login_leaves_the_backoff_alone(world, monkeypatch):
    acc = _throttled_world(world)
    _login_world(world, monkeypatch, B)
    assert pm.login_headless(email=B)["success"]
    assert pm.load_state()["telemetry"][acc]["backoffUntil"] > time.time() + 3000


# -- P20 round 1 ----------------------------------------------------------------------------------

def test_stream_json_framing_never_hides_the_result_or_a_limit(world, monkeypatch):
    from unittest.mock import MagicMock
    init = json.dumps({"type": "system", "subtype": "init", "session_id": "x"})
    assistant = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "OK"}]}})
    cases = {
        "limited": (1, init + "\nClaude AI usage limit reached|1792752600\n"),  # plain text after init
        "unknown": (0, init + "\n" + assistant + "\n"),  # cut off before its result: not an answer
        "ok": (0, "\n".join([init, json.dumps(MEASURED_EVENT), assistant,
                             json.dumps({"type": "result", "is_error": False, "result": "OK"})])),
    }
    for label, (rc, out) in cases.items():
        monkeypatch.setattr(pm.subprocess, "run", lambda *a, **k: MagicMock(returncode=rc, stdout=out, stderr=""))
        assert pm._run_probe()[0] == label, label
    assert pm._run_probe()[2]["five_hour"]["utilization"] == 0.05


def test_a_standby_401_inside_its_own_retry_refreshes_and_reads(world):
    world.add_account(A)
    world.add_account(B, five_hour=33.0)
    world.activate(A)
    pm.fetch_all_usage(force_refresh=True)
    acc = world.accounts[B]["id"]
    pm._note_429(acc, "3600", time.time())
    _end_backoff(acc)
    fake_anthropic.expire_access(world.orca_creds(B)["claudeAiOauth"]["accessToken"])
    _age_cache()
    row = _rows()[B]
    assert row["telemetry"] == "ok" and row["fiveHourUtil"] == 33.0, \
        "the 401 retry is part of the claimed call, not a second caller to hold off"


def test_a_readout_from_a_probe_the_readout_did_not_attribute_is_never_used(world):
    acc = _throttled_world(world)
    stray = {"status": "allowed", "five_hour": {"utilization": 0.9, "resetsAt": int(time.time()) + 3600},
             "seven_day": {"utilization": 0.9, "resetsAt": int(time.time()) + 86400}}
    pm.update_state(lambda s: s.setdefault("probes", {}).__setitem__(
        acc, {"at": time.time(), "result": "ok", "detail": "limited-path probe", "readout": stray}))
    pm.balance_accounts()
    assert _rows()[A]["numbersSource"] != "probe" and _probe_calls(A) == []


def test_a_readout_probe_records_the_reset_so_a_limit_it_found_can_end_with_it(world):
    acc = _throttled_world(world)
    pm.balance_accounts()
    rec = pm.load_state()["probes"][acc]
    assert rec["readoutFor"] == acc and rec["fiveHourAtProbe"] == 40.0
    assert pm._parse_ts(rec["resetsAt"]) > time.time()


def test_a_missing_readout_is_logged_and_a_dry_run_never_probes(world):
    acc = _throttled_world(world, readout=False)
    pm.balance_accounts(dry_run=True)
    assert _probe_calls(A) == [], "a dry run makes no request"
    pm.balance_accounts()
    assert [e["accountId"] for e in world.events("telemetry.readout_missing")] == [acc]


# -- P20 round 2 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("info", [
    "unexpected",                                                              # not an object
    {"status": "unexpected", "unifiedWindows": MEASURED_EVENT["rate_limit_info"]["unifiedWindows"]},
    {"unifiedWindows": MEASURED_EVENT["rate_limit_info"]["unifiedWindows"]},   # no status
    {"status": "allowed", "unifiedWindows": "x"},
    {"status": "allowed", "unifiedWindows": {"five_hour": "x", "seven_day": "y"}},
])
def test_a_malformed_rate_limit_event_is_no_readout_and_never_raises(info):
    try:
        readout = pm._probe_readout([json.dumps({"type": "rate_limit_event", "rate_limit_info": info})])
    except Exception as e:  # noqa: BLE001 - a raise here would abort the balancer's evaluation
        raise AssertionError("malformed telemetry raised %r" % e)
    assert readout is None


def test_an_untyped_line_is_never_the_probes_answer(world, monkeypatch):
    from unittest.mock import MagicMock
    out = '{"future_stream_event": true}\n'
    monkeypatch.setattr(pm.subprocess, "run", lambda *a, **k: MagicMock(returncode=0, stdout=out, stderr=""))
    assert pm._run_probe()[0] == "unknown"


def test_a_429_that_began_before_the_login_cannot_restore_the_backoff(world, monkeypatch):
    acc = _throttled_world(world)
    began = time.time() - 1  # a `usage` call with the old grant, in flight across the login
    _login_world(world, monkeypatch, A)
    assert pm.login_headless(email=A)["success"]
    pm._note_429(acc, "3600", began)
    assert acc not in (pm.load_state().get("telemetry") or {})
    pm._note_429(acc, "3600", time.time())  # a 429 for the new grant still backs off
    assert pm.load_state()["telemetry"][acc]["backoffUntil"] > time.time() + 3500
