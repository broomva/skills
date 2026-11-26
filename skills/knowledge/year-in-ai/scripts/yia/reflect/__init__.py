"""reflect: reason about how the year went, not just count it.

The ledger counts turns without keeping their text. Reflect goes back to the
stores, rebuilds each session a person drove as an *episode* (their prompts,
the agents' trimmed final replies, what was invoked, where it was corrected),
has subagents digest the episodes in batches, joins them to outcomes (merged
PRs, tickets, knowledge-graph entities), and leaves the invoking agent a
cited ``reflection.md`` that a lint holds to the data.

Stages, each a ``year_in_ai.py reflect`` subcommand:

1. ``episodes``  code only: episodes, digest batches, sampled tool traces.
2. (agents)      one digest subagent per batch writes ``digests/<id>.json``.
3. ``check``     validates every digest; a quote must be the user's own words.
4. ``join``      code only: links episodes to merged PRs, tickets, KG entities.
5. ``reduce``    code only: the data payload and the month packets.
6. (agent)       the invoking agent writes ``reflection.md``.
7. ``lint``      every claim cited, every citation real, every quote verbatim,
                 every number in the payload.

**Privacy.** Episodes hold the user's words. Everything this package writes
goes under a private directory (``~/.local/share/year-in-ai/reflect/<year>``,
mode 0700, files 0600), never into the ledger, the repo or any service.
``reflect share`` writes a redacted copy of the reflection for anything that
leaves the machine.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_ROOT = "~/.local/share/year-in-ai/reflect"

#: An episode id: ``e-`` and eight hex characters (more only on a collision).
EPISODE_ID = re.compile(r"\be-[0-9a-f]{8,16}\b")
#: A citation in reflection.md: one or more episode ids in square brackets.
CITATION = re.compile(r"\[(e-[0-9a-f]{8,16}(?:\s*,\s*e-[0-9a-f]{8,16})*)\]")
#: A tracker ticket id such as ``BRO-1234``.
TICKET = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-([0-9]{1,6})\b")
#: A pull request URL on GitHub.
PR_URL = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/pull/([0-9]+)")

#: Prefixes that look like ticket ids but are standards, models and encodings.
NOT_TICKETS = {
    "UTF", "SHA", "ISO", "GPT", "RFC", "CVE", "MD", "HTTP", "TLS", "SSL", "AES", "RSA", "COVID", "MP", "H",
    "PEP", "ES", "ECMA", "IEEE", "X", "LLAMA", "QWEN", "CLAUDE", "OPUS", "SONNET", "HAIKU", "GEMINI", "P",
    "K", "V", "BASE", "INT", "FP", "BF", "Q", "WCAG", "WPA", "PCI", "SOC", "GDPR", "OK", "TODO", "TOP",
    "PR", "IP", "IPV", "PG", "PY", "CSS", "HTML", "JSON", "API", "MCP", "LLM", "AI", "UI", "UX",
}


def private_dir(year: int, root: Optional[str] = None) -> Path:
    """The private directory for one year's reflection, created 0700."""
    base = Path(os.path.expanduser(root or DEFAULT_ROOT))
    path = base / str(year)
    path.mkdir(parents=True, exist_ok=True)
    for p in (base, path):
        try:
            os.chmod(p, 0o700)
        except OSError:
            pass
    return path


def write_private(path: Path, text: str) -> None:
    """Write a text file readable only by its owner, creating its directory 0700."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)


def write_json(path: Path, data) -> None:
    write_private(path, json.dumps(data, indent=1, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path: Path) -> list:
    out = []
    if not path.is_file():
        return out
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


_QUOTE_CHARS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", " ": " "})
_WS = re.compile(r"\s+")


def norm_quote(text: str) -> str:
    """Text as compared for a verbatim quote: straight quotes, collapsed whitespace, trimmed."""
    return _WS.sub(" ", text.translate(_QUOTE_CHARS)).strip()


def quote_found(quote: str, texts: Iterable[str]) -> bool:
    """Is ``quote`` a contiguous, case-sensitive span of one of ``texts`` (whitespace-insensitive)?"""
    q = norm_quote(quote).strip(" .,;:!?\"'")
    if not q:
        return False
    return any(q in norm_quote(t) for t in texts if t)


def episode_id(session_hash: str, taken: Optional[set] = None) -> str:
    """``e-`` plus the first eight hex characters of the session hash, longer on a collision."""
    for n in (8, 10, 12, 16):
        candidate = f"e-{session_hash[:n]}"
        if taken is None or candidate not in taken:
            return candidate
    return f"e-{hashlib.sha1(session_hash.encode()).hexdigest()[:16]}"


def tickets_in(text: str, allowed: Optional[set] = None) -> set:
    """Ticket ids in ``text``, minus look-alikes; only ``allowed`` prefixes when given."""
    out = set()
    for prefix, num in TICKET.findall(text or ""):
        if prefix in NOT_TICKETS or prefix.isdigit():
            continue
        if allowed is not None and prefix not in allowed:
            continue
        out.add(f"{prefix}-{int(num)}")
    return out


def pr_urls_in(text: str) -> set:
    return {f"https://github.com/{repo}/pull/{num}" for repo, num in PR_URL.findall(text or "")}
