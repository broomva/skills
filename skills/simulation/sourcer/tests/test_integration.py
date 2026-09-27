"""The daemon and the store composed -- the path that actually ships.

Each module's own tests prove its invariants in isolation, which is exactly how
the architectural hole survived: the daemon could prove custody, the store never
asked, and no test exercised the two together. These do.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetchd as F  # noqa: E402
import store as S  # noqa: E402

KEY = b"integration-key"
PAGE = b"ACME S.A.S. appointed Maria Restrepo as CTO in March."


class AllowAll(F.Politeness):
    def __init__(self):
        super().__init__(interval=0.0)

    def allows(self, url):
        return True


@pytest.fixture
def rig(tmp_path):
    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r1", politeness=AllowAll(),
        transport=lambda u: (200, PAGE) if u.endswith("/acme") else (404, b"nope"),
        key=KEY,
    )
    d.seal_plan({"seeds": ["acme"], "max_depth": 2})
    conn = S.connect(tmp_path / "store.db")
    return d, conn


def test_a_real_fetch_becomes_an_observed_record(rig):
    d, conn = rig
    res = d.fetch("https://example.com/acme")
    ev = d.evidence_for(res, 0, 11)
    rec = S.Record(id="acme", kind="node", canonical_key="org::acme", depth=0,
                   layer="L2", origin="observed", evidence=S.Evidence(**ev))
    assert S.put_record(conn, rec, admitter=d) == "inserted"
    S.set_verdict(conn, "acme", "entailed")
    assert S.expandable_ids(conn) == ["acme"]
    assert S.get_record(conn, "acme")["evidence"]["quote"] == "ACME S.A.S."


def test_fabricated_evidence_cannot_enter_the_store(rig):
    """The end-to-end statement of the whole architecture."""
    d, conn = rig
    d.fetch("https://example.com/acme")

    forged = b"ACME S.A.S. was founded by someone who does not exist"
    digest = F.sha256_of(forged)
    (d.snapshots / digest).write_bytes(forged)   # self-consistent by every hash check

    rec = S.Record(
        id="fake", kind="node", canonical_key="org::fake", depth=1, layer="L2",
        origin="observed",
        evidence=S.Evidence(url="https://example.com/acme", sha256=digest,
                            snapshot=f"snapshots/{digest}", span_start=0,
                            span_end=11, quote="ACME S.A.S."),
    )
    with pytest.raises(S.StoreError, match="do not say what this record quotes"):
        S.put_record(conn, rec, admitter=d)
    assert S.inventory(conn)["total"] == 0


def test_a_tampered_log_blocks_ingestion_entirely(rig):
    """A broken chain is not a per-pair problem; nothing may enter."""
    d, conn = rig
    res = d.fetch("https://example.com/acme")
    with d.log.open("a") as fh:
        fh.write('{"kind":"fetch","url":"u","sha256":"z","seq":99,"mac":"x"}\n')

    rec = S.Record(id="acme", kind="node", canonical_key="org::acme", depth=0,
                   layer="L2", origin="observed",
                   evidence=S.Evidence(url=res.url, sha256=res.sha256,
                                       snapshot=res.snapshot, span_start=0,
                                       span_end=11, quote="ACME S.A.S."))
    with pytest.raises(F.ChainBroken):
        S.put_record(conn, rec, admitter=d)


def test_a_404_cannot_become_evidence_end_to_end(rig):
    d, conn = rig
    res = d.fetch("https://example.com/missing")
    with pytest.raises(F.FetchError, match="not a page"):
        d.evidence_for(res, 0, 3)
