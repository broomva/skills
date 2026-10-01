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


def _detached_holder(cwd):
    """A process in the worktree that isn't the janitor's child (here the test
    process plays the janitor): its shell exits, so launchd adopts it."""
    out = subprocess.run(["/bin/sh", "-c", "sleep 30 >/dev/null 2>&1 & echo $!"], cwd=str(cwd), capture_output=True,
                         text=True, start_new_session=True)
    return int(out.stdout.strip())


def test_a_process_holding_the_worktree_fails_it(world, wt):
    pid = _detached_holder(wt)
    try:
        time.sleep(0.3)
        verdict, detail = _guard(world, wt).no_holder()
        assert verdict == "fail" and str(pid) in detail
    finally:
        os.kill(pid, 9)
    time.sleep(0.2)
    assert _guard(world, wt).no_holder()[0] == "pass"


def test_the_janitors_own_ancestors_and_children_dont_count_as_holders_or_as_a_listing(world, wt, monkeypatch):
    me, parent = os.getpid(), os.getppid()
    child = subprocess.Popen(["sleep", "30"], cwd=str(wt))  # the janitor's own child, like its lsof
    try:
        time.sleep(0.3)
        assert _guard(world, wt).no_holder()[0] == "pass"
    finally:
        child.kill()
        child.wait()
    # A sandbox shows the janitor, its shell and the session above it: still blind.
    monkeypatch.setattr(janitor, "_ps", lambda: {me: parent, parent: 4242, 4242: 1, child.pid: me})
    assert janitor._own(janitor._ps()) == {me, parent, 4242, child.pid}
    assert _guard(world, wt).no_holder()[0] == "not run"


def test_a_process_listing_that_shows_only_the_janitors_own_is_a_check_that_didnt_run(world, wt, monkeypatch):
    monkeypatch.setattr(janitor, "_ps", lambda: {os.getpid(): os.getppid()})  # as a sandbox shows it: only itself
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


def test_two_backups_at_one_instant_both_land(world, wt):
    a = janitor.backup(world.state["broomva"], str(wt), now=1_790_000_000.0)
    b = janitor.backup(world.state["broomva"], str(wt), now=1_790_000_000.0)
    assert a["dir"] != b["dir"] and os.path.isdir(a["dir"]) and os.path.isdir(b["dir"])


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
    # A scope repo's owner needs a terminal status on the board; the listing's "done" isn't one.
    assert res["aborted"] == "check" and "no board row for the owner" in json.dumps(res["steps"])
    monkeypatch.setattr(janitor.Guard, "owner_finished", lambda self: ("pass", "stubbed"))
    res = janitor.run(config.scope("broomva"), src, str(target), OWNER, True, lambda m: None)
    assert "refused for a scope repo" in res.get("aborted", ""), res
    assert src.calls == []


def test_the_owner_must_own_the_worktree_it_removes(world, wt, tmp_path):
    elsewhere = tmp_path / "another-worktree"
    elsewhere.mkdir()
    _listing(world, [_row(OWNER, elsewhere)])
    src = FixtureSources(world.fixture)
    res = janitor.run(config.scope("broomva"), src, str(wt), OWNER, True, lambda m: None)
    assert res["aborted"] == "owner" and "not in this worktree" in res["steps"][-1]["out"] and src.calls == []


def test_a_secret_inside_an_ignored_directory_is_found(world, wt):
    (wt / ".gitignore").write_text(".env\nnode_modules/\ndata/\n")
    (wt / "data").mkdir()
    (wt / "data" / "app.db").write_text("rows")
    assert "data/app.db" in janitor.secret_files(str(wt))


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


def test_an_open_pr_on_the_worktrees_branch_fails_it(world, wt):
    _git("remote", "add", "origin", "https://github.com/broomva/workspace.git", cwd=wt)
    (world.fixture / "gh" / "broomva__workspace" / "prs-head-feat__x.json").write_text('[{"number": 5, "state": "OPEN"}]')
    assert _guard(world, wt).pr_closed() == ("fail", "PR #5 is open")
    (world.fixture / "gh" / "broomva__workspace" / "prs-head-feat__x.json").write_text('[{"number": 5, "state": "MERGED"}]')
    assert _guard(world, wt).pr_closed()[0] == "pass"


def test_path_must_be_the_owners_worktree_not_a_directory_above_it(world, wt):
    _listing(world, [_row(OWNER, wt)])
    above = str(wt.parent)
    res = janitor.run(config.scope("broomva"), FixtureSources(world.fixture), above, OWNER, True, lambda m: None)
    assert res["aborted"] == "owner"


def test_scratch_fails_closed(world, wt, tmp_path, monkeypatch):
    assert janitor.scratch(str(wt))
    broken = tmp_path / "broken"
    (broken / ".git").mkdir(parents=True)  # a repo git can't read
    assert not janitor.scratch(str(broken))
    import ctx
    common = os.path.realpath(subprocess.run(["git", "-C", str(wt), "rev-parse", "--git-common-dir"],
                                             capture_output=True, text=True).stdout.strip())
    real = ctx.load_scopes()
    monkeypatch.setattr(ctx, "load_scopes", lambda: type("S", (), {"by_repo": dict(real.by_repo, **{common: None})}))
    assert not janitor.scratch(str(wt))  # listed in two scopes (None): still a scope repo


def test_secrets_in_ignored_dirs_are_found_but_dependency_dirs_are_skipped(world, wt):
    (wt / ".gitignore").write_text(".env\nnode_modules/\ndata/\n")
    for rel in ("data/app.db", "node_modules/pkg/cache.db"):
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text("x")
    found = janitor.secret_files(str(wt))
    assert "data/app.db" in found and not any(f.startswith("node_modules") for f in found)


def test_a_worktree_claude_rm_keeps_is_an_abort_and_a_removed_ones_profile_goes(world, wt):
    _listing(world, [_row(OWNER, wt)])
    sd = world.state["broomva"]
    (sd / "profiles").mkdir(parents=True)
    prof = sd / "profiles" / "broomva-x-pr1.json"  # keyed by the ledger's spawn of this session
    prof.write_text("{}")
    decoy = sd / "profiles" / "fleet-drill-1.json"  # the listing's name: never what decides
    decoy.write_text("{}")
    from fleetlib import ledger
    it = ledger.append(sd, {"kind": "intent", "verb": "spawn", "key": "broomva-x-pr1", "target": {"name": "x"},
                            "scope": "broomva", "tick": 1, "dry_run": False, "by": "act"})
    ledger.append(sd, {"kind": "done", "verb": "spawn", "of": it["id"], "key": "broomva-x-pr1",
                       "result": {"session_id": OWNER}, "scope": "broomva", "tick": 1, "dry_run": False, "by": "act"})
    src = FixtureSources(world.fixture)
    res = janitor.run(config.scope("broomva"), src, str(wt), OWNER, True, lambda m: None)
    assert res["aborted"] == "rm kept the worktree" and prof.exists()  # the fixture's rm removes nothing

    class Removes(FixtureSources):
        def run_claude(self, args, cwd=None, timeout=120):
            if args[0] == "rm":
                subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=str(wt.parent / "scratch"),
                               capture_output=True)
            return "removed"
    res = janitor.run(config.scope("broomva"), Removes(world.fixture), str(wt), OWNER, True, lambda m: None)
    assert res["removed"] and not prof.exists() and decoy.exists(), res
