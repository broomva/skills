"""Unit and behaviour tests for provider-manager, in the fake world (tests/fakeworld).

The kill paths themselves are in test_kill_paths.py; this file checks the mechanisms one at a time,
with the reason each refusal or decision gives.
"""

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import fake_anthropic
import keychain_db
import pytest

from conftest import IMPL_DIR, pm

pytestmark = pytest.mark.new_only
pm_state = pytest.importorskip("pm_state", reason="modules introduced by BRO-2713")
pm_store = pytest.importorskip("pm_store", reason="modules introduced by BRO-2713")

A = "a@example.com"
B = "b@example.com"
C = "c@example.com"


def _switch(target, **kw):
    """switch_account, with a refusal returned as a value (so a test asserts on it, not crashes)."""
    try:
        return pm.switch_account(target, **kw)
    except pm.SwitchRefused as e:
        return {"success": False, "refused": str(e)}


def _decisions(world):
    return world.events("balance.decision")


def _refusals(world):
    return world.events("switch.refused")


# -- store naming (what Claude Code 2.1.280 reads) ------------------------------------------------

def test_store_item_names_follow_claude_code(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", "/Users/broomva")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_SECURESTORAGE_CONFIG_DIR", raising=False)
    assert pm_store.store_item_names() == ("Claude Code-credentials", ["Claude Code-credentials-d098dafb"])

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/Users/broomva/.claude")
    assert pm_store.store_item_names() == ("Claude Code-credentials-d098dafb", ["Claude Code-credentials"])

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    primary, mirrors = pm_store.store_item_names()
    assert primary == pm_store.scoped_item_name(tmp_path) and mirrors == []

    monkeypatch.setenv("CLAUDE_SECURESTORAGE_CONFIG_DIR", "")
    assert pm_store.store_item_names()[0] == "Claude Code-credentials"


def test_keychain_write_keeps_secrets_off_argv_up_to_the_security_stdin_limit():
    secret = "oat01-fake-" + "x" * 900  # well over the old 800-byte limit, under 4032 chars of command
    data = {"claudeAiOauth": {"accessToken": secret}, "mcpOAuth": {"linear": {"accessToken": "y" * 400}}}
    with patch.object(pm_store, "run_cmd", return_value=MagicMock(returncode=0)) as run:
        assert pm_store.keychain_write("Svc", "acct", data) is True
    argv, kw = run.call_args
    assert argv[0] == ["security", "-i"]
    assert all(secret not in a for a in argv[0])
    assert secret.encode().hex() in kw["input_str"] and secret not in kw["input_str"]


def test_keychain_read_distinguishes_absent_from_unreadable(world):
    assert pm_store.keychain_read("nope", "tester").status == "absent"
    world.faults(read_error=["Claude Code-credentials"])
    r = pm_store.keychain_read("Claude Code-credentials", "tester")
    assert r.status == "error" and r.data is None


def test_claude_refresh_lock_uses_claude_codes_two_directories(world):
    new = world.config_dir / ".oauth_refresh.lock"
    legacy = Path(os.path.realpath(str(world.config_dir)) + ".lock")
    with pm_store.claude_refresh_lock(world.config_dir, wait_seconds=0.2):
        assert new.is_dir() and legacy.is_dir()
        with pytest.raises(pm_store.LockBusy):
            with pm_store.claude_refresh_lock(world.config_dir, wait_seconds=0.2):
                pass
    assert not new.exists() and not legacy.exists()


# -- accounts -------------------------------------------------------------------------------------

def test_list_accounts_marks_the_store_account_active(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(B)
    accs = {a["email"]: a for a in pm.list_accounts()}
    assert accs[B]["isActive"] and accs[B]["activeSource"] == "orca_copy_match"
    assert not accs[A]["isActive"]
    assert accs[A]["hasStoredCredentials"] and accs[A]["isTokenFresh"]


# -- switch ---------------------------------------------------------------------------------------

def test_switch_writes_the_primary_item_only_and_records_the_switch(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    mirror_before = world.store_raw(world.mirror)
    res = pm.switch_account(B)
    assert res["success"] and res["switchedTo"] == B
    assert world.store()["claudeAiOauth"]["refreshToken"] == world.orca_creds(B)["claudeAiOauth"]["refreshToken"]
    assert world.store_raw(world.mirror) == mirror_before, "one chain must never sit in two refreshable items"
    assert json.loads(world.paths["CLAUDE_CONFIG_PATH"].read_text())["oauthAccount"]["emailAddress"] == B
    assert world.orca_active_email() == B
    ev = world.switches()[-1]
    assert ev["toAccount"] == B and ev["fromAccount"] == A and ev["trace_id"] and ev["run_id"]


def test_switch_unknown_account_and_missing_credentials(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    with pytest.raises(ValueError, match="not found in managed accounts roster"):
        pm.switch_account("nobody@example.com")
    keychain_db.update_json(world.db, pm_store.ORCA_SERVICE, world.accounts[B]["id"], lambda cur: {})
    with pytest.raises(RuntimeError, match="No credentials stored in Keychain"):
        pm.switch_account(B)


def test_switch_refuses_a_stale_target_with_the_reason_and_marks_it_needs_login(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    world.make_orca_copy_stale(B)
    with pytest.raises(pm.SwitchRefused, match="could not be refreshed"):
        pm.switch_account(B)
    assert _refusals(world)[-1]["target"] == B
    assert pm.load_state()["health"][world.accounts[B]["id"]]["needsLogin"] is True
    assert [a for a in pm.list_accounts() if a["email"] == B][0]["needsLogin"]


def test_switch_refreshes_a_near_expiry_target_through_its_own_copy_first(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    creds = world.orca_creds(B)
    old_rt = creds["claudeAiOauth"]["refreshToken"]
    creds["claudeAiOauth"]["expiresAt"] = fake_anthropic.now_ms() + 120_000  # under the 10-minute margin
    world.set_orca_creds(B, creds)
    pm.switch_account(B)
    new_rt = world.orca_creds(B)["claudeAiOauth"]["refreshToken"]
    assert new_rt != old_rt and fake_anthropic.refresh_state(old_rt) == "consumed"
    assert world.store()["claudeAiOauth"]["refreshToken"] == new_rt


def test_switch_writes_back_the_outgoing_chain_identified_by_profile(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    s = world.session()
    world.expire_store_access()
    s.run(1)  # Claude Code rotates A in the store; A's Orca copy now lags
    live = world.store()["claudeAiOauth"]
    assert live["refreshToken"] != world.orca_creds(A)["claudeAiOauth"]["refreshToken"]
    res = pm.switch_account(B)
    assert res["wroteBack"] is True
    assert world.orca_creds(A)["claudeAiOauth"]["refreshToken"] == live["refreshToken"]
    assert world.switches()[-1]["outgoingIdentity"] == "profile"


def test_switch_refuses_an_unidentifiable_store_credential_unless_forced(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    stranger = fake_anthropic.mint(A)  # a chain no Orca copy knows...
    stranger["expiresAt"] = fake_anthropic.now_ms() - 1000  # ...whose access token cannot be checked
    keychain_db.update_json(world.db, world.primary, "tester", lambda cur: dict(cur, claudeAiOauth=stranger))
    before = world.store_raw()
    with pytest.raises(pm.SwitchRefused, match="cannot be identified"):
        pm.switch_account(B)
    assert world.store_raw() == before
    assert pm.switch_account(B, force=True)["success"]
    assert world.store_email() == B


def test_switch_refuses_a_target_copy_holding_another_accounts_tokens(world):
    world.add_account(A)
    world.add_account(B)
    world.add_account(C)
    world.activate(A)
    world.set_orca_creds(B, world.orca_creds(C))  # B's slot holds C's grant
    with pytest.raises(pm.SwitchRefused, match="different account"):
        pm.switch_account(B)


def test_switch_to_the_account_already_in_the_store_is_a_noop(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    before = world.store_raw()
    assert pm.switch_account(A)["alreadyActive"] is True
    assert world.store_raw() == before and world.switches() == []


def test_switch_waits_for_a_claude_code_refresh_to_finish(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    lock = world.config_dir / ".oauth_refresh.lock"
    os.mkdir(lock)
    monkeypatch.setattr(pm, "CLAUDE_LOCK_WAIT_SECONDS", 3.0)
    import threading
    threading.Timer(0.5, lambda: os.rmdir(lock)).start()
    assert pm.switch_account(B)["success"]


def test_switch_refusals_name_the_reason(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    monkeypatch.setattr(pm, "CLAUDE_LOCK_WAIT_SECONDS", 0.2)
    os.mkdir(world.config_dir / ".oauth_refresh.lock")
    with pytest.raises(pm.SwitchRefused, match="refreshing its token"):
        pm.switch_account(B)
    os.rmdir(world.config_dir / ".oauth_refresh.lock")
    world.faults(read_error=[world.primary])
    with pytest.raises(pm.SwitchRefused, match="could not be read"):
        pm.switch_account(B)


def test_switch_refuses_when_the_store_changes_mid_switch_then_retries_cleanly(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    s = world.session()
    real_validate = pm._validate_target

    def validate_while_a_session_refreshes(*a, **kw):
        world.expire_store_access()
        s.run(1)  # Claude Code rotates A's chain after the switch took its snapshot
        return real_validate(*a, **kw)

    monkeypatch.setattr(pm, "_validate_target", validate_while_a_session_refreshes)
    with pytest.raises(pm.SwitchRefused, match="store changed"):
        pm.switch_account(B)
    live = world.store()["claudeAiOauth"]["refreshToken"]
    monkeypatch.setattr(pm, "_validate_target", real_validate)
    assert pm.switch_account(B)["wroteBack"] is True
    assert world.orca_creds(A)["claudeAiOauth"]["refreshToken"] == live
    assert s.run(1) == ["ok"] and s.served[-1] == B


def test_switch_primary_write_failure_leaves_the_store_unchanged(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    before = world.store_raw()
    world.faults(write_error=[world.primary])
    with pytest.raises(pm_store.StoreError):
        pm.switch_account(B)
    world.faults()
    assert world.store_raw() == before


# -- refresh interlock ----------------------------------------------------------------------------

def test_refresh_never_spends_a_refresh_token_that_a_store_item_holds(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    rt = world.orca_creds(A)["claudeAiOauth"]["refreshToken"]
    assert pm.refresh_account_token(world.accounts[A]["id"]) is None  # A is the store's account
    b_oauth = world.orca_creds(B)["claudeAiOauth"]
    b_rt = b_oauth["refreshToken"]
    keychain_db.update_json(world.db, world.mirror, "tester",  # the mirror holds B's chain...
                            lambda c: dict(c, claudeAiOauth=b_oauth))
    world.claude_process_reading_the_mirror()  # ...and a running session reads the mirror
    assert pm.refresh_account_token(world.accounts[B]["id"]) is None
    assert fake_anthropic.refresh_state(rt) == "valid" and fake_anthropic.refresh_state(b_rt) == "valid"
    assert {e["reason"] for e in world.events("refresh.refused")} == {
        "store_account", "refresh_token_in_mirror_with_a_reader"}


def test_a_stale_mirror_nobody_reads_does_not_block_switching_back(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)  # like old provider-manager: A's chain in the primary, the mirror and A's copy
    assert _switch(B)["success"]
    res = _switch(A)
    assert res["success"], res
    assert world.store_email() == A


def test_override_detection_reads_real_environment_tokens_only(world):
    cfg = world.config_dir
    world.ps_output.write_text(
        "/usr/bin/grep CLAUDE_CONFIG_DIR=%s PATH=/bin\n" % cfg                   # a scan, not Claude Code
        + "/Users/x/.local/share/claude/versions/2.1.280 HOME=/Users/x PATH=/bin\n"
        + "/Users/x/.local/bin/claude -p hi PATH=/bin CLAUDE_CONFIG_DIR=/elsewhere/.claude\n")  # another dir
    assert pm_store.config_dir_override_running(cfg) is False
    world.ps_output.write_text("/Applications/Some App.app/Contents/claude/versions/2.1.280 --x "
                               "PATH=/bin CLAUDE_CONFIG_DIR=%s\n" % cfg)  # a space in argv0
    assert pm_store.config_dir_override_running(cfg) is True
    world.claude_process_reading_the_mirror()
    assert pm_store.config_dir_override_running(cfg) is True


def test_refresh_persists_the_rotated_pair_to_the_copy(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    old = world.orca_creds(B)["claudeAiOauth"]["refreshToken"]
    new = pm.refresh_account_token(world.accounts[B]["id"])
    assert new and new["refreshToken"] != old
    assert world.orca_creds(B)["claudeAiOauth"]["refreshToken"] == new["refreshToken"]
    assert fake_anthropic.refresh_state(old) == "consumed"


# -- telemetry ------------------------------------------------------------------------------------

def test_numbers_entry_limits_and_locks():
    e = pm._numbers_entry("x", {"five_hour": {"utilization": 20}, "seven_day": {"utilization": 85, "locked_reason": "weekly"}}, 1.0)
    assert e["isRateLimited"] and e["lockedReason"] == "weekly"
    e = pm._numbers_entry("x", {"five_hour": {"utilization": 50}, "limits": [{"is_active": True, "percent": 100, "group": "q"}]}, 1.0)
    assert e["isRateLimited"] and e["lockedReason"] == "q_limit_reached"
    e = pm._numbers_entry("x", {"five_hour": {"utilization": 20}, "limits": [{"is_active": True, "percent": None}]}, 1.0)
    assert not e["isRateLimited"] and e["status"] == "ok"
    assert pm._numbers_entry("x", {"five_hour": {"utilization": 96}}, 1.0)["status"] == "critical"


def test_usage_reads_the_store_account_with_the_store_token_and_never_refreshes_it(world):
    world.add_account(A, five_hour=33.0)
    world.add_account(B)
    world.activate(A)
    rows = {r["email"]: r for r in pm.fetch_all_usage(force_refresh=True)}
    assert rows[A]["telemetry"] == "ok" and rows[A]["fiveHourUtil"] == 33.0
    fake_anthropic.expire_access(world.store()["claudeAiOauth"]["accessToken"])
    keychain_db.update_json(world.db, world.primary, "tester",
                            lambda c: dict(c, claudeAiOauth=dict(c["claudeAiOauth"], expiresAt=fake_anthropic.now_ms() - 1)))
    rows = {r["email"]: r for r in pm.fetch_all_usage(force_refresh=True)}
    assert rows[A]["telemetry"] == "auth_expired" and rows[A]["isRateLimited"] is False
    assert [c for c in fake_anthropic.calls("refresh") if c["email"] == A] == []


def test_usage_429_backs_off_and_keeps_stale_numbers_without_claiming_a_limit(world):
    world.add_account(A, five_hour=40.0)
    world.add_account(B)
    world.activate(A)
    pm.fetch_all_usage(force_refresh=True)
    world.set_usage(A, usage_mode="429")
    rows = {r["email"]: r for r in pm.fetch_all_usage(force_refresh=True)}
    assert rows[A]["telemetry"] == "throttled" and rows[A]["stale"] and rows[A]["fiveHourUtil"] == 40.0
    assert rows[A]["isRateLimited"] is False
    n = len([c for c in fake_anthropic.calls("usage") if c["email"] == A])
    pm.fetch_all_usage(force_refresh=True)
    assert len([c for c in fake_anthropic.calls("usage") if c["email"] == A]) == n, "inside the backoff: no call"
    assert world.events("telemetry.throttled")


def test_usage_cache_roundtrip_and_ttl(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    pm.fetch_all_usage(force_refresh=True)
    n = len(fake_anthropic.calls("usage"))
    pm.fetch_all_usage()
    assert len(fake_anthropic.calls("usage")) == n


# -- the balancer ---------------------------------------------------------------------------------

def test_balance_within_budget_and_dry_run(world):
    world.add_account(A, five_hour=25.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    assert pm.balance_accounts(threshold=85.0)["reason"] == "within_budget"
    world.set_usage(A, five_hour=92.0)
    world.set_usage(B, five_hour=15.0)
    os.unlink(pm.USAGE_CACHE_PATH)
    dry = pm.balance_accounts(threshold=85.0, dry_run=True)
    assert dry["action"] == "would_switch" and dry["toAccount"] == B and world.switches() == []
    real = pm.balance_accounts(threshold=85.0)
    assert real["action"] == "switched" and real["reason"] == "active_exceeded_threshold"
    assert world.switches()[-1]["source"] == "proactive_balance"


def test_balance_hysteresis_needs_a_clearly_healthier_standby(world):
    world.add_account(A, five_hour=91.0)
    world.add_account(B, five_hour=69.0)  # under standbyMax (70) but not 25 points under A
    world.activate(A)
    assert pm.balance_accounts()["reason"] == "no_healthy_standby"


def test_balance_never_picks_a_standby_whose_usage_is_unreadable(world):
    world.add_account(A, five_hour=95.0)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    world.set_usage(B, usage_mode="500")  # live credentials, unreadable telemetry
    assert pm.balance_accounts()["reason"] == "no_healthy_standby"
    assert world.switches() == []


def test_balance_ignores_a_weekly_exhausted_standby(world):
    world.add_account(A, five_hour=91.0, seven_day=80.0)
    world.add_account(B, five_hour=0.0, seven_day=100.0)
    world.activate(A)
    assert pm.balance_accounts(threshold=85.0)["reason"] == "no_healthy_standby"


def test_balance_fails_over_when_the_probe_confirms_the_limit(world):
    world.add_account(A, five_hour=100.0)
    world.add_account(B, five_hour=20.0)
    world.activate(A)
    world.set_usage(A, exhausted=True)
    res = pm.balance_accounts()
    assert res["action"] == "switched" and res["reason"] == "confirmed_rate_limited" and res["probe"] == "limited"
    assert world.events("probe")[-1]["result"] == "limited"


def test_balance_does_not_act_on_an_inconclusive_probe(world, monkeypatch):
    world.add_account(A, five_hour=100.0)
    world.add_account(B, five_hour=20.0)
    world.activate(A)
    monkeypatch.setattr(pm, "probe_active_account", lambda: ("unknown", "probe rc 1"))
    assert pm.balance_accounts()["reason"] == "probe_inconclusive"
    assert world.switches() == []


def test_hold_blocks_automatic_switching(world):
    world.add_account(A, five_hour=95.0)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    pm.update_state(lambda s: s.__setitem__("holdUntil", time.time() + 600))
    assert pm.balance_accounts()["reason"] == "hold"
    assert world.switches() == []


def test_observe_only_mode_logs_would_switch_for_automatic_evaluations(world):
    world.add_account(A, five_hour=95.0)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    pm.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    pm.CONFIG_PATH.write_text(json.dumps({"autoBalance": False}))
    res = pm.run_auto()
    assert res["action"] == "would_switch" and res["observeOnly"] and world.switches() == []


def test_run_auto_evaluates_at_most_once_per_interval_unless_a_limit_is_reported(world):
    world.add_account(A, five_hour=30.0)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    assert pm.run_auto()["reason"] == "within_budget"
    assert pm.run_auto()["reason"] == "recent_evaluation"
    assert pm.run_auto(signal="rate_limit")["reason"] != "recent_evaluation"


def test_rotate_requires_a_confirmed_limit_and_force_overrides_it(world):
    world.add_account(A, five_hour=40.0)
    world.add_account(B, five_hour=80.0)
    world.add_account(C, five_hour=10.0)
    world.activate(A)
    res = pm.rotate_account(reason="rate_limit_429")
    assert res["success"] is False and res["reason"] == "probe_ok_not_limited"
    dry = pm.rotate_account(reason="rate_limit_429", dry_run=True, force=True)
    assert dry["dryRun"] and dry["nextAccount"] == C
    res = pm.rotate_account(reason="rate_limit_429", force=True)
    assert res["success"] and res["rotatedTo"] == C
    assert world.switches()[-1]["source"] == "rate_limit_failover"


def test_rotate_with_one_account_or_only_exhausted_standbys_fails(world):
    world.add_account(A, five_hour=99.0, seven_day=90.0)
    world.activate(A)
    assert pm.rotate_account()["success"] is False
    world.add_account(B, five_hour=0.0, seven_day=100.0)
    assert pm.rotate_account(force=True)["reason"] == "no_available_standby"


# -- probe ----------------------------------------------------------------------------------------

def test_probe_env_strips_session_and_auth_overrides(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://x")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/keep/me")
    env = pm._probe_env()
    assert "CLAUDECODE" not in env and "CLAUDE_CODE_OAUTH_TOKEN" not in env and "ANTHROPIC_BASE_URL" not in env
    assert env["CLAUDE_CONFIG_DIR"] == "/keep/me" and env["PROVIDER_MANAGER_PROBE"] == "1"


# -- hooks ----------------------------------------------------------------------------------------

def test_hook_writes_nothing_to_stdout(world, pmh, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    pm.fetch_all_usage(force_refresh=True)
    monkeypatch.setenv("PROVIDER_MANAGER_INLINE", "1")
    out, err = io.StringIO(), io.StringIO()
    with patch("sys.stdout", out), patch("sys.stderr", err):
        pmh.handle_session_start({})
        pmh.handle_prompt_submit({})
        pmh.handle_post_tool_use({"error": "rate_limit_error 429"})
        pmh.handle_stop_failure({"session_id": "s1", "error": "authentication_failed"})
    assert out.getvalue() == ""
    assert "Active: %s" % A in err.getvalue()


def test_stop_failure_rate_limit_records_the_session_and_fails_over_and_the_session_continues(world, pmh, monkeypatch):
    world.add_account(A, five_hour=100.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    world.set_usage(A, exhausted=True)
    s = world.session()
    assert s.request() == "rate_limit"  # the turn ends: StopFailure(rate_limit)
    monkeypatch.setenv("PROVIDER_MANAGER_INLINE", "1")
    monkeypatch.setenv("PASEO_AGENT_ID", "agent-123")
    pmh.handle_stop_failure({"hook_event_name": "StopFailure", "session_id": "S1", "cwd": "/w",
                             "transcript_path": "/t.jsonl", "error": "rate_limit"})
    assert world.store_email() == B
    assert s.request() == "ok" and s.served[-1] == B  # resumed in place on the new account
    stalled = pm_state.list_stalled(pm.STALLED_PATH, 0)
    assert stalled[-1]["sessionId"] == "S1" and stalled[-1]["paseoAgentId"] == "agent-123"
    assert world.switches()[-1]["source"] == "auto_failover"


def test_hook_kick_spawns_a_detached_evaluation_and_returns_at_once(world):
    world.add_account(A, five_hour=30.0)
    world.add_account(B)
    world.activate(A)
    t0 = time.time()
    res = subprocess.run([sys.executable, str(IMPL_DIR / "provider_manager_hook.py"), "prompt-submit"],
                         input="{}", text=True, capture_output=True, env=world.env(), timeout=30)
    assert res.returncode == 0 and res.stdout == ""
    assert time.time() - t0 < 5.0
    deadline = time.time() + 20
    while time.time() < deadline and not _decisions(world):
        time.sleep(0.2)
    assert _decisions(world) and _decisions(world)[-1]["reason"] == "within_budget"


def test_probe_process_never_runs_the_hook(world, pmh, monkeypatch):
    monkeypatch.setenv("PROVIDER_MANAGER_PROBE", "1")
    monkeypatch.setattr(sys, "argv", ["hook", "prompt-submit"])
    with patch.object(pmh, "kick") as k:
        pmh.main()
    k.assert_not_called()


# -- login ----------------------------------------------------------------------------------------

def _login_world(world, monkeypatch, email):
    shim = world.bin / "node"
    shim.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, Path(__file__).parent / "fakeworld/fake_node.py"))
    shim.chmod(0o755)
    monkeypatch.setenv("FAKE_BROWSER_EMAIL", email)
    monkeypatch.setenv("FAKE_BROWSER_ORG", world.accounts[email]["org"])


def test_login_headless_for_a_standby_never_touches_the_store(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    world.make_orca_copy_stale(B)
    _login_world(world, monkeypatch, B)
    before = world.store_raw()
    res = pm.login_headless(email=B)
    assert res["success"] and res["storeAccount"] is False and res["switched"] is False
    assert world.store_raw() == before
    assert fake_anthropic.refresh_state(world.orca_creds(B)["claudeAiOauth"]["refreshToken"]) == "valid"
    with keychain_db.db(world.db) as d:
        leftovers = [k for k in d["items"] if "Claude Code-credentials-" in k and world.mirror not in k]
    assert leftovers == [], "the isolated login item must be deleted"


def test_login_headless_for_the_store_account_renews_the_live_store(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    _login_world(world, monkeypatch, A)
    res = pm.login_headless(email=A)
    assert res["storeAccount"] is True
    live = world.store()["claudeAiOauth"]["refreshToken"]
    assert world.orca_creds(A)["claudeAiOauth"]["refreshToken"] == live
    assert world.store(world.mirror)["claudeAiOauth"]["refreshToken"] != live, "the mirror is never written"


# -- events ---------------------------------------------------------------------------------------

def test_events_log_and_history(world):
    pm.log_provider_event("switch", {"fromAccount": A, "toAccount": B, "source": "proactive_balance"})
    pm.log_provider_event("balance.decision", {"action": "none", "reason": "within_budget"})
    assert [e["event"] for e in pm.read_provider_events()] == ["switch", "balance.decision"]
    assert [e["event"] for e in pm.read_provider_events(kinds=["switch"])] == ["switch"]
    e = pm.read_provider_events()[0]
    assert e["run_id"] == pm_state.RUN_ID and e["session_id"] == "sess-under-test"


def test_balancer_lock_is_exclusive_across_processes_and_reentrant_within_one(tmp_path):
    lock = tmp_path / "b.lock"
    code = ("import sys,time;sys.path.insert(0,%r);import pm_state\n"
            "with pm_state.balancer_lock(%r) as h:\n print('held' if h else 'busy',flush=True);time.sleep(2)\n"
            % (str(IMPL_DIR), str(lock)))
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    with pm_state.balancer_lock(lock) as h:
        assert h is False
    p.wait()
    with pm_state.balancer_lock(lock) as h1:
        with pm_state.balancer_lock(lock) as h2:
            assert h1 and h2


def test_cli_json_flag_works_before_or_after_the_subcommand(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    for argv in (["--json", "list"], ["list", "--json"]):
        r = subprocess.run([sys.executable, str(IMPL_DIR / "provider_manager.py")] + argv,
                           capture_output=True, text=True, env=world.env(), timeout=60)
        assert r.returncode == 0 and isinstance(json.loads(r.stdout), list), argv


def test_keychain_write_over_the_stdin_limit_goes_through_argv_as_hex_like_claude_code():
    secret = "oat01-fake-" + "x" * 3000
    with patch.object(pm_store, "run_cmd", return_value=MagicMock(returncode=0)) as run:
        assert pm_store.keychain_write("Svc", "acct", {"claudeAiOauth": {"accessToken": secret}})
    argv = run.call_args[0][0]
    assert argv[:2] == ["security", "add-generic-password"] and all(secret not in a for a in argv)


# -- round-2 findings (P20 round 1, CodeRabbit) ---------------------------------------------------

def test_refresh_never_runs_while_another_provider_manager_action_holds_the_lock(world):
    """B1: `usage` runs beside a switch. It must not spend a refresh token on a stale snapshot."""
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    creds = world.orca_creds(B)
    creds["claudeAiOauth"]["expiresAt"] = fake_anthropic.now_ms() + 10_000  # B's copy needs a refresh
    world.set_orca_creds(B, creds)
    rt = creds["claudeAiOauth"]["refreshToken"]
    release = world.tmp / "release"
    code = ("import os,sys,time;sys.path.insert(0,%r);import pm_state\n"
            "with pm_state.balancer_lock(%r):\n print('held',flush=True)\n"
            " while not os.path.exists(%r): time.sleep(0.05)\n"
            % (str(IMPL_DIR), str(pm.BALANCER_LOCK_PATH), str(release)))
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True, env=world.env())
    assert p.stdout.readline().strip() == "held"
    try:
        rows = {r["email"]: r for r in pm.fetch_all_usage(force_refresh=True)}
    finally:
        release.write_text("1")  # held until here, however slow the runner
        p.wait(timeout=30)
    assert fake_anthropic.refresh_state(rt) == "valid", "no refresh while another action holds the lock"
    assert rows[B]["telemetry"] == "auth_expired"
    assert world.events("refresh.deferred")


def test_refresh_rereads_the_store_so_a_switch_that_just_happened_is_seen(world):
    """B1, the exact shape: a snapshot says B is a standby; a switch then puts B in the store."""
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    stale_ctx = pm.build_context()
    assert stale_ctx["storeAccountId"] == world.accounts[A]["id"]
    pm.switch_account(B)
    in_store = world.store()["claudeAiOauth"]["refreshToken"]
    assert pm.refresh_account_token(world.accounts[B]["id"]) is None
    assert fake_anthropic.refresh_state(in_store) == "valid"


def test_invalid_grant_after_another_writer_refreshed_the_copy_is_not_needs_login(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    b = world.orca_creds(B)
    real_http = pm._http

    def racing_http(url, **kw):
        if url == pm.TOKEN_ENDPOINT_URL:  # someone else refreshes B's copy first
            fresh = fake_anthropic.mint(B)
            world.set_orca_creds(B, {"claudeAiOauth": fresh})
            fake_anthropic.consume(b["claudeAiOauth"]["refreshToken"])
        return real_http(url, **kw)

    monkeypatch.setattr(pm, "_http", racing_http)
    assert pm.refresh_account_token(world.accounts[B]["id"]) is None
    assert world.accounts[B]["id"] not in pm.load_state().get("health", {})


def test_a_stale_claude_refresh_lock_is_reclaimed(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    lock = world.config_dir / ".oauth_refresh.lock"
    os.mkdir(lock)
    old = time.time() - 120
    os.utime(lock, (old, old))
    res = _switch(B)
    assert res["success"], res
    assert not lock.exists()


def test_identity_needs_email_and_org_to_agree():
    roster = [{"id": "y", "email": "y@team.com", "organizationUuid": "org-team"},
              {"id": "z", "email": "z@solo.com", "organizationUuid": "org-solo"}]
    assert pm._match_roster({"account": {"email": "y@team.com"}, "organization": {"uuid": "org-team"}}, roster)["id"] == "y"
    assert pm._match_roster({"account": {"email": "n@team.com"}, "organization": {"uuid": "org-team"}}, roster) is None
    assert pm._match_roster({"account": {"email": "y@team.com"}, "organization": {"uuid": "org-other"}}, roster) is None
    assert pm._match_roster({"organization": {"uuid": "org-solo"}}, roster)["id"] == "z"


def test_a_same_org_stranger_in_the_store_is_not_written_back_as_a_roster_account(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    org_a = world.accounts[A]["org"]
    fake_anthropic.add_account("n@example.com", "uuid-n", org_a)  # a teammate, same org, not in the roster
    keychain_db.update_json(world.db, world.primary, "tester",
                            lambda c: dict(c, claudeAiOauth=fake_anthropic.mint("n@example.com")))
    a_copy = world.orca_creds(A)
    with pytest.raises(pm.SwitchRefused, match="cannot be identified"):
        pm.switch_account(B)
    assert world.orca_creds(A) == a_copy


def test_a_write_that_cannot_be_read_back_records_the_switch_as_unverified(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    real = pm.write_store_oauth

    def lands_wrong(item, oauth, account=None, timeout=30.0, **kw):  # rc 0, but the item ends up different
        real(item, dict(oauth, refreshToken="garbage"), account, timeout, **kw)

    monkeypatch.setattr(pm, "write_store_oauth", lands_wrong)
    with pytest.raises(pm_store.StoreError, match="did not read back"):
        pm.switch_account(B)
    assert pm.load_state()["lastSwitch"]["unverified"] is True
    assert world.events("switch.unverified")


def test_an_orca_write_that_silently_does_not_land_is_reported(world, monkeypatch):
    world.add_account(A)
    monkeypatch.setattr(pm_store, "keychain_write", lambda *a, **k: True)  # rc 0, nothing written
    assert pm_store.write_orca_oauth(world.accounts[A]["id"], {"accessToken": "x", "refreshToken": "new"}) is False


def test_a_reported_limit_survives_a_cooldown_and_a_dry_run(world):
    world.add_account(A, five_hour=100.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    world.set_usage(A, exhausted=True)
    pm.update_state(lambda s: s.update(pendingSignals=[{"type": "rate_limit", "at": time.time()}],
                                       lastSwitch={"at": time.time(), "from": None, "to": None}))
    assert pm.balance_accounts()["reason"] == "cooldown"
    assert pm.load_state()["pendingSignals"], "a cooldown must not swallow the report"
    pm.update_state(lambda s: s.__setitem__("lastSwitch", None))
    assert pm.balance_accounts(dry_run=True)["action"] == "would_switch"
    assert pm.load_state()["pendingSignals"], "a dry run must not swallow the report"
    assert pm.balance_accounts()["action"] == "switched"
    assert pm.load_state()["pendingSignals"] == []


def test_an_empty_store_is_never_filled_by_an_automatic_evaluation(world):
    world.add_account(A)
    world.add_account(B)
    assert pm.run_auto()["reason"] == "no_active_account"
    assert world.switches() == []


def test_an_unmeasured_claude_code_version_makes_automatic_switching_observe_only(world, monkeypatch):
    world.add_account(A, five_hour=95.0)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    monkeypatch.setenv("FAKE_CLAUDE_VERSION", "2.2.0")
    res = pm.run_auto()
    assert res["action"] == "would_switch" and res["reason"] == "version_unverified"
    assert res["claudeVersion"] == "2.2.0" and world.switches() == []
    assert pm.balance_accounts()["action"] == "switched", "an operator's balance is not gated"


def test_probe_classification_reads_the_result_text_not_incidental_numbers(world, monkeypatch):
    outputs = {
        "ok": (0, json.dumps({"type": "result", "is_error": False, "result": "OK", "duration_ms": 429}), ""),
        "unknown": (1, json.dumps({"type": "result", "is_error": True, "duration_ms": 429,
                                   "result": "Failed to refresh OAuth token: another Claude Code process is refreshing it"}), ""),
        # the real 2.1.280 binary's output for a subscription limit (measured in tests/drill, probe scenario)
        "limited": (1, json.dumps({"type": "result", "is_error": True, "api_error_status": 429,
                                   "result": "You've hit your session limit \u00b7 resets 10:47pm (America/Bogota)"}), ""),
        "limited, text only": (1, json.dumps({"type": "result", "is_error": True,
                                              "result": "You've hit your weekly limit \u00b7 resets Oct 8"}), ""),
        "auth_dead": (1, json.dumps({"type": "result", "is_error": True, "api_error_status": None,
                                     "result": "Failed to authenticate: OAuth session expired and could not be refreshed"}), ""),
    }
    for label, (rc, out, err) in outputs.items():
        monkeypatch.setattr(pm.subprocess, "run", lambda *a, **k: MagicMock(returncode=rc, stdout=out, stderr=err))
        assert pm.probe_active_account()[0] == label.split(",")[0], label


def test_probe_uses_the_sessions_default_model_unless_configured(world, monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return MagicMock(returncode=0, stdout=json.dumps({"is_error": False, "result": "OK"}), stderr="")

    monkeypatch.setattr(pm.subprocess, "run", fake_run)
    pm.probe_active_account()
    assert "--model" not in seen["cmd"]
    pm.CONFIG_PATH.write_text(json.dumps({"probeModel": "opus"}))
    pm.probe_active_account()
    assert seen["cmd"][seen["cmd"].index("--model") + 1] == "opus"


def test_hook_under_isolated_python_exits_zero_with_no_stdout_even_when_modules_are_missing(world, tmp_path):
    hook = IMPL_DIR / "provider_manager_hook.py"
    r = subprocess.run([sys.executable, "-I", str(hook), "prompt-submit"], input="{}", text=True,
                       capture_output=True, env=dict(world.env(), PROVIDER_MANAGER_AUTO="0"), timeout=30)
    assert r.returncode == 0 and r.stdout == ""
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    (lonely / "provider_manager_hook.py").write_text(hook.read_text())  # no siblings: imports fail
    r = subprocess.run([sys.executable, "-I", str(lonely / "provider_manager_hook.py"), "stop-failure"],
                       input='{"error": "rate_limit"}', text=True, capture_output=True, timeout=30)
    assert r.returncode == 0 and r.stdout == ""


def test_claude_json_that_does_not_parse_is_never_replaced_and_its_mode_is_kept(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    cfg = world.paths["CLAUDE_CONFIG_PATH"]
    cfg.write_text('{"projects": {"truncated":')
    pm.switch_account(B)
    assert cfg.read_text() == '{"projects": {"truncated":'
    cfg.write_text(json.dumps({"projects": {"x": 1}}))
    os.chmod(cfg, 0o600)
    pm.switch_account(A)
    assert json.loads(cfg.read_text())["projects"] == {"x": 1}
    assert (os.stat(cfg).st_mode & 0o777) == 0o600


def test_events_and_stalled_logs_are_private(world, pmh, monkeypatch):
    pm.log_provider_event("x", {})
    pmh.handle_stop_failure({"session_id": "s", "error": "unknown"})
    for path in (pm.PROVIDER_EVENTS_PATH, pm.STALLED_PATH):
        assert (os.stat(path).st_mode & 0o777) == 0o600, path


# -- P20 round 2 delta ----------------------------------------------------------------------------

def test_the_unscoped_item_is_always_protected_even_when_it_is_the_mirror(world, monkeypatch):
    """Run with CLAUDE_CONFIG_DIR=~/.claude, the primary is the scoped item and the mirror is
    `Claude Code-credentials`: the item every default session reads, which no ps scan can see."""
    world.add_account(A)
    world.add_account(B)
    world.activate(A)  # both items hold A's chain, as A's copy does
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(world.config_dir))
    primary, mirrors = pm_store.store_item_names()
    assert mirrors == ["Claude Code-credentials"]
    b = world.orca_creds(B)["claudeAiOauth"]
    keychain_db.update_json(world.db, primary, "tester", lambda c: dict(c, claudeAiOauth=b))  # tool's view: B
    a_rt = world.orca_creds(A)["claudeAiOauth"]["refreshToken"]
    assert pm.refresh_account_token(world.accounts[A]["id"]) is None
    assert fake_anthropic.refresh_state(a_rt) == "valid"


def test_settle_loop_retries_until_a_switch_and_runs_once_per_machine(world, monkeypatch):
    script = [{"action": "none", "reason": "cooldown", "remainingSeconds": 3},
              {"action": "none", "reason": "switch_refused", "error": "the store changed while ...; retry"},
              {"action": "switched", "reason": "confirmed_rate_limited"}]
    calls = []

    def fake_run_auto(reason="hook", signal=None):
        res = script[len(calls)]
        calls.append(res)
        if res["action"] == "switched":
            pm.update_state(lambda s: s.__setitem__("lastSwitch", {"at": time.time()}))
        return res

    monkeypatch.setattr(pm, "run_auto", fake_run_auto)
    monkeypatch.setattr(pm.time, "sleep", lambda s: None)
    assert pm.run_auto_until_settled("stop-failure", "rate_limit")["action"] == "switched"
    assert len(calls) == 3
    calls.clear()
    script[:] = [{"action": "none", "reason": "no_healthy_standby"}]
    with pm_state.exclusive(pm.SETTLE_LOCK_PATH):  # another settle loop is running
        assert pm.run_auto_until_settled("stop-failure", "rate_limit")["reason"] == "settle_loop_running"
    assert calls == []
    assert pm.run_auto_until_settled("stop-failure", "rate_limit")["reason"] == "no_healthy_standby"
    assert len(calls) == 1, "a conclusive outcome ends the loop"


def test_login_headless_refuses_to_log_over_an_unidentifiable_live_store(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    fake_anthropic.add_account("n@other.com", "uuid-n", "org-other")
    keychain_db.update_json(world.db, world.primary, "tester",
                            lambda c: dict(c, claudeAiOauth=fake_anthropic.mint("n@other.com")))
    _login_world(world, monkeypatch, A)
    before = world.store_raw()
    with pytest.raises(pm.SwitchRefused, match="Pass --force"):
        pm.login_headless(email=A)
    assert world.store_raw() == before


def test_a_report_newer_than_the_cached_probe_gets_a_new_probe(world):
    world.add_account(A, five_hour=100.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    world.set_usage(A, exhausted=True)
    now = time.time()
    pm.update_state(lambda s: s.update(
        probes={world.accounts[A]["id"]: {"at": now - 100, "result": "ok"}},
        pendingSignals=[{"type": "rate_limit", "at": now - 10}]))
    res = pm.balance_accounts()
    assert res["action"] == "switched" and res["probe"] == "limited"


def test_an_unknown_probe_is_cached_for_seconds_not_minutes(world, monkeypatch):
    monkeypatch.setattr(pm, "probe_active_account", lambda: ("ok", "fresh"))
    pm.update_state(lambda s: s.__setitem__("probes", {"x": {"at": time.time() - 40, "result": "unknown"}}))
    assert pm.probe_cached("x", 600.0) == ("ok", "fresh")


def test_a_per_model_weekly_cap_counts_as_limited():
    e = pm._numbers_entry("x", {"five_hour": {"utilization": 10}, "seven_day": {"utilization": 40},
                                "seven_day_opus": {"utilization": 100}}, 1.0)
    assert e["isRateLimited"] and e["lockedReason"] == "seven_day_opus_limit_reached"


def test_no_failover_back_to_an_account_the_probe_confirmed_limited(world):
    world.add_account(A, five_hour=100.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    world.set_usage(A, exhausted=True)
    assert pm.balance_accounts()["action"] == "switched"  # A probed limited, now on B
    world.set_usage(B, five_hour=100.0, exhausted=True)
    world.set_usage(A, five_hour=10.0, exhausted=False)  # A's numbers look fine again (a model cap?)
    pm.update_state(lambda s: s.__setitem__("lastSwitch", {"at": time.time() - 400}))
    os.unlink(pm.USAGE_CACHE_PATH)
    assert pm.balance_accounts()["reason"] == "no_healthy_standby"


def test_a_report_arriving_during_the_probe_survives_it(world, monkeypatch):
    world.add_account(A, five_hour=100.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    pm.update_state(lambda s: s.__setitem__("pendingSignals", [{"type": "rate_limit", "at": time.time() - 5}]))

    def probe_while_a_new_report_lands(account_id, ttl, fresh_after=0.0, **kw):
        time.sleep(0.01)
        pm.update_state(lambda s: s["pendingSignals"].append({"type": "rate_limit", "at": time.time()}))
        return "ok", "probe answered"

    monkeypatch.setattr(pm, "probe_cached", probe_while_a_new_report_lands)
    assert pm.balance_accounts()["reason"] == "probe_ok_not_limited"
    assert len(pm.load_state()["pendingSignals"]) == 1


def test_a_paused_version_gate_shows_in_the_session_start_line(world, pmh, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    pm.update_state(lambda s: s.__setitem__("claudeVersion", {"path": "/x", "version": "2.2.0", "at": time.time()}))
    monkeypatch.setenv("PROVIDER_MANAGER_AUTO", "0")
    err = io.StringIO()
    with patch("sys.stderr", err), patch.object(pmh, "kick"):
        pmh.handle_session_start({})
    assert "automatic switching paused: Claude Code 2.2.0" in err.getvalue()


def test_existing_world_readable_logs_are_tightened(world):
    pm.PROVIDER_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    pm.PROVIDER_EVENTS_PATH.write_text("")
    os.chmod(pm.PROVIDER_EVENTS_PATH, 0o644)
    pm.log_provider_event("x", {})
    assert (os.stat(pm.PROVIDER_EVENTS_PATH).st_mode & 0o777) == 0o600


def test_a_store_proven_dead_is_not_written_back_over_the_copy(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    s = world.session()
    world.expire_store_access()
    s.run(1)  # the store now holds a newer link of A's chain than A's copy
    a_copy = world.orca_creds(A)
    pm.switch_account(B, store_proven_dead=True)
    assert world.orca_creds(A) == a_copy


# -- P20 delta round 1 ----------------------------------------------------------------------------

def test_a_probe_is_stamped_with_its_start_so_a_report_during_it_is_reprobed(world, monkeypatch):
    def slow_probe():
        time.sleep(0.05)
        return "ok", "probe answered"

    monkeypatch.setattr(pm, "probe_active_account", slow_probe)
    t0 = time.time()
    pm.probe_cached("x", 600.0)
    assert pm.load_state()["probes"]["x"]["at"] < t0 + 0.05


def test_the_settle_loop_handles_a_report_that_arrived_while_it_was_finishing(world, monkeypatch):
    calls = []

    def fake_run_auto(reason="hook", signal=None):
        calls.append(signal)
        if len(calls) == 1:  # while this evaluation runs, another session's report lands
            pm.update_state(lambda s: s.setdefault("pendingSignals", []).append(
                {"type": "rate_limit", "at": time.time() + 0.001, "sessionId": "S2"}))
            return {"action": "none", "reason": "probe_ok_not_limited"}
        pm.update_state(lambda s: s.__setitem__("pendingSignals", []))
        return {"action": "none", "reason": "probe_ok_not_limited"}

    monkeypatch.setattr(pm, "run_auto", fake_run_auto)
    monkeypatch.setattr(pm.time, "sleep", lambda s: None)
    pm.run_auto_until_settled("stop-failure", "rate_limit")
    assert len(calls) == 2, "the late report was evaluated before the loop let go"


def test_the_limited_hold_ends_when_the_accounts_window_resets(world):
    world.add_account(A, five_hour=100.0)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    world.set_usage(A, exhausted=True)
    assert pm.balance_accounts()["action"] == "switched"  # A probed limited
    world.set_usage(B, five_hour=100.0, exhausted=True)
    world.set_usage(A, five_hour=5.0, exhausted=False, five_hour_resets_at="2099-01-01T00:00:00Z")  # a new window
    pm.update_state(lambda s: s.__setitem__("lastSwitch", {"at": time.time() - 400}))
    os.unlink(pm.USAGE_CACHE_PATH)
    assert pm.balance_accounts()["action"] == "switched"
    assert world.store_email() == A


def test_a_store_that_changes_between_reads_refuses_transiently_and_records_no_switch(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)

    def busy(*a, **k):
        raise pm_store.StoreBusy("kept changing")

    monkeypatch.setattr(pm, "write_store_oauth", busy)
    res = _switch(B)
    assert res["success"] is False and "store changed" in res["refused"]
    assert pm.load_state().get("lastSwitch") is None and not world.events("switch.unverified")


def test_only_known_per_model_buckets_count_as_limits():
    e = pm._numbers_entry("x", {"five_hour": {"utilization": 10}, "seven_day_oauth_apps": {"utilization": 100}}, 1.0)
    assert not e["isRateLimited"]


def test_reset_detection_compares_times_not_strings_and_spares_per_model_caps():
    now = time.time()
    iso = lambda t, us: time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".%06d+00:00" % us  # noqa: E731
    later = now + 3 * 3600
    probe = {"resetsAt": iso(later, 577660), "fiveHourAtProbe": 100.0}
    assert not pm._window_reset_since(probe, {"fiveHourResetsAt": iso(later, 577682)}, now), "same window, new microseconds"
    assert pm._window_reset_since(probe, {"fiveHourResetsAt": iso(later + 5 * 3600, 1)}, now), "a new window"
    assert pm._window_reset_since({"resetsAt": iso(now - 10, 0), "fiveHourAtProbe": 100.0}, {}, now), "the reset passed"
    assert not pm._window_reset_since({"resetsAt": iso(now - 10, 0), "fiveHourAtProbe": 30.0}, {}, now), \
        "a per-model cap (5-hour bucket not full) survives a 5-hour reset"
