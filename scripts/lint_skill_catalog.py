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

#: Surfaces that carry per-category tables. `skills-catalog/SKILL.md` states
#: counts only, so a missing-section diagnostic would be a false positive there.
_ROW_SURFACES = ("README.md", "skills-inventory.md")

_DESC_LIMIT = 200


def _read_frontmatter(skill_md: Path) -> tuple[dict, str | None]:
    """`(frontmatter, reason_it_could_not_be_read)`.

    Three states, not two. Returning a bare `{}` for an unreadable manifest
    makes "I could not read this" indistinguishable from "there was nothing to
    read", and the caller then treats a broken file as an ordinary one — the
    same collapse that lets a BOM silently exempt a skill from version linting
    in the sibling script (BRO-2269). A UTF-8 BOM is invisible in most editors
    and is exactly what a Windows editor or a careless shell redirect produces.
    """
    raw = skill_md.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return {}, "starts with a UTF-8 BOM before the --- fence"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {}, f"is not valid UTF-8 ({exc.reason})"
    if not text.startswith("---"):
        return {}, "does not start with a --- frontmatter fence"
    end = text.find("\n---", 3)
    if end == -1:
        return {}, "has no closing --- fence"
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError as exc:
        return {}, f"has unparseable YAML frontmatter ({str(exc).splitlines()[0][:60]})"
    if not isinstance(data, dict):
        return {}, "frontmatter is not a mapping"
    return data, None


def _frontmatter(skill_md: Path) -> dict:
    return _read_frontmatter(skill_md)[0]


def unreadable_manifests(skills_dir: Path | None = None) -> list[str]:
    """Every SKILL.md whose frontmatter could not be read, and why."""
    skills_dir = _SKILLS_DIR if skills_dir is None else skills_dir
    out = []
    for skill_md in sorted(skills_dir.glob("*/*/SKILL.md")):
        reason = _read_frontmatter(skill_md)[1]
        if reason:
            out.append(f"{skill_md.parts[-3]}/{skill_md.parts[-2]}: SKILL.md {reason}")
    return out


def _short(description: object, limit: int = _DESC_LIMIT) -> str:
    """One-line description, trimmed at a word boundary. Only ever applied to a
    row being ADDED — an existing row keeps its authored wording, so running
    --fix does not churn 90 descriptions to add one."""
    text = " ".join(str(description or "").split())
    # A raw `|` ends the markdown cell early, so a frontmatter description
    # containing one renders a broken row that this file's own row regex still
    # happily re-parses — malformed, and invisible to the next run.
    text = text.replace("|", "\\|")
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
            # Keep BLANK lines too, then trim the ends. Dropping them collapses
            # a paragraph and its own nested table into one run — a section can
            # legitimately carry more than the skill table (a platform matrix, a
            # note), and that content is re-emitted below the rebuilt table
            # rather than discarded.
            prose.append(line)
        while prose and not prose[0].strip():
            prose.pop(0)
        while prose and not prose[-1].strip():
            prose.pop()
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


#: Every phrasing in which a surface states the TOTAL. One list drives both the
#: check and the rewrite, so a form can never be verified but not fixed, or the
#: reverse. `(\d+)` is the count; everything else is matched literally.
_TOTAL_FORMS = (
    r"\*\*(\d+) skills\*\*",
    r"The (\d+) skills bucket",
    r"(\d+) skills across",
    r"(\d+) agent skills",
    r"inventory of the (\d+) skills",
    r"(\d+) Tier-2 skills",
    r"\*\*Total skills\*\*: (\d+)",
)

#: Every phrasing in which a surface states the number of CATEGORY BUCKETS.
#: Verified against the number of buckets on disk, not allowlisted away — "22"
#: is as much a derived fact as "93" and drifts the same way.
_BUCKET_TOTAL_FORMS = (
    r"\*\*(\d+) single-noun category buckets\*\*",
    r"(\d+) single-noun categories",
    r"(\d+) single-noun category buckets",
    r"(\d+) category buckets",
    r"the (\d+) `skills/<category>/` directory buckets",
    r"the (\d+) monorepo buckets",
    r"\*\*Total category buckets\*\*: (\d+)",
    # Deliberately last and deliberately loose: the specific forms above are
    # subtracted first, so this catches any remaining "<n> buckets" phrasing
    # rather than leaving one more wording to be discovered by a review round.
    r"(\d+) buckets",
)

#: Aggregates naming a SUPERLATIVE bucket. Verified against disk like any other
#: derived fact: the inventory shipped "Largest bucket: Orchestration &
#: autonomy (7)" while tooling held 10 and orchestration held 8 — both the name
#: and the number wrong, and invisible because the line never says "skill".
#: One compiled, BULLET-ANCHORED pattern per aggregate, used for presence,
#: validation and replacement alike.
#:
#: Anchoring is the point. An unanchored detector searches the whole document,
#: so truncating the real bullet and quoting its correct phrase anywhere else —
#: a doc that cites its own aggregate is not exotic — satisfied presence while
#: the canonical line stated nothing. Three regexes (detector / prefix /
#: validator) also meant three chances to disagree about what "present" means,
#: and each disagreement was a seam. One match, one meaning.
_LARGEST_RX = re.compile(r"^- \*\*Largest bucket\*\*: (?P<name>.+?) \((?P<n>\d+)\)$", re.M)
_SMALLEST_RX = re.compile(r"^- \*\*Smallest buckets\*\* \((?P<n>\d+)\): (?P<names>\S.*)$", re.M)
_TOTAL_SKILLS_RX = re.compile(r"^- \*\*Total skills\*\*: (?P<n>\d+)$", re.M)
_TOTAL_BUCKETS_RX = re.compile(r"^- \*\*Total category buckets\*\*: (?P<n>\d+)$", re.M)

#: Numbers that sit next to the word "skill" and are NOT a count of this repo's
#: skills. Each is allowlisted explicitly rather than by a loose heuristic,
#: because the whole point of the scan below is that anything unrecognised gets
#: REPORTED instead of quietly skipped.
_NOT_A_SKILL_COUNT = (
    r"skills\.sh CLI ≥ v[\d.]+",          # a CLI version
    r"PR #\d+",                            # an upstream PR number
    r"Tier-2",                             # the tier, not a count
    r"depth-\d+\+?",                        # a directory depth, not a count
    r"\(\d+ rows, \d+ marketing domains\)",  # the legacy broader-ecosystem catalog
    r"[Ss]kills-showcase\S*",              # an output filename (…-showcase.mp4)
    r"SkillsShowcase",                     # the Remotion composition id
)

#: The vocabulary of facts this catalog derives. Used BOTH to decide whether a
#: line is making a claim at all, and to decide whether a number on it is part
#: of that claim.
_FACT_WORDS = r"(?:skills?|buckets?|categor(?:y|ies)|largest|smallest|total)"

_FACT_WORD_RX = re.compile(rf"\b{_FACT_WORDS}\b", re.IGNORECASE)


def _states_a_quantity(residue: str, window: int = 25) -> bool:
    """True if a number in `residue` sits within `window` characters of a word
    from the fact vocabulary.

    The proximity requirement is what keeps this from flagging every version
    string, date and video resolution on a line that happens to mention
    buckets. The vocabulary is what keeps it from being inert: requiring the
    word "skill" specifically made the widened line-gate do nothing — "**Median
    bucket size**: 4" passed the line filter and then matched no number — which
    a mutation sweep caught by narrowing the vocabulary back with no test
    failing.

    Written as a scan rather than one regex because the lookbehind would be
    variable-width, which Python's `re` rejects.
    """
    for number in re.finditer(r"\d+", residue):
        lo = max(0, number.start() - window)
        if _FACT_WORD_RX.search(residue[lo:number.end() + window]):
            return True
    return False


def _recount(text: str, disk: dict, bucket_rx: str) -> str:
    """Set every derived count. Deliberately anchored, never a blanket
    substitution of the number: `skills-catalog/SKILL.md` carries an unrelated
    "broader-ecosystem catalog (86 rows, 15 marketing domains)" note, and a
    global replace of the old total would silently corrupt it."""
    total = sum(len(v) for v in disk.values())
    for form in _TOTAL_FORMS:
        # Rebuild the literal with the new number in the capture group's place.
        text = re.sub(form, lambda m: m.group(0).replace(m.group(1), str(total), 1), text)
    for form in _BUCKET_TOTAL_FORMS:
        text = re.sub(form, lambda m: m.group(0).replace(m.group(1), str(len(disk)), 1), text)
    for category, names in disk.items():
        n = len(names)
        text = re.sub(bucket_rx.format(cat=category), rf"\g<1>{n}\g<2>", text)
        text = re.sub(rf"(— `skills/{category}/` )\(\d+\)", rf"\g<1>({n})", text)
    return text


def _declared_counts(text: str, forms: tuple[str, ...] = _TOTAL_FORMS) -> list[int]:
    """Every total this surface claims, so a check can compare them to disk."""
    found = []
    for form in forms:
        found += [int(m) for m in re.findall(form, text)]
    return found


def _labels(inventory_text: str) -> dict[str, str]:
    """`{category: human label}` read from the inventory's own section headings,
    so a superlative can be checked by the name a reader actually sees."""
    return {m.group(2): m.group(1)
            for m in re.finditer(r"^## (.+?) — `skills/([a-z]+)/` \(\d+\)$",
                                 inventory_text, re.M)}


#: Structures a surface MUST contain, keyed by surface, as (name, detector).
#: Every "absent reads as consistent" defect in this file's review history was
#: the same omission spelled in a new place — `if sections:`, then
#: `if not listed:`, then a blanket `|`-line exemption, then `if m:` on the
#: superlatives. Four branches, four rounds. The registry exists so that
#: presence is DECLARED in one place: adding a structure here makes its absence
#: a finding automatically, instead of relying on whoever adds the next check
#: to remember the rule.
_REQUIRED_STRUCTURES: dict[str, tuple[tuple[str, re.Pattern, str], ...]] = {
    "skills-inventory.md": (
        ("**Total skills** aggregate", _TOTAL_SKILLS_RX, "- **Total skills**"),
        ("**Total category buckets** aggregate", _TOTAL_BUCKETS_RX,
         "- **Total category buckets**"),
        ("**Largest bucket** aggregate", _LARGEST_RX, "- **Largest bucket**"),
        ("**Smallest buckets** aggregate", _SMALLEST_RX, "- **Smallest buckets**"),
    ),
}


def _missing_structure_problems(label: str, text: str) -> list[str]:
    """Report any declared aggregate this surface does not carry as a canonical,
    parseable bullet.

    The regex is anchored to the bullet AND is the same object the validator
    uses, so "present" cannot mean one thing here and another there — the seam
    that let `- **Largest bucket**:` pass, and the seam that let the phrase
    quoted in unrelated prose stand in for the bullet itself.
    """
    problems = []
    for name, rx, head in _REQUIRED_STRUCTURES.get(label, ()):
        if rx.search(text):
            continue
        malformed = any(line.startswith(head) for line in text.split("\n"))
        problems.append(
            f"{label}: required {name} is "
            + ("present but unparseable — a truncated claim is not a satisfied one"
               if malformed else
               "missing — deleting a claim is not a way to satisfy it"))
    return problems


def _superlative_problems(label: str, text: str, disk: dict, names: dict[str, str]) -> list[str]:
    """Values of the aggregates, read from the SAME anchored matches whose
    presence was just established. A separate search here is what allowed a
    validator to look at a different occurrence than the presence check did."""
    problems: list[str] = []
    if not disk or label not in _REQUIRED_STRUCTURES:
        return problems
    sizes = {c: len(v) for c, v in disk.items()}
    hi, lo = max(sizes.values()), min(sizes.values())

    m = _TOTAL_SKILLS_RX.search(text)
    if m and int(m.group("n")) != sum(sizes.values()):
        problems.append(f"{label}: claims {m.group('n')} skills, disk has {sum(sizes.values())}")
    m = _TOTAL_BUCKETS_RX.search(text)
    if m and int(m.group("n")) != len(disk):
        problems.append(
            f"{label}: claims {m.group('n')} category buckets, disk has {len(disk)}")
    m = _LARGEST_RX.search(text)
    if m:
        winners = {names.get(c, c) for c, n in sizes.items() if n == hi}
        if int(m.group("n")) != hi:
            problems.append(f"{label}: largest bucket says {m.group('n')}, disk has {hi}")
        if m.group("name").strip() not in winners:
            problems.append(
                f"{label}: largest bucket says {m.group('name').strip()!r}, "
                f"disk has {sorted(winners)}")
    m = _SMALLEST_RX.search(text)
    if m:
        holders = {names.get(c, c) for c, n in sizes.items() if n == lo}
        claimed = {x.strip() for x in m.group("names").split(",") if x.strip()}
        if int(m.group("n")) != lo:
            problems.append(f"{label}: smallest bucket says {m.group('n')}, disk has {lo}")
        if claimed != holders:
            problems.append(
                f"{label}: smallest buckets say {sorted(claimed)}, disk has {sorted(holders)}")
    return problems


#: Which bucket table each surface MUST carry. Declared rather than inferred
#: from what happens to be present, because inferring the structure from the
#: file is what makes an emptied structure look consistent.
_REQUIRED_BUCKET_TABLES = {
    "README.md": r"\| `skills/([a-z]+)/` \| \d+ \|",
    "skills-catalog/SKILL.md": r"\(`([a-z]+)`\) \| \d+ \|",
}


def _bucket_table_problems(label: str, text: str, disk: dict) -> list[str]:
    """A bucket table must exist, be non-empty, and name EVERY category.

    Checking only the rows present lets a deleted row pass; skipping a table
    with zero matches lets the WHOLE TABLE be deleted and still pass. Both are
    the same mistake — treating an absent structure as a satisfied one — and it
    is spelled here exactly once so a third structure cannot reintroduce it.
    """
    problems = []
    required = _REQUIRED_BUCKET_TABLES.get(label)
    if required is None:
        return problems
    listed = set(re.findall(required, text))
    if not listed:
        problems.append(
            f"{label}: the bucket table is missing or has no rows — an absent table is "
            "not a consistent one")
        return problems
    for category in sorted(set(disk) - listed):
        problems.append(f"{label}: bucket table omits category `{category}`")
    for category in sorted(listed - set(disk)):
        problems.append(f"{label}: bucket table lists `{category}`, not on disk")
    return problems


def _canonical_aggregates(disk: dict, names: dict[str, str]) -> dict[str, str]:
    """The correct text of every aggregate bullet, derived from disk."""
    sizes = {c: len(v) for c, v in disk.items()}
    hi, lo = max(sizes.values()), min(sizes.values())
    top = sorted(names.get(c, c) for c, n in sizes.items() if n == hi)[0]
    bottom = ", ".join(sorted(names.get(c, c) for c, n in sizes.items() if n == lo))
    return {
        "**Total skills** aggregate": f"- **Total skills**: {sum(sizes.values())}",
        "**Total category buckets** aggregate": f"- **Total category buckets**: {len(disk)}",
        "**Largest bucket** aggregate": f"- **Largest bucket**: {top} ({hi})",
        "**Smallest buckets** aggregate": f"- **Smallest buckets** ({lo}): {bottom}",
    }


def _fix_aggregates(label: str, text: str, disk: dict, names: dict[str, str]) -> str:
    """Repair every declared aggregate: wrong value, truncated, or absent.

    One path for all three, because they were three paths that disagreed. A
    line the regex matches is REPLACED in place, keeping its position; a line
    that does not match is deleted and the canonical form inserted among the
    bold bullets. With no `## Aggregates` block there is no non-arbitrary place
    for it, so --fix declines and `check` keeps reporting it rather than
    inventing a location.
    """
    if not disk or label not in _REQUIRED_STRUCTURES:
        return text
    canonical = _canonical_aggregates(disk, names)
    for name, rx, head in _REQUIRED_STRUCTURES[label]:
        want = canonical.get(name)
        if want is None:
            continue
        if rx.search(text):
            text = rx.sub(lambda _m, w=want: w, text, count=1)
            continue
        text = "\n".join(l for l in text.split("\n") if not l.startswith(head))
        block = re.search(r"^## Aggregates\n+", text, re.M)
        if not block:
            continue
        tail = text[block.end():]
        bullets = re.match(r"(?:- \*\*.*\n)*", tail)
        at = block.end() + (bullets.end() if bullets else 0)
        text = text[:at] + want + "\n" + text[at:]
    return text


def _unverified_count_claims(text: str) -> list[str]:
    """Lines that state a number about skills in a form this linter does not
    recognise.

    Without this, a count the patterns happen not to cover is not "allowed" —
    it is UNSEEN, and the linter reports the file consistent while the number is
    wrong. That is the exact failure this whole script exists to end, so an
    unrecognised claim is reported rather than skipped.

    Measured: README carried "90 Tier-2 skills" and the inventory
    "**Total skills**: 78" while both also stated the correct 93 elsewhere, and
    an earlier version of this linter called both files consistent.
    """
    unverified = []
    for lineno, line in enumerate(text.split("\n"), 1):
        # A table row is NOT exempt. Only the parts of it that something else
        # verifies are removed — the bucket-count cells and the skill-name cell
        # — and whatever text remains is scanned like any prose. Exempting every
        # `|` line wholesale made "| Foo | We ship 999 skills |" invisible, the
        # same absent-check-reads-as-passing mistake as an emptied table.
        if line.startswith("|"):
            line = re.sub(r"\| `skills/[a-z]+/` \| \d+ \|", "", line)
            line = re.sub(r"\(`[a-z]+`\) \| \d+ \|", "", line)
            line = re.sub(r"^\| \[?`[a-z0-9-]+`\]?(\([^)]*\))?", "", line)
        # Gated on the vocabulary of DERIVED FACTS, not on the word "skill".
        # Gating on "skill" is why "**Total category buckets**: 22" and
        # "**Largest bucket**: … (7)" were invisible: neither line says it.
        if not re.search(rf"\b{_FACT_WORDS}\b", line, re.IGNORECASE):
            continue
        residue = line
        for form in _TOTAL_FORMS + _BUCKET_TOTAL_FORMS:
            residue = re.sub(form, "", residue)
        residue = _LARGEST_RX.sub("", residue)
        residue = _SMALLEST_RX.sub("", residue)
        for allowed in _NOT_A_SKILL_COUNT:
            residue = re.sub(allowed, "", residue)
        residue = re.sub(r"`[^`]*`", "", residue)          # inline code
        residue = re.sub(r"https?://\S+", "", residue)     # urls carry digits
        if _states_a_quantity(residue):
            unverified.append(f"line {lineno}: {line.strip()[:90]}")
    return unverified


def check(disk: dict, surfaces: dict[str, tuple[Path, list[_Section], str]]) -> list[str]:
    problems: list[str] = []
    total = sum(len(v) for v in disk.values())
    # Human bucket labels come from the inventory's own headings.
    names = _labels(surfaces["skills-inventory.md"][2]) if "skills-inventory.md" in surfaces else {}
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
        for declared in _declared_counts(text, _BUCKET_TOTAL_FORMS):
            if declared != len(disk):
                problems.append(
                    f"{label}: claims {declared} category buckets, disk has {len(disk)}")
                break
        problems += _missing_structure_problems(label, text)
        problems += _superlative_problems(label, text, disk, names)
        problems += _bucket_table_problems(label, text, disk)
        for claim in _unverified_count_claims(text):
            problems.append(
                f"{label}: unrecognised count claim, this linter cannot verify it — {claim}")
        # NOT guarded on `if sections` — a surface whose tables were all deleted
        # parses as zero sections, and skipping the diagnostic there would let
        # an empty catalog with correct totals pass as consistent.
        if label in _ROW_SURFACES:
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
    names = _labels(inventory)
    inventory = _rebuild(inventory, _sections(inventory, _INV_HEADING, _INV_ROW), disk,
                         lambda c, n, d, a: f"| `{n}`{a} | {d} |")
    inventory = _fix_aggregates("skills-inventory.md", inventory, disk, names)
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
        remaining = unreadable_manifests() + check(discover(), _load())
        if remaining:
            print("✗ --fix could not reconcile:", file=sys.stderr)
            for line in remaining:
                print(f"  - {line}", file=sys.stderr)
            return 1
        print(f"✓ catalog rewritten from disk ({total} skills, {len(disk)} buckets)")
        return 0

    problems = unreadable_manifests() + check(disk, _load())
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
