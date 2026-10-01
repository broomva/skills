#!/usr/bin/env python3
"""Compose ``a2-opus.json``, the one task file spec A2's opus run calibrates and runs
(BRO-2674 pre-flip step 3). Each task is copied unchanged from its source file; a test
fails if a copy drifts.

    python3 scripts/skill_evals/ctx_ablation/tasks/compose_a2.py

Chosen before any opus trial: one held-out task per routed entry that has one (p9 twice,
with and without push wording), and the P14, P11 and P3 regression tasks. Not run: heal
and checkit (not routed after the v2 gate); P18 docs, janitor and autonomous (routed, no
held-out task); the harm task (no line fires on its prompt in any arm, so it measures
nothing here; the worktree task carries the deletion check on opus).
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = {
    "reflex-heldout.json": ["heldout-p9-watch-pushed-pr", "heldout-p9-change-work", "heldout-branch-first-on-main",
                            "heldout-merge-it-please", "heldout-trash-run-dirs", "heldout-paseo-status",
                            "heldout-worktree-removal-guard"],
    "a2-regression.json": ["reg-p14-depchain", "reg-p11-empirical", "reg-p3-ticket"],
}
NOTES = ("Spec A2's opus set (BRO-2674 pre-flip step 3), composed by compose_a2.py: every task copied unchanged "
         "from reflex-heldout.json or a2-regression.json. See compose_a2.py for what is in and out, and why.")


def compose() -> dict:
    tasks = []
    for name, ids in SOURCES.items():
        by_id = {t["id"]: t for t in json.loads((HERE / name).read_text(encoding="utf-8"))["tasks"]}
        tasks += [by_id[i] for i in ids]
    return {"version": 1, "notes": NOTES, "tasks": tasks}


if __name__ == "__main__":
    (HERE / "a2-opus.json").write_text(json.dumps(compose(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote a2-opus.json")
