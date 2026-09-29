"""Shared fixtures: a scratch HOME with three real git repos and a scopes.yaml.

    broomva   main checkout (branch main) + a worktree on feat/x   -> scope broomva
    sri       its own repo (branch main)                           -> scope sri
    other     a repo with no scope                                 -> no-op

Hooks run as the owner registers them: `/bin/sh ctx-hook.sh <event>` with
CTX_PYTHON set and the hook JSON on stdin, in a subprocess, timed. The wrapper
execs `python3 -I -S ctx_hook.py`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
HOOK = SCRIPTS / "ctx_hook.py"
WRAPPER = SCRIPTS / "ctx-hook.sh"
CTX = SCRIPTS / "ctx.py"
sys.path.insert(0, str(SCRIPTS))  # so every test module can `import ctx`

#: The deadline every hook invocation must meet, start to exit, measured from
#: outside the process.
HOOK_WALL_S = 0.200
#: Behaviour tests give the hook a generous budget, so a loaded test machine
#: cannot turn "what does the hook publish" into a timing test. The `timed`
#: fixture restores the real 80 ms for the tests that are about time.
BEHAVIOUR_BUDGET_MS = "5000"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   cwd=str(cwd), check=True, capture_output=True)


@dataclass
class HookRun:
    rc: int
    stdout: str
    stderr: str
    elapsed: float

    @property
    def context(self) -> Optional[str]:
        if not self.stdout:
            return None
        return json.loads(self.stdout)["hookSpecificOutput"]["additionalContext"]


@dataclass
class World:
    home: Path
    broomva: Path
    worktree: Path
    sri: Path
    other: Path
    budget_ms: Optional[str] = BEHAVIOUR_BUDGET_MS

    def store(self, scope: str) -> Path:
        return self.home / ".local" / "state" / "ctx" / scope

    def events(self, scope: str) -> List[Dict]:
        log = self.store(scope) / "events.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]

    def board(self, scope: str) -> Dict:
        return json.loads((self.store(scope) / "board.json").read_text())

    def hook(self, event: str, payload: Dict, env: Optional[Dict[str, str]] = None,
             script: Optional[Path] = None, raw: Optional[str] = None) -> HookRun:
        """Through the wrapper, as registered; or, with `script`, a ctx_hook.py
        run directly (the fail-open tests pair a copy with a broken ctx.py)."""
        full_env = dict(os.environ)
        full_env.pop("CTX_HOOK_BUDGET_MS", None)
        if self.budget_ms:
            full_env["CTX_HOOK_BUDGET_MS"] = self.budget_ms
        full_env["CTX_PYTHON"] = sys.executable
        full_env.update(env or {})
        data = raw if raw is not None else json.dumps(payload)
        cmd = (["/bin/sh", str(WRAPPER), event] if script is None
               else [sys.executable, "-I", "-S", str(script), event])
        t0 = time.monotonic()
        proc = subprocess.run(cmd, input=data.encode(), capture_output=True, env=full_env, timeout=30)
        return HookRun(proc.returncode, proc.stdout.decode(), proc.stderr.decode(), time.monotonic() - t0)

    def start(self, sid: str, cwd: Path, **env: str) -> HookRun:
        return self.hook("session-start", {"session_id": sid, "cwd": str(cwd),
                                           "hook_event_name": "SessionStart", "source": "startup"}, env)

    def stop(self, sid: str, cwd: Path, message: str = "done", **env: str) -> HookRun:
        return self.hook("stop", {"session_id": sid, "cwd": str(cwd), "hook_event_name": "Stop",
                                  "stop_hook_active": False, "last_assistant_message": message}, env)

    def died(self, sid: str, cwd: Path, error: str = "rate_limit") -> HookRun:
        # The shape Claude Code 2.1.280 sends: the class in `error`, free text in
        # `error_details` and `last_assistant_message` (neither is stored).
        return self.hook("stop-failure", {"session_id": sid, "cwd": str(cwd),
                                          "hook_event_name": "StopFailure", "error": error,
                                          "error_details": "429 Too Many Requests: resets at 5pm",
                                          "last_assistant_message": "partial answer text"})

    def cli(self, *args: str, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(CTX), *args], cwd=str(cwd),
                              capture_output=True, text=True, timeout=60)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in ("PASEO_AGENT_ID", "FLEET_ROLE", "CLAUDE_CONFIG_DIR", "GIT_DIR", "GIT_WORK_TREE"):
        monkeypatch.delenv(var, raising=False)

    broomva, sri, other = home / "broomva", home / "broomva" / "work" / "sri", home / "other"
    for repo in (broomva, sri, other):
        repo.mkdir(parents=True, exist_ok=True)
        _git("init", "-q", "-b", "main", cwd=repo)
        _git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    # sri is nested inside broomva's tree, as on the owner's machine, and is still
    # its own repo with its own common dir.
    (broomva / ".gitignore").write_text("work/\n")
    worktree = home / "wt" / "feat-x"
    worktree.parent.mkdir()
    _git("worktree", "add", "-q", "-b", "feat/x", str(worktree), cwd=broomva)

    cfg = home / ".config" / "ctx"
    cfg.mkdir(parents=True)
    (cfg / "scopes.yaml").write_text(
        "version: 1\n"
        "scopes:\n"
        "  broomva:\n"
        "    - ~/broomva        # the main checkout; worktrees resolve here too\n"
        "  sri:\n"
        "    - ~/broomva/work/sri/.git\n"
    )
    real = lambda p: Path(os.path.realpath(p))
    return World(home=home, broomva=real(broomva), worktree=real(worktree), sri=real(sri), other=real(other))


@pytest.fixture
def timed(world: World) -> World:
    """The world with the hooks' real deadline, for tests that are about time."""
    world.budget_ms = None
    return world
