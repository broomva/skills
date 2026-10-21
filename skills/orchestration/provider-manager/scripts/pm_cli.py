"""pm_cli.py — the provider_manager.py command line: argument parsing and output only.
All behaviour lives in provider_manager (passed in as `pm`)."""

import argparse
import json
import sys
import time
from typing import Any, Dict

import pm_state



def _fmt_pct(v: Any) -> str:
    return "%s%%" % v if v is not None else "-"


def _usage_status(a: Dict[str, Any]) -> str:
    t = a.get("telemetry")
    if a.get("needsLogin"):
        return "NEEDS_LOGIN"
    if t == "ok":
        return "LIMITED" if a.get("isRateLimited") else (a.get("usageStatus") or "ok").upper()
    notes = []
    numbers_at = (a.get("usage") or {}).get("numbersAt")
    notes.append("numbers %dm old" % int((time.time() - numbers_at) / 60) if numbers_at else "no numbers yet")
    if a.get("backoffRemainingSeconds"):
        notes.append("next try in %dm" % max(1, int(a["backoffRemainingSeconds"] / 60)))
    return "%s (%s)" % ((t or "unavailable").upper(), ", ".join(notes))


def cmd_stalled(pm, hours: float, as_json: bool) -> None:
    entries = pm_state.list_stalled(pm.STALLED_PATH, time.time() - hours * 3600)
    if as_json:
        print(json.dumps(entries, indent=2))
        return
    if not entries:
        print("No stalled sessions in the last %g h." % hours)
        return
    print("%-20s %-22s %-38s %-14s %s" % ("TIME (UTC)", "ERROR", "SESSION", "PASEO AGENT", "CWD"))
    for e in entries:
        print("%-20s %-22s %-38s %-14s %s" % (e.get("iso"), e.get("error"), e.get("sessionId"),
                                              (e.get("paseoAgentId") or "-")[:14], e.get("cwd")))
    print("\nResume: send each a prompt (Paseo: the agent id above), or `claude --resume <session>` from its cwd.")


def _print_claude_list(accounts: list, as_json: bool) -> None:
    if as_json:
        print(json.dumps(accounts, indent=2))
        return
    print("%-8s %-28s %-14s %-14s %s" % ("ACTIVE", "EMAIL", "SUBSCRIPTION", "STORED CREDS", "UUID"))
    print("-" * 85)
    for a in accounts:
        creds = "Yes (Fresh)" if a.get("isTokenFresh") else ("Yes" if a.get("hasStoredCredentials") else "No")
        print("%-8s %-28s %-14s %-14s %s" % (" * " if a["isActive"] else "", a["email"],
                                             (a.get("subscriptionType") or "-"), creds, a["id"]))


def _print_codex_list(accounts: list, as_json: bool) -> None:
    if as_json:
        print(json.dumps(accounts, indent=2))
        return
    print("%-8s %-28s %-14s %-14s %s" % ("ACTIVE", "EMAIL", "SUBSCRIPTION", "STORED CREDS", "UUID"))
    print("-" * 85)
    for a in accounts:
        creds = "Yes (Fresh)" if a.get("isTokenFresh") else ("Yes" if a.get("hasStoredCredentials") else "No")
        print("%-8s %-28s %-14s %-14s %s" % (" * " if a["isActive"] else "", a["email"],
                                             (a.get("subscriptionType") or "-"), creds, a["id"]))


def _print_claude_usage(pm, accounts: list, as_json: bool) -> None:
    if as_json:
        print(json.dumps(accounts, indent=2))
        return
    print("%-8s %-28s %-22s %-22s %s" % ("ACTIVE", "EMAIL", "5-HOUR UTIL", "7-DAY UTIL", "STATUS"))
    print("-" * 100)
    for a in accounts:
        fh = _fmt_pct(a["fiveHourUtil"])
        if a.get("fiveHourResetsAt"):
            fh += " (%s)" % a["fiveHourResetsAt"].split("T")[-1][:5]
        sd = _fmt_pct(a["sevenDayUtil"])
        if a.get("sevenDayResetsAt"):
            sd += " (%s)" % a["sevenDayResetsAt"].split("T")[0]
        print("%-8s %-28s %-22s %-22s %s" % (" * " if a["isActive"] else "", a["email"], fh, sd, _usage_status(a)))
    active = next((a for a in accounts if a.get("isActive")), None)
    stale = pm.stale_numbers_note(active, pm.load_config()) if active else None
    if stale:
        print("\nNote: %s." % stale)
    gate = pm.gate_status()
    if gate:
        print("\nNote: %s." % gate)


def _print_codex_usage(accounts: list, as_json: bool) -> None:
    if as_json:
        print(json.dumps(accounts, indent=2))
        return
    print("%-8s %-28s %-12s %-12s %-8s %-14s %s" % ("ACTIVE", "EMAIL", "5-HOUR UTIL", "7-DAY UTIL", "CREDITS",
                                                  "STATUS", "STANDBY"))
    print("-" * 110)
    for a in accounts:
        pw = a.get("primary") or {}
        sw = a.get("secondary") or {}
        fh = _fmt_pct(pw.get("usedPercent"))
        sd = _fmt_pct(sw.get("usedPercent"))
        cr = (a.get("credits") or {}).get("balance") or "-"
        status = a.get("usageStatus", "-")
        if a.get("healthReason") and a.get("telemetry") != "ok":
            status += " (%s)" % a["healthReason"]
        standby = "active" if a.get("isActive") else (a.get("standbyReason") or "candidate")
        print("%-8s %-28s %-12s %-12s %-8s %-14s %s" % (
            " * " if a.get("isActive") else "", a.get("email") or "-", fh, sd, cr, status, standby))


def main(pm) -> None:
    common = argparse.ArgumentParser(add_help=False)
    # SUPPRESS: a subparser's default would otherwise erase a --json given before the subcommand
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output results in JSON format")
    common.add_argument("--provider", choices=["claude", "codex", "all"], default=argparse.SUPPRESS,
                        help="Target provider (claude, codex, or all; default: claude)")
    parser = argparse.ArgumentParser(description="Subscription account manager (Claude Code & OpenAI Codex)", parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List managed accounts", parents=[common])
    sub.add_parser("status", help="Show active provider and auth status", parents=[common])
    p = sub.add_parser("usage", help="Usage telemetry for all accounts", parents=[common])
    p.add_argument("--force", action="store_true", help="Bypass the cache (a 429 backoff still applies)")
    p = sub.add_parser("balance", help="Evaluate and, if justified, balance accounts", parents=[common])
    p.add_argument("--threshold", type=float, default=None, help="Active 5-hour %% that starts a balance (default 90)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--auto", action="store_true", help="Hook mode: one evaluation per interval, machine-wide")
    p.add_argument("--reason", default="hook")
    p.add_argument("--signal", choices=["rate_limit", "auth_failed"], default=None)
    p = sub.add_parser("switch", help="Switch the active account (safely)", parents=[common])
    p.add_argument("account", help="Account email or UUID")
    p.add_argument("--force", action="store_true", help="Discard an unidentifiable store credential")
    p = sub.add_parser("login-headless", help="Re-authorize an account from a browser session", parents=[common])
    p.add_argument("--email")
    p.add_argument("--repair-home", help="Codex: recover a retained home only after authority-confirmed token revocation")
    p.add_argument("--browser", default="arc", choices=["arc", "chrome"])
    p.add_argument("--profile")
    p.add_argument("--force", action="store_true", help="Log in over an unidentifiable store credential")
    p.add_argument("--space", help="Codex: the Arc space to log in from (default: codexAccounts.<email>.arcSpace, else Stimulus)")
    p = sub.add_parser("rotate", help="Failover for a reported rate limit (operator/orchestrator only)", parents=[common])
    p.add_argument("--reason", default="rate_limit")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="Skip the probe and the minimum gap")
    p = sub.add_parser("history", help="Recent switches (and, with --all, every decision)", parents=[common])
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("stalled", help="Sessions whose turn ended on a rate limit or auth failure", parents=[common])
    p.add_argument("--hours", type=float, default=24.0)
    p = sub.add_parser("hold", help="Pause automatic switching", parents=[common])
    p.add_argument("--minutes", type=float, default=30.0)
    p.add_argument("--clear", action="store_true")
    p = sub.add_parser("codex-home", help="Show the selected immutable Codex home", parents=[common])
    p.add_argument("--email")
    p = sub.add_parser("codex-launcher", help="Install a separate account-selection launcher", parents=[common])
    p.add_argument("--binary", required=True, help="Absolute path of the real Codex executable")
    sub.add_parser("state", help="Balancer state: lock, cooldown, hold, health", parents=[common])
    args = parser.parse_args()
    args.json = getattr(args, "json", False)
    args.provider = getattr(args, "provider", "claude")

    try:
        if args.command in ("codex-home", "codex-launcher"):
            import pm_codex_homes
            if args.command == "codex-launcher":
                result = {"launcher": pm_codex_homes.install_launcher(args.binary)}
            else:
                result = pm_codex_homes.entry(args.email) if args.email else pm_codex_homes.selected()
                if not result:
                    raise pm.StoreError("No isolated Codex home; select or log in the account first")
            print(json.dumps(result, indent=2) if args.json else result.get("home", result.get("launcher")))
        elif args.command == "list":
            if args.provider == "codex":
                _print_codex_list(pm.list_codex_accounts(), args.json)
            elif args.provider == "all":
                if args.json:
                    print(json.dumps({
                        "claude": pm.list_accounts(),
                        "codex": pm.list_codex_accounts(),
                    }, indent=2))
                else:
                    print("[Claude Code Accounts]")
                    _print_claude_list(pm.list_accounts(), False)
                    print("\n[OpenAI Codex Accounts]")
                    _print_codex_list(pm.list_codex_accounts(), False)
            else:
                _print_claude_list(pm.list_accounts(), args.json)
        elif args.command == "status":
            if args.provider == "codex":
                status = pm.get_codex_auth_status()
                if args.json:
                    print(json.dumps(status, indent=2))
                else:
                    print("Provider:      OpenAI Codex")
                    print("Logged In:     %s" % status.get("loggedIn"))
                    print("Active Email:  %s" % (status.get("email") or "-"))
                    print("Plan Type:     %s" % (status.get("planType") or "-"))
                    print("Account ID:    %s" % (status.get("accountId") or "-"))
                    print("Token Fresh:   %s" % status.get("tokenFresh"))
            elif args.provider == "all":
                c_status = pm.get_claude_auth_status()
                x_status = pm.get_codex_auth_status()
                if args.json:
                    print(json.dumps({"claude": c_status, "codex": x_status}, indent=2))
                else:
                    print("[Claude Code]")
                    print("Logged In:     %s" % c_status.get("loggedIn"))
                    print("Active Email:  %s" % c_status.get("email"))
                    print("Organization:  %s (%s)" % (c_status.get("orgName"), c_status.get("orgId")))
                    print("Subscription:  %s" % c_status.get("subscriptionType"))
                    print("\n[OpenAI Codex]")
                    print("Logged In:     %s" % x_status.get("loggedIn"))
                    print("Active Email:  %s" % (x_status.get("email") or "-"))
                    print("Plan Type:     %s" % (x_status.get("planType") or "-"))
                    print("Account ID:    %s" % (x_status.get("accountId") or "-"))
                    print("Token Fresh:   %s" % x_status.get("tokenFresh"))
            else:
                status = pm.get_claude_auth_status()
                if args.json:
                    print(json.dumps(status, indent=2))
                else:
                    print("Logged In:     %s" % status.get("loggedIn"))
                    print("Active Email:  %s" % status.get("email"))
                    print("Organization:  %s (%s)" % (status.get("orgName"), status.get("orgId")))
                    print("Subscription:  %s" % status.get("subscriptionType"))
        elif args.command == "usage":
            if args.provider == "codex":
                _print_codex_usage(pm.fetch_codex_usage(force=args.force), args.json)
            elif args.provider == "all":
                if args.json:
                    print(json.dumps({
                        "claude": pm.fetch_all_usage(force_refresh=args.force),
                        "codex": pm.fetch_codex_usage(force=args.force),
                    }, indent=2))
                else:
                    print("[Claude Code Usage]")
                    _print_claude_usage(pm, pm.fetch_all_usage(force_refresh=args.force), False)
                    print("\n[OpenAI Codex Usage]")
                    _print_codex_usage(pm.fetch_codex_usage(force=args.force), False)
            else:
                _print_claude_usage(pm, pm.fetch_all_usage(force_refresh=args.force), args.json)
        elif args.command == "balance":
            if args.provider == "codex":
                if args.auto:
                    res = pm.run_auto_until_settled(reason=args.reason, signal=args.signal, provider="codex")
                else:
                    res = pm.evaluate_codex_balance(threshold=args.threshold, dry_run=args.dry_run, reason=args.reason)
                if args.json:
                    print(json.dumps(res, indent=2))
                else:
                    act = res.get("action")
                    if act == "switched":
                        print("Balanced Codex: switched %s -> %s (%s)" % (res.get("previous"), res.get("active"), res.get("reason")))
                    elif act == "would_switch":
                        print("Would switch Codex %s -> %s (%s)" % (res.get("previous"), res.get("target"), res.get("reason")))
                    else:
                        print("Codex balanced: %s" % res.get("reason"))
            elif args.provider == "all":
                if args.auto:
                    res = pm.run_auto_until_settled(reason=args.reason, signal=args.signal, provider="all")
                    if args.json:
                        print(json.dumps(res, indent=2))
                    else:
                        c_res = res.get("claude", {}) if isinstance(res, dict) else {}
                        x_res = res.get("codex", {}) if isinstance(res, dict) else {}
                        print("[Claude Code] action=%s reason=%s" % (c_res.get("action"), c_res.get("reason")))
                        print("[OpenAI Codex] action=%s reason=%s" % (x_res.get("action"), x_res.get("reason")))
                else:
                    c_res = pm.balance_accounts(threshold=args.threshold, dry_run=args.dry_run, verbose=not args.json,
                                                source="manual_balance", signal=args.signal)
                    x_res = pm.evaluate_codex_balance(threshold=args.threshold, dry_run=args.dry_run, reason=args.reason)
                    if args.json:
                        print(json.dumps({"claude": c_res, "codex": x_res}, indent=2))
                    else:
                        print("[Claude Code Balance]")
                        c_act = c_res.get("action")
                        if c_act == "switched":
                            print("Balanced Claude: switched %s -> %s (%s)" % (c_res.get("fromAccount"), c_res.get("toAccount"), c_res.get("reason")))
                        elif c_act == "would_switch":
                            print("Would switch Claude: %s -> %s (%s)" % (c_res.get("fromAccount"), c_res.get("toAccount"), c_res.get("reason")))
                        else:
                            print("Claude balanced: %s" % c_res.get("reason"))

                        print("\n[OpenAI Codex Balance]")
                        x_act = x_res.get("action")
                        if x_act == "switched":
                            print("Balanced Codex: switched %s -> %s (%s)" % (x_res.get("previous"), x_res.get("active"), x_res.get("reason")))
                        elif x_act == "would_switch":
                            print("Would switch Codex %s -> %s (%s)" % (x_res.get("previous"), x_res.get("target"), x_res.get("reason")))
                        else:
                            print("Codex balanced: %s" % x_res.get("reason"))
            else:
                if args.auto:
                    res = pm.run_auto_until_settled(reason=args.reason, signal=args.signal, provider="claude")
                else:
                    res = pm.balance_accounts(threshold=args.threshold, dry_run=args.dry_run, verbose=not args.json,
                                           source="manual_balance", signal=args.signal)
                if args.json:
                    print(json.dumps(res, indent=2))
                else:
                    action = res.get("action")
                    if action == "switched":
                        print("Balanced: switched %s -> %s (%s)" % (res.get("fromAccount"), res.get("toAccount"), res.get("reason")))
                    elif action == "would_switch":
                        print("Would switch %s -> %s (%s)" % (res.get("fromAccount"), res.get("toAccount"), res.get("reason")))
                    else:
                        print("No switch: %s%s" % (res.get("reason"), (" — " + res["error"]) if res.get("error") else ""))
        elif args.command == "switch":
            if args.provider == "codex":
                res = pm.switch_codex_account(args.account, force=args.force)
                if args.json:
                    print(json.dumps(res, indent=2))
                elif res.get("status") == "already_active":
                    print("%s is already the active Codex account." % res.get("account"))
                else:
                    print("Switched Codex to %s (ID: %s)%s" % (
                        res.get("active"),
                        res.get("id"),
                        f"; saved previous tokens for {res.get('previous')}" if res.get("previous") else ""
                    ))
            else:
                res = pm.switch_account(args.account, force=args.force)
                if args.json:
                    print(json.dumps(res, indent=2))
                elif res.get("alreadyActive"):
                    print("%s is already the active account." % res["switchedTo"])
                else:
                    print("Switched to %s (ID: %s)%s" % (res["switchedTo"], res["accountId"],
                                                          "; saved the outgoing account's live tokens" if res.get("wroteBack") else ""))
        elif args.command == "login-headless":
            if getattr(args, "provider", "claude") == "codex":
                res = pm.login_codex_headless(email=args.email, space=args.space, repair_home=args.repair_home)
                if res.get("repairedHome") and not args.json:
                    print("Repaired confirmed-revoked Codex home %s; native history and session pins retained." % res["repairedHome"])
                else:
                    print(json.dumps(res, indent=2) if args.json else "Logged in Codex %s (Arc space %s); %s." % (
                        res["email"], res.get("space"), "new sessions now use it" if res.get("activated")
                        else "home saved, new sessions stay on %s (switch to select it)" % res.get("active")))
            else:
                res = pm.login_headless(email=args.email, browser=args.browser, profile=args.profile, force=args.force)
                print(json.dumps(res, indent=2) if args.json else "Logged in %s (no switch)." % res["email"])
        elif args.command == "rotate":
            res = pm.rotate_account(reason=args.reason, dry_run=args.dry_run, force=args.force)
            if args.json:
                print(json.dumps(res, indent=2))
            elif res.get("dryRun"):
                print("Dry run: would rotate %s -> %s" % (res.get("currentAccount"), res.get("nextAccount")))
            elif res.get("success"):
                print("Rotated %s -> %s" % (res.get("rotatedFrom"), res.get("rotatedTo")))
            else:
                print("No rotation: %s" % res.get("error"))
        elif args.command == "history":
            kinds = None if args.all else ["switch"]
            events = pm.read_provider_events(limit=args.limit, kinds=kinds)
            if args.json:
                print(json.dumps(events, indent=2))
            elif not events:
                print("No provider events recorded yet.")
            else:
                print("%-20s %-22s %-26s %-26s %s" % ("TIMESTAMP (UTC)", "EVENT/SOURCE", "FROM", "TO", "DETAILS"))
                for ev in reversed(events):
                    label = ev.get("source") if ev.get("event") == "switch" else ev.get("event")
                    detail = ev.get("reason") or ""
                    if ev.get("activeUtilization") is not None and ev.get("standbyUtilization") is not None:
                        detail += " (%s%% -> %s%%)" % (ev.get("activeUtilization"), ev.get("standbyUtilization"))
                    print("%-20s %-22s %-26s %-26s %s" % (ev.get("iso"), label, ev.get("fromAccount") or "-",
                                                          ev.get("toAccount") or "-", detail))
        elif args.command == "stalled":
            cmd_stalled(pm, args.hours, args.json)
        elif args.command == "hold":
            until = 0.0 if args.clear else time.time() + args.minutes * 60
            pm.update_state(lambda s: s.__setitem__("holdUntil", until))
            pm.log_provider_event("hold", {"until": int(until)})
            print(json.dumps({"holdUntil": until}) if args.json else
                  ("Hold cleared." if args.clear else "Automatic switching held for %g minutes." % args.minutes))
        elif args.command == "state":
            st = pm.load_state()
            st["lockHolder"] = pm_state.lock_holder(pm.BALANCER_LOCK_PATH)
            st["config"] = pm.load_config()
            verified, version = pm.version_verified(st["config"])
            st["versionGate"] = {"claudeVersion": version, "automaticSwitching": "on" if verified else "paused"}
            st.pop("storeIdentity", None)
            st["claudeTelemetry"] = pm.telemetry_summary(st)
            print(json.dumps(st, indent=2))
    except Exception as e:  # noqa: BLE001 - the CLI reports, it does not trace
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            sys.stderr.write("Error: %s\n" % e)
        sys.exit(1)
