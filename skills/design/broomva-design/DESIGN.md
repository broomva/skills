# Design System: Broomva
**Project ID:** broomva-blue-axis

## 1. Visual Theme & Atmosphere

Broomva is a calm operating surface for human and agentic work. It feels precise, quiet, and observant: white or deep-blue canvases, blue-black ink, fine borders, matte working surfaces, and a single current of blue light when the system is alive.

The visual hierarchy comes from spacing, typography, and tonal contrast rather than decoration. Application chrome stays restrained and information-dense. Depth is rare and meaningful. Glass indicates that a surface floats above the work; glow indicates live work. Marketing surfaces may become more atmospheric, but the product remains legible, direct, and grounded.

Core characteristics:

- Blue-axis monochrome: apparent blacks and grays carry a subtle hue near `265`.
- Matte by default: cards, sidebars, panels, and navigation do not use glass.
- Earned spectacle: the composer halo, Undertow, and tidepool are the only signature dramatic cues.
- Honest work: states, receipts, asks, and lifecycle stages replace invented progress percentages.
- Quiet geometry: compact controls, a 4px spacing ladder, moderate card radii, and ample breathing room.

## 2. Color Palette & Roles

### Primary foundation

- **Blue-black ink** (`oklch(0.175 0.022 265)`) — Primary light-theme text, solid buttons, and the deepest product mark. It reads as black until inspected closely.
- **Paper white** (`oklch(1 0 0)`) — Light-theme page and card surface. Use pure white as a surface, never as dark-theme body text.
- **Cool soft canvas** (`oklch(0.966 0.003 265)`) — Sidebars, quiet secondary surfaces, and low-emphasis grouping.
- **Deep current canvas** (`oklch(0.135 0.020 272)`) — Dark-theme page background; a blue-purple near-black, never neutral black.
- **Soft ice foreground** (`oklch(0.965 0.004 265)`) — Primary text and high-emphasis icons on dark surfaces.

### Accent and interactive

- **Resonant AI Blue** (`oklch(0.60 0.12 260)`) — Links, focus rings, information, selection, and live-system glow. It is the default accent and should remain scarce.
- **Tidepool Cyan** (`oklch(0.65 0.14 235)`) — Secondary accent reserved for `Needs you` and the coolest edge of live-signal weather.
- **Frosted selection** (`oklch(0.60 0.12 260 / 0.09)`) — Selected rows and hover states when a blue relationship is useful.
- **Visible focus** (`var(--bv-blue)`) — A `2px` focus ring with at least `2px` separation. Never remove it without an equivalent.

### Typography and text hierarchy

- **Primary ink** (`oklch(0.175 0.022 265)`) — Titles, body text, and primary actions on light surfaces.
- **Slate body** (`oklch(0.38 0.020 265)`) — Long-form secondary copy with comfortable contrast.
- **Muted current** (`oklch(0.50 0.015 265)`) — Metadata and supporting labels, not essential instructions.
- **Placeholder mist** (`oklch(0.68 0.010 265)`) — Placeholder text and deliberately low-emphasis content.

### Functional states

- **Resolved green** (`oklch(0.62 0.17 152)`) — Success and completed outcomes.
- **Informational blue** (`oklch(0.60 0.12 260)`) — Information and live work.
- **Attention amber** (`oklch(0.76 0.15 85)`) — Warnings and blocked-but-recoverable conditions.
- **Intervention red** (`oklch(0.56 0.21 27)`) — Errors, destructive actions, and urgent intervention.

Every functional color requires a text label, icon, or structural cue. Color alone never communicates state.

OKLCH values are canonical. Do not introduce raw hex aliases into implementation code; use semantic tokens so light and dark roles stay coupled.

### Borders and depth

- **Whisper edge** (`oklch(0.25 0.04 265 / 0.07)`) — Default dividers and card boundaries.
- **Visible edge** (`oklch(0.25 0.04 265 / 0.16)`) — Inputs and secondary buttons.
- **Emphasis edge** (`oklch(0.25 0.04 265 / 0.26)`) — Rare emphasized boundaries.
- **Composer bloom** (`0 4px 80px 8px oklch(0.55 0.12 260 / 0.08)`) — The one broad light bloom in product UI; reserve it for the composer.

## 3. Typography Rules

Application chrome uses system fonts deliberately. Cal Sans is a display accent, not the default interface typeface.

| Role | Font | Weight | Line height | Notes |
|---|---|---:|---:|---|
| Screen title | `ui-sans-serif, -apple-system, system-ui, "Segoe UI", Helvetica, Arial, sans-serif` | Regular (400) | Tight (1.25) | `28px`, `-0.01em`; direct, sentence-case title |
| Section title | System sans stack | Medium (500) | Tight (1.25) | `22px` or `24px`, `-0.01em`; avoid oversized dashboard headings |
| Empty-state title | System sans stack | Semibold (600) | Tight (1.25) | `24px`; the only semibold product heading tier |
| Body and chat | System sans stack | Regular (400) | Normal (1.5) | `16px`; default reading tier and mobile input minimum |
| Controls and navigation | System sans stack | Medium (500) | Normal (1.5) | `14px`; buttons, tabs, sidebar rows |
| Metadata | System sans stack | Regular (400) | Normal (1.5) | `12px`; timestamps, codes, and secondary labels |
| Marketing display | `"CalSans", ui-sans-serif, system-ui, sans-serif` | Semibold (600) | Tight (1.25) | Opt in with `[data-display-font="calsans"]`; use for heroes, not app chrome |
| Receipts and identifiers | `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace` | Regular (400) | Normal (1.5) | Compact machine-readable evidence |

Use the fixed scale `12 / 14 / 16 / 18 / 22 / 24 / 28px`. Use sentence case everywhere. Product copy is plain, precise, and usually second person. Do not use emoji, em dashes, title case, or decorative eyebrow labels.

## 4. Component Stylings

### Buttons and icon controls

- **Shape:** Compact pill-shaped controls (`9999px`) with `36px` default and `44px` large heights. Icon buttons use moderately rounded corners (`0.5rem`), not circles by default.
- **Surface:** Primary buttons use Blue-black ink; secondary and soft buttons use cool matte surfaces; ghost buttons remain transparent.
- **States:** Hover changes tone, not geometry. Focus uses the Resonant AI Blue ring. Disabled controls retain their label and reduce contrast without becoming invisible.
- **Transition:** Fast (`150ms`) for hover and focus; standard easing (`cubic-bezier(0.25, 0.1, 0.25, 1)`). Never use `transition: all`.

### Cards and containers

- **Shape:** Restrained rounded corners (`0.75rem`) for normal cards and `1rem` for large cards or dialogs. Never make every container pill-shaped.
- **Surface:** Matte Paper white or dark card surface with a Whisper edge. Cards do not use glass.
- **States:** Interactive hover may add a soft blue-tinted shadow without moving the card. Running cards sit inside Undertow rather than changing their border into an animated progress meter.

### Navigation

- **Layout:** A quiet `200px` sidebar and `52px` header establish the desktop shell. Active rows use Frosted selection with clear foreground contrast.
- **Typography:** Medium `14px` labels in sentence case. Icons support recognition but do not replace labels for primary navigation.
- **Responsive behavior:** Collapse into a mobile shell that preserves the current task and composer. Avoid hiding essential state behind hover-only disclosure.

### Inputs and forms

- **Shape:** Moderately rounded corners (`0.375rem`) with a visible `1px` edge. The composer alone uses the signature `28px` radius.
- **Surface:** Inputs are matte. The composer may use heavy glass and the Composer bloom because it floats above the work plane.
- **States:** Placeholder Mist is visibly subordinate; focus uses Resonant AI Blue; errors pair Intervention red with text. Mobile inputs remain at least `16px` to prevent browser zoom.
- **Accessibility:** Every field has a persistent accessible label, errors are programmatically associated, and controls are operable by keyboard.

### Overlays and floating surfaces

- **Surface:** Dialogs and command palettes use heavy frosted glass (`32px` blur, saturation `2.0`); menus, tooltips, and popovers use lighter frosted glass (`22px` blur, saturation `1.8`).
- **Shape:** Popovers use `0.75rem`; dialogs use `1rem`.
- **Depth:** A blue-black scrim separates the overlay from the page. Background text must not remain legible through the frost.
- **Behavior:** Focus is trapped in modal dialogs, Escape closes when safe, and focus returns to the trigger.

### Work and agentic states

- **Vocabulary:** `Queued`, `Running`, `Stuck`, `Needs you`, `Done`, `Standing`.
- **Live signal:** Undertow is a contained halo frame around active work. Tidepool is its compact dot-scale form. Both become static but still legible under reduced motion.
- **Evidence:** Run cards foreground decisions, asks, receipts, and lifecycle stages. Never imply certainty with a synthetic progress percentage.

## 5. Layout Principles

- Use a `4px` base ladder: `4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48px`. New spacing values require a system-level reason.
- Keep chat and reading content at a comfortable maximum width of `768px`. Let work feeds breathe; do not fill the viewport with equal-weight cards.
- Establish hierarchy with whitespace and alignment before borders, shadows, or color.
- Design mobile-first, then verify at `375px`, `768px`, and `1440px`. No horizontal overflow is acceptable.
- Keep primary actions near the content they affect. Persistent composers may dock, but must not obscure the last item or keyboard focus.
- Use motion tiers of fast (`150ms`), common (`200ms`), slow (`350ms`), and morph (`500ms`). Undertow's ambient rhythms may be longer because they communicate presence rather than response.
- Respect `prefers-reduced-motion` and preserve state meaning when animation is removed.
- Maintain WCAG 2.2 AA contrast, visible keyboard focus, semantic regions, and approximately `44px` touch targets for primary mobile controls.

## 6. Design System Notes for Stitch Generation

Generate a calm Broomva product surface on a light or deep-blue canvas. Use system typography for application UI, Blue-black ink (`oklch(0.175 0.022 265)`), cool hue-265 neutrals, and Resonant AI Blue (`oklch(0.60 0.12 260)`) only for focus, selection, information, and live signals. Keep cards and chrome matte. Reserve frosted glass for overlays, popovers, and the `28px` composer. Use `0.75rem` cards, `1rem` dialogs, the 4px spacing ladder, and the canonical work states. Show real receipts and asks instead of progress percentages.

When iterating, preserve the blackhole mark, blue-axis palette, sparse depth, state vocabulary, and Undertow/tidepool motion language. Reject generic gradient heroes, ambient glass dashboards, arbitrary radii, or decorative status color without text.
