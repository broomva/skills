"""Knowledge graph: seed loads and every edge resolves (no dangling references)."""
import knowledge


def test_seed_counts(swapit_home):
    kn = knowledge.Knowledge()
    s = kn.stats()
    assert s["hazards"] >= 20
    assert s["item_classes"] >= 40
    assert s["alternatives"] >= 40


def test_every_hazard_edge_resolves(swapit_home):
    kn = knowledge.Knowledge()
    for c in kn.item_classes.values():
        for edge in c.get("hazards", []):
            assert edge["hazard_id"] in kn.hazards, f"{c['id']} -> {edge['hazard_id']}"


def test_every_alternative_edge_resolves(swapit_home):
    kn = knowledge.Knowledge()
    for a in kn.alternatives.values():
        for cid in a.get("replaces", []):
            assert cid in kn.item_classes, f"{a['id']} replaces unknown {cid}"
        for hid in a.get("avoids_hazards", []):
            assert hid in kn.hazards, f"{a['id']} avoids unknown {hid}"


def test_every_item_class_has_a_swap_path(swapit_home):
    kn = knowledge.Knowledge()
    covered = {cid for a in kn.alternatives.values() for cid in a.get("replaces", [])}
    missing = set(kn.item_classes) - covered
    assert not missing, f"item-classes with no alternative: {missing}"


def test_every_record_is_grounded(swapit_home):
    kn = knowledge.Knowledge()
    for pool in (kn.hazards, kn.item_classes, kn.alternatives):
        for rec in pool.values():
            assert rec.get("sources"), f"{rec['id']} has no source citation"


def test_hazards_for_class_carries_edge_data(swapit_home):
    kn = knowledge.Knowledge()
    hz = kn.hazards_for_class("nonstick-cookware")
    assert hz
    assert all("presence_likelihood" in h and "rationale" in h for h in hz)


def test_alternatives_for_class(swapit_home):
    kn = knowledge.Knowledge()
    alts = {a["id"] for a in kn.alternatives_for_class("nonstick-cookware")}
    assert "cast-iron-skillet" in alts


def test_search(swapit_home):
    kn = knowledge.Knowledge()
    assert any(r["id"] == "bpa" for r in kn.search("bisphenol"))
