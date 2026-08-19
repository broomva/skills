#!/usr/bin/env python3
"""format_lint — flag unsupported platform claims and unsourced precision in drafts.

Severity follows the ledger's GRADE, not the author's confidence:

    refuted            ERROR  contradicted by a primary source that was loaded
    contested          WARN   the literature genuinely disagrees
    unverified         WARN   origin could not be located — NOT proof of falsity
    folklore           WARN   circulates as fact with no located basis
    hypothesis_as_fact WARN   plausible mechanism asserted as established

The refuted/unverified split is the point. "I could not find a source" is a statement
about a search, not about the world, and a linter that conflates the two manufactures
exactly the false confidence it exists to prevent.

Usage:
    format_lint.py <file>...        lint files ( - for stdin )
    format_lint.py <f> --json       machine-readable
    format_lint.py <f> --strict     warnings also fail the exit code

Exit: 0 clean/warnings, 1 on ERROR (or any finding under --strict), 2 on bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "references" / "claims-ledger.json"

GRADE_SEVERITY = {
    "refuted": "ERROR",
    "contested": "WARN",
    "unverified": "WARN",
    "folklore": "WARN",
    "hypothesis_as_fact": "WARN",
}

ALLOW_RX = re.compile(r"format-lint:\s*allow[= ]([A-Za-z0-9_, -]+?)\s*(?:-->|$)")
CONTROL_RX = re.compile(r"^\s*<!--\s*format-lint:\s*(disable|enable)\s*-->\s*$")
MARKER_BLANK_RX = re.compile(r"<!--\s*format-lint:.*?-->")

# A rule must not fire when the sentence denies, corrects, or attributes the claim —
# otherwise the linter punishes the corrections it exists to promote.
SENT_SPLIT_RX = re.compile(r"(?<=[.!?;])\s+")


def _negated_at(line: str, start: int) -> bool:
    """True when the SENTENCE containing `start` denies/corrects/attributes the claim.

    Line-level scoping was too coarse: an unrelated "This is not complicated." earlier on
    the same line suppressed a live assertion after it.
    """
    pos = 0
    for sent in SENT_SPLIT_RX.split(line):
        seg = line.find(sent, pos)
        if seg == -1:
            seg = pos
        if seg <= start < seg + len(sent):
            return bool(NEGATION_RX.search(sent))
        pos = seg + len(sent)
    return bool(NEGATION_RX.search(line))


NEGATION_RX = re.compile(
    r"(?i)\b(?:not|never|no longer|isn't|is ?n't|aren't|doesn't|does not|don't|do not|"
    r"myth|false|untrue|debunk\w*|misquot\w*|misattribut\w*|unfounded|no evidence|"
    r"claims? that|allegedly|supposedly|so-called|refut\w*|contrary to)\b"
)


def load_ledger(path: Path = LEDGER) -> dict:
    if not path.exists():
        raise SystemExit(f"format_lint: ledger not found at {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    bad = [
        (r.get("id", "?"), r.get("grade"))
        for cat in ("refuted", "folklore", "hypothesis_as_fact")
        for r in data.get(cat, [])
        if r.get("grade") not in GRADE_SEVERITY
    ]
    if bad:
        raise SystemExit(
            "format_lint: unknown grade(s) in ledger — a typo must not silently "
            f"downgrade severity: {bad}"
        )
    return data


def _fence_and_frontmatter(lines: list[str]) -> tuple[set[int], list[dict]]:
    """Exempt fenced blocks and *well-formed* YAML frontmatter; report malformed ones.

    Frontmatter requires a closing `---` AND at least one `key:` line — otherwise a
    Markdown horizontal rule at the top of a file would exempt the whole document.
    An unclosed fence is reported rather than silently swallowing the remainder.
    """
    exempt: set[int] = set()
    problems: list[dict] = []

    fence_open_at: int | None = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
            fence_open_at = None if fence_open_at is not None else i
            exempt.add(i)
            continue
        if fence_open_at is not None:
            exempt.add(i)
    if fence_open_at is not None:
        problems.append(
            {
                "line": fence_open_at + 1,
                "severity": "ERROR",
                "category": "lint_control",
                "id": "unclosed-fence",
                "matched": "```",
                "message": "An unclosed code fence exempts every line to end of file.",
                "instead": "Close the fence.",
            }
        )

    if lines and lines[0].strip() == "---":
        close = next((j for j in range(1, len(lines)) if lines[j].strip() == "---"), None)
        if close is not None and any(
            re.match(r"^[A-Za-z_][\w-]*\s*:", lines[j]) for j in range(1, close)
        ):
            exempt |= set(range(0, close + 1))
    return exempt, problems


def _control_regions(lines: list[str], fenced: set[int] | None = None) -> tuple[set[int], list[dict]]:
    """`<!-- format-lint: disable -->` … `enable`, as an exact standalone comment.

    Guards: an unclosed region is an ERROR; a nested disable is an ERROR; and a region
    spanning effectively the whole document is an ERROR, because a closed whole-file
    region would otherwise be a silent total bypass.
    """
    off: set[int] = set()
    problems: list[dict] = []
    open_at: int | None = None
    spans: list[tuple[int, int]] = []

    fenced = fenced or set()
    for i, line in enumerate(lines):
        m = None if i in fenced else CONTROL_RX.match(line)
        if not m:
            if open_at is not None:
                off.add(i)
            continue
        off.add(i)
        if m.group(1) == "disable":
            if open_at is not None:
                problems.append(
                    {
                        "line": i + 1, "severity": "ERROR", "category": "lint_control",
                        "id": "nested-disable", "matched": "format-lint: disable",
                        "message": "A disable region is already open; nesting is collapsed by a single enable.",
                        "instead": "Close the first region before opening another.",
                    }
                )
            else:
                open_at = i
        else:
            if open_at is not None:
                spans.append((open_at, i))
            open_at = None

    if open_at is not None:
        problems.append(
            {
                "line": open_at + 1, "severity": "ERROR", "category": "lint_control",
                "id": "unclosed-disable", "matched": "format-lint: disable",
                "message": "A disable region was never closed, so every rule is off to end of file.",
                "instead": "Close it with `<!-- format-lint: enable -->` right after the quoted material.",
            }
        )

    body = [i for i, l in enumerate(lines) if l.strip()]
    if body:
        covered = sum(1 for i in body if i in off)
        if covered / len(body) > 0.8:
            problems.append(
                {
                    "line": (spans[0][0] + 1) if spans else 1,
                    "severity": "ERROR", "category": "lint_control",
                    "id": "whole-file-disable", "matched": "format-lint: disable",
                    "message": f"Disable regions cover {covered}/{len(body)} non-blank lines — effectively a whole-file bypass.",
                    "instead": "Scope suppressions to the quoted material, or use inline allow=<rule-id> markers.",
                }
            )
    return off, problems


def _allowed_ids(lines: list[str], idx: int) -> set[str]:
    """Rule ids suppressed on THIS line only.

    Current-line-only by design: a marker that also covered the next line let one
    comment excuse two separate assertions.
    """
    m = ALLOW_RX.search(lines[idx]) if 0 <= idx < len(lines) else None
    return {s.strip() for s in m.group(1).split(",") if s.strip()} if m else set()


def _blocks(lines: list[str], skip: set[int]) -> list[tuple[str, list[int]]]:
    """Join hard-wrapped lines into paragraph blocks, keeping a char->line map.

    Real markdown wraps at ~90 columns, so a claim routinely straddles a newline. Matching
    per raw line silently misses those — which is how a real-world article containing the
    exact fabrication this linter was built to catch came back clean.
    """
    out: list[tuple[str, list[int]]] = []
    buf: list[str] = []
    owner: list[int] = []

    def flush() -> None:
        if buf:
            joined = " ".join(buf)
            assert len(joined) == len(owner), "char->line map desynchronised"
            out.append((joined, owner[:]))

    for i, line in enumerate(lines):
        if i in skip or not line.strip():
            flush()
            buf, owner = [], []
            continue
        # Blank out format-lint's own control/allow comments, offset-preserving. They are
        # metadata, not prose — and a rule id such as `sends-3-5x-likes` literally contains
        # the pattern it names, so an unblanked marker matches itself.
        seg = MARKER_BLANK_RX.sub(lambda m: " " * len(m.group(0)), line).strip()
        if not seg:
            flush()
            buf, owner = [], []
            continue
        if buf:
            owner.append(i)  # the joining space belongs to the line it pulls in
        buf.append(seg)
        owner.extend([i] * len(seg))
    flush()
    return out


def _line_of(owner: list[int], offset: int) -> int:
    return owner[min(offset, len(owner) - 1)] if owner else 0


def lint_text(text: str, ledger: dict) -> list[dict]:
    lines = text.splitlines()
    exempt, problems = _fence_and_frontmatter(lines)
    ctrl_off, ctrl_problems = _control_regions(lines, exempt)
    skip = exempt | ctrl_off
    findings: list[dict] = list(problems) + list(ctrl_problems)

    blocks = _blocks(lines, skip)

    for category in ("refuted", "folklore", "hypothesis_as_fact"):
        for rule in ledger.get(category, []):
            grade = rule.get("grade", category)
            severity = GRADE_SEVERITY.get(grade, "WARN")
            rx = re.compile(rule["pattern"])
            for btext, owner in blocks:
                for m in rx.finditer(btext):
                    if _negated_at(btext, m.start()):
                        continue
                    lo = _line_of(owner, m.start())
                    hi = _line_of(owner, m.end() - 1)
                    spanned = range(lo, hi + 1)
                    if any(rule["id"] in _allowed_ids(lines, k) for k in spanned):
                        continue
                    findings.append(
                        {
                            "line": lo + 1, "severity": severity, "category": category,
                            "grade": grade, "id": rule["id"],
                            "matched": " ".join(m.group(0).split())[:80],
                            "message": rule["message"], "instead": rule.get("instead", ""),
                        }
                    )

    pws = ledger.get("precision_without_source")
    if pws:
        rx = re.compile(pws["pattern"])
        window = int(pws.get("window_lines", 3))
        # A marker must look like a RESOLVABLE locator. A bare "https://" or the
        # substring "PMC" is not a citation.
        marker_rx = re.compile(pws["marker_regex"], re.I)
        for btext, owner in blocks:
            for m in rx.finditer(btext):
                if _negated_at(btext, m.start()):
                    continue
                lo = _line_of(owner, m.start())
                hi = _line_of(owner, m.end() - 1)
                if any("unsourced-precision" in _allowed_ids(lines, k) for k in range(lo, hi + 1)):
                    continue
                blob = "\n".join(lines[max(0, lo - window) : min(len(lines), hi + window + 1)])
                if marker_rx.search(blob):
                    continue
                findings.append(
                    {
                        "line": lo + 1, "severity": "WARN",
                        "category": "precision_without_source", "grade": "unverified",
                        "id": "unsourced-precision",
                        "matched": " ".join(m.group(0).split())[:80],
                        "message": pws["message"],
                        "instead": "Cite a resolvable URL or DOI containing that figure, or make the claim qualitative.",
                    }
                )

    findings.sort(key=lambda f: (f["line"], f["id"]))
    return findings


def render(label: str, findings: list[dict]) -> str:
    if not findings:
        return f"[format-lint] {label}: clean"
    out = [f"[format-lint] {label}: {len(findings)} finding(s)"]
    for f in findings:
        grade = f.get("grade", f["category"])
        out.append(f"  {f['severity']:<5} L{f['line']}  ({f['id']} · {grade})  «{f['matched']}»")
        out.append(f"        {f['message']}")
        if f["instead"]:
            out.append(f"        → {f['instead']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="format_lint")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    args = ap.parse_args(argv)

    ledger = load_ledger(args.ledger)
    results: dict[str, list[dict]] = {}
    for spec in args.files:
        if spec == "-":
            results["<stdin>"] = lint_text(sys.stdin.read(), ledger)
            continue
        p = Path(spec)
        if not p.exists():
            print(f"format_lint: no such file: {spec}", file=sys.stderr)
            return 2
        results[str(p)] = lint_text(p.read_text(encoding="utf-8", errors="replace"), ledger)

    if args.as_json:
        print(json.dumps(results, indent=2))
    else:
        for label, findings in results.items():
            print(render(label, findings))

    flat = [f for fs in results.values() for f in fs]
    if args.strict and flat:
        return 1
    return 1 if any(f["severity"] == "ERROR" for f in flat) else 0


if __name__ == "__main__":
    raise SystemExit(main())
