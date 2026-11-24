#!/usr/bin/env -S python3 -I
"""branch-first-hook.py — no edits on main in a governed checkout (BRO-3802).

Owner rule (MEMORY.md "Before any work"): after `git checkout main`, creating a
branch is the first action, and work committed on main is recovered by branching
from it and then `git branch -f main origin/main`. This PreToolUse hook on Write, Edit, MultiEdit
and NotebookEdit refuses an edit to any file git does not ignore (tracked or new) when the file's
repository is governed (it has a governance policy.yaml) and its checkout is on main or master.
A file edited or committed through Bash is not caught here: telling that from shell text took a
parser that blocked legitimate commits and missed others (P20 #1299 rounds 1-2), so both are known
misses in the rules registry, rules.yaml (BRO-3865), for a git-level hook that sees every commit.

Allowed: files outside any repository, ignored files (scratch, caches),
repositories without a governance policy.yaml, detached HEAD, and any branch other
than main or master. BSTACK_ALLOW_MAIN_EDIT=<reason> in the hook's environment (set before the
session starts; an `export` in Bash does not reach hooks) allows the edit and names the reason
on stderr, for the rare session that must write on main.

Exit 2 blocks (Claude Code feeds stderr to the agent); exit 0 allows. Fails open
on unreadable input, since a crash here must not stop unrelated work.
"""
from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
from pathlib import Path

# Appended, not prepended: the layout resolver lives beside this file and scripts/
# must not shadow the stdlib under -I (scripts/governance_paths.py, BRO-3200).
sys.path.append(str(Path(__file__).resolve().parent))
from governance_paths import governance_file  # noqa: E402

PROTECTED = {"main", "master"}


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    # Every variable that moves git's repository discovery, as the Linear gate drops them (P20 #1299 r15 A).
    env = {k: v for k, v in os.environ.items() if k not in (
        "GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM")}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env, timeout=10)


@functools.lru_cache(maxsize=None)  # many hunk paths in one directory cost one lookup (P20 #1299 r17 C)
def governed_on_main(start: Path) -> tuple[Path, str] | None:
    top = git(start, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return None
    repo = Path(top.stdout.strip())
    if not governance_file(repo, "policy.yaml").exists():
        return None
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch.returncode != 0 or branch.stdout.strip() not in PROTECTED:
        return None
    return repo, branch.stdout.strip()


def refuse(repo: Path, branch: str, what: str, session_top: Path | None = None) -> int:
    reason = os.environ.get("BSTACK_ALLOW_MAIN_EDIT")
    if reason:
        print(f"branch-first: {what} on {branch} allowed by BSTACK_ALLOW_MAIN_EDIT ({reason})", file=sys.stderr)
        return 0
    # A checkout other worktrees share is never switched: that moves the scripts every session's hooks
    # run from and leaves concurrent sessions on someone else's branch (P20 #1299 rounds 9-10).
    shared = git(repo, "worktree", "list", "--porcelain").stdout.count("\nworktree ") > 0
    own_tree = (f"git -C {repo} worktree add .claude/worktrees/<name> -b <type>/<ticket>-<slug> "
                f"(e.g. feat/bro-1234-short-name), then edit under that path")
    if session_top is not None and session_top.resolve() != repo.resolve():
        # The file lives in another checkout (often the shared primary one on main) (P20 #1299 round 5).
        print(
            f"Branch first: {repo} is on {branch} and is not this session's checkout ({session_top}). "
            f"Edit the copy of this file in your own checkout instead; "
            + (f"{repo} is shared by other worktrees, so do not switch it; if the work belongs there, "
               f"give it its own worktree: {own_tree}." if shared else
               f"if {repo} is yours, branch it first: git -C {repo} checkout -b <type>/<ticket>-<slug>."),
            file=sys.stderr,
        )
        return 2
    if shared:
        print(
            f"Branch first: {repo} is on {branch} and other worktrees share it, so do not switch it. "
            f"Give the work its own worktree before the first {what}: {own_tree}. "
            f"Commits that already landed on {branch} locally come with it.",
            file=sys.stderr,
        )
        return 2
    print(
        f"Branch first: {repo} is on {branch}. Create a branch before the first {what}: "
        f"git -C {repo} checkout -b <type>/<ticket>-<slug> (e.g. feat/bro-1234-short-name). "
        f"If commits already landed on main locally, carry them onto the branch and reset main: "
        f"git -C {repo} checkout -b <new-branch> && git -C {repo} branch -f main origin/main.",
        file=sys.stderr,
    )
    return 2


def nearest_dir(path: Path) -> Path | None:
    for candidate in [path, *path.parents]:
        if candidate.is_dir():
            return candidate
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(event, dict) or not isinstance(event.get("tool_input") or {}, dict):
        return 0
    tool_input = event.get("tool_input") or {}
    cwd = Path(str(event.get("cwd") or os.getcwd()))
    # Every path the call names, in either key style (the write-safety gate reads filePath too) and in
    # each hunk of a MultiEdit (P20 #1299 round 16, stratum A).
    keys = ("file_path", "filePath", "notebook_path", "notebookPath")
    hunks = tool_input.get("edits") if isinstance(tool_input.get("edits"), list) else []
    raws = [obj.get(k) for obj in [tool_input, *[h for h in hunks if isinstance(h, dict)]] for k in keys]
    raws = list(dict.fromkeys(r for r in raws if r and isinstance(r, str)))
    top = git(cwd, "rev-parse", "--show-toplevel") if raws and cwd.is_dir() else None
    # No repository at the session's cwd: the file's checkout is not known to be the session's, so
    # it is treated as another checkout (P20 #1299 round 7: a plain or missing cwd got the
    # "branch this checkout" advice for a checkout that was not its own).
    session_top = Path(top.stdout.strip()) if top is not None and top.returncode == 0 else Path(str(cwd))
    for raw in raws:
        path = Path(raw)
        if not path.is_absolute():
            path = cwd / path
        # Judge the file a write lands in: a symlink in a feature worktree that points into the main
        # checkout writes main's file (P20 #1299 round 8). A path no filesystem call accepts (a NUL)
        # names no file the edit could write: skip it quietly, as malformed input is (r17 C).
        try:
            path = path.resolve()
        except (OSError, ValueError):
            continue
        start = nearest_dir(path.parent)
        hit = governed_on_main(start) if start else None
        if hit is None:
            continue
        if git(hit[0], "check-ignore", "-q", str(path)).returncode == 0:
            continue
        return refuse(hit[0], hit[1], "edit", session_top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
