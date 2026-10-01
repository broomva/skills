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


def _batch_records(asks, tick=1, ts=None):
    return [{"v": 1, "ts": ts or common.ts(NOW - 2 * H), "scope": "broomva", "tick": tick, "dry_run": True,
             "by": "tick", "kind": "intent", "verb": "ask", "id": "%d-1" % tick, "key": "scope:broomva",
             "target": {"batch": "/x", "asks": asks}}]


def _ack(tick, asks="all", ago=H):
    return {"v": 1, "ts": common.ts(NOW - ago), "scope": "broomva", "tick": None, "dry_run": False,
            "by": "owner:t", "id": "owner-%d" % tick, "kind": "ack", "of": "%d-1" % tick, "asks": asks}


def test_an_open_ask_is_asked_once_and_then_carried_as_still_open():
    s = S(session_id=_sid(1), status="waiting", waiting_for="dialog open")
    first = report.build(_snap([s]), [], True)
    (key,) = [a["key"] for a in first["asks"]]
    assert key.startswith("prompt:" + _sid(1) + ":") and first["asks_open"] == []
    again = report.build(_snap([s]), _batch_records(first["asks"]), True)
    assert again["asks"] == [] and [a["key"] for a in again["asks_open"]] == [key]
    assert again["asks_open"][0]["first_tick"] == 1


def test_an_ack_holds_while_the_condition_lasts_and_a_recurrence_is_a_new_ask():
    s = S(session_id=_sid(1), status="waiting", waiting_for="dialog open")
    asks = report.build(_snap([s]), [], True)["asks"]
    records = _batch_records(asks) + [_ack(1, ago=30 * H)]
    rep = report.build(_snap([s]), records, True)  # still true 30 h after the ack: not asked again
    assert rep["asks"] == [] and rep["asks_open"] == [] and len(rep["acked_still_open"]) == 1
    # The prompt is answered: the next tick sees it gone and closes the key...
    gone = report.build(_snap([S(session_id=_sid(1))]), records, True)
    assert gone["resolved"] == [asks[0]["key"]]
    records += [{"v": 1, "ts": common.ts(NOW), "scope": "broomva", "tick": 2, "dry_run": False, "by": "tick",
                 "id": "2-1", "kind": "ack", "keys": gone["resolved"], "resolved": True}]
    # ...so the same prompt coming back is a new ask, notified at once.
    again = report.build(_snap([s]), records, True)
    assert [a["key"] for a in again["asks"]] == [asks[0]["key"]]


def test_a_second_different_question_from_one_session_is_a_new_ask():
    q1 = bg(session_id=_sid(1), state="blocked", job=dict(QUESTION_JOB, needs="approve plan A?"))
    q2 = bg(session_id=_sid(1), state="blocked", job=dict(QUESTION_JOB, needs="approve plan B?"))
    first = report.build(_snap([q1]), [], True)["asks"]
    records = _batch_records(first) + [_ack(1)]
    second = report.build(_snap([q2]), records, True)
    assert len(second["asks"]) == 1 and second["asks"][0]["key"] != first[0]["key"]


def test_an_ack_answers_its_own_batch_whole_or_per_ask():
    recs = []
    for t in (1, 2, 3):
        recs += _batch_records([{"id": "a1", "key": "k%d" % t, "class": "3", "question": "q"},
                                {"id": "a2", "key": "j%d" % t, "class": "3", "question": "q"}], tick=t)
    assert len(ledger.open_by_key(recs)) == 6
    assert set(ledger.open_by_key(recs + [_ack(2)])) == {"k1", "j1", "k3", "j3"}
    assert set(ledger.open_by_key(recs + [_ack(3, ["a1"])])) == {"k1", "j1", "k2", "j2", "j3"}


def test_a_waits_key_holds_while_its_subagents_keep_writing():
    first = report.build(_snap([S(session_id=_sid(1), status="waiting", waiting_for="dialog open",
                                  activity_ago=2 * H)]), [], True)["asks"]
    later = report.build(_snap([S(session_id=_sid(1), status="waiting", waiting_for="dialog open",
                                  activity_ago=2 * H, sub_ago=60)]), _batch_records(first), True)
    assert later["asks"] == [] and later["resolved"] == [] and len(later["asks_open"]) == 1


def _resolves(asked, now_snap):
    """Is the one key `asked` raised resolved by a tick that reads `now_snap`?"""
    asks = report.build(asked, [], True)["asks"]
    assert len(asks) == 1, asks
    return asks[0]["key"] in report.build(now_snap, _batch_records(asks), True)["resolved"]


def _surf(snap, **surfaces):
    snap["surfaces"].update(surfaces)
    return snap


def test_an_ask_is_resolved_only_from_the_surfaces_that_raise_it():
    blocked = lambda **kw: bg(session_id=_sid(1), state="blocked", job=dict(QUESTION_JOB), **kw)  # noqa: E731
    done = lambda: bg(session_id=_sid(1), state="done", job=dict(QUESTION_JOB, state="done", needs=""))  # noqa: E731
    ok = {"jobs": {"ok": True}, "claude_version": {"ok": True}}
    # A job question: not while the job files, or its own job file, or this scope's board, weren't read.
    assert not _resolves(_surf(_snap([blocked()]), **ok), _surf(_snap([done()]), jobs={"ok": False, "error": "x"}))
    unread = bg(session_id=_sid(1), state="blocked")
    unread["job_unread"] = True  # its own file was mid-write: the session reads as unknown
    assert not _resolves(_surf(_snap([blocked()]), **ok), _surf(_snap([unread]), **ok))
    assert not _resolves(_surf(_snap([blocked()]), **ok),
                         _surf(_snap([done()]), board={"broomva": {"ok": False, "error": "EIO"}}, **ok))
    # Another scope's board doesn't matter; read and gone, it resolves.
    assert _resolves(_surf(_snap([blocked()]), **ok),
                     _surf(_snap([done()]), board={"broomva": {"ok": True}, "sri": {"ok": False}}, **ok))
    # Drift is found in the version, the job files and the listing: all three must be read.
    drifted = _surf(_snap([], drift=["job file: state 'paused'"]), **ok)
    assert not _resolves(drifted, _surf(_snap([]), jobs={"ok": False, "error": "x"}, claude_version={"ok": True}))
    assert not _resolves(drifted, _surf(_snap([]), jobs={"ok": True}, claude_version={"ok": False}))
    assert _resolves(drifted, _surf(_snap([]), **ok))
    # Unparsed job files: only a reading of the job files says they parse now.
    unparsed = _surf(_snap([]), jobs={"ok": True, "unparsed": 2}, claude_version={"ok": True})
    assert not _resolves(unparsed, _surf(_snap([]), jobs={"ok": False, "error": "x"}, claude_version={"ok": True}))
    # A repo's rules: not while the repo wasn't observed; resolved once it leaves the scope.
    flagged = _snap([], repos=[{"repo": "/w/b/.git", "slug": "o/b", "ok": True, "default_branch": "main",
                                "rules": {"types": [], "pull_request": False, "approvals": 0, "checks": [],
                                          "unpinned": [], "driver_eligible": False, "flags": ["no pull_request rule"]},
                                "prs": []}])
    assert not _resolves(flagged, _snap([], repos=[{"repo": "/w/b/.git", "slug": "o/b", "ok": False, "error": "gh"}]))
    assert not _resolves(flagged, _snap([], repos=[{"repo": "/w/b/.git", "slug": None, "ok": False,
                                                    "error": "origin remote: timed out"}]))
    assert _resolves(flagged, _snap([], repos=[]))


def test_the_gates_hold_for_a_session_that_still_classifies():
    # An interactive session blocked by its ARC-STATUS: the scope's board must be read, the job files needn't be.
    asked = _snap([S(session_id=_sid(1), board=arc("BLOCKED"), activity_ago=900)])
    # Busy now (class 5, which needs no board), so it isn't unknown when the board isn't read.
    moved_on = lambda **surf: _surf(_snap([S(session_id=_sid(1), status="busy", activity_ago=60)]), **surf)  # noqa: E731
    blind = moved_on(board={"broomva": {"ok": False, "error": "EIO"}})
    assert [s["class"] for s in report.build(blind, [], True)["sessions"]] == ["5"]
    assert not _resolves(asked, blind)
    assert _resolves(asked, moved_on(jobs={"ok": False, "error": "x"}))
    # A prompt needs the listing; records with no process need the Paseo records too.
    waiting = _snap([S(session_id=_sid(1), status="waiting", waiting_for="dialog open")])
    assert not _resolves(waiting, _surf(_snap([]), listing={"ok": False, "error": "timed out"}))
    assert _resolves(waiting, _snap([S(session_id=_sid(1))]))
    rec = {"agent_id": "p1", "session_id": None, "title": "t", "last_status": "idle", "scope": "broomva",
           "placement": "cwd"}
    orphan = _snap([S(session_id=_sid(9))], paseo_open=[rec])
    assert not _resolves(orphan, _surf(_snap([S(session_id=_sid(9))]), paseo_records={"ok": False, "error": "x"}))
    assert _resolves(orphan, _snap([S(session_id=_sid(9))]))


def test_an_open_ask_whose_surface_was_not_read_is_still_listed_and_counted():
    waiting = _snap([S(session_id=_sid(1), status="waiting", waiting_for="dialog open")])
    asks = report.build(waiting, [], True)["asks"]
    blind = _surf(_snap([]), listing={"ok": False, "error": "timed out"})
    rep = report.build(blind, _batch_records(asks), True)
    assert [a["key"] for a in rep["asks_unchecked"]] == [asks[0]["key"]]
    md = report.render_md(rep)
    assert "**Open asks: 2**" in md and "not re-checked this tick" in md  # the listing ask, and this one


def test_a_comparison_failing_three_runs_in_a_row_is_an_ask_and_its_error_is_guarded():
    def rep(n):
        return report.build(_snap([]), [], True, {"ts": "t", "pass": False, "error": "ghp_" + "c" * 36,
                                                  "failed_in_a_row": n})
    assert "compare:failing" not in [a["key"] for a in rep(2)["asks"]]
    r = rep(3)
    assert "compare:failing" in [a["key"] for a in r["asks"]]
    assert "ghp_" not in report.render_md(r) + json.dumps(r["asks"])
    refused = report.build(_snap([]), [], True, {"refused": "unregistered"})
    assert [a["key"] for a in refused["asks"]] == ["compare:not-run"] and "Not run" in report.render_md(refused)


def test_the_ack_text_says_what_an_ack_answers():
    rep = report.build(_snap([S(session_id=_sid(1), status="waiting", waiting_for="dialog open")]), [], True)
    text = report.render_md(rep) + report.render_batch(rep)
    assert "every earlier" not in text and "`fleet ack --all`" in text
    assert rep["batches"]["unanswered"] == 1 and rep["batches"]["unseen"] == 1  # this tick's own batch


def test_a_count_ask_keeps_its_key_when_its_members_change():
    # Churn in the set (a session ends, another starts) must not mint a new
    # ask every tick; the question carries the current count.
    def rep_with(ids):
        snap = _snap([S(session_id=_sid(9))], paseo_open=[
            {"agent_id": i, "session_id": None, "title": "t", "last_status": "idle", "scope": "broomva",
             "placement": "cwd"} for i in ids])
        return report.build(snap, [], True)
    a1 = [a for a in rep_with(["p1", "p2"])["asks"] if a["key"].startswith("records-")]
    a2 = [a for a in rep_with(["p1", "p3", "p4"])["asks"] if a["key"].startswith("records-")]
    assert a1[0]["key"] == a2[0]["key"] == "records-without-process"
    assert a1[0]["question"].startswith("2 ") and a2[0]["question"].startswith("3 ")


def test_a_surface_that_was_not_read_is_asked_about():
    surf = {"listing": {"ok": True}, "paseo_records": {"ok": True}, "jobs": {"ok": True, "unparsed": 2},
            "transcripts": {"ok": False, "error": "unreadable"},
            "board": {"broomva": {"ok": False, "error": "EIO"}}, "ledger": {"ok": False, "corrupt": 1}}
    keys = {a["key"] for a in report.build(_snap([], surfaces=surf), [], True)["asks"]}
    assert {"surface:transcripts", "surface:board:broomva", "surface:jobs-unparsed",
            "surface:ledger-corrupt"} <= keys


def test_a_rules_flag_says_no_driver_only_when_the_repo_is_not_eligible():
    def rules(flags, eligible):
        return {"types": [], "pull_request": True, "approvals": 0, "checks": [], "unpinned": [],
                "driver_eligible": eligible, "flags": flags}
    repos = [{"repo": "/a", "slug": "o/a", "ok": True, "rules": rules(["no pull_request rule"], False), "prs": []},
             {"repo": "/b", "slug": "o/b", "ok": True,
              "rules": rules(["force-push to the default branch not blocked"], True), "prs": []}]
    asks = {a["key"].split(":")[1]: a["question"] for a in report.build(_snap([], repos=repos), [], True)["asks"]}
    assert "no driver" in asks["o/a"] and "no driver" not in asks["o/b"]


def test_scheduled_work_is_inventoried_in_the_report_and_raises_no_ask():
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
    assert not [a for a in rep["asks"] if a["key"].startswith("sched")]  # report-only in phase 1
    md = report.render_md(rep)
    assert "| launchd | com.x.b | com.x.b | every 900s | loaded |" in md and "exit 78" in md
    assert "| paseo | s1 | pickup | cron | active | - | - |" in md and "**yes**" in md


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


def _seen(tick, button, ago):
    return {"v": 1, "ts": common.ts(NOW - ago), "scope": "broomva", "tick": tick, "dry_run": True, "by": "tick",
            "id": "%d-9%d" % (tick, int(ago)), "kind": "seen", "of": "1-1",
            "result": {"button": button, "gave_up": button is None}}


def test_an_unseen_batch_is_shown_now_again_next_tick_then_at_most_every_6_hours():
    import fleet_reconcile as fr

    recs = _batch_records([{"id": "a1", "key": "k", "class": "3", "question": "q"}])
    due = lambda rs: [b["tick"] for b in fr.due_batches(rs, ledger.open_by_key(rs), NOW)]  # noqa: E731
    assert due(recs) == [1]                                       # never shown
    once = recs + [_seen(1, None, H)]
    assert due(once) == [1]                                       # gave up: the next tick shows it again
    twice = once + [_seen(2, "Later", 0.5 * H)]
    assert due(twice) == []                                       # then at most once per 6 h
    assert due(recs + [_seen(1, None, 8 * H), _seen(2, "Later", 7 * H)]) == [1]
    assert due(recs + [_seen(1, "Seen", 0.1 * H)]) == []          # a Seen click: not shown again
    assert due(recs + [_ack(1)]) == []                            # answered: nothing open
