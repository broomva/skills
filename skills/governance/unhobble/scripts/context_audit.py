#!/usr/bin/env python3
"""context_audit.py — deterministic evidence for a context-surface audit.

This script measures a context surface (CLAUDE.md, AGENTS.md, a SKILL.md, a
system prompt, or a bare prompt) against the six Claude-5 context-engineering
reversals. It produces EVIDENCE ONLY.

It deliberately does not emit keep/delete verdicts. Whether a rule may be
deleted depends on whether an independent mechanism already enforces it — a
grounding question the agent (composing `keel`) answers, not a regex. A script
that printed "DELETE" here would be guessing with a confident voice.

Signals, each mapped to the reversal it serves:

  budget        total always-on tokens vs target        (the headline number)
  polarity      prohibition / mandate / permission /
                judgment / descriptive per section      (R1 rules -> judgment)
  examples      fenced blocks + example/anti-pattern
                table rows per section                  (R2 examples -> interface)
  disclosure    surface exceeds split threshold with
                no references/ split                    (R3 upfront -> progressive)
  duplication   near-duplicate section clusters
                (word-shingle Jaccard)                  (R4 repetition -> single source)
  derivable     sections that restate the filesystem    ("avoid the obvious")
  mechanism     path/command references in a section
                that actually exist on disk             (anchored-vs-self-referential input)
  anchor state  whether a probe has DEMONSTRATED that
                mechanism firing — unresolved until
                one has (see references/mechanism-probe.md)
  contradiction topics carrying both a prohibition and
                a permission/judgment, across sections  (the article's own diagnostic)

Usage:
    context_audit.py <path> [<path> ...] [--budget N] [--json] [--repo-root DIR]
    context_audit.py <path> --probe-receipts probes.json
    context_audit.py --prompt-text "..." [--json]
    context_audit.py --prompt-file prompt.md [--json]
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import heapq
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------
# Token estimation
# --------------------------------------------------------------------------

# Prose-markdown chars-per-token. Calibrated against tiktoken cl100k over 12
# real governance surfaces (CLAUDE.md, AGENTS.md, METALAYER.md, nine SKILL.md
# files): observed range 3.67-4.58, mean 4.10. Using the mean, per-file error
# spans about -10% to +13% — wide enough that a budget call landing within ~15%
# of a threshold should be settled with the real tokenizer, not this.
#
# Used only when tiktoken is unavailable; every consumer labels the result
# "estimate(...)" so a reader never mistakes it for an exact count.
# `pip install tiktoken` for exact counts.
_CHARS_PER_TOKEN = 4.10


def estimate_tokens(text: str) -> int:
    """Token count. Exact when tiktoken is importable, else a prose estimate."""
    try:
        import tiktoken  # type: ignore

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return int(len(text) / _CHARS_PER_TOKEN + 0.5)


def tokenizer_name() -> str:
    try:
        import tiktoken  # noqa: F401

        return "tiktoken/cl100k_base"
    except Exception:
        return f"estimate(chars/{_CHARS_PER_TOKEN})"


# --------------------------------------------------------------------------
# Markdown segmentation
# --------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# Capture the FULL run length: a ```` fence is closed only by a run of >= 4 of
# the same char, so an inner ``` block does not terminate it. SKILL.md files
# routinely wrap markdown examples in 4-backtick fences, and SKILL.md is a
# first-class audit target — treating the inner fence as a close leaks example
# headings into the section table.
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def _scan_fences(lines: list[str]):
    """Yield (index, line, in_fence, event) with CommonMark-ish fence nesting.

    `event` is "open", "close", or None. Callers that only skip fenced content
    ignore it; count_examples needs it, because two ADJACENT fenced blocks are
    one uninterrupted run of in_fence lines and cannot be counted by watching
    for transitions.
    """
    open_char: str | None = None
    open_len = 0
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if m:
            run = m.group(1)
            if open_char is None:
                open_char, open_len = run[0], len(run)
                yield i, line, True, "open"
                continue
            if run[0] == open_char and len(run) >= open_len:
                open_char, open_len = None, 0
                yield i, line, True, "close"
                continue
        yield i, line, open_char is not None, None


@dataclass
class Section:
    path: str
    heading: str
    level: int
    start_line: int
    end_line: int
    text: str
    tokens: int = 0
    polarity: dict = field(default_factory=dict)
    dominant: str = "descriptive"
    examples: int = 0
    derivable: bool = False
    mechanism_refs: list = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.path}#{self.heading}"


def split_sections(text: str, path: str = "<text>") -> list[Section]:
    """Split markdown into heading-delimited sections.

    Content before the first heading becomes a synthetic "(preamble)" section
    so no tokens escape the budget. Fenced code blocks are never treated as
    headings — a `# comment` line inside a shell block is not a section.
    """
    lines = text.splitlines()
    marks: list[tuple[int, int, str]] = []  # (line_idx, level, heading)

    for i, line, in_fence, _ in _scan_fences(lines):
        if in_fence:
            continue
        h = _HEADING.match(line)
        if h:
            marks.append((i, len(h.group(1)), h.group(2).strip()))

    sections: list[Section] = []
    if not marks or marks[0][0] > 0:
        end = marks[0][0] if marks else len(lines)
        body = "\n".join(lines[:end])
        if body.strip():
            sections.append(
                Section(path, "(preamble)", 0, 1, end, body)
            )

    for idx, (line_idx, level, heading) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        body = "\n".join(lines[line_idx:end])
        sections.append(
            Section(path, heading, level, line_idx + 1, end, body)
        )

    for s in sections:
        s.tokens = estimate_tokens(s.text)
    return sections


# --------------------------------------------------------------------------
# Directive polarity  (R1: rules -> judgment)
# --------------------------------------------------------------------------

# Ordered most-specific first; the first class that matches a sentence wins.
# Multi-word phrases are matched before the bare keywords they contain, so
# "must not" classifies as prohibition rather than mandate.
_POLARITY_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "prohibition",
        re.compile(
            r"\b("
            # Note the will-family negations before the `you will` mandate
            # alternative below: "You will not push to main" is a prohibition,
            # and without these it matched `you will` and inverted to mandate.
            r"never|do not|don[’']?t|must not|mustn[’']?t|shall not|"
            r"will not|won[’']?t|cannot|can[’']?t|"
            r"should not|shouldn[’']?t|avoid|forbidden|prohibited|disallowed|"
            r"under no circumstances|no room for|refrain from|"
            r"stop (?:doing|using)|do NOT"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "mandate",
        re.compile(
            r"\b("
            r"must|always|required|requires|shall|mandatory|obligatory|"
            r"you will|ensure that|make sure|has to|have to|need to|"
            r"non-negotiable|without exception"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "permission",
        re.compile(
            r"\b("
            r"as appropriate|where appropriate|when appropriate|if appropriate|"
            r"as needed|if needed|when needed|as necessary|feel free|"
            r"you may|it'?s fine to|optionally|at your discretion|"
            r"use your (?:own )?judg?ement|use your judgment"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "judgment",
        re.compile(
            r"\b("
            r"prefer|prefers|preferred|consider|weigh|lean toward|lean towards|"
            r"default to|tend to|tends to|match the|matches the|reads? like|"
            r"in the style of|unless|rather than|instead of|when in doubt|"
            r"trade-?off|balance"
            r")\b",
            re.IGNORECASE,
        ),
    ),
]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n")

# A document that *discusses* rules — an anti-pattern table, a before/after
# rewrite, a note about what a script does — is not thereby issuing them. Two
# exclusions keep the rules-ratio measuring directives rather than mentions.
# Without them, the surfaces this tool exists to audit score as pure
# prohibition simply for quoting the rules they are proposing to delete.

# (a) The keyword sits inside a quoted or code span — the sentence is citing.
#
# The single-quote alternative is boundary-gated. Ungated, an apostrophe pair
# in ordinary prose forges a span: "Claude's output must never contain the
# user's raw API key" reads `'s output must never contain the user'` as a
# quotation and silently drops a real prohibition. The lookarounds require the
# quote marks to sit outside a word, which still admits 'quoted rule' and
# rejects possessives.
_QUOTED_SPAN = re.compile(
    r"\"[^\"\n]*\"|“[^”\n]*”|‘[^’\n]*’|"
    r"(?<![A-Za-z0-9])['’][^'’\n]{4,}['’](?![A-Za-z0-9])|`[^`\n]*`"
)

# (b) The keyword's subject is a third-person inanimate referent — the sentence
# is describing behavior ("It never says delete", "the hook never fires"),
# not instructing the reader. Deliberately narrow:
#   - an actor subject ("the agent must not…") stays a directive;
#   - `that`/`which` are excluded — as relative pronouns they swallow real
#     judgement framing ("code that reads like…");
#   - `there`/`this` are excluded — "There must be a ticket for every work
#     unit" and "This must be done before every merge" are directives.
_DESCRIPTIVE_SUBJECT = re.compile(
    r"\b(?:it|they|"
    r"the\s+(?:script|tool|check|gate|hook|flag|rule|test|report|table|"
    r"column|command|file|pattern|regex|function))\s+(?:\w+ly\s+)?$",
    re.IGNORECASE,
)

# The descriptive-subject filter applies ONLY to these keywords. English does
# not disambiguate "The script must exit 0" (describing) from "The file must be
# committed" (instructing), so suppressing the must-family costs real
# directives. This is a heuristic feeding a report, and the dangerous direction
# is UNDER-counting rules — that reads as "your surface is already fine". So it
# fails open: when ambiguous, count it as a directive.
_SUPPRESSIBLE = re.compile(r"^(?:never|always|cannot|can't)$", re.IGNORECASE)


def _spans(sentence: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _QUOTED_SPAN.finditer(sentence)]


def _is_mention_not_use(sentence: str, match: re.Match) -> bool:
    """True when a polarity keyword is quoted, or merely described."""
    start = match.start()
    if any(a <= start < b for a, b in _spans(sentence)):
        return True
    if not _SUPPRESSIBLE.match(match.group(0)):
        return False
    return bool(_DESCRIPTIVE_SUBJECT.search(sentence[:start]))


# A URL slug is not a directive. `never-merge-red` in a link would otherwise
# classify the whole sentence as a prohibition.
_URL = re.compile(r"<?https?://\S+>?|<?www\.\S+>?")


def sentences(text: str) -> list[str]:
    """Split into candidate directive sentences, minus fenced code.

    URLs are left intact here so the contradiction report can quote a sentence
    faithfully; they are stripped inside classify_sentence instead.
    """
    out: list[str] = []
    for _, line, in_fence, _ in _scan_fences(text.splitlines()):
        if in_fence:
            continue
        for piece in _SENTENCE_SPLIT.split(line):
            piece = piece.strip(" \t-*|>#")
            if len(piece) >= 12:
                out.append(piece)
    return out


def classify_sentence(sentence: str) -> str:
    """Classify a sentence's directive form, counting uses and not mentions.

    URLs are blanked first: a slug like `/docs/never-merge-red` would otherwise
    read as a prohibition. Stripping here rather than in the splitter keeps
    this correct from every entry point, including direct calls.
    """
    sentence = _URL.sub(" ", sentence)
    for name, pattern in _POLARITY_PATTERNS:
        for match in pattern.finditer(sentence):
            if not _is_mention_not_use(sentence, match):
                return name
    return "descriptive"


def polarity_profile(text: str) -> tuple[dict, str]:
    counts = {
        "prohibition": 0,
        "mandate": 0,
        "permission": 0,
        "judgment": 0,
        "descriptive": 0,
    }
    for s in sentences(text):
        counts[classify_sentence(s)] += 1
    directives = {
        k: v for k, v in counts.items() if k != "descriptive"
    }
    dominant = (
        max(directives, key=lambda k: directives[k])
        if any(directives.values())
        else "descriptive"
    )
    return counts, dominant


def rules_ratio(counts: dict) -> float:
    """Share of directive sentences phrased as hard rules rather than judgment."""
    hard = counts["prohibition"] + counts["mandate"]
    soft = counts["permission"] + counts["judgment"]
    total = hard + soft
    return round(hard / total, 3) if total else 0.0


# --------------------------------------------------------------------------
# Example density  (R2: examples -> interface design)
# --------------------------------------------------------------------------

_EXAMPLE_ROW = re.compile(
    r"\b(example|e\.g\.|for instance|anti-?pattern|anti-?rationalization|"
    r"excuse\b|then\s*\||\bbad\b.*\bgood\b|instead of.*use)\b",
    re.IGNORECASE,
)


# Prose examples — the dominant form in prompts, where examples are lines
# rather than table rows. Counted separately from table rows so neither form
# is invisible.
_EXAMPLE_LEAD = re.compile(
    r"^\s*(?:[-*+]\s*|\d+[.)]\s*)?"
    r"(?:example|for example|e\.g\.|for instance|such as:|sample)\b[:\s]",
    re.IGNORECASE,
)


def count_examples(text: str) -> int:
    """Fenced blocks, example-flavoured table rows, and example-lead lines.

    Fences are counted through _scan_fences rather than by halving a raw
    delimiter count, so a nested 4-backtick block counts once instead of twice.
    """
    fences = 0
    rows = 0
    leads = 0
    for _, line, in_fence, event in _scan_fences(text.splitlines()):
        if event == "open":
            fences += 1
        if in_fence:
            continue
        stripped = line.lstrip()
        if stripped.startswith("|"):
            if _EXAMPLE_ROW.search(line):
                rows += 1
        elif _EXAMPLE_LEAD.match(line):
            leads += 1
    return fences + rows + leads


# --------------------------------------------------------------------------
# Filesystem-derivable content  ("avoid stating the obvious")
# --------------------------------------------------------------------------

_DERIVABLE_HEADING = re.compile(
    r"\b(structure|layout|directory|directories|file tree|tree|"
    r"project structure|repo structure|folder|organization)\b",
    re.IGNORECASE,
)
_PATHISH = re.compile(r"(^|\s)([\w.\-]+/)+[\w.\-]*|[│├└─]|^\s*[\w.\-]+/\s*$")


def is_derivable(section: Section) -> bool:
    """A section whose content mostly restates what `ls` would show."""
    body_lines = [
        ln for ln in section.text.splitlines()[1:] if ln.strip()
    ]
    if not body_lines:
        return False
    pathish = sum(1 for ln in body_lines if _PATHISH.search(ln))
    ratio = pathish / len(body_lines)
    if _DERIVABLE_HEADING.search(section.heading) and ratio >= 0.4:
        return True
    return ratio >= 0.7 and len(body_lines) >= 4


# --------------------------------------------------------------------------
# Mechanism references (input to the anchored / self-referential question)
# --------------------------------------------------------------------------

_MECHANISM_REF = re.compile(
    r"`([^`\n]{3,120})`"
)
# Deliberately excludes .md — a rule citing another *document* is prose
# pointing at prose. Only executable or machine-read surfaces (hooks, scripts,
# policy, CI config, source) can be the producer of an independent signal.
_LOOKS_LIKE_PATH = re.compile(r"^[~\w./\-]+\.(sh|py|ya?ml|toml|json|rs|ts|js)$")
_LOOKS_LIKE_CMD = re.compile(
    r"^(make|npm|bun|cargo|pytest|python3?|gh|git)\s+[~\w:./\-]+"
)


def _resolve_mechanism(repo_root: Path, ref: str) -> tuple[bool, str]:
    """(exists, scope) for a referenced path.

    Scope matters and one boolean cannot carry it. A repo-relative hook and a
    user-scope hook at `~/.claude/...` are both genuine mechanisms; an absolute
    path pointing somewhere else entirely is not part of the audited surface.
    So `~`-prefixed refs are expanded and reported as scope "user", in-repo refs
    as "repo", and anything that escapes the root resolves to not-exists rather
    than silently anchoring — `repo_root / "/abs/x.sh"` discards repo_root.
    """
    try:
        if ref.startswith("~"):
            target = Path(ref).expanduser().resolve()
            return target.exists(), "user"
        target = (repo_root / ref).resolve()
        root = repo_root.resolve()
        if not target.is_relative_to(root):
            return False, "external"
        return target.exists(), "repo"
    except (OSError, ValueError, RuntimeError):
        return False, "external"


def mechanism_refs(
    section: Section,
    repo_root: Path | None,
    receipts: dict[str, dict] | None = None,
    ambiguous_covers: "Iterable[str]" = (),
) -> list[dict]:
    """Backtick-quoted executable paths/commands in a section, with existence.

    A section referencing an *executable* file that exists is an *anchored
    candidate*: some mechanism outside the prose *may* already enforce it.
    Existence is the only thing this function can check. Two further questions
    it deliberately does not guess at:

      efficacy      does the mechanism fire at all? -> `probe`, resolved only
                    from a receipt produced by references/mechanism-probe.md
      independence  is the signal outside the governed actor's reach? -> keel

    Markdown references never qualify (see _LOOKS_LIKE_PATH).
    """
    refs: list[dict] = []
    seen: set[str] = set()
    for raw in _MECHANISM_REF.findall(section.text):
        ref = raw.strip()
        if ref in seen:
            continue
        if _LOOKS_LIKE_PATH.match(ref):
            kind = "path"
            exists, scope = (
                _resolve_mechanism(repo_root, ref) if repo_root else (False, "external")
            )
        elif _LOOKS_LIKE_CMD.match(ref):
            kind = "command"
            exists, scope = False, "command"
        else:
            continue
        seen.add(ref)
        refs.append(
            {
                "ref": ref,
                "kind": kind,
                "exists_on_disk": exists,
                "scope": scope,
                "probe": probe_state(ref, receipts, section, ambiguous_covers),
                "shows_evidence": shows_evidence(ref, receipts),
            }
        )
    return refs


# --------------------------------------------------------------------------
# Probe receipts (efficacy: does the mechanism actually fire?)
# --------------------------------------------------------------------------

# A receipt is an ATTESTATION. Nothing here observes the probe, re-runs it, or
# checks the booleans against anything — the script's only options are to
# believe the file or ignore it. That is a real limit and it is disclosed rather
# than papered over: an agent that wants a section deleted can type three
# `true`s and take the free tier, which makes the producer of the signal the
# actor being governed. `shows_evidence` is the visible tell; the durable fix is
# a runner that emits receipts from an observed run (BRO-2036, forward
# reference — no code here depends on it). See references/mechanism-probe.md.

# The three legs of a probe. Each is load-bearing, and the third most of all:
# without neutering the mechanism and watching the check go red, a green result
# cannot distinguish "the gate works" from "my test passes regardless".
_PROBE_LEGS = ("fires_on_trigger", "silent_on_non_trigger", "neutered_check_went_red")


class BadProbeReceipts(Exception):
    """The receipt file exists but is not a receipt file.

    Raised rather than defaulted to empty: a typo in the path would otherwise
    silently downgrade every anchor to "unresolved" while the run looked normal.
    """


def load_probe_receipts(path: Path) -> dict[str, dict]:
    """Read `{"probes": {"<ref>": {<leg>: bool, ...}}}` from disk.

    Probing is a runtime act, so its result reaches a static analyser only as a
    recorded receipt. Nothing here infers a probe outcome from the filesystem —
    a regex claiming a hook fires would be guessing in a confident voice, which
    is the failure mode this whole column exists to correct.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise BadProbeReceipts(str(e)) from e
    if not isinstance(raw, dict) or not isinstance(raw.get("probes"), dict):
        raise BadProbeReceipts(f"{path}: expected a top-level 'probes' object")
    # A non-dict VALUE is refused by name rather than filtered out. Dropping it
    # silently reproduced the defect the unmatched-key warning exists to close,
    # arriving through the value-type door instead of the key door: the receipt
    # vanishes and the report reads like a clean run.
    bad = sorted(k for k, v in raw["probes"].items() if not isinstance(v, dict))
    if bad:
        raise BadProbeReceipts(
            f"{path}: receipt value must be an object; got a bare literal for "
            + ", ".join(f"'{k}'" for k in bad[:5])
            + (f" (+{len(bad) - 5} more)" if len(bad) > 5 else "")
        )
    return dict(raw["probes"])


def receipt_covers(rec: dict) -> list[str]:
    """The rules a receipt claims to cover — section headings or `path#heading`."""
    c = rec.get("covers")
    if isinstance(c, str):
        c = [c]
    if not isinstance(c, list):
        return []
    return [str(x).strip() for x in c if str(x).strip()]


def section_ids(section: "Section") -> set[str]:
    """Both handles a receipt may name a section by."""
    return {section.heading.strip(), section.key.strip()}


def _path_suffix_match(claimed: str, actual: str) -> bool:
    """Do two spellings of a file path denote the same file?

    `Section.path` is whatever argv said, so the SAME section is `CLAUDE.md`,
    `/abs/path/CLAUDE.md`, or `sub/CLAUDE.md` depending on how the tool was
    invoked — including the directory-glob mode SKILL.md recommends. A qualified
    `covers` written against one spelling matched none of the others, so the
    documented remedy for ambiguity did not work in the recommended workflow.

    Compared component-wise in either direction, so `a/CLAUDE.md` and
    `b/CLAUDE.md` still do NOT match: only a true path suffix counts.
    """
    a = [p for p in actual.replace("\\", "/").split("/") if p not in ("", ".")]
    c = [p for p in claimed.replace("\\", "/").split("/") if p not in ("", ".")]
    if not a or not c:
        return False
    n = min(len(a), len(c))
    return a[-n:] == c[-n:]


def cover_matches(cover: str, section: "Section") -> bool:
    """Does one `covers` entry name this section?

    Bare heading, or `path#heading` where the path is any suffix spelling of the
    section's file.
    """
    cover = cover.strip()
    path, sep, heading = cover.rpartition("#")
    if not sep:
        path, heading = "", cover
    if heading.strip() != section.heading.strip():
        return False
    return not path.strip() or _path_suffix_match(path.strip(), section.path)


def cover_hits(
    receipts: dict[str, dict] | None, sections: "Iterable[Section]"
) -> dict[str, int]:
    """How many sections each distinct `covers` entry names.

    0 = stale (a heading renamed since the probe). >1 = AMBIGUOUS, and refused
    rather than guessed: `Conventions` appears in both CLAUDE.md and AGENTS.md,
    and SKILL.md step 1 tells you to audit them together. Promoting both on a
    receipt that probed one is a BAD DELETION, not a fail-safe one. It is the
    same rule `nearest_ref` follows for receipt keys, one level over.
    """
    sections = list(sections)
    hits: dict[str, int] = {}
    for rec in (receipts or {}).values():
        for c in receipt_covers(rec):
            if c not in hits:
                hits[c] = sum(1 for s in sections if cover_matches(c, s))
    return hits


def probe_state(
    ref: str,
    receipts: dict[str, dict] | None,
    section: "Section | None" = None,
    ambiguous: "Iterable[str]" = (),
) -> str:
    """Per-reference, PER-SECTION efficacy verdict.

    unresolved  no receipt, or a receipt whose `covers` does not name this rule
    fires       all three legs attested AND this rule is in `covers` (attested,
                not verified — see the note above `_PROBE_LEGS`)
    dead        the receipt says the probe was run and the mechanism did not fire
    incomplete  a receipt exists but does not carry all three legs; notably a
                probe with no neutered-control leg proves nothing
    unscoped    a receipt with no `covers` at all — it names no rule, so it
                promotes nothing

    Scope is the point. A probe exercises one branch of one mechanism; the
    deletion verdict is per RULE. Without `covers`, one receipt for a gate
    promotes every section in every audited file that happens to cite it — so
    "probed the rm -rf branch" would license deleting "secrets must never be
    committed". That is the citation trap this skill names, relocated from `.md`
    refs to `.sh` refs, and it is why an unscoped receipt fails CLOSED.

    A NEGATIVE finding is exempt from the scope gate on purpose: `dead` never
    promotes anything, and discarding it for a paperwork reason would repeat the
    error of throwing away the honest answer.
    """
    rec = (receipts or {}).get(ref)
    if rec is None:
        return "unresolved"
    # `is False` and `is True` throughout: a JSON-stringified "true" or a 1 must
    # not reach `fires`. This strictness is the trust boundary of the feature.
    if rec.get("fires_on_trigger") is False:
        return "dead"
    covers = receipt_covers(rec)
    if not covers:
        return "unscoped"
    if section is not None:
        applicable = [c for c in covers if cover_matches(c, section)]
        if not applicable:
            return "unresolved"
        # Every entry that reaches this section names more than one section, so
        # which one was probed is unknown. Refuse; do not pick.
        if all(c in set(ambiguous) for c in applicable):
            return "ambiguous"
    if all(rec.get(leg) is True for leg in _PROBE_LEGS):
        return "fires"
    return "incomplete"


def shows_evidence(ref: str, receipts: dict[str, dict] | None) -> bool:
    """Does the receipt show its work, or does it only assert booleans?

    Not a verification — the script cannot check an `evidence` string either.
    It is the difference between a record someone can be held to and a bare
    claim, and it is worth rendering because the two are otherwise identical in
    the report while being very different things to bet a deletion on.

    Type-checked rather than coerced. `str(True)` is `"True"`, so a stringifying
    test cleared the star for `"evidence": true` — a bare boolean is by
    definition a claim showing no work, and it is the natural thing to type for
    someone already typing three booleans. A dict is accepted because a runner
    emits an evidence OBJECT, not a sentence.
    """
    rec = (receipts or {}).get(ref)
    if not rec:
        return False
    ev = rec.get("evidence")
    if isinstance(ev, str):
        return bool(ev.strip())
    if isinstance(ev, dict):
        return bool(ev)
    return False


def nearest_ref(key: str, refs: Iterable[str]) -> str | None:
    """Best guess at the reference a receipt key was reaching for.

    The dominant error is the right mechanism under the wrong path form — a
    receipt keyed by the path you know the hook by rather than the literal
    backticked string in the surface. So basename equality is tried first and
    beats lexical similarity, which would rank a same-directory sibling above
    the same file at a different depth.

    AMBIGUITY YIELDS NOTHING. Two refs sharing a basename (`.claude/hooks/gate.sh`
    and `scripts/gate.sh`) make a confident suggestion actively harmful: the user
    probed one, is told they meant the other, takes it, and the wrong section is
    promoted with the report calling it success. A named unmatched key with no
    hint is strictly better than a hint that induces the wrong fix.
    """
    refs = sorted(set(refs))
    if not refs:
        return None
    base = key.rsplit("/", 1)[-1]
    same_base = [r for r in refs if r.rsplit("/", 1)[-1] == base]
    if same_base:
        return same_base[0] if len(same_base) == 1 else None
    close = difflib.get_close_matches(key, refs, n=2, cutoff=0.6)
    if not close:
        return None
    if len(close) > 1:
        ratio = difflib.SequenceMatcher(None, key, close[0]).ratio()
        if ratio == difflib.SequenceMatcher(None, key, close[1]).ratio():
            return None
    return close[0]


def is_negative_receipt(rec: dict) -> bool:
    """A receipt recording that the mechanism did NOT fire.

    Tracked separately everywhere because it is the one kind that applies
    without `covers` — it never promotes, so scope cannot make it dangerous,
    and discarding it would throw away the most valuable receipt in the file.
    Saying such a receipt "promoted nothing past UNRESOLVED" is false: it moves
    sections to DEAD.
    """
    return rec.get("fires_on_trigger") is False


def match_receipts(
    receipts: dict[str, dict] | None,
    refs: Iterable[str],
    live_refs: Iterable[str] = (),
    hits: dict[str, int] | None = None,
    max_unmatched: int = 10,
) -> dict:
    """What the supplied receipts actually did.

    A receipt keyed to nothing leaves its section UNRESOLVED, which is the
    fail-safe polarity and stays. The hazard is silence: without this, a file
    of carefully probed receipts keyed one path-form off produces a report
    BYTE-IDENTICAL to supplying no receipts at all, and reads as a clean run.

    Three further ways a receipt can accomplish nothing while looking applied,
    each reported rather than inferred: it names a reference the surface does
    not contain, it names one that is not a live mechanism, or its `covers`
    names a section that does not exist.
    """
    empty = {
        "loaded": 0, "matched": 0, "unmatched": [], "unmatched_total": 0,
        "unscoped": 0, "unscoped_negative": 0, "unscoped_promoted_nothing": 0,
        "inert": [], "unmatched_covers": [], "unmatched_covers_total": 0,
        "ambiguous_covers": [], "ambiguous_covers_total": 0,
    }
    if not receipts:
        return empty
    present, live = set(refs), set(live_refs)
    hits = hits or {}
    missing = sorted(k for k in receipts if k not in present)
    stale = sorted(c for c, n in hits.items() if n == 0)
    ambiguous = sorted(c for c, n in hits.items() if n > 1)
    unscoped = [r for r in receipts.values() if not receipt_covers(r)]
    # An unscoped NEGATIVE receipt still applies. Counting it with the rest is
    # what made the report print "promoted nothing" about a run that moved four
    # sections to DEAD.
    unscoped_negative = sum(1 for r in unscoped if is_negative_receipt(r))
    return {
        "loaded": len(receipts),
        "matched": len(receipts) - len(missing),
        "unmatched": [
            {"key": k, "nearest": nearest_ref(k, present)}
            for k in missing[:max_unmatched]
        ],
        "unmatched_total": len(missing),
        "unscoped": len(unscoped),
        "unscoped_negative": unscoped_negative,
        "unscoped_promoted_nothing": len(unscoped) - unscoped_negative,
        # Matched the surface but is not a live mechanism anywhere in it, so it
        # changed no state. "Matched" and "applied" are not the same word.
        "inert": sorted(k for k in receipts if k in present and k not in live),
        "unmatched_covers": stale[:max_unmatched],
        "unmatched_covers_total": len(stale),
        "ambiguous_covers": ambiguous[:max_unmatched],
        "ambiguous_covers_total": len(ambiguous),
    }


def is_live_mechanism(ref: dict) -> bool:
    """Can this reference carry a section at all?

    A path must exist. A COMMAND's existence was never checkable — `_LOOKS_LIKE_CMD`
    refs are hardcoded `exists_on_disk: False` — so under an existence test a
    fully-evidenced receipt for `make janitor` changed nothing while the report
    called it applied. But a probe receipt IS the evidence a command produces a
    signal; it is the only evidence obtainable. So a PROBED command counts, and
    an unprobed one still does not.
    """
    if ref["exists_on_disk"]:
        return True
    return ref["kind"] == "command" and ref["probe"] != "unresolved"


def anchor_state(refs: list[dict]) -> str:
    """Section-level tier, keyed on demonstrated firing rather than existence.

    none       no live mechanism is referenced
    dead       at least one live mechanism was probed and did NOT fire
    fires      every live mechanism was probed and fired
    unproven   a mechanism is present, nothing has shown all of them firing

    Order matters and `dead` dominating is the whole safety property. Under
    `any(fires)`, a section citing a working gate beside a probed-DEAD one read
    `fires` — so a user who did the honest thing and filed a negative receipt
    saying a path is unprotected had that finding discarded, and was told the
    prose now solely carrying the behavior was free to delete. A known-dead
    mechanism cannot be more proven than an unknown one.

    `unproven` is not a softer `fires`. Three hooks in the workspace this rule
    was derived from were registered, scheduled, independent, and produced no
    signal whatsoever; all three would read as anchored candidates.
    """
    live = [r for r in refs if is_live_mechanism(r)]
    if not live:
        return "none"
    if any(r["probe"] == "dead" for r in live):
        return "dead"
    if all(r["probe"] == "fires" for r in live):
        return "fires"
    return "unproven"


# "?" is the point of the column: an unprobed mechanism is an open question,
# not a quiet pass. Rendering it blank would restore the exact conflation the
# separate field exists to break.
_FIRES_CELL = {"fires": "yes", "unproven": "?", "dead": "DEAD", "none": ""}


def fires_cell(row: dict) -> str:
    """The firing cell for a section row — `yes*` when the receipt is bare.

    A three-boolean receipt with nothing behind it and a receipt quoting exit
    codes and commands both resolve to `fires`, because the script can verify
    neither. They should not LOOK the same, so the one that shows no work is
    starred.
    """
    state = row.get("anchor_state", "none")
    if state != "fires":
        return _FIRES_CELL[state]
    firing = [r for r in row.get("mechanism_refs", []) if r.get("probe") == "fires"]
    return "yes" if all(r.get("shows_evidence") for r in firing) else "yes*"


# --------------------------------------------------------------------------
# Duplication  (R4: repetition -> single description)
# --------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")


def normalize_words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def shingles(text: str, k: int = 8) -> set[tuple[str, ...]]:
    words = normalize_words(text)
    if len(words) < k:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + k]) for i in range(len(words) - k + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return round(inter / union, 3) if union else 0.0


def _normalized_digest(text: str) -> str:
    return hashlib.sha1(" ".join(normalize_words(text)).encode()).hexdigest()


def find_duplicates(
    sections: list[Section],
    threshold: float = 0.25,
    min_tokens: int = 40,
    max_results: int = 50,
    # Above the 92-skill / 1523-section monorepo corpus, so a realistic run is
    # never silently clipped; the cap exists only to bound pathological input.
    max_sections: int = 2500,
) -> list[dict]:
    """Near-duplicate section pairs, with bounded retention.

    The first version scored all n(n-1)/2 pairs AND retained every match as a
    dict before sorting — 499,500 dicts / 186 MB on a 1000-section surface, to
    render 15 rows. Three changes bound it:

      1. Exact duplicates are grouped by content digest first, in O(n). This is
         the pathological case (a surface that repeats a block verbatim) and it
         is also the most actionable finding, so it is worth its own pass.
      2. A length-ratio prefilter skips the set intersection entirely when the
         pair cannot reach the threshold: |A∩B| <= min(|A|,|B|) and
         |A∪B| >= max(|A|,|B|), so J <= min/max.
      3. Retention is a bounded heap of max_results, not an unbounded list.
    """
    candidates = [s for s in sections if s.tokens >= min_tokens]

    # 1. Exact-duplicate grouping.
    by_digest: dict[str, list[Section]] = {}
    for s in candidates:
        by_digest.setdefault(_normalized_digest(s.text), []).append(s)

    heap: list[tuple[float, int, dict]] = []
    seq = 0

    def offer(a: Section, b: Section, score: float) -> None:
        nonlocal seq
        entry = {
            "a": a.key,
            "b": b.key,
            "similarity": score,
            "tokens_at_risk": min(a.tokens, b.tokens),
            "exact": score == 1.0,
        }
        seq += 1
        if len(heap) < max_results:
            heapq.heappush(heap, (score, seq, entry))
        elif score > heap[0][0]:
            heapq.heapreplace(heap, (score, seq, entry))

    exact_members: set[str] = set()
    for group in by_digest.values():
        if len(group) < 2:
            continue
        for s in group[1:]:
            offer(group[0], s, 1.0)
        for s in group:
            exact_members.add(s.key)

    # 2/3. Near-duplicates among the rest, sorted by shingle-set size so the
    # length bound can BREAK rather than merely skip: once |B| exceeds
    # |A|/threshold, no later B can reach the threshold either.
    rest = [s for s in candidates if s.key not in exact_members]
    truncated = 0
    if len(rest) > max_sections:
        rest.sort(key=lambda s: -s.tokens)
        truncated = len(rest) - max_sections
        rest = rest[:max_sections]

    grams = {s.key: shingles(s.text) for s in rest}
    rest.sort(key=lambda s: len(grams[s.key]))
    for i, a in enumerate(rest):
        ga = grams[a.key]
        if not ga:
            continue
        limit = len(ga) / threshold
        for b in rest[i + 1 :]:
            gb = grams[b.key]
            if len(gb) > limit:
                break
            score = jaccard(ga, gb)
            if score >= threshold:
                offer(a, b, score)

    out = [e for _, _, e in sorted(heap, key=lambda x: (-x[0], x[1]))]
    if truncated and out:
        # No silent caps: say what was dropped.
        out[0] = {**out[0], "sections_not_compared": truncated}
    return out


# --------------------------------------------------------------------------
# Contradiction candidates (the article's own diagnostic)
# --------------------------------------------------------------------------

_STOPWORDS = frozenset(
    """a an the and or but if then than that this these those of to in on at by for
    with from as is are was were be been being it its it's you your we our they them
    do does did done not no never always must should would could may might can will
    shall have has had here there when where which who whom what how why all any some
    each every other another same such only just also very more most less least own
    use used using make makes made get gets got run runs ran into out up down over
    under again further once about against between during before after above below
    off through per via etc via one two three new old first last next prev
    file files line lines code claude agent agents skill skills user users""".split()
)


def topic_words(sentence: str) -> set[str]:
    return {
        w
        for w in normalize_words(sentence)
        if len(w) >= 5 and w not in _STOPWORDS
    }


_HARD = ("prohibition", "mandate")
_SOFT = ("permission", "judgment")


def find_contradictions(
    sections: list[Section], max_results: int | None = 20
) -> list[dict]:
    """Topics carrying both a hard rule and a soft allowance, in different sections.

    This is the failure the Claude Code team found in their own transcripts:
    "leave documentation as appropriate" colliding with "DO NOT add comments".
    Output is deliberately named *candidates* — the pairing is lexical, and the
    agent adjudicates whether the two directives genuinely collide.
    """
    index: dict[str, dict[str, list[dict]]] = {}
    for sec in sections:
        for sent in sentences(sec.text):
            cls = classify_sentence(sent)
            if cls in _HARD:
                side = "hard"
            elif cls in _SOFT:
                side = "soft"
            else:
                continue
            for topic in topic_words(sent):
                index.setdefault(topic, {"hard": [], "soft": []})
                index[topic][side].append(
                    {
                        "section": sec.key,
                        "polarity": cls,
                        "sentence": sent[:160],
                    }
                )

    # One row per topic. Selecting the representative pair directly is O(H+S)
    # per topic; materialising the full hard x soft cross-product and deduping
    # afterwards was O(H*S) and peaked at 2.9 GB / 39 s on a 61k-token surface
    # with concentrated vocabulary — to return three rows.
    out: list[dict] = []
    for topic, sides in index.items():
        hard, soft = sides["hard"], sides["soft"]
        if not (hard and soft):
            continue

        # Prefer a cross-section collision: a local pair is more often a rule
        # beside its own stated carve-out, and so ranks lower.
        h0 = hard[0]
        pair = next(
            ((h0, s) for s in soft if s["section"] != h0["section"]),
            None,
        ) or next(
            ((h, soft[0]) for h in hard if h["section"] != soft[0]["section"]),
            None,
        )
        if pair is None:
            pair = (h0, soft[0])

        h, s = pair
        out.append(
            {
                "topic": topic,
                "hard": h,
                "soft": s,
                # Same-section collisions are NOT excluded. A sentence carries
                # exactly one polarity, so it can never pair with itself, and
                # the article's own example ("DO NOT add comments" against
                # "leave documentation as appropriate") is precisely a local
                # collision. Excluding them also made contradiction detection
                # dead in prompt mode, where everything is one section.
                "same_section": h["section"] == s["section"],
                # Rarer topic words make for more specific collisions.
                "specificity": round(1 / (len(hard) + len(soft)), 3),
            }
        )

    out.sort(key=lambda c: (c["same_section"], -c["specificity"], c["topic"]))
    return out if max_results is None else out[:max_results]


# --------------------------------------------------------------------------
# Progressive disclosure  (R3)
# --------------------------------------------------------------------------


_OUTBOUND_LINK = re.compile(r"\[[^\]]+\]\(([^)]+\.md[^)]*)\)|`([\w./\-]+\.md)`")


def count_outbound_links(text: str) -> int:
    """Links out to other documents — the observable trace of deferred loading."""
    return len(
        {
            (m[0] or m[1])
            for m in _OUTBOUND_LINK.findall(text)
            if (m[0] or m[1])
        }
    )


def disclosure_check(
    path: Path, text: str, tokens: int, split_threshold: int
) -> dict | None:
    """Flag a surface that carries everything upfront.

    Two signals, because the right one differs by surface: a SKILL.md defers by
    shipping a `references/` dir, a repo CLAUDE.md defers by pointing at other
    documents. `docs/` is not counted — nearly every repo has one, so it would
    make this check pass vacuously.
    """
    if tokens < split_threshold:
        return None
    parent = path.parent
    has_ref_dir = any(
        (parent / d).is_dir() for d in ("references", "reference")
    )
    links = count_outbound_links(text)
    defers = has_ref_dir or links >= 3
    return {
        "path": str(path),
        "tokens": tokens,
        "threshold": split_threshold,
        "has_reference_dir": has_ref_dir,
        "outbound_doc_links": links,
        "defers": defers,
        "note": (
            f"over threshold but defers ({'references/ dir' if has_ref_dir else ''}"
            f"{' + ' if has_ref_dir and links else ''}"
            f"{f'{links} outbound doc links' if links else ''}) — confirm the "
            "bulk actually lives there"
            if defers
            else "over threshold with no references/ dir and <3 outbound links "
            "— everything loads upfront"
        ),
    }


# --------------------------------------------------------------------------
# Audit driver
# --------------------------------------------------------------------------

DEFAULT_BUDGET = 5000
DEFAULT_SPLIT_THRESHOLD = 2500

_SURFACE_GLOBS = ("CLAUDE.md", "AGENTS.md", "SKILL.md", "AGENT.md")


class NoSurfacesFound(Exception):
    """A directory was audited but contained no known context surface.

    Reported rather than swallowed: an empty run otherwise prints
    "0 tok vs target 5000 -> within" and congratulates the user for pointing
    the tool at the wrong directory.
    """


def collect_paths(inputs: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in inputs:
        p = Path(raw).expanduser()
        if p.is_dir():
            for name in _SURFACE_GLOBS:
                paths.extend(sorted(p.rglob(name)))
        elif p.is_file():
            paths.append(p)
        else:
            raise FileNotFoundError(raw)
    # Stable order, no duplicates.
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def audit(
    inputs: Iterable[str],
    budget: int = DEFAULT_BUDGET,
    split_threshold: int = DEFAULT_SPLIT_THRESHOLD,
    repo_root: Path | None = None,
    dup_threshold: float = 0.25,
    max_contradictions: int = 20,
    probe_receipts: dict[str, dict] | None = None,
) -> dict:
    paths = collect_paths(inputs)
    if not paths:
        raise NoSurfacesFound(", ".join(str(i) for i in inputs))
    all_sections: list[Section] = []
    disclosure: list[dict] = []
    per_file: list[dict] = []

    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        secs = split_sections(text, str(path))
        for s in secs:
            s.polarity, s.dominant = polarity_profile(s.text)
            s.examples = count_examples(s.text)
            s.derivable = is_derivable(s)
        file_tokens = estimate_tokens(text)
        per_file.append(
            {
                "path": str(path),
                "tokens": file_tokens,
                "sections": len(secs),
                "lines": len(text.splitlines()),
            }
        )
        d = disclosure_check(path, text, file_tokens, split_threshold)
        if d:
            disclosure.append(d)
        all_sections.extend(secs)

    # Mechanism refs resolve in a SECOND pass: whether a `covers` entry is
    # ambiguous is a property of the whole audited set, not of one file, and a
    # per-file loop cannot see that `Conventions` exists in two of them.
    hits = cover_hits(probe_receipts, all_sections)
    ambiguous = {c for c, n in hits.items() if n > 1}
    for s in all_sections:
        s.mechanism_refs = mechanism_refs(s, repo_root, probe_receipts, ambiguous)

    contradictions = find_contradictions(all_sections, max_results=None)
    total = sum(f["tokens"] for f in per_file)
    combined = {
        "prohibition": 0,
        "mandate": 0,
        "permission": 0,
        "judgment": 0,
        "descriptive": 0,
    }
    for s in all_sections:
        for k, v in s.polarity.items():
            combined[k] += v

    section_rows = [
        {
            "key": s.key,
            "heading": s.heading,
            "level": s.level,
            "lines": f"{s.start_line}-{s.end_line}",
            "tokens": s.tokens,
            "dominant": s.dominant,
            "rules_ratio": rules_ratio(s.polarity),
            "polarity": s.polarity,
            "examples": s.examples,
            "derivable": s.derivable,
            "mechanism_refs": s.mechanism_refs,
            # Existence. Retained verbatim — it is still the input to the
            # question, it is just no longer the answer to it.
            "anchored_candidate": any(
                r["exists_on_disk"] for r in s.mechanism_refs
            ),
            # Firing. Separate field because a mechanism can exist, be
            # registered, run on schedule, and still emit nothing.
            "anchor_state": anchor_state(s.mechanism_refs),
        }
        for s in sorted(all_sections, key=lambda x: -x.tokens)
    ]

    return {
        "tokenizer": tokenizer_name(),
        "budget": {
            "target": budget,
            "actual": total,
            "over_by": max(0, total - budget),
            "within": total <= budget,
        },
        "files": per_file,
        "polarity_total": combined,
        "rules_ratio": rules_ratio(combined),
        "anchors": {
            state: sum(1 for r in section_rows if r["anchor_state"] == state)
            for state in ("fires", "unproven", "dead", "none")
        },
        # Loaded / applied / keyed-to-nothing. One block rather than a bare
        # count, because "how many receipts did you read" is the least useful
        # of the three: a receipt that matched no reference did nothing.
        "probe_receipts": match_receipts(
            probe_receipts,
            [r["ref"] for s in all_sections for r in s.mechanism_refs],
            [
                r["ref"]
                for s in all_sections
                for r in s.mechanism_refs
                if is_live_mechanism(r)
            ],
            hits,
        ),
        # Sections promoted to `fires` on a receipt that asserts booleans and
        # shows nothing. Counted separately from `anchors` so the state map
        # stays a clean state->count, and surfaced because a bare attestation
        # is the weakest thing a deletion can rest on.
        "attestations_without_evidence": sum(
            1 for r in section_rows if fires_cell(r) == "yes*"
        ),
        "sections": section_rows,
        "duplication": find_duplicates(all_sections, dup_threshold),
        "contradictions": contradictions[:max_contradictions],
        "contradictions_total": len(contradictions),
        "disclosure": disclosure,
    }


def audit_prompt(text: str, max_contradictions: int = 20) -> dict:
    """Prompt mode — the same signals, minus the always-on budget question."""
    secs = split_sections(text, "<prompt>")
    for s in secs:
        s.polarity, s.dominant = polarity_profile(s.text)
        s.examples = count_examples(s.text)
    counts, dominant = polarity_profile(text)
    contradictions = find_contradictions(secs, max_results=None)
    return {
        "tokenizer": tokenizer_name(),
        "tokens": estimate_tokens(text),
        "sections": len(secs),
        "polarity_total": counts,
        "rules_ratio": rules_ratio(counts),
        "dominant": dominant,
        "examples": count_examples(text),
        "contradictions": contradictions[:max_contradictions],
        "contradictions_total": len(contradictions),
        "duplication": find_duplicates(secs, 0.3, min_tokens=25),
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _render_receipts(rc: dict) -> list[str]:
    """The receipts line — always shown once receipts were supplied.

    Stated as "N of M applied" rather than left to inference: the count of
    receipts READ tells a reader nothing, and a file that applied to nothing at
    all otherwise renders exactly like no file.
    """
    if not rc.get("loaded"):
        return []
    # "matched", not "applied" — a key can match a reference in the surface and
    # still change nothing.
    out = [f"**Probe receipts** — {rc['matched']} of {rc['loaded']} matched a "
           f"reference in the audited surface(s)."]
    total = rc.get("unmatched_total", 0)
    if total:
        shown = rc.get("unmatched") or []
        more = f" (showing {len(shown)})" if total > len(shown) else ""
        out[0] += (
            f" **{total} key(s) matched nothing and did nothing**{more}:"
        )
        for u in shown:
            hint = (
                f" — did you mean `{u['nearest']}`?"
                if u["nearest"]
                else " — no unambiguous near match"
            )
            out.append(f"- `{u['key']}`{hint}")
        out.append(
            "\nA receipt key is the literal backticked reference as it appears in "
            "the surface (`.control/policy.yaml`, `make janitor`), not the path "
            "you know the mechanism by."
        )
    if rc.get("inert"):
        out.append(
            f"\n**{len(rc['inert'])} matched key(s) are inert** — referenced, but "
            "not a live mechanism anywhere in the surface, so no section changed "
            "state: " + ", ".join(f"`{k}`" for k in rc["inert"][:10]) + "."
        )
    # Split, because these two say opposite things about what the run did. The
    # blanket version printed "promoted nothing past UNRESOLVED" about a run
    # that moved four sections to DEAD.
    if rc.get("unscoped_promoted_nothing"):
        out.append(
            f"\n**{rc['unscoped_promoted_nothing']} receipt(s) carry no `covers`** "
            "and therefore promoted nothing past UNRESOLVED. A probe exercises one "
            "branch of one mechanism; the deletion verdict is per rule, so a receipt "
            "has to name the rules it covers — `references/mechanism-probe.md`."
        )
    if rc.get("unscoped_negative"):
        out.append(
            f"\n**{rc['unscoped_negative']} receipt(s) record a NEGATIVE finding "
            "with no `covers`** — and those DID apply. A mechanism that does not "
            "fire promotes nothing, so scope cannot make it dangerous: every "
            "section citing it reads DEAD."
        )
    ambig = rc.get("ambiguous_covers_total", 0)
    if ambig:
        listed = ", ".join(f"`{c}`" for c in (rc.get("ambiguous_covers") or []))
        out.append(
            f"\n**{ambig} `covers` entry(ies) name MORE THAN ONE section** — "
            f"{listed}. Which one was probed is unknown, so none is promoted. "
            "Qualify as `path#heading`; if two sections in one file share a "
            "heading, no `covers` form can separate them — split the heading."
        )
    stale = rc.get("unmatched_covers_total", 0)
    if stale:
        listed = ", ".join(f"`{c}`" for c in (rc.get("unmatched_covers") or []))
        out.append(
            f"\n**{stale} `covers` entry(ies) name no section** in the audited "
            f"surface(s) — {listed}. A heading that has since been renamed stops "
            "promoting, which is the safe direction, but silently."
        )
    if (
        total
        or rc.get("inert")
        or rc.get("unscoped_promoted_nothing")
        or ambig
        or stale
    ):
        out.append(
            "\nThe receipts reported above applied nothing — they leave their "
            "sections UNRESOLVED rather than promoting them, which is the safe "
            "direction.\n"
        )
    else:
        out.append("")
    return out


def render(report: dict) -> str:
    L: list[str] = []
    add = L.append

    if "budget" in report:
        b = report["budget"]
        verdict = "within" if b["within"] else f"over by {b['over_by']}"
        add(f"# Context audit ({report['tokenizer']})\n")
        add(f"**Budget** — {b['actual']} tok vs target {b['target']} → {verdict}\n")
        add("| File | Tokens | Lines | Sections |")
        add("|---|---:|---:|---:|")
        for f in report["files"]:
            add(f"| {f['path']} | {f['tokens']} | {f['lines']} | {f['sections']} |")
        add("")
    else:
        add(f"# Prompt audit ({report['tokenizer']})\n")
        add(
            f"**{report['tokens']} tok · dominant form: {report['dominant']} · "
            f"rules-ratio {report['rules_ratio']} · {report['examples']} examples**\n"
        )

    p = report["polarity_total"]
    add(
        f"**Directive mix** — prohibition {p['prohibition']} · mandate {p['mandate']} "
        f"· permission {p['permission']} · judgment {p['judgment']} "
        f"→ rules-ratio **{report['rules_ratio']}** "
        f"(share of directives phrased as hard rules)\n"
    )

    if report.get("sections") and isinstance(report["sections"], list):
        n_sec = len(report["sections"])
        more = f" — showing 30 of {n_sec}" if n_sec > 30 else ""
        add(f"## Sections by weight{more}\n")
        add("| Section | Tok | Form | Rules | Ex | Derivable | Anchored? | Fires? |")
        add("|---|---:|---|---:|---:|:-:|:-:|:-:|")
        for s in report["sections"][:30]:
            add(
                f"| {s['heading'][:44]} | {s['tokens']} | {s['dominant']} | "
                f"{s['rules_ratio']} | {s['examples']} | "
                f"{'yes' if s['derivable'] else ''} | "
                # Keyed on anchor_state, not `anchored_candidate`: a probed
                # command is a live mechanism whose file existence was never
                # checkable, and rendering it as no candidate at all while the
                # firing column said `yes` was incoherent.
                f"{'cand' if s.get('anchor_state', 'none') != 'none' else ''} | "
                f"{fires_cell(s)} |"
            )
        add("")
        a = report.get("anchors") or {}
        if a.get("unproven") or a.get("dead"):
            add(
                f"**Anchors** — {a.get('fires', 0)} probed firing · "
                f"**{a.get('unproven', 0)} UNRESOLVED** · {a.get('dead', 0)} probed dead. "
                "An UNRESOLVED anchor is a mechanism that exists; nothing here shows "
                "it produces a signal. Probe it before deleting the prose it "
                "supposedly makes free — `references/mechanism-probe.md`, then "
                "`--probe-receipts`.\n"
            )
        bare = report.get("attestations_without_evidence", 0)
        if bare:
            add(
                f"`*` — {bare} section(s) rest on a receipt that asserts three "
                "booleans and shows no work. A receipt is an attestation this "
                "script cannot verify; if the actor that wants the deletion also "
                "wrote the receipt, this column is decorative. Have a runner emit "
                "it — `references/mechanism-probe.md`.\n"
            )
        L.extend(_render_receipts(report.get("probe_receipts") or {}))

    if report.get("contradictions"):
        shown = min(10, len(report["contradictions"]))
        total_c = report.get("contradictions_total", len(report["contradictions"]))
        suffix = f" — showing {shown} of {total_c}" if total_c > shown else ""
        add(f"## Contradiction candidates (agent adjudicates){suffix}\n")
        for c in report["contradictions"][:10]:
            local = " _(same section — may be a rule plus its carve-out)_" if c["same_section"] else ""
            add(f"- **{c['topic']}**{local}")
            add(f"  - `{c['hard']['polarity']}` {c['hard']['section']} — {c['hard']['sentence']}")
            add(f"  - `{c['soft']['polarity']}` {c['soft']['section']} — {c['soft']['sentence']}")
        add("")

    if report.get("duplication"):
        n_dup = len(report["duplication"])
        more = f" — showing 15 of {n_dup} retained" if n_dup > 15 else ""
        add(f"## Near-duplicate sections{more}\n")
        add("| A | B | Jaccard | Tok at risk |")
        add("|---|---|---:|---:|")
        for d in report["duplication"][:15]:
            add(f"| {d['a']} | {d['b']} | {d['similarity']} | {d['tokens_at_risk']} |")
        add("")

    if report.get("disclosure"):
        add("## Progressive-disclosure flags\n")
        for d in report["disclosure"]:
            add(f"- `{d['path']}` — {d['tokens']} tok — {d['note']}")
        add("")

    add(
        "> Evidence only. Keep / relocate / delete requires knowing whether an "
        "independent mechanism already enforces each rule — two questions this "
        "script answers neither of: does it fire (probe it), and is the signal "
        "outside the governed actor's reach (`keel`). Read the SKILL.md "
        "adjudication table."
    )
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("paths", nargs="*", help="files or directories to audit")
    ap.add_argument("--prompt-text", help="audit a bare prompt string")
    ap.add_argument("--prompt-file", help="audit a prompt from a file")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    ap.add_argument("--split-threshold", type=int, default=DEFAULT_SPLIT_THRESHOLD)
    ap.add_argument("--dup-threshold", type=float, default=0.25)
    ap.add_argument("--max-contradictions", type=int, default=20)
    ap.add_argument("--repo-root", help="root for mechanism-reference existence checks")
    ap.add_argument(
        "--probe-receipts",
        help=(
            "JSON receipts from references/mechanism-probe.md; without it every "
            "anchor stays UNRESOLVED, which is the honest default"
        ),
    )
    ap.add_argument("--json", action="store_true")
    # Exit-code gates. Without one of these the tool always exits 0 — it is a
    # report, not a judge. Opting in is what lets CI actually enforce something,
    # rather than run the command and describe it as a gate.
    ap.add_argument(
        "--fail-over-budget",
        action="store_true",
        help="exit 1 when the surface exceeds --budget",
    )
    ap.add_argument(
        "--max-rules-ratio",
        type=float,
        help="exit 1 when the hard-rule share of directives exceeds this",
    )
    ap.add_argument(
        "--fail-on-unmatched-receipts",
        action="store_true",
        help=(
            "exit 1 when a supplied receipt key, or a `covers` entry, names "
            "nothing in the audited surface(s)"
        ),
    )
    args = ap.parse_args(argv)

    if args.prompt_text is not None or args.prompt_file is not None:
        # `--fail-over-budget` in prompt mode used to pass silently: the prompt
        # report has no budget key, so the .get() default returned "within".
        # That is the round-1 MAJOR-4 shape (a gate that cannot fail) wearing a
        # different mode, so it is refused outright rather than defaulted.
        if args.fail_over_budget:
            print(
                "error: --fail-over-budget does not apply in prompt mode "
                "(a prompt has no always-on budget); use --max-rules-ratio",
                file=sys.stderr,
            )
            return 2
        # Same shape: prompt mode never resolves mechanism references, so
        # accepting receipts here would take a file and do nothing with it —
        # and the receipts gate would be a check that cannot fail.
        if args.probe_receipts or args.fail_on_unmatched_receipts:
            print(
                "error: --probe-receipts/--fail-on-unmatched-receipts do not "
                "apply in prompt mode (a prompt references no mechanisms to probe)",
                file=sys.stderr,
            )
            return 2
        if args.prompt_file:
            try:
                text = Path(args.prompt_file).expanduser().read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError as e:
                print(f"error: cannot read prompt file: {e}", file=sys.stderr)
                return 2
        else:
            text = args.prompt_text
        report = audit_prompt(text, max_contradictions=args.max_contradictions)
    elif args.paths:
        root = Path(args.repo_root).expanduser() if args.repo_root else None
        if root is None:
            first = Path(args.paths[0]).expanduser()
            root = first if first.is_dir() else first.parent
        receipts: dict[str, dict] | None = None
        if args.probe_receipts:
            try:
                receipts = load_probe_receipts(
                    Path(args.probe_receipts).expanduser()
                )
            except BadProbeReceipts as e:
                print(f"error: cannot read probe receipts: {e}", file=sys.stderr)
                return 2
        try:
            report = audit(
                args.paths,
                budget=args.budget,
                split_threshold=args.split_threshold,
                repo_root=root,
                dup_threshold=args.dup_threshold,
                max_contradictions=args.max_contradictions,
                probe_receipts=receipts,
            )
        except FileNotFoundError as e:
            print(f"error: no such path: {e}", file=sys.stderr)
            return 2
        except NoSurfacesFound as e:
            print(
                f"error: no {'/'.join(_SURFACE_GLOBS)} found under {e}",
                file=sys.stderr,
            )
            return 2
    else:
        ap.print_help()
        return 2

    print(json.dumps(report, indent=2) if args.json else render(report))

    failures: list[str] = []
    if args.fail_over_budget and not report["budget"]["within"]:
        b = report["budget"]
        failures.append(f"over budget by {b['over_by']} tokens")
    if args.max_rules_ratio is not None and report["rules_ratio"] > args.max_rules_ratio:
        failures.append(
            f"rules-ratio {report['rules_ratio']} exceeds {args.max_rules_ratio}"
        )
    if args.fail_on_unmatched_receipts:
        rc_ = report.get("probe_receipts") or {}
        n = rc_.get("unmatched_total", 0) + rc_.get("unmatched_covers_total", 0)
        if n:
            failures.append(f"{n} receipt key(s)/covers entry(ies) named nothing")
    if failures:
        print("\nFAIL: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
