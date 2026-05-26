# Knowledge Extraction Reference

## The Three-Layer Stack

```
Layer 1 — Ephemeral (scrolls away)
  Moltbook threads, X replies, passing ideas

Layer 2 — Session extract (auto-generated, needs review)
  research/notes/YYYY-MM-DD-social-insights-raw.md
  → 82 items promoted, 145 discarded in first live run (2026-04-06)

Layer 3 — Permanent vault (promoted manually or by agent)
  research/notes/{module}-design.md
  docs/references/social-discoveries.md
  posts/drafts/{slug}.md
```

## Scoring Rubric (Nous Gate)

Every external comment is scored on three dimensions (0-3 each):

### Novelty
- **0**: Already verbatim in the knowledge graph
- **1**: Adds new evidence to an existing note (cite this in footnote)
- **2**: New framing of a concept we've articulated (update the note)
- **3**: Genuinely new concept not yet captured anywhere

### Specificity
- **0**: Vague/generic ("agents need better memory")
- **1**: Directional with a named pattern ("bi-temporal indexing matters for agents")
- **2**: Specific claim with mechanism ("the gap between valid-time and transaction-time is where debugging lives — you need both timestamps to reconstruct the agent's belief state at decision time")
- **3**: Precise and immediately actionable ("add `valid_time: DateTime` to Lago's `EventEnvelope` struct alongside `transaction_time`")

### Relevance
- **0**: Unrelated to Life OS, broomva.tech, or active design questions
- **1**: Adjacent (useful context, worth bookmarking)
- **2**: Directly relevant to an existing module or open question
- **3**: Blocks or unblocks a specific open design question in Life OS

**Promotion threshold**: Total ≥ 5/9 → promote to `research/notes/`.

Scores ≥ 7/9 → immediate promotion candidate, suggest specific destination file.

## Source Taxonomy

### From Moltbook

| Signal | Extract | Destination |
|--------|---------|-------------|
| Novel framing of architecture | Full quote + author + post context | `research/notes/YYYY-MM-DD-synthesis.md` |
| Challenge to Life OS design | Exact objection + our response | `research/notes/{module}-open-questions.md` |
| External research cited | Paper/blog URL + 1-sentence summary | `docs/references/social-discoveries.md` |
| High-karma commenter insight | Full quote + handle | `docs/references/social-discoveries.md` (Framings section) |

### From X

| Signal | Extract | Destination |
|--------|---------|-------------|
| Technical reply extending our ideas | Thread + who said what | `research/notes/YYYY-MM-DD-x-threads.md` |
| New paper or project | URL + brief + relevance | `docs/references/social-discoveries.md` |
| Architectural critique | Objection + our response | `research/notes/{module}-critiques.md` |
| Emerging framing in the community | Exact language being used | `docs/references/social-discoveries.md` (Framings section) |

### From External URLs (crawled)

| Type | Action |
|------|--------|
| arXiv paper | Fetch abstract, extract key claims, link to Life OS module |
| GitHub repo | Check README, note architectural approach, compare to Life OS |
| Blog post | Extract thesis, quote 1-2 passages, note resonance |

## Blog Post Candidate Criteria

A topic becomes a **blog post candidate** when:
- It appears in ≥3 promoted items from different conversations
- OR it generates ≥5 replies in a single Moltbook thread
- OR the same framing gets independently invented by ≥2 external people

**Standing candidates** (as of 2026-04-06):

| Topic | Evidence | Priority |
|-------|---------|---------|
| "The Soul File Is Not Your Agent's Identity" | 5 Moltbook threads, X regulation conversation, xproof_agent_verify deep reply | HIGH |
| "Why Confidence Scores Are Referential Integrity Violations" | drsoftec thread, karma≠truth thread, multiple Moltbook comments | HIGH |
| "The Quiet Supply Chain: Memory Your Agent Carried from Sessions You Forgot" | 4850d9b3 thread, 2d7acacd thread, 13bc2226, d3b92312 | HIGH |
| "Bi-Temporal Memory: Valid-Time vs Transaction-Time" | 4a157f93, PsudoMike X thread, 2040695955238875534 | MEDIUM |
| "The Confused Deputy Problem in Agent Security" | jeremie_strand 4-reply thread, 0da62967, Category 6 escalation | MEDIUM |

## Handoff to /blog-post

When generating a post from social intelligence:

1. **Read the synthesis doc** for the topic section
2. **Read social-discoveries.md** for verbatim framings to incorporate
3. **Note known objections** from the conversations (preempt in the post)
4. **List distribution targets** (specific accounts who engaged with the idea)

Invoke:
```
/blog-post "{topic}" — {audience}, {intent}, {tone}
```

Pass as context to /blog-post:
- The pre-tested angle (what landed in Moltbook/X)
- 2-3 verbatim community quotes to anchor the piece
- The distribution targets list

## Knowledge Node Templates

### New research note

```markdown
---
tags: [research, notes, {module}]
type: architecture-note
status: draft
created: YYYY-MM-DD
source: social-engagement
evidence: [{post_id_or_tweet_id}]
---

# {Title}

**Core claim**: {one sentence}

## Evidence
{Community quotes and threads that surfaced this}

## Life OS Connection
{Which module and how it addresses/instantiates this}

## Open Questions
{What this conversation didn't resolve}
```

### Reference entry

```markdown
| Handle/URL | Platform | Why Relevant | Status | Added |
|-----------|----------|-------------|--------|-------|
| @handle | X/Moltbook | {one sentence} | Active/Inactive | YYYY-MM-DD |
```
