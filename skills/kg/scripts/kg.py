#!/usr/bin/env python3
"""
kg.py — knowledge graph loader (LLM-as-index routing layer).

Reads docs/knowledge-index.md (the dense catalog produced by `bookkeeping index`),
ranks entity blocks by topical relevance to a user-supplied topic, and prints
the top-N entity bodies as a single context block the agent can ingest.

This is the LOAD skill, not a query DSL. Querying is what the agent does
once loaded.

Architectural anchor: BRO-1223. Substrate is canonical markdown. The agent IS
the query engine. No SQLite mirror, no embeddings, no typed-edge schema.

Usage:
    python3 kg.py load "<topic>" [--n N] [--type T] [--json]
                [--terms "a,b"]...   # query expansion (repeatable; one value each)
                [--expand 1]         # also load 1-hop related: neighbours
                [--explain]          # per-signal score trace
    python3 kg.py info                     # catalog stats + top hubs

Exit codes:
    0  ok
    1  no catalog / no matches / user error
    2  internal error
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Resolve workspace root the same way bookkeeping does.
# BROOMVA_ROOT env var override unblocks non-standard host layouts (CI
# runners, co-developers with different paths). Closes BRO-1223 I5/I6.
BROOMVA_ROOT = Path(os.environ.get("BROOMVA_ROOT", Path.home() / "broomva"))
CATALOG_PATH = BROOMVA_ROOT / "docs" / "knowledge-index.md"
ENTITIES_DIR = BROOMVA_ROOT / "research" / "entities"
POLICY_PATH = BROOMVA_ROOT / ".control" / "policy.yaml"

# Defaults — used when policy.yaml is missing OR has no catalog: block.
# Each consumer (kg.py here, knowledge-catalog-refresh-hook.sh, bstack
# doctor.sh) bakes in the same default for its key, so the system stays
# governed-not-required: works without policy.yaml, respects policy.yaml
# when present.
_DEFAULT_STALE_WARN_HOURS = 24


def _load_catalog_policy() -> dict:
    """Read the catalog: block from .control/policy.yaml.

    Returns a dict with `stale_warn_hours`, falling back to defaults if
    policy.yaml is missing/malformed or has no `catalog:` block.
    PyYAML is a soft dependency — if absent, returns defaults.
    """
    defaults = {"stale_warn_hours": _DEFAULT_STALE_WARN_HOURS}
    if not POLICY_PATH.exists():
        return defaults
    try:
        import yaml
    except ImportError:
        return defaults
    try:
        data = yaml.safe_load(POLICY_PATH.read_text()) or {}
    except Exception:
        return defaults
    if not isinstance(data, dict):
        return defaults
    catalog = data.get("catalog")
    if not isinstance(catalog, dict):
        return defaults
    out = dict(defaults)
    for k in defaults:
        if k in catalog:
            try:
                out[k] = float(catalog[k])
            except (TypeError, ValueError):
                pass
    return out


# Maximum age in seconds before warning the catalog is stale.
# Read from policy.yaml at import time; falls back to 24h default.
# Bounds check: <=0 silently disables warnings → use default instead.
# (P20 C4 + haystack dogfood R5 — without this, `stale_warn_hours: 0.0001`
# floors to int(0.36) = 0 AFTER multiplication, re-triggering the same
# every-query-warning spam. Guard both before AND after the conversion.)
_stale_hours_value = _load_catalog_policy()["stale_warn_hours"]
if not isinstance(_stale_hours_value, (int, float)) or _stale_hours_value <= 0:
    _stale_hours_value = _DEFAULT_STALE_WARN_HOURS
STALE_WARN_SECONDS = int(_stale_hours_value * 3600)
if STALE_WARN_SECONDS <= 0:
    # Sub-hour fractional input survived the pre-multiplication guard but
    # floored to zero. Fall back to the default rather than spam stderr.
    STALE_WARN_SECONDS = int(_DEFAULT_STALE_WARN_HOURS * 3600)


# Tier-2 (body-grep) auto-fires not only when tier-1 returns too few hits, but
# also when tier-1's BEST hit is weak — "low confidence". A weak top score means
# the catalog matched only on a substring/single signal, which is exactly when a
# body-only entity is likely to be the real answer (the dominant miss class in
# `bookkeeping bench`: paraphrase / body-only queries that fill the top-n with
# weak distractors so the old `count < n` gate never fired). On the additive
# rubric (score_entity): an exact slug hit = 10/term, tag-exact = 4, claim = 3 —
# so a genuine multi-signal match scores ≳ 18, while a lone substring hit scores
# 3–10. The floor sits between. Calibrated against the 62-query gold-set (BRO-1426):
# it recovers the +~10pp R@5 that `--body-search` gave, while confident exact-match
# queries (top ≥ floor) still skip the body read. Override per-call via --tier2-floor.
TIER2_CONFIDENCE_FLOOR = 18


# ── Catalog parsing ───────────────────────────────────────────────────────────

class CatalogEntry:
    """One parsed entity block from the catalog."""

    __slots__ = ("slug", "type", "status", "score", "claim", "out_links",
                 "in_links", "tags", "sources", "aliases", "rel_path", "raw_block")

    def __init__(self, slug: str):
        self.slug: str = slug
        self.type: str = ""
        self.status: str = ""
        self.score = None
        self.claim: str = ""
        self.out_links: list = []
        self.in_links: list = []
        self.tags: list = []
        self.sources: list = []
        self.aliases: list = []  # alternate names (kepano synonym layer + merged-slug routing, BRO-1423)
        self.rel_path: str = ""  # path relative to research/entities/ (v2+)
        self.raw_block: str = ""


def parse_catalog(text: str) -> tuple[dict, list]:
    """Parse the dense catalog into (metadata, [CatalogEntry, ...]).

    Supports both schemas:
        dense-catalog-v1 (3-line block): header / claim / out·in·tags·src
        dense-catalog-v2 (4-line block): + path line, pipe-separated sources

    The v2 path line eliminates slug-clash routing ambiguity:
    multi-directory slug clashes get a single catalog entry (sorted
    last-write wins), and the `path:` field tells the loader exactly
    which file that entry describes. Without it, kg.py would rglob and
    pick an arbitrary match. With it, load is deterministic.

    v2 also pipe-separates sources because moltbook URLs routinely
    contain parenthetical commas; comma-splitting fragments ~9% of
    sources. The parser handles both `, ` (v1) and ` | ` (v2) for
    forward/backward compat — if a `src:` block contains ` | ` it's
    v2; otherwise v1.
    """
    metadata: dict = {}

    # Parse YAML frontmatter (between --- markers)
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                metadata[k.strip()] = v.strip()
        text = text[fm_match.end():]

    entries: list = []
    # Match each entity block: header + claim + meta + optional path
    # - score is `[^\n]+?` (rest-of-line, non-greedy) — accepts "7", "7/9",
    #   "high", AND space-bearing values like a dict repr ("{'total': '6/9', …}").
    #   Defensive: a malformed/space-bearing score must NEVER drop the whole
    #   block. The old `\S+` stopped at the first space, so a dict-repr score
    #   (emitted by bookkeeping for stub-deterministic entities) made the block
    #   fail to match and silently vanish from routing — 23 entities at 370.
    #   Root cause is fixed upstream (bookkeeping emits a scalar); this is the
    #   belt-and-braces so the loader is robust to any future score shape.
    # - meta_line is `[^\n]*` (may be empty for entities without edges/tags)
    # - path line is optional (forward-compat with v1 catalogs)
    block_re = re.compile(
        r"^####\s+(\S+)\s+\[([^\]·]+)·([^\]]+)\](?:\s*·\s*score\s+([^\n]+?))?\s*\n"
        r"([^\n]*)\n"
        r"([^\n]*)"
        r"(?:\npath:\s+(\S+))?\n",
        re.MULTILINE,
    )

    for m in block_re.finditer(text):
        slug, type_val, status, score, claim, meta_line, rel_path = m.groups()
        e = CatalogEntry(slug.strip())
        e.type = type_val.strip()
        e.status = status.strip()
        # Score kept as string — accepts "7", "7/9", "high", etc.
        e.score = score.strip() if score else None
        e.claim = claim.strip()
        e.rel_path = rel_path.strip() if rel_path else ""
        e.raw_block = m.group(0)

        # Parse meta_line: → A, B · ← C, D · #tag1 #tag2 · src: source1 | source2
        meta_parts = [p.strip() for p in meta_line.split("·")]
        for part in meta_parts:
            if part.startswith("→ "):
                e.out_links = [x.strip() for x in part[2:].split(",") if x.strip()]
            elif part.startswith("← "):
                e.in_links = [x.strip() for x in part[2:].split(",") if x.strip()]
            elif part.startswith("#"):
                e.tags = [t.lstrip("#").strip() for t in part.split() if t.startswith("#")]
            elif part.startswith("aka: "):
                # Alternate names (BRO-1423): comma-separated. Scored like slugs
                # so a query for an alias routes to this entity.
                e.aliases = [x.strip() for x in part[5:].split(",") if x.strip()]
            elif part.startswith("src: "):
                src_str = part[5:]
                # v2 uses ' | ' separator (robust to commas in source URLs).
                # Fall back to ',' for v1 catalogs.
                if " | " in src_str:
                    e.sources = [x.strip() for x in src_str.split(" | ") if x.strip()]
                else:
                    e.sources = [x.strip() for x in src_str.split(",") if x.strip()]

        entries.append(e)

    return metadata, entries


# ── Relevance scoring ─────────────────────────────────────────────────────────

def score_entity(entry: "CatalogEntry", topic_terms: list, body_text: str = "",
                 trace: "list | None" = None) -> int:
    """Score an entity for topical relevance.

    Scoring rubric (additive, all case-insensitive):
        +10  any topic_term is exactly the slug
        +8   any topic_term is exactly an alias (BRO-1423 — an alias is a
             deliberate alternate identity, incl. a merged-away dup's slug;
             scored just below the slug so querying an alias routes here)
        +5   any topic_term is a substring of the slug
        +4   any topic_term is a substring of an alias
        +4   any topic_term matches a tag exactly
        +3   any topic_term is a substring of any tag
        +3   any topic_term appears in the claim
        +2   any topic_term appears in the body (only checked if body provided)
        +1   any topic_term appears in any out_link or in_link slug
        +1   any topic_term appears in any source

    If `trace` is a list, each contributing signal is appended as a
    (label, points) tuple — this powers `--explain` with zero cost on the
    hot path (callers that don't explain pass trace=None).
    """
    score = 0
    slug_l = entry.slug.lower()
    claim_l = entry.claim.lower()
    aliases_l = [a.lower() for a in entry.aliases]
    tags_l = [t.lower() for t in entry.tags]
    sources_l = [s.lower() for s in entry.sources]
    links_l = [s.lower() for s in (entry.out_links + entry.in_links)]
    body_l = body_text.lower() if body_text else ""

    def _hit(label: str, pts: int) -> None:
        nonlocal score
        score += pts
        if trace is not None:
            trace.append((label, pts))

    for t in topic_terms:
        if t == slug_l:
            _hit(f"slug=={t}", 10)
        elif t in slug_l:
            _hit(f"slug~{t}", 5)

        for alias in aliases_l:
            if alias == slug_l:
                continue  # a self-alias would double-count the slug hit (BRO-1423 review)
            if t == alias:
                _hit(f"alias=={t}", 8)
                break
            elif t in alias:
                _hit(f"alias~{t}", 4)
                break

        for tag in tags_l:
            if t == tag:
                _hit(f"tag=={t}", 4)
                break
            elif t in tag:
                _hit(f"tag~{t}", 3)
                break

        if t in claim_l:
            _hit(f"claim~{t}", 3)

        if body_l and t in body_l:
            _hit(f"body~{t}", 2)

        if any(t in lk for lk in links_l):
            _hit(f"link~{t}", 1)

        if any(t in s for s in sources_l):
            _hit(f"src~{t}", 1)

    return score


def tokenize_topic(topic: str) -> list:
    """Split a topic into searchable terms (lowercase, no punctuation, no stopwords)."""
    # Tokenize on whitespace + punctuation, keep underscores
    tokens = re.findall(r"[a-z0-9_-]+", topic.lower())
    # Drop common english stopwords that add no signal
    stopwords = {
        "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
        "with", "as", "is", "are", "was", "were", "be", "been", "do", "does", "did",
        "from", "by", "at", "what", "how", "why", "when", "where", "all", "any",
        "this", "that", "these", "those", "i", "you", "we", "they", "it", "its",
        "their", "them", "us", "our",
    }
    return [t for t in tokens if t not in stopwords and len(t) >= 2]


# ── Output rendering ──────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def render_load_output(
    topic: str,
    matches: list,
    metadata: dict,
    total_in_catalog: int,
    full_bodies: bool,
    explain_traces: "dict | None" = None,
) -> str:
    """Render the human/agent-readable load output."""
    out: list = []
    sep = "═" * 70

    n_primary = sum(1 for m in matches if m[3] is None)
    n_expand = len(matches) - n_primary

    generated = metadata.get("generated", "?")
    out.append(sep)
    out.append(f" KG LOAD: {topic}")
    out.append(sep)
    out.append("")
    loaded_line = (f"Loaded {len(matches)}/{total_in_catalog} entities "
                   f"from docs/knowledge-index.md")
    if n_expand:
        loaded_line += f"  ({n_primary} matched + {n_expand} via graph expansion)"
    out.append(loaded_line)
    out.append(f"(catalog generated {generated})")
    out.append("")

    total_bytes = 0
    for idx, (score, entry, body_path, via) in enumerate(matches, 1):
        score_str = f"score {entry.score}" if entry.score is not None else "—"
        via_tag = f" ↳ via {via}" if via else ""
        out.append(f"╭─ #{idx} · relevance {score} · {score_str} ── "
                   f"{entry.slug} [{entry.type}·{entry.status}]{via_tag} " + "─" * 8)
        out.append(f"│ Source: {body_path.relative_to(BROOMVA_ROOT)}")
        out.append(f"│ Claim: {entry.claim}")
        if entry.out_links:
            out.append(f"│ → {', '.join(entry.out_links)}")
        if entry.tags:
            out.append(f"│ Tags: {', '.join(entry.tags)}")
        if explain_traces is not None:
            tr = explain_traces.get(entry.slug, [])
            catalog_sum = sum(p for _, p in tr)
            sig = "  ".join(f"{lbl}(+{p})" for lbl, p in tr) or "(no catalog signal)"
            out.append(f"│ explain: {sig} = {catalog_sum} catalog")
            residual = score - catalog_sum
            if residual > 0:
                out.append(f"│          (+{residual} tier-2 body grep)")
        out.append("│ " + "─" * 60)
        if full_bodies:
            try:
                body = body_path.read_text(errors="replace")
                total_bytes += len(body)
                # Indent the body for visual separation
                for line in body.splitlines():
                    out.append(f"│ {line}")
            except Exception as exc:
                out.append(f"│ (failed to read: {exc})")
        out.append("╰" + "─" * 68)
        out.append("")

    out.append(sep)
    if full_bodies:
        out.append(f" Total entity body bytes loaded: {total_bytes/1024:.1f} KB "
                   f"(~{estimate_tokens(' '.join(out))} tokens including this header)")
    out.append(sep)

    return "\n".join(out)


def render_json_output(topic: str, matches: list, metadata: dict, full_bodies: bool) -> str:
    payload = {
        "topic": topic,
        "catalog_generated": metadata.get("generated"),
        "matches": [
            {
                "rank": idx,
                "relevance_score": rscore,
                "slug": e.slug,
                "type": e.type,
                "status": e.status,
                "score": e.score,
                "claim": e.claim,
                "out_links": e.out_links,
                "in_links": e.in_links,
                "tags": e.tags,
                "sources": e.sources,
                "path": str(body_path.relative_to(BROOMVA_ROOT)),
                "via": via,  # None=primary match, "<seed>"=1-hop expansion
                "body": body_path.read_text(errors="replace") if full_bodies else None,
            }
            for idx, (rscore, e, body_path, via) in enumerate(matches, 1)
        ],
    }
    return json.dumps(payload, indent=2)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_load(args: argparse.Namespace) -> int:
    """Load top-N entities for the topic.

    Two-tier scoring:
      Tier 1 — catalog-only score (claim + tags + slug + links + sources).
               Fast (~5ms) and zero filesystem hits beyond the catalog.
      Tier 2 — entity-body grep, only triggered when tier 1 returns fewer
               than N matches (or --body-search is forced). Slower
               (~300ms for ~250 entities) but recovers entities whose
               topic appears only in prose, not the dense catalog.

    The two-tier approach honors the LLM-as-index architecture: the
    catalog routes for terms it knows about; the body grep is the
    "load on demand" fallback for terms the catalog can't see.
    """
    if not args.topic:
        print("Usage: kg.py load \"<topic>\" [--n N]", file=sys.stderr)
        return 1

    if not CATALOG_PATH.exists():
        print(f"[kg] catalog not found at {CATALOG_PATH}. "
              "Regenerate with: python3 skills/bookkeeping/scripts/bookkeeping.py index",
              file=sys.stderr)
        return 1

    age = time.time() - CATALOG_PATH.stat().st_mtime
    if age > STALE_WARN_SECONDS and not args.quiet:
        hrs = int(age / 3600)
        print(f"[kg] warning: catalog is {hrs}h old. "
              "Consider regenerating with `bookkeeping index`.",
              file=sys.stderr)

    text = CATALOG_PATH.read_text(errors="replace")
    metadata, entries = parse_catalog(text)

    if not entries:
        print(f"[kg] catalog at {CATALOG_PATH} has no parseable entity blocks",
              file=sys.stderr)
        return 1

    if args.type:
        entries = [e for e in entries if e.type == args.type]
        if not entries:
            print(f"[kg] no entities of type '{args.type}' in catalog", file=sys.stderr)
            return 1

    topic_terms = tokenize_topic(args.topic)
    # Query expansion (A): agent-supplied synonym/variant terms are scored
    # alongside the topic. The agent is already in the loop, so it IS the
    # query expander — QMD fine-tunes a 1.7B model for this only because it
    # runs headless. Each --terms value may itself be comma/space separated.
    # Dedupe preserving order so the topic's own terms keep priority.
    if getattr(args, "terms", None):
        for extra in args.terms:
            topic_terms.extend(tokenize_topic(extra))
        topic_terms = list(dict.fromkeys(topic_terms))
    if not topic_terms:
        print(f"[kg] topic '{args.topic}' tokenized to nothing meaningful "
              "(all stopwords or punctuation)", file=sys.stderr)
        return 1

    # Tier 1: catalog-only scoring (fast — claim + tags + slug + links + sources)
    scored = []
    by_slug = {e.slug: e for e in entries}
    for e in entries:
        s = score_entity(e, topic_terms)
        if s > 0:
            scored.append((s, e))

    # Tier 2: body grep fallback — fires when catalog signal is insufficient.
    # Trigger conditions (any):
    #   - --body-search flag forces it always
    #   - tier 1 returned fewer than args.n matches (too FEW hits)
    #   - tier 1's best hit is below the confidence floor (hits too WEAK) — this
    #     is the auto-recall gate: a query with ≥n weak distractors used to
    #     suppress tier-2 and never surface the body-only answer (BRO-1426).
    # Body scoring uses the same rubric as tier 1 but reads file content;
    # adds +2 per topic term that appears in the body. Already-scored
    # entities accumulate body bonus; new entities enter scored list.
    tier1_hits = len(scored)
    tier1_top = max((s for s, _ in scored), default=0)
    _floor_arg = getattr(args, "tier2_floor", None)
    floor = _floor_arg if _floor_arg is not None else TIER2_CONFIDENCE_FLOOR
    low_confidence = tier1_top < floor
    tier2_added = 0
    if args.body_search or tier1_hits < args.n or low_confidence:
        slug_to_score = {e.slug: s for s, e in scored}
        for e in entries:
            # Skip if filesystem path is unknown (catalog v1 entries without path:)
            body_path = (ENTITIES_DIR / e.rel_path) if e.rel_path else None
            if body_path is None or not body_path.exists():
                # Fall back to rglob
                candidates = list(ENTITIES_DIR.rglob(f"{e.slug}.md"))
                candidates = [p for p in candidates if ".lago-blobs" not in p.parts]
                if not candidates:
                    continue
                body_path = candidates[0]
            try:
                body = body_path.read_text(errors="replace").lower()
            except Exception:
                continue
            body_bonus = sum(2 for t in topic_terms if t in body)
            if body_bonus > 0:
                old_score = slug_to_score.get(e.slug, 0)
                new_score = old_score + body_bonus
                slug_to_score[e.slug] = new_score
                if old_score == 0:
                    tier2_added += 1
        # Rebuild scored list from updated map
        scored = [(s, by_slug[slug]) for slug, s in slug_to_score.items() if s > 0]

    if not scored:
        print(f"[kg] no entities matched topic terms {topic_terms} "
              f"(neither catalog nor body)", file=sys.stderr)
        return 1

    if not args.quiet and tier2_added > 0:
        print(f"[kg] tier-2 body search added {tier2_added} entities "
              f"(tier-1 catalog scoring found {tier1_hits})", file=sys.stderr)

    # Hub-aware tiebreak (D): at equal topical relevance, prefer the more
    # central entity (higher catalog in-degree) over arbitrary alphabetical
    # order. `in_links` is capped by the catalog preset (top-5 full / top-3
    # compact), so this is a capped centrality proxy — enough to beat a pure
    # alpha tiebreak and capture most of the value of a hub-rank RRF term.
    scored.sort(key=lambda x: (-x[0], -len(x[1].in_links), x[1].slug))
    top = scored[: args.n]
    score_by_slug = {e.slug: s for s, e in scored}

    # Graph 1-hop expansion (B): optionally pull the `related:` neighbours of
    # the top hits into the load. This is the structural advantage flat-
    # document search engines (QMD, BM25) cannot offer — the agent gets the
    # matched entities AND their immediate graph neighbourhood, automating the
    # manual "reading frontier" step. Neighbours are deduped against the
    # primary set, ranked by their own relevance then in-degree, and capped at
    # --n so a hub neighbour (e.g. `arcan`, in-degree 111) cannot explode load.
    expansion: list = []  # (seed_slug, entry)
    expand_hops = getattr(args, "expand", 0) or 0
    # Only 1-hop is supported for now. Each match carries a single `via` (its
    # immediate parent); at hop 1 every parent is a primary top-N entity, which
    # is always present in the result set, so provenance can never dangle.
    # Deeper hops would need full-ancestry tracking + ancestor-preserving caps
    # (a capped flat list can keep a deep node while dropping its intermediary)
    # — deferred. Clamp values >1 to 1 with a note rather than mislabel depth.
    if expand_hops > 1:
        if not args.quiet:
            print("[kg] note: --expand currently supports a single hop; "
                  "clamping to 1.", file=sys.stderr)
        expand_hops = 1
    if expand_hops > 0:
        if args.type and not args.quiet:
            # by_slug only holds the type-filtered set, so cross-type related:
            # edges (the common case) won't resolve — say so rather than return
            # a silently-empty neighbourhood.
            print(f"[kg] note: --expand neighbours are limited to type='{args.type}' "
                  "(cross-type related: edges aren't resolved under --type)",
                  file=sys.stderr)
        primary_slugs = {e.slug for _, e in top}
        seen_exp: set = set()
        frontier = [e for _, e in top]
        for _hop in range(expand_hops):
            next_frontier = []
            for seed in frontier:
                for nb_slug in (seed.out_links + seed.in_links):
                    nb = by_slug.get(nb_slug)
                    if nb is None or nb.slug in primary_slugs or nb.slug in seen_exp:
                        continue
                    seen_exp.add(nb.slug)
                    expansion.append((seed.slug, nb))
                    next_frontier.append(nb)
            frontier = next_frontier
        expansion.sort(key=lambda se: (-score_by_slug.get(se[1].slug, 0),
                                       -len(se[1].in_links), se[1].slug))
        expansion = expansion[: args.n]

    # Phase 2: resolve to filesystem paths.
    # Catalog v2 carries explicit `path:` per entity — load that file exactly
    # (no rglob ambiguity on slug clashes). Falls back to rglob for v1.
    def _resolve_body(e: "CatalogEntry"):
        if e.rel_path:
            candidate = ENTITIES_DIR / e.rel_path
            if candidate.exists():
                return candidate
        candidates = [p for p in ENTITIES_DIR.rglob(f"{e.slug}.md")
                      if ".lago-blobs" not in p.parts]
        return candidates[0] if candidates else None

    # matches tuple: (relevance_score, entry, body_path, via)
    #   via=None        → primary topical match
    #   via="<seed>"    → pulled in by --expand as a 1-hop neighbour of <seed>
    matches: list = []
    for rscore, e in top:
        body_path = _resolve_body(e)
        if body_path is None:
            continue  # Skip entities whose files we can't locate (catalog drift)
        matches.append((rscore, e, body_path, None))
    for seed_slug, e in expansion:
        body_path = _resolve_body(e)
        if body_path is None:
            continue
        matches.append((score_by_slug.get(e.slug, 0), e, body_path, seed_slug))

    if not matches:
        print(f"[kg] matched {len(top)} entities in catalog but no body files found "
              "(catalog may be stale)", file=sys.stderr)
        return 1

    # --explain (C): compute per-entity catalog-signal traces for the matched
    # set only (top-N — cheap). Body-grep bonus shows as a residual line.
    explain_traces = None
    if getattr(args, "explain", False):
        explain_traces = {}
        for _rs, e, _bp, _via in matches:
            tr: list = []
            score_entity(e, topic_terms, trace=tr)
            explain_traces[e.slug] = tr

    full = not args.no_bodies
    if args.json:
        print(render_json_output(args.topic, matches, metadata, full_bodies=full))
    else:
        print(render_load_output(
            args.topic, matches, metadata, len(entries), full_bodies=full,
            explain_traces=explain_traces,
        ))

    return 0


def cmd_info(_args: argparse.Namespace) -> int:
    """Print catalog stats + top hubs."""
    if not CATALOG_PATH.exists():
        print(f"[kg] catalog not found at {CATALOG_PATH}", file=sys.stderr)
        return 1

    text = CATALOG_PATH.read_text(errors="replace")
    metadata, entries = parse_catalog(text)

    age = time.time() - CATALOG_PATH.stat().st_mtime
    age_h = age / 3600

    print(f"Catalog: {CATALOG_PATH.relative_to(BROOMVA_ROOT)}")
    print(f"  generated: {metadata.get('generated', '?')}")
    print(f"  age:       {age_h:.1f}h")
    print(f"  entities:  {len(entries)}")
    print(f"  schema:    {metadata.get('schema', '?')}")
    print()

    # Type breakdown from parsed entries
    by_type: dict = {}
    for e in entries:
        by_type[e.type] = by_type.get(e.type, 0) + 1
    print("By type:")
    for t in sorted(by_type, key=lambda x: -by_type[x]):
        print(f"  {t:24s} {by_type[t]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kg",
        description="Knowledge graph loader (LLM-as-index routing layer)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_load = sub.add_parser("load", help="Load top-N entities for a topic")
    p_load.add_argument("topic", help="Free-form topic to load entities for")
    p_load.add_argument("--n", type=int, default=10,
                        help="Number of entities to load (default 10)")
    p_load.add_argument("--type", help="Restrict to entity type (concept, pattern, …)")
    p_load.add_argument("--terms", action="append", metavar="TERM",
                        help="Query expansion: extra synonym/variant terms to score "
                             "alongside the topic. Repeatable (one value per flag), and "
                             "each value may be comma/space-separated "
                             "(e.g. --terms 'retrieval,recall').")
    p_load.add_argument("--expand", type=int, default=0, metavar="HOPS",
                        help="Graph expansion: also load the 1-hop `related:` neighbours "
                             "of the top hits (adds up to --n more entities, so total "
                             "load is at most 2x--n; values >1 clamp to 1 for now; "
                             "default 0 = off).")
    p_load.add_argument("--explain", action="store_true",
                        help="Show the per-signal score trace for each loaded entity.")
    p_load.add_argument("--json", action="store_true", help="Machine-readable output")
    p_load.add_argument("--no-bodies", action="store_true",
                        help="Skip entity body content (catalog blocks only)")
    p_load.add_argument("--body-search", action="store_true",
                        help="Force tier-2 entity-body grep. By default tier-2 "
                             "auto-fires when tier-1 returns fewer than --n hits OR "
                             "its best hit is below the confidence floor; this forces "
                             "it unconditionally.")
    p_load.add_argument("--tier2-floor", type=int, default=None, metavar="SCORE",
                        help=f"Tier-1 top-score below which tier-2 auto-fires "
                             f"(default {TIER2_CONFIDENCE_FLOOR}). Set 0 to disable the "
                             f"confidence gate (tier-2 then fires only on count<--n).")
    p_load.add_argument("--quiet", action="store_true", help="Suppress staleness warnings")
    p_load.set_defaults(func=cmd_load)

    p_info = sub.add_parser("info", help="Print catalog stats")
    p_info.set_defaults(func=cmd_info)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
