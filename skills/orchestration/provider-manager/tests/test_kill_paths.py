"""Regression suite for BRO-2713: each test is a path by which a balance or failover killed (or
falsely rotated) running sessions, reproduced end to end in the fake world with a running session
(ClaudeCodeSim) that behaves like Claude Code 2.1.280.

Run against origin/main's scripts (PM_IMPL_DIR) these fail: each failure is the kill reproduced.
Run against this branch they pass.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import fake_anthropic
import pytest
from sim import SessionDied

from conftest import IMPL_DIR, pm

A = "a@example.com"
B = "b@example.com"


def _try(fn, *args, **kw):
    """Call a switch/balance entry point; the fixed code may refuse by raising."""
    try:
        return fn(*args, **kw)
    except Exception as e:  # noqa: BLE001 - refusal is an allowed outcome here
        return {"raised": repr(e)}


def _age_usage_cache():
    """Let the usage cache's TTL lapse, so the next read is fresh telemetry, not a cached entry."""
    path = Path(pm.USAGE_CACHE_PATH)
    if not path.exists():
        return
    data = json.loads(path.read_text())
    for entry in data.get("accounts", {}).values():
        entry["cachedAt"] = entry.get("cachedAt", 0) - 3600
    path.write_text(json.dumps(data))


def _age_shared_token(world, email):
    """Time passes: the access token shared by the store and the Orca copy nears expiry
    (Claude Code refreshes inside a 5-minute window)."""
    soon = fake_anthropic.now_ms() + 60_000
    creds = world.orca_creds(email)
    creds["claudeAiOauth"]["expiresAt"] = soon
    world.set_orca_creds(email, creds)
    world.expire_store_access()


# K1 — the 10-01 14:33Z / 10-02 03:48Z shape: a switch writes a target whose stored refresh token was
# already consumed. Every running session refreshes with it, gets invalid_grant, and dies.
def test_k1_switch_to_stale_standby_never_kills_running_session(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    world.make_orca_copy_stale(B)
    s = world.session()
    assert s.run(2) == ["ok", "ok"]

    _try(pm.switch_account, B)

    s.run(3)  # SessionDied here is the kill
    assert s.dead is None
    assert world.store_email() == A, "a dead credential must never reach the store"


# K2 — no write-back: Claude Code rotates A's refresh token while A is active; a switch away and back
# writes A's consumed Orca copy.
def test_k2_switch_away_and_back_after_claude_rotation_never_kills(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    s = world.session()
    s.run(1)
    old_at = world.orca_creds(A)["claudeAiOauth"]["accessToken"]
    _age_shared_token(world, A)
    s.run(1)
    assert s.refreshes == 1, "the session should have rotated A's refresh token"
    fake_anthropic.expire_access(old_at)  # time passes; the pre-rotation access token is now dead
    creds = world.orca_creds(A)
    creds["claudeAiOauth"]["expiresAt"] = fake_anthropic.now_ms() - 1000
    world.set_orca_creds(A, creds)

    _try(pm.switch_account, B)
    s.run(1)
    assert world.store_email() == B
    _try(pm.switch_account, A)

    s.run(3)
    assert s.dead is None
    assert world.store_email() == A
    assert s.served[-1] == A


# K3 — the usage endpoint answering 429 is telemetry throttling, not an exhausted account.
def test_k3_usage_429_never_triggers_a_rotation(world):
    world.add_account(A)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    world.set_usage(A, usage_mode="429")
    s = world.session()

    _try(pm.balance_accounts, threshold=85.0, dry_run=False)
    _try(pm.balance_accounts, threshold=85.0, dry_run=False)

    assert world.switches() == []
    assert world.store_email() == A
    assert s.run(2) == ["ok", "ok"]


# K4 — a standby whose usage cannot be read (here: its stored grant is dead) was treated as the best
# candidate (`best_util is None`), and the switch killed everyone.
def test_k4_balance_never_switches_to_a_standby_with_unknown_usage(world):
    world.add_account(A, five_hour=94.0)
    world.add_account(B)
    world.activate(A)
    world.make_orca_copy_stale(B)
    s = world.session()
    s.run(1)

    _try(pm.balance_accounts, threshold=85.0, dry_run=False)

    s.run(2)
    assert s.dead is None
    assert world.switches() == []


# K5 — PostToolUseFailure text is never a Claude rate limit (GitHub's API limit, a 429 from a site).
def test_k5_tool_errors_mentioning_rate_limits_never_rotate(world, pmh):
    world.add_account(A, five_hour=30.0)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    for payload in (
        {"hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
         "error": "gh: API rate limit exceeded for user ID 1. (HTTP 403)"},
        {"hook_event_name": "PostToolUseFailure", "tool_name": "WebFetch",
         "error": "Request failed with status code 429 Too Many Requests"},
        {"hook_event_name": "PostToolUse", "tool_name": "Read",
         "tool_response": {"file": {"content": "RATE_LIMIT_PATTERNS = [r'rate_limit_error']"}}},
    ):
        _try(pmh.handle_post_tool_use, payload)
    assert world.switches() == []
    assert world.store_email() == A


# K6 — N sessions' hooks fire together; the machine must rotate at most once.
def test_k6_concurrent_hook_processes_switch_at_most_once(world):
    world.add_account(A, five_hour=95.0)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    env = world.env()
    env["PROVIDER_MANAGER_INLINE"] = "1"
    go = world.tmp / "go"
    hook = str(IMPL_DIR / "provider_manager_hook.py")
    wrapper = (
        "import os,runpy,sys,time\n"
        "while not os.path.exists(%r): time.sleep(0.005)\n"
        "sys.argv=[%r,'prompt-submit']\n"
        "runpy.run_path(%r, run_name='__main__')\n" % (str(go), hook, hook)
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", wrapper], env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(8)
    ]
    time.sleep(0.5)  # let every interpreter start and park on the go file
    go.write_text("1")
    for p in procs:
        p.communicate(timeout=120)

    assert len(world.switches()) == 1, [e.get("iso") for e in world.switches()]


# K7 — two flips 21 s apart (10-02 03:48:58Z / 03:49:19Z): right after a switch, the new account's
# usage read 429 and the balancer flipped straight back.
def test_k7_no_flip_back_when_new_account_telemetry_is_throttled(world):
    world.add_account(A, five_hour=94.0)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    _try(pm.balance_accounts, threshold=85.0, dry_run=False)
    assert world.store_email() == B, "precondition: the first, justified balance switches to B"

    world.set_usage(B, usage_mode="429")
    _age_usage_cache()
    _try(pm.balance_accounts, threshold=85.0, dry_run=False)

    assert len(world.switches()) == 1
    assert world.store_email() == B


def test_k7b_no_flip_back_inside_the_cooldown(world):
    world.add_account(A, five_hour=94.0)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    _try(pm.balance_accounts, threshold=85.0, dry_run=False)
    assert world.store_email() == B

    world.set_usage(B, five_hour=96.0)
    world.set_usage(A, five_hour=10.0)
    _age_usage_cache()
    _try(pm.balance_accounts, threshold=85.0, dry_run=False)

    assert len(world.switches()) == 1


# K8 — D28: the switch merged mcpOAuth across both store items with "later wins", so the stale mirror's
# Linear tokens replaced the live ones (Linear then signs out on its next refresh).
def test_k8_switch_leaves_each_store_items_mcp_tokens_untouched(world):
    world.add_account(A)
    world.add_account(B)
    live = {"linear-server|abc123": {"serverName": "linear-server", "accessToken": "lin-at-2",
                                     "refreshToken": "lin-rt-2", "expiresAt": 1999999999999}}
    stale = {"linear-server|abc123": {"serverName": "linear-server", "accessToken": "lin-at-1",
                                      "refreshToken": "lin-rt-1", "expiresAt": 1799999999999}}
    world.activate(A, mcp=live)
    mirror = world.store(world.mirror)
    mirror["mcpOAuth"] = stale
    import keychain_db
    keychain_db.write_json(world.db, world.mirror, "tester", mirror)

    _try(pm.switch_account, B)

    assert world.store_email() == B
    assert world.store().get("mcpOAuth") == live
    assert world.store(world.mirror).get("mcpOAuth") == stale


# K9 — an unreadable store must stop the switch, not be treated as empty.
def test_k9_switch_fails_closed_when_the_store_is_unreadable(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A, mcp={"linear-server|abc123": {"accessToken": "lin-at", "refreshToken": "lin-rt"}})
    before = world.store_raw()
    world.faults(read_error=[world.primary])

    _try(pm.switch_account, B)

    world.faults()
    assert world.store_raw() == before


# K10 — telemetry must never spend the refresh token the store holds. Here orca-data names B as
# active while the store holds A (a session wrote A back after a switch: the 10-01 18:40Z "flipped
# back without my action"), and A's access token has expired.
def test_k10_usage_telemetry_never_spends_the_stores_refresh_token(world):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    orca = json.loads(world.paths["ORCA_DATA_PATH"].read_text())
    orca["settings"]["activeClaudeManagedAccountId"] = world.accounts[B]["id"]
    world.paths["ORCA_DATA_PATH"].write_text(json.dumps(orca))
    at = world.orca_creds(A)["claudeAiOauth"]["accessToken"]
    fake_anthropic.expire_access(at)
    creds = world.orca_creds(A)
    creds["claudeAiOauth"]["expiresAt"] = fake_anthropic.now_ms() - 1000
    world.set_orca_creds(A, creds)
    world.expire_store_access()

    _try(pm.fetch_all_usage, force_refresh=True)

    s = world.session()
    s.run(2)
    assert s.dead is None


# K12 — usage says "limited" (a locked_reason) but the account serves requests; the probe must
# overrule the telemetry.
def test_k12_a_passing_probe_blocks_the_rotation(world):
    world.add_account(A)
    world.add_account(B, five_hour=5.0)
    world.activate(A)
    world.set_usage(A, locked_reason="five_hour_limit_reached")

    _try(pm.balance_accounts, threshold=85.0, dry_run=False)

    assert world.switches() == []
    assert world.store_email() == A


# K13 — a Claude Code process is mid-refresh (holds its refresh lock); a switch must not race it.
def test_k13_switch_never_races_a_claude_code_refresh(world, monkeypatch):
    world.add_account(A)
    world.add_account(B)
    world.activate(A)
    monkeypatch.setattr(pm, "CLAUDE_LOCK_WAIT_SECONDS", 0.3, raising=False)
    os.mkdir(world.config_dir / ".oauth_refresh.lock")
    before = world.store_raw()

    _try(pm.switch_account, B)

    assert world.store_raw() == before


# K14 — D24 / BRO-2713's first report (10-01 14:33Z): the ACTIVE account's grant is dead, so every
# session fails with authentication_failed. Recovery must not wait for a human: fail over to a healthy
# account (Claude Code itself proved the store's credential dead), and resumed sessions continue there.
def test_k14_a_dead_active_grant_fails_over_to_a_healthy_account(world, pmh, monkeypatch):
    world.add_account(A)
    world.add_account(B, five_hour=10.0)
    world.activate(A)
    o = world.store()["claudeAiOauth"]
    fake_anthropic.consume(o["refreshToken"])
    fake_anthropic.expire_access(o["accessToken"])
    world.expire_store_access()
    s = world.session()
    with pytest.raises(SessionDied):
        s.request()
    monkeypatch.setenv("PROVIDER_MANAGER_INLINE", "1")
    if hasattr(pmh, "handle_stop_failure"):
        pmh.handle_stop_failure({"hook_event_name": "StopFailure", "session_id": "S1",
                                 "error": "authentication_failed"})
    resumed = world.session("S1-resumed")
    assert resumed.run(2) == ["ok", "ok"]
    assert resumed.served[-1] == B
