"""Parse the Claude Code CLI ``--output-format stream-json`` NDJSON stream.

The stream shape below was observed live against CLI 2.1.220 (BRO-2005 recon).
Two independent trigger detectors are implemented because they answer different
questions:

* **Detector A** — an ``assistant`` event carrying a ``tool_use`` block named
  ``Skill`` with ``input.skill == <name>``. This proves the model *asked* for the
  skill.
* **Detector B** — any event with a top-level ``tool_use_result`` of
  ``{"success": true, "commandName": "<name>"}``. This proves the launch actually
  *succeeded*.

``triggered()`` is the OR of the two: the eval grades outcomes, not paths, so a
skill that fires on turn 5 counts exactly as much as one that fires on turn 1.

Parsing is deliberately tolerant. The live stream also emits ``rate_limit_event``,
``system/thinking_tokens``, ``system/hook_started`` and other types that were never
exercised during recon; unknown types are ignored rather than raising, and
unparseable lines are counted in ``parse_errors`` instead of aborting.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

#: The tool name the CLI uses when the model invokes a skill.
SKILL_TOOL_NAME = "Skill"

#: Keys observed (or plausibly used) to carry the skill name inside a Skill tool_use.
_SKILL_NAME_KEYS = ("skill", "name", "command", "skill_name")

#: Tools an agent could use to read SKILL.md straight off disk and complete the
#: task WITHOUT ever emitting a Skill event. That is a leak, not a pass — see
#: ``Transcript.read_skill_content``.
RECOVERY_TOOLS = frozenset({"Read", "Grep", "Glob", "Bash", "LS", "NotebookRead"})

#: The CLI echoes this line back once a skill loads; it names the exact directory
#: on disk that was loaded, which proves the temp-dir copy fired and not a
#: same-named skill installed elsewhere.
_BASE_DIR_RE = re.compile(r"Base directory for this skill:\s*(\S+)")


def normalize_skill_name(name: str) -> str:
    """Fold a skill name to its comparison form: lowercase, plugin prefix stripped.

    Plugin-provided skills surface as ``plugin:skill`` in both the roster and the
    Skill tool_use, so ``kg`` must match ``bstack:kg``.
    """
    return str(name).strip().lower().rsplit(":", 1)[-1]


def _skill_content_patterns(skill: str, workspace: str | None = None) -> list[re.Pattern[str]]:
    """Regexes that identify *this* skill's own materialised files.

    Every pattern names either the skill under test or the directory the runner
    materialises it into. A bare ``SKILL.md`` is deliberately NOT one of them: the
    needle used to be the literal string anywhere in a tool input, which excluded
    ``WebFetch{"url": ".../blob/main/SKILL.md"}`` and
    ``Read{"/downloads/somebodys-skill/SKILL.md"}`` from evidence and scored a read
    of a *different* skill's file as this skill's recovery leak.
    """
    name = re.escape(normalize_skill_name(skill))
    #: A path boundary as it appears inside a JSON-serialised tool input.
    edge = r"(?:^|[/\\\"'\s=(,])"
    #: End of a path component: a separator, a quote, whitespace, or end of string.
    #: Deliberately not ``\b`` — that also matched ``demo-notes.md``.
    stop = r"(?=[/\\\"'\s]|$)"
    pats = [
        # 1. The case workspace materialises the skill under test — and nothing else —
        #    under <cwd>/.claude/skills/. Anything addressed there is the answer key,
        #    including a wildcard (`.claude/skills/*/SKILL.md`) that can only resolve
        #    to it, because the workspace holds exactly one skill by construction.
        re.compile(r"\.claude[/\\]+skills[/\\]", re.IGNORECASE),
        # 2. The skill's own directory, named explicitly, anywhere on disk — with or
        #    without this repo's `skills/<bucket>/<skill>/` bucket segment.
        re.compile(edge + r"skills[/\\]+(?:[\w.-]+[/\\]+)?" + name + stop, re.IGNORECASE),
        re.compile(edge + r"skills[/\\]+(?:[\w.-]+[/\\]+)?" + name + r"[/\\]", re.IGNORECASE),
        # 3. ...or its directory named without a `skills/` parent, still pointing at
        #    its own SKILL.md (`checkit/SKILL.md`, `checkit/references/x.md`).
        re.compile(edge + name + r"[/\\]+(?:[^\"'\s]*[/\\]+)?SKILL\.md", re.IGNORECASE),
    ]
    if workspace:
        root = re.escape(str(workspace).rstrip("/\\"))
        pats.append(re.compile(root + r"[/\\]+\.claude[/\\]+skills", re.IGNORECASE))
    return pats


def refers_to_skill_content(skill: str, blob: str, workspace: str | None = None) -> bool:
    """Does *blob* (a serialised tool input) point at the skill's own files?

    ROOT PREDICATE. Two callers depend on it and they must agree, because they are
    two halves of one rule:

    * :meth:`Transcript.read_skill_content` uses it to score the RECOVERED leak —
      the run answered by reading ``SKILL.md`` off disk instead of triggering.
    * ``checks.py`` uses it to *exclude* those same reads from counting as evidence
      that the run ingested the artifact or documented a finding.

    Keeping one predicate is what stops the contradiction the review found: the
    exact Read that defines the leak was also satisfying an ingest check.

    Scoped to the skill under test, not to the string ``SKILL.md``. *workspace* is
    the case cwd when the caller knows it; the materialised copy lives at
    ``<workspace>/.claude/skills/<skill>/``. Somebody else's ``SKILL.md`` — fetched
    from GitHub, read out of a downloads folder — is a legitimate artifact and must
    stay eligible as ingest evidence.
    """
    return any(p.search(blob) for p in _skill_content_patterns(skill, workspace))


def iter_json_lines(text: str) -> Iterator[tuple[dict[str, Any] | None, str]]:
    """Yield ``(parsed_or_None, raw_line)`` for every non-blank line of *text*."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            yield None, line
            continue
        yield (obj if isinstance(obj, dict) else None), line


@dataclass(frozen=True)
class ToolUse:
    """One ``tool_use`` block lifted out of an assistant event."""

    name: str
    input: dict[str, Any]
    id: str = ""
    parent_tool_use_id: str | None = None

    @property
    def is_subagent(self) -> bool:
        """True when the call came from inside a Task/subagent, not the main loop."""
        return self.parent_tool_use_id is not None


@dataclass(frozen=True)
class ToolResult:
    """One ``tool_result`` block — what the CLI said actually happened (BRO-2016).

    The missing half of the linkage. ``tool_use`` is the model's *claim* to have
    called something; this is the outcome. Without it every tool-side evidence
    predicate graded intent.
    """

    tool_use_id: str
    is_error: bool
    content: str = ""


def _is_error_flag(value: Any) -> bool:
    """Whether a ``tool_result``'s ``is_error`` field means failure.

    Not ``bool(value)``. Absence means SUCCESS — 375 of 1327 successful results in a
    real-transcript sample omit the key entirely (Read, Write, Edit, MCP, Skill,
    WebFetch all do) — and the string ``"False"`` is truthy in Python, so a future
    shape change from bool to string would silently invert the predicate and
    condemn every successful call.
    """
    if value is True:
        return True
    return isinstance(value, str) and value.strip().lower() == "true"


@dataclass
class Transcript:
    """A parsed CLI run: the event list plus process-level outcome metadata."""

    events: list[dict[str, Any]] = field(default_factory=list)
    exit_code: int = 0
    stderr: str = ""
    source: str = ""
    parse_errors: int = 0
    wall_ms: int | None = None

    # -- construction ---------------------------------------------------------

    @classmethod
    def from_ndjson(
        cls,
        text: str,
        *,
        exit_code: int = 0,
        stderr: str = "",
        source: str = "",
        wall_ms: int | None = None,
    ) -> "Transcript":
        events: list[dict[str, Any]] = []
        bad = 0
        for obj, _raw in iter_json_lines(text):
            if obj is None:
                bad += 1
            else:
                events.append(obj)
        return cls(
            events=events,
            exit_code=exit_code,
            stderr=stderr,
            source=source,
            parse_errors=bad,
            wall_ms=wall_ms,
        )

    # -- structural accessors -------------------------------------------------

    @property
    def init_event(self) -> dict[str, Any] | None:
        for ev in self.events:
            if ev.get("type") == "system" and ev.get("subtype") == "init":
                return ev
        return None

    @property
    def result_event(self) -> dict[str, Any] | None:
        for ev in reversed(self.events):
            if ev.get("type") == "result":
                return ev
        return None

    def skill_roster(self) -> list[str] | None:
        """Skills visible to the run, per the ``init`` event.

        Returns ``None`` when there is no init event or it carries no ``skills``
        array — that is a loud signal that the CLI stream shape changed and the
        harness must fail rather than silently score every case as a non-trigger.
        """
        init = self.init_event
        if init is None:
            return None
        roster = init.get("skills")
        if not isinstance(roster, list):
            return None
        return [str(s) for s in roster]

    @property
    def cwd(self) -> str | None:
        init = self.init_event
        return init.get("cwd") if init else None

    # -- content walkers ------------------------------------------------------

    @staticmethod
    def _blocks(ev: dict[str, Any]) -> list[dict[str, Any]]:
        msg = ev.get("message")
        if not isinstance(msg, dict):
            return []
        content = msg.get("content")
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        if isinstance(content, list):
            return [b for b in content if isinstance(b, dict)]
        return []

    def tool_uses(self) -> list[ToolUse]:
        out: list[ToolUse] = []
        for ev in self.events:
            if ev.get("type") != "assistant":
                continue
            parent = ev.get("parent_tool_use_id")
            for block in self._blocks(ev):
                if block.get("type") != "tool_use":
                    continue
                raw_input = block.get("input")
                out.append(
                    ToolUse(
                        name=str(block.get("name") or ""),
                        input=raw_input if isinstance(raw_input, dict) else {},
                        id=str(block.get("id") or ""),
                        parent_tool_use_id=parent,
                    )
                )
        return out

    def tool_results(self) -> dict[str, "ToolResult"]:
        """Every ``tool_result``, keyed by the ``tool_use_id`` it answers.

        BY ID, never by order: parallel tool calls were observed live resolving out
        of order (A, B issued; B, A returned), so any positional pairing attributes
        one call's outcome to another — which is worse than not checking at all,
        because it fails in both directions at once.
        """
        out: dict[str, ToolResult] = {}
        for ev in self.events:
            if ev.get("type") != "user":
                continue
            for block in self._blocks(ev):
                if block.get("type") != "tool_result":
                    continue
                tuid = str(block.get("tool_use_id") or "")
                if not tuid:
                    continue
                content = block.get("content")
                text = content if isinstance(content, str) else json.dumps(content, default=str)
                out[tuid] = ToolResult(
                    tool_use_id=tuid,
                    is_error=_is_error_flag(block.get("is_error")),
                    content=text,
                )
        return out

    def resolves_tool_results(self) -> bool:
        """Does this transcript model tool results at all?

        The capability probe that keeps :meth:`executed_successfully` from
        overshooting. A transcript with no result blocks anywhere is not evidence
        that its calls failed — it is evidence that this recording does not carry
        outcomes, and condemning on it would fail every hand-built fixture and every
        older recording.
        """
        return bool(self.tool_results())

    def executed_successfully(self, tu: "ToolUse | str") -> bool:
        """ROOT PREDICATE (BRO-2016): did this tool call actually RUN?

        Every tool-side evidence check funnels through here, so the three-valued
        reality is collapsed once, in one place, rather than approximated per check:

        * a matching result flagged as an error -> **False**. It errored. This is the
          ticket's core claim and it is unconditional.
        * a matching result otherwise -> **True**. It ran.
        * no matching result -> it depends, and the tie-breakers are what stop this
          fix from becoming a false-negative machine:

          - the call came from inside a subagent (:attr:`ToolUse.is_subagent`) ->
            **True**. Whether stream-json routes subagent results into the same
            stream is UNMEASURED — the sampled corpus contained none — and
            condemning on unmeasured plumbing is how a gate starts rejecting correct
            runs.
          - this transcript resolves results elsewhere -> **False**. It demonstrably
            records outcomes and recorded none for this call, so the call never
            finished.
          - this transcript resolves nothing -> **True**. Absence of evidence is not
            evidence of absence.

        That last clause is the whole anti-overshoot guard: the naive rule ("evidence
        requires a present non-error result") was measured to break 9 existing tests.
        """
        tuid = tu if isinstance(tu, str) else tu.id
        results = self.tool_results()
        found = results.get(tuid) if tuid else None
        if found is not None:
            return not found.is_error
        if not isinstance(tu, str) and tu.is_subagent:
            return True
        return not results

    def tool_call_failed(self, tool_use_id: str) -> bool:
        """True only on a DEMONSTRATED failure. Deliberately weaker than
        :meth:`executed_successfully`, which also condemns unresolved calls.

        Used by the trigger detector, where Detector B already *is* the execution
        channel — so tightening Detector A past demonstrated failure buys nothing
        and risks calling a real trigger a miss.
        """
        found = self.tool_results().get(tool_use_id)
        if found is not None and found.is_error:
            return True
        for ev in self.events:
            res = ev.get("tool_use_result")
            if isinstance(res, dict) and res.get("success") is False:
                for block in self._blocks(ev):
                    if (
                        block.get("type") == "tool_result"
                        and str(block.get("tool_use_id") or "") == tool_use_id
                    ):
                        return True
        return False

    def assistant_text(self) -> str:
        parts: list[str] = []
        for ev in self.events:
            if ev.get("type") != "assistant":
                continue
            for block in self._blocks(ev):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
        return "\n".join(parts)

    def user_texts(self) -> list[str]:
        """Text the harness/CLI fed back in — tool results, skill preambles."""
        parts: list[str] = []
        for ev in self.events:
            if ev.get("type") != "user":
                continue
            for block in self._blocks(ev):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif block.get("type") == "tool_result":
                    content = block.get("content")
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        for sub in content:
                            if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                                parts.append(sub["text"])
        return parts

    def final_text(self) -> str:
        res = self.result_event
        if res and isinstance(res.get("result"), str):
            return res["result"]
        return ""

    def output_text(self) -> str:
        """Everything the agent itself said — what outcome checks grade against.

        Deliberately excludes ``user`` events: those carry tool results, which can
        echo SKILL.md verbatim. Grading against them would let a run that merely
        *read* the skill satisfy checks written for a run that *used* it.
        """
        assistant = self.assistant_text()
        final = self.final_text()
        if final and final in assistant:
            return assistant
        return f"{assistant}\n{final}".strip()

    # -- trigger detection ----------------------------------------------------

    _norm = staticmethod(normalize_skill_name)

    def skill_invocations(self) -> list[str]:
        """Detector A — skill names the model asked for via the Skill tool."""
        out: list[str] = []
        for tu in self.tool_uses():
            if tu.name != SKILL_TOOL_NAME:
                continue
            for key in _SKILL_NAME_KEYS:
                val = tu.input.get(key)
                if isinstance(val, str) and val.strip():
                    out.append(val.strip())
                    break
        return out

    def skill_launches(self) -> list[str]:
        """Detector B — skill names whose launch the CLI reported as successful."""
        out: list[str] = []
        for ev in self.events:
            res = ev.get("tool_use_result")
            if not isinstance(res, dict):
                continue
            if res.get("success") is not True:
                continue
            name = res.get("commandName")
            if isinstance(name, str) and name.strip():
                out.append(name.strip())
        return out

    def skill_invocations_that_ran(self) -> list[str]:
        """Detector A, minus names whose every Skill call was REJECTED (BRO-2016).

        ``skill_invocations`` keeps raw-claim semantics — it is asserted directly by
        the detector tests and used in reporting — so the filtering lives here.
        A name survives if at least one of its Skill calls was not demonstrably
        rejected: two attempts where the first errored and the second worked is a
        trigger, not a miss.
        """
        surviving: list[str] = []
        for tu in self.tool_uses():
            if tu.name != SKILL_TOOL_NAME:
                continue
            for key in _SKILL_NAME_KEYS:
                val = tu.input.get(key)
                if isinstance(val, str) and val.strip():
                    if not self.tool_call_failed(tu.id):
                        surviving.append(val.strip())
                    break
        return surviving

    def triggered(self, skill: str) -> bool:
        """Did the skill fire? A REJECTED Skill call is not a firing.

        Detector A was the model's request and Detector B the CLI's confirmation,
        unioned — so a run where the model asked for the skill and the launch came
        back ``success: false`` scored as triggered. Detector A is now filtered to
        calls that were not demonstrably rejected.
        """
        target = self._norm(skill)
        seen = {self._norm(s) for s in self.skill_invocations_that_ran()}
        seen |= {self._norm(s) for s in self.skill_launches()}
        return target in seen

    def skill_base_dirs(self) -> list[str]:
        """Directories the CLI reported loading a skill from."""
        out: list[str] = []
        for text in self.user_texts():
            out.extend(_BASE_DIR_RE.findall(text))
        return out

    def read_skill_content(self, skill: str, workspace: str | None = None) -> bool:
        """Did the agent read *this* skill's SKILL.md off disk instead of invoking it?

        Materialising the skill inside the case cwd is what makes it discoverable,
        but it also puts the answer key on the filesystem. A run that greps
        ``.claude/skills/<name>/SKILL.md`` and then answers correctly is
        ``recovered-without-triggering`` — a distinct outcome from both pass and
        fail, and the one that would otherwise score a real trigger failure green.

        Delegates to :func:`refers_to_skill_content` so this outcome and the
        check-side exclusion can never drift apart. *workspace* is the case cwd,
        which is where the answer key was materialised; reading somebody else's
        ``SKILL.md`` off the internet is an ordinary artifact read, not recovery.

        A read the tool REJECTED is not recovery either (BRO-2016) — nothing was
        recovered. Gate-risk-free: it moves a trial from RECOVERED to FAIL, both
        non-PASS, so it can only sharpen the diagnosis and can never green anything.
        """
        for tu in self.tool_uses():
            if tu.name not in RECOVERY_TOOLS:
                continue
            if not self.executed_successfully(tu):
                continue
            blob = json.dumps(tu.input, ensure_ascii=False)
            if refers_to_skill_content(skill, blob, workspace):
                return True
        return False

    # -- run outcome ----------------------------------------------------------

    @property
    def is_error(self) -> bool:
        res = self.result_event
        if res is None:
            return True
        if res.get("is_error") is True:
            return True
        subtype = res.get("subtype")
        return bool(subtype) and subtype != "success"

    @property
    def error_reason(self) -> str:
        res = self.result_event
        if res is None:
            return "no result event in stream"
        if res.get("is_error") is True:
            return str(res.get("result") or res.get("subtype") or "is_error")
        subtype = res.get("subtype")
        if subtype and subtype != "success":
            return f"result subtype={subtype}"
        return ""

    def _result_num(self, key: str) -> Any:
        res = self.result_event
        return res.get(key) if res else None

    @property
    def cost_usd(self) -> float | None:
        val = self._result_num("total_cost_usd")
        return float(val) if isinstance(val, (int, float)) else None

    @property
    def duration_ms(self) -> int | None:
        val = self._result_num("duration_ms")
        if isinstance(val, (int, float)):
            return int(val)
        return self.wall_ms

    @property
    def num_turns(self) -> int | None:
        val = self._result_num("num_turns")
        return int(val) if isinstance(val, (int, float)) else None

    @property
    def permission_denials(self) -> list[Any]:
        val = self._result_num("permission_denials")
        return list(val) if isinstance(val, list) else []
