"""Version single-source-of-truth guard.

The version is declared in three places — `pyproject.toml`, `__init__.py`, and
the `SKILL.md` frontmatter. They MUST agree: a release is tagged `health-vX.Y.Z`
against this number, so silent drift would mislabel a release or ship a skill
manifest that disagrees with its package. This test fails CI on divergence and
on a non-semver string.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import broomva_health

_SKILL_ROOT = Path(__file__).resolve().parents[2]  # skills/health/
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _pyproject_version() -> str:
    data = tomllib.loads((_SKILL_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _skill_md_version() -> str:
    text = (_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", text, re.MULTILINE)
    assert match, "SKILL.md frontmatter must declare `version: X.Y.Z`"
    return match.group(1)


def test_version_is_single_sourced() -> None:
    pyproject = _pyproject_version()
    dunder = broomva_health.__version__
    skill_md = _skill_md_version()
    assert pyproject == dunder == skill_md, (
        f"version drift — pyproject={pyproject!r} __init__={dunder!r} "
        f"SKILL.md={skill_md!r}; bump all three together (see README 'Releasing')."
    )


def test_version_is_semver() -> None:
    assert _SEMVER.fullmatch(broomva_health.__version__), (
        f"__version__ {broomva_health.__version__!r} is not MAJOR.MINOR.PATCH"
    )


def test_changelog_documents_current_version() -> None:
    """The CHANGELOG must carry a section for the current version (release gate)."""
    changelog = (_SKILL_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{broomva_health.__version__}]" in changelog, (
        f"CHANGELOG.md is missing a section for {broomva_health.__version__} — "
        "add it before bumping the version."
    )
