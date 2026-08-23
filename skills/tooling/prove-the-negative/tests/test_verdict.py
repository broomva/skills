import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest
from verdict import Case, parse_cases, run_verdict  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verdict.py"


def c(name, kind, outcome):
    return Case(name, kind, outcome)


class TestTheInferenceThisRefuses:
    def test_all_denials_and_no_control_is_INVALID_not_PASS(self):
        # THE bug. A suite of denials with nothing that must succeed reports
        # health when its subject is switched off. Measured 2026-08-22: a
        # sandbox that could not start denied every probe and was read as
        # confinement working.
        cases = [c("write outside denied", "assertion", "pass"),
                 c("sudo denied", "assertion", "pass"),
                 c("egress denied", "assertion", "pass")]
        assert run_verdict(cases).verdict == "INVALID"

    def test_a_failed_control_makes_the_whole_run_INVALID(self):
        cases = [c("bash executes", "control", "fail"),
                 c("write outside denied", "assertion", "pass")]
        r = run_verdict(cases)
        assert r.verdict == "INVALID"
        assert "bash executes" in r.culprits

    def test_INVALID_is_not_FAIL(self):
        # A caller that collapses them re-creates the bug: "we learned nothing"
        # becomes "we found a problem" and is eventually ignored as noise.
        no_control = run_verdict([c("x", "assertion", "pass")])
        real_fail = run_verdict([c("ctl", "control", "pass"), c("x", "assertion", "fail")])
        assert no_control.verdict == "INVALID"
        assert real_fail.verdict == "FAIL"
        assert no_control.verdict != real_fail.verdict


class TestErrorsNeverPass:
    def test_an_errored_control_is_INVALID(self):
        # A crashed apparatus did not demonstrate liveness.
        assert run_verdict([c("ctl", "control", "error")]).verdict == "INVALID"

    def test_an_errored_DENIAL_assertion_is_FAIL_not_PASS(self):
        # The subtle one: a probe that crashed proves nothing about what its
        # subject cannot reach, even though the probe was checking a denial.
        cases = [c("ctl", "control", "pass"), c("egress denied", "assertion", "error")]
        r = run_verdict(cases)
        assert r.verdict == "FAIL"
        assert "egress denied" in r.culprits


class TestHappyPath:
    def test_controls_green_and_assertions_hold_is_PASS(self):
        cases = [c("bash executes", "control", "pass"),
                 c("cwd is tenant dir", "control", "pass"),
                 c("write outside denied", "assertion", "pass")]
        assert run_verdict(cases).verdict == "PASS"

    def test_an_empty_case_set_is_INVALID(self):
        # Vacuous: no controls means no liveness evidence, and reporting PASS
        # over zero cases is the purest form of the bug.
        assert run_verdict([]).verdict == "INVALID"


class TestParsingRejectsRatherThanCoerces:
    @pytest.mark.parametrize("bad", [
        [{"name": "x", "kind": "assertion", "outcome": "ok"}],      # unknown outcome
        [{"name": "x", "kind": "check", "outcome": "pass"}],        # unknown kind
        [{"name": "", "kind": "control", "outcome": "pass"}],       # no name
        [{"kind": "control", "outcome": "pass"}],                   # missing name
        ["not an object"],
        {"not": "a list"},
    ])
    def test_malformed_input_raises(self, bad):
        # Coercing would be the same class of bug: defaulting an unknown
        # outcome to "pass" greens a run silently; defaulting a mistyped kind to
        # "assertion" drops the only control and makes the suite unfalsifiable.
        with pytest.raises(ValueError):
            parse_cases(bad)

    def test_valid_input_parses(self):
        parsed = parse_cases([{"name": "x", "kind": "control", "outcome": "pass"}])
        assert parsed == [Case("x", "control", "pass")]


class TestExitCodes:
    """The exit code IS the contract for CI; a caller must be able to tell
    INVALID from FAIL without parsing prose."""

    def _run(self, cases):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "-"],
            input=json.dumps(cases), text=True, capture_output=True,
        )

    def test_pass_exits_0(self):
        r = self._run([{"name": "ctl", "kind": "control", "outcome": "pass"}])
        assert r.returncode == 0 and "PASS" in r.stdout

    def test_fail_exits_1(self):
        r = self._run([{"name": "ctl", "kind": "control", "outcome": "pass"},
                       {"name": "a", "kind": "assertion", "outcome": "fail"}])
        assert r.returncode == 1 and "FAIL" in r.stdout

    def test_invalid_exits_2(self):
        r = self._run([{"name": "a", "kind": "assertion", "outcome": "pass"}])
        assert r.returncode == 2 and "INVALID" in r.stdout

    def test_unreadable_input_exits_2_not_0(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "-"],
                           input="{not json", text=True, capture_output=True)
        assert r.returncode == 2


class TestSkippedIsAHoleNotAResult:
    """A probe the subject declined to run measured nothing. Scoring it FAIL
    raises a false alarm; scoring it PASS is the original bug in miniature."""

    def test_a_skipped_assertion_makes_the_run_INVALID(self):
        cases = [c("ctl", "control", "pass"),
                 c("write outside denied", "assertion", "skipped")]
        r = run_verdict(cases)
        assert r.verdict == "INVALID"
        assert "write outside denied" in r.culprits

    def test_skipped_is_not_FAIL(self):
        # Measured: an agent declined a probe on its own judgment and a
        # narration-reading grader recorded a confinement failure that had not
        # happened. A disposition is not a boundary result in either direction.
        skipped = run_verdict([c("ctl", "control", "pass"), c("x", "assertion", "skipped")])
        broke = run_verdict([c("ctl", "control", "pass"), c("x", "assertion", "fail")])
        assert skipped.verdict == "INVALID"
        assert broke.verdict == "FAIL"

    def test_skipped_is_not_PASS(self):
        assert run_verdict([c("ctl", "control", "pass"),
                            c("x", "assertion", "skipped")]).verdict != "PASS"

    def test_a_skipped_CONTROL_is_INVALID_too(self):
        assert run_verdict([c("ctl", "control", "skipped")]).verdict == "INVALID"

    def test_skipped_parses(self):
        assert parse_cases([{"name": "x", "kind": "assertion", "outcome": "skipped"}])[0].outcome == "skipped"
