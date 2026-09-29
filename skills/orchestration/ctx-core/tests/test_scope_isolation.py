"""Scope resolution and isolation.

A scope comes from scopes.yaml alone, keyed by the realpath of the repo's git
common dir. The sri and broomva stores never cross: an sri session neither
writes to nor reads from broomva's store, which is checked by auditing every
file the process opens, not only by looking at what it outputs.
"""
from __future__ import annotations

import builtins
import io
import json
import os
import subprocess
import time

import pytest

import ctx
from conftest import World


def test_unscoped_repo_is_a_silent_noop(world: World) -> None:
    for run in (world.start("s-other", world.other), world.stop("s-other", world.other, "ARC-STATUS: DONE x"),
                world.died("s-other", world.other)):
        assert (run.rc, run.stdout, run.stderr) == (0, "", "")
    assert not (world.home / ".local" / "state").exists(), "an unscoped session created the state root"
    for args in (("board",), ("board", "--json"), ("board", "--rebuild"), ("doctor",)):
        res = world.cli(*args, cwd=world.other)
        assert (res.returncode, res.stdout, res.stderr) == (0, "", ""), args


def test_no_config_or_no_repo_is_a_noop(world: World) -> None:
    (world.home / ".config" / "ctx" / "scopes.yaml").unlink()
    assert world.start("s-1", world.broomva).stdout == ""
    scratch = world.home / "not-a-repo"
    scratch.mkdir()
    (world.home / ".config" / "ctx" / "scopes.yaml").write_text("scopes:\n  broomva:\n    - ~/broomva\n")
    assert world.start("s-2", scratch).stdout == ""
    assert world.events("broomva") == []


def test_worktree_resolves_to_the_main_checkouts_scope(world: World) -> None:
    assert world.start("s-main", world.broomva).rc == 0
    assert world.start("s-wt", world.worktree).rc == 0
    evs = world.events("broomva")
    assert {e["session_id"] for e in evs} == {"s-main", "s-wt"}
    assert {e["repo"] for e in evs} == {str(world.broomva / ".git")}
    assert {e["session_id"]: e["branch"] for e in evs} == {"s-main": "main", "s-wt": "feat/x"}


def test_sri_and_broomva_stores_never_cross(world: World) -> None:
    world.start("b-1", world.broomva)
    world.stop("b-1", world.broomva, "ARC-STATUS: MERGED broomva-only")
    world.start("s-1", world.sri)
    run = world.start("s-2", world.sri)
    world.stop("s-2", world.sri, "ARC-STATUS: DONE sri-only")

    assert {e["session_id"] for e in world.events("broomva")} == {"b-1"}
    assert {e["session_id"] for e in world.events("sri")} == {"s-1", "s-2"}
    assert "s-1" in run.context and "b-1" not in run.context and "broomva-only" not in run.context
    sri_board = json.loads(world.cli("board", "--json", cwd=world.sri).stdout)
    assert set(sri_board["sessions"]) == {"s-1", "s-2"}
    assert "broomva-only" not in json.dumps(sri_board)


def test_an_sri_session_never_opens_a_path_in_broomvas_store(world: World, monkeypatch) -> None:
    """Audit every open(), io.open() (which pathlib uses) and os.open() while
    sri hooks run in-process."""
    world.start("b-1", world.broomva)
    world.stop("b-1", world.broomva, "ARC-STATUS: MERGED x")
    world.start("s-0", world.sri)
    world.cli("board", cwd=world.sri)  # sri has a cache, so SessionStart opens its board.json
    world.cli("board", cwd=world.broomva)  # and so does broomva: a cross read would be possible
    opened = []
    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

    def audit_open(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)

    def audit_io_open(file, *a, **k):
        opened.append(str(file))
        return real_io_open(file, *a, **k)

    def audit_os_open(path, *a, **k):
        opened.append(str(path))
        return real_os_open(path, *a, **k)

    monkeypatch.setattr(builtins, "open", audit_open)
    monkeypatch.setattr(io, "open", audit_io_open)
    monkeypatch.setattr(os, "open", audit_os_open)
    for event, extra in (("session-start", {}),
                         ("stop", {"last_assistant_message": "ARC-STATUS: DONE"}),
                         ("stop-failure", {"error_type": "server_error"})):
        payload = dict({"session_id": "s-audit", "cwd": str(world.sri)}, **extra)
        ctx.run_hook(event, json.dumps(payload), deadline=time.monotonic() + 5)
    monkeypatch.setattr(builtins, "open", real_open)
    monkeypatch.setattr(io, "open", real_io_open)
    monkeypatch.setattr(os, "open", real_os_open)

    broomva_store = str(world.store("broomva"))
    sri_store = str(world.store("sri"))
    assert any(p.startswith(sri_store) for p in opened), "the audit saw nothing: vacuous"
    assert any(p == sri_store + "/board.json" for p in opened), "a pathlib read went unaudited"
    assert [p for p in opened if p.startswith(broomva_store)] == []


def test_a_repo_in_two_scopes_has_no_scope_and_the_others_are_unaffected(world: World) -> None:
    (world.home / ".config" / "ctx" / "scopes.yaml").write_text(
        "scopes:\n  broomva:\n    - ~/broomva\n    - ~/other\n  sri:\n    - ~/broomva/.git\n"
        "    - ~/broomva/work/sri\n")
    run = world.start("s-1", world.broomva)
    assert (run.rc, run.stdout) == (0, "")
    world.start("s-2", world.other)
    world.start("s-3", world.sri)
    assert [e["session_id"] for e in world.events("broomva")] == ["s-2"]
    assert [e["session_id"] for e in world.events("sri")] == ["s-3"]
    report = world.cli("doctor", "--unscoped", cwd=world.other)
    assert report.returncode == 1 and "is listed in scopes broomva, sri" in report.stdout


@pytest.mark.parametrize("bad", ["../evil", "Broomva", "a/b", "-x", ""])
def test_scope_ids_cannot_escape_the_state_root(bad: str) -> None:
    with pytest.raises(ctx.ConfigError):
        ctx.parse_scopes("scopes:\n  %s:\n    - ~/x\n" % (bad or "''"))


@pytest.mark.parametrize("text", [
    "scopes:\n  broomva:\n  - ~/x\n",            # item not deeper than its scope
    "scopes:\n\tbroomva:\n",                    # tab indentation
    "scope:\n  broomva:\n    - ~/x\n",          # unknown top-level key
    "scopes:\n  broomva:\n    - ~/x\n  broomva:\n    - ~/y\n",
])
def test_malformed_config_is_a_config_error(text: str) -> None:
    with pytest.raises(ctx.ConfigError):
        ctx.parse_scopes(text)


def test_config_accepts_comments_quotes_and_git_dirs(world: World) -> None:
    parsed = ctx.parse_scopes("# c\nversion: 1\nscopes:\n  a:\n    - '~/p q'   # c\n    - \"~/r#s\"\n")
    assert parsed == {"a": ["~/p q", "~/r#s"]}


def test_crm_and_credential_shaped_cwds_are_never_written(world: World) -> None:
    subs = ("crm", "crm/deals", "vendor/xoxb-tokens", "k/" + "A1b2" * 8)
    for sub in subs:
        d = world.broomva / sub
        d.mkdir(parents=True, exist_ok=True)
        run = world.start("s-%d" % subs.index(sub), d)
        assert (run.rc, run.stdout) == (0, "")
        assert ctx.resolve_scope(str(d)) is None, sub  # the first layer, on its own
    assert world.events("broomva") == []
    # The second layer: an event is not even built for a guard-failing cwd.
    scope = ctx.resolve_scope(str(world.broomva))
    crm = scope._replace(where=scope.where._replace(cwd=str(world.broomva / "crm")))
    assert ctx.make_event("session.stop", crm, "s-x", {}) is None
    # "mycrm" is not crm/, and "task-list" is not a token.
    for sub in ("mycrm", "fix/task-list"):
        (world.broomva / sub).mkdir(parents=True)
        assert ctx.resolve_scope(str(world.broomva / sub)) is not None, sub


def test_doctor_unscoped_lists_repos_with_sessions_but_no_scope(world: World) -> None:
    projects = world.home / ".claude" / "projects"
    for name, cwd in (("p-other", world.other), ("p-broomva", world.broomva),
                      ("p-gone", world.home / "deleted-worktree")):
        (projects / name).mkdir(parents=True)
        (projects / name / "s1.jsonl").write_text(
            json.dumps({"type": "summary"}) + "\n" + json.dumps({"cwd": str(cwd), "sessionId": "s1"}) + "\n")
    res = world.cli("doctor", "--unscoped", cwd=world.home)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "unscoped repos with sessions: 1" in res.stdout
    assert str(world.other.relative_to(world.home)) in res.stdout
    assert "broomva/.git" not in res.stdout
    assert "1 sessions in a cwd that no longer exists" in res.stdout


def _git_says(cwd) -> tuple:
    out = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir",
                          "--show-toplevel"], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    common, top = out.stdout.split()
    return os.path.realpath(common), os.path.realpath(top)


def test_the_filesystem_resolver_agrees_with_git(world: World, tmp_path) -> None:
    """ctx reads .git / gitdir / commondir itself so a hook spawns no process.
    It must give `git rev-parse` 's answer on every layout it handles."""
    sub = world.broomva / "pkg" / "deep"
    sub.mkdir(parents=True)
    # a submodule
    subprocess.run(["git", "-c", "protocol.file.allow=always", "-c", "user.name=t", "-c", "user.email=t@e",
                    "submodule", "add", "-q", str(world.other), "vendor/other"], cwd=str(world.broomva),
                   check=True, capture_output=True)
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    wt_sub = world.worktree / "a" / "b"
    wt_sub.mkdir(parents=True)
    mod_sub = world.broomva / "vendor" / "other" / "x"
    mod_sub.mkdir(parents=True)
    cases = [world.broomva, sub, world.worktree, wt_sub, world.sri, world.broomva / "vendor" / "other", mod_sub,
             world.broomva / ".git", world.broomva / ".git" / "refs", bare, world.home]
    for cwd in cases:
        got = ctx.locate(str(cwd))
        want = _git_says(cwd)
        assert (got and (got.common_dir, got.toplevel)) == (want or None), cwd
    assert ctx.locate(str(world.worktree)).branch == "feat/x"
    subprocess.run(["git", "checkout", "-q", "--detach"], cwd=str(world.sri), check=True)
    assert ctx.locate(str(world.sri)).branch.startswith("detached@")


def test_a_config_entry_may_name_a_worktree_or_a_git_dir(world: World) -> None:
    (world.home / ".config" / "ctx" / "scopes.yaml").write_text(
        "scopes:\n  broomva:\n    - %s\n  sri:\n    - %s/.git\n" % (world.worktree, world.sri))
    world.start("s-1", world.broomva)  # the main checkout, reached through its worktree's entry
    world.start("s-2", world.sri)
    assert [e["session_id"] for e in world.events("broomva")] == ["s-1"]
    assert [e["session_id"] for e in world.events("sri")] == ["s-2"]


def test_git_redirected_by_the_environment_falls_back_to_git(world: World, monkeypatch) -> None:
    monkeypatch.setenv("GIT_DIR", str(world.sri / ".git"))
    where = ctx.locate(str(world.broomva))
    assert where and where.common_dir == os.path.realpath(str(world.sri / ".git"))


def test_a_config_entry_may_name_a_submodule(world: World) -> None:
    subprocess.run(["git", "-c", "protocol.file.allow=always", "-c", "user.name=t", "-c", "user.email=t@e",
                    "submodule", "add", "-q", str(world.other), "vendor/other"], cwd=str(world.broomva),
                   check=True, capture_output=True)
    mod = world.broomva / "vendor" / "other"
    (world.home / ".config" / "ctx" / "scopes.yaml").write_text("scopes:\n  mods:\n    - %s\n" % mod)
    world.start("s-1", mod)
    assert [e["session_id"] for e in world.events("mods")] == ["s-1"]
    assert world.events("mods")[0]["repo"] == os.path.realpath(str(world.broomva / ".git" / "modules" / "vendor" / "other"))


def test_a_reftable_repo_gets_its_branch_from_git(tmp_path) -> None:
    repo = tmp_path / "rt"
    made = subprocess.run(["git", "init", "-q", "--ref-format=reftable", "-b", "feat/rt", str(repo)],
                          capture_output=True)
    if made.returncode != 0:
        import pytest as _pytest
        _pytest.skip("this git has no reftable support")
    assert (repo / ".git" / "HEAD").read_text().strip() == "ref: refs/heads/.invalid"
    assert ctx.locate(str(repo)).branch == "feat/rt"
