# Changelog

All notable changes to `unslop` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- 82 tests, both polarities (see the P20 hardening entry below).
