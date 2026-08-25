"""The command line the workflow drives. One entry point, seven verbs.

The split this file exists to enforce: **agents read, code decides.** A crawl
agent is given a path to bytes already on disk and returns spans; it never
fetches, never writes to the store, and never says whether its own claim is
good. Everything that decides -- what may be admitted, what verified, what
expands -- happens here, in code, from the artifacts on disk.

    plan     seal the denominator and push the seeds
    take     claim one frontier item, fetch it, hand back a path to read
    land     admit the agent's claims, apply the verdicts, expand what survived
    status   where the run is, in the terms the gates will ask about
    resolve  propose possibly_same_as edges -- proposes, never merges
    emit     the node and edge tables Parallax ingests
    project  the map as Layer-3 entity pages (dry-run by default)

`take` and `land` are two commands rather than one because the agent's work sits
between them. That is also why `land` takes a claim token: the item was leased
by `take`, and only the holder of that lease may finish it. Without the token a
second worker could land claims against an item it never took.

Exit codes are typed. 0 is success, 2 is a refusal this program is making on
purpose, and 1 is left alone -- an unhandled traceback exits 1, and "the run
refused your claims" must not be indistinguishable from "the runner crashed".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import emit as E  # noqa: E402
import extract as X  # noqa: E402
import fetchd as F  # noqa: E402
import identity as I  # noqa: E402
import loop as L  # noqa: E402
import project as PJ  # noqa: E402
import store as S  # noqa: E402
import traverse as T  # noqa: E402

OK = 0
REFUSED = 2


class Refusal(Exception):
    """Something this program declines to do, as opposed to something broken."""


def _open(args):
    run = Path(args.run)
    daemon = F.FetchDaemon(root=run.parent, run_id=run.name)
    return daemon, S.connect(Path(args.db))


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------


def cmd_plan(args) -> int:
    """Seal the plan, traverse each seed's site, and push what it found.

    The plan is sealed BEFORE the first fetch and never rewritten, so the run
    cannot later grow the number it is measured against. Traversal runs here
    rather than inside the loop because it is the one step that turns a seed
    into a page set, and doing it per-item would re-read every sitemap once per
    page.
    """
    run = Path(args.run)
    run.parent.mkdir(parents=True, exist_ok=True)
    daemon = F.FetchDaemon(root=run.parent, run_id=run.name)
    plan = L.Plan(
        seeds=tuple(args.seed), max_depth=args.max_depth, fetch_budget=args.budget
    )
    try:
        daemon.seal_plan(plan.as_dict())
    except F.FetchError as exc:
        raise Refusal(str(exc)) from exc

    conn = S.connect(Path(args.db))
    out = {"plan": plan.as_dict(), "traversals": [], "queued": 0}
    for seed in plan.seeds:
        if args.no_traverse:
            out["queued"] += int(S.push_frontier(conn, seed, 0))
            continue
        # The traversal's own fetches (robots.txt, sitemaps) come out of the same
        # sealed budget as the crawl's. Bounding its document count by what is
        # left is what stops `--budget 1` spending two requests before the loop
        # has claimed anything.
        spent = sum(1 for r in daemon.verified_rows() if r.get("kind") == "fetch")
        # `left < 2`, not `< 1`. A traversal costs at least TWO requests -- the
        # host's robots.txt plus one sitemap -- and `max_docs` bounds only the
        # sitemap documents, so a remaining allowance of exactly one was still
        # an overspend by one.
        left = args.budget - spent
        if left < 2:
            # `max(1, ...)` handed out one more document after the shared budget
            # was already gone, so two seeds under `--budget 1` fetched twice.
            # A spent budget is spent.
            out["traversals"].append({
                "seed": seed, "pages": [], "dropped": [], "docs": [],
                "seen": 0, "closes": True, "robots_url": None,
                "note": f"fetch budget of {args.budget} cannot cover a traversal "
                        f"of this seed ({left} request(s) left, 2 needed)",
            })
            # The seed is still QUEUED. Skipping the traversal means the crawl
            # does not learn the site's other pages; it must not mean the crawl
            # forgets the page it was actually pointed at, or a small budget
            # would produce a run with an empty frontier and nothing to read.
            out["queued"] += int(S.push_frontier(conn, seed, 0))
            continue
        # Both bounds, not just the document count: `budget` caps how many pages
        # reach the frontier and must not promise more than the run can fetch.
        trav = T.traverse(daemon, seed, budget=min(args.budget, left),
                          max_docs=left - 1)
        out["traversals"].append(trav.as_dict())
        out["queued"] += T.push_pages(conn, trav.pages, depth=0, parent_id=seed)
        # The seed itself is a page worth reading even when it is absent from
        # the sitemap, which is common: a sitemap lists what a publisher wants
        # indexed, not everything that exists.
        out["queued"] += int(S.push_frontier(conn, seed, 0))
    # Persist the traversal record INTO THE RUN. `inventory-closed` needs it to
    # tell "fetched and accounted for" from "fetched and lost", and requiring an
    # operator to remember `--traversal` meant every workflow run failed that
    # gate for a reason that had nothing to do with the crawl. A run directory
    # should describe itself.
    (run / "traversal.json").write_text(
        json.dumps(out["traversals"], indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return OK


# --------------------------------------------------------------------------
# take
# --------------------------------------------------------------------------


def cmd_take(args) -> int:
    """Claim one item, fetch it, and hand back a path the agent may read.

    The path points into the run's snapshot store, resolved from the digest.
    Handing over a path rather than the bytes themselves is deliberate: the
    agent's spans are byte offsets into that file, and passing the content
    through a shell would let an encoding change shift every offset it returns.
    """
    daemon, conn = _open(args)
    plan_path = daemon.dir / "plan.json"
    if not plan_path.exists():
        raise Refusal(f"{plan_path}: no sealed plan -- run `plan` first")
    plan = json.loads(plan_path.read_text())

    # EVERY fetch row, not just the 2xx ones. A 404 and a redirect refusal each
    # cost a request to the host; counting only successes let a run that spent
    # its whole budget on dead pages keep asking for more. The budget bounds
    # what the crawl DOES, not what it got away with.
    n_fetched = sum(1 for r in daemon.verified_rows() if r.get("kind") == "fetch")
    if n_fetched >= plan["fetch_budget"]:
        print(json.dumps({
            "item": None,
            "reason": f"fetch budget of {plan['fetch_budget']} is spent",
            "frontier": S.frontier_stats(conn),
        }, indent=2, sort_keys=True))
        return OK

    row = S.claim(conn, args.worker, max_depth=plan["max_depth"])
    if row is None:
        print(json.dumps({
            "item": None, "reason": "the frontier holds nothing claimable",
            "frontier": S.frontier_stats(conn),
        }, indent=2, sort_keys=True))
        return OK

    try:
        res = daemon.fetch(row["key"])
        ok, why = daemon.usable_as_evidence(res)
        if not ok:
            raise F.FetchError(why)
    except F.FetchError as exc:
        # The item is done either way: it was tried, and a page that cannot be
        # read is not work still outstanding. Leaving it claimable would make
        # the run retry a 404 until the lease budget ran out.
        S.finish(conn, row["key"], row["claim_token"])
        print(json.dumps({
            "item": None, "url": row["key"], "reason": f"{type(exc).__name__}: {exc}",
        }, indent=2, sort_keys=True))
        return OK

    print(json.dumps({
        "item": {
            "url": res.url,
            "digest": res.sha256,
            "depth": row["depth"],
            "claim_token": row["claim_token"],
            "path": str(daemon.snapshots / res.sha256),
            "n_bytes": res.n_bytes,
        },
        "vocabulary": X.vocabulary_doc(),
    }, indent=2, sort_keys=True))
    return OK


# --------------------------------------------------------------------------
# land
# --------------------------------------------------------------------------


def cmd_land(args) -> int:
    """Admit the claims, apply the verdicts, expand what survived, finish.

    `--verdicts` maps a CLAIM INDEX -- `"0"`, `"1"` -- to true or false, and
    comes from a verifier that never saw the extractor's reasoning.

    Keyed by claim rather than by record id, and that is not a convenience. A
    record id is derived during `admit`, from the bytes; the verifier runs
    before admission and cannot know one. Asking it for ids would mean either
    handing it the extractor's output to name things (which is the coupling the
    blinding exists to prevent) or running admission first and verification
    second, which is the batch model this design rejects.

    One claim yields three records, and a verdict lands on them asymmetrically
    because they are different propositions. `true` entails all three: if the
    span states the relation, it named the endpoints correctly to do so. `false`
    refutes only the EDGE -- the entities may well be named correctly on a page
    that does not state the relation between them, and refuting them on that
    basis would discard a true reading because a different one failed. The nodes
    stay `unchecked`, which keeps them out of the next hop either way.

    A claim with no verdict stays `unchecked` throughout -- not a synonym for
    `inconclusive`, and emphatically not permission to expand. Omitting the file
    therefore admits everything and expands nothing, which is the correct
    behaviour for a run whose verifier did not report.
    """
    daemon, conn = _open(args)

    # AUTHORISE FIRST. This used to be the last step -- `S.finish` at the very
    # end raised on a bad token, by which point the records were admitted, the
    # verdicts written and the frontier expanded. A caller with a wrong or
    # expired token got every mutation it asked for and an error message.
    try:
        lease = S.held_lease(conn, args.url, args.token)
    except S.StoreError as exc:
        raise Refusal(str(exc)) from exc
    # And the depth comes from the LEASE, never from an argument. As a free
    # parameter it let a worker holding a valid lease on a depth-2 item land it
    # as depth 0 and push its descendants in at depth 1, walking under the
    # sealed max_depth for as long as it liked.
    depth = lease["depth"]

    res = daemon.receipt_for(args.url, args.digest)
    if res is None:
        # Release on the way out. The lease was validated a moment ago, so
        # holding it through a refusal would leave the run reporting work in
        # flight that nobody is doing until it expires.
        _release(conn, args.url, args.token)
        raise Refusal(
            f"{args.url} @ {args.digest[:12]}: no chained log row pairs these. "
            "`land` may only be called for a page `take` actually fetched."
        )

    try:
        claims = X.claims_from_json(Path(args.claims).read_text())
    except X.ExtractionError as exc:
        # The lease is released even on a refusal: the item was taken, tried and
        # is not still outstanding. Otherwise a malformed extractor output would
        # leave the run reporting work in flight that nobody is doing.
        _release(conn, args.url, args.token)
        raise Refusal(f"extractor output refused: {exc}") from exc

    try:
        verdicts = _verdicts(Path(args.verdicts)) if args.verdicts else {}
    except Refusal:
        _release(conn, args.url, args.token)
        raise
    stats = L.LoopStats()
    landed = []
    by_claim: dict = {}
    for idx, claim in enumerate(claims):
        stats.claims_seen += 1
        try:
            records = X.admit(daemon, res, claim, depth=depth)
        except (X.ExtractionError, F.FetchError) as exc:
            stats.rejected += 1
            stats.notes.append(f"claim {idx} rejected -- {exc}")
            continue
        kept = []
        for rec in records:
            try:
                S.put_record(conn, rec, admitter=daemon)
            except S.StoreError as exc:
                stats.rejected += 1
                stats.notes.append(f"{rec.id} refused by the store -- {exc}")
                continue
            stats.admitted += 1
            kept.append(rec)
            landed.append(rec)
        by_claim[idx] = kept

    for idx, records in by_claim.items():
        if str(idx) not in verdicts:
            continue
        if verdicts[str(idx)]:
            for rec in records:
                S.set_verdict(conn, rec.id, "entailed")
                stats.entailed += 1
        else:
            for rec in (r for r in records if r.kind == "edge"):
                S.set_verdict(
                    conn, rec.id, "refuted",
                    refutation="the blinded verifier did not find the span to "
                               "support this relation",
                )
                stats.refuted += 1

    # RE-CHECK the lease before expanding. Authorising once at the top is not
    # enough on its own: the lease can lapse while the agent's claims are being
    # admitted, and another worker can reclaim the item. Admitting records under
    # a stale lease is survivable -- records are content-addressed and
    # `put_record` treats a repeat as a re-sighting -- but EXPANSION is not, so
    # the frontier is only touched under a lease that is still live.
    #
    # This narrows the window rather than removing it; a check and a write are
    # two statements, and closing that properly means one transaction spanning
    # the whole of `land`, which the store does not offer across a process
    # boundary. What it does guarantee is that a worker whose lease died before
    # it got here cannot push work for someone else's item.
    try:
        S.held_lease(conn, args.url, args.token)
    except S.StoreError as exc:
        raise Refusal(
            f"the lease lapsed during land, so the frontier was not expanded: {exc}"
        ) from exc

    ids = {r.id for r in landed}
    written = [r for r in S.select(conn) if r.get("id") in ids]
    stats.expanded = L.expand(conn, written, depth + 1, parent_id=args.url)

    try:
        S.finish(conn, args.url, args.token)
    except S.StoreError as exc:
        # A typed refusal, not a traceback. Dropping this wrapper turned exit 2
        # into exit 1 and lost the reason -- the one thing the exit codes exist
        # to keep apart.
        raise Refusal(str(exc)) from exc

    print(json.dumps({
        "depth": depth,
        "landed": sorted(ids),
        "stats": stats.as_dict(),
        "frontier": S.frontier_stats(conn),
    }, indent=2, sort_keys=True))
    return OK


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


def _verdicts(path: Path) -> dict:
    """Parse a verdicts file, requiring JSON booleans and nothing else.

    Truthiness is not a verdict. `{"0": "false"}` is a string, and a string is
    truthy, so it marked all three of a claim's records `entailed` and let the
    crawl expand on the strength of a judge that said no. A verifier that
    reports in any shape but `true`/`false` has not reported, and guessing what
    it meant is exactly the coercion this pipeline refuses everywhere else.
    """
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise Refusal(f"{path}: not JSON -- {exc}") from exc
    if not isinstance(raw, dict):
        raise Refusal(f"{path}: expected an object of claim index -> bool")
    out = {}
    for k, v in raw.items():
        if not isinstance(v, bool):
            raise Refusal(
                f"{path}: verdict for claim {k!r} is {type(v).__name__} "
                f"({v!r}); a verdict must be JSON true or false"
            )
        if not (isinstance(k, str) and k.isdigit()):
            raise Refusal(f"{path}: {k!r} is not a claim index")
        out[k] = v
    return out


def _release(conn, key: str, token: str) -> None:
    """Release a lease on the way out of a refusal, without masking it.

    `finish` raises when the lease has already lapsed, and letting that escape
    from an error path replaced a typed refusal with an unhandled traceback --
    turning exit 2 into exit 1 and losing the reason.
    """
    try:
        S.finish(conn, key, token)
    except S.StoreError:
        pass


def cmd_resolve(args) -> int:
    """Propose identity candidates. Merges nothing, ever.

    Exit 0 with an empty list is the normal answer for a map with no
    near-duplicates, and is reported as such rather than as silence.
    """
    _daemon, conn = _open(args)
    try:
        report = I.resolve(conn, depth=args.depth, threshold=args.threshold,
                           max_pairs=args.max_pairs)
    except I.IdentityError as exc:
        raise Refusal(str(exc)) from exc
    print(json.dumps(report, indent=2, sort_keys=True))
    return OK


def cmd_emit(args) -> int:
    """The Parallax handoff: node and edge tables, provenance intact."""
    daemon, conn = _open(args)
    try:
        out = E.emit(S.select(conn), prefix=args.prefix, daemon=daemon)
    except E.EmitError as exc:
        raise Refusal(str(exc)) from exc
    print(json.dumps(out, indent=2, sort_keys=True))
    return OK


def cmd_project(args) -> int:
    """The knowledge-graph handoff. DRY-RUN unless --write is given.

    Writing into a permanent, shared, hand-curated graph is not a default.
    """
    _daemon, conn = _open(args)
    records = S.select(conn)
    pages = PJ.build(records, run_id=Path(args.run).name)
    if not pages:
        print(json.dumps({
            "pages": 0, "dry_run": not args.write,
            "reason": "no record in this map is an observed, entailed node of a "
                      "kind the graph has a type for",
        }, indent=2, sort_keys=True))
        return OK
    out = PJ.write(pages, Path(args.entities), dry_run=not args.write)
    out["projected"] = [p.as_dict() for p in pages]
    print(json.dumps(out, indent=2, sort_keys=True))
    return OK


def cmd_status(args) -> int:
    daemon, conn = _open(args)
    plan_path = daemon.dir / "plan.json"
    try:
        chain_ok, chain_why, rows = F.verify_run(daemon.dir, daemon.key)
    except Exception as exc:  # a missing/unreadable run is a fact, not a crash
        chain_ok, chain_why, rows = False, f"{type(exc).__name__}: {exc}", []
    print(json.dumps({
        "run": daemon.run_id,
        "plan": json.loads(plan_path.read_text()) if plan_path.exists() else None,
        "chain": {"ok": chain_ok, "why": chain_why, "rows": len(rows or ())},
        "inventory": S.inventory(conn),
        "expandable": len(S.expandable_ids(conn)),
    }, indent=2, sort_keys=True))
    return OK


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sourcer", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--run", required=True, help="the run directory")
        p.add_argument("--db", required=True, help="the store's sqlite file")
        return p

    p = common(sub.add_parser("plan", help="seal the plan and queue the seeds"))
    p.add_argument("--seed", action="append", required=True)
    p.add_argument("--max-depth", type=int, default=2)
    p.add_argument("--budget", type=int, default=50)
    p.add_argument("--no-traverse", action="store_true",
                   help="queue the seeds without walking their sitemaps")
    p.set_defaults(fn=cmd_plan)

    p = common(sub.add_parser("take", help="claim, fetch, and hand back a path"))
    p.add_argument("--worker", default="w1")
    p.set_defaults(fn=cmd_take)

    p = common(sub.add_parser("land", help="admit claims, apply verdicts, expand"))
    p.add_argument("--url", required=True)
    p.add_argument("--digest", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--claims", required=True, help="JSON list of claims")
    p.add_argument("--verdicts",
                   help='JSON object of claim index -> bool, e.g. {"0": true}')
    p.set_defaults(fn=cmd_land)

    p = common(sub.add_parser("status", help="where the run is"))
    p.set_defaults(fn=cmd_status)

    p = common(sub.add_parser("resolve", help="propose possibly_same_as edges"))
    p.add_argument("--threshold", type=float, default=I.DEFAULT_THRESHOLD)
    p.add_argument("--max-pairs", type=int, default=I.DEFAULT_MAX_PAIRS)
    p.add_argument("--depth", type=int, default=0)
    p.set_defaults(fn=cmd_resolve)

    p = common(sub.add_parser("emit", help="the tables Parallax ingests"))
    p.add_argument("--prefix", default="sourcer")
    p.set_defaults(fn=cmd_emit)

    p = common(sub.add_parser("project", help="the map as Layer-3 entity pages"))
    p.add_argument("--entities", required=True, help="the entities directory")
    p.add_argument("--write", action="store_true",
                   help="actually write; without it this is a dry run")
    p.set_defaults(fn=cmd_project)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except Refusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return REFUSED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
