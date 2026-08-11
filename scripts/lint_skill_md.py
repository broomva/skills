#!/usr/bin/env python3
"""Registry-wide SKILL.md frontmatter linter for the broomva/skills monorepo.

Validates every skill against the agentskills.io specification
(https://agentskills.io/specification):

  name         required, <=64 chars, lowercase [a-z0-9-], no leading/trailing or
               consecutive hyphens, and must match the parent directory name
  description  required, non-empty, <=1024 chars
  compatibility  optional, <=500 chars

Nested sub-skills (skills/<x>/skills/<sub>/SKILL.md) are checked the same way.
Skill-private `extensions/` and third-party skills vendored inside virtualenvs
are excluded.

## The description ratchet

The 1024-char `description` cap is normative, and it is TIGHTER than the
1536-char cap the Claude Code host renders at (measured in BRO-2014). Between
the two sits a *silent band*: a description of 1025-1536 renders in full, fires
normally, and is still invalid under the standard — it breaks only when some
other conforming host loads the skill.

25 of 90 skills already exceeded the cap when the rule arrived, so a hard fail
would have blocked every subsequent PR. Instead the cap ratchets, via
GRANDFATHERED, whose keys are paths **relative to the scan root** (so
`knowledge/kg/SKILL.md`, not `skills/knowledge/kg/SKILL.md`) mapped to the
length frozen at adoption. Four rules:

  * a skill NOT listed that exceeds the cap        -> FAIL  (no new debt)
  * a listed skill whose description GREW          -> FAIL  (no regression)
  * a listed skill now at/under the cap            -> FAIL  (remove it; no rot)
  * a listed path matching no skill                -> FAIL  (no stale entries)

The remaining backlog prints on every run — never silent. Burndown is editorial
compression, not truncation: a description is trigger surface, and cutting it
carelessly stops the skill firing. Tracked in BRO-2131.

Pure stdlib + PyYAML; no network. Exit 1 on any violation.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESC = 1024          # agentskills.io §Description — normative, NOT the render cap
MAX_COMPATIBILITY = 500  # agentskills.io §compatibility
RENDER_CAP = 1536        # measured, informational — the top of the silent band

# Third-party skills vendored inside virtualenvs / package dirs are not ours to
# lint. They are gitignored, so CI's fresh checkout never sees them — but a
# LOCAL run does, and would fail on someone else's skill. Excluding them is what
# makes a local run reproduce CI exactly.
VENDORED = {".venv", "venv", "node_modules", "site-packages", ".git"}

GRANDFATHERED: dict[str, int] = {
    "knowledge/kg/SKILL.md": 2218,
    "orchestration/governed-autonomy-loop/SKILL.md": 1808,
    "knowledge/colombia-conflict/SKILL.md": 1782,
    "governance/architecture-design-principles/SKILL.md": 1709,
    "governance/dogfood/SKILL.md": 1691,
    "publishing/revenuecast/SKILL.md": 1601,
    "tooling/disambiguate/SKILL.md": 1516,
    "aerospace/sdr-satellite/SKILL.md": 1429,
    "governance/unhobble/SKILL.md": 1396,
    "design/design-distill/SKILL.md": 1390,
    "knowledge/comprehend/SKILL.md": 1390,
    "governance/keel/SKILL.md": 1356,
    "models/heretic-abliteration/SKILL.md": 1320,
    "video/video-cut/SKILL.md": 1298,
    "tooling/audit-harness-usage/SKILL.md": 1243,
    "research/checkit/SKILL.md": 1226,
    "knowledge/what/SKILL.md": 1222,
    "orchestration/p9/SKILL.md": 1137,
    "governance/bstack/SKILL.md": 1136,
    "design/tekton/SKILL.md": 1133,
    "orchestration/handoff/SKILL.md": 1116,
    "tooling/make-spec/SKILL.md": 1088,
    "compute/agentic-vps/SKILL.md": 1046,
    "commerce/d1-cli/SKILL.md": 1041,
    "knowledge/ccr/SKILL.md": 1027,
}


def discover(root: Path) -> list[Path]:
    """Every independently-installable SKILL.md under `root`, sorted."""
    out = []
    for p in root.rglob("SKILL.md"):
        parts = p.relative_to(root).parts
        if "extensions" in parts or VENDORED.intersection(parts):
            continue
        out.append(p)
    return sorted(out)


def _parse(md: Path) -> tuple[dict | None, str | None]:
    """(frontmatter, error). Exactly one is non-None."""
    text = md.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None, "missing YAML frontmatter (no leading ---)"
    end = text.find("\n---", 3)
    if end < 0:
        return None, "unclosed YAML frontmatter"
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as e:
        return None, f"malformed YAML — {e}"
    if not isinstance(fm, dict):
        return None, "frontmatter is not a mapping"
    return fm, None


def lint(root: Path, grandfathered: dict[str, int] | None = None,
         ) -> tuple[list[str], list[tuple[str, int, int]], int]:
    """Return (errors, backlog, n_skills). Pure — no printing, no exit."""
    grandfathered = GRANDFATHERED if grandfathered is None else grandfathered
    errors: list[str] = []
    backlog: list[tuple[str, int, int]] = []
    seen: set[str] = set()

    skill_mds = discover(root)
    if not skill_mds:
        return [f"no SKILL.md found under {root}"], [], 0

    for md in skill_mds:
        rel = md.relative_to(root)
        key = rel.as_posix()
        fm, err = _parse(md)
        if err:
            errors.append(f"{key}: {err}")
            continue
        assert fm is not None

        name = fm.get("name")
        if not name:
            errors.append(f"{key}: missing required field `name`")
        elif not isinstance(name, str):
            errors.append(f"{key}: `name` must be a string, got {type(name).__name__}")
        elif len(name) > MAX_NAME:
            errors.append(f"{key}: `name` exceeds {MAX_NAME} chars ({len(name)})")
        elif not NAME_RE.match(name):
            errors.append(
                f"{key}: `name`='{name}' must match [a-z][a-z0-9]*(-[a-z0-9]+)* "
                "(lowercase, hyphens, no leading/trailing/consecutive)")
        elif name != md.parent.name:
            errors.append(
                f"{key}: `name`='{name}' does not match parent dir "
                f"'{md.parent.name}' (agentskills.io §Name)")

        compat = fm.get("compatibility")
        if isinstance(compat, str) and len(compat) > MAX_COMPATIBILITY:
            errors.append(
                f"{key}: `compatibility` is {len(compat)} chars > {MAX_COMPATIBILITY} max")

        desc = fm.get("description")
        if not desc:
            errors.append(f"{key}: missing required field `description`")
            continue
        if not isinstance(desc, str):
            errors.append(f"{key}: `description` must be a string, got {type(desc).__name__}")
            continue

        seen.add(key)
        dlen, prior = len(desc), grandfathered.get(key)
        if dlen > MAX_DESC:
            if prior is None:
                errors.append(
                    f"{key}: `description` is {dlen} chars > {MAX_DESC} max "
                    f"(agentskills.io §Description). {MAX_DESC}-{RENDER_CAP} still renders "
                    "in full in Claude Code — that is the silent band, not permission.")
            elif dlen > prior:
                errors.append(
                    f"{key}: `description` grew {prior} -> {dlen} chars; grandfathered "
                    f"skills may only shrink toward the {MAX_DESC} cap")
            else:
                backlog.append((key, dlen, prior))
        elif prior is not None:
            errors.append(
                f"{key}: `description` now conforms ({dlen} <= {MAX_DESC}) — remove "
                f"'{key}' from GRANDFATHERED in scripts/lint_skill_md.py so the list "
                "cannot rot")

    for stale in sorted(set(grandfathered) - seen):
        errors.append(
            f"GRANDFATHERED entry '{stale}' matches no linted skill "
            "(renamed or deleted?) — remove it from scripts/lint_skill_md.py")

    return errors, backlog, len(skill_mds)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--root", default="skills", help="directory to scan (default: skills)")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2

    errors, backlog, n = lint(root)

    if backlog:
        print(f"description backlog — {len(backlog)} skill(s) over the {MAX_DESC}-char "
              "spec cap (frozen, may only shrink; BRO-2131):")
        for key, dlen, prior in sorted(backlog, key=lambda r: -r[1]):
            print(f"  {dlen:>5} (cap+{dlen - MAX_DESC:<4}) {key}")
        print()

    if errors:
        print("FAIL — frontmatter violations:\n")
        for e in errors:
            print(f"  {e}")
        print(f"\n{len(errors)} error(s) across {n} skill(s)")
        return 1

    print(f"OK — {n} SKILL.md files conform to agentskills.io spec"
          + (f" ({len(backlog)} grandfathered description(s) pending burndown)"
             if backlog else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
