# Changelog

All notable changes to `unslop` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.3] — 2026-08-21

broomva-design dogfood (BRO-2197, the house exemplar audits itself):

- **Font subsystem**: `fontFamily: "var(--bv-font-mono, ui-monospace, monospace)"` declared nothing —
  yet its fallback tail leaked as fake family roots (`ui-monospace`×31 and a mangled `monospace)` on
  the exemplar). `_split_families()` now strips `var()` (nested-safe) and routes fallback tails to
  `fallback_only`. Namespaced font tokens (`--bv-font-sans`, `--brand-font-heading`) register as
  declarations — closes the `fonts.deliberate` gap from the genesis arc (BRO-2196).
- Known collateral documented: `MIN_SCREENSHOT_BYTES` flags genuinely sparse specimen pages (a
  two-swatch token page compresses under the floor); kept — it guards white-page false evidence.

## [0.2.2] — 2026-08-20

Genesis dogfood finding #2 (BRO-2196, via cross-model review of the arc's own PR): `app/manifest.ts`
— a Next metadata route serving `/manifest.webmanifest` — carries user-facing name/description copy
(the PWA install surface) and was not a copy module, so the copy pass missed it. The match is
path-scoped to the metadata route (`app/manifest.ts`, any depth) — a build/bundler `lib/manifest.ts`
stays data, never copy (cross-model nit on this very fix).

## [0.2.1] — 2026-08-20

Genesis dogfood (BRO-2196): continuation lines of multi-line `/* … */` / `{/* … */}` comments were
counted as UI copy (7 of 21 em-dash sites on the first live run were comment prose). Block comments
are now blanked newline-preserving before the copy scan, so markers, buzzwords and prose patterns
inside them never count and real sites keep their line numbers.

## [0.2.0] — 2026-08-20

Absorbed [petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop) (read verbatim; BRO-2195):

- Ten prose-slop `copy_tells` keys (faux_insight, throat_clearing, colon_reveal, fake_profound,
  importance_puffery, weasel_attribution, rhetorical_setup, dramatic_simple, superficial_ing,
  negative_listing) — one data-driven scan loop, line-level and multi-sentence passes; gated in
  aggregate by the new `copy.slop-patterns` check (WARN 1–2 / FAIL ≥3; future survey keys count
  automatically, no per-pattern gate branch to forget).
- `not_x_but_y` now catches the period-separated ("It's not X. It's Y.") and "isn't"-led ("The
  question isn't X, it's Y") forms; buzzword list gains the no-ai-slop banned-word deltas and the
  spaced "game changer".
- Fixed a false negative the new tests exposed: `export const pitch = "…"` in a plain `.ts/.js` copy
  module was eaten by the JSX-attribute stripper, hiding assignment-style copy from every line-level
  tell.
- Cross-model round 1 (codex gpt-5.4) hardening: `copy.slop-patterns` severity counts **distinct
  file:line sites** (one line matching three patterns is one site); period-separated binary contrasts
  require an article ("It's not *a* chatbot. It's *a* teammate." counts — "It's not available on iPad.
  It's available on desktop." does not, and "isn't coming. It's already here" books once, under the
  waivable aggregate); HTML template strings inside `.ts` copy modules are markup-stripped; cited
  claims (`[1]`, links) are not weasel attribution; "the bottom line" dropped as a colon-reveal lead-in
  (literal in finance copy).
- Voice doctrine in `arc.md` step 5 (minimum effective edit, proportional cutting, post-fix
  self-check) and the adopted detection stance in `tells.md`: named patterns are evidence — never a
  claim of AI authorship.

## [0.1.1] — 2026-08-19

Dogfood fix (broomva.tech): `DESIGN.md` / `PRODUCT.md` are found in a parent directory up to the git
toplevel, not only at the app root — a monorepo's `apps/web` no longer reads as "no direction", and the
gate reads the decisions from wherever the survey found them (`substance.design_docs.paths`).
Same dogfood run: input `placeholder="you@example.com"` / `"Acme Labs"` are examples, not fake content;
prose MDX only counts lorem / John Doe (never testimonials, pricing, claims); tests, stories, scripts and
`opengraph-image`/`icon` routes are not UI copy or token surfaces; copy-tell sites kept up to 200 for
planning; `fonts.deliberate` PASSes an AI-default face that DESIGN.md/PRODUCT.md *names* as the decision.

## [0.1.0] — 2026-08-18

First release (BRO-2184).

- `scripts/unslop_survey.py` — full-repo UI inventory for Next (app/pages), SvelteKit, Astro, Nuxt,
  Remix, Vite+React, static HTML; **root-cause attribution** (font / icons / color / radius / shadow /
  gradient / glass → declaring file + blast radius + the single fix); copy tells; **substance** tells
  (legal routes, async loading/error/empty coverage, placeholders, testimonials, pricing scaffold,
  product evidence, reduced-motion, design docs); composes the impeccable detector via `--detect`.
- `scripts/unslop_gate.py` — the crafted floor: 23 checks (4 conditional), PASS/WARN/FAIL/SKIP, waivers with mandatory
  reasons, `--strict`, `--profile persuade|operate|auto`, render-evidence check (desktop + mobile).
- `references/` — arc, crafted floor (sourced, [M]/[J]-tagged), dated tells list, root-cause playbook.
- 84 tests, both polarities (see the P20 hardening entry below).
