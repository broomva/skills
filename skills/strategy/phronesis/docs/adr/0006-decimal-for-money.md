# ADR-0006: Decimal for money, not int cents or float

**Status:** Accepted (2026-05-06)

## Context

`Recommendation.value`, `RoiCell.*`, `BaselineSection.baseline_value`, `StrategicThesis.magnitude_estimate` all carry monetary values. Three options: float, int (in minor units / cents), or `decimal.Decimal`.

## Decision

`decimal.Decimal` everywhere money is involved.

## Consequences

* No floating-point error in cumulative ROI / NPV calculations
* USDC and COP both have non-cent precision needs; `Decimal` handles arbitrary-precision
* Phase-3 mirror is `rust_decimal::Decimal` — identical semantics
* Pydantic 2 supports `Decimal` natively with JSON-string serialization

## Alternatives considered

1. **`int` cents.** Rejected — fails for non-cent currencies (e.g., COP, large USDC fractions)
2. **`float`.** Rejected — accumulating floating-point error in 5-year ROI projections
3. **Custom Money type.** Rejected — premature abstraction; `Decimal` + `value_currency: str` is sufficient
