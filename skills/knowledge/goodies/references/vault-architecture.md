# Goodies — Architecture & Data Model Specification

## System Overview

Goodies is a public bookmarking and curation system for high-value resources, developer tools, design references, and research artifacts.

```
[Resource URL / Pointer]
       │
       ▼
[/goodies Skill] ──> [/checkit Deep Research] ──> [bstack KG Entity (P6)]
       │
       ▼
[Dynamic Category Resolution & Schema Validation]
       │
       ▼
[Vault Sync Engine (vault_sync.py)] ──> [data/vault.json + data/taxonomy.json]
       │
       ▼
[Git Commit & Push] ──> [GitHub Pages Static Site]
```

## Data Schema Specification (`VaultItem`)

Each vault entry is represented as a JSON object:

```json
{
  "id": "kebab-case-unique-slug",
  "url": "https://canonical-url.com",
  "title": "Resource Name",
  "category": "dynamic-category-slug",
  "subCategory": "dynamic-subcategory-slug",
  "tagline": "One-line catchy summary (max 140 chars)",
  "summary": "Multi-sentence rich description detailing why it is good and how to use it.",
  "highlights": [
    "Key feature or takeaway 1",
    "Key feature or takeaway 2"
  ],
  "tags": ["tag1", "tag2", "tag3"],
  "favicon": "https://url.to/favicon.ico",
  "ogImage": "https://url.to/og-image.png",
  "kgEntity": "research/entities/tool/resource.md",
  "qualityScore": 9.0,
  "addedAt": "2026-08-08T09:30:00Z",
  "updatedAt": "2026-08-08T09:30:00Z"
}
```

## Dynamic Taxonomy Model (`data/taxonomy.json`)

Categories are **dynamic** and evolve automatically:

```json
{
  "categories": {
    "category-slug": {
      "name": "Human Readable Category Name",
      "count": 12,
      "description": "Category domain description",
      "subCategories": ["subcat-1", "subcat-2"]
    }
  },
  "updatedAt": "2026-08-08T09:30:00Z"
}
```

When an item is processed, `vault_schema.py` checks if a matching category exists. If the item represents a novel domain (e.g. `bioinformatics-tools`), the taxonomy engine automatically registers the new category, provides a human-readable title, and updates `data/taxonomy.json`.
