# Design System: Broomva
**Project ID:** broomva-blue-axis

## 1. Visual Theme & Atmosphere

Broomva is a product-neutral visual identity for digital products. It can support transactional applications, content and media, commerce, analytics, communication, internal tools, and emerging interfaces without changing its character. The system feels precise, quiet, and observant: white or deep-blue canvases, Blue-black ink, fine borders, matte working surfaces, and a scarce current of blue light.

The hierarchy comes from spacing, typography, and tonal contrast rather than decoration. Depth is rare and meaningful. Glass marks a surface that actually floats above the current context. Glow marks deliberate emphasis, never generic excitement. A product may be sparse or information-dense, expressive or operational, as long as the blue-axis palette, quiet geometry, and semantic restraint remain intact.

Core characteristics:

- **Blue-axis monochrome:** apparent blacks and grays carry a subtle hue near `265`.
- **Matte by default:** cards, sidebars, panels, navigation, and content regions do not use glass.
- **Earned elevation:** frost and broad shadows belong to dialogs, popovers, command surfaces, and rare focal controls.
- **Functional color:** blue communicates interaction and information; green, amber, and red communicate outcomes, warnings, and errors.
- **Quiet geometry:** compact controls, a 4px spacing ladder, moderate card radii, and deliberate negative space.
- **Domain independence:** product concepts determine composition and copy; they do not redefine the visual foundation.

## 2. Color Palette & Roles

### Primary foundation

- **Blue-black ink** (`oklch(0.175 0.022 265)`) — Primary light-theme text, solid buttons, and the deepest product mark. It reads as black until inspected closely.
- **Paper white** (`oklch(1 0 0)`) — Light-theme page and card surface. Use pure white as a surface, never as dark-theme body text.
- **Cool soft canvas** (`oklch(0.966 0.003 265)`) — Sidebars, quiet secondary surfaces, and low-emphasis grouping.
- **Deep current canvas** (`oklch(0.135 0.020 272)`) — Dark-theme page background; a blue-purple near-black, never neutral black.
- **Soft ice foreground** (`oklch(0.965 0.004 265)`) — Primary text and high-emphasis icons on dark surfaces.

### Accent and interaction

- **Resonant AI Blue** (`oklch(0.60 0.12 260)`) — Focus rings, links, selection, information, and the primary brand accent. Keep it scarce enough to retain meaning.
- **Tidepool Cyan** (`oklch(0.65 0.14 235)`) — Optional secondary accent only when two distinct interactive or informational accents must coexist.
- **Frosted selection** (`oklch(0.60 0.12 260 / 0.09)`) — Selected rows and hover states when a blue relationship helps orientation.
- **Visible focus** (`var(--bv-blue)`) — A `2px` focus ring with at least `2px` separation. Never remove it without an equivalent.

### Text hierarchy

- **Primary ink** (`oklch(0.175 0.022 265)`) — Titles, body text, and primary actions on light surfaces.
- **Slate body** (`oklch(0.38 0.020 265)`) — Long-form secondary copy with comfortable contrast.
- **Muted current** (`oklch(0.50 0.015 265)`) — Metadata and supporting labels, not essential instructions.
- **Placeholder mist** (`oklch(0.68 0.010 265)`) — Placeholder text and deliberately low-emphasis content.

### Functional states

- **Resolved green** (`oklch(0.62 0.17 152)`) — Success, availability, and completed outcomes.
- **Informational blue** (`oklch(0.60 0.12 260)`) — Information, selection, and active context.
- **Attention amber** (`oklch(0.76 0.15 85)`) — Warnings and recoverable conditions.
- **Intervention red** (`oklch(0.56 0.21 27)`) — Errors, destructive actions, and urgent intervention.

Every functional color requires a text label, icon, or structural cue. Color alone never communicates meaning. OKLCH values are canonical; do not introduce raw hex aliases into implementation code.

### Borders and depth

- **Whisper edge** (`oklch(0.25 0.04 265 / 0.07)`) — Default dividers and card boundaries.
- **Visible edge** (`oklch(0.25 0.04 265 / 0.16)`) — Inputs and secondary buttons.
- **Emphasis edge** (`oklch(0.25 0.04 265 / 0.26)`) — Rare emphasized boundaries.
- **Feature bloom** (`0 4px 80px 8px oklch(0.55 0.12 260 / 0.08)`) — A rare broad light bloom for one focal control or elevated feature, never ambient decoration.

## 3. Typography Rules

Application UI uses system fonts deliberately. Cal Sans is a display accent, not the default interface typeface.

| Role | Font | Weight | Line height | Notes |
|---|---|---:|---:|---|
| Screen title | `ui-sans-serif, -apple-system, system-ui, "Segoe UI", Helvetica, Arial, sans-serif` | Regular (400) | Tight (1.25) | `28px`, `-0.01em`; direct, sentence-case title |
| Section title | System sans stack | Medium (500) | Tight (1.25) | `22px` or `24px`, `-0.01em`; avoid oversized application headings |
| Empty-state title | System sans stack | Semibold (600) | Tight (1.25) | `24px`; the only semibold product heading tier |
| Body and reading | System sans stack | Regular (400) | Normal (1.5) | `16px`; default reading tier and mobile input minimum |
| Controls and navigation | System sans stack | Medium (500) | Normal (1.5) | `14px`; buttons, tabs, filters, and navigation rows |
| Metadata | System sans stack | Regular (400) | Normal (1.5) | `12px`; timestamps, prices, codes, and supporting labels |
| Marketing display | `"CalSans", ui-sans-serif, system-ui, sans-serif` | Semibold (600) | Tight (1.25) | Opt in with `[data-display-font="calsans"]`; use for heroes, not app chrome |
| Data and identifiers | `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace` | Regular (400) | Normal (1.5) | Compact machine-readable values, code, and tabular identifiers |

Use the fixed scale `12 / 14 / 16 / 18 / 22 / 24 / 28px`. Use sentence case everywhere. Product copy is plain, precise, and action-oriented. Do not use emoji, em dashes, title case, or decorative eyebrow labels.

## 4. Component Stylings

### Buttons and icon controls

- **Shape:** Compact pill-shaped action buttons (`9999px`) with `36px` default and `44px` large heights. Icon buttons use moderately rounded corners (`0.5rem`), not circles by default.
- **Surface:** Primary buttons use Blue-black ink; secondary and soft buttons use cool matte surfaces; ghost buttons remain transparent.
- **States:** Hover changes tone, not geometry. Focus uses Resonant AI Blue. Disabled controls retain their label and reduce contrast without becoming invisible.
- **Transition:** Fast (`150ms`) with standard easing (`cubic-bezier(0.25, 0.1, 0.25, 1)`). Never use `transition: all`.

### Cards, content, and data containers

- **Shape:** Use `0.75rem` for ordinary cards and `1rem` for large cards or dialogs. Never make every container pill-shaped.
- **Surface:** Use matte Paper white or the dark card surface with a Whisper edge. Cards do not use glass.
- **Hierarchy:** Prefer whitespace, type, and alignment before nested borders. Dense tables may reduce vertical spacing, but must preserve readable row focus and selection.
- **Interaction:** Hover may add a soft blue-tinted shadow without moving the card. Entire-card links require a visible title and a predictable focus target.

### Navigation

- **Composition:** Navigation may be a sidebar, header, tab bar, rail, breadcrumb, or native platform pattern. Preserve the product's information architecture instead of forcing one shell.
- **Typography:** Use medium `14px` sentence-case labels. Icons support recognition but do not replace primary labels.
- **Selection:** Use Frosted selection and clear foreground contrast. The current location must remain identifiable without color alone.
- **Responsive behavior:** Move, collapse, or recompose navigation according to platform conventions while keeping essential destinations discoverable.

### Inputs and forms

- **Shape:** Use `0.375rem` with a visible `1px` edge. A product may assign the `28px` feature radius to one genuinely focal input or command control, but ordinary fields remain compact.
- **Surface:** Inputs are matte. A floating command surface may use heavy glass because it occupies a separate elevation layer.
- **States:** Placeholder Mist is subordinate; focus uses Resonant AI Blue; errors pair Intervention red with specific text. Mobile inputs remain at least `16px`.
- **Accessibility:** Every field has a persistent accessible label, errors are programmatically associated, and controls are operable by keyboard or the platform's equivalent input method.

### Overlays and feedback

- **Surface:** Dialogs and command palettes may use heavy frosted glass (`32px` blur, saturation `2.0`); menus, tooltips, and popovers use lighter frost (`22px` blur, saturation `1.8`).
- **Shape:** Popovers use `0.75rem`; dialogs use `1rem`.
- **Depth:** A blue-black scrim separates a modal overlay from the page. Background text must not remain legible through the frost.
- **Behavior:** Modal focus is contained, Escape closes when safe, focus returns to the trigger, and status feedback remains available to assistive technology.

### Product-specific compositions

Compose the foundation around the product's actual objects: products and carts, articles and collections, accounts and permissions, charts and filters, messages and media, bookings and schedules, or any other domain model. Use semantic copy and platform conventions. Domain extensions may add components and motion, but must not change the foundation's palette, type scale, spacing ladder, elevation rules, or accessibility contract.

## 5. Layout Principles

- Use a `4px` base ladder: `4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48px`. New spacing values require a system-level reason.
- Choose content width by task: approximately `640–768px` for sustained reading, wider canvases for comparison and data, and edge-to-edge media only when the content benefits.
- Establish hierarchy with whitespace and alignment before borders, shadows, or color.
- Design from the smallest relevant viewport, then verify at representative mobile, tablet, and desktop sizes. No horizontal overflow is acceptable.
- Keep primary actions near the content they affect. Persistent controls must not obscure content or keyboard focus.
- Use motion tiers of fast (`150ms`), common (`200ms`), slow (`350ms`), and morph (`500ms`). Motion explains state or spatial change; it does not decorate inactivity.
- Respect `prefers-reduced-motion` and preserve meaning when animation is removed.
- Maintain WCAG 2.2 AA contrast, visible keyboard focus, semantic regions, and approximately `44px` touch targets for primary mobile controls.
- Adapt safely to native mobile, desktop, embedded, and constrained surfaces by translating semantic roles rather than copying CSS values blindly.

## 6. Design System Notes for Stitch Generation

Generate a calm Broomva interface for the named product and platform. Start from a light or deep-blue canvas, system typography for application UI, Blue-black ink (`oklch(0.175 0.022 265)`), cool hue-265 neutrals, and Resonant AI Blue (`oklch(0.60 0.12 260)`) only for focus, selection, information, and rare brand emphasis. Keep cards and chrome matte. Reserve frosted glass for surfaces that actually float. Use `0.75rem` cards, `1rem` dialogs, compact controls, and the 4px spacing ladder.

Infer the information architecture and component composition from the product domain. Preserve the blackhole mark, blue-axis palette, sparse depth, semantic color roles, and accessible interaction states. Reject generic gradient heroes, ambient glass dashboards, arbitrary radii, decorative status color without text, and any domain-specific extension that leaks into unrelated products.
