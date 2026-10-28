# Liquid Midnight · DESIGN.md

**Status:** v0.1.0 (2026-10-28). **Scope:** keynotes, reels and feed posts, landing sections, and showcase cards in apps.
**Sources:** the Agent Workspaces keynote and reels ([broomva/agent-workspaces](https://github.com/broomva/agent-workspaces) `deck/index.html` @`187972f`), and a product landing page. The landing contributes only principles, materials and motion grammar.
**Relationship to the broomva-design skill:** an *independent sibling*, chosen by the owner on 2026-10-28. broomva-design is the calm, matte, blue-axis system for products. Liquid Midnight is the expressive system for showcases. Pick one per project, and do not mix their tokens on one surface. See §14.

This file is meant to stand alone. An agent with no other context should be able to produce on-style work from it, the tokens, `css/materials.css` and `kit/`.

---

## 1. The look in one paragraph

Apple **Midnight** blue-black grounds (hue 245–252, never purple), with one blue accent. Floating surfaces are **liquid glass**: a thin tint, so the live field shows through a light blur, a bright top edge and a cyan caustic along the bottom. Every one of them is rimmed in **liquid metal**: a conic chrome edge whose specular *travels* around the perimeter, with thin cyan, magenta and gold fringes at the highlights. Behind everything:
- a quiet **ASCII text shader** flows like molten metal;
- soft **ambient light** drifts;
- real **WebGL glass plasma orbs** (dark glass, plasma filaments, caustics) mark the living things.

Type is **Raleway Light** with tight tracking, and the key phrase is set in Raleway Regular blue. Motion is **springs and slow sweeps on one clock**. Every frame is a pure function of `t`, so a page can be rendered to video.

![Cover board](https://raw.githubusercontent.com/broomva/liquid-midnight/39523b3/docs/renders/pen/00-cover.png)

---

## 2. Principles

1. **Glass plus metal, always together.** Glass is the body. The travelling chrome rim is what makes it this style. A floating surface without the rim is not finished.
2. **The field must be alive behind the glass.** Glass is only as good as what it frosts. Put the ASCII flow, a canvas diagram or the ambient light under it. Glass over a flat colour reads as a grey box.
3. **One accent.** Blue (`--lm-blue`) carries emphasis, kickers, focus and the active route. Other hues are semantic only: green means retained or positive, coral means loss, gold means proven or ledgered, warm means human attention.
4. **Light, large, tight type.** Display is Raleway 300. Emphasis is a weight change (400) plus blue, never italics.
5. **Real materials, not decals.** An orb is a shader with refraction and plasma, not a radial gradient. Metal is a travelling specular, not a static grey stroke.
6. **Time-addressable motion.** Integrate state in fixed 1/60 s steps from t = 0 and seed every random draw. Derive the rim angle from `t`. Wall-clock CSS animation is only acceptable as the live-preview fallback.
7. **Judge the render, not the code.** Every surface gets rendered and looked at, in both modes, against the named references (§13).

---

## 3. Do and don't

**Do**
- Use Midnight grounds `oklch(0.155 0.028 250)` with a drifting ambient (blue, steel and ai blobs, blur 90).
- Give every floating surface (card, pill, segmented control, counter, caption chip) the liquid-glass body and the `--ua` chrome rim.
- Use the WebGL glass plasma orb (`kit/orb.js`) for agents, nodes and the brand mark. Fall back to `orb2d` only when WebGL is unavailable.
- Put a low-alpha ASCII flow under the glass (`asciiBackground`, alpha .15 night / .12 day).
- Use mono uppercase kickers with a 28 px leading rule, a Raleway 300 headline, and the payoff phrase in Raleway 400 blue.
- Render both modes and inspect them before calling anything done.

**Don't (each of these was rejected by the owner on sight)**
- ✕ **Purple casts** anywhere: grounds, glows, ambient. `--lm-violet` is a *steel*, not a purple.
- ✕ **The `arcan-glass` skill or its look.** It was asked to be removed.
- ✕ **A flat glass panel with no metal rim.** Verdict: "not implemented".
- ✕ **Soft radial-gradient "glow orbs"** in place of the plasma orb.
- ✕ **ASCII that reads as noise or rain**, for example an act background that was called "awful" and rebuilt. Keep the flow slow and capped at .72 density; never use falling columns or random flicker.
- ✕ Italic emphasis, bold display weights, generic "premium" purple-pink gradients, or glass stacked on glass.
- ✕ Wall-clock-only animation on anything that must render to video.

---

## 4. Colour

OKLCH is canonical. Hex values are sRGB fallbacks, emitted first in `tokens/tokens.css` and overridden inside `@supports (color: oklch(0 0 0))`. Modes: **night** (default, `:root`) and **day / paper** (`[data-lm-mode=day]`). Tones (`[data-lm-tone=graphite|abyss]`) override only the night grounds and secondary text; they are emitted before the day block, so `data-lm-mode=day` always wins. Nesting a night region inside a day page is not supported by the CSS materials (descendant selectors key on the nearest day ancestor); the kit's `readColors()` does honour the nearest `data-lm-mode`. For the same reason a tone set inside a day subtree is ignored.

<!-- tokens:start (generated by scripts/build-tokens.mjs; do not edit by hand) -->
| Token | Night (OKLCH) | Night hex | Day / paper (OKLCH) | Day hex | Role |
|---|---|---|---|---|---|
| `--lm-deep` | `oklch(0.155 0.028 250)` | `#040d18` | `oklch(0.968 0.005 250)` | `#f2f5f8` | Page ground. Cool blue-black, never neutral black, never purple. |
| `--lm-surface` | `oklch(0.205 0.03 245)` | `#0b1924` | `oklch(0.995 0.002 250)` | `#fcfdff` | Opaque panels; reduced-transparency and high-contrast fallback for glass. |
| `--lm-elev` | `oklch(0.245 0.03 245)` | `#14222e` | `oklch(0.95 0.006 250)` | `#ebeff2` | Raised opaque surface. |
| `--lm-t1` | `oklch(0.975 0.004 250)` | `#f5f7f9` | `oklch(0.22 0.006 260)` | `#191b1d` | Primary text, headlines, live values. |
| `--lm-t2` | `oklch(0.83 0.015 248)` | `#c0c8d1` | `oklch(0.42 0.012 255)` | `#494d54` | Body copy, ledes, inactive control labels. |
| `--lm-t3` | `oklch(0.65 0.022 248)` | `#85919c` | `oklch(0.55 0.014 255)` | `#6c727a` | Metadata, counter labels, tags. Not for essential instructions. |
| `--lm-line` | `oklch(0.78 0.03 245 / 0.12)` | `#a8baca1f` | `oklch(0.3 0.02 255 / 0.1)` | `#272e381a` | Hairline dividers. |
| `--lm-line2` | `oklch(0.78 0.03 245 / 0.24)` | `#a8baca3d` | `oklch(0.3 0.02 255 / 0.2)` | `#272e3833` | Visible edges, canvas grid lines. |
| `--lm-blue` | `oklch(0.71 0.15 252)` | `#54a5fc` | `oklch(0.55 0.18 255)` | `#026fd7` | THE accent: emphasised headline phrase, kickers, focus ring, active route. |
| `--lm-ai` | `oklch(0.62 0.19 256)` | `#2584f5` | `oklch(0.55 0.19 256)` | `#006ddd` | Agent/AI presence; ambient blob 3; deeper orb tint. |
| `--lm-violet` | `oklch(0.79 0.035 235)` | `#a6bfce` | `oklch(0.5 0.03 240)` | `#546673` | Despite the name: a neutral STEEL used for structure lines and ambient blob 2. Never a purple. |
| `--lm-cyan` | `oklch(0.81 0.12 225)` | `#5cd1fb` | `oklch(0.6 0.13 225)` | `#008fba` | Caustics, secondary flows, glass bottom edge. |
| `--lm-green` | `oklch(0.76 0.19 148)` | `#43d066` | `oklch(0.6 0.17 148)` | `#0e9a3f` | Retained / positive / write path. |
| `--lm-coral` | `oklch(0.67 0.21 28)` | `#fc5045` | `oklch(0.58 0.21 28)` | `#db2d27` | Loss / failure counters. |
| `--lm-gold` | `oklch(0.86 0.12 88)` | `#f2cd6f` | `oklch(0.62 0.13 80)` | `#af7c00` | Proven, built or ledgered paths only; merge commits. |
| `--lm-warm` | `oklch(0.79 0.16 65)` | `#ffa234` | `oklch(0.68 0.17 60)` | `#e27900` | Warnings, human attention. |
| `--lm-glass` | `oklch(0.24 0.03 248 / 0.5)` | `#14212d80` | `oklch(1 0 0 / 0.56)` | `#ffffff8f` | Base glass tint (HUD glass). |
| `--lm-glass-heavy` | `oklch(0.24 0.03 248 / 0.86)` | `#14212ddb` | `oklch(1 0 0 / 0.82)` | `#ffffffd1` | Reduced-transparency glass. |
| `--lm-rim` | `oklch(0.93 0.02 240 / 0.48)` | `#dceaf47a` | `oklch(1 0 0 / 0.95)` | `#fffffff2` | Static glass rim highlight. |
| `--lm-sheen` | `oklch(1 0 0 / 0.1)` | `#ffffff1a` | `oklch(1 0 0 / 0.75)` | `#ffffffbf` | Inset top-edge light. |
| `--lm-spec` | `oklch(0.96 0.02 235 / 0.15)` | `#e6f4fe26` | `oklch(1 0 0 / 0.55)` | `#ffffff8c` | Pointer-tracked specular. |

Liquid-metal palette:

| Token | Night (OKLCH) | Night hex | Day / paper (OKLCH) | Day hex | Role |
|---|---|---|---|---|---|
| `--lm-metal-steel` | `oklch(0.56 0.03 245)` | `#667785` | `oklch(0.66 0.02 248)` | `#89949e` | Metal body between highlights. |
| `--lm-metal-shine` | `oklch(0.985 0.015 240)` | `#f2fcff` | `oklch(0.24 0.03 245)` | `#13212d` | Travelling specular. |
| `--lm-metal-fringe-a` | `oklch(0.8 0.14 220)` | `#25d2fc` | `oklch(0.6 0.14 225)` | `#008fbe` | Spectral fringe: cyan. |
| `--lm-metal-fringe-b` | `oklch(0.72 0.19 350)` | `#f86ab5` | `oklch(0.6 0.18 350)` | `#ca488f` | Spectral fringe: magenta. Only ever a thin fringe at a highlight. |
| `--lm-metal-fringe-c` | `oklch(0.86 0.13 85)` | `#f8ca65` | `oklch(0.7 0.13 80)` | `#c8942d` | Spectral fringe: gold. |
<!-- tokens:end -->

**Tones.** `graphite` is near-neutral at hue 255 with chroma .004–.008, for footage-heavy reels. `abyss` is a deeper sea at hue 230. Both keep the same accents.

**Semantic rules.** A colour never carries meaning alone. Pair it with a label (counter labels, tags) or a structural cue. Coral marks loss counters and failure, never decoration. Gold marks only proven, built or ledgered paths.

---

## 5. Materials (exact CSS: `css/materials.css`)

The material recipes use literal `oklch()` colours (gradients and shadows with alpha), so they need an OKLCH-capable browser: Safari 15.4+, Chrome/Edge 111+, Firefox 113+. The tokens carry hex fallbacks; the materials do not, by choice (duplicating every gradient in hex would double the file for browsers this showcase style does not target).

All rims share one mechanism:
- a `::after` ring with 1.2 px padding;
- `mask-composite: exclude`, so only the border band shows;
- a `conic-gradient(from var(--ua), …)` with two bright stops (70° and 250°), each trailed by a fringe: cyan at 215, blue at 250 and gold at 85.

`kit/loop.js#setUA` advances `--ua` at 40°/s. It is registered with `@property` so it interpolates as an angle.

### 5.1 Liquid glass card: `.lm-glass` (deck lines 322-327)
```css
background: linear-gradient(180deg, oklch(0.36 0.03 248 / .3), oklch(0.2 0.03 250 / .26) 55%, oklch(0.17 0.03 250 / .34));
backdrop-filter: blur(9px) saturate(220%) brightness(1.12);
box-shadow: 0 30px 80px -30px oklch(0.04 0.02 250 / .85), 0 8px 22px -12px oklch(0.04 0.02 250 / .6),
  inset 0 1px 0 oklch(1 0 0 / .2),                 /* bright top edge */
  inset 0 14px 28px -18px oklch(1 0 0 / .1),       /* thickness */
  inset 0 -22px 34px -26px oklch(0.8 0.12 222 / .22), /* cyan caustic along the bottom */
  inset 0 0 0 1px oklch(1 0 0 / .045);
/* ::before pointer specular: radial-gradient(480px circle at var(--mx) var(--my), var(--lm-spec), transparent 62%) */
/* ::after rim: conic chrome, opacity .62 (.55 day) */
```
Radius 22 for cards, 24 on reels, 28 for act breakers; padding 32/36. **Blur stays light (9 px).** The field must stay legible through the glass; heavy frost is a different, rejected look.

### 5.2 Capsule (nav pill, segmented control): `.lm-capsule` (deck lines 309-318)
Dark, thick glass:
- `linear-gradient(180deg, oklch(0.29 0.022 250 / .66), oklch(0.185 0.024 250 / .74))`;
- `blur(26px) saturate(180%)`;
- a deep drop shadow;
- a lit top edge `inset 0 1px 0 oklch(1 0 0 / .16)` and a dark bottom edge.

The rim runs at opacity .9 with an extra blue stop at 80°. Inside it:
- **Raised chip** `.lm-chip`: 40 px tall, gradient `oklch(1 0 0 / .075) → .018`, inset top light. Pressed state is a blue glass fill with a `0 0 18px -4px` blue bloom.
- **Segmented thumb** `.lm-thumb`: a raised glass chip with a thin metal inner rim. Its x and width ride springs (§8).

### 5.3 Paper gel (day mode): `.lm-glass.lm-gel` (from the landing)
Milky day glass:
- a pointer sheen `radial-gradient(140px circle at var(--mx) var(--my), white/80%, transparent 62%)` over a white thickness gradient (.58 → .16 → .30);
- `blur(8px) saturate(220%) brightness(1.05)`;
- **gel insets** `inset 0 1px 1px white/95%, inset 0 -1px 1.5px white/55%, inset 0 0 12px white/45%`;
- **shadow ink hued to the brand, never black**: `oklch(0.3 0.08 250 / .08–.18)`.

The metal rim stays, at .55 opacity. On light surfaces the specular inverts: `--lm-metal-shine` is a dark glint in day mode.

### 5.4 Chrome ring: `.lm-ring` (deck lines 359-363)
Focal round buttons get a 2 px conic ring rotating at **2× `--ua`**, over a dark radial body (`.lm-orb-button`). Icons inside are stroked with the SVG metal gradient `#lm-metal` (deck `#mtl`): `#f6f8fc · .42 #9ea7b8 · .58 #e6ebf3 · #5c6577`; day `#lm-metal-day` (deck `#mtlDay`): `#58606f · .45 #232833 · .6 #6d7585 · #1b1f27`.

### 5.5 Metal text and metal lines
- `.lm-metal-text`: `linear-gradient(180deg, #f7f9fd, #c9d0dc 45%, #eef2f8 58%, #9aa3b4)` clipped to glyphs. Day mode uses graphite: `#3a414d → #1d2129 → #525a68`.
- Canvas lines use `kit/metal.js#ribbon`: the strands carry `metalGrad` (steel → shine → steel, a band .1 wide). The band travels at phase `((t·0.21 + seed·0.1373) mod 1.3) − 0.15`. A bright core `fringe` follows, plus ±1.2 px cyan and magenta fringes drawn with `lighter` compositing (`source-over` in day mode).
- `metalRing(x, y, R, t)`: a steel base plus two travelling lobes (`cos¹⁰` and `cos¹⁶`, the second at 0.63× speed). Where a lobe is brightest (v > .18) it splits into fringes: cyan at −0.95·lw, magenta at +0.95·lw, gold at +1.9·lw.

### 5.6 Ambient light: `.lm-ambient`
Three 52 vmax radial blobs, all at blur 90 and opacity .5 (.38 day):
- **blue** at 45%, drifting 44 s;
- **steel** at 32%, drifting 56 s;
- **ai** at 34%, drifting 60 s.

All drift `ease-in-out infinite alternate`. In capture mode, freeze them or drive their transforms from `t`.

---

## 6. Orb, ASCII and field recipes (`kit/`)

![Orb · ASCII board](https://raw.githubusercontent.com/broomva/liquid-midnight/39523b3/docs/renders/pen/05-orb-ascii.png)

### 6.1 WebGL glass plasma orb (`kit/orb.js`, shaders in `kit/orb-shaders.js`)
- **Look** (reference: vault.rickybharti.com/orbloom): a thick glass sphere around a plasma core.
  - Plasma: two noise-bent filament arms (pow 14 / 22), 11 rays, two caustic layers, a rim flare and a hot core.
  - Glass: refraction `k = 1 − .4·r^2.4`, chromatic split only where r > .8, fresnel `(1 − z)³`, a bottom caustic, a top-left specular at (−.36, .44), a thin rim glint and a bloom out to 1.68 r.
- **Colour:** pass any token. A = the colour lifted 40% toward cyan (filaments); B = the colour × (.8, .8, .85) per RGB channel (body). Blue orbs get a rim tint of .45 and other hues .08. That small blue-violet lift at the fresnel edge is part of the approved look; do not raise it.
- **Use:**
  ```js
  ORB.attach(canvas); ORB.begin(ctx); orb(x, y, r, C.blue, t); ORB.end();
  ```
  This batches every orb in one WebGL pass. Called outside a batch, `orb()` renders a 256² sprite. With no WebGL it calls `orb2d()`.
- **Limits:** outside a batch, an orb renders through one shared 256² sprite, so a sprite orb larger than about 128 css px at 2× DPR is upscaled and softens. Batch large hero orbs. Batched orbs follow translation and uniform scale only: a rotated or non-uniformly scaled context is not supported (draw orbs before applying such transforms).
- **Sizing:** the visible sphere radius is .62 r; the sprite spans ±1.7 sphere radii, so its side is 3.4 × the sphere radius (1.7 × its diameter). The batch layer is an absolutely positioned overlay at the canvas's content box, inserted right after it, so the canvas's offset parent must be positioned (e.g. a `position: relative` wrapper); a `position: fixed` canvas gets a fixed layer. Each source canvas gets its own layer, released when the canvas leaves the DOM, shadow roots included (or with `ORB.detach(cv)`). CSS transforms on the canvas are not followed: transform a wrapper that contains both, or skip `attach` and use the sprite path.
- **Pencil:** `design/shaders/orb.glsl` is the same shader as a pen.dev shader fill. Use a **square** node whose side is 3.4 × the sphere radius you want; non-square nodes draw an ellipse.

### 6.2 ASCII text shader (`kit/ascii.js`)
- **Ramp** `' .·:-=+*%#@'`. Never change it: the ramp is the look.
- **Atlas:** `atlas(fs, colour, set)` bakes glyphs at the canvas's own device scale, so they copy 1:1 and frames stay byte-identical.
- **Field:** `asciiField(x, y, w, h, cell, A, fn)`; `fn → 0..1` picks the glyph, and ≤ .02 leaves the cell empty.
- **Background:** `asciiBackground(canvas)` draws `metalFlow` with 11 px glyphs on a 15 px cell, alpha **.15 night / .12 day**:
  ```
  f = sin(x·.011 + sin(y·.008 + t·.19)·1.7 + t·.13)·.5 + .5
  g = sin(y·.015 − t·.11 + sin(x·.005 + t·.07)·2.2)·.5 + .5
  v = min(.72, (f·g)^2.2 · 1.25)
  ```
- **Glyph trails** behind moving orbs: `glyphTrail(at, colour, 12)` steps `'Oo+:.'` with a linear fade (.85 → 0).
- **Act-breaker pieces:** `dotRing` (dotted ASCII orbits) and `ringText` (verbs streaming around a metal ring, brightened by a sweep), always under a frosted glass card. Each piece is generated once from a seed and then animated by `t`.
- **Pencil:** `design/shaders/ascii.glsl` with the baked `ascii-atlas.png`, which `scripts/bake-atlas.mjs` regenerates.

### 6.3 Living-diagram grammar (`kit/core.js`, `kit/metal.js`)
- Cubic béziers: `hc`, `vc`, `bend`.
- Multi-strand metal `ribbon`s that spread from s0 to s1 px and breathe by `amp`.
- Edge particles `Flow`: alpha follows `sin(πu)`; `advance()` integrates and `draw()` paints.
- `march` dashes are reserved for the *active* or build route.
- Glow dots mark nodes. Labels are mono uppercase.
- Glass cards sit *above* the canvas, so the diagram reads through them.

### 6.4 Landing field (paper mode)
The landing replaced the ASCII field with a soft three-colour grain-gradient shader:
- softness .8, intensity .12, noise .10–.18;
- three wave states (quiet, busy, flood) that crossfade on the scroll clock;
- the background travels paper → wash → night through the brand hue, never through grey.

Use this as the day-mode field option.

---

## 7. Typography

Vendored in `fonts/`, all SIL OFL 1.1: Inter, Raleway, JetBrains Mono (variable woff2) and Roboto Flex.

| Role | Family | Weight | Size / line-height | Tracking | Notes |
|---|---|---:|---|---|---|
| Hero | Raleway | 300 | 156 / .98 | −.045em | the payoff phrase in 400 `--lm-blue`; no italics |
| Act breaker | Raleway | 300 | 104 / 1 | −.04em | centred, inside a radius-28 glass card |
| Reel title | Raleway | 300 | 100 / 1.02 | −.034em | text-shadow `0 2px 30px deep/.6` over busy fields |
| Title | Raleway | 300 | 76 / 1.04 | −.032em | max width ≈ 1100 px |
| Card title | Raleway | 400 | 34 / 1.12 | −.02em | |
| Lede | Inter | 400 | 26 / 1.45 | −.011em | `--lm-t2`, max 820 px |
| Body | Inter | 400 | 21 / 1.5 | 0 | `cv11`, `ss01` |
| Control | Inter | 500 | 17 / 1 (chips 14) | 0 | |
| Kicker | JetBrains Mono | 500 | 15 / 1 | .16em, uppercase | `--lm-blue`, 28 × 1.5 px leading rule, gap 14 |
| Tag | JetBrains Mono | 500 | 13 / 1 | .14em, uppercase | `--lm-t3`, 8 px glowing dot |
| Counter value / label | JetBrains Mono | 500 | 38 / 16 | .04em / .18em | tabular numerals, zero-padded `042` |
| Code / paths | JetBrains Mono | 400 | 18.5 / 1.62 | −.01em | keywords blue, strings t1, comments t3 |
| Intent caption | Roboto Flex | 500 | 64 / 1.2 | 0 | ≤ 22 chars per line, translucent Midnight box |

Tracking tightens as size grows. Sizes are given at stage scale (1920 × 1080 or 1080 × 1920). For the web, scale them with `clamp()`, keeping the ratios.

![Typography board](https://raw.githubusercontent.com/broomva/liquid-midnight/39523b3/docs/renders/pen/02-typography.png)

---

## 8. Motion

| Thing | Spec |
|---|---|
| Rim angle `--ua` | `(t · 40) mod 360` deg; focal rings 2×; frozen (0°) under reduced motion |
| Springs (`Sp.step(dt, response, damping)`) | Apple-style response r (s per cycle) and damping ratio z. Integrated in ≤ 8 ms substeps and interruptible (it animates from the live value) |
| Default | r .5, z 1: reveals, counters, positions |
| Scene presence | r .34, z 1 |
| Segmented thumb, chips | r .4, z 1 |
| Large panels | r .6, z 1 |
| Playful | r .8, z .9: slight overshoot |
| Beats | `beat(t, t0, d)` uses ease-out-cubic over `[t0, t0+d]`, for time-addressed reveals |
| CSS easing | entrances `cubic-bezier(.22,1,.36,1)`; exits about 45% shorter than entrances (landing: enter .8 s, exit .45 s); staggers .03–.28 s |
| Press | `scale(.96)`, chips `.97`, and no CSS transitions on buttons |
| Metal sweep | one pass ≈ 6.2 s per path, offset per path by its seed so sweeps never sync |
| Ambient drift | 44 / 56 / 60 s alternate |
| Scroll stories | one clock scrubbed by scroll (`t = T · progress`), smoothed by a critically damped follower (τ ≈ 120 ms); no CSS view timelines |
| Render contract | `createLoop({init, step, paint}).renderAt(t)` replays fixed 1/60 s steps from 0 with `reseed()`. A headless browser renders any frame (see `?t=` in the specimen). Capture pages pin motion on (`setMotion(true)`), so frames do not depend on the capturing machine's reduced-motion setting |

![Motion board](https://raw.githubusercontent.com/broomva/liquid-midnight/39523b3/docs/renders/pen/06-motion.png)

---

## 9. Formats

| Format | Size | Safe zone | Notes |
|---|---|---|---|
| Keynote 16:9 | 1920 × 1080 | content margin left 140, top 116 | stage scaled to fit; HUD capsules at 24 px from the edges |
| Reel 9:16 | 1080 × 1920 | top 250, bottom 480, left 64, right 150 | IG Reels and TikTok UI. Kicker at y 262, title at y 300, content width 866; captions: Roboto Flex 64, ≤ 22 chars, margins L 64 / R 150 / V 500 |
| Feed 4:5 | 1080 × 1350 | top 80, bottom 120, sides 64 | the same stage grammar, cropped |
| Landing | fluid | max widths 1180 (hero) and 960; body ≤ 625 px | hero `min-height: 100vh`; nav capsule 62 px |

![Formats board](https://raw.githubusercontent.com/broomva/liquid-midnight/39523b3/docs/renders/pen/07-formats.png)

---

## 10. Spacing and radii

- Base unit 4 px. Ladder: 4, 8, 12, 16, 20, 24, 32, 44, 64, 116, 140.
- Radii: chip 18 · card 22 · reel card 24 · breaker 28 · capsule 999.
- Gaps: kicker rule 14; chips inside a capsule 2–4; cards in a row 18–24.

---

## 11. Accessibility

Measured contrast (WCAG 2), text on ground and on surface:

| Text | Night on deep | Night on surface | Day on deep | Day on surface |
|---|---:|---:|---:|---:|
| t1 | 18.2 | 16.6 | 15.8 | 17.0 |
| t2 | 11.5 | 10.5 | 7.8 | 8.3 |
| t3 | 6.1 | 5.5 | **4.4** | 4.8 |
| blue | 7.6 | 6.9 | 4.5 | 4.8 |
| green | 9.7 | 8.9 | **3.4** | 3.6 |
| coral | 5.9 | 5.4 | 4.3 | 4.7 |
| gold | 12.8 | 11.7 | 3.4 | 3.6 |

- In day mode, `green` and `gold` reach only 3:1 on the ground, so use them for large text (≥ 24 px) or as non-text marks; never for body or small labels. `t3` and `coral` sit just under 4.5:1 on the day ground: large text there, or small text on `surface` (≥ 4.6:1). A label next to a colour does not make low-contrast text readable; it only stops colour being the sole carrier of meaning.
- Glass sits on a live field, so check contrast against the *darkest and brightest* frames. Keep text on glass at t1/t2. If the field gets bright, raise the tint, do not shrink the type.
- **Reduced transparency:** glass becomes `--lm-glass-heavy` with no backdrop filter (restated last in the CSS, so no material beats it).
- **More contrast:** opaque `--lm-surface`, a 1.5 px `t2` outline, and no rim.
- **Reduced motion:** the live clock holds still (`createLoop().start()` stops advancing `t`, as the deck did), springs snap, `--ua` and the ASCII flow freeze, and the ambient light stops. `MOTION` follows the OS setting live; `setMotion(true|false)` pins it and `setMotion(null)` hands it back. `renderAt(t)` still seeks, because a capture asks for that frame explicitly. Under reduced motion the live loop repaints only when something changes: DOM driven from `step()` updates every frame, but **any canvas change made outside `step()` must call `loop.invalidate()`**. Typical triggers are a resize or `fit()` (it clears the canvas), a theme switch, new data, a font swap, and a GPU context restore (`ORB.onChange(() => loop.invalidate())`).
- **Focus:** a 2 px `--lm-blue` outline with 2 px offset. Never remove it.
- Canvases and orbs are decorative (`aria-hidden`) unless they carry data; diagrams that do carry data get a text equivalent.
- Render-to-video: burn captions in (OpenCaptions-style box) and keep them inside the reel safe zone.

---

## 12. How to apply

### 12.1 Keynote scene (16:9)
1. Ground `.lm-ground`, `.lm-ambient`, plus the `asciiBackground` canvas under the stage.
2. Head at left 140, top 116: kicker, then a Raleway 300 title with the payoff phrase in `<em>` (400 blue).
3. Draw the diagram on a 1920 × 1080 canvas with ribbons, `Flow` particles and orbs. Use `ORB.attach/begin/end` per frame.
4. Floating cards are `.lm-glass` above the canvas, with radius 22 and padding 32/36.
5. Reveal with springs (r .5) or `beat()`. Drive everything from `createLoop`, and expose `window.renderAt`.
6. Render t = 0, the mid-beats and the end in night and day. Look at every frame.

### 12.2 Reel (9:16)
1. Stage 1080 × 1920 with the safe zone top 250, bottom 480, left 64, right 150.
2. Kicker at y 262 with a right-side meta label in t3. Title Raleway 300 100 at y 300, width 866.
3. Controls: a `.lm-capsule.lm-seg` at y ≈ 528, glass chips, glass counters at y ≈ 1150.
4. Centre the focal diagram on the safe-area centre line (x ≈ 497).
5. Captions: Roboto Flex 64, ≤ 22 chars, the spoken keyword in blue, a translucent Midnight box, bottom margin 500.
6. Render through `renderAt(t)` at 60 fps, then check stills at the beats and the full video.

### 12.3 Landing section
1. Choose a mode: night (Midnight field), or paper (day tokens, the gel glass and the grain-gradient field of §6.4).
2. Run one scroll-scrubbed clock with a critically damped follower. The authored static markup must be fully readable before enhancement.
3. Hero: kicker, display headline, lede, one orb. The nav is a capsule pill with a metal rim.
4. On any GPU or frame failure, dispose of the contexts and fall back to the static markup.
5. Honour reduced motion and reduced transparency (§11), and screenshot it at 1440 and 390 widths.

### 12.4 App card (showcase moments inside a product)
1. Use it sparingly: one glass card with the metal rim on an otherwise calm surface (onboarding hero, empty state, achievement). Product chrome stays on the product's own system.
2. The card is `.lm-glass.lm-card` with a tag, a card title (Raleway 400 34), body text in t2, and an optional `.lm-counter`.
3. Put a small orb (sprite mode) or an ASCII strip *behind* the card so the glass has a field to frost.
4. Check the card in reduced-transparency and high-contrast modes.

---

## 13. Verification culture

The owner judges the **rendered result** against named references. Code review is not acceptance.
- Every page and scene is rendered (headless, `renderAt(t)`) in **night and day**, and looked at.
- References: the Agent Workspaces keynote frames; the reel `reel-01-folder-v2`; vault.rickybharti.com/orbloom for the orb; the basit_designs liquid-glass nav pill for capsules and metal icons.
- The specimen (`specimen/index.html`, rendered by `bun run render`) and the Pencil boards (`design/liquid-midnight.pen`) are the visual contract. Re-render both whenever tokens or materials change.

![Specimen · hero](https://raw.githubusercontent.com/broomva/liquid-midnight/39523b3/docs/renders/night-hero.png)

---

## 14. Where the keynote and the landing agree and differ

| Dimension | Keynote and reels | Landing | System rule |
|---|---|---|---|
| Default mode | Night (Midnight) | Day / paper | Both are first-class modes: `[data-lm-mode]` |
| Hue axis | 245–252 blue | its own brand hue, with blue only in the chrome stops | **The hue axis is a parameter.** Keep the materials and swap the accent and ground hue together, at the same lightness and chroma |
| Display type | Raleway 300, −.032 to −.045em | a geometric sans 500, −.058em, `text-wrap: balance` | Raleway 300 is the style. A brand face may replace it only if it stays light and tightly tracked |
| Kicker | mono 15, .16em, leading rule | mono 11, .08em | same grammar; scale with the format |
| Glass | blur 9, saturate 220%, cyan caustic | saturate 220% (agrees), blur 3–34 per surface, gel insets, SVG liquid lens ("bend, don't blur") | Night uses `.lm-glass`; paper uses `.lm-gel`. A lens is optional |
| Chrome rim | conic, `--ua` 40°/s | the same port, page-wide `--ua` 40°/s | identical |
| Orb, ASCII | WebGL orb, ASCII field | the same shader and the same ASCII flow, recoloured | identical, colour-parameterised |
| Field | ASCII metal flow | grain-gradient shader with quiet, busy and flood states | night → ASCII; paper → grain gradient |
| Clock | `renderAt(t)` per scene | one scroll-scrubbed clock (73 s story) with a τ 120 ms follower | one clock per surface, always pure in `t` |
| Shadows | blue-black | ink hued to the brand, never black | shadow ink always takes the ground hue |
| Robustness | WebGL → `orb2d` | static markup first; failure disposes GPU and restores markup | both |

**Relationship to broomva-design.** Its tokens use hue 265 and a deeper `oklch(0.135 0.02 272)` ground. Glass is reserved for elevated surfaces, and the default is matte. Liquid Midnight does the opposite on purpose: expressive glass everywhere that floats, at hue 250. Treat them as siblings: a product uses one, and a showcase uses the other. If a product needs one showcase moment, import a single `.lm-glass` card per §12.4. Do not merge the token sets.

---

## 15. Files

| Path | What |
|---|---|
| `tokens/tokens.json` | source of truth (colour, type, radius, motion, formats) |
| `tokens/tokens.css` | generated custom properties (hex fallback + OKLCH), modes and tones |
| `css/materials.css` | glass, capsule, chip, ring, metal text, counter, caption, ambient, a11y fallbacks |
| `kit/` | ES-module render kit: `core` (maths, PRNG, springs, béziers, canvas primitives), `metal`, `ascii`, `orb` (WebGL + 2D fallback), `loop` (render contract) |
| `specimen/index.html` | live specimen of every token, material and component in motion (`bun run serve`) |
| `design/liquid-midnight.pen` | Pencil boards 00–07; `design/shaders/` holds the shader fills |
| `docs/renders/` | specimen renders (night and day) and Pencil board exports |
