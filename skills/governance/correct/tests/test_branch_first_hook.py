#!/usr/bin/env -S python3 -I
"""test_branch_first_hook.py — the branch-first cases a registry replay cannot build (BRO-3802).

A registry row's setup is limited to `git init`, `mkdir`, `touch` and file writes, so its paths can
be judged by their text: no case can create a link or a second worktree (P20 #1299 round 12 found
that fixtures which could made that judgement unsound). The cases that need a link or a linked
worktree are built here, in a temporary directory, and run against the shipped hook; the
branch-first row names this file as its `proof_test`.

  python3 -I scripts/test_branch_first_hook.py

Each case is mutation-checked: deleting the hook's `path.resolve()` fails the symlink case, and
making `shared` never true fails both shared cases.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "scripts" / "branch-first-hook.py"  # the skill keeps code in scripts/
sys.path.append(str(HOOK.parent))  # appended: the stdlib keeps precedence under -I
from governance_paths import governance_file  # noqa: E402  the root the hook itself reads
# Nothing from the caller's git configuration reaches the fixtures or the hook.
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
ENV.pop("BSTACK_ALLOW_MAIN_EDIT", None)


def git(*args: str) -> None:
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "user.name=t", "-c", "user.email=t@invalid",
                    *args], check=True, capture_output=True, env=ENV)


def governed_on_main(path: Path) -> Path:
    git("init", "-q", "-b", "main", str(path))
    policy = governance_file(path, "policy.yaml")  # resolved as the hook resolves it
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text("")
    (path / "README.md").write_text("a\n")
    git("-C", str(path), "add", "-A")
    git("-C", str(path), "commit", "-q", "--no-verify", "-m", "init")
    return path


def hook(cwd: Path, file_path: Path) -> tuple[int, str]:
    event = {"tool_name": "Edit", "cwd": str(cwd),
             "tool_input": {"file_path": str(file_path), "old_string": "a", "new_string": "b"}}
    proc = subprocess.run(["python3", "-I", str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                          cwd=str(cwd), env=ENV, timeout=60)
    return proc.returncode, proc.stderr


FAILED = []


def expect(name: str, cond: bool, detail: object = "") -> None:
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f": {detail}"))
    if not cond:
        FAILED.append(name)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()

        # A link in a feature checkout that points into a governed checkout on main writes main's
        # file (P20 #1299 round 8); the hook judges the file the write lands in.
        main_repo = governed_on_main(root / "on-main")
        git("init", "-q", "-b", "feat/x", str(root / "mine"))
        (root / "mine" / "link.md").symlink_to(main_repo / "README.md")
        code, why = hook(root / "mine", root / "mine" / "link.md")
        expect("a symlink into a governed checkout on main is refused, with the other-checkout fix",
               code == 2 and "Branch first" in why and "Edit the copy" in why, (code, why))

        # A checkout other worktrees share is never switched, whichever session edits it (P20 #1299
        # rounds 9-11): the session's own checkout, and a session in a linked worktree.
        shared = governed_on_main(root / "shared-main")
        git("-C", str(shared), "worktree", "add", "-q", "-b", "feat/y", str(root / "shared-wt"))
        code, why = hook(shared, shared / "README.md")
        expect("the session's own shared checkout gets the worktree recipe and no switch",
               code == 2 and "do not switch it" in why and "worktree add" in why and "checkout -b" not in why,
               (code, why))
        code, why = hook(root / "shared-wt", shared / "README.md")
        expect("a linked worktree's session editing the shared checkout gets no switch either",
               code == 2 and "shared by other worktrees" in why and "checkout -b" not in why, (code, why))

        # A path no filesystem call accepts (a NUL) is malformed input: allowed quietly (P20 #1299 r17 C).
        code, why = hook(root / "mine", Path(str(main_repo / "README.md") + "\x00x"))
        expect("a path with a NUL is allowed without a traceback", code == 0 and "Traceback" not in why, (code, why))

        # Control: the linked worktree's own files are on a feature branch.
        code, why = hook(root / "shared-wt", root / "shared-wt" / "README.md")
        expect("control: an edit in the linked worktree on its feature branch is allowed", code == 0, (code, why))
    if FAILED:
        return 1
    print("all branch-first hook tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
