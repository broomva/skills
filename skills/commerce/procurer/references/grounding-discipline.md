# Grounding Discipline

The non-negotiable rules for sourcing every price, citation, and confidence score in a procurement report. These rules exist to prevent the failure mode that destroys procurement research: **plausible-sounding numbers with no provenance**.

If the report violates these rules, it isn't procurement research — it's a hallucinated wishlist. The user *will* commit money based on it. Take the rules seriously.

---

## Rule 1 — Every price has a citation

> No bare numbers. Every cost band that appears in the report carries an explicit source attribution.

For each price-bearing observation, capture:

- `source_url` — URL where the price was read. Prefer product/SKU pages over category pages, and category pages over homepages.
- `source_title` — the page title or product name as the provider displays it. Disambiguates when URLs are session-encoded.
- `fetched_at` — ISO-8601 UTC timestamp of when the price was read. Prices age fast (commodity materials, currency volatility); the timestamp is the freshness signal.
- `provider_name` — the human-readable supplier name (e.g., "Homecenter", "Tecnoglass").
- `provider_tier` — T1 / T2 / T3 / T4 / T5 from `provider-taxonomy.md`.

If the agent has no web-fetching tool available, mark every band as **unsourced calibration** and tell the user explicitly: "These ranges are from prior knowledge; before committing, run a sourced pass with web search."

---

## Rule 2 — No fabrication

> If no public price exists for an `(alternative, provider)` pair, leave it empty. Never fill from training data.

Specifically:

- **Quote-on-request products** (most contractors, most T5 services) — record the quote-on-request signal explicitly: `"Tecnoglass — cotización a solicitud, no public price page; estimate range from prior CO market data: $1.5M–2.5M COP/m²; confidence 0.6."`
- **Out-of-stock products** — note the listing exists but the price isn't currently shown.
- **Discontinued products** — note and propose the closest current equivalent.
- **Region-mismatched products** — if the only public price is from a different region, note the locale gap and discount confidence.

Filling empty cells with training-data numbers is the most damaging failure mode of this skill. Better to ship an incomplete report than a polished one with invented numbers.

---

## Rule 3 — Confidence (0–1) on every band

Each cost band carries a confidence score reflecting source quality:

| Confidence | Source quality |
|---|---|
| **≥ 0.90** | Exact product page. SKU + unit + currency + tax-treatment all explicit. Fetched within last 7 days. |
| **0.75 – 0.89** | Listing or quote page exists, but one of: unit needs interpretation; spec doesn't fully match; tax treatment ambiguous; > 30 days old. |
| **0.50 – 0.74** | Category-level price, comparable product, or quote-on-request market estimate from a recent transaction. Locale matches. |
| **< 0.50** | Inferred from market familiarity / training data / different locale. **Flag in report and recommend a sourced refresh before committing.** |

Confidence is not a vibe — it's a defensible position the agent should be able to explain when asked.

---

## Rule 4 — Unit and currency normalization

> All bands in one report must use the **same currency** and the **same unit conventions per category**.

### Currency

- Default to the **user's locale currency** (COP for CO, USD for US, EUR for Eurozone, etc.).
- If the user is multi-locale (e.g., Broomva operates CO + DE), ask. Don't assume.
- Use the locale's thousand/decimal conventions (CO: `$ 1.250.000`; US: `$1,250,000`).
- When converting from a foreign-priced source, capture the FX rate used and timestamp it: `"USD 850 → COP 3,400,000 (FX 4000, fetched 2026-05-13)"`.

### Tax / VAT / IVA

- Be explicit about tax inclusion. Three states:
  - `"Precio con IVA 19%"` — price already includes tax.
  - `"Precio sin IVA — agregar 19%"` — add tax to the figure.
  - `"IVA no aplica"` — exempt category (e.g., medical, some services).
- For CO procurement: also flag ReteFuente / ReteIVA / ReteICA when the user is a corporate buyer above DIAN thresholds, but mark these as informational (the buyer's accountant computes them).
- For US procurement: sales tax varies by state; flag as `"+ state sales tax"` unless the source page shows tax-inclusive.

### Units

- Normalize to category-canonical units (see `provider-taxonomy.md`):
  - Sheet goods → per m² (CO) or per ft² (US).
  - Pipes / wires / cables → per linear meter (ml) or per linear foot.
  - Bulk materials → per kg, per ton, per saco (50 kg or 42.5 kg).
  - Services → per hour, per visit, or per project (state which).
- When a source uses a different unit, convert and show both: `"$25,000/galón ≈ $6,600/litro"`.

---

## Rule 5 — Sanity bands

For each category, the agent knows roughly what the market median is. If an observed price falls outside `[median / 2, median × 2]`, **don't drop it — flag it in `notes`** and let the user decide:

- `"Outlier-high: 2.3× market median. Provider may include premium service or specification beyond standard."`
- `"Outlier-low: 0.4× market median. Verify SKU matches and that provider is not a clearance / open-box."`

Sanity bands per category live in the locale-specific examples (see `assets/examples/construction-materials-co.md` for the CO seeds). For new categories, the agent computes a rough median from the cited observations and applies 2× on each side.

---

## Rule 6 — Diversity bias

For `standard` and `deep` modes (see `mode-tiers.md`):

- Cite **≥ 2 tiers** per report — typically a T1 anchor and a T3+ benchmark.
- For each individual alternative spanning multiple tiers, cite **≥ 1 provider per tier** spanned.
- For a `standard` price comparison within one alternative, **≥ 3 providers** total.

The reason: a single-tier report hides the structural choice. A report citing only T4 contractors hides the option of going T2; a report citing only T1 hides the option of professional install. Diversity is the report's honesty signal.

---

## Rule 7 — Locale-aware suppliers

> Use suppliers/domains appropriate to the user's market.

- **Default the locale to the user's stated region.** If the user didn't state it, ask before searching.
- For CO: prefer `homecenter.com.co`, `sodimac.com.co`, `easy.com.co`, `pintuco.com.co`, `corona.co`, etc. See `assets/examples/construction-materials-co.md` for the CO allowlist.
- For US: prefer `homedepot.com`, `lowes.com`, `amazon.com`, `bestbuy.com`, etc.
- **Marketplaces are second-best.** A Mercado Libre / Amazon listing is fine as a fallback but loses confidence vs. a manufacturer or branded retailer's product page.
- **Never cite forums, blogs, or AI-summarized prices as primary.** Use them only for context, never for the band numbers.

---

## Rule 8 — Flag the dominant failure mode

This is grounding discipline at the **problem level**, not the data level.

> Before the cost-band table, name the **dominant failure mode** of the user's existing situation.

If 80% of the user's problem can be solved by a Tier-1 intervention, **say so loudly** in the Problem framing section. Don't let the user commit Tier-4 money to solve a problem a Tier-1 fix would handle.

Examples:

- *Window noise*: "80–90% of perceived noise on a sliding-window installation comes from seal leakage, not glass mass. The Tier-1 felpa replacement captures most of the available improvement at 5% of the Tier-3 glass replacement cost."
- *Slow laptop*: "Most performance loss on laptops > 3 years old is storage saturation, not CPU. The Tier-1 SSD swap captures most of the speed at 10% of a new-machine purchase."
- *Hot bedroom*: "Most heat ingress on Bogotá apartments above floor 10 is direct sun on west-facing windows. Tier-1 reflective film addresses a larger share than Tier-4 mini-split installation in many cases."

Honesty about the failure mode is the procurer's most valuable single output. It's also what separates the skill from a marketplace search.

---

## Composite checklist

Before rendering the report, the agent verifies:

- [ ] Every cost band has at least one citation with `source_url`, `source_title`, `fetched_at`, `provider_name`, `provider_tier`.
- [ ] Confidence scores assigned per Rule 3 criteria, not guesses.
- [ ] All amounts in the same currency with locale conventions.
- [ ] Tax treatment explicit for each band.
- [ ] Units normalized to category canonical.
- [ ] At least 2 tiers cited (for standard/deep).
- [ ] Suppliers locale-appropriate.
- [ ] Dominant failure mode named in Problem framing.

If any box is unchecked, fix before rendering. If a check is impossible (e.g., no web tool), mark the report as **unsourced calibration** and tell the user.

---

See also: `mode-tiers.md` for how many searches to run per band, and `report-template.md` for the final shape.
