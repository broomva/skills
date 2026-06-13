# Contributing

Thanks for your interest in contributing.

This repository has two contribution flows depending on what you're adding:

- **Catalog updates** — adding an inventory entry pointing at an externally-hosted skill, or updating the showcase video
- **Tier-2 skill graduation** — vendoring a skill into the monorepo at `skills/<name>/`

## Tier-2 skill graduation flow

> Use this for skills that meet the [Broomva packaging strategy](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-25-skills-packaging-strategy.html) Tier-2 criteria: rule-of-three proven (P16), no independent release cadence justification needed, fits within the monorepo's release rhythm.

1. **Choose the skill name** — kebab-case, lowercase, ≤64 chars, no leading/trailing/consecutive hyphens. Must equal the parent directory name.

2. **Create the layout:**

```
skills/<name>/
├── SKILL.md           # required — the skill itself
├── README.md          # optional — human-readable overview
├── CHANGELOG.md       # optional — Keep-a-Changelog format
├── scripts/           # optional — CLI tooling (Python/TS/Bash)
├── references/        # optional — templates, schemas, theme.css, fixtures
├── assets/            # optional — binary artifacts, images
└── tests/             # optional — smoke + integration
```

3. **SKILL.md frontmatter** (per [agentskills.io](https://agentskills.io/specification) + Broomva extensions):

```yaml
---
# Required (agentskills.io spec)
name: <name>                        # must match parent dir
description: |                      # multi-line trigger keywords + when-to-use + carve-outs
  What the skill does, when to invoke, when NOT to invoke.
  Triggers on "...", "...", "...".

# Optional (agentskills.io spec)
license: MIT
metadata:
  version: "1.0.0"                  # semver string
  homepage: "https://broomva.tech/skills/<name>"

# Broomva extensions
primitive: null                     # P-number if applicable; else null
category: <one of: meta | lifecycle | knowledge | orchestration | safety | design | content | strategy | platform | domain>
required: false                     # true = bstack-substrate-mandatory
introduced_in: "0.X.0"              # bstack VERSION when first registered
---
```

4. **Install + use:**

```bash
npx skills add broomva/skills --skill <name>
```

5. **Open a PR.** Include in the PR description:
   - Which Broomva Tier-2 criterion the skill meets (rule-of-three evidence)
   - Whether it's a workspace-graduated prototype (Tier 3 → Tier 2) or a fresh skill
   - If graduated: link to the workspace's [bstack-engine candidate ledger](https://github.com/broomva/workspace/blob/main/research/entities/pattern/bstack-engine.md) entry

### Shared utilities

If multiple Tier-2 skills share utility code, place it under `_shared/<category>/` (e.g. `_shared/strategy/`, `_shared/tribe-v2/`). Reference from individual skill SKILL.md bodies.

## Versioning & Releasing

Skills are versioned **independently** with [SemVer](https://semver.org/): MAJOR
for breaking CLI/schema changes, MINOR for new commands/metrics, PATCH for fixes.
Pre-1.0 skills may carry breaking changes in MINOR bumps.

**A skill is "versioned" iff its `SKILL.md` frontmatter declares a `version`.**
Versioned skills are enforced by CI — `scripts/lint_skill_versions.py` (the
`lint-skill-versions` workflow) requires:

- the version is valid SemVer;
- it agrees across `SKILL.md`, `pyproject.toml`, and `package.json` (whichever exist);
- a `CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com/)) carries a
  matching `## [version]` section.

Unversioned (prototype / pre-release) skills are **exempt** — don't declare a
version until the skill is ready to be released.

Packaged skills that are publishable (a `pyproject.toml`, or a `package.json`
without `"private": true`) should also ship a `LICENSE`. `SKILL.md`-only skills
rely on the repository-root [`LICENSE`](LICENSE).

### Cutting a release

1. Bump the version everywhere it appears (`SKILL.md`; plus `pyproject.toml` /
   `package.json` / `__init__.py` if present) and add a dated `CHANGELOG.md` section.
2. Open a PR; merge once CI is green. Merging to `main` is what `npx skills add`
   publishes — skills.sh serves the default branch.
3. Tag + publish the GitHub release:

   ```bash
   scripts/release-skill.sh <skill> <version>   # e.g. health 0.9.1
   ```

   It validates consistency + the CHANGELOG, then pushes the annotated tag
   `<skill>-vX.Y.Z`, which triggers the `release-skill` workflow to build
   (Python skills) and publish the GitHub release from the CHANGELOG section.

## Catalog update flow

> Use this for adding an inventory entry that points at an externally-hosted skill (e.g. `broomva/p9`, `broomva/role-x`, third-party skill repos).

1. Edit [`references/skills-inventory.md`](references/skills-inventory.md) to add the new entry with name, repo URL, category, and one-line description.
2. (Optional) Update the showcase video — see "Updating the showcase video" below.
3. Open a PR.

The catalog entry does NOT require copying the skill source into this repo; the inventory is a discovery surface, the source lives wherever it's hosted (Tier-1 per-skill repo or another monorepo).

## Root-level SKILL.md

The repository's root `SKILL.md` IS the catalog skill itself — what users get when they run `npx skills add broomva/skills`. It instructs the agent how to browse `references/skills-inventory.md` and surface relevant skills.

Don't add new skill subdirectories at the root level — those are reserved for catalog tooling (`skills-showcase/`, future `_shared/`, etc.). All new agent-skill content goes under `skills/<name>/`.

## Updating the showcase video

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
