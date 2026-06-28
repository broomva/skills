# ADR-0008: Bision failure-mode linter rules (L1-L5) as release gate

**Status:** Accepted (2026-05-06)

## Context

Bision Consulting documented 5 empirical C-level failure patterns from audited projects (slide: "Las cinco fallas que vemos en C-Level", Bogotá 2026):

1. Sin tesis estratégica (100% of audited projects)
2. Casos de uso mal priorizados (87%)
3. Datos no preparados (74%)
4. Desconexión negocio-tecnología (61%)
5. Sin medición de ROI (48%)

Phronesis must make each *structurally impossible*, not just discouraged.

## Decision

Five linter rules + four typed primitives + one ideation enum, all required:

| Failure | Rule | Primitive |
|---|---|---|
| 1 | L1 STRATEGIC_THESIS_REQUIRED | `StrategicThesis` |
| 2 | L2 DIVERSE_IDEATION_SOURCES | `IdeationSource` enum |
| 3 | L3 DATA_READINESS_GATE | `DataReadinessAssessment` |
| 4 | L4 ADOPTION_METRIC_REQUIRED | `AdoptionMetric` |
| 5 | L5 BASELINE_REQUIRED | `BaselineSection` |

Test class `tests/integration/test_bision_failure_prevention.py` (M3 lands the test, M0 lands the primitives) constructs a deliberately-broken engagement per failure mode and asserts the corresponding rule blocks. Pre-commit + CI gate.

## Consequences

* Phronesis ships with an empirical claim: "an engagement that runs end-to-end through this substrate cannot exhibit any of Bision's 5 failure modes"
* That claim is testable, and it ships green from day one
* Primitives are additive, not refactoring — no design rework

## Alternatives considered

1. **Discourage failures via documentation only.** Rejected — documentation doesn't prevent
2. **Flag in linter only (don't add typed primitives).** Rejected — type system is stronger than linter
3. **Add only L1 + L5 (the highest-frequency).** Rejected — L2-L4 are 87%/74%/61% — also unacceptably common
