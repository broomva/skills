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
  kill switch, dry-falls-toward-dry and the token's export.

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
    ("listing cap not enforced", OBS, 'if len(rows) >= sec["listing_cap"]:', "if False:",
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
    ("activity read from Paseo", CLS, 'vals = [v for v in (t.get("mtime"), t.get("sub")) if',
     'vals = [v for v in (t.get("mtime"), t.get("sub"), (s.get("paseo") or {}).get("last_activity_at")) if',
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
    ("an acked ask is asked again at once", REP, "ASK_SUPPRESS_S = 24 * 3600", "ASK_SUPPRESS_S = 0",
     [T + "test_report.py", "-k", "acked_ask"]),
    ("notified every tick", REP, "    if now - last >= renotify_h * 3600:", "    if True:",
     [T + "test_report.py", "-k", "renotify"]),
    ("no text guard", COM, '    if not ctx.guard_ok(flat) or _CRM.search(flat):\n        return WITHHELD\n', "",
     [T + "test_report.py", "-k", "withheld"]),
    ("no recursion guard", TICK, 'if [ -n "${FLEET_CHILD:-}" ]; then\n  exit 0\nfi\n', "",
     [T + "test_tick.py", "-k", "recursion"]),
    ("no kill switch", TICK, 'if [ "$KILL" != "1" ]; then', "if false; then", [T + "test_tick.py", "-k", "kill_switch"]),
    ("an env value makes a tick live", TICK, "  (*) DRY=1 ;;", "  (*) DRY=0 ;;",
     [T + "test_tick.py", "-k", "falls_toward_dry"]),
    ("the token not exported", TICK, "    export GH_TOKEN\n", "", [T + "test_tick.py", "-k", "token_reaches"]),
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
            if old not in orig:
                print("STALE     %s (anchor not found in %s)" % (name, rel))
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
