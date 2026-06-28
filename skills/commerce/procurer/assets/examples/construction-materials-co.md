# Colombian Construction Materials — Locale Reference

A locale-specific reference for procurer runs covering CO construction materials. Lifted and generalized from the `materiales-intel.v1` rules-package skeleton at `freelance/_pending-constructora/rules-package/`.

This file is **reference data** — supplier shortlists, family taxonomy, sanity bands, tax notes — to compound on top of `references/grounding-discipline.md` when a procurer run touches CO construction.

> **Note.** This reference is *informational* — it doesn't replace running grounded web searches per Rule 1. Use it to pre-narrow the supplier search space and validate sanity bands against historical CO market knowledge.

---

## Supplier shortlist by tier (CO)

### Tier 1 — Grandes superficies (national retail chains)

| Provider | Domain | Notes |
|---|---|---|
| Homecenter | homecenter.com.co | Largest national chain; full catalog; reliable price page. |
| Sodimac | sodimac.com.co | Same parent as Homecenter; some store-by-store price variation. |
| Easy | easy.com.co | Smaller footprint; pricing competitive on bulk. |
| Constructor | constructor.com.co | Cemex's retail brand; strong on basics. |

### Tier 2 — Fabricantes / marcas líderes (manufacturer direct, branded)

| Provider | Domain | Categories |
|---|---|---|
| Argos | argos.co | Cemento gris/blanco. |
| Cemex | cemex.com | Cemento; ready-mix. |
| Holcim | holcim.com.co | Cemento. |
| Ultracem | (search) | Cemento — regional. |
| Corona | corona.co | Cerámica, sanitarios, grifería. |
| Alfagres | alfagres.com | Pisos cerámicos / porcelanatos. |
| Grival | grival.com.co | Grifería. |
| Pavco | pavco.com.co | Tubería PVC/CPVC. |
| Pintuco | pintuco.com.co | Pintura. |

### Tier 3 — Especializados (branded, narrower catalog)

| Provider | Domain | Categories |
|---|---|---|
| Cerámica Italia | ceramicaitalia.com.co | Cerámicas, baldosas. |
| FV | fv.com.co | Grifería premium. |
| Acquagrif | acquagrif.com | Grifería. |
| Gerfor | gerfor.com | Tubería. |
| Tigre-Celta | tigrecelta.com.co | Tubería. |
| Sherwin-Williams | sherwin.com.co | Pintura premium. |
| Gerdau Diaco | (search) | Hierro / acero estructural. |
| Acerías Paz del Río | (search) | Hierro. |
| Ternium | (search) | Hierro. |
| Sidoc | (search) | Hierro. |
| Tecnoglass | tecnoglass.com | Vidrio (DVH, laminado, acústico). |
| Vitelsa | (search) | Ventanería de aluminio. |

### Tier 4 — Contratistas / instaladores

- Constructora local (Bogotá / Medellín / Cali).
- Instalador de vidrio / aluminios independiente.
- Contratista de plomería, electricidad, pintura por gremios separados.

### Tier 5 — Consultores / arquitectos / ingenieros

- Arquitecto independiente.
- Ingeniero estructural (cuando el alcance toca estructura).
- Ingeniero acústico (e.g., AcustiCo para ventanería acústica).
- Gerencia de proyecto (para obras > 200 M COP).

---

## Familia taxonomy (canonical units + synonyms)

For each family the agent uses these canonical units when normalizing prices. Synonyms help search-query construction.

| Familia | Canonical unit | Synonyms / search terms |
|---|---|---|
| hierro | unidad (varilla); kg; ton | varilla, hierro figurado, hierro liso, hierro corrugado, acero de refuerzo |
| cemento | saco (50 kg or 42.5 kg) | cemento gris, cemento blanco, cemento portland, Argos, Cemex, Holcim, Ultracem |
| pisos | m² | porcelanato, cerámica, gres porcelánico, piso mate, piso pulido |
| baldosas | m² | baldosa, enchape muro, enchape piso, revestimiento cerámico |
| griferia | unidad | grifo, grifería, llave, lavamanos, sanitario, ducha, monomando |
| tuberia_pvc | metro lineal (ml) | tubería PVC, tubo PVC, PVC presión, PVC sanitaria, Pavco, Gerfor |
| tuberia_cpvc | metro lineal (ml) | tubería CPVC, agua caliente, Pavco CPVC |
| pintura | galón / cuñeta | pintura, vinilo, esmalte, anticorrosivo, Pintuco, Sherwin, Corona |
| electrico | metro lineal (ml) | cable AWG, canaleta, caja de paso, tomacorriente, breaker, interruptor |

### Sanity-band multipliers (flag outliers at > N× the family median)

| Familia | Multiplier |
|---|---|
| hierro | 1.5× |
| cemento | 1.3× |
| pisos | 2.0× |
| baldosas | 2.0× |
| griferia | 2.5× |
| tuberia_pvc | 2.0× |
| tuberia_cpvc | 2.0× |
| pintura | 1.8× |
| electrico | 2.0× |

Lower multiplier = tighter market (commodity-shaped, e.g. cemento). Higher multiplier = wider market (spec-driven, e.g. grifería).

---

## Tax handling (CO)

- **IVA** = 19% on most goods and services. Flag in every band:
  - `"Precio con IVA 19% incluido"` if the source page shows tax-inclusive.
  - `"Precio sin IVA — agregar 19%"` if the source page shows the bare commercial price.
- **Retenciones** (informational for corporate buyers):
  - ReteFuente: 2.5% on goods, 4% on services (above DIAN umbral).
  - ReteIVA: 15% of the IVA, when retainer applies.
  - ReteICA: varies by municipio (Bogotá: 6.96‰ to 13.8‰ depending on actividad económica).
- **Personas naturales** generally don't apply retenciones on small purchases.
- **Régimen simple / Régimen común** — affects RUT-side handling, not the procurement price itself.

State tax treatment explicitly per band; never silently assume IVA-inclusive or IVA-exclusive.

---

## Regional notes

| Region | Notes |
|---|---|
| **Bogotá** | Largest market; best supplier diversity; most price discovery available online. |
| **Medellín** | Strong on aluminum/glass (proximity to manufacturers); some category leadership (e.g. Tecnoglass headquarters). |
| **Cali** | Strong on cement (Cemex, Argos regional); lighter on premium specialty. |
| **Eje Cafetero** (Pereira/Manizales/Armenia) | Mid-market depth; some online presence; bias toward local distributors. |
| **Costa Caribe** (Barranquilla/Cartagena/Santa Marta) | Stronger import / international flow; premium specialty available via Barranquilla port; humidity affects spec choices (e.g. acabados marinos). |
| **Oriente** (Bucaramanga + Cúcuta) | Mid-tier; commodity strong; specialty thinner online. |

For regions outside Bogotá, ask the user whether to:
1. Search the user's region first (locale-pure).
2. Use Bogotá as a price anchor (broader supplier base, may not deliver to user's region without freight).

---

## Common procurement-flow patterns for CO construction

These are the canonical decompositions for the most-asked CO procurer questions:

### "How much will it cost to build/renovate <X>?"

Pattern 4 — Single-vendor → Multi-vendor → Integrator. Default to multi-vendor + arquitecto supervision for residential renovations $20M–$200M; recommend integrator for >$200M.

### "What's the price of <material> for my obra?"

Pattern 3 — Standard → Custom → Bespoke. Standard SKU at T1 retail anchors the floor; T2/T3 manufacturer-direct often beats T1 above a volume threshold (~5M COP).

### "Should I buy <material> retail or get the manufacturer?"

Pattern 4 in miniature — usually T1 retail wins under 1M COP, T2/T3 manufacturer wins above 5M COP (volume discount), tie zone in between.

### "Who can install <X>?"

Pattern 4 directly — Single-vendor (retailer-bundled install) vs. Multi-vendor (separate trades) vs. Integrator (contratista general). Most residential users default-pick Multi-vendor and discover Integrator's value too late.

---

## When this reference applies

Use this file when:

- User is in CO and the procurement involves construction materials, ventanería, plomería, eléctrico, pintura, pisos, baldosas, sanitarios.
- User asks for CO supplier shortlists or "where do I buy X in Bogotá / Medellín / etc."
- Tax treatment is ambiguous and needs explicit IVA / retención framing.
- Cross-referencing against the materiales-intel.v1 rules-package is useful (the canonical taxonomy lives here, not the rules-package — the rules-package is a deployed tenant artifact derived from this).

---

## Composition with the broader procurer skill

This file is consumed at Stage 1 (decomposition) and Stage 4 (grounded search) of the procurer procedure:

- **Stage 1** — When the family maps to one of the 9 CO construction families, the decomposition pattern is usually Pattern 1 (fix-it problems) or Pattern 3 (acquire-something problems).
- **Stage 4** — Use the supplier shortlist as the allowed-domain set for `WebSearch`; pre-filter results to known providers before broadening.

For a CO constructora tenant operating in production on the Life-runtime engine, the canonical artifact is the deployed rules-package, not this reference. The reference is for ad-hoc procurer runs and skill-internal calibration.
