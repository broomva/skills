#!/usr/bin/env -S python3 -I
"""test_rules_canary.py — the canary certifies only refusals the harness's own log attributes (BRO-3814).

Each scenario builds a scratch repo with one canaried row (enforcer scripts/gate.py, registered in
the checkout's settings), then runs `rules_canary.py run` with a FAKE Claude Code binary. `run`
launches one session per canary case; the fake reads a scenario file beside the canary's checkout,
writes a transcript and a --debug-file log in the harness's formats (measured on 2.1.326), creates
markers, and can do what P20 #1298's reviewers did: refuse with another hook, rewrite input, run an
unsupported hook kind, undo a settings edit during the run, load from the wrong place.
"""
from __future__ import annotations

import json
import os
import plistlib
import site
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "scripts"  # the skill keeps code in scripts/
if site.getusersitepackages() not in sys.path:
    sys.path.append(site.getusersitepackages())
import yaml  # noqa: E402

sys.path.append(str(HERE))
from governance_paths import DIRS, governance_file  # noqa: E402  (the layout move, BRO-3200)

OWN = '"$CLAUDE_PROJECT_DIR"/scripts/gate.py'
OTHER = '"$CLAUDE_PROJECT_DIR"/scripts/other.py'
ROW = {
    "id": "no-bad", "rule": "x", "level": "hook",
    "enforcer": {"path": "scripts/gate.py", "registered": {"event": "PreToolUse", "tools": ["Bash"], "scope": "project"}},
    "canary": {
        "proofs": [{"call": {"tool": "Bash", "input": {"command": "touch {run}/p && run BAD"}},
                    "marker": {"absent": "{run}/p"}, "expect_reason": "Gate X"}],
        "controls": [{"call": {"tool": "Bash", "input": {"command": "touch {run}/c && run GOOD"}},
                      "marker": {"present": "{run}/c"}}]},
}
REFUSAL = "PreToolUse:Bash hook error: Gate X: BAD is refused"
HONEST = {
    "proof": {"hooks": [{"cmd": OWN, "status": 0, "decision": "deny", "reason": "Gate X: BAD is refused"}],
              "outcome": "denied", "result": REFUSAL, "error": True},
    "control": {"hooks": [{"cmd": OWN, "status": 0}], "outcome": "dispatched", "result": "ran", "error": False,
                "markers": ["c"]},
}

FAKE = r'''#!/usr/bin/env python3
import datetime, json, os, pathlib, sys, uuid
args = sys.argv[1:]
if args == ["--version"]:
    if os.environ.get("FAKE_VERSION_WRITES"):  # content landing between the checks and the snapshot
        w = json.loads(os.environ["FAKE_VERSION_WRITES"]); pathlib.Path(w["path"]).write_text(w["content"])
    print("9.9.9 (Claude Code)"); sys.exit(0)
brief = args[args.index("-p") + 1]
debug = pathlib.Path(args[args.index("--debug-file") + 1])
cwd = pathlib.Path.cwd()
base = cwd.parent
s = json.loads((base.parent / "scenario.json").read_text())
work = base / "work"
kind = "proof" if "/p &&" in brief else "control"
spec = s["cases"][kind]
(base.parent / f"fake-env-{kind}.json").write_text(json.dumps(dict(os.environ)))
(base.parent / f"fake-argv-{kind}.json").write_text(json.dumps(args))
try:
    (cwd / "probe-write").write_text("x")
    (base.parent / "checkout-writable").write_text("yes")
except OSError:
    pass

def unlocked(paths, fn):
    for p in paths:
        os.chmod(p, os.stat(p).st_mode | 0o200)
    fn()
    for p in paths:
        os.chmod(p, os.stat(p).st_mode & ~0o222)

config = pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"])
for action in (s.get("during", []) if kind == "proof" else []):
    claude_dir, settings, gate = cwd / ".claude", cwd / ".claude" / "settings.json", cwd / "scripts" / "gate.py"
    if action == "edit-settings-undo":
        def f():
            old = settings.read_text(); settings.write_text('{"hooks": {}}'); settings.write_text(old)
        unlocked([claude_dir, settings], f)
    elif action == "local-settings-create-delete":
        def f():
            local = claude_dir / "settings.local.json"; local.write_text("{}"); local.unlink()
        unlocked([claude_dir], f)
    elif action == "edit-enforcer-undo":
        def f():
            old = gate.read_text(); gate.write_text("print('allow')\n"); gate.write_text(old)
        unlocked([gate], f)
    elif action == "dev-mod":
        mods = config / "dev-mods" / "s" / "probe"; mods.mkdir(parents=True); (mods / "hooks.json").write_text("{}")
    elif action == "remote-hooks":
        (config / "remote-settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"type": "prompt"}]}]}}))
    elif action == "remote-env":
        (config / "remote-settings.json").write_text(json.dumps({"env": {"BASH_ENV": "/tmp/x.sh"}}))
    elif action == "builtin-store":
        store = config / "plugins" / "store"; store.mkdir(parents=True); (store / "cc-plugin-x_builtin-1.json").write_text("{}")
    elif action == "plugin-installed":
        cache = config / "plugins" / "cache" / "m" / "p"; cache.mkdir(parents=True); (cache / "hooks.json").write_text("{}")
    elif action == "managed-create-delete":
        managed = pathlib.Path(s["managed"]); managed.write_text('{"disableAllHooks": true}'); managed.unlink()
    elif action == "managed-dir-create-delete":
        managed = pathlib.Path(s["managed"]); managed.parent.mkdir(parents=True)
        managed.write_text("{}"); managed.unlink(); managed.parent.rmdir()
    elif action == "managed-target-edit-undo":
        target = pathlib.Path(s["managed"]).resolve(); old = target.read_text()
        target.write_text('{"disableAllHooks": true}'); target.write_text(old)
    elif action == "root-edit":
        (pathlib.Path(s["root"]) / "scripts" / "gate.py").write_text("print('untested')\n")
for name in spec.get("markers", []):
    (work / name).write_text("x")
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
head = {"type": "system", "cwd": str(cwd), "permissionMode": "bypassPermissions", "version": "9.9.9", "timestamp": now}
head.update(s.get("facts", {}))
head = {k: v for k, v in head.items() if v is not None}
lines, log = [head], ["2026-01-01T00:00:00.000Z [DEBUG] Registered %d hooks from 4 plugins" % spec.get("plugin_hooks", 0)]
for rec in spec.get("remote", ["No settings found (404)", "Saved to %s/remote-settings.json" % os.environ["CLAUDE_CONFIG_DIR"],
                               "Saved empty sentinel (404 response)"]):
    log.append("2026-01-01T00:00:00.000Z [DEBUG] Remote settings: " + rec)
command = next(l for l in brief.splitlines() if l.strip().startswith("`")).strip().strip("`")
for i in range(spec.get("calls", 1)):
    tid = f"toolu_{kind}{i}"
    use = {"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": command}}
    lines.append({"type": "assistant", "message": {"content": [use]}})
    if spec.get("duplicate_message"):
        lines.append({"type": "assistant", "message": {"content": [dict(use, input={"command": command, "x": 1})]}})
    lines.append({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": spec["result"], "is_error": spec["error"]}]}})
    for raw in spec.get("log_before", []):
        log.append("2026-01-01T00:00:00.000Z [DEBUG] " + raw)
    for h in spec["hooks"]:
        tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")  # a hook that echoes the credential into its record
        h = dict(h, cmd=h["cmd"].replace("{TOKEN}", tok), **({"reason": h["reason"].replace("{TOKEN}", tok)} if "reason" in h else {}))
        log.append('2026-01-01T00:00:00.000Z [DEBUG] Hooks: PreToolUse:Bash [%s] finished with status %d (5ms)' % (h["cmd"], h["status"]))
        if h["status"] == 2:
            log.append('2026-01-01T00:00:00.000Z [ERROR] "Hook PreToolUse:Bash (PreToolUse) error: status code 2\\nstderr:\\n%s"' % h.get("reason", ""))
        if "decision" in h:
            log.append("2026-01-01T00:00:00.000Z [DEBUG] Hook PreToolUse (%s) returned permissionDecision: %s%s"
                       % (h["cmd"], h["decision"], " (reason: %s)" % h["reason"] if h.get("reason") else ""))
    if spec.get("outcome") == "denied":
        log.append("2026-01-01T00:00:00.000Z [DEBUG] Hook denied tool use for Bash")
    elif spec.get("outcome") == "dispatched":
        log.append("2026-01-01T00:00:00.000Z [INFO] [Stall] tool_dispatch_start tool=Bash toolUseId=%s permissionDecisionMs=3" % tid)
sid = str(uuid.uuid4())
if s.get("session") != "unlogged":
    logs = (pathlib.Path(s["elsewhere"]) if s.get("session") == "elsewhere" else config / "projects") / "proj"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"{sid}.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
if spec.get("leak_work"):  # a hook that wrote the credential into the run's work directory
    (work / "leaked").write_text(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""))
if spec.get("leak_token"):  # a hook that printed the credential into the harness's log
    log.append("[DEBUG] hook stderr: " + os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""))
if not spec.get("no_debug"):
    debug.write_text("\n".join(log) + "\n")
print(json.dumps({"session_id": sid, "result": "done"}))
'''

failures = 0


def expect(label: str, ok: bool, detail="") -> None:
    global failures
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f": {str(detail)[-700:]}"))
    failures += not ok


def variant(proof=None, control=None):
    cases = json.loads(json.dumps(HONEST))
    cases["proof"].update(proof or {})
    cases["control"].update(control or {})
    return cases


REVERT_AFTER_LAST_SNAPSHOT = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import rules_canary as rc
path, content, calls, orig = Path(sys.argv[2]), sys.argv[3], [], rc.snapshot
def snapshot(paths):
    out = orig(paths)
    calls.append(1)
    if len(calls) == 2:
        path.write_text(content)
    return out
rc.snapshot = snapshot
sys.exit(rc.main(sys.argv[4:]))
"""


def scenario(cases=None, rows=(ROW,), layout=DIRS[-1], during=(), facts=None, session=None, managed=None,
             local_settings_committed=False, dirty=False, caller_env=None, managed_dir_absent=False, drop_in=None,
             credentials=True, mdm=None, register=(OWN,), settings_env=None, settings_extra=None, managed_late=None,
             managed_revert=None, dropin_late=None, settings_bom=False):
    """Build a repo, run the canary with the fake harness; return (rc, receipt, output, what the fake saw)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root, logs, scratch = tmp / "repo", tmp / "projects", tmp / "scratch"
        (root / layout).mkdir(parents=True)
        (root / ".claude").mkdir()
        (root / "scripts").mkdir()
        (root / "scripts" / "gate.py").write_text("print('gate')\n")
        (root / "scripts" / "other.py").write_text("print('other')\n")
        (root / ".claude" / "settings.json").write_text(json.dumps(dict({"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [c if isinstance(c, dict) else {"type": "command", "command": c}
                                          for c in register]}]}},
            **({"env": settings_env} if settings_env else {}), **(settings_extra or {}))))
        if settings_bom:  # the harness reads a UTF-8 BOM'd settings file; so must the validator
            raw = (root / ".claude" / "settings.json").read_bytes()
            (root / ".claude" / "settings.json").write_bytes(b"\xef\xbb\xbf" + raw)
        if local_settings_committed:
            (root / ".claude" / "settings.local.json").write_text("{}")
        (root / layout / "rules.yaml").write_text(yaml.safe_dump({"version": 1, "rules": list(rows)}))
        for argv in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "add", "-f", ".claude"],
                     ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(argv, cwd=root, check=True, capture_output=True)
        if dirty:
            (root / "scripts" / "gate.py").write_text("print('changed')\n")
        managed_path = tmp / "managed" / ("absent" if managed_dir_absent else "") / "managed-settings.json"
        if not managed_dir_absent:
            managed_path.parent.mkdir(parents=True, exist_ok=True)
        if managed == "symlink":
            (tmp / "managed-target.json").write_text("{}")
            managed_path.symlink_to(tmp / "managed-target.json")
        elif managed is not None:
            managed_path.write_text(json.dumps(managed))
        if drop_in is not None:
            (managed_path.parent / "managed-settings.d").mkdir()
            (managed_path.parent / "managed-settings.d" / "10-x.json").write_text(json.dumps(drop_in))
        mdm_dir = tmp / "mdm"
        mdm_dir.mkdir()
        if mdm is not None:
            (mdm_dir / "com.anthropic.claudecode.plist").write_bytes(plistlib.dumps(mdm))
        creds = tmp / "creds.json"
        if credentials:
            creds.write_text(json.dumps({"claudeAiOauth": dict({"accessToken": "sk-ant-oat01-test", "subscriptionType": "max",
                                                                "rateLimitTier": "default_claude_max_20x",
                                                                "expiresAt": int(time.time() * 1000) + 3_600_000},
                                                               **(credentials if isinstance(credentials, dict) else {}))}))
        fake = tmp / "bin" / "claude"
        fake.parent.mkdir()
        fake.write_text(FAKE)
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        run_dir = scratch / "run"
        scratch.mkdir()
        (scratch / "scenario.json").write_text(json.dumps({
            "elsewhere": str(logs), "cases": cases or HONEST, "during": list(during), "facts": facts or {},
            "session": session, "managed": str(managed_path), "root": str(root)}))
        env = dict(os.environ, RULES_CHECK_ROOT=str(root), RULES_CHECK_HOME=str(tmp), RULES_CANARY_CREDENTIAL=str(creds),
                   RULES_CANARY_MANAGED_SETTINGS=str(managed_path), RULES_CANARY_MDM_DIR=str(mdm_dir),
                   RULES_CANARY_PARALLEL="1", **(caller_env or {}))
        if managed_late is not None:  # rewritten by the fake's `--version`: after the checks, before the snapshot
            env["FAKE_VERSION_WRITES"] = json.dumps({"path": str(managed_path), "content": json.dumps(managed_late)})
        if dropin_late is not None:  # a drop-in that appears after the bound paths were listed
            (managed_path.parent / "managed-settings.d").mkdir(exist_ok=True)
            env["FAKE_VERSION_WRITES"] = json.dumps({"path": str(managed_path.parent / "managed-settings.d" / "10-late.json"),
                                                     "content": json.dumps(dropin_late)})
        argv = ["run", "--dir", str(run_dir), "--claude", str(fake)]
        if managed_revert is None:
            proc = subprocess.run([sys.executable, "-I", str(HERE / "rules_canary.py"), *argv],
                                  capture_output=True, text=True, env=env)
        else:  # rewrite the managed file right after the LAST snapshot: the window a late check misses
            proc = subprocess.run([sys.executable, "-I", "-c", REVERT_AFTER_LAST_SNAPSHOT, str(HERE), str(managed_path),
                                   json.dumps(managed_revert), *argv], capture_output=True, text=True, env=env)
        try:
            receipt = json.loads(governance_file(root, "rules-canary-receipt.json").read_text())
        except OSError:
            receipt = {}

        def read(name):
            f = scratch / name
            return json.loads(f.read_text()) if f.exists() else {}

        seen = {"env": read("fake-env-proof.json"), "argv": read("fake-argv-proof.json") or [],
                "writable": (scratch / "checkout-writable").exists(),
                "checkout_left": (run_dir / "checkout").exists(),
                "config_files": sorted(p.name for p in run_dir.glob("sessions/*/config/.credentials.json")),
                "token_files": [str(f) for f in run_dir.rglob("*") if f.is_file() and not f.is_symlink()
                                and b"sk-ant-oat01-test" in f.read_bytes()] if run_dir.exists() else [],
                "worktrees": subprocess.run(["git", "-C", str(root), "worktree", "list"], capture_output=True,
                                            text=True).stdout.strip().count("\n")}
        return proc.returncode, receipt, proc.stdout + proc.stderr, seen


def passed(receipt):
    return receipt.get("rows", {}).get("no-bad", {}).get("pass") is True


# ── the honest run, and what its receipt records ──
rc, receipt, out, seen = scenario()
expect("an honest run (one session per case, refusals attributed by the harness's log) certifies",
       rc == 0 and passed(receipt), out)
results = receipt.get("rows", {}).get("no-bad", {}).get("results", [])
expect("the receipt is v5, names the parser contract, and binds each case's transcript and debug log",
       receipt.get("version") == 5 and receipt.get("parser", "").startswith("claude-code-debug-hooks/")
       and len(results) == 2 and all(r["session"]["debug_log"]["sha256"] and r["session"]["transcript"]["sha256"]
                                     for r in results), receipt)
bound = receipt.get("bound", {}).get("files", {})
expect("the bound inputs include the absent settings.local.json, the enforcer and the MDM preferences",
       any(p.endswith(".claude/settings.local.json") and v == "absent" for p, v in bound.items())
       and any(p.endswith("scripts/gate.py") and v not in ("absent", "dir") for p, v in bound.items())
       and any(p.endswith("com.anthropic.claudecode.plist") for p in bound), bound)
argv = seen["argv"]
expect("each session loads project settings only and writes the harness's debug log",
       "--setting-sources" in argv and argv[argv.index("--setting-sources") + 1] == "project"
       and "--debug-file" in argv, argv)
expect("each session runs with its own config directory, holding no credentials file",
       "/sessions/" in seen["env"].get("CLAUDE_CONFIG_DIR", "") and not seen["config_files"], seen)
expect("each session runs on the subscription login's token; the receipt records the plan and never the token",
       seen["env"].get("CLAUDE_CODE_OAUTH_TOKEN") == "sk-ant-oat01-test"
       and receipt.get("launch", {}).get("auth", {}).get("plan") == "max" and "sk-ant-oat01-test" not in json.dumps(receipt),
       (seen["env"].get("CLAUDE_CODE_OAUTH_TOKEN"), receipt.get("launch", {}).get("auth")))
expect("the session saw a read-only checkout", not seen["writable"], seen)
expect("the canary removes its checkout and worktree afterwards", not seen["checkout_left"] and seen["worktrees"] == 0, seen)
rc, receipt, out, seen = scenario(caller_env={"BSTACK_OVERRIDE_WRITE_GATE": "1", "BROOMVA_X": "1"})
expect("the session's environment inherits no gate override or workspace variable",
       rc == 0 and "BSTACK_OVERRIDE_WRITE_GATE" not in seen["env"] and "BROOMVA_X" not in seen["env"], seen["env"])
rc, receipt, out, _ = scenario(cases=variant(proof={"duplicate_message": True}))
expect("the harness writing one tool_use message twice is one call, not a retry", rc == 0 and passed(receipt), out)

# ── evidence each case must show ──
rc, receipt, out, _ = scenario(cases=variant(proof={"calls": 0, "hooks": [], "outcome": None}))
expect("a proof the session never attempted does not certify", rc == 1 and "not ['Bash']" in out, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"calls": 2}))
expect("an undeclared second call is judged too (each attempt needs its own refusal record)", rc == 0 and passed(receipt), out)
rc, receipt, out, _ = scenario(cases=variant(proof={"hooks": [{"cmd": OWN, "status": 0}], "outcome": "denied",
                                                    "result": "Permission to use Bash has been denied."}))
expect("a refusal with no hook record (a deny rule, a prompt) does not certify", rc == 1
       and "records no hook refusal" in out, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"hooks": [{"cmd": OWN, "status": 0, "decision": "deny",
                                                               "reason": "Other gate: no"}]}))
expect("the enforcer refusing for another reason does not certify", rc == 1 and "another reason" in out, out)
rc, receipt, out, _ = scenario(cases=variant(control={"hooks": [{"cmd": OWN, "status": 0, "decision": "deny",
                                                                 "reason": "Gate X"}], "outcome": "denied",
                                                      "result": REFUSAL, "error": True, "markers": []}))
expect("a refused control does not certify", rc == 1 and "control was refused" in out, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"markers": ["p"]}))
expect("a refused proof whose marker exists anyway does not certify", rc == 1 and "exists" in out, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"outcome": None}))
expect("a refusal the harness wrote no outcome record for does not certify", rc == 1 and "call outcome(s)" in out, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"no_debug": True}))
expect("a session with no debug log does not certify (nothing attributes the refusal)", rc == 1
       and "no debug log" in out, out)

# ── attribution (the STRUCTURAL hoist) ──
rc, receipt, out, _ = scenario(register=(OWN, OTHER), cases=variant(proof={"hooks": [
    {"cmd": OWN, "status": 0}, {"cmd": OTHER, "status": 0, "decision": "deny", "reason": "Gate X: BAD is refused"}]}))
expect("a same-reason refusal from another hook the checkout registers does not certify (was BRO-3821)",
       rc == 1 and "refused by another hook" in out, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"hooks": [
    {"cmd": OWN, "status": 0}, {"cmd": '"$CLAUDE_PROJECT_DIR"/scripts/gate.py.old', "status": 0, "decision": "deny",
                                "reason": "Gate X"}]}))
expect("a hook the checkout does not register (a sibling gate.py.old) fails the run", rc == 1
       and "not an invocation the checkout registers" in out, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"hooks": [], "log_before": [
    'Hook PreToolUse ("$CLAUDE_PROJECT_DIR"/scripts/gate.py) returned permissionDecision: deny (reason: Gate X: BAD)']}))
expect("a deny record with no execution record for its hook does not certify (an incomplete log)", rc == 1
       and "no execution record" in out, out)
rc, receipt, out, _ = scenario(register=(OWN, OTHER), cases=variant(proof={"hooks": [
    {"cmd": OTHER, "status": 1}, {"cmd": OWN, "status": 0, "decision": "deny", "reason": "unrelated reason"}],
    "log_before": ['"Hook PreToolUse:Bash (PreToolUse) error: status code 1\\nstderr:\\nGate X: from a hook that did not block"']}))
expect("the expected reason in a NON-blocking hook's stderr does not certify the enforcer's other refusal", rc == 1
       and "another reason" in out, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"hooks": [{"cmd": OWN, "status": 2, "reason": "Gate X: BAD is refused"}]}))
expect("an exit-2 refusal by the row's enforcer certifies", rc == 0 and passed(receipt), out)
rc, receipt, out, _ = scenario(register=(OWN, OTHER), cases=variant(proof={"hooks": [
    {"cmd": OWN, "status": 0}, {"cmd": OTHER, "status": 2, "reason": "Gate X: BAD is refused"}]}))
expect("an exit-2 refusal by another registered hook does not certify", rc == 1 and "refused by another hook" in out, out)
rc, receipt, out, _ = scenario(cases=variant(control={"hooks": []}))
expect("a control the row's enforcer never ran on does not certify (a suppressed enforcer)", rc == 1
       and "does not record the row's enforcer" in out, out)
for line, word, label in (
        ("Hook PreToolUse (\"$CLAUDE_PROJECT_DIR\"/scripts/gate.py) modified tool input keys: [command]", "rewrote",
         "an input rewrite"),
        ("Hooks: Processing prompt hook with prompt: deny it", "unsupported hook mechanism", "a prompt hook"),
        ("Hook PreToolUse (\"$CLAUDE_PROJECT_DIR\"/scripts/gate.py) returned permissionDecision: ask", "answered `ask`",
         "an ask decision"),
        ("Hook PreToolUse permission record in a new format", "unrecognised hook record", "an unrecognised record"),
        ("hooks module evil-mod@local tool.check settled in 1ms (native link, next() included)", "not built in",
         "a native module that is not built in")):
    rc, receipt, out, _ = scenario(cases=variant(proof={"log_before": [line]}))
    expect(f"{label} in the harness's log fails the run", rc == 1 and word in out and not receipt, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"plugin_hooks": 2}))
expect("plugins registering hooks in the session fails the run", rc == 1 and "plugins registered" in out, out)

# ── inputs bound throughout the run ──
for action, label in (("edit-settings-undo", "a settings edit undone before the check"),
                      ("local-settings-create-delete", "a settings.local.json created and deleted during the run"),
                      ("edit-enforcer-undo", "an enforcer edit restored before the check")):
    rc, receipt, out, _ = scenario(during=[action])
    expect(f"{label} does not certify", rc == 1 and "changed during the run" in out and not receipt, out)
rc, receipt, out, _ = scenario(local_settings_committed=True)
expect("a checkout holding a settings.local.json refuses to run", rc == 1 and "settings.local.json" in out, out)
rc, receipt, out, _ = scenario(dirty=True)
expect("a dirty checkout under test refuses to run", rc == 2 and not receipt, out)
rc, receipt, out, _ = scenario(during=["root-edit"])
expect("the tree under test edited during the run does not certify", rc == 1 and "tree under test changed" in out, out)

# ── settings env that runs code before any hook script ──
for key in ("BASH_ENV", "PYTHONPATH", "PATH", "NODE_OPTIONS", "DYLD_INSERT_LIBRARIES", "HOME", "XDG_CONFIG_HOME",
            "CLAUDE_PROJECT_DIR"):
    rc, receipt, out, _ = scenario(settings_env={key: "/tmp/x"})
    expect(f"the checkout's settings env setting {key} refuses the run", rc == 1 and f"sets {key}" in out and not receipt, out)
rc, receipt, out, _ = scenario(settings_env={"DISABLE_AUTOUPDATER": "1"})
expect("a settings env with no startup variable does not block an honest run", rc == 0 and passed(receipt), out)
rc, receipt, out, _ = scenario(settings_env=["HOME"])
expect("a settings env that is not a mapping refuses the run", rc == 1 and "not a mapping" in out and not receipt, out)
rc, receipt, out, _ = scenario(managed={"env": {"BASH_ENV": "/tmp/x"}})
expect("managed settings setting a startup variable refuse the run", rc == 1 and "sets BASH_ENV" in out, out)

# ── managed sources (the ones a session cannot exclude) ──
for managed, word in (({"hooks": {"PreToolUse": [{"hooks": [{"type": "prompt", "prompt": "x"}]}]}}, "registers hooks"),
                      ({"enabledPlugins": {"p@m": True}}, "names plugins")):
    rc, receipt, out, _ = scenario(managed=managed)
    expect(f"managed settings that {word} refuse the run", rc == 1 and word in out and not receipt, out)
rc, receipt, out, _ = scenario(managed={"env": {}})
expect("managed settings with no hook and no plugin do not block an honest run", rc == 0 and passed(receipt), out)
rc, receipt, out, _ = scenario(drop_in={"hooks": {"PreToolUse": []}, "enabledPlugins": {"p@m": True}})
expect("a managed-settings.d drop-in with hooks or plugins refuses the run", rc == 1 and "10-x.json" in out, out)
rc, receipt, out, _ = scenario(mdm={"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]}})
expect("MDM managed preferences registering hooks refuse the run", rc == 1 and "com.anthropic.claudecode.plist" in out, out)
for action, label, managed in (("managed-create-delete", "managed settings created and deleted during the run", None),
                               ("managed-target-edit-undo", "a symlinked managed target edited and restored", "symlink")):
    rc, receipt, out, _ = scenario(during=[action], managed=managed)
    expect(f"{label} does not certify", rc == 1 and "changed during the run" in out and not receipt, out)
rc, receipt, out, _ = scenario(managed_dir_absent=True, during=["managed-dir-create-delete"])
expect("an absent managed directory created and removed during the run does not certify",
       rc == 1 and "changed during the run" in out and not receipt, out)

# ── the session's own config directory ──
for action, word in (("dev-mod", "gained dev-mods"), ("remote-hooks", "registers hooks"),
                     ("plugin-installed", "installed plugin")):
    rc, receipt, out, _ = scenario(during=[action])
    expect(f"the session's config directory ({action}) does not certify", rc == 1 and word in out and not receipt, out)
rc, receipt, out, _ = scenario(during=["builtin-store"])
expect("the harness's own built-in plugin records do not fail an honest run", rc == 0 and passed(receipt), out)
rc, receipt, out, _ = scenario(credentials=False)
expect("no Claude login refuses the run", rc == 1 and "no Claude subscription login" in out and not receipt, out)
rc, receipt, out, _ = scenario(credentials={"subscriptionType": "team"})
expect("a login on a plan that is not a personal subscription refuses the run",
       rc == 1 and "not a personal subscription" in out and not receipt, out)
rc, receipt, out, _ = scenario(credentials={"expiresAt": None})
expect("a login with no known expiry refuses the run", rc == 1 and "no expiry" in out and not receipt, out)
rc, receipt, out, seen = scenario(cases=variant(proof={"leak_token": True}))
expect("a session whose log holds the subscription token certifies nothing, and the token is in no output",
       rc == 1 and "held the subscription token" in out and not receipt and "sk-ant-oat01-test" not in out, out)
expect("no file the run leaves holds the subscription token", not seen["token_files"], seen["token_files"])
rc, receipt, out, seen = scenario(cases=variant(proof={"hooks": [{"cmd": OWN, "status": 0, "decision": "deny",
                                                                  "reason": "Gate X: BAD is refused {TOKEN}"},
                                                                 {"cmd": "/x/{TOKEN}", "status": 0}]}))
expect("a hook record holding the subscription token is never judged, so no evidence or error line prints it",
       rc == 1 and not receipt and "sk-ant-oat01-test" not in out and not seen["token_files"], out)
rc, receipt, out, seen = scenario(cases=variant(proof={"leak_token": True}), session="unlogged")
expect("a session that leaked the token and wrote no transcript leaves no file holding it (P20 #1298 round 5)",
       rc == 1 and not receipt and not seen["token_files"] and "sk-ant-oat01-test" not in out, (seen["token_files"], out))
rc, receipt, out, seen = scenario(cases=variant(proof={"leak_work": True}))
expect("a token written into the run's work directory is swept, and the run certifies nothing (round 6)",
       rc == 1 and not receipt and not seen["token_files"] and "held the subscription token" in out
       and "sk-ant-oat01-test" not in out, (seen["token_files"], out))
with tempfile.TemporaryDirectory() as tmp:
    locked = Path(tmp) / "locked.log"
    locked.write_text("x sk-ant-oat01-test")
    locked.chmod(0)
    try:
        import rules_canary as sweeper  # noqa: E402
        swept = sweeper.sweep_token(Path(tmp), "sk-ant-oat01-test")
    finally:
        locked.chmod(0o600)
    expect("a file the sweep cannot read fails the run closed (it may hold the token)",
           any("could not be checked" in e for e in swept), swept)
with tempfile.TemporaryDirectory() as tmp:
    import rules_canary as sweeper  # noqa: E402
    base = Path(tmp)
    (base / "sk-ant-oat01-test").touch()
    (base / "d-sk-ant-oat01-test").mkdir()
    named = sweeper.sweep_token(base, "sk-ant-oat01-test")
    expect("an entry whose NAME holds the token is deleted, and no message carries the token (round 7)",
           len(named) == 2 and not any("sk-ant-oat01-test" in e for e in named) and not list(base.iterdir()), named)
    for mode in (0, 0o600):  # unlistable; listable but its entries cannot be stat'ed or read
        sub = base / f"locked-{mode:o}"
        sub.mkdir()
        (sub / "cache.json").write_text("sk-ant-oat01-test")
        sub.chmod(mode)
        try:
            hidden = sweeper.sweep_token(base, "sk-ant-oat01-test")
        finally:
            sub.chmod(0o700)
        expect(f"a directory the sweep cannot fully read (mode {mode:o}) fails the run closed",
               any("could not be" in e for e in hidden), hidden)
        (sub / "cache.json").unlink()
        sub.rmdir()
rc, receipt, out, _ = scenario(credentials={"accessToken": ["not", "a", "string"]})
expect("a login whose token is not a string refuses the run", rc == 1 and "no Claude subscription login" in out
       and not receipt, out)
with tempfile.TemporaryDirectory() as tmp:
    import rules_canary as sweeper  # noqa: E402
    base = Path(tmp)
    (base / "target").mkdir()
    (base / "log-link").symlink_to("sk-ant-oat01-test")
    (base / "sk-ant-oat01-test").symlink_to(base / "target", target_is_directory=True)
    os.mkfifo(base / "pipe")
    links = sweeper.sweep_token(base, "sk-ant-oat01-test")
    left = sorted(p.name for p in base.iterdir())
    expect("a symlink whose target or name holds the token is deleted (never followed); a FIFO is not read (round 8)",
           left == ["pipe", "target"] and len(links) == 2 and not any("sk-ant-oat01-test" in e for e in links),
           (left, links))
rc, receipt, out, _ = scenario(credentials={"expiresAt": float("nan")})
expect("a login whose expiry is not a finite number refuses the run", rc == 1 and "no expiry" in out and not receipt, out)
rc, receipt, out, _ = scenario(managed={}, managed_late={"env": {"BASH_ENV": "/tmp/x.sh"}})
expect("managed settings written between the checks and the snapshot are still validated (round 8)",
       rc == 1 and "sets BASH_ENV" in out and not receipt, out)
rc, receipt, out, _ = scenario(managed={}, managed_late={"env": {"BASH_ENV": "/tmp/x.sh"}}, managed_revert={})
expect("managed settings in force during the run but reverted after the last snapshot are still caught (round 9)",
       rc == 1 and "sets BASH_ENV" in out and not receipt, out)
rc, receipt, out, _ = scenario(managed={}, dropin_late={})
expect("a managed drop-in that appears after the bound inputs were listed fails the run (round 10)",
       rc == 1 and "set of bound inputs changed" in out and not receipt, out)
rc, receipt, out, _ = scenario(register=(OWN, {"type": "command", "command": OWN, "args": ["safe x"]}))
expect("a hook entry with `args` (run without the shell, its arguments logged ambiguously) refuses the run (round 10)",
       rc == 1 and "outside HOOK_ENTRY_KEYS" in out and not receipt, out)
rc, receipt, out, _ = scenario(credentials={"accessToken": "   "})
expect("a whitespace-only token refuses the run", rc == 1 and "no Claude subscription login" in out and not receipt, out)
with tempfile.TemporaryDirectory() as tmp:
    import rules_canary as reg_mod  # noqa: E402
    co = Path(tmp)
    (co / ".claude").mkdir()
    (co / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [
        {"type": "command", "command": "/x/gate.py", "args": ["a"]}, {"type": "command", "command": "/x/other.py"}]}]}}))
    regs = reg_mod.registered_invocations(co)
    expect("an exec-form (args) entry registers no invocation", regs == {("/x/other.py", ())}, regs)
rc, receipt, out, _ = scenario(settings_extra={"apiKeyHelper": "echo k"}, settings_bom=True)
expect("a BOM'd project settings file is validated like any other (round 12)",
       rc == 1 and "`apiKeyHelper`, a settings key not in SETTINGS_KEYS_ALLOWED" in out and not receipt, out)
with tempfile.TemporaryDirectory() as tmp:
    import rules_canary as kc  # noqa: E402
    bad = Path(tmp) / "settings.json"
    bad.write_text("{not json")
    unparsed = kc.settings_errors([bad])
    expect("a settings file that cannot be parsed is refused, not read as empty",
           any("cannot be parsed" in e for e in unparsed), unparsed)
    saved = os.environ.get("USER")
    try:
        accounts = []
        for user in ("runner", "has space", None):
            if user is None:
                os.environ.pop("USER", None)
            else:
                os.environ["USER"] = user
            accounts.append(kc.keychain_account())
    finally:
        if saved is not None:
            os.environ["USER"] = saved
    expect("the Keychain account is the harness's: $USER, else the login name, else claude-code-user (round 12)",
           accounts == ["runner", "claude-code-user", kc.login_name()], accounts)
rc, receipt, out, _ = scenario(cases=variant(proof={"remote": ["Fetched 2 settings", "Saved to /x/remote-settings.json"]}))
expect("a session whose log shows remote settings loaded fails, whatever the file says afterwards (round 12)",
       rc == 1 and "loaded remote settings" in out and not receipt, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"remote": []}))
expect("a session whose log does not show the empty remote-settings fetch fails", rc == 1
       and "has no remote settings (404)" in out and not receipt, out)
rc, receipt, out, _ = scenario(settings_extra={"apiKeyHelper": "echo sk-ant-api03-x"})
expect("project settings with an apiKeyHelper (it replaces the subscription token) refuse the run",
       rc == 1 and "`apiKeyHelper`, a settings key not in SETTINGS_KEYS_ALLOWED" in out and not receipt, out)
rc, receipt, out, _ = scenario(managed={"apiKeyHelper": "echo k"})
expect("managed settings with a key outside the allowlist refuse the run",
       rc == 1 and "not in SETTINGS_KEYS_ALLOWED" in out and not receipt, out)
rc, receipt, out, _ = scenario(during=["remote-env"])
expect("remote settings whose env sets a startup variable fail the run", rc == 1 and "sets BASH_ENV" in out and not receipt, out)
rc, receipt, out, _ = scenario(cases=variant(proof={"log_before": ["[claudeai-mcp] Disabled: API-key auth precedence active"]}))
expect("a session the harness logs as authenticated by API key fails the run",
       rc == 1 and "authenticated with an API key" in out and not receipt, out)
rc, receipt, out, _ = scenario(credentials={"expiresAt": 1000})
expect("a login whose token is about to expire refuses the run", rc == 1 and "expires within" in out and not receipt, out)

# ── the session must be the launch's own ──
rc, receipt, out, _ = scenario(session="unlogged")
expect("a launch whose session left no transcript does not certify", rc == 1 and "transcript(s) in its config" in out, out)
rc, receipt, out, _ = scenario(session="elsewhere")
expect("a transcript outside the session's config directory is not the launched session's", rc == 1
       and "transcript(s) in its config" in out, out)
for fact, value, word in (("cwd", "/tmp/elsewhere", "not the canary's checkout"),
                          ("permissionMode", "default", "permission mode"),
                          ("version", "1.0.0", "the launched binary is"),
                          ("version", None, "records no Claude Code version"),
                          ("timestamp", "2020-01-01T00:00:00+00:00", "did not start during this launch")):
    rc, receipt, out, _ = scenario(facts={fact: value})
    expect(f"a session whose {fact} disagrees with the launch does not certify", rc == 1 and word in out, out)

# ── layouts (BRO-3200) ──
for layout in DIRS:
    rc, receipt, out, _ = scenario(layout=layout)
    expect(f"an honest run certifies with the registry in {layout}/", rc == 0 and passed(receipt), out)

# ── units ──
import rules_canary as canary_mod  # noqa: E402
vacuous = json.loads(json.dumps(ROW))
vacuous["canary"]["proofs"][0]["marker"] = {"absent": "{run}/never-written"}
expect("a proof marker the call never writes is refused (a canary that cannot fail)",
       any("not a path the call itself writes" in e for e in canary_mod.canary_errors(vacuous["canary"], vacuous)))
cases = {
    '"$CLAUDE_PROJECT_DIR"/scripts/gate.py': "/co/scripts/gate.py",
    'python3 -I "${CLAUDE_PROJECT_DIR}/scripts/gate.py" --flag': "/co/scripts/gate.py",
    'python3 /co/scripts/../scripts/gate.py': None,
    '"$CLAUDE_PROJECT_DIR"/./scripts/gate.py': None,
    'python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py.old"': "/co/scripts/gate.py.old",
    # Not one simple invocation: attributes to no script (P20 #1298 fresh round 1).
    'X=1 bash /co/scripts/gate.py': None,
    'python3 -c "import x" /co/scripts/gate.py': None,
    '"$CLAUDE_PROJECT_DIR"/scripts/gate.py </dev/null; "$CLAUDE_PROJECT_DIR"/scripts/impostor.sh': None,
    'env -u "$CLAUDE_PROJECT_DIR"/scripts/gate.py "$CLAUDE_PROJECT_DIR"/scripts/impostor.sh': None,
    'python3 -W "$CLAUDE_PROJECT_DIR"/scripts/gate.py "$CLAUDE_PROJECT_DIR"/scripts/impostor.py': None,
    'BASH_ENV=/co/i.sh bash /co/scripts/gate.py': None,
    'bash /co/scripts/gate.py "$HOME"': None,
    # Defences each guard alone must hold: a newline is two commands; a flag that takes an argument.
    '/co/scripts/gate.py\n/co/scripts/impostor.sh': None,
    'python3 -W /co/scripts/gate.py /co/scripts/impostor.py': None,
    # The fail-soft tail (stderr dropped, exit status swallowed) is still one script; nothing else is.
    'python3 -I /co/scripts/gate.py hook stop 2>/dev/null || true': "/co/scripts/gate.py",
    '/co/scripts/gate.py || true': "/co/scripts/gate.py",
    '/co/scripts/gate.py </dev/null || true': None,
    '/co/scripts/gate.py >/dev/null || true': None,
    '/co/scripts/gate.py 2>&1 || true': None,
    '/co/scripts/gate.py || /co/scripts/impostor.sh': None,
    '/co/scripts/gate.py 2>/dev/null; true': None,
    '/co/scripts/gate.py ~/x': None,
    # Round 2: the interpreter is a bare name (a path to one is itself the script that runs); no
    # assignment; no single quotes or quoted ~ (the shell would not expand them).
    '/co/bin/python3 /co/scripts/gate.py': "/co/bin/python3",
    'CTX_PYTHON=/opt/homebrew/bin/python3 /bin/sh /x/ctx-hook.sh stop': None,
    "'$CLAUDE_PROJECT_DIR/scripts/gate.py'": None,
    "'~/gate.py'": None,
    '"~/gate.py"': None,
}
got = {c: canary_mod.executed_script(c, "/co") for c in cases}
split = (canary_mod.executed_script('$CLAUDE_PROJECT_DIR/scripts/gate.py', "/co dir"),
         canary_mod.executed_script('"$CLAUDE_PROJECT_DIR"/scripts/gate.py', "/co dir"))
expect("an unquoted project path that would split attributes to nothing; quoted, it is the script",
       split == (None, "/co dir/scripts/gate.py"), split)
home_form = canary_mod.executed_script("python3 -I ~/s/p9.py hook stop 2>/dev/null || true", "/co")
expect("a home-relative script (~/...) is not a canonical form: it attributes to nothing", home_form is None, home_form)
expect("executed_script attributes only a simple invocation of one script, exactly", got == cases, got)
# BRO-3849 and P20 #1298 round 2: forms where a shell-imitating parser and the shell disagreed.
odd = {c: canary_mod.executed_script(c, "/co") for c in (
    '$CLAUDE_PROJECT_DIRfoo/scripts/gate.py', '"$CLAUDE_PROJECT_DIR_X"/scripts/gate.py', '~""/gate',
    '""$CLAUDE_PROJECT_DIR/gate', '/co/scripts/gate.py\r/co/scripts/impostor.sh', "zsh /co/scripts/gate.py",
    "bash /co/scripts/gate.py", "python /co/scripts/gate.py", "/co/scripts/gate.py  --x", "/co/scripts/gate.py =x")}
expect("forms a parser and the shell read differently attribute to nothing", set(odd.values()) == {None}, odd)


def differential(project_name: str) -> tuple[int, list]:
    """Every command the grammar accepts, from a cross product of adversarial pieces, run under each
    real shell present: the shell must execute exactly the script and arguments attributed."""
    import itertools
    import shutil
    shells = [s for s in ("sh", "bash", "zsh") if shutil.which(s)]
    required = {"sh", "bash"} | ({"zsh"} if sys.platform == "darwin" else set())  # CI's Linux has no zsh
    assert required <= set(shells), f"the differential needs {sorted(required)}; found {shells}"
    with tempfile.TemporaryDirectory() as tmp:
        proj, home = Path(tmp) / project_name, Path(tmp) / "home"
        for base in (proj, home, Path(tmp) / "abs"):
            (base / "s").mkdir(parents=True)
            gate = base / "s" / "g.py"
            gate.write_text("#!/usr/bin/env python3\nimport os, sys\nprint(os.path.realpath(sys.argv[0]), *sys.argv[1:])\n")
            gate.chmod(0o755)
        abs_ = str(Path(tmp, "abs").resolve())
        prefixes = ["", "python3 ", "python3 -I ", "python3 -W ", "X=1 ", "exec "]
        scripts = ['"$CLAUDE_PROJECT_DIR"/s/g.py', '"$CLAUDE_PROJECT_DIR/s/g.py"', '"${CLAUDE_PROJECT_DIR}/s/g.py"',
                   '$CLAUDE_PROJECT_DIR/s/g.py', '""$CLAUDE_PROJECT_DIR/s/g.py', '"$CLAUDE_PROJECT_DIR"x/s/g.py',
                   '~/s/g.py', '~""/s/g.py', f"{abs_}/s/g.py", f"{abs_}/s/../s/g.py", f"{abs_}/missing/../s/g.py",
                   '"$CLAUDE_PROJECT_DIR"/missing/../s/g.py', f"{abs_}/./s/g.py", f"'{abs_}/s/g.py'", f"{abs_}/s/g*.py"]
        args = ["", " a", " a --b=c d", " --x=1", " a=b", " =b", " $HOME", " ~", " a*", ' "q"', " -", " a:b", " a\rb", " a\tb"]
        tails = ["", " 2>/dev/null", " || true", " 2>/dev/null || true", "; true", "; echo x", " && echo x",
                 " || echo x", " | cat", " >/dev/null", " 2>&1"]
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "CLAUDE_PROJECT_DIR": str(proj)}
        accepted, wrong = 0, []
        for pre, scr, arg, tail in itertools.product(prefixes, scripts, args, tails):
            cmd = pre + scr + arg + tail
            inv = canary_mod.simple_invocation(cmd, str(proj))
            if inv is None:
                continue
            accepted += 1
            want = " ".join([inv[0], *inv[1]])
            for sh in shells:
                got = subprocess.run([sh, "-c", cmd], env=env, cwd=tmp, capture_output=True, text=True).stdout.strip()
                if got != want:
                    wrong.append((sh, cmd, want, got))
        return accepted, wrong


# P20 #1298 round 3: attribution compares the whole invocation, script AND arguments, as ownership does.
with tempfile.TemporaryDirectory() as tmp:
    co = Path(tmp)
    (co / "scripts").mkdir()
    (co / "scripts" / "gate.py").write_text("x")
    (co / ".claude").mkdir()
    own_cmd, other_cmd = '"$CLAUDE_PROJECT_DIR"/scripts/gate.py safe', '"$CLAUDE_PROJECT_DIR"/scripts/gate.py unsafe'
    (co / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"command": own_cmd}]}]}}))
    arow = {"enforcer": {"path": "scripts/gate.py", "args": ["safe"]}}
    acase = {"kind": "proof", "call": {"tool": "Bash", "input": {"command": "true"}},
             "marker": {"absent": str(co / "never")}, "expect_reason": "Gate X"}
    acalls = [{"tool": "Bash", "input": {"command": "true"}, "is_error": True, "result": "PreToolUse:Bash hook error: Gate X"}]
    def seg_by(cmd, outcome="denied", decision="deny"):
        return {"tool": "Bash", "outcome": outcome, "tool_use_id": "t1", "execs": [(cmd, 0)],
                "decisions": [(cmd, decision, "Gate X")], "exit2": []}
    by_other = canary_mod.judge_case(acase, acalls, [seg_by(other_cmd)], {}, arow, co)
    by_own = canary_mod.judge_case(acase, acalls, [seg_by(own_cmd)], {}, arow, co)
    expect("a refusal by the same script with other arguments is not the row's enforcer refusing",
           by_other[0] is False and "another hook" in by_other[1] and by_own[0] is True, (by_other, by_own))
    ccase = dict(acase, kind="control", marker={"present": str(co / "m")})
    ccalls = [dict(acalls[0], id="t1", is_error=False, result="ok")]
    ctl = canary_mod.judge_case(ccase, ccalls, [seg_by(other_cmd, "dispatched", "allow")], {}, arow, co)
    expect("a control allowed by the same script with other arguments does not show the row's enforcer allowing it",
           ctl[0] is False and "enforcer running and allowing" in ctl[1], ctl)
    alog = {"problems": [], "plugin_hooks": 0,
            "segments": [{"execs": [(other_cmd, 2)], "rewrites": [], "modules": [], "decisions": []}]}
    errs = canary_mod.log_errors(alog, co)
    expect("a hook run with arguments the checkout never registered fails the run",
           any("not an invocation the checkout registers" in e for e in errs), errs)
for project_name in ("proj dir", 'pr"o$j `x` *'):  # the value is quoted: never re-expanded, split or globbed
    accepted, wrong = differential(project_name)
    expect(f"every accepted form runs, under sh, bash and zsh, exactly the script and arguments attributed "
           f"(project dir {project_name!r})", accepted >= 100 and not wrong, (accepted, wrong[:3]))
with tempfile.TemporaryDirectory() as tmp:
    real = Path(tmp) / "hooks-alt" / "inner"
    real.mkdir(parents=True)
    (real / "gate.py").write_text("x")
    (Path(tmp) / "scripts").mkdir()
    (Path(tmp) / "scripts" / "lnk").symlink_to(real)
    got = canary_mod.executed_script('"$CLAUDE_PROJECT_DIR"/scripts/lnk/gate.py', tmp)
    expect("a symlinked path attributes to the file it reaches, not the name it shows",
           got == os.path.realpath(real / "gate.py"), got)
# Lines measured on a real 2.1.326 canary session: other events, telemetry, the stdout-first exit-2 record.
REAL = "\n".join("2026-11-17T15:47:01.000Z " + x for x in (
    '[DEBUG] Hooks: SessionStart:startup [/x/auth-preflight-hook.sh] finished with status 0 (40ms)',
    '[DEBUG] "Hook SessionStart:startup (SessionStart) success:\\nstderr:\\n3 credential surface(s) need permission"',
    '[DEBUG] hooks module cc-plugin-telemetry@builtin telemetry.log settled in 0.1ms (native link, next() included)',
    '[DEBUG] Hooks: PreToolUse:Write ["$CLAUDE_PROJECT_DIR"/scripts/check-file-write-safety.py] finished with status 2 (80ms)',
    '[DEBUG] Hook JSON output had unrecognized keys (ignored): ok, blocked_by, details.',
    '[ERROR] "Hook PreToolUse:Write (PreToolUse) error: status code 2\\nstdout:\\n{}\\nstderr:\\ncontrol surface"',
    '[DEBUG] Hook denied tool use for Write',
    '[DEBUG] Hooks: Stop [/x/bridge-hook.sh] finished with status 0 (9ms)'))
parsed = canary_mod.hook_log(REAL)
expect("the parser reads real 2.1.326 records: other events skipped, the stdout-first exit-2 refusal attributed",
       not parsed["problems"] and len(parsed["segments"]) == 1 and parsed["segments"][0]["outcome"] == "denied"
       and parsed["segments"][0]["execs"] == [('"$CLAUDE_PROJECT_DIR"/scripts/check-file-write-safety.py', 2)]
       and parsed["segments"][0]["exit2"][0][0] == '"$CLAUDE_PROJECT_DIR"/scripts/check-file-write-safety.py'
       and "control surface" in parsed["segments"][0]["exit2"][0][1], parsed)


# The managed sources are the canary machine's (CI on #1298 read every receipt stale: the MDM path
# names the user, so the digest differed between the Mac and the runner with no managed file at all).
with tempfile.TemporaryDirectory() as tmp:
    probe = ("import sys; sys.path.insert(0, sys.argv[1]); import rules_canary as c; print(c.managed_digest())")

    def digest(user, mdm_file=False):
        mdm = Path(tmp) / "mdm"
        mdm.mkdir(exist_ok=True)
        if mdm_file:
            (mdm / "com.anthropic.claudecode.plist").write_bytes(plistlib.dumps({"x": 1}))
        env = dict(os.environ, USER=user, RULES_CANARY_MDM_DIR=str(mdm),
                   RULES_CANARY_MANAGED_SETTINGS=str(Path(tmp) / "none" / "managed-settings.json"))
        return subprocess.run([sys.executable, "-I", "-c", probe, str(HERE)], capture_output=True, text=True,
                              env=env).stdout.strip()

    absent = digest("runner")
    same = digest("broomva") == absent
    changed = digest("runner", mdm_file=True) != absent
    expect("the managed digest is the same on any machine with no managed file, and moves when one appears",
           same and changed, (same, changed))
# A receipt with an entry for the row and a managed digest from another machine: reaches the comparison.
other_machine = {"version": 5, "rows": {"no-bad": {"results": []}}, "settings_sha256": {"managed": "f" * 64}}
stale = canary_mod.freshness(dict(ROW), other_machine, check_user=False, check_harness=False)
on_mac = canary_mod.freshness(dict(ROW), other_machine, check_user=True, check_harness=False)
expect("freshness without user checks (CI) never compares managed settings; on the canary's machine it does",
       not any("managed settings" in s for s in stale) and any("managed settings" in s for s in on_mac), (stale, on_mac))


def closure(files: dict, ignore: str = "") -> str:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text)
        if ignore:
            (root / ".gitignore").write_text(ignore)
        for argv in (["git", "init", "-q"], ["git", "add", "-A"]):
            subprocess.run(argv, cwd=root, check=True, capture_output=True)
        probe = subprocess.run([sys.executable, "-I", "-c",
                                "import sys; sys.path.insert(0, sys.argv[1]); import rules_canary as c; from pathlib import Path; "
                                "print(sorted(p.name for p in c.dependencies(Path(sys.argv[2]))))",
                                str(HERE), str(root / "scripts" / "gate.sh")],
                               capture_output=True, text=True, env=dict(os.environ, RULES_CHECK_ROOT=str(root)))
        return probe.stdout.strip() + probe.stderr


got = closure({"scripts/gate.sh": "cat state.json tracked.json\n", "scripts/state.json": "{}", "scripts/tracked.json": "{}"},
              ignore="scripts/state.json\n")
expect("an ignored runtime file a gate names is not in the closure; a tracked one is",
       got == "['gate.sh', 'tracked.json']", got)
got = closure({"scripts/gate.sh": "cat conf.json rules-canary-receipt.json\n", "scripts/conf.json": '{"run": "other.sh"}',
               "scripts/other.sh": "echo other\n", f"{DIRS[-1]}/rules-canary-receipt.json": "{}"})
expect("a data file a gate names is bound but not walked, and the receipt is never a dependency",
       got == "['conf.json', 'gate.sh']", got)

print("all rules_canary tests passed" if not failures else f"{failures} rules_canary test(s) failed")
sys.exit(1 if failures else 0)
