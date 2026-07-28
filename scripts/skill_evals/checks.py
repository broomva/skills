"""CHECK_REGISTRY — per-case outcome predicates dispatched by the eval runner.

A prompt-set case names the checks it expects in ``expected_checks``; the runner
looks each id up here and runs it against the finished transcript. Per BRO-2005
(and Schmid's rule of thumb) these are ~90% regex/deterministic: cheap, stable,
and free of the circularity of asking a model to grade a model.

Two design rules hold across every check:

1. **Grade outcomes, not paths.** A check asserts something about what the run
   *produced*, never that a particular tool fired on a particular turn. Where a
   check does look at tool use it accepts *either* tool evidence or textual
   evidence, so an agent that reaches the same outcome by another route passes.
2. **Grade the agent's own output.** Checks read
   ``Transcript.output_text()`` (assistant text + final result), which excludes
   tool-result events. Otherwise a run that merely echoed SKILL.md back into
   context would satisfy checks written for a run that acted on it.
3. **Tool INPUTS, never tool names.** ``Bash`` is not evidence of anything;
   ``Bash {"command": "curl https://…"}`` is. A check that keys on the tool name
   collapses into "did the agent call any tool at all", which every non-trivial
   run satisfies — the vacuity the adversarial review proved with ``echo hi``.
   Every tool-side predicate here inspects the input payload, and every one of
   them excludes references to the skill's own files (see
   ``refers_to_skill_content``): reading ``SKILL.md`` off disk is the RECOVERED
   leak, so it must never double as evidence that the artifact was ingested.

The LLM-judge seam at the bottom of this file is deliberately UNBUILT — see
``make_judge_check``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

try:  # package import (tests, runner)
    from skill_evals.transcript import Transcript, ToolUse, refers_to_skill_content
except ImportError:  # pragma: no cover - direct-file import fallback
    from transcript import Transcript, ToolUse, refers_to_skill_content  # type: ignore


# ---------------------------------------------------------------------------
# context / result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckContext:
    """Everything a check may look at. Frozen so checks cannot mutate state."""

    case: dict[str, Any]
    skill: str
    transcript: Transcript
    workspace: str | None = None

    @property
    def text(self) -> str:
        """The agent's own output — assistant text plus the final result."""
        return self.transcript.output_text()

    # NOTE: there is deliberately no `tool_names` helper. Every check that keyed on
    # one collapsed into "did the agent call any tool at all" — the vacuity an
    # adversarial review proved with a transcript whose only call was `Bash echo hi`.
    # Inspect inputs (below, or the module-level `_*_tool_evidence` predicates).

    def tool_inputs_blob(self, *names: str) -> str:
        """JSON-serialised inputs of every tool_use whose name is in *names*.

        Filtered to calls that RAN, for the same reason ``_candidate_tool_uses`` is
        (BRO-2016). No check references this today, which is exactly why it is
        tightened now: leaving one un-tightened evidence accessor in the module
        re-plants the defect for whoever writes the next check.
        """
        wanted = set(names)
        parts = [
            json.dumps(tu.input, ensure_ascii=False)
            for tu in self.transcript.tool_uses()
            if (not wanted or tu.name in wanted) and self.transcript.executed_successfully(tu)
        ]
        return "\n".join(parts)


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"check_id": self.check_id, "passed": self.passed, "detail": self.detail}


CheckFn = Callable[[CheckContext], CheckResult]


def _re(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)


def _hit(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return m.group(0).strip()[:60] if m else ""


def _result(check_id: str, passed: bool, evidence: str, want: str) -> CheckResult:
    detail = f"matched {evidence!r}" if passed else f"no evidence of {want}"
    return CheckResult(check_id, passed, detail)


# ---------------------------------------------------------------------------
# tool-INPUT predicates (design rule 3)
# ---------------------------------------------------------------------------

#: A shell command that actually pulls an artifact in. Anchored on the verb, so
#: ``echo hi`` — or any other command that touches nothing — matches nothing.
_FETCH_CMD_RE = _re(
    r"(?:^|[|;&(`]|\s)(curl|wget|yt-dlp|youtube-dl|http|https|pandoc|pdftotext|"
    r"gh\s+(?:api|pr|issue|repo|release)|git\s+(?:clone|show|log|cat-file)|"
    r"cat|head|tail|less|jq|python3?\s+-m\s+json\.tool|open)\b"
)

#: A shell command that walks a tree or searches it.
_WALK_CMD_RE = _re(
    r"(?:^|[|;&(`]|\s)(ls|find|tree|fd|rg|grep|du|wc|stat|"
    r"git\s+(?:ls-files|ls-tree|status|diff))\b"
)

#: Something that looks like a URL or a filesystem path inside a tool input.
_TARGET_RE = re.compile(r"https?://\S+|[\w.~-]*/[\w./~-]+|\b[\w-]+\.[A-Za-z0-9]{1,8}\b")

#: A written path that plausibly *is* a durable finding: a document extension, or a
#: knowledge-bearing directory. ``/x/unrelated.txt`` is neither.
_DOC_PATH_RE = _re(
    r"\.(?:md|mdx|markdown|json|ya?ml|ndjson|csv|rst|adoc)$|"
    r"(?:^|/)(?:research|docs?|notes?|entities|knowledge|adrs?|specs?|plans?)/"
)

_FETCH_TOOLS = frozenset({"WebFetch", "WebSearch"})
_READ_TOOLS = frozenset({"Read", "NotebookRead"})
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_LIST_TOOLS = frozenset({"Glob", "LS", "Grep"})

#: Input keys that carry the thing a tool acted ON, in rough priority order.
_TARGET_KEYS = (
    "url", "query", "file_path", "notebook_path", "path", "pattern", "command",
    "prompt", "glob", "filePath",
)


def _target(tu: "ToolUse") -> str:
    """The first non-empty target-ish value in a tool input, as a string."""
    for key in _TARGET_KEYS:
        val = tu.input.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _describe(tu: "ToolUse", value: str, limit: int = 60) -> str:
    return f"{tu.name}({value[:limit]})"


def _candidate_tool_uses(ctx: CheckContext) -> list["ToolUse"]:
    """Tool calls that may serve as evidence: anything not aimed at the skill itself.

    Excluding the skill's own files here is the whole resolution of the
    review's contradiction — a Read of ``.claude/skills/<skill>/SKILL.md`` scores
    RECOVERED, and must not simultaneously prove the artifact was ingested. The
    exclusion is scoped to *this* skill's materialised copy (``ctx.workspace``),
    so fetching somebody else's ``SKILL.md`` off GitHub stays valid evidence.

    A call that did not RUN is likewise not evidence (BRO-2016). This is the single
    funnel for ``documents_finding``, ``walks_repo_tree_and_canonical_files`` and
    ``ingests_full_artifact_not_metadata``, so the execution requirement is applied
    once here rather than patched into each of the three — the root predicate is
    ``Transcript.executed_successfully``, which carries the carve-outs that stop it
    condemning transcripts that simply do not model results.
    """
    out: list["ToolUse"] = []
    for tu in ctx.transcript.tool_uses():
        if not ctx.transcript.executed_successfully(tu):
            continue
        blob = json.dumps(tu.input, ensure_ascii=False)
        if refers_to_skill_content(ctx.skill, blob, ctx.workspace):
            continue
        out.append(tu)
    return out


# ---------------------------------------------------------------------------
# artifact scoping (D7): "did it ingest THE artifact", not "did it read a file"
# ---------------------------------------------------------------------------

#: A URL, or a path-shaped run of segments, inside the case prompt.
_PROMPT_URL_RE = re.compile(r"https?://[^\s<>\"'`)\]}]+")
_PROMPT_PATH_RE = re.compile(r"(?<![\w@:])(?:[\w~-][\w.~-]*/)+[\w.~-]+")

#: A slash in prose is not a path. ``founder/creator`` and ``role/x`` both match
#: ``_PROMPT_PATH_RE`` and both used to contribute artifact tokens, so
#: ``ingests_full_artifact_not_metadata`` on real-trace-04 accepted a fetch of any
#: URL containing "founder". A real reference carries a host or a filename — it has
#: a dot, or it has enough segments to be a path. An either/or, matched against
#: every genuine reference in the pilot: ``arxiv.org/abs/2602.12670`` (dot),
#: ``x.com/gethuxe`` (dot), ``github.com/gepa-ai/gepa`` (both), ``docs/spec.md``
#: (dot). Prose pairs carry neither.
def _is_path_shaped(match: str) -> bool:
    return "." in match or match.count("/") >= 2

#: Segments that appear in almost every URL/path and therefore discriminate nothing.
#: Scoping on these would be the same vacuity as keying on a tool NAME.
_GENERIC_SEGMENTS = frozenset({
    "http", "https", "www", "com", "org", "net", "io", "dev", "app", "co", "ai",
    "github", "gitlab", "githubusercontent", "arxiv", "youtube", "youtu", "medium",
    "substack", "blob", "main", "master", "tree", "raw", "docs", "doc", "index",
    "html", "htm", "wiki", "pdf", "abs", "src", "lib", "tmp", "var", "usr", "home",
    "users", "files", "file", "page", "pages", "view", "watch", "posts", "post",
    "blog", "api", "en", "www2", "content", "default", "readme", "readme.md",
    # Route nouns on the big artifact hosts. `…/status/<id>` and `…/i/article/<id>`
    # appear in EVERY X permalink, so scoping on them scopes to the site, not the
    # post — the same host-level vacuity `_is_distinctive` rejects below.
    "status", "statuses", "article", "articles",
})


def _is_distinctive(tok: str) -> bool:
    """Does *tok* name THIS artifact, or merely the site it happens to live on?

    The round-3 leak (N2): ``_PROMPT_PATH_RE`` matches ``github.com/gepa-ai/gepa``
    and splits it on ``/``, so ``github.com`` entered the token set intact. The
    stoplist never caught it — it holds ``github`` and ``com`` as separate
    segments, and the dotted host is neither. Scoping on ``github.com`` turns
    ``ingests_full_artifact_not_metadata`` into "did the agent fetch anything from
    GitHub", which a fetch of a COMPLETELY DIFFERENT repo also satisfies. Measured
    false-passes before this predicate existed: a different github repo, a
    different arXiv paper, a different YouTube video, and
    ``Read /var/log/github.com.log``.

    A dotted token is therefore admitted only when one of its dot-separated parts
    is itself distinctive. ``github.com`` / ``arxiv.org`` / ``www.youtube.com`` /
    ``x.com`` are hosts and are dropped; ``2602.12670`` (an arXiv id) and
    ``julianealborna.com`` (a host whose own name IS the artifact) survive.
    """
    if len(tok) < 4 or tok in _GENERIC_SEGMENTS:
        return False
    if "." not in tok:
        return True
    return any(len(part) >= 4 and part not in _GENERIC_SEGMENTS for part in tok.split("."))


def _artifact_tokens(prompt: str) -> set[str]:
    """Distinctive tokens naming the artifact the case actually points at.

    Empty when the prompt names no artifact (a bare-topic case, or a pasted
    document). Callers treat "no tokens" as "nothing to scope to" and stay
    permissive rather than failing a case that never had an artifact to match.
    """
    tokens: set[str] = set()
    chunks: list[str] = []
    for m in _PROMPT_URL_RE.finditer(prompt):
        url = m.group(0)
        rest = url.split("://", 1)[-1]
        host, _, path = rest.partition("/")
        chunks.extend(host.split(":")[0].split("."))
        chunks.extend(re.split(r"[/?&=#]", path))
    for m in _PROMPT_PATH_RE.finditer(prompt):
        if _is_path_shaped(m.group(0)):
            chunks.extend(m.group(0).split("/"))
    for chunk in chunks:
        tok = chunk.strip().lower()
        # ONE admission predicate, applied to the token and to its stem alike.
        # Testing the stem separately is how `www.youtube` (stem of
        # `www.youtube.com`) used to slip past a stoplist that holds only `www`,
        # `youtube` and `com`.
        for candidate in (tok, tok.rsplit(".", 1)[0]):
            if _is_distinctive(candidate):
                tokens.add(candidate)
    return tokens


def _case_artifact_tokens(case: dict[str, Any]) -> set[str]:
    """Artifact tokens for a case: its prompt, plus any declared aliases.

    ``artifact_aliases`` exists for ONE shape, and it is not an escape hatch: an
    artifact reached through an indirection that shares no distinctive token with
    the link the user pasted. The pilot's golden-04 is exactly that — the X status
    renders as the empty string and carries a bare ``t.co`` link, so all of the
    post's substance sits at ``x.com/i/article/2079141496981184512``, which shares
    with the prompt only the host ``x.com``. Once host-level tokens are (rightly)
    dropped, the correct route of following the redirect would score FAIL.

    An alias is a URL/id that resolves to the SAME artifact, declared in the
    prompt set where a reviewer can check it against the verification log. It only
    ever ADDS tokens; it cannot make a wrong-artifact fetch pass, because the wrong
    artifact still matches none of them.
    """
    tokens = _artifact_tokens(str(case.get("prompt", "")))
    aliases = case.get("artifact_aliases") or []
    if isinstance(aliases, (list, tuple)):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                tokens |= _artifact_tokens(alias)
    return tokens


def _hits_artifact(target: str, tokens: set[str]) -> bool:
    """Does *target* reference the artifact the case named? Vacuously true if none."""
    if not tokens:
        return True
    low = target.lower()
    return any(tok in low for tok in tokens)


def _ingest_tool_evidence(ctx: CheckContext) -> str:
    """A tool call that actually pulled THE case's artifact in, or ``""``.

    DELIBERATE (D7): a read is scoped to the artifact the case names, not accepted
    for any file at all. ``Read {"file_path": "/etc/hosts"}`` is a read; it is not
    evidence that *this* case's artifact was ingested, and the check is named
    ``ingests_full_artifact_not_metadata``. When the prompt names no artifact —
    a bare topic, a pasted document — there is nothing to scope to and any
    content-pulling call counts, because the alternative would fail a case that
    could never have matched. The textual arm of the check is unchanged, so an
    agent that reaches the artifact by an unmodelled route still passes.
    """
    tokens = _case_artifact_tokens(ctx.case)
    for tu in _candidate_tool_uses(ctx):
        target = _target(tu)
        if not target or not _hits_artifact(target, tokens):
            continue
        if tu.name in _FETCH_TOOLS:
            return _describe(tu, target)
        if tu.name in _READ_TOOLS:
            return _describe(tu, target)
        if tu.name == "Bash" and _FETCH_CMD_RE.search(target) and _TARGET_RE.search(target):
            return _describe(tu, target)
    return ""


def _walk_tool_evidence(ctx: CheckContext) -> str:
    """A tool call that actually inspected a tree, or ``""``."""
    for tu in _candidate_tool_uses(ctx):
        target = _target(tu)
        if not target:
            continue
        if tu.name in _LIST_TOOLS:
            return _describe(tu, target)
        if tu.name == "Bash" and _WALK_CMD_RE.search(target):
            return _describe(tu, target)
    return ""


def _document_tool_evidence(ctx: CheckContext) -> str:
    """A write whose destination looks like a durable finding, or ``""``."""
    for tu in _candidate_tool_uses(ctx):
        if tu.name not in _WRITE_TOOLS:
            continue
        target = _target(tu)
        if target and _DOC_PATH_RE.search(target):
            return _describe(tu, target)
    return ""


# ---------------------------------------------------------------------------
# generic checks — usable by any skill's prompt set
# ---------------------------------------------------------------------------


def check_skill_triggered(ctx: CheckContext) -> CheckResult:
    """The skill fired at some point in the run (any turn)."""
    ok = ctx.transcript.triggered(ctx.skill)
    return CheckResult(
        "skill_triggered",
        ok,
        # Says what it now MEANS. The old wording ("tool_use/tool_use_result
        # observed") described the union that let a REJECTED launch read as a
        # firing; a detail string that misdescribes its own trigger is the
        # forward-honesty failure this workspace's canon lens catches.
        "Skill launch observed (a Skill call that was not rejected, or a successful launch)"
        if ok
        else "no Skill event for this skill, or every Skill call was rejected",
    )


# REMOVED 2026-07-28: `completed_without_error` was STRUCTURALLY UNFAILABLE.
#
# It read `ok = not ctx.transcript.is_error` — but `grade_trial` returns
# `out(ERROR, ...)` on `if transcript.is_error:` (runner.py) BEFORE `run_checks`
# is ever reached, so the only condition the check tested could never arrive at
# it. Every invocation returned True. It was a vacuous check sitting in the
# registry of a harness whose entire purpose is catching vacuous checks, and it
# was asserted on 11 cases across two prompt sets before two independent
# reviewers found it.
#
# Deleted rather than repaired: there is nothing left for it to test, because
# the runner already handles the error case at a strictly earlier point. Removing
# it from CHECK_REGISTRY is deliberate — a prompt set that still asserts it now
# fails validation with "unknown check id", which is the correct loud failure.
#
# The invariant that made it vacuous is pinned by
# test_error_transcripts_never_reach_run_checks, so this cannot silently return.


#: Substance is counted in words, not characters. A correct answer to a yes/no
#: question is short; an acknowledgement is short AND says nothing. Only the
#: second is a failure, so the floor has to be low enough to let the first through.
_MIN_ANSWER_WORDS = 3

#: Sentence boundary, used to peel a trailing offer off an answer. A LINE BREAK
#: ends a sentence too: a markdown answer whose bullets or code lines carry no
#: terminal punctuation would otherwise collapse into one "sentence" spanning the
#: whole turn, and the turn's first word would be read as the head word of its
#: closing question.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

#: An acknowledgement with no content: what "empty" actually looks like in a
#: transcript that technically has characters in it.
_STUB_RE = re.compile(
    r"^\W*(?:ok(?:ay)?|sure(?: thing)?|done|yes|no|yep|nope|got it|will do|on it|"
    r"thanks|understood|see above|n/?a|tbd|of course|absolutely|no problem|"
    r"happy to help|glad to help|…|\.{2,})\W*$",
    re.IGNORECASE,
)


def check_final_answer_non_empty(ctx: CheckContext) -> CheckResult:
    """The run produced a real answer rather than an acknowledgement or a stub.

    Substance is measured in WORDS, not characters. The previous 40-character
    floor failed a correct short reply — "no, it just calls an API endpoint" is
    34 characters and is the right answer to a yes/no question — which is a gate
    false-failing correct behaviour, exactly as useless as one that false-passes.
    """
    final = ctx.transcript.final_text().strip()
    words = len(re.findall(r"\b[\w'’-]+\b", final))
    stub = bool(_STUB_RE.match(final))
    ok = bool(final) and words >= _MIN_ANSWER_WORDS and not stub
    if ok:
        detail = f"{words} words / {len(final)} chars"
    elif stub:
        detail = f"acknowledgement only: {final[:40]!r}"
    else:
        detail = f"only {words} word(s) / {len(final)} chars"
    return CheckResult("final_answer_non_empty", ok, detail)


def check_no_permission_denials(ctx: CheckContext) -> CheckResult:
    """No tool call was blocked — a denial makes a trigger failure ambiguous."""
    denials = ctx.transcript.permission_denials
    return CheckResult(
        "no_permission_denials", not denials, "" if not denials else f"{len(denials)} denial(s)"
    )


# ---------------------------------------------------------------------------
# outcome checks referenced by the checkit pilot prompt set
# ---------------------------------------------------------------------------

_VERIFY_RE = _re(
    r"\b(verif(?:y|ied|ying|ication)|cross[- ]check(?:ed|ing)?|corroborat\w*|"
    r"primary source|source[- ]check\w*|confirmed (?:via|against|by|with)|"
    r"could not (?:confirm|verify)|unverified|citation|cited)\b"
)

_FULL_INGEST_RE = _re(
    r"\b(transcript|full text|read (?:the )?(?:whole|full|entire)|"
    r"watched (?:the|it)|opened (?:the|it)|contents of|fetched (?:the|it)|"
    r"скачал|downloaded (?:the|it)|line \d+|section \d)\b"
)

_ACTIVE_WORK_RE = _re(
    r"\b(our |we already|we're building|we are building|existing |current(?:ly)? |"
    r"in (?:our|the) (?:stack|repo|workspace)|relates to|overlaps with|"
    r"compared? (?:to|with) (?:our|the existing)|already have|BRO-\d+|"
    r"your (?:stack|repo|work|harness))"
)

_DOCUMENT_RE = _re(
    r"\b(wrote|writing|written to|filed|saved|created|documented|note at|"
    r"captured in|recorded in)\b[^\n]{0,80}?"
    r"(\.md|\.json|\.ya?ml|research/|docs/|notes?/|entit(?:y|ies))"
)

_NEXT_STEP_RE = _re(r"\b(next step|next action|recommend|suggest|option \d|i'd start|priorit)")
_ENUM_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+\S", re.MULTILINE)

_REPO_ARTIFACT_RE = _re(
    r"\b(README(?:\.md)?|package\.json|Cargo\.toml|pyproject(?:\.toml)?|go\.mod|"
    r"SKILL\.md|CONTRIBUTING|LICENSE|Makefile|Dockerfile|\.github/|src/|docs/|tests?/)"
)
_TREE_RE = _re(r"\b(directory tree|repo(?:sitory)? (?:tree|layout|structure)|file tree|top[- ]level dirs?)\b")

# ---------------------------------------------------------------------------
# bounce vs offer — WHO is being asked to decide the task
# ---------------------------------------------------------------------------
#
#   bounce — "Which of those would you like me to take?"   (you tell me what to do)
#   offer  — "Want me to write that up as a note?"         (I propose; you confirm)
#
# Only the first is the failure; the second is SKILL.md's own prescribed closing
# shape. Two round-3 defects came from grading something other than that:
#
# 1. The opener rule was a bare PREFIX match with no interrogative requirement, so
#    "Which one wins depends on how often you bump the lockfile." — a DECLARATIVE
#    sentence that merely starts with "which" — was scored as opening with a
#    clarifying question. 7 of 7 constructed answers containing zero questions
#    failed. Requiring an actual question is necessary (and, per 2, not sufficient).
#
# 2. The direction rule was `.search()`ed across the whole trailing question, so an
#    OFFER whose OBJECT clause happened to contain "which one" — "Want me to
#    benchmark which one is faster?" — was scored a bounce. 6 of 8 realistic offers
#    were rejected.
#
# The discriminator is FRONTING, which is where English marks who supplies the
# missing content. A wh-question puts the gap in head position, so the user has to
# fill it in. A polar question fronts the modal, so the agent has already named the
# action and the user only says yes or no — which is exactly why an offer may
# legally CONTAIN "which one" deep inside its object clause. Matching on the head
# word instead of on mere presence is the fix for 2; running every arm only over
# sentences that actually end in "?" is the fix for 1.

_PLEASANTRY = (
    r"(?:sure(?: thing)?|ok(?:ay)?|got it|hi|hey|of course|absolutely|no problem|"
    r"happy to help|glad to help|great question)"
)

#: Leading discourse noise consumed before a question's head word is read.
_LEAD_NOISE_RE = re.compile(rf"^[\s\W]*(?:(?:{_PLEASANTRY})\b[\s,.!—–-]*)*", re.IGNORECASE)

#: A fronted subordinate clause ("Before I dig in, …"), which can push the real
#: head word off position 0. Stripping it is UNION-ed with the unstripped head, so
#: it can only add detections — "Which package manager are you using, and how long
#: …?" is still read as wh-fronted from its own first word.
_FRONTED_CLAUSE_RE = re.compile(r"^[^,;:?]{0,60}?[,;:]\s*")

#: The interrogative words that put the gap in head position. "how about" / "what
#: about" are carved out: they front a PROPOSAL ("How about I write that up?"),
#: which is an offer wearing a wh-word.
_WH_HEAD_RE = re.compile(
    r"^(?!(?:how|what) about\b)(?:which|what|who|whom|whose|where|when|why|how)\b",
    re.IGNORECASE,
)

#: A question addressed to the user rather than asked rhetorically. "What breaks
#: first? The nightly job." asks nobody and answers itself.
_SECOND_PERSON_RE = re.compile(r"\byou(?:r|rs)?\b", re.IGNORECASE)

#: An explicit demand that the user restate the ask. A bounce however it is
#: fronted, so this arm is searched anywhere inside an interrogative sentence.
#: Every alternative here is a form that only occurs when the USER is being asked
#: to supply something — deliberately NOT the round-3 "which one|which of these"
#: rule, whose whole defect was that offers contain those strings too.
_CLARIFY_RE = re.compile(
    r"\b(?:could|can|would|will) you (?:clarify|specify|confirm|tell me|say|let me know)\b"
    r"|\bjust to (?:clarify|confirm|check|make sure)\b"
    r"|\bto (?:make sure|clarify|confirm) (?:i|we)\b"
    r"|\b(?:which|what)\b[^?.!]{0,60}?\b(?:would you (?:like|prefer)|do you want)\b"
    r"|\bwhat (?:exactly )?(?:are|is) your? (?:after|goal|aim|priority|priorities)\b"
    r"|\bwhat should i (?:focus|prioriti|start|look|do)\w*\b",
    re.IGNORECASE,
)


def _is_wh_fronted(question: str) -> bool:
    """Is the interrogative word the HEAD of *question* (so the user fills the gap)?"""
    head = _LEAD_NOISE_RE.sub("", question, count=1)
    if _WH_HEAD_RE.match(head):
        return True
    unfronted = _FRONTED_CLAUSE_RE.sub("", head, count=1)
    return bool(unfronted) and unfronted != head and bool(_WH_HEAD_RE.match(unfronted))

_PRIMITIVE_RE = _re(
    r"\b(under the hood|underneath|primitive|mechanism|implement(?:ed|ation|s)|"
    r"how it (?:actually )?works|built on|relies on|boils down to|the reason (?:it|this)|"
    r"architectur\w+|substrate)\b"
)


def check_mentions_source_verification(ctx: CheckContext) -> CheckResult:
    hit = _hit(_VERIFY_RE, ctx.text)
    return _result("mentions_source_verification", bool(hit), hit, "source verification language")


def check_ingests_full_artifact_not_metadata(ctx: CheckContext) -> CheckResult:
    """Evidence the artifact itself was consumed, not just its title/URL.

    Tool evidence must name what was fetched or read (and must not be the skill's
    own SKILL.md); ``Bash echo hi`` is not ingestion. Textual evidence remains an
    accepted alternative route per design rule 1.
    """
    tool_hit = _ingest_tool_evidence(ctx)
    hit = _hit(_FULL_INGEST_RE, ctx.text)
    ok = bool(tool_hit) or bool(hit)
    return _result(
        "ingests_full_artifact_not_metadata",
        ok,
        tool_hit or hit,
        "full-artifact ingestion (a fetch/read naming its target, or full-text language)",
    )


def check_connects_to_active_work(ctx: CheckContext) -> CheckResult:
    hit = _hit(_ACTIVE_WORK_RE, ctx.text)
    return _result("connects_to_active_work", bool(hit), hit, "a link back to the user's active work")


def check_documents_finding(ctx: CheckContext) -> CheckResult:
    """A durable artifact was produced — a write to a document-shaped destination.

    A write to any path at all is not a documented finding: an ``Edit`` of
    ``/x/unrelated.txt`` used to satisfy this. The destination must carry a
    document extension or sit in a knowledge-bearing directory.
    """
    tool_hit = _document_tool_evidence(ctx)
    hit = _hit(_DOCUMENT_RE, ctx.text)
    ok = bool(tool_hit) or bool(hit)
    return _result(
        "documents_finding", ok, tool_hit or hit, "a documented, durable finding"
    )


def check_produces_ranked_next_steps(ctx: CheckContext) -> CheckResult:
    """At least two enumerated items framed as next steps / recommendations."""
    enumerated = len(_ENUM_RE.findall(ctx.text))
    hit = _hit(_NEXT_STEP_RE, ctx.text)
    ok = enumerated >= 2 and bool(hit)
    return _result(
        "produces_ranked_next_steps",
        ok,
        f"{enumerated} enumerated items + {hit!r}",
        "≥2 enumerated items framed as next steps",
    )


def check_walks_repo_tree_and_canonical_files(ctx: CheckContext) -> CheckResult:
    """The repo's shape was actually inspected, not inferred from the URL.

    Tool evidence must be a listing/search call that names a path or pattern —
    ``Bash echo hi`` is not a traversal.
    """
    tool_hit = _walk_tool_evidence(ctx)
    hit = _hit(_REPO_ARTIFACT_RE, ctx.text) or _hit(_TREE_RE, ctx.text)
    ok = bool(tool_hit) or bool(hit)
    return _result(
        "walks_repo_tree_and_canonical_files",
        ok,
        tool_hit or hit,
        "repo-tree traversal (a listing/search naming its target) or canonical-file references",
    )


def _sentences(text: str) -> list[str]:
    """The turn split into sentences, blanks dropped."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _split_trailing_questions(text: str) -> tuple[str, list[str]]:
    """``(body, trailing_questions)`` — peel the interrogative tail off a turn.

    *body* is the part of the final turn that ANSWERED. An answer that ends by
    offering a next step ("...want me to write that up?") leaves a body behind; a
    bounced clarifying question leaves nothing.
    """
    sents = _sentences(text)
    cut = len(sents)
    while cut and sents[cut - 1].endswith("?"):
        cut -= 1
    return " ".join(sents[:cut]).strip(), sents[cut:]


def check_no_clarifying_question_bounced_back(ctx: CheckContext) -> CheckResult:
    """The run inferred the ask instead of handing articulation back to the user.

    Two distinct shapes, and only one of them is the failure:

    * **bounce** — the turn asks the user to specify the ask before doing the
      work, or IS nothing but that question. The skill exists to prevent this.
    * **answer + offer** — a bounded answer that closes with "want me to write
      that up?". That is correct behaviour, and SKILL.md's own prescribed shape.

    Four arms, all of them running only over sentences that ACTUALLY END IN A
    QUESTION MARK — a declarative "Which one wins depends on…" is not a question
    and must not be graded as one:

    1. *whole turn is a question* — nothing survives once the trailing
       interrogatives are peeled, so no work was done. Length is irrelevant.
    2. *explicit demand* — any question that asks the user to restate the ask
       ("could you clarify…", "just to clarify…", "which of those would you like").
    3. *closes wh-fronted* — the turn's closing move is a wh-question, i.e. it ends
       by demanding content instead of proposing an action.
    4. *wh-fronted at the user* — a wh-question addressed to the user ("you")
       anywhere in the turn. Arms 3 and 4 together are one rule with a rhetorical
       exception: a wh-question is a bounce unless the agent answers it itself,
       which is what "not the closing move AND not addressed to you" means.
    """
    final = ctx.transcript.final_text().strip() or ctx.text.strip()
    body, trailing = _split_trailing_questions(final)
    body_words = len(re.findall(r"\b[\w'’-]+\b", body))
    questions = [s for s in _sentences(final) if s.endswith("?")]

    # Nothing but a question (possibly behind "sure," / "got it") is a bounce
    # however long the question itself is.
    all_question = bool(trailing) and (
        body_words < _MIN_ANSWER_WORDS or bool(_STUB_RE.match(body))
    )
    demanded = next((q for q in questions if _CLARIFY_RE.search(q)), "")
    closes_wh = next((q for q in trailing if _is_wh_fronted(q)), "")
    addressed_wh = next(
        (q for q in questions if _is_wh_fronted(q) and _SECOND_PERSON_RE.search(q)), ""
    )

    ok = not (all_question or demanded or closes_wh or addressed_wh)
    if all_question:
        why = f"the whole turn is a question; {body_words} word(s) of answer before it"
    elif demanded:
        why = f"asks the user to specify the ask: {demanded[:60]!r}"
    elif closes_wh:
        why = f"closes by demanding content rather than proposing a step: {closes_wh[:60]!r}"
    elif addressed_wh:
        why = f"asks the user to supply the task: {addressed_wh[:60]!r}"
    else:
        why = ""
    return CheckResult("no_clarifying_question_bounced_back", ok, why)


def check_traverses_to_primitives(ctx: CheckContext) -> CheckResult:
    hit = _hit(_PRIMITIVE_RE, ctx.text)
    return _result(
        "traverses_to_primitives", bool(hit), hit, "traversal to underlying mechanism"
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

CHECK_REGISTRY: dict[str, CheckFn] = {
    # generic
    "skill_triggered": check_skill_triggered,
    "final_answer_non_empty": check_final_answer_non_empty,
    "no_permission_denials": check_no_permission_denials,
    # outcome checks (checkit pilot; reusable)
    "mentions_source_verification": check_mentions_source_verification,
    "ingests_full_artifact_not_metadata": check_ingests_full_artifact_not_metadata,
    "connects_to_active_work": check_connects_to_active_work,
    "documents_finding": check_documents_finding,
    "produces_ranked_next_steps": check_produces_ranked_next_steps,
    "walks_repo_tree_and_canonical_files": check_walks_repo_tree_and_canonical_files,
    "no_clarifying_question_bounced_back": check_no_clarifying_question_bounced_back,
    "traverses_to_primitives": check_traverses_to_primitives,
}


def unknown_checks(check_ids: list[str]) -> list[str]:
    """Check ids referenced by a prompt set that this registry cannot dispatch."""
    return [c for c in check_ids if c not in CHECK_REGISTRY]


def run_checks(check_ids: list[str], ctx: CheckContext) -> list[CheckResult]:
    """Dispatch each id through the registry. Unknown ids fail loudly, never silently."""
    out: list[CheckResult] = []
    for check_id in check_ids:
        fn = CHECK_REGISTRY.get(check_id)
        if fn is None:
            out.append(CheckResult(check_id, False, "unknown check id (not in CHECK_REGISTRY)"))
            continue
        try:
            out.append(fn(ctx))
        except Exception as exc:  # a broken check must not be scored as a pass
            out.append(CheckResult(check_id, False, f"check raised {type(exc).__name__}: {exc}"))
    return out


# ===========================================================================
# SEAM — LLM judge (deliberately NOT built; BRO-2005 scope stops here)
# ===========================================================================
#
# ~90% of checks should stay regex. The residual 10% are genuinely qualitative
# dimensions ("did the analysis actually engage with the artifact's argument, or
# only its abstract?") that no regex settles. When that judge is built it must:
#
#   * return STRUCTURED OUTPUT against JUDGE_SCHEMA below — never free text that a
#     second regex then parses, which merely relocates the brittleness;
#   * run on a DIFFERENT model than the one under eval (a model grading its own
#     transcript is the self-referential verification keel exists to flag);
#   * be cached by (transcript hash, rubric hash) so a re-run of the suite is free;
#   * stay a MINORITY of any prompt set's expected_checks — if a skill's pass
#     hinges mostly on judge calls, the outcome was not specified sharply enough.
#
# Until then ``make_judge_check`` raises. A stub returning True would be exactly
# the vacuous pass this harness exists to prevent.

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["passed", "confidence", "evidence", "reasoning"],
    "properties": {
        "passed": {"type": "boolean", "description": "Does the transcript satisfy the rubric?"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Verbatim spans from the transcript supporting the verdict.",
            "minItems": 1,
        },
        "reasoning": {"type": "string", "maxLength": 600},
    },
}


@dataclass(frozen=True)
class JudgeSpec:
    """Declarative description of a judge check. Inert until the judge is built."""

    check_id: str
    rubric: str
    model: str = "sonnet"
    schema: dict[str, Any] = field(default_factory=lambda: JUDGE_SCHEMA)


def make_judge_check(spec: JudgeSpec) -> CheckFn:
    """SEAM: build a CHECK_REGISTRY-compatible callable backed by an LLM judge.

    Not implemented in BRO-2005 by design. Raises rather than returning a
    permissive stub, so a prompt set that reaches for the judge early fails
    visibly instead of collecting free passes.
    """

    raise NotImplementedError(
        f"LLM-judge check {spec.check_id!r} is a declared seam, not an implementation. "
        "Build it against JUDGE_SCHEMA with a grader model distinct from the model "
        "under eval, then register it in CHECK_REGISTRY."
    )
