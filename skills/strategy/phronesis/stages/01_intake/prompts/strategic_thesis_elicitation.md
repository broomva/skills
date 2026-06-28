# Strategic Thesis Elicitation Prompt

Use this prompt during the sponsor interview (CDO / COO / CFO equivalent) to
elicit a Strategic Thesis that satisfies L1.

> Before we do *any* AI work, I need to understand the **economic lever**
> we're pulling. Not "we want to use AI" — that's vague and gets us
> nowhere. What's the dollar / risk / speed lever that justifies your time
> and the engagement budget?

## Five-question follow-up

1. What measurable outcome would let you say "this engagement was worth it"?
2. What's the dollar magnitude (revenue / cost / risk / speed) of that
   outcome over the next 12 months?
3. How did you arrive at that number? *(basis)*
4. Is this a "now" lever (h1, deploy this year), "next" (h2, prove this
   year, scale next), or "later" (h3, optionality)?
5. Who has authority to approve a $X-budget AI initiative aimed at this
   lever?

## Reject vague answers

"operational excellence", "do AI better", "be more efficient" — push back
until you have a quantified lever.

The `StrategicThesis` Pydantic model rejects empty `evidence`,
`magnitude_estimate=0`, or missing `decision_rights_owner` at construction.
The L1 linter (M3) rejects engagements that close intake without one.

## Output

A `StrategicThesis(...)` object passed to `IntakeStage.declare_thesis()`.

```python
thesis = StrategicThesis(
    economic_lever="<one-sentence lever>",
    lever_kind="revenue" | "cost" | "risk" | "speed" | "strategic-option",
    magnitude_estimate=Decimal("<dollar amount>"),
    magnitude_basis="<how the number was derived>",
    strategic_horizon="h1-now" | "h2-next" | "h3-later",
    decision_rights_owner="<role + name>",
    measured_in="USD/yr" | "tickets/mo" | "GWh/yr" | ...,
    evidence=[<≥1 Citation tying this back to interview/data/regulation>],
)
intake_stage.declare_thesis(engagement, thesis)
```
