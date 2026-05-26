# ADR-0001: Python substrate now, Life Rust crate Phase 3

**Status:** Accepted (2026-05-06)

## Context

Phronesis could be built either as (a) a Python skill in the bstack family or (b) a Rust crate in the Life monorepo (`core/life/crates/life-phronesis/`) from day one.

The Life-crate path inherits powerful infrastructure (lago event journal, haima billing, vigil telemetry, nous evaluators, anima identity, lifegw endpoint) that consulting engagements genuinely need. The Python skill path optimizes for fast iteration on methodology content (frameworks, prompts, deliverable templates) and zero-friction contributor onboarding.

## Decision

Build the substrate as a Python skill at `skills/phronesis/` in Phase 1. Defer the Life Rust crate to Phase 3, after methodology has been validated with 1-2 real engagements.

The autonomous-mode contract (`runners/autonomous/contract.py`) ships in Phase 1 as typed Pydantic models with a `service.py` that raises `NotImplementedError`. Phase 3 transcribes Phase 1's Python primitives to Rust and wires them to the Life infrastructure.

## Consequences

**Positive:**
* Phase 1 ships in 3-4 weeks instead of 8+
* Methodology iteration on YAML/markdown is fast; Rust adds compile cycles
* Contributors can add a framework via PR without learning Cargo
* Validation happens before productization — Phase 2 engagements teach what's actually needed
* End state matches "Life crate from day one" without paying the upfront cost

**Negative:**
* Phase 3 is a transcription, not a no-op — types must be designed Rust-clean (which they are: explicit enums, `Decimal` for money, `datetime` for time, no Python dicts as variant types)
* The Life-infrastructure benefits (lago, haima, vigil, nous) are deferred until Phase 3
* Two codebases exist briefly during Phase 3 transition

## Alternatives considered

1. **Life crate from day one.** Rejected — premature productization on aspirational methodology. McKinsey didn't build QuantumBlack day one; they built it after the practice was proven.
2. **TypeScript skill.** Rejected — adjacent skills are Python, no toolchain advantage, and no PyO3 path to Phase 3 Rust.
3. **Python with PyO3 Rust extension for hot paths.** Rejected — premature optimization. Phase 1 has no hot paths; methodology dominates compute.
