# seo-llmeo

SEO and LLM Engine Optimization (LLMEO) skill for BroomVA content. Combines traditional search-engine optimization with LLM discoverability techniques.

## Quick Start

```bash
# Install
npx skills add broomva/seo-llmeo -y -g

# Audit a page for SEO + LLMEO signals
# Agent runs audit checklist and returns scored results

# Generate llms.txt for a site
# Agent analyzes site structure and produces llms.txt

# Generate meta tags for a page
# Agent reads page content and outputs optimal meta tags
```

## Modes

| Mode | Command | Output |
|------|---------|--------|
| `audit` | `audit <url-or-path>` | Scored checklist with fix suggestions |
| `llms-txt` | `llms-txt <site-root>` | Generated/updated llms.txt file |
| `meta` | `meta <url-or-path>` | Meta tags (title, description, OG, Twitter) |
| `structured-data` | `structured-data <url-or-path>` | JSON-LD structured data |

## Integration

- **content-creation** — pre-publish SEO/LLMEO validation
- **arcan-glass** — design system page meta tags
- **brand-icons** — OG image asset references
- **broomva.tech** — site-wide audit and llms.txt

## License

MIT
