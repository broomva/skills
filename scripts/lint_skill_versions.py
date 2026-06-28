#!/usr/bin/env python3
"""Per-skill SemVer consistency linter for the broomva/skills monorepo.

A skill is "versioned" (a release candidate) iff its `SKILL.md` frontmatter
declares a `version` (top-level, or `metadata.version` per the agentskills.io
spec). Unversioned skills are pre-release and exempt — we do NOT force a version
on prototypes.

For every VERSIONED skill, enforce:
  1. the version is valid SemVer (MAJOR.MINOR.PATCH[-pre][+build]);
  2. any `pyproject.toml` `[project].version` matches it;
  3. any `package.json` `version` matches it;
  4. a `CHANGELOG.md` exists with a `## [<version>]` section.

This keys on the SKILL.md version deliberately: a `package.json`/`pyproject`
that carries a version for build tooling (e.g. a `private` JS helper) does NOT
make the skill a release — only the skill manifest does.

Exit non-zero (with a per-skill report) if any versioned skill is inconsistent.
Pure stdlib + PyYAML; no network.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

import yaml

# SemVer 2.0.0 (https://semver.org) — numeric core + optional pre-release/build.
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"


def _frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _skill_version(fm: dict) -> str | None:
    """Canonical skill version: top-level `version`, else `metadata.version`."""
    if "version" in fm and fm["version"] is not None:
        return str(fm["version"])
    meta = fm.get("metadata")
    if isinstance(meta, dict) and meta.get("version") is not None:
        return str(meta["version"])
    return None


def _pyproject_version(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    v = data.get("project", {}).get("version")
    return str(v) if v is not None else None


def _package_json_version(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    v = data.get("version")
    return str(v) if v is not None else None


def _changelog_has_version(path: Path, version: str) -> bool:
    if not path.exists():
        return False
    return f"## [{version}]" in path.read_text(encoding="utf-8")


def lint_skill(skill_dir: Path) -> list[str]:
    """Return a list of error strings for one skill (empty == OK / exempt)."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return []
    name = skill_dir.name
    fm = _frontmatter(skill_md)
    version = _skill_version(fm)
    if version is None:
        return []  # unversioned → pre-release → exempt

    errors: list[str] = []
    if not _SEMVER.match(version):
        errors.append(f"SKILL.md version {version!r} is not valid SemVer (MAJOR.MINOR.PATCH)")

    py = _pyproject_version(skill_dir / "pyproject.toml")
    if py is not None and py != version:
        errors.append(f"pyproject version {py!r} != SKILL.md version {version!r}")

    js = _package_json_version(skill_dir / "package.json")
    if js is not None and js != version:
        errors.append(f"package.json version {js!r} != SKILL.md version {version!r}")

    if not _changelog_has_version(skill_dir / "CHANGELOG.md", version):
        errors.append(
            f"CHANGELOG.md missing a '## [{version}]' section "
            "(a versioned skill must document its release)"
        )
    return [f"{name}: {e}" for e in errors]


def _iter_skill_dirs() -> list[Path]:
    """Every directory under skills/ that holds a SKILL.md, at any depth.

    Mirrors the md-linter's nested traversal (skills/<name>/ and
    skills/<name>/skills/<sub>/) and is forward-compatible with category
    buckets (skills/<category>/<name>/). The `extensions/` carve-out is
    excluded to match lint-skill-md.yml, which does not lint private
    extensions. Keying on rglob("SKILL.md") rather than top-level iterdir()
    closes the gap where nested versioned sub-skills (and, post-bucketing,
    EVERY skill) escaped the SemVer + CHANGELOG check.
    """
    dirs: list[Path] = []
    for skill_md in sorted(_SKILLS_DIR.rglob("SKILL.md")):
        rel = skill_md.relative_to(_SKILLS_DIR)
        if "extensions" in rel.parts:
            continue
        dirs.append(skill_md.parent)
    return dirs


def main() -> int:
    if not _SKILLS_DIR.is_dir():
        print(f"no skills/ dir at {_SKILLS_DIR}", file=sys.stderr)
        return 2

    all_errors: list[str] = []
    versioned = 0
    for skill_dir in _iter_skill_dirs():
        skill_md = skill_dir / "SKILL.md"
        if _skill_version(_frontmatter(skill_md)) is not None:
            versioned += 1
        all_errors.extend(lint_skill(skill_dir))

    if all_errors:
        print(f"✗ skill-version lint FAILED ({len(all_errors)} issue(s)):\n", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        print(
            "\nFix: align the version across SKILL.md / pyproject / package.json, "
            "use SemVer, and add a matching CHANGELOG section. See CONTRIBUTING.md "
            "(Versioning & Releasing).",
            file=sys.stderr,
        )
        return 1

    print(f"✓ skill-version lint passed ({versioned} versioned skill(s) consistent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
