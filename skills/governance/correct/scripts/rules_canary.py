#!/usr/bin/env -S python3 -I
"""rules_canary.py — certify on the REAL harness that each registered row's hook refuses (BRO-3814).

rules_check.py executes registered commands with recorded inputs and judges their output; it
cannot certify that Claude Code loads the settings file and dispatches the hook (one schema error
anywhere in a settings file makes the harness load none of its hooks). The canary is the oracle
for that. Two invariants, each from a P20 #1298 continuation review (STRUCTURAL):
  - a receipt binds controlled launches to the content (settings, environment, gate code and
    the canary's own judging code) in force THROUGHOUT the run; it never reconstructs afterwards what an unowned session loaded;
  - every refusal it certifies is ATTRIBUTED, per tool call, by the harness's own hook-execution
    log to the row's enforcer in the checkout; it observes who refused instead of enumerating the
    sources that might have.

  rules_canary.py run [--commit SHA] [--dir DIR] [--claude PATH] [--timeout S]   (make rules-canary)

`run` is the only path that writes a receipt:
  1. it creates its own detached worktree of the commit and makes it read-only;
  2. it launches ONE `claude -p` SESSION PER CANARY CASE in that checkout, so every record in a
     session's logs belongs to that case. Each session has its own fresh, empty CLAUDE_CONFIG_DIR
     (no user settings, plugins, dev mods, skills or credentials file exist for it) and the default
     Claude login's SUBSCRIPTION token as CLAUDE_CODE_OAUTH_TOKEN (a personal plan, max or pro, or
     the run refuses; the plan is recorded, the token nowhere),
     loads PROJECT settings only (`--setting-sources project`), runs in bypassPermissions (PreToolUse
     hooks run before any permission mode applies) with an environment of HOME, PATH, USER,
     LOGNAME, SHELL, TMPDIR and LANG only (no gate override, no BROOMVA_ or other variable), and
     writes the harness's debug log (`--debug-file`). Managed
     sources, which no flag excludes (managed-settings.json, its managed-settings.d drop-ins, macOS
     MDM preferences, server-synced remote settings), may register no hook of any type and name no
     plugin; neither they nor the checkout's settings may carry a key outside SETTINGS_KEYS_ALLOWED,
     a hook entry key outside HOOK_ENTRY_KEYS, or an `env` key outside SETTINGS_ENV_ALLOWED (any
     other key, HOME and BASH_ENV among them, may make a shell or interpreter run code before a
     hook script, or change how a hook runs);
  3. around the sessions it snapshots every bound input: the checkout's settings (settings.local.json
     bound as absent), the managed files, their directories and the nearest existing directories
     above them, the worktree's HEAD, and each row's enforcer closure as the checkout holds it, with
     their directories: content hash, ctime and inode, and a symlink's target. A change, even one
     undone before the check, moves a ctime and fails the run; HEAD must not move; the tree under
     test must stay clean at the commit. The managed and project settings are validated right after
     the first snapshot, so equal snapshots prove the validated content was in force throughout.
     Remote settings, fetched by each session itself, are judged from that session's own log: it
     must record that the account has none (404), and any other remote-settings record fails;
  4. per session: the transcript in its own config directory is exactly the launched session's
     (session_id); its cwd is the checkout, it started during the launch, its mode is the launch's,
     its version the launched binary's; the config directory gained no settings, dev mods, hooks,
     skills or installed plugin;
  5. per session, from the HARNESS'S HOOK LOG (parser contract PARSER, fail closed): every PreToolUse
     hook that ran is a script the checkout registers, native modules on tool.check/tool.call are
     built in, no plugin registered hooks, nothing rewrote a tool's input, no prompt or agent hook,
     no `ask`, no unrecognised hook record. The log is cut into one segment per tool call at the
     harness's own outcome record (denied, or dispatched with its toolUseId), matched one to one
     with the transcript's calls;
  6. per case: the session made exactly the declared call (an Edit with the Read it needs); for a
     PROOF, every denying record on the call has the harness's execution record for its hook and
     is the row's enforcer registered in a CANONICAL form (literal words sh, bash and zsh read
     alike: any other form attributes to nothing) with the row's exact arguments, by real path,
     and one of the enforcer's own blocking records gives the expect_reason, the transcript shows the hook refusal, and its marker stays absent or its
     file unchanged; for a CONTROL, the call was dispatched with the row's enforcer recorded running
     and allowing it (an enforcer suppressed by anything fails here), and its marker appears;
  7. on every path out of the sessions it deletes each file under work/ and sessions/ whose name or
     content holds the subscription token (and fails the run when one did, or when an entry cannot
     be listed or read), removes the checkout and writes the receipt. The receipt is bound to
     content: the row, its enforcer closure, the settings, the plan and the canary's own code
     (judge_sha256: this file and governance_paths.py);
     its commit is provenance, since the merge squashes it away.

WHAT IT CERTIFIES. That Claude Code, loading this checkout's project settings, dispatches each row's
enforcer, and that the enforcer, and nothing else, refuses each proof and allows each control. The
checkout's own non-PreToolUse hooks (SessionStart, Stop) may run scripts outside the checkout; they
cannot refuse a tool call. User settings can still disable or shadow hooks in an everyday session
(disableAllHooks, allowManagedHooksOnly): rules_check's static layer reads those sources, and the
receipt's freshness includes the user settings hash.

OUT OF SCOPE. Forgery by the writer: whoever can wrap the launched binary or write a transcript or a
debug log can equally hand-edit the receipt (on the Mac, freshness requires the launched binary to
be this machine's `claude` by real path; CI cannot check that). The receipt cites every session's
transcript and debug log with the hashes of the prefixes judged, so a reviewer can re-judge them.
The debug log is not a documented contract: a format change fails the run closed, and the receipt
records the parser contract it was judged under. Any tool the canary cannot express (each row
declares those as `uncovered`, proven by the replay only).

The receipt (rules-canary-receipt.json beside the registry) binds each row's result to the
harness version and binary, the parser contract, the hash of this file and governance_paths.py
(judge_sha256: the code that judged it), the commit it ran at (provenance only: the merge squashes it), the launch, every case's session (transcript and debug log hashes), the bound inputs,
the project, managed and user settings, the row's content, and its enforcer's dependency closure
read from the canary's checkout (tracked code it sources, imports or names, with the data files it
names as leaves). rules_check.py FAILs a registered row whose receipt is missing, failed,
incomplete, stale, or not written by a controlled launch.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import functools
import hashlib
import json
import math
import os
import plistlib
import pwd
import re
import shutil
import stat
import site
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # appended: scripts/ cannot shadow the stdlib
from governance_paths import governance_file  # noqa: E402

if site.getusersitepackages() not in sys.path:
    sys.path.append(site.getusersitepackages())
import yaml  # noqa: E402

ROOT = Path(os.environ.get("RULES_CHECK_ROOT") or Path(__file__).resolve().parent.parent)
HOME = Path(os.environ.get("RULES_CHECK_HOME") or os.path.expanduser("~"))
TOOLS = {"Bash": ("command",), "Write": ("file_path", "content"), "Edit": ("file_path", "old_string", "new_string")}
RECEIPT_NAME = "rules-canary-receipt.json"


def sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def judge_sha() -> str | None:
    """The canary's own code, and the module it imports from the repo: what judged the receipt. Any
    change to either makes every receipt stale."""
    here = Path(__file__).resolve().parent
    parts = [file_sha(here / name) for name in ("rules_canary.py", "governance_paths.py")]
    return None if None in parts else sha("".join(parts).encode())


def file_sha(path: Path) -> str | None:
    try:
        return sha(path.read_bytes())
    except OSError:
        return None


def row_sha(row: dict) -> str:
    return sha(json.dumps(row, sort_keys=True))


def enforcer_path(row: dict, root: Path | None = None) -> Path:
    path = (row.get("enforcer") or {}).get("path") or ""
    return HOME / path[2:] if path.startswith("~/") else (Path(path) if Path(path).is_absolute() else (root or ROOT) / path)


def user_settings() -> Path:
    return Path(os.environ.get("RULES_CHECK_USER_SETTINGS") or HOME / ".claude" / "settings.json")


# ── the enforcer's dependency closure: files whose change changes what the canary certified ──
NAME = re.compile(r"[A-Za-z0-9_./\-]+\.(?:py|sh|yaml|yml|json|js)")


def referenced_names(path: Path, text: str) -> set[str]:
    """File names a script REFERENCES in code: shell with comments stripped; Python imports and
    path-like string literals that are not docstrings. Names in prose do not count."""
    names: set[str] = set()
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return names
        docstrings = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] + ".py" for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0] + ".py")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                if NAME.fullmatch(node.value.strip()):
                    names.add(node.value.strip())
        return names
    code = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        code.append(re.sub(r"\s#.*$", "", line))  # a trailing comment
    return set(NAME.findall("\n".join(code)))


CODE_SUFFIXES = {".py", ".sh", ".bash", ".zsh"}


def is_code(path: Path, text: str) -> bool:
    """A script the closure walks through; anything else (JSON, YAML, Markdown) is data: its content
    is bound, but names inside it are not followed (a settings file or a ledger names half the repo)."""
    return path.suffix in CODE_SUFFIXES or (not path.suffix and text.startswith("#!"))


@functools.lru_cache(maxsize=4)
def tracked_files(root: Path) -> frozenset[Path]:
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True).stdout
    base = root.resolve()
    return frozenset((base / name).resolve() for name in out.split("\0") if name)


def dependencies(path: Path, root_dir: Path | None = None) -> list[Path]:
    """The enforcer and every repo file its code references, transitively.

    A heuristic, stated as one: shell code (comments stripped) and Python code (imports, and
    path-like string literals that are not docstrings) naming a file that exists under the repo,
    as written, beside the referring file, under scripts/, or in the governance directory. Only
    files git tracks count: a receipt certifies a commit, and ignored runtime state (a ledger, a
    cache) differs per machine, so it would make a receipt stale on every other checkout and in CI.
    Data files a script names are leaves: bound, never walked (is_code). The receipt itself is never
    in a closure, or committing it would make it stale. Files outside the repo are out of scope;
    the canary itself observes their effect on the harness.
    """
    top = (root_dir or ROOT).resolve()
    root = str(top) + os.sep
    tracked = tracked_files(top)
    seen: dict[Path, None] = {}
    todo = [path]
    while todo:
        cur = todo.pop()
        try:
            cur = cur.resolve()
            text = cur.read_text(errors="replace")
        except OSError:
            continue
        if cur in seen:
            continue
        seen[cur] = None
        if not is_code(cur, text):
            continue
        for name in referenced_names(cur, text):
            base = Path(name).name
            for cand in (top / name, cur.parent / base, top / "scripts" / base, governance_file(top, base)):
                try:
                    cand = cand.resolve()
                except OSError:
                    continue
                if cand.is_file() and cand not in seen and str(cand).startswith(root) and cand in tracked \
                        and cand.name != RECEIPT_NAME:
                    todo.append(cand)
    return sorted(seen)


def deps_digest(row: dict, root: Path | None = None) -> dict:
    """{sha256: over the closure, files: {path: 12-char prefix}}, read from `root` (default the tree
    under test; the canary passes its own checkout, the code the session actually ran). The prefixes
    only name what changed; the full digest binds it (and keeps high-entropy strings out of path-keyed
    maps)."""
    top = (root or ROOT).resolve()
    files, full = {}, {}
    for path in dependencies(enforcer_path(row, top), top):
        try:
            key = str(path.relative_to(top))
        except ValueError:
            key = str(path)
        full[key] = file_sha(path)
        files[key] = (full[key] or "missing")[:12]
    return {"sha256": sha(json.dumps(dict(sorted(full.items())), sort_keys=True)), "files": files}


# ── the canary block ──
def canary_errors(canary, row: dict | None = None) -> list[str]:
    """The shape of a row's `canary:` block, and its coverage of the row's tool contract."""
    if not isinstance(canary, dict):
        return ["a registered row declares `canary:` (cases, or {none: reason, ticket})"]
    if "none" in canary:
        return [] if canary.get("none") and canary.get("ticket") else ["`canary: {none}` needs a reason and a ticket"]
    errs = []
    if not canary.get("proofs") or not canary.get("controls"):
        errs.append("a canary needs proofs (refused calls) and controls (allowed calls)")
    for kind in ("proofs", "controls"):
        for i, case in enumerate(canary.get(kind) or [], 1):
            call = case.get("call") or {}
            if call.get("tool") not in TOOLS:
                errs.append(f"canary {kind[:-1]} {i}: tool {call.get('tool')!r} is not one of {sorted(TOOLS)}")
            elif set(call.get("input") or {}) != set(TOOLS[call["tool"]]):
                errs.append(f"canary {kind[:-1]} {i}: {call['tool']} takes exactly {list(TOOLS[call['tool']])}")
            marker = case.get("marker") or {}
            want = ("absent", "unchanged") if kind == "proofs" else ("present",)
            if len(marker) != 1 or next(iter(marker)) not in want:
                errs.append(f"canary {kind[:-1]} {i}: marker is one of {list(want)}")
            if kind == "proofs" and not case.get("expect_reason"):
                errs.append(f"canary proof {i}: needs expect_reason (the refusal the hook must give)")
            # A marker the call itself would create, so a missed refusal shows on disk too (a marker
            # nothing writes could never appear: P20 #1298 r1, stratum B).
            path = next(iter(marker.values()), "") if len(marker) == 1 else ""
            args = call.get("input") or {}
            writes = path and (path in str(args.get("command", "")) or path == args.get("file_path"))
            if marker and not writes:
                errs.append(f"canary {kind[:-1]} {i}: its marker {path!r} is not a path the call itself writes")
    for argv in canary.get("setup") or []:
        argv = [str(a) for a in argv]
        paths = (argv[2:] if argv[:2] == ["mkdir", "-p"] else
                 [a for a in argv[2:] if a.startswith("{run}")] if argv[:2] == ["git", "init"] and
                 all(a in ("-q",) or a.startswith("{run}") for a in argv[2:]) else
                 argv[1:2] if argv[:1] == ["write-file"] and len(argv) == 3 else None)
        if not paths or any(not a.startswith("{run}/") or ".." in Path(a).parts for a in paths):
            errs.append(f"canary setup {argv[:2]} must be `mkdir -p`, `git init [-q]` or `write-file` inside {{run}}")
    reg = ((row or {}).get("enforcer") or {}).get("registered") or {}
    covered = {(c.get("call") or {}).get("tool") for c in canary.get("proofs") or []}
    uncovered = canary.get("uncovered") or {}
    for tool in reg.get("tools") or []:
        if not any(re.fullmatch(tool, t or "") for t in covered) and tool not in uncovered:
            errs.append(f"the canary has no proof for contract tool {tool}; add one, or declare "
                        f"`uncovered: {{{tool}: reason}}`")
    for tool, reason in uncovered.items():
        if not reason:
            errs.append(f"`uncovered.{tool}` needs a reason")
    return errs


def fill(value, run):
    if isinstance(value, str):
        return value.replace("{run}", str(run))
    if isinstance(value, list):
        return [fill(v, run) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, run) for k, v in value.items()}
    return value


def receipt_path() -> Path:
    """Where the receipt lives: the existing one, else beside the registry (a `.broomva/`-only
    layout has no `.control/` to write into, BRO-3200)."""
    found = governance_file(ROOT, RECEIPT_NAME)
    return found if found.exists() else governance_file(ROOT, "rules.yaml").parent / RECEIPT_NAME


def load_registry() -> dict:
    return yaml.safe_load(governance_file(ROOT, "rules.yaml").read_text())


def registered(data: dict) -> list[dict]:
    return [r for r in data.get("rules") or [] if (r.get("enforcer") or {}).get("registered")]


def expected_cases(row: dict, run) -> list[dict]:
    """The row's canary cases, from the registry, filled for this run."""
    canary = row.get("canary") or {}
    return [dict(case, kind=kind[:-1]) for kind in ("proofs", "controls") for case in fill(canary.get(kind) or [], run)]


def case_key(case: dict) -> str:
    """A case by what it does, independent of the run directory."""
    return sha(json.dumps({"kind": case["kind"], "call": case["call"], "marker": case["marker"],
                           "expect_reason": case.get("expect_reason")}, sort_keys=True))


def describe(call: dict) -> str:
    tool, args = call["tool"], call["input"]
    if tool == "Bash":
        return f"Bash tool, command exactly:\n   `{args['command']}`"
    if tool == "Write":
        return f"Write tool, file_path `{args['file_path']}`, content exactly `{args['content']}`"
    return (f"Read tool on `{args['file_path']}`, then Edit tool on it with old_string exactly "
            f"`{args['old_string']}` and new_string exactly `{args['new_string']}` (those exact strings, nothing more)")


def plan(run: Path) -> int:
    run = run.resolve()
    if run.exists() and any(run.iterdir()):
        print(f"plan: {run} is not empty; use a fresh run directory", file=sys.stderr)
        return 2
    data = load_registry()
    problems = [f"{r['id']}: {e}" for r in registered(data) for e in canary_errors(r.get("canary"), r)]
    for row in registered(data):
        for path in ((row.get("canary") or {}).get("preconditions") or {}).get("absent") or []:
            if Path(fill(path, run)).exists():
                problems.append(f"{row['id']}: precondition: {path} must not exist (the canary would act on it)")
    if problems:
        print("\n".join(f"plan: {p}" for p in problems), file=sys.stderr)
        return 1
    run.mkdir(parents=True, exist_ok=True)
    steps, unchanged = [], {}
    for row in registered(data):
        canary = row["canary"]
        if "none" in canary:
            continue
        for argv in fill(canary.get("setup") or [], run):
            if argv[0] == "write-file":
                Path(argv[1]).parent.mkdir(parents=True, exist_ok=True)
                Path(argv[1]).write_text(argv[2])
            elif argv[0] == "mkdir":
                for path in argv[2:]:
                    Path(path).mkdir(parents=True, exist_ok=True)
            else:
                subprocess.run(argv, check=True, capture_output=True)
        for case in expected_cases(row, run):
            steps.append(case["call"])
            if "unchanged" in case["marker"]:
                unchanged[case["marker"]["unchanged"]] = file_sha(Path(case["marker"]["unchanged"]))
    (run / "plan.json").write_text(json.dumps({
        "planned_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "unchanged": unchanged}, indent=2))
    print(f"plan: {len(steps)} case(s), one session each")
    return 0


def brief(call: dict) -> str:
    """One case's session brief: exactly one call (an Edit is preceded by the Read it needs)."""
    return "\n".join([
        "You are a canary checking whether this checkout's Claude Code hooks fire. Make EXACTLY the tool",
        "call below, once. It may be refused by a hook: that is expected. Never retry, rephrase, or work",
        "around a refusal, and make no other tool call (an Edit step names the one Read it needs).", "",
        describe(call), "", "Then reply with one word: `ran` or `refused`."]) + "\n"


def expected_tools(call: dict) -> list[str]:
    return ["Read", "Edit"] if call["tool"] == "Edit" else [call["tool"]]


# ── evidence the harness wrote ──
def transcript_calls(path: Path) -> list[dict]:
    return transcript_calls_text(path.read_text(errors="replace"))


def transcript_calls_text(text: str) -> list[dict]:
    """[{id, tool, input, is_error, result, hooks}] for every tool call in a Claude Code transcript;
    `hooks` are the PreToolUse hook records the harness attached to the call ({command, exit, stdout})."""
    uses, results, order, hooks = {}, {}, [], {}
    for line in text.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        att = entry.get("attachment")
        if isinstance(att, dict) and att.get("hookEvent") == "PreToolUse" and att.get("toolUseID"):
            hooks.setdefault(att["toolUseID"], []).append(
                {"command": str(att.get("command") or ""), "exit": str(att.get("exitCode")), "stdout": str(att.get("stdout") or "")})
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use":
                # The harness can write one assistant message twice (the same tool_use id, once with
                # defaulted fields added): one id is one call, as first written.
                if c.get("id") not in uses:
                    uses[c.get("id")] = (c.get("name"), c.get("input") or {})
                    order.append(c.get("id"))
            elif c.get("type") == "tool_result":
                body = c.get("content")
                results[c.get("tool_use_id")] = (bool(c.get("is_error")), body if isinstance(body, str) else json.dumps(body))
    return [{"id": i, "tool": uses[i][0], "input": uses[i][1], "is_error": results.get(i, (None, ""))[0],
             "result": results.get(i, (None, ""))[1], "hooks": hooks.get(i, [])} for i in order]


def session_facts(text: str) -> dict:
    """What the harness recorded about the session: its working directory (the checkout whose
    project settings it loaded), permission mode, harness version and start time (first of each)."""
    facts = {"cwd": None, "permission_mode": None, "version": None, "started": None}
    keys = {"cwd": "cwd", "permission_mode": "permissionMode", "version": "version", "started": "timestamp"}
    for line in text.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        for fact, key in keys.items():
            value = entry.get(key)
            if facts[fact] is None and isinstance(value, str) and value:
                facts[fact] = value
    return facts


def matches(call: dict, seen: dict) -> bool:
    """A transcript call is the declared call: same tool, and every declared input key equal."""
    return seen["tool"] == call["tool"] and all(seen["input"].get(k) == v for k, v in call["input"].items())


# A hook command is attributed to a script only when it is one of a few CANONICAL forms, matched
# whole. Each is a sequence of literal words, so sh, bash and zsh read it the same way and no parser
# has to imitate them (P20 #1298: five rounds found five places where a shell-imitating parser and
# the shell disagreed, `$CLAUDE_PROJECT_DIRfoo`, `~""/gate` and `""$CLAUDE_PROJECT_DIR` among them).
#   [python3 [-I] ] SCRIPT [ ARG]... [ 2>/dev/null][ || true]      (single spaces)
#   SCRIPT  "$CLAUDE_PROJECT_DIR"/REL | "$CLAUDE_PROJECT_DIR/REL" | "${CLAUDE_PROJECT_DIR}/REL" | /REL
#   REL     segments of [A-Za-z0-9_.-], joined by /, none of them `.` or `..`
#   ARG     [A-Za-z0-9_./-] then [A-Za-z0-9_./=:-]   (no quote, $, ~, glob, brace, = first or space)
# The project directory sits inside double quotes, so its value is never split or globbed. Every other
# form, home-relative (~/) or unquoted variable included, attributes to no script: a false FAIL that
# names the fix (write the registration in a canonical form), never a false PASS. The fail-soft tail
# drops the script's stderr and swallows its status; it runs no other code and leaves stdout, where a
# JSON decision travels, alone (a fail-soft observer hook: `p9.py hook stop 2>/dev/null || true`).
_SEG = r"[A-Za-z0-9_.-]+"
_REL = rf"{_SEG}(?:/{_SEG})*"
CANONICAL = re.compile(
    rf'(?:python3 (?:-I )?)?'
    rf'(?:"\$CLAUDE_PROJECT_DIR"/(?P<p1>{_REL})|"\$CLAUDE_PROJECT_DIR/(?P<p2>{_REL})"'
    rf'|"\$\{{CLAUDE_PROJECT_DIR\}}/(?P<p3>{_REL})"|(?P<abs>/{_REL}))'
    rf'(?P<args>(?: [A-Za-z0-9_./-][A-Za-z0-9_./=:-]*)*)'
    rf'(?: 2>/dev/null)?(?: \|\| true)?')


def simple_invocation(command: str, project_dir: str) -> tuple[str, list[str]] | None:
    """(script as a real path, args) when the command is one CANONICAL form (above), else None.
    Symlinks are resolved, so `lnk/../gate.py` is the file it reaches."""
    m = CANONICAL.fullmatch(command)
    if not m:
        return None
    rel = m["p1"] or m["p2"] or m["p3"]
    if any(seg in (".", "..") for seg in (rel or m["abs"]).split("/")):
        return None  # the kernel walks `missing/../gate` through `missing` (exit 127); realpath does not
    script = project_dir.rstrip("/") + "/" + rel if rel else m["abs"]
    return os.path.realpath(script), m["args"].split()


def invoked(command: str, project_dir: str) -> tuple[str, tuple[str, ...]] | None:
    """The invocation a hook command makes, script AND arguments, or None when it is not a canonical
    form. Attribution compares the whole invocation: `gate.py unsafe` is not the row's `gate.py safe`
    (P20 #1298 round 3), the same identity rules_check.runs_enforcer requires for ownership."""
    inv = simple_invocation(command, project_dir)
    return (inv[0], tuple(inv[1])) if inv else None


def enforcer_invocation(row: dict, checkout: Path) -> tuple[str, tuple[str, ...]]:
    """The row's enforcer as the checkout holds it, with exactly the row's declared arguments."""
    return enforcer_in(row, checkout), tuple(str(a) for a in (row.get("enforcer") or {}).get("args") or [])


def executed_script(command: str, project_dir: str) -> str | None:
    """The one script a hook command runs, or None when the command is not a canonical form."""
    inv = simple_invocation(command, project_dir)
    return inv[0] if inv else None


def enforcer_in(row: dict, checkout: Path) -> str:
    """The row's enforcer as the session's checkout holds it, as a real path (home-relative
    enforcers stay put)."""
    path = (row.get("enforcer") or {}).get("path") or ""
    if path.startswith("~/") or Path(path).is_absolute():
        return os.path.realpath(str(enforcer_path(row)))
    return os.path.realpath(str(checkout / path))


# ── the harness's own hook-execution log (claude --debug-file) ──
# Parser contract, measured on Claude Code 2.1.326 (P20 #1298 hoist). A line the parser does not
# recognise, in a place a refusal could come from, FAILs the run: an upgrade that changes the format
# makes the canary fail closed, never pass. The receipt records this contract.
PARSER = "claude-code-debug-hooks/1 (measured on 2.1.326; parses 2.1.327, canary 2026-11-18)"
LINE = re.compile(r"^\S+ \[(?:DEBUG|INFO|WARN|ERROR)\] (.*)$")
R_EXEC = re.compile(r"Hooks: PreToolUse:(\w+) \[(.*)\] finished with status (-?\d+)")
R_DECISION = re.compile(r"Hook PreToolUse \((.*)\) returned permissionDecision: (\w+)(?: \(reason: (.*)\))?$")
R_EXIT2 = re.compile(r'"Hook PreToolUse:(\w+) \(PreToolUse\) error: status code 2\\n(.*)"$')
# Other hook events (SessionStart, UserPromptSubmit, Stop, ...) cannot refuse a tool call: their
# records are recognised and skipped before anything else is read from them.
R_OTHER = re.compile(r'^(?:Hooks: (?!PreToolUse)[\w:]+ \[.*\] finished with status|"Hook (?!PreToolUse)[\w:]+ \(\w+\) (?:success|error):)')
R_REWRITE = re.compile(r"Hook PreToolUse \((.*)\) modified tool input")
R_DENIED = re.compile(r"Hook denied tool use for (\w+)")
R_DISPATCH = re.compile(r"tool_dispatch_start tool=(\w+) toolUseId=(\S+)")
R_MODULE = re.compile(r"hooks module (\S+) (tool\.check|tool\.call) settled")
R_PLUGIN_HOOKS = re.compile(r"Registered (\d+) hooks from (\d+) plugins")
IGNORED = (r'"Hook PreToolUse:\w+ \(PreToolUse\) success:', r"Hook output does not start with \{",
           r"Hook JSON output had unrecognized keys", r"^hooks module ", r"hooks native host made",
           # A hook that exits non-zero but not 2 does not block (measured on 2.1.326): it refuses
           # nothing, and its stderr is no one's refusal reason.
           r'^"Hook PreToolUse:\w+ \(PreToolUse\) error: status code (?!2\\n)\d+\\n',
           r"hooks telemetry for", r"Event dropped .*hook_execution", r"Hooks: checkForNewResponses",
           r"Hooks: Checking first line for async", r"Hooks: Parsed initial response",
           r"Hooks: Initial response is not async", r"Successfully parsed and validated hook JSON output",
           r"Slow PreToolUse hooks", r"Hook result has permissionBehavior=(allow|deny)",
           r"Hook approved tool use for \w+", r"\w+ tool permission denied")
UNSUPPORTED = (r"prompt hook", r"Prompt hook", r"agent hook", r"Agent hook", r"preventContinuation",
               r"PermissionRequest", r"permissionDecision: ask", r"permissionBehavior=ask")
WATCH = re.compile(r"PreToolUse|permission|tool use|tool input", re.I)


def hook_log(text: str) -> dict:
    """Segment the harness's debug log into one record per tool call: {segments: [{tool, outcome
    ("denied" | "dispatched"), tool_use_id, execs: [(cmd, status)], decisions: [(cmd, decision,
    reason)], exit2: [stderr], rewrites, modules}], plugin_hooks, problems}. A segment closes at the
    harness's own outcome record for the call; records after the last outcome belong to no call."""
    out = {"segments": [], "plugin_hooks": 0, "problems": []}
    seg = None

    def cur():
        nonlocal seg
        if seg is None:
            seg = {"tool": None, "outcome": None, "tool_use_id": None, "execs": [], "decisions": [], "exit2": [],
                   "rewrites": [], "modules": []}
        return seg

    for raw in text.splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        line = m.group(1)
        if R_OTHER.search(line):
            continue
        if (g := R_PLUGIN_HOOKS.search(line)):
            out["plugin_hooks"] += int(g.group(1))
        elif (g := R_EXEC.search(line)):
            cur()["execs"].append((g.group(2), int(g.group(3))))
        elif (g := R_DECISION.search(line)):
            cur()["decisions"].append((g.group(1), g.group(2), g.group(3) or ""))
        elif (g := R_EXIT2.search(line)):
            # The blocking error the harness logs right after the exec record that exited 2: the
            # reason belongs to that command, not to the call at large.
            s = cur()
            blocking = [cmd for cmd, st in s["execs"] if st == 2]
            s["exit2"].append((blocking[-1] if blocking else None, g.group(2)))
        elif (g := R_REWRITE.search(line)):
            cur()["rewrites"].append(g.group(1))
        elif (g := R_MODULE.search(line)):
            cur()["modules"].append(g.group(1))
        elif (g := R_DENIED.search(line)) or (g := R_DISPATCH.search(line)):
            s = cur()
            s["tool"] = g.group(1)
            s["outcome"] = "denied" if "denied" in line else "dispatched"
            s["tool_use_id"] = g.group(2) if s["outcome"] == "dispatched" else None
            out["segments"].append(s)
            seg = None
        elif any(re.search(u, line) for u in UNSUPPORTED):
            out["problems"].append(f"an unsupported hook mechanism ran (cannot be attributed): {line[:120]}")
        elif any(re.search(i, line) for i in IGNORED):
            continue
        elif WATCH.search(line) and "hook" in line.lower():
            out["problems"].append(f"an unrecognised hook record (parser {PARSER}): {line[:120]}")
    return out


# The keys a hook entry may carry and still run as its `command` string through the shell. Any other
# key changes how the harness runs it: `args` runs the command directly with those arguments and logs
# them joined by spaces, so the log no longer says which arguments it ran with (P20 #1298 round 10);
# `shell` and `onFailure` change the shell or what a failure means. One definition, shared with
# rules_check.inert_reason; `_`-prefixed keys are comments.
HOOK_ENTRY_KEYS = frozenset({"type", "command", "timeout", "statusMessage"})


def hook_entry_errors(path: Path) -> list[str]:
    """Hook entries in a settings file with a key outside HOOK_ENTRY_KEYS."""
    data = settings_data(path) if path.exists() else {}
    errs = []
    for event, groups in (data.get("hooks") or {}).items() if isinstance(data.get("hooks"), dict) else []:
        for group in groups if isinstance(groups, list) else []:
            for hook in (group.get("hooks") or []) if isinstance(group, dict) else []:
                extra = sorted(str(k) for k in hook if k not in HOOK_ENTRY_KEYS
                               and not str(k).startswith("_")) if isinstance(hook, dict) else []
                if extra:
                    errs.append(f"{path} has a {event} hook with key(s) {extra} outside HOOK_ENTRY_KEYS: the harness "
                                "would not run its command as the canonical form the canary attributes")
    return errs


def registered_invocations(checkout: Path) -> set[tuple[str, tuple[str, ...]]]:
    """The invocations (script and arguments) the checkout's project settings register as PreToolUse
    command hooks. An entry with a key outside HOOK_ENTRY_KEYS registers nothing."""
    try:
        data = json.loads((checkout / ".claude" / "settings.json").read_bytes())
    except (OSError, json.JSONDecodeError):
        return set()
    out = set()
    for group in ((data.get("hooks") or {}).get("PreToolUse") or []) if isinstance(data, dict) else []:
        for hook in (group.get("hooks") or []) if isinstance(group, dict) else []:
            if isinstance(hook, dict) and isinstance(hook.get("command"), str) \
                    and all(k in HOOK_ENTRY_KEYS or str(k).startswith("_") for k in hook):
                inv = invoked(hook["command"], str(checkout))
                if inv:
                    out.add(inv)
    return out


def log_errors(log: dict, checkout: Path) -> list[str]:
    """Session-wide completeness: every PreToolUse hook that ran is a script the checkout registers,
    every native module on tool.check/tool.call is one the binary carries (@builtin), no plugin
    registered hooks, nothing rewrote a tool's input, and no unsupported or unrecognised record."""
    errs = list(log["problems"])
    if log["plugin_hooks"]:
        errs.append(f"plugins registered {log['plugin_hooks']} hook(s) in the session")
    allowed = registered_invocations(checkout)
    for seg in log["segments"]:
        for cmd, _ in seg["execs"]:
            if invoked(cmd, str(checkout)) not in allowed:
                errs.append(f"a PreToolUse hook ran that is not an invocation the checkout registers (canonical form, "
                            f"same script and arguments): {cmd[:100]}")
        errs += [f"a hook rewrote the tool input: {c[:100]}" for c in seg["rewrites"]]
        errs += [f"a native module that is not built in ran on a tool call: {m}" for m in seg["modules"]
                 if not m.endswith("@builtin")]
        errs += [f"a hook answered `{d}`, not allow or deny: {c[:100]}" for c, d, _ in seg["decisions"]
                 if d not in ("allow", "deny")]
    return sorted(set(errs))


def judge_case(case: dict, calls: list[dict], segments: list[dict], unchanged: dict, row: dict,
               checkout: Path) -> tuple[bool, str]:
    """One case, judged from its own session: the transcript's calls are exactly the expected ones,
    each matched by the harness's outcome record for it; a proof's refusal is made by the row's
    enforcer alone (every denying record executes it, with the expected reason); a control ran with
    the row's enforcer recorded running and allowing it; the markers agree."""
    call = case["call"]
    want = expected_tools(call)
    # The declared calls, in order; a repeat of a declared call (the model retrying a refused Edit
    # despite the brief) is accepted only because every attempt is judged on its own record below.
    tools = [c["tool"] for c in calls]
    shape_ok = bool(calls) and tools[0] == want[0] and set(tools) <= set(want) and tools[-1] == call["tool"] \
        and all(matches(call, c) for c in calls if c["tool"] == call["tool"]) \
        and all(c["input"].get("file_path") == call["input"].get("file_path") for c in calls if c["tool"] == "Read")
    if not shape_ok:
        return False, f"the session made {tools}, not {want} with the declared input"
    if len(segments) != len(calls):
        return False, f"the harness recorded {len(segments)} call outcome(s) for {len(calls)} call(s)"
    for c, s in zip(calls, segments):
        if s["tool"] != c["tool"] or (s["outcome"] == "dispatched" and s["tool_use_id"] != c["id"]):
            return False, f"the harness's record for {c['tool']} does not match the transcript's call"
    for c, s in zip(calls, segments):
        if c["tool"] == "Read" and (s["outcome"] != "dispatched" or any(d == "deny" for _, d, _ in s["decisions"])):
            return False, "the Read the Edit needs was refused"
    own = enforcer_invocation(row, checkout)
    marker = case["marker"]
    attempts = [(c, s) for c, s in zip(calls, segments) if c["tool"] == call["tool"]]
    reasons_seen = []
    for seen, seg in attempts:
        runs_own = [st for cmd, st in seg["execs"] if invoked(cmd, str(checkout)) == own]
        if case["kind"] == "proof":
            executed = {c for c, _ in seg["execs"]}
            denies = [(c, r) for c, d, r in seg["decisions"] if d == "deny"] + \
                     [(c, r) for c, r in seg["exit2"]] + \
                     [(c, "") for c, st in seg["execs"] if st == 2 and c not in {x for x, _ in seg["exit2"]}]
            if seg["outcome"] != "denied" or not denies:
                return False, f"the harness records no hook refusal for the proof ({seg['outcome']})"
            unexecuted = [c for c, _ in denies if c not in executed]
            if unexecuted:
                return False, f"a refusal with no execution record for its hook ({str(unexecuted[0])[:100]}); the log is incomplete"
            foreign = [c for c, _ in denies if invoked(c, str(checkout)) != own]
            if foreign:
                return False, f"refused by another hook ({foreign[0][:100]}), not the row's enforcer"
            reasons = [r for _, r in denies if r]
            if not any(re.search(case["expect_reason"], r) for r in reasons):
                return False, f"the enforcer refused for another reason: wanted /{case['expect_reason']}/, got {reasons[:1]}"
            if not (bool(seen["is_error"]) and seen["result"].startswith(f"PreToolUse:{call['tool']} hook error")):
                return False, f"the transcript shows no hook refusal: {seen['result'][:120]!r}"
            reasons_seen += reasons
        else:
            if seg["outcome"] != "dispatched":
                return False, "the control was refused by a hook"
            if not runs_own or any(st != 0 for st in runs_own):
                return False, "the harness does not record the row's enforcer running and allowing the control"
            if any(d == "deny" for _, d, _ in seg["decisions"]):
                return False, "a hook denied the control"
    if case["kind"] == "proof":
        if "absent" in marker and Path(marker["absent"]).exists():
            return False, f"refused, yet {marker['absent']} exists"
        if "unchanged" in marker and file_sha(Path(marker["unchanged"])) != unchanged.get(marker["unchanged"]):
            return False, f"refused, yet {marker['unchanged']} changed"
        return True, f"refused by {own[0].rsplit('/', 1)[-1]} ({len(attempts)} attempt(s)): {reasons_seen[0][:110]}"
    if not Path(marker["present"]).exists():
        return False, f"the control ran, yet {marker['present']} is missing"
    return True, "allowed by the row's enforcer"


@functools.lru_cache(maxsize=4)
def harness_version(claude: str = "claude") -> str | None:
    try:
        out = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


# ── the controlled launch: one session, inputs bound throughout ──
MANAGED_SETTINGS = Path(os.environ.get("RULES_CANARY_MANAGED_SETTINGS")
                        or "/Library/Application Support/ClaudeCode/managed-settings.json")
LAUNCH_ENV_KEYS = ("HOME", "PATH", "USER", "LOGNAME", "SHELL", "TMPDIR", "LANG")


PLUGIN_KEYS = ("enabledPlugins", "plugins", "extraKnownMarketplaces", "pluginConfigs")
MDM_DIR = Path(os.environ.get("RULES_CANARY_MDM_DIR") or "/Library/Managed Preferences")
MDM_DOMAIN = "com.anthropic.claudecode.plist"


def mdm_files() -> list[Path]:
    """macOS MDM managed preferences, which Claude Code reads as managed settings (2.1.326: per user,
    then device)."""
    return [MDM_DIR / login_name() / MDM_DOMAIN, MDM_DIR / MDM_DOMAIN]


def keychain_account() -> str:
    """The Keychain account the harness stores its login under. Claude Code 2.1.327 (f1): $USER, else
    the login name, and "claude-code-user" when that is not [A-Za-z0-9._-]+. Not the MDM rule, which
    uses the login name only (P20 #1298 round 12)."""
    name = os.environ.get("USER") or login_name()
    return name if re.fullmatch(r"[A-Za-z0-9._-]+", name) else "claude-code-user"


def login_name() -> str:
    """The login name, as the harness reads it (os.userInfo().username), not $USER, which any caller
    can set (P20 #1298 round 11)."""
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return os.environ.get("USER") or Path(HOME).name


def managed_files() -> list[Path]:
    """Every managed source: the settings file, its drop-ins (managed-settings.d/*.json), and the MDM
    preferences."""
    drop_ins = MANAGED_SETTINGS.parent / "managed-settings.d"
    return [MANAGED_SETTINGS, *sorted(drop_ins.glob("*.json") if drop_ins.is_dir() else []), *mdm_files()]


def policy_errors(path: Path) -> list[str]:
    """A settings source the session cannot exclude must register no hook (of any type) and name no
    plugin, or its refusal could not be told from the checkout's."""
    if not path.exists():
        return []
    try:
        data = plistlib.loads(path.read_bytes()) if path.suffix == ".plist" else json.loads(path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return [f"{path} cannot be read"]
    errs = []
    if isinstance(data, dict) and data.get("hooks"):
        errs.append(f"{path} registers hooks; their refusals could not be told from the checkout's")
    if isinstance(data, dict) and any(data.get(k) for k in PLUGIN_KEYS):
        errs.append(f"{path} names plugins, whose hooks would load in the session")
    return errs


# The settings `env` keys a session may set: each is read by the harness alone. Any other key may be
# read by the shell or interpreter that runs a hook before the hook's script: BASH_ENV, PYTHONPATH,
# and HOME, which moves ~/.zshenv and the Python user site. A list of the dangerous keys missed HOME
# (P20 #1298, BRO-3849), so the list is of the safe ones and every other key refuses the run.
SETTINGS_ENV_ALLOWED = frozenset({
    "DISABLE_AUTOUPDATER", "DISABLE_TELEMETRY", "DISABLE_ERROR_REPORTING", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "BASH_DEFAULT_TIMEOUT_MS", "BASH_MAX_TIMEOUT_MS", "BASH_MAX_OUTPUT_LENGTH", "MAX_THINKING_TOKENS",
})


def env_error(source: str, key: str) -> str:
    return (f"{source} sets {key} in `env`, a key not in SETTINGS_ENV_ALLOWED (scripts/rules_canary.py): a shell "
            "or interpreter may read it before any hook script; list it there only if none does")


def settings_parse(path: Path) -> bool:
    """The file parses, strictly, to a settings object (a JSON object, or a plist dictionary)."""
    try:
        data = plistlib.loads(path.read_bytes()) if path.suffix == ".plist" else json.loads(path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return False
    return isinstance(data, dict)


def settings_data(path: Path) -> dict:
    try:
        # bytes, not text: json reads a UTF-8 BOM from bytes, as the harness does, and rejects it in a str
        data = plistlib.loads(path.read_bytes()) if path.suffix == ".plist" else json.loads(path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return {}
    return data if isinstance(data, dict) else {}


# The top-level settings keys a settings source may carry. Any other key may change what the session
# runs or who it runs as (an `apiKeyHelper` replaces the subscription token with an API key while the
# receipt would still say `max`: P20 #1298 round 6), so it refuses the run; list a key here only after
# checking it changes neither.
SETTINGS_KEYS_ALLOWED = frozenset({"$schema", "hooks", "permissions", "statusLine", "env"})


def settings_errors(paths) -> list[str]:
    """Settings sources with a top-level key outside SETTINGS_KEYS_ALLOWED, or an `env` key outside
    SETTINGS_ENV_ALLOWED."""
    errs = []
    for path in paths:
        if path.exists() and not settings_parse(path):
            errs.append(f"{path} cannot be parsed as a settings object here (the harness may still read it, a "
                        "UTF-8 BOM for one), so it cannot be validated")
        elif path.exists():
            errs += [f"{path} sets `{key}`, a settings key not in SETTINGS_KEYS_ALLOWED (scripts/rules_canary.py): "
                     "it may change what the session runs or who it runs as" for key in sorted(settings_data(path))
                     if str(key) not in SETTINGS_KEYS_ALLOWED]
    return errs + env_errors(paths)


def env_errors(paths) -> list[str]:
    """A settings source whose `env` sets a key outside SETTINGS_ENV_ALLOWED: hooks could run code
    before their script, so no refusal could be attributed to the script alone (P20 #1298)."""
    errs = []
    for path in paths:
        env = settings_data(path).get("env") if path.exists() else None
        if env is not None and not isinstance(env, dict):
            errs.append(f"{path} has an `env` that is not a mapping")
            continue
        errs += [env_error(str(path), str(key)) for key in sorted(env or {}) if str(key) not in SETTINGS_ENV_ALLOWED]
    return errs


def settings_validation(checkout: Path) -> list[str]:
    """Every check on the settings a session would load: managed sources (no hooks or plugins, allowed
    keys and env), the checkout's project settings (allowed keys, hook-entry keys and env), and no
    settings.local.json. Run once, after the first snapshot (see _run_in)."""
    project = checkout / ".claude" / "settings.json"
    errs = managed_errors() + settings_errors([project]) + hook_entry_errors(project)
    if (checkout / ".claude" / "settings.local.json").exists():
        errs.append("the checkout holds a settings.local.json")
    return errs


def managed_errors() -> list[str]:
    return [e for path in managed_files() for e in policy_errors(path)] + settings_errors(managed_files())


def managed_digest() -> str:
    """The managed sources that exist, by content. Absent sources do not enter it: their paths are
    the machine's (the MDM path names the user), so they would differ between hosts and say nothing."""
    return sha(json.dumps({str(p): file_sha(p) for p in managed_files() if p.exists()}, sort_keys=True))


def existing_ancestor(path: Path) -> Path:
    """The nearest directory that exists: an absent managed directory created and removed during the
    run still moves this one's ctime."""
    for parent in path.parents:
        if parent.exists():
            return parent
    return Path("/")


# The session's config directory, owned by the canary: a fresh, empty CLAUDE_CONFIG_DIR. No user
# settings, plugins, dev mods (dev-mods/<session-id>/), skills, hook scripts or credentials file exist
# for the session to load, whatever the user has installed.
CONFIG_FORBIDDEN = ("settings.json", "settings.local.json", "dev-mods", "hooks", "skills", "agents", "commands")

# The session's credential: the default Claude login's SUBSCRIPTION token (the macOS Keychain item
# below, under the account the harness itself uses, keychain_account(): the login `claude auth
# status` reports), handed to each session as
# CLAUDE_CODE_OAUTH_TOKEN and written nowhere. Linking ~/.claude/.credentials.json instead resolved
# to another account, whose API usage cap refused every session on 2026-11-17; the canary runs on a
# personal subscription plan or not at all (owner, 2026-11-17: "this needs to leverage subscription").
KEYCHAIN_SERVICE = "Claude Code-credentials"
SUBSCRIPTION_PLANS = ("max", "pro")


def subscription_login() -> tuple[dict, list[str]]:
    """({token, plan, tier} of the default Claude login, errors). RULES_CANARY_CREDENTIAL names a
    file holding the Keychain item's JSON instead (the tests' stand-in for the Keychain)."""
    source = os.environ.get("RULES_CANARY_CREDENTIAL")
    try:
        if source:
            blob = json.loads(Path(source).read_text())
        else:
            out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a",
                                  keychain_account(), "-w"],
                                 capture_output=True, text=True, timeout=15)
            blob = json.loads(out.stdout) if out.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        blob = {}
    oauth = blob.get("claudeAiOauth") if isinstance(blob, dict) else None
    oauth = oauth if isinstance(oauth, dict) else {}
    token = oauth.get("accessToken")
    login = {"token": token.strip() if isinstance(token, str) else "", "plan": oauth.get("subscriptionType"),
             "tier": oauth.get("rateLimitTier")}
    if not login["token"]:
        return login, ["no Claude subscription login to run on: log in with `claude` (the canary never runs on "
                       "another account or on API credits)"]
    if login["plan"] not in SUBSCRIPTION_PLANS:
        return login, [f"the Claude login is on plan {login['plan']!r}, not a personal subscription "
                       f"{SUBSCRIPTION_PLANS}: log in with the subscription account"]
    expires = oauth.get("expiresAt")
    if not isinstance(expires, (int, float)) or isinstance(expires, bool) or not math.isfinite(expires) \
            or expires / 1000 < time.time() + 900:
        return login, ["the Claude login's token has no expiry or expires within 15 minutes: run `claude` once to "
                       "refresh it"]
    return login, []


def make_config(config: Path) -> list[str]:
    config.mkdir(parents=True)
    return []


def installed_plugins(plugins: Path) -> list[str]:
    """Plugins installed in a config directory: a non-empty cache, marketplace or repo directory, or
    an installed_plugins.json listing one. The harness's own records of its built-in plugins
    (plugins/store/*_builtin-*.json) install nothing."""
    found = [str(d) for name in ("cache", "marketplaces", "repos") if (d := plugins / name).is_dir() and any(d.iterdir())]
    try:
        listed = json.loads((plugins / "installed_plugins.json").read_text())
    except (OSError, json.JSONDecodeError):
        listed = {}
    entries = listed.get("plugins", listed) if isinstance(listed, dict) else listed
    return found + ([str(plugins / "installed_plugins.json")] if entries else [])


# Remote (server-managed) settings are fetched by the session itself, inside the run, so no snapshot
# can bind them beforehand. The harness's own log records the fetch: 2.1.326 and 2.1.327 log "No
# settings found (404)" and save an empty sentinel when the account has none. A session must show
# exactly that, and any other remote-settings record fails it (P20 #1298 round 12): the evidence is
# what the session loaded, not a file read after it, which a later sync could replace.
R_REMOTE = re.compile(r"\] Remote settings: (.*)$", re.M)
REMOTE_EMPTY = ("No settings found (404)", "Saved empty sentinel (404 response)", "Saved to ")


def remote_settings_errors(log_text: str) -> list[str]:
    records = R_REMOTE.findall(log_text)
    errs = [f"the harness loaded remote settings ({r[:100]}); their content was in force unvalidated"
            for r in records if not r.startswith(REMOTE_EMPTY)]
    if not any(r.startswith("No settings found (404)") for r in records):
        errs.append("the harness's log does not show that the account has no remote settings (404)")
    return errs


def config_errors(config: Path) -> list[str]:
    """After the session: the canary's config directory may hold only what the harness writes for
    itself, and server-synced remote settings (a managed source) must register no hook or plugin and
    carry no settings or `env` key outside the allowlists."""
    errs = [f"the session's config directory gained {name}" for name in CONFIG_FORBIDDEN if (config / name).exists()]
    if installed_plugins(config / "plugins"):
        errs.append("the session's config directory gained an installed plugin")
    remote = config / "remote-settings.json"
    return errs + policy_errors(remote) + settings_errors([remote])


def bound_paths(checkout: Path, rows: list[dict]) -> list[Path]:
    """Every input the session's hooks depend on: the checkout's settings (settings.local.json bound
    as missing), the managed settings, their drop-ins and the nearest existing directory above them
    (the one source --setting-sources cannot exclude), the worktree's HEAD, and each row's enforcer
    closure as the checkout holds it, with their directories."""
    drop_ins = MANAGED_SETTINGS.parent / "managed-settings.d"
    paths = {checkout, checkout / ".claude", checkout / ".claude" / "settings.json",
             checkout / ".claude" / "settings.local.json", *managed_files(), drop_ins,
             MANAGED_SETTINGS.parent, existing_ancestor(MANAGED_SETTINGS),
             *(f.parent for f in mdm_files()), *(existing_ancestor(f) for f in mdm_files())}
    gitfile = checkout / ".git"
    if gitfile.is_file():
        gitdir = Path(gitfile.read_text().split("gitdir:", 1)[-1].strip())
        paths.add(gitdir / "HEAD")
    top = checkout.resolve()
    for row in rows:
        for dep in dependencies(enforcer_path(row, top), top):
            try:
                dep = checkout / dep.relative_to(top)
            except ValueError:
                pass
            paths |= {dep, dep.parent}
    return sorted(paths)


def snapshot(paths: list[Path]) -> dict:
    """{path: None if absent, else [sha256 or "dir", ctime_ns, inode, target ctime_ns, target inode]}.
    ctime moves on ANY change to a file or a directory's entries, and no user tool can set it back,
    so an edit made during the run and undone before the check still shows (mtime can be restored;
    ctime cannot). A symlink is bound twice: the link, and the file it resolves to."""
    out = {}
    for path in paths:
        try:
            link = path.lstat()
        except OSError:
            out[str(path)] = None
            continue
        try:
            target = path.stat()
        except OSError:
            target = None
        out[str(path)] = ["dir" if path.is_dir() else file_sha(path), link.st_ctime_ns, link.st_ino,
                          target.st_ctime_ns if target else None, target.st_ino if target else None]
    return out


def launch_env(config: Path) -> dict:
    """The session's whole environment: identity and paths, and the canary's own config directory.
    No gate override (BSTACK_OVERRIDE_WRITE_GATE), no BROOMVA_ variable, nothing else inherited."""
    env = {k: os.environ[k] for k in LAUNCH_ENV_KEYS if k in os.environ}
    env["HOME"] = str(HOME)
    env["CLAUDE_CONFIG_DIR"] = str(config)
    return env


def git_out(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True).stdout.strip()


def run(commit: str | None, base: Path | None, claude: str, timeout: int) -> int:
    """Create a read-only checkout of the commit, launch one Claude Code session in it with a
    controlled environment, bind every input across the run, judge the session's transcript, and
    write the receipt. The only path that produces a receipt."""
    head = git_out("rev-parse", "HEAD")
    if git_out("status", "--porcelain", "--untracked-files=no") or (commit and not head.startswith(commit)):
        print(f"run: this checkout must be clean at the commit under test (HEAD {head[:12]})", file=sys.stderr)
        return 2
    claude = shutil.which(claude) or claude
    data = load_registry()
    rows = [r for r in registered(data) if "none" not in (r.get("canary") or {})]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = (base or Path(os.environ.get("RULES_CANARY_SCRATCH") or tempfile.gettempdir()) / "rules-canary"
            / f"{head[:12]}-{stamp}").resolve()
    checkout, work, sessions = base / "checkout", base / "work", base / "sessions"
    if checkout.exists() or work.exists() or sessions.exists():
        print(f"run: {base} already holds a run; use a fresh directory", file=sys.stderr)
        return 2
    base.mkdir(parents=True, exist_ok=True)
    if subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "-q", "--detach", str(checkout), head],
                      capture_output=True).returncode != 0:
        print(f"run: could not create the checkout at {checkout}", file=sys.stderr)
        return 2
    try:
        return _run_in(checkout, work, sessions, head, rows, data, claude, timeout)
    finally:
        subprocess.run(["chmod", "-R", "u+w", str(checkout)], capture_output=True)
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(checkout)], capture_output=True)


def sweep_token(directory: Path, token: str) -> list[str]:
    """Delete every entry under the directory whose NAME or CONTENT holds the token. Returns one error
    per entry that held it (deleted) or that could not be listed, stat'ed, read or deleted (fail closed:
    an entry the sweep cannot see may hold it). No message carries the token: paths are redacted."""
    errs: list[str] = []
    if not token or not directory.exists():
        return errs

    def say(path, what: str) -> None:
        errs.append(f"{str(path).replace(token, '<subscription token>')} {what}; the run certifies nothing")

    for root, dirs, files in os.walk(directory, onerror=lambda exc: say(exc.filename or directory,
                                                                         "could not be listed")):
        for name in list(dirs):  # os.walk lists a symlink to a directory here, and never follows it
            d = Path(root) / name
            if d.is_symlink():
                dirs.remove(name)
                files.append(name)  # a link: judged by its name and target below, never followed
            elif token in name:
                dirs.remove(name)
                failed = []
                shutil.rmtree(d, onerror=lambda _f, path, _e: failed.append(path))
                for path in failed:
                    say(path, "held or sat under a name holding the subscription token and could not be deleted")
                if not failed:
                    say(d, "held the subscription token in its name; it was deleted")
        for name in files:
            f = Path(root) / name
            try:
                mode = os.lstat(f).st_mode
                if stat.S_ISLNK(mode):
                    held = token in name or token in os.readlink(f)
                elif token in name:
                    held = True
                else:  # only a regular file has content to read (a FIFO would block the read)
                    held = stat.S_ISREG(mode) and token.encode() in f.read_bytes()
                if held:
                    f.unlink()
                    say(f, "held the subscription token (name, link target or content); it was deleted")
            except OSError as exc:
                say(f, f"could not be checked for the subscription token ({type(exc).__name__})")
    return errs


def launch_session(index: int, case: dict, checkout: Path, sessions: Path, claude: str, timeout: int,
                   token: str) -> dict:
    """One case's session. However it ends (judged, refused, timed out, no transcript, an exception),
    every file under the session's directory that holds the subscription token is deleted on the way
    out, and a session that left one certifies nothing (P20 #1298 rounds 4-5: a check on one return
    path left the token in the debug log of a session that wrote no transcript)."""
    home = sessions / f"{index:02d}"
    try:
        result = _launch_session(index, case, checkout, home, claude, timeout, token)
    finally:
        swept = sweep_token(home, token)
    if swept:
        result = dict(result, errors=list(result.get("errors") or []) + [f"case {index}: {e}" for e in swept])
    return result


def _launch_session(index: int, case: dict, checkout: Path, home: Path, claude: str, timeout: int,
                    token: str) -> dict:
    config, log = home / "config", home / "debug.log"
    errs = make_config(config)
    if errs:
        return {"errors": errs}
    env = dict(launch_env(config), CLAUDE_CODE_OAUTH_TOKEN=token)
    argv = [claude, "-p", brief(case["call"]), "--output-format", "json", "--permission-mode", "bypassPermissions",
            "--setting-sources", "project", "--debug-file", str(log)]
    started = dt.datetime.now(dt.timezone.utc)
    try:
        proc = subprocess.run(argv, cwd=checkout, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"errors": [f"case {index}: the session did not finish in {timeout}s"]}
    ended = dt.datetime.now(dt.timezone.utc)
    errs = [f"case {index}: {e}" for e in config_errors(config)]
    try:
        session_id = json.loads(proc.stdout).get("session_id")
    except (json.JSONDecodeError, AttributeError):
        session_id = None
    found = sorted((config / "projects").glob(f"*/{session_id}.jsonl")) if session_id else []
    if len(found) != 1:
        return {"errors": errs + [f"case {index}: the launch named session {session_id!r}, and {len(found)} "
                                  "transcript(s) in its config directory match it"]}
    raw, log_raw = found[0].read_bytes(), (log.read_bytes() if log.exists() else b"")
    if token and (token.encode() in raw or token.encode() in log_raw):
        # Judge nothing from evidence that holds the credential: no evidence line may carry it. The
        # files themselves are deleted by launch_session on the way out, whatever the return path.
        return {"errors": errs + [f"case {index}: the session's transcript or debug log held the subscription "
                                  "token; nothing was judged from it"]}
    text = raw.decode(errors="replace")
    facts = session_facts(text)
    try:
        start = dt.datetime.fromisoformat((facts["started"] or "").replace("Z", "+00:00"))
    except ValueError:
        start = None
    if not facts["cwd"] or Path(facts["cwd"]).resolve() != checkout.resolve():
        errs.append(f"case {index}: the session ran in {facts['cwd']}, not the canary's checkout")
    if start is None or not started - dt.timedelta(seconds=2) <= start <= ended:
        errs.append(f"case {index}: the transcript's session did not start during this launch")
    if facts["permission_mode"] != "bypassPermissions":
        errs.append(f"case {index}: the session ran in permission mode {facts['permission_mode']!r}")
    if not log_raw:
        errs.append(f"case {index}: the harness wrote no debug log; the refusals cannot be attributed")
    if b"API-key auth precedence" in log_raw:
        errs.append(f"case {index}: the session authenticated with an API key, not the subscription token")
    errs += [f"case {index}: {e}" for e in remote_settings_errors(log_raw.decode(errors="replace"))]
    hooks = hook_log(log_raw.decode(errors="replace"))
    errs += [f"case {index}: {e}" for e in log_errors(hooks, checkout)]
    return {"errors": errs, "facts": facts, "calls": transcript_calls_text(text), "segments": hooks["segments"],
            "record": {"session_id": session_id, "exit": proc.returncode, "started": started.isoformat(timespec="seconds"),
                       "ended": ended.isoformat(timespec="seconds"),
                       "transcript": {"path": str(found[0]), "bytes": len(raw), "sha256": sha(raw)},
                       "debug_log": {"path": str(log), "bytes": len(log_raw), "sha256": sha(log_raw)}}}


def _run_in(checkout: Path, work: Path, sessions: Path, head: str, rows: list[dict], data: dict, claude: str,
            timeout: int) -> int:
    problems = [f"{r['id']}: {e}" for r in registered(data) for e in canary_errors(r.get("canary"), r)]
    login, login_errors = subscription_login()
    problems += login_errors
    if problems:
        print("\n".join(f"run: {p}" for p in problems), file=sys.stderr)
        return 1
    subprocess.run(["chmod", "-R", "a-w", str(checkout)], check=True, capture_output=True)
    if plan(work) != 0:
        return 1
    plan_data = json.loads((work / "plan.json").read_text())
    cases = [(row, case) for row in rows for case in expected_cases(row, work)]
    paths = bound_paths(checkout, rows)
    version = harness_version(claude)
    before = snapshot(paths)
    # EVERY settings validation runs here, once, after the "before" snapshot: equal snapshots then
    # prove the validated content was in force for every session. A check anywhere else leaves a
    # window a change can enter unvalidated; rounds 8-11 of P20 #1298 found four such checks one at
    # a time (managed env, the window's end, the bound-input set, hook-entry keys), so there is one.
    window = settings_validation(checkout)
    if sorted(map(str, bound_paths(checkout, rows))) != sorted(map(str, paths)):
        # A managed drop-in (or any bound file) appeared after the paths were listed: it would be
        # validated but never snapshotted, so a later edit to it would go unseen (P20 #1298 round 10).
        window.append("the set of bound inputs changed before the run began (a managed drop-in appeared)")
    if window:
        print("\n".join(f"run: {p}" for p in window), file=sys.stderr)
        return 1
    started = dt.datetime.now(dt.timezone.utc)
    try:
        with ThreadPoolExecutor(max_workers=int(os.environ.get("RULES_CANARY_PARALLEL") or 4)) as pool:
            outcomes = list(pool.map(lambda ic: launch_session(ic[0], ic[1][1], checkout, sessions, claude, timeout,
                                                               login["token"]),
                                     enumerate(cases)))
    finally:
        # Whatever the sessions or their hooks wrote anywhere in the run (markers in work/, logs in
        # sessions/), on every path out: no file the run leaves may hold the token (P20 #1298 round 6).
        swept = sweep_token(work, login["token"]) + sweep_token(sessions, login["token"])
    ended = dt.datetime.now(dt.timezone.utc)
    after = snapshot(paths)
    errs = [f"{p} changed during the run" for p in paths if before[str(p)] != after[str(p)]]
    if git_out("rev-parse", "HEAD", cwd=checkout) != head:
        errs.append("the checkout's HEAD moved during the run")
    if git_out("rev-parse", "HEAD") != head or git_out("status", "--porcelain", "--untracked-files=no"):
        errs.append("the tree under test changed during the run (its receipt would describe other code)")
    errs += [e for o in outcomes for e in o["errors"]] + swept
    for o in outcomes:
        v = (o.get("facts") or {}).get("version")
        if not v:
            errs.append("a session's transcript records no Claude Code version")
        elif not version or v not in version.split():
            errs.append(f"a session ran Claude Code {v}, the launched binary is {version}")
    if errs:
        print("run: " + "; ".join(sorted(set(errs))), file=sys.stderr)
        return 1
    bound = {p: (v[0][:12] if v and v[0] != "dir" else ("dir" if v else "absent")) for p, v in before.items()}
    receipt = {"version": 5, "generated_at": ended.isoformat(timespec="seconds"), "harness": version, "commit": head,
               "parser": PARSER, "judge_sha256": judge_sha(),
               "launch": {"claude": claude, "cwd": str(checkout), "env": launch_env(sessions / "NN" / "config"),
                          "permission_mode": "bypassPermissions", "sessions": len(outcomes),
                          "auth": {"via": "CLAUDE_CODE_OAUTH_TOKEN", "plan": login["plan"], "tier": login["tier"]},
                          "started": started.isoformat(timespec="seconds"), "ended": ended.isoformat(timespec="seconds")},
               "bound": {"sha256": sha(json.dumps({p: (v[0] if v else None) for p, v in before.items()}, sort_keys=True)),
                         "files": bound},
               "settings_sha256": {"project": file_sha(checkout / ".claude" / "settings.json"),
                                   "managed": managed_digest(), "user": file_sha(user_settings())},
               "rows": {}}
    failed, index = 0, 0
    for row in rows:
        results = []
        for case in expected_cases(row, work):
            o = outcomes[index]
            ok, evidence = judge_case(case, o["calls"], o["segments"], plan_data["unchanged"], row, checkout)
            key = case_key(expected_cases(row, "{run}")[len(results)])
            results.append({"case": key, "kind": case["kind"], "ok": ok, "evidence": evidence, "session": o["record"]})
            index += 1
        ok = bool(results) and all(r["ok"] for r in results)
        failed += not ok
        receipt["rows"][row["id"]] = {"row_sha256": row_sha(row), "deps": deps_digest(row, checkout), "pass": ok,
                                      "results": results}
        print(f"{'ok  ' if ok else 'FAIL'} {row['id']}: " + "; ".join(
            f"{r['kind']} {'ok' if r['ok'] else r['evidence']}" for r in results))
    out = receipt_path()
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if login["token"] in text:  # unreachable while the per-session check holds; the receipt is public
        print("run: the receipt would hold the subscription token; not written", file=sys.stderr)
        return 1
    out.write_text(text)
    print(f"run: receipt at {out.relative_to(ROOT)} ({len(outcomes)} sessions); {failed} row(s) failed")
    return 1 if failed else 0


def freshness(row: dict, receipt: dict | None, check_user: bool, check_harness: bool) -> list[str]:
    """Why this registered row's receipt does not certify the current tree (empty: it does)."""
    canary = row.get("canary")
    errs = canary_errors(canary, row)
    if errs or "none" in canary:
        return errs
    receipt = receipt or {}
    entry = receipt.get("rows", {}).get(row["id"])
    if not entry:
        return ["no canary receipt for this row; run `make rules-canary` and commit the receipt"]
    stale = []
    launch = receipt.get("launch") or {}
    sessions_ok = all((r.get("session") or {}).get("debug_log", {}).get("sha256")
                      and (r.get("session") or {}).get("transcript", {}).get("sha256") for r in entry.get("results") or [])
    if receipt.get("version") != 5 or not receipt.get("harness") or not launch.get("claude") \
            or not (receipt.get("bound") or {}).get("sha256") or not sessions_ok or not entry.get("results"):
        stale.append("the receipt is not one a controlled launch wrote (version 5, launch, bound inputs, per-case sessions)")
    if (launch.get("auth") or {}).get("plan") not in SUBSCRIPTION_PLANS:
        stale.append("the receipt's sessions did not run on a personal subscription login (launch.auth.plan)")
    if receipt.get("parser") != PARSER:
        stale.append(f"the receipt was judged under parser {receipt.get('parser')!r}, not {PARSER!r}")
    # The receipt is bound to CONTENT (the row, the enforcer's closure, the settings, the plan and the
    # canary's own judging code), not to a commit: the merge squashes the commit it ran at away (P20
    # #1298 round 7), and the commit is kept as provenance only.
    if receipt.get("judge_sha256") != judge_sha():
        stale.append("the canary's judging code (scripts/rules_canary.py, scripts/governance_paths.py) changed "
                     "since the canary ran")
    expected = [case_key(c) for c in expected_cases(row, "{run}")]
    results = entry.get("results") or []
    if not entry.get("pass") or not expected or [r.get("case") for r in results] != expected \
            or not all(r.get("ok") for r in results):
        stale.append("the canary did not pass every case the registry declares now")
    if entry.get("row_sha256") != row_sha(row):
        stale.append("the row changed since the canary ran")
    now, then = deps_digest(row), entry.get("deps") or {}
    if now["sha256"] != then.get("sha256"):
        a, b = now["files"], then.get("files") or {}
        changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        stale.append(f"the enforcer or a file it depends on changed ({', '.join(changed[:4]) or 'content'})")
    if receipt.get("settings_sha256", {}).get("project") != file_sha(ROOT / ".claude" / "settings.json"):
        stale.append("the project settings changed since the canary ran")
    # Managed and user settings are the canary machine's: compared there, not in CI (another machine).
    if check_user and receipt.get("settings_sha256", {}).get("managed") != managed_digest():
        stale.append("the managed settings changed since the canary ran")
    if check_user and receipt.get("settings_sha256", {}).get("user") != file_sha(user_settings()):
        stale.append("the user settings changed since the canary ran")
    if check_harness:
        local = shutil.which("claude")
        if not local:
            stale.append("no claude on PATH to compare the harness with")
        version = harness_version(local) if local else None
        if local and not version:
            stale.append(f"`{local} --version` reported no version to compare the harness with")
        if version and version != receipt.get("harness"):
            stale.append(f"the harness is {version}, the canary ran on {receipt.get('harness')}")
        if local and os.path.realpath(local) != os.path.realpath(launch.get("claude") or ""):
            stale.append(f"the canary launched {launch.get('claude')}, not this machine's claude ({local})")
    return [f"canary receipt stale: {'; '.join(stale)}; rerun the canary"] if stale else []


def load_receipt() -> dict | None:
    try:
        return json.loads(governance_file(ROOT, RECEIPT_NAME).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="launch the canary session and write the receipt")
    r.add_argument("--commit", help="the commit under test (default HEAD; the checkout must be clean at it)")
    r.add_argument("--dir", help="a fresh directory for the run (default under $RULES_CANARY_SCRATCH or the temp dir)")
    r.add_argument("--claude", default="claude", help="the Claude Code binary to launch")
    r.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args(argv)
    return run(args.commit, Path(args.dir) if args.dir else None, args.claude, args.timeout)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
