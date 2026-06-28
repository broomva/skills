# DESIGN.md Specification

The DESIGN.md format was introduced by Google for Stitch as an **agent-friendly markdown file** that captures a project's design system in a format readable by both humans and AI agents.

## Role in the File Ecosystem

| File | Purpose | Standard |
|------|---------|---------|
| `README.md` | How to use the project (humans) | Universal |
| `CLAUDE.md` | How to work with the codebase (Claude Code) | Anthropic |
| `AGENTS.md` | Universal agent instructions | Linux Foundation-backed |
| `DESIGN.md` | How the project should look (design agents) | Google Stitch |

## Required Structure

```markdown
# Design System: [Project Title]
**Project ID:** [Insert Project ID Here]

## 1. Visual Theme & Atmosphere
(Evocative mood descriptors, density, aesthetic philosophy, key characteristics)

## 2. Color Palette & Roles
(Each color: Descriptive Name + value + functional role)

## 3. Typography Rules
(Font families, weight/size hierarchy, rendering, spacing)

## 4. Component Stylings
* **Buttons:** shape, color, behavior, states
* **Cards/Containers:** corners, background, shadow, padding
* **Navigation:** layout, typography, states, mobile
* **Inputs/Forms:** stroke, background, focus, placeholder

## 5. Layout Principles
(Spacing system, grid, whitespace, responsive, animation)

## 6. Design System Notes for Stitch Generation (optional)
(Prompt templates, color reference format, iteration guidance)
```

## Writing Rules

### DO

- Use **evocative, designer-friendly language**: "Ocean-deep Cerulean (#0077B6)" not "blue"
- Always explain **what each element is used for** (functional purpose)
- Include **exact values in parentheses** after natural language descriptions
- Translate CSS values into physical descriptions:
  - `rounded-full` → "Pill-shaped"
  - `rounded-lg` → "Generously rounded corners"
  - `rounded-none` → "Sharp, squared-off edges"
  - `shadow-sm` → "Whisper-soft diffused shadow"
  - `shadow-xl` → "Heavy, high-contrast drop shadow"
- Maintain **consistent terminology** throughout

### DON'T

- Use generic terms like "blue" or "rounded" without qualification
- Use unexplained CSS class names ("rounded-xl" without "generously rounded corners")
- Rely solely on descriptive names without precise values, or vice versa
- Omit functional explanations for design components
- Use vague atmospheric descriptions without specificity

## Color Entry Format

Every color entry must have three components:

```
- **Descriptive Name** (`color-value` / `hex-fallback`) — Functional role explaining where and when this color is used
```

Example:
```
- **Resonant AI Blue** (`oklch(0.55 0.25 260)` / `#0066ff`) — Primary brand color. Used exclusively for primary CTAs, active navigation links, focus rings, and interactive element accents
```

## Color Organization

Group colors by functional role:

1. **Primary Foundation** — Background surfaces, depth layers
2. **Accent & Interactive** — Brand colors, CTAs, interactive states
3. **Typography & Text Hierarchy** — Primary, secondary, muted, disabled text
4. **Functional States** — Success, warning, error, info
5. **Borders** — Subtle, default, strong, focus
6. **Charts & Data Visualization** — 5-color sequential palette

## Typography Entry Format

```
| Role | Font | Weight | Line Height | Notes |
|------|------|--------|-------------|-------|
| Display Headlines | [Name] | [Weight] | [Value] | [Context] |
```

Include:
- Font families with full fallback chains
- Weight names AND numeric values
- Line height for each tier
- Letter-spacing where non-default

## Component Entry Format

For each component type:

1. **Shape** — corner radius in descriptive terms + exact value
2. **Surface** — background treatment (solid, glass, gradient) with opacity/blur values
3. **Border** — style, color, width
4. **Default state** — complete visual description
5. **Hover state** — what changes and by how much
6. **Focus state** — focus ring specification
7. **Disabled state** — opacity, pointer-events
8. **Transition** — duration + easing

## Generation Pipeline

When creating DESIGN.md from an existing project, follow five stages:

1. **Retrieval** — Read the project's CSS (globals.css, theme files) and component code
2. **Extraction** — Identify design tokens: colors, typography, spacing, borders, shadows, radii, animations
3. **Translation** — Convert every CSS/Tailwind value into natural design language with values in parens
4. **Synthesis** — Organize into the five-section format with consistent terminology
5. **Alignment** — Verify all sections are complete, no raw CSS leaked, all values have descriptive names

## Portability

DESIGN.md is portable because:
- Written in plain Markdown — no tool-specific syntax
- Any agent (Claude Code, Cursor, Gemini CLI, Codex) can read and apply it
- Can be generated from Stitch projects, Figma files, existing code, or hand-written
- Bridges visual design tools and code-generation agents
- Version-controllable alongside code in Git
