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
  contradiction topics carrying both a prohibition and
                a permission/judgment, across sections  (the article's own diagnostic)

Usage:
    context_audit.py <path> [<path> ...] [--budget N] [--json] [--repo-root DIR]
    context_audit.py --prompt-text "..." [--json]
    context_audit.py --prompt-file prompt.md [--json]
"""

from __future__ import annotations

import argparse
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
    """Yield (index, line, in_fence) with CommonMark-ish fence nesting."""
    open_char: str | None = None
    open_len = 0
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if m:
            run = m.group(1)
            if open_char is None:
                open_char, open_len = run[0], len(run)
                yield i, line, True
                continue
            if run[0] == open_char and len(run) >= open_len:
                open_char, open_len = None, 0
                yield i, line, True
                continue
        yield i, line, open_char is not None


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

    for i, line, in_fence in _scan_fences(lines):
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
            r"never|do not|don't|dont|must not|mustn't|shall not|cannot|can't|"
            r"should not|shouldn't|avoid|forbidden|prohibited|disallowed|"
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
    r"\"[^\"\n]*\"|“[^”\n]*”|(?<![A-Za-z0-9])'[^'\n]{4,}'(?![A-Za-z0-9])|`[^`\n]*`"
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
    for _, line, in_fence in _scan_fences(text.splitlines()):
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
    """Fenced blocks, example-flavoured table rows, and example-lead lines."""
    fences = len(re.findall(r"^\s*(?:```|~~~)", text, re.MULTILINE)) // 2
    rows = 0
    leads = 0
    for line in text.splitlines():
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
_LOOKS_LIKE_PATH = re.compile(r"^[\w./\-]+\.(sh|py|ya?ml|toml|json|rs|ts|js)$")
_LOOKS_LIKE_CMD = re.compile(r"^(make|npm|bun|cargo|pytest|python3?|gh|git)\s+[\w:.\-]+")


def _within_root(repo_root: Path, ref: str) -> bool:
    """Exists AND lives inside the audited repo.

    An absolute ref (or one escaping via ../) would otherwise mark a section
    anchored against a file that is not part of the surface being audited —
    `repo_root / "/abs/x.sh"` silently discards repo_root.
    """
    if Path(ref).is_absolute():
        return False
    try:
        target = (repo_root / ref).resolve()
        return target.is_relative_to(repo_root.resolve()) and target.exists()
    except (OSError, ValueError):
        return False


def mechanism_refs(section: Section, repo_root: Path | None) -> list[dict]:
    """Backtick-quoted executable paths/commands in a section, with existence.

    A section referencing an *executable* file that exists is an *anchored
    candidate*: some mechanism outside the prose may already enforce it.
    Existence is the only thing checked here — whether that mechanism actually
    produces a signal the agent cannot write to is keel's question, not this
    script's. Markdown references never qualify (see _LOOKS_LIKE_PATH).
    """
    refs: list[dict] = []
    seen: set[str] = set()
    for raw in _MECHANISM_REF.findall(section.text):
        ref = raw.strip()
        if ref in seen:
            continue
        if _LOOKS_LIKE_PATH.match(ref):
            kind = "path"
            exists = bool(repo_root and _within_root(repo_root, ref))
        elif _LOOKS_LIKE_CMD.match(ref):
            kind = "command"
            exists = False
        else:
            continue
        seen.add(ref)
        refs.append({"ref": ref, "kind": kind, "exists_on_disk": exists})
    return refs


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


def find_duplicates(
    sections: list[Section], threshold: float = 0.25, min_tokens: int = 40
) -> list[dict]:
    candidates = [s for s in sections if s.tokens >= min_tokens]
    grams = {s.key: shingles(s.text) for s in candidates}
    pairs: list[dict] = []
    for i, a in enumerate(candidates):
        for b in candidates[i + 1 :]:
            score = jaccard(grams[a.key], grams[b.key])
            if score >= threshold:
                pairs.append(
                    {
                        "a": a.key,
                        "b": b.key,
                        "similarity": score,
                        "tokens_at_risk": min(a.tokens, b.tokens),
                    }
                )
    pairs.sort(key=lambda p: -p["similarity"])
    return pairs


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
            s.mechanism_refs = mechanism_refs(s, repo_root)
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
        "sections": [
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
                "anchored_candidate": any(
                    r["exists_on_disk"] for r in s.mechanism_refs
                ),
            }
            for s in sorted(all_sections, key=lambda x: -x.tokens)
        ],
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
        add("## Sections by weight\n")
        add("| Section | Tok | Form | Rules | Ex | Derivable | Anchored? |")
        add("|---|---:|---|---:|---:|:-:|:-:|")
        for s in report["sections"][:30]:
            add(
                f"| {s['heading'][:44]} | {s['tokens']} | {s['dominant']} | "
                f"{s['rules_ratio']} | {s['examples']} | "
                f"{'yes' if s['derivable'] else ''} | "
                f"{'cand' if s['anchored_candidate'] else ''} |"
            )
        add("")

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
        add("## Near-duplicate sections\n")
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
        "independent mechanism already enforces each rule — run `keel` or read "
        "the SKILL.md adjudication table."
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
    args = ap.parse_args(argv)

    if args.prompt_text or args.prompt_file:
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
        try:
            report = audit(
                args.paths,
                budget=args.budget,
                split_threshold=args.split_threshold,
                repo_root=root,
                dup_threshold=args.dup_threshold,
                max_contradictions=args.max_contradictions,
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
    if args.fail_over_budget and not report.get("budget", {}).get("within", True):
        b = report["budget"]
        failures.append(f"over budget by {b['over_by']} tokens")
    if args.max_rules_ratio is not None and report["rules_ratio"] > args.max_rules_ratio:
        failures.append(
            f"rules-ratio {report['rules_ratio']} exceeds {args.max_rules_ratio}"
        )
    if failures:
        print("\nFAIL: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
