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
             '    the copy first), then check that the new access token\'s profile names that account."""\n',
             '    the copy first), then check that the new access token\'s profile names that account."""\n'
             '    return True, oauth_of(read_orca(target["id"]).data), "ok"\n')],
           [K + "test_k1_switch_to_stale_standby_never_kills_running_session",
            U + "test_switch_refuses_a_stale_target_with_the_reason_and_marks_it_needs_login",
            U + "test_switch_refuses_a_target_copy_holding_another_accounts_tokens"]),
    "M2": ("outgoing write-back skipped",
           [("provider_manager.py", "if write_back and not write_orca_oauth(write_back, store_oauth, LOCKED_IO_TIMEOUT):", "if False:")],
           [K + "test_k2_switch_away_and_back_after_claude_rotation_never_kills",
            U + "test_switch_writes_back_the_outgoing_chain_identified_by_profile"]),
    "M3": ("usage 429 recorded as a rate limit",
           [("provider_manager.py",
             'return done(_degraded_entry(account_id, "throttled", prev, now, "usage endpoint 429"))',
             'return done(dict(_degraded_entry(account_id, "ok", prev, now), telemetry="ok", isRateLimited=True))')],
           [U + "test_usage_429_backs_off_and_keeps_stale_numbers_without_claiming_a_limit"]),
    "M4": ("standby with unreadable usage or a dead grant eligible",
           [("provider_manager.py",
             'return bool(a.get("telemetry") == "ok" and a.get("hasStoredCredentials") and not a.get("needsLogin")\n'
             '                and not a.get("isRateLimited") and fh is not None and fh <= cfg["standbyMax"]',
             'return bool(a.get("hasStoredCredentials") and not a.get("isRateLimited")\n'
             '                and (fh is None or fh <= cfg["standbyMax"])'),
            ("provider_manager.py", '                and (active_fh is None or fh <= active_fh - cfg["margin"]))',
             '                and (active_fh is None or fh is None or fh <= active_fh - cfg["margin"]))')],
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
           [("pm_store.py", '        data = dict(cur.data or {})\n        data["claudeAiOauth"] = oauth\n        again',
             '        data = {"claudeAiOauth": oauth}\n        again')],
           [K + "test_k8_switch_leaves_each_store_items_mcp_tokens_untouched"]),
    "M9": ("unreadable keychain item treated as empty",
           [("pm_store.py",
             '        return Read("error", None, "security rc %d: %s" % (res.returncode, (res.stderr or "").strip()[:120]))',
             '        return Read("absent", None)')],
           [K + "test_k9_switch_fails_closed_when_the_store_is_unreadable",
            U + "test_keychain_read_distinguishes_absent_from_unreadable"]),
    "M10": ("refresh interlock removed",
            [("provider_manager.py", '        elif ctx["storeAccountId"] and account_id == ctx["storeAccountId"]:', "        elif False:"),
             ("provider_manager.py", '        if not refusal and any(same_token(oauth["refreshToken"], rt) for rt in ctx["storeRts"]):',
              "        if False:")],
            [U + "test_refresh_never_spends_a_refresh_token_that_a_store_item_holds"]),
    "M10+M13": ("refresh interlock removed AND the store account read like a standby",
                [("provider_manager.py", '        elif ctx["storeAccountId"] and account_id == ctx["storeAccountId"]:', "        elif False:"),
                 ("provider_manager.py", '        if not refusal and any(same_token(oauth["refreshToken"], rt) for rt in ctx["storeRts"]):',
                  "        if False:"),
                 ("provider_manager.py", '        elif ctx["storeIdentity"] not in VERIFIED_IDENTITY + ("store_empty",) and not allow_unverified:',
                  "        elif False:"),
                 ("provider_manager.py", '    is_store_account = account_id == ctx["storeAccountId"]', "    is_store_account = False")],
                [K + "test_k10_usage_telemetry_never_spends_the_stores_refresh_token"]),
    "M11": ("probe skipped (telemetry 'limited' trusted)",
            [("provider_manager.py", 'result, detail = probe_cached(active["id"], cfg["probeTtlSeconds"], fresh_after=newest_report,',
              'result, detail = "limited", "mutated"; _unused = dict(fresh_after=newest_report,')],
            [K + "test_k12_a_passing_probe_blocks_the_rotation",
             U + "test_rotate_requires_a_confirmed_limit_and_force_overrides_it"]),
    "M3+M11": ("usage 429 as a limit AND the probe skipped",
               [("provider_manager.py",
                 'return done(_degraded_entry(account_id, "throttled", prev, now, "usage endpoint 429"))',
                 'return done(dict(_degraded_entry(account_id, "ok", prev, now), telemetry="ok", isRateLimited=True))'),
                ("provider_manager.py", 'result, detail = probe_cached(active["id"], cfg["probeTtlSeconds"], fresh_after=newest_report,',
                 'result, detail = "limited", "mutated"; _unused = dict(fresh_after=newest_report,')],
               [K + "test_k3_usage_429_never_triggers_a_rotation"]),
    "M17": ("hysteresis removed (any standby under 100% is 'healthier')",
            [("provider_manager.py", 'and fh is not None and fh <= cfg["standbyMax"]', 'and fh is not None and fh < 100.0'),
             ("provider_manager.py", '                and (active_fh is None or fh <= active_fh - cfg["margin"]))', '                )')],
            [U + "test_balance_hysteresis_needs_a_clearly_healthier_standby"]),
    "M3+M7+M11+M17": ("the 03:48:58/03:49:19 flip: 429 as a limit, no probe, no cooldown, no hysteresis",
                      [("provider_manager.py",
                        'return done(_degraded_entry(account_id, "throttled", prev, now, "usage endpoint 429"))',
                        'return done(dict(_degraded_entry(account_id, "ok", prev, now), telemetry="ok", isRateLimited=True))'),
                       ("provider_manager.py", 'result, detail = probe_cached(active["id"], cfg["probeTtlSeconds"], fresh_after=newest_report,',
                        'result, detail = "limited", "mutated"; _unused = dict(fresh_after=newest_report,'),
                       ("provider_manager.py", "    if since < gap:", "    if False:"),
                       ("provider_manager.py", 'and fh is not None and fh <= cfg["standbyMax"]', 'and fh is not None and fh < 100.0')],
                      [K + "test_k7_no_flip_back_when_new_account_telemetry_is_throttled"]),
    "M12": ("Claude Code's refresh lock not taken",
            [("provider_manager.py", "        with claude_refresh_lock(claude_config_dir(), CLAUDE_LOCK_WAIT_SECONDS) as held_for:",
              "        with __import__('contextlib').nullcontext(lambda: 0.0) as held_for:")],
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
    "M19": ("refresh runs without the machine-wide lock",
            [("provider_manager.py", '''    with pm_state.balancer_lock(BALANCER_LOCK_PATH, blocking=False, holder="refresh") as held:
        if not held:''',
              '''    with pm_state.balancer_lock(BALANCER_LOCK_PATH, blocking=False, holder="refresh") as held:
        if False:''')],
            [U + "test_refresh_never_runs_while_another_provider_manager_action_holds_the_lock"]),
    "M21": ("a stale Claude Code refresh lock is never reclaimed",
            [("pm_store.py", '    """proper-lockfile\'s rule: a lock directory untouched for 60 s belongs to a dead holder."""\n',
              '    """proper-lockfile\'s rule: a lock directory untouched for 60 s belongs to a dead holder."""\n    return False\n')],
            [U + "test_a_stale_claude_refresh_lock_is_reclaimed"]),
    "M22": ("identity matched on email alone, or on org alone",
            [("provider_manager.py", "        return hits[0] if not (org and known_org and org != known_org) else None", "        return hits[0]"),
             ("provider_manager.py", "    if email:\n        hits", "    if False:\n        hits")],
            [U + "test_identity_needs_email_and_org_to_agree",
             U + "test_a_same_org_stranger_in_the_store_is_not_written_back_as_a_roster_account"]),
    "M23": ("a reported limit is consumed by the first evaluation, whatever it decides",
            [("provider_manager.py", '    if pending:\n        signal = signal or pending[-1].get("type")',
              '    if pending:\n        update_state(lambda s: s.__setitem__("pendingSignals", []))\n'
              '        signal = signal or pending[-1].get("type")')],
            [U + "test_a_reported_limit_survives_a_cooldown_and_a_dry_run"]),
    "M24": ("version gate off",
            [("provider_manager.py", "        verified, version = version_verified(cfg)", "        verified, version = True, None")],
            [U + "test_an_unmeasured_claude_code_version_makes_automatic_switching_observe_only"]),
    "M25": ("the mirror item is written again",
            [("provider_manager.py", '                write_store_oauth(ctx["primary"], live_oauth, ctx["user"], LOCKED_IO_TIMEOUT, attempts=1)\n',
              '                write_store_oauth(ctx["primary"], live_oauth, ctx["user"], LOCKED_IO_TIMEOUT, attempts=1)\n'
              '                [write_store_oauth(m, live_oauth, ctx["user"]) for m in ctx["mirrors"]]\n')],
            [U + "test_switch_writes_the_primary_item_only_and_records_the_switch"]),
    "M26a": ("the mirror is protected even when nothing reads it",
             [("provider_manager.py", ' \\\n                and config_dir_override_running(claude_config_dir()):', ':')],
             [U + "test_a_stale_mirror_nobody_reads_does_not_block_switching_back"]),
    "M26b": ("the mirror is never protected",
             [("provider_manager.py", ' \\\n                and config_dir_override_running(claude_config_dir()):', ' and False:')],
             [U + "test_refresh_never_spends_a_refresh_token_that_a_store_item_holds"]),
    "M27": ("an unparseable ~/.claude.json is overwritten",
            [("provider_manager.py", "        if before is not None and not isinstance(data, dict):\n            return False\n", "")],
            [U + "test_claude_json_that_does_not_parse_is_never_replaced_and_its_mode_is_kept"]),
    "M28": ("the target is refreshed only near expiry (its refresh token inferred, not proven)",
            [("provider_manager.py", '''    oauth = refresh_account_token(target["id"], allow_unverified=allow_unverified)
    if not oauth:''',
              '''    copy = oauth_of(read_orca(target["id"]).data)
    oauth = refresh_account_token(target["id"], allow_unverified=allow_unverified) \
        if expiring(copy, 10 * 60_000) else copy
    if not oauth:''')],
            [K + "test_k15_a_live_access_token_with_a_spent_refresh_token_never_reaches_the_store"]),
    "M29": ("the unscoped item is protected only when a process override is seen",
            [("provider_manager.py", "    unconditional = [store] + [r for m, r in zip(mirrors, mirror_reads) if m == STORE_BASE]\n"
              "    scoped = [r for m, r in zip(mirrors, mirror_reads) if m != STORE_BASE]",
              "    unconditional = [store]\n    scoped = list(mirror_reads)")],
            [U + "test_the_unscoped_item_is_always_protected_even_when_it_is_the_mirror"]),
    "M30": ("a cached probe answers a report newer than itself",
            [("provider_manager.py", '    if p and age_ok and p.get("at", 0) >= fresh_after:', '    if p and age_ok:')],
            [U + "test_a_report_newer_than_the_cached_probe_gets_a_new_probe"]),
    "M31": ("a probe-confirmed limited account is a failover target again at once",
            [("provider_manager.py", '        if p.get("result") == "limited" and now - p.get("at", 0) < LIMITED_HOLD_SECONDS \\\n'
              '                and not _window_reset_since(p, a, now):', '        if False:')],
            [U + "test_no_failover_back_to_an_account_the_probe_confirmed_limited"]),
    "M32": ("several settle loops run at once",
            [("provider_manager.py", '''        if not mine:
            return {"success": True, "action": "none", "reason": "settle_loop_running"}''', "        pass")],
            [U + "test_settle_loop_retries_until_a_switch_and_runs_once_per_machine"]),
    "M33": ("resolving reports clears ones that arrived during the probe",
            [("provider_manager.py", 'p for p in s.get("pendingSignals", []) if (p.get("type"), p.get("at"), p.get("sessionId")) not in seen]))',
              'p for p in []]))')],
            [U + "test_a_report_arriving_during_the_probe_survives_it"]),
    "M34": ("per-model weekly caps ignored",
            [("provider_manager.py", '        if key in MODEL_WEEKLY_BUCKETS and isinstance(bucket, dict) \\\n',
              '        if False and isinstance(bucket, dict) \\\n')],
            [U + "test_a_per_model_weekly_cap_counts_as_limited"]),
    "M35": ("a probe is stamped with its finish time",
            [("provider_manager.py", '        account_id, {"at": started, "result": result,',
              '        account_id, {"at": time.time(), "result": result,')],
            [U + "test_a_probe_is_stamped_with_its_start_so_a_report_during_it_is_reprobed"]),
    "M36": ("the settle loop lets go with a report it turned away still pending",
            [("provider_manager.py", "                if not newer:\n                    break", "                if True:\n                    break")],
            [U + "test_the_settle_loop_handles_a_report_that_arrived_while_it_was_finishing"]),
    "M37": ("the limited hold ignores a window reset",
            [("provider_manager.py", "                and not _window_reset_since(p, a, now):", ":")],
            [U + "test_the_limited_hold_ends_when_the_accounts_window_resets"]),
    "M38": ("reset detection compares strings (the live endpoint's microseconds vary)",
            [("provider_manager.py", "    return current is not None and current > at_probe + 60",
              "    return account.get(\"fiveHourResetsAt\") not in (None, probe.get(\"resetsAt\"))")],
            [U + "test_reset_detection_compares_times_not_strings_and_spares_per_model_caps"]),
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


RED_MARKERS = ("AssertionError", "SessionDied", "DID NOT RAISE")


def outcome(res: subprocess.CompletedProcess) -> str:
    """'red' only when the test failed on its own assertion (or the session died, or an expected
    refusal did not happen). A collection error, an import error, a missing pytest or an unrelated
    exception from a broken mutation would turn every mutation 'red' and prove nothing."""
    tail = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""
    if res.returncode == 0 and " passed" in tail:
        return "green"
    if res.returncode == 1 and " failed" in tail and " error" not in tail \
            and any(m in res.stdout for m in RED_MARKERS):
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
