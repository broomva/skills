"""E1 in CI: the whole harness (extraction, masks, hashing, the replay cache,
every arm, the separation check on the test split) on a synthetic world where
a working gate exists (s1_synthetic). The real snapshot stays on the
owner's machine, so this is what CI can check: that the harness tells a
working gate from always-inject, wrong-key and never, on held-out sessions and
strict hits. Set CTX_S1_E1_SUMMARY to a file to append the report there (the
CI job points it at $GITHUB_STEP_SUMMARY)."""
from __future__ import annotations

import os
import time

import pytest

import s1_synthetic as SYN
import ctx_s1
import ctx_s1_eval as E
import ctx_s1_replay as R


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    # module-scoped: build the world once (the `world` fixture is per test)
    from conftest import make_world

    root = tmp_path_factory.mktemp("syn")
    with pytest.MonkeyPatch.context() as mp:
        world = make_world(root, mp)
        now = time.time()
        SYN.write_world(world, now)
        meta = R.build_snapshot("broomva", root / "snap", days=30, network=False, now=now, salt=b"\x05" * 32)
        snap = R.load_snapshot(root / "snap" / "snapshot.jsonl.gz")
        rep = E.evaluate(snap, dict(ctx_s1.DEFAULT_PARAMS, **SYN.PARAMS), timing=False)
        yield meta, snap, rep


def test_the_synthetic_world_has_the_shape_it_promises(synthetic):
    meta, snap, _ = synthetic
    assert meta["sessions"] == SYN.N_SESSIONS and meta["splits"] == {"train": 24, "validation": 8, "test": 8}
    assert all(len(s["needed"]) == 2 for s in snap["sessions"])  # each session's two reads


def test_e1_separates_the_arms_on_the_test_split(synthetic):
    _, _, rep = synthetic
    sep = rep["separation"]
    if os.environ.get("CTX_S1_E1_SUMMARY"):
        with open(os.environ["CTX_S1_E1_SUMMARY"], "a") as fh:
            fh.write("## E1 on the synthetic fixture\n\n" + E.render_md(rep, "test") + "\n")
    assert sep["split"] == "test" and sep["ok"], sep["checks"]
    gate = rep["arms"]["gate"]["test"]["all"]
    # one claim per prompt that names a topic, one strict hit a session: the
    # other read lands past the window
    assert (gate["claims"], gate["hits"], gate["easy_hits"]) == (16, 8, 0)
    assert gate["strict_precision"] == 0.5 and gate["strict_recall"] == 0.5


def test_the_mutant_arms_score_below_the_gate(synthetic):
    _, _, rep = synthetic
    arms = sep_arms = rep["separation"]["arms"]
    assert sep_arms["always"]["strict_precision"] < arms["gate"]["strict_precision"]
    assert sep_arms["wrong-key"]["hits"] == 0 and sep_arms["never"]["injections"] == 0
    assert sep_arms["always"]["bytes"] > arms["gate"]["bytes"]


def test_stages_that_only_reoffer_have_no_one_stage_arm(synthetic):
    _, _, rep = synthetic
    assert "stage:subagent" not in rep["arms"] and "stage:compact" not in rep["arms"]
    assert "stage:prompt" in rep["arms"]
