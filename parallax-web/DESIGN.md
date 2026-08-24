# Parallax — design decisions

Extracted from the incumbent, not imposed on it. Every value below is already in
`app/globals.css`; what was missing was the statement, not the system. The header comment on that
file is the origin of most of this and stays the source of truth for the tokens themselves.

The product this dresses is a simulation runtime whose whole claim is that it cannot lie about being
a simulator. The design has one job that follows from that: **make the difference between what was
observed and what was simulated impossible to miss, and never let the page itself look more certain
than the numbers on it.**

## Typeface — decided

Two families, no webfont, no network request for type.

- **`--sans`** — the system grotesk stack (`ui-sans-serif, -apple-system, BlinkMacSystemFont,
  system-ui, "Segoe UI", Helvetica, Arial`). All human-readable prose.
- **`--mono`** — `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas`. **All chrome**:
  labels, code, tables, chips, transcripts, run ids, hashes.

The split is semantic rather than decorative: mono means *this is a machine-produced value you could
go and check*. Prose is never mono and an identifier is never sans.

Mono runs at exactly **two sizes and two trackings**, and nothing else:

| token | value | used for |
|---|---|---|
| `--m-micro` | 0.6875rem | uppercase labels only |
| `--m-code` | 0.8125rem | code, tables, chips, transcripts |
| `--tr-lab` | 0.14em | tracking for the uppercase labels |
| `--tr-code` | 0.01em | tracking for everything else mono |

Self-hosting a display face is deliberately **not** done. A surface that blocks on a font CDN is a
worse outcome than a system stack, and the system grotesk is not the tell — Inter shipped as a
decision nobody made is.

## Icons — decided

**There is no icon library, and adding one is a decision that needs a reason.** This app depends on
no icon package. Three marks exist and all three are authored SVG in the component that uses them:

- `components/Nav.tsx` — the Parallax mark: one solid baseline, two dotted rays, a ring at the
  origin. It is the figure the product is named after, drawn at 18px.
- `components/Cinema.tsx` — the opening figure (trunk → fork → two branches → the measured angle).
- `components/RealityMap.tsx` — the reality map.

A generic icon set would put a rounded-corner house style next to a mark that means something
specific. If an icon is ever genuinely needed, draw it in the same vocabulary as the mark: 1.6
stroke, round caps, dotted for simulated, solid for observed.

## Colour — decided

One foreground, six alpha steps, one accent spent twice.

- **Foreground** is a single oklch triple (`--fg-c`), exposed as `--fg-1` … `--fg-6` at six alphas.
  There is no second ink. A "lighter grey" is a lower alpha of the same ink, never a new colour.
- **Accent** is one hue axis (`--accent`, with `--accent-ink` / `--accent-btn` as the AA-safe
  variants of the same hue). It marks **the chosen path and nothing else.** An accent that appears
  on every third element stops meaning "this one".
- **Semantic** `--ok` / `--warn` / `--crit` exist and are for state, never for decoration.
- Everything is authored in **oklch** so the light and dark ramps are the same perceptual steps
  rather than two hand-tuned palettes that drift.

Two surfaces, one system, foreground and background exchanged:

- The **landing** pins light (`data-theme="light"`). Its two dark regions — the opening film and the
  motion panels — are dark because they are *a film and a set of readouts*, not because the page
  follows the OS.
- **`/demo`** is dark end to end. That is not a mood: it opens on a film and stays inside it, so the
  surface follows the footage rather than the document. It redefines the same roles under `--d-*`
  and scopes `color-scheme: dark` with `:has(.demo)` so the landing is untouched.

## Radius — decided (scale extracted 2026-08-23)

Previously nine literal values across 28 sites and **no token**. Now a named scale in
`globals.css`, with every existing rendering preserved exactly:

| token | value | used for |
|---|---|---|
| `--r-hair` | 2px | hairline swatches and bars |
| `--r-xs` | 0.25rem | inline code |
| `--r-sm` | 0.375rem | small controls, chips |
| `--r-md` | 0.5rem | nav links |
| `--r-lg` | 0.75rem | panels, cards, figures |
| `--r-pill` | 9999px | pills and badges |
| `--r-circle` | 50% | dots and rings |

One value moved: a legend swatch at 3px is now `--r-hair` (2px). Nothing else changed by a pixel.

**One documented exception — there are two copies of this scale, on purpose.**
`public/proof/index.html` contains no `<link>` anywhere: it is deliberately self-contained so the
evidence page opens with no server and no build step. It therefore cannot consume `globals.css`, and
it **redeclares the same seven tokens in its own `:root`**. That is a duplication, it is the price of
the page's standalone property, and it is the one place where "declared once" is not literally true.
The two must be kept in step by hand — if you change a radius token in `globals.css`, change it in
`proof/index.html` too, or the evidence page quietly drifts away from the product it is evidence for.

**Known follow-up:** seven steps is more than this system needs — 4px / 6px / 8px almost certainly
want to be one step. That collapse changes pixels on every surface at once and was deliberately
deferred rather than bundled with the token extraction. It is the next radius edit, and it is now a
one-line edit because the scale exists.

## Motion — decided

- Scroll is a camera, not a scrollbar: the opening and `/demo` map scroll position onto a frame, so
  the words and the picture cannot drift apart because nothing tweens on a timer.
- `prefers-reduced-motion` is honoured everywhere and is **never** a degraded experience: the
  reduced path lands on the finished figure, and the posters alone carry the whole story.
- Remotion compositions pause when off-screen. A figure nobody is looking at is not a render loop.

## Voice — decided

Spanish on `/demo` (the worked case is a Colombian multi-site operator and the film is set in one);
English on the landing and the runtime README (the audience is whoever reads the source).

- **Sentence case** in headings. Never Title Case.
- **Headings carry a message, not a label.** "Lo que corre, y lo que no" — never "Estado".
- **No emoji in product copy**, no ✓-bullets as a rhetorical device (the two `✓` in the status grid
  are a legend for a two-column built/not-built comparison, which is a table marker, not decoration).
- **No "it's not X, it's Y"**, no eyebrow throat-clearing, no buzzwords. The survey reports zero of
  each and it stays that way.
- **Em dashes are authored and deliberate.** They are the house punctuation across this repo's
  commits, docs and copy, and they are load-bearing in a voice that qualifies its own claims
  mid-sentence. A tell-counter will flag them; the correct response is a waiver, not a rewrite.
  Stripping them would remove the author's voice to move a number, which is the thing the counter
  exists to prevent.
- **Never state a capability the code does not have.** The status section names what is designed and
  not built, and the honest line about calibration stays on every surface. That is a design decision
  as much as an editorial one: the page must not look more certain than the system is.

## What this design must never do

1. Present a simulated value with the same weight as an observed one.
2. Render a claim inside generated pixels. Words live in the DOM; a diffusion model does not get to
   author a number this project has to stand behind.
3. Publish a figure whose provenance is not on the page next to it.
