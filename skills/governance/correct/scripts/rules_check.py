#!/usr/bin/env -S python3 -I
"""rules_check.py — replay every rule in the registry (rules.yaml) against its enforcer (BRO-3800).

The registry pairs each rule an agent session is held to with what enforces it.
This script checks the pairing within an OBSERVABLE claim (P20 #1298 continuation review,
STRUCTURAL): for every registered row, it executes the registered commands with the recorded
inputs, environment, working directory and timeout, and judges their output under each event's
declared contract; the row passes when, in AGGREGATE (any refusing registration refuses, as the
harness combines hooks), every proof is refused for the expected reason and every control is
allowed. It does not claim that Claude Code loads the settings file or dispatches the hook: a
schema error anywhere in a settings file makes the harness load none of its hooks, and no static
check can certify that. Whether the real harness refuses is certified by the canary
(scripts/rules_canary.py, BRO-3814): real sessions per registered row, receipts bound to the
harness version, settings and enforcer content, and a row whose receipt is stale FAILs here. Three P20 rounds found one defect
class at eleven sites: a status other than FAIL while the enforcer the harness
runs did not decide (a substring "registration", `python3 -c path`, a proof that
named the enforcer as an argument, a crash read as a decision, an absent hook
read as SKIP; then rows proven by a test or a reference skipping the live check,
a PENDING granted to any outside file, a tool the gate was never dispatched).
The round-3 continuation review returned STRUCTURAL, and this is the hoist:

  1. A row with `enforcer.registered` is replayed LIVE, behaviorally, before any
     other evidence counts: every proof and control, through every registration
     the harness would dispatch that case to (the settings command, `sh -c`,
     CLAUDE_PROJECT_DIR set), judged like the in-tree replay (decision, reason,
     remedy). A registered row without proofs and controls FAILs; `proof_test`
     and `proof_ref` add evidence and never replace it. A live failure is a FAIL
     whichever checkout's copy the harness runs.
  2. `registered.tools` is the contract for a per-tool event: each listed tool
     needs a proof and a registration, every case's tool must be listed, and
     completeness fails when the enforcer is registered for a tool no contract
     lists.
  3. A command proof gives only ARGUMENTS; the runner launches the enforcer.
  4. Fail closed (P20 #1298 round 2): an enforcer's hook entry may carry only allowlisted keys, its
     event must act before the action, settings `env` is replayed, a registered row's cases may
     only move state into {scratch}, and `--base` ratchets every obligation by content. The
     checker vouches for what it can replay and FAILs the rest, instead of modelling one more
     harness field per review round.
  5. Missing evidence is a FAIL wherever it must exist. A machine-local or
     user-scope row declares the hosts that must have it (`hosts:`); elsewhere it
     is SKIP, never PASS. A host matches on any of the machine's names.
  6. A decision is exit 0 (by JSON) or exit 2 (a block, for hooks) / exit 1 with
     the expected output (for commands). Anything else is an error.

`known_misses` are inputs the enforcer should refuse and does not yet, each with
its ticket; one that starts being refused FAILS until it moves to `proofs`.

Completeness fails when a patterned policy gate, a hook on any event that can
block (every event not in NON_BLOCKING_EVENTS) in project settings, project local
settings, and (on the hosts in `user_settings_on`) user and managed settings, or a
git hook in .githooks/ has no row and is not in hooks_not_rules, or when a
required source cannot be read. Plugin hooks are not scanned yet (BRO-3811; noted in the
registry header).

  rules_check.py                 table; exit 1 on any FAIL or an empty registry
  rules_check.py --ci            skip the user-settings scan
  rules_check.py --json | --markdown | --only ID ...

RULES_CHECK_ROOT, RULES_CHECK_HOME and RULES_CHECK_HOST override the repo root,
the home directory and the host names (comma-separated; tests use all three).

Replay containment (P20 #1299 rounds 8-14) protects the machine from a MISTAKEN registered row:
every setup step and replayed enforcer runs with git and Python sealed, with HOME, the p9 home
and the p9 session defaulted into the scratch (a case may only narrow them there), and a case
writes data files, never code and never a filled governance file. It does not make a row
untrusted input: rows, like the enforcers they replay, are repository code that review and the
registry ratchet judge, and a row that forges its own fixture is caught there, as a row that edits
its hook would be. `proof_test`, `applies` and the setup of an unregistered row run as the
repository's own code (BRO-3883 tracks narrowing them).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shlex
import shutil
import site
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

# The shebang runs this file isolated (-I), which hides user site-packages, and
# PyYAML lives there on the workstation. Re-add that one directory by APPENDING it.
_USER_SITE = site.getusersitepackages()
if _USER_SITE not in sys.path:
    sys.path.append(_USER_SITE)
# Appended, not prepended, for the same reason: the shared layout resolver lives beside
# this file (scripts/governance_paths.py) and must not let scripts/ shadow the stdlib.
sys.path.append(str(Path(__file__).resolve().parent))
from governance_paths import governance_file as _governance_file, governance_globs  # noqa: E402
import rules_canary as _canary  # noqa: E402  (the real-harness receipts, BRO-3814)

CANARY_RECEIPT: dict | None = None  # the committed canary receipt, read by main()
REPLAY_ONLY = False  # --replay-only: judge the replay layer alone (the registry mutation test uses it)
try:
    import yaml
except ImportError:  # surfaced as a hard exit, never a silent pass
    yaml = None

ROOT = Path(os.environ.get("RULES_CHECK_ROOT") or Path(__file__).resolve().parent.parent)
HOME = Path(os.environ.get("RULES_CHECK_HOME") or os.path.expanduser("~"))


def host_identities() -> list[str]:
    """Every name this machine answers to; a declared host matches on any of them.

    The network hostname comes from DHCP and changes under a session: on 2026-11-16
    one session saw one .lan name, then another, and every user-scope row went SKIP
    on the very host that declares them. macOS LocalHostName is set by the owner and
    does not follow the network, so it is read too.
    """
    if os.environ.get("RULES_CHECK_HOST"):
        return [h for h in os.environ["RULES_CHECK_HOST"].split(",") if h]
    names = [socket.gethostname()]
    if sys.platform == "darwin":
        try:
            local = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True,
                                   text=True, timeout=5)
            if local.returncode == 0 and local.stdout.strip() not in ("", *names):
                names.append(local.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
    return names


HOST_IDENTITIES = host_identities()
HOSTNAME = " / ".join(HOST_IDENTITIES)


def governance_file(name: str) -> Path:
    """The registry or policy under ROOT, new layout first (BRO-3200; governance_paths.py)."""
    return _governance_file(ROOT, name)


REGISTRY = governance_file("rules.yaml")

# The correction ladder, highest first. Where a check runs is `runs_in`, not a level.
ENFORCING_LEVELS = ["architecture", "types", "lint", "test", "hook"]
LEVELS = ENFORCING_LEVELS + ["sensor", "judgment", "gap"]
CLASS_THRESHOLD = 2
# Completeness fails closed: every hook event can stop or redirect the agent unless it is on this
# list (Claude Code: these only observe or add context). A new event is blocking until listed here.
NON_BLOCKING_EVENTS = ("SessionStart", "SessionEnd", "Notification", "PreCompact", "PostToolUse",
                       "PostToolUseFailure")
# Events dispatched per tool: a registered row on one of them states its tools explicitly.
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest")
# Events whose hook can stop the action it guards: a tool call before it runs, a prompt, a turn end.
PRE_ACTION_EVENTS = ("PreToolUse", "PermissionRequest", "UserPromptSubmit", "Stop", "SubagentStop")
# What a case of a REGISTERED row may set: its env only relocates state into {scratch}, and its setup
# only builds files there. Anything else could make a broken enforcer look like it refuses.
CASE_ENV_KEYS = {"HOME": "path", "BROOMVA_P9_HOME": "path", "BROOMVA_P9_SESSION": "name"}
SETUP_COMMANDS = {"git", "mkdir", "touch"}
P9_SCRIPTS = "{home}/.agents/skills/p9/scripts"
# What a case may write: data, never code or a filled governance file (scripts/rules_case_data.py).
from rules_case_data import DATA_SUFFIXES, data_name_error  # noqa: E402,F401
INTERPRETERS = {"python", "python3", "bash", "sh", "zsh", "env", "node", "bun"}
MANAGED_SETTINGS = Path(os.environ.get("RULES_CHECK_MANAGED_SETTINGS")
                        or "/Library/Application Support/ClaudeCode/managed-settings.json")


class Result:
    def __init__(self, rule_id: str, level: str):
        self.rule_id, self.level = rule_id, level
        self.fails: list[str] = []
        self.notes: list[str] = []
        self.skipped: list[str] = []
        self.external = False

    @property
    def status(self) -> str:
        if self.fails:
            return "FAIL"
        if self.level == "gap":
            return "GAP"
        if self.level == "judgment":
            return "REPEAT" if any(n.startswith("repeat") for n in self.notes) else "JUDGMENT"
        if self.skipped:
            return "SKIP"
        return "EXTERNAL" if self.external else "PASS"

    def detail(self) -> str:
        return "; ".join(self.fails or self.skipped or self.notes)

    def as_dict(self) -> dict:
        return {"id": self.rule_id, "level": self.level, "status": self.status, "fails": self.fails,
                "notes": self.notes, "skipped": self.skipped}


# ── hosts ──────────────────────────────────────────────────────────────────────
HOST_GROUPS: dict = {}  # the top-level `hosts:` of the registry being checked; set by main()


def host_names(data: dict) -> set[str]:
    return {name for name, patterns in (data.get("hosts") or {}).items()
            if any(fnmatch.fnmatch(h, p) for h in HOST_IDENTITIES for p in patterns or [])}


def resolve(path: str) -> Path:
    if path.startswith("~/"):
        return HOME / path[2:]
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def host_bound(rule: dict) -> bool:
    enforcer = rule.get("enforcer") or {}
    path = enforcer.get("path") or ""
    scope = (enforcer.get("registered") or {}).get("scope", "project")
    return path.startswith("~/") or Path(path).is_absolute() or scope == "user"


# ── settings ───────────────────────────────────────────────────────────────────
def registrations(settings_path: Path) -> list[tuple[str, str | None, str, dict]]:
    """(event, matcher, command, hook entry) for every hook. Raises on an unreadable file."""
    data = json.loads(settings_path.read_text())
    out = []
    for event, entries in (data.get("hooks") or {}).items():
        for entry in entries or []:
            for hook in entry.get("hooks", []) or []:
                out.append((event, entry.get("matcher"), hook.get("command") or "", hook))
    return out


# The hook-entry keys the checker can vouch for. Every round that modelled one more harness field
# (async, once, if, then shell, exec-form args, onFailure ...) was followed by one it did not model,
# so the entry is an ALLOWLIST: an enforcer registration carrying any other key is not vouched for
# and its row FAILs, whatever the harness does with the key (P20 #1298 round 2, both strata).
# Keys starting with `_` are documentation (`_purpose`); the harness ignores them.
HOOK_ENTRY_KEYS = _canary.HOOK_ENTRY_KEYS  # one definition, shared with the canary
DEFAULT_TIMEOUT_S = 60


def inert_reason(hook: dict) -> str | None:
    """Why the checker cannot vouch that the harness blocks with this entry, or None."""
    if hook.get("type") != "command":
        return f"type {hook.get('type')!r}: an enforcer's entry states type: command"
    if not isinstance(hook.get("command"), str) or not hook["command"].strip():
        return "command must be a non-empty string"
    timeout = hook.get("timeout")
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0):
        return f"timeout {timeout!r} must be a positive number (the harness rejects the whole file otherwise)"
    if "statusMessage" in hook and not isinstance(hook["statusMessage"], str):
        return "statusMessage must be a string"
    extra = sorted(k for k in hook if k not in HOOK_ENTRY_KEYS and not str(k).startswith("_"))
    if extra:
        return (f"key(s) {extra} are outside the hook-entry allowlist {sorted(HOOK_ENTRY_KEYS)}; the "
                "checker cannot vouch for how the harness runs it. Remove them, or extend the allowlist "
                "with a test that replays their effect")
    return None


def user_settings() -> Path:
    """User settings; RULES_CHECK_USER_SETTINGS points the mutation test at a modified copy."""
    return Path(os.environ.get("RULES_CHECK_USER_SETTINGS") or HOME / ".claude" / "settings.json")


def settings_for(scope: str) -> Path:
    return ROOT / ".claude" / "settings.json" if scope == "project" else user_settings()


MATCHER_ALT = re.compile(r"[A-Za-z0-9_\-]+(\.\*)?")  # Bash, mcp__linear-server__.* (same in JS and Python)


def matcher_errors(matcher: str | None) -> list[str]:
    """Alternatives an enforcer's matcher may use: the only regex both dialects read the same way."""
    if matcher in (None, "", "*"):
        return []
    return [f"matcher alternative {alt!r} is outside the subset the checker can match like the harness "
            "(a tool name, or a name prefix ending in .*)" for alt in matcher.split("|") if not MATCHER_ALT.fullmatch(alt)]


def matcher_covers(matcher: str | None, tool: str | None) -> bool:
    if not tool or matcher in (None, "", "*"):
        return True
    try:
        return re.fullmatch(matcher, tool) is not None
    except re.error:
        return matcher == tool


ROOT_TOKEN = "\x00ROOT\x00"  # stands in for the project dir while splitting, so a space in it cannot split


def expand(command: str) -> str:
    return command.replace('"$CLAUDE_PROJECT_DIR"', ROOT_TOKEN).replace("${CLAUDE_PROJECT_DIR}", ROOT_TOKEN) \
        .replace("$CLAUDE_PROJECT_DIR", ROOT_TOKEN)


# Words that run the next word as the command (`exec gate.sh`, `env X=1 gate.sh`).
COMMAND_PREFIXES = {"exec", "command", "nohup", "env", "time"}
SHELLS = {"sh", "bash", "zsh"}


def script_path(script: str) -> Path:
    """A registered script as the harness resolves it: relative to the project directory."""
    path = Path(script).expanduser()
    return path if path.is_absolute() else ROOT / path


def first_simple_command(command: str) -> list[str] | None:
    """The words of the command's first simple command (before any `;`, `&&`, `||`, `|` or
    redirection), as the shell splits them; None when it cannot be parsed."""
    try:
        lexer = shlex.shlex(expand(command), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = [tok.replace(ROOT_TOKEN, str(ROOT)) for tok in lexer]
    except ValueError:
        return None
    simple: list[str] = []
    for tok in tokens:
        if tok and all(ch in "();<>|&" for ch in tok):
            if tok[0] in "<>" and simple and simple[-1].isdigit():
                simple.pop()  # the fd of `2>/dev/null` is not an argument
            break
        simple.append(tok)
    return simple


def invocation(command: str) -> tuple[str | None, list[str]]:
    """(script, args) of the command's FIRST simple command, as the shell splits it.

    `gate.sh; true`, `gate.sh 2>/dev/null || true` and `exec gate.sh` all run gate.sh with no
    arguments. Anything this cannot parse names no script, so it owns no row: a false FAIL,
    never a false PASS. Whether the command enforces is decided by running it.
    """
    simple = first_simple_command(command)
    if simple is None:
        return None, []
    interpreter = None
    for i, tok in enumerate(simple):
        if tok in ("-c", "-e") and interpreter:
            # `sh -c 'gate.sh'` runs the string as a command; `python3 -c path` runs it as code.
            if interpreter in SHELLS and i + 1 < len(simple):
                return invocation(simple[i + 1])
            return None, []
        if Path(tok).name in INTERPRETERS:
            interpreter = Path(tok).name
            continue
        if tok in COMMAND_PREFIXES or tok.startswith("-") or ("=" in tok and not tok.startswith(("/", ".", "~"))):
            continue
        return tok, simple[i + 1:]
    return None, []


def script_of(command: str) -> str | None:
    """The script a command runs (classification only; liveness is proven by running it)."""
    return invocation(command)[0]


def same_script(command: str, target: Path, path: str, scope: str = "project") -> bool:
    """Does this registered command run the row's enforcer? By resolved path, never by substring.

    A command may run another checkout's copy of an in-repo enforcer (the main checkout's, from a
    worktree): it matches on the repo-relative path. Whether that copy enforces is then decided by
    replaying it, and a copy that does not is a FAIL.
    """
    script = script_of(command)
    if not script:
        return False
    live = script_path(script)
    try:
        if live.resolve() == target.resolve():
            return True
    except OSError:
        return False
    rel = Path(path)
    return not rel.is_absolute() and not path.startswith("~") and live.parts[-len(rel.parts):] == rel.parts


# ── what the harness runs: one definition, used by every check ───────────────────
class Reg(tuple):
    """One registered hook command: (source, scope, event, matcher, command, hook entry, inert)."""
    __slots__ = ()

    def __new__(cls, source, scope, event, matcher, command, hook=None, inert=None):
        return super().__new__(cls, (source, scope, event, matcher, command, hook or {}, inert))

    source = property(lambda s: s[0])
    scope = property(lambda s: s[1])
    event = property(lambda s: s[2])
    matcher = property(lambda s: s[3])
    command = property(lambda s: s[4])
    hook = property(lambda s: s[5])
    inert = property(lambda s: s[6])  # why the harness would not block with it, or None

    @property
    def timeout(self) -> float:
        try:
            return float(self.hook.get("timeout") or DEFAULT_TIMEOUT_S)
        except (TypeError, ValueError):
            return float(DEFAULT_TIMEOUT_S)


def harness_sources(data: dict, ci: bool, hosts_here: set[str]) -> list[tuple[Path, bool, str]]:
    """(path, required, scope) for every settings file the harness merges here.

    Project settings and project local settings always; user and managed settings on the hosts in
    `user_settings_on` (not under --ci, which has no user). An optional file counts when present.
    """
    sources = [(ROOT / ".claude" / "settings.json", True, "project"),
               (ROOT / ".claude" / "settings.local.json", False, "project")]
    if not ci and set(data.get("user_settings_on") or []) & hosts_here:
        sources += [(user_settings(), True, "user"), (MANAGED_SETTINGS, False, "user")]
    return sources


HARNESS_ENV: dict[str, str] = {}  # the merged settings `env`, set by harness_registrations()


def harness_registrations(data: dict, ci: bool, hosts_here: set[str]) -> tuple[list[Reg], list[str]]:
    """Every hook command the harness would load here, and the required sources it could not read."""
    regs, errors, off, managed_only = [], [], None, None
    for source, required, scope in harness_sources(data, ci, hosts_here):
        if not required and not source.exists():
            continue
        try:
            settings = json.loads(source.read_text())
            regs += [Reg(source, scope, e, m, c, h, inert_reason(h)) for e, m, c, h in registrations(source)]
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read {source} ({exc})")
            continue
        if settings.get("disableAllHooks"):
            off = f"disableAllHooks in {source.name}"
        if settings.get("allowManagedHooksOnly"):
            managed_only = f"allowManagedHooksOnly in {source.name}"
    # The harness passes the merged settings `env` to every hook (user < project < local < managed);
    # the replay runs with it, so an env that disables a gate makes the row FAIL by behaviour.
    order = {"user": 0, "project": 1}
    HARNESS_ENV.clear()
    for source, _required, scope in sorted(harness_sources(data, ci, hosts_here),
                                           key=lambda s: (s[0] == MANAGED_SETTINGS, order.get(s[2], 0),
                                                          s[0].name == "settings.local.json")):
        if source.exists():
            try:
                HARNESS_ENV.update({str(k): str(v) for k, v in (json.loads(source.read_text()).get("env") or {}).items()})
            except (OSError, json.JSONDecodeError, AttributeError):
                pass
    # Switches that turn whole sources off: no hook blocks, or only managed ones load.
    if off or managed_only:
        regs = [r if (r.inert or (not off and r.source == MANAGED_SETTINGS))
                else Reg(r.source, r.scope, r.event, r.matcher, r.command, r.hook, off or managed_only)
                for r in regs]
    return regs, errors


def runs_enforcer(rule: dict, reg: Reg) -> bool:
    """The registration runs this row's enforcer, and only it, with exactly this row's arguments.

    Ownership needs one CANONICAL form (rules_canary.CANONICAL): `gate.sh; true`, `sh -c 'gate.sh'`,
    `exec gate.sh` or `gate.sh </dev/null; other.sh` own no row, because the decision of a compound
    command cannot be attributed to one script (P20 #1298: the replay of `gate.sh </dev/null;
    impostor.sh` refused, and the gate was credited with the impostor's refusal). The row then reads
    "not registered" and FAILs."""
    enforcer = rule.get("enforcer") or {}
    path = enforcer.get("path")
    if not path:
        return False
    inv = _canary.simple_invocation(reg.command, str(ROOT))
    if inv is None:
        return False
    script, args = inv
    return (same_script(shlex.quote(script), resolve(path), path)
            and args == [str(a) for a in enforcer.get("args") or []])


def owns(rule: dict, reg: Reg) -> bool:
    """The row declares this registration: its enforcer, its arguments, its event and scope."""
    declared = (rule.get("enforcer") or {}).get("registered")
    return (isinstance(declared, dict) and declared.get("event") == reg.event
            and declared.get("scope", "project") == reg.scope and runs_enforcer(rule, reg))


def is_literal(tool: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_\-]+", tool or "") is not None


def entry_covers(entry: str, tool: str | None) -> bool:
    """A contract entry is a tool name or a matcher pattern; does it cover this tool?"""
    return entry == tool if is_literal(entry) else matcher_covers(entry, tool)


def under_root(path: str) -> bool:
    try:
        Path(path).resolve().relative_to(ROOT.resolve())
        return True
    except (ValueError, OSError):
        return False


# ── replay ─────────────────────────────────────────────────────────────────────
def fill(value, scratch: Path):
    if isinstance(value, str):
        return value.replace("{root}", str(ROOT)).replace("{scratch}", str(scratch)).replace("{home}", str(HOME))
    if isinstance(value, list):
        return [fill(v, scratch) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, scratch) for k, v in value.items()}
    return value


def interpreter_for(path: Path) -> list[str]:
    if path.suffix == ".sh":
        return ["bash", str(path)]
    if path.suffix == ".py":
        return [sys.executable, "-I", str(path)]
    return [str(path)]


# The caller's variables a replay keeps: an allowlist, not a list of names to drop. GIT_* (round 12),
# PYTHON* (round 13) and then BSTACK_ALLOW_MAIN_EDIT (round 15) each changed a verdict from the
# caller's shell, one leak a round (P20 #1299 round 15, stratum B).
CALLER_ENV_KEPT = ("PATH", "LANG", "LANGUAGE", "TMPDIR", "USER", "LOGNAME", "SHELL", "TERM", "TZ")


def base_env(scratch: Path, case: dict, extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k in CALLER_ENV_KEPT or k.startswith("LC_")}
    env.update({"CLAUDE_PROJECT_DIR": str(ROOT), "RULES_CHECK_REPLAY": "1",
                "BROOMVA_CONTROL_DECISION_LEDGER": str(scratch / "decisions.jsonl"),
                "BSTACK_WRITE_GATE_EVENTS_LOG": str(scratch / "write-gate-events.jsonl")})
    # The invoking user's state stays out of reach: a case that names no HOME or p9 home still
    # replays against its scratch, never the live queue, wait marks or fleet logs (P20 #1299 r14 B).
    env.update({"HOME": str(scratch / "home"), "BROOMVA_P9_HOME": str(scratch / "p9"),
                "BROOMVA_P9_SESSION": "rules-check"})
    env.update(extra or {})  # the harness's own settings env, for a live replay
    env.update({k: str(v) for k, v in fill(case.get("env") or {}, scratch).items()})
    env.update(GIT_SEALED(scratch))
    # Python likewise imports nothing a case wrote (P20 #1299 rounds 12-13): no script or working
    # directory on sys.path, and the user site is the invoking user's, wherever HOME points (a .pth
    # there runs at every start). Every PYTHON* from the caller is dropped above.
    env.update({"PYTHONSAFEPATH": "1", "PYTHONUSERBASE": REAL_USER_BASE})
    return env


# The user base of the invoking user, fixed before any case moves HOME: an enforcer that appends
# site.getusersitepackages() itself (the control gate, for PyYAML) reads the real one (P20 #1299 r13).
REAL_USER_BASE = __import__("site").getuserbase()


def GIT_SEALED(scratch: Path) -> dict:
    """Git in a replay reads only what the case built (P20 #1299 round 11, stratum C): a case may move
    HOME into its scratch and write files there, so git reads no global or system config, finds no
    repository above the scratch, and opens a bare repository only when one is named. Set last: a
    case's env cannot undo it. (A setup also may not write a .git* path: see case_errors.)"""
    # Environment config outranks a repository's own, so a planted core.fsmonitor or hooks path
    # never runs, whatever channel wrote it (P20 #1299 round 12, stratum C).
    overrides = {"safe.bareRepository": "explicit", "core.fsmonitor": "false", "core.hooksPath": os.devnull}
    env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CEILING_DIRECTORIES": str(scratch),
           "GIT_CONFIG_COUNT": str(len(overrides))}
    for i, (key, value) in enumerate(overrides.items()):
        env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = key, value
    return env


def write_transcript(scratch: Path, turns: list[dict]) -> Path:
    path = scratch / "transcript.jsonl"
    with path.open("w") as f:
        for turn in turns:
            role = turn.get("role", "assistant")
            entry = {"type": role, "message": {"role": role, "content": [
                {"type": "text", "text": turn.get("text", "")}]}}
            if "origin" in turn:
                entry["origin"] = turn["origin"]  # who wrote a user line: the owner, a task, a peer
            f.write(json.dumps(entry) + "\n")
    return path


def run_setup(case: dict, scratch: Path) -> None:
    for argv in case.get("setup") or []:
        proc = subprocess.run(fill(argv, scratch), capture_output=True, text=True, cwd=str(scratch),
                              env=base_env(scratch, case), timeout=60)
        if proc.returncode != 0:
            raise OSError(f"setup {argv[:2]} exited {proc.returncode}: {proc.stderr.strip()[:200]}")


# How each event's hook says "refuse" in JSON (exit 2 refuses on every blocking event). Output
# shaped for another event is not a decision for this one (P20 #1298 round 3, stratum A).
JSON_REFUSALS = {
    "PreToolUse": ("decision", "permissionDecision"),
    "PermissionRequest": ("behavior",),
    "UserPromptSubmit": ("decision",),
    "Stop": ("decision",),
    "SubagentStop": ("decision",),
}


def hook_decision(proc: subprocess.CompletedProcess, event: str = "PreToolUse") -> tuple[str, str]:
    if proc.returncode == 2:
        return "block", (proc.stderr or proc.stdout or "").strip()
    if proc.returncode != 0:
        return "error", f"exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:160]}"
    text = (proc.stdout or "").strip()
    if text.startswith("{"):
        # The harness reads a JSON decision only when ALL of stdout is one JSON object; a stray line
        # before it (a BASH_ENV echo, a debug print) makes the harness ignore the decision.
        try:
            out = json.loads(text)
        except json.JSONDecodeError:
            return "allow", "stdout is not a single JSON object; the harness ignores it"
        if not isinstance(out, dict):
            return "allow", ""
        spec = out.get("hookSpecificOutput") or {}
        if not isinstance(spec, dict) or spec.get("hookEventName") not in (None, event):
            spec = {}  # output for another event
        forms = JSON_REFUSALS.get(event, ())
        decision = spec.get("decision") if isinstance(spec.get("decision"), dict) else {}
        if ("decision" in forms and str(out.get("decision", "")).lower() == "block") or \
                ("permissionDecision" in forms and str(spec.get("permissionDecision", "")).lower() == "deny") or \
                ("behavior" in forms and str(decision.get("behavior", "")).lower() == "deny"):
            return "block", str(out.get("reason") or spec.get("permissionDecisionReason")
                                or decision.get("message") or "")
        return "allow", ""
    return "allow", ""


def hook_event(case: dict, scratch: Path) -> str:
    event = fill(json.loads(json.dumps(case.get("event") or {})), scratch)
    event.setdefault("cwd", str(ROOT))
    if "transcript" in case:
        event["transcript_path"] = str(write_transcript(scratch, case["transcript"]))
    return json.dumps(event)


def replay_in_tree(target: Path, case: dict, scratch: Path, args: list | None,
                   event: str = "PreToolUse") -> tuple[str, str]:
    """The enforcer at this checkout, as a hook (event on stdin) or a command (args)."""
    if "args" in case:
        for name, body in (case.get("files") or {}).items():  # fixture files for a command proof
            dest = scratch / name
            # Judged where it is written, for every row (P20 #1299 r12, stratum B): the resolved path
            # stays in the scratch and is not one git reads.
            real, top = os.path.realpath(dest), os.path.realpath(scratch)
            if not real.startswith(top + os.sep) or any(part.casefold() in (".git", ".gitconfig")
                                                        for part in Path(real[len(top):]).parts):
                raise OSError(f"files {name} must be a path inside {{scratch}} that git does not read")
            if data_name_error(name):
                raise OSError(f"files {data_name_error(name)}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body)
        proc = subprocess.run(interpreter_for(target) + fill(case["args"], scratch), capture_output=True,
                              text=True, cwd=str(fill(case.get("cwd", "{root}"), scratch)),
                              env=base_env(scratch, case), timeout=600)
        out = proc.stdout + proc.stderr
        if proc.returncode == 0:
            return "allow", out
        if proc.returncode == 1:
            return "block", out
        return "error", f"exit {proc.returncode}: {out.strip()[:160]}"
    proc = subprocess.run(interpreter_for(target) + list(args or []), input=hook_event(case, scratch),
                          capture_output=True, text=True, cwd=str(event_cwd(case, scratch)),
                          env=base_env(scratch, case), timeout=60)
    return hook_decision(proc, event)


def event_cwd(case: dict, scratch: Path) -> Path:
    """The process cwd for a replayed hook: the event's recorded cwd (the session's), else the root."""
    cwd = fill(str((case.get("event") or {}).get("cwd") or ""), scratch)
    return Path(cwd) if cwd and Path(cwd).is_dir() else ROOT


def replay_live(command: str, case: dict, scratch: Path, timeout: float = DEFAULT_TIMEOUT_S,
                event: str = "PreToolUse") -> tuple[str, str]:
    """Exactly what the harness runs: the registered command line, through sh -c, under the entry's
    timeout. A timed-out hook does not block: the harness lets the action proceed."""
    env = base_env(scratch, case, extra=HARNESS_ENV)  # the seals stay last
    try:
        proc = subprocess.run(["sh", "-c", command], input=hook_event(case, scratch), capture_output=True,
                              text=True, cwd=str(event_cwd(case, scratch)), env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "allow", f"timed out after {timeout:g}s; the harness lets the action proceed"
    return hook_decision(proc, event)


def judge(res: Result, kind: str, i: int, case: dict, got: str, why: str, want: str) -> bool:
    label = case.get("from") or case.get("why") or ""
    if got == "error":
        res.fails.append(f"{kind} {i} errored, which is not a decision ({why})")
        return False
    if got != want:
        res.fails.append(f"{kind} {i} expected {want}, enforcer said {got}" + (f" ({label})" if label else ""))
        return False
    if want == "block":
        pattern = case.get("expect_output") if "args" in case else case.get("expect_reason")
        if pattern and not re.search(pattern, why):
            res.fails.append(f"{kind} {i} was refused for another reason: wanted /{pattern}/, got {why[:120]!r}")
            return False
        if case.get("remedy") and not re.search(case["remedy"], why):
            res.fails.append(f"{kind} {i}'s refusal does not name the fix /{case['remedy']}/")
            return False
    return True


# ── a row ──────────────────────────────────────────────────────────────────────
def check_rule(rule: dict, ci: bool, threshold: int, hosts_here: set[str], regs: list[Reg]) -> Result:
    res = Result(str(rule.get("id", "?")), str(rule.get("level", "?")))
    level = rule.get("level")
    if level not in LEVELS:
        res.fails.append(f"level {level!r} is not one of {LEVELS}")
        return res
    if not rule.get("rule"):
        res.fails.append("missing `rule` sentence")
    # The obligation comes from the harness, not from the row (P20 #1298 fresh round 1): when the
    # harness runs this row's enforcer, the row must declare that registration, so it is replayed.
    # Relabelling the row, or deleting its `registered`, cannot turn a dead registration into a pass.
    declared = (rule.get("enforcer") or {}).get("registered") or {}
    for reg in regs:
        if runs_enforcer(rule, reg) and not owns(rule, reg):
            res.fails.append(f"the harness runs {Path(rule['enforcer']['path']).name} on {reg.event} "
                             f"({reg.source.name}, {reg.scope}); this row must declare it "
                             f"(`registered: {{event: {reg.event}, scope: {reg.scope}}}`) so it is replayed")
            break
    if level in ("judgment", "gap") and (declared or any(runs_enforcer(rule, r) for r in regs)):
        res.fails.append(f"a {level} row cannot hold an enforcer the harness runs or a `registered` "
                         "declaration: a registered enforcer is a mechanism row, replayed live")
    if res.fails and (level in ("judgment", "gap") or not declared):
        return res

    if level == "judgment":
        if not rule.get("judgment"):
            res.fails.append("judgment rule must say why no check can decide it (`judgment:`)")
        if len(rule.get("occurrences") or []) >= threshold:
            res.notes.append(f"repeat: {len(rule['occurrences'])} occurrences on a judgment rule; "
                             "move it up the ladder or record why it stays prose")
        return res
    if level == "gap":
        if not rule.get("ticket"):
            res.fails.append("gap rule must name the ticket that closes it (`ticket:`)")
        target = rule.get("target") or {}
        if target.get("level") not in ENFORCING_LEVELS + ["sensor"] or not target.get("mechanism"):
            res.fails.append("gap rule must state `target: {level, mechanism}`: what will enforce it")
        return res

    enforcer = rule.get("enforcer") or {}
    path = enforcer.get("path")
    if not path:
        res.fails.append("mechanism rule has no `enforcer.path`")
        return res
    reg = enforcer.get("registered")
    if level == "hook" and not reg and not rule.get("proof_ref"):
        res.fails.append("a hook row must say where it is registered (`enforcer.registered`)")
        return res
    if reg:
        res.fails.extend(contract_errors(reg))
        if res.fails:
            return res
    unknown = sorted(set(rule.get("hosts") or []) - set(HOST_GROUPS))
    if unknown:
        res.fails.append(f"hosts {unknown} are not declared in the top-level `hosts:`; an unknown group "
                         "would read SKIP everywhere")
        return res
    if host_bound(rule):
        declared = set(rule.get("hosts") or [])
        if not declared:
            res.fails.append("a machine-local or user-scope enforcer must declare the hosts that must have it (`hosts:`)")
            return res
        if not declared & hosts_here:
            res.skipped.append(f"required on {sorted(declared)}; this host ({HOSTNAME}) is not one of them")
            return res
        if ci and (reg or {}).get("scope") == "user":
            res.skipped.append("user-scope row; --ci does not read user settings")
            return res
    target = resolve(path)
    if not target.exists():
        res.fails.append(f"enforcer missing: {path}")
        return res

    proofs, controls = rule.get("proofs") or [], rule.get("controls") or []
    for case in proofs + controls + (rule.get("known_misses") or []):
        if "run" in case:
            res.fails.append("a case may not `run` a command; give `args` and the runner launches the enforcer")
            return res
    if rule.get("proof_test"):
        proc = subprocess.run(fill(rule["proof_test"], Path(tempfile.gettempdir())), capture_output=True,
                              text=True, cwd=str(ROOT), timeout=600)
        if proc.returncode != 0:
            res.fails.append(f"proof_test failed (exit {proc.returncode})")
        else:
            res.notes.append(f"proven by {Path(rule['proof_test'][-1]).name}")
    # The invariant (P20 round 3, STRUCTURAL): a row that says where the harness runs its
    # enforcer is judged by replaying that registration, for every proof and control, before any
    # other evidence counts. A test or a reference elsewhere is additional evidence, never a
    # substitute, so no status but FAIL is reachable while the registered command does not decide.
    if reg and not (proofs and controls):
        res.fails.append("a registered enforcer needs `proofs` and `controls` that the live harness "
                         "replays; a test or a reference elsewhere cannot show the registered command decides")
        return res
    if reg:
        for kind, cases in (("proof", proofs), ("control", controls), ("known miss", rule.get("known_misses") or [])):
            for i, case in enumerate(cases, 1):
                res.fails.extend(f"{kind} {i}: {e}" for e in case_errors(case))
        tools = list(reg.get("tools") or [])
        proof_tools = [(p.get("event") or {}).get("tool_name") for p in proofs]
        for entry in tools:
            if not any(entry_covers(entry, t) for t in proof_tools):
                res.fails.append(f"no proof exercises {entry}, which the contract (`registered.tools`) lists")
        for case in proofs + controls:
            tool = (case.get("event") or {}).get("tool_name")
            if tools and not any(entry_covers(e, tool) for e in tools):
                res.fails.append(f"a case uses {tool}, which the contract (`registered.tools`) does not cover")
                break
    if rule.get("proof_ref") and not proofs:
        res.notes.append(f"proven elsewhere: {rule['proof_ref']}")
        res.external = True
        return res
    if not proofs and not rule.get("proof_test"):
        res.fails.append("mechanism rule has no proof (a replay of a real past mistake it must refuse)")
        return res
    if proofs and not controls:
        res.fails.append("no control: a proof alone cannot tell this enforcer from one that refuses everything")
    for i, case in enumerate(proofs, 1):
        if "args" in case and not case.get("expect_output"):
            res.fails.append(f"proof {i} has no expect_output: a crash would read as a refusal")
        if "args" not in case and not case.get("expect_reason"):
            res.fails.append(f"proof {i} has no expect_reason: a refusal for the wrong reason would pass")
    for m in rule.get("known_misses") or []:
        if not m.get("ticket"):
            res.fails.append("a known miss must name the ticket that will close it")
    if res.fails:
        return res

    scratch = Path(tempfile.mkdtemp(prefix="rules-check-"))
    event = (reg or {}).get("event") or "PreToolUse"
    try:
        if rule.get("applies"):
            proc = subprocess.run(fill(rule["applies"], scratch), capture_output=True, text=True,
                                  cwd=str(ROOT), timeout=600)
            if proc.returncode != 0:
                out = (proc.stdout + proc.stderr).strip().splitlines()
                res.fails.append("the live repo violates it: " + (out[0][:200] if out else f"exit {proc.returncode}"))
        for kind, cases, want in (("proof", proofs, "block"), ("control", controls, "allow")):
            for i, case in enumerate(cases, 1):
                try:
                    run_setup(case, scratch)
                    got, why = replay_in_tree(target, case, scratch, enforcer.get("args"), event)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    res.fails.append(f"{kind} {i} could not run: {exc}")
                    continue
                judge(res, kind, i, case, got, why, want)
        misses = rule.get("known_misses") or []
        for i, case in enumerate(misses, 1):
            try:
                run_setup(case, scratch)
                got, _ = replay_in_tree(target, case, scratch, enforcer.get("args"), event)
            except (subprocess.TimeoutExpired, OSError) as exc:
                res.fails.append(f"known miss {i} could not run: {exc}")
                continue
            if got == "block":
                res.fails.append(f"known miss {i} is now refused ({case.get('from', '')}); move it to `proofs`")
        if misses and not res.fails:
            res.notes.append(f"{len(misses)} known miss(es) still allowed: "
                             + ", ".join(sorted({m['ticket'] for m in misses})))
        if reg:
            live_replay(rule, regs, proofs, controls, scratch, res)
            # The real harness is the oracle for "Claude Code loads and refuses" (continuation review):
            # a registered row needs a fresh, passing canary receipt, or an explicit `canary: {none}`.
            scope = reg.get("scope", "project")
            if REPLAY_ONLY:
                res.notes.append("canary not checked (--replay-only: the replay layer alone)")
            else:
                # The harness merges user settings into every session, so they bind every row's receipt.
                res.fails.extend(_canary.freshness(rule, CANARY_RECEIPT, check_user=not ci, check_harness=not ci))
            if isinstance(rule.get("canary"), dict) and rule["canary"].get("none"):
                res.notes.append(f"not certified on the real harness: {rule['canary']['none']} ({rule['canary'].get('ticket')})")
        if rule.get("proof_ref") and not res.fails:
            res.notes.append(f"also proven elsewhere: {rule['proof_ref']}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return res


SETUP_FORMS = "git init [-q] [-b BRANCH] PATH; mkdir [-p] PATH...; touch PATH..."


def setup_paths(argv: list[str]) -> list[str] | None:
    """The paths an allowed setup command writes, or None when the command is not an allowed form.

    Exact forms only: git takes options that run commands (`-c alias.x=!cmd`) or move its writes
    (`--git-dir`, `-C`), so it is limited to `init` with a quiet flag and a branch name.
    """
    if argv[:2] == ["git", "init"]:
        rest, i = argv[2:], 0
        paths = []
        while i < len(rest):
            if rest[i] == "-q":
                i += 1
            elif rest[i] == "-b" and i + 1 < len(rest) and not rest[i + 1].startswith("-"):
                i += 2
            elif not rest[i].startswith("-") and not paths:
                paths.append(rest[i])
                i += 1
            else:
                return None
        return paths if paths else None
    if argv and argv[0] in ("mkdir", "touch"):
        rest = [a for a in argv[1:] if not (argv[0] == "mkdir" and a == "-p")]
        return None if not rest or any(a.startswith("-") for a in rest) else rest
    return None


def case_errors(case: dict) -> list[str]:
    """A registered row's case may only relocate state into {scratch} and build files there."""
    errs = []
    marker = Path("/__scratch__")

    def contained(value: str) -> bool:
        """The path, with .. resolved, is {scratch} or under it (a relative path starts there)."""
        filled = fill(str(value), marker)
        full = os.path.normpath(filled if filled.startswith("/") else os.path.join(str(marker), filled))
        return full == str(marker) or full.startswith(str(marker) + os.sep)

    for key, value in (case.get("env") or {}).items():
        if key not in CASE_ENV_KEYS:
            errs.append(f"env {key} is outside {sorted(CASE_ENV_KEYS)}; a case may only move state into {{scratch}}")
        elif CASE_ENV_KEYS[key] == "path" and not (str(value).startswith("{scratch}") and contained(value)):
            errs.append(f"env {key} must point into {{scratch}}")
        elif CASE_ENV_KEYS[key] == "name" and "/" in str(value):
            errs.append(f"env {key} is a name, not a path")
    fixtures = "{root}/scripts/rules_fixtures.py"

    def git_owned(arg: str) -> bool:
        """A repository's own directory or a config file (.git, .gitconfig): a setup that writes one
        could plant a command git runs (core.fsmonitor; P20 #1299 r11). Case-folded: the Mac's
        filesystem reads .GIT as .git (P20 #1299 r12). A .gitignore runs nothing."""
        return any(part.casefold() in (".git", ".gitconfig") for part in Path(fill(arg, marker)).parts)

    for name in case.get("files") or {}:
        # A command case's fixture files are written under {scratch} by name (P20 #1299 r12, stratum B).
        name = str(name)
        if name.startswith(("/", "~", "{")) or ".." in Path(name).parts or not contained(name):
            errs.append(f"files {name} must be a relative path inside {{scratch}}")
        elif git_owned(name):
            errs.append(f"files {name} is a path git reads; only `git init` builds one")
        elif data_name_error(name):
            errs.append(f"files {data_name_error(name)}")
    for argv in case.get("setup") or []:
        argv = [str(a) for a in argv]
        if argv[:3] == ["python3", "-I", fixtures]:
            writes = {"write-file": argv[4:5], "fleet-census": argv[4:5], "p9-wait": []}.get(argv[3] if len(argv) > 3 else "")
            if argv[3:4] == ["write-file"] and argv[4:5] and data_name_error(argv[4]):
                errs.append(f"setup rules_fixtures.py write-file {data_name_error(argv[4])}")
            if argv[3:4] == ["p9-wait"] and argv[4:5] != [P9_SCRIPTS]:
                # The fixture imports p9 from this directory, so it is the installed p9, never a
                # directory a case could write (P20 #1299 round 12, stratum A).
                errs.append(f"setup rules_fixtures.py p9-wait must name {P9_SCRIPTS}")
            if writes is None:
                errs.append(f"setup rules_fixtures.py {argv[3:4]} is not a known fixture")
            for arg in writes or []:
                if not (arg.startswith("{scratch}") and contained(arg)):
                    errs.append(f"setup rules_fixtures.py writes {arg}, outside {{scratch}}")
                elif git_owned(arg):
                    errs.append(f"setup rules_fixtures.py writes {arg}, a path git reads; only `git init` builds one")
            continue
        paths = setup_paths(argv)
        if paths is None:
            errs.append(f"setup {argv[:3]} is not one of the allowed forms: {SETUP_FORMS}, or rules_fixtures.py")
            continue
        for arg in paths:
            if arg.startswith("~") or not contained(arg):
                errs.append(f"setup {argv[0]} touches {arg}, outside {{scratch}}")
            elif git_owned(arg):
                errs.append(f"setup {argv[0]} touches {arg}, a path git reads; only `git init` builds one")
            elif argv[0] == "touch" and data_name_error(arg, empty=True):
                errs.append(f"setup touch {data_name_error(arg, empty=True)}")
    return errs


def contract_errors(reg: dict) -> list[str]:
    """`registered` must say which event and, for a per-tool event, which tools the harness
    dispatches to the enforcer. The list is the contract: each tool needs a proof and a registration."""
    errs = []
    if "tool" in reg:
        errs.append("`registered.tool` is now `registered.tools: [...]`, every tool the harness must "
                    "dispatch to this enforcer")
    if not reg.get("event"):
        errs.append("`registered.event` is missing")
    elif reg.get("event") not in PRE_ACTION_EVENTS:
        errs.append(f"{reg.get('event')} runs after the action (or cannot stop it); an enforcer is registered "
                    f"on one of {list(PRE_ACTION_EVENTS)}")
    tools = reg.get("tools")
    if reg.get("event") in TOOL_EVENTS:
        if not isinstance(tools, list) or not tools or not all(isinstance(x, str) and x for x in tools):
            errs.append(f"a {reg.get('event')} enforcer must list its tools (`registered.tools`)")
    elif tools:
        errs.append(f"{reg.get('event')} is not dispatched per tool; drop `registered.tools`")
    if reg.get("scope", "project") not in ("project", "user"):
        errs.append("`registered.scope` is project or user")
    return errs


def combine(outcomes: list[tuple[str, str]]) -> tuple[str, str]:
    """The harness runs every matching hook: any error is no decision, any block blocks."""
    errors = [why for got, why in outcomes if got == "error"]
    if errors:
        return "error", errors[0]
    blocks = [why for got, why in outcomes if got == "block"]
    return ("block", " | ".join(blocks)) if blocks else ("allow", "")


def live_replay(rule: dict, regs: list[Reg], proofs: list, controls: list, scratch: Path,
                res: Result) -> None:
    """Replay every proof and control through every registration of this enforcer the harness
    would dispatch it to, from every settings file it merges (project, local, user, managed)."""
    reg, path = rule["enforcer"]["registered"], rule["enforcer"]["path"]
    owned = [r for r in regs if owns(rule, r)]
    for r in owned:
        res.fails.extend(f"{r.source.name}: {e}" for e in matcher_errors(r.matcher))
    mine = [r for r in owned if not r.inert]
    for r in owned:
        if r.inert:
            res.fails.append(f"a registration in {r.source.name} is inert ({r.inert})")
    if not mine:
        res.fails.append(f"not registered: no {reg['event']} entry in the {reg.get('scope', 'project')} "
                         f"settings runs {path}" + (f" with {rule['enforcer']['args']}" if rule['enforcer'].get('args') else ""))
        return
    for entry in reg.get("tools") or [None]:
        if not any(entry_covers_matcher(r.matcher, entry) for r in mine):
            res.fails.append(f"not registered for {entry}: the harness would not dispatch it to {Path(path).name}")
    before = len(res.fails)
    for kind, cases, want in (("live proof", proofs, "block"), ("live control", controls, "allow")):
        for i, case in enumerate(cases, 1):
            tool = (case.get("event") or {}).get("tool_name")
            dispatched = [r for r in mine if matcher_covers(r.matcher, tool)]
            if not dispatched:
                continue  # reported above, against the contract
            try:
                run_setup(case, scratch)
                got, why = combine([replay_live(r.command, case, scratch, r.timeout, r.event) for r in dispatched])
            except (subprocess.TimeoutExpired, OSError) as exc:
                res.fails.append(f"{kind} {i} could not run: {exc}")
                continue
            judge(res, kind, i, case, got, why, want)
    outside = sorted({s for r in mine if (s := script_of(r.command)) and not under_root(str(script_path(s)))})
    if len(res.fails) > before and outside:
        res.fails.append(f"the harness runs {', '.join(outside)}; a fix on this branch reaches it only "
                         "after merge and pull, and it is a FAIL until then")


def entry_covers_matcher(matcher: str | None, entry: str | None) -> bool:
    """Does a registration's matcher dispatch this contract entry? A pattern entry only by name."""
    if entry is None or is_literal(entry):
        return matcher_covers(matcher, entry)
    return entry in (matcher or "").split("|")


# ── completeness ───────────────────────────────────────────────────────────────
def completeness(data: dict, ci: bool, hosts_here: set[str]) -> Result:
    res = Result("registry-completeness", "test")
    rules = data.get("rules") or []
    gates = {g for r in rules for g in ([r["policy_gate"]] if isinstance(r.get("policy_gate"), str)
                                         else r.get("policy_gate") or [])}
    try:
        policy = yaml.safe_load(governance_file("policy.yaml").read_text())
        hard = policy["gates"]["hard"]
        if not isinstance(hard, list):
            raise TypeError("gates.hard is not a list")
    except (OSError, KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
        res.fails.append(f"cannot read the hard gates in {governance_file('policy.yaml')} ({exc}); "
                         "completeness is unknown")
        hard = []
    for gate in hard:
        if isinstance(gate, dict) and gate.get("pattern") and gate.get("id") not in gates:
            res.fails.append(f"policy gate {gate.get('id')} has a pattern but no row (`policy_gate:`)")
    gap_names = {Path(p).name for r in rules for p in (r.get("covers_hooks") or [])}
    not_rules = [str(k).split() for k in (data.get("hooks_not_rules") or {})]
    regs, errors = harness_registrations(data, ci, hosts_here)
    res.fails += [f"{e}; completeness is unknown" for e in errors]
    # A settings `env` key outside the allowlist may make a hook's shell or interpreter run code first.
    res.fails += [_canary.env_error("the merged settings", k) for k in sorted(HARNESS_ENV)
                  if k not in _canary.SETTINGS_ENV_ALLOWED]
    for reg in regs:
        script, args = invocation(reg.command)
        owners = [r for r in rules if owns(r, reg)]
        if reg.event not in NON_BLOCKING_EVENTS and not script and not reg.inert:
            res.fails.append(f"blocking hook {reg.command[:80]!r} ({reg.event}, {reg.source.name}) cannot be "
                             "parsed into a command, so nothing can tell what it runs; simplify it")
            continue
        if reg.event not in NON_BLOCKING_EVENTS and script and not owners and not reg.inert:
            name = Path(script).name
            named = name in gap_names or any(k[0] == name and (len(k) == 1 or k[1:] == args) for k in not_rules)
            if not named:
                res.fails.append(f"blocking hook {name}{' ' + ' '.join(args) if args else ''} ({reg.event}, "
                                 f"{reg.source.name}) is owned by no row (`registered` with its event and "
                                 "args) and is not in hooks_not_rules or a gap row's covers_hooks")
        if not owners or reg.event not in TOOL_EVENTS:
            continue
        contract = [e for r in owners for e in ((r["enforcer"]["registered"].get("tools")) or [])]
        if reg.matcher in (None, "", "*"):
            res.fails.append(f"{Path(script).name} is registered on every {reg.event} tool; name the tools "
                             "in the matcher so each can be held to a proof")
            continue
        # Each alternative is a literal tool the contract covers, or a pattern the contract lists
        # verbatim: an alternative that merely overlaps one contract tool (`Bash|[A-Z].*`) would
        # dispatch tools nothing proves.
        for alt in reg.matcher.split("|"):
            ok = any(entry_covers(e, alt) for e in contract) if is_literal(alt) else alt in contract
            if not ok:
                res.fails.append(f"{Path(script).name} is registered for {alt} ({reg.event}) but no owning "
                                 "row's contract (`registered.tools`) covers it, so nothing proves it")
    githooks = ROOT / ".githooks"
    names = {Path((r.get("enforcer") or {}).get("path") or "").name for r in rules} | gap_names \
        | {k[0] for k in not_rules}
    for hook in sorted(githooks.iterdir()) if githooks.is_dir() else []:
        if hook.is_file() and os.access(hook, os.X_OK) and hook.name not in names:
            res.fails.append(f"git hook .githooks/{hook.name} has no row and is not in hooks_not_rules")
    return res


# ── ratchet ────────────────────────────────────────────────────────────────────
def fingerprint(case: dict) -> str:
    """A case by content: everything that decides what it proves, nothing that only describes it."""
    return json.dumps({k: v for k, v in case.items() if k not in ("from", "why", "ticket")}, sort_keys=True)


TIGHTENING_KEYS = {"remedy", "expect_reason"}  # added to a case, they only make it stricter


def kept(case: dict, cases: list) -> bool:
    """The case survives in `cases`: unchanged, or only tightened (a remedy or expect_reason added)."""
    drop = ("from", "why", "ticket")
    base = {k: v for k, v in case.items() if k not in drop}
    for other in cases:
        new = {k: v for k, v in other.items() if k not in drop}
        if all(k in new and new[k] == v for k, v in base.items()) and set(new) - set(base) <= TIGHTENING_KEYS:
            return True
    return False


def lowerings(old: dict, new: dict) -> list[str]:
    """How a row's obligations went down between the base and this registry, each a stable string."""
    out = []
    order = {lvl: i for i, lvl in enumerate(LEVELS)}
    if order.get(new.get("level"), 99) > order.get(old.get("level"), 99):
        out.append(f"level {old.get('level')} -> {new.get('level')}")
    o_enf, n_enf = old.get("enforcer") or {}, new.get("enforcer") or {}
    o_reg, n_reg = o_enf.get("registered"), n_enf.get("registered")
    if o_reg and not n_reg:
        out.append("registered removed")
    elif o_reg and n_reg:
        for key, default in (("event", None), ("scope", "project")):
            if o_reg.get(key, default) != n_reg.get(key, default):
                out.append(f"registered.{key} {o_reg.get(key, default)} -> {n_reg.get(key, default)}")
        for tool in sorted(set(o_reg.get("tools") or []) - set(n_reg.get("tools") or [])):
            out.append(f"contract tool {tool} removed")
    if o_enf.get("path"):  # a row that had no enforcer and gains one is promoted, not lowered
        for key in ("path", "args"):
            if (o_enf.get(key) or None) != (n_enf.get(key) or None):
                out.append(f"enforcer.{key} changed")
    if set(new.get("hosts") or []) != set(old.get("hosts") or []) and old.get("hosts") is not None:
        out.append(f"hosts {old.get('hosts')} -> {new.get('hosts')}")
    for key in ("proofs", "controls"):
        for i, case in enumerate(old.get(key) or [], 1):
            if not kept(case, new.get(key) or []):
                out.append(f"{key[:-1]} {i} removed or changed")
    misses = {fingerprint(c) for c in new.get("known_misses") or []}
    fixed = {fingerprint({k: v for k, v in c.items() if k not in ("expect_reason", "remedy")})
             for c in new.get("proofs") or []}
    for i, case in enumerate(old.get("known_misses") or [], 1):
        if fingerprint(case) not in misses and \
                fingerprint({k: v for k, v in case.items() if k != "ticket"}) not in fixed:
            out.append(f"known miss {i} dropped without becoming a proof")
    o_can, n_can = old.get("canary"), new.get("canary")
    if isinstance(o_can, dict) and "none" not in o_can:
        if not isinstance(n_can, dict) or "none" in n_can:
            out.append("canary removed")
        else:
            for key in ("proofs", "controls"):
                for i, case in enumerate(o_can.get(key) or [], 1):
                    if not kept(case, n_can.get(key) or []):
                        out.append(f"canary {key[:-1]} {i} removed or changed")
    for key in ("applies", "proof_test", "policy_gate"):
        if old.get(key) and old.get(key) != new.get(key):
            out.append(f"{key} changed")
    return out


def ratchet(data: dict, base_ref: str, registry: Path) -> Result:
    """Compare this registry with the base branch's: every lowering needs a NEW, exact record.

    Rows declare their own bar, so a change that lowers it together with the hook would pass every
    check of this tree alone. The ratchet compares obligations by content (each proof and control,
    the event, scope, tools, enforcer, hosts, applies, known misses), not by count. A lowering is
    allowed only with a record that is new since the base and names it exactly: the row's
    `demoted: [{what, reason, ticket}]`, the top-level `retired:` for a removed row, or the
    top-level `demotions:` for a change to hosts, user_settings_on, class_threshold,
    hooks_not_rules or covers_hooks. A ref that does not resolve is a FAIL, never "new registry".
    """
    res = Result("registry-ratchet", "test")
    if subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}"],
                      capture_output=True).returncode != 0:
        res.fails.append(f"base ref {base_ref!r} does not resolve; the ratchet cannot run (fetch it)")
        return res
    rel = registry.resolve().relative_to(ROOT.resolve()).as_posix() if registry.is_absolute() else str(registry)
    base = None
    for path in [rel] + [g for g in governance_globs("rules.yaml") if g != rel]:
        proc = subprocess.run(["git", "-C", str(ROOT), "show", f"{base_ref}:{path}"], capture_output=True, text=True)
        if proc.returncode == 0:
            base = yaml.safe_load(proc.stdout) or {}
            break
    if base is None:
        res.notes.append(f"{base_ref} has no registry; nothing to ratchet against (a new registry)")
        return res

    def fresh(entries: list, old_entries: list) -> list:
        old = {json.dumps(e, sort_keys=True) for e in old_entries or []}
        return [e for e in entries or [] if json.dumps(e, sort_keys=True) not in old
                and e.get("reason") and e.get("ticket")]

    rows = {r.get("id"): r for r in data.get("rules") or []}
    base_rows = {r.get("id"): r for r in base.get("rules") or []}
    retired = {e.get("id"): e for e in fresh(data.get("retired"), base.get("retired"))}
    for rid, old in base_rows.items():
        new = rows.get(rid)
        if new is None:
            if rid not in retired:
                res.fails.append(f"row {rid} was removed; record it in the top-level `retired:` (id, reason, ticket)")
                continue
            # A retired row replaced by a renamed copy is compared with that copy, so a rename cannot
            # launder a lowering.
            key = ((old.get("enforcer") or {}).get("path"), (old.get("enforcer") or {}).get("args"), old.get("policy_gate"))
            new = next((r for r in rows.values() if r.get("id") not in base_rows and key[0] and
                        ((r.get("enforcer") or {}).get("path"), (r.get("enforcer") or {}).get("args"),
                         r.get("policy_gate")) == key), None)
            if new is None:
                continue
        recorded = {e.get("what") for e in fresh(new.get("demoted"), old.get("demoted"))}
        for change in lowerings(old, new):
            if change not in recorded:
                res.fails.append(f"{rid}: {change}; record exactly {change!r} in the row's `demoted:` "
                                 "(what, reason, ticket), or restore it")
    waived = {e.get("what") for e in fresh(data.get("demotions"), base.get("demotions"))}
    changes = []
    for key in ("hosts", "user_settings_on"):
        if base.get(key) is not None and base.get(key) != data.get(key):
            changes.append(key)
    if class_threshold(data) > class_threshold(base):
        changes.append("class_threshold")
    if set(data.get("hooks_not_rules") or {}) - set(base.get("hooks_not_rules") or {}):
        changes.append("hooks_not_rules")
    covers = lambda d: {p for r in d.get("rules") or [] for p in (r.get("covers_hooks") or [])}  # noqa: E731
    if covers(data) - covers(base):
        changes.append("covers_hooks")
    for key in changes:
        if key not in waived:
            res.fails.append(f"top-level {key} widened or changed; record it in `demotions:` "
                             f"({{what: {key}, reason, ticket}})")
    return res


# ── main ───────────────────────────────────────────────────────────────────────
def load(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("rules_check: PyYAML is not importable; install it (pip install pyyaml)")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise SystemExit(f"rules_check: {path} must be a mapping with a `rules:` list")
    ids = [r.get("id") for r in data["rules"]]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise SystemExit(f"rules_check: duplicate rule ids: {', '.join(map(str, dupes))}")
    return data


def class_threshold(data: dict) -> int:
    """The registry's `class_threshold`: the one reader the registry checks and P16's
    rule-of-three gate share (P20 #1303 STRUCTURAL; two regex readers had misread valid YAML).
    Absent is CLASS_THRESHOLD; anything but a positive integer stops the check."""
    value = data.get("class_threshold", CLASS_THRESHOLD)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SystemExit(f"rules_check: class_threshold must be a positive integer, not {value!r}")
    return value


def markdown(rules: list[dict]) -> str:
    lines = ["| Rule | Level | Enforcer | Proof |", "|---|---|---|---|"]
    order = {lvl: i for i, lvl in enumerate(LEVELS)}
    for r in sorted(rules, key=lambda r: (order.get(r.get("level"), 99), r.get("id", ""))):
        enf = (r.get("enforcer") or {}).get("path") or (r.get("ticket") and f"gap: {r['ticket']}") or "—"
        proof = (f"{len(r.get('proofs') or [])} replay / {len(r.get('controls') or [])} control"
                 if r.get("proofs") else (r.get("proof_ref") or ("judgment" if r.get("level") == "judgment" else "—")))
        lines.append(f"| `{r.get('id')}`: {r.get('rule', '').replace('|', '/')} | {r.get('level')} | `{enf}` | {proof} |")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ci", action="store_true", help="skip the user-settings scan and user-scope rows")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--registry", default=str(REGISTRY))
    ap.add_argument("--base", help="git ref whose registry this one may not silently lower (CI: the PR base)")
    ap.add_argument("--replay-only", action="store_true",
                    help="judge the replay layer alone: skip canary receipts (each row says so). The registry "
                         "mutation test uses it, so a mutation is caught by behaviour, not by a stale receipt")
    args = ap.parse_args(argv)

    data = load(Path(args.registry))
    threshold = class_threshold(data)
    HOST_GROUPS.clear()
    HOST_GROUPS.update(data.get("hosts") or {})
    hosts_here = host_names(data)
    rules = [r for r in data["rules"] if not args.only or r.get("id") in args.only]
    if args.only and len(rules) != len(set(args.only)):
        missing = set(args.only) - {r.get("id") for r in rules}
        print(f"rules_check: unknown rule id(s): {', '.join(sorted(missing))}", file=sys.stderr)
        return 2
    if not rules:
        print("rules_check: the registry has no rules; refusing to report a pass over nothing", file=sys.stderr)
        return 1
    if args.markdown:
        print(markdown(rules))
        return 0

    regs, _errors = harness_registrations(data, args.ci, hosts_here)  # completeness reports _errors
    global CANARY_RECEIPT, REPLAY_ONLY
    CANARY_RECEIPT = _canary.load_receipt()
    REPLAY_ONLY = args.replay_only
    results = [check_rule(r, args.ci, threshold, hosts_here, regs) for r in rules]
    if not args.only:
        results.append(completeness(data, args.ci, hosts_here))
        if args.base:
            results.append(ratchet(data, args.base, Path(args.registry)))
    if args.json:
        print(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        width = max(len(r.rule_id) for r in results)
        for r in results:
            print(f"  {r.status:<8} {r.level:<12} {r.rule_id:<{width}}  {r.detail()}")
        counts: dict[str, int] = {}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1
        uncertified = sum(1 for r in results if any(n.startswith("not certified on the real harness") for n in r.notes))
        proven = sum(1 for r in results if r.status == "PASS" and r.level in ENFORCING_LEVELS
                     and r.rule_id != "registry-completeness"
                     and not any(n.startswith("not certified on the real harness") for n in r.notes))
        print(f"\n  {len(rules)} rules on {HOSTNAME} (hosts: {', '.join(sorted(hosts_here)) or 'none declared'}): "
              f"{proven} enforced and proven here, {uncertified} replayed but not certified on the real harness, "
              + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
