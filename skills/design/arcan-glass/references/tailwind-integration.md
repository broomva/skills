# Arcan Glass — Tailwind v4 Integration

## @theme inline Block

All `--ag-*` tokens are mapped to Tailwind's utility namespace via `@theme inline` in `globals.css`. This means you can use them directly as Tailwind classes:

```html
<div class="bg-ai-blue text-text-primary rounded-lg shadow-md">
  Direct token usage
</div>
```

### Color Mapping

| Tailwind Class | Token |
|---------------|-------|
| `bg-ai-blue` / `text-ai-blue` | `--ag-ai-blue` |
| `bg-web3-green` / `text-web3-green` | `--ag-web3-green` |
| `bg-bg-deep` | `--ag-bg-deep` |
| `bg-bg-dark` | `--ag-bg-dark` |
| `bg-bg-surface` | `--ag-bg-surface` |
| `bg-bg-elevated` | `--ag-bg-elevated` |
| `bg-bg-hover` | `--ag-bg-hover` |
| `text-text-primary` | `--ag-text-primary` |
| `text-text-secondary` | `--ag-text-secondary` |
| `text-text-muted` | `--ag-text-muted` |
| `text-text-disabled` | `--ag-text-disabled` |

### shadcn/ui Semantic Colors

| Tailwind Class | Maps To |
|---------------|---------|
| `bg-background` | `--ag-bg-deep` |
| `bg-foreground` | `--ag-text-primary` |
| `bg-card` | `--ag-bg-surface` |
| `bg-popover` | `--ag-bg-elevated` |
| `bg-primary` | `--ag-ai-blue` |
| `bg-secondary` | `--ag-bg-hover` |
| `bg-muted` | `--ag-bg-surface` |
| `bg-accent` | `--ag-web3-green` |
| `bg-destructive` | `--ag-error` |
| `bg-sidebar` | `--ag-bg-dark` |
| `border-border` | `--ag-border-default` |
| `ring-ring` | `--ag-ai-blue` |

---

## @utility Blocks

Custom compound utilities defined in `globals.css`:

| Utility | Effect |
|---------|--------|
| `glass` | Medium glass: 60% surface tint + 16px blur + saturate(1.2) + subtle border + 12px radius |
| `glass-subtle` | Light glass: 40% tint + 8px blur + saturate(1.1) |
| `glass-heavy` | Heavy glass: 80% tint + 24px blur + saturate(1.3) |
| `glow-blue` | AI Blue glow shadow |
| `glow-green` | Web3 Green glow shadow |
| `glass-highlight` | Adds `::before` highlight pseudo-element |

**Usage:**
```html
<!-- Basic glass surface -->
<div class="glass p-6">Content</div>

<!-- Glass with highlight and glow -->
<div class="glass glass-highlight glow-blue p-6">Featured</div>

<!-- Heavy glass nav -->
<nav class="glass-heavy px-6 py-3 sticky top-0 z-50">Nav</nav>
```

---

## Dark/Light Mode Strategy

Arcan Glass uses the `.dark` / `.light` class strategy (compatible with `next-themes`):

```tsx
// layout.tsx
import { ThemeProvider } from "next-themes";

export default function Layout({ children }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark">
      {children}
    </ThemeProvider>
  );
}
```

The `@custom-variant dark` directive in `globals.css` wires `dark:` utilities to `.dark` class:

```css
@custom-variant dark (&:is(.dark *));
```

**Usage:**
```html
<div class="bg-bg-surface dark:bg-bg-surface">
  <!-- Tokens auto-adapt via CSS custom properties, so dark: prefix is rarely needed -->
</div>
```

Since all colors are defined as CSS custom properties that change with `.light` class, most elements don't need explicit `dark:` variants — the tokens handle it automatically.

---

## shadcn/ui Component Mapping

Arcan Glass tokens are designed to drop into shadcn/ui without modifications. The `globals.css` defines all required shadcn/ui variables:

| shadcn Variable | Arcan Glass Source |
|----------------|-------------------|
| `--background` | `--ag-bg-deep` |
| `--foreground` | `--ag-text-primary` |
| `--card` | `--ag-bg-surface` |
| `--card-foreground` | `--ag-text-primary` |
| `--popover` | `--ag-bg-elevated` |
| `--popover-foreground` | `--ag-text-primary` |
| `--primary` | `--ag-ai-blue` |
| `--primary-foreground` | white |
| `--secondary` | `--ag-bg-hover` |
| `--secondary-foreground` | `--ag-text-primary` |
| `--muted` | `--ag-bg-surface` |
| `--muted-foreground` | `--ag-text-muted` |
| `--accent` | `--ag-web3-green` |
| `--accent-foreground` | `--ag-bg-deep` |
| `--destructive` | `--ag-error` |
| `--border` | `--ag-border-default` |
| `--input` | `--ag-border-default` |
| `--ring` | `--ag-ai-blue` |
| `--radius` | `--ag-radius-glass` (12px) |

---

## cva Variant Extensions

To add glass variants to shadcn components using `cva`:

### Button with Glass Variant

```tsx
import { cva } from "class-variance-authority";

const buttonVariants = cva(
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-md text-sm font-medium transition-[background-color,border-color,color,box-shadow,transform] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.96] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        // Arcan Glass variants
        glass: "glass glass-highlight hover:-translate-y-px hover:shadow-lg",
        "glass-primary": "glass-button glass-button-primary",
        "glass-accent": "glass-button glass-button-accent",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-10 px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);
```

### Card with Glass Variant

```tsx
const cardVariants = cva("rounded-lg border text-card-foreground", {
  variants: {
    variant: {
      default: "bg-card shadow-sm",
      glass: "glass-card",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});
```

---

## Import Order

In your project's main CSS file:

```css
/* globals.css — just import the Arcan Glass file */
@import "tailwindcss";
@import "tw-animate-css";
/* Copy arcan-glass globals.css content here, or import from package */
```

If using Arcan Glass as the complete globals.css (recommended), simply copy it as your project's `globals.css` — it already includes the Tailwind import and all necessary configuration.
