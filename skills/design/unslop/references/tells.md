# Tells — the current LLM defaults, dated and regenerable

**last_verified: 2026-08-18.** A tell is a *correlate* of unattended generation, not a defect: skeleton
loaders are good, Lucide is a fine icon set, a privacy policy is required. The list works as a
*detector* because these are what a model emits by default. It decays: "premium in 2025" (dark + purple
orbs + glass + bento) is "default in 2026", and `high-end-visual-design`-style skills that prescribed it
now prescribe three of the thirty. **Never paste this list into a design system as bans.** The durable
rule is class D + a dated list like this one, regenerated from the sources below.

Sources: the reel (@aj.on.ai, 2026-08-15, 34k likes — `research/entities/pattern/vibecoded-tells.md`),
impeccable's 64 detector rules (v4.0.4), Vercel's agent-facing brand guidelines reject list
(`vercel.com/design`), Anthropic `frontend-design`, `design-taste-frontend` line 39.

## Four classes, four remedies

| Class | What it detects | Remedy | Who fixes it |
|---|---|---|---|
| **A. Aesthetic defaults** | the model's prior over "modern SaaS" | decide a direction once, declare tokens at the root | the arc, autonomously |
| **B. Copy defaults** | the model's prose prior | a voice: sentence case, verb+noun, no em dashes / emoji / ✓ / "not X, it's Y" | the arc, autonomously |
| **C. Template structure** | the scaffold: hero → 3 cards → 3 tiers → testimonials → footer | replace with structure derived from the actual product | the arc + a human for what the product *is* |
| **D. Absence of substance** | there is no product behind the page | a real demo, real loading states, real legal, real people | **only a human / the real product** — never generated |

## The 30 (reel, verbatim) → class → machine check

| # | Tell | Class | Check today |
|---|---|---|---|
| 1 | harsh gradients | A | impeccable `gradient-text`/`radial-*`; survey `roots.gradient` |
| 2 | lucide icons | C | gate `icons.single-system` (WARN unless stated) |
| 3 | pure white background | A | judgment (direction) |
| 4 | rainbow coloring | A | impeccable `ai-color-palette`; gate `tokens.color` |
| 5 | drop shadows (on everything) | A | impeccable `dark-glow`/`gpt-thin-border-wide-shadow`; gate `tokens.shadow` |
| 6 | 3 feature cards in a row | C | impeccable `icon-tile-stack`/`repeated-container-text` |
| 7 | emojis | B | gate `copy.emoji` |
| 8 | liquid glass | A | survey `roots.glass`; impeccable floor |
| 9 | em dashes | B | gate `copy.em-dash`; impeccable `em-dash-overuse` (advisory) |
| 10 | inter/geist/space grotesk | A | gate `fonts.deliberate`; impeccable `overused-font` |
| 11 | colored left stripe | A | impeccable `border-accent-on-rounded`/`side-tab` |
| 12 | fake testimonials | D | gate `substance.testimonials` (WARN → human) |
| 13 | bento grids | C | judgment |
| 14 | terminal window | C | impeccable `blinking-cursor` |
| 15 | "it's not x, it's y" | B | gate `copy.not-x-but-y`; impeccable `aphoristic-cadence` |
| 16 | checkmark bullets | B | gate `copy.checkmark-bullets` |
| 17 | 3 pricing tiers | C | gate `substance.pricing` (WARN) |
| 18 | no real product demos | **D** | gate `substance.product-evidence` (persuade: FAIL) |
| 19 | soft corner radius | A | gate `tokens.radius` (vocabulary, not value) |
| 20 | purple and black | A | impeccable `ai-color-palette` |
| 21 | no skeleton loaders | **D** | gate `substance.loading-states` |
| 22 | radial orbs | A | impeccable `radial-halo`/`radial-spotlight-glow` |
| 23 | dot grids | A | impeccable `codex-grid-background` |
| 24 | sparkle icons | A | judgment (impeccable `pulsing-dot` nearby) |
| 25 | animated arrows | A | impeccable `marquee`/`image-hover-transform`; gate `motion.reduced-motion` |
| 26 | no TOS | **D** | gate `substance.legal` |
| 27 | no privacy policy | **D** | gate `substance.legal` |
| 28 | hover animations (for everything) | A | impeccable `hover-color-rules`/`image-hover-transform` |
| 29 | neon colors | A | impeccable `ai-color-palette` |
| 30 | basic pastel colors | A | impeccable `cream-palette`; judgment |

## Vercel's reject list (first-party design org, 2026) — corroborates the reel

"Do not ship any of these recognizable defaults: all-caps or tracked eyebrows · em dashes · decorative
gradients, glows, blobs · cards nested inside cards · stock imagery, fake screenshots, decorative brand
marks · false certainty or exaggerated claims · manufactured personality (jokes, celebration, Easter
eggs)". Design principle: "Design in monochrome. Use color only when it adds significant meaning."
"Default to stillness." "Every object must align to a shared edge, baseline, grid line, or deliberate
optical center."

## Two tells the reel misses (from the tool survey)

- **Div-built fake product UI in the hero** (a styled-div "dashboard"/"terminal"/"task list" standing in
  for the product) — taste-skill calls it "the #1 LLM-design Tell". Class D: it *is* the absent demo. Not
  statically detectable with confidence; the reviewer checks it against `substance.product-evidence`.
- **Fabricated metrics as texture** ("99.98% UPTIME SLA", "124ms AVG. RESPONSE") — Stitch `taste-design`
  and impeccable's Truth check; the survey flags `fake-metrics` and the gate WARNs `substance.claims`.

## Prose-slop on product surfaces (after petergyang/no-ai-slop, read verbatim 2026-08-20)

[no-ai-slop](https://github.com/petergyang/no-ai-slop) (Peter Yang, 5.5k★ in six weeks, also a ChatGPT
plugin) catalogs ~18 sentence-level patterns for *writing*. Landing pages are writing; the subset that
recurs on persuade surfaces is machine-checked by the survey as `copy_tells` keys, gated in aggregate by
`copy.slop-patterns` (WARN 1–2 sites, FAIL ≥3 — their own "1–2 em dashes are fine in longer drafts"
grading, generalized):

| key | canonical example | theirs |
|---|---|---|
| `faux_insight` | "What nobody tells you about scaling" | Faux-insight setups |
| `throat_clearing` | "Let me be clear: this is fast" | Throat-clearing openers |
| `colon_reveal` | "The best part: it learns." (curated lead-ins only) | Colon reveals |
| `fake_profound` | "The future of shipping is here." / "…isn't coming. It's already here." | Fake-profound kickers |
| `importance_puffery` | "marks a pivotal moment", "a testament to" | Importance puffery |
| `weasel_attribution` | "Experts agree", "studies show" | Weasel attribution |
| `rhetorical_setup` | "Imagine a world where…", "What if I told you…" | Rhetorical setups |
| `dramatic_simple` | "It's that simple." | Dramatic fragmentation |
| `superficial_ing` | ", showcasing our commitment to…" | Superficial analysis |
| `negative_listing` | "No setup. No config. Just code." | Negative listing |

Their binary-contrast pattern widened our existing `not_x_but_y` (period-separated and "isn't"-led forms
now count). Their banned-word list contributed the buzzword deltas (delve, foster, tapestry,
transformative, ever-evolving, embark, multifaceted, meticulous, paramount, paradigm shift, spaced "game
changer"). What stayed judgment-only — synonym cycling, robotic rhythm, minimum-effective-edit
proportionality — lives in `arc.md` step 5 as [J] rules, not regexes.

Two stances adopted from that skill, verbatim in spirit:

- **Detection names patterns, never authors.** "AI detectors guess. Named patterns are evidence the user
  can check." The survey reports `file:line` sites; it never claims the copy was AI-written.
- **The list detects, it doesn't ban — and it decays.** Their list is static and undated; at 5.5k★ it is
  itself an instance of second-order slop (a ban list popular enough gets trained and prompted around,
  and *visibly avoiding* the list becomes the next tell). This section carries a read-date for exactly
  that reason; regenerate per the section below.

## What the other skills already say (so unslop composes, not repeats)

- **impeccable** (Bakaus) — 64 mechanical rules + `craft-floor.md` ("Refuse: the category's defaults, not
  bans") + `document`/`extract`/`polish`/`harden`. unslop runs its detector and calls its commands.
- **Anthropic `frontend-design`** — direction-setting: distinctive type, committed palette, no generic
  AI aesthetics. unslop cites it when a direction must be authored.
- **`design-taste-frontend`** (line 39) — names 6 of the 30 as "the LLM defaults" and sets three dials.
- **`high-end-visual-design`** — *prescribes* #8/#13/#22. Evidence that a static ban/prescribe list ages.
- **`broomva-design`** — forbids most of the list by construction (system type, matte cards, no emoji /
  em dashes); carries Lucide + `0.75rem` radii deliberately and says so — the model for "stated decision".
- **gstack `/design-review`** (Garry Tan) — renders 5–15 pages, AI-Slop blacklist + letter grade, atomic
  CSS-preferred fix loop capped at 30; "Never read source code". unslop is the complement: it reads the
  source to find the *root* and renders to prove the result.
- **ui-craft** (educlopez) — `ux_coverage` completeness axis (billing/pricing/settings/docs archetypes;
  "Coverage never gates") is the nearest thing to substance tells; its `fold_candidates` ablation is the
  evidence behind "draw, don't choose".
- **emilkowalski `improve-animations`** — the one existing *full-repo read-only audit → plans* traversal,
  motion only. unslop generalises the shape to every root kind and adds the fix + gate.
- **Vercel web-interface-guidelines** — a11y/forms/typography/perf checklist over named files; zero
  aesthetics; unslop defers to it (and impeccable `audit`) rather than re-listing.

## Regeneration

Re-run when any of: impeccable bumps its rule set; a new viral tell-list appears; a design org publishes
a reject list; a face/pattern on this list stops being the default. Bump `last_verified`.
