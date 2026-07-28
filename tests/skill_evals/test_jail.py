"""Tests for the environment jail (scripts/skill_evals/jail.py, BRO-2018).

The harness gave every trial a fresh temp cwd and called that isolation. It was
half of it: the skills under test resolve their state from ``$HOME`` — p9 writes
``~/.config/broomva/p9``, kg locates the whole workspace at ``Path.home()/"broomva"``
— and ``subprocess.run`` was passing no ``env=``, so a live positive trial read and
wrote the user's real stores.

Two rules shape every test below.

**Prove it in a subprocess, never in-process.** ``os.environ`` in this interpreter
is not what a spawned child sees; a check that reads the parent's snapshot passes
while the child escapes. Every containment assertion here launches a real process
under the jailed env and asks *it* where the paths went.

**Bidirectional, in the same file.** A containment test that would pass even with
the jail switched off proves nothing, so each one is paired with its mutation:
``test_subprocess_escapes_to_the_real_home_without_the_jail`` is what makes
``test_subprocess_resolves_home_inside_the_jail`` mean something, and
``test_verify_jail_reports_an_escape_when_home_leaks`` is what stops
:func:`~skill_evals.jail.verify_jail` from being a function that always says yes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals import jail as J  # noqa: E402
from skill_evals import runner as R  # noqa: E402

#: Resolves the paths a skill script would, and prints where they landed. Run as a
#: child process so the answer describes the child's environment, not this one's.
PROBE = (
    "import json, os;"
    "from pathlib import Path;"
    "print(json.dumps({'home': str(Path.home()), 'tilde': os.path.expanduser('~'),"
    "'xdg': os.environ.get('XDG_CONFIG_HOME', ''),"
    "'key': os.environ.get('ANTHROPIC_API_KEY', ''),"
    "'p9': os.environ.get('BROOMVA_P9_HOME', ''),"
    "'path': os.environ.get('PATH', '')}))"
)


def probe(env):
    """Run PROBE in a child process under *env* and return its resolved paths."""
    proc = subprocess.run(
        [sys.executable, "-c", PROBE],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# containment — and the mutation that proves the containment tests can fail
# ---------------------------------------------------------------------------


def test_subprocess_resolves_home_inside_the_jail(tmp_path):
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    got = probe(J.build_case_env(ws))
    jail = str(J.jail_home(ws))
    assert got["home"] == jail
    assert got["tilde"] == jail
    assert got["xdg"] == str(J.jail_home(ws) / ".config")


def test_subprocess_escapes_to_the_real_home_without_the_jail(tmp_path):
    """THE mutation proof. Same probe, unjailed env — it finds the real HOME.

    Without this, every assertion above would still hold on a machine where
    ``Path.home()`` happened to be unset, and the suite would be measuring nothing.
    """
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    got = probe(dict(os.environ))
    assert got["home"] == os.path.expanduser("~")
    assert got["home"] != str(J.jail_home(ws))


def test_p9_state_dir_resolves_inside_the_jail(tmp_path):
    """p9's own resolution order, reproduced: BROOMVA_P9_HOME, XDG, then ~/.config.

    Mirrors ``skills/orchestration/p9/scripts/p9.py``. This is the concrete write
    the ticket was filed about.
    """
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    env = J.build_case_env(ws)
    src = (
        "import os;from pathlib import Path;"
        "print(os.environ.get('BROOMVA_P9_HOME') or "
        "str(Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'broomva'/'p9'))"
    )
    proc = subprocess.run([sys.executable, "-c", src], env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().startswith(str(J.jail_home(ws)))


def test_kg_workspace_resolves_inside_the_jail(tmp_path):
    """kg locates the entire workspace — and so research/entities — off Path.home()."""
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    env = J.build_case_env(ws)
    proc = subprocess.run(
        [sys.executable, "-c", "from pathlib import Path;print(Path.home()/'broomva')"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(J.jail_home(ws) / "broomva")


def test_a_skill_script_can_still_write_its_state_dir(tmp_path):
    """FALSE-POSITIVE proof: containing the write must not prevent it.

    Over-isolating so the script cannot run at all trades a side effect for a
    false-fail, which is the failure mode
    ``anti-vacuity-fixes-overshoot-into-noise`` documents. The jail pre-creates the
    XDG tree precisely so a script that writes ``~/.config/...`` succeeds.
    """
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    src = (
        "from pathlib import Path;"
        "d=Path.home()/'.config'/'broomva'/'p9';d.mkdir(parents=True, exist_ok=True);"
        "f=d/'queue.json';f.write_text('[]');print(f.read_text())"
    )
    proc = subprocess.run([sys.executable, "-c", src], env=J.build_case_env(ws),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[]"
    assert (J.jail_home(ws) / ".config" / "broomva" / "p9" / "queue.json").is_file()


# ---------------------------------------------------------------------------
# deny-by-default
# ---------------------------------------------------------------------------


def test_api_key_never_survives_the_jail(tmp_path):
    """The named hazard: a subscription CLI handed an API key bills another account.

    Pinned as its own test rather than left implicit in the allowlist, because the
    way this regresses is somebody widening PASSTHROUGH_ENV, not somebody adding
    ``ANTHROPIC_API_KEY`` back by hand.
    """
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    parent = dict(os.environ, ANTHROPIC_API_KEY="sk-ant-should-not-survive")
    assert "ANTHROPIC_API_KEY" not in J.build_case_env(ws, parent)
    assert probe(J.build_case_env(ws, parent))["key"] == ""


@pytest.mark.parametrize(
    "var",
    ["BROOMVA_P9_HOME", "CLAUDE_CONFIG_DIR", "BROOMVA_P9_REPO", "NODE_OPTIONS",
     "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY"],
)
def test_unlisted_variables_are_dropped(tmp_path, var):
    ws = tmp_path / "ws"
    env = J.build_case_env(ws, {var: "leaked", "PATH": "/usr/bin"})
    assert var not in env


def test_allowlisted_variables_survive(tmp_path):
    """The other direction: deny-by-default must not deny the CLI its own PATH."""
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    env = J.build_case_env(ws, {"PATH": "/usr/bin:/bin", "TERM": "xterm", "DROPME": "x"})
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["TERM"] == "xterm"
    assert "DROPME" not in env
    assert probe(J.build_case_env(ws))["path"], "a child with no PATH cannot launch anything"


def test_home_is_set_not_passed_through(tmp_path):
    """HOME must be *overwritten*, never inherited — inheriting is the whole defect."""
    ws = tmp_path / "ws"
    env = J.build_case_env(ws, {"HOME": "/Users/somebody", "PATH": "/usr/bin"})
    assert env["HOME"] == str(J.jail_home(ws))


# ---------------------------------------------------------------------------
# verify_jail — the pre-flight proof, and proof that it can say no
# ---------------------------------------------------------------------------


def test_verify_jail_holds_on_a_prepared_workspace(tmp_path):
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    verdict = J.verify_jail(ws)
    assert verdict.holds, verdict.escapes
    assert verdict.resolved["home"] == str(J.jail_home(ws))


def test_verify_jail_reports_an_escape_when_home_leaks(tmp_path, monkeypatch):
    """MUTATION: hand verify_jail a leaky env-builder; it must refuse to pass.

    A pre-flight check that cannot fail is worse than none — it is a green light
    wired to nothing.
    """
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    real_builder = J.build_case_env  # captured BEFORE the patch, or leaky recurses

    def leaky(workspace, parent_env=None):
        env = real_builder(workspace, parent_env)
        env["HOME"] = os.path.expanduser("~")  # the pre-BRO-2018 behaviour
        return env

    monkeypatch.setattr(J, "build_case_env", leaky)
    verdict = J.verify_jail(ws)
    assert not verdict.holds
    assert any("home resolved to" in e for e in verdict.escapes)


def test_containment_is_component_wise_not_a_string_prefix(tmp_path, monkeypatch):
    """A sibling sharing the jail's textual prefix must NOT read as contained.

    ``str.startswith`` would pass ``<ws>/.eval-home-backup``, which is a hole in the
    one check the rest of the design defers to. Caught in review of BRO-2018.
    """
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    sibling = ws / f"{J.JAIL_DIRNAME}-backup"
    sibling.mkdir(parents=True)

    assert J._within(J.jail_home(ws) / ".config", J.jail_home(ws))
    assert J._within(J.jail_home(ws), J.jail_home(ws))
    assert not J._within(sibling, J.jail_home(ws))

    real_builder = J.build_case_env

    def sibling_home(workspace, parent_env=None):
        env = real_builder(workspace, parent_env)
        env["HOME"] = str(sibling)
        return env

    monkeypatch.setattr(J, "build_case_env", sibling_home)
    verdict = J.verify_jail(ws)
    assert not verdict.holds
    assert any("home resolved to" in e for e in verdict.escapes)


def test_verify_jail_flags_a_surviving_api_key(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    J.prepare_jail(ws, link_auth=False)
    real_builder = J.build_case_env

    def keyed(workspace, parent_env=None):
        env = real_builder(workspace, parent_env)
        env["ANTHROPIC_API_KEY"] = "sk-ant-leak"
        return env

    monkeypatch.setattr(J, "build_case_env", keyed)
    verdict = J.verify_jail(ws)
    assert not verdict.holds
    assert any("ANTHROPIC_API_KEY" in e for e in verdict.escapes)


# ---------------------------------------------------------------------------
# auth passthrough — the one deliberate hole
# ---------------------------------------------------------------------------


def test_auth_material_is_linked_not_copied(tmp_path):
    """A symlink, so the secret is never duplicated into a temp dir we then delete."""
    real = tmp_path / "real-home"
    (real / "Library" / "Keychains").mkdir(parents=True)
    (real / "Library" / "Keychains" / "login.keychain-db").write_text("secret")
    home = tmp_path / "ws" / J.JAIL_DIRNAME
    home.mkdir(parents=True)

    created = J.link_auth_material(home, real_home=real, platform="darwin")

    link = home / "Library" / "Keychains" / "login.keychain-db"
    assert created == [link]
    assert link.is_symlink()
    assert link.resolve() == (real / "Library" / "Keychains" / "login.keychain-db").resolve()


def test_auth_passthrough_links_nothing_else(tmp_path):
    """The hole stays the size it is documented to be."""
    real = tmp_path / "real-home"
    (real / "Library" / "Keychains").mkdir(parents=True)
    (real / "Library" / "Keychains" / "login.keychain-db").write_text("secret")
    (real / "Library" / "Keychains" / "iCloud.keychain-db").write_text("other secret")
    (real / ".ssh").mkdir()
    (real / ".ssh" / "id_ed25519").write_text("private key")
    home = tmp_path / "ws" / J.JAIL_DIRNAME
    home.mkdir(parents=True)

    J.link_auth_material(home, real_home=real, platform="darwin")

    assert not (home / "Library" / "Keychains" / "iCloud.keychain-db").exists()
    assert not (home / ".ssh").exists()


def test_missing_auth_source_is_skipped_not_fatal(tmp_path):
    """CI has no keychain; refusing to build a jail there would break the suite."""
    real = tmp_path / "empty-home"
    real.mkdir()
    home = tmp_path / "ws" / J.JAIL_DIRNAME
    home.mkdir(parents=True)
    assert J.link_auth_material(home, real_home=real, platform="darwin") == []


def test_wrapper_activation_vars_are_dropped(tmp_path):
    """A CLI on PATH may be a WRAPPER that injects settings and hooks.

    ``shutil.which("claude")`` resolves to ``~/.superconductor/bin/claude`` on this
    machine, and that wrapper appends
    ``--settings ~/.superconductor/hooks/claude-settings.json`` — SessionStart,
    PreToolUse, Stop hooks — into the run. ``--setting-sources project`` does not
    gate ``--settings``, so those hooks would fire inside every eval trial and the
    "16 built-ins only" isolation claim would be false.

    The wrapper gates that injection on ``SUPERCONDUCTOR_TERMINAL_ID`` being set AND
    ``SUPERCONDUCTOR_MANAGED_AGENT=1``; with either absent it execs the real binary
    with a scrubbed environment. Deny-by-default drops both, so the jail already
    closes this. Pinned here because it is a *consequence* of the allowlist rather
    than an intention of it — someone widening PASSTHROUGH_ENV would reopen it
    without ever touching this file.
    """
    ws = tmp_path / "ws"
    parent = {
        "PATH": "/usr/bin",
        "SUPERCONDUCTOR_TERMINAL_ID": "2d596d6c-dead-beef",
        "SUPERCONDUCTOR_MANAGED_AGENT": "1",
    }
    env = J.build_case_env(ws, parent)
    assert "SUPERCONDUCTOR_TERMINAL_ID" not in env
    assert "SUPERCONDUCTOR_MANAGED_AGENT" not in env


def test_auth_material_missing_is_detected(tmp_path):
    """Silent absence turns into a whole suite of 'Not logged in' ERRORs."""
    empty = tmp_path / "empty-home"
    empty.mkdir()
    assert J.auth_material_missing(real_home=empty, platform="darwin") is True

    stocked = tmp_path / "stocked-home"
    (stocked / "Library" / "Keychains").mkdir(parents=True)
    (stocked / "Library" / "Keychains" / "login.keychain-db").write_text("x")
    assert J.auth_material_missing(real_home=stocked, platform="darwin") is False


def test_rmtree_cannot_delete_the_real_credential_through_the_link(tmp_path):
    """The workspace is rmtree'd after every trial and holds a link to the REAL
    keychain. If rmtree followed it, the harness would delete the user's login
    keychain — catastrophic, and worth an explicit test rather than a reasoned
    assurance about shutil semantics."""
    import shutil as _shutil

    real = tmp_path / "real-home"
    (real / "Library" / "Keychains").mkdir(parents=True)
    kc = real / "Library" / "Keychains" / "login.keychain-db"
    kc.write_text("PRECIOUS")

    root = tmp_path / "case"
    ws = root / "ws"
    J.prepare_jail(ws, link_auth=False)
    # linked explicitly for darwin, so the assertion holds on Linux CI too
    J.link_auth_material(J.jail_home(ws), real_home=real, platform="darwin")
    assert (J.jail_home(ws) / "Library" / "Keychains" / "login.keychain-db").is_symlink()

    _shutil.rmtree(root, ignore_errors=True)

    assert not ws.exists()
    assert kc.exists() and kc.read_text() == "PRECIOUS"


def test_prepare_jail_creates_the_xdg_tree(tmp_path):
    home = J.prepare_jail(tmp_path / "ws", link_auth=False)
    for sub in (".config", ".cache", ".local/share", ".local/state", "tmp"):
        assert (home / sub).is_dir(), sub


# ---------------------------------------------------------------------------
# real-state watch
# ---------------------------------------------------------------------------


def test_watch_is_quiet_when_nothing_changed(tmp_path):
    """FALSE-POSITIVE proof: a watch that always reports change gets muted."""
    store = tmp_path / "store"
    store.mkdir()
    (store / "queue.json").write_text("[]")
    watch = J.RealStateWatch(paths=(str(store),))
    watch.snapshot()
    assert watch.changes() == []


def test_watch_reports_a_write(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    watch = J.RealStateWatch(paths=(str(store),))
    watch.snapshot()
    (store / "leaked.json").write_text("{}")
    changes = watch.changes()
    assert len(changes) == 1
    assert changes[0].startswith("created: ")
    assert "leaked.json" in changes[0]


def test_watch_reports_a_deletion(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    victim = store / "queue.json"
    victim.write_text("[]")
    watch = J.RealStateWatch(paths=(str(store),))
    watch.snapshot()
    victim.unlink()
    assert any(c.startswith("deleted: ") for c in watch.changes())


def test_watch_tolerates_a_missing_store(tmp_path):
    """A machine that has never run p9 has no ~/.config/broomva. Not an error."""
    watch = J.RealStateWatch(paths=(str(tmp_path / "never-created"),))
    watch.snapshot()
    assert watch.changes() == []


# ---------------------------------------------------------------------------
# the wiring — LiveRunner actually hands the jailed env to the process
# ---------------------------------------------------------------------------


def test_live_runner_passes_the_jailed_env(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    ws = tmp_path / "ws"
    ws.mkdir()
    runner = R.LiveRunner(cli="/bin/true", fingerprint={"skill_md_sha256": "a",
                                                        "description_sha256": "b"})
    runner.run("hi", ws, case_id="c1", trial=1)

    env = seen["env"]
    assert env is not None
    assert env["HOME"] == str(J.jail_home(ws))
    assert "ANTHROPIC_API_KEY" not in env
    assert J.jail_home(ws).is_dir(), "the jail must exist before the process starts"


def test_live_runner_without_the_jail_inherits_the_real_env(tmp_path, monkeypatch):
    """The escape hatch does what it says — this is what --no-env-jail buys, and
    the reason the flag's help text calls it dangerous."""
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    ws = tmp_path / "ws"
    ws.mkdir()
    runner = R.LiveRunner(cli="/bin/true", env_jail=False,
                          fingerprint={"skill_md_sha256": "a", "description_sha256": "b"})
    runner.run("hi", ws, case_id="c1", trial=1)

    assert seen["env"] is None  # None => inherit the parent environment
    assert not J.jail_home(ws).exists()


def test_replay_never_builds_a_jail(tmp_path):
    """Replay grades recorded bytes and spawns nothing, so it should pay for nothing."""
    ws = tmp_path / "ws"
    ws.mkdir()
    runner = R.ReplayRunner(root=tmp_path / "fixtures", fingerprint={})
    with pytest.raises(R.FixtureError):
        runner.run("hi", ws, case_id="missing", trial=1)
    assert not J.jail_home(ws).exists()


# ---------------------------------------------------------------------------
# the residual the jail cannot close, asserted so it stays closed
# ---------------------------------------------------------------------------


#: A home-shaped absolute path. The jail redirects ``~`` and every XDG variable, so
#: this is the one shape it cannot reach.
_ABSOLUTE_HOME_RE = __import__("re").compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")


def _hardcoded_home_paths(src: Path) -> list[str]:
    """Absolute home paths in *executable* string literals — never in prose.

    The first version of this grepped lines and immediately produced the failure
    mode this arc is named for: it flagged ``p9.py`` for the string
    ``file:///Users/x/repos/A`` **inside a docstring**, where it is an example in a
    sentence explaining how such a URL is rejected. A guard that fires on
    documentation gets muted, and a muted guard is worse than an absent one.

    So the predicate is structural rather than textual: parse the module and look
    only at string constants that are not docstrings. Prose is excluded by
    construction instead of by a growing list of exceptions.
    """
    import ast

    text = src.read_text(encoding="utf-8", errors="replace")
    if src.suffix != ".py":  # shell: no docstrings, so comment-stripping is enough
        return [
            f"{src.name}:{n}"
            for n, line in enumerate(text.splitlines(), 1)
            if _ABSOLUTE_HOME_RE.search(line) and not line.lstrip().startswith("#")
        ]
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        f"{src.name}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and _ABSOLUTE_HOME_RE.search(node.value)
    ]


def test_no_evaluated_skill_resolves_state_from_an_absolute_path():
    """A HOME jail contains ``~`` and every XDG path. It cannot contain ``/Users/me/x``.

    So the jail is sufficient for the skills under eval only while none of them
    hardcodes an absolute path — true as of BRO-2018, and this is what keeps it
    true. A skill that adds one escapes the jail silently, and a live eval suite is
    exactly where that must not be discovered by accident.
    """
    offenders: list[str] = []
    for prompts in sorted((REPO / "skills").glob("*/*/evals/prompts.json")):
        skill_dir = prompts.parent.parent
        for src in sorted(skill_dir.rglob("*.py")) + sorted(skill_dir.rglob("*.sh")):
            if "test" in src.name or "tests" in src.parts:
                continue
            offenders += [f"{skill_dir.name}/{hit}" for hit in _hardcoded_home_paths(src)]
    assert not offenders, (
        "these evaluated skills resolve a path the env jail cannot redirect, so a "
        f"live eval would touch real state through it: {offenders}"
    )


def test_the_absolute_path_guard_can_actually_fail(tmp_path):
    """MUTATION: the guard above passes today. Prove that is a result, not a no-op.

    Also proves the docstring exemption is not a blanket exemption — the same path
    in a docstring is ignored, in code it is caught.
    """
    prose = tmp_path / "prose.py"
    prose.write_text('"""Rejects file:///Users/x/repos/A as a remote."""\nX = 1\n')
    assert _hardcoded_home_paths(prose) == []

    code = tmp_path / "code.py"
    code.write_text('STATE = "/Users/broomva/.config/broomva"\n')
    assert _hardcoded_home_paths(code) == ["code.py:1"]
