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
    HEAD, OLD, _GATED, _Run, _comment, _fake_gh, _marker, _view, gates, p9)  # noqa: F401  (fixtures)

MERGE = "d" * 40
MERGED_AT = "2026-09-26T12:00:00Z"
PR = 900


def _run(view, *, pulls=None, edited=None, **fake):
    """The gate tests' fake, plus the two reads only p20-at-merge makes."""
    inner = _fake_gh(view, calls=[], **fake)
    pulls = ([{"number": PR, "merge_commit_sha": MERGE, "merged_at": MERGED_AT}]
             if pulls is None else pulls)
    edited = edited or {}

    def run(cmd, *a, **k):
        if cmd[:2] == ["gh", "api"] and any(f"/commits/{MERGE}/pulls" in c for c in cmd):
            return _Run(json.dumps(pulls))
        if cmd[:3] == ["gh", "api", "--paginate"] and any("/comments" in c for c in cmd):
            rows = [f"{c['author']['login']}\t{c['authorAssociation']}\t{c['createdAt']}\t"
                    f"{edited.get(i, c['createdAt'])}\n"
                    for i, c in enumerate(view["comments"])
                    if "p20-verdict" in c["body"].lower()]
            return _Run("".join(rows))
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
        f"{OLD}...{HEAD}": ["docs/other.md"], f"main...{OLD}": ["src/a.py", "src/b.py"]}))
    rc, out, _ = _main(p9, capsys)
    assert rc == p9.EXIT_OK and "carries to the final head" in out, out


def test_a_verdict_on_an_earlier_commit_that_later_code_changed_is_not_covered(
        p9, monkeypatch, capsys):
    view = _view(comments=[_comment(_marker(sha=OLD))])
    monkeypatch.setattr(p9.subprocess, "run", _run(view, compare_map={
        f"{OLD}...{HEAD}": ["src/a.py"], f"main...{OLD}": ["src/a.py", "src/b.py"]}))
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
        {"number": 5, "merge_commit_sha": "e" * 40, "merged_at": MERGED_AT}]))
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
