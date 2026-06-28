# Arcan Glass — Design Tokens

## Overview

All tokens use the `--ag-` prefix to avoid collision with shadcn/ui (`--`) and Tailwind (`--tw-`). shadcn/ui compatibility is maintained via aliased `--background`, `--foreground`, etc. variables that reference `--ag-*` tokens.

---

## Shadows

Six depth levels plus brand glow effects.

| Token | Value (Dark) | Usage |
|-------|-------------|-------|
| `--ag-shadow-xs` | `0 1px 2px oklch(0 0 0 / 0.30)` | Subtle lift, badges |
| `--ag-shadow-sm` | `0 2px 4px oklch(0 0 0 / 0.35)` | Buttons, inputs |
| `--ag-shadow-md` | `0 4px 8px oklch(0 0 0 / 0.40)` | Cards, panels |
| `--ag-shadow-lg` | `0 8px 16px oklch(0 0 0 / 0.45)` | Hover elevation |
| `--ag-shadow-xl` | `0 16px 32px oklch(0 0 0 / 0.50)` | Dialogs, dropdowns |
| `--ag-shadow-2xl` | `0 24px 48px oklch(0 0 0 / 0.55)` | Modals, max depth |

### Glow Shadows

| Token | Value | Usage |
|-------|-------|-------|
| `--ag-shadow-glow-blue` | `0 0 20px oklch(0.55 0.25 260 / 0.25)` | Primary glow, focus |
| `--ag-shadow-glow-green` | `0 0 20px oklch(0.72 0.19 155 / 0.25)` | Accent glow, success |

Day Glass shadows use lower opacity (0.06-0.18), darker low-chroma violet, and a subtle inset highlight so light surfaces stay grounded without looking muddy.

---

## Blur Levels

Used for `backdrop-filter` in glass effects. Limit to 3-5 elements per viewport for performance.

| Token | Value | Usage |
|-------|-------|-------|
| `--ag-blur-sm` | `4px` | Subtle frost, inputs, overlays |
| `--ag-blur-md` | `8px` | Buttons, badges |
| `--ag-blur-lg` | `16px` | Cards, panels (default glass) |
| `--ag-blur-xl` | `24px` | Nav, modal, sidebar (heavy glass) |

---

## Typography

### Font Families

| Token | Value | Usage |
|-------|-------|-------|
| `--ag-font-heading` | `"Poppins", system-ui, -apple-system, sans-serif` | Headings h1–h6 |
| `--ag-font-body` | `-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif` | Body text, UI |
| `--ag-font-mono` | `"SF Mono", "Fira Code", "JetBrains Mono", "Menlo", monospace` | Code, data |

### Font Sizes

| Name | Value | px |
|------|-------|----|
| xs | `0.75rem` | 12 |
| sm | `0.875rem` | 14 |
| base | `1rem` | 16 |
| lg | `1.125rem` | 18 |
| xl | `1.25rem` | 20 |
| 2xl | `1.5rem` | 24 |
| 3xl | `2.25rem` | 36 |
| 4xl | `3rem` | 48 |

### Font Weights

| Name | Value | Usage |
|------|-------|-------|
| normal | 400 | Body text |
| medium | 500 | UI labels, buttons |
| semibold | 600 | Headings, emphasis |
| bold | 700 | Strong emphasis |

### Line Heights

| Name | Value | Usage |
|------|-------|-------|
| tight | 1.2 | Headings |
| snug | 1.3 | Subheadings |
| normal | 1.5 | Body (default) |
| relaxed | 1.6 | Long-form prose |

---

## Spacing

4px base unit. Maps directly to Tailwind's default spacing scale.

| Token | Value | px |
|-------|-------|----|
| `--ag-space-1` | `0.25rem` | 4 |
| `--ag-space-2` | `0.5rem` | 8 |
| `--ag-space-3` | `0.75rem` | 12 |
| `--ag-space-4` | `1rem` | 16 |
| `--ag-space-5` | `1.25rem` | 20 |
| `--ag-space-6` | `1.5rem` | 24 |
| `--ag-space-8` | `2rem` | 32 |
| `--ag-space-10` | `2.5rem` | 40 |
| `--ag-space-12` | `3rem` | 48 |
| `--ag-space-16` | `4rem` | 64 |

---

## Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--ag-radius-sm` | `4px` | Small buttons, badges |
| `--ag-radius-md` | `8px` | Inputs, buttons |
| `--ag-radius-lg` | `12px` | Cards, panels |
| `--ag-radius-xl` | `16px` | Modals, large surfaces |
| `--ag-radius-full` | `9999px` | Pills, avatars |
| `--ag-radius-glass` | `12px` | Default for all glass components |

---

## Transitions

| Token | Value | Usage |
|-------|-------|-------|
| `--ag-transition-fast` | `150ms ease` | Hovers, focus, micro-interactions |
| `--ag-transition-normal` | `250ms ease` | Cards, panels, menus |
| `--ag-transition-slow` | `350ms ease` | Page-level, sidebars |
| `--ag-transition-morph` | `500ms cubic-bezier(0.4, 0, 0.2, 1)` | Shape morphing, radius transitions |
| `--ag-transition-glow` | `1500ms ease-in-out` | Glow pulse cycles |

---

## Tailwind Mapping

All tokens are available as Tailwind utilities via `@theme inline`:

```html
<!-- Shadows -->
<div class="shadow-md shadow-glow-blue">Glowing card</div>

<!-- Radius -->
<div class="rounded-lg">12px radius</div>

<!-- Fonts -->
<h1 class="font-heading">Poppins heading</h1>
<code class="font-mono">Monospace</code>
```
