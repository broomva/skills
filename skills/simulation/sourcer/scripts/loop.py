"""The depth loop: fetch, extract, verify, and expand only what survived.

The one structural claim of this module is where verification sits. It is a
stage *inside* the per-node pipeline, not a pass at the end. In a batch model a
fabricated node at hop two has seeded fifty descendants before anyone checks it,
and the refutation arrives with a subtree hanging off it. Here the refutation
prunes before the subtree exists -- the same checks, a very different blast
radius.

    claim  ->  fetch  ->  extract  ->  verify  ->  expand
                                          |
                                    refuted stops here

Recursion is expressed as a depth loop rather than as recursion, because the
workflow substrate permits one level of nesting and a node therefore cannot
spawn a sub-workflow for what it discovers. Breadth-first falls out of that, and
is the better shape anyway: everything at hop *d* is known before anything at
*d+1* is fetched, so a budget spent is a budget spent on the shallowest
unexplored thing.

**How a crawl moves from one entity to the next, and why it is narrow.** A
verified `profile` node's name is a URL read out of the page, at offsets the
extractor committed to before any check ran. That URL -- and only that URL -- is
what enters the frontier for the next hop. There is no argument in which the
loop is handed a URL to go and fetch; it can only follow a link the bytes
literally contained. The alternative, letting an extractor return a list of
"discovered" URLs, puts the crawl's whole trajectory in the model's gift, and a
single hallucinated address at hop two spends the rest of the budget on a site
that does not exist.

The model is outside this module. `extractor` and `verifier` are injected
callables, so the loop is deterministic and testable while the judgement stays
where judgement belongs.
"""

from __future__ import annotations

import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract as X  # noqa: E402
import fetchd as F  # noqa: E402
import store as S  # noqa: E402

#: Edges whose object is a page the crawl may follow. Deliberately just these
#: two: they are the predicates whose object IS a location, so following one is
#: reading the thing the page pointed at rather than guessing where to go next.
EXPANSION_PREDICATES = frozenset({"has_profile", "org_profile"})


class LoopError(Exception):
    """A refusal from the loop itself, as opposed to from one item."""


@dataclass(frozen=True)
class Plan:
    """The denominator, fixed before the first fetch.

    Sealed into the run through `FetchDaemon.seal_plan`, so a run cannot later
    grow the number it is measured against -- which is how a progress bar comes
    to never go backwards.
    """

    seeds: tuple
    max_depth: int
    fetch_budget: int

    def __post_init__(self) -> None:
        if not self.seeds:
            raise LoopError("a plan with no seeds crawls nothing")
        if self.max_depth < 0:
            raise LoopError(f"max_depth must be >= 0, got {self.max_depth}")
        if self.fetch_budget < 1:
            raise LoopError(f"fetch_budget must be >= 1, got {self.fetch_budget}")

    def as_dict(self) -> dict:
        return {
            "seeds": list(self.seeds),
            "max_depth": self.max_depth,
            "fetch_budget": self.fetch_budget,
        }


@dataclass
class LoopStats:
    """What the run did, in the terms a reader needs to trust it.

    `refuted` and `expanded` are reported separately from `admitted` on purpose.
    A run that admitted a hundred records and expanded none of them is a run
    that found a hundred things it did not believe, and that is a completely
    different outcome from finding nothing -- which the record count alone
    cannot tell you.
    """

    fetched: int = 0
    items_done: int = 0
    claims_seen: int = 0
    admitted: int = 0
    rejected: int = 0
    entailed: int = 0
    refuted: int = 0
    inconclusive: int = 0
    expanded: int = 0
    budget_stops: int = 0
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "items_done": self.items_done,
            "claims_seen": self.claims_seen,
            "admitted": self.admitted,
            "rejected": self.rejected,
            "entailed": self.entailed,
            "refuted": self.refuted,
            "inconclusive": self.inconclusive,
            "expanded": self.expanded,
            "budget_stops": self.budget_stops,
            "notes": list(self.notes),
        }


def profile_url(record: dict) -> Optional[str]:
    """The http(s) URL a `profile` node names, if it names one.

    The name came out of the page, so this is the whole mechanism by which a
    crawl can move: a link the bytes contained, at committed offsets. Anything
    that does not parse as an absolute http(s) URL is not somewhere to go.
    """
    key = record.get("canonical_key", "")
    if not key.startswith("profile::"):
        return None
    name = (record.get("attrs") or {}).get("name", "")
    parts = urllib.parse.urlsplit(name)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return name


def proposition(record, names: dict) -> str:
    """The claim a verifier is asked to judge. The WHOLE claim.

    This function exists because of a defect that made every other defence in
    the pipeline moot. The verifier used to be handed the bare predicate for an
    edge -- `"employs"` -- so on a page reading `ACME employs Alice. Globex
    employs Bob.` a claim relating ACME to BOB fits inside 600 bytes, contains
    both mentions, and asks the judge only "does this text say `employs`". It
    does. The crossed edge was then recorded `entailed` and passed every gate:
    a complete path from genuine attested bytes to a false verified relation.

    A verifier cannot refuse a claim it was never shown. So it gets the named
    endpoints, in order, and the name comes from the bytes -- which is exactly
    what makes it safe to put in the question.
    """
    if record.kind == "edge":
        src = names.get(record.src, record.src)
        dst = names.get(record.dst, record.dst)
        return f"{src!r} {record.predicate} {dst!r}"
    kind = record.canonical_key.split("::", 1)[0]
    name = (record.attrs or {}).get("name", record.canonical_key)
    return f"this text names the {kind} {name!r}"


def expand(conn, records, depth: int, parent_id: Optional[str] = None) -> int:
    """Push the next hop's URLs. Only from records that verified.

    The `expandable()` check is the load-bearing line in this module. It reads
    `origin == observed AND verdict == entailed` -- so an unchecked record, a
    refuted one, and an inferred one all stay exactly where they are. They are
    kept, reported, and queryable; they simply do not get to spend the fetch
    budget on descendants.
    """
    by_id = {r.get("id"): r for r in records}
    pushed = 0
    for r in records:
        if r.get("kind") != "edge" or r.get("predicate") not in EXPANSION_PREDICATES:
            continue
        # The EDGE must have verified, and so must the profile node it points
        # at. Either one failing means the link between them is not established,
        # and following it anyway would be crawling on the strength of a claim
        # the run itself declined to believe.
        if not _verified(r):
            continue
        dst = by_id.get(r.get("dst"))
        if dst is None or not _verified(dst):
            continue
        url = profile_url(dst)
        if url is None:
            continue
        if S.push_frontier(conn, url, depth, parent_id or r.get("src")):
            pushed += 1
    return pushed


def _verified(record: dict) -> bool:
    return record.get("origin") == "observed" and record.get("verdict") == "entailed"


def process_item(
    daemon,
    conn,
    url: str,
    depth: int,
    extractor: Callable,
    verifier: Callable,
    stats: LoopStats,
) -> None:
    """One frontier item, all five stages, in order.

    Anything that goes wrong with a single item is recorded and returns; it does
    not abort the run. One 404 in a page set is not a reason to lose the other
    forty-nine, and a run that dies on the first bad page reports less than one
    that finishes and says what it could not read.
    """
    try:
        res = daemon.fetch(url)
    except F.FetchError as exc:
        stats.notes.append(f"{url}: {type(exc).__name__}: {exc}")
        return
    except Exception as exc:
        # NOT just FetchError. A transport raising `urllib.error.URLError`, a
        # socket timeout, or any defect below the daemon is not a domain
        # refusal -- and letting it escape meant `run`'s `finally` marked the
        # lease DONE on the way out, so the item was permanently dropped from a
        # crawl that then reported itself complete. One bad page must cost one
        # page.
        stats.notes.append(f"{url}: transport raised {type(exc).__name__}: {exc}")
        return
    stats.fetched += 1

    ok, why = daemon.usable_as_evidence(res)
    if not ok:
        stats.notes.append(f"{url}: {why}")
        return
    payload = daemon.open_attested(res.url, res.sha256)

    try:
        claims = extractor(payload, res.url)
    except Exception as exc:
        stats.notes.append(f"{url}: extractor raised {type(exc).__name__}: {exc}")
        return

    fresh = []
    for claim in claims:
        stats.claims_seen += 1
        try:
            records = X.admit(daemon, res, claim, depth=depth)
        except (X.ExtractionError, F.FetchError) as exc:
            # A claim that cannot be admitted is NOT recorded as a weaker claim.
            # Downgrading it to `simulated` would launder a bad reading into a
            # derivation with no premises, so it is counted and dropped.
            stats.rejected += 1
            stats.notes.append(f"{url}: claim rejected -- {exc}")
            continue
        for rec in records:
            try:
                S.put_record(conn, rec, admitter=daemon)
            except S.StoreError as exc:
                stats.rejected += 1
                stats.notes.append(f"{url}: {rec.id} refused by the store -- {exc}")
                continue
            stats.admitted += 1
            fresh.append(rec)

    # -- verify, per record, BEFORE anything expands ------------------------
    names = {r.id: (r.attrs or {}).get("name", r.canonical_key)
             for r in fresh if r.kind == "node"}
    for rec in fresh:
        quote = rec.evidence.quote if rec.evidence else ""
        try:
            entailed = bool(verifier(quote, proposition(rec, names)))
        except Exception as exc:
            stats.notes.append(f"{rec.id}: verifier raised {type(exc).__name__}: {exc}")
            continue
        if entailed:
            S.set_verdict(conn, rec.id, "entailed")
            stats.entailed += 1
        elif rec.kind == "edge":
            S.set_verdict(
                conn, rec.id, "refuted",
                refutation="the blinded verifier did not find the span to support "
                           "this claim",
            )
            stats.refuted += 1
        else:
            # See `cmd_land`: a judge looked, and what it settled was the
            # relation, not the naming. `inconclusive` says exactly that.
            S.set_verdict(conn, rec.id, "inconclusive")
            stats.inconclusive += 1

    # -- expand, from the store, reading the verdicts just written ----------
    ids = {r.id for r in fresh}
    written = [r for r in S.select(conn) if r.get("id") in ids]
    stats.expanded += expand(conn, written, depth + 1, parent_id=url)


def run(
    daemon,
    conn,
    plan: Plan,
    extractor: Callable,
    verifier: Callable,
    worker: str = "w1",
) -> LoopStats:
    """The loop. Breadth-first, bounded by depth and by the fetch budget.

    Seeds are pushed at depth 0 and the frontier does the rest: `claim` hands out
    the shallowest outstanding item under a lease, so this is the same function
    whether one worker runs it or six do.
    """
    stats = LoopStats()
    for seed in plan.seeds:
        S.push_frontier(conn, seed, 0)

    while True:
        if stats.fetched >= plan.fetch_budget:
            stats.budget_stops += 1
            stats.notes.append(
                f"stopped at the fetch budget of {plan.fetch_budget}; the frontier "
                f"still holds {S.frontier_stats(conn)['remaining']} item(s)"
            )
            break
        row = S.claim(conn, worker, max_depth=plan.max_depth)
        if row is None:
            break
        try:
            process_item(
                daemon, conn, row["key"], row["depth"], extractor, verifier, stats
            )
        finally:
            # Under `finally` so a crash inside one item does not leave its lease
            # outstanding, which would make the run report work in flight that
            # nobody is doing until the lease expires.
            S.finish(conn, row["key"], row["claim_token"])
            stats.items_done += 1
    return stats


__all__ = [
    "LoopError",
    "Plan",
    "LoopStats",
    "EXPANSION_PREDICATES",
    "profile_url",
    "proposition",
    "expand",
    "process_item",
    "run",
]
