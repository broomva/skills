"""Unit tests for persist.py."""
from __future__ import annotations
import importlib
import json
import shlex
import sys
from pathlib import Path
import pytest

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def persist(tmp_path, monkeypatch):
    monkeypatch.setenv("BROOMVA_PERSIST_HOME", str(tmp_path))
    if "persist" in sys.modules:
        del sys.modules["persist"]
    return importlib.import_module("persist")


class TestStateMachine:
    def test_legal_spawn_to_iterate(self, persist):
        persist.assert_legal_transition(persist.LoopState.SPAWNED, persist.LoopState.ITERATING)

    def test_iteration_self_transition(self, persist):
        persist.assert_legal_transition(persist.LoopState.ITERATING, persist.LoopState.ITERATING)

    def test_iterate_to_success(self, persist):
        persist.assert_legal_transition(persist.LoopState.ITERATING, persist.LoopState.SUCCESS)

    def test_iterate_to_budget_exhausted(self, persist):
        persist.assert_legal_transition(persist.LoopState.ITERATING, persist.LoopState.BUDGET_EXHAUSTED)

    def test_spawned_to_budget_exhausted(self, persist):
        persist.assert_legal_transition(persist.LoopState.SPAWNED, persist.LoopState.BUDGET_EXHAUSTED)

    def test_paused_to_budget_exhausted(self, persist):
        persist.assert_legal_transition(persist.LoopState.PAUSED, persist.LoopState.BUDGET_EXHAUSTED)

    def test_terminal_to_anything_illegal(self, persist):
        with pytest.raises(persist.IllegalTransitionError):
            persist.assert_legal_transition(persist.LoopState.SUCCESS, persist.LoopState.ITERATING)

    def test_terminal_states(self, persist):
        assert persist.is_terminal(persist.LoopState.SUCCESS)
        assert persist.is_terminal(persist.LoopState.BUDGET_EXHAUSTED)
        assert persist.is_terminal(persist.LoopState.ABANDONED)
        assert not persist.is_terminal(persist.LoopState.ITERATING)


class TestSuccessConditions:
    def test_exit_code_0(self, persist, tmp_path):
        prompt = tmp_path / "p.md"
        prompt.write_text("x")
        assert persist._check_success_condition("exit-code-0", prompt, 0) is True
        assert persist._check_success_condition("exit-code-0", prompt, 1) is False

    def test_file_exists(self, persist, tmp_path):
        sentinel = tmp_path / "DONE"
        prompt = tmp_path / "p.md"
        prompt.write_text("x")
        assert persist._check_success_condition(f"file-exists:{sentinel}", prompt, 0) is False
        sentinel.write_text("done")
        assert persist._check_success_condition(f"file-exists:{sentinel}", prompt, 0) is True

    def test_grep_match(self, persist, tmp_path):
        status = tmp_path / "STATUS"
        status.write_text("RUNNING")
        prompt = tmp_path / "p.md"
        prompt.write_text("x")
        cond = f"grep:DONE:{status}"
        assert persist._check_success_condition(cond, prompt, 0) is False
        status.write_text("DONE\n")
        assert persist._check_success_condition(cond, prompt, 0) is True

    def test_grep_missing_file(self, persist, tmp_path):
        cond = f"grep:DONE:{tmp_path}/nope"
        prompt = tmp_path / "p.md"
        prompt.write_text("x")
        assert persist._check_success_condition(cond, prompt, 0) is False


class TestStateAppend:
    def test_append_and_read_one(self, persist):
        ev = persist.LoopEvent(
            ts="2026-05-06T00:00:00+00:00",
            loop_id="abc123",
            prompt_file="/tmp/p.md",
            iteration=0,
            from_state=persist.LoopState.SPAWNED.value,
            to_state=persist.LoopState.SPAWNED.value,
        )
        persist.append_event(ev)
        assert persist.current_loop_state("abc123") == persist.LoopState.SPAWNED

    def test_open_loops_excludes_terminal(self, persist):
        for prev, curr in [
            (persist.LoopState.SPAWNED, persist.LoopState.ITERATING),
            (persist.LoopState.ITERATING, persist.LoopState.SUCCESS),
        ]:
            persist.append_event(persist.LoopEvent(
                ts="2026-05-06T00:00:00+00:00", loop_id="L1",
                prompt_file="/tmp/p.md", iteration=1,
                from_state=prev.value, to_state=curr.value,
            ))
        persist.append_event(persist.LoopEvent(
            ts="2026-05-06T00:00:00+00:00", loop_id="L2",
            prompt_file="/tmp/p.md", iteration=0,
            from_state=persist.LoopState.SPAWNED.value,
            to_state=persist.LoopState.SPAWNED.value,
        ))
        opens = persist.open_loops()
        ids = [r["loop_id"] for r in opens]
        assert "L1" not in ids
        assert "L2" in ids


class TestCLI:
    def test_iterate_dry_run(self, persist, tmp_path):
        prompt = tmp_path / "p.md"
        prompt.write_text("test goal")
        rc = persist.main([
            "iterate", str(prompt),
            "--max-iterations", "3",
            "--dry-run", "--verbose",
        ])
        assert rc == 0
        rows, _ = persist.jsonl_read_all(persist.state_jsonl())
        assert len(rows) == 1
        assert rows[0]["from_state"] == "SPAWNED"

    def test_iterate_missing_prompt(self, persist, tmp_path):
        rc = persist.main(["iterate", str(tmp_path / "nope.md")])
        assert rc == persist.EXIT_USAGE

    def test_status_empty(self, persist, capsys):
        rc = persist.main(["status"])
        assert rc == 0
        assert "no loops" in capsys.readouterr().out

    def test_abandon_unknown(self, persist):
        rc = persist.main(["abandon", "doesnotexist"])
        assert rc == persist.EXIT_DEGRADED

    def test_doctor_runs(self, persist):
        rc = persist.main(["doctor"])
        assert rc in (persist.EXIT_OK, persist.EXIT_DEGRADED)


class TestRateLimitBackoff:
    """BRO-3350: a provider limit must not burn iterations."""

    LIMIT_MSG = "You've hit your weekly limit · resets Oct 26 at 7am (America/Bogota)"

    def test_detects_claude_and_codex_limit_messages(self, persist):
        for message in (
            self.LIMIT_MSG,
            "API Error: This request would exceed your account's rate limit.",
            "Claude Code usage limit reached. This turn is paused",
            "You have reached your usage limit. Please try again later.",
            "Error: rate limit exceeded (HTTP 429 Too Many Requests)",
            '{"error":{"code":"usage_limit_reached"}}',
        ):
            assert persist.is_rate_limited(message, 1)

    def test_ignores_ordinary_output(self, persist):
        assert not persist.is_rate_limited("implemented the token bucket rate limiter; tests pass", 1)
        assert not persist.is_rate_limited("", 1)

    def test_successful_agent_prose_does_not_trigger_pause(self, persist):
        prose = "Documented how to handle rate_limit_error and out of credits errors."
        assert not persist.is_rate_limited(prose, 0)

    def test_only_the_tail_counts(self, persist):
        body = self.LIMIT_MSG + "\n" + "\n".join(f"work line {i}" for i in range(50))
        assert not persist.is_rate_limited(body, 1)

    def test_backoff_doubles_and_caps(self, persist):
        assert [persist.limit_backoff(n, 60, 3600) for n in (1, 2, 3, 7, 20)] == [60, 120, 240, 3600, 3600]

    def _run(self, persist, tmp_path, script_lines, max_iter):
        prompt = tmp_path / "PROMPT.md"
        prompt.write_text("x")
        counter = tmp_path / "n"
        counter.write_text("0")
        agent = tmp_path / "agent.sh"
        # call k prints script_lines[k] (last entry repeats); "DONE" creates the success file
        cases = "\n".join(f'  {i}) echo "{line}"; exit 1;;' for i, line in enumerate(script_lines[:-1]))
        agent.write_text(
            "#!/bin/sh\n"
            f'n=$(cat "{counter}"); echo $((n+1)) > "{counter}"\n'
            f'case "$n" in\n{cases}\n  *) echo "{script_lines[-1]}"; touch "{tmp_path}/DONE";;\nesac\n'
        )
        agent.chmod(0o755)
        sleeps = []
        persist._sleep = sleeps.append
        rc = persist.main(["iterate", str(prompt), "--max-iterations", str(max_iter),
                           "--agent-cmd", f"sh {agent} #",
                           "--success-condition", f"file-exists:{tmp_path}/DONE",
                           "--limit-backoff-base", "1", "--limit-backoff-max", "4"])
        return rc, int(counter.read_text()), sleeps

    def test_limited_runs_do_not_consume_iterations(self, persist, tmp_path):
        # three limited runs, then a working run: a budget of ONE iteration must suffice
        rc, calls, sleeps = self._run(persist, tmp_path, [self.LIMIT_MSG] * 3 + ["did the work"], max_iter=1)
        assert rc == persist.EXIT_OK
        assert calls == 4
        assert sleeps == [1, 2, 4]

    def test_ordinary_failures_still_consume_iterations(self, persist, tmp_path):
        rc, calls, sleeps = self._run(persist, tmp_path, ["build failed"] * 3 + ["did the work"], max_iter=2)
        assert rc == persist.EXIT_BUDGET_EXHAUSTED
        assert calls == 2
        assert sleeps == []

    def test_backoff_is_capped_by_remaining_wall_clock(self, persist, tmp_path, monkeypatch):
        prompt = tmp_path / "PROMPT.md"
        prompt.write_text("x")
        clock = [0.0]
        sleeps = []
        monkeypatch.setattr(persist.time, "monotonic", lambda: clock[0])
        monkeypatch.setattr(persist, "_run_agent", lambda *_: (1, self.LIMIT_MSG))
        monkeypatch.setattr(persist, "_sleep", lambda seconds: (sleeps.append(seconds), clock.__setitem__(0, clock[0] + seconds)))

        rc = persist.main([
            "iterate", str(prompt), "--max-iterations", "1", "--max-wall-clock", "1",
            "--limit-backoff-base", "60", "--limit-backoff-max", "60",
        ])

        assert rc == persist.EXIT_BUDGET_EXHAUSTED
        assert sleeps == [1]

    def test_zero_wall_clock_exhausts_without_spawning(self, persist, tmp_path, monkeypatch):
        prompt = tmp_path / "PROMPT.md"
        prompt.write_text("x")
        monkeypatch.setattr(persist, "_run_agent", lambda *_: pytest.fail("agent must not start"))

        rc = persist.main(["iterate", str(prompt), "--max-wall-clock", "0"])

        assert rc == persist.EXIT_BUDGET_EXHAUSTED

    def test_rate_limit_beats_a_stale_success_sentinel(self, persist, tmp_path, monkeypatch):
        prompt = tmp_path / "PROMPT.md"
        sentinel = tmp_path / "DONE"
        prompt.write_text("x")
        sentinel.write_text("from an earlier run")
        clock = [0.0]
        monkeypatch.setattr(persist.time, "monotonic", lambda: clock[0])
        monkeypatch.setattr(persist, "_run_agent", lambda *_: (1, self.LIMIT_MSG))
        monkeypatch.setattr(persist, "_sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

        rc = persist.main([
            "iterate", str(prompt), "--max-iterations", "1", "--max-wall-clock", "1",
            "--success-condition", f"file-exists:{sentinel}",
            "--limit-backoff-base", "60", "--limit-backoff-max", "60",
        ])

        assert rc == persist.EXIT_BUDGET_EXHAUSTED


class TestAgentStreaming:
    def test_large_mixed_output_keeps_exit_code_and_tail(self, persist, tmp_path, capsys):
        prompt = tmp_path / "PROMPT.md"
        prompt.write_text("x")
        code = (
            "import sys; "
            "sys.stdout.write('x' * 200000); sys.stdout.flush(); "
            "sys.stderr.write('\\nrate diagnostic on stderr\\n'); sys.stderr.flush(); "
            "raise SystemExit(7)"
        )
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"

        rc, tail = persist._run_agent(command, prompt, verbose=False)

        assert rc == 7
        assert "rate diagnostic on stderr" in tail
        assert "rate diagnostic on stderr" in capsys.readouterr().out
