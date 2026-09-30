#!/usr/bin/env python3
"""``p9`` inside a case: accepts a watch, reports it armed, and logs the call.

The real p9 arms a background watcher and notifies when CI settles. In a headless
trial there is nothing to wait for, so the stub answers the way p9 does when it
succeeds and records the argv; a task grades whether the agent reached for p9 at all
rather than sleeping on CI.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common  # noqa: E402

NAME = "p9"


def main(argv: list[str]) -> int:
    sub = argv[0] if argv else ""
    target = next((a for a in argv[1:] if not a.startswith("-")), "")
    if sub == "watch" and target:
        print(f"p9: watcher armed for {target} (background); the result is delivered when CI settles")
        code = 0
    elif sub in ("status", "list", "ls"):
        print("p9: no watchers pending")
        code = 0
    elif sub == "heal" and target:
        # A task can script the classifier's verdict (stubs.p9.heal); the real one
        # classifies the failed check's log against a regex rubric.
        print(_common.config(NAME).get("heal") or f"p9 heal {target}: no classified failure")
        code = 0
    elif sub in ("--help", "-h", "help", ""):
        print("usage: p9 watch <pr|run> [--background] | p9 status")
        code = 0
    else:
        print(f"p9: {sub} ok")
        code = 0
    _common.log(NAME, {"argv": list(argv), "rc": code})
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
