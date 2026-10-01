"""The janitor's guard (spec §5.5): each check passes, fails, or can't run, and
either of the last two aborts; the backup; and the run, which removes only
scratch worktrees until the janitor drill passes."""
from __future__ import annotations

import json
import os
import subprocess
import time

import pytest
from conftest import _git

from fleetlib import config, janitor
from fleetlib.sources import FixtureSources

OWNER = "%08d-0000-4000-8000-%012d" % (31, 31)


@pytest.fixture
def wt(world, tmp_path):
    """A scratch repo (no origin, in no scope) with a worktree, its files 2 days old."""
    repo = tmp_path / "scratch"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / ".gitignore").write_text(".env\nnode_modules/\n")
    (repo / "a.txt").write_text("a\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "init", cwd=repo)
    path = tmp_path / "wt-1"
    _git("worktree", "add", "-q", "-b", "feat/x", str(path), cwd=repo)
    (path / ".env").write_text("SECRET=1\n")
    (path / "new.txt").write_text("untracked\n")
    (path / "a.txt").write_text("a changed\n")
    old = time.time() - 2 * 86400
    for root, _, files in os.walk(path):
        for f in files:
            os.utime(os.path.join(root, f), (old, old))
    return path


def _listing(w, rows):
    (w.fixture / "claude" / "agents.json").write_text(json.dumps(rows))


def _row(sid, cwd, state="done", pid=None, kind="background"):
    r = {"sessionId": sid, "kind": kind, "cwd": str(cwd), "name": "fleet-drill-1", "startedAt": 1_790_000_000_000,
         "id": sid[:8], "state": state}
    if pid:
        r.update(pid=pid, status="busy")
    return r


def _guard(w, path, owner=OWNER):
    return janitor.Guard(config.scope("broomva"), FixtureSources(w.fixture), str(path), owner)


def test_a_finished_owner_in_a_quiet_backed_up_worktree_passes_every_check(world, wt):
    _listing(world, [_row(OWNER, wt)])
    res = _guard(world, wt).run()
    assert res["ok"] and res["exit"] == 0, res
    assert [c["check"] for c in res["checks"]] == list(janitor.CHECKS)


def test_the_owner_must_have_finished_and_be_listed(world, wt):
    _listing(world, [_row(OWNER, wt, state="running", pid=4242)])
    assert _guard(world, wt).owner_finished()[0] == "fail"
    _listing(world, [])
    assert _guard(world, wt).owner_finished()[0] == "not run"


def test_another_live_session_in_the_worktree_fails_it(world, wt):
    other = "%08d-0000-4000-8000-%012d" % (32, 32)
    _listing(world, [_row(OWNER, wt), _row(other, wt / "sub", pid=999, kind="interactive")])
    verdict, detail = _guard(world, wt).no_live_session()
    assert verdict == "fail" and "00000032" in detail


def test_a_file_modified_in_the_last_day_fails_it(world, wt):
    (wt / "a.txt").write_text("touched\n")
    verdict, detail = _guard(world, wt).quiet_24h()
    assert verdict == "fail" and "a.txt" in detail


def test_an_ignored_secret_it_cant_read_fails_the_backup_check(world, wt):
    (wt / ".env").chmod(0)
    try:
        verdict, detail = _guard(world, wt).backup_possible()
        assert verdict == "fail" and ".env" in detail
    finally:
        (wt / ".env").chmod(0o600)


def test_a_process_holding_the_worktree_fails_it(world, wt):
    holder = subprocess.Popen(["sleep", "30"], cwd=str(wt))
    try:
        time.sleep(0.3)
        verdict, detail = _guard(world, wt).no_holder()
        assert verdict == "fail" and str(holder.pid) in detail
    finally:
        holder.kill()
        holder.wait()
    assert _guard(world, wt).no_holder()[0] == "pass"


def test_a_process_listing_that_shows_only_the_janitors_own_is_a_check_that_didnt_run(world, wt, monkeypatch):
    monkeypatch.setattr(janitor, "_children", lambda listed: set(listed))  # as a sandbox shows it: only itself
    verdict, detail = _guard(world, wt).no_holder()
    assert verdict == "not run" and "nothing but the janitor's own" in detail
    _listing(world, [_row(OWNER, wt)])
    res = _guard(world, wt).run()
    assert not res["ok"] and res["exit"] == 2


def test_no_origin_or_a_detached_head_has_no_pr(world, wt):
    assert _guard(world, wt).pr_closed() == ("pass", "no GitHub origin, so no PR")
    _git("checkout", "-q", "--detach", cwd=wt)
    assert _guard(world, wt).pr_closed()[0] == "pass"


def test_the_backup_holds_the_diff_untracked_files_secrets_and_a_branch_for_unpushed_commits(world, wt):
    res = janitor.backup(world.state["broomva"], str(wt))
    d = res["dir"]
    assert "a changed" in open(os.path.join(d, "diff.patch")).read()
    assert open(os.path.join(d, "untracked", "new.txt")).read() == "untracked\n"
    assert open(os.path.join(d, "secrets", ".env")).read() == "SECRET=1\n"
    assert res["unpushed"] >= 1 and res["branch"].startswith("fleet-backup/")  # no remote: every commit is unpushed
    assert subprocess.run(["git", "-C", str(wt), "rev-parse", "--verify", res["branch"]],
                          capture_output=True).returncode == 0
    assert oct(os.stat(d).st_mode & 0o777) == "0o700"


def test_backups_older_than_fourteen_days_are_pruned(world, wt):
    res = janitor.backup(world.state["broomva"], str(wt))
    old = time.time() - 15 * 86400
    os.utime(res["dir"], (old, old))
    assert janitor.prune(world.state["broomva"]) == 1 and not os.path.exists(res["dir"])


def test_the_run_reports_only_without_remove_and_never_removes_a_scope_repos_worktree(world, wt, monkeypatch):
    _listing(world, [_row(OWNER, wt)])
    src = FixtureSources(world.fixture)
    res = janitor.run(config.scope("broomva"), src, str(wt), OWNER, False, lambda m: None)
    assert "would" in res and src.calls == []
    scoped = world.home / "wt"
    target = sorted(p for p in scoped.iterdir() if p.is_dir())[0]
    _listing(world, [_row(OWNER, target)])
    monkeypatch.setattr(janitor.Guard, "quiet_24h", lambda self: ("pass", "stubbed"))  # the shared repos stay untouched
    assert janitor.scratch(str(wt)) and not janitor.scratch(str(target))
    res = janitor.run(config.scope("broomva"), src, str(target), OWNER, True, lambda m: None)
    assert "refused for a scope repo" in res.get("aborted", ""), res
    assert src.calls == []


def test_a_scratch_run_stops_rechecks_backs_up_rereads_and_removes(world, wt):
    _listing(world, [_row(OWNER, wt)])
    src = FixtureSources(world.fixture)
    res = janitor.run(config.scope("broomva"), src, str(wt), OWNER, True, lambda m: None)
    assert [s["step"] for s in res["steps"]] == ["check", "stop", "re-check", "backup", "listing at removal", "rm"]
    assert src.calls == [["claude", "rm", OWNER]]  # a done owner with no process isn't stopped again
    _listing(world, [dict(_row(OWNER, wt), pid=4242, status="idle")])
    src = FixtureSources(world.fixture)
    janitor.run(config.scope("broomva"), src, str(wt), OWNER, True, lambda m: None)
    assert src.calls[0] == ["claude", "stop", OWNER]
