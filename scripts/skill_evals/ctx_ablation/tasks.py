"""The task file: schema, validation, and the synthetic runs that keep graders honest.

A task file is ``{"version": 1, "notes": ..., "tasks": [...]}``. One task::

    {
      "id": "reflex-list-agents-fleet-count",
      "class": "reflex",                       # retrieval | reflex | coordination | harm
      "prompt": "how many paseo agents ...",   # a real turn, or the closest real one
      "origin": {"kind": "memory-feedback", "ref": "paseo-sidebar-lists-...md"},
      "targets": ["memory"],                   # the injection expected to carry what it needs
      "rationale": "why a bare session fails it",
      "fixture": {"files": {...}, "setup": [...], "stubs": {...},
                  "ctx_peers": [...], "vars": {...}},
      "source_paths": ["memory:paseo-sidebar-...md"],   # the right-source metric
      "assertions": [{"kind": "tool_call", ...}, ...],  # ALL must hold
      "exemplars": {"pass": {...}, "fail": {...}}       # the fail one = control removed
    }

VACUITY, CLOSED THREE WAYS BEFORE A TRIAL IS PAID FOR
-----------------------------------------------------
1. :func:`validate_task` (static): no assertions, an unknown kind, a positive regex
   that matches the empty string, or an ``answer`` regex that matches the PROMPT
   (the answer could parrot the question) is an error.
2. :func:`null_run` (fixture): the task graded against a run that did nothing must
   fail. A task made only of "did not do X" assertions passes an idle run; this
   catches it whatever the assertion mix.
3. :func:`run_exemplar` (fixture): the pass exemplar must pass and the fail exemplar
   must fail. The fail exemplar is the control removed: the naive run a session
   without the injection is expected to make. A grader that cannot tell those two
   apart measures nothing, and the test suite runs this for every committed task.

The fourth, the live one, is calibration (``run.py calibrate``): every task must
fail in the bare arm or it is dropped.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from skill_evals.ctx_ablation import graders as g
from skill_evals.ctx_ablation.fixture import Case, Corpus, build_case, expand, read_stub_logs
from skill_evals.ctx_ablation.stubs import guard as guard_mod
from skill_evals.transcript import REFUSAL_MARKER, Transcript

TASKS_VERSION = 1
TASK_CLASSES = ("retrieval", "reflex", "coordination", "harm")
TARGETS = ("memory", "rolex", "ctx", "s1")
#: Where a task comes from: a real session turn, a memory feedback file, a
#: knowledge-graph entity, a spec, or a role-x lens rule (its quality bar).
ORIGIN_KINDS = ("real-trace", "memory-feedback", "kg-entity", "spec", "lens")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")

#: Parameters each assertion kind requires.
REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "tool_call": ("tool",),
    "no_tool_call": ("tool",),
    "bash": ("re",),
    "no_bash": ("re",),
    "read_source": ("paths",),
    "answer": ("re",),
    "no_answer": ("re",),
    "path": ("path",),
    "file": ("path",),
    "git": ("args",),
    "stub": ("stub", "argv_re"),
    "no_stub": ("stub", "argv_re"),
    "every_stub": ("stub", "where_re", "must_re"),
    "home_contains": ("text",),
    "any": ("of",),
    "text_before_write": ("re",),
    "bash_after_write": ("re", "path_re"),
}


class TaskError(ValueError):
    """The task file is malformed, or a task cannot be graded honestly."""


@dataclass(frozen=True)
class Task:
    id: str
    cls: str
    prompt: str
    assertions: list[dict[str, Any]]
    fixture: dict[str, Any] = field(default_factory=dict)
    source_paths: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    origin: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    exemplars: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "class": self.cls, "targets": list(self.targets),
                "origin": dict(self.origin), "source_paths": list(self.source_paths)}


# ---------------------------------------------------------------------------
# static validation
# ---------------------------------------------------------------------------


def _regex_fields(kind: str, spec: Mapping[str, Any]) -> list[tuple[str, str]]:
    names = ["re", "not_re", "argv_re", "where_re", "must_re", "path_re"]
    out = [(n, spec[n]) for n in names if isinstance(spec.get(n), str)]
    for key, want in (spec.get("input") or {}).items():
        if isinstance(want, dict) and isinstance(want.get("re"), str):
            out.append((f"input.{key}.re", want["re"]))
    return out


def _validate_assertions(assertions: list[Any], where: str, prompt: str) -> list[str]:
    errors: list[str] = []
    for i, spec in enumerate(assertions):
        at = f"{where} assertions[{i}]"
        if not isinstance(spec, dict):
            errors.append(f"{at}: must be an object")
            continue
        kind = spec.get("kind")
        if kind not in g.ASSERTION_KINDS:
            errors.append(f"{at}: unknown kind {kind!r}")
            continue
        for param in REQUIRED_PARAMS[kind]:
            if param not in spec:
                errors.append(f"{at}: {kind} needs {param!r}")
        if kind == "any":
            subs = spec.get("of")
            if not isinstance(subs, list) or len(subs) < 2:
                errors.append(f"{at}: any needs 'of': a list of two or more assertions")
            else:
                errors += _validate_assertions(subs, at, prompt)
            continue
        for name, pattern in _regex_fields(kind, spec):
            probe = re.sub(r"\$\{[^}]+\}", "X", pattern)
            try:
                compiled = re.compile(probe, re.IGNORECASE | re.MULTILINE)
            except re.error as exc:
                errors.append(f"{at}: {name} does not compile: {exc}")
                continue
            if name in g.POSITIVE_REGEX_FIELDS.get(kind, ()) and compiled.search(""):
                errors.append(f"{at}: {name} /{pattern}/ matches the empty string, so it "
                              "passes a run that did nothing")
            if kind == "answer" and prompt and compiled.search(prompt):
                errors.append(f"{at}: answer /{pattern}/ matches the PROMPT — an answer that "
                              "repeats the question would pass")
        for p in spec.get("paths", []) if kind == "read_source" else []:
            if not isinstance(p, str) or p.partition(":")[0] not in ("ws", "memory", "home"):
                errors.append(f"{at}: path {p!r} needs a ws:, memory: or home: prefix")

    return errors


def validate_task(raw: Any) -> list[str]:
    """Errors for one raw task object (empty list = valid)."""
    if not isinstance(raw, dict):
        return ["task must be an object"]
    tid = raw.get("id")
    where = f"task {tid!r}" if isinstance(tid, str) else "task"
    errors: list[str] = []
    if not isinstance(tid, str) or not _ID_RE.match(tid):
        errors.append(f"{where}: 'id' must match {_ID_RE.pattern}")
    if raw.get("class") not in TASK_CLASSES:
        errors.append(f"{where}: 'class' must be one of {TASK_CLASSES}")
    prompt = raw.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        errors.append(f"{where}: 'prompt' must be a non-empty string")
        prompt = ""
    origin = raw.get("origin")
    if not isinstance(origin, dict) or origin.get("kind") not in ORIGIN_KINDS or not origin.get("ref"):
        errors.append(f"{where}: 'origin' needs kind in {ORIGIN_KINDS} and a ref")
    targets = raw.get("targets")
    if not isinstance(targets, list) or not targets or any(t not in TARGETS for t in targets):
        errors.append(f"{where}: 'targets' must be a non-empty subset of {TARGETS}")
    if not str(raw.get("rationale") or "").strip():
        errors.append(f"{where}: 'rationale' (why a bare session fails it) is required")

    assertions = raw.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        errors.append(f"{where}: 'assertions' must be a non-empty list — a task that asserts "
                      "nothing passes every run")
        assertions = []
    errors += _validate_assertions(assertions, where, prompt)
    src = raw.get("source_paths", [])
    if not isinstance(src, list) or any(
        not isinstance(p, str) or p.partition(":")[0] not in ("ws", "memory", "home") for p in src
    ):
        errors.append(f"{where}: 'source_paths' must be ws:/memory:/home: path specs")
    if raw.get("class") == "retrieval" and not src:
        errors.append(f"{where}: a retrieval task must name its source_paths")
    fixture = raw.get("fixture", {})
    if not isinstance(fixture, dict):
        errors.append(f"{where}: 'fixture' must be an object")
        fixture = {}
    if raw.get("class") == "coordination" and not fixture.get("ctx_peers"):
        errors.append(f"{where}: a coordination task needs fixture.ctx_peers (the peer to notice)")
    ex = raw.get("exemplars")
    if not isinstance(ex, dict) or not isinstance(ex.get("pass"), dict) or not isinstance(ex.get("fail"), dict):
        errors.append(f"{where}: 'exemplars' needs a 'pass' and a 'fail' run (the fail run is the "
                      "control removed)")
    return errors


def parse_task(raw: dict[str, Any]) -> Task:
    return Task(
        id=raw["id"], cls=raw["class"], prompt=raw["prompt"],
        assertions=list(raw["assertions"]), fixture=dict(raw.get("fixture") or {}),
        source_paths=list(raw.get("source_paths") or []), targets=list(raw.get("targets") or []),
        origin=dict(raw.get("origin") or {}), rationale=str(raw.get("rationale") or ""),
        exemplars=dict(raw.get("exemplars") or {}),
    )


def load_tasks(path: Path) -> tuple[list[Task], dict[str, Any]]:
    """Parse and validate a task file. Raises :class:`TaskError` listing every error."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TaskError(f"cannot read task file {path}: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("version") != TASKS_VERSION:
        raise TaskError(f"task file must be an object with version {TASKS_VERSION}")
    raw_tasks = doc.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise TaskError("'tasks' must be a non-empty list")
    errors: list[str] = []
    seen: set[str] = set()
    for raw in raw_tasks:
        errors += validate_task(raw)
        tid = raw.get("id") if isinstance(raw, dict) else None
        if tid in seen:
            errors.append(f"duplicate task id {tid!r}")
        seen.add(tid)
    if errors:
        raise TaskError("; ".join(errors))
    return [parse_task(r) for r in raw_tasks], doc


# ---------------------------------------------------------------------------
# synthetic runs: the null run and the exemplars
# ---------------------------------------------------------------------------


def synthetic_transcript(calls: list[dict[str, Any]], answer: str, cwd: str) -> Transcript:
    """A stream-json transcript with the shape the CLI emits, for grading offline."""
    events: list[dict[str, Any]] = [{"type": "system", "subtype": "init", "cwd": cwd, "skills": []}]
    for i, call in enumerate(calls):
        if "say" in call:  # assistant text between tool calls (``text_before_write``)
            events.append({"type": "assistant", "message": {"content": [{"type": "text", "text": call["say"]}]}})
            continue
        tid = f"toolu_synthetic_{i:03d}"
        events.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tid, "name": call["name"], "input": call.get("input", {})}]}})
        content = str(call.get("output", ""))
        if call.get("refused"):
            content = f"{REFUSAL_MARKER}{content}</tool_use_error>"
        events.append({"type": "user", "message": {"content": [{
            "type": "tool_result", "tool_use_id": tid, "content": content,
            "is_error": bool(call.get("refused") or call.get("is_error")),
        }]}})
    if answer:
        events.append({"type": "assistant", "message": {"content": [{"type": "text", "text": answer}]}})
    events.append({"type": "result", "subtype": "success", "is_error": False, "result": answer})
    return Transcript(events=events)


def _perform(case: Case, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Carry out an exemplar's actions in the case and return them as tool calls.

    ``bash`` actions really run, in the workspace with the case env, so the stubs
    log and git state moves exactly as they would live. Each passes through the
    case guard's own decision first: a blocked command is recorded as refused and
    not run, and a rewritten one runs rewritten while the recorded input keeps the
    command as written, which is what the live transcript shows. Other tools are
    recorded only.
    """
    calls: list[dict[str, Any]] = []
    for action in actions:
        if "say" in action:
            calls.append({"say": expand(str(action["say"]), case.variables)})
            continue
        if "mcp" in action:
            calls.append(_call_mcp(case, action))
            continue
        if "bash" in action:
            cmd = expand(action["bash"], case.variables)
            decision = guard_mod.decide("Bash", {"command": cmd}, real_home=str(Path.home()),
                                        local_bin=str(case.layout.local_bin)) or {}
            if decision.get("decision") == "block":
                calls.append({"name": "Bash", "input": {"command": cmd}, "refused": True,
                              "output": decision["reason"]})
                continue
            run_cmd = ((decision.get("hookSpecificOutput") or {}).get("updatedInput") or {}).get("command", cmd)
            # Defence in depth: whatever the guard decided, this executor never runs a
            # real stubbed binary. A mutation proof that neutered the guard's rewrite
            # once ran the real /usr/bin/trash from a test, into the operator's Trash.
            if guard_mod.real_binary_re(str(Path.home())).search(run_cmd):
                calls.append({"name": "Bash", "input": {"command": cmd}, "refused": True,
                              "output": "synthetic executor: a real stubbed binary, not run"})
                continue
            proc = subprocess.run(["/bin/sh", "-c", run_cmd], cwd=str(case.layout.workspace),
                                  env=dict(case.env), capture_output=True, text=True, timeout=120)
            calls.append({"name": "Bash", "input": {"command": cmd},
                          "output": (proc.stdout + proc.stderr)[-4000:], "is_error": proc.returncode != 0})
        else:
            calls.append({"name": action["tool"], "input": expand(action.get("input", {}), case.variables),
                          "output": expand(str(action.get("output", "")), case.variables)})
    return calls


def _call_mcp(case: Case, action: dict[str, Any]) -> dict[str, Any]:
    """Call the case's MCP stub for real (JSON-RPC over stdio), so its log is written
    exactly as it is when the CLI calls it. Only the ``paseo`` server exists."""
    if action["mcp"] != "paseo":
        raise TaskError(f"no MCP stub named {action['mcp']!r}")
    args = expand(action.get("arguments", {}), case.variables)
    stub = Path(__file__).resolve().parent / "stubs" / "paseo_mcp.py"
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": action["tool"], "arguments": args}},
    ]
    proc = subprocess.run([sys.executable, "-I", str(stub)], cwd=str(case.layout.workspace),
                          env={**case.env, "CTXABL_CASE_ROOT": str(case.layout.root)},
                          input="".join(json.dumps(x) + "\n" for x in lines),
                          capture_output=True, text=True, timeout=60)
    replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    content = next((r["result"]["content"][0]["text"] for r in replies if r.get("id") == 2 and "result" in r), "")
    return {"name": f"mcp__paseo__{action['tool']}", "input": args, "output": content}


def grade_synthetic(task: Task, case: Case, calls: list[dict[str, Any]], answer: str
                    ) -> tuple[bool, list[g.AssertionResult]]:
    transcript = synthetic_transcript(calls, expand(answer, case.variables), str(case.layout.workspace))
    ctx = g.GradeContext(transcript=transcript, layout=case.layout, env=case.env,
                         variables=case.variables, stub_logs=read_stub_logs(case.layout))
    return g.grade(ctx, task.assertions)


def null_run(task: Task, corpus: Corpus, root: Path) -> tuple[bool, list[g.AssertionResult]]:
    """Grade a run that did nothing. A sound task FAILS this."""
    case = build_case(root, task.fixture, corpus, link_auth=False)
    return grade_synthetic(task, case, [], "")


def run_exemplar(task: Task, which: str, corpus: Corpus, root: Path) -> tuple[bool, list[g.AssertionResult]]:
    ex = task.exemplars[which]
    case = build_case(root, task.fixture, corpus, link_auth=False)
    calls = _perform(case, list(ex.get("actions") or []))
    return grade_synthetic(task, case, calls, str(ex.get("answer", "")))


__all__ = [
    "TASK_CLASSES",
    "Task",
    "TaskError",
    "grade_synthetic",
    "load_tasks",
    "null_run",
    "parse_task",
    "run_exemplar",
    "synthetic_transcript",
    "validate_task",
]
