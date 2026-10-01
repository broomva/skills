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
    ("an unseen batch shown every tick", "scripts/fleet_reconcile.py",
     "        if len(shows) <= 1 or now - last >= reshow_s:", "        if True:",
     [T + "test_report.py", "-k", "unseen_batch"]),
    ("a Seen click does not stop the dialog", "scripts/fleet_reconcile.py",
     'if b["seen"] or not any(v["of"] == b["id"] for v in open_keys.values()):',
     'if not any(v["of"] == b["id"] for v in open_keys.values()):', [T + "test_report.py", "-k", "unseen_batch"]),
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
    ("a failed tick exits 0", TICK, '  alert tick "tick $N failed at $FAILED ($RCS)"\n  exit 1',
     '  alert tick "tick $N failed at $FAILED ($RCS)"\n  exit 0', [T + "test_tick.py", "-k", "failed_step"]),
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
    ("a repo that left the scope keeps its ask", REP, "        return all(r.get(\"slug\") for r in rep[\"repos\"])",
     "        return False", [T + "test_report.py", "-k", "surfaces_that_raise"]),
    ("a repo with no slug read counts as gone", REP, "        return all(r.get(\"slug\") for r in rep[\"repos\"])",
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
    ("a wait's key moved by activity", REP,
     '_tag(s["evidence"])), "3",', '_tag("%s|%s" % (s["evidence"], s["activity_age_s"]))), "3",',
     [T + "test_report.py", "-k", "subagents_keep_writing"]),
    ("activity read from the first window only", "../ctx-core/scripts/ctx_compare.py",
     "TAIL_WINDOWS = (128 * 1024, 2 * 1024 * 1024, 16 * 1024 * 1024)", "TAIL_WINDOWS = (128 * 1024,)",
     [T + "test_observe.py", "-k", "larger_than"]),
    ("a dialog not shown counts as shown", "scripts/fleet_reconcile.py",
     '    if res.get("error"):\n        # Not shown', '    if False:\n        # Not shown',
     [T + "test_tick.py", "-k", "cannot_be_shown"]),
    ("p9 hourly when the dialog fails", "scripts/fleet_reconcile.py", "    res = show_dialog(title, text)\n",
     '    res = show_dialog(title, text)\n    p9_notify(title, "n open")\n',
     [T + "test_tick.py", "-k", "cannot_be_shown"]),
    ("the dialog defaults to Seen", "scripts/fleet_reconcile.py", 'default button "Later"', 'default button "Seen"',
     [T + "test_tick.py", "-k", "defaults_to_later"]),
    ("the dialog leads with the oldest batch", "scripts/fleet_reconcile.py", "    newest = due[-1]\n",
     "    newest = due[0]\n", [T + "test_tick.py", "-k", "defaults_to_later"]),
    ("a refused compare is silent", REP, '    if cmp_.get("refused"):  # one key', "    if False:  # one key",
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
