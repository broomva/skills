"""The class table (spec §5.4): one positive case per class, the spec's
ordering tests, every pair of rules that can both match (the earlier must
win), a grid proving the remaining pairs can't both match, the overlap pass,
the count check and the spawn pause.

tests/mutation_check.py deletes each rule and swaps each overlapping pair; the
cases here are what kill those mutants.
"""
from __future__ import annotations

import itertools

import pytest
from conftest import NOW, H, env_for, make_session as S

from fleetlib import classify

OURS = {"fleet_key": "broomva-workspace-pr7"}


def died(err="rate_limit", ago=600):
    return {"state": "died", "last_event": "session.died", "last_ts": NOW - ago, "died_ts": NOW - ago,
            "died_error": err}


def arc(word, ago=600):
    return {"state": "stopped", "last_event": "session.stop", "last_ts": NOW - ago, "arc_status": word,
            "arc_ts": NOW - ago}


LIMIT_JOB = {"state": "blocked", "limit_text": True, "reset_text": "resets 10am (America/Bogota)",
             "detail": "You've hit your session limit · resets 10am (America/Bogota)", "updated_at": NOW - 600}
QUESTION_JOB = {"state": "blocked", "needs": "approve the fix approach?", "detail": "fix ready",
                "suggested_reply": True}


def bg(**kw):
    kw.setdefault("kind", "background")
    kw.setdefault("pid", None)
    kw.setdefault("status", None)
    return S(**kw)


def oos(**kw):
    kw.setdefault("scope", "sri")
    return S(**kw)


def cls(s, env=None):
    return classify.classify(s, env or env_for())


# --------------------------------------------------------------------------
# Every class, one positive case each

POSITIVE = [
    ("1", oos()),
    ("1", S(scope=None, placement="unplaced")),
    ("2", S(board=died("rate_limit"), activity_ago=900)),
    ("2", bg(state="blocked", job=LIMIT_JOB, activity_ago=900)),
    ("3", S(status="waiting", waiting_for="dialog open")),
    ("4", bg(state="failed")),
    ("4", S(board=died("server_error"), activity_ago=900)),
    ("5", S(status="busy", activity_ago=60)),
    ("5", S(status="busy", activity_ago=5 * H, sub_ago=60)),  # a subagent's transcript counts
    ("6", S(status="busy", activity_ago=3 * H)),
    ("7", S(board=arc("BLOCKED"), activity_ago=900)),
    ("7", bg(state="blocked", job=QUESTION_JOB)),
    ("8", S(board=arc("DONE"), activity_ago=900)),
    ("8", S(board=arc("MERGED"), activity_ago=900, branch="fix/y")),
    ("9", S(activity_ago=2 * H, **OURS)),
    ("9", bg(state="done", activity_ago=2 * H, **OURS)),  # no process, done: idle
    ("9a", S(activity_ago=20 * 60, **OURS)),
    ("10", S()),
    ("10", S(name="broomva-workspace-pr9", fleet_shaped=True)),
    ("unknown", S(no_transcript=True, **OURS)),
    ("unknown", S(status="busy", no_transcript=True, **OURS)),
    ("unknown", S(board=arc("DONE"), activity_ago=900, branch=None)),  # its PR can't be checked
]


@pytest.mark.parametrize("expected,s", POSITIVE, ids=["%s-%d" % (c, i) for i, (c, _) in enumerate(POSITIVE)])
def test_each_class_has_a_positive_case(expected, s):
    got = cls(s)
    assert got["class"] == expected, got
    assert got["evidence"]


def test_every_class_in_the_table_is_covered_by_a_positive_case():
    assert {c for c, _ in POSITIVE} == set(classify.ORDER)


# --------------------------------------------------------------------------
# The spec's ordering tests (§5.4)

def test_a_limit_death_lands_in_2_not_4():
    s = bg(state="failed", board=died("rate_limit"), activity_ago=900)
    assert {"2", "4"} <= set(classify.matching(s, env_for()))
    assert cls(s)["class"] == "2"


def test_a_pending_permission_while_busy_lands_in_3_not_5():
    # Busy in a turn, stopped on a permission prompt: the listing says waiting.
    s = S(status="waiting", waiting_for="permission prompt", activity_ago=5)
    assert cls(s)["class"] == "3"
    assert "5" not in classify.matching(s, env_for())


def test_a_background_session_blocked_on_a_question_to_its_user_lands_in_7_not_3():
    s = bg(state="blocked", pid=777, status="waiting", waiting_for="input needed", job=QUESTION_JOB)
    assert cls(s)["class"] == "7"
    assert classify._waiting(s, env_for()) is None
    # ...while a background session stopped on a permission prompt stays in 3.
    s2 = bg(state="blocked", pid=778, status="waiting", waiting_for="permission prompt", job=QUESTION_JOB)
    assert cls(s2)["class"] == "3"


def test_a_label_write_changes_neither_5_nor_6():
    # A label write moves Paseo's updatedAt and lastActivityAt (spike P8);
    # activity is the transcript's modification time only.
    touched = {"agent_id": "a1", "archived": False, "labels": {"fleet": ""}, "last_status": "running",
               "updated_at": NOW - 1, "last_activity_at": NOW - 1, "workspace_id": "w", "session_id_from": "x"}
    stale = dict(touched, updated_at=NOW - 30 * H, last_activity_at=NOW - 30 * H)
    for paseo in (touched, stale):
        assert cls(S(status="busy", activity_ago=60, paseo=paseo))["class"] == "5"
        assert cls(S(status="busy", activity_ago=3 * H, paseo=paseo))["class"] == "6"


def test_two_running_sessions_with_overlapping_claims_stay_in_5_and_both_are_reported():
    a = S(session_id="aaaaaaaa-0000-4000-8000-000000000001", status="busy", activity_ago=60, **OURS)
    b = S(session_id="bbbbbbbb-0000-4000-8000-000000000002", status="busy", activity_ago=90)
    assert cls(a)["class"] == "5" and cls(b)["class"] == "5"
    claims = {a["session_id"]: [{"repo": "/w/broomva/.git", "path": "scripts/gate.py"},
                                {"repo": "/w/broomva/.git", "path": "README.md"}],
              b["session_id"]: [{"repo": "/w/broomva/.git", "path": "scripts/gate.py"}]}
    out = classify.overlap_pass([a, b], claims, "broomva")["overlaps"]
    assert out == [{"sessions": [a["session_id"], b["session_id"]], "paths": ["scripts/gate.py"],
                    "repo": "/w/broomva/.git", "would_mail": [a["session_id"]]}]
    assert cls(a)["class"] == "5" and cls(b)["class"] == "5"  # the pass changes no class


# --------------------------------------------------------------------------
# Every pair of rules that can both match: the earlier one wins. Each case is
# built so both rules match (asserted), which is what makes a swap of the two
# rules in RULES fail this test.

def _pair_cases():
    busy_old = dict(status="busy", activity_ago=3 * H + 10)
    return [
        ("1", "2", oos(board=died("rate_limit"), activity_ago=900)),
        ("1", "3", oos(status="waiting", waiting_for="dialog open")),
        ("1", "4", oos(kind="background", state="failed")),
        ("1", "5", oos(status="busy", activity_ago=60)),
        ("1", "6", oos(status="busy", activity_ago=3 * H)),
        ("1", "7", oos(board=arc("BLOCKED"), activity_ago=900)),
        ("1", "8", oos(board=arc("DONE"), activity_ago=900)),
        ("1", "9", oos(activity_ago=2 * H, **OURS)),
        ("1", "9a", oos(activity_ago=600, **OURS)),
        ("1", "10", oos()),
        ("2", "3", S(board=died("rate_limit"), activity_ago=900, status="waiting", waiting_for="dialog open")),
        ("2", "4", bg(state="failed", board=died("rate_limit"), activity_ago=900)),
        ("2", "5", S(board=died("rate_limit", ago=60), status="busy", activity_ago=30)),
        ("2", "6", S(board=died("rate_limit", ago=3 * H), **busy_old)),
        ("2", "7", bg(state="blocked", job=LIMIT_JOB, board=arc("BLOCKED", ago=700), activity_ago=800)),
        ("2", "8", bg(state="blocked", job=LIMIT_JOB, board=arc("DONE", ago=700), activity_ago=800)),
        ("2", "9", S(board=died("rate_limit", ago=2 * H), activity_ago=2 * H + 60, **OURS)),
        ("2", "9a", S(board=died("rate_limit", ago=600), activity_ago=700, **OURS)),
        ("2", "10", S(board=died("rate_limit"), activity_ago=900)),
        ("3", "4", bg(state="failed", pid=11, status="waiting", waiting_for="permission prompt")),
        ("3", "7", S(status="waiting", waiting_for="dialog open", board=arc("BLOCKED"), activity_ago=900)),
        ("3", "8", S(status="waiting", waiting_for="dialog open", board=arc("DONE"), activity_ago=900)),
        ("3", "10", S(status="waiting", waiting_for="dialog open")),
        ("4", "5", S(board=died("server_error", ago=60), status="busy", activity_ago=30)),
        ("4", "6", S(board=died("server_error", ago=3 * H), **busy_old)),
        ("4", "7", bg(state="failed", pid=12, status="idle", board=arc("BLOCKED"), activity_ago=900)),
        ("4", "8", bg(state="failed", pid=13, status="idle", board=arc("DONE"), activity_ago=900)),
        ("4", "9", S(board=died("server_error", ago=2 * H), activity_ago=2 * H + 60, **OURS)),
        ("4", "9a", S(board=died("server_error", ago=600), activity_ago=700, **OURS)),
        ("4", "10", bg(state="failed")),
        ("5", "7", S(status="busy", board=arc("BLOCKED", ago=600), activity_ago=660)),
        ("5", "8", S(status="busy", board=arc("DONE", ago=600), activity_ago=660)),
        ("5", "10", S(status="busy", activity_ago=60)),
        ("6", "7", S(board=arc("BLOCKED", ago=3 * H), **busy_old)),
        ("6", "8", S(board=arc("DONE", ago=3 * H), **busy_old)),
        ("6", "10", S(**busy_old)),
        ("7", "8", bg(state="blocked", job=QUESTION_JOB, board=arc("DONE", ago=700), activity_ago=800)),
        ("7", "9", S(board=arc("BLOCKED", ago=2 * H), activity_ago=2 * H + 60, **OURS)),
        ("7", "9a", S(board=arc("BLOCKED", ago=600), activity_ago=700, **OURS)),
        ("7", "10", S(board=arc("BLOCKED"), activity_ago=900)),
        ("8", "10", S(board=arc("DONE"), activity_ago=900)),
    ]


PAIRS = _pair_cases()


@pytest.mark.parametrize("first,second,s", PAIRS, ids=["%s-over-%s" % (a, b) for a, b, _ in PAIRS])
def test_the_earlier_of_two_matching_rules_wins(first, second, s):
    m = classify.matching(s, env_for())
    assert first in m and second in m, m
    assert cls(s)["class"] == first


#: Pairs that no session can match together, by construction. The grid below
#: checks the claim; the mutation check skips swapping them (an equivalent
#: mutant), and every other pair is in PAIRS.
EXCLUSIVE = {("3", "5"), ("3", "6"), ("3", "9"), ("3", "9a"), ("5", "6"), ("5", "9"), ("5", "9a"), ("6", "9"),
             ("6", "9a"), ("8", "9"), ("8", "9a"), ("9", "9a"), ("9", "10"), ("9a", "10")}


def test_pairs_and_exclusive_pairs_cover_every_pair_of_rules():
    ids = [r.id for r in classify.RULES]
    every = {(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]}
    assert {(a, b) for a, b, _ in PAIRS} | EXCLUSIVE == every
    assert not ({(a, b) for a, b, _ in PAIRS} & EXCLUSIVE)


def test_no_session_on_the_grid_matches_an_exclusive_pair():
    boards = [None, died("rate_limit", 800), died("server_error", 800), arc("BLOCKED", 800), arc("DONE", 800),
              dict(arc("DONE", 800), last_ts=NOW - 100)]
    jobs = [None, LIMIT_JOB, QUESTION_JOB, {"state": "done"}]
    env = env_for()
    seen = 0
    for kind, pid, status, state, wf, act, ours, board, job in itertools.product(
            ("interactive", "background"), (4242, None), (None, "idle", "busy", "waiting"),
            (None, "done", "stopped", "blocked", "failed"), (None, "permission prompt", "input needed"),
            (None, 30, 700, 3000, 5000, 8000), (True, False), boards, jobs):
        kw = dict(kind=kind, pid=pid, status=status, state=state, waiting_for=wf, board=board or {})
        if board is None:
            kw.pop("board")
        if job is not None:
            kw["job"] = job
        if act is None:
            kw["no_transcript"] = True
        else:
            kw["activity_ago"] = act
        if ours:
            kw.update(OURS)
        s = S(**kw)
        m = set(classify.matching(s, env))
        for a, b in EXCLUSIVE:
            assert not (a in m and b in m), (a, b, kw)
        seen += 1
    assert seen > 10000


# --------------------------------------------------------------------------
# The rules' own edges

def test_a_death_the_session_went_on_from_is_not_a_death():
    # Died at the limit, then kept working in the same process: the
    # died-then-continued case the core measured on 2026-09-30.
    s = S(status="busy", board=died("rate_limit", ago=3 * H), activity_ago=60)
    assert cls(s)["class"] == "5"


def test_an_arc_status_counts_only_while_it_is_the_latest_word():
    later_event = S(board=dict(arc("DONE", 900), last_ts=NOW - 100), activity_ago=950)
    worked_on = S(board=arc("DONE", 900), activity_ago=60)
    for s in (later_event, worked_on):
        assert classify.current_arc(s) is None
        assert cls(s)["class"] == "10"


def test_a_terminal_status_with_an_open_pr_on_its_branch_is_not_closed():
    from fleetlib import observe

    repos = [{"repo": "/w/broomva/.git", "ok": True,
              "prs": [{"number": 7, "head": "feat/x", "head_id": observe.branch_id("feat/x")}]}]
    s = S(board=arc("DONE"), activity_ago=900)
    assert cls(s, env_for(repos))["class"] == "10"
    assert cls(S(board=arc("DONE"), activity_ago=900, **OURS), env_for(repos))["class"] == "unknown"


def test_a_terminal_status_on_a_repo_whose_prs_were_not_read_is_unknown():
    repos = [{"repo": "/w/broomva/.git", "ok": False}]
    got = cls(S(board=arc("MERGED"), activity_ago=900), env_for(repos))
    assert got["class"] == "unknown" and "could not be read" in got["evidence"]


def test_class_actions_differ_for_fleet_and_unmanaged_sessions():
    assert cls(S(board=died("rate_limit"), activity_ago=900, **OURS))["action"].startswith("resume after")
    assert cls(S(board=died("rate_limit"), activity_ago=900))["action"].startswith("report")
    assert cls(S(status="busy", activity_ago=3 * H, **OURS))["action"] == "report; one mail"
    assert cls(S(status="busy", activity_ago=3 * H))["action"] == "report"


def test_the_limit_reset_is_stated_from_the_job_or_transcript_else_assumed():
    s = bg(state="blocked", job=LIMIT_JOB, activity_ago=900)
    t, how = classify.limit_reset(s)
    assert how == "stated" and t > NOW - 600
    s2 = S(board=died("rate_limit", ago=600), activity_ago=900,
           limit_text="hit your session limit · resets 10:50pm (America/Bogota)")
    assert classify.limit_reset(s2)[1] == "stated"
    s3 = S(board=died("rate_limit", ago=600), activity_ago=900)
    t3, how3 = classify.limit_reset(s3)
    assert how3 == "assumed" and t3 == pytest.approx(NOW - 600 + classify.ASSUMED_RESET_S)
    assert "reset stated" in cls(s)["evidence"] and "reset assumed" in cls(s3)["evidence"]


# --------------------------------------------------------------------------
# Snapshot-level: the spawn pause, the count check, the overlap pass

def _snap(sessions, **kw):
    snap = {"scope": "broomva", "now": NOW, "sessions": sessions, "repos": [{"repo": "/w/broomva/.git", "ok": True,
                                                                              "prs": []}],
            "surfaces": {"listing": {"ok": True}, "paseo_records": {"ok": True}}, "paseo_open": [],
            "claims": {"published": False, "by_session": {}}}
    snap.update(kw)
    return snap


def test_the_spawn_pause_applies_whoever_hit_the_limit():
    mine = S(session_id="a" * 8 + "-0000-4000-8000-000000000001", board=died("rate_limit", 600), activity_ago=900)
    snap = _snap([mine])
    pause = classify.spawn_pause(snap, classify.classify_all(snap))
    assert pause["sessions"] == [mine["session_id"]] and pause["active"] and pause["how"] == "assumed"
    assert classify.spawn_pause(_snap([S()]), classify.classify_all(_snap([S()]))) is None


def test_the_count_check_reports_records_with_no_process_and_unmanaged_sessions():
    live = S(session_id="c" * 8 + "-0000-4000-8000-000000000001")
    managed = S(session_id="d" * 8 + "-0000-4000-8000-000000000002",
                paseo={"agent_id": "x", "archived": False, "labels": {}, "last_status": "idle",
                       "updated_at": None, "last_activity_at": None, "workspace_id": "w", "session_id_from": "r"})
    recs = [{"agent_id": "p1", "session_id": managed["session_id"], "title": "t", "last_status": "idle",
             "scope": "broomva", "placement": "cwd"},
            {"agent_id": "p2", "session_id": "e" * 8 + "-0000-4000-8000-000000000003", "title": "gone",
             "last_status": "idle", "scope": "broomva", "placement": "cwd"},
            {"agent_id": "p3", "session_id": None, "title": "no id", "last_status": "idle", "scope": "broomva",
             "placement": "cwd"},
            {"agent_id": "p4", "session_id": "f" * 8 + "-0000-4000-8000-000000000004", "title": "sri",
             "last_status": "idle", "scope": "sri", "placement": "cwd"}]
    out = classify.count_check(_snap([live, managed], paseo_open=recs))
    assert [r["agent_id"] for r in out["records_without_process"]] == ["p2", "p3"]
    assert [u["session_id"] for u in out["unmanaged"]] == [live["session_id"]]


def test_the_count_check_does_not_run_on_a_listing_that_was_not_read():
    out = classify.count_check(_snap([], surfaces={"listing": {"ok": False, "error": "x"}}))
    assert out["ran"] is False


def test_the_overlap_pass_ignores_unknown_claims_dead_sessions_and_other_scopes():
    a = S(session_id="a" * 8 + "-0000-4000-8000-000000000001", status="busy", activity_ago=60, **OURS)
    dead = S(session_id="b" * 8 + "-0000-4000-8000-000000000002", pid=None)
    other = oos(session_id="c" * 8 + "-0000-4000-8000-000000000003")
    unk = S(session_id="d" * 8 + "-0000-4000-8000-000000000004")
    path = {"repo": "/w/broomva/.git", "path": "x.py"}
    claims = {a["session_id"]: [path], dead["session_id"]: [path], other["session_id"]: [path],
              unk["session_id"]: [{"repo": "/w/broomva/.git", "unknown": True}]}
    assert classify.overlap_pass([a, dead, other, unk], claims, "broomva")["overlaps"] == []


# --------------------------------------------------------------------------
# Round-2 fixes (P20 round 1)

def test_a_terminal_status_with_an_unknown_or_detached_branch_is_unknown():
    for branch in (None, "", "detached@abc123def456"):
        got = cls(S(board=arc("DONE"), activity_ago=900, branch=branch))
        assert got["class"] == "unknown" and "branch is unknown" in got["evidence"]


def test_an_unread_board_or_job_file_turns_an_absence_class_into_unknown():
    surfaces_board = {"board": {"broomva": {"ok": False, "error": "x"}}, "jobs": {"ok": True}}
    env_b = classify.Env("broomva", NOW, [{"repo": "/w/broomva/.git", "ok": True, "prs": []}], surfaces_board)
    got = classify.classify(S(), env_b)  # would be 10
    assert got["class"] == "unknown" and "the board was not read" in got["evidence"]
    assert classify.classify(S(status="busy", activity_ago=60), env_b)["class"] == "5"  # positive evidence stands
    assert classify.classify(oos(), env_b)["class"] == "1"
    env_j = classify.Env("broomva", NOW, [{"repo": "/w/broomva/.git", "ok": True, "prs": []}],
                         {"board": {"broomva": {"ok": True}}, "jobs": {"ok": False, "error": "x"}})
    assert classify.classify(bg(state="done"), env_j)["class"] == "unknown"
    assert classify.classify(S(), env_j)["class"] == "10"  # an interactive session has no job file
    unread = bg(state="done")
    unread["job_unread"] = True
    assert cls(unread)["class"] == "unknown" and "its job file" in cls(unread)["evidence"]


def test_class_9_resumes_a_session_with_no_process_and_mails_a_live_one():
    assert cls(bg(state="done", activity_ago=2 * H, **OURS))["action"].startswith("resume once")
    assert cls(S(activity_ago=2 * H, **OURS))["action"].startswith("one mail")


def test_a_blocked_job_whose_detail_asks_its_user_is_class_7():
    from fleetlib import observe

    # Read from the whole detail, before the report clips it to 100 characters.
    long_q = "x" * 150 + " which fix should I take?"
    for detail in ("awaiting user confirmation; probe sequence flagged", "which fix should I take?", long_q):
        job = {"state": "blocked", "detail": detail[:100], "detail_asks": observe._detail_asks(detail)}
        assert cls(bg(state="blocked", job=job))["class"] == "7"
    job = {"state": "blocked", "detail": "fix ready", "detail_asks": observe._detail_asks("fix ready")}
    assert cls(bg(state="blocked", job=job))["class"] == "10"


def test_a_late_untimestamped_write_does_not_revive_a_dead_session():
    # 2.1.280 appends last-prompt and cost-state records ~1 h after a turn:
    # the mtime moves, the last timestamped entry doesn't (P20 round 2, N1).
    late = dict(activity_ago=600, last_entry_ago=4200)
    assert cls(bg(state="blocked", job=dict(LIMIT_JOB, updated_at=NOW - 4200), **late))["class"] == "2"
    assert cls(S(board=died("rate_limit", ago=4200), **late))["class"] == "2"
    assert cls(S(board=arc("DONE", ago=4200), **late))["class"] == "8"
    # Unknown last entry: nothing says it went on.
    assert cls(S(board=died("rate_limit", ago=4200), activity_ago=60, last_entry_ago=None))["class"] == "2"
    # A real later entry does.
    assert cls(S(status="busy", board=died("rate_limit", ago=4200), activity_ago=60))["class"] == "5"


def test_a_withheld_branch_still_matches_its_open_pr():
    from fleetlib import observe

    branch = "fix/sk-learn-bump"  # the guard withholds "sk-" at a token start
    s = S(board=arc("DONE"), activity_ago=900, branch=branch)
    s["branch"] = "[withheld]"  # the display form; branch_id was taken from the raw name
    repos = [{"repo": "/w/broomva/.git", "ok": True,
              "prs": [{"number": 12, "head": "[withheld]", "head_id": observe.branch_id(branch)}]}]
    assert cls(s, env_for(repos))["class"] == "10"  # an open PR: not closed


def test_only_5xx_and_network_errors_are_transient():
    assert "transient" in cls(S(board=died("server_error"), activity_ago=900))["evidence"]
    for err in ("max_output_tokens", "timeout", "authentication_failed"):
        assert "transient" not in cls(S(board=died(err), activity_ago=900))["evidence"]


def test_the_spawn_pause_counts_a_limit_death_in_another_scope():
    other = oos(session_id="b" * 8 + "-0000-4000-8000-000000000002", board=died("rate_limit", 60),
                activity_ago=900)
    snap = _snap([S(), other])
    pause = classify.spawn_pause(snap, classify.classify_all(snap))
    assert pause["sessions"] == [other["session_id"]] and pause["other_scopes"] == 1 and pause["active"]


def test_a_session_in_an_existing_directory_outside_any_repo_is_out_of_scope_as_such():
    got = cls(S(scope=None, placement="no-repo"))
    assert got["class"] == "1" and got["evidence"] == "cwd is not in a git repo"
