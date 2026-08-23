#!/usr/bin/env python3
"""Catalog-consistency linter for the broomva/skills monorepo.

Three surfaces describe the same set of skills, and all three are maintained by
hand:

  1. `README.md`                                     — per-category tables, a
     bucket-count table, and prose counts
  2. `skills/tooling/skills-catalog/references/skills-inventory.md`
     — the "canonical reference inventory"
  3. `skills/tooling/skills-catalog/SKILL.md`         — a bucket table and prose
     counts

Nothing derived them, so each PR carried forward whatever the previous one
wrote. Measured on main at 391a76a: disk had 93 skills, README listed 91 rows
while claiming 90, and the inventory listed 87. Six shipped skills had never
been catalogued at all.

The truth is `skills/<category>/<name>/SKILL.md` on disk. This script derives
every count and every row set from it and reports each surface that disagrees.
`--fix` rewrites the surfaces to match.

Two failure modes are worth naming, because only one of them is about counts:

  * COUNT DRIFT — a number nobody recomputes.
  * FORMAT DRIFT — `attempt-audit` had been added to the inventory as a
    `- **`x`** — ...` BULLET sitting inside a markdown table. That breaks the
    table render AND hides the row from every line-based check, which is why
    the two files disagreed by three different numbers rather than by one. A
    linter that only counted `| `x` |` rows would have called that file
    consistent while a skill was missing from it.

Exit 0 when every surface agrees, 1 otherwise. Pure stdlib + PyYAML; no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
_README = _REPO_ROOT / "README.md"
_INVENTORY = _SKILLS_DIR / "tooling/skills-catalog/references/skills-inventory.md"
_CATALOG_SKILL = _SKILLS_DIR / "tooling/skills-catalog/SKILL.md"

#: A README row: `| [`name`](skills/cat/name/)<annot> | description |`.
#: The optional group is the name-cell annotation — `**(vendored)**` on parallax
#: marks a copy the `parallax-sync` gate keeps byte-identical to its canonical
#: repo. Capture it, or a rewrite silently strips a marker another gate needs.
_README_ROW = re.compile(
    r"^\| \[`([a-z0-9-]+)`\]\([^)]*\)(\s\*\*.*?\*\*)?\s*\| (.*?) \|\s*$"
)
#: An inventory row: `| `name`<annot> | description |`.
_INV_ROW = re.compile(r"^\| `([a-z0-9-]+)`(\s\*\*.*?\*\*)?\s*\| (.*?) \|\s*$")
#: A skill named as a BULLET where a table row belongs. Malformed, but it IS
#: the skill being present — treat it as a row so `--fix` normalises it rather
#: than inserting a duplicate alongside it.
_STRAY_BULLET = re.compile(r"^- \*\*`([a-z0-9-]+)`\*\*\s*[—-]\s*(.*?)\s*$")

_README_HEADING = re.compile(r"^### .+? — `skills/(?P<cat>[a-z]+)/`$", re.M)
_INV_HEADING = re.compile(r"^## .+? — `skills/(?P<cat>[a-z]+)/` \((?P<n>\d+)\)$", re.M)

_DESC_LIMIT = 200


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


def _short(description: object, limit: int = _DESC_LIMIT) -> str:
    """One-line description, trimmed at a word boundary. Only ever applied to a
    row being ADDED — an existing row keeps its authored wording, so running
    --fix does not churn 90 descriptions to add one."""
    text = " ".join(str(description or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


def discover(skills_dir: Path | None = None) -> dict[str, dict[str, str]]:
    """`{category: {skill_name: description}}` from the filesystem.

    Only depth-2 (`skills/<category>/<name>/SKILL.md`) counts as a skill, which
    is what the README's own "22 single-noun category buckets" describes. A
    nested sub-skill (`skills/<x>/skills/<sub>/SKILL.md`) is part of its parent
    and is deliberately not a catalog row.
    """
    # Resolved at CALL time, not bound as a default: a module-level default
    # argument freezes at import, so a caller that repoints _SKILLS_DIR (every
    # test here) would silently keep scanning the real repo.
    skills_dir = _SKILLS_DIR if skills_dir is None else skills_dir
    out: dict[str, dict[str, str]] = {}
    for skill_md in sorted(skills_dir.glob("*/*/SKILL.md")):
        category, name = skill_md.parts[-3], skill_md.parts[-2]
        out.setdefault(category, {})[name] = _short(_frontmatter(skill_md).get("description"))
    return out


class _Section:
    """One category's table inside a surface, and how to rewrite it."""

    def __init__(self, category: str, start: int, stop: int, rows: dict, annot: dict,
                 strays: list[str], prose: list[str]):
        self.category = category
        self.start = start
        self.stop = stop
        self.rows = rows          # name -> description, in file order
        self.annot = annot        # name -> " **(vendored)**"
        self.strays = strays      # names found as bullets, not rows
        self.prose = prose        # non-row lines to keep after the table


def _sections(text: str, heading_rx: re.Pattern, row_rx: re.Pattern) -> list[_Section]:
    """Every category table in `text`.

    The region runs from the table separator to the next heading — NOT to the
    first non-row line. Scanning a contiguous run of `|` lines stops dead at a
    malformed row, truncating the set of rows believed present, and a --fix
    built on that then inserts duplicates of everything below the break.
    """
    sections: list[_Section] = []
    for heading in heading_rx.finditer(text):
        sep = text.find("|---|---|\n", heading.end())
        if sep == -1:
            continue
        sep += len("|---|---|\n")
        nxt = [p for p in (text.find("\n## ", sep), text.find("\n### ", sep)) if p != -1]
        stop = min(nxt) if nxt else len(text)
        rows: dict[str, str] = {}
        annot: dict[str, str] = {}
        strays: list[str] = []
        prose: list[str] = []
        for line in text[sep:stop].split("\n"):
            row = row_rx.match(line)
            if row:
                rows[row.group(1)] = row.group(3)
                if row.group(2):
                    annot[row.group(1)] = row.group(2)
                continue
            bullet = _STRAY_BULLET.match(line)
            if bullet:
                rows[bullet.group(1)] = bullet.group(2)
                strays.append(bullet.group(1))
                continue
            if line.strip():
                prose.append(line)
        sections.append(_Section(heading.group("cat"), sep, stop, rows, annot, strays, prose))
    return sections


def _rebuild(text: str, sections: list[_Section], disk: dict, render) -> str:
    """Rewrite each section's table from (existing rows ∪ disk), sorted."""
    out: list[str] = []
    cursor = 0
    for sec in sections:
        merged = dict(sec.rows)
        for name, desc in disk.get(sec.category, {}).items():
            merged.setdefault(name, desc)
        keep = {n: merged[n] for n in sorted(disk.get(sec.category, {})) if n in merged}
        body = "\n".join(render(sec.category, n, keep[n], sec.annot.get(n, "")) for n in keep)
        body += "\n"
        if sec.prose:
            body += "\n" + "\n".join(sec.prose) + "\n"
        out.append(text[cursor:sec.start])
        out.append(body)
        cursor = sec.stop
    out.append(text[cursor:])
    return "".join(out)


def _recount(text: str, disk: dict, bucket_rx: str) -> str:
    """Set every derived count. Deliberately anchored, never a blanket
    substitution of the number: `skills-catalog/SKILL.md` carries an unrelated
    "broader-ecosystem catalog (86 rows, 15 marketing domains)" note, and a
    global replace of the old total would silently corrupt it."""
    total = sum(len(v) for v in disk.values())
    text = re.sub(r"\*\*\d+ skills\*\*", f"**{total} skills**", text)
    text = re.sub(r"The \d+ skills bucket", f"The {total} skills bucket", text)
    text = re.sub(r"\d+ skills across", f"{total} skills across", text)
    text = re.sub(r"\d+ agent skills", f"{total} agent skills", text)
    text = re.sub(r"inventory of the \d+ skills", f"inventory of the {total} skills", text)
    for category, names in disk.items():
        n = len(names)
        text = re.sub(bucket_rx.format(cat=category), rf"\g<1>{n}\g<2>", text)
        text = re.sub(rf"(— `skills/{category}/` )\(\d+\)", rf"\g<1>({n})", text)
    return text


def _declared_counts(text: str) -> list[int]:
    """Every total this surface claims, so a check can compare them to disk."""
    found = []
    for rx in (r"\*\*(\d+) skills\*\*", r"The (\d+) skills bucket", r"(\d+) skills across",
               r"(\d+) agent skills", r"inventory of the (\d+) skills"):
        found += [int(m) for m in re.findall(rx, text)]
    return found


def check(disk: dict, surfaces: dict[str, tuple[Path, list[_Section], str]]) -> list[str]:
    problems: list[str] = []
    total = sum(len(v) for v in disk.values())
    for label, (_path, sections, text) in surfaces.items():
        listed: set[str] = set()
        for sec in sections:
            on_disk = set(disk.get(sec.category, {}))
            listed |= set(sec.rows)
            for name in sorted(on_disk - set(sec.rows)):
                problems.append(f"{label}: `{name}` is on disk but has no row in {sec.category}")
            for name in sorted(set(sec.rows) - on_disk):
                problems.append(f"{label}: `{name}` has a row in {sec.category} but is not on disk")
            for name in sec.strays:
                problems.append(
                    f"{label}: `{name}` is a bullet inside the {sec.category} table, not a row "
                    "— it breaks the render and hides the skill from line-based checks"
                )
        for declared in _declared_counts(text):
            if declared != total:
                problems.append(f"{label}: claims {declared} skills, disk has {total}")
                break
        if sections:
            covered = {s.category for s in sections}
            for category in sorted(set(disk) - covered):
                problems.append(f"{label}: no section for category `{category}`")
    for label, (_path, _sections, text) in surfaces.items():
        for category, names in disk.items():
            for m in re.finditer(rf"\(`{category}`\) \| (\d+) \|", text):
                if int(m.group(1)) != len(names):
                    problems.append(
                        f"{label}: bucket `{category}` says {m.group(1)}, disk has {len(names)}")
            for m in re.finditer(rf"\| `skills/{category}/` \| (\d+) \|", text):
                if int(m.group(1)) != len(names):
                    problems.append(
                        f"{label}: bucket `{category}` says {m.group(1)}, disk has {len(names)}")
            for m in re.finditer(rf"— `skills/{category}/` \((\d+)\)", text):
                if int(m.group(1)) != len(names):
                    problems.append(
                        f"{label}: bucket `{category}` says {m.group(1)}, disk has {len(names)}")
    return problems


def _load() -> dict[str, tuple[Path, list[_Section], str]]:
    readme = _README.read_text(encoding="utf-8")
    inventory = _INVENTORY.read_text(encoding="utf-8")
    catalog = _CATALOG_SKILL.read_text(encoding="utf-8")
    return {
        "README.md": (_README, _sections(readme, _README_HEADING, _README_ROW), readme),
        "skills-inventory.md": (_INVENTORY, _sections(inventory, _INV_HEADING, _INV_ROW), inventory),
        "skills-catalog/SKILL.md": (_CATALOG_SKILL, [], catalog),
    }


def fix(disk: dict) -> None:
    readme = _README.read_text(encoding="utf-8")
    readme = _rebuild(readme, _sections(readme, _README_HEADING, _README_ROW), disk,
                      lambda c, n, d, a: f"| [`{n}`](skills/{c}/{n}/){a} | {d} |")
    _README.write_text(_recount(readme, disk, r"(\| `skills/{cat}/` \| )\d+( \|)"), encoding="utf-8")

    inventory = _INVENTORY.read_text(encoding="utf-8")
    inventory = _rebuild(inventory, _sections(inventory, _INV_HEADING, _INV_ROW), disk,
                         lambda c, n, d, a: f"| `{n}`{a} | {d} |")
    _INVENTORY.write_text(_recount(inventory, disk, r"(\(`{cat}`\) \| )\d+( \|)"), encoding="utf-8")

    catalog = _CATALOG_SKILL.read_text(encoding="utf-8")
    _CATALOG_SKILL.write_text(_recount(catalog, disk, r"(\(`{cat}`\) \| )\d+( \|)"), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--fix", action="store_true", help="rewrite the surfaces to match disk")
    args = ap.parse_args(argv)

    disk = discover()
    total = sum(len(v) for v in disk.values())
    if args.fix:
        fix(disk)
        remaining = check(discover(), _load())
        if remaining:
            print("✗ --fix could not reconcile:", file=sys.stderr)
            for line in remaining:
                print(f"  - {line}", file=sys.stderr)
            return 1
        print(f"✓ catalog rewritten from disk ({total} skills, {len(disk)} buckets)")
        return 0

    problems = check(disk, _load())
    if problems:
        print(f"✗ catalog disagrees with disk ({total} skills, {len(disk)} buckets):",
              file=sys.stderr)
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        print("\nRun `python3 scripts/lint_skill_catalog.py --fix`.", file=sys.stderr)
        return 1
    print(f"✓ catalog consistent ({total} skills, {len(disk)} buckets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
