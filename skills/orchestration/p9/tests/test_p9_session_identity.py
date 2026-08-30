"""Harness-derived session identity (BRO-2373).

BRO-1529 built per-session scoping and made it conditional on the caller
exporting ``BROOMVA_P9_SESSION``. A workspace-wide grep found that variable set
in *tests and nowhere else*, so every real agent fell through to one shared
persisted id and the per-session ceiling degenerated to a global one: two
agents in one repo starved each other at ``max_concurrent_prs: 1``.

The whole suite missed it because every isolation test set the variable itself.
Monkeypatching the marker under test means the test can only ever exercise the
branch production never takes.

**So these tests run the real CLI in real subprocesses with real environments.**
No monkeypatch, no in-process import. The environment *is* the thing under
test; anything that fakes it re-creates the original blind spot.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_P9 = _HERE.parent / "scripts" / "p9.py"
_FIXTURES = _HERE / "fixtures"

sys.path.insert(0, str(_HERE.parent / "scripts"))
import p9 as _p9  # noqa: E402

# `p9 watch` exits 5 when the ceiling refuses a new watcher.
CEILING = _p9.EXIT_CONCURRENCY_CEILING
REPO = "broomva/test"

# Every marker name p9 declares, cleared from the inherited environment so a
# test's regime is exactly what it passes in.
_SCRUB = ("BROOMVA_P9_SESSION", *(name for name, _ in _p9.SESSION_MARKERS))


@pytest.fixture()
def sandbox(tmp_path):
    """An isolated p9 state dir + a runner that spawns the real CLI."""
    home = tmp_path / "home"
    home.mkdir()

    def run(*args: str, **markers: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
        env["BROOMVA_P9_HOME"] = str(home)
        env["BROOMVA_P9_POLICY"] = str(_FIXTURES / "policy-good.yaml")
        env["BROOMVA_P9_REPO"] = REPO
        env.update(markers)
        return subprocess.run(
            [sys.executable, str(_P9), *args],
            env=env, capture_output=True, text=True, timeout=60,
        )

    def watch(pr: int, **markers: str) -> subprocess.CompletedProcess:
        return run("watch", str(pr), "--repo", REPO,
                   "--dry-run", "--detach", **markers)

    run.watch = watch  # type: ignore[attr-defined]
    return run


_SESSION_RE = re.compile(r"open for session (\S+) in ")


def _session_of(proc: subprocess.CompletedProcess) -> str:
    """The session id named in a ceiling refusal.

    Parsed positionally, not by prefix: matching known prefixes would make an
    explicit ``BROOMVA_P9_SESSION`` value unreadable and quietly turn the
    precedence tests into assertions about the parser.
    """
    m = _SESSION_RE.search(proc.stderr + proc.stdout)
    if not m:
        raise AssertionError(
            f"no ceiling refusal to read a session id from: {proc.stderr!r}")
    return m.group(1)


class TestIsolationIsTheDefault:
    """The bug: isolation required an opt-in that nothing performed."""

    def test_two_harness_sessions_do_not_collide(self, sandbox):
        """Two Claude Code sessions, same repo, different PRs — both arm.

        This is the reported failure. On origin/main the second exits 5.
        """
        a = sandbox.watch(101, CLAUDE_CODE_MESSAGING_SOCKET="/tmp/cc-socks/1111.sock")
        b = sandbox.watch(202, CLAUDE_CODE_MESSAGING_SOCKET="/tmp/cc-socks/2222.sock")
        assert a.returncode == 0, a.stderr
        assert b.returncode == 0, (
            "second agent session was refused the ceiling — isolation did not "
            f"apply: {b.stderr}"
        )

    def test_same_session_still_hits_the_ceiling(self, sandbox):
        """Negative control: derivation must not make the ceiling vacuous.

        Without this, a per-invocation id would pass the test above while
        removing back-pressure entirely.
        """
        marker = {"CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/cc-socks/1111.sock"}
        a = sandbox.watch(101, **marker)
        b = sandbox.watch(202, **marker)
        assert a.returncode == 0, a.stderr
        assert b.returncode == CEILING, (
            "one session armed two watchers in one repo at "
            f"max_concurrent_prs=1: {b.stdout} {b.stderr}"
        )

    @pytest.mark.parametrize("env_name,prefix", _p9.SESSION_MARKERS)
    def test_every_declared_marker_isolates(self, sandbox, env_name, prefix):
        """Exhaustive over ``SESSION_MARKERS``.

        A marker added to the table but not actually isolating fails here, so
        a new harness cannot be declared and left inert.
        """
        a = sandbox.watch(101, **{env_name: "stream-a"})
        b = sandbox.watch(202, **{env_name: "stream-b"})
        assert a.returncode == 0, a.stderr
        assert b.returncode == 0, (
            f"{env_name} is declared in SESSION_MARKERS but does not isolate: "
            f"{b.stderr}"
        )
        assert _session_of(
            sandbox.watch(303, **{env_name: "stream-b"})
        ).startswith(f"{prefix}-")


class TestPrecedence:
    def test_explicit_env_outranks_derivation(self, sandbox):
        """An explicit id still wins — two different sockets share one scope."""
        sandbox.watch(101, BROOMVA_P9_SESSION="explicit",
                      CLAUDE_CODE_MESSAGING_SOCKET="/tmp/cc-socks/1111.sock")
        b = sandbox.watch(202, BROOMVA_P9_SESSION="explicit",
                          CLAUDE_CODE_MESSAGING_SOCKET="/tmp/cc-socks/9999.sock")
        assert b.returncode == CEILING
        assert _session_of(b) == "explicit"

    def test_first_declared_marker_wins(self, sandbox):
        """Precedence follows declaration order, not env iteration order."""
        first_name, first_prefix = _p9.SESSION_MARKERS[0]
        markers = {name: f"value-for-{name}" for name, _ in _p9.SESSION_MARKERS}
        sandbox.watch(101, **markers)
        b = sandbox.watch(202, **markers)
        assert _session_of(b).startswith(f"{first_prefix}-")

    def test_no_marker_keeps_the_shared_fallback(self, sandbox):
        """Environments exposing nothing keep pre-BRO-2373 behavior."""
        sandbox.watch(101)
        b = sandbox.watch(202)
        assert b.returncode == CEILING
        assert _session_of(b).startswith("default-")


class TestStability:
    """Stability is the binding constraint: an id that moves between two
    invocations of one session fragments both the ceiling and the wait-queue."""

    def test_derived_id_is_stable_across_invocations(self, sandbox):
        marker = {"CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/cc-socks/1111.sock"}
        sandbox.watch(101, **marker)
        a = _session_of(sandbox.watch(202, **marker))
        b = _session_of(sandbox.watch(303, **marker))
        assert a == b, f"session id moved between invocations: {a} != {b}"

    def test_id_does_not_depend_on_cwd(self, sandbox, tmp_path):
        """An agent that ``cd``s between repos keeps one identity.

        This is why the git worktree is deliberately not part of the key:
        changing identity mid-session would orphan the agent's own queued work.
        """
        marker = {"CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/cc-socks/1111.sock"}
        sandbox.watch(101, **marker)
        here = _session_of(sandbox.watch(202, **marker))
        elsewhere_dir = tmp_path / "elsewhere"
        elsewhere_dir.mkdir()
        cwd = os.getcwd()
        os.chdir(elsewhere_dir)
        try:
            there = _session_of(sandbox.watch(303, **marker))
        finally:
            os.chdir(cwd)
        assert here == there, f"identity changed with cwd: {here} != {there}"

    def test_derivation_never_touches_the_filesystem(self, sandbox):
        """A marker naming a file that does not exist must still derive.

        The Claude Code socket can be unlinked while the session lives; if
        derivation stat'd it, the id would move mid-session.
        """
        missing = "/tmp/cc-socks/definitely-not-present-9999999.sock"
        assert not Path(missing).exists()
        sandbox.watch(101, CLAUDE_CODE_MESSAGING_SOCKET=missing)
        b = sandbox.watch(202, CLAUDE_CODE_MESSAGING_SOCKET=missing)
        assert _session_of(b).startswith("cc-")


CC = "CLAUDE_CODE_MESSAGING_SOCKET"
ORCA = "ORCA_WORKTREE_ID"
AGENT = "AGENT_SESSION_ID"


class TestSharedProcessRegime:
    """The round-1 BLOCKER: several markers present at once, one of them shared.

    The first version of these tests injected each marker **independently**,
    which is not the regime production runs in — here `CLAUDE_CODE_MESSAGING_SOCKET`
    and `ORCA_WORKTREE_ID` are *both* set. Under first-present precedence the
    shared Claude socket masked the distinguishing Orca id and two agents
    collided exactly as before the fix. These tests pin the composite.
    """

    def test_shared_socket_distinct_worktrees_do_not_collide(self, sandbox):
        a = sandbox.watch(101, **{CC: "/tmp/cc-socks/1.sock", ORCA: "uuid::/wt/a"})
        b = sandbox.watch(202, **{CC: "/tmp/cc-socks/1.sock", ORCA: "uuid::/wt/b"})
        assert a.returncode == 0, a.stderr
        assert b.returncode == 0, (
            "two agents sharing one Claude process but in different worktrees "
            f"resolved to the same scope: {b.stderr}")

    def test_identical_marker_sets_still_share_a_scope(self, sandbox):
        """Negative control for the composite: same set => same id."""
        m = {CC: "/tmp/cc-socks/1.sock", ORCA: "uuid::/wt/a"}
        assert sandbox.watch(101, **m).returncode == 0
        assert sandbox.watch(202, **m).returncode == CEILING

    def test_any_differing_marker_separates(self, sandbox):
        """Composite is discriminating on every field, not just the first."""
        base = {CC: "/tmp/cc-socks/1.sock", ORCA: "uuid::/wt/a", AGENT: "x"}
        assert sandbox.watch(101, **base).returncode == 0
        assert sandbox.watch(202, **{**base, AGENT: "y"}).returncode == 0


class TestLatch:
    """Identity is latched, so a changing marker SET cannot move it — while a
    changing marker VALUE still must."""

    def test_marker_disappearing_keeps_the_identity(self, sandbox):
        """`env -i` strips markers; a wrapper that sanitizes env reaches this."""
        full = {CC: "/tmp/cc-socks/1.sock", ORCA: "uuid::/wt/a"}
        sandbox.watch(101, **full)
        before = _session_of(sandbox.watch(202, **full))
        after = _session_of(sandbox.watch(303, **{CC: "/tmp/cc-socks/1.sock"}))
        assert before == after, f"identity moved when a marker vanished: {before} != {after}"

    def test_marker_appearing_keeps_the_identity(self, sandbox):
        partial = {CC: "/tmp/cc-socks/1.sock"}
        sandbox.watch(101, **partial)
        before = _session_of(sandbox.watch(202, **partial))
        after = _session_of(sandbox.watch(
            303, **{CC: "/tmp/cc-socks/1.sock", ORCA: "uuid::/wt/a"}))
        assert before == after, f"identity moved when a marker appeared: {before} != {after}"

    def test_the_latch_does_not_leak_across_a_conflicting_marker(self, sandbox):
        """The latch must not re-open the BLOCKER it was added alongside.

        Agent A latches {cc=S, orca=W1}. Agent B arrives with {cc=S, orca=W2}.
        They overlap on `cc` — if overlap alone were enough to adopt, B would
        inherit A's identity and collide. Disagreement on `orca` must veto it.
        """
        assert sandbox.watch(
            101, **{CC: "/tmp/cc-socks/1.sock", ORCA: "uuid::/wt/a"}).returncode == 0
        assert sandbox.watch(
            202, **{CC: "/tmp/cc-socks/1.sock", ORCA: "uuid::/wt/b"}).returncode == 0


class TestValueFidelity:
    """Properties of the composite itself.

    These call the function in-process rather than through the CLI: they are
    about how a marker *value* maps to an id, not about the multi-process
    regime, and reading an id out of a ceiling refusal would make them
    assertions about the error-message parser instead.
    """

    @staticmethod
    def _id_for(markers):
        return _p9._composite_id(markers)

    def test_whitespace_variants_are_distinct_identities(self):
        """A prior revision stripped marker values and merged four identities.

        `'x'`, `' x '`, `'  x'` and `'x  '` all became one scope. Whitespace
        decides presence; it must never decide identity.
        """
        ids = {v: self._id_for({AGENT: v}) for v in ("x", " x ", "  x", "x  ")}
        assert len(set(ids.values())) == 4, f"distinct values merged: {ids}"

    def test_blank_values_are_absent_not_identities(self):
        """Presence is still whitespace-insensitive — only identity is not."""
        import os
        for blank in ("", "   ", "\t"):
            os.environ[AGENT] = blank
            try:
                assert _p9._present_markers().get(AGENT) is None
            finally:
                os.environ.pop(AGENT, None)

    def test_a_marker_value_cannot_forge_a_field_boundary(self):
        """Composite fields are separated by Unit Separator, which no env var
        value can contain — so one marker cannot impersonate two."""
        honest = self._id_for({CC: "a", ORCA: "b"})
        forged = self._id_for({CC: f"a{_p9._MARKER_SEP}ORCA_WORKTREE_ID=b"})
        assert honest != forged

    def test_marker_order_is_declaration_order_not_dict_order(self):
        """Two dicts with the same pairs in different insertion order are one
        identity — otherwise the id would depend on how the env was read."""
        assert self._id_for({CC: "s", ORCA: "w"}) == self._id_for({ORCA: "w", CC: "s"})


class TestLatchCompatibility:
    """The adopt-or-mint predicate, in isolation."""

    def test_agreement_on_overlap_adopts(self):
        assert _p9._latch_compatible({CC: "s"}, {CC: "s", ORCA: "w"})
        assert _p9._latch_compatible({CC: "s", ORCA: "w"}, {CC: "s"})

    def test_disagreement_on_any_shared_marker_vetoes(self):
        assert not _p9._latch_compatible({CC: "s", ORCA: "w1"},
                                         {CC: "s", ORCA: "w2"})

    def test_no_overlap_never_adopts(self):
        assert not _p9._latch_compatible({CC: "s"}, {ORCA: "w"})
