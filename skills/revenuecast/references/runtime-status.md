# L3 Runtime — STATUS: DEFERRED / EARNED

The Layer-3 autonomous runtime (`references/runtime-spec.html`) is **specified, not
built**. It is bundled with this skill as a reference design; it graduates to its own
Rust deploy repo (Railway) **only when actually built**.

## Gate condition (do not build until this is true)

> Build the runtime daemon **only after Layer-2 (the agentic-dev wedge) shows measured
> conversion** — a running authority→email→tripwire funnel with real numbers, produced
> by manual posting + the `content-engine` skill, NOT by this daemon.

This is the P20 review's #2 must-fix: the runtime is over-capitalized before demand is
proven. Validate the cheap way first.

## Definition of "earned" (the trigger to start M1)

1. L2 funnel live ≥30 days with a measured tripwire conversion > 0 and ≥1 recurring
   member (the `revenuecast.manifest.yaml` `kpis.validated` block is non-empty).
2. Manual posting effort demonstrably exceeds the daemon's build cost.
3. The open-source-vs-paid boundary is drawn (the runtime is the closed-execution surface).

## When earned — M1 order (from the spec)

1. `kleos-store` on embedded sled/sqlite (Lago is M2 — it's in-flight in `core/life/`).
2. `kleos-publisher` — YouTube first (cheapest API), then IG (25/24h cap), TikTok
   private-until-audit, X text-only ($0.20 URL-write penalty enforces "X = authority").
3. `kleos-shield` + `.control/policy.yaml` S-K1…S-K5 + C2PA signing at the publish boundary.
4. `kleos-core` observe→decide→act→judge loop; `kleos-generate` shells to `content-engine`.
5. **M2:** `kleos-feedback` — the bandit/attribution/DNA-fold-back self-improvement loop
   (unbuilt new code; do not claim self-improvement before it ships AND is measured —
   `symphony-egri/batch.rs` is a pass/fail tally, NOT a variant selector).

P11 (publish + screenshot real posts) and P20 (cross-review the rate-limiters + shield)
are pre-merge gates for M1. Provenance: BRO-1429 · BRO-1436.
