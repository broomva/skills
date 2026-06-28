#!/usr/bin/env python3
"""persist.py — bstack P12 Persistent Loop Discipline.

Cross-context restart loop: state persists in the filesystem, the agent's
context window is restarted fresh each iteration. Closes the failure mode
where long-horizon agentic work degrades silently as the conversation
context window rots past 100K tokens (the "Dumb Zone").

The defining moves are:

  1. The agent writes a goal + state snapshot to PROMPT.md
  2. A bash loop spawns fresh agent contexts: `while :; do claude -p "$(cat PROMPT.md)"; done`
  3. State persists in the filesystem (PROMPT.md + git tree + STATE.json)
  4. Validation backpressure comes from compilers/tests/linters, NOT model self-grading
  5. Loop exits when success_condition fires OR budget exhausted OR user interrupts

The pattern was popularized by Geoffrey Huntley as "Ralph loop" but the bstack
P12 primitive deliberately uses a non-anthropomorphized name. Skill repo:
github.com/broomva/persist. Spec: workspace AGENTS.md §P12.

This script is the substrate; the discipline lives in AGENTS.md (the agent's
reasoning enforces when to spawn a persist loop, not just how).

CLI:
  persist iterate <prompt-file>   Spawn a fresh-context loop driven by the prompt
  persist status                  Show open loop state at ~/.config/broomva/persist/state.jsonl
  persist abandon <loop-id>       Mark a loop ABANDONED (terminal); frees concurrency slot
  persist doctor                  Health-check (gh, git, prompt file, state dir)
  persist conformance             Run the test battery
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as _dt
import enum
import errno
import fcntl
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# ── Exit codes ──────────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_POLICY_ERROR = 2
EXIT_USAGE = 3
EXIT_EXTERNAL_ERROR = 4
EXIT_BUDGET_EXHAUSTED = 5
EXIT_INVARIANT_VIOLATION = 99


# ── Paths ───────────────────────────────────────────────────────────────────
def persist_home() -> Path:
    override = os.environ.get("BROOMVA_PERSIST_HOME")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "broomva" / "persist"


def state_jsonl() -> Path:
    return persist_home() / "state.jsonl"


def state_lock_path() -> Path:
    return persist_home() / "state.lock"


# ── Errors ──────────────────────────────────────────────────────────────────
class PersistError(Exception):
    code = EXIT_DEGRADED


class IllegalTransitionError(PersistError):
    code = EXIT_INVARIANT_VIOLATION


class BudgetExhaustedError(PersistError):
    code = EXIT_BUDGET_EXHAUSTED


# ── State machine ──────────────────────────────────────────────────────────
class LoopState(str, enum.Enum):
    SPAWNED = "SPAWNED"      # loop registered, prompt file detected
    ITERATING = "ITERATING"  # currently running an iteration
    PAUSED = "PAUSED"        # waiting for external input (CI, human review)
    SUCCESS = "SUCCESS"      # success condition met (terminal)
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"  # max_iterations or wall-clock exceeded (terminal)
    ABANDONED = "ABANDONED"  # manually abandoned (terminal)


_TRANSITIONS: set[tuple[LoopState, LoopState]] = {
    (LoopState.SPAWNED, LoopState.ITERATING),
    (LoopState.ITERATING, LoopState.ITERATING),  # iteration N → iteration N+1
    (LoopState.ITERATING, LoopState.PAUSED),
    (LoopState.ITERATING, LoopState.SUCCESS),
    (LoopState.ITERATING, LoopState.BUDGET_EXHAUSTED),
    (LoopState.PAUSED, LoopState.ITERATING),
    (LoopState.PAUSED, LoopState.ABANDONED),
    (LoopState.SPAWNED, LoopState.ABANDONED),
    (LoopState.ITERATING, LoopState.ABANDONED),
}


def assert_legal_transition(curr: LoopState, nxt: LoopState) -> None:
    if (curr, nxt) not in _TRANSITIONS and curr != nxt:
        raise IllegalTransitionError(
            f"Illegal loop state transition: {curr.value} → {nxt.value}"
        )


def is_terminal(state: LoopState) -> bool:
    return state in {LoopState.SUCCESS, LoopState.BUDGET_EXHAUSTED, LoopState.ABANDONED}


# ── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class LoopEvent:
    """One row of state.jsonl."""
    ts: str
    loop_id: str
    prompt_file: str
    iteration: int
    from_state: str
    to_state: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_jsonl(self) -> str:
        return json.dumps(dataclasses.asdict(self), separators=(",", ":"))


@dataclass(frozen=True)
class LoopBudget:
    max_iterations: int = 50
    max_wall_clock_s: int = 14400  # 4h default — matches METR's 80%-horizon ceiling


# ── File helpers ────────────────────────────────────────────────────────────
@contextlib.contextmanager
def file_lock(lock_path: Path, timeout_s: float = 30.0) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                if time.monotonic() >= deadline:
                    raise PersistError(
                        f"flock timeout after {timeout_s}s on {lock_path}"
                    ) from e
                time.sleep(0.05)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def jsonl_append(path: Path, payload: str, lock: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(lock):
        with path.open("a", encoding="utf-8") as f:
            f.write(payload)
            if not payload.endswith("\n"):
                f.write("\n")


def jsonl_read_all(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    raw = path.read_text(encoding="utf-8")
    if not raw:
        return [], 0
    lines = raw.splitlines()
    rows: list[dict[str, Any]] = []
    dropped = 0
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                dropped = 1
            else:
                raise IllegalTransitionError(
                    f"Mid-file JSON corruption in {path} at line {i + 1}"
                )
    return rows, dropped


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def append_event(event: LoopEvent) -> None:
    assert_legal_transition(
        LoopState(event.from_state), LoopState(event.to_state),
    )
    jsonl_append(state_jsonl(), event.to_jsonl(), state_lock_path())


def current_loop_state(loop_id: str) -> LoopState | None:
    rows, _ = jsonl_read_all(state_jsonl())
    last: LoopState | None = None
    for r in rows:
        if r.get("loop_id") == loop_id:
            last = LoopState(r["to_state"])
    return last


def open_loops() -> list[dict[str, Any]]:
    rows, _ = jsonl_read_all(state_jsonl())
    seen: dict[str, dict[str, Any]] = {}
    for r in rows:
        seen[r["loop_id"]] = r
    return [r for r in seen.values() if not is_terminal(LoopState(r["to_state"]))]


# ── Subcommands ─────────────────────────────────────────────────────────────
def cmd_iterate(args: argparse.Namespace) -> int:
    """Spawn a fresh-context loop driven by prompt-file.

    The pattern: each iteration reads prompt-file fresh; the agent updates
    prompt-file at the end of each iteration to reflect new state; loop exits
    when SUCCESS_CONDITION fires (file presence, exit-code 0, or grep pattern)
    or budget exhausted.
    """
    prompt_path = Path(args.prompt_file)
    if not prompt_path.exists():
        print(f"persist: prompt file not found: {prompt_path}", file=sys.stderr)
        return EXIT_USAGE

    loop_id = uuid.uuid4().hex[:12]
    budget = LoopBudget(
        max_iterations=args.max_iterations,
        max_wall_clock_s=args.max_wall_clock,
    )

    append_event(LoopEvent(
        ts=_utcnow(),
        loop_id=loop_id,
        prompt_file=str(prompt_path.resolve()),
        iteration=0,
        from_state=LoopState.SPAWNED.value,
        to_state=LoopState.SPAWNED.value,
        extra={
            "max_iterations": budget.max_iterations,
            "max_wall_clock_s": budget.max_wall_clock_s,
            "success_condition": args.success_condition or "",
            "agent_cmd": args.agent_cmd,
        },
    ))

    if args.dry_run:
        print(f"loop_id={loop_id} (dry-run; no agent spawned)")
        print(f"  prompt: {prompt_path}")
        print(f"  budget: max_iter={budget.max_iterations} wall={budget.max_wall_clock_s}s")
        print(f"  agent_cmd: {args.agent_cmd}")
        print(f"  success_condition: {args.success_condition or 'none'}")
        return EXIT_OK

    # Foreground loop — block on each iteration.
    started_at = time.monotonic()
    iteration = 0
    last_state = LoopState.SPAWNED

    while iteration < budget.max_iterations:
        elapsed = time.monotonic() - started_at
        if elapsed > budget.max_wall_clock_s:
            append_event(LoopEvent(
                ts=_utcnow(), loop_id=loop_id,
                prompt_file=str(prompt_path.resolve()), iteration=iteration,
                from_state=last_state.value,
                to_state=LoopState.BUDGET_EXHAUSTED.value,
                extra={"reason": "wall-clock", "elapsed_s": int(elapsed)},
            ))
            print(f"persist: wall-clock budget exhausted ({int(elapsed)}s); loop {loop_id} terminated")
            return EXIT_BUDGET_EXHAUSTED

        iteration += 1
        append_event(LoopEvent(
            ts=_utcnow(), loop_id=loop_id,
            prompt_file=str(prompt_path.resolve()), iteration=iteration,
            from_state=last_state.value,
            to_state=LoopState.ITERATING.value,
            extra={"elapsed_s": int(elapsed)},
        ))
        last_state = LoopState.ITERATING

        if args.verbose:
            print(f"\n=== persist loop {loop_id} — iteration {iteration}/{budget.max_iterations} (elapsed {int(elapsed)}s) ===")

        # Spawn a fresh agent context. Agent is responsible for updating
        # prompt_file at the end of iteration to reflect new state.
        rc = _spawn_agent(args.agent_cmd, prompt_path, args.verbose)

        # Check success condition (file presence / grep / exit code)
        if args.success_condition:
            if _check_success_condition(args.success_condition, prompt_path, rc):
                append_event(LoopEvent(
                    ts=_utcnow(), loop_id=loop_id,
                    prompt_file=str(prompt_path.resolve()), iteration=iteration,
                    from_state=last_state.value,
                    to_state=LoopState.SUCCESS.value,
                    extra={"reason": "success_condition matched", "exit_code": rc},
                ))
                print(f"persist: loop {loop_id} SUCCESS at iteration {iteration}")
                return EXIT_OK

    # Iteration ceiling
    append_event(LoopEvent(
        ts=_utcnow(), loop_id=loop_id,
        prompt_file=str(prompt_path.resolve()), iteration=iteration,
        from_state=last_state.value,
        to_state=LoopState.BUDGET_EXHAUSTED.value,
        extra={"reason": "max_iterations", "iterations": iteration},
    ))
    print(f"persist: max_iterations ({budget.max_iterations}) reached; loop {loop_id} terminated")
    return EXIT_BUDGET_EXHAUSTED


def _spawn_agent(agent_cmd: str, prompt_path: Path, verbose: bool) -> int:
    """Run the agent CLI with the prompt file's contents.

    Default agent_cmd is `claude -p {}` where {} is replaced with the prompt
    contents. Other CLIs supported: `codex {}`, `gemini -p {}`, etc.
    """
    prompt_text = prompt_path.read_text(encoding="utf-8")
    cmd_template = agent_cmd.replace("{}", prompt_text) if "{}" in agent_cmd \
        else f"{agent_cmd} {prompt_text}"

    if verbose:
        print(f"  spawning: {agent_cmd}")
    try:
        result = subprocess.run(
            cmd_template, shell=True, check=False,
        )
        return result.returncode
    except FileNotFoundError as e:
        print(f"persist: agent command not found: {e}", file=sys.stderr)
        return 127


def _check_success_condition(condition: str, prompt_path: Path, last_rc: int) -> bool:
    """Evaluate the success condition. Three forms supported:
    - 'exit-code-0' → last agent invocation returned 0
    - 'file-exists:PATH' → check filesystem
    - 'grep:PATTERN:FILE' → check pattern in file
    """
    if condition == "exit-code-0":
        return last_rc == 0
    if condition.startswith("file-exists:"):
        return Path(condition.split(":", 1)[1]).exists()
    if condition.startswith("grep:"):
        try:
            _, pattern, file_path = condition.split(":", 2)
        except ValueError:
            return False
        try:
            text = Path(file_path).read_text(encoding="utf-8")
            return pattern in text
        except OSError:
            return False
    return False


def cmd_status(args: argparse.Namespace) -> int:
    rows = open_loops()
    if args.loop_id is not None:
        rows = [r for r in rows if r["loop_id"] == args.loop_id]
    if args.json:
        print(json.dumps({"open_loops": rows}, indent=2))
    else:
        if not rows:
            print("no loops in flight")
            return EXIT_OK
        for r in rows:
            print(
                f"{r['loop_id']}  {r['to_state']:<18} iter={r.get('iteration', 0):<3}  "
                f"prompt={Path(r.get('prompt_file', '')).name}"
            )
    return EXIT_OK


def cmd_abandon(args: argparse.Namespace) -> int:
    state = current_loop_state(args.loop_id)
    if state is None:
        print(f"persist: loop {args.loop_id} not found", file=sys.stderr)
        return EXIT_DEGRADED
    if is_terminal(state):
        print(f"persist: loop {args.loop_id} already terminal ({state.value}); no-op")
        return EXIT_OK
    rows, _ = jsonl_read_all(state_jsonl())
    last = next((r for r in reversed(rows) if r["loop_id"] == args.loop_id), None)
    if not last:
        print(f"persist: loop {args.loop_id} state lookup failed", file=sys.stderr)
        return EXIT_DEGRADED
    append_event(LoopEvent(
        ts=_utcnow(), loop_id=args.loop_id,
        prompt_file=last.get("prompt_file", ""),
        iteration=last.get("iteration", 0),
        from_state=state.value,
        to_state=LoopState.ABANDONED.value,
        extra={"reason": args.reason or "manual abandon"},
    ))
    print(f"loop {args.loop_id}: {state.value} → ABANDONED")
    return EXIT_OK


def cmd_doctor(_args: argparse.Namespace) -> int:
    problems: list[str] = []

    # State dir writable
    try:
        persist_home().mkdir(parents=True, exist_ok=True)
        probe = persist_home() / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        problems.append(f"state directory not writable: {e}")

    # git available
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, text=True,
                             timeout=5, check=False)
        if out.returncode != 0:
            problems.append("git not functioning")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        problems.append("git not installed")

    if not problems:
        print("persist doctor: ok")
        return EXIT_OK
    print("persist doctor: degraded")
    for p in problems:
        print(f"  - {p}")
    return EXIT_DEGRADED


def cmd_conformance(args: argparse.Namespace) -> int:
    runner = os.environ.get("BROOMVA_PERSIST_PYTEST", f"{sys.executable} -m pytest")
    tests_dir = Path(__file__).resolve().parent.parent / "tests"
    if not tests_dir.exists():
        print(f"persist conformance: tests directory not found at {tests_dir}",
              file=sys.stderr)
        return EXIT_DEGRADED
    cmd = runner.split() + [str(tests_dir)]
    if args.verbose:
        cmd.append("-v")
    rc = subprocess.run(cmd, check=False).returncode
    if rc == 0:
        print("persist conformance: ok")
        return EXIT_OK
    print(f"persist conformance: failed (pytest exit {rc})", file=sys.stderr)
    return EXIT_DEGRADED


# ── CLI dispatch ───────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="persist",
        description=(
            "bstack P12 Persistent Loop Discipline. Cross-context restart loop: "
            "state in filesystem, fresh agent context per iteration. "
            "See workspace AGENTS.md §P12."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("iterate", help="Spawn a fresh-context loop driven by a prompt file")
    pi.add_argument("prompt_file", help="Path to PROMPT.md (the agent's persistent state)")
    pi.add_argument("--max-iterations", type=int, default=50,
                    help="Hard ceiling on iterations (default: 50)")
    pi.add_argument("--max-wall-clock", type=int, default=14400,
                    help="Wall-clock budget in seconds (default: 14400 = 4h, METR 80%%-horizon)")
    pi.add_argument("--success-condition", default=None,
                    help="exit-code-0 | file-exists:PATH | grep:PATTERN:FILE")
    pi.add_argument("--agent-cmd", default="claude -p '{}'",
                    help="Agent CLI invocation. {} is replaced with prompt contents. "
                         "Default: 'claude -p \\'{}\\''")
    pi.add_argument("--dry-run", action="store_true",
                    help="Register the loop in state.jsonl but don't spawn the agent")
    pi.add_argument("--verbose", "-v", action="store_true")
    pi.set_defaults(func=cmd_iterate)

    ps = sub.add_parser("status", help="Show open loops")
    ps.add_argument("--loop-id", default=None, help="Filter by loop ID")
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(func=cmd_status)

    pa = sub.add_parser("abandon", help="Mark a loop ABANDONED (terminal)")
    pa.add_argument("loop_id")
    pa.add_argument("--reason", default=None)
    pa.set_defaults(func=cmd_abandon)

    pd = sub.add_parser("doctor", help="Health-check persist dependencies")
    pd.set_defaults(func=cmd_doctor)

    pc = sub.add_parser("conformance", help="Run the test battery")
    pc.add_argument("--verbose", "-v", action="store_true")
    pc.set_defaults(func=cmd_conformance)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PersistError as e:
        print(f"persist: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
