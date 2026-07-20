# Claude Design — "Create Design System" prompt (template)

Fill the `{{...}}` slots from the measured moodboard, then paste into
claude.ai → Claude Design → Create Design System, alongside the curated
reference images + the 3 moodboard `.md` files. The "refine, not diverge"
framing is deliberate — it makes the tool's output a clean **diff** against the
in-stack version rather than a competing direction.

---

I'm building a **{{PRODUCT}}** ({{ONE_LINE_WHAT_IT_IS}}). I've attached reference
screenshots and a moodboard. Create a complete, cohesive design system from them,
honoring the validated direction below exactly — this direction is already
synthesized from the references, so refine and polish it, don't diverge from it.

DIRECTION — {{ONE_OR_TWO_MODE_SUMMARY, e.g. "one warm, low-saturation palette
with TWO modes"}}:
• {{MODE_1 (primary): canvas + ink + which reference it derives from}}
• {{MODE_2: canvas + ink + which reference}}
• Chrome discipline from {{CHROME_REF, e.g. Linear}}: hairline borders, separation
  by surface tone (no heavy shadows), tiny accent dots, calm density, {{LAYOUT}}.

MEASURED PALETTE (use as the basis, refine for contrast/AA):
• {{MODE_1}} — bg {{}} · surface {{}} · surface-2 {{}} · text {{}} · muted {{}} · border {{}}
• {{MODE_2}} — bg {{}} · surface {{}} · surface-2 {{}} · text {{}} · muted {{}} · border {{}}
• Single accent — {{ACCENT_HUE}} ({{mode1}}) / {{ACCENT_HUE_2}} ({{mode2}}). Plus
  status: ok / warn / danger / info, tuned per mode.

TYPE: {{DISPLAY_FACE}} for display ({{weight}}, {{tracking}}) + {{BODY_FACE}} for
body/UI ({{weight}}, deliberately {{light|…}} — never bold/black). Reads as one
family. Display {{px}}, h1 {{}}, h2 {{}}, body {{}}, small {{}}, label {{}} uppercase.

CHROMA RULE: saturated colour appears in EXACTLY ONE surface — {{hero/empty-state
device}}. All functional UI (cards, tables, nav, sidebar) stays neutral + the single accent.

COMPONENTS TO PRODUCE (card patterns + stubs): {{LIST, e.g. button (primary
inverted / accent / secondary / ghost), surface card, metric scorecard, skill
tile, sidebar nav, action-queue row, data-table row, status pill, hero surface}}.

DELIVER: colour tokens as CSS custom properties for {{BOTH/the}} mode(s) (a
colors_and_type.css switched by a data-theme attribute), a type scale,
radii/spacing/motion tokens, the card patterns, and JSX UI-kit stubs using
{{STACK, e.g. Tailwind v4 + shadcn/ui}} conventions (cn() +
class-variance-authority, components as .tsx).

NON-GOALS (hard constraints): {{LIST the anti-patterns, e.g. no cool blue-gray
dark mode; no stark pure-white light mode; no multi-colour functional UI; no
heavy drop shadows; no bold/black type weights; no chroma inside data tables}}.

---

## Upload manifest (alongside this prompt)
- Curated, non-redundant reference images (the anchors + one card-pattern each +
  the chrome reference) — give absolute paths.
- The 3 moodboard docs: `Moodboard.md` · `Design-Brief.md` · `Fonts.md`.
- Do NOT upload the in-stack `design-system/` folder — keeping it out is what
  makes the tool's return a clean diff.

## After it returns
Drop the generated zip beside the in-stack `colors_and_type.css`; diff; keep the
stronger tokens/stubs from each; reconcile into one system; proceed to scaffold.
