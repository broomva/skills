#!/usr/bin/env python3
"""format_lint — catch debunked platform folklore and unsourced precision in content drafts.

Encodes the verified/refuted claim set from broomva/workspace BRO-2145. The point is
narrow and mechanical: a draft should not repeat a claim we already traced to nothing,
and a precise-looking number should be accompanied by something loadable.

Usage:
    format_lint.py <file> [<file>...]      lint files
    format_lint.py -                       lint stdin
    format_lint.py <file> --json           machine-readable
    format_lint.py <file> --strict         WARN also fails the exit code

Exit: 0 clean (or warnings only), 1 if any ERROR (or any finding under --strict).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "references" / "claims-ledger.json"

# severity per category
SEVERITY = {
    "refuted": "ERROR",
    "hypothesis_as_fact": "ERROR",
    "folklore": "WARN",
    "precision_without_source": "WARN",
}


def load_ledger(path: Path = LEDGER) -> dict:
    if not path.exists():
        raise SystemExit(f"format_lint: ledger not found at {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


ALLOW_RX = re.compile(r"format-lint:\s*allow[= ]([A-Za-z0-9_, -]+?)\s*(?:-->|$)")
DISABLE_RX = re.compile(r"format-lint:\s*disable\b")
ENABLE_RX = re.compile(r"format-lint:\s*enable\b")


def _disabled_regions(lines: list[str]) -> tuple[set[int], int | None]:
    """Lines inside an explicit `<!-- format-lint: disable -->` … `enable` region.

    A catalogue of false claims must be able to name them. The safeguard: an UNCLOSED
    disable is reported as a finding, so a document cannot silently switch the gate off
    for everything that follows.
    """
    off: set[int] = set()
    open_at: int | None = None
    for i, line in enumerate(lines):
        if DISABLE_RX.search(line):
            open_at = i if open_at is None else open_at
            off.add(i)
            continue
        if ENABLE_RX.search(line):
            open_at = None
            off.add(i)
            continue
        if open_at is not None:
            off.add(i)
    return off, open_at


def _exempt_lines(lines: list[str]) -> set[int]:
    """0-indexed lines excluded from all rules.

    Two exemptions, both principled:

    * ``` fenced blocks — quoting a bad claim inside a fence is how you *document* it.
      Without this the ledger could not describe itself.
    * YAML frontmatter — `description:` carries trigger phrases, which are the words a
      user types, not assertions the document makes. Linting them would forbid a skill
      from being findable by the very folklore it corrects.
    """
    inside: set[int] = set()
    open_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            open_fence = not open_fence
            inside.add(i)
            continue
        if open_fence:
            inside.add(i)
    # leading YAML frontmatter
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            inside.add(i)
            if lines[i].strip() == "---":
                break
        inside.add(0)
    return inside


def _allowed_ids(lines: list[str], idx: int) -> set[int] | set[str]:
    """Rule ids suppressed for this line via an inline marker on it or the line above.

    Marker form: `<!-- format-lint: allow=rule-id,other-id -->`. Naming the rule is
    required — a blanket suppression would let a document silence the ledger wholesale.
    """
    out: set[str] = set()
    for j in (idx, idx - 1):
        if j < 0 or j >= len(lines):
            continue
        m = ALLOW_RX.search(lines[j])
        if m:
            out |= {s.strip() for s in m.group(1).split(",") if s.strip()}
    return out


def _has_citation_near(lines: list[str], idx: int, markers: list[str], window: int) -> bool:
    lo = max(0, idx - window)
    hi = min(len(lines), idx + window + 1)
    blob = "\n".join(lines[lo:hi])
    return any(m in blob for m in markers)


def lint_text(text: str, ledger: dict) -> list[dict]:
    lines = text.splitlines()
    skip = _exempt_lines(lines)
    disabled, unclosed = _disabled_regions(lines)
    skip |= disabled
    findings: list[dict] = []

    if unclosed is not None:
        findings.append(
            {
                "line": unclosed + 1,
                "severity": "ERROR",
                "category": "lint_control",
                "id": "unclosed-disable",
                "matched": "format-lint: disable",
                "message": "A `format-lint: disable` region was never closed, so every rule is off from here to end of file.",
                "instead": "Close it with `<!-- format-lint: enable -->` immediately after the quoted material.",
            }
        )

    for category in ("refuted", "folklore", "hypothesis_as_fact"):
        for rule in ledger.get(category, []):
            rx = re.compile(rule["pattern"])
            for i, line in enumerate(lines):
                if i in skip:
                    continue
                m = rx.search(line)
                if not m:
                    continue
                if rule["id"] in _allowed_ids(lines, i):
                    continue
                findings.append(
                    {
                        "line": i + 1,
                        "severity": SEVERITY[category],
                        "category": category,
                        "id": rule["id"],
                        "matched": m.group(0)[:80],
                        "message": rule["message"],
                        "instead": rule.get("instead", ""),
                    }
                )

    pws = ledger.get("precision_without_source")
    if pws:
        rx = re.compile(pws["pattern"])
        markers = pws["citation_markers"]
        window = int(pws.get("window_lines", 3))
        for i, line in enumerate(lines):
            if i in skip:
                continue
            if "unsourced-precision" in _allowed_ids(lines, i):
                continue
            for m in rx.finditer(line):
                if _has_citation_near(lines, i, markers, window):
                    continue
                findings.append(
                    {
                        "line": i + 1,
                        "severity": SEVERITY["precision_without_source"],
                        "category": "precision_without_source",
                        "id": "unsourced-precision",
                        "matched": m.group(0)[:80],
                        "message": pws["message"],
                        "instead": "Cite a loadable artifact containing that numeral, or make the claim qualitative.",
                    }
                )

    findings.sort(key=lambda f: (f["line"], f["id"]))
    return findings


def render(path_label: str, findings: list[dict]) -> str:
    if not findings:
        return f"[format-lint] {path_label}: clean"
    out = [f"[format-lint] {path_label}: {len(findings)} finding(s)"]
    for f in findings:
        out.append(f"  {f['severity']:<5} L{f['line']}  ({f['id']})  «{f['matched']}»")
        out.append(f"        {f['message']}")
        if f["instead"]:
            out.append(f"        → {f['instead']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="format_lint")
    ap.add_argument("files", nargs="+", help="files to lint, or - for stdin")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--strict", action="store_true", help="warnings also fail")
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    args = ap.parse_args(argv)

    ledger = load_ledger(args.ledger)
    all_results: dict[str, list[dict]] = {}

    for spec in args.files:
        if spec == "-":
            all_results["<stdin>"] = lint_text(sys.stdin.read(), ledger)
            continue
        p = Path(spec)
        if not p.exists():
            print(f"format_lint: no such file: {spec}", file=sys.stderr)
            return 2
        all_results[str(p)] = lint_text(p.read_text(encoding="utf-8", errors="replace"), ledger)

    if args.as_json:
        print(json.dumps(all_results, indent=2))
    else:
        for label, findings in all_results.items():
            print(render(label, findings))

    flat = [f for fs in all_results.values() for f in fs]
    if args.strict and flat:
        return 1
    return 1 if any(f["severity"] == "ERROR" for f in flat) else 0


if __name__ == "__main__":
    raise SystemExit(main())
