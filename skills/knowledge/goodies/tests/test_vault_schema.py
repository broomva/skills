#!/usr/bin/env python3
"""
Unit tests for vault_schema.py & TaxonomyManager.
"""

import json
import pytest
from pathlib import Path
from sys import path

# Ensure scripts directory is on sys.path
path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from vault_schema import validate_item_json, TaxonomyManager, VaultItem


def test_vault_item_validation_success():
    valid_item = {
        "id": "test-resource",
        "url": "https://example.com",
        "title": "Test Resource",
        "category": "developer-tools",
        "tagline": "A great test resource for testing",
        "summary": "Detailed summary explaining why this test resource is valuable.",
        "addedAt": "2026-08-08T09:30:00Z"
    }
    errs = validate_item_json(valid_item)
    assert len(errs) == 0


def test_vault_item_validation_missing_fields():
    invalid_item = {
        "id": "test-resource",
        "url": "https://example.com"
    }
    errs = validate_item_json(invalid_item)
    assert len(errs) > 0


def test_taxonomy_manager_dynamic_resolution(tmp_path):
    tax_file = tmp_path / "taxonomy.json"
    mgr = TaxonomyManager(tax_file)
    
    # Resolve new category dynamically
    resolved = mgr.resolve_category("ai-agents", "AI & Autonomous Agents")
    assert resolved == "ai-agents"
    assert "ai-agents" in mgr.categories
    assert mgr.categories["ai-agents"]["name"] == "AI & Autonomous Agents"

    # Update counts
    items = [
        {"category": "ai-agents"},
        {"category": "ai-agents"},
        {"category": "design-inspiration"}
    ]
    mgr.update_counts(items)
    assert mgr.categories["ai-agents"]["count"] == 2
    assert mgr.categories["design-inspiration"]["count"] == 1

    mgr.save()
    assert tax_file.exists()
    loaded_data = json.loads(tax_file.read_text())
    assert "categories" in loaded_data
    assert loaded_data["categories"]["ai-agents"]["count"] == 2
