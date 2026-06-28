# Window Noise Attenuation — Bedroom on Bogotá Avenue

> **Worked example.** Output shape of one `standard`-mode procurer run on a real need surfaced in conversation 2026-05-13. Treats the live answer Claude gave in chat as the unsourced-calibration baseline; a real run would replace `[citation pending]` placeholders with grounded sources from Homecenter, Sodimac, Tecnoglass, Vitelsa, etc.
> 
> **Use this as a reference shape, not as final price data.** The bands here are calibration ranges informed by CO market familiarity, not citations.

---

# Reduce traffic noise from bedroom window on a Bogotá avenue

**Locale:** CO Bogotá  
**Currency:** COP  
**Mode:** standard (calibration; replace placeholders with sourced run before committing)  
**Generated:** 2026-05-13T17:00Z

## Problem framing

The bedroom faces an avenue. Existing window is an aluminum slider with brush-pile (felpa) seals. The user reports that the windows attenuate "some" noise but traffic is still audible.

**Dominant failure mode (Grounding Rule 8):** sliding windows leak sound primarily through **seal path** (brush felpa is a wind-stop, not a sound-stop — air gaps between bristles transmit ~30–50% of acoustic energy on a 1% gap area). The **glass path** (monolithic 4–6 mm pane has a coincidence dip in the 1–4 kHz traffic band) is the secondary leak. **Flanking path** (aluminum frame) is third-order.

This means **the cheapest Tier-1 intervention captures the largest share of the available improvement.** The user should not commit Tier-3 money before trying Tier-1.

## Alternatives

### Alternative A — Tier-1 fix: replace seals, adjust rollers, add curtains   (Tiers: T1)

**Thesis.** Close the dominant failure mode (felpa-seal leakage) without modifying the window system. Captures 30–50% of available perceived-noise reduction at 5% of the Tier-3 cost.

**Cost band (COP).**
- Low: $ 80.000 (felpa only, DIY)
- Typical: $ 250.000 (felpa + acoustic curtains + roller-adjust labor)
- High: $ 600.000 (premium blackout/acoustic curtain + installer)

**Confidence:** 0.65 (unsourced calibration; needs sourced refresh — felpa pricing is well-known per-meter, curtain pricing varies widely).

**Providers cited (N=4 expected after sourced run):**
| Tier | Provider | Price | Unit | Confidence | Source |
|---|---|---|---|---|---|
| T1 | Homecenter | $ 5.000–15.000 | metro felpa siliconada | — | [citation pending] |
| T1 | Sodimac | $ 4.500–12.000 | metro felpa siliconada | — | [citation pending] |
| T1 | Easy | $ 4.500–14.000 | metro felpa siliconada | — | [citation pending] |
| T1 | Mercado Libre — local ferretería | $ 80.000–250.000 | cortina acústica 2×2m | — | [citation pending] |

**Notes.**
- Felpa "siliconada" / "con aleta" (dual-fin with center plastic film) is the correct upgrade; replace the brush-only stock seal.
- Roller adjustment is a screw on the bottom-rail (visible in user photo IMG_7082). Free if DIY; ~$80k if you hire an aluminios installer for 1 hour.
- Curtains help mid-high frequencies only; expect 3–5 dB perceived reduction.
- Excludes IVA where listed; CO buyer should budget IVA 19% on materials.
- **Lead time:** same-day to 48h.

### Alternative B — Tier-2/3 augmentation: internal acoustic secondary window   (Tiers: T3 → T4)

**Thesis.** Add a second glazed barrier inside the existing window with a 5–10 cm air gap. The air gap kills low-frequency rumble that single-pane mass solutions miss. Typical Rw improvement: 15–25 dB on top of existing window.

**Cost band (COP).**
- Low: $ 600.000 / m² (acrylic magnetic insert, DIY-spec'd / custom-fab)
- Typical: $ 900.000 / m² (casement secondary window, 6mm laminated, installed)
- High: $ 1.300.000 / m² (premium acoustic interior, dual-laminated, gasketed)

**Confidence:** 0.60 (unsourced calibration; CO secondary-window market is fragmented across local talleres de aluminios, prices vary 1.5× across providers).

**Providers cited (N=3–5 expected after sourced run):**
| Tier | Provider | Price | Unit | Confidence | Source |
|---|---|---|---|---|---|
| T3 | Local taller de aluminios (Bogotá centro) | cotización a solicitud | m² instalado | — | [citation pending] |
| T3 | Vitelsa | cotización a solicitud | m² instalado | — | [citation pending] |
| T4 | Constructora Acústica CO (varios) | cotización a solicitud | m² instalado | — | [citation pending] |

**Notes.**
- "Ventana interior" / "contraventana acústica" — terminology to use when calling talleres.
- Single most effective intervention short of full replacement.
- Reversible — can be removed if the user moves.
- Excludes IVA; install includes labor + materials in cited bands.
- **Lead time:** 2–4 weeks for fabrication + 1 day install.
- **Outlier-low flag:** any quote below $ 500k/m² is suspect (verify SKU includes laminated glass, not just monolithic).

### Alternative C — Tier-3/4 replacement: full acoustic DVH + casement frame   (Tiers: T3 → T4)

**Thesis.** Replace the slider with a casement (compression-seal) frame and laminated DVH (asymmetric panes, PVB acoustic interlayer). Typical Rw 38–42 dB vs ~25–28 dB current. Only justified if the user is already renovating or wants the thermal/aesthetic side-benefits.

**Cost band (COP).**
- Low: $ 1.200.000 / m² (entry acoustic DVH, casement, no premium brand)
- Typical: $ 1.700.000 / m² (Tecnoglass / Vitelsa / Alfa with acoustic-rated DVH)
- High: $ 2.500.000 / m² (premium PVB Saflex Q / Trosifol SC, tilt-turn frame)

**Confidence:** 0.70 (CO acoustic DVH market priced via manufacturer distributors; bands well-anchored).

**Providers cited (N=4–6 expected after sourced run):**
| Tier | Provider | Price | Unit | Confidence | Source |
|---|---|---|---|---|---|
| T3 | Tecnoglass distribuidor Bogotá | cotización a solicitud | m² instalado | — | [citation pending] |
| T3 | Vitelsa | cotización a solicitud | m² instalado | — | [citation pending] |
| T3 | Alfa Arquitectura y Concreto sub | cotización a solicitud | m² instalado | — | [citation pending] |
| T4 | Constructora local con ventanería | cotización a solicitud | proyecto | — | [citation pending] |

**Notes.**
- **Ask for the Rw rating with documentation.** Most CO suppliers quote DVH without acoustic certification — that's a red flag.
- A real acoustic window will have a test certificate showing Rw ≥ 35 dB.
- Casement (batiente) or tilt-turn (oscilobatiente) only — sliders disqualify the acoustic spec.
- Includes demolition + install + interior re-finishing (~20% of bare DVH cost typically rolled in).
- IVA 19% applies; corporate buyers add ReteFuente 4% on services.
- **Lead time:** 6–10 weeks (fabrication-limited, especially on imported acoustic laminate).

### Alternative D — Tier-5 advisory: acoustic engineer assessment (optional pre-step)   (Tiers: T5)

**Thesis.** Before committing Tier-3 money, hire 2–4 hours of an acoustic engineer to measure current Rw, identify the dominant leak path empirically, and confirm whether B or C is actually warranted. Pays for itself if it prevents an unnecessary C-tier purchase.

**Cost band (COP).**
- Low: $ 350.000 (single-visit measurement, no report)
- Typical: $ 800.000 (visit + 2-page report with recommendations)
- High: $ 2.500.000 (full residential acoustic audit with 3D modeling)

**Confidence:** 0.55 (acoustic consultancy in CO is small, prices vary widely; CR1 / AcustiCo / independent consultants).

**Providers cited (N=2–3 expected after sourced run):**
| Tier | Provider | Price | Unit | Confidence | Source |
|---|---|---|---|---|---|
| T5 | AcustiCo (Bogotá) | cotización a solicitud | visita | — | [citation pending] |
| T5 | Consultor acústico independiente | cotización a solicitud | visita | — | [citation pending] |

**Notes.**
- Skip if user is committing < $ 2M total; the consultant fee is too high a share.
- Worth it if user is contemplating C (>$ 5M total).

## Cross-cutting notes

- **Tax treatment.** All bands exclude IVA 19% unless noted. Corporate buyers add applicable retenciones (ReteFuente 4% on services + ReteICA per municipio).
- **Bogotá supplier shortlist.** 
  - T1 retail: Homecenter (multiple stores), Sodimac (Av 68 + Calle 80), Easy.
  - T3 fabricators: Paloquemao / 7 de Agosto area concentrates the talleres de aluminios.
  - T3 manufacturers: Tecnoglass (representante Bogotá), Vitelsa (Calle 80), Alfa.
  - T5 consultants: AcustiCo, independent acoustic engineers (search "ingeniero acústico Bogotá").
- **Hidden costs.** Interior re-finishing (paint, drywall touch-up) often 15–20% above bare-installed window cost on a replacement. Curtain rod / hardware for Alternative A's curtain step is ~$ 50–150k extra not in the band.
- **Lead times.** A: same-day. B: 2–4 weeks. C: 6–10 weeks. D: 1–2 weeks for the consultant visit.
- **Locale calibration.** Bogotá apartments above floor 12 on major avenues (Calle 80, Carrera 7, Av Boyacá, Calle 26) show consistent 60–72 dBA daytime traffic noise — the user's experience is typical for the geography.

## Recommendation

**Start with:** Alternative A (Tier-1 felpa + rollers + curtains).

**Total budget envelope:** $ 80.000 – $ 600.000 COP (one-time, weekend execution).

**Rationale (3 sentences).** The dominant failure mode on a brush-felpa aluminum slider is seal leakage, which Alternative A addresses directly at ~5% of Alternative C's cost. The user should run A first, give it 2–3 weeks of lived experience, and only escalate if the residual noise is still meaningful. The cost of A is small enough that running it as a diagnostic is rational even if the user later commits to C.

**If that doesn't work:** Alternative B (internal acoustic secondary window) — $ 600k–1.3M COP/m² installed. Escalate to B only if Alternative A's perceived noise reduction is < 50% after 2–3 weeks of daily use, or if low-frequency rumble (trucks, motos with modified exhausts) is the dominant residual complaint.

**Skip Alternative C** unless the user is already renovating that wall or wants the thermal/aesthetic side-benefits. C is over-spec'd for noise alone after B is in place.

**Alternative D (consultant)** is worth it only if the user is contemplating C without renovation; for the A → B path, A's diagnostic value substitutes for it.

## Sources

*[citation pending]* — Sourced refresh required before committing. The bands in this report are calibration ranges from prior CO market knowledge and conversation context, not live citations. Recommend a `standard`-mode procurer run with `WebSearch` enabled to convert placeholders into Homecenter / Sodimac / Tecnoglass / Vitelsa product pages.

---

## What this example demonstrates

- **Pattern 1 decomposition** (Incremental → Augmentation → Replacement) plus an optional **Tier-5 consultant** rung as a diagnostic.
- **Honest framing of the dominant failure mode** (felpa-seal leakage) before the alternatives, per Grounding Rule 8.
- **Cost-disruption span** across three orders of magnitude (A: $80k–$600k; B: $600k–$1.3M/m²; C: $1.2M–$2.5M/m²).
- **Explicit recommendation with a fallback condition** ("if A doesn't reduce ≥50% in 2–3 weeks, escalate to B").
- **Locale-aware** suppliers, tax handling, lead times.
- **Confidence transparency** — every band carries a confidence reflecting that this is unsourced calibration, not a live grounded run.
