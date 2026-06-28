"""M4 — procurement commons + taxonomy growth: privacy, hashing, merge, parity.

Two new fact kinds extend the commons:
  * ``procurement_option`` — a public "where to buy" offer (retailer/region/price/url).
  * ``item_class`` — taxonomy growth (a new category, corroboration-gated).

The binding properties tested here:
  * the procurement fact carries NO private purchase data (``vendor``/``cost`` stay forbidden —
    the public fact uses ``retailer`` + ``price_min``/``price_max``);
  * the content-hash key is identity-only ``(alternative, retailer, region)`` so the same offer
    corroborates across users, while a different region is a different fact;
  * merge applies offers + freshens market data forward only, and ADDS new item-classes but
    never overwrites a seed class;
  * the Python id derivation reproduces the pinned cross-language parity vectors byte-for-byte
    (the TS ``computeFactId`` asserts the same vectors — if they ever diverge, corroboration
    silently breaks).
"""
import json
from pathlib import Path

import anonymize
import knowledge
import pytest
import sync


# ----------------------------------------------------------------- privacy + validation
def test_procurement_fact_is_clean_no_vendor_or_cost():
    f = anonymize.procurement_option_fact(
        alternative="cast-iron-skillet", retailer="Lodge", region="US",
        url="https://lodge", price_min=25, price_max=45, currency="USD", as_of="2026-06-01",
    )
    assert anonymize.scan_for_forbidden(f) == []
    assert f["kind"] == "procurement_option"
    # the public offer uses retailer/price_*, NEVER the private vendor/cost
    assert "vendor" not in f["payload"] and "cost" not in f["payload"]
    assert f["payload"]["retailer"] == "Lodge"


def test_vendor_and_cost_remain_forbidden_field_names():
    # even if a buggy caller tried to attach the private purchase record, the gate rejects it
    for leak in ({"vendor": "MyStore"}, {"cost": 30}, {"procurer_report_ref": "x"}):
        with pytest.raises(anonymize.PrivacyError):
            anonymize.assert_clean({"kind": "procurement_option", "payload": {"alternative": "a", "retailer": "r", "region": "US", **leak}})


def test_region_is_validated_and_normalized():
    f = anonymize.procurement_option_fact(alternative="a", retailer="r", region="co")
    assert f["payload"]["region"] == "CO"  # normalized to upper
    for bad in ("USA", "1", "C", ""):
        with pytest.raises(ValueError):
            anonymize.procurement_option_fact(alternative="a", retailer="r", region=bad)


def test_currency_and_price_validation():
    with pytest.raises(ValueError):
        anonymize.procurement_option_fact(alternative="a", retailer="r", region="US", currency="dollars")
    with pytest.raises(ValueError):
        anonymize.procurement_option_fact(alternative="a", retailer="r", region="US", price_min=50, price_max=10)
    with pytest.raises(ValueError):
        anonymize.procurement_option_fact(alternative="a", retailer="r", region="US", price_min=-1)


# ------------------------------------------------------------------- content addressing
def test_hash_key_is_alternative_retailer_region():
    base = dict(alternative="cast-iron-skillet", retailer="Lodge", region="US")
    a = anonymize.procurement_option_fact(**base, price_min=20, url="https://a")
    b = anonymize.procurement_option_fact(**base, price_min=99, url="https://b")  # price/url differ
    assert a["id"] == b["id"]  # same identity → corroborates (price/url are refinable, not key)
    c = anonymize.procurement_option_fact(alternative="cast-iron-skillet", retailer="Lodge", region="CO")
    assert c["id"] != a["id"]  # different region → a different fact (the scale axis)
    d = anonymize.procurement_option_fact(alternative="cast-iron-skillet", retailer="Amazon", region="US")
    assert d["id"] != a["id"]  # different retailer → a different fact


def test_item_class_fact_clean_and_keyed_by_id():
    f = anonymize.item_class_fact(item_class="silicone-bakeware", name="Silicone bakeware", category="kitchen")
    assert anonymize.scan_for_forbidden(f) == []
    g = anonymize.item_class_fact(item_class="silicone-bakeware", name="Different name", category="other")
    assert f["id"] == g["id"]  # keyed by id only → corroborates


# --------------------------------------------------------------------------- parity
def test_python_reproduces_pinned_parity_vectors():
    """Python id derivation must reproduce the pinned vectors that the TS computeFactId also
    asserts. These vectors are duplicated in broomva.tech's content-hash parity test."""
    vectors = json.loads((Path(__file__).resolve().parent / "parity_vectors.json").read_text())

    def key_for(kind, p):
        if kind == "product":
            return {"gtin": p.get("gtin"), "product_name": p.get("product_name"), "brand": p.get("brand"), "item_class": p.get("item_class"), "observed_hazards": sorted(p.get("observed_hazards") or [])}
        if kind == "item_class_hazard":
            return {"item_class": p.get("item_class"), "hazard_id": p.get("hazard_id")}
        if kind == "procurement_option":
            return {"alternative": p.get("alternative"), "retailer": p.get("retailer"), "region": p.get("region")}
        if kind == "item_class":
            return {"item_class": p.get("item_class")}
        return {"name": p.get("name"), "replaces": sorted(p.get("replaces") or []), "avoids_hazards": sorted(p.get("avoids_hazards") or [])}

    for v in vectors:
        got = anonymize._content_hash(v["kind"], key_for(v["kind"], v["payload"]))
        assert got == v["id"], f"{v['kind']} parity drift: {got} != {v['id']}"


# ------------------------------------------------------------------------------ merge
def test_merge_applies_offer_and_freshens_forward(swapit_home):
    older = anonymize.procurement_option_fact(alternative="cast-iron-skillet", retailer="Lodge", region="US", price_min=20, price_max=30, as_of="2026-01-01")
    sync.merge_incoming([older])
    kn = knowledge.Knowledge()
    offers = kn.offers_for_alternative("cast-iron-skillet", "US")
    assert any(o["retailer"] == "Lodge" and o["price_min"] == 20 for o in offers)

    newer = anonymize.procurement_option_fact(alternative="cast-iron-skillet", retailer="Lodge", region="US", price_min=28, price_max=44, as_of="2026-06-01")
    sync.merge_incoming([newer])
    o = knowledge.Knowledge().offers_for_alternative("cast-iron-skillet", "US")[0]
    assert o["price_min"] == 28 and o["as_of"] == "2026-06-01"  # freshened forward

    stale = anonymize.procurement_option_fact(alternative="cast-iron-skillet", retailer="Lodge", region="US", price_min=99, as_of="2025-01-01")
    sync.merge_incoming([stale])
    o = knowledge.Knowledge().offers_for_alternative("cast-iron-skillet", "US")[0]
    assert o["price_min"] == 28, "an older as_of must never regress fresher market data"


def test_merge_skips_offer_for_unknown_alternative(swapit_home):
    f = anonymize.procurement_option_fact(alternative="does-not-exist", retailer="X", region="US")
    sync.merge_incoming([f])
    assert not knowledge.Knowledge().offers_for_alternative("does-not-exist")


def test_merge_adds_new_item_class_but_never_overwrites_seed(swapit_home):
    before = knowledge.Knowledge().item_class("nonstick-cookware")
    assert before is not None
    # attempt to overwrite an existing seed class — must be ignored
    sync.merge_incoming([anonymize.item_class_fact(item_class="nonstick-cookware", name="HIJACKED", category="evil")])
    assert knowledge.Knowledge().item_class("nonstick-cookware")["name"] == before["name"]
    # a genuinely new class is added
    sync.merge_incoming([anonymize.item_class_fact(item_class="silicone-bakeware", name="Silicone bakeware", category="kitchen")])
    added = knowledge.Knowledge().item_class("silicone-bakeware")
    assert added is not None and added["name"] == "Silicone bakeware" and added["source"] == "commons"


def test_offers_region_filter(swapit_home):
    sync.merge_incoming([
        anonymize.procurement_option_fact(alternative="glass-bottle", retailer="IKEA", region="US"),
        anonymize.procurement_option_fact(alternative="glass-bottle", retailer="IKEA", region="DE"),
    ])
    kn = knowledge.Knowledge()
    assert len(kn.offers_for_alternative("glass-bottle", "US")) == 1
    assert len(kn.offers_for_alternative("glass-bottle")) >= 2  # unfiltered sees both


def test_seed_offers_present_and_valid(swapit_home):
    kn = knowledge.Knowledge()
    assert len(kn.procurement) >= 10
    alt_ids = set(kn.alternatives)
    for o in kn.procurement.values():
        assert o["alternative"] in alt_ids, f"seed offer targets unknown alternative {o['alternative']}"
        assert len(o["region"]) == 2 and o["region"].isalpha()


def test_contribution_forbidden_set_unchanged_by_new_kinds():
    # retailer/price_*/region/area/url/as_of/currency are NOT private — the new public fields
    # must not have been added to the forbidden set, while vendor/cost remain forbidden.
    for public in ("retailer", "price_min", "price_max", "region", "area", "as_of", "currency", "availability"):
        assert public not in anonymize.CONTRIBUTION_FORBIDDEN
    for private in ("vendor", "cost"):
        assert private in anonymize.CONTRIBUTION_FORBIDDEN
