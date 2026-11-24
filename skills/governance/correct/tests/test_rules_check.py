#!/usr/bin/env -S python3 -I
"""test_rules_check.py — the rule-registry check must be able to fail (BRO-3800).

Each case builds a throwaway repo root with its own .control/rules.yaml,
.control/policy.yaml, fake enforcers and .claude/settings.json, then runs
rules_check.py against it. Most cases are refusals, because a check that cannot
fail proves nothing. The cases named "r1"/"r2" reproduce the P20 findings of
rounds 1 and 2 on PR #1298: each was a way the checker reported PASS without the
enforcer having decided anything.

Hermetic: RULES_CHECK_ROOT, RULES_CHECK_HOME and RULES_CHECK_HOST point at the
fixture, so the real settings, enforcers and host are never read.
"""
from __future__ import annotations

import json
import os
import site
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

CHECK = Path(__file__).resolve().parent.parent / "scripts" / "rules_check.py"  # the skill keeps code in scripts/
if site.getusersitepackages() not in sys.path:  # PyYAML lives in user site-packages
    sys.path.append(site.getusersitepackages())
import yaml  # noqa: E402

# A PreToolUse hook that refuses Bash commands (and file paths) containing BAD, and says what to do.
# Two environment knobs let a test make ONLY the live registration diverge from the in-tree run:
# REASON changes the refusal's text, ONLYFIRST stops refusing the second spelling (BAD2), BLOCKALL
# refuses everything.
GATE = textwrap.dedent("""\
    import json, os, sys
    ti = json.load(sys.stdin).get("tool_input") or {}
    cmd = ti.get("command", "") or ti.get("file_path", "")
    if os.environ.get("DISABLE_GATE"):
        sys.exit(0)
    if os.environ.get("BLOCKALL") or ("BAD" in cmd and not (os.environ.get("ONLYFIRST") and "BAD2" in cmd)):
        print(json.dumps({"decision": "block", "reason": os.environ.get("REASON", "Gate X: BAD is refused; use GOOD")}))
    """)
ALLOW_ALL = "import sys; sys.stdin.read()\n"
NO_HOOKS = {"hooks": {}}  # a user-scope fixture registers its hook in user settings only
BLOCK_ALL = "import sys; sys.stdin.read(); print('refused', file=sys.stderr); sys.exit(2)\n"
LINT = ("import sys\nif 'BAD' in open(sys.argv[1]).read():\n"
        "    print('found BAD: use GOOD')\n    sys.exit(1)\n")
POLICY = "gates:\n  hard: []\n"
REG = {"event": "PreToolUse", "tools": ["Bash"], "scope": "project"}
HOOK_RULE = {
    "id": "no-bad", "rule": "Never run BAD.", "level": "hook",
    "enforcer": {"path": "scripts/gate.py", "registered": REG},
    "proofs": [{"from": "t", "expect_reason": "Gate X",
                "event": {"tool_name": "Bash", "tool_input": {"command": "run BAD now"}}}],
    "controls": [{"why": "t", "event": {"tool_name": "Bash", "tool_input": {"command": "run GOOD now"}}}],
    "canary": {"none": "a fixture", "ticket": "BRO-1"},
}
LINT_RULE = {"id": "lint", "rule": "x", "level": "lint", "enforcer": {"path": "lint.py"},
             "proofs": [{"from": "t", "args": ["{scratch}/f.txt"], "files": {"f.txt": "BAD"},
                         "expect_output": "found BAD"}],
             "controls": [{"why": "t", "args": ["{scratch}/f.txt"], "files": {"f.txt": "GOOD"}}]}


def typed(settings):
    """A copy of a settings dict where every hook entry without a `type` states `type: command`."""
    if not isinstance(settings, dict):
        return settings
    out = json.loads(json.dumps(settings))
    for entries in (out.get("hooks") or {}).values():
        for entry in entries or []:
            for hook in entry.get("hooks") or []:
                hook.setdefault("type", "command")
    return out


def hooks(*commands):
    """settings.json with PreToolUse/Bash hook commands."""
    return {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": c} for c in commands]}]}}


def run(rules, gate=GATE, settings=None, extra=None, only=True, policy=POLICY, top=None,
        host="ci-runner", home_settings=None, args=None, layout=".control", base=None, root_name="repo",
        raw=False, receipt=None, path=None):
    """layout is the governance directory; ".broomva" also drops --registry, so the
    default resolution (BRO-3200, new key first) is what reads it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / root_name
        home = Path(tmp) / "home"
        gov = root / layout
        for d in (gov, root / "scripts", root / ".claude", home / ".claude"):
            d.mkdir(parents=True)
        (root / "scripts" / "gate.py").write_text(gate)
        for name, body in (extra or {}).items():
            dest = (root / name).resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body)
        settings = settings if settings is not None else hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"')
        if not raw:  # a real settings file states `type: command`; tests of a missing type pass raw=True
            settings, home_settings = typed(settings), typed(home_settings)
        (root / ".claude" / "settings.json").write_text(json.dumps(settings).replace("{tmp}", tmp))
        if home_settings is not None:
            (home / ".claude" / "settings.json").write_text(json.dumps(home_settings).replace("{tmp}", tmp))
        if policy is not None:
            (gov / "policy.yaml").write_text(policy)
        (gov / "rules.yaml").write_text(yaml.safe_dump({"version": 1, "rules": rules, **(top or {})}))
        if base is not None:  # the base branch's registry, committed; the tree under test on top
            new_rules = (gov / "rules.yaml").read_text()
            (gov / "rules.yaml").write_text(yaml.safe_dump({"version": 1, **base}))
            for argv0 in (["git", "init", "-q"], ["git", "add", "-A"],
                          ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"]):
                subprocess.run(argv0, cwd=root, check=True, capture_output=True)
            (gov / "rules.yaml").write_text(new_rules)
            args = list(args or []) + ["--base", "HEAD"]
        if receipt is not None:  # a canary receipt built by rules_canary itself over the files as written
            for argv0 in (["git", "init", "-q"], ["git", "add", "-A"],
                          ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "certified"]):
                subprocess.run(argv0, cwd=root, check=True, capture_output=True)
            gen = textwrap.dedent("""\
                import json, sys
                sys.path.append(sys.argv[1])
                import rules_canary as c
                mode, rows = sys.argv[2], {}
                for r in c.registered(c.load_registry()):
                    if "none" in (r.get("canary") or {}):
                        continue
                    keys = [c.case_key(x) for x in c.expected_cases(r, "{run}")]
                    session = {"debug_log": {"sha256": "d" * 64}, "transcript": {"sha256": "f" * 64}}
                    results = [{"case": k, "ok": mode != "failed", "session": session} for k in keys]
                    if mode == "fabricated":
                        results = []
                    deps = c.deps_digest(r)
                    if mode == "stale-enforcer":
                        deps = {"sha256": "0" * 64, "files": {k: "0" * 12 for k in deps["files"]}}
                    rows[r["id"]] = {"row_sha256": c.row_sha(dict(r, rule="older") if mode == "stale-row" else r),
                                     "deps": deps, "pass": mode not in ("failed", "fabricated"), "results": results}
                head = c.subprocess.run(["git", "-C", str(c.ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                receipt = {"version": 1 if mode == "v1" else 5, "harness": "test", "rows": rows, "parser": c.PARSER,
                           "judge_sha256": "0" * 64 if mode == "old-judge" else c.judge_sha(),
                           "commit": "0" * 40 if mode == "foreign-commit" else head,
                           "launch": {"claude": "/usr/local/bin/claude",
                                      "auth": {"plan": "team" if mode == "team-plan" else "max"}},
                           "bound": {"sha256": "e" * 64, "files": {}},
                           "settings_sha256": {"project": c.file_sha(c.ROOT / ".claude" / "settings.json"),
                                               "managed": c.managed_digest(), "user": c.file_sha(c.user_settings())}}
                c.governance_file(c.ROOT, c.RECEIPT_NAME).write_text(json.dumps(receipt))
                """)
            subprocess.run([sys.executable, "-I", "-c", gen, str(CHECK.parent), receipt], check=True, capture_output=True,
                           env=dict(os.environ, RULES_CHECK_ROOT=str(root), RULES_CHECK_HOME=str(home)))
        env = dict(os.environ, RULES_CHECK_ROOT=str(root), RULES_CHECK_HOME=str(home), RULES_CHECK_HOST=host,
                   **({"PATH": path} if path else {}))
        argv = [sys.executable, "-I", str(CHECK), "--json"]
        if layout == ".control":
            argv += ["--registry", str(gov / "rules.yaml")]
        if only and rules:
            argv += ["--only", *[r["id"] for r in rules]]
        proc = subprocess.run(argv + list(args or []), capture_output=True, text=True, env=env, timeout=300)
        if not proc.stdout.strip():
            return proc.returncode, []
        try:
            return proc.returncode, json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise AssertionError(f"rules_check did not print JSON: {proc.stdout!r} {proc.stderr!r}")


def status(rows, rule_id):
    return next(r["status"] for r in rows if r["id"] == rule_id)


def fails(rows, rule_id):
    return " | ".join(next(r["fails"] for r in rows if r["id"] == rule_id))


def expect(name, cond, detail=""):
    if not cond:
        print(f"FAIL {name}: {detail}")
        sys.exit(1)
    print(f"ok   {name}")


# The positive controls run an ordinary git and python, without whatever GIT_* or PYTHON* the
# session running this test sets (a harness may set GIT_CONFIG_GLOBAL; P20 #1299 r13, stratum A).
CALLER_ENV = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PYTHON"))}


def sealed_git_reads_nothing_planted() -> None:
    """P20 #1299 r11: under the replay's git environment a planted global config and a planted bare
    repository are not read (a case may point HOME into its scratch and write files there)."""
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location("rules_check_sealed", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp).resolve()
        (scratch / ".gitconfig").write_text("[user]\n\tname = planted\n")
        bare = scratch / "bare"
        (bare / "objects").mkdir(parents=True)
        (bare / "refs").mkdir()
        (bare / "HEAD").write_text("ref: refs/heads/main\n")
        (bare / "config").write_text("[core]\n\tbare = true\n[user]\n\tname = bare-planted\n")
        repo = scratch / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        marker = scratch / "fsmonitor-ran"
        with (repo / ".git" / "config").open("a") as f:
            f.write(f"[core]\n\tfsmonitor = touch {marker}\n")
        env = dict(CALLER_ENV, HOME=str(scratch))
        def name(cwd, sealed):
            # sealed: the environment every setup and replay runs in, with the case's HOME in its scratch
            e = module.base_env(scratch, {"env": {"HOME": str(scratch)}}) if sealed else env
            return subprocess.run(["git", "config", "user.name"], cwd=cwd, env=e, capture_output=True,
                                  text=True).stdout.strip()
        expect("r11: the test plants what an unsealed git reads (positive control)",
               name(scratch, False) == "planted" and name(bare, False) == "bare-planted", (name(scratch, False), name(bare, False)))
        expect("r11: sealed, git reads neither the planted global config nor the planted bare repository",
               name(scratch, True) == "" and name(bare, True) == "", (name(scratch, True), name(bare, True)))
        def fsmonitor_runs(sealed):
            marker.unlink(missing_ok=True)
            e = module.base_env(scratch, {}) if sealed else env
            subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "x"], env=e, capture_output=True)
            return marker.exists()
        expect("r12: an unsealed git runs a core.fsmonitor planted in repository config (positive control)",
               fsmonitor_runs(False))
        expect("r12: sealed, a core.fsmonitor planted in repository config does not run", not fsmonitor_runs(True))
        # core.hooksPath planted in repository config (r13: each seal key has its own test)
        hooks = scratch / "planted-hooks"
        hooks.mkdir()
        hook_marker = scratch / "hook-ran"
        (hooks / "pre-commit").write_text(f"#!/bin/sh\ntouch {hook_marker}\n")
        (hooks / "pre-commit").chmod(0o755)
        subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", str(hooks)], check=True, capture_output=True)
        def hook_runs(sealed):
            hook_marker.unlink(missing_ok=True)
            e = module.base_env(scratch, {}) if sealed else env
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@invalid", "commit", "-q",
                            "--allow-empty", "-m", "t"], env=e, capture_output=True)
            return hook_marker.exists()
        expect("r13: an unsealed git runs a hook from a planted core.hooksPath (positive control)", hook_runs(False))
        expect("r13: sealed, a planted core.hooksPath does not run", not hook_runs(True))
    with tempfile.TemporaryDirectory() as tmp:
        outer = Path(tmp).resolve()
        subprocess.run(["git", "init", "-q", str(outer)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(outer), "config", "user.name", "outer"], check=True, capture_output=True)
        inner = outer / "scratch"
        (inner / "sub").mkdir(parents=True)
        def outer_name(e):
            return subprocess.run(["git", "config", "user.name"], cwd=str(inner / "sub"), env=e, capture_output=True,
                                  text=True).stdout.strip()
        expect("r13: an unsealed git in a scratch inside a repository reads that repository (positive control)",
               outer_name(dict(CALLER_ENV, GIT_CONFIG_GLOBAL=os.devnull)) == "outer")
        expect("r13: sealed, git stops at the scratch (GIT_CEILING_DIRECTORIES)",
               outer_name(module.base_env(inner, {})) == "")
        saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_PARAMETERS", "PYTHONUSERBASE")}
        try:
            os.environ["GIT_CONFIG_PARAMETERS"] = "'user.name'='from-parent'"
            expect("r14: an unsealed git reads the caller's GIT_CONFIG_PARAMETERS (positive control)",
                   subprocess.run(["git", "config", "user.name"], cwd=str(inner / "sub"),
                                  env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull), capture_output=True,
                                  text=True).stdout.strip() == "from-parent")
            expect("r13: a GIT_* from the caller (GIT_CONFIG_PARAMETERS) does not reach a replay",
                   subprocess.run(["git", "config", "user.name"], cwd=str(inner / "sub"),
                                  env=module.base_env(inner, {}), capture_output=True, text=True).stdout.strip() == "")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def sealed_python_imports_nothing_planted() -> None:
    """P20 #1299 r12 A: with HOME in the scratch, a .pth in the user site-packages runs at every Python
    start; under the replay's environment it does not, and neither does a module in the working dir."""
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location("rules_check_py_sealed", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp).resolve()
        home = dict(CALLER_ENV, HOME=str(scratch))
        home.pop("PYTHONNOUSERSITE", None)
        site_dir = subprocess.run(["python3", "-c", "import site; print(site.getusersitepackages())"], env=home,
                                  capture_output=True, text=True).stdout.strip()
        marker = scratch / "pth-ran"
        Path(site_dir).mkdir(parents=True, exist_ok=True)
        Path(site_dir, "planted.pth").write_text(f"import pathlib; pathlib.Path({str(marker)!r}).touch()\n")
        (scratch / "json.py").write_text(f"import pathlib; pathlib.Path({str(marker)!r}).touch()\n")
        def ran(env, argv):
            marker.unlink(missing_ok=True)
            subprocess.run(argv, env=env, cwd=str(scratch), capture_output=True)
            return marker.exists()
        sealed = module.base_env(scratch, {"env": {"HOME": str(scratch)}})
        expect("r12 A: an unsealed python runs a .pth planted under a scratch HOME (positive control)",
               site_dir.startswith(str(scratch)) and ran(home, ["python3", "-c", "pass"]), site_dir)
        expect("r12 A: an unsealed `python3 -c` imports a json.py planted in its working directory (positive control)",
               ran(home, ["python3", "-c", "import json"]))
        expect("r12 A: sealed, python runs neither the planted .pth nor the planted json.py",
               not ran(sealed, ["python3", "-c", "import json"]))
        Path(site_dir, "plantedmod.py").write_text(f"import pathlib; pathlib.Path({str(marker)!r}).touch()\n")
        appending = ["python3", "-I", "-c", "import site, sys; sys.path.append(site.getusersitepackages()); "
                     "import plantedmod"]
        expect("r13: an enforcer that appends the user site imports a module planted under a scratch HOME "
               "(positive control)", ran(home, appending))
        expect("r13: sealed, the user site is the invoking user's (PYTHONUSERBASE), not the scratch HOME's",
               not ran(sealed, appending))
        elsewhere = scratch / "elsewhere"
        elsewhere.mkdir()
        saved = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = str(scratch)  # the caller's PYTHONPATH names the directory holding json.py
        try:
            from_parent = module.base_env(scratch, {"env": {"HOME": str(scratch)}})
        finally:
            if saved is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = saved
        marker.unlink(missing_ok=True)
        subprocess.run(["python3", "-c", "import json"], env=dict(CALLER_ENV, PYTHONPATH=str(scratch)),
                       cwd=str(elsewhere), capture_output=True)
        expect("r14: an unsealed python imports from the caller's PYTHONPATH (positive control)", marker.exists())
        marker.unlink(missing_ok=True)
        subprocess.run(["python3", "-c", "import json"], env=from_parent, cwd=str(elsewhere), capture_output=True)
        expect("r13: a PYTHON* from the caller (PYTHONPATH) does not reach a replay", not marker.exists())


def replays_run_in_the_sealed_env() -> None:
    """P20 #1299 r15 B: base_env is tested above; this proves every place a replay starts a process
    uses it (setup, the in-tree hook, a command case, the live registration). Each call's env is
    recorded and must carry the scratch HOME, the git seal and the Python seal, and no caller
    variable outside the allowlist."""
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location("rules_check_wiring", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seen = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    def recorder(argv, **kwargs):
        seen.append(kwargs.get("env") or {})
        return Done()

    real_run = module.subprocess.run
    os.environ["RULES_CHECK_LEAK_SENTINEL"] = "1"
    module.subprocess.run = recorder
    try:
        with tempfile.TemporaryDirectory(prefix="rules-check-") as tmp:
            scratch = Path(tmp)
            module.run_setup({"setup": [["mkdir", "-p", "{scratch}/d"]]}, scratch)
            event = {"tool_name": "Bash", "tool_input": {"command": "x"}}
            module.replay_in_tree(CHECK, {"event": event}, scratch, None)
            module.replay_in_tree(CHECK, {"args": ["{scratch}/f.txt"], "files": {"f.txt": "x"}}, scratch, None)
            # The harness's settings env is applied before the seals: one that names a seal key does
            # not undo it (P20 #1299 round 16, stratum B).
            real_harness_env = module.HARNESS_ENV
            module.HARNESS_ENV = {"GIT_CONFIG_GLOBAL": "/planted", "PYTHONSAFEPATH": ""}
            try:
                module.replay_live("true", {"event": event}, scratch)
            finally:
                module.HARNESS_ENV = real_harness_env
    finally:
        module.subprocess.run = real_run
        os.environ.pop("RULES_CHECK_LEAK_SENTINEL", None)
    def sealed(env):
        return (env.get("HOME", "").startswith(str(scratch)) and env.get("GIT_CONFIG_GLOBAL") == os.devnull
                and env.get("PYTHONSAFEPATH") == "1" and "RULES_CHECK_LEAK_SENTINEL" not in env)
    expect("r15: setup, the in-tree hook, a command case and the live registration all run sealed",
           len(seen) == 4 and all(sealed(e) for e in seen), [sorted(e)[:8] for e in seen])


def branch_first_replay_ignores_the_callers_escape() -> None:
    """P20 #1299 r15 B: a session that set BSTACK_ALLOW_MAIN_EDIT (the hook's documented escape)
    still replays branch-first as the harness would for any session: the escape is the caller's."""
    # In broomva/workspace this replays the workspace's own registry. Here the registry is the one
    # `correct.py init` writes into a fresh repository, which carries the same branch-first row.
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp).resolve() / "repo"
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True, timeout=60)
        env = dict(os.environ, RULES_CHECK_HOME=str(Path(tmp).resolve() / "home"), RULES_CHECK_HOST="ci-runner")
        env.pop("RULES_CHECK_ROOT", None)
        made = subprocess.run([sys.executable, "-I", str(CHECK.parent / "correct.py"), "init", "--root", str(repo)],
                              env=env, capture_output=True, text=True, timeout=600)
        expect("r15 setup: correct.py init gives the replay a registry with the branch-first row",
               made.returncode == 0, (made.stdout + made.stderr)[-400:])
        proc = subprocess.run(["python3", "-I", str(CHECK), "--replay-only", "--only", "branch-first"],
                              env=dict(env, RULES_CHECK_ROOT=str(repo), BSTACK_ALLOW_MAIN_EDIT="hotfix"),
                              capture_output=True, text=True, timeout=600)
    expect("r15: the caller's BSTACK_ALLOW_MAIN_EDIT does not turn branch-first's proofs into allows",
           proc.returncode == 0 and "PASS     hook         branch-first" in proc.stdout, proc.stdout[-400:])


def state_defaults_into_scratch() -> None:
    """P20 #1299 r14 B: a case that names no HOME or p9 home still replays against its scratch."""
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location("rules_check_defaults", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scratch = Path(tempfile.gettempdir(), "rules-check-defaults")
    env = module.base_env(scratch, {})
    inside = all(env[k].startswith(str(scratch) + os.sep) for k in ("HOME", "BROOMVA_P9_HOME"))
    expect("r14: with no case env, HOME and the p9 home are inside the scratch and the p9 session is fixed",
           inside and env.get("BROOMVA_P9_SESSION") == "rules-check", {k: env.get(k) for k in
                                                                        ("HOME", "BROOMVA_P9_HOME", "BROOMVA_P9_SESSION")})
    narrowed = module.base_env(scratch, {"env": {"HOME": "{scratch}/home6"}})
    expect("r14: a case narrows HOME within its scratch", narrowed["HOME"] == str(scratch / "home6"), narrowed["HOME"])


def fixture_refuses_code() -> None:
    """The write-file fixture judges the name where it writes (rules_check judges it first)."""
    import importlib.util  # noqa: PLC0415
    fixtures = CHECK.parent / "rules_fixtures.py"
    with tempfile.TemporaryDirectory(prefix="rules-check-") as tmp:
        for name, want in (("mod.py", 2), (".bashrc", 2), ("state.json", 0), (".gitignore", 0),
                           (".claude/settings.json", 2), ("r/.control/policy.yaml", 2), ("r/.broomva/notes.md", 0),
                           ("rules-check-notes.txt", 0)):
            proc = subprocess.run(["python3", "-I", str(fixtures), "write-file", str(Path(tmp, name)), "x"],
                                  capture_output=True, text=True)
            expect(f"r13: the write-file fixture {'refuses' if want else 'writes'} {name}", proc.returncode == want,
                   (proc.returncode, proc.stderr))
    with tempfile.TemporaryDirectory() as outer:
        target = Path(outer, "rules-check-linked")
        target.mkdir()
        Path(outer, "link").symlink_to(target)
        proc = subprocess.run(["python3", "-I", str(fixtures), "write-file", str(Path(outer, "link", "mod.py")), "x"],
                              capture_output=True, text=True)
        expect("r16: through a link into a scratch, the fixture judges the resolved path and refuses with exit 2",
               proc.returncode == 2 and "Traceback" not in proc.stderr, (proc.returncode, proc.stderr[-300:]))
    with tempfile.TemporaryDirectory(prefix="rules-check-") as tmp:
        # A directory a case names rules-check-* hides nothing above it (P20 #1299 round 18, stratum C).
        proc = subprocess.run(["python3", "-I", str(fixtures), "write-file",
                               str(Path(tmp, ".claude", "rules-check-x", "settings.json")), "x"],
                              capture_output=True, text=True)
        expect("r18: a rules-check-* directory under a tool's dot directory does not hide it", proc.returncode == 2,
               (proc.returncode, proc.stderr))


def main() -> None:
    code, rows = run([HOOK_RULE])
    expect("a working enforcer, registered and replayed live, passes", code == 0 and status(rows, "no-bad") == "PASS", rows)

    code, rows = run([HOOK_RULE], gate=ALLOW_ALL)
    expect("an enforcer that allows the recorded mistake fails", code == 1 and "expected block" in fails(rows, "no-bad"), rows)

    code, rows = run([HOOK_RULE], gate=BLOCK_ALL)
    expect("an enforcer that refuses everything fails on its control", code == 1 and "control 1" in fails(rows, "no-bad"), rows)

    code, rows = run([dict(HOOK_RULE, controls=[])])
    expect("proofs without a control fail", code == 1 and "`controls`" in fails(rows, "no-bad"), rows)

    code, rows = run([dict(HOOK_RULE, proofs=[{k: v for k, v in HOOK_RULE["proofs"][0].items() if k != "expect_reason"}])])
    expect("a hook proof without expect_reason fails", code == 1 and "expect_reason" in fails(rows, "no-bad"), rows)

    code, rows = run([HOOK_RULE], gate=GATE.replace("Gate X: BAD is refused; use GOOD", "some other gate"))
    expect("a refusal for another reason fails", code == 1 and "another reason" in fails(rows, "no-bad"), rows)

    code, rows = run([dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], remedy="use GOOD")])])
    expect("a refusal that names the fix passes its remedy check", code == 0, rows)
    code, rows = run([dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], remedy="use NOTHING")])])
    expect("a refusal that does not name the fix fails its remedy check", code == 1 and "name the fix" in fails(rows, "no-bad"), rows)

    crashy = GATE + "if 'GOOD' in cmd:\n    raise RuntimeError('crashed on the control')\n"
    code, rows = run([HOOK_RULE], gate=crashy)
    expect("r1: a hook that crashes on the control does not count as allowing it", code == 1 and "errored" in fails(rows, "no-bad"), rows)

    code, rows = run([dict(HOOK_RULE, enforcer=dict(HOOK_RULE["enforcer"], path="scripts/nope.py"))])
    expect("a missing enforcer fails", code == 1 and "enforcer missing" in fails(rows, "no-bad"), rows)

    # ── registration: replayed through exactly what the harness runs ──
    code, rows = run([HOOK_RULE], settings=hooks('echo "$CLAUDE_PROJECT_DIR/scripts/gate.py"'))
    expect("r1: an entry that only NAMES the hook (echo) fails", code == 1 and "not registered" in fails(rows, "no-bad"), rows)

    code, rows = run([HOOK_RULE], settings=hooks("python3 -c scripts/gate.py"))
    expect("r2: an entry that runs the path as code (python3 -c) fails", code == 1 and "not registered" in fails(rows, "no-bad"), rows)

    code, rows = run([HOOK_RULE], settings=hooks("/nonexistent/checkout/scripts/gate.py"))
    expect("r2: an entry pointing at a missing file fails (the harness would run nothing)", code == 1
           and ("not registered" in fails(rows, "no-bad") or "errored" in fails(rows, "no-bad")), rows)

    code, rows = run([HOOK_RULE], settings={"hooks": {}})
    expect("an unregistered hook fails", code == 1 and "not registered" in fails(rows, "no-bad"), rows)

    code, rows = run([dict(HOOK_RULE, enforcer={"path": "scripts/gate.py"})])
    expect("r1: a hook row without `registered` fails", code == 1 and ("must say where it is registered" in fails(rows, "no-bad")
           or "must declare it" in fails(rows, "no-bad")), rows)

    code, rows = run([HOOK_RULE], settings=hooks("python3 {tmp}/old/scripts/gate.py"),
                     extra={"../old/scripts/gate.py": ALLOW_ALL})
    expect("r3: another checkout's copy registered in project settings is replayed, and an allow-all copy FAILs",
           code == 1 and "live proof 1 expected block" in fails(rows, "no-bad"), rows)
    wrapper = hooks("if grep -q BAD; then exit 2; fi # $CLAUDE_PROJECT_DIR/scripts/gate.py")
    code, rows = run([HOOK_RULE], settings=wrapper)
    expect("r3: a shell wrapper that names the enforcer in a comment is not its registration",
           code == 1 and "not registered" in fails(rows, "no-bad"), rows)

    # ── P20 round 3 (STRUCTURAL): every registered row is judged by its live replay ──
    user_live = dict(HOOK_RULE, hosts=["mac"],
                     enforcer={"path": "scripts/gate.py", "registered": dict(REG, scope="user")})
    code, rows = run([user_live], settings=NO_HOOKS, top={"hosts": {"mac": ["the-mac"]}, "user_settings_on": ["mac"]}, host="the-mac",
                     home_settings=hooks("python3 {tmp}/main/scripts/gate.py"),
                     extra={"../main/scripts/gate.py": ALLOW_ALL})
    expect("r3: a live copy in another checkout that allows the mistake is a FAIL, not PENDING", code == 1
           and "after merge and pull" in fails(rows, "no-bad"), rows)
    code, rows = run([user_live], settings=NO_HOOKS, top={"hosts": {"mac": ["the-mac"]}, "user_settings_on": ["mac"]}, host="the-mac",
                     home_settings=hooks("python3 {tmp}/main/scripts/gate.py"),
                     extra={"../main/scripts/gate.py": GATE})
    expect("a live copy in another checkout that decides correctly passes", code == 0
           and status(rows, "no-bad") == "PASS", rows)
    tested = {"id": "no-bad", "rule": "x", "level": "hook", "enforcer": {"path": "scripts/gate.py", "registered": REG},
              "proof_test": [sys.executable, "-c", "pass"]}
    code, rows = run([tested])
    expect("r3: a registered row proven only by a test fails (it needs live proofs and controls)", code == 1
           and "needs `proofs` and `controls`" in fails(rows, "no-bad"), rows)
    code, rows = run([dict(tested, proof_test=None, proof_ref="another repo's tests")])
    expect("r3: a registered row proven only elsewhere fails (EXTERNAL is no hiding place)", code == 1
           and "needs `proofs` and `controls`" in fails(rows, "no-bad"), rows)
    code, rows = run([HOOK_RULE], settings=dict(hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'), env={"REASON": "other"}))
    expect("r3: a live registration that refuses for another reason fails (live replay is judged too)",
           code == 1 and "live proof 1 was refused for another reason" in fails(rows, "no-bad"), rows)
    two = dict(HOOK_RULE, proofs=HOOK_RULE["proofs"] + [{"from": "t", "expect_reason": "Gate X", "event": {
        "tool_name": "Bash", "tool_input": {"command": "run BAD2 now"}}}])
    code, rows = run([two], settings=dict(hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'), env={"ONLYFIRST": "1"}))
    expect("r3: every proof is replayed live, not only the first", code == 1
           and "live proof 2 expected block" in fails(rows, "no-bad"), rows)

    # ── the tool contract ──
    files = {"event": "PreToolUse", "tools": ["Write", "Edit"], "scope": "project"}
    def fcase(tool, path):
        return {"tool_name": tool, "tool_input": {"file_path": path}}
    file_rule = {"id": "no-bad", "rule": "x", "level": "hook", "canary": HOOK_RULE["canary"],
                 "enforcer": {"path": "scripts/gate.py", "registered": files},
                 "proofs": [{"from": "t", "expect_reason": "Gate X", "event": fcase("Write", "/x/BAD")},
                            {"from": "t", "expect_reason": "Gate X", "event": fcase("Edit", "/x/BAD")}],
                 "controls": [{"why": "t", "event": fcase("Write", "/x/GOOD")}]}
    both = {"hooks": {"PreToolUse": [{"matcher": "Write|Edit", "hooks": [
        {"command": 'python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'}]}]}}
    code, rows = run([file_rule], settings=both)
    expect("a contract whose every tool has a proof and a registration passes", code == 0
           and status(rows, "no-bad") == "PASS", rows)
    write_only = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [
        {"command": 'python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'}]}]}}
    code, rows = run([file_rule], settings=write_only)
    expect("r3: a contract tool the harness never dispatches to the enforcer fails (the MultiEdit hole)",
           code == 1 and "not registered for Edit" in fails(rows, "no-bad"), rows)
    code, rows = run([dict(file_rule, proofs=file_rule["proofs"][:1])], settings=both)
    expect("r3: a contract tool with no proof fails", code == 1 and "no proof exercises Edit" in fails(rows, "no-bad"), rows)
    code, rows = run([dict(file_rule, enforcer={"path": "scripts/gate.py", "registered": dict(files, tools=["Write"])},
                           proofs=file_rule["proofs"][:1])], settings=both, only=False)
    expect("r3: a registration for a tool no contract lists fails completeness", code == 1
           and "registered for Edit" in fails(rows, "registry-completeness"), rows)
    code, rows = run([dict(HOOK_RULE, enforcer={"path": "scripts/gate.py", "registered": {
        "event": "PreToolUse", "tool": "Bash", "scope": "project"}})])
    expect("the old single `tool:` key is refused with the fix", code == 1 and "registered.tools" in fails(rows, "no-bad"), rows)

    # ── command proofs: arguments only; the runner launches the enforcer ──
    code, rows = run([LINT_RULE], extra={"lint.py": LINT}, settings={"hooks": {}})
    expect("a command enforcer refuses the mistake and allows the control", code == 0 and status(rows, "lint") == "PASS", rows)
    code, rows = run([LINT_RULE], extra={"lint.py": "import sys; sys.exit(0)\n"}, settings={"hooks": {}})
    expect("a command enforcer that passes the mistake fails", code == 1, rows)
    code, rows = run([LINT_RULE], extra={"lint.py": "raise RuntimeError('crashed')\n"}, settings={"hooks": {}})
    expect("r1: a crashing lint (exit 1, no stated reason) does not count as refusing", code == 1
           and "another reason" in fails(rows, "lint"), rows)
    code, rows = run([LINT_RULE], extra={"lint.py": "import sys; sys.exit(2)\n"}, settings={"hooks": {}})
    expect("a lint that errors (exit 2) is not a decision", code == 1 and "errored" in fails(rows, "lint"), rows)
    forged = dict(LINT_RULE, proofs=[{"from": "t", "run": ["python3", "-c", "print('found BAD'); exit(1)", "lint.py"],
                                      "expect_output": "found BAD"}])
    code, rows = run([forged], extra={"lint.py": "import sys; sys.exit(0)\n"}, settings={"hooks": {}})
    expect("r2: a case may not run its own command (the forged-argv bypass)", code == 1 and "may not `run`" in fails(rows, "lint"), rows)
    applied = dict(LINT_RULE, applies=[sys.executable, "-I", "{root}/lint.py", "{root}/live.txt"])
    code, rows = run([applied], extra={"lint.py": LINT, "live.txt": "BAD"}, settings={"hooks": {}})
    expect("a lint the live repo violates fails even when its fixtures pass", code == 1 and "live repo violates" in fails(rows, "lint"), rows)

    # ── known misses: a ratchet on inputs the enforcer should refuse and does not yet ──
    miss = {"from": "t", "ticket": "BRO-1", "event": {"tool_name": "Bash", "tool_input": {"command": "run B4D"}}}
    code, rows = run([dict(HOOK_RULE, known_misses=[miss])])
    expect("a known miss that is still allowed is reported, not failed", code == 0
           and any("known miss" in n for n in rows[0]["notes"]), rows)
    fixed = dict(miss, event={"tool_name": "Bash", "tool_input": {"command": "run BAD too"}})
    code, rows = run([dict(HOOK_RULE, known_misses=[fixed])])
    expect("a known miss that is now refused fails until it moves to proofs", code == 1 and "now refused" in fails(rows, "no-bad"), rows)
    code, rows = run([dict(HOOK_RULE, known_misses=[{k: v for k, v in miss.items() if k != "ticket"}])])
    expect("a known miss without a ticket fails", code == 1 and "ticket" in fails(rows, "no-bad"), rows)

    # ── hosts: absent evidence is a FAIL where it must exist, SKIP elsewhere ──
    user_rule = dict(HOOK_RULE, enforcer={"path": "scripts/gate.py", "registered": dict(REG, scope="user")})
    code, rows = run([user_rule], settings=NO_HOOKS)
    expect("r2: a user-scope row without declared hosts fails", code == 1 and "declare the hosts" in fails(rows, "no-bad"), rows)
    declared = dict(user_rule, hosts=["mac"])
    code, rows = run([declared], settings=NO_HOOKS, top={"hosts": {"mac": ["the-mac"]}, "user_settings_on": ["mac"]}, host="ci-runner")
    expect("a user-scope row off its declared hosts is SKIP", code == 0 and status(rows, "no-bad") == "SKIP", rows)
    code, rows = run([declared], settings=NO_HOOKS, top={"hosts": {"mac": ["the-mac"]}, "user_settings_on": ["mac"]}, host="the-mac", home_settings={"permissions": {}})
    expect("r2: on a declared host, user settings without the hook FAIL (wiping hooks is not a SKIP)",
           code == 1 and "not registered" in fails(rows, "no-bad"), rows)
    code, rows = run([declared], settings=NO_HOOKS, top={"hosts": {"mac": ["the-mac"]}, "user_settings_on": ["mac"]}, host="Mac.lan,the-mac",
                     home_settings={"permissions": {}})
    expect("a declared host is matched on any of its names (a DHCP hostname cannot turn FAIL into SKIP)",
           code == 1 and "not registered" in fails(rows, "no-bad"), rows)
    code, rows = run([declared], settings=NO_HOOKS, top={"hosts": {"mac": ["the-mac"]}, "user_settings_on": ["mac"]}, host="the-mac",
                     home_settings=hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'))
    expect("on a declared host with the hook registered, the user-scope row passes", code == 0
           and status(rows, "no-bad") == "PASS", rows)
    local = {"id": "loc", "rule": "x", "level": "test", "enforcer": {"path": "~/gone.py"}, "proof_ref": "x",
             "hosts": ["mac"]}
    code, rows = run([local], top={"hosts": {"mac": ["the-mac"]}, "user_settings_on": ["mac"]}, host="the-mac")
    expect("r2: a machine-local enforcer missing on its declared host FAILS", code == 1 and "enforcer missing" in fails(rows, "loc"), rows)
    code, rows = run([local], top={"hosts": {"mac": ["the-mac"]}, "user_settings_on": ["mac"]}, host="elsewhere")
    expect("the same row on another host is SKIP", code == 0 and status(rows, "loc") == "SKIP", rows)

    # ── rows that are not mechanisms ──
    code, rows = run([{"id": "g", "rule": "x", "level": "gap", "ticket": "BRO-1"}])
    expect("a gap without a target fails", code == 1, rows)
    code, rows = run([{"id": "g", "rule": "x", "level": "gap", "ticket": "BRO-1",
                       "target": {"level": "hook", "mechanism": "a hook"}}])
    expect("a gap with ticket and target reports GAP", code == 0 and status(rows, "g") == "GAP", rows)
    code, rows = run([{"id": "j", "rule": "x", "level": "judgment"}])
    expect("a judgment rule without a reason fails", code == 1, rows)
    code, rows = run([{"id": "j", "rule": "x", "level": "judgment", "judgment": "why", "occurrences": ["a", "b"]}])
    expect("a judgment rule with two occurrences is a REPEAT", code == 0 and status(rows, "j") == "REPEAT", rows)
    code, rows = run([{"id": "x", "rule": "x", "level": "ci"}])
    expect("`ci` is no longer a level (where a check runs is runs_in)", code == 1, rows)
    ext = {"id": "ext", "rule": "x", "level": "test", "enforcer": {"path": "scripts/gate.py"}, "proof_ref": "y"}
    code, rows = run([ext], settings=NO_HOOKS)
    expect("a rule the harness does not run here, proven in another repo, is EXTERNAL", code == 0
           and status(rows, "ext") == "EXTERNAL", rows)

    # ── fresh round 1 (#1298): the harness, not the row, decides what must be replayed ──
    echo = hooks('echo "$CLAUDE_PROJECT_DIR/scripts/gate.py"')
    dead = hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"')
    dead_gate = "import sys; sys.stdin.read()\n"  # registered, allows everything
    code, rows = run([dict(ext, level="hook")], settings=dead, gate=dead_gate)
    expect("r4: dropping `registered` and citing a reference cannot make a live dead hook EXTERNAL", code == 1
           and "must declare it" in fails(rows, "ext"), rows)
    relabel = {"id": "no-bad", "rule": "x", "level": "judgment", "judgment": "y",
               "enforcer": HOOK_RULE["enforcer"]}
    code, rows = run([relabel], settings=echo, only=False)
    expect("r4: relabelling a row `judgment` leaves its registration unowned, and completeness FAILs", code == 1
           and "owned by no row" in fails(rows, "registry-completeness"), rows)
    code, rows = run([relabel], settings=dead, gate=dead_gate)
    expect("r4: a judgment row whose enforcer the harness runs FAILs (it must be a replayed row)", code == 1
           and "cannot hold an enforcer" in fails(rows, "no-bad"), rows)
    wide = {"hooks": {"PreToolUse": [{"matcher": "Bash|[A-Z].*", "hooks": [
        {"command": 'python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'}]}]}}
    code, rows = run([HOOK_RULE], settings=wide, only=False)
    expect("r4: a matcher alternative that only overlaps the contract (`[A-Z].*`) fails completeness", code == 1
           and "[A-Z].*" in fails(rows, "registry-completeness"), rows)
    local = json.dumps(dict(typed(hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"')), env={"BLOCKALL": "1"}))
    code, rows = run([HOOK_RULE], extra={".claude/settings.local.json": local})
    expect("r4: settings.local.json is read: its registration and env are replayed (it refuses the control)", code == 1
           and "live control 1 expected allow" in fails(rows, "no-bad"), rows)
    # Ownership needs ONE simple invocation of the enforcer (P20 #1298 fresh round 1): a compound or
    # wrapped command's decision cannot be attributed to one script, so it owns no row.
    for form in ('exec python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"', 'python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"; true',
                 "sh -c 'python3 \"$CLAUDE_PROJECT_DIR/scripts/gate.py\"'",
                 'python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py" </dev/null; python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"',
                 'env -u "$CLAUDE_PROJECT_DIR/scripts/gate.py" python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"',
                 'python3 -W "$CLAUDE_PROJECT_DIR/scripts/gate.py" "$CLAUDE_PROJECT_DIR/scripts/gate.py"',
                 'BASH_ENV="$CLAUDE_PROJECT_DIR/scripts/gate.py" python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'):
        code, rows = run([HOOK_RULE], settings=hooks(form))
        expect(f"r5: a compound or wrapped registration owns no row ({form[:34]}...)", code == 1
               and "not registered" in fails(rows, "no-bad"), rows)
    code, rows = run([HOOK_RULE], settings=hooks('python3 -I "$CLAUDE_PROJECT_DIR/scripts/gate.py"'))
    expect("r5: a simple invocation with an allowlisted interpreter flag owns the row", code == 0
           and status(rows, "no-bad") == "PASS", rows)
    for key in ("BASH_ENV", "PYTHONPATH", "HOME"):
        code, rows = run([HOOK_RULE], settings=dict(hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'), env={key: "/tmp/x"}),
                         only=False)
        expect(f"r5: a settings env that sets {key} fails completeness (code runs before every hook script)", code == 1
               and f"sets {key}" in fails(rows, "registry-completeness"), rows)
    code, rows = run([HOOK_RULE], settings=dict(hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'),
                                               env={"DISABLE_AUTOUPDATER": "1"}), only=False)
    expect("r6: a settings env key on the allowlist does not fail completeness", code == 0
           and "env" not in fails(rows, "registry-completeness"), rows)
    code, rows = run([dict(HOOK_RULE, enforcer=dict(HOOK_RULE["enforcer"], registered=dict(REG, tools=["mcp__x__.*"])),
                           proofs=[dict(HOOK_RULE["proofs"][0], event={"tool_name": "mcp__x__save", "tool_input": {"command": "run BAD"}})],
                           controls=[dict(HOOK_RULE["controls"][0], event={"tool_name": "mcp__x__save", "tool_input": {"command": "run GOOD"}})])],
                     settings={"hooks": {"PreToolUse": [{"matcher": "mcp__x__.*", "hooks": [
                         {"command": 'python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'}]}]}}, only=False)
    expect("a pattern matcher listed verbatim in the contract, with a proof it covers, passes", code == 0, rows)

    # ── completeness: fails closed ──
    code, rows = run([], only=False)
    expect("r1: an empty registry fails", code == 1, rows)
    code, rows = run([HOOK_RULE], only=False, policy=None)
    expect("r2: an unreadable policy.yaml fails completeness (unknown is not complete)", code == 1
           and "cannot read" in fails(rows, "registry-completeness"), rows)
    gated = "gates:\n  hard:\n    - id: G1\n      rule: x\n      pattern: BAD\n"
    code, rows = run([HOOK_RULE], only=False, policy=gated)
    expect("a patterned gate with no row fails completeness", code == 1 and "G1" in fails(rows, "registry-completeness"), rows)
    code, rows = run([dict(HOOK_RULE, policy_gate="G1")], only=False, policy=gated)
    expect("a gate covered by a row passes completeness", code == 0, rows)
    stray = hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"')
    stray["hooks"]["UserPromptSubmit"] = [{"hooks": [{"command": "python3 scripts/stray.py"}]}]
    code, rows = run([HOOK_RULE], only=False, settings=stray)
    expect("r2: a UserPromptSubmit hook with no row fails completeness", code == 1
           and "stray.py" in fails(rows, "registry-completeness"), rows)
    task = hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"')
    task["hooks"]["TaskCompleted"] = [{"hooks": [{"command": "python3 scripts/stray.py"}]}]
    code, rows = run([HOOK_RULE], only=False, settings=task)
    expect("r3: a hook on an event outside the old fixed list (TaskCompleted) fails completeness", code == 1
           and "stray.py" in fails(rows, "registry-completeness"), rows)
    code, rows = run([HOOK_RULE], only=False, extra={".claude/settings.local.json": json.dumps(typed(
        {"hooks": {"Stop": [{"hooks": [{"command": "python3 scripts/stray.py"}]}]}}))})
    expect("r3: a blocking hook in settings.local.json fails completeness", code == 1
           and "stray.py" in fails(rows, "registry-completeness"), rows)
    code, rows = run([HOOK_RULE], only=False, settings=stray, top={"hooks_not_rules": {"stray.py": "never blocks"}})
    expect("a hook listed in hooks_not_rules passes completeness", code == 0, rows)

    # ── the unified layout (BRO-3200): .broomva/<X> is read, and read first ──
    code, rows = run([HOOK_RULE], layout=".broomva")
    expect("a registry at .broomva/rules.yaml is found without --registry", code == 0
           and status(rows, "no-bad") == "PASS", rows)
    code, rows = run([HOOK_RULE], only=False, policy=gated, layout=".broomva")
    expect("the policy at .broomva/policy.yaml is the one completeness reads", code == 1
           and "G1" in fails(rows, "registry-completeness"), rows)

    # ── round 2 (#1298): the hook ENTRY the harness obeys, not only its command line ──
    gate_cmd = 'python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'
    for field, value in (("async", True), ("asyncRewake", True), ("once", True), ("if", "Bash(echo never *)"),
                         ("type", "prompt")):
        entry = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": gate_cmd, field: value}]}]}}
        code, rows = run([HOOK_RULE], settings=entry)
        expect(f"r5: a registration with {field}={value!r} does not block, so the row FAILs", code == 1
               and "inert" in fails(rows, "no-bad"), rows)
    for where in (".claude/settings.json", ".claude/settings.local.json"):
        off = dict(hooks(gate_cmd), disableAllHooks=True) if where.endswith("settings.json") else {"disableAllHooks": True}
        extra = {} if where.endswith("settings.json") else {where: json.dumps(off)}
        code, rows = run([HOOK_RULE], settings=off if not extra else None, extra=extra)
        expect(f"r5: disableAllHooks in {where} turns the hook off, so the row FAILs", code == 1
               and "disableAllHooks" in fails(rows, "no-bad"), rows)
    code, rows = run([HOOK_RULE], extra={".claude/settings.local.json": json.dumps({"allowManagedHooksOnly": True})})
    expect("r5: allowManagedHooksOnly drops project hooks, so the row FAILs", code == 1
           and "allowManagedHooksOnly" in fails(rows, "no-bad"), rows)
    slow = GATE.replace("ti = json.load", "import time; time.sleep(3)\nti = json.load")
    code, rows = run([HOOK_RULE], gate=slow, settings={"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"command": gate_cmd, "timeout": 1}]}]}})
    expect("r5: a hook slower than its registered timeout lets the action through, so the row FAILs", code == 1
           and "live proof 1 expected block" in fails(rows, "no-bad"), rows)
    code, rows = run([dict(HOOK_RULE, hosts=["macbook"])], top={"hosts": {"mac": ["the-mac"]}})
    expect("r5: a host group the registry does not declare FAILs (it would read SKIP everywhere)", code == 1
           and "not declared" in fails(rows, "no-bad"), rows)
    elsewhere = hooks(gate_cmd)
    elsewhere["hooks"]["UserPromptSubmit"] = [{"hooks": [{"command": "{tmp}/evil2/gate.py"}]}]
    elsewhere["hooks"]["PreToolUse"].append({"matcher": "Read", "hooks": [{"command": "{tmp}/evil2/gate.py"}]})
    code, rows = run([HOOK_RULE], settings=elsewhere, only=False, extra={"../evil2/gate.py": BLOCK_ALL})
    expect("r5: a blocking hook that only shares the enforcer's file NAME is owned by no row", code == 1
           and "evil2" not in "" and "owned by no row" in fails(rows, "registry-completeness"), rows)
    permission = hooks(gate_cmd)
    permission["hooks"]["PermissionRequest"] = [{"matcher": "Bash", "hooks": [{"command": gate_cmd}]}]
    code, rows = run([HOOK_RULE], settings=permission, only=False)
    expect("r5: the enforcer registered on an event no row declares (PermissionRequest) FAILs", code == 1, rows)

    # ── the ratchet: a row may not lower its own bar against the base branch unrecorded ──
    code, rows = run([HOOK_RULE], only=False, base={"rules": [HOOK_RULE]})
    expect("an unchanged registry passes the ratchet", code == 0 and status(rows, "registry-ratchet") == "PASS", rows)
    lowered = dict(HOOK_RULE, level="test", enforcer={"path": "scripts/gate.py"})
    code, rows = run([lowered], settings=NO_HOOKS, only=False, base={"rules": [HOOK_RULE]})
    expect("r5: dropping `registered` and lowering the level against the base FAILs the ratchet", code == 1
           and "registered removed" in fails(rows, "registry-ratchet"), rows)
    recorded = dict(lowered, demoted=[{"what": "registered removed", "reason": "r", "ticket": "BRO-1"},
                                      {"what": "level hook -> test", "reason": "r", "ticket": "BRO-1"}])
    code, rows = run([recorded], settings=NO_HOOKS, only=False, base={"rules": [HOOK_RULE]})
    expect("a recorded demotion passes the ratchet", status(rows, "registry-ratchet") == "PASS", rows)
    user_moved = dict(HOOK_RULE, hosts=["mac"], enforcer={"path": "scripts/gate.py", "registered": dict(REG, scope="user")})
    code, rows = run([user_moved], settings=NO_HOOKS, only=False, top={"hosts": {"mac": ["the-mac"]}},
                     base={"rules": [HOOK_RULE], "hosts": {"mac": ["the-mac"]}})
    expect("r5: moving a project row to user scope (where --ci skips it) FAILs the ratchet", code == 1
           and "registered.scope project -> user" in fails(rows, "registry-ratchet"), rows)
    code, rows = run([HOOK_RULE], only=False, base={"rules": [HOOK_RULE, dict(HOOK_RULE, id="gone")]})
    expect("r5: a removed row FAILs the ratchet unless it is retired", code == 1
           and "gone was removed" in fails(rows, "registry-ratchet"), rows)
    code, rows = run([HOOK_RULE], only=False, top={"hosts": {"mac": ["nope"]}},
                     base={"rules": [HOOK_RULE], "hosts": {"mac": ["the-mac"]}})
    expect("r5: changing the top-level host patterns FAILs the ratchet unless recorded", code == 1
           and "top-level hosts" in fails(rows, "registry-ratchet"), rows)

    # ── round 3 (#1298 round 2's breaks): allowlists, not deny-lists ──
    for key, value in (("shell", "powershell"), ("args", []), ("onFailure", "continue"), ("once", True),
                       ("rewakeMessage", "x")):
        entry = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": gate_cmd, key: value}]}]}}
        code, rows = run([HOOK_RULE], settings=entry)
        expect(f"r6: a hook-entry key outside the allowlist ({key}) is not vouched for, so the row FAILs", code == 1
               and "outside the hook-entry allowlist" in fails(rows, "no-bad"), rows)
    documented = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": gate_cmd, "timeout": 5, "_purpose": "documentation"}]}]}}
    code, rows = run([HOOK_RULE], settings=documented)
    expect("an entry with only allowlisted keys and `_` documentation keys passes", code == 0, rows)
    code, rows = run([HOOK_RULE], settings=dict(hooks(gate_cmd), env={"DISABLE_GATE": "1"}))
    expect("r6: a settings env that disables the gate is replayed, so the row FAILs by behaviour", code == 1
           and "live proof 1 expected block" in fails(rows, "no-bad"), rows)
    code, rows = run([HOOK_RULE], extra={".claude/settings.local.json": json.dumps({"env": {"DISABLE_GATE": "1"}})})
    expect("r6: the same env in settings.local.json is replayed too", code == 1
           and "live proof 1 expected block" in fails(rows, "no-bad"), rows)
    post = dict(HOOK_RULE, enforcer=dict(HOOK_RULE["enforcer"], registered=dict(REG, event="PostToolUse")))
    code, rows = run([post], settings={"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [{"command": gate_cmd}]}]}})
    expect("r6: an enforcer on PostToolUse (after the action ran) FAILs", code == 1
           and "runs after the action" in fails(rows, "no-bad"), rows)
    deny = ("import json, sys\nev = json.load(sys.stdin)\ncmd = (ev.get('tool_input') or {}).get('command', '')\n"
            "if 'BAD' in cmd:\n    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PermissionRequest', "
            "'decision': {'behavior': 'deny', 'message': 'Gate X: use GOOD'}}}))\n")
    perm = dict(HOOK_RULE, enforcer=dict(HOOK_RULE["enforcer"], registered=dict(REG, event="PermissionRequest")))
    code, rows = run([perm], gate=deny, settings={"hooks": {"PermissionRequest": [{"matcher": "Bash", "hooks": [
        {"command": gate_cmd}]}]}})
    expect("a PermissionRequest denial (decision.behavior deny) is a refusal (no false FAIL)", code == 0, rows)
    sneaky = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], env={"GATE_FORCE": "1"})])
    code, rows = run([sneaky])
    expect("r6: a proof env outside the state-relocation allowlist FAILs (it could fake a refusal)", code == 1
           and "env GATE_FORCE is outside" in fails(rows, "no-bad"), rows)
    outside = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[["touch", "{root}/scripts/x"]])])
    code, rows = run([outside])
    expect("r6: a proof setup that touches outside {scratch} FAILs", code == 1
           and "outside {scratch}" in fails(rows, "no-bad"), rows)
    shelly = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[["sh", "-c", "true"]])])
    code, rows = run([shelly])
    expect("r6: a proof setup that runs a shell FAILs", code == 1 and "is not one of" in fails(rows, "no-bad"), rows)
    opaque = hooks(gate_cmd)
    opaque["hooks"]["PreToolUse"].append({"matcher": "Bash", "hooks": [{"command": 'X=1; "$CLAUDE_PROJECT_DIR"/evil.sh'}]})
    code, rows = run([HOOK_RULE], settings=opaque, only=False)
    expect("r6: a blocking hook that cannot be parsed into a command fails completeness", code == 1
           and "cannot be parsed" in fails(rows, "registry-completeness"), rows)
    code, rows = run([HOOK_RULE], root_name="re po")
    expect("a checkout path with a space still parses and passes", code == 0, rows)
    code, rows = run([dict(HOOK_RULE, level="judgment", judgment="y")], root_name="re po", settings=hooks(gate_cmd))
    expect("r6: with a space in the path, a relabelled row still FAILs", code == 1, rows)

    # ── the content ratchet ──
    swapped = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], event={"tool_name": "Bash",
                                                                          "tool_input": {"command": "run BAD3"}})])
    code, rows = run([swapped], only=False, base={"rules": [HOOK_RULE]})
    expect("r6: swapping a proof for another (same count) FAILs the ratchet", code == 1
           and "proof 1 removed or changed" in fails(rows, "registry-ratchet"), rows)
    weak = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], expect_reason=".")])
    code, rows = run([weak], only=False, base={"rules": [HOOK_RULE]})
    expect("r6: weakening expect_reason FAILs the ratchet", code == 1
           and "proof 1 removed or changed" in fails(rows, "registry-ratchet"), rows)
    prefix = dict(swapped, demoted=[{"what": "p", "reason": "r", "ticket": "BRO-1"}])
    code, rows = run([prefix], only=False, base={"rules": [HOOK_RULE]})
    expect("r6: a demotion that only prefixes the change does not record it", code == 1
           and "registry-ratchet" in [r["id"] for r in rows if r["status"] == "FAIL"], rows)
    exact = dict(swapped, demoted=[{"what": "proof 1 removed or changed", "reason": "r", "ticket": "BRO-1"}])
    code, rows = run([exact], only=False, base={"rules": [HOOK_RULE]})
    expect("an exact, new demotion records the change", status(rows, "registry-ratchet") == "PASS", rows)
    old_record = [{"what": "level hook -> sensor", "reason": "r", "ticket": "BRO-1"}]
    reused = dict(HOOK_RULE, level="sensor", demoted=old_record)
    code, rows = run([reused], only=False, base={"rules": [dict(HOOK_RULE, demoted=old_record)]})
    expect("r6: a demotion carried over from the base does not authorize a new lowering", code == 1
           and "level hook -> sensor" in fails(rows, "registry-ratchet"), rows)
    renamed = dict(HOOK_RULE, id="no-bad-2", proofs=HOOK_RULE["proofs"][:1], controls=HOOK_RULE["controls"][:1])
    two = dict(HOOK_RULE, proofs=HOOK_RULE["proofs"] + [dict(HOOK_RULE["proofs"][0], event={
        "tool_name": "Bash", "tool_input": {"command": "run BAD again"}})])
    code, rows = run([renamed], only=False, top={"retired": [{"id": "no-bad", "reason": "r", "ticket": "BRO-1"}]},
                     base={"rules": [two]})
    expect("r6: renaming a row and retiring the old id cannot launder a lowering", code == 1
           and "proof 2 removed or changed" in fails(rows, "registry-ratchet"), rows)
    event_moved = dict(HOOK_RULE, enforcer=dict(HOOK_RULE["enforcer"], registered=dict(REG, event="PermissionRequest")))
    code, rows = run([event_moved], only=False, base={"rules": [HOOK_RULE]},
                     settings={"hooks": {"PermissionRequest": [{"matcher": "Bash", "hooks": [{"command": gate_cmd}]}]}})
    expect("r6: changing registered.event FAILs the ratchet", code == 1
           and "registered.event PreToolUse -> PermissionRequest" in fails(rows, "registry-ratchet"), rows)
    code, rows = run([HOOK_RULE], only=False, top={"hooks_not_rules": {"extra.py": "x"}}, base={"rules": [HOOK_RULE]})
    expect("r6: widening hooks_not_rules FAILs the ratchet", code == 1
           and "hooks_not_rules" in fails(rows, "registry-ratchet"), rows)
    code, rows = run([HOOK_RULE], only=False, top={"class_threshold": 5}, base={"rules": [HOOK_RULE]})
    expect("r6: raising class_threshold FAILs the ratchet", code == 1
           and "class_threshold" in fails(rows, "registry-ratchet"), rows)
    with_miss = dict(HOOK_RULE, known_misses=[miss])
    code, rows = run([HOOK_RULE], only=False, base={"rules": [with_miss]})
    expect("r6: dropping a known miss that did not become a proof FAILs the ratchet", code == 1
           and "known miss 1 dropped" in fails(rows, "registry-ratchet"), rows)
    code, rows = run([HOOK_RULE], only=False, args=["--base", "no-such-ref"])
    expect("r6: a base ref that does not resolve FAILs the ratchet (not 'new registry')", code == 1
           and "does not resolve" in fails(rows, "registry-ratchet"), rows)

    tightened = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], remedy="use GOOD")])
    code, rows = run([tightened], only=False, base={"rules": [HOOK_RULE]})
    expect("adding a remedy to a proof tightens it and passes the ratchet", status(rows, "registry-ratchet") == "PASS", rows)
    branch = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[["git", "init", "-q", "-b", "feat/x", "{scratch}/r"]])])
    code, rows = run([branch])
    expect("a setup argument that is not a path (a branch name with a slash) is allowed", code == 0, rows)
    up = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[["touch", "../escape"]])])
    code, rows = run([up])
    expect("r6: a setup path that climbs out of {scratch} (..) FAILs", code == 1 and "outside {scratch}" in fails(rows, "no-bad"), rows)

    # ── round 3 stratum A: the boundary's own leaks ──
    for argv in (["git", "-c", "alias.x=!touch /tmp/rules-escape", "x"], ["git", "--git-dir=/tmp/escaped.git", "init", "-q"],
                 ["git", "-C", "/tmp", "init"], ["touch", "{scratch}/../escape"], ["mkdir", "-p", "/tmp/escape"]):
        bad = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[argv])])
        code, rows = run([bad])
        expect(f"r7: setup {argv[:3]} is refused (not an allowed form, or escapes scratch)", code == 1
               and ("not one of the allowed forms" in fails(rows, "no-bad") or "outside {scratch}" in fails(rows, "no-bad")), rows)
    trav = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], env={"HOME": "{scratch}/../outside"})])
    code, rows = run([trav])
    expect("r7: a case env that climbs out of {scratch} (..) is refused", code == 1
           and "must point into {scratch}" in fails(rows, "no-bad"), rows)
    wrong_event = ("import json, sys\nev = json.load(sys.stdin)\ncmd = (ev.get('tool_input') or {}).get('command', '')\n"
                   "if 'BAD' in cmd:\n    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PermissionRequest', "
                   "'decision': {'behavior': 'deny', 'message': 'Gate X: use GOOD'}}}))\n")
    code, rows = run([HOOK_RULE], gate=wrong_event)
    expect("r7: a PreToolUse hook answering in PermissionRequest's format is not a refusal", code == 1
           and "expected block" in fails(rows, "no-bad"), rows)
    labelled = ("import json, sys\nev = json.load(sys.stdin)\ncmd = (ev.get('tool_input') or {}).get('command', '')\n"
                "if 'BAD' in cmd:\n    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PermissionRequest', "
                "'permissionDecision': 'deny', 'permissionDecisionReason': 'Gate X: use GOOD'}}))\n")
    code, rows = run([HOOK_RULE], gate=labelled)
    expect("r7: a refusal labelled for another event (hookEventName) is not a refusal for this one", code == 1
           and "expected block" in fails(rows, "no-bad"), rows)
    unlabelled = ("import json, sys\nev = json.load(sys.stdin)\ncmd = (ev.get('tool_input') or {}).get('command', '')\n"
                  "if 'BAD' in cmd:\n    print(json.dumps({'hookSpecificOutput': {"
                  "'decision': {'behavior': 'deny', 'message': 'Gate X: use GOOD'}}}))\n")
    code, rows = run([HOOK_RULE], gate=unlabelled)
    expect("r7: PermissionRequest's refusal form, unlabelled, is not a PreToolUse refusal", code == 1
           and "expected block" in fails(rows, "no-bad"), rows)
    flagged = dict(HOOK_RULE, enforcer=dict(HOOK_RULE["enforcer"], args=["--relaxed"]))
    code, rows = run([flagged], only=False, base={"rules": [HOOK_RULE]},
                     settings=hooks('python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py" --relaxed'))
    expect("r7: adding enforcer args is a recorded change (the ratchet FAILs without a demotion)", code == 1
           and "enforcer.args changed" in fails(rows, "registry-ratchet"), rows)

    # ── continuation directive: strict entry values, whole-stdout JSON, matcher subset, fixtures ──
    for hook, label in (({"command": gate_cmd}, "no type"), ({"type": "command", "command": gate_cmd, "timeout": 0}, "timeout 0"),
                        ({"type": "command", "command": gate_cmd, "timeout": "5"}, "timeout '5'"),
                        ({"type": "command", "command": gate_cmd, "statusMessage": 123}, "statusMessage 123")):
        code, rows = run([HOOK_RULE], settings={"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [hook]}]}}, raw=True)
        expect(f"r8: an entry the harness's schema rejects ({label}) FAILs", code == 1 and "inert" in fails(rows, "no-bad"), rows)
    code, rows = run([dict(HOOK_RULE, enforcer=dict(HOOK_RULE["enforcer"], registered=dict(REG, tools=["Bash"])))],
                     settings={"hooks": {"PreToolUse": [{"matcher": "(?i)Bash", "hooks": [{"command": gate_cmd}]}]}})
    expect("r8: a matcher outside the shared regex subset ((?i)Bash) FAILs", code == 1
           and "outside the subset" in fails(rows, "no-bad"), rows)
    chatty = GATE.replace("ti = json.load", "print('loading gate')\nti = json.load")
    code, rows = run([HOOK_RULE], gate=chatty)
    expect("r8: a JSON decision after another stdout line is not a decision (the harness ignores it)", code == 1
           and "expected block" in fails(rows, "no-bad"), rows)
    escape = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[
        ["python3", "-I", "{root}/scripts/rules_fixtures.py", "write-file", "{scratch}/../../escape.sh", "x"]])])
    code, rows = run([escape])
    expect("r8: a fixture that writes outside {scratch} FAILs", code == 1
           and "rules_fixtures.py writes" in fails(rows, "no-bad"), rows)
    for planted in ("{scratch}/r/.git/config", "{scratch}/r/.git", "{scratch}/.gitconfig", "{scratch}/r/.GIT/config"):
        plant = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[
            ["python3", "-I", "{root}/scripts/rules_fixtures.py", "write-file", planted, "[core]\\n fsmonitor = x"]])])
        code, rows = run([plant])
        expect(f"P20 #1299 r11: a setup that writes {planted} (git would read it) FAILs", code == 1
               and "a path git reads" in fails(rows, "no-bad"), rows)
    sealed_git_reads_nothing_planted()
    planted_p9 = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[
        ["python3", "-I", "{root}/scripts/rules_fixtures.py", "p9-wait", "{scratch}/evil"]])])
    code, rows = run([planted_p9])
    expect("P20 #1299 r12 A: a p9-wait fixture importing p9 from a case-chosen directory FAILs", code == 1
           and "p9-wait must name" in fails(rows, "no-bad"), rows)
    sealed_python_imports_nothing_planted()
    # P20 #1299 round 13 (STRUCTURAL): a case writes data, never code an enforcer could import or source.
    for step in (["python3", "-I", "{root}/scripts/rules_fixtures.py", "write-file",
                  "{scratch}/h/.config/broomva/fleet/meta/provider_sensors.py", "x"],
                 ["python3", "-I", "{root}/scripts/rules_fixtures.py", "write-file", "{scratch}/h/.zshenv", "x"],
                 ["touch", "{scratch}/h/site-packages/yaml.py"]):
        code_case = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[step])])
        code, rows = run([code_case])
        expect(f"r13: a setup that writes code ({step[-2] if step[0] == 'python3' else step[-1]}) FAILs",
               code == 1 and ("not a data file" in fails(rows, "no-bad")
                              or "not data a case writes" in fails(rows, "no-bad")), rows)
    lint = dict(LINT_RULE, controls=[dict(LINT_RULE["controls"][0], files={"site/yaml.py": "x"})])
    code, rows = run([lint], extra={"lint.py": LINT}, settings={"hooks": {}})
    expect("r13: a command case's files entry that is code FAILs where it is written", code == 1
           and "not a data file" in fails(rows, "lint"), rows)
    for name in ("{scratch}/h/.claude/settings.json", "{scratch}/r/.control/policy.yaml", "{scratch}/r/.CONTROL/policy.yaml",
                 "{scratch}/r/.broomva/preauth.yaml", "{scratch}/h/.hidden.json"):
        step = ["python3", "-I", "{root}/scripts/rules_fixtures.py", "write-file", name, "x"]
        written = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[step])])
        code, rows = run([written])
        expect(f"r14: a setup that fills {name} (tool config, a governance file, a dot name) FAILs",
               code == 1 and "write-file" in fails(rows, "no-bad"), rows)
    empty_policy = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], setup=[
        ["mkdir", "-p", "{scratch}/r/.control"], ["touch", "{scratch}/r/.control/policy.yaml"]])])
    code, rows = run([empty_policy])
    expect("r14: a governance file created empty with touch is allowed (the row runs and passes)", code == 0, rows)
    registered_files = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], files={"site/yaml.py": "x"})])
    code, rows = run([registered_files])
    expect("r14: a registered case's files entry that is code FAILs before the replay", code == 1
           and "files site/yaml.py is not a data file" in fails(rows, "no-bad"), rows)
    state_defaults_into_scratch()
    replays_run_in_the_sealed_env()
    branch_first_replay_ignores_the_callers_escape()
    fixture_refuses_code()
    for name in ("/tmp/rules-check-escape", "on-main/.git/config", "a/../../escape", "x/.Git/config"):
        lint = dict(LINT_RULE, controls=[dict(LINT_RULE["controls"][0], files={name: "x"})])
        code, rows = run([lint], extra={"lint.py": LINT}, settings={"hooks": {}})
        expect(f"P20 #1299 r12: a command case's files key {name!r} outside {{scratch}} or under .git FAILs",
               code == 1 and "files " in fails(rows, "lint"), rows)

    # ── the canary layer (continuation review): the real harness certifies, a stale receipt FAILs ──
    cased = dict(HOOK_RULE, canary={
        "proofs": [{"call": {"tool": "Bash", "input": {"command": "touch {run}/p && run BAD"}}, "marker": {"absent": "{run}/p"},
                    "expect_reason": "Gate X"}],
        "controls": [{"call": {"tool": "Bash", "input": {"command": "touch {run}/c && run GOOD"}}, "marker": {"present": "{run}/c"}}]})
    code, rows = run([{k: v for k, v in HOOK_RULE.items() if k != "canary"}])
    expect("c1: a registered row without a canary declaration FAILs", code == 1
           and "declares `canary:`" in fails(rows, "no-bad"), rows)
    code, rows = run([cased])
    expect("c1: a canaried row without a receipt FAILs", code == 1 and "no canary receipt" in fails(rows, "no-bad"), rows)
    code, rows = run([cased], receipt="fresh", args=["--ci"])
    expect("a fresh, passing receipt certifies the row", code == 0 and status(rows, "no-bad") == "PASS", rows)
    code, rows = run([cased], receipt="failed", args=["--ci"])
    expect("c1: a receipt where the canary failed on the real harness FAILs", code == 1
           and "did not pass every case" in fails(rows, "no-bad"), rows)
    code, rows = run([cased], receipt="stale-row", args=["--ci"])
    expect("c1: a receipt for an older version of the row is stale and FAILs", code == 1
           and "the row changed" in fails(rows, "no-bad"), rows)
    code, rows = run([cased], receipt="stale-enforcer", args=["--ci"])
    expect("c1: an enforcer (or a file it depends on) edited after the canary ran is stale and FAILs", code == 1
           and "a file it depends on changed" in fails(rows, "no-bad"), rows)
    for mode, label in (("fabricated", "a receipt with no case results"),
                        ("v1", "a receipt without harness transcript evidence")):
        code, rows = run([cased], receipt=mode, args=["--ci"])
        expect(f"c2: {label} does not certify", code == 1 and "canary receipt stale" in fails(rows, "no-bad"), rows)
    code, rows = run([cased], receipt="foreign-commit", args=["--ci"])
    expect("c2: a receipt whose commit was squashed away (not in this history) still certifies identical content",
           code == 0 and status(rows, "no-bad") == "PASS", rows)
    code, rows = run([cased], receipt="old-judge", args=["--ci"])
    expect("c2: a receipt judged by other canary code is stale and FAILs",
           code == 1 and "judging code" in fails(rows, "no-bad"), rows)
    code, rows = run([cased], receipt="foreign-commit", path=str(Path(sys.executable).parent) + ":/usr/bin:/bin")
    expect("c2: off CI, a machine with no claude on PATH cannot compare the harness and FAILs (round 9)",
           code == 1 and "no claude on PATH" in fails(rows, "no-bad"), rows)
    with tempfile.TemporaryDirectory() as quiet:
        (Path(quiet) / "claude").write_text("#!/bin/sh\nexit 1\n")
        (Path(quiet) / "claude").chmod(0o755)
        code, rows = run([cased], receipt="foreign-commit", path=f"{quiet}:{Path(sys.executable).parent}:/usr/bin:/bin")
    expect("c2: off CI, a claude that reports no version cannot be compared and FAILs (round 12)",
           code == 1 and "reported no version" in fails(rows, "no-bad"), rows)
    code, rows = run([cased], receipt="team-plan", args=["--ci"])
    expect("c2: a receipt whose sessions ran on a login that is not a personal subscription does not certify",
           code == 1 and "personal subscription login" in fails(rows, "no-bad"), rows)
    code, rows = run([cased], args=["--replay-only"])
    expect("--replay-only judges the replay layer alone and says so", code == 0
           and any("--replay-only" in n for n in rows[0]["notes"]), rows)
    code, rows = run([HOOK_RULE], only=False, base={"rules": [cased]}, args=["--replay-only"])
    expect("c1: replacing a canary with `none` FAILs the ratchet", code == 1
           and "canary removed" in fails(rows, "registry-ratchet"), rows)

    gap = {"id": "no-bad", "rule": "x", "level": "gap", "ticket": "BRO-1", "target": {"level": "hook", "mechanism": "a hook"}}
    code, rows = run([HOOK_RULE], only=False, base={"rules": [gap]}, args=["--replay-only"])
    expect("promoting a gap row to an enforced row (gaining an enforcer) passes the ratchet",
           status(rows, "registry-ratchet") == "PASS", rows)

    where = GATE.replace('"Gate X: BAD is refused; use GOOD"', '"Gate X cwd=" + os.getcwd()')
    in_scratch = dict(HOOK_RULE, proofs=[dict(HOOK_RULE["proofs"][0], expect_reason="cwd=.*rules-check-",
                                              event={"tool_name": "Bash", "cwd": "{scratch}", "tool_input": {"command": "run BAD"}})])
    code, rows = run([in_scratch], gate=where)
    expect("a2: the replayed hook runs in the event's recorded cwd (the claim says so)", code == 0, rows)

    print("all rules_check tests passed")


if __name__ == "__main__":
    main()
