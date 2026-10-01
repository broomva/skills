#!/usr/bin/env python3
"""Mutation check: break each rule and each protection in turn; a test must fail.

- Every rule of the class table is deleted, one at a time.
- Every pair of rules that can both match (test_classify.PAIRS) is swapped.
  The other pairs can't both match (test_classify.EXCLUSIVE, which a grid test
  checks), so swapping them is an equivalent mutant and is not run.
- Each protection below is removed: the listing and PR-list caps, a failed
  slug reading as zero, the bearer and env never extracted, activity read from
  transcripts only, the arc and death currency rules, the ask suppression and
  re-notify windows, the text guard, and in tick.sh the recursion guard, the
  kill switch, dry-falls-toward-dry and the token's export; plus one per P20
  round-1 finding (the job time, the cap cross-check, degraded surfaces, the
  unknown branch, ack-through, per-key asks, token scoping, a failed tick's
  exit, the process-group kill, tick numbering) and per round-3 fix (where a
  key may resolve, the wait's key, the tail windows, the dialog's default,
  line and failure, the lock before an alert, the token file's mode, the held
  lock, the compare's day and refusal, owner ids).

Each mutant edits a scratch copy of this skill (and ctx-core beside it) and
runs the tests that pin it. Exit 1 on a survivor, a stale anchor, or an error.

    python3 tests/mutation_check.py [--quick]   (--quick: rules only)
"""
import ast
import pathlib
import shutil
import subprocess
import sys
import tempfile

SKILL = pathlib.Path(__file__).resolve().parents[1]
CLS, OBS, PAR, REP, COM, TICK = ("scripts/fleetlib/classify.py", "scripts/fleetlib/observe.py",
                                 "scripts/fleetlib/parsers.py", "scripts/fleetlib/report.py",
                                 "scripts/fleetlib/common.py", "scripts/tick.sh")
ACT = "scripts/fleetlib/act.py"
T = "tests/"

PROTECTIONS = [
    ("listing cap not enforced", OBS, "        if at_cap and not proven:", "        if False:",
     [T + "test_observe.py", "-k", "cap"]),
    ("PR list cap not enforced", OBS, 'if len(prs) >= sec["pr_list_cap"]:', "if False:",
     [T + "test_observe.py", "-k", "pr_list_at_the_cap"]),
    ("a failed slug reads as zero PRs", OBS,
     '        out["error"] = "origin remote is not a GitHub slug"\n        return out',
     '        out["ok"], out["prs"] = True, []\n        return out',
     [T + "test_observe.py", "-k", "slug"]),
    ("the Paseo record kept whole", PAR, '        "has_error": bool(d.get("lastError")),',
     '        "has_error": bool(d.get("lastError")), "raw": d,', [T + "test_parsers.py", "-k", "bearer"]),
    ("the job env kept", PAR, '        "settings_path": settings_path,',
     '        "settings_path": settings_path, "env": d.get("providerEnv"),',
     [T + "test_parsers.py", "-k", "never_carries"]),
    ("activity read from the mtime", CLS, '    v = (s.get("transcript") or {}).get("activity")',
     '    v = (s.get("transcript") or {}).get("mtime")', [T + "test_classify.py", "-k", "late_untimestamped"]),
    ("activity read from Paseo", CLS, '    v = (s.get("transcript") or {}).get("activity")',
     '    v = ((s.get("paseo") or {}).get("last_activity_at") or (s.get("transcript") or {}).get("activity"))',
     [T + "test_classify.py", "-k", "label_write"]),
    ("a later event does not retire an ARC-STATUS", CLS,
     '    if b.get("last_ts") is not None and b["arc_ts"] < b["last_ts"]:\n        return None\n', "",
     [T + "test_classify.py", "-k", "latest_word"]),
    ("a death is a death even after more work", CLS,
     "    return t is not None and a is not None and a > t + GRACE_S", "    return False",
     [T + "test_classify.py", "-k", "went_on_from"]),
    ("a question to the user counts as a prompt", CLS,
     'if s.get("status") == "waiting" and s.get("waiting_for") and not bg_question(s):',
     'if s.get("status") == "waiting" and s.get("waiting_for"):',
     [T + "test_classify.py", "-k", "question_to_its_user"]),
    ("a terminal status with unread PRs is closed", CLS,
     '        return Stop("ARC-STATUS %s, but the PRs of its repo could not be read" % arc)', "        pass",
     [T + "test_classify.py", "-k", "were_not_read"]),
    ("an ack does not hold while the condition lasts", "scripts/fleetlib/ledger.py",
     '                    v["state"] = "acked"', '                    v["state"] = "resolved"',
     [T + "test_report.py", "-k", "ack_holds"]),
    ("a resolved condition never closes its key", "scripts/fleetlib/ledger.py",
     '                if k in st and st[k]["state"] in ("open", "acked"):\n                    st[k]["state"] = "resolved"',
     '                if False:\n                    pass',
     [T + "test_report.py", "-k", "recurrence"]),
    ("ack allowed inside a session", "scripts/fleet_reconcile.py",
     '    if os.environ.get("FLEET_CHILD") or os.environ.get("CLAUDECODE"):', "    if False:",
     [T + "test_tick.py", "-k", "acks"]),
    ("no text guard", COM, '    if not ctx.guard_ok(flat) or _CRM.search(flat):\n        return WITHHELD\n', "",
     [T + "test_report.py", "-k", "withheld"]),
    ("no recursion guard", TICK, 'if [ -n "${FLEET_CHILD:-}" ]; then\n  exit 0\nfi\n', "",
     [T + "test_tick.py", "-k", "recursion"]),
    ("no kill switch", TICK, 'if [ "$KILL" != "1" ]; then', "if false; then", [T + "test_tick.py", "-k", "kill_switch"]),
    ("an env value makes a tick live", TICK, "  (*) DRY=1 ;;", "  (*) DRY=0 ;;",
     [T + "test_tick.py", "-k", "falls_toward_dry"]),
    ("the token not exported", TICK, 'if [ -n "$TOKEN" ]; then export GH_TOKEN="$TOKEN"; fi', ":",
     [T + "test_tick.py", "-k", "token_reaches"]),
    # P20 round 1 findings, each pinned
    ("a job's time read as epoch ms only", PAR, '        "updated_at": _epoch(d.get("updatedAt")),',
     '        "updated_at": (d["updatedAt"] / 1000.0) if type(d.get("updatedAt")) is int else None,',
     [T + "test_parsers.py", "-k", "update_time"]),
    ("a listing at the cap taken on faith", OBS,
     'proven = at_cap and surf["jobs"]["ok"] and bool(job_ids) and set(job_ids) <= listed', "proven = at_cap",
     [T + "test_observe.py", "-k", "cap"]),
    ("an unread surface degrades nothing", CLS,
     "            missing = _unread(s, env) if rule.id in ABSENCE_CLASSES else None", "            missing = None",
     [T + "test_classify.py", "-k", "unread"]),
    ("an unknown branch reads as closed", CLS,
     '    if not bid:\n', '    if False:\n',
     [T + "test_classify.py", "-k", "unknown_or_detached"]),
    ("an ack answers other batches' asks", "scripts/fleetlib/ledger.py",
     'if v["state"] == "open" and v["of"] == r.get("of") and \\', 'if v["state"] == "open" and \\',
     [T + "test_report.py", "-k", "own_batch"]),
    ("a batch every tick", REP, '        if v and v["state"] == "open":', "        if False:",
     [T + "test_report.py", "-k", "asked_once"]),
    ("the token reaches every child", "scripts/fleetlib/sources.py",
     "        _take_token()\n", "        pass\n", [T + "test_observe.py", "-k", "token_out_of"]),
    ("a TERM-proof child outlives its step", TICK,
     '  kill -KILL -- "-$STEP_PID" 2>/dev/null  # children that outlived their leader, TERM-proof ones included\n',
     "", [T + "test_tick.py", "-k", "watchdog"]),
    ("a lost counter reuses a tick number", "scripts/fleet_reconcile.py",
     "    n = max(n, ledger.last_tick(records) or 0) + 1", "    n = n + 1",
     [T + "test_tick.py", "-k", "lost_counter"]),
    # P20 round 3 findings, each pinned
    ("an ask resolved from a surface not read", REP,
     'k not in now_true and observed(k, rep))', "k not in now_true)",
     [T + "test_report.py", "-k", "surfaces_that_raise"]),
    ("an unknown session's asks resolved", REP,
     ' or (row is not None and row["class"] == "unknown"):', ":",
     [T + "test_report.py", "-k", "surfaces_that_raise"]),
    ("drift resolved from the listing alone", REP, 'return ok("claude_version", "jobs", "listing")',
     'return ok("listing")', [T + "test_report.py", "-k", "surfaces_that_raise"]),
    ("a repo that left the scope keeps its ask", REP, "        return all(r.get(\"slug\") or (r.get(\"error\") or \"\").startswith(NOT_GITHUB) for r in rep[\"repos\"])",
     "        return False", [T + "test_report.py", "-k", "surfaces_that_raise"]),
    ("a repo with no slug read counts as gone", REP, "        return all(r.get(\"slug\") or (r.get(\"error\") or \"\").startswith(NOT_GITHUB) for r in rep[\"repos\"])",
     "        return True", [T + "test_report.py", "-k", "surfaces_that_raise"]),
    ("a blocked key resolved with the board unread", REP, "        return board and (", "        return True or (",
     [T + "test_report.py", "-k", "still_classifies"]),
    ("an interactive blocked key waits on the job files", REP, 'return board and (row["kind"] != "background" or ok("jobs"))',
     'return board and ok("jobs")', [T + "test_report.py", "-k", "still_classifies"]),
    ("a prompt resolved with the listing unread", REP,
     '        if not ok("listing") or (row is not None', '        if (row is not None',
     [T + "test_report.py", "-k", "still_classifies"]),
    ("records resolved with the Paseo records unread", REP, 'return ok("listing", "paseo_records")',
     'return ok("listing")', [T + "test_report.py", "-k", "still_classifies"]),
    ("an unchecked open ask goes unlisted", REP, "if k not in skip]", "if False]",
     [T + "test_report.py", "-k", "still_listed"]),
    ("a failing comparison is never asked about", REP,
     '    elif "error" in cmp_ and (cmp_.get("failed_in_a_row") or 0) >= COMPARE_FAILS_TO_ASK:', "    elif False:",
     [T + "test_report.py", "-k", "three_runs"]),
    ("a tail drops a line it starts on", COM, "fh.seek(max(0, start - 1))", "fh.seek(start)",
     [T + "test_observe.py", "-k", "starts_exactly"]),
    ("a non-GitHub origin blocks a departed repo's resolution", REP,
     'all(r.get("slug") or (r.get("error") or "").startswith(NOT_GITHUB) for r in rep["repos"])',
     'all(r.get("slug") for r in rep["repos"])', [T + "test_report.py", "-k", "surfaces_that_raise"]),
    ("one compare key for both owner steps", REP, '"prototype": "move", "unreadable": "move"',
     '"prototype": "register", "unreadable": "register"', [T + "test_report.py", "-k", "three_runs"]),
    ("report.json keeps the compare error raw", REP, "        return dict(compare, error=common.safe_text(compare[\"error\"], 200))",
     "        return compare", [T + "test_report.py", "-k", "three_runs"]),
    # Phase 2: the verbs' floor, the send gate, recover, the coordinator's posture, the profile, the janitor
    ("report mode lets a verb act", ACT, '        if self.sec["mode"] != "act":\n            raise ModeRefused',
     '        if False:\n            raise ModeRefused', [T + "test_act.py", "-k", "report_mode"]),
    ("arguments checked before the mode", "scripts/fleet_reconcile.py",
     '    if sec["mode"] != "act":  # before anything else, arguments included', "    if False:",
     [T + "test_tick.py", "-k", "acks_asks"]),
    ("a corrupt ledger doesn't stop mail and spawn", ACT, 'if self.corrupt and verb in ("mail", "spawn"):', "if False:",
     [T + "test_act.py", "-k", "corrupt"]),
    ("an open ask doesn't stop the verb", ACT, "            if any(n and n in k for n in needles):",
     "            if False:", [T + "test_act.py", "-k", "unanswered_ask"]),
    ("a held PR gets a driver", ACT, 'if any(lb.lower() == HOLD_LABEL for lb in pr["labels"]):', "if False:",
     [T + "test_act.py", "-k", "instructing"]),
    ("a draft gets a driver", ACT, '        if pr["draft"]:\n', "        if False:\n",
     [T + "test_act.py", "-k", "held_draft"]),
    ("a Dependabot PR gets a driver", ACT, '        if pr["dependabot"]:\n', "        if False:\n",
     [T + "test_act.py", "-k", "held_draft"]),
    ("unread PR files read as none", ACT, "files = json.loads(self.src.pr_files(slug, number))", "files = []",
     [T + "test_act.py", "-k", "owner_merge"]),
    ("an unruled repo gets a driver", ACT, '        if not rules["driver_eligible"]:', "        if False:",
     [T + "test_act.py", "-k", "unruled"]),
    ("a taken name is spawned again", ACT, "        if taken:\n", "        if False:\n",
     [T + "test_act.py", "-k", "name_any"]),
    ("a checked-out branch gets a second driver", ACT, "        if holders:\n", "        if False:\n",
     [T + "test_act.py", "-k", "whole_observation"]),
    ("the fleet cap isn't kept", ACT, 'if len(fleet_live) >= caps["fleet_sessions"]:', "if False:",
     [T + "test_act.py", "-k", "whole_observation"]),
    ("adopted sessions count toward the fleet cap", ACT, '        fleet_live = [s for s in snap["sessions"] if s.get("pid") is not None and s.get("fleet_key")\n                      and not s.get("adopted")]',
     '        fleet_live = [s for s in snap["sessions"] if s.get("pid") is not None and s.get("fleet_key")]',
     [T + "test_act.py", "-k", "eight_adopted"]),
    ("the active cap isn't kept", ACT, 'if len(active) > caps["active_sessions"]:', "if False:",
     [T + "test_act.py", "-k", "whole_observation"]),
    ("unknown claims don't block", ACT, "            if unknown:\n", "            if False:\n",
     [T + "test_act.py", "-k", "whole_observation"]),
    ("the spawn pause is ignored", ACT, '        if pause and pause["active"]:', "        if False:",
     [T + "test_act.py", "-k", "spawn_pause"]),
    ("a dry spawn runs claude", ACT, '        if self.dry:\n            return self._done(it, {"would": True, "argv": argv[:-1]',
     '        if False:\n            return self._done(it, {"would": True, "argv": argv[:-1]',
     [T + "test_act.py", "-k", "dry_spawn"]),
    ("mail reaches any session", ACT,
     '            if who is None:\n                raise Refused("ineligible", "session %s is neither a fleet spawn in the ledger nor adopted in the "',
     '            if False:\n                raise Refused("ineligible", "session %s is neither a fleet spawn in the ledger nor adopted in the "',
     [T + "test_act.py", "-k", "reaches_only"]),
    ("act mail skips the 6 h rule", ACT, '            if prior:\n                raise Refused("ineligible", "a mail to',
     '            if False:\n                raise Refused("ineligible", "a mail to', [T + "test_act.py", "-k", "six_hour"]),
    ("a failed mail counts toward the 6 h rule", "scripts/fleetlib/ledger.py",
     'if out is None or out["kind"] in ("done", "unknown"):', "if True:", [T + "test_act.py", "-k", "six_hour"]),
    ("live and dry mail counted together", "scripts/fleetlib/ledger.py",
     'if bool(r.get("dry_run")) != dry or (r.get("target") or {}).get("recipient") != recipient:',
     'if (r.get("target") or {}).get("recipient") != recipient:', [T + "test_act.py", "-k", "six_hour"]),
    ("a shared name is mailed", ACT, "        if len(same) > 1:", "        if False:",
     [T + "test_act.py", "-k", "shared_name"]),
    ("a Paseo relaunch isn't followed", ACT, "        if row is None and agent_id:", "        if False:",
     [T + "test_act.py", "-k", "relaunch"]),
    ("a template value skips the guard", ACT, "{k: common.safe_text(v, 200) for k, v in values.items()}",
     "{k: str(v) for k, v in values.items()}", [T + "test_act.py", "-k", "still_passes_the_text_guard"]),
    ("resume passes flags", ACT, 'argv = ["--bg", "--resume", sid]', 'argv = ["--bg", "--resume", sid, "--name", "x"]',
     [T + "test_act.py", "-k", "dry_resume"]),
    ("a second resume while one is unconfirmed", ACT, '            if pending:\n                raise Refused("ineligible", "a resume of it',
     '            if False:\n                raise Refused("ineligible", "a resume of it',
     [T + "test_act.py", "-k", "unconfirmed"]),
    ("a background session with a process is resumed", ACT,
     '        if row["pid"] is not None:\n            raise Refused("ineligible", "%s has a live process',
     '        if False:\n            raise Refused("ineligible", "%s has a live process',
     [T + "test_act.py", "-k", "unconfirmed"]),
    ("the gate passes a send with no intent", "scripts/fleetlib/sendgate.py",
     '    if not found:\n        return refuse("no matching intent:', '    if False:\n        return refuse("no matching intent:',
     [T + "test_sendgate.py", "-k", "without_a_matching"]),
    ("the gate passes a recipient no longer ours", "scripts/fleetlib/sendgate.py",
     '    if it["key"] not in {v["key"] for v in act.ours().values()}:', "    if False:",
     [T + "test_sendgate.py", "-k", "no_longer_adopted"]),
    ("the gate skips the 6 h rule", "scripts/fleetlib/sendgate.py", '    if prior:\n        return refuse("a second mail',
     '    if False:\n        return refuse("a second mail', [T + "test_sendgate.py", "-k", "six_hours"]),
    ("the gate skips the name check", "scripts/fleetlib/sendgate.py",
     '    if len(live) != 1 or live[0]["session_id"] != t["session_id"]:', "    if False:",
     [T + "test_sendgate.py", "-k", "no_longer_maps"]),
    ("a dry send goes out", "scripts/fleetlib/sendgate.py", '    if dry:\n        try:\n            ledger.append(sd, dict(base, kind="done"',
     '    if False:\n        try:\n            ledger.append(sd, dict(base, kind="done"', [T + "test_sendgate.py", "-k", "dry_send"]),
    ("an unledgered send isn't recorded as such", "scripts/fleetlib/sendgate.py", 'reason="unledgered_send",',
     'reason="harness_refused",', [T + "test_sendgate.py", "-k", "unledgered"]),
    ("a duplicate spawn reads as one", "scripts/fleetlib/recover.py", '"session_ids": ids, "duplicate": True}',
     '"session_ids": ids, "session_id": ids[0]}', [T + "test_recover.py", "-k", "flagged_with_two"]),
    ("resume recovered from an older process", "scripts/fleetlib/recover.py",
     "if started is not None and started >= since:", "if started is not None:", [T + "test_recover.py", "-k", "resume"]),
    ("a tick doesn't recover", TICK, 'step recover "$FLEET" recover --scope "$SCOPE" --tick "$N"; RCS="recover=$RC"',
     'RC=0; RCS="recover=$RC"', [T + "test_tick.py", "-k", "dead_tick"]),
    ("the prompt follows the disallowed list with no --", "scripts/fleetlib/coordinator.py",
     '    return out + ["--", prompt]', "    return out + [prompt]", [T + "test_coordinator.py", "-k", "double_dash"]),
    ("Paseo writes aren't disallowed", "scripts/fleetlib/coordinator.py",
     '[PASEO_PREFIX + t for t in sec["paseo_tools"]["write"]]', "[]", [T + "test_coordinator.py", "-k", "double_dash"]),
    ("an unclassified Paseo tool passes", "scripts/fleetlib/coordinator.py", "        elif name not in read:",
     "        elif False:", [T + "test_coordinator.py", "-k", "posture"]),
    ("a failing posture isn't stopped", "scripts/fleetlib/coordinator.py",
     '            if res["posture"]:\n                _stop(proc)', '            if False:\n                _stop(proc)',
     [T + "test_coordinator.py", "-k", "terminates"]),
    ("the coordinator runs in report mode", TICK, 'if [ "$MODE" = "act" ] && [ -z "$FAILED" ]; then',
     'if [ -z "$FAILED" ]; then', [T + "test_tick.py", "-k", "no_coordinator_runs"]),
    ("a session's variables reach a fleet child", "scripts/fleetlib/sources.py",
     "    env = {k: v for k, v in os.environ.items() if k in CHILD_KEEP or not k.startswith(CHILD_DROP)}",
     "    env = dict(os.environ)",
     [T + "test_coordinator.py", "-k", "no_session_variables"]),
    ("the profile doesn't hide gh's config", "scripts/fleetlib/profile.py",
     'DENY_READ = ["~/.config/gh", "~/.paseo", KEYCHAIN]', 'DENY_READ = ["~/.paseo", KEYCHAIN]',
     [T + "test_coordinator.py", "-k", "probe_6"]),
    ("the profile allows settings edits", "scripts/fleetlib/profile.py", ', "Edit(**/.claude/settings*.json)"]', "]",
     [T + "test_coordinator.py", "-k", "probe_6"]),
    ("the allowlist isn't strict", "scripts/fleetlib/profile.py", '"strictAllowlist": True', '"strictAllowlist": False',
     [T + "test_coordinator.py", "-k", "probe_6"]),
    ("a driver uses a token file open to others", "scripts/fleetlib/profile.py",
     "        if stat.S_IMODE(st.st_mode) not in (0o600, 0o400):", "        if False:",
     [T + "test_coordinator.py", "-k", "0600"]),
    ("the profile is written readable by others", "scripts/fleetlib/profile.py", "        os.fchmod(fd, 0o600)",
     "        os.fchmod(fd, 0o644)", [T + "test_coordinator.py", "-k", "0600"]),
    ("the CLI prints the token", "scripts/fleet_reconcile.py",
     '    shown["env"]["GH_TOKEN"] = "[withheld: %s]" % (',
     '    shown["env"]["GH_TOKEN"] = (token or "") + "[withheld: %s]" % (',
     [T + "test_coordinator.py", "-k", "never_prints"]),
    ("a listing showing only the janitor counts as read", "scripts/fleetlib/janitor.py",
     "        if not set(parents) - own:", "        if False:",
     [T + "test_janitor.py", "-k", "only_the_janitors"]),
    ("a check that didn't run doesn't abort", "scripts/fleetlib/janitor.py", '"ok": not fails and not blind,',
     '"ok": not fails,', [T + "test_janitor.py", "-k", "only_the_janitors"]),
    ("a holder is ignored", "scripts/fleetlib/janitor.py", '        if holders:\n            return "fail", "held by',
     '        if False:\n            return "fail", "held by', [T + "test_janitor.py", "-k", "holding"]),
    ("a recent file is ignored", "scripts/fleetlib/janitor.py", "        if newest:\n", "        if False:\n",
     [T + "test_janitor.py", "-k", "modified_in_the_last"]),
    ("a secret it can't read is ignored", "scripts/fleetlib/janitor.py",
     '        if bad:\n            return "fail", "can\'t back up', '        if False:\n            return "fail", "can\'t back up',
     [T + "test_janitor.py", "-k", "cant_read"]),
    ("another live session in the worktree is ignored", "scripts/fleetlib/janitor.py",
     '        if live:\n            return "fail", "live in the worktree', '        if False:\n            return "fail", "live in the worktree',
     [T + "test_janitor.py", "-k", "another_live"]),
    ("a running owner counts as finished", "scripts/fleetlib/janitor.py",
     '        if row["kind"] == "background" and row["state"] == "done":', '        if row["kind"] == "background":',
     [T + "test_janitor.py", "-k", "must_have_finished"]),
    ("a scope repo's worktree is removed", "scripts/fleetlib/janitor.py", "    if not scratch(g.path):", "    if False:",
     [T + "test_janitor.py", "-k", "scope_repos"]),
    # P20 round 1 on phase 2, each pinned
    ("the gate fails open on an error", "scripts/fleet_reconcile.py",
     "type(exc).__name__, common.safe_text(exc, 120)), file=sys.stderr)\n        return 2",
     "type(exc).__name__, common.safe_text(exc, 120)), file=sys.stderr)\n        return 1",
     [T + "test_sendgate.py", "-k", "fails_closed"]),
    ("a refusal it can't record lets the send through", "scripts/fleetlib/sendgate.py",
     "            check += \" (and the refusal couldn't be recorded: %s)\" % exc", "            return 0, \"\"",
     [T + "test_sendgate.py", "-k", "cant_lock"]),
    ("no success reads as done", "scripts/fleetlib/sendgate.py", ' or resp.get("success") is False))', "))",
     [T + "test_sendgate.py", "-k", "no_success"]),
    ("template values are free text", ACT, '                if k not in TEMPLATE_VARS or not TEMPLATE_VARS[k].match(v or ""):',
     "                if False:", [T + "test_act.py", "-k", "fixed_shapes"]),
    ("a live label runs on the keyring", ACT, "            if not self.dry and not profile.read_token(self.sec):",
     "            if False:", [T + "test_act.py", "-k", "live_label"]),
    ("a spawn while one is unconfirmed", ACT, '            if pending:\n                raise Refused("ineligible", "a spawn of',
     '            if False:\n                raise Refused("ineligible", "a spawn of',
     [T + "test_act.py", "-k", "spawn_is_refused_while"]),
    ("an unread surface passes a spawn", ACT, "            if not (surf.get(name) or {}).get(\"ok\"):", "            if False:",
     [T + "test_act.py", "-k", "whole_observation"]),
    ("an unread board passes a spawn", ACT, '        if bad:\n            raise Refused("ineligible", "the board of',
     '        if False:\n            raise Refused("ineligible", "the board of', [T + "test_act.py", "-k", "whole_observation"]),
    ("names read from the guarded snapshot", ACT, '        named = rows if rows is not None else snap["sessions"]',
     '        named = snap["sessions"]', [T + "test_act.py", "-k", "read_raw"]),
    ("a lagging listing loses the spawn", ACT,
     'return self._done(it, dict({"job_id": m.group(1)}, **({"session_id": sid} if sid else {})))',
     'return self._failed(it, "spawn_error", "no session row")', [T + "test_act.py", "-k", "listing_lags"]),
    ("a job id isn't ours", "scripts/fleetlib/ledger.py",
     'ids = list(ids) + ([res["job_id"]] if isinstance(res.get("job_id"), str) and not ids else [])', "ids = list(ids)",
     [T + "test_act.py", "-k", "listing_lags"]),
    ("the coordinator escapes the watchdog's group", "scripts/fleetlib/coordinator.py",
     "                                env=child_env(extra))", "                                env=child_env(extra), start_new_session=True)",
     [T + "test_coordinator.py", "-k", "watchdogs"]),
    ("an event before the init event passes", "scripts/fleetlib/coordinator.py", "            elif _acts(line):",
     "            elif False:", [T + "test_coordinator.py", "-k", "before_its_init"]),
    ("no init deadline", "scripts/fleetlib/coordinator.py", "    timer.start()", "    pass",
     [T + "test_coordinator.py", "-k", "no_init_event"]),
    ("NotebookEdit allowed", "scripts/fleetlib/coordinator.py", 'DISALLOWED = ("Agent", "Edit", "Write", "NotebookEdit")',
     'DISALLOWED = ("Agent", "Edit", "Write")', [T + "test_coordinator.py", "-k", "double_dash"]),
    ("the coordinator loads MCP servers", "scripts/fleetlib/coordinator.py", '"--strict-mcp-config", "--max-budget-usd"',
     '"--max-budget-usd"', [T + "test_coordinator.py", "-k", "double_dash"]),
    ("the janitor removes a worktree its owner doesn't own", "scripts/fleetlib/janitor.py",
     '    if row is None or not _inside(row["cwd"], g.path):', "    if row is None:", [T + "test_janitor.py", "-k", "must_own"]),
    ("a scope repo's owner finished by the listing", "scripts/fleetlib/janitor.py",
     '        if not scratch(self.path):\n            return "fail", "no board row', '        if False:\n            return "fail", "no board row',
     [T + "test_janitor.py", "-k", "scope_repos"]),
    ("the janitor's ancestors count as other processes", "scripts/fleetlib/janitor.py",
     "    while p and p != 1 and p not in own:", "    while False:", [T + "test_janitor.py", "-k", "ancestors"]),
    ("an open PR on the branch passes", "scripts/fleetlib/janitor.py", "        if open_:\n", "        if False:\n",
     [T + "test_janitor.py", "-k", "open_pr"]),
    ("a live tick runs without the fleet token", TICK,
     'if [ "$MODE" = "act" ] && [ "$DRY" = "0" ] && [ -z "$TOKEN" ]; then', "if false; then",
     [T + "test_tick.py", "-k", "without_the_fleet_token"]),
    ("recover runs on the keyring", TICK,
     '# §5.7\'s order: the fleet token, then recover (its label check reads GitHub).\nif [ -n "$TOKEN" ]; then export GH_TOKEN="$TOKEN"; fi\n'
     'export FLEET_GH_AUTH="$GH_AUTH" FLEET_RELEASE="$RELEASE"\n'
     '# Intents a dead tick left open are closed first, from what happened (§5.7).\n'
     'step recover "$FLEET" recover --scope "$SCOPE" --tick "$N"; RCS="recover=$RC"\n',
     'step recover "$FLEET" recover --scope "$SCOPE" --tick "$N"; RCS="recover=$RC"\n'
     'if [ -n "$TOKEN" ]; then export GH_TOKEN="$TOKEN"; fi\n'
     'export FLEET_GH_AUTH="$GH_AUTH" FLEET_RELEASE="$RELEASE"\n',
     [T + "test_tick.py", "-k", "github_with_the_fleet_token"]),
    ("a failed tick exits 0", TICK, '  alert "tick-$FAILED" "tick $N failed at $FAILED ($RCS)"\n  exit 1',
     '  alert "tick-$FAILED" "tick $N failed at $FAILED ($RCS)"\n  exit 0', [T + "test_tick.py", "-k", "failed_step"]),
    ("an owner-merge PR gets a driver", ACT, "            if owner:\n                raise Refused",
     "            if False:\n                raise Refused", [T + "test_act.py", "-k", "owner_merge"]),
    ("mail recovered from text before the intent", "scripts/fleetlib/recover.py",
     "if ts is not None and ts >= since and text in _delivered(e):", "if ts is not None and text in _delivered(e):",
     [T + "test_recover.py", "-k", "either_shape"]),
    ("the hold label is the coordinator's", ACT, "            if name.strip().lower() == HOLD_LABEL:",
     "            if False:", [T + "test_act.py", "-k", "hold_label_is"]),
    ("a secret in an ignored directory is missed", "scripts/fleetlib/janitor.py",
     "        if os.path.isdir(full) and not os.path.islink(full):", "        if False:",
     [T + "test_janitor.py", "-k", "ignored_directory"]),
    ("two backups at one instant collide", "scripts/fleetlib/janitor.py", "    while dest.exists():  # two backups",
     "    while False:  # two backups", [T + "test_janitor.py", "-k", "two_backups"]),
    # The owner channel on Paseo (owner decision 2026-10-01), and #258's carry-overs
    ("a raised batch is raised again", "scripts/fleet_reconcile.py", '        if b.get("item") or not asks:',
     "        if not asks:", [T + "test_tick.py", "-k", "raised_once"]),
    ("the owner's verdict isn't read back", "scripts/fleet_reconcile.py", '        if ans["verdict"] and new:',
     "        if False:", [T + "test_tick.py", "-k", "raised_once"]),
    ("an answer is recorded again every tick", "scripts/fleet_reconcile.py", '        if ans["verdict"] and new:',
     '        if ans["verdict"]:', [T + "test_paseo_ask.py", "-k", "recorded_once"]),
    ("a final answer keeps being read", "scripts/fleet_reconcile.py",
     '        if not b.get("item") or last.get("state") in FINAL or', '        if not b.get("item") or',
     [T + "test_paseo_ask.py", "-k", "recorded_once"]),
    ("the read-back window is unbounded", "scripts/fleet_reconcile.py",
     '(common.parse_iso(b["ts"]) or 0.0) < since:', "False:", [T + "test_paseo_ask.py", "-k", "read_window"]),
    ("a note after the asks resolved is lost", "scripts/fleet_reconcile.py",
     '    for b in ledger.ask_batches(records):\n        last = b.get("answer") or {}\n',
     '    open_of = {v["of"] for v in ledger.open_by_key(records).values()}\n'
     '    for b in ledger.ask_batches(records):\n        last = b.get("answer") or {}\n'
     '        if b["id"] not in open_of:\n            continue\n',
     [T + "test_paseo_ask.py", "-k", "stopped_being_true"]),
    ("a settled decision counts without taking effect", "scripts/fleetlib/paseo_ask.py",
     '            made = {"verdict": DECIDED[text], "note": note, "at": e.get("ts")}',
     '            out.append({"verdict": DECIDED[text], "note": note, "at": e.get("ts")})',
     [T + "test_paseo_ask.py", "-k", "took_effect"]),
    ("a chat line that reads like a decision counts", "scripts/fleetlib/paseo_ask.py",
     '        if kind == "gate.pending" and e.get("actor") == "human" and text in DECIDED:',
     "        if text in DECIDED:", [T + "test_paseo_ask.py", "-k", "took_effect"]),
    ("a send-back's note is lost after an approve", "scripts/fleetlib/paseo_ask.py",
     'for d in made if d["note"]]', 'for d in made[-1:] if d["note"]]', [T + "test_paseo_ask.py", "-k", "took_effect"]),
    ("done isn't an approval", "scripts/fleetlib/paseo_ask.py", '    if item.get("state") == "done":',
     "    if False:", [T + "test_paseo_ask.py", "-k", "took_effect"]),
    ("a cancel isn't an answer", "scripts/fleetlib/paseo_ask.py", '    elif item.get("state") == "canceled":',
     "    elif False:", [T + "test_paseo_ask.py", "-k", "took_effect"]),
    ("the asks go unfenced", "scripts/fleetlib/paseo_ask.py", '.replace(FENCE, "\'\'\'") for a in asks]',
     " for a in asks]", [T + "test_paseo_ask.py", "-k", "fenced"]),
    ("an orphan item is raised again", "scripts/fleet_reconcile.py",
     '            item = paseo_ask.find(sec, tag, since=asked) or paseo_ask.raise_item(sec, title, text)',
     "            item = paseo_ask.raise_item(sec, title, text)", [T + "test_tick.py", "-k", "adopted"]),
    ("a closed or older item is adopted", "scripts/fleetlib/paseo_ask.py",
     '        if it.get("state") in OPEN_STATES and (since is None or (made or 0.0) >= since - 60):',
     "        if True:", [T + "test_paseo_ask.py", "-k", "nothing_else"]),
    ("an item from before the batch is adopted", "scripts/fleetlib/paseo_ask.py",
     ' and (since is None or (made or 0.0) >= since - 60):', ":", [T + "test_paseo_ask.py", "-k", "nothing_else"]),
    ("a queued item is never dispatched", "scripts/fleet_reconcile.py",
     '            if item.get("state") == "proposed":  # queued', '            if False:  # queued',
     [T + "test_tick.py", "-k", "queued_at_maestros_cap_is_dispatched"]),
    ("a queued item is never dispatched later", "scripts/fleet_reconcile.py", '        if ans["state"] == "proposed":',
     "        if False:", [T + "test_paseo_ask.py", "-k", "refusal_at_the_cap"]),
    ("a refusal at the cap fails the tick", "scripts/fleet_reconcile.py",
     '                print("fleet act ask: Maestro item %s of tick %s is still queued',
     '                failed += 1\n                print("fleet act ask: Maestro item %s of tick %s is still queued',
     [T + "test_paseo_ask.py", "-k", "refusal_at_the_cap"]),
    ("a queued batch counts as seen", "scripts/fleetlib/ledger.py", '(maestro and res.get("state") != "proposed")',
     "maestro", [T + "test_paseo_ask.py", "-k", "refusal_at_the_cap"]),
    ("a batch is raised before its asks have lasted", "scripts/fleet_reconcile.py",
     '        if asked is not None and now - asked < sec.get("ask_raise_after_min", 50) * 60:', "        if False:",
     [T + "test_tick.py", "-k", "lasted"]),
    ("an alert is stamped before it's delivered", TICK,
     '  [ "${FLEET_NOTIFY:-}" = "0" ] && return 0\n  "$FLEET" alert',
     '  touch "$stamp"\n  [ "${FLEET_NOTIFY:-}" = "0" ] && return 0\n  "$FLEET" alert',
     [T + "test_tick.py", "-k", "maestro_is_back"]),
    ("a delivered alert isn't stamped", TICK, '    (0) touch "$stamp" ;;', "    (0) : ;;",
     [T + "test_tick.py", "-k", "kind_already_open"]),
    ("an alert queued at the cap is stamped", TICK, '    (4) log "ALERT $kind NOT delivered: queued',
     '    (4) touch "$stamp"; log "ALERT $kind NOT delivered: queued', [T + "test_tick.py", "-k", "queued_at_the_cap"]),
    ("an open alert of its kind is raised again", "scripts/fleetlib/paseo_ask.py", "    if open_one is not None:",
     "    if False:", [T + "test_tick.py", "-k", "kind_already_open"]),
    ("the bash fallback goes nowhere", TICK,
     '      if maestro_alert "fleet $SCOPE: $kind [fleet-reconcile $SCOPE alert $kind]" "$msg (tick.log: $LOG)"; then',
     "      if false; then", [T + "test_tick.py", "-k", "invalid_config"]),
    ("the bash fallback stamps a queued alert", TICK,
     "  case \"$out\" in (*'\"state\":\"proposed\"'*|*'\"state\": \"proposed\"'*) return 1 ;; esac\n", "",
     [T + "test_tick.py", "-k", "bash_fallback"]),
    ("maestro's failures pass as answers", "scripts/fleetlib/paseo_ask.py", "    if proc.returncode != 0:",
     "    if False:", [T + "test_paseo_ask.py", "-k", "failures_are_errors"]),
    ("ask runs go to whatever repo is current", "scripts/fleetlib/paseo_ask.py", '"--repo", ensure_repo(sec),',
     '"--repo", os.getcwd(),', [T + "test_paseo_ask.py", "-k", "fleets_own_repo"]),
    ("one alert stamp for every failure", TICK, '  alert "tick-$FAILED" "tick $N failed at $FAILED ($RCS)"',
     '  alert tick "tick $N failed at $FAILED ($RCS)"', [T + "test_tick.py", "-k", "failed_step"]),
    ("a profile is keyed by the re-read listing", "scripts/fleetlib/janitor.py",
     "if owner_sid in ids or owner_sid[:8] in ids", 'if row["session_id"] in ids or row["session_id"][:8] in ids',
     [T + "test_janitor.py", "-k", "left_the_listing"]),
    ("no tool allowlist", "scripts/fleetlib/coordinator.py", '    out += ["--tools"] + list(ALLOWED)\n', "",
     [T + "test_coordinator.py", "-k", "allowlist"]),
    ("a tool outside the allowlist passes", "scripts/fleetlib/coordinator.py",
     "            if t not in ALLOWED and t not in DISALLOWED and not t.startswith(PASEO_PREFIX)]", "            if False]",
     [T + "test_coordinator.py", "-k", "allowlist"]),
    ("no tool list passes", "scripts/fleetlib/coordinator.py",
     "    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):", "    if False:",
     [T + "test_coordinator.py", "-k", "allowlist"]),
    ("a late init event undoes the deadline", "scripts/fleetlib/coordinator.py",
     '                if res["init"] or res["posture"]:\n                    continue  # decided',
     '                if res["init"]:\n                    continue  # decided', [T + "test_coordinator.py", "-k", "late_init"]),
    ("the overlap template carries the coordinator's words", ACT, '            if template == "overlap":',
     "            if False:", [T + "test_act.py", "-k", "published_claims"]),
    ("the hold label passes in capitals", ACT, "            if name.strip().lower() == HOLD_LABEL:",
     "            if name.strip() == HOLD_LABEL:", [T + "test_act.py", "-k", "spelled"]),
    ("a resume doesn't wait for the listing", ACT, "        pid = self._poll_pid(sid)",
     '        pid = (next((r for r in self.listing() if r["session_id"] == sid), None) or {}).get("pid")',
     [T + "test_act.py", "-k", "waits_for_the_listing"]),
    ("PATH above the owner's worktree passes", "scripts/fleetlib/janitor.py",
     "        if top != g.path:\n            row = None", "        if False:\n            row = None",
     [T + "test_janitor.py", "-k", "not_a_directory_above"]),
    ("an unreadable repo is scratch", "scripts/fleetlib/janitor.py",
     '        return not os.path.exists(os.path.join(path, ".git"))', "        return True",
     [T + "test_janitor.py", "-k", "scratch_fails_closed"]),
    ("an ambiguous repo is scratch", "scripts/fleetlib/janitor.py",
     "    return where.common_dir not in ctx.load_scopes().by_repo",
     "    return ctx.load_scopes().by_repo.get(where.common_dir) is None", [T + "test_janitor.py", "-k", "scratch_fails_closed"]),
    ("dependency dirs are searched", "scripts/fleetlib/janitor.py",
     "            if os.path.basename(rel) in HEAVY_DIRS:\n                continue", "            if False:\n                continue",
     [T + "test_janitor.py", "-k", "dependency_dirs"]),
    ("a kept worktree counts as removed", "scripts/fleetlib/janitor.py", '    if not res["removed"]:  # claude rm keeps',
     '    if False:  # claude rm keeps', [T + "test_janitor.py", "-k", "claude_rm_keeps"]),
    ("a removed driver's profile stays", "scripts/fleetlib/janitor.py",
     '    for p in (sd / "profiles" / ("%s.json" % key), sd / "ghcfg" / key):', "    for p in ():",
     [T + "test_janitor.py", "-k", "claude_rm_keeps"]),
    ("a profile deleted by the listing's name", "scripts/fleetlib/janitor.py",
     '    for p in (sd / "profiles" / ("%s.json" % key), sd / "ghcfg" / key):',
     '    for p in (sd / "profiles" / ("%s.json" % row["name"]), sd / "ghcfg" / key):',
     [T + "test_janitor.py", "-k", "claude_rm_keeps"]),
    ("a corrupt ledger passes the gate", "scripts/fleetlib/sendgate.py", "    if corrupt:  # a corrupt line",
     "    if False:  # a corrupt line", [T + "test_sendgate.py", "-k", "corrupt_ledger_refuses"]),
    ("the shim lets a broken gate through", "scripts/fleet",
     '[ "${1:-}" = send-gate ] && [ "${2:-}" = pre ] && fail=2', ":", [T + "test_sendgate.py", "-k", "cant_start"]),
    ("a quote of the mail reads as delivered", "scripts/fleetlib/recover.py", " and text in _delivered(e):", ":",
     [T + "test_recover.py", "-k", "only_quotes"]),
    ("a partial Paseo classification passes", "scripts/fleetlib/config.py",
     'all(isinstance(v.get(k), list) and all(isinstance(t, str) for t in v[k]) for k in ("read", "write"))',
     'all(isinstance(v.get(k, []), list) for k in ("read", "write"))', [T + "test_coordinator.py", "-k", "partial_paseo"]),
    ("a fleet child loses its auth settings", "scripts/fleetlib/sources.py",
     'CHILD_KEEP = ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",', 'CHILD_KEEP = ("-", "-",',
     [T + "test_coordinator.py", "-k", "keeps_auth"]),
    ("a parent's messaging token reaches a fleet child", "scripts/fleetlib/sources.py",
     'CHILD_DROP = ("CLAUDECODE", "CLAUDE_CODE_", "PASEO_")',
     'CHILD_DROP = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "PASEO_")', [T + "test_coordinator.py", "-k", "keeps_auth"]),
    ("a duplicate fleet name never clears", REP, "names.count(n) > 1", "names.count(n) > 0",
     [T + "test_report.py", "-k", "duplicate_fleet_name"]),
    ("a duplicate spawn isn't asked", REP, '    for key in rep.get("spawn_duplicates") or []:', "    for key in []:",
     [T + "test_report.py", "-k", "duplicate_fleet_name"]),
    ("a wait's key moved by activity", REP,
     '_tag(s["evidence"])), "3",', '_tag("%s|%s" % (s["evidence"], s["activity_age_s"]))), "3",',
     [T + "test_report.py", "-k", "subagents_keep_writing"]),
    ("activity read from the first window only", "../ctx-core/scripts/ctx_compare.py",
     "TAIL_WINDOWS = (128 * 1024, 2 * 1024 * 1024, 16 * 1024 * 1024)", "TAIL_WINDOWS = (128 * 1024,)",
     [T + "test_observe.py", "-k", "larger_than"]),
    ("a refused compare is silent", REP, '    if cmp_.get("refused"):\n        # Keyed', "    if False:\n        # Keyed",
     [T + "test_tick.py", "-k", "failed_compare"]),
    ("the tick-number alert holds the lock", TICK,
     '(""|*[!0-9]*) trap - EXIT; release; alert tick', '(""|*[!0-9]*) alert tick',
     [T + "test_tick.py", "-k", "tick_number"]),
    ("a token file open to others is used", TICK,
     'if [ "$MODE" != "600" ] && [ "$MODE" != "400" ]; then', "if false; then",
     [T + "test_tick.py", "-k", "open_to_others"]),
    ("a lock held for hours is silent", TICK, "if [ $((NOW - MT)) -ge 7200 ]; then", "if false; then",
     [T + "test_tick.py", "-k", "two_hours"]),
    ("a failed compare uses up the day", "scripts/fleet_reconcile.py",
     'ran = [ln for ln in lines if "error" not in ln]', "ran = lines",
     [T + "test_tick.py", "-k", "failed_compare"]),
    ("two owner records share an id", "scripts/fleetlib/ledger.py",
     'while rec["id"] in taken:  # two owner', 'while False:  # two owner',
     [T + "test_ledger.py", "-k", "one_millisecond"]),
]


def _rule_lines(src: str):
    return [ln for ln in src.splitlines(keepends=True) if ln.startswith("    Rule(\"")]


def _rule_id(line: str) -> str:
    return line.split('"')[1]


def _pairs():
    tree = ast.parse((SKILL / "tests" / "test_classify.py").read_text())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_pair_cases":
            for elt in node.body[-1].value.elts:
                out.append((elt.elts[0].value, elt.elts[1].value))
    return out


def _run(root: pathlib.Path, args):
    return subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *args],
                          cwd=str(root / "fleet-reconcile"), capture_output=True, text=True, timeout=900)


def main() -> int:
    quick = "--quick" in sys.argv
    base = (SKILL / CLS).read_text()
    rules = _rule_lines(base)
    by_id = {_rule_id(ln): ln for ln in rules}
    mutants = []
    for ln in rules:
        mutants.append(("delete rule %s" % _rule_id(ln), CLS, ln, "", [T + "test_classify.py"]))
    for a, b in _pairs():
        la, lb = by_id[a], by_id[b]
        swapped = base.replace(la, "\0A").replace(lb, la).replace("\0A", lb)
        mutants.append(("swap rules %s and %s" % (a, b), CLS, base, swapped, [T + "test_classify.py"]))
    if not quick:
        mutants += PROTECTIONS
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache")
        for name in ("fleet-reconcile", "ctx-core"):
            shutil.copytree(str(SKILL.parent / name), str(root / name), ignore=ignore)
        for name, rel, old, new, args in mutants:
            path = root / "fleet-reconcile" / rel
            orig = path.read_text()
            if orig.count(old) != 1:
                print("STALE     %s (anchor found %d times in %s)" % (name, orig.count(old), rel))
                bad += 1
                continue
            path.write_text(orig.replace(old, new, 1))
            try:
                proc = _run(root, args)
            finally:
                path.write_text(orig)
            if proc.returncode == 0:
                print("SURVIVED  %s" % name)
                bad += 1
            elif proc.returncode == 1:
                print("killed    %s" % name)
            else:
                print("ERROR     %s (pytest exit %d)\n%s" % (name, proc.returncode, proc.stdout[-2000:]))
                bad += 1
    print("%d mutants, %d not killed" % (len(mutants), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
