"""Identity: exact keys merge, everything softer becomes an edge.

D3, stated as one rule with two halves. Two records with the same canonical key
are one entity and the store merges them without asking. Two records that merely
*look* alike are two entities and a `possibly_same_as` edge between them — never
a merge.

The asymmetry is deliberate and it is the whole design. **A wrong merge is much
harder to notice than a missing one.** A missing merge shows up as two nodes a
reader can see and join; a wrong merge silently attributes one company's
leadership, subsidiaries and profiles to another, and nothing downstream can
recover the two halves because the evidence for both now hangs off one id. So
this module has no authority to merge anything. It proposes, and the proposal is
a record like any other -- typed, evidenced where it can be, and refusable.

**Every edge it emits is `simulated`.** That is not a hedge, it is the truth: no
page says "these two records are the same entity". The claim is derived from
comparing two things the crawl already held, which is exactly what `simulated`
means on this lattice, and `expandable()` therefore refuses to let one spend the
fetch budget on descendants. A similarity score is not evidence, and grading it
`observed` because the two records underneath it were observed is precisely the
laundering `meet_origin` exists to prevent.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract as X  # noqa: E402

#: Legal-form suffixes and corporate noise that carry no identity. `ACME S.A.S.`
#: and `ACME S.A.` are the same company in every sense a reader cares about, and
#: the suffix is exactly the part that varies between sources.
#:
#: Deliberately conservative. Every entry here makes two names LOOK more alike,
#: so a wrong entry manufactures candidate pairs; the list holds only forms whose
#: removal cannot change which company is meant.
LEGAL_FORMS = frozenset({
    "sas", "sa", "sl", "srl", "spa", "ltda", "ltd", "limited", "llc", "inc",
    "incorporated", "corp", "corporation", "co", "gmbh", "ag", "bv", "nv",
    "plc", "pty", "oy", "ab", "as", "aps", "kk", "sarl", "sasu", "eirl",
})

#: Tokens that appear in so many names they cannot discriminate between them,
#: plus the connective particles Spanish and English company names are full of.
#: Two companies sharing only "group" are not candidates for being one company,
#: and `Nacional de Café` is `Café Nacional` with a particle in the middle.
#:
#: Connectives are safe to drop because they carry no identity at all. Anything
#: that DOES carry identity must stay: every entry here makes two names look
#: more alike, so a wrong entry manufactures candidate pairs.
STOPWORDS = frozenset({
    "the", "group", "holdings", "holding", "company", "and",
    "de", "del", "la", "las", "el", "los", "y", "of", "for", "en",
})

#: How alike two names must be before a pair is worth a human's attention.
#: Jaccard over token sets, which is order-insensitive -- `Nacional de Café` and
#: `Café Nacional` are the same tokens in a different order, and a reader would
#: call those a candidate pair without hesitating.
DEFAULT_THRESHOLD = 0.6

#: A pair whose comparable form is IDENTICAL after normalisation but whose keys
#: differ. Scored 1.0 and always proposed, whatever the threshold, because the
#: only thing separating them is punctuation or a legal form.
EXACT_AFTER_NORMALISATION = 1.0

#: How many pairs one pass may propose. Similarity is quadratic in the node
#: count, and an unbounded proposer on a large map buries the real candidates in
#: a list nobody reads -- which is the same as proposing none, but expensive.
DEFAULT_MAX_PAIRS = 200

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class IdentityError(Exception):
    """A refusal. Never a silent merge."""


def _join_initials(tokens: list) -> list:
    """Rejoin runs of single letters into one token.

    Without this the legal-form list never fires on the form it most needs to:
    `S.A.S.` tokenises to `s`, `a`, `s`, none of which is in `LEGAL_FORMS`, so
    the suffix survives and `ACME S.A.S.` looks materially different from
    `ACME Ltda`. Found by running the comparison rather than by reading it.

    The same rule handles initialisms — `I B M` becomes `ibm` — which is the
    other place a name gets split into letters that mean nothing apart.
    """
    out, run = [], []
    for t in tokens:
        if len(t) == 1:
            run.append(t)
            continue
        if run:
            out.append("".join(run))
            run = []
        out.append(t)
    if run:
        out.append("".join(run))
    return out


def comparable(name: str) -> tuple:
    """The token set two names are compared on.

    NFKD and an accent strip, because `Café` and `Cafe` are one word written by
    two systems, and a crawl that treats them as two companies has failed at the
    first hurdle in every non-English market -- which is the market this was
    built for.

    Legal forms and stopwords come out. What remains is the part of a name that
    actually identifies something.
    """
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    tokens = _join_initials([t for t in _NON_ALNUM.split(text.casefold()) if t])
    kept = tuple(t for t in tokens if t not in LEGAL_FORMS and t not in STOPWORDS)
    # A name that is ENTIRELY legal forms and stopwords keeps its tokens rather
    # than becoming empty. `The Company Ltd` is a poor name, but reducing it to
    # nothing would make it match every other poor name at a similarity of 1.0.
    return kept or tuple(tokens)


def similarity(a: str, b: str) -> float:
    """Jaccard over comparable token sets. 0.0 when either side has nothing.

    Deliberately not an edit distance. Edit distance rewards names that are
    typographically close, and the failure mode that matters here is the
    opposite one: `Banco Agrario` and `Banco Agrícola` are two banks four
    characters apart, while `Nacional de Café` and `Café Nacional` are one
    company in a different order. Token overlap gets both right; character
    distance gets both wrong.
    """
    ta, tb = set(comparable(a)), set(comparable(b))
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return EXACT_AFTER_NORMALISATION
    return len(ta & tb) / len(ta | tb)


@dataclass(frozen=True)
class Candidate:
    """One proposed identity, with the score and the reason it was proposed."""

    left: str
    right: str
    kind: str
    score: float
    reason: str

    def as_dict(self) -> dict:
        return {
            "left": self.left, "right": self.right, "kind": self.kind,
            "score": round(self.score, 4), "reason": self.reason,
        }


def candidates(
    records,
    threshold: float = DEFAULT_THRESHOLD,
    max_pairs: int = DEFAULT_MAX_PAIRS,
) -> list:
    """Pairs of DISTINCT node records that might be one entity.

    Only within a kind: an org and a person who happen to share a name are not a
    candidate merge, they are a person and the company named after them, and
    proposing otherwise would be worse than proposing nothing.

    `profile` is excluded entirely. A profile's identity is its URL, which is
    exact by construction -- two profile records with different keys are two
    different pages, and no amount of textual similarity makes them one.
    """
    if not 0.0 < threshold <= 1.0:
        raise IdentityError(f"threshold must be in (0, 1], got {threshold}")

    by_kind: dict = {}
    for r in records:
        if r.get("kind") != "node":
            continue
        key = r.get("canonical_key", "")
        kind = key.split("::", 1)[0]
        if kind in X.EXACT_KINDS:
            continue
        name = (r.get("attrs") or {}).get("name")
        if not name:
            continue
        by_kind.setdefault(kind, []).append((r.get("id"), name))

    out = []
    truncated = 0
    for kind, items in sorted(by_kind.items()):
        items.sort()
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                lid, lname = items[i]
                rid, rname = items[j]
                if lid == rid:
                    continue
                score = similarity(lname, rname)
                if score < threshold:
                    continue
                if len(out) >= max_pairs:
                    truncated += 1
                    continue
                reason = (
                    "identical after normalising legal forms and accents"
                    if score >= EXACT_AFTER_NORMALISATION
                    else f"{score:.2f} token overlap"
                )
                # Ordered, so the same pair proposed from either direction is one
                # candidate rather than two. `possibly_same_as` is symmetric, and
                # emitting both directions would double-count in every report.
                lo, hi = sorted((lid, rid))
                out.append(Candidate(lo, hi, kind, score, reason))
    if truncated:
        # Named, not silently dropped. A proposer that quietly stops at a cap
        # reports the same empty tail as a map with no more candidates.
        raise IdentityError(
            f"{len(out) + truncated} candidate pairs exceed the cap of {max_pairs}; "
            "raise --max-pairs or narrow the map, but do not read this as "
            f"{max_pairs} being all there is"
        )
    return sorted(out, key=lambda c: (-c.score, c.left, c.right))


def propose(conn, candidate: Candidate, depth: int, layer: str = "L2"):
    """Turn one candidate into a `possibly_same_as` edge record. SIMULATED.

    Not a merge, and not observed. No page anywhere says these two records are
    the same entity -- the claim is derived by comparing two things the crawl
    already holds, which is what `simulated` means. `expandable()` therefore
    refuses to let it seed the next hop, so a wrong guess costs one edge rather
    than a subtree.

    `inferred_from` names both endpoints, so `lattice-exact` can walk the
    ancestry and confirm the grade rather than taking this function's word.
    """
    import store as S

    eid = X.edge_id(candidate.left, X.SAME_AS, candidate.right)
    return S.Record(
        id=eid,
        kind="edge",
        canonical_key=eid,
        depth=depth,
        layer=layer,
        origin="simulated",
        inferred_from=(candidate.left, candidate.right),
        predicate=X.SAME_AS,
        src=candidate.left,
        dst=candidate.right,
        attrs={
            "score": f"{candidate.score:.4f}",
            "reason": candidate.reason,
            "kind": candidate.kind,
        },
    )


def resolve(conn, depth: int = 0, threshold: float = DEFAULT_THRESHOLD,
            max_pairs: int = DEFAULT_MAX_PAIRS) -> dict:
    """Propose every candidate in the map. Returns a report, merges nothing.

    Idempotent: a candidate already proposed is re-sighted rather than
    duplicated, because the edge id is a pure function of its endpoints.
    """
    import store as S

    records = S.select(conn)
    found = candidates(records, threshold=threshold, max_pairs=max_pairs)
    inserted = 0
    for c in found:
        # No admitter: this record is `simulated`, and `put_record` requires a
        # daemon only for `observed`. That is the custody rule doing exactly what
        # it should -- an inference needs no bytes because it cites none.
        if S.put_record(conn, propose(conn, c, depth)) == "inserted":
            inserted += 1
    return {
        "candidates": [c.as_dict() for c in found],
        "proposed": len(found),
        "newly_inserted": inserted,
        "threshold": threshold,
        "merged": 0,
        "note": "possibly_same_as is an EDGE, never a merge: a wrong merge is "
                "much harder to notice than a missing one",
    }


__all__ = [
    "IdentityError",
    "LEGAL_FORMS",
    "STOPWORDS",
    "DEFAULT_THRESHOLD",
    "DEFAULT_MAX_PAIRS",
    "EXACT_AFTER_NORMALISATION",
    "Candidate",
    "comparable",
    "similarity",
    "candidates",
    "propose",
    "resolve",
]
