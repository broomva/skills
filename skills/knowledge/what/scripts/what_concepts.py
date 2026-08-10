#!/usr/bin/env python3
"""what_concepts.py — deterministic concept inventory for the `what` skill.

`/what` explains the *concepts* a session used, at the operator's register.
The explaining is latent work. Deciding **which** terms need explaining is
precision work, and this script does it:

  1. Resolve the session slice (transcript JSONL, conversation markdown, or raw text).
  2. Extract candidate technical terms from the agent's prose.
  3. Mark each term agent-introduced (the human never used it) and
     defined-inline (the agent already glossed it in-session).
  4. Classify knowledge-graph coverage: grounded / partial / ungrounded.
  5. Rank, and emit markdown or JSON.

The ranking exists so the explanation leads with what actually blocks
understanding, rather than with what was hardest to build. A term used
repeatedly, never glossed, with no entity page, is the highest-value row in
the table — and a Bookkeeping (P6) filing candidate.

Usage
-----
    # everything since the last time you asked /what, in the current project
    python3 what_concepts.py

    # a specific transcript, whole session, machine-readable
    python3 what_concepts.py --transcript ~/.claude/projects/-Users-x/abc.jsonl \
        --scope session --json

    # a P1 Bridge conversation log, or arbitrary text on stdin
    python3 what_concepts.py --conversation docs/conversations/2026-08-10.md
    git log -p -3 | python3 what_concepts.py --text -

Exit codes: 0 = inventory produced (possibly empty), 1 = source not found or
unreadable, 2 = bad usage.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

__version__ = "1.0.0"

EXIT_OK = 0
EXIT_NO_SOURCE = 1
EXIT_USAGE = 2


# --------------------------------------------------------------------------
# Path resolution (mirrors kg.py precedence: env > policy.yaml > default)
# --------------------------------------------------------------------------

def find_policy(start: Path) -> Path | None:
    """Nearest-ancestor .control/policy.yaml walking up from `start` (inclusive)."""
    d = start.resolve()
    for cand_dir in [d, *d.parents]:
        cand = cand_dir / ".control" / "policy.yaml"
        if cand.is_file():
            return cand
    return None


def policy_knowledge_block(policy: Path) -> dict:
    """Top-level `knowledge:` mapping from policy.yaml, or {} if unusable.

    A missing file, absent PyYAML, malformed YAML, or a non-mapping value all
    degrade to {} — path resolution must never crash the inventory.
    """
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    try:
        data = yaml.safe_load(policy.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    block = data.get("knowledge")
    return block if isinstance(block, dict) else {}


def resolve_catalog(explicit: str | None, start: Path) -> Path | None:
    """Resolve docs/knowledge-index.md. Returns None when nothing exists.

    Grounding is a bonus, never a precondition: with no catalog every term is
    reported `ungrounded` and the inventory still ranks correctly.
    """
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    env = os.environ.get("KG_CATALOG")
    if env:
        p = Path(env).expanduser()
        return p if p.is_file() else None
    policy = find_policy(start)
    if policy is not None:
        root = policy.parent.parent
        cat = policy_knowledge_block(policy).get("catalog_path")
        if isinstance(cat, str) and cat:
            p = Path(cat).expanduser()
            p = p if p.is_absolute() else (root / p)
            if p.is_file():
                return p
        p = root / "docs" / "knowledge-index.md"
        if p.is_file():
            return p
    p = Path.home() / "broomva" / "docs" / "knowledge-index.md"
    return p if p.is_file() else None


def resolve_claude_md(explicit: str | None, start: Path) -> Path | None:
    """Nearest-ancestor CLAUDE.md — the source of the P1-P20 short-name table."""
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    d = start.resolve()
    for cand_dir in [d, *d.parents]:
        cand = cand_dir / "CLAUDE.md"
        if cand.is_file():
            return cand
    p = Path.home() / "broomva" / "CLAUDE.md"
    return p if p.is_file() else None


def project_slug(cwd: Path) -> str:
    """Claude Code encodes a project dir by flattening its path separators.

    /Users/broomva/broomva  ->  -Users-broomva-broomva
    /Users/broomva/.buzz    ->  -Users-broomva--buzz
    """
    return re.sub(r"[/._]", "-", str(cwd))


def resolve_transcript(
    transcript: str | None, project_dir: str | None, cwd: Path
) -> Path | None:
    """Newest *.jsonl for this project, or an explicit override.

    Walks up from cwd so a worktree deep inside a repo still resolves to the
    repo's own project dir rather than silently finding nothing.
    """
    if transcript:
        p = Path(transcript).expanduser()
        return p if p.is_file() else None
    if project_dir:
        d: Path | None = Path(project_dir).expanduser()
    else:
        base = Path(
            os.environ.get("CLAUDE_PROJECTS_DIR", str(Path.home() / ".claude" / "projects"))
        ).expanduser()
        d = None
        for cand_dir in [cwd.resolve(), *cwd.resolve().parents]:
            cand = base / project_slug(cand_dir)
            if cand.is_dir():
                d = cand
                break
    if d is None or not d.is_dir():
        return None
    files = sorted(
        (p for p in d.glob("*.jsonl") if p.is_file()),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    return files[0] if files else None


# --------------------------------------------------------------------------
# Session model
# --------------------------------------------------------------------------

@dataclass
class Turn:
    role: str  # "human" | "agent"
    text: str
    ref: str = ""
    ts: str = ""


WHAT_INVOCATION = re.compile(r"^\s*/what\b", re.IGNORECASE)

# Claude Code records a user-invoked slash command as an XML envelope, not as the
# typed text — and the exact shape varies by version, so BOTH forms are reachable:
#   <command-name>/what</command-name>\n<command-message>what</command-message>...
#   /what
# Matching only the raw form made the entire since-last-what scope inert in
# production. The captured name is compared exactly, so /whatever and /effort
# never count as a /what marker.
COMMAND_NAME = re.compile(r"<command-name>\s*/?([a-z0-9][a-z0-9-]*)\s*</command-name>", re.I)


def is_what_invocation(text: str) -> bool:
    """True when this human turn is a `/what` invocation, in either recorded form."""
    m = COMMAND_NAME.search(text)
    if m:
        return m.group(1).lower() == "what"
    return bool(WHAT_INVOCATION.match(text))


def load_transcript(path: Path, include_tools: bool, include_sidechains: bool) -> list[Turn]:
    """Parse a Claude Code transcript JSONL into human/agent turns.

    Three channels exist in the file; only two are the agent's *vocabulary*:
      - assistant `text` blocks  -> agent prose (always mined)
      - `tool_use` inputs        -> code the agent wrote (opt-in, --include-tools)
      - `tool_result` content    -> files the agent merely *read* (never mined)

    Mining tool_results would flood the inventory with terms the agent never
    chose, which is the opposite of what `/what` is for. `thinking` blocks are
    skipped too: the operator never saw them, so they cannot be why something
    failed to land.
    """
    turns: list[Turn] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        if row.get("isSidechain") and not include_sidechains:
            continue
        if row.get("isMeta"):
            continue
        rtype = row.get("type")
        msg = row.get("message")
        if not isinstance(msg, dict):
            continue
        ref = str(row.get("uuid") or "")
        ts = str(row.get("timestamp") or "")
        content = msg.get("content")

        if rtype == "user":
            # A real human turn carries a plain string. A list is tool_result
            # plumbing wearing the "user" role — never a human utterance.
            if isinstance(content, str) and content.strip():
                turns.append(Turn("human", content, ref, ts))
            continue

        if rtype != "assistant" or not isinstance(content, list):
            continue
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif btype == "tool_use" and include_tools:
                parts.append(json.dumps(block.get("input", ""), ensure_ascii=False))
        if parts:
            turns.append(Turn("agent", "\n".join(parts), ref, ts))
    return turns


CONVO_TURN = re.compile(r"^#{1,4}\s*(user|human|assistant|agent|claude)\b", re.IGNORECASE)


def load_conversation(path: Path) -> list[Turn]:
    """Parse a P1 Bridge conversation markdown log into turns.

    Recognises `## User` / `### Assistant` style headers. A file with no such
    headers degrades to one agent turn holding the whole body, which still
    yields a usable inventory.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    turns: list[Turn] = []
    role: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if role and "\n".join(buf).strip():
            turns.append(Turn(role, "\n".join(buf).strip()))

    for line in text.splitlines():
        m = CONVO_TURN.match(line)
        if m:
            flush()
            head = m.group(1).lower()
            role = "human" if head in ("user", "human") else "agent"
            buf = []
            continue
        if role:
            buf.append(line)
    flush()
    if not turns and text.strip():
        return [Turn("agent", text)]
    return turns


def slice_scope(turns: list[Turn], scope: str) -> tuple[list[Turn], str]:
    """Return (sliced turns, effective scope).

    `auto` and `since-last-what` cut everything up to and including the last
    human turn that invoked /what — "explain what happened since I last asked".
    One rule covers both the post-arc case and the mid-conversation
    "wait, what?" case, so no separate mode is needed.
    """
    if scope == "session":
        return turns, "session"
    markers = [i for i, t in enumerate(turns) if t.role == "human" and is_what_invocation(t.text)]
    end = len(turns)
    # The invocation running right now is the final turn. Slicing after *it* yields
    # nothing, so the slice opens at the PREVIOUS marker and closes just before the
    # live one — that is what "everything since you last asked" means. Dropping only
    # a trailing marker keeps the offline case (a saved transcript) working unchanged.
    if markers and markers[-1] == len(turns) - 1:
        end = len(turns) - 1
        markers = markers[:-1]
    if markers:
        return turns[markers[-1] + 1:end], "since-last-what"
    return turns, "session"


# --------------------------------------------------------------------------
# Term extraction
# --------------------------------------------------------------------------

FENCE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
# Path stripping is done token-wise, NOT by regex. Any `\S*/\S*` form is quadratic on
# a long slash-free run — every start position rescans the whole token hunting for a
# slash — so one pasted JWT or hash list stalled the tool for 16s. Splitting on
# whitespace first makes it linear, and a file path is by definition one token.
PATH_EXT = re.compile(
    r"\.(?:md|py|ts|tsx|js|jsx|json|ya?ml|toml|rs|sh|txt|html|css)$", re.IGNORECASE
)

PRIMITIVE_NAMED = re.compile(r"\b([A-Z][A-Za-z]*(?:-[A-Z][A-Za-z]*)*)\s*\(P(\d{1,2})\)")
PRIMITIVE_BARE = re.compile(r"\bP([1-9]|1[0-9]|20)\b")
KEBAB = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+){1,5}\b")
SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,4}\b")
CAMEL = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")
ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,5}\b")

# Generic engineering vocabulary the operator already owns. `/what` is for
# workspace-specific jargon, not a dictionary of the industry. Extend per-run
# with --stopword; override a specific entry with --keep-term.
STOPWORDS = {
    "api", "cli", "ci", "cd", "pr", "prs", "url", "uri", "id", "ids", "ui", "ux",
    "os", "io", "db", "sql", "http", "https", "json", "yaml", "toml", "html", "css",
    "md", "todo", "fixme", "note", "ok", "utc", "iso", "ascii", "utf",
    "npm", "sdk", "mcp", "llm", "ast", "e2e", "qa", "vm", "ssh", "dns", "tls",
    "aws", "gcp", "us", "it", "the", "and", "for", "not", "but", "all", "any",
    "eof", "env", "cwd", "pwd", "tmp", "src", "lib", "bin", "dir", "repo",
    "up-to-date", "well-formed", "well-known", "read-only", "write-only",
    "end-to-end", "out-of-scope", "in-scope", "state-of-the-art", "so-called",
    "follow-up", "follow-ups", "trade-off", "trade-offs",
    "high-level", "low-level", "long-running", "short-lived", "one-off",
    "first-class", "third-party", "open-source", "real-time", "run-time",
    "left-hand", "right-hand", "step-by-step", "line-by-line", "case-by-case",
    "non-zero", "no-op", "no-ops", "double-check", "self-contained", "built-in",
    "opt-in", "opt-out", "drop-in", "back-and-forth",
    # Harness tool-input keys and stdlib call names. These flood the inventory
    # under --include-tools, where the mined text is code rather than prose.
    # A fixed, enumerable set — not whack-a-mole.
    "file_path", "old_string", "new_string", "run_in_background", "replace_all",
    "tool_use_id", "subagent_type", "is_file", "is_dir", "read_text",
    "write_text", "file_paths", "max_results", "timeout_ms",
    # shouted status labels — verdicts and log levels, not concepts
    "fail", "pass", "warn", "skip", "major", "minor", "blocker", "critical",
    "done", "error", "debug", "info", "trace", "yes", "new", "old",
    "important", "never", "always", "must", "only", "before", "after",
}

# A two-segment compound starting with one of these is English hyphenation
# ("re-invoke", "auto-deleted"), not workspace vocabulary. Anything the
# knowledge graph grounds is exempt, so a real term never gets filtered here.
PREFIX_SEGMENTS = {
    "re", "auto", "un", "non", "pre", "post", "de", "over", "under", "semi",
    "anti", "co", "bi", "tri", "mid", "mis", "sub", "multi", "inter", "intra",
    "self", "ex", "pro", "counter",
}

# Frequency says a term was load-bearing; it does not say the term was confusing.
# Cap its contribution so the explanation-need signals decide the ranking.
#
# INVARIANT (asserted below, and pinned by test_scoring_constants_*): for two terms
# of the same kind and the same agent_introduced value, a never-glossed ungrounded
# term outranks an already-glossed grounded one at ANY frequency. That requires the
# explanation-need advantage to exceed the largest frequency advantage:
#     UNDEFINED_BONUS + (ungrounded - grounded) > FREQ_CAP
# The first version shipped 2.0 + 0.5 = 2.5 against a cap of 4.0, so the headline
# claim was false above ~15 uses.
FREQ_WEIGHT = 1.2
FREQ_CAP = 4.0
UNDEFINED_BONUS = 5.0
AGENT_INTRODUCED_BONUS = 3.0

KIND_WEIGHT = {"primitive": 2.0, "kebab": 1.5, "camel": 1.0, "acronym": 1.0, "snake": 0.5}
COVERAGE_WEIGHT = {"grounded": 1.0, "partial": 0.5, "ungrounded": 1.5}

MIN_LEN = {"kebab": 6, "snake": 6, "camel": 5, "acronym": 2}

# A shared slug segment must be this long to imply partial coverage; shorter ones
# ("gate", "loop", "state") match half the graph and mean nothing.
PARTIAL_SEGMENT_MIN = 6

assert UNDEFINED_BONUS + (COVERAGE_WEIGHT["ungrounded"] - COVERAGE_WEIGHT["grounded"]) > FREQ_CAP, (
    "scoring constants violate the ranking invariant: a loud already-glossed term "
    "would outrank a quiet never-glossed one"
)

# A trailing run/ticket/version number makes the compound an identifier, not an
# idea: round-2, board-m3, bro-2107, run-264, slice_1.
IDENT_TAIL = re.compile(r"[a-z]?\d+")


def scrub(text: str, keep_code: bool) -> str:
    """Strip the surfaces that produce terms nobody chose: fences, URLs, paths.

    Whitespace is collapsed last so extraction and the `uses` recount see the same
    shape. Without it a line-wrapped `Cross-Review\\n(P20)` extracts as the canonical
    `Cross-Review (P20)` and then recounts to zero, silently dropping the row.
    """
    if not keep_code:
        text = FENCE.sub(" ", text)
    # No separate URL pass: every URL is one whitespace-delimited token containing
    # `/`, so the path filter already removes it. A dedicated `URL.sub` here was dead
    # code — deleting it left the whole suite green, which is how it was found.
    return " ".join(
        tok for tok in text.split()
        if "/" not in tok and not PATH_EXT.search(tok.rstrip(".,;:)]}"))
    )


def count_uses(text: str, term: str, kind: str) -> int:
    """Occurrences of `term`, using the boundary its own extraction pattern implies.

    Acronyms and CamelCase are extracted on `\\b`, so `RCS` inside `RCS-based` IS a
    use and must be counted as one — the strict `(?<![\\w-])` guard scored those at
    zero and dropped the term. Kebab/snake/primitive keep the strict guard, so
    `review` is never counted inside `cross-review`.
    """
    if kind == "primitive" and " (" in term:
        # PRIMITIVE_NAMED reconstructs a CANONICAL surface ("Bookkeeping (P6)") from a
        # match that allowed any spacing ("Bookkeeping(P6)"). Counting the canonical
        # form literally then returns 0 and silently drops the highest-weight row.
        name, rest = term.split(" (", 1)
        pattern = rf"(?<![\w-]){re.escape(name)}\s*\({re.escape(rest.rstrip(')'))}\)"
    elif kind in ("acronym", "camel"):
        pattern = rf"\b{re.escape(term)}\b"
    else:
        pattern = rf"(?<![\w-]){re.escape(term)}(?![\w-])"
    return len(re.findall(pattern, text))


def normalize(term: str) -> str:
    """Fold a term into knowledge-graph slug shape for lookup.

    'Cross-Review (P20)' -> 'cross-review-p20';  'HttpClient' -> 'http-client'
    """
    t = re.sub(r"[()\[\]{}]", "", term)
    t = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", t)
    t = re.sub(r"[_\s]+", "-", t)
    t = re.sub(r"-{2,}", "-", t)
    return t.strip("-").lower()


def extract_terms(text: str) -> dict[str, str]:
    """Return {surface term: kind} for one blob of prose.

    A `Name (Pn)` hit suppresses the bare `Name`, so 'Bookkeeping (P6)' does not
    also appear as a separate CamelCase row for 'Bookkeeping'.
    """
    found: dict[str, str] = {}
    suppress: set[str] = set()
    for m in PRIMITIVE_NAMED.finditer(text):
        found[f"{m.group(1)} (P{int(m.group(2))})"] = "primitive"
        suppress.add(m.group(1))
        suppress.add(f"P{int(m.group(2))}")
    for m in PRIMITIVE_BARE.finditer(text):
        if m.group(0) not in suppress:
            found.setdefault(m.group(0), "primitive")
    for pat, kind in ((KEBAB, "kebab"), (SNAKE, "snake"), (CAMEL, "camel"), (ACRONYM, "acronym")):
        for m in pat.finditer(text):
            if m.group(0) in suppress:
                continue
            found.setdefault(m.group(0), kind)
    return found


def is_noise(
    term: str, kind: str, stopwords: set[str], keep: set[str], grounded: bool = False
) -> bool:
    """Heuristic filters, ordered so the knowledge graph always wins.

    An explicit --keep-term outranks everything; a grounded term outranks every
    heuristic below it. Only unrecognised terms are judged on shape.
    """
    low = term.lower()
    if low in keep:
        return False
    if grounded:
        return False
    if low in stopwords:
        return True
    if len(term) < MIN_LEN.get(kind, 0):
        return True
    if kind in ("kebab", "snake"):
        segs = low.split("-" if kind == "kebab" else "_")
        if IDENT_TAIL.fullmatch(segs[-1]):
            return True  # round-2, board-m3, bro-2107 — an identifier, not an idea
        if len(segs) == 2 and segs[0] in PREFIX_SEGMENTS:
            return True
    return False


def definitional(text: str, term: str) -> bool:
    """Did the session already gloss this term? Then it does not need explaining."""
    t = re.escape(term)
    # The term must not be a prefix of a longer hyphenated sibling: "cross-review-gate"
    # is not a gloss of "cross-review", and a bare `-` in the separator class made
    # every such compound read as a definition, zeroing the never-glossed signal.
    end = r"(?![\w-])"
    patterns = (
        rf"{t}{end}\s+(?:is|are|was|were|means?|refers to|stands for)\b",
        rf"{t}{end}\s*[—–]\s*\w",          # em/en dash gloss (never a plain hyphen)
        rf"{t}{end}\s*[:=]\s+\w",          # "term: gloss"
        rf"\b(?:i\.e\.|that is|in other words|which is)[^.\n]{{0,80}}{t}{end}",
        rf"{t}{end}\s*\([^)]{{4,}}\)",
    )
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


# --------------------------------------------------------------------------
# Knowledge-graph grounding
# --------------------------------------------------------------------------

# Live catalog heads carry two shapes the strict form rejected, costing 43 of 895
# entities — which then read `ungrounded` and get re-proposed as duplicates:
#   #### slug [concept·—]                        (status is an em-dash, not \w)
#   #### slug [concept·candidate] · score 7/9    (trailing scoring metadata)
CATALOG_HEAD = re.compile(r"^####\s+(\S+)\s+\[([a-z_-]+)[·|]([^\]]+)\]\s*(?:·.*)?$")
CATALOG_PATH = re.compile(r"^path:\s*(\S+)\s*$")
AKA = re.compile(r"\baka:\s*([^·|\n]+)")


@dataclass
class Entity:
    slug: str
    etype: str
    status: str
    claim: str = ""
    path: str = ""
    aliases: list[str] = field(default_factory=list)


def parse_catalog(text: str) -> tuple[dict[str, Entity], dict[str, str]]:
    """Parse docs/knowledge-index.md into {slug: Entity} and {alias slug: slug}."""
    entities: dict[str, Entity] = {}
    aliases: dict[str, str] = {}
    cur: Entity | None = None
    claim_pending = False
    for line in text.splitlines():
        m = CATALOG_HEAD.match(line)
        if m:
            cur = Entity(slug=m.group(1), etype=m.group(2), status=m.group(3))
            entities[cur.slug] = cur
            claim_pending = True
            continue
        if cur is None:
            continue
        mp = CATALOG_PATH.match(line)
        if mp:
            cur.path = mp.group(1)
            cur = None
            claim_pending = False
            continue
        if claim_pending and line.strip():
            cur.claim = line.strip()
            claim_pending = False
            continue
        ma = AKA.search(line)
        if ma:
            for alias in ma.group(1).split(","):
                key = normalize(alias)
                if key:
                    cur.aliases.append(alias.strip())
                    aliases.setdefault(key, cur.slug)
    # A real slug always beats an alias that shadows it, regardless of the order
    # the two appeared in the catalog.
    for shadowed in set(aliases) & set(entities):
        del aliases[shadowed]
    return entities, aliases


PRIMITIVE_TABLE_ROW = re.compile(r"^\|\s*P(\d{1,2})\s*\|\s*\*\*([^*]+?)\*\*")


def parse_primitives(text: str) -> dict[str, str]:
    """Map 'p6' -> 'Bookkeeping' from the CLAUDE.md short-name index or P-table."""
    out: dict[str, str] = {}
    for m in PRIMITIVE_NAMED.finditer(text):
        out.setdefault(f"p{int(m.group(2))}", m.group(1))
    for line in text.splitlines():
        m = PRIMITIVE_TABLE_ROW.match(line)
        if m:
            name = re.split(r"—| - ", m.group(2))[0].strip()
            out.setdefault(f"p{int(m.group(1))}", name)
    return out


@dataclass
class Grounding:
    coverage: str
    path: str | None = None
    claim: str | None = None
    key: str | None = None  # stable identity for dedupe; None when ungrounded


def classify(
    term: str,
    entities: dict[str, Entity],
    aliases: dict[str, str],
    primitives: dict[str, str],
) -> Grounding:
    """Resolve one term against the primitive table, then the entity catalog."""
    key = normalize(term)
    pm = re.fullmatch(r"p(\d{1,2})", key) or re.search(r"-p(\d{1,2})$", key)
    if pm:
        pkey = f"p{int(pm.group(1))}"
        if pkey in primitives:
            return Grounding(
                "grounded",
                "CLAUDE.md#bstack-core-automation-primitives",
                f"{pkey.upper()} = {primitives[pkey]}",
                f"primitive:{pkey}",
            )
    slug = key if key in entities else aliases.get(key)
    if slug:
        e = entities[slug]
        return Grounding("grounded", e.path or f"{e.etype}/{e.slug}.md", e.claim, f"entity:{slug}")
    # `partial` = the term shares a distinctive segment with an entity slug. The
    # earlier rule (whole term IS a slug segment, or an 8-char substring) was
    # unreachable for realistic multi-word terms, so the tier never fired: a
    # `stability-margin` next to a `stability-budget` entity read `ungrounded` and
    # became a duplicate filing candidate.
    segs = {s for s in key.split("-") if len(s) >= PARTIAL_SEGMENT_MIN}
    if segs:
        best: tuple[int, str] | None = None
        for cand in entities:
            shared = len(segs & set(cand.split("-")))
            # Deterministic: most shared segments wins, ties broken by slug name.
            if shared and (best is None or (-shared, cand) < (-best[0], best[1])):
                best = (shared, cand)
        if best is not None:
            e = entities[best[1]]
            return Grounding("partial", e.path or f"{e.etype}/{e.slug}.md", e.claim, None)
    return Grounding("ungrounded")


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------

@dataclass
class Concept:
    term: str
    kind: str
    uses: int
    agent_introduced: bool
    defined_inline: bool
    coverage: str
    entity_path: str | None
    claim: str | None
    score: float


def score_concept(uses: int, agent_introduced: bool, defined_inline: bool,
                  kind: str, coverage: str) -> float:
    """The ranking model, in one place so dedupe recomputes rather than inherits."""
    return round(
        min(FREQ_WEIGHT * math.log1p(uses), FREQ_CAP)
        + (AGENT_INTRODUCED_BONUS if agent_introduced else 0.0)
        + (0.0 if defined_inline else UNDEFINED_BONUS)
        + KIND_WEIGHT.get(kind, 0.5)
        + COVERAGE_WEIGHT.get(coverage, 0.0),
        3,
    )


def build_inventory(
    turns: list[Turn],
    entities: dict[str, Entity],
    aliases: dict[str, str],
    primitives: dict[str, str],
    min_freq: int = 2,
    keep_code: bool = False,
    stopwords: set[str] | None = None,
    keep_terms: set[str] | None = None,
) -> list[Concept]:
    stopwords = STOPWORDS if stopwords is None else stopwords
    keep_terms = set() if keep_terms is None else keep_terms

    agent_text = scrub("\n".join(t.text for t in turns if t.role == "agent"), keep_code)
    human_text = scrub("\n".join(t.text for t in turns if t.role == "human"), keep_code)
    human_norm = {normalize(t) for t in extract_terms(human_text)}

    concepts: list[Concept] = []
    for term, kind in extract_terms(agent_text).items():
        # Classify first: grounding is what rescues a real term from the shape
        # heuristics, so it has to be known before the filter runs.
        g = classify(term, entities, aliases, primitives)
        if is_noise(term, kind, stopwords, keep_terms, grounded=g.coverage == "grounded"):
            continue
        uses = count_uses(agent_text, term, kind)
        if uses < min_freq:
            continue
        agent_introduced = normalize(term) not in human_norm
        defined_inline = definitional(agent_text, term)
        concepts.append(
            Concept(term, kind, uses, agent_introduced, defined_inline,
                    g.coverage, g.path, g.claim,
                    score_concept(uses, agent_introduced, defined_inline, kind, g.coverage))
        )
    # Deterministic order: score desc, uses desc, term asc. Never mtime or set order.
    concepts.sort(key=lambda c: (-c.score, -c.uses, c.term))
    return concepts


def dedupe(concepts: Iterable[Concept]) -> list[Concept]:
    """Collapse surface variants of one idea, summing uses and keeping the best row.

    Two terms merge when they ground to the same entity (an alias and its slug)
    or normalize to the same shape. Ungrounded terms never merge on grounding,
    since `partial` hits can point many unrelated terms at one page.
    """
    best: dict[str, Concept] = {}
    total: dict[str, int] = {}
    for c in concepts:
        key = (
            f"g::{c.entity_path}::{c.claim}"
            if (c.coverage == "grounded" and c.entity_path)
            else f"n::{normalize(c.term)}"
        )
        total[key] = total.get(key, 0) + c.uses
        prev = best.get(key)
        if prev is None or (c.score, c.term) > (prev.score, prev.term):
            best[key] = c
    out: list[Concept] = []
    for key, c in best.items():
        uses = total[key]
        # Recompute rather than inherit: a merged row's score must reflect its merged
        # use count, or it ranks against unmerged rows on a stale number.
        merged = Concept(**{
            **asdict(c), "uses": uses,
            "score": score_concept(uses, c.agent_introduced, c.defined_inline, c.kind, c.coverage),
        })
        out.append(merged)
    out.sort(key=lambda c: (-c.score, -c.uses, c.term))
    return out


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

REPITCH = (
    "No candidate concepts cleared the thresholds.\n\n"
    "Treat this as the **re-pitch** case: the slice is short or plain, so explain\n"
    "the last message again with more context and a simpler register."
)


def render_markdown(concepts: list[Concept], meta: dict) -> str:
    lines = [
        f"# Concept inventory — {meta['source']}",
        "",
        f"scope: `{meta['scope']}` · turns: {meta['turns']} "
        f"(agent {meta['agent_turns']} / human {meta['human_turns']}) · "
        f"catalog: {meta['catalog'] or 'none'}",
        "",
    ]
    if not concepts:
        lines.append(REPITCH)
        return "\n".join(lines)

    lines += [
        "| # | Term | Uses | Agent-introduced | Defined inline | Coverage | Where to read |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(concepts, 1):
        lines.append(
            f"| {i} | `{c.term}` | {c.uses} | {'yes' if c.agent_introduced else 'no'} "
            f"| {'yes' if c.defined_inline else 'NO'} | {c.coverage} | {c.entity_path or '—'} |"
        )
    grounded = [c for c in concepts if c.coverage == "grounded" and c.claim]
    if grounded:
        lines += ["", "## Grounded claims (read these before explaining)", ""]
        lines += [f"- **{c.term}** — {c.claim}" for c in grounded]
    ungrounded = [c for c in concepts if c.coverage == "ungrounded"]
    if ungrounded:
        lines += [
            "",
            "## Ungrounded — Bookkeeping (P6) candidates (score before filing)",
            "",
            "No entity page. Most are English hyphenation, not concepts — run these",
            "through the P6 gate (>= 5/9) and file only what clears it.",
            "",
        ]
        lines += [f"- `{c.term}` ({c.uses} uses)" for c in ungrounded]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="what-concepts",
        description="Rank the concepts a session used and classify their knowledge-graph coverage.",
    )
    src = p.add_argument_group("source (first match wins)")
    src.add_argument("--transcript", help="explicit Claude Code transcript JSONL")
    src.add_argument("--project-dir", help="~/.claude/projects/<slug> dir; newest *.jsonl is used")
    src.add_argument("--conversation", help="a P1 Bridge docs/conversations/*.md log")
    src.add_argument("--text", help="raw text file, or - for stdin")
    src.add_argument("--cwd", default=None, help="derive the project dir from this path (default: $PWD)")

    p.add_argument("--scope", choices=("auto", "since-last-what", "session"), default="auto",
                   help="auto/since-last-what cut at the last /what invocation (default: auto)")
    p.add_argument("--include-tools", action="store_true",
                   help="also mine tool_use inputs (code the agent wrote)")
    p.add_argument("--include-sidechains", action="store_true", help="include subagent turns")
    p.add_argument("--keep-code", action="store_true", help="do not strip fenced code blocks")
    p.add_argument("--catalog", help="docs/knowledge-index.md (default: resolved)")
    p.add_argument("--claude-md", help="CLAUDE.md holding the primitive table (default: resolved)")
    p.add_argument("--stopword", action="append", default=[], metavar="TERM",
                   help="add a term to the stoplist (repeatable)")
    p.add_argument("--keep-term", action="append", default=[], metavar="TERM",
                   help="force-keep a term the stoplist would drop (repeatable)")
    p.add_argument("--top", type=int, default=12, help="max concepts to report (default: 12)")
    p.add_argument("--min-freq", type=int, default=2, help="minimum uses to qualify (default: 2)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def load_turns(args, cwd: Path) -> tuple[list[Turn], str] | None:
    """Resolve the session source into turns, or None when nothing is readable."""
    if args.text:
        if args.text == "-":
            return [Turn("agent", sys.stdin.read())], "stdin"
        p = Path(args.text).expanduser()
        if not p.is_file():
            print(f"no such text file: {p}", file=sys.stderr)
            return None
        return [Turn("agent", p.read_text(encoding="utf-8", errors="replace"))], str(p)
    if args.conversation:
        p = Path(args.conversation).expanduser()
        if not p.is_file():
            print(f"no such conversation log: {p}", file=sys.stderr)
            return None
        return load_conversation(p), str(p)
    tp = resolve_transcript(args.transcript, args.project_dir, cwd)
    if tp is None:
        print(
            "no transcript found — pass --transcript, --project-dir, --conversation, or --text",
            file=sys.stderr,
        )
        return None
    return load_transcript(tp, args.include_tools, args.include_sidechains), str(tp)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.top < 1 or args.min_freq < 1:
        print("--top and --min-freq must be >= 1", file=sys.stderr)
        return EXIT_USAGE

    cwd = Path(args.cwd).expanduser() if args.cwd else Path.cwd()
    loaded = load_turns(args, cwd)
    if loaded is None:
        return EXIT_NO_SOURCE
    turns, source = loaded

    sliced, effective_scope = slice_scope(turns, args.scope)

    catalog_path = resolve_catalog(args.catalog, cwd)
    entities: dict[str, Entity] = {}
    alias_map: dict[str, str] = {}
    if catalog_path is not None:
        entities, alias_map = parse_catalog(
            catalog_path.read_text(encoding="utf-8", errors="replace")
        )
    claude_md = resolve_claude_md(args.claude_md, cwd)
    primitives = (
        parse_primitives(claude_md.read_text(encoding="utf-8", errors="replace"))
        if claude_md is not None
        else {}
    )

    concepts = dedupe(
        build_inventory(
            sliced, entities, alias_map, primitives,
            min_freq=args.min_freq,
            keep_code=args.keep_code,
            stopwords=STOPWORDS | {s.lower() for s in args.stopword},
            keep_terms={k.lower() for k in args.keep_term},
        )
    )[: args.top]

    meta = {
        "source": source,
        "scope": effective_scope,
        "turns": len(sliced),
        "agent_turns": sum(1 for t in sliced if t.role == "agent"),
        "human_turns": sum(1 for t in sliced if t.role == "human"),
        "catalog": str(catalog_path) if catalog_path else None,
        "entities_indexed": len(entities),
        "version": __version__,
    }

    if args.json:
        print(json.dumps({"meta": meta, "concepts": [asdict(c) for c in concepts]}, indent=2))
    else:
        print(render_markdown(concepts, meta))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
