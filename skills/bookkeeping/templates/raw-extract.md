---
# ── RAW EXTRACT FILE — LAYER 2 ───────────────────────────────────────────────
# This file is a raw extraction from a single run. Items have NOT been scored
# by the LLM judge. Status is "needs-review". Do not cite entity pages from
# this file — wait until items are promoted to Layer 3.
#
# Retention: 30 days active review → research/archive/raw/YYYY-MM/ thereafter.
# All items must reach status promoted or discarded within 48 hours of creation.

date: "{YYYY-MM-DD}"
# Required. Date this extraction run was performed.

source_type: moltbook | x-engagement-session | paper-read | conversation-extract | web-research | github-survey | mixed
# Required. Primary source type for this run. Use "mixed" if the run
# processed multiple source types in a single pass.

run_id: "{short-run-identifier}"
# Required. Short unique identifier for this run. Convention: YYYYMMDD-NNN
# where NNN is a zero-padded sequence number for runs on the same day.
# Example: 20260406-001

item_count: {N}
# Required. Total number of items in this file. Keep in sync with actual item count.

extracted_by: "{agent-id-or-human}"
# Required. Who ran the extraction. "claude-sonnet-4-6" for Claude sessions,
# "human" for manual extractions, or a named agent ID.

status: needs-review
# Always "needs-review" on creation. Change to "reviewed" once all items
# have been resolved (promoted or discarded). Never leave as "needs-review"
# after 48 hours.

reviewed_at: ~
# Optional. Fill in when status changes to "reviewed".

review_notes: ~
# Optional. Any notes on the batch — themes, patterns, quality issues.
---

<!-- ═══════════════════════════════════════════════════════════════════════════
  RAW EXTRACT — {RUN-ID}
  ─────────────────────────────────────────────────────────────────────────────
  Source type: {source_type}
  Extracted: {YYYY-MM-DD} by {extracted_by}

  This file contains unscored knowledge items extracted from Layer 1 (ephemeral
  observations). Items are NOT yet validated. Do not reference these items as
  established knowledge until they are promoted to entity pages.

  To process this file:
    bookkeeping promote --file {YYYY-MM-DD-run-id-raw.md}

  Or process items manually by updating each item's `promotion_status` field
  and creating entity pages for promoted items.

  See skills/bookkeeping/references/promotion-workflow.md for the full protocol.
  ══════════════════════════════════════════════════════════════════════════════ -->

# Raw Extract — {YYYY-MM-DD} / {run-id}

---

<!-- ─────────────────────────────────────────────────────────────────────────
  ITEM TEMPLATE
  Copy this block for each extracted item. Replace all {placeholders}.
  Delete the comment blocks in the final file.
  ─────────────────────────────────────────────────────────────────────────── -->

## Item 1 — {short-slug}

<!-- short-slug: a 2–4 word kebab-case label for this item. Not the entity slug —
     just a human-readable identifier within this file. Example: rope-context-extension -->

**Heuristic Scores (Pass 1):**
| Dimension | Score | Notes |
|-----------|-------|-------|
| Novelty | {0-3}/3 | {Brief justification: is this new to the knowledge graph?} |
| Specificity | {0-3}/3 | {Brief justification: is there a concrete mechanism, result, or name?} |
| Relevance | {0-3}/3 | {Brief justification: which active project or open question does this serve?} |
| **Raw Total** | **{N}/9** | |

**Ambiguous band?** {Yes — needs LLM judge (Pass 2) | No — score is unambiguous}

<!-- If "Yes", invoke the LLM judge using the prompt in scoring-rubric.md § 4
     and paste the result in the LLM Judge Result block below. -->

<!-- LLM Judge Result (Pass 2) — only present if ambiguous band:
**Judge scores:** N:{0-3} S:{0-3} R:{0-3} = {total}/9
**Decision:** promote | discard
**Confidence:** high | medium | low
**Judge reasoning:** "{overall reasoning from judge JSON output}"
-->

**Source:**
- **Type:** {moltbook | x-reply | x-thread | web-article | research-paper | conversation | github | internal-doc}
- **URL / Reference:** {full URL or file path}
- **Author:** {name or @handle, if known}
- **Observed at:** {YYYY-MM-DD}

**Quote / Raw Text:**
> {Verbatim quote or close paraphrase. Use blockquote format.
>  If paraphrasing, add "[paraphrase]" at the end of the block.}

**Interpretation:**
{1–3 sentences. What does this item mean, and why is it significant? This is your editorial layer — the quote above is the evidence; this is the analysis. Do not inflate: if you cannot write 1 genuine sentence of interpretation, reconsider whether the item is worth promoting.}

**Candidate Entity Types:** {concept, pattern, tool, person, project, discovery, question}
<!-- List all types that this item could reasonably become. Comma-separated.
     The first type listed becomes the primary type if promoted. -->

**Candidate Slug(s):** `{primary-slug}`, `{secondary-slug-if-scatter}`
<!-- If this item will scatter into multiple entity pages (one source → N entities),
     list all candidate slugs. Each will become a separate entity page. -->

**Promotion Status:** pending
<!-- pending → promoted (when entity page created) | discarded (when below threshold)
     Update this field when the item is resolved. -->

**Entity Page(s):** ~
<!-- Fill in once promoted. Use wikilink format.
     Example: [[rope-embeddings]], [[rotary-position-encoding]] -->

---

## Item 2 — {short-slug}

**Heuristic Scores (Pass 1):**
| Dimension | Score | Notes |
|-----------|-------|-------|
| Novelty | {0-3}/3 | {justification} |
| Specificity | {0-3}/3 | {justification} |
| Relevance | {0-3}/3 | {justification} |
| **Raw Total** | **{N}/9** | |

**Ambiguous band?** {Yes | No}

**Source:**
- **Type:** {source-type}
- **URL / Reference:** {url or path}
- **Author:** {author}
- **Observed at:** {YYYY-MM-DD}

**Quote / Raw Text:**
> {verbatim or close paraphrase}

**Interpretation:**
{1–3 sentences of editorial analysis.}

**Candidate Entity Types:** {types}

**Candidate Slug(s):** `{slug}`

**Promotion Status:** pending

**Entity Page(s):** ~

---

<!-- Add more Item blocks as needed. Each follows the same structure.
     Numbering must be sequential. item_count in frontmatter must match total. -->

---

## Promotion Summary

<!-- Fill this table as items are processed. Update in real time — do not wait
     until all items are done. This table is the quick-status view for this file. -->

| Item | Slug | Score | Status | Entity Page |
|------|------|-------|--------|-------------|
| 1 | {short-slug} | {N}/9 | pending | ~ |
| 2 | {short-slug} | {N}/9 | pending | ~ |
<!-- Add one row per item. -->

**Totals:** {promoted_count} promoted / {discarded_count} discarded / {pending_count} pending

<!-- When all items are resolved, update the frontmatter:
     status: reviewed
     reviewed_at: YYYY-MM-DD
-->

---

<!-- ─────────────────────────────────────────────────────────────────────────
  PROCESSING INSTRUCTIONS
  ─────────────────────────────────────────────────────────────────────────────
  1. Score each item using Pass 1 heuristics (scoring-rubric.md § 3).
  2. For items in the ambiguous band (score 3–6), invoke the LLM judge (Pass 2).
  3. For promoted items (score ≥5 after both passes):
     a. Create entity page at research/entities/{type}/{slug}.md
     b. Use templates/entity-page.md
     c. Set sources.raw_extract_file to this filename
     d. Set sources.item_number to the item number
     e. Update this item's promotion_status to "promoted"
     f. Fill in the Entity Page(s) field with the wikilink
  4. For discarded items (score ≤4 after both passes):
     a. Update promotion_status to "discarded"
     b. The item stays in this file for archival — do not delete it
  5. Update the Promotion Summary table.
  6. When all items are resolved, update frontmatter status to "reviewed".
  7. After 30 days, move this file to research/archive/raw/YYYY-MM/.

  Run: bookkeeping promote --file {this-filename}.md
  ─────────────────────────────────────────────────────────────────────────── -->
