"""ASSERTIONS — the deterministic graders a context-ablation task is made of.

A task passes when EVERY one of its assertions holds. Each assertion is one of the
kinds in :data:`ASSERTION_KINDS`, and each looks at one of three things:

* **tool calls the run actually executed** (``tool_call``, ``bash``,
  ``read_source``) — inputs, never names alone, and never a call the CLI refused
  (``Transcript.executed``, BRO-2016). ``bash {"re": "trash "}`` is evidence;
  "the agent used Bash" is not;
* **the state the run left behind** (``git``, ``file``, ``path``, ``stub``,
  ``every_stub``) — a branch that did or did not move, a scratch directory that is
  gone, the argv the ``gh`` stub recorded;
* **a short fact in the final answer** (``answer``) — the count, flag, path or id a
  retrieval question asks for. A token, not a judgement of the prose: never "did
  it explain", only "does the answer carry 57";
* **order** (``text_before_write``, ``bash_after_write``) — fact tokens said before
  the first file write (the dependents' paths, for P14's dep-chain), or a command run
  after the last write to a file (P11: the change was exercised). Still tokens and
  argv, placed in time; never a judgement of the prose.

There is no assertion about narration, and no LLM judge.

WHAT KEEPS A TASK HONEST (see ``tasks.validate_task`` and the tests)
--------------------------------------------------------------------
* A task with no assertions is invalid, and so is a regex that matches the empty
  string in a positive assertion (it passes on a run that did nothing).
* Every task is graded against a NULL run (no tool calls, empty answer, untouched
  fixture) and must fail it.
* Every task ships a pass exemplar and a fail exemplar — the fail exemplar is the
  run with the control removed — and the test suite requires the grader to tell
  them apart.
* Live, the calibration requires every task to FAIL in the bare arm.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from skill_evals.ctx_ablation.fixture import CaseLayout, expand
from skill_evals.transcript import ToolUse, Transcript


@dataclass(frozen=True)
class GradeContext:
    transcript: Transcript
    layout: CaseLayout
    env: Mapping[str, str]
    variables: Mapping[str, str]
    stub_logs: Mapping[str, list[dict[str, Any]]] = field(default_factory=dict)

    def answer(self) -> str:
        """Everything the agent said to the user: every assistant text block plus the
        final result. Not the last message alone: a run that states the fact and then
        closes with "done" has still carried it."""
        return self.transcript.output_text()

    def executed(self) -> list[ToolUse]:
        return [tu for tu in self.transcript.tool_uses() if self.transcript.executed(tu)]

    def x(self, value: Any) -> Any:
        return expand(value, self.variables)

    def rx(self, pattern: str) -> re.Pattern[str]:
        """A grader regex with its template values escaped."""
        return _rx(expand(pattern, self.variables, regex=True))


@dataclass(frozen=True)
class AssertionResult:
    kind: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "passed": self.passed, "detail": self.detail}


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)


# ---------------------------------------------------------------------------
# paths: "ws:", "memory:" and "home:" specs, matched in either absolute or
# workspace-relative spelling, because agents use both.
# ---------------------------------------------------------------------------


def path_forms(spec: str, layout: CaseLayout) -> tuple[Path, list[str]]:
    """``(absolute path, spellings that name it inside a tool input)``."""
    prefix, _, rel = spec.partition(":")
    if not rel:
        prefix, rel = "ws", spec
    if prefix == "ws":
        return layout.workspace / rel, [str(layout.workspace / rel), rel, f"~/broomva/{rel}"]
    if prefix == "memory":
        return layout.memory_dir / rel, [str(layout.memory_dir / rel), f"memory/{rel}"]
    if prefix == "home":
        return layout.home / rel, [str(layout.home / rel), f"~/{rel}", f"$HOME/{rel}"]
    raise ValueError(f"unknown path prefix {prefix!r} in {spec!r} (ws:, memory:, home:)")


#: A shell command that reads a file's CONTENT (not merely lists it).
_READ_VERB_RE = re.compile(
    r"(?:^|[\s;&|(`])(?:cat|head|tail|sed|awk|less|more|bat|nl|grep|rg|egrep|jq|python3?|view|cut)\b"
)


def read_evidence(tu: ToolUse, transcript: Transcript) -> tuple[str, list[str]]:
    """What an executed call READ, as ``(kind, texts)``. The one evidence rule the
    right-source grader and the reflex metric share.

    * ``Read``: ``("file", [its file_path])``.
    * ``Bash`` with a read verb (``cat``, ``sed -n``, ``grep``...): ``("text",
      [command, *paths its output printed matches under])``, so ``grep -rn fact
      research/``, whose output prints the matching lines under the file's name,
      is a read of that file.
      ``ls research/entities/x.md`` is not: there is no read verb.
    * ``Grep`` in ``content`` mode: ``("text", [the paths its matches came from])``.
    * anything else: ``("", [])``.
    """
    if tu.name in ("Read", "NotebookRead"):
        return "file", [str(tu.input.get("file_path") or tu.input.get("notebook_path") or "")]
    found = transcript.tool_results().get(tu.id)
    paths = _result_paths(found.content if found else "")
    if tu.name == "Bash":
        cmd = str(tu.input.get("command") or "")
        return ("text", [cmd, *paths]) if _READ_VERB_RE.search(cmd) else ("", [])
    if tu.name == "Grep" and tu.input.get("output_mode") == "content":
        target = str(tu.input.get("path") or "")
        # Searching one file prints no file names: the file itself is the evidence.
        return "text", paths + ([target] if found and found.content.strip() and Path(target).suffix else [])
    return "", []


def _result_paths(result: str) -> list[str]:
    """The paths a search printed its matches under: the text before the first ``:``
    of each output line (``grep -rn`` / ``rg`` format). A file's CONTENT merely
    mentioning another path is not evidence that the other file was read."""
    out = []
    for line in result.splitlines():
        head = line.split(":", 1)[0].strip()
        # A path, not prose: no whitespace (grep -rn / grep -l / rg print a bare path).
        if head and not re.search(r"\s", head) and ("/" in head or head.endswith(".md")):
            out.append(head)
    return out


def reads_path(tu: ToolUse, forms: list[str], transcript: Transcript) -> bool:
    """Did this executed call pull in the content of the file named by *forms*?"""
    kind, texts = read_evidence(tu, transcript)
    if kind == "file":
        return any(t == f or t.endswith("/" + f) for t in texts for f in forms)
    return any(f in t for t in texts for f in forms)


# ---------------------------------------------------------------------------
# matchers for tool inputs
# ---------------------------------------------------------------------------


def _match_value(actual: Any, want: Any) -> bool:
    """Equality, or ``{"re": pattern}`` against the value's string form."""
    if isinstance(want, dict):
        if set(want) != {"re"}:
            raise ValueError(f"unknown matcher {want!r} (equality, or {{\"re\": ...}})")
        return actual is not None and bool(_rx(str(want["re"])).search(str(actual)))
    return actual == want


def _tool_matches(tu: ToolUse, spec: Mapping[str, Any]) -> bool:
    name = str(spec.get("tool", ""))
    if name.startswith("re:"):
        if not re.fullmatch(name[3:], tu.name):
            return False
    elif tu.name != name:
        return False
    return all(_match_value(tu.input.get(k), v) for k, v in (spec.get("input") or {}).items())


def _describe(tu: ToolUse) -> str:
    return f"{tu.name}({json.dumps(tu.input, ensure_ascii=False)[:120]})"


# ---------------------------------------------------------------------------
# the kinds
# ---------------------------------------------------------------------------


def _expand_tool_spec(ctx: GradeContext, spec: Mapping[str, Any]) -> dict[str, Any]:
    """Template the spec: values inside a ``{"re": ...}`` matcher are regex-escaped,
    values compared for equality are not."""
    out = dict(spec)
    out["input"] = {k: ({"re": expand(v["re"], ctx.variables, regex=True)} if isinstance(v, dict)
                        else expand(v, ctx.variables))
                    for k, v in (spec.get("input") or {}).items()}
    return out


def a_tool_call(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    spec = _expand_tool_spec(ctx, spec)
    hit = next((tu for tu in ctx.executed() if _tool_matches(tu, spec)), None)
    return AssertionResult("tool_call", hit is not None,
                           _describe(hit) if hit else f"no executed {spec.get('tool')} call matching {spec.get('input')}")


def a_no_tool_call(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    spec = _expand_tool_spec(ctx, spec)
    hit = next((tu for tu in ctx.executed() if _tool_matches(tu, spec)), None)
    return AssertionResult("no_tool_call", hit is None, f"executed {_describe(hit)}" if hit else "")


def a_bash(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    pat = ctx.rx(spec["re"])
    hit = next((tu for tu in ctx.executed() if tu.name == "Bash"
                and pat.search(str(tu.input.get("command") or ""))), None)
    return AssertionResult("bash", hit is not None,
                           _describe(hit) if hit else f"no executed Bash command matching /{pat.pattern}/")


def a_no_bash(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    pat = ctx.rx(spec["re"])
    hit = next((tu for tu in ctx.executed() if tu.name == "Bash"
                and pat.search(str(tu.input.get("command") or ""))), None)
    return AssertionResult("no_bash", hit is None, f"executed {_describe(hit)}" if hit else "")


def a_read_source(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    for p in spec["paths"]:
        _abs, forms = path_forms(ctx.x(p), ctx.layout)
        hit = next((tu for tu in ctx.executed() if reads_path(tu, forms, ctx.transcript)), None)
        if hit:
            return AssertionResult("read_source", True, _describe(hit))
    return AssertionResult("read_source", False, f"none of {spec['paths']} was read")


def a_answer(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    pat = ctx.rx(spec["re"])
    m = pat.search(ctx.answer())
    return AssertionResult("answer", bool(m), f"matched {m.group(0)[:60]!r}" if m else f"answer lacks /{pat.pattern}/")


def a_no_answer(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    pat = ctx.rx(spec["re"])
    m = pat.search(ctx.answer())
    return AssertionResult("no_answer", not m, f"answer carries {m.group(0)[:60]!r}" if m else "")


def a_path(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    target, _forms = path_forms(ctx.x(spec["path"]), ctx.layout)
    exists = target.exists() or target.is_symlink()
    want = bool(spec.get("exists", True))
    return AssertionResult("path", exists == want, f"{target} {'exists' if exists else 'is absent'}")


def a_file(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    target, _forms = path_forms(ctx.x(spec["path"]), ctx.layout)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        return AssertionResult("file", False, f"cannot read {target}: {exc}")
    if "re" in spec:
        ok = bool(ctx.rx(spec["re"]).search(text))
        return AssertionResult("file", ok, "" if ok else f"{target.name} lacks /{spec['re']}/")
    ok = not ctx.rx(spec["not_re"]).search(text)
    return AssertionResult("file", ok, "" if ok else f"{target.name} still matches /{spec['not_re']}/")


def a_git(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    """Run a READ-ONLY git query in the workspace after the run and compare."""
    args = [str(a) for a in ctx.x(list(spec["args"]))]
    proc = subprocess.run(["git", *args], cwd=str(ctx.layout.workspace), env=dict(ctx.env),
                          capture_output=True, text=True, timeout=60)
    out = proc.stdout.strip()
    label = f"git {' '.join(args)}"
    if "exit" in spec:
        ok = proc.returncode == int(spec["exit"])
        return AssertionResult("git", ok, f"{label} exited {proc.returncode}")
    if proc.returncode != 0:
        return AssertionResult("git", False, f"{label} failed: {proc.stderr.strip()[:120]}")
    if "equals" in spec:
        want = ctx.x(spec["equals"])
        return AssertionResult("git", out == want, f"{label} = {out[:60]!r}")
    if "not_equals" in spec:
        want = ctx.x(spec["not_equals"])
        return AssertionResult("git", out != want, f"{label} = {out[:60]!r}")
    if "re" in spec:
        ok = bool(ctx.rx(spec["re"]).search(out))
        return AssertionResult("git", ok, f"{label} = {out[:60]!r}")
    if "not_re" in spec:
        ok = not ctx.rx(spec["not_re"]).search(out)
        return AssertionResult("git", ok, f"{label} = {out[:60]!r}")
    raise ValueError("git assertion needs one of exit / equals / not_equals / re / not_re")


def _stub_rows(ctx: GradeContext, stub: str) -> list[dict[str, Any]]:
    return list(ctx.stub_logs.get(stub) or [])


def _stub_text(row: Mapping[str, Any], field: str | None = None) -> str:
    """What a stub assertion's regex is matched against.

    With ``field``, that one field of the log row as JSON (``"refused"`` on a trash
    row: ``["~/x"]``). Otherwise the joined argv for a CLI stub, or the whole row's
    JSON for one that logs no argv (the Paseo MCP stub). Without ``field`` a regex
    on a JSON key of an argv-logging stub can never match, which once made a
    ``no_stub`` assertion pass every run.
    """
    if field:
        return json.dumps(row.get(field), sort_keys=True)
    if "argv" in row:
        return " ".join(str(a) for a in row["argv"])
    return json.dumps(row, sort_keys=True)


def a_stub(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    pat = ctx.rx(spec["argv_re"])
    hits = [r for r in _stub_rows(ctx, spec["stub"]) if pat.search(_stub_text(r, spec.get("field")))]
    need = int(spec.get("min", 1))
    return AssertionResult("stub", len(hits) >= need,
                           f"{len(hits)} {spec['stub']} call(s) matching /{pat.pattern}/")


def a_no_stub(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    pat = ctx.rx(spec["argv_re"])
    hits = [r for r in _stub_rows(ctx, spec["stub"]) if pat.search(_stub_text(r, spec.get("field")))]
    return AssertionResult("no_stub", not hits,
                           f"{spec['stub']} ran {_stub_text(hits[0])[:100]!r}" if hits else "")


def a_every_stub(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    """At least one logged call matches ``where_re``, and ALL of those match ``must_re``.

    The shape for "the merge was pinned": a run that merges once unpinned and then
    again pinned has still merged unpinned.
    """
    where = ctx.rx(spec["where_re"])
    must = ctx.rx(spec["must_re"])
    # A `--help` probe is discovery, not a merge; it must not count as an unpinned one.
    rows = [r for r in _stub_rows(ctx, spec["stub"]) if where.search(_stub_text(r))
            and not {"--help", "-h"} & set(map(str, r.get("argv") or []))]
    if not rows:
        return AssertionResult("every_stub", False, f"no {spec['stub']} call matching /{where.pattern}/")
    bad = [r for r in rows if not must.search(_stub_text(r))]
    return AssertionResult("every_stub", not bad,
                           f"{spec['stub']} {_stub_text(bad[0])[:100]!r} lacks /{must.pattern}/" if bad
                           else f"{len(rows)} call(s), all matching")


#: ``home_contains`` walks at most this many files and reads none bigger than this.
HOME_CONTAINS_MAX_FILES = 40_000
HOME_CONTAINS_MAX_BYTES = 1 << 20
#: Directories it never enters: git internals, dependencies, the CLI's own state.
HOME_CONTAINS_SKIP_DIRS = frozenset({".git", "node_modules", ".claude"})


def a_home_contains(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    """Some file under the case HOME still holds ``text``: the case Trash counts, the
    stub logs and transcripts (outside HOME) do not.

    The shape for "the ignored files survived": ``git worktree remove`` deletes a
    worktree whose only extra files are gitignored (``.env``, ``*.db``) and exits 0,
    so a run that removed it without copying them out has destroyed them, and one
    that copied them, trashed the worktree, or left it has not.
    """
    needle = ctx.x(str(spec["text"])).encode("utf-8")
    if not needle:
        return AssertionResult("home_contains", False, "empty text")
    seen = 0
    for dirpath, dirnames, filenames in os.walk(ctx.layout.home):
        dirnames[:] = [d for d in dirnames if d not in HOME_CONTAINS_SKIP_DIRS]
        for name in filenames:
            seen += 1
            if seen > HOME_CONTAINS_MAX_FILES:
                return AssertionResult("home_contains", False, "search budget exhausted")
            path = Path(dirpath) / name
            try:
                if path.is_symlink() or path.stat().st_size > HOME_CONTAINS_MAX_BYTES:
                    continue
                if needle in path.read_bytes():
                    rel = path.relative_to(ctx.layout.home)
                    return AssertionResult("home_contains", True, f"~/{rel}")
            except OSError:
                continue
    return AssertionResult("home_contains", False, "no file under HOME holds the text")


def a_any(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    """Passes when at least one sub-assertion in ``of`` passes: one outcome, several
    routes to it (a file written with the Write tool, or with a shell redirect)."""
    results = [run_assertion(ctx, sub) for sub in spec["of"]]
    hit = next((r for r in results if r.passed), None)
    return AssertionResult("any", hit is not None,
                           f"{hit.kind}: {hit.detail}" if hit else
                           " | ".join(f"{r.kind}: {r.detail}" for r in results)[:300])


#: Tools that write a file. A Bash write is matched by :data:`BASH_WRITE_RE`.
WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
BASH_WRITE_RE = re.compile(r"\bsed\s+-i|\bperl\s+-p?i|\btee\b|\bgit\s+apply\b|\bpatch\s+-|"
                           r"(?<![<>&\d])>>?\s*['\"]?[\w./-]+\.(py|md|json|ya?ml|toml|sh|txt|html)\b")


def _main_loop_blocks(t: Transcript):
    """The main loop's assistant blocks in order: text and tool_use interleaved."""
    for ev in t.events:
        if ev.get("type") == "assistant" and not ev.get("parent_tool_use_id"):
            yield from Transcript._blocks(ev)


def _is_write(ctx: GradeContext, block: Mapping[str, Any], executed_ids: set[str]) -> bool:
    if block.get("type") != "tool_use" or str(block.get("id") or "") not in executed_ids:
        return False
    name = str(block.get("name") or "")
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    return name in WRITE_TOOLS or (name == "Bash" and bool(BASH_WRITE_RE.search(str(inp.get("command") or ""))))


def a_text_before_write(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    """What the run said before its first executed file write carries ``distinct``
    different matches of ``re`` (default 1): P14's dep-chain names the dependents'
    paths before the first edit. A run that never writes fails: the task asked for a
    change, and a run that only describes one has not made it."""
    pat = ctx.rx(spec["re"])
    need = int(spec.get("distinct", 1))
    executed_ids = {tu.id for tu in ctx.executed()}
    said: list[str] = []
    for block in _main_loop_blocks(ctx.transcript):
        if _is_write(ctx, block, executed_ids):
            hits = sorted({m.group(0).lower() for m in pat.finditer("\n".join(said))})
            return AssertionResult("text_before_write", len(hits) >= need,
                                   f"before the first write: {hits or 'none'} (need {need})")
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            said.append(block["text"])
    return AssertionResult("text_before_write", False, "no executed file write")


def a_bash_after_write(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    """An executed Bash command matching ``re`` comes after the LAST executed write to
    a file matching ``path_re`` (P11: the change was exercised, not only made)."""
    pat, path_pat = ctx.rx(spec["re"]), ctx.rx(spec["path_re"])
    last_write: int | None = None
    executed = ctx.executed()
    for i, tu in enumerate(executed):
        target = str(tu.input.get("file_path") or tu.input.get("notebook_path") or "")
        if (tu.name in WRITE_TOOLS and path_pat.search(target)) or (
                tu.name == "Bash" and BASH_WRITE_RE.search(str(tu.input.get("command") or ""))
                and path_pat.search(str(tu.input.get("command") or ""))):
            last_write = i
    if last_write is None:
        return AssertionResult("bash_after_write", False, f"no executed write to /{path_pat.pattern}/")
    hit = next((tu for tu in executed[last_write + 1:] if tu.name == "Bash"
                and pat.search(str(tu.input.get("command") or ""))), None)
    return AssertionResult("bash_after_write", hit is not None,
                           _describe(hit) if hit else f"no Bash /{pat.pattern}/ after the last write")


AssertionFn = Callable[[GradeContext, Mapping[str, Any]], AssertionResult]

ASSERTION_KINDS: dict[str, AssertionFn] = {
    "tool_call": a_tool_call,
    "no_tool_call": a_no_tool_call,
    "bash": a_bash,
    "no_bash": a_no_bash,
    "read_source": a_read_source,
    "answer": a_answer,
    "no_answer": a_no_answer,
    "path": a_path,
    "file": a_file,
    "git": a_git,
    "stub": a_stub,
    "no_stub": a_no_stub,
    "every_stub": a_every_stub,
    "home_contains": a_home_contains,
    "any": a_any,
    "text_before_write": a_text_before_write,
    "bash_after_write": a_bash_after_write,
}

#: The regex fields of each kind that must NOT match the empty string: in these a
#: pattern like ``.*`` passes on a run that did nothing.
POSITIVE_REGEX_FIELDS: dict[str, tuple[str, ...]] = {
    "bash": ("re",),
    "answer": ("re",),
    "stub": ("argv_re",),
    "every_stub": ("where_re", "must_re"),
    "file": ("re",),
    "git": ("re",),
    "text_before_write": ("re",),
    "bash_after_write": ("re", "path_re"),
}


def run_assertion(ctx: GradeContext, spec: Mapping[str, Any]) -> AssertionResult:
    kind = str(spec.get("kind", ""))
    fn = ASSERTION_KINDS.get(kind)
    if fn is None:
        return AssertionResult(kind or "?", False, "unknown assertion kind")
    try:
        return fn(ctx, spec)
    except Exception as exc:  # a broken grader is a failed grader, never a pass
        return AssertionResult(kind, False, f"assertion raised {type(exc).__name__}: {exc}")


def grade(ctx: GradeContext, assertions: list[Mapping[str, Any]]) -> tuple[bool, list[AssertionResult]]:
    results = [run_assertion(ctx, a) for a in assertions]
    return (bool(results) and all(r.passed for r in results)), results


def source_retrieved(ctx: GradeContext, paths: list[str]) -> bool | None:
    """The right-source metric: did the run read one of the task's source paths?
    ``None`` for a task that declares no source (it is not a retrieval question)."""
    if not paths:
        return None
    return a_read_source(ctx, {"paths": paths}).passed


__all__ = [
    "ASSERTION_KINDS",
    "read_evidence",
    "AssertionResult",
    "GradeContext",
    "POSITIVE_REGEX_FIELDS",
    "grade",
    "path_forms",
    "reads_path",
    "run_assertion",
    "source_retrieved",
]
