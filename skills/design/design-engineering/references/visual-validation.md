# Visual Validation Workflow

Screenshot-driven visual validation ensures agent-generated designs maintain quality, consistency, and correctness at every stage.

## Core Principle

> Generate → Screenshot → Evaluate → Iterate

Never proceed to the next design step without validating the current one visually.

## Validation Stages

### Stage 1: Structure Validation

After creating the frame hierarchy and layout:

1. **`snapshot_layout()`** (Pencil) — verify computed layout rectangles
   - Check: no overlapping elements
   - Check: no elements clipped by parent bounds
   - Check: spacing between elements matches design tokens
   - Use `problemsOnly: true` for quick audit

2. **`get_screenshot(nodeId)`** (Pencil) — visual confirmation
   - Check: layout structure matches intent
   - Check: proper alignment and visual hierarchy

### Stage 2: Content Validation

After adding text, images, and component content:

1. **Screenshot** — verify content renders correctly
   - Check: text is readable and properly sized
   - Check: images have correct aspect ratio and fill
   - Check: component hierarchy is clear

2. **Token audit** — verify design system compliance
   ```
   search_all_unique_properties(parentIds, ["fillColor", "textColor", "fontSize", "fontFamily"])
   ```
   - Check: no raw hex values that should be variable references
   - Check: font families match DESIGN.md specification
   - Check: font sizes follow the hierarchy

### Stage 3: Styling Validation

After applying colors, effects, and glass treatments:

1. **Screenshot** — verify visual quality
   - Check: glass effects render correctly (blur, transparency, highlight)
   - Check: color palette matches DESIGN.md
   - Check: shadow depth creates proper elevation hierarchy
   - Check: borders are consistent weight and opacity

2. **Contrast check** — verify accessibility
   - Check: all text/background combinations meet 4.5:1 (normal) or 3:1 (large)
   - Check: UI components meet 3:1 against backgrounds

### Stage 4: Interaction State Validation

After defining hover, focus, active, and disabled states:

1. **Screenshot each state** — verify all states are distinct
   - Check: hover state is noticeably different from default
   - Check: focus indicator is clearly visible (2px outline, 2px offset)
   - Check: disabled state shows reduced opacity

### Stage 5: Responsive Validation

Test at standard breakpoints:

| Breakpoint | Width | Check |
|------------|-------|-------|
| Mobile | 375px | Touch targets ≥ 24px, readable text, single column |
| Tablet | 768px | Proper column collapse, navigation adaptation |
| Desktop | 1440px | Full layout, proper spacing, max-width containers |

### Stage 6: Dark/Light Mode Validation

1. **Screenshot in both modes** — verify theme switching
   - Check: all text remains readable in both modes
   - Check: glass opacity adjusts correctly (dark: 0.40-0.80, light: 0.60-0.90)
   - Check: shadows adjust appropriately (lighter in light mode)
   - Check: brand colors remain unchanged across modes

## Design Token Audit Workflow

### Find Leaked Raw Values

```
search_all_unique_properties(parentIds, [
  "fillColor",
  "textColor",
  "strokeColor",
  "fontSize",
  "fontFamily",
  "fontWeight",
  "cornerRadius",
  "padding",
  "gap"
])
```

Review results for:
- Colors not matching DESIGN.md palette → should be tokenized
- Font families not matching spec → should use variable references
- Inconsistent spacing values → should use base unit multiples
- Inconsistent corner radius → should match design token scale

### Tokenize Raw Values

```
replace_all_matching_properties(parentIds, {
  fillColor: { from: "#0066ff", to: "$color.aiBlue" },
  textColor: { from: "#ffffff", to: "$color.textPrimary" },
  fontSize: { from: 14, to: "$size.bodySmall" }
})
```

### Verify Token Coverage

```
get_variables()
```

Ensure all used values have corresponding variable definitions.

## Cross-Tool Validation

### Code → Visual Comparison

When implementing designs in code:

1. Render the component in browser
2. Screenshot the rendered output
3. Compare side-by-side with Pencil/Figma screenshot
4. Verify: colors match, spacing matches, typography matches, effects match

### Figma → Code Fidelity

When implementing from Figma designs:

1. `get_design_context(figmaUrl)` — extract structured layout
2. `get_screenshot(figmaUrl)` — capture design reference
3. Implement in code
4. Screenshot the implementation
5. Compare and iterate until pixel-accurate

## Automated Checks

### Layout Inspection Flags

When using `snapshot_layout()`, flag these problems:

| Problem | Severity | Action |
|---------|----------|--------|
| Element extends beyond parent bounds | High | Fix overflow or increase parent size |
| Elements overlap unintentionally | High | Adjust spacing or z-index |
| Inconsistent spacing between siblings | Medium | Normalize gap values |
| Element too small for touch (< 24px) | High | Increase size to meet WCAG |
| Text truncated | Medium | Increase container or reduce font size |

### Color Audit Flags

| Problem | Severity | Action |
|---------|----------|--------|
| Text contrast < 4.5:1 | High | Adjust text or background lightness |
| UI component contrast < 3:1 | High | Increase border/icon contrast |
| Raw hex not in DESIGN.md palette | Medium | Tokenize or add to palette |
| Pure gray (#808080 etc.) without hue | Low | Add brand hue undertone |

### Typography Audit Flags

| Problem | Severity | Action |
|---------|----------|--------|
| Font not in DESIGN.md spec | High | Replace with specified font |
| Font size not in hierarchy | Medium | Snap to nearest tier |
| Missing weight hierarchy | Medium | Apply proper weight per tier |
| Line height < 1.5 for body | Medium | Increase line height |

## Validation Frequency

| Event | Validation Required |
|-------|-------------------|
| After creating frame structure | Layout + screenshot |
| After adding content | Screenshot + token audit |
| After styling | Screenshot + contrast check |
| After adding interaction states | Screenshot of each state |
| After responsive adjustments | Screenshot at each breakpoint |
| After dark/light mode implementation | Screenshot in both modes |
| Before handoff/export | Full audit (all stages) |
| After code implementation | Cross-tool comparison |
