#!/usr/bin/env python3
"""Validate every `skills/**/SKILL.md` against the agentskills.io spec.

Enforced per skill:
  1. YAML frontmatter delimited by EXACT `---` lines at both ends;
  2. required fields `name` and `description`;
  3. `name` is lowercase alphanumerics and single hyphens, <= 64 chars, with no
     leading, trailing or consecutive hyphens;
  4. `name` matches the parent directory name (spec section "Name").

Nested sub-skills (`skills/<x>/skills/<sub>/SKILL.md`) are checked identically.
`extensions/` is excluded: those are skill-private, not independently
installable.

This was a 66-line heredoc inside `.github/workflows/lint-skill-md.yml`, which
meant the gate running on every pull request had no tests and could not be run
locally. It had three FALSE GREENS, each measured against a control proving the
linter did catch an ordinary bad name:

  - `---yaml` was accepted as a closing fence (`text.find("\\n---", 3)`), so
    everything after it was ignored;
  - `errors="replace"` turned invalid UTF-8 into U+FFFD, so a mangled manifest
    "parsed";
  - an unlistable subtree was silently dropped. The `if not skill_mds` guard
    only fires when the WHOLE tree is empty, so in a real repository a hidden
    violation simply vanished.

Plus two crashes-instead-of-reports: a dangling symlink and an unreadable file
both exited on a traceback.

Pure stdlib + PyYAML. No network.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

#: ASCII deliberately: `\w`-style classes are Unicode-aware, and a name is a
#: directory name and a URL component, not prose.
#: Used with `fullmatch`, deliberately. `$` matches BEFORE a trailing newline, so
#: `NAME_RE.match("good\n")` was true — and a directory name can carry that
#: newline too, letting the parent-match check agree with it.
NAME_RE = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*", re.ASCII)
MAX_NAME = 64
FENCE = b"---"


class _NoDuplicateKeys(yaml.SafeLoader):
    """PyYAML keeps the LAST of duplicate keys and says nothing, so
    `name: BAD` followed by `name: good` validated as `good` — a valid
    declaration concealing an invalid one."""


def _construct_unique(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError:
            raise yaml.YAMLError(f"unhashable key {key!r}") from None
        if duplicate:
            raise yaml.YAMLError(f"duplicate key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeys.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique)


def _read_bytes(path: Path) -> tuple[bytes | None, str | None]:
    """`(raw, reason_it_could_not_be_read)`.

    `(None, None)` means genuinely ABSENT. Three states, not two: the inline
    version had none of them, so a dangling symlink and a permission-denied file
    both ended the run on a traceback rather than reporting the manifest.
    """
    try:
        return path.read_bytes(), None
    except FileNotFoundError:
        # A dangling symlink is not an absence: something IS there, naming a
        # target that is not.
        if path.is_symlink():
            return None, "is a broken symlink"
        return None, None
    except OSError as exc:
        return None, f"could not be read ({type(exc).__name__})"


def read_frontmatter(skill_md: Path) -> tuple[dict, str | None, bool]:
    """`(frontmatter, reason_it_could_not_be_read, it_exists)`.

    Fences are located in BYTES and only the frontmatter region is decoded, so
    invalid UTF-8 in a skill's prose body is not this linter's business while
    invalid UTF-8 in the frontmatter is a finding. Decoding the whole file with
    `errors="replace"` made both invisible.
    """
    raw, unreadable = _read_bytes(skill_md)
    if unreadable:
        return {}, unreadable, True
    if raw is None:
        return {}, None, False
    if raw.startswith(b"\xef\xbb\xbf"):
        return {}, "starts with a UTF-8 BOM before the --- fence", True
    lines = raw.replace(b"\r\n", b"\n").split(b"\n")
    # EXACT equality at BOTH ends. `startswith("---")` accepted a decorated
    # opener and `find("\n---")` accepted `---yaml` as a closer, which is the
    # false green: a lax closing fence silently truncates the document.
    if not lines or lines[0] != FENCE:
        return {}, "missing YAML frontmatter (no leading ---)", True
    closing = next((i for i, line in enumerate(lines[1:], 1) if line == FENCE), None)
    if closing is None:
        return {}, "unclosed YAML frontmatter", True
    try:
        body = b"\n".join(lines[1:closing]).decode("utf-8")
    except UnicodeDecodeError as exc:
        return {}, f"frontmatter is not valid UTF-8 ({exc.reason})", True
    try:
        data = yaml.load(body, Loader=_NoDuplicateKeys)
    except yaml.YAMLError as exc:
        # FLATTENED, not truncated. A PyYAML error is several lines including a
        # caret diagram; printing it raw broke the one-error-per-line format the
        # rest of the report relies on, and truncating to the first line threw
        # away the line/column that makes it actionable.
        detail = " ".join(part.strip() for part in str(exc).split("\n") if part.strip())
        return {}, f"malformed YAML — {detail}", True
    if data is None:
        return {}, None, True
    if not isinstance(data, dict):
        return {}, "frontmatter is not a mapping", True
    return data, None, True


def discover(skills_dir: Path) -> tuple[list[Path], list[str]]:
    """`(skill_dirs_manifests, reasons_a_subtree_could_not_be_enumerated)`.

    `os.walk` with `onerror`, NOT `rglob`. Two reasons:

      - on Python 3.11 — which the workflow pins — `Path.rglob` filters
        candidates through `Path.exists()`, which FOLLOWS symlinks, so a
        dangling `SKILL.md` is never yielded at all. On 3.12+ it is yielded and
        then crashes. Broken either way, differently per version.
      - `os.walk` silently swallows a directory it cannot list, so an EACCES
        subtree read as a subtree with nothing in it. Enumerating is a
        measurement; failing it is a finding, not a smaller tree.
    """
    found: list[Path] = []
    unwalkable: list[str] = []

    def _record(exc: OSError) -> None:
        where = getattr(exc, "filename", None) or skills_dir
        try:
            where = Path(where).relative_to(skills_dir)
        except ValueError:
            pass
        unwalkable.append(
            f"{where}: directory could not be listed ({type(exc).__name__}) — "
            "the skills under it were NOT checked")

    for root, subdirs, files in os.walk(skills_dir, followlinks=False, onerror=_record):
        rel = Path(root).relative_to(skills_dir)
        if "extensions" in rel.parts:
            subdirs[:] = []
            continue
        # A symlinked DIRECTORY is not entered — `followlinks=True` invites a
        # loop — but silently not entering one is the same omission this file
        # exists to remove. The old gate missed these too, so this is not a
        # behaviour regression; it is the omission being reported instead of
        # taken. `skills/` currently holds zero symlinks, so nothing real
        # changes today.
        for sub in subdirs:
            link = Path(root) / sub
            if link.is_symlink() and (link / "SKILL.md").exists():
                unwalkable.append(
                    f"{rel / sub}: is a symlinked directory holding a SKILL.md and was "
                    "NOT entered; move the skill into the repository or remove the link")
        if "SKILL.md" in files:
            found.append(Path(root) / "SKILL.md")
        elif "SKILL.md" in subdirs:
            # `os.walk` sorts a directory — or a symlink to one — into dirnames,
            # so a SKILL.md of that shape never appears in `files`.
            unwalkable.append(
                f"{rel}/SKILL.md: is a directory, not a manifest — "
                "the skill was NOT checked")
    return sorted(found), unwalkable


def lint_skill_md(skill_md: Path) -> list[str]:
    """Errors for one manifest.

    Messages are byte-identical to the inline version's for every input the old
    gate handled, so the EXTRACTION is provably behaviour-preserving and any
    output difference is attributable to a fix rather than to the move. The one
    deliberate wording change is the UTF-8 BOM case: the old gate reported it as
    "missing YAML frontmatter", which sent readers looking for a fence that was
    right there.
    """
    fm, unreadable, present = read_frontmatter(skill_md)
    if not present:
        # This function is only ever called on a path DISCOVERY returned, so
        # "absent" here does not mean "no skill lives here" — it means the
        # manifest went away between being found and being read. Returning []
        # made that a silent exemption.
        return [f"{skill_md}: vanished between discovery and reading"]
    if unreadable:
        # NOT an exemption. "I could not read the manifest" is a finding about
        # the manifest.
        return [f"{skill_md}: {unreadable}"]
    parent = skill_md.parent.name
    errors: list[str] = []
    name = fm.get("name")
    if not name:
        errors.append(f"{skill_md}: missing required field `name`")
    elif not isinstance(name, str):
        errors.append(f"{skill_md}: `name` must be a string, got {type(name).__name__}")
    elif len(name) > MAX_NAME:
        errors.append(f"{skill_md}: `name` exceeds {MAX_NAME} chars ({len(name)})")
    elif not NAME_RE.fullmatch(name):
        errors.append(
            f"{skill_md}: `name`='{name}' must match [a-z][a-z0-9]*(-[a-z0-9]+)* "
            "(lowercase, hyphens, no leading/trailing/consecutive)")
    elif name != parent:
        errors.append(
            f"{skill_md}: `name`='{name}' does not match parent dir '{parent}' "
            "(agentskills.io §Name)")
    description = fm.get("description")
    if not description:
        errors.append(f"{skill_md}: missing required field `description`")
    elif not isinstance(description, str):
        errors.append(
            f"{skill_md}: `description` must be a string, got "
            f"{type(description).__name__}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skills-dir", type=Path, default=Path("skills"))
    args = parser.parse_args(argv)
    skills_dir = args.skills_dir

    if not skills_dir.is_dir():
        print(f"ERROR: no skills/ dir at {skills_dir}")
        return 1

    skill_mds, unwalkable = discover(skills_dir)
    if not skill_mds and not unwalkable:
        print(f"ERROR: no SKILL.md found under {skills_dir}/")
        return 1

    print(f"linting {len(skill_mds)} SKILL.md files\n")

    # Seeded from discovery: a subtree we could not enumerate is a finding by
    # construction, not a smaller tree. The old `if not skill_mds` guard fired
    # only when EVERYTHING was unreadable, so one good skill was enough to hide
    # an unlistable sibling.
    errors: list[str] = list(unwalkable)
    for md in skill_mds:
        errors.extend(lint_skill_md(md))

    if errors:
        print("FAIL — frontmatter violations:\n")
        for err in errors:
            print(f"  {err}")
        print(f"\n{len(errors)} error(s) across {len(skill_mds)} skill(s)")
        return 1
    print(f"OK — {len(skill_mds)} SKILL.md files conform to agentskills.io spec")
    return 0


if __name__ == "__main__":
    sys.exit(main())
