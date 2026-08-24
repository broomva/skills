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


def daemon(tmp_path, pages=None, allow=True, key=KEY, seal=True):
    """A daemon with its plan already sealed, which is the normal state.

    `seal=False` is for the tests that assert fetching before sealing is refused.
    """
    pages = pages or {"https://example.com/a": (200, b"ACME S.A.S. hires a CTO")}

    def transport(url):
        return pages.get(url, (404, b"not found"))

    d = F.FetchDaemon(
        root=tmp_path, run_id="r1", politeness=FakeRobots(allow=allow),
        transport=transport, key=key,
    )
    if seal:
        d.seal_plan({"seeds": ["acme"], "max_depth": 2})
    return d


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
    """A key beside the log is readable by whatever can read the log.

    Checks the raw bytes AND the encodings a leak actually takes. The first
    version compared raw bytes only, so review wrote key.hex() into every log row
    and the guard passed while the chain secret was fully recoverable from the run
    directory -- the leak that matters is almost never the literal bytes.
    """
    import base64

    d = daemon(tmp_path)
    d.fetch("https://example.com/a")
    forms = {
        "raw": KEY,
        "hex": KEY.hex().encode(),
        "hex-upper": KEY.hex().upper().encode(),
        "b64": base64.b64encode(KEY),
        "b64-nopad": base64.b64encode(KEY).rstrip(b"="),
        "b32": base64.b32encode(KEY),
        "utf8": KEY.decode("utf-8", errors="ignore").encode(),
    }
    for p in d.dir.rglob("*"):
        if not p.is_file():
            continue
        blob = p.read_bytes()
        for label, form in forms.items():
            if form:
                assert form not in blob, f"chain key leaked as {label} into {p.name}"


# ----------------------------------------------------------------- chaining


def test_chain_verifies_and_counts_rows(tmp_path):
    d = daemon(tmp_path)
    d.fetch("https://example.com/a")
    ok, reason = F.verify_chain(d.log, KEY)
    assert ok and "2 rows" in reason


def test_editing_a_row_breaks_the_chain(tmp_path):
    d = daemon(tmp_path)
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
    d = daemon(tmp_path)          # daemon() seals on construction
    with pytest.raises(F.FetchError, match="already exists"):
        d.seal_plan({"seeds": ["acme"], "max_depth": 99})


def test_genesis_commits_to_the_plan_digest(tmp_path):
    d = daemon(tmp_path, seal=False)
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
    real = d.fetch("https://example.com/a")
    assert d.attests(real.url, real.sha256), "warms the cache"

    with d.log.open("a") as fh:
        fh.write('{"kind":"fetch","url":"u","sha256":"z","mac":"nope"}\n')
    with pytest.raises(F.ChainBroken):
        d.attests(real.url, real.sha256)


def test_every_public_check_has_a_caller():
    """Structural guard against the defect class, not just this instance.

    Counts real CALL SITES via the AST. The first version counted raw substrings,
    so review deleted the only call to usable_as_evidence and the guard still
    passed -- the `def` line and a docstring mention summed to two. A gate its own
    producer trivially satisfies verifies nothing, and this one was about exactly
    that failure mode while exhibiting it.
    """
    import ast

    src = (Path(__file__).resolve().parents[1] / "scripts" / "fetchd.py").read_text()
    tree = ast.parse(src)
    called: dict[str, int] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name:
                called[name] = called.get(name, 0) + 1
    for fn in ("verify_chain", "usable_as_evidence", "chain_ok", "open_attested"):
        assert called.get(fn, 0) >= 1, (
            f"{fn} has {called.get(fn, 0)} call sites in fetchd.py -- defined and "
            "never called, which is an absent check rather than a weak one"
        )


# ------------------------------- evidence construction goes through the check


def test_evidence_for_refuses_a_404_body(tmp_path):
    """Binds usable_as_evidence to a caller: the extractor cannot skip it."""
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/missing")
    with pytest.raises(F.FetchError, match="not a page"):
        d.evidence_for(res, 0, 3)


def test_evidence_for_refuses_an_empty_payload(tmp_path):
    d = daemon(tmp_path, pages={"https://example.com/e": (200, b"")})
    res = d.fetch("https://example.com/e")
    with pytest.raises(F.FetchError, match="zero bytes"):
        d.evidence_for(res, 0, 1)


def test_evidence_for_refuses_a_span_past_the_artifact(tmp_path):
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")
    with pytest.raises(F.FetchError, match="runs past the artifact"):
        d.evidence_for(res, 0, 100_000)


def test_evidence_for_refuses_an_inverted_or_empty_span(tmp_path):
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")
    with pytest.raises(F.FetchError, match="empty or inverted"):
        d.evidence_for(res, 5, 5)


def test_evidence_for_refuses_a_whitespace_span(tmp_path):
    d = daemon(tmp_path, pages={"https://example.com/w": (200, b"ACME    \n   CTO")})
    res = d.fetch("https://example.com/w")
    with pytest.raises(F.FetchError, match="whitespace"):
        d.evidence_for(res, 4, 12)


def test_evidence_for_quotes_the_actual_bytes_at_the_offsets(tmp_path):
    """The quote is READ from the artifact, never supplied by the caller.

    A caller-supplied quote is a needle picked after seeing the haystack; reading
    it at the committed offsets means the extractor had to point at a location.
    """
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")   # b"ACME S.A.S. hires a CTO"
    ev = d.evidence_for(res, 0, 11)
    assert ev["quote"] == "ACME S.A.S."
    assert ev["sha256"] == res.sha256


def test_evidence_for_refuses_when_the_chain_is_broken(tmp_path):
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")
    with d.log.open("a") as fh:
        fh.write('{"kind":"fetch","url":"u","sha256":"z","mac":"nope"}\n')
    with pytest.raises(F.ChainBroken):
        d.evidence_for(res, 0, 4)


# --------------------------------- truncation and forgery (BLOCKER, codex)


def test_truncating_the_log_is_detected(tmp_path):
    """Every surviving row still chains; only the head sidecar disagrees.

    Without it a run that lost its tail verified as a complete one -- the
    chain proves rows were not EDITED, and says nothing about rows removed
    from the end.
    """
    d = daemon(tmp_path)
    d.fetch("https://example.com/a")
    d.fetch("https://example.com/missing")

    lines = d.log.read_text().splitlines()
    d.log.write_text("\n".join(lines[:-1]) + "\n")

    ok, reason = F.verify_chain(d.log, KEY)
    assert not ok and "truncated" in reason


def test_a_log_without_genesis_does_not_verify(tmp_path):
    d = daemon(tmp_path)
    d.fetch("https://example.com/a")
    lines = d.log.read_text().splitlines()
    d.log.write_text("\n".join(lines[1:]) + "\n")
    ok, reason = F.verify_chain(d.log, KEY)
    assert not ok and ("genesis" in reason or "seq" in reason)


def test_rows_carry_contiguous_sequence_numbers(tmp_path):
    d = daemon(tmp_path)
    d.fetch("https://example.com/a")
    seqs = [json.loads(ln)["seq"] for ln in d.log.read_text().splitlines() if ln.strip()]
    assert seqs == list(range(len(seqs)))


def test_a_caller_supplied_status_cannot_launder_a_404(tmp_path):
    """MAJOR (codex): usable_as_evidence trusted the argument, not the log.

    Fetch a url as 404, then hand evidence_for a FetchResult claiming 200 for
    the same (url, digest). The receipt is now read back out of the chained log,
    so the caller's assertion is not what gets checked.
    """
    d = daemon(tmp_path)
    real = d.fetch("https://example.com/missing")
    assert real.status == 404

    laundered = F.FetchResult(
        url=real.url, sha256=real.sha256, snapshot=real.snapshot,
        status=200, tool="urllib", retrieved_at=real.retrieved_at,
        n_bytes=max(real.n_bytes, 100),
    )
    with pytest.raises(F.FetchError, match="not a page"):
        d.evidence_for(laundered, 0, 3)


# --------------------------------------------- robots fails closed (codex)


def test_robots_failure_is_not_permission(tmp_path):
    """A parser defect or network error used to read as 'crawling allowed'."""
    class Exploding(F.Politeness):
        def __init__(self):
            super().__init__(interval=0.0)
        def _read(self, rp):
            raise RuntimeError("parser blew up")

    p = F.Politeness(interval=0.0)
    import urllib.robotparser as rparser
    orig = rparser.RobotFileParser.read
    rparser.RobotFileParser.read = lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        assert p.allows("https://example.com/a") is False
    finally:
        rparser.RobotFileParser.read = orig


# ---------------------- the quote is finally checked (BLOCKER, adjudicator)


def test_evidence_reads_from_the_digest_not_the_caller_s_path(tmp_path):
    """evidence_for dereferenced res.snapshot -- the field it argued not to trust.

    A real url, a real digest and snapshot="authored.bin" returned a quote from
    the caller's own file, wearing a genuine attestation.
    """
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")          # b"ACME S.A.S. hires a CTO"
    (d.dir / "authored.bin").write_bytes(b"ACME S.A.S. was founded by Nobody McFake")

    spoof = F.FetchResult(url=res.url, sha256=res.sha256, snapshot="authored.bin",
                          status=200, tool="urllib", retrieved_at=res.retrieved_at,
                          n_bytes=res.n_bytes)
    ev = d.evidence_for(spoof, 0, 11)
    assert ev["quote"] == "ACME S.A.S.", "read from the attested bytes"
    assert ev["snapshot"] == f"snapshots/{res.sha256}", "path derived from the digest"


def test_evidence_ignores_a_traversing_snapshot_path(tmp_path):
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")
    (tmp_path / "OUTSIDE.txt").write_bytes(b"anything at all outside the run")
    spoof = F.FetchResult(url=res.url, sha256=res.sha256, snapshot="../../OUTSIDE.txt",
                          status=200, tool="urllib", retrieved_at=res.retrieved_at,
                          n_bytes=res.n_bytes)
    ev = d.evidence_for(spoof, 0, 11)
    assert ev["quote"] == "ACME S.A.S."


def test_verifies_rejects_a_quote_the_bytes_do_not_support(tmp_path):
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")
    assert d.verifies(res.url, res.sha256, 0, 11, "ACME S.A.S.") is True
    assert d.verifies(res.url, res.sha256, 0, 11,
                      "ACME S.A.S. is controlled by the Sinaloa Cartel") is False


def test_verifies_is_false_for_an_unattested_digest(tmp_path):
    d = daemon(tmp_path)
    d.fetch("https://example.com/a")
    assert d.verifies("https://example.com/a", "c" * 64, 0, 4, "ACME") is False


def test_verifies_raises_rather_than_returning_false_on_a_broken_chain(tmp_path):
    """Fatal not falsy -- the rule attests() follows, which verifies() first broke."""
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")
    with d.log.open("a") as fh:
        fh.write('{"kind":"fetch","url":"u","sha256":"z","seq":9,"mac":"nope"}\n')
    with pytest.raises(F.ChainBroken):
        d.verifies(res.url, res.sha256, 0, 11, "ACME S.A.S.")


def test_a_snapshot_replaced_after_the_fetch_is_caught(tmp_path):
    d = daemon(tmp_path)
    res = d.fetch("https://example.com/a")
    (d.snapshots / res.sha256).write_bytes(b"swapped out afterwards")
    with pytest.raises(F.FetchError, match="replaced after the fetch"):
        d.open_attested(res.url, res.sha256)


def test_the_head_sidecar_cannot_be_forged_without_the_key(tmp_path):
    """Truncate, then copy {mac, rows} from the last surviving row.

    The sidecar was plain metadata -- the one component of a deliberately keyed
    chain a keyless adversary could rewrite.
    """
    d = daemon(tmp_path)
    d.fetch("https://example.com/a")
    d.fetch("https://example.com/missing")

    lines = [ln for ln in d.log.read_text().splitlines() if ln.strip()]
    d.log.write_text("\n".join(lines[:-1]) + "\n")
    surviving = json.loads(lines[-2])
    F._head_path(d.log).write_text(
        json.dumps({"mac": surviving["mac"], "rows": len(lines) - 1}, sort_keys=True) + "\n"
    )
    ok, reason = F.verify_chain(d.log, KEY)
    assert not ok and "not authentic" in reason
