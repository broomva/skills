#!/usr/bin/env python3
"""
vault_ingest.py — Ingests a URL or resource pointer, extracts rich metadata, resolves dynamic taxonomy,
and outputs a VaultItem ready for public vault sync.
"""

import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

# Ensure scripts directory is on sys.path
sys.path.insert(0, str(Path(__file__).parent))
from vault_schema import TaxonomyManager, validate_item_json


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    return slug.strip('-')


def build_vault_item(
    url: str,
    title: str,
    tagline: str,
    summary: str,
    category: str,
    sub_category: str = None,
    highlights: list = None,
    tags: list = None,
    favicon: str = None,
    og_image: str = None,
    kg_entity: str = None,
    quality_score: float = 8.5
) -> Dict[str, Any]:
    """Constructs a valid VaultItem dict."""
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc or parsed.path
    if domain.startswith("www."):
        domain = domain[4:]

    item_id = slugify(title) if title else slugify(domain)
    now_iso = datetime.now(timezone.utc).isoformat()

    if not favicon:
        favicon = f"https://www.google.com/s2/favicons?domain={domain}"

    item = {
        "id": item_id,
        "url": url,
        "title": title or domain.capitalize(),
        "category": slugify(category) if category else "developer-tools",
        "subCategory": slugify(sub_category) if sub_category else None,
        "tagline": tagline[:140] if tagline else "Curated web resource.",
        "summary": summary or tagline or "High-value reference resource.",
        "highlights": highlights or [],
        "tags": tags or [slugify(category)] if category else ["resource"],
        "favicon": favicon,
        "ogImage": og_image,
        "kgEntity": kg_entity,
        "qualityScore": float(quality_score),
        "addedAt": now_iso,
        "updatedAt": now_iso
    }

    errs = validate_item_json(item)
    if errs:
        raise ValueError(f"VaultItem validation failed: {', '.join(errs)}")

    return item


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 vault_ingest.py <url> [title] [category] [tagline]")
        sys.exit(1)

    input_url = sys.argv[1]
    input_title = sys.argv[2] if len(sys.argv) > 2 else ""
    input_cat = sys.argv[3] if len(sys.argv) > 3 else "developer-tools"
    input_tagline = sys.argv[4] if len(sys.argv) > 4 else "Curated resource"

    vault_item = build_vault_item(
        url=input_url,
        title=input_title,
        tagline=input_tagline,
        summary=f"Curated reference for {input_title or input_url}.",
        category=input_cat
    )

    print(json.dumps(vault_item, indent=2))
