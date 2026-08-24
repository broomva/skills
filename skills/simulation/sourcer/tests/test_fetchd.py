"""Tests for the fetch daemon.

The point of this module is a claim the rest of sourcer leans on: that bytes in
the store came off a wire. So the tests that matter are the ones that try to get
authored bytes accepted, and the one that proves the gap in `verify_snapshot`
this daemon exists to close.

No test here touches the network. The transport is injected -- which does not
weaken the invariants, because a test transport can return bad bytes but cannot
make the daemon record them as good.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetchd as F  # noqa: E402

KEY = b"test-chain-key"


class FakeRobots(F.Politeness):
    def __init__(self, allow=True, interval=0.0):
        super().__init__(interval=interval)
        self._allow = allow

    def allows(self, url):
        return self._allow


def daemon(tmp_path, pages=None, allow=True, key=KEY):
    pages = pages or {"https://example.com/a": (200, b"ACME S.A.S. hires a CTO")}

    def transport(url):
        return pages.get(url, (404, b"not found"))

    return F.FetchDaemon(
        root=tmp_path, run_id="r1", politeness=FakeRobots(allow=allow),
        transport=transport, key=key,
    )


# ------------------------------------------------------- content addressing


def test_snapshot_filename_is_the_content_hash(tmp_path):
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")
    stored = (d.dir / res.snapshot).read_bytes()
    assert F.sha256_of(stored) == res.sha256
    assert Path(res.snapshot).name == res.sha256, "the name IS the digest"


def test_same_bytes_twice_is_dedup_not_a_race(tmp_path):
    """Two workers fetching one page must not be a write conflict."""
    d = daemon(tmp_path)
    a = d.fetch("https://example.com/a")
    b = d.fetch("https://example.com/a")
    assert a.sha256 == b.sha256
    assert len(list(d.snapshots.iterdir())) == 1


# ----------------------------------------------------------- the key itself


def test_missing_chain_key_is_a_refusal_not_a_default(tmp_path, monkeypatch):
    """An unkeyed chain verifies and proves nothing -- the vacuous-gate shape."""
    monkeypatch.delenv(F.CHAIN_KEY_ENV, raising=False)
    with pytest.raises(F.FetchError, match="is unset"):
        F.FetchDaemon(root=tmp_path, run_id="r1")


def test_key_is_never_written_into_the_run_directory(tmp_path):
    """A key stored beside the log is readable by whatever can read the log."""
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"], "max_depth": 2})
    d.fetch("https://example.com/a")
    for p in d.dir.rglob("*"):
        if p.is_file():
            assert KEY not in p.read_bytes(), f"chain key leaked into {p.name}"


# ----------------------------------------------------------------- chaining


def test_chain_verifies_and_counts_rows(tmp_path):
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    d.fetch("https://example.com/a")
    ok, reason = F.verify_chain(d.log, KEY)
    assert ok and "2 rows" in reason


def test_editing_a_row_breaks_the_chain(tmp_path):
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    d.fetch("https://example.com/a")

    lines = d.log.read_text().splitlines()
    row = json.loads(lines[-1])
    row["url"] = "https://example.com/somewhere-else"
    lines[-1] = json.dumps(row, sort_keys=True)
    d.log.write_text("\n".join(lines) + "\n")

    ok, reason = F.verify_chain(d.log, KEY)
    assert not ok and "mac mismatch" in reason


def test_a_reader_without_the_key_cannot_forge_a_row(tmp_path):
    """The whole reason the chain is keyed rather than a plain hash."""
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    d.fetch("https://example.com/a")

    # An attacker who can READ the log appends a plausible row, recomputing the
    # chain the only way it can -- with a key it does not have.
    F.append_row(d.log, {"kind": "fetch", "url": "https://evil/x",
                         "sha256": "0" * 64}, key=b"guessed-key")
    ok, reason = F.verify_chain(d.log, KEY)
    assert not ok and "mac mismatch" in reason


def test_empty_chain_does_not_verify_vacuously(tmp_path):
    d = daemon(tmp_path)
    d.log.parent.mkdir(parents=True, exist_ok=True)
    d.log.write_text("")
    ok, reason = F.verify_chain(d.log, KEY)
    assert not ok and "vacuous" in reason


# ------------------------------------------------------------- sealed plan


def test_plan_is_sealed_once(tmp_path):
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"], "max_depth": 2})
    with pytest.raises(F.FetchError, match="already exists"):
        d.seal_plan({"seeds": ["acme"], "max_depth": 99})


def test_genesis_commits_to_the_plan_digest(tmp_path):
    d = daemon(tmp_path)
    digest = d.seal_plan({"seeds": ["acme"], "max_depth": 2})
    genesis = json.loads(d.log.read_text().splitlines()[0])
    assert genesis["kind"] == "genesis"
    assert genesis["plan_digest"] == digest
    assert F.sha256_of((d.dir / "plan.json").read_bytes()) == digest


# -------------------------------------------------------------- politeness


def test_robots_disallow_is_a_refusal(tmp_path):
    d = daemon(tmp_path, allow=False)
    with pytest.raises(F.RobotsRefusal):
        d.fetch("https://example.com/a")
    assert not d.log.exists() or d.pairs() == set()


def test_per_host_interval_waits_out_only_the_remaining_gap():
    """A second request 0.5s after the first, under a 2s floor, waits 1.5s."""
    slept: list[float] = []
    p = FakeRobots(interval=2.0)
    # (call 1) now=0.0, no prior -> no wait, stamp 0.0
    # (call 2) now=0.5, gap 0.5 < 2.0 -> wait the remaining 1.5, stamp 10.0
    ticks = iter([0.0, 0.0, 0.5, 10.0])
    p.wait("https://example.com/a", sleeper=slept.append, clock=lambda: next(ticks))
    assert slept == [], "the first request to a host never waits"
    p.wait("https://example.com/b", sleeper=slept.append, clock=lambda: next(ticks))
    assert slept == [pytest.approx(1.5)]


def test_first_contact_with_a_new_host_does_not_wait():
    slept: list[float] = []
    p = FakeRobots(interval=2.0)
    ticks = iter([0.0, 0.0, 0.1, 0.1])
    p.wait("https://a.example/x", sleeper=slept.append, clock=lambda: next(ticks))
    p.wait("https://b.example/y", sleeper=slept.append, clock=lambda: next(ticks))
    assert slept == [], "the floor is per-host, not global"


# ------------------------------------------- what may be cited as evidence


def test_non_2xx_is_recorded_but_not_usable_as_evidence(tmp_path):
    """A 404 body stored and read as a page is the defect this prevents."""
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/missing")
    assert res.status == 404
    assert d.attests(res.url, res.sha256), "the fetch is still recorded"
    ok, why = d.usable_as_evidence(res)
    assert not ok and "not a page" in why


def test_zero_bytes_is_not_usable_as_evidence(tmp_path):
    """The exact input that makes data-provider's verify_snapshot return True."""
    d = daemon(tmp_path, pages={"https://example.com/empty": (200, b"")})
    res = d.fetch("https://example.com/empty")
    assert res.sha256.startswith("e3b0c442"), "sha256 of the empty string"
    ok, why = d.usable_as_evidence(res)
    assert not ok and "zero bytes" in why


# ----------------------------------------------- custody: the actual claim


def test_authored_bytes_are_not_attested(tmp_path):
    """The gap this module exists to close.

    An agent writes a snapshot by hand whose filename correctly equals its own
    content hash. Every integrity check passes -- the file exists, the digest
    matches. `attests` still refuses it, because no chained log row pairs that
    url with those bytes.
    """
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    d.fetch("https://example.com/a")

    forged = b"ACME S.A.S. was founded by a person who does not exist"
    digest = F.sha256_of(forged)
    (d.snapshots / digest).write_bytes(forged)

    # Self-consistent by every hash-based measure...
    assert F.sha256_of((d.snapshots / digest).read_bytes()) == digest
    # ...and never fetched.
    assert not d.attests("https://example.com/a", digest)
    assert d.attests("https://example.com/a", d.fetch("https://example.com/a").sha256)


def test_url_swap_is_caught_by_the_pair(tmp_path):
    """verify_snapshot returns True for a swapped url; attests does not."""
    d = daemon(tmp_path, pages={
        "https://example.com/a": (200, b"page A"),
        "https://linkedin.com/in/someone": (200, b"page B"),
    })
    a = d.fetch("https://example.com/a")
    assert d.attests("https://example.com/a", a.sha256)
    assert not d.attests("https://linkedin.com/in/someone", a.sha256)


# ------------------------------------- the check that had no caller (BLOCKER)


def test_attests_refuses_when_the_chain_does_not_verify(tmp_path):
    """The defect this pair of tests exists for.

    verify_chain() was correct, tested, and called by NOTHING. attests() read the
    log directly, so a row appended without the key broke the chain and was still
    reported as a genuine fetch -- two individually-right checks that were never
    composed. A check nobody calls is not a weaker check, it is an absent one.
    """
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    real = d.fetch("https://example.com/a")
    assert d.attests(real.url, real.sha256)

    with d.log.open("a") as fh:
        fh.write(json.dumps({"kind": "fetch", "url": "https://evil.example/fake",
                             "sha256": "b" * 64, "mac": "deadbeef"}, sort_keys=True) + "\n")

    with pytest.raises(F.ChainBroken):
        d.attests("https://evil.example/fake", "b" * 64)


def test_a_broken_chain_poisons_every_pair_not_just_the_forged_one(tmp_path):
    """A log that can be edited can be edited to contain any pair."""
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    real = d.fetch("https://example.com/a")

    lines = d.log.read_text().splitlines()
    row = json.loads(lines[-1])
    row["url"] = "https://example.com/elsewhere"
    lines[-1] = json.dumps(row, sort_keys=True)
    d.log.write_text("\n".join(lines) + "\n")

    with pytest.raises(F.ChainBroken):
        d.attests(real.url, real.sha256)


def test_chain_broken_is_fatal_not_falsy(tmp_path):
    """False would say 'not fetched'; the truth is 'this log proves nothing'."""
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    d.fetch("https://example.com/a")
    with d.log.open("a") as fh:
        fh.write('{"kind":"fetch","url":"u","sha256":"z","mac":"nope"}\n')
    try:
        result = d.attests("u", "z")
    except F.ChainBroken:
        return
    pytest.fail(f"returned {result!r} instead of raising -- a caller would read "
                "that as 'never fetched' rather than 'the log is untrustworthy'")


def test_chain_cache_is_invalidated_by_a_write(tmp_path):
    """Memoisation must not hold a stale pass across a tamper."""
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    real = d.fetch("https://example.com/a")
    assert d.attests(real.url, real.sha256), "warms the cache"

    with d.log.open("a") as fh:
        fh.write('{"kind":"fetch","url":"u","sha256":"z","mac":"nope"}\n')
    with pytest.raises(F.ChainBroken):
        d.attests(real.url, real.sha256)


def test_every_public_check_has_a_caller():
    """Structural guard against the defect class, not just this instance.

    The bug was an orphaned check. Assert that each verification helper is
    referenced somewhere beyond its own definition, so the next one that loses
    its caller fails here rather than in production.
    """
    src = (Path(__file__).resolve().parents[1] / "scripts" / "fetchd.py").read_text()
    for fn in ("verify_chain", "usable_as_evidence", "chain_ok"):
        uses = src.count(fn)
        assert uses >= 2, f"{fn} appears {uses}x -- defined and never called"


# ------------------------------- evidence construction goes through the check


def test_evidence_for_refuses_a_404_body(tmp_path):
    """Binds usable_as_evidence to a caller: the extractor cannot skip it."""
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    res = d.fetch("https://example.com/missing")
    with pytest.raises(F.FetchError, match="not a page"):
        d.evidence_for(res, 0, 3)


def test_evidence_for_refuses_an_empty_payload(tmp_path):
    d = daemon(tmp_path, pages={"https://example.com/e": (200, b"")})
    d.seal_plan({"seeds": ["acme"]})
    res = d.fetch("https://example.com/e")
    with pytest.raises(F.FetchError, match="zero bytes"):
        d.evidence_for(res, 0, 1)


def test_evidence_for_refuses_a_span_past_the_artifact(tmp_path):
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    res = d.fetch("https://example.com/a")
    with pytest.raises(F.FetchError, match="runs past the artifact"):
        d.evidence_for(res, 0, 100_000)


def test_evidence_for_refuses_an_inverted_or_empty_span(tmp_path):
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    res = d.fetch("https://example.com/a")
    with pytest.raises(F.FetchError, match="empty or inverted"):
        d.evidence_for(res, 5, 5)


def test_evidence_for_refuses_a_whitespace_span(tmp_path):
    d = daemon(tmp_path, pages={"https://example.com/w": (200, b"ACME    \n   CTO")})
    d.seal_plan({"seeds": ["acme"]})
    res = d.fetch("https://example.com/w")
    with pytest.raises(F.FetchError, match="whitespace"):
        d.evidence_for(res, 4, 12)


def test_evidence_for_quotes_the_actual_bytes_at_the_offsets(tmp_path):
    """The quote is READ from the artifact, never supplied by the caller.

    A caller-supplied quote is a needle picked after seeing the haystack; reading
    it at the committed offsets means the extractor had to point at a location.
    """
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    res = d.fetch("https://example.com/a")   # b"ACME S.A.S. hires a CTO"
    ev = d.evidence_for(res, 0, 11)
    assert ev["quote"] == "ACME S.A.S."
    assert ev["sha256"] == res.sha256


def test_evidence_for_refuses_when_the_chain_is_broken(tmp_path):
    d = daemon(tmp_path)
    d.seal_plan({"seeds": ["acme"]})
    res = d.fetch("https://example.com/a")
    with d.log.open("a") as fh:
        fh.write('{"kind":"fetch","url":"u","sha256":"z","mac":"nope"}\n')
    with pytest.raises(F.ChainBroken):
        d.evidence_for(res, 0, 4)
