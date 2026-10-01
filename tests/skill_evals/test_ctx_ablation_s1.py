"""ctx_ablation's System 1 arms: which one-stage arms exist, what a trial's
summary counts, and that arms without the gate report no System 1 section."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals.ctx_ablation import arms as A  # noqa: E402
from skill_evals.ctx_ablation import run as R  # noqa: E402


def test_one_stage_arms_only_where_the_proposal_gates_alone():
    import ctx_s1

    floored = A._floored(A.S1_PARAMS)
    assert set(A.S1_ALONE) == {st for st in A.S1_ALL if st in ctx_s1.ALONE_STAGES and st in floored}
    assert "s1-subagent" not in A.ARM_REGISTRY and "s1-compact" not in A.ARM_REGISTRY
    assert all(("s1-" + st) in A.ARM_REGISTRY for st in A.S1_ALONE)


def test_the_summary_leaves_subagent_claims_out_and_counts_session_start_once(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    rows = [
        {"stage": "prompt", "mode": "inject", "outcome": "inject", "injected": ["spec:a"], "bytes": 100,
         "prompt_id": "p1"},
        {"stage": "session-start", "mode": "inject", "outcome": "inject", "injected": ["spec:b"], "bytes": 50},
        {"stage": "subagent", "mode": "inject", "outcome": "inject", "injected": ["spec:c"], "bytes": 70,
         "agent_id": "a1"},
        {"stage": "post-bash", "mode": "shadow", "outcome": "inject", "injected": ["spec:d"], "bytes": 40},
    ]
    (store / "s1-decisions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    case = SimpleNamespace(layout=SimpleNamespace(ctx_store=store, workspace=tmp_path))
    t = SimpleNamespace(tool_uses=lambda: [])
    out = R.s1_summary(case, t)
    assert out["injected_ids"] == ["spec:a", "spec:b"]          # the subagent's went to the subagent
    assert out["bytes"] == 220                                  # shadow decisions never reach the model
    assert out["bytes_not_in_session_start"] == 170             # session-start is in the SessionStart chars
    assert out["by_stage"]["subagent"]["claims"] == 1


def test_a_call_that_did_not_run_is_no_follow_through(tmp_path):
    from skill_evals.ctx_ablation import s1_follow

    f = tmp_path / "docs" / "specs" / "a.html"
    read = SimpleNamespace(name="Read", input={"file_path": str(f)})
    objs = {"spec:a": ["o:docs/specs/a.html"]}
    assert s1_follow.followed([("spec:a", 0)], objs, [read], tmp_path, ran=[True]) == 1
    assert s1_follow.followed([("spec:a", 0)], objs, [read], tmp_path, ran=[False]) == 0


def test_mid_turn_bytes_weigh_tasks_as_the_turn_one_delta_does():
    from skill_evals.ctx_ablation import metrics as M

    def row(arm, task, trial, ctx, mid=None):
        r = {"arm": arm, "task": task, "trial": trial, "outcome": M.PASS, "context_tokens": ctx}
        if mid is not None:
            r["s1"] = {"mid_turn_bytes": mid, "by_stage": {}, "claims": 0, "followed": 0}
        return r

    rows = [row("bare", "a", 1, 1000), row("bare", "b", 1, 1000),
            row("s1", "a", 1, 1000, mid=1000),                                    # one trial of task a
            row("s1", "b", 1, 1000, mid=0), row("s1", "b", 2, 1000, mid=0), row("s1", "b", 3, 1000, mid=0)]
    s1 = {r.arm: r for r in M.aggregate(rows, ["bare", "s1"])}["s1"]
    assert s1.injected_tokens == 125.0  # (1000 + 0) / 2 tasks / 4, not 1000 / 4 trials / 4
