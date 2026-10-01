"""E1 and E3: the replay's ground truth, its masks, its hashing, where the
snapshot may live, the tune loop's rules, and (only where CTX_S1_FROZEN points
at the owner's private snapshot) its reproduction of the committed report.
The arms' separation on held-out data is pinned on the synthetic fixture
(test_s1_e1_synthetic.py)."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path

import pytest

import s1_support as S
import ctx_s1
import ctx_s1_eval as E
import ctx_s1_replay as R

REPO = Path(__file__).resolve().parents[4]
REPORTS = REPO / "scripts" / "skill_evals" / "ctx_s1_replay"
FROZEN = Path(os.environ["CTX_S1_FROZEN"]) if os.environ.get("CTX_S1_FROZEN") else None
PARAMS_DIR = Path(__file__).resolve().parents[1] / "references"
ENTITY_REL = "research/entities/pattern/gate-that-cannot-fail.md"


T = S.Transcript


@pytest.fixture
def corpus(world, tmp_path):
    S.write_corpus(world)
    t0 = time.time() - 3 * 86400
    for root, _, files in os.walk(str(world.broomva / "research")):
        for f in files:  # the corpus predates the sessions: no hit is an "edited later" one
            os.utime(os.path.join(root, f), (t0 - 86400, t0 - 86400))
    ent = str(world.broomva / ENTITY_REL)
    # A: searched, then read the entity by itself -> needed
    a = T(world, "sess-a", world.broomva, t0)
    a.prompt("why does the zebrafish gate refuse writes to ops")
    a.tool("Bash", command="rg -l zebrafish research/")
    a.tool("Read", file_path=ent)
    a.save()
    # B: an injection named the entity before the read -> masked, not needed
    b = T(world, "sess-b", world.broomva, t0 + 3600)
    b.prompt("look at the gate pattern for the zebrafish writes")
    b.injected("Related entity: %s" % ENTITY_REL)
    b.tool("Read", file_path=ent)
    b.save()
    # C: the session wrote the file, then read it -> authored, not needed
    c = T(world, "sess-c", world.broomva, t0 + 7200)
    c.prompt("draft the zebrafish gate entity")
    c.tool("Write", file_path=ent, content="x")
    c.tool("Read", file_path=ent)
    c.save()
    # D: a later session in sri -> not in the broomva snapshot at all
    d = T(world, "sess-d", world.sri, t0 + 10800)
    d.prompt("zebrafish client secret plan")
    d.tool("Read", file_path=str(world.sri / "plan.md"))
    d.save()
    # E: a later session whose search LISTED the entity before the read (an easy hit)
    e = T(world, "sess-e", world.broomva, t0 + 20000)
    e.prompt("zebrafish gate question 0")
    e.tool("Bash", _out="research/entities/pattern/gate-that-cannot-fail.md", command="rg -l zebrafish research/")
    e.tool("Read", file_path=ent)
    e.save()
    # F: a skill body (an isMeta record) named the entity before the read: masked
    f = T(world, "sess-f", world.broomva, t0 + 23600)
    f.prompt("zebrafish gate question 1")
    f.skill_body("See %s for the pattern." % ENTITY_REL)
    f.tool("Read", file_path=ent)
    f.save()
    # G: an earlier session that found it from the prompt alone (no search)
    g = T(world, "sess-g", world.broomva, t0 - 3600)
    g.prompt("the zebrafish gate question again")
    g.tool("Read", file_path=ent)
    g.save()
    salt = b"\x01" * 32
    meta = R.build_snapshot("broomva", tmp_path / "snap", days=14, network=False, salt=salt)
    snap = R.load_snapshot(tmp_path / "snap" / "snapshot.jsonl.gz")
    return world, meta, snap, tmp_path / "snap"


def test_truth_is_counterfactual_and_masked(corpus):
    world, meta, snap, _ = corpus
    starts = {s["start"]: s for s in snap["sessions"]}
    assert len(snap["sessions"]) == 6  # sri's session is not in broomva's snapshot
    by_order = sorted(snap["sessions"], key=lambda s: s["s"])
    needed = [len(s["needed"]) for s in by_order]
    # G and A needed it; B (hook pointer), C (authored) and F (a skill body named it) did not;
    # E needed it, but its search had listed it
    assert needed == [1, 1, 0, 0, 1, 0]
    assert by_order[2]["pointed"] and by_order[5]["pointed"]
    assert by_order[4]["needed"][0][2] == 1 and by_order[1]["needed"][0][2] == 0  # listed vs not
    assert [s["split"] for s in by_order] == ["train", "train", "train", "validation", "test", "test"]


def test_the_snapshot_holds_no_text(corpus):
    world, meta, snap, d = corpus
    raw = gzip.decompress((d / "snapshot.jsonl.gz").read_bytes()).decode()
    for bad in ("zebrafish", "gate", "research/entities", "sess-a", "ops", str(world.home), "scripts/gate.py",
                "refuse", "draft"):
        assert bad not in raw, bad
    assert re.search(r'"w:[0-9a-f]{12}"', raw)  # hashed keys keep only their channel
    assert meta["sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert stat.S_IMODE((d / "snapshot.jsonl.gz").stat().st_mode) == 0o600


def test_the_snapshot_is_private_by_place(corpus):
    """It is written beside the scope's cache by default, and refused anywhere
    inside a git checkout, so it cannot be committed by accident."""
    world = corpus[0]
    assert R.default_dir("broomva") == world.store("broomva") / "e1"
    with pytest.raises(ValueError, match="inside the git checkout"):
        R.build_snapshot("broomva", world.broomva / "evals" / "e1", days=14, network=False, salt=b"\x02" * 32)
    assert not (world.broomva / "evals").exists()
    assert not list(REPORTS.glob("**/snapshot.jsonl.gz"))  # and no snapshot is in this repo


def test_times_are_exact_so_a_same_day_item_is_judged_to_the_second(corpus):
    _, _, snap, _ = corpus
    assert any(e["ts"] % 86400 for s in snap["sessions"] for e in s["events"])
    # the entity's `created:` is a date: it is a candidate from 36 h past that midnight
    assert {h["c"] % 86400 for h in snap["items"] if h["t"] == "entity"} == {R.DATE_ONLY_SLACK % 86400}


def test_the_replay_decides_as_the_live_gate_does_on_a_long_prompt(world, tmp_path):
    """Hashed keys in the snapshot keep the prompt's order, so the replay cuts at
    max_terms the same words the live gate does, and decides the same."""
    import ctx_s2

    S.write_corpus(world)
    filler = " ".join("filler%02d" % i for i in range(80))
    prompt = "why does the zebrafish gate refuse writes " + filler
    scope = ctx_s2.ctx.resolve_scope(str(world.broomva))
    items, _ = ctx_s2.gather(scope, network=False)
    H = R.Hasher(b"\x03" * 32)
    keys, self_obj, _, _ = ctx_s1.extract_keys("prompt", {"prompt": prompt}, scope.where, None)
    assert len(keys["w"]) > ctx_s1.DEFAULT_MAX_TERMS
    params = dict(ctx_s1.DEFAULT_PARAMS, stages={"prompt": {"floor": 0.01}})
    live_store, snap_store = tmp_path / "live", tmp_path / "snap"
    r = ctx_s2.BM25Ranker()
    r.fit(items)
    ctx_s2.write_cache(live_store, items, r, now=0.0)
    hashed = [dict(it, keys={ch: [H.key(k) for k in ks] for ch, ks in (it.get("keys") or {}).items()})
              for it in items]
    r2 = ctx_s2.BM25Ranker()
    r2.fit(hashed)
    ctx_s2.write_cache(snap_store, hashed, r2, now=0.0)
    live = ctx_s1.decide("prompt", keys, set(), {}, ctx_s1.CacheReader(live_store), params)
    replayed = ctx_s1.decide("prompt", {ch: [H.key(k) for k in ks] for ch, ks in keys.items()}, set(), {},
                             ctx_s1.CacheReader(snap_store), params)
    assert live["injected"] and live["injected"] == replayed["injected"]
    shuffled = ctx_s1.decide("prompt", {ch: sorted(H.key(k) for k in ks) for ch, ks in keys.items()}, set(), {},
                             ctx_s1.CacheReader(snap_store), params)
    assert shuffled["top"] != live["top"]  # key order matters past max_terms: the old sorted snapshot drifted


def test_the_snapshot_keeps_each_events_key_order(corpus):
    """The live gate cuts prompt words at max_terms in the prompt's order, so the
    snapshot must keep that order, not sort the hashes."""
    import ctx_keys as K

    _, _, snap, _ = corpus
    H = R.Hasher(b"\x01" * 32)
    g = sorted(snap["sessions"], key=lambda s: s["s"])[0]
    prompt_ev = [e for e in g["events"] if e["st"] == "prompt"][0]
    want = [H.key("w:" + w) for w in K.unique(K.terms("the zebrafish gate question again"))]
    assert prompt_ev["k"]["w"] == want and want != sorted(want)


def test_a_changed_snapshot_is_refused(corpus):
    _, _, _, d = corpus
    data = gzip.decompress((d / "snapshot.jsonl.gz").read_bytes()).replace(b'"len":', b'"len": ')
    (d / "snapshot.jsonl.gz").write_bytes(gzip.compress(data))
    with pytest.raises(ValueError, match="does not match"):
        R.load_snapshot(d / "snapshot.jsonl.gz")


def test_the_salt_is_private_and_stable(world):
    s1 = R.load_salt()
    assert R.load_salt() == s1
    assert stat.S_IMODE(R.salt_path().stat().st_mode) == 0o600


def test_e1_scores_the_gate_and_separates_always_from_never(corpus):
    _, _, snap, _ = corpus
    rep = E.evaluate(snap, dict(ctx_s1.DEFAULT_PARAMS, **S.LOW_FLOORS), timing=False)
    arms = rep["arms"]
    tr = lambda arm, st="all": arms[arm]["train"][st]
    assert tr("gate")["hits"] >= 1 and tr("gate")["precision"] > 0  # A's search pre-empted its read
    assert arms["stage:prompt"]["train"]["prompt"]["hits"] >= 1  # G's prompt alone did too
    te = arms["stage:post-bash"]["test"]["post-bash"]
    # E's hit came after its search listed the file: an easy hit, so not a strict one
    assert te["hits"] >= 1 and te["listed_hits"] == te["easy_hits"] == te["hits"]
    assert te["strict_precision"] == 0.0 and te["strict_recall"] == 0.0
    assert tr("never")["injections"] == 0 and tr("never")["recall"] == 0
    assert tr("always")["injections"] >= tr("gate")["injections"]
    sep = rep["separation"]
    assert sep["split"] == "test" and sep["checks"]["never_injects_nothing"] and sep["checks"]["gate_injects"]
    assert not sep["checks"]["gate_hits_strictly"] and not sep["ok"]  # test holds only E's listed hit


def test_e1_is_deterministic(corpus):
    _, _, snap, _ = corpus
    p = dict(ctx_s1.DEFAULT_PARAMS, **S.LOW_FLOORS)
    strip = lambda r: json.dumps({k: v for k, v in r.items() if k != "arms"}, sort_keys=True) + json.dumps(
        {a: {sp: {st: {k: v for k, v in b.items() if not k.endswith("_ms")} for st, b in x.items()}
             for sp, x in res.items()} for a, res in r["arms"].items()}, sort_keys=True)
    assert strip(E.evaluate(snap, p, timing=False)) == strip(E.evaluate(snap, p, timing=False))


# --------------------------------------------------------------------------
# E3

def test_tune_is_bounded_deterministic_and_ledgered(corpus, tmp_path):
    _, _, snap, d = corpus
    before = (d / "snapshot.jsonl.gz").read_bytes()
    runs = []
    for i in range(2):
        ledger = tmp_path / ("ledger-%d.jsonl" % i)
        res = E.tune(snap, dict(ctx_s1.DEFAULT_PARAMS), trials=14, seed=7, ledger=ledger, log=lambda *_: None)
        lines = [json.loads(l) for l in ledger.read_text().splitlines()]
        assert len(res["history"]) <= 14 and len(lines) == len(res["history"]) + 1
        assert "summary" in lines[-1]
        runs.append([(h["change"], h["accepted"]) for h in res["history"]])
    assert runs[0] == runs[1]
    assert (d / "snapshot.jsonl.gz").read_bytes() == before  # tune never writes the frozen snapshot


def test_tune_accepts_only_what_holds_out():
    cur = {"strict_f05": 0.10, "strict_recall": 0.2, "f05": 0.1, "bytes": 100.0, "strict_hits": 3}
    better = {"strict_f05": 0.20, "strict_recall": 0.2, "f05": 0.1, "bytes": 100.0, "strict_hits": 4}
    assert E.accept(cur, cur, better, better)[0]
    assert not E.accept(cur, cur, better, dict(better, strict_f05=0.05))[0]            # held-out regressed
    assert not E.accept(cur, cur, better, dict(better, bytes=500.0))[0]                # bytes grew, recall did not
    assert E.accept(cur, cur, better, dict(better, bytes=500.0, strict_recall=0.3))[0]  # bytes grew with recall
    assert not E.accept(cur, cur, cur, cur)[0]                                          # no train gain, no change
    # an easy-hit gain is no gain: the objective is the bar's metric
    assert not E.accept(cur, cur, dict(cur, f05=0.9), dict(cur, f05=0.9))[0]
    # nor is a gain that rests on one strict hit
    assert not E.accept(cur, cur, dict(better, strict_hits=1), better)[0]


def test_tune_scores_strict_f05_and_skips_stages_that_only_reoffer(corpus):
    _, _, snap, _ = corpus
    res = E.tune(snap, dict(ctx_s1.DEFAULT_PARAMS), trials=60, seed=3, log=lambda *_: None)
    assert {h["phase"] for h in res["history"]} <= set(E.TUNED_STAGES) | {"weights"}
    sigs = [json.dumps(E._canon(h["params"]), sort_keys=True) for h in res["history"]]
    assert len(sigs) == len(set(sigs))  # no proposal scored twice
    # a setting equal to the stage table's default is no change at all
    assert E._canon({"stages": {"prompt": {"max": ctx_s1.STAGES["prompt"]["max"], "floor": 1}}}) == \
        E._canon({"stages": {"prompt": {"floor": 1}}})
    assert "subagent" not in E.TUNED_STAGES and "compact" not in E.TUNED_STAGES
    assert all("strict_f05" in h["train"] for h in res["history"])


def test_the_spec_bar_removes_a_floor_that_did_not_earn_it():
    p = {"stages": {"prompt": {"floor": 5}, "pre-edit": {"floor": 3}, "post-bash": {"floor": 9}}}
    per = {"prompt": {"strict_precision": 0.9, "injections": 10},        # too few injections
           "pre-edit": {"strict_precision": 0.1, "injections": 500},     # too imprecise
           "post-bash": {"strict_precision": 0.4, "injections": 60}}     # clears it
    out, dropped = E.enforce_bar(p, per)
    assert out["stages"]["prompt"]["floor"] is None and out["stages"]["pre-edit"]["floor"] is None
    assert out["stages"]["post-bash"]["floor"] == 9 and len(dropped) == 2


# --------------------------------------------------------------------------
# The owner's private snapshot: only where CTX_S1_FROZEN points at it

frozen = pytest.mark.skipif(FROZEN is None or not (FROZEN / "snapshot.jsonl.gz").exists(),
                            reason="the real snapshot is private: set CTX_S1_FROZEN to its dir")


def _frozen_params(name: str):
    return json.loads((PARAMS_DIR / name).read_text())


@frozen
@pytest.mark.parametrize("name", ["e1-report.json", "e1-report-ppr.json"])
def test_the_frozen_snapshot_reproduces_its_committed_report(name):
    """Each committed report, re-derived from the private snapshot with the
    parameters and ranker it names."""
    snap = R.load_snapshot(FROZEN / "snapshot.jsonl.gz")
    committed = json.loads((REPORTS / name).read_text())
    assert committed["snapshot"]["sha256"] == snap["meta"]["sha256"], "the report is from another snapshot"
    rep = E.evaluate(snap, committed["params_body"], ranker=committed["ranker"], timing=False)
    for arm, res in committed["arms"].items():
        for sp, rows in res.items():
            for st, b in rows.items():
                got = rep["arms"][arm][sp][st]
                for k, v in b.items():
                    if k.endswith("_ms") or k == "decisions_timed":
                        continue
                    if isinstance(v, float):  # libm may differ in the last place across platforms
                        assert abs(got[k] - v) <= 1e-9 * max(1.0, abs(v)), (arm, sp, st, k)
                    else:
                        assert got[k] == v, (arm, sp, st, k)
    assert rep["separation"] == committed["separation"]


@frozen
def test_the_shipped_parameters_pass_the_spec_bar_on_the_frozen_snapshot():
    """No stage ships with a floor unless E1 shows it clears strict precision
    >= 0.30 over >= 50 injections on the test split, with that stage alone."""
    snap = R.load_snapshot(FROZEN / "snapshot.jsonl.gz")
    shipped = dict(ctx_s1.DEFAULT_PARAMS, **_frozen_params("s1-params.json"))
    for st, cfg in (shipped.get("stages") or {}).items():
        if cfg.get("floor") is None:
            continue
        rep = E.evaluate(snap, shipped, arms=["stage:" + st], timing=False)
        b = rep["arms"]["stage:" + st]["test"][st]
        assert b["injections"] >= E.MIN_INJECTIONS and b["strict_precision"] >= E.MIN_PRECISION, st


# --------------------------------------------------------------------------
# The replay sees what the live gate sees (round-2 findings)

def _snap(world, tmp_path, name="s"):
    R.build_snapshot("broomva", tmp_path / name, days=14, network=False, salt=b"\x07" * 32)
    return R.load_snapshot(tmp_path / name / "snapshot.jsonl.gz")


def test_calls_issued_together_anchor_after_their_message(world, tmp_path):
    """Reads issued in one assistant message were all written before any hook
    output: the first one's claim cannot be a hit on the second."""
    S.write_corpus(world)
    t = T(world, "par", world.broomva, time.time() - 86400)
    t.prompt("look at the gate")
    t.tools([("Read", {"file_path": str(world.broomva / "scripts" / "gate.py")}),
             ("Read", {"file_path": str(world.broomva / ENTITY_REL)})])
    t.tool("Bash", command="ls")
    t.save()
    reads = [e for e in _snap(world, tmp_path)["sessions"][0]["events"] if e["st"] == "post-read"]
    assert [e["a"] for e in reads] == [2, 2]  # both after the batch (ordinals 0 and 1)


def test_a_relative_shell_read_keys_as_it_does_live(world, tmp_path):
    S.write_corpus(world)
    t = T(world, "rel", world.broomva, time.time() - 86400)
    t.prompt("check it")
    t.tool("Bash", command="sed -n 1,5p scripts/gate.py")
    t.save()
    ev = [e for e in _snap(world, tmp_path)["sessions"][0]["events"] if e["st"] == "post-bash"][0]
    H = R.Hasher(b"\x07" * 32)
    assert ev["pk"] == H.key("p:scripts/gate.py") and ev["self"] == [H.key("o:scripts/gate.py")]
    assert ev["ll"] == len("scripts/gate.py")


def test_truth_and_the_gate_resolve_a_path_the_same_way(world):
    """A fetch is the object the gate would call the event's own file: a nested
    repo in the scope is that repo's; another scope's or an unscoped repo's is
    nothing."""
    import subprocess

    lib = world.broomva / "vendor" / "lib"
    lib.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(lib), check=True)
    cfg = world.home / ".config" / "ctx" / "scopes.yaml"
    cfg.write_text(cfg.read_text().replace("    - ~/broomva        #", "    - ~/broomva/vendor/lib\n    - ~/broomva        #"))
    where = ctx_s1.ctx.resolve_scope(str(world.broomva)).where
    for f in (world.broomva / "scripts" / "gate.py", lib / "notes.md", world.sri / "plan.md", world.other / "x.md"):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
        truth = R.fetch_objs("Read", {"file_path": str(f)}, where, "broomva", "broomva")
        _, gate_self, _, _ = ctx_s1.extract_keys("post-read", {"tool_input": {"file_path": str(f)}}, where,
                                                 "broomva", "broomva")
        assert truth == gate_self, f
    assert R.fetch_objs("Read", {"file_path": str(lib / "notes.md")}, where, "broomva", "broomva") == {"o:notes.md"}
    # and the echo check names it the same way, through the scope's roots
    assert "o:docs/notes.md" in R.echo_objs("see %s" % (lib / "docs" / "notes.md"), where, {},
                                            roots=[(str(lib), "")])


def test_a_bare_pr_number_the_gate_keys_on_is_an_echo(world):
    S.write_corpus(world)
    where = ctx_s1.ctx.resolve_scope(str(world.broomva)).where
    for text in ("review PR #253 please", "gh pr comment 253 --body done", "gh pr view 253 -R o/skills"):
        assert "o:pr:skills#253" in R.echo_objs(text, where, {}, repo="skills"), text
    assert not any(o.startswith("o:pr:") for o in R.echo_objs("gh pr checks --watch --interval 10", where, {},
                                                                repo="skills"))


def test_a_wikilink_in_injected_text_masks_the_item(world, tmp_path):
    S.write_corpus(world)
    t = T(world, "wiki", world.broomva, time.time() - 86400)
    t.prompt("zebrafish gate")
    t.injected("See [[gate-that-cannot-fail]] for the pattern.")
    t.tool("Read", file_path=str(world.broomva / ENTITY_REL))
    t.save()
    s = _snap(world, tmp_path)["sessions"][0]
    assert s["needed"] == [] and s["pointed"]


def test_a_subagent_is_masked_and_listed_like_its_parent(world, tmp_path):
    S.write_corpus(world)
    t0 = time.time() - 86400
    parent = T(world, "subpar", world.broomva, t0)
    parent.prompt("ask a helper about the gate")
    parent.tool("Agent", _out="done. agentId: abcdef1234567890", prompt="find the gate facts",
                subagent_type="general-purpose")
    parent.save()
    sub = T(world, "subpar", world.broomva, t0 + 10,
            path=parent.path.parent / "subpar" / "subagents" / "agent-abcdef1234567890.jsonl")
    spec = world.broomva / "docs" / "specs" / "2026-09-01-gate-design.html"
    sub.injected("Instructions: read docs/specs/2026-09-01-gate-design.html first.")
    sub.tool("Read", file_path=str(spec))                                    # pointed: masked
    sub.tool("Bash", _out="research/entities/pattern/gate-that-cannot-fail.md", command="rg -l gate research")
    sub.tool("Read", file_path=str(world.broomva / ENTITY_REL))              # a search listed it
    mem = S.memory_dir(world.home, world.broomva) / "gate-rule.md"
    sub.tool("Read", file_path=str(mem))                                     # found by itself
    sub.save()
    snap = _snap(world, tmp_path)
    ev = [e for e in snap["sessions"][0]["events"] if e["st"] == "subagent"][0]
    kinds = {snap["items"][i]["t"]: listed for i, _, listed in ev["sub"]}
    assert kinds == {"entity": 1, "memory": 0}  # the spec was pointed at first


def test_an_item_edited_after_the_event_is_an_easy_hit(corpus, world, tmp_path):
    os.utime(str(world.broomva / ENTITY_REL), None)  # edited now, after every session
    rep = E.evaluate(_snap(world, tmp_path, "edited"), dict(ctx_s1.DEFAULT_PARAMS, **S.LOW_FLOORS),
                     arms=["stage:prompt"], timing=False)
    b = rep["arms"]["stage:prompt"]["train"]["prompt"]
    assert b["hits"] >= 1 and b["edited_hits"] == b["hits"] == b["easy_hits"] and b["strict_precision"] == 0.0


def test_a_date_only_creation_counts_from_late_that_day():
    day = 1_790_035_200  # a UTC midnight
    assert R._eligible_from({"created": day, "mtime": day + 3600}) == day + 3600  # the file existed by then
    assert R._eligible_from({"created": day, "mtime": day + 9 * 86400}) == day + R.DATE_ONLY_SLACK
    assert R._eligible_from({"created": day + 77, "mtime": day + 9 * 86400}) == day + 77  # a real time


def test_a_fetch_before_a_later_pointer_is_still_a_hit(world, tmp_path):
    """Pointed at after the agent had already fetched it: the fetch was the
    agent's own, so the claim's hit stands. Pointed at inside the window with
    no fetch before it: unjudgeable, not a miss."""
    S.write_corpus(world)
    t0 = time.time() - 86400
    a = T(world, "fetch-first", world.broomva, t0)
    a.prompt("why does the zebrafish gate refuse writes")
    a.tool("Read", file_path=str(world.broomva / ENTITY_REL))
    a.injected("Related entity: %s" % ENTITY_REL)
    a.tool("Bash", command="ls")
    a.save()
    b = T(world, "point-first", world.broomva, t0 + 600)
    b.prompt("why does the zebrafish gate refuse writes again")
    b.tool("Bash", command="ls")
    b.injected("Related entity: %s" % ENTITY_REL)
    b.tool("Bash", command="ls")
    b.save()
    snap = _snap(world, tmp_path, "ptr")
    for s in snap["sessions"]:
        s["split"] = "train"
    rep = E.evaluate(snap, dict(ctx_s1.DEFAULT_PARAMS, **S.LOW_FLOORS), arms=["stage:prompt"], timing=False)
    b = rep["arms"]["stage:prompt"]["train"]["prompt"]
    assert b["hits"] == 1 and b["unjudgeable"] >= 1


def test_a_numberless_gh_pr_view_keys_the_pr_its_output_names(world, tmp_path):
    S.write_corpus(world)
    t = T(world, "ghview", world.broomva, time.time() - 86400)
    t.prompt("what is open")
    t.tool("Bash", _out="title: x\nurl: https://github.com/o/broomva/pull/12\n", command="gh pr view")
    t.save()
    ev = [e for e in _snap(world, tmp_path, "gh")["sessions"][0]["events"] if e["st"] == "post-bash"][0]
    assert ev["k"].get("pr") == [R.Hasher(b"\x07" * 32).key("pr:broomva#12")]


def test_after_a_cd_the_event_is_the_new_repos(world, tmp_path):
    """The hook resolves the repo from the cwd it is handed; after `cd` into a
    nested repo of the scope, a PR number is that repo's."""
    import subprocess

    S.write_corpus(world)
    lib = world.broomva / "vendor" / "lib"
    lib.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(lib), check=True)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:o/libby.git"], cwd=str(lib), check=True)
    cfg = world.home / ".config" / "ctx" / "scopes.yaml"
    cfg.write_text(cfg.read_text().replace("    - ~/broomva        #", "    - ~/broomva/vendor/lib\n    - ~/broomva        #"))
    t = T(world, "cdlib", world.broomva, time.time() - 86400)
    t.prompt("check the lib pr")
    t.cwd = str(lib)
    t.tool("Bash", command="gh pr view 12")
    t.save()
    ev = [e for e in _snap(world, tmp_path, "cd")["sessions"][0]["events"] if e["st"] == "post-bash"][0]
    assert ev["k"].get("pr") == [R.Hasher(b"\x07" * 32).key("pr:libby#12")]


def test_the_committed_reports_name_the_committed_proposal():
    """The reports were run with the proposal file as committed (the PPR one
    with the same parameters, so the ranker is the only difference)."""
    cand = json.loads((PARAMS_DIR / "s1-params.candidate.json").read_text())
    for name in ("e1-report.json", "e1-report-ppr.json"):
        rep = json.loads((REPORTS / name).read_text())
        assert rep["params"] == cand["version"] and rep["params_body"]["stages"] == cand["stages"], name
        assert rep["snapshot"]["sha256"] == cand["snapshot"], name
