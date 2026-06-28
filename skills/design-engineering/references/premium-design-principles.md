# Premium Design Principles

Guidelines for producing distinctive, high-end UI designs that are immediately distinguishable from generic AI-generated output.

## The Premium Design Checklist

Every design must pass these checks before it ships:

### Atmospheric Coherence
- [ ] Consistent hue undertone across ALL neutral surfaces (never pure gray)
- [ ] Shared material metaphor throughout (glass, paper, stone — pick one)
- [ ] Unified shadow direction and depth scale
- [ ] Color palette follows dominant + accent hierarchy (not evenly distributed)

### Material Quality
- [ ] Surfaces feel like something physical (glass, metal, fabric, wood)
- [ ] Maximum 3-5 glass/blur surfaces per viewport (glass is earned, not default)
- [ ] Each glass surface uses the composable 4-layer system: backdrop blur + highlight + shadow + tint
- [ ] Light simulation via top-edge gradient highlights

### Typography Distinction
- [ ] Custom font pairing (NOT Inter, Roboto, Arial, system-ui defaults)
- [ ] Explicit weight hierarchy visible in the design (display vs body vs label)
- [ ] Appropriate letter-spacing for each tier (tighter for display, normal for body, wide for badges)
- [ ] `text-rendering: optimizeLegibility` and antialiased smoothing

### Color Precision
- [ ] All colors defined in perceptually uniform color space (OKLCH preferred)
- [ ] Maximum 2-3 saturated brand colors + 4 semantic states
- [ ] Wide-gamut P3 enhancement for brand colors where supported
- [ ] Hex fallbacks via `@supports not (color: oklch())`
- [ ] Descriptive names for every color (not "blue-500")

### Interaction Choreography
- [ ] Tiered animation timing creates rhythm (not everything at 200ms)
- [ ] Hover effects are subtle and purposeful (lift, glow, border shift)
- [ ] Entry animations use staggered reveals (50-100ms per element)
- [ ] Ambient effects reserved for loading/attention states
- [ ] `prefers-reduced-motion` collapses ALL animation

### Detail Precision
- [ ] Shadow opacities are intentional (0.30-0.55 dark mode, 0.05-0.18 light mode)
- [ ] Border opacities vary by purpose (subtle 0.40, default 0.50, strong 0.60)
- [ ] Radius scale is consistent and purposeful (sm/md/lg/xl/full)
- [ ] Scrollbar styling maintains the design aesthetic

## Anti-Patterns: What Makes Design Look Generic AI

| Anti-Pattern | Why It's Bad | Fix |
|---|---|---|
| Purple gradients on white backgrounds | Cliched "AI aesthetic" that screams generated | Commit to one atmospheric hue; dark-first with subtle undertone |
| Inter/Roboto/Arial as body font | Default system fonts = zero design effort | Distinctive pair: CalSans + Geist, or similar confident pairing |
| 3-column identical card grid | Most common AI layout pattern | Vary card treatment, use asymmetry, break the grid with hero sections |
| Even color distribution | Every color equally prominent = no hierarchy | Dominant background + 1-2 accent colors used sparingly |
| Stock team photos | "Diverse people smiling in office" = instant generic | AI-generated contextual imagery, abstract patterns, or no images |
| Identical component treatment | Every button same size, every card same shadow | Vary emphasis via glass tiers, shadow depth, size, border weight |
| Stacked effects (gradient + shadow + blur + border) | Maximalism without purpose = visual noise | One primary effect per surface; composable layers, not additive |
| Pure gray backgrounds and text | Lifeless, institutional, no personality | Always tint neutrals with your brand hue (e.g., 275-hue blue-purple) |
| Missing hover/focus/active states | Static mockup ≠ interactive design | Every interactive element needs at least hover + focus + active |
| Placeholder content | "Lorem ipsum" or "Your Text Here" | Realistic, plausible content appropriate to the domain |

## Material Metaphor System

Choose ONE primary material and use it consistently:

### Glass (Arcan Glass)
- Translucent backgrounds via `color-mix(in oklab, surface opacity%, transparent)`
- `backdrop-filter: blur() saturate()` for frosted effect
- Top-edge gradient highlight for light simulation
- Three tiers: subtle (40%/8px), medium (60%/16px), heavy (80%/24px)

### Paper/Editorial
- Flat surfaces with subtle shadows
- High contrast between surface layers
- Heavy reliance on typography hierarchy for depth
- Minimal decoration, maximum content density

### Metal/Industrial
- Hard edges, sharp corners
- High-contrast borders
- Monochromatic with single accent
- Heavy shadows, minimal blur

### Organic/Natural
- Generous border radius
- Warm color temperature
- Soft shadows with color tinting
- Flowing transitions, breathing animations

## Color Theory for Agents

### The 60-30-10 Rule
- **60%** dominant color (backgrounds, surfaces) — should be your darkest/lightest neutral
- **30%** secondary color (cards, containers, elevated surfaces) — slightly lighter/darker neutral
- **10%** accent color (CTAs, links, highlights) — your saturated brand color(s)

### Perceptual Uniformity (OKLCH)

OKLCH ensures that colors with the same lightness value LOOK equally light, regardless of hue. This prevents the common problem where "red at 50% lightness looks darker than yellow at 50% lightness."

```
oklch(L C H)
  L = Lightness (0 = black, 1 = white) — perceptually uniform
  C = Chroma (0 = gray, ~0.4 = maximum saturation)
  H = Hue (0-360 degrees)
```

### Wide-Gamut Enhancement

```css
/* Standard sRGB */
--brand-blue: oklch(0.55 0.25 260);

/* Enhanced for P3 displays */
@media (color-gamut: p3) {
  --brand-blue: oklch(0.55 0.28 260); /* higher chroma */
}
```

## Typography Hierarchy

### The Professional Stack

| Tier | Font Type | Weight | Size Range | Letter-Spacing |
|------|-----------|--------|------------|----------------|
| Display | Display/heading face | SemiBold (600) | 2.5-4rem | -0.02em (tight) |
| Section | Display/heading face | SemiBold (600) | 1.5-2rem | -0.01em |
| Body | Body/reading face | Regular (400) | 0.875-1rem | Normal |
| UI Labels | Body/reading face | Medium (500) | 0.875rem | Normal |
| Micro/Badges | Body/reading face | Medium (500) | 0.625rem | 0.2em (wide) |
| Mono/Code | Monospace face | Regular (400) | 0.875rem | Normal |

### Font Pairing Rules
- **Contrast**: Heading and body fonts should be visually distinct
- **Complement**: They should share similar x-height and proportions
- **Character**: The heading font carries personality; the body font carries readability
- **Consistency**: Same body font for all non-heading text (labels, buttons, inputs, meta)

## Animation Design Language

### Purpose Categories

| Purpose | Duration | Example |
|---------|----------|---------|
| **Feedback** | 100-200ms | Button press, checkbox toggle |
| **Transition** | 200-400ms | Card hover lift, panel slide |
| **Reveal** | 300-500ms | Content entrance, modal open |
| **Transform** | 400-600ms | Shape morph, layout shift |
| **Ambient** | 1000-2000ms | Loading glow, breathing pulse |

### The One-Effect Rule
Each surface gets ONE primary effect:
- A card either glows OR lifts OR scales — not all three
- A button either shifts color OR grows — not both
- A nav either blurs OR slides — not both

Exception: composable glass layers (blur + highlight + shadow + tint) are designed as a single cohesive system, not independent effects.

## Responsive Design Strategy

### Breakpoint Philosophy
- **Mobile-first** CSS with `min-width` queries
- But **desktop-first design** — start with the full layout, then simplify for mobile
- Design at: 375px (mobile), 768px (tablet), 1440px (desktop)

### Responsive Decisions
- Navigation: inline → hamburger below 768px
- Grid: 3-column → 2-column → 1-column
- Typography: scale down 15-20% on mobile
- Spacing: reduce by one step on mobile (section margins, card padding)
- Glass: reduce blur intensity on mobile for performance
- Animation: simpler on mobile, respect `prefers-reduced-motion`
