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


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    """Fresh p9 with tmpdir state, max_concurrent_prs=1, and repo resolution
    pinned to "no ambient repo" — every test that needs one is explicit."""
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    monkeypatch.setenv("BROOMVA_P9_REPO", "")
    monkeypatch.delenv("BROOMVA_P9_SESSION", raising=False)
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


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

    def test_env_set_empty_pins_no_repo_without_probing(self, p9, monkeypatch):
        """An explicitly-empty env means "no repo", NOT "go ask gh" — that is
        what makes the suite hermetic."""
        def boom(*a, **k):  # pragma: no cover - must never run
            raise AssertionError("resolution probed a subprocess")
        monkeypatch.setattr(p9.subprocess, "run", boom)
        assert p9.resolve_repo() == ""

    @pytest.mark.parametrize("raw", [
        "broomva/workspace",
        "  broomva/workspace  ",
        "broomva/workspace/",
        "https://github.com/broomva/workspace",
        "https://github.com/broomva/workspace.git",
        "git@github.com:broomva/workspace.git",
        "ssh://git@github.com/broomva/workspace.git",
    ])
    def test_canonicalizes_every_spelling(self, p9, raw):
        assert p9.canonical_repo(raw) == WORKSPACE

    def test_odd_repo_values_are_kept_not_collapsed(self, p9):
        """A value that isn't `owner/name` must survive. Collapsing it to ""
        would alias it onto the legacy no-repo key and erase its identity."""
        assert p9.canonical_repo("weird") == "weird"
        assert p9.repo_key("weird") == "weird"
        assert p9.repo_key("weird") != p9.repo_key("")
        _watching(p9, 7, "weird")
        assert [r["repo"] for r in _raw_rows(p9)] == ["weird"]
        assert p9.current_pr_state(7, "weird") == p9.PRState.WATCHING
        assert p9.current_pr_state(7, "") is None

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
    def test_legacy_row_is_readable_under_the_resolved_repo(self, p9, monkeypatch):
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.current_pr_state(36, WORKSPACE) == p9.PRState.WATCHING
        assert [(r["repo"], r["pr"]) for r in p9.open_prs()] == [(WORKSPACE, 36)]

    def test_legacy_in_flight_state_is_not_discarded(self, p9, monkeypatch):
        """A live legacy watcher must survive the migration, not vanish."""
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        before = len(_raw_rows(p9))
        p9.migrate_legacy_state_repos()
        after = _raw_rows(p9)
        assert len(after) == before
        assert after[0]["repo"] == WORKSPACE
        assert after[0]["extra"] == {"pid": 20307}  # every other field intact
        assert after[0]["watcher_id"] == "legacy"

    def test_migration_persists_on_next_save(self, p9, monkeypatch):
        """Read-path attribution is in memory; the next state write makes it
        durable."""
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        _watching(p9, 99, WORKSPACE)  # any append triggers the rewrite
        assert all(r["repo"] for r in _raw_rows(p9))

    def test_pure_read_does_not_rewrite_the_log(self, p9, monkeypatch):
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        raw_before = p9.state_jsonl().read_text(encoding="utf-8")
        p9.open_prs()
        p9.current_pr_state(36, WORKSPACE)
        assert p9.state_jsonl().read_text(encoding="utf-8") == raw_before

    def test_migration_declines_when_no_repo_resolves(self, p9):
        """Attributing a row to a repo we cannot name would be a guess; the
        legacy key is kept instead."""
        _write_legacy(p9, 36)
        raw_before = p9.state_jsonl().read_text(encoding="utf-8")
        assert p9.migrate_legacy_state_repos() == 0
        assert p9.state_jsonl().read_text(encoding="utf-8") == raw_before
        assert p9.current_pr_state(36, "") == p9.PRState.WATCHING

    def test_migration_is_idempotent(self, p9, monkeypatch):
        _write_legacy(p9, 36)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.migrate_legacy_state_repos() == 1
        p9._STATE_MIGRATION_DONE = False  # allow a second real pass
        raw = p9.state_jsonl().read_text(encoding="utf-8")
        assert p9.migrate_legacy_state_repos() == 0
        assert p9.state_jsonl().read_text(encoding="utf-8") == raw

    def test_torn_last_line_survives_migration(self, p9, monkeypatch):
        """A crash-torn trailing write must not be silently deleted by the
        rewrite, and must not crash it."""
        _write_legacy(p9, 36)
        with p9.state_jsonl().open("a", encoding="utf-8") as f:
            f.write('{"ts":"par')
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.migrate_legacy_state_repos() == 1
        text = p9.state_jsonl().read_text(encoding="utf-8")
        assert '{"ts":"par' in text
        assert json.loads(text.splitlines()[0])["repo"] == WORKSPACE

    def test_missing_state_file_is_a_no_op(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert not p9.state_jsonl().exists()
        assert p9.migrate_legacy_state_repos() == 0

    def test_legacy_row_does_not_shadow_a_real_repo_pr(self, p9, monkeypatch):
        """Migration attributes the legacy row to the resolved repo — it must
        not leak into a *different* repo's lookup."""
        _write_legacy(p9, 256)
        monkeypatch.setenv("BROOMVA_P9_REPO", WORKSPACE)
        assert p9.current_pr_state(256, WORKSPACE) == p9.PRState.WATCHING
        assert p9.current_pr_state(256, SRI) is None
