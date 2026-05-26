# ADR-0005: Anonymization strict-by-default, loose-by-exception

**Status:** Accepted (2026-05-06)

## Context

Phronesis extracts learnings from completed engagements into `research/entities/` for cross-engagement compounding. Some IP is genuinely reusable (industry patterns, ROI multipliers, anti-patterns). Other IP is tenant-confidential and must not leave the private engagement directory.

## Decision

`AnonymizationPolicy` defaults: strip tenant slug, strip personal names, replace currency exact values with bands, replace dates with relative descriptors, replace locations with regions, redact tenant-specified terms.

Loosening (e.g., a publishable case study with tenant consent) is an explicit per-engagement override, recorded in `engagements/<slug>/anonymization-overrides.yaml`. Reviewer must approve loosening.

## Consequences

* Default behavior is safe. Tenant data does not leak unless someone explicitly turns off a guard
* Canary anonymization test (ADR-0007) verifies no canary token from a fixture engagement reaches `research/entities/`
* Some engagement IP that *could* be more public-friendly stays anonymous; that's the right tradeoff

## Alternatives considered

1. **Manual review only, no default policy.** Rejected — easy to forget; policy is enforced at extraction time
2. **Anonymize only on user opt-in.** Rejected — tenant-data leaks once and the trust is gone
