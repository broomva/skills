"""BRO-3710 — waits that do work.

On T3 Code the host watches PRs itself (`watch_pull_request`), so p9 must not
run a second `gh --watch`: `p9 watch` records the watch and `p9 observe` folds
it on each wake. And the wait-queue, which had a pop order but no producer,
is now filled by `harvest` and put in front of the agent by two hooks.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_FIXTURES = _HERE / "fixtures"
_SCRIPT = _HERE.parent / "scripts" / "p9.py"
REPO = "broomva/test"


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    monkeypatch.setenv("BROOMVA_P9_REPO", REPO)
    monkeypatch.setenv("BROOMVA_P9_MEMORY_DIRS", "")
    if "p9" in sys.modules:
        del sys.modules["p9"]
    mod = importlib.import_module("p9")
    monkeypatch.setattr(mod, "notify", lambda *a, **k: None)
    return mod


def _checks(monkeypatch, p9, *buckets):
    """Make every `gh pr checks` read return these buckets."""
    rows = [{"name": f"c{i}", "bucket": b} for i, b in enumerate(buckets)]
    monkeypatch.setattr(p9, "_gh_json", lambda cmd, **kw: list(rows))


def _no_spawn(monkeypatch, p9):
    def boom(*a, **k):
        raise AssertionError("a host-owned watch must not spawn gh --watch")
    monkeypatch.setattr(p9, "spawn_watcher", boom)


def _watch_args(pr=7, **kw):
    import argparse
    base = dict(pr=str(pr), repo=None, dry_run=False, detach=False,
                background=False, block=False, slice=None, adopt=False,
                force=False, json=False)
    base.update(kw)
    return argparse.Namespace(**base)


# ── host detection ──────────────────────────────────────────────────────────
class TestHostProfile:
    def test_t3_owns_pr_waits(self, p9, monkeypatch):
        monkeypatch.setenv("T3CODE_THREAD_ID", "thread-1")
        monkeypatch.setenv("CLAUDECODE", "1")
        prof = p9.host_profile()
        assert prof["host"] == "t3"
        assert prof["pr_watch_owner"] == "t3"
        assert prof["background_wakes"] is True

    def test_plain_claude_code_keeps_p9_watcher(self, p9, monkeypatch):
        monkeypatch.setenv("CLAUDECODE", "1")
        assert p9.host_profile()["pr_watch_owner"] == "p9"

    @pytest.mark.parametrize("value", ["p9", "t3"])
    def test_override(self, p9, monkeypatch, value):
        monkeypatch.setenv("T3CODE_THREAD_ID", "thread-1")
        monkeypatch.setenv("P9_PR_WATCH_OWNER", value)
        assert p9.host_profile()["pr_watch_owner"] == value

    def test_host_text_names_watch_pull_request(self, p9, monkeypatch, capsys):
        import argparse
        monkeypatch.setenv("T3CODE_THREAD_ID", "thread-1")
        p9.cmd_host(argparse.Namespace(json=False))
        out = capsys.readouterr().out
        assert "watch_pull_request" in out and "p9 observe" in out


# ── checks verdict ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("checks,verdict", [
    (None, "unknown"),
    ([], "none"),
    ([{"name": "a", "bucket": "pending"}], "pending"),
    ([{"name": "a", "bucket": "pass"}, {"name": "b", "bucket": "skipping"}], "green"),
    ([{"name": "a", "bucket": "fail"}, {"name": "b", "bucket": "pending"}], "red"),
    ([{"name": "a", "bucket": "cancel"}], "red"),
])
def test_checks_verdict(p9, checks, verdict):
    assert p9._checks_verdict(checks)[0] == verdict


def test_red_names_the_failed_checks(p9):
    _, failed = p9._checks_verdict([{"name": "lint", "bucket": "fail"},
                                     {"name": "test", "bucket": "pass"}])
    assert failed == ["lint"]


# ── host-owned watch ────────────────────────────────────────────────────────
class TestHostWatch:
    @pytest.fixture(autouse=True)
    def _t3(self, monkeypatch):
        monkeypatch.setenv("T3CODE_THREAD_ID", "thread-1")

    def test_pending_records_watch_without_gh_watch(self, p9, monkeypatch, capsys):
        _no_spawn(monkeypatch, p9)
        _checks(monkeypatch, p9, "pending")
        assert p9.cmd_watch(_watch_args()) == p9.EXIT_OK
        row = p9.latest_row(7, REPO)
        assert row["to_state"] == "WATCHING"
        assert row["extra"]["host_watch"] == "t3"
        assert row["extra"]["pid"] == 0
        assert "watch_pull_request" in capsys.readouterr().out

    def test_settled_green_folds_at_once(self, p9, monkeypatch):
        _no_spawn(monkeypatch, p9)
        _checks(monkeypatch, p9, "pass")
        p9.cmd_watch(_watch_args())
        assert p9.latest_row(7, REPO)["to_state"] == "GREEN"

    def test_watch_marks_the_wait(self, p9, monkeypatch):
        _no_spawn(monkeypatch, p9)
        _checks(monkeypatch, p9, "pending")
        p9.cmd_watch(_watch_args())
        mark = p9.consume_wait_mark()
        assert mark and mark["pr"] == 7

    def test_dry_run_keeps_classic_path(self, p9, monkeypatch):
        called = []
        monkeypatch.setattr(p9, "_host_watch", lambda *a: called.append(a) or 0)
        p9.cmd_watch(_watch_args(dry_run=True))
        assert not called

    def test_json_reports_host_mode(self, p9, monkeypatch, capsys):
        _no_spawn(monkeypatch, p9)
        _checks(monkeypatch, p9, "pending")
        p9.cmd_watch(_watch_args(json=True))
        out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert out["mode"] == "host" and out["verdict"] == "pending"


class TestObserve:
    @pytest.fixture(autouse=True)
    def _t3(self, monkeypatch):
        monkeypatch.setenv("T3CODE_THREAD_ID", "thread-1")

    def _arm(self, p9, monkeypatch):
        _no_spawn(monkeypatch, p9)
        _checks(monkeypatch, p9, "pending")
        p9.cmd_watch(_watch_args())
        return p9.latest_row(7, REPO)

    def test_red_folds_with_failed_checks(self, p9, monkeypatch):
        self._arm(p9, monkeypatch)
        monkeypatch.setattr(p9, "_gh_json", lambda cmd, **kw: [
            {"name": "lint", "bucket": "fail"}, {"name": "t", "bucket": "pending"}])
        out = p9.observe_pr(7, REPO)
        assert out["folded"] and out["state"] == "RED_UNCLASSIFIED"
        row = p9.latest_row(7, REPO)
        assert row["to_state"] == "RED_UNCLASSIFIED"
        assert row["extra"]["failed_checks"] == ["lint"]

    def test_pending_restamps_the_row(self, p9, monkeypatch):
        first = self._arm(p9, monkeypatch)
        time.sleep(1.1)
        out = p9.observe_pr(7, REPO)
        row = p9.latest_row(7, REPO)
        assert not out["folded"] and row["to_state"] == "WATCHING"
        assert row["ts"] > first["ts"]
        assert row["watcher_id"] == first["watcher_id"]

    def test_second_wake_after_fold_changes_nothing(self, p9, monkeypatch):
        self._arm(p9, monkeypatch)
        _checks(monkeypatch, p9, "pass")
        assert p9.observe_pr(7, REPO)["folded"]
        before = p9.latest_row(7, REPO)
        again = p9.observe_pr(7, REPO)
        assert not again["folded"]
        assert p9.latest_row(7, REPO) == before

    def test_stale_read_cannot_fold_a_rewatch(self, p9, monkeypatch):
        """A re-watch lands between observe's read and its write: the fold
        must lose the compare-and-swap, not bury the live watch."""
        stale = self._arm(p9, monkeypatch)
        p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=7, repo=REPO, from_state="WATCHING",
            to_state="WATCHING", watcher_id="replacement", session_id="",
            extra={"pid": 0, "host_watch": "t3"}))
        real_latest = p9.latest_row
        monkeypatch.setattr(p9, "latest_row", lambda pr, repo=None: dict(stale))
        _checks(monkeypatch, p9, "pass")
        assert not p9.observe_pr(7, REPO)["folded"]
        live = real_latest(7, REPO)
        assert live["to_state"] == "WATCHING"
        assert live["watcher_id"] == "replacement"

    def test_untracked_pr_is_reported_not_folded(self, p9, monkeypatch):
        _checks(monkeypatch, p9, "pass")
        out = p9.observe_pr(99, REPO)
        assert out["state"] is None and not out["folded"]
        assert p9.latest_row(99, REPO) is None


class TestReapHostWatch:
    @pytest.fixture(autouse=True)
    def _t3(self, monkeypatch):
        monkeypatch.setenv("T3CODE_THREAD_ID", "thread-1")

    def _arm(self, p9, monkeypatch):
        _no_spawn(monkeypatch, p9)
        _checks(monkeypatch, p9, "pending")
        p9.cmd_watch(_watch_args())

    def test_fresh_host_watch_survives_reap(self, p9, monkeypatch):
        self._arm(p9, monkeypatch)
        assert p9.reap_stale_watchers(grace_seconds=0) == []
        assert p9.latest_row(7, REPO)["to_state"] == "WATCHING"

    def test_unobserved_past_ttl_is_reaped(self, p9, monkeypatch):
        self._arm(p9, monkeypatch)
        monkeypatch.setenv("BROOMVA_P9_HOST_WATCH_TTL_S", "0")
        reaped = p9.reap_stale_watchers(grace_seconds=0)
        assert len(reaped) == 1
        assert "host watch not observed" in reaped[0]["reason"]


# ── harvest ─────────────────────────────────────────────────────────────────
def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture()
def tree(tmp_path):
    """A checkout whose branch changed src/feature_flag.py, with docs that
    mention it on main."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    files = {
        "src/feature_flag.py": "x = 1\n",
        "docs/guide.md": "Flags live in src/feature_flag.py.\n",
        "research/entities/flags.md": "See feature_flag.py for the toggles.\n",
        "CLAUDE.md": "Never edit feature_flag.py by hand.\n",
        "docs/unrelated.md": "Nothing to see.\n",
    }
    for rel, text in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "origin", "main")
    _git(work, "fetch", "-q", "origin")
    _git(work, "checkout", "-qb", "feature")
    (work / "src/feature_flag.py").write_text("x = 2\n")
    _git(work, "commit", "-qam", "change flag")
    return work


class TestHarvest:
    @pytest.fixture(autouse=True)
    def _on(self, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_HARVEST", "1")

    def test_docs_graph_and_governance(self, p9, tree):
        added = p9.harvest_queue(pr=7, repo="", cwd=tree)
        by_source = {it.source: it for it in added}
        assert sorted(it.source for it in added) == ["docs", "docs", "graph"]
        assert not any("unrelated.md" in it.item for it in added)
        docs = [it for it in added if it.source == "docs"]
        assert {it.item.split()[1] for it in docs} == {"docs/guide.md", "CLAUDE.md"}
        governance = next(it for it in docs if "CLAUDE.md" in it.item)
        assert governance.isolation_tier == "blocked"
        assert by_source["graph"].item.startswith("graph: research/entities/flags.md")
        assert "PR #7" in by_source["graph"].item

    def test_offered_once_even_after_pop(self, p9, tree):
        first = p9.harvest_queue(pr=7, cwd=tree)
        assert first
        while p9.queue_pop() is not None:
            pass
        assert p9.harvest_queue(pr=7, cwd=tree) == []

    def test_other_repo_reads_no_docs(self, p9, tree):
        _git(tree, "remote", "set-url", "origin", "https://github.com/acme/widgets.git")
        assert p9.harvest_queue(pr=7, repo="other/repo", cwd=tree) == []
        assert p9.harvest_queue(pr=7, repo="acme/widgets", cwd=tree)

    def test_off_switch(self, p9, tree, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_HARVEST", "0")
        assert p9.harvest_queue(pr=7, cwd=tree) == []

    def test_memory_follow_ups(self, p9, tmp_path, monkeypatch):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "MEMORY.md").write_text("needs follow-up\n")
        (mem / "fresh.md").write_text("Status: needs follow-up on the gate\n")
        (mem / "quiet.md").write_text("all done\n")
        old = mem / "old.md"
        old.write_text("needs follow-up\n")
        os.utime(old, (time.time() - 3 * 86400,) * 2)
        monkeypatch.setenv("BROOMVA_P9_MEMORY_DIRS", str(mem))
        added = p9.harvest_queue(cwd=tmp_path)
        assert [it.source for it in added] == ["memory"]
        assert "fresh.md" in added[0].item

    def test_never_raises(self, p9, monkeypatch):
        monkeypatch.setattr(p9, "_harvest", lambda *a: 1 / 0)
        assert p9.harvest_queue() == []


# ── hooks ───────────────────────────────────────────────────────────────────
class TestWaitFromTool:
    def test_watch_pull_request_url(self, p9):
        w = p9._wait_from_tool("mcp__t3-code__watch_pull_request",
                               {"url": "https://github.com/acme/widgets/pull/42"})
        assert w == {"tool": "watch_pull_request", "pr": 42, "repo": "acme/widgets"}

    def test_watch_pull_request_number(self, p9):
        w = p9._wait_from_tool("mcp__t3-code__watch_pull_request",
                               {"number": 5, "repository": "acme/widgets"})
        assert w["pr"] == 5 and w["repo"] == "acme/widgets"

    @pytest.mark.parametrize("name,tin,declared", [
        ("mcp__t3-code__delegate_task", {"task": "x"}, True),
        ("mcp__t3-code__delegate_task", {"task": "x", "mode": "wait"}, False),
        ("mcp__t3-code__t3_background_wait", {"taskIds": ["a"]}, True),
        ("mcp__t3-code__t3_background_wait", {"taskIds": ["a"], "waiting": False}, False),
        ("Bash", {"command": "ls"}, False),
        ("mcp__t3-code__task_status", {"taskId": "a"}, False),
    ])
    def test_which_calls_declare_a_wait(self, p9, name, tin, declared):
        assert (p9._wait_from_tool(name, tin) is not None) is declared


class TestHooks:
    def _queue(self, p9, tier="none"):
        p9.queue_push("docs: check the guide", "docs", isolation_tier=tier)

    def test_post_tool_use_marks_and_briefs(self, p9):
        self._queue(p9)
        out = p9.hook_post_tool_use({
            "tool_name": "mcp__t3-code__watch_pull_request",
            "tool_input": {"url": "https://github.com/acme/widgets/pull/42"}})
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert "check the guide" in ctx and "p9 wait-queue pop" in ctx
        assert p9.consume_wait_mark()["pr"] == 42

    def test_post_tool_use_quiet_on_empty_queue(self, p9):
        assert p9.hook_post_tool_use({"tool_name": "mcp__t3-code__delegate_task",
                                      "tool_input": {"task": "x"}}) is None
        assert p9.consume_wait_mark() is not None  # still marked

    def test_post_tool_use_ignores_other_tools(self, p9):
        self._queue(p9)
        assert p9.hook_post_tool_use({"tool_name": "Bash",
                                      "tool_input": {"command": "ls"}}) is None
        assert p9.consume_wait_mark() is None

    def test_stop_blocks_once_per_wait(self, p9):
        self._queue(p9)
        p9.mark_wait("watch_pull_request", pr=1)
        first = p9.hook_stop({})
        assert first["decision"] == "block"
        assert "check the guide" in first["reason"]
        assert p9.hook_stop({}) is None

    def test_stop_never_blocks_the_retry(self, p9):
        self._queue(p9)
        p9.mark_wait("watch_pull_request", pr=1)
        assert p9.hook_stop({"stop_hook_active": True}) is None

    def test_stop_quiet_without_a_wait(self, p9):
        self._queue(p9)
        assert p9.hook_stop({}) is None

    def test_stop_ignores_blocked_items(self, p9):
        self._queue(p9, tier="blocked")
        p9.mark_wait("watch_pull_request", pr=1)
        assert p9.hook_stop({}) is None

    def test_stale_mark_is_dropped(self, p9):
        self._queue(p9)
        p9.mark_wait("watch_pull_request", pr=1)
        path = next(p9.wait_marks_dir().glob("*.json"))
        mark = json.loads(path.read_text())
        mark["ts"] = "2000-01-01T00:00:00+00:00"
        path.write_text(json.dumps(mark))
        assert p9.hook_stop({}) is None

    def test_cli_entry_survives_garbage(self, tmp_path):
        env = {**os.environ, "BROOMVA_P9_HOME": str(tmp_path),
               "BROOMVA_P9_HARVEST": "0"}
        for payload in ("not json", "[1,2]", ""):
            r = subprocess.run([sys.executable, str(_SCRIPT), "hook", "stop"],
                               input=payload, capture_output=True, text=True, env=env)
            assert r.returncode == 0
            assert r.stdout == ""


class TestHookInstall:
    def _settings(self, tmp_path, data):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps(data))
        return path

    def _run(self, p9, path, **kw):
        import argparse
        args = argparse.Namespace(settings=str(path), p9_path="/opt/p9/p9.py",
                                  uninstall=kw.get("uninstall", False),
                                  dry_run=kw.get("dry_run", False))
        return p9.cmd_hook_install(args)

    def test_install_keeps_other_hooks_and_is_idempotent(self, p9, tmp_path):
        other = {"type": "command", "command": "/x/bridge.sh"}
        path = self._settings(tmp_path, {"model": "x", "hooks": {
            "Stop": [{"hooks": [other]}]}})
        self._run(p9, path)
        once = json.loads(path.read_text())
        self._run(p9, path)
        assert json.loads(path.read_text()) == once
        assert once["model"] == "x"
        stop_cmds = [h["command"] for g in once["hooks"]["Stop"] for h in g["hooks"]]
        assert "/x/bridge.sh" in stop_cmds
        assert "python3 -I /opt/p9/p9.py hook stop" in stop_cmds
        post = once["hooks"]["PostToolUse"][0]
        assert post["matcher"] == p9.HOOK_POST_TOOL_MATCHER
        assert post["hooks"][0]["command"].endswith("hook post-tool-use")

    def test_uninstall_removes_only_p9(self, p9, tmp_path):
        other = {"type": "command", "command": "/x/bridge.sh"}
        path = self._settings(tmp_path, {"hooks": {"Stop": [{"hooks": [other]}]}})
        self._run(p9, path)
        self._run(p9, path, uninstall=True)
        assert json.loads(path.read_text()) == {"hooks": {"Stop": [{"hooks": [other]}]}}

    def test_dry_run_writes_nothing(self, p9, tmp_path):
        path = self._settings(tmp_path, {})
        self._run(p9, path, dry_run=True)
        assert json.loads(path.read_text()) == {}

    def test_refuses_invalid_json(self, p9, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("{oops")
        assert self._run(p9, path) == p9.EXIT_DEGRADED
        assert path.read_text() == "{oops"
