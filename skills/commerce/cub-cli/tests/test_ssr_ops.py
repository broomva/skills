"""Tests for the Storefront Pro recon core."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import ssr_ops  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
HTML = (FIXTURES / "storefront.html").read_text(encoding="utf-8")
HAR = json.loads((FIXTURES / "capture.har").read_text(encoding="utf-8"))


def test_extracts_operations_from_ssr_block():
    ops = ssr_ops.from_ssr(HTML)
    assert ops["GetRetailerBySlug"]["sha256Hash"] == "a" * 64
    assert ops["GetRetailerBySlug"]["capturedFrom"] == "ssr"


def test_first_occurrence_wins():
    # A later entry for the same operation must not clobber the first.
    assert ssr_ops.from_ssr(HTML)["GetRetailerBySlug"]["sha256Hash"] == "a" * 64


def test_skips_entries_with_no_persisted_hash():
    # Without a hash the operation is not callable, so it must not enter the registry.
    assert "NoHash" not in ssr_ops.from_ssr(HTML)


def test_ssr_block_may_be_url_encoded():
    # The real pages URL-encode this block; plain JSON must also work.
    plain = '<script id="ssr-query-perf-data" type="application/json">' + json.dumps(
        {"q": [{"operationName": "Op", "url": "/graphql?operationName=Op&extensions="
                + '%7B%22persistedQuery%22%3A%7B%22sha256Hash%22%3A%22ff%22%7D%7D'}]}
    ) + "</script>"
    assert ssr_ops.from_ssr(plain)["Op"]["sha256Hash"] == "ff"


def test_missing_ssr_block_is_an_explicit_error():
    try:
        ssr_ops.from_ssr("<html><body>nothing here</body></html>")
    except ValueError as exc:
        assert "ssr-query-perf-data" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_session_scoped_ids_are_redacted_from_ssr():
    # slotId is scoped to one session; it must not be published in a registry.
    ops = ssr_ops.from_ssr(HTML)
    assert ops["SlotPlacements"]["sampleVariables"]["slotId"] == "<str>"


def test_store_constants_are_kept_because_they_are_configuration():
    ops = ssr_ops.from_ssr(HTML)
    assert ops["SlotPlacements"]["sampleVariables"]["shopId"] == "9758"


def test_recovers_store_constants():
    consts = ssr_ops.store_constants(HTML)
    assert consts["shopId"] == "9758"
    assert consts["zoneId"] == "205"
    assert consts["retailerId"] == "142"


def test_har_get_and_post_entries():
    ops = ssr_ops.from_har(HAR)
    assert ops["SearchResults"]["sha256Hash"] == "c" * 64
    assert ops["AddToCart"]["sha256Hash"] == "d" * 64


def test_har_ignores_non_graphql_requests():
    assert "logo" not in json.dumps(ssr_ops.from_har(HAR))


def test_har_never_retains_concrete_values():
    # A HAR is a recording of a live session. Only the shape may survive.
    serialized = json.dumps(ssr_ops.from_har(HAR))
    assert "SECRET-ADDR" not in serialized
    assert "bacon" not in serialized


def test_shape_of_replaces_scalars_with_type_placeholders():
    assert ssr_ops.shape_of({"a": "x", "b": 1, "c": True}) == {
        "a": "<str>",
        "b": "<int>",
        "c": "<bool>",
    }


def test_shape_of_preserves_null_and_collapses_lists():
    assert ssr_ops.shape_of({"a": None}) == {"a": None}
    assert ssr_ops.shape_of([1, 2, 3]) == ["<int>"]
    assert ssr_ops.shape_of([]) == []


def test_shape_of_is_depth_bounded():
    deep = {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}
    assert "deep" not in json.dumps(ssr_ops.shape_of(deep))


def _run() -> int:
    """Run without pytest, so the suite works on a bare interpreter."""
    passed = failed = 0
    for name in sorted(globals()):
        if not name.startswith("test_"):
            continue
        try:
            globals()[name]()
            passed += 1
            print(f"  ok   {name}")
        except Exception as exc:  # noqa: BLE001 - a test runner reports, never raises
            failed += 1
            print(f"  FAIL {name}: {exc}")
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
