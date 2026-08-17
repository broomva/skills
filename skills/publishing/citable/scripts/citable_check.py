#!/usr/bin/env python3
"""citable_check — lint authored text against measured AI-citation effects.

Every threshold here traces to a published study, not to taste. Sources:

  Scrunch (2026-05-06) — 12,000 LinkedIn post observations from ChatGPT
  2026-01-15..04-15, 21 content dimensions, causal estimates via double
  machine learning. Includes posts ChatGPT considered and declined to cite.
  https://scrunch.com/blog/linkedin-posts-robots-cant-resist-what-data-says-about-chatgpt-citations

  Semrush (2026) — 325,000 prompts across ChatGPT Search / Google AI Mode /
  Perplexity, 89,000 unique cited LinkedIn URLs.
  https://www.semrush.com/blog/linkedin-ai-visibility-study/

The checks are deliberately mechanical. Judgement calls (is the technical
detail real? does the hook open a gap?) stay in SKILL.md where they belong.

Exit codes: 0 = no FAILs, 1 = at least one FAIL, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field, asdict

# ── Surface budgets ──────────────────────────────────────────────────────────
# Two different consumers truncate at two different budgets. Counting
# characters satisfies neither, which is the whole point of this table.
SURFACES: dict[str, dict] = {
    "headline": {
        "max_chars": 220,
        "why": "LinkedIn headline hard limit; one of five author fields that "
               "travel with a post into another member's feed.",
    },
    "services": {
        "min_chars": 150,
        "max_chars": 500,
        "why": "LinkedIn services description limits.",
    },
    "post": {
        "min_words": 50,
        "max_words": 299,
        "why": "Semrush: cited feed posts cluster at 50-299 words.",
    },
    "article": {
        "min_words": 500,
        "max_words": 2000,
        "why": "Semrush: articles are 50-66%% of cited LinkedIn content; "
               "cited ones cluster at 500-2000 words.",
    },
    "prose": {
        "why": "Generic prose. Length checks skipped.",
    },
}

# Mathematical Alphanumeric Symbols. ChatGPT's retriever does not apply NFKD,
# so these never decompose to ASCII and the words are unqueryable.
MATH_ALPHA = re.compile(r"[\U0001D400-\U0001D7FF]")

# Characters that survive NFKD into plain letters are fine; these are the ones
# that look like formatting and are not.
AI_TELL_CHARS = {"—": "em dash"}

LINK_IN_COMMENTS = re.compile(
    r"link\s+(?:is\s+)?in\s+(?:the\s+)?(?:comments?|first\s+comment)"
    r"|comments?\s+for\s+the\s+link"
    r"|enlace\s+en\s+(?:los\s+)?comentarios",
    re.I,
)

# A number attached to a unit or a bare figure with >=2 significant chars.
NUMERIC = re.compile(r"(?<![\w.])\d[\d,._]*(?:\s?%|\s?[a-zA-Z]{1,4}\b)?")

# Spelled-out numerals count as specificity too. Counting only digits marks
# "nine iterations, seven of them failed" as unspecific, which is wrong — the
# claim is exactly as concrete either way. (Caught dogfooding this skill on a
# real draft: 3 digit-tokens reported against ~10 actual quantities.)
_WORD_NUMS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    "fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|"
    "fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|"
    "dozen|half|twice|double|triple"
)
WORD_NUMERIC = re.compile(rf"\b(?:{_WORD_NUMS})\b", re.I)

# Surfaces too short for density to mean anything. A headline carrying no digits
# is not a defect; requiring one produced a false FAIL on a perfectly good
# 192-char headline.
NO_DENSITY_SURFACES = {"headline"}

FAQ_HEADING = re.compile(r"^\s*(?:#{1,6}\s*)?(?:q:|question:|faq\b)", re.I | re.M)


@dataclass
class Check:
    name: str
    status: str  # PASS | WARN | FAIL | SKIP
    detail: str
    effect: str = ""


@dataclass
class Report:
    surface: str
    checks: list[Check] = field(default_factory=list)

    def add(self, *a, **kw) -> None:
        self.checks.append(Check(*a, **kw))

    @property
    def failed(self) -> bool:
        return any(c.status == "FAIL" for c in self.checks)


def _words(text: str) -> int:
    return len(text.split())


def check_unicode(text: str, rep: Report) -> None:
    """The single largest negative effect in the Scrunch data."""
    hits = MATH_ALPHA.findall(text)
    if hits:
        sample = "".join(sorted(set(hits))[:12])
        rep.add(
            "math-alpha-unicode",
            "FAIL",
            f"{len(hits)} mathematical-alphanumeric char(s) found: {sample}. "
            "ChatGPT's retriever does not NFKD-normalise these, so the words "
            "containing them are unqueryable. Retype in plain text.",
            effect="-58% citation, +12% reactions (Scrunch)",
        )
    else:
        rep.add(
            "math-alpha-unicode",
            "PASS",
            "No fake-bold/italic codepoints.",
            effect="-58% citation, +12% reactions if present (Scrunch)",
        )


def check_length(text: str, surface: str, rep: Report) -> None:
    spec = SURFACES[surface]
    if not any(k in spec for k in ("max_chars", "min_chars", "max_words", "min_words")):
        rep.add("length", "SKIP", spec.get("why", "No budget for this surface."))
        return

    n_c, n_w = len(text), _words(text)
    problems, notes = [], []

    if "max_chars" in spec:
        notes.append(f"{n_c}/{spec['max_chars']} chars")
        if n_c > spec["max_chars"]:
            problems.append(f"over by {n_c - spec['max_chars']} chars")
    if "min_chars" in spec and n_c < spec["min_chars"]:
        problems.append(f"under minimum by {spec['min_chars'] - n_c} chars")
    if "max_words" in spec:
        notes.append(f"{n_w} words (target {spec.get('min_words', 0)}-{spec['max_words']})")
        if n_w > spec["max_words"]:
            problems.append(f"over by {n_w - spec['max_words']} words")
    if "min_words" in spec and n_w < spec["min_words"]:
        problems.append(f"under target by {spec['min_words'] - n_w} words")

    joined = "; ".join(notes) or f"{n_c} chars, {n_w} words"
    if problems:
        rep.add("length", "FAIL", f"{joined}. {'; '.join(problems)}. {spec['why']}")
    else:
        rep.add("length", "PASS", f"{joined}. Within budget.")


def check_named_entities(text: str, entities: list[str], rep: Report) -> None:
    """Named entities are read from the post text, not the mention graph."""
    if not entities:
        found = sorted({
            m.group(0)
            for m in re.finditer(r"\b(?:[A-Z][a-z]+[A-Z]\w*|[A-Z]{2,}|[A-Z][a-z]{2,})\b", text)
        })
        found = [f for f in found if f.lower() not in _STOP_CAPS]
        n = len(found)
        detail = f"{n} candidate proper noun(s): {', '.join(found[:10])}"
    else:
        found = [e for e in entities if re.search(rf"\b{re.escape(e)}\b", text, re.I)]
        n = len(found)
        detail = f"{n}/{len(entities)} expected entities present: {', '.join(found) or 'none'}"

    status = "PASS" if n >= 3 else "WARN"
    rep.add(
        "named-entities",
        status,
        detail + ("" if n >= 3 else ". Name specific companies, products, tools in plain text."),
        effect="+33% citation, +5% reactions (Scrunch)",
    )


_STOP_CAPS = {
    "the", "this", "that", "it", "i", "we", "you", "and", "but", "so", "then",
    "not", "now", "what", "when", "which", "who", "why", "how", "a", "an",
}


def check_specificity(text: str, surface: str, rep: Report) -> None:
    """Technical detail is the dominant positive effect and is free."""
    if surface in NO_DENSITY_SURFACES:
        rep.add(
            "technical-specificity",
            "SKIP",
            f"Density is not meaningful on a {surface}; judge it by whether the "
            "claim names a real thing, not by counting figures.",
            effect="+77% citation, ~0 reactions (Scrunch)",
        )
        return

    digits = NUMERIC.findall(text)
    words_ = WORD_NUMERIC.findall(text)
    total = len(digits) + len(words_)
    per_100w = (total / max(_words(text), 1)) * 100
    breakdown = f"{len(digits)} numeric + {len(words_)} spelled-out"

    if total == 0:
        rep.add(
            "technical-specificity",
            "FAIL",
            "No numbers, measurements, or versions found. Technical detail is "
            "the largest positive citation effect and costs nothing in "
            "engagement. Add real figures from real work.",
            effect="+77% citation, ~0 reactions (Scrunch)",
        )
    else:
        status = "PASS" if per_100w >= 1.0 else "WARN"
        rep.add(
            "technical-specificity",
            status,
            f"{total} quantity token(s) ({breakdown}), {per_100w:.1f} per 100 words."
            + ("" if status == "PASS" else " Sparse; consider more concrete figures."),
            effect="+77% citation, ~0 reactions (Scrunch)",
        )


def check_link_in_comments(text: str, rep: Report) -> None:
    if LINK_IN_COMMENTS.search(text):
        rep.add(
            "link-in-comments",
            "WARN",
            "Link-in-comments detected. This is a deliberate trade, not a bug: "
            "the post loses citation odds, the linked URL roughly doubles its "
            "own. Correct only when the destination is the asset you own.",
            effect="-31% post citation, +11% reactions; linked URL 24%->59% (Scrunch)",
        )
    else:
        rep.add("link-in-comments", "PASS", "Post is self-contained.")


def check_faq_shape(text: str, rep: Report) -> None:
    if FAQ_HEADING.search(text):
        rep.add(
            "faq-structure",
            "WARN",
            "FAQ-shaped headings found. On LinkedIn this is the one tested "
            "structure that loses on both surfaces.",
            effect="0 citation, -9% reactions (Scrunch)",
        )
    else:
        rep.add("faq-structure", "PASS", "Not FAQ-structured.")


def check_ai_tells(text: str, rep: Report) -> None:
    """Not a citation effect. A credibility effect, and it is cheap to fix."""
    counts = {ch: text.count(ch) for ch in AI_TELL_CHARS if text.count(ch)}
    total = sum(counts.values())
    per_1kw = (total / max(_words(text), 1)) * 1000
    if total == 0:
        rep.add("ai-tells", "PASS", "No em dashes.", effect="credibility, not citation")
    else:
        status = "WARN" if per_1kw <= 2 else "FAIL"
        names = ", ".join(f"{AI_TELL_CHARS[c]} x{n}" for c, n in counts.items())
        rep.add(
            "ai-tells",
            status,
            f"{names} ({per_1kw:.1f} per 1000 words). Widely read as "
            "machine-written in 2026; first-person credibility is the whole "
            "point of this content class. Replace with commas, colons, or periods.",
            effect="credibility, not citation",
        )


def check_non_ascii(text: str, rep: Report) -> None:
    """Informational. Accents are fine; the scan exists to surface surprises."""
    inv: dict[str, int] = {}
    for ch in text:
        if ord(ch) > 127 and not MATH_ALPHA.match(ch):
            inv[ch] = inv.get(ch, 0) + 1
    if not inv:
        rep.add("non-ascii-inventory", "PASS", "Pure ASCII.")
        return
    top = ", ".join(
        f"{ch!r} U+{ord(ch):04X} x{n} ({unicodedata.name(ch, '?')[:28]})"
        for ch, n in sorted(inv.items(), key=lambda kv: -kv[1])[:6]
    )
    rep.add("non-ascii-inventory", "PASS", f"{len(inv)} distinct non-ASCII: {top}")


def run(text: str, surface: str, entities: list[str]) -> Report:
    rep = Report(surface=surface)
    check_unicode(text, rep)
    check_length(text, surface, rep)
    check_specificity(text, surface, rep)
    check_named_entities(text, entities, rep)
    check_link_in_comments(text, rep)
    check_faq_shape(text, rep)
    check_ai_tells(text, rep)
    check_non_ascii(text, rep)
    return rep


_ICON = {"PASS": "ok  ", "WARN": "warn", "FAIL": "FAIL", "SKIP": "skip"}


def render(rep: Report) -> str:
    lines = [f"citable — surface: {rep.surface}", ""]
    for c in rep.checks:
        lines.append(f"  [{_ICON[c.status]}] {c.name}")
        lines.append(f"         {c.detail}")
        if c.effect:
            lines.append(f"         effect: {c.effect}")
    n_fail = sum(1 for c in rep.checks if c.status == "FAIL")
    n_warn = sum(1 for c in rep.checks if c.status == "WARN")
    lines += ["", f"  {n_fail} FAIL, {n_warn} WARN, {len(rep.checks)} checks"]
    if n_fail == 0:
        lines.append("  Mechanics clear. The judgement calls are in SKILL.md and are not automatable.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="citable_check",
        description="Lint authored text against measured AI-citation effects.",
    )
    p.add_argument("path", nargs="?", help="File to check. Omit to read stdin.")
    p.add_argument(
        "--surface",
        default="prose",
        choices=sorted(SURFACES),
        help="Which budget applies (default: prose).",
    )
    p.add_argument(
        "--entities",
        default="",
        help="Comma-separated entities that SHOULD appear (e.g. 'Rust,Databricks').",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON.")
    args = p.parse_args(argv)

    if args.path:
        try:
            text = open(args.path, encoding="utf-8").read()
        except OSError as e:
            print(f"citable_check: cannot read {args.path}: {e}", file=sys.stderr)
            return 2
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("citable_check: empty input", file=sys.stderr)
        return 2

    entities = [e.strip() for e in args.entities.split(",") if e.strip()]
    rep = run(text, args.surface, entities)

    if args.json:
        print(json.dumps(asdict(rep), indent=2, ensure_ascii=False))
    else:
        print(render(rep))
    return 1 if rep.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
