"""Shared fixtures for fleet-reconcile.

`world`: a scratch HOME holding real git repos laid out the way the captured
fixture's path templates expect (tests/capture_fixtures.py):

    {HOME}/broomva            scope broomva (with a nested repo, skills)
    {HOME}/broomva/skills     scope broomva
    {HOME}/client/sri         scope sri
    {HOME}/wt/<scope>-<n>     git worktrees of the scope's main repo
    {HOME}/other/<n>          repos in no scope
    {HOME}/gone/<n>           never created (worktrees removed after merge)

plus scopes.yaml, a fleet.json, and a copy of the captured fixture with
{HOME} filled in, the core's event logs among them.

`make_session` builds a snapshot session for the classifier tests.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
CTX_SCRIPTS = SKILL.parent / "ctx-core" / "scripts"
FIXTURE = HERE / "fixtures" / "cc-2.1.280"
FLEET = SCRIPTS / "fleet"
for _p in (str(CTX_SCRIPTS), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FAKE_BEARER = "FIXTURE-FAKE-BEARER-NOT-A-SECRET"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=str(cwd),
                   check=True, capture_output=True)


def _repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "-b", "main", cwd=path)
    _git("commit", "-q", "--allow-empty", "-m", "init", cwd=path)


@dataclass
class World:
    home: Path
    fixture: Path
    config: Path
    state: Dict[str, Path] = field(default_factory=dict)

    def fleet(self, *args: str, env: Optional[Dict[str, str]] = None, check: bool = False,
              timeout: float = 120) -> subprocess.CompletedProcess:
        e = dict(os.environ)
        e.update(env or {})
        proc = subprocess.run(["/bin/sh", str(FLEET), *args], capture_output=True, text=True, env=e,
                              timeout=timeout)
        if check:
            assert proc.returncode == 0, proc.stdout + proc.stderr
        return proc

    def write_config(self, **overrides: Any) -> Dict[str, Any]:
        cfg = {"v": 1, "scopes": {
            "broomva": {"dispatch_enabled": 1, "dry_run": 1, "mode": "report",
                        "state_dir": str(self.state["broomva"])},
            "sri": {"dispatch_enabled": 1, "dry_run": 1, "mode": "report", "state_dir": str(self.state["sri"])},
        }}
        for key, value in overrides.items():
            cfg["scopes"]["broomva"][key] = value
        self.config.write_text(json.dumps(cfg))
        return cfg


def _templates(fixture: Path) -> Dict[str, set]:
    found: Dict[str, set] = {}
    for p in fixture.rglob("*"):
        if p.is_file():
            for m in re.finditer(r"\{HOME\}/(wt|other|broomva|client)(/[A-Za-z0-9._-]+)?", p.read_text()):
                found.setdefault(m.group(1), set()).add(m.group(2) or "")
    return found


def build_world(root: Path, home: Optional[Path] = None) -> World:
    """A world under `root`. With `home`, the repos, scopes.yaml and the core's
    logs already built there are reused (read-only), and only the fixture copy,
    the config and the state dirs are new."""
    if home is not None:
        return _fork_world(root, home)
    home = root / "home"
    home.mkdir()
    broomva, skills, sri = home / "broomva", home / "broomva" / "skills", home / "client" / "sri"
    for r in (broomva, skills, sri):
        _repo(r)
    (broomva / ".gitignore").write_text("skills/\nsub/\n")
    (broomva / "sub").mkdir()
    tpl = _templates(FIXTURE)
    for sub in sorted(tpl.get("wt", ())):
        name = sub.lstrip("/")
        main = sri if name.startswith("sri-") else broomva
        (home / "wt").mkdir(exist_ok=True)
        _git("worktree", "add", "-q", "--detach", str(home / "wt" / name), cwd=main)
    for sub in sorted(tpl.get("other", ())):
        _repo(home / "other" / sub.lstrip("/"))
    cfg = home / ".config" / "ctx"
    cfg.mkdir(parents=True)
    (cfg / "scopes.yaml").write_text("version: 1\nscopes:\n  broomva:\n    - ~/broomva\n    - ~/broomva/skills\n"
                                     "  sri:\n    - ~/client/sri\n")
    real_home = os.path.realpath(str(home))
    fixture = root / "fixture"
    for p in FIXTURE.rglob("*"):
        if p.is_file():
            dst = fixture / p.relative_to(FIXTURE)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(p.read_text().replace("{HOME}", real_home))
    for scope in ("broomva", "sri"):
        src = fixture / "ctx" / scope / "events.jsonl"
        if src.is_file():
            store = home / ".local" / "state" / "ctx" / scope
            store.mkdir(parents=True)
            shutil.copy(src, store / "events.jsonl")
    remotes = {
        os.path.realpath(str(broomva / ".git")): "https://github.com/broomva/workspace.git",
        os.path.realpath(str(skills / ".git")): "git@github.com:broomva/skills.git",
        os.path.realpath(str(sri / ".git")): "https://example.invalid/client/sri.git",
    }
    (fixture / "git").mkdir(exist_ok=True)
    (fixture / "git" / "remotes.json").write_text(json.dumps(remotes))
    w = World(home=home, fixture=fixture, config=cfg / "fleet.json")
    w.state = {s: home / ".local" / "state" / "fleet-reconcile" / s for s in ("broomva", "sri")}
    w.write_config()
    return w


def _fork_world(root: Path, home: Path) -> World:
    base = home.parent
    fixture = root / "fixture"
    shutil.copytree(str(base / "fixture"), str(fixture))
    w = World(home=home, fixture=fixture, config=root / "fleet.json")
    w.state = {s: root / "state" / s for s in ("broomva", "sri")}
    w.write_config()
    return w


@pytest.fixture(scope="session")
def _base_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    old = os.environ.get("GIT_CONFIG_NOSYSTEM")
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    try:
        return build_world(tmp_path_factory.mktemp("base")).home
    finally:
        if old is None:
            os.environ.pop("GIT_CONFIG_NOSYSTEM", None)


def _enter(w: World, monkeypatch: pytest.MonkeyPatch) -> World:
    monkeypatch.setenv("HOME", str(w.home))
    monkeypatch.setenv("FLEET_CONFIG", str(w.config))
    monkeypatch.setenv("FLEET_NOTIFY", "0")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in ("CLAUDE_CONFIG_DIR", "GIT_DIR", "GIT_WORK_TREE", "FLEET_CHILD", "FLEET_SCOPE", "DRY_RUN",
                "GH_TOKEN", "PASEO_AGENT_ID"):
        monkeypatch.delenv(var, raising=False)
    return w


@pytest.fixture
def world(tmp_path: Path, _base_home: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """Shared repos (read-only), with this test's own fixture copy, config and
    state dirs. For tests that write under HOME, use fresh_world."""
    return _enter(build_world(tmp_path, home=_base_home), monkeypatch)


@pytest.fixture
def fresh_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """A world of its own, HOME included (slower: it builds the repos)."""
    return _enter(build_world(tmp_path), monkeypatch)


@pytest.fixture
def meta() -> Dict[str, Any]:
    return json.loads((FIXTURE / "meta.json").read_text())


# --------------------------------------------------------------------------
# Snapshot sessions for the classifier

NOW = 1_790_000_000.0
H = 3600.0


def make_session(**kw: Any) -> Dict[str, Any]:
    """A session as observe.py writes it, in scope broomva, idle, with a
    transcript 10 minutes old, unless the keywords say otherwise. Keyword
    shortcuts: activity_ago (seconds), no_transcript, job={...}, board={...}."""
    s: Dict[str, Any] = {
        "session_id": kw.pop("session_id", "11111111-0000-4000-8000-000000000001"),
        "name": kw.pop("name", "a-session"), "kind": kw.pop("kind", "interactive"),
        "cwd": "/w/broomva", "cwd_exists": True, "bg_id": None, "state": kw.pop("state", None),
        "pid": kw.pop("pid", 4242), "status": kw.pop("status", "idle"), "waiting_for": kw.pop("waiting_for", None),
        "started_at": NOW - 10 * H, "job": None, "board": None, "paseo": kw.pop("paseo", None),
        "transcript": {"found": True, "mtime": NOW - 600, "sub": None}, "limit_text": kw.pop("limit_text", None),
        "scope": kw.pop("scope", "broomva"), "repo": kw.pop("repo", "/w/broomva/.git"),
        "branch": kw.pop("branch", "feat/x"), "placement": kw.pop("placement", "cwd"),
        "fleet_key": kw.pop("fleet_key", None), "adopted": False, "fleet_shaped": kw.pop("fleet_shaped", False),
    }
    if "activity_ago" in kw:
        s["transcript"]["mtime"] = NOW - kw.pop("activity_ago")
    if kw.pop("no_transcript", False):
        s["transcript"] = {"found": False, "mtime": None, "sub": None}
    if "sub_ago" in kw:
        s["transcript"]["sub"] = NOW - kw.pop("sub_ago")
    if "job" in kw:
        j = {"job_id": s["session_id"][:8], "state": "done", "detail": "", "needs": "", "suggested_reply": False,
             "limit_text": False, "reset_text": None, "worktree_path": None, "worktree_branch": None,
             "updated_at": NOW - 600, "settings_path": None}
        j.update(kw.pop("job"))
        s["job"] = j
    if "board" in kw:
        b = {"scope": "broomva", "state": "stopped", "last_event": "session.stop", "last_ts": NOW - 700,
             "died_ts": None, "died_error": None, "arc_status": None, "arc_ts": None, "repo": s["repo"],
             "branch": s["branch"]}
        b.update(kw.pop("board"))
        s["board"] = b
    assert not kw, "unknown make_session keywords: %s" % sorted(kw)
    return s


def env_for(repos=None, now: float = NOW, scope: str = "broomva"):
    from fleetlib import classify

    return classify.Env(scope, now, repos if repos is not None else [
        {"repo": "/w/broomva/.git", "ok": True, "prs": []}])
