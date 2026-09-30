#!/usr/bin/env python3
"""``trash`` inside a case: moves paths into the case's own ``~/.Trash`` and logs it.

The real ``/usr/bin/trash`` moves into the Trash of the macOS user it runs as, which
is the operator's, whatever ``$HOME`` says. Fixture scratch directories must not end
up there, so this stub shadows it on the case PATH (and the case guard rewrites an
absolute ``/usr/bin/trash`` to it). What the agent sees is the same: the paths are
gone from where they were.

It refuses any path outside the case. The case's Trash is deleted with the case, so
trashing a real path here would destroy it for good — worse than the real binary,
which is at least recoverable. A refused path is logged and left untouched.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common  # noqa: E402

NAME = "trash"


def main(argv: list[str]) -> int:
    paths = [a for a in argv if not a.startswith("-")]
    case = os.path.realpath(_common.case_root())
    bin_dir = _common.case_root() / ".eval-home" / ".Trash"
    bin_dir.mkdir(parents=True, exist_ok=True)
    moved, missing, refused = [], [], []
    for raw in paths:
        src = Path(raw).expanduser()
        real = os.path.realpath(src.parent) if src.is_symlink() else os.path.realpath(src)
        if not (real == case or real.startswith(case + os.sep)):
            refused.append(raw)
            continue
        if not src.exists() and not src.is_symlink():
            missing.append(raw)
            continue
        dest = bin_dir / src.name
        n = 1
        while dest.exists():
            n += 1
            dest = bin_dir / f"{src.name} {n}"
        where = str(src.absolute())
        shutil.move(str(src), str(dest))
        moved.append(where)
    for raw in missing:
        sys.stderr.write(f"trash: {raw}: No such file or directory\n")
    for raw in refused:
        sys.stderr.write(f"trash: {raw}: outside this workspace, not moved\n")
    code = 1 if missing or refused or not paths else 0
    if not paths:
        sys.stderr.write("usage: trash [-v] path ...\n")
    _common.log(NAME, {"argv": list(argv), "moved": moved, "missing": missing, "refused": refused,
                       "rc": code})
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
