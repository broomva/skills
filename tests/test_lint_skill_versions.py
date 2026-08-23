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
