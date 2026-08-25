#!/usr/bin/env python3
"""
Recover the callable GraphQL surface of an Instacart Storefront Pro site.

Storefront Pro sites (cub.com, and the other retailers on the same platform) serve a
GraphQL endpoint that accepts *only* persisted queries: raw queries and introspection
are both rejected with PERSISTED_QUERY_NOT_SUPPORTED. A client can therefore call
exactly the operations whose sha256 hashes have been observed in real traffic.

Two places those hashes can be observed, neither needing browser automation:

  ssr   A rendered page embeds <script id="ssr-query-perf-data">, the server's own
        record of the GraphQL requests it issued while server-rendering — each one a
        full URL carrying operationName, variables, and the persisted-query hash.

  har   A DevTools "Save all as HAR" export, which additionally captures the
        client-side operations (search, cart) that never appear in any SSR payload.

Both emit the same registry shape, so they merge.

Values are never retained. Variables are reduced to their shape, because a HAR is a
recording of a real session and its variables carry address ids, coordinates, cart ids
and user ids.

Usage:
    ssr_ops.py ssr <page.html|->        [--json]
    ssr_ops.py har <capture.har>        [--json]
    ssr_ops.py merge <a.json> <b.json>  [--json]
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
from typing import Any

SSR_SCRIPT_RE = re.compile(
    r'<script id="ssr-query-perf-data"[^>]*>(.*?)</script>', re.S
)
APOLLO_SCRIPT_RE = re.compile(
    r'<script id="node-apollo-state"[^>]*>(.*?)</script>', re.S
)

# Identifiers that are scoped to one session and meaningless to anyone else.
SESSION_SCOPED = {
    "slotId",
    "pageViewId",
    "previewToken",
    "addressId",
    "debugPlacementId",
    "sessionId",
    "userId",
}

MAX_SHAPE_DEPTH = 4


def shape_of(value: Any, depth: int = 0) -> Any:
    """Reduce a value to its structure, discarding every scalar."""
    if depth > MAX_SHAPE_DEPTH:
        return "<...>"
    if value is None:
        return None
    if isinstance(value, list):
        return [shape_of(value[0], depth + 1)] if value else []
    if isinstance(value, dict):
        return {k: shape_of(v, depth + 1) for k, v in value.items()}
    return f"<{type(value).__name__}>"


def redact(variables: dict) -> dict:
    """Keep configuration constants; replace session-scoped identifiers with shapes."""
    out: dict = {}
    for k, v in variables.items():
        if k in SESSION_SCOPED and v not in (None, "", []):
            out[k] = f"<{type(v).__name__}>"
        elif isinstance(v, dict):
            out[k] = redact(v)
        else:
            out[k] = v
    return out


def _decode_script_block(raw: str) -> Any:
    """SSR blocks are JSON, sometimes URL-encoded. Try both before giving up."""
    raw = raw.strip()
    for decode in (lambda s: s, urllib.parse.unquote):
        try:
            return json.loads(decode(raw))
        except (ValueError, TypeError):
            continue
    raise ValueError("script block is neither JSON nor URL-encoded JSON")


def _op_from_url(url: str) -> tuple[str, str, dict] | None:
    """Pull (operationName, sha256Hash, variables) out of an APQ GET url."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    name = (query.get("operationName") or [None])[0]
    if not name:
        return None
    try:
        ext = json.loads((query.get("extensions") or ["{}"])[0])
        digest = ext.get("persistedQuery", {}).get("sha256Hash")
    except ValueError:
        digest = None
    if not digest:
        return None
    try:
        variables = json.loads((query.get("variables") or ["{}"])[0])
    except ValueError:
        variables = {}
    # `variables` is not guaranteed to be an object: a malformed or non-object value
    # would otherwise propagate and abort the whole extraction over one bad entry.
    if not isinstance(variables, dict):
        variables = {}
    return name, digest, variables


def from_ssr(html: str) -> dict:
    """Extract the operation registry from a rendered Storefront Pro page."""
    match = SSR_SCRIPT_RE.search(html)
    if not match:
        raise ValueError(
            "no <script id='ssr-query-perf-data'> block found — "
            "is this a rendered Instacart Storefront Pro page?"
        )
    data = _decode_script_block(match.group(1))

    entries: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "operationName" in node and "url" in node:
                entries.append(node)
            else:
                for value in node.values():
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)

    operations: dict[str, dict] = {}
    for entry in entries:
        parsed = _op_from_url(entry.get("url", ""))
        if not parsed:
            continue
        name, digest, variables = parsed
        # First occurrence wins; repeats carry the same hash by definition.
        operations.setdefault(
            name,
            {
                "sha256Hash": digest,
                "sampleVariables": redact(variables),
                "capturedFrom": "ssr",
            },
        )
    return operations


def from_har(har: dict) -> dict:
    """Extract the operation registry from a DevTools HAR export."""
    operations: dict[str, dict] = {}
    for entry in har.get("log", {}).get("entries", []):
        request = entry.get("request", {})
        url = request.get("url", "")
        if "/graphql" not in url:
            continue

        if request.get("method") == "GET":
            parsed = _op_from_url(url)
            if not parsed:
                continue
            name, digest, variables = parsed
        else:
            try:
                body = json.loads((request.get("postData") or {}).get("text") or "{}")
            except ValueError:
                continue
            one = body[0] if isinstance(body, list) and body else body
            if not isinstance(one, dict):
                continue
            name = one.get("operationName")
            digest = (
                (one.get("extensions") or {}).get("persistedQuery", {}).get("sha256Hash")
            )
            variables = one.get("variables") or {}
            if not name or not digest:
                continue

        operations.setdefault(
            name,
            {
                "sha256Hash": digest,
                # A HAR records a live session: keep shape only, never values.
                "sampleVariables": shape_of(variables),
                "capturedFrom": "har",
            },
        )
    return operations


def store_constants(html: str) -> dict:
    """Best-effort recovery of the shop/zone/retailer ids a client must send."""
    found: dict[str, Any] = {}
    match = APOLLO_SCRIPT_RE.search(html)
    if not match:
        return found
    try:
        data = _decode_script_block(match.group(1))
    except ValueError:
        return found

    wanted = {"shopId", "zoneId", "retailerId", "postalCode", "retailerLocationId"}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in wanted and isinstance(value, (str, int)) and key not in found:
                    found[key] = str(value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return found


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    mode = argv[1]
    as_json = "--json" in argv
    args = [a for a in argv[2:] if not a.startswith("--")]

    if mode == "ssr":
        if not args:
            print("ssr needs a file (or - for stdin)", file=sys.stderr)
            return 2
        html = sys.stdin.read() if args[0] == "-" else open(
            args[0], encoding="utf-8", errors="replace"
        ).read()
        operations = from_ssr(html)
        constants = store_constants(html)
    elif mode == "har":
        if not args:
            print("har needs a file", file=sys.stderr)
            return 2
        with open(args[0], encoding="utf-8", errors="replace") as fh:
            operations = from_har(json.load(fh))
        constants = {}
    elif mode == "merge":
        if len(args) < 2:
            print("merge needs two registry files", file=sys.stderr)
            return 2
        operations = {}
        for path in args:
            with open(path, encoding="utf-8") as fh:
                blob = json.load(fh)
            operations.update(blob.get("operations", blob))
        constants = {}
    else:
        print(f"unknown mode: {mode}", file=sys.stderr)
        return 2

    if as_json:
        print(json.dumps({"operations": operations, "constants": constants}, indent=1))
    else:
        print(f"{len(operations)} operation(s)")
        for name in sorted(operations):
            print(f"  {name}  {operations[name]['sha256Hash'][:16]}…")
        if constants:
            print("\nstore constants:")
            for key in sorted(constants):
                print(f"  {key} = {constants[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
