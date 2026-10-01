"""E1 (offline replay) and E3 (the tune loop) for the ctx System 1 gate.

    ctx-s1 eval  [--snapshot DIR] [--params FILE] [--out DIR] [--window 10] [--ranker bm25]
    ctx-s1 tune  [--snapshot DIR] [--params FILE] [--trials 40] [--seed 1] [--ledger FILE] [--write FILE]

--snapshot defaults to the scope's private snapshot (ctx_s1_replay.default_dir).
    ctx-s1 follow [--days 7]           follow-through of live injections (decisions log x transcripts)

E1 replays the private snapshot (ctx_s1_replay) through the real decision
function (ctx_s1.decide) over a real on-disk cache written by the real System 2
writer (ctx_s2.write_cache) from the snapshot's items, one fresh cache reader
per event, as the hook does. No model call, deterministic, CI-able.

Per stage and per split (train / validation / test, 60/20/20 by session start
time: tune fits on train, accepts on validation, and the spec's bar and the
separation check are read on test, which no trial reads):
    events, injection rate, abstain rate and why, injected claims, hits,
    precision, strict precision (easy hits left out: the event named the item, a
    search had just listed it, or the item was edited after the event), recall
    and strict recall, F1, F0.5 and strict F0.5, bytes per session, echo share,
    and the p50 /
    p99 of the decision's own latency (interpreter start-up is measured apart,
    by the hook benchmark).

A hit: an injected claim whose item the agent itself first fetched within
`window` tool calls after the injection landed. Recall: the share of needed
fetches (first self-directed fetches, after the masks; ctx_s1_replay) that an
injection of the same item preceded within the window. An injected item that
injected text had already pointed at is unjudgeable: neither hit nor miss.
Echo: a prompt-stage hit whose item the prompt itself named (the gate read
the answer off the prompt).

Arms, so the metric is shown to separate (memory eval-harness-vacuity-patterns):
    gate        the parameters under test, every stage the params give a floor
    always      inject the best candidates at every event, floors and caps off
    never       abstain everywhere
    wrong-key   the gate, fed another session's keys for each event (a mutant)
    stage:<s>   the gate with one stage on, the others off (E2's one-stage
                arms); not for compact and subagent, which only re-offer
                claims another stage injected and so never inject alone

Separation is read on the TEST split, on strict hits: the gate must inject
and strictly hit, `always` must inject more, cost more and score below it, and
`wrong-key` must score below it. It is a harness check, not a quality claim:
on a thin split it can pass on a single strict hit, which the report states;
the quality claim is the spec's bar, which the report prints per stage. CI
checks the harness on a synthetic fixture where a working gate exists
(tests/test_s1_e1_synthetic.py).

E3, `ctx-s1 tune`: propose floor, budget and channel-weight changes, score each
on train by strict F0.5 (the metric the bar uses), accept only when train
improves on at least MIN_TRAIN_STRICT_HITS strict hits, validation does not
regress, and bytes per session do not grow unless strict recall does. No
proposal is scored twice.
Every trial goes to a ledger with its full parameters. A stage keeps no floor
(abstains on everything) unless it clears the spec's bar on the test split,
which no trial reads, alone, on strict hits: precision >= 0.30 over >= 50
injections (workspace#840 §6.2). Deterministic
for a seed, bounded by --trials, and it only reads the snapshot; the ledger
names the snapshot's sha256.
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import ctx  # noqa: E402
import ctx_s1
import ctx_s1_replay as R
import ctx_s2

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

REPORT_SCHEMA = 1
SPLITS = ("train", "validation", "test")
EVAL_STAGES = ("session-start", "prompt", "pre-edit", "post-read", "post-bash", "subagent", "compact")
#: The spec's bar for a stage to get a floor at all (§6.2): used at least 30%
#: of the time over at least 50 injections. E1's precision stands in for "used".
MIN_PRECISION = 0.30
MIN_INJECTIONS = 50
#: tune does not accept a change its train score owes to fewer strict hits
#: than this: one hit is noise to fit a floor to.
MIN_TRAIN_STRICT_HITS = 2


# --------------------------------------------------------------------------
# The replay cache: the snapshot's items through the real writer

def snapshot_items(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Snapshot items as System 2 items. Claims and sources are placeholders of
    their true lengths, so bytes and budgets are measured on the real sizes."""
    out = []
    for h in snap["items"]:
        out.append({"id": "i%d" % h["i"], "type": h["t"], "claim": "c" * int(h.get("len") or 0),
                    "source": "s" * int(h.get("slen", 40)), "obj": h.get("o", []), "created": h.get("c", 0),
                    "keys": h.get("k", {}), "L": h.get("L", {}), "links": h.get("ln", [])})
    return out


def build_cache(snap: Dict[str, Any], store: Path, ranker: str = "bm25") -> Path:
    items = snapshot_items(snap)
    r = ctx_s2.get_ranker(ranker)
    r.fit(items)
    return ctx_s2.write_cache(store, items, r, {"scope": "snapshot", "snapshot": snap["meta"].get("sha256")},
                              now=0.0)


# --------------------------------------------------------------------------
# One replay

def _fresh_state() -> Dict[str, Any]:
    return {"v": ctx_s1.SCHEMA, "injected": {}, "paths": {}, "counts": {}, "subagents": []}


def _donors(sessions: Sequence[Dict[str, Any]]) -> Dict[Tuple[int, int], Dict[str, Any]]:
    """wrong-key: each keyed event gets the keys of a same-stage event from
    ANOTHER session: the one halfway round the list, or the next one after it
    that belongs to a different session. Deterministic."""
    by_stage: Dict[str, List[Tuple[int, int]]] = {}
    for s in sessions:
        for j, e in enumerate(s["events"]):
            by_stage.setdefault(e["st"], []).append((s["s"], j))
    look = {(s["s"], j): e for s in sessions for j, e in enumerate(s["events"])}
    out = {}
    for st, lst in by_stage.items():
        n = len(lst)
        for pos, ref in enumerate(lst):
            donor = None
            for step in range(n):
                cand = lst[(pos + n // 2 + step) % n]
                if cand[0] != ref[0]:
                    donor = look[cand]
                    break
            out[ref] = donor if donor is not None else {"st": st, "k": {}}
    return out


def _new_bucket() -> Dict[str, Any]:
    return {"events": 0, "keyless": 0, "injections": 0, "claims": 0, "hits": 0, "unjudgeable": 0,
            "echo_hits": 0, "listed_hits": 0, "edited_hits": 0, "easy_hits": 0, "bytes": 0, "abstain": {},
            "ms": [], "needed": 0, "covered": 0, "covered_strict": 0, "sessions": 0}


def windows(tool: int = R.DEFAULT_WINDOW, turn: int = R.TURN_WINDOW, sub: int = R.SUB_WINDOW) -> Dict[str, int]:
    return {"pre-edit": tool, "post-read": tool, "post-bash": tool, "prompt": turn, "session-start": turn,
            "compact": turn, "subagent": sub}


def replay(snap: Dict[str, Any], store: Path, params: Dict[str, Any], arm: str = "gate",
           stages: Optional[Sequence[str]] = None, window: int = R.DEFAULT_WINDOW,
           timing: bool = True, turn_window: int = R.TURN_WINDOW) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """{split: {stage | "all": metrics}} for one arm.

    Each hit is also classified: an echo (the event's own text named the item),
    listed (a tool's output just before the fetch named it: the agent, or the
    subagent, read what a search had printed), or edited later (the item's file
    changed after the event, so the replay's copy may hold keys the live gate
    lacked). A hit of any of these kinds is an easy hit; strict precision and
    strict recall leave them out."""
    stages = tuple(stages or EVAL_STAGES)
    win = windows(window, turn_window)
    mode = {"always": "always", "never": "never"}.get(arm, "gate")
    items = snap["items"]
    donors = _donors(snap["sessions"]) if arm == "wrong-key" else {}
    shared_reader = None if timing else ctx_s1.CacheReader(store)
    out: Dict[str, Dict[str, Dict[str, Any]]] = {sp: {} for sp in SPLITS}
    for s in snap["sessions"]:
        sp = s["split"]
        agg = out[sp]
        state = _fresh_state()
        needed = {row[0]: (row[1], row[2] if len(row) > 2 else 0) for row in s["needed"]}
        pointed = {i: o for i, o in s.get("pointed", [])}
        covered: Dict[int, str] = {}
        covered_strict: Dict[int, str] = {}
        seen_stage: Set[str] = set()
        sub_needed = sub_covered = sub_strict = 0
        for st, n in (s.get("keyless") or {}).items():
            if st in stages:
                b = agg.setdefault(st, _new_bucket())
                b["events"] += n
                b["keyless"] += n
                b["abstain"]["no-key"] = b["abstain"].get("no-key", 0) + n
        for j, e in enumerate(s["events"]):
            st = e["st"]
            if st not in stages:
                continue
            seen_stage.add(st)
            b = agg.setdefault(st, _new_bucket())
            b["events"] += 1
            src = donors.get((s["s"], j), e) if arm == "wrong-key" else e
            keys = {ch: list(v) for ch, v in (src.get("k") or {}).items()}
            ts = e["ts"]
            eligible = (lambda idx, ts=ts: items[idx].get("c", 0) <= ts)
            t0 = time.perf_counter()
            reader = shared_reader if shared_reader is not None else ctx_s1.CacheReader(store)
            d = ctx_s1.decide(st, keys, set(e.get("self") or []), state, reader, params,
                              label="x" * int(e.get("ll", 40)), path_key=e.get("pk"),
                              agent_id="sub-%d-%d" % (s["s"], j) if st == "subagent" else None,
                              agent_type="reviewer" if e.get("rev") else "general-purpose",
                              mode=mode, eligible=eligible)
            b["ms"].append((time.perf_counter() - t0) * 1000)
            ctx_s1.record(state, st, d, e.get("pk"), "sub-%d-%d" % (s["s"], j) if st == "subagent" else None,
                          float(ts), opened=set(e.get("self") or []))
            if st == "subagent" and e.get("sub") is not None:
                sub_needed += sum(1 for row in e["sub"] if row[1] < win["subagent"])
            if d["outcome"] != "inject":
                b["abstain"][d["reason"]] = b["abstain"].get(d["reason"], 0) + 1
                continue
            b["injections"] += 1
            b["bytes"] += d["bytes"]
            a = e["a"]
            w = win[st]
            echo = set(e.get("echo") or [])
            sub = {row[0]: (row[1], row[2]) for row in (e.get("sub") or [])} if st == "subagent" else None
            for iid in d["injected"]:
                idx = int(iid[1:])
                b["claims"] += 1
                edited = items[idx].get("m", 0) > ts
                if st == "subagent":
                    if e.get("sub") is None:
                        b["unjudgeable"] += 1
                    elif idx in sub and sub[idx][0] < w:
                        b["hits"] += 1
                        sub_covered += 1
                        listed = sub[idx][1]
                        b["listed_hits"] += bool(listed)
                        b["edited_hits"] += edited
                        if listed or edited:
                            b["easy_hits"] += 1
                        else:
                            sub_strict += 1
                    continue
                p_at = pointed.get(idx)
                if p_at is not None and p_at <= a:
                    b["unjudgeable"] += 1  # injected text had already pointed at it
                    continue
                o, listed = needed.get(idx, (None, 0))
                if not (o is not None and a <= o < a + w) and p_at is not None and p_at < a + w:
                    # not fetched before a pointer that landed inside the
                    # window: whether the claim or the pointer would have led
                    # to the fetch cannot be told apart
                    b["unjudgeable"] += 1
                    continue
                if o is not None and a <= o < a + w:
                    b["hits"] += 1
                    covered.setdefault(idx, st)
                    b["echo_hits"] += idx in echo
                    b["listed_hits"] += bool(listed)
                    b["edited_hits"] += edited
                    easy = bool(idx in echo or listed or edited)
                    b["easy_hits"] += easy
                    if not easy:
                        covered_strict.setdefault(idx, st)
        for st in seen_stage | {k for k in (s.get("keyless") or {}) if k in stages}:
            agg.setdefault(st, _new_bucket())["sessions"] += 1
        # recall: the session's own needed fetches, credited to the stage that
        # covered them; a subagent's needed fetches are its stage's (and all's)
        allb = agg.setdefault("all", _new_bucket())
        allb["sessions"] += 1
        allb["needed"] += len(needed) + sub_needed
        allb["covered"] += len(covered) + sub_covered
        allb["covered_strict"] += len(covered_strict) + sub_strict
        for st in stages:
            if st == "subagent":
                continue
            agg.setdefault(st, _new_bucket())["needed"] += len(needed)
        for idx, st in covered.items():
            agg[st]["covered"] += 1
        for idx, st in covered_strict.items():
            agg[st]["covered_strict"] += 1
        if "subagent" in stages:
            sb = agg.setdefault("subagent", _new_bucket())
            sb["needed"] += sub_needed
            sb["covered"] += sub_covered
            sb["covered_strict"] += sub_strict
    for sp in SPLITS:
        _roll_all(out[sp], stages)
        for st, b in out[sp].items():
            _finish(b)
    return out


def _roll_all(agg: Dict[str, Dict[str, Any]], stages: Sequence[str]) -> None:
    allb = agg.setdefault("all", _new_bucket())
    for st in stages:
        b = agg.get(st)
        if not b:
            continue
        for k in ("events", "keyless", "injections", "claims", "hits", "unjudgeable", "echo_hits", "listed_hits",
                  "edited_hits", "easy_hits", "bytes"):
            allb[k] += b[k]
        for r, n in b["abstain"].items():
            allb["abstain"][r] = allb["abstain"].get(r, 0) + n
        allb["ms"] += b["ms"]


def _pct(xs: List[float], q: float) -> Optional[float]:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, max(0, int(round(q * len(xs))) - 1))], 3)


def _finish(b: Dict[str, Any]) -> None:
    judged = b["claims"] - b["unjudgeable"]
    p = b["hits"] / judged if judged else None
    sp = (b["hits"] - b["easy_hits"]) / judged if judged else None
    r = b["covered"] / b["needed"] if b["needed"] else None
    sr = b["covered_strict"] / b["needed"] if b["needed"] else None
    b["precision"] = round(p, 4) if p is not None else None
    b["strict_precision"] = round(sp, 4) if sp is not None else None
    b["recall"] = round(r, 4) if r is not None else None
    b["strict_recall"] = round(sr, 4) if sr is not None else None

    def fb(beta: float, p: Optional[float], r: Optional[float]) -> Optional[float]:
        if not p or not r:
            return 0.0 if (p is not None or r is not None) else None
        return round((1 + beta * beta) * p * r / (beta * beta * p + r), 4)

    b["f1"], b["f05"] = fb(1.0, p, r), fb(0.5, p, r)
    b["strict_f05"] = fb(0.5, sp, sr)
    b["injection_rate"] = round(b["injections"] / b["events"], 4) if b["events"] else None
    b["abstain_rate"] = round(1 - b["injections"] / b["events"], 4) if b["events"] else None
    b["bytes_per_session"] = round(b["bytes"] / b["sessions"], 1) if b["sessions"] else 0.0
    b["echo_share"] = round(b["echo_hits"] / b["hits"], 4) if b["hits"] else None
    b["p50_ms"], b["p99_ms"] = _pct(b["ms"], 0.5), _pct(b["ms"], 0.99)
    b["decisions_timed"] = len(b["ms"])
    del b["ms"]


# --------------------------------------------------------------------------
# E1: every arm, the separation check, the report

def default_arms(params: Dict[str, Any]) -> List[str]:
    return ["gate", "always", "never", "wrong-key"] + ["stage:" + s for s in TUNED_STAGES]


def evaluate(snap: Dict[str, Any], params: Dict[str, Any], window: int = R.DEFAULT_WINDOW,
             ranker: str = "bm25", arms: Optional[Sequence[str]] = None, timing: bool = True,
             workdir: Optional[Path] = None) -> Dict[str, Any]:
    arms = list(arms or default_arms(params))
    tmp = tempfile.mkdtemp(prefix="ctx-s1-e1-", dir=str(workdir) if workdir else None)
    store = Path(tmp) / "store"
    try:
        build_cache(snap, store, ranker)
        results: Dict[str, Any] = {}
        for arm in arms:
            if arm.startswith("stage:"):
                st = arm.split(":", 1)[1]
                results[arm] = replay(snap, store, params, "gate", stages=[st], window=window, timing=timing)
            else:
                results[arm] = replay(snap, store, params, arm, window=window, timing=timing)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    return {"schema": REPORT_SCHEMA, "snapshot": {k: snap["meta"].get(k) for k in (
        "sha256", "scope", "created_day", "days", "sessions", "events", "keyed_events", "needed", "items",
        "splits", "by_stage", "by_type")},
        "params": params.get("version"), "params_body": params, "ranker": ranker, "window": window,
        "arms": results, "separation": separation(results)}


SEPARATION_FIELDS = ("injections", "hits", "easy_hits", "precision", "strict_precision", "recall",
                     "strict_recall", "f05", "strict_f05", "bytes")


def separation(results: Dict[str, Any], split: str = "test") -> Dict[str, Any]:
    """The vacuity guard, on the TEST split (the floors were fitted on train,
    so a check read there would pass by construction) and on strict hits (the
    metric the bar uses): the gate must inject and strictly hit, `always` must
    inject more, cost more and score below it on strict precision and strict
    F0.5, `wrong-key` must score below it, and `never` must inject nothing.
    Every comparison is strict, so an inert gate fails it."""
    g = {arm: ((results.get(arm) or {}).get(split) or {}).get("all") or {}
         for arm in ("gate", "always", "never", "wrong-key") if arm in results}
    v = lambda arm, key: (g.get(arm) or {}).get(key) or 0
    strict_hits = lambda arm: v(arm, "hits") - v(arm, "easy_hits")
    checks = {
        "never_injects_nothing": "never" in g and v("never", "injections") == 0,
        "gate_injects": v("gate", "injections") > 0,
        "gate_hits_strictly": strict_hits("gate") > 0,
        "always_injects_more": v("always", "injections") > v("gate", "injections"),
        "always_costs_more_bytes": v("always", "bytes") > v("gate", "bytes"),
        "always_below_gate_strict_precision": v("always", "strict_precision") < v("gate", "strict_precision"),
        "always_below_gate_strict_f05": v("always", "strict_f05") < v("gate", "strict_f05"),
        "wrong_key_below_gate_strict_f05": "wrong-key" in g and v("wrong-key", "strict_f05") < v("gate",
                                                                                                "strict_f05"),
    }
    return {"split": split, "checks": checks, "ok": all(checks.values()),
            "arms": {arm: {k: b.get(k) for k in SEPARATION_FIELDS} for arm, b in g.items()}}


def render_md(rep: Dict[str, Any], split: str = "test") -> str:
    snap = rep["snapshot"]
    lines = ["# E1 replay: ctx System 1 gate", "",
             "Snapshot `%s` (scope %s, %s days to %s, %d sessions split %s, %d events, %d needed fetches). "
             "Params `%s`, ranker %s, window %d tool calls (30 for a prompt, start or compaction). "
             "Split shown: **%s**. Strict precision leaves out easy hits (the event named the item, a search "
             "had just listed it, or the item was edited after the event)." % (
                 str(snap.get("sha256"))[:12], snap.get("scope"), snap.get("days"), snap.get("created_day"),
                 snap.get("sessions") or 0, json.dumps(snap.get("splits")), snap.get("events") or 0,
                 snap.get("needed") or 0, rep["params"], rep["ranker"], rep["window"], split), "",
             "| arm | stage | events | inj rate | claims | hits (easy) | precision | strict precision | recall | "
             "F0.5 | bytes/session | p99 ms |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def fmt(x, pct=False):
        if x is None:
            return "—"
        return ("%.1f%%" % (100 * x)) if pct else (("%.3f" % x) if isinstance(x, float) else str(x))

    for arm, res in rep["arms"].items():
        rows = res.get(split) or {}
        order = ["all"] + [s for s in EVAL_STAGES if s in rows] if not arm.startswith("stage:") else \
            [arm.split(":", 1)[1]]
        for st in order:
            b = rows.get(st)
            if not b:
                continue
            lines.append("| %s | %s | %d | %s | %d | %d (%d) | %s | %s | %s | %s | %s | %s |" % (
                arm, st, b["events"], fmt(b["injection_rate"], True), b["claims"], b["hits"], b["easy_hits"],
                fmt(b["precision"]), fmt(b["strict_precision"]), fmt(b["recall"]), fmt(b["f05"]),
                fmt(b["bytes_per_session"]), fmt(b["p99_ms"])))
    sep = rep["separation"]
    lines += ["", "Separation on the %s split, strict hits: %s" % (sep["split"], "PASS" if sep["ok"] else "FAIL"),
              ""]
    lines += ["- %s: %s" % (k, "ok" if v else "FAILED") for k, v in sep["checks"].items()]
    lines += ["", "| arm (%s, all stages) | injections | hits (easy) | strict precision | strict recall | "
                  "strict F0.5 | bytes |" % sep["split"], "|---|---|---|---|---|---|---|"]
    for arm, b in (sep.get("arms") or {}).items():
        lines.append("| %s | %d | %d (%d) | %s | %s | %s | %d |" % (
            arm, b["injections"] or 0, b["hits"] or 0, b["easy_hits"] or 0, fmt(b["strict_precision"]),
            fmt(b["strict_recall"]), fmt(b["strict_f05"]), b["bytes"] or 0))
    g = (sep.get("arms") or {}).get("gate") or {}
    strict = (g.get("hits") or 0) - (g.get("easy_hits") or 0)
    lines += ["", ("Separation checks the harness, not the gate's worth: here it rests on %d strict hit(s) by the "
                   "gate in %d injections." if sep["ok"] else
                   "Separation fails: the gate makes %d strict hit(s) in %d injections on this split, so the "
                   "replay cannot tell it from the mutant arms here.") % (strict, g.get("injections") or 0)]
    bar = [(arm.split(":", 1)[1], (res.get("test") or {}).get(arm.split(":", 1)[1]) or {})
           for arm, res in rep["arms"].items() if arm.startswith("stage:")]
    if bar:
        lines += ["", "The spec's bar, test split, each stage alone (strict precision >= %.2f over >= %d "
                      "injections): %s" % (MIN_PRECISION, MIN_INJECTIONS,
                                           "PASS" if any(_clears(b) for _, b in bar) else "no stage passes"), "",
                  "| stage | injections | `always` injects | strict precision | bar |", "|---|---|---|---|---|"]
        alw = ((rep["arms"].get("always") or {}).get("test") or {})
        for st, b in bar:
            lines.append("| %s | %d | %s | %s | %s |" % (
                st, b.get("injections") or 0, (alw.get(st) or {}).get("injections", "—"),
                fmt(b.get("strict_precision")), "pass" if _clears(b) else "fail"))
        lines += ["", "A stage whose injections equal `always`'s is not gated by its floor."]
    return "\n".join(lines) + "\n"


def _clears(b: Dict[str, Any]) -> bool:
    return (b.get("injections") or 0) >= MIN_INJECTIONS and (b.get("strict_precision") or 0) >= MIN_PRECISION


# --------------------------------------------------------------------------
# E3: the tune loop

TUNABLE_CHANNELS = ("p", "d", "f", "b", "pr", "t", "w")
FLOOR_GRID = (0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30)
BUDGET_GRID = {"prompt": (600, 1000, 1500), "session-start": (600, 1000, 1500), "compact": (600, 1500),
               "pre-edit": (300, 600), "post-read": (300, 600), "post-bash": (300, 600), "subagent": (500, 1000)}


#: Stages that can inject on their own: compact and subagent only re-offer what
#: another stage injected, so they are neither tuned nor given a one-stage arm.
TUNED_STAGES = tuple(s for s in EVAL_STAGES if s in ctx_s1.ALONE_STAGES)


def objective(res: Dict[str, Any], split: str, stage: str = "all") -> Dict[str, Any]:
    """Strict F0.5: easy hits (echo, listed, edited later) left out, as the
    spec's bar leaves them out."""
    a = res[split].get(stage) or {}
    return {"strict_f05": a.get("strict_f05") or 0.0, "strict_precision": a.get("strict_precision"),
            "strict_hits": (a.get("hits") or 0) - (a.get("easy_hits") or 0),
            "strict_recall": a.get("strict_recall") or 0.0, "f05": a.get("f05") or 0.0,
            "bytes": a.get("bytes_per_session") or 0.0, "injections": a.get("injections") or 0}


def _canon(params: Dict[str, Any]) -> Dict[str, Any]:
    """The parameters as the gate reads them: a stage setting equal to the stage
    table's default is dropped, so `max 3 -> 3` is the same proposal as none."""
    p = _clean(params)
    for st, cfg in list(p["stages"].items()):
        base = ctx_s1.STAGES.get(st, {})
        p["stages"][st] = {k: v for k, v in cfg.items() if not (k in ("max", "budget") and base.get(k) == v)}
    return p


def _clean(params: Dict[str, Any]) -> Dict[str, Any]:
    p = json.loads(json.dumps(params, sort_keys=True))
    p.setdefault("stages", {})
    p.setdefault("channel_weights", dict(ctx_s1.DEFAULT_PARAMS["channel_weights"]))
    return p


def propose(params: Dict[str, Any], rng: random.Random, stage: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
    """One change. For a stage: its floor, its per-event cap, or its budget.
    With no stage: one channel weight."""
    p = _clean(params)
    if stage is None:
        ch = rng.choice(TUNABLE_CHANNELS)
        cur = float(p["channel_weights"].get(ch, 0.0))
        new = round(max(0.0, min(2.0, cur + rng.choice((-0.4, -0.2, 0.2, 0.4)))), 2)
        p["channel_weights"][ch] = new
        return p, "weight %s %.2f -> %.2f" % (ch, cur, new)
    cfg = p["stages"].setdefault(stage, {})
    kind = rng.choice(("floor", "floor", "floor", "max", "budget")) if cfg.get("floor") is not None else "floor"
    if kind == "max":
        cur = int(cfg.get("max", ctx_s1.STAGES[stage]["max"]))
        new = max(1, min(ctx_s1.STAGES[stage]["max"], cur + rng.choice((-1, 1))))
        cfg["max"] = new
        return p, "max %s %d -> %d" % (stage, cur, new)
    if kind == "budget":
        cur = cfg.get("budget", ctx_s1.STAGES[stage]["budget"])
        new = rng.choice([b for b in BUDGET_GRID[stage] if b != cur] or [cur])
        cfg["budget"] = new
        return p, "budget %s %s -> %s" % (stage, cur, new)
    cur = cfg.get("floor")
    if cur is None:
        new = rng.choice(FLOOR_GRID)
    else:
        i = min(range(len(FLOOR_GRID)), key=lambda k: abs(FLOOR_GRID[k] - cur))
        j = max(0, min(len(FLOOR_GRID) - 1, i + rng.choice((-2, -1, 1, 2))))
        new = FLOOR_GRID[j]
    cfg["floor"] = new
    return p, "floor %s %s -> %s" % (stage, cur, new)


def enforce_bar(params: Dict[str, Any], per_stage_test: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Drop the floor of any stage that does not clear the spec's bar on the
    TEST split (which no trial looked at), with that stage alone, counting only
    strict hits: precision >= MIN_PRECISION over >= MIN_INJECTIONS injections."""
    p = _clean(params)
    dropped = []
    for st in EVAL_STAGES:
        cfg = p["stages"].get(st) or {}
        if cfg.get("floor") is None:
            continue
        b = per_stage_test.get(st) or {}  # compact and subagent are never measured alone: no floor
        if not _clears(b):
            cfg["floor"] = None
            dropped.append("%s (strict precision %s over %d injections, test)" % (
                st, b.get("strict_precision"), b.get("injections", 0)))
    return p, dropped


def accept(cur_train, cur_valid, new_train, new_valid) -> Tuple[bool, str]:
    """On strict F0.5: train must improve; validation must not fall; bytes must
    not grow on validation unless strict recall does."""
    k = "strict_f05"
    if new_train[k] <= cur_train[k]:
        return False, "train strict F0.5 did not improve (%.4f <= %.4f)" % (new_train[k], cur_train[k])
    if new_train.get("strict_hits", 0) < MIN_TRAIN_STRICT_HITS:
        return False, "train gain rests on %d strict hit(s), under %d" % (new_train.get("strict_hits", 0),
                                                                        MIN_TRAIN_STRICT_HITS)
    if new_valid[k] < cur_valid[k]:
        return False, "validation strict F0.5 regressed (%.4f < %.4f)" % (new_valid[k], cur_valid[k])
    if new_valid["bytes"] > cur_valid["bytes"] and new_valid["strict_recall"] <= cur_valid["strict_recall"]:
        return False, "bytes grew (%.0f > %.0f) without strict recall" % (new_valid["bytes"], cur_valid["bytes"])
    return True, "train strict F0.5 %.4f -> %.4f; validation %.4f -> %.4f" % (
        cur_train[k], new_train[k], cur_valid[k], new_valid[k])


def tune(snap: Dict[str, Any], params: Dict[str, Any], trials: int = 42, seed: int = 1,
         ledger: Optional[Path] = None, window: int = R.DEFAULT_WINDOW, log=print,
         ranker: str = "bm25") -> Dict[str, Any]:
    """Bounded coordinate search, one phase per stage and a last one for the
    channel weights. A stage phase scores that stage alone (the way E2 runs
    it); the weight phase scores every stage that has a floor, together. At
    most `trials` replays in all. Returns {params (bar applied), tuned_params,
    history, summary}."""
    rng = random.Random(seed)
    tmp = tempfile.mkdtemp(prefix="ctx-s1-e3-")
    store = Path(tmp) / "store"
    history: List[Dict[str, Any]] = []
    phases = list(TUNED_STAGES) + ["weights"]
    tried: Set[str] = set()
    per = max(1, trials // len(phases))
    try:
        build_cache(snap, store, ranker)

        def score(p, stages, obj_stage):
            res = replay(snap, store, p, "gate", stages=stages, window=window, timing=False)
            return res, objective(res, "train", obj_stage), objective(res, "validation", obj_stage)

        cur = _clean(params)
        t = 0
        for phase in phases:
            if phase == "weights":
                on = [s for s in TUNED_STAGES if (cur["stages"].get(s) or {}).get("floor") is not None]
                stages, obj_stage = (on or list(TUNED_STAGES)), "all"
            else:
                stages, obj_stage = [phase], phase
            _, cur_tr, cur_ho = score(cur, stages, obj_stage)
            for _ in range(per):
                for _attempt in range(25):  # a no-op or an already-scored proposal is drawn again
                    cand, what = propose(cur, rng, None if phase == "weights" else phase)
                    sig = json.dumps(_canon(cand), sort_keys=True)
                    if sig not in tried and sig != json.dumps(_canon(cur), sort_keys=True):
                        break
                else:
                    continue
                tried.add(sig)
                _, tr, ho = score(cand, stages, obj_stage)
                ok, why = accept(cur_tr, cur_ho, tr, ho)
                rec = {"trial": t, "phase": phase, "seed": seed, "ranker": ranker, "change": what,
                       "train": tr, "validation": ho, "params": cand,
                       "accepted": ok, "why": why, "snapshot": snap["meta"].get("sha256"), "ts": ctx.now_ts()}
                history.append(rec)
                if ledger is not None:
                    with open(ledger, "a") as fh:
                        fh.write(json.dumps(rec, sort_keys=True) + "\n")
                log("trial %2d %-13s %-6s %-30s train strict F0.5 %.4f  validation %.4f  %s" % (
                    t, phase, "ACCEPT" if ok else "reject", what, tr["strict_f05"], ho["strict_f05"], why))
                t += 1
                if ok:
                    cur, cur_tr, cur_ho = cand, tr, ho
        per_stage: Dict[str, Any] = {}
        for st in TUNED_STAGES:
            res = replay(snap, store, cur, "gate", stages=[st], window=window, timing=False)
            per_stage[st] = {sp: {k: (res[sp].get(st) or {}).get(k) for k in (
                "injections", "claims", "hits", "easy_hits", "precision", "strict_precision", "recall",
                "strict_recall", "f05", "strict_f05", "bytes_per_session")}
                for sp in SPLITS}
        final, dropped = enforce_bar(cur, {st: v["test"] for st, v in per_stage.items()})
        if dropped:
            log("no floor (the spec's bar, strict precision >= %.2f over >= %d injections on TEST, stage alone): %s" % (
                MIN_PRECISION, MIN_INJECTIONS, "; ".join(dropped)))
        summary = {"trials": t, "per_phase": per, "accepted": sum(1 for h in history if h["accepted"]),
                   "per_stage_tuned": per_stage, "dropped_by_bar": dropped,
                   "stages_with_a_floor": [s for s in TUNED_STAGES
                                           if (final["stages"].get(s) or {}).get("floor") is not None]}
        if ledger is not None:
            with open(ledger, "a") as fh:
                fh.write(json.dumps({"summary": summary, "params": final, "tuned_params": cur, "seed": seed,
                                     "ranker": ranker,
                                     "trials": trials, "snapshot": snap["meta"].get("sha256"),
                                     "ts": ctx.now_ts()}, sort_keys=True) + "\n")
        return {"params": final, "tuned_params": cur, "history": history, "summary": summary}
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# Follow-through of live injections: the decisions log joined to transcripts

def follow_through(scope, days: float = 7.0, window: int = R.DEFAULT_WINDOW,
                   now: Optional[float] = None) -> Dict[str, Any]:
    """For each live injection in the scope's decisions log: did the session
    later open the item's object within `window` tool calls? The same notion of
    a use as bstack's context_ledger (a Read or shell read of the path, `kg
    load`, `gh pr view`). Per stage: injected, followed, rate. Shadow decisions
    are counted apart. SubagentStart is left out: its claims went into the
    subagent's context, and this joins the parent's transcript only."""
    now = time.time() if now is None else now
    log = ctx_s1.log_path(scope.store)
    decisions: Dict[str, List[Dict[str, Any]]] = {}
    for p in (Path(str(log) + ".1"), log):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("outcome") == "inject" and d.get("session") and d.get("stage") != "subagent":
                # a subagent's claims went into its own context; the parent's
                # calls do not follow them
                decisions.setdefault(d["session"], []).append(d)
    by_stage: Dict[str, Dict[str, int]] = {}
    items_obj: Dict[str, List[str]] = {}
    try:
        reader = ctx_s1.CacheReader(scope.store)
        for f in sorted((reader.dir / "items").iterdir()):
            for rec in json.loads(f.read_bytes()).values():
                items_obj[rec["id"]] = rec.get("obj") or []
    except (OSError, ValueError):
        pass
    scopes = ctx.load_scopes()
    for path in R.transcripts(days, now):
        sid = path.stem
        if sid not in decisions:
            continue
        raw = R.read_session(path, scopes, scope.id)
        if raw is None:
            continue
        uses = raw["fetches"]
        for d in decisions[sid]:
            b = by_stage.setdefault("%s/%s" % (d["stage"], d.get("mode")), {"injected": 0, "followed": 0})
            anchor = _anchor_of(raw, d)
            for iid in d.get("injected", []):
                b["injected"] += 1
                objs = set(items_obj.get(iid, []))
                if anchor is not None and any(anchor <= f[0] < anchor + window and objs & set(f[1]) for f in uses):
                    b["followed"] += 1
    for b in by_stage.values():
        b["rate"] = round(b["followed"] / b["injected"], 4) if b["injected"] else None
    return {"scope": scope.id, "days": days, "window": window, "by_stage": by_stage,
            "note": "live follow-through is a proxy: a claim read in context leaves no tool call (spec §6.5)"}


def _anchor_of(raw: Dict[str, Any], d: Dict[str, Any]) -> Optional[int]:
    """The ordinal of the first tool call after a decision, from its time."""
    try:
        t = ctx.parse_ts(d["ts"])
    except (KeyError, ValueError, IndexError):
        return None
    best = None
    for ev in raw["events"]:
        if ev.get("ts") and ev["ts"] >= t - 1:
            best = ev["anchor"]
            break
    return best


# --------------------------------------------------------------------------
# CLI (dispatched from ctx_s1_cli.py: `ctx-s1 eval|tune|snapshot|follow`)

def _load_params(path: Optional[str]) -> Dict[str, Any]:
    """`default` is ctx_s1.DEFAULT_PARAMS (no floor, default weights): the start
    a tune run can be reproduced from without any earlier tuning."""
    if path == "default":
        return dict(json.loads(json.dumps(ctx_s1.DEFAULT_PARAMS)), version="default")
    if path:
        os.environ["CTX_S1_PARAMS"] = path
    return ctx_s1.load_params()


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="ctx-s1")
    ap.add_argument("-C", dest="cwd", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sn = sub.add_parser("snapshot", help="extract a hashed replay snapshot from local transcripts")
    sn.add_argument("--out", help="default: the scope's private dir, %s" % R.default_dir("<scope>"))
    sn.add_argument("--scope", default=None)
    sn.add_argument("--days", type=float, default=R.DEFAULT_DAYS)
    sn.add_argument("--no-network", action="store_true")
    ev = sub.add_parser("eval", help="E1: replay a snapshot through the gate and every arm")
    ev.add_argument("--snapshot", help="snapshot dir (default: the scope's private one)")
    ev.add_argument("--params")
    ev.add_argument("--out", help="write e1-report.json and e1-report.md here")
    ev.add_argument("--window", type=int, default=R.DEFAULT_WINDOW)
    ev.add_argument("--ranker", default="bm25", choices=["bm25", "ppr"])
    ev.add_argument("--arms", help="comma list (default: gate,always,never,wrong-key,stage:*)")
    ev.add_argument("--no-timing", action="store_true")
    ev.add_argument("--split", default="test", choices=SPLITS)
    tu = sub.add_parser("tune", help="E3: propose and score parameter changes on E1")
    tu.add_argument("--snapshot")
    tu.add_argument("--params")
    tu.add_argument("--trials", type=int, default=40)
    tu.add_argument("--seed", type=int, default=1)
    tu.add_argument("--window", type=int, default=R.DEFAULT_WINDOW)
    tu.add_argument("--ledger", help="append every trial here (JSON lines)")
    tu.add_argument("--ranker", default="bm25", choices=["bm25", "ppr"])
    tu.add_argument("--write", help="write the parameters that pass the spec's bar here (stages below it get no floor)")
    tu.add_argument("--write-candidate", help="write the tuned parameters, bar not applied (for E2 and shadow runs)")
    fo = sub.add_parser("follow", help="follow-through of live injections (decisions log x transcripts)")
    fo.add_argument("--days", type=float, default=7.0)
    args = ap.parse_args(argv)
    cwd = os.path.abspath(args.cwd or os.getcwd())
    if args.cmd == "snapshot":
        scope_id = args.scope or getattr(ctx.resolve_scope(cwd), "id", None)
        if not scope_id:
            print("no scope", file=sys.stderr)
            return 1
        try:
            meta = R.build_snapshot(scope_id, Path(args.out) if args.out else R.default_dir(scope_id),
                                    days=args.days, network=not args.no_network,
                                    progress=lambda m: print(m, file=sys.stderr))
        except ValueError as exc:
            print("ctx-s1 snapshot: %s" % exc, file=sys.stderr)
            return 2
        print(json.dumps(meta, indent=1, sort_keys=True))
        return 0
    if args.cmd == "follow":
        scope = ctx.resolve_scope(os.path.abspath(args.cwd or os.getcwd()))
        if scope is None:
            return 0
        print(json.dumps(follow_through(scope, args.days), indent=1, sort_keys=True))
        return 0
    snap_dir = args.snapshot
    if not snap_dir:
        scope = ctx.resolve_scope(cwd)
        if scope is None:
            print("no scope and no --snapshot", file=sys.stderr)
            return 1
        snap_dir = str(R.default_dir(scope.id))
    snap = R.load_snapshot(Path(snap_dir) / "snapshot.jsonl.gz")
    params = _load_params(args.params)
    if args.cmd == "eval":
        arms = args.arms.split(",") if args.arms else None
        rep = evaluate(snap, params, window=args.window, ranker=args.ranker, arms=arms,
                       timing=not args.no_timing)
        md = render_md(rep, args.split)
        if args.out:
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "e1-report.json").write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
            (out / "e1-report.md").write_text(md)
        print(md)
        return 0 if rep["separation"]["ok"] else 1
    if args.cmd == "tune":
        res = tune(snap, params, trials=args.trials, seed=args.seed,
                   ledger=Path(args.ledger) if args.ledger else None, window=args.window, ranker=args.ranker)
        tag = "%s%s-s%d-t%d" % ("" if args.ranker == "bm25" else args.ranker + "-",
                                str(snap["meta"].get("sha256"))[:8], args.seed, args.trials)
        for path, body, kind in ((args.write, res["params"], "bar"), (args.write_candidate, res["tuned_params"],
                                                                          "candidate")):
            if not path:
                continue
            out = dict(body)
            out["version"] = "%s-%s" % (kind, tag)
            out["tuned_from"] = params.get("version")
            out["snapshot"] = snap["meta"].get("sha256")
            out["note"] = ("E3 tune, spec bar applied: a stage below strict precision %.2f over %d "
                           "injections on the test split has no floor" % (MIN_PRECISION, MIN_INJECTIONS)
                           if kind == "bar" else
                           "E3 tune, bar NOT applied: the best train strict F0.5 whose validation did not regress; "
                           "a proposal for E2 arms and shadow runs, not for injection")
            Path(path).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        print(json.dumps(res["summary"], indent=1, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
