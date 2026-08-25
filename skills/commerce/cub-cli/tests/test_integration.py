"""
Live-endpoint integration tests.

These are the tests that catch the failure mode this skill is most exposed to:
**persisted-query hashes rotate when the storefront deploys.** When that happens every
shipped hash 400s at once, and no amount of unit testing sees it. Nothing else here can
detect it, because the whole point of a persisted query is that the client cannot
construct the document itself.

Opt-in — these make real requests. Run:

    CUB_LIVE=1 python3 tests/test_integration.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORIGIN = "https://www.cub.com"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def _registry() -> dict:
    return json.loads((ROOT / "data" / "ops.json").read_text())["operations"]


def _get(url: str, cookie: str | None = None) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept": "*/*"})
    if cookie:
        req.add_header("cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, res.read(), dict(res.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def _guest_cookie() -> str:
    """Mint a guest session the same way the client does."""
    _, _, headers = _get(f"{ORIGIN}/store/cub/storefront")
    jar = []
    for key, value in headers.items():
        if key.lower() == "set-cookie":
            jar.append(value.split(";")[0])
    return "; ".join(jar)


def _apq(name: str, digest: str, variables: dict) -> str:
    return (
        f"{ORIGIN}/graphql?operationName={name}"
        f"&variables={urllib.parse.quote(json.dumps(variables))}"
        f"&extensions={urllib.parse.quote(json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': digest}}))}"
    )


def test_shipped_hash_is_still_registered():
    """A rotated hash is the way this skill dies. Detect it explicitly."""
    op = _registry()["GetRetailerBySlug"]
    status, body, _ = _get(_apq("GetRetailerBySlug", op["sha256Hash"], {"slug": "cub"}))
    payload = json.loads(body)
    errors = json.dumps(payload.get("errors", []))
    assert "PersistedQueryNotFound" not in errors, (
        "shipped hash is no longer registered — the storefront redeployed. "
        "Re-run: python3 scripts/ssr_ops.py ssr <fresh page.html>"
    )
    assert status == 200, f"HTTP {status}: {body[:200]!r}"
    assert payload["data"]["retailer"]["id"] == "142"


def test_raw_queries_are_still_rejected():
    """The constraint this whole design rests on. If it lifts, the client can simplify."""
    req = urllib.request.Request(
        f"{ORIGIN}/graphql",
        data=json.dumps({"query": "query Probe { __typename }"}).encode(),
        headers={"user-agent": UA, "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = res.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
    assert "PERSISTED_QUERY_NOT_SUPPORTED" in body.decode(), (
        "the endpoint now accepts raw queries — the persisted-query constraint "
        "documented in SKILL.md no longer holds"
    )


def test_product_reads_require_a_session():
    """Guest session is required and sufficient. Both halves matter."""
    op = _registry()["CollectionProductsWithFeaturedProducts"]
    variables = {
        "shopId": "9758",
        "postalCode": "55113",
        "zoneId": "205",
        "slug": "rc-on-sale-recommended-for-you",
        "filters": [],
        "pageViewId": "00000000-0000-4000-8000-000000000000",
        "itemsDisplayType": "collections_storefront",
        "first": 5,
        "pageSource": "storefront",
    }
    url = _apq("CollectionProductsWithFeaturedProducts", op["sha256Hash"], variables)

    status_anon, body_anon, _ = _get(url)
    assert status_anon == 401 or "Not Authenticated" in body_anon.decode(), (
        "product reads no longer require a session"
    )

    status_guest, body_guest, _ = _get(url, cookie=_guest_cookie())
    assert status_guest == 200, f"guest session rejected: HTTP {status_guest}"
    assert json.loads(body_guest)["data"]["collectionProducts"] is not None


def _run() -> int:
    if not os.environ.get("CUB_LIVE"):
        print("skipped — set CUB_LIVE=1 to run live-endpoint tests")
        return 0
    passed = failed = 0
    for name in sorted(globals()):
        if not name.startswith("test_"):
            continue
        try:
            globals()[name]()
            passed += 1
            print(f"  ok   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {name}: {exc}")
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
