"""The handoff: a sourcer map becomes the node and edge tables Parallax ingests.

D6 — v1 emits node + edge tables, no ontology proposal. Parallax proposes the
ontology; this layer's job is to hand it rows with the observed/simulated
distinction still attached, because that distinction is the entire reason the
crawl was built the way it was and it is trivially lost in a table.

**The grammar is imported, never re-spelled.** `data-provider` already owns the
`--table` string Parallax parses -- its delimiters, its reserved characters, its
row count, its per-column origin. Writing a second copy here would create two
spellings of one contract, which is the drift this codebase has been bitten by
repeatedly: both sides stay green and agree with neither. So this module builds
`data-provider` Records and calls its `emit_table_arg`.

If `data-provider` cannot be imported, this module **refuses**. It does not fall
back to a local implementation of the grammar, because a fallback IS the second
spelling, and the failure it protects against is one that only shows up when the
two have already diverged.

**Only what verified is emitted.** A row Parallax accepts is a row somebody will
read as a finding, so the filter is the same one `expandable()` uses:
`observed AND entailed`, plus `simulated` rows whose ancestry the map holds and
which are graded honestly. An `unchecked` record has not been judged and does
not go.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract as X  # noqa: E402

#: Where `data-provider` lives relative to this skill. Both are under
#: `skills/simulation/`, and the import is by path rather than by package
#: because neither skill is installed -- they are directories a runner points at.
_PROVIDER = Path(__file__).resolve().parents[2] / "data-provider" / "scripts"


class EmitError(Exception):
    """A refusal. Never a silently-degraded table."""


def _provider():
    """The data-provider module, or a refusal naming what is missing.

    Deliberately not wrapped in a try/except that falls back. A fallback would
    be a second implementation of a grammar that already exists, and the whole
    point of importing is that there is only one.
    """
    if not (_PROVIDER / "provider.py").is_file():
        raise EmitError(
            f"data-provider is not at {_PROVIDER}. This module emits through its "
            "`--table` grammar rather than re-spelling it, so a missing "
            "data-provider is a refusal and not a reason to write the string here."
        )
    if str(_PROVIDER) not in sys.path:
        sys.path.insert(0, str(_PROVIDER))
    import provider  # noqa: PLC0415

    for needed in ("Record", "Field", "Evidence", "emit_table_arg", "ProviderError"):
        if not hasattr(provider, needed):
            raise EmitError(
                f"data-provider has no `{needed}`; its contract changed and this "
                "handoff must be updated rather than guessed at"
            )
    return provider


def shippable(records) -> list:
    """The rows a reader is allowed to see as findings.

    `observed AND entailed` is the same bar `expandable()` uses, and for the same
    reason: a record the crawl would not spend a fetch on is not one it should
    spend a reader's trust on either. `simulated` rows ride along -- they are
    real output, graded honestly -- but only when verification entailed them,
    so a guess nobody checked stays out of the table.
    """
    return [
        r for r in records
        if r.get("verdict") == "entailed" and r.get("origin") in ("observed", "simulated")
    ]


def retrieval_times(daemon) -> dict:
    """`(url, digest) -> retrieved_at`, read out of the chained fetch log.

    sourcer's own Evidence deliberately does not carry a timestamp: the CHAIN
    carries it. The fetch row is the timestamped record and the digest is what
    binds a citation to it, so reading the time back out of the log keeps the
    two layers agreeing about *when* instead of letting this one invent a value
    that would look identical and mean nothing.

    Returns `{}` for a daemon that cannot be read, and the caller says so in the
    emitted report rather than substituting `now()`.
    """
    if daemon is None:
        return {}
    # NOT swallowed. `verified_rows` raises when the chain does not hold, and
    # returning `{}` there meant a run whose log had been tampered with emitted
    # a table anyway -- with `evidence_verified=True` attached, which is the one
    # claim this module makes on its own authority. Failing open at exactly the
    # point the custody argument rests is worse than not checking at all.
    rows = daemon.verified_rows()
    return {
        (r.get("url"), r.get("sha256")): str(r.get("retrieved_at", ""))
        for r in rows if r.get("kind") == "fetch"
    }


def _field(provider, name: str, value, record: dict, when: dict):
    """One data-provider Field carrying this record's provenance.

    An `observed` field cites the artifact; a `simulated` one names what it was
    derived from. The disjunction is data-provider's own invariant and is
    restated here only because the two modules type provenance in the same
    shape for the same reason.
    """
    ev = record.get("evidence")
    if record.get("origin") == "observed" and ev:
        return provider.Field(
            name=name, value=value,
            evidence=provider.Evidence(
                url=ev["url"],
                sha256=ev["sha256"],
                # From the chain, not from `now()`. See `retrieval_times`.
                retrieved_at=when.get((ev["url"], ev["sha256"]), ""),
                # Derived from the digest, never from a stored field. The whole
                # reason sourcer resolves snapshot paths this way is that a
                # caller must not name the file its own citation is read from,
                # and handing that rule to another layer would be where it stops.
                snapshot=f"snapshots/{ev['sha256']}",
            ),
        )
    return provider.Field(
        name=name, value=value,
        inferred_from=", ".join(record.get("inferred_from") or ["the map"]),
    )


def node_rows(records, when: Optional[dict] = None) -> list:
    """One row per shippable node: key, kind, name, depth, layer."""
    provider = _provider()
    when = when or {}
    out = []
    for r in shippable(records):
        if r.get("kind") != "node":
            continue
        key = r.get("canonical_key", "")
        name = (r.get("attrs") or {}).get("name", key)
        out.append(provider.Record(fields=[
            # The JOIN column is the record `id`, because that is what an edge's
            # `src`/`dst` hold. Emitting `canonical_key` here made every edge in
            # the table point at a key no node row carried, whenever the two
            # differed -- a silently unjoinable pair of tables.
            _field(provider, "key", r.get("id"), r, when),
            _field(provider, "canonical_key", key, r, when),
            _field(provider, "kind", key.split("::", 1)[0], r, when),
            _field(provider, "name", name, r, when),
            _field(provider, "depth", r.get("depth", 0), r, when),
            _field(provider, "layer", r.get("layer", "L2"), r, when),
        ]))
    return out


def edge_rows(records, when: Optional[dict] = None) -> list:
    """One row per shippable edge: subject, predicate, object, depth.

    An edge whose endpoints are not themselves shippable is DROPPED, not
    emitted with dangling ids. A table asserting a relation between two things
    it does not contain says more than the map does, which is the exact thing
    `projection-fidelity` refuses.
    """
    provider = _provider()
    when = when or {}
    shipped = {r.get("id") for r in shippable(records) if r.get("kind") == "node"}
    out = []
    for r in shippable(records):
        if r.get("kind") != "edge":
            continue
        if r.get("src") not in shipped or r.get("dst") not in shipped:
            continue
        out.append(provider.Record(fields=[
            _field(provider, "subject", r.get("src"), r, when),
            _field(provider, "predicate", r.get("predicate"), r, when),
            _field(provider, "object", r.get("dst"), r, when),
            _field(provider, "depth", r.get("depth", 0), r, when),
        ]))
    return out


def dropped_edges(records) -> list:
    """Edges left out because an endpoint did not ship. Reported, not hidden.

    The count is the difference between "this map has no relations" and "this
    map's relations point at things verification did not entail", and a reader
    cannot tell those apart from the table alone.
    """
    shipped = {r.get("id") for r in shippable(records) if r.get("kind") == "node"}
    return [
        {"id": r.get("id"), "predicate": r.get("predicate"),
         "missing": [e for e in (r.get("src"), r.get("dst")) if e not in shipped]}
        for r in shippable(records)
        if r.get("kind") == "edge"
        and (r.get("src") not in shipped or r.get("dst") not in shipped)
    ]


def emit(records, prefix: str = "sourcer", daemon=None) -> dict:
    """Both tables, as the argv Parallax expects, plus what was left out.

    `evidence_verified=True` is passed deliberately and is the one claim this
    module makes on its own authority: the records reaching here have already
    been through `span-verbatim` and `transport-custody`, which check strictly
    more than data-provider's own artifact check does. Saying so explicitly is
    the contract data-provider asks for -- it refuses by default precisely so
    that a caller cannot skip verification silently.
    """
    provider = _provider()
    # An observed row's whole meaning is that bytes back it. Emitting one
    # without a daemon that can still verify its own chain would be asserting
    # custody nobody checked, so it refuses rather than degrades.
    if any(r.get("origin") == "observed" for r in shippable(records)):
        if daemon is None:
            raise EmitError(
                "this map holds observed rows, so `emit` needs the daemon that "
                "fetched them: the table is emitted with evidence_verified=True "
                "and that claim has to rest on something"
            )
        try:
            when = retrieval_times(daemon)
        except Exception as exc:
            raise EmitError(
                f"refusing to emit from an unverifiable run: {exc}. Every row "
                "would carry a custody claim the chain cannot support."
            ) from exc
    else:
        when = retrieval_times(daemon)
    nodes, edges = node_rows(records, when), edge_rows(records, when)
    if not nodes and not edges:
        raise EmitError(
            "nothing to emit: no record in this map is both entailed and "
            "gradeable. A run that found nothing is complete, not a table."
        )

    out = {
        "dropped_edges": dropped_edges(records),
        "tables": {},
        # Stated rather than assumed: a reader can see whether the timestamps in
        # this handoff came from the chain or were unavailable.
        "retrieval_times_resolved": bool(when),
    }
    for name, rows in (("nodes", nodes), ("edges", edges)):
        if not rows:
            out["tables"][name] = None
            continue
        table = f"{prefix}_{name}"
        arg = provider.emit_table_arg(table, rows, evidence_verified=True)
        out["tables"][name] = {
            "table": table,
            "rows": len(rows),
            "arg": arg,
            "argv": ["parallax", "propose", "--kind", "business-data", "--table", arg],
        }
    return out


__all__ = ["EmitError", "retrieval_times", "shippable", "node_rows", "edge_rows", "dropped_edges", "emit"]
