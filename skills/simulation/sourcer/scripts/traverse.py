"""Whole-site traversal: robots.txt -> sitemap -> a bounded page set.

This is the module that turns "fetch one URL when told" into "crawl a site". It
holds no network code at all. Every byte it reads arrives through
`FetchDaemon.fetch` and is read back through `open_attested`, so every page it
discovers is attested by construction rather than by a later check remembering
to run -- the custody split of the architecture is preserved by *not having an
alternative path*, which is the same reason the store takes an admitter and not
a predicate.

Two properties are worth stating up front because they are what the tests are
about, not incidental:

**A `<loc>` is a candidate, never a claim.** A sitemap is a page publishers
author about themselves. Nothing in it is evidence of anything; it is a list of
URLs somebody would like crawled. So traversal emits frontier entries, never
records. Whether those pages say what they are alleged to say is step 4's
question, asked of bytes.

**The accounting closes.** Every `<loc>` seen is either accepted or dropped with
a reason, and `Traversal.closes()` asserts it. A traversal that quietly caps at
N looks identical to one that found exactly N, and the spec's `inventory-closed`
gate exists because that difference is invisible in every other artifact. Every
bound in this module -- budget, document count, index depth, decompressed size --
drops what it excludes with a stated reason rather than truncating a list.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------
# Bounds
#
# Each of these is a refusal, not a truncation: crossing one appends to
# `dropped` with a reason. They exist because a sitemap is attacker-controlled
# input in the general case -- a crawl pointed at a hostile host must terminate
# and must not be able to exhaust the machine before it does.
# --------------------------------------------------------------------------

#: Cap on a sitemap *after* decompression. The sitemaps.org bound is 50MB
#: uncompressed; this is well above any legitimate document and far below what
#: would hurt. Enforced during the decompress, not after, or a 10KB gzip bomb
#: expanding to 10GB would already have been materialised before the check.
MAX_SITEMAP_BYTES = 64 * 1024 * 1024

#: How deep a chain of sitemap indexes may be followed. sitemaps.org permits
#: exactly one level of indexing; this allows a little slack for hosts that
#: nest anyway, and refuses beyond it. Without a bound, an index that lists
#: itself is an infinite crawl -- and `seen` deduplication alone does not save
#: you, because A -> B -> A' where A' is a byte-different copy of A recurses.
MAX_INDEX_DEPTH = 3

#: How many sitemap documents one traversal may fetch. A site with 500 sitemap
#: shards is legitimate; a site that generates one per request is not, and this
#: is the difference between the two that does not require telling them apart.
DEFAULT_MAX_DOCS = 50

#: How much compressed input is fed to the inflater at a time. A module-level
#: constant rather than a local so a test can shrink it: the truncation bug the
#: cap defends against only appears across a chunk boundary, and with a 64KB
#: step every realistic test fixture is a single chunk and can never reach it.
CHUNK_BYTES = 64 * 1024

#: First two bytes of a gzip member. Sitemaps are routinely served as `.xml.gz`
#: with a `Content-Type` that does not say so, so sniff the bytes rather than
#: trusting either the extension or the header.
GZIP_MAGIC = b"\x1f\x8b"

#: `Sitemap:` directives in robots.txt. The key is case-insensitive per the
#: convention, and the value runs to end of line.
_SITEMAP_LINE = re.compile(rb"^\s*sitemap\s*:\s*(\S+)\s*$", re.IGNORECASE)

#: Anything that looks like a document type declaration. See `parse_sitemap`.
_DOCTYPE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)


class TraversalError(Exception):
    """Traversal could not proceed. Distinct from a page being dropped.

    A drop is a recorded outcome of the traversal; an error means the traversal
    itself was asked to do something incoherent. Conflating them is how a crawl
    that fetched nothing reports a clean empty page set.
    """


# --------------------------------------------------------------------------
# URL identity
# --------------------------------------------------------------------------


def host_of(url: str) -> str:
    """The containment identity of a url: lowercased host, plus non-default port.

    Deliberately the same shape as `fetchd.Politeness.host_of`, and deliberately
    not imported from it -- traversal's question is "may this sitemap speak for
    this url", which is about authority, while politeness's is "how fast may I
    hit this server", which is about load. They agree today. Coupling them would
    mean a future change to one silently answers the other.
    """
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        # `urlsplit` parses lazily: `https://example.com:bogus/a` splits fine and
        # only raises when `.port` is read. A hostile sitemap can therefore reach
        # into the middle of parsing and throw a type traverse() does not catch,
        # aborting a whole crawl over one bad <loc>. An unparseable authority is
        # not a host, so it gets an identity nothing can match and is dropped by
        # the containment check like any other off-host entry.
        return "\x00invalid-authority"
    default = {"http": 80, "https": 443}.get(parts.scheme)
    return host if port in (None, default) else f"{host}:{port}"


def robots_url_for(seed: str) -> str:
    """The robots.txt that governs `seed`.

    Built from scheme+netloc only. Deriving it by string surgery on the seed
    ("strip everything after the last slash") put the rules file at
    `https://example.com/blog/robots.txt` for a seed of `/blog/post`, which is
    a 404 on every real host and therefore read as "no restrictions".
    """
    parts = urllib.parse.urlsplit(seed)
    if parts.scheme not in ("http", "https"):
        raise TraversalError(
            f"{seed!r}: traversal needs an http(s) url -- a scheme this module "
            "cannot fetch cannot be bounded by robots.txt either"
        )
    if not parts.hostname:
        raise TraversalError(f"{seed!r}: no host to traverse")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


# --------------------------------------------------------------------------
# robots.txt -> sitemap references
# --------------------------------------------------------------------------


def sitemap_refs(
    payload: bytes, robots_url: str
) -> tuple[list[str], list[tuple[str, str]]]:
    """Extract `Sitemap:` directives. Returns (accepted, [(raw, reason), ...]).

    Both halves are returned because the refusals are the interesting half. A
    robots.txt whose only sitemap points at another host is a real
    configuration and also the exact shape of a poisoned one; returning only
    the empty accepted-list makes those two indistinguishable to the caller.

    Parsed line-wise on bytes rather than decoded first: robots.txt has no
    declared encoding, and a single invalid UTF-8 byte anywhere in the file
    would otherwise take the whole rules document out.
    """
    accepted: list[str] = []
    refused: list[tuple[str, str]] = []
    seen: set[str] = set()
    home = host_of(robots_url)

    for raw_line in payload.splitlines():
        m = _SITEMAP_LINE.match(raw_line)
        if not m:
            continue
        raw = m.group(1).decode("utf-8", errors="replace")
        # Relative sitemap references are out of spec but common. Resolving
        # against robots_url makes `sitemap.xml` mean the site's own, which is
        # the only thing it could have meant.
        url = urllib.parse.urljoin(robots_url, raw)
        if url in seen:
            continue
        seen.add(url)

        scheme = urllib.parse.urlsplit(url).scheme
        if scheme not in ("http", "https"):
            refused.append((raw, f"scheme {scheme!r} is not http(s)"))
            continue
        if host_of(url) != home:
            # sitemaps.org permits cross-host submission only when the target
            # host's own robots.txt also names the sitemap -- a handshake this
            # module cannot complete from one side. Refusing is the honest
            # reading: otherwise any site could enlist a crawler against any
            # other by listing its URLs.
            refused.append((raw, f"off-host: {host_of(url)} is not {home}"))
            continue
        accepted.append(url)

    return accepted, refused


# --------------------------------------------------------------------------
# Sitemap documents
# --------------------------------------------------------------------------


def decompress_if_gzip(payload: bytes, cap: int = MAX_SITEMAP_BYTES) -> bytes:
    """Inflate a gzipped sitemap, refusing past `cap` *during* the inflate.

    `gzip.decompress(payload)` then checking the length is the version that does
    not work: by the time you can measure the result you have already allocated
    it, so a 40KB file that expands to 40GB is an OOM and not a refusal. This
    decompresses in bounded chunks and raises as soon as the running total
    crosses the cap.
    """
    if not payload.startswith(GZIP_MAGIC):
        return payload
    obj = zlib.decompressobj(zlib.MAX_WBITS | 16)  # 16 => gzip wrapper
    out = bytearray()
    view = memoryview(payload)
    over = (
        f"gzipped sitemap expands past {cap} bytes -- refusing to materialise "
        "it. A compression ratio this high is a bomb, not a large sitemap."
    )
    for off in range(0, len(view), CHUNK_BYTES):
        try:
            out += obj.decompress(view[off : off + CHUNK_BYTES], cap - len(out) + 1)
        except zlib.error as exc:
            raise TraversalError(f"corrupt gzip sitemap: {exc}") from exc
        # `unconsumed_tail` is non-empty exactly when max_length stopped the
        # inflate early. Feeding the next chunk on top of that silently DISCARDS
        # the tail, so a truncated inflate must never be a state we continue
        # from. Checking the tail is the direct statement of that; the `+ 1`
        # above is the arithmetic that makes hitting the limit imply crossing
        # the cap, and neither is trusted to cover for the other -- a mutation
        # sweep found the arithmetic alone was unenforced by any test.
        if obj.unconsumed_tail:
            raise TraversalError(over)
        if len(out) > cap:
            raise TraversalError(over)
    try:
        out += obj.flush()
    except zlib.error as exc:
        raise TraversalError(f"corrupt gzip sitemap: {exc}") from exc
    if len(out) > cap:
        raise TraversalError(over)
    if obj.unused_data:
        # A gzip stream may hold several members; `decompressobj` stops after the
        # first and parks the rest in `unused_data`. Returning the first member
        # alone meant `gzip(small_valid_sitemap) + gzip(10GB_of_A)` inflated to
        # 76 bytes, passed every cap, and silently discarded whatever else the
        # file claimed to contain. Refusing is right rather than decompressing
        # on: a multi-member sitemap is outside the format, so the choice is
        # between refusing it and inventing a rule about which member counts.
        raise TraversalError(
            f"gzipped sitemap carries {len(obj.unused_data)} trailing bytes after "
            "the first member -- refused. Decoding only the first member would "
            "silently drop whatever the rest of the file claims to hold."
        )
    if not obj.eof:
        raise TraversalError("truncated gzip sitemap -- the stream never ended")
    return bytes(out)


def _local(tag: str) -> str:
    """The local name of a possibly-namespaced ElementTree tag.

    ElementTree returns `{http://www.sitemaps.org/schemas/sitemap/0.9}urlset`.
    Matching the qualified name means a sitemap served without the namespace --
    which many are -- parses to zero entries and reads as an empty site.
    """
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


@dataclass(frozen=True)
class SitemapDoc:
    """One parsed sitemap: either an index of sitemaps or a set of pages."""

    kind: str  # "index" | "urlset"
    locs: tuple[str, ...]
    dropped: tuple[tuple[str, str], ...]  # (raw loc, reason)


def parse_sitemap(payload: bytes, doc_url: str) -> SitemapDoc:
    """Parse a sitemap or sitemap index into its `<loc>` entries.

    Host containment is enforced here rather than by the caller: a `<loc>`
    pointing off-host is dropped with a reason. The rule is the one property
    that keeps a crawl of one site from becoming a crawl of the internet, and
    leaving it to the caller means it holds only where the caller remembered.

    The sitemaps.org *path* rule -- that a sitemap at `/a/sitemap.xml` may only
    list URLs under `/a/` -- is deliberately NOT enforced. It is widely violated
    by correct, benign configurations (a `/sitemaps/pages.xml` listing `/about`
    is ordinary), so enforcing it would refuse mostly-real pages while adding
    nothing against a hostile host, which controls the whole origin anyway.
    Host containment is where the actual boundary is.
    """
    payload = decompress_if_gzip(payload)

    # Refuse a DOCTYPE outright rather than parse and hope. Measured on this
    # box: ElementTree on CPython 3.9.6 *does* expand internal entities, so the
    # billion-laughs document parses to a 100k-character `<loc>`; only external
    # entities (XXE) are refused. A sitemap has no legitimate use for a DTD, so
    # the structural refusal is both safe and free -- and unlike a size cap it
    # does not depend on guessing an expansion ratio.
    if _DOCTYPE.search(payload):
        raise TraversalError(
            f"{doc_url}: sitemap carries a DOCTYPE -- refused unparsed. Entity "
            "expansion is on in this parser and a sitemap never needs a DTD."
        )

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise TraversalError(f"{doc_url}: not parseable as XML -- {exc}") from exc

    root_name = _local(root.tag)
    if root_name == "sitemapindex":
        kind, wrapper = "index", "sitemap"
    elif root_name == "urlset":
        kind, wrapper = "urlset", "url"
    else:
        raise TraversalError(
            f"{doc_url}: root element is <{root_name}>, not <urlset> or "
            "<sitemapindex> -- this is not a sitemap"
        )

    home = host_of(doc_url)
    locs: list[str] = []
    dropped: list[tuple[str, str]] = []
    seen: set[str] = set()

    for entry in root:
        if _local(entry.tag) != wrapper:
            continue
        loc_el = next((c for c in entry if _local(c.tag) == "loc"), None)
        if loc_el is None or not (loc_el.text or "").strip():
            dropped.append(("", f"<{wrapper}> with no <loc>"))
            continue
        raw = loc_el.text.strip()
        # Resolved against the document, so a relative <loc> -- out of spec but
        # emitted by real generators -- means what it obviously means.
        url = urllib.parse.urljoin(doc_url, raw)
        if url in seen:
            continue
        seen.add(url)
        scheme = urllib.parse.urlsplit(url).scheme
        if scheme not in ("http", "https"):
            dropped.append((raw, f"scheme {scheme!r} is not http(s)"))
            continue
        if host_of(url) != home:
            dropped.append((raw, f"off-host: {host_of(url)} is not {home}"))
            continue
        locs.append(url)

    return SitemapDoc(kind=kind, locs=tuple(locs), dropped=tuple(dropped))


# --------------------------------------------------------------------------
# The traversal
# --------------------------------------------------------------------------


@dataclass
class Traversal:
    """What one site traversal found, and everything it did not keep.

    `docs` records every sitemap document the daemon was asked for and what came
    back, so "this site has no sitemap" and "the sitemap 404'd" and "the sitemap
    was a bomb" are three distinguishable outcomes rather than one empty list.
    """

    seed: str
    robots_url: str
    pages: list[str] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    docs: list[dict] = field(default_factory=list)
    seen: int = 0

    def drop(self, url: str, reason: str, source: str = "") -> None:
        self.dropped.append({"url": url, "reason": reason, "source": source})

    def closes(self) -> bool:
        """Every distinct candidate is accounted for exactly once.

        A *candidate* is a URL the traversal considered admitting -- a page from
        a `<urlset>`, a sitemap reference, or an index entry it declined to
        follow. Each is counted in `seen` once, at first sighting, and must end
        up in exactly one of `pages` or `dropped`. Re-sightings are not counted
        again; an index entry that *was* followed is not a candidate at all,
        because it is accounted for in `docs` as a document instead.

        This is the `inventory-closed` gate's local form. It is a method rather
        than a comment because a bound that silently truncates and a site that
        genuinely ended are identical in `pages` alone, and this is the only
        place that difference survives.
        """
        return len(self.pages) + len(self.dropped) == self.seen

    def as_dict(self) -> dict:
        return {
            "seed": self.seed,
            "robots_url": self.robots_url,
            "pages": list(self.pages),
            "dropped": list(self.dropped),
            "docs": list(self.docs),
            "seen": self.seen,
            "closes": self.closes(),
        }


def _fetch_text(daemon, url: str) -> tuple[Optional[bytes], str]:
    """Fetch through the daemon and read the attested bytes back. (bytes, note).

    Returns `(None, reason)` for every failure a hostile or merely broken host
    can produce, because traversal must survive one bad document. The bytes come
    from `open_attested(url, digest)` rather than from the transport's return
    value: the digest resolves the path, so even here -- where the caller is
    trusted code -- there is no argument that names the file being read.
    """
    # Imported lazily and by name so this module has no import-time dependency
    # on the daemon, which keeps `parse_sitemap` and friends unit-testable with
    # no key in the environment. (`FetchDaemon` refuses to construct unkeyed.)
    import fetchd as F

    try:
        res = daemon.fetch(url)
    except F.RobotsRefusal as exc:
        return None, f"robots.txt refuses it: {exc}"
    except F.RedirectRefusal as exc:
        return None, f"redirected: {exc}"
    except F.FetchError as exc:
        return None, f"fetch failed: {exc}"
    except Exception as exc:  # transport/network defects are not our verdict
        return None, f"fetch raised {type(exc).__name__}: {exc}"

    ok, why = daemon.usable_as_evidence(res)
    if not ok:
        return None, why
    try:
        return daemon.open_attested(res.url, res.sha256), "ok"
    except F.FetchError as exc:
        return None, f"attested bytes unreadable: {exc}"


def traverse(
    daemon,
    seed: str,
    budget: int,
    max_docs: int = DEFAULT_MAX_DOCS,
    max_index_depth: int = MAX_INDEX_DEPTH,
) -> Traversal:
    """robots.txt -> sitemap(s) -> a bounded page set, all bytes via `daemon`.

    `budget` caps accepted pages. It is a cap on what enters the frontier, not a
    cap on what is looked at: every `<loc>` past the budget is dropped with
    `"budget exhausted"`, so the truncation is visible in the result instead of
    being the difference between two lists of the same length.

    Sitemap indexes are followed breadth-first to `max_index_depth`. Documents
    already fetched are not re-fetched -- an index listing itself is a common
    generator bug and an obvious loop.
    """
    if budget < 0:
        raise TraversalError(f"budget must be >= 0, got {budget}")
    if max_docs < 1:
        raise TraversalError(f"max_docs must be >= 1, got {max_docs}")

    robots = robots_url_for(seed)
    out = Traversal(seed=seed, robots_url=robots)

    payload, note = _fetch_text(daemon, robots)
    out.docs.append({"url": robots, "kind": "robots", "note": note})
    if payload is None:
        # No rules file is not an error and not a page set. The daemon's own
        # politeness layer has already decided what an absent robots.txt means
        # for permission; traversal only loses its sitemap references.
        return out

    refs, refused = sitemap_refs(payload, robots)
    for raw, reason in refused:
        out.seen += 1
        out.drop(raw, reason, source=robots)

    # (url, index_depth). Breadth-first so a shallow, complete sitemap is
    # exhausted before a deep chain spends the document budget.
    queue: list[tuple[str, int]] = [(u, 0) for u in refs]
    #: Every url ever put on `queue`, so an index that lists a sibling index
    #: twice does not enter twice and is not counted twice when it is dropped.
    enqueued: set[str] = set(refs)
    #: Every url whose bytes were actually requested. Separate from `enqueued`
    #: because the document budget is about fetches, not about intentions.
    fetched: set[str] = set()
    #: Every page-candidate counted into `seen`. Two sitemap shards listing the
    #: same page is ordinary, and counting it twice would break `closes()` in
    #: exactly the way `closes()` exists to catch.
    considered: set[str] = set()

    while queue:
        doc_url, idepth = queue.pop(0)
        if doc_url in fetched:
            continue
        if len(fetched) >= max_docs:
            out.seen += 1
            out.drop(doc_url, f"document budget of {max_docs} exhausted", source=seed)
            continue
        fetched.add(doc_url)

        payload, note = _fetch_text(daemon, doc_url)
        if payload is None:
            out.docs.append({"url": doc_url, "kind": "sitemap", "note": note})
            continue
        try:
            doc = parse_sitemap(payload, doc_url)
        except TraversalError as exc:
            out.docs.append({"url": doc_url, "kind": "sitemap", "note": str(exc)})
            continue

        out.docs.append(
            {
                "url": doc_url,
                "kind": doc.kind,
                "note": "ok",
                "n_locs": len(doc.locs),
                "n_dropped": len(doc.dropped),
            }
        )
        for raw, reason in doc.dropped:
            out.seen += 1
            out.drop(raw, reason, source=doc_url)

        if doc.kind == "index":
            for loc in doc.locs:
                if loc in enqueued:
                    continue
                if idepth + 1 > max_index_depth:
                    # Declined, so it is a candidate that produced nothing and
                    # must show up in the accounting. An entry that IS followed
                    # is not counted here at all -- it becomes a row in `docs`.
                    enqueued.add(loc)
                    out.seen += 1
                    out.drop(
                        loc,
                        f"sitemap index nested past depth {max_index_depth}",
                        source=doc_url,
                    )
                    continue
                enqueued.add(loc)
                queue.append((loc, idepth + 1))
            continue

        for loc in doc.locs:
            # Counted once, at first sighting. Sharded sitemaps repeat URLs.
            if loc in considered:
                continue
            considered.add(loc)
            out.seen += 1
            if len(out.pages) >= budget:
                out.drop(loc, "budget exhausted", source=doc_url)
                continue
            out.pages.append(loc)

    return out


def push_pages(
    conn, pages, depth: int, parent_id: Optional[str] = None
) -> int:
    """Put a traversal's page set on the store's frontier at `depth`.

    Returns the number newly queued. Deliberately thin: `push_frontier` already
    owns re-sighting and the shorter-path depth update, and a second copy of
    that logic here is a second place for it to be wrong.
    """
    import store as S

    return sum(1 for url in pages if S.push_frontier(conn, url, depth, parent_id))


__all__ = [
    "TraversalError",
    "SitemapDoc",
    "Traversal",
    "MAX_SITEMAP_BYTES",
    "MAX_INDEX_DEPTH",
    "DEFAULT_MAX_DOCS",
    "CHUNK_BYTES",
    "host_of",
    "robots_url_for",
    "sitemap_refs",
    "decompress_if_gzip",
    "parse_sitemap",
    "traverse",
    "push_pages",
]
