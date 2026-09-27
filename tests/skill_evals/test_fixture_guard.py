"""The scrubber is only worth what the RECORD path is bound to (BRO-2030).

`runner.py` contained zero occurrences of the string `scrub`. Scrubbing was a separate
manual step, so a fixture recorded by anyone who did not know about it — or by any
branch on which `scrub.py` did not exist, which was every branch but one — was
unscrubbed by construction. Measured: a second agent's `p9` fixtures, recorded off
main, carried the operator's home directory in three files and the same
`emailAddress` / `organizationUuid` / `organizationName` triple in a fourth, while the
branch that had run the scrubber by hand had none of the former.

These tests assert the COUPLING, which is a different claim from "the patterns work"
(tests/skill_evals/test_scrub.py) and is the one that was missing. The mutation proof
for this file is:

    skills/governance/cross-review/scripts/mutation-proof.sh run \
      --target scripts/skill_evals/fixture_guard.py --strategy stub \
      --test 'python3 -m pytest tests/skill_evals/test_fixture_guard.py -q'

`fixture_guard.py` exists to be a surgical mutation target: stubbing it neuters exactly
the enforcement and nothing else, so a RED result means "the runner is bound to the
guard" rather than "the interpreter fell over".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals import fixture_guard as G  # noqa: E402
from skill_evals import runner as R  # noqa: E402
from skill_evals import scrub as S  # noqa: E402
from skill_evals.transcript import Transcript  # noqa: E402

# Imported, not re-declared: `test_scrub.py` defines the invented identity constants and
# carries the guard test that keeps them invented. Two copies would drift, and the copy
# that drifted back to a real value is the one nobody would notice.
#
# A sibling import via this directory rather than `tests.skill_evals.…`: there is
# deliberately no `__init__.py` here (see conftest.py — it would shadow the package under
# test), so the dotted form does not resolve.
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_scrub import FAKE_ORG_UUID, FAKE_USER_ID  # noqa: E402

#: One NDJSON line carrying the config leak, assembled so the tracked test file does
#: not itself contain an address-shaped literal the repo's secret scanner would flag.
#: json.dumps escapes the inner quotes exactly ONCE, which is the shape a real
#: recording has: a tool result whose text is a JSON document. Writing the backslashes
#: by hand here double-escapes them into a shape no fixture contains, and a test built
#: on that would pass against a scrubber that cannot read the real thing.
LEAKY_EVENT = json.dumps({
    "type": "user",
    "message": {"content": [{"type": "tool_result", "content": (
        '  "emailAddress": "ops@northwind-labs.co",\n'
        '  "organizationUuid": "' + FAKE_ORG_UUID + '",\n'
        '  "userID": "' + FAKE_USER_ID + '"'
    )}]},
})


def _live_runner(tmp_path: Path, **kw) -> R.LiveRunner:
    return R.LiveRunner(
        cli="/nonexistent/claude",
        record_dir=tmp_path / "rec",
        skill="demo",
        cli_version=R.EXPECTED_CLI_VERSION,
        fingerprint={"skill_md_sha256": "aa" * 32, "description_sha256": "bb" * 32},
        **kw,
    )


def _record(runner: R.LiveRunner, stdout: str, *, stderr: str = "") -> Path:
    t = Transcript.from_ndjson(stdout, exit_code=0, stderr=stderr, source="test", wall_ms=1)
    runner._record("case-01", 1, "the prompt", stdout, t)
    return Path(runner.record_dir) / "cases" / "case-01" / "trial-01.jsonl"


# ===========================================================================
# the coupling
# ===========================================================================


def test_record_writes_a_SCRUBBED_fixture(tmp_path):
    """The load-bearing assertion. Not "scrub.py works" — "--record calls it"."""
    path = _record(_live_runner(tmp_path), LEAKY_EVENT + "\n")
    written = path.read_text()
    assert "northwind-labs" not in written
    assert FAKE_ORG_UUID not in written
    assert S.scan(path.parent) == {}, "the fixture on disk is not scrub-clean"


def test_record_scrubs_the_STDERR_it_stores_in_the_meta(tmp_path):
    """The meta sidecar carries the last 4000 bytes of stderr, and a CLI that dies
    mid-run prints paths. Scrubbing the transcript and not the sidecar leaves the leak
    one file to the left."""
    runner = _live_runner(tmp_path)
    _record(runner, LEAKY_EVENT + "\n", stderr="failed reading /Users/somebody/.claude.json")
    meta = json.loads(
        (Path(runner.record_dir) / "cases" / "case-01" / "trial-01.meta.json").read_text()
    )
    assert "/Users/somebody" not in meta["stderr"]
    assert meta["stderr"] == "failed reading /Users/USER/.claude.json"


def test_the_meta_records_WHAT_was_redacted(tmp_path):
    """A reviewer should be able to see that a fixture was scrubbed and by which rules,
    without re-running anything. `scrubbed: {}` on a clean recording is meaningful too:
    it says the gate ran and found nothing, which is not the same as never running."""
    runner = _live_runner(tmp_path)
    _record(runner, LEAKY_EVENT + "\n")
    meta = json.loads(
        (Path(runner.record_dir) / "cases" / "case-01" / "trial-01.meta.json").read_text()
    )
    assert isinstance(meta["scrubbed"], dict)
    assert meta["scrubbed"], "redactions happened but the meta records none"


def test_record_FAILS_CLOSED_when_the_scrub_cannot_converge(tmp_path, monkeypatch):
    """A non-convergent rule — one whose replacement re-matches its own pattern — means
    the guard cannot say the bytes are clean. The only safe answer is to refuse: an
    unscrubbed fixture on disk is worse than no fixture, because somebody commits it.
    """
    import re

    # Grows on every pass: LEAK -> LEAKX -> LEAKXX. A rule whose replacement contains
    # its own pattern is the shape the temp-root rule had (its `/var/folders/XX/XXXX`
    # placeholder re-matched `/var/folders/[A-Za-z0-9_]+/[A-Za-z0-9_]+`).
    bad = ("never-converges", re.compile(r"LEAK"), "LEAKX")
    monkeypatch.setattr(S, "REDACTIONS", S.REDACTIONS + (bad,))
    runner = _live_runner(tmp_path)
    with pytest.raises(G.UnscrubbedFixture, match="not convergent"):
        _record(runner, json.dumps({"type": "x", "note": "LEAK"}) + "\n")
    assert not (Path(runner.record_dir) / "cases").exists(), (
        "the case directory was created despite the refusal — a partially written "
        "fixture set is the thing a later --replay would grade"
    )


def test_record_FAILS_CLOSED_when_a_redaction_breaks_the_JSON(tmp_path, monkeypatch):
    """Redaction is byte surgery on JSON. A rule that produces an illegal escape makes
    the line unparseable, replay scores the trial ERROR, and nothing re-read the file to
    notice. So the guard re-parses every line it is about to write."""
    import re

    monkeypatch.setattr(S, "REDACTIONS", (
        ("breaks-json", re.compile(r"note"), "no\\te"),
    ))
    runner = _live_runner(tmp_path)
    with pytest.raises(G.UnscrubbedFixture, match="no longer parses as JSON"):
        _record(runner, json.dumps({"type": "x", "note": "hello"}) + "\n")


def test_record_FAILS_CLOSED_when_scrubbing_drops_a_line(tmp_path, monkeypatch):
    """An event count that changes is structural damage, not redaction."""
    import re

    monkeypatch.setattr(S, "REDACTIONS", (("eats-a-line", re.compile(r"\n"), ""),))
    runner = _live_runner(tmp_path)
    with pytest.raises(G.UnscrubbedFixture, match="line count"):
        _record(runner, json.dumps({"a": 1}) + "\n" + json.dumps({"b": 2}) + "\n")


def test_the_escape_hatch_is_recorded_in_the_meta(tmp_path):
    """`--no-scrub` is allowed to exist and is not allowed to leave no trace. The meta
    says `false`, and fixture_pack refuses to publish a fixture that says so."""
    runner = _live_runner(tmp_path, scrub_recordings=False)
    path = _record(runner, LEAKY_EVENT + "\n")
    assert "northwind-labs" in path.read_text(), "--no-scrub did not skip scrubbing"
    meta = json.loads(path.with_suffix(".meta.json").read_text())
    assert meta["scrubbed"] is False


def test_scrubbing_is_ON_by_default():
    """The default is the whole point: a control you have to remember is not a control.
    Asserted on the dataclass so a future edit to the flag's default trips here."""
    assert R.LiveRunner.__dataclass_fields__["scrub_recordings"].default is True


# ===========================================================================
# gate 2 — what git tracks
# ===========================================================================


def test_the_tracked_fixture_scan_recognises_a_fixture_by_SHAPE(tmp_path):
    """`cases/<id>/trial-NN.jsonl` is what --record writes and what --replay reads, so
    it is the right thing to recognise. Matching on a DIRECTORY NAME is what let a
    fixture set recorded into `skills/orchestration/p9/evals/fixtures/` past a guard
    that only knew about `tests/skill_evals/fixtures/live`.
    """
    assert Path("anywhere/at/all/cases/golden-01/trial-03.jsonl").match(
        G.RECORDED_FIXTURE_GLOB)
    assert not Path("tests/skill_evals/test_runner.py").match(G.RECORDED_FIXTURE_GLOB)


def test_the_synthetic_selftest_set_is_the_only_allowed_tracked_fixtures():
    """CI's graded replay depends on the harness-selftest set being in git, and it is
    hand-authored rather than model output. Everything else recorded goes to the asset.
    """
    assert G.TRACKED_FIXTURES_ALLOWED == (
        "tests/skill_evals/fixtures/harness-selftest/",
    )
