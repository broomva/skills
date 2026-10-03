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
    secret = "oat01-fake-" + "x" * 900  # a realistic store item is well over 800 bytes
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

def test_switch_writes_claudeaioauth_to_both_items_and_records_the_switch(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    res = pm.switch_account(B)
    assert res["success"] and res["switchedTo"] == B
    for item in (world.primary, world.mirror):
        assert world.store(item)["claudeAiOauth"]["refreshToken"] == world.orca_creds(B)["claudeAiOauth"]["refreshToken"]
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
    assert pm.refresh_account_token(world.accounts[A]["id"], store_rts=[rt], store_account_id=None) is None
    assert fake_anthropic.refresh_state(rt) == "valid"
    assert {e["reason"] for e in world.events("refresh.refused")} == {"refresh_token_in_store", "store_account"}


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
    assert world.store(world.mirror)["claudeAiOauth"]["refreshToken"] == live


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
