# The arc — full traversal, root fixes, verified floor, autonomously

`/unslop <repo|dir> [--profile persuade|operate] [--dry-run] [--pr]` runs this arc end to end without
handing control back mid-way. Every step names the primitive it composes; unslop reimplements none of them.

```
0 Snapshot   → 1 Survey → 2 Direction → 3 Root plan → 4 Fix at root → 5 Structure+copy
             → 6 Class D → 7 Render+inspect → 8 Gate → 9 PR + report
```

## 0. Snapshot (bstack P15 / P10)

`git status` clean or a worktree; branch named for the ticket; note the framework and the dev command.
Never edit on `main`. Never start without knowing how the app is *run* (step 7 needs it).

## 1. Survey (deterministic)

```bash
python3 scripts/unslop_survey.py <repo> --detect --json .unslop/survey.json --md .unslop/survey.md
```

Read `.unslop/survey.md`. It tells you: framework + routes · the **roots** (font / icons / color / radius /
shadow / gradient / glass with the file that declares each and its blast radius) · copy tells · the
**substance** picture (legal, async-state coverage, placeholders, testimonials, pricing scaffold, product
evidence, motion/reduced-motion, design docs) · impeccable's findings by rule (if the detector is
installed — install `impeccable` if not; the survey says so and the gate WARNs, it never pretends).

Do not start editing yet. The survey is the map; the fixes come from the plan.

## 2. Direction — decide once (latent; composes impeccable `init`/`document`, Anthropic `frontend-design`)

- If `PRODUCT.md`/`DESIGN.md` exist: read them; they win over your taste and over any tell list.
- If not: run impeccable's `document` (extracts the incumbent tokens into a DESIGN.md) and, when the
  incumbent is *itself* the default look, `new-work` to choose a replacement world. Author the missing
  paragraph the gate reads: **the typeface decision, the icon decision, the voice** (sentence case,
  verb+noun, no em dashes / emoji / ✓ / "it's not X, it's Y"), the radius/shadow vocabulary. Anthropic's
  `frontend-design` is the reference for what "distinctive, committed" means; `broomva-design`'s DESIGN.md
  is the house example of stating decisions.
- Persist: `DESIGN.md` at the repo root (Stitch-compatible so every other tool reads it). Direction is the
  *root of roots*: skip it and every fix below is a coin flip toward a different default.
- Autonomy rule: infer the direction from the product's own material (README, copy, brand assets, the
  incumbent CSS). Do **not** ask "what style do you want?". If the product truly has no material, choose the
  quietest committed world (monochrome-first, one accent, system or one self-hosted face) and say so in
  DESIGN.md — a stated quiet decision beats an unstated loud default.
- **Draw, don't "choose".** ui-craft's blind-build ablation (2026-07-29): 10/10 builds converged on the
  same fold no matter what the prose said — prescribing, permitting and forbidding all converge; only a
  forced *class draw* moved it. Anthropic's Opus 4.8 guide says the same for palettes (negatives swap
  one default for another). So when the direction is open, enumerate 4 named, concrete worlds (hex,
  face, radius, layout class), draw one by an external seed (ticket number, commit hash), and commit to
  it. "Adjectives describe a region. A specific reference describes a point." (Google DESIGN.md
  philosophy.)

## 3. Root plan (latent, from `roots[]`)

For each root in the survey, write one line: `kind · current default · root file · the single edit ·
blast radius`. Order per `root-cause-playbook.md`: font → icons → color tokens → radius → shadow →
gradient/glass → motion → copy voice. Then the structure list (which surfaces are template scaffolds) and
the class-D list (what needs a human). Put the plan in `.unslop/plan.md`. It is the PR body's spine.

## 4. Fix at the root (edits; composes impeccable `extract`, `typeset`, `colorize`, `layout`, `quieter`)

One edit per root, at the declaring file. Then run the survey again and diff `roots[]` — the site counts
for the old default must drop to zero without touching call sites. If they don't, the root was wrong;
find the real one before editing more. impeccable's per-edit hook (if enabled) surfaces mechanical
findings as you go; act on them.

## 5. Structure + copy (per surface; composes impeccable `shape`, `distill`, `clarify`, `polish`)

Walk `routes[]`. For each page: is it a template (hero → 3 cards → 3 tiers → testimonials)? Re-derive from
the product; cards are the lazy container. Rewrite copy in the voice; strings live in content/i18n files
where the codebase has them, so the rewrite is one place. Delete "it's not X, it's Y", eyebrows, ✓-bullets,
buzzwords, em dashes; keep the product's own words.

**Voice doctrine (after no-ai-slop).** Make the *minimum effective edit*: fix the named pattern, keep the
author's vocabulary, cadence, bluntness and humor. Cutting must be proportional to the actual slop — never
rewrite distinctive copy merely to zero a counter, and never introduce what you're removing elsewhere
(synonym cycling, robotic one-shape sentences, stacked punchy fragments). A waiver with the reason
"authored voice, kept deliberately" is the correct green for copy a human wrote on purpose.

**Post-fix self-check** (before step 7, on your own edits): (1) same author recognizably — would they
sign it? (2) no invented claims, stats, testimonials, or sources; (3) proportional — strong human
sentences untouched; (4) the fix didn't trade one pattern for another; (5) every remaining
`copy.slop-patterns` site is either fixed or carries a reasoned waiver.

## 6. Class D — substance (composes impeccable `harden`, `onboard`; needs a human for truth)

- **States**: route-level loading/error files + Skeleton/aria-busy/Suspense per async component; a
  ≥500ms delay before showing; error names problem + recovery and preserves input; empty state has a
  heading and one action.
- **Legal**: routes + footer links wired; **the text comes from a human/legal owner** — leave a clearly
  marked placeholder route that renders "policy pending" and flag it in the report, never generated
  policy prose presented as real. The gate WARNs on operate surfaces and FAILs on persuade surfaces
  until it is real; that FAIL is the point.
- **Product evidence**: capture the real product — Playwright screenshots of real states, a short
  recording — and place them under `public/screenshots|media`. If there is no product yet, no fake demo.
- **Placeholders / claims / testimonials**: real or removed; testimonials need name + role + permission
  → the human waives `substance.testimonials` with reason "verified real …" once confirmed.

## 7. Render + inspect (bstack P11 — reasoning is not validation)

Run the app. Screenshot every page route at **1280** and **390** into `.unslop/evidence/` with the route
slug in the filename (`index-1280.png`, `pricing-390.png`). Read the screenshots. Fix what they show in one
batched round; confirm with at most one more (impeccable's bounded-pass rule). Also run
`impeccable audit` for a11y/perf/responsive; do not re-implement it.

**Outside voice (bstack P20).** Every design critic in the field shares the generator's model family;
gstack's Codex "outside voice" is the lone exception and it reviews source, not pixels. Send the
screenshots + the gate table to a *different* model (the Cross-Review strata) with one question — "would a
designer at a respected studio ship this, and what is the single most AI-generated thing on the page?" —
and treat a named finding as a fix item, not an opinion. Reasoning about the render is not validation;
neither is one model grading its own render.

## 8. Gate (deterministic)

```bash
python3 scripts/unslop_gate.py <repo> --detect --evidence .unslop/evidence \
        [--waivers .unslop/waivers.json] [--profile persuade|operate] [--strict] --json .unslop/gate.json
```

Exit 0 = the floor is clear. Every WARN is read and either fixed or waived *with a reason ≥20 chars* in
`.unslop/waivers.json` (the waiver names the check and, where relevant, the value: a font, a rule id).
A FAIL that only a human can clear (legal text, testimonial truth, product evidence) stays FAIL and is
named in the report — the arc does not fake its way to green.

## 9. PR + report (bstack P4 / P20)

PR body = `.unslop/plan.md` (roots, one edit each) + before/after `roots[]` site counts + gate table +
the class-D items handed to a human + evidence screenshots. Cross-review (P20) for anything touching a
design system or >200 LOC. Never merge on red.

## Anti-rationalizations

| Excuse | Reality |
|---|---|
| "I'll ask which style they want first." | The direction is inferred from the product's own material and *stated* in DESIGN.md. Asking is the failure; a stated quiet choice is the fallback. |
| "The detector is clean, ship it." | The detector covers classes A–C. Class D (substance) and render evidence are the gate's other half; a clean detector with lorem and no privacy route is still slop. |
| "I fixed the fonts in every component." | Then you fixed the example, not the class. Re-run the survey: `roots.font.sites` must reach zero by one edit. |
| "It looks fine in my head / in the JSX." | Screenshots at 1280 and 390 or it did not happen. |
| "I'll generate the privacy policy / testimonials so the gate passes." | Fabricated substance is the worst tell there is. Leave the FAIL, hand it to a human, say so in the PR. |
| "The user said autonomous, so I'll merge." | Autonomous through the gate and the PR. Merge authorization stays with the policy. |
