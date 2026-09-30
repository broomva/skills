"""The world one trial runs in: a jailed HOME with the workspace at ``~/broomva``.

LAYOUT (one temp root per trial)
--------------------------------
::

    <root>/
      .eval-home/                         HOME (skill_evals.jail: deny-by-default env,
        Library/Keychains/login...  ->      auth passthrough, nothing else of the real HOME)
        .gitconfig                        fixture identity, no signing
        broomva/                          cwd: a git repo, snapshot of the real workspace's
          research/entities/ docs/ roles/   knowledge graph, catalog, specs and lens registry,
          <task files>                      plus whatever the task adds
        .claude/projects/<slug>/memory/   snapshot of the real memory directory
        .config/ctx/scopes.yaml           ctx scope for ~/broomva
        .local/state/ctx/broomva/         fixture board: old rows, plus the task's peers
        .local/bin/{gh,trash,p9}          stubs, first on PATH
      origin.git/                         bare remote, so push/pull work offline
      stubs.json  stub-logs/  stub-state/ stub fixture data and call logs (graders read these)
      arm-settings.json  mcp.json         the arm's --settings, the Paseo MCP stub

The cwd is ``~/broomva`` for the same reason the real sessions' is: memory files and
role-x output name paths that way, and the auto-memory directory is keyed on the cwd.
The runner's own jail puts HOME *inside* the cwd, which would leave every
``~/...`` path in the memory snapshot pointing nowhere.

Every piece of state is built for every arm (see ``arms.py``). The trial is
disposable: the root is deleted afterwards unless ``--keep-workspaces``.

THE CORPUS IS THE OPERATOR'S, AND IT NEVER ENTERS THE REPO
----------------------------------------------------------
The knowledge graph and memory are snapshotted from the real workspace once per
run (:func:`snapshot_corpus`), read-only, into the run's output directory, and
cloned from there into each trial. This repo is public; the tasks name paths and
facts, the corpus itself is never committed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))

from skill_evals import jail as jail_mod  # noqa: E402
from skill_evals.ctx_ablation import arms as arms_mod  # noqa: E402

DEFAULT_WORKSPACE_SRC = Path.home() / "broomva"
DEFAULT_MEMORY_SRC = (Path.home() / ".claude" / "projects"
                      / re.sub(r"[^A-Za-z0-9]", "-", str(Path.home() / "broomva")) / "memory")
#: What of the real workspace a case gets. The knowledge graph and its catalog (what
#: role-x reads and names), the specs, and the lens registry role-x selects from.
DEFAULT_INCLUDE = ("research/entities", "docs/knowledge-index.md", "docs/specs", "roles")

SCOPE_ID = "broomva"
#: Fixed so a fixture commit's sha depends only on its content.
FIXTURE_DATE = "2026-09-01T12:00:00+0000"
STUB_NAMES = ("gh", "trash", "p9", "paseo")


class FixtureError(RuntimeError):
    """The case could not be built. Run-invariant causes are caught by preflight."""


def project_slug(path: Path | str) -> str:
    """The CLI's auto-memory key for a cwd: every non-alphanumeric becomes ``-``.

    Measured, not assumed: a probe with ``MEMORY.md`` at this slug under a jailed
    HOME had its canary read back, and each trial re-checks that the ``init``
    event's cwd is the path this slug was computed from.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


@dataclass(frozen=True)
class CaseLayout:
    root: Path

    @property
    def home(self) -> Path:
        return jail_mod.jail_home(self.root)

    @property
    def workspace(self) -> Path:
        return self.home / "broomva"

    @property
    def local_bin(self) -> Path:
        return self.home / ".local" / "bin"

    @property
    def logs(self) -> Path:
        return self.root / "stub-logs"

    @property
    def origin(self) -> Path:
        return self.root / "origin.git"

    @property
    def settings(self) -> Path:
        return self.root / "arm-settings.json"

    @property
    def mcp_config(self) -> Path:
        return self.root / "mcp.json"

    @property
    def stubs_config(self) -> Path:
        return self.root / "stubs.json"

    @property
    def memory_dir(self) -> Path:
        return self.home / ".claude" / "projects" / project_slug(self.workspace) / "memory"

    @property
    def ctx_store(self) -> Path:
        return self.home / ".local" / "state" / "ctx" / SCOPE_ID

    def env(self) -> dict[str, str]:
        """The trial's environment: the jail's, with the stubs first on PATH, and
        every route to real GitHub failing closed. PATH order shadows ``gh``; an
        absolute ``gh`` still finds the keychain the jail links in, so it gets a
        token that authenticates nothing. The system gitconfig (Xcode's sets the
        osxkeychain credential helper) is skipped and git never prompts, so a push
        to a real remote fails instead of authenticating; git accepts only file://
        remotes."""
        env = jail_mod.build_case_env(self.root)
        env["PATH"] = f"{self.local_bin}{os.pathsep}{env.get('PATH', '')}"
        env.update({
            "GH_TOKEN": "ctxabl-no-real-github",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            # Only file:// remotes: https and ssh (whose keys come from the passwd
            # entry's ~/.ssh, not $HOME) are refused by git itself. The fixture's
            # origin is a local bare repo.
            "GIT_ALLOW_PROTOCOL": "file",
            "GIT_SSH_COMMAND": "false",
        })
        return env


# ---------------------------------------------------------------------------
# corpus: a read-only snapshot of the operator's knowledge, taken once per run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Corpus:
    root: Path
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def workspace(self) -> Path:
        return self.root / "broomva"

    @property
    def memory(self) -> Path:
        return self.root / "memory"


def _copy_regular(src: Path, dest: Path, skipped: list[str]) -> None:
    """Copy regular files and directories only. A symlink in the source is skipped,
    because a link carried into a bypassPermissions trial is a path to real state."""
    if src.is_symlink():
        skipped.append(str(src))
        return
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return
    for child in sorted(src.iterdir()):
        if child.name in (".git", "__pycache__", ".DS_Store"):
            continue
        _copy_regular(child, dest / child.name, skipped)


def _tree_digest(root: Path) -> tuple[str, int, int]:
    h = hashlib.sha256()
    files = size = 0
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            data = p.read_bytes()
            h.update(str(p.relative_to(root)).encode() + b"\0" + hashlib.sha256(data).digest())
            files += 1
            size += len(data)
    return h.hexdigest(), files, size


def snapshot_corpus(
    dest: Path,
    *,
    workspace_src: Path = DEFAULT_WORKSPACE_SRC,
    memory_src: Path = DEFAULT_MEMORY_SRC,
    include: Iterable[str] = DEFAULT_INCLUDE,
) -> Corpus:
    """Copy the knowledge the trials need out of the real workspace. Read-only on the
    source. Missing pieces are recorded in the manifest, not silently dropped."""
    dest = Path(dest)
    ws_dest, mem_dest = dest / "broomva", dest / "memory"
    ws_dest.mkdir(parents=True, exist_ok=True)
    mem_dest.mkdir(parents=True, exist_ok=True)
    skipped: list[str] = []
    missing: list[str] = []
    for rel in include:
        src = Path(workspace_src) / rel
        if not src.exists():
            missing.append(rel)
            continue
        _copy_regular(src, ws_dest / rel, skipped)
    if Path(memory_src).is_dir():
        _copy_regular(Path(memory_src), mem_dest, skipped)
    else:
        missing.append(str(memory_src))
    rewritten = rewrite_home_paths(dest, Path.home())
    digest, files, size = _tree_digest(dest)
    manifest = {
        "workspace_src": str(workspace_src),
        "memory_src": str(memory_src),
        "include": list(include),
        "missing": missing,
        "skipped_symlinks": len(skipped),
        "files_with_home_paths_rewritten": rewritten,
        "files": files,
        "bytes": size,
        "sha256": digest,
        "memory_index_chars": _chars(mem_dest / "MEMORY.md"),
        "taken_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return Corpus(dest, manifest)


def load_corpus(dest: Path) -> Corpus:
    manifest_path = Path(dest) / "manifest.json"
    if not manifest_path.is_file():
        raise FixtureError(f"no corpus snapshot at {dest} (manifest.json missing)")
    return Corpus(Path(dest), json.loads(manifest_path.read_text(encoding="utf-8")))


#: Text files whose absolute real-home paths are rewritten to ``~`` in the snapshot.
_TEXT_SUFFIXES = (".md", ".json", ".yaml", ".yml", ".txt", ".html", ".toml", ".jsonl")


def rewrite_home_paths(root: Path, real_home: Path) -> int:
    """Point absolute real-home paths in the snapshot at the case HOME instead.

    Memory and KG files name paths like ``/Users/<op>/broomva/...``. In a trial the
    home is the jail, so ``~/broomva/...`` is the same place the author meant, and
    the absolute spelling is a door to the operator's real files. Returns the number
    of files changed; the manifest records it.
    """
    prefix = str(real_home).rstrip("/")
    pattern = re.compile(re.escape(prefix) + r"(?=/|\b)")
    changed = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new = pattern.sub("~", text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
    return changed


def _chars(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8"))
    except OSError:
        return 0


def clone_tree(src: Path, dest: Path) -> None:
    """Copy *src* to *dest* (which must not exist). APFS clones when available: the
    corpus is ~1,500 files and every trial takes a private copy of it."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        proc = subprocess.run(["cp", "-cR", str(src), str(dest)], capture_output=True, text=True)
        if proc.returncode == 0:
            return
        if dest.exists():
            shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=False)


# ---------------------------------------------------------------------------
# the case
# ---------------------------------------------------------------------------


def _run(argv: list[str], cwd: Path, env: Mapping[str, str], *, check: bool = True,
         input_text: str | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(argv, cwd=str(cwd), env=dict(env), capture_output=True, text=True,
                          input=input_text, timeout=120)
    if check and proc.returncode != 0:
        raise FixtureError(f"{' '.join(argv[:4])} failed ({proc.returncode}): {proc.stderr.strip()[:400]}")
    return proc


def expand(value: Any, variables: Mapping[str, str], *, regex: bool = False) -> Any:
    """Replace ``${name}`` in strings (recursively). An unknown name raises: an empty
    substitution inside a regex matches everything, which is a vacuous grader. With
    ``regex=True`` each value is escaped, so a branch name's ``.`` or a path's ``+``
    is matched literally."""
    if isinstance(value, str):
        def sub(m: re.Match) -> str:
            key = m.group(1)
            if key not in variables:
                raise KeyError(f"unknown template variable ${{{key}}}")
            return re.escape(variables[key]) if regex else variables[key]
        return re.sub(r"\$\{([A-Za-z0-9_:./-]+)\}", sub, value)
    if isinstance(value, list):
        return [expand(v, variables, regex=regex) for v in value]
    if isinstance(value, dict):
        return {k: expand(v, variables, regex=regex) for k, v in value.items()}
    return value


def _ts(now: float, minutes_ago: float) -> str:
    t = now - minutes_ago * 60
    whole = int(t)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(whole)) + ".%03dZ" % int((t - whole) * 1000)


#: Old rows every board carries: sessions in this checkout that finished hours ago.
#: Outside ctx's 6 h live window, inside its 48 h recent window, so every brief has
#: the production shape (a header and some history) without implying a live peer.
BASELINE_PEERS: tuple[dict[str, Any], ...] = (
    {"session_id": "0b8e2d41-6c1f-4a7e-9d35-81f0c2e4a6b9", "branch": "main", "age_min": 7 * 60,
     "arc_line": "ARC-STATUS: MERGED skills#240 fixture docs refresh"},
    {"session_id": "5d27a9c3-e8b0-4f16-a2d4-7c93e1f0b852", "branch": "main", "age_min": 20 * 60,
     "arc_line": "ARC-STATUS: DONE weekly review notes filed"},
    {"session_id": "a1f4c6e8-2b9d-4d03-8e57-3c6a9b1d2f40", "branch": "main", "age_min": 31 * 60,
     "arc_line": "ARC-STATUS: CLOSED stale lint branch"},
)


def _arc_status(line: str) -> str:
    m = re.match(r"^ARC-STATUS: ([A-Z]+)", line or "")
    word = m.group(1) if m else ""
    return word if word in ("MERGED", "CLOSED", "DONE", "BLOCKED") else "OTHER"


def _peer_events(peer: Mapping[str, Any], layout: CaseLayout, now: float) -> list[dict[str, Any]]:
    cwd_spec = str(peer.get("cwd", "ws"))
    cwd = layout.workspace if cwd_spec == "ws" else layout.home / cwd_spec.removeprefix("home:")
    base = {
        "v": 1,
        "session_id": peer["session_id"],
        "cwd": os.path.realpath(cwd),
        "repo": os.path.realpath(layout.workspace / ".git"),
        "branch": peer.get("branch"),
    }
    if peer.get("paseo_agent_id"):
        base["paseo_agent_id"] = peer["paseo_agent_id"]
    age = float(peer.get("age_min", 10))
    started = age + float(peer.get("ran_min", 25))
    events = [{**base, "type": "session.start", "ts": _ts(now, started), "payload": {}}]
    stop_payload: dict[str, Any] = {}
    if peer.get("arc_line"):
        stop_payload = {"arc_status": _arc_status(peer["arc_line"]), "arc_line": peer["arc_line"][:120]}
    events.append({**base, "type": "session.stop", "ts": _ts(now, age), "payload": stop_payload})
    return events


def write_ctx_store(layout: CaseLayout, peers: Iterable[Mapping[str, Any]], env: Mapping[str, str],
                    *, now: float | None = None) -> int:
    """Write the scope config and the board log, then have ctx.py fold it.

    The fold is the check: rows are counted by ctx's own reader, so a fixture event
    that breaks the schema (and would be skipped, silently, by every brief) fails
    the build here instead of quietly emptying the ctx arm.
    """
    now = time.time() if now is None else now
    cfg = layout.home / ".config" / "ctx"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "scopes.yaml").write_text(
        f"version: 1\nscopes:\n  {SCOPE_ID}:\n    - {layout.workspace}\n", encoding="utf-8")
    all_peers = list(BASELINE_PEERS) + list(peers)
    events = [e for p in all_peers for e in _peer_events(p, layout, now)]
    events.sort(key=lambda e: e["ts"])
    layout.ctx_store.mkdir(parents=True, exist_ok=True)
    with open(layout.ctx_store / "events.jsonl", "w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    proc = _run([sys.executable, "-I", str(arms_mod.CTX_SCRIPTS / "ctx.py"), "-C", str(layout.workspace),
                 "board", "--json"], layout.workspace, env)
    try:
        board = json.loads(proc.stdout)
    except ValueError as exc:
        raise FixtureError(f"ctx board did not return JSON: {proc.stdout[:200]!r}") from exc
    sessions = board.get("sessions") or {}
    if len(sessions) != len(all_peers) or board.get("skipped_lines"):
        raise FixtureError(
            f"ctx folded {len(sessions)} session(s) and skipped {board.get('skipped_lines')} line(s) "
            f"from {len(all_peers)} fixture peers: the fixture breaks the event schema")
    return len(sessions)


def write_stub_wrappers(layout: CaseLayout, python: str) -> None:
    layout.local_bin.mkdir(parents=True, exist_ok=True)
    for name in STUB_NAMES:
        script = arms_mod.STUBS_DIR / f"{name}.py"
        wrapper = layout.local_bin / name
        wrapper.write_text(
            "#!/bin/sh\n"
            f"CTXABL_CASE_ROOT={shlex.quote(str(layout.root))} "
            f"exec {shlex.quote(python)} -I {shlex.quote(str(script))} \"$@\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)


def write_mcp_config(layout: CaseLayout, python: str) -> None:
    layout.mcp_config.write_text(json.dumps({"mcpServers": {"paseo": {
        "type": "stdio",
        "command": python,
        "args": ["-I", str(arms_mod.STUBS_DIR / "paseo_mcp.py")],
        "env": {"CTXABL_CASE_ROOT": str(layout.root)},
    }}}, indent=2), encoding="utf-8")


def _git_vars(layout: CaseLayout, env: Mapping[str, str]) -> dict[str, str]:
    out = _run(["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads"],
               layout.workspace, env).stdout
    variables = {}
    for line in out.splitlines():
        name, _, sha = line.partition(" ")
        variables[f"sha:{name}"] = sha
        variables[f"short:{name}"] = sha[:7]
    head = _run(["git", "symbolic-ref", "--short", "-q", "HEAD"], layout.workspace, env, check=False)
    variables["head_branch"] = head.stdout.strip()
    return variables


@dataclass
class Case:
    """A built trial world plus the variables its graders are templated with."""

    layout: CaseLayout
    env: dict[str, str]
    variables: dict[str, str]
    ctx_sessions: int = 0


def build_case(
    root: Path,
    task_fixture: Mapping[str, Any],
    corpus: Corpus,
    *,
    python: str = sys.executable,
    link_auth: bool = True,
    now: float | None = None,
) -> Case:
    """Build everything a trial needs except the arm's settings file."""
    layout = CaseLayout(Path(root).resolve())
    jail_mod.prepare_jail(layout.root, link_auth=link_auth)
    env = layout.env()
    home = layout.home
    (home / ".gitconfig").write_text(
        "[user]\n\tname = Eval Fixture\n\temail = eval-fixture@example.invalid\n"
        "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n"
        "[advice]\n\tdetachedHead = false\n",
        encoding="utf-8",
    )

    # The workspace: the knowledge snapshot, then the task's own files, one commit.
    if corpus.workspace.is_dir():
        clone_tree(corpus.workspace, layout.workspace)
    else:
        layout.workspace.mkdir(parents=True)
    for rel, content in (task_fixture.get("files") or {}).items():
        dest = layout.workspace / rel
        if not dest.resolve().is_relative_to(layout.workspace.resolve()):
            raise FixtureError(f"fixture file {rel!r} escapes the workspace")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    git_env = {**env, "GIT_AUTHOR_DATE": FIXTURE_DATE, "GIT_COMMITTER_DATE": FIXTURE_DATE}
    _run(["git", "init", "-q", "-b", "main"], layout.workspace, git_env)
    _run(["git", "add", "-A"], layout.workspace, git_env)
    _run(["git", "commit", "-q", "--allow-empty", "-m", "workspace snapshot"], layout.workspace, git_env)
    _run(["git", "clone", "-q", "--bare", str(layout.workspace), str(layout.origin)], layout.root, git_env)
    _run(["git", "remote", "add", "origin", str(layout.origin)], layout.workspace, git_env)
    _run(["git", "fetch", "-q", "origin"], layout.workspace, git_env)
    _run(["git", "branch", "-q", "--set-upstream-to=origin/main", "main"], layout.workspace, git_env)

    # The memory snapshot, in every arm. Whether it is INJECTED is the arm's call.
    if corpus.memory.is_dir():
        clone_tree(corpus.memory, layout.memory_dir)
    else:
        layout.memory_dir.mkdir(parents=True)

    # The stubs are on PATH before setup runs, so a setup step that calls gh or
    # trash reaches the stub, never the real binary.
    write_stub_wrappers(layout, python)
    layout.stubs_config.write_text("{}", encoding="utf-8")
    setup_env = {**git_env, "WS": str(layout.workspace), "CASE_ROOT": str(layout.root)}
    for cmd in task_fixture.get("setup") or []:
        proc = _run(["/bin/sh", "-c", cmd], layout.workspace, setup_env, check=False)
        if proc.returncode != 0:
            raise FixtureError(f"setup step failed ({proc.returncode}): {cmd!r}: {proc.stderr.strip()[:300]}")

    variables = {
        "ws": str(layout.workspace),
        "home": str(home),
        "memory": str(layout.memory_dir),
        "origin": str(layout.origin),
        **_git_vars(layout, env),
    }
    for key, val in (task_fixture.get("vars") or {}).items():
        variables[str(key)] = str(expand(val, variables))
    # An empty value substituted into a regex matches everything; drop it, so a
    # reference to it fails as an unknown variable instead.
    variables = {k: v for k, v in variables.items() if v}

    stubs = expand(task_fixture.get("stubs") or {}, variables)
    layout.stubs_config.write_text(json.dumps(stubs, indent=2, sort_keys=True), encoding="utf-8")
    write_mcp_config(layout, python)
    peers = expand(task_fixture.get("ctx_peers") or [], variables)
    ctx_sessions = write_ctx_store(layout, peers, env, now=now)
    return Case(layout=layout, env=env, variables=variables, ctx_sessions=ctx_sessions)


def write_arm_settings(case: Case, arm: arms_mod.Arm, rt: arms_mod.HookRuntime) -> dict[str, Any]:
    settings = arms_mod.build_settings(arm, case.layout.root, rt)
    case.layout.settings.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return settings


def sanitize(text: str, layout: CaseLayout) -> str:
    """Replace the case's temp path with ``<case>`` in text headed for a record, so a
    committed report carries no machine-specific paths."""
    for root in {str(layout.root), os.path.realpath(layout.root)}:
        text = text.replace(root, "<case>")
    return text


def read_stub_logs(layout: CaseLayout) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    if not layout.logs.is_dir():
        return out
    for path in sorted(layout.logs.glob("*.jsonl")):
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        out[path.stem] = rows
    return out


__all__ = [
    "BASELINE_PEERS",
    "Case",
    "CaseLayout",
    "Corpus",
    "FixtureError",
    "build_case",
    "clone_tree",
    "expand",
    "load_corpus",
    "project_slug",
    "read_stub_logs",
    "rewrite_home_paths",
    "sanitize",
    "snapshot_corpus",
    "write_arm_settings",
    "write_ctx_store",
]
