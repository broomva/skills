#!/usr/bin/env python3
"""
validate_report.py — structural linter for a procurer-skill report.

Usage:
    python3 validate_report.py <report.md>

Checks (exit 1 on any failure):
  1. Required top-level headers present: Problem framing, Alternatives,
     Recommendation, Sources.
  2. >= 3 alternatives (sections matching '### Alternative ' prefix).
  3. Each alternative has Thesis, Cost band, Confidence, Providers cited.
  4. Each cost band block contains Low / Typical / High numbers in a
     consistent currency prefix (e.g. '$', 'COP', 'USD').
  5. Each confidence value parses as a float in [0, 1].
  6. Every footnote [N] referenced in the body has a matching entry in
     '## Sources'.
  7. Every source entry has a URL, a title, and a 'fetched' timestamp.
  8. Recommendation block has 'Start with', 'Total budget envelope',
     'Rationale'.

Exit codes:
    0 — all checks pass.
    1 — one or more structural failures.
    2 — usage error (no file, file unreadable).

This validator does NOT verify price accuracy, confidence calibration,
or that the recommendation is sound. Those are the agent's responsibility.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REQUIRED_TOP_HEADERS = [
    "Problem framing",
    "Alternatives",
    "Recommendation",
    "Sources",
]

ALTERNATIVE_REQUIRED_FIELDS = [
    "Thesis",
    "Cost band",
    "Confidence",
    "Providers cited",
]

RECOMMENDATION_REQUIRED_FIELDS = [
    "Start with",
    "Total budget envelope",
    "Rationale",
]

MIN_ALTERNATIVES = 3


def parse_sections(text: str) -> dict[str, str]:
    """Split a markdown doc into top-level `## ` sections.

    Returns a dict of `header_text -> body_text` for each `## Header` block.
    """
    sections: dict[str, str] = {}
    current_header: str | None = None
    current_body: list[str] = []

    for line in text.splitlines():
        match = re.match(r"^##\s+(?!#)(.+?)\s*$", line)
        if match:
            if current_header is not None:
                sections[current_header] = "\n".join(current_body).strip()
            current_header = match.group(1).strip()
            current_body = []
        else:
            if current_header is not None:
                current_body.append(line)

    if current_header is not None:
        sections[current_header] = "\n".join(current_body).strip()

    return sections


def parse_alternatives(alternatives_body: str) -> list[tuple[str, str]]:
    """Split the body of `## Alternatives` into individual `### Alternative …` blocks.

    Returns a list of `(name, body)` tuples.
    """
    blocks: list[tuple[str, str]] = []
    current_name: str | None = None
    current_body: list[str] = []

    for line in alternatives_body.splitlines():
        match = re.match(r"^###\s+(Alternative\s+.+?)\s*$", line)
        if match:
            if current_name is not None:
                blocks.append((current_name, "\n".join(current_body).strip()))
            current_name = match.group(1).strip()
            current_body = []
        else:
            if current_name is not None:
                current_body.append(line)

    if current_name is not None:
        blocks.append((current_name, "\n".join(current_body).strip()))

    return blocks


def find_confidence_values(body: str) -> list[float]:
    """Extract confidence values from an alternative body.

    Looks for patterns like `Confidence: 0.85` or `**Confidence:** 0.85`.
    Returns parsed float values.
    """
    values: list[float] = []
    for match in re.finditer(
        r"Confidence[:\*\s]+([01](?:\.\d+)?)",
        body,
        flags=re.IGNORECASE,
    ):
        try:
            values.append(float(match.group(1)))
        except ValueError:
            continue
    return values


def find_cost_band_numbers(body: str) -> dict[str, list[str]]:
    """Find Low / Typical / High lines in a cost-band block.

    Returns a dict like {"Low": ["$ 80.000"], "Typical": [...], "High": [...]}.
    Each value is a list of raw matched strings (the prefix + number).
    """
    results: dict[str, list[str]] = {"Low": [], "Typical": [], "High": []}
    for label in results:
        for match in re.finditer(
            rf"{label}[:\s]+([^\n]+)",
            body,
            flags=re.IGNORECASE,
        ):
            results[label].append(match.group(1).strip())
    return results


def find_footnotes_referenced(text: str) -> set[int]:
    """Extract all `[N]` footnote references from the body."""
    refs: set[int] = set()
    for match in re.finditer(r"\[(\d+)\]", text):
        refs.add(int(match.group(1)))
    return refs


def find_sources_defined(sources_body: str) -> dict[int, str]:
    """Parse the `## Sources` body into a dict of `id -> source_line`.

    Expects lines like:
        [1] https://example.com — "Title" — fetched 2026-05-13T14:22Z
    """
    sources: dict[int, str] = {}
    for line in sources_body.splitlines():
        match = re.match(r"^\s*\[(\d+)\]\s+(.+)$", line)
        if match:
            sources[int(match.group(1))] = match.group(2).strip()
    return sources


def source_line_has_url_title_fetched(line: str) -> tuple[bool, list[str]]:
    """Verify a source line has a URL, title text, and a fetched timestamp."""
    missing: list[str] = []
    if not re.search(r"https?://\S+", line):
        missing.append("URL")
    # Title: anything between em-dashes or quoted, after URL
    if not re.search(r"[—\-]\s*\S+", line) and not re.search(r'"[^"]+"', line):
        missing.append("title")
    if not re.search(r"fetched\s+\S+", line, flags=re.IGNORECASE):
        missing.append("fetched-at timestamp")
    return (len(missing) == 0, missing)


def detect_currency_prefix(s: str) -> str | None:
    """Identify a currency prefix from a price string (e.g. '$', 'COP', 'USD')."""
    match = re.search(r"(\$|COP|USD|EUR|GBP|MXN|CLP)", s)
    if match:
        return match.group(1)
    return None


def validate(report_path: Path) -> list[str]:
    """Validate a procurer report. Returns a list of error messages (empty if OK)."""
    errors: list[str] = []

    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Cannot read file: {exc}"]

    sections = parse_sections(text)

    # Check 1: required top-level headers
    for header in REQUIRED_TOP_HEADERS:
        if header not in sections:
            errors.append(f"Missing required top-level header: ## {header}")

    # If Alternatives section is missing, downstream checks are moot
    if "Alternatives" not in sections:
        return errors

    # Check 2: >= MIN_ALTERNATIVES
    alternatives = parse_alternatives(sections["Alternatives"])
    if len(alternatives) < MIN_ALTERNATIVES:
        errors.append(
            f"Found {len(alternatives)} alternative(s); need >= {MIN_ALTERNATIVES}."
        )

    # Check 3 + 4 + 5: per-alternative structure
    all_currencies: set[str] = set()
    for name, body in alternatives:
        for field in ALTERNATIVE_REQUIRED_FIELDS:
            if field.lower() not in body.lower():
                errors.append(f"[{name}] missing field: {field}")

        # Cost band — needs Low/Typical/High
        bands = find_cost_band_numbers(body)
        for label, matches in bands.items():
            if not matches:
                errors.append(f"[{name}] cost band missing '{label}'.")
            else:
                for raw in matches:
                    cur = detect_currency_prefix(raw)
                    if cur:
                        all_currencies.add(cur)

        # Confidence — must parse as float in [0,1]
        confs = find_confidence_values(body)
        if not confs:
            errors.append(f"[{name}] no parseable Confidence value found.")
        else:
            for c in confs:
                if not (0.0 <= c <= 1.0):
                    errors.append(
                        f"[{name}] confidence {c} outside [0, 1]."
                    )

    # Check 4 (continued): currency consistency
    if len(all_currencies) > 1:
        errors.append(
            f"Inconsistent currency across alternatives: found {sorted(all_currencies)}."
        )

    # Check 6: footnotes referenced match sources defined
    refs = find_footnotes_referenced(sections["Alternatives"])
    sources = find_sources_defined(sections.get("Sources", ""))

    undefined = refs - set(sources.keys())
    if undefined:
        errors.append(
            f"Footnote(s) referenced but not in ## Sources: {sorted(undefined)}"
        )

    # Check 7: each source has URL + title + fetched-at
    for sid, line in sources.items():
        ok, missing = source_line_has_url_title_fetched(line)
        if not ok:
            errors.append(
                f"Source [{sid}] missing: {', '.join(missing)} — line: {line!r}"
            )

    # Check 8: recommendation block fields
    rec_body = sections.get("Recommendation", "")
    for field in RECOMMENDATION_REQUIRED_FIELDS:
        if field.lower() not in rec_body.lower():
            errors.append(f"## Recommendation missing field: {field}")

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_report.py <report.md>", file=sys.stderr)
        return 2

    report_path = Path(argv[1])
    if not report_path.exists():
        print(f"File not found: {report_path}", file=sys.stderr)
        return 2

    errors = validate(report_path)

    if not errors:
        print(f"OK — {report_path} passes all procurer-report structural checks.")
        return 0

    print(f"FAIL — {report_path} has {len(errors)} structural issue(s):\n")
    for err in errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
