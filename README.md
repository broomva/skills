# Skills

A curated collection of agent skills and the canonical reference inventory.

## What's Here

| Path | Description |
|---|---|
| `references/skills-inventory.md` | Full categorized inventory of 83 skills across 15 domains |
| `skills-showcase/` | Remotion video + X thread skill for rendering the showcase |

## Usage

### Browse the inventory

The inventory lives in [`references/skills-inventory.md`](references/skills-inventory.md) — a single-file reference of every skill, grouped by category with descriptions and metadata.

### Install a skill

```bash
npx skills add broomva/skills@skills-showcase
```

### Find more skills

```bash
npx skills find <query>
```

Browse the ecosystem at [skills.sh](https://skills.sh/).

## Creating Skills

```bash
npx skills init my-skill
```

See the [skill-creator](https://skills.sh/) conventions for structure and packaging.
