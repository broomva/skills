"""Per-trial measurements and the per-arm table.

TOKENS, AND WHAT "INJECTED" MEANS HERE
--------------------------------------
Two numbers per trial come from the stream-json ``usage`` records:

* ``context_tokens`` — the FIRST model call's input (``input_tokens`` +
  ``cache_creation_input_tokens`` + ``cache_read_input_tokens``). It is the whole
  prompt at turn one: system prompt, tools, memory, hook context and the user turn.
  For a given task it differs between arms only by what the arm injected.
* ``total_input_tokens`` — the same three fields from the ``result`` event, summed
  over every call in the run. What the run cost in input, however long it went on.

``injected_tokens`` for an arm is the mean, over tasks, of its ``context_tokens``
minus the bare arm's for the same task. Measured, not estimated from characters:
it includes the CLI's own auto-memory instructions (~3.2k tokens on CLI 2.1.280,
before a single line of MEMORY.md), which a character count of the index misses.
Without a bare arm in the run it is not computed; it is never defaulted to zero.

THE HEADLINE
------------
``lift`` is the arm's pass rate minus bare's, with a Newcombe 95% interval.
``lift_per_1k`` is that lift per 1,000 injected tokens: what each thousand tokens of
context buys. ``pass_per_1k`` is the raw pass rate per 1,000 injected tokens.

The intervals treat trials as independent. They are not: trials of one task are
correlated, so the true uncertainty is wider than printed, and the per-task table
is the thing to read before trusting a lift.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from skill_evals import ablation as ablation_mod
from skill_evals.ctx_ablation import graders as g
from skill_evals.transcript import Transcript

PASS = "PASS"
FAIL = "FAIL"
#: The CLI failed, timed out, or produced no result: no signal.
ERROR = "ERROR"
#: The arm claims an injection the trial never received. Scored as nothing, never
#: as a pass or fail of the injection: a role-x arm whose hook silently printed
#: nothing IS the bare arm, and counting it would report "role-x adds nothing".
INJECTION_MISSING = "INJECTION_MISSING"
#: An injection arrived that the arm does not include (a leak into the control).
LEAKED = "LEAKED"
NON_OUTCOMES = frozenset({ERROR, INJECTION_MISSING, LEAKED})

_ENTITY_RE = re.compile(r"\[(research/entities/[^\]\s]+\.md)")


def _usage_sum(usage: Mapping[str, Any] | None) -> int | None:
    if not isinstance(usage, Mapping):
        return None
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    vals = [usage.get(k) for k in keys]
    if all(v is None for v in vals):
        return None
    return int(sum(int(v or 0) for v in vals))


def context_tokens(t: Transcript) -> int | None:
    for ev in t.events:
        if ev.get("type") == "assistant" and not ev.get("parent_tool_use_id"):
            msg = ev.get("message") or {}
            return _usage_sum(msg.get("usage"))
    return None


def result_usage(t: Transcript) -> dict[str, int | None]:
    res = t.result_event or {}
    usage = res.get("usage") if isinstance(res.get("usage"), Mapping) else {}
    return {
        "total_input_tokens": _usage_sum(usage),
        "output_tokens": int(usage["output_tokens"]) if isinstance(usage.get("output_tokens"), int) else None,
    }


def hook_outputs(t: Transcript) -> list[dict[str, Any]]:
    """SessionStart hook responses as the stream reports them.

    UserPromptSubmit output is NOT in the stream (measured on CLI 2.1.280), which is
    why role-x delivery is proven from its own intake log instead; see run.py.
    """
    out = []
    for ev in t.events:
        if ev.get("type") == "system" and ev.get("subtype") == "hook_response":
            text = str(ev.get("output") or ev.get("stdout") or "")
            try:  # a JSON hook's context is its additionalContext, not the wrapper
                text = json.loads(text)["hookSpecificOutput"]["additionalContext"]
            except (ValueError, KeyError, TypeError):
                pass
            out.append({"event": ev.get("hook_event"), "name": ev.get("hook_name"),
                        "exit_code": ev.get("exit_code"), "chars": len(text), "text": text})
    return out


def rate_limit_utilization(t: Transcript) -> float | None:
    best = None
    for ev in t.events:
        if ev.get("type") != "rate_limit_event":
            continue
        info = ev.get("rate_limit_info") or {}
        for window in (info.get("unifiedWindows") or {}).values():
            u = window.get("utilization") if isinstance(window, Mapping) else None
            if isinstance(u, (int, float)):
                best = u if best is None else max(best, u)
    return best


def _read_under(ctx: g.GradeContext, needles: Sequence[str]) -> bool:
    """Did the run READ something whose path contains one of *needles*? The same
    evidence rule as ``graders.reads_path``: a Read, a Bash read verb naming it, or a
    content-mode Grep. Listing (``ls``, Glob) and writing are not reading."""
    for tu in ctx.executed():
        if tu.name in ("Read", "NotebookRead"):
            target = str(tu.input.get("file_path") or tu.input.get("notebook_path") or "")
            if any(n in target for n in needles):
                return True
        elif tu.name == "Bash":
            cmd = str(tu.input.get("command") or "")
            if g._READ_VERB_RE.search(cmd) and any(n in cmd for n in needles):
                return True
        elif tu.name == "Grep" and tu.input.get("output_mode") == "content":
            if any(n in str(tu.input.get("path") or "") for n in needles):
                return True
    return False


def reflexes(ctx: g.GradeContext) -> dict[str, bool]:
    """Which retrieval channels the run reached for, from executed tool calls."""
    names = {tu.name for tu in ctx.executed()}
    return {
        "kg": _read_under(ctx, ["research/entities"]),
        "docs": _read_under(ctx, ["docs/"]),
        "memory": _read_under(ctx, [str(ctx.layout.memory_dir), "/.claude/projects/"]),
        "web": bool(names & {"WebFetch", "WebSearch"}),
        "subagent": bool(names & {"Task", "Agent"}),
    }


def injected_entities(rolex_text: str) -> list[str]:
    return sorted(set(_ENTITY_RE.findall(rolex_text or "")))


def entities_opened(ctx: g.GradeContext, entities: Iterable[str]) -> list[str]:
    opened = []
    for rel in entities:
        _abs, forms = g.path_forms(f"ws:{rel}", ctx.layout)
        if any(g.reads_path(tu, forms, ctx.transcript) for tu in ctx.executed()):
            opened.append(rel)
    return opened


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


def _mean(xs: Sequence[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def wilson(passes: int, n: int) -> list[float] | None:
    if n <= 0:
        return None
    lo, hi = ablation_mod.wilson_interval(passes, n)
    return [round(lo, 4), round(hi, 4)]


@dataclass
class ArmRow:
    arm: str
    trials: int
    graded: int
    passes: int
    non_outcomes: dict[str, int]
    pass_rate: float | None
    pass_ci: list[float] | None
    context_tokens: float | None
    total_input_tokens: float | None
    output_tokens: float | None
    injected_tokens: float | None
    injected_chars: float | None
    tool_calls: float | None
    source_rate: float | None
    source_n: int
    wall_s: float | None
    cost_usd: float | None
    reflex_rates: dict[str, float | None]
    entities_injected: int
    entities_opened: int
    lift: float | None = None
    lift_ci: list[float] | None = None
    lift_per_1k: float | None = None
    #: The lift interval divided by the (measured, near-constant) injected thousands.
    lift_per_1k_ci: list[float] | None = None
    pass_per_1k: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def aggregate(results: Sequence[Mapping[str, Any]], arm_order: Sequence[str]) -> list[ArmRow]:
    """One row per arm, over every recorded trial of it."""
    by_arm: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in results:
        by_arm[r["arm"]].append(r)
    # Per-task mean context tokens in bare: the reference each arm's injection is
    # measured against.
    bare_ctx: dict[str, float] = {}
    for task, rows in _group(by_arm.get("bare", []), "task").items():
        m = _mean([r.get("context_tokens") for r in rows])
        if m is not None:
            bare_ctx[task] = m

    rows_out: list[ArmRow] = []
    for arm in [a for a in arm_order if a in by_arm] + sorted(set(by_arm) - set(arm_order)):
        rs = by_arm[arm]
        graded = [r for r in rs if r["outcome"] not in NON_OUTCOMES]
        passes = sum(1 for r in graded if r["outcome"] == PASS)
        non = defaultdict(int)
        for r in rs:
            if r["outcome"] in NON_OUTCOMES:
                non[r["outcome"]] += 1
        injected = None
        if bare_ctx:
            deltas = []
            for task, trs in _group(graded, "task").items():
                m = _mean([t.get("context_tokens") for t in trs])
                if m is not None and task in bare_ctx:
                    deltas.append(m - bare_ctx[task])
            injected = _mean(deltas) if arm != "bare" else 0.0
        src = [r["source_retrieved"] for r in graded if r.get("source_retrieved") is not None]
        reflex_keys = ("kg", "docs", "memory", "web", "subagent")
        rows_out.append(ArmRow(
            arm=arm,
            trials=len(rs),
            graded=len(graded),
            passes=passes,
            non_outcomes=dict(non),
            pass_rate=(passes / len(graded)) if graded else None,
            pass_ci=wilson(passes, len(graded)),
            context_tokens=_mean([r.get("context_tokens") for r in graded]),
            total_input_tokens=_mean([r.get("total_input_tokens") for r in graded]),
            output_tokens=_mean([r.get("output_tokens") for r in graded]),
            injected_tokens=injected,
            injected_chars=_mean([r.get("injected_chars") for r in graded]),
            tool_calls=_mean([r.get("tool_calls") for r in graded]),
            source_rate=(sum(src) / len(src)) if src else None,
            source_n=len(src),
            wall_s=_mean([(r.get("wall_ms") or 0) / 1000 for r in graded if r.get("wall_ms") is not None]),
            cost_usd=_mean([r.get("cost_usd") for r in graded]),
            reflex_rates={k: round(sum(1 for r in graded if (r.get("reflexes") or {}).get(k)) / len(graded), 4)
                          if graded else None for k in reflex_keys},
            entities_injected=sum(len(r.get("entities_injected") or []) for r in graded),
            entities_opened=sum(len(r.get("entities_opened") or []) for r in graded),
        ))
    bare = next((r for r in rows_out if r.arm == "bare"), None)
    for row in rows_out:
        if bare is None or row.arm == "bare" or row.pass_rate is None or bare.pass_rate is None:
            continue
        row.lift = round(row.pass_rate - bare.pass_rate, 4)
        lo, hi = ablation_mod.newcombe_difference(row.passes, row.graded, bare.passes, bare.graded)
        row.lift_ci = [round(lo, 4), round(hi, 4)]
        if row.injected_tokens and row.injected_tokens > 0:
            k = row.injected_tokens / 1000.0
            row.lift_per_1k = round(row.lift / k, 4)
            row.lift_per_1k_ci = [round(lo / k, 4), round(hi / k, 4)]
            row.pass_per_1k = round(row.pass_rate / k, 4)
    return rows_out


def _group(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        out[str(r.get(key))].append(r)
    return out


def task_matrix(results: Sequence[Mapping[str, Any]], arm_order: Sequence[str]) -> dict[str, dict[str, str]]:
    """``{task: {arm: "passes/graded"}}`` — the table to read before any aggregate."""
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for (task, arm), rows in _group2(results).items():
        graded = [r for r in rows if r["outcome"] not in NON_OUTCOMES]
        passes = sum(1 for r in graded if r["outcome"] == PASS)
        cell = f"{passes}/{len(graded)}"
        if len(graded) < len(rows):
            cell += f" ({len(rows) - len(graded)} void)"
        out[task][arm] = cell
    return {t: {a: out[t].get(a, "-") for a in arm_order} for t in sorted(out)}


def _group2(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    out: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        out[(str(r["task"]), str(r["arm"]))].append(r)
    return out


def _f(v: float | None, fmt: str = "{:.2f}") -> str:
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else fmt.format(v)


def format_table(rows: Sequence[ArmRow]) -> str:
    """The per-arm table, as GitHub markdown."""
    head = ("| arm | pass | 95% CI | lift vs bare (95% CI) | injected tok | lift / 1k tok (95% CI) | "
            "pass / 1k tok | ctx tok (turn 1) | input tok (run) | tool calls | right source | wall s |")
    lines = [head, "|" + "---|" * 12]
    for r in rows:
        ci = f"[{r.pass_ci[0]:.2f}, {r.pass_ci[1]:.2f}]" if r.pass_ci else "n/a"
        lift = "—" if r.arm == "bare" else (
            f"{r.lift:+.2f} [{r.lift_ci[0]:+.2f}, {r.lift_ci[1]:+.2f}]" if r.lift is not None else "n/a")
        src = f"{r.source_rate:.2f} (n={r.source_n})" if r.source_rate is not None else "n/a"
        void = f" +{sum(r.non_outcomes.values())} void" if r.non_outcomes else ""
        per1k = (f"{r.lift_per_1k:+.3f} [{r.lift_per_1k_ci[0]:+.2f}, {r.lift_per_1k_ci[1]:+.2f}]"
                 if r.lift_per_1k is not None and r.lift_per_1k_ci else "n/a")
        lines.append(
            f"| {r.arm} | {r.passes}/{r.graded}{void} ({_f(r.pass_rate)}) | {ci} | {lift} | "
            f"{_f(r.injected_tokens, '{:,.0f}')} | {per1k} | {_f(r.pass_per_1k, '{:.3f}')} | "
            f"{_f(r.context_tokens, '{:,.0f}')} | {_f(r.total_input_tokens, '{:,.0f}')} | "
            f"{_f(r.tool_calls, '{:.1f}')} | {src} | {_f(r.wall_s, '{:.0f}')} |"
        )
    return "\n".join(lines)


def format_matrix(matrix: Mapping[str, Mapping[str, str]], arm_order: Sequence[str]) -> str:
    lines = ["| task | " + " | ".join(arm_order) + " |", "|" + "---|" * (len(arm_order) + 1)]
    for task, cells in matrix.items():
        lines.append(f"| {task} | " + " | ".join(cells.get(a, "-") for a in arm_order) + " |")
    return "\n".join(lines)


def format_reflexes(rows: Sequence[ArmRow]) -> str:
    lines = ["| arm | read KG | read docs | read memory | web | subagent | role-x entities opened |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        rr = r.reflex_rates
        opened = (f"{r.entities_opened}/{r.entities_injected} ({r.entities_opened / r.entities_injected:.1%})"
                  if r.entities_injected else "—")
        cells = " | ".join(_f(rr[k]) for k in ("kg", "docs", "memory", "web", "subagent"))
        lines.append(f"| {r.arm} | {cells} | {opened} |")
    return "\n".join(lines)


__all__ = [
    "ArmRow",
    "ERROR",
    "FAIL",
    "INJECTION_MISSING",
    "LEAKED",
    "NON_OUTCOMES",
    "PASS",
    "aggregate",
    "context_tokens",
    "entities_opened",
    "format_matrix",
    "format_reflexes",
    "format_table",
    "hook_outputs",
    "injected_entities",
    "rate_limit_utilization",
    "reflexes",
    "result_usage",
    "task_matrix",
    "wilson",
]
