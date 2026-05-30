"""Interceptor driver tests — the pure tree parser + ref resolver.

The real InterceptorDriver shells out to a browser CLI and is exercised only by
the live dogfood. These tests cover the deterministic parsing logic that turns
the compact accessibility tree into actionable refs.
"""

from __future__ import annotations

from tradingview_bridge.interceptor_driver import Element, find_ref, parse_elements

# Shape captured from the live spike against TradingView.
SAMPLE_TREE = """
>0 [e21|button|Trade]
>1 [e22|button|Share your idea with the trade community]
>2 [e31|button|Long position]
>3 [e40|spinbutton|Quantity|value=100]
>4 [e41|button|Buy 3667.7]
>5 [e42|button|Sell 3665.7]
"""


def test_parse_elements_extracts_ref_role_name() -> None:
    els = parse_elements(SAMPLE_TREE)
    assert Element("e21", "button", "Trade") in els
    assert Element("e31", "button", "Long position") in els


def test_parse_elements_strips_trailing_attrs() -> None:
    els = parse_elements(SAMPLE_TREE)
    qty = next(e for e in els if e.ref == "e40")
    assert qty.role == "spinbutton"
    assert qty.name == "Quantity"  # the |value=100 attr is dropped from name


def test_find_ref_substring_default() -> None:
    assert find_ref(SAMPLE_TREE, "button", "Trade") == "e21"
    # "Buy" matches "Buy 3667.7" by substring
    assert find_ref(SAMPLE_TREE, "button", "Buy") == "e41"
    assert find_ref(SAMPLE_TREE, "button", "Sell") == "e42"


def test_find_ref_case_insensitive() -> None:
    assert find_ref(SAMPLE_TREE, "button", "trade") == "e21"


def test_find_ref_exact() -> None:
    # exact: "Buy" != "Buy 3667.7"
    assert find_ref(SAMPLE_TREE, "button", "Buy", exact=True) is None
    assert find_ref(SAMPLE_TREE, "button", "Trade", exact=True) == "e21"


def test_find_ref_role_must_match() -> None:
    # "Quantity" exists but as a spinbutton, not a button
    assert find_ref(SAMPLE_TREE, "button", "Quantity") is None
    assert find_ref(SAMPLE_TREE, "spinbutton", "Quantity") == "e40"


def test_find_ref_absent_returns_none() -> None:
    assert find_ref(SAMPLE_TREE, "button", "Nonexistent") is None


def test_parse_empty_tree() -> None:
    assert parse_elements("") == []
