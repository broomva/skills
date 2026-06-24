"""Sync client — queue, dry-run preview, opt-in guard, merge, and a push/pull round-trip."""
import http.server
import json
import threading

import anonymize
import knowledge
import pytest
import sync


def test_enqueue_and_dry_run(swapit_home):
    sync.enqueue(anonymize.product_fact(product_name="X", item_class="cling-film-pvc"))
    preview = sync.dry_run()
    assert len(preview) == 1 and preview[0]["clean"] is True


def test_enqueue_rejects_dirty_fact(swapit_home):
    with pytest.raises(anonymize.PrivacyError):
        sync.enqueue({"kind": "product", "payload": {"room": "kitchen"}})


def test_push_pull_requires_optin(swapit_home):
    with pytest.raises(RuntimeError):
        sync.push_pull()


def test_configure(swapit_home):
    cfg = sync.configure(endpoint="http://example", token="t", opt_in=True)
    assert cfg["opt_in"] is True and cfg["endpoint"] == "http://example"


def test_merge_incoming_product_and_alternative(swapit_home):
    prod = anonymize.product_fact(product_name="CommunityWrap", item_class="cling-film-pvc", observed_hazards=["phthalates"])
    prod["corroboration_count"] = 3
    alt = anonymize.alternative_fact(name="Hemp wrap", replaces=["cling-film-pvc"], avoids_hazards=["phthalates"], material="hemp", rationale="inert")
    merged = sync.merge_incoming([prod, alt])
    assert merged == 2
    kn = knowledge.Knowledge()
    assert any(p["name"] == "CommunityWrap" for p in kn.products.values())
    assert any(a["name"] == "Hemp wrap" for a in kn.alternatives.values())


def test_merge_incoming_hazard_edge(swapit_home):
    # add a brand-new hazard edge to an item-class that didn't have it
    fact = anonymize.hazard_presence_fact(item_class="plastic-storage-bin", hazard_id="bpa", presence_likelihood=0.3, rationale="community report")
    fact["corroboration_count"] = 2
    sync.merge_incoming([fact])
    kn = knowledge.Knowledge()
    edges = [e["hazard_id"] for e in kn.item_class("plastic-storage-bin")["hazards"]]
    assert "bpa" in edges


def test_merge_skips_unresolvable_refs_and_selfheal_stays_clean(swapit_home):
    import selfheal

    bad_alt = anonymize.alternative_fact(name="Bogus", replaces=["does-not-exist"], avoids_hazards=["bpa"], material="x", rationale="y")
    bad_haz = anonymize.hazard_presence_fact(item_class="no-such-class", hazard_id="bpa", presence_likelihood=0.5, rationale="z")
    assert sync.merge_incoming([bad_alt, bad_haz]) == 0  # both skipped
    assert [f for f in selfheal.run() if f["severity"] == "error"] == []  # no broken edges written


def test_merge_never_lowers_existing_hazard(swapit_home):
    kn = knowledge.Knowledge()
    before = next(e["presence_likelihood"] for e in kn.item_class("nonstick-cookware")["hazards"] if e["hazard_id"] == "ptfe")
    attack = anonymize.hazard_presence_fact(item_class="nonstick-cookware", hazard_id="ptfe", presence_likelihood=0.0, rationale="suppress")
    attack["corroboration_count"] = 5
    sync.merge_incoming([attack])
    after = next(e["presence_likelihood"] for e in knowledge.Knowledge().item_class("nonstick-cookware")["hazards"] if e["hazard_id"] == "ptfe")
    assert after == before  # community input can never suppress a safety warning


def test_merge_tolerates_malformed_numbers_from_server(swapit_home):
    # a hostile / compromised commons returns bad numeric fields — must not crash the merge
    bad = {
        "id": "fact_bad",
        "kind": "item_class_hazard",
        "payload": {"item_class": "plastic-storage-bin", "hazard_id": "bpa", "presence_likelihood": "NOT-A-NUMBER", "confidence": "x"},
    }
    merged = sync.merge_incoming([bad])  # must not raise
    assert merged == 1  # applied with safe defaults rather than crashing


def test_merge_can_raise_hazard(swapit_home):
    raise_fact = anonymize.hazard_presence_fact(item_class="plastic-storage-bin", hazard_id="microplastics", presence_likelihood=0.99, rationale="raise")
    sync.merge_incoming([raise_fact])
    pl = next(e["presence_likelihood"] for e in knowledge.Knowledge().item_class("plastic-storage-bin")["hazards"] if e["hazard_id"] == "microplastics")
    assert pl == 0.99


def test_push_pull_quarantines_server_rejected(swapit_home):
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 — reject everything (422)
            self.send_response(422)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):  # noqa: N802
            data = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *a):  # noqa: A002
            return

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        sync.configure(endpoint=f"http://127.0.0.1:{srv.server_address[1]}", opt_in=True)
        sync.enqueue(anonymize.product_fact(product_name="Q", item_class="cling-film-pvc"))
        res = sync.push_pull()
        assert res["pushed"] == 0 and res["rejected"] == 1
        assert sync.queued() == []  # not stuck in the queue forever
    finally:
        srv.shutdown()


def test_push_pull_roundtrip(swapit_home):
    received = []

    class H(http.server.BaseHTTPRequestHandler):
        def _ok(self, obj):
            data = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length", 0))
            received.append(json.loads(self.rfile.read(n)))
            self._ok({"ok": True})

        def do_GET(self):  # noqa: N802
            self._ok(received)  # echo posted facts back as "incoming"

        def log_message(self, format, *a):  # noqa: A002
            return

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        sync.configure(endpoint=f"http://127.0.0.1:{srv.server_address[1]}", opt_in=True)
        sync.enqueue(anonymize.product_fact(product_name="Z", item_class="cling-film-pvc"))
        res = sync.push_pull()
        assert res["pushed"] == 1
        assert received and received[0]["payload"]["product_name"] == "Z"
        assert sync.queued() == []  # queue cleared after push
        assert sync.load_config()["last_sync"] is not None
    finally:
        srv.shutdown()
