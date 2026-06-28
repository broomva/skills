# Prompt Schema Reference

## Frontmatter Fields

Every prompt is an `.mdx` file in `content/prompts/` with YAML frontmatter.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Human-readable prompt name |
| `summary` | string | One-sentence description of what the prompt does |
| `date` | string (YYYY-MM-DD) | Publication or last-modified date |
| `published` | boolean | Whether the prompt is publicly visible |

### Prompt-Specific Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `category` | string | - | Taxonomic grouping (see categories.md) |
| `version` | string | "1.0" | Semver for tracking prompt evolution |
| `model` | string | - | Target model (e.g., "claude-4", "gpt-4o") |
| `variables` | array | - | Template variables the prompt expects |
| `tags` | string[] | [] | Searchable tags |
| `links` | array | [] | Related resources with `label` and `url` |

### Variable Schema

```yaml
variables:
  - name: language          # Variable name (used as {{language}} in body)
    description: "..."      # Human-readable description
    default: "typescript"   # Default value if not provided
```

## Body

The markdown body after the frontmatter `---` is the prompt itself. Use `{{variable_name}}` for template variables that get substituted at pull time.

## API Response Shape

### List endpoint (`GET /api/prompts`)

Returns `ContentSummary[]`:

```json
[
  {
    "title": "Code Review Agent",
    "summary": "...",
    "date": "2026-03-18",
    "slug": "code-review-agent",
    "kind": "prompts",
    "published": true,
    "category": "system-prompts",
    "version": "1.0",
    "model": "claude-4",
    "tags": ["code-review", "agent"],
    "variables": [{ "name": "language", "description": "...", "default": "typescript" }]
  }
]
```

Query parameters: `?category=`, `?tag=`, `?model=`, `?format=full` (includes raw content).

### Detail endpoint (`GET /api/prompts/[slug]`)

Returns `ContentDocument` (summary fields plus `content` and `html`).
