# Broomva look — condensed spec

Paste this to another agent to make anything look like Broomva. It is the
visual foundations only, distilled. Pair it with `broomva-essentials.css`
(link that file and the tokens below are already defined).

---

## The one-sentence brief

Calm, monochrome design on a blue axis: every "black" is a barely-blue dark
ink, every gray is cool, color earns its place, glass is earned only by
floating surfaces, and every shadow carries a faint blue. It reads as plain
monochrome until you look closely — then everything is faintly, coolly blue.

## Non-negotiables (get these wrong and it isn't Broomva)

1. **The ink is blue-black, not black.** `oklch(0.175 0.022 265)`. Never `#000`.
2. **Every neutral is cool** — hue 265, whisper chroma. No warm grays, ever.
3. **One accent hue: ai-blue** `oklch(0.60 0.12 260)`. It carries links, focus,
   info, and the frosted interaction layer. A second blue `oklch(0.65 0.14 235)`
   ("accent-blue") appears only to own "Needs you". No other decorative color.
4. **Color earns its place.** It shows up in exactly: status dots/pills, the
   ai-blue focus/hover/selected frost, and live-signal glow. Everything else is
   monochrome. No gradient washes, no colored left-border strips.
5. **Glass is earned.** Only overlays (dialogs, command palette), popovers
   (menus, tooltips), and the composer get glass — and each carries an inner
   light line `inset 0 1px 0 rgba(255,255,255,.7)`. Cards, panels, sidebars,
   headers are matte. Always.
6. **Shadows are blue-tinted**, in three tiers: a 1px edge at rest, a diffuse
   16px lift on hover, and the composer halo (a wide 80px frosted-blue bloom) as
   the single dramatic depth cue. No inner shadows, no dense gray shadows.
7. **Dark mode is deep blue-purple** `oklch(0.135 0.02 272)`, never black, and
   never pure-white text.

## Type

- System font stack. Regular 400 is the default weight; 500 for buttons and
  section headers; 600 reserved for empty-state titles only.
- Tight scale, nothing else: **12 / 14 / 16 / 18 / 22 / 24 / 28** px.
- Sentence case everywhere. Never Title Case, never UPPERCASE, never
  letter-spacing on labels, never uppercase eyebrows.
- Headings sit at normal weight with `-0.01em` tracking; body at 1.5 line-height.

## Shape & motion

- **Radii ladder:** chips `.25rem` → inputs `.375rem` → rows/icon-buttons
  `.5rem` → cards `.75rem` → dialogs `1rem` → composer `28px` → pills full.
  Pill radius is for buttons and avatars only — **never cards**.
- **Buttons are pills.** Primary = ink fill, hover lightens one step. Ghost/soft
  hover = frosted-blue fill (`--bv-frost`). No scale, no rotation, no glow on
  hover. Pressed = one step deeper frost; the button stays still.
- **Motion under 300ms** (200ms common), `cubic-bezier(0.25,0.1,0.25,1)`. Enter
  `opacity:0, y:8 → 1,0`. Calm, never bouncy. Motion encodes presence, not
  urgency. Everything stops under `prefers-reduced-motion`.
- **Borders are whisper-soft** blue-black at ~7% for dividers, ~16% for edges
  that must be seen. A solid opaque border looks wrong here.

## Icons

Lucide only, pinned to an exact version. 20px standard / 16px inline / 24px
empty-state. 2px stroke, round caps, `currentColor`. No fill icons, no mixed
libraries, no emoji as icons.

## Layout defaults

Flat white canvas; cool-gray soft surface for sidebars. 4px spacing base. The
app shell never scrolls; inner panels do.

## The core tokens (all in `broomva-essentials.css`)

```
--bv-ink            oklch(0.175 0.022 265)   text + primary buttons
--bv-paper          oklch(1 0 0)             white canvas
--bv-canvas         oklch(0.966 0.003 265)   cool soft surface / sidebar
--bv-text-muted     oklch(0.50 0.015 265)    secondary text
--bv-text-body      oklch(0.38 0.020 265)    long-form body
--bv-blue           oklch(0.60 0.12 260)     the one accent
--bv-frost          oklch(0.60 0.12 260/.09) hover / selected fill
--bv-border         oklch(0.25 0.04 265/.07) whisper divider
--bv-border-strong  oklch(0.25 0.04 265/.16) visible edge
--bv-success/warning/danger                  status dots only
--bv-needs-you      oklch(0.65 0.14 235)     the gate — never red
--bv-shadow-edge / -hover / -composer        the three blue-tinted tiers
--bv-radius-card 0.75rem · --bv-radius-full 9999px · --bv-radius-composer 28px
--bv-ease cubic-bezier(0.25,0.1,0.25,1) · --bv-dur 0.2s
```

## Don't

- No pure `#000`, no pure-white dark-mode text — all colors are OKLCH.
- No glass on cards, sidebars, or chrome. Glass is for floating surfaces only.
- No new hues. No gradient washes. No colored accent strips.
- No warm grays. No Title Case, UPPERCASE, or letter-spaced labels.
- No scale/rotate/glow on hover — hover is a frosted-blue fill or one-step lighten.
- No progress percentages for agent work — show receipts (what changed, decided, asks).
- No em dashes or emoji in UI chrome.

---

*This is the visual distillation. The full system (components, work-model
primitives, the Undertow live signal, voice) lives in `readme.md` and `SKILL.md`.*
