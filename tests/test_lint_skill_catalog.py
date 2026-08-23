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
