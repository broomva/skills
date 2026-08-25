"""Typed `(subject, predicate, object)` extraction over a closed vocabulary.

This is the module that turns a page set into a graph. It does not read pages --
a model does that, and a model's reading is not a thing a test can hold. What is
here is the admission layer that reading must pass, and it is built so that the
interesting failures are arithmetic rather than judgement.

Three devices do most of the work, and each replaces a check somebody would
otherwise have to remember.

**An entity's name is the bytes, not a field.** A `Mention` declares a kind and
a byte span; the name is whatever is at those offsets, and the canonical key is
recomputed from it. There is no argument in which an extractor states what an
entity is called, so there is nothing to state falsely. The spec's requirement
that "the canonical key must literally occur in fetched bytes" stops being a
check and becomes the only way a key can be produced.

**A relation is evidenced by a bounded span containing both mentions.** The
`triple-entailed` gate exists against relations inferred from mere co-mention --
a company in the header and a person in the footer are not thereby related. That
is hard to judge and easy to measure: the relation's span must contain both
endpoint spans *and* be no longer than `MAX_RELATION_SPAN`. Co-mention across a
page cannot satisfy both. Quoting the whole document, as the spec puts it, is
the same vacuity wearing a hat, and a length bound is what takes the hat off.

**The vocabulary is closed, and typed.** A predicate outside it is refused, and
so is one whose endpoints are the wrong kinds -- `employs` from a person to an
org is not a slightly-wrong edge, it is a sign the extractor did not understand
the sentence.

Everything admitted is `observed` and carries evidence built through
`FetchDaemon.evidence_for`, so the daemon's own refusals (non-2xx, unattested
pair, whitespace span, snapshot-derived-from-digest) apply here without this
module restating them.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------
# The closed vocabulary
# --------------------------------------------------------------------------

#: Entity kinds. Closed on purpose: an open kind set means the identity rule
#: ("same kind + same key => same entity") has no fixed domain, and two crawls
#: can then disagree about whether a thing is one entity or two.
ENTITY_KINDS = ("org", "person", "profile", "location", "product")

#: predicate -> (subject kind, object kind). The types are the point: an edge
#: whose endpoints are the wrong kinds is evidence the sentence was misread, not
#: a near-miss worth keeping.
PREDICATES: dict = {
    # org -> org
    "subsidiary_of": ("org", "org"),
    "parent_of": ("org", "org"),
    "acquired": ("org", "org"),
    "invested_in": ("org", "org"),
    "partner_of": ("org", "org"),
    "supplies": ("org", "org"),
    "competitor_of": ("org", "org"),
    # person <-> org
    "employs": ("org", "person"),
    "leads": ("person", "org"),
    "founded": ("person", "org"),
    "board_member_of": ("person", "org"),
    "advises": ("person", "org"),
    # presence
    "has_profile": ("person", "profile"),
    "org_profile": ("org", "profile"),
    "located_in": ("org", "location"),
    "offers": ("org", "product"),
}

#: Identity, per D3: exact-key merges are automatic and everything softer is an
#: EDGE rather than a merge. Endpoints must share a kind, and the kind is free,
#: so it cannot be expressed in PREDICATES' fixed-pair table.
SAME_AS = "possibly_same_as"

#: Predicates that hold in both directions. A gate can use this to refuse a
#: graph asserting `partner_of(a,b)` and denying `partner_of(b,a)`; extraction
#: only needs to know that emitting one is not a claim about ordering.
SYMMETRIC = frozenset({"partner_of", "competitor_of", SAME_AS})

#: Predicate -> the predicate that says the same thing backwards. Exported for
#: the whole-map gates: an inverse pair is where a crawl contradicts itself, and
#: the contradiction is invisible unless the relationship is declared somewhere.
#: Deliberately partial. `leads` is NOT the inverse of `employs` -- a CEO is
#: both employed by and leads the same company -- and inventing the pairing
#: would make a correct graph look self-contradictory.
INVERSES: dict = {
    "subsidiary_of": "parent_of",
    "parent_of": "subsidiary_of",
}

#: Attributes an edge may carry. Closed, because an unevidenced attribute is a
#: claim wearing a data hat -- these ride on the EDGE's evidence span and are
#: therefore judged by the same entailment check as the relation itself.
ATTR_KEYS = frozenset({"title", "since", "until", "note"})

#: Longest span that may evidence a relation. Roughly a long sentence. The bound
#: is the whole `triple-entailed` defence: a subject and an object that are
#: genuinely related are said to be related somewhere close together, and one
#: that needs 4KB of context to connect them is co-mention.
MAX_RELATION_SPAN = 600

#: Bounds on an entity name read out of the page. The lower bound refuses a
#: one-character "entity"; the upper refuses a paragraph quoted as a name, which
#: is how a whole-document span sneaks past a check that only looks at offsets.
MIN_NAME_CHARS = 2
MAX_NAME_CHARS = 120

#: Longest an attribute value may be, for the same reason.
MAX_ATTR_CHARS = 200

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


class ExtractionError(Exception):
    """A refusal. Never a downgrade -- there is no `simulated` fallback here.

    An extraction that cannot be admitted as observed is not quietly recorded as
    an inference: nothing was inferred, something was claimed and did not check
    out. Producing a simulated record from a failed observation would launder a
    bad reading into a derivation with no premises.
    """


# --------------------------------------------------------------------------
# Names and keys
# --------------------------------------------------------------------------


def normalize_name(raw: str) -> str:
    """Collapse a name read out of bytes to its comparable form.

    NFKC first, because a page that writes `ＡＣＭＥ` in fullwidth characters
    and one that writes `ACME` are naming the same company, and two records is
    the wrong answer. Whitespace is collapsed rather than stripped-at-the-ends
    only: a name split across a line break in the HTML is one name.
    """
    text = unicodedata.normalize("NFKC", raw)
    # Any unicode space -- including NBSP, which is what a real page puts
    # between a company name and its legal suffix.
    return " ".join(text.split())


def key_for(kind: str, name: str) -> str:
    """The canonical key of an entity. Pure, total, and the only key source.

    Deterministic so two workers reading two pages that name the same company
    produce the same key without coordinating, which is what makes the store's
    exact-key merge (D3) safe to do automatically.
    """
    if kind not in ENTITY_KINDS:
        raise ExtractionError(f"{kind!r} is not one of {ENTITY_KINDS}")
    slug = _SLUG_STRIP.sub("-", normalize_name(name).casefold()).strip("-")
    if not slug:
        raise ExtractionError(
            f"{name!r} normalises to an empty key -- punctuation is not a name"
        )
    return f"{kind}::{slug}"


def _check_name(kind: str, name: str) -> None:
    n = normalize_name(name)
    if "�" in n:
        # Spans are BYTE offsets and `evidence_for` decodes with
        # errors="replace", so a span that starts or ends inside a multi-byte
        # character yields U+FFFD. On a page in Spanish -- which the worked
        # example is -- that is an off-by-one landing mid-accent, and the name
        # it produces is not the name. Refuse rather than store the mojibake:
        # the key derived from it would be wrong, permanently, and would merge
        # with nothing.
        raise ExtractionError(
            f"{name!r} contains a replacement character -- the span cuts a "
            "multi-byte character, so these bytes are not the whole name"
        )
    if len(n) < MIN_NAME_CHARS:
        raise ExtractionError(
            f"{name!r} is {len(n)} characters -- too short to identify a {kind}"
        )
    if len(n) > MAX_NAME_CHARS:
        raise ExtractionError(
            f"a {kind} name of {len(n)} characters is a passage, not a name "
            f"(max {MAX_NAME_CHARS}) -- a span this wide is how a whole-document "
            "quote gets past a check that only inspects offsets"
        )


# --------------------------------------------------------------------------
# What an extractor may say
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Mention:
    """An entity, located rather than named.

    There is deliberately no `name` field. The name is the bytes at
    [start, end), so an extractor cannot name something the page does not say --
    not because it is checked, but because there is no argument in which to say
    it.
    """

    kind: str
    span_start: int
    span_end: int

    def __post_init__(self) -> None:
        if self.kind not in ENTITY_KINDS:
            raise ExtractionError(f"{self.kind!r} is not one of {ENTITY_KINDS}")
        if self.span_start < 0 or self.span_end <= self.span_start:
            raise ExtractionError(
                f"span [{self.span_start},{self.span_end}) is empty or inverted"
            )


@dataclass(frozen=True)
class Claim:
    """One typed relation, with the span that is alleged to state it."""

    subject: Mention
    predicate: str
    object: Mention
    span_start: int
    span_end: int
    attrs: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.predicate != SAME_AS and self.predicate not in PREDICATES:
            raise ExtractionError(
                f"{self.predicate!r} is outside the closed vocabulary. "
                f"Allowed: {sorted(list(PREDICATES) + [SAME_AS])}"
            )
        if self.span_start < 0 or self.span_end <= self.span_start:
            raise ExtractionError(
                f"relation span [{self.span_start},{self.span_end}) is empty "
                "or inverted"
            )
        # Type the endpoints here, at construction, so a mistyped claim cannot
        # exist long enough to be counted in a denominator.
        if self.predicate == SAME_AS:
            if self.subject.kind != self.object.kind:
                raise ExtractionError(
                    f"{SAME_AS} needs both ends to be the same kind, got "
                    f"{self.subject.kind} and {self.object.kind} -- two things of "
                    "different kinds are not a candidate merge"
                )
        else:
            want_s, want_o = PREDICATES[self.predicate]
            if self.subject.kind != want_s or self.object.kind != want_o:
                raise ExtractionError(
                    f"{self.predicate} is ({want_s} -> {want_o}), got "
                    f"({self.subject.kind} -> {self.object.kind})"
                )

        # The co-mention defence, stated as arithmetic.
        for label, m in (("subject", self.subject), ("object", self.object)):
            if not (self.span_start <= m.span_start and m.span_end <= self.span_end):
                raise ExtractionError(
                    f"the {label} mention [{m.span_start},{m.span_end}) is not "
                    f"inside the relation span [{self.span_start},{self.span_end}) "
                    "-- a relation must be evidenced by text that contains both "
                    "things it relates"
                )
        width = self.span_end - self.span_start
        if width > MAX_RELATION_SPAN:
            raise ExtractionError(
                f"relation span is {width} bytes (max {MAX_RELATION_SPAN}). Two "
                "entities this far apart are co-mentioned, not related; widening "
                "the span until it contains both is precisely the move this bound "
                "exists to refuse"
            )

        bad = set(self.attrs) - ATTR_KEYS
        if bad:
            raise ExtractionError(
                f"attributes {sorted(bad)} are outside {sorted(ATTR_KEYS)}"
            )
        for k, v in self.attrs.items():
            if not isinstance(v, str):
                raise ExtractionError(
                    f"attribute {k!r} is {type(v).__name__}; edge attributes are "
                    "strings, because they ride on the edge's evidence span and "
                    "must be readable in it"
                )
            if len(v) > MAX_ATTR_CHARS:
                raise ExtractionError(
                    f"attribute {k!r} is {len(v)} characters (max {MAX_ATTR_CHARS})"
                )


@dataclass(frozen=True)
class Entity:
    """A resolved mention: the name is now known, because the bytes were read."""

    kind: str
    name: str
    key: str
    evidence: dict


def edge_id(src: str, predicate: str, dst: str) -> str:
    """A deterministic id for an edge.

    Hashed rather than concatenated because a key may contain any of the
    separators, and `a::b|p|c` colliding with `a|b::p|c` is a merge of two
    unrelated edges that no later check would notice.
    """
    h = hashlib.sha256(f"{src}\x00{predicate}\x00{dst}".encode()).hexdigest()[:16]
    return f"edge::{predicate}::{h}"


# --------------------------------------------------------------------------
# Admission
# --------------------------------------------------------------------------


def resolve(daemon, res, mention: Mention) -> Entity:
    """Read a mention's bytes and derive the entity from them.

    Evidence is built by `daemon.evidence_for`, which re-reads the receipt out
    of the chained log rather than trusting `res` -- so this function inherits
    every refusal the daemon owns instead of restating a weaker version of it.
    """
    ev = daemon.evidence_for(res, mention.span_start, mention.span_end)
    name = normalize_name(ev["quote"])
    _check_name(mention.kind, name)
    return Entity(
        kind=mention.kind, name=name, key=key_for(mention.kind, name), evidence=ev
    )


def admit(
    daemon,
    res,
    claim: Claim,
    depth: int,
    layer: str = "L2",
) -> list:
    """Turn one claim into [subject node, object node, edge]. Or refuse.

    Every returned record is `observed` and carries its own evidence: the nodes
    cite the spans their names were read from, the edge cites the span alleged
    to state the relation. That is the "different upstreams" rule the design
    leans on -- the daemon attests that these bytes came from this URL, and
    these records attest that this claim came from these bytes. Two signatures
    over two different propositions.

    Nothing here writes to the store. `put_record` still asks the daemon for
    itself; a caller that skipped this function entirely would be refused there
    rather than here, which is the property that makes this module a convenience
    rather than the security boundary.
    """
    import store as S

    subject = resolve(daemon, res, claim.subject)
    obj = resolve(daemon, res, claim.object)

    if subject.key == obj.key:
        raise ExtractionError(
            f"{subject.key} {claim.predicate} itself -- a self-edge. Two spans "
            "resolving to one entity means the sentence names it twice, not that "
            "it relates to itself"
        )

    rel_ev = daemon.evidence_for(res, claim.span_start, claim.span_end)

    nodes = [
        S.Record(
            id=e.key,
            kind="node",
            canonical_key=e.key,
            depth=depth,
            layer=layer,
            origin="observed",
            evidence=S.Evidence(**e.evidence),
            attrs={"name": e.name},
        )
        for e in (subject, obj)
    ]
    eid = edge_id(subject.key, claim.predicate, obj.key)
    edge = S.Record(
        id=eid,
        kind="edge",
        canonical_key=eid,
        depth=depth,
        layer=layer,
        origin="observed",
        evidence=S.Evidence(**rel_ev),
        predicate=claim.predicate,
        src=subject.key,
        dst=obj.key,
        attrs=dict(claim.attrs),
    )
    return nodes + [edge]


# --------------------------------------------------------------------------
# The extractor's wire format
# --------------------------------------------------------------------------


def claims_from_json(blob: str) -> list:
    """Parse an extractor agent's output into Claims, refusing anything else.

    The agent is a model, so its output is untrusted text and this is where that
    stops being true. Unknown keys are refused rather than ignored: an extractor
    emitting `"name": "ACME"` alongside a span has misunderstood the contract in
    a way that silently dropping the field would hide, and the field it invented
    is exactly the one this design removed on purpose.
    """
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"extractor output is not JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ExtractionError(
            f"expected a list of claims, got {type(data).__name__}"
        )

    out = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ExtractionError(f"claim {i} is {type(item).__name__}, not an object")
        allowed = {"subject", "predicate", "object", "span_start", "span_end", "attrs"}
        extra = set(item) - allowed
        if extra:
            raise ExtractionError(
                f"claim {i} carries unknown keys {sorted(extra)}. Allowed: "
                f"{sorted(allowed)} -- an entity is located by span, never named"
            )
        missing = allowed - {"attrs"} - set(item)
        if missing:
            raise ExtractionError(f"claim {i} is missing {sorted(missing)}")
        out.append(
            Claim(
                subject=_mention(item["subject"], f"claim {i} subject"),
                predicate=item["predicate"],
                object=_mention(item["object"], f"claim {i} object"),
                span_start=_int(item["span_start"], f"claim {i} span_start"),
                span_end=_int(item["span_end"], f"claim {i} span_end"),
                attrs=item.get("attrs") or {},
            )
        )
    return out


def _mention(raw, where: str) -> Mention:
    if not isinstance(raw, dict):
        raise ExtractionError(f"{where} is {type(raw).__name__}, not an object")
    allowed = {"kind", "span_start", "span_end"}
    extra = set(raw) - allowed
    if extra:
        raise ExtractionError(f"{where} carries unknown keys {sorted(extra)}")
    missing = allowed - set(raw)
    if missing:
        raise ExtractionError(f"{where} is missing {sorted(missing)}")
    return Mention(
        kind=raw["kind"],
        span_start=_int(raw["span_start"], f"{where}.span_start"),
        span_end=_int(raw["span_end"], f"{where}.span_end"),
    )


def _int(v, where: str) -> int:
    # `isinstance(True, int)` is True in Python, and a bool arriving as an offset
    # would silently mean 0 or 1 rather than being refused.
    if isinstance(v, bool) or not isinstance(v, int):
        raise ExtractionError(f"{where} must be an integer, got {v!r}")
    return v


def vocabulary_doc() -> str:
    """The closed vocabulary as text, for the extractor agent's brief.

    Generated from the tables rather than written beside them, so a predicate
    added to `PREDICATES` cannot be missing from the prompt that is supposed to
    be the complete list -- the recorded failure mode being a doc that describes
    software which no longer exists.
    """
    lines = ["Entity kinds: " + ", ".join(ENTITY_KINDS), "", "Predicates:"]
    for p, (s, o) in sorted(PREDICATES.items()):
        sym = "  (symmetric)" if p in SYMMETRIC else ""
        lines.append(f"  {p}: {s} -> {o}{sym}")
    lines.append(f"  {SAME_AS}: X -> X, any kind, both ends the same  (symmetric)")
    lines += [
        "",
        f"Edge attributes: {', '.join(sorted(ATTR_KEYS))} (strings, "
        f"<= {MAX_ATTR_CHARS} chars)",
        "",
        "Every entity is located by a byte span, never named. The name is the "
        "bytes at those offsets.",
        f"A relation's span must contain both endpoint spans and be at most "
        f"{MAX_RELATION_SPAN} bytes.",
    ]
    return "\n".join(lines)


__all__ = [
    "ExtractionError",
    "ENTITY_KINDS",
    "PREDICATES",
    "SAME_AS",
    "SYMMETRIC",
    "INVERSES",
    "ATTR_KEYS",
    "MAX_RELATION_SPAN",
    "MIN_NAME_CHARS",
    "MAX_NAME_CHARS",
    "MAX_ATTR_CHARS",
    "Mention",
    "Claim",
    "Entity",
    "normalize_name",
    "key_for",
    "edge_id",
    "resolve",
    "admit",
    "claims_from_json",
    "vocabulary_doc",
]
