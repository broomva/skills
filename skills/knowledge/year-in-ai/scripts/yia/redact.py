"""Share-safe redaction.

The private deck quotes real prompts and names real repositories, because that
specificity is most of what makes the artefact worth looking at.  A deck that
leaves the machine must not.

The rule that matters: redaction **relabels, it never deletes**.  A project
whose path is sensitive keeps its counts under a placeholder, so totals and
shares still sum to the same numbers.  Dropping the row instead would quietly
change every percentage on the card and make the share-safe deck disagree with
the private one.
"""

from __future__ import annotations

import copy
import re
from typing import Any

#: Path segments that mark a location as client or personal data by default.
SENSITIVE_SEGMENTS = (
    "crm", "client", "clients", "private", "confidential", "secrets",
    "personal", "invoices", "payroll", "contracts",
)

PLACEHOLDER = "«redacted»"

#: Fields whose value is free text written by a human and never safe to share.
FREE_TEXT_PATHS = (
    ("moments", "first_prompt", "text"),
)


def _norm_terms(terms: tuple[str, ...] | list[str] | None) -> list[str]:
    return sorted({t.strip().lower() for t in (terms or []) if t and t.strip()})


def is_sensitive(value: str | None, terms: list[str]) -> bool:
    """Does this path or label touch a sensitive segment or extra term?"""
    if not value:
        return False
    lowered = value.lower()
    segments = set(re.split(r"[/\\\s._-]+", lowered))
    if segments & set(SENSITIVE_SEGMENTS):
        return True
    return any(term in lowered for term in terms)


def _label(value: str | None, terms: list[str], *, keep_basename: bool) -> str | None:
    if value is None:
        return None
    if is_sensitive(value, terms):
        return PLACEHOLDER
    if keep_basename:
        parts = [p for p in re.split(r"[/\\]", value) if p]
        return parts[-1] if parts else value
    return value


def _redact_ranking(rows: list[dict[str, Any]], terms: list[str], *, keep_basename: bool) -> list[dict[str, Any]]:
    """Relabel rows, merging any that collapse onto the same placeholder.

    Merging rather than dropping is what preserves the totals: two sensitive
    projects become one ``«redacted»`` row whose count is their sum.
    """
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = _label(row.get("name"), terms, keep_basename=keep_basename)
        key = name or ""
        if key in merged:
            merged[key]["count"] += row.get("count", 0)
            merged[key]["share"] = round(merged[key]["share"] + row.get("share", 0.0), 4)
        else:
            merged[key] = {**row, "name": name}
    return sorted(merged.values(), key=lambda r: -r.get("count", 0))


def redact(payload: dict[str, Any], extra_terms: tuple[str, ...] | list[str] | None = None) -> dict[str, Any]:
    """Return a share-safe copy of ``payload``."""
    terms = _norm_terms(extra_terms)
    out = copy.deepcopy(payload)

    rankings = out.get("rankings") or {}
    for key, keep_basename in (("projects", True), ("branches", False)):
        if isinstance(rankings.get(key), list):
            rankings[key] = _redact_ranking(rankings[key], terms, keep_basename=keep_basename)

    moments = out.get("moments") or {}
    for section in ("longest_session", "hardest_session", "first_prompt"):
        node = moments.get(section)
        if isinstance(node, dict):
            if "project" in node:
                node["project"] = _label(node.get("project"), terms, keep_basename=True)
            if "branch" in node:
                node["branch"] = _label(node.get("branch"), terms, keep_basename=False)

    for path in FREE_TEXT_PATHS:
        node: Any = out
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict) and path[-1] in node:
            node[path[-1]] = None
            node["text_redacted"] = True

    phrases = moments.get("top_phrases")
    if isinstance(phrases, list):
        moments["top_phrases"] = [
            row for row in phrases if not is_sensitive(row.get("phrase"), terms)
        ]

    # Absolute filesystem roots identify the machine and its owner.
    for report in out.get("coverage") or []:
        if isinstance(report, dict):
            report["root"] = None

    outcomes = out.get("outcomes") or {}
    git = outcomes.get("git")
    if isinstance(git, dict) and isinstance(git.get("by_repo"), list):
        git["by_repo"] = [
            {**row, "repo": _label(row.get("repo"), terms, keep_basename=True)}
            for row in git["by_repo"]
        ]

    out["share_safe"] = True
    out["redaction"] = {
        "segments": list(SENSITIVE_SEGMENTS),
        "extra_terms": terms,
        "policy": "relabel-and-merge; counts are preserved so totals match the private deck",
    }
    return out
