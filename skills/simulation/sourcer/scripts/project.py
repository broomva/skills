"""Projection: a verified map becomes Layer-3 entity pages.

The other half of D6's handoff. `emit.py` hands Parallax a table it can run;
this hands the knowledge graph pages a human and an agent can read.

Two rules make this safe, and they are the same two rules the rest of the skill
runs on.

**A projection may not assert more than the map does.** Only `entailed` records
project, and every page carries the URL and digest its claim was read from. That
is `projection-fidelity`, fail-closed, and this module builds its input rather
than being trusted to have honoured it -- `emitted_ids()` returns exactly what
was written, so the gate checks the artifact rather than the intention.

**A projection is regenerable, so it is never edited by hand.** Correct the map
and re-project. A page edited in place is a claim with no evidence behind it,
which is the state this whole architecture exists to make impossible; the
`generated` frontmatter marker says so on every page.

The schema is not this module's to invent. `bookkeeping lint` enforces
`core_claim` at 140 characters (an ERROR, not a warning) and tags drawn from
`_tags.md`'s controlled vocabulary, so both are enforced here at write time --
because a page that fails the linter is a page that never lands, and finding
that out at commit is finding it out too late to fix cheaply.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
import json
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract as X  # noqa: E402

#: `bookkeeping lint` fails a page whose core_claim exceeds this. An ERROR, not
#: a warning, so a page over it does not land at all.
MAX_CORE_CLAIM = 140

#: Tags this projection may use. Every one is a CANONICAL entry in
#: `research/entities/_tags.md` -- not merely a word appearing in one of its
#: descriptions, which is how `provenance` was picked at first and caught by
#: the test that checks this. A tag outside the vocabulary is a lint warning,
#: and inventing one per crawled company would make the vocabulary meaningless
#: within a week. Type-redundant tags (`org`, `person`, `concept`...) are
#: forbidden by the vocabulary itself -- `type:` already encodes that.
PROJECTION_TAGS = ("knowledge-graph", "verification", "identity")

#: sourcer entity kind -> knowledge-graph `type:`. `profile` and `product` have
#: no home in the graph's type set and are carried as attributes of the entity
#: they belong to rather than promoted to pages of their own.
KIND_TO_TYPE = {"org": "org", "person": "person", "location": "concept"}

_SLUG = re.compile(r"[^a-z0-9]+")


class ProjectionError(Exception):
    """A refusal. Never a page asserting more than the map holds."""


def yaml_scalar(text) -> str:
    """A YAML-safe scalar for adversary-controlled text.

    Entity names come out of crawled bytes, so a hostile page can name itself
    `X"\nstatus: verified\ninjected: "yes` and — with naive `f'"{name}"'`
    quoting — write arbitrary keys into the frontmatter of a permanent
    knowledge-graph page. Demonstrated, not hypothetical: a review produced a
    page whose parsed frontmatter carried an `injected` key.

    JSON encoding is the fix and needs no dependency: YAML is a superset of JSON
    for scalars, so a `json.dumps` string is always a valid, fully-escaped
    double-quoted YAML scalar.
    """
    return json.dumps("" if text is None else str(text), ensure_ascii=False)


def slug_of(key: str) -> str:
    """The filename an entity key projects to, without its kind prefix."""
    body = key.split("::", 1)[1] if "::" in key else key
    s = _SLUG.sub("-", body.casefold()).strip("-")
    if not s:
        raise ProjectionError(f"{key!r} has no projectable slug")
    return s


def core_claim_for(record: dict, edges: list) -> str:
    """One sentence, under the linter's hard cap, saying what the map holds.

    Truncated at a word boundary with an ellipsis rather than mid-token: a claim
    cut to `...the company acquir` reads as a typo, and the cap is an ERROR so
    there is no version of this that gets to be sloppy and still land.
    """
    name = (record.get("attrs") or {}).get("name", record.get("canonical_key", ""))
    rels = [f"{e.get('predicate')} {_short(e.get('dst'))}" for e in edges[:3]]
    claim = (
        f"{name} — {'; '.join(rels)}." if rels
        else f"{name} was found and verified, with no relations yet established."
    )
    if len(claim) <= MAX_CORE_CLAIM:
        return claim
    cut = claim[: MAX_CORE_CLAIM - 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut + "…"


def _short(key) -> str:
    return str(key).split("::", 1)[-1].replace("-", " ") if key else "?"


@dataclass(frozen=True)
class Page:
    """One entity page, ready to write."""

    key: str
    path: str
    body: str

    def as_dict(self) -> dict:
        return {"key": self.key, "path": self.path, "bytes": len(self.body)}


def projectable(records) -> list:
    """Records this module is allowed to turn into pages.

    `entailed` only, `observed` only, and only kinds the graph has a type for.
    A simulated record is real output and belongs in the Parallax table; it does
    not belong in a permanent Layer-3 page, because a page is what a later
    reader cites and an inference cited as a page loses its grade on the way.
    """
    return [
        r for r in records
        if r.get("kind") == "node"
        and r.get("origin") == "observed"
        and r.get("verdict") == "entailed"
        and r.get("canonical_key", "").split("::", 1)[0] in KIND_TO_TYPE
    ]


def page_for(record: dict, records: list, run_id: str, today: Optional[str] = None) -> Page:
    """Build one page. Every claim on it points at bytes."""
    key = record["canonical_key"]
    kind = key.split("::", 1)[0]
    name = (record.get("attrs") or {}).get("name", key)
    ev = record.get("evidence") or {}
    stamp = today or date.today().isoformat()

    # OBSERVED edges only. A `possibly_same_as` proposal is simulated and
    # entailed, and without the origin filter it rendered straight into the
    # core_claim, the related links and the Relations list of a permanent page
    # -- carrying no evidence, on a page whose whole contract is that every
    # claim points at bytes. Exactly what this module's own docstring says it
    # prevents, prevented by nothing.
    out_edges = [
        e for e in records
        if e.get("kind") == "edge" and e.get("src") == record.get("id")
        and e.get("verdict") == "entailed" and e.get("origin") == "observed"
    ]
    # `related:` links only to entities that ALSO project. A wikilink to a page
    # that was never written is a dangling reference the graph reports as broken,
    # and pointing at a record verification did not entail would assert exactly
    # what projection-fidelity forbids.
    projected = {r["canonical_key"] for r in projectable(records)}
    related = sorted({
        yaml_scalar("[[" + slug_of(e["dst"]) + "]]")
        for e in out_edges if e.get("dst") in projected
    })

    lines = [
        "---",
        f"id: {yaml_scalar(KIND_TO_TYPE[kind] + '/' + slug_of(key))}",
        f"type: {KIND_TO_TYPE[kind]}",
        "status: candidate",
        f"core_claim: {yaml_scalar(core_claim_for(record, out_edges))}",
        "tags:",
        *[f"  - {t}" for t in PROJECTION_TAGS],
        "sources:",
        f"  - sourcer-run-{run_id}",
        "related:",
        *[f"  - {r}" for r in related],
        f"created: {yaml_scalar(stamp)}",
        f"updated: {yaml_scalar(stamp)}",
        "generated: sourcer",
        "---",
        "",
        f"# {name}",
        "",
        "> Generated by `sourcer` from a verified crawl. **Do not edit by hand** —",
        "> a projection is regenerable, so correcting it here would produce a claim",
        "> with no evidence behind it. Correct the map and re-project.",
        "",
        "## What the bytes say",
        "",
        f"This entity's name was read at bytes "
        f"`[{ev.get('span_start')}, {ev.get('span_end')})` of a page held at "
        f"`{str(ev.get('sha256', ''))[:12]}`:",
        "",
        f"> {ev.get('quote', '').strip()}",
        "",
        f"Source: <{ev.get('url', '')}>",
        "",
    ]

    if out_edges:
        lines += ["## Relations", ""]
        for e in out_edges:
            eev = e.get("evidence") or {}
            lines.append(
                f"- **{e.get('predicate')}** → `{e.get('dst')}` "
                f"— evidenced at `[{eev.get('span_start')}, {eev.get('span_end')})` "
                f"of `{str(eev.get('sha256', ''))[:12]}`"
            )
        lines.append("")

    lines += [
        "## What this does not claim",
        "",
        "A page at that URL, held at that digest, verifiably says this. It is",
        "**not** a claim that what the page says is true — an inflated title, a",
        "phantom advisory board or a nominee director each produce a fully green",
        "observed record. That is a strong, checkable guarantee and it is not",
        "omniscience.",
        "",
    ]
    return Page(key=key, path=f"{KIND_TO_TYPE[kind]}/{slug_of(key)}.md",
                body="\n".join(lines))


def build(records, run_id: str, today: Optional[str] = None) -> list:
    """Every page this map projects to. Writes nothing.

    Refuses on a path collision. Two distinct keys can slug to one filename, and
    without this the second page silently overwrites the first while
    `emitted_ids` reports both as projected -- a projection that claims more
    entities than it wrote.
    """
    pages = [page_for(r, records, run_id, today) for r in projectable(records)]
    seen: dict = {}
    for page in pages:
        if page.path in seen and seen[page.path] != page.key:
            raise ProjectionError(
                f"{page.key} and {seen[page.path]} both project to {page.path}; "
                "one would silently overwrite the other while both are reported "
                "as written"
            )
        seen[page.path] = page.key
    return pages


def emitted_ids(records) -> list:
    """The `projection-fidelity` input, derived from what WILL be written.

    Built here rather than assembled by a caller, so the gate audits the
    artifact instead of a list somebody remembered to keep in step with it.
    """
    return [{"id": r["id"]} for r in projectable(records)]


def write(pages: list, root: Path, dry_run: bool = True) -> dict:
    """Write the pages under `root` (an entities directory).

    `dry_run` defaults to TRUE. A projection writes into a permanent, shared,
    hand-curated knowledge graph, and the default for a command that does that
    is to show what it would do.
    """
    root = Path(root)
    written = []
    for page in pages:
        target = root / page.path
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page.body, encoding="utf-8")
        written.append(str(target))
    return {"dry_run": dry_run, "pages": len(pages), "paths": written}


__all__ = [
    "ProjectionError", "MAX_CORE_CLAIM", "PROJECTION_TAGS", "KIND_TO_TYPE",
    "Page", "slug_of", "core_claim_for", "projectable", "page_for", "build",
    "emitted_ids", "write",
]
