# ADR-0004: Five stage-boundary human review gates, non-negotiable in both modes

**Status:** Accepted (2026-05-06)

## Context

Phronesis runs 5 stages (intake → maturity → ideate → prioritize → roadmap). Question: are review gates between stages mandatory, optional, or skippable?

Top-firm engagements have human review at every consequential decision boundary — that's how partners catch hallucinations and add judgment. Removing gates accelerates throughput at the cost of quality and trust.

## Decision

5 gates are non-negotiable in both modes:
* CLI mode: `phronesis review <stage>` blocks until `--approve` or `--revise`
* Autonomous mode: runner blocks on `decision != "approved"`; webhook-driven; default fallback on timeout = pause, never auto-approve

The consultant can choose *which gates apply per engagement* (collapsing intake+scan into one if appropriate) but the substrate offers all 5 as defaults.

## Consequences

* Engagements are slower than fully-autonomous would be
* Quality is higher; hallucinations caught at boundaries
* Trust gap is closed — clients see human judgment in the loop
* Maps to bstack's P2 (Control Gate) primitive

## Alternatives considered

1. **Optional gates.** Rejected — once optional, they get skipped. Defaults define norms.
2. **Auto-approve on timeout.** Rejected — autonomous consulting that auto-ships under timeout is a trust-destroying failure mode
3. **3 gates (collapse Stage 3+4 into one).** Rejected — leave that decision to the consultant per engagement
