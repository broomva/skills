# Arcan Glass — Animation Patterns

All animations are wrapped in `@media (prefers-reduced-motion: no-preference)` guards. When reduced motion is preferred, all durations collapse to near-zero and transforms are disabled.

---

## Glow Pulse

Blue glow oscillation for active/loading states. Uses AI Blue at varying opacity.

```css
@keyframes glow-pulse {
  0%, 100% {
    box-shadow: 0 0 16px oklch(0.55 0.25 260 / 0.20);
  }
  50% {
    box-shadow: 0 0 28px oklch(0.55 0.25 260 / 0.40);
  }
}
```

**Tailwind:** `animate-glow-pulse`

**Usage:**
```html
<!-- Loading indicator -->
<div class="glass-card animate-glow-pulse">Processing...</div>

<!-- Active state -->
<button class="glass-button glass-button-primary animate-glow-pulse">Live</button>
```

**Green variant** (custom): Replace hue 260 with 155 for web3-green glow.

---

## Hover Lift

Subtle upward translation with shadow elevation and optional highlight brightening.

```css
.hover-lift {
  transition: transform var(--ag-transition-normal),
              box-shadow var(--ag-transition-normal);
}
.hover-lift:hover {
  transform: translateY(-2px);
  box-shadow: var(--ag-shadow-lg);
}
```

**Tailwind composition:**
```html
<div class="transition-[box-shadow,transform] duration-250 ease-out hover:-translate-y-0.5 hover:shadow-lg">
  Hover me
</div>
```

Already built into `.glass-card` and `.glass-button`.

---

## Glass Reveal

Entry animation for glass surfaces — opacity, blur, and position animate together.

```css
@keyframes glass-reveal {
  from {
    opacity: 0;
    backdrop-filter: blur(0px);
    transform: translateY(8px) scale(0.98);
  }
  to {
    opacity: 1;
    backdrop-filter: blur(var(--ag-blur-lg));
    transform: translateY(0) scale(1);
  }
}
```

**Tailwind:** `animate-glass-reveal`

**Usage:**
```html
<!-- Modal entrance -->
<div class="glass-modal animate-glass-reveal">...</div>

<!-- Card stagger (combine with delay utilities) -->
<div class="glass-card animate-glass-reveal" style="animation-delay: 0ms">Card 1</div>
<div class="glass-card animate-glass-reveal" style="animation-delay: 100ms">Card 2</div>
<div class="glass-card animate-glass-reveal" style="animation-delay: 200ms">Card 3</div>
```

---

## Morph

Border-radius transition with smooth cubic-bezier for shape-shifting effects.

```css
.morph {
  transition: border-radius var(--ag-transition-morph);
}
.morph:hover {
  border-radius: var(--ag-radius-xl);
}
```

**Tailwind composition:**
```html
<div class="rounded-lg transition-[border-radius] duration-500 ease-[cubic-bezier(0.4,0,0.2,1)] hover:rounded-xl">
  Morphing shape
</div>
```

---

## Focus Ring

Expanding ring with blue glow fade-in for accessible focus indication.

```css
@keyframes focus-ring-expand {
  from {
    box-shadow: 0 0 0 0 oklch(0.55 0.25 260 / 0.40);
  }
  to {
    box-shadow: 0 0 0 4px oklch(0.55 0.25 260 / 0.15);
  }
}

.focus-ring:focus-visible {
  animation: focus-ring-expand 200ms ease forwards;
}
```

**Usage:**
```html
<button class="glass-button focus-ring">Accessible button</button>
```

The default `:focus-visible` style in globals.css provides a solid 2px outline. Use `focus-ring` class for the animated variant.

---

## Gradient Flow

Slowly rotating brand gradient for hero sections and feature backgrounds.

```css
@keyframes gradient-flow {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
```

**Tailwind:** `animate-gradient-flow`

**Usage:**
```html
<section class="bg-gradient-to-r from-ai-blue via-web3-green to-ai-blue bg-[length:200%_200%] animate-gradient-flow">
  <h1 class="text-4xl font-heading text-white">Hero Section</h1>
</section>
```

---

## Scroll Reveal

Uses `animation-timeline: view()` for scroll-triggered glass reveal. Falls back to Intersection Observer for unsupported browsers.

**CSS (progressive enhancement):**
```css
@supports (animation-timeline: view()) {
  .scroll-reveal {
    animation: glass-reveal linear both;
    animation-timeline: view();
    animation-range: entry 0% entry 100%;
  }
}
```

**JavaScript fallback:**
```js
if (!CSS.supports("animation-timeline", "view()")) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("animate-glass-reveal");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll(".scroll-reveal").forEach((el) => observer.observe(el));
}
```

---

## Transition Tokens

| Token | Duration | Easing | Use Case |
|-------|----------|--------|----------|
| `--ag-transition-fast` | 150ms | ease | Hover, focus, micro |
| `--ag-transition-normal` | 250ms | ease | Card, menu, panel |
| `--ag-transition-slow` | 350ms | ease | Sidebar, page |
| `--ag-transition-morph` | 500ms | cubic-bezier(0.4, 0, 0.2, 1) | Shape, radius |
| `--ag-transition-glow` | 1500ms | ease-in-out | Glow cycles |

---

## Reduced Motion

All animations respect `prefers-reduced-motion`:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

This is already included in `globals.css`. No additional action needed — just use the animation classes normally.
