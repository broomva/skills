---
name: role-x
primitive: P17
category: orchestration
description: |
  bstack P17 — Lens-Routed Request Articulation. The typed routing
  layer above P5 parallel-agent dispatch. On every substantive user
  input, the first-touch agent reflexively selects role lens(es) from
  `roles/<name>.md`, loads substantive context (files, conventions,
  domain checklists), and decides single-agent (augment) vs surfaced
  prompt-refinement (rewrite) vs parallel-team plan (decompose).
  No "act as X" persona theater — substantive context grounding only.
  Use when starting any session, before responding to any substantive
  user input. Composes with P5 (parallel-agent typing), P14 (the
  lens's quality_bar IS the domain-specific dep-chain trace), P15
  (state snapshot feeds signals), and P13 (dream cycle consolidates
  lens rules from telemetry).
---

# role-x — bstack P17 — Lens-Routed Request Articulation

**Primitive:** P17 in the Broomva Stack. See [`broomva/workspace`](https://github.com/broomva/workspace) `AGENTS.md` §P17 for the full reflexive trigger rule and the design spec at `docs/superpowers/specs/2026-05-13-role-x-primitive-design.md`.

## What this skill provides

1. **Lens registry**: `roles/_meta.md` (always-loaded base) + `roles/<name>.md` per-domain lenses. Each lens has YAML frontmatter (signals, context_loaders, quality_bar, prompt_improvement_patterns, default_mode, mode_escalation, out_of_scope) and a prose body.
2. **Selection algorithm** (reasoning-enforced): score each lens against current signals (paths, prompt_keywords, branch_patterns, linear_labels); threshold ≥ 2 matches; resolve `extends:` chain.
3. **Mode selection** (reasoning-enforced): `augment` (silent context load — default), `rewrite` (surfaced prompt refinement), `decompose` (P5 parallel-agent plan, user-approved). Mode escalation per the lens's `mode_escalation` field.
4. **CLI helpers** (`scripts/role-x.py`):
   - `role-x list` — list all available lenses with status + extends + default_mode
   - `role-x validate <path>` — validate lens YAML frontmatter against schema
   - `role-x index` — regenerate `roles/_index.md` discovery file
   - `role-x intake` (v0.2.0) — `UserPromptSubmit` hook entry point
   - `role-x suggest` (v0.4.0) — analyze events.jsonl; surface fire-rate + drift + emergent clusters
   - `role-x init <name>` (v0.4.0) — scaffold a `status: candidate` lens from CLI flags
   - `role-x coverage` (v0.4.1) — brief registry-health summary; silent when healthy (SessionStart hook entry point)
5. **Hooks** (`scripts/*-hook.sh`):
   - `role-x-intake-hook.sh` (v0.2.0) — `UserPromptSubmit` wrapper
   - `role-x-coverage-hook.sh` (v0.4.1) — `SessionStart` wrapper with 24h cooldown
6. **Reference docs** (`references/`):
   - `lens-schema.md` — YAML frontmatter field reference
   - `selection-algorithm.md` — scoring algorithm in detail
   - `mode-selection.md` — augment/rewrite/decompose decision tree
   - `feedback-loop.md` — Nous-pattern telemetry + P13 consolidation (M2+)

## When to invoke

### Intake reflex (every prompt)

Always — at the start of every session, before responding to substantive user input. P17 is a reflexive primitive. The skill exists to make the lens registry and CLI helpers discoverable; the *behavior* is enforced by reasoning + the UserPromptSubmit hook.

Carve-outs (no role-x intake needed): single-line typo fixes, pure read questions ("what does this function do?"), conversation continuation without new substantive request.

### Meta-progression discipline (v0.4.1+)

The intake reflex routes prompts in real-time. The meta-progression discipline ensures the *registry itself* grows from real telemetry:

| When | Action | Cadence |
|---|---|---|
| **SessionStart** in a workspace with the role-x coverage hook wired | `role-x coverage --since 7d` fires automatically; surfaces fire-rate + config hints when registry health drops | ≤1 nudge per 24h |
| **Per substantive prompt** | If intake routes to `_meta` only **AND** prompt is domain-rich (≥8 words, ≥4 distinct meaningful tokens) | Agent sees a 1-line `role-x init <slug>` suggestion appended to the intake context |
| **When the agent observes a recurring `_meta`-only pattern** within a session (e.g. 3+ unrouted prompts about the same domain) | Propose `role-x init <name>` to the user as the rule-of-three trigger | At the agent's discretion, surfaced as a one-line note |
| **Weekly (or after collecting ~50+ events)** | Run `role-x suggest --since 7d` for the full report — fire-rate, per-lens drift, emergent keyword clusters (requires sanitized capture on) | Manual, with telemetry signal from the SessionStart nudge |
| **After ≥3 positive-outcome uses of a `status: candidate` lens** | Author promotes the lens to `status: active` (P16 rule-of-three) | Manual, candidate ledger tracks instances |

### When NOT to invoke meta-actions

- Single-prompt sessions where the intake nudge is purely informational — don't pause work to author lenses mid-flow
- Edits to existing active lenses unless `role-x tune <lens>` (v0.5.0+) surfaces concrete drift signals
- New lenses without ≥3 distinct-session evidence in events.jsonl (avoids cargo-cult lens proliferation)

## When NOT to invoke

- One-shot read questions answered from context alone
- Conversation-only exchanges (no work to execute)
- Brainstorming / design discussion (use `superpowers:brainstorming` instead; role-x kicks in once implementation begins)

## Composition with other primitives

| Primitive | How role-x composes |
|---|---|
| **P5** parallel agents | role-x decompose mode produces the dispatch plan; each sub-agent runs role-x at its scope (typed edges in the reasoning graph) |
| **P13** dream cycle | lens consolidation via `role-x-replay.py` (M4 — planned, not yet shipped) — gather → replay → prune → consolidate → index |
| **P14** dep-chain | the lens's `quality_bar` IS the domain-specific P14 enumeration template |
| **P15** state snapshot | feeds the selection algorithm's signals |
| **P16** bstack engine | new lenses get promoted via per-lens rule-of-three (≥3 positive-outcome uses → `status: active`) |
| `/autonomous` | seeds `roles/_meta.md` content; remains invocable for the full reflex pipeline |
| `persona-*` skills | referenceable from lenses via `context_loaders.skills:`; not replaced |

## How to use

1. **Start of session** — agent reads `roles/_meta.md` + all `roles/*.md` (cached in working context). At UserPromptSubmit for substantive work, agent reasons through:
   - Snapshot signals (P15): current branch, touched files (`git diff --name-only`), prompt content, Linear ticket if any
   - Score each lens against signals (≥2 matches → applies)
   - Resolve `extends:` chain; merge context_loaders + quality_bar
   - Choose mode (augment / rewrite / decompose) per the lens's `default_mode` + `mode_escalation` rules
   - Surface mode + selected lenses to user **unless** mode is augment
   - Proceed with the user's request, applying the lens's quality_bar as the P14 dep-chain trace
2. **Adding a new lens** — author `roles/<name>.md` following the schema in `references/lens-schema.md`; run `role-x validate roles/<name>.md`; run `role-x index` to regenerate `roles/_index.md`; commit on a worktree branch; PR.
3. **Lens consolidation** (M4 — planned, not yet shipped) — `python3 scripts/role-x-replay.py <lens-name>` runs the P13 dream cycle against `~/.config/broomva/role/events.jsonl`.

## Cardinal invariant

> **No `act as X` persona rewrites.** Lenses load substantive context (files, conventions, checklists, optional suggestions). They do *not* insert persona declarations into the model's working context. The 2026 research (PRISM USC, Zheng et al. arXiv 2311.10054, Anthropic best-practices) is clear: persona declarations don't add expertise and frequently hurt accuracy for code/factual tasks (MMLU drops 71.6% → 66.3% with long expert personas).

## Files

- `roles/_meta.md` — always-loaded base lens (the workspace's implicit "bstack-aware autonomous senior engineer" contract made addressable). Lives in the consuming workspace, not in this skill repo.
- `roles/<name>.md` — per-domain lenses. Live in the consuming workspace.
- `roles/<name>.eval.yaml` — resolver-eval fixture (`should_fire` / `should_not_fire` intents) asserting the lens's trigger actually routes. Run via `role-x.py eval`; gate in CI. The skillify "resolver eval" step — a trigger that says "phrase X selects lens Y" is only trustworthy once a test proves it. Live in the consuming workspace alongside the lens.
- `roles/_index.md` — auto-generated discovery index.
- `scripts/role-x.py` — CLI helpers (`validate`, `list`, `index`, `intake`, `coverage`, `suggest`, `init`, `eval`).
- `references/*.md` — schema + algorithm reference docs.
- `~/.config/broomva/role/events.jsonl` — telemetry log (M2).
- `~/.config/broomva/role/status.json` — per-lens stats cache (M2).
- `~/.config/broomva/role/consolidation-runs/` — dream-cycle snapshots (M4).

## Related

- **Design spec:** [`broomva/workspace`](https://github.com/broomva/workspace)`/docs/superpowers/specs/2026-05-13-role-x-primitive-design.md`
- **Implementation plan:** [`broomva/workspace`](https://github.com/broomva/workspace)`/docs/superpowers/plans/2026-05-13-role-x-primitive-implementation.md`
- **Pattern entity:** [`broomva/workspace`](https://github.com/broomva/workspace)`/research/entities/pattern/role-x.md`
- **Reflexive trigger rule:** [`broomva/workspace`](https://github.com/broomva/workspace)`/AGENTS.md` §P17
- **bstack engine ledger:** [`broomva/workspace`](https://github.com/broomva/workspace)`/research/entities/pattern/bstack-engine.md` (P17 in Promoted Patterns)
- **Seed meta-role source:** [`broomva/autonomous`](https://github.com/broomva/autonomous) — `/autonomous` skill embeds the universal role contract
