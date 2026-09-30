"""The report, the ask batch and its notification rules, and the owner's
labelling sheet."""
from __future__ import annotations

import csv
import io
import json

import pytest
from conftest import NOW, H, make_session as S

from fleetlib import common, ledger, report
from test_classify import LIMIT_JOB, QUESTION_JOB, arc, bg, died, oos


def _snap(sessions, **kw):
    snap = {"v": 1, "scope": "broomva", "tick": 3, "ts": common.ts(NOW), "now": NOW,
            "pinned_cc_version": "2.1.280", "cc_version": "2.1.280", "drift": [], "sessions": sessions,
            "surfaces": {"listing": {"ok": True, "rows": len(sessions)}, "paseo_records": {"ok": True},
                         "board": {"broomva": {"ok": True, "rows": 1, "events": 1}}},
            "paseo_open": [], "claims": {"published": False, "by_session": {}},
            "repos": [{"repo": "/w/broomva/.git", "slug": "broomva/workspace", "ok": True, "default_branch": "main",
                       "rules": {"types": ["pull_request"], "pull_request": True, "approvals": 0, "checks": [],
                                 "unpinned": [], "driver_eligible": True, "flags": []}, "prs": []}],
            "scheduled": {"items": [], "surfaces": {}}}
    snap.update(kw)
    return snap


def _sid(n):
    return "%08d-0000-4000-8000-%012d" % (n, n)


def test_the_report_renders_every_section_and_serializes(tmp_path):
    sessions = [S(session_id=_sid(1), status="waiting", waiting_for="dialog open"),
                S(session_id=_sid(2), board=arc("BLOCKED"), activity_ago=900),
                oos(session_id=_sid(3)), S(session_id=_sid(4), scope=None, placement="unplaced")]
    rep = report.build(_snap(sessions), [], True)
    json.dumps(rep)
    md = report.render_md(rep)
    for heading in ("## Observation", "## Classes", "## Sessions in scope broomva", "## Count check",
                    "## Overlap pass", "## Repos, rules and PRs", "## Scheduled work", "## Asks"):
        assert heading in md
    assert "Report only (phase 1). Nothing was sent, spawned, labelled or resumed." in md
    assert [a["class"] for a in rep["asks"]] == ["3", "7"]
    assert "00000004" in md  # the unplaced session is listed, not only counted


def test_other_sessions_words_are_withheld_when_they_carry_a_crm_path_or_a_token():
    sessions = [S(session_id=_sid(1), name="notes from crm/people/someone"),
                S(session_id=_sid(2), name="use ghp_" + "b" * 36),
                bg(session_id=_sid(3), state="blocked", job=dict(QUESTION_JOB, needs="see ~/broomva/crm/x.md?"))]
    for s in sessions:
        s["name"] = common.safe_text(s["name"])
        if s["job"]:
            s["job"]["needs"] = common.safe_text(s["job"]["needs"], 100)
    rep = report.build(_snap(sessions), [], True)
    blob = json.dumps(rep) + report.render_md(rep) + report.render_batch(rep)
    assert "crm/" not in blob and "ghp_" not in blob
    assert blob.count("[withheld]") >= 3


def _batch_records(asks, tick=1, ts=None, notified=None):
    recs = [{"v": 1, "ts": ts or common.ts(NOW - 2 * H), "scope": "broomva", "tick": tick, "dry_run": True,
             "kind": "intent", "verb": "ask", "id": "%d-1" % tick, "key": "asks:%d" % tick,
             "target": {"batch": "/x", "asks": asks}}]
    if notified:
        recs.append({"v": 1, "ts": notified, "scope": "broomva", "tick": tick, "dry_run": True, "kind": "done",
                     "verb": "ask", "id": "%d-1" % tick, "result": {"notified": True}})
    return recs


def _ack(tick, asks="all", ago=H):
    return {"v": 1, "ts": common.ts(NOW - ago), "scope": "broomva", "tick": tick, "dry_run": False, "kind": "ack",
            "acks": {"tick": tick, "asks": asks}}


def test_an_open_ask_is_asked_once_and_then_carried_as_still_open():
    s = S(session_id=_sid(1), status="waiting", waiting_for="dialog open")
    first = report.build(_snap([s]), [], True)
    assert [a["key"] for a in first["asks"]] == ["prompt:" + _sid(1)] and first["asks_open"] == []
    again = report.build(_snap([s]), _batch_records(first["asks"]), True)
    assert again["asks"] == [] and [a["key"] for a in again["asks_open"]] == ["prompt:" + _sid(1)]
    assert again["asks_open"][0]["first_tick"] == 1


def test_an_acked_ask_is_not_asked_again_for_a_day():
    s = S(session_id=_sid(1), status="waiting", waiting_for="dialog open")
    asks = report.build(_snap([s]), [], True)["asks"]
    records = _batch_records(asks) + [_ack(1)]
    rep = report.build(_snap([s]), records, True)
    assert rep["asks"] == [] and rep["asks_open"] == [] and len(rep["acked_still_open"]) == 1
    records[-1]["ts"] = common.ts(NOW - 25 * H)
    assert len(report.build(_snap([s]), records, True)["asks"]) == 1


def test_acking_a_tick_acknowledges_every_earlier_batch():
    recs = []
    for t in (1, 2, 3):
        recs += _batch_records([{"id": "a1", "key": "k%d" % t, "class": "3", "question": "q"}], tick=t)
    assert set(ledger.open_by_key(recs)) == {"k1", "k2", "k3"}
    assert set(ledger.open_by_key(recs + [_ack(2)])) == {"k3"}
    assert set(ledger.open_by_key(recs + [_ack(3, ["a1"])])) == {"k1", "k2"}
    assert ledger.open_by_key(recs + [_ack(3)]) == {}


def test_notify_for_a_new_batch_else_at_most_once_per_renotify_window():
    ask = [{"id": "a1", "key": "k", "class": "3", "question": "q"}]
    assert report.should_notify(_batch_records(ask, tick=5), 5, ["k"], 6, NOW)[0] is True
    recent = _batch_records(ask, tick=5, notified=common.ts(NOW - H))
    assert report.should_notify(recent, 6, ["k"], 6, NOW) == (False, "notified 60m ago; re-notify after 6h")
    stale = _batch_records(ask, tick=5, notified=common.ts(NOW - 7 * H))
    assert report.should_notify(stale, 6, ["k"], 6, NOW)[0] is True
    assert report.should_notify(stale, 6, [], 6, NOW) == (False, "no open asks")  # no longer true: resolved
    assert report.should_notify(stale + [_ack(5)], 6, ["k"], 6, NOW) == (False, "no open asks")


def test_a_count_ask_is_new_when_its_members_change():
    def rep_with(ids):
        snap = _snap([S(session_id=_sid(9))], paseo_open=[
            {"agent_id": i, "session_id": None, "title": "t", "last_status": "idle", "scope": "broomva",
             "placement": "cwd"} for i in ids])
        return report.build(snap, [], True)
    k1 = [a["key"] for a in rep_with(["p1", "p2"])["asks"] if a["key"].startswith("records-")]
    k2 = [a["key"] for a in rep_with(["p1", "p3"])["asks"] if a["key"].startswith("records-")]
    assert k1 and k2 and k1 != k2


def test_a_surface_that_was_not_read_is_asked_about():
    surf = {"listing": {"ok": True}, "paseo_records": {"ok": True}, "jobs": {"ok": True, "unparsed": 2},
            "transcripts": {"ok": False, "error": "unreadable"},
            "board": {"broomva": {"ok": False, "error": "EIO"}}, "ledger": {"ok": False, "corrupt": 1}}
    keys = {a["key"] for a in report.build(_snap([], surfaces=surf), [], True)["asks"]}
    assert {"surface:transcripts", "surface:board:broomva", "surface:jobs-unparsed:2",
            "surface:ledger-corrupt:1"} <= keys


def test_a_rules_flag_says_no_driver_only_when_the_repo_is_not_eligible():
    def rules(flags, eligible):
        return {"types": [], "pull_request": True, "approvals": 0, "checks": [], "unpinned": [],
                "driver_eligible": eligible, "flags": flags}
    repos = [{"repo": "/a", "slug": "o/a", "ok": True, "rules": rules(["no pull_request rule"], False), "prs": []},
             {"repo": "/b", "slug": "o/b", "ok": True,
              "rules": rules(["force-push to the default branch not blocked"], True), "prs": []}]
    asks = {a["key"].split(":")[1]: a["question"] for a in report.build(_snap([], repos=repos), [], True)["asks"]}
    assert "no driver" in asks["o/a"] and "no driver" not in asks["o/b"]


def test_scheduled_asks_come_from_a_failing_exit_or_an_overdue_schedule_only():
    items = [
        {"source": "launchd", "id": "com.x.a", "name": "com.x.a", "cadence": "every 900s", "status": "loaded",
         "last_run": NOW - 30 * H, "last_result": "exit 0", "next_run": None, "stale": True, "detail": ""},
        {"source": "launchd", "id": "com.x.b", "name": "com.x.b", "cadence": "every 900s", "status": "loaded",
         "last_run": NOW - H, "last_result": "exit 78", "next_run": None, "stale": False, "detail": ""},
        {"source": "launchd", "id": "com.x.c", "name": "com.x.c", "cadence": "on demand", "status": "loaded",
         "last_run": None, "last_result": "exit (never exited)", "next_run": None, "stale": None, "detail": ""},
        {"source": "paseo", "id": "s1", "name": "pickup", "cadence": "cron", "status": "active",
         "last_run": None, "last_result": None, "next_run": NOW - 2 * H, "stale": True, "detail": ""},
    ]
    rep = report.build(_snap([], scheduled={"items": items, "surfaces": {}}), [], True)
    assert sorted(a["key"].rsplit(":", 1)[0] for a in rep["asks"]) == ["sched:launchd:com.x.b", "sched:paseo:s1"]


def _rep(tick, classes):
    return {"tick": tick, "sessions": [
        {"session_id": _sid(i), "short": _sid(i)[:8], "name": "n%d" % i, "kind": "interactive", "class": c,
         "evidence": "e", "action": "a"} for i, c in classes]}


def test_the_labelling_sheet_is_stratified_distinct_first_and_reproducible():
    reps = [_rep(1, [(1, "10"), (2, "10"), (3, "10"), (4, "10"), (5, "5"), (6, "1")]),
            _rep(2, [(1, "10"), (5, "5"), (7, "3")]),
            _rep(3, [(5, "5"), (8, "unknown")])]
    rows, available = report.labelling_sheet(reps, per_class=3, seed=7)
    per = {}
    for r in rows:
        per.setdefault(r["class"], []).append(r)
    # Distinct sessions only: class 5 has one session over three ticks, so one row.
    assert {k: len(v) for k, v in per.items()} == {"1": 1, "3": 1, "5": 1, "10": 3, "unknown": 1}
    assert len({r["session"] for r in per["10"]}) == 3
    assert available["5"] == 1 and available["10"] == 4
    assert rows == report.labelling_sheet(reps, per_class=3, seed=7)[0]
    assert [r["row"] for r in rows] == list(range(1, len(rows) + 1))
    parsed = list(csv.DictReader(io.StringIO(report.sheet_csv(rows))))
    assert parsed[0]["owner_agree_or_disagree"] == "" and list(parsed[0]) == list(report.SHEET_COLUMNS)
    md = report.sheet_md(rows, available, [1, 2, 3], "broomva")
    assert "agree / disagree" in md and "≥90%" in md
