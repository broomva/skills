---
# ── IDENTITY ──────────────────────────────────────────────────────────────────
# Replace {type} with one of: concept | pattern | tool | person | project | discovery | question
# Replace {slug} with a kebab-case identifier that uniquely names this entity.
# Example: "concept/rope-embeddings" or "tool/spacetimedb"
id: "{type}/{slug}"

# Human-readable display title. Title case. ≤ 80 characters.
title: "{Human-Readable Title}"

# Primary entity type. Use the dominant nature of this entity.
# concept = abstract idea/mechanism, pattern = recurring solution,
# tool = software/framework/API, person = named individual,
# project = internal or external project, discovery = empirical finding,
# question = open unanswered question
type: concept

# Lifecycle stage. New entity pages start as "raw" or "candidate".
# raw → candidate → entity → synthesis → archived
status: raw

# ISO date of first creation (not first discovery — when this file was made).
created: "{YYYY-MM-DD}"

# ISO date of most recent substantive edit. MUST be today on every write.
updated: "{YYYY-MM-DD}"

# ── CLASSIFICATION ────────────────────────────────────────────────────────────
# At least one tag required. kebab-case. Use controlled vocabulary from
# research/entities/_tags.md when possible; free tags are acceptable.
tags:
  - "{primary-tag}"
  - "{secondary-tag}"

# Which Broomva project or research domain this entity primarily belongs to.
# Examples: "life-agent-os", "noesis", "haima", "general-ml"
# Omit this field entirely if the entity is domain-agnostic.
module: "{project-or-domain}"

# Always 3 for entity pages. Do not change.
layer: 3

# ── PROVENANCE ────────────────────────────────────────────────────────────────
# At least one source entry is required. Add multiple entries if this entity
# is corroborated by independent sources — convergence strengthens the entity.
sources:
  - post_id: "{platform-unique-id}"   # Optional. Social post ID for deduplication.
    url: "{full-url}"                  # Required. Canonical permalink.
    type: "{source-type}"              # Required. See scoring-rubric.md § Source Taxonomy.
    author: "{@handle-or-Full Name}"   # Optional but recommended.
    extraction_date: "{YYYY-MM-DD}"    # Required. When this source was processed.
    raw_extract_file: "{YYYY-MM-DD}-{run-id}-raw.md"  # Optional. Layer 2 provenance.
    item_number: {N}                   # Optional. Item # in the raw extract file.
  # Add more source entries if there are multiple corroborating sources:
  # - url: "{another-url}"
  #   type: "{source-type}"
  #   extraction_date: "{YYYY-MM-DD}"

# ── SCORING ───────────────────────────────────────────────────────────────────
scoring:
  raw_score: {N}           # Sum of novelty + specificity + relevance. Must be 0–9.
  novelty: {0-3}           # Nous gate Dimension 1: how new to the knowledge graph.
  specificity: {0-3}       # Nous gate Dimension 2: how concrete and grounded.
  relevance: {0-3}         # Nous gate Dimension 3: connection to active work.
  pass: heuristic          # "heuristic" | "llm-judge" | "human"
  promoted_by: "{agent-id-or-human}"   # Who made the promotion decision.
  promoted_at: "{YYYY-MM-DD}"          # When the promotion was made.
  blog_candidate: false    # true if meets blog candidate criteria (scoring-rubric.md § 6).
  priority: false          # true if raw_score ≥ 7.

# ── GRAPH ─────────────────────────────────────────────────────────────────────
# All wikilinks must use [[slug]] format where slug matches the id field of
# the target entity (without the type/ prefix).
# Example: [[rope-embeddings]] not [[concept/rope-embeddings]]

# Entities that share conceptual space. Add brief annotations (inline comment).
related:
  - "[[{related-entity-slug}]]"    # {brief reason for the relationship}
  # - "[[{another-slug}]]"         # {relationship note}

# Entities whose core claims conflict with this entity's core claim.
# If this list is non-empty, entity cannot reach status:entity until resolved.
# See promotion-workflow.md § Contradiction Detection Protocol.
contradicts: []
# contradicts:
#   - "[[{conflicting-entity-slug}]]"  # {nature of conflict}

# Entities that were combined to produce this one (synthesis outputs only).
# Leave empty unless this entity was created from a Layer 4 synthesis operation.
compounds_from: []

# ── CONTENT METADATA ──────────────────────────────────────────────────────────
# One sentence, ≤ 140 characters. A claim, not a category label.
# Bad:  "Attention is a mechanism in transformers."
# Good: "Attention lets transformers weight any token's influence on any other, enabling O(n²) global context."
core_claim: "{One precise, falsifiable or actionable sentence ≤ 140 chars.}"

# Count of bulleted items in the ## Open Questions section below. Keep in sync.
open_questions_count: {N}

# implemented | designed | experimental | open-question | not-applicable
# "not-applicable" for concepts/people/discoveries where implementation is meaningless.
implementation_status: not-applicable
---

# {Human-Readable Title}

<!-- ═══════════════════════════════════════════════════════════════════════════
  HOW TO USE THIS TEMPLATE
  ─────────────────────────────────────────────────────────────────────────────
  Replace all {placeholder} tokens with real content.
  Delete these comment blocks when the file is ready to promote to status:entity.
  Required sections: Core Claim, Context, Evidence, Open Questions, Promotion Notes.
  Optional sections: Graph Connections, Implementation (omit if not-applicable).
  ══════════════════════════════════════════════════════════════════════════════ -->

## Core Claim

<!-- One tweet-sized sentence restating the core_claim from frontmatter.
     This must match the frontmatter field exactly. It is not a summary —
     it is the central assertion of the entity in plain English. -->

{One precise, falsifiable or actionable sentence ≤ 140 chars.}

---

## Context

<!-- 2–3 sentences of background. Answers: What space does this entity live in?
     What problem does it address or what phenomenon does it describe?
     What prior knowledge does a reader need to understand the core claim?
     Do NOT repeat the core claim here — assume the reader just read it. -->

{Background sentence 1: situate this entity in its domain.}

{Background sentence 2: what makes this entity worth capturing — what was the prior state of knowledge?}

{Background sentence 3 (optional): how does this entity relate to other known concepts at a high level?}

---

## Evidence

<!-- One subsection per source in the frontmatter sources list.
     Each subsection provides the raw evidence that grounds the entity. -->

### Source 1 — {short source label, e.g. "@author on X, 2026-04-06"}

**Quote / Excerpt:**
> {Verbatim quote or very close paraphrase. Use > blockquote format.
>  If paraphrasing, note "[paraphrase]" at the end.}

**Author:** {Name or @handle} — {brief one-line description of why this author is credible on this topic, if relevant}

**What it adds:** {1–2 sentences. What specific claim, mechanism, number, or framing does this source contribute to the entity? Be precise — this is the specificity justification for the score.}

<!-- If there are additional sources, duplicate this block:
### Source 2 — {short source label}

**Quote / Excerpt:**
> {verbatim or close paraphrase}

**Author:** {Name or @handle}

**What it adds:** {contribution to the entity}
-->

---

## Graph Connections

<!-- Only include this section if there are meaningful graph edges.
     Omit the section entirely (or leave empty subsections) if the entity
     is isolated — it is better to leave connections empty than to add
     spurious links. -->

### Related Entities

<!-- For each wikilink in the frontmatter related list, explain *why* it is
     related. One sentence per entity. Use [[slug]] format. -->

- **[[{related-entity-slug}]]**: {Why are these related? What conceptual bridge connects them?}
<!-- - **[[{another-slug}]]**: {relationship explanation} -->

### Compounds Into

<!-- Entities that this entity contributes to building. The reverse direction
     of compounds_from. Leave empty if unknown — synthesis notes will populate
     this retroactively. -->

<!-- - **[[{synthesis-slug}]]**: {What does this entity contribute to the compound?} -->

### Contradictions

<!-- Only present if contradicts is non-empty in frontmatter.
     Must include a resolution note explaining the nature of the conflict
     and current resolution status. -->

<!-- #### [[{conflicting-slug}]]

**Nature of conflict:** {What exactly do the two core claims assert that is mutually exclusive?}

**Resolution status:** Unresolved | Resolved — Temporal | Resolved — Conditional | Resolved — Definitional | Resolved — Superseded

**Resolution notes:** {If resolved: what was the resolution? If unresolved: what evidence would resolve it?} -->

---

## Implementation

<!-- Include this section only if implementation_status is NOT "not-applicable".
     If the entity is a concept, pattern, or tool that has (or could have) a
     concrete implementation in this workspace, describe it here. -->

<!-- ### Code / Mechanism

**Location:** {File path or crate/module name, if implemented.}

**Type signature / Interface:**
```{language}
// Paste the relevant type, function signature, or pseudocode here.
// Not the full implementation — just the interface that captures the concept.
```

**How it works:**
{2–3 sentences describing the mechanism in terms of the implementation, not the abstract concept. This section should be read by someone about to modify the code.}

### Status

**Implementation status:** {Implemented | Designed | Experimental | Open question}

**Confidence:** {How confident are you this implementation correctly instantiates the concept?} -->

---

## Open Questions

<!-- Bulleted list of open questions this entity raises but does not answer.
     These are not implementation TODOs — they are epistemic gaps.
     Keep count in sync with open_questions_count in frontmatter.
     Each question should be precise enough that a future agent could
     recognize when it has been answered. -->

- {Question 1: What is still unknown about this entity? Make it specific.}
- {Question 2: What would need to be true for the core claim to be false?}
<!-- Add more as needed. Count must match open_questions_count in frontmatter. -->

---

## Current

<!-- OPTIONAL (GBrain compiled-truth pattern). Include this section for entities
     whose understanding *evolves* — fast-moving tools, projects, people, or any
     concept the graph re-derives as new evidence arrives.

     ## Current is the COMPILED best-understanding: a single, present-tense
     synthesis of everything in ## Timeline below, rewritten in place on each
     update (it is destructively edited — old text is replaced, not appended).
     Read this to know "what do we believe right now", without replaying the
     whole evidence log.

     Omit this section entirely for stable entities — a fixed concept needs no
     compiled-truth/timeline split, and existing pages without it lint clean. -->

{Present-tense synthesis of the current best understanding. Rewrite in place on
each update. This is the answer to "what is true now" — compiled from the
Timeline, not a running log.}

---

## Timeline

<!-- OPTIONAL (GBrain compiled-truth pattern). Pairs with ## Current above.
     Append-only, NEWEST-LAST evidence log. Each entry is a list item that MUST
     begin with a leading ISO date (YYYY-MM-DD) — the lint check flags entries
     without one (WARNING severity). The date is what makes the log an audit
     trail: "what did we believe, and when did the evidence arrive".

     Rules:
       - Append new entries at the BOTTOM (newest-last). Never rewrite past
         entries — that would destroy the audit trail. Corrections are new
         dated entries that supersede, not edits to old ones.
       - Every top-level entry starts with a full ISO date. Partial dates
         (2026-04) and bare years are flagged by lint.
       - Sub-bullets (indented detail under a dated entry) are exempt.
       - When the Timeline changes, re-compile ## Current to match. -->

- {YYYY-MM-DD} — {What evidence/event arrived on this date, and what it changed
  about the entity's understanding. One line; indent sub-bullets for detail.}
- {YYYY-MM-DD} — {Next dated entry, appended below the previous one.}

---

## Promotion Notes

<!-- Traceability block. Fill from the raw extract file and scoring rubric output.
     Do not delete this section after promotion — it is the provenance record. -->

**Extraction date:** {YYYY-MM-DD}

**Source file:** `{YYYY-MM-DD-run-id-raw.md}` — Item {N}

**Nous gate scores:**
| Dimension | Score | Justification |
|-----------|-------|---------------|
| Novelty | {0-3}/3 | {1-sentence justification — what is genuinely new here?} |
| Specificity | {0-3}/3 | {1-sentence justification — what concrete detail grounds this?} |
| Relevance | {0-3}/3 | {1-sentence justification — which active project or question does this serve?} |
| **Total** | **{N}/9** | |

**Scoring pass:** {heuristic | llm-judge | human}

**Promoted by:** {agent-id or "human"}

**Promoted at:** {YYYY-MM-DD}

<!-- If this entity was promoted via LLM judge (Pass 2), paste the judge's
     "overall" reasoning field here for auditability:
**Judge reasoning:** "{judge overall reasoning text}"
-->
