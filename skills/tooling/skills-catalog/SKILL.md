---
name: skills-catalog
category: tooling
description: >
  Canonical reference inventory of the 75 agent skills in the broomva/skills monorepo,
  organized into 22 single-noun category buckets that mirror the skills/<category>/ directory
  layout, with a Remotion video showcase generator and X thread copy. Use when discovering
  available skills, browsing the full skills catalog, generating skills showcase content, or
  understanding what capabilities are available across governance, orchestration, tooling,
  knowledge, research, strategy, cadence, publishing, video, audio, design, finance, compute,
  models, messaging, robotics, aerospace, neuroscience, healthcare, science, commerce, and
  everyday utilities. Triggers on "skills inventory", "list all skills", "what skills are
  available", "skills catalog", "skills showcase", "skills video", "showcase skills", "skills
  reference", or any request to browse, search, or visualize the skills monorepo.
---

# Skills

Canonical inventory and showcase for the agent skills ecosystem.

## Inventory

The full categorized reference lives in [references/skills-inventory.md](references/skills-inventory.md).

75 skills across 22 category buckets (mirroring the `skills/<category>/` directory layout):

| Category | Count | Key skills |
|---|---|---|
| Governance & control (`governance`) | 6 | agentic-control-kernel, architecture-design-principles, bstack |
| Orchestration & autonomy (`orchestration`) | 7 | autonomous, eve-forge, governed-autonomy-loop |
| Skill & prompt tooling (`tooling`) | 5 | broomva-cli, make-spec, prompt-library |
| Knowledge & memory (`knowledge`) | 4 | bookkeeping, braindump, colombia-conflict |
| Research (`research`) | 2 | checkit, deep-dive-research-orchestrator |
| Strategy & decisions (`strategy`) | 5 | decision-log, phronesis, pre-mortem |
| Operating cadence (`cadence`) | 4 | drift-check, morning-briefing, stakeholder-update |
| Publishing & growth (`publishing`) | 5 | blog-post, content-creation, revenuecast |
| Video & multimedia (`video`) | 6 | brainrot-for-good, content-engine, creative-review |
| Audio & music (`audio`) | 2 | livecoding, omnivoice |
| Design & brand (`design`) | 4 | arcan-glass, brand-icons, design-engineering |
| Finance & payments (`finance`) | 4 | finance-substrate, haima, investment-management |
| Compute infrastructure (`compute`) | 3 | agentic-vps, colab-remote, remote-gpu |
| Model runtimes (`models`) | 2 | bitnet, heretic-abliteration |
| Messaging channels (`messaging`) | 2 | claude-code-channels, claude-remote-sessions |
| Robotics (`robotics`) | 2 | capx-agentic-robotics, orcahand |
| Aerospace & RF (`aerospace`) | 2 | openrocket-sim, sdr-satellite |
| Neuroscience & BCI (`neuroscience`) | 3 | tribe-v2-agent-alignment, tribe-v2-bci-applied, tribe-v2-neuroscience |
| Healthcare (`healthcare`) | 2 | founder-mode-oncology, health |
| Science (`science`) | 1 | ocean-genomics |
| Commerce & procurement (`commerce`) | 2 | procurer, swapit |
| Everyday utilities (`utilities`) | 2 | gasgo, alkosto-wait-optimizer |

Read the full inventory with descriptions: `Read references/skills-inventory.md`

## Showcase Video

A Remotion project that renders the inventory as an animated video (1080x1080, 30fps, 48s)
plus a 7-post X thread lives at the **monorepo root** in `skills-showcase/` (a repo-level dev
tool, not part of this skill's install — `--skill skills-catalog` ships only `SKILL.md` +
`references/skills-inventory.md`). From a clone of `broomva/skills`:

> **Note:** the video dataset (`skills-showcase/src/data/skills.ts`) still reflects the legacy
> "broader-ecosystem" catalog (86 rows, 15 marketing domains). The canonical inventory above
> has been converged to the 22 monorepo buckets (BRO-1932); re-syncing `skills.ts` + the
> Remotion scene grouping + re-rendering the video is tracked as a separate follow-up.

```bash
cd skills-showcase          # at the repo root, not inside the skill
npm install
npx remotion render SkillsShowcase out/skills-showcase.mp4
npx remotion render SkillsShowcase out/skills-showcase.gif --every-nth-frame=3
```

Pre-rendered outputs land in the repo-root `skills-showcase/out/`.

## Adding Skills

Edit this skill's `references/skills-inventory.md` for the catalog, and (for the video dataset)
the repo-root `skills-showcase/src/data/skills.ts`. Re-render after changes.
