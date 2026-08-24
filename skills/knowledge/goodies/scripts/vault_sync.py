#!/usr/bin/env python3
"""
vault_sync.py — Merges items, updates taxonomy, generates search index, and pushes to public vault repo.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List

# Ensure scripts directory is on sys.path
sys.path.insert(0, str(Path(__file__).parent))
from vault_schema import TaxonomyManager, validate_item_json


def scaffold_repo_if_missing(repo_path: Path):
    """Scaffolds a new public goodies vault repository if it does not exist."""
    repo_path.mkdir(parents=True, exist_ok=True)
    data_dir = repo_path / "data"
    items_dir = data_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    workflows_dir = repo_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    # Scaffolding index.html if missing
    index_html = repo_path / "index.html"
    if not index_html.exists():
        index_html.write_text('''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Goodies — Curated Reference & Tooling</title>
  <meta name="description" content="A curated public vault of exceptional websites, design references, developer tools, research papers, and software resources.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="styles.css">
  <script src="https://cdn.jsdelivr.net/npm/fuse.js@6.6.2"></script>
</head>
<body>
  <div class="app-background"><div class="glow-orb orb-1"></div><div class="glow-orb orb-2"></div></div>
  <div class="layout-container">
    <header class="site-header">
      <div class="header-brand">
        <div class="brand-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
            <line x1="12" y1="22.08" x2="12" y2="12"></line>
          </svg>
        </div>
        <div>
          <h1 class="brand-title">Goodies</h1>
          <p class="brand-subtitle">Curated directory of design, tooling & research gems</p>
        </div>
      </div>
      <div class="header-actions">
        <span class="vault-stat-badge" id="stat-count">0 Items</span>
        <span class="vault-stat-badge secondary" id="stat-categories">0 Categories</span>
      </div>
    </header>
    <section class="controls-section">
      <div class="search-box">
        <svg class="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        <input type="text" id="search-input" placeholder="Search resources... (Press '/' to focus)" />
        <kbd class="search-shortcut">/</kbd>
        <button id="search-clear" class="btn-clear" hidden>✕</button>
      </div>
      <div class="taxonomy-bar" id="taxonomy-bar"></div>
    </section>
    <main class="vault-grid" id="vault-grid"></main>
    <div class="empty-state" id="empty-state" hidden>
      <div class="empty-icon">🔍</div>
      <h3>No matching goodies found</h3>
      <p>Try refining your search terms or clearing selected category filters.</p>
      <button class="btn-reset" id="btn-reset-filters">Reset Filters</button>
    </div>
    <div class="modal-backdrop" id="detail-modal" hidden>
      <div class="modal-surface">
        <button class="modal-close" id="modal-close">✕</button>
        <div class="modal-content" id="modal-content"></div>
      </div>
    </div>
    <footer class="site-footer">
      <p>Powered by <strong>bstack</strong> & <code>/goodies</code> skill · Knowledge Graph Integrated</p>
    </footer>
  </div>
  <script src="app.js"></script>
</body>
</html>\n''')

    # Scaffolding styles.css if missing
    styles_css = repo_path / "styles.css"
    if not styles_css.exists():
        styles_css.write_text('''
:root {
  --bv-ink:            oklch(0.175 0.022 265);
  --bv-white:          oklch(1 0 0);
  --bv-blue:           oklch(0.60 0.12 260);
  --bv-cyan:           oklch(0.72 0.13 220);
  --bv-glow-blue:      oklch(0.62 0.18 258);
  --bv-glow-cyan:      oklch(0.72 0.13 220);

  --background:        oklch(0.135 0.020 272);
  --foreground:        oklch(0.965 0.004 265);
  --card:              oklch(0.175 0.025 272);
  --card-hover:        oklch(0.205 0.028 272);
  --muted:             oklch(0.185 0.024 272);
  --muted-foreground:  oklch(0.65 0.020 270);
  --border:            oklch(0.62 0.05 268 / 0.14);
  --border-hover:      oklch(0.60 0.12 260 / 0.35);

  --glass-surface-heavy: oklch(0.205 0.026 272 / 0.92);
  --glass-border:        oklch(0.62 0.06 265 / 0.22);
  --glass-light-line:    oklch(1 0 0 / 0.12);

  --font-sans:     ui-sans-serif, -apple-system, system-ui, "Inter", sans-serif;
  --font-heading:  "Outfit", "Inter", var(--font-sans);
  --font-mono:     ui-monospace, "JetBrains Mono", monospace;
  --shadow-composer:   0 4px 12px oklch(0 0 0 / 0.3), 0 0 40px oklch(0.60 0.12 260 / 0.14);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
[hidden] { display: none !important; }
body { background-color: var(--background); color: var(--foreground); font-family: var(--font-sans); min-height: 100vh; }
.app-background { position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; }
.glow-orb { position: absolute; border-radius: 50%; filter: blur(140px); opacity: 0.18; }
.orb-1 { width: 600px; height: 600px; background: radial-gradient(circle, var(--bv-glow-blue), transparent 70%); top: -150px; left: -150px; }
.orb-2 { width: 700px; height: 700px; background: radial-gradient(circle, var(--bv-glow-cyan), transparent 70%); bottom: -200px; right: -200px; }
.layout-container { max-width: 1280px; margin: 0 auto; padding: 2.5rem 1.5rem; }
.site-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }
.header-brand { display: flex; align-items: center; gap: 1rem; }
.brand-icon { width: 44px; height: 44px; border-radius: 12px; background: linear-gradient(135deg, var(--bv-blue), var(--bv-cyan)); display: flex; align-items: center; justify-content: center; color: #fff; }
.brand-title { font-family: var(--font-heading); font-size: 1.85rem; font-weight: 800; }
.brand-subtitle { font-size: 0.9rem; color: var(--muted-foreground); }
.vault-stat-badge { background: oklch(0.20 0.028 272); border: 1px solid var(--border); padding: 0.35rem 0.85rem; border-radius: 8px; font-size: 0.825rem; font-weight: 600; color: var(--bv-cyan); font-family: var(--font-mono); }
.controls-section { margin-bottom: 2.25rem; display: flex; flex-direction: column; gap: 1.25rem; }
.search-box { position: relative; display: flex; align-items: center; background: var(--glass-surface-heavy); backdrop-filter: blur(20px) saturate(1.8); border: 1px solid var(--glass-border); border-radius: 14px; padding: 0.85rem 1.25rem; box-shadow: inset 0 1px 0 var(--glass-light-line), var(--shadow-composer); }
.search-icon { color: var(--muted-foreground); margin-right: 0.75rem; }
#search-input { width: 100%; background: transparent; border: none; outline: none; color: var(--foreground); font-size: 1rem; }
.taxonomy-bar { display: flex; gap: 0.6rem; overflow-x: auto; padding-bottom: 0.5rem; }
.cat-pill { display: flex; align-items: center; gap: 0.5rem; background: oklch(0.18 0.024 272); border: 1px solid var(--border); color: var(--muted-foreground); padding: 0.45rem 1rem; border-radius: 20px; font-size: 0.85rem; cursor: pointer; }
.cat-pill.active { background: linear-gradient(135deg, var(--bv-blue), oklch(0.55 0.15 280)); color: #fff; border-color: transparent; }
.vault-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 1.5rem; }
.goodie-card { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 1.5rem; cursor: pointer; transition: all 0.25s ease; }
.goodie-card:hover { transform: translateY(-4px); background: var(--card-hover); border-color: var(--border-hover); box-shadow: 0 8px 24px oklch(0 0 0 / 0.4); }
.modal-backdrop { position: fixed; inset: 0; background: oklch(0.14 0.025 270 / 0.65); backdrop-filter: blur(16px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 1.5rem; }
.modal-surface { background: var(--glass-surface-heavy); backdrop-filter: blur(28px) saturate(2.0); border: 1px solid var(--glass-border); border-radius: 20px; max-width: 720px; width: 100%; padding: 2.25rem; }
.site-footer { margin-top: 4rem; text-align: center; color: var(--muted-foreground); font-size: 0.85rem; }
''')

    # Scaffolding app.js if missing
    app_js = repo_path / "app.js"
    if not app_js.exists():
        app_js.write_text('''
document.addEventListener('DOMContentLoaded', () => {
  let vaultItems = [];
  let taxonomy = { categories: {} };
  let currentCategory = 'all';
  let searchQuery = '';
  let fuseInstance = null;
  const vaultGrid = document.getElementById('vault-grid');
  const emptyState = document.getElementById('empty-state');
  const taxonomyBar = document.getElementById('taxonomy-bar');
  const searchInput = document.getElementById('search-input');
  const statCount = document.getElementById('stat-count');
  const statCategories = document.getElementById('stat-categories');
  const detailModal = document.getElementById('detail-modal');
  const modalContent = document.getElementById('modal-content');
  const modalClose = document.getElementById('modal-close');

  async function loadVaultData() {
    try {
      const [itemsRes, taxRes] = await Promise.all([
        fetch('data/vault.json?t=' + Date.now()).catch(() => null),
        fetch('data/taxonomy.json?t=' + Date.now()).catch(() => null)
      ]);
      if (itemsRes && itemsRes.ok) vaultItems = await itemsRes.json();
      if (taxRes && taxRes.ok) taxonomy = await taxRes.json();
      initFuse();
      renderTaxonomyBar();
      renderGrid();
      updateStats();
    } catch (e) { console.warn(e); }
  }

  function initFuse() {
    if (typeof Fuse !== 'undefined') {
      fuseInstance = new Fuse(vaultItems, { keys: ['title', 'tagline', 'summary', 'category', 'tags'], threshold: 0.35 });
    }
  }

  function updateStats() {
    if (statCount) statCount.textContent = `${vaultItems.length} Items`;
    if (statCategories) statCategories.textContent = `${Object.keys(taxonomy.categories || {}).length} Categories`;
  }

  function renderTaxonomyBar() {
    const categories = taxonomy.categories || {};
    let html = `<button class="cat-pill ${currentCategory === 'all' ? 'active' : ''}" data-category="all"><span>All Items</span><span>${vaultItems.length}</span></button>`;
    Object.entries(categories).forEach(([key, info]) => {
      const count = vaultItems.filter(i => i.category === key).length;
      html += `<button class="cat-pill ${currentCategory === key ? 'active' : ''}" data-category="${key}"><span>${info.name || key}</span><span>${count}</span></button>`;
    });
    if (taxonomyBar) {
      taxonomyBar.innerHTML = html;
      taxonomyBar.querySelectorAll('.cat-pill').forEach(btn => {
        btn.addEventListener('click', () => { currentCategory = btn.dataset.category; renderTaxonomyBar(); renderGrid(); });
      });
    }
  }

  function renderGrid() {
    let items = vaultItems;
    if (currentCategory !== 'all') items = items.filter(i => i.category === currentCategory);
    if (searchQuery.trim() !== '' && fuseInstance) {
      const results = fuseInstance.search(searchQuery.trim());
      const ids = new Set(results.map(r => r.item.id));
      items = items.filter(i => ids.has(i.id));
    }
    if (items.length === 0) {
      if (vaultGrid) vaultGrid.style.display = 'none';
      if (emptyState) emptyState.hidden = false;
      return;
    }
    if (vaultGrid) {
      vaultGrid.style.display = 'grid';
      if (emptyState) emptyState.hidden = true;
      vaultGrid.innerHTML = items.map(item => `
        <article class="goodie-card" data-id="${item.id}">
          <div class="card-header">
            <h2 class="card-title">${item.title}</h2>
            <span class="card-badge">${item.category}</span>
          </div>
          <p class="card-tagline">${item.tagline || ''}</p>
          <div class="card-footer">
            <div>${(item.tags || []).map(t => `<span class="card-tag">#${t}</span>`).join(' ')}</div>
            <span>↗</span>
          </div>
        </article>
      `).join('');
      vaultGrid.querySelectorAll('.goodie-card').forEach(card => {
        card.addEventListener('click', () => {
          const item = vaultItems.find(i => i.id === card.dataset.id);
          if (item) openModal(item);
        });
      });
    }
  }

  function openModal(item) {
    if (!modalContent) return;
    modalContent.innerHTML = `
      <h2 style="font-family:var(--font-heading); font-size:1.5rem;">${item.title}</h2>
      <span class="card-badge">${item.category}</span>
      <p style="color:var(--text-muted); margin:1rem 0;">${item.tagline || ''}</p>
      <div style="background:var(--bg-surface); padding:1rem; border-radius:8px; margin-bottom:1.5rem;">
        <p>${item.summary || ''}</p>
      </div>
      <a href="${item.url}" target="_blank" style="background:var(--accent-primary); color:#fff; padding:0.5rem 1.25rem; border-radius:6px; text-decoration:none;">Visit Resource ↗</a>
    `;
    if (detailModal) detailModal.hidden = false;
  }

  if (modalClose) modalClose.addEventListener('click', () => { if (detailModal) detailModal.hidden = true; });
  if (searchInput) searchInput.addEventListener('input', (e) => { searchQuery = e.target.value; renderGrid(); });
  loadVaultData();
});
''')

    # Scaffolding deploy.yml workflow
    deploy_yml = workflows_dir / "deploy.yml"
    if not deploy_yml.exists():
        deploy_yml.write_text('''name: Deploy Goodies to GitHub Pages
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: false
jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: '.'
      - id: deployment
        uses: actions/deploy-pages@v4
''')

    # Scaffolding README.md
    readme_md = repo_path / "README.md"
    if not readme_md.exists():
        readme_md.write_text("# Goodies 💎\n\n[![GitHub Pages Deployment](https://github.com/broomva/goodies/actions/workflows/deploy.yml/badge.svg)](https://github.com/broomva/goodies/actions/workflows/deploy.yml)\n[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n\nA curated, publicly hosted vault of high-value design inspiration, developer tools, UI component libraries, research papers, and software resources.\n\n🌐 **Live Site**: [https://broomva.github.io/goodies/](https://broomva.github.io/goodies/)\n\n## ⚡ Overview\n\n**Goodies** is a static web application built with vanilla CSS glassmorphism aesthetics and Fuse.js client-side search. It acts as the public distribution channel for web resources curated and indexed by **bstack** AI agents.\n")

    # Scaffolding LICENSE
    license_file = repo_path / "LICENSE"
    if not license_file.exists():
        license_file.write_text("MIT License\n\nCopyright (c) 2026 Broomva\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the \"Software\"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.\n")

    # Scaffolding CONTRIBUTING.md
    contributing_md = repo_path / "CONTRIBUTING.md"
    if not contributing_md.exists():
        contributing_md.write_text("# Contributing to Goodies 💎\n\nThank you for your interest in contributing to **Goodies**! Submissions are managed via `/goodies add <URL>` or manual PRs.\n")

    # Scaffolding .gitignore
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".DS_Store\nThumbs.db\n.idea/\n.vscode/\nnode_modules/\n__pycache__/\n")

    # Initialize Git repository if not initialized
    if not (repo_path / ".git").exists():
        try:
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=repo_path, check=True)
        except Exception as e:
            print(f"Warning: Git init failed in {repo_path}: {e}", file=sys.stderr)


def sync_vault_repo(repo_path: Path, new_item: Dict[str, Any] = None, push: bool = False) -> Dict[str, Any]:
    """
    Syncs new or updated vault item into public repo (scaffolding automatically if missing).
    """
    if not repo_path.exists() or not (repo_path / "data").exists():
        scaffold_repo_if_missing(repo_path)

    data_dir = repo_path / "data"
    items_dir = data_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save new item if provided
    if new_item:
        errs = validate_item_json(new_item)
        if errs:
            raise ValueError(f"Invalid item data: {', '.join(errs)}")
        item_id = new_item["id"]
        item_file = items_dir / f"{item_id}.json"
        item_file.write_text(json.dumps(new_item, indent=2) + "\n")

    # 2. Gather all item files
    all_items: List[Dict[str, Any]] = []
    for item_file in items_dir.glob("*.json"):
        try:
            item_data = json.loads(item_file.read_text())
            all_items.append(item_data)
        except Exception as e:
            print(f"Warning: Failed to parse {item_file}: {e}", file=sys.stderr)

    # Sort items newest first
    all_items.sort(key=lambda x: x.get("addedAt", ""), reverse=True)

    # 3. Write consolidated vault.json
    vault_json_path = data_dir / "vault.json"
    vault_json_path.write_text(json.dumps(all_items, indent=2) + "\n")

    # 4. Update dynamic taxonomy
    taxonomy_path = data_dir / "taxonomy.json"
    tax_mgr = TaxonomyManager(taxonomy_path)
    tax_mgr.update_counts(all_items)
    tax_mgr.save()

    # 5. Build search index cache
    search_index = []
    for item in all_items:
        search_index.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "tagline": item.get("tagline"),
            "category": item.get("category"),
            "tags": item.get("tags", []),
            "url": item.get("url")
        })
    search_index_path = data_dir / "search-index.json"
    search_index_path.write_text(json.dumps(search_index, indent=2) + "\n")

    result = {
        "status": "success",
        "total_items": len(all_items),
        "categories_count": len(tax_mgr.categories),
        "items_dir": str(items_dir),
        "vault_json": str(vault_json_path)
    }

    # 6. Git commit & push if requested
    if push:
        try:
            # Sync GitHub repository metadata if gh CLI is available
            try:
                subprocess.run([
                    "gh", "repo", "edit", "--description",
                    "Curated, publicly hosted vault of high-value design inspiration, developer tools, UI components, and software resources.",
                    "--homepage", "https://broomva.github.io/goodies/",
                    "--add-topic", "curation",
                    "--add-topic", "design-inspiration",
                    "--add-topic", "developer-tools",
                    "--add-topic", "ui-components",
                    "--add-topic", "knowledge-graph",
                    "--add-topic", "bstack",
                    "--add-topic", "design-system"
                ], cwd=repo_path, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            msg = f"feat(vault): add/update item '{new_item['title'] if new_item else 'sync'}'"
            subprocess.run(["git", "commit", "-m", msg], cwd=repo_path, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=repo_path, check=True)
            result["pushed"] = True
        except Exception as e:
            result["push_error"] = str(e)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 vault_sync.py <path_to_vault_repo> [--item <item_json_path>] [--push]")
        sys.exit(1)

    repo_dir = Path(sys.argv[1])
    item_json = None
    should_push = "--push" in sys.argv

    if "--item" in sys.argv:
        idx = sys.argv.index("--item")
        if idx + 1 < len(sys.argv):
            item_path = Path(sys.argv[idx + 1])
            if item_path.exists():
                item_json = json.loads(item_path.read_text())

    res = sync_vault_repo(repo_dir, item_json, should_push)
    print(json.dumps(res, indent=2))
