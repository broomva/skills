# Knowledge Promotion Workflow

This document defines the 4-layer knowledge lifecycle: how information flows from ephemeral observation to permanent synthesis, and what happens at each gate. All agents and scripts operating in this workspace must follow this workflow when handling knowledge items.

---

## 1. Full Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — EPHEMERAL                                                    │
│  Context window, Moltbook threads, X replies, passing ideas             │
│  Duration: session only. Never written to disk in raw form.             │
│                                                                         │
│  What gets extracted?           What gets discarded?                    │
│  ── Named concept + mechanism   ── Pure opinions / sentiment           │
│  ── Concrete benchmark / result ── Social pleasantries                 │
│  ── Novel framing or metaphor   ── Restatements of known facts         │
│  ── Tool or person reference    ── Off-topic tangents                  │
└──────────────┬──────────────────────────────────────────────────────────┘
               │  Extraction (automated loop or manual)
               │  Filter: Novelty ≥ 1 OR Specificity ≥ 2
               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — RAW EXTRACTS                                                 │
│  research/notes/YYYY-MM-DD-{run-id}-raw.md                              │
│  Status: needs-review. Not yet scored. Not yet in the graph.            │
│  Retention: 30 days → archive/ (never delete, just move)               │
│                                                                         │
│  Each item has: text, source, candidate entity types, promo status      │
└──────────────┬──────────────────────────────────────────────────────────┘
               │  Nous Gate scoring (see scoring-rubric.md)
               │
               ├── Score ≤ 2 ──────────────────────────────► DISCARD
               │                                              (stays in L2 for archival)
               │
               ├── Score 3–6 ──► LLM Judge (Pass 2)
               │                     │
               │                     ├── decision: promote ──► continue ▼
               │                     └── decision: discard ──► DISCARD
               │
               └── Score ≥ 7 ─────────────────────────────► continue ▼
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — ENTITY PAGES                                                 │
│  research/entities/{type}/{slug}.md                                     │
│  Status: raw → candidate → entity. Permanent graph nodes.              │
│  Scatter: one source item can create N entity pages (one per concept)   │
│                                                                         │
│  Graph edges: related, contradicts, compounds_from (wikilinks)          │
└──────────────┬──────────────────────────────────────────────────────────┘
               │  Synthesis trigger (≥ 3 related entities with score ≥5)
               │  OR manual synthesis decision
               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 4 — SYNTHESIS NOTES                                              │
│  research/notes/YYYY-MM-DD-{topic}-synthesis.md                         │
│  Status: draft → reviewed → published. Compound insights only.         │
│  Minimum entity count: 3+ entities contributing                         │
│                                                                         │
│  Output: compound insight not present in any single entity              │
│  May trigger: blog candidate flag → content-creation skill handoff      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer 1 — Ephemeral

**What lives here:** Anything in the current context window — conversation threads, social media replies read during an engagement session, notes jotted during a meeting, ideas that surface mid-task.

**Duration:** Session only. Layer 1 items are never written to disk in raw form. They are either extracted into Layer 2 or discarded entirely.

**Extraction criteria:** An item is worth extracting to Layer 2 if it meets at least one of:
- Contains a named concept, tool, person, or mechanism (not just a sentiment or opinion)
- Includes a concrete number, benchmark, or reproducible result
- Introduces a framing or metaphor not already present in the knowledge graph
- Comes from a primary source (original author, direct observation) rather than a repost

**What is discarded at Layer 1 (never extracted):**
- Pure social engagement (likes, polite replies, "great point" exchanges)
- Restatements of already-captured concepts with no new detail
- Off-topic items with Relevance: 0 and Novelty: 0
- Content that would score Specificity: 0 (no concrete mechanism, example, or result)

**Extraction trigger:** Run the extraction loop (`bookkeeping ingest`) at the end of each engagement session, or when the context window contains ≥ 10 candidate items. Never let extraction fall more than 24 hours behind.

---

## 3. Layer 2 — Raw Extracts

**Location:** `research/notes/YYYY-MM-DD-{run-id}-raw.md`

**Format:** Use the template at `skills/bookkeeping/templates/raw-extract.md`. Each file represents one extraction run (one engagement session, one paper read, one conversation digest).

**Content per item:**
- Item number and short slug
- Raw text (verbatim quote or close paraphrase)
- Source URL or reference
- Fast-path heuristic scores (N/S/R breakdown)
- Candidate entity types (comma-separated type values)
- Promotion status: `pending` | `promoted` | `discarded`

**Retention policy:**
- Active review period: 30 days from creation date
- After 30 days: move to `research/archive/raw/YYYY-MM/` (never delete)
- Items with `promotion_status: pending` after 30 days: auto-discard with a note in the archive file
- The archive is append-only and never pruned — it is the permanent provenance record

**Review discipline:** Every raw extract file must reach 100% resolved items (all `pending` changed to `promoted` or `discarded`) within 48 hours of creation. Unreviewed raw files block knowledge graph freshness.

---

## 4. Layer 3 — Entity Pages

**Location:** `research/entities/{type}/{slug}.md`

Directory structure:
```
research/entities/
├── concept/
├── pattern/
├── tool/
├── person/
├── project/
├── discovery/
├── question/
├── framework-refinement/
├── industry-pattern/
└── persona/
```

**Creation criteria:** An entity page is created when a Layer 2 item scores ≥ 5 on the Nous gate (or ≥ 3 with a positive LLM judge decision).

**Format:** Use the template at `skills/bookkeeping/templates/entity-page.md`. Schema validation rules are in `references/entity-schema.md`.

**Tags:** assign from the controlled vocabulary in `research/entities/_tags.md` (81 canonical tags across 4 facets). Never tag an entity with its own `type:` (redundant — `type:` already encodes it) and never invent a free tag; `lint` warns on both. A tight, controlled tag set is what makes tags a real routing signal (the `kg` catalog scores on them) rather than noise.

**Scatter mechanics — One source → N entity pages:**

A single source item (one tweet, one paper section, one conversation extract) frequently contains multiple distinct promotable claims. Each claim becomes its own entity page. This is the scatter operation:

1. Read the item and identify all distinct named concepts, tools, people, or findings.
2. Score each sub-claim independently against the Nous gate.
3. Create a separate entity page for each sub-claim that meets the promotion threshold.
4. Link the entity pages to each other via `related` wikilinks if they share conceptual space.
5. In each entity page's `sources`, point back to the same source URL — multiple entity pages can cite the same source.

**Why scatter instead of one note per session?** Session notes create monolithic blobs that are hard to traverse, link, or synthesize later. Entity pages are atomic, independently linkable, and composable. The graph becomes queryable.

**Graph edge discipline:**
- `related`: add conservatively. Only link if there is a meaningful conceptual relationship a future agent would care about.
- `contradicts`: always investigate before adding. See Contradiction Detection Protocol below.
- `compounds_from`: only populate when this entity was explicitly created by combining others (synthesis output).

---

## 5. Layer 4 — Synthesis Notes

**Location:** `research/notes/YYYY-MM-DD-{topic}-synthesis.md`

**Format:** Use the template at `skills/bookkeeping/templates/synthesis-note.md`.

**Minimum entity count:** A synthesis note requires at least **3 contributing entity pages** with `status: entity` (not `raw` or `candidate`). Synthesis over unverified entities produces unreliable compounds.

**Synthesis trigger conditions (any one suffices):**
1. ≥ 3 entity pages share a common tag AND at least 2 have `priority: true`
2. Two entity pages in the `contradicts` graph have been resolved — the resolution is synthesizable
3. A cluster of entity pages all compound toward the same open question (a `question` entity gets answered by ≥ 3 `discovery` or `concept` entities)
4. Manual decision: you recognize a compound insight while reviewing entities that isn't captured in any single page

**How compounds are detected:**

A compound insight is an assertion that:
- Cannot be derived from any single contributing entity alone
- Requires combining the core claims of ≥ 2 entities
- Is non-obvious (would not be predicted from either entity in isolation)

Run graph traversal over the `related` and `compounds_from` edges. If a cluster of 3+ entities all point to the same conceptual space and none of them contains the emergent claim, the compound exists.

**Synthesis types:**
- `convergence`: Multiple independent sources arrive at the same mechanism or conclusion
- `contradiction`: Two entities make conflicting claims; synthesis resolves or contextualizes the conflict
- `progression`: Entities form a temporal or logical sequence (A led to B led to C)
- `gap-analysis`: A cluster of entities collectively defines the boundary of unknown territory

---

## 6. Contradiction Detection Protocol

A contradiction exists when two entity pages make claims that cannot both be true simultaneously in the same context.

**Detection:**
- Automated: when a new entity is created, run a similarity scan over `core_claim` fields of existing entities in the same type/tag space. Flag pairs with high semantic similarity but opposing valence.
- Manual: any agent noticing conflicting claims while reading entity pages should set `contradicts` on both entities immediately.

**Resolution steps:**

1. **Flag both entities:** Add each to the other's `contradicts` list. Set both to `status: candidate` until resolved.
2. **Investigate provenance:** Check the `sources` for both. Are they from different time periods (temporal contradiction)? Different contexts (conditional contradiction)? Different definitions (definitional ambiguity)?
3. **Classify the contradiction:**
   - *Temporal*: Both were true at different times. Resolve by adding date context to core claims. Mark older entity `status: archived`.
   - *Conditional*: Both are true under different conditions. Resolve by adding condition qualifiers to both core claims.
   - *Definitional*: The entities use the same term differently. Resolve by creating a disambiguation entity of type `concept`.
   - *Genuine conflict*: One is wrong. Discard the lower-confidence entity, update the survivor's core claim.
4. **Write resolution note:** In both entity bodies, add a `## Contradiction Resolution` section explaining which type and how it was resolved.
5. **Create synthesis note** if the resolution yields a compound insight (it often does).
6. **Remove from `contradicts`** once resolved and promote both to `status: entity` (or `status: archived` if superseded).

---

## 7. Blog Pipeline

When an entity or synthesis note is flagged as `blog_candidate: true`, the following handoff process applies:

1. **Verify eligibility:** Confirm the item meets at least one blog candidate criterion from `scoring-rubric.md § 6`.
2. **Extract the angle:** The blog angle is not a summary of the entity — it is the *compound insight* or *unexpected finding* that makes the entity worth reading. For synthesis notes, the angle is the emergent pattern. For entity pages, it is often the contradiction resolved or the mechanism explained.
3. **Create a blog brief:** Write a short (≤ 200 word) brief capturing:
   - The hook (what is surprising or counterintuitive)
   - The audience (who needs to know this)
   - The core claim (from the entity's `core_claim` field)
   - Supporting entities (wikilinks to the 2–4 entities that ground the post)
4. **Hand off to `content-creation` skill:** Pass the entity slug, brief, and source wikilinks. The skill handles draft, multimedia, and publishing pipeline.
5. **Update entity frontmatter:** Set `blog_candidate: true` (already set) and add `blog_status: briefed` once handed off. Track through `blog_status: drafted → published`.

---

## 8. Self-Maintenance Rules

The following rules are self-enforcing — agents reason about them when modifying this file:

1. **Layer count consistency:** This file defines exactly 4 layers. If `scoring-rubric.md` or `SKILL.md` reference a different number of layers or different layer names, update all three files in the same commit.

2. **Threshold consistency:** The promotion threshold (≥5 promote, ≥7 priority, 3–6 ambiguous band) must be identical in this file and `scoring-rubric.md`. Verify before committing any change to either file.

3. **Template-path consistency:** Every template path referenced in this file (`templates/entity-page.md`, `templates/raw-extract.md`, `templates/synthesis-note.md`) must correspond to an actual file. If a template is renamed, update this file in the same commit.

4. **Minimum entity count for synthesis:** The number 3 appears in both this file (§5) and the synthesis template frontmatter. If either changes, both must change.

5. **Archive path convention:** If the archive directory convention changes (currently `research/archive/raw/YYYY-MM/`), update the Layer 2 retention policy section and the raw-extract template footer simultaneously.
