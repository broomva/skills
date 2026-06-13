#!/usr/bin/env bash
# release-skill.sh <skill> <version> — cut a per-skill release in the monorepo.
#
# Validates SemVer + cross-source version consistency + a matching CHANGELOG
# section, then creates and pushes the annotated tag `<skill>-v<version>` —
# which triggers .github/workflows/release-skill.yml to publish the GitHub
# release (and build/attach the sdist+wheel for Python skills).
#
# Pre-req: bump the version in SKILL.md (+ pyproject.toml / package.json if the
# skill has them) and add the CHANGELOG section BEFORE running this. Requires a
# clean working tree and PyYAML (`pip install pyyaml`).
#
# Usage: scripts/release-skill.sh health 0.9.1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL="${1:-}"
VERSION="${2:-}"

if [ -z "$SKILL" ] || [ -z "$VERSION" ]; then
  echo "usage: scripts/release-skill.sh <skill> <version>   (e.g. health 0.9.1)" >&2
  exit 2
fi

DIR="$ROOT/skills/$SKILL"
[ -f "$DIR/SKILL.md" ] || { echo "error: no skill at skills/$SKILL" >&2; exit 1; }

# SemVer (MAJOR.MINOR.PATCH[-pre][+build])
if ! printf '%s' "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$'; then
  echo "error: version '$VERSION' is not SemVer (MAJOR.MINOR.PATCH)" >&2
  exit 1
fi

# Clean tree (the tag must mark a committed state).
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
  echo "error: working tree not clean — commit or stash first" >&2
  exit 1
fi

# Whole-repo version-consistency lint (fast).
python3 "$ROOT/scripts/lint_skill_versions.py"

# SKILL.md version must equal the requested version.
DECLARED="$(python3 - "$DIR/SKILL.md" <<'PY'
import sys, yaml
text = open(sys.argv[1], encoding="utf-8").read()
fm = yaml.safe_load(text[3:text.find("\n---", 3)]) or {}
print(fm.get("version") or (fm.get("metadata") or {}).get("version") or "")
PY
)"
if [ "$DECLARED" != "$VERSION" ]; then
  echo "error: skills/$SKILL/SKILL.md version '$DECLARED' != requested '$VERSION'" >&2
  echo "       bump SKILL.md (+ pyproject/package.json) + CHANGELOG, commit, then retry." >&2
  exit 1
fi

# CHANGELOG section must exist.
if ! grep -qE "^## \[$VERSION\]" "$DIR/CHANGELOG.md" 2>/dev/null; then
  echo "error: skills/$SKILL/CHANGELOG.md missing a '## [$VERSION]' section" >&2
  exit 1
fi

TAG="$SKILL-v$VERSION"
if git -C "$ROOT" rev-parse "$TAG" >/dev/null 2>&1; then
  echo "error: tag $TAG already exists" >&2
  exit 1
fi

git -C "$ROOT" tag -a "$TAG" -m "$SKILL v$VERSION"
git -C "$ROOT" push origin "$TAG"
echo "✓ pushed $TAG — the release-skill workflow will publish the GitHub release."
