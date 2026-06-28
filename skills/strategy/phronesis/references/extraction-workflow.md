# Extraction Workflow (M7)

`core/extraction/` lifts knowledge from concluded engagement journals
into the workspace knowledge graph at `research/entities/`. This page
documents the end-to-end flow + the reflexive trigger + the human
review gate.

See also: `references/anonymization-policy.md` (what gets stripped),
`core/extraction/{anonymizer,candidates,pipeline}.py` (the
implementation), `tests/integration/test_extraction_pipeline.py`
(end-to-end checks).

## Trigger

The pipeline is **reflexive** (per
`feedback_bookkeeping_reflexive.md`) — it fires automatically when
`Engagement.emit(EventKind.ENGAGEMENT_CONCLUDED, ...)` is invoked. No
manual command is required for the happy path. The hook lives in
`core/engagement.py::Engagement._fire_extraction_hook()`.

To re-run on an existing concluded engagement (e.g. after fixing the
anonymization policy and wanting fresh candidates):

```bash
phronesis bookkeep <tenant-slug>
```

To disable during interactive debugging:

```bash
PHRONESIS_EXTRACTION_ENABLED=0 ...
```

## Flow

```
ENGAGEMENT_CONCLUDED emitted
        │
        ▼
on_engagement_concluded(engagement)        ← reflexive hook
        │
        ▼
extract_and_queue(engagement)              ← orchestrator
        │
        ├──► EngagementAnonymizer(tenant, policy + journal-derived redact_terms)
        │
        ├──► extract_industry_patterns(engagement, anonymizer)
        │       Rule 1: maturity dimension < 2.5 → industry-pattern candidate
        │       Rule 2: thesis economic_lever  → industry-pattern candidate
        │
        ├──► extract_framework_refinements(engagement, anonymizer)
        │       Rule 1: 2+ use cases share ideation_source → RICE refinement
        │       Rule 2: RICE-top != ROI-top                → RICE refinement
        │
        ▼
for each ExtractionCandidate:
    ├── re-check tenant markers (defense-in-depth)
    │       if leaked → add to result.leaks, SKIP
    │
    ├── bookkeeping.score_item(RawItem)        ← P8 Nous gate (0-9)
    │       (deterministic stub when bookkeeping module unavailable)
    │
    ├── persist JSON record:
    │       <queue_root>/<tenant-slug>/<promoted|low-score>/<slug>-<ts>.json
    │
    └── if score ≥5 AND no leaks:
            persist entity stub at:
            <entity_graph_root>/<entity-type>/<slug>.md
            (status: candidate — operator polishes before promote)
```

## Sandboxing

For test isolation, override the destination paths via env vars:

| Env var | Default | Use |
|---|---|---|
| `PHRONESIS_EXTRACTION_QUEUE_ROOT` | `~/.config/phronesis/extraction-queue/` | review-queue records |
| `PHRONESIS_ENTITY_GRAPH_ROOT` | `~/broomva/research/entities/` | promoted entity stubs |
| `PHRONESIS_EXTRACTION_ENABLED` | `1` (on) | set `0` to disable reflexive trigger |
| `PHRONESIS_EXTRACTION_STUB_SCORER` | (unset) | set `1` to force deterministic stub scorer (skip real LLM call) |

## Candidate shape

```python
class ExtractionCandidate(BaseModel):
    slug: str                          # kebab-case
    entity_type: Literal["industry-pattern", "framework-refinement"]
    content: str                       # anonymized body
    quote: str                         # anonymized source phrase
    title: str                         # short human-readable title
    provenance_event_ids: list[str]    # ULID(s) of journal events
    industry: str | None               # for industry-pattern only
    framework_ref: str | None          # for framework-refinement only
    signals: dict[str, float | str]    # numeric/string features
```

`industry` and `framework_ref` are mutually exclusive — one is set per
candidate depending on `entity_type`.

## Scoring

Each candidate is wrapped as a bookkeeping `RawItem` and passed to
`bookkeeping.score_item(item, existing_slugs)`. The score is a 0-9
total across three dimensions:

- **Novelty** (0-3) — does this overlap with existing entities?
- **Specificity** (0-3) — concrete enough to act on?
- **Relevance** (0-3) — life-OS-adjacent?

Score ≥5 → promote (file as entity stub).
Score <5 → queue for human review.

This is the **same Nous gate** the rest of the workspace uses — we never
duplicate the math.

## Entity stub format

Promoted candidates land at
`<entity_graph_root>/<entity-type>/<slug>.md` as YAML-frontmatter
markdown. Body sections:

```markdown
---
type: industry-pattern | framework-refinement
slug: <kebab-case>
title: <short title>
status: candidate           ← always "candidate" at extraction time
provenance:
  source: phronesis-extraction
  engagement_slug: <slug>
  event_ids:
    - <ULID>
score:
  total: N/9
  ...
industry: <industry>        ← XOR framework_ref: <ref>
signals:
  - <key>: <value>
created_at: <ISO>
---

# <Title>

## Pattern (anonymized)
<body>

## Source quote
> <quote>

## Promotion gate
- Bookkeeping P8 score: N/9 (<method>)
- Rule-of-three: surface ≥2 more same-industry / same-framework
  engagements before treating as a stable graph node.
- Operator action: polish, verify signals, confirm anonymization,
  promote `status` candidate → active.
```

## Rule-of-three

A first-instance candidate is just one data point. A stable
industry-pattern or framework-refinement entity requires the same
pattern to recur in ≥3 same-industry / same-framework engagements.
The pipeline files candidates at `status: candidate`; operator
promotes to `status: active` only after the third instance.

This matches the bstack Crystallize (P16) discipline at the
workspace-wide level — every primitive in `CLAUDE.md` was promoted
only after rule-of-three. The extraction pipeline applies the same
discipline to industry + framework knowledge.

## Anti-patterns

- **Don't duplicate the bookkeeping scoring math.** Use
  `bookkeeping.score_item()` directly. The stub scorer is for tests
  + environments where bookkeeping isn't importable — never used in
  production.
- **Don't leak tenant slugs.** The canary test (14 × 3 = 42 tokens)
  catches this. If it fires, fix the policy, not the test.
- **Don't hard-code anonymization terms.** Use
  `AnonymizationPolicy.redact_terms` + the journal-derived auto-list.
- **Don't file entities directly.** Every candidate goes through the
  bookkeeping P8 gate + the review queue. The candidate-vs-active
  status distinction is what makes the human review gate visible.

## Re-extraction safety

Running the pipeline twice on the same engagement produces two queue
records with different timestamps. The entity stub file is
overwritten if it exists — this is fine because the candidate's slug
is deterministic and the body changes only if the engagement journal
changes. To preserve a prior stub, copy it before re-running.

## Phase 2 enhancements (out of scope for M7)

- LLM extraction rules to replace rule-based ones (once a corpus of
  ≥3 same-industry concluded engagements exists).
- NER-based personal-name detection (replaces the regex heuristic).
- Project-codename declaration on `Engagement.tenant` so codenames
  flow into `redact_terms` automatically.
- Cross-engagement synthesis: detect a recurring pattern across
  multiple candidates and propose merging them into a higher-level
  entity.
