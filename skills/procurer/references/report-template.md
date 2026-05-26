# Report Template

The output of every procurer run conforms to this template. The structure is non-negotiable; the *length* per section scales with mode (`fast` / `standard` / `deep`).

A report that violates structure fails `scripts/validate_report.py`. Run the validator before delivering to the user.

---

## The skeleton

```markdown
# <Need restated in one line>

**Locale:** <CO Bogotá | US California | …>  
**Currency:** <COP | USD | …>  
**Mode:** <fast | standard | deep>  
**Generated:** <ISO-8601 UTC>

## Problem framing

<2–4 sentences. Name the dominant failure mode (Grounding Rule 8). Separate symptom from cause. State the constraint or context the user gave (region, urgency, budget headroom, aesthetic prefs).>

## Alternatives

### Alternative A — <name>   (Tiers: T1 → T3)

**Thesis.** <One sentence: what problem this actually solves. Not what the alternative *is*.>

**Cost band (in user currency).**  
- Low: <number>  
- Typical: <number>  
- High: <number>  
- Includes / excludes: <tax treatment, installation, materials breakdown if material>

**Confidence:** <0.0–1.0>. <One-line rationale: e.g., "Three exact product pages cited; unit fully specified.">

**Providers cited (N):**
| Tier | Provider | Price | Unit | Confidence | Source |
|---|---|---|---|---|---|
| T1 | Homecenter | $ 12.450 | unidad | 0.95 | [1] |
| T2 | Pavco | $ 14.200 | unidad | 0.88 | [2] |
| T3 | Tecnoglass | cotización a solicitud | m² | 0.55 | [3] |

**Notes.** <Lead time, hidden costs, deal-breakers, sanity-band flags, what's NOT in the band.>

---

### Alternative B — <name>   (Tiers: T2 → T4)
… same structure …

### Alternative C — <name>   (Tiers: T4 → T5)
… same structure …

(3–5 alternatives total)

## Cross-cutting notes

- **Tax treatment.** <e.g., "All prices in this report exclude IVA 19% unless noted; CO buyer should add IVA + applicable retenciones.">
- **Supplier shortlist by region.** <e.g., "Bogotá: Homecenter Av 68 / Tecnoglass distrito sur / Vitelsa Calle 80.">
- **Common hidden costs.** <e.g., "Casement window install includes demolition + waste removal + interior re-finishing — budget ~20% above the bare DVH cost.">
- **Lead times.** <e.g., "Standard DVH: 3–4 weeks. Acoustic DVH with laminated PVB: 6–8 weeks.">

## Recommendation

**Start with:** <Alternative X>  
**Total budget envelope:** <low – high in user currency>  
**Rationale (2–3 sentences).** <Why this alternative resolves the dominant failure mode at the best cost-per-problem-solved ratio; what's the risk if it doesn't.>  
**If that doesn't work:** <Alternative Y as fallback> — <one-line condition that would trigger escalation: "if Tier-1 fix improves perceived noise by < 50% after 2 weeks, escalate to Alternative B">.

## Sources

[1] https://www.homecenter.com.co/… — "Felpa siliconada para ventana corrediza 5m" — fetched 2026-05-13T14:22Z  
[2] https://www.pavco.com.co/… — "Pavco Felpa con Aleta" — fetched 2026-05-13T14:23Z  
[3] https://www.tecnoglass.com/contacto — "Cotización ventanería acústica — solicitud por correo" — fetched 2026-05-13T14:25Z  
…
```

---

## Filled exemplar — window noise (Bogotá)

See `../assets/examples/window-noise-attenuation.md` for the worked example with full citations placeholders.

---

## Mode-specific tailoring

### `fast` mode

- Same structure, but `Providers cited` has 1–2 rows.
- `Cross-cutting notes` can be 1–2 bullets.
- `Recommendation.Rationale` is one sentence.
- Total length 200–500 words.

### `standard` mode

- The full template above.
- 3–5 alternatives, each with 3–5 providers cited.
- Cross-cutting notes covers tax, supplier shortlist, hidden costs, lead times.
- Recommendation includes fallback.
- 600–1,200 words.

### `deep` mode

- Full template + a **Scenario sensitivity** subsection in Recommendation:
  - *Worst case (highest cited)*: budget envelope.
  - *Expected (median)*: budget envelope.
  - *Best case (lowest cited)*: budget envelope.
- Add a **Lead-time map**: which alternatives can ship in 2 weeks vs. 8+.
- Add **Risk register**: 3–5 risks with mitigations.
- 1,500–3,000 words.

---

## Failure modes the template prevents

| If the template were missing… | The failure mode |
|---|---|
| Problem framing | Report jumps to alternatives without diagnosing — user spends Tier-4 money on a Tier-1 problem. |
| Thesis per alternative | Alternatives become a feature list, not a decision aid. |
| Confidence column | User can't tell which numbers are firm and which are guesses. |
| Sources block | Numbers are uncheckable; report is hallucination-shaped. |
| Recommendation with budget envelope | User reads, doesn't know what to do, asks follow-up. The skill failed to be decision-shaped. |
| Cross-cutting notes | Tax treatment ambiguous, user under-budgets by 19%+. |

---

## Validator contract

`scripts/validate_report.py <report.md>` checks (exit non-zero on failure):

1. Headers present: `Problem framing`, `Alternatives`, `Recommendation`, `Sources`.
2. ≥ 3 alternatives (sections under `## Alternatives` matching `### Alternative ` prefix).
3. Each alternative has `Thesis`, `Cost band`, `Confidence`, `Providers cited`.
4. Each cost band has 3 numbers (low / typical / high) in consistent currency.
5. Each confidence value is in `[0, 1]`.
6. Every footnote `[N]` referenced in the body appears in `## Sources`.
7. Every source has URL, title, fetched-at timestamp.
8. Recommendation block has `Start with`, `Total budget envelope`, `Rationale`.

---

See also: `decomposition-patterns.md` for choosing what the alternatives are, `provider-taxonomy.md` for choosing who cites them, `grounding-discipline.md` for the citation rules.
