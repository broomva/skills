#!/usr/bin/env python3
"""disambiguate — find the places a requirement can be read more than one way.

Deterministic core of the `disambiguate` skill. Stdlib only, no network, no
model calls, no third-party corpora.

The detectors implement the mechanically-checkable subset of the ambiguity
catalog distilled from ASD-STE100 Simplified Technical English (Issue 9).
They are organized by the question the reader cannot answer:

    A  Which thing?          reference ambiguity
    B  Who must, and must they?   agency and modality
    C  How do I know it is done?  verifiability
    D  Can I hold this?           atomicity and load
    E  Can I parse it at all?     construction traps

Design rules for this file:

1.  Conservative over complete. A false positive costs the user more than a
    miss, because a noisy linter gets ignored. Detectors that need real
    part-of-speech tagging are either narrowed to a high-precision surface
    pattern or downgraded to `info`.
2.  Never report a defect without a fix. Every finding carries a rewrite
    pattern. This mirrors the source standard's own design: it never lists a
    disallowed word without an approved substitute plus a worked example.
3.  Honest limits. Where the algorithm cannot decide (proper nouns, titles),
    it says so in an advisory rather than guessing. See `--glossary`.

No text of the source standard is reproduced here beyond short example
sentences used as test fixtures. The standard is free to download from
asd-ste100.org and remains the authority.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

__version__ = "1.0.0"

# Sentence-length ceilings. Procedural text is executed under load, one step at
# a time; descriptive text is read as a unit. Hence the different budgets.
CEILING = {"procedural": 20, "descriptive": 25}

SEVERITIES = ("block", "warn", "info")


# --------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------

# Units that bind to a preceding number and count with it as one word.
UNITS = {
    # Deliberately excludes single letters and words that are also ordinary
    # English ("a", "in", "s", "min", "us"). Binding "16 a" in "16 a minimum of
    # three times" would silently undercount the sentence.
    "mm", "cm", "km", "ft", "yd", "mil", "micron", "microns",
    "millimeter", "millimeters", "centimeter", "centimeters", "meter",
    "meters", "metre", "metres", "kilometer", "kilometers", "inch", "inches",
    "foot", "feet", "yard", "yards",
    "mg", "kg", "lb", "lbs", "oz", "ton", "tons", "gram", "grams",
    "kilogram", "kilograms", "pound", "pounds", "ounce", "ounces",
    "ml", "cc", "gal", "qt", "liter", "liters", "litre", "litres", "gallon",
    "gallons",
    "sec", "secs", "second", "seconds", "minute", "minutes",
    "hr", "hrs", "hour", "hours", "day", "days", "week", "weeks",
    "month", "months", "year", "years", "ms", "ns",
    "a.m", "p.m", "am.", "pm.",
    "hz", "khz", "mhz", "ghz", "hertz",
    "mv", "kv", "volt", "volts", "ma", "amp", "amps", "ampere", "amperes",
    "kw", "mw", "watt", "watts", "ohm", "ohms",
    "psi", "bar", "kpa", "mpa", "atm", "torr", "pascal", "pascals",
    "nm", "newton", "newtons", "lbf", "kgf",
    "celsius", "fahrenheit", "kelvin", "degree", "degrees",
    "kb", "mb", "gb", "tb", "bit", "bits", "byte", "bytes",
    "rpm", "kt", "kts", "knot", "knots", "mph", "kph",
    "%", "percent", "pct",
}

# Spelled-out numbers bind to a following unit exactly as digits do.
NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
    "thousand", "million", "billion",
}


# Irregular past participles, for passive-voice detection without a tagger.
IRREGULAR_PARTICIPLES = {
    "done", "made", "set", "given", "taken", "shown", "written", "sent",
    "built", "held", "kept", "put", "run", "read", "found", "seen", "known",
    "chosen", "drawn", "driven", "eaten", "fallen", "forgotten", "got",
    "gotten", "hidden", "kept", "left", "lost", "met", "paid", "said", "sold",
    "spent", "told", "thought", "understood", "worn", "won", "broken",
    "brought", "bought", "caught", "cut", "dealt", "felt", "fed", "flown",
    "frozen", "grown", "hung", "heard", "hit", "let", "lit", "meant", "risen",
    "shut", "spoken", "split", "spread", "stood", "struck", "swept", "torn",
    "thrown", "woken", "worn", "beaten", "bent", "bound", "burnt", "cast",
    "chosen", "clung", "come", "cost", "crept", "dug", "drunk", "fought",
    "fit", "hurt", "laid", "led", "lent", "made", "overridden", "proven",
    "quit", "rebuilt", "rewritten", "sought", "shot", "shrunk", "sung",
    "sunk", "slept", "slid", "sped", "spun", "stuck", "stung", "swum",
    "swung", "taught", "torn", "upheld", "upset", "withdrawn", "withheld",
}

BE_FORMS = {"is", "are", "was", "were", "be", "been", "being", "am", "'s", "'re"}

# Words that carry no measurable acceptance test. This list is original to this
# skill, assembled from requirements-engineering practice; it is not the source
# standard's dictionary.
VAGUE_PREDICATES = {
    "appropriate", "appropriately", "adequate", "adequately", "gracefully",
    "graceful", "robust", "robustly", "scalable", "efficient", "efficiently",
    "user-friendly", "seamless", "seamlessly", "intuitive", "intuitively",
    "reasonable", "reasonably", "sufficient", "sufficiently", "properly",
    "reliable", "reliably", "performant", "simple", "easy", "easily",
    "fast", "quick", "quickly", "slow", "minimal", "significant",
    "significantly", "various", "several", "many", "some", "generally",
    "typically", "usually", "normally", "flexible", "modern", "clean",
    "optimal", "optimally", "acceptable", "smooth", "smoothly", "nice",
    "better", "best-practice", "state-of-the-art", "industry-standard",
    "meaningful", "relevant", "suitable", "proper", "correct-ish",
}

VAGUE_PHRASES = [
    "as needed", "as required", "as appropriate", "if necessary",
    "where possible", "when possible", "if possible", "as applicable",
    "best practices", "best practice", "industry standard",
    "state of the art", "and so on", "among others", "or similar",
    "to be determined", "tbd", "etc",
]

# Comparatives that imply a delta but name no baseline.
COMPARATIVE_PAT = re.compile(
    r"\b(faster|slower|better|worse|cheaper|larger|smaller|higher|lower|"
    r"stronger|weaker|safer|simpler|easier|harder|more\s+\w+|less\s+\w+|"
    r"improved?|increases?d?|reduces?d?|decreases?d?|optimiz\w+|enhanc\w+)\b",
    re.I,
)

WEAK_MODALS = {"should", "may", "might", "could", "would", "ought"}

LATIN_ABBREVS = [
    (r"\be\.g\.", "for example"),
    (r"\bi\.e\.", "that is"),
    (r"\betc\.", "and other items — name them, or end the list"),
    (r"\bviz\.", "namely"),
    (r"\bcf\.", "compare"),
    (r"\bN\.B\.", "note"),
    (r"\bvs\.", "compared to"),
]

CONTRACTION_PAT = re.compile(
    r"\b\w+(?:n't|'re|'ve|'ll|'d)\b|\bit's\b|\bthat's\b|\bthere's\b|"
    r"\bwe're\b|\byou're\b|\bdon't\b|\bcan't\b|\bwon't\b",
    re.I,
)

# Phrasal verbs whose meaning is not the sum of their parts. Deliberately short
# and conservative: many particle verbs are perfectly clear.
OPAQUE_PHRASAL = {
    "carry out": "do",
    "bring about": "cause",
    "put up with": "accept",
    "look into": "examine",
    "sort out": "correct",
    "figure out": "find",
    "deal with": "correct, or process",
    "come across": "find",
    "take care of": "do, or maintain",
    "run into": "find, or hit",
    "get rid of": "remove, or discard",
    "go over": "examine",
    "hold off": "wait",
    "knock out": "disable",
}

# Verbs after which a dropped "that" hides the clause boundary.
THAT_TAKING = r"(make sure|makes sure|ensure|ensures|verify|verifies|check|checks|" \
              r"show|shows|showed|recommend|recommends|mean|means|note|assume|assumes|" \
              r"confirm|confirms|indicate|indicates|require|requires)"

DETERMINERS = {
    "the", "a", "an", "this", "these", "that", "those", "its", "their",
    "your", "our", "his", "her", "each", "every", "any", "some", "no",
}

CONDITION_STARTERS = {
    "if", "when", "while", "before", "after", "once", "unless", "until",
    "during", "whenever", "given", "provided", "in", "for", "to", "on",
}

# Function words that break a noun stack.
FUNCTION_WORDS = {
    "a", "an", "the", "this", "that", "these", "those", "of", "in", "on",
    "at", "to", "for", "with", "by", "from", "into", "onto", "over", "under",
    "and", "or", "but", "nor", "so", "yet", "as", "than", "then", "if",
    "when", "while", "before", "after", "is", "are", "was", "were", "be",
    "been", "being", "has", "have", "had", "do", "does", "did", "can",
    "cannot", "must", "will", "shall", "should", "may", "might", "could",
    "would", "not", "no", "its", "it", "you", "your", "we", "our", "they",
    "their", "each", "all", "any", "both", "every", "such", "same", "other",
    "more", "most", "less", "least", "very", "only", "also", "there", "here",
    "per", "via", "where", "because", "about", "between", "through", "during",
    "without", "within", "across", "against", "upon", "since", "until",
    "though", "although", "whether", "what", "which", "who", "whom", "how",
    "why", "well", "just", "even", "still", "already", "often", "always",
    "never", "sometimes", "rather", "quite", "too", "own", "way", "one",
}

IMPERATIVE_HINT = {
    "add", "adjust", "align", "apply", "assemble", "attach", "build", "call",
    "cancel", "change", "check", "clean", "clear", "close", "compare",
    "complete", "configure", "connect", "continue", "create", "cut",
    "deactivate", "define", "delete", "deploy", "disable", "disconnect",
    "discard", "do", "document", "drain", "emit", "enable", "ensure", "enter",
    "examine", "execute", "expose", "extend", "fetch", "fill", "find", "fix",
    "flush", "generate", "give", "go", "handle", "hold", "identify",
    "ignore", "implement", "increase", "index", "initialize", "insert",
    "inspect", "install", "invoke", "isolate", "keep", "let", "lift", "list",
    "load", "lock", "log", "look", "lower", "make", "measure", "merge",
    "migrate", "monitor", "move", "open", "parse", "persist", "pass", "poll",
    "prepare", "prevent", "print", "process", "publish", "pull", "push",
    "put", "queue", "read", "rebuild", "receive", "record", "reduce",
    "refactor", "refer", "reject", "release", "reload", "remove", "rename",
    "render", "repair", "replace", "reply", "report", "request", "reset",
    "resolve", "restart", "restore", "retry", "return", "revoke", "rotate",
    "run", "save", "scan", "schedule", "seal", "select", "send", "serve",
    "set", "show", "shut", "sign", "split", "start", "stop", "store",
    "stream", "submit", "subtract", "supply", "sync", "tag", "test",
    "throw", "tighten", "torque", "touch", "track", "transmit", "trigger",
    "truncate", "tune", "turn", "unlock", "update", "upgrade", "upload",
    "use", "validate", "verify", "wait", "write",
}

# Inflected forms of the action verbs. A noun stack ends at a verb; without
# these, "the new caching layer makes …" reads as a five-word stack whose head
# noun is "makes".
VERB_FORMS: set[str] = set()
for _v in IMPERATIVE_HINT:
    VERB_FORMS.update({_v, _v + "s", _v + "es", _v + "ed", _v + "ing", _v + "d"})
VERB_FORMS.update({
    "makes", "made", "making", "does", "did", "doing", "has", "have", "had",
    "gets", "got", "goes", "went", "comes", "came", "takes", "took", "gives",
    "gave", "needs", "needed", "wants", "uses", "used", "using", "allows",
    "causes", "means", "requires", "returns", "provides", "supports",
    "contains", "includes", "occurs", "happens", "exists", "remains",
    "leave", "leaves", "left", "carry", "carries", "carried", "sit", "sits",
    "match", "matches", "end", "ends", "name", "names", "named", "point",
    "points", "mean", "meant", "admit", "admits", "permit", "permits",
    "produce", "produces", "cost", "costs", "beat", "beats", "fire", "fires",
    "stay", "stays", "span", "spans", "break", "breaks", "apply", "applies",
    "follow", "follows", "belong", "belongs", "work", "works", "help",
    "helps", "keep", "keeps", "become", "becomes", "seem", "seems", "appear",
    "appears", "tell", "tells", "ask", "asks", "say", "says", "see", "sees",
    "know", "knows", "think", "thinks", "want", "wants", "hide", "hides",
    "reads", "writes", "holds", "describe", "describes", "resolve", "resolves",
})

STATE_ASSERTION_PAT = re.compile(
    r"\b(?:no\s+\w+\s+(?:is|are)\s+(?:permitted|allowed|acceptable)"
    r"|(?:is|are)\s+(?:required|necessary|imperative|essential|mandatory|expected)"
    r"|must\s+be\s+(?:ensured|guaranteed|maintained|observed|respected))\b",
    re.I,
)

SAFETY_LABEL_PAT = re.compile(r"^\s*(WARNING|CAUTION|DANGER|NOTICE|ATTENTION|NOTE)\s*:\s*", re.I)

CONSEQUENCE_PAT = re.compile(
    r"\b(can cause|will cause|causes|can result|will result|results in|"
    r"can damage|can injure|can occur|leads to|can lead to|otherwise)\b", re.I
)


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass
class Finding:
    code: str
    family: str
    severity: str
    line: int
    excerpt: str
    why: str
    fix: str
    ste: str = ""

    def render(self) -> str:
        return (
            f"  [{self.severity.upper():5}] {self.code:22} line {self.line}\n"
            f"          > {self.excerpt}\n"
            f"          why: {self.why}\n"
            f"          fix: {self.fix}"
            + (f"\n          ste: {self.ste}" if self.ste else "")
        )


FAMILY_TITLE = {
    "A": "Which thing?",
    "B": "Who must, and must they?",
    "C": "How do I know it is done?",
    "D": "Can I hold this?",
    "E": "Can I parse it at all?",
}


# --------------------------------------------------------------------------
# Word counting (the precision piece)
# --------------------------------------------------------------------------

_STEP_MARKER = re.compile(r"^\s*(?:\(?\d+[.)]|\(?[A-Za-z][.)])\s+")
_PAREN = re.compile(r"\([^()]*\)")
_DQUOTE = re.compile(r"[“”\"][^“”\"]*[“”\"]")
_NUMBER = re.compile(r"^[+-]?\$?\d[\d,]*(?:\.\d+)?[%]?$")


def _is_number(tok: str) -> bool:
    t = tok.strip(".,;:")
    return bool(_NUMBER.match(t)) or t.lower() in NUMBER_WORDS


def _is_unit(tok: str) -> bool:
    t = tok.strip(".,;:").lower()
    return t in UNITS or t.startswith("°")


SENTINELS = {"\x01", "\x02", "\x03", "\x04", "\x05"}


def _is_sentinel(tok: str) -> bool:
    return tok in SENTINELS


def count_ste_words(sentence: str, glossary: Sequence[str] = ()) -> tuple[int, list[str]]:
    """Count words the way the standard counts them, and report what is uncertain.

    One word each: a parenthetical group, a quoted span, a run set off by
    uppercase, a number, a number with its unit, an abbreviation, an
    alphanumeric identifier, a hyphenated compound, and any glossary term.

    Returns (count, advisories). Advisories name the places where a human or a
    glossary entry is needed — multi-word proper nouns and document titles
    cannot be detected without knowing the domain, so they are surfaced rather
    than guessed at.
    """
    advisories: list[str] = []
    text = sentence.strip()

    # A safety label and a leading step number are not part of the sentence.
    text = SAFETY_LABEL_PAT.sub("", text)
    text = _STEP_MARKER.sub("", text)

    # Glossary terms collapse first, longest first so that a longer term wins.
    for term in sorted(glossary, key=len, reverse=True):
        if term and term.lower() in text.lower():
            text = re.sub(re.escape(term), " \x04 ", text, flags=re.I)

    # A predominantly-uppercase sentence is a formatting convention (a safety
    # instruction, a heading). Case then carries no quoting signal, so fold it.
    letters = [c for c in text if c.isalpha()]
    upper_ratio = sum(c.isupper() for c in letters) / len(letters) if letters else 0.0
    caps_is_quoting = upper_ratio < 0.6

    # An identifier such as "No. 1" or "#4" names one item and counts once.
    text = re.sub(r"\b(?:No|Nos|Ref|Fig|Item|Step)\.?\s*#?\s*\d+\b", " \x05 ", text, flags=re.I)
    text = re.sub(r"#\s*\d+\b", " \x05 ", text)
    text = _PAREN.sub(" \x01 ", text)
    text = _DQUOTE.sub(" \x02 ", text)

    if caps_is_quoting:
        # A contiguous run of uppercase tokens names a control, a placard or a
        # label; it is quoted by typography and counts once.
        text = re.sub(
            r"\b(?:[A-Z][A-Z0-9-]{1,}(?:\s+[A-Z][A-Z0-9-]{1,})*)\b",
            lambda m: " \x03 " if len(m.group(0)) > 1 else m.group(0),
            text,
        )

    raw = [t for t in re.split(r"\s+", text) if t.strip(" \t\r\n")]

    count = 0
    i = 0
    cap_run: list[str] = []
    while i < len(raw):
        tok = raw[i].strip(",.;:!?")
        if not tok:
            i += 1
            continue

        # Number, optionally followed by its unit (and a second unit word such
        # as "degrees Celsius").
        if _is_number(tok):
            j = i + 1
            consumed = 0
            while j < len(raw) and consumed < 2 and _is_unit(raw[j]):
                j += 1
                consumed += 1
            count += 1
            i = j
            continue

        count += 1

        # Track capitalized multi-word runs for the proper-noun advisory.
        if tok[:1].isupper() and i > 0 and not _is_sentinel(tok):
            cap_run.append(tok)
        else:
            if len(cap_run) > 1:
                advisories.append(
                    f'"{" ".join(cap_run)}" — if this names a person, an '
                    f"organization, a place, or a document title, it counts as "
                    f"one word: subtract {len(cap_run) - 1}. Add it to "
                    f"--glossary to make the count exact."
                )
            cap_run = []
        i += 1

    if len(cap_run) > 1:
        advisories.append(
            f'"{" ".join(cap_run)}" — if this names a person, an organization, '
            f"a place, or a document title, it counts as one word: subtract "
            f"{len(cap_run) - 1}. Add it to --glossary to make the count exact."
        )

    return count, advisories


# --------------------------------------------------------------------------
# Segmentation
# --------------------------------------------------------------------------

_ABBREV_GUARD = re.compile(r"\b(?:No|Fig|Ref|Rev|Sec|Vol|Ch|pp|approx|min|max|e\.g|i\.e|a\.m|p\.m|vs|St|Mr|Ms|Dr)\.$", re.I)


def split_sentences(block: str) -> list[str]:
    """Split on sentence enders. A colon ends a sentence when it introduces a
    vertical list, which is why it is treated as a boundary here."""
    parts: list[str] = []
    buf = ""
    for chunk in re.split(r"(?<=[.!?:])\s+", block.strip()):
        buf = (buf + " " + chunk).strip() if buf else chunk
        if _ABBREV_GUARD.search(buf.rstrip()):
            continue
        parts.append(buf)
        buf = ""
    if buf:
        parts.append(buf)
    return [p for p in parts if p.strip()]


def strip_noncontent(text: str) -> list[str]:
    """Blank the lines that are not prose, keeping line numbers intact.

    Markdown is the normal input — a ticket, a REQUIREMENTS.md, a spec. Without
    this, YAML frontmatter and fenced code get parsed as sentences, which
    produced 161 findings on this skill's own SKILL.md, nearly all of them
    noise. A checker that is noisy on its own documentation will be turned off.
    """
    lines = text.splitlines()
    out: list[str] = []
    in_fence = False
    fence_mark = ""
    in_frontmatter = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # YAML frontmatter: a --- fence on the very first line.
        if i == 0 and stripped == "---":
            in_frontmatter = True
            out.append("")
            continue
        if in_frontmatter:
            if stripped in {"---", "..."}:
                in_frontmatter = False
            out.append("")
            continue

        # Fenced code, ``` or ~~~, closed only by the same marker.
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_mark = stripped[:3]
            out.append("")
            continue
        if in_fence:
            if stripped.startswith(fence_mark):
                in_fence = False
            out.append("")
            continue

        # Headings, tables, rules, and indented code blocks.
        if (not stripped
                or stripped.startswith(("#", "|", ">"))
                or re.match(r"^(-{3,}|={3,}|\*{3,})$", stripped)
                or line.startswith("    ") and not re.match(r"^\s*(?:[-*+]|\(?[a-zA-Z0-9][.)])\s", line)):
            out.append("")
            continue

        # A list marker is structure, not a word.
        body = re.sub(r"^\s*(?:[-*+])\s+", "", line)
        # Inline code and links carry no prose to check.
        body = re.sub(r"`[^`]*`", " CODE ", body)
        body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)
        out.append(body)

    return out


def iter_units(text: str) -> Iterable[tuple[int, str]]:
    """Yield (line_number, sentence) over the prose in the document."""
    for lineno, line in enumerate(strip_noncontent(text), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        for sent in split_sentences(stripped):
            yield lineno, sent


def paragraphs(text: str) -> list[tuple[int, list[str]]]:
    out: list[tuple[int, list[str]]] = []
    lineno = 1
    buf: list[str] = []
    start = 1
    for i, line in enumerate(strip_noncontent(text), start=1):
        if line.strip():
            if not buf:
                start = i
            buf.append(line.strip())
        else:
            if buf:
                out.append((start, split_sentences(" ".join(buf))))
                buf = []
    if buf:
        out.append((start, split_sentences(" ".join(buf))))
    return out


# --------------------------------------------------------------------------
# Mode detection
# --------------------------------------------------------------------------


def is_imperative(sent: str) -> bool:
    """True when this sentence commands the reader.

    Document mode sets the length ceiling, but whether a given sentence is an
    instruction is a property of that sentence. A mostly-descriptive spec still
    contains commands, and those commands still have to obey the command rules.
    """
    body = _STEP_MARKER.sub("", SAFETY_LABEL_PAT.sub("", sent).strip())
    first = re.split(r"[\s,]+", body.lower())[:1]
    if not first or not first[0]:
        return False
    w = first[0].strip(".,:;")
    if w in IMPERATIVE_HINT:
        return True
    if w in CONDITION_STARTERS and "," in body:
        nxt = re.split(r"\s+", body.split(",", 1)[1].strip().lower())[:1]
        return bool(nxt and nxt[0].strip(".,:;") in IMPERATIVE_HINT)
    return False


def detect_mode(text: str) -> str:
    """Procedural text tells the reader to act; descriptive text tells them what
    is true. The ceilings and the verb rules differ, so this must be settled
    before anything else is checked."""
    imperative = 0
    total = 0
    for _, sent in iter_units(text):
        if not re.search(r"[A-Za-z]", sent):
            continue
        total += 1
        if is_imperative(sent):
            imperative += 1
    if total == 0:
        return "descriptive"
    return "procedural" if imperative / total >= 0.3 else "descriptive"


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------


def _add(findings: list[Finding], **kw) -> None:
    findings.append(Finding(**kw))


def check_sentence(lineno: int, sent: str, mode: str, glossary: Sequence[str]) -> list[Finding]:
    f: list[Finding] = []
    low = sent.lower()
    body = SAFETY_LABEL_PAT.sub("", sent).strip()
    body_nostep = _STEP_MARKER.sub("", body)
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", body_nostep)
    lwords = [w.lower() for w in words]
    short = (sent[:96] + "…") if len(sent) > 96 else sent
    commanding = is_imperative(sent)

    # ---------------- A — Which thing? ----------------

    # A1 demonstrative with no head noun.
    for m in re.finditer(r"\b(This|These|That|Those)\s+(\w+)", body_nostep):
        nxt = m.group(2).lower()
        if nxt in BE_FORMS or nxt in {"can", "will", "must", "should", "may",
                                      "causes", "means", "allows", "makes",
                                      "requires", "prevents", "happens",
                                      "occurs", "results", "gives", "lets"}:
            _add(f, code="A1-bare-demonstrative", family="A", severity="warn",
                 line=lineno, excerpt=short,
                 why=f'"{m.group(1)}" carries no head noun, so the reader must guess '
                     f"which item it points at. When two candidates are in scope, the "
                     f"two readings often have opposite consequences.",
                 fix=f'Name the item: "{m.group(1)} <noun> {m.group(2)}…".',
                 ste="GR-4")

    # A1b bare it/they with more than one candidate antecedent.
    if re.search(r"\b(it|they|them)\b", low):
        candidates = re.findall(r"\b(?:the|a|an)\s+([a-z][a-z-]+(?:\s+[a-z][a-z-]+){0,2})", low)
        uniq = list(dict.fromkeys(candidates))
        if len(uniq) >= 2:
            _add(f, code="A1-pronoun-antecedent", family="A", severity="info",
                 line=lineno, excerpt=short,
                 why=f"A pronoun refers back, but {len(uniq)} noun phrases are in scope "
                     f"({', '.join(uniq[:3])}…). The reader picks one; you do not control which.",
                 fix="Replace the pronoun with the noun it means, even at the cost of repetition.",
                 ste="GR-3")

    # A2 noun stack of four or more.
    #
    # Anchored on a determiner: a stack is a noun phrase, so it follows "the",
    # "a", "this", and so on. Without that anchor the run-of-content-words
    # heuristic matches ordinary clauses. Commas, function words, verb forms,
    # and inline-code placeholders all end a run.
    stack_tokens = re.findall(r"[A-Za-z][A-Za-z'-]*|,", body_nostep)
    run: list[str] = []
    armed = False

    def _flush(acc: list[str]) -> None:
        if len(acc) >= 4:
            stack = " ".join(acc)
            _add(f, code="A2-noun-stack", family="A", severity="warn",
                 line=lineno, excerpt=stack,
                 why=f'"{stack}" stacks {len(acc)} modifiers before its head noun '
                     f'"{acc[-1]}". A noun stack is a relation graph with the edges '
                     f"deleted: the reader has to reconstruct which word modifies which.",
                 fix="Put the edges back with prepositions. "
                     f'"{acc[-1]} of the {" ".join(acc[:-1])}" — then keep each '
                     "resulting group to three words or fewer.",
                 ste="2.1")

    for tok in stack_tokens + [","]:
        lw = tok.lower()
        if lw in DETERMINERS:
            _flush(run)
            run, armed = [], True
            continue
        if lw == "," or lw in FUNCTION_WORDS or lw in VERB_FORMS or tok == "CODE":
            _flush(run)
            run, armed = [], False
            continue
        if armed:
            run.append(tok)

    # A3 attachment-ambiguous "with".
    if re.search(r"\bwith\b", low) and commanding:
        _add(f, code="A3-with-attachment", family="A", severity="info",
             line=lineno, excerpt=short,
             why='"with" can mean the instrument, the accompaniment, or a property of the '
                 'object. "Install the panel with the green fasteners" has three readings.',
             fix="If it names the instrument, keep the primary action verb and make the "
                 "instrument explicit. If it names a condition, move it to a leading "
                 '"When …," clause.',
             ste="GR-2")

    # ---------------- B — Who must, and must they? ----------------

    # B1 passive voice.
    for i, w in enumerate(lwords[:-1]):
        if w in BE_FORMS:
            nxt = lwords[i + 1]
            nxt2 = lwords[i + 2] if i + 2 < len(lwords) else ""
            part = nxt
            if nxt in {"not", "also", "then", "always", "never"} and nxt2:
                part = nxt2
            if (part.endswith("ed") and len(part) > 3) or part in IRREGULAR_PARTICIPLES:
                agent = re.search(r"\bby\s+(the\s+)?\w+", low)
                _add(f, code="B1-passive" + ("" if agent else "-agentless"),
                     family="B", severity="info" if agent else "warn",
                     line=lineno, excerpt=short,
                     why=("Passive voice moves the actor out of the subject. "
                          + ("The actor is named, so this is a style cost only."
                             if agent else
                             "No actor is named at all, so the sentence does not say who "
                             "is responsible — the single most common defect in a requirement.")),
                     fix="Name the actor and make it the subject: "
                         '"<actor> <verb>s <object>". In an instruction, drop the actor '
                         "and use the command form instead.",
                     ste="3.6")
                break

    # B2 an instruction that is not in the command form.
    if mode == "procedural":
        if re.search(r"\b(can be|is to be|are to be|will be|should be|shall be|must be)\s+\w+(ed|en)\b", low):
            _add(f, code="B2-non-imperative-instruction", family="B", severity="warn",
                 line=lineno, excerpt=short,
                 why="A non-command construction leaves three things open at once: whether "
                     "the step is required, who does it, and whether it has already been "
                     "done. The reader cannot resolve any of them from the text.",
                 fix='Rewrite as a command: "Continue the test." not "The test can be continued."',
                 ste="5.3")

    # B3 obligation strength undefined.
    for w in WEAK_MODALS:
        if re.search(rf"\b{w}\b", low):
            _add(f, code="B3-weak-modal", family="B", severity="warn",
                 line=lineno, excerpt=short,
                 why=f'"{w}" does not say whether this is mandatory, permitted, or merely '
                     f"hoped for. Two readers will build two different systems and both "
                     f"will claim to have met the requirement.",
                 fix='Choose one: "must" (mandatory), "can" (capability or permission), '
                     '"will" (a future fact). If it is genuinely optional, say so and '
                     "give the default.",
                 ste="1.3, 5.3")
            break

    # B4 subject dropped from a leading clause.
    if re.match(r"^\s*(If|When|While|After|Before|Once)\s+\w+(ed|ing)\s*,", body_nostep, re.I):
        _add(f, code="B4-dropped-subject", family="B", severity="warn",
             line=lineno, excerpt=short,
             why='"If installed, remove the shims" does not say what is installed. '
                 "Dropping the subject shortens the sentence and lengthens the reading.",
             fix='Restore the subject: "If the shims are installed, remove them."',
             ste="4.2")

    # ---------------- C — How do I know it is done? ----------------

    if STATE_ASSERTION_PAT.search(low):
        _add(f, code="C1-abstract-assertion", family="C", severity="warn",
             line=lineno, excerpt=short,
             why="This states a desired world-state but names no action and no observation. "
                 '"No leaks are permitted" does not tell anyone what to do or what to look at.',
             fix='Convert it to a check the reader can perform: "Make sure that there are '
                 'no leaks." Then give the threshold that decides pass or fail.',
             ste="4.1")

    comp = COMPARATIVE_PAT.search(low)
    if comp and not re.search(r"\d", body_nostep):
        _add(f, code="C2-unquantified-delta", family="C", severity="warn",
             line=lineno, excerpt=short,
             why=f'"{comp.group(0)}" names a direction of change with no baseline and no target. '
                 f"There is no value of the system for which this is false, so it cannot fail, "
                 f"so it cannot be tested.",
             fix="Give the measure, the current value, and the target: "
                 '"reduce p95 latency from 800 ms to 200 ms or less".',
             ste="4.1")

    for w in lwords:
        if w in VAGUE_PREDICATES:
            _add(f, code="C3-vague-predicate", family="C", severity="warn",
                 line=lineno, excerpt=short,
                 why=f'"{w}" has no observable that settles it. Every reader supplies their '
                     f"own bar, and the disagreement surfaces at review time, not now.",
                 fix=f'Replace "{w}" with the observation you would actually make: a number, '
                     f"a threshold, a named state, or a command whose output you can read.",
                 ste="1.3, 4.1")
            break
    else:
        for phrase in VAGUE_PHRASES:
            if re.search(rf"\b{re.escape(phrase)}\b", low):
                _add(f, code="C3-vague-predicate", family="C", severity="warn",
                     line=lineno, excerpt=short,
                     why=f'"{phrase}" defers the decision to the reader without telling them '
                         f"how to decide.",
                     fix="Name the condition explicitly, or delete the hedge and commit.",
                     ste="1.3, 4.1")
                break

    # C4 a risk with no stated result.
    if SAFETY_LABEL_PAT.match(sent) and not CONSEQUENCE_PAT.search(low):
        _add(f, code="C4-missing-consequence", family="C", severity="warn",
             line=lineno, excerpt=short,
             why="A warning without its consequence gives the reader no reason to weigh it. "
                 "Stating the outcome is what makes a person careful.",
             fix='Add the result: "… . <Named cause> can cause <named outcome>."',
             ste="7.3")

    # ---------------- D — Can I hold this? ----------------

    n, advisories = count_ste_words(sent, glossary)
    ceiling = CEILING[mode]
    if n > ceiling:
        note = (" " + " ".join(advisories)) if advisories else ""
        _add(f, code="D1-over-length", family="D", severity="warn",
             line=lineno, excerpt=short,
             why=f"{n} words against a ceiling of {ceiling} for {mode} text. The ceiling is "
                 f"not a style preference: it is the point past which a reader executing "
                 f"under load starts to lose the front of the sentence.{note}",
             fix="Split at the natural clause boundary, or lift the list into a vertical "
                 "list. Do not shorten by deleting articles, subjects, or verbs.",
             ste=f"{'5.1' if mode == 'procedural' else '6.3'}, 8.4 thru 8.7")

    if ";" in sent:
        _add(f, code="D3-semicolon", family="D", severity="block",
             line=lineno, excerpt=short,
             why="A semicolon joins two independent clauses, which means the unit now holds "
                 "two statements. A reader can satisfy one and miss the other, and a test "
                 "cannot report which half failed.",
             fix="Use a period. If the two halves are genuinely one action, use a comma "
                 "and a connecting word.",
             ste="8.1")

    if commanding:
        verbs = [w for w in lwords if w in IMPERATIVE_HINT]
        if re.search(r"\b(and|or)\s+(?:then\s+)?(" + "|".join(sorted(IMPERATIVE_HINT)) + r")\b", low) and len(verbs) >= 2:
            _add(f, code="D2-compound-obligation", family="D", severity="warn",
                 line=lineno, excerpt=short,
                 why="Two actions in one unit. The reader can do the first and stop, and the "
                     "record will still say the step was done. It is also not separately "
                     "testable.",
                 fix="Split into two numbered steps — unless the two actions genuinely occur "
                     'at the same time ("Remove and discard the seal"), which is the only '
                     "case where one sentence is correct.",
                 ste="5.2")

    # ---------------- E — Can I parse it at all? ----------------

    for i, w in enumerate(lwords):
        if w.endswith("ing") and len(w) > 5 and w not in {"during", "string", "setting", "warning", "engineering"}:
            prev = lwords[i - 1] if i else ""
            if prev in BE_FORMS or i == 0:
                _add(f, code="E1-ing-form", family="E", severity="info",
                     line=lineno, excerpt=short,
                     why=f'"{w}" can be read as an ongoing action, as a name for the action, '
                         f'or as a modifier. "Changing filters" is either the act of changing '
                         f"or the filters that change.",
                     fix="Use a finite verb for the action, or a plain noun for the thing.",
                     ste="3.5")
                break

    m = re.search(THAT_TAKING + r"\s+(?!that\b)(the|a|an|you|it|this|these|there|all|each|no)\b", low)
    if m:
        _add(f, code="E2-dropped-that", family="E", severity="info",
             line=lineno, excerpt=short,
             why=f'"{m.group(1)}" introduces a subordinate clause, and without "that" the '
                 f"reader cannot see where the main clause ends. Most languages cannot drop "
                 f"the equivalent word, so a translating reader stalls here.",
             fix=f'Write "{m.group(1)} that {m.group(2)} …".',
             ste="GR-1")

    # E3 condition placed after the action.
    if commanding:
        first = lwords[0] if lwords else ""
        if first in IMPERATIVE_HINT:
            tail = re.search(r",?\s+\b(if|when|while|after|before|once|unless|until)\b", body_nostep, re.I)
            # Count words before the marker rather than characters: a short
            # command with a trailing condition ("Set the flag to true when …")
            # sat just under a percentage threshold. Requiring three words also
            # spares the case where the marker is the verb's own complement
            # ("Record when the alarm fires").
            before = len(re.findall(r"[A-Za-z][A-Za-z'-]*", body_nostep[: tail.start()])) if tail else 0
            if tail and before >= 3:
                _add(f, code="E3-condition-after-action", family="E", severity="warn",
                     line=lineno, excerpt=short,
                     why="The reader meets the command first and the condition second. Under "
                         "load they act, then discover the step did not apply. The condition "
                         "is the applicability test and has to arrive first.",
                     fix=f'Lead with the condition and separate it with a comma: '
                         f'"{tail.group(1).capitalize()} …, <command>."',
                     ste="5.4, 7.2")

    if CONTRACTION_PAT.search(sent):
        _add(f, code="E4-contraction", family="E", severity="info",
             line=lineno, excerpt=short,
             why="A contraction hides a negation inside a suffix. A reader skimming a "
                 '"do not" step can miss "don\'t" entirely, and the negation is the '
                 "whole content of the step.",
             fix="Write both words in full.",
             ste="4.2")

    for pat, sub in LATIN_ABBREVS:
        if re.search(pat, sent):
            _add(f, code="E5-latin-abbreviation", family="E", severity="info",
                 line=lineno, excerpt=short,
                 why="A Latin abbreviation assumes a shared education. Readers routinely "
                     'swap "e.g." and "i.e.", which inverts example and definition.',
                 fix=f'Use the English words: "{sub}".',
                 ste="GR-6")
            break

    for phrase, sub in OPAQUE_PHRASAL.items():
        if re.search(rf"\b{re.escape(phrase)}\b", low):
            _add(f, code="E6-opaque-phrasal-verb", family="E", severity="info",
                 line=lineno, excerpt=short,
                 why=f'"{phrase}" does not mean what its parts mean, so it cannot be looked up '
                     f"word by word.",
                 fix=f'Use a single verb: "{sub}".',
                 ste="9.3")
            break

    if re.search(r"\w+/\w+", body_nostep) and not re.search(r"https?://|[\w.]+/[\w.]+\.(py|ts|md|js|rs)", body_nostep):
        _add(f, code="E7-slash-conjunction", family="E", severity="info",
             line=lineno, excerpt=short,
             why="A slash does not say whether it means and, or, or both.",
             fix='Write the conjunction you mean. If you mean both, say "A and B". If '
                 'either satisfies it, say "A or B".',
             ste="8.1")

    return f


def check_document(text: str, mode: str, glossary: Sequence[str]) -> list[Finding]:
    findings: list[Finding] = []

    for lineno, sent in iter_units(text):
        findings.extend(check_sentence(lineno, sent, mode, glossary))

    # D4 paragraph load.
    for start, sents in paragraphs(text):
        if len(sents) > 6:
            _add(findings, code="D4-paragraph-overrun", family="D", severity="info",
                 line=start, excerpt=f"{len(sents)} sentences in one paragraph",
                 why=f"{len(sents)} sentences against a ceiling of six. A paragraph is the unit "
                     f"a reader holds at once; past six they stop holding it and start "
                     f"re-reading.",
                 fix="Split at the topic change. One paragraph carries one topic.",
                 ste="6.5, 6.6")

    # A4 synonym drift: several names for what is probably one thing.
    # Clustering on the last word misses the real case ("main body", "body",
    # "body assembly" do not share a head), so cluster on any shared content
    # word instead.
    phrases: dict[str, set[str]] = {}
    for _, sent in iter_units(text):
        toks = re.findall(r"[a-z][a-z-]*", sent.lower())
        for idx, t in enumerate(toks):
            if t not in {"the", "a", "an"}:
                continue
            phrase: list[str] = []
            for nxt in toks[idx + 1: idx + 4]:
                if nxt in FUNCTION_WORDS or nxt in IMPERATIVE_HINT:
                    break
                phrase.append(nxt)
            if not phrase:
                continue
            text_phrase = " ".join(phrase)
            for w in phrase:
                if len(w) >= 4 and w not in FUNCTION_WORDS:
                    phrases.setdefault(w, set()).add(text_phrase)

    for word, variants in sorted(phrases.items()):
        if len(variants) >= 3:
            shown = ", ".join(f'"{v}"' for v in sorted(variants)[:4])
            _add(findings, code="A4-synonym-drift", family="A", severity="warn",
                 line=1,
                 excerpt=f'{len(variants)} names built around "{word}"',
                 why=f"{shown} all name something built around \"{word}\". If these are one "
                     f"thing, the reader is being told there are {len(variants)}. If they are "
                     f"different things, nothing in the text distinguishes them.",
                 fix="Pick one name and use it every time, including where the repetition "
                     "reads badly. Consistency beats elegant variation in a document that "
                     "is executed rather than enjoyed.",
                 ste="1.11, 9.4")

    # D5 mode mixing inside one list.
    raw_lines = text.splitlines()
    visible = strip_noncontent(text)
    list_items = [(i, ln.strip()) for i, (ln, keep) in enumerate(zip(raw_lines, visible), 1)
                  if keep.strip() and re.match(r"^\s*(?:[-*+]|\(?[a-z0-9][.)])\s+\S", ln)]
    if len(list_items) >= 2:
        imper, descr = [], []
        for i, item in list_items:
            body = re.sub(r"^\s*(?:[-*+]|\(?[a-z0-9][.)])\s+", "", item)
            w = re.split(r"\s+", body.strip().lower())[:1]
            if not w or not w[0]:
                continue
            (imper if w[0].strip(".,:;") in IMPERATIVE_HINT else descr).append(i)
        if imper and descr and len(imper) + len(descr) >= 3:
            _add(findings, code="D5-mode-mixing", family="D", severity="info",
                 line=list_items[0][0],
                 excerpt=f"{len(imper)} command item(s), {len(descr)} statement item(s)",
                 why="One list mixes things the reader must do with things that are merely "
                     "true. Scanning it, they cannot tell which items are their "
                     "responsibility.",
                 fix="Split into two lists: what is true, and what to do.",
                 ste="4.3, 6.0")

    return findings


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def summarize(findings: Sequence[Finding]) -> dict:
    by_sev = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
    by_fam = {k: sum(1 for f in findings if f.family == k) for k in FAMILY_TITLE}
    return {"total": len(findings), "by_severity": by_sev, "by_family": by_fam}


def render(findings: Sequence[Finding], mode: str, source: str, strict: bool) -> str:
    out = [f"disambiguate {__version__} — {source}", f"mode: {mode} (ceiling {CEILING[mode]} words)", ""]
    if not findings:
        out.append("  No mechanical ambiguity found.")
        out.append("")
        out.append("  This clears the deterministic layer only. Word-sense, atomicity, and")
        out.append("  whether the stated threshold is the right one still need judgment.")
        return "\n".join(out)

    order = {"block": 0, "warn": 1, "info": 2}
    for fam in sorted(FAMILY_TITLE):
        fam_f = sorted((f for f in findings if f.family == fam),
                       key=lambda f: (order[f.severity], f.line))
        if not fam_f:
            continue
        out.append(f"{fam} — {FAMILY_TITLE[fam]}  ({len(fam_f)})")
        for f in fam_f:
            out.append(f.render())
        out.append("")

    s = summarize(findings)
    out.append(f"total {s['total']}  "
               f"block {s['by_severity']['block']}  "
               f"warn {s['by_severity']['warn']}  "
               f"info {s['by_severity']['info']}")
    if strict:
        out.append("strict: warn is fatal.")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="disambiguate",
        description="Find the places a requirement can be read more than one way.",
    )
    p.add_argument("target", nargs="?", default="-",
                   help="file to check, or - for stdin")
    p.add_argument("--mode", choices=["procedural", "descriptive", "auto"], default="auto",
                   help="procedural text commands the reader (20-word ceiling); "
                        "descriptive text informs them (25). Default: detect.")
    p.add_argument("--glossary", metavar="PATH",
                   help="JSON list of multi-word terms that count as one word "
                        "(product names, proper nouns, document titles)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--strict", action="store_true", help="exit non-zero on warn as well as block")
    p.add_argument("--count", metavar="SENTENCE",
                   help="print the word count for one sentence and exit")
    p.add_argument("--version", action="version", version=__version__)
    a = p.parse_args(argv)

    glossary: list[str] = []
    if a.glossary:
        glossary = json.loads(Path(a.glossary).read_text())

    if a.count is not None:
        n, adv = count_ste_words(a.count, glossary)
        print(n)
        for x in adv:
            print(f"note: {x}", file=sys.stderr)
        return 0

    text = sys.stdin.read() if a.target == "-" else Path(a.target).read_text()
    source = "stdin" if a.target == "-" else a.target
    if not text.strip():
        print("empty input", file=sys.stderr)
        return 2

    mode = detect_mode(text) if a.mode == "auto" else a.mode
    findings = check_document(text, mode, glossary)

    if a.json:
        print(json.dumps({
            "version": __version__,
            "source": source,
            "mode": mode,
            "ceiling": CEILING[mode],
            "summary": summarize(findings),
            "findings": [asdict(f) for f in findings],
        }, indent=2))
    else:
        print(render(findings, mode, source, a.strict))

    if any(f.severity == "block" for f in findings):
        return 1
    if a.strict and any(f.severity == "warn" for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
