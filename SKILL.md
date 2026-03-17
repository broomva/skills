---
name: skills
description: >
  Canonical reference inventory of 83 agent skills across 15 domains, with a Remotion video
  showcase generator and X thread copy. Use when discovering available skills, browsing the
  full skills catalog, generating skills showcase content, or understanding what capabilities
  are available across AI agents, memory, research, observability, deployment, Next.js, React
  Native, design systems, MCP, databases, QA, CLI tooling, and platform specialties. Triggers
  on "skills inventory", "list all skills", "what skills are available", "skills catalog",
  "skills showcase", "skills video", "showcase skills", "skills reference", or any request to
  browse, search, or visualize the full agent skills ecosystem.
---

# Skills

Canonical inventory and showcase for the agent skills ecosystem.

## Inventory

The full categorized reference lives in [references/skills-inventory.md](references/skills-inventory.md).

83 skills across 15 domains:

| Domain | Count | Key Skills |
|---|---|---|
| AI & Agent Systems | 6 | ai-sdk, claude-api, agentic-control-kernel, autoany |
| Memory & Knowledge | 5 | agent-consciousness, knowledge-graph-memory, obsidian-cli |
| Research & Intelligence | 5 | deep-research, financial-deep-research, competitor-intel |
| Observability & Debugging | 5 | sentry-fix-issues, langsmith-trace |
| Deployment & Infrastructure | 6 | use-railway, vercel-cli, symphony |
| Next.js & React | 8 | next-best-practices, next-cache-components, next-forge |
| Mobile & Expo | 7 | building-ui, vercel-react-native-skills, use-dom |
| Design & UI Systems | 6 | building-components, frontend-design, liquid-glass-design |
| JSON-Render Ecosystem | 5 | json-render-core, json-render-react, json-render-remotion |
| MCP & Protocol Integration | 4 | building-mcp-servers, mcp-builder, ucp |
| Database & API | 4 | using-neon, workflow, api-documentation |
| QA & Browser Testing | 5 | dogfood, gstack, agent-browser |
| CLI & Workflow Tooling | 6 | domain-cli, turborepo, autoship, linear-cli |
| Design Tooling | 3 | remotion-best-practices, ai-elements |
| Platform Specialties | 8 | rust-best-practices, local-llm-ops, garmin-connect |

Read the full inventory with descriptions: `Read references/skills-inventory.md`

## Showcase Video

The [skills-showcase/](skills-showcase/) subdirectory contains a Remotion project that renders
the inventory as an animated video (1080x1080, 30fps, 48s) plus a 7-post X thread.

```bash
cd skills-showcase
npm install
npx remotion render SkillsShowcase out/skills-showcase.mp4
npx remotion render SkillsShowcase out/skills-showcase.gif --every-nth-frame=3
```

Pre-rendered outputs in `skills-showcase/out/`.

## Adding Skills

Edit `references/skills-inventory.md` for the catalog and `skills-showcase/src/data/skills.ts`
for the video dataset. Re-render after changes.
