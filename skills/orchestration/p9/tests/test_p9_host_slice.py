"""BRO-2815 — waits on hosts where a finished background task never wakes the
session (Paseo). There the only wait that completes is a foreground one, and a
foreground Bash call is capped at 10 minutes, so `watch` and `wait-for` slice
their wait under the cap and hand back EXIT_PENDING instead of being killed.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_FIXTURES = _HERE / "fixtures"
REPO = "broomva/test"


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    monkeypatch.setenv("BROOMVA_P9_REPO", REPO)
    if "p9" in sys.modules:
        del sys.modules["p9"]
    mod = importlib.import_module("p9")
    monkeypatch.setattr(mod, "notify", _record_notify)
    _NOTIFIED.clear()
    return mod


_NOTIFIED: list[str] = []


def _record_notify(kind, *_a, **_kw):
    _NOTIFIED.append(kind)


class _SlowProc:
    """A `gh pr checks --watch` that is still running when the slice ends."""
    pid = 4242

    def __init__(self):
        self.terminated = False
        self.timeouts: list[float | None] = []

    def wait(self, timeout=None):
        self.timeouts.append(timeout)
        if timeout is None:
            raise AssertionError("an unsliced wait would block past the Bash cap")
        raise subprocess.TimeoutExpired("gh", timeout)

    def terminate(self):
        self.terminated = True


class _DoneProc:
    pid = 4243

    def __init__(self, rc=0):
        self.rc = rc
        self.timeouts: list[float | None] = []

    def wait(self, timeout=None):
        self.timeouts.append(timeout)
        return self.rc


class TestHostProfile:
    def test_paseo_does_not_wake(self, p9, monkeypatch):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        prof = p9.host_profile()
        assert prof["host"] == "paseo"
        assert prof["background_wakes"] is False
        assert prof["wait_mode"] == "foreground"
        assert prof["default_slice_seconds"] < prof["bash_call_cap_seconds"]

    def test_plain_claude_code_wakes(self, p9, monkeypatch):
        monkeypatch.setenv("CLAUDECODE", "1")
        prof = p9.host_profile()
        assert (prof["host"], prof["background_wakes"]) == ("claude-code", True)
        assert prof["default_slice_seconds"] is None

    @pytest.mark.parametrize("value,wakes", [("1", True), ("0", False)])
    def test_override_wins_both_ways(self, p9, monkeypatch, value, wakes):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        monkeypatch.setenv("P9_BACKGROUND_WAKES", value)
        assert p9.host_profile()["background_wakes"] is wakes
        monkeypatch.delenv("PASEO_AGENT_ID")
        assert p9.host_profile()["background_wakes"] is wakes

    def test_host_json(self, p9, monkeypatch, capsys):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        assert p9.main(["host", "--json"]) == p9.EXIT_OK
        assert json.loads(capsys.readouterr().out)["wait_mode"] == "foreground"

    def test_host_text_names_the_foreground_rule(self, p9, monkeypatch, capsys):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        p9.main(["host"])
        out = capsys.readouterr().out
        assert "FOREGROUND" in out and "blocking subagents" in out


class TestWatchSlice:
    def test_slice_expiry_hands_back_pending(self, p9, monkeypatch):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        proc = _SlowProc()
        monkeypatch.setattr(p9, "spawn_watcher", lambda *a, **kw: proc)
        rc = p9.main(["watch", "700", "--repo", REPO])
        assert rc == p9.EXIT_PENDING
        assert proc.timeouts[0] == p9.DEFAULT_SLICE_SECONDS
        assert proc.terminated
        # Not ABANDONED: the next action is simply to watch again.
        assert p9.current_pr_state(700) == p9.PRState.PUSHED
        assert _NOTIFIED == []

    def test_rewatch_after_expiry_folds_green(self, p9, monkeypatch):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        monkeypatch.setattr(p9, "spawn_watcher", lambda *a, **kw: _SlowProc())
        assert p9.main(["watch", "701", "--repo", REPO]) == p9.EXIT_PENDING
        done = _DoneProc(0)
        monkeypatch.setattr(p9, "spawn_watcher", lambda *a, **kw: done)
        assert p9.main(["watch", "701", "--repo", REPO]) == p9.EXIT_OK
        assert p9.current_pr_state(701) == p9.PRState.GREEN

    def test_no_slice_where_background_wakes(self, p9, monkeypatch):
        done = _DoneProc(0)
        monkeypatch.setattr(p9, "spawn_watcher", lambda *a, **kw: done)
        assert p9.main(["watch", "702", "--repo", REPO]) == p9.EXIT_OK
        assert done.timeouts == [None]

    def test_explicit_slice_and_zero(self, p9, monkeypatch):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        done = _DoneProc(0)
        monkeypatch.setattr(p9, "spawn_watcher", lambda *a, **kw: done)
        p9.main(["watch", "703", "--repo", REPO, "--slice", "30"])
        p9.main(["watch", "704", "--repo", REPO, "--slice", "0"])
        assert done.timeouts == [30.0, None]

    def test_slice_expiry_json(self, p9, monkeypatch, capsys):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        monkeypatch.setattr(p9, "spawn_watcher", lambda *a, **kw: _SlowProc())
        p9.main(["watch", "705", "--repo", REPO, "--json"])
        last = capsys.readouterr().out.strip().splitlines()[-1]
        assert json.loads(last)["result"] == "PENDING"

    def test_detach_on_non_waking_host_warns(self, p9, monkeypatch, capsys):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        monkeypatch.setattr(p9, "spawn_watcher", lambda *a, **kw: _DoneProc())
        p9.main(["watch", "706", "--repo", REPO, "--detach"])
        assert "does not wake" in capsys.readouterr().err

    def test_red_still_folds_inside_the_slice(self, p9, monkeypatch):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        monkeypatch.setattr(p9, "spawn_watcher", lambda *a, **kw: _DoneProc(1))
        assert p9.main(["watch", "707", "--repo", REPO]) == p9.EXIT_OK
        assert p9.current_pr_state(707) == p9.PRState.RED_UNCLASSIFIED


class TestWaitForSlice:
    def test_slice_returns_pending_before_timeout(self, p9, monkeypatch, capsys):
        monkeypatch.setattr(p9.time, "sleep", lambda s: None)
        rc = p9.main(["wait-for", "deploy", "--cmd", "false",
                      "--interval", "0.1", "--timeout", "60",
                      "--slice", "0.3"])
        assert rc == p9.EXIT_PENDING
        err = capsys.readouterr().err
        assert "slice-expired" in err and "again" in err
        assert _NOTIFIED == []

    def test_slice_holds_once_remaining_drops_below_it(self, p9):
        # Real clock: by the third poll the time left to the deadline (0.5s)
        # is below the slice (0.6s). The slice must still end the call — a
        # 900s wait sliced at 540s must not run on to 900 past the Bash cap.
        rc = p9.main(["wait-for", "mid", "--cmd", "false",
                      "--interval", "0.25", "--timeout", "1.0",
                      "--slice", "0.6"])
        assert rc == p9.EXIT_PENDING

    def test_success_inside_slice(self, p9, monkeypatch):
        rc = p9.main(["wait-for", "ok", "--cmd", "true", "--slice", "5"])
        assert rc == p9.EXIT_OK

    def test_timeout_shorter_than_slice_is_a_real_timeout(self, p9, monkeypatch):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        rc = p9.main(["wait-for", "short", "--cmd", "false",
                      "--interval", "0.1", "--timeout", "0.3"])
        assert rc == p9.EXIT_DEGRADED

    def test_rearm_argv_never_inherits_a_slice(self, p9, monkeypatch):
        monkeypatch.setenv("PASEO_AGENT_ID", "abc")
        p9.main(["wait-for", "rec", "--cmd", "true"])
        rows, _ = p9.jsonl_read_all(p9.waits_jsonl())
        argv = rows[0]["extra"]["argv"]
        assert argv[argv.index("--slice") + 1] == "0"


def test_conftest_scrubs_host_markers(p9):
    # Run from inside Paseo, this suite must still see a waking host by
    # default — otherwise every legacy watch test silently gets a slice.
    assert p9.host_profile()["background_wakes"] is True


def test_pending_exit_code_is_the_documented_8(p9):
    # SKILL.md tells the agent "exit 8 means run it again". Pin the number:
    # folded to 0 a slice expiry reads as success and the agent moves on
    # with CI still running.
    assert p9.EXIT_PENDING == 8
    assert p9.EXIT_PENDING not in (p9.EXIT_OK, p9.EXIT_DEGRADED,
                                   p9.EXIT_AUTO_MERGE_BLOCKED)
