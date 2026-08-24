# The crafted floor — what "premium, crafted with care" means operationally

Distilled 2026-08-18 from the practitioners who set the bar (Kowalski, Freiberg, Linear/Saarinen,
Coursey, Comeau, Wathan & Schoger, Butterick, Rams, Apple HIG, Material, GOV.UK, Vercel, Stripe/Dill,
NN/g, Fogg, WCAG, web.dev). Every rule is tagged **[M]** machine-checkable (grep / lint / axe /
Lighthouse / screenshot / E2E) or **[J]** judgment (needs a reviewer with a rubric). unslop's gate
implements the [M] subset it can reach statically; the [J] rows are the reviewer's checklist in the arc.

The floor is a *floor*: clearing it makes a surface not-embarrassing. Direction (the committed visual
world) is what makes it good, and no checklist supplies that — see `arc.md` §Direction.

> "You can have craft without quality, but rarely quality without craft." — Katie Dill (Stripe)
> "All of a product's details need to be correct before public release. But that doesn't mean it has
> to be perfect." — Karri Saarinen (Linear)

## 1. Typography

| Rule | Tag | Source |
|---|---|---|
| Body 15–25px on web; line-height 120–145% of size (1.5 as reset default) | M | Butterick; Comeau reset |
| Measure ≤75ch (target ~65ch); 45 minimum | M | Butterick 45–90; Refactoring UI 45–75; Kowalski 65 |
| All-caps needs +5–12% tracking; tighten display tracking, never below −0.04em | M | Butterick; RUI; impeccable floor |
| Curly quotes, one space after periods, `…` not `...`, real dashes only in prose | M | Butterick; Kowalski |
| Underline reserved for links; bold for UI emphasis; never bold+italic | M | Butterick |
| `font-variant-numeric: tabular-nums` on numeric columns / prices | M | Kowalski |
| Fallback stack matches x-height; `size-adjust` on the fallback to cut CLS | M | Kowalski; web.dev |
| ≤3 distinct weights carry hierarchy (Linear: 400–510 only) | M | RUI; Identity Forge on Linear |
| `-webkit-font-smoothing`, `font: inherit` on controls, `text-wrap: balance/pretty` | M | Comeau |
| The face is a *decision*: no AI-default face by accident, no system stack by omission | M+J | Butterick ("Arial is fatal to credibility"); Vercel; impeccable `overused-font` |
| Font sizes ∈ the scale; no arbitrary sizes, no "tiny muted prose" | M | Vercel reject list |

## 2. Spacing / layout / density

| Rule | Tag | Source |
|---|---|---|
| One spacing ladder (4/8/12/16/24/32/48/64/96), hand-tuned, even px | M | RUI; Linear 4px grid |
| Groups read as groups: internal gap ≤ external gap; more space above a heading than below | M | RUI; impeccable floor |
| Align to a shared edge / baseline / grid line; 12-6-4 columns; prose 6–7 desktop cols | M (edge histogram) | Vercel |
| No horizontal overflow at 390px; primary content visible without horizontal scroll | M | Apple; impeccable `first-viewport-column-overflow` |
| No nested cards; borders don't repair weak hierarchy; surfaces earned by selection/interaction/warning/grouping | M | Vercel; impeccable `nested-cards`; RUI "fewer borders" |
| Density is a choice per surface, not a template ("start with too much white space, then remove") | J | RUI |

## 3. Color

| Rule | Tag | Source |
|---|---|---|
| Palette lives in tokens: 8–10 greys, 1–2 primaries × 5–10 shades, defined up front | M | RUI |
| Perceptual space (OKLCH/LCH); three theme vars base/accent/contrast | M | Linear redesign; Evil Martians |
| Contrast 4.5:1 body, 3:1 large (≥24px or ≥18.5px bold) and non-text/focus | M | WCAG 2.2; Soueidan |
| Never rely on color alone; no grey text on colored surfaces (tint from the hue) | M partial | RUI; NN/g; impeccable `gray-on-color` |
| Monochrome first; color only where it adds meaning; one accent | M (hue count) | Vercel; Linear |
| No decorative gradients / glows / mesh / glass; shadows carry offset + soft blur, one light source, tinted | M | Vercel; Freiberg "no swanky mesh gradients"; Comeau; impeccable `radial-halo`/`dark-glow` |
| ≤5 elevation levels, one vocabulary (border *or* shadow per level) | M | RUI; Comeau; impeccable floor |

## 4. Motion

| Rule | Tag | Source |
|---|---|---|
| Durations: press 100–160ms · tooltip 125–200 · dropdown 150–250 · modal 200–300(≤500) · all UI <300ms | M | Kowalski STANDARDS.md |
| Exit ≈20% faster than enter; stagger 30–80ms; duration ∝ distance | M | Kowalski |
| `ease-out` for enter and exit; `ease-in-out` for on-screen morphs; **never `ease-in`**; custom beziers, e.g. `cubic-bezier(0.23,1,0.32,1)` | M | Kowalski (Comeau permits ease-in for exits — resolve toward Kowalski) |
| Frequency gate: 100+/day (keyboard, palette) → no animation ever; occasional → standard; rare/first-time → delight | J (M proxy: no transition on keyboard paths) | Kowalski; Freiberg |
| Never `scale(0)`; start 0.9–0.97 + opacity 0; press `scale(0.97)`; popover `transform-origin` at trigger | M | Kowalski |
| Animate only `transform`/`opacity`; never height/width/padding/box-shadow/top/left | M | Kowalski; Freiberg; Comeau |
| Interruptible (transitions not keyframes for state); hover gated `@media (hover:hover) and (pointer:fine)` | M | Kowalski; Freiberg |
| Reduced motion = fewer and gentler, not zero: keep opacity/color, drop movement | M | Kowalski; Vercel "Default to stillness" |
| One authored moment per surface, not an identical entrance on every section | J | impeccable floor; Freiberg 90/10 novelty |
| Tooltips: delayed first, instant subsequent; toasts 4s, pause when tab hidden | M | Kowalski (Sonner) |

## 5. States

| Rule | Tag | Source |
|---|---|---|
| <1s: no indicator; 2–10s: skeleton/spinner; >10s: progress + cancel; never a flash | M (delay ≥500ms) | Nielsen response-time limits; NN/g skeletons |
| Every async surface has loading, error, and empty designed — not afterthoughts | M (presence) + J (quality) | Kowalski; NN/g |
| Errors: near the source, icon+text (not color alone), name the problem and the recovery, preserve input | M partial | NN/g error guidelines; impeccable floor |
| Empty state has a heading and one action | M | NN/g; impeccable `onboard` |
| Load time is part of craft (LCP ≤2.5s, INP ≤200ms, CLS ≤0.1 @p75) | M | Stripe checklist; web.dev |

## 6. Copy

| Rule | Tag | Source |
|---|---|---|
| Sentence case everywhere, incl. titles and buttons | M | GOV.UK; Polaris |
| Plain, active, grade-7; no jargon ("leverage", "empower", "seamless") | M | GOV.UK; Polaris; impeccable `marketing-buzzword` |
| Buttons: verb + noun; no "click here"; no "you can" | M | Polaris; GOV.UK |
| No all-caps eyebrows/kickers, no em dashes, no "it's not X, it's Y", no ✓-bullets, no emoji-as-icons, no authoring narration | M | Vercel reject list; impeccable `hero-eyebrow-chip`/`kicker-above-heading`/`em-dash-overuse`/`aphoristic-cadence`; the reel |
| Copy is the product's own language; controls name their action | J | impeccable floor |

## 7. Accessibility

| Rule | Tag | Source |
|---|---|---|
| Hit targets ≥44×44 (24 is the legal floor, 44 the craft bar); text ≥11pt mobile | M | Apple HIG; Kowalski; WCAG 2.5.8 |
| Focus visible: never remove outline without a replacement; ≥3:1; 2px perimeter; `:focus-visible`; not clipped by overflow | M | Soueidan; Freiberg two-ring focus |
| Keyboard reaches everything; reduced motion honored; decorative markup `aria-hidden` | M | multiple |

## 8. Performance

| Rule | Tag | Source |
|---|---|---|
| woff2 only; `font-display` chosen deliberately; preload one; subset/variable | M | web.dev |
| Images sized (width/height or aspect-ratio), `max-width:100%`, @2x | M | Apple; Comeau |
| Compositor-only animation (see §4) | M | — |

## 9. Consistency (the vocabulary)

| Rule | Tag | Source |
|---|---|---|
| ≤4 radii (control / card / dialog / pill), nested radius < parent | M | Kowalski; Linear 6/12; Freiberg "random 6px" |
| ≤5 shadows; ≤3 weights; one easing set; one icon set, one stroke weight | M | RUI; Comeau; Kowalski; Vercel |
| "Consistent, not uniform": platform conventions adopted, identity carried by restrictions | J | GOV.UK; Apple; Identity Forge on Linear |

## 10. Trust / substance (the class-D tells)

| Rule | Tag | Source |
|---|---|---|
| Real organisation, real contact, real people; terms + privacy present and linked; updated recently | M (presence) | Fogg credibility; NN/g trust |
| Real product evidence: real screenshots/video; decorative stock is ignored by users and banned by Vercel | M (no stock hosts) + J (is it real?) | Nielsen photos-as-content; Vercel |
| No fake testimonials, fake metrics, false certainty; "good design is honest" | J (human verifies) | Rams; Vercel |
| Thorough to the last detail; the spec is the baseline, not the finish line | J | Rams; Saarinen |
| Novelty budget ~10%, spent at once-only moments; no manufactured personality | J | Freiberg; Vercel |

## Contradictions the gate resolves (stated, not hidden)

1. **`ease-in` on exit** — Comeau permits, Kowalski forbids. Gate forbids `ease-in` on UI by default.
2. **Shadows vs hairlines** — Comeau/RUI layer tinted shadows; Linear/Vercel use 0.5px hairlines and no shadows. Both crafted → the check is *one consistent vocabulary*, never a specific choice.
3. **System fonts** — Butterick avoids; Linear/Vercel ship Inter/Geist; broomva-design uses the system stack deliberately. The check is *deliberate + stated + size-adjusted fallback*, not the face.
4. **Dark + purple glow as "premium"** — every Linear-clone teardown says copying that surface is what makes clones hollow. Dark/glow is never a check in either direction.
5. **Expressiveness** — Material 3 Expressive measures faster recognition with more shape/motion/color; Vercel defaults to stillness. Reconcile: expressiveness scales inversely with use frequency and task seriousness (Kowalski's frequency table).
6. **Line length** — 45–90 / 45–75 / ~65. Gate ≤75, target 65.

## Machine-checkable subset unslop's gate implements today

`direction.authored` · `detector.clean` (impeccable, 64 rules) · `fonts.deliberate` · `icons.single-system` ·
`tokens.color|radius|shadow` · `copy.em-dash|emoji|checkmark-bullets|not-x-but-y|buzzwords` ·
`substance.legal|loading-states|error-states|placeholders|stock-imagery|claims|testimonials|pricing|product-evidence` ·
`motion.reduced-motion` · `evidence.render`. Everything else in the [M] column is a **planned** check or is
already covered by impeccable `audit` (a11y/perf/responsive) — run it in the arc; do not re-implement.
