# Decomposition Patterns

A procurement need rarely arrives pre-decomposed. The user names a symptom ("bedroom is noisy", "we need A/C", "I want a new kitchen") and expects you to surface the alternatives. **How you decompose the need determines the quality of every downstream stage.** This document is the menu of canonical patterns.

> **Cardinal rule.** Before applying any pattern, separate the **symptom** from the **failure mode**. The cheapest, highest-value alternative usually addresses the dominant failure mode head-on, not the symptom.

---

## Pattern 1 — Incremental → Augmentation → Replacement

**Use for:** Physical / fix-it problems where an existing system is underperforming. The default pattern for "fix the X".

### The three rungs

1. **Incremental** — Treat the dominant failure mode of the existing system. Cheap, fast, reversible. Often DIY-retail (T1). The high-value option 80% of the time.
2. **Augmentation** — Add a new component alongside the existing system, keeping the original in place. Mid-cost, mid-disruption. Usually T2–T3.
3. **Replacement** — Tear out and replace the system entirely. Expensive, disruptive, often-overkill. T3–T5.

### Worked example — Window noise

| Rung | Alternative | Thesis |
|---|---|---|
| Incremental | Replace felpa seals, adjust rollers, add acoustic curtain | The dominant leak is the brush-pile seal; closing it captures most of the available improvement. |
| Augmentation | Internal secondary window (5–10 cm air gap, casement gasket) | Adds a second barrier with an air gap — the air gap kills low-frequency rumble that mass-only solutions miss. |
| Replacement | Full DVH with laminated PVB acoustic glass + casement frame | Replaces the whole system; only worth it during a broader renovation. |

### Why this pattern works

The cost of each rung roughly 10×s the previous one. So does the disruption. But the *acoustic improvement* often saturates after the augmentation rung — meaning replacement is rarely the right answer unless other constraints (thermal, age, aesthetics) ride along.

### Other domains

- **Roof leak**: patch the membrane (T1) → add a torch-on overlay (T3) → re-roof (T5).
- **Slow laptop**: clean + reinstall (T1) → SSD/RAM upgrade (T2) → new machine (T2 with disposal of old).
- **Hot bedroom**: window film + curtain (T1) → portable A/C (T2) → split system installed (T4).

---

## Pattern 2 — DIY → Service → Managed

**Use for:** Recurring tasks or services where the lever is *who owns the responsibility*, not what the work is.

### The three rungs

1. **DIY** — User does the work, buying only consumables.
2. **Service (point)** — User hires for the specific task, retains accountability for the outcome.
3. **Managed (relationship)** — User outsources accountability for the whole category; provider owns the outcome on a retainer/subscription.

### Worked example — Personal accounting (Colombia)

| Rung | Alternative | Thesis |
|---|---|---|
| DIY | Use Siigo Lite + DIAN portal for monthly declarations | If your structure is simple (one PN, no employees) the software handles it. |
| Service | Hire a contador independiente for annual reporting | When the structure adds complexity (rentas extranjeras, dividends from Broomva Tech Corp, criptos), a per-engagement contador catches what software misses. |
| Managed | Retainer with a contaduría firm (e.g., Crowe / BDO local) | When you have multiple LLCs / international structure / IRS exposure, a firm on retainer takes the whole category off your plate. |

### Other domains

- **Cleaning**: own supplies (T1) → cleaner once a week (T3) → full facilities mgmt (T5).
- **IT support**: troubleshoot yourself (T1) → call a freelancer (T3) → MSP on retainer (T5).
- **Legal**: templates online (T1) → engage per-matter (T4) → outside counsel on retainer (T5).

### Common trap

Don't jump straight to Managed. The pricing premium is steep, and the relationship's value only kicks in above a complexity threshold the user may not yet have hit.

---

## Pattern 3 — Standard → Custom → Bespoke

**Use for:** Goods or services where the spec is variable and *specificity drives cost*.

### The three rungs

1. **Standard** — Off-the-shelf SKU. Discoverable on a retailer's site, often Tier 1 or Tier 2.
2. **Custom** — Standard spec with options (size, finish, configuration). Manufacturer/fabricator does light customization. Tier 3.
3. **Bespoke** — Designed to fit a specific situation; no SKU exists ahead of time. Tier 4 or Tier 5.

### Worked example — Kitchen sink

| Rung | Alternative | Thesis |
|---|---|---|
| Standard | Single-basin stainless 50×40 cm from Homecenter | Fits most counters, low cost, available immediately. |
| Custom | Two-basin with drainboard from Tramontina / Franke catalogue | Spec'd to the user's counter dimensions, longer lead time. |
| Bespoke | Concrete or hand-formed copper basin commissioned from a fabricator | Designed in; only worth it for a kitchen renovation with strong aesthetic intent. |

### Other domains

- **Furniture**: IKEA → catalog from a local carpentry shop → bespoke piece by a designer.
- **Suit**: off-the-rack → made-to-measure → fully bespoke.
- **Website**: template (Squarespace) → customized template (developer) → bespoke design+build.

### Cost curve

Standard → Custom is usually a 1.5–3× cost jump. Custom → Bespoke is often 5–10×. The user should know which jump they're contemplating before they ask "what's the price."

---

## Pattern 4 — Single-vendor → Multi-vendor → Integrator

**Use for:** Complex projects with multiple sub-categories of spend, where the lever is *how many vendors the user manages*.

### The three rungs

1. **Single-vendor** — One supplier handles the whole scope. Lowest user-side complexity, often higher unit cost (the vendor charges a single-source premium). T4.
2. **Multi-vendor** — User splits the scope across specialists and coordinates them. Lowest unit cost, highest user-side complexity. T2 + T3 + T4 combined.
3. **Integrator** — User hires a generalist (architect, GC, systems integrator) to coordinate the specialists. T5.

### Worked example — Bathroom remodel

| Rung | Alternative | Thesis |
|---|---|---|
| Single-vendor | "Remodelaciones Andrés" handles everything | Cheapest in management overhead; you'll likely pay 15–25% over the multi-vendor sum. |
| Multi-vendor | Buy fixtures (Homecenter/Corona) + hire plumber + hire enchapador + hire pintor | Cheapest by line-item; you coordinate timing, returns, and rework. |
| Integrator | Hire an arquitecto to spec + supervise + contract subs on your behalf | Architect fee 8–15% of project cost; quality and timing risk drop sharply. |

### Other domains

- **Wedding**: single venue does everything → DIY vendors → wedding planner.
- **Software stack**: monolithic SaaS → best-of-breed SaaS → systems integrator.

---

## Choosing a pattern

The four patterns aren't exclusive — a real need often blends them. Use this decision tree:

```
Is the existing system underperforming?
├── Yes → Pattern 1 (Incremental → Augmentation → Replacement)
└── No → Is it a recurring service or accountability question?
        ├── Yes → Pattern 2 (DIY → Service → Managed)
        └── No → Is the spec variable across users?
                ├── Yes → Pattern 3 (Standard → Custom → Bespoke)
                └── No → Pattern 4 (Single-vendor → Multi-vendor → Integrator)
```

Most procurement reports land on Pattern 1 or 3. Patterns 2 and 4 mostly come up for service and project scoping.

---

## Anti-patterns

- **Naming the symptom as the alternative.** "The window is noisy" is not an alternative — "replace the felpa" is.
- **Three identical alternatives.** If A, B, and C all sit in Tier 3 with slightly different brands, you didn't decompose, you shopped. Span the cost-disruption axis.
- **Skipping the cheapest rung.** Always include the Tier-1 fix even when you think the user wants Tier-4. The Tier-1 option is the honest anchor.
