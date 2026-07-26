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
import subprocess
import sys
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


class TestLegacyMigration:
    """Attribution is DURABLE and LABELLED.

    An earlier design attributed legacy rows in memory on every read. That put
    a `gh repo view` API call on the read path, and let reads and the durable
    rewrite disagree about a row's key. Now the migration runs once at CLI
    entry, stamps `repo_inferred`, and every reader sees the same bytes.
    """

    def test_migration_attributes_and_labels_the_guess(self, p9, monkeypatch):
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.migrate_legacy_state_repos() == 1
        row = _raw_rows(p9)[0]
        assert row["repo"] == WORKSPACE
        assert row["repo_inferred"] is True
        assert p9.current_pr_state(36, WORKSPACE) == p9.PRState.WATCHING
        assert [(r["repo"], r["pr"]) for r in p9.open_prs()] == [(WORKSPACE, 36)]

    def test_cli_entry_runs_the_migration(self, p9, monkeypatch):
        """Once, up front — so a command's reads and writes agree on keys."""
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.main(["status", "--no-reap", "--json"]) == p9.EXIT_OK
        assert _raw_rows(p9)[0]["repo"] == WORKSPACE

    def test_legacy_in_flight_state_is_not_discarded(self, p9, monkeypatch):
        """A live legacy watcher must survive the migration, not vanish."""
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        before = len(_raw_rows(p9))
        p9.migrate_legacy_state_repos()
        after = _raw_rows(p9)
        assert len(after) == before
        assert after[0]["extra"] == {"pid": 20307}  # every other field intact
        assert after[0]["watcher_id"] == "legacy"
        assert after[0]["to_state"] == "WATCHING"

    def test_reads_never_resolve_a_repo(self, p9, no_probe):
        """MINOR-5. `gh repo view` is a network call with a 10s timeout; it
        must not sit on the path of listing rows. `no_probe` makes any
        subprocess an error."""
        _watching(p9, 42, WORKSPACE)
        assert p9.current_pr_state(42, WORKSPACE) == p9.PRState.WATCHING
        assert len(p9.open_prs()) == 1
        assert p9.latest_row(42, WORKSPACE) is not None

    def test_read_of_a_migrated_store_is_network_free(self, p9, monkeypatch, no_probe):
        """After the one-time migration, even a store that HAD legacy rows
        never resolves again — the pre-check is a plain file scan."""
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        p9.migrate_legacy_state_repos()
        p9._STATE_MIGRATION_DONE = False   # simulate a fresh process
        monkeypatch.setenv("BROOMVA_P9_REPO", "")  # and no env hint
        assert p9.migrate_legacy_state_repos() == 0  # no_probe would fire
        assert len(p9.open_prs()) == 1

    def test_migration_declines_when_no_repo_resolves(self, p9, monkeypatch):
        """Attributing a row to a repo we cannot name would be a guess; the
        legacy key is kept instead."""
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", p9.REPO_NONE_SENTINEL)
        raw_before = p9.state_jsonl().read_text(encoding="utf-8")
        assert p9.migrate_legacy_state_repos() == 0
        assert p9.state_jsonl().read_text(encoding="utf-8") == raw_before
        assert p9.current_pr_state(36, "") == p9.PRState.WATCHING

    def test_declining_does_not_latch(self, p9, monkeypatch):
        """A decline must stay retryable: latching would leave the row
        unmigrated while later code assumes the post-migration invariant."""
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", p9.REPO_NONE_SENTINEL)
        assert p9.migrate_legacy_state_repos() == 0
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.migrate_legacy_state_repos() == 1

    def test_missing_file_does_not_latch(self, p9, monkeypatch):
        """Rows can appear later in the same process (first-ever event)."""
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert not p9.state_jsonl().exists()
        assert p9.migrate_legacy_state_repos() == 0
        _write_legacy(p9, 36)
        assert p9.migrate_legacy_state_repos() == 1

    def test_migration_is_idempotent(self, p9, monkeypatch):
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.migrate_legacy_state_repos() == 1
        p9._STATE_MIGRATION_DONE = False  # allow a second real pass
        raw = p9.state_jsonl().read_text(encoding="utf-8")
        assert p9.migrate_legacy_state_repos() == 0
        assert p9.state_jsonl().read_text(encoding="utf-8") == raw

    def test_corruption_is_quarantined_not_sealed(self, p9, monkeypatch):
        """MAJOR-3. `jsonl_read_all` tolerates a torn LAST line but raises on
        corruption anywhere else. The rewrite terminates the torn tail with a
        newline, so one ordinary append later it is no longer last — and every
        state read wedges permanently. Move it out instead of sealing it in.
        """
        _write_legacy(p9, 36)
        with p9.state_jsonl().open("a", encoding="utf-8") as f:
            f.write('{"ts":"par')
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.migrate_legacy_state_repos() == 1

        # Preserved verbatim, out of the way.
        assert p9.state_corrupt_path().read_text(encoding="utf-8") == '{"ts":"par\n'
        text = p9.state_jsonl().read_text(encoding="utf-8")
        assert '{"ts":"par' not in text
        assert json.loads(text.splitlines()[0])["repo"] == WORKSPACE

        # The whole point: append after the migration and the log still reads.
        _watching(p9, 99, WORKSPACE)
        rows, dropped = p9.jsonl_read_all(p9.state_jsonl())
        assert dropped == 0 and len(rows) == 2
        assert p9.current_pr_state(99, WORKSPACE) == p9.PRState.WATCHING

    def test_legacy_row_does_not_shadow_a_real_repo_pr(self, p9, monkeypatch):
        """Migration attributes the legacy row to the resolved repo — it must
        not leak into a *different* repo's lookup."""
        _write_legacy(p9, 256)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        p9.migrate_legacy_state_repos()
        assert p9.current_pr_state(256, WORKSPACE) == p9.PRState.WATCHING
        assert p9.current_pr_state(256, SRI) is None


# ─────────────────────────────────────────────────────────────────────────────
# BLOCKER-1 — an inferred repo is never ACTED on
# ─────────────────────────────────────────────────────────────────────────────
class TestInferredRepoIsNeverActedOn:
    """Attribution makes an orphaned row reachable; it does not make the guess
    true. Everything that leaves the process must still refuse it.

    The live chain this closes: `rearm` re-watched a repo-less row as
    `watch <pr> --repo <ambient>`, the watcher went GREEN against a PR nobody
    targeted, and with `auto_merge.enabled` + a matching branch rule the
    actuator merged it.
    """

    def _dead_legacy_row(self, p9, pr=55):
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        row = {"ts": "2020-01-01T00:00:00+00:00", "pr": pr, "repo": "",
               "from_state": "PUSHED", "to_state": "WATCHING",
               "watcher_id": "wnorepo", "attempt": 0, "evaluator_score": None,
               "extra": {"pid": dead.pid}, "session_id": ""}
        p9.jsonl_append(p9.state_jsonl(), json.dumps(row), p9.state_lock_path())

    @pytest.mark.parametrize("ambient", ["-", "broomva/skills"])
    def test_rearm_never_names_a_repo_for_an_inferred_row(
            self, p9, monkeypatch, ambient):
        """Must hold in BOTH regimes. Pinning tests to repo-less is exactly
        what hid this: the guard only misbehaves once a repo resolves."""
        monkeypatch.setenv("BROOMVA_P9_REPO", ambient)
        self._dead_legacy_row(p9)
        spawned = []

        class _FP:
            pid = 99999

        monkeypatch.setattr(p9.subprocess, "Popen",
                            lambda argv, **kw: (spawned.append(argv), _FP())[1])
        assert p9.main(["rearm", "--now", "--json"]) == p9.EXIT_OK
        assert "--repo" not in spawned[0], (
            f"re-watched a row that recorded no repo against one: {spawned[0]}")
        # Folded, and the slot is actually freed (the fold landed on the same
        # key as the row it retires — attribution included).
        assert p9.open_prs() == []

    def test_inferred_label_survives_into_the_next_process(self, p9, monkeypatch):
        """The guard cannot depend on migration timing: once persisted, the
        row looks exactly like one a command recorded unless it stays
        labelled."""
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        p9.migrate_legacy_state_repos()
        p9._STATE_MIGRATION_DONE = False          # fresh process
        row = p9.latest_row(36, WORKSPACE)
        assert row["repo"] == WORKSPACE           # reachable
        assert p9._row_repo(row) == ""            # but never acted on

    def test_cleanup_will_not_ask_github_about_an_inferred_repo(
            self, p9, monkeypatch, capsys):
        """`cleanup` folds rows terminal off a GitHub answer. Asking "is #36
        merged?" of the wrong repo is the false-positive cleanup this command
        promises never to do."""
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        p9.migrate_legacy_state_repos()
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda cmd, *a, **k: calls.append(cmd))
        assert p9.main(["cleanup"]) == p9.EXIT_OK
        assert not calls, f"queried GitHub on an inferred repo: {calls}"
        assert "no repo recorded" in capsys.readouterr().out
        assert p9.current_pr_state(36, WORKSPACE) == p9.PRState.WATCHING

    def test_reap_will_not_reconcile_an_inferred_repo_against_github(
            self, p9, monkeypatch):
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        p9.migrate_legacy_state_repos()
        calls = []
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda cmd, *a, **k: calls.append(cmd))
        reaped = p9.reap_stale_watchers(grace_seconds=0.0, reconcile=True)
        assert len(reaped) == 1
        assert not calls, f"queried GitHub on an inferred repo: {calls}"
        # Folded on its own key — no leaked slot.
        assert p9.open_prs() == []

    def test_a_real_repo_row_is_still_acted_on(self, p9, monkeypatch):
        """The guard must not disarm rearm for ordinary rows."""
        self._dead_legacy_row(p9)
        # Overwrite with a row that genuinely recorded a repo.
        p9.state_jsonl().unlink()
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        _watching(p9, 55, WORKSPACE, session_id="", pid=dead.pid,
                  ts="2020-01-01T00:00:00+00:00")
        spawned = []

        class _FP:
            pid = 99999

        monkeypatch.setattr(p9.subprocess, "Popen",
                            lambda argv, **kw: (spawned.append(argv), _FP())[1])
        assert p9.main(["rearm", "--now", "--json"]) == p9.EXIT_OK
        assert "--repo" in spawned[0] and WORKSPACE in spawned[0]


# ─────────────────────────────────────────────────────────────────────────────
# MAJOR-4 — the ceiling scope is an explicit policy setpoint
# ─────────────────────────────────────────────────────────────────────────────
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
