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
