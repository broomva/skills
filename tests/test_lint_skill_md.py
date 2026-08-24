"""Tests for `scripts/lint_skill_md.py`.

The linter this replaces was a heredoc inside the workflow, so it had no tests
at all — which is how three false greens survived in a gate that runs on every
pull request. Every "is reported" case below is paired with a control, because
a checker that reports on everything is as useless as one that reports on
nothing.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_skill_md.py"


@pytest.fixture()
def lint():
    spec = importlib.util.spec_from_file_location("lint_skill_md_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _skill(root: Path, name: str, body: bytes | str = None, dirname: str = None) -> Path:
    d = root / "skills" / "tooling" / (dirname or name)
    d.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = f"---\nname: {name}\ndescription: A description.\n---\nbody\n"
    md = d / "SKILL.md"
    md.write_bytes(body if isinstance(body, bytes) else body.encode("utf-8"))
    return md


def _run(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=cwd,
                          capture_output=True, text=True)


class TestTheControl:
    def test_a_conforming_skill_passes(self, tmp_path, lint):
        _skill(tmp_path, "good")
        assert lint.lint_skill_md(tmp_path / "skills/tooling/good/SKILL.md") == []

    def test_an_ordinary_violation_is_caught(self, tmp_path, lint):
        """Without this, every "no problems" below would be indistinguishable
        from a linter that reports nothing at all."""
        _skill(tmp_path, "bad", "---\nname: WRONG-CASE\ndescription: d\n---\n")
        assert lint.lint_skill_md(tmp_path / "skills/tooling/bad/SKILL.md")

    def test_the_real_repository_passes(self):
        """The linter must accept the tree it governs, or the tightening has
        traded a false green for a false red."""
        repo = SCRIPT.parents[1]
        r = subprocess.run([sys.executable, str(SCRIPT)], cwd=repo,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Traceback" not in r.stdout + r.stderr


class TestFencesAreExactAtBothEnds:
    """The first false green. `text.find("\\n---", 3)` accepted `---yaml` as a
    closing fence, so everything after it was silently ignored — including a
    second `name:` that the reader would reasonably expect to be checked."""

    @pytest.mark.parametrize("body,reported", [
        ("---\nname: f\ndescription: d\n---\n", False),
        ("---\nname: f\ndescription: d\n---yaml\n", True),
        ("---\nname: f\ndescription: d\n--- \n", True),
        ("---yaml\nname: f\ndescription: d\n---\n", True),
        (" ---\nname: f\ndescription: d\n---\n", True),
        ("---\nname: f\ndescription: d\n", True),
    ])
    def test_only_bare_fences_delimit_frontmatter(self, tmp_path, lint, body, reported):
        md = _skill(tmp_path, "f", body)
        problems = lint.lint_skill_md(md)
        assert bool(problems) == reported, (body, problems)

    def test_crlf_is_a_line_ending_not_a_fence_defect(self, tmp_path, lint):
        """Exact fences must not reject a well-formed CRLF manifest — the false
        red that pairs with the tightening."""
        md = _skill(tmp_path, "crlf",
                    b"---\r\nname: crlf\r\ndescription: A description.\r\n---\r\nbody\r\n")
        assert lint.lint_skill_md(md) == []


class TestEncodingIsCheckedNotPapreredOver:
    """The second false green. `errors="replace"` turned every invalid byte into
    U+FFFD, so a mangled manifest "parsed" and the gate reported conformance."""

    def test_invalid_utf8_in_the_frontmatter_is_reported(self, tmp_path, lint):
        md = _skill(tmp_path, "badenc",
                    b"---\nname: badenc\ndescription: \xff\xfe\n---\n")
        assert any("not valid UTF-8" in p for p in lint.lint_skill_md(md))

    def test_invalid_utf8_in_the_BODY_is_not_this_linters_business(self, tmp_path, lint):
        """CONTROL, and the reason fences are located in bytes: this linter
        validates frontmatter. Rejecting a skill for a stray byte in its prose
        would be a false red, so only the frontmatter region is decoded."""
        md = _skill(tmp_path, "bodyenc",
                    b"---\nname: bodyenc\ndescription: A description.\n---\nprose \xff\xfe\n")
        assert lint.lint_skill_md(md) == []

    def test_a_bom_is_named_accurately(self, tmp_path, lint):
        """The old gate reported a BOM as "missing YAML frontmatter", sending
        readers to look for a fence that was right there."""
        md = _skill(tmp_path, "bom",
                    b"\xef\xbb\xbf---\nname: bom\ndescription: d\n---\n")
        assert any("BOM" in p for p in lint.lint_skill_md(md))


class TestDiscoveryReportsWhatItCouldNotEnumerate:
    """The third false green, and the worst: `if not skill_mds` only fires when
    the WHOLE tree is empty, so one readable skill was enough to hide an
    unlistable sibling holding a violation."""

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list a 0o000 directory")
    def test_an_unlistable_subtree_is_reported(self, tmp_path, lint):
        _skill(tmp_path, "good")
        hidden = tmp_path / "skills" / "tooling" / "hidden"
        (hidden / "inner").mkdir(parents=True)
        (hidden / "inner" / "SKILL.md").write_text(
            "---\nname: TOTALLY-INVALID\ndescription: d\n---\n", encoding="utf-8")
        hidden.chmod(0o000)
        try:
            _found, unwalkable = lint.discover(tmp_path / "skills")
            assert any("could not be listed" in u for u in unwalkable), unwalkable
        finally:
            hidden.chmod(0o755)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list a 0o000 directory")
    def test_it_reaches_the_exit_code(self, tmp_path, lint):
        """Through the real entry point. A finding that never leaves discovery
        is not a gate — and this is exactly the case the old guard missed,
        because a good skill kept the count non-zero."""
        _skill(tmp_path, "good")
        hidden = tmp_path / "skills" / "tooling" / "hidden"
        (hidden / "inner").mkdir(parents=True)
        (hidden / "inner" / "SKILL.md").write_text(
            "---\nname: TOTALLY-INVALID\ndescription: d\n---\n", encoding="utf-8")
        hidden.chmod(0o000)
        try:
            r = _run(tmp_path)
            assert r.returncode == 1, r.stdout
            assert "could not be listed" in r.stdout
            assert "Traceback" not in r.stdout + r.stderr
        finally:
            hidden.chmod(0o755)

    def test_a_dangling_manifest_is_discovered_and_reported(self, tmp_path, lint):
        """`Path.rglob` filters candidates through `Path.exists()`, which follows
        symlinks, so on the Python 3.11 this workflow pins a dangling SKILL.md
        was never yielded at all; on 3.12+ it was yielded and then crashed."""
        d = tmp_path / "skills" / "tooling" / "dangling"
        d.mkdir(parents=True)
        (d / "SKILL.md").symlink_to(tmp_path / "no-such-target")
        found, _unwalkable = lint.discover(tmp_path / "skills")
        assert (d / "SKILL.md") in found
        assert any("broken symlink" in p for p in lint.lint_skill_md(d / "SKILL.md"))

    def test_a_directory_named_skill_md_is_reported(self, tmp_path, lint):
        d = tmp_path / "skills" / "tooling" / "dirm"
        d.mkdir(parents=True)
        (d / "SKILL.md").mkdir()
        _found, unwalkable = lint.discover(tmp_path / "skills")
        assert any("is a directory, not a manifest" in u for u in unwalkable), unwalkable

    def test_a_normal_tree_is_discovered_at_every_depth(self, tmp_path, lint):
        """CONTROL: the walk must find everything `rglob` did."""
        for rel in ["a", "b/skills/c", "d/e/f"]:
            p = tmp_path / "skills" / "tooling" / rel
            p.mkdir(parents=True)
            (p / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        found, unwalkable = lint.discover(tmp_path / "skills")
        assert unwalkable == []
        assert len(found) == 3, found

    def test_extensions_are_excluded(self, tmp_path, lint):
        p = tmp_path / "skills" / "tooling" / "x" / "extensions" / "priv"
        p.mkdir(parents=True)
        (p / "SKILL.md").write_text("---\nname: WRONG\n---\n", encoding="utf-8")
        found, unwalkable = lint.discover(tmp_path / "skills")
        assert found == [] and unwalkable == []


class TestUnreadableIsAFindingNotACrash:
    @pytest.mark.skipif(os.geteuid() == 0, reason="root can read a 0o000 file")
    def test_a_permission_denied_manifest_is_reported(self, tmp_path, lint):
        md = _skill(tmp_path, "locked")
        md.chmod(0o000)
        try:
            assert any("could not be read" in p for p in lint.lint_skill_md(md))
        finally:
            md.chmod(0o644)


class TestTheSpecRules:
    @pytest.mark.parametrize("name,ok", [
        ("good", True), ("multi-part-name", True), ("a1", True),
        ("WRONG-CASE", False), ("-leading", False), ("trailing-", False),
        ("double--hyphen", False), ("1leading-digit", False),
        ("under_score", False), ("a" * 65, False),
    ])
    def test_name_syntax(self, tmp_path, lint, name, ok):
        md = _skill(tmp_path, name, f"---\nname: {name}\ndescription: d\n---\n",
                    dirname=name)
        problems = [p for p in lint.lint_skill_md(md) if "`name`" in p]
        assert (not problems) == ok, (name, problems)

    def test_name_must_match_the_parent_directory(self, tmp_path, lint):
        md = _skill(tmp_path, "declared",
                    "---\nname: declared\ndescription: d\n---\n", dirname="actual")
        assert any("does not match parent dir" in p for p in lint.lint_skill_md(md))

    def test_a_non_string_name_is_reported(self, tmp_path, lint):
        md = _skill(tmp_path, "n", "---\nname: 42\ndescription: d\n---\n")
        assert any("must be a string" in p for p in lint.lint_skill_md(md))

    @pytest.mark.parametrize("body", [
        "---\nname: d\n---\n",
        "---\nname: d\ndescription:\n---\n",
        "---\nname: d\ndescription: ''\n---\n",
    ])
    def test_description_is_required(self, tmp_path, lint, body):
        md = _skill(tmp_path, "d", body)
        assert any("description" in p for p in lint.lint_skill_md(md))

    def test_malformed_yaml_reports_on_one_line(self, tmp_path, lint):
        """A PyYAML error spans several lines including a caret diagram. Printed
        raw it broke the one-error-per-line format the report relies on."""
        md = _skill(tmp_path, "y", "---\nname: [unclosed\n---\n")
        problems = lint.lint_skill_md(md)
        assert problems and all("\n" not in p for p in problems)
        assert any("line 1" in p for p in problems), problems


class TestTheEntryPoint:
    def test_an_empty_skills_dir_is_an_error(self, tmp_path):
        (tmp_path / "skills").mkdir()
        r = _run(tmp_path)
        assert r.returncode == 1 and "no SKILL.md found" in r.stdout

    def test_a_missing_skills_dir_is_an_error(self, tmp_path):
        r = _run(tmp_path)
        assert r.returncode == 1 and "no skills/ dir" in r.stdout

    def test_a_clean_tree_exits_zero(self, tmp_path):
        _skill(tmp_path, "good")
        r = _run(tmp_path)
        assert r.returncode == 0, r.stdout
        assert "OK — 1 SKILL.md files conform" in r.stdout
