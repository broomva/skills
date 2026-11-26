import json
import os
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

    def test_an_errored_DENIAL_assertion_is_INVALID_not_FAIL(self):
        # The subtle one: a probe that crashed proves nothing about what its
        # subject cannot reach, even though the probe was checking a denial.
        # "Proves nothing" is the definition of INVALID. Grading it FAIL charges
        # the apparatus's crash to the subject's account, which is the same
        # category error as grading a `skipped` probe.
        cases = [c("ctl", "control", "pass"),
                 c("reachable", "assertion", "pass"),
                 c("egress denied", "assertion", "error")]
        r = run_verdict(cases)
        assert r.verdict == "INVALID"
        assert "egress denied" in r.culprits

    def test_a_lone_errored_assertion_is_INVALID(self):
        # Asserting only `!= "PASS"` here would hold under the OLD broken
        # behaviour (FAIL) as well as the new one, so it could not tell the fix
        # from the defect. Name the verdict.
        cases = [c("ctl", "control", "pass"), c("egress denied", "assertion", "error")]
        assert run_verdict(cases).verdict == "INVALID"


class TestAControlOnlySuiteMeasuresNothing:
    """The mirror image of the headline bug, and just as vacuous. A run whose
    controls all pass and which then asserts nothing has demonstrated that the
    apparatus works and NOTHING about the subject. Returning PASS there greens
    the gate on an empty measurement."""

    def test_a_control_only_suite_is_INVALID_not_PASS(self):
        assert run_verdict([c("bash executes", "control", "pass")]).verdict == "INVALID"

    def test_several_green_controls_and_no_assertion_is_still_INVALID(self):
        cases = [c("bash executes", "control", "pass"),
                 c("cwd is tenant dir", "control", "pass")]
        assert run_verdict(cases).verdict == "INVALID"

    def test_one_assertion_is_enough_to_be_a_measurement(self):
        # POSITIVE CONTROL for the two above: they assert a NON-PASS verdict and
        # would both hold if run_verdict were broken into never returning PASS.
        cases = [c("bash executes", "control", "pass"),
                 c("write outside denied", "assertion", "pass")]
        assert run_verdict(cases).verdict == "PASS"


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
        r = self._run([{"name": "ctl", "kind": "control", "outcome": "pass"},
                       {"name": "denied", "kind": "assertion", "outcome": "pass"}])
        assert r.returncode == 0 and "PASS" in r.stdout

    def test_a_lone_errored_assertion_exits_2_not_1(self):
        r = self._run([{"name": "ctl", "kind": "control", "outcome": "pass"},
                       {"name": "egress denied", "kind": "assertion", "outcome": "error"}])
        assert r.returncode == 2 and "INVALID" in r.stdout

    def test_a_control_only_run_exits_2_not_0(self):
        r = self._run([{"name": "ctl", "kind": "control", "outcome": "pass"}])
        assert r.returncode == 2 and "INVALID" in r.stdout

    def test_fail_exits_1(self):
        r = self._run([{"name": "ctl", "kind": "control", "outcome": "pass"},
                       {"name": "a", "kind": "assertion", "outcome": "fail"}])
        assert r.returncode == 1 and "FAIL" in r.stdout

    def test_invalid_exits_2(self):
        r = self._run([{"name": "a", "kind": "assertion", "outcome": "pass"}])
        assert r.returncode == 2 and "INVALID" in r.stdout

    def test_unparseable_input_exits_2_not_0(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "-"],
                           input="{not json", text=True, capture_output=True)
        assert r.returncode == 2

    def _run_file(self, path):
        return subprocess.run([sys.executable, str(SCRIPT), str(path)],
                              text=True, capture_output=True)

    def test_a_readable_file_is_graded_at_all(self, tmp_path):
        """POSITIVE CONTROL for the two tests below, and the reason they mean
        anything. Both of them assert a NON-ZERO exit; if the file branch were
        broken outright they would still pass, and the suite would be the very
        all-denials matrix this skill refuses. This case must SUCCEED."""
        f = tmp_path / "cases.json"
        f.write_text(json.dumps([{"name": "ctl", "kind": "control", "outcome": "pass"},
                                 {"name": "denied", "kind": "assertion", "outcome": "pass"}]))
        r = self._run_file(f)
        assert r.returncode == 0 and "PASS" in r.stdout

    def test_a_missing_file_is_INVALID_not_FAIL(self, tmp_path):
        """Unreadable is not unparseable. Exit 1 would claim an assertion did
        not hold -- a finding about the subject -- when nothing was read at all."""
        r = self._run_file(tmp_path / "nope.json")
        assert r.returncode == 2, r.stderr
        assert "INVALID" in r.stderr and "Traceback" not in r.stderr

    def test_a_directory_is_INVALID_not_FAIL(self, tmp_path):
        r = self._run_file(tmp_path)
        assert r.returncode == 2, r.stderr
        assert "INVALID" in r.stderr and "Traceback" not in r.stderr

    @pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                        reason="root reads a 0o000 file, so the case cannot arise")
    def test_an_unreadable_file_is_INVALID_not_FAIL(self, tmp_path):
        """Distinct from missing and from a directory: the path resolves and the
        file exists, and open() still raises. PermissionError is an OSError, so
        this passes for the same reason -- but only a test proves the reason
        holds for every OSError rather than for FileNotFoundError alone."""
        f = tmp_path / "cases.json"
        f.write_text("[]")
        f.chmod(0o000)
        try:
            r = self._run_file(f)
        finally:
            f.chmod(0o600)
        assert r.returncode == 2, r.stderr
        assert "INVALID" in r.stderr and "Traceback" not in r.stderr

    def test_a_usage_error_is_INVALID(self):
        r = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True)
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


@pytest.mark.parametrize('control', ['pass', 'fail', 'missing', 'error', 'skipped'])
@pytest.mark.parametrize('target', ['detected', 'not_detected', 'error', 'skipped'])
@pytest.mark.parametrize('absence_refutes', [True, False])
def test_measurement_conclusions_require_controls_and_predeclared_falsification(control, target, absence_refutes):
    from verdict import measurement_verdict
    raw = {'claim': 'target generates signal', 'conditions': 'run-1, sensitivity 0.1',
           'observation_ref': 'raw.json#target', 'control_ref': 'raw.json#control',
           'falsification_criterion': 'no signal above threshold with live control',
           'target_outcome': target, 'positive_control': control,
           'absence_refutes': absence_refutes}
    import jsonschema
    result = measurement_verdict(raw)
    schema = json.loads((SCRIPT.parents[1] / 'references/measurement.schema.json').read_text())
    jsonschema.validate(result, schema)
    actual = result['claim_verdict']
    if control != 'pass':
        assert actual == 'inconclusive_no_positive_control'
    elif target in ('error', 'skipped'):
        assert actual == 'inconclusive'
    elif target == 'detected':
        assert actual == 'detected'
    else:
        assert actual == ('refuted' if absence_refutes else 'not_detected')


def test_measurement_control_requires_receipt():
    from verdict import measurement_verdict
    with pytest.raises(ValueError):
        measurement_verdict({'claim': 'c', 'conditions': 'run', 'observation_ref': 'raw',
                             'falsification_criterion': 'no signal', 'absence_refutes': True,
                             'target_outcome': 'not_detected', 'positive_control': 'pass'})


def test_json_cli_preserves_invalid_vs_refuted(tmp_path):
    path = tmp_path / 'cases.json'
    assertions = [{'name': 'boundary held', 'kind': 'assertion', 'outcome': 'fail'}]
    for payload, expected, code in [
        ([], 'inconclusive_no_positive_control', 2),
        (assertions, 'inconclusive_no_positive_control', 2),
        ([{'name': 'live', 'kind': 'control', 'outcome': 'pass'}] + assertions, 'refuted', 1),
    ]:
        path.write_text(json.dumps(payload), encoding='utf-8')
        result = subprocess.run([sys.executable, str(SCRIPT), '--json', str(path)], capture_output=True, text=True)
        assert result.returncode == code
        assert json.loads(result.stdout)['claim_verdict'] == expected


@pytest.mark.parametrize('extra', [{}, {'control_ref': None}])
def test_missing_control_output_conforms_to_published_schema(extra):
    import jsonschema
    from verdict import measurement_verdict
    raw = {'claim': 'target signal', 'conditions': 'run-1', 'observation_ref': 'raw',
           'falsification_criterion': 'controlled null', 'absence_refutes': True,
           'target_outcome': 'not_detected', 'positive_control': 'missing', **extra}
    result = measurement_verdict(raw)
    schema = json.loads((SCRIPT.parents[1] / 'references/measurement.schema.json').read_text())
    jsonschema.validate(result, schema)
    assert result['control_ref'] is None
    assert result['claim_verdict'] == 'inconclusive_no_positive_control'


@pytest.mark.parametrize('extra', [{'control_ref': {}}, {'run_id': 'unrecognized'}])
def test_untyped_or_unknown_measurement_fields_are_invalid(extra):
    from verdict import measurement_verdict
    raw = {'claim': 'target signal', 'conditions': 'run-1', 'observation_ref': 'raw',
           'falsification_criterion': 'controlled null', 'absence_refutes': True,
           'target_outcome': 'not_detected', 'positive_control': 'missing', **extra}
    with pytest.raises(ValueError):
        measurement_verdict(raw)


@pytest.mark.parametrize('overrides,expected_verdict,expected_code', [
    ({'target_outcome': 'detected', 'positive_control': 'pass', 'absence_refutes': True}, 'detected', 0),
    ({'target_outcome': 'not_detected', 'positive_control': 'pass', 'absence_refutes': True}, 'refuted', 1),
    ({'target_outcome': 'not_detected', 'positive_control': 'pass', 'absence_refutes': False}, 'not_detected', 2),
    ({'target_outcome': 'not_detected', 'positive_control': 'missing', 'absence_refutes': True}, 'inconclusive_no_positive_control', 2),
    ({'target_outcome': 'skipped', 'positive_control': 'pass', 'absence_refutes': True}, 'inconclusive', 2),
])
def test_measurement_cli_exit_codes_and_json_contract(tmp_path, overrides, expected_verdict, expected_code):
    import jsonschema
    raw = {
        'claim': 'target signal',
        'conditions': 'run-1',
        'observation_ref': 'raw.json#target',
        'control_ref': 'raw.json#control',
        'falsification_criterion': 'controlled null',
        **overrides,
    }
    path = tmp_path / 'measurement.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--measurement', str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected_code
    payload = json.loads(result.stdout)
    assert payload['claim_verdict'] == expected_verdict
    schema = json.loads((SCRIPT.parents[1] / 'references/measurement.schema.json').read_text(encoding='utf-8'))
    jsonschema.validate(payload, schema)


def test_measurement_cli_invalid_or_missing_input_exits_2_json(tmp_path):
    bad = tmp_path / 'bad.json'
    bad.write_text(json.dumps({'claim': ''}), encoding='utf-8')
    for target in (bad, tmp_path / 'missing.json'):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), '--measurement', str(target)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload['verdict'] == 'INVALID'
        assert payload['claim_verdict'] == 'inconclusive'
