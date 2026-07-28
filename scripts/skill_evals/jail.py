#!/usr/bin/env python3
"""Environment jail — the half of case isolation the fresh temp cwd never covered.

BRO-2018. The harness already gives every trial a fresh, non-git temp directory to
run in. That isolates the *filesystem the agent starts in*. It does not isolate the
*environment a skill's own scripts resolve their state from* — and the skills under
test resolve almost all of it from ``$HOME``:

* ``skills/orchestration/p9/scripts/p9.py`` — ``BROOMVA_P9_HOME`` or
  ``XDG_CONFIG_HOME`` or ``Path.home()/".config"`` → ``~/.config/broomva/p9``;
* ``skills/knowledge/kg/scripts/kg.py`` — ``Path.home()/"broomva"``, i.e. it locates
  the *entire workspace*, and with it ``research/entities/``, off ``$HOME``.

A positive trial is supposed to make the agent actually run those scripts; that is
what a trigger eval is for. So the more faithfully the harness works, the more
reliably it corrupts real state. ``subprocess.run`` in :class:`~skill_evals.runner.LiveRunner`
passed no ``env=`` at all, so the child inherited the full parent environment.

The fix is a jail: a per-workspace ``HOME`` plus a deny-by-default allowlist for
everything else, so ``~`` and every XDG path a skill script consults land inside
the temp workspace and vanish with it.

Why deny-by-default rather than a list of overrides to unset: an allowlist fails
*closed* when a new skill invents ``BROOMVA_WHATEVER_HOME``. A denylist has to be
edited to stay correct, which means it is wrong between the day the skill lands and
the day someone notices. The same reasoning produced ``filterPassthroughEnv`` in
apps/maestro for the sibling problem (a bypassPermissions CLI inheriting secrets).

MEASURED, NOT ASSUMED — the macOS auth constraint
-------------------------------------------------
Redirecting ``HOME`` on its own **breaks the CLI outright**: it reports
``Not logged in · Please run /login`` and every trial ERRORs. The subscription
OAuth token lives in the login keychain, and the login keychain lives *under
$HOME*::

    $ security find-generic-password -s "Claude Code-credentials"
    keychain: "/Users/<user>/Library/Keychains/login.keychain-db"

Setting ``CLAUDE_CONFIG_DIR`` back to the real ``~/.claude`` does not rescue it,
and neither does copying ``~/.claude.json`` into the jail — both were tried, both
still report ``Not logged in``. What does work, verified live against CLI 2.1.220,
is linking the keychain back in: ``HOME=<jail>`` plus
``<jail>/Library/Keychains/login.keychain-db* -> ~/Library/Keychains/…`` returns
``is_error=false``, and every byte the CLI writes (``.claude.json``, ``.claude/``,
``Library/Caches``) lands inside the jail.

So the jail is HOME-redirect **plus a narrow, explicit auth passthrough**. That
passthrough is the one deliberate hole in the wall, it is listed in
:data:`AUTH_PASSTHROUGH`, and :func:`verify_jail` proves the rest of the wall holds.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

#: The jail's ``HOME``, as a child of the case workspace.
#:
#: Deliberately *inside* the workspace rather than a sibling temp dir: it makes the
#: jail a pure function of the workspace path, so nothing has to be threaded through
#: the ``Runner`` protocol (which the test suite and BRO-2006's ablation arm both
#: implement), and ``--keep-workspaces`` keeps the jail alongside the run that made
#: it. The workspace already carries a harness-managed dot-dir (``.claude/skills``),
#: so this is the existing idiom, not a new one.
JAIL_DIRNAME = ".eval-home"

#: Environment variables that survive into a case run. Everything else is dropped.
#:
#: The bar for adding one: the CLI cannot run without it, AND it cannot be used to
#: resolve a path outside the jail. ``HOME`` is absent on purpose — it is *set*, not
#: passed through (see :func:`build_case_env`), and so are the XDG vars.
#:
#: ``ANTHROPIC_API_KEY`` is the named hazard this closes: a subscription CLI handed
#: an API key silently bills a different account. It is not listed, so it is dropped
#: — and ``test_api_key_never_survives_the_jail`` pins that, because the failure mode
#: is someone widening this set later, not someone adding the key back by hand.
PASSTHROUGH_ENV = frozenset(
    {
        # Process basics. Without PATH the CLI cannot find node/git/ripgrep.
        "PATH",
        "SHELL",
        "TERM",
        # macOS keychain access is looked up per-user; USER/LOGNAME are consulted by
        # securityd and cost nothing to keep.
        "USER",
        "LOGNAME",
        # Locale — text handling only; carries no path.
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        # Corporate TLS. Dropping these turns a proxied network into an opaque
        # connection failure that reads as a skill result.
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "NODE_EXTRA_CA_CERTS",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "all_proxy",
    }
)

#: Paths, relative to the real ``$HOME``, linked back into the jail so the CLI can
#: still authenticate. THE deliberate hole in the wall — keep it as small as the
#: measurement allows, and never widen it to make an unrelated thing work.
#:
#: macOS: the login keychain holds the subscription OAuth token. The glob picks up
#: ``login.keychain-db`` and its sidecar files; it does NOT link the whole
#: ``Library/Keychains`` directory, which also contains the per-user iCloud keychain.
#:
#: Linux/CI: no keychain — the CLI writes ``~/.claude/.credentials.json``.
AUTH_PASSTHROUGH: dict[str, tuple[str, ...]] = {
    "darwin": ("Library/Keychains/login.keychain-db*",),
    "linux": (".claude/.credentials.json",),
}

#: Real state a leak would land in, checked around a live suite. Narrow on purpose:
#: see :class:`RealStateWatch` for why this is advisory rather than fatal.
DEFAULT_WATCHED_PATHS: tuple[str, ...] = ("~/.config/broomva",)


def jail_home(workspace: Path) -> Path:
    """Where :func:`build_case_env` will point ``HOME``. Pure; creates nothing."""
    return Path(workspace) / JAIL_DIRNAME


def _auth_globs(platform: str | None = None) -> tuple[str, ...]:
    key = (platform or sys.platform).lower()
    if key.startswith("darwin"):
        return AUTH_PASSTHROUGH["darwin"]
    if key.startswith("linux"):
        return AUTH_PASSTHROUGH["linux"]
    return ()


def link_auth_material(
    home: Path, *, real_home: Path | None = None, platform: str | None = None
) -> list[Path]:
    """Symlink the credential material listed in :data:`AUTH_PASSTHROUGH` into *home*.

    Returns the links created. Missing sources are skipped silently — a replay-only
    or CI machine has no keychain, and refusing to build a jail there would make the
    jail the reason tests cannot run.
    """
    src_root = Path(real_home) if real_home is not None else Path(os.path.expanduser("~"))
    created: list[Path] = []
    for pattern in _auth_globs(platform):
        rel = Path(pattern)
        for src in sorted(src_root.glob(pattern)):
            dest = Path(home) / rel.parent / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() or dest.is_symlink():
                continue
            dest.symlink_to(src)
            created.append(dest)
    return created


def prepare_jail(
    workspace: Path, *, link_auth: bool = True, real_home: Path | None = None
) -> Path:
    """Create the jail ``HOME`` for *workspace* and return it.

    Called by the live runner immediately before it spawns a process, so replay —
    which spawns nothing and therefore cannot leak — never builds one.
    """
    home = jail_home(workspace)
    for sub in ("", ".config", ".cache", ".local/share", ".local/state", "tmp"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    if link_auth:
        link_auth_material(home, real_home=real_home)
    return home


def build_case_env(
    workspace: Path, parent_env: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The complete environment for one case run. Deny-by-default.

    Everything a skill script could resolve a path from is pointed inside the jail;
    everything else has to be named in :data:`PASSTHROUGH_ENV` to survive.
    """
    env_in = os.environ if parent_env is None else parent_env
    home = jail_home(workspace)
    env = {k: v for k, v in env_in.items() if k in PASSTHROUGH_ENV}
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
            # Not isolation for its own sake: a skill that writes a scratch file to
            # $TMPDIR and a *concurrent* trial doing the same is a cross-trial
            # collision, which reads as flake rather than as the shared-state bug it
            # is. --jobs makes that reachable.
            "TMPDIR": str(home / "tmp"),
        }
    )
    return env


# ---------------------------------------------------------------------------
# proof that the jail holds, on this machine, before a live suite spends money
# ---------------------------------------------------------------------------

#: Resolves the paths a skill script would, and reports where they actually landed.
#: Run as a SUBPROCESS under the jailed env — never in-process. A parent-process
#: check would read this interpreter's startup snapshot of the environment and pass
#: while the child sees something else entirely, which is precisely the class of
#: false-green this file exists to close.
_PROBE_SRC = """
import json, os
from pathlib import Path
print(json.dumps({
    "home": str(Path.home()),
    "tilde": os.path.expanduser("~"),
    "xdg_config": os.environ.get("XDG_CONFIG_HOME", ""),
    "p9_state": os.environ.get("BROOMVA_P9_HOME")
        or str(Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "broomva"),
    "kg_workspace": str(Path.home() / "broomva"),
    "api_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
}))
"""


@dataclass(frozen=True)
class JailVerdict:
    """Where a probe's path resolution landed, and whether any of it escaped."""

    resolved: dict[str, str] = field(default_factory=dict)
    escapes: list[str] = field(default_factory=list)

    @property
    def holds(self) -> bool:
        return not self.escapes


def verify_jail(workspace: Path, *, python: str | None = None) -> JailVerdict:
    """Prove, by launching a real subprocess, that the jail contains path resolution.

    The two names checked are not arbitrary: ``p9_state`` and ``kg_workspace``
    reproduce, exactly, how the two evaluated skills with real state stores resolve
    theirs. If either lands outside the workspace, a live run of that skill would
    write the user's actual p9 store or actual knowledge graph.
    """
    home = jail_home(workspace)
    proc = subprocess.run(
        [python or sys.executable, "-c", _PROBE_SRC],
        cwd=str(workspace),
        env=build_case_env(workspace),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return JailVerdict(escapes=[f"probe failed to run: {proc.stderr.strip()[:300]}"])
    import json as _json

    try:
        resolved = _json.loads(proc.stdout)
    except ValueError as exc:
        return JailVerdict(escapes=[f"probe emitted unparseable output: {exc}"])

    escapes: list[str] = []
    root = str(home)
    for key in ("home", "tilde", "xdg_config", "p9_state", "kg_workspace"):
        value = str(resolved.get(key, ""))
        if not value or not value.startswith(root):
            escapes.append(f"{key} resolved to {value!r}, outside the jail at {root!r}")
    if resolved.get("api_key_present"):
        escapes.append(
            "ANTHROPIC_API_KEY survived into the case environment — a subscription "
            "CLI handed an API key bills a different account"
        )
    return JailVerdict(resolved={k: str(v) for k, v in resolved.items()}, escapes=escapes)


# ---------------------------------------------------------------------------
# advisory watch over the real state a leak would land in
# ---------------------------------------------------------------------------


def _snapshot_one(path: Path) -> dict[str, tuple[int, int]]:
    if not path.exists():
        return {}
    if path.is_file():
        st = path.stat()
        return {str(path): (st.st_mtime_ns, st.st_size)}
    out: dict[str, tuple[int, int]] = {}
    for p in sorted(path.rglob("*")):
        try:
            st = p.stat()
        except OSError:
            continue
        if p.is_file():
            out[str(p)] = (st.st_mtime_ns, st.st_size)
    return out


@dataclass
class RealStateWatch:
    """Before/after fingerprint of the real state stores a leak would land in.

    ADVISORY, not fatal, and that is a deliberate calibration rather than timidity.
    These stores are shared: a p9 watcher running in another terminal writes
    ``~/.config/broomva/p9`` on its own schedule, so a broad mtime sweep cannot tell
    our escape apart from somebody else's legitimate write. Making it fatal by
    default would manufacture exactly the false-fail class that
    ``research/entities/pattern/anti-vacuity-fixes-overshoot-into-noise.md``
    documents — a check that fails for reasons unrelated to the defect, which gets
    muted, which is worse than not having it.

    The *hard* guarantee is :func:`verify_jail`, which is deterministic and has no
    concurrent-writer confound. This watch exists for the ticket's other complaint —
    that a leak is currently **invisible** — so it reports, loudly, with the paths
    named, and ``--fail-on-real-state-change`` promotes it to fatal for anyone who
    knows their stores are quiet.
    """

    paths: tuple[str, ...] = DEFAULT_WATCHED_PATHS
    before: dict[str, tuple[int, int]] = field(default_factory=dict, init=False)

    def _expand(self) -> list[Path]:
        return [Path(os.path.expanduser(p)) for p in self.paths]

    def snapshot(self) -> None:
        self.before = {}
        for p in self._expand():
            self.before.update(_snapshot_one(p))

    def changes(self) -> list[str]:
        after: dict[str, tuple[int, int]] = {}
        for p in self._expand():
            after.update(_snapshot_one(p))
        out: list[str] = []
        for path in sorted(set(self.before) | set(after)):
            was, now = self.before.get(path), after.get(path)
            if was == now:
                continue
            if was is None:
                out.append(f"created: {path}")
            elif now is None:
                out.append(f"deleted: {path}")
            else:
                out.append(f"modified: {path}")
        return out


def describe_jail(workspace: Path) -> str:
    """One line for the run banner, so the isolation in force is never implicit."""
    home = jail_home(workspace)
    linked = _auth_globs() or ("(none for this platform)",)
    return f"env-jail HOME={home} passthrough={len(PASSTHROUGH_ENV)} vars auth={','.join(linked)}"


__all__ = [
    "AUTH_PASSTHROUGH",
    "DEFAULT_WATCHED_PATHS",
    "JAIL_DIRNAME",
    "JailVerdict",
    "PASSTHROUGH_ENV",
    "RealStateWatch",
    "build_case_env",
    "describe_jail",
    "jail_home",
    "link_auth_material",
    "prepare_jail",
    "verify_jail",
]
