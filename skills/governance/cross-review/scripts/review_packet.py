#!/usr/bin/env python3
"""Validate a claim ledger, blinded debate and independent refuter receipt.

This checks packet structure and traceability, not whether an agent was actually
isolated or whether a cited observation is true. Keep dispatch receipts for that.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def text(value: object, where: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: nonempty text required")


def rows(value: object, where: str, nonempty: bool = False) -> list:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{where}: {'nonempty ' if nonempty else ''}array required")
    return value


def validate(packet: object) -> None:
    if not isinstance(packet, dict):
        raise ValueError("packet must be an object")
    text(packet.get("artifact_hash"), "artifact_hash")
    claims = {}
    for c in rows(packet.get("claims"), "claims", True):
        if not isinstance(c, dict):
            raise ValueError("claim must be an object")
        for key in ("id", "claim", "what_supports_it", "whats_missing"):
            text(c.get(key), f"claim.{key}")
        if c["id"] in claims:
            raise ValueError("duplicate claim id")
        if c.get("status") not in ("established", "contested", "untested"):
            raise ValueError("claim.status must be established, contested or untested")
        claims[c["id"]] = c
    for source in rows(packet.get("primary_sources"), "primary_sources", True):
        text(source, "primary source reference")
    agents = set()
    for role in ("skeptic", "believer", "refuter"):
        review = packet.get(role)
        if not isinstance(review, dict):
            raise ValueError(f"{role}: object required")
        text(review.get("dispatch_id"), f"{role}.dispatch_id")
        if review["dispatch_id"] in agents:
            raise ValueError("three distinct dispatch receipts required")
        agents.add(review["dispatch_id"])
        if review.get("fresh_context") is not True:
            raise ValueError(f"{role}: fresh_context must be true")
        if review.get("artifact_hash") != packet["artifact_hash"]:
            raise ValueError(f"{role}: artifact hash mismatch")
        reviewed = rows(
            review.get("reviewed_claim_ids"), f"{role}.reviewed_claim_ids", True
        )
        if any(not isinstance(cid, str) for cid in reviewed) or set(reviewed) != set(
            claims
        ):
            raise ValueError(f"{role}: explicitly review every ledger claim")
        for source in rows(
            review.get("raw_sources_read"), f"{role}.raw_sources_read", True
        ):
            if source not in packet["primary_sources"]:
                raise ValueError(f"{role}: unknown raw source")
        for f in rows(review.get("findings"), f"{role}.findings"):
            if not isinstance(f, dict) or f.get("claim_id") not in claims:
                raise ValueError(f"{role}: finding needs a known claim_id")
            for key in ("reading", "evidence", "settling_observation", "disposition"):
                text(f.get(key), f"{role}.{key}")
    # The refuter must inspect the actual primary material, not only the debate.
    if set(packet["refuter"]["raw_sources_read"]) != set(packet["primary_sources"]):
        raise ValueError("refuter must inspect every primary source in the packet")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("packet", type=Path)
    args = ap.parse_args()
    try:
        validate(json.loads(args.packet.read_text(encoding="utf-8")))
    except (ValueError, OSError, TypeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 2
    print(json.dumps({"valid": True, "scope": "structure and traceability only"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
