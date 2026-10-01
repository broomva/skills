"""The janitor's guard, backup and run (spec §5.5).

`fleet janitor-check <path> --owner <bg id>` runs the checks and aborts the
removal when any of them fails or can't run:

  owner_finished    the owning session finished: a terminal status on the board
                    (MERGED, CLOSED, DONE); for a scratch worktree only (of no
                    scope repo, so no board holds it), a background job the
                    listing shows done (pending the spec);
  no_live_session   no other session has a live process with its cwd in the
                    worktree, re-read from claude agents at that moment;
  pr_closed         the branch's PR, if any, is merged or closed;
  quiet_24h         no file in the worktree was modified in the last 24 h;
  no_holder         no process but the janitor's own holds the worktree (lsof),
                    and the process listing shows other processes at all: one
                    that shows only the janitor's own is a check that didn't
                    run (probe 2: a sandbox hid 26 processes);
  backup_possible   every ignored secret (.env*, *.db) can be read for the backup.

`fleet janitor-run` checks, stops the owner (claude stop), re-checks, backs up
(the diff, untracked files, ignored secrets, a branch for unpushed commits) to
<state_dir>/backups/<path hash>/, re-reads the listing, and removes with
claude rm <id>, which itself keeps a worktree with tracked changes, untracked
files or unpushed commits. Until the phase-2 janitor drill passes, removal is
refused for any worktree of a scope repo: the tick reports what it would
remove, and only scratch worktrees are removed (the drill's).
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import ctx

from . import common, ledger, observe, parsers
from .sources import SourceError, Sources

QUIET_S = 24 * 3600
BACKUP_DAYS = 14
SECRET_GLOBS = (".env*", "*.db")
SKIP_DIRS = {".git"}
#: Dependency and build output: not backed up, not searched for secrets (§5.5).
HEAVY_DIRS = {"node_modules", "target", "build", "dist", ".venv", "__pycache__", ".next"}
TERMINAL = ("MERGED", "CLOSED", "DONE")
MAX_FILES = 200000
CHECKS = ("owner_finished", "no_live_session", "pr_closed", "quiet_24h", "no_holder", "backup_possible")

Verdict = Tuple[str, str]  # ("pass" | "fail" | "not run", detail)


def _git(path: str, *args: str, timeout: float = 30) -> str:
    proc = subprocess.run(["git", "-C", path] + list(args), stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=timeout)
    if proc.returncode != 0:
        raise SourceError("git %s exited %d: %s" % (args[0], proc.returncode,
                                                    common.safe_text(proc.stderr.decode("utf-8", "replace"), 100)))
    return proc.stdout.decode("utf-8", "replace")


def _inside(cwd: Optional[str], path: str) -> bool:
    if not cwd:
        return False
    try:
        c = os.path.realpath(cwd)
    except OSError:
        return False
    return c == path or c.startswith(path.rstrip("/") + "/")


def _own(parents: Dict[int, int]) -> Set[int]:
    """The janitor's own processes in a ps reading {pid: ppid}: itself, its
    ancestors (the shell and session that started it) and its children (the
    ps and lsof it runs)."""
    me = os.getpid()
    own = {me}
    p = parents.get(me, os.getppid())
    while p and p != 1 and p not in own:
        own.add(p)
        p = parents.get(p, 0)
    own.add(os.getppid())
    own |= {pid for pid, pp in parents.items() if pp == me}
    return own


def _ps() -> Dict[int, int]:
    proc = subprocess.run(["ps", "-axo", "pid=,ppid="], stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
    if proc.returncode != 0:
        raise OSError("ps exited %d" % proc.returncode)
    out = {}
    for line in proc.stdout.decode().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            out[int(parts[0])] = int(parts[1])
    return out


class Guard:
    def __init__(self, sec: Dict[str, Any], src: Sources, path: str, owner: str,
                 now: Optional[float] = None) -> None:
        self.sec, self.src, self.owner = sec, src, owner
        self.path = os.path.realpath(path)
        self.now = time.time() if now is None else now

    def _rows(self) -> List[Dict[str, Any]]:
        rows, _ = parsers.parse_listing(self.src.agents_listing())
        return rows

    def owner_row(self, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return next((r for r in rows if r["bg_id"] == self.owner or r["session_id"] == self.owner
                     or (len(self.owner) >= 8 and r["session_id"].startswith(self.owner))), None)

    # -- the checks ----------------------------------------------------------
    def owner_finished(self) -> Verdict:
        try:
            row = self.owner_row(self._rows())
        except (SourceError, parsers.ParseError) as exc:
            return "not run", "the listing couldn't be read: %s" % common.safe_text(exc, 80)
        if row is None:
            return "not run", "claude agents doesn't list the owner %s" % self.owner
        scopes = ctx.load_scopes()
        board, surf = observe._board_rows(sorted({s for s in scopes.by_repo.values() if s}))
        if any(not b.get("ok") for b in surf.values()):
            return "not run", "a board couldn't be read"
        b = board.get(row["session_id"])
        if b is not None:
            if b.get("arc_status") in TERMINAL:
                return "pass", "board: ARC-STATUS %s" % b["arc_status"]
            return "fail", "board: no terminal status (%s, last %s)" % (b.get("state"), b.get("last_event"))
        if not scratch(self.path):
            return "fail", "no board row for the owner of a scope repo's worktree (a terminal status is needed)"
        if row["kind"] == "background" and row["state"] == "done":
            return "pass", "no board row (a scratch worktree); the listing shows the job done"
        return "fail", "no board row, and the listing shows %s" % (row["state"] or row["status"] or "it live")

    def no_live_session(self, exclude_owner: bool = True) -> Verdict:
        try:
            rows = self._rows()
        except (SourceError, parsers.ParseError) as exc:
            return "not run", "the listing couldn't be read: %s" % common.safe_text(exc, 80)
        owner = self.owner_row(rows)
        live = [r for r in rows if r["pid"] is not None and _inside(r["cwd"], self.path)
                and not (exclude_owner and owner is not None and r["session_id"] == owner["session_id"])]
        if live:
            return "fail", "live in the worktree: %s" % ", ".join(r["session_id"][:8] for r in live)
        return "pass", "no other live session in it"

    def pr_closed(self) -> Verdict:
        try:
            branch = _git(self.path, "symbolic-ref", "--quiet", "--short", "HEAD").strip()
        except SourceError:
            return "pass", "detached HEAD: no PR branch"
        try:
            remotes = _git(self.path, "remote").split()
            url = _git(self.path, "remote", "get-url", "origin").strip() if "origin" in remotes else ""
        except SourceError as exc:
            return "not run", "git couldn't read the remotes: %s" % common.safe_text(exc, 80)
        slug = parsers.parse_remote_slug(url) if url else None
        if not slug:
            return "pass", "no GitHub origin, so no PR"
        try:
            prs = json.loads(self.src.pr_heads(slug, branch))
        except (SourceError, ValueError) as exc:
            return "not run", "gh pr list failed: %s" % common.safe_text(exc, 80)
        open_ = [p["number"] for p in prs if p.get("state") == "OPEN"]
        if open_:
            return "fail", "PR #%d is open" % open_[0]
        return "pass", "PRs: %s" % (", ".join("#%d %s" % (p["number"], p["state"].lower()) for p in prs) or "none")

    def quiet_24h(self) -> Verdict:
        since, n, newest = self.now - QUIET_S, 0, None
        try:
            for root, dirs, files in os.walk(self.path, onerror=_raise):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in files:
                    n += 1
                    if n > MAX_FILES:
                        return "not run", "more than %d files" % MAX_FILES
                    p = os.path.join(root, f)
                    mt = os.lstat(p).st_mtime
                    if mt > since and (newest is None or mt > newest[0]):
                        newest = (mt, p)
        except OSError as exc:
            return "not run", "the worktree couldn't be walked: %s" % (exc.strerror or exc)
        if newest:
            return "fail", "%s was modified %s ago" % (os.path.relpath(newest[1], self.path),
                                                       common.age(self.now - newest[0]))
        return "pass", "%d files, none modified in 24 h" % n

    def no_holder(self) -> Verdict:
        try:
            parents = _ps()
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return "not run", "ps failed: %s" % common.safe_text(str(exc) or type(exc).__name__, 80)
        own = _own(parents)
        if not set(parents) - own:
            return "not run", "the process listing shows nothing but the janitor's own processes"
        try:
            lsof = subprocess.run(["lsof", "-w", "-n", "-F", "p", "+D", self.path], stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            return "not run", "lsof failed: %s" % common.safe_text(exc, 80)
        holders = sorted({int(x[1:]) for x in lsof.stdout.decode().split() if x[:1] == "p" and x[1:].isdigit()} - own)
        if lsof.returncode not in (0, 1) or (lsof.returncode == 1 and lsof.stderr.strip() and not holders):
            return "not run", "lsof exited %d: %s" % (lsof.returncode, common.safe_text(lsof.stderr.decode(), 80))
        if holders:
            return "fail", "held by pid(s) %s" % ", ".join(str(p) for p in holders[:5])
        return "pass", "no process holds it"

    def backup_possible(self) -> Verdict:
        try:
            secrets = secret_files(self.path)
        except SourceError as exc:
            return "not run", str(exc)
        bad = [s for s in secrets if not os.access(os.path.join(self.path, s), os.R_OK)]
        if bad:
            return "fail", "can't back up the ignored %s" % bad[0]
        return "pass", "%d ignored secret(s) to back up" % len(secrets)

    # -- the whole guard ----------------------------------------------------
    def run(self, skip: Tuple[str, ...] = ()) -> Dict[str, Any]:
        checks = []
        for name in CHECKS:
            if name in skip:
                continue
            verdict, detail = getattr(self, name)()
            checks.append({"check": name, "verdict": verdict, "detail": detail})
        fails = [c for c in checks if c["verdict"] == "fail"]
        blind = [c for c in checks if c["verdict"] == "not run"]
        return {"path": self.path, "owner": self.owner, "ok": not fails and not blind,
                "exit": 1 if fails else 2 if blind else 0, "checks": checks}


def _raise(exc: OSError) -> None:
    raise exc


# --------------------------------------------------------------------------
# Backup, expiry, and the run

def backup_dir(state_dir: Path, path: str) -> Path:
    return Path(state_dir) / "backups" / hashlib.sha256(os.path.realpath(path).encode()).hexdigest()[:16]


def backup(state_dir: Path, path: str, now: Optional[float] = None) -> Dict[str, Any]:
    """The diff, untracked files, ignored secrets and a branch for unpushed
    commits; not node_modules, target or build output (ignored, and not
    secrets). Raises SourceError or OSError: no backup, no removal."""
    now = time.time() if now is None else now
    path = os.path.realpath(path)
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now)) + ".%03dZ" % int((now % 1) * 1000)
    dest, n = backup_dir(state_dir, path) / stamp, 1
    while dest.exists():  # two backups in one millisecond: never one over another
        n += 1
        dest = backup_dir(state_dir, path) / ("%s-%d" % (stamp, n))
    dest.mkdir(parents=True, mode=0o700)
    diff = _git(path, "diff", "HEAD", "--binary")
    (dest / "diff.patch").write_text(diff, encoding="utf-8")
    untracked = [x for x in _git(path, "ls-files", "-z", "--others", "--exclude-standard").split("\0") if x]
    secrets = secret_files(path)
    for sub, rels in (("untracked", untracked), ("secrets", secrets)):
        for rel in rels:
            src = os.path.join(path, rel)
            tgt = dest / sub / rel
            tgt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.path.isdir(src):
                shutil.copytree(src, str(tgt), symlinks=True)
            else:
                shutil.copy2(src, str(tgt), follow_symlinks=False)
    unpushed = [x for x in _git(path, "rev-list", "HEAD", "--not", "--remotes").split() if x]
    ref = None
    if unpushed:
        ref = "fleet-backup/%s-%s" % (backup_dir(state_dir, path).name[:8], dest.name)
        _git(path, "branch", ref, "HEAD")
    manifest = {"path": path, "at": common.ts(now), "diff_bytes": len(diff), "untracked": untracked,
                "secrets": secrets, "unpushed": len(unpushed), "branch": ref}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return dict(manifest, dir=str(dest))


def secret_files(path: str) -> List[str]:
    """Ignored files named like secrets (.env*, *.db): backed up before any removal."""
    # --directory lists an ignored directory as one entry; each is walked for
    # secrets (data/app.db), except dependency and build output (§5.5).
    out = _git(path, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory")
    found = []
    for rel in (x for x in out.split("\0") if x):
        rel = rel.rstrip("/")
        full = os.path.join(path, rel)
        if os.path.isdir(full) and not os.path.islink(full):
            if os.path.basename(rel) in HEAVY_DIRS:
                continue
            for root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if d not in HEAVY_DIRS]
                found += [os.path.relpath(os.path.join(root, f), path) for f in files
                          if any(fnmatch.fnmatch(f, g) for g in SECRET_GLOBS)]
        elif any(fnmatch.fnmatch(os.path.basename(rel), g) for g in SECRET_GLOBS):
            found.append(rel)
    return sorted(found)


def prune(state_dir: Path, now: Optional[float] = None) -> int:
    """Delete backups older than 14 days (§5.5); returns how many."""
    now = time.time() if now is None else now
    root = Path(state_dir) / "backups"
    n = 0
    for d in sorted(root.glob("*/*")) if root.is_dir() else []:
        try:
            if d.is_dir() and now - d.stat().st_mtime > BACKUP_DAYS * 86400:
                shutil.rmtree(str(d))
                n += 1
        except OSError:
            continue
    return n


def scratch(path: str) -> bool:
    """A worktree of no scope repo: the only kind removed before the drill
    passes. Fails closed: a repo git can't read, or one listed in any scope
    (an ambiguous one included), is not scratch."""
    where = ctx.locate(path, timeout=5.0)
    if where is None:
        return not os.path.exists(os.path.join(path, ".git"))
    return where.common_dir not in ctx.load_scopes().by_repo


def run(sec: Dict[str, Any], src: Sources, path: str, owner: str, remove: bool,
        log: Callable[[str], None]) -> Dict[str, Any]:
    """Check; stop the owner; re-check; back up; re-read the listing; remove.
    Every step is logged; any failure or check that can't run aborts."""
    g = Guard(sec, src, path, owner)
    res: Dict[str, Any] = {"path": g.path, "owner": owner, "removed": False, "steps": []}

    def step(name: str, out: Any) -> None:
        res["steps"].append({"step": name, "out": out})
        log("%s: %s" % (name, json.dumps(out, default=str)[:400]))

    pruned = prune(Path(sec["state_dir"]))
    if pruned:
        step("prune", "%d backup(s) older than %d days deleted" % (pruned, BACKUP_DAYS))
    # The owner must own this worktree: stop and rm act on the owner, the
    # checks and the backup on the path, so a mismatch would remove an
    # unchecked worktree.
    try:
        row = g.owner_row(g._rows())
    except (SourceError, parsers.ParseError) as exc:
        row, why = None, "the listing couldn't be read: %s" % exc
    else:
        why = "claude agents doesn't list %s" % owner if row is None else (
            "%s's cwd (%s) is not in this worktree" % (owner, common.safe_path(row["cwd"])))
    if row is not None and _inside(row["cwd"], g.path):
        try:  # and PATH is the owner's worktree itself, not a directory above it
            top = os.path.realpath(_git(row["cwd"], "rev-parse", "--show-toplevel").strip())
        except SourceError as exc:
            top, why = None, "git couldn't read the owner's worktree: %s" % exc
        else:
            why = "PATH is not the owner's worktree (that is %s)" % common.safe_path(top)
        if top != g.path:
            row = None
    if row is None or not _inside(row["cwd"], g.path):
        step("owner", why)
        res["aborted"] = "owner"
        return res

    first = g.run(skip=("no_holder",))  # the owner's own process holds it until it is stopped
    step("check", first)
    if not first["ok"]:
        res["aborted"] = "check"
        return res
    if not remove:
        res["would"] = "stop %s, re-check, back up to %s, then claude rm %s" % (
            owner, backup_dir(Path(sec["state_dir"]), g.path), owner)
        return res
    if not scratch(g.path):
        res["aborted"] = "removal is refused for a scope repo's worktree until the janitor drill passes (§5.5)"
        return res
    try:
        row = g.owner_row(g._rows())
        if row is not None and row["pid"] is None:
            step("stop", "no process: already stopped")
        else:
            step("stop", src.run_claude(["stop", owner]).strip()[:200])
            time.sleep(1.0)
    except (SourceError, parsers.ParseError) as exc:
        step("stop", "failed: %s" % exc)
        res["aborted"] = "stop"
        return res
    again = g.run(skip=("owner_finished",))
    step("re-check", again)
    if not again["ok"]:
        res["aborted"] = "re-check"
        return res
    try:
        step("backup", backup(Path(sec["state_dir"]), g.path))
    except (SourceError, OSError) as exc:
        step("backup", "failed: %s" % exc)
        res["aborted"] = "backup"
        return res
    last = g.no_live_session(exclude_owner=False)
    step("listing at removal", {"verdict": last[0], "detail": last[1]})
    if last[0] != "pass":
        res["aborted"] = "listing at removal"
        return res
    try:
        out = src.run_claude(["rm", owner]).strip()
        step("rm", out[:400])
    except SourceError as exc:
        step("rm", "failed: %s" % exc)
        res["aborted"] = "rm"
        return res
    res["removed"] = not os.path.exists(g.path)
    if not res["removed"]:  # claude rm keeps a worktree with changes or unpushed commits
        res["aborted"] = "rm kept the worktree"
        return res
    # The driver's profile holds the fleet token; it goes with the worktree
    # (§5.3). It is keyed by the ledger's spawn of this session, not by a name
    # from the listing (a duplicate name, or one like "..", must delete nothing).
    sd = Path(sec["state_dir"])
    key = next((k for k, ids in ledger.spawned(ledger.read(sd)[0]).items()
                if row["session_id"] in ids or row["session_id"][:8] in ids), None)
    if not key or not observe.fleet_shaped(key, sec["scope"]):
        return res
    for p in (sd / "profiles" / ("%s.json" % key), sd / "ghcfg" / key):
        try:
            shutil.rmtree(str(p)) if p.is_dir() else (p.unlink() if p.exists() else None)
        except OSError as exc:
            step("profile", "not removed: %s" % exc)
    return res
