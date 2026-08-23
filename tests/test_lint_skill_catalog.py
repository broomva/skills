"""Tests for scripts/lint_skill_catalog.py.

Every case drives the REAL `check`/`fix`/`discover` against a fixture repo on
disk. None of them reconstructs what the linter is expected to output — a test
that mirrors the implementation only ever tests the mirror, and would keep
passing while the two drifted apart.

The fixture is deliberately tiny (two buckets, a handful of skills) so that a
count assertion names a number a reader can verify by eye.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_skill_catalog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("lint_skill_catalog", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lint_skill_catalog"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def lint():
    return _load_module()


SKILLS = {
    "governance": {"alpha": "Alpha does governance things.",
                   "beta": "Beta does other governance things."},
    "tooling": {"gamma": "Gamma is a tool.",
                "delta": "Delta is another tool."},
}


def _readme(rows: dict[str, list[str]], total: int, buckets: dict[str, int]) -> str:
    out = [f"**{total} skills** organized into **2 single-noun category buckets**.", ""]
    for cat, lines in rows.items():
        out += [f"### {cat.title()} — `skills/{cat}/`", "", "| Skill | What it does |",
                "|---|---|"] + lines + [""]
    out += [f"The {total} skills bucket into 2 single-noun categories:", "",
            "| Category | Bucket | Count |", "|---|---|---|"]
    out += [f"| {c.title()} | `skills/{c}/` | {n} |" for c, n in buckets.items()]
    return "\n".join(out) + "\n"


def _inventory(rows: dict[str, list[str]], total: int, buckets: dict[str, int]) -> str:
    out = [f"> {total} skills across 2 category buckets.", ""]
    for cat, lines in rows.items():
        out += [f"## {cat.title()} — `skills/{cat}/` ({buckets[cat]})", "",
                "| Skill | What it does |", "|---|---|"] + lines + [""]
    return "\n".join(out) + "\n"


def _catalog_skill(total: int, buckets: dict[str, int]) -> str:
    out = ["---", "name: skills-catalog", "description: Catalog.", "---", "",
           f"Canonical reference inventory of the {total} agent skills.", "",
           "| Category | Count | Key skills |", "|---|---|---|"]
    out += [f"| {c.title()} (`{c}`) | {n} | x, y |" for c, n in buckets.items()]
    # An unrelated number that must survive every rewrite.
    out += ["", '> the video dataset still reflects the legacy "broader-ecosystem"',
            "> catalog (86 rows, 15 marketing domains).", ""]
    return "\n".join(out) + "\n"


def _build(tmp_path: Path, lint, *, readme: str, inventory: str, catalog: str,
           skills: dict = SKILLS) -> Path:
    """Write a fixture repo and point the module's path globals at it."""
    for cat, names in skills.items():
        for name, desc in names.items():
            d = tmp_path / "skills" / cat / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {desc}\n---\n\nbody\n", encoding="utf-8")
    inv = tmp_path / "skills/tooling/skills-catalog/references"
    inv.mkdir(parents=True, exist_ok=True)
    (inv / "skills-inventory.md").write_text(inventory, encoding="utf-8")
    (tmp_path / "skills/tooling/skills-catalog/SKILL.md").write_text(catalog, encoding="utf-8")
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")

    lint._SKILLS_DIR = tmp_path / "skills"
    lint._README = tmp_path / "README.md"
    lint._INVENTORY = inv / "skills-inventory.md"
    lint._CATALOG_SKILL = tmp_path / "skills/tooling/skills-catalog/SKILL.md"
    return tmp_path


def _rrow(cat, name, desc, annot=""):
    return f"| [`{name}`](skills/{cat}/{name}/){annot} | {desc} |"


def _irow(name, desc, annot=""):
    return f"| `{name}`{annot} | {desc} |"


# skills-catalog itself lives in the tooling bucket of the fixture repo, so the
# fixture must list it or every case would trip a spurious "missing row".
def _consistent(tmp_path, lint, **kw):
    skills = {
        "governance": dict(SKILLS["governance"]),
        "tooling": dict(SKILLS["tooling"], **{"skills-catalog": "Catalog."}),
    }
    buckets = {c: len(v) for c, v in skills.items()}
    total = sum(buckets.values())
    rrows = {c: [_rrow(c, n, d) for n, d in sorted(v.items())] for c, v in skills.items()}
    irows = {c: [_irow(n, d) for n, d in sorted(v.items())] for c, v in skills.items()}
    return _build(tmp_path, lint,
                  readme=kw.get("readme") or _readme(rrows, total, buckets),
                  inventory=kw.get("inventory") or _inventory(irows, total, buckets),
                  catalog=kw.get("catalog") or _catalog_skill(total, buckets),
                  skills=skills), skills, buckets, total, rrows, irows


class TestDiscover:
    def test_finds_depth_two_skills_only(self, tmp_path, lint):
        _consistent(tmp_path, lint)
        nested = tmp_path / "skills/tooling/gamma/skills/subskill"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text("---\nname: subskill\ndescription: d\n---\n")
        disk = lint.discover(lint._SKILLS_DIR)
        assert "subskill" not in disk.get("tooling", {})
        assert sum(len(v) for v in disk.values()) == 5

    def test_reads_the_description_from_frontmatter(self, tmp_path, lint):
        _consistent(tmp_path, lint)
        assert lint.discover(lint._SKILLS_DIR)["governance"]["alpha"] == "Alpha does governance things."


class TestCheckAcceptsAConsistentCatalog:
    def test_a_consistent_catalog_reports_nothing(self, tmp_path, lint):
        """POSITIVE CONTROL. Every case below asserts that some problem IS
        reported; if `check` returned a complaint unconditionally they would all
        pass while the linter was useless. This one must come back empty."""
        _consistent(tmp_path, lint)
        assert lint.check(lint.discover(lint._SKILLS_DIR), lint._load()) == []


class TestCheckCatchesDrift:
    def test_a_skill_with_no_row_is_reported(self, tmp_path, lint):
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        rrows["governance"] = [r for r in rrows["governance"] if "`beta`" not in r]
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets))
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("`beta`" in p and "no row" in p for p in problems), problems

    def test_a_row_with_no_skill_is_reported(self, tmp_path, lint):
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        rrows["governance"].append(_rrow("governance", "ghost", "Was deleted."))
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets))
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("`ghost`" in p and "not on disk" in p for p in problems), problems

    def test_a_stray_bullet_inside_a_table_is_reported(self, tmp_path, lint):
        """The format-drift case. `attempt-audit` shipped like this on main: the
        skill IS named, so a naive 'is it mentioned' check passes, but the table
        render breaks and every `| \\`x\\` |` count misses it."""
        _, _s, buckets, total, _r, irows = _consistent(tmp_path, lint)
        irows["tooling"] = [r for r in irows["tooling"] if "`delta`" not in r]
        irows["tooling"].insert(1, "- **`delta`** — Delta is another tool.")
        _consistent(tmp_path, lint, inventory=_inventory(irows, total, buckets))
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("`delta`" in p and "bullet" in p for p in problems), problems

    def test_a_wrong_total_is_reported(self, tmp_path, lint):
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        _consistent(tmp_path, lint, readme=_readme(rrows, total + 7, buckets))
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any(f"claims {total + 7}" in p for p in problems), problems

    def test_a_wrong_bucket_count_is_reported(self, tmp_path, lint):
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        wrong = dict(buckets, governance=buckets["governance"] + 3)
        _consistent(tmp_path, lint, readme=_readme(rrows, total, wrong))
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("governance" in p and "bucket" in p for p in problems), problems


class TestFix:
    def test_fix_adds_the_missing_row_and_check_then_passes(self, tmp_path, lint):
        _, _s, buckets, total, rrows, irows = _consistent(tmp_path, lint)
        rrows["governance"] = [r for r in rrows["governance"] if "`beta`" not in r]
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets))
        lint.fix(lint.discover(lint._SKILLS_DIR))
        assert lint.check(lint.discover(lint._SKILLS_DIR), lint._load()) == []
        assert "`beta`" in lint._README.read_text()

    def test_fix_does_not_duplicate_rows_after_a_stray_bullet(self, tmp_path, lint):
        """The regression this linter was nearly shipped with. Scanning only a
        CONTIGUOUS run of table rows stops at the malformed line, so every row
        below it looks absent and --fix appends a second copy of each."""
        _, _s, buckets, total, rrows, irows = _consistent(tmp_path, lint)
        # bullet FIRST, two real rows after it — those two must not be doubled
        irows["tooling"] = ["- **`delta`** — Delta is another tool.",
                            _irow("gamma", "Gamma is a tool."),
                            _irow("skills-catalog", "Catalog.")]
        _consistent(tmp_path, lint, inventory=_inventory(irows, total, buckets))
        lint.fix(lint.discover(lint._SKILLS_DIR))
        text = lint._INVENTORY.read_text()
        for name in ("gamma", "delta", "skills-catalog"):
            assert text.count(f"| `{name}`") == 1, f"{name} duplicated:\n{text}"
        assert lint.check(lint.discover(lint._SKILLS_DIR), lint._load()) == []

    def test_fix_preserves_a_name_cell_annotation(self, tmp_path, lint):
        """`**(vendored)**` on parallax states that the copy is gated
        byte-identical by parallax-sync. A rewrite that drops it removes the
        provenance another gate depends on."""
        _, _s, buckets, total, rrows, irows = _consistent(tmp_path, lint)
        rrows["tooling"] = [_rrow("tooling", "gamma", "Gamma is a tool.", " **(vendored)**")
                            if "`gamma`" in r else r for r in rrows["tooling"]]
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets))
        lint.fix(lint.discover(lint._SKILLS_DIR))
        assert "**(vendored)**" in lint._README.read_text()

    def test_fix_leaves_an_unrelated_count_alone(self, tmp_path, lint):
        """skills-catalog/SKILL.md carries "(86 rows, 15 marketing domains)"
        about a different, legacy catalog. A blanket replace of the old total
        would corrupt it."""
        _consistent(tmp_path, lint)
        lint.fix(lint.discover(lint._SKILLS_DIR))
        assert "(86 rows, 15 marketing domains)" in lint._CATALOG_SKILL.read_text()

    def test_fix_keeps_an_authored_description_rather_than_regenerating_it(self, tmp_path, lint):
        _, _s, buckets, total, rrows, irows = _consistent(tmp_path, lint)
        rrows["governance"] = [_rrow("governance", "alpha", "A hand-written wording.")
                               if "`alpha`" in r else r for r in rrows["governance"]]
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets))
        lint.fix(lint.discover(lint._SKILLS_DIR))
        assert "A hand-written wording." in lint._README.read_text()

    def test_fix_removes_a_row_whose_skill_is_gone(self, tmp_path, lint):
        _, _s, buckets, total, rrows, irows = _consistent(tmp_path, lint)
        rrows["governance"].append(_rrow("governance", "ghost", "Was deleted."))
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets))
        lint.fix(lint.discover(lint._SKILLS_DIR))
        assert "`ghost`" not in lint._README.read_text()


class TestExitCodes:
    def test_main_exits_1_on_drift_and_0_when_clean(self, tmp_path, lint, monkeypatch):
        _, _s, buckets, total, rrows, irows = _consistent(tmp_path, lint)
        rrows["governance"] = [r for r in rrows["governance"] if "`beta`" not in r]
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets))
        assert lint.main([]) == 1
        assert lint.main(["--fix"]) == 0
        assert lint.main([]) == 0


class TestCountsInEveryForm:
    """The linter shipped a review round blind to two real counts.

    README carried "90 Tier-2 skills" and the inventory "**Total skills**: 78"
    while both also stated the correct 93 elsewhere, and `check` called them
    consistent — a count linter false-green on drifted counts, which is the
    failure it exists to end.

    The suite could not catch it because the fixtures only ever contained the
    count FORMS the implementation already handled. That is the mirror problem
    one level down: not a test that mirrors the code, but a fixture that does.
    So the first case below asserts the general property — an unrecognised form
    is REPORTED, not skipped — rather than enumerating more forms.
    """

    def test_an_unrecognised_count_form_is_reported_not_ignored(self, tmp_path, lint):
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        readme = _readme(rrows, total, buckets) + "\nWe ship 47 flagship skills this quarter.\n"
        _consistent(tmp_path, lint, readme=readme)
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("unrecognised count claim" in p and "47" in p for p in problems), problems

    def test_a_tier_2_total_is_verified(self, tmp_path, lint):
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        readme = f"A monorepo of {total + 9} Tier-2 skills.\n\n" + _readme(rrows, total, buckets)
        _consistent(tmp_path, lint, readme=readme)
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any(f"claims {total + 9}" in p for p in problems), problems

    def test_a_total_skills_bullet_is_verified(self, tmp_path, lint):
        _, _s, buckets, total, rrows, irows = _consistent(tmp_path, lint)
        inv = _inventory(irows, total, buckets) + "\n- **Total skills**: 78\n"
        _consistent(tmp_path, lint, inventory=inv)
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("claims 78" in p for p in problems), problems

    def test_a_wrong_bucket_TOTAL_is_verified(self, tmp_path, lint):
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        readme = _readme(rrows, total, buckets) + "\nOrganised into 9 category buckets.\n"
        _consistent(tmp_path, lint, readme=readme)
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("9 category buckets" in p or "claims 9 category" in p for p in problems), problems

    def test_fix_repairs_every_form_including_the_late_added_ones(self, tmp_path, lint):
        _, _s, buckets, total, rrows, irows = _consistent(tmp_path, lint)
        readme = f"A monorepo of {total + 9} Tier-2 skills.\n\n" + _readme(rrows, total, buckets)
        inv = _inventory(irows, total, buckets) + "\n- **Total skills**: 78\n"
        _consistent(tmp_path, lint, readme=readme, inventory=inv)
        lint.fix(lint.discover(lint._SKILLS_DIR))
        assert lint.check(lint.discover(lint._SKILLS_DIR), lint._load()) == []
        assert f"{total} Tier-2 skills" in lint._README.read_text()
        assert f"**Total skills**: {total}" in lint._INVENTORY.read_text()


class TestSurfaceStructureHoles:
    def test_a_surface_with_every_table_deleted_is_reported(self, tmp_path, lint):
        """Zero sections parse when the tables are gone. Guarding the
        missing-category diagnostic on `if sections:` let an empty catalog with
        correct totals pass as consistent."""
        _, _s, buckets, total, _r, irows = _consistent(tmp_path, lint)
        _consistent(tmp_path, lint, readme=f"**{total} skills** in 2 category buckets.\n")
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("no section for category" in p for p in problems), problems

    def test_a_derived_description_containing_a_pipe_is_escaped(self, tmp_path, lint):
        """An unescaped `|` ends the cell early, rendering a broken row that
        this file's own regex still re-parses — malformed and self-perpetuating."""
        tmp, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        d = tmp / "skills/governance/piped"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            "---\nname: piped\ndescription: Routes A | B | C.\n---\n", encoding="utf-8")
        lint.fix(lint.discover(lint._SKILLS_DIR))
        row = [l for l in lint._README.read_text().split("\n") if "`piped`" in l][0]
        # Split on UNESCAPED pipes only: a well-formed two-column row yields
        # ['', name-cell, description-cell, ''].
        cells = re.split(r"(?<!\\)\|", row)
        assert len(cells) == 4, f"cell boundaries broken ({len(cells)}): {row!r}"
        assert "\\|" in row, row

    def test_the_annotation_lands_on_its_own_row_not_merely_in_the_file(self, tmp_path, lint):
        """Asserting the marker is somewhere in the document would pass if --fix
        moved it onto the wrong skill."""
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        rrows["tooling"] = [_rrow("tooling", "gamma", "Gamma is a tool.", " **(vendored)**")
                            if "`gamma`" in r else r for r in rrows["tooling"]]
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets))
        lint.fix(lint.discover(lint._SKILLS_DIR))
        lines = lint._README.read_text().split("\n")
        gamma = [l for l in lines if "`gamma`" in l][0]
        others = [l for l in lines if "**(vendored)**" in l and "`gamma`" not in l]
        assert "**(vendored)**" in gamma, gamma
        assert not others, others


class TestTheTighteningDoesNotOvershoot:
    """Bidirectional proof for the unrecognised-count scan.

    Making a permissive check strict is the classic way to trade a false-green
    for a false-red: the scan now flags any number near the word "skill", and
    the real README and inventory are full of numbers that are not skill counts
    — a CLI version, an upstream PR number, an output filename, the directory
    depth, a legacy catalog's row count.

    Every line below is real prose from the surfaces this linter governs, and
    every one of them must come back CLEAN. Without these, the previous class
    could be satisfied by a scan that simply reports everything.
    """

    LEGITIMATE = [
        "> **Note:** **requires skills.sh CLI ≥ v1.5.8** (PR #1272), which discovers buckets.",
        "npx remotion render SkillsShowcase out/skills-showcase.mp4",
        "Skills are bucketed by single-noun **category** at `skills/<category>/<name>/` (depth-2).",
        '> the video dataset still reflects the legacy "broader-ecosystem" catalog',
        "> catalog (86 rows, 15 marketing domains). The canonical inventory above",
        "Install any skill path-independently: `npx skills add broomva/skills --skill <name>`.",
        "| `_shared/` | (reserved) shared utilities used by multiple Tier-2 skills |",
        # depth-3 tripped the scan when only depth-2 was allowlisted
        "No flag is needed (that's only for depth-3+); buckets are exactly one level.",
        "The [`skills-showcase`](skills-showcase/) tool generates a Remotion video (1080x1920).",
        # The trailing DATE survives every subtraction and is clean only because
        # it sits far from any fact word — the one line in the corpus that makes
        # the proximity window load-bearing rather than decorative.
        ("> 93 skills across 22 category buckets, mirroring the `skills/<category>/` directory "
         "layout. Regenerated from the README discovery surface (canonical). "
         "Last updated: 2026-08-18."),
    ]

    @pytest.mark.parametrize("line", LEGITIMATE)
    def test_real_prose_is_not_flagged_as_an_unverifiable_count(self, lint, line):
        assert lint._unverified_count_claims(line) == [], line

    def test_a_genuinely_unverifiable_count_still_is_flagged(self, lint):
        """POSITIVE CONTROL for the seven cases above: if the scan were disabled
        outright they would all pass while it caught nothing."""
        assert lint._unverified_count_claims("We ship 47 flagship skills this quarter.")

    def test_the_allowlist_is_load_bearing_not_decorative(self, lint):
        """Each allowlist entry must actually be why its line is clean — remove
        the allowlist and the real prose starts failing."""
        saved = lint._NOT_A_SKILL_COUNT
        lint._NOT_A_SKILL_COUNT = ()
        try:
            flagged = [l for l in self.LEGITIMATE if lint._unverified_count_claims(l)]
        finally:
            lint._NOT_A_SKILL_COUNT = saved
        assert flagged, "no line depends on the allowlist — it is dead configuration"


class TestNonSkillContentInASection:
    """A category section can legitimately carry more than the skill table — a
    note, a platform matrix, another table entirely. Round 1 of the cross-model
    review reported that `--fix` DELETES it; that turned out to be wrong (it is
    preserved), but the blank lines inside it were being collapsed, which runs a
    paragraph into the table that follows it.
    """

    def _with_extra(self, tmp_path, lint):
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        rrows["governance"] = rrows["governance"] + [
            "", "Supported platforms:", "", "| Platform | Status |", "|---|---|",
            "| Linux | yes |", "| macOS | yes |"]
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets))
        lint.fix(lint.discover(lint._SKILLS_DIR))
        return lint._README.read_text()

    def test_a_nested_non_skill_table_survives_fix(self, lint, tmp_path):
        text = self._with_extra(tmp_path, lint)
        for probe in ("Supported platforms:", "| Platform | Status |",
                      "| Linux | yes |", "| macOS | yes |"):
            assert probe in text, f"lost: {probe!r}\n{text}"

    def test_the_blank_line_before_a_nested_table_survives(self, lint, tmp_path):
        """Without it the paragraph and its table render as one run."""
        text = self._with_extra(tmp_path, lint)
        assert "Supported platforms:\n\n| Platform | Status |" in text, text

    def test_the_skill_rows_are_still_rebuilt_around_it(self, lint, tmp_path):
        """POSITIVE CONTROL: preserving the extra content must not come at the
        cost of the table this linter exists to maintain."""
        text = self._with_extra(tmp_path, lint)
        assert "| [`alpha`](skills/governance/alpha/) |" in text
        assert "| [`beta`](skills/governance/beta/) |" in text
        assert lint.check(lint.discover(lint._SKILLS_DIR), lint._load()) == []


AGGREGATES = ("\n---\n\n## Aggregates\n\n"
              "- **Total skills**: {total}\n"
              "- **Total category buckets**: {nbuckets}\n"
              "- **Largest bucket**: {largest} ({hi})\n"
              "- **Smallest buckets** ({lo}): {smallest}\n")


class TestAggregatesThatNeverSayTheWordSkill:
    """The inventory shipped `**Largest bucket**: Orchestration & autonomy (7)`
    while tooling held 10 and orchestration held 8 — name and number both wrong,
    and invisible for two review rounds because the scan was gated on the word
    "skill" and that line does not contain it. These are derived facts and are
    checked as such.
    """

    def _inv_with(self, tmp_path, lint, **over):
        _, _s, buckets, total, _r, irows = _consistent(tmp_path, lint)
        # tooling has 3 (gamma, delta, skills-catalog); governance has 2
        base = dict(total=total, nbuckets=len(buckets), largest="Tooling",
                    hi=max(buckets.values()), lo=min(buckets.values()), smallest="Governance")
        base.update(over)
        inv = _inventory(irows, total, buckets) + AGGREGATES.format(**base)
        _consistent(tmp_path, lint, inventory=inv)
        return lint.check(lint.discover(lint._SKILLS_DIR), lint._load())

    def test_a_consistent_aggregates_block_reports_nothing(self, tmp_path, lint):
        """POSITIVE CONTROL for this whole class."""
        assert self._inv_with(tmp_path, lint) == []

    def test_a_wrong_largest_count_is_reported(self, tmp_path, lint):
        problems = self._inv_with(tmp_path, lint, hi=7)
        assert any("largest bucket says 7" in p for p in problems), problems

    def test_a_wrong_largest_name_is_reported(self, tmp_path, lint):
        problems = self._inv_with(tmp_path, lint, largest="Governance")
        assert any("largest bucket says 'Governance'" in p for p in problems), problems

    def test_a_wrong_smallest_count_is_reported(self, tmp_path, lint):
        problems = self._inv_with(tmp_path, lint, lo=99)
        assert any("smallest bucket says 99" in p for p in problems), problems

    def test_a_wrong_total_category_buckets_is_reported(self, tmp_path, lint):
        problems = self._inv_with(tmp_path, lint, nbuckets=999)
        assert any("999 category buckets" in p for p in problems), problems

    def test_fix_repairs_the_superlatives(self, tmp_path, lint):
        self._inv_with(tmp_path, lint, hi=7, largest="Governance")
        lint.fix(lint.discover(lint._SKILLS_DIR))
        assert lint.check(lint.discover(lint._SKILLS_DIR), lint._load()) == []
        assert "**Largest bucket**: Tooling (3)" in lint._INVENTORY.read_text()


class TestCountsAnywhereNotJustInProse:
    def test_a_count_inside_a_heading_is_reported(self, tmp_path, lint):
        """Headings were skipped as 'checked structurally', so
        `## Catalog of 999 skills` passed."""
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        _consistent(tmp_path, lint,
                    readme=_readme(rrows, total, buckets) + "\n## Catalog of 999 skills\n")
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("999" in p for p in problems), problems


class TestBucketTableCompleteness:
    def _catalog_with(self, tmp_path, lint, buckets_override):
        _, _s, buckets, total, _r, _i = _consistent(tmp_path, lint)
        _consistent(tmp_path, lint, catalog=_catalog_skill(total, buckets_override))
        return lint.check(lint.discover(lint._SKILLS_DIR), lint._load())

    def test_a_complete_bucket_table_reports_nothing(self, tmp_path, lint):
        """POSITIVE CONTROL for the two below."""
        _, _s, buckets, _t, _r, _i = _consistent(tmp_path, lint)
        assert self._catalog_with(tmp_path, lint, buckets) == []

    def test_a_deleted_bucket_row_is_reported(self, tmp_path, lint):
        _, _s, buckets, _t, _r, _i = _consistent(tmp_path, lint)
        problems = self._catalog_with(tmp_path, lint, {"governance": buckets["governance"]})
        assert any("omits category `tooling`" in p for p in problems), problems

    def test_a_bucket_row_for_a_category_not_on_disk_is_reported(self, tmp_path, lint):
        _, _s, buckets, _t, _r, _i = _consistent(tmp_path, lint)
        problems = self._catalog_with(tmp_path, lint, dict(buckets, ghostcat=4))
        assert any("`ghostcat`" in p and "not on disk" in p for p in problems), problems


class TestBothRowSurfacesAreChecked:
    def test_deleting_every_table_in_the_INVENTORY_is_reported(self, tmp_path, lint):
        """The README-only version of this test let `_ROW_SURFACES` be narrowed
        to ("README.md",) without a single failure — a surviving mutation the
        cross-model round named explicitly."""
        _, _s, buckets, total, _r, _i = _consistent(tmp_path, lint)
        _consistent(tmp_path, lint,
                    inventory=f"> {total} skills across {len(buckets)} category buckets.\n")
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("skills-inventory.md" in p and "no section for category" in p
                   for p in problems), problems


class TestTheTwoPropertiesTheSweepFoundUnproven:
    """A mutation sweep over the suite above left two mutants alive. Both were
    tests passing for the wrong reason, not missing behaviour — the exact case
    where a green suite certifies a property it never exercises.
    """

    def test_a_wrong_smallest_NAME_SET_is_reported_at_the_correct_count(self, tmp_path, lint):
        """The existing smallest-bucket test passes a wrong COUNT, which trips
        the count branch and leaves the set comparison unexercised. Hold the
        count correct so only the set can fail."""
        _, _s, buckets, total, _r, irows = _consistent(tmp_path, lint)
        inv = _inventory(irows, total, buckets) + AGGREGATES.format(
            total=total, nbuckets=len(buckets), largest="Tooling", hi=max(buckets.values()),
            lo=min(buckets.values()), smallest="Tooling")     # correct count, WRONG set
        _consistent(tmp_path, lint, inventory=inv)
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("smallest buckets say" in p for p in problems), problems

    def test_a_bucket_claim_that_never_says_skill_is_still_scanned(self, tmp_path, lint):
        """Every other aggregate case is caught by an ANCHORED form, so the
        widened fact vocabulary was load-bearing nowhere and could be narrowed
        back to the word "skill" without failing a test. This line mentions a
        bucket and a number in a form the linter does not recognise, and says
        "skill" nowhere — it is verifiable only through the widened gate."""
        _, _s, buckets, total, _r, irows = _consistent(tmp_path, lint)
        inv = _inventory(irows, total, buckets) + "\n- **Median bucket size**: 4\n"
        _consistent(tmp_path, lint, inventory=inv)
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("Median bucket size" in p for p in problems), problems

    def test_that_same_line_is_clean_once_it_states_a_derived_fact(self, lint):
        """POSITIVE CONTROL: the gate must widen coverage, not simply reject
        every line containing a number and the word bucket."""
        assert lint._unverified_count_claims("- **Total category buckets**: 22") == []


class TestEveryBucketPhrasingIsVerified:
    def test_single_noun_category_buckets_is_a_verified_form(self, tmp_path, lint):
        """`skills-catalog/SKILL.md` says "organized into 22 single-noun category
        buckets". No form covered that exact phrasing, and the scan surfaced it
        as unverifiable rather than passing it — the design working. It is a
        real derived count, so it is now VERIFIED rather than allowlisted."""
        _, _s, buckets, total, _r, _i = _consistent(tmp_path, lint)
        catalog = _catalog_skill(total, buckets) + \
            "\nOrganized into 99 single-noun category buckets.\n"
        _consistent(tmp_path, lint, catalog=catalog)
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("99 category buckets" in p for p in problems), problems
        assert not any("unrecognised" in p for p in problems), problems


class TestTheProximityWindow:
    """No line in the real corpus pins the window: every legitimate number is
    clean because it gets SUBTRACTED, not because of distance. A mutation
    setting the window to 100000 therefore survived the whole suite. The bound
    is real behaviour, so it is tested directly rather than left to a corpus
    that happens not to exercise it.
    """

    def test_a_number_far_from_any_fact_word_is_not_a_quantity(self, lint):
        far = "buckets " + ("filler " * 20) + "2026"
        assert not lint._states_a_quantity(far), far

    def test_a_number_beside_a_fact_word_is_a_quantity(self, lint):
        """POSITIVE CONTROL: without it the case above is satisfied by a
        function that always returns False."""
        assert lint._states_a_quantity("Median bucket size: 4")

    def test_the_window_is_the_reason_and_not_an_accident(self, lint):
        """Same string, both sides of the boundary."""
        near = "buckets " + ("x" * 10) + " 2026"
        far = "buckets " + ("x" * 200) + " 2026"
        assert lint._states_a_quantity(near)
        assert not lint._states_a_quantity(far)


class TestAnAbsentStructureIsNotAConsistentOne:
    """The invariant, stated once: a structure that is missing or empty must be
    a finding, never a pass. It was got wrong twice — `if sections:` for
    category tables, then `if not listed: continue` for bucket tables — which is
    the shape where each new branch costs another review round. Both branches
    are covered here so a third cannot be added quietly.
    """

    def test_an_emptied_bucket_table_is_reported(self, tmp_path, lint):
        _, _s, buckets, total, _r, _i = _consistent(tmp_path, lint)
        gutted = "\n".join(l for l in _catalog_skill(total, buckets).split("\n")
                           if not re.match(r"\| \w+ \(`[a-z]+`\) \|", l))
        _consistent(tmp_path, lint, catalog=gutted)
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("missing or has no rows" in p for p in problems), problems

    def test_an_emptied_readme_bucket_table_is_reported(self, tmp_path, lint):
        """The same invariant in the OTHER surface — the branch that would
        otherwise be the next review round."""
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        gutted = "\n".join(l for l in _readme(rrows, total, buckets).split("\n")
                           if not re.match(r"\| \w+ \| `skills/[a-z]+/` \| \d+ \|", l))
        _consistent(tmp_path, lint, readme=gutted)
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("missing or has no rows" in p for p in problems), problems

    def test_a_complete_bucket_table_is_still_clean(self, lint, tmp_path):
        """POSITIVE CONTROL for both: the check must distinguish absent from
        present, not merely always complain."""
        _consistent(tmp_path, lint)
        assert lint.check(lint.discover(lint._SKILLS_DIR), lint._load()) == []


class TestClaimsInsideTableRows:
    def test_a_count_claim_in_a_table_cell_is_reported(self, tmp_path, lint):
        """Every `|` line was exempted as 'checked structurally', so a claim in
        a free-text cell was invisible. Only the structurally-verified cells are
        removed now; the rest is scanned like prose."""
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        _consistent(tmp_path, lint,
                    readme=_readme(rrows, total, buckets) + "\n| Thing | We ship 999 skills |\n")
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("999" in p for p in problems), problems

    def test_a_normal_skill_row_is_not_flagged(self, tmp_path, lint):
        """POSITIVE CONTROL: scanning cells must not flag the catalog's own
        rows, or the linter is unusable on the file it governs."""
        _consistent(tmp_path, lint)
        assert lint.check(lint.discover(lint._SKILLS_DIR), lint._load()) == []

    def test_a_loose_bucket_phrasing_in_a_cell_is_verified_not_flagged(self, tmp_path, lint):
        """'inventory across all 22 buckets' is a real derived count that no
        specific form covered. It is verified, so a WRONG one is reported."""
        _, _s, buckets, total, rrows, _i = _consistent(tmp_path, lint)
        _consistent(tmp_path, lint, readme=_readme(rrows, total, buckets)
                    + "\n| Doc | Inventory across all 77 buckets |\n")
        problems = lint.check(lint.discover(lint._SKILLS_DIR), lint._load())
        assert any("77 category buckets" in p for p in problems), problems
        assert not any("unrecognised" in p for p in problems), problems


class TestFixRepairsSuperlativesInBothDirections:
    def test_fix_repairs_a_wrong_SMALLEST_aggregate(self, tmp_path, lint):
        """Deleting the smallest-branch from _fix_superlatives survived the
        sweep: checking it was tested, FIXING it was not."""
        _, _s, buckets, total, _r, irows = _consistent(tmp_path, lint)
        inv = _inventory(irows, total, buckets) + AGGREGATES.format(
            total=total, nbuckets=len(buckets), largest="Tooling", hi=max(buckets.values()),
            lo=min(buckets.values()), smallest="Tooling")     # wrong set
        _consistent(tmp_path, lint, inventory=inv)
        lint.fix(lint.discover(lint._SKILLS_DIR))
        assert lint.check(lint.discover(lint._SKILLS_DIR), lint._load()) == []
        assert "**Smallest buckets** (2): Governance" in lint._INVENTORY.read_text()
