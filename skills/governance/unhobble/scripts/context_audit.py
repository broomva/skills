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

# Prose-markdown chars-per-token. Calibrated against tiktoken cl100k over nine
# real governance surfaces (CLAUDE.md, AGENTS.md, METALAYER.md, SKILL.md files,
# reference docs): observed range 3.71-4.37, mean 4.06, median 4.25. The mean is
# used, so the estimate lands within roughly ±8% on this shape of text.
#
# Used only when tiktoken is unavailable; every consumer labels the result
# "estimate(...)" so a reader never mistakes it for an exact count. Budget
# decisions near a threshold deserve the real tokenizer — `pip install tiktoken`.
_CHARS_PER_TOKEN = 4.06


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
_FENCE = re.compile(r"^\s*(```|~~~)")


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
    fence: str | None = None

    for i, line in enumerate(lines):
        f = _FENCE.match(line)
        if f:
            tok = f.group(1)
            if fence is None:
                fence = tok
            elif line.strip().startswith(fence):
                fence = None
            continue
        if fence is not None:
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
_QUOTED_SPAN = re.compile(
    r"\"[^\"\n]*\"|“[^”\n]*”|'[^'\n]{4,}'|`[^`\n]*`"
)

# (b) The keyword's subject is a third-person inanimate referent — the sentence
# is describing behavior ("It never says delete", "the script must exit 0"),
# not instructing the reader. Deliberately narrow:
#   - an actor subject ("the agent must not…") stays a directive, because that
#     is genuine constraint language;
#   - `that` and `which` are excluded — in this corpus they are relative
#     pronouns far more often than demonstrative subjects, and treating them as
#     descriptive swallows real judgement framing ("code that reads like…").
_DESCRIPTIVE_SUBJECT = re.compile(
    r"\b(?:it|this|they|there|"
    r"the\s+(?:script|tool|check|gate|hook|flag|rule|test|report|table|"
    r"column|command|file|pattern|regex|function))\s+(?:\w+ly\s+)?$",
    re.IGNORECASE,
)


def _spans(sentence: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _QUOTED_SPAN.finditer(sentence)]


def _is_mention_not_use(sentence: str, match: re.Match) -> bool:
    """True when a polarity keyword is quoted, or merely described."""
    start = match.start()
    if any(a <= start < b for a, b in _spans(sentence)):
        return True
    return bool(_DESCRIPTIVE_SUBJECT.search(sentence[:start]))


def sentences(text: str) -> list[str]:
    """Split into candidate directive sentences, minus fenced code."""
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        f = _FENCE.match(line)
        if f:
            tok = f.group(1)
            if fence is None:
                fence = tok
            elif line.strip().startswith(fence):
                fence = None
            continue
        if fence is not None:
            continue
        for piece in _SENTENCE_SPLIT.split(line):
            piece = piece.strip(" \t-*|>#")
            if len(piece) >= 12:
                out.append(piece)
    return out


def classify_sentence(sentence: str) -> str:
    """Classify a sentence's directive form, counting uses and not mentions."""
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


def count_examples(text: str) -> int:
    """Fenced blocks plus example-flavoured table rows."""
    fences = len(re.findall(r"^\s*(?:```|~~~)", text, re.MULTILINE)) // 2
    rows = sum(
        1
        for line in text.splitlines()
        if line.lstrip().startswith("|") and _EXAMPLE_ROW.search(line)
    )
    return fences + rows


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
            exists = bool(repo_root and (repo_root / ref).exists())
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
    sections: list[Section], max_results: int = 20
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

    out: list[dict] = []
    for topic, sides in index.items():
        if not (sides["hard"] and sides["soft"]):
            continue
        for h in sides["hard"]:
            for s in sides["soft"]:
                if h["section"] == s["section"]:
                    continue
                out.append(
                    {
                        "topic": topic,
                        "hard": h,
                        "soft": s,
                        # Rarer topic words make for more specific collisions.
                        "specificity": round(
                            1 / (len(sides["hard"]) + len(sides["soft"])), 3
                        ),
                    }
                )
    out.sort(key=lambda c: (-c["specificity"], c["topic"]))
    # One row per topic keeps the report readable.
    seen: set[str] = set()
    deduped = []
    for c in out:
        if c["topic"] in seen:
            continue
        seen.add(c["topic"])
        deduped.append(c)
    return deduped[:max_results]


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
) -> dict:
    paths = collect_paths(inputs)
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
        "contradictions": find_contradictions(all_sections),
        "disclosure": disclosure,
    }


def audit_prompt(text: str) -> dict:
    """Prompt mode — the same signals, minus the always-on budget question."""
    secs = split_sections(text, "<prompt>")
    for s in secs:
        s.polarity, s.dominant = polarity_profile(s.text)
        s.examples = count_examples(s.text)
    counts, dominant = polarity_profile(text)
    return {
        "tokenizer": tokenizer_name(),
        "tokens": estimate_tokens(text),
        "sections": len(secs),
        "polarity_total": counts,
        "rules_ratio": rules_ratio(counts),
        "dominant": dominant,
        "examples": count_examples(text),
        "contradictions": find_contradictions(secs),
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
        add("## Contradiction candidates (agent adjudicates)\n")
        for c in report["contradictions"][:10]:
            add(f"- **{c['topic']}**")
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
    ap.add_argument("--repo-root", help="root for mechanism-reference existence checks")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.prompt_text or args.prompt_file:
        text = (
            args.prompt_text
            if args.prompt_text
            else Path(args.prompt_file).expanduser().read_text(encoding="utf-8")
        )
        report = audit_prompt(text)
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
            )
        except FileNotFoundError as e:
            print(f"error: no such path: {e}", file=sys.stderr)
            return 2
    else:
        ap.print_help()
        return 2

    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
