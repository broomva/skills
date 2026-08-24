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
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

# SemVer 2.0.0 (https://semver.org) — numeric core + optional pre-release/build.
# `\d` is Unicode-aware and `$` matches before a trailing newline, so the
# previous `^...$` + `.match()` pair accepted "1.2.3\n" and the Arabic-Indic
# "1٢.0.0" as valid SemVer. ASCII classes + `fullmatch` at the call site.
_SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?",
    re.ASCII,
)

#: A ``## [x.y.z]`` heading inside a fenced block is an EXAMPLE, not a release.
#: CommonMark lets a fence be indented up to three spaces and lets it run to end
#: of document unclosed. Requiring a closing fence meant an UNCLOSED one matched
#: nothing, nothing was stripped, and the example heading inside it counted as a
#: release — so the strictest-looking half of this rule produced the false green.
_FENCE_RX = re.compile(
    r"^ {0,3}(?P<f>`{3,}|~{3,})[^\n]*$"          # opener, with an info string
    r".*?"
    r"(?:^ {0,3}(?P=f)[`~]*[ \t]*$|\Z)",         # closer: whitespace ONLY after it
    re.M | re.S)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"


def _read_bytes(path: Path) -> tuple[bytes | None, str | None]:
    """`(raw, reason_it_could_not_be_read)` for any file this linter opens.

    Every reader in this file previously had its OWN exception tuple, and each
    caught a DIFFERENT subset: the manifest reader caught UnicodeDecodeError but
    not OSError, the package readers caught OSError but not UnicodeDecodeError.
    So a permission-denied SKILL.md and a non-UTF-8 pyproject.toml both escaped
    as tracebacks while every "unreadable" test passed — the tests exercised
    malformed SYNTAX, never an unreadable FILE.

    One reader, one exception surface. A new caller inherits the coverage
    instead of re-deciding it.
    """
    try:
        return path.read_bytes(), None
    except FileNotFoundError:
        # A DANGLING SYMLINK is not an absence: something IS there, naming a
        # target that is not. `.exists()` follows the link and answers False,
        # so the four `.exists()` preflights this replaces let a broken symlink
        # exempt a skill from every rule below — absent-reads-as-consistent,
        # reintroduced one layer ABOVE the shared reader written to kill it.
        if path.is_symlink():
            return None, "is a broken symlink"
        return None, None
    except OSError as exc:
        # Includes an unreadable ANCESTOR directory (EACCES), which `.exists()`
        # also reports as a plain False.
        return None, f"could not be read ({type(exc).__name__})"


def _read_utf8(path: Path) -> tuple[str | None, str | None]:
    """`_read_bytes` plus decoding, so decode failures are reported alike."""
    raw, unreadable = _read_bytes(path)
    if unreadable:
        return None, unreadable
    if raw is None:
        return None, None  # absent — the caller decides whether that is a finding
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, f"is not valid UTF-8 ({exc.reason})"


class _NoDuplicateKeys(yaml.SafeLoader):
    """PyYAML keeps the LAST of duplicate keys and says nothing, so
    `version: not-semver` followed by `version: 1.2.3` erased the invalid
    declaration this lint exists to report — defeating the every-declaration
    check at the parser, below where that check can see."""


def _construct_unique(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError:
            # An unhashable key (a sequence or mapping used as one) is legal
            # YAML and never valid frontmatter. Raising TypeError out of a
            # constructor crashed the whole lint with a traceback — this file's
            # own defect class inverted, introduced by its own fix.
            raise yaml.YAMLError(f"unhashable key {key!r}") from None
        if duplicate:
            raise yaml.YAMLError(f"duplicate key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeys.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict:
    """`json.loads` has the same behaviour as PyYAML here."""
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def _read_frontmatter(skill_md: Path) -> tuple[dict, str | None, bool]:
    """`(frontmatter, reason_it_could_not_be_read)` — three states, not two.

    A skill is "versioned" iff its frontmatter declares a version, so returning a
    bare `{}` for a manifest we could not READ made it indistinguishable from a
    manifest with nothing to read: the skill reported as an unversioned
    pre-release and silently skipped SemVer validation, pyproject/package.json
    agreement, and the CHANGELOG requirement, while this lint stayed green.

    A UTF-8 BOM is the realistic trigger — invisible in most editors, and exactly
    what a Windows editor or a careless shell redirect produces. Measured with a
    live control: a well-formed manifest carrying `version: not-semver` reports
    two problems, while BOM / leading-blank-line / unparseable-YAML variants of
    the SAME invalid version reported none.
    """
    raw, unreadable = _read_bytes(skill_md)
    if unreadable:
        return {}, unreadable, True
    if raw is None:
        return {}, None, False  # no SKILL.md here at all
    if raw.startswith(b"\xef\xbb\xbf"):
        return {}, "starts with a UTF-8 BOM before the --- fence", True
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {}, f"is not valid UTF-8 ({exc.reason})", True
    # CRLF is a line ending, not a fence defect: splitting on "\n" alone left a
    # trailing "\r" on every line, so exact fence equality rejected every
    # well-formed CRLF manifest as having no frontmatter. Normalise the TEXT,
    # not just the split — the closing-fence offset indexes back into it, and
    # normalising only the lines shifted that slice by one byte per line,
    # silently truncating the last frontmatter value ("1.0.0" -> "1.0").
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    # EXACT fences at both ends. `first.strip()` accepted a whitespace-decorated
    # opener, and `find("\n---")` accepted `---yaml` as a CLOSING fence — the
    # same laxness the opening check had already been tightened against, left
    # in place at the other end.
    if not lines or lines[0] != "---":
        return {}, "does not start with a --- frontmatter fence", True
    closing = next((i for i, line in enumerate(lines[1:], 1) if line == "---"), None)
    if closing is None:
        return {}, "has no closing --- fence", True
    end = len("\n".join(lines[:closing]))
    try:
        data = yaml.load(text[3:end], Loader=_NoDuplicateKeys)
    except yaml.YAMLError as exc:
        return {}, f"has unparseable YAML frontmatter ({str(exc).splitlines()[0][:60]})", True
    if not isinstance(data, dict):
        return {}, "frontmatter is not a mapping", True
    return data, None, True


def _frontmatter(skill_md: Path) -> dict:
    return _read_frontmatter(skill_md)[0]


def _declared_versions(fm: dict) -> list[tuple[str, Any]]:
    """EVERY place this manifest declares a version, as `(where, value)`.

    `_skill_version` answers "which declaration wins", which is a different
    question from "what did the author declare". Checking only the winner meant
    a top-level `version: 1.2.3` beside `metadata.version: not-semver` reported
    nothing: the invalid declaration was real, present, and never examined.
    """
    found: list[tuple[str, Any]] = []
    if "version" in fm:
        found.append(("version", fm["version"]))
    meta = fm.get("metadata")
    if isinstance(meta, dict) and "version" in meta:
        found.append(("metadata.version", meta["version"]))
    return found



def _skill_version(fm: dict) -> str | None:
    """Canonical skill version: top-level `version`, else `metadata.version`."""
    if "version" in fm and fm["version"] is not None:
        return str(fm["version"])
    meta = fm.get("metadata")
    if isinstance(meta, dict) and meta.get("version") is not None:
        return str(meta["version"])
    return None


def _pyproject_version(path: Path) -> tuple[str | None, str | None]:
    """`(version, reason_it_could_not_be_read)`.

    Absent and unreadable are different answers. Collapsing them into `None`
    made a malformed pyproject.toml indistinguishable from no pyproject.toml at
    all, so the version-agreement rule silently stopped applying to exactly the
    file most likely to be wrong.
    """
    text, unreadable = _read_utf8(path)
    if unreadable:
        return None, f"pyproject.toml {unreadable}"
    if text is None:
        return None, None  # genuinely absent — pyproject.toml is optional
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return None, f"pyproject.toml is not valid TOML ({type(exc).__name__})"
    project = data.get("project")
    if not isinstance(project, dict):
        return None, None
    v = project.get("version")
    if "version" in project and v is None:
        return None, "pyproject.toml declares an empty [project].version"
    return (str(v) if v is not None else None), None


def _package_json_version(path: Path) -> tuple[str | None, str | None]:
    """`(version, reason_it_could_not_be_read)` — see `_pyproject_version`."""
    text, unreadable = _read_utf8(path)
    if unreadable:
        return None, f"package.json {unreadable}"
    if text is None:
        return None, None  # genuinely absent — package.json is optional
    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"package.json is not valid JSON ({type(exc).__name__})"
    if not isinstance(data, dict):
        return None, "package.json is not a JSON object"
    v = data.get("version")
    if "version" in data and v is None:
        return None, "package.json declares a null version"
    return (str(v) if v is not None else None), None


def _changelog_has_version(path: Path, version: str) -> tuple[bool, str | None]:
    """`(declares_the_version, reason_it_could_not_be_read)`.

    The FOURTH reader in this file, and the one that fails the other way: it
    called `read_text()` with no error handling, so a CHANGELOG that is not
    valid UTF-8 crashed the whole lint with a traceback instead of being
    reported. Same root defect as the other three — absent, present-and-
    readable, and unreadable collapsed into two states — with the opposite
    symptom, which is why looking for silent passes alone did not find it.
    """
    text, unreadable = _read_utf8(path)
    if unreadable:
        return False, f"CHANGELOG.md {unreadable}"
    if text is None:
        return False, None  # absent CHANGELOG -> the caller reports it missing
    # A LINE-ANCHORED heading, with fenced blocks stripped first. `"## [v]" in
    # text` was a substring search, so a CHANGELOG that merely SHOWED the
    # heading in a usage example satisfied the requirement to DECLARE it.
    body = _FENCE_RX.sub("", text)
    return (
        # Up to three leading spaces: CommonMark treats them as an ATX heading,
        # and rejecting them was a false RED on valid CHANGELOGs. Safe only
        # BECAUSE the fence pattern above also accepts an indented opener —
        # loosening one without the other would let an indented example count.
        # The version must END the bracket: `## [1.2.3]not-a-release` names a
        # different thing and was matching as a prefix.
        re.search(rf"^ {{0,3}}\#\#[^\S\n]+\[{re.escape(version)}\](?=[ \t]*$|[ \t])",
                  body, re.M) is not None,
        None,
    )


def lint_skill(skill_dir: Path) -> list[str]:
    """Return a list of error strings for one skill (empty == OK / exempt)."""
    skill_md = skill_dir / "SKILL.md"
    name = skill_dir.name
    fm, unreadable, present = _read_frontmatter(skill_md)
    if not present:
        return []
    if unreadable:
        # NOT an exemption. "I could not read the manifest" is a finding about
        # the manifest; treating it as "there is nothing to check" is how a
        # skill opts out of every rule below by carrying an invisible byte.
        return [f"{name}: SKILL.md {unreadable} — cannot determine whether it is versioned"]
    errors: list[str] = []
    # EVERY declaration is checked, before and independently of which one wins.
    # Validating only the winner let a failed declaration hide behind a working
    # one — first as a null, then as a second, invalid, NON-null value.
    declared = _declared_versions(fm)
    for where, value in declared:
        if value is None:
            errors.append(
                f"SKILL.md declares an empty {where} — remove the key or set one")
        elif not _SEMVER.fullmatch(str(value)):
            errors.append(
                f"SKILL.md {where} {str(value)!r} is not valid SemVer (MAJOR.MINOR.PATCH)")
    distinct = {str(v) for _w, v in declared if v is not None}
    if len(distinct) > 1:
        errors.append(
            f"SKILL.md declares conflicting versions {sorted(distinct)} — "
            "one manifest, one version")
    version = _skill_version(fm)
    if version is None:
        return [f"{name}: {e}" for e in errors]  # unversioned → pre-release → exempt

    py, py_unreadable = _pyproject_version(skill_dir / "pyproject.toml")
    if py_unreadable:
        errors.append(f"{py_unreadable} — cannot confirm it agrees with SKILL.md")
    if py is not None and py != version:
        errors.append(f"pyproject version {py!r} != SKILL.md version {version!r}")

    js, js_unreadable = _package_json_version(skill_dir / "package.json")
    if js_unreadable:
        errors.append(f"{js_unreadable} — cannot confirm it agrees with SKILL.md")
    if js is not None and js != version:
        errors.append(f"package.json version {js!r} != SKILL.md version {version!r}")

    declared, changelog_unreadable = _changelog_has_version(skill_dir / "CHANGELOG.md", version)
    if changelog_unreadable:
        errors.append(f"{changelog_unreadable} — cannot confirm it documents {version!r}")
    elif not declared:
        errors.append(
            f"CHANGELOG.md missing a '## [{version}]' section "
            "(a versioned skill must document its release)"
        )
    return [f"{name}: {e}" for e in errors]


def _iter_skill_dirs() -> tuple[list[Path], list[str]]:
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
    unwalkable: list[str] = []

    def _record(exc: OSError) -> None:
        """`os.walk` swallows a directory it cannot list and walks on. That is
        this file's defect class at the traversal layer: a subtree we could not
        ENUMERATE reported as a subtree with nothing in it, so a skill with an
        invalid version vanished and `main()` printed "0 versioned skill(s)
        consistent" and exited 0. Enumerating is a measurement; failing it is a
        finding, not a smaller tree."""
        where = getattr(exc, "filename", None) or _SKILLS_DIR
        try:
            where = Path(where).relative_to(_SKILLS_DIR)
        except ValueError:
            pass
        unwalkable.append(
            f"{where}: directory could not be listed ({type(exc).__name__}) — "
            "the skills under it were NOT checked")

    # `os.walk`, NOT `rglob`. On Python 3.11 `Path.rglob` filters candidates
    # through `Path.exists()`, which FOLLOWS symlinks, so a dangling SKILL.md is
    # never yielded and the skill is not merely exempt — it does not exist. The
    # same absent-reads-as-consistent defect, relocated from the reader to
    # DISCOVERY, where a unit test calling `lint_skill` directly cannot see it.
    # It is also version-dependent: 3.12 lists the dangling entry, 3.11 does not,
    # so the local suite passed while CI went green on nothing. `os.walk` reports
    # directory entries by name and behaves the same on both.
    for root, _subdirs, files in os.walk(_SKILLS_DIR, followlinks=False, onerror=_record):
        skill_dir = Path(root)
        rel = skill_dir.relative_to(_SKILLS_DIR)
        if "extensions" in rel.parts:
            continue
        if "SKILL.md" not in files:
            if "SKILL.md" in _subdirs:
                # `os.walk` sorts a directory — or a symlink to one — into
                # dirnames, so a SKILL.md of that shape was absent from `files`
                # and skipped in silence. Same sentence as the rest of this
                # file: something IS there and we could not read it.
                unwalkable.append(
                    f"{rel}/SKILL.md: is a directory, not a manifest — "
                    "the skill was NOT checked")
            continue
        dirs.append(skill_dir)
    return sorted(dirs), unwalkable


def main() -> int:
    if not _SKILLS_DIR.is_dir():
        print(f"no skills/ dir at {_SKILLS_DIR}", file=sys.stderr)
        return 2

    skill_dirs, unwalkable = _iter_skill_dirs()
    all_errors: list[str] = list(unwalkable)
    versioned = 0
    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        # No three-state guard here on purpose. An unreadable manifest yields
        # {} -> _skill_version None -> already uncounted, AND the count is only
        # printed on the success path, which an unreadable manifest can never
        # reach because it is itself a finding. A guard here is unobservable in
        # both directions; a mutation sweep proved it by leaving the "fix"
        # unkillable, which is what redundant code looks like from outside.
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
