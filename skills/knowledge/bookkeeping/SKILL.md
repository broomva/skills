---
name: bookkeeping
category: knowledge
version: 1.0.0
primitive: P6
description: Universal knowledge engine — scores, promotes, and compounds knowledge across all sources into a permanent, query-able entity graph
author: broomva
tags:
  - knowledge-graph
  - knowledge-extraction
  - scoring
  - entity-graph
  - bstack
  - p6
compounding:
  - social-intelligence
  - knowledge-graph-memory
  - content-creation
  - deep-dive-research
---

# bookkeeping — Universal Knowledge Engine

The bookkeeping skill is **bstack primitive P6**: the universal knowledge bookkeeping layer that sits beneath every knowledge-producing workflow in the Broomva stack. It implements the LLM Wiki pattern (Karpathy): raw sources flow in, get scored, scatter into entity pages, deduplicate against the existing graph, and compound into synthesis notes. Every other skill that produces knowledge delegates its extraction and promotion phases here.

---

## When to Invoke

- After any knowledge-gathering session: social engagement runs, research experiments, deep-dive sessions, conversation transcripts
- When prompted with `/bookkeeping` or `bookkeeping run`
- Automatically after the `social-intelligence` loop runs (Phase 2 — Knowledge Extraction — is fully delegated here)
- Before creating synthesis notes or flagging blog post candidates
- When asked to "extract knowledge from", "distill", "index", or "promote" any content
- When entity pages are stale or lint errors are detected in the entity graph

## Reflexive Trigger Rule (binding on every agent in this workspace)

Bookkeeping — and knowledge capture generally — is a reflex, not a request, **and never a question**. Agents must invoke `bookkeeping.py` and file graph-worthy material without being prompted in any of these situations:

1. **Before committing a feature/page that reads from the graph** — anything consuming `~/.config/bookkeeping/status.json`, `research/entities/`, or a snapshot at `apps/*/public/data/bookkeeping.json`. The data must be fresh at commit time.
2. **Before committing a synced snapshot to a public surface** — e.g., `apps/*/public/data/bookkeeping.json`. The committed copy must reflect a freshly-run pipeline.
3. **At the close of any substantial work session that produced graph-relevant material** — new names, decisions, concepts, partnerships, threads, design debates. The pipeline ingests/scores/promotes so the next session starts indexed.
4. **Before a substantial promotion run, prefer `bookkeeping replay` over `bookkeeping run`** — `run` reads from the live graph it writes to (the *shadow-dream* corruption mode). `replay` runs against a frozen snapshot first; review the diff; then `--commit` if the changes look right. Use `run` for small, well-scoped extractions; use `replay` for cross-source consolidation passes or any time the graph has grown materially since the last run.
5. **The moment a session surfaces a discrete graph-worthy item** — a decision, a name, a discovered tool/person/paper, a recurring pattern, or a typed relation inferred between entities. File it proactively (entity page, `related:` edge, or synthesis note) **as part of the work** and report what you filed in one line. Do **not** ask the user whether to record it.

**Never a question.** The interrogative form — *"do you want me to create an entry / file this into the knowledge graph?"* — is forbidden. Capture is the default action, not an opt-in the user approves; the agent files first and reports after, so the user vetoes *after* (cheap: `git revert` / delete the entity), never gates *before*. Surfacing graph-worthy material and then deferring its capture to a user yes/no is the **permission-to-document anti-pattern**: knowledge that waits for permission is knowledge lost. Two bounds keep this safe rather than spammy: (a) capture is gated by the **Nous score** (proactive ≠ indiscriminate — a low-confidence inference goes to a synthesis note, not a committed entity); (b) an **explicit standing instruction not to record** something, or material the agent has reason to treat as sensitive/private, overrides the default — those are the *only* cases where the agent withholds capture, and it does so silently, not by asking permission to document. See `research/entities/pattern/proactive-documentation.md`.

Mental checklist before declaring graph-dependent work done: *Did this session produce material that belongs in the graph? Does my feature read graph state? Am I about to commit a snapshot? Should I be using `replay --commit` instead of `run` here?* — yes to any → invoke bookkeeping / file it before committing, **without asking**.

---

## Pipeline — 7 Stages

Each stage is idempotent. Stages can be run individually or as a full pipeline via `bookkeeping run`.

### Stage 1 — INGEST

Load raw sources from any of: JSONL run logs, conversation transcripts (Markdown), web clips, manual notes, social engagement logs. Normalize every item to the canonical source record:

```json
{
  "source_id": "sha256-prefix-8chars",
  "type": "social_comment | transcript | web_clip | note | experiment_log",
  "content": "...",
  "timestamp": "ISO-8601",
  "metadata": {
    "origin": "moltbook | x | conversation | web | manual",
    "author": "...",
    "url": "...",
    "session_id": "..."
  }
}
```

All ingested records are appended to the Layer 2 raw extract file at `research/notes/YYYY-MM-DD-{source}-raw.md` and to `~/.config/bookkeeping/run-log.jsonl`.

### Stage 2 — SCORE

Two-pass scoring against the Nous gate rubric (full spec in `references/scoring-rubric.md`):

**Dimensions** (each 0–3):
- `novelty` — Is this genuinely new to the knowledge graph?
- `specificity` — Is this concrete and actionable, not generic?
- `relevance` — Does this connect to active projects, research threads, or strategic concerns?

**Heuristic fast-path** (no LLM call needed):
- Score ≤ 2 → discard immediately (clearly low-signal)
- Score ≥ 7 → promote immediately (clearly high-signal)

**LLM-as-judge** for ambiguous band (score 3–6):
- Pass item + existing entity graph context to judge (see LLM Judge Spec below)
- Output: per-item score tuple `(novelty, specificity, relevance)` + total + promote flag + candidate entity slugs

Scoring output is written to the raw extract file as a YAML front-matter annotation per item.

### Stage 3 — SCATTER

From each high-scoring source item, extract N candidate entity concepts (0–5 per source). Each candidate becomes a potential entity page in the graph. Scatter means one source can produce multiple entities — a single research thread might yield a tool entity, a person entity, a technique entity, and a project entity.

Candidates are output as slug strings (lowercase, hyphen-separated): `e.g. "bitnet-ternary-weights", "karpathy-llm-wiki-pattern"`.

### Stage 4 — RESOLVE

Deduplicate candidates against the existing entity graph:

1. **Exact wikilink slug match** — check `research/entities/{type}/{slug}.md` directly
2. **Fuzzy title match** — compare candidate title against all existing entity titles (cutoff: 0.80 similarity). If match found → update existing entity. If no match → create new entity.

Resolution prevents graph fragmentation. A single concept must not appear under multiple slugs.

### Stage 5 — PROMOTE

Apply promotion decision based on total score:

| Score | Action | Destination |
|-------|--------|-------------|
| ≥ 5   | Promote | `research/entities/{type}/{slug}.md` (Layer 3) |
| 3–4   | Hold    | Stays in `research/notes/YYYY-MM-DD-{source}-raw.md` (Layer 2) |
| ≤ 2   | Discard | Dropped, not written |

Entity page type is inferred from the candidate context: `tool`, `person`, `concept`, `project`, `paper`, `pattern`, `dataset`. Use the template at `templates/entity-page.md` when creating new pages.

### Stage 6 — SYNTHESIZE

After promotion, scan the entity graph for clusters: groups of 3 or more entities that share tags or reference each other via `[[wikilinks]]`. For each cluster:

1. Check if a synthesis note already exists in `research/notes/` covering that cluster
2. If not → flag the cluster as a synthesis candidate with a suggested filename: `YYYY-MM-DD-{cluster-topic}-synthesis.md`
3. Synthesis candidates are written to `~/.config/bookkeeping/status.json` under `pending_synthesis`

Synthesis notes are not auto-generated — they are flagged for human or agent authorship. The bookkeeping skill creates the scaffold, not the prose.

### Stage 7 — LINT

Validate all entity pages in `research/entities/` against the schema (full spec in `references/entity-schema.md`):

Errors (block-worthy, surfaced as `error`):

- `core_claim` field present and ≤ 140 characters
- `sources` field present and non-empty
- `related` field uses `[[wikilink]]` format (not bare URLs or plain text)

Warnings (non-breaking nudges, surfaced as `warning`):

- No broken wikilinks (all `[[slug]]` references resolve to existing entity files)
- `status` field is one of: `raw`, `candidate`, `entity`, `synthesis`, `archived`
- `type` field is one of: `concept`, `pattern`, `tool`, `person`, `project`, `discovery`, `question`, `framework-refinement`, `industry-pattern`, `persona`, `org`
- **Frontmatter dates are quoted** — an unquoted `created: 2026-05-30` re-serializes to a full timestamp on edit and breaks `YYYY-MM-DD` queries; mechanically auto-fixable via `lint --fix`
- **Tags are controlled-vocabulary** — every tag ∈ `research/entities/_tags.md` (81 canonical tags); no missing tags, no type-redundant tags (a tag equal to `type:`); the check no-ops if `_tags.md` is absent
- **`contradicts:` carries a resolution** — a non-empty `contradicts:` list must have a body `## Contradiction`/`## Resolution` section
- `## Timeline` entries (when present) carry a leading ISO date

> Enum values defer to `references/entity-schema.md` (the schema is authoritative for `type`/`status` membership); SKILL.md remains authoritative for thresholds, stages, and layers.

Lint report is written to stdout and to `~/.config/bookkeeping/status.json` under `lint_errors`. A non-zero lint error count does NOT block the pipeline — it surfaces warnings only. `lint --fix` mechanically repairs the auto-fixable classes (`related:` format, unquoted dates).

---

## Self-Maintenance Rules (CRITICAL)

These rules govern any agent that modifies files in this skill. They are enforced by reasoning, not by hooks. When you touch any file under `skills/bookkeeping/`, you MUST apply these rules before completing the task.

**Rule 1 — Stage count consistency**
When adding, removing, or renaming a pipeline stage: update the stage count and stage list in BOTH this file AND `README.md`. The stage count in both files must always match.

**Rule 2 — Scoring threshold consistency**
When changing the promote threshold (currently ≥5), the discard threshold (currently ≤2), or the heuristic fast-path boundaries (currently ≤2 / ≥7): update BOTH this file AND `references/scoring-rubric.md`. The two files must always agree on all threshold values.

**Rule 3 — Entity schema consistency**
When adding a new entity `type` value or a new `status` value: update BOTH `references/entity-schema.md` AND `templates/entity-page.md`. The template must always reflect all valid field values defined in the schema.

**Rule 4 — Layer definition consistency**
When changing the layer count (currently 4) or redefining layer boundaries: update BOTH this file AND `references/promotion-workflow.md`. All destination path patterns must be consistent across both files.

**Rule 5 — Post-modification verification**
After any modification to any file in this skill, run:
```bash
python3 scripts/bookkeeping.py lint --all
python3 scripts/bookkeeping.py status
```
Fix all lint errors before considering the task complete.

**Rule 6 — SKILL.md is authoritative**
This SKILL.md is the single source of truth for all thresholds, stage definitions, and layer boundaries. All other files in this skill (references/, templates/, README.md) defer to it. If a conflict exists between this file and any other file, this file wins and the other file must be updated.

---

## CLI Reference

```bash
python3 scripts/bookkeeping.py run                    # Full 7-stage pipeline
python3 scripts/bookkeeping.py replay                 # Score against frozen snapshot (no writes)
python3 scripts/bookkeeping.py replay --commit        # Apply replay's proposed promotions
python3 scripts/bookkeeping.py ingest --source FILE   # Ingest single file
python3 scripts/bookkeeping.py score --file FILE      # Score items in raw extract
python3 scripts/bookkeeping.py promote --file FILE    # Promote pending items
python3 scripts/bookkeeping.py synthesize             # Detect clusters, flag candidates
python3 scripts/bookkeeping.py synthesize --gaps      # + ranked ## Gaps report (goal-formation)
python3 scripts/bookkeeping.py synthesize --gaps --backlog  # JSON Backlog ticket candidates → file via Linear MCP
python3 scripts/bookkeeping.py lint --all             # Validate all entity pages
python3 scripts/bookkeeping.py lint --all --health    # + 0-100 health score + remediation plan
python3 scripts/bookkeeping.py bench                  # Retrieval benchmark (P@5/R@5/MRR)
python3 scripts/bookkeeping.py status                 # Show knowledge graph stats
python3 scripts/bookkeeping.py query "concept-slug"   # Find and display entity page
```

The pipeline remains **7 stages** (Ingest → Score → Scatter → Resolve → Promote → Synthesize → Lint). `bench`, `synthesize --gaps`, and `lint --health` are *subcommands/flags*, not new pipeline stages.

All commands accept `--dry-run` to preview changes without writing. All commands write structured output to `~/.config/bookkeeping/run-log.jsonl`.

### `bench` — retrieval benchmark (P@k / R@k / MRR)

Measures the **same two-tier retrieval the `kg` load skill performs** (tier-1 catalog scoring over `docs/knowledge-index.md`; tier-2 body-grep fallback) against a labeled fixture, so the numbers describe real retrieval quality, not a mock.

```bash
python3 scripts/bookkeeping.py bench                            # default fixture, k=5
python3 scripts/bookkeeping.py bench --k 10 --json              # widen cutoff, JSON out
python3 scripts/bookkeeping.py bench --fixture path/to.jsonl    # custom fixture
```

- Fixture: `fixtures/brainbench.jsonl` — one `{"query","expected":["type/slug",...],"notes"}` per line. Every `expected` id is a real `research/entities/{type}/{slug}` page.
- Metrics are macro-averaged (mean of per-query P@k / R@k / reciprocal-rank). Single-gold queries cap P@k at `1/k` by construction — read P@k alongside R@k and MRR.
- Machine-readable results are written to `~/.config/bookkeeping/bench-latest.json` (for trend tracking across catalog regenerations).
- Unit tests for the metric math + gaps→backlog export: `scripts/test_bench.py` (stdlib `unittest`, 46 cases). **CI-gated** on every push/PR via `.github/workflows/test.yml` (test suite + a CLI smoke) so retrieval metrics and the export can't silently regress.

### `synthesize --gaps` — gap analysis (goal-formation)

A **gap** is where the graph is incomplete in a way that blocks retrieval or signals an unanswered research question: (a) unresolved `[[wikilink]]` targets, (b) missing/over-long `core_claim`, (c) highly-referenced **stubs** (short body but ≥3 inbound refs). Each gap is scored by inbound-reference frequency and emitted as a ranked `## Gaps` markdown section. High-leverage gaps (≥3 inbound refs, or broken links with ≥2 referrers) are written to `~/.config/bookkeeping/status.json` under `pending_gaps` — candidate **Backlog** research questions (the script never calls Linear). `pending_gaps` is recomputed on every `synthesize` run regardless of the `--gaps` flag.

**`--backlog` — Pillar-2 goal-formation close.** `synthesize --gaps --backlog [--backlog-cap N]` emits the high-leverage gaps as JSON **ticket candidates** (`title`, `body`, stable `dedup_key`, `leverage`), ranked by leverage and **deduped** (the same slug across type dirs — e.g. `concept|pattern|tool/bstack` — collapses to one candidate). The engine **never files tickets**: filing is **agent-mediated through the Linear MCP** after a **P20 reasoning-enforced quality pass** ("is this a real, actionable research question?"). This honors the workspace's *Linear-via-MCP, never CLI/API* rule (the CLI defaults to the wrong workspace) and keeps the knowledge engine free of network side-effects. The `dedup_key` (`kg-gap:<kind>:<slug>`) lets the filer skip gaps already promoted, so the loop is idempotent across runs. Flow: `synthesize --gaps --backlog` → agent reads candidates → quality-filters → files top-N into Linear Backlog via MCP.

### `lint --health` — health score + remediation plan

Computes a `0-100` health score — `100 * (1 - weighted_issues / total_entities)`, errors weighted `1.0`, warnings `0.3`, capped at `[0,100]` — and prints a **dependency-ordered remediation plan**: broken-wikilink TARGETS first (creating one missing page unblocks every referrer), then missing/over-long `core_claim`, then enum non-conformance. Implied by `lint --all`.

### `replay` — closes the shadow-dream corruption mode

`bookkeeping run` reads from the same graph it writes to. The local research entity at `research/entities/concept/multi-tier-dreaming.md` (scored 9/9) explicitly identifies this as a *"shadow dream"* — gather + consolidate without the **replay** phase. The corruption mode hasn't fired yet only because the graph is small.

`replay` adds the missing replay phase:

1. **Gather** — read the source files (or auto-discover all `*-raw.md`)
2. **Replay** — copy `research/entities/` into a tempdir; score+promote against the *frozen* copy
3. **Prune** — items below threshold or failing lint are flagged; replay reports counts
4. **Consolidate** — pass `--commit` to apply the proposed promotions to the live graph (re-runs the scoring against the live state to ensure idempotence)
5. **Index** — `git diff research/entities/` is the audit trail; the agent or human inspects before merging

Without `--commit`, replay is **read-only** — pure diagnostic. With `--commit`, replay re-runs the pipeline against the live graph (so the diff applies cleanly to the same starting state the human approved).

Smoke-tested against the live workspace: 3 raw extracts gathered, 178 entities frozen in tmpdir, 96 items scored (15 below threshold, 81 would-promote, mean 5.4/9). No writes without `--commit`.

### `render` — Category B projection (MD → single-file HTML)

```bash
bookkeeping render <path>             # render a single .md file
bookkeeping render <dir>/             # glob *-synthesis.md in directory
bookkeeping render --layer 4          # all Layer-4 synthesis notes
bookkeeping render --link-html        # rewrite [[slug]] → .html targets
bookkeeping render --verbose          # log each rendered file
```

Produces a deterministic single-file HTML projection alongside the source MD.
The HTML carries `canonical:` frontmatter pointing back to the source MD; it
is gitignored by default and regenerable. See the **Format Discernment (P18 ·
Audience)** section below for when to use this vs keep MD-only.

`render` is the **lossless floor**, not the rich ceiling: it can only express
what CommonMark expresses (no diagrams, SVG, charts, or interactivity — by
design, "avoids client-side dependencies"). When the artifact's *presentation*
carries knowledge, do **not** reach for `render` — generatively author a
**Category C** rich HTML document (see below).

---

## Format Discernment (P18 · Audience)

Before emitting any artifact, classify into one of three categories. Choose
format from the category, not the other way around.

### Category A — Substrate (MD, always)

Any artifact another agent, governance system, or `bookkeeping` will re-read,
lint, score, or grep:

- `research/entities/**/*.md` — graph nodes
- `research/notes/*-raw.md` — Layer 2 extracts
- `research/notes/*-synthesis.md` — Layer 4 canonical (HTML is a *projection*, see B)
- `CLAUDE.md`, `AGENTS.md`, `METALAYER.md` — governance, L3
- `skills/*/SKILL.md` — skill packages, agent-consumed
- `docs/superpowers/specs/*.md`, `plans/*.md` — superpowers consumed
- `docs/conversations/*.md` — conversation bridge output
- `.control/policy.yaml`, `schemas/*.json` — already non-MD, same category

**Invariant:** HTML breaks substrate. MD-only. Frontmatter at top.

### Category B — Projection (MD canonical + HTML on demand)

Artifacts authored and re-edited as text but consumed by a human as a rendered
document:

- Layer 4 synthesis notes (blog-post candidates)
- Weekly retros, status updates, post-mortems
- Architecture explainers (large reviews)

**Behavior:** MD is source-of-truth (lintable, scored, agent-readable).
`bookkeeping render <path>` projects to HTML for human-read events. HTML is
`.gitignored`, regenerable, carries `canonical:` frontmatter pointing back
to MD.

### Category C — Native (generatively authored; the medium IS the value)

Artifacts where the **presentation itself carries knowledge** — diagrams,
interactive views, or multiple data-representation modalities convey what
prose-in-markdown cannot. No useful MD source exists (an MD version would lose
the thing that makes the artifact valuable). Examples: architecture and
decision documents, system explainers, dashboards, interactive demos, drag-drop
boards, animation sandboxes; future `.ipynb` analyses, `.tldr` canvases,
`.svg` packs.

**This is NOT a `render` projection and NOT a template fill.** The agent
**generatively authors** the artifact — bespoke for *this* content, in *this*
session, informed by the actual data + relevant `research/entities/` + session
research. There is deliberately **no component/template library to assemble
from**: a fixed kit ossifies and under-fits the content. Generative authoring
adapts to each context. This skill *directs* the generation (below); the
agent's generative capacity is the engine.

**Generation menu** — pick the modalities the content needs, author them fresh:

| When the content is… | Generate… |
|---|---|
| A system / architecture | inline **SVG** diagram, hand-authored for that system |
| A process / workflow / state machine / sequence | inlined **Mermaid** or SVG |
| Tradeoffs / options / criteria | sortable/filterable **tables**, interactive **decision matrices** |
| A layered system | **tier-stack** diagram |
| Time / evolution / roadmap | **timeline** |
| A hierarchy / taxonomy | **tree / nested** view |
| Quantitative data | **charts** (inline SVG or inlined lib), **metric/stat cards** |
| Dense reference | **collapsible** sections, **tabs**, sticky **table-of-contents** nav |
| Relationships | **node-link graph** |
| Code / config | annotated, syntax-highlighted blocks |

**Constraints (the how — binding):**

1. **Self-contained single file.** Inline all CSS/JS/SVG; system-font stack;
   **no external CDN or network dependency** (deterministic, offline, portable,
   archival — the same value `render` enforces). If a library is genuinely
   needed (e.g., Mermaid), inline it; don't CDN-link it.
2. **Accessible & responsive.** Semantic HTML, light/dark, keyboard-navigable,
   legible at any width; degrades to readable static content with JS disabled.
3. **Graph-integrated.** Carry frontmatter in the format's idiomatic carrier
   (HTML-comment YAML for `.html`, notebook `metadata` for `.ipynb`, sidecar
   `.meta.yaml` for binaries) with at least `type` + `slug`; render wikilinks as
   `<a data-relation="…">` anchors; include `canonical:` when an MD source
   exists. Category-C artifacts still pass `bookkeeping lint` and rejoin the
   graph.
4. **Rich by default.** Once an artifact qualifies as C, author it *to the
   ceiling*, not to the minimum that clears the predicate. Default to the full
   expressive range the content can carry: diagrams + flows + the right
   data-representation modalities from the menu, purposeful motion and
   interaction (transitions, hover/focus affordances, expand/collapse, filter,
   sort, step-through), and the depth the subject actually warrants. **Length
   and structure follow the content, not a cap** — a dense architecture or
   decision doc may be long, sectioned, tabbed, or **multiple linked HTML
   pages** (an `index.html` + sibling pages under one `docs/<arc>/` dir, linked
   with relative `<a href>`); a small explainer stays one tight page. "As
   complex as needed" is the rule; gratuitous complexity for its own sake is
   still the anti-pattern. The floor (`render`) is for B; C does not settle for
   floor-grade output.

**Design-craft composition (the polish layer).** The constraints above are the
*correctness* floor (portable, accessible, graph-integrated). They are not a
*visual-craft* bar — and craft is deliberately **not** machine-checked
(the workspace declined to promote "premium/best-in-class" to an invariant
because it has no lint gate; see the Ritual-vs-Substance table in `CLAUDE.md`).
Craft therefore stays a **convention**, but a *named, discoverable* one: when
generatively authoring a Category-C artifact, **compose with the design layer**
for visual quality rather than relying on raw generative instinct —

| Skill | Use for |
|---|---|
| `ui-ux-pro-max` (plugin) | layout systems, 50+ styles, color palettes, font pairings, chart types — the broad UI/UX intelligence menu |
| `impeccable` | visual hierarchy, information architecture, cognitive-load reduction, spacing/typography/alignment audit, ambitious-but-tasteful visual effects |
| `make-interfaces-feel-better` / `emil-design-eng` | interaction & motion polish — the invisible details (easing, timing, affordance, state transitions) that make a doc feel crafted |
| `arcan-glass` | Broomva brand tokens (Arcan Glass design language) when the artifact is brand-facing |

Pull from these at authoring time the same way you pull modalities from the
generation menu. They set the *craft* bar; the four binding constraints set the
*correctness* floor. Both apply — neither substitutes for the other. Because
craft is a convention not a gate, a C artifact never *fails lint* for being
plain; but the standing instruction is to author rich, not plain.

**Floor vs ceiling.** `bookkeeping render` (Category B) is the deterministic
*floor* — a lossless MD→HTML projection of text-expressible content. Category C
is the *ceiling* — generatively authored rich HTML where the medium is the
value. Never force `render` to be rich; never settle for `render` when the
content deserves C.

### Predicate Test

The agent applies these in order at artifact-creation time:

1. Will any agent or substrate re-read this as text? → **A**
2. Does an MD source-of-truth exist (or should exist), with content fully
   expressible as text? → **B** (`render` projects it on demand)
3. Does the artifact's **presentation carry knowledge** — diagrams, interaction,
   or multiple data-representation modalities markdown can't hold? → **C**
   (generatively author rich self-contained HTML; not a `render` projection,
   not a template)

**Tiebreaker:** when ambiguous between B and C, default to **B** (reversible,
lower disruption). But do not let the tiebreaker downgrade a genuinely visual /
interactive artifact to a flat projection — if the modalities in the generation
menu would materially help the reader, it is **C**.

### Enforcement

Four lint checks via `bookkeeping lint --all`:

| Check | Severity | Trigger |
|-------|----------|---------|
| `stale_projection` | warning | `<note>.md` mtime > `<note>.html` mtime |
| `broken_canonical` | error | `<note>.html`'s `canonical:` field doesn't resolve to existing sibling MD |
| `substrate_violation` | error | Non-`.md` file under `research/entities/` (hidden dirs like `.lago-blobs/` excluded) |
| `unregistered_c` | warning | `.html` under `research/notes/` with no frontmatter AND no sibling MD |

Full reference and worked examples: `references/format-discernment.md`.

---

## 4-Layer Knowledge Lifecycle

```
Layer 1 — Ephemeral (never stored)
  Social threads, passing ideas, unprocessed conversation fragments.
  Lives only in context windows. Discarded after session.

Layer 2 — Raw Extracts  research/notes/YYYY-MM-DD-{source}-raw.md
  Ingested + scored items. Score 3-4 items rest here.
  Reviewed manually or swept by next bookkeeping run.

Layer 3 — Entity Pages  research/entities/{type}/{slug}.md
  Promoted items (score ≥5). Structured, query-able, wikilinked.
  The permanent knowledge graph. Source of truth for the vault.

Layer 4 — Synthesis Notes  research/notes/YYYY-MM-DD-{topic}-synthesis.md
  Cluster-level understanding. Written when ≥3 entities share a theme.
  Blog candidates and architectural decisions live here.
```

---

## Output Locations

| Output | Path |
|--------|------|
| Layer 2 raw extracts | `research/notes/YYYY-MM-DD-{source}-raw.md` |
| Layer 3 entity pages | `research/entities/{type}/{slug}.md` |
| Layer 4 synthesis notes | `research/notes/YYYY-MM-DD-{topic}-synthesis.md` |
| Run log (JSONL) | `~/.config/bookkeeping/run-log.jsonl` |
| Status + lint report | `~/.config/bookkeeping/status.json` |

---

## Integration Points

| Skill | Integration |
|-------|-------------|
| `social-intelligence` | Delegates Phase 2 (Knowledge Extraction Loop) entirely to bookkeeping. After each engagement run, calls `bookkeeping run` on the loop-log.jsonl. |
| `knowledge-graph-memory` | Receives entity page paths after promotion. Indexes them into the Obsidian vault via the symlink layer. |
| `content-creation` | Receives blog candidate flags from `status.json` → `pending_synthesis`. Picks up entity wikilinks as source material. |
| `deep-dive-research` | Outputs raw research logs that bookkeeping ingests. Ensures research sessions feed the permanent entity graph, not just the conversation transcript. |
| `CLAUDE.md P6` | This skill is bstack primitive P6. Listed alongside P1–P20 in the Bstack Core Automation Primitives table. All sessions that produce knowledge are expected to run bookkeeping before closing. |

---

## LLM Judge Spec

Used in Stage 2 for the ambiguous band (score 3–6). The judge is called with the item text and a snapshot of relevant existing entities.

**System prompt:**
```
You are a knowledge quality evaluator for a personal knowledge OS (the Broomva bstack).
Your job is to score extracted knowledge items on three dimensions and decide whether to
promote them into the permanent entity graph.

Scoring dimensions (each 0–3):
  novelty      — 0: already well-represented in graph. 3: genuinely new concept or framing.
  specificity  — 0: vague, generic, or obvious. 3: concrete, named, actionable.
  relevance    — 0: unrelated to active projects or research threads. 3: directly applicable.

Promotion threshold: total ≥ 5 → promote = true.

Output ONLY valid JSON. No markdown fences, no explanation outside the JSON object.
```

**User prompt template:**
```
ITEM TEXT:
{item_content}

EXISTING ENTITY GRAPH CONTEXT (relevant excerpts):
{entity_context}

ACTIVE PROJECT TAGS FOR RELEVANCE SCORING:
{active_tags}

Score this item and identify candidate entity slugs it could produce.

Output format:
{
  "novelty": <0-3>,
  "novelty_reason": "<one sentence>",
  "specificity": <0-3>,
  "specificity_reason": "<one sentence>",
  "relevance": <0-3>,
  "relevance_reason": "<one sentence>",
  "total": <0-9>,
  "promote": <true|false>,
  "candidate_entities": ["slug-one", "slug-two"]
}
```

---

## Reference Files

| File | Purpose |
|------|---------|
| `references/scoring-rubric.md` | Full Nous gate rubric with examples for each score level |
| `references/entity-schema.md` | Complete entity page schema with all valid field values |
| `references/promotion-workflow.md` | Layer definitions, promotion decision tree, status transitions |
| `templates/entity-page.md` | Canonical template for new entity pages |
| `scripts/bookkeeping.py` | Main CLI implementation |
