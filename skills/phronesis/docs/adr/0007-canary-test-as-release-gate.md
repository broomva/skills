# ADR-0007: Canary anonymization test as release gate

**Status:** Accepted (2026-05-06)

## Context

P6 (tenant data isolation) is a non-negotiable safety property. Easy to violate by accident: an extraction logic change could leak a tenant slug into `research/entities/`; a new framework could embed an example with a real client name; etc.

We need a test that *catches* this mechanically and blocks releases until fixed.

## Decision

`tests/integration/test_anonymization_canary.py` defines a fixed list of 14 canary tokens (tenant slug, 3 personal names, 4 currency exact values, 3 location-exact strings, 2 product names, 1 phrase). It runs the full extraction pipeline against the `acme-bank` fixture and asserts that none of the canaries appears in any extracted entity content.

The test runs in pre-commit, pre-push, AND CI. Failure blocks every release until fixed.

## Consequences

* P6 is verified mechanically, not by reviewer attention
* New canary tokens can be added per fixture as the surface grows (Hindi names, EUR currencies, etc.)
* Fast and deterministic — no LLM in the loop, just substring assertions
* The test itself becomes a documentation artifact: "what does anonymization protect?"

## Alternatives considered

1. **Manual review.** Rejected — easy to miss; recurring; expensive in human time
2. **ML-based PII detection.** Rejected — overkill for Phase 1; canary tokens cover the practical attack surface
3. **CI-only (not pre-commit).** Rejected — too late; mistakes leak before CI catches them
