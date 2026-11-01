"""The T3 source (BRO-3376): the read-only reader over T3's state database,
the rows observe places by scope, and the two asks report raises on them
(a scheduled thread waiting on a user-input request; a scheduled thread whose
runs fail in a row). Both polarities of each."""
from __future__ import annotations

import json
import shutil
import sqlite3

import pytest

from fleetlib import config, observe, report, sources, t3
from fleetlib.sources import FixtureSources, SourceError

NOW = 1790812547.24685  # the scenario capture's captured_at
BROOMVA_ORCH = "mcp:aaaa1111-0000-4000-8000-000000000001"
META = "mcp:bbbb2222-0000-4000-8000-000000000002"
SRI_ORCH = "mcp:cccc3333-0000-4000-8000-000000000003"
INTERACTIVE = "dddd4444-0000-4000-8000-000000000004"


# The reader, over a database with T3's pinned columns ------------------------

def _db(path, drop=None):
    c = sqlite3.connect(str(path))
    c.execute("pragma journal_mode=wal")  # T3's own mode: the reader must leave its file unwritten under WAL
    for table, cols in t3.COLUMNS.items():
        cols = [x for x in cols if (table, x) != drop]
        extra = {"scheduled_tasks": ["prompt", "webhook_secret"]}.get(table, [])
        c.execute("create table %s (%s)" % (table, ", ".join(cols + extra)))
    c.execute("insert into projection_projects values ('p1', '/w/broomva', null)")
    c.execute("insert into orchestration_v2_projection_threads values ('t-orch', 'p1', 'Orchestrator', 'codex', "
              "'2026-09-30T23:00:00.000Z', null, null, '{\"worktreePath\": \"/w/broomva/wt\", \"title\": \"x\"}')")
    c.execute("insert into orchestration_v2_projection_threads values ('t-gone', 'p1', 'Archived', 'codex', "
              "'2026-09-30T23:00:00.000Z', '2026-09-30T23:10:00.000Z', null, '{}')")
    if drop is None:  # an archived thread, still scheduled and waiting: neither listed nor counted
        c.execute("insert into scheduled_tasks (task_id, title, enabled, schedule_json, thread_id, last_run_status, "
                  "next_run_at) values ('s-gone', 'old', 1, '{}', 't-gone', 'succeeded', null)")
        c.execute("insert into orchestration_v2_projection_runtime_requests values ('gone-open', 't-gone', "
                  "'user_input', 'pending', '2026-09-30T21:00:00.000Z', null)")
    for tid, st in (("t-busy", "running"), ("t-idle", "completed")):  # unscheduled, nothing open
        c.execute("insert into orchestration_v2_projection_threads values (?, 'p1', ?, 'claudeAgent', "
                  "'2026-09-30T23:00:00.000Z', null, null, '{}')", (tid, tid))
        c.execute("insert into orchestration_v2_projection_runs values (?, 1, ?, '2026-09-30T22:00:00.000Z', null)",
                  (tid, st))
    if drop != ("scheduled_tasks", "prompt"):
        c.execute("insert into scheduled_tasks (task_id, title, enabled, schedule_json, thread_id, last_run_status, "
                  "next_run_at, prompt, webhook_secret) values ('s1', 'tick', 1, '{\"everyMs\": 7200000}', 't-orch', "
                  "'succeeded', null, 'THE PROMPT TEXT', 'THE-SECRET')")
    for rid, status, resolved in (("open", "pending", None), ("done", "resolved", "2026-09-30T23:01:00.000Z"),
                                  ("gone", "cancelled", None), ("late", "expired", None)):
        c.execute("insert into orchestration_v2_projection_runtime_requests (runtime_request_id, thread_id, kind, status, "
                  "created_at%s) values (?, 't-orch', 'user_input', ?, '2026-09-30T22:00:00.000Z'%s)"
                  % ((", resolved_at", ", ?") if drop is None else ("", "")),
                  (rid, status, resolved) if drop is None else (rid, status))
    c.execute("insert into orchestration_v2_projection_runtime_requests (runtime_request_id, thread_id, kind, status, "
              "created_at) values ('cmd', 't-orch', 'command', 'pending', '2026-09-30T22:00:00.000Z')")
    # Two failures, then more queued and active runs than the window holds: the streak must still be seen.
    for n, st in enumerate(("completed", "failed", "failed") + ("interrupted", "cancelled", "rolled_back") * 2
                           + ("queued",) * 6 + ("running",), 1):
        c.execute("insert into orchestration_v2_projection_runs values ('t-orch', ?, ?, '2026-09-30T22:00:00.000Z', "
                  "null)", (n, st))
    c.commit()
    c.close()


def test_the_reader_keeps_open_requests_and_reads_no_prompt_or_secret(tmp_path):
    db = tmp_path / "statev2.sqlite"
    _db(db)
    text = t3.read_state(str(db), NOW)
    assert "THE PROMPT TEXT" not in text and "THE-SECRET" not in text
    st = t3.parse_state(text)
    # Resolved, cancelled and expired are over; a command approval is not a user input.
    assert [r["request_id"] for r in st["requests"]] == ["open"]
    # Read: the scheduled thread and a busy one. Not read: an archived thread, an idle unscheduled one.
    assert sorted(t["thread_id"] for t in st["threads"]) == ["t-busy", "t-orch"]
    assert {t["thread_id"]: t for t in st["threads"]}["t-orch"]["worktree"] == "/w/broomva/wt"
    assert "gone-open" not in [r["request_id"] for r in st["requests"]]  # an archived thread's request is not read
    assert [s["task_id"] for s in st["schedules"]] == ["s1"]
    # The latest finished runs past six neutral, six queued and one active: none of those can fill the window.
    assert [r["status"] for r in st["runs"]["t-orch"]] == ["failed", "failed", "completed"]
    assert st["queued"] == {"t-orch": 6} and st["active"] == {"t-orch": 1, "t-busy": 1}
    assert t3.failing_streak(st["runs"]["t-orch"]) == 2


def test_a_missing_pinned_column_fails_the_surface_never_reads_as_empty(tmp_path, monkeypatch):
    db = tmp_path / "statev2.sqlite"
    _db(db, drop=("orchestration_v2_projection_runtime_requests", "resolved_at"))
    # Named as schema drift ("lacks"), not left to whichever query hits the column first.
    with pytest.raises(t3.T3Unread, match="runtime_requests lacks resolved_at"):
        t3.read_state(str(db), NOW)
    monkeypatch.setenv(t3.STATE_ENV, str(db))
    with pytest.raises(SourceError, match="lacks resolved_at"):
        sources.Sources().t3_state(NOW)
    # A path named by FLEET_T3_STATE that isn't there: a failure, never "no threads" (that resolves T3 asks),
    # even with no T3 home on the host.
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path / "no-t3-home"))
    monkeypatch.setenv(t3.STATE_ENV, str(tmp_path / "gone" / "statev2.sqlite"))
    with pytest.raises(t3.T3Unread, match="is missing"):
        t3.read_state(t3.default_path(), NOW)
    monkeypatch.delenv(t3.STATE_ENV)


def test_a_missing_database_is_t3_not_installed_only_without_a_t3_home(tmp_path, monkeypatch):
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path / "t3"))
    absent = t3.parse_state(t3.read_state(t3.default_path(), NOW))  # no T3 home: a host without T3
    assert absent["installed"] is False and absent["threads"] == [] and absent["requests"] == []
    (tmp_path / "t3").mkdir()  # T3's home there, its userdata (or just the file) not: moved or renamed
    with pytest.raises(t3.T3Unread, match="is missing"):
        t3.read_state(t3.default_path(), NOW)
    (tmp_path / "t3" / "userdata").mkdir()
    with pytest.raises(t3.T3Unread, match="is missing"):
        t3.read_state(t3.default_path(), NOW)


def test_more_threads_than_the_cap_fail_the_surface_rather_than_list_part(tmp_path, monkeypatch):
    db = tmp_path / "statev2.sqlite"
    _db(db)
    monkeypatch.setattr(t3, "MAX_THREADS", 2)  # t-orch and t-busy; the archived scheduled thread doesn't count
    assert len(t3.parse_state(t3.read_state(str(db), NOW))["threads"]) == 2
    monkeypatch.setattr(t3, "MAX_THREADS", 1)
    with pytest.raises(t3.T3Unread, match="over 1 threads"):
        t3.read_state(str(db), NOW)


def test_the_reader_opens_the_database_read_only(tmp_path):
    db = tmp_path / "statev2.sqlite"
    _db(db)
    before = db.read_bytes()
    t3.read_state(str(db), NOW)
    assert db.read_bytes() == before
    c = t3._connect(str(db))
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        c.execute("insert into projection_projects values ('p2', '/x', null)")
    c.close()


def test_the_reader_reads_one_snapshot_and_sees_wal_data_not_yet_checkpointed(tmp_path, monkeypatch):
    db = tmp_path / "statev2.sqlite"
    _db(db)
    w = sqlite3.connect(str(db))  # a writer that stays open, its WAL never checkpointed
    w.execute("pragma wal_autocheckpoint=0")
    w.execute("insert into orchestration_v2_projection_runtime_requests values ('late', 't-orch', 'user_input', "
              "'pending', '2026-09-30T22:30:00.000Z', null)")
    w.commit()
    seen = []
    real = t3._connect

    def traced(path):
        c = real(path)
        c.set_trace_callback(seen.append)
        return c

    monkeypatch.setattr(t3, "_connect", traced)
    st = t3.parse_state(t3.read_state(str(db), NOW))
    w.close()
    assert "late" in [r["request_id"] for r in st["requests"]]
    assert seen[0].strip().lower() == "begin"  # one read transaction: every query reads one snapshot


def test_a_value_json_cannot_encode_fails_the_surface(tmp_path):
    db = tmp_path / "statev2.sqlite"
    _db(db)
    c = sqlite3.connect(str(db))
    c.execute("update orchestration_v2_projection_threads set title = ? where thread_id = 't-orch'", (b"\x00\xff",))
    c.commit()
    c.close()
    with pytest.raises(t3.T3Unread):
        t3.read_state(str(db), NOW)


def test_a_failing_streak_counts_failed_runs_in_a_row_past_neutral_ones():
    runs = lambda *s: [{"status": x} for x in s]  # noqa: E731
    assert t3.failing_streak(runs("failed", "failed", "completed")) == 2
    # Interrupted, cancelled and rolled back say nothing about the loop: skipped, neither counted nor breaking.
    assert t3.failing_streak(runs("failed", "interrupted", "cancelled", "rolled_back", "failed")) == 2
    assert t3.failing_streak(runs("completed", "failed", "failed")) == 0
    assert t3.failing_streak(runs("failed", "some-new-state", "failed")) == 1  # an unknown state ends it
    assert t3.failing_streak(runs()) == 0


def test_more_open_user_inputs_than_the_cap_fail_the_surface(tmp_path, monkeypatch):
    db = tmp_path / "statev2.sqlite"
    _db(db)
    monkeypatch.setattr(t3, "MAX_REQUESTS", 1)  # one open user input: at the cap, read; the command is not counted
    assert len(t3.parse_state(t3.read_state(str(db), NOW))["requests"]) == 1
    c = sqlite3.connect(str(db))
    c.execute("insert into orchestration_v2_projection_runtime_requests (runtime_request_id, thread_id, kind, status, "
              "created_at) values ('open2', 't-orch', 'user_input', 'pending', '2026-09-30T22:05:00.000Z')")
    c.commit()
    c.close()
    with pytest.raises(t3.T3Unread, match="over 1 open user-input"):
        t3.read_state(str(db), NOW)


# Observe and report over the scenario capture ------------------------------------

#: The scenario capture's T3 threads are healthy, so the other tests' ask counts hold. These two
#: conditions are added per test: the Broomva orchestrator's run waiting 75 min on a user input with two
#: schedule fires queued behind it, and the SRI orchestrator's last two runs failed.
def _conditions(world):
    p = world.fixture / "t3" / "state.json"
    st = json.loads(p.read_text())
    st["requests"].append({"request_id": "rr-broomva-1", "thread_id": BROOMVA_ORCH, "kind": "user_input",
                           "status": "pending", "created_at": "2026-09-30T22:40:47.000Z"})
    st["active"][BROOMVA_ORCH] = 1
    st["queued"][BROOMVA_ORCH] = 2
    st["runs"][SRI_ORCH][0]["status"] = "failed"
    p.write_text(json.dumps(st))


def _rep(world, scope="broomva", healthy=False, **cfg):
    if not healthy:
        _conditions(world)
    world.write_config(**cfg)
    snap = observe.observe(config.scope(scope), FixtureSources(world.fixture), 1, now=NOW)
    return report.build(snap, [], True)


def _keys(rep):
    return {k: (cls, q) for k, cls, q in report.candidates(rep)}


def test_t3_threads_are_read_and_placed_by_scope(world):
    rep = _rep(world)
    assert rep["surfaces"]["t3"]["ok"], rep["surfaces"]["t3"]
    by = {r["thread_id"]: r for r in rep["t3_threads"]}
    assert set(by) == {BROOMVA_ORCH, META, SRI_ORCH, INTERACTIVE}  # the idle, unscheduled thread is not listed
    assert by[BROOMVA_ORCH]["scope"] == "broomva" and by[SRI_ORCH]["scope"] == "sri"
    assert by[BROOMVA_ORCH]["waiting"]["age_s"] == 75 * 60 and by[BROOMVA_ORCH]["queued"] == 2
    assert by[META]["waiting"] is None
    md = report.render_md(rep)
    assert "## T3 threads" in md and "| aaaa1111 | Broomva Orchestrator |" in md and "**75m**" in md


def test_a_removed_worktree_places_the_thread_through_its_project_root(world):
    p = world.fixture / "t3" / "state.json"
    st = json.loads(p.read_text())
    for t in st["threads"]:
        if t["thread_id"] == BROOMVA_ORCH:
            t["worktree"] = str(world.home / "wt" / "removed-after-merge")
    p.write_text(json.dumps(st))
    rep = _rep(world)
    row = {r["thread_id"]: r for r in rep["t3_threads"]}[BROOMVA_ORCH]
    assert row["scope"] == "broomva" and "project_root" not in row
    assert any(k.startswith("t3-wait:%s:" % BROOMVA_ORCH) for k in _keys(rep))


def test_only_a_t3_wait_skips_the_ledgers_raise_delay():
    assert report.pre_aged("t3-wait:t:abc") and not report.pre_aged("t3-failing:t")
    assert not report.pre_aged("prompt:s:abc") and not report.pre_aged("surface:t3")


def test_an_unreadable_request_time_fails_the_surface_rather_than_resolve_the_ask(world):
    _conditions(world)
    p = world.fixture / "t3" / "state.json"
    st = json.loads(p.read_text())
    st["requests"][-1]["created_at"] = "yesterday"
    p.write_text(json.dumps(st))
    rep = _rep(world, healthy=True)
    assert not rep["surfaces"]["t3"]["ok"] and "created_at" in rep["surfaces"]["t3"]["error"]
    assert not report.observed("t3-wait:%s:x" % BROOMVA_ORCH, rep)


def test_a_failing_ask_says_when_a_retry_is_already_queued(world):
    _conditions(world)
    p = world.fixture / "t3" / "state.json"
    st = json.loads(p.read_text())
    st["queued"][SRI_ORCH] = 1
    p.write_text(json.dumps(st))
    q = _keys(_rep(world, "sri", healthy=True))["t3-failing:%s" % SRI_ORCH][1]
    assert "A retry is running or queued" in q and "No retry" not in q


def test_a_failing_ask_with_no_retry_says_the_loop_is_stopped(world):
    assert "No retry is running or queued" in _keys(_rep(world, "sri"))["t3-failing:%s" % SRI_ORCH][1]


def test_a_scheduled_thread_waiting_past_the_threshold_is_a_blocking_ask(world):
    keys = _keys(_rep(world))
    wait = [k for k in keys if k.startswith("t3-wait:")]
    assert len(wait) == 1 and wait[0].startswith("t3-wait:%s:" % BROOMVA_ORCH)
    cls, q = keys[wait[0]]
    assert cls == "7" and "waited 75m" in q and "every 2h" in q and "2 queued" in q  # class 7 counts in Maestro's Needs you
    assert not any(INTERACTIVE in k for k in keys)  # an unscheduled thread waiting is its owner's own prompt


def test_a_wait_under_the_threshold_is_not_an_ask(world):
    assert not any(k.startswith("t3-wait:") for k in _keys(_rep(world, t3_wait_ask_min=90)))


def test_another_scopes_thread_is_listed_never_asked_about(world):
    broomva = _keys(_rep(world, "broomva"))
    assert not any(k.startswith("t3-failing:") for k in broomva)
    sri = _keys(_rep(world, "sri"))
    assert set(k for k in sri if k.startswith("t3-")) == {"t3-failing:%s" % SRI_ORCH}
    assert "last 2 finished runs failed" in sri["t3-failing:%s" % SRI_ORCH][1]


def test_an_unread_t3_surface_raises_its_own_ask_and_resolves_no_t3_key(world):
    shutil.rmtree(str(world.fixture / "t3"))
    rep = _rep(world, healthy=True)
    keys = _keys(rep)
    assert "surface:t3" in keys and not any(k.startswith("t3-wait:") for k in keys)
    assert not report.observed("t3-wait:%s:x" % BROOMVA_ORCH, rep)
    assert not report.observed("t3-failing:%s" % SRI_ORCH, rep)


def test_the_scenario_capture_alone_raises_no_t3_ask(world):
    assert not any(k.startswith("t3-") for k in _keys(_rep(world, healthy=True)))


def _unplaced(rep):
    for r in rep["t3_threads"]:
        if r["thread_id"] in (BROOMVA_ORCH, SRI_ORCH):
            r["scope"] = None  # its worktree and project root unreadable this tick: placement unknown
    return {r["thread_id"]: r for r in rep["t3_threads"]}


def test_an_unplaced_thread_whose_condition_still_holds_keeps_its_asks_open(world):
    rep = _rep(world)
    key = next(k for k in _keys(rep) if k.startswith("t3-wait:%s:" % BROOMVA_ORCH))
    failing = "t3-failing:%s" % SRI_ORCH
    _unplaced(rep)
    assert not report.observed(key, rep) and not report.observed(failing, rep)
    assert key not in report.resolved_keys([], [], rep)
    rep["t3_threads"] = [r for r in rep["t3_threads"] if r["thread_id"] != BROOMVA_ORCH]
    assert report.observed(key, rep)  # no longer listed at all: a reading, so the wait resolves


def test_an_unplaced_thread_whose_condition_ended_resolves_its_asks(world):
    # Unknown placement keeps an ask open only while the reading still shows it true; once the reading shows
    # it over, it resolves, so an acked occurrence can't suppress the next one (round-4 finding).
    rep = _rep(world)
    key = next(k for k in _keys(rep) if k.startswith("t3-wait:%s:" % BROOMVA_ORCH))
    failing = "t3-failing:%s" % SRI_ORCH
    by = _unplaced(rep)
    by[BROOMVA_ORCH]["waiting"] = None  # the request was answered
    by[SRI_ORCH]["failing_streak"] = 0  # a run completed
    assert report.observed(key, rep) and report.observed(failing, rep)
    by[BROOMVA_ORCH]["waiting"] = {"request_id": "a-later-request", "age_s": 60}  # a new wait is a new key
    assert report.observed(key, rep)
    by[SRI_ORCH]["failing_streak"], by[SRI_ORCH]["schedule"] = 2, None  # its schedule was turned off
    assert report.observed(failing, rep)


def test_a_wait_that_ended_resolves_from_a_reading(world):
    rep = _rep(world, healthy=True)
    assert not any(k.startswith("t3-wait:") for k in _keys(rep))
    assert report.observed("t3-wait:%s:x" % BROOMVA_ORCH, rep)
