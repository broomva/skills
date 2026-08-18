# Entity Page Schema

This document defines the canonical YAML frontmatter schema for all entity pages in the knowledge graph. Every file under `research/entities/` must conform to this schema. Agents creating or modifying entity pages must validate against these rules before writing.

---

## 1. Full Annotated Schema

```yaml
---
# ── IDENTITY ──────────────────────────────────────────────────────────────────
id: "{type}/{slug}"
# Required. Unique stable identifier. Format: "{entity_type}/{kebab-case-slug}".
# Example: "concept/rope-embeddings". Never change after creation — slugs are
# used as wikilink targets throughout the graph.

title: "{Human-Readable Title}"
# Required. Display name for the entity. Title case. ≤ 80 characters.

type: concept | pattern | tool | person | project | discovery | question
# Required. Primary entity type. See Section 2 for type definitions.

status: raw | candidate | entity | synthesis | archived
# Required. Current lifecycle stage. See Section 3 for transitions.

created: "YYYY-MM-DD"
# Required. ISO date of first creation (not first discovery).

updated: "YYYY-MM-DD"
# Required. ISO date of most recent substantive edit. Update on every write.

# ── CLASSIFICATION ────────────────────────────────────────────────────────────
tags:
  - "{tag}"
# Required. At least one tag. Use kebab-case. Tags MUST come from the controlled
# vocabulary in research/entities/_tags.md (81 canonical tags, 4 facets).
# `lint` warns (non-breaking) on: missing tags, tags not in the vocabulary, and
# type-redundant tags (a tag equal to `type:` — the type field already encodes
# it, so `tags: [concept]` on a concept entity is forbidden). Run the migration
# to normalize. The vocabulary lint no-ops if _tags.md is absent.

module: "{project-or-domain}"
# Optional. Which Broomva project or research domain this entity primarily
# belongs to. Examples: "life-agent-os", "noesis", "haima", "general-ml".
# Omit if the entity is domain-agnostic.

layer: 3
# Required. 3 for Layer-3 entity pages (the common case).
# Layer-4 synthesis pages carry `layer: 4` and use their own template.
#
# `layer` records WHAT A PAGE IS; `status` records HOW FAR ALONG IT IS. The two
# are independent axes, and the §3 status lifecycle applies unchanged at BOTH
# layers — a `layer: 4` page is promoted to `status: entity` by the same trigger
# as a `layer: 3` one. (Before 2026-08-18 this comment read "Always 3 for entity
# pages", which was read as forbidding `layer: 4` + `status: entity` and left all
# three Layer-4 pages permanently stuck at `candidate` with no reachable terminal
# state. BRO-2180.)

# ── PROVENANCE ────────────────────────────────────────────────────────────────
sources:
  - post_id: "{platform-unique-id}"
    # Optional. Platform-specific post ID (tweet ID, Moltbook thread ID, etc.).
    # Use when available for deduplication. Omit for non-social sources.
    url: "{full-url}"
    # Required per source. Canonical URL. For social posts, use permalink.
    type: moltbook | x-reply | x-thread | web-article | research-paper | conversation | github | internal-doc
    # Required per source. Controls novelty prior in scoring.
    author: "{handle-or-name}"
    # Optional. Author identifier. Use @handle for social, full name for papers.
    extraction_date: "YYYY-MM-DD"
    # Required per source. When this source was processed.
    raw_extract_file: "YYYY-MM-DD-{run-id}-raw.md"
    # Optional. Link back to the Layer 2 file this came from.
    item_number: {N}
    # Optional. Item number within the raw extract file (for traceability).
# Sources list must have at least one entry. Multiple sources strengthen the
# entity and can raise the effective novelty score if they converge independently.

# ── SCORING ───────────────────────────────────────────────────────────────────
scoring:
  raw_score: {0-9}
  # Required. Sum of novelty + specificity + relevance.
  novelty: {0-3}
  # Required. Score on Nous gate Dimension 1.
  specificity: {0-3}
  # Required. Score on Nous gate Dimension 2.
  relevance: {0-3}
  # Required. Score on Nous gate Dimension 3.
  pass: heuristic | llm-judge | human
  # Required. Which pass produced the final score.
  # "heuristic" = Pass 1 only (score was unambiguous: ≤2 or ≥7)
  # "llm-judge" = Pass 2 invoked (score was in ambiguous band 3–6)
  # "human" = manually reviewed and overridden
  promoted_by: "{agent-id-or-human}"
  # Required. Who promoted this item. Use "claude-sonnet-4-6" for Claude sessions,
  # "human" for manual promotions, or a named agent ID.
  promoted_at: "YYYY-MM-DD"
  # Required. When the promotion decision was made.
  blog_candidate: true | false
  # Required. Whether this entity meets blog candidate criteria from scoring-rubric.md.
  priority: true | false
  # Required. True if raw_score ≥ 7. Triggers synthesis candidate flag.

# ── GRAPH ─────────────────────────────────────────────────────────────────────
related:
  - "[[{entity-slug}]]"
  # Optional. Entities that share conceptual space with this one. Use wikilink
  # format. Brief annotation on the line below each wikilink is encouraged.
  # Example:
  #   - "[[rope-embeddings]]"  # same rotary position encoding family

contradicts:
  - "[[{entity-slug}]]"
  # Optional. Entities that make claims conflicting with this entity's core claim.
  # Always populate a resolution section in the entity body when this is set —
  # `lint` warns (non-breaking) if a NON-EMPTY contradicts list lacks a body
  # `## Contradiction`/`## Resolution` heading. An empty `contradicts: []` is fine.
  # See promotion-workflow.md § Contradiction Detection Protocol.

compounds_from:
  - "[[{entity-slug}]]"
  # Optional. Entities that were combined or synthesized to produce this one.
  # Use when this entity emerges from a Layer 4 synthesis operation.

# ── CONTENT METADATA ──────────────────────────────────────────────────────────
core_claim: "{one sentence ≤ 140 characters}"
# Required. The central assertion of this entity in a single tweet-sized sentence.
# Must be falsifiable or at least precise. Not a category label — a claim.
# Bad:  "RoPE is a positional encoding technique."
# Good: "RoPE extends context length without retraining by rotating Q/K in freq space."

open_questions_count: {N}
# Required. Count of open questions listed in the entity body. Keep in sync.

implementation_status: implemented | designed | experimental | open-question | not-applicable
# Required. Whether the concept has been implemented in this workspace.
# "not-applicable" for concepts/people/discoveries where implementation isn't meaningful.

# ── TEMPORAL REVISION ENVELOPE ────────────────────────────────────────────────
# Four typed fields with deliberately different provenance rules. Full write-side
# contract: references/temporal-revision-envelope.md. Validation is warning-only
# and opt-in (`lint --temporal`); none of these fields is required, and default
# lint never reports on them.

recorded_at: "YYYY-MM-DD"
# Optional, machine-written. SYSTEM time — when the graph recorded this state.
# Stamped by `promote` on creation and re-stamped on a substantive update. Never
# operator-supplied. Distinct from `updated`, which tracks the page; this tracks
# the record. Pages predating the envelope are not backfilled by the update path.

valid_from: "YYYY-MM-DD"
# Optional. CLAIM-EFFECTIVE time — when the claim became true. Written only when
# a source (raw item `metadata.valid_from`) or an explicit `revise --valid-from`
# supplies it. NEVER inferred from prose, from dates elsewhere in the page, or
# from the ingest timestamp. An absent value means "not stated", which is the
# honest answer; a defaulted one would assert something nobody claimed.

supersedes:
  - "[[{entity-slug}]]"
# Optional. Records this page replaces. Emitted ONLY by an explicit correction
# workflow (`bookkeeping revise`, or `bookkeeping merge` on the canonical) —
# never inferred from present-tense prose, however emphatic. Entries must be
# [[wikilink]] form and must resolve to an entity file (a merge tombstone
# resolves deliberately: superseding a merged-away slug is the normal case).

revision_link:
  - "{url-ticket-or-doc-path}"
# Optional, but REQUIRED whenever `supersedes` is non-empty. The record(s) that
# authorized the supersession. Without it, a replacement asserts that something
# was superseded while saying nothing about who decided that, or on what basis.
#
# A LIST, because a page can be corrected more than once and each correction has
# its own authorizing record; a scalar that each revision overwrote would leave
# the latest ticket claiming authorship of every earlier supersession. A
# hand-authored scalar is still accepted on read and normalised to a one-element
# list on the next write.
#
# KNOWN LIMITATION: which link authorized which `supersedes` entry is NOT
# represented. The pair says "these records were replaced, on the authority of
# these decisions" and no more. Per-entry binding is tracked separately.
---
```

---

## 2. Entity Type Definitions

| Type | Definition | Typical `core_claim` shape |
|------|------------|---------------------------|
| **concept** | An abstract idea, principle, or mechanism. Not tied to a specific implementation. | "X works by doing Y, which enables Z." |
| **pattern** | A recurring solution to a recurring problem. Has applicability conditions. | "When X, apply Y to get Z." |
| **tool** | A software library, framework, CLI, API, or instrument. | "Tool X does Y, notable for Z." |
| **person** | A named individual relevant to the knowledge graph (researcher, founder, practitioner). | "{Name} is known for X, which matters because Y." |
| **project** | An internal or external project tracked in the graph. | "Project X does Y, currently at stage Z." |
| **discovery** | An empirical finding, benchmark result, or observed phenomenon. | "Finding: X produces Y under condition Z." |
| **question** | An open question that hasn't been answered yet. Acts as a placeholder in the graph. | "Unknown: how does X relate to Y in context Z?" |

**Multiple types:** A single entity can exhibit multiple types (e.g., a tool that is also a discovery). Use the primary type in the `type` field and add secondary types as tags (e.g., `tags: [tool, discovery]`).

---

## 3. Status Lifecycle

```
raw → candidate → entity → synthesis → archived
```

| Status | Meaning | Transition Trigger |
|--------|---------|-------------------|
| **raw** | Extracted but not yet reviewed. May have errors. | Created by automated extraction or Pass 1 heuristic. |
| **candidate** | Promoted by LLM judge with `confidence: low`. Needs human verification. | Pass 2 judge outputs `confidence: low` + `decision: promote`. |
| **entity** | Verified, clean, ready to participate in graph traversal. Valid at `layer: 3` and `layer: 4` alike. | Human or high-confidence judge confirms. |
| **synthesis** | Entity has been **incorporated into** a Layer-4 synthesis note. Note this describes being *cited by* one — it is not the status of a page that *is* a Layer-4 synthesis; such a page uses `entity` like any other. | Synthesis note lists this entity in `compounds_from`. |
| **archived** | Superseded, disproved, or no longer relevant. Kept for provenance. | Manual decision; add `archived_reason` field when archiving. |

---

## 4. Validation Rules

Agents must enforce these rules when creating or modifying entity pages:

1. **`core_claim` ≤ 140 characters.** Count characters including spaces. If you cannot state the claim in 140 chars, it is not a claim — it is a category. Sharpen it.

2. **`sources` must have at least one entry.** An entity with no provenance is untrustworthy. If the source is an internal insight (conversation extract), cite the session file.

3. **`related`, `contradicts`, `compounds_from` must use `[[wikilink]]` format.** Plain text references are not graph edges. The wikilink must exactly match the `id` slug of the target entity.

4. **`updated` must be today's date** on every write. This is not optional. Stale `updated` dates break graph audit. The opt-in `lint --temporal` audit also warns when `updated` predates the newest valid ISO date found in `sources` or the body.

5. **`open_questions_count` must match** the actual number of bulleted items in the Open Questions section. Count before writing.

6. **`id` is immutable after creation.** If a slug needs to change, archive the old entity and create a new one with a `related` pointer to the old slug and a note explaining the rename.

7. **`scoring.raw_score` must equal `scoring.novelty + scoring.specificity + scoring.relevance`.** Sum is enforced. Mismatches indicate a copy-paste error.

8. **No entity may have `status: entity` if `contradicts` is populated** without a resolution section in the body. Contradiction must be addressed before promoting to `entity`.

9. **Date mutable state where it travels without surrounding context.** A
   catalog-visible `core_claim`, mutable state heading (`Status`, `Roadmap`,
   `Open decision`, `Open follow-ups`, and related labels), or explicit state
   label should carry an inline `YYYY-MM-DD` as-of marker. `lint --temporal`
   reports this as a warning only. It does not infer contradiction or
   supersession, and it does not make revision-graph fields mandatory.

---

## 5. Example Complete Frontmatter

```yaml
---
id: "concept/egri-ternary-diffusion"
title: "EGRI Ternary Diffusion"
type: concept
status: entity
created: "2026-03-15"
updated: "2026-04-06"

tags:
  - ternary-quantization
  - diffusion-models
  - egri
  - generative-ai

module: "autoany"
layer: 3

sources:
  - url: "https://x.com/broomva/status/1234567890"
    type: x-thread
    author: "@broomva"
    extraction_date: "2026-03-15"
    raw_extract_file: "2026-03-15-xloop-001-raw.md"
    item_number: 3

scoring:
  raw_score: 7
  novelty: 3
  specificity: 2
  relevance: 2
  pass: llm-judge
  promoted_by: "claude-sonnet-4-6"
  promoted_at: "2026-03-15"
  blog_candidate: true
  priority: true

related:
  - "[[bitnet-1bit-llm]]"
  - "[[egri-kernel]]"

contradicts: []

compounds_from: []

core_claim: "EGRI ternary diffusion adapts {-1,0,1} weight quantization to video generation, cutting VRAM 3x with <2% quality loss."

open_questions_count: 3

implementation_status: experimental
---
```

---

*Self-maintenance rule: When adding new entity types or status values to this schema, update the entity-page template (`templates/entity-page.md`) to reflect the new options in the YAML frontmatter comments. Schema and template must stay in sync.*
