"""Where a path, a PR and a re-offered claim belong, and the two races
round 2 found: housekeeping against a session's lock, and a deadline between
the saved state and the printed output."""
from __future__ import annotations

import json
import os
import time

import s1_support as S
import ctx_keys as K
import ctx_s1
import ctx_s2

NOW = 1_790_000_000.0


def test_a_path_in_a_nested_repo_of_another_scope_is_not_keyed(world):
    """sri is its own repo inside broomva's tree and its own scope: a broomva
    session reading it keys nothing, so nothing of it reaches broomva's log."""
    S.write_corpus(world)
    where = ctx_s1.ctx.resolve_scope(str(world.broomva)).where
    plan = world.sri / "plan.md"
    plan.write_text("x")
    keys, self_obj, path_key, _ = ctx_s1.extract_keys(
        "post-read", {"tool_input": {"file_path": str(plan)}}, where, "broomva", "broomva")
    assert not any(keys.values()) and not self_obj and path_key is None
    # the session's own file still keys
    keys, _, path_key, _ = ctx_s1.extract_keys(
        "post-read", {"tool_input": {"file_path": str(world.broomva / "scripts" / "gate.py")}}, where, "broomva",
        "broomva")
    assert path_key == "scripts/gate.py" and "p:scripts/gate.py" in keys["p"]


def test_a_path_in_an_unscoped_repo_is_not_keyed(world):
    where = ctx_s1.ctx.resolve_scope(str(world.broomva)).where
    f = world.other / "README.md"
    f.write_text("x")
    keys, _, path_key, _ = ctx_s1.extract_keys("pre-edit", {"tool_input": {"file_path": str(f)}}, where,
                                               "broomva", "broomva")
    assert not any(keys.values()) and path_key is None


def test_a_pr_in_another_repo_is_keyed_to_that_repo():
    assert K.bash_actions("gh pr view 12 -R broomva/bstack") == [("pr-view", "12", "bstack")]
    assert K.bash_actions("gh pr checks --repo=broomva/Bstack 7") == [("pr-checks", "7", "bstack")]
    assert K.bash_actions("gh pr view https://github.com/broomva/bstack/pull/12") == [("pr-view", "12", "bstack")]
    assert K.bash_actions("gh pr merge 9 --squash") == [("pr-merge", "9", None)]
    assert K.bash_actions("gh pr view -Rbroomva/bstack 12") == [("pr-view", "12", "bstack")]
    # an option's value is not the PR's number
    assert K.bash_actions("gh pr checks --watch --interval 10") == [("pr-checks", None, None)]
    assert K.bash_actions("gh pr list --limit 30") == []
    assert K.bash_actions("gh pr comment 41 --body 7") == [("pr-comment", "41", None)]
    keys, _, _, label = ctx_s1.extract_keys("post-bash", {"tool_input": {"command": "gh pr view 12 -R o/bstack"}},
                                            None, "workspace")
    assert keys["pr"] == ["pr:bstack#12"] and label == "bstack#12"


def test_a_reoffered_session_or_pr_claim_ages_out(tmp_path):
    items = [ctx_s2.make_item("spec:docs/a.html", "spec", "A spec on feat/x.", "docs/a.html", NOW,
                              {"b": ["b:feat/x"]}, ["o:docs/a.html"])]
    r = ctx_s2.BM25Ranker()
    r.fit(items)
    ctx_s2.write_cache(tmp_path / "store", items, r, now=NOW)
    reader = ctx_s1.CacheReader(tmp_path / "store")
    rec = lambda t: {"stage": "prompt", "ts": t, "score": 1.0, "claim": "c", "source": "s", "obj": []}
    state = {"injected": {"session:abcd": rec(NOW), "pr:skills#7": rec(NOW), "spec:docs/a.html": rec(NOW)}}
    params = dict(ctx_s1.DEFAULT_PARAMS, stages={"compact": {"floor": 0.0}})
    soon = ctx_s1.decide("compact", {"b": ["b:feat/x"]}, set(), state, reader, params, now=NOW + 3600)
    assert {t[0] for t in soon["top"]} == {"session:abcd", "pr:skills#7", "spec:docs/a.html"}
    later = ctx_s1.decide("compact", {"b": ["b:feat/x"]}, set(), state, reader, params, now=NOW + 7 * 3600)
    assert {t[0] for t in later["top"]} == {"pr:skills#7", "spec:docs/a.html"}
    # the age is the claim's as-of time, not when this session received it: a
    # fresh cache, a claim received an hour ago, but as of seven hours ago
    ctx_s2.write_cache(tmp_path / "fresh", items, r, now=NOW + 6 * 3600)
    fresh = ctx_s1.CacheReader(tmp_path / "fresh")
    state["injected"]["session:abcd"] = dict(rec(NOW + 6 * 3600), as_of=NOW)
    again = ctx_s1.decide("compact", {"b": ["b:feat/x"]}, set(), state, fresh, params, now=NOW + 7 * 3600)
    assert "session:abcd" not in {t[0] for t in again["top"]}
    state["injected"]["session:abcd"] = dict(rec(NOW + 6 * 3600), as_of=NOW + 6 * 3600)
    again = ctx_s1.decide("compact", {"b": ["b:feat/x"]}, set(), state, fresh, params, now=NOW + 7 * 3600)
    assert "session:abcd" in {t[0] for t in again["top"]}


def test_a_subagent_does_not_spend_the_sessions_allowance(tmp_path):
    items = [ctx_s2.make_item("spec:docs/a.html", "spec", "A spec on feat/x.", "docs/a.html", NOW,
                              {"b": ["b:feat/x"]}, ["o:docs/a.html"])]
    r = ctx_s2.BM25Ranker()
    r.fit(items)
    ctx_s2.write_cache(tmp_path / "store", items, r, now=NOW)
    reader = ctx_s1.CacheReader(tmp_path / "store")
    state = {"injected": {"spec:docs/a.html": {"ts": NOW, "score": 1.0, "claim": "c", "source": "s", "obj": []}},
             "counts": {"total": ctx_s1.SESSION_MAX}}
    params = dict(ctx_s1.DEFAULT_PARAMS, stages={"subagent": {"floor": 0.0}})
    d = ctx_s1.decide("subagent", {"b": ["b:feat/x"]}, set(), state, reader, params, agent_id="a1",
                      agent_type="general-purpose", now=NOW)
    assert d["outcome"] == "inject", d["reason"]


def test_housekeeping_never_removes_a_held_or_recently_used_lock(tmp_path):
    store = tmp_path / "store"
    handle, state = ctx_s1.open_state(store, "sess-old")
    lock = store / ctx_s1.STATE_DIR / "sess-old.lock"
    week_ago = time.time() - 8 * 86400
    os.utime(str(lock), (week_ago, week_ago))
    assert ctx_s2.gc_sessions(store) == 0 and lock.exists()  # held: left alone
    ctx_s1.save_state(handle, state)
    handle, _ = ctx_s1.open_state(store, "sess-old")  # a use touches it
    ctx_s1.release_state(handle)
    assert time.time() - lock.stat().st_mtime < 60
    assert ctx_s2.gc_sessions(store) == 0 and lock.exists()
    for p in (store / ctx_s1.STATE_DIR).iterdir():
        os.utime(str(p), (week_ago, week_ago))
    assert ctx_s2.gc_sessions(store) == 2 and not lock.exists()  # idle a week: state and lock go


def test_housekeeping_leaves_a_sessions_state_while_its_lock_is_held(tmp_path):
    """Old state and an old lock, but a hook holds the lock (it has not touched
    it yet): nothing is removed under it."""
    import fcntl

    d = tmp_path / "store" / ctx_s1.STATE_DIR
    d.mkdir(parents=True)
    state, lock = d / "sess-y.json", d / "sess-y.lock"
    state.write_text("{}")
    lock.write_text("")
    week_ago = time.time() - 8 * 86400
    for f in (state, lock):
        os.utime(str(f), (week_ago, week_ago))
    fd = os.open(str(lock), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        assert ctx_s2.gc_sessions(tmp_path / "store") == 0 and state.exists() and lock.exists()
    finally:
        os.close(fd)
    assert ctx_s2.gc_sessions(tmp_path / "store") == 2


def test_a_nested_repo_that_cannot_be_placed_is_not_keyed(world):
    """A stale `.git` file (its gitdir gone) marks a repo we cannot read: its
    files are not keyed as the session's, nor as `~/...`."""
    S.write_corpus(world)
    stale = world.broomva / "stale"
    stale.mkdir()
    (stale / ".git").write_text("gitdir: /nonexistent/worktrees/x\n")
    (stale / "notes.md").write_text("x")
    where = ctx_s1.ctx.resolve_scope(str(world.broomva)).where
    keys, self_obj, path_key, _ = ctx_s1.extract_keys(
        "post-read", {"tool_input": {"file_path": str(stale / "notes.md")}}, where, "broomva", "broomva")
    assert not any(keys.values()) and not self_obj and path_key is None


def test_a_lock_unlinked_under_a_waiting_hook_is_not_used(tmp_path, monkeypatch):
    """If housekeeping unlinks the lock between a hook's open and its flock, the
    hook would hold a lock nobody else can see: it abstains instead."""
    store = tmp_path / "store"
    handle, _ = ctx_s1.open_state(store, "sess-x")
    ctx_s1.release_state(handle)
    lock = store / ctx_s1.STATE_DIR / "sess-x.lock"
    real_flock = ctx_s1.fcntl.flock

    def flock_after_unlink(fd, op):
        if lock.exists():
            lock.unlink()
        return real_flock(fd, op)

    monkeypatch.setattr(ctx_s1.fcntl, "flock", flock_after_unlink)
    try:
        ctx_s1.open_state(store, "sess-x")
    except ctx_s1.Busy:
        pass
    else:
        raise AssertionError("a lock on an unlinked file was used")


def test_the_output_is_emitted_before_the_log_line(world, tmp_path, monkeypatch):
    S.write_corpus(world)
    assert S.build(world).returncode == 0
    monkeypatch.setenv("CTX_S1", "1")
    monkeypatch.setenv("CTX_S1_STAGES", "pre-edit")
    monkeypatch.setenv("CTX_S1_PARAMS", str(S.write_params(tmp_path, S.LOW_FLOORS)))
    order = []
    log = world.store("broomva") / ctx_s1.LOG_NAME
    emit = lambda out: order.append(("emit", log.exists() and len(log.read_text().splitlines())))
    out = ctx_s1.run_stage("pre-edit", json.dumps(S.edit("s-emit", world.broomva,
                                                         world.broomva / "scripts" / "gate.py")),
                           deadline=time.monotonic() + 5, emit=emit)
    assert out and order == [("emit", False)]  # emitted while the log had no line yet
    assert len(log.read_text().splitlines()) == 1


def test_a_claim_received_from_the_cache_carries_the_builds_time(tmp_path):
    items = [ctx_s2.make_item("session:abcd", "session", "Session abcd is live on feat/x.", "ctx board", NOW,
                              {"b": ["b:feat/x"]}, ["o:session:abcd"])]
    r = ctx_s2.BM25Ranker()
    r.fit(items)
    ctx_s2.write_cache(tmp_path / "store", items, r, now=NOW)
    reader = ctx_s1.CacheReader(tmp_path / "store")
    state = {"injected": {}, "counts": {}, "paths": {}}
    params = dict(ctx_s1.DEFAULT_PARAMS, stages={"session-start": {"floor": 0.0}})
    d = ctx_s1.decide("session-start", {"b": ["b:feat/x"]}, set(), state, reader, params, now=NOW + 60)
    ctx_s1.record(state, "session-start", d, None, None, NOW + 3600)
    assert state["injected"]["session:abcd"]["as_of"] == reader.built_at == NOW


def test_housekeeping_sweeps_an_old_temp_file(tmp_path):
    d = tmp_path / "store" / ctx_s1.STATE_DIR
    d.mkdir(parents=True)
    tmp = d / ".sess-z.json.123.tmp"
    tmp.write_text("{")
    week_ago = time.time() - 8 * 86400
    os.utime(str(tmp), (week_ago, week_ago))
    assert ctx_s2.gc_sessions(tmp_path / "store") == 1 and not tmp.exists()


def test_a_short_flag_is_read_per_subcommand():
    assert K.bash_actions("gh pr merge -s 253") == [("pr-merge", "253", None)]   # -s is --squash
    assert K.bash_actions("gh pr review -a 253") == [("pr-review", "253", None)]  # -a is --approve
    assert K.bash_actions("gh pr create -t 5 -b x") == [("pr-create", None, None)]  # -t takes a title
