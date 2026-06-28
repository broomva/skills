# bstack inheritance — what this skill borrows, what it owns

`broomva/dogfood` is a **downstream skill** of [`broomva/bstack`](https://github.com/broomva/bstack). It implements one specific primitive's reflexes (P11 Empirical Feedback Loop, rules 7 + 6) as an explicit slash command — where `/autonomous` fires them implicitly inside its full 21-reflex pipeline.

This document declares the inheritance contract precisely so future agents (and future humans) understand what's borrowed vs what's local, and so version drift doesn't silently break composition.

## Inherited from bstack (canonical sources upstream)

| Concept | Lives in (bstack repo) | What dogfood does with it |
|---|---|---|
| **P11 Empirical Feedback Loop primitive contract** | `bstack/references/primitives.md` §P11 (lines 198–235) | This skill *implements* reflex 7 (Dogfood Plan) and reflex 6 (Dogfood Receipt) — they're the discipline, this skill is the operational handle |
| **Per-stack cookbook** | `bstack/references/dogfood-patterns.md` | Loaded on demand at runtime; not duplicated in this repo. If bstack isn't installed, a minimum surfaces table is inlined in `SKILL.md` Phase 2 fallback |
| **Stack-detection algorithm** | `bstack/scripts/doctor.sh` §13 | Mirrored in `scripts/dogfood.sh detect`. Detection signals: `Cargo.toml + src-tauri/` → tauri-sidecar; `next.config.*` → nextjs; `app.json + expo` → expo-rn; `Cargo.toml` solo → rust-cli; `openapi.*` or REST framework deps → rest-api; `mcp.{json,yaml}` → mcp-server |
| **Dogfood Plan schema** | `bstack/references/dogfood-patterns.md` §"The Dogfood Plan contract (binding)" | Six rows: entry surface · driver · evidence · smoke · end-to-end · receipt anchor. This skill produces exactly this shape |
| **Dogfood Receipt schema** | `bstack/references/dogfood-patterns.md` §"Receipt template" | Evidence table + anti-rationalization line. This skill produces exactly this shape |
| **Promotion gating ledger** | `bstack/research/entities/pattern/bstack-engine.md` (when mirrored) | Candidate-status promotion attempts logged upstream |

## Owned by dogfood (local to this repo)

| Concept | Lives in (this repo) | Why local |
|---|---|---|
| **Explicit slash command trigger** | `SKILL.md` (the `name:`, `argument-hint:`, `USE WHEN` description) | The "explicit trigger" is what this skill *adds* — bstack defines the discipline, dogfood gives it a `/dogfood` handle |
| **Subcommand variants** (`plan` / `execute` / `receipt`) | `SKILL.md` workflow phases | Bstack defines the artifacts; this skill defines the subcommand UX |
| **CLI wrapper** | `scripts/dogfood.sh` | Standalone (no Claude session required); mirrors bstack's detection but stays installable on its own |
| **Composition table with other skills** | `SKILL.md` "Composition" section, README "Composition" table | This skill's relationship to `/autonomous`, `/p9`, `Interceptor`, `cross-review` — local to dogfood because the *trigger UX* is what composes |
| **Minimum-surfaces fallback table** | `SKILL.md` Phase 2 fallback | Lets dogfood work standalone if bstack isn't installed; covers ~80% of cases without the deep cookbook |

## Version compatibility

| dogfood | Requires bstack ≥ | Notes |
|---|---|---|
| 0.1.0 | 0.13.0 (or no bstack — fallback works) | bstack 0.13.0 ships the cookbook + §13 + onboard stub |
| 0.2.0 (planned) | 0.13.0 | Will add receipt scoring into bookkeeping (P6) — requires bstack 0.14.0 when that lands |

## How the inheritance is enforced (concrete checks)

1. **At install**: `npx skills add broomva/dogfood` doesn't auto-install bstack. The skill notes in its `install.md` and README that bstack is recommended but not required.
2. **At load**: `SKILL.md` Phase 2 attempts `npx skills path broomva/bstack` to locate the cookbook. If the path doesn't resolve or `references/dogfood-patterns.md` is missing, the skill falls back to the inlined minimum surfaces table and emits a one-line warning.
3. **At PR review**: the upstream bstack `doctor §13` check verifies a Dogfood Plan anchor exists in the repo (AGENTS.md, docs/dogfood-plan.md, or PR body). If you have both skills installed, `bstack doctor` reports `/dogfood`-produced plans correctly.

## Upstream attribution — pre-existing `dogfood` skill (v0.2.0+)

`broomva/dogfood` v0.2.0 introduced an `explore` subcommand that, for web stacks, composes with the pre-existing `dogfood` skill from the Claude Code agent-skills catalog (`~/.agents/skills/dogfood/`). That skill is a 6-phase web-app exploratory QA workflow built around `agent-browser`.

**What was adapted (with attribution)**:

| File in this repo | Adapted from |
|---|---|
| `references/exploratory-issue-taxonomy.md` | `~/.agents/skills/dogfood/references/issue-taxonomy.md` — severity levels + 7 issue categories + exploration checklist (structure reused, prose paraphrased, attribution explicit) |
| `templates/exploratory-report.md` | `~/.agents/skills/dogfood/templates/dogfood-report-template.md` — issue-by-issue report shape (header + summary + ISSUE-XXX blocks). Adds the bstack-specific anti-rationalization-receipt section. |
| `scripts/dogfood.sh explore` (web stacks) | The 6-phase workflow (initialize → authenticate → orient → explore → document → wrap up) from `~/.agents/skills/dogfood/SKILL.md`. The recipe-emit shape (not auto-execute) is the bstack-composed variant — the agent / user runs the emitted commands. |

**Why compose rather than runtime-link**:

- The pre-existing skill is web-only. broomva/dogfood is multi-stack (Tauri+sidecar, Next.js, Expo RN, Rust CLI, REST API, MCP server).
- The pre-existing skill is a *workflow*, not a *contract*. broomva/dogfood's Plan + Receipt + anti-rationalization-line are the P11 contract that surrounds any execution.
- A single `npx skills add broomva/dogfood` install is enough for both the contract AND the web-exploratory driver. Users don't need to install both repos.

**What stays in the pre-existing skill, not adopted here**:

- Direct `agent-browser` command execution at install time (we emit recipes, not auto-run them).
- Standalone web-only invocation (`dogfood vercel.com` without a parent Plan) — the pre-existing global skill still serves that use case.
- Future enhancements to the workflow that don't compose with bstack P11.

If you want pure web-app exploratory QA without the bstack contract, install the pre-existing skill globally and use it directly: it lives at `~/.agents/skills/dogfood/` after install from the agent-skills catalog.

## What this skill does NOT borrow from bstack

- **Bstack's other primitives** (P1–P10, P12–P20). Dogfood only operationalizes P11. The other primitives are bstack's territory.
- **Bstack doctor's overall check pipeline** — dogfood doesn't gate, lint, or audit. It produces artifacts.
- **Bstack's onboarding wizard** (`bstack onboard.sh`). Dogfood is a runtime skill; bstack's onboard handles initialization.

## Drift detection

If bstack changes its Dogfood Plan or Receipt schema (the six-row plan, the receipt table shape), dogfood must update in lockstep. The drift signal is:

- bstack VERSION bumps + `references/dogfood-patterns.md` diff that touches the schema sections (`The Dogfood Plan contract (binding)` or `Receipt template`)

When that happens, this skill bumps to a matching minor version and updates `SKILL.md` Phase 2 fallback table.

## Why this skill exists separately from bstack

Three reasons:

1. **Installability**: `npx skills add broomva/dogfood` is shorter than telling someone "install bstack and then use the P11 reflex 7 + 16". Skills with discrete UX deserve their own install handle.
2. **Composition surface**: `/dogfood` is a *trigger* — `/autonomous` calls into it; users invoke it directly. Bstack is a *substrate* — primitives, doctor, governance. Substrate-vs-trigger separation is the same shape as bstack-vs-autonomous.
3. **Fallback path**: dogfood works without bstack (with reduced cookbook depth). Forcing bstack as a hard dep would limit adoption.

## Cross-references

- **bstack repo**: https://github.com/broomva/bstack
- **bstack v0.13.0 release** (cookbook + §13 ship): https://github.com/broomva/bstack/releases/tag/v0.13.0 (TBD on tag-creation by the bstack maintainer)
- **bstack P11 PR**: https://github.com/broomva/bstack/pull/43 (merged 2026-05-22)
