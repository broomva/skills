"""Arms: which context injections a trial gets, as an explicit ``--settings`` file.

THE RULE EVERY ARM FOLLOWS: STATE IS CONSTANT, ONLY THE INJECTION VARIES
------------------------------------------------------------------------
Every case, whatever its arm, has the same files on disk: the knowledge graph and
catalog in the workspace, the memory directory under ``~/.claude/projects``, the
ctx store under ``~/.local/state/ctx``, the stubs and the delete gate. An arm
changes only what is PUSHED into the model's context:

* ``memory``   the CLI's auto-memory, which loads ``MEMORY.md`` into the system
               prompt (``autoMemoryEnabled``). Off, the files are still there to
               be found; nothing points at them.
* ``rolex``    role-x's UserPromptSubmit intake hook, the real script from this
               branch, reading the workspace's ``roles/`` and catalog.
* ``ctx``      ctx-core's SessionStart hook, the real script, briefing from the
               fixture ctx store.
* ``rolex_coverage``  role-x's SessionStart coverage nudge (``all`` only).

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

#: Markers a hook's output must carry for the arm to count as delivered.
ROLEX_MARKER = "[role-x intake"
CTX_MARKER = "Shared board facts"


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
        return tuple(out)

    @property
    def is_bare(self) -> bool:
        return not (self.memory or self.rolex or self.ctx or self.rolex_coverage)


ARM_REGISTRY: dict[str, Arm] = {
    "bare": Arm("bare", description="no injections"),
    "memory": Arm("memory", memory=True, description="auto-memory: MEMORY.md in the system prompt"),
    "rolex": Arm("rolex", rolex=True, description="role-x UserPromptSubmit intake, default top-5"),
    "ctx": Arm("ctx", ctx=True, description="ctx-core SessionStart board brief"),
    "all": Arm("all", memory=True, rolex=True, ctx=True, rolex_coverage=True,
               description="memory + role-x intake + ctx brief + role-x coverage"),
    "rolex-top2": Arm("rolex-top2", rolex=True, rolex_top_n=2,
                      description="role-x intake with the task-entity list cut to 2"),
}

DEFAULT_ARMS = ("bare", "memory", "rolex", "ctx", "all", "rolex-top2")

_TOPN_RE = re.compile(r"^rolex-top(\d{1,2})$")


def parse_arm(spec: str) -> Arm:
    """An arm id from the registry, or ``rolex-top<N>`` for any N in 0..50."""
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


def hook_commands(arm: Arm, case_root: Path, rt: HookRuntime) -> dict[str, list[dict[str, Any]]]:
    """The ``hooks`` object for *arm*. The delete gate is in every arm."""
    case = {"CTXABL_CASE_ROOT": str(case_root)}
    hooks: dict[str, list[dict[str, Any]]] = {
        "PreToolUse": [{
            "matcher": "Bash",
            "hooks": [{"type": "command", "timeout": 10,
                       "command": _cmd(case, [rt.python, "-I", str(STUBS_DIR / "delete_gate.py")])}],
        }],
    }
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
        hooks["SessionStart"] = [{"hooks": session_start}]
    if arm.rolex:
        env = dict(rolex_env)
        if arm.rolex_top_n is not None:
            env["ROLE_X_TASK_ENTITY_TOP_N"] = str(arm.rolex_top_n)
        hooks["UserPromptSubmit"] = [{"hooks": [{"type": "command", "timeout": 20, "command": _cmd(
            env, ["/bin/bash", str(ROLEX_SCRIPTS / "role-x-intake-hook.sh")])}]}]
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
    "HookRuntime",
    "ROLEX_MARKER",
    "build_settings",
    "hook_commands",
    "parse_arm",
]
