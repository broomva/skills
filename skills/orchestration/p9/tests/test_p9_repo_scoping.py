"""BRO-1988 — `(repo, pr)` is the identity; the PR number alone is not.

Reproduced live 2026-07-26 against the real state store:

  1. **Foreign-repo PR consumed the global concurrency slot.**
     `p9 watch 50 --repo broomva/skills --background` refused with
     `max_concurrent_prs=1 already in flight` because an open PR in
     `GetStimulus/sri` held the only slot.

  2. **Lifecycle state shadowed across repos.**
     `p9 merge-ready 256` answered `PR #256 not GREEN (current=ABANDONED)`
     for `broomva/workspace#256` — freshly created, 3/3 checks green,
     MERGEABLE/CLEAN — because `GetStimulus/sri#256` (ABANDONED) owned that
     state key. Since `watch` is the only transition into GREEN and (1)
     blocked it, `watch → merge-ready → auto-merge` became unreachable.

These tests construct two same-numbered PRs in two repos and pin: watching
one does not block the other, neither one's lifecycle state is visible as
the other's, and legacy bare-number rows migrate rather than crashing or
vanishing.
"""

from __future__ import annotations

import importlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
_FIXTURES = _HERE / "fixtures"
sys.path.insert(0, str(_SCRIPTS))

# The two repos from the live reproduction.
SRI = "GetStimulus/sri"
WORKSPACE = "broomva/workspace"
SKILLS = "broomva/skills"


AMBIENT = "broomva/ambient"


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    """Fresh p9 with tmpdir state and max_concurrent_prs=1.

    The ambient repo is pinned to a REAL repo that is deliberately *unrelated*
    to every repo under test, so nothing here can pass by accidentally being
    the ambient one — and so the suite runs in the regime production runs in.
    Tests that need "no repo at all" set the explicit `-` sentinel themselves.
    """
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    monkeypatch.setenv("BROOMVA_P9_REPO", AMBIENT)
    monkeypatch.delenv("BROOMVA_P9_SESSION", raising=False)
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


@pytest.fixture()
def no_probe(monkeypatch):
    """Fail loudly if anything shells out. Repo resolution must not reach the
    network on paths that claim not to."""
    def boom(cmd, *a, **k):  # pragma: no cover - the assertion is the point
        raise AssertionError(f"unexpected subprocess: {cmd}")
    import p9 as _p9
    monkeypatch.setattr(_p9.subprocess, "run", boom)


def _event(p9, pr, repo, prev, curr, *, session_id="A", **extra):
    p9.append_state_event(p9.PRStateEvent(
        ts=extra.pop("ts", None) or p9._utcnow(), pr=pr, repo=repo,
        from_state=prev.value, to_state=curr.value,
        watcher_id=f"w{pr}", session_id=session_id, extra=extra,
    ))


def _watching(p9, pr, repo, *, session_id="A", pid=0, ts=None):
    _event(p9, pr, repo, p9.PRState.PUSHED, p9.PRState.WATCHING,
           session_id=session_id, pid=pid, ts=ts)


def _green(p9, pr, repo, *, session_id="A"):
    _watching(p9, pr, repo, session_id=session_id)
    _event(p9, pr, repo, p9.PRState.WATCHING, p9.PRState.GREEN,
           session_id=session_id)


def _raw_rows(p9):
    return [json.loads(line) for line
            in p9.state_jsonl().read_text(encoding="utf-8").splitlines()
            if line.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Repo resolution — deterministic and testable, one answer per invocation
# ─────────────────────────────────────────────────────────────────────────────
class TestRepoResolution:
    def test_explicit_flag_beats_everything(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_REPO", SRI)
        assert p9.resolve_repo(WORKSPACE) == WORKSPACE

    def test_env_pins_resolution(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.resolve_repo() == WORKSPACE

    def test_sentinel_pins_no_repo_without_probing(self, p9, monkeypatch, no_probe):
        """`-` means "no repo", NOT "go ask gh"."""
        monkeypatch.setenv("BROOMVA_P9_REPO", p9.REPO_NONE_SENTINEL)
        assert p9.resolve_repo() == ""

    def test_empty_env_means_unset_not_repo_less(self, p9, monkeypatch):
        """NIT-8. A wrapper doing `export BROOMVA_P9_REPO=$(cmd_that_failed)`
        must degrade to normal detection, not silently drop into repo-less
        state with a global ceiling and no diagnostic. Shell convention:
        empty == unset."""
        monkeypatch.setenv("BROOMVA_P9_REPO", "")
        monkeypatch.setattr(p9, "_detect_repo_uncached", lambda: SKILLS)
        assert p9.resolve_repo() == SKILLS

    @pytest.mark.parametrize("raw", [
        "broomva/workspace",
        "  broomva/workspace  ",
        "broomva/workspace/",
        "https://github.com/broomva/workspace",
        "https://github.com/broomva/workspace.git",
        "http://github.com/broomva/workspace",
        "git@github.com:broomva/workspace.git",
        "ssh://git@github.com/broomva/workspace.git",
        "https://github.com/broomva/workspace/pull/5",
    ])
    def test_canonicalizes_every_spelling(self, p9, raw):
        assert p9.canonical_repo(raw) == WORKSPACE

    def test_non_github_hosts_stay_distinct(self, p9):
        """MAJOR-2. A github.com-only prefix allowlist left the scheme+host in
        place, so `split("/")[:2]` returned `https:/<host>` and EVERY repo on
        a GHE/GitLab host collapsed to one key — BRO-1988 again, host-wide.
        Reachable via the `git remote get-url` fallback this PR added, and
        `gh` supports GHE through `GH_HOST`."""
        a = p9.canonical_repo("https://github.mycorp.com/teamA/repo1")
        b = p9.canonical_repo("https://github.mycorp.com/teamB/repo2")
        assert (a, b) == ("teamA/repo1", "teamB/repo2")
        c = p9.canonical_repo("https://gitlab.com/a/b")
        d = p9.canonical_repo("git@gitlab.com:c/d.git")
        assert (c, d) == ("a/b", "c/d")
        assert len({p9.repo_key(x) for x in (a, b, c, d)}) == 4

    def test_ghe_rows_do_not_shadow_each_other(self, p9):
        """The same collapse, end to end: two GHE repos, same PR number."""
        _watching(p9, 42, "https://github.mycorp.com/teamA/repo1")
        _green(p9, 42, "https://github.mycorp.com/teamB/repo2")
        assert p9.current_pr_state(42, "teamA/repo1") == p9.PRState.WATCHING
        assert p9.current_pr_state(42, "teamB/repo2") == p9.PRState.GREEN
        assert len(p9.open_prs()) == 2

    @pytest.mark.parametrize("raw, expected", [
        ("weird", "weird"),           # 1 segment: kept, never aliased onto ""
        ("https://github.com/", ""),  # 0 segments: nothing left to keep
        ("/", ""),
        ("//", ""),
        ("   ", ""),
        ("", ""),
        (None, ""),
    ])
    def test_canonical_repo_boundaries(self, p9, raw, expected):
        """MAJOR-2, second defect: the docstring claimed odd values are *never*
        collapsed to "", but `https://github.com/`, `/` and `//` all were, and
        the old test only probed `"weird"`. Pin the real contract."""
        assert p9.canonical_repo(raw) == expected

    def test_odd_repo_values_are_kept_not_collapsed(self, p9):
        """A single-segment value must survive. Collapsing it to "" would
        alias it onto the legacy no-repo key and erase its identity."""
        assert p9.repo_key("weird") == "weird"
        assert p9.repo_key("weird") != p9.repo_key("")
        _watching(p9, 7, "weird")
        assert [r["repo"] for r in _raw_rows(p9)] == ["weird"]
        assert p9.current_pr_state(7, "weird") == p9.PRState.WATCHING
        assert p9.current_pr_state(7, "") is None

    def test_unusable_explicit_repo_warns(self, p9, capsys):
        """Silence is how a garbage `--repo` becomes an invisible slide into
        repo-less state."""
        assert p9.resolve_repo("https://github.com/") == ""
        assert "does not reduce to OWNER/REPO" in capsys.readouterr().err

    def test_unusable_env_repo_warns(self, p9, monkeypatch, capsys):
        monkeypatch.setenv("BROOMVA_P9_REPO", "/")
        assert p9.resolve_repo() == ""
        assert "does not reduce to OWNER/REPO" in capsys.readouterr().err

    def test_repo_key_is_case_insensitive(self, p9):
        assert p9.repo_key("GetStimulus/SRI") == p9.repo_key("getstimulus/sri")
        assert p9.repo_key(SRI) != p9.repo_key(WORKSPACE)

    def test_state_rows_are_stored_canonical(self, p9):
        """Normalize on write, not just on compare: `row["repo"]` is handed
        straight to `gh --repo`, and it is what `p9 status` prints."""
        _watching(p9, 42, "https://github.com/broomva/workspace.git")
        assert [r["repo"] for r in _raw_rows(p9)] == [WORKSPACE]

    def test_case_variant_reads_the_same_state(self, p9):
        """GitHub owner/name are case-insensitive; two spellings must not
        split one logical repo into two keys (that would strand state)."""
        _watching(p9, 42, "GetStimulus/sri")
        assert p9.current_pr_state(42, "getstimulus/SRI") == p9.PRState.WATCHING

    def test_detection_falls_back_to_git_remote(self, p9, monkeypatch):
        monkeypatch.delenv("BROOMVA_P9_REPO", raising=False)
        calls = []

        class _R:
            def __init__(self, rc, out=""):
                self.returncode, self.stdout, self.stderr = rc, out, ""

        def fake(cmd, *a, **k):
            calls.append(cmd)
            if cmd[:2] == ["gh", "repo"]:
                return _R(1)  # gh present but unauthenticated
            if cmd[:3] == ["git", "remote", "get-url"]:
                return _R(0, "git@github.com:broomva/skills.git\n")
            return _R(1)

        monkeypatch.setattr(p9.subprocess, "run", fake)
        assert p9.resolve_repo() == SKILLS
        assert ["git", "remote", "get-url", "origin"] in calls

    def test_detection_is_memoized_per_process(self, p9, monkeypatch):
        """One invocation must never resolve two different answers — the write
        key and the read key have to agree."""
        monkeypatch.delenv("BROOMVA_P9_REPO", raising=False)
        n = {"calls": 0}

        class _R:
            returncode, stdout, stderr = 0, "broomva/skills\n", ""

        def fake(cmd, *a, **k):
            n["calls"] += 1
            return _R()

        monkeypatch.setattr(p9.subprocess, "run", fake)
        assert p9.resolve_repo() == SKILLS
        assert p9.resolve_repo() == SKILLS
        assert p9.resolve_repo() == SKILLS
        assert n["calls"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Effect 1 — a foreign repo's PR must not consume the concurrency slot
# ─────────────────────────────────────────────────────────────────────────────
class TestCrossRepoConcurrency:
    def test_foreign_repo_row_does_not_hold_the_slot(self, p9):
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")  # max=1
        _watching(p9, 307, SRI, session_id="A")
        # Same session, different repo → must not raise.
        p9.enforce_concurrency_ceiling(cfg, session_id="A", repo=SKILLS)

    def test_same_repo_still_blocks(self, p9):
        """The ceiling is scoped, not deleted."""
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
        _watching(p9, 49, SKILLS, session_id="A")
        with pytest.raises(p9.ConcurrencyCeilingError):
            p9.enforce_concurrency_ceiling(cfg, session_id="A", repo=SKILLS)

    def test_watch_cli_not_blocked_by_other_repo(self, p9, monkeypatch):
        """The exact refusal from the live repro: an open GetStimulus/sri PR
        must not refuse `p9 watch 50 --repo broomva/skills`."""
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        _watching(p9, 307, SRI, session_id="A")
        rc = p9.main(["watch", "50", "--repo", SKILLS, "--dry-run"])
        assert rc == p9.EXIT_OK
        assert p9.current_pr_state(50, SKILLS) == p9.PRState.WATCHING
        # Both are in flight, under their own keys.
        assert {(r["repo"], r["pr"]) for r in p9.open_prs()} == {
            (SRI, 307), (SKILLS, 50)}

    def test_watch_cli_still_blocked_within_a_repo(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        _watching(p9, 49, SKILLS, session_id="A")
        rc = p9.main(["watch", "50", "--repo", SKILLS, "--dry-run"])
        assert rc == p9.EXIT_CONCURRENCY_CEILING

    def test_unresolvable_repo_falls_back_to_the_global_ceiling(self, p9, monkeypatch):
        """With no repo, identity is ambiguous — the ceiling must degrade to
        the cross-repo count, not vanish."""
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        monkeypatch.setenv("BROOMVA_P9_REPO", p9.REPO_NONE_SENTINEL)
        _watching(p9, 307, SRI, session_id="A")
        assert p9.main(["watch", "50", "--dry-run"]) == p9.EXIT_CONCURRENCY_CEILING

    def test_same_number_two_repos_both_watchable(self, p9, monkeypatch):
        """Two same-numbered PRs in different repos: watching one does not
        block watching the other."""
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        assert p9.main(["watch", "256", "--repo", SRI, "--dry-run"]) == p9.EXIT_OK
        assert p9.main(
            ["watch", "256", "--repo", WORKSPACE, "--dry-run"]) == p9.EXIT_OK
        assert len(p9.open_prs()) == 2

    def test_live_watcher_dedup_is_repo_scoped(self, p9, monkeypatch):
        """A live watcher on repo A's #42 must not refuse repo B's #42."""
        import os
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        _watching(p9, 42, SRI, session_id="A", pid=os.getpid())  # alive
        assert p9.main(
            ["watch", "42", "--repo", WORKSPACE, "--dry-run"]) == p9.EXIT_OK


# ─────────────────────────────────────────────────────────────────────────────
# Effect 2 — lifecycle state must not be shadowed across repos
# ─────────────────────────────────────────────────────────────────────────────
def _seed_shadow(p9):
    """The live shape: workspace#256 is freshly GREEN, and `GetStimulus/sri`
    #256 walked to ABANDONED.

    Row ORDER is load-bearing, and getting it wrong makes every assertion
    below vacuous: a bare-number read returns the *last* row for that number,
    so the foreign repo's terminal events must land last — exactly as they did
    live, where sri#256 was driven to ABANDONED while workspace#256 sat green
    and unwatchable. Seed the shadow first and a bare read accidentally
    answers correctly.
    """
    _green(p9, 256, WORKSPACE)
    _green(p9, 256, SRI)
    _event(p9, 256, SRI, p9.PRState.GREEN, p9.PRState.MERGE_READY)
    _event(p9, 256, SRI, p9.PRState.MERGE_READY, p9.PRState.ABANDONED)


class TestCrossRepoLifecycle:
    def test_state_reads_are_repo_scoped(self, p9):
        _seed_shadow(p9)
        assert p9.current_pr_state(256, SRI) == p9.PRState.ABANDONED
        assert p9.current_pr_state(256, WORKSPACE) == p9.PRState.GREEN

    def test_merge_ready_not_shadowed_by_foreign_repo(self, p9):
        """The reproduced wedge: `p9 merge-ready 256` said
        `not GREEN (current=ABANDONED)` for a green workspace#256."""
        _seed_shadow(p9)
        rc = p9.main(["merge-ready", "256", "--repo", WORKSPACE, "--no-verify"])
        assert rc == p9.EXIT_OK
        assert p9.current_pr_state(256, WORKSPACE) == p9.PRState.MERGE_READY
        # The foreign repo's terminal state is untouched.
        assert p9.current_pr_state(256, SRI) == p9.PRState.ABANDONED

    def test_merge_ready_without_flag_uses_resolved_repo(self, p9, monkeypatch):
        """No `--repo`: resolution must be deterministic and still repo-scoped."""
        _seed_shadow(p9)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.main(["merge-ready", "256", "--no-verify"]) == p9.EXIT_OK
        assert p9.current_pr_state(256, WORKSPACE) == p9.PRState.MERGE_READY

    def test_merge_ready_writes_the_key_it_read(self, p9):
        _seed_shadow(p9)
        p9.main(["merge-ready", "256", "--repo", WORKSPACE, "--no-verify"])
        promoted = [r for r in _raw_rows(p9) if r["to_state"] == "MERGE_READY"]
        assert [r["repo"] for r in promoted] == [SRI, WORKSPACE]

    def test_merge_ready_still_refuses_a_non_green_pr(self, p9):
        """Scoping must not turn the gate off."""
        _watching(p9, 256, WORKSPACE)
        rc = p9.main(["merge-ready", "256", "--repo", WORKSPACE, "--no-verify"])
        assert rc == p9.EXIT_DEGRADED

    def test_merge_ready_refuses_a_pr_it_has_no_state_for(self, p9):
        """The other direction of the same shadow: a foreign repo's GREEN
        #256 must never promote a PR this repo has never watched."""
        _green(p9, 256, SRI)
        rc = p9.main(["merge-ready", "256", "--repo", WORKSPACE, "--no-verify"])
        assert rc == p9.EXIT_DEGRADED
        assert p9.current_pr_state(256, WORKSPACE) is None
        assert p9.current_pr_state(256, SRI) == p9.PRState.GREEN

    def test_abandon_is_repo_scoped(self, p9):
        _seed_shadow(p9)
        assert p9.main(["abandon", "256", "--repo", WORKSPACE]) == p9.EXIT_OK
        assert p9.current_pr_state(256, WORKSPACE) == p9.PRState.ABANDONED
        # sri#256 was already terminal and gained no new row.
        assert len([r for r in _raw_rows(p9)
                    if r["repo"] == SRI and r["to_state"] == "ABANDONED"]) == 1

    def test_abandon_never_writes_an_orphan_row(self, p9, monkeypatch):
        """Read key and write key must be the same. Reading bare-number while
        writing repo-qualified folded a terminal row under a key nothing
        tracks and left the real row open forever."""
        _watching(p9, 600, WORKSPACE)
        monkeypatch.setenv("BROOMVA_P9_REPO", SRI)  # resolution says elsewhere
        assert p9.main(["abandon", "600"]) == p9.EXIT_DEGRADED
        # No row was written under the wrong repo, and #600 is still in flight.
        assert [r["repo"] for r in _raw_rows(p9)] == [WORKSPACE]
        assert p9.current_pr_state(600, WORKSPACE) == p9.PRState.WATCHING

    def test_auto_merge_refuses_on_a_foreign_repos_merge_ready(self, p9, monkeypatch):
        """The worst shadowing outcome would be merging the wrong PR. Foreign
        MERGE_READY rows land LAST so a bare-number read would say "go"."""
        monkeypatch.setenv("BROOMVA_P9_POLICY",
                           str(_FIXTURES / "policy-with-auto-merge.yaml"))
        _watching(p9, 300, WORKSPACE)  # same number, NOT merge-ready
        _green(p9, 300, SRI)
        _event(p9, 300, SRI, p9.PRState.GREEN, p9.PRState.MERGE_READY)

        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda cmd, *a, **k: calls.append(cmd))
        rc = p9.main(["auto-merge", "300", "--repo", WORKSPACE])
        assert rc == p9.EXIT_DEGRADED
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]
        assert p9.current_pr_state(300, SRI) == p9.PRState.MERGE_READY

    def test_auto_merge_proceeds_on_its_own_merge_ready(self, p9, monkeypatch):
        """And the converse: a foreign repo's terminal #300 must not veto a
        legitimately merge-ready workspace#300."""
        monkeypatch.setenv("BROOMVA_P9_POLICY",
                           str(_FIXTURES / "policy-with-auto-merge.yaml"))
        _green(p9, 300, WORKSPACE)
        _event(p9, 300, WORKSPACE, p9.PRState.GREEN, p9.PRState.MERGE_READY)
        _green(p9, 300, SRI)
        _event(p9, 300, SRI, p9.PRState.GREEN, p9.PRState.ABANDONED)  # lands last

        calls = []

        class _R:
            def __init__(self, stdout="", rc=0):
                self.stdout, self.stderr, self.returncode = stdout, "", rc

        def fake(cmd, *a, **k):
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "view"]:
                return _R(json.dumps({"branch": "docs/x", "files": ["docs/y.md"]}))
            return _R()

        monkeypatch.setattr(p9.subprocess, "run", fake)
        assert p9.main(["auto-merge", "300", "--repo", WORKSPACE]) == p9.EXIT_OK
        assert [c for c in calls if c[:3] == ["gh", "pr", "merge"]]
        assert p9.current_pr_state(300, WORKSPACE) == p9.PRState.MERGED

    def test_report_filter_is_repo_scoped(self, p9, capsys):
        _seed_shadow(p9)
        assert p9.main(["report", "--repo", WORKSPACE, "--json"]) == p9.EXIT_OK
        reports = json.loads(capsys.readouterr().out)["reports"]
        assert [(r["pr"], r["repo"], r["state"]) for r in reports] == [
            (256, WORKSPACE, "GREEN")]


# ─────────────────────────────────────────────────────────────────────────────
# Legacy bare-number state — migrate, never crash, never discard
# ─────────────────────────────────────────────────────────────────────────────
def _write_legacy(p9, pr, to_state="WATCHING", *, session_id=""):
    """A pre-BRO-1988 row: keyed by bare PR number, no repo."""
    row = {"ts": "2026-05-05T17:46:39+00:00", "pr": pr, "repo": "",
           "from_state": "PUSHED", "to_state": to_state,
           "watcher_id": "legacy", "attempt": 0, "evaluator_score": None,
           "extra": {"pid": 20307}, "session_id": session_id}
    p9.jsonl_append(p9.state_jsonl(), json.dumps(row), p9.state_lock_path())
    return row


class TestLegacyStateIsKeptNotGuessed:
    """A bare-number legacy row keeps ``repo == ""`` — its true identity.

    Round 2 attributed such rows to the ambient repo and persisted the guess.
    Three separate defects came out of that one decision (a live merge hazard
    in `rearm`, state shadowing that recreated BRO-1988's own symptom, and a
    `gh repo view` on the read path), so the guess is gone. Nothing is
    discarded — only invented.
    """

    def test_legacy_row_keeps_its_own_key(self, p9):
        _write_legacy(p9, 36)
        assert p9.current_pr_state(36, "") == p9.PRState.WATCHING
        assert [(r["repo"], r["pr"]) for r in p9.open_prs()] == [("", 36)]

    def test_no_repo_is_ever_invented(self, p9, monkeypatch):
        """Not on read, not at CLI entry, not on write."""
        _write_legacy(p9, 36)
        before = p9.state_jsonl().read_text(encoding="utf-8")
        assert p9.main(["status", "--no-reap", "--json"]) == p9.EXIT_OK
        assert p9.state_jsonl().read_text(encoding="utf-8") == before
        assert _raw_rows(p9)[0]["repo"] == ""

    def test_legacy_row_does_not_shadow_a_real_same_numbered_pr(self, p9):
        """MAJOR-A. The ambient repo genuinely has PR 36, GREEN. A repo-less
        row for the same number must not take over that key and mask it —
        that is BRO-1988's own symptom, recreated by the guess, and it was a
        regression against main."""
        _green(p9, 36, AMBIENT)
        _write_legacy(p9, 36)          # lands last: last-wins would mask GREEN
        assert p9.current_pr_state(36, AMBIENT) == p9.PRState.GREEN
        assert p9.current_pr_state(36, "") == p9.PRState.WATCHING
        assert p9.main(["merge-ready", "36", "--repo", AMBIENT,
                        "--no-verify"]) == p9.EXIT_OK

    def test_legacy_row_never_holds_a_real_repos_slot(self, p9, monkeypatch):
        """Keeping "" as the key is what makes this true: a repo-scoped
        ceiling simply never counts it against a named repo."""
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        _write_legacy(p9, 36, session_id="A")
        assert p9.main(["watch", "50", "--repo", SKILLS,
                        "--dry-run"]) == p9.EXIT_OK

    def test_legacy_in_flight_state_is_not_discarded(self, p9):
        _write_legacy(p9, 36)
        p9.main(["status", "--no-reap"])
        row = _raw_rows(p9)[0]
        assert row["to_state"] == "WATCHING"
        assert row["extra"] == {"pid": 20307}
        assert row["watcher_id"] == "legacy"

    def test_reads_never_resolve_a_repo(self, p9, no_probe):
        """MINOR-5. `gh repo view` is a network call with a 10s timeout; it
        must not sit on the path of listing rows. `no_probe` makes any
        subprocess an error."""
        _watching(p9, 42, WORKSPACE)
        _write_legacy(p9, 36)
        assert p9.current_pr_state(42, WORKSPACE) == p9.PRState.WATCHING
        assert len(p9.open_prs()) == 2
        assert p9.latest_row(42, WORKSPACE) is not None

    def test_cli_entry_never_resolves_a_repo(self, p9, no_probe):
        """MINOR-5, the other half: the entry pass is repo-free, so even a
        read-only command on a store with legacy rows stays offline."""
        _write_legacy(p9, 36)
        assert p9.main(["status", "--no-reap", "--json"]) == p9.EXIT_OK


class TestCorruptionQuarantine:
    """MAJOR-3. `jsonl_read_all` tolerates a torn LAST line but raises on
    mid-file corruption, so a torn tail is a time bomb: one append later it is
    no longer last and every read wedges."""

    def _torn(self, p9):
        _watching(p9, 36, WORKSPACE)
        with p9.state_jsonl().open("a", encoding="utf-8") as f:
            f.write('{"ts":"par')

    def test_torn_line_is_moved_out_and_the_log_reads_back(self, p9):
        self._torn(p9)
        assert p9.quarantine_corrupt_state_lines() == 1
        assert p9.state_corrupt_path().read_text(encoding="utf-8") == '{"ts":"par\n'
        assert '{"ts":"par' not in p9.state_jsonl().read_text(encoding="utf-8")
        # The whole point: append afterwards and the log still reads.
        _watching(p9, 99, WORKSPACE)
        rows, dropped = p9.jsonl_read_all(p9.state_jsonl())
        assert dropped == 0 and len(rows) == 2
        assert p9.current_pr_state(99, WORKSPACE) == p9.PRState.WATCHING

    def test_quarantine_is_written_before_the_log_is_replaced(
            self, p9, tmp_path, monkeypatch):
        """M-F2. Ordering is what makes it crash-safe: if preserving the line
        fails we must abort with the log untouched, not drop it.

        The failure is injected narrowly — the quarantine path is pointed at a
        location whose parent is a regular file, so `mkdir` raises. (Patching
        `Path.open` globally and calling `monkeypatch.undo()` would also revert
        the fixture's BROOMVA_P9_HOME and send the assertion at the real state
        store; resolve the path once, up front, and never re-derive it.)
        """
        self._torn(p9)
        state_path = p9.state_jsonl()
        before = state_path.read_text(encoding="utf-8")
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory", encoding="utf-8")
        monkeypatch.setattr(p9, "state_corrupt_path",
                            lambda: blocker / "state.jsonl.corrupt")
        assert p9.quarantine_corrupt_state_lines() == 0
        # Log untouched — the torn line is still there, nothing was dropped.
        assert state_path.read_text(encoding="utf-8") == before
        assert '{"ts":"par' in before

    def test_temp_file_is_fsynced_before_the_rename(self, p9, monkeypatch):
        """M-N. `write` + `replace` is atomic for visibility, not durability."""
        self._torn(p9)
        synced = []
        monkeypatch.setattr(p9.os, "fsync", lambda fd: synced.append(fd))
        replaced = []
        real_replace = p9.os.replace

        def spy_replace(src, dst):
            # At the moment of the rename, the temp file must already be
            # fsynced (2 syncs: quarantine file, then temp).
            replaced.append(len(synced))
            return real_replace(src, dst)

        monkeypatch.setattr(p9.os, "replace", spy_replace)
        assert p9.quarantine_corrupt_state_lines() == 1
        assert replaced == [2], f"fsyncs before rename: {replaced}"

    def test_temp_file_is_cleaned_up_on_failure(self, p9, monkeypatch):
        """M-O. A failed pass must not litter `.quarantine.tmp` beside a log
        that other processes scan."""
        self._torn(p9)
        monkeypatch.setattr(p9.os, "replace",
                            lambda *a: (_ for _ in ()).throw(OSError("nope")))
        assert p9.quarantine_corrupt_state_lines() == 0
        leftovers = list(p9.p9_home().glob("*.tmp"))
        assert leftovers == [], f"temp files left behind: {leftovers}"

    def test_clean_log_is_a_no_op_and_latches(self, p9):
        _watching(p9, 36, WORKSPACE)
        before = p9.state_jsonl().read_text(encoding="utf-8")
        assert p9.quarantine_corrupt_state_lines() == 0
        assert p9.state_jsonl().read_text(encoding="utf-8") == before
        assert p9._STATE_QUARANTINE_DONE is True

    def test_success_latches(self, p9):
        """M-AC. Rescanning a 1600-row log on every call is pure waste."""
        self._torn(p9)
        assert p9.quarantine_corrupt_state_lines() == 1
        assert p9._STATE_QUARANTINE_DONE is True
        assert p9.quarantine_corrupt_state_lines() == 0

    def test_missing_file_does_not_latch(self, p9):
        """Rows arrive later in the same process on a fresh state dir."""
        assert not p9.state_jsonl().exists()
        assert p9.quarantine_corrupt_state_lines() == 0
        assert p9._STATE_QUARANTINE_DONE is False
        self._torn(p9)
        assert p9.quarantine_corrupt_state_lines() == 1

    def test_cli_entry_runs_it(self, p9):
        self._torn(p9)
        assert p9.main(["status", "--no-reap"]) == p9.EXIT_OK
        assert '{"ts":"par' not in p9.state_jsonl().read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# BLOCKER-1 — a row with no recorded repo is never re-armed
# ─────────────────────────────────────────────────────────────────────────────
class TestRepoLessRowIsNeverReArmed:
    """The safety property is **no child watcher targets any repo**, not "the
    argv we pass omits --repo".

    Round 2 asserted the argv property and shipped the defect anyway: the
    child calls `resolve_repo(None)` itself, and since parent and child share
    cwd and env it resolves the same ambient repo. The chain that survived a
    round with a test named after it:

        gh pr checks 55 --watch --repo broomva/skills  ->  GREEN
        ->  p9 merge-ready 55  ->  gh pr merge 55 --squash

    So the test below runs a REAL child against a PATH-shimmed `gh` and
    asserts nothing was ever invoked. A Popen-mocked argv assertion cannot
    carry this claim.
    """

    def _seed_dead_repoless(self, home, pr=55):
        row = {"ts": "2020-01-01T00:00:00+00:00", "pr": pr, "repo": "",
               "from_state": "PUSHED", "to_state": "WATCHING",
               "watcher_id": "wnorepo", "attempt": 0, "evaluator_score": None,
               "extra": {"pid": 999991}, "session_id": ""}
        (home / "state.jsonl").write_text(json.dumps(row) + "\n")

    def _gh_shim(self, home):
        shim = home / "bin"
        shim.mkdir(exist_ok=True)
        log = home / "gh-calls.log"
        gh = shim / "gh"
        gh.write_text(f'#!/bin/sh\necho "$@" >> {log}\nexit 0\n')
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        return shim, log

    @pytest.mark.parametrize("ambient", ["-", "broomva/skills"])
    def test_no_child_watcher_is_spawned_at_all(self, p9, tmp_path, ambient):
        """Must hold in BOTH regimes — the ambient-repo one is where round 2
        broke, and pinning tests repo-less is what hid it."""
        self._seed_dead_repoless(tmp_path)
        shim, ghlog = self._gh_shim(tmp_path)
        env = dict(os.environ)
        env.update(BROOMVA_P9_HOME=str(tmp_path),
                   BROOMVA_P9_POLICY=str(_FIXTURES / "policy-good.yaml"),
                   BROOMVA_P9_REPO=ambient,
                   PATH=f"{shim}{os.pathsep}{env['PATH']}")
        out = subprocess.run(
            [sys.executable, str(_SCRIPTS / "p9.py"), "rearm", "--now", "--json"],
            env=env, capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        action = json.loads(out.stdout)["rearmed"][0]

        # The safety property, asserted directly.
        time.sleep(1.0)  # a spawned child would have reached `gh` by now
        assert not ghlog.exists(), (
            f"a child watcher invoked gh: {ghlog.read_text()!r}")
        assert "rearmed_pid" not in action, f"a watcher was re-armed: {action}"
        assert "skipped" in action and "no repo recorded" in action["skipped"]

        # And it is folded, so the slot is freed rather than held forever.
        rows = [json.loads(l) for l
                in (tmp_path / "state.jsonl").read_text().splitlines() if l.strip()]
        assert rows[-1]["to_state"] == "ABANDONED"
        assert rows[-1]["repo"] == ""       # folded on its own key
        assert {(r["repo"], r["to_state"]) for r in rows} == {
            ("", "WATCHING"), ("", "ABANDONED")}

    def test_a_row_with_a_real_repo_is_still_re_armed(self, p9, tmp_path):
        """The guard must not disarm rearm for ordinary rows."""
        row = {"ts": "2020-01-01T00:00:00+00:00", "pr": 55, "repo": WORKSPACE,
               "from_state": "PUSHED", "to_state": "WATCHING",
               "watcher_id": "w55", "attempt": 0, "evaluator_score": None,
               "extra": {"pid": 999991}, "session_id": ""}
        (tmp_path / "state.jsonl").write_text(json.dumps(row) + "\n")
        shim, ghlog = self._gh_shim(tmp_path)
        env = dict(os.environ)
        env.update(BROOMVA_P9_HOME=str(tmp_path),
                   BROOMVA_P9_POLICY=str(_FIXTURES / "policy-good.yaml"),
                   BROOMVA_P9_REPO="broomva/skills",
                   PATH=f"{shim}{os.pathsep}{env['PATH']}")
        out = subprocess.run(
            [sys.executable, str(_SCRIPTS / "p9.py"), "rearm", "--now", "--json"],
            env=env, capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert "rearmed_pid" in json.loads(out.stdout)["rearmed"][0]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not ghlog.exists():
            time.sleep(0.1)
        assert ghlog.exists(), "the real-repo row was not re-armed"
        assert f"--repo {WORKSPACE}" in ghlog.read_text()

    def test_dry_run_says_it_will_fold_not_rewatch(self, p9, capsys):
        dead = subprocess.Popen([sys.executable, "-c", "pass"]); dead.wait()
        p9.jsonl_append(p9.state_jsonl(), json.dumps(
            {"ts": "2020-01-01T00:00:00+00:00", "pr": 55, "repo": "",
             "from_state": "PUSHED", "to_state": "WATCHING",
             "watcher_id": "w", "attempt": 0, "evaluator_score": None,
             "extra": {"pid": dead.pid}, "session_id": ""}),
            p9.state_lock_path())
        assert p9.main(["rearm", "--now", "--dry-run", "--json"]) == p9.EXIT_OK
        would = json.loads(capsys.readouterr().out)["rearmed"][0]["would"]
        assert "fold" in would and "no repo recorded" in would

    def test_cleanup_will_not_ask_github_about_an_unknown_repo(
            self, p9, monkeypatch, capsys):
        """`cleanup` folds rows terminal off a GitHub answer. Asking "is #36
        merged?" of the wrong repo is the false-positive cleanup this command
        promises never to do."""
        _write_legacy(p9, 36)
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda cmd, *a, **k: calls.append(cmd))
        assert p9.main(["cleanup"]) == p9.EXIT_OK
        assert not calls, f"queried GitHub on an unknown repo: {calls}"
        assert "no repo recorded" in capsys.readouterr().out
        assert p9.current_pr_state(36, "") == p9.PRState.WATCHING

    def test_reap_will_not_reconcile_an_unknown_repo_against_github(
            self, p9, monkeypatch):
        _write_legacy(p9, 36)
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda cmd, *a, **k: calls.append(cmd))
        reaped = p9.reap_stale_watchers(grace_seconds=0.0, reconcile=True)
        assert len(reaped) == 1
        assert not calls, f"queried GitHub on an unknown repo: {calls}"
        assert p9.open_prs() == []          # folded on its own key, slot freed


# ─────────────────────────────────────────────────────────────────────────────
# stuck-scan — the fourth `_row_repo` site (was entirely uncovered)
# ─────────────────────────────────────────────────────────────────────────────
class TestStuckScan:
    def _live_row(self, p9, pr, repo):
        _watching(p9, pr, repo, pid=os.getpid(), ts="2020-01-01T00:00:00+00:00")

    def test_reports_a_stalled_watcher(self, p9, capsys):
        self._live_row(p9, 42, WORKSPACE)
        rc = p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        assert rc == p9.EXIT_DEGRADED
        stuck = json.loads(capsys.readouterr().out)["stuck"]
        assert [(s["pr"], s["repo"]) for s in stuck] == [(42, WORKSPACE)]

    def test_never_reports_an_unknown_repo_as_a_real_one(self, p9, capsys):
        """M-S. A repo-less row must be reported honestly, not stamped with
        whatever repo happens to be ambient."""
        _write_legacy(p9, 36)
        p9.append_state_event(p9.PRStateEvent(
            ts="2020-01-01T00:00:00+00:00", pr=36, repo="",
            from_state="WATCHING", to_state="WATCHING",
            watcher_id="legacy", extra={"pid": os.getpid()}))
        p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        stuck = json.loads(capsys.readouterr().out)["stuck"]
        assert [s["repo"] for s in stuck] == [""]

    def test_marker_is_repo_keyed_so_two_repos_dedup_apart(self, p9, capsys):
        """M-S2. Same PR number in two repos must not share one stall-dedup
        marker, or the second repo's stall is silently swallowed."""
        self._live_row(p9, 42, WORKSPACE)
        self._live_row(p9, 42, SRI)
        p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        stuck = json.loads(capsys.readouterr().out)["stuck"]
        assert sorted(s["repo"] for s in stuck) == sorted([WORKSPACE, SRI])
        assert all(s["notified"] for s in stuck)
        markers = sorted(x.name for x in p9.stuck_markers_dir().iterdir())
        assert len(markers) == 2, markers

    def test_case_variants_share_one_marker(self, p9, capsys):
        """The flip side: one logical repo must not produce two markers."""
        self._live_row(p9, 42, "GetStimulus/sri")
        p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        first = sorted(x.name for x in p9.stuck_markers_dir().iterdir())
        p9.state_jsonl().unlink()
        self._live_row(p9, 42, "getstimulus/SRI")
        p9.main(["stuck-scan", "--threshold-min", "1", "--json"])
        assert sorted(x.name for x in p9.stuck_markers_dir().iterdir()) == first


class TestCeilingScopePolicy:
    def _policy(self, tmp_path, scope):
        src = (_FIXTURES / "policy-good.yaml").read_text(encoding="utf-8")
        if scope is not None:
            src = src.replace("max_concurrent_prs: 1",
                              f"max_concurrent_prs: 1\n"
                              f"  max_concurrent_prs_scope: {scope}")
        path = tmp_path / f"policy-{scope}.yaml"
        path.write_text(src, encoding="utf-8")
        return path

    def test_defaults_to_repo(self, p9):
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
        assert cfg.ci_watch.max_concurrent_prs_scope == "repo"

    def test_global_scope_restores_the_cross_repo_count(
            self, p9, tmp_path, monkeypatch):
        """The knob is the point: a workspace that WANTS one bounded merge
        train across every repo can still have it."""
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        monkeypatch.setenv("BROOMVA_P9_POLICY",
                           str(self._policy(tmp_path, "global")))
        _watching(p9, 307, SRI, session_id="A")
        assert p9.main(["watch", "50", "--repo", SKILLS,
                        "--dry-run"]) == p9.EXIT_CONCURRENCY_CEILING

    def test_repo_scope_is_what_unblocks_it(self, p9, tmp_path, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        monkeypatch.setenv("BROOMVA_P9_POLICY",
                           str(self._policy(tmp_path, "repo")))
        _watching(p9, 307, SRI, session_id="A")
        assert p9.main(["watch", "50", "--repo", SKILLS,
                        "--dry-run"]) == p9.EXIT_OK

    def test_invalid_scope_fails_closed(self, p9, tmp_path):
        with pytest.raises(p9.PolicyError):
            p9.load_policy(self._policy(tmp_path, "per-moon-phase"))
