"""Risk engine: the swap-first ranking must put high-exposure items on top."""
import knowledge
import risk


def test_food_heat_route_is_maximally_relevant():
    rel = risk.exposure_relevance(
        ["food-contact-heat", "ingestion"],
        {"food_contact": True, "heat": True, "frequency": "daily"},
        "kitchen",
    )
    assert rel == 1.0


def test_unknown_usage_has_baseline_floor():
    assert risk.exposure_relevance(["inhalation"], None, "kitchen") >= 0.15


def test_child_contact_amplifies():
    base = risk.exposure_relevance(["dermal"], {"food_contact": False}, "baby-kids")
    amp = risk.exposure_relevance(["dermal"], {"child_contact": True}, "baby-kids")
    assert amp > base


def test_scratched_daily_pan_outranks_sealed_bin(swapit_home):
    kn = knowledge.Knowledge()
    pan = {"condition": "scratched", "usage": {"frequency": "daily", "food_contact": True, "heat": True}}
    bin_ = {"condition": "sealed", "usage": {"frequency": "unused", "food_contact": False, "heat": False}}
    pan_r = risk.score_item(pan, kn.hazards_for_class("nonstick-cookware"), "kitchen")
    bin_r = risk.score_item(bin_, kn.hazards_for_class("plastic-storage-bin"), "misc")
    assert pan_r["score"] > bin_r["score"]
    assert pan_r["band"] == "high"
    assert bin_r["band"] == "low"


def test_condition_increases_risk(swapit_home):
    kn = knowledge.Knowledge()
    hz = kn.hazards_for_class("nonstick-cookware")
    good = risk.score_item({"condition": "good", "usage": {"frequency": "daily", "heat": True, "food_contact": True}}, hz, "kitchen")
    scratched = risk.score_item({"condition": "scratched", "usage": {"frequency": "daily", "heat": True, "food_contact": True}}, hz, "kitchen")
    assert scratched["raw"] > good["raw"]


def test_reduction_for_alternative_full_removal(swapit_home):
    kn = knowledge.Knowledge()
    pan = {"condition": "scratched", "usage": {"frequency": "daily", "food_contact": True, "heat": True}}
    pr = risk.score_item(pan, kn.hazards_for_class("nonstick-cookware"), "kitchen")
    red = risk.reduction_for_alternative(pr, kn.alternative("cast-iron-skillet"))
    assert red["pct"] == 100  # cast iron avoids both ptfe and pfas


def test_contributions_sorted_descending(swapit_home):
    kn = knowledge.Knowledge()
    r = risk.score_item(
        {"condition": "good", "usage": {"frequency": "daily", "food_contact": True}},
        kn.hazards_for_class("plastic-food-container"),
        "food-packaging",
    )
    risks = [c["risk"] for c in r["contributions"]]
    assert risks == sorted(risks, reverse=True)
