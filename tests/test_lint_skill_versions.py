"""Tests for scripts/lint_skill_versions.py.

The script had no test file. Every case here drives the real `lint_skill`
against a fixture skill on disk, and every "this is reported" case is paired
with a control that must come back clean — because the defect these were
written for produced *no problems* for three different broken manifests, which
is indistinguishable from three passes unless something in the set must fail.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_skill_versions.py"

#: An invalid version, so a manifest the linter can READ always has something to
#: report. Every fixture below carries it: the difference between the cases is
#: only whether the manifest is readable, never whether it is correct.
BAD_VERSION = "version: not-semver"


def _load():
    spec = importlib.util.spec_from_file_location("lint_skill_versions_under_test", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lint_skill_versions_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def lint():
    return _load()


def _skill(tmp_path: Path, name: str, raw: bytes | None) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        (d / "SKILL.md").write_bytes(raw)
    return d


def _wellformed(name: str) -> bytes:
    return f"---\nname: {name}\ndescription: D.\n{BAD_VERSION}\n---\n".encode("utf-8")


class TestTheControl:
    def test_a_readable_manifest_with_a_bad_version_is_reported(self, tmp_path, lint):
        """POSITIVE CONTROL for every case below. Without it, "no problems"
        four times reads as four passes rather than one working check and three
        blind spots — which is exactly how this defect survived."""
        problems = lint.lint_skill(_skill(tmp_path, "ok", _wellformed("ok")))
        assert problems, "the control must report something, or the suite proves nothing"
        assert any("SemVer" in p for p in problems), problems

    def test_a_readable_manifest_with_a_good_version_is_clean(self, tmp_path, lint):
        """NEGATIVE CONTROL: the check must not report on every input."""
        raw = b"---\nname: fine\ndescription: D.\n---\n"
        assert lint.lint_skill(_skill(tmp_path, "fine", raw)) == []


class TestAnUnreadableManifestIsAFindingNotAnExemption:
    """A skill is "versioned" iff its frontmatter declares a version, so a
    manifest the linter cannot read reported as an unversioned pre-release and
    skipped every rule. A UTF-8 BOM is invisible in most editors and is exactly
    what a Windows editor or a careless shell redirect produces.
    """

    @pytest.mark.parametrize("label,raw,expect", [
        ("utf-8 BOM", "﻿" + f"---\nname: b\ndescription: D.\n{BAD_VERSION}\n---\n",
         "BOM"),
        ("blank line before the fence", f"\n---\nname: b\ndescription: D.\n{BAD_VERSION}\n---\n",
         "--- frontmatter fence"),
        ("no closing fence", f"---\nname: b\ndescription: D.\n{BAD_VERSION}\n",
         "closing"),
        ("unparseable YAML", f"---\nname: [unclosed\n{BAD_VERSION}\n---\n",
         "unparseable YAML"),
        ("frontmatter is a list", "---\n- just\n- a list\n---\n",
         "not a mapping"),
    ])
    def test_it_is_reported_with_a_reason(self, tmp_path, lint, label, raw, expect):
        problems = lint.lint_skill(_skill(tmp_path, "broken", raw.encode("utf-8")))
        assert problems, f"{label}: silently exempted"
        assert any(expect in p for p in problems), (label, problems)

    def test_invalid_utf8_is_reported(self, tmp_path, lint):
        problems = lint.lint_skill(_skill(tmp_path, "bad-bytes", b"---\nname: \xff\xfe\n---\n"))
        assert any("not valid UTF-8" in p for p in problems), problems

    def test_the_report_names_the_skill(self, tmp_path, lint):
        problems = lint.lint_skill(_skill(tmp_path, "named-skill",
                                          ("﻿---\nname: x\n---\n").encode("utf-8")))
        assert any("named-skill" in p for p in problems), problems


class TestWhatRemainsExempt:
    def test_a_directory_with_no_manifest_is_not_a_skill(self, tmp_path, lint):
        """Deliberately still exempt: a directory without a SKILL.md is not a
        skill, and `lint-skill-md` owns that question."""
        assert lint.lint_skill(_skill(tmp_path, "no-manifest", None)) == []

    def test_an_unversioned_skill_stays_exempt(self, tmp_path, lint):
        """Also deliberate, and documented in the script: unversioned means
        pre-release. The fix must not turn every prototype into a failure."""
        raw = b"---\nname: proto\ndescription: A prototype.\n---\n"
        assert lint.lint_skill(_skill(tmp_path, "proto", raw)) == []


def _versioned(tmp_path: Path, name: str, version: str = "1.2.3", **files: str) -> Path:
    """A skill that is versioned and internally consistent, plus whatever extra
    manifests a case wants to break."""
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: D.\nversion: {version}\n---\n", encoding="utf-8")
    (d / "CHANGELOG.md").write_text(f"## [{version}]\n- x\n", encoding="utf-8")
    for filename, body in files.items():
        (d / filename.replace("__", ".")).write_text(body, encoding="utf-8")
    return d


class TestPackageManifestAgreement:
    """This rule had NO test at all — replacing `_package_json_version` with
    `return None` survived the suite, so the whole agreement check could vanish
    green. These are the controls that make the unreadable cases below mean
    something.
    """

    def test_a_disagreeing_pyproject_is_reported(self, tmp_path, lint):
        d = _versioned(tmp_path, "py-bad", pyproject__toml='[project]\nversion = "9.9.9"\n')
        assert any("pyproject" in p and "9.9.9" in p for p in lint.lint_skill(d))

    def test_a_disagreeing_package_json_is_reported(self, tmp_path, lint):
        d = _versioned(tmp_path, "js-bad", package__json='{"version": "9.9.9"}')
        assert any("package.json" in p and "9.9.9" in p for p in lint.lint_skill(d))

    def test_agreeing_manifests_are_clean(self, tmp_path, lint):
        d = _versioned(tmp_path, "agree",
                       pyproject__toml='[project]\nversion = "1.2.3"\n',
                       package__json='{"version": "1.2.3"}')
        assert lint.lint_skill(d) == []

    def test_absent_manifests_stay_exempt(self, tmp_path, lint):
        """A skill with no pyproject/package.json has nothing to disagree with."""
        assert lint.lint_skill(_versioned(tmp_path, "bare")) == []


class TestAnUnreadablePackageManifestIsAlsoAFinding:
    """The same defect class as the SKILL.md fix, in two sibling readers of the
    same file: `_pyproject_version` and `_package_json_version` converted an
    unreadable file into `None`, which is what "no such file" also returns. The
    agreement rule then silently stopped applying to exactly the file most
    likely to be wrong.
    """

    @pytest.mark.parametrize("filename,body,expect", [
        ("pyproject__toml", "[project\nversion = broken", "pyproject.toml could not be read"),
        ("package__json", '{"version": ', "package.json could not be read"),
        ("package__json", '["not", "an", "object"]', "not a JSON object"),
        ("package__json", '{"version": null}', "declares a null version"),
        ("pyproject__toml", '[project]\nversion =\n', "could not be read"),
    ])
    def test_it_is_reported_rather_than_treated_as_absent(
        self, tmp_path, lint, filename, body, expect
    ):
        d = _versioned(tmp_path, f"broken-{abs(hash((filename, body, expect)))}", **{filename: body})
        problems = lint.lint_skill(d)
        assert problems, f"{filename}={body!r} silently exempted"
        assert any(expect in p for p in problems), problems


class TestAnEmptyVersionIsADeclarationNotAnAbsence:
    def test_a_null_skill_version_is_reported(self, tmp_path, lint):
        """`version:` with no value is an author who meant to version the skill
        and did not finish — not a pre-release."""
        d = tmp_path / "nullver"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: nullver\ndescription: D.\nversion:\n---\n",
                                    encoding="utf-8")
        assert any("empty version" in p for p in lint.lint_skill(d)), lint.lint_skill(d)

    def test_a_null_metadata_version_is_reported(self, tmp_path, lint):
        d = tmp_path / "nullmeta"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: nullmeta\ndescription: D.\nmetadata:\n  version:\n---\n", encoding="utf-8")
        assert any("empty version" in p for p in lint.lint_skill(d)), lint.lint_skill(d)

    def test_a_genuinely_absent_version_is_still_exempt(self, tmp_path, lint):
        """CONTROL: the two cases above must not turn every prototype into a
        failure — that is the overshoot this rule invites."""
        d = tmp_path / "proto2"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: proto2\ndescription: D.\n---\n", encoding="utf-8")
        assert lint.lint_skill(d) == []


class TestTheFenceMustBeExact:
    def test_a_fence_with_a_suffix_is_not_a_fence(self, tmp_path, lint):
        d = tmp_path / "suffixed"
        d.mkdir()
        (d / "SKILL.md").write_text("---yaml\nname: s\ndescription: D.\nversion: 1.0.0\n---\n",
                                    encoding="utf-8")
        problems = lint.lint_skill(d)
        # Assert the REASON, not merely that something was reported. Accepting
        # the suffix still produces a finding — "unparseable YAML", because the
        # leftover `yaml` line breaks the parse — so a truthiness assertion
        # passed either way and a mutation reverting the fence check survived.
        assert any("frontmatter fence" in x for x in problems), problems

    def test_a_plain_fence_still_parses(self, tmp_path, lint):
        """CONTROL for the case above."""
        d = _versioned(tmp_path, "plain-fence")
        assert lint.lint_skill(d) == []
