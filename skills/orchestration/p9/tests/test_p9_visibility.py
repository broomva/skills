"""Tests for BRO-1701 — background-work visibility.

Covers the four deliverables:
  1. Termination invariant — every `p9 watch` / `p9 wait-for` exit path
     (success, failure, timeout, kill) folds a state event, emits a
     P9-TERMINATION-REPORT on stderr, and appends a notify.jsonl audit row.
  2. Notify dispatcher — channel fan-out (command/ntfy/webhook), env
     quick-config, malformed-config isolation, always-on audit floor.
  3. Non-PR waits + re-arm — `p9 wait-for` lifecycle in waits.jsonl,
     `p9 rearm` re-spawning dead waits from their recorded argv.
  4. Stuck-detector — `p9 stuck-scan` structured dump + per-episode dedup.

Signal-path tests spawn the real CLI as a subprocess (with a PATH-shimmed
fake `gh`) because signal handlers only make sense in a real process.
"""

from __future__ import annotations

import importlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
_FIXTURES = _HERE / "fixtures"
sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    """Fresh p9 import with tmpdir state and good policy fixture."""
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    monkeypatch.delenv("BROOMVA_P9_NTFY_TOPIC", raising=False)
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


class _FakeProc:
    def __init__(self, returncode: int = 0):
        self._rc = returncode
        self.pid = 99999

    def wait(self):
        return self._rc

    def terminate(self):
        pass


def _notify_rows(p9):
    rows, _ = p9.jsonl_read_all(p9.notify_jsonl())
    return rows


def _wait_rows(p9):
    rows, _ = p9.jsonl_read_all(p9.waits_jsonl())
    return rows


def _cli_env(tmp_path: Path, extra_path: Path | None = None) -> dict:
    env = dict(os.environ)
    env["BROOMVA_P9_HOME"] = str(tmp_path)
    env["BROOMVA_P9_POLICY"] = str(_FIXTURES / "policy-good.yaml")
    env.pop("BROOMVA_P9_NTFY_TOPIC", None)
    if extra_path:
        env["PATH"] = f"{extra_path}{os.pathsep}{env['PATH']}"
    return env


def _wait_until(predicate, timeout_s: float = 8.0, step: float = 0.05):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 1. Termination invariant
# ─────────────────────────────────────────────────────────────────────────────
class TestTerminationInvariant:
    def test_every_pr_state_has_next_action(self, p9):
        for state in p9.PRState:
            assert state.value in p9._NEXT_ACTION

    def test_every_wait_state_has_next_action(self, p9):
        for state in p9.WaitState:
            assert state.value in p9._WAIT_NEXT_ACTION

    def test_green_fold_emits_report_and_notifies(self, p9, monkeypatch, capsys):
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=0))
        rc = p9.main(["watch", "100", "--repo", "broomva/test"])
        assert rc == 0
        err = capsys.readouterr().err
        assert p9.REPORT_MARKER in err
        marker_line = next(l for l in err.splitlines()
                           if l.startswith(p9.REPORT_MARKER))
        report = json.loads(marker_line[len(p9.REPORT_MARKER) + 1:])
        assert report["state"] == "GREEN"
        assert report["cause"] == "gh-exit"
        assert "merge-status" in report["next_action"]
        kinds = [r["kind"] for r in _notify_rows(p9)]
        assert "termination:green" in kinds

    def test_red_fold_emits_report(self, p9, monkeypatch, capsys):
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=1))
        rc = p9.main(["watch", "200", "--repo", "broomva/test"])
        assert rc == 0
        err = capsys.readouterr().err
        assert '"state":"RED_UNCLASSIFIED"' in err
        assert "termination:red_unclassified" in [r["kind"] for r in _notify_rows(p9)]

    def test_sigterm_kill_folds_abandoned_and_reports(self, p9, tmp_path):
        """The heart of BRO-1701: a killed watcher must not die silently."""
        shim = tmp_path / "bin"
        shim.mkdir()
        gh = shim / "gh"
        gh.write_text("#!/bin/sh\nsleep 30\n")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        proc = subprocess.Popen(
            [sys.executable, str(_SCRIPTS / "p9.py"),
             "watch", "42", "--repo", "broomva/test"],
            env=_cli_env(tmp_path, extra_path=shim),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert _wait_until(
            lambda: p9.current_pr_state(42, "broomva/test") == p9.PRState.WATCHING
        ), "watcher never registered WATCHING"
        os.kill(proc.pid, signal.SIGTERM)
        out, err = proc.communicate(timeout=15)
        assert proc.returncode == p9.EXIT_DEGRADED
        assert p9.REPORT_MARKER in err
        assert '"cause":"killed:SIGTERM"' in err
        assert p9.current_pr_state(42, "broomva/test") == p9.PRState.ABANDONED
        kinds = [r["kind"] for r in _notify_rows(p9)]
        assert "termination:abandoned" in kinds

    def test_reap_emits_termination_report(self, p9, capsys):
        p9.append_state_event(p9.PRStateEvent(
            ts="2020-01-01T00:00:00+00:00", pr=7, repo="broomva/test",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="w7", extra={"pid": 0},
        ))
        reaped = p9.reap_stale_watchers(grace_seconds=0.0)
        assert [r["pr"] for r in reaped] == [7]
        err = capsys.readouterr().err
        assert p9.REPORT_MARKER in err
        assert '"cause":"reaped:dead-watcher"' in err
        assert "termination:abandoned" in [r["kind"] for r in _notify_rows(p9)]

    def test_report_command_renders_next_action(self, p9, monkeypatch, capsys):
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=0))
        p9.main(["watch", "300", "--repo", "broomva/test"])
        capsys.readouterr()
        rc = p9.main(["report", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["reports"], "report must render tracked rows"
        rep = next(r for r in out["reports"] if r.get("pr") == 300)
        assert rep["state"] == "GREEN"
        assert rep["next_action"]
        assert rep["report"] == "p9-termination"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Notify dispatcher
# ─────────────────────────────────────────────────────────────────────────────
class TestNotify:
    def test_audit_floor_with_zero_channels(self, p9):
        row = p9.notify("test", "t", "b")
        assert row["deliveries"] == []
        rows = _notify_rows(p9)
        assert rows and rows[-1]["kind"] == "test"

    def test_command_channel_receives_json_on_stdin(self, p9, tmp_path):
        sink = tmp_path / "sink.json"
        p9.notify_config_path().write_text(json.dumps({
            "channels": [{"type": "command", "cmd": f"cat > {sink}"}],
        }))
        row = p9.notify("test", "hello", "world", {"pr": 1})
        assert row["deliveries"] == [{"channel": "command", "ok": True}]
        data = json.loads(sink.read_text())
        assert data["title"] == "hello"
        assert data["payload"]["pr"] == 1

    def test_channel_failure_is_isolated_and_recorded(self, p9, tmp_path):
        sink = tmp_path / "sink.json"
        p9.notify_config_path().write_text(json.dumps({
            "channels": [
                {"type": "command", "cmd": "exit 3"},
                {"type": "command", "cmd": f"cat > {sink}"},
            ],
        }))
        row = p9.notify("test", "t", "b")
        assert [d["ok"] for d in row["deliveries"]] == [False, True]
        assert sink.exists(), "later channels must still fire"

    def test_malformed_config_recorded_never_raises(self, p9):
        p9.notify_config_path().write_text("{not json")
        row = p9.notify("test", "t", "b")
        assert row["deliveries"][0]["channel"] == "config"
        assert row["deliveries"][0]["ok"] is False

    def test_ntfy_env_quick_config(self, p9, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            class _R:
                def read(self):
                    return b"ok"
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            return _R()

        monkeypatch.setattr(p9.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("BROOMVA_P9_NTFY_TOPIC", "my-topic")
        row = p9.notify("test", "Title!", "body")
        assert row["deliveries"] == [{"channel": "ntfy", "ok": True}]
        # JSON publish endpoint: topic + title ride in the UTF-8 body.
        body = json.loads(calls[0].data.decode("utf-8"))
        assert body["topic"] == "my-topic"
        assert body["title"] == "Title!"
        assert body["message"] == "body"

    def test_notify_cli_smoke(self, p9, capsys):
        rc = p9.main(["notify", "hello", "--body", "world", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["title"] == "hello"

    def test_notify_cli_degraded_on_channel_failure(self, p9, capsys):
        p9.notify_config_path().write_text(json.dumps({
            "channels": [{"type": "command", "cmd": "exit 1"}],
        }))
        rc = p9.main(["notify", "x"])
        assert rc == p9.EXIT_DEGRADED


# ─────────────────────────────────────────────────────────────────────────────
# 3. Non-PR waits (`p9 wait-for`) + re-arm
# ─────────────────────────────────────────────────────────────────────────────
class TestWaitFor:
    def test_success_folds_succeeded(self, p9, capsys):
        rc = p9.main(["wait-for", "quick", "--cmd", "true",
                      "--interval", "0.1", "--timeout", "5"])
        assert rc == 0
        rows = _wait_rows(p9)
        assert rows[-1]["to_state"] == "SUCCEEDED"
        err = capsys.readouterr().err
        assert p9.REPORT_MARKER in err
        assert "termination:succeeded" in [r["kind"] for r in _notify_rows(p9)]

    def test_timeout_folds_timed_out(self, p9, capsys):
        rc = p9.main(["wait-for", "never", "--cmd", "false",
                      "--interval", "0.1", "--timeout", "0.3"])
        assert rc == p9.EXIT_DEGRADED
        rows = _wait_rows(p9)
        assert rows[-1]["to_state"] == "TIMED_OUT"
        assert rows[-1]["extra"]["polls"] >= 1

    def test_unrunnable_command_fails_fast(self, p9):
        rc = p9.main(["wait-for", "typo", "--cmd",
                      "definitely-not-a-command-xyz",
                      "--interval", "0.1", "--timeout", "30"])
        assert rc == p9.EXIT_EXTERNAL_ERROR
        rows = _wait_rows(p9)
        assert rows[-1]["to_state"] == "FAILED"

    def test_heartbeat_touched_per_poll(self, p9, tmp_path):
        """Heartbeat exists while the wait is LIVE (stuck-scan's progress
        signal) and is cleaned up by the terminal fold."""
        proc = subprocess.Popen(
            [sys.executable, str(_SCRIPTS / "p9.py"),
             "wait-for", "hb", "--cmd", "false",
             "--interval", "0.2", "--timeout", "60"],
            env=_cli_env(tmp_path),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            assert _wait_until(
                lambda: any(r["name"] == "hb" for r in _wait_rows(p9))
            ), "wait never registered"
            wid = next(r["wait_id"] for r in _wait_rows(p9)
                       if r["name"] == "hb")
            assert _wait_until(
                lambda: p9.wait_heartbeat_path(wid).exists()
            ), "heartbeat never touched while live"
        finally:
            os.kill(proc.pid, signal.SIGTERM)
            proc.communicate(timeout=15)
        assert not p9.wait_heartbeat_path(wid).exists(), \
            "terminal fold must clean up the heartbeat"

    def test_status_lists_open_waits(self, p9, capsys):
        p9.append_wait_event(p9.WaitEvent(
            ts=p9._utcnow(), wait_id="w1", name="deploy",
            from_state="NEW", to_state="WAITING",
            extra={"pid": os.getpid()},
        ))
        rc = p9.main(["status", "--json", "--no-reap"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["open_waits"][0]["name"] == "deploy"
        assert "open_prs" in out

    def test_sigterm_kill_folds_killed(self, p9, tmp_path):
        proc = subprocess.Popen(
            [sys.executable, str(_SCRIPTS / "p9.py"),
             "wait-for", "killme", "--cmd", "false",
             "--interval", "0.2", "--timeout", "60"],
            env=_cli_env(tmp_path),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert _wait_until(
            lambda: any(r["to_state"] == "WAITING" for r in _wait_rows(p9))
        ), "wait never registered WAITING"
        os.kill(proc.pid, signal.SIGTERM)
        out, err = proc.communicate(timeout=15)
        assert proc.returncode == p9.EXIT_DEGRADED
        assert '"cause":"killed:SIGTERM"' in err
        assert _wait_rows(p9)[-1]["to_state"] == "KILLED"

    def test_detach_spawns_and_registers(self, p9, tmp_path, capsys):
        rc = p9.main(["wait-for", "bg", "--cmd", "true",
                      "--interval", "0.1", "--timeout", "10",
                      "--detach", "--json"])
        assert rc == 0
        info = json.loads(capsys.readouterr().out)
        assert _wait_until(
            lambda: any(r["to_state"] == "SUCCEEDED" for r in _wait_rows(p9))
        ), "detached wait never completed"
        assert Path(info["log"]).exists()

    def test_preset_unknown_is_usage_error(self, p9):
        rc = p9.main(["wait-for", "x", "--preset", "nope"])
        assert rc == p9.EXIT_USAGE

    def test_preset_vercel_requires_target(self, p9):
        rc = p9.main(["wait-for", "x", "--preset", "vercel"])
        assert rc == p9.EXIT_USAGE


class TestRearm:
    def _dead_pid(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        return proc.pid

    def test_dry_run_lists_dead_wait(self, p9, capsys):
        p9.append_wait_event(p9.WaitEvent(
            ts=p9._utcnow(), wait_id="wdead", name="dw",
            from_state="NEW", to_state="WAITING",
            extra={"pid": self._dead_pid(),
                   "argv": [sys.executable, str(_SCRIPTS / "p9.py"),
                            "wait-for", "dw", "--cmd", "true",
                            "--interval", "0.1", "--timeout", "5"]},
        ))
        rc = p9.main(["rearm", "--dry-run", "--now", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["rearmed"][0]["wait_id"] == "wdead"
        assert "would" in out["rearmed"][0]
        # dry-run must not fold the row
        assert _wait_rows(p9)[-1]["to_state"] == "WAITING"

    def test_rearm_respawns_dead_wait_from_argv(self, p9, capsys):
        p9.append_wait_event(p9.WaitEvent(
            ts=p9._utcnow(), wait_id="wdead2", name="dw2",
            from_state="NEW", to_state="WAITING",
            extra={"pid": self._dead_pid(),
                   "argv": [sys.executable, str(_SCRIPTS / "p9.py"),
                            "wait-for", "dw2", "--cmd", "true",
                            "--interval", "0.1", "--timeout", "10"]},
        ))
        rc = p9.main(["rearm", "--now", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["rearmed"][0].get("rearmed_pid")
        # Old row folded ABANDONED; the re-spawned wait completes SUCCEEDED
        # with lineage recorded.
        def _resolved():
            rows = _wait_rows(p9)
            by_id = {}
            for r in rows:
                by_id[r["wait_id"]] = r
            old = by_id.get("wdead2", {})
            succ = [r for r in by_id.values()
                    if r["to_state"] == "SUCCEEDED"
                    and r.get("extra", {}).get("rearmed_from") == "wdead2"]
            return old.get("to_state") == "ABANDONED" and bool(succ)
        assert _wait_until(_resolved), "rearm did not fold+respawn"

    def test_wait_without_argv_is_skipped(self, p9, capsys):
        p9.append_wait_event(p9.WaitEvent(
            ts=p9._utcnow(), wait_id="wnoargv", name="na",
            from_state="NEW", to_state="WAITING",
            extra={"pid": self._dead_pid()},
        ))
        rc = p9.main(["rearm", "--now", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["rearmed"][0].get("skipped")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Stuck-detector
# ─────────────────────────────────────────────────────────────────────────────
class TestStuckScan:
    def _live_watching_row(self, p9, pr=900):
        p9.append_state_event(p9.PRStateEvent(
            ts="2020-01-01T00:00:00+00:00", pr=pr, repo="broomva/test",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="wstuck", extra={"pid": os.getpid()},
        ))

    def test_stale_live_watcher_is_stuck(self, p9, capsys):
        self._live_watching_row(p9)
        rc = p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        assert rc == p9.EXIT_DEGRADED
        out = json.loads(capsys.readouterr().out)
        assert out["stuck"][0]["pr"] == 900
        assert out["stuck"][0]["notified"] is True
        assert out["stuck"][0]["next_action"]
        assert "stuck" in [r["kind"] for r in _notify_rows(p9)]

    def test_second_scan_dedups_same_episode(self, p9, capsys):
        self._live_watching_row(p9)
        p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        capsys.readouterr()
        n_before = len(_notify_rows(p9))
        rc = p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        assert rc == p9.EXIT_DEGRADED  # still stuck, still reported
        out = json.loads(capsys.readouterr().out)
        assert out["stuck"][0]["notified"] is False  # but not re-notified
        assert len(_notify_rows(p9)) == n_before

    def test_renotify_overrides_dedup(self, p9, capsys):
        self._live_watching_row(p9)
        p9.main(["stuck-scan", "--threshold-min", "1"])
        n_before = len(_notify_rows(p9))
        p9.main(["stuck-scan", "--threshold-min", "1", "--renotify"])
        assert len(_notify_rows(p9)) > n_before

    def test_dead_pid_is_not_stuck(self, p9, capsys):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        p9.append_state_event(p9.PRStateEvent(
            ts="2020-01-01T00:00:00+00:00", pr=901, repo="broomva/test",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="wdead", extra={"pid": proc.pid},
        ))
        rc = p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        assert rc == p9.EXIT_OK
        out = json.loads(capsys.readouterr().out)
        assert out["stuck"] == []

    def test_stale_live_wait_is_stuck(self, p9, capsys):
        p9.append_wait_event(p9.WaitEvent(
            ts="2020-01-01T00:00:00+00:00", wait_id="wstale", name="slow",
            from_state="NEW", to_state="WAITING",
            extra={"pid": os.getpid()},
        ))
        rc = p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        assert rc == p9.EXIT_DEGRADED
        out = json.loads(capsys.readouterr().out)
        assert out["stuck"][0]["name"] == "slow"

    def test_fresh_heartbeat_is_not_stuck(self, p9, capsys):
        p9.append_wait_event(p9.WaitEvent(
            ts="2020-01-01T00:00:00+00:00", wait_id="wfresh", name="fresh",
            from_state="NEW", to_state="WAITING",
            extra={"pid": os.getpid()},
        ))
        p9.touch_wait_heartbeat("wfresh")
        rc = p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        assert rc == p9.EXIT_OK


# ─────────────────────────────────────────────────────────────────────────────
# Watch logs (progress signal + post-mortem detail)
# ─────────────────────────────────────────────────────────────────────────────
class TestWatchLogs:
    def test_spawn_watcher_writes_log_file(self, p9, monkeypatch):
        captured = {}

        def fake_popen(cmd, **kw):
            captured["stdout"] = kw.get("stdout")
            return _FakeProc(0)

        monkeypatch.setattr(p9.subprocess, "Popen", fake_popen)
        p9.spawn_watcher(1, "broomva/test", watcher_id="abc123")
        assert captured["stdout"] is not p9.subprocess.DEVNULL
        assert p9.watch_log_path("abc123").exists()

    def test_report_includes_log_tail_for_single_pr(self, p9, capsys):
        p9.logs_dir().mkdir(parents=True, exist_ok=True)
        log = p9.watch_log_path("wtail")
        log.write_text("check A pass\ncheck B fail\n")
        p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=700, repo="broomva/test",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="wtail", extra={"pid": 0, "log": str(log)},
        ))
        rc = p9.main(["report", "--pr", "700", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        rep = out["reports"][0]
        assert rep["pr"] == 700
        assert rep["log_tail"] == ["check A pass", "check B fail"]


# ─────────────────────────────────────────────────────────────────────────────
# Re-watch vs concurrency ceiling (found live while dogfooding PR #82)
# ─────────────────────────────────────────────────────────────────────────────
class TestRewatchCeiling:
    def test_same_pr_rewatch_not_blocked_by_own_red_row(self, p9, monkeypatch):
        """A RED fold from a transient gh error must not block the re-watch
        of the SAME PR at max_concurrent_prs=1 — the ceiling bounds distinct
        PRs, and a re-watch replaces its own row."""
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=1))
        rc = p9.main(["watch", "600", "--repo", "broomva/test"])
        assert rc == 0
        assert p9.current_pr_state(600, "broomva/test") == p9.PRState.RED_UNCLASSIFIED
        # ceiling in policy-good.yaml is small; re-watch of the same PR
        # must pass regardless
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=0))
        rc = p9.main(["watch", "600", "--repo", "broomva/test"])
        assert rc == 0
        assert p9.current_pr_state(600, "broomva/test") == p9.PRState.GREEN

    def test_distinct_pr_still_blocked_at_ceiling(self, p9, monkeypatch):
        policy = p9.load_policy()
        ceiling = policy.ci_watch.max_concurrent_prs
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=1))
        for i in range(ceiling):
            assert p9.main(["watch", str(610 + i), "--repo", "broomva/test"]) == 0
        # one more DISTINCT PR must still hit the ceiling
        rc = p9.main(["watch", "699", "--repo", "broomva/test"])
        assert rc == p9.EXIT_CONCURRENCY_CEILING


# ─────────────────────────────────────────────────────────────────────────────
# P20 cross-review round-1 regressions (adversarial review + CodeRabbit)
# ─────────────────────────────────────────────────────────────────────────────
class TestP20Round1:
    def test_ntfy_unicode_title_rides_in_json_body_not_header(self, p9, monkeypatch):
        """MAJOR #1: real termination titles carry '→'/'—', which die in
        latin-1 HTTP headers. The JSON publish endpoint carries them in the
        UTF-8 body — assert the title never lands in a header."""
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            class _R:
                def read(self):
                    return b"ok"
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            return _R()

        monkeypatch.setattr(p9.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("BROOMVA_P9_NTFY_TOPIC", "t")
        title = "p9 PR #82 → GREEN — done"
        row = p9.notify("termination:green", title, "body")
        assert row["deliveries"] == [{"channel": "ntfy", "ok": True}]
        req = calls[0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["title"] == title
        assert body["topic"] == "t"
        assert req.get_header("Title") is None
        # header values must be latin-1 encodable end-to-end
        for k, v in req.header_items():
            v.encode("latin-1")

    def test_rearm_survives_slash_in_wait_name(self, p9, capsys):
        """MAJOR #2: a dead wait named 'deploy/prod' must be re-armed, not
        crash rearm after destructively folding the row."""
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        p9.append_wait_event(p9.WaitEvent(
            ts=p9._utcnow(), wait_id="wslash", name="deploy/prod",
            from_state="NEW", to_state="WAITING",
            extra={"pid": proc.pid,
                   "argv": [sys.executable, str(_SCRIPTS / "p9.py"),
                            "wait-for", "deploy/prod", "--cmd", "true",
                            "--interval", "0.1", "--timeout", "5"]},
        ))
        rc = p9.main(["rearm", "--now", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        act = out["rearmed"][0]
        assert act.get("rearmed_pid"), f"rearm failed: {act}"
        assert "deploy/prod" not in act["log"].rsplit("/", 1)[-1]
        assert Path(act["log"]).parent == p9.logs_dir()

    def test_rearm_argv_wrong_script_is_rejected(self, p9, capsys):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        p9.append_wait_event(p9.WaitEvent(
            ts=p9._utcnow(), wait_id="wevil", name="evil",
            from_state="NEW", to_state="WAITING",
            extra={"pid": proc.pid,
                   "argv": [sys.executable, "/tmp/not-p9.py",
                            "wait-for", "evil", "--cmd", "true"]},
        ))
        rc = p9.main(["rearm", "--now", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["rearmed"][0].get("skipped")
        # row must NOT have been folded
        assert _wait_rows(p9)[-1]["to_state"] == "WAITING"

    def test_cmd_overrides_preset(self, p9):
        """CodeRabbit major: --cmd must win over --preset, as documented."""
        rc = p9.main(["wait-for", "both", "--preset", "vercel",
                      "--cmd", "true", "--interval", "0.1", "--timeout", "5"])
        assert rc == 0  # vercel preset without --target would be EXIT_USAGE
        rows = _wait_rows(p9)
        assert rows[-1]["extra"]["cmd"] == "true"
        assert rows[-1]["to_state"] == "SUCCEEDED"

    def test_wait_terminal_fold_is_single(self, p9):
        """MINOR #3: exactly one terminal row per wait lifecycle."""
        p9.main(["wait-for", "single", "--cmd", "true",
                 "--interval", "0.1", "--timeout", "5"])
        rows = [r for r in _wait_rows(p9) if r["name"] == "single"]
        terminal = [r for r in rows if r["to_state"] != "WAITING"]
        assert len(terminal) == 1
        # heartbeat cleaned up on terminal fold
        assert not p9.wait_heartbeat_path(rows[-1]["wait_id"]).exists()

    def test_escalated_termination_fires_policy_hook(self, p9, tmp_path, monkeypatch):
        """MINOR #5: 'termination:escalated' must reach the policy
        escalation hook, not just a literal 'escalation' kind."""
        sink = tmp_path / "hook-sink.json"
        hook = tmp_path / "hook.sh"
        hook.write_text(f"#!/bin/sh\ncat > {sink}\n")
        hook.chmod(0o755)
        policy = tmp_path / "policy.yaml"
        policy.write_text(
            (_FIXTURES / "policy-good.yaml").read_text()
            .replace("notify_hook: skills/p9/scripts/p9-escalate-notify.sh",
                     f"notify_hook: {hook}")
        )
        monkeypatch.setenv("BROOMVA_P9_POLICY", str(policy))
        row = p9.notify("termination:escalated", "t", "b")
        assert {"channel": "command", "ok": True} in row["deliveries"]
        assert json.loads(sink.read_text())["title"] == "t"

    def test_status_pr_filter_excludes_waits(self, p9, capsys):
        p9.append_wait_event(p9.WaitEvent(
            ts=p9._utcnow(), wait_id="wx", name="unrelated",
            from_state="NEW", to_state="WAITING",
            extra={"pid": os.getpid()},
        ))
        rc = p9.main(["status", "--json", "--no-reap", "--pr", "1"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["open_waits"] == []

    def test_report_repo_filter_excludes_waits(self, p9, capsys):
        p9.append_wait_event(p9.WaitEvent(
            ts=p9._utcnow(), wait_id="wy", name="unrelated",
            from_state="NEW", to_state="WAITING",
            extra={"pid": os.getpid()},
        ))
        rc = p9.main(["report", "--repo", "broomva/other", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert all(r["kind"] == "pr-watch" for r in out["reports"])

    def test_rearm_repo_less_row_is_folded_before_respawn(self, p9, monkeypatch, capsys):
        """MINOR #8: a repo-less WATCHING row can never be matched by the
        re-spawned watch --adopt; rearm must fold it itself."""
        spawned = []

        def fake_popen(argv, **kw):
            spawned.append(argv)
            return _FakeProc(0)

        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        p9.append_state_event(p9.PRStateEvent(
            ts="2020-01-01T00:00:00+00:00", pr=55, repo="",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="wnorepo", extra={"pid": proc.pid},
        ))
        monkeypatch.setattr(p9.subprocess, "Popen", fake_popen)
        rc = p9.main(["rearm", "--now", "--json"])
        assert rc == 0
        assert p9.current_pr_state(55, "") == p9.PRState.ABANDONED
        assert spawned and "watch" in spawned[0]

    def test_webhook_channel_delivers_payload(self, p9, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            class _R:
                def read(self):
                    return b"ok"
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            return _R()

        monkeypatch.setattr(p9.urllib.request, "urlopen", fake_urlopen)
        p9.notify_config_path().write_text(json.dumps({
            "channels": [{"type": "webhook", "url": "https://x.example/h"}],
        }))
        row = p9.notify("test", "t", "b", {"pr": 9})
        assert row["deliveries"] == [{"channel": "webhook", "ok": True}]
        body = json.loads(calls[0].data.decode("utf-8"))
        assert body["payload"]["pr"] == 9
