"""BRO-3192, Claude side, measured on the owner's Mac on 2026-10-19:

- usage telemetry for the active account had been THROTTLED for over two hours: the 429 backoff must
  honour Retry-After (or back off exponentially, capped), persist, and keep every kick off the endpoint;
  `usage` and the balancer must say how old the last good numbers are, and what the balancer still does;
- a dead grant (team@, NEEDS_LOGIN) was refreshed every ~5 minutes, 205 times in a day;
- `pendingSignals` from three days earlier sat in the state, past their 15-minute TTL.
"""

import json
import time
from email.utils import formatdate
from pathlib import Path

import fake_anthropic
import pytest

from conftest import pm

pytestmark = pytest.mark.new_only

A = "a@example.com"
B = "b@example.com"


def _usage_calls(email):
    return [c for c in fake_anthropic.calls("usage") if c["email"] == email]


def _refresh_calls(world, email):
    return [c for c in fake_anthropic.calls("refresh") if c["email"] == email]


def _age_usage_cache(seconds=3600):
    path = Path(pm.USAGE_CACHE_PATH)
    data = json.loads(path.read_text())
    for entry in data.get("accounts", {}).values():
        entry["cachedAt"] = entry.get("cachedAt", 0) - seconds
    path.write_text(json.dumps(data))


def _age_numbers(account_id, seconds):
    path = Path(pm.USAGE_CACHE_PATH)
    data = json.loads(path.read_text())
    entry = data["accounts"][account_id]
    entry["numbersAt"] = entry["numbersAt"] - seconds
    path.write_text(json.dumps(data))


# -- 429 backoff ----------------------------------------------------------------------------------

def test_retry_after_is_honoured_floored_and_capped_and_exponential_without_it(world):
    world.add_account(A)
    acc = world.accounts[A]["id"]
    now = time.time()
    assert pm._note_429(acc, "3600", now) == pytest.approx(now + 3600)
    assert pm._note_429(acc, "0", now) == pytest.approx(now + pm.RETRY_AFTER_FLOOR_SECONDS), \
        "Retry-After: 0 must not let every kick call the endpoint again"
    assert pm._note_429(acc, "99999999", now) == pytest.approx(now + pm.RETRY_AFTER_CAP_SECONDS)
    http_date = formatdate(now + 900, usegmt=True)
    assert pm._note_429(acc, http_date, now) == pytest.approx(now + 900, abs=2)
    pm.update_state(lambda s: s["telemetry"].pop(acc))
    waits = [pm._note_429(acc, None, now) - now for _ in range(6)]
    assert waits == [120, 240, 480, 960, 1800, 1800]
    assert pm.load_state()["telemetry"][acc]["backoffStep"] == 6, "the backoff is persisted"


def test_kicks_inside_a_retry_after_backoff_never_call_the_usage_endpoint(world, pmh, monkeypatch):
    world.add_account(A, five_hour=40.0)
    world.add_account(B)
    world.activate(A)
    pm.fetch_all_usage(force_refresh=True)
    world.set_usage(A, usage_mode="429", retry_after="3600")
    rows = {r["email"]: r for r in pm.fetch_all_usage(force_refresh=True)}
    assert rows[A]["telemetry"] == "throttled" and rows[A]["isRateLimited"] is False
    assert 3500 < rows[A]["backoffRemainingSeconds"] <= 3600
    n = len(_usage_calls(A))
    monkeypatch.setenv("PROVIDER_MANAGER_INLINE", "1")
    for _ in range(4):  # four sessions' prompts, each a kick that runs an evaluation
        pm.update_state(lambda s: s.update(lastEvalAt=0, lastKickAt=0))
        _age_usage_cache()
        pmh.handle_prompt_submit({})
    assert len(_usage_calls(A)) == n, "a kick inside the backoff reached the usage endpoint"
    assert pm.telemetry_summary()[A]["backoffRemainingMinutes"] >= 58


def test_usage_and_state_show_the_age_of_the_last_good_numbers(world, capsys, monkeypatch):
    world.add_account(A, five_hour=40.0)
    world.add_account(B)
    world.activate(A)
    pm.fetch_all_usage(force_refresh=True)
    world.set_usage(A, usage_mode="429", retry_after="3600")
    pm.fetch_all_usage(force_refresh=True)
    _age_numbers(world.accounts[A]["id"], 139 * 60)
    import pm_cli

    monkeypatch.setattr("sys.argv", ["provider_manager.py", "usage"])
    pm_cli.main(pm)
    out = capsys.readouterr().out
    assert "THROTTLED (numbers 139m old, next try in 59m)" in out
    assert "balancing on numbers is paused" in out and "StopFailure" in out
    assert pm.telemetry_summary()[A]["numbersAgeMinutes"] == 139


def test_stale_numbers_hold_says_so_and_a_stopfailure_report_still_fails_over(world):
    world.add_account(A, five_hour=40.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    pm.fetch_all_usage(force_refresh=True)
    world.set_usage(A, usage_mode="429", retry_after="3600", readout=False)  # no probe readout either
    pm.fetch_all_usage(force_refresh=True)
    _age_numbers(world.accounts[A]["id"], 139 * 60)
    _age_usage_cache()

    res = pm.balance_accounts()
    assert res["reason"] == "telemetry_unavailable" and res["action"] == "none"
    assert "139m old" in res["telemetryNote"] and "StopFailure" in res["telemetryNote"]
    assert world.events("balance.decision")[-1]["telemetryNote"] == res["telemetryNote"]

    world.set_usage(A, exhausted=True)  # the account really is limited: the probe will say so
    pm.update_state(lambda s: s.__setitem__("pendingSignals", [{"type": "rate_limit", "at": time.time()}]))
    _age_usage_cache()
    res = pm.balance_accounts(source="auto_failover", automatic=True)
    assert res["action"] == "switched" and res["reason"] == "confirmed_rate_limited"
    assert "StopFailure" in res["telemetryNote"]
    assert world.store_email() == B


def test_fresh_numbers_carry_no_stale_note(world):
    world.add_account(A, five_hour=40.0)
    world.add_account(B)
    world.activate(A)
    res = pm.balance_accounts()
    assert res["reason"] == "within_budget" and "telemetryNote" not in res


# -- dead grants ----------------------------------------------------------------------------------

def test_a_dead_grant_is_spent_once_then_skipped_until_new_tokens_arrive(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    world.make_orca_copy_stale(B)
    rows = {r["email"]: r for r in pm.fetch_all_usage(force_refresh=True)}
    assert rows[B]["telemetry"] == "needs_login" and rows[B]["needsLogin"]
    assert len(_refresh_calls(world, B)) == 1
    for _ in range(5):  # five evaluations later (the live log: one refresh.failed every ~5 minutes)
        _age_usage_cache()
        pm.update_state(lambda s: s.__setitem__("lastEvalAt", 0))
        pm.run_auto(reason="prompt-submit")
    assert len(_refresh_calls(world, B)) == 1, "a dead grant was spent again"
    assert len(world.events("refresh.failed")) == 1
    assert [a for a in pm.list_accounts() if a["email"] == B][0]["needsLogin"]

    world.set_orca_creds(B, {"claudeAiOauth": fake_anthropic.mint(B)})  # a login wrote new tokens
    _age_usage_cache()
    rows = {r["email"]: r for r in pm.fetch_all_usage(force_refresh=True)}
    assert rows[B]["telemetry"] == "ok" and not rows[B]["needsLogin"]
    assert world.accounts[B]["id"] not in pm.load_state()["health"]


def test_a_legacy_needs_login_mark_gets_one_more_refresh_which_records_the_grant(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    world.make_orca_copy_stale(B)
    b = world.accounts[B]["id"]
    pm.update_state(lambda s: s["health"].__setitem__(b, {"needsLogin": True, "reason": "invalid_grant", "since": 1}))
    pm.fetch_all_usage(force_refresh=True)
    assert len(_refresh_calls(world, B)) == 1 and pm.load_state()["health"][b]["deadGrant"]
    _age_usage_cache()
    pm.fetch_all_usage(force_refresh=True)
    assert len(_refresh_calls(world, B)) == 1


def test_a_switch_to_a_dead_grant_is_refused_without_spending_it_again(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    world.make_orca_copy_stale(B)
    pm.fetch_all_usage(force_refresh=True)
    with pytest.raises(pm.SwitchRefused, match="invalid_grant"):
        pm.switch_account(B)
    assert len(_refresh_calls(world, B)) == 1


# -- pending StopFailure reports ------------------------------------------------------------------

def test_pending_signals_past_their_ttl_are_expired_on_every_evaluation(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    now = time.time()
    fresh = {"type": "rate_limit", "at": now - 10, "sessionId": "fresh"}
    pm.update_state(lambda s: s.update(
        holdUntil=now + 600,  # even an evaluation that stops at the hold expires them
        pendingSignals=[{"type": "rate_limit", "at": now - 3 * 86400, "sessionId": "old"},
                        {"type": "rate_limit", "at": now - pm.SIGNAL_TTL_SECONDS - 1, "sessionId": "just-old"},
                        fresh]))
    assert pm.balance_accounts()["reason"] == "hold"
    assert pm.load_state()["pendingSignals"] == [fresh]
