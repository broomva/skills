"""The reflection lint: a claim the data cannot back fails the build.

A *claim* is every paragraph, list item, table row and blockquote outside a
heading. Each must:

* cite at least one episode, as ``[e-1a2b3c4d]`` or ``[e-1a2b3c4d, e-5e6f7a8b]``
  (claims under a ``Data notes`` heading are exempt from this rule only);
* cite only episodes that exist;
* quote only the user's own words: a blockquote, or a quoted span of three or
  more words, must appear verbatim in a prompt of an episode the claim cites;
* use only numbers present in ``data.json``. Plain numbers, thousands
  separators, ``%`` and ``K``/``M`` suffixes are checked; ISO dates, episode
  and ticket ids, ``#123`` references, URLs, quotes and inline code are not
  numbers. Put identifiers that contain digits (``Python 3.9``) in backticks.

The reflection must also have the five sections: Monthly arcs and the four
chapters.
"""

from __future__ import annotations

import math
import re
from typing import Dict, Iterable, List, Set, Tuple

from . import CITATION, EPISODE_ID, TICKET, norm_quote, quote_found

REQUIRED_SECTIONS = ("Monthly arcs", "Themes and ideas", "How you worked with agents", "Challenges and outcomes",
                     "Insights for next year")
EXEMPT_SECTIONS = ("data notes",)

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_CODE = re.compile(r"`[^`]*`")
_URL = re.compile(r"https?://\S+")
_DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?(?:T\d{2}:\d{2})?\b")
_REF = re.compile(r"#\d+\b")
_QUOTED = re.compile(r"“([^”]+)”|\"([^\"]+)\"")
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?:\s?([KkMm%])(?![a-zA-Z]))?")


def units(markdown: str) -> Tuple[List[dict], List[str], List[str]]:
    """Claims as ``{"line", "section", "kind", "text"}``, the headings, and structural errors."""
    out: List[dict] = []
    headings: List[str] = []
    errors: List[str] = []
    lines = markdown.splitlines()
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1
    section = ""
    current = None
    in_comment = in_fence = False
    table_row = 0

    def close():
        nonlocal current
        if current and current["text"].strip():
            out.append(current)
        current = None

    for n in range(i, len(lines)):
        line = lines[n]
        stripped = line.strip()
        if in_comment:
            in_comment = "-->" not in line
            continue
        if stripped.startswith("<!--"):
            close()
            in_comment = "-->" not in stripped
            continue
        if stripped.startswith("```"):
            close()
            if not in_fence:
                errors.append(f"line {n + 1}: fenced blocks are not allowed in a reflection")
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _HEADING.match(line)
        if heading:
            close()
            section = heading.group(2).strip()
            headings.append(section)
            table_row = 0
            continue
        if not stripped or _RULE.match(line):
            close()
            table_row = 0
            continue
        if stripped.startswith("|"):
            # Only headings, paragraphs, list items and blockquotes are allowed:
            # every table shape tried as an exemption (label headers, separator
            # rows) was a way to state a claim the lint did not check.
            close()
            if table_row == 0:
                errors.append(f"line {n + 1}: tables are not allowed in a reflection; "
                              "write each claim as a sentence or list item")
            table_row += 1
            out.append({"line": n + 1, "section": section, "kind": "row", "text": stripped})
            continue
        if stripped.startswith(">"):
            body = stripped.lstrip(">").strip()
            if current is None or current["kind"] != "blockquote":
                close()
                current = {"line": n + 1, "section": section, "kind": "blockquote", "text": body}
            else:
                current["text"] += " " + body
            continue
        if _LIST.match(line):
            close()
            current = {"line": n + 1, "section": section, "kind": "item", "text": _LIST.sub("", line, 1)}
            continue
        if current is None or current["kind"] == "blockquote":
            close()
            current = {"line": n + 1, "section": section, "kind": "paragraph", "text": stripped}
        else:
            current["text"] += " " + stripped
    close()
    return out, headings, errors


def payload_numbers(data) -> List[float]:
    found: List[float] = []

    def walk(node):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            if math.isfinite(node):
                found.append(float(node))
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return found


def number_supported(token: Tuple[str, str, str], values: Iterable[float]) -> bool:
    whole, frac, suffix = token
    n = float(whole.replace(",", "") + ("." + frac if frac else ""))
    places = len(frac or "")
    scale = {"k": 1e3, "m": 1e6}.get((suffix or "").lower(), 1.0)
    for v in values:
        if scale == 1.0 and abs(v - n) < 1e-9:
            return True
        if round(v / scale, places) == n and (scale > 1 or places > 0):
            return True
    return False


def _without_unchecked(text: str) -> str:
    text = CITATION.sub(" ", text)
    text = EPISODE_ID.sub(" ", text)
    text = _CODE.sub(" ", text)
    text = _URL.sub(" ", text)
    text = _QUOTED.sub(" ", text)
    text = TICKET.sub(" ", text)
    text = _REF.sub(" ", text)
    return _DATE.sub(" ", text)


def lint(markdown: str, episodes: Dict[str, dict], data) -> Tuple[List[str], dict]:
    """``(errors, stats)`` for a reflection against its episodes (by id) and data payload."""
    claims, headings, errors = units(markdown)
    errors = list(errors)
    values = payload_numbers(data)
    stats = {"claims": len(claims), "cited": 0, "citations": 0, "quotes": 0, "numbers": 0}
    lowered = [h.lower() for h in headings]
    for name in REQUIRED_SECTIONS:
        if not any(name.lower() in h for h in lowered):
            errors.append(f"missing section: {name}")
    all_prompts = None
    for claim in claims:
        where = f"line {claim['line']}"
        text = claim["text"]
        cited: Set[str] = set()
        for group in CITATION.findall(text):
            cited |= {x.strip() for x in group.split(",")}
        cited |= set(EPISODE_ID.findall(text))
        stats["citations"] += len(cited)
        for eid in sorted(cited):
            if eid not in episodes:
                errors.append(f"{where}: citation {eid} does not resolve to an episode")
        exempt = claim["section"].lower().startswith(EXEMPT_SECTIONS)
        if not CITATION.search(text):
            if not exempt:
                errors.append(f"{where}: uncited claim: {text[:80]}")
        else:
            stats["cited"] += 1
        prompts = [p["text"] for eid in cited if eid in episodes for p in episodes[eid]["prompts"]]
        quotes = []
        if claim["kind"] == "blockquote":
            body = CITATION.sub("", text).strip().strip("—- ").strip()
            body = re.sub(r"\s*[—-]\s*$", "", body)
            quotes.append(body.strip("“”\""))
        for a, b in _QUOTED.findall(text):
            span = a or b
            if len(span.split()) >= 3:
                quotes.append(span)
        for q in quotes:
            stats["quotes"] += 1
            if not quote_found(q, prompts):
                if all_prompts is None:
                    all_prompts = [p["text"] for e in episodes.values() for p in e["prompts"]]
                hint = (" (it is in another episode: cite that one)" if quote_found(q, all_prompts)
                        else "")
                errors.append(f"{where}: quote is not verbatim from a cited user prompt{hint}: "
                              f"“{norm_quote(q)[:60]}”")
        for token in _NUMBER.findall(_without_unchecked(text)):
            stats["numbers"] += 1
            if not number_supported(token, values):
                shown = token[0] + ("." + token[1] if token[1] else "") + (token[2] or "")
                errors.append(f"{where}: number {shown} is not in the data payload")
    return errors, stats
