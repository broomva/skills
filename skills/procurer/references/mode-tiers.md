# Mode Tiers — Fast / Standard / Deep

Procurement runs vary by stakes. A quick "roughly what does this cost" deserves a different budget than a $50M-COP decision. This file defines the three search modes with concrete budgets and latency targets.

The mode is chosen at **Stage 3** of the procurer procedure (see `SKILL.md`). Default to `standard` unless the user signals otherwise.

---

## Mode contracts

| Dimension | `fast` | `standard` | `deep` |
|---|---|---|---|
| **Use when** | Rough order of magnitude needed; user is exploring | Default for real decisions | High-stakes, multi-vendor decisions |
| **Web searches per alternative** | 1 | ≥ 3 | ≥ 6 |
| **Providers cited per alternative** | 1–2 | 3–5 | 5–7 |
| **Tier coverage per report** | 1 tier OK (T1 anchor only) | ≥ 2 tiers (T1 + ≥ 1 higher) | ≥ 3 tiers |
| **Confidence floor for any band** | 0.50 (with note) | 0.70 | 0.80 |
| **Cross-locale fallbacks** | OK with note | Discount confidence | Not allowed; fail explicitly |
| **Latency target** | < 1 min total | 3–5 min | best-effort, no SLA |
| **Report length** | 1 page / 200–400 words | 2–3 pages / 600–1,000 words | 4+ pages / 1,500+ words |
| **Recommendation depth** | Picks one alternative, single rationale line | Picks one + names fallback + budget envelope | Picks one + names fallback + budget envelope + scenario sensitivity (worst case, best case, lead-time tradeoffs) |

---

## Mode triggers

### Use `fast` when
- The user opens with "roughly" / "ballpark" / "give me a number" / "quickly".
- The decision is < $200 USD-equivalent or < $1M COP.
- The user already knows what they want, just wants to know the price.
- A previous procurer run on the same need ran in `standard` or `deep` recently; this is a refresh.

### Use `standard` when (default)
- The user is making an actual buy/hire decision.
- The decision is $200–$10,000 USD-equivalent ($1M–$40M COP).
- The user wants to compare alternatives.
- No explicit signal of urgency or thoroughness.

### Use `deep` when
- The user says "thorough" / "executive report" / "I need the full picture" / "presenting this to <board / client>".
- The decision is > $10,000 USD ($40M COP).
- Multi-vendor / multi-trade scope.
- Implementation will take > 2 weeks (long lead times warrant deeper diligence).
- The user is allocating a procurement budget for a team or a project.

### Auto-escalation triggers

Within a run, auto-escalate to the next mode if:

- `fast` → `standard`: only 1 provider found across all alternatives; user explicitly asked to compare; price spread > 3× between the 1 cited and any second-hand reference.
- `standard` → `deep`: price spread > 2× between cited providers; only 1 tier covered after 3+ searches per alternative; user explicitly asked for thoroughness mid-run.

Always notify the user when escalating: "Standard search surfaced only one provider; escalating to deep to widen coverage. Latency budget extends accordingly."

---

## Budget caps

Procurement search isn't free — it costs latency, sometimes API calls, and the user's attention. Soft caps per mode:

| Mode | Max wall-clock | Max web searches | Max words in report |
|---|---|---|---|
| `fast` | 90 s | 5 | 500 |
| `standard` | 6 min | 20 | 1,200 |
| `deep` | best-effort, but warn at 20 min | 50 | 2,500 |

These caps are the agent's reflex. When a cap is hit:
- Stop searching.
- Render the report with what's available.
- Mark any unfilled cells explicitly: *"No public price located in budget; recommend operator outreach to provider X for direct quote."*

---

## Mode-specific search strategies

### `fast` strategy

1. Identify the single most-likely provider tier (usually T1 retail).
2. One search per alternative: `<sku> <T1 provider name>`.
3. Read the price off the first product-page hit. Don't second-source.
4. Render the report with 1–2 providers cited; recommend `standard` if user wants more.

### `standard` strategy

1. For each alternative, plan 3 searches: one T1 retail anchor + one T2/T3 specialty + one T4 contractor (when applicable).
2. Run them in sequence; if any return no result, swap to a sibling provider in the same tier.
3. Capture all 3 prices with confidence per `grounding-discipline.md` Rule 3.
4. If after 3 searches per alternative only 1 tier is covered, do a 4th search to widen tier coverage before rendering.

### `deep` strategy

1. For each alternative, plan ≥ 6 searches: T1 anchor + 2–3 specialty/manufacturer + 2–3 contractor/integrator/consultant quotes.
2. Include quote-on-request signals: when a manufacturer's page says "cotización a solicitud", note this and capture a representative market range from prior transactions if available.
3. For multi-trade scopes, search the integrator tier (T5) separately and price the bundled cost vs. the sum of sub-tier prices to surface the integrator's overhead.
4. Compute sensitivity: what does the budget envelope look like at worst-case (highest cited prices), expected (median), and best-case (lowest cited prices)?
5. Render the report with cited providers, scenario sensitivity, and a clear recommendation including fallback paths.

---

## Anti-modes (don't do this)

- **`xfast`** — running without any web search, citing only training data, calling it "fast". Never. Either run web searches or mark the report as unsourced calibration.
- **`deeper`** — exceeding the deep cap to hunt for one more provider. Diminishing returns; the marginal vendor rarely changes the recommendation. Render and ship.
- **`bespoke`** — designing a special mode for one report. The three tiers cover the space; pick one.

---

See also: `grounding-discipline.md` for the citation rules each mode enforces, and `report-template.md` for the mode-specific report shapes.
