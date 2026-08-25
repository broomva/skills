"""The gate suite: twelve gates, five stages, eleven of them fail closed.

This is what makes a map trustworthy without the operator reading it. Every gate
is a pure function over what the run left on disk -- the chained log, the
snapshots, the records -- so nothing here takes a producer's word for anything,
including the producer's word that a check ran.

Three properties are non-negotiable, and each exists against a failure this
workspace has actually shipped.

**Every gate reports its denominator.** `counted` is how many items the gate
examined. A check that silently iterates over an empty set is indistinguishable
from one that passed, and that is how a suite comes to report confidence it
never earned.

**A gate that could not run is not a pass.** `inconclusive` is its own status,
and for a fail-closed gate it makes the run `INVALID` exactly as `fail` does.
The tempting alternative -- treat "no verifier configured" as "nothing to
object to" -- turns the two most important gates into decoration.

**The suite proves itself every time.** `gate-suite-proven` runs a committed
fixture pair through each deterministic gate: planted decoys it must reject, and
an honest map it must accept. A suite that passes a decoy marks the run INVALID,
which is the missing polarity check that otherwise lets a gate self-certify --
without it, a gate whose predicate was inverted, or whose loop body was never
entered, reports the same green as one that works. The must-accept half is not
ceremony either: a gate that fails everything catches every decoy, so the decoys
alone could be satisfied by breaking the gate rather than by it working.

A note on the count. The spec's own table lists twelve gates, of which eleven
fail closed; BRO-2294 says thirteen. Twelve is what is implemented, because the
table is the specification and a thirteenth invented to match a tally would be a
gate that asserts nothing.

What this suite does NOT establish is worth stating in the same breath, since a
green run is otherwise easy to over-read: it certifies that a page at this URL,
held at this digest, verifiably says this. It does not certify that what the
page says is true. An inflated title, a phantom advisory board, a shell company
listing a nominee director each produce a fully green observed claim.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract as X  # noqa: E402
import fetchd as F  # noqa: E402
import store as S  # noqa: E402

#: Fail-closed gates make the run INVALID when they fail or cannot run.
#: An annotating gate never changes the verdict, however loud it is.
CLOSED = "closed"
ANNOTATE = "annotate"

PASS = "pass"
FAIL = "fail"
INCONCLUSIVE = "inconclusive"
ANNOTATED = "annotate"

VALID = "VALID"
INVALID = "INVALID"


@dataclass(frozen=True)
class GateResult:
    gate: str
    stage: str
    policy: str
    status: str
    counted: int
    detail: str = ""
    failures: tuple = ()

    def __post_init__(self) -> None:
        # A gate that examined nothing and reported `pass` is the exact shape
        # the spec's "recorded denominators" device exists against -- it reads
        # identically to a gate that checked a thousand things and found them
        # all sound. Passing on an empty set is often CORRECT (a map with no
        # edges has no inadmissible edges), so the rule is not "never pass at
        # zero"; it is that the reason must be stated where a reader will see
        # it. Enforced at construction so a new gate cannot forget.
        if self.counted == 0 and self.status == PASS and not self.detail:
            raise ValueError(
                f"{self.gate}: passed with an empty denominator and no reason. "
                "Say why there was nothing to check, or the pass is unreadable."
            )

    def as_dict(self) -> dict:
        return {
            "gate": self.gate,
            "stage": self.stage,
            "policy": self.policy,
            "status": self.status,
            "counted": self.counted,
            "detail": self.detail,
            "failures": list(self.failures[:20]),
            "n_failures": len(self.failures),
        }


def _result(gate, stage, policy, failures, counted, detail="", empty="") -> GateResult:
    """Build a result, requiring a reason whenever the denominator is zero.

    `empty` is the sentence a reader gets when the gate had nothing to examine.
    It is a separate argument rather than something the caller remembers to put
    in `detail`, because "remember to explain the empty case" is precisely the
    kind of instruction that holds until the next gate is added.
    """
    failures = tuple(failures)
    status = FAIL if failures else PASS
    if counted == 0 and status == PASS and not detail:
        detail = empty or "nothing of this kind in the map"
    return GateResult(gate, stage, policy, status, counted, detail, failures)


# --------------------------------------------------------------------------
# Stage: ingest
# --------------------------------------------------------------------------


def gate_plan_sealed_and_log_chained(daemon) -> GateResult:
    """The denominator was fixed before the run, and the log still holds together.

    A plan written after the fact makes what was found look like what was
    planned; an unchained log makes every row in it a suggestion.
    """
    name, stage = "plan-sealed-and-log-chained", "ingest"
    if not (daemon.dir / "plan.json").exists():
        return GateResult(name, stage, CLOSED, FAIL, 0, "no sealed plan.json")
    try:
        ok, reason, rows = F.verify_run(daemon.dir, daemon.key)
    except Exception as exc:
        return GateResult(name, stage, CLOSED, FAIL, 0, f"{type(exc).__name__}: {exc}")
    if not ok:
        return GateResult(name, stage, CLOSED, FAIL, len(rows or ()), reason)
    return GateResult(name, stage, CLOSED, PASS, len(rows), reason)


def gate_transport_custody(daemon, records) -> GateResult:
    """Nothing in the store came from anywhere but the wire.

    Three separate claims, because each fails differently: a snapshot must hash
    to its own name, every cited pair must appear in the chained log, and the
    host's robots.txt must itself have been fetched and snapshotted. The last one
    is the one a crawler is tempted to skip, and skipping it means "we honoured
    robots" rests on the daemon's memory rather than on bytes.
    """
    name, stage = "transport-custody", "ingest"
    failures = []
    snaps = sorted(daemon.snapshots.glob("*")) if daemon.snapshots.is_dir() else []
    for path in snaps:
        if path.name.endswith(".partial"):
            failures.append(f"{path.name}: a torn write was left behind")
            continue
        if F.sha256_of(path.read_bytes()) != path.name:
            failures.append(f"{path.name}: does not hash to its own name")

    try:
        pairs = daemon.pairs()
    except F.ChainBroken as exc:
        return GateResult(name, stage, CLOSED, FAIL, len(snaps), str(exc))

    cited = {
        (r["evidence"]["url"], r["evidence"]["sha256"])
        for r in records
        if r.get("evidence")
    }
    for url, digest in sorted(cited):
        if (url, digest) not in pairs:
            failures.append(f"{url} @ {digest[:12]}: cited but never fetched")

    # Every FILE, not merely every cited one. Checking only citations left a
    # gap the live dogfood walked straight into: a planted file named by its own
    # correct digest, cited by nothing, satisfied both checks above and the
    # gate reported pass. "Bytes in the store that never came off a wire" is the
    # thing this gate is named for, and an uncited planted file is exactly that
    # -- it is also precisely what a record refused today would cite tomorrow.
    logged = {digest for (_u, digest) in pairs}
    for path in snaps:
        if path.name.endswith(".partial"):
            continue
        if path.name not in logged:
            failures.append(
                f"{path.name[:12]}: in the snapshot store but in no daemon row "
                "-- authored, not fetched"
            )

    # robots.txt, per host that was fetched at all.
    fetched_hosts = {_host_of(u) for (u, _d) in pairs}
    robots_hosts = {_host_of(u) for (u, _d) in pairs if u.endswith("/robots.txt")}
    for host in sorted(fetched_hosts - robots_hosts):
        failures.append(f"{host}: fetched without its robots.txt being snapshotted")

    return _result(name, stage, CLOSED, failures, len(snaps) + len(cited),
                   empty="no snapshots held and no evidence cited")


def _host_of(url: str) -> str:
    # Imported inside the function so `gates` does not pull in the traversal
    # module (and its parser) just to be imported.
    import traverse as T

    return T.host_of(url)


# --------------------------------------------------------------------------
# Stage: per node
# --------------------------------------------------------------------------


def gate_record_admissible(records) -> GateResult:
    """No unclassified record exists, and every node key is derivable from bytes.

    The second half is the one that costs an attacker something. `observed`
    requires evidence and forbids `inferred_from`; that much the dataclass
    enforces at birth. What it cannot enforce afterwards is that the key still
    matches the quote -- and a record whose key says `org::acme` while its quote
    says something else is a name-collision merge waiting to happen.
    """
    name, stage = "record-admissible", "per node"
    failures = []
    nodes = [r for r in records if r.get("kind") == "node"]
    for r in nodes:
        rid = r.get("id", "?")
        origin, ev, inferred = r.get("origin"), r.get("evidence"), r.get("inferred_from")
        if origin == "observed":
            if not ev:
                failures.append(f"{rid}: observed with no evidence")
                continue
            if inferred:
                failures.append(f"{rid}: observed but carries inferred_from")
            key = r.get("canonical_key", "")
            kind = key.split("::", 1)[0] if "::" in key else ""
            try:
                derived = X.key_for(kind, ev.get("quote", ""))
            except X.ExtractionError as exc:
                failures.append(f"{rid}: key not derivable from its quote -- {exc}")
                continue
            if derived != key:
                failures.append(
                    f"{rid}: quote {ev.get('quote', '')!r} derives {derived}, "
                    f"not {key}"
                )
        elif origin == "simulated":
            if not inferred:
                failures.append(f"{rid}: simulated with no inferred_from")
            if ev:
                failures.append(f"{rid}: simulated but carries evidence")
        else:
            failures.append(f"{rid}: origin is {origin!r}")
    return _result(name, stage, CLOSED, failures, len(nodes),
                   empty="the map holds no node records")


def gate_span_verbatim(daemon, records) -> GateResult:
    """The bytes at the cited offsets say what the record says they say.

    Byte offsets, re-read from the attested snapshot. `bytes.find(quote)` would
    let a producer pick the needle after seeing the haystack; an offset is a
    location it had to commit to before the check ran.
    """
    name, stage = "span-verbatim", "per node"
    failures = []
    observed = [r for r in records if r.get("origin") == "observed" and r.get("evidence")]
    for r in observed:
        ev = r["evidence"]
        try:
            ok = daemon.verifies(
                ev["url"], ev["sha256"], ev["span_start"], ev["span_end"], ev["quote"]
            )
        except F.ChainBroken as exc:
            return GateResult(name, stage, CLOSED, FAIL, len(observed), str(exc))
        if not ok:
            failures.append(
                f"{r.get('id')}: bytes [{ev['span_start']},{ev['span_end']}) of "
                f"{ev['sha256'][:12]} do not say {ev['quote'][:40]!r}"
            )
    return _result(name, stage, CLOSED, failures, len(observed),
                   empty="the map holds no observed records")


def gate_span_entails_claim(daemon, records, verifier=None) -> GateResult:
    """A real, correctly-hashed span that does not actually support the claim.

    Judgement, not arithmetic -- so the judging happens in the loop, where a
    blinded verifier sees the span and the claim and never sees the extractor's
    reasoning. What this gate audits is the LEDGER that judging left behind: an
    observed record still sitting at `unchecked` is one nobody looked at, and a
    map full of those has not been verified however green everything else is.

    An earlier version demanded a fresh verifier callable at gate time and
    reported `inconclusive` without one, which made every command-line run
    INVALID by construction -- there is no way to hand a model to argparse. It
    was also asking a second judge to redo work whose answer was already
    recorded, and then ignoring the recording. Found by running the suite over a
    real crawl rather than by reading it.

    `refuted` is NOT a failure. `Record everything. Expand only what verifies.`
    means a disbelieved claim is expected to be present, carrying its
    refutation, and simply not seeding anything. Failing the run because the
    verifier did its job would inarguably invert the rule.

    A `verifier` may still be supplied, and then it re-judges everything the
    ledger records as entailed. Disagreement is a failure: two blinded judges
    reaching opposite conclusions about one span means at least one of them is
    not judging what it claims to be.
    """
    name, stage = "span-entails-claim", "per node"
    observed = [
        r for r in records
        if r.get("kind") == "node" and r.get("origin") == "observed" and r.get("evidence")
    ]
    failures = [
        f"{r.get('id')}: still unchecked -- the blinded verifier never judged it"
        for r in observed if r.get("verdict") == "unchecked"
    ]
    if verifier is not None:
        for r in observed:
            if r.get("verdict") != "entailed":
                continue
            ev = r["evidence"]
            claim = f"{r.get('canonical_key')} is named here"
            if not verifier(ev["quote"], claim):
                failures.append(
                    f"{r.get('id')}: recorded entailed, but a second blinded judge "
                    f"does not find the span to support {claim!r}"
                )
    return _result(name, stage, CLOSED, failures, len(observed),
                   empty="the map holds no observed node records")


# --------------------------------------------------------------------------
# Stage: per edge
# --------------------------------------------------------------------------


def gate_edge_admissible(records) -> GateResult:
    """Endpoints exist and predicates are in the closed vocabulary."""
    name, stage = "edge-admissible", "per edge"
    failures = []
    node_ids = {r.get("id") for r in records if r.get("kind") == "node"}
    edges = [r for r in records if r.get("kind") == "edge"]
    for r in edges:
        rid, pred = r.get("id"), r.get("predicate")
        if pred != X.SAME_AS and pred not in X.PREDICATES:
            failures.append(f"{rid}: predicate {pred!r} is outside the vocabulary")
        for side in ("src", "dst"):
            if r.get(side) not in node_ids:
                failures.append(f"{rid}: {side} {r.get(side)!r} is not a node in the map")
        if pred in X.PREDICATES and r.get("src") and r.get("dst"):
            want_s, want_o = X.PREDICATES[pred]
            for side, want in (("src", want_s), ("dst", want_o)):
                got = str(r.get(side, "")).split("::", 1)[0]
                if got != want:
                    failures.append(
                        f"{rid}: {pred} wants {side} of kind {want}, got {got!r}"
                    )
    return _result(name, stage, CLOSED, failures, len(edges),
                   empty="the map holds no edges")


def gate_triple_entailed(records) -> GateResult:
    """A relation inferred from mere co-mention on a page.

    Two halves, and neither is sufficient alone.

    The ARITHMETIC half is re-checked here from stored data rather than trusted
    from construction: the endpoint offsets travel on the edge precisely so this
    gate does not have to ask the producer whether it validated them, since a
    gate that reads a flag set by the thing it is auditing is auditing nothing.
    But containment and a width bound only rule out co-mention that is far
    apart. Two names within 600 bytes of each other -- an ordinary team page --
    satisfy the arithmetic completely while stating no relation at all.

    So the JUDGEMENT half has to have happened, and this gate audits that it
    did. An edge still at `unchecked` is a relation nobody judged, and a map
    holding those has not established the one thing it exists to establish.
    Found by probing rather than reading: `span-entails-claim` filters to nodes,
    so before this an unjudged EDGE passed every per-edge gate and the run
    reported VALID. Only `projection-fidelity` would have caught it, and only if
    someone happened to project that particular edge.

    `refuted` is not a failure here, for the same reason it is not one there:
    a disbelieved relation is kept, carries its refutation, and expands nothing.
    """
    name, stage = "triple-entailed", "per edge"
    failures = []
    edges = [r for r in records if r.get("kind") == "edge"]
    for r in edges:
        rid = r.get("id")
        if r.get("verdict") == "unchecked":
            failures.append(
                f"{rid}: still unchecked -- the arithmetic cannot establish that a "
                "relation is stated, only that it could be; nobody judged this one"
            )
        ev, attrs = r.get("evidence"), r.get("attrs") or {}
        if not ev:
            failures.append(f"{rid}: an edge with no evidence")
            continue
        lo, hi = ev["span_start"], ev["span_end"]
        width = hi - lo
        if width > X.MAX_RELATION_SPAN:
            failures.append(
                f"{rid}: relation span is {width} bytes (max "
                f"{X.MAX_RELATION_SPAN}) -- co-mention, not a relation"
            )
        for label, key in (("subject", X.SUBJECT_SPAN), ("object", X.OBJECT_SPAN)):
            raw = attrs.get(key)
            if not raw:
                failures.append(f"{rid}: no recorded {label} span to check")
                continue
            try:
                a, b = (int(x) for x in str(raw).split(":", 1))
            except ValueError:
                failures.append(f"{rid}: {label} span {raw!r} is unparseable")
                continue
            if a < 0 or b <= a:
                # `20:10` satisfies `lo <= a and b <= hi` for any enclosing
                # range, so an inverted span sailed through the containment
                # check that is supposed to be the independent structural
                # recheck. An empty or backwards span points at no bytes.
                failures.append(
                    f"{rid}: {label} span [{a},{b}) is empty or inverted -- it "
                    "locates no bytes, so containment says nothing about it"
                )
                continue
            if not (lo <= a and b <= hi):
                failures.append(
                    f"{rid}: {label} span [{a},{b}) is outside the relation span "
                    f"[{lo},{hi})"
                )
    return _result(name, stage, CLOSED, failures, len(edges),
                   empty="the map holds no edges")


# --------------------------------------------------------------------------
# Stage: whole map
# --------------------------------------------------------------------------


def gate_lattice_exact(records) -> GateResult:
    """No observed grade survives a path through a simulated one.

    `meet_origin` per record is not enough: contamination is transitive, and a
    record derived from a record derived from a guess is a guess. Enforced across
    the graph by walking `inferred_from` to its roots.
    """
    name, stage = "lattice-exact", "whole map"
    failures = []
    by_id = {r.get("id"): r for r in records}
    derived = [r for r in records if r.get("inferred_from")]

    def roots_origin(rid, seen):
        r = by_id.get(rid)
        if r is None:
            return None
        if rid in seen:
            # A cycle in inferred_from is itself a defect; treat as simulated so
            # it cannot launder an observed grade while it is reported.
            return "simulated"
        seen = seen | {rid}
        parents = r.get("inferred_from") or []
        if not parents:
            return r.get("origin")
        got = [roots_origin(p, seen) for p in parents]
        if any(g is None for g in got):
            return None
        return S.meet_origin(*got)

    for r in derived:
        rid = r.get("id")
        want = roots_origin(rid, frozenset())
        if want is None:
            failures.append(f"{rid}: inferred_from names a record not in the map")
            continue
        if r.get("origin") != want:
            failures.append(
                f"{rid}: graded {r.get('origin')} but its ancestry meets to {want}"
            )
    return _result(name, stage, CLOSED, failures, len(derived),
                   empty="no record in the map is derived from another, so no "
                         "path through a simulated grade exists")


def _is_robots(url: str) -> bool:
    """A canonical rules file -- no query, no fragment, exactly that path.

    The same predicate `fetchd` uses to decide what may install a policy, for
    the same reason: `/robots.txt?x` is a different resource, and letting it
    count here would let a page under the crawler's own control excuse itself
    from the inventory.
    """
    parts = urllib.parse.urlsplit(url)
    return parts.path == "/robots.txt" and not parts.query and not parts.fragment


def read_ledger(run_dir) -> set:
    """Pages a worker read, whatever they yielded, from `<run>/read.jsonl`.

    A page that was read and honestly produced no claims is not "used", not
    "dropped-with-reason" and not "unread" -- it fits none of the three fates
    this gate knows, and without a ledger it reads as silent loss. Which is the
    one thing the gate exists to tell it apart from.

    TRUST BOUNDARY, stated rather than assumed: this file is NOT in the MAC'd
    chain, so anything that can write the run directory can add a line to it and
    make a genuinely lost page look accounted for. That is acceptable only
    because crawl agents have no write access to the run directory at all -- the
    same custody split the daemon rests on -- and because this gate is about
    silent loss rather than about tamper, which the chain covers.
    """
    path = Path(run_dir) / "read.jsonl"
    if not path.is_file():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.add(json.loads(line)["url"])
        except (ValueError, KeyError):
            continue
    return out


def gate_inventory_closed(daemon, records, traversal=None, unread=()) -> GateResult:
    """Silent loss. Every fetched page is used, dropped-with-reason, or unread.

    The interesting case is a page that was fetched, cost a request, and then
    appears nowhere -- which reads identically to a page that was never found.
    """
    name, stage = "inventory-closed", "whole map"
    failures = []
    try:
        rows = daemon.verified_rows()
    except F.ChainBroken as exc:
        return GateResult(name, stage, CLOSED, FAIL, 0, str(exc))

    fetched = {
        r["url"] for r in rows
        if r.get("kind") == "fetch" and 200 <= int(r.get("status", 0)) < 300
    }
    used = {r["evidence"]["url"] for r in records if r.get("evidence")}
    dropped = set()
    # One traversal or many. `plan` runs one per seed and writes them as a list,
    # so accepting only a single dict silently ignored every seed after the
    # first -- and the pages it found then read as unaccounted.
    for d in _traversals(traversal):
        if not d.get("closes", False):
            failures.append(
                f"a traversal's own accounting does not close: "
                f"{len(d.get('pages', []))} pages + {len(d.get('dropped', []))} "
                f"dropped != {d.get('seen')} seen"
            )
        dropped |= {x.get("url") for x in d.get("dropped", [])}
        # A sitemap or robots.txt is fetched to be READ, not to be cited. It is
        # accounted for by appearing in the traversal's document ledger.
        dropped |= {doc.get("url") for doc in d.get("docs", [])}

    # A rules file is fetched to be OBEYED, not to be cited, so no record will
    # ever name it and it has no other fate to be given. `transport-custody`
    # already REQUIRES one per fetched origin, so accounting for it here is not
    # a loophole -- it is the same fact read from the other side. Without this a
    # crawl that skipped traversal (`--no-traverse`) failed this gate on the one
    # fetch the architecture insists on making.
    robots = {u for u in fetched if _is_robots(u)}
    unaccounted = (fetched - used - dropped - robots
                   - set(unread) - read_ledger(daemon.dir))
    for url in sorted(unaccounted):
        failures.append(
            f"{url}: fetched, then accounted for nowhere -- not cited by a "
            "record, not dropped by the traversal, not in the read ledger, and "
            "not declared unread"
        )
    return _result(name, stage, CLOSED, failures, len(fetched),
                   empty="the run fetched nothing")


def _traversals(traversal) -> list:
    """Normalise whatever the caller passed into a list of traversal dicts.

    SAME TRUST BOUNDARY AS `read_ledger`, stated for the same reason: neither
    `traversal.json` nor the ledger is in the MAC'd chain, so anything able to
    write the run directory can add a document row and make a genuinely lost
    page look accounted for. That is acceptable only because crawl agents have
    no write access to the run directory -- the custody split the daemon rests
    on -- and because this gate is about SILENT LOSS rather than about tamper,
    which the chain covers and `plan-sealed-and-log-chained` reports.
    """
    if traversal is None:
        return []
    if isinstance(traversal, list):
        return [t if isinstance(t, dict) else t.as_dict() for t in traversal]
    return [traversal if isinstance(traversal, dict) else traversal.as_dict()]


def gate_corroboration_grade(records) -> GateResult:
    """Marks single-sourced claims. Never gates.

    It did not survive attack -- two outlets reprinting one press release
    corroborate each other -- so it annotates and is deliberately not allowed to
    change the verdict. Kept because "how much of this rests on one page" is a
    real question a reader should be able to ask.
    """
    name, stage = "corroboration-grade", "whole map"
    by_key: dict = {}
    for r in records:
        if not r.get("evidence"):
            continue
        by_key.setdefault(r.get("canonical_key"), set()).add(r["evidence"]["url"])
    single = sorted(k for k, urls in by_key.items() if len(urls) == 1)
    return GateResult(
        name, stage, ANNOTATE, ANNOTATED, len(by_key),
        f"{len(single)} of {len(by_key)} claims rest on a single page",
        tuple(single),
    )


# --------------------------------------------------------------------------
# Stage: pre-ship
# --------------------------------------------------------------------------


def gate_projection_fidelity(records, projection=None) -> GateResult:
    """A projection asserting more than the map does.

    `projection` is a list of `{"id": ...}` -- whatever a knowledge-graph page or
    an ontology proposal is about to claim. Each must correspond to a record that
    the map holds AND that verification entailed. Projecting an unchecked record
    is how a map's uncertainty gets laundered into a confident sentence
    downstream.
    """
    name, stage = "projection-fidelity", "pre-ship"
    if projection is None:
        return GateResult(
            name, stage, CLOSED, INCONCLUSIVE, 0,
            "no projection supplied; nothing was checked and that is not a pass",
        )
    by_id = {r.get("id"): r for r in records}
    failures = []
    for item in projection:
        rid = item.get("id") if isinstance(item, dict) else item
        rec = by_id.get(rid)
        if rec is None:
            failures.append(f"{rid}: projected but not in the map")
            continue
        if rec.get("verdict") != "entailed":
            failures.append(
                f"{rid}: projected with verdict {rec.get('verdict')!r} -- only "
                "entailed records may be asserted downstream"
            )
    return _result(name, stage, CLOSED, failures, len(projection),
                   empty="an empty projection asserts nothing")


# --------------------------------------------------------------------------
# The decoys, and the gate that runs them
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DecoyResult:
    """One probe at a gate, and whether the gate answered correctly.

    `polarity` is what makes this two devices rather than one. A `must-reject`
    probe is a planted decoy: a known-false claim the gate has to refuse. A
    `must-accept` probe is the other half of the committed fixture pair, and it
    is not ceremony -- a gate that fails everything catches every decoy and is
    worthless, so without the accepting half the decoys could be satisfied by
    breaking the gate rather than by it working.
    """

    gate: str
    description: str
    polarity: str          # "must-reject" | "must-accept"
    ok: bool


def _decoy_rig(tmp: Path):
    """A throwaway daemon holding one real page, for building known-false claims.

    Synthetic rather than borrowed from the run under test, so decoy-proving does
    not depend on the run having found anything -- and so a decoy can never
    accidentally write into a real store.
    """
    page = b"ACME S.A.S. appointed Maria Restrepo as CTO. " + b"filler. " * 200

    class AllowAll(F.Politeness):
        def __init__(self):
            super().__init__(interval=0.0)

        def allows(self, url):
            return True

    d = F.FetchDaemon(
        root=tmp, run_id="decoy", politeness=AllowAll(),
        transport=lambda u: (200, page, u), key=b"decoy-key",
    )
    d.seal_plan({"seeds": ["decoy"], "max_depth": 0})
    res = d.fetch("https://decoy.test/robots.txt")
    res = d.fetch("https://decoy.test/a")
    return d, res, page


def sha256_of_bytes(payload: bytes) -> str:
    return F.sha256_of(payload)


def run_decoys() -> list:
    """Plant a known-false claim in each deterministic gate; require rejection.

    Every entry is a defect a real run could contain, expressed as the smallest
    input that exhibits it. If a gate accepts one, the gate is not doing what its
    name says and the run is INVALID regardless of what else passed.
    """
    out = []
    with tempfile.TemporaryDirectory() as td:
        d, res, page = _decoy_rig(Path(td))
        ev = d.evidence_for(res, 0, 11)          # "ACME S.A.S."
        assert ev["quote"] == "ACME S.A.S.", ev  # the fixture must be what we think

        def node(**over):
            base = {
                "id": "org::acme-s-a-s", "kind": "node",
                "canonical_key": "org::acme-s-a-s", "depth": 0, "layer": "L2",
                "origin": "observed", "verdict": "entailed", "evidence": dict(ev),
                "inferred_from": [], "attrs": {},
            }
            base.update(over)
            return base

        good_node = node()
        person = node(id="person::maria-restrepo", canonical_key="person::maria-restrepo",
                      evidence=dict(d.evidence_for(res, page.find(b"Maria Restrepo"),
                                                   page.find(b"Maria Restrepo") + 14)))

        def edge(**over):
            rel = d.evidence_for(res, 0, 44)
            base = {
                "id": "edge::employs::x", "kind": "edge", "canonical_key": "edge::employs::x",
                "depth": 0, "layer": "L2", "origin": "observed", "verdict": "entailed",
                "evidence": dict(rel), "inferred_from": [], "predicate": "employs",
                "src": "org::acme-s-a-s", "dst": "person::maria-restrepo",
                "attrs": {X.SUBJECT_SPAN: "0:11", X.OBJECT_SPAN: "22:36"},
            }
            base.update(over)
            return base

        def must_reject(gate, desc, result):
            out.append(DecoyResult(gate, desc, "must-reject", result.status == FAIL))

        def must_accept(gate, desc, result):
            out.append(DecoyResult(gate, desc, "must-accept", result.status == PASS))

        # -- the gates must PASS the honest map, first. A gate that fails
        #    everything catches every decoy and is worthless.
        honest = [good_node, person, edge()]
        for g, r in (
            ("record-admissible", gate_record_admissible(honest)),
            ("span-verbatim", gate_span_verbatim(d, honest)),
            ("edge-admissible", gate_edge_admissible(honest)),
            ("triple-entailed", gate_triple_entailed(honest)),
            ("lattice-exact", gate_lattice_exact(honest)),
            ("transport-custody", gate_transport_custody(d, honest)),
            ("projection-fidelity",
             gate_projection_fidelity(honest, [{"id": "org::acme-s-a-s"}])),
        ):
            must_accept(g, "an honest map", r)

        # -- record-admissible
        must_reject("record-admissible", "a key that its own quote does not derive",
              gate_record_admissible([node(canonical_key="org::globex", id="org::globex")]))
        must_reject("record-admissible", "observed with no evidence",
              gate_record_admissible([node(evidence=None)]))
        must_reject("record-admissible", "observed carrying inferred_from",
              gate_record_admissible([node(inferred_from=["x"])]))

        # -- span-verbatim
        forged = dict(ev)
        forged["quote"] = "ACME S.A.S. is a front company"
        must_reject("span-verbatim", "a quote the attested bytes do not contain",
              gate_span_verbatim(d, [node(evidence=forged)]))
        unattested = dict(ev)
        unattested["sha256"] = "0" * 64
        unattested["snapshot"] = "snapshots/" + "0" * 64
        must_reject("span-verbatim", "a digest that was never fetched",
              gate_span_verbatim(d, [node(evidence=unattested)]))

        # -- edge-admissible
        must_reject("edge-admissible", "a predicate outside the vocabulary",
              gate_edge_admissible([good_node, person, edge(predicate="vibes_with")]))
        must_reject("edge-admissible", "an endpoint that is not in the map",
              gate_edge_admissible([good_node, edge(dst="person::nobody")]))
        must_reject("edge-admissible", "an endpoint of the wrong kind",
              gate_edge_admissible([good_node, person,
                                    edge(src="person::maria-restrepo",
                                         dst="org::acme-s-a-s")]))

        # -- triple-entailed
        wide = d.evidence_for(res, 0, X.MAX_RELATION_SPAN + 50)
        must_reject("triple-entailed", "a relation span wide enough to be co-mention",
              gate_triple_entailed([edge(evidence=dict(wide))]))
        must_reject("triple-entailed", "an endpoint span outside the relation span",
              gate_triple_entailed([edge(attrs={X.SUBJECT_SPAN: "0:11",
                                                X.OBJECT_SPAN: "900:914"})]))
        must_reject("triple-entailed", "an edge with no recorded endpoint spans",
              gate_triple_entailed([edge(attrs={})]))
        must_reject("triple-entailed", "a relation nobody judged",
              gate_triple_entailed([edge(verdict="unchecked")]))

        # -- lattice-exact
        must_reject("lattice-exact", "an observed grade derived from a simulated record",
              gate_lattice_exact([
                  node(id="guess", canonical_key="org::guess", origin="simulated",
                       evidence=None, inferred_from=["seed"]),
                  node(id="seed", canonical_key="org::seed", origin="simulated",
                       evidence=None, inferred_from=[]),
                  node(id="laundered", canonical_key="org::laundered",
                       origin="observed", evidence=dict(ev), inferred_from=["guess"]),
              ]))

        # -- projection-fidelity
        must_reject("projection-fidelity", "projecting a record the map does not hold",
              gate_projection_fidelity(honest, [{"id": "org::invented"}]))
        must_reject("projection-fidelity", "projecting an unchecked record",
              gate_projection_fidelity([node(verdict="unchecked")],
                                       [{"id": "org::acme-s-a-s"}]))

        # -- transport-custody
        planted = d.snapshots / ("f" * 64)
        planted.write_bytes(b"authored, not fetched")
        must_reject("transport-custody", "a snapshot that does not hash to its own name",
              gate_transport_custody(d, honest))
        planted.unlink()
        # The other half of custody, and a different failure: the snapshots on
        # disk are all fine, but a record cites a pair the chained log never
        # recorded. Distinct from span-verbatim's version -- there the bytes
        # disagree with the quote; here there are no bytes at all.
        never = dict(ev)
        never["sha256"] = "b" * 64
        never["snapshot"] = "snapshots/" + "b" * 64
        must_reject("transport-custody", "a record citing a pair never fetched",
              gate_transport_custody(d, [node(evidence=never)]))
        # And the uncited case, which is the one that got through: a file whose
        # name IS its own hash, referenced by no record at all.
        authored = b"planted, never fetched"
        stray = d.snapshots / sha256_of_bytes(authored)
        stray.write_bytes(authored)
        must_reject("transport-custody", "an uncited file planted in the store",
              gate_transport_custody(d, honest))
        stray.unlink()

    return out


#: Gates that `run_decoys` must probe in BOTH directions. Named explicitly so
#: adding a gate without probing it fails a test rather than passing silently.
PROBED_GATES = (
    "transport-custody", "record-admissible", "span-verbatim",
    "edge-admissible", "triple-entailed", "lattice-exact",
    "projection-fidelity",
)


def probe_coverage(decoys) -> list:
    """Gates missing a probe in either direction.

    An aggregate count is not enough, and that was a real hole: with
    `must-accept` counted globally, an always-FAIL `transport-custody` still
    satisfied every one of its own must-reject probes while OTHER gates supplied
    the suite's accepting half. The polarity pair has to hold per gate, or a
    broken gate is indistinguishable from a strict one.
    """
    gaps = []
    for gate in PROBED_GATES:
        polarities = {d.polarity for d in decoys if d.gate == gate}
        for want in ("must-reject", "must-accept"):
            if want not in polarities:
                gaps.append(f"{gate}: no {want} probe")
    return gaps


def gate_suite_proven(decoys) -> GateResult:
    """The gate that keeps the others honest.

    A validation suite that always passes is worse than none, because it
    manufactures confidence. Every decoy above is a defect a gate claims to
    catch; if one gets through, the claim is false and nothing else this suite
    reported can be relied on.
    """
    name, stage = "gate-suite-proven", "pre-ship"
    missed = [
        f"{d.gate} [{d.polarity}]: {d.description}" for d in decoys if not d.ok
    ] + probe_coverage(decoys)
    return _result(name, stage, CLOSED, missed, len(decoys),
                   empty="no probes were run, which proves nothing")


# --------------------------------------------------------------------------
# The suite
# --------------------------------------------------------------------------


@dataclass
class SuiteResult:
    results: list = field(default_factory=list)
    decoys: list = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """INVALID if any fail-closed gate failed OR could not run.

        `inconclusive` counting as INVALID is the whole point of a fail-closed
        policy: a gate that did not run has not licensed anything, and reading
        its silence as consent is how the two judgement gates would quietly
        become optional.
        """
        for r in self.results:
            if r.policy == CLOSED and r.status in (FAIL, INCONCLUSIVE):
                return INVALID
        return VALID

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "gates": [r.as_dict() for r in self.results],
            "decoys": {
                "total": len(self.decoys),
                "missed": [
                    {"gate": d.gate, "polarity": d.polarity,
                     "description": d.description}
                    for d in self.decoys if not d.ok
                ],
            },
            "counted_total": sum(r.counted for r in self.results),
        }

    def report(self) -> str:
        w = max((len(r.gate) for r in self.results), default=10)
        lines = []
        for r in self.results:
            mark = {PASS: "pass", FAIL: "FAIL", INCONCLUSIVE: "INCONCLUSIVE",
                    ANNOTATED: "note"}[r.status]
            lines.append(f"  {mark:<12} {r.gate:<{w}}  n={r.counted:<5} {r.detail}")
            for f in r.failures[:5]:
                lines.append(f"               - {f}")
            if len(r.failures) > 5:
                lines.append(f"               ... and {len(r.failures) - 5} more")
        missed = [d for d in self.decoys if not d.ok]
        lines.append(f"\n  probes: {len(self.decoys) - len(missed)}/{len(self.decoys)} answered correctly")
        lines.append(f"\n  verdict: {self.verdict}")
        return "\n".join(lines)


def run_suite(
    daemon,
    conn,
    traversal=None,
    projection=None,
    verifier: Optional[Callable] = None,
    unread=(),
) -> SuiteResult:
    """Every gate, in stage order, over what the run left on disk."""
    records = S.select(conn)
    # The verdict-auditing gates get the CANONICAL records only. A conflicting
    # re-sighting is retained deliberately -- the run paid for it and nothing is
    # deleted -- but it carries no verdict of its own, so auditing it as though
    # it did made any conflict fail the run for a claim that WAS judged. The
    # structural gates still see everything, because a conflict payload is a
    # record that exists and must be admissible and verbatim like any other.
    canonical = S.select(conn, include_conflicts=False)
    decoys = run_decoys()
    return SuiteResult(
        results=[
            gate_plan_sealed_and_log_chained(daemon),
            gate_transport_custody(daemon, records),
            gate_record_admissible(records),
            gate_span_verbatim(daemon, records),
            gate_span_entails_claim(daemon, canonical, verifier),
            gate_edge_admissible(records),
            gate_triple_entailed(canonical),
            gate_lattice_exact(records),
            gate_inventory_closed(daemon, records, traversal, unread),
            gate_corroboration_grade(records),
            gate_projection_fidelity(records, projection),
            gate_suite_proven(decoys),
        ],
        decoys=decoys,
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="gates.py",
        description="Run the sourcer gate suite over a completed run.",
    )
    ap.add_argument("--run", required=True, help="the run directory (holds plan.json)")
    ap.add_argument("--db", required=True, help="the store's sqlite file")
    ap.add_argument("--traversal",
                    help="a traversal JSON file; defaults to <run>/traversal.json")
    ap.add_argument("--projection", help="a JSON list of records about to be asserted")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    run = Path(args.run)
    daemon = F.FetchDaemon(root=run.parent, run_id=run.name)
    conn = S.connect(Path(args.db))
    # Found in the run directory when not named. A gate that needs a flag an
    # operator must remember is a gate that fails for reasons unrelated to the
    # thing it measures.
    trav_path = Path(args.traversal) if args.traversal else (run / "traversal.json")
    traversal = json.loads(trav_path.read_text()) if trav_path.is_file() else None
    projection = json.loads(Path(args.projection).read_text()) if args.projection else None

    suite = run_suite(daemon, conn, traversal=traversal, projection=projection)
    if args.json:
        print(json.dumps(suite.as_dict(), indent=2, sort_keys=True))
    else:
        print(f"sourcer gate suite -- run {run.name}")
        print(suite.report())
    # 2, not 1: an unhandled traceback also exits 1, and "the gates said no" must
    # not be indistinguishable from "the gate runner crashed".
    return 0 if suite.verdict == VALID else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
