#!/usr/bin/env python3
"""Mutation proof for the BRO-2713 guards.

Each mutation disables one guard in a scratch copy of scripts/ (the working tree is never touched).
The named tests must then FAIL. A mutation whose tests stay green means those tests do not prove
that guard: the run prints UNPROVEN and exits 1.

Guards are layered on purpose (a probe also stops what a telemetry bug lets through), so some kill
paths need two mutations to reappear. Those pairs are listed as combined mutations.

    python tests/mutation_check.py            # all
    python tests/mutation_check.py M3 M11     # some
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
K = "tests/test_kill_paths.py::"
U = "tests/test_provider_manager.py::"

# name: (description, [(file, old, new), ...], [tests that must fail])
MUTATIONS = {
    "M1": ("target liveness check skipped",
           [("provider_manager.py",
             '    """Prove the target\'s credential is live and is the target, without touching the store."""\n',
             '    """Prove the target\'s credential is live and is the target, without touching the store."""\n'
             '    return True, oauth, "ok"\n')],
           [K + "test_k1_switch_to_stale_standby_never_kills_running_session",
            U + "test_switch_refuses_a_stale_target_with_the_reason_and_marks_it_needs_login",
            U + "test_switch_refuses_a_target_copy_holding_another_accounts_tokens"]),
    "M2": ("outgoing write-back skipped",
           [("provider_manager.py", "if write_back and not write_orca_oauth(write_back, store_oauth):", "if False:")],
           [K + "test_k2_switch_away_and_back_after_claude_rotation_never_kills",
            U + "test_switch_writes_back_the_outgoing_chain_identified_by_profile"]),
    "M3": ("usage 429 recorded as a rate limit",
           [("provider_manager.py",
             'return done(_degraded_entry(account_id, "throttled", prev, now, "usage endpoint 429"))',
             'return done(dict(_degraded_entry(account_id, "ok", prev, now), telemetry="ok", isRateLimited=True))')],
           [U + "test_usage_429_backs_off_and_keeps_stale_numbers_without_claiming_a_limit"]),
    "M4": ("standby with unreadable usage or a dead grant eligible",
           [("provider_manager.py",
             'return (a.get("telemetry") == "ok" and a.get("hasStoredCredentials") and not a.get("needsLogin")\n'
             '                and not a.get("isRateLimited") and fh is not None and fh <= cfg["standbyMax"]',
             'return (a.get("hasStoredCredentials") and not a.get("isRateLimited")\n'
             '                and (fh is None or fh <= cfg["standbyMax"])')],
           [U + "test_balance_never_picks_a_standby_whose_usage_is_unreadable"]),
    "M5": ("post-tool-use rotates on rate-limit text again",
           [("provider_manager_hook.py", '    """Deliberately nothing: see the module docstring."""\n    return None',
             '    pm.rotate_account(reason="tool_rate_limit", force=True)')],
           [K + "test_k5_tool_errors_mentioning_rate_limits_never_rotate"]),
    "M6": ("machine-wide balancer lock not exclusive",
           [("pm_state.py", "            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n            break",
             "            break")],
           [U + "test_balancer_lock_is_exclusive_across_processes_and_reentrant_within_one"]),
    "M7": ("cooldown skipped",
           [("provider_manager.py", "    if since < gap:", "    if False:")],
           [K + "test_k7b_no_flip_back_inside_the_cooldown"]),
    "M8": ("store write drops the item's other keys (mcpOAuth)",
           [("pm_store.py", '    data = dict(cur.data or {})\n    data["claudeAiOauth"] = oauth\n    if not keychain_write(item',
             '    data = {"claudeAiOauth": oauth}\n    if not keychain_write(item')],
           [K + "test_k8_switch_leaves_each_store_items_mcp_tokens_untouched"]),
    "M9": ("unreadable keychain item treated as empty",
           [("pm_store.py",
             '        return Read("error", None, "security rc %d: %s" % (res.returncode, (res.stderr or "").strip()[:120]))',
             '        return Read("absent", None)')],
           [K + "test_k9_switch_fails_closed_when_the_store_is_unreadable",
            U + "test_keychain_read_distinguishes_absent_from_unreadable"]),
    "M10": ("refresh interlock removed",
            [("provider_manager.py", "    if store_account_id and account_id == store_account_id:", "    if False:"),
             ("provider_manager.py", '    if any(same_token(oauth["refreshToken"], rt) for rt in store_rts or []):', "    if False:")],
            [U + "test_refresh_never_spends_a_refresh_token_that_a_store_item_holds"]),
    "M10+M13": ("refresh interlock removed AND the store account read like a standby",
                [("provider_manager.py", "    if store_account_id and account_id == store_account_id:", "    if False:"),
                 ("provider_manager.py", '    if any(same_token(oauth["refreshToken"], rt) for rt in store_rts or []):', "    if False:"),
                 ("provider_manager.py", '    is_store_account = account_id == ctx["storeAccountId"]', "    is_store_account = False")],
                [K + "test_k10_usage_telemetry_never_spends_the_stores_refresh_token"]),
    "M11": ("probe skipped (telemetry 'limited' trusted)",
            [("provider_manager.py", 'result, detail = probe_cached(active["id"], cfg["probeTtlSeconds"])',
              'result, detail = "limited", "mutated"')],
            [K + "test_k12_a_passing_probe_blocks_the_rotation",
             U + "test_rotate_requires_a_confirmed_limit_and_force_overrides_it"]),
    "M3+M11": ("usage 429 as a limit AND the probe skipped",
               [("provider_manager.py",
                 'return done(_degraded_entry(account_id, "throttled", prev, now, "usage endpoint 429"))',
                 'return done(dict(_degraded_entry(account_id, "ok", prev, now), telemetry="ok", isRateLimited=True))'),
                ("provider_manager.py", 'result, detail = probe_cached(active["id"], cfg["probeTtlSeconds"])',
                 'result, detail = "limited", "mutated"')],
               [K + "test_k3_usage_429_never_triggers_a_rotation"]),
    "M17": ("hysteresis removed (any standby under 100% is 'healthier')",
            [("provider_manager.py", 'and fh is not None and fh <= cfg["standbyMax"]', 'and fh is not None and fh < 100.0'),
             ("provider_manager.py", '                and (active_fh is None or fh <= active_fh - cfg["margin"]))', '                )')],
            [U + "test_balance_hysteresis_needs_a_clearly_healthier_standby"]),
    "M3+M7+M11+M17": ("the 03:48:58/03:49:19 flip: 429 as a limit, no probe, no cooldown, no hysteresis",
                      [("provider_manager.py",
                        'return done(_degraded_entry(account_id, "throttled", prev, now, "usage endpoint 429"))',
                        'return done(dict(_degraded_entry(account_id, "ok", prev, now), telemetry="ok", isRateLimited=True))'),
                       ("provider_manager.py", 'result, detail = probe_cached(active["id"], cfg["probeTtlSeconds"])',
                        'result, detail = "limited", "mutated"'),
                       ("provider_manager.py", "    if since < gap:", "    if False:"),
                       ("provider_manager.py", 'and fh is not None and fh <= cfg["standbyMax"]', 'and fh is not None and fh < 100.0')],
                      [K + "test_k7_no_flip_back_when_new_account_telemetry_is_throttled"]),
    "M12": ("Claude Code's refresh lock not taken",
            [("provider_manager.py", "        with claude_refresh_lock(claude_config_dir(), CLAUDE_LOCK_WAIT_SECONDS):",
              "        with open(os.devnull):")],
            [K + "test_k13_switch_never_races_a_claude_code_refresh",
             U + "test_switch_refusals_name_the_reason"]),
    "M14": ("evaluation interval skipped",
            [("provider_manager.py",
              '    if not signal and now - load_state().get("lastEvalAt", 0) < cfg["evalIntervalSeconds"]:\n'
              '        return {"success": True, "action": "none", "reason": "recent_evaluation"}',
              ""),
             ("provider_manager.py",
              '        if not signal and time.time() - load_state().get("lastEvalAt", 0) < cfg["evalIntervalSeconds"]:\n'
              '            return {"success": True, "action": "none", "reason": "recent_evaluation"}',
              "")],
            [U + "test_run_auto_evaluates_at_most_once_per_interval_unless_a_limit_is_reported"]),
    "M15": ("store-changed check skipped",
            [("provider_manager.py", "            if not _same_chain(oauth_of(now_store.data), store_oauth):", "            if False:")],
            [U + "test_switch_refuses_when_the_store_changes_mid_switch_then_retries_cleanly"]),
    "M18": ("a dead active grant is treated as inconclusive (no failover)",
            [("provider_manager.py", '        elif result == "auth_dead":\n            reason = "active_grant_dead"',
              '        elif False:\n            reason = "active_grant_dead"')],
            [K + "test_k14_a_dead_active_grant_fails_over_to_a_healthy_account"]),
    "M16": ("StopFailure rate_limit does not start a failover",
            [("provider_manager_hook.py", '        kick("stop-failure", signal=signal, force=True)', "        pass")],
            [U + "test_stop_failure_rate_limit_records_the_session_and_fails_over_and_the_session_continues"]),
}


def apply(dst: Path, edits) -> None:
    for fname, old, new in edits:
        p = dst / fname
        text = p.read_text()
        n = text.count(old)
        if n != 1:
            raise SystemExit("mutation anchor in %s found %d times (expected 1): %r" % (fname, n, old[:80]))
        p.write_text(text.replace(old, new))


def run_tests(impl: Path, tests) -> subprocess.CompletedProcess:
    env = dict(os.environ, PM_IMPL_DIR=str(impl), PM_IMPL_IS_NEW="1")
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x"] + list(tests),
                          cwd=ROOT, env=env, text=True, capture_output=True, timeout=900)


def outcome(res: subprocess.CompletedProcess) -> str:
    """'red' only for a real test failure. A collection error, an import error or a missing pytest
    would turn every mutation 'red' and prove nothing."""
    tail = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""
    if res.returncode == 0 and " passed" in tail:
        return "green"
    if res.returncode == 1 and " failed" in tail and " error" not in tail:
        return "red"
    return "invalid"


def main(argv) -> int:
    names = argv or list(MUTATIONS)
    with tempfile.TemporaryDirectory(prefix="pm-mut-base-") as base:
        shutil.copytree(SCRIPTS, Path(base) / "scripts")
        all_tests = sorted({t for n in names for t in MUTATIONS[n][2]})
        baseline = run_tests(Path(base) / "scripts", all_tests)
        if outcome(baseline) != "green":
            print("INCONCLUSIVE: the listed tests are not green on the unmutated copy\n" + baseline.stdout[-2000:])
            return 2
    print("baseline: %d tests green on the unmutated copy" % len(all_tests))
    unproven = []
    for name in names:
        desc, edits, tests = MUTATIONS[name]
        results = []
        for t in tests:
            with tempfile.TemporaryDirectory(prefix="pm-mut-") as tmp:
                dst = Path(tmp) / "scripts"
                shutil.copytree(SCRIPTS, dst)
                apply(dst, edits)
                results.append(outcome(run_tests(dst, [t])))
        red = results.count("red")
        verdict = "PROVEN" if red == len(results) else ("INVALID" if "invalid" in results else "UNPROVEN")
        if verdict != "PROVEN":
            unproven.append(name)
        print("%-14s %-9s %-70s %d/%d tests red" % (name, verdict, desc, red, len(results)))
    if unproven:
        print("UNPROVEN: %s" % ", ".join(unproven))
        return 1
    print("all %d mutations proven" % len(names))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
