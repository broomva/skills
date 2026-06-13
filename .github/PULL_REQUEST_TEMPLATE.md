<!-- Thanks for contributing to broomva/skills. -->

## What & why

<!-- One or two sentences: what does this change and why. -->

## Type

- [ ] New skill (Tier-2 graduation — see CONTRIBUTING.md)
- [ ] Change to an existing skill
- [ ] Catalog / inventory update
- [ ] Repo infrastructure (CI, release, docs)

## Affected skill(s)

<!-- e.g. skills/health -->

## Checklist

- [ ] `SKILL.md` frontmatter valid (`name` + `description`); `name` matches the directory.
- [ ] If the skill **declares a version**: SemVer, consistent across `SKILL.md` /
      `pyproject.toml` / `package.json`, with a matching `CHANGELOG.md` section
      (`scripts/lint_skill_versions.py` passes).
- [ ] Version bumped per [SemVer](https://semver.org) if behavior changed
      (MAJOR breaking · MINOR additive · PATCH fix).
- [ ] Tests / lints pass locally for the affected skill.
- [ ] No secrets, credentials, or personal data in the diff.

## Release

<!-- If this should cut a release after merge, note the tag, e.g. `health-v0.9.1`.
     Release: `scripts/release-skill.sh <skill> <version>` (see CONTRIBUTING.md). -->
