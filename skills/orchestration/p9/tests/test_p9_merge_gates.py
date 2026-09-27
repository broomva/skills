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
BASE = "c" * 40


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
                all_checks=[{"name": "Merge Gate", "bucket": "pass"},
                            {"name": "pytest", "bucket": "pass"}],
                behind_by=0, unresolved_threads=0, base_sha=BASE)
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
        ("  gates:\n    governance:\n      required_strata: [A]\n", "required_strata"),
        ("  gates:\n    governance:\n      required_strata: [B, C]\n", "required_strata"),
        ("  gates:\n    governance:\n      paths: [docs/**]\n", "may add paths"),
        ("  gates:\n    governance:\n      paths: [CLAUDE.md, AGENTS.md]\n", "may add paths"),
        ("  gates:\n    governance:\n      required_checks: [Merge Gate]\n", "stability-check"),
        ("  gates:\n    governance:\n      l3_max_per_window: 2\n", "l3_max_per_window"),
        ("  gates:\n    governance:\n      l3_window_seconds: 3600\n", "l3_window_seconds"),
        ("  gates:\n    governance:\n      required_checks: []\n", "required_checks"),
        ("  gates:\n    governance:\n      paths: []\n", "paths"),
        ("  gates:\n    governance:\n      l3_max_per_window: 0\n", "l3_max_per_window"),
        ("  gates:\n    requred_strata: [A]\n", "unknown key"),
        ("  gates:\n    p20: []\n", "p20 must be a mapping"),
        ("  gates:\n    p20: false\n", "p20 must be a mapping"),
        ("  gates:\n    governance: []\n", "governance must be a mapping"),
        ("  gates:\n    p20:\n      pass_scor: 9\n", "unknown key"),
        ("  rules:\n    - branch_pattern: \"docs/*\"\n      action: auto\n"
         "  gates:\n    p20:\n      pass_score: 7\n", "action=auto"),
    ])
    def test_weakening_is_rejected(self, p9, tmp_path, block, needle):
        with pytest.raises(p9.PolicyError) as e:
            _policy(p9, tmp_path, block)
        assert needle in str(e.value)

    def test_governance_may_add_paths_and_checks(self, p9, tmp_path):
        cfg = _policy(p9, tmp_path,
                      "  gates:\n    governance:\n      paths: [CLAUDE.md, AGENTS.md, "
                      "METALAYER.md, .control/policy.yaml, .control/rcs-parameters.toml, "
                      "SECURITY.md]\n      required_checks: [stability-check, extra]\n"
                      "      l3_window_seconds: 172800\n")
        gov = cfg.auto_merge.gates.governance
        assert "SECURITY.md" in gov.paths and "extra" in gov.required_checks
        assert gov.l3_window_seconds == 172800

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
        ({"base_sha": ""}, "up_to_date"),
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
        _comment(_marker(score=99)),                         # not a /10 score
        _comment(_marker(score=100)),
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
        # a duplicate name must not let a later green run mask a red one
        [{"name": "stability-check", "bucket": "fail"},
         {"name": "stability-check", "bucket": "pass"}],
        [{"name": "stability-check", "bucket": "pass"},
         {"name": "stability-check", "bucket": "fail"}],
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


def _fake_gh(view, *, required=None, all_checks=None, calls, base_policy=None,
             base_now=BASE, renamed=None, binary=(), compare_files=None):
    required = required if required is not None else [{"name": "Merge Gate", "bucket": "pass"}]
    all_checks = all_checks if all_checks is not None else (
        required + [{"name": "pytest", "bucket": "pass"}])
    renamed = renamed or {}
    every = [x["path"] for x in view["files"]]
    capped = dict(view, files=view["files"][:100], changedFiles=len(every))

    def run(cmd, *a, **k):
        calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"] and "-q" in cmd:
            return _Run(json.dumps({"branch": view["headRefName"],
                                    "head": view["headRefOid"], "changed": len(every)}))
        if cmd[:3] == ["gh", "pr", "view"] and "baseRefName" in cmd[-1] and "," not in cmd[-1]:
            return _Run(json.dumps({"baseRefName": view["baseRefName"]}))
        if cmd[:3] == ["gh", "pr", "view"]:
            return _Run(json.dumps(capped))
        if cmd[:3] == ["gh", "api", "--paginate"]:
            return _Run("".join(
                f"{p}\t{renamed.get(p, '')}\tmodified\t{0 if p in binary else 5}\n"
                for p in every))
        if cmd[:3] == ["gh", "pr", "checks"]:
            return _Run(json.dumps(required if "--required" in cmd else all_checks))
        if cmd[:2] == ["gh", "api"] and "graphql" in cmd:
            return _Run(json.dumps({"data": {"repository": {"pullRequest": {
                "reviewThreads": {"totalCount": 1, "nodes": [{"isResolved": True}]}}}}}))
        if cmd[:2] == ["gh", "api"] and any("/branches/" in c for c in cmd):
            return _Run(json.dumps({"commit": {"sha": base_now}}))
        if cmd[:2] == ["gh", "api"] and any("/contents/.control/policy.yaml" in c for c in cmd):
            if base_policy is None:
                return _Run(stderr="gh: Not Found (HTTP 404)", returncode=1)
            return _Run(base_policy)
        if cmd[:2] == ["gh", "api"] and any("/compare/" in c for c in cmd):
            return _Run(json.dumps({"status": "ahead", "behind_by": 0,
                                    "files": [{"filename": f} for f in (compare_files or [])],
                                    "base_commit": {"sha": BASE}}))
        if cmd[:2] == ["gh", "api"] and any("/commits" in c for c in cmd):
            return _Run(json.dumps([]))
        if cmd[:3] == ["gh", "pr", "merge"]:
            return _Run(returncode=0)
        return _Run(returncode=1, stderr=f"unmocked {cmd[:4]}")
    return run


def _listing(p9, view, renamed=None):
    every = [x["path"] for x in view["files"]]
    return p9.PRListing(branch=view["headRefName"], head_sha=view["headRefOid"],
                        paths=tuple(every + [v for v in (renamed or {}).values()]),
                        unmeasured=())


def _view(**over):
    v = {"state": "OPEN", "isDraft": False, "baseRefName": "main", "headRefName": "fix/anything",
         "headRefOid": HEAD, "mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE",
         "reviewDecision": "", "reviews": [], "additions": 20, "deletions": 5,
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


class TestMergeTimeRaces:
    def test_base_moving_during_evaluation_blocks_the_merge(self, p9, monkeypatch):
        # --match-head-commit pins the head; the gates also saw one base tip.
        _seed_merge_ready(p9, 720)
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(_view(), calls=calls, base_now="f" * 40))
        rc = p9.main(["auto-merge", "720", "--repo", "broomva/test"])
        assert rc == p9.EXIT_AUTO_MERGE_BLOCKED
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]

    def test_pr_over_100_files_is_judged_on_the_complete_list(self, p9, monkeypatch):
        _seed_merge_ready(p9, 721)
        files = [{"path": f"src/m{i}.py"} for i in range(150)]
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(_view(files=files, changedFiles=150), calls=calls))
        assert p9.main(["auto-merge", "721", "--repo", "broomva/test"]) == p9.EXIT_OK

    def test_governance_file_on_page_two_is_found(self, p9, monkeypatch):
        _seed_merge_ready(p9, 722)
        files = [{"path": f"src/m{i}.py"} for i in range(120)] + [{"path": "AGENTS.md"}]
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(_view(files=files, changedFiles=121), calls=calls))
        rc = p9.main(["auto-merge", "722", "--repo", "broomva/test"])
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
                                 listing=_listing(p9, view))
        assert d["source"] == f"broomva/test@{BASE}"   # read AT the pinned base commit
        assert d["action"] == "require_human"   # main's rules, not the PR's

    def test_pr_introducing_a_policy_file_is_blocked(self, unpinned, monkeypatch):
        p9 = unpinned
        local = p9.load_policy(_GATED).auto_merge
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(_view(), calls=calls, base_policy=None))
        view = _view(files=[{"path": ".control/policy.yaml"}])
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(view, calls=calls, base_policy=None))
        d = p9.decide_auto_merge(local, pr=704, repo="broomva/test",
                                 listing=_listing(p9, view))
        assert d["action"] == "require_human"
        assert "own introduction" in d["reason"]

    def test_repo_without_a_base_policy_uses_the_local_one(self, unpinned, monkeypatch):
        p9 = unpinned
        local = p9.load_policy(_GATED).auto_merge
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(_view(), calls=calls, base_policy=None))
        d = p9.decide_auto_merge(local, pr=705, repo="broomva/test",
                                 listing=_listing(p9, _view()))
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
        d = p9.decide_auto_merge(local, pr=706, repo="broomva/test",
                                 listing=_listing(p9, _view()))
        assert d["action"] == "require_human"


class TestRecordAndCheck:
    def test_p20_record_pins_the_reviewed_commit(self, p9, monkeypatch, capsys):
        rc = p9.main(["p20-record", "9", "--score", "8", "--strata", "C,B",
                      "--sha", HEAD, "--dry-run"])
        assert rc == p9.EXIT_OK
        out = capsys.readouterr().out.strip()
        assert out == f"P20-VERDICT: PASS score=8 strata=B,C sha={HEAD}"
        # What it writes is what the gate reads.
        m = p9.latest_p20_marker([_comment(out)], ())
        assert (m.verdict, m.score, m.strata, m.sha) == ("PASS", 8, ("B", "C"), HEAD)

    def test_p20_record_refuses_a_pass_below_seven(self, p9):
        assert p9.main(["p20-record", "9", "--score", "6", "--strata", "B",
                        "--sha", HEAD, "--dry-run"]) == p9.EXIT_USAGE

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


# ─────────────────────────────────────────────────────────────────────────────
# P20 round-1 findings (BRO-2591): each with both arms
# ─────────────────────────────────────────────────────────────────────────────
class TestMarkerIsTheFirstLineOnly:
    def test_a_note_quoting_a_pass_cannot_flip_a_fail(self, p9, gates):
        body = _marker(verdict="FAIL", score=3, strata="B") + \
            "\n\nledger: " + _marker(score=9, strata="A,B,C")
        assert "p20" in _failed(p9, gates, _big(p9, comments=[_comment(body)]))

    def test_marker_on_line_one_with_a_note_below_counts(self, p9, gates):
        body = _marker() + "\n\nround ledger: 6 -> 8"
        assert _failed(p9, gates, _big(p9, comments=[_comment(body)])) == set()

    def test_crlf_fail_after_pass_is_read_as_fail(self, p9, gates):
        f = _big(p9, comments=[
            _comment(_marker(), at="2026-09-26T10:00:00Z"),
            _comment(_marker(verdict="FAIL", score=4) + "\r\n", at="2026-09-26T11:00:00Z")])
        assert "p20" in _failed(p9, gates, f)

    @pytest.mark.parametrize("later", [
        "**" + _marker(verdict="FAIL", score=4) + "**",      # bold
        "P20-VERDICT: FAIL score=4",                          # truncated
        "re-ran P20-VERDICT, now failing",                   # prose naming it
    ])
    def test_a_later_unparseable_verdict_blocks(self, p9, gates, later):
        f = _big(p9, comments=[_comment(_marker(), at="2026-09-26T10:00:00Z"),
                               _comment(later, at="2026-09-26T11:00:00Z")])
        assert "p20" in _failed(p9, gates, f)

    def test_a_later_comment_not_naming_a_verdict_leaves_the_pass(self, p9, gates):
        f = _big(p9, comments=[_comment(_marker(), at="2026-09-26T10:00:00Z"),
                               _comment("thanks, merging soon", at="2026-09-26T11:00:00Z")])
        assert _failed(p9, gates, f) == set()


class TestPolicyShape:
    def test_unknown_auto_merge_key_is_rejected(self, p9, tmp_path):
        with pytest.raises(p9.PolicyError) as e:
            _policy(p9, tmp_path, "  gate:\n    p20:\n      pass_score: 7\n")
        assert "unknown key" in str(e.value)

    def test_auto_default_with_gates_is_rejected(self, p9, tmp_path):
        with pytest.raises(p9.PolicyError) as e:
            _policy(p9, tmp_path, "  default_action: auto\n  gates:\n    p20:\n"
                                  "      pass_score: 7\n")
        assert "default_action" in str(e.value)

    @pytest.mark.parametrize("value", ["null", "~"])
    def test_explicit_null_gates_is_gated(self, p9, value):
        # The minimal loader (CI has no PyYAML) returns None for `null`, as PyYAML
        # does for a bare `gates:`. Null must mean gated-with-defaults, not legacy.
        text = _HEADER + f"auto_merge:\n  enabled: true\n  gates: {value}\n"
        assert p9._parse_policy(p9._minimal_yaml_load(text)).auto_merge.gates is not None

    def test_empty_gates_is_gated_in_both_loaders(self, p9, tmp_path):
        text = _HEADER + "auto_merge:\n  enabled: true\n  gates:\n"
        pyyaml = p9.load_policy_text(text).auto_merge.gates
        minimal = p9._parse_policy(p9._minimal_yaml_load(text)).auto_merge.gates
        assert pyyaml is not None and pyyaml == minimal

    def test_always_review_floor_survives_a_configured_list(self, gates):
        assert ".github/workflows/**" in gates.p20.public_api_paths
        assert "schemas/**" in gates.p20.public_api_paths


class TestAlwaysReview:
    @pytest.mark.parametrize("path", [".github/workflows/merge-gate.yml",
                                      ".claude/settings.json", ".control/preauth.yaml"])
    def test_one_line_control_surface_edit_needs_p20(self, p9, gates, path):
        f = _good(p9, files=[path], additions=1, deletions=1)
        assert "p20" in _failed(p9, gates, f)
        assert _failed(p9, gates, _good(p9, files=[path], comments=[_comment(_marker())])) \
            == set()

    def test_binary_change_needs_p20(self, p9, gates):
        f = _good(p9, files=["assets/x.bin"], additions=0, deletions=0,
                  unmeasured=["assets/x.bin"])
        assert "p20" in _failed(p9, gates, f)


class TestChangeRequestsStand:
    def _r(self, login, state, at):
        return {"author": {"login": login}, "state": state, "submittedAt": at}

    def test_a_later_comment_does_not_withdraw_a_change_request(self, p9, gates):
        f = _good(p9, reviews=[self._r("ana", "CHANGES_REQUESTED", "2026-09-26T10:00:00Z"),
                               self._r("ana", "COMMENTED", "2026-09-26T11:00:00Z")])
        assert "no_changes_requested" in _failed(p9, gates, f)

    @pytest.mark.parametrize("later", ["APPROVED", "DISMISSED"])
    def test_approval_or_dismissal_clears_it(self, p9, gates, later):
        f = _good(p9, reviews=[self._r("ana", "CHANGES_REQUESTED", "2026-09-26T10:00:00Z"),
                               self._r("ana", later, "2026-09-26T11:00:00Z")])
        assert _failed(p9, gates, f) == set()

    def test_another_reviewers_approval_does_not_clear_it(self, p9, gates):
        f = _good(p9, reviews=[self._r("ana", "CHANGES_REQUESTED", "2026-09-26T10:00:00Z"),
                               self._r("bo", "APPROVED", "2026-09-26T11:00:00Z")])
        assert "no_changes_requested" in _failed(p9, gates, f)

    def test_a_change_request_on_page_two_still_blocks(self, p9, gates):
        # gh preloads every page of reviews, so the list is complete: 150
        # reviews do not block by themselves, and one change request among
        # them does.
        many = [self._r(f"u{i}", "COMMENTED", "2026-09-26T10:00:00Z") for i in range(150)]
        assert _failed(p9, gates, _good(p9, reviews=many)) == set()
        late = many + [self._r("ana", "CHANGES_REQUESTED", "2026-09-26T11:00:00Z")]
        assert "no_changes_requested" in _failed(p9, gates, _good(p9, reviews=late))


class TestIndependentCheck:
    def test_only_an_aggregate_and_a_bot_vouch_blocks(self, p9, gates):
        f = _good(p9, all_checks=[{"name": "Merge Gate", "bucket": "pass"},
                                  {"name": "CodeRabbit", "bucket": "pass"}])
        assert "independent_check" in _failed(p9, gates, f)

    def test_a_p20_pass_covers_a_pr_no_ci_ran_on(self, p9, gates):
        f = _good(p9, all_checks=[{"name": "Merge Gate", "bucket": "pass"}],
                  comments=[_comment(_marker())])
        assert _failed(p9, gates, f) == set()

    def test_unreadable_checks_block(self, p9, gates):
        assert "independent_check" in _failed(p9, gates, _good(p9, all_checks=None))


class TestRenames:
    def test_renaming_agents_md_away_stays_governance(self, p9, monkeypatch):
        _seed_merge_ready(p9, 730)
        view = _view(files=[{"path": "docs/AGENTS.md"}, {"path": "src/b.py"}])
        calls = []
        monkeypatch.setattr(p9.subprocess, "run", _fake_gh(
            view, calls=calls, renamed={"docs/AGENTS.md": "AGENTS.md"}))
        rc = p9.main(["auto-merge", "730", "--repo", "broomva/test"])
        assert rc == p9.EXIT_AUTO_MERGE_BLOCKED
        rows, _ = p9.jsonl_read_all(p9.state_jsonl())
        failed = {g["gate"] for g in [r for r in rows if r["pr"] == 730][-1]
                  ["extra"]["auto_merge"]["gates"] if not g["ok"]}
        assert "governance_strata" in failed

    def test_same_pr_without_the_rename_merges(self, p9, monkeypatch):
        _seed_merge_ready(p9, 731)
        view = _view(files=[{"path": "docs/AGENTS.md"}, {"path": "src/b.py"}])
        monkeypatch.setattr(p9.subprocess, "run", _fake_gh(view, calls=[]))
        assert p9.main(["auto-merge", "731", "--repo", "broomva/test"]) == p9.EXIT_OK


class TestHeadConsistency:
    def test_head_moving_between_listing_and_facts_blocks(self, p9, monkeypatch):
        _seed_merge_ready(p9, 732)
        view = _view()
        calls = []
        inner = _fake_gh(view, calls=calls)

        def run(cmd, *a, **k):
            if cmd[:3] == ["gh", "pr", "view"] and "-q" in cmd:
                calls.append(cmd)
                return _Run(json.dumps({"branch": "fix/anything", "head": OLD, "changed": 2}))
            return inner(cmd, *a, **k)
        monkeypatch.setattr(p9.subprocess, "run", run)
        assert p9.main(["auto-merge", "732", "--repo", "broomva/test"]) == \
            p9.EXIT_AUTO_MERGE_BLOCKED
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]


class TestGathering:
    """The half of the gate that talks to GitHub, run against the fake."""

    def test_l3_counter_counts_distinct_governance_commits(self, p9, monkeypatch):
        seen = []

        def run(cmd, *a, **k):
            seen.append(cmd)
            path = next(c.split("=", 1)[1] for c in cmd if c.startswith("path="))
            shas = {"CLAUDE.md": ["s1"], "AGENTS.md": ["s1", "s2"]}.get(path, [])
            return _Run(json.dumps([{"sha": x} for x in shas]))
        monkeypatch.setattr(p9.subprocess, "run", run)
        tier = p9.GovernanceTier()
        assert p9._count_governance_commits("broomva/test", "main", tier) == 2
        assert all("sha=main" in c for c in seen)

    def test_l3_counter_unreadable_is_none(self, p9, monkeypatch):
        monkeypatch.setattr(p9.subprocess, "run", lambda *a, **k: _Run(returncode=1))
        assert p9._count_governance_commits("broomva/test", "main", p9.GovernanceTier()) is None

    def test_governance_pr_merges_end_to_end_only_with_every_strict_condition(
            self, p9, monkeypatch):
        _seed_merge_ready(p9, 733)
        view = _view(files=[{"path": "CLAUDE.md"}, {"path": "src/b.py"}],
                     comments=[_comment(_marker(strata="A,B,C"))])
        checks = [{"name": "Merge Gate", "bucket": "pass"},
                  {"name": "stability-check", "bucket": "pass"}]
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(view, calls=[], all_checks=checks))
        assert p9.main(["auto-merge", "733", "--repo", "broomva/test"]) == p9.EXIT_OK

    def test_carry_forward_is_gathered_from_compare(self, p9, monkeypatch):
        view = _view(comments=[_comment(_marker(sha=OLD))])
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(view, calls=[], compare_files=["docs/other.md"]))
        f = p9.gather_pr_gate_facts(740, "broomva/test",
                                    p9.load_policy(_GATED).auto_merge.gates,
                                    listing=_listing(p9, view))
        assert f.marker_is_ancestor is True and f.marker_delta_files == ["docs/other.md"]

    def test_compare_without_a_files_key_is_unknown(self, p9, monkeypatch):
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda *a, **k: _Run(json.dumps({"status": "ahead"})))
        assert p9._compare_files("broomva/test", f"{OLD}...{HEAD}") == ("ahead", None)

    def test_unknown_merge_state_is_retried(self, p9, monkeypatch):
        view = _view()
        inner = _fake_gh(view, calls=[])
        n = {"views": 0}

        def run(cmd, *a, **k):
            if cmd[:3] == ["gh", "pr", "view"] and "-q" not in cmd:
                n["views"] += 1
                if n["views"] == 1:
                    return _Run(json.dumps(dict(view, mergeStateStatus="UNKNOWN")))
            return inner(cmd, *a, **k)
        monkeypatch.setattr(p9.subprocess, "run", run)
        f = p9.gather_pr_gate_facts(741, "broomva/test",
                                    p9.load_policy(_GATED).auto_merge.gates)
        assert n["views"] == 2 and f.merge_state == "CLEAN"

    def test_more_than_100_threads_is_unknown(self, p9, monkeypatch):
        payload = {"data": {"repository": {"pullRequest": {"reviewThreads": {
            "totalCount": 150, "nodes": [{"isResolved": True}] * 100}}}}}
        monkeypatch.setattr(p9.subprocess, "run", lambda *a, **k: _Run(json.dumps(payload)))
        assert p9._unresolved_review_threads(1, "broomva/test") == -1


class TestBasePolicyResolution:
    @pytest.fixture()
    def unpinned(self, p9, monkeypatch, tmp_path):
        monkeypatch.delenv("BROOMVA_P9_POLICY", raising=False)
        monkeypatch.chdir(tmp_path)
        return p9

    def test_missing_base_ref_is_not_a_missing_policy(self, unpinned, monkeypatch):
        p9 = unpinned
        local = p9.load_policy(_GATED).auto_merge
        monkeypatch.setattr(p9.subprocess, "run", lambda *a, **k: _Run(
            stderr="gh: No commit found for the ref gone (HTTP 404)", returncode=1))
        am, why = p9.authoritative_auto_merge_policy(local, "broomva/test", "gone", [])
        assert am is None and "unreadable" in why

    def test_ref_is_url_encoded(self, unpinned, monkeypatch):
        p9 = unpinned
        seen = []
        monkeypatch.setattr(p9.subprocess, "run", lambda cmd, *a, **k: (
            seen.append(cmd), _Run(stderr="gh: Not Found (HTTP 404)", returncode=1))[1])
        p9.authoritative_auto_merge_policy(p9.load_policy(_GATED).auto_merge,
                                           "broomva/test", "rel/x#y&z", [])
        assert any("ref=rel%2Fx%23y%26z" in c for c in seen[0])

    def test_unpinned_auto_merge_is_judged_by_the_base_policy(self, unpinned, monkeypatch):
        # The checkout has no policy at all; the base branch's gated one rules.
        p9 = unpinned
        policy_file = Path("policy.yaml")
        policy_file.write_text(_GATED.read_text())
        monkeypatch.setattr(p9, "load_policy", lambda *a, **k: p9.load_policy_text(
            policy_file.read_text()))
        _seed_merge_ready(p9, 742)
        calls = []
        monkeypatch.setattr(p9.subprocess, "run", _fake_gh(
            _view(), calls=calls, base_policy=_GATED.read_text()))
        assert p9.main(["auto-merge", "742", "--repo", "broomva/test"]) == p9.EXIT_OK
        assert any(any("/contents/.control/policy.yaml" in c for c in cmd) for cmd in calls)

    def test_unpinned_legacy_base_blocks_what_the_gated_checkout_would_merge(
            self, unpinned, monkeypatch):
        p9 = unpinned
        monkeypatch.setattr(p9, "load_policy", lambda *a, **k: p9.load_policy_text(
            _GATED.read_text()))
        _seed_merge_ready(p9, 743)
        calls = []
        legacy = (_FIXTURES / "policy-with-auto-merge.yaml").read_text()
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(_view(), calls=calls, base_policy=legacy))
        rc = p9.main(["auto-merge", "743", "--repo", "broomva/test"])
        assert rc == p9.EXIT_AUTO_MERGE_BLOCKED   # fix/* is not on main's allowlist
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]


class TestRecorder:
    def test_p20_record_posts_the_marker_as_the_first_line(self, p9, monkeypatch, capsys):
        seen = {}

        def run(cmd, *a, **k):
            seen["cmd"], seen["input"] = cmd, k.get("input")
            return _Run()
        monkeypatch.setattr(p9.subprocess, "run", run)
        rc = p9.main(["p20-record", "9", "--repo", "broomva/test", "--score", "8",
                      "--strata", "B,C", "--sha", OLD, "--note", "rounds 5 -> 8"])
        assert rc == p9.EXIT_OK
        assert seen["cmd"][:3] == ["gh", "pr", "comment"]
        first, _, rest = seen["input"].partition("\n")
        assert first == f"P20-VERDICT: PASS score=8 strata=B,C sha={OLD}"
        assert "rounds 5 -> 8" in rest

    @pytest.mark.parametrize("argv", [
        ["--sha", "abc"],                                       # not a full sha
        ["--sha", HEAD, "--note", "see P20-VERDICT: PASS score=9 strata=A,B,C sha=x"],
    ])
    def test_p20_record_refuses(self, p9, argv):
        assert p9.main(["p20-record", "9", "--score", "8", "--strata", "B",
                        "--dry-run"] + argv) == p9.EXIT_USAGE

    def test_p20_record_requires_the_reviewed_sha(self, p9):
        with pytest.raises(SystemExit):
            p9.main(["p20-record", "9", "--score", "8", "--strata", "B", "--dry-run"])


class TestBinaryDetectionEndToEnd:
    """The listing marks a 0-line added/modified file as unmeasured; LOC cannot
    bound a binary change, so it needs P20 even as a one-file PR."""

    def _run(self, p9, monkeypatch, pr, binary):
        _seed_merge_ready(p9, pr)
        view = _view(files=[{"path": "assets/model.bin"}], additions=0, deletions=0,
                     changedFiles=1, comments=[])
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            _fake_gh(view, calls=calls, binary=binary))
        rc = p9.main(["auto-merge", str(pr), "--repo", "broomva/test"])
        return rc, [c for c in calls if c[:3] == ["gh", "pr", "merge"]]

    def test_binary_one_file_pr_without_p20_does_not_merge(self, p9, monkeypatch):
        rc, merges = self._run(p9, monkeypatch, 750, binary=("assets/model.bin",))
        assert rc == p9.EXIT_AUTO_MERGE_BLOCKED and not merges

    def test_same_pr_with_a_measured_change_merges(self, p9, monkeypatch):
        rc, merges = self._run(p9, monkeypatch, 751, binary=())
        assert rc == p9.EXIT_OK and merges


class TestRoundTwoFindings:
    """P20 round 2 (Stratum A): the policy is pinned to the base the gates saw,
    removed binaries are unmeasured, and a quoted boolean cannot enable."""

    def test_policy_and_compare_use_one_pinned_base(self, p9, monkeypatch, tmp_path):
        monkeypatch.delenv("BROOMVA_P9_POLICY", raising=False)
        monkeypatch.chdir(tmp_path)
        calls = []
        monkeypatch.setattr(p9.subprocess, "run", _fake_gh(
            _view(), calls=calls, base_policy=_GATED.read_text()))
        d = p9.decide_auto_merge(p9.load_policy(_GATED).auto_merge, pr=760,
                                 repo="broomva/test", listing=_listing(p9, _view()))
        assert d["action"] == "auto" and d["base_sha"] == BASE
        flat = [" ".join(c) for c in calls]
        assert any(f"contents/.control/policy.yaml?ref={BASE}" in c for c in flat)
        assert any(f"compare/{BASE}...{HEAD}" in c for c in flat)
        assert not any("compare/main..." in c for c in flat)

    def test_listing_marks_every_zero_line_row_including_renames(self, p9, monkeypatch):
        rows = ("assets/old.bin\t\tremoved\t0\n"
                "docs/moved.md\tdocs/was.md\trenamed\t0\n"
                "assets/new.bin\t\tadded\t0\n"
                "src/a.py\t\tmodified\t7\n")

        def run(cmd, *a, **k):
            if cmd[:3] == ["gh", "pr", "view"]:
                return _Run(json.dumps({"branch": "b", "head": HEAD, "changed": 4}))
            return _Run(rows)
        monkeypatch.setattr(p9.subprocess, "run", run)
        listing = p9._gh_pr_listing(770, "broomva/test")
        assert listing.unmeasured == ("assets/old.bin", "docs/moved.md", "assets/new.bin")
        assert "docs/was.md" in listing.paths

    @pytest.mark.parametrize("value", ['"false"', "'false'", '"true"', "1", "yes-please"])
    def test_a_non_boolean_enabled_is_rejected_by_both_loaders(self, p9, value):
        # bool("false") is True, so every loader must REJECT a non-boolean flag.
        # CI runs without PyYAML (the minimal loader), so both are tested here.
        text = _HEADER + f"auto_merge:\n  enabled: {value}\n  gates:\n    p20:\n      pass_score: 7\n"
        loaders = [("minimal", lambda t: p9._parse_policy(p9._minimal_yaml_load(t)))]
        try:
            import yaml
            loaders.append(("pyyaml", lambda t: p9._parse_policy(yaml.safe_load(t))))
        except ImportError:
            pass
        for name, load in loaders:
            with pytest.raises(p9.PolicyError) as e:
                load(text)
            assert "enabled" in str(e.value), name


class TestRoundThreeFindings:
    """P20 round 3 (Stratum B): the production pre-merge re-check, retargeting,
    and an encoded branch name."""

    def _unpinned(self, p9, monkeypatch, tmp_path, *, branch_shas, bases):
        monkeypatch.delenv("BROOMVA_P9_POLICY", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(p9, "load_policy", lambda *a, **k: p9.load_policy_text(
            _GATED.read_text()))
        calls = []
        inner = _fake_gh(_view(), calls=calls, base_policy=_GATED.read_text())
        shas, base_names = iter(branch_shas), iter(bases)

        def run(cmd, *a, **k):
            if cmd[:2] == ["gh", "api"] and any("/branches/" in c for c in cmd):
                calls.append(cmd)
                return _Run(json.dumps({"commit": {"sha": next(shas)}}))
            if cmd[:3] == ["gh", "pr", "view"] and cmd[-1] == "baseRefName":
                calls.append(cmd)
                return _Run(json.dumps({"baseRefName": next(base_names)}))
            return inner(cmd, *a, **k)
        monkeypatch.setattr(p9.subprocess, "run", run)
        return calls

    def test_base_moving_after_the_pin_blocks_on_the_production_path(
            self, p9, monkeypatch, tmp_path):
        _seed_merge_ready(p9, 780)
        calls = self._unpinned(p9, monkeypatch, tmp_path,
                               branch_shas=[BASE, "f" * 40], bases=["main", "main"])
        assert p9.main(["auto-merge", "780", "--repo", "broomva/test"]) == \
            p9.EXIT_AUTO_MERGE_BLOCKED
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]

    def test_steady_base_merges_on_the_production_path(self, p9, monkeypatch, tmp_path):
        _seed_merge_ready(p9, 781)
        calls = self._unpinned(p9, monkeypatch, tmp_path,
                               branch_shas=[BASE, BASE], bases=["main", "main"])
        assert p9.main(["auto-merge", "781", "--repo", "broomva/test"]) == p9.EXIT_OK
        assert [c for c in calls if c[:3] == ["gh", "pr", "merge"]]

    def test_retargeted_pr_blocks(self, p9, monkeypatch, tmp_path):
        _seed_merge_ready(p9, 782)
        calls = self._unpinned(p9, monkeypatch, tmp_path,
                               branch_shas=[BASE, BASE], bases=["main", "release"])
        assert p9.main(["auto-merge", "782", "--repo", "broomva/test"]) == \
            p9.EXIT_AUTO_MERGE_BLOCKED
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]

    def test_branch_name_is_url_encoded(self, p9, monkeypatch):
        seen = []
        monkeypatch.setattr(p9.subprocess, "run", lambda cmd, *a, **k: (
            seen.append(cmd), _Run(json.dumps({"commit": {"sha": BASE}})))[1])
        assert p9._gh_branch_sha("broomva/test", "main#x") == BASE
        assert seen[0][-1] == "repos/broomva/test/branches/main%23x"
