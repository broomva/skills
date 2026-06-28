"""Privacy boundary contract (the M1->M3 invariant).

These tests lock the contract that the M3 anonymizer is built against: which fields are
private, which are shareable, and that the two sets never overlap. The single most
important assertion is that the free-text ``name`` field is private.
"""
import state


def test_name_is_private():
    # name is free text and the field most likely to carry identifying detail
    assert "name" in state.PRIVATE_FIELDS


def test_core_identifying_fields_are_private():
    for field in (
        "room", "quantity", "brand", "acquired", "notes", "photos",
        "cost", "vendor", "url", "title", "checklist", "bookmarks",
    ):
        assert field in state.PRIVATE_FIELDS, f"{field} must be private"


def test_usage_container_is_not_blanket_private():
    # usage sub-keys are the non-identifying signal that drives risk — they must be
    # contributable, so the container is not on the denylist
    assert "usage" not in state.PRIVATE_FIELDS


def test_shareable_usage_signal_defined():
    for field in ("frequency", "food_contact", "heat", "child_contact"):
        assert field in state.SHAREABLE_USAGE_FIELDS


def test_allowlist_and_denylist_are_disjoint():
    assert state.SHAREABLE_ITEM_FIELDS.isdisjoint(state.PRIVATE_FIELDS)
    assert state.SHAREABLE_USAGE_FIELDS.isdisjoint(state.PRIVATE_FIELDS)


def test_item_schema_keys_are_classified(swapit_home):
    """Every key an item carries is either shareable or private — no unclassified leak."""
    import swapit

    swapit.main(["add", "--name", "x", "--class", "nonstick-cookware", "--room", "kitchen"])
    item = next(iter(state.load_items().values()))
    classified = state.PRIVATE_FIELDS | state.SHAREABLE_ITEM_FIELDS | {
        "id", "item_class", "status", "created", "updated", "product_ref", "usage",
    }
    unclassified = set(item) - classified
    assert not unclassified, f"unclassified item fields (privacy review needed): {unclassified}"
