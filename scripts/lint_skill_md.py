#!/usr/bin/env python3
"""Registry-wide SKILL.md frontmatter linter for the broomva/skills monorepo.

Validates every skill against the agentskills.io specification
(https://agentskills.io/specification):

  name         required, <=64 chars, lowercase [a-z0-9-], no leading/trailing or
               consecutive hyphens, and must match the parent directory name.
               A leading digit is legal (`1password`).
  description  required, non-empty, <=1024 chars
  compatibility  optional; when present must be 1-500 chars (empty is invalid)

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
import ast
import re
import sys
from pathlib import Path

import yaml

# Spec §Name: "May only contain unicode lowercase alphanumeric characters (a-z,
# 0-9) and hyphens (-)", no leading/trailing hyphen, no consecutive hyphens. A
# LEADING DIGIT is therefore legal (`1password`), and this pattern must stay
# byte-identical to skillify_check.SPEC_NAME_RE — two validators enforcing one
# contract must not disagree, or a skill passes one gate and fails the other.
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
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
    """Every independently-installable SKILL.md under `root`, sorted.

    Exclusions apply to ANCESTOR components only (`parts[:-2]`), never to the
    skill's own directory name. Matching every component would silently unlint a
    legitimately-named skill: `tooling/venv/SKILL.md` or `tooling/extensions/
    SKILL.md` would vanish from the registry gate while looking perfectly healthy.
    """
    out = []
    for p in root.rglob("SKILL.md"):
        ancestors = p.relative_to(root).parts[:-2]
        if "extensions" in ancestors or VENDORED.intersection(ancestors):
            continue
        out.append(p)
    return sorted(out)


def extract_grandfathered(source: str) -> dict[str, int]:
    """Read the GRANDFATHERED literal out of a copy of this module's source.

    Parsed with `ast`, never imported — the whole point is to inspect a version
    of this file from another commit, which must not execute.
    """
    tree = ast.parse(source)
    found = []
    mutated: str | None = None

    # MODULE LEVEL ONLY. A scope-blind ast.walk counts a harmless local shadow
    # (`def f(): GRANDFATHERED = {}`) as a second baseline binding and rejects an
    # otherwise-unchanged file. Only the module-level binding is the baseline.
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id == "GRANDFATHERED" and node.value is not None:
                    found.append(ast.literal_eval(node.value))
                if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                        and t.value.id == "GRANDFATHERED"):
                    mutated = "GRANDFATHERED[...] = ..."
        elif isinstance(node, ast.AugAssign):
            # `GRANDFATHERED |= {...}` rewrites the runtime mapping while the
            # literal above it — the one this function returns — stays innocent.
            # The SUBSCRIPT form (`GRANDFATHERED["k"] += 500`) does the same for
            # one entry, which is exactly a frozen-length raise.
            tgt = node.target
            if isinstance(tgt, ast.Name) and tgt.id == "GRANDFATHERED":
                mutated = "GRANDFATHERED |= ... (augmented assignment)"
            elif (isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Name)
                    and tgt.value.id == "GRANDFATHERED"):
                mutated = "GRANDFATHERED[...] += ... (augmented subscript assignment)"

    # Only genuinely MUTATING dict methods count. Flagging every attribute call
    # made `.get(...)` or `.copy()` — pure reads — abort the comparison. The set
    # of dict mutators is closed, so enumerate it instead of guessing.
    # `fromkeys` is deliberately absent: it returns a NEW dict and leaves the
    # receiver untouched, so classifying it as a mutator aborts on a pure read.
    _DICT_MUTATORS = {"update", "setdefault", "pop", "popitem", "clear",
                      "__setitem__", "__delitem__"}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "GRANDFATHERED"
                and node.func.attr in _DICT_MUTATORS):
            mutated = f"GRANDFATHERED.{node.func.attr}(...)"

    if not found:
        raise ValueError("GRANDFATHERED not found in source")
    # Returning the FIRST of several bindings would let a benign first assignment
    # shadow a second one carrying new debt: compare_ratchet would clear the
    # decoy while lint() used the real mapping. One binding, no mutation, or the
    # comparison is not measuring what runs.
    if len(found) > 1:
        raise ValueError(f"GRANDFATHERED is assigned {len(found)} times — "
                         "the ratchet baseline must have exactly one binding")
    if mutated:
        raise ValueError(f"GRANDFATHERED is mutated after assignment ({mutated}) — "
                         "the ratchet baseline must be a single immutable literal")
    return found[0]


def compare_ratchet(base_src: str, head_src: str) -> list[str]:
    """Errors if HEAD's ratchet is not monotonically tighter than BASE's.

    Without this the ratchet does not ratchet. Every rule in `lint()` reads the
    baseline out of the same file the PR is editing, so a PR can legalise new
    over-cap debt simply by appending its own entry, or undo a shrink by raising
    a frozen number — and every test still passes. The baseline is only a
    baseline if it cannot be moved by the change being measured.
    """
    base, head = extract_grandfathered(base_src), extract_grandfathered(head_src)
    errors = []
    for key, length in sorted(head.items()):
        if key not in base:
            errors.append(
                f"GRANDFATHERED gained '{key}' ({length}) — the ratchet may only "
                "shrink. Bring the description under the cap instead of freezing it.")
        elif length > base[key]:
            errors.append(
                f"GRANDFATHERED raised '{key}' {base[key]} -> {length} — frozen "
                "lengths may only decrease.")
    return errors


def _parse(md: Path) -> tuple[dict | None, str | None]:
    """(frontmatter, error). Exactly one is non-None.

    Delimiters are matched as WHOLE LINES. A substring test (`startswith("---")`
    / `find("\\n---")`) accepts `---invalid` as an opener and lets a body line
    like `---8<---` terminate the block early, silently truncating the
    frontmatter that everything downstream is validating.
    """
    text = md.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, "missing YAML frontmatter (no leading ---)"
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        return None, "unclosed YAML frontmatter"
    try:
        fm = yaml.safe_load("\n".join(lines[1:close])) or {}
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
        # Record the path as SEEN at discovery, not after the description
        # validates. Otherwise a grandfathered skill with a malformed or missing
        # description reports twice — once for the real defect and once as a
        # bogus "stale grandfather entry" — pointing the author at the wrong file.
        seen.add(key)
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
                f"{key}: `name`='{name}' must match {NAME_RE.pattern} "
                "(lowercase a-z0-9 and hyphens, no leading/trailing/consecutive hyphen)")
        elif name != md.parent.name:
            errors.append(
                f"{key}: `name`='{name}' does not match parent dir "
                f"'{md.parent.name}' (agentskills.io §Name)")

        # Spec §compatibility: "Must be 1-500 characters IF PROVIDED" — so a
        # present-but-empty value is invalid, not merely absent.
        if "compatibility" in fm:
            compat = fm["compatibility"]
            if not isinstance(compat, str):
                errors.append(
                    f"{key}: `compatibility` must be a string, got {type(compat).__name__}")
            elif not compat.strip():
                errors.append(f"{key}: `compatibility` is present but empty (spec: 1-500 chars)")
            elif len(compat) > MAX_COMPATIBILITY:
                errors.append(
                    f"{key}: `compatibility` is {len(compat)} chars > {MAX_COMPATIBILITY} max")

        desc = fm.get("description")
        if not desc:
            errors.append(f"{key}: missing required field `description`")
            continue
        if not isinstance(desc, str):
            errors.append(f"{key}: `description` must be a string, got {type(desc).__name__}")
            continue

        dlen, prior = len(desc), grandfathered.get(key)
        if dlen > MAX_DESC:
            if prior is None:
                errors.append(
                    f"{key}: `description` is {dlen} chars > {MAX_DESC} max "
                    f"(agentskills.io §Description). {MAX_DESC + 1}-{RENDER_CAP} still renders "
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
    ap.add_argument("--compare-baseline", metavar="PATH", default=None,
                    help="a copy of this file from the merge base; assert the ratchet "
                         "only shrank (new/raised GRANDFATHERED entries are rejected)")
    args = ap.parse_args(argv)

    if args.compare_baseline:
        base = Path(args.compare_baseline)
        if not base.is_file():
            print(f"ERROR: baseline not found: {base}", file=sys.stderr)
            return 2
        drift = compare_ratchet(base.read_text(encoding="utf-8"),
                                Path(__file__).read_text(encoding="utf-8"))
        if drift:
            print("FAIL — the ratchet moved the wrong way:\n")
            for e in drift:
                print(f"  {e}")
            return 1
        print("OK — GRANDFATHERED is monotonically tighter than the baseline")

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
