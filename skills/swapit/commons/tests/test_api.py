"""swapit-commons API — submit/corroborate/serve + privacy backstop."""


def _fact(fid, kind="product", **payload):
    base = {"product_name": "Wrap", "item_class": "cling-film-pvc", "confidence": 0.5}
    base.update(payload)
    return {"id": fid, "kind": kind, "payload": base}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_post_high_confidence_is_approved_and_served(client):
    f = _fact("fact_a", confidence=0.8)
    r = client.post("/facts", json=f)
    assert r.status_code == 200
    body = r.json()
    assert body["corroboration_count"] == 1 and body["status"] == "approved"
    assert any(x["id"] == "fact_a" for x in client.get("/facts").json())


def test_low_confidence_pending_until_corroborated(client):
    f = _fact("fact_b", kind="item_class_hazard", item_class="plastic-toothbrush", hazard_id="microplastics", confidence=0.4)
    r1 = client.post("/facts", json=f, headers={"X-Anon-Token": "tok-1"})
    assert r1.json()["status"] == "pending"
    assert client.get("/facts").json() == []  # pending facts are not served

    r2 = client.post("/facts", json=f, headers={"X-Anon-Token": "tok-2"})
    body = r2.json()
    assert body["corroboration_count"] == 2
    assert body["status"] == "approved"
    assert body["contributor_count"] == 2  # two distinct (hashed) tokens
    assert any(x["id"] == "fact_b" for x in client.get("/facts").json())


def test_same_token_does_not_double_count_contributors(client):
    f = _fact("fact_b2", kind="item_class_hazard", item_class="plastic-toothbrush", hazard_id="microplastics", confidence=0.4)
    client.post("/facts", json=f, headers={"X-Anon-Token": "same"})
    body = client.post("/facts", json=f, headers={"X-Anon-Token": "same"}).json()
    assert body["corroboration_count"] == 2 and body["contributor_count"] == 1


def test_rejects_forbidden_inventory_fields(client):
    f = _fact("fact_c", item_class="x", room="kitchen", quantity=3)
    r = client.post("/facts", json=f)
    assert r.status_code == 422


def test_rejects_unknown_kind(client):
    r = client.post("/facts", json={"id": "fact_d", "kind": "bogus", "payload": {}})
    assert r.status_code == 400


def test_since_filter_excludes_old(client):
    client.post("/facts", json=_fact("fact_e", confidence=0.8))
    assert client.get("/facts?since=2999-01-01T00:00:00Z").json() == []


def test_corroboration_keeps_first_seen_payload(client):
    # an attacker corroborates a benign fact while swapping its payload (strip hazards)
    client.post("/facts", json=_fact("fact_swap", observed_hazards=["bpa"], confidence=0.4), headers={"X-Anon-Token": "a"})
    body = client.post("/facts", json=_fact("fact_swap", observed_hazards=[], confidence=0.4), headers={"X-Anon-Token": "b"}).json()
    assert body["corroboration_count"] == 2
    assert body["payload"]["observed_hazards"] == ["bpa"]  # first-seen payload preserved


def test_oversized_payload_rejected(client):
    r = client.post("/facts", json=_fact("fact_big", product_name="x" * 40000))
    assert r.status_code == 413
