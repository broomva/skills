"""The data provider layer's deterministic core.

Every test below is a rule from the spec, and every rule came from a specific
observed failure rather than from taste. Where a test looks pedantic, the
docstring says which failure it is pinning -- so that a future reader deciding
whether to relax it can see what relaxing it costs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import provider as p  # noqa: E402


def ev(url: str = "https://example.test/a", digest: str = "d" * 64) -> p.Evidence:
    return p.Evidence(url=url, sha256=digest, retrieved_at="2026-08-24T00:00:00+00:00", snapshot=f"evidence/{digest}.snapshot")


# ---------------------------------------------------------------------------
# R1 -- classification at birth
# ---------------------------------------------------------------------------


class TestClassificationAtBirth:
    def test_a_field_read_from_an_artifact_is_observed(self):
        f = p.make_field("company", "Acme", evidence=ev())
        assert f.origin == "observed"

    def test_a_field_with_an_inference_note_is_simulated(self):
        f = p.make_field("size", 200, inferred_from="headcount band on the listing page")
        assert f.origin == "simulated"

    def test_an_unclassified_field_cannot_be_constructed(self):
        """The default that is refused.

        Letting this through as `simulated` would read as caution and is in fact
        a fabrication: it asserts we know the value was produced, when we know
        nothing about it. And it is unrecoverable -- Parallax types at birth and
        has no operator that adds provenance later.
        """
        with pytest.raises(p.ProviderError) as e:
            p.make_field("company", "Acme")
        assert e.value.code == "UNCLASSIFIED_FIELD"

    def test_a_field_cannot_be_both(self):
        with pytest.raises(p.ProviderError) as e:
            p.make_field("company", "Acme", evidence=ev(), inferred_from="also guessed")
        assert e.value.code == "AMBIGUOUS_ORIGIN"

    def test_a_field_needs_a_name(self):
        with pytest.raises(p.ProviderError) as e:
            p.make_field("  ", "Acme", evidence=ev())
        assert e.value.code == "FIELD_NAME_REQUIRED"


# ---------------------------------------------------------------------------
# judging -- the meet, applied per column
# ---------------------------------------------------------------------------


class TestJudging:
    def test_a_column_read_everywhere_is_observed(self):
        rows = [
            p.Record([p.make_field("company", "A", evidence=ev())]),
            p.Record([p.make_field("company", "B", evidence=ev())]),
        ]
        assert p.judge_columns(rows)["company"] == "observed"

    def test_one_guess_makes_the_whole_column_simulated(self):
        """Contamination flows one way.

        Nine cited values and one guess is a simulated column. Reporting it as
        observed because most of it was read is precisely the overclaim the type
        exists to prevent, and it is the version a dashboard would prefer.
        """
        rows = [
            p.Record([p.make_field("company", "A", evidence=ev())]),
            p.Record([p.make_field("company", "B", inferred_from="matched by name")]),
        ]
        assert p.judge_columns(rows)["company"] == "simulated"

    def test_a_missing_value_is_not_evidence(self):
        """A gap does not count as observed.

        Judging only the fields that happen to be present would let a column with
        one cited row and nine absences report as fully observed.
        """
        rows = [
            p.Record([p.make_field("company", "A", evidence=ev())]),
            p.Record([p.make_field("other", "B", evidence=ev())]),
        ]
        assert p.judge_columns(rows)["company"] == "simulated"

    def test_judging_is_per_column_not_per_record(self):
        rows = [
            p.Record(
                [
                    p.make_field("company", "A", evidence=ev()),
                    p.make_field("score", 1, inferred_from="model"),
                ]
            ),
            p.Record(
                [
                    p.make_field("company", "B", evidence=ev()),
                    p.make_field("score", 2, inferred_from="model"),
                ]
            ),
        ]
        judged = p.judge_columns(rows)
        assert judged == {"company": "observed", "score": "simulated"}


class TestTypeInference:
    @pytest.mark.parametrize(
        "values,expected",
        [
            ([1, 2, 3], "number"),
            ([1.5, 2.0], "number"),
            ([True, False], "boolean"),
            (["a", "b"], "string"),
            (["2026-08-24", "2026-01-01"], "date"),
            (["2026-08-24T10:00:00", "2026-01-01 09:00"], "date"),
        ],
    )
    def test_agreeing_values_infer_a_type(self, values, expected):
        assert p.infer_type(values) == expected

    def test_mixed_values_infer_NOTHING(self):
        """None is a real answer, and becomes a blocking question downstream.

        Quietly calling a mixed column `string` is how a number stops being
        addable three layers later, in a place with no connection to this one.
        """
        assert p.infer_type([1, "two"]) is None

    def test_booleans_are_not_numbers(self):
        """Python says isinstance(True, int). The type system here should not."""
        assert p.infer_type([True, 1]) is None

    def test_all_empty_infers_nothing(self):
        assert p.infer_type([None, None]) is None


# ---------------------------------------------------------------------------
# emit -- the handoff is type-preserving
# ---------------------------------------------------------------------------


class TestEmit:
    def test_the_row_count_is_counted_not_declared(self):
        rows = [p.Record([p.make_field("company", f"C{i}", evidence=ev())]) for i in range(3)]
        assert p.emit_table_arg("leads", rows).startswith("leads#3:")

    def test_origins_survive_into_the_invocation(self):
        rows = [
            p.Record(
                [
                    p.make_field("company", "A", evidence=ev()),
                    p.make_field("score", 1, inferred_from="model"),
                ]
            )
        ]
        arg = p.emit_table_arg("leads", rows)
        assert "company:string:observed" in arg
        assert "score:number:simulated" in arg

    def test_an_untyped_column_is_emitted_without_a_type(self):
        """So that Parallax raises the blocking question.

        Emitting `string` to keep the argument tidy would answer a question
        nobody asked us, in the one place a human was supposed to be consulted.
        """
        rows = [
            p.Record([p.make_field("mixed", 1, evidence=ev())]),
            p.Record([p.make_field("mixed", "two", evidence=ev())]),
        ]
        arg = p.emit_table_arg("leads", rows)
        assert "mixed," in arg or arg.endswith("mixed")
        assert "mixed:" not in arg

    def test_emitting_nothing_is_refused_with_a_reason(self):
        with pytest.raises(p.ProviderError) as e:
            p.emit_table_arg("leads", [])
        assert e.value.code == "NO_RECORDS"

    def test_the_command_is_argv_not_a_shell_string(self):
        rows = [p.Record([p.make_field("company", "A", evidence=ev())])]
        cmd = p.emit_command("leads", rows)
        assert cmd[:5] == ["parallax", "propose", "--kind", "business-data", "--table"]
        assert len(cmd) == 6


# ---------------------------------------------------------------------------
# R3 -- progress is work done
# ---------------------------------------------------------------------------


class TestProgress:
    def test_progress_is_done_over_total(self):
        run = p.Run(run_id="r1", question="q", total_units=4)
        p.advance(run, 1)
        assert run.progress == 0.25

    def test_progress_cannot_go_backwards(self):
        """The counter that went 6 -> 2.

        A completion count that decreases is a restart being reported as
        progress, and the caller has no way to tell the two apart.
        """
        run = p.Run(run_id="r1", question="q", total_units=10)
        p.advance(run, 6)
        with pytest.raises(p.ProviderError) as e:
            p.advance(run, 2)
        assert e.value.code == "PROGRESS_WENT_BACKWARDS"
        assert run.done_units == 6

    def test_progress_cannot_exceed_the_plan(self):
        run = p.Run(run_id="r1", question="q", total_units=3)
        with pytest.raises(p.ProviderError) as e:
            p.advance(run, 4)
        assert e.value.code == "PROGRESS_EXCEEDS_TOTAL"

    def test_progress_with_no_planned_work_is_zero_not_a_crash(self):
        run = p.Run(run_id="r1", question="q", total_units=0)
        assert run.progress == 0.0

    def test_nothing_but_advance_moves_the_number(self):
        """The defect stated positively.

        The service this came from computed its percentage from the stage it had
        reached. There is deliberately no setter here: `progress` is derived, so
        it cannot report motion that did not happen.
        """
        run = p.Run(run_id="r1", question="q", total_units=10)
        assert run.progress == 0.0
        run.status = "orchestrating"  # a stage change, on its own
        assert run.progress == 0.0


# ---------------------------------------------------------------------------
# R4 -- a terminal empty state
# ---------------------------------------------------------------------------


class TestTerminalStates:
    def test_finding_nothing_completes(self):
        """The state the studied service never reached.

        No run was observed leaving `orchestrating`, so "we looked and there is
        nothing" and "still going" were indistinguishable for as long as anyone
        was willing to wait.
        """
        run = p.Run(run_id="r1", question="q", total_units=5)
        p.finish(run, candidates=0)
        assert run.status == "complete"
        assert run.is_terminal
        assert run.candidates == 0
        assert run.note == "found nothing"

    def test_completing_fills_the_progress_bar(self):
        run = p.Run(run_id="r1", question="q", total_units=5)
        p.advance(run, 2)
        p.finish(run, candidates=3)
        assert run.progress == 1.0

    def test_a_cancelled_run_is_terminal(self):
        run = p.Run(run_id="r1", question="q", total_units=5)
        p.cancel(run, reason="operator stopped it")
        assert run.is_terminal
        assert run.note == "operator stopped it"

    def test_a_terminal_run_cannot_be_advanced_or_refinished(self):
        run = p.Run(run_id="r1", question="q", total_units=5)
        p.finish(run, candidates=1)
        for call in (lambda: p.advance(run, 5), lambda: p.finish(run, candidates=2), lambda: p.cancel(run, reason="x")):
            with pytest.raises(p.ProviderError) as e:
                call()
            assert e.value.code == "RUN_TERMINAL"


# ---------------------------------------------------------------------------
# R2 + R7 -- evidence that can be checked, status that cannot reassure falsely
# ---------------------------------------------------------------------------


class TestEvidenceAndStatus:
    def test_a_snapshot_round_trips_and_verifies(self, tmp_path: Path):
        e = p.save_snapshot(tmp_path, "r1", "https://example.test/a", b"<html>hello</html>")
        assert p.verify_snapshot(tmp_path, "r1", e) is True

    def test_a_tampered_snapshot_fails_verification(self, tmp_path: Path):
        """Which is the entire reason the hash is stored beside the URL.

        A citation that only names a page decays silently: the page changes, the
        link still resolves, and nothing reports that the sentence it supported
        is gone.
        """
        e = p.save_snapshot(tmp_path, "r1", "https://example.test/a", b"original")
        (tmp_path / p.STATE_DIR / "r1" / e.snapshot).write_bytes(b"something else")
        assert p.verify_snapshot(tmp_path, "r1", e) is False

    def test_a_missing_snapshot_fails_verification(self, tmp_path: Path):
        e = ev()
        assert p.verify_snapshot(tmp_path, "r1", e) is False

    def test_a_missing_run_is_an_error_not_a_run_at_zero_percent(self, tmp_path: Path):
        """The rule that cost an earlier verification its credibility.

        A status surface answering identically whether its subject exists has
        told you nothing, and reads as though it has.
        """
        with pytest.raises(p.ProviderError) as e:
            p.load_run(tmp_path, "nope")
        assert e.value.code == "RUN_NOT_FOUND"

    def test_a_saved_run_round_trips(self, tmp_path: Path):
        run = p.Run(run_id="r1", question="who sells arepas", total_units=3, started_at="2026-08-24T00:00:00+00:00")
        p.advance(run, 2, candidates=7)
        p.save_run(tmp_path, run)
        back = p.load_run(tmp_path, "r1")
        assert (back.done_units, back.total_units, back.candidates) == (2, 3, 7)
        assert back.progress == run.progress


# ---------------------------------------------------------------------------
# the CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_emit_prints_a_runnable_invocation(self, tmp_path: Path, capsys):
        records = [
            {
                "company": {"value": "Acme", "evidence": {"url": "https://x.test", "sha256": "a" * 64, "snapshot": "evidence/a.snapshot"}},
                "score": {"value": 3, "inferred_from": "model"},
            }
        ]
        f = tmp_path / "records.json"
        f.write_text(json.dumps(records), encoding="utf-8")
        code = p.main(["emit", "--table", "leads", "--records", str(f)])
        assert code == 0
        out = capsys.readouterr().out.strip()
        assert out.startswith("parallax propose --kind business-data --table leads#1:")
        assert "company:string:observed" in out
        assert "score:number:simulated" in out

    def test_an_unclassified_record_is_a_typed_refusal_with_exit_2(self, tmp_path: Path, capsys):
        f = tmp_path / "records.json"
        f.write_text(json.dumps([{"company": {"value": "Acme"}}]), encoding="utf-8")
        code = p.main(["emit", "--table", "leads", "--records", str(f)])
        assert code == 2
        assert "UNCLASSIFIED_FIELD" in capsys.readouterr().err

    def test_status_on_a_missing_run_exits_2(self, tmp_path: Path, capsys):
        code = p.main(["status", "--run", "nope", "--root", str(tmp_path)])
        assert code == 2
        assert "RUN_NOT_FOUND" in capsys.readouterr().err
