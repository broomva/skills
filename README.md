# Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![skills.sh](https://img.shields.io/badge/skills.sh-directory-8B5CF6)](https://skills.sh/)

A curated collection of agent skills — the canonical reference inventory **plus** the Broomva monorepo for Tier-2 skills.

This repository serves two purposes:

1. **Catalog** (root `SKILL.md`) — the discovery surface for **84+ skills across 15 domains**, with a Remotion video showcase.
2. **Monorepo** (`skills/<name>/`) — the home for Tier-2 vendored skills per the [Broomva packaging strategy](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-25-skills-packaging-strategy.html). Each skill is independently installable via `--skill <name>`.

## Quick install

```bash
# Catalog (root SKILL.md — skill discovery + inventory browsing)
npx skills add broomva/skills

# Tier-2 skill from the monorepo
npx skills add broomva/skills --skill handoff
npx skills add broomva/skills --skill make-spec
```

## Repository layout

| Path | Purpose |
|---|---|
| [`SKILL.md`](SKILL.md) | The catalog skill itself — invoked when the agent needs to browse the inventory |
| [`references/skills-inventory.md`](references/skills-inventory.md) | Full categorized inventory of 84+ skills across 15 domains |
| [`skills-showcase/`](skills-showcase/) | Remotion video + X thread renderer for the inventory |
| [`skills/`](skills/) | **Monorepo** — Tier-2 vendored skills, one directory per skill |
| `_shared/` | (reserved) shared utilities used by multiple Tier-2 skills |

## Tier-2 skills (vendored in this monorepo)

### Workflow & lifecycle

| Skill | Path | What it does |
|---|---|---|
| [`handoff`](skills/handoff/) | `skills/handoff/SKILL.md` | Fresh-session handoff doc drafting — compress a substantive arc into a single resumable doc for the next agent context |
| [`make-spec`](skills/make-spec/) | `skills/make-spec/SKILL.md` | Native-HTML design-doc scaffolding (spec / plan / ADR / report / pr-explainer) using the canonical Broomva dark theme — implements P18 (Format-Follows-Audience) for Category-C artifacts |

### Strategy & decision intelligence

> Migrated 2026-05-25 from the bundled `broomva/strategy-skills` repo per the Tier-2 monorepo plan. Each sub-skill is now individually installable.

| Skill | Path | What it does |
|---|---|---|
| [`pre-mortem`](skills/pre-mortem/) | `skills/pre-mortem/SKILL.md` | Structured failure-mode analysis (4-category scoring, mitigation plan) before a project launches |
| [`premortem`](skills/premortem/) | `skills/premortem/SKILL.md` | Klein/Kahneman premortem with parallel sub-agent deep-dives + HTML report |
| [`braindump`](skills/braindump/) | `skills/braindump/SKILL.md` | Capture raw thoughts → Obsidian vault with auto-categorization and backlinks |
| [`morning-briefing`](skills/morning-briefing/) | `skills/morning-briefing/SKILL.md` | Generate a focused daily brief from vault priorities and action items |
| [`drift-check`](skills/drift-check/) | `skills/drift-check/SKILL.md` | Compare stated priorities vs actual effort (git log + vault) — strategy drift report |
| [`strategy-critique`](skills/strategy-critique/) | `skills/strategy-critique/SKILL.md` | Red-team critique of strategy documents with gaps, risks, and missing assumptions |
| [`stakeholder-update`](skills/stakeholder-update/) | `skills/stakeholder-update/SKILL.md` | Take one set of facts → generate 3 versions (technical, business, customer-facing) |
| [`decision-log`](skills/decision-log/) | `skills/decision-log/SKILL.md` | Structured decision capture with context, alternatives, rationale → vault links |
| [`weekly-review`](skills/weekly-review/) | `skills/weekly-review/SKILL.md` | Scan vault for weekly changes; surface what changed; flag what needs attention |

More Tier-2 graduations land here per the [migration plan](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-25-skills-packaging-strategy.html). See [CONTRIBUTING.md](CONTRIBUTING.md#tier-2-skill-graduation-flow) for the graduation flow.

## Catalog inventory

The inventory covers every layer of the stack:

| Category | Count |
|---|---|
| AI & Agent Systems | 7 |
| Memory & Knowledge | 5 |
| Research & Intelligence | 5 |
| Observability & Debugging | 5 |
| Deployment & Infrastructure | 6 |
| Next.js & React | 8 |
| Mobile & Expo | 7 |
| Design & UI Systems | 6 |
| JSON-Render Ecosystem | 5 |
| MCP & Protocol Integration | 4 |
| Database & API | 4 |
| QA & Browser Testing | 5 |
| CLI & Workflow Tooling | 6 |
| Design Tooling | 3 |
| Platform Specialties | 8 |

Full details with descriptions in [`references/skills-inventory.md`](references/skills-inventory.md).

## Skills showcase

The [`skills-showcase`](skills-showcase/) tool generates a polished Remotion video (1080x1080, 30fps, 48s) and a 7-post X thread from the inventory data.

```bash
cd skills-showcase
npm install
npx remotion studio                    # Preview in browser
npx remotion render SkillsShowcase out/skills-showcase.mp4
npx remotion render SkillsShowcase out/skills-showcase.gif --every-nth-frame=3
```

Pre-rendered outputs are in [`skills-showcase/out/`](skills-showcase/out/).

## Browse & discover

```bash
npx skills find <query>
```

Browse the full ecosystem at [skills.sh](https://skills.sh/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for both flows: the **root-level catalog** flow (adding inventory entries, updating the showcase) and the **Tier-2 monorepo graduation** flow (adding a skill at `skills/<name>/`).

## License

[MIT](LICENSE)
