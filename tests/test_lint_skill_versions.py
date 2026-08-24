"""Tests for scripts/lint_skill_versions.py.

The script had no test file. Every case here drives the real `lint_skill`
against a fixture skill on disk, and every "this is reported" case is paired
with a control that must come back clean — because the defect these were
written for produced *no problems* for three different broken manifests, which
is indistinguishable from three passes unless something in the set must fail.
"""

from __future__ import annotations

import importlib.util
import os
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
        """NEGATIVE CONTROL: the check must not report on every input.

        The fixture used to carry NO version, so this passed by EXEMPTION — the
        unversioned early return — and would have stayed green with every rule
        below it deleted. It now declares a real version and a matching
        CHANGELOG, so "clean" means the rules ran and found nothing.
        """
        assert lint.lint_skill(_versioned(tmp_path, "fine")) == []


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
        # Malformed SYNTAX and an unreadable FILE are different findings and now
        # say so: calling a truncated JSON literal "could not be read" pointed a
        # reader at permissions when the defect was a missing brace.
        ("pyproject__toml", "[project\nversion = broken", "pyproject.toml is not valid TOML"),
        ("package__json", '{"version": ', "package.json is not valid JSON"),
        ("package__json", '["not", "an", "object"]', "not a JSON object"),
        ("package__json", '{"version": null}', "declares a null version"),
        ("pyproject__toml", '[project]\nversion =\n', "is not valid TOML"),
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


class TestTheFourthReaderFailsTheOtherWay:
    """`_changelog_has_version` called `read_text()` with no error handling, so
    a CHANGELOG that is not valid UTF-8 CRASHED the whole lint with a traceback
    rather than being reported.

    Same root defect as the other three readers — absent, present-and-readable,
    and unreadable collapsed into two states — with the opposite symptom. Found
    by auditing every reader in the file after missing this class twice here,
    rather than by waiting for a review round to name it: hunting only for
    silent passes would not have surfaced a crash.
    """

    def _with_changelog(self, tmp_path, name, raw: bytes):
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: D.\nversion: 1.0.0\n---\n", encoding="utf-8")
        (d / "CHANGELOG.md").write_bytes(raw)
        return d

    def test_a_changelog_missing_the_version_is_reported(self, tmp_path, lint):
        """CONTROL: the rule still works."""
        problems = lint.lint_skill(self._with_changelog(tmp_path, "missing", b"## [9.9.9]\n"))
        assert any("CHANGELOG.md missing" in p for p in problems), problems

    def test_a_correct_changelog_is_clean(self, tmp_path, lint):
        """CONTROL: and does not report on every input."""
        assert lint.lint_skill(self._with_changelog(tmp_path, "good", b"## [1.0.0]\n")) == []

    def test_an_unreadable_changelog_is_reported_not_raised(self, tmp_path, lint):
        d = self._with_changelog(tmp_path, "badbytes", b"## [1.0.0]\n- \xff\xfe not utf-8\n")
        problems = lint.lint_skill(d)          # must not raise
        assert any("CHANGELOG.md" in p and "not valid UTF-8" in p for p in problems), problems

    def test_an_unreadable_changelog_does_not_masquerade_as_a_missing_section(
        self, tmp_path, lint
    ):
        """The two states must stay distinguishable in the REPORT, not just in
        the exit code: "you forgot to document the release" and "I could not
        read your changelog" send the author to different places."""
        d = self._with_changelog(tmp_path, "distinct", b"## [1.0.0]\n- \xff\xfe\n")
        problems = lint.lint_skill(d)
        assert not any("missing a '## [" in p for p in problems), problems


class TestAnUnreadableManifestReachesMain:
    def test_an_unreadable_manifest_reaches_the_exit_code(self, tmp_path, lint, capsys):
        """The finding must reach `main`'s exit code and output, not merely the
        helper. (The versioned TALLY is deliberately not asserted: it is printed
        only on the success path, which an unreadable manifest can never reach,
        so any claim about it is unobservable.)"""
        good = tmp_path / "good"
        good.mkdir()
        (good / "SKILL.md").write_text(
            "---\nname: good\ndescription: D.\nversion: 1.0.0\n---\n", encoding="utf-8")
        (good / "CHANGELOG.md").write_text("## [1.0.0]\n", encoding="utf-8")
        bom = tmp_path / "bom"
        bom.mkdir()
        (bom / "SKILL.md").write_bytes(
            "﻿---\nname: bom\ndescription: D.\nversion: 2.0.0\n---\n".encode("utf-8"))
        lint._SKILLS_DIR = tmp_path
        assert lint.main() == 1                      # the unreadable one is a finding
        err = capsys.readouterr().err
        assert "bom" in err, err


class TestEveryReaderSurvivesAnUnreadableFILE:
    """The round-2 surviving mutation: removing `OSError` from a package
    reader's exception tuple failed nothing, because every "unreadable" test
    exercised malformed SYNTAX — never a file the OS refuses to open.

    Each reader had its own exception tuple catching a different subset, so a
    permission-denied SKILL.md and a non-UTF-8 pyproject.toml both escaped as
    tracebacks while the suite stayed green. One shared reader now, and these
    cases pin it per file.
    """

    FILES = ["SKILL.md", "pyproject.toml", "package.json", "CHANGELOG.md"]

    def _skill(self, tmp_path, name):
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: D.\nversion: 1.0.0\n---\n", encoding="utf-8")
        (d / "CHANGELOG.md").write_text("## [1.0.0]\n", encoding="utf-8")
        (d / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n', encoding="utf-8")
        (d / "package.json").write_text('{"version": "1.0.0"}', encoding="utf-8")
        return d

    def test_a_fully_readable_skill_is_clean(self, tmp_path, lint):
        """CONTROL: all four files present and consistent."""
        assert lint.lint_skill(self._skill(tmp_path, "allgood")) == []

    @pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                        reason="root can read a 0o000 file, so the case cannot arise")
    @pytest.mark.parametrize("filename", FILES)
    def test_a_permission_denied_file_is_reported_not_raised(self, tmp_path, lint, filename):
        d = self._skill(tmp_path, f"denied-{filename.replace('.', '-')}")
        target = d / filename
        target.chmod(0o000)
        try:
            problems = lint.lint_skill(d)      # must not raise
        finally:
            target.chmod(0o644)
        assert problems, f"{filename}: an unopenable file was silently exempted"
        assert any(filename in p and "could not be read" in p for p in problems), problems

    @pytest.mark.parametrize("filename", ["pyproject.toml", "package.json", "CHANGELOG.md"])
    def test_a_non_utf8_file_is_reported_not_raised(self, tmp_path, lint, filename):
        """The mirror gap: the package readers caught OSError but not
        UnicodeDecodeError, so invalid bytes tracebacked."""
        d = self._skill(tmp_path, f"bytes-{filename.replace('.', '-')}")
        (d / filename).write_bytes(b"\xff\xfe not utf-8 at all\n")
        problems = lint.lint_skill(d)          # must not raise
        assert any(filename in p and "not valid UTF-8" in p for p in problems), problems


class TestBothFenceEndsAreExact:
    """The opening fence had a test; the CLOSING one did not, and a mutation
    loosening it to `startswith("---")` survived. I had written that both ends
    were exact — the code was, the suite was not."""

    def _skill(self, tmp_path, name, body: str):
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")
        (d / "CHANGELOG.md").write_text("## [1.0.0]\n", encoding="utf-8")
        return d

    def test_a_closing_fence_with_a_suffix_is_not_a_fence(self, tmp_path, lint):
        body = "---\nname: closed-badly\ndescription: D.\nversion: 1.0.0\n---yaml\n"
        problems = lint.lint_skill(self._skill(tmp_path, "closed-badly", body))
        assert any("no closing --- fence" in p for p in problems), problems

    def test_a_plain_closing_fence_parses(self, tmp_path, lint):
        """CONTROL for the case above."""
        body = "---\nname: closed-well\ndescription: D.\nversion: 1.0.0\n---\n"
        assert lint.lint_skill(self._skill(tmp_path, "closed-well", body)) == []


class TestABrokenSymlinkIsNotAnAbsence:
    """The round-3 BLOCKER, and the sharpest instance of this file's own defect
    class: four `.exists()` preflights sat IN FRONT of the shared reader written
    to eliminate exactly this. `.exists()` follows a symlink and answers False
    for a dangling one, so a broken link named SKILL.md made the skill look
    unversioned and exempted it from every rule — measured against a live
    control that reports two problems for the identical real file.
    """

    @pytest.mark.parametrize("filename", ["SKILL.md", "pyproject.toml", "package.json", "CHANGELOG.md"])
    def test_each_reader_reports_a_dangling_link(self, tmp_path, lint, filename):
        d = _versioned(tmp_path, f"link-{filename.replace('.', '-')}")
        target = d / filename
        if target.exists():
            target.unlink()
        target.symlink_to(tmp_path / "no-such-target")
        problems = lint.lint_skill(d)
        assert problems, f"a dangling {filename} silently exempted the skill"
        assert any("broken symlink" in p for p in problems), problems

    def test_a_genuinely_absent_optional_manifest_is_still_exempt(self, tmp_path, lint):
        """CONTROL for the above: absent must keep meaning absent, or the fix
        for a false green is just a false red."""
        assert lint.lint_skill(_versioned(tmp_path, "no-optionals")) == []

    def test_a_directory_without_a_skill_md_is_not_a_skill(self, tmp_path, lint):
        d = tmp_path / "empty"
        d.mkdir()
        assert lint.lint_skill(d) == []


class TestSemVerIsAsciiAndAnchored:
    """`\\d` is Unicode-aware and `$` matches before a trailing newline, so
    `.match()` on `^...$` accepted both "1.2.3\\n" and the Arabic-Indic
    "1٢.0.0" as valid SemVer."""

    # Exercised through `lint_skill`, not against `_SEMVER` directly. Asserting
    # on the compiled object tests the pattern; it does not test that the linter
    # USES it correctly, and a `fullmatch` -> `match` mutation at the call site
    # survived a suite that only ever asked the regex.
    @pytest.mark.parametrize("literal", [
        '"1.2.3\\n"',   # trailing newline: `$` matches before it, `fullmatch` does not
        '"1.2.3 "',      # trailing space
        '"1٢.0.0"',      # Arabic-Indic digit, matched by a Unicode-aware `\\d`
        '"1.2.3-1٢"',
        '"v1.2.3"',
        '"1.2"',
    ])
    def test_invalid_versions_are_rejected(self, tmp_path, lint, literal):
        d = tmp_path / f"sv-{abs(hash(literal))}"
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nname: sv\ndescription: D.\nversion: {literal}\n---\n", encoding="utf-8")
        problems = lint.lint_skill(d)
        assert any("not valid SemVer" in p for p in problems), (literal, problems)

    @pytest.mark.parametrize("version", ["0.0.4", "1.2.3", "10.20.30", "1.2.3-rc.1", "1.2.3-rc.1+build.5"])
    def test_valid_versions_are_accepted(self, tmp_path, lint, version):
        """CONTROL: tightening must not reject the spec's own examples — the
        false-red half of the proof."""
        d = _versioned(tmp_path, f"ok-{abs(hash(version))}", version=f'"{version}"')
        assert not [p for p in lint.lint_skill(d) if "not valid SemVer" in p]


class TestChangelogHeadingIsDeclaredNotMerelyMentioned:
    """`f"## [{version}]" in text` was a substring search, so a CHANGELOG that
    only SHOWED the heading — in a fenced usage example, or mid-sentence —
    satisfied the requirement to DECLARE the release."""

    @pytest.mark.parametrize("body,declared", [
        ("## [1.2.3]\n- x\n", True),
        ("## [1.2.3] - 2026-01-01\n", True),
        ("##   [1.2.3]\n", True),
        ("```\n## [1.2.3]\n```\n", False),
        ("~~~\n## [1.2.3]\n~~~\n", False),
        ("see the ## [1.2.3] section\n", False),
        ("### [1.2.3]\n", False),
        ("## [1.2.4]\n", False),
    ])
    def test_only_a_real_heading_counts(self, tmp_path, lint, body, declared):
        d = _versioned(tmp_path, f"cl-{abs(hash(body))}")
        (d / "CHANGELOG.md").write_text(body, encoding="utf-8")
        missing = [p for p in lint.lint_skill(d) if "CHANGELOG.md missing" in p]
        assert (not missing) == declared, (body, lint.lint_skill(d))


class TestEveryDeclarationIsChecked:
    """`metadata.version` had no POSITIVE test — deleting its extraction branch
    survived the suite — and the empty-version check ran only when NO canonical
    version was found, so one failed declaration hid behind one that worked."""

    def test_a_valid_metadata_version_is_used(self, tmp_path, lint):
        d = tmp_path / "meta-ok"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: meta-ok\ndescription: D.\nmetadata:\n  version: 2.0.0\n---\n",
            encoding="utf-8")
        (d / "CHANGELOG.md").write_text("## [2.0.0]\n", encoding="utf-8")
        assert lint.lint_skill(d) == []

    def test_a_metadata_version_is_actually_enforced(self, tmp_path, lint):
        """The other half: if `metadata.version` were ignored, this would be
        exempt rather than reported."""
        d = tmp_path / "meta-bad"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: meta-bad\ndescription: D.\nmetadata:\n  version: not-semver\n---\n",
            encoding="utf-8")
        assert any("not valid SemVer" in p for p in lint.lint_skill(d))

    def test_a_null_metadata_version_beside_a_valid_one_is_reported(self, tmp_path, lint):
        d = _versioned(tmp_path, "mixed")
        (d / "SKILL.md").write_text(
            "---\nname: mixed\ndescription: D.\nversion: 1.2.3\nmetadata:\n  version:\n---\n",
            encoding="utf-8")
        assert any("empty version" in p for p in lint.lint_skill(d)), lint.lint_skill(d)


class TestCrlfIsALineEndingNotAFenceDefect:
    def test_a_crlf_manifest_parses(self, tmp_path, lint):
        """Exact fence equality on a `split(chr(10))` left a trailing CR on every
        line, so every well-formed CRLF manifest read as having no frontmatter —
        a false RED introduced by the fix for a false GREEN."""
        d = tmp_path / "crlf"
        d.mkdir()
        (d / "SKILL.md").write_bytes(
            b"---\r\nname: crlf\r\ndescription: D.\r\nversion: 1.0.0\r\n---\r\nbody\r\n")
        (d / "CHANGELOG.md").write_text("## [1.0.0]\n", encoding="utf-8")
        assert lint.lint_skill(d) == []

    def test_the_crlf_value_is_not_truncated(self, tmp_path, lint):
        """Normalising only the LINES shifted the closing-fence offset by one
        byte per line, silently truncating the last value ("1.0.0" -> "1.0")."""
        d = tmp_path / "crlf-trunc"
        d.mkdir()
        (d / "SKILL.md").write_bytes(
            b"---\r\nname: t\r\ndescription: D.\r\nversion: 1.0.0\r\n---\r\n")
        fm, unreadable, present = lint._read_frontmatter(d / "SKILL.md")
        assert (present, unreadable) == (True, None)
        assert fm["version"] == "1.0.0", fm


class TestDiscoverySeesWhatTheReaderCanReport:
    """CI caught what this suite could not: every test above calls `lint_skill`
    directly, so none of them exercise DISCOVERY. On Python 3.11 `Path.rglob`
    filters candidates through `Path.exists()`, which follows symlinks, so a
    dangling SKILL.md was never yielded — the skill did not merely pass, it was
    never looked at, and the whole broken-symlink fix was unreachable from the
    real entry point. Version-dependent too: 3.12 lists it, 3.11 does not, so
    the local suite was green while CI proved the gate could not go red.
    """

    def _skills_tree(self, tmp_path, lint, monkeypatch):
        root = tmp_path / "skills" / "tooling"
        root.mkdir(parents=True)
        monkeypatch.setattr(lint, "_SKILLS_DIR", tmp_path / "skills")
        return root

    def test_a_dangling_manifest_is_discovered(self, tmp_path, lint, monkeypatch):
        root = self._skills_tree(tmp_path, lint, monkeypatch)
        (root / "dangling").mkdir()
        (root / "dangling" / "SKILL.md").symlink_to(tmp_path / "no-such-target")
        assert (root / "dangling") in lint._iter_skill_dirs()

    def test_the_entry_point_goes_red_on_a_dangling_manifest(
        self, tmp_path, lint, monkeypatch, capsys
    ):
        """Through `main()`, the way CI runs it — not through `lint_skill`."""
        root = self._skills_tree(tmp_path, lint, monkeypatch)
        (root / "dangling").mkdir()
        (root / "dangling" / "SKILL.md").symlink_to(tmp_path / "no-such-target")
        assert lint.main() == 1
        captured = capsys.readouterr()
        assert "broken symlink" in captured.out + captured.err

    def test_a_normal_tree_is_still_fully_discovered(self, tmp_path, lint, monkeypatch):
        """CONTROL: the walk must find everything rglob did, at any depth."""
        root = self._skills_tree(tmp_path, lint, monkeypatch)
        for rel in ["a", "b/skills/c", "d/e/f"]:
            (root / rel).mkdir(parents=True)
            (root / rel / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        found = lint._iter_skill_dirs()
        assert {(root / r) for r in ["a", "b/skills/c", "d/e/f"]} <= set(found)

    def test_extensions_are_still_excluded(self, tmp_path, lint, monkeypatch):
        root = self._skills_tree(tmp_path, lint, monkeypatch)
        (root / "x" / "extensions" / "priv").mkdir(parents=True)
        (root / "x" / "extensions" / "priv" / "SKILL.md").write_text(
            "---\nname: p\n---\n", encoding="utf-8")
        assert not [d for d in lint._iter_skill_dirs() if "extensions" in d.parts]
