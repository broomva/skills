#!/usr/bin/env python3
"""
vault_schema.py — Schema validation & dynamic taxonomy manager for goodies-vault.
"""

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Any

REQUIRED_FIELDS = ["id", "url", "title", "category", "tagline", "summary", "addedAt"]

@dataclass
class VaultItem:
    id: str
    url: str
    title: str
    category: str
    tagline: str
    summary: str
    addedAt: str
    subCategory: Optional[str] = None
    highlights: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    favicon: Optional[str] = None
    ogImage: Optional[str] = None
    kgEntity: Optional[str] = None
    qualityScore: float = 8.0
    updatedAt: Optional[str] = None

    def validate(self) -> List[str]:
        errors = []
        if not self.id or not re.match(r'^[a-z0-9-]+$', self.id):
            errors.append(f"Invalid id slug: '{self.id}' (must be kebab-case)")
        if not self.url.startswith("http://") and not self.url.startswith("https://"):
            errors.append(f"Invalid URL: '{self.url}'")
        if not self.title or len(self.title.strip()) < 2:
            errors.append("Title must be at least 2 characters long")
        if not self.category or not re.match(r'^[a-z0-9-]+$', self.category):
            errors.append(f"Invalid category slug: '{self.category}'")
        if not self.tagline:
            errors.append("Tagline is required")
        if not self.summary:
            errors.append("Summary is required")
        return errors


class TaxonomyManager:
    """Manages dynamic taxonomy categories and tag counts."""

    def __init__(self, taxonomy_path: Optional[Path] = None):
        self.taxonomy_path = taxonomy_path
        self.categories: Dict[str, Dict[str, Any]] = {}
        if taxonomy_path and taxonomy_path.exists():
            self.load()

    def load(self):
        try:
            data = json.loads(self.taxonomy_path.read_text())
            self.categories = data.get("categories", {})
        except Exception as e:
            self.categories = {}

    def resolve_category(self, cat_slug: str, cat_name: Optional[str] = None, description: Optional[str] = None) -> str:
        """Resolves existing category or dynamically creates a new one."""
        cat_slug = cat_slug.lower().strip().replace(" ", "-")
        if cat_slug not in self.categories:
            formatted_name = cat_name or cat_slug.replace("-", " ").title()
            self.categories[cat_slug] = {
                "name": formatted_name,
                "count": 0,
                "description": description or f"Curated {formatted_name} resources and references."
            }
        return cat_slug

    def update_counts(self, items: List[Dict[str, Any]]):
        counts: Dict[str, int] = {}
        for item in items:
            cat = item.get("category", "uncategorized")
            counts[cat] = counts.get(cat, 0) + 1

        for cat, count in counts.items():
            if cat not in self.categories:
                self.resolve_category(cat)
            self.categories[cat]["count"] = count

    def save(self):
        if not self.taxonomy_path:
            return
        payload = {
            "categories": self.categories,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }
        self.taxonomy_path.parent.mkdir(parents=True, exist_ok=True)
        self.taxonomy_path.write_text(json.dumps(payload, indent=2) + "\n")


def validate_item_json(item_data: Dict[str, Any]) -> List[str]:
    """Validates raw dict against VaultItem schema."""
    for req in REQUIRED_FIELDS:
        if req not in item_data or not item_data[req]:
            return [f"Missing required field: '{req}'"]
    item = VaultItem(
        id=item_data["id"],
        url=item_data["url"],
        title=item_data["title"],
        category=item_data["category"],
        tagline=item_data["tagline"],
        summary=item_data["summary"],
        addedAt=item_data["addedAt"],
        subCategory=item_data.get("subCategory"),
        highlights=item_data.get("highlights", []),
        tags=item_data.get("tags", []),
        favicon=item_data.get("favicon"),
        ogImage=item_data.get("ogImage"),
        kgEntity=item_data.get("kgEntity"),
        qualityScore=item_data.get("qualityScore", 8.0),
        updatedAt=item_data.get("updatedAt")
    )
    return item.validate()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
        if file_path.exists():
            data = json.loads(file_path.read_text())
            errs = validate_item_json(data)
            if errs:
                print(f"Validation FAILED for {file_path}:")
                for e in errs:
                    print(f"  - {e}")
                sys.exit(1)
            else:
                print(f"Validation PASSED for {file_path}")
                sys.exit(0)
    print("Usage: python3 vault_schema.py <path_to_item.json>")
