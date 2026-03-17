# Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![skills.sh](https://img.shields.io/badge/skills.sh-directory-8B5CF6)](https://skills.sh/)

A curated collection of agent skills and the canonical reference inventory — **83 skills across 15 domains**.

## Quick Install

```bash
npx skills add broomva/skills@skills-showcase
```

## What's Here

| Path | Description |
|---|---|
| [`references/skills-inventory.md`](references/skills-inventory.md) | Full categorized inventory of 83 skills across 15 domains |
| [`skills-showcase/`](skills-showcase/) | Remotion video + X thread skill for rendering the showcase |

## Skills Inventory

The inventory covers every layer of the stack:

| Category | Count |
|---|---|
| AI & Agent Systems | 6 |
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

## Skills Showcase

The [`skills-showcase`](skills-showcase/) skill generates a polished Remotion video (1080x1080, 30fps, 48s) and a 7-post X thread from the inventory data.

```bash
cd skills-showcase
npm install
npx remotion studio                    # Preview in browser
npx remotion render SkillsShowcase out/skills-showcase.mp4
npx remotion render SkillsShowcase out/skills-showcase.gif --every-nth-frame=3
```

Pre-rendered outputs are in [`skills-showcase/out/`](skills-showcase/out/).

## Browse & Discover

```bash
npx skills find <query>
```

Browse the full ecosystem at [skills.sh](https://skills.sh/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add skills, update the inventory, or re-render the showcase.

## License

[MIT](LICENSE)
