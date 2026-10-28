# Liquid Dawn · DESIGN.md

**Status:** v0.1.0 (2026-10-28). **Scope:** landing pages and heroes, product showcase moments, reels and posts,
chat and composer surfaces that should feel calm, and living backgrounds.
**Lineage:** the daylight sibling of [Liquid Midnight](../liquid-midnight/DESIGN.md). It keeps the materials
(liquid glass, a travelling liquid-metal rim, ASCII text shaders, time-addressable motion) and moves them onto paper
and into nature. Light (Dawn) is the primary mode; Dusk is the dark mode.
**Ticket:** BRO-3570.

This file stands alone: an agent with no other context should produce on-style work from it, the tokens,
`assets/css/materials.css` and `assets/kit/`.

---

## 1. The look in one paragraph

Warm **paper** grounds (never pure white) under a faint survey grid and three slow pools of light (sky, lagoon and sand).
Fields are **nature drawn in type**: lagoon caustics in `·-~≈`, blades of meadow grass that lean with each gust, cumulus
in `·.:°o`, and pebble ripples on a one-glyph dot lattice. Through those fields drift **glyph-tile shoals**: fish,
minnow schools, rays, birds and islands, each a mosaic of small rounded tiles with a glyph inside and a soft shadow
tile cast onto the water. Floating surfaces are **dew glass**: milky, thick and quiet, rimmed in **pearl**, a liquid
metal whose white specular and dark glint walk slowly round the edge with thin lagoon, sand and sky fringes. Where
glass sits on a field, the field **bends** through it (magnified body, outward-bent bevel, fringes at the rim)
rather than only blurring. Type is light and tightly tracked, in one of four voices (§7; Manrope Light by default),
with the payoff phrase in **tide**, the single accent. Real proportional text is laid out by **pretext**, so a page can ripple or make room.
Everything moves slowly, on one clock, and every frame is a pure function of `t`.

---

## 2. Principles

1. **Calm is a number.** Every field time term advances at ≤ 0.2 rad/s (`FIELD_SPEED_MAX`), breeze gusts are measured
   at ≤ 40 px/s, field density caps at .7 (`CAP`), and there is no per-frame random draw anywhere. Calm here is
   measured, not an adjective.
2. **Paper first.** Dawn is the default and the reference. Dusk is a full mode, not an inversion: it has its own
   ground (sea-slate, hue 228) and its own glass recipe.
3. **Glass bends, metal walks.** Every floating surface is dew glass with the pearl rim. Over a kit field the
   refraction is drawn by the field itself (`lenses`). A flat frosted panel with no rim is unfinished.
4. **Nature is the field; ink is the subject.** Nature colours (sky, lagoon, moss, sand, stone) live in fields and
   tiles only. Text uses ink, ink2, ink3 and tide.
5. **One accent.** `--ld-tide` carries emphasis, kickers, focus and the active item. Coral appears once per scene at
   most (one creature) or as the loss semantic.
6. **Leave a clearing.** A hero keeps a quiet ellipse behind its words (`clearing()` mask, `.ld-clearing`). Creatures
   swim around it, not through the headline.
7. **Time-addressable.** `createLoop().renderAt(t)` replays fixed 1/60 s steps; creatures, ripples and pebbles are
   pure in `t` and a seed. A headless browser renders any frame.
8. **Judge the render.** Render both modes at several times and look at every frame (§11).

---

## 3. Do and don't

**Do**
- Paper ground `--ld-paper`, `.ld-wash`, `.ld-grid`, one kit field canvas, and `.ld-clearing` behind hero copy.
- Dew glass (`.ld-glass`) on cards and captions, `.ld-capsule` for nav and segmented controls, and `.ld-lens` where a
  surface sits over a field it should bend (composers, focal cards, droplets).
- Pass the lens rects to `field({ lenses })` so the canvas draws the refraction.
- Glyph-tile shoals (`createShoal`, `createIslands`) for life; minnows travel in schools.
- Typeset pages and flowing paragraphs with pretext (`layoutPage`, `lensPage`, `flowAround`).

**Don't**
- ✕ Pure white or neutral grey grounds; ✕ purple anywhere (inherited from Liquid Midnight's rejected list).
- ✕ Editorial serif display type or newspaper layouts: this is paper-*like*, not editorial.
- ✕ ASCII that reads as rain, static or a uniform texture. If a field looks the same everywhere, add depth
  (`tide` already modulates shallows and deeps) or a clearing.
- ✕ Heavy frost (blur > 22 px on glass); ✕ glass stacked on glass; ✕ a frosted panel with no pearl rim.
- ✕ Soft radial "glow orbs" as subjects; light pools live only in `.ld-wash`.
- ✕ Magenta fringes on pearl: rims use lagoon, sand and sky only. (The liquid lens is the one exception: its fringe
  is optical dispersion, R/G/B parting at the very rim, and shows the natural spectrum.)
- ✕ Fast motion: creatures and drifting things stay at or under ~25 px/s; travelling light (gusts, pulses, ripple and
  pebble rings) at or under ~40 px/s. A deliberate interaction is the only exception.
- ✕ The black-hole `well` as a default: use it once per story at most. The `pebble` is the default lens.

---

## 4. Colour

OKLCH is canonical; `assets/tokens/tokens.css` (generated from `tokens.json` by `scripts/build_tokens.mjs`) emits an
sRGB hex fallback first and the OKLCH value inside `@supports`. Modes: **dawn** (`:root`, default), **dusk**
(`[data-ld-mode="dusk"]`). To follow the OS, the kit's `followOS()` resolves the attribute to dawn or dusk and
calls back on every change; there is no CSS-only auto, because every Dusk material rule keys on the literal attribute.

| Token | Dawn | Dusk | Role |
|---|---|---|---|
| `--ld-paper` | `oklch(0.972 0.006 95)` | `oklch(0.2 0.02 228)` | Ground: warm paper / sea-slate evening |
| `--ld-surface` | `oklch(0.992 0.003 95)` | `oklch(0.245 0.022 228)` | Opaque panels, glass fallback |
| `--ld-sunk` | `oklch(0.945 0.008 95)` | `oklch(0.175 0.018 228)` | Wells and field frames |
| `--ld-ink` | `oklch(0.25 0.02 235)` | `oklch(0.955 0.008 95)` | Primary text (slate-blue ink / paper ink) |
| `--ld-ink2` | `oklch(0.43 0.018 235)` | `oklch(0.81 0.014 220)` | Body, ledes |
| `--ld-ink3` | `oklch(0.52 0.016 235)` | `oklch(0.68 0.018 220)` | Metadata, tags |
| `--ld-tide` | `oklch(0.52 0.1 215)` | `oklch(0.8 0.1 205)` | THE accent |
| `--ld-sky` · `--ld-lagoon` · `--ld-moss` · `--ld-sand` · `--ld-stone` · `--ld-coral` | see `tokens.json` | | Nature: fields and tiles only |
| `--ld-metal-steel` · `-shine` · `-glint` · `-fringe-a/b/c` | see `tokens.json` | | Pearl rim |

**Measured contrast (WCAG 2, tested in `tests/skill.test.mjs`):**

| Text | Dawn on paper | Dawn on surface | Dusk on paper | Dusk on surface |
|---|---:|---:|---:|---:|
| ink | 14.7 | 15.6 | 15.8 | 14.2 |
| ink2 | 7.5 | 7.9 | 10.0 | 9.0 |
| ink3 | 5.1 | 5.4 | 6.3 | 5.6 |
| tide | 4.8 | 5.1 | 10.0 | 9.0 |

Nature colours fall to 1.5–3.5:1 on Dawn paper **by design**: they are never text. Moss as a status dot next to a
label is fine; moss text is not.

---

## 5. Materials (`assets/css/materials.css`)

All rims share one mechanism: a `::after` ring with 1.25 px padding, `mask-composite: exclude`, and a
`conic-gradient(from var(--ua), …)` with two white speculars (52° and 232°), each chased by fringes (lagoon + sand at
64–72°, sky + lagoon at 244–252°) and two dark glints (150° and 330°) that give the edge depth on paper.
`kit/loop.js#setClock` advances `--ua` at 24°/s (slower than Midnight's 40°/s: calmer).

| Class | Recipe |
|---|---|
| `.ld-glass` | Dawn: white .66 → .36 → .50, `blur(14px) saturate(160%) brightness(1.04)`, gel insets (top 1 px white .95, bottom .55, inner glow 14 px), shadow ink hued `oklch(0.35 0.05 230 / .16–.28)`, a lagoon caustic along the bottom. Dusk: slate tint .3–.42, same blur, blue-black shadows. Radius 26. |
| `.ld-capsule` | Pill: white .72 → .46, `blur(22px) saturate(170%)`. Holds `.ld-chip`s (36 px, raised white chip when pressed). |
| `.ld-lens` | Refractive glass: almost no blur (1.5 px), a top highlight, lagoon and sand side insets (chromatic edge), a lagoon bottom caustic. Over a kit field the canvas draws the bend; over DOM/photos add `.ld-lens--svg` for the `#ld-lens` SVG displacement filter (Chromium; elsewhere a light blur). Radius 32. |
| `.ld-ring` | 44 px round button, paper body, pearl ring rotating at 2× `--ua`. |
| `.ld-wash` · `.ld-grid` · `.ld-clearing` | Light pools (blur 80, opacity .55 / .32 dusk) breathing on `--ld-b1..3`; 24 px survey grid masked to the centre; the hero clearing. |
| `.ld-composer` | The calm input (with `.ld-lens`): 560 px, radius 22, mono hint row. |

---

## 6. The kit (`assets/kit/`, ES modules, no dependencies but the vendored pretext)

### 6.1 Fields (`fields.js`, pure)
| Field | Signature | Character |
|---|---|---|
| `tide` | `(x, y, t, {scale=520, speed=.18})` | `speed` is the rad/s of the fastest term (the base clock runs at speed / 2.5). Iterated domain-warp caustics with a slow fbm warp (breaks the 2π tiling) and a depth term (shallows vs deeps). Ramp `RAMP.water` ` ·-~≈=` (`=` reserved). |
| `breeze` | `(x, y, t, {speed=.2}) → {v, lean}` | Gust phase at .2 rad/s, so gusts travel at ≈ 33 px/s (21–32 measured; the warp slows some rows); `bladeGlyph(v, lean)` picks `' , ! \| ) / \`. Ramp `RAMP.blades`. |
| `cloud` | `(x, y, t, {scale})` | fbm cumulus drifting east at ~7 px/s. Ramp `RAMP.cloud` ` ·.:°o`. |
| `rippleField({w, h, n, period, seed, base})` | `→ (x, y, t)` | Pebble ring pairs at 26 px/s; `base` keeps a faint one-glyph lattice (the Claude FM halftone idea). Ramp `RAMP.dots` ` ·•`. |
| `clearing(x, y, cx, cy, rx, ry)` | mask 0 → 1 | The quiet hero centre. |
| `refract(px, py, lens)` | `→ {sx, sy, edge} \| null` | Convex lens: magnify 1.1, bevel band bends outward. |

### 6.2 ASCII (`ascii.js`)
- `field(cx, {w, h, cell, fs, ramp, color, alpha, fn, lenses, fringe, mask})`: one atlas glyph per lit cell; glyph
  alpha follows density (.3 → 1); cells inside a lens sample through `refract()` and draw lagoon/sand fringe copies at
  the rim.
- `tiles(cx, cells, {cell, shadow, dx=3, dy=4})`: the glyph-tile mosaic with a cast shadow.
- `atlas`, `glyph`, `fontsReady`, `resetAtlases`.

### 6.3 Shoals (`shoal.js`)
- `createShoal({w, h, seed, kinds, count, cell, coral, colors}).at(t)`: masks `fish`, `minnow` (spawns a school of
  2–4), `ray`, `bird`, `leaf`, `pebble`. 8–22 px/s, bob ≤ 1.5 cells, lattice-snapped, facing follows direction.
  Exactly one coral creature when `coral: true`.
- `createIslands({w, h, seed, n, colors, drift=3}).at(t)`: noise-blob archipelago (sand rim, moss interior, `t` trees).

### 6.4 Type as a field (`page.js`, pretext)
- `layoutPage(text, font, width, lh)`: pretext `prepareWithSegments` + `layoutWithLines`.
- `lensPage(cx, {lines, font, x, y, lineHeight, color, accent, lens, t})`: per-glyph displacement.
  `kind: "pebble"` (rings 34 px/s, wavelength 46, life 9 s) or `kind: "well"` (point-lens `d + rs²/d`, empty core).
- `flowAround(cx, {prepared, x, y, w, h, lineHeight, obstacles})`: per row, per free span (`freeSpans`), one
  `layoutNextLineRange()`: the variable-width-per-row call that makes reflow around a moving shape cheap.
- Pretext is vendored at `kit/vendor/pretext.js` (v1.0.0, MIT, Cheng Lou). Measure spaces with
  `{whiteSpace: "pre-wrap"}` if you lay out a lone space (a known pretext trap).

### 6.5 Hero recipes (`heroes.js`)
`createHero(name, {w, h, colors, seed, calm}).paint({soft, sharp}, t, lens)`, a CSS ground
(`.ld-hero-bg[data-recipe=name]`), an optional soft canvas (`.ld-field.ld-soft`, CSS-blurred into light) and a sharp
canvas. Owner-chosen directions (2026-10-28):

| Recipe | Layers | Look |
|---|---|---|
| `dawn` (default) | soft + sharp | caustic light rising from below, glyph currents over it, fish riding two currents, type inside the glass |
| `caustic` | soft + sharp | no glyphs in the room: pool-floor light; type appears only where the glass is |
| `currents` | sharp | the leanest: glyph streamlines with travelling pulses; riders |
| `lagoon` | sharp | aqua water, a one-glyph dot lattice lit by caustics, tile fish (closest to the shark references) |
| `horizon` | sharp | a literal dawn: type cumulus, a dotted-ring sun on the waterline, its reflection in the tide |
| `tide` | sharp | the first hero: tide glyphs, islands, a shoal |

`assets/specimen/heroes.html` shows all six.

### 6.6 Cinema (`cinema.js`): the shader on a scroll-scrubbed film
For a page with a `scroll-cinema` film (`@broomva/scroll-cinema`: N clips, N+1 posters, endpoints pinned). The
ASCII shader runs on the film itself:
- `sampleFrame(stage, cols, rows, scratch)` samples the visible video frame (or poster) into a grid; luminance is
  stretched between the 4th and 96th percentiles (`normaliseLuma`), so a pale dawn frame still spans the ramp.
- `seamDissolve(p, {seams, width, end, base})`: how much of the frame is type at scroll progress p: 0 inside a
  section (the film stays a photograph), 1 at a page break (a clip seam or a chapter break), and 1 from `end` on,
  where the film hands off to the paper.
- `dissolveThresholds(cols, rows, {seed})`: tide-ordered, rank-normalised per-cell thresholds, so the dissolve
  spreads like water and half the frame is type at d = .5. `cellDissolve(d, th)` softens each cell's turn.
- `filmType(cx, frame, {d, thresholds, paper, ink, lens, back})` draws the glyphs in the frame's own colours pulled
  toward ink. Give it a CSS-blurred `back` canvas and the photograph frosts into paper before the type sharpens.
- **The film keeps its own grade in both modes** (as the SRI landing does): a dawn-graded film under Dusk paper
  fails. Either generate a dusk-graded film for Dusk, or hold the cinema section in Dawn.

### 6.7 Paper: photographs in print (owner references, 2026-10-28)
The direction the owner pointed at (the haj sharks, the Metricra scenic footer, Wafer, the 404 page, the 3-7 card, the
2-5 orb, the 1-12 lens): near-white paper, pictures turned into PRINT, real refraction, very thin type. Live in
`assets/specimen/paper.html`.

| Piece | Module | What it does |
|---|---|---|
| Glyph mosaic | `mosaic.js` | `mosaic(cx, src, {cell, keyLight})`: a picture painted at one pixel per cell becomes greyscale tiles, each with a glyph from `:;t%SX#8@` by tone, its edge fraying into loose dots. `paintImage()` takes a photo (with `keyLight` keying its white ground); `paintShark()` is a procedural stand-in. |
| Liquid lens | `lens.js` | `createLens(overlay, source)`: WebGL. The centre magnifies (×1.4), the rim bends the page round its edge, R/G/B refract 6–7% apart so only the rim shows a rainbow; rim light, top-left specular, inner and drop shadow. `dragLens()` springs it to the finger (r .32, z .86) and squashes it 8% on press. |
| Agent orb | `spark.js` | `sparkOrb(cx, sparkField(n))`: a sphere of short radial light streaks round a white core, turning slowly; `busy` lengthens the streaks and sends a pulse outward. Lives on a dark chip. |
| Print | `engrave.js` | `printInto(cx, L, {mode})`: `engrave` (lines whose width is the tone, bare paper for the lightest tones, cross-hatch in the deepest) or `dither` (4×4 Bayer between two inks). Two inks plus a faint paper grain: dither with `grain: 0` is strictly two colours; engraving anti-aliases its line edges unless `aa: false`. Printed at 1× CSS px and copied up crisp. `L` is a luminance function: `imageLuma(img, w, h)` makes one from any picture (cover-cropped; null if CORS-tainted); `coastScene()` and `cloudSky()` are procedural subjects. `DUOTONES`: cobalt, teal, slate. |
| Glass numerals | page CSS | a backdrop-filtered layer masked by real type (rendered once to a canvas), so the picture shows frosted through the letters only. |

Photographs replace the procedural subjects where they exist (shark cut-outs for the mosaic, a toile engraving and a
painted sky); the procedural versions remain the fallback and the test fixtures.

### 6.8 Loop (`loop.js`) and core (`core.js`)
- `createLoop({init, step, paint, seed, still})` → `{start, stop, renderAt, invalidate}`; `setClock(t)` sets `--ua` and
  `--ld-b1..3` (breath periods 7.2 / 11.6 / 18.8 s: non-commensurate, so the light never visibly repeats).
- `fitCanvas`, `sheen` (pointer specular on glass), `Sp` springs (response/damping), `beat`, `prng`, `noise2`, `fbm`,
  `readColors`, `setMotion`.

---

## 7. Typography: four type themes

The voice is a parameter, like the mode. `data-ld-type` on `<html>` (or any subtree) swaps the display, text and
mono families, the display weight and tracking, and the payoff style together; `--ld-display-tracking` scales to
titles (×.78) and headings (×.45). Default: `manrope`. Owner kept all four (2026-10-28). See
`assets/specimen/type.html`; the specimen's **Aa** chip cycles them.

| Theme | Display | Payoff `<em>` | Text | Mono | Character |
|---|---|---|---|---|---|
| `manrope` (default) | Manrope 300, −.045em | Manrope 400, tide | Inter | JetBrains Mono | geometric, light, airy |
| `inter-tight` | Inter Tight 300, −.04em | Inter Tight 500, tide | Inter | JetBrains Mono | closest to SF Pro; Apple-neutral |
| `geist` | Geist 300, −.045em | Geist 400, tide | Geist | Geist Mono | precise, technical calm |
| `instrument` | Instrument Sans 400, −.035em | **Instrument Serif italic** 400, ×1.08, tide | Instrument Sans | Geist Mono | soft and warm |

`instrument` is the only theme with italic emphasis (Liquid Midnight forbids it); the payoff is one serif word.

| Role | Size / lh | Notes |
|---|---|---|
| Hero | clamp(48, 6.4vw, 104) / 1 | theme weight and tracking |
| Title | clamp(36, 4.2vw, 64) / 1.04 | tracking × .78 |
| Heading | 26 / 1.15 | weight + 100, tracking × .45 |
| Lede | clamp(17, 1.4vw, 21) / 1.55 | text family, ink2 |
| Body | 16 / 1.6 | text family |
| Kicker | 12 / 1, .18em uppercase | theme mono, tide, 22 px rule |
| Tag | 11 / 1, .14em uppercase | theme mono, 6 px dot |
| Number | 34 / 1, tabular | display family |
| Field glyphs | 7–13 | always JetBrains Mono (the ramps are tuned to its widths) |

Fonts are vendored in `assets/fonts/`, each with its SIL OFL licence (tested). Call `fontsReady()` (kit) before
painting canvas text or measuring with pretext: it loads the ACTIVE theme's faces.

---

## 8. Motion

| Thing | Spec |
|---|---|
| Pearl `--ua` | `(t · 24) mod 360`°; rings 2×; 0° under reduced motion |
| Light pools | `--ld-b1..3 = sin(2πt / [7.2, 11.6, 18.8])` |
| Fields | every time term ≤ 0.2 rad/s: tide .18 (fastest term), breeze .2 (≈ 33 px/s); cloud drifts ≈ 7 px/s; hero current pulses 20–29 px/s |
| Creatures | 8–22 px/s, lattice-snapped; islands 3 px/s |
| Pebble | a drop every 9 s; rings 34 px/s; settles in 9 s |
| Springs | `Sp.step(dt, r, z)`: default r .5 z 1; playful r .8 z .9 |
| Reveals | `beat(t, t0, d)`, ease-out-cubic; entrances `cubic-bezier(.22,1,.36,1)` |
| Press | `scale(.97)` chips, `.96` rings |

---

## 9. Formats

| Format | Size | Notes |
|---|---|---|
| Landing hero | fluid, 900 px tall at 1440 | clearing behind the copy, composer or CTA on `.ld-lens` |
| Section | max width 1240, 112 px vertical rhythm | kicker → title → lede, then panels |
| Reel 9:16 | 1080 × 1920 | safe zone top 250, bottom 480, left 64, right 150 (as Liquid Midnight) |
| Post 4:5 | 1080 × 1350 | top 80, bottom 120, sides 64 |

---

## 10. Accessibility

- Text tokens pass 4.5:1 on paper and surface in both modes (table in §4; enforced by the tests).
- **Reduced transparency:** glass becomes `--ld-glass-heavy` with no backdrop filter; the wash hides.
- **More contrast:** glass becomes opaque `--ld-surface` with a 1.5 px ink2 outline; rims, grid and wash hide.
- **Reduced motion:** the loop holds a settled still (6 s), also when the OS preference flips mid-run; `--ua` holds at
  0°; springs snap. Capture pages pin motion on.
- **Focus:** 2 px `--ld-tide` outline, 2 px offset. Never remove it.
- Field canvases are decorative (`aria-hidden`); text drawn on canvas (pages, flow) must also exist as real text if
  it carries meaning (the specimen's pages are illustrative).

---

## 11. Verification

```bash
node scripts/render.mjs assets specimen/index.html --t 0,6,12 --mode dawn,dusk --out renders
```

Look at every PNG. Check: the clearing holds behind the headline; no field reads as uniform texture or rain; the
composer bends the field under it; the pearl rim shows a white specular and a dark glint; Dusk is sea-slate, not
black or purple; creatures read as creatures; nothing overflows its panel.

---

## 12. References

- Liquid Midnight (sibling; materials and the render contract).
- Claude FM's one-glyph lattice (`research/entities/pattern/lattice-quantized-motion-art.md`) and the pretext
  typographic shader notes (`docs/specs/2026-08-05-typographic-shader-notes.md`) in broomva/workspace.
- Inspora: *Shark on vacation* and *shark ascii animation* (glyph-tile shoals on a calm field around a glass
  composer); *black hole.mp4* (a page of text bent by a lens: our `well`); *glass recorder* (thick refractive capsule:
  our `.ld-lens`); *Liquid glass* nav (a dropdown that bends the flowers behind it: our field-side refraction).
