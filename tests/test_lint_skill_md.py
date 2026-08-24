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

    def test_a_symlinked_skill_directory_is_reported_not_skipped(self, tmp_path, lint):
        """`followlinks=True` invites a loop, so a symlinked directory is not
        entered — but silently not entering one is the same omission this linter
        exists to remove. The old gate missed these too, so reporting is not a
        behaviour regression; it is the omission being surfaced instead of taken.
        Found by asking of my own fix: can a real skill be MISSED?"""
        outside = tmp_path / "elsewhere" / "linked-skill"
        outside.mkdir(parents=True)
        (outside / "SKILL.md").write_text("---\nname: X\ndescription: d\n---\n",
                                          encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "linked-skill").symlink_to(outside)
        _found, unwalkable = lint.discover(tmp_path / "skills")
        assert any("symlinked directory holding a SKILL.md" in u for u in unwalkable), unwalkable

    def test_a_symlinked_directory_without_a_manifest_is_left_alone(self, tmp_path, lint):
        """CONTROL: a symlinked assets or references directory is ordinary and
        must not be reported, or the fix for an omission becomes a false red."""
        outside = tmp_path / "other"
        outside.mkdir()
        (outside / "notes.md").write_text("x", encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "assets").symlink_to(outside)
        _found, unwalkable = lint.discover(tmp_path / "skills")
        assert unwalkable == [], unwalkable

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
        assert "pass the frontmatter checks" in r.stdout
        # NOT "conform to agentskills.io spec". The spec also caps `description`
        # at 1024 characters and 33 of the 99 real manifests exceed it, so that
        # claim was broader than anything this gate verifies.
        assert "conform to agentskills.io spec" not in r.stdout


class TestNameIsFullMatched:
    """`$` matches BEFORE a trailing newline, so `NAME_RE.match("good\\n")` was
    true. The second time I wrote that bug in one day — PR #189 had the identical
    defect in its SemVer check — which is why the assertion here goes through
    `lint_skill_md` rather than asking the compiled pattern."""

    @pytest.mark.parametrize("literal", ['"x\\n"', '"x "', '" x"'])
    def test_whitespace_decorated_names_are_rejected(self, tmp_path, lint, literal):
        md = _skill(tmp_path, "x", f"---\nname: {literal}\ndescription: d\n---\n")
        assert any("`name`" in p for p in lint.lint_skill_md(md)), literal

    def test_a_plain_name_is_still_accepted(self, tmp_path, lint):
        """CONTROL for the above."""
        assert lint.lint_skill_md(_skill(tmp_path, "plain")) == []


class TestDuplicateKeysCannotConcealAViolation:
    def test_a_duplicate_name_is_reported(self, tmp_path, lint):
        """PyYAML keeps the LAST of duplicate keys silently, so `name: BAD`
        followed by `name: x` validated as `x` — a valid declaration concealing
        an invalid one, below the layer that checks names."""
        md = _skill(tmp_path, "x", "---\nname: BAD\nname: x\ndescription: d\n---\n")
        assert any("duplicate key" in p for p in lint.lint_skill_md(md))

    def test_an_unhashable_key_is_reported_not_raised(self, tmp_path, lint):
        """The duplicate check tests `key in mapping`, which raises TypeError for
        a sequence key — legal YAML, never valid frontmatter."""
        md = _skill(tmp_path, "x", "---\n? [a, b]\n: c\nname: x\ndescription: d\n---\n")
        problems = lint.lint_skill_md(md)
        assert any("unhashable key" in p for p in problems), problems

    def test_distinct_keys_are_unaffected(self, tmp_path, lint):
        """CONTROL."""
        assert lint.lint_skill_md(_skill(tmp_path, "d2")) == []


class TestAVanishedManifestIsNotAnExemption:
    def test_a_manifest_deleted_after_discovery_is_reported(self, tmp_path, lint):
        """`lint_skill_md` is only ever called on a path discovery returned, so
        "absent" cannot mean "no skill lives here" — it means the manifest went
        away between being found and being read. Returning [] made that a silent
        exemption, which is this linter's own defect class."""
        md = _skill(tmp_path, "vanish", "---\nname: WRONG-CASE\ndescription: d\n---\n")
        found, _ = lint.discover(tmp_path / "skills")
        assert md in found
        md.unlink()
        assert any("vanished" in p for p in lint.lint_skill_md(md))


class TestDescriptionType:
    @pytest.mark.parametrize("value,reported", [
        ("A real description.", False),
        ("42", False),
        ("", True),
    ])
    def test_string_descriptions(self, tmp_path, lint, value, reported):
        md = _skill(tmp_path, "d3", f"---\nname: d3\ndescription: '{value}'\n---\n")
        problems = [p for p in lint.lint_skill_md(md) if "description" in p]
        assert bool(problems) == reported, (value, problems)

    def test_a_non_string_description_is_reported(self, tmp_path, lint):
        md = _skill(tmp_path, "d4", "---\nname: d4\ndescription: 42\n---\n")
        assert any("must be a string" in p for p in lint.lint_skill_md(md))

    def test_a_list_description_is_reported(self, tmp_path, lint):
        md = _skill(tmp_path, "d5", "---\nname: d5\ndescription:\n  - a\n  - b\n---\n")
        assert any("must be a string" in p for p in lint.lint_skill_md(md))


class TestASymlinkCycleDoesNotHang:
    def test_discovery_terminates_on_a_self_referential_link(self, tmp_path, lint):
        """The property `followlinks=False` actually protects.

        A mutation sweep found that flipping it to `True` SURVIVED the suite:
        the symlinked-directory test only asserted the link was reported, which
        stays true either way. What `False` really buys is termination — a
        directory linked to its own ancestor walks forever with `True`. Pinning
        the report without pinning the loop left the flag unprotected.
        """
        tooling = tmp_path / "skills" / "tooling"
        (tooling / "real").mkdir(parents=True)
        (tooling / "real" / "SKILL.md").write_text(
            "---\nname: real\ndescription: A description.\n---\n", encoding="utf-8")
        # skills/tooling/real/loop -> skills/  (points back above itself)
        (tooling / "real" / "loop").symlink_to(tmp_path / "skills")

        found, _unwalkable = lint.discover(tmp_path / "skills")

        # Terminates, and the genuine skill is still found exactly once.
        assert [p for p in found if p.parent.name == "real"] == [
            tooling / "real" / "SKILL.md"]


class TestTheNameLengthBoundary:
    """A `MAX_NAME = 63` mutation survived: the suite covered 65 but never the
    valid 64, and the longest real name is 31 — so nothing pinned the edge."""

    @pytest.mark.parametrize("length,ok", [(63, True), (64, True), (65, False)])
    def test_the_cap_is_inclusive_at_64(self, tmp_path, lint, length, ok):
        name = "a" * length
        md = _skill(tmp_path, name, f"---\nname: {name}\ndescription: d\n---\n",
                    dirname=name)
        problems = [p for p in lint.lint_skill_md(md) if "exceeds" in p]
        assert (not problems) == ok, (length, problems)


class TestYamlMergeKeysStillWork:
    def test_a_merge_key_is_expanded_not_rejected(self, tmp_path, lint):
        """`SafeLoader.construct_mapping` calls `flatten_mapping` to expand
        `<<: *anchor`. The duplicate-key constructor replaced that method, and
        skipping the flatten step turned a document the OLD gate accepted into
        an error — making a fix a behaviour regression."""
        md = _skill(tmp_path, "m", "---\nbase: &b\n  description: shared\n"
                                   "<<: *b\nname: m\n---\n")
        assert lint.lint_skill_md(md) == []

    def test_duplicates_are_still_rejected(self, tmp_path, lint):
        """CONTROL: restoring merge support must not restore duplicate keys."""
        md = _skill(tmp_path, "m2", "---\nname: BAD\nname: m2\ndescription: d\n---\n")
        assert any("duplicate key" in p for p in lint.lint_skill_md(md))


class TestASymlinkedDirectoryIsSearchedAtDepth:
    def test_a_nested_manifest_under_a_link_is_reported(self, tmp_path, lint):
        """Checking only `link/SKILL.md` missed `link/nested/SKILL.md`, so a
        linked-in package whose skill sat one level down was still omitted in
        silence."""
        outside = tmp_path / "outside" / "pkg" / "deep"
        outside.mkdir(parents=True)
        (outside / "SKILL.md").write_text("---\nname: X\ndescription: d\n---\n",
                                          encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "linked").symlink_to(tmp_path / "outside" / "pkg")
        _found, unwalkable = lint.discover(tmp_path / "skills")
        assert any("symlinked directory holding a SKILL.md" in u for u in unwalkable), unwalkable

    def test_a_symlinked_assets_directory_is_still_left_alone(self, tmp_path, lint):
        """CONTROL: searching at depth must not start reporting ordinary linked
        asset directories."""
        outside = tmp_path / "assets" / "img"
        outside.mkdir(parents=True)
        (outside / "x.png").write_text("x", encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "assets").symlink_to(tmp_path / "assets")
        _found, unwalkable = lint.discover(tmp_path / "skills")
        assert unwalkable == [], unwalkable


class TestSymlinkProbingFailsClosed:
    """`os.walk` SWALLOWS a directory it cannot list and walks on, so the
    `except OSError` around the probe never fired: an unreadable subtree inside
    a linked package read as a subtree with nothing in it, and the link went
    unreported. The same defect `discover` already fixes one level up,
    reintroduced in the helper written to fix the symlink case — the third time
    this shape appeared in this file's own code."""

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list a 0o000 directory")
    def test_an_unreadable_linked_subtree_is_still_reported(self, tmp_path, lint):
        pkg = tmp_path / "outside" / "pkg"
        deep = pkg / "deep"
        deep.mkdir(parents=True)
        (deep / "SKILL.md").write_text("---\nname: INVALID\ndescription: d\n---\n",
                                       encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "linked").symlink_to(pkg)
        deep.chmod(0o000)
        try:
            _found, unwalkable = lint.discover(tmp_path / "skills")
            assert any("symlinked directory" in u for u in unwalkable), unwalkable
        finally:
            deep.chmod(0o755)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list a 0o000 directory")
    def test_it_reaches_the_exit_code(self, tmp_path, lint, monkeypatch):
        """Through `main()`: a finding that never leaves discovery is not a gate."""
        pkg = tmp_path / "outside" / "pkg"
        deep = pkg / "deep"
        deep.mkdir(parents=True)
        (deep / "SKILL.md").write_text("---\nname: INVALID\ndescription: d\n---\n",
                                       encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "linked").symlink_to(pkg)
        _skill(tmp_path, "ok")
        deep.chmod(0o000)
        try:
            monkeypatch.chdir(tmp_path)
            r = _run(tmp_path)
            assert r.returncode == 1, r.stdout
            assert "Traceback" not in r.stdout + r.stderr
        finally:
            deep.chmod(0o755)

    def test_a_readable_empty_linked_directory_is_not_reported(self, tmp_path, lint):
        """CONTROL: failing closed on "cannot tell" must not become reporting
        every link. A readable linked directory with no SKILL.md is ordinary."""
        outside = tmp_path / "outside" / "pkg"
        (outside / "deep").mkdir(parents=True)
        (outside / "deep" / "notes.md").write_text("x", encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "linked").symlink_to(outside)
        _found, unwalkable = lint.discover(tmp_path / "skills")
        assert unwalkable == [], unwalkable


class TestAnExplicitKeyMayOverrideAMergedOne:
    """Two failure modes traded against each other before this settled: skipping
    `flatten_mapping` broke `<<: *anchor` outright, and calling it first made
    merged fields indistinguishable from written ones — so an explicit key
    OVERRIDING a merged one read as a duplicate. That is valid YAML, and the
    override is the whole point of a merge."""

    def test_an_override_is_accepted_and_wins(self, tmp_path, lint):
        md = _skill(tmp_path, "ov",
                    "---\nbase: &b\n  description: shared\n  name: base\n"
                    "<<: *b\nname: ov\ndescription: mine\n---\n")
        assert lint.lint_skill_md(md) == []
        fm, _u, _p = lint.read_frontmatter(md)
        assert fm["description"] == "mine" and fm["name"] == "ov"

    def test_it_matches_plain_safe_load(self, lint):
        """The strongest form: agree with the loader this replaced."""
        import yaml
        doc = ("base: &b\n  description: shared\n  name: base\n"
               "<<: *b\nname: ov\ndescription: mine\n")
        assert yaml.load(doc, Loader=lint._NoDuplicateKeys) == yaml.safe_load(doc)

    def test_a_genuine_duplicate_is_still_rejected(self, tmp_path, lint):
        """CONTROL: restoring override support must not restore duplicates."""
        md = _skill(tmp_path, "dup2", "---\nname: A\nname: dup2\ndescription: d\n---\n")
        assert any("duplicate key" in p for p in lint.lint_skill_md(md))


class TestTheLoaderAgreesWithSafeLoad:
    """The behaviour-preservation claim in its strongest form.

    Replacing `safe_load` with a custom constructor cost two consecutive
    FALSE REDS on valid YAML — first `<<: *anchor` rejected outright, then an
    explicit key overriding a merged one read as a duplicate. Both were caught
    by review rather than by a test, because the tests asserted specific
    messages instead of asserting that valid documents still parse the same.

    So the property, not the symptom: for any document without duplicate keys,
    this loader must return exactly what `safe_load` returns.
    """

    @pytest.mark.parametrize("doc", [
        "name: a\ndescription: d\n",
        "b: &b\n  x: 1\n<<: *b\nname: a\n",
        "b: &b\n  x: 1\n  name: base\n<<: *b\nname: a\n",
        "b: &b\n  name: base\nname: a\n<<: *b\n",
        "p: &p\n  x: 1\nq: &q\n  y: 2\n<<: [*p, *q]\nname: a\n",
        "p: &p\n  x: 1\nq: &q\n  <<: *p\n  y: 2\n<<: *q\nname: a\n",
        "name: a\nmeta:\n  k: v\n  l: w\n",
        "name: a\ntags:\n  - x\n  - y\n",
        "name: a\ndescription:\n",
        'name: a\ndescription: "x: y"\n',
        "name: a\ndescription: |\n  line1\n  line2\n",
        "a: &v text\nname: a\nd: *v\n",
        "~: 1\nname: a\n",
        "yes: 1\nno: 2\nname: a\n",
        # The cases the first version of this list MISSED, which is the lesson:
        # a fixed list of documents I thought of is not a property. Both were
        # found by review, not by the battery.
        "1: a\ntrue: b\nname: x\n",      # YAML-distinct keys that collide in Python
        "1: a\n1.0: b\nname: x\n",       # int vs float, same Python hash
        "'1': a\n1: b\nname: x\n",       # str vs int, distinct by tag
        "&a\nself: *a\nname: x\n",       # recursive alias to the enclosing map
        "a: &m\n  k: *m\nname: x\n",     # recursion one level down
        # TWO merge keys in one mapping. `safe_load` accepts this and merges
        # both, so treating `<<` as an ordinary key would report a duplicate —
        # a false red. Found by a surviving mutation, not by review: removing
        # the merge-tag skip changed nothing until a document existed that
        # actually had two of them.
        "p: &p\n  x: 1\nq: &q\n  y: 2\n<<: *p\n<<: *q\nname: a\n",
    ])
    def test_valid_documents_parse_identically(self, lint, doc):
        import yaml
        mine = yaml.load(doc, Loader=lint._NoDuplicateKeys)
        want = yaml.safe_load(doc)
        # `repr`, not `==`. Two self-referential dicts compared with `==` blow
        # the recursion limit — Python's cycle detection covers identity, not
        # two structurally-equal distinct objects. `repr` renders a cycle as
        # `{...}` and terminates, which is exactly the comparison wanted here.
        assert repr(mine) == repr(want)


class TestDuplicateDetectionIsNotNameSpecific:
    """A mutation from `if duplicate:` to `if duplicate and key == "name":`
    survived, because every duplicate-key test used `name`. The rule is about
    duplication, not about one field."""

    @pytest.mark.parametrize("field", ["name", "description", "version", "foo"])
    def test_any_duplicated_key_is_rejected(self, lint, field):
        import yaml
        doc = f"name: x\ndescription: d\n{field}: A\n{field}: B\n"
        with pytest.raises(yaml.YAMLError, match="duplicate key"):
            yaml.load(doc, Loader=lint._NoDuplicateKeys)

    def test_a_duplicate_description_reaches_the_report(self, tmp_path, lint):
        """Through `lint_skill_md`, not just the loader."""
        md = _skill(tmp_path, "dd",
                    "---\nname: dd\ndescription: A\ndescription: B\n---\n")
        assert any("duplicate key 'description'" in p for p in lint.lint_skill_md(md))


class TestAllThreeLineEndingsAreNormalised:
    """The FOURTH false red I introduced in this PR while fixing false greens.

    The inline version read in TEXT mode, where Python's universal-newline
    handling normalises CR, LF and CRLF alike. Moving to bytes — necessary, so
    that invalid UTF-8 in a prose body is not this linter's business — dropped
    that, and normalising only CRLF made a bare-CR manifest the old gate
    ACCEPTED report "missing YAML frontmatter".
    """

    @pytest.mark.parametrize("raw", [
        b"---\nname: le\ndescription: A description.\n---\nbody\n",
        b"---\r\nname: le\r\ndescription: A description.\r\n---\r\nbody\r\n",
        b"---\rname: le\rdescription: A description.\r---\rbody\r",
        b"---\r\nname: le\rdescription: A description.\n---\nbody\n",
    ])
    def test_a_well_formed_manifest_parses_in_any_line_ending(self, tmp_path, lint, raw):
        assert lint.lint_skill_md(_skill(tmp_path, "le", raw)) == []

    def test_a_violation_is_still_caught_through_bare_cr(self, tmp_path, lint):
        """CONTROL: normalising must not become a way to pass."""
        md = _skill(tmp_path, "le2", b"---\rname: WRONG-CASE\rdescription: d\r---\r")
        assert any("`name`" in p for p in lint.lint_skill_md(md))


class TestValueConstructionErrorsAreReported:
    def test_an_impossible_timestamp_is_reported_not_raised(self, tmp_path, lint):
        """PyYAML's implicit resolvers CONSTRUCT values, and `2024-13-40`
        resolves as a timestamp whose constructor raises ValueError straight
        through `yaml.YAMLError` — a traceback instead of a report, from a
        manifest a human could plausibly write."""
        md = _skill(tmp_path, "ts", "---\nname: ts\ndescription: 2024-13-40\n---\n")
        problems = lint.lint_skill_md(md)
        assert problems and all("Traceback" not in p for p in problems)
        assert any("malformed YAML" in p for p in problems), problems

    def test_a_valid_date_is_still_accepted(self, tmp_path, lint):
        """CONTROL: a real date resolves to a `datetime.date`, which is a
        non-string description and reported as such — not as malformed YAML."""
        md = _skill(tmp_path, "ts2", "---\nname: ts2\ndescription: 2024-01-02\n---\n")
        assert any("must be a string" in p for p in lint.lint_skill_md(md))


class TestExcludedSubtreesArePruned:
    """`subdirs[:] = []` survived mutation: dropping it still hides every
    readable `extensions/` manifest, because the `continue` catches them
    anyway. What pruning actually buys is not descending — so an unreadable
    descendant of an EXCLUDED subtree cannot raise a finding about a tree this
    linter has deliberately opted out of."""

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list a 0o000 directory")
    def test_an_unreadable_descendant_of_extensions_is_not_reported(self, tmp_path, lint):
        _skill(tmp_path, "ok")
        ext = tmp_path / "skills" / "tooling" / "x" / "extensions" / "priv"
        ext.mkdir(parents=True)
        (ext / "SKILL.md").write_text("---\nname: WRONG\n---\n", encoding="utf-8")
        ext.chmod(0o000)
        try:
            found, unwalkable = lint.discover(tmp_path / "skills")
            assert unwalkable == [], unwalkable
            assert not [p for p in found if "extensions" in p.parts]
        finally:
            ext.chmod(0o755)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list a 0o000 directory")
    def test_an_unreadable_NON_excluded_subtree_is_still_reported(self, tmp_path, lint):
        """CONTROL: pruning must apply only to the exclusion."""
        _skill(tmp_path, "ok")
        hidden = tmp_path / "skills" / "tooling" / "hidden" / "inner"
        hidden.mkdir(parents=True)
        hidden.parent.chmod(0o000)
        try:
            _found, unwalkable = lint.discover(tmp_path / "skills")
            assert any("could not be listed" in u for u in unwalkable), unwalkable
        finally:
            hidden.parent.chmod(0o755)


class TestExclusionIsPrunedBeforeDescent:
    """The previous pruning fix was one level too late. `os.walk` has to LIST a
    directory to reach the body of the loop, so an unreadable `extensions/`
    fired `onerror` before `subdirs[:] = []` could run — producing a finding
    about a subtree this linter has deliberately opted out of. Pruning now
    happens in the PARENT's `subdirs`, before descent."""

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list a 0o000 directory")
    def test_an_unreadable_extensions_directory_is_not_reported(self, tmp_path, lint):
        _skill(tmp_path, "ok")
        ext = tmp_path / "skills" / "tooling" / "x" / "extensions"
        (ext / "priv").mkdir(parents=True)
        ext.chmod(0o000)
        try:
            _found, unwalkable = lint.discover(tmp_path / "skills")
            assert unwalkable == [], unwalkable
        finally:
            ext.chmod(0o755)

    def test_a_readable_extensions_manifest_is_still_excluded(self, tmp_path, lint):
        """CONTROL: pruning earlier must not change WHAT is excluded."""
        _skill(tmp_path, "ok")
        ext = tmp_path / "skills" / "tooling" / "x" / "extensions" / "priv"
        ext.mkdir(parents=True)
        (ext / "SKILL.md").write_text("---\nname: WRONG\n---\n", encoding="utf-8")
        found, _unwalkable = lint.discover(tmp_path / "skills")
        assert not [p for p in found if "extensions" in p.parts]


class TestDeeplyNestedValuesAreReported:
    def test_a_recursion_error_becomes_a_finding(self, tmp_path, lint):
        """PyYAML recurses while constructing, so a deeply nested value raises
        `RecursionError` — which is not a `YAMLError`, `ValueError` or
        `TypeError`, and so came out as a traceback."""
        body = "---\nname: deep\ndescription: " + "[" * 2000 + "]" * 2000 + "\n---\n"
        md = _skill(tmp_path, "deep", body)
        problems = lint.lint_skill_md(md)
        assert problems and any("malformed YAML" in p for p in problems), problems


class TestAnUnwalkableOnlyTreeIsNotCalledEmpty:
    """`if not skill_mds:` replacing `if not skill_mds and not unwalkable:`
    survived: every entry-point test with an unwalkable subtree also created a
    readable skill, so nothing covered a tree that is ENTIRELY unreadable — which
    would report the misleading generic "no SKILL.md found" instead of naming
    the directory it could not list."""

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list a 0o000 directory")
    def test_it_names_what_it_could_not_list(self, tmp_path, lint, capsys, monkeypatch):
        tooling = tmp_path / "skills" / "tooling"
        hidden = tooling / "hidden"
        (hidden / "inner").mkdir(parents=True)
        hidden.chmod(0o000)
        try:
            monkeypatch.setattr(lint, "_SKILLS_DIR", tmp_path / "skills", raising=False)
            r = _run(tmp_path)
            assert r.returncode == 1, r.stdout
            assert "could not be listed" in r.stdout, r.stdout
            assert "no SKILL.md found" not in r.stdout, r.stdout
        finally:
            hidden.chmod(0o755)

    def test_a_genuinely_empty_tree_still_says_so(self, tmp_path):
        """CONTROL: an empty skills/ is a different thing from an unreadable
        one, and must keep its own message."""
        (tmp_path / "skills").mkdir()
        r = _run(tmp_path)
        assert r.returncode == 1 and "no SKILL.md found" in r.stdout


class TestAnyConstructionFailureIsAFinding:
    """Enumerating what a PyYAML constructor can raise did not converge:
    `YAMLError`, then `ValueError` from a timestamp, then `RecursionError` from
    deep nesting, then `KeyError` from `!!bool wat` and `AttributeError` from
    `!!timestamp wat`. Each reached a user as a traceback and each took a round
    to find. Caught by INTENT now — a value that will not construct is a finding
    about the manifest — with the `try` covering one call so it cannot swallow a
    defect elsewhere."""

    @pytest.mark.parametrize("value", [
        "!!bool wat",        # KeyError
        "!!timestamp wat",   # AttributeError
        "!!int wat",         # ValueError
        "!!float wat",
        "!!python/object:os.system x",   # ConstructorError
        "2024-13-40",        # ValueError from the implicit timestamp resolver
    ])
    def test_it_is_reported_not_raised(self, tmp_path, lint, value):
        md = _skill(tmp_path, "t", f"---\nname: t\ndescription: {value}\n---\n")
        problems = lint.lint_skill_md(md)
        assert problems, value
        assert any("malformed YAML" in p for p in problems), (value, problems)

    def test_a_valid_explicit_tag_still_reaches_the_type_check(self, tmp_path, lint):
        """CONTROL: catching broadly must not turn every tagged value into
        "malformed". A valid `!!bool` constructs fine and is reported as a
        non-string description, which is a different and more accurate finding."""
        md = _skill(tmp_path, "t2", "---\nname: t2\ndescription: !!bool true\n---\n")
        assert any("must be a string" in p for p in lint.lint_skill_md(md))

    def test_an_ordinary_manifest_is_untouched(self, tmp_path, lint):
        """CONTROL."""
        assert lint.lint_skill_md(_skill(tmp_path, "t3")) == []


class TestTheSymlinkProbeSharesTheExclusion:
    def test_a_linked_tree_holding_only_an_extension_is_left_alone(self, tmp_path, lint):
        """`discover` excludes `extensions/`, so a linked tree containing ONLY an
        extension manifest holds nothing this linter checks — reporting it as a
        skill it declined to enter is a false red."""
        ext = tmp_path / "assets" / "extensions" / "priv"
        ext.mkdir(parents=True)
        (ext / "SKILL.md").write_text("---\nname: priv\n---\n", encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "assets").symlink_to(tmp_path / "assets")
        _found, unwalkable = lint.discover(tmp_path / "skills")
        assert unwalkable == [], unwalkable

    def test_a_linked_tree_holding_a_real_skill_is_still_reported(self, tmp_path, lint):
        """CONTROL: sharing the exclusion must not silence the real case."""
        pkg = tmp_path / "pkg" / "deep"
        pkg.mkdir(parents=True)
        (pkg / "SKILL.md").write_text("---\nname: r\n---\n", encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "linked").symlink_to(tmp_path / "pkg")
        _found, unwalkable = lint.discover(tmp_path / "skills")
        assert any("symlinked directory" in u for u in unwalkable), unwalkable


class TestReportOrderIsDeterministic:
    def test_discovery_is_sorted(self, tmp_path, lint):
        """Dropping `sorted(found)` survived every assertion: nothing pinned the
        order, so a report could reshuffle between runs on the same tree and read
        as a change."""
        for name in ["zebra", "alpha", "middle"]:
            _skill(tmp_path, name)
        found, _unwalkable = lint.discover(tmp_path / "skills")
        assert found == sorted(found)
        assert [p.parent.name for p in found] == ["alpha", "middle", "zebra"]


class TestVendoredManifestsAreNotThisReposSkills:
    """Found by reconciling the count the linter REPORTS against what git
    TRACKS, minutes after this linter merged.

    `.venv/lib/*/site-packages/` now contains third-party `SKILL.md` files —
    logfire, typer and fastapi all ship agent skills inside the PyPI package —
    and the walk descended into them. All three happened to conform, so the only
    visible symptom was a count of 103 where git tracks 100. The next dependency
    that ships a non-conforming manifest would have failed the lint locally on a
    file nobody here owns.

    CI never saw it: a fresh checkout has no `.venv`. That is why it survived
    review and four cross-model rounds.
    """

    @pytest.mark.parametrize("vendor", [
        ".venv/lib/python3.12/site-packages/pkg/.agents/skills/vendored",
        "node_modules/some-pkg/skills/vendored",
        "venv/lib/site-packages/pkg/skills/vendored",
        ".tox/py311/lib/pkg/skills/vendored",
    ])
    def test_a_vendored_manifest_is_not_discovered(self, tmp_path, lint, vendor):
        _skill(tmp_path, "real")
        v = tmp_path / "skills" / "tooling" / "host" / vendor
        v.mkdir(parents=True)
        # deliberately NON-conforming: if it were linted, it would fail
        (v / "SKILL.md").write_text("---\nname: TOTALLY-WRONG\n---\n", encoding="utf-8")
        found, unwalkable = lint.discover(tmp_path / "skills")
        assert unwalkable == [], unwalkable
        assert [p.parent.name for p in found] == ["real"], found

    def test_a_real_skill_beside_a_vendored_tree_is_still_found(self, tmp_path, lint):
        """CONTROL: pruning must not hide a genuine skill."""
        _skill(tmp_path, "real")
        v = tmp_path / "skills" / "tooling" / "real" / ".venv" / "site-packages"
        v.mkdir(parents=True)
        (v / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        found, _ = lint.discover(tmp_path / "skills")
        assert (tmp_path / "skills" / "tooling" / "real" / "SKILL.md") in found

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list a 0o000 directory")
    def test_an_unreadable_vendored_tree_raises_no_finding(self, tmp_path, lint):
        """Pruned BEFORE descent, like `extensions/`: `os.walk` has to LIST a
        directory to reach it, so an unreadable excluded tree would otherwise
        fire `onerror` and report a subtree this linter opted out of."""
        _skill(tmp_path, "real")
        v = tmp_path / "skills" / "tooling" / "host" / ".venv"
        (v / "inner").mkdir(parents=True)
        v.chmod(0o000)
        try:
            _found, unwalkable = lint.discover(tmp_path / "skills")
            assert unwalkable == [], unwalkable
        finally:
            v.chmod(0o755)

    def test_the_symlink_probe_shares_the_exclusion(self, tmp_path, lint):
        """A linked tree holding only a VENDORED manifest holds nothing this
        linter checks, so reporting it as a skill it declined to enter would be
        a false red — the same rule `extensions/` already gets."""
        vend = tmp_path / "outside" / ".venv" / "site-packages" / "pkg" / "skills" / "v"
        vend.mkdir(parents=True)
        (vend / "SKILL.md").write_text("---\nname: v\n---\n", encoding="utf-8")
        tooling = tmp_path / "skills" / "tooling"
        tooling.mkdir(parents=True)
        (tooling / "linked").symlink_to(tmp_path / "outside")
        _found, unwalkable = lint.discover(tmp_path / "skills")
        assert unwalkable == [], unwalkable


class TestTheReportedCountMatchesWhatGitTracks:
    def test_the_linter_counts_exactly_the_repositorys_own_manifests(self):
        """The reconciliation that found the vendored-manifest bug, kept as a
        test. A count the linter reports that git cannot account for means it is
        walking something this repository does not ship."""
        repo = SCRIPT.parents[1]
        tracked = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "skills/*SKILL.md"],
            capture_output=True, text=True, check=True).stdout.split()
        expected = [p for p in tracked if "/extensions/" not in p]

        r = subprocess.run([sys.executable, str(SCRIPT)], cwd=repo,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        reported = int(r.stdout.split("linting ")[1].split()[0])
        assert reported == len(expected), (
            f"linter counted {reported}, git tracks {len(expected)} "
            "— it is walking files this repository does not ship")
