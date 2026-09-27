"""Tests for whole-site traversal.

Two things this module is really about, and they are not "does it parse XML".

The first is that traversal cannot reach the network on its own. Every test that
exercises `traverse` hands it a daemon with an injected transport, and one test
asserts the module holds no network import at all -- because "it only fetches
through the daemon" is a claim about a path not existing, and a test that only
watches the happy path cannot see the other one.

The second is that the accounting closes. Nearly every traversal test ends by
asserting `closes()`, including -- especially -- the ones where a bound fires.
A crawl that silently drops half a site and one that found half a site produce
the same `pages` list, and `seen` is the only place they differ.
"""

from __future__ import annotations

import gzip
import random
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetchd as F  # noqa: E402
import store as S  # noqa: E402
import traverse as T  # noqa: E402

KEY = b"traverse-test-key"

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def urlset(*locs, ns=True) -> bytes:
    body = "".join(f"<url><loc>{u}</loc></url>" for u in locs)
    return f'<?xml version="1.0"?><urlset {NS if ns else ""}>{body}</urlset>'.encode()


def index(*locs, ns=True) -> bytes:
    body = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in locs)
    return (
        f'<?xml version="1.0"?><sitemapindex {NS if ns else ""}>{body}</sitemapindex>'
    ).encode()


def robots(*sitemaps) -> bytes:
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Sitemap: {s}" for s in sitemaps]
    return ("\n".join(lines) + "\n").encode()


class AllowAll(F.Politeness):
    def __init__(self):
        super().__init__(interval=0.0)

    def allows(self, url):
        return True


def rig(tmp_path, pages: dict, politeness=None):
    """A sealed daemon serving `pages`, mapping url -> (status, bytes)."""

    def transport(url):
        entry = pages.get(url)
        if entry is None:
            return (404, b"not found", url)
        return entry if len(entry) == 3 else (entry[0], entry[1], url)

    d = F.FetchDaemon(
        root=tmp_path / "runs",
        run_id="r1",
        politeness=politeness or AllowAll(),
        transport=transport,
        key=KEY,
    )
    d.seal_plan({"seeds": ["https://example.com/"], "max_depth": 1})
    return d


# --------------------------------------------------------------------------
# The custody claim, asserted structurally
# --------------------------------------------------------------------------


def test_traverse_module_cannot_reach_the_network():
    """The claim is that bytes arrive only via the daemon. Prove the path is absent.

    A behavioural test cannot establish this: it can show the daemon WAS used on
    the paths it exercised, never that no other path exists. Reading the source
    for a network import can.
    """
    src = (Path(T.__file__)).read_text()
    for forbidden in ("urllib.request", "urlopen", "import requests", "http.client",
                      "socket"):
        assert forbidden not in src, (
            f"traverse.py references {forbidden!r} -- if traversal can open a "
            "socket, every page it reports is attested by convention rather than "
            "by construction"
        )
    # urllib.parse is fine and is what it does use.
    assert "import urllib.parse" in src


def test_traverse_fetches_nothing_the_daemon_did_not(tmp_path):
    """Every url traversal touched appears in the daemon's chained log."""
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/sm.xml")),
        "https://example.com/sm.xml": (200, urlset("https://example.com/a")),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == ["https://example.com/a"]
    logged = {u for (u, _digest) in d.pairs()}
    assert logged == {"https://example.com/robots.txt", "https://example.com/sm.xml"}
    # The discovered page is a CANDIDATE. Traversal must not have fetched it --
    # that is the next hop's job, under the next hop's budget.
    assert "https://example.com/a" not in logged
    assert out.closes()


# --------------------------------------------------------------------------
# robots.txt -> sitemap references
# --------------------------------------------------------------------------


def test_sitemap_refs_are_case_insensitive_and_deduped():
    payload = b"SITEMAP: https://example.com/a.xml\nsitemap:  https://example.com/a.xml\nSiTeMaP: https://example.com/b.xml\n"
    ok, refused = T.sitemap_refs(payload, "https://example.com/robots.txt")
    assert ok == ["https://example.com/a.xml", "https://example.com/b.xml"]
    assert refused == []


def test_relative_sitemap_reference_resolves_against_the_rules_file():
    ok, _ = T.sitemap_refs(b"Sitemap: /sm.xml\n", "https://example.com/robots.txt")
    assert ok == ["https://example.com/sm.xml"]


def test_off_host_sitemap_reference_is_refused_with_a_reason():
    """The empty accepted-list is not enough -- the refusal must be legible."""
    ok, refused = T.sitemap_refs(
        b"Sitemap: https://evil.example.net/sm.xml\n",
        "https://example.com/robots.txt",
    )
    assert ok == []
    assert len(refused) == 1
    assert "off-host" in refused[0][1]


def test_non_http_sitemap_scheme_is_refused():
    ok, refused = T.sitemap_refs(
        b"Sitemap: file:///etc/passwd\n", "https://example.com/robots.txt"
    )
    assert ok == []
    assert "not http(s)" in refused[0][1]


def test_invalid_utf8_in_robots_does_not_lose_the_file():
    """One bad byte must not take out the rules document."""
    payload = b"# \xff\xfe garbage comment\nSitemap: https://example.com/sm.xml\n"
    ok, _ = T.sitemap_refs(payload, "https://example.com/robots.txt")
    assert ok == ["https://example.com/sm.xml"]


def test_robots_url_is_built_from_the_origin_not_the_seed_path():
    assert (
        T.robots_url_for("https://example.com/blog/post?x=1")
        == "https://example.com/robots.txt"
    )
    assert T.robots_url_for("http://example.com:8080/x") == "http://example.com:8080/robots.txt"


@pytest.mark.parametrize("bad", ["ftp://example.com/x", "not-a-url", "https:///nohost"])
def test_unfetchable_seed_is_refused(bad):
    with pytest.raises(T.TraversalError):
        T.robots_url_for(bad)


# --------------------------------------------------------------------------
# Sitemap parsing
# --------------------------------------------------------------------------


def test_namespaced_and_bare_sitemaps_both_parse():
    """Matching the qualified tag name reads a bare sitemap as an empty site."""
    for ns in (True, False):
        doc = T.parse_sitemap(
            urlset("https://example.com/a", "https://example.com/b", ns=ns),
            "https://example.com/sm.xml",
        )
        assert doc.kind == "urlset"
        assert doc.locs == ("https://example.com/a", "https://example.com/b")


def test_sitemap_index_is_distinguished_from_a_urlset():
    doc = T.parse_sitemap(index("https://example.com/s1.xml"), "https://example.com/i.xml")
    assert doc.kind == "index"


def test_off_host_loc_is_dropped_with_a_reason():
    doc = T.parse_sitemap(
        urlset("https://example.com/a", "https://evil.example.net/b"),
        "https://example.com/sm.xml",
    )
    assert doc.locs == ("https://example.com/a",)
    assert len(doc.dropped) == 1
    assert "off-host" in doc.dropped[0][1]


def test_relative_loc_resolves_against_the_document():
    doc = T.parse_sitemap(urlset("/a", "b"), "https://example.com/sub/sm.xml")
    assert doc.locs == ("https://example.com/a", "https://example.com/sub/b")


def test_a_url_entry_with_no_loc_is_dropped_not_skipped():
    payload = f'<urlset {NS}><url><lastmod>2026-01-01</lastmod></url></urlset>'.encode()
    doc = T.parse_sitemap(payload, "https://example.com/sm.xml")
    assert doc.locs == ()
    assert len(doc.dropped) == 1


def test_a_non_sitemap_document_is_refused():
    with pytest.raises(T.TraversalError, match="not a sitemap"):
        T.parse_sitemap(b"<html><body>hi</body></html>", "https://example.com/sm.xml")


def test_unparseable_xml_is_refused():
    with pytest.raises(T.TraversalError, match="not parseable"):
        T.parse_sitemap(b"<urlset><url>", "https://example.com/sm.xml")


def test_billion_laughs_is_refused_unparsed():
    """Measured, not assumed: ElementTree on CPython 3.9 DOES expand internal
    entities, so this document parses to a 100k-character <loc> if allowed
    through. The refusal is structural -- a DOCTYPE at all -- because a sitemap
    has no legitimate use for one."""
    bomb = (
        b'<?xml version="1.0"?>\n'
        b'<!DOCTYPE lolz [ <!ENTITY lol "lol">'
        b' <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        b' <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;"> ]>\n'
        b"<urlset><url><loc>&lol3;</loc></url></urlset>"
    )
    with pytest.raises(T.TraversalError, match="DOCTYPE"):
        T.parse_sitemap(bomb, "https://example.com/sm.xml")


def test_xxe_is_refused():
    xxe = (
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b"<urlset><url><loc>&x;</loc></url></urlset>"
    )
    with pytest.raises(T.TraversalError, match="DOCTYPE"):
        T.parse_sitemap(xxe, "https://example.com/sm.xml")


# --------------------------------------------------------------------------
# Compression
# --------------------------------------------------------------------------


def test_gzipped_sitemap_is_inflated_and_parsed():
    doc = T.parse_sitemap(
        gzip.compress(urlset("https://example.com/a")), "https://example.com/sm.xml.gz"
    )
    assert doc.locs == ("https://example.com/a",)


def test_uncompressed_payload_passes_through_untouched():
    raw = urlset("https://example.com/a")
    assert T.decompress_if_gzip(raw) is raw


def test_gzip_bomb_is_refused_before_it_is_materialised():
    """A 10MB-of-zeros member compresses to a few KB. The cap must fire during
    the inflate; `gzip.decompress()` then measuring has already allocated it."""
    bomb = gzip.compress(b"\0" * (2 * 1024 * 1024))
    assert len(bomb) < 64 * 1024, "fixture is not actually a high-ratio payload"
    with pytest.raises(T.TraversalError, match="expands past"):
        T.decompress_if_gzip(bomb, cap=1024)


def test_a_payload_just_under_the_cap_still_inflates():
    """The bound must not be off by one in the refusing direction."""
    body = urlset(*(f"https://example.com/{i}" for i in range(20)))
    out = T.decompress_if_gzip(gzip.compress(body), cap=len(body))
    assert out == body


def test_a_multi_chunk_payload_at_the_cap_is_not_silently_truncated(monkeypatch):
    """The bound must refuse, never quietly return a prefix.

    Found by a mutation sweep: dropping the `+ 1` from max_length survived the
    whole suite, because with a 64KB chunk step every fixture here is a single
    chunk and the truncation only exists across a chunk boundary. Shrinking the
    step is what makes the failure reachable at test scale at all.
    """
    monkeypatch.setattr(T, "CHUNK_BYTES", 256)
    # Incompressible on purpose: the chunking is over COMPRESSED input, so
    # 8KB of "x" is one 43-byte chunk and never crosses a boundary. Seeded so
    # the fixture is the same bytes on every run.
    rnd = random.Random(20260824)
    body = bytes(rnd.randrange(256) for _ in range(8192))
    blob = gzip.compress(body)
    assert len(blob) > 4 * 256, "fixture must span several inflate chunks"
    # Under the cap: complete bytes, no prefix.
    assert T.decompress_if_gzip(blob, cap=len(body) + 10) == body
    # Over the cap: a refusal, not a truncated return.
    with pytest.raises(T.TraversalError, match="expands past"):
        T.decompress_if_gzip(blob, cap=1000)


def test_corrupt_gzip_is_a_refusal_not_a_crash():
    broken = bytearray(gzip.compress(urlset("https://example.com/a")))
    broken[10:20] = b"\x00" * 10
    with pytest.raises((T.TraversalError, zlib.error)):
        T.decompress_if_gzip(bytes(broken))


# --------------------------------------------------------------------------
# The traversal, end to end
# --------------------------------------------------------------------------


def test_closes_reports_false_when_the_accounting_does_not_balance():
    """The polarity test for `closes()`, and the reason it exists.

    A mutation sweep replaced the whole body with `return True` and all 44 tests
    still passed -- so every `assert out.closes()` in this file was asserting a
    constant. An invariant no test has ever seen fail is not an invariant, it is
    a decoration.
    """
    t = T.Traversal(seed="s", robots_url="r")
    t.seen = 3
    assert not t.closes(), "0 accounted for, 3 seen"
    t.pages.append("https://example.com/a")
    assert not t.closes(), "1 accounted for, 3 seen"
    t.drop("https://example.com/b", "budget exhausted")
    assert not t.closes(), "2 accounted for, 3 seen"
    t.drop("https://example.com/c", "off-host")
    assert t.closes()
    # And it fails in the other direction too: recording something never seen.
    t.drop("https://example.com/d", "phantom")
    assert not t.closes(), "4 accounted for, 3 seen"


def test_over_depth_index_named_by_two_parents_yields_one_drop(tmp_path):
    """Two shards naming the same too-deep index must not double-count it.

    The `enqueued` guard is not what makes the crawl terminate -- `fetched`
    already does that, which is why a mutation sweep found removing it survived
    the termination test. What it protects is the denominator: a candidate
    counted twice makes `seen` disagree with the number of distinct URLs the
    traversal actually considered.
    """
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/i.xml")),
        "https://example.com/i.xml": (
            200, index("https://example.com/a.xml", "https://example.com/b.xml"),
        ),
        # Both children name the SAME grandchild, which sits past the bound.
        "https://example.com/a.xml": (200, index("https://example.com/deep.xml")),
        "https://example.com/b.xml": (200, index("https://example.com/deep.xml")),
    })
    out = T.traverse(d, "https://example.com/", budget=10, max_index_depth=1)
    deep = [x for x in out.dropped if x["url"] == "https://example.com/deep.xml"]
    assert len(deep) == 1, f"counted {len(deep)} times: {out.dropped}"
    assert out.seen == 1
    assert out.closes()


def test_a_whole_site_traversal(tmp_path):
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/sm.xml")),
        "https://example.com/sm.xml": (
            200, urlset("https://example.com/a", "https://example.com/b"),
        ),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == ["https://example.com/a", "https://example.com/b"]
    assert out.dropped == []
    assert out.seen == 2
    assert out.closes()


def test_an_index_is_followed_to_its_shards(tmp_path):
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/i.xml")),
        "https://example.com/i.xml": (
            200, index("https://example.com/s1.xml", "https://example.com/s2.xml"),
        ),
        "https://example.com/s1.xml": (200, urlset("https://example.com/a")),
        "https://example.com/s2.xml": (200, urlset("https://example.com/b")),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    assert sorted(out.pages) == ["https://example.com/a", "https://example.com/b"]
    assert out.closes()


def test_a_self_referential_index_terminates(tmp_path):
    """A generator bug that lists the index in itself is an infinite crawl."""
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/i.xml")),
        "https://example.com/i.xml": (
            200, index("https://example.com/i.xml", "https://example.com/s.xml"),
        ),
        "https://example.com/s.xml": (200, urlset("https://example.com/a")),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == ["https://example.com/a"]
    assert out.closes()


def test_index_nesting_past_the_bound_is_dropped_with_a_reason(tmp_path):
    pages = {
        "https://example.com/robots.txt": (200, robots("https://example.com/i0.xml")),
    }
    # i0 -> i1 -> i2 -> i3 -> i4, each a distinct index document.
    for i in range(5):
        pages[f"https://example.com/i{i}.xml"] = (
            200, index(f"https://example.com/i{i + 1}.xml"),
        )
    d = rig(tmp_path, pages)
    out = T.traverse(d, "https://example.com/", budget=10, max_index_depth=2)
    assert out.pages == []
    assert [x["reason"] for x in out.dropped] == ["sitemap index nested past depth 2"]
    assert out.closes()


def test_budget_exhaustion_is_recorded_never_silent(tmp_path):
    """The whole point of `seen`. Two pages kept out of five must be legible as
    a truncation, not as a site with two pages."""
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/sm.xml")),
        "https://example.com/sm.xml": (
            200, urlset(*(f"https://example.com/{i}" for i in range(5))),
        ),
    })
    out = T.traverse(d, "https://example.com/", budget=2)
    assert len(out.pages) == 2
    assert len(out.dropped) == 3
    assert all(x["reason"] == "budget exhausted" for x in out.dropped)
    assert out.seen == 5
    assert out.closes()


def test_a_page_listed_by_two_shards_is_counted_once(tmp_path):
    """Sharded sitemaps repeat URLs. Counting a re-sighting into `seen` without
    landing it anywhere breaks the very invariant `seen` exists to support."""
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/i.xml")),
        "https://example.com/i.xml": (
            200, index("https://example.com/s1.xml", "https://example.com/s2.xml"),
        ),
        "https://example.com/s1.xml": (
            200, urlset("https://example.com/a", "https://example.com/dup"),
        ),
        "https://example.com/s2.xml": (
            200, urlset("https://example.com/dup", "https://example.com/b"),
        ),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    assert sorted(out.pages) == [
        "https://example.com/a", "https://example.com/b", "https://example.com/dup",
    ]
    assert out.seen == 3
    assert out.closes()


def test_document_budget_is_recorded_never_silent(tmp_path):
    pages = {
        "https://example.com/robots.txt": (
            200, robots(*(f"https://example.com/s{i}.xml" for i in range(4))),
        ),
    }
    for i in range(4):
        pages[f"https://example.com/s{i}.xml"] = (200, urlset(f"https://example.com/p{i}"))
    d = rig(tmp_path, pages)
    out = T.traverse(d, "https://example.com/", budget=10, max_docs=2)
    assert len(out.pages) == 2
    assert len(out.dropped) == 2
    assert all("document budget" in x["reason"] for x in out.dropped)
    assert out.closes()


def test_a_missing_robots_yields_an_empty_traversal_not_an_error(tmp_path):
    d = rig(tmp_path, {})
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == []
    assert out.docs[0]["kind"] == "robots"
    assert "not a page" in out.docs[0]["note"]
    assert out.closes()


def test_a_404_sitemap_does_not_abort_the_others(tmp_path):
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (
            200, robots("https://example.com/gone.xml", "https://example.com/ok.xml"),
        ),
        "https://example.com/ok.xml": (200, urlset("https://example.com/a")),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == ["https://example.com/a"]
    notes = {doc["url"]: doc["note"] for doc in out.docs}
    assert "not a page" in notes["https://example.com/gone.xml"]
    assert out.closes()


def test_a_redirecting_sitemap_is_dropped_not_fatal(tmp_path):
    """The daemon refuses redirects so a citation names where bytes came from.
    Traversal must survive that refusal, not propagate it."""
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (
            200, robots("https://example.com/moved.xml", "https://example.com/ok.xml"),
        ),
        "https://example.com/moved.xml": (200, urlset("https://example.com/x"),
                                          "https://example.com/elsewhere.xml"),
        "https://example.com/ok.xml": (200, urlset("https://example.com/a")),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == ["https://example.com/a"]
    notes = {doc["url"]: doc["note"] for doc in out.docs}
    assert "redirected" in notes["https://example.com/moved.xml"]
    assert out.closes()


def test_robots_refusal_of_a_sitemap_is_survived(tmp_path):
    class RefuseSitemaps(F.Politeness):
        def __init__(self):
            super().__init__(interval=0.0)

        def allows(self, url):
            return url.endswith("/robots.txt")

    d = rig(
        tmp_path,
        {
            "https://example.com/robots.txt": (200, robots("https://example.com/sm.xml")),
            "https://example.com/sm.xml": (200, urlset("https://example.com/a")),
        },
        politeness=RefuseSitemaps(),
    )
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == []
    assert "robots.txt refuses it" in out.docs[1]["note"]
    assert out.closes()


def test_a_bombed_sitemap_does_not_take_out_the_traversal(tmp_path):
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (
            200, robots("https://example.com/bomb.xml", "https://example.com/ok.xml"),
        ),
        "https://example.com/bomb.xml": (
            200,
            b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aa">]><urlset><url>'
            b"<loc>&a;</loc></url></urlset>",
        ),
        "https://example.com/ok.xml": (200, urlset("https://example.com/a")),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == ["https://example.com/a"]
    notes = {doc["url"]: doc["note"] for doc in out.docs}
    assert "DOCTYPE" in notes["https://example.com/bomb.xml"]
    assert out.closes()


def test_zero_budget_keeps_nothing_and_still_closes(tmp_path):
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/sm.xml")),
        "https://example.com/sm.xml": (200, urlset("https://example.com/a")),
    })
    out = T.traverse(d, "https://example.com/", budget=0)
    assert out.pages == []
    assert len(out.dropped) == 1
    assert out.closes()


@pytest.mark.parametrize("budget,max_docs", [(-1, 10), (10, 0)])
def test_incoherent_bounds_are_refused(tmp_path, budget, max_docs):
    d = rig(tmp_path, {})
    with pytest.raises(T.TraversalError):
        T.traverse(d, "https://example.com/", budget=budget, max_docs=max_docs)


def test_traversal_refuses_to_fetch_before_the_plan_is_sealed(tmp_path):
    """Inherited from the daemon, and worth pinning: an unsealed run has no
    denominator, so a page set from one means nothing."""
    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r1", politeness=AllowAll(),
        transport=lambda u: (200, b"", u), key=KEY,
    )
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == []
    assert "no sealed plan" in out.docs[0]["note"]


def test_as_dict_carries_the_closure_flag(tmp_path):
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/sm.xml")),
        "https://example.com/sm.xml": (200, urlset("https://example.com/a")),
    })
    out = T.traverse(d, "https://example.com/", budget=10).as_dict()
    assert out["closes"] is True
    assert out["pages"] == ["https://example.com/a"]


# --------------------------------------------------------------------------
# Handing the page set to the store
# --------------------------------------------------------------------------


def test_pages_reach_the_frontier(tmp_path):
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/sm.xml")),
        "https://example.com/sm.xml": (
            200, urlset("https://example.com/a", "https://example.com/b"),
        ),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    conn = S.connect(tmp_path / "map.db")
    assert T.push_pages(conn, out.pages, depth=1, parent_id="seed") == 2
    # Idempotent: a second traversal of the same site re-queues nothing.
    assert T.push_pages(conn, out.pages, depth=1, parent_id="seed") == 0
    assert S.frontier_stats(conn)["total"] == 2


def test_a_queued_page_is_claimable_at_its_depth(tmp_path):
    conn = S.connect(tmp_path / "map.db")
    T.push_pages(conn, ["https://example.com/a"], depth=1)
    assert S.claim(conn, "w1", max_depth=0) is None, "depth bound must hold"
    row = S.claim(conn, "w1", max_depth=1)
    assert row["key"] == "https://example.com/a"


def test_a_malformed_authority_is_dropped_not_raised():
    """`urlsplit` parses lazily and only raises when `.port` is read, so a
    hostile `<loc>` reached into the middle of parsing and threw a type
    `traverse()` does not catch — aborting a whole crawl over one bad entry."""
    doc = T.parse_sitemap(
        urlset("https://example.com/ok", "https://example.com:bogus/a"),
        "https://example.com/sm.xml",
    )
    assert doc.locs == ("https://example.com/ok",)
    assert len(doc.dropped) == 1
    assert "off-host" in doc.dropped[0][1]


def test_a_malformed_authority_does_not_abort_a_traversal(tmp_path):
    d = rig(tmp_path, {
        "https://example.com/robots.txt": (200, robots("https://example.com/sm.xml")),
        "https://example.com/sm.xml": (
            200, urlset("https://example.com:bogus/a", "https://example.com/good"),
        ),
    })
    out = T.traverse(d, "https://example.com/", budget=10)
    assert out.pages == ["https://example.com/good"]
    assert out.closes()


def test_trailing_bytes_after_the_first_gzip_member_are_refused():
    """`decompressobj` stops after the first member and parks the rest in
    `unused_data`. Returning the first alone meant
    `gzip(small_sitemap) + gzip(10GB)` inflated to 76 bytes, passed every cap,
    and silently discarded whatever else the file claimed to hold."""
    good = urlset("https://example.com/a")
    blob = gzip.compress(good) + gzip.compress(b"A" * 5000)
    with pytest.raises(T.TraversalError, match="trailing bytes"):
        T.decompress_if_gzip(blob, cap=1000)
    # A single member is still fine, so this is a boundary and not a ban.
    assert T.decompress_if_gzip(gzip.compress(good)) == good


def test_a_truncated_gzip_stream_is_refused():
    good = urlset("https://example.com/a")
    truncated = gzip.compress(good)[:-6]
    with pytest.raises((T.TraversalError, zlib.error)):
        T.decompress_if_gzip(truncated)
