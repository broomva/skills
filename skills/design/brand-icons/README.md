# brand-icons

Brand icon and visual identity asset generation and management for BroomVA projects. Generates favicons, app icons, Open Graph images, and social media avatars from brand assets.

## Quick Start

```bash
# Install
npx skills add broomva/skills --skill brand-icons -y -g

# Generate full icon set from source image
# Agent reads source SVG/PNG and produces multi-size favicon set, app icons, OG template

# Create OG image for a blog post
# Agent generates 1200x630 branded image with title text

# Audit a project for missing brand assets
# Agent checks for favicon, apple-touch-icon, PWA icons, OG images
```

## Modes

| Mode | Command | Output |
|------|---------|--------|
| `generate` | `generate <source-image>` | Full icon set (favicons, app icons, OG template) |
| `og-image` | `og-image <title>` | 1200x630 Open Graph image |
| `audit` | `audit <project-path>` | Missing/inconsistent asset checklist |
| `social` | `social <platform> <source>` | Platform-specific profile and banner images |

## Integration

- **arcan-glass** — brand tokens for OG image generation
- **content-creation** — auto-generate OG images for blog posts
- **seo-llmeo** — OG/Twitter meta tag asset references
- **design-engineering** — DESIGN.md visual identity alignment

## License

MIT
