# ADR-0002: Frameworks organized by consulting purpose, not by source firm

**Status:** Accepted (2026-05-06)

## Context

The framework library has 14 Phase-1 + 13 D-scope frameworks from many sources (McKinsey, BCG, Strategyzer, Intercom, etc.). Two natural directory structures:
1. By **source firm**: `frameworks/mckinsey/`, `frameworks/bcg/`, `frameworks/strategyzer/`...
2. By **consulting purpose**: `frameworks/strategy/`, `frameworks/maturity/`, `frameworks/ideation/`, `frameworks/prioritization/`, `frameworks/roi/`, `frameworks/ai-lifecycle/`, `frameworks/change/`.

## Decision

Organize by consulting purpose. Each YAML file names its source firm internally as `source_firm:` in the frontmatter.

## Consequences

* A consultant looking for "what helps me prioritize?" lands in `frameworks/prioritization/` and sees RICE, ICE, WSJF — a comparison set, not a single firm's output
* The `framework_selector` primitive (M1) reasons over purpose, not lineage
* Source firm credit is preserved per file, not at the directory level

## Alternatives considered

1. **By source firm.** Rejected — biases the reader toward firm-specific orthodoxy. Phronesis is plural by design; the directory structure should reinforce that.
2. **Flat directory.** Rejected — 27 frameworks in one folder is hard to navigate.
