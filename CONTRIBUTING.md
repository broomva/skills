# Contributing

Thanks for your interest in contributing to this skills collection.

## Adding a New Skill

1. Create a folder at the root named after your skill (kebab-case)
2. Add a `SKILL.md` with YAML frontmatter (`name` and `description` are required)
3. Add source files, references, or assets as needed
4. Update `references/skills-inventory.md` with the new skill entry
5. Open a PR

### SKILL.md Requirements

```yaml
---
name: my-skill
description: >
  What the skill does and when to trigger it.
  Include specific trigger phrases.
---
```

The body should contain concise instructions — see the [skill-creator](https://skills.sh/) conventions.

## Updating the Inventory

If you're adding a skill that exists elsewhere (not in this repo), you can still add it to `references/skills-inventory.md` as a catalog entry.

## Updating the Showcase Video

```bash
cd skills-showcase
npm install
# Edit src/data/skills.ts with new entries
npx remotion studio          # Preview
npx remotion render SkillsShowcase out/skills-showcase.mp4
npx remotion render SkillsShowcase out/skills-showcase.gif --every-nth-frame=3
```

## Code of Conduct

Be respectful and constructive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
