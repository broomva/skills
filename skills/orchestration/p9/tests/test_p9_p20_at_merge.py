"""BRO-4175 — `p9 p20-at-merge`: the review rule, read after a merge.

The command reuses `p20_rule`, the function the merge gate itself calls, so a
merge the gate would have let through reads as covered here too. The case that
motivated moving it into p9: a verdict carried across a base update (workspace
PR 1497) was reported as uncovered by a second copy of the rule.
"""
from __future__ import annotations

import json

import pytest

from test_p9_merge_gates import (  # the gate tests' own fake GitHub
    BASE, HEAD, OLD, _GATED, _Run, _comment, _fake_gh, _marker, _view, gates, p9)  # noqa: F401  (fixtures)

MERGE = "d" * 40
MERGED_AT = "2026-09-26T12:00:00Z"
PR = 900


def _run(view, *, pulls=None, edited=None, extra_comments=(), parents=(BASE,),
         merge_message="squash message", pr_commits=("one",), deleted=(),
         more_deleted=False, **fake):
    """The gate tests' fake, plus the reads only p20-at-merge makes.
    `pulls` rows are (number, merge_commit_sha, merged_at); `edited` maps a
    comment's index to its updated_at; `extra_comments` are REST-only rows
    (login, association, created_at, updated_at); `parents` are the merge
    commit's; `pr_commits` the PR's commit messages; `deleted` the times of
    comment deletions."""
    inner = _fake_gh(view, calls=[], **fake)
    pulls = [(PR, MERGE, MERGED_AT)] if pulls is None else pulls
    edited = edited or {}

    def run(cmd, *a, **k):
        joined = " ".join(cmd)
        if cmd[:3] == ["gh", "api", "--paginate"] and f"/commits/{MERGE}/pulls" in joined:
            return _Run("".join(f"{n}\t{m}\t{t}\n" for n, m, t in pulls))
        if cmd[:3] == ["gh", "api", "--paginate"] and f"/pulls/{PR}/commits" in joined:
            return _Run("".join(json.dumps(m) + "\n" for m in pr_commits))
        if cmd[:3] == ["gh", "api", "--paginate"] and "/comments" in joined:
            rows = [f"{c['author']['login']}\t{c['authorAssociation']}\t{c['createdAt']}\t"
                    f"{edited.get(i, c['createdAt'])}\n"
                    for i, c in enumerate(view["comments"])]
            rows += ["\t".join(r) + "\n" for r in extra_comments]
            return _Run("".join(rows))
        if cmd[:2] == ["gh", "api"] and cmd[-1] == f"repos/broomva/test/commits/{MERGE}":
            return _Run(json.dumps({"sha": MERGE, "commit": {"message": merge_message},
                                    "parents": [{"sha": x} for x in parents]}))
        if cmd[:3] == ["gh", "api", "graphql"] and "COMMENT_DELETED_EVENT" in joined:
            # As GitHub answers: totalCount counts every timeline item, filtered or not.
            return _Run(json.dumps({"data": {"repository": {"pullRequest": {"timelineItems": {
                "totalCount": 19, "pageInfo": {"hasNextPage": more_deleted},
                "nodes": [{"createdAt": t} for t in deleted]}}}}}))
        return inner(cmd, *a, **k)
    return run


def _main(p9, capsys, *extra):
    rc = p9.main(["p20-at-merge", "--repo", "broomva/test", "--commit", MERGE, *extra])
    out = capsys.readouterr()
    return rc, out.out, out.err


def test_a_passing_verdict_at_the_head_is_covered(p9, monkeypatch, capsys):
    monkeypatch.setattr(p9.subprocess, "run", _run(_view()))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_OK
    assert out.strip() == (f"P20 at merge, pull request {PR}: a passing verdict names the final "
                           "head; a verdict was needed (more files than the threshold).")


def test_a_verdict_carried_across_a_base_update_is_covered(p9, monkeypatch, capsys):
    # The PR 1497 case: reviewed at OLD, then main was merged in (touching no PR file).
    view = _view(comments=[_comment(_marker(sha=OLD))])
    monkeypatch.setattr(p9.subprocess, "run", _run(view, compare_map={
        f"{OLD}...{HEAD}": ["docs/other.md"], f"{BASE}...{OLD}": ["src/a.py", "src/b.py"]}))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_OK and "carries to the final head" in out, out


def test_a_verdict_on_an_earlier_commit_that_later_code_changed_is_not_covered(
        p9, monkeypatch, capsys):
    view = _view(comments=[_comment(_marker(sha=OLD))])
    monkeypatch.setattr(p9.subprocess, "run", _run(view, compare_map={
        f"{OLD}...{HEAD}": ["src/a.py"], f"{BASE}...{OLD}": ["src/a.py", "src/b.py"]}))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED
    assert "does not cover the final head" in out, out


@pytest.mark.parametrize("body,state", [
    (None, "no verdict;"),
    (_marker(verdict="FAIL", score=5), "the last verdict fails or stops"),
    (_marker(verdict="STOP", score=5), "the last verdict fails or stops"),
    ("**P20-VERDICT: PASS score=8**", "the last verdict does not parse"),
])
def test_a_merge_over_the_threshold_without_a_passing_verdict_is_not_covered(
        p9, monkeypatch, capsys, body, state):
    view = _view(comments=[_comment(body)] if body else [])
    monkeypatch.setattr(p9.subprocess, "run", _run(view))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED and state in out, out


def test_a_small_change_needs_no_verdict(p9, monkeypatch, capsys):
    view = _view(files=[{"path": "src/a.py"}], changedFiles=1, comments=[])
    monkeypatch.setattr(p9.subprocess, "run", _run(view))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_OK
    assert out.strip().endswith("no verdict was needed; no verdict was needed."), out


def test_a_failing_verdict_binds_a_small_change_too(p9, monkeypatch, capsys):
    view = _view(files=[{"path": "src/a.py"}], changedFiles=1,
                 comments=[_comment(_marker(verdict="FAIL", score=4))])
    monkeypatch.setattr(p9.subprocess, "run", _run(view))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED and "fails or stops" in out, out


def test_a_verdict_written_after_the_merge_is_not_read(p9, monkeypatch, capsys):
    view = _view(comments=[_comment(_marker(), at="2026-09-26T13:00:00Z")])
    monkeypatch.setattr(p9.subprocess, "run", _run(view))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED and "no verdict;" in out, out


def test_a_verdict_edited_after_the_merge_cannot_be_told(p9, monkeypatch, capsys):
    monkeypatch.setattr(p9.subprocess, "run",
                        _run(_view(), edited={0: "2026-09-26T13:00:00Z"}))
    rc, out, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and out == ""
    assert "edited after the merge" in err, err


def test_an_edit_by_an_untrusted_account_does_not_matter(p9, monkeypatch, capsys):
    view = _view(comments=[_comment(_marker()),
                           _comment(_marker(), login="drive-by", assoc="NONE")])
    monkeypatch.setattr(p9.subprocess, "run",
                        _run(view, edited={1: "2026-09-26T13:00:00Z"}))
    rc, _, _ = _main(p9, capsys)
    assert rc == p9.EXIT_OK


def test_a_governance_change_needs_every_stratum(p9, monkeypatch, capsys):
    view = _view(files=[{"path": "CLAUDE.md"}, {"path": "src/b.py"}],
                 comments=[_comment(_marker(strata="B,C"))])
    monkeypatch.setattr(p9.subprocess, "run", _run(view))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED
    assert "lacks a stratum a governance path needs" in out and "CLAUDE.md" not in out, out


def test_no_pull_request_made_the_commit(p9, monkeypatch, capsys):
    monkeypatch.setattr(p9.subprocess, "run", _run(_view(), pulls=[]))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED
    assert out.strip() == f"P20 at merge, commit {MERGE[:12]}: no pull request merged as this commit."


def test_a_pull_request_that_only_contains_the_commit_is_not_the_one(p9, monkeypatch, capsys):
    # commits/{sha}/pulls also lists PRs whose branch holds the commit; only a
    # merge_commit_sha equal to it names the PR that merged.
    monkeypatch.setattr(p9.subprocess, "run", _run(_view(), pulls=[
        (5, "e" * 40, MERGED_AT)]))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED and "no pull request merged" in out


def test_an_unreadable_github_cannot_be_told(p9, monkeypatch, capsys):
    monkeypatch.setattr(p9.subprocess, "run",
                        lambda *a, **k: _Run(returncode=1, stderr="HTTP 502"))
    rc, out, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and out == "" and "could not tell" in err


def test_an_incomplete_file_list_cannot_be_told_and_prints_no_path(p9, monkeypatch, capsys):
    view = _view(files=[{"path": "secret-client/a.py"}, {"path": "src/b.py"}])
    inner = _run(view)

    def run(cmd, *a, **k):
        if cmd[:3] == ["gh", "api", "--paginate"] and any("/files" in c for c in cmd):
            return _Run("secret-client/a.py\t\tmodified\t5\n")  # one row of two
        return inner(cmd, *a, **k)
    monkeypatch.setattr(p9.subprocess, "run", run)
    rc, out, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and out == ""
    assert "secret-client" not in err and "P9Error" in err, err


def test_the_line_names_no_path_the_author_chose(p9, monkeypatch, capsys):
    view = _view(files=[{"path": "schemas/client-name.json"}, {"path": "src/b.py"}],
                 additions=400)
    monkeypatch.setattr(p9.subprocess, "run", _run(view))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_OK and "client-name" not in out
    assert "an always-review path" in out and "more changed lines than the threshold" in out, out


def test_json_carries_the_same_decision(p9, monkeypatch, capsys):
    monkeypatch.setattr(p9.subprocess, "run", _run(_view()))
    rc, out, _ = _main(p9, capsys, "--json")
    d = json.loads(out)
    assert rc == p9.EXIT_OK and d["pr"] == PR and d["covered"] is True
    assert d["commit"] == MERGE and d["gates"] == [{"gate": "p20", "ok": True}]


def test_a_short_commit_id_is_refused(p9, capsys):
    assert p9.main(["p20-at-merge", "--repo", "broomva/test", "--commit", "abc123"]) == p9.EXIT_USAGE


@pytest.mark.parametrize("over,kind", [
    (dict(additions=500), "more changed lines than the threshold"),
    (dict(changed_files=3, files=["a", "b", "c"]), "more files than the threshold"),
    (dict(files=["schemas/x.json"]), "an always-review path"),
    (dict(unmeasured=["img.png"]), "a file with no counted lines"),
    (dict(files=["CLAUDE.md"]), "a governance path"),
])
def test_every_trigger_has_a_fixed_name(p9, gates, over, kind):
    from test_p9_merge_gates import _good
    f = _good(p9, **over)
    kinds = [p9._trigger_kind(t) for t in p9.p20_triggers(gates, f)]
    assert kind in kinds and "another trigger" not in kinds, kinds


def test_the_merge_gate_and_p20_at_merge_judge_with_one_rule(p9, gates):
    # Same facts, same verdict on the rule's gates: no second copy to drift.
    from test_p9_merge_gates import _big, _gov
    for f in (_big(p9), _big(p9, comments=[]), _gov(p9), _gov(p9, strata="B,C")):
        rule = {r.gate: r.ok for r in p9.p20_rule(gates, f)}
        full = {r.gate: r.ok for r in p9.evaluate_merge_gates(gates, f) if r.gate in rule}
        assert rule == full
        assert p9.p20_at_merge(gates, f, MERGED_AT)["covered"] == all(rule.values())


def test_a_trigger_added_later_is_named_without_its_text(p9, monkeypatch, capsys):
    # p20_triggers may grow a rule whose text quotes a path; the line must not.
    monkeypatch.setattr(p9, "p20_triggers", lambda g, f: ["new rule on secret-client/x"])
    monkeypatch.setattr(p9.subprocess, "run", _run(_view()))
    rc, out, _ = _main(p9, capsys)
    assert "another trigger" in out and "secret-client" not in out, out


def test_a_pull_request_whose_view_cannot_be_read_cannot_be_told(p9, monkeypatch, capsys):
    inner = _run(_view())

    def run(cmd, *a, **k):
        # the listing reads succeed; the full view behind the gate facts fails
        if cmd[:3] == ["gh", "pr", "view"] and "-q" not in cmd and cmd[-1] != "headRefOid":
            return _Run(returncode=1, stderr="HTTP 502")
        return inner(cmd, *a, **k)
    monkeypatch.setattr(p9.subprocess, "run", run)
    rc, out, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and out == "" and "could not read the pull request" in err


# ─── Round 1 of review (BRO-4175): each finding, as the case that showed it ───

def test_a_verdict_written_after_the_merge_does_not_choose_the_reviewed_commit(
        p9, monkeypatch, capsys):
    # Before the merge: PASS at OLD, and later commits changed a PR file (not carried).
    # After the merge: a PASS at the head. The merge was not covered.
    view = _view(comments=[_comment(_marker(sha=OLD)),
                           _comment(_marker(sha=HEAD), at="2026-09-26T13:00:00Z")])
    monkeypatch.setattr(p9.subprocess, "run", _run(view, compare_map={
        f"{OLD}...{HEAD}": ["src/a.py"], f"{BASE}...{OLD}": ["src/a.py", "src/b.py"]}))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED and "does not cover" in out, out


def test_a_comment_after_the_merge_does_not_break_a_carried_verdict(p9, monkeypatch, capsys):
    view = _view(comments=[_comment(_marker(sha=OLD)),
                           _comment("about the P20-VERDICT above", at="2026-09-26T13:00:00Z")])
    monkeypatch.setattr(p9.subprocess, "run", _run(view, compare_map={
        f"{OLD}...{HEAD}": ["docs/other.md"], f"{BASE}...{OLD}": ["src/a.py", "src/b.py"]}))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_OK and "carries to the final head" in out, out


def test_reviewed_files_are_read_against_the_pull_requests_base_not_the_branch(
        p9, monkeypatch, capsys):
    # OLD touched src/gone.py, a later commit dropped it again. After a merge
    # commit, main...OLD returns no files; the PR's base commit still sees it.
    view = _view(comments=[_comment(_marker(sha=OLD))])
    monkeypatch.setattr(p9.subprocess, "run", _run(view, compare_map={
        f"{OLD}...{HEAD}": ["src/gone.py"],
        f"{BASE}...{OLD}": ["src/a.py", "src/b.py", "src/gone.py"],
        f"main...{OLD}": []}))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED and "does not cover" in out, out


def test_a_failed_compare_is_unknown(p9, monkeypatch, capsys):
    view = _view(comments=[_comment(_marker(sha=OLD))])
    inner = _run(view)

    def run(cmd, *a, **k):
        if cmd[:2] == ["gh", "api"] and any(f"/compare/{OLD}...{HEAD}" in c for c in cmd):
            return _Run(returncode=1, stderr="gh: Not Found (HTTP 404)")
        return inner(cmd, *a, **k)
    monkeypatch.setattr(p9.subprocess, "run", run)
    rc, out, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and out == "" and "could not compare" in err, (rc, out, err)


def test_an_edit_after_the_merge_that_removed_the_verdict_text_cannot_be_told(
        p9, monkeypatch, capsys):
    # The comment no longer names P20-VERDICT; what it said at the merge is unknown.
    monkeypatch.setattr(p9.subprocess, "run", _run(_view(), extra_comments=[
        ("broomva", "OWNER", "2026-09-26T11:00:00Z", "2026-09-26T13:00:00Z")]))
    rc, out, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and "edited after the merge" in err, (rc, out, err)


def test_an_edit_in_the_same_second_as_the_merge_counts(p9, monkeypatch, capsys):
    monkeypatch.setattr(p9.subprocess, "run", _run(_view(), extra_comments=[
        ("broomva", "OWNER", "2026-09-26T11:00:00Z", MERGED_AT)]))
    rc, _, _ = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR


def test_an_unparseable_file_row_prints_no_path(p9, monkeypatch, capsys):
    # This P9Error quotes the row; the command must print the error's kind only.
    view = _view(files=[{"path": "secret-client/a.py"}, {"path": "src/b.py"}])
    inner = _run(view)

    def run(cmd, *a, **k):
        if cmd[:3] == ["gh", "api", "--paginate"] and any("/files" in c for c in cmd):
            return _Run("secret-client/a.py\tbroken\nsrc/b.py\t\tmodified\t5\n")
        return inner(cmd, *a, **k)
    monkeypatch.setattr(p9.subprocess, "run", run)
    rc, out, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and out == ""
    assert "secret-client" not in err and "P9Error" in err, err


def test_a_head_that_moved_between_reads_cannot_be_told(p9, monkeypatch, capsys):
    view = _view()
    inner = _run(view)

    def run(cmd, *a, **k):
        if cmd[:3] == ["gh", "pr", "view"] and "-q" not in cmd and cmd[-1] != "headRefOid":
            return _Run(json.dumps(dict(view, headRefOid=OLD)))
        return inner(cmd, *a, **k)
    monkeypatch.setattr(p9.subprocess, "run", run)
    rc, _, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and "could not read the pull request" in err


@pytest.mark.parametrize("trigger,kind", [
    ("always-review path schemas/12 LOC > 3.json", "an always-review path"),
    ("unmeasured (binary) change img/9 files > 1.png", "a file with no counted lines"),
    ("12 LOC > 3", "more changed lines than the threshold"),
])
def test_a_path_cannot_pose_as_another_trigger(p9, trigger, kind):
    assert p9._trigger_kind(trigger) == kind


# ─── Round 2 of review (BRO-4175) ───

def _policy_with_pass_score(n: int) -> str:
    return _GATED.read_text().replace("pass_score: 7", f"pass_score: {n}")


@pytest.mark.parametrize("before,local,want", [
    (8, 7, "EXIT_AUTO_MERGE_BLOCKED"),   # the merge lowered the bar: judged by the bar before it
    (7, 8, "EXIT_OK"),                   # the merge raised it: same rule
])
def test_the_policy_is_the_one_before_the_merge(p9, monkeypatch, capsys, tmp_path, before, local, want):
    monkeypatch.delenv("BROOMVA_P9_POLICY", raising=False)
    mine = tmp_path / "policy.yaml"
    mine.write_text(_policy_with_pass_score(local))
    view = _view(comments=[_comment(_marker(score=7))])
    calls = []
    inner = _run(view, base_policy=_policy_with_pass_score(before))

    def run(cmd, *a, **k):
        calls.append(" ".join(cmd))
        return inner(cmd, *a, **k)
    monkeypatch.setattr(p9.subprocess, "run", run)
    rc, out, _ = _main(p9, capsys, "--policy", str(mine))
    assert rc == getattr(p9, want), (rc, out)
    assert any(f"/contents/.control/policy.yaml?ref={BASE}" in c for c in calls), calls


def test_a_malformed_local_policy_prints_none_of_its_values(p9, monkeypatch, capsys, tmp_path):
    bad = tmp_path / "policy.yaml"
    bad.write_text(_GATED.read_text().replace("pass_score: 7", "pass_score: REVIEW_SENTINEL"))
    rc, out, err = _main(p9, capsys, "--policy", str(bad))
    assert rc == p9.EXIT_POLICY_ERROR and "REVIEW_SENTINEL" not in out + err, err


@pytest.mark.parametrize("deleted,want", [
    (("2026-09-26T12:30:00Z",), "EXIT_EXTERNAL_ERROR"),   # after the merge: a FAIL may be gone
    ((MERGED_AT,), "EXIT_EXTERNAL_ERROR"),                # in the merge's second
    (("2026-09-26T11:00:00Z",), "EXIT_OK"),               # before it: the gate saw the same comments
])
def test_a_comment_deleted_after_the_merge_cannot_be_told(p9, monkeypatch, capsys, deleted, want):
    monkeypatch.setattr(p9.subprocess, "run", _run(_view(), deleted=deleted))
    rc, _, _ = _main(p9, capsys)
    assert rc == getattr(p9, want)


def test_a_verdict_in_the_same_second_as_the_merge_cannot_be_told(p9, monkeypatch, capsys):
    view = _view(comments=[_comment(_marker(verdict="FAIL", score=4)),
                           _comment(_marker(), at=MERGED_AT)])
    monkeypatch.setattr(p9.subprocess, "run", _run(view))
    rc, _, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and "same second" in err, err


E2 = "e" * 40


@pytest.mark.parametrize("parents,merge_message,pr_commits", [
    ((E2, HEAD), "Merge pull request", ("a", "b")),   # merge commit: the first parent
    ((E2,), "Title (#900)", ("a", "b")),              # squash of two commits
    ((E2,), "only", ("only",)),                       # one commit: squash and rebase agree
])
def test_the_reviewed_files_are_read_against_the_branch_before_the_merge(
        p9, monkeypatch, capsys, parents, merge_message, pr_commits):
    # OLD touched src/gone.py, later dropped; only a base that predates the merge sees it.
    view = _view(comments=[_comment(_marker(sha=OLD))])
    monkeypatch.setattr(p9.subprocess, "run", _run(
        view, parents=parents, merge_message=merge_message, pr_commits=pr_commits,
        compare_map={f"{OLD}...{HEAD}": ["src/gone.py"],
                     f"{E2}...{OLD}": ["src/a.py", "src/b.py", "src/gone.py"],
                     f"{BASE}...{OLD}": []}))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_AUTO_MERGE_BLOCKED and "does not cover" in out, out


def test_a_rebase_of_several_commits_cannot_be_told(p9, monkeypatch, capsys):
    monkeypatch.setattr(p9.subprocess, "run", _run(
        _view(), parents=(E2,), merge_message="second", pr_commits=("first", "second")))
    rc, _, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and "rebase" in err, err


def test_more_deleted_comments_than_one_page_cannot_be_told(p9, monkeypatch, capsys):
    monkeypatch.setattr(p9.subprocess, "run", _run(_view(), more_deleted=True))
    rc, _, err = _main(p9, capsys)
    assert rc == p9.EXIT_EXTERNAL_ERROR and "deleted comments" in err, err
