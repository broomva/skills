#!/usr/bin/env python3
"""
Unit tests for vault_sync.py.
"""

import json
import pytest
from pathlib import Path
from sys import path

path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from vault_sync import sync_vault_repo


def test_sync_vault_repo(tmp_path):
    repo_dir = tmp_path / "mock-vault-repo"
    repo_dir.mkdir()
    data_dir = repo_dir / "data"
    data_dir.mkdir()

    new_item = {
        "id": "sample-tool",
        "url": "https://sampletool.dev",
        "title": "Sample Tool",
        "category": "developer-tools",
        "tagline": "Sample tagline for sample tool",
        "summary": "Sample detailed summary",
        "addedAt": "2026-08-08T09:30:00Z"
    }

    result = sync_vault_repo(repo_dir, new_item=new_item, push=False)
    assert result["status"] == "success"
    assert result["total_items"] == 1

    vault_json = data_dir / "vault.json"
    assert vault_json.exists()
    items = json.loads(vault_json.read_text())
    assert len(items) == 1
    assert items[0]["id"] == "sample-tool"

    search_index = data_dir / "search-index.json"
    assert search_index.exists()
    index_items = json.loads(search_index.read_text())
    assert len(index_items) == 1
    assert index_items[0]["title"] == "Sample Tool"
