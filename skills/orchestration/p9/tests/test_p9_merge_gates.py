"""BRO-2591 — gated auto-merge: any branch merges iff its PR passes the gates.

Every gate is tested on BOTH arms: a baseline PR that must merge, and one
mutation per gate that must not. A gate with only a passing test cannot be told
apart from a gate that cannot fail.
"""
from __future__ import annotations

import dataclasses
import importlib
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_FIXTURES = _HERE / "fixtures"
_GATED = _FIXTURES / "policy-gated.yaml"
HEAD = "a" * 40
OLD = "b" * 40


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_GATED))
    monkeypatch.setenv("BROOMVA_P9_REPO", "broomva/test")
    if "p9" in sys.modules:
        del sys.modules["p9"]
    mod = importlib.import_module("p9")
    monkeypatch.setattr(mod, "_GATE_RETRY_SLEEP", 0)
    return mod


@pytest.fixture()
def gates(p9):
    return p9.load_policy(_GATED).auto_merge.gates


def _marker(verdict="PASS", score=8, strata="B,C", sha=HEAD):
    return f"P20-VERDICT: {verdict} score={score} strata={strata} sha={sha}"


def _comment(body, login="broomva", assoc="OWNER", at="2026-09-26T10:00:00Z"):
    return {"author": {"login": login}, "authorAssociation": assoc,
            "body": body, "createdAt": at}


def _good(p9, **over):
    """A small, single-file PR that every gate passes."""
    base = dict(pr=1, state="OPEN", is_draft=False, base="main", head_sha=HEAD,
                merge_state="CLEAN", mergeable="MERGEABLE", review_decision="",
                reviews=[], comments=[], additions=8, deletions=2, changed_files=1,
                files=["src/x.py"],
                required_checks=[{"name": "Merge Gate", "bucket": "pass"}],
                all_checks=None, behind_by=0, unresolved_threads=0)
    base.update(over)
    return p9.PRGateFacts(**base)


def _big(p9, **over):
    """Multi-file, so over the P20 threshold."""
    kw = dict(changed_files=2, files=["src/x.py", "src/y.py"])
    kw.update(over)
    return _good(p9, **kw)


def _gov(p9, strata="A,B,C", **over):
    kw = dict(changed_files=2, files=["CLAUDE.md", "src/y.py"],
              comments=[_comment(_marker(strata=strata))],
              all_checks=[{"name": "Merge Gate", "bucket": "pass"},
                          {"name": "stability-check", "bucket": "pass"}],
              l3_recent_commits=0)
    kw.update(over)
    return _good(p9, **kw)


def _failed(p9, g, f):
    return {r.gate for r in p9.evaluate_merge_gates(g, f) if not r.ok}


# ─────────────────────────────────────────────────────────────────────────────
# Parser: no YAML can switch a gate off or loosen it below the P20 definition
# ─────────────────────────────────────────────────────────────────────────────
_HEADER = _GATED.read_text().split("auto_merge:")[0]


def _policy(p9, tmp_path, block):
    f = tmp_path / "p.yaml"
    f.write_text(_HEADER + "auto_merge:\n  enabled: true\n" + block, encoding="utf-8")
    return p9.load_policy(f)


class TestParse:
    def test_gated_fixture_parses(self, p9, gates):
        assert gates.p20.pass_score == 7
        assert gates.governance.required_strata == ("A", "B", "C")
        assert gates.governance.required_checks == ("stability-check",)

    def test_configured_bots_extend_never_replace(self, gates):
        assert "some-lint-bot" in gates.review_bots
        assert "coderabbitai" in gates.review_bots
        assert "CodeRabbit" in gates.review_bots

    def test_no_gates_is_legacy(self, p9):
        cfg = p9.load_policy(_FIXTURES / "policy-with-auto-merge.yaml")
        assert cfg.auto_merge.gates is None

    @pytest.mark.parametrize("block,needle", [
        ("  gates:\n    p20:\n      pass_score: 6\n", "pass_score"),
        ("  gates:\n    p20:\n      max_loc: 500\n", "max_loc"),
        ("  gates:\n    p20:\n      max_files: 5\n", "max_files"),
        ("  gates:\n    governance:\n      required_strata: [D]\n", "required_strata"),
        ("  gates:\n    governance:\n      required_checks: []\n", "required_checks"),
        ("  gates:\n    governance:\n      paths: []\n", "paths"),
        ("  gates:\n    governance:\n      l3_max_per_window: 0\n", "l3_max_per_window"),
        ("  gates:\n    requred_strata: [A]\n", "unknown key"),
        ("  gates:\n    p20:\n      pass_scor: 9\n", "unknown key"),
        ("  rules:\n    - branch_pattern: \"docs/*\"\n      action: auto\n"
         "  gates:\n    p20:\n      pass_score: 7\n", "action=auto"),
    ])
    def test_weakening_is_rejected(self, p9, tmp_path, block, needle):
        with pytest.raises(p9.PolicyError) as e:
            _policy(p9, tmp_path, block)
        assert needle in str(e.value)

    def test_stricter_values_accepted(self, p9, tmp_path):
        cfg = _policy(p9, tmp_path, "  gates:\n    p20:\n      pass_score: 9\n"
                                    "      max_loc: 50\n      max_files: 0\n")
        assert cfg.auto_merge.gates.p20.pass_score == 9
        assert cfg.auto_merge.gates.p20.max_files == 0


# ─────────────────────────────────────────────────────────────────────────────
# Evaluator: the should-merge arm, then one must-not arm per gate
# ─────────────────────────────────────────────────────────────────────────────
class TestEvaluatorBothArms:
    def test_small_green_pr_merges(self, p9, gates):
        assert _failed(p9, gates, _good(p9)) == set()

    def test_unstable_with_green_required_checks_merges(self, p9, gates):
        # UNSTABLE = only a NON-required check is un-green (a CodeRabbit
        # status that never resolves). Required ones decide.
        assert _failed(p9, gates, _good(p9, merge_state="UNSTABLE")) == set()

    @pytest.mark.parametrize("over,gate", [
        ({"is_draft": True}, "open"),
        ({"state": "CLOSED"}, "open"),
        ({"merge_state": "BLOCKED"}, "mergeable"),
        ({"merge_state": "UNKNOWN"}, "mergeable"),
        ({"merge_state": "DIRTY", "mergeable": "CONFLICTING"}, "mergeable"),
        ({"required_checks": [{"name": "Merge Gate", "bucket": "fail"}]}, "required_checks"),
        ({"required_checks": [{"name": "Merge Gate", "bucket": "pending"}]}, "required_checks"),
        ({"required_checks": [{"name": "Merge Gate", "bucket": "skipping"}]}, "required_checks"),
        ({"required_checks": None}, "required_checks"),
        ({"required_checks": []}, "required_checks"),
        ({"behind_by": 1}, "up_to_date"),
        ({"behind_by": None}, "up_to_date"),
        ({"reviews": [{"author": {"login": "someone"}, "state": "CHANGES_REQUESTED"}]},
         "no_changes_requested"),
        ({"review_decision": "CHANGES_REQUESTED"}, "no_changes_requested"),
        ({"unresolved_threads": 1}, "threads_resolved"),
        ({"unresolved_threads": -1}, "threads_resolved"),
        ({"changed_files": 101, "files": ["src/x.py"] * 100}, "classifiable"),
        ({"head_sha": ""}, "classifiable"),
    ])
    def test_each_gate_blocks(self, p9, gates, over, gate):
        assert gate in _failed(p9, gates, _good(p9, **over))

    def test_coderabbit_success_is_not_a_required_check(self, p9, gates):
        # Rate-limited CodeRabbit reports SUCCESS. If it is the only required
        # check, nothing vouches for the PR.
        f = _good(p9, required_checks=[{"name": "CodeRabbit", "bucket": "pass"}])
        assert "required_checks" in _failed(p9, gates, f)

    def test_coderabbit_red_does_not_block_when_real_checks_green(self, p9, gates):
        f = _good(p9, required_checks=[{"name": "Merge Gate", "bucket": "pass"},
                                       {"name": "CodeRabbit", "bucket": "fail"}])
        assert _failed(p9, gates, f) == set()


class TestP20:
    def test_multi_file_without_marker_blocks(self, p9, gates):
        assert "p20" in _failed(p9, gates, _big(p9))

    def test_multi_file_with_pass_at_head_merges(self, p9, gates):
        assert _failed(p9, gates, _big(p9, comments=[_comment(_marker())])) == set()

    def test_over_200_loc_single_file_needs_p20(self, p9, gates):
        assert "p20" in _failed(p9, gates, _good(p9, additions=150, deletions=51))
        assert _failed(p9, gates, _good(p9, additions=150, deletions=50)) == set()

    def test_public_api_path_needs_p20(self, p9, gates):
        assert "p20" in _failed(p9, gates, _good(p9, files=["schemas/state.json"]))

    @pytest.mark.parametrize("comment", [
        _comment(_marker(), login="coderabbitai"),          # review bot
        _comment(_marker(), login="renovate[bot]"),          # any [bot]
        _comment(_marker(), login="some-lint-bot"),          # policy-listed bot
        _comment(_marker(), assoc="NONE"),                   # drive-by account
        _comment(_marker(), assoc="CONTRIBUTOR"),
        _comment(_marker(score=6)),                          # below 7
        _comment(_marker(verdict="STOP")),
        _comment("P20 verdict PASS 9/10, looks great"),      # prose is not a marker
    ])
    def test_untrusted_or_weak_markers_do_not_count(self, p9, gates, comment):
        assert "p20" in _failed(p9, gates, _big(p9, comments=[comment]))

    def test_latest_marker_wins_so_old_pass_cannot_be_cherry_picked(self, p9, gates):
        f = _big(p9, comments=[
            _comment(_marker(verdict="PASS", score=9), at="2026-09-26T10:00:00Z"),
            _comment(_marker(verdict="FAIL", score=4), at="2026-09-26T11:00:00Z"),
        ])
        assert "p20" in _failed(p9, gates, f)

    def test_stale_marker_carries_only_across_unrelated_base_updates(self, p9, gates):
        common = dict(comments=[_comment(_marker(sha=OLD))], marker_is_ancestor=True,
                      reviewed_files=["src/x.py", "src/y.py"])
        ok = _big(p9, marker_delta_files=["docs/unrelated.md"], **common)
        assert _failed(p9, gates, ok) == set()
        touched = _big(p9, marker_delta_files=["src/y.py"], **common)
        assert "p20" in _failed(p9, gates, touched)

    def test_reverting_a_reviewed_change_invalidates_the_verdict(self, p9, gates):
        # src/y.py was reviewed, then reverted: it left the PR's file list but
        # the reviewed content changed. Checked against the REVIEWED files too.
        f = _good(p9, changed_files=2, files=["src/x.py", "docs/a.md"],
                  comments=[_comment(_marker(sha=OLD))], marker_is_ancestor=True,
                  reviewed_files=["src/x.py", "src/y.py", "docs/a.md"],
                  marker_delta_files=["src/y.py"])
        assert "p20" in _failed(p9, gates, f)

    @pytest.mark.parametrize("over", [
        {"marker_is_ancestor": False, "marker_delta_files": [], "reviewed_files": []},
        {"marker_is_ancestor": None, "marker_delta_files": [], "reviewed_files": []},
        {"marker_is_ancestor": True, "marker_delta_files": None, "reviewed_files": []},
        {"marker_is_ancestor": True, "marker_delta_files": [], "reviewed_files": None},
        {"marker_is_ancestor": True, "marker_delta_files": ["z"] * 300, "reviewed_files": []},
    ])
    def test_unprovable_carry_forward_blocks(self, p9, gates, over):
        f = _big(p9, comments=[_comment(_marker(sha=OLD))], **over)
        assert "p20" in _failed(p9, gates, f)


class TestGovernanceTier:
    def test_all_strata_checks_and_rate_merges(self, p9, gates):
        assert _failed(p9, gates, _gov(p9)) == set()

    def test_two_strata_is_not_enough(self, p9, gates):
        assert "governance_strata" in _failed(p9, gates, _gov(p9, strata="B,C"))

    @pytest.mark.parametrize("checks", [
        [{"name": "Merge Gate", "bucket": "pass"}],                       # absent
        [{"name": "stability-check", "bucket": "skipping"}],
        [{"name": "stability-check", "bucket": "fail"}],
        None,
    ])
    def test_stability_check_must_run_and_pass(self, p9, gates, checks):
        assert "governance_checks" in _failed(p9, gates, _gov(p9, all_checks=checks))

    @pytest.mark.parametrize("n", [1, 2, None])
    def test_l3_rate_budget_blocks(self, p9, gates, n):
        assert "l3_rate" in _failed(p9, gates, _gov(p9, l3_recent_commits=n))

    @pytest.mark.parametrize("path", [".CONTROL/policy.yaml", "./AGENTS.md", "claude.md"])
    def test_case_and_prefix_variants_are_governance(self, p9, gates, path):
        f = _big(p9, files=[path, "src/y.py"], comments=[_comment(_marker())])
        assert "governance_strata" in _failed(p9, gates, f)

    def test_nested_project_claude_md_is_not_root_governance(self, p9, gates):
        f = _big(p9, files=["apps/x/CLAUDE.md", "src/y.py"], comments=[_comment(_marker())])
        assert _failed(p9, gates, f) == set()

    def test_governance_is_always_over_the_p20_threshold(self, p9, gates):
        f = _gov(p9, changed_files=1, files=["AGENTS.md"], comments=[])
        assert {"p20", "governance_strata"} <= _failed(p9, gates, f)


# ─────────────────────────────────────────────────────────────────────────────
# End to end through `p9 auto-merge`, with gh mocked
# ─────────────────────────────────────────────────────────────────────────────
class _Run:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def _seed_merge_ready(p9, pr):
    for prev, curr in [(p9.PRState.PUSHED, p9.PRState.WATCHING),
                       (p9.PRState.WATCHING, p9.PRState.GREEN),
                       (p9.PRState.GREEN, p9.PRState.MERGE_READY)]:
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-09-26T00:00:00+00:00", pr=pr, repo="broomva/test",
            from_state=prev.value, to_state=curr.value, watcher_id="seed"))


def _fake_gh(view, *, required=None, calls, base_policy=None):
    required = required if required is not None else [{"name": "Merge Gate", "bucket": "pass"}]

    def run(cmd, *a, **k):
        calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"] and "-q" in cmd:
            return _Run(json.dumps({"branch": view["headRefName"],
                                    "files": [x["path"] for x in view["files"]]}))
        if cmd[:3] == ["gh", "pr", "view"]:
            return _Run(json.dumps(view))
        if cmd[:3] == ["gh", "pr", "checks"]:
            return _Run(json.dumps(required), returncode=0)
        if cmd[:2] == ["gh", "api"] and "graphql" in cmd:
            return _Run(json.dumps({"data": {"repository": {"pullRequest": {
                "reviewThreads": {"nodes": [{"isResolved": True}]}}}}}))
        if cmd[:2] == ["gh", "api"] and any("/contents/.control/policy.yaml" in c for c in cmd):
            if base_policy is None:
                return _Run(stderr="gh: Not Found (HTTP 404)", returncode=1)
            return _Run(base_policy)
        if cmd[:2] == ["gh", "api"] and any("/compare/" in c for c in cmd):
            return _Run(json.dumps({"status": "ahead", "behind_by": 0, "files": []}))
        if cmd[:3] == ["gh", "pr", "merge"]:
            return _Run(returncode=0)
        return _Run(returncode=1, stderr=f"unmocked {cmd[:4]}")
    return run


def _view(**over):
    v = {"state": "OPEN", "isDraft": False, "baseRefName": "main", "headRefName": "fix/anything",
         "headRefOid": HEAD, "mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE",
         "reviewDecision": "", "latestReviews": [], "additions": 20, "deletions": 5,
         "changedFiles": 2, "files": [{"path": "src/a.py"}, {"path": "src/b.py"}],
         "comments": [_comment(_marker())]}
    v.update(over)
    return v


class TestAutoMergeCommand:
    def test_any_branch_merges_when_every_gate_passes(self, p9, monkeypatch):
        # fix/* was stranded under the prefix allowlist; the gates decide now.
        _seed_merge_ready(p9, 700)
        calls = []
        monkeypatch.setattr(p9.subprocess, "run", _fake_gh(_view(), calls=calls))
        rc = p9.main(["auto-merge", "700", "--repo", "broomva/test"])
        assert rc == p9.EXIT_OK
        merges = [c for c in calls if c[:3] == ["gh", "pr", "merge"]]
        assert len(merges) == 1
        # Pinned to the SHA the gates verified.
        assert merges[0][merges[0].index("--match-head-commit") + 1] == HEAD
        assert p9.current_pr_state(700) == p9.PRState.MERGED

    def test_coderabbit_only_pass_must_not_merge(self, p9, monkeypatch):
        _seed_merge_ready(p9, 701)
        calls = []
        view = _view(comments=[_comment(_marker(), login="coderabbitai")])
        monkeypatch.setattr(p9.subprocess, "run", _fake_gh(
            view, calls=calls, required=[{"name": "CodeRabbit", "bucket": "pass"}]))
        rc = p9.main(["auto-merge", "701", "--repo", "broomva/test"])
        assert rc == p9.EXIT_AUTO_MERGE_BLOCKED
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]
        rows, _ = p9.jsonl_read_all(p9.state_jsonl())
        last = [r for r in rows if r["pr"] == 701][-1]
        failed = {g["gate"] for g in last["extra"]["auto_merge"]["gates"] if not g["ok"]}
        assert {"required_checks", "p20"} <= failed

    def test_blocking_rule_overrides_green_gates(self, p9, monkeypatch):
        _seed_merge_ready(p9, 702)
        calls = []
        view = _view(files=[{"path": "secrets/key.txt"}, {"path": "src/b.py"}])
        monkeypatch.setattr(p9.subprocess, "run", _fake_gh(view, calls=calls))
        rc = p9.main(["auto-merge", "702", "--repo", "broomva/test"])
        assert rc == p9.EXIT_AUTO_MERGE_BLOCKED
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]


class TestBasePolicyIsAuthoritative:
    """Without the operator pin, the policy on the PR's BASE judges the PR."""

    @pytest.fixture()
    def unpinned(self, p9, monkeypatch):
        monkeypatch.delenv("BROOMVA_P9_POLICY", raising=False)
        monkeypatch.chdir(_FIXTURES.parent)  # no .control/ walk-up hit needed
        return p9

    def test_pr_cannot_approve_itself_by_editing_the_policy(self, unpinned, monkeypatch):
        p9 = unpinned
        local = p9.load_policy(_GATED).auto_merge          # the PR's permissive copy
        base_text = (_FIXTURES / "policy-with-auto-merge.yaml").read_text()  # main: legacy
        calls = []
        view = _view(headRefName="fix/loosen", files=[{"path": ".control/policy.yaml"}])
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(view, calls=calls, base_policy=base_text))
        d = p9.decide_auto_merge(local, pr=703, repo="broomva/test",
                                 branch="fix/loosen", paths=[".control/policy.yaml"])
        assert d["source"] == "broomva/test@main"
        assert d["action"] == "require_human"   # main's rules, not the PR's

    def test_pr_introducing_a_policy_file_is_blocked(self, unpinned, monkeypatch):
        p9 = unpinned
        local = p9.load_policy(_GATED).auto_merge
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(_view(), calls=calls, base_policy=None))
        d = p9.decide_auto_merge(local, pr=704, repo="broomva/test", branch="x",
                                 paths=[".control/policy.yaml"])
        assert d["action"] == "require_human"
        assert "own introduction" in d["reason"]

    def test_repo_without_a_base_policy_uses_the_local_one(self, unpinned, monkeypatch):
        p9 = unpinned
        local = p9.load_policy(_GATED).auto_merge
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(_view(), calls=calls, base_policy=None))
        d = p9.decide_auto_merge(local, pr=705, repo="broomva/test", branch="x",
                                 paths=["src/a.py", "src/b.py"])
        assert d["source"].startswith("local policy")
        assert d["action"] == "auto"

    def test_unreadable_base_policy_blocks(self, unpinned, monkeypatch):
        p9 = unpinned
        local = p9.load_policy(_GATED).auto_merge

        def run(cmd, *a, **k):
            if any("/contents/.control/policy.yaml" in c for c in cmd):
                return _Run(stderr="HTTP 502", returncode=1)
            return _fake_gh(_view(), calls=[])(cmd)
        monkeypatch.setattr(p9.subprocess, "run", run)
        d = p9.decide_auto_merge(local, pr=706, repo="broomva/test", branch="x",
                                 paths=["src/a.py"])
        assert d["action"] == "require_human"


class TestRecordAndCheck:
    def test_p20_record_pins_the_current_head(self, p9, monkeypatch, capsys):
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda cmd, *a, **k: _Run(json.dumps({"headRefOid": HEAD})))
        rc = p9.main(["p20-record", "9", "--score", "8", "--strata", "C,B", "--dry-run"])
        assert rc == p9.EXIT_OK
        out = capsys.readouterr().out.strip()
        assert out == f"P20-VERDICT: PASS score=8 strata=B,C sha={HEAD}"
        # What it writes is what the gate reads.
        m = p9.latest_p20_marker([_comment(out)], ())
        assert (m.verdict, m.score, m.strata, m.sha) == ("PASS", 8, ("B", "C"), HEAD)

    def test_p20_record_refuses_a_pass_below_seven(self, p9):
        assert p9.main(["p20-record", "9", "--score", "6", "--strata", "B",
                        "--dry-run"]) == p9.EXIT_USAGE

    def test_gate_check_exit_codes(self, p9, monkeypatch):
        monkeypatch.setattr(p9.subprocess, "run", _fake_gh(_view(), calls=[]))
        assert p9.main(["gate-check", "710", "--repo", "broomva/test"]) == p9.EXIT_OK
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(_view(comments=[]), calls=[]))
        assert p9.main(["gate-check", "711", "--repo", "broomva/test"]) == \
            p9.EXIT_AUTO_MERGE_BLOCKED

    def test_gate_results_are_json_serializable(self, p9, gates):
        results = p9.evaluate_merge_gates(gates, _good(p9))
        json.dumps([dataclasses.asdict(r) for r in results])
