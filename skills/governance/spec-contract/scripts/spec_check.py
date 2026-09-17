#!/usr/bin/env python3
"""spec_check — the deterministic half of the spec contract.

Reads a design doc (markdown or HTML) and checks the invariants that a script
can decide on its own. Everything it cannot decide — whether a decision is
*actually* expensive to reverse, whether an alternative is real or a strawman —
is out of scope by construction and belongs to ``references/rubric.md``.

The checks are a synthesis of five primary sources, each cited on the check that
carries it:

  LYNCH   Michael Lynch, "How to Write an Effective Software Design Document"
          (refactoringenglish.com, 2026-06-24) + the Little Moments worked example
  GOOGLE  Malte Ubl, "Design Docs at Google" (industrialempathy.com)
  RUST    rust-lang/rfcs 0000-template.md
  NYGARD  Michael Nygard, "Documenting Architecture Decisions" (2011)
  OXIDE   Oxide Computer RFD 1, "Requests for Discussion"

Usage:
    spec_check.py DOC [DOC ...] [--profile adr|spec|plan|rfd] [--json]
                  [--strict] [--check-links]

Exit codes: 0 all required checks pass · 1 a required check failed
            2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------
# Section vocabulary.
#
# One producer for every synonym set. A corpus does not use canonical headings —
# "Missing features", "What this is not" and "Out of scope" are all the same
# section — so the checker resolves heading text to a CLASS, never to a name.
# Adding a synonym here is the only supported way to widen a class.
# --------------------------------------------------------------------------

SECTION_CLASSES: dict[str, tuple[str, ...]] = {
    "objective": ("objective", "summary", "purpose", "tl;dr", "tldr", "overview"),
    "context": ("background", "context", "motivation", "problem", "why now"),
    "goals": ("goals", "requirements", "outcomes", "what we want"),
    "non_goals": (
        "non-goals", "non goals", "nongoals", "out of scope", "not in scope",
        "what this is not", "missing features", "explicitly excluded",
        "deliberately omitted", "exclusions",
    ),
    "design": ("design", "architecture", "approach", "proposal", "solution",
               "implementation", "mechanism", "how it works"),
    "alternatives": (
        "alternatives", "alternatives considered", "rationale and alternatives",
        "options considered", "rejected", "why not", "other approaches",
        "prior art", "considered and rejected",
    ),
    "drawbacks": (
        "drawbacks", "consequences", "costs", "downsides", "risks",
        "trade-offs", "tradeoffs", "limitations", "what this costs",
        "negative consequences", "what we give up",
    ),
    "open_questions": (
        "open issues", "open questions", "unresolved questions", "unresolved",
        "unknowns", "to decide", "tbd", "outstanding",
    ),
    "acceptance": (
        "acceptance", "acceptance criteria", "service level objectives", "slo",
        "slos", "success criteria", "definition of done", "how we will know",
        "measurement", "validation", "test plan",
    ),
}

# Profile → (required, recommended). A profile is a claim about which
# reversal-cost axes this document type exists to pin down; it is not a style.
#
# The required set is deliberately small and is the intersection of what the
# five sources agree is load-bearing. `alternatives` is required everywhere
# because all five say so in the same words — GOOGLE calls it "one of the most
# important" sections, RUST makes it a template heading, LYNCH, NYGARD and OXIDE
# each make the comparison the point of the document. A missing recommended
# section warns; the doc still passes.
#
# Measured against this workspace's 105 existing specs/plans/ADRs on 2026-09-16:
# requiring all nine classes passed 1/105. That is a gate nobody adopts, and a
# gate nobody adopts enforces nothing. The split below is what made the contract
# a bar a new doc can clear on purpose rather than a verdict on the back catalog.
PROFILES: dict[str, dict[str, tuple[str, ...]]] = {
    "adr": {
        "required": ("context", "design", "alternatives", "drawbacks"),
        "recommended": ("objective", "acceptance"),
    },
    "spec": {
        "required": ("objective", "design", "non_goals", "alternatives"),
        "recommended": ("context", "goals", "drawbacks", "acceptance",
                        "open_questions"),
    },
    "plan": {
        # A plan with no definition of done is a wish list, so acceptance is
        # required here and merely recommended on a spec.
        "required": ("objective", "goals", "acceptance"),
        "recommended": ("non_goals", "design", "open_questions"),
    },
    "rfd": {
        "required": ("objective", "design", "alternatives", "drawbacks"),
        "recommended": ("context", "open_questions", "acceptance"),
    },
    "note": {
        # For short docs that are still design-bearing. The floor, not a pass.
        "required": ("design",),
        "recommended": ("objective", "alternatives"),
    },
}


def required(profile: str) -> tuple[str, ...]:
    return PROFILES[profile]["required"]


def recommended(profile: str) -> tuple[str, ...]:
    return PROFILES[profile]["recommended"]

# NYGARD: proposed/accepted/deprecated/superseded, "if a decision is reversed we
# will keep the old one around, but mark it as superseded".
# OXIDE: prediscussion/ideation/discussion/published/committed/abandoned.
# The union below is deliberately permissive; the constraint that bites is that
# a terminal state must name its successor.
VALID_STATUSES = {
    "draft", "prediscussion", "ideation", "proposed", "in-review", "discussion",
    "accepted", "published", "implemented", "committed", "deprecated",
    "superseded", "abandoned", "rejected", "design-complete",
}
STATUS_NEEDS_POINTER = {"superseded", "deprecated"}

# GOOGLE: "non-goals aren't negated goals like 'The system shouldn't crash', but
# rather things that could reasonably be goals, but are explicitly chosen not to
# be goals." A bare negation is the defect this detects.
NEGATION_HEAD = re.compile(
    r"^\W*(?:the\s+\w+\s+)?(?:should\s+not|shouldn'?t|must\s+not|mustn'?t|"
    r"will\s+not|won'?t|cannot|can'?t|does\s+not|doesn'?t|is\s+not|isn'?t|"
    r"never|avoid(?:ing)?|prevent(?:ing)?)\b",
    re.I,
)
# The discriminator is the MODAL, not the word "no". A declined goal is a noun
# phrase — "No support for albums", "Location-aware caching" — and never reaches
# NEGATION_HEAD, which matches only modal/auxiliary negations. An earlier cut
# added a noun-phrase exemption on top and it suppressed a true positive ("Must
# not lose data": "not lose" read as a noun phrase), so the exemption is gone.

REJECTION_MARKERS = re.compile(
    r"\b(?:but|however|rejected|reject|too\s+\w+|lock-?in|expensive|costly|"
    r"complexity|overkill|doesn'?t|don'?t|can'?t|cannot|wouldn'?t|lacks?|"
    r"missing|instead|downside|drawback|risk|slower|unsupported|not\s+worth|"
    r"ruled\s+out|discarded|dismissed|cons?\s*:|\bcons\b)",
    re.I,
)

# GOOGLE's implementation-manual anti-pattern: "If a doc basically says 'This is
# how we are going to implement it' without going into trade-offs, alternatives,
# and explaining decision making … it would probably have been a better idea to
# write the actual program right away."
TRADEOFF_LANGUAGE = re.compile(
    r"\b(?:trade-?offs?|instead\s+of|rather\s+than|at\s+the\s+cost\s+of|"
    r"we\s+rejected|versus|vs\.?|downside|upside|alternative|in\s+exchange|"
    r"we\s+chose|we\s+considered|weighed|compared\s+(?:to|with)|"
    r"the\s+cost\s+is|pros?\s+and\s+cons?|one-?way\s+door|two-?way\s+door)\b",
    re.I,
)

# LYNCH's SLO section: "A well-defined SLO prevents ambiguity by expressing goals
# in concrete, objective terms." A number with a unit, a percentage, or a
# runnable command all count as concrete; adjectives do not.
MEASURABLE = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s?(?:%|ms|s\b|sec|seconds?|min|minutes?|h\b|hours?|"
    r"days?|weeks?|GB|MB|KB|TB|req/s|rps|qps|LOC|lines|px|USD|\$)|"
    r"\bp\d{2}\b|\b\d+/\d+\b|\$\d|`[^`]*(?:test|check|pytest|cargo|make|npm|"
    r"bun|curl|gh)\b[^`]*`)",
    re.I,
)

# NYGARD: "All consequences should be listed here, not just the positive ones."
# This is a COST vocabulary, deliberately distinct from TRADEOFF_LANGUAGE above:
# a drawbacks section states what the chosen design costs, which is not the same
# utterance as comparing it to an option that was not chosen.
COST_LANGUAGE = re.compile(
    r"\b(?:cost(?:s|ly)?|expensive|doubles?|increases?|grows?|slower|slows?|"
    r"harder|more\s+\w+|loses?|lose|losing|give[s]?\s+up|gave\s+up|"
    r"sacrific\w+|at\s+the\s+expense|penalt\w+|degrad\w+|regress\w+|"
    r"no\s+longer|breaks?|limits?|limitation|risk|downside|drawback|"
    r"trade-?off|we\s+accept|requires?\s+(?:more|extra|additional)|"
    r"overhead|complexity|debt|churn|coupling|lock-?in|cannot|can'?t|"
    r"won'?t\s+\w+|fragile|brittle)\b",
    re.I,
)

# LYNCH on open issues: each entry should say "What is the immediate next step
# for resolving the issue?"
NEXT_STEP = re.compile(
    r"\b(?:next\s+step|proposed(?:\s+solution)?|resolution|decide\s+by|owner|"
    r"we\s+will|plan(?:ned)?\s+to|action|ask\s+\w+|spike|prototype|measure|"
    r"benchmark|investigate|defer(?:red)?\s+to)\b",
    re.I,
)

# GOOGLE: "The sweet spot for a larger project seems to be around 10-20ish pages.
# If you get way beyond that, it might make sense to split up the problem."
# ~500 words/page.
WORDS_PER_PAGE = 500
MAX_PAGES = 20
MIN_WORDS = 250

STATUS_LINE = re.compile(r"\bstatus\b\s*[:\-–—]\s*([^\n<·|]{1,80})", re.I)
REVERSAL_LINE = re.compile(
    r"\b(?:reversal[\s-]cost|reversibility|decision[\s-]class|door)\b"
    r"\s*[:\-–—]?\s*([^\n<·|]{0,60})",
    re.I,
)
ONE_WAY = re.compile(r"\bone-?way\b", re.I)
TWO_WAY = re.compile(r"\btwo-?way\b", re.I)
URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+")


@dataclass
class Section:
    level: int
    title: str
    body: str
    cls: str | None = None
    # Body PLUS every nested subsection, down to the next heading at or above
    # this one's level. Every content check reads `subtree`, never `body`:
    # a doc that puts its SLO numbers under `### Latency` beneath
    # `## Service level objectives` has a section whose own body is empty, and
    # a check that reads `body` would score it as having said nothing.
    subtree: str = ""

    @property
    def items(self) -> list[str]:
        """Bullet items in the section subtree, or paragraphs when it has none."""
        src = self.subtree or self.body
        bullets = [
            re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", ln).strip()
            for ln in src.splitlines()
            if re.match(r"^\s*(?:[-*+]|\d+\.)\s+\S", ln)
        ]
        if bullets:
            return bullets
        return [p.strip() for p in re.split(r"\n\s*\n", src) if p.strip()]


@dataclass
class Finding:
    check: str
    severity: str  # "fail" | "warn"
    message: str
    evidence: str = ""


@dataclass
class Report:
    path: str
    profile: str
    words: int
    sections: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(f.severity == "fail" for f in self.findings)


# --------------------------------------------------------------------------
# Parsing. Two entry surfaces — markdown and HTML — and every check runs over
# the same Section list, so neither surface can drift into being unchecked.
# --------------------------------------------------------------------------

def _strip_html(raw: str) -> str:
    s = re.sub(r"(?is)<(script|style|svg|head)[^>]*>.*?</\1>", " ", raw)
    s = re.sub(r"(?is)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|pre|blockquote|td)>", "\n", s)
    s = re.sub(r"(?is)<li[^>]*>", "- ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                 ("&#39;", "'"), ("&nbsp;", " "), ("&mdash;", "—"),
                 ("&ndash;", "–"), ("&hellip;", "…")):
        s = s.replace(a, b)
    return s


def parse(raw: str, is_html: bool) -> tuple[list[Section], str]:
    """Return (sections, plain_text). Plain text keeps the front matter."""
    if is_html:
        heading_re = re.compile(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>")
        marks: list[tuple[int, int, int, str]] = []
        for m in heading_re.finditer(raw):
            title = _strip_html(m.group(2))
            marks.append((m.start(), m.end(), int(m.group(1)),
                          re.sub(r"\s+", " ", title).strip()))
        sections = []
        for i, (_s, e, lvl, title) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(raw)
            sections.append(Section(lvl, title, _strip_html(raw[e:end])))
        return sections, _strip_html(raw)

    lines = raw.splitlines()
    sections, cur, buf = [], None, []
    for ln in lines:
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", ln)
        if m:
            if cur:
                cur.body = "\n".join(buf)
                sections.append(cur)
            cur, buf = Section(len(m.group(1)), m.group(2).strip(), ""), []
        elif cur is not None:
            buf.append(ln)
    if cur:
        cur.body = "\n".join(buf)
        sections.append(cur)
    return sections, raw


def attach_subtrees(sections: list[Section]) -> None:
    """Fill `subtree` for every section: its own body plus all nested ones."""
    for i, sec in enumerate(sections):
        parts = [sec.body]
        for nxt in sections[i + 1:]:
            if nxt.level <= sec.level:
                break
            parts.append(nxt.title)
            parts.append(nxt.body)
        sec.subtree = "\n".join(parts)


def classify(sections: Iterable[Section]) -> None:
    for sec in sections:
        t = re.sub(r"^[\d.\s]+", "", sec.title).strip().lower().rstrip(":")
        t = re.sub(r"[🔗#]", "", t).strip()
        best: tuple[int, str] | None = None
        for cls, names in SECTION_CLASSES.items():
            for name in names:
                if t == name:
                    score = 1000
                elif t.startswith(name) or t.endswith(name):
                    score = 500 + len(name)
                elif re.search(rf"\b{re.escape(name)}\b", t):
                    score = len(name)
                else:
                    continue
                if best is None or score > best[0]:
                    best = (score, cls)
        sec.cls = best[1] if best else None


def infer_profile(path: Path, words: int | None = None) -> str:
    """Profile from the path, falling back to `note` for genuinely short docs.

    The word threshold matters: GOOGLE explicitly blesses the "1-3 page mini
    design doc", so a 400-word note judged against the full spec profile would
    fail for being what it was meant to be.
    """
    p = str(path).lower()
    if "/adrs/" in p or "-adr-" in p or p.endswith("adr.md"):
        return "adr"
    if "/plans/" in p:
        return "plan"
    if "/rfd" in p or "/rfcs/" in p:
        return "rfd"
    if words is not None and words < 700:
        return "note"
    return "spec"


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check(path: Path, profile: str | None, strict: bool,
          check_links: bool) -> Report:
    raw = path.read_text(encoding="utf-8", errors="replace")
    is_html = path.suffix.lower() in (".html", ".htm")
    sections, text = parse(raw, is_html)
    attach_subtrees(sections)
    classify(sections)
    words = len(re.findall(r"\b[\w'-]+\b", text))
    prof = profile or infer_profile(path, words)
    if prof not in PROFILES:
        raise SystemExit(f"unknown profile {prof!r}; pick from {sorted(PROFILES)}")

    by_cls: dict[str, list[Section]] = {}
    for s in sections:
        if s.cls:
            by_cls.setdefault(s.cls, []).append(s)

    rep = Report(str(path), prof, words,
                 {c: "; ".join(s.title for s in v) for c, v in by_cls.items()})
    add = rep.findings.append

    # --- C1 required sections (LYNCH inclusion rule, per-profile) ------------
    for cls in required(prof):
        if cls not in by_cls:
            add(Finding(
                "C1-missing-section", "fail",
                f"profile {prof!r} requires a {cls.replace('_', ' ')} section; "
                f"none of {SECTION_CLASSES[cls][:4]}… matched any heading",
            ))
    for cls in recommended(prof):
        if cls not in by_cls:
            add(Finding(
                "C1-missing-recommended", "warn",
                f"profile {prof!r} recommends a {cls.replace('_', ' ')} section",
            ))

    # --- C2 status (NYGARD supersession, OXIDE state machine) ----------------
    m = STATUS_LINE.search(text)
    if not m:
        add(Finding("C2-no-status", "fail",
                    "no 'Status:' field; a doc with no state cannot be "
                    "superseded, and a doc that cannot be superseded silently "
                    "becomes a false description of what shipped"))
    else:
        val = m.group(1).strip().lower()
        head = re.split(r"[\s,(]", val)[0].strip(" .")
        if head not in VALID_STATUSES:
            add(Finding("C2-bad-status", "warn",
                        f"status {head!r} is outside the known state set",
                        evidence=m.group(0).strip()))
        elif head in STATUS_NEEDS_POINTER:
            tail = text[m.end():m.end() + 400]
            if not (URL_RE.search(m.group(0) + tail)
                    or re.search(r"\b(?:by|→|->)\s*\S+", val)
                    or re.search(r"\.(?:md|html)\b", m.group(0) + tail)):
                add(Finding("C2-dangling-supersede", "fail",
                            f"status {head!r} names no successor; NYGARD "
                            "requires a reference to the replacement",
                            evidence=m.group(0).strip()))

    # --- C3 reversal cost declared (LYNCH's inclusion rule, made explicit) ---
    rm = REVERSAL_LINE.search(text)
    if not rm:
        sev = "fail" if strict else "warn"
        add(Finding("C3-no-reversal-cost", sev,
                    "no reversal-cost / one-way-vs-two-way-door declaration; "
                    "LYNCH's inclusion rule ('what's the penalty for being "
                    "wrong?') is the reason this document exists"))
    elif not (ONE_WAY.search(rm.group(0)) or TWO_WAY.search(rm.group(0))
              or re.search(r"\b(?:high|low|medium|irreversible|cheap|expensive)\b",
                           rm.group(1), re.I)):
        add(Finding("C3-vague-reversal-cost", "warn",
                    "reversal cost is named but not graded",
                    evidence=rm.group(0).strip()))

    # --- C4 non-goals are not negated goals (GOOGLE) -------------------------
    for sec in by_cls.get("non_goals", []):
        for item in sec.items:
            head = item.strip()
            if not head or len(head) < 8:
                continue
            if NEGATION_HEAD.match(head):
                add(Finding(
                    "C4-negated-goal", "warn",
                    "non-goal reads as a negated requirement, not a goal "
                    "deliberately declined (GOOGLE: non-goals 'aren't negated "
                    "goals like \"The system shouldn't crash\"')",
                    evidence=head[:160]))

    # --- C5 alternatives: >=2, each with a reason (RUST, GOOGLE, LYNCH) ------
    alts = by_cls.get("alternatives", [])
    if alts:
        named: list[str] = []
        for sec in alts:
            named += [i for i in sec.items if len(i.strip()) > 3]
            # Sub-headings nested under the alternatives heading are the other
            # idiom for naming an option (the Little Moments doc uses exactly
            # this: "### Alternative frontend stacks" → "#### FontAwesome").
            start = next(i for i, s in enumerate(sections) if s is sec)
            for s in sections[start + 1:]:
                if s.level <= sec.level:
                    break
                named.append(s.title)
        distinct = {re.sub(r"\W+", " ", n).strip().lower()[:60] for n in named if n}
        distinct = {d for d in distinct if len(d) > 3}
        if len(distinct) < 2:
            add(Finding("C5-thin-alternatives", "fail",
                        f"alternatives section names {len(distinct)} option(s); "
                        "RUST asks 'what other designs have been considered and "
                        "what is the rationale for not choosing them?' — one "
                        "option is not a comparison"))
        body = " ".join(s.subtree for s in alts)
        if not REJECTION_MARKERS.search(body):
            add(Finding("C5-no-rejection-reason", "fail",
                        "alternatives are listed with no stated reason for "
                        "rejection; a list of options is not a rationale"))

    # --- C6 drawbacks of the CHOSEN design (RUST 'Drawbacks', NYGARD) --------
    if "drawbacks" in required(prof) + recommended(prof):
        dsec = by_cls.get("drawbacks", [])
        if dsec and not COST_LANGUAGE.search(" ".join(s.subtree for s in dsec)):
            add(Finding("C6-drawbacks-without-cost", "fail",
                        "drawbacks/consequences section states no cost; NYGARD: "
                        "'All consequences should be listed here, not just the "
                        "positive ones'"))

    # --- C7 open questions carry a next step (LYNCH) ------------------------
    for sec in by_cls.get("open_questions", []):
        body = sec.subtree.strip()
        if not body or re.fullmatch(r"[-*\s]*(none|n/?a|nothing)\.?", body, re.I):
            continue
        if not NEXT_STEP.search(body):
            add(Finding("C7-open-question-without-next-step", "warn",
                        "open questions state no next step; LYNCH requires "
                        "'what is the immediate next step for resolving the "
                        "issue?'", evidence=sec.title))

    # --- C8 acceptance is measurable (LYNCH SLOs) ---------------------------
    if "acceptance" in required(prof) + recommended(prof):
        asec = by_cls.get("acceptance", [])
        if asec and not MEASURABLE.search(" ".join(s.subtree for s in asec)):
            add(Finding("C8-unmeasurable-acceptance", "fail",
                        "acceptance/SLO section contains no number, unit or "
                        "runnable command; LYNCH: a well-defined SLO 'prevents "
                        "ambiguity by expressing goals in concrete, objective "
                        "terms'"))

    # --- C9 implementation-manual detector (GOOGLE) -------------------------
    hits = len(TRADEOFF_LANGUAGE.findall(text))
    if hits == 0 and words > MIN_WORDS:
        add(Finding("C9-implementation-manual", "fail",
                    "no trade-off language anywhere in the document; GOOGLE: a "
                    "doc that says 'this is how we are going to implement it' "
                    "without trade-offs 'would probably have been a better idea "
                    "to write the actual program right away'"))

    # --- C10 size (GOOGLE 10-20 pages) --------------------------------------
    pages = words / WORDS_PER_PAGE
    if pages > MAX_PAGES:
        add(Finding("C10-oversized", "warn",
                    f"~{pages:.0f} pages ({words} words); GOOGLE puts the sweet "
                    f"spot at 10-20 and suggests splitting the problem beyond it"))
    elif words < MIN_WORDS:
        add(Finding("C10-stub", "warn",
                    f"{words} words — below the {MIN_WORDS}-word floor; this "
                    "reads as a stub, not a design doc"))

    # --- C11 link liveness (opt-in; keeps the default gate hermetic) --------
    if check_links:
        import urllib.error
        import urllib.request
        seen: set[str] = set()
        for url in URL_RE.findall(text):
            url = url.rstrip(".,;:)")
            if url in seen:
                continue
            seen.add(url)
            try:
                req = urllib.request.Request(
                    url, method="HEAD",
                    headers={"User-Agent": "spec-check/1.0"})
                urllib.request.urlopen(req, timeout=8)
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 405, 429):
                    continue  # blocked to bots, not dead
                add(Finding("C11-dead-link", "fail",
                            f"link returns HTTP {exc.code}", evidence=url))
            except Exception as exc:  # noqa: BLE001 - network shapes vary
                add(Finding("C11-dead-link", "warn",
                            f"link unreachable: {type(exc).__name__}",
                            evidence=url))

    return rep


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def render(rep: Report) -> str:
    out = [f"{rep.path}  [profile={rep.profile} words={rep.words} "
           f"classes={len(rep.sections)}/{len(SECTION_CLASSES)}]"]
    if not rep.findings:
        out.append("  ok — every required check passed")
    for f in sorted(rep.findings, key=lambda x: (x.severity != "fail", x.check)):
        mark = "FAIL" if f.severity == "fail" else "warn"
        out.append(f"  [{mark}] {f.check}: {f.message}")
        if f.evidence:
            out.append(f"         ↳ {f.evidence}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="spec_check", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="+", type=Path)
    ap.add_argument("--profile", choices=sorted(PROFILES),
                    help="override the profile inferred from the path")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="promote the reversal-cost warning to a failure")
    ap.add_argument("--check-links", action="store_true",
                    help="resolve every http(s) URL (network; off by default)")
    ns = ap.parse_args(argv)

    reports = []
    for doc in ns.docs:
        if not doc.exists():
            print(f"spec_check: no such file: {doc}", file=sys.stderr)
            return 2
        reports.append(check(doc, ns.profile, ns.strict, ns.check_links))

    if ns.json:
        print(json.dumps([asdict(r) for r in reports], indent=2))
    else:
        print("\n\n".join(render(r) for r in reports))
        bad = sum(1 for r in reports if r.failed)
        if len(reports) > 1:
            print(f"\n{len(reports) - bad}/{len(reports)} documents pass")

    return 1 if any(r.failed for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
