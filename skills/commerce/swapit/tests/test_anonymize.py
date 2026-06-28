"""The privacy invariant — inventory never crosses the boundary.

The binding property: a contribution is built only from generic inputs, and the gate
(scan_for_forbidden / assert_clean) rejects anything carrying an inventory-structural
field. The fuzz tests assert that *every* real inventory item would be caught.
"""
import random

import anonymize
import ops
import pytest


def test_product_fact_is_clean():
    f = anonymize.product_fact(
        product_name="Brand X Wrap", item_class="cling-film-pvc", brand="X", gtin="123",
        observed_hazards=["phthalates"], recycling_code="3", label_terms=["PVC"],
    )
    assert anonymize.scan_for_forbidden(f) == []
    assert f["kind"] == "product" and f["payload"]["item_class"] == "cling-film-pvc"


def test_hazard_and_alternative_facts_clean():
    h = anonymize.hazard_presence_fact(item_class="plastic-toothbrush", hazard_id="microplastics", presence_likelihood=0.6, rationale="abrasion")
    a = anonymize.alternative_fact(name="Hemp wrap", replaces=["cling-film-pvc"], avoids_hazards=["phthalates"], material="hemp", rationale="inert")
    assert anonymize.scan_for_forbidden(h) == []
    assert anonymize.scan_for_forbidden(a) == []


def test_content_hash_dedups_identical_facts():
    a = anonymize.product_fact(product_name="X", item_class="cling-film-pvc", gtin="123")
    b = anonymize.product_fact(product_name="X", item_class="cling-film-pvc", gtin="123")
    assert a["id"] == b["id"]  # same content → same id → corroborates, not duplicates


def test_scan_finds_nested_forbidden():
    bad = {"kind": "x", "payload": {"a": {"b": [{"quantity": 3}]}}}
    hits = anonymize.scan_for_forbidden(bad)
    assert any("quantity" in h for h in hits)


def test_assert_clean_rejects_inventory_fields():
    with pytest.raises(anonymize.PrivacyError):
        anonymize.assert_clean({"kind": "product", "payload": {"item_class": "x", "room": "kitchen"}})


def test_real_inventory_item_is_rejected_by_gate(swapit_home):
    item = ops.add_item(name="Grandma's bottle from Berlin", item_class="polycarbonate-bottle", room="kitchen", brand="Acme", quantity=2)
    # a real owned item carries room/quantity/usage — naively contributing it must fail
    with pytest.raises(anonymize.PrivacyError):
        anonymize.assert_clean({"kind": "product", "payload": item})


def test_fuzz_every_inventory_item_would_leak(swapit_home):
    """No matter how an item is shaped, the gate finds an inventory-structural field."""
    rooms = ["kitchen", "bedroom", "garage", "nursery"]
    classes = ["polycarbonate-bottle", "nonstick-cookware", "plastic-storage-bin", "vinyl-shower-curtain"]
    for i in range(150):
        item = ops.add_item(
            name=f"item{i}", item_class=random.choice(classes), room=random.choice(rooms),
            brand=f"brand{i}", quantity=random.randint(1, 5),
            usage={"frequency": random.choice(["daily", "rare", "unused"]), "food_contact": bool(i % 2), "heat": bool(i % 3), "child_contact": False},
        )
        leaks = anonymize.scan_for_forbidden({"payload": item})
        assert leaks, f"inventory item {i} produced no leak signal — gate would wrongly admit it"


def test_fuzz_product_facts_always_clean():
    for i in range(150):
        f = anonymize.product_fact(
            product_name=f"P{i}", item_class="cling-film-pvc", brand=f"B{i % 7}",
            gtin=str(random.randint(0, 10 ** 12)),
            observed_hazards=random.sample(["bpa", "phthalates", "pfas", "dehp"], k=random.randint(0, 3)),
        )
        assert anonymize.scan_for_forbidden(f) == []


def test_usage_dict_and_subkeys_are_blocked():
    # the household-behaviour signal — the drift the prior review caught
    assert anonymize.scan_for_forbidden({"payload": {"usage": {"frequency": "daily"}}})
    assert anonymize.scan_for_forbidden({"payload": {"child_contact": True}})  # flattened sub-key
    with pytest.raises(anonymize.PrivacyError):
        anonymize.assert_clean({"kind": "product", "payload": {"usage": {"child_contact": True}}})


def test_client_server_forbidden_sets_match():
    """The commons server's denylist must never drift from the client's gate."""
    import importlib.util
    from pathlib import Path

    p = Path(__file__).resolve().parent.parent / "commons" / "app" / "privacy.py"
    spec = importlib.util.spec_from_file_location("commons_privacy", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod.FORBIDDEN) == set(anonymize.CONTRIBUTION_FORBIDDEN)


def test_tuple_container_does_not_bypass_gate():
    bad = {"kind": "x", "payload": {"extra": ({"room": "kitchen", "cost": 9},)}}
    with pytest.raises(anonymize.PrivacyError):
        anonymize.assert_clean(bad)


def test_freetext_length_capped():
    with pytest.raises(anonymize.PrivacyError):
        anonymize.product_fact(product_name="x" * 700, item_class="cling-film-pvc")


def test_content_hash_differs_for_different_mapping():
    a = anonymize.product_fact(product_name="X", brand="B", gtin="1", item_class="cling-film-pvc", observed_hazards=["phthalates"])
    b = anonymize.product_fact(product_name="X", brand="B", gtin="1", item_class="plastic-food-container", observed_hazards=["bpa"])
    assert a["id"] != b["id"]  # same name/brand/gtin but different mapping → a different fact
