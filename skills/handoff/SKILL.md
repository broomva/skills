---
name: handoff
description: |
  Fresh-session handoff doc drafting. Produces a stable, single-file
  human-readable narrative state for the NEXT agent context (fresh
  session, after `/clear`, after persist iteration, after a tab close).
  The artifact lives at `docs/handoffs/YYYY-MM-DD-<arc>.md` and follows
  a stable shape: TL;DR + State-of-the-world (P15 snapshot) +
  What-was-delivered (PR table with SHAs) + First action + Pickup state.
  Distinct from P12 persist's `PROMPT.md` (machine-state for
  cross-context loop) and the P1 Bridge session log (raw transcript) —
  the handoff is the narrative bridge a human reads in ten seconds and
  a fresh agent reads in thirty.
  Use when: (1) ending a substantive session that another agent will
  continue, (2) preparing a fresh-session pickup point mid-arc,
  (3) needing to compress a multi-PR arc into a single resumable
  document, (4) the user says "write a handoff" / "fresh-session
  handoff" / "let me come back to this tomorrow".
  Triggers on "handoff", "fresh-session", "fresh session", "pickup",
  "where we are", "leave off", "for the next session", "resume tomorrow",
  "stage continuation", "for the next agent".
---

# handoff — Fresh-session handoff doc skill

**Compress a substantive arc into a single resumable doc the next agent
loads cold.**

## Why this skill exists

Across the 7-day window 2026-05-18 → 2026-05-24, **nine fresh-session
handoff docs** were drafted by hand. Six landed in `docs/handoffs/`
(Houston substrate completion, BRO-1208 streaming hang, Houston
advanced-settings wave, Life-Houston H1 runner refactor, Stage 1
fresh-session, etc.) and three landed in `docs/conversations/HANDOFF-*`
(substrate completion arc, BRO-1180 four pillars, Spec J real-Anthropic
smoke). All shared the same shape — the recurrence met rule-of-three
(P16) ~3× over.

Before this skill, the writer rebuilt the structure each time: which
sections appear, what order, what level of detail per section, which
git SHAs to cite, how to phrase the "first action". The skill captures
the canonical shape so subsequent handoffs are produced consistently
in a single pass.

## What this skill provides

1. **Template** (`references/handoff-template.md`) — the canonical
   section structure, with annotations explaining each section's
   purpose and stop condition.
2. **Anti-patterns** below — what NOT to include (the failure modes
   that produce unusable handoffs).
3. **Composition rules** — when to use this skill alone vs. compose
   with `persist` (P12), `bookkeeping`, or `make-spec`.

## When to invoke

- **End of substantive in-session work** that another agent (or the
  same user in a fresh context) will resume.
- **Mid-arc snapshot** when context is approaching 100K tokens and
  the user wants to break before continuing in a fresh context (this
  is the *handoff* half of P12 — `PROMPT.md` is the *state-replay* half).
- **Stage boundary** in a multi-stage arc (Stage 0 → Stage 1 →
  Stage 2 pattern that appeared 4× in the Houston/Life-Houston work).
- **Before merging the last PR of a substantial arc** so the next
  agent inherits the arc's lessons and remaining loose ends.

## Carve-outs (do not invoke)

- Single-PR work that's fully self-contained → just the PR description suffices.
- Pure read questions → no handoff needed.
- Continuation of work in the same context → no fresh-context boundary.
- Personal-life retrospective → use the Telos surface, not this.

## The canonical shape (mirrors `references/handoff-template.md`)

```
# <Arc name> — <Stage / Phase>

**TL;DR.** <One-sentence summary of where we are; ends with the FIRST ACTION.>

## State of the world (P15 snapshot YYYY-MM-DD)

- **<Repo 1>** — <branch>, ahead N / behind M vs origin/main. Last commits …
- **<Repo 2>** — <branch>, last merged PRs with SHAs.
- **<Running services / dev daemons>** — STILL RUNNING / DEAD; restart command if dead.

## What <arc> delivered (so the next agent doesn't redo it)

| PR | Crate(s) / files | What it gave |
|----|------------------|--------------|
| #N | … | … |

## E2E proof (re-runnable any time the prereqs hold)

```bash
<exact command>
# Expected: <observable output>
```

## First action

<The single next step the fresh agent should take, with the exact command
or file path. NO ambiguity. NO "consider X or Y" — pick one.>

## Pickup state (what's open)

- [ ] <open thread 1>
- [ ] <open thread 2>

## Related context

- Lessons doc: `docs/<...>.md`
- Linear: BRO-NNNN
- Prior handoff: `docs/handoffs/<earlier>.md`
```

## The five anti-patterns this skill exists to prevent

| Anti-pattern | Failure mode | Fix |
|---|---|---|
| **Missing P15 snapshot** | Fresh agent reasons against stale state (last-seen instead of current); duplicates work or conflicts with unmerged work. | Always include git status + branch + ahead/behind + open PRs + daemon state. |
| **No "first action" / vague "first action"** | Fresh agent spends 10+ minutes triangulating where to start. | Pick ONE concrete next step with the exact command/file path. If ambiguous, pick anyway and document the alternative as "if blocked, try X". |
| **PR table without SHAs** | Fresh agent can't reproduce the substrate state; doesn't know whether a PR landed or just opened. | Always cite the merge SHA next to each delivered PR. |
| **Lessons buried in prose** | Lessons silently lost because no skim-reader will find them in paragraph 8. | Pull lessons into a labeled section OR link to a separate `<arc>-lessons.md`. |
| **Aspirational scope** | "Next we should also do A, B, C, D, E …" with no priority. Fresh agent thrashes. | List ONLY the next 1–3 actions. Defer A, B, C, D, E to Linear backlog or a separate planning doc. |

## File placement

- **Workspace handoff** (cross-repo or workspace-governance): `docs/handoffs/YYYY-MM-DD-<slug>.md`
- **Project-local handoff** (single repo): `<repo>/docs/handoffs/YYYY-MM-DD-<slug>.md`
- **Legacy location** (still acceptable, gradually migrate): `docs/conversations/HANDOFF-YYYY-MM-DD-<slug>.md`

Filename slug should name the **arc**, not the date. The date is the
mtime, the slug is the identifier.

## Composition rules

| Compose with | When |
|---|---|
| **`persist` (P12)** | When the handoff is the prelude to a fresh-context loop. The handoff is the human-readable narrative; `PROMPT.md` is the machine-readable state. Both exist; they're different artifacts. |
| **`bookkeeping`** | When the handoff cites lessons that should also live as entity pages (`research/entities/pattern/<lesson>.md`). File the lesson via `bookkeeping file` AFTER the handoff is written; reference the entity in the handoff's "Related context" section. |
| **`make-spec`** | When the handoff is dense enough that a separate HTML companion (spec / plan) is warranted. The handoff stays markdown; the companion is HTML. P18 audience rule: handoff is agent-loaded → markdown. |
| **`/p9 watch`** | If the handoff is being written mid-CI (after a push, before merge), include the watch command + PR number so the next agent doesn't restart the wait. |

## Validation (handoff self-test)

A well-formed handoff passes all five checks:

- [ ] **TL;DR** is one sentence and names the first action explicitly
- [ ] **P15 snapshot** covers every repo touched in the arc + every long-running daemon
- [ ] **PR table** cites merge SHAs (not just PR numbers)
- [ ] **First action** is a single concrete step with the exact command or file path
- [ ] **Pickup state** lists ≤5 open threads (more than 5 = aspirational scope; split into a separate plan doc)

## References

- Canonical examples: `docs/handoffs/2026-05-24-stage1-fresh-session.md`, `docs/handoffs/2026-05-23-life-houston-h1-runner-refactor.md`, `docs/handoffs/2026-05-22-bro-1208-streaming-hang-handoff.md`
- Template: `references/handoff-template.md`
- Related primitive: P12 persist (cross-context loop); P15 state-snapshot; P18 audience
- Related skills: `persist`, `bookkeeping`, `make-spec`, `autonomous`
