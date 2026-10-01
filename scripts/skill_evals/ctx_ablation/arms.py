"""Arms: which context injections a trial gets, as an explicit ``--settings`` file.

THE RULE EVERY ARM FOLLOWS: STATE IS CONSTANT, ONLY THE INJECTION VARIES
------------------------------------------------------------------------
Every case, whatever its arm, has the same files on disk: the knowledge graph and
catalog in the workspace, the memory directory under ``~/.claude/projects``, the
ctx store under ``~/.local/state/ctx``, the stubs and the case guard. An arm
changes only what is PUSHED into the model's context:

* ``memory``   the CLI's auto-memory, which loads ``MEMORY.md`` into the system
               prompt (``autoMemoryEnabled``). Off, the files are still there to
               be found; nothing points at them.
* ``rolex``    role-x's UserPromptSubmit intake hook, the real script from this
               branch, reading the workspace's ``roles/`` and catalog.
* ``reflex``   the same hook with ``ROLE_X_OUTPUT=reflex``: role-x's reflex router,
               at most three factual lines chosen from git and board state and the
               prompt, no persona lines, no entity list (BRO-2674; ``rolex-reflex``
               is an alias).
* ``qbar``     the same hook with ``ROLE_X_OUTPUT=qbar``: the lens block cut to its
               quality bar, #251's recommended arm (``rolex-qbar`` is an alias).
* ``ctx``      ctx-core's SessionStart hook, the real script, briefing from the
               fixture ctx store.
* ``s1``       ctx-core's System 1 gate (ctx_s1.py), one registration per stage it
               names, each through the real wrapper, with the E3-tuned candidate
               floors (``references/s1-params.candidate.json``: the shipped params
               abstain everywhere, so an arm on them would be bare). Its cache is
               built in EVERY arm by the fixture (state constant); only the hooks
               differ.
* ``rolex_coverage``  role-x's SessionStart coverage nudge (``all`` only). It reads
               the last 7 days of intake events, and a fresh jail has one, so it is
               silent in every trial: registered for fidelity, it injects nothing.

That is the counterfactual the question asks about: "what if this were not
injected", not "what if the knowledge did not exist". A bare arm that also deleted
the knowledge graph would measure the graph, and every lift would be inflated by
everything a bare session could have found by looking.

Nothing here reads or writes ``~/.claude/settings.json``. The CLI runs with
``--setting-sources project`` (the fixture workspace has no project settings) plus
``--settings <this arm's file>``, under a jailed ``HOME``, so the operator's user
settings, hooks and plugins are not loaded in any arm.

What is deliberately NOT an arm, and is identical (absent) in all of them: the
workspace ``CLAUDE.md``, installed skills and plugins, and the four other
production SessionStart hooks (skill freshness, git identity, auth preflight,
skill-source sync). Those four live in the workspace repo, only speak when
something is wrong, and two of them probe the network. See the README.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Repo layout: <repo>/scripts/skill_evals/ctx_ablation/arms.py
REPO_ROOT = Path(__file__).resolve().parents[3]
STUBS_DIR = Path(__file__).resolve().parent / "stubs"
ROLEX_SCRIPTS = REPO_ROOT / "skills" / "orchestration" / "role-x" / "scripts"
CTX_SCRIPTS = REPO_ROOT / "skills" / "orchestration" / "ctx-core" / "scripts"

#: The production ctx hook budget is 80 ms inside the interpreter, and a hook that
#: misses it injects nothing. Under a parallel eval that miss would be noise in the
#: ctx arm, so the harness gives it this much. The brief it renders is the same.
CTX_HOOK_BUDGET_MS = 1500

#: Every tool the case guard sees. Reads are in it: a bare trial reading the real
#: memory directory by absolute path would contaminate the control.
GUARD_MATCHER = "Bash|Write|Edit|MultiEdit|NotebookEdit|Read|NotebookRead|Grep|Glob"
GUARDED_TOOLS = frozenset(GUARD_MATCHER.split("|"))

#: Markers a hook's output must carry for the arm to count as delivered.
ROLEX_MARKER = "[role-x intake"
#: The reflex router's block. It may legitimately print nothing (no reflex
#: applies), so its delivery proof is the live hook's log row, not this marker.
ROLEX_REFLEX_MARKER = "[bstack reflexes"
CTX_MARKER = "Shared board facts"
S1_MARKER = "[ctx claims]"

def _ctx_s1():
    import sys

    if str(CTX_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(CTX_SCRIPTS))
    import ctx_s1

    return ctx_s1


def _s1_stages() -> dict[str, tuple[str, str | None]]:
    """The System 1 stages an arm can turn on, with the hook event and matcher
    each registers on, read from ctx-core's one stage table (ctx_s1.STAGES).
    compact needs a compaction, which a short trial never reaches, and
    post-compact only measures."""
    return {st: (cfg["event"], cfg.get("matcher")) for st, cfg in _ctx_s1().STAGES.items()
            if st not in ("compact", "post-compact")}


S1_EVENTS = _s1_stages()
S1_ALL = tuple(S1_EVENTS)
S1_PARAMS = CTX_SCRIPTS.parent / "references" / "s1-params.candidate.json"


def _floored(path: Path) -> set[str]:
    try:
        stages = json.loads(path.read_text(encoding="utf-8")).get("stages") or {}
    except (OSError, ValueError):
        return set()
    return {st for st, cfg in stages.items() if isinstance(cfg, dict) and cfg.get("floor") is not None}


#: One-stage arms only for stages that can inject alone (subagent, like
#: compact, only re-offers claims another stage injected) AND that the
#: proposal floors give a floor: any other one-stage arm would be `bare`.
S1_ALONE = tuple(st for st in S1_ALL if st in _ctx_s1().ALONE_STAGES and st in _floored(S1_PARAMS))
#: As for the ctx hook: a generous in-process deadline, so a loaded eval machine
#: does not turn a stage into a timeout. The decision it makes is the same.
S1_HOOK_BUDGET_MS = 1500


@dataclass(frozen=True)
class Arm:
    id: str
    memory: bool = False
    rolex: bool = False
    ctx: bool = False
    rolex_coverage: bool = False
    #: ``None`` leaves role-x at its default cap (5); an int sets
    #: ``ROLE_X_TASK_ENTITY_TOP_N`` for the intake hook.
    rolex_top_n: int | None = None
    #: ``None`` leaves role-x's output at its default (the hook command is
    #: unchanged); a string sets ``ROLE_X_OUTPUT`` ("reflex", "qbar").
    rolex_output: str | None = None
    #: System 1 stages this arm registers (empty: none).
    s1_stages: tuple[str, ...] = ()
    description: str = ""

    @property
    def injections(self) -> tuple[str, ...]:
        """The injections this arm must be SEEN to deliver, per trial."""
        out = []
        if self.memory:
            out.append("memory")
        if self.rolex:
            out.append("rolex")
        if self.ctx:
            out.append("ctx")
        if self.s1_stages:
            out.append("s1")
        return tuple(out)

    @property
    def is_reflex(self) -> bool:
        return self.rolex and self.rolex_output == "reflex"

    @property
    def is_bare(self) -> bool:
        return not (self.memory or self.rolex or self.ctx or self.rolex_coverage or self.s1_stages)


ARM_REGISTRY: dict[str, Arm] = {
    "bare": Arm("bare", description="no injections"),
    "memory": Arm("memory", memory=True, description="auto-memory: MEMORY.md in the system prompt"),
    "rolex": Arm("rolex", rolex=True, description="role-x UserPromptSubmit intake, default top-5"),
    "ctx": Arm("ctx", ctx=True, description="ctx-core SessionStart board brief"),
    "all": Arm("all", memory=True, rolex=True, ctx=True, rolex_coverage=True,
               description="memory + role-x intake + ctx brief + role-x coverage"),
    "rolex-top2": Arm("rolex-top2", rolex=True, rolex_top_n=2,
                      description="role-x intake with the task-entity list cut to 2"),
    "reflex": Arm("reflex", rolex=True, rolex_output="reflex",
                  description="role-x reflex router (ROLE_X_OUTPUT=reflex)"),
    "qbar": Arm("qbar", rolex=True, rolex_output="qbar",
                description="role-x intake cut to its quality bar (ROLE_X_OUTPUT=qbar)"),
    "s1": Arm("s1", s1_stages=S1_ALL, description="ctx System 1 gate, every stage"),
    "ctx+s1": Arm("ctx+s1", ctx=True, s1_stages=S1_ALL,
                  description="ctx brief plus the System 1 gate (the coordination regression guard)"),
    **{"s1-" + st: Arm("s1-" + st, s1_stages=(st,), description="ctx System 1 gate, %s stage alone" % st)
       for st in S1_ALONE},
}
S1_ARMS = ("bare", "s1") + tuple("s1-" + st for st in S1_ALONE)

#: Other names for registry arms: the owner's brief called them rolex-reflex and
#: rolex-qbar; the design of record (workspace spec, §5.4) calls them reflex and qbar.
ARM_ALIASES = {"rolex-reflex": "reflex", "rolex-qbar": "qbar"}

DEFAULT_ARMS = ("bare", "memory", "rolex", "ctx", "all", "rolex-top2")

_TOPN_RE = re.compile(r"^rolex-top(\d{1,2})$")


def parse_arm(spec: str) -> Arm:
    """An arm id from the registry, or ``rolex-top<N>`` for any N in 0..50."""
    spec = ARM_ALIASES.get(spec, spec)
    if spec in ARM_REGISTRY:
        return ARM_REGISTRY[spec]
    m = _TOPN_RE.match(spec)
    if m and 0 <= int(m.group(1)) <= 50:
        n = int(m.group(1))
        return Arm(spec, rolex=True, rolex_top_n=n,
                   description=f"role-x intake with the task-entity list cut to {n}")
    raise ValueError(f"unknown arm {spec!r}; known: {sorted(ARM_REGISTRY)} or rolex-top<N>")


def _cmd(env: dict[str, str], argv: list[str]) -> str:
    return " ".join([f"{k}={shlex.quote(v)}" for k, v in env.items()] + [shlex.quote(a) for a in argv])


@dataclass(frozen=True)
class HookRuntime:
    """How the hooks are launched. Resolved once per run by :func:`resolve_runtime`."""

    #: The interpreter every hook and stub runs under.
    python: str
    #: role-x needs PyYAML, which on this machine lives in the USER site. The jail
    #: moves HOME, so ``site.getusersitepackages()`` would point into the jail and
    #: the hook would exit 0 having injected NOTHING — the role-x arm would silently
    #: be the bare arm. PYTHONUSERBASE puts it back; ``preflight`` proves it worked.
    pythonuserbase: str = ""
    #: The operator's real home. The case guard blocks any command or file tool that
    #: names a path under it.
    real_home: str = ""


def hook_commands(arm: Arm, case_root: Path, rt: HookRuntime) -> dict[str, list[dict[str, Any]]]:
    """The ``hooks`` object for *arm*. The case guard is in every arm."""
    case = {"CTXABL_CASE_ROOT": str(case_root)}
    if rt.real_home:
        case["CTXABL_REAL_HOME"] = rt.real_home
    hooks: dict[str, list[dict[str, Any]]] = {
        "PreToolUse": [{
            "matcher": GUARD_MATCHER,
            "hooks": [{"type": "command", "timeout": 10,
                       "command": _cmd(case, [rt.python, "-I", str(STUBS_DIR / "guard.py")])}],
        }],
    }
    for st in arm.s1_stages:
        event, matcher = S1_EVENTS[st]
        group: dict[str, Any] = {"hooks": [{"type": "command", "timeout": 10, "command": _cmd(
            {"CTX_S1": "1", "CTX_S1_STAGES": st, "CTX_S1_PARAMS": str(S1_PARAMS),
             "CTX_S1_BUDGET_MS": str(S1_HOOK_BUDGET_MS), "CTX_PYTHON": rt.python},
            ["/bin/sh", str(CTX_SCRIPTS / "ctx-s1-hook.sh"), st])}]}
        if matcher:
            group = {"matcher": matcher, **group}
        hooks.setdefault(event, []).append(group)
    rolex_env = {"ROLE_X_PYTHON": rt.python}
    if rt.pythonuserbase:
        rolex_env["PYTHONUSERBASE"] = rt.pythonuserbase
    session_start = []
    if arm.ctx:
        session_start.append({"type": "command", "timeout": 10, "command": _cmd(
            {"CTX_PYTHON": rt.python, "CTX_HOOK_BUDGET_MS": str(CTX_HOOK_BUDGET_MS)},
            ["/bin/sh", str(CTX_SCRIPTS / "ctx-hook.sh"), "session-start"])})
    if arm.rolex_coverage:
        session_start.append({"type": "command", "timeout": 10, "command": _cmd(
            rolex_env, ["/bin/bash", str(ROLEX_SCRIPTS / "role-x-coverage-hook.sh")])})
    if session_start:
        hooks.setdefault("SessionStart", []).insert(0, {"hooks": session_start})
    if arm.rolex:
        env = dict(rolex_env)
        if arm.rolex_top_n is not None:
            env["ROLE_X_TASK_ENTITY_TOP_N"] = str(arm.rolex_top_n)
        if arm.rolex_output is not None:
            env["ROLE_X_OUTPUT"] = arm.rolex_output
        hooks.setdefault("UserPromptSubmit", []).insert(0, {"hooks": [{"type": "command", "timeout": 20,
                                                                    "command": _cmd(
            env, ["/bin/bash", str(ROLEX_SCRIPTS / "role-x-intake-hook.sh")])}]})
    return hooks


def build_settings(arm: Arm, case_root: Path, rt: HookRuntime) -> dict[str, Any]:
    """The complete ``--settings`` document for one trial of *arm*."""
    return {
        # Explicit in BOTH directions. Relying on the CLI default for "on" would make
        # the memory arm depend on a default the CLI may change.
        "autoMemoryEnabled": arm.memory,
        "hooks": hook_commands(arm, case_root, rt),
    }


__all__ = [
    "ARM_REGISTRY",
    "Arm",
    "CTX_MARKER",
    "DEFAULT_ARMS",
    "S1_ALL",
    "S1_ARMS",
    "S1_EVENTS",
    "S1_MARKER",
    "HookRuntime",
    "ROLEX_MARKER",
    "ROLEX_REFLEX_MARKER",
    "build_settings",
    "hook_commands",
    "parse_arm",
]
