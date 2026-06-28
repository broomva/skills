# Arcan Glass — Glass Components

## The 4-Layer Glass Effect System

Every glass component in Arcan Glass is built from four composable layers:

### Layer 1: Backdrop Blur
The foundation — frosted glass effect via `backdrop-filter`.
```css
backdrop-filter: blur(var(--ag-blur-lg)) saturate(1.2);
-webkit-backdrop-filter: blur(var(--ag-blur-lg)) saturate(1.2);
background: color-mix(in oklab, var(--ag-bg-surface) 60%, transparent);
```
The `color-mix(in oklab)` tint provides natural blending regardless of what's behind the element. `saturate(1.2)` enriches the backdrop content visible through the blur.

### Layer 2: Highlight
A `::before` pseudo-element creating a subtle top-edge light reflection.
```css
&::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(
    180deg,
    oklch(1 0 0 / 0.05) 0%,
    oklch(1 0 0 / 0.02) 20%,
    transparent 50%
  );
  pointer-events: none;
}
```
In light mode, increase to 0.08–0.12 opacity for visible sheen. In dark mode, keep subtle at 0.03–0.06.

### Layer 3: Shadow
Multi-level box-shadow providing depth. Glass components use `--ag-shadow-md` by default, elevating to `--ag-shadow-lg` on hover. Primary/accent variants add glow shadows.

### Layer 4: Adaptive Tint
Using `color-mix()` to blend the surface color with brand colors for contextual tinting:
```css
/* Blue-tinted glass */
background: color-mix(in oklab, var(--ag-ai-blue) 15%, var(--ag-bg-surface) 50%, transparent);

/* Green-tinted glass */
background: color-mix(in oklab, var(--ag-web3-green) 15%, var(--ag-bg-surface) 50%, transparent);
```

---

## Components

### Glass Card

The primary container. Medium glass with highlight, shadow, and hover lift.

**CSS class:** `.glass-card`

**Raw CSS:**
```css
.glass-card {
  position: relative;
  background: color-mix(in oklab, var(--ag-bg-surface) 60%, transparent);
  backdrop-filter: blur(16px) saturate(1.2);
  border: 1px solid var(--ag-border-subtle);
  border-radius: 12px;
  box-shadow: var(--ag-shadow-md);
  padding: 1.5rem;
  transition: transform 250ms ease, box-shadow 250ms ease;
}
.glass-card::before { /* highlight layer */ }
.glass-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--ag-shadow-lg);
}
```

**Tailwind composition:**
```html
<div class="glass glass-highlight p-6 shadow-md transition-[box-shadow,transform] hover:-translate-y-0.5 hover:shadow-lg">
  <h3 class="font-heading text-lg text-text-primary">Card Title</h3>
  <p class="text-text-secondary mt-2">Card content</p>
</div>
```

**Or use the class directly:**
```html
<div class="glass-card">
  <h3>Card Title</h3>
  <p>Card content</p>
</div>
```

---

### Glass Nav

Fixed navigation bar with heavy glass and bottom border.

**CSS class:** `.glass-nav`

**Tailwind composition:**
```html
<nav class="glass-heavy sticky top-0 z-50 border-b border-border px-6 py-3">
  <div class="flex items-center justify-between">
    <span class="font-heading text-lg text-ai-blue">BroomVA</span>
    <div class="flex gap-4">
      <a class="text-text-secondary hover:text-text-primary transition-colors" href="#">Home</a>
      <a class="text-text-secondary hover:text-text-primary transition-colors" href="#">About</a>
    </div>
  </div>
</nav>
```

**Or use the class:**
```html
<nav class="glass-nav sticky top-0 z-50 px-6 py-3">
  <!-- nav content -->
</nav>
```

---

### Glass Button

Three variants: default (ghost glass), primary (AI Blue fill), accent (Web3 Green fill).

**CSS classes:** `.glass-button`, `.glass-button .glass-button-primary`, `.glass-button .glass-button-accent`

**Usage:**
```html
<!-- Default (ghost glass) -->
<button class="glass-button">Settings</button>

<!-- Primary (AI Blue) -->
<button class="glass-button glass-button-primary">Get Started</button>

<!-- Accent (Web3 Green) -->
<button class="glass-button glass-button-accent">Connected</button>
```

**Tailwind composition (primary example):**
```html
<button class="inline-flex items-center gap-2 bg-ai-blue/85 backdrop-blur-sm border border-ai-blue/50
               rounded-md px-4 py-2 text-sm font-medium text-white
               min-h-10 transition-[background-color,box-shadow,transform]
               hover:bg-ai-blue/95 hover:shadow-glow-blue hover:-translate-y-px active:scale-[0.96]">
  Get Started
</button>
```

---

### Glass Input

Subtle glass with focus ring expansion.

**CSS class:** `.glass-input`

**Usage:**
```html
<input type="text" class="glass-input w-full" placeholder="Search...">
```

**Tailwind composition:**
```html
<input type="text"
       class="glass-subtle px-3 py-2 rounded-md text-sm text-text-primary placeholder:text-text-muted
              transition-[border-color,box-shadow]
              focus:outline-none focus:border-ai-blue focus:ring-2 focus:ring-ai-blue/15"
       placeholder="Search...">
```

---

### Glass Modal

Heavy glass with reveal animation and overlay backdrop.

**CSS classes:** `.glass-modal`, `.glass-modal-overlay`

**Usage:**
```html
<!-- Overlay -->
<div class="glass-modal-overlay" aria-hidden="true"></div>

<!-- Modal -->
<div class="glass-modal max-w-lg mx-auto">
  <h2 class="font-heading text-xl text-text-primary">Modal Title</h2>
  <p class="text-text-secondary mt-3">Modal content here.</p>
  <div class="flex gap-3 mt-6 justify-end">
    <button class="glass-button">Cancel</button>
    <button class="glass-button glass-button-primary">Confirm</button>
  </div>
</div>
```

---

### Glass Sidebar

Full-height sidebar with heavy glass and right border.

**CSS class:** `.glass-sidebar`

**Usage:**
```html
<aside class="glass-sidebar w-64 p-4">
  <nav class="flex flex-col gap-1">
    <a class="rounded-md px-3 py-2 text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors" href="#">
      Dashboard
    </a>
    <a class="rounded-md px-3 py-2 text-sm bg-bg-hover text-text-primary" href="#">
      Projects
    </a>
  </nav>
</aside>
```

---

### Glass Badge

Pill-shaped badge with subtle glass. Optional brand color variants.

**CSS classes:** `.glass-badge`, `.glass-badge .glass-badge-blue`, `.glass-badge .glass-badge-green`

**Usage:**
```html
<span class="glass-badge">Default</span>
<span class="glass-badge glass-badge-blue">AI</span>
<span class="glass-badge glass-badge-green">Web3</span>
```

---

## Performance Guidelines

1. **Limit `backdrop-filter` to 3-5 elements per viewport** — each blurred element forces a compositing layer
2. **Use `will-change: backdrop-filter` sparingly** — only on elements that will animate
3. **Prefer `.glass-subtle` for repeated items** (list items, table rows) — lower blur = less GPU cost
4. **Use `.glass-heavy` only for landmark surfaces** — nav, sidebar, modal
5. **Test on low-end devices** — `backdrop-filter` performance varies significantly across GPUs
