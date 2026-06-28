# Provider Taxonomy

A 5-tier model for classifying who can supply each alternative in a procurement report. The tier *isn't* about quality or trust — it's about **how much of the work the provider does**, which is the dominant cost driver.

---

## The 5 tiers

### Tier 1 — DIY-Retail

**What they sell:** Consumables, parts, off-the-shelf SKUs. The user installs / uses / consumes.

**Cost structure:** Catalog price; volume discounts; low margin on commodities, higher margin on accessories.

**When this tier is the answer:** when the dominant failure mode is a worn part or a missing consumable, and the user is comfortable installing.

**Examples by domain:**
- Construction: Homecenter (Sodimac), Easy, Constructor (CO); Home Depot, Lowe's (US).
- Tech: Best Buy, Mercado Libre, Amazon.
- Office: Falabella, Mercado Libre.
- Auto: AutoZone, AutoParts.

**Signal it's the right tier:** the user said "I'll do it myself" or "what tool do I need" or the failure mode is well-understood and the part is cheap.

---

### Tier 2 — Mid-Retail / Specialty Product

**What they sell:** Specialty products with optional installation. Often manufacturer-branded but sold through resellers.

**Cost structure:** Product margin + optional install fee. Install is often subcontracted.

**When this tier is the answer:** when the spec is more demanding than a commodity, but the install is straightforward.

**Examples by domain:**
- Construction: Pavco showroom, Pintuco store, Corona brand store. (CO)
- Tech: Apple Store, brand reseller (Dell Premier).
- Furniture: Tugó, Tramontina, Crate & Barrel.
- Auto: dealer accessories department.

**Signal it's the right tier:** the user wants a specific brand or spec, doesn't mind paying for the brand premium, and either installs themselves or has it installed by the seller.

---

### Tier 3 — Fabricator / Manufacturer / Specialty Service

**What they sell:** Custom products built to spec, or one-step-up specialty services. Often regional or independent businesses.

**Cost structure:** Setup fee + materials + labor; lead time meaningful (1–8 weeks typical).

**When this tier is the answer:** when the standard SKU doesn't fit and customization is real.

**Examples by domain:**
- Construction: aluminum workshop (taller de aluminios), carpenter, locksmith, wrought-iron shop.
- Tech: contract software house, custom hardware fab.
- Furniture: independent carpenter, upholsterer.
- Auto: independent mechanic, custom shop.

**Signal it's the right tier:** the user described constraints that don't map to a SKU (irregular sizes, specific aesthetics, integration with existing system).

---

### Tier 4 — Contractor / Installer

**What they sell:** End-to-end service for a defined scope. Sources materials, brings labor, delivers a working result.

**Cost structure:** Fixed-price or T&M; markup on materials (10–25%) + labor. Liability on the result.

**When this tier is the answer:** when the user wants a working result without managing the parts.

**Examples by domain:**
- Construction: general contractor, HVAC installer, electrician, plumber.
- Tech: managed-services provider (MSP), implementation partner.
- Events: catering company, AV company.

**Signal it's the right tier:** the user said "I just want it done" or the scope crosses trades the user can't coordinate themselves.

---

### Tier 5 — Consultant / Engineer / Turnkey / Integrator

**What they sell:** Advisory, design, supervision, or full-scope project management. The most strategic and the most expensive per hour.

**Cost structure:** Hourly / day-rate, fixed-fee for scoped engagements, or % of project cost for integration roles.

**When this tier is the answer:** when the decision itself is hard, the scope is uncertain, or the project is large enough that 10–25% overhead on coordination saves more than it costs.

**Examples by domain:**
- Construction: architect, structural engineer, acoustic consultant.
- Tech: management consultant, enterprise architect, fractional CTO.
- Finance: tax advisor, wealth manager, M&A advisor.
- Health: specialist physician, second-opinion service.

**Signal it's the right tier:** the user is uncertain about what to do, not just who to hire; the project is multi-trade and high-stakes; or the user explicitly wants supervised end-to-end execution.

---

## Tier picking — rules of thumb

| Situation | Tier likely most useful |
|---|---|
| Existing system, known failure mode, cheap part | T1 |
| Spec'd product, install simple, brand matters | T2 |
| Standard doesn't fit, customization real | T3 |
| Multi-trade or "just want it working" | T4 |
| Decision itself is hard, or project is large + multi-trade | T5 |

### Diversity bias for grounded reports

For a `standard` or `deep` procurement run, **always cite at least two tiers** in the report. The Tier-1 anchor gives the user a price floor; the higher tier gives them a benchmark for what they're really comparing against. A report with only Tier-4 quotes hides the alternative of doing it cheaper.

---

## Locale-specific examples

Provider names map differently per market. Examples below for the two most common procurer locales.

### Colombia (CO)

| Tier | Examples |
|---|---|
| T1 | Homecenter, Sodimac, Easy, Constructor, Mercado Libre, Falabella |
| T2 | Corona, Alfagres, Pintuco, Pavco, Grival store, Tramontina showroom |
| T3 | Tallér de aluminios (local), carpintero (local), Vitelsa, Tecnoglass-distribuidor |
| T4 | Constructora local, instalador-de-vidrio, contratista de plomería |
| T5 | Arquitecto independiente, ingeniero acústico (e.g. AcustiCo), gerencia de proyecto |

### United States (US)

| Tier | Examples |
|---|---|
| T1 | Home Depot, Lowe's, Amazon, Best Buy |
| T2 | Apple Store, IKEA, manufacturer-direct online (Andersen, Pella) |
| T3 | Local fabricator, custom millwork shop |
| T4 | General contractor, MEP subs |
| T5 | Architect, structural engineer, consulting firm |

For other locales, ask the user for their region before searching — supplier networks diverge sharply.

---

## What changes the tier mapping

- **Project size.** A T5 architect on a $1,000 job is overkill; on a $100,000 job is cheap.
- **User's bandwidth.** A user with no time should bias toward T4/T5 even when T2/T3 would be cheaper.
- **Repeat factor.** If the user will need this category again, a T5 consultant who teaches them how to do it themselves pays for itself.
- **Regulatory load.** Some scopes (electrical, gas, structural) require a licensed provider — that pushes T4 minimum.

---

See also: `decomposition-patterns.md` for *what* the alternatives are, and `mode-tiers.md` for *how many* providers to cite per tier.
