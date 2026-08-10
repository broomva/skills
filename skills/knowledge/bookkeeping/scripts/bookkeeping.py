#!/usr/bin/env python3
"""
bookkeeping.py — Broomva knowledge engine (bstack P6)
7-stage pipeline: Ingest → Score → Scatter → Resolve → Promote → Synthesize → Lint

Usage: python3 scripts/bookkeeping.py <command> [options]

Commands:
  run          Full 7-stage pipeline
  ingest       Normalize a single file to internal representation
  score        Score all items in a raw extract file
  promote      Promote pending items (score ≥5) to entity pages
  synthesize   Detect entity clusters, flag synthesis candidates
  lint         Validate entity pages
  status       Print knowledge graph stats
  query        Find and display an entity page
"""

from __future__ import annotations  # PEP 563: lazy annotation evaluation (Py3.9 compat)

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Ensure scripts/ is importable when bookkeeping.py is run as a script
# (so `from render import …` resolves to scripts/render.py).
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from render import render_markdown_to_html  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────

# Knowledge-graph paths resolve repo-native + config-driven, defaulting to
# today's behavior so the personal ~/broomva graph is byte-for-byte unchanged.
# Precedence (highest first):
#   1. Explicit config — a TOP-LEVEL `knowledge:` block in the nearest
#      .control/policy.yaml (found by walking up from CWD). Keys: root,
#      entities_dir, catalog_path — each root-relative unless absolute. A
#      non-empty block anchors the root at the repo owning that policy file,
#      letting a consumer repo (e.g. SRI → docs/research) opt in with no env
#      vars. Distinct from the nested `plants.knowledge` control-plant block —
#      only the top-level `knowledge:` key is read here.
#   2. Env override — KG_ROOT / KG_ENTITIES_DIR / KG_CATALOG. Legacy
#      BROOMVA_ROOT is still honored for root (haystack benchmark harness with
#      fixtures under /tmp/kg-bench-N{scale}/, and CI runners with other paths).
#   3. Default — ~/broomva + research/entities + docs/knowledge-index.md.
# Backward-compat invariant: with no top-level `knowledge:` block AND no KG_*
# env, the result is exactly the pre-config paths.


def _find_policy_file(start):
    """Nearest-ancestor .control/policy.yaml walking up from `start` (inclusive)."""
    start = Path(start).resolve()
    for d in (start, *start.parents):
        cand = d / ".control" / "policy.yaml"
        if cand.is_file():
            return cand
    return None


def _read_knowledge_block(policy):
    """Top-level `knowledge:` dict from policy.yaml, or {} if absent/unreadable.

    PyYAML is a soft dependency — absent it, returns {} (default resolution).
    A missing file, malformed YAML, non-dict root, or non-dict `knowledge:`
    all degrade to {}. Only the TOP-LEVEL `knowledge:` key is read — a nested
    `plants.knowledge` control-plant block is deliberately ignored.
    """
    if policy is None:
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(policy.read_text()) or {}
    except Exception:
        return {}
    kn = data.get("knowledge") if isinstance(data, dict) else None
    return kn if isinstance(kn, dict) else {}


def _abs_or_rel(value, base):
    """Expand `value`; return as-is if absolute, else joined under `base`."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p)


def _resolve_knowledge_paths(start_dir=None, env=None):
    """Resolve (root, entities_dir, catalog_path). See precedence comment above.

    Pure/testable: `start_dir` defaults to CWD, `env` to os.environ.
    """
    env = os.environ if env is None else env
    start_dir = Path.cwd() if start_dir is None else Path(start_dir)

    # (3) default root, honoring legacy BROOMVA_ROOT
    root = Path(env.get("BROOMVA_ROOT") or (Path.home() / "broomva")).expanduser()
    entities_dir = None
    catalog_path = None

    # (2) KG_* env overrides (per-key)
    if env.get("KG_ROOT"):
        root = Path(env["KG_ROOT"]).expanduser()
    if env.get("KG_ENTITIES_DIR"):
        entities_dir = Path(env["KG_ENTITIES_DIR"]).expanduser()
    if env.get("KG_CATALOG"):
        catalog_path = Path(env["KG_CATALOG"]).expanduser()

    # (1) top-level `knowledge:` block wins (per-key), anchoring root at the repo.
    #     KG_NO_POLICY=1 skips this layer entirely — the escape hatch that pins
    #     the graph via KG_* env with NO policy override (the bench harness sets
    #     it so its child loader reads exactly the supplied catalog, even when
    #     the child CWD walks up into some configured repo).
    policy = None if env.get("KG_NO_POLICY") else _find_policy_file(start_dir)
    kn = _read_knowledge_block(policy)
    if kn and policy is not None:  # non-empty kn implies policy was found
        repo_root = policy.parent.parent  # .control/policy.yaml → repo root
        # Accept only string path values. A non-str value (YAML coerces
        # `entities_dir: yes` → bool, a bare date → date, `123` → int, a list),
        # or an unrecognized key, is ignored with a warning — so a mis-authored
        # policy DEGRADES to the default rather than crashing every command at
        # import time (resolution runs at module load). Honors the
        # _read_knowledge_block "degrade to default" contract for bad values too.
        for key in kn:
            if key not in ("root", "entities_dir", "catalog_path"):
                print(f"[kg] ignoring unrecognized knowledge.{key} in {policy}",
                      file=sys.stderr)

        def _cfg(key):
            v = kn.get(key)
            if v is None:
                return None
            if not isinstance(v, str):
                print(f"[kg] knowledge.{key} must be a string path (got "
                      f"{type(v).__name__}) in {policy}; ignoring", file=sys.stderr)
                return None
            return v or None  # empty string → treat as unset

        kroot, kent, kcat = _cfg("root"), _cfg("entities_dir"), _cfg("catalog_path")
        # Only relocate when a recognized path key is actually set — a block with
        # only unknown/typo'd keys must NOT silently hijack root off the env.
        if kroot or kent or kcat:
            root = _abs_or_rel(kroot, repo_root) if kroot else repo_root
            if kent:
                entities_dir = _abs_or_rel(kent, root)
            if kcat:
                catalog_path = _abs_or_rel(kcat, root)

    # derive any unset path from the resolved root (today's layout)
    if entities_dir is None:
        entities_dir = root / "research" / "entities"
    if catalog_path is None:
        catalog_path = root / "docs" / "knowledge-index.md"
    return root, entities_dir, catalog_path


BROOMVA_ROOT, ENTITIES_DIR, _RESOLVED_CATALOG_PATH = _resolve_knowledge_paths()
# NOTES_DIR tracks the entity tree's parent (research/ by default, or
# docs/research/ when a consumer relocates entities via the knowledge: block).
NOTES_DIR = ENTITIES_DIR.parent / "notes"


def _display_path(p):
    """Render `p` relative to BROOMVA_ROOT when contained, else absolute — so a
    configured path OUTSIDE the root (an absolute knowledge.entities_dir /
    catalog_path, or KG_ENTITIES_DIR / KG_CATALOG) never crashes output
    formatting on `.relative_to`."""
    try:
        return p.relative_to(BROOMVA_ROOT)
    except ValueError:
        return p
CONFIG_DIR = Path.home() / ".config" / "bookkeeping"
RUN_LOG = CONFIG_DIR / "run-log.jsonl"
STATUS_CACHE = CONFIG_DIR / "status.json"
# Skill-owned assets (templates, fixtures) ship WITH the script — anchor them
# on the script's own location, not BROOMVA_ROOT. BROOMVA_ROOT is the *data*
# root (research/entities, docs/knowledge-index.md); it can point at an isolated
# worktree whose gitignored skills/ tree is empty. Resolving assets relative to
# __file__ keeps `bench`/templates working under any BROOMVA_ROOT override.
_SCRIPT_SKILL_DIR = _SCRIPTS_DIR.parent  # …/skills/bookkeeping
_FALLBACK_SKILL_DIR = BROOMVA_ROOT / "skills" / "bookkeeping"


def _skill_asset_dir(name: str) -> Path:
    """Resolve a skill asset subdir (`templates`, `fixtures`) per-asset.

    Each asset is checked INDEPENDENTLY: prefer the script-relative dir if it
    actually contains that subdir, else fall back to the BROOMVA_ROOT-derived
    one. Checking only `templates/` (the old behaviour) mis-resolved `fixtures/`
    whenever a layout shipped one subdir but not the other.
    """
    script_candidate = _SCRIPT_SKILL_DIR / name
    if script_candidate.exists():
        return script_candidate
    return _FALLBACK_SKILL_DIR / name


# SKILL_DIR retained for callers that join their own subpath; defaults to the
# script-relative dir (where the asset subdirs normally live).
SKILL_DIR = _SCRIPT_SKILL_DIR
_TEMPLATES_DIR = _skill_asset_dir("templates")
_FIXTURES_DIR = _skill_asset_dir("fixtures")
ENTITY_TEMPLATE = _TEMPLATES_DIR / "entity-page.md"
RAW_TEMPLATE = _TEMPLATES_DIR / "raw-extract.md"

PROMOTE_THRESHOLD = 5
DISCARD_THRESHOLD = 2
IMMEDIATE_PROMOTE_THRESHOLD = 7

# Max H1/H2 sections a markdown file may carry before it is treated as a
# long-form document rather than a per-section raw extract (BRO-1983).
_MAX_MARKDOWN_SECTION_ITEMS = 8
LLM_JUDGE_AMBIGUOUS_LOW = 3
LLM_JUDGE_AMBIGUOUS_HIGH = 6

ENTITY_TYPES = [
    "concept",
    "pattern",
    "tool",
    "person",
    "project",
    "discovery",
    "question",
    "framework-refinement",  # present on disk; was missing from the list (drift fix)
    "industry-pattern",      # present on disk; was missing from the list (drift fix)
    "persona",               # P12/hyperpersonalization: user-identity substrate
                             # (Compiled Truth + Timeline body schema; see
                             # docs/specs/2026-05-28-persona-substrate-architecture.html)
    "org",                   # companies/institutions as first-class KG nodes
                             # (promoted 2026-06-12, BRO-1496 — rule-of-three met:
                             # Talent Hub, TeamStation, GOES + multi-contact orgs
                             # from the CRM deep-enrichment pipeline)
]

# Life OS keywords for relevance scoring
LIFE_OS_TERMS = [
    "arcan", "lago", "autonomic", "haima", "anima", "nous", "praxis",
    "vigil", "spaces", "bstack", "egri", "symphony", "autoany",
    "life os", "agent os", "aios", "broomva", "noesis", "opsis",
    "relay", "hive", "haima", "mission-control", "control-metalayer",
    "x402", "spacetimedb", "soul file", "memory", "promotion gate",
    "hysteresis", "bi-temporal", "bitemporal", "event sourcing",
    "knowledge graph", "entity page", "wikilink",
]

# Technical terms that increase novelty when present
TECH_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "not", "this",
    "that", "these", "those", "it", "its", "we", "you", "he", "she",
    "they", "their", "our", "your", "my", "i", "me", "us", "him", "her",
}

# Optional LLM dependency (legacy Gemini judge)
try:
    import google.generativeai as genai  # type: ignore
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

# Optional LLM dependency (authored-agents Anthropic judge — BRO-1015)
#
# Loads the three blessed scorer agents from
# ~/broomva/core/life/agents/bookkeeping-{novelty,specificity,relevance}.md
# and calls them sequentially through the Anthropic API. Each agent
# scores ONE dimension; we aggregate to the existing 0..=9 total. This
# is the architecturally-aligned path: the agent prompts live in
# version-controlled .md files (Layer 3 data per the authored-agents
# spec), not embedded as Python string literals.
try:
    from anthropic import Anthropic  # type: ignore
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

try:
    import yaml  # type: ignore
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# Resolves to ~/broomva/core/life/agents/. Each blessed bookkeeping
# scorer is loaded from this directory at runtime.
AUTHORED_AGENTS_DIR = BROOMVA_ROOT / "core" / "life" / "agents"


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class RawItem:
    """A normalized knowledge item extracted from a source file."""
    item_id: str
    source_id: str
    source_type: str  # moltbook, x, web, conversation, research
    content: str
    quote: str
    author: str
    timestamp: str
    metadata: dict = field(default_factory=dict)


@dataclass
class LintError:
    """A validation error found in an entity page."""
    file_path: str
    field: str
    message: str
    severity: str = "error"  # error | warning


@dataclass
class ScoredItem:
    """A RawItem with Nous gate scores attached."""
    item: RawItem
    novelty: int       # 0-3
    specificity: int   # 0-3
    relevance: int     # 0-3
    total: int
    promote: bool
    candidate_entities: list[str]
    scoring_method: str  # "heuristic" or "llm_judge"
    reasoning: dict = field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    """Return current UTC timestamp as ISO8601 string."""
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:80]


def wikilink_slug(target: str) -> str:
    """Resolve a wikilink target to the candidate entity slug.

    A wikilink may carry a display alias (``[[slug|Text]]``), a heading anchor
    (``[[slug#h]]``), and/or a **type qualifier** (``[[concept/slug]]``). Entity
    stems never contain ``/``, so the slug is always the final path segment.
    Stripping the qualifier before slugifying is the fix for the catalog/lint
    counting type-qualified links as dangling (BRO-1976): ``slugify`` alone drops
    the ``/`` and yields ``conceptslug`` — a phantom that never resolves.
    """
    core = target.split("|", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1]
    return slugify(core)


def ensure_dirs() -> None:
    """Create required directories if they don't exist."""
    for d in [ENTITIES_DIR, NOTES_DIR, CONFIG_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    for et in ENTITY_TYPES:
        (ENTITIES_DIR / et).mkdir(parents=True, exist_ok=True)


def existing_entity_slugs() -> list[str]:
    """Return all entity slugs currently in the entities directory."""
    slugs = []
    for et in ENTITY_TYPES:
        type_dir = ENTITIES_DIR / et
        if type_dir.exists():
            for p in type_dir.glob("*.md"):
                slugs.append(p.stem)
    return slugs


def existing_entity_slug_types() -> "dict[str, set[str]]":
    """Map each existing entity slug to the set of type dirs it appears in.

    Used by `resolve_slug` so a low-confidence fuzzy match cannot attach a
    candidate to an entity of a DIFFERENT type (BRO-1983). A slug may live in
    more than one type dir (e.g. person/x and pattern/x), hence a set.
    """
    out: "dict[str, set[str]]" = {}
    for et in ENTITY_TYPES:
        type_dir = ENTITIES_DIR / et
        if type_dir.exists():
            for p in type_dir.glob("*.md"):
                out.setdefault(p.stem, set()).add(et)
    return out


def log_run(entry: dict) -> None:
    """Append a run log entry to the JSONL run log."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def update_status_cache(stats: dict) -> None:
    """Write the current stats snapshot to the status cache."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_CACHE.write_text(json.dumps({**stats, "updated_at": now_iso()}, indent=2))


# ── Stage 1: Ingest ───────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from a markdown file.

    Returns (frontmatter_dict, body_text). If yaml is unavailable,
    returns ({}, full_text).
    """
    if not _YAML_AVAILABLE:
        return {}, text

    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        fm = {}
    body = text[m.end():]
    return fm, body


def parse_html_frontmatter(text: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from an HTML file's leading comment.

    Expects a comment of shape `<!--\\n---\\n…\\n---\\n-->` somewhere in
    the first 4 KB of the document. Returns (frontmatter_dict, body_text);
    body_text is the original text with the matched frontmatter comment
    removed. Returns ({}, original_text) if frontmatter is absent,
    malformed, or not a dict, or if yaml is unavailable.
    """
    if not _YAML_AVAILABLE or not text:
        return {}, text

    head = text[:4096]
    m = re.search(r"<!--\s*\n---\s*\n(.*?)\n---\s*\n-->", head, re.DOTALL)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:
        return {}, text
    if not isinstance(fm, dict):
        return {}, text
    body = text[: m.start()] + text[m.end():]
    return fm, body


def read_frontmatter(path: Path) -> tuple[dict, str]:
    """
    Read frontmatter from a file, dispatching by extension.

    .md / .markdown → parse_frontmatter
    .html           → parse_html_frontmatter
    other           → ValueError

    Raises FileNotFoundError if the path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))
    suffix = path.suffix.lower()
    text = path.read_text(errors="replace")
    if suffix in (".md", ".markdown"):
        return parse_frontmatter(text)
    if suffix == ".html":
        return parse_html_frontmatter(text)
    raise ValueError(f"Unsupported extension for frontmatter: {path.suffix}")


def extract_wikilinks_md(text: str) -> list[tuple[str, str]]:
    """
    Extract wikilinks from Markdown text.

    Returns list of (target_slug, edge_type) tuples. For Markdown,
    edge_type is always "references" (no edge typing in MD wikilink syntax).

    HTML comment blocks are stripped before extraction to avoid false
    positives from commented-out examples.
    """
    body_no_comments = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return [
        (link.split("|")[0], "references")
        for link in re.findall(r"\[\[([^\]]+)\]\]", body_no_comments)
    ]


def extract_wikilinks_html(text: str) -> list[tuple[str, str]]:
    """
    Extract typed wikilinks from HTML text.

    Matches `<a … href="…" … data-relation="…">` anchors (attribute order
    is irrelevant) and returns (target_slug, edge_type) tuples — same
    shape as extract_wikilinks_md.

    External hrefs (http://, https://, mailto:, #fragment) and untyped
    anchors (missing data-relation) are skipped. Slug derivation strips
    leading ./ or ../ segments and the .md/.html extension, so
    `../concept/foo.md` becomes `concept/foo`.
    """
    results: list[tuple[str, str]] = []
    for tag in re.findall(r"<a\b([^>]*?)>", text, flags=re.IGNORECASE):
        href_m = re.search(r"""\bhref\s*=\s*(["'])([^"']*)\1""", tag, flags=re.IGNORECASE)
        rel_m = re.search(r"""\bdata-relation\s*=\s*(["'])([^"']*)\1""", tag, flags=re.IGNORECASE)
        if not href_m or not rel_m:
            continue
        href = href_m.group(2)
        if re.match(r"^(?:https?:|mailto:|#)", href, flags=re.IGNORECASE):
            continue
        # Strip leading ./ or ../ segments, then the .md/.html extension.
        slug = re.sub(r"^(?:\.{1,2}/)+", "", href)
        slug = re.sub(r"\.(?:md|html)$", "", slug, flags=re.IGNORECASE)
        results.append((slug, rel_m.group(2)))
    return results


def ingest_file(source_path: Path, verbose: bool = False) -> list[RawItem]:
    """
    Normalize a raw extract file to a list of RawItem objects.

    Supports:
    - Markdown files with YAML frontmatter (## Item blocks)
    - Plain text / log files (one item per non-empty paragraph)
    - JSONL files (each line is a JSON object)
    """
    if not source_path.exists():
        print(f"[ingest] ERROR: {source_path} not found", file=sys.stderr)
        return []

    text = source_path.read_text(errors="replace")
    source_id = source_path.stem
    source_type = _detect_source_type(source_path, text)
    items: list[RawItem] = []

    if source_path.suffix == ".jsonl":
        items = _ingest_jsonl(text, source_id, source_type)
    elif source_path.suffix in (".md", ".markdown"):
        items = _ingest_markdown(text, source_id, source_type)
    else:
        items = _ingest_plaintext(text, source_id, source_type)

    if verbose:
        print(f"[ingest] {source_path.name} → {len(items)} items (type={source_type})")
    return items


def _detect_source_type(path: Path, text: str) -> str:
    """Infer source type from filename or content."""
    name = path.stem.lower()
    if "moltbook" in name or "social" in name:
        return "moltbook"
    if "-x-" in name or name.startswith("x-"):
        return "x"
    if "conversation" in name or "session" in name:
        return "conversation"
    if "research" in name or "notes" in name:
        return "research"
    if "web" in name:
        return "web"
    return "research"


def _make_item(
    source_id: str,
    source_type: str,
    content: str,
    quote: str = "",
    author: str = "",
    timestamp: str = "",
    metadata: dict | None = None,
) -> RawItem:
    return RawItem(
        item_id=str(uuid.uuid4())[:8],
        source_id=source_id,
        source_type=source_type,
        content=content.strip(),
        quote=quote.strip(),
        author=author,
        timestamp=timestamp or now_iso(),
        metadata=metadata or {},
    )


def _ingest_jsonl(text: str, source_id: str, source_type: str) -> list[RawItem]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        # ── Loop-log format ────────────────────────────────────────────────────
        # Each line is a 30-min engagement run with moltbook_comments[], x_posts[],
        # and a notes string. Extract each comment topic and x post as a separate item.
        if "moltbook_comments" in obj or "x_posts" in obj:
            run_id = obj.get("run_id", "")
            ts = obj.get("timestamp", "")
            karma = obj.get("karma", "")

            for cmt in (obj.get("moltbook_comments") or []) if isinstance(obj.get("moltbook_comments"), list) else []:
                topic = cmt.get("topic") or cmt.get("angle") or ""
                if not topic or len(topic) < 20:
                    continue
                post_id = cmt.get("post_id", "")
                angle = cmt.get("angle", "")
                content = f"{topic}\n\nAngle: {angle}" if angle and angle != topic else topic
                items.append(_make_item(
                    source_id=source_id,
                    source_type="moltbook",
                    content=content,
                    quote=topic[:200],
                    author="broomva",
                    timestamp=ts,
                    metadata={"run_id": run_id, "post_id": post_id, "karma": karma},
                ))

            for xp in (obj.get("x_posts") or []) if isinstance(obj.get("x_posts"), list) else []:
                note = xp.get("note", "")
                if not note or len(note) < 20:
                    continue
                items.append(_make_item(
                    source_id=source_id,
                    source_type="x",
                    content=note,
                    quote=note[:200],
                    author="broomva_tech",
                    timestamp=ts,
                    metadata={"run_id": run_id, "tweet_id": xp.get("id", ""), "type": xp.get("type", ""), "karma": karma},
                ))

            # The run-level notes field as a summary item
            notes = obj.get("notes", "")
            if notes and len(notes) > 30:
                items.append(_make_item(
                    source_id=source_id,
                    source_type="moltbook",
                    content=notes,
                    quote=notes[:200],
                    author="broomva",
                    timestamp=ts,
                    metadata={"run_id": run_id, "karma": karma, "item_type": "run-summary"},
                ))
            continue

        # ── Generic JSONL format ───────────────────────────────────────────────
        content = obj.get("content") or obj.get("text") or obj.get("body") or ""
        if not content or len(content) < 20:
            continue
        items.append(_make_item(
            source_id=source_id,
            source_type=source_type,
            content=content,
            quote=obj.get("quote", ""),
            author=obj.get("author", ""),
            timestamp=obj.get("timestamp", ""),
            metadata={k: v for k, v in obj.items() if k not in ("content", "quote", "author", "timestamp")},
        ))
    return items


def _ingest_markdown(text: str, source_id: str, source_type: str) -> list[RawItem]:
    """
    Parse markdown files into RawItems.

    Supports two formats:
    1. social-insights-raw.md format — ## Item N sections with blockquote content,
       **Score** lines, and **Our angle** / **→ Suggested destination** metadata.
    2. synthesis / general notes format — ## section headers as item boundaries,
       with paragraph content below each header.
    3. Fallback — split by paragraph (≥40 chars).
    """
    fm, body = parse_frontmatter(text)
    items = []

    # ── Format 1: ## Item N blocks (social-insights-raw.md) ─────────────────
    # Pattern: ## Item 3 — @author (Platform `post_id`)
    item_pattern = re.compile(r"^## Item \d+", re.MULTILINE)
    item_blocks = item_pattern.split(body)

    if len(item_blocks) > 1:
        for block in item_blocks[1:]:
            lines = block.splitlines()

            # Extract header line (first non-empty after split)
            header = lines[0].strip() if lines else ""
            # Parse author from "— @author (Platform ...)"
            author_match = re.search(r"@(\w[\w\d_]+)", header)
            author = f"@{author_match.group(1)}" if author_match else ""
            post_id_match = re.search(r"`([a-f0-9\-]{6,})`", header)
            post_id = post_id_match.group(1) if post_id_match else ""

            # Extract score from "**Score**: 6/9 — novelty:3 specificity:2 relevance:1"
            score_total = 0
            novelty = specificity = relevance = 0
            for line in lines:
                sm = re.search(r"\*\*Score\*\*[:\s]+(\d+)/9.*?novelty[:\s]*(\d).*?specificity[:\s]*(\d).*?relevance[:\s]*(\d)", line)
                if sm:
                    score_total = int(sm.group(1))
                    novelty, specificity, relevance = int(sm.group(2)), int(sm.group(3)), int(sm.group(4))
                    break

            # Collect blockquote lines as the quote (the external voice)
            quote_lines = []
            in_quote = False
            for line in lines:
                if line.startswith("> "):
                    quote_lines.append(line[2:].strip())
                    in_quote = True
                elif in_quote and line.strip() == ">":
                    quote_lines.append("")  # blank blockquote line
                elif in_quote and not line.startswith(">"):
                    in_quote = False

            quote = "\n".join(quote_lines).strip()

            # Collect "Our angle" content — lines after **Our angle** header
            # (this is the broomva comment text, which is the main content)
            angle_lines = []
            in_angle = False
            for line in lines:
                if re.match(r"\*\*Our angle\*\*", line):
                    in_angle = True
                    # Remainder of this line after the header
                    rest = re.sub(r"\*\*Our angle\*\*[:\s]*", "", line).strip()
                    if rest:
                        angle_lines.append(rest)
                    continue
                if in_angle:
                    if line.startswith("**→") or line.startswith("---"):
                        break
                    if line.startswith("> "):
                        angle_lines.append(line[2:].strip())
                    elif line.strip():
                        angle_lines.append(line.strip())

            angle_text = "\n".join(angle_lines).strip()

            # Main content = our angle (what we said) if present; else the quote
            content = angle_text if len(angle_text) >= 40 else quote
            if not content or len(content) < 20:
                continue

            items.append(_make_item(
                source_id=source_id,
                source_type=source_type,
                content=content,
                quote=quote,
                author=author,
                metadata={
                    **dict(fm),
                    "post_id": post_id,
                    "score_total": score_total,
                    "novelty": novelty,
                    "specificity": specificity,
                    "relevance": relevance,
                    "pre_scored": True,  # already scored by extraction loop
                },
            ))
        return items

    # ── Format 2: ## Section headers as item boundaries (synthesis notes) ───
    #
    # Two hardenings (BRO-1983):
    #   1. H1/H2 only. The old `^#{1,3} ` also split on H3, so sub-structure
    #      *inside* a section became its own "entity". H3+ now stays in the
    #      body of its parent section, where it belongs.
    #   2. Section-count cap. A long-form research document with N headings is
    #      NOT an N-item extract — treating it as one is exactly how one doc
    #      became dozens of entity pages. Past the cap the format does not
    #      apply and the document yields nothing here, rather than a swarm of
    #      fragments (Format 3's paragraph split would be worse still, so the
    #      over-cap case returns explicitly).
    section_pattern = re.compile(r"^#{1,2} .+", re.MULTILINE)
    sections = section_pattern.split(body)
    headers = section_pattern.findall(body)

    if len(sections) > 2:  # more than just a preamble
        if len(headers) > _MAX_MARKDOWN_SECTION_ITEMS:
            print(
                f"[ingest] {source_id}: {len(headers)} H1/H2 sections exceeds the "
                f"{_MAX_MARKDOWN_SECTION_ITEMS}-section cap — treating as a long-form "
                f"document, not a per-section extract (0 items)",
                file=sys.stderr,
            )
            return []
        for header, section_body in zip(headers, sections[1:]):
            section_body = section_body.strip()
            if not section_body or len(section_body) < 60:
                continue
            # Skip table-of-contents-only sections
            if section_body.count("\n") < 2 and not re.search(r"[.!?]", section_body):
                continue
            content = f"{header.lstrip('#').strip()}\n\n{section_body}"
            items.append(_make_item(
                source_id=source_id,
                source_type=source_type,
                content=content.strip(),
                metadata=dict(fm),
            ))
        if items:
            return items

    # ── Format 3: Paragraph fallback ────────────────────────────────────────
    paragraphs = re.split(r"\n{2,}", body)
    for para in paragraphs:
        para = para.strip()
        if not para or para.startswith("#") or para.startswith("---"):
            continue
        if len(para) < 40:
            continue
        items.append(_make_item(
            source_id=source_id,
            source_type=source_type,
            content=para,
            metadata=dict(fm),
        ))
    return items


def _ingest_plaintext(text: str, source_id: str, source_type: str) -> list[RawItem]:
    items = []
    paragraphs = re.split(r"\n{2,}", text)
    for para in paragraphs:
        para = para.strip()
        if len(para) < 40:
            continue
        items.append(_make_item(
            source_id=source_id,
            source_type=source_type,
            content=para,
        ))
    return items


def discover_raw_extracts() -> list[Path]:
    """Find all raw extract files in NOTES_DIR matching the naming convention."""
    if not NOTES_DIR.exists():
        return []
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-.+-raw\.(md|txt|jsonl)$")
    return sorted(
        p for p in NOTES_DIR.iterdir()
        if p.is_file() and pattern.match(p.name)
    )


# ── Stage 2: Score ────────────────────────────────────────────────────────────

def _count_technical_terms(text: str) -> int:
    """Count unique technical words not in common stop words."""
    words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_-]{3,}\b", text.lower())
    unique = {w for w in words if w not in TECH_STOP_WORDS}
    return len(unique)


def heuristic_score(item: RawItem) -> tuple[int, int, int]:
    """
    Fast-path Nous gate scoring.

    Returns (novelty, specificity, relevance) each in range [0, 3].
    """
    text = item.content.lower()

    # Novelty: fewer known Life OS hits → more novel
    known_hits = sum(1 for term in LIFE_OS_TERMS if term in text)
    tech_terms = _count_technical_terms(item.content)
    if known_hits >= 4:
        novelty = 0
    elif known_hits >= 1:
        novelty = 1
    elif tech_terms < 5:
        novelty = 2
    else:
        novelty = 3

    # Specificity: length + structural markers
    has_numbers = any(c.isdigit() for c in item.content)
    has_code = "`" in item.content or "```" in item.content
    has_quote = ('"' in item.content or "'" in item.content) and len(item.content) > 100
    has_cause = any(
        w in text
        for w in ["because", "therefore", "means", "in practice", "as a result", "which causes"]
    )
    length_bonus = 1 if len(item.content) > 200 else 0
    extra_length = 1 if len(item.content) > 500 else 0
    specificity = min(3, sum([has_numbers, has_code, has_quote, has_cause]) + length_bonus + extra_length)

    # Relevance: Life OS keyword hits
    relevance = min(3, known_hits)

    return novelty, specificity, relevance


# ── Entity-slug shape gate (BRO-1983) ─────────────────────────────────────────
#
# The Title-Case-run regex below grabs ANY capitalized 2-6 word run out of a
# section body. Left ungated it mints sentence fragments as permanent entity
# pages — `pattern/the-goodhart`, `pattern/the-singularity-is-not`,
# `project/stop-comparing`, `project/agents-without-disclosing`,
# `tool/all-image-file-directories`. 182 of 810 live entity pages (22%) carried
# this shape when the defect was traced.
#
# An entity slug must be NOUN-PHRASE shaped ("event-sourcing", "promotion-gate"),
# not SENTENCE-FRAGMENT shaped (article-led, verb-led, or carrying a copula /
# negation / subordinating preposition). The gate below is deliberately strict:
# per the promoter invariant, minting a junk page is strictly worse than not
# promoting, so a candidate that cannot be shown to be entity-shaped is dropped.

# Determiners / articles / conjunctions / pronouns that cannot legitimately LEAD
# an entity name. ("the-goodhart", "all-image-file-directories", "our-approach")
_SLUG_LEAD_STOPWORDS = frozenset({
    "the", "a", "an", "all", "any", "each", "every", "some", "no", "none",
    "this", "that", "these", "those", "such", "both", "either", "neither",
    "our", "your", "its", "my", "their", "his", "her", "it", "we", "they",
    "you", "i", "he", "she", "us", "them", "me", "him",
    "and", "or", "but", "nor", "so", "yet", "if", "then", "than", "as",
    "because", "since", "although", "though", "while", "whereas", "unless",
    "however", "moreover", "furthermore", "meanwhile", "instead", "therefore",
    "thus", "hence", "also", "still", "now", "just", "only", "even", "very",
    "more", "most", "less", "least", "much", "many", "few", "several",
    "here", "there", "when", "where", "who", "whom", "whose", "which",
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "into",
    "over", "under", "about", "after", "before", "during", "between",
    "without", "within", "through", "across", "despite", "against", "upon",
    "first", "second", "third", "next", "last", "other", "another", "same",
})

# Imperative verbs that mark an instruction fragment, not an entity.
# ("stop-comparing", "look-at-the-data", "use-the-cli")
_SLUG_LEAD_VERBS = frozenset({
    "stop", "look", "make", "makes", "use", "uses", "see", "get", "gets",
    "let", "lets", "do", "does", "put", "take", "takes", "give", "gives",
    "go", "goes", "come", "keep", "keeps", "build", "builds", "ship",
    "ships", "add", "adds", "remove", "removes", "avoid", "avoids",
    "consider", "note", "notes", "read", "reads", "write", "writes",
    "think", "thinks", "imagine", "remember", "forget", "check", "checks",
    "try", "tries", "start", "starts", "begin", "begins", "run", "runs",
    "call", "calls", "ask", "asks", "tell", "tells", "show", "shows",
    "find", "finds", "know", "knows", "learn", "learns", "want", "wants",
    "need", "needs", "help", "helps", "watch", "listen", "follow",
    "choose", "pick", "set", "sets", "bring", "leave", "move", "turn",
    "hold", "mean", "means", "become", "happen", "apply", "ensure",
    "prefer", "treat", "reject", "accept", "assume", "expect", "explain",
    "describe", "define", "compare", "replace", "update", "fix", "solve",
})

# Copulas / auxiliaries / negations / subordinators. Their presence ANYWHERE in
# the slug proves the phrase is a clause, not a name.
# ("the-singularity-is-not", "agents-without-disclosing", "what-we-can-do")
# Tokens that mark a slug as a lifted CLAUSE rather than a name.
#
# Deliberately NARROW. An earlier version also listed copulas and negation
# ("is", "are", "was", "not", "no", "without", "has", "have", modals). Measured
# against the live graph, that rejected 50 existing entity slugs, most of them
# legitimate — this knowledge graph's convention is CLAIM-SHAPED names:
#   completion-is-an-endpoint-projection
#   correlated-verifier-is-no-verifier
#   freshness-is-the-wrong-invariant
#   gradient-is-a-vector-not-a-reprimand
#   isolation-is-a-reachability-property
#   accuracy-without-attention
# A copula is the load-bearing word in those, not a defect. Rejecting it would
# block the graph's highest-value pages from ever being (re)created.
#
# What actually separates a good claim-slug from a fragment is not the presence
# of a verb but whether the slug DANGLES — ends on a function word, leads with a
# determiner/imperative, or carries a pronoun/discourse adverb. Those are handled
# by _SLUG_LEAD_STOPWORDS, _SLUG_LEAD_VERBS, _SLUG_TRAIL_STOPWORDS and
# _SLUG_INTERIOR_REJECT. This set keeps only subordinators, which introduce a
# dependent clause and never appear in a well-formed entity name.
_SLUG_CLAUSE_TOKENS = frozenset({
    "unless", "whether", "because", "although", "though", "whereas",
    "isnt", "arent", "wasnt", "werent", "cannot", "cant", "dont", "doesnt",
    "didnt", "wont", "wouldnt", "shouldnt", "couldnt", "hasnt", "havent",
})

# Function words that cannot legitimately END an entity name (dangling clause).
_SLUG_TRAIL_STOPWORDS = frozenset({
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "into",
    "over", "under", "about", "after", "before", "during", "between",
    "and", "or", "but", "nor", "the", "a", "an", "as", "than", "then",
    "that", "this", "these", "those", "is", "are", "was", "were", "not",
    "it", "its", "we", "our", "your", "their", "his", "her", "they",
})

# Function words that betray a lifted sentence when they appear INTERIOR to a
# slug. Deliberately excludes prepositions and conjunctions ("of", "as", "by",
# "for", "in", "to", "and"), which occur in legitimate entity names.
_SLUG_INTERIOR_REJECT = frozenset({
    # pronouns / possessives
    "their", "our", "your", "its", "my", "his", "her", "them", "us", "we",
    "they", "you", "it", "he", "she", "me", "him", "i",
    # discourse adverbs
    "just", "also", "even", "very", "however", "therefore", "thus",
    "hence", "moreover", "furthermore", "meanwhile", "instead", "already",
    "actually", "really", "simply", "merely", "basically",
})
_SLUG_MIN_LEN = 3
# How many times a curated LIFE_OS_TERMS name must recur in a body before an
# incidental mention counts as the item being ABOUT that module. One mention is
# a name-drop; a page that is genuinely about Arcan says "Arcan" repeatedly.
_TERM_TOPICAL_MIN_HITS = 3
# Mentions per 1000 characters required alongside the absolute floor. 0.5 means
# roughly one mention per 2000 chars. Calibrated against the observed failure:
# a 64,969-char transcript dump name-dropping "arcan" 12 times scores 0.18 and
# is correctly rejected, while a genuinely on-topic section scores far higher.
_TERM_TOPICAL_MIN_DENSITY = 0.5
# Above this, an "item" is a dump rather than an entity and no slug heuristic is
# trustworthy on it. Generous — real sections run a few thousand chars; the
# observed failure was 64,969.
_MAX_PROMOTABLE_ITEM_CHARS = 12000

# Control characters that must never reach a written entity page. Raw extracts
# are built from session transcripts and tool output, which can carry NUL and
# other C0 bytes; git then classifies the page as BINARY, which breaks diffing,
# grep, the linter's own reader, and every editor tool. Two 71KB pages in the
# workspace graph (pattern/arcan.md, pattern/autonomic.md) were NUL-corrupt this
# way and silently regenerated on every run. Tab / LF / CR are legitimate.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_page_text(text: str) -> str:
    """Strip control characters that would make a written page binary.

    Applied at the write boundary rather than at ingest so it holds for every
    producer path, including templates and future callers.
    """
    return _CONTROL_CHAR_RE.sub("", text)
# Claim-shaped names are this graph's convention and run long:
#   gradient-is-a-vector-not-a-reprimand        (7)
#   common-mode-vs-differential-mode-drift-sensing (7)
#   server-only-guard-blocks-non-next-runtimes  (7)
# A cap of 6 rejected all three. 8 still rejects lifted sentences, which run
# longer and are caught by the lead/interior/trailing rules anyway.
_SLUG_MAX_TOKENS = 8


def is_entity_shaped_slug(slug: str) -> bool:
    """True when `slug` is noun-phrase shaped and may become an entity page.

    Rejects the sentence-fragment shapes the Title-Case-run regex produces
    (BRO-1983). Deliberately conservative: `promote_item` treats "no candidate
    passed" as a promotion-blocking signal rather than minting a junk page.
    """
    if not slug or not isinstance(slug, str):
        return False
    slug = slug.strip().strip("-")
    if len(slug) < _SLUG_MIN_LEN:
        return False
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        return False
    tokens = slug.split("-")
    if len(tokens) > _SLUG_MAX_TOKENS:
        return False
    if tokens[0] in _SLUG_LEAD_STOPWORDS or tokens[0] in _SLUG_LEAD_VERBS:
        return False
    if any(t in _SLUG_CLAUSE_TOKENS for t in tokens):
        return False
    # Function words INTERIOR to the slug also mark a sentence, but only a
    # narrow subset is safe to reject: prepositions and conjunctions appear in
    # real names ("llm-as-index-architecture", "chain-of-thought",
    # "gate-satisfiable-by-construction"), so rejecting every stopword anywhere
    # would be a false-positive machine. Pronouns, possessives and discourse
    # adverbs effectively never appear in an entity name and reliably indicate
    # a lifted sentence — e.g. "anthropic-just-dropped-their-claude-skills",
    # which the lead-position checks miss because it starts with a proper noun.
    if any(t in _SLUG_INTERIOR_REJECT for t in tokens[1:]):
        return False
    if len(tokens) > 1 and tokens[-1] in _SLUG_TRAIL_STOPWORDS:
        return False
    # Dangling gerund: a slug ending in "-ing" directly after a function word is
    # a truncated clause ("agents-without-disclosing"), whereas the same
    # preposition with a noun object is a real name ("accuracy-without-
    # attention"). The preposition is NOT the signal — the trailing participle
    # is. A gerund after a content word is fine and common here
    # ("common-mode-vs-differential-mode-drift-sensing").
    if (
        len(tokens) > 2
        and tokens[-1].endswith("ing")
        and len(tokens[-1]) > 4
        and (tokens[-2] in _SLUG_LEAD_STOPWORDS or tokens[-2] in _SLUG_TRAIL_STOPWORDS)
    ):
        return False
    # A slug that is nothing but function words carries no referent.
    if all(t in _SLUG_LEAD_STOPWORDS or t in _SLUG_TRAIL_STOPWORDS for t in tokens):
        return False
    return True


# Title-Case runs of 2-6 words. Two hardenings over the original
# `\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b`:
#   1. `(?<![-\w])` — the original `\b` fired mid-hyphenated-compound, so
#      "Game-Theoretic Foundation" yielded the orphan `theoretic-foundation`.
#   2. `{1,5}` — the `{1,3}` cap truncated long titles into fragments
#      ("The Singularity Is Not Near" → `the-singularity-is-not`). The shape
#      gate above, not an arbitrary word cap, is what rejects fragments now.
_TITLECASE_RUN_RE = re.compile(r"(?<![-\w])([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5})(?![-\w])")

# How many Title-Case runs to consider per item body. Bounded on purpose: the
# gate must REDUCE what reaches disk, never widen it.
_TITLECASE_SCAN_WINDOW = 12


def _build_entity_slug_candidates(item: RawItem) -> list[str]:
    """
    Heuristic extraction of candidate entity slugs from item content.

    Looks for known Life OS module names (a curated vocabulary, trusted) and
    capitalized multi-word phrases (untrusted — must pass `is_entity_shaped_slug`).

    Returns [] when nothing entity-shaped is found. An empty result is a
    promotion-blocking signal, NOT an invitation to invent a slug.
    """
    candidates = []
    text = item.content

    # An entity page is a concept, not a transcript. When ingest cannot find
    # section boundaries it falls back to emitting the WHOLE file as one item —
    # the 2026-05-12 prompt-patterns extract arrives as a single 64,969-char
    # blob. Nothing that large is "one entity", and every slug heuristic below
    # degrades on it: a name-drop looks topical, and any Title-Case pair
    # anywhere in 65KB looks like a name. That is how five module pages plus
    # assorted fragments got minted from one dump.
    #
    # Returning [] here is the documented promotion-blocking signal, so an
    # oversized item is skipped rather than guessed at. The raw extract is not
    # lost: it stays in research/notes/ for a human or a section-aware pass.
    if len(text) > _MAX_PROMOTABLE_ITEM_CHARS:
        return []

    # Known module names as direct candidates. LIFE_OS_TERMS is a curated
    # vocabulary — every entry is already noun-phrase shaped, so it bypasses
    # the SHAPE gate by construction. It does NOT bypass the ABOUTNESS test
    # below, and must not: shape was never the problem here.
    #
    # The original test was a bare `term in text.lower()` — a substring MENTION.
    # That is what produced the two worst pages in the graph: a prompt-patterns
    # dump that merely name-dropped "arcan" and "autonomic" was promoted as
    # pattern/arcan.md and pattern/autonomic.md, two 71KB NUL-corrupt pages that
    # regenerated on every run. It is also the origin of the duplicate-slug
    # problem in general — anima/arcan/bstack/broomva/praxis/relay/spaces/
    # symphony all exist under 2-5 different type dirs, because each run
    # re-minted them from an incidental mention and _infer_entity_type guessed
    # a different type each time.
    #
    # A mention is not aboutness. Require one of:
    #   - the term appears in the item's leading line (Format-2 ingest prepends
    #     the section heading, so that line is the item's title), or
    #   - the term recurs at least _TERM_TOPICAL_MIN_HITS times in the body.
    # Matching is word-boundary so "relay" no longer fires on "relayed".
    lowered = text.lower()
    lead_line = lowered.split("\n", 1)[0]
    for term in LIFE_OS_TERMS:
        if len(term) <= 4:
            continue
        term_re = re.compile(rf"(?<![-\w]){re.escape(term)}(?![-\w])")
        if not term_re.search(lowered):
            continue
        in_title = bool(term_re.search(lead_line))
        hits = len(term_re.findall(lowered))
        # Density, not a raw count. An absolute floor alone is trivially cleared
        # by a large document: the 2026-05-12 prompt-patterns raw extract ingests
        # as ONE 64,969-char item that name-drops "arcan" 12 times, "haima" 9,
        # "autonomic"/"anima" 4 and "spaces" 3 — so a `hits >= 3` rule minted
        # five module pages from one transcript dump, including the 71KB
        # pattern/arcan.md that regenerated on every run.
        #
        # 12 mentions across 65KB is 0.18 per 1000 chars — incidental. A page
        # genuinely about Arcan names it far more densely. Requiring BOTH an
        # absolute floor and a density floor keeps short, genuinely-topical
        # sections working while rejecting big dumps.
        per_1k = (hits * 1000.0 / len(text)) if text else 0.0
        topical = hits >= _TERM_TOPICAL_MIN_HITS and per_1k >= _TERM_TOPICAL_MIN_DENSITY
        if in_title or topical:
            candidates.append(slugify(term))

    # Capitalized phrases — last-resort path, strictly gated.
    #
    # The scan window is BOUNDED. The original took `caps_phrases[:5]` and then
    # accepted all 5 unconditionally; scanning the whole body instead would turn
    # a gate into a net-widener (more accepted candidates, hence more pages).
    # The window is larger than the old 5 only so that a real name at position 6
    # is not lost when the first five runs are all fragments.
    for phrase in _TITLECASE_RUN_RE.findall(text)[:_TITLECASE_SCAN_WINDOW]:
        slug = slugify(phrase)
        if is_entity_shaped_slug(slug):
            candidates.append(slug)

    # Deduplicate and return up to 5
    seen = set()
    result = []
    for c in candidates:
        if c and c not in seen and is_entity_shaped_slug(c):
            seen.add(c)
            result.append(c)
    return result[:5]


def score_item_heuristic(item: RawItem) -> ScoredItem:
    """
    Score a RawItem using the fast-path heuristic only.

    Returns a ScoredItem with scoring_method='heuristic'.
    """
    novelty, specificity, relevance = heuristic_score(item)
    total = novelty + specificity + relevance
    candidates = _build_entity_slug_candidates(item)
    return ScoredItem(
        item=item,
        novelty=novelty,
        specificity=specificity,
        relevance=relevance,
        total=total,
        promote=total >= PROMOTE_THRESHOLD,
        candidate_entities=candidates,
        scoring_method="heuristic",
        reasoning={
            "novelty_basis": "known_term_hits",
            "specificity_basis": "structural_markers",
            "relevance_basis": "life_os_keywords",
        },
    )


def score_item_llm(item: RawItem, existing_slugs: list[str]) -> Optional[ScoredItem]:
    """
    Score a RawItem using the LLM-as-judge (gemini-2.0-flash).

    Returns None if the API call fails or google.generativeai is unavailable.
    Falls back to heuristic score on any error.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not _GENAI_AVAILABLE or not api_key:
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        slug_context = ", ".join(existing_slugs[:40]) if existing_slugs else "none yet"
        system_prompt = (
            "You are a knowledge quality evaluator for a personal AI agent OS knowledge graph. "
            "Score extracted knowledge items on novelty (0-3), specificity (0-3), and relevance (0-3). "
            "novelty: 3=entirely new concept not in the graph, 0=well-known repeated idea. "
            "specificity: 3=concrete, measurable, cites code/numbers/names, 0=vague/generic. "
            "relevance: 3=directly about Life OS modules or agent architecture, 0=unrelated. "
            "Output ONLY valid JSON with keys: novelty, specificity, relevance, total, "
            "candidate_entities (list of entity slugs this item belongs to), reasoning (dict)."
        )
        user_prompt = (
            f"Existing entity slugs (for context): {slug_context}\n\n"
            f"Item source type: {item.source_type}\n"
            f"Item author: {item.author or 'unknown'}\n"
            f"Item content:\n{item.content[:800]}\n\n"
            "Score this item and return JSON only."
        )

        response = model.generate_content(
            f"{system_prompt}\n\n{user_prompt}",
            generation_config={"temperature": 0.1, "max_output_tokens": 512},
        )
        raw = response.text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```json?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)
        novelty = int(data.get("novelty", 0))
        specificity = int(data.get("specificity", 0))
        relevance = int(data.get("relevance", 0))
        total = novelty + specificity + relevance
        candidates = [slugify(s) for s in data.get("candidate_entities", [])][:5]

        return ScoredItem(
            item=item,
            novelty=novelty,
            specificity=specificity,
            relevance=relevance,
            total=total,
            promote=total >= PROMOTE_THRESHOLD,
            candidate_entities=candidates,
            scoring_method="llm_judge",
            reasoning=data.get("reasoning", {}),
        )
    except Exception as e:
        return None


# ── Authored-agents scorer (BRO-1015) ─────────────────────────────────────────
#
# Replaces the single-call Gemini judge with three parallel calls to the
# blessed bookkeeping scorer agents at
# ~/broomva/core/life/agents/bookkeeping-{novelty,specificity,relevance}.md.
#
# Why this matters: the agent prompts are version-controlled Layer-3 data
# (per the authored-agents architecture). When a maintainer wants to
# tune the novelty scorer, they edit `bookkeeping-novelty.md` and PR it
# — every Python pipeline run reads the updated prompt. No code change
# required in `bookkeeping.py`.
#
# The authored-agents path is preferred over Gemini when:
# - ANTHROPIC_API_KEY is set AND
# - `anthropic` Python SDK is installed AND
# - The three .md files exist at AUTHORED_AGENTS_DIR
#
# Falls back to Gemini, then heuristic-only, when those aren't met.


def _load_agent_spec(name: str) -> Optional[dict]:
    """
    Load an authored agent spec from disk and return its parsed
    frontmatter + body. Returns None if the file doesn't exist, can't
    be parsed, or `yaml` isn't available (PyYAML is an optional dep).

    The schema mirrors `ergon::parse_agent_md`: the body is the agent's
    `instructions`, the YAML frontmatter holds `model`, `max_turns`,
    `input_schema`, `output_schema`, etc.
    """
    if not _YAML_AVAILABLE:
        return None
    path = AUTHORED_AGENTS_DIR / f"{name}.md"
    if not path.exists():
        return None
    try:
        text = path.read_text()
        # Frontmatter is delimited by `---` at the top of the file.
        if not text.startswith("---\n"):
            return None
        end = text.find("\n---\n", 4)
        if end < 0:
            return None
        frontmatter = yaml.safe_load(text[4:end])
        body = text[end + 5 :].strip()
        if not isinstance(frontmatter, dict) or not body:
            return None
        return {
            "name": frontmatter.get("name", name),
            "model": frontmatter.get("model", "claude-haiku-4-5"),
            "max_turns": frontmatter.get("max_turns", 1),
            "input_schema": frontmatter.get("input_schema", {}),
            "output_schema": frontmatter.get("output_schema", {}),
            "instructions": body,
        }
    except Exception:
        return None


def _call_authored_scorer(
    spec: dict,
    item: RawItem,
    existing_slugs: list[str],
    client,
) -> Optional[dict]:
    """
    Invoke one authored bookkeeping-* scorer against the Anthropic API.

    Builds the prompt from the agent's `instructions` (loaded verbatim
    from the .md body), passes the item's text as the input matching
    the agent's `input_schema`, asks the model to return JSON matching
    `output_schema`. Validates the structure and returns the parsed
    response dict, or None on any failure (so the caller can fall back
    to the next path).
    """
    # The input shape follows each agent's declared input_schema.
    # All three scorers accept {item_text, source_type, ...}; relevance
    # additionally accepts active_projects / open_questions.
    agent_input = {
        "item_text": item.content[:2000],
        "source_type": item.source_type,
        # RawItem has no `source_url` field — the attribute access raised
        # AttributeError on every authored-agents scoring call. The URL, when
        # known, lives in `metadata`.
        "source_url": (item.metadata or {}).get("source_url", "") or "",
    }
    if spec["name"] == "bookkeeping-novelty":
        agent_input["existing_entity_slugs"] = existing_slugs[:40]
    if spec["name"] == "bookkeeping-relevance":
        # Best-effort population. Concrete active projects / open
        # questions could be threaded through from upstream; this is
        # the minimum that lets the agent score above 0.
        agent_input["active_projects"] = [
            "life-agent-os", "ergon", "lago", "arcan", "haima", "anima", "nous", "praxis",
        ]
        agent_input["open_questions"] = []

    system = spec["instructions"]
    user = (
        "Score the following item. Reply with ONLY a JSON object matching the agent's "
        "output_schema. No prose outside the JSON.\n\n"
        f"Input (matches `{spec['name']}` input_schema):\n"
        f"```json\n{json.dumps(agent_input, indent=2)}\n```\n\n"
        "Required output shape (the agent's `output_schema` — populate every required field):\n"
        f"```json\n{json.dumps(spec['output_schema'], indent=2)}\n```"
    )

    try:
        response = client.messages.create(
            model=spec["model"],
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Concatenate text blocks (Anthropic returns a list of content blocks)
        raw = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        # Strip markdown code fences if the model added them anyway.
        raw = re.sub(r"^```json?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        # Minimum required fields per agent's output_schema.
        if not isinstance(data, dict) or "score" not in data:
            return None
        score = data.get("score")
        if not isinstance(score, int) or not (0 <= score <= 3):
            return None
        return data
    except Exception:
        return None


def score_item_authored_agents(
    item: RawItem, existing_slugs: list[str]
) -> Optional[ScoredItem]:
    """
    Score a RawItem using the three blessed bookkeeping scorer agents
    (BRO-1012). Returns None if the path is unavailable (no API key, no
    SDK, missing agent files) so the caller can fall back.
    """
    if not _ANTHROPIC_AVAILABLE:
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    specs = {
        dim: _load_agent_spec(f"bookkeeping-{dim}")
        for dim in ("novelty", "specificity", "relevance")
    }
    if not all(specs.values()):
        return None

    try:
        client = Anthropic(api_key=api_key)
    except Exception:
        return None

    results = {}
    reasoning = {}
    for dim, spec in specs.items():
        out = _call_authored_scorer(spec, item, existing_slugs, client)
        if out is None:
            return None  # any-call failure → fall back to next scorer
        results[dim] = out["score"]
        # Each scorer's `reasoning` field is a single string; we
        # aggregate under the dimension key for the ScoredItem.reasoning
        # dict.
        reasoning[f"{dim}_reasoning"] = out.get("reasoning", "")
        # Capture anti-pattern self-reports if the scorer set any.
        warnings = out.get("anti_pattern_warnings") or []
        if warnings:
            reasoning[f"{dim}_anti_patterns"] = warnings

    novelty = results["novelty"]
    specificity = results["specificity"]
    relevance = results["relevance"]
    total = novelty + specificity + relevance

    # Candidate-entity extraction: novelty agent surfaces
    # `closest_existing_slug` when score < 3. Use that as the candidate
    # slug; otherwise build from content.
    candidates = []
    nov_out = results.get("novelty_full") or {}
    # _call_authored_scorer returned only the score, not the full dict.
    # We need to re-thread the closest_existing_slug if available; for
    # now build candidates from content as a fallback.
    candidates = _build_entity_slug_candidates(item)

    return ScoredItem(
        item=item,
        novelty=novelty,
        specificity=specificity,
        relevance=relevance,
        total=total,
        promote=total >= PROMOTE_THRESHOLD,
        candidate_entities=candidates,
        scoring_method="authored_agents",
        reasoning=reasoning,
    )


def score_item(item: RawItem, existing_slugs: list[str], verbose: bool = False) -> ScoredItem:
    """
    Two-pass scorer: heuristic fast-path, then LLM for ambiguous band.

    - Score ≤ DISCARD_THRESHOLD (2): discard immediately, no LLM call.
    - Score ≥ IMMEDIATE_PROMOTE_THRESHOLD (7): promote immediately, no LLM call.
    - Score 3-6: call LLM judge (authored agents preferred, Gemini fallback,
      heuristic-only last resort).
    """
    h = score_item_heuristic(item)

    if h.total <= DISCARD_THRESHOLD or h.total >= IMMEDIATE_PROMOTE_THRESHOLD:
        if verbose:
            print(
                f"  [{item.item_id}] heuristic={h.total}/9 "
                f"(n={h.novelty} s={h.specificity} r={h.relevance}) → fast-path"
            )
        return h

    # Ambiguous band: try the authored-agents path first (BRO-1015 —
    # version-controlled .md prompts at core/life/agents/), fall back to
    # the legacy single-call Gemini judge, then to heuristic-only.
    if verbose:
        print(
            f"  [{item.item_id}] heuristic={h.total}/9 → judge (authored agents first)..."
        )
    authored = score_item_authored_agents(item, existing_slugs)
    if authored is not None:
        if verbose:
            print(
                f"  [{item.item_id}] authored_agents={authored.total}/9 "
                f"(n={authored.novelty} s={authored.specificity} r={authored.relevance})"
            )
        return authored

    llm_result = score_item_llm(item, existing_slugs)
    if llm_result is not None:
        if verbose:
            print(
                f"  [{item.item_id}] llm={llm_result.total}/9 "
                f"(n={llm_result.novelty} s={llm_result.specificity} r={llm_result.relevance})"
            )
        return llm_result

    if verbose:
        print(f"  [{item.item_id}] LLM unavailable, keeping heuristic={h.total}/9")
    return h


# ── Stage 3: Scatter ──────────────────────────────────────────────────────────

def scatter(scored: ScoredItem, verbose: bool = False) -> list[str]:
    """
    Map a single scored item to one or more entity candidate slugs.

    Returns the list of candidate slugs from the scorer, augmented by
    content analysis for items that had no LLM-derived candidates.

    LLM-supplied `candidate_entities` are PREFERRED; the regex path in
    `_build_entity_slug_candidates` is last-resort and strictly gated
    (BRO-1983). Either way `resolve_candidates` re-applies the shape gate.
    """
    candidates = [c for c in scored.candidate_entities if is_entity_shaped_slug(c)]
    if not candidates:
        candidates = _build_entity_slug_candidates(scored.item)
    if verbose and candidates:
        print(f"  scatter → {candidates}")
    return candidates


# ── Stage 4: Resolve ──────────────────────────────────────────────────────────

# A 0.80 difflib cutoff let an unrelated candidate silently ATTACH to (and then
# rewrite) an existing entity — a live corruption vector, not merely noise.
# 0.92 keeps typo/plural repair ("prosopo" → "prosopon") and drops the rest.
_RESOLVE_FUZZY_CUTOFF = 0.92


def _fuzzy_match_is_safe(candidate: str, match: str) -> bool:
    """Structural guard on a fuzzy slug attachment.

    A near-string match is trusted only when the two slugs share the same
    *shape* of name: identical token count, differing in at most one token
    (typo / plural / tense). Anything else is an unrelated entity that merely
    scored high on character overlap.
    """
    ct, mt = candidate.split("-"), match.split("-")
    if len(ct) != len(mt):
        return False
    return sum(1 for a, b in zip(ct, mt) if a != b) <= 1


def resolve_slug(
    candidate: str,
    existing_slugs: list[str],
    entity_type: "str | None" = None,
    slug_types: "dict[str, set[str]] | None" = None,
) -> tuple[str, bool]:
    """
    Match a candidate slug against existing entity slugs.

    Returns (resolved_slug, is_existing). An EXACT match always attaches. A
    fuzzy match must clear `_RESOLVE_FUZZY_CUTOFF`, `_fuzzy_match_is_safe`, and
    — when `entity_type` / `slug_types` are supplied — must live in the same
    type directory as the inferred type. Otherwise the candidate stays NEW
    rather than overwriting an unrelated entity (BRO-1983).
    """
    if candidate in existing_slugs:
        return candidate, True

    matches = difflib.get_close_matches(
        candidate, existing_slugs, n=3, cutoff=_RESOLVE_FUZZY_CUTOFF
    )
    for m in matches:
        if not _fuzzy_match_is_safe(candidate, m):
            continue
        if entity_type is not None and slug_types is not None:
            if entity_type not in slug_types.get(m, set()):
                continue
        return m, True
    return candidate, False


def resolve_candidates(
    candidates: list[str],
    existing_slugs: list[str],
    verbose: bool = False,
    item: "RawItem | None" = None,
    slug_types: "dict[str, set[str]] | None" = None,
) -> list[tuple[str, bool]]:
    """
    Resolve all candidate slugs, returning (slug, is_existing) pairs.
    Deduplicated by resolved slug.

    Candidates that are not entity-shaped are dropped here as a final safety
    net — including LLM-supplied ones, which are *preferred* (see `scatter`)
    but not trusted blindly (BRO-1983).
    """
    seen = set()
    results = []
    for c in candidates:
        if not is_entity_shaped_slug(c):
            if verbose:
                print(f"  resolve: {c!r} → REJECTED (not entity-shaped)")
            continue
        etype = _infer_entity_type(c, item) if item is not None else None
        resolved, is_existing = resolve_slug(c, existing_slugs, etype, slug_types)
        if resolved not in seen:
            seen.add(resolved)
            results.append((resolved, is_existing))
            if verbose:
                tag = "existing" if is_existing else "new"
                print(f"  resolve: {c!r} → {resolved!r} ({tag})")
    return results


# ── Stage 5: Promote ──────────────────────────────────────────────────────────

def _load_entity_template() -> str:
    """
    Return the built-in entity template used by promote_item().

    The external entity-page.md template (ENTITY_TEMPLATE) is the *human-authoring*
    template — its placeholders use descriptive names like {Human-Readable Title} that
    are not intended for programmatic substitution. The built-in default below uses the
    exact keys that content_map in promote_item() populates.
    """
    # Built-in default template — keys match content_map exactly
    return """\
---
slug: {slug}
type: {entity_type}
status: candidate
core_claim: "{core_claim}"
sources:
  - {source_ref}
related: []
created: {created}
updated: {updated}
recorded_at: "{recorded_at}"
tags:
  - {entity_type}
  - bookkeeping
---

# {title}

## Core Claim

{core_claim}

## Evidence

> {quote}

Source: {source_ref} | Score: {score}/9 (n={novelty} s={specificity} r={relevance})

## Context

{content}

## Related

<!-- Add wikilinks to related entities here, e.g. [[arcan]] [[memory]] -->

## Open Questions

<!-- What remains unclear? -->

## Synthesis Notes

<!-- Populated by synthesize stage -->
"""


# ── core_claim derivation (BRO-1983) ──────────────────────────────────────────
#
# The original producer was `raw_claim[:137] + "..."` — a hard mid-word truncation
# sized precisely to clear the linter's `len(core_claim) <= 140` rule. A quality
# gate the producer satisfies BY CONSTRUCTION is not a gate: every mis-promoted
# research doc shipped a 140-char shard of markdown as its permanent claim
# ("VERIFIED VERDICTS (2026-07-20) — authoritative **The three novelty
# checks:** - **(a) Model-invariant harness stability — PARTIAL YES, our...").
#
# The replacement derives a COMPLETE sentence. Order of attempts:
#   1. first sentence that fits the limit and passes `_lint_core_claim_quality`
#   2. else, the first *clause* of an over-long sentence, split at a semicolon /
#      em-dash / colon — still a complete, self-contained proposition
#   3. else None → PROMOTION-BLOCKING. The caller skips rather than minting a
#      page with a truncated claim.
# A `...` suffix is never emitted, at any step.

_CORE_CLAIM_MAX = 140
_CORE_CLAIM_MIN = 12          # shorter than this is a label, not a claim
_CORE_CLAIM_MIN_WORDS = 3

_MD_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_MD_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_MD_HRULE_RE = re.compile(r"^\s{0,3}(?:[-*_]\s*){3,}$")
_MD_TABLE_ROW_RE = re.compile(r"^\s*\|")
_MD_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_MD_BLOCKQUOTE_RE = re.compile(r"^\s*>+\s?")

# Clause separators that end a self-contained proposition.
_CLAUSE_SPLIT_RE = re.compile(r"\s*(?:;|—|–|--)\s+|\s+[:—]\s+")

# A clause led by a coordinator / subordinator is a continuation of the clause
# before it — standing alone it is a fragment ("but REFRAME REQUIRED").
_CLAUSE_LEAD_REJECT = frozenset({
    "but", "and", "or", "nor", "yet", "so", "however", "therefore", "thus",
    "hence", "which", "that", "because", "although", "though", "while",
    "whereas", "instead", "moreover", "furthermore", "meanwhile", "then",
    "also", "plus", "besides", "otherwise", "still",
})

# Sentence terminator: . ! ? followed by whitespace/EOS, not part of a decimal
# ("3.14"), an ellipsis, or a known abbreviation.
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "cf.", "al.", "fig.", "no.",
                  "dr.", "mr.", "mrs.", "ms.", "st.", "approx.", "est.", "inc.")


def _strip_markdown_for_claim(body: str) -> str:
    """Reduce a markdown body to plain prose suitable for claim extraction."""
    text = _MD_FENCE_RE.sub(" ", body or "")
    text = _MD_HTML_COMMENT_RE.sub(" ", text)

    kept: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            kept.append("")
            continue
        if _MD_HEADING_RE.match(line) or _MD_HRULE_RE.match(line):
            continue                      # section headers are not claims
        if _MD_TABLE_ROW_RE.match(line) or "|" in line and line.count("|") >= 2:
            continue                      # table rows are not claims
        line = _MD_BLOCKQUOTE_RE.sub("", line)
        line = _MD_LIST_MARKER_RE.sub("", line)
        # A colon-terminated line with no sentence punctuation is a lead-in
        # label ("**The three novelty checks:**"), not a claim. Keeping it
        # glued the label onto the following list item and produced
        # "The three novelty checks: (a) Model-invariant harness stability."
        if re.sub(r"[*_`\s]+$", "", line).endswith(":") and not re.search(r"[.!?]", line):
            continue
        kept.append(line)

    text = "\n".join(kept)
    # Inline markup → plain text.
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)          # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)       # links
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", text)  # wikilinks
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text, flags=re.DOTALL)  # bold
    text = re.sub(r"(?<!\w)([*_])(?!\s)(.+?)(?<!\s)\1(?!\w)", r"\2", text)  # emphasis
    text = re.sub(r"~~(.+?)~~", r"\1", text)                   # strikethrough
    text = text.replace("`", "")
    # Any residual markup characters at claim boundaries.
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    """Split prose into sentences, tolerating decimals and common abbreviations."""
    sentences: list[str] = []
    start = 0
    for m in re.finditer(r"[.!?]+(?=\s|$)", text):
        end = m.end()
        head = text[start:end]
        lowered = head.lower().rstrip()
        if any(lowered.endswith(abbr) for abbr in _ABBREVIATIONS):
            continue
        # "3." inside "3.14" never matches (lookahead needs whitespace), but a
        # trailing enumerator like "1. " would — require a letter in the chunk.
        if not re.search(r"[A-Za-z]{2}", head):
            continue
        sentences.append(head.strip())
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return [s for s in sentences if s]


# Arrows, list bullets, table pipes, blockquotes, headings, enumerators — the
# leading glyphs of a document fragment rather than a sentence.
_CLAIM_STRUCTURAL_PREFIX_RE = re.compile(r"^\s*(?:[→←↔⇒⇐»]|[-*•]\s|\||>|#|\d+\.\s)")


def _claim_is_acceptable(claim: str, limit: int) -> bool:
    """A candidate claim must fit, be a real proposition, and pass the lint gate."""
    if not claim:
        return False
    if len(claim) > limit or len(claim) < _CORE_CLAIM_MIN:
        return False
    if len(claim.split()) < _CORE_CLAIM_MIN_WORDS:
        return False
    if claim.endswith(("...", "…")):
        return False
    # A claim that opens with a structural glyph is a document fragment the
    # markdown stripper failed to shed — a continuation arrow, list bullet,
    # table cell or blockquote — not a proposition. Observed live (BRO-1991):
    # pattern/environment-contract carried "→ In our taxonomy: an arm-B system."
    #
    # Measured against all 804 committed pages before shipping: 0 flagged
    # (0.00%). Unlike the "does the claim mention its slug?" heuristic — which
    # flagged 36% of the same corpus and was therefore rejected — this tests a
    # structural property, so it does not need to interpret meaning.
    if _CLAIM_STRUCTURAL_PREFIX_RE.match(claim):
        return False
    # The producer must clear the INDEPENDENT quality gate, not just the
    # length rule it used to satisfy by construction.
    return not _lint_core_claim_quality("<derive>", claim)


def _yaml_safe_claim(claim: str) -> str:
    """Make a claim safe to embed inside a double-quoted YAML scalar."""
    claim = claim.replace("\\", "/").replace('"', "'")
    claim = claim.replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", claim).strip()


def derive_core_claim(body: str, limit: int = _CORE_CLAIM_MAX) -> Optional[str]:
    """Derive a complete, YAML-safe one-sentence core_claim from an item body.

    Returns None when no clean claim can be derived — a promotion-blocking
    signal. NEVER returns a truncated string (BRO-1983).
    """
    prose = _strip_markdown_for_claim(body)
    if not prose:
        return None

    # 0 — the whole body already fits: nothing is truncated, so the body IS the
    # claim. This is the branch the original code got right; only the >limit
    # branch was defective.
    whole = _yaml_safe_claim(prose)
    if _claim_is_acceptable(whole, limit):
        return whole

    sentences = _split_sentences(prose)

    # 1 — first complete sentence that fits.
    for sentence in sentences:
        candidate = _yaml_safe_claim(sentence)
        if _claim_is_acceptable(candidate, limit):
            return candidate

    # 2 — first self-contained clause of an over-long sentence.
    for sentence in sentences:
        for clause in _CLAUSE_SPLIT_RE.split(sentence):
            clause = (clause or "").strip().rstrip(",;:")
            if not clause:
                continue
            first = re.sub(r"[^a-z]", "", clause.split()[0].lower())
            if first in _CLAUSE_LEAD_REJECT:
                continue  # a continuation fragment, not a standalone claim
            # Restore terminal punctuation so the claim reads as a proposition.
            if not clause.endswith((".", "!", "?")):
                clause = clause + "."
            candidate = _yaml_safe_claim(clause)
            if _claim_is_acceptable(candidate, limit):
                return candidate

    return None


# ── Entity-type inference (BRO-1983) ──────────────────────────────────────────
#
# The original used bare substring `in` tests over `slug + " " + content`, so
# "api" matched *rapid*, "cli" matched *client*, "app" matched *happen*/*apply*,
# and "how"/"why" matched arbitrary prose. First-match-wins turned those into
# systematic type misassignment (and duplicate slugs across type dirs).

def _keyword_re(words: "list[str]") -> "re.Pattern":
    """Word-boundary alternation over `words` (case-insensitive)."""
    return re.compile(
        r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE
    )


_TYPE_PATTERN_RE = _keyword_re(["pattern", "patterns", "approach", "method",
                                "strategy", "technique"])
_TYPE_TOOL_RE = _keyword_re(["tool", "tools", "library", "framework", "sdk",
                             "cli", "api"])
_TYPE_PROJECT_RE = _keyword_re(["project", "platform", "product", "app",
                                "system"])
_TYPE_QUESTION_RE = _keyword_re(["open question", "open questions"])
_TYPE_DISCOVERY_RE = _keyword_re(["discovered", "insight", "breakthrough"])
_TYPE_PERSON_RE = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")
# An interrogative SENTENCE — not a stray '?' anywhere in the body, which is
# what made `question/` a dumping ground.
_INTERROGATIVE_RE = re.compile(
    r"(?:^|[.!?]\s+)(?:who|what|when|where|why|how|which|is|are|do|does|"
    r"did|can|could|should|would|will)\b[^.!?]*\?",
    re.IGNORECASE,
)


def _infer_entity_type(slug: str, item: RawItem) -> str:
    """Guess entity type from slug and content (word-boundary matched)."""
    text = slug + " " + item.content
    if _TYPE_PATTERN_RE.search(text):
        return "pattern"
    if _TYPE_TOOL_RE.search(text):
        return "tool"
    if _TYPE_PERSON_RE.search(item.author or ""):
        return "person"
    if _TYPE_PROJECT_RE.search(text):
        return "project"
    if _TYPE_QUESTION_RE.search(text) or _INTERROGATIVE_RE.search(item.content):
        return "question"
    if _TYPE_DISCOVERY_RE.search(text):
        return "discovery"
    return "concept"


def _merged_tombstone_path(slug: str, entity_type: str | None = None) -> "Path | None":
    """Return the path of a `status: merged` tombstone for `slug`, else None.

    A merge (`bookkeeping merge`, BRO-1442) leaves the folded-away dup on disk
    with `status: merged` so the promote pipeline can detect "this slug was
    merged into a canonical" and SKIP re-creating it from its raw extract —
    without this, deletions silently resurrect on the next run.

    Scoped to `entity_type` when given (default in the promote path): two
    unrelated entities may share a slug across type dirs (e.g. person/x +
    pattern/x), so a tombstone in ONE dir must not suppress a live entity in
    ANOTHER. With entity_type=None it falls back to slug-wide (any dir) — only
    used by callers that genuinely want the first tombstone for the slug.
    """
    if not ENTITIES_DIR.exists():
        return None
    if entity_type is not None:
        cands = [ENTITIES_DIR / entity_type / f"{slug}.md"]
    else:
        cands = list(ENTITIES_DIR.rglob(f"{slug}.md"))
    for p in cands:
        if ".lago-blobs" in p.parts or not p.exists():
            continue
        try:
            fm, _ = read_frontmatter(p)
        except Exception:
            continue
        if fm.get("status") == "merged":
            return p
    return None


# ── Typed temporal revision envelope — PRODUCER side (gh-156) ─────────────────
#
# The shipped `lint --temporal` audit is a DETECTOR. It can surface that a page
# asserts mutable state without an as-of date; it cannot establish which belief
# is current or which record supersedes another. That question is only decidable
# if the WRITE path emits the answer, so the producers come first and the
# semantic validation is layered on afterwards.
#
# Four typed fields, with deliberately different provenance rules:
#
#   recorded_at   system time. Emitted MECHANICALLY on creation and re-stamped
#                 on a substantive update. Never operator-supplied — a
#                 hand-chosen "when the system learned this" is not system time.
#   valid_from    claim-effective time. OPTIONAL, and only ever written when a
#                 source or an explicit revision SUPPLIES it. It is never
#                 inferred from prose, from an ISO date found in the body, or
#                 from the ingest timestamp (which is when we saw the claim, not
#                 when the claim became true).
#   supersedes    the records this page replaces, as [[wikilink]]s. Emitted ONLY
#                 by an explicit correction/revision action (`revise`, `merge`).
#   revision_link the record that authorized the supersession. Required
#                 alongside `supersedes` so a replacement is always traceable to
#                 the decision that made it.
#
# The hard rule this section exists to enforce: no field here may be produced by
# reading present-tense prose. A schema that claims guarantees no writing path
# supplies is compliance theater — see references/temporal-revision-envelope.md.

# `valid_from` is read from exactly this metadata key on the raw item. One
# canonical key, no fuzzy aliasing: guessing which of several near-miss keys the
# author "meant" is the prose inference this envelope refuses to do.
_VALID_FROM_METADATA_KEY = "valid_from"

_FM_CLOSING_FENCE_RE = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)


class MalformedEnvelopeError(Exception):
    """An existing `supersedes` value cannot be rewritten without losing data.

    Raised instead of silently repairing. A correction workflow that quietly
    rewrote corrupt provenance would destroy the very record it exists to
    preserve — the operator has to look at it.
    """


def _yaml_double_quoted(value: str) -> str:
    """Render `value` as a YAML double-quoted scalar, escaped.

    `json.dumps` is exactly right here: YAML 1.2's double-quoted scalar accepts
    JSON's escape set, so quotes, backslashes, newlines and control characters
    all survive. Naive f-string interpolation does not — a `--revision-link`
    containing a quote and a newline could otherwise close the scalar and inject
    frontmatter (`x"\\n---\\nforged:`), splicing an attacker-controlled document
    into the page.
    """
    return json.dumps(str(value), ensure_ascii=False)


def _coerce_iso_date_str(value: object) -> "str | None":
    """Render `value` as a canonical YYYY-MM-DD string, or None if it isn't a date.

    Accepts what YAML actually hands back for a date-shaped field (`date`,
    `datetime`, or a string) and rejects everything else. Returning None is the
    contract for "not supplied" — a caller must never fall back to today, since
    that would silently manufacture a claim-effective time.
    """
    parsed = _coerce_temporal_date(value)
    return parsed.isoformat() if parsed is not None else None


def _supplied_valid_from(item: "RawItem") -> "str | None":
    """Return the explicitly supplied claim-effective date for `item`, else None.

    Reads ONLY `item.metadata["valid_from"]`. It deliberately does not consult
    `item.content` (prose inference), `item.timestamp` (ingest time, not
    claim-effective time), or any date found in the body. When the source did
    not state when the claim became true, the field is omitted — an absent
    `valid_from` is honest, a guessed one is not.
    """
    metadata = getattr(item, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    return _coerce_iso_date_str(metadata.get(_VALID_FROM_METADATA_KEY))


def _fm_key_block_re(key: str) -> "re.Pattern":
    """Match a frontmatter key AND any indented/list continuation lines it owns.

    Replacing only the `key:` line would orphan the items of a block list
    (`supersedes:\\n  - "[[x]]"`) into invalid YAML at the top level. Consuming
    the continuation block keeps a rewrite total.

    The closing `---` fence is excluded explicitly, and the lookahead tolerates
    a trailing `\\r`. Without that, a block list as the LAST frontmatter key
    would swallow the fence (`---` satisfies the "line starts with a dash" arm)
    and splice frontmatter into the body — and on a CRLF page the fence line is
    `---\\r`, which an anchored `---[ \\t]*$` would fail to recognise at all.

    Blank lines are consumed only when a further continuation line follows, so
    a legal `key:\\n  - a\\n\\n  - b\\n` block is taken whole while a blank line
    separating the key from the fence is left alone.
    """
    return re.compile(
        rf"^{re.escape(key)}:[^\n]*\n"
        rf"(?:(?:[ \t]*\r?\n)*(?!---[ \t]*\r?$)(?:[ \t]+|[ \t]*-)[^\n]*\n)*",
        re.MULTILINE,
    )


def _set_frontmatter_scalar(
    text: str, key: str, rendered: str, after: "str | None" = None,
) -> str:
    """Set `key: rendered` in `text`'s frontmatter, replacing or inserting.

    `rendered` is emitted verbatim, so callers own the YAML rendering (quoting a
    date, flow-listing wikilinks). Only the leading frontmatter block is
    touched; a body line that happens to start with `key:` is preserved — the
    same invariant `_split_frontmatter` exists to protect.

    Returns `text` unchanged when the document has no frontmatter: a page
    without frontmatter is not an entity page, and inventing one here would
    produce a file the rest of the pipeline cannot read.

    Every occurrence of `key` is removed and the new value written once at the
    position of the first. Replacing only the first would leave a duplicate key
    behind — and PyYAML resolves duplicates to the LAST one, so the write would
    parse back as if it had never happened.
    """
    fm, body = _split_frontmatter(text)
    if not fm:
        return text
    line = f"{key}: {rendered}\n"
    block_re = _fm_key_block_re(key)
    matches = list(block_re.finditer(fm))
    if matches:
        at = matches[0].start()
        fm = block_re.sub("", fm)
        fm = fm[:at] + line + fm[at:]
        return fm + body
    if after:
        after_re = _fm_key_block_re(after)
        m = after_re.search(fm)
        if m:
            fm = fm[: m.end()] + line + fm[m.end():]
            return fm + body
    # Fall back to inserting immediately before the closing fence.
    fences = list(_FM_CLOSING_FENCE_RE.finditer(fm))
    if len(fences) >= 2:
        at = fences[-1].start()
        fm = fm[:at] + line + fm[at:]
    return fm + body


def _render_flow_list(values: "list[str]") -> str:
    """Render values as a single-line YAML flow list of escaped scalars.

    Flow style (not a block list) keeps every envelope field a one-line entry,
    which is what makes `_set_frontmatter_scalar` rewrites and the byte-identity
    idempotency check straightforward.
    """
    return "[" + ", ".join(_yaml_double_quoted(v) for v in values) + "]"


def _parse_wikilink_list(value: object) -> "list[str]":
    """Parse a `supersedes` value into slugs, STRICTLY.

    Only canonical `[[slug]]` entries are accepted — the write side emits
    nothing else. Anything other than that (a bare slug, a truncated `[[broken`,
    a non-string) raises rather than being repaired or dropped, because the
    caller is about to rewrite this field: silently canonicalising a malformed
    entry, or dropping one it cannot read, would destroy provenance while
    reporting success. The audit reports these as warnings; the WRITER refuses.
    """
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    if not isinstance(value, list):
        raise MalformedEnvelopeError(
            f"supersedes must be a list, found {type(value).__name__}")
    out: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise MalformedEnvelopeError(
                f"supersedes entry {entry!r} is not a string")
        m = _CANONICAL_WIKILINK_RE.match(entry.strip())
        if not m:
            raise MalformedEnvelopeError(
                f"supersedes entry {entry!r} is not [[wikilink]] format")
        slug = m.group(1).strip()
        if slug and slug not in out:
            out.append(slug)
    return out


_ENVELOPE_KEYS = ("supersedes", "revision_link", "recorded_at", "valid_from")


def _assert_no_duplicate_envelope_keys(text: str) -> None:
    """Refuse to rewrite frontmatter that declares an envelope key twice.

    PyYAML resolves a duplicate key to the LAST occurrence, so a read-then-write
    would silently discard whatever the earlier one held: `revision_link` listed
    as ticket-A and then ticket-B parses as ticket-B alone, and adding ticket-C
    would erase A permanently. Reading a value we are about to destroy is not
    something a correction workflow may do quietly.

    Detection walks the parser's own mapping nodes rather than matching lines.
    A line-based count answers a different question than YAML does, in both
    directions: `note: "…\\nsupersedes: prose"` is one key inside a legal
    multiline scalar (a false refusal), and `"supersedes":` is a second real key
    a `^supersedes:` pattern never sees (a missed one).
    """
    if not _YAML_AVAILABLE:
        return
    fm, _ = _split_frontmatter(text)
    if not fm:
        return
    inner = fm.strip()
    if inner.startswith("---"):
        inner = inner[3:]
    if inner.rstrip().endswith("---"):
        inner = inner.rstrip()[:-3]
    try:
        node = yaml.compose(inner)
    except Exception:
        return  # unparseable frontmatter is the ordinary lint's problem
    if node is None or not isinstance(node, yaml.MappingNode):
        return
    seen: dict = {}
    for key_node, _value in node.value:
        key = getattr(key_node, "value", None)
        if not isinstance(key, str):
            continue
        seen[key] = seen.get(key, 0) + 1
    for key in _ENVELOPE_KEYS:
        if seen.get(key, 0) > 1:
            raise MalformedEnvelopeError(
                f"frontmatter declares '{key}' {seen[key]} times; YAML keeps "
                f"only the last, so rewriting would discard the others")


def _parse_revision_links(value: object) -> "list[str]":
    """Parse `revision_link` into a list, tolerating the legacy scalar form.

    A single authorizing record reads naturally as a scalar and hand-authored
    pages carry it that way, so a lone string is accepted and normalised into a
    one-element list. Anything else raises — including a BLANK entry, which is
    not "nothing to preserve": it is a slot somebody meant to fill, and quietly
    dropping it on rewrite is the same silent repair the strict `supersedes`
    parser refuses.
    """
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    out: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise MalformedEnvelopeError(
                f"revision_link entry {entry!r} is not a string")
        entry = entry.strip()
        if not entry:
            raise MalformedEnvelopeError("revision_link contains a blank entry")
        if entry not in out:
            out.append(entry)
    return out


def _apply_revision_envelope(
    text: str,
    *,
    supersedes: "list[str]",
    revision_link: str,
    valid_from: "str | None" = None,
    today: "str | None" = None,
) -> str:
    """Write the typed revision envelope onto an entity page's frontmatter.

    The single write-side entry point for `supersedes` + `revision_link`, shared
    by every explicit correction workflow (`revise`, `merge`). Nothing else in
    the pipeline may emit these two fields — that restriction is what keeps
    "this record replaces that one" a statement somebody made, rather than
    something a regex concluded from present-tense prose.

    Both `supersedes` and `revision_link` are UNIONED with what is already
    present (order preserved, deduped). A page can be corrected more than once,
    and a later revision must not silently drop what an earlier one recorded —
    which is why `revision_link` is a LIST: overwriting a scalar would leave
    ticket B claiming authorship of the supersession ticket A authorized.

    (What the envelope still does not represent is WHICH link authorized WHICH
    entry. A per-entry binding is a larger schema change; until it exists, the
    fields say "these records were replaced, on the authority of these
    decisions" and no more. See references/temporal-revision-envelope.md.)

    Idempotent in both directions: when the merged envelope and `valid_from`
    are already what a revision would write, the text is returned UNCHANGED —
    no stamp is touched. Without that early return, replaying the same command
    on a later day would rewrite `updated` and `recorded_at` and report a
    substantive change that did not happen.

    Raises MalformedEnvelopeError when the existing `supersedes` or
    `revision_link` cannot be read exactly; the caller decides whether that is
    fatal.
    """
    today = today or today_str()
    _assert_no_duplicate_envelope_keys(text)
    existing_slugs = _parse_wikilink_list(_frontmatter_value(text, "supersedes"))
    existing_links = _parse_revision_links(_frontmatter_value(text, "revision_link"))
    existing_valid_from = _coerce_iso_date_str(_frontmatter_value(text, "valid_from"))
    existing_recorded_at = _coerce_temporal_date(_frontmatter_value(text, "recorded_at"))

    merged = list(existing_slugs)
    for slug in supersedes:
        if slug not in merged:
            merged.append(slug)
    links = list(existing_links)
    link = (revision_link or "").strip()
    if merged and link and link not in links:
        links.append(link)

    unchanged = (
        merged == existing_slugs
        and links == existing_links
        and (valid_from is None or valid_from == existing_valid_from)
        # A page carrying the right envelope but NO parseable system-time stamp
        # is not "already recorded" — the mechanical field is still missing, and
        # returning early here would leave the first explicit revision unstamped
        # forever.
        and existing_recorded_at is not None
    )
    if unchanged:
        return text

    if merged:
        text = _set_frontmatter_scalar(
            text, "supersedes", _render_flow_list([f"[[{s}]]" for s in merged]),
            after="related")
        text = _set_frontmatter_scalar(
            text, "revision_link", _render_flow_list(links), after="supersedes")
    # `updated` is written QUOTED. Emitting it bare would un-quote a page that
    # already had `updated: "2026-01-01"`, and the repo's own unquoted-date lint
    # then warns on every page this command touches — the writer failing the
    # gate it is supposed to satisfy. (The promote path still emits it bare;
    # that predates the envelope and is left alone here.)
    text = _set_frontmatter_scalar(
        text, "updated", _yaml_double_quoted(today), after="created")
    text = _set_frontmatter_scalar(
        text, "recorded_at", _yaml_double_quoted(today), after="updated")
    # Placed AFTER `recorded_at` exists, so `after=` actually resolves. Set
    # earlier, the anchor was absent on a page acquiring the envelope for the
    # first time and the field landed at the end of the frontmatter instead.
    if valid_from:
        text = _set_frontmatter_scalar(
            text, "valid_from", _yaml_double_quoted(valid_from), after="recorded_at")
    return text


def _frontmatter_value(text: str, key: str) -> object:
    """Return one parsed frontmatter value from raw page text, or None."""
    fm, _ = parse_frontmatter(text)
    return fm.get(key) if isinstance(fm, dict) else None


def promote_item(
    scored: ScoredItem,
    entity_slug: str,
    entity_type: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> Path | None:
    """
    Write an entity page for a scored item.

    Creates research/entities/{entity_type}/{entity_slug}.md using the template.
    Returns the path written, or None in dry_run mode or on error.
    """
    if entity_type is None:
        entity_type = _infer_entity_type(entity_slug, scored.item)

    entity_dir = ENTITIES_DIR / entity_type
    entity_path = entity_dir / f"{entity_slug}.md"

    # Respect merge tombstones (BRO-1442): a dup folded into a canonical must not
    # resurrect from its raw extract on a later promote. The canonical owns the
    # content (and the dup's slug as an alias). Scoped to entity_type so an
    # unrelated same-slug tombstone in a different type dir can't suppress this.
    _tomb = _merged_tombstone_path(entity_slug, entity_type=entity_type)
    if _tomb is not None:
        if verbose:
            print(f"  [promote] skip (merged → tombstone): {entity_slug}")
        return None

    if entity_path.exists():
        # Update an existing page. The current pipeline carries no semantic
        # merge through this branch — it only ever bumped the `updated:`
        # field — so an unconditional rewrite produces a pure date-bump diff
        # on every run (the 137-entities-churned-per-run pathology in
        # ~/.config/bookkeeping/run-log.jsonl). The content-identity guard
        # below skips the write when the ONLY would-be change is `updated:`.
        # `updated:` must reflect the last *substantive* change, not the last
        # *run* — so a run with no new raw material must leave the file
        # byte-identical.
        wrote = _update_entity_page_if_changed(entity_path, dry_run=dry_run)
        if verbose:
            verb = "updated existing" if wrote else "unchanged (skipped)"
            print(f"  [promote] {verb}: {_display_path(entity_path)}")
        # Return the path only when a real write happened, so the caller's
        # entities_updated counter reflects substantive updates — not no-ops.
        # (dry_run is reported as a no-op write: nothing was written.)
        return entity_path if wrote else None

    # A junk slug must never reach disk. `_build_entity_slug_candidates` and
    # `resolve_candidates` already gate, but promote_item is also a public
    # entry point (cmd_promote, callers in tests) — defence in depth.
    if not is_entity_shaped_slug(entity_slug):
        if verbose:
            print(f"  [promote] SKIP (slug not entity-shaped): {entity_slug!r}")
        return None

    template = _load_entity_template()
    title = entity_slug.replace("-", " ").title()
    # core_claim must be a single YAML-safe line. It is DERIVED as a complete
    # sentence (or a complete clause), never truncated — see derive_core_claim.
    # No derivable claim ⇒ promotion-blocking: skipping beats minting a page
    # whose permanent claim is a 137-char shard of markdown (BRO-1983).
    core_claim = derive_core_claim(scored.item.content)
    if not core_claim:
        if verbose:
            print(
                f"  [promote] SKIP (no complete claim ≤{_CORE_CLAIM_MAX} chars "
                f"derivable): {entity_slug}"
            )
        return None
    source_ref = scored.item.source_id
    today = today_str()

    # Substitute all {placeholder} patterns
    content_map = {
        "slug": entity_slug,
        "entity_type": entity_type,
        "title": title,
        "core_claim": core_claim,
        "source_ref": source_ref,
        "created": today,
        "updated": today,
        # System time, emitted mechanically — this is the one envelope field the
        # producer is entitled to author on its own.
        "recorded_at": today,
        "content": scored.item.content,
        "quote": scored.item.quote or scored.item.content[:200],
        "score": str(scored.total),
        "novelty": str(scored.novelty),
        "specificity": str(scored.specificity),
        "relevance": str(scored.relevance),
    }
    page = template
    for key, value in content_map.items():
        page = page.replace("{" + key + "}", value)
    page = _sanitize_page_text(page)

    # `valid_from` is written ONLY when the source supplied it. No supplied
    # value ⇒ no field: an omitted claim-effective time is a truthful "not
    # stated", whereas defaulting it to today would assert that every promoted
    # claim became true on its promotion date.
    valid_from = _supplied_valid_from(scored.item)
    if valid_from:
        page = _set_frontmatter_scalar(
            page, "valid_from", _yaml_double_quoted(valid_from), after="recorded_at")
    elif verbose and isinstance(getattr(scored.item, "metadata", None), dict) \
            and scored.item.metadata.get(_VALID_FROM_METADATA_KEY) is not None:
        # The source TRIED to state a claim-effective time and it did not parse.
        # Dropping it is correct — coercing a guess would be worse — but doing
        # so silently hides a broken upstream emitter.
        print(f"  [promote] ignoring unparseable metadata.valid_from "
              f"{scored.item.metadata[_VALID_FROM_METADATA_KEY]!r}: {entity_slug}")

    if not dry_run:
        entity_dir.mkdir(parents=True, exist_ok=True)
        entity_path.write_text(page)
        if verbose:
            print(f"  [promote] created: {_display_path(entity_path)}")
    else:
        if verbose:
            print(f"  [promote] dry-run: would create {_display_path(entity_path)}")

    return entity_path if not dry_run else None


# Frontmatter fields that legitimately change every run and therefore must
# be excluded from the content-identity comparison. Both entries are pure
# system-time stamps the pipeline re-writes on update.
#
# `recorded_at` MUST be listed here. It is bumped by `_render_updated_entity`
# alongside `updated`, so leaving it out would make every page differ from its
# own candidate on every run — resurrecting exactly the 137-entities-churned
# pathology the guard below was built to kill, and inflating `recorded_at` into
# a "last run" stamp instead of "last substantive change".
#
# `valid_from`, `supersedes`, and `revision_link` are deliberately NOT volatile:
# they are semantic claims, and a change to any of them is a real delta that
# must be written.
_VOLATILE_FRONTMATTER_FIELDS = ("updated", "recorded_at")


def _split_frontmatter(text: str) -> tuple[str, str]:
    """
    Split `text` into (frontmatter_block, body), where frontmatter_block
    includes both `---` fences and the trailing newline. Returns ("", text)
    when the document has no leading YAML frontmatter.

    Anchors frontmatter-only transforms (volatile-field stripping, `updated:`
    bumping) so they never touch the body. A body line that happens to start
    with `updated:` — a wrapped sentence, a markdown table row, a quoted log
    line — must be preserved; otherwise the content-identity guard below could
    silently classify a real (future semantic-merge) change as a no-op and
    discard it. (P20 finding, 2026-05-28.)
    """
    m = re.match(r"^(---\s*\n.*?\n---\s*\n)(.*)$", text, re.DOTALL)
    if m:
        return m.group(1), m.group(2)
    return "", text


def _strip_volatile_fields(text: str) -> str:
    """
    Return `text` with the volatile frontmatter lines removed, for use in a
    content-identity comparison.

    Only top-of-line `field: …` entries inside the leading YAML frontmatter
    are stripped (e.g. `updated: 2026-05-28`); the body is left untouched.
    This lets two versions of an entity page be compared modulo their
    timestamp: if everything else is byte-identical, the update is a no-op
    and must not be rewritten.
    """
    fm, body = _split_frontmatter(text)
    if not fm:
        return text
    for fld in _VOLATILE_FRONTMATTER_FIELDS:
        fm = re.sub(rf"^{re.escape(fld)}:\s*.*$\n?", "", fm, flags=re.MULTILINE)
    return fm + body


def _render_updated_entity(existing: str) -> str:
    """
    Compute the would-be new content for an existing entity page on update.

    The current pipeline carries no semantic merge through the update path —
    it only bumps the `updated:` and `recorded_at:` frontmatter fields to
    today. Isolated as a named seam so a future semantic-merge step (and tests)
    can compose here without touching the content-identity guard below.

    `recorded_at` is re-stamped only when the page ALREADY carries it. Pages
    predating the typed envelope are not backfilled here, because the update
    path cannot know when they were actually recorded: a backfill would stamp
    today as the system time of a claim recorded long before, and it would land
    on exactly the arbitrary subset of legacy pages that happen to acquire some
    unrelated delta. (It would not churn the whole graph — the guard below
    strips `recorded_at` as volatile — which is precisely what makes the
    mis-stamping quiet rather than obvious.) Legacy pages acquire the field
    through an explicit revision or a dedicated migration instead.
    """
    today = today_str()
    fm, body = _split_frontmatter(existing)
    if not fm:
        return existing
    fm = re.sub(
        r"(^updated:\s*)(.+)$", rf"\g<1>{today}", fm, flags=re.MULTILINE
    )
    fm = re.sub(
        r'(^recorded_at:\s*)(.+)$', rf'\g<1>"{today}"', fm, flags=re.MULTILINE
    )
    return fm + body


def _update_entity_page_if_changed(entity_path: Path, dry_run: bool = False) -> bool:
    """
    Content-identity guard for the existing-entity update path.

    Computes the would-be new page content (currently: existing content with
    the `updated:` field bumped to today — the pipeline carries no semantic
    merge through this branch). Compares it to the existing content with all
    volatile (pure-timestamp) fields stripped. If they are otherwise
    identical, SKIPS the write entirely — no `updated:` bump, no rewrite —
    and returns False.

    Returns True only when there is a real semantic delta (the would-be
    content differs from the existing content for some reason other than the
    `updated:` field), in which case `updated:` is set to today and the file
    is written (unless dry_run, where the would-be write is reported but not
    performed).

    Net effect: two consecutive `bookkeeping run` invocations with no new raw
    material produce zero file modifications on the second run — and, because
    the current update branch never introduces a semantic delta, zero on the
    first run either. This eliminates the pure date-bump churn.
    """
    existing = entity_path.read_text()
    # The would-be new content under the current (timestamp-only) update path.
    candidate = _render_updated_entity(existing)

    # Compare modulo volatile fields. If the only difference is `updated:`,
    # the update is a no-op → skip.
    if _strip_volatile_fields(existing) == _strip_volatile_fields(candidate):
        return False

    # Real semantic delta — write (with `updated:` bumped to today).
    candidate = _sanitize_page_text(candidate)
    if not dry_run:
        entity_path.write_text(candidate)
    return True


# ── Stage 6: Synthesize ───────────────────────────────────────────────────────

def find_synthesis_candidates(verbose: bool = False) -> list[dict]:
    """
    Detect entity clusters that may warrant a synthesis note.

    A cluster is a group of ≥2 entities that share a common keyword in their
    core_claim or content. Returns list of cluster descriptors.
    """
    if not ENTITIES_DIR.exists():
        return []

    entity_files = list(ENTITIES_DIR.rglob("*.md"))
    if verbose:
        print(f"[synthesize] Scanning {len(entity_files)} entity pages...")

    # Build keyword → [slugs] map
    keyword_map: dict[str, list[str]] = {}
    for ef in entity_files:
        slug = ef.stem
        text = ef.read_text(errors="replace").lower()
        for term in LIFE_OS_TERMS + ["event sourcing", "trust", "policy", "governance"]:
            if term in text:
                keyword_map.setdefault(term, []).append(slug)

    candidates = []
    for term, slugs in sorted(keyword_map.items(), key=lambda x: -len(x[1])):
        if len(slugs) >= 2:
            candidates.append({
                "topic": term,
                "entity_count": len(slugs),
                "slugs": slugs[:10],
            })

    # Deduplicate by overlapping slug sets (keep largest clusters)
    seen_slugs: set[str] = set()
    filtered = []
    for c in candidates:
        slug_set = set(c["slugs"])
        if not slug_set.issubset(seen_slugs):
            filtered.append(c)
            seen_slugs.update(slug_set)

    return filtered[:20]


# ── Stage 7: Lint ─────────────────────────────────────────────────────────────

# An unquoted ISO-date scalar in frontmatter: `key: 2026-05-30` (optionally with
# a time component). Matches the value only when it is NOT wrapped in quotes —
# `key: "2026-05-30"` does not match because the char after the space is `"`,
# not a digit. List-item lines (`  - 2026-05-30`) are not matched: there is no
# `key:` token. The value must be followed by EOL or whitespace, so a malformed
# `key: 2026-05-30# x` (no space before `#` → a YAML string, not a date) does not
# match and is left untouched. `rest` captures a real trailing comment (which YAML
# requires to be whitespace-preceded) so the auto-fix preserves it.
_UNQUOTED_DATE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_-]+):[ \t]+"
    r"(?P<val>\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?)"
    r"(?P<rest>(?:[ \t]+#.*)?[ \t]*)$"
)


def _extract_frontmatter_block(text: str) -> Optional[str]:
    """Return the raw text between the opening and closing `---` fences, or None."""
    m = re.match(r"^(?:---\s*\n)(.*?)(?:\n---\s*\n)", text, re.DOTALL)
    return m.group(1) if m else None


def _lint_unquoted_dates(path_str: str, text: str) -> list[LintError]:
    """Warn on unquoted ISO-date scalars in frontmatter.

    Unquoted YAML dates (`updated: 2026-05-30`) are parsed into native
    date/timestamp objects that many tools re-serialize into a full ISO
    timestamp (`2026-05-30T00:00:00.000Z`) on the next unrelated edit — silently
    breaking downstream consumers that expect a stable `YYYY-MM-DD` string
    (documented Obsidian Dataview + Symfony breakages). Quoting keeps them stable
    strings. WARNING severity (non-breaking) because pages graph-wide still carry
    unquoted dates; mechanically auto-fixable via `lint --fix`. See
    research/notes/2026-06-08-frontmatter-best-practices-synthesis.md (BRO-1449).
    """
    fm = _extract_frontmatter_block(text)
    if fm is None:
        return []
    errors: list[LintError] = []
    for raw in fm.split("\n"):
        m = _UNQUOTED_DATE_RE.match(raw)
        if m:
            val = m.group("val")
            errors.append(LintError(
                path_str, m.group("key"),
                f"unquoted date {val!r} — quote it (\"{val}\") for round-trip "
                f"stability; run `lint --fix`",
                "warning",
            ))
    return errors


_TAG_VOCAB_CACHE: "set[str] | None | bool" = False  # False = not yet loaded
# Top-level list items only (dash at column 0) so an indented sub-bullet under a
# tag entry can never be mis-captured as a vocabulary tag.
_TAG_LINE_RE = re.compile(r"^-\s+`([a-z0-9][a-z0-9-]*)`")


def load_tag_vocab() -> "set[str] | None":
    """Load the controlled tag vocabulary from research/entities/_tags.md.

    Returns the set of canonical tags, or None when the file is absent (so the
    tag-vocabulary lint gracefully no-ops in a repo / state without it — e.g.
    before the vocabulary lands). Cached after first load.
    """
    global _TAG_VOCAB_CACHE
    if _TAG_VOCAB_CACHE is not False:
        return _TAG_VOCAB_CACHE  # type: ignore[return-value]
    vocab_path = ENTITIES_DIR / "_tags.md"
    if not vocab_path.exists():
        _TAG_VOCAB_CACHE = None
        return None
    vocab: set[str] = set()
    for line in vocab_path.read_text(errors="replace").splitlines():
        m = _TAG_LINE_RE.match(line)
        if m:
            vocab.add(m.group(1))
    _TAG_VOCAB_CACHE = vocab or None
    return _TAG_VOCAB_CACHE  # type: ignore[return-value]


def _lint_tags(path_str: str, fm: dict, type_dir: str) -> list[LintError]:
    """Warn on missing tags, type-redundant tags, type-name tags, and off-vocab tags.

    Non-breaking (all warnings). Distinguishes two type-related cases so the
    message is accurate (P20 nit): a tag equal to THIS entity's own type is
    "redundant with type:"; a tag that is some OTHER entity-type name is invalid
    as a tag (types are encoded by the `type:` field, never as tags). Off-vocab
    is only checked when _tags.md exists. See research/entities/_tags.md.
    """
    errors: list[LintError] = []
    tags = fm.get("tags")
    if not tags or not isinstance(tags, list):
        errors.append(LintError(path_str, "tags", "entity has no tags (≥1 required)", "warning"))
        return errors
    vocab = load_tag_vocab()
    type_names = set(ENTITY_TYPES)
    fm_type = str(fm.get("type", "")).strip()
    for t in tags:
        ts = str(t).strip()
        if not ts:
            continue
        if ts == fm_type or ts == type_dir:
            errors.append(LintError(
                path_str, "tags",
                f"tag {ts!r} is redundant with type: — drop it", "warning"))
        elif ts in type_names:
            errors.append(LintError(
                path_str, "tags",
                f"tag {ts!r} is an entity-type name, not a valid tag "
                "(types are encoded by the type: field) — drop it", "warning"))
        elif vocab is not None and ts not in vocab:
            errors.append(LintError(
                path_str, "tags",
                f"tag {ts!r} not in controlled vocabulary (research/entities/_tags.md)",
                "warning"))
    return errors


_RESOLUTION_HEADING_RE = re.compile(r"^#{1,4}\s+.*(contradiction|resolution)", re.IGNORECASE | re.MULTILINE)


def _lint_contradicts_resolution(path_str: str, fm: dict, body: str) -> list[LintError]:
    """Warn when `contradicts:` is populated but the body has no resolution section.

    Mirrors the entity-schema rule (§ "No entity may have status: entity if
    contradicts is populated without a resolution section"). Only fires on a
    NON-EMPTY contradicts list — an empty `contradicts: []` is fine. Makes the
    typed edge trustworthy rather than implying coverage that isn't documented.

    The detector is a deliberately loose heading heuristic (a `## Contradiction`
    or `## Resolution` heading, H1–H4). Known gaps, accepted because severity is
    `warning`: false-negative on a resolution written without such a heading
    (a `**Resolution:**` bold line or prose), and false-positive on a heading
    that merely mentions the contradiction without resolving it. Tightening would
    trade these for more noise; the warning is a nudge to document, not a proof.
    """
    contradicts = fm.get("contradicts")
    if not isinstance(contradicts, list) or len(contradicts) == 0:
        return []
    if _RESOLUTION_HEADING_RE.search(body):
        return []
    return [LintError(
        path_str, "contradicts",
        f"contradicts is populated ({len(contradicts)} entr"
        f"{'y' if len(contradicts) == 1 else 'ies'}) but no resolution section "
        "(## Contradiction/Resolution) found in body",
        "warning")]


def lint_entity_page(entity_path: Path) -> list[LintError]:
    """
    Validate a single entity page.

    Checks:
    - YAML frontmatter parseable
    - core_claim exists and is ≤140 characters
    - sources is a non-empty list
    - related entries match [[wikilink]] format
    - referenced wikilinks resolve to existing entity slugs
    - frontmatter dates are quoted (round-trip stability)
    """
    errors: list[LintError] = []
    path_str = str(entity_path)

    if not entity_path.exists():
        errors.append(LintError(path_str, "file", "File does not exist", "error"))
        return errors

    text = entity_path.read_text(errors="replace")
    fm, body = parse_frontmatter(text)

    if not fm:
        if not _YAML_AVAILABLE:
            errors.append(LintError(path_str, "yaml", "PyYAML not installed, skipping frontmatter lint", "warning"))
        else:
            errors.append(LintError(path_str, "frontmatter", "Missing or unparseable YAML frontmatter", "error"))
        return errors

    # core_claim
    core_claim = fm.get("core_claim", "")
    # Merge tombstones (status: merged) are NOT content entities — they are
    # promote-skip markers + provenance (BRO-1442). They carry no sources and a
    # fixed pointer core_claim, so the content-field requirements below
    # (core_claim presence/length, non-empty sources) don't apply to them.
    is_tombstone = fm.get("status") == "merged"

    if is_tombstone:
        # Tombstone↔canonical consistency (BRO-1423): the merged-away slug must be
        # an alias on its `merged_into` canonical, else /kg can't route the old
        # name to the canonical (the alias was lost — e.g. a merge-conflict
        # auto-merge dropped it). Warning, not error: the merge still happened.
        merged_into = fm.get("merged_into")
        # Tolerate a `[[canon]]` wikilink form; require a string (BRO-1423 review).
        if isinstance(merged_into, str):
            merged_into = merged_into.strip().strip("[]").strip()
        else:
            merged_into = None
        tomb_slug = fm.get("slug") if isinstance(fm.get("slug"), str) else entity_path.stem
        if merged_into:
            canon_files = [p for p in ENTITIES_DIR.rglob(f"{merged_into}.md")
                           if ".lago-blobs" not in p.parts]
            if not canon_files:
                errors.append(LintError(
                    path_str, "merged_into",
                    f"merged_into '{merged_into}' has no entity file", "warning"))
            else:
                try:
                    cfm, _ = read_frontmatter(canon_files[0])
                    # Case-insensitive: kg routing lowercases aliases (BRO-1423 review).
                    canon_aliases = [a.lower() for a in _catalog_coerce_str_list(cfm.get("aliases"))]
                except Exception:
                    canon_aliases = []
                if tomb_slug.lower() not in canon_aliases:
                    errors.append(LintError(
                        path_str, "merged_into",
                        f"merged into '{merged_into}' but '{tomb_slug}' is not an "
                        f"alias on it — /kg can't route the old name", "warning"))
        else:
            errors.append(LintError(
                path_str, "merged_into",
                "status: merged but no merged_into target", "warning"))

    if not is_tombstone:
        if not core_claim:
            errors.append(LintError(path_str, "core_claim", "core_claim is missing", "error"))
        else:
            if len(str(core_claim)) > 140:
                errors.append(LintError(
                    path_str, "core_claim",
                    f"core_claim is {len(str(core_claim))} chars (max 140)", "error"
                ))
            errors.extend(_lint_core_claim_quality(path_str, core_claim))

        # sources
        sources = fm.get("sources", [])
        if not sources or not isinstance(sources, list):
            errors.append(LintError(path_str, "sources", "sources must be a non-empty list", "error"))

    # status
    valid_statuses = {"candidate", "entity", "synthesis", "raw", "archived", "merged"}
    status = fm.get("status", "")
    if status and status not in valid_statuses:
        errors.append(LintError(
            path_str, "status",
            f"status {status!r} not in {valid_statuses}", "warning"
        ))

    # type
    entity_type = fm.get("type", "")
    if entity_type and entity_type not in ENTITY_TYPES:
        errors.append(LintError(
            path_str, "type",
            f"type {entity_type!r} not in {ENTITY_TYPES}", "warning"
        ))

    # related: must be wikilink format
    related = fm.get("related", [])
    if isinstance(related, list):
        for ref in related:
            if ref and not re.match(r"^\[\[.+\]\]$", str(ref)):
                errors.append(LintError(
                    path_str, "related",
                    f"related entry {ref!r} is not [[wikilink]] format", "error"
                ))

    # Resolve wikilinks in body — skip HTML comment lines to avoid false positives
    wikilinks = extract_wikilinks_md(body)
    existing = set(existing_entity_slugs())
    for target, _edge in wikilinks:
        slug = wikilink_slug(target)
        if slug and slug not in existing:
            errors.append(LintError(
                path_str, "wikilink",
                f"Broken wikilink: [[{target}]] (slug {slug!r} not found)", "warning"
            ))

    # Timeline check (GBrain compiled-truth + timeline pattern): if the page has
    # a `## Timeline` section, each entry should carry a leading ISO date
    # (newest-last, append-only). Undated entries are a WARNING — they break the
    # "what did we believe and when" audit trail. Backward-compatible: pages
    # without a ## Timeline section are unaffected.
    errors.extend(_lint_timeline(path_str, body))

    # Unquoted frontmatter dates re-serialize to full timestamps on edit and
    # break YYYY-MM-DD queries — warn (mechanically auto-fixable via lint --fix).
    errors.extend(_lint_unquoted_dates(path_str, text))

    # Controlled-vocabulary tags: warn on missing / type-redundant / off-vocab
    # tags so rich metadata stays a real routing signal (research/entities/_tags.md).
    errors.extend(_lint_tags(path_str, fm, entity_path.parent.name))

    # Typed contradiction edges must carry a body resolution to be trustworthy.
    errors.extend(_lint_contradicts_resolution(path_str, fm, body))

    return errors


# ── core_claim quality (BRO-1689) ─────────────────────────────────────────────
# A core_claim should be a distilled one-sentence claim. When a research doc is
# mis-promoted (whole-doc-as-body), entities inherit a FRAGMENT as their claim —
# a table row, a section header, a raw-extract preamble. Tier-1 /kg routing scores
# on core_claim, so a fragment claim is a catalog row that never matches a real
# query AND crowds out real entities. These signatures are mechanically detectable;
# clickbait-title claims need human judgment and are deliberately NOT flagged here.
#
# BRO-1983 — the gate must be able to reject the PRODUCER's known failure
# output. Before this, the only length rule was `len(core_claim) <= 140` and
# the producer emitted `body[:137] + "..."` — satisfying the gate by
# construction, so lint could never catch a truncated markdown shard. The
# second block below encodes the producer's actual observed garbage.
_JUNK_CLAIM_PATTERNS: "list[tuple[re.Pattern, str]]" = [
    (re.compile(r"\s\|\s.*\|"), "contains markdown table pipes"),
    (re.compile(r"(?i)\braw extract\b"), "is a raw-extract header"),
    (re.compile(r"^\s*Pathway\s+[A-C]\b"), "is a 'Pathway X' action-item fragment"),
    (re.compile(r"(?i)^\s*bottom line\b"), "is a 'Bottom line' BLUF fragment"),
    (re.compile(r"^\s*\d+\.\d+\s+[A-Za-z]"), "is a numbered section-header fragment"),
    # ── producer-failure signatures ──
    (re.compile(r"(?:\.\.\.|…)\s*$"), "ends in a truncation marker (mid-sentence cut)"),
    (re.compile(r"\*\*"), "contains raw markdown bold — an un-stripped body shard"),
    (re.compile(r"^\s*\(?[A-Za-z0-9]{1,2}\)\s"), "starts with a bare list enumerator"),
    (re.compile(r":\s*\(?[a-z]\)\s"), "splices a label onto an inline list enumerator"),
    (re.compile(r"\bVERIFIED\s+VERDICTS?\b"), "is an ALL-CAPS 'VERIFIED VERDICT' header artifact"),
    (re.compile(r"\bVERDICTS?\b(?=\s*[:—–-]|\s+[A-Z]{2,})"), "is a 'VERDICT:' header artifact"),
    (re.compile(r"^\s*#{1,6}\s"), "is a markdown heading"),
    (re.compile(r"^\s*>\s"), "is a markdown blockquote line"),
    (re.compile(r"^\s*[-*+]\s+\S"), "is a markdown list item"),
]


def _lint_core_claim_quality(path_str: str, core_claim) -> "list[LintError]":
    """Flag core_claims that are mis-promotion artifacts (fragments) rather than a
    distilled claim (BRO-1689). Structural signatures only — see _JUNK_CLAIM_PATTERNS;
    clickbait-title claims need human judgment and are intentionally not flagged."""
    cc = str(core_claim or "").strip()
    if not cc:
        return []  # missing-claim is handled by the caller
    for rx, why in _JUNK_CLAIM_PATTERNS:
        if rx.search(cc):
            return [LintError(
                path_str, "core_claim",
                f"core_claim {why} — mis-promotion artifact, not a distilled claim "
                f"(BRO-1689): {cc[:60]!r}", "error")]
    if _claim_is_allcaps_banner(cc):
        return [LintError(
            path_str, "core_claim",
            "core_claim is an ALL-CAPS header/status banner — mis-promotion artifact, "
            f"not a distilled claim (BRO-1689): {cc[:60]!r}", "error")]
    return []


# Header artifacts SHOUT. A claim carrying a RUN of adjacent ALL-CAPS words is a
# lifted status banner ("VERIFIED VERDICTS", "PARTIAL YES", "REFRAME REQUIRED"),
# not prose. Generalizes past a VERDICT keyword list.
#
# Adjacency (not a bare ratio) plus a length floor is what keeps ordinary
# acronym prose clean: "The HTTP API is versioned" and "GPT-5.4 beats HTML
# rendering" are legitimate claims, and acronyms are almost always ≤4 chars —
# so a run only counts when at least one of its words is ≥5 chars.
_ALLCAPS_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_ALLCAPS_RUN_MIN = 2       # adjacent shouted words needed to call it a banner
_ALLCAPS_PROSE_LEN = 5     # a shouted word this long is prose, not an acronym


def _claim_is_allcaps_banner(cc: str) -> bool:
    """True when `cc` reads as an ALL-CAPS header/status banner rather than prose."""
    run: "list[str]" = []
    for word in _ALLCAPS_WORD_RE.findall(cc):
        if word.isupper():
            run.append(word)
            if len(run) >= _ALLCAPS_RUN_MIN and any(
                len(w) >= _ALLCAPS_PROSE_LEN for w in run
            ):
                return True
        else:
            run = []
    return False


_TIMELINE_HEADING_RE = re.compile(r"^##\s+Timeline\b.*$", re.MULTILINE)
# An entry is a list item (-, *, or N.) whose content starts with an ISO date,
# optionally bold-wrapped (**2026-05-30** …) or bracketed ([2026-05-30] …).
_TIMELINE_DATED_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+[\[*]*\d{4}-\d{2}-\d{2}\b")
_TIMELINE_ENTRY_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S")


def _lint_timeline(path_str: str, body: str) -> list[LintError]:
    """Warn on Timeline entries that lack a leading ISO (YYYY-MM-DD) date.

    Only the lines under a `## Timeline` heading (up to the next `## ` heading
    or EOF) are examined, and only list-item lines count as entries — prose,
    sub-bullets indented under a dated entry, and blank lines are ignored.
    """
    m = _TIMELINE_HEADING_RE.search(body)
    if not m:
        return []
    section = body[m.end():]
    # Stop at the next level-2 (or higher) heading.
    nxt = re.search(r"^#{1,2}\s+\S", section, re.MULTILINE)
    if nxt:
        section = section[:nxt.start()]

    errors: list[LintError] = []
    in_comment = False
    for raw in section.splitlines():
        stripped = raw.strip()
        if "<!--" in stripped and "-->" not in stripped:
            in_comment = True
            continue
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        # Only top-level list items (≤1 indent level) are timeline entries;
        # deeper indentation is detail belonging to the entry above.
        indent = len(raw) - len(raw.lstrip(" "))
        if indent > 2:
            continue
        if not _TIMELINE_ENTRY_RE.match(raw):
            continue
        if not _TIMELINE_DATED_RE.match(raw):
            preview = stripped[:60]
            errors.append(LintError(
                path_str, "timeline",
                f"Timeline entry lacks a leading ISO date (YYYY-MM-DD): {preview!r}",
                "warning",
            ))
    return errors


# ── Opt-in temporal-drift audit ───────────────────────────────────────────────
#
# This audit is deliberately narrower than semantic reconciliation. It catches
# two mechanically defensible conditions:
#   1. `updated` predates newer, valid dated evidence in sources/body.
#   2. Catalog-visible claims, state-labelled headings, or explicit state-label
#      lines make mutable assertions without an inline ISO as-of date.
#
# Arbitrary present-tense prose and generic "Open Questions" sections stay out
# of scope. Deciding whether one claim supersedes another remains P13 review
# work until typed producers exist. Findings are warnings and the audit is only
# run when the caller passes `lint --temporal`.
_TEMPORAL_ISO_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
_TEMPORAL_CLAIM_RE = re.compile(
    r"(?:\b(?:currently|today)\b|"
    r"\b(?:is|are)\s+now\b|"
    r"\b(?:is|are|remains?)\s+(?:now\s+)?"
    r"(?:planned|shipped|resolved|deprecated|superseded|live|active)\b|"
    r"\b(?:is|are)\s+no longer\b|"
    r"\bcurrent (?:state|status|architecture|implementation|behaviou?r)\s+"
    r"(?:is|remains|has)\b)",
    re.IGNORECASE,
)
_TEMPORAL_HEADING_RE = re.compile(
    r"^(?:"
    r"current(?: state|status|architecture|implementation|behaviou?r|version|"
    r"system|stack|path|workflow|mode|decision)|current|today|status|roadmap|"
    r"planned|shipped|resolved|deprecated|superseded|open decisions?|"
    r"open follow-?ups?)"
    r"(?=$|\s*(?:[:—–(\-]))",
    re.IGNORECASE,
)
_TEMPORAL_LABEL_RE = re.compile(
    r"^\s*(?:(?:[-*]|\d+\.)\s+)?(?:\*\*)?"
    r"(?:current(?: state|status|architecture|implementation|behaviou?r|"
    r"version|system|stack|path|workflow|mode|decision)?|currently|today|"
    r"status|open decisions?|open follow-?ups?|planned|shipped|resolved|"
    r"deprecated|superseded|no longer)(?:\*\*)?\s*(?::|—|–|-|\()",
    re.IGNORECASE,
)
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")


def _eligible_temporal_dates(text: str, audit_date: date) -> list[date]:
    """Return valid ISO dates in `text` that are not later than the audit."""
    found: list[date] = []
    for raw in _TEMPORAL_ISO_RE.findall(text):
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            continue
        if parsed <= audit_date:
            found.append(parsed)
    return found


def _coerce_temporal_date(value: object) -> "date | None":
    """Coerce YAML date/datetime/string values to a date, else None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        try:
            return date.fromisoformat(raw)
        except ValueError:
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                return datetime.fromisoformat(raw).date()
            except ValueError:
                return None
    return None


def _first_section_content_line(lines: list[str], start: int) -> str:
    """Return the first non-comment content line before the next heading."""
    in_comment = False
    for line in lines[start:]:
        if _MARKDOWN_HEADING_RE.match(line):
            break
        stripped = line.strip()
        if not stripped:
            continue
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        return line
    return ""


_CANONICAL_WIKILINK_RE = re.compile(r"^\[\[([^\[\]|#]+)\]\]$")


def _default_entity_lookup(slug: str) -> "dict | None":
    """Resolve `slug` to its frontmatter on disk, or None when no file exists.

    Tombstones resolve deliberately: superseding a slug that was merged away is
    the normal case, and reporting it as dangling would flag every merge.
    """
    path = _find_entity_file(slug)
    if path is None:
        return None
    try:
        fm, _ = read_frontmatter(path)
    except Exception:
        return {}
    return fm if isinstance(fm, dict) else {}


def _lint_temporal_envelope(
    path_str: str,
    fm: dict,
    *,
    audit_date: date,
    entity_lookup,
) -> list[LintError]:
    """Warning-only validation of the typed revision envelope (gh-156).

    Validates only what the WRITE path is supposed to guarantee — that stamps
    parse, that a supersession resolves, that it carries an authorizing record,
    and that its timeline runs forwards. It still does not judge whether the
    supersession is CORRECT; that stays a P13 review question.

    Every finding is a warning, and every finding is reachable only via
    `lint --temporal`. Promotion to a hard gate is gated on live-graph
    calibration and an independent cross-review, not on this code existing.
    """
    errors: list[LintError] = []

    recorded_at_raw = fm.get("recorded_at")
    recorded_at = _coerce_temporal_date(recorded_at_raw)
    if recorded_at_raw is not None and recorded_at is None:
        errors.append(LintError(
            path_str, "temporal_recorded_at",
            f"recorded_at {recorded_at_raw!r} is not an ISO date (YYYY-MM-DD)",
            "warning",
        ))
    elif recorded_at is not None and recorded_at > audit_date:
        errors.append(LintError(
            path_str, "temporal_recorded_at",
            f"recorded_at {recorded_at.isoformat()} is in the future — it is "
            f"system time, so it cannot postdate the audit "
            f"({audit_date.isoformat()})",
            "warning",
        ))

    valid_from_raw = fm.get("valid_from")
    if valid_from_raw is not None and _coerce_temporal_date(valid_from_raw) is None:
        errors.append(LintError(
            path_str, "temporal_valid_from",
            f"valid_from {valid_from_raw!r} is not an ISO date (YYYY-MM-DD)",
            "warning",
        ))

    self_slug = fm.get("slug") if isinstance(fm.get("slug"), str) else None
    supersedes_raw = fm.get("supersedes")
    entries: list[object]
    if supersedes_raw is None:
        entries = []
    elif isinstance(supersedes_raw, list):
        entries = list(supersedes_raw)
    else:
        entries = [supersedes_raw]
        errors.append(LintError(
            path_str, "temporal_supersedes",
            f"supersedes must be a list of [[wikilink]] entries, got "
            f"{type(supersedes_raw).__name__}",
            "warning",
        ))

    resolved: list[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            errors.append(LintError(
                path_str, "temporal_supersedes",
                f"supersedes entry {entry!r} is not a string", "warning"))
            continue
        m = _CANONICAL_WIKILINK_RE.match(entry.strip())
        if not m:
            errors.append(LintError(
                path_str, "temporal_supersedes",
                f"supersedes entry {entry!r} is not [[wikilink]] format",
                "warning",
            ))
            continue
        slug = m.group(1).strip()
        if self_slug and slug == self_slug:
            errors.append(LintError(
                path_str, "temporal_supersedes",
                f"supersedes lists its own slug {slug!r} — a record cannot "
                f"supersede itself", "warning",
            ))
            continue
        target_fm = entity_lookup(slug)
        if target_fm is None:
            errors.append(LintError(
                path_str, "temporal_supersedes",
                f"supersedes {slug!r} has no entity file — the superseded "
                f"record is unresolvable", "warning",
            ))
            continue
        resolved.append(slug)
        # A revision that predates what it replaces is a timeline inversion:
        # either the stamps are wrong or the direction of the supersession is.
        target_recorded = _coerce_temporal_date(target_fm.get("recorded_at"))
        if (
            recorded_at is not None
            and target_recorded is not None
            and target_recorded > recorded_at
        ):
            errors.append(LintError(
                path_str, "temporal_supersedes",
                f"supersedes {slug!r} recorded {target_recorded.isoformat()}, "
                f"which is newer than this record's recorded_at "
                f"{recorded_at.isoformat()} — timeline inversion",
                "warning",
            ))

    # `revision_link` is written as a list (one entry per authorizing record) but
    # a hand-authored scalar is accepted; either way it must carry at least one
    # non-blank string.
    revision_link = fm.get("revision_link")
    link_entries = revision_link if isinstance(revision_link, list) else [revision_link]
    has_link = any(
        isinstance(entry, str) and entry.strip() != "" for entry in link_entries)
    # A list where SOME entry is unusable must not pass merely because another
    # one is fine: the writer refuses such a page, so the audit that is supposed
    # to precede the writer has to see it too.
    if revision_link is not None:
        for entry in link_entries:
            # A null MEMBER is checked like any other: the writer rejects it, so
            # the audit that precedes the writer must not wave it through. (A
            # null `revision_link` scalar never reaches here — the guard above
            # treats it as absence, which is what YAML null means.)
            if not isinstance(entry, str):
                errors.append(LintError(
                    path_str, "temporal_revision_link",
                    f"revision_link entry {entry!r} is not a string", "warning"))
            elif entry.strip() == "":
                errors.append(LintError(
                    path_str, "temporal_revision_link",
                    "revision_link contains a blank entry", "warning"))
    if entries and not has_link:
        errors.append(LintError(
            path_str, "temporal_revision_link",
            "supersedes is set without a revision_link — the supersession has "
            "no authorizing record", "warning",
        ))
    # An EMPTY `revision_link: []` alongside an empty `supersedes: []` is a pair
    # of cleared optional fields, not an orphan — there is no link to be
    # orphaned. Only an actual link with nothing to revise is reported.
    if has_link and not entries:
        errors.append(LintError(
            path_str, "temporal_revision_link",
            "revision_link is set with no supersedes — it points at a revision "
            "that revises nothing", "warning",
        ))

    return errors


def _lint_temporal_drift(
    path_str: str,
    fm: dict,
    body: str,
    *,
    audit_date: "date | None" = None,
    entity_lookup=None,
) -> list[LintError]:
    """Emit opt-in, warning-only temporal drift findings for one entity."""
    audit_date = audit_date or date.today()
    errors: list[LintError] = []

    errors.extend(_lint_temporal_envelope(
        path_str, fm,
        audit_date=audit_date,
        entity_lookup=entity_lookup or _default_entity_lookup,
    ))

    updated = _coerce_temporal_date(fm.get("updated"))
    sources = fm.get("sources") or []
    evidence = json.dumps(sources, ensure_ascii=False, default=str) + "\n" + body
    evidence_dates = _eligible_temporal_dates(evidence, audit_date)
    if updated is not None and evidence_dates:
        newest = max(evidence_dates)
        if newest > updated:
            errors.append(LintError(
                path_str,
                "temporal_updated",
                f"frontmatter updated {updated.isoformat()} predates newest dated "
                f"source/body evidence {newest.isoformat()}",
                "warning",
            ))

    core_claim = str(fm.get("core_claim") or "")
    if (
        _TEMPORAL_CLAIM_RE.search(core_claim)
        and not _eligible_temporal_dates(core_claim, audit_date)
    ):
        errors.append(LintError(
            path_str,
            "temporal_as_of",
            "core_claim makes a mutable current-state assertion without an "
            "inline ISO as-of date (YYYY-MM-DD)",
            "warning",
        ))

    lines = body.splitlines()
    for index, line in enumerate(lines):
        heading = _MARKDOWN_HEADING_RE.match(line)
        if heading:
            title = heading.group(1).strip()
            if _TEMPORAL_HEADING_RE.search(title):
                first_content = _first_section_content_line(lines, index + 1)
                dated_context = line + "\n" + first_content
                if not _eligible_temporal_dates(dated_context, audit_date):
                    errors.append(LintError(
                        path_str,
                        "temporal_as_of",
                        f"mutable heading {title!r} lacks an ISO as-of date in "
                        "the heading or first content line",
                        "warning",
                    ))
            continue

        if (
            _TEMPORAL_LABEL_RE.search(line)
            and not _eligible_temporal_dates(line, audit_date)
        ):
            preview = line.strip()[:80]
            errors.append(LintError(
                path_str,
                "temporal_as_of",
                f"mutable state label lacks an inline ISO as-of date: {preview!r}",
                "warning",
            ))

    return errors


def _lint_temporal_entity_page(
    entity_path: Path,
    *,
    audit_date: "date | None" = None,
) -> list[LintError]:
    """Read one entity and run the opt-in temporal audit when parseable."""
    if not entity_path.exists():
        return []
    fm, body = parse_frontmatter(entity_path.read_text(errors="replace"))
    if not fm:
        return []
    return _lint_temporal_drift(
        str(entity_path), fm, body, audit_date=audit_date,
    )


def _lint_temporal_all(verbose: bool = False) -> list[LintError]:
    """Run the opt-in temporal audit across real entity pages."""
    if not ENTITIES_DIR.exists():
        return []
    errors: list[LintError] = []
    pages = [
        page for page in ENTITIES_DIR.rglob("*.md")
        if page.name != "_tags.md" and ".lago-blobs" not in page.parts
    ]
    if verbose:
        print(f"[lint --temporal] Checking {len(pages)} entity pages...")
    for page in pages:
        page_errors = _lint_temporal_entity_page(page)
        errors.extend(page_errors)
        if verbose:
            for error in page_errors:
                print(
                    f"  [WARNING] {page.name}: {error.field} — {error.message}"
                )
    return errors


# ── Lint --fix: mechanical auto-repair (Fix 2) ─────────────────────────────────
#
# Only the unambiguous, mechanical `related:` format classes are auto-repaired:
#   - bare slug                 →  "[[slug]]"
#   - path-form (foo/bar.md)    →  "[[bar]]"   (basename, no .md)
# core_claim length and missing core_claim are NEVER auto-edited — those need
# human judgment and are reported as before. The repair is idempotent: a value
# already in [[wikilink]] form is left untouched.


def _canonicalize_related_value(raw: str) -> Optional[str]:
    """
    Map a single `related:` entry to canonical `[[slug]]` form.

    Returns the canonical string, or None when the value is NOT a mechanical
    fix class (so the caller leaves it untouched and reports it for manual
    repair). Already-canonical `[[...]]` values return themselves unchanged
    (so the operation is idempotent).

    Fix classes (mechanical, unambiguous):
      - bare slug  ("foo-bar")                  → "[[foo-bar]]"
      - path-form  ("a/b/foo.md", "foo.md")     → "[[foo]]"  (basename, no .md)
    """
    val = raw.strip().strip('"').strip("'").strip()
    if not val:
        return None
    # Already a wikilink → idempotent no-op (still "fixable class", but no change).
    if re.match(r"^\[\[.+\]\]$", val):
        return val
    # Reject values with internal whitespace or wikilink brackets — not a
    # clean slug/path token, so not a mechanical fix.
    if any(c in val for c in (" ", "\t", "[", "]", "|")):
        return None
    # Path-form: strip directory components and a trailing .md/.markdown.
    base = val.rsplit("/", 1)[-1]
    base = re.sub(r"\.(?:md|markdown)$", "", base, flags=re.IGNORECASE)
    base = base.strip()
    if not base:
        return None
    return f"[[{base}]]"


def fix_entity_page(entity_path: Path, dry_run: bool = False) -> tuple[int, list[str]]:
    """
    Auto-repair mechanical `related:` format violations in an entity page.

    Operates on the raw frontmatter text (not the parsed dict) so that every
    byte outside the `related:` block is preserved exactly — only offending
    list-item values are rewritten. Handles both block form

        related:
          - foo
          - a/b/bar.md

    and inline-flow form

        related: [foo, a/b/bar.md]

    Returns (num_fixed, unfixable_values) where unfixable_values are related
    entries that are malformed but not a mechanical fix class (reported, not
    edited). Idempotent: a file with only canonical `[[...]]` entries yields
    (0, []) and is not rewritten.
    """
    if not entity_path.exists():
        return 0, []
    text = entity_path.read_text(errors="replace")
    fm_match = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)", text, re.DOTALL)
    if not fm_match:
        return 0, []

    head, fm_text, tail = fm_match.group(1), fm_match.group(2), fm_match.group(3)
    fm_lines = fm_text.split("\n")
    out_lines: list[str] = []
    fixed = 0
    unfixable: list[str] = []

    i = 0
    n = len(fm_lines)
    while i < n:
        line = fm_lines[i]

        # ── Inline-flow form: related: [a, b, c] ──
        inline = re.match(r"^(related:\s*)\[(.*)\]\s*$", line)
        if inline:
            prefix, inner = inline.group(1), inline.group(2)
            if inner.strip() == "":
                out_lines.append(line)  # related: [] — nothing to fix
                i += 1
                continue
            new_items: list[str] = []
            for raw_item in inner.split(","):
                canon = _canonicalize_related_value(raw_item)
                stripped = raw_item.strip().strip('"').strip("'").strip()
                if canon is None:
                    unfixable.append(stripped)
                    new_items.append(raw_item.strip())  # leave as-is
                else:
                    if canon != stripped:
                        fixed += 1
                    # Quote so the [[ ]] survives YAML flow parsing.
                    new_items.append(f'"{canon}"')
            out_lines.append(f"{prefix}[{', '.join(new_items)}]")
            i += 1
            continue

        # ── Block form: related: \n   - item \n   - item ──
        if re.match(r"^related:\s*$", line):
            out_lines.append(line)
            i += 1
            # Consume the indented list items that belong to this block.
            while i < n:
                item_m = re.match(r"^(\s+)-\s+(.*?)\s*$", fm_lines[i])
                if not item_m:
                    break
                indent, raw_item = item_m.group(1), item_m.group(2)
                canon = _canonicalize_related_value(raw_item)
                stripped = raw_item.strip().strip('"').strip("'").strip()
                if canon is None:
                    unfixable.append(stripped)
                    out_lines.append(fm_lines[i])  # leave untouched
                else:
                    if canon != stripped:
                        fixed += 1
                    out_lines.append(f'{indent}- "{canon}"')
                i += 1
            continue

        out_lines.append(line)
        i += 1

    if fixed == 0:
        return 0, unfixable

    new_text = head + "\n".join(out_lines) + tail + text[fm_match.end():]
    if not dry_run:
        entity_path.write_text(new_text)
    return fixed, unfixable


def fix_unquoted_dates(entity_path: Path, dry_run: bool = False) -> int:
    """
    Quote unquoted ISO-date scalars in an entity page's frontmatter.

    A sibling of fix_entity_page (which handles `related:` format): this pass is
    scoped to the unquoted-date class only — `updated: 2026-05-30` →
    `updated: "2026-05-30"`. Kept separate so fix_entity_page's related-only
    contract (and its tests) stay intact. Operates on the raw frontmatter text so
    content outside a matched date line is preserved (subject to the usual LF
    newline normalization on rewrite); a trailing comment on a fixed line is kept.
    Idempotent: already-quoted dates yield 0 and the file is not rewritten. See
    research/notes/2026-06-08-frontmatter-best-practices-synthesis.md.
    """
    if not entity_path.exists():
        return 0
    text = entity_path.read_text(errors="replace")
    fm_match = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)", text, re.DOTALL)
    if not fm_match:
        return 0
    head, fm_text, tail = fm_match.group(1), fm_match.group(2), fm_match.group(3)
    out_lines: list[str] = []
    fixed = 0
    for line in fm_text.split("\n"):
        dm = _UNQUOTED_DATE_RE.match(line)
        if dm:
            rest = dm.group("rest")
            trailing = rest if rest.strip() else ""  # preserve trailing comment only
            new_line = f'{dm.group("indent")}{dm.group("key")}: "{dm.group("val")}"{trailing}'
            if new_line != line:
                fixed += 1
            out_lines.append(new_line)
        else:
            out_lines.append(line)

    if fixed == 0:
        return 0
    new_text = head + "\n".join(out_lines) + tail + text[fm_match.end():]
    if not dry_run:
        entity_path.write_text(new_text)
    return fixed


def fix_all(dry_run: bool = False, verbose: bool = False) -> tuple[int, int, list[str]]:
    """
    Run fix_entity_page (related: format) + fix_unquoted_dates across all pages.

    Returns (files_fixed, total_items_fixed, unfixable_values). Only files
    that had at least one mechanical fix applied are counted in files_fixed.
    """
    files_fixed = 0
    total_fixed = 0
    all_unfixable: list[str] = []
    if not ENTITIES_DIR.exists():
        return 0, 0, []
    for page in sorted(ENTITIES_DIR.rglob("*.md")):
        n_fixed, unfixable = fix_entity_page(page, dry_run=dry_run)
        n_dates = fix_unquoted_dates(page, dry_run=dry_run)
        n_fixed += n_dates
        all_unfixable.extend(unfixable)
        if n_fixed > 0:
            files_fixed += 1
            total_fixed += n_fixed
            if verbose:
                rel = page.relative_to(BROOMVA_ROOT) if str(page).startswith(str(BROOMVA_ROOT)) else page
                parts = []
                n_related = n_fixed - n_dates
                if n_related:
                    parts.append(f"{n_related} related")
                if n_dates:
                    parts.append(f"{n_dates} date{'s' if n_dates != 1 else ''}")
                print(f"  [fix] {rel}: {', '.join(parts)} repaired")
    return files_fixed, total_fixed, all_unfixable


def lint_all(verbose: bool = False) -> list[LintError]:
    """Run lint_entity_page on all entity pages and lint_format_discernment on research/."""
    all_errors: list[LintError] = []
    if ENTITIES_DIR.exists():
        pages = list(ENTITIES_DIR.rglob("*.md"))
        if verbose:
            print(f"[lint] Checking {len(pages)} entity pages...")
        for page in pages:
            errs = lint_entity_page(page)
            all_errors.extend(errs)
            if verbose and errs:
                for e in errs:
                    print(f"  [{e.severity.upper()}] {Path(e.file_path).name}: {e.field} — {e.message}")
    # Format-discernment checks run on research/ tree (parent of entities/)
    research_dir = ENTITIES_DIR.parent if ENTITIES_DIR.exists() else Path("research")
    if research_dir.exists():
        fd_errors = lint_format_discernment(research_dir)
        all_errors.extend(fd_errors)
        if verbose and fd_errors:
            for e in fd_errors:
                print(f"  [{e.severity.upper()}] {Path(e.file_path).name}: {e.field} — {e.message}")
    return all_errors


def lint_format_discernment(root: Path) -> list[LintError]:
    """
    Format-discernment lint checks (P17, see SKILL.md "Format Discernment").

    Implements all four belt-and-suspenders checks:
      - stale_projection: <note>.md mtime > <note>.html mtime → warn
      - broken_canonical: HTML projection's canonical: points to a missing
        file OR outside the sibling directory → error
      - substrate_violation: non-MD file under entities/ → error (Category A
        is MD-only)
      - unregistered_c: HTML under notes/ with no frontmatter AND no sibling
        MD → warn (can't be located in the knowledge graph)
    """
    errors: list[LintError] = []
    if not root.exists():
        return errors
    for html_path in root.rglob("*.html"):
        # 1. stale_projection
        md_path = html_path.with_suffix(".md")
        if md_path.exists() and md_path.stat().st_mtime > html_path.stat().st_mtime:
            errors.append(LintError(
                str(html_path),
                "stale_projection",
                f"{md_path.name} is newer than {html_path.name} — "
                f"rerun `bookkeeping render` to refresh",
                "warning",
            ))
        # 2. broken_canonical
        try:
            fm, _ = parse_html_frontmatter(html_path.read_text(errors="replace"))
        except Exception:
            fm = {}
        canonical = fm.get("canonical")
        if canonical:
            # Resolve canonical relative to the HTML file's directory
            target = (html_path.parent / canonical).resolve()
            if not target.exists():
                errors.append(LintError(
                    str(html_path),
                    "broken_canonical",
                    f"canonical: {canonical!r} does not exist relative to {html_path.parent}",
                    "error",
                ))
            elif target.parent != html_path.parent.resolve():
                errors.append(LintError(
                    str(html_path),
                    "broken_canonical",
                    f"canonical: {canonical!r} resolves outside sibling directory "
                    f"({target.parent} != {html_path.parent.resolve()})",
                    "error",
                ))
    # 3. substrate_violation: Category A = MD only under entities/
    # Skip hidden infrastructure dirs (e.g. .lago-blobs/) and hidden files —
    # those are storage substrate, not entity substrate.
    entities_dir = root / "entities"
    if entities_dir.exists():
        for path in entities_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in (".md", ".markdown"):
                continue
            rel = path.relative_to(entities_dir)
            if any(part.startswith(".") for part in rel.parts):
                continue
            errors.append(LintError(
                str(path),
                "substrate_violation",
                f"Non-MD file under entities/ — Category A is MD-only "
                f"(P17 Format Discernment Discipline)",
                "error",
            ))
    # 4. unregistered_c: .html under notes/ with no frontmatter AND no sibling .md
    notes_dir = root / "notes"
    if notes_dir.exists():
        for html_path in notes_dir.rglob("*.html"):
            try:
                fm, _ = parse_html_frontmatter(html_path.read_text(errors="replace"))
            except Exception:
                fm = {}
            md_sibling = html_path.with_suffix(".md")
            if not fm and not md_sibling.exists():
                errors.append(LintError(
                    str(html_path),
                    "unregistered_c",
                    f"HTML artifact under notes/ has no frontmatter AND no sibling MD — "
                    f"declare frontmatter (Category C) or add MD source (Category B)",
                    "warning",
                ))
    return errors


# ── Full Pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(
    source_files: list[Path] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Execute the full 7-stage bookkeeping pipeline.

    Returns a run log entry dict with pipeline statistics.
    """
    start_time = time.time()
    run_id = int(time.time())

    ensure_dirs()

    # ── Auto-discover sources if none given ──
    if not source_files:
        source_files = discover_raw_extracts()
        if verbose:
            print(f"[run] Auto-discovered {len(source_files)} raw extract files")

    if not source_files:
        print("[run] No source files found. Use --source or add raw extracts to research/notes/")
        return {}

    existing_slugs = existing_entity_slugs()
    slug_types = existing_entity_slug_types()

    # Stage counters
    items_ingested = 0
    items_scored = 0
    items_promoted = 0
    items_discarded = 0
    items_raw_only = 0
    entities_created = 0
    entities_updated = 0
    scoring_breakdown = {"heuristic": 0, "llm_judge": 0}

    all_scored: list[ScoredItem] = []

    # ── Stage 1+2+3+4: Ingest → Score → Scatter → Resolve ──
    for src in source_files:
        if verbose:
            print(f"\n[run] Processing: {src.name}")

        raw_items = ingest_file(src, verbose=verbose)
        items_ingested += len(raw_items)

        for item in raw_items:
            scored = score_item(item, existing_slugs, verbose=verbose)
            scoring_breakdown[scored.scoring_method] = (
                scoring_breakdown.get(scored.scoring_method, 0) + 1
            )
            items_scored += 1

            if scored.total <= DISCARD_THRESHOLD:
                items_discarded += 1
                if verbose:
                    print(f"  [{item.item_id}] DISCARD score={scored.total}/9")
                continue

            candidates = scatter(scored, verbose=verbose)
            resolved = resolve_candidates(
                candidates, existing_slugs, verbose=verbose,
                item=item, slug_types=slug_types,
            )

            if not resolved:
                items_raw_only += 1
                if verbose:
                    print(f"  [{item.item_id}] no candidates → raw-only")
                continue

            # A body with no derivable complete claim cannot become an entity
            # page (BRO-1983). Filter here so the run counters stay honest —
            # promote_item guards again, but by then it is already "promoted".
            if derive_core_claim(item.content) is None:
                items_raw_only += 1
                if verbose:
                    print(f"  [{item.item_id}] no complete core_claim → raw-only")
                continue

            all_scored.append(scored)

    # ── Stage 5: Promote ──
    print(f"\n[run] Promoting {len(all_scored)} items (threshold ≥{PROMOTE_THRESHOLD})...")
    for scored in all_scored:
        if scored.total < PROMOTE_THRESHOLD:
            items_raw_only += 1
            continue

        candidates = scatter(scored)
        resolved = resolve_candidates(
            candidates, existing_slugs, item=scored.item, slug_types=slug_types
        )
        if not resolved:
            items_raw_only += 1
            continue

        # ONE item carries ONE core_claim, so it can support at most ONE entity
        # page. This was `resolved[:2]`, which minted a second page from the
        # SAME `scored` object — identical core_claim, identical evidence,
        # identical source, differing only in slug and title. The second slug is
        # by construction the LESS central candidate, so its title described
        # something the claim was not about: `groq-compound` and `hugging-face`
        # both ended up asserting a fact about Firecracker; `prompt-sampler` and
        # `spaces` both carried an evolutionary-LLM-optimizer claim. Measured on
        # the live graph (BRO-1990): 20 committed pages in 10 such pairs, plus
        # 23 of 27 pages from one scheduled run whose claim was not about their
        # own slug.
        #
        # `cmd_promote` (the single-file path) already used `resolved[:1]`; only
        # the pipeline path fanned out, so the two entry points disagreed about
        # the same invariant. Relationships between entities belong in `related:`
        # edges, never in a duplicated claim on a second page.
        for slug, is_existing in resolved[:1]:
            path = promote_item(scored, slug, dry_run=dry_run, verbose=verbose)
            if is_existing:
                # promote_item returns the path only when a substantive
                # update was written (or, in dry-run, would be written);
                # a no-op date-bump returns None and is NOT counted.
                if path is not None:
                    entities_updated += 1
            else:
                # Create case: a brand-new entity is always a write. In
                # dry-run, promote_item returns None for creates by design,
                # so fall back to dry_run to keep the preview count accurate.
                if path is not None or dry_run:
                    entities_created += 1
                    existing_slugs.append(slug)
                    # Keep slug_types in step with existing_slugs. It is
                    # snapshotted once before the loop, so without this an
                    # entity created EARLIER IN THE SAME RUN is visible to
                    # exact matching but invisible to the fuzzy type guard —
                    # a later near-miss candidate fails the type check and
                    # mints a near-duplicate page, which is the very failure
                    # mode this gate exists to prevent.
                    slug_types.setdefault(slug, set()).add(
                        _infer_entity_type(slug, scored.item)
                    )

        items_promoted += 1

    # ── Stage 6: Synthesize ──
    synthesis_candidates = find_synthesis_candidates(verbose=verbose)
    if synthesis_candidates and verbose:
        print(f"\n[run] Synthesis candidates: {len(synthesis_candidates)}")
        for c in synthesis_candidates[:5]:
            print(f"  topic={c['topic']!r} entities={c['entity_count']}")

    # ── Stage 7: Lint ──
    lint_errors = lint_all(verbose=verbose)
    lint_error_count = len([e for e in lint_errors if e.severity == "error"])

    duration = round(time.time() - start_time, 2)

    entry = {
        "run_id": run_id,
        "timestamp": now_iso(),
        "source_files": [str(s) for s in source_files],
        "items_ingested": items_ingested,
        "items_scored": items_scored,
        "items_promoted": items_promoted,
        "items_discarded": items_discarded,
        "items_raw_only": items_raw_only,
        "entities_created": entities_created,
        "entities_updated": entities_updated,
        "synthesis_candidates": len(synthesis_candidates),
        "lint_errors": lint_error_count,
        "scoring_breakdown": scoring_breakdown,
        "duration_seconds": duration,
    }

    if not dry_run:
        log_run(entry)
        # Update status cache
        _refresh_status_cache()

    print(f"\n[run] Done in {duration}s")
    print(f"  Ingested: {items_ingested} | Scored: {items_scored} | Promoted: {items_promoted}")
    print(f"  Discarded: {items_discarded} | Raw-only: {items_raw_only}")
    print(f"  Entities created: {entities_created} | Updated: {entities_updated}")
    print(f"  Synthesis candidates: {len(synthesis_candidates)} | Lint errors: {lint_error_count}")
    if dry_run:
        print("  [DRY RUN] No files written.")

    return entry


# ── Status ────────────────────────────────────────────────────────────────────

def _refresh_status_cache() -> dict:
    """Recompute entity graph stats and write to status cache."""
    stats: dict = {
        "total_entities": 0,
        "by_type": {},
        "by_status": {},
        "recent_promotions_7d": 0,
        "lint_errors": 0,
        "last_run": None,
    }

    if ENTITIES_DIR.exists():
        for et in ENTITY_TYPES:
            type_dir = ENTITIES_DIR / et
            if not type_dir.exists():
                continue
            pages = list(type_dir.glob("*.md"))
            stats["by_type"][et] = len(pages)
            stats["total_entities"] += len(pages)

            cutoff = datetime.now() - timedelta(days=7)
            for p in pages:
                mtime = datetime.fromtimestamp(p.stat().st_mtime)
                if mtime >= cutoff:
                    stats["recent_promotions_7d"] += 1

                # Count by status
                text = p.read_text(errors="replace")
                fm, _ = parse_frontmatter(text)
                status = fm.get("status", "unknown") if fm else "unknown"
                stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

    if RUN_LOG.exists():
        lines = RUN_LOG.read_text().strip().splitlines()
        if lines:
            try:
                last = json.loads(lines[-1])
                stats["last_run"] = last.get("timestamp")
                stats["lint_errors"] = last.get("lint_errors", 0)
            except Exception:
                pass

    update_status_cache(stats)
    return stats


def run_status() -> None:
    """Print a formatted knowledge graph status report."""
    # Try cached stats first
    stats: dict = {}
    if STATUS_CACHE.exists():
        try:
            stats = json.loads(STATUS_CACHE.read_text())
        except Exception:
            pass

    if not stats:
        stats = _refresh_status_cache()

    total = stats.get("total_entities", 0)
    by_type = stats.get("by_type", {})
    by_status = stats.get("by_status", {})
    recent = stats.get("recent_promotions_7d", 0)
    lint_errors = stats.get("lint_errors", 0)
    last_run = stats.get("last_run", "never")
    updated_at = stats.get("updated_at", "?")

    print("\nKnowledge Graph Status")
    print("=" * 40)
    print(f"Total entities: {total}")

    type_parts = " | ".join(f"{t}: {by_type.get(t, 0)}" for t in ENTITY_TYPES if by_type.get(t, 0) > 0)
    if type_parts:
        print(f"  {type_parts}")

    status_parts = " | ".join(f"{s}: {c}" for s, c in sorted(by_status.items()))
    if status_parts:
        print(f"Status breakdown: {status_parts}")

    print(f"Recent promotions (last 7 days): {recent}")
    print(f"Lint errors: {lint_errors}")
    print(f"Last run: {last_run}")
    print(f"Cache updated: {updated_at}")

    # Show recent run log entries
    if RUN_LOG.exists():
        lines = RUN_LOG.read_text().strip().splitlines()
        if lines:
            print(f"\nRecent runs ({min(3, len(lines))} of {len(lines)}):")
            for line in lines[-3:]:
                try:
                    r = json.loads(line)
                    ts = r.get("timestamp", "?")[:19]
                    print(
                        f"  {ts} | "
                        f"ingested={r.get('items_ingested',0)} "
                        f"promoted={r.get('items_promoted',0)} "
                        f"created={r.get('entities_created',0)} "
                        f"({r.get('duration_seconds',0)}s)"
                    )
                except Exception:
                    pass


# ── Query ─────────────────────────────────────────────────────────────────────

def run_query(slug: str, verbose: bool = False) -> None:
    """Find and display an entity page by slug (fuzzy matched)."""
    if not ENTITIES_DIR.exists():
        print(f"[query] No entities directory at {ENTITIES_DIR}")
        return

    all_pages: dict[str, Path] = {}
    for et in ENTITY_TYPES:
        type_dir = ENTITIES_DIR / et
        if type_dir.exists():
            for p in type_dir.glob("*.md"):
                all_pages[p.stem] = p

    if not all_pages:
        print("[query] No entity pages found.")
        return

    # Exact match first
    if slug in all_pages:
        path = all_pages[slug]
    else:
        # Fuzzy match
        matches = difflib.get_close_matches(slug, list(all_pages.keys()), n=3, cutoff=0.5)
        if not matches:
            print(f"[query] No entity found for {slug!r}")
            print(f"  Available ({len(all_pages)}): {', '.join(list(all_pages.keys())[:10])}...")
            return
        if len(matches) == 1 or matches[0] == slug:
            path = all_pages[matches[0]]
        else:
            print(f"[query] Multiple matches for {slug!r}:")
            for m in matches:
                print(f"  {m} ({_display_path(all_pages[m])})")
            path = all_pages[matches[0]]
            print(f"  → Showing {matches[0]}")

    print(f"\n{_display_path(path)}")
    print("─" * 60)
    print(path.read_text())


# ── CLI Subcommands ───────────────────────────────────────────────────────────

def cmd_run(args: argparse.Namespace) -> None:
    """Execute the full 7-stage pipeline."""
    sources: list[Path] | None = None
    if args.source:
        sources = [Path(args.source)]
        if not sources[0].exists():
            print(f"ERROR: {args.source} not found", file=sys.stderr)
            sys.exit(1)

    run_pipeline(
        source_files=sources,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


def cmd_ingest(args: argparse.Namespace) -> None:
    """Normalize a single file and print JSON to stdout."""
    path = Path(args.source)
    items = ingest_file(path, verbose=args.verbose)
    print(json.dumps([asdict(i) for i in items], indent=2))


def cmd_score(args: argparse.Namespace) -> None:
    """Score all items in a raw extract file and print results."""
    path = Path(args.file)
    items = ingest_file(path, verbose=args.verbose)
    existing = existing_entity_slugs()
    results = []
    for item in items:
        scored = score_item(item, existing, verbose=args.verbose)
        results.append({
            "item_id": item.item_id,
            "content_preview": item.content[:80],
            "novelty": scored.novelty,
            "specificity": scored.specificity,
            "relevance": scored.relevance,
            "total": scored.total,
            "promote": scored.promote,
            "method": scored.scoring_method,
            "candidates": scored.candidate_entities,
        })

    for r in results:
        promote_str = "PROMOTE" if r["promote"] else "discard"
        print(
            f"[{r['item_id']}] {r['total']}/9 "
            f"(n={r['novelty']} s={r['specificity']} r={r['relevance']}) "
            f"[{r['method']}] → {promote_str}"
        )
        print(f"  {r['content_preview']!r}")
        if r["candidates"]:
            print(f"  candidates: {r['candidates']}")


def cmd_promote(args: argparse.Namespace) -> None:
    """Promote pending items (score ≥ threshold) from a raw extract to entity pages."""
    path = Path(args.file)
    items = ingest_file(path, verbose=args.verbose)
    existing = existing_entity_slugs()
    slug_types = existing_entity_slug_types()
    ensure_dirs()

    promoted = 0
    for item in items:
        scored = score_item(item, existing, verbose=args.verbose)
        if scored.total < PROMOTE_THRESHOLD:
            if args.verbose:
                print(f"  SKIP [{item.item_id}] score={scored.total}/9 < {PROMOTE_THRESHOLD}")
            continue

        candidates = scatter(scored, verbose=args.verbose)
        resolved = resolve_candidates(
            candidates, existing, verbose=args.verbose,
            item=item, slug_types=slug_types,
        )
        if not resolved:
            print(f"  [{item.item_id}] no entity candidates, skipping")
            continue

        if derive_core_claim(item.content) is None:
            print(f"  [{item.item_id}] no complete core_claim derivable, skipping")
            continue

        for slug, is_existing in resolved[:1]:
            promote_item(scored, slug, dry_run=args.dry_run, verbose=True)
            if not is_existing:
                existing.append(slug)
                # Same snapshot-vs-growing-list hazard as the run_pipeline
                # create branch: slug_types is built once before the loop, so a
                # slug created earlier in this run must be registered here or
                # the fuzzy type guard cannot see it.
                slug_types.setdefault(slug, set()).add(
                    _infer_entity_type(slug, scored.item)
                )
        promoted += 1

    print(f"\n[promote] Done: {promoted} items promoted from {path.name}")
    if args.dry_run:
        print("[promote] DRY RUN — no files written")


def cmd_replay(args: argparse.Namespace) -> None:
    """Replay scoring/promotion against a frozen snapshot of `research/entities/`.

    Closes the corruption mode where bookkeeping reads from the same graph it
    writes to (the "shadow dream" failure described in the multi-tier-dreaming
    research entity). Replay phase = run the full pipeline against a frozen
    copy, generate a diff, surface it for review. Promotion to the live graph
    requires explicit `--commit`.

    Five-phase shape (per multi-tier-dreaming entity):
      1. Gather   — read the source file as the dense lower-tier signal
      2. Replay   — score+promote against a FROZEN copy of research/entities/
      3. Prune    — items below threshold or failing lint are flagged
      4. Consolidate — `--commit` mode applies the diff to the live graph
      5. Index    — git diff output is the audit trail of what changed

    Without --commit, replay is a pure read operation: it copies entities to
    a tempdir, runs scoring against that copy, and prints the proposed diff.
    With --commit, replay re-runs the same logic against the LIVE graph (so
    the diff applies to the same starting state the human approved).
    """
    import shutil
    import tempfile

    source_path = Path(args.source) if args.source else None
    if source_path and not source_path.exists():
        print(f"ERROR: {source_path} not found", file=sys.stderr)
        sys.exit(1)

    live_entities = ENTITIES_DIR
    if not live_entities.exists():
        print(f"ERROR: {live_entities} not found", file=sys.stderr)
        sys.exit(1)

    # Phase 1: Gather (which sources are we replaying?)
    if source_path:
        sources = [source_path]
    else:
        sources = list(NOTES_DIR.glob("*-raw.md"))
        sources = [p for p in sources if p.is_file()]
        if not sources:
            print("[replay] no raw extract files in research/notes/", file=sys.stderr)
            sys.exit(0)

    print(f"[replay] Phase 1 (Gather): {len(sources)} source file(s)")
    for s in sources[:5]:
        try:
            print(f"  - {s.relative_to(BROOMVA_ROOT)}")
        except ValueError:
            print(f"  - {s}")
    if len(sources) > 5:
        print(f"  ... +{len(sources) - 5} more")

    # Phase 2: Replay against frozen substrate
    with tempfile.TemporaryDirectory(prefix="bookkeeping-replay-") as tmpdir:
        frozen_root = Path(tmpdir)
        frozen_entities = frozen_root / "research" / "entities"
        frozen_entities.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(live_entities, frozen_entities)
        print(f"\n[replay] Phase 2 (Replay): froze {sum(1 for _ in frozen_entities.rglob('*.md'))} entity files at {frozen_entities}")

        # Track what would change in the replay world (but don't actually
        # write to it — we use existing_entity_slugs() against the frozen
        # state for collision detection, and report counts only).
        existing_frozen = sorted(p.stem for p in frozen_entities.rglob("*.md"))

        promoted = 0
        skipped = 0
        scores = []
        for src in sources:
            try:
                items = ingest_file(src, verbose=args.verbose)
            except Exception as e:
                print(f"  ! ingest failed for {src.name}: {e}", file=sys.stderr)
                continue
            for item in items:
                try:
                    scored = score_item(item, existing_frozen, verbose=False)
                except Exception as e:
                    print(f"  ! score failed for {item.item_id}: {e}", file=sys.stderr)
                    continue
                scores.append(scored.total)
                if scored.total < PROMOTE_THRESHOLD:
                    skipped += 1
                    continue
                # Would-promote: simulate without writing
                promoted += 1
                if args.verbose:
                    # ScoredItem carries `candidate_entities`, never a
                    # `suggested_slug` field — the old attribute raised
                    # AttributeError on every `replay --verbose` run.
                    _cands = scored.candidate_entities or ["(no candidate)"]
                    print(f"  WOULD-PROMOTE [{item.item_id}] score={scored.total}/9 → {_cands[0]}")

        print(f"\n[replay] Phase 3 (Prune): {skipped} item(s) below threshold; {promoted} would-promote")
        if scores:
            print(f"          score distribution: min={min(scores)} max={max(scores)} mean={sum(scores)/len(scores):.1f}")

    # Phase 4: Consolidate (--commit only)
    if args.commit:
        print(f"\n[replay] Phase 4 (Consolidate): --commit set; running pipeline against LIVE graph")
        run_pipeline(
            source_files=sources,
            dry_run=False,
            verbose=args.verbose,
        )
        # Phase 5: Index (the agent / user inspects git diff to verify)
        print(f"\n[replay] Phase 5 (Index): inspect `git diff research/entities/` for the audit trail")
    else:
        print(f"\n[replay] Phase 4 (Consolidate): SKIPPED — pass --commit to apply the diff to the live graph")
        print(f"          to inspect what would change without committing, run:")
        print(f"            bookkeeping run --dry-run --source <file>")


# ── GBrain knowledge primitives (BRO-1246) ─────────────────────────────────────
#
# Three capabilities that turn the bookkeeping engine from a *write* pipeline
# into a self-measuring, self-diagnosing knowledge graph:
#
#   1. `bench`              — retrieval benchmark (P@k / R@k / MRR) over the same
#                            two-tier algorithm the `kg` load skill uses. Answers
#                            "is the catalog + body-grep retrieval any good?".
#   2. `synthesize --gaps` — gap analysis: unresolved wikilinks, missing/over-long
#                            core_claim, and highly-referenced stubs. Gaps are
#                            candidate research questions (goal-formation, Pillar 2).
#   3. `lint --health`     — a 0-100 health score + dependency-ordered remediation
#                            plan (broken-link targets first — highest leverage).
#
# All three read the SAME substrate the live system reads (research/entities/ +
# docs/knowledge-index.md), so the numbers describe the real graph, not a mock.

CATALOG_PATH = _RESOLVED_CATALOG_PATH  # resolved at module load (repo-native)
BENCH_LATEST = CONFIG_DIR / "bench-latest.json"

# Stopwords for query tokenization — mirrors kg.py's tokenize_topic so the
# benchmark measures the exact retrieval the kg load skill performs.
_BENCH_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "with", "as", "is", "are", "was", "were", "be", "been", "do", "does", "did",
    "from", "by", "at", "what", "how", "why", "when", "where", "all", "any",
    "this", "that", "these", "those", "i", "you", "we", "they", "it", "its",
    "their", "them", "us", "our",
}


@dataclass
class _CatalogEntry:
    """One parsed entity block from docs/knowledge-index.md (catalog v1/v2).

    Carries the same parsed fields kg.py's CatalogEntry does (slug, type,
    status, claim, links, tags, sources, rel_path) so tier-1 scoring is
    identical. Two intentional differences from kg.py: this class adds
    `entity_id()` (the `type/slug` label space the fixture grades against),
    and it omits kg's `score`/`raw_block` fields (unused by the metrics). The
    identity-model divergence is documented on `retrieve()`.
    """
    slug: str
    type: str = ""
    status: str = ""
    claim: str = ""
    out_links: list = field(default_factory=list)
    in_links: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    rel_path: str = ""  # path relative to research/entities/ (v2: "concept/foo.md")

    def entity_id(self) -> str:
        """Return the canonical `type/slug` id used by the benchmark fixture.

        Prefers the catalog's explicit `path:` (v2) — strips the trailing
        `.md` so `concept/foo.md` → `concept/foo`. Falls back to
        `<type>/<slug>` when the path line is absent (v1 catalog).
        """
        if self.rel_path:
            rid = re.sub(r"\.(?:md|markdown)$", "", self.rel_path, flags=re.IGNORECASE)
            return rid
        return f"{self.type}/{self.slug}" if self.type else self.slug


def _bench_tokenize(topic: str) -> list[str]:
    """Split a query into searchable terms (mirror of kg.py tokenize_topic)."""
    tokens = re.findall(r"[a-z0-9_-]+", topic.lower())
    return [t for t in tokens if t not in _BENCH_STOPWORDS and len(t) >= 2]


def _bench_parse_catalog(text: str) -> tuple[dict, list[_CatalogEntry]]:
    """Parse the dense catalog into (metadata, [_CatalogEntry, ...]).

    Uses the same block-grammar regex kg.py uses (catalog v1 3-line block and
    v2 4-line block with a `path:` line + pipe-separated sources), so the
    entities scored here are exactly the entities kg routes over. This covers
    parsing only — the identity model and the final filesystem filter diverge
    from kg; both divergences are documented on `retrieve()`.
    """
    metadata: dict = {}
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                metadata[k.strip()] = v.strip()
        text = text[fm_match.end():]

    entries: list[_CatalogEntry] = []
    block_re = re.compile(
        r"^####\s+(\S+)\s+\[([^\]·]+)·([^\]]+)\](?:\s*·\s*score\s+(\S+))?\s*\n"
        r"([^\n]*)\n"
        r"([^\n]*)"
        r"(?:\npath:\s+(\S+))?\n",
        re.MULTILINE,
    )
    for m in block_re.finditer(text):
        slug, type_val, status, _score, claim, meta_line, rel_path = m.groups()
        e = _CatalogEntry(slug=slug.strip())
        e.type = type_val.strip()
        e.status = status.strip()
        e.claim = claim.strip()
        e.rel_path = rel_path.strip() if rel_path else ""
        for part in (p.strip() for p in meta_line.split("·")):
            if part.startswith("→ "):
                e.out_links = [x.strip() for x in part[2:].split(",") if x.strip()]
            elif part.startswith("← "):
                e.in_links = [x.strip() for x in part[2:].split(",") if x.strip()]
            elif part.startswith("#"):
                e.tags = [t.lstrip("#").strip() for t in part.split() if t.startswith("#")]
            elif part.startswith("src: "):
                src_str = part[5:]
                sep = " | " if " | " in src_str else ","
                e.sources = [x.strip() for x in src_str.split(sep) if x.strip()]
        entries.append(e)
    return metadata, entries


def _bench_score_entry(entry: _CatalogEntry, terms: list[str], body: str = "") -> int:
    """Score one catalog entry against query terms (mirror of kg.py score_entity).

    Additive, case-insensitive:
        +10 term == slug · +5 term in slug · +4 term == tag · +3 term in tag
        +3  term in claim · +2 term in body (tier-2 only) · +1 link · +1 source
    """
    score = 0
    slug_l = entry.slug.lower()
    claim_l = entry.claim.lower()
    tags_l = [t.lower() for t in entry.tags]
    sources_l = [s.lower() for s in entry.sources]
    links_l = [s.lower() for s in (entry.out_links + entry.in_links)]
    body_l = body.lower() if body else ""
    for t in terms:
        if t == slug_l:
            score += 10
        elif t in slug_l:
            score += 5
        for tag in tags_l:
            if t == tag:
                score += 4
                break
            if t in tag:
                score += 3
                break
        if t in claim_l:
            score += 3
        if body_l and t in body_l:
            score += 2
        if any(t in lk for lk in links_l):
            score += 1
        if any(t in s for s in sources_l):
            score += 1
    return score


def _load_bench_catalog() -> tuple[dict, list[_CatalogEntry], dict[str, _CatalogEntry]]:
    """Read + parse docs/knowledge-index.md once; return (meta, entries, by_id)."""
    if not CATALOG_PATH.exists():
        return {}, [], {}
    text = CATALOG_PATH.read_text(errors="replace")
    meta, entries = _bench_parse_catalog(text)
    by_id = {e.entity_id(): e for e in entries}
    return meta, entries, by_id


def retrieve(
    query: str,
    k: int = 5,
    entries: Optional[list[_CatalogEntry]] = None,
) -> list[str]:
    """Two-tier retrieval that reuses the `kg` load skill's scoring — ranked ids.

    What is shared with kg.py (identical, so the metrics describe real routing):
      - parsing      (`_bench_parse_catalog` ≡ kg.parse_catalog block grammar)
      - tokenization (`_bench_tokenize` ≡ kg.tokenize_topic stopwords + regex)
      - tier-1 score (`_bench_score_entry` ≡ kg.score_entity additive weights)
      - tier-2 trigger/bonus (fires when tier-1 yields < `k` positive hits;
        +2 per query term present in the entity body; same rglob body lookup).

    What DIVERGES from kg.py (so the docstring does not over-claim a mirror):
      (a) Identity model. This function keys, dedups, and ranks by the catalog
          `type/slug` id (`_CatalogEntry.entity_id()`), and RETURNS `type/slug`
          ids — the fixture's gold-label space. kg.py keys/dedups by the BARE
          `slug` and resolves to files. Two entities that share a slug across
          types stay distinct here but would collide in kg.
      (b) No final filesystem filter. kg.py runs a Phase-2 pass that resolves
          each ranked entity to a real body file and DROPS any it cannot locate
          (catalog-vs-disk drift). This function omits that pass: a ranked
          catalog entry with no body file on disk is still returned. (Tier-2
          reads bodies, but only to ADD score — it never removes an entry.)

    Returns up to `k` `type/slug` ids, ranked by (-score, slug). Ties break on
    slug for determinism.
    """
    if entries is None:
        _meta, entries, _by_id = _load_bench_catalog()
    if not entries:
        return []
    terms = _bench_tokenize(query)
    if not terms:
        return []

    # Tier 1 — catalog-only scoring.
    scored: dict[str, int] = {}
    by_slug: dict[str, _CatalogEntry] = {}
    for e in entries:
        by_slug[e.entity_id()] = e
        s = _bench_score_entry(e, terms)
        if s > 0:
            scored[e.entity_id()] = s

    # Tier 2 — body-grep fallback (only when catalog signal is insufficient).
    if len([s for s in scored.values() if s > 0]) < k:
        for e in entries:
            body_path = None
            if e.rel_path:
                cand = ENTITIES_DIR / e.rel_path
                if cand.exists():
                    body_path = cand
            if body_path is None:
                cands = [
                    p for p in ENTITIES_DIR.rglob(f"{e.slug}.md")
                    if ".lago-blobs" not in p.parts
                ]
                if not cands:
                    continue
                body_path = cands[0]
            try:
                body = body_path.read_text(errors="replace").lower()
            except Exception:
                continue
            bonus = sum(2 for t in terms if t in body)
            if bonus > 0:
                scored[e.entity_id()] = scored.get(e.entity_id(), 0) + bonus

    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[1] and by_slug[kv[0]].slug or kv[0]))
    return [eid for eid, _s in ranked[:k]]


# ── Retrieval metrics ──────────────────────────────────────────────────────────
#
# All three are standard IR metrics, computed per-query then macro-averaged.
# `retrieved` is the ranked id list; `expected` is the (unordered) gold set.

def precision_at_k(retrieved: list[str], expected: set[str], k: int) -> float:
    """Fraction of the top-k retrieved ids that are relevant. |hits∩top_k| / k.

    Deduplicates the top-k window (`set(top[:k]) & expected`) so a ranked list
    with a repeated id cannot inflate the hit count above the number of
    distinct relevant ids actually retrieved.
    """
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    hits = len(set(top) & expected)
    return hits / k


def recall_at_k(retrieved: list[str], expected: set[str], k: int) -> float:
    """Fraction of the relevant ids that appear in the top-k. |hits∩top_k| / |expected|.

    Deduplicates the top-k window (`set(top[:k]) & expected`) so duplicate ids
    in the ranked list cannot push recall above 1.0.
    """
    if not expected:
        return 0.0
    hits = len(set(retrieved[:k]) & expected)
    return hits / len(expected)


def reciprocal_rank(retrieved: list[str], expected: set[str]) -> float:
    """1 / rank of the first relevant id (1-indexed); 0 if none retrieved."""
    for i, r in enumerate(retrieved, start=1):
        if r in expected:
            return 1.0 / i
    return 0.0


class BenchFixtureError(ValueError):
    """Raised when a benchmark fixture is missing, empty, or malformed.

    A silently-empty benchmark reports a perfect-looking run over zero cases,
    which is worse than failing — a broken fixture would never surface a
    regression. So every parse problem is loud.
    """


def load_bench_fixture(path: Path) -> list[dict]:
    """Load a JSONL benchmark fixture: one {query, expected, notes} per line.

    Fails loudly (raises BenchFixtureError) rather than silently skipping:
      - file missing
      - any non-blank, non-`#` line that is not valid JSON
      - any row that is not a dict, or lacks a "query"
      - any row whose "expected" is not a list[str] (a bare string would hit
        the `set("type/slug")` → {'t','y','p',...} character-splitting bug)
      - zero valid cases parsed overall

    Blank lines and `#`-prefixed comment lines are the only things skipped.
    """
    if not path.exists():
        raise BenchFixtureError(f"fixture not found at {path}")

    cases: list[dict] = []
    for lineno, raw in enumerate(path.read_text(errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchFixtureError(
                f"{path}:{lineno}: invalid JSON ({exc.msg})"
            ) from exc
        if not isinstance(obj, dict) or "query" not in obj:
            raise BenchFixtureError(
                f"{path}:{lineno}: each row must be a JSON object with a "
                f'"query" field (got {type(obj).__name__})'
            )
        expected = obj.get("expected", [])
        if not isinstance(expected, list) or not all(
            isinstance(e, str) for e in expected
        ):
            raise BenchFixtureError(
                f'{path}:{lineno}: "expected" must be a list of strings '
                f"(got {expected!r}); a bare string would be split into "
                "characters by set()"
            )
        obj["expected"] = expected
        obj.setdefault("notes", "")
        cases.append(obj)

    if not cases:
        raise BenchFixtureError(
            f"{path}: no valid benchmark cases parsed (file is empty or "
            "all-comment) — refusing to report a perfect run over 0 queries"
        )
    return cases


def run_bench(fixture_path: Path, k: int = 5) -> dict:
    """Run the retrieval benchmark; return aggregate + per-query metrics.

    Macro-averaging (mean of per-query metrics) gives every query equal weight,
    which is the right choice for a labeled fixture where each query represents
    one realistic information need.
    """
    cases = load_bench_fixture(fixture_path)
    _meta, entries, _by_id = _load_bench_catalog()
    if not entries:
        raise RuntimeError(
            f"catalog at {CATALOG_PATH} parsed to 0 entities; regenerate it "
            "(`bookkeeping index`) or update the bench parser for the current "
            "schema — refusing to report a benchmark over an empty catalog"
        )

    per_query: list[dict] = []
    for c in cases:
        query = c["query"]
        expected = set(c.get("expected", []))
        retrieved = retrieve(query, k=k, entries=entries)
        p = precision_at_k(retrieved, expected, k)
        r = recall_at_k(retrieved, expected, k)
        rr = reciprocal_rank(retrieved, expected)
        per_query.append({
            "query": query,
            "expected": sorted(expected),
            "retrieved": retrieved,
            "hits": sorted(set(retrieved[:k]) & expected),
            "precision_at_k": round(p, 4),
            "recall_at_k": round(r, 4),
            "reciprocal_rank": round(rr, 4),
            "notes": c.get("notes", ""),
        })

    n = len(per_query) or 1
    agg = {
        "k": k,
        "fixture": str(fixture_path),
        "catalog": str(CATALOG_PATH),
        "catalog_generated": _meta.get("generated", "?"),
        "catalog_entity_count": len(entries),
        "n_queries": len(per_query),
        "mean_precision_at_k": round(sum(q["precision_at_k"] for q in per_query) / n, 4),
        "mean_recall_at_k": round(sum(q["recall_at_k"] for q in per_query) / n, 4),
        "mrr": round(sum(q["reciprocal_rank"] for q in per_query) / n, 4),
        "generated_at": now_iso(),
        "per_query": per_query,
    }
    return agg


# ── Real-loader engine (BRO-1422 follow-up) ──────────────────────────────────
# run_bench() above is the hermetic FORK engine (own parser + scorer) the unit
# tests pin. It is a fast reference, but a fork can drift from the production
# loader and HIDE bugs — it never caught the dict-score parse drop that made 23
# entities invisible to /kg. The engine below subprocess-drives the REAL kg.py
# so the numbers describe production routing, and adds A/B modes so the value of
# --body-search / --terms is measurable, not assumed.

KG_PY = Path(os.environ.get(
    "KG_PY", Path.home() / ".claude" / "skills" / "kg" / "scripts" / "kg.py"))

# A/B modes the real-engine bench compares. Each is (label, extra kg.py flags).
# The PER_QUERY_TERMS sentinel means "use this row's optional `terms` field" —
# query expansion is per-query (the agent supplies synonyms), not a fixed flag.
BENCH_MODES = (
    ("baseline", ()),
    ("+body-search", ("--body-search",)),
    ("+terms", "PER_QUERY_TERMS"),
)


def retrieve_via_kg(query: str, k: int, extra_flags=(), root: Optional[Path] = None) -> list[str]:
    """Drive the REAL kg.py loader; return ranked `type/slug` ids (primary only).

    Subprocess `kg.py load <query> --n k --json --quiet [extra]` against the
    catalog under `root` (BROOMVA_ROOT). Each primary match maps to the
    fixture's `type/slug` id space; 1-hop `--expand` neighbours (`via` set) are
    excluded — they are context enrichment, not routing results. Returns [] on
    any failure (no matches / non-zero exit / bad JSON) — a miss, never a crash.
    """
    root = root or BROOMVA_ROOT
    if not KG_PY.exists():
        raise RuntimeError(f"kg.py not found at {KG_PY}; set KG_PY to override")
    cmd = [sys.executable, str(KG_PY), "load", query, "--n", str(k),
           "--json", "--quiet", *extra_flags]
    # Pin the child loader to the SAME catalog we resolved. KG_NO_POLICY stops
    # the child from re-resolving through a policy walk-up (which outranks
    # KG_CATALOG) — without it a subprocess CWD inside some configured repo could
    # read a different catalog than the parent benched.
    catalog = CATALOG_PATH if root == BROOMVA_ROOT else root / "docs" / "knowledge-index.md"
    env = {**os.environ, "BROOMVA_ROOT": str(root),
           "KG_CATALOG": str(catalog), "KG_NO_POLICY": "1"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    except (subprocess.TimeoutExpired, OSError):
        return []
    if r.returncode != 0:
        return []
    try:
        payload = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    ids: list[str] = []
    for m in payload.get("matches", []):
        if m.get("via"):  # skip 1-hop --expand neighbours
            continue
        t, slug = m.get("type"), m.get("slug")
        if t and slug:
            ids.append(f"{t}/{slug}")
    return ids


def _bench_mode_aggregate(cases: list[dict], k: int, label: str, flags, root: Path) -> dict:
    """Run one A/B mode over all cases; return aggregate + per-query metrics."""
    per_query: list[dict] = []
    skipped = 0
    for c in cases:
        if flags == "PER_QUERY_TERMS":
            terms = c.get("terms")
            if not terms:
                skipped += 1
                continue
            # A gold-set may encode `terms` as a comma-string OR a JSON list;
            # normalise to one comma-joined arg (a raw list in argv would raise
            # TypeError in subprocess and kill the whole bench run).
            if isinstance(terms, (list, tuple)):
                terms = ",".join(str(t) for t in terms)
            extra = ("--terms", str(terms))
        else:
            extra = tuple(flags)
        expected = set(c.get("expected", []))
        retrieved = retrieve_via_kg(c["query"], k, extra, root=root)
        per_query.append({
            "query": c["query"],
            "expected": sorted(expected),
            "retrieved": retrieved,
            "hits": sorted(set(retrieved[:k]) & expected),
            "precision_at_k": round(precision_at_k(retrieved, expected, k), 4),
            "recall_at_k": round(recall_at_k(retrieved, expected, k), 4),
            "reciprocal_rank": round(reciprocal_rank(retrieved, expected), 4),
            "notes": c.get("notes", ""),
        })
    n = len(per_query) or 1
    return {
        "mode": label,
        "n_queries": len(per_query),
        "n_skipped": skipped,
        "mean_precision_at_k": round(sum(q["precision_at_k"] for q in per_query) / n, 4),
        "mean_recall_at_k": round(sum(q["recall_at_k"] for q in per_query) / n, 4),
        "mrr": round(sum(q["reciprocal_rank"] for q in per_query) / n, 4),
        "per_query": per_query,
    }


def run_bench_real(fixture_path: Path, k: int = 5, modes=None, root: Optional[Path] = None) -> dict:
    """Benchmark the REAL kg.py loader across A/B modes.

    Returns the baseline mode at the top level (same shape run_bench() returns,
    so cmd_bench prints it the same way) plus a `modes` map for A/B comparison.
    """
    root = root or BROOMVA_ROOT
    cases = load_bench_fixture(fixture_path)
    # Respect a relocated catalog (knowledge.catalog_path) when benching the
    # resolved root; fall back to root-relative for isolated fixture roots.
    catalog = CATALOG_PATH if root == BROOMVA_ROOT else root / "docs" / "knowledge-index.md"
    if not catalog.exists():
        raise RuntimeError(
            f"catalog not found at {catalog} — run `bookkeeping index` first")
    text = catalog.read_text(errors="replace")
    header_count = len(re.findall(r"^#### ", text, re.M))
    gen_m = re.search(r"^generated:\s*(.+)$", text, re.M)
    modes = modes if modes is not None else BENCH_MODES
    mode_results = {label: _bench_mode_aggregate(cases, k, label, flags, root)
                    for label, flags in modes}
    base = mode_results.get("baseline") or next(iter(mode_results.values()))
    return {
        "k": k,
        "fixture": str(fixture_path),
        "catalog": str(catalog),
        "engine": "kg.py (real loader, subprocess)",
        "catalog_entity_count": header_count,
        "catalog_generated": gen_m.group(1).strip() if gen_m else "?",
        "n_queries": base["n_queries"],
        "mean_precision_at_k": base["mean_precision_at_k"],
        "mean_recall_at_k": base["mean_recall_at_k"],
        "mrr": base["mrr"],
        "modes": mode_results,
        "per_query": base["per_query"],
        "generated_at": now_iso(),
    }


def cmd_bench(args: argparse.Namespace) -> None:
    """Run the retrieval benchmark and print P@k / R@k / MRR."""
    if args.k < 1:
        print(f"[bench] --k must be >= 1 (got {args.k}); P@k/R@k/MRR are "
              "undefined for a non-positive cutoff", file=sys.stderr)
        sys.exit(2)
    fixture_path = Path(args.fixture) if args.fixture else (
        _FIXTURES_DIR / "brainbench.jsonl"
    )
    if not fixture_path.exists():
        print(f"[bench] fixture not found at {fixture_path}", file=sys.stderr)
        sys.exit(1)
    if not CATALOG_PATH.exists():
        print(f"[bench] catalog not found at {CATALOG_PATH} — run `bookkeeping index` first",
              file=sys.stderr)
        sys.exit(1)

    engine = getattr(args, "engine", "real")
    try:
        if engine == "fork":
            result = run_bench(fixture_path, k=args.k)
        else:
            result = run_bench_real(fixture_path, k=args.k)
    except BenchFixtureError as exc:
        print(f"[bench] malformed fixture: {exc}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print(f"[bench] {exc}", file=sys.stderr)
        sys.exit(1)

    # Always persist machine-readable JSON (goal: trend tracking across runs).
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    BENCH_LATEST.write_text(json.dumps(result, indent=2))

    if args.json:
        print(json.dumps(result, indent=2))
        return

    k = result["k"]
    print(f"\nRetrieval Benchmark (P@{k} / R@{k} / MRR)")
    print("=" * 72)
    print(f"Fixture:  {fixture_path}")
    print(f"Catalog:  {result['catalog_entity_count']} entities "
          f"(generated {result['catalog_generated']})")
    print(f"Queries:  {result['n_queries']}")
    print()

    # Per-query table.
    header = f"{'P@'+str(k):>6} {'R@'+str(k):>6} {'RR':>6}  query"
    print(header)
    print("-" * 72)
    for q in result["per_query"]:
        miss = "" if q["hits"] else "  ✗ MISS"
        qtext = q["query"]
        if len(qtext) > 44:
            qtext = qtext[:43] + "…"
        print(f"{q['precision_at_k']:>6.2f} {q['recall_at_k']:>6.2f} "
              f"{q['reciprocal_rank']:>6.2f}  {qtext}{miss}")
    print("-" * 72)
    print(f"{result['mean_precision_at_k']:>6.3f} {result['mean_recall_at_k']:>6.3f} "
          f"{result['mrr']:>6.3f}  MEAN (macro-averaged over {result['n_queries']} queries)")
    print()

    # A/B mode comparison (real engine only) — quantifies the recall lift from
    # --body-search (force tier-2) and --terms (query expansion) vs baseline.
    modes = result.get("modes")
    if modes:
        print(f"Mode comparison — engine: {result.get('engine', '?')}")
        print(f"  {'mode':<14} {'P@'+str(k):>6} {'R@'+str(k):>6} {'MRR':>6}  queries")
        print("  " + "-" * 44)
        for label, mr in modes.items():
            note = (f"  ({mr['n_skipped']} skipped: no `terms`)"
                    if mr.get("n_skipped") else "")
            print(f"  {label:<14} {mr['mean_precision_at_k']:>6.3f} "
                  f"{mr['mean_recall_at_k']:>6.3f} {mr['mrr']:>6.3f}  "
                  f"{mr['n_queries']}{note}")
        print()

    misses = [q for q in result["per_query"] if not q["hits"]]
    if misses:
        print(f"[bench] {len(misses)} query(ies) with zero hits in top-{k}:")
        for q in misses:
            print(f"  - {q['query']!r} → expected {q['expected']}, "
                  f"got {q['retrieved'][:3]}…")
    print(f"\n[bench] wrote machine-readable results to {BENCH_LATEST}")


# ── Gap analysis (synthesize --gaps) ───────────────────────────────────────────
#
# A "gap" is a place where the knowledge graph is incomplete in a way that
# blocks retrieval or signals an unanswered research question:
#   (a) broken wikilink   — a [[slug]] referenced by ≥1 entity with no file
#   (b) missing core_claim — entity has no/over-long claim (degrades catalog routing)
#   (c) referenced stub    — body < STUB_BODY_MIN_LINES but inbound refs ≥ STUB_MIN_REFS
#
# Each gap is scored by inbound-reference frequency: a missing page that 5
# entities point at is a higher-leverage gap than one nobody references.
# High-scoring gaps are candidate Backlog tickets (Pillar 2, goal-formation) —
# the script writes them to status.json but never calls Linear itself.

_STUB_BODY_MIN_LINES = 15   # bodies shorter than this are "stubs"
_STUB_MIN_REFS = 3          # a stub is a gap only if ≥3 entities reference it
_GAP_HIGH_REFS = 3          # gaps with ≥3 inbound refs are "pending" (Backlog candidates)
_GAP_BROKEN_MIN_REFERRERS = 2  # broken links with ≥2 referrers are also "pending"


def _body_content_lines(body: str) -> int:
    """Count substantive body lines: non-blank, non-comment, non-heading-only."""
    n = 0
    in_comment = False
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "<!--" in line and "-->" not in line:
            in_comment = True
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if line.startswith("<!--") and line.endswith("-->"):
            continue
        # Heading-only lines and horizontal rules don't count as content.
        if line.startswith("#") or set(line) <= {"-", "=", "*"}:
            continue
        n += 1
    return n


def find_gaps(verbose: bool = False) -> dict:
    """Detect and rank knowledge-graph gaps. Returns a structured report.

    Returns dict with keys:
        broken_links    — [{target, referrers:[slug...], count}]   (count desc)
        claim_issues    — [{slug, id, kind:"missing"|"too_long", length}]
        referenced_stubs— [{slug, id, body_lines, inbound, referrers:[...]}] (inbound desc)
        pending_gaps    — high-leverage subset (Backlog candidates): broken-link
                          targets (≥ _GAP_BROKEN_MIN_REFERRERS referrers),
                          referenced stubs (≥ _GAP_HIGH_REFS inbound), and
                          high-inbound core_claim issues (≥ _GAP_HIGH_REFS)
    """
    if not ENTITIES_DIR.exists():
        return {"broken_links": [], "claim_issues": [], "referenced_stubs": [],
                "pending_gaps": []}

    entity_files = sorted(
        (p for p in ENTITIES_DIR.rglob("*.md") if ".lago-blobs" not in p.parts),
        key=lambda p: str(p),
    )
    existing = set(existing_entity_slugs())

    # Build inbound-reference map (slug → set of referrers) and per-entity metadata.
    inbound: dict[str, set] = {}
    meta: dict[str, dict] = {}  # slug → {id, claim, body_lines}
    for path in entity_files:
        text = path.read_text(errors="replace")
        fm, body = parse_frontmatter(text)
        rel = path.relative_to(ENTITIES_DIR)
        type_dir = rel.parts[0] if len(rel.parts) > 1 else "_root"
        slug = (fm.get("slug") if isinstance(fm.get("slug"), str) else None) or path.stem
        eid = f"{type_dir}/{slug}"
        claim = fm.get("core_claim") if isinstance(fm.get("core_claim"), str) else (
            fm.get("core_claim", "")
        )
        # Key by type/slug id, not bare slug: the graph allows the same slug
        # under different type dirs (e.g. person/jason-stern + pattern/jason-stern).
        # Keying by slug would let the later file overwrite the earlier one and
        # silently drop one entity's claim/stub gaps.
        meta[eid] = {
            "slug": slug,
            "id": eid,
            "claim": claim or "",
            "body_lines": _body_content_lines(body),
        }
        # Edges: wikilinks in body + any wikilink in a related: string value.
        link_text = body
        if isinstance(fm.get("related"), list):
            for rel_val in fm["related"]:
                if isinstance(rel_val, str):
                    link_text += " " + rel_val
        for target, _edge in extract_wikilinks_md(link_text):
            tslug = wikilink_slug(target)
            if tslug and tslug != slug:
                inbound.setdefault(tslug, set()).add(slug)

    # (a) Broken links: referenced slugs with no entity file.
    broken_links = []
    for tslug, referrers in inbound.items():
        if tslug not in existing:
            broken_links.append({
                "target": tslug,
                "referrers": sorted(referrers),
                "count": len(referrers),
            })
    broken_links.sort(key=lambda g: (-g["count"], g["target"]))

    # (b) core_claim issues: missing or over-long (>140 chars degrades the catalog).
    claim_issues = []
    for eid, m in meta.items():
        slug = m["slug"]
        claim = m["claim"]
        if not claim:
            claim_issues.append({"slug": slug, "id": m["id"], "kind": "missing",
                                 "length": 0, "inbound": len(inbound.get(slug, ()))})
        elif len(str(claim)) > 140:
            claim_issues.append({"slug": slug, "id": m["id"], "kind": "too_long",
                                 "length": len(str(claim)),
                                 "inbound": len(inbound.get(slug, ()))})
    claim_issues.sort(key=lambda g: (-g["inbound"], g["slug"]))

    # (c) Referenced stubs: short body but ≥_STUB_MIN_REFS inbound references.
    referenced_stubs = []
    for eid, m in meta.items():
        slug = m["slug"]
        inbound_n = len(inbound.get(slug, ()))
        if m["body_lines"] < _STUB_BODY_MIN_LINES and inbound_n >= _STUB_MIN_REFS:
            referenced_stubs.append({
                "slug": slug, "id": m["id"], "body_lines": m["body_lines"],
                "inbound": inbound_n, "referrers": sorted(inbound.get(slug, ())),
            })
    referenced_stubs.sort(key=lambda g: (-g["inbound"], g["slug"]))

    # Pending gaps = high-leverage subset → Backlog ticket candidates.
    pending: list[dict] = []
    for g in broken_links:
        if g["count"] >= _GAP_BROKEN_MIN_REFERRERS:
            pending.append({
                "kind": "broken_link", "target": g["target"],
                "inbound": g["count"], "referrers": g["referrers"],
                "suggestion": f"Create entity for [[{g['target']}]] "
                              f"(referenced by {g['count']} entities)",
            })
    for g in referenced_stubs:
        if g["inbound"] >= _GAP_HIGH_REFS:
            pending.append({
                "kind": "referenced_stub", "target": g["slug"],
                "inbound": g["inbound"], "referrers": g["referrers"],
                "suggestion": f"Expand stub {g['id']} "
                              f"({g['body_lines']} body lines, {g['inbound']} inbound refs)",
            })
    # Missing/over-long core_claim on a highly-referenced entity is also a
    # high-leverage gap: it degrades catalog routing for every entity that
    # points at it. The gap docstring promises pending_gaps is the
    # high-leverage subset, so claim issues with enough inbound refs belong
    # here alongside broken links and stubs.
    for g in claim_issues:
        if g["inbound"] >= _GAP_HIGH_REFS:
            kind_label = ("missing" if g["kind"] == "missing"
                          else f"over-long ({g['length']} chars)")
            pending.append({
                "kind": f"claim_{g['kind']}", "target": g["slug"],
                "inbound": g["inbound"], "referrers": [],
                "suggestion": f"Fix {kind_label} core_claim on {g['id']} "
                              f"({g['inbound']} inbound refs — degrades catalog "
                              "routing for every referrer)",
            })
    pending.sort(key=lambda g: -g["inbound"])

    if verbose:
        print(f"[gaps] {len(broken_links)} broken links, {len(claim_issues)} "
              f"claim issues, {len(referenced_stubs)} referenced stubs, "
              f"{len(pending)} pending (high-leverage)")

    return {
        "broken_links": broken_links,
        "claim_issues": claim_issues,
        "referenced_stubs": referenced_stubs,
        "pending_gaps": pending,
    }


def render_gaps_markdown(gaps: dict, top: int = 20) -> str:
    """Render the gap report as a ranked `## Gaps` markdown section."""
    lines: list[str] = ["## Gaps", ""]
    lines.append("Ranked by inbound-reference frequency. High-leverage gaps "
                 "(broken-link targets, highly-referenced stubs) are candidate "
                 "Backlog research questions — see `pending_gaps` in status.json.")
    lines.append("")

    bl = gaps["broken_links"][:top]
    lines.append(f"### Broken wikilinks ({len(gaps['broken_links'])})")
    if bl:
        lines.append("")
        lines.append("Referenced slugs with no entity file. Creating the missing "
                     "page unblocks every referrer at once.")
        lines.append("")
        for g in bl:
            refs = ", ".join(g["referrers"][:6])
            more = "" if len(g["referrers"]) <= 6 else f" +{len(g['referrers']) - 6} more"
            lines.append(f"- **[[{g['target']}]]** — {g['count']}× "
                         f"(referrers: {refs}{more})")
    else:
        lines.append("\n_None._")
    lines.append("")

    ci = gaps["claim_issues"][:top]
    lines.append(f"### core_claim issues ({len(gaps['claim_issues'])})")
    if ci:
        lines.append("")
        for g in ci:
            if g["kind"] == "missing":
                lines.append(f"- **{g['id']}** — missing core_claim "
                             f"({g['inbound']} inbound refs)")
            else:
                lines.append(f"- **{g['id']}** — core_claim {g['length']} chars "
                             f"(max 140; {g['inbound']} inbound refs)")
    else:
        lines.append("\n_None._")
    lines.append("")

    rs = gaps["referenced_stubs"][:top]
    lines.append(f"### Referenced stubs ({len(gaps['referenced_stubs'])})")
    if rs:
        lines.append("")
        lines.append(f"Bodies < {_STUB_BODY_MIN_LINES} content lines but referenced "
                     f"≥ {_STUB_MIN_REFS} times — the graph expects more here.")
        lines.append("")
        for g in rs:
            lines.append(f"- **{g['id']}** — {g['body_lines']} body lines, "
                         f"{g['inbound']} inbound refs")
    else:
        lines.append("\n_None._")
    lines.append("")

    pending = gaps["pending_gaps"]
    lines.append(f"### Pending (Backlog candidates — {len(pending)})")
    if pending:
        lines.append("")
        for g in pending:
            lines.append(f"- ({g['inbound']}×) {g['suggestion']}")
    else:
        lines.append("\n_None._")
    lines.append("")
    return "\n".join(lines)


def _persist_pending_gaps(pending: list[dict]) -> None:
    """Merge pending_gaps into ~/.config/bookkeeping/status.json (idempotent).

    Reads the existing status cache, sets/replaces the `pending_gaps` key, and
    writes it back. Never calls Linear — these are candidates for human/agent
    promotion to Backlog tickets, surfaced for the goal-formation loop.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    status: dict = {}
    if STATUS_CACHE.exists():
        try:
            loaded = json.loads(STATUS_CACHE.read_text())
            # A valid cache must be a JSON object; a list/scalar is corruption.
            if isinstance(loaded, dict):
                status = loaded
            else:
                raise ValueError(f"expected a JSON object, got {type(loaded).__name__}")
        except Exception as exc:
            # Don't silently clobber a cache we couldn't read — it may hold
            # other keys (stats, run metadata). Preserve it for inspection and
            # warn loudly before writing a fresh one.
            bad_path = STATUS_CACHE.with_suffix(STATUS_CACHE.suffix + ".bad")
            try:
                shutil.copy2(STATUS_CACHE, bad_path)
                preserved = f"preserved a copy at {bad_path}"
            except Exception as copy_exc:  # pragma: no cover - best-effort backup
                preserved = f"(could not back it up: {copy_exc})"
            print(f"[gaps] WARNING: {STATUS_CACHE} is unreadable ({exc}); "
                  f"{preserved}. Writing a fresh status cache with only "
                  "pending_gaps.", file=sys.stderr)
            status = {}
    status["pending_gaps"] = pending
    status["pending_gaps_updated_at"] = now_iso()
    STATUS_CACHE.write_text(json.dumps(status, indent=2))


# ── Health score + remediation (lint --health) ─────────────────────────────────
#
# Health score: 100 * (1 - weighted_issues / total_entities), capped at [0,100].
# Errors weigh more than warnings (a broken schema is worse than a dangling
# link). The remediation plan orders fixes by *leverage*: broken-link TARGETS
# first (one new page unblocks N referrers), then claim issues, then enum
# non-conformance. This is dependency-ordered: do the unblocking work first.

_HEALTH_ERROR_WEIGHT = 1.0
_HEALTH_WARN_WEIGHT = 0.3


def compute_health(errors: list[LintError], total_entities: int) -> dict:
    """Compute the 0-100 lint-health (issue-density) score from a lint error list.

    This is *issue density* — weighted issues per entity — NOT a semantic
    quality score. Because it averages over the whole graph, concentrated
    breakage in a large graph still reads as a high score; `affected_entities`
    (the count of DISTINCT entity files carrying ≥1 issue) is reported
    alongside so that concentration is visible rather than masked.
    """
    n_err = sum(1 for e in errors if e.severity == "error")
    n_warn = sum(1 for e in errors if e.severity == "warning")
    weighted = n_err * _HEALTH_ERROR_WEIGHT + n_warn * _HEALTH_WARN_WEIGHT
    denom = total_entities or 1
    score = 100.0 * (1.0 - weighted / denom)
    score = max(0.0, min(100.0, score))
    affected = len({e.file_path for e in errors if getattr(e, "file_path", None)})
    return {
        "score": round(score, 1),
        "metric": "lint health (issue density)",
        "errors": n_err,
        "warnings": n_warn,
        "weighted_issues": round(weighted, 2),
        "total_entities": total_entities,
        "affected_entities": affected,
    }


def build_remediation_plan(errors: list[LintError]) -> list[dict]:
    """Group lint issues into a dependency-ordered remediation plan.

    Leverage order (highest first) — this is the exact emit order below:
      1. broken-wikilink TARGETS — creating one missing entity unblocks every
         referrer; grouped by target slug so the count = referrers unblocked.
      2. missing core_claim       — blocks catalog routing for that entity.
      3. over-long core_claim     — degrades catalog routing (truncation).
      4. non-conformant type, then non-conformant status — schema enum drift.
      5. cosmetic/format group, in order: missing-sources, related-format,
         timeline-undated, frontmatter, other (format-discernment, projections).

    Returns a ranked list of {step, category, count, leverage, detail} dicts.
    """
    # Bucket 1: broken wikilinks grouped by target (the high-leverage class).
    broken_by_target: dict[str, int] = {}
    missing_claim = 0
    long_claim = 0
    bad_type = 0
    bad_status = 0
    bad_sources = 0
    bad_related = 0
    frontmatter = 0
    timeline = 0
    other = 0

    for e in errors:
        if e.field == "wikilink" and e.message.startswith("Broken wikilink"):
            m = re.search(r"\[\[([^\]]+)\]\]", e.message)
            # wikilink_slug (not slugify): type-qualified [[concept/foo]] must
            # group with [[foo]] on the bare stem, else remediation over-counts
            # "missing entities to create" and mislabels targets (BRO-1976).
            target = wikilink_slug(m.group(1)) if m else e.message
            broken_by_target[target] = broken_by_target.get(target, 0) + 1
        elif e.field == "core_claim" and "missing" in e.message:
            missing_claim += 1
        elif e.field == "core_claim":
            long_claim += 1
        elif e.field == "type":
            bad_type += 1
        elif e.field == "status":
            bad_status += 1
        elif e.field == "sources":
            bad_sources += 1
        elif e.field == "related":
            bad_related += 1
        elif e.field in ("frontmatter", "yaml"):
            frontmatter += 1
        elif e.field == "timeline":
            timeline += 1
        else:
            other += 1

    plan: list[dict] = []

    # 1. Broken-link targets — ranked by referrers unblocked (most leverage).
    n_targets = len(broken_by_target)
    n_broken_refs = sum(broken_by_target.values())
    if n_targets:
        top_targets = sorted(broken_by_target.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        detail = ", ".join(f"[[{t}]] ({c}×)" for t, c in top_targets)
        plan.append({
            "category": "broken-wikilink-targets",
            "count": n_targets,
            "leverage": n_broken_refs,
            "detail": f"Create {n_targets} missing entit"
                      f"{'y' if n_targets == 1 else 'ies'} → unblocks "
                      f"{n_broken_refs} dangling ref"
                      f"{'' if n_broken_refs == 1 else 's'}. Top: {detail}",
        })
    if missing_claim:
        plan.append({
            "category": "missing-core_claim", "count": missing_claim,
            "leverage": missing_claim,
            "detail": f"Add core_claim to {missing_claim} entit"
                      f"{'y' if missing_claim == 1 else 'ies'} (blocks catalog routing).",
        })
    if long_claim:
        plan.append({
            "category": "over-long-core_claim", "count": long_claim,
            "leverage": long_claim,
            "detail": f"Trim {long_claim} core_claim"
                      f"{'' if long_claim == 1 else 's'} to ≤140 chars "
                      f"(truncated in catalog).",
        })
    # 4. Schema-enum non-conformance (type/status) — before the cosmetic
    #    format/sources group, matching the documented dependency order.
    if bad_type:
        plan.append({
            "category": "non-conformant-type", "count": bad_type, "leverage": bad_type,
            "detail": f"Reconcile {bad_type} type value"
                      f"{'' if bad_type == 1 else 's'} with the schema enum.",
        })
    if bad_status:
        plan.append({
            "category": "non-conformant-status", "count": bad_status, "leverage": bad_status,
            "detail": f"Reconcile {bad_status} status value"
                      f"{'' if bad_status == 1 else 's'} with the schema enum.",
        })
    # 5. Cosmetic / format group (sources, related-format, timeline, frontmatter, other).
    if bad_sources:
        plan.append({
            "category": "missing-sources", "count": bad_sources, "leverage": bad_sources,
            "detail": f"Add a sources list to {bad_sources} entit"
                      f"{'y' if bad_sources == 1 else 'ies'}.",
        })
    if bad_related:
        plan.append({
            "category": "related-format", "count": bad_related, "leverage": bad_related,
            "detail": f"Fix {bad_related} related entr"
                      f"{'y' if bad_related == 1 else 'ies'} to [[wikilink]] form "
                      f"(try `lint --fix`).",
        })
    if timeline:
        plan.append({
            "category": "timeline-undated", "count": timeline, "leverage": timeline,
            "detail": f"Add a leading ISO date to {timeline} Timeline entr"
                      f"{'y' if timeline == 1 else 'ies'}.",
        })
    if frontmatter:
        plan.append({
            "category": "frontmatter", "count": frontmatter, "leverage": frontmatter,
            "detail": f"Repair {frontmatter} unparseable/missing frontmatter block"
                      f"{'' if frontmatter == 1 else 's'}.",
        })
    if other:
        plan.append({
            "category": "other", "count": other, "leverage": other,
            "detail": f"{other} miscellaneous issue"
                      f"{'' if other == 1 else 's'} (format-discernment, projections).",
        })

    # Already in leverage order by construction (broken-targets first); number them.
    for i, step in enumerate(plan, start=1):
        step["step"] = i
    return plan


def gaps_to_backlog_candidates(pending: list[dict], cap: int = 10) -> list[dict]:
    """Map high-leverage pending gaps → ticket-ready Backlog candidates (pure).

    Returns up to ``cap`` candidates sorted by leverage (inbound refs), each with
    a stable ``dedup_key`` so the filer can skip gaps already promoted to tickets.
    The engine deliberately does NOT file tickets itself: filing goes through the
    Linear MCP with a P20 quality pass (the workspace's Linear-via-MCP constraint
    + no network side-effects in the knowledge engine). Pure / stdlib / testable.
    """
    actions = {
        "broken_link": "Create missing entity",
        "referenced_stub": "Expand referenced stub",
        "claim_missing": "Add core_claim",
        "claim_too_long": "Trim core_claim",
    }
    if cap <= 0:
        return []
    ranked = sorted(pending, key=lambda g: -int(g.get("inbound", 0)))
    out: list[dict] = []
    seen: set[str] = set()
    for g in ranked:
        if len(out) >= cap:
            break
        kind = str(g.get("kind", "gap"))
        target = str(g.get("target", "?"))
        dedup_key = f"kg-gap:{kind}:{target}"
        if dedup_key in seen:
            # Collapse same-slug/different-type duplicates (e.g. a slug that exists
            # as concept|pattern|tool/<slug>) so dedup_keys stay unique and we never
            # file near-identical tickets for one underlying gap.
            continue
        seen.add(dedup_key)
        inbound = int(g.get("inbound", 0))
        action = actions.get(kind, "Resolve knowledge-graph gap")
        referrers = list(g.get("referrers", []) or [])
        body = [g.get("suggestion", ""), "",
                f"- gap kind: `{kind}`",
                f"- target: `{target}`",
                f"- inbound references: {inbound}"]
        if referrers:
            shown = ", ".join(f"`{r}`" for r in referrers[:12])
            more = f" (+{len(referrers) - 12} more)" if len(referrers) > 12 else ""
            body.append(f"- referrers: {shown}{more}")
        body += ["", "Surfaced by `bookkeeping synthesize --gaps`. File via Linear MCP "
                 "after a P20 quality pass; `dedup_key` prevents re-filing."]
        out.append({
            "dedup_key": dedup_key,
            "title": f"[kg-gap] {action}: {target} ({inbound} ref{'' if inbound == 1 else 's'})",
            "body": "\n".join(body),
            "kind": kind,
            "target": target,
            "leverage": inbound,
        })
    return out


def cmd_synthesize(args: argparse.Namespace) -> None:
    """Detect entity clusters and flag synthesis candidates.

    With --gaps (or always, when computing the full report), also runs gap
    analysis: unresolved wikilinks, missing/over-long core_claim, and
    highly-referenced stubs — ranked by inbound-reference frequency. Gaps are
    candidate research questions for the goal-formation loop (Pillar 2).
    """
    if getattr(args, "backlog", False):
        # verbose=False even under --verbose: find_gaps' verbose summary prints to
        # stdout and would corrupt the JSON document this branch emits, breaking a
        # downstream json.load (P20/Strata-B nit, BRO-1258).
        gaps = find_gaps(verbose=False)
        _persist_pending_gaps(gaps["pending_gaps"])
        cands = gaps_to_backlog_candidates(
            gaps["pending_gaps"], cap=getattr(args, "backlog_cap", 10))
        print(json.dumps({"backlog_candidates": cands, "count": len(cands),
                          "generated_at": now_iso()}, indent=2))
        return

    candidates = find_synthesis_candidates(verbose=args.verbose)
    if not candidates:
        print("[synthesize] No synthesis candidates found.")
    else:
        print(f"\n[synthesize] {len(candidates)} synthesis candidates:")
        for c in candidates:
            print(f"\n  Topic: {c['topic']!r} ({c['entity_count']} entities)")
            for slug in c["slugs"][:5]:
                print(f"    - {slug}")
            if len(c["slugs"]) > 5:
                print(f"    ... and {len(c['slugs']) - 5} more")

    # Gap analysis — always computed so pending_gaps stays fresh in status.json;
    # the full ## Gaps markdown section prints only with --gaps (keeps the
    # default `synthesize` output focused on synthesis clusters).
    gaps = find_gaps(verbose=args.verbose)
    _persist_pending_gaps(gaps["pending_gaps"])

    if getattr(args, "gaps", False):
        print()
        print(render_gaps_markdown(gaps))
    else:
        n_pending = len(gaps["pending_gaps"])
        if n_pending:
            print(f"\n[synthesize] {n_pending} high-leverage gap(s) detected "
                  f"(run `synthesize --gaps` for the ranked report; "
                  f"written to status.json:pending_gaps).")


def cmd_lint(args: argparse.Namespace) -> None:
    """Validate entity pages for frontmatter correctness and broken wikilinks."""
    fix = getattr(args, "fix", False)
    single_file = bool(args.file) and not args.all

    # ── --fix: mechanical auto-repair (related: format + unquoted dates) ──
    if fix:
        if single_file:
            p = Path(args.file)
            n_related, unfixable = fix_entity_page(p, dry_run=False)
            n_dates = fix_unquoted_dates(p, dry_run=False)
            total_fixed = n_related + n_dates
            files_fixed = 1 if total_fixed else 0
            if args.verbose and total_fixed:
                parts = []
                if n_related:
                    parts.append(f"{n_related} related")
                if n_dates:
                    parts.append(f"{n_dates} date{'s' if n_dates != 1 else ''}")
                print(f"  [fix] {p.name}: {', '.join(parts)} repaired")
        else:
            files_fixed, total_fixed, unfixable = fix_all(dry_run=False, verbose=args.verbose)
        print(
            f"[lint --fix] Repaired {total_fixed} frontmatter issue"
            f"{'' if total_fixed == 1 else 's'} across {files_fixed} file"
            f"{'' if files_fixed == 1 else 's'} (related: format + unquoted dates)."
        )

    # Health summary prints with --health, or always on a full `lint --all`
    # run (the task accepts "always print the summary block at end of lint --all").
    want_health = getattr(args, "health", False) or args.all

    # ── Report pass: lint after any fixes so the summary reflects what remains ──
    is_full = args.all or not args.file
    if is_full:
        errors = lint_all(verbose=args.verbose)
        total_entities = (
            len([p for p in ENTITIES_DIR.rglob("*.md") if ".lago-blobs" not in p.parts])
            if ENTITIES_DIR.exists() else 0
        )
    else:
        path = Path(args.file)
        errors = lint_entity_page(path)
        total_entities = 1

    # Temporal reconciliation remains an explicit warning audit rather than a
    # universal lint gate. Preserve default output/health behavior unless the
    # caller asks for it.
    if getattr(args, "temporal", False):
        if is_full:
            errors.extend(_lint_temporal_all(verbose=args.verbose))
        else:
            errors.extend(_lint_temporal_entity_page(path))

    if not errors:
        if fix:
            print("[lint] No remaining errors. Mechanical fixes applied above.")
        else:
            print("[lint] No errors found.")
        if want_health:
            _print_health_block([], total_entities)
        return

    if fix:
        # After --fix, what remains needs human judgment (core_claim length,
        # missing core_claim, broken wikilinks, etc.).
        remaining_related = [e for e in errors if e.field == "related"]
        print(
            f"[lint --fix] {len(errors)} issue(s) remain for manual fix "
            f"({len(remaining_related)} non-mechanical related entr"
            f"{'y' if len(remaining_related) == 1 else 'ies'})."
        )

    error_count = len([e for e in errors if e.severity == "error"])
    warning_count = len([e for e in errors if e.severity == "warning"])

    for e in errors:
        label = "ERROR" if e.severity == "error" else "WARN "
        file_name = Path(e.file_path).name
        print(f"[{label}] {file_name}: {e.field} — {e.message}")

    print(f"\n[lint] {len(errors)} issues: {error_count} errors, {warning_count} warnings")

    if want_health:
        _print_health_block(errors, total_entities)

    if error_count > 0:
        sys.exit(1)


def _print_health_block(errors: list[LintError], total_entities: int) -> None:
    """Print the 0-100 health score + dependency-ordered remediation plan."""
    health = compute_health(errors, total_entities)
    plan = build_remediation_plan(errors)

    print()
    print("Knowledge Graph Lint Health (issue density)")
    print("=" * 56)
    print(f"Lint-health score: {health['score']}/100  "
          f"({health['errors']} errors × {_HEALTH_ERROR_WEIGHT} + "
          f"{health['warnings']} warns × {_HEALTH_WARN_WEIGHT} = "
          f"{health['weighted_issues']} weighted, over {health['total_entities']} entities)")
    print(f"Affected entities: {health['affected_entities']} distinct file"
          f"{'' if health['affected_entities'] == 1 else 's'} carry ≥1 issue "
          f"(issue density averages over the whole graph — this number shows "
          "how concentrated the breakage is).")
    if not plan:
        print("Remediation: none — graph is clean.")
        return
    print()
    print("Remediation plan (dependency-ordered, highest leverage first):")
    for step in plan[:10]:
        print(f"  {step['step']:>2}. [{step['category']}] "
              f"×{step['count']} (unblocks {step['leverage']})")
        print(f"      {step['detail']}")


def _find_entity_file(slug: str) -> "Path | None":
    """Locate the live (non-tombstone) entity file for `slug`, else any match."""
    if not ENTITIES_DIR.exists():
        return None
    cands = [p for p in ENTITIES_DIR.rglob(f"{slug}.md") if ".lago-blobs" not in p.parts]
    for p in cands:
        try:
            fm, _ = read_frontmatter(p)
        except Exception:
            continue
        if fm.get("status") != "merged":
            return p
    return cands[0] if cands else None


def _add_alias_to_frontmatter(text: str, alias: str) -> str:
    """Add `alias` to the frontmatter `aliases:` list.

    Handles three existing shapes without ever producing a duplicate `aliases:`
    key (which would corrupt the YAML and drop prior aliases):
      - inline flow list:  `aliases: [a, b]`  → `aliases: [a, b, alias]`
      - block list:        `aliases:\n  - a`  → append `  - alias`
      - empty block:       `aliases:`         → add first `  - alias`
      - none:              append a new block.
    """
    m = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)", text, re.DOTALL)
    if not m:
        return text
    head, fm, tail = m.group(1), m.group(2), m.group(3)

    # Inline flow list: aliases: [a, b]
    inline = re.search(r"^aliases:\s*\[(.*?)\]\s*$", fm, re.M)
    if inline:
        items = [x.strip() for x in inline.group(1).split(",") if x.strip()]
        if alias in items:
            return text  # already present
        items.append(alias)
        fm = fm[:inline.start()] + f"aliases: [{', '.join(items)}]" + fm[inline.end():]
        return head + fm + tail + text[m.end():]

    # Already present as a block entry?
    if re.search(rf"^\s*-\s*{re.escape(alias)}\s*$", fm, re.M):
        return text
    # Block list with entries OR empty block: insert after the `aliases:` line.
    if re.search(r"^aliases:\s*$", fm, re.M):
        fm = re.sub(r"(^aliases:\s*$)", rf"\1\n  - {alias}", fm, count=1, flags=re.M)
    else:
        fm = fm.rstrip() + f"\naliases:\n  - {alias}"
    return head + fm + tail + text[m.end():]


def cmd_merge(args: argparse.Namespace) -> None:
    """Merge a duplicate entity into a canonical one, durably (BRO-1442).

    Repoints inbound [[dup]] wikilinks → [[canonical]], records `dup` as an alias
    on the canonical (provenance), and rewrites the dup as a `status: merged`
    tombstone so the catalog (`index`) excludes it (no /kg routing competition)
    AND `promote` skips it (it does not resurrect from its raw extract). The
    canonical must already carry the dup's substance — verify before merging.
    """
    dup, canon = args.dup, args.canonical
    if dup == canon:
        print("[merge] dup and canonical are the same slug", file=sys.stderr)
        sys.exit(2)
    dup_path = _find_entity_file(dup)
    canon_path = _find_entity_file(canon)
    if dup_path is None:
        print(f"[merge] dup entity '{dup}' not found", file=sys.stderr)
        sys.exit(1)
    if canon_path is None:
        print(f"[merge] canonical entity '{canon}' not found", file=sys.stderr)
        sys.exit(1)
    # Guard: dup already merged.
    try:
        dup_fm, _ = read_frontmatter(dup_path)
    except Exception:
        dup_fm = {}
    if dup_fm.get("status") == "merged":
        print(f"[merge] '{dup}' is already a merged tombstone — nothing to do")
        return
    # Guard: refuse to merge INTO a tombstone (would create a dangling/chained
    # provenance: canonical points nowhere). Flatten manually first.
    try:
        canon_fm, _ = read_frontmatter(canon_path)
    except Exception:
        canon_fm = {}
    if canon_fm.get("status") == "merged":
        ci = canon_fm.get("merged_into", "?")
        print(f"[merge] canonical '{canon}' is itself a merged tombstone "
              f"(merged_into: {ci}) — merge into '{ci}' instead", file=sys.stderr)
        sys.exit(2)

    dry = getattr(args, "dry_run", False)

    # 0. Compute the canonical's new text BEFORE touching anything, so every
    #    reason to refuse fires while the graph is still untouched. Repointing
    #    referrers first and validating afterwards left them pointing at a
    #    canonical that never got merged — an abort that corrupts.
    dup_type = dup_path.relative_to(ENTITIES_DIR).parts[0]
    # A whitespace-only override would otherwise write an envelope the audit
    # rejects, so it falls back to the tombstone rather than being taken
    # literally.
    revision_link = (getattr(args, "revision_link", None) or "").strip() or str(
        _display_path(ENTITIES_DIR / dup_type / f"{dup}.md"))
    canon_text = canon_path.read_text(errors="replace")
    if not _split_frontmatter(canon_text)[0]:
        print(f"[merge] canonical '{canon}' has no YAML frontmatter — every "
              f"envelope write would silently no-op while the dup is still "
              f"tombstoned", file=sys.stderr)
        sys.exit(1)
    canon_new = _add_alias_to_frontmatter(canon_text, dup)
    try:
        canon_new = _apply_revision_envelope(
            canon_new, supersedes=[dup], revision_link=revision_link)
    except MalformedEnvelopeError as exc:
        print(f"[merge] canonical '{canon}' has a malformed revision envelope: "
              f"{exc}. Repair it by hand, then re-run this merge.",
              file=sys.stderr)
        sys.exit(1)

    # 1. Repoint inbound wikilinks (plain, aliased, heading-anchored forms) across
    # entities AND synthesis notes. Skip the dup itself and any existing tombstone
    # (rewriting a tombstone's prose would corrupt its provenance trail).
    repoint_roots = [ENTITIES_DIR]
    if NOTES_DIR.exists():
        repoint_roots.append(NOTES_DIR)
    repointed = 0
    for root in repoint_roots:
        for p in root.rglob("*.md"):
            if ".lago-blobs" in p.parts or p == dup_path:
                continue
            try:
                pfm, _ = read_frontmatter(p)
            except Exception:
                pfm = {}
            if pfm.get("status") == "merged":
                continue  # don't rewrite another tombstone's recorded prose
            t = p.read_text(errors="replace")
            nt = (t.replace(f"[[{dup}]]", f"[[{canon}]]")
                    .replace(f"[[{dup}|", f"[[{canon}|")
                    .replace(f"[[{dup}#", f"[[{canon}#"))
            if nt != t:
                if not dry:
                    p.write_text(nt)
                repointed += 1
    # 2. Write the canonical computed in step 0 — the alias (provenance) plus
    #    the typed revision. A merge IS an explicit correction, so the canonical
    #    supersedes the dup and points at the tombstone that authorized it;
    #    without this the envelope would have a `revise` producer and no real
    #    caller, the schema-with-no-writer failure this phase exists to avoid.
    if canon_new != canon_text and not dry:
        canon_path.write_text(canon_new)
    # 3. Rewrite dup as a tombstone.
    today = today_str()
    tombstone = (
        f"---\nslug: {dup}\ntype: {dup_type}\nstatus: merged\n"
        f"merged_into: {canon}\nmerged_at: {today}\n"
        f'core_claim: "Merged into [[{canon}]] — the canonical entity carries the content."\n---\n\n'
        f"# {dup.replace('-', ' ').title()}\n\n"
        f"Merged into [[{canon}]] on {today} (BRO-1442). Retained as a tombstone so the "
        f"promote pipeline does not resurrect this slug from its raw extract; `{canon}` "
        f"lists `{dup}` as an alias.\n"
    )
    if not dry:
        dup_path.write_text(tombstone)
    tag = " (dry-run)" if dry else ""
    print(f"[merge]{tag} {dup} → {canon}: repointed {repointed} link(s), aliased canonical, tombstoned.")
    if not dry:
        print("        Run `bookkeeping index` to drop the tombstone from the catalog.")


def cmd_revise(args: argparse.Namespace) -> None:
    """Record an explicit correction: `entity` supersedes one or more records (gh-156).

    The sanctioned way to state "this page replaces that one". It is an
    operator/agent ACTION, never an inference: the caller names the revising
    entity, the superseded slugs, and the record that authorized the change.
    Nothing about present-tense prose can trigger it.

    Both supersession targets and the revising entity must already exist on
    disk. Pointing at a slug with no file is a hard error rather than a
    warning, because writing an unresolvable `supersedes` would create exactly
    the dangling-provenance state the audit then has to report.
    """
    entity = args.entity
    entity_path = _find_entity_file(entity)
    if entity_path is None:
        print(f"[revise] entity '{entity}' not found", file=sys.stderr)
        sys.exit(1)

    # A blank link satisfies argparse but not the audit, so the command would
    # otherwise "succeed" while writing an envelope its own linter rejects.
    revision_link = (args.revision_link or "").strip()
    if not revision_link:
        print("[revise] --revision-link must not be blank — a supersession "
              "with no authorizing record is untraceable", file=sys.stderr)
        sys.exit(2)

    targets: list[str] = []
    for raw in args.supersedes:
        for slug in str(raw).split(","):
            slug = slug.strip().strip("[]").strip()
            if slug and slug not in targets:
                targets.append(slug)
    if not targets:
        print("[revise] --supersedes requires at least one slug", file=sys.stderr)
        sys.exit(2)
    if entity in targets:
        print(f"[revise] '{entity}' cannot supersede itself", file=sys.stderr)
        sys.exit(2)
    missing = [s for s in targets if _find_entity_file(s) is None]
    if missing:
        print(f"[revise] superseded slug(s) not found: {', '.join(missing)}",
              file=sys.stderr)
        sys.exit(1)

    # `valid_from` is operator-supplied here and nowhere else in this command:
    # a revision is precisely the moment somebody KNOWS when the corrected
    # claim became true. Absent the flag, the field is left alone.
    valid_from = None
    if getattr(args, "valid_from", None):
        valid_from = _coerce_iso_date_str(args.valid_from)
        if valid_from is None:
            print(f"[revise] --valid-from {args.valid_from!r} is not an ISO date "
                  f"(YYYY-MM-DD)", file=sys.stderr)
            sys.exit(2)

    original = entity_path.read_text(errors="replace")
    # Every setter is a no-op on a document without frontmatter, so without this
    # check the command would exit 0 reporting "no change" while recording
    # nothing at all.
    fm_block, _ = _split_frontmatter(original)
    if not fm_block:
        print(f"[revise] '{entity}' has no YAML frontmatter — nothing to revise "
              f"({_display_path(entity_path)})", file=sys.stderr)
        sys.exit(1)

    try:
        revised = _apply_revision_envelope(
            original,
            supersedes=targets,
            revision_link=revision_link,
            valid_from=valid_from,
        )
    except MalformedEnvelopeError as exc:
        print(f"[revise] '{entity}' has a malformed revision envelope: {exc}. "
              f"Repair it by hand — rewriting it here would destroy the "
              f"provenance this command exists to preserve.", file=sys.stderr)
        sys.exit(1)

    dry = getattr(args, "dry_run", False)
    if not dry and revised != original:
        entity_path.write_text(revised)
    tag = " (dry-run)" if dry else ""
    changed = "already recorded" if revised == original else "updated"
    print(f"[revise]{tag} {entity} supersedes {', '.join(targets)} "
          f"(revision_link: {revision_link}) — {changed}.")
    print("        Supersession findings surface under `lint --temporal` "
          "(warning-only).")


def cmd_status(_args: argparse.Namespace) -> None:
    """Print knowledge graph statistics."""
    run_status()

# ── Layer-2 retention (BRO-1991) ──────────────────────────────────────────────
#
# CLAUDE.md has always specified "Layer 2 — Raw Extracts ... Retained 30 days,
# then archived", but nothing implemented it, so `research/notes/*-raw.md`
# accumulated without bound: 20 of 26 extracts were past the window when this
# landed, the oldest at 111 days. Every scheduled run re-ingested all of them
# and re-promoted fragments, which is why deleting the minted pages never stuck
# — the next run regenerated them from the same April notes.
#
# Archiving MOVES, never deletes. Entity provenance is safe across the move
# because `sources:` values are note BASENAMES, not paths (pinned by a test).

RAW_ARCHIVE_DIRNAME = "archive"
DEFAULT_RETENTION_DAYS = 30

_RAW_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-")


def raw_extract_age_days(path: Path, today: "date | None" = None) -> "int | None":
    """Age of a Layer-2 raw extract in days.

    Prefers the `YYYY-MM-DD-` filename prefix, which is the note's logical date
    and survives copies, rebases and checkouts. Falls back to mtime only when
    the name carries no date. Returns None if neither is usable, and the caller
    treats that as "do not touch" — an unparseable name must never be archived
    by guesswork.
    """
    ref = today or date.today()
    m = _RAW_DATE_RE.match(path.name)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
        return (ref - d).days
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return None
    return (ref - mtime).days


def run_archive(
    days: int = DEFAULT_RETENTION_DAYS,
    apply: bool = False,
    notes_dir: "Path | None" = None,
    today: "date | None" = None,
) -> "list[tuple[Path, int]]":
    """Move raw extracts older than `days` into `<notes>/archive/`.

    Returns the list of (path, age_days) that were (or would be) archived.
    """
    base = notes_dir or NOTES_DIR
    if not base.exists():
        print(f"[archive] no notes dir at {base}")
        return []

    archive_dir = base / RAW_ARCHIVE_DIRNAME
    aged: "list[tuple[Path, int]]" = []
    skipped_undated = 0

    for p in sorted(base.glob("*-raw.md")):
        age = raw_extract_age_days(p, today=today)
        if age is None:
            skipped_undated += 1
            continue
        if age > days:
            aged.append((p, age))

    if not aged:
        print(f"[archive] nothing older than {days}d in {base}")
        return []

    for p, age in aged:
        if apply:
            archive_dir.mkdir(parents=True, exist_ok=True)
            dest = archive_dir / p.name
            if dest.exists():
                # Never clobber an existing archived note; the on-disk copy is
                # the older, authoritative one.
                print(f"  [skip] {p.name} — already archived")
                continue
            p.rename(dest)
            print(f"  archived {p.name} ({age}d)")
        else:
            print(f"  [dry-run] would archive {p.name} ({age}d)")

    if skipped_undated:
        print(f"[archive] {skipped_undated} undated file(s) left alone")
    verb = "archived" if apply else "would archive"
    print(f"[archive] {verb} {len(aged)} extract(s) older than {days}d → {archive_dir}")
    if not apply:
        print("[archive] DRY RUN — pass --apply to move them")
    return aged


def cmd_archive(args: argparse.Namespace) -> None:
    """Enforce the Layer-2 retention window."""
    run_archive(days=args.days, apply=args.apply)



def cmd_query(args: argparse.Namespace) -> None:
    """Find and display an entity page."""
    run_query(args.slug, verbose=getattr(args, "verbose", False))


def cmd_render(args: argparse.Namespace) -> None:
    """
    Category B projection: render a Layer 4 synthesis MD into a single-file HTML.

    Path resolution:
      - file `.md`  → render to sibling `.html`
      - directory   → render all `*-synthesis.md` inside (non-recursive by default)
      - --layer N   → render all Layer-N synthesis notes under research/notes/
    """
    targets: list[Path] = []
    src = Path(args.path) if args.path else None

    if args.layer is not None:
        from_notes = Path("research/notes")
        if not from_notes.exists():
            print(f"[render] research/notes/ not found in {Path.cwd()}", file=sys.stderr)
            sys.exit(2)
        if args.layer == 4:
            targets = sorted(from_notes.glob("*-synthesis.md"))
        else:
            print(f"[render] --layer {args.layer}: only layer 4 supported today",
                  file=sys.stderr)
            sys.exit(2)
    elif src is None:
        print("[render] usage: bookkeeping render <path> | --layer N", file=sys.stderr)
        sys.exit(2)
    elif src.is_dir():
        targets = sorted(src.glob("*-synthesis.md"))
    elif src.is_file():
        targets = [src]
    else:
        print(f"[render] not found: {src}", file=sys.stderr)
        sys.exit(2)

    if not targets:
        print("[render] no synthesis notes matched")
        return

    rendered = 0
    for md_path in targets:
        try:
            md_text = md_path.read_text(errors="replace")
            html = render_markdown_to_html(md_text, md_path, link_html=args.link_html)
            out_path = md_path.with_suffix(".html")
            out_path.write_text(html)
            rendered += 1
            if args.verbose:
                print(f"[render] {md_path} → {out_path}")
        except Exception as exc:
            print(f"[render] failed {md_path}: {exc}", file=sys.stderr)
    print(f"[render] {rendered} file(s) rendered")


# ── cmd_index — dense LLM-loadable catalog ────────────────────────────────────
#
# The catalog is the load-bearing primitive for the LLM-as-index architecture
# (BRO-1223). It is a Category-A substrate file (agent-readable markdown, not
# a Category-B HTML projection) — see SKILL.md §Format Discernment.
#
# Format per entity (3 lines):
#   #### {slug} [{type}·{status}]{score_suffix}
#   {core_claim truncated to ~200 chars, or first-paragraph excerpt}
#   → {top-5 outbound, ranked by target in-degree} · ← {top-5 inbound, ranked by
#     source in-degree} · #{tag1} #{tag2} #{tag3} · src: {top-2 sources}
#
# At ~269 entities this produces ~17k tokens — fits any 1M-context model with
# ~98% headroom, leaving room for the agent to also load 10-20 full entity
# bodies on demand. The catalog routes; the agent loads.

# Maximum lengths for catalog block fields (token budget control).
# Standard caps fit ~10k entities in a 1M-context window with ~50% headroom.
# Beyond ~5k entities, the haystack benchmark showed catalog tokens grow
# linearly and cross the 1M ceiling at N=10k. The compact preset cuts caps
# roughly in half — buying 2-3× headroom for substrates between 5k and 20k.
_CATALOG_CLAIM_MAX = 220        # characters
_CATALOG_TOP_LINKS = 5          # top-N outbound + top-N inbound per entity
_CATALOG_TOP_TAGS = 4           # top-N tags per entity
_CATALOG_TOP_SOURCES = 2        # top-N sources per entity
_CATALOG_TOP_ALIASES = 5        # top-N aliases per entity (kepano synonym layer + merged-slug routing, BRO-1423)
_CATALOG_HUB_LIST = 12          # top-N hubs in header section

# Compact preset — kicks in via --compact flag OR auto when entity count
# exceeds _CATALOG_AUTO_COMPACT_THRESHOLD. The thresholds are deliberately
# conservative; agents reading the compact catalog see less context per
# entity but can still route via slug+claim+tags.
_CATALOG_COMPACT_CLAIM_MAX = 100
_CATALOG_COMPACT_TOP_LINKS = 3
_CATALOG_COMPACT_TOP_TAGS = 2
_CATALOG_COMPACT_TOP_SOURCES = 1
_CATALOG_COMPACT_TOP_ALIASES = 3
_CATALOG_COMPACT_HUB_LIST = 8

# Auto-compact when entity count exceeds this threshold. Set high enough
# that the default workspace (~250 entities) never compacts; low enough
# that we don't approach the 1M ceiling.
_CATALOG_AUTO_COMPACT_THRESHOLD = 5000


def _catalog_coerce_str_list(v) -> list[str]:
    """Best-effort coerce a frontmatter value into a list[str].

    Frontmatter authoring is permissive: tags/sources/related may be strings,
    lists of strings, or lists of dicts. This collapses each variant to a
    deterministic list[str].
    """
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        out: list[str] = []
        for x in v:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                for vv in x.values():
                    if isinstance(vv, str):
                        out.append(vv)
                        break
        return out
    return []


def _catalog_extract_links(text: str) -> list[str]:
    """Extract wikilink targets as canonical slugs via the shared resolver.

    Routes through ``wikilink_slug`` (not just delimiter-stripping) so a
    type-qualified ``[[concept/foo]]`` resolves to the bare stem ``foo`` AND a
    mixed-case/spaced ``[[concept/Foo Bar]]`` resolves to ``foo-bar`` — matching
    the node keys (also slugified stems), so catalog edges connect to their node
    instead of dangling. All 4 wikilink-resolution sites now share one resolver
    (BRO-1976)."""
    out: list[str] = []
    for raw in re.findall(r"\[\[([^\]]+)\]\]", text):
        target = wikilink_slug(raw)
        if target:
            out.append(target)
    return out


def _catalog_strip_md(text: str) -> str:
    """Remove markdown emphasis/links for one-line claim rendering."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)            # inline code
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)      # bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)          # italic
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # md links
    text = re.sub(r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]", r"\1", text)  # wikilinks
    return text.strip()


def _catalog_claim_for(fm: dict, body: str) -> str:
    """Get a one-line claim: prefer fm.core_claim, fall back to first body paragraph."""
    raw = fm.get("core_claim")
    if not isinstance(raw, str):
        # Fall back to first non-heading paragraph of body
        candidates: list[str] = []
        for para in re.split(r"\n\s*\n", body.strip(), maxsplit=20):
            stripped = para.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("```"):
                continue
            candidates.append(stripped)
            break
        raw = candidates[0] if candidates else ""
    claim = _catalog_strip_md(raw)
    if len(claim) > _CATALOG_CLAIM_MAX:
        claim = claim[: _CATALOG_CLAIM_MAX - 1].rstrip() + "…"
    return claim or "(no claim)"


def _catalog_estimate_tokens(text: str) -> int:
    """Rough OAI/Anthropic tokenizer estimate: ~4 chars/token."""
    return max(1, len(text) // 4)


def _catalog_collect() -> dict:
    """Walk research/entities/, parse frontmatter+body, build the in/out edge graph.

    Returns a dict with:
        nodes        — {slug: {type_dir, fm, body, path}}
        out_edges    — {slug: set[slug]}     (wikilinks in body+frontmatter)
        in_edges     — {slug: set[slug]}     (reverse of out_edges)
        type_buckets — {type_dir: list[slug] sorted by in-degree desc}
    """
    if not ENTITIES_DIR.exists():
        return {"nodes": {}, "out_edges": {}, "in_edges": {}, "type_buckets": {}}

    # Sorted iteration is deterministic across Python processes — required for
    # cross-process parity with downstream consumers (e.g., kg load skill,
    # validation scripts). Without sort, rglob iteration order can vary and
    # slug clashes (e.g., pattern/anima.md + tool/anima.md) resolve
    # non-deterministically.
    entity_files = sorted(
        (p for p in ENTITIES_DIR.rglob("*.md") if ".lago-blobs" not in p.parts),
        key=lambda p: str(p),
    )

    nodes: dict[str, dict] = {}
    out_edges: dict[str, set] = {}

    for path in entity_files:
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        fm, body = parse_frontmatter(text)
        # Merge tombstones (a dup folded into a canonical via `bookkeeping merge`)
        # are excluded from the catalog so they no longer compete for /kg's top-N
        # (BRO-1442). The file is kept on disk as a promote-skip marker + provenance.
        if fm.get("status") == "merged":
            continue
        rel = path.relative_to(ENTITIES_DIR)
        type_dir = rel.parts[0] if len(rel.parts) > 1 else "_root"
        slug = (fm.get("slug") if isinstance(fm.get("slug"), str) else None) or path.stem
        nodes[slug] = {
            "type_dir": type_dir,
            "fm": fm,
            "body": body,
            "path": path,
        }
        # Edges from wikilinks anywhere in the file (body + any wikilinks in fm.related strings)
        link_text = body
        for rel_link in _catalog_coerce_str_list(fm.get("related")):
            link_text += " " + rel_link
        targets = {t for t in _catalog_extract_links(link_text) if t != slug}
        out_edges[slug] = targets

    in_edges: dict[str, set] = {}
    for src, tgts in out_edges.items():
        for t in tgts:
            in_edges.setdefault(t, set()).add(src)

    def indegree(s: str) -> int:
        return len(in_edges.get(s, ()))

    type_buckets: dict[str, list[str]] = {}
    for slug, n in nodes.items():
        type_buckets.setdefault(n["type_dir"], []).append(slug)
    for t in type_buckets:
        type_buckets[t].sort(key=lambda s: (-indegree(s), s))

    return {
        "nodes": nodes,
        "out_edges": out_edges,
        "in_edges": in_edges,
        "type_buckets": type_buckets,
    }


def _catalog_caps(compact: bool) -> dict:
    """Resolve per-entity caps based on compact-mode."""
    if compact:
        return {
            "claim_max": _CATALOG_COMPACT_CLAIM_MAX,
            "top_links": _CATALOG_COMPACT_TOP_LINKS,
            "top_tags": _CATALOG_COMPACT_TOP_TAGS,
            "top_sources": _CATALOG_COMPACT_TOP_SOURCES,
            "top_aliases": _CATALOG_COMPACT_TOP_ALIASES,
            "hub_list": _CATALOG_COMPACT_HUB_LIST,
        }
    return {
        "claim_max": _CATALOG_CLAIM_MAX,
        "top_links": _CATALOG_TOP_LINKS,
        "top_tags": _CATALOG_TOP_TAGS,
        "top_sources": _CATALOG_TOP_SOURCES,
        "top_aliases": _CATALOG_TOP_ALIASES,
        "hub_list": _CATALOG_HUB_LIST,
    }


def _catalog_render_entity_block(
    slug: str,
    node: dict,
    out_edges: dict[str, set],
    in_edges: dict[str, set],
    caps: Optional[dict] = None,
) -> str:
    """Render one entity as a 4-line catalog block.

    Format (schema dense-catalog-v1):
        #### {slug} [{type}·{status}]{score}
        {claim, ≤220 chars}
        → out · ← in · #tag1 #tag2 · src: source1 | source2
        path: {type_dir}/{slug}.md

    Why 4 lines: the path field eliminates the slug-clash routing
    ambiguity. When the same slug exists in multiple type directories
    (e.g. pattern/anima.md + tool/anima.md), the catalog dedups by
    slug (sorted last-write wins), but readers — including /kg load —
    need to know WHICH file the catalog describes. Without an explicit
    path, kg.py's `rglob(slug.md)[0]` returns an arbitrary file that
    may not match the catalog header. With it, load is deterministic.

    Source separator is ' | ' (not ', ') because moltbook source URLs
    routinely contain parenthetical commas — splitting on ',' fragments
    ~9% of sources. Pipe is unambiguous: no entity source uses '|'.
    """
    caps = caps or _catalog_caps(compact=False)
    fm = node["fm"]
    body = node["body"]
    type_val = fm.get("type") if isinstance(fm.get("type"), str) else node["type_dir"]
    status = fm.get("status") if isinstance(fm.get("status"), str) else "—"
    score = fm.get("score")
    # Reduce score to a single space-free catalog token. Stub-deterministic
    # entities carry a DICT score ({'total': '6/9', 'novelty': 1, ...}); the
    # f-string used to emit its Python repr, whose embedded spaces broke kg.py's
    # `· score \S+` block grammar — the whole block failed to match and the
    # entity was silently dropped from /kg routing (23 entities at 370). Emit
    # only the total, space-stripped, so every block parses.
    if isinstance(score, dict):
        score = score.get("total")
    score_token = str(score).replace(" ", "") if score is not None else None
    score_suffix = f" · score {score_token}" if score_token else ""

    # Honor caps["claim_max"] — recompute claim with the resolved cap.
    raw = fm.get("core_claim")
    if isinstance(raw, str):
        claim = _catalog_strip_md(raw)
    else:
        claim = _catalog_claim_for(fm, body)
    if len(claim) > caps["claim_max"]:
        claim = claim[: caps["claim_max"] - 1].rstrip() + "…"
    if not claim:
        claim = "(no claim)"

    # Rank outbound by target in-degree (most-referenced targets first)
    def in_deg(s: str) -> int:
        return len(in_edges.get(s, ()))

    out_sorted = sorted(out_edges.get(slug, ()), key=lambda s: (-in_deg(s), s))[: caps["top_links"]]
    in_sorted = sorted(in_edges.get(slug, ()), key=lambda s: (-in_deg(s), s))[: caps["top_links"]]

    tags = _catalog_coerce_str_list(fm.get("tags"))[: caps["top_tags"]]
    sources = _catalog_coerce_str_list(fm.get("sources"))[: caps["top_sources"]]
    # Aliases (BRO-1423): kepano synonym layer + merged-slug routing. An entity's
    # alternate names (incl. the slugs of dups merged into it) become catalog-
    # routable so /kg finds the canonical when an alias is queried.
    # Sanitize: the `aka:` segment lives in a `·`-delimited, comma-split meta-line,
    # so an alias containing those delimiters can't round-trip — drop it. Also drop
    # any alias equal to the slug (would double-count in scoring) and dedup
    # (case-insensitive, order-preserving) before capping. (BRO-1423 review)
    _alias_seen: set = set()
    aliases = []
    for _a in _catalog_coerce_str_list(fm.get("aliases")):
        _a = _a.strip()
        _al = _a.lower()
        if not _a or "·" in _a or "," in _a or _al == slug.lower() or _al in _alias_seen:
            continue
        _alias_seen.add(_al)
        aliases.append(_a)
    aliases = aliases[: caps["top_aliases"]]

    # Line 1: header
    line1 = f"#### {slug} [{type_val}·{status}]{score_suffix}"

    # Line 2: claim
    line2 = claim

    # Line 3: composite metadata (out · in · tags · src)
    parts: list[str] = []
    if out_sorted:
        parts.append("→ " + ", ".join(out_sorted))
    if in_sorted:
        parts.append("← " + ", ".join(in_sorted))
    if tags:
        parts.append(" ".join("#" + t.replace(" ", "-") for t in tags))
    if aliases:
        # `aka:` segment — comma-separated alternate names; kg.py scores these
        # like slugs so a query for an alias routes to this entity.
        parts.append("aka: " + ", ".join(aliases))
    if sources:
        # Pipe-separated, robust against commas-in-parens in source URLs
        parts.append("src: " + " | ".join(sources))
    line3 = " · ".join(parts) if parts else "(no edges, no tags, no sources)"

    # Line 4: filesystem path (resolves slug clashes — catalog and loader agree)
    try:
        rel_path = Path(node["path"]).relative_to(ENTITIES_DIR)
    except Exception:
        rel_path = Path(node["path"]).name
    line4 = f"path: {rel_path}"

    return f"{line1}\n{line2}\n{line3}\n{line4}\n"


def _catalog_render(state: dict, compact: Optional[bool] = None) -> str:
    """Render the full dense catalog markdown.

    `compact` controls per-entity caps:
      - None (default): auto-compact when len(nodes) > _CATALOG_AUTO_COMPACT_THRESHOLD
      - True:           force compact (smaller caps; lower token budget)
      - False:          force full caps (no auto-compact)

    The catalog frontmatter records the resolved `compact` and `schema` so
    downstream consumers (kg.py loader) can detect which preset was used.
    """
    nodes = state["nodes"]
    in_edges = state["in_edges"]
    out_edges = state["out_edges"]
    type_buckets = state["type_buckets"]

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total = len(nodes)
    counts_by_type = {t: len(slugs) for t, slugs in type_buckets.items()}

    # Resolve compact mode — explicit flag wins; otherwise auto-threshold.
    if compact is None:
        compact = total > _CATALOG_AUTO_COMPACT_THRESHOLD
    caps = _catalog_caps(compact=compact)

    # Top hubs by in-degree
    hubs = sorted(
        ((len(in_edges.get(s, ())), s) for s in nodes),
        reverse=True,
    )[: caps["hub_list"]]

    total_edges = sum(len(v) for v in out_edges.values())
    all_targets = set().union(*out_edges.values()) if out_edges else set()
    resolved = all_targets & set(nodes)
    dangling = all_targets - set(nodes)

    lines: list[str] = []

    # YAML frontmatter (single source of truth for the agent's freshness check)
    lines.append("---")
    lines.append(f"generated: {now}")
    lines.append("generator: bookkeeping index")
    lines.append(f"schema: dense-catalog-v{'2-compact' if compact else '2'}")
    lines.append(f"compact: {str(compact).lower()}")
    lines.append(f"entity_count: {total}")
    lines.append("---")
    lines.append("")

    # Header
    lines.append("# Knowledge Index")
    lines.append("")
    lines.append(
        "LLM-loadable catalog of all entity pages. Read this to route to relevant "
        "entities; load full bodies on demand via `/kg load <topic>` or direct Read. "
        "Substrate is markdown — see SKILL.md §Format Discernment (Category A)."
    )
    lines.append("")
    lines.append(f"**{total} entities · {total_edges} edges · {len(dangling)} dangling**")
    lines.append("")

    # Counts table
    lines.append("## By type")
    lines.append("")
    lines.append("| Type | Count |")
    lines.append("|---|---|")
    for t in sorted(counts_by_type, key=lambda x: -counts_by_type[x]):
        lines.append(f"| {t} | {counts_by_type[t]} |")
    lines.append("")

    # Hubs
    lines.append(f"## Top hubs (in-degree)")
    lines.append("")
    if hubs:
        hub_strs = [f"`{s}` ({d})" for d, s in hubs if d > 0]
        lines.append(" · ".join(hub_strs) if hub_strs else "_(no hubs yet)_")
    lines.append("")

    # Dangling (demand signal)
    if dangling:
        # Rank dangling by how often referenced
        ref_count: dict[str, int] = {}
        for src, tgts in out_edges.items():
            for t in tgts:
                if t in dangling:
                    ref_count[t] = ref_count.get(t, 0) + 1
        top_dangling = sorted(ref_count.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        if top_dangling:
            lines.append("## Most-referenced missing pages")
            lines.append("")
            for slug, n in top_dangling:
                lines.append(f"- `{slug}` ({n}×)")
            lines.append("")

    # Per-type entity catalog
    lines.append("## Entities")
    lines.append("")
    for type_dir in sorted(type_buckets, key=lambda t: (-len(type_buckets[t]), t)):
        slugs = type_buckets[type_dir]
        lines.append(f"### {type_dir} ({len(slugs)})")
        lines.append("")
        for slug in slugs:
            lines.append(_catalog_render_entity_block(slug, nodes[slug], out_edges, in_edges, caps=caps))
    return "\n".join(lines)


def cmd_index(args: argparse.Namespace) -> None:
    """Generate the dense LLM-loadable knowledge catalog.

    Writes to docs/knowledge-index.md (Category-A substrate) — agent-readable
    markdown that routes to entity files. The agent reads this catalog at
    session start; entity bodies are loaded on demand.
    """
    state = _catalog_collect()
    if not state["nodes"]:
        print(f"[index] no entities found under {ENTITIES_DIR}", file=sys.stderr)
        sys.exit(1)

    # --compact forces compact preset; --no-compact forces full caps;
    # default = auto (compact when entity count > _CATALOG_AUTO_COMPACT_THRESHOLD).
    compact: Optional[bool] = None
    if getattr(args, "compact", False):
        compact = True
    elif getattr(args, "no_compact", False):
        compact = False
    output = _catalog_render(state, compact=compact)
    out_path = CATALOG_PATH  # repo-native write path (resolved at module load)

    if args.dry_run:
        print(output)
        print(
            f"\n[index] DRY RUN — would write {len(state['nodes'])} entities to {out_path} "
            f"(~{_catalog_estimate_tokens(output)} tokens)",
            file=sys.stderr,
        )
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write via tmpfile + replace
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(output)
    tmp.replace(out_path)

    print(
        f"[index] {len(state['nodes'])} entities → {_display_path(out_path)} "
        f"(~{_catalog_estimate_tokens(output)} tokens)"
    )


# ── Entry Point ───────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="bookkeeping",
        description="Broomva knowledge engine (bstack P6) — 7-stage pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run
    p_run = sub.add_parser("run", help="Full 7-stage pipeline")
    p_run.add_argument("--source", metavar="FILE", help="Source file (auto-discovers if omitted)")
    p_run.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    p_run.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_run.set_defaults(func=cmd_run)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Normalize a file to JSON")
    p_ingest.add_argument("--source", required=True, metavar="FILE", help="Source file to ingest")
    p_ingest.add_argument("--verbose", "-v", action="store_true")
    p_ingest.set_defaults(func=cmd_ingest)

    # score
    p_score = sub.add_parser("score", help="Score all items in a raw extract")
    p_score.add_argument("--file", required=True, metavar="FILE", help="Raw extract file")
    p_score.add_argument("--verbose", "-v", action="store_true")
    p_score.set_defaults(func=cmd_score)

    # promote
    p_promote = sub.add_parser("promote", help="Promote items (score ≥5) to entity pages")
    p_promote.add_argument("--file", required=True, metavar="FILE", help="Raw extract file")
    p_promote.add_argument("--dry-run", action="store_true")
    p_promote.add_argument("--verbose", "-v", action="store_true")
    p_promote.set_defaults(func=cmd_promote)

    # replay (P6 extension — closes the shadow-dream corruption mode)
    p_replay = sub.add_parser(
        "replay",
        help="Replay scoring/promotion against a FROZEN snapshot of research/entities/ "
             "(closes the corruption mode where bookkeeping reads from the graph it writes to)",
    )
    p_replay.add_argument("--source", metavar="FILE",
                          help="Source raw extract (auto-discovers all *-raw.md if omitted)")
    p_replay.add_argument("--commit", action="store_true",
                          help="Apply the proposed promotions to the live graph "
                               "(default: dry-run only — print would-promote counts)")
    p_replay.add_argument("--verbose", "-v", action="store_true")
    p_replay.set_defaults(func=cmd_replay)

    # synthesize
    p_synth = sub.add_parser("synthesize", help="Detect entity clusters for synthesis")
    p_synth.add_argument(
        "--gaps", action="store_true",
        help="Emit the ranked ## Gaps report (broken wikilinks, missing/over-long "
             "core_claim, highly-referenced stubs). pending_gaps is always written "
             "to status.json regardless of this flag.",
    )
    p_synth.add_argument(
        "--backlog", action="store_true",
        help="Emit high-leverage gaps as JSON Backlog ticket candidates "
             "(title/body/dedup_key) for filing via the Linear MCP. The engine "
             "does not file tickets itself (Linear-via-MCP + P20 quality pass).",
    )
    p_synth.add_argument("--backlog-cap", type=int, default=10,
                         help="Max Backlog candidates to emit (default 10).")
    p_synth.add_argument("--verbose", "-v", action="store_true")
    p_synth.set_defaults(func=cmd_synthesize)

    # lint
    p_lint = sub.add_parser("lint", help="Validate entity pages")
    p_lint.add_argument("--all", action="store_true", help="Lint all entity pages")
    p_lint.add_argument("--file", metavar="FILE", help="Lint a specific entity page")
    p_lint.add_argument(
        "--fix", action="store_true",
        help="Auto-repair mechanical related: format violations "
             "(bare slug / path-form → [[wikilink]]). core_claim issues are "
             "always left for manual fix. Idempotent.",
    )
    p_lint.add_argument(
        "--health", action="store_true",
        help="Print the 0-100 health score + dependency-ordered remediation plan. "
             "Implied by --all.",
    )
    p_lint.add_argument(
        "--temporal", action="store_true",
        help="Add non-blocking temporal-drift warnings for stale updated dates "
             "and undated mutable state claims/headings/labels. Opt-in; does "
             "not attempt semantic supersession or reconciliation.",
    )
    p_lint.add_argument("--verbose", "-v", action="store_true")
    p_lint.set_defaults(func=cmd_lint)

    # bench — retrieval benchmark (P@k / R@k / MRR) over the kg two-tier algorithm
    p_bench = sub.add_parser(
        "bench",
        help="Benchmark catalog+body retrieval (P@k / R@k / MRR) against a labeled fixture",
    )
    p_bench.add_argument("--fixture", metavar="PATH",
                         help="JSONL fixture (default: skills/bookkeeping/fixtures/brainbench.jsonl)")
    p_bench.add_argument("--k", type=int, default=5, help="Cutoff rank k (default 5)")
    p_bench.add_argument("--engine", choices=("real", "fork"), default="real",
                         help="'real' = drive the installed kg.py via subprocess "
                              "(production routing + A/B modes; default); 'fork' = "
                              "the hermetic in-process reference scorer (no kg.py "
                              "needed, no A/B modes).")
    p_bench.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_bench.set_defaults(func=cmd_bench)

    # status
    p_status = sub.add_parser("status", help="Print knowledge graph stats")
    p_status.set_defaults(func=cmd_status)

    # archive — Layer-2 retention window (BRO-1991)
    p_archive = sub.add_parser(
        "archive",
        help="Archive Layer-2 raw extracts past the retention window (default 30d)")
    p_archive.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS,
                           help=f"retention window in days (default {DEFAULT_RETENTION_DAYS})")
    p_archive.add_argument("--apply", action="store_true",
                           help="actually move the files (default is dry-run)")
    p_archive.set_defaults(func=cmd_archive)

    # merge — fold a duplicate entity into a canonical (tombstone + repoint, BRO-1442)
    p_merge = sub.add_parser(
        "merge", help="Merge a duplicate entity into a canonical (tombstone + repoint links)")
    p_merge.add_argument("dup", help="slug of the duplicate entity to fold away")
    p_merge.add_argument("canonical", help="slug of the canonical entity to keep")
    p_merge.add_argument("--dry-run", action="store_true",
                         help="report actions without writing")
    p_merge.add_argument(
        "--revision-link", metavar="REF",
        help="record that authorized the merge (default: the tombstone path)")
    p_merge.set_defaults(func=cmd_merge)

    # revise — explicit correction: record supersedes + revision_link (gh-156)
    p_revise = sub.add_parser(
        "revise",
        help="Record an explicit correction: ENTITY supersedes one or more records")
    p_revise.add_argument("--entity", required=True,
                          help="slug of the revising (current) entity")
    p_revise.add_argument(
        "--supersedes", required=True, nargs="+", metavar="SLUG",
        help="slug(s) this entity replaces; repeat or comma-separate")
    p_revise.add_argument(
        "--revision-link", required=True, metavar="REF",
        help="the record that authorized this revision (URL, ticket, doc path). "
             "Required: a supersession with no authorizing record is untraceable.")
    p_revise.add_argument(
        "--valid-from", metavar="YYYY-MM-DD",
        help="claim-effective date, when the revision supplies one. Omit when "
             "unknown — it is never guessed.")
    p_revise.add_argument("--dry-run", action="store_true",
                          help="report actions without writing")
    p_revise.set_defaults(func=cmd_revise)

    # query
    p_query = sub.add_parser("query", help="Find and display an entity page")
    p_query.add_argument("slug", help="Entity slug (fuzzy matched)")
    p_query.add_argument("--verbose", "-v", action="store_true")
    p_query.set_defaults(func=cmd_query)

    # render (Category B projection — MD canonical → single-file HTML)
    p_render = sub.add_parser(
        "render",
        help="Project a Layer 4 synthesis MD to a single-file HTML (Category B)",
    )
    p_render.add_argument("path", nargs="?", help="MD file or directory of -synthesis.md notes")
    p_render.add_argument("--layer", type=int, default=None,
                          help="Render all notes at the given layer (currently only 4)")
    p_render.add_argument("--link-html", action="store_true",
                          help="Rewrite [[slug]] to .html targets instead of .md")
    p_render.add_argument("--verbose", action="store_true", help="Print each rendered file")
    p_render.set_defaults(func=cmd_render)

    # index — dense LLM-loadable catalog (BRO-1223)
    p_index = sub.add_parser(
        "index",
        help="Generate the dense knowledge catalog at docs/knowledge-index.md (LLM-as-index substrate)",
    )
    p_index.add_argument("--compact", action="store_true",
                         help="Force compact preset (smaller caps; lower token budget). "
                              "Defaults to auto-compact when entity count exceeds "
                              f"{_CATALOG_AUTO_COMPACT_THRESHOLD}.")
    p_index.add_argument("--no-compact", action="store_true",
                         help="Disable auto-compact even when entity count is high.")
    p_index.add_argument("--dry-run", action="store_true",
                         help="Print the catalog to stdout without writing")
    p_index.set_defaults(func=cmd_index)

    return parser


def main() -> None:
    """Main entry point for the bookkeeping CLI."""
    # Dependency warnings (non-fatal)
    if not _GENAI_AVAILABLE:
        print(
            "[bookkeeping] Note: google-generativeai not installed. "
            "LLM judge disabled (heuristic-only scoring).",
            file=sys.stderr,
        )
    if not _YAML_AVAILABLE:
        print(
            "[bookkeeping] Note: PyYAML not installed. "
            "Frontmatter parsing and lint checks degraded.",
            file=sys.stderr,
        )

    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
