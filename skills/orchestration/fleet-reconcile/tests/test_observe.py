"""The observe step end to end over the captured fixture, in a scratch HOME
whose repos match the fixture's path templates, and its fail-closed cases."""
from __future__ import annotations

import collections
import json
import shutil

import pytest
from conftest import FAKE_BEARER

from fleetlib import classify, config, observe, report
from fleetlib.sources import FixtureSources, SourceError


def _observe(world, meta, scope="broomva", src=None, **cfg):
    world.write_config(**cfg)
    sec = config.scope(scope)
    return observe.observe(sec, src or FixtureSources(world.fixture), 1, now=meta["captured_at"])


def test_every_surface_of_the_capture_is_read(world, meta):
    snap = _observe(world, meta)
    surf = snap["surfaces"]
    for name in ("claude_version", "listing", "jobs", "transcripts", "paseo_records", "ledger"):
        assert surf[name]["ok"], (name, surf[name])
    assert all(b["ok"] for b in surf["board"].values())
    assert snap["drift"] == []
    listing = json.loads((world.fixture / "claude" / "agents.json").read_text())
    assert len(snap["sessions"]) == len(listing)
    assert surf["jobs"]["files"] == sum(1 for r in listing if r["kind"] == "background")


def test_sessions_are_placed_by_the_cores_rule(world, meta):
    snap = _observe(world, meta)
    placed = collections.Counter((s["scope"], s["placement"]) for s in snap["sessions"])
    assert placed[("broomva", "cwd")] > 0 and placed[("sri", "cwd")] > 0
    home = str(world.home.resolve())
    for s in snap["sessions"]:
        if s["cwd"].startswith(home + "/gone/"):
            assert s["placement"] in ("board", "worktree-parent", "unplaced")
        if s["cwd"].startswith(home + "/client/sri") or s["cwd"].startswith(home + "/wt/sri-"):
            assert s["scope"] == "sri"


def test_the_fake_bearer_never_reaches_a_snapshot_or_report(world, meta):
    snap = _observe(world, meta)
    rep = report.build(snap, [], True)
    for blob in (json.dumps(snap), json.dumps(rep), report.render_md(rep)):
        assert FAKE_BEARER not in blob and "Authorization" not in blob and "FIXTURE_ENV" not in blob


def test_a_listing_at_the_cap_fails_closed_and_nothing_is_classified(world, meta):
    rows = json.loads((world.fixture / "claude" / "agents.json").read_text())
    big = [dict(rows[i % len(rows)], sessionId="f%07x-0000-4000-8000-%012d" % (i, i)) for i in range(200)]
    (world.fixture / "claude" / "agents.json").write_text(json.dumps(big))
    snap = _observe(world, meta)
    assert snap["surfaces"]["listing"]["ok"] is False and snap["surfaces"]["listing"]["failed_closed"]
    assert snap["sessions"] == []
    rep = report.build(snap, [], True)
    assert rep["class_counts"] == {}
    assert rep["count_check"]["ran"] is False
    assert [a["key"] for a in rep["asks"]][0] == "listing"
    assert "NO" in report.render_md(rep)
    # One row under the cap is read.
    (world.fixture / "claude" / "agents.json").write_text(json.dumps(big[:199]))
    assert _observe(world, meta)["surfaces"]["listing"]["ok"] is True


def test_the_cap_is_the_configured_one(world, meta):
    # At a cap of 10 the capture's listing is over it, so it is read only
    # because every job file appears in it; at the default 200 no check runs.
    assert _observe(world, meta, listing_cap=10)["surfaces"]["listing"]["completeness"]
    assert "completeness" not in _observe(world, meta)["surfaces"]["listing"]


def test_a_slug_that_does_not_resolve_fails_that_repo_and_does_not_read_as_zero(world, meta):
    snap = _observe(world, meta, scope="sri")
    (repo,) = snap["repos"]
    assert repo["ok"] is False and "not a GitHub slug" in repo["error"] and "prs" not in repo
    rep = report.build(snap, [], True)
    (r,) = rep["repos"]
    assert r["prs"] is None
    assert "**NO**" in report.render_md(rep)
    assert any(a["key"].startswith("repo:") for a in rep["asks"])


class _FailingGh(FixtureSources):
    def open_prs(self, slug, limit):
        if slug == "broomva/skills":
            raise SourceError("gh pr list exited 1: HTTP 404")
        return super().open_prs(slug, limit)


def test_a_gh_failure_fails_only_that_repo(world, meta):
    snap = _observe(world, meta, src=_FailingGh(world.fixture))
    by = {r["slug"]: r for r in snap["repos"]}
    assert by["broomva/workspace"]["ok"] and by["broomva/workspace"]["prs"] is not None
    assert by["broomva/skills"]["ok"] is False and "404" in by["broomva/skills"]["error"]


def test_a_pr_list_at_the_cap_fails_the_repo(world, meta):
    snap = _observe(world, meta, pr_list_cap=1)
    assert all(not r["ok"] and "cap" in r["error"] for r in snap["repos"] if r["slug"] == "broomva/workspace")


def test_the_ruleset_check_reads_the_effective_rules(world, meta):
    snap = _observe(world, meta)
    by = {r["slug"]: r for r in snap["repos"]}
    assert by["broomva/workspace"]["rules"]["driver_eligible"] is True
    assert by["broomva/skills"]["rules"]["flags"] == ["no pull_request rule"]
    rules = json.loads((world.fixture / "gh" / "broomva__skills" / "rules.json").read_text())
    rules.append({"type": "pull_request", "parameters": {"required_approving_review_count": 0}})
    (world.fixture / "gh" / "broomva__skills" / "rules.json").write_text(json.dumps(rules))
    by = {r["slug"]: r for r in _observe(world, meta)["repos"]}
    assert by["broomva/skills"]["rules"]["driver_eligible"] is True


def test_a_missing_surface_is_reported_not_read_as_empty(world, meta):
    shutil.rmtree(world.fixture / "paseo" / "agents")
    snap = _observe(world, meta)
    assert snap["surfaces"]["paseo_records"]["ok"] is False
    cc = classify.count_check(snap)
    assert cc["records_without_process"] is None and "not read" in cc["records_reason"]


def test_a_newer_claude_code_is_reported_as_drift(world, meta):
    (world.fixture / "claude" / "version.txt").write_text("2.2.0 (Claude Code)\n")
    snap = _observe(world, meta)
    assert any("2.2.0" in d for d in snap["drift"])
    assert any(a["key"].startswith("drift:") for a in report.build(snap, [], True)["asks"])


def test_fleet_keys_come_only_from_the_ledger_or_the_adopted_list(world, meta):
    rows = json.loads((world.fixture / "claude" / "agents.json").read_text())
    rows[0]["name"] = "broomva-workspace-pr842"
    (world.fixture / "claude" / "agents.json").write_text(json.dumps(rows))
    adopted = rows[1]["sessionId"]
    snap = _observe(world, meta, adopted=[{"session_id": adopted, "adopted": "2026-09-30", "note": "t"}])
    by = {s["session_id"]: s for s in snap["sessions"]}
    first = by[rows[0]["sessionId"]]
    assert first["fleet_shaped"] and first["fleet_key"] is None  # fleet-shaped, but not in the ledger
    assert by[adopted]["fleet_key"] == "adopt:" + adopted


def test_the_scheduled_inventory_lists_this_scopes_schedules_and_launchd_jobs(world, meta):
    snap = _observe(world, meta, launchd_prefix="com.broomva.")
    items = snap["scheduled"]["items"]
    by_src = collections.Counter(i["source"] for i in items)
    assert by_src["launchd"] == 2 and by_src["dream"] == 1
    sch = snap["scheduled"]["surfaces"]["paseo_schedules"]
    assert sch["ok"] and sch["listed"] + sch["other_scopes"] == 5
    sri = _observe(world, meta, scope="sri")["scheduled"]
    s2 = sri["surfaces"]["paseo_schedules"]
    # Each schedule is listed in exactly one scope: 1 broomva arc, 1 paused
    # sri arc and 3 one-shot sri pickups at capture time.
    assert (sch["listed"], s2["listed"]) == (1, 4) and s2["other_scopes"] == 1
    assert not any(i["source"] == "launchd" for i in sri["items"])  # no launchd_prefix for sri


def test_a_limit_line_is_read_from_the_transcript_tail_for_a_board_death(world, meta):
    snap = _observe(world, meta)
    died = [s for s in snap["sessions"] if (s["board"] or {}).get("died_error") == "rate_limit"
            and s["board"]["state"] == "died" and not (s["job"] or {}).get("reset_text")]
    if not died:
        pytest.skip("the capture holds no board limit death")
    sid = died[0]["session_id"]
    tails = world.fixture / "claude" / "transcript-tails"
    tails.mkdir()
    (tails / (sid + ".txt")).write_text('..."text":"You\'ve hit your session limit · resets 10:50pm '
                                        '(America/Bogota)"}]...')
    snap = _observe(world, meta)
    s = {x["session_id"]: x for x in snap["sessions"]}[sid]
    assert s["limit_text"].endswith("resets 10:50pm (America/Bogota)")
    assert classify.limit_reset(s)[1] == "stated"


# --------------------------------------------------------------------------
# Round-2 fixes (P20 round 1)

def test_a_listing_at_the_cap_is_read_when_every_job_file_is_in_it(world, meta):
    # `claude agents --all` has no limit, and lists every background job ever
    # run, so it can pass the cap legitimately: then the job files prove it whole.
    rows = json.loads((world.fixture / "claude" / "agents.json").read_text())
    extra = [dict(rows[0], kind="interactive", sessionId="e%07x-0000-4000-8000-%012d" % (i + 1, i), pid=20000 + i,
                  status="idle", name="extra-%d" % i) for i in range(210 - len(rows))]
    for r in extra:
        r.pop("id", None)
        r.pop("state", None)
    (world.fixture / "claude" / "agents.json").write_text(json.dumps(rows + extra))
    snap = _observe(world, meta)
    assert snap["surfaces"]["listing"]["ok"] and snap["surfaces"]["listing"]["completeness"]
    assert len(snap["sessions"]) == 210
    # One job file missing from the listing: it may be truncated after all.
    bg = [r for r in rows if r["kind"] == "background"][0]
    (world.fixture / "claude" / "agents.json").write_text(json.dumps([r for r in rows + extra if r is not bg]
                                                                     + [dict(extra[0], sessionId="f" * 8 + extra[0]["sessionId"][8:])]))
    assert _observe(world, meta)["surfaces"]["listing"]["failed_closed"]


def test_an_unparsed_job_file_degrades_only_its_own_session(world, meta):
    rows = json.loads((world.fixture / "claude" / "agents.json").read_text())
    bg = [r for r in rows if r["kind"] == "background" and "pid" not in r][0]
    (world.fixture / "claude" / "jobs" / bg["id"] / "state.json").write_text("{torn")
    snap = _observe(world, meta)
    assert snap["surfaces"]["jobs"]["ok"] and snap["surfaces"]["jobs"]["unparsed"] == 1
    by = {s["session_id"]: s for s in snap["sessions"]}
    assert by[bg["sessionId"]]["job_unread"] is True
    assert sum(1 for s in snap["sessions"] if s["job_unread"]) == 1
    rep = report.build(snap, [], True)
    row = [x for x in rep["sessions"] if x["session_id"] == bg["sessionId"]][0]
    assert row["class"] in ("1", "unknown")  # never a healthy 9, 9a or 10
    assert any(a["key"].startswith("surface:jobs-unparsed") for a in rep["asks"])


def test_an_existing_directory_outside_any_repo_is_placed_as_such(world, meta, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    scope, repo, branch, how = observe.place(str(plain), {"repo": "/x/.git", "branch": "b"}, None, {})
    assert (scope, how) == (None, "no-repo")


def test_the_captured_limit_deaths_classify_as_class_2_despite_their_late_transcript_writes(world, meta):
    # P20 round 2 (N1): every captured limit death's transcript mtime sits
    # about an hour past its last timestamped entry (Claude Code's
    # untimestamped last-prompt and cost-state records). Read from the last
    # entry, each is still class 2 in its own scope.
    snap = _observe(world, meta)
    limit = [s for s in snap["sessions"] if (s["job"] or {}).get("limit_text") and s["job"]["state"] == "blocked"]
    assert limit, "the capture holds usage-limit deaths"
    late = 0
    for s in limit:
        t = s["transcript"]
        assert t["last_entry"] is not None
        late += t["mtime"] - t["last_entry"] > 3000
        env = classify.Env(s["scope"] or "none", meta["captured_at"], snap["repos"], snap["surfaces"])
        got = classify.classify(s, env)
        assert got["class"] in ("2", "1"), got
        if s["scope"]:
            assert got["class"] == "2", got
    assert late, "the capture shows the late untimestamped write"
