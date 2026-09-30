#!/usr/bin/env python3
"""ctx-ablation — does the context we inject make sessions behave better, per token?

    python3 scripts/skill_evals/ctx_ablation/run.py validate  --tasks T.json [--deep]
    python3 scripts/skill_evals/ctx_ablation/run.py preflight --tasks T.json --out DIR [--live-canary]
    python3 scripts/skill_evals/ctx_ablation/run.py calibrate --tasks T.json --out DIR [--trials 3]
    python3 scripts/skill_evals/ctx_ablation/run.py run       --tasks T.json --out DIR [--arms ...]
    python3 scripts/skill_evals/ctx_ablation/run.py report    --out DIR

A causal measurement: the same task, in the same world, run under arms that differ
only in what is injected into the model's context (``arms.py``), graded by
deterministic assertions on tool calls and end state (``graders.py``).

THE ORDER IS THE METHOD
-----------------------
1. ``validate`` — every task is well-formed, fails a null run, and its grader tells
   its pass exemplar from its fail exemplar (``--deep``). Free.
2. ``preflight`` — each arm's hooks are run offline against each task's real
   fixture. An arm that claims role-x or ctx and would inject nothing is a
   refusal, not a result. ``--live-canary`` spends one short model call per arm to
   prove each arm delivers exactly its injections, memory included. Near free.
3. ``calibrate`` — the bare arm only. A task that passes without any injection
   measures nothing about injection; it is dropped, and the calibration is
   written down. This is the control-absent rule.
4. ``run`` — every arm on the retained tasks. Refuses tasks the calibration
   dropped, and refuses to run with no calibration at all.

Every trial is appended to ``results.jsonl`` as it finishes, so a run that stops
(the budget guard, a crash, Ctrl-C) resumes where it left off.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Sequence

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))

from skill_evals import jail as jail_mod  # noqa: E402
from skill_evals import runner as runner_mod  # noqa: E402
from skill_evals.ctx_ablation import arms as arms_mod  # noqa: E402
from skill_evals.ctx_ablation import fixture as fx  # noqa: E402
from skill_evals.ctx_ablation import graders as g  # noqa: E402
from skill_evals.ctx_ablation import metrics as m  # noqa: E402
from skill_evals.ctx_ablation import tasks as tasks_mod  # noqa: E402
from skill_evals.transcript import Transcript  # noqa: E402

DEFAULT_TASKS = _HERE / "tasks" / "pilot.json"
#: Haiku by default: see README § "Which model". The subscription's five-hour window
#: is shared with every other session on this account.
DEFAULT_MODEL = "haiku"
DEFAULT_TRIALS = 3
DEFAULT_TIMEOUT_S = 420
DEFAULT_JOBS = 4
#: Stop launching trials once the account's rate-limit window is this full.
DEFAULT_MAX_UTILIZATION = 0.90
#: Used for the plan's cost line until a calibration has measured the real figure.
DEFAULT_COST_ESTIMATE_USD = 0.12
#: The CLI whose stream shape this harness was verified against: hook_response
#: events for SessionStart, none for UserPromptSubmit, init.cwd, rate_limit_event.
EXPECTED_CLI_VERSION = "2.1.280"
#: The session id the offline role-x run logs under, so the live run's intake
#: event can be told apart from it.
OFFLINE_SESSION = "ctxabl-offline"
#: role-x's own carve-out (CARVE_OUT_MIN_WORDS in role-x.py): shorter prompts get no
#: intake block, in production as here.
ROLEX_MIN_WORDS = 3
#: Memory delivery, proven per trial from tokens: a memory arm's turn-one context must
#: exceed bare's (same task) by at least this, and any other arm's must not. Measured
#: on the pilot: memory arms +10,280 or more (the CLI's auto-memory block alone is
#: ~3.2k), every other arm +1,019 or less (role-x plus the brief).
MEMORY_MIN_DELTA_TOKENS = 2000

def calibration_dir(out: Path) -> Path:
    return Path(out) / "calibration"


CALIBRATION_RETAINED = "retained"
CALIBRATION_VACUOUS = "vacuous"
CALIBRATION_NO_SIGNAL = "no-signal"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# runtime for the hooks and stubs
# ---------------------------------------------------------------------------


def resolve_runtime() -> tuple[arms_mod.HookRuntime, str]:
    """The interpreter hooks run under, and whether role-x's PyYAML is reachable.

    Returns ``(runtime, problem)``; ``problem`` is empty when role-x can run.
    """
    python = shutil.which("python3") or sys.executable
    probe = subprocess.run([python, "-c", "import site; print(site.getuserbase())"],
                           capture_output=True, text=True, timeout=30)
    userbase = probe.stdout.strip()
    with tempfile.TemporaryDirectory(prefix="ctxabl-yaml-") as home:
        env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "PYTHONUSERBASE": userbase}
        ok = subprocess.run(
            [python, "-I", "-c", "import site, sys; sys.path.append(site.getusersitepackages()); import yaml"],
            env=env, capture_output=True, text=True, timeout=30).returncode == 0
    rt = arms_mod.HookRuntime(python=python, pythonuserbase=userbase, real_home=str(Path.home()))
    problem = "" if ok else (
        f"PyYAML is not importable by {python} under a moved HOME (PYTHONUSERBASE={userbase}); "
        "the role-x hook would exit 0 and inject nothing")
    return rt, problem


def _hook_env(case: fx.Case) -> dict[str, str]:
    return {**case.env, "CLAUDE_PROJECT_DIR": str(case.layout.workspace)}


def run_hook_offline(command: str, payload: dict[str, Any], case: fx.Case) -> str:
    """Run one hook command the way the CLI does (``sh -c``, JSON on stdin)."""
    proc = subprocess.run(["/bin/sh", "-c", command], cwd=str(case.layout.workspace), env=_hook_env(case),
                          input=json.dumps(payload), capture_output=True, text=True, timeout=60)
    return proc.stdout


def rolex_offline(case: fx.Case, settings: dict[str, Any], prompt: str) -> str:
    """What the role-x intake hook will inject for *prompt*. UserPromptSubmit output
    never appears in stream-json, so this is the only record of the text."""
    out = []
    for group in settings.get("hooks", {}).get("UserPromptSubmit", []):
        for hook in group.get("hooks", []):
            out.append(run_hook_offline(hook["command"], {
                "session_id": OFFLINE_SESSION, "hook_event_name": "UserPromptSubmit",
                "prompt": prompt, "cwd": str(case.layout.workspace)}, case))
    return "".join(out)


def session_start_offline(case: fx.Case, settings: dict[str, Any]) -> str:
    """SessionStart output, for preflight only: running the ctx hook appends to the
    board, so it is never run in a case a live trial will use."""
    out = []
    for group in settings.get("hooks", {}).get("SessionStart", []):
        for hook in group.get("hooks", []):
            raw = run_hook_offline(hook["command"], {
                "session_id": "ctxabl-preflight-0001", "hook_event_name": "SessionStart",
                "source": "startup", "cwd": str(case.layout.workspace)}, case)
            try:
                raw = json.loads(raw)["hookSpecificOutput"]["additionalContext"]
            except (ValueError, KeyError, TypeError):
                pass
            out.append(raw)
    return "\n".join(o for o in out if o)


def rolex_logged_prompt(layout: fx.CaseLayout, prompt: str) -> bool:
    """Did the LIVE intake hook run on this prompt? role-x logs every intake with the
    prompt's sha256 under the (jailed) HOME, just before it prints the block."""
    path = layout.home / ".config" / "broomva" / "role" / "events.jsonl"
    digest = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("prompt_digest") == digest and ev.get("session") != OFFLINE_SESSION:
            return True
    return False


# ---------------------------------------------------------------------------
# one trial
# ---------------------------------------------------------------------------


class Settings:
    """Run-wide knobs, resolved once."""

    def __init__(self, args: argparse.Namespace, cli: str, cli_version: str, rt: arms_mod.HookRuntime,
                 corpus: fx.Corpus, out: Path):
        self.cli = cli
        self.cli_version = cli_version
        self.model = args.model
        self.timeout = args.timeout
        self.keep = args.keep_workspaces
        self.rt = rt
        self.corpus = corpus
        self.out = out
        #: Every record carries this; a run directory holds one key only.
        self.calibration = str(getattr(args, "calibration_sha", "") or "uncalibrated")
        self.run_key = "|".join([self.model, cli_version or "?",
                                 str(corpus.manifest.get("sha256", "?"))[:12], self.calibration[:12]])


def _argv(s: Settings, prompt: str, layout: fx.CaseLayout) -> list[str]:
    # The runner's argv contract (stream-json + --verbose, --setting-sources project,
    # bypassPermissions, no session persistence), plus this harness's three flags.
    base = runner_mod.LiveRunner(cli=s.cli, model=s.model, timeout_s=s.timeout).build_argv(prompt)
    return base + ["--settings", str(layout.settings), "--mcp-config", str(layout.mcp_config),
                   "--strict-mcp-config"]


def _outcome_for_injections(arm: arms_mod.Arm, case: fx.Case, t: Transcript, rolex_text: str,
                            prompt: str) -> tuple[str, str]:
    """``("", "")`` when the arm got exactly its injections, else (outcome, why)."""
    layout = case.layout
    init_cwd = (t.init_event or {}).get("cwd")
    if not init_cwd:
        return m.ERROR, "the init event carries no cwd, so the memory key cannot be checked"
    if os.path.realpath(init_cwd) != os.path.realpath(layout.workspace):
        return m.ERROR, "the session cwd is not the workspace, so the memory key is wrong"
    hooks = m.hook_outputs(t)
    ctx_seen = any(arms_mod.CTX_MARKER in h["text"] for h in hooks)
    if arm.ctx and not ctx_seen:
        return m.INJECTION_MISSING, "ctx arm, but no SessionStart hook output carried the board brief"
    if not arm.ctx and ctx_seen:
        return m.LEAKED, "the board brief reached an arm without ctx"
    rolex_ran = rolex_logged_prompt(layout, prompt)
    # role-x itself declines some prompts (fewer than three words, among others),
    # and then prints nothing in production too. The offline run on the same prompt
    # and workspace says whether this is one; PyYAML being unreachable, the other
    # way to print nothing, is refused before any trial by resolve_runtime.
    rolex_expected = arms_mod.ROLEX_MARKER in rolex_text
    if arm.rolex and not rolex_expected and len(prompt.split()) >= ROLEX_MIN_WORDS:
        # Not the carve-out, so role-x printing nothing means it could not run (no
        # roles/ or catalog in the corpus, a missing dependency): the arm is bare.
        return m.INJECTION_MISSING, "role-x printed no intake block for a prompt it does not carve out"
    if arm.rolex and rolex_expected and not rolex_ran:
        return m.INJECTION_MISSING, "role-x arm, but the live intake hook logged no intake for this prompt"
    if not arm.rolex and rolex_ran:
        return m.LEAKED, "role-x ran in an arm without it"
    if arm.memory and not (layout.memory_dir / "MEMORY.md").is_file():
        return m.INJECTION_MISSING, "memory arm, but MEMORY.md is not at the cwd's memory key"
    return "", ""


def run_trial(s: Settings, task: tasks_mod.Task, arm: arms_mod.Arm, trial: int) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix=f"ctxabl-{task.id[:20]}-{arm.id}-{trial}-")).resolve()
    record: dict[str, Any] = {"task": task.id, "class": task.cls, "arm": arm.id, "trial": trial,
                              "model": s.model, "cli_version": s.cli_version, "run_key": s.run_key}
    try:
        try:
            case = fx.build_case(root, task.fixture, s.corpus, python=s.rt.python)
            settings = fx.write_arm_settings(case, arm, s.rt)
            rolex_text = rolex_offline(case, settings, task.prompt) if arm.rolex else ""
        except (fx.FixtureError, OSError, subprocess.SubprocessError, KeyError) as exc:
            record.update(outcome=m.ERROR, detail=f"fixture: {exc}")
            return record
        argv = _argv(s, task.prompt, case.layout)
        started = time.monotonic()
        try:
            proc = subprocess.run(argv, cwd=str(case.layout.workspace), env=case.env,
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=s.timeout)
            stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr, code = f"TIMEOUT after {s.timeout}s", 124
        except OSError as exc:
            record.update(outcome=m.ERROR, detail=f"could not launch the CLI: {exc}")
            return record
        wall_ms = int((time.monotonic() - started) * 1000)
        tdir = s.out / "transcripts" / arm.id / task.id
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / f"trial-{trial:02d}.jsonl").write_text(stdout, encoding="utf-8")
        t = Transcript.from_ndjson(stdout, exit_code=code, stderr=stderr, wall_ms=wall_ms)
        record.update(_measure(s, task, arm, case, t, rolex_text, wall_ms))
        if not t.events or t.is_error:
            record.update(outcome=m.ERROR, detail=(t.error_reason or stderr or f"exit {code}")[:300])
            return record
        bad, why = _outcome_for_injections(arm, case, t, rolex_text, task.prompt)
        if bad:
            record.update(outcome=bad, detail=why)
            return record
        ctx = g.GradeContext(transcript=t, layout=case.layout, env=case.env, variables=case.variables,
                             stub_logs=fx.read_stub_logs(case.layout))
        passed, results = g.grade(ctx, task.assertions)
        clean = lambda text: fx.sanitize(text, case.layout)  # noqa: E731
        record.update(
            outcome=m.PASS if passed else m.FAIL,
            detail=clean("; ".join(f"{r.kind}: {r.detail}" for r in results if not r.passed))[:600],
            assertions=[{**r.to_dict(), "detail": clean(r.detail)} for r in results],
            source_retrieved=g.source_retrieved(ctx, task.source_paths),
            reflexes=m.reflexes(ctx),
            entities_opened=m.entities_opened(ctx, record.get("entities_injected") or []),
        )
        return record
    finally:
        if not s.keep:
            shutil.rmtree(root, ignore_errors=True)
        else:
            record["workspace"] = str(root)


def _measure(s: Settings, task: tasks_mod.Task, arm: arms_mod.Arm, case: fx.Case, t: Transcript,
             rolex_text: str, wall_ms: int) -> dict[str, Any]:
    hooks = m.hook_outputs(t)
    memory_chars = 0
    if arm.memory:
        try:
            memory_chars = len((case.layout.memory_dir / "MEMORY.md").read_text(encoding="utf-8"))
        except OSError:
            memory_chars = 0
    session_chars = sum(h["chars"] for h in hooks if h["event"] == "SessionStart")
    tool_uses = t.tool_uses()
    return {
        "wall_ms": wall_ms,
        "cost_usd": t.cost_usd,
        "num_turns": t.num_turns,
        "context_tokens": m.context_tokens(t),
        **m.result_usage(t),
        "tool_calls": len(tool_uses),
        "tool_calls_executed": sum(1 for tu in tool_uses if t.executed(tu)),
        "injected_chars": memory_chars + session_chars + len(rolex_text),
        "injected_chars_by_source": {"memory": memory_chars, "session_start": session_chars,
                                     "rolex": len(rolex_text)},
        "entities_injected": m.injected_entities(rolex_text),
        "rate_limit_utilization": m.rate_limit_utilization(t),
    }


# ---------------------------------------------------------------------------
# a suite: planning, the budget guard, resume
# ---------------------------------------------------------------------------


def verify_memory_delivery(rows: Sequence[dict[str, Any]], arm_memory: dict[str, bool]
                           ) -> tuple[list[dict[str, Any]], str]:
    """Prove memory delivery (and its absence) per trial, from the tokens.

    Auto-memory leaves no event in the stream, so the only direct evidence is the
    size of the first call: a memory arm's must exceed the same task's bare minimum
    by ``MEMORY_MIN_DELTA_TOKENS``; any other arm's must not. A graded trial that
    breaks this becomes INJECTION_MISSING or LEAKED. Without a bare arm there is no
    reference, and the note says so rather than passing silently.
    """
    bare: dict[str, int] = {}
    for r in rows:
        if r["arm"] == "bare" and isinstance(r.get("context_tokens"), int):
            bare[r["task"]] = min(bare.get(r["task"], r["context_tokens"]), r["context_tokens"])
    if not bare:
        return list(rows), "memory delivery NOT verified: no bare arm in these results"
    out, flipped = [], 0
    for r in rows:
        ref, ctx_tok = bare.get(r["task"]), r.get("context_tokens")
        if (r["outcome"] in m.NON_OUTCOMES or r["arm"] == "bare" or ref is None
                or not isinstance(ctx_tok, int) or r["arm"] not in arm_memory):
            out.append(r)
            continue
        delivered = ctx_tok - ref >= MEMORY_MIN_DELTA_TOKENS
        if arm_memory[r["arm"]] and not delivered:
            r = {**r, "outcome": m.INJECTION_MISSING,
                 "detail": f"memory arm, but turn one is only {ctx_tok - ref:+} tokens over bare"}
            flipped += 1
        elif not arm_memory[r["arm"]] and delivered:
            r = {**r, "outcome": m.LEAKED,
                 "detail": f"turn one is {ctx_tok - ref:+} tokens over bare in an arm without memory"}
            flipped += 1
        out.append(r)
    return out, f"memory delivery verified from tokens against bare ({flipped} trial(s) voided)"


def load_results(out: Path) -> list[dict[str, Any]]:
    path = out / "results.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def latest_by_key(rows: Sequence[dict[str, Any]]) -> dict[tuple[str, str, int], dict[str, Any]]:
    out: dict[tuple[str, str, int], dict[str, Any]] = {}
    for r in rows:
        out[(r["task"], r["arm"], int(r["trial"]))] = r
    return out


class MixedRunError(RuntimeError):
    """The run directory already holds trials from a different model, CLI, corpus
    or calibration; resuming would pool them into one table."""


def run_suite(s: Settings, tasks: Sequence[tasks_mod.Task], arms: Sequence[arms_mod.Arm], trials: int,
              *, jobs: int, max_utilization: float, retry_void: bool, seed: int) -> dict[str, Any]:
    existing = load_results(s.out)
    foreign = sorted({r.get("run_key", "?") for r in existing} - {s.run_key})
    if foreign:
        raise MixedRunError(
            f"{s.out} already holds trials under another run key ({foreign[0]}); this run is "
            f"{s.run_key}. Use a new --out: a resume must not pool models, CLIs, corpora or "
            "calibrations into one table.")
    done = latest_by_key(existing)
    plan = []
    for trial in range(1, trials + 1):
        # Trial-major and shuffled within a trial, so a run the budget guard stops
        # early leaves every arm about equally sampled, not the first arms complete.
        block = [(t, a, trial) for t in tasks for a in arms]
        random.Random(seed + trial).shuffle(block)
        plan.extend(block)
    todo = []
    for t, a, n in plan:
        prev = done.get((t.id, a.id, n))
        if prev is None or (retry_void and prev.get("outcome") in m.NON_OUTCOMES):
            todo.append((t, a, n))
    print(f"[ctx-ablation] {len(plan)} trial(s) planned, {len(plan) - len(todo)} already recorded, "
          f"{len(todo)} to run (jobs={jobs})", file=sys.stderr)
    lock = threading.Lock()
    stop = threading.Event()
    counts = {"ran": 0, "skipped": 0}

    def one(item):
        t, a, n = item
        if stop.is_set():
            with lock:
                counts["skipped"] += 1
            return
        rec = run_trial(s, t, a, n)
        with lock:
            with open(s.out / "results.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
            counts["ran"] += 1
            util = rec.get("rate_limit_utilization")
            print(f"[ctx-ablation] {counts['ran']:>4}/{len(todo)} {rec['outcome']:<17} "
                  f"{a.id:<11} {t.id:<40} "
                  f"{(rec.get('wall_ms') or 0) / 1000:5.0f}s  util={util if util is not None else '?'}",
                  file=sys.stderr)
            if isinstance(util, (int, float)) and util >= max_utilization and not stop.is_set():
                stop.set()
                print(f"[ctx-ablation] BUDGET GUARD: rate-limit window at {util:.0%} >= "
                      f"{max_utilization:.0%}; no new trials start. Re-run the same command later "
                      "to resume.", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        list(pool.map(one, todo))
    return {"planned": len(plan), "ran": counts["ran"], "skipped_budget": counts["skipped"],
            "stopped_by_budget_guard": stop.is_set()}


def estimate(n_trials: int, jobs: int, calibration: dict[str, Any] | None) -> str:
    cost = wall = None
    if calibration:
        cost = calibration.get("mean_cost_usd")
        wall = calibration.get("mean_wall_s")
    cost = cost if isinstance(cost, (int, float)) else DEFAULT_COST_ESTIMATE_USD
    wall = wall if isinstance(wall, (int, float)) else 60.0
    source = "measured in calibration" if calibration and calibration.get("mean_cost_usd") else "default guess"
    return (f"{n_trials} trials x ~${cost:.3f} = ~${n_trials * cost:.2f} notional API-equivalent "
            f"({source}); ~{n_trials * wall / max(1, jobs) / 60:.0f} min at jobs={jobs}")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def _load(args) -> list[tasks_mod.Task]:
    tasks, _doc = tasks_mod.load_tasks(args.tasks)
    if getattr(args, "task", None):
        wanted = set(args.task)
        missing = wanted - {t.id for t in tasks}
        if missing:
            raise tasks_mod.TaskError(f"no such task id(s): {sorted(missing)}")
        tasks = [t for t in tasks if t.id in wanted]
    return tasks


def _corpus(args, out: Path) -> fx.Corpus:
    dest = out / "corpus"
    if (dest / "manifest.json").is_file() and not args.refresh_corpus:
        return fx.load_corpus(dest)
    if dest.exists():
        shutil.rmtree(dest)
    corpus = fx.snapshot_corpus(dest, workspace_src=args.workspace_src, memory_src=args.memory_src)
    print(f"[ctx-ablation] corpus snapshot: {corpus.manifest['files']} files, "
          f"{corpus.manifest['bytes'] / 1e6:.1f} MB, sha256 {corpus.manifest['sha256'][:12]}"
          + (f", MISSING {corpus.manifest['missing']}" if corpus.manifest["missing"] else ""),
          file=sys.stderr)
    return corpus


def cmd_validate(args) -> int:
    try:
        tasks = _load(args)
    except tasks_mod.TaskError as exc:
        print(f"[ctx-ablation] INVALID: {exc}", file=sys.stderr)
        return EXIT_FAIL
    print(f"[ctx-ablation] {len(tasks)} task(s) valid: "
          + ", ".join(f"{c}={sum(1 for t in tasks if t.cls == c)}" for c in tasks_mod.TASK_CLASSES))
    if not args.deep:
        return EXIT_OK
    failures = 0
    with tempfile.TemporaryDirectory(prefix="ctxabl-validate-") as tmp:
        corpus = fx.Corpus(Path(tmp) / "empty-corpus")  # the graders never read the corpus
        for task in tasks:
            checks = []
            for label, fn, want in (("null run", lambda r: tasks_mod.null_run(task, corpus, r), False),
                                    ("pass exemplar", lambda r: tasks_mod.run_exemplar(task, "pass", corpus, r), True),
                                    ("fail exemplar", lambda r: tasks_mod.run_exemplar(task, "fail", corpus, r), False)):
                root = Path(tempfile.mkdtemp(dir=tmp))
                try:
                    passed, results = fn(root)
                except Exception as exc:  # noqa: BLE001 - reported, never swallowed
                    checks.append(f"{label}: raised {type(exc).__name__}: {exc}")
                    continue
                if passed != want:
                    why = "; ".join(f"{r.kind}: {r.detail}" for r in results if r.passed != want or not r.passed)
                    checks.append(f"{label} {'passed' if passed else 'failed'} (must "
                                  f"{'pass' if want else 'fail'}): {why[:200]}")
            status = "ok" if not checks else "BROKEN"
            failures += bool(checks)
            print(f"  {status:<7}{task.id}" + "".join(f"\n           - {c}" for c in checks))
    return EXIT_FAIL if failures else EXIT_OK


def cmd_preflight(args) -> int:
    tasks = _load(args)
    arms = [arms_mod.parse_arm(a) for a in args.arms.split(",")]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rt, problem = resolve_runtime()
    if problem and any(a.rolex for a in arms):
        print(f"[ctx-ablation] PREFLIGHT FAILED: {problem}", file=sys.stderr)
        return EXIT_FAIL
    corpus = _corpus(args, out)
    table: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    notes: list[str] = []
    for task in tasks:
        table[task.id] = {}
        for arm in arms:
            with tempfile.TemporaryDirectory(prefix="ctxabl-pre-") as tmp:
                case = fx.build_case(Path(tmp), task.fixture, corpus, python=rt.python, link_auth=False)
                settings = fx.write_arm_settings(case, arm, rt)
                rolex = rolex_offline(case, settings, task.prompt) if arm.rolex else ""
                session = session_start_offline(case, settings)
                memory = ((case.layout.memory_dir / "MEMORY.md").read_text(encoding="utf-8")
                          if arm.memory and (case.layout.memory_dir / "MEMORY.md").is_file() else "")
                if arm.rolex and arms_mod.ROLEX_MARKER not in rolex:
                    if len(task.prompt.split()) < ROLEX_MIN_WORDS:
                        notes.append(f"{arm.id} x {task.id}: role-x declines a prompt under "
                                     f"{ROLEX_MIN_WORDS} words, as it does in production")
                    else:
                        problems.append(f"{arm.id} x {task.id}: role-x printed no intake block")
                if arm.ctx and arms_mod.CTX_MARKER not in session:
                    problems.append(f"{arm.id} x {task.id}: ctx printed no board brief")
                if arm.memory and not memory:
                    problems.append(f"{arm.id} x {task.id}: no MEMORY.md at the memory key")
                injected = "\n".join([rolex, session, memory])
                in_context = [a["re"] for a in task.assertions if a.get("kind") == "answer"
                              and g._rx(fx.expand(a["re"], case.variables)).search(injected)]
                table[task.id][arm.id] = {"rolex": len(rolex), "session_start": len(session),
                                          "memory": len(memory), "answer_in_context": in_context}
    (out / "preflight.json").write_text(json.dumps({"tasks": table, "problems": problems, "notes": notes},
                                                   indent=2), encoding="utf-8")
    print("| task | " + " | ".join(a.id for a in arms) + " |\n|" + "---|" * (len(arms) + 1))
    for tid, row in table.items():
        cells = []
        for a in arms:
            c = row[a.id]
            total = c["rolex"] + c["session_start"] + c["memory"]
            cells.append(f"{total:,}" + (" *" if c["answer_in_context"] else ""))
        print(f"| {tid} | " + " | ".join(cells) + " |")
    print("\n(injected characters per task x arm. * = the answer's fact is IN the injected text: "
          "by design for a coordination task, whose fact is the peer the brief names; for a "
          "retrieval task it means that arm is handed the answer rather than pointed at it)")
    for note in notes:
        print(f"[ctx-ablation] note  {note}", file=sys.stderr)
    for p in problems:
        print(f"[ctx-ablation] PREFLIGHT PROBLEM  {p}", file=sys.stderr)
    code = EXIT_FAIL if problems else EXIT_OK
    if args.live_canary and not problems:
        code = live_canary(args, arms, rt, corpus, out) or code
    return code


CANARY_MEMORY = "MEMCANARY-7Q"
CANARY_CTX = "CTXCANARY-4K"
#: From the first quality-bar bullet of role-x's _meta lens ("Snapshot (P15) and
#: Dep-Chain (P14)..."): the canary's evidence that the role-x block reached the model.
#: Not "snapshot", which the fixture's own commit message also carries.
CANARY_ROLEX = "dep-chain"
#: The question names no canary token. The first version quoted them, and role-x's
#: "consider authoring a lens" nudge builds a slug from prompt words, so it echoed
#: the tokens back into context and the role-x arms "saw" canaries they never had.
CANARY_PROMPT = (
    "Do not use any tools. Answer from your context only, never from this message. "
    "Reply with exactly three lines: 1) every token shaped like LETTERS followed by CANARY, a "
    "hyphen and a code that appears in your memory or system prompt, or none; 2) every token of "
    "that shape that appears in context injected by a hook, or none; 3) the first bullet of any "
    "list headed Quality bar in your context, or none."
)


def live_canary(args, arms: Sequence[arms_mod.Arm], rt: arms_mod.HookRuntime, corpus: fx.Corpus,
                out: Path) -> int:
    """One short model call per arm: the model reports which canaries it can see.

    Proves the mechanism end to end, memory included: an arm must see exactly the
    canaries of its own injections and none of the others'.
    """
    cli, version = _cli(args)
    if not cli:
        return EXIT_USAGE
    canary_fixture = {"ctx_peers": [{"session_id": "c0ffee00-1111-4222-8333-944455556666",
                                     "branch": "main", "age_min": 5,
                                     "arc_line": f"ARC-STATUS: OTHER {CANARY_CTX} lane"}]}
    failures = 0
    for arm in arms:
        with tempfile.TemporaryDirectory(prefix="ctxabl-canary-") as tmp:
            case = fx.build_case(Path(tmp), canary_fixture, corpus, python=rt.python)
            (case.layout.memory_dir / "MEMORY.md").write_text(
                f"# Memory Index\n- {CANARY_MEMORY}: the canary line for the memory arm.\n", encoding="utf-8")
            fx.write_arm_settings(case, arm, rt)
            s = Settings(args, cli, version, rt, corpus, out)
            proc = subprocess.run(_argv(s, CANARY_PROMPT, case.layout), cwd=str(case.layout.workspace),
                                  env=case.env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=180)
            answer = Transcript.from_ndjson(proc.stdout).final_text()
            seen = {"memory": CANARY_MEMORY in answer, "ctx": CANARY_CTX in answer,
                    "rolex": CANARY_ROLEX in answer.lower()}
            want = {"memory": arm.memory, "ctx": arm.ctx, "rolex": arm.rolex}
            ok = seen == want
            failures += not ok
            print(f"  canary {arm.id:<11} saw {seen}  want {want}  {'ok' if ok else 'MISMATCH'}")
            if not ok:
                print(f"         answer: {answer[:300]!r}")
    return EXIT_FAIL if failures else EXIT_OK


def _cli(args) -> tuple[str | None, str]:
    cli = runner_mod.detect_cli(args.cli)
    if not cli:
        print("error: agent CLI not found; pass --cli", file=sys.stderr)
        return None, ""
    version = runner_mod.cli_version(cli)
    if version and version != EXPECTED_CLI_VERSION:
        print(f"[ctx-ablation] WARNING  CLI {version} != {EXPECTED_CLI_VERSION}, the version whose "
              "stream shape (hook_response, init.cwd, rate_limit_event) this harness was checked on",
              file=sys.stderr)
    return cli, version


def _live_setup(args, out: Path) -> tuple[Settings | None, int]:
    rt, problem = resolve_runtime()
    arms = [arms_mod.parse_arm(a) for a in args.arms.split(",")] if hasattr(args, "arms") else []
    if problem and any(a.rolex for a in arms):
        print(f"[ctx-ablation] REFUSING: {problem}", file=sys.stderr)
        return None, EXIT_FAIL
    cli, version = _cli(args)
    if not cli:
        return None, EXIT_USAGE
    probe = Path(tempfile.mkdtemp(prefix="ctxabl-jailcheck-"))
    try:
        jail_mod.prepare_jail(probe, link_auth=False)
        verdict = jail_mod.verify_jail(probe)
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    if not verdict.holds:
        for leak in verdict.escapes:
            print(f"[ctx-ablation] JAIL ESCAPE  {leak}", file=sys.stderr)
        return None, EXIT_FAIL
    if jail_mod.auth_material_missing():
        print("[ctx-ablation] WARNING  no keychain to link into the jail: trials may all fail "
              "'Not logged in'", file=sys.stderr)
    corpus = _corpus(args, out)
    missing = set(corpus.manifest.get("missing") or [])
    if any(a.rolex for a in arms) and missing & {"roles", "docs/knowledge-index.md"}:
        print(f"[ctx-ablation] REFUSING: the corpus lacks {sorted(missing)}, so role-x would print "
              "nothing and every role-x trial would be a bare one", file=sys.stderr)
        return None, EXIT_FAIL
    cal = getattr(args, "calibration_doc", None)
    if cal and cal.get("corpus_sha256") and cal["corpus_sha256"] != corpus.manifest.get("sha256"):
        print("[ctx-ablation] REFUSING: the calibration was taken on another corpus snapshot "
              f"({str(cal['corpus_sha256'])[:12]} != {str(corpus.manifest.get('sha256'))[:12]}); "
              "recalibrate on this one", file=sys.stderr)
        return None, EXIT_FAIL
    return Settings(args, cli, version, rt, corpus, out), EXIT_OK


def calibration_verdicts(bare_rows: Sequence[dict[str, Any]], task_ids: Sequence[str],
                         trials: int) -> dict[str, dict[str, Any]]:
    """The control-absent rule, applied. A task is RETAINED only if the bare arm
    produced graded trials and passed none of them. One bare pass makes it VACUOUS:
    the grader can pass without the injection, so a pass under an injection says
    nothing about the injection. Too few graded trials is NO-SIGNAL, which is not
    retained either: a task whose bare run could not be graded was never shown to fail.
    """
    out: dict[str, dict[str, Any]] = {}
    for tid in task_ids:
        tr = [r for r in bare_rows if r["task"] == tid and r["arm"] == "bare"]
        graded = [r for r in tr if r["outcome"] not in m.NON_OUTCOMES]
        passes = sum(1 for r in graded if r["outcome"] == m.PASS)
        if len(graded) < min(2, trials):
            verdict = CALIBRATION_NO_SIGNAL
        elif passes:
            verdict = CALIBRATION_VACUOUS
        else:
            verdict = CALIBRATION_RETAINED
        out[tid] = {"bare_passes": passes, "bare_graded": len(graded), "void": len(tr) - len(graded),
                    "verdict": verdict,
                    "fail_details": sorted({str(r.get("detail", ""))[:160] for r in graded
                                            if r["outcome"] == m.FAIL})[:3]}
    return out


def cmd_calibrate(args) -> int:
    tasks = _load(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    n = len(tasks) * args.trials
    print(f"[ctx-ablation] CALIBRATION (bare arm only): {len(tasks)} tasks x {args.trials} trials; "
          f"{estimate(n, args.jobs, None)}", file=sys.stderr)
    if args.dry_run:
        return EXIT_OK
    args.arms = "bare"
    s, code = _live_setup(args, out)
    if s is None:
        return code
    # Calibration trials live in their own directory. If they shared results.jsonl
    # with `run`, the run would resume from them and reuse, as its bare arm, the very
    # trials that selected the tasks for failing in bare: bare would score 0% on the
    # retained set by construction. The run's bare arm is a fresh sample instead,
    # which also shows how much of each calibration failure was luck.
    s.out = calibration_dir(out)
    s.out.mkdir(parents=True, exist_ok=True)
    watch = jail_mod.RealStateWatch()
    watch.snapshot()
    info = run_suite(s, tasks, [arms_mod.ARM_REGISTRY["bare"]], args.trials, jobs=args.jobs,
                     max_utilization=args.max_utilization, retry_void=args.retry_void, seed=args.seed)
    rows = [r for r in latest_by_key(load_results(s.out)).values() if r["arm"] == "bare"]
    verdicts = calibration_verdicts(rows, [t.id for t in tasks], args.trials)
    changes = watch.changes()
    (out / "real-state-changes.json").write_text(json.dumps(changes, indent=2), encoding="utf-8")
    costs = [r["cost_usd"] for r in rows if isinstance(r.get("cost_usd"), (int, float))]
    walls = [r["wall_ms"] / 1000 for r in rows if isinstance(r.get("wall_ms"), int)]
    cal = {
        "rule": "a task must FAIL in the bare arm, or it is dropped as vacuous",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": s.model, "cli_version": s.cli_version, "trials": args.trials,
        "corpus_sha256": s.corpus.manifest.get("sha256"),
        "mean_cost_usd": round(sum(costs) / len(costs), 4) if costs else None,
        "mean_wall_s": round(sum(walls) / len(walls), 1) if walls else None,
        "run": info,
        # A count only: the paths name the operator's machine and go to their own file
        # in the run directory, so this file is safe to commit as written.
        "real_state_changes": len(changes),
        "tasks": verdicts,
    }
    (out / "calibration.json").write_text(json.dumps(cal, indent=2), encoding="utf-8")
    print("\n| task | bare passes | verdict |\n|---|---|---|")
    for tid, v in verdicts.items():
        print(f"| {tid} | {v['bare_passes']}/{v['bare_graded']}"
              + (f" (+{v['void']} void)" if v["void"] else "") + f" | {v['verdict']} |")
    kept = sum(1 for v in verdicts.values() if v["verdict"] == CALIBRATION_RETAINED)
    print(f"\n[ctx-ablation] {kept}/{len(verdicts)} task(s) retained; calibration written to "
          f"{out / 'calibration.json'}", file=sys.stderr)
    return EXIT_OK


def select_round_robin(tasks: Sequence[tasks_mod.Task], limit: int) -> list[tasks_mod.Task]:
    """The pre-registered rule for a pilot drawn from more retained tasks than it runs:
    round-robin over each task's PRIMARY target (its first), in file order. Fixed before
    any calibration result was seen, so the pilot cannot be chosen for its outcome, and
    balanced so no one injection gets all the tasks."""
    queues: dict[str, list[tasks_mod.Task]] = {}
    for t in tasks:
        queues.setdefault(t.targets[0] if t.targets else "", []).append(t)
    picked: list[tasks_mod.Task] = []
    while len(picked) < limit and any(queues.values()):
        for key in list(queues):
            if queues[key] and len(picked) < limit:
                picked.append(queues[key].pop(0))
    order = {t.id: i for i, t in enumerate(tasks)}
    return sorted(picked, key=lambda t: order[t.id])


def cmd_run(args) -> int:
    tasks = _load(args)
    arms = [arms_mod.parse_arm(a) for a in args.arms.split(",")]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cal = None
    if args.calibration:
        raw_cal = Path(args.calibration).read_bytes()
        cal = json.loads(raw_cal)
        args.calibration_doc = cal
        args.calibration_sha = hashlib.sha256(raw_cal).hexdigest()
        if cal.get("model") and cal["model"] != args.model:
            print(f"error: the calibration was run on {cal['model']!r}, this run is {args.model!r}. "
                  "Which tasks fail without injection depends on the model; recalibrate.",
                  file=sys.stderr)
            return EXIT_USAGE
        verdicts = cal.get("tasks") or {}
        dropped = [t.id for t in tasks if (verdicts.get(t.id) or {}).get("verdict") != CALIBRATION_RETAINED]
        for tid in dropped:
            v = (verdicts.get(tid) or {}).get("verdict", "uncalibrated")
            print(f"[ctx-ablation] dropping {tid}: calibration verdict {v}", file=sys.stderr)
        tasks = [t for t in tasks if t.id not in dropped]
    elif not args.allow_uncalibrated:
        print("error: no --calibration. A task that passes without any injection measures nothing, "
              "and only a calibration run can tell; run `calibrate` first (or pass "
              "--allow-uncalibrated for a smoke run whose numbers you will not report).", file=sys.stderr)
        return EXIT_USAGE
    if not tasks:
        print("error: no tasks left to run", file=sys.stderr)
        return EXIT_USAGE
    if args.limit:
        tasks = select_round_robin(tasks, args.limit)
        print(f"[ctx-ablation] --limit {args.limit}: {', '.join(t.id for t in tasks)}", file=sys.stderr)
    n = len(tasks) * len(arms) * args.trials
    print(f"[ctx-ablation] RUN: {len(tasks)} tasks x {len(arms)} arms ({','.join(a.id for a in arms)}) "
          f"x {args.trials} trials; {estimate(n, args.jobs, cal)}", file=sys.stderr)
    if args.dry_run:
        return EXIT_OK
    s, code = _live_setup(args, out)
    if s is None:
        return code
    watch = jail_mod.RealStateWatch()
    watch.snapshot()
    info = run_suite(s, tasks, arms, args.trials, jobs=args.jobs, max_utilization=args.max_utilization,
                     retry_void=args.retry_void, seed=args.seed)
    changes = watch.changes()
    if changes:
        print(f"[ctx-ablation] REAL STATE CHANGED under ~/.config/broomva during the run "
              f"({len(changes)} path(s)); another session may have written them", file=sys.stderr)
    meta = {"run": info, "calibration": str(args.calibration) if args.calibration else None,
            "tasks": [t.to_dict() for t in tasks], "arms": [a.__dict__ for a in arms],
            "model": s.model, "cli_version": s.cli_version, "trials": args.trials,
            "corpus": s.corpus.manifest, "real_state_changes": changes}
    (out / "run-meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return cmd_report(args)


def cmd_report(args) -> int:
    out = Path(args.out)
    rows = list(latest_by_key(load_results(out)).values())
    if not rows:
        print(f"error: no results under {out}", file=sys.stderr)
        return EXIT_USAGE
    arm_memory = {}
    for arm_id in {r["arm"] for r in rows}:
        try:
            arm_memory[arm_id] = arms_mod.parse_arm(arm_id).memory
        except ValueError:
            pass
    rows, memory_note = verify_memory_delivery(rows, arm_memory)
    print(f"[ctx-ablation] {memory_note}", file=sys.stderr)
    order = [a for a in arms_mod.DEFAULT_ARMS if any(r["arm"] == a for r in rows)]
    order += sorted({r["arm"] for r in rows} - set(order))
    if getattr(args, "task", None):
        rows = [r for r in rows if r["task"] in set(args.task)]
    table = m.aggregate(rows, order)
    matrix = m.task_matrix(rows, order)
    text = "\n\n".join([
        f"_{memory_note}._",
        "### Per arm\n\n" + m.format_table(table),
        "### Per task (passes / graded trials)\n\n" + m.format_matrix(matrix, order),
        "### Retrieval reflexes (share of graded trials)\n\n" + m.format_reflexes(table),
    ])
    (out / "report.md").write_text(text + "\n", encoding="utf-8")
    (out / "report.json").write_text(json.dumps({"arms": [r.to_dict() for r in table], "matrix": matrix},
                                                indent=2), encoding="utf-8")
    print(text)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ctx-ablation", description=__doc__.split("\n")[1],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, live: bool) -> None:
        sp.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
        sp.add_argument("--task", action="append", help="only this task id (repeatable)")
        if live:
            sp.add_argument("--out", required=True, help="run directory (results, transcripts, corpus)")
            sp.add_argument("--model", default=DEFAULT_MODEL)
            sp.add_argument("--cli")
            sp.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
            sp.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
            sp.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
            sp.add_argument("--max-utilization", type=float, default=DEFAULT_MAX_UTILIZATION,
                            help="stop starting trials once the rate-limit window is this full")
            sp.add_argument("--retry-void", action="store_true",
                            help="re-run trials whose recorded outcome was ERROR/INJECTION_MISSING/LEAKED")
            sp.add_argument("--keep-workspaces", action="store_true")
            sp.add_argument("--dry-run", action="store_true", help="print the plan and estimate, spend nothing")
            sp.add_argument("--seed", type=int, default=20260929)
            sp.add_argument("--workspace-src", type=Path, default=fx.DEFAULT_WORKSPACE_SRC)
            sp.add_argument("--memory-src", type=Path, default=fx.DEFAULT_MEMORY_SRC)
            sp.add_argument("--refresh-corpus", action="store_true")

    v = sub.add_parser("validate", help="schema; with --deep, null run + exemplars (free)")
    common(v, live=False)
    v.add_argument("--deep", action="store_true")
    v.set_defaults(fn=cmd_validate)

    pf = sub.add_parser("preflight", help="run each arm's hooks offline per task (free)")
    common(pf, live=True)
    pf.add_argument("--arms", default=",".join(arms_mod.DEFAULT_ARMS))
    pf.add_argument("--live-canary", action="store_true", help="one short model call per arm")
    pf.set_defaults(fn=cmd_preflight)

    c = sub.add_parser("calibrate", help="bare arm only; drops tasks that pass without injection")
    common(c, live=True)
    c.set_defaults(fn=cmd_calibrate)

    r = sub.add_parser("run", help="every arm on the calibrated tasks")
    common(r, live=True)
    r.add_argument("--arms", default=",".join(arms_mod.DEFAULT_ARMS))
    r.add_argument("--calibration", type=Path)
    r.add_argument("--allow-uncalibrated", action="store_true")
    r.add_argument("--limit", type=int, default=0,
                   help="run at most N retained tasks, chosen round-robin by primary target")
    r.set_defaults(fn=cmd_run)

    rp = sub.add_parser("report", help="re-render the tables from results.jsonl")
    rp.add_argument("--out", required=True)
    rp.add_argument("--task", action="append")
    rp.set_defaults(fn=cmd_report)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (tasks_mod.TaskError, MixedRunError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
