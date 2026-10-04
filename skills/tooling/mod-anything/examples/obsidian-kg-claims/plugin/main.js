"use strict";
// KG Claims — an Obsidian community plugin (rung 2: the app's own plugin API).
//
// In reading view, every internal link whose target note carries a `core_claim` in its
// frontmatter gets the claim shown inline after the link, and as the link's hover title.
// The target is resolved by Obsidian's own link resolver and the claim is read from
// Obsidian's metadata cache, so the plugin never touches the file system and only ever
// reads. No build step: plain CommonJS against the `obsidian` module the app provides.

const { Plugin, getLinkpath } = require("obsidian");

const FIELD = "core_claim";
const CLS = "kg-claim";

function claimFor(app, href, sourcePath) {
  const dest = app.metadataCache.getFirstLinkpathDest(getLinkpath(href), sourcePath);
  if (!dest) return null;
  const cache = app.metadataCache.getFileCache(dest);
  const claim = cache && cache.frontmatter ? cache.frontmatter[FIELD] : null;
  if (typeof claim !== "string" || !claim.trim()) return null;
  return { claim: claim.trim(), path: dest.path };
}

module.exports = class KgClaimsPlugin extends Plugin {
  onload() {
    this.registerMarkdownPostProcessor((el, ctx) => this.decorate(el, ctx.sourcePath));
    // The metadata cache fills in after startup. A note rendered before its link targets
    // were parsed would show no claims, so re-render the open previews once it is ready,
    // and again whenever a note's frontmatter changes.
    this.registerEvent(this.app.metadataCache.on("resolved", () => this.rerender()));
    this.registerEvent(this.app.metadataCache.on("changed", () => this.rerender()));
  }

  onunload() {
    if (this.pending) window.clearTimeout(this.pending);
    this.pending = 0;
    document.querySelectorAll("." + CLS).forEach((n) => n.remove());
    document.querySelectorAll("a.internal-link[data-kg-claim]").forEach((a) => {
      a.removeAttribute("data-kg-claim");
      a.removeAttribute("title");
    });
  }

  decorate(el, sourcePath) {
    for (const a of el.querySelectorAll("a.internal-link")) {
      const next = a.nextElementSibling;
      if (next && next.classList.contains(CLS)) continue;
      const href = a.getAttribute("data-href") || a.getAttribute("href");
      if (!href) continue;
      const hit = claimFor(this.app, href, sourcePath);
      if (!hit) continue;
      a.setAttribute("title", hit.claim);
      a.setAttribute("data-kg-claim", hit.path);
      const span = document.createElement("span");
      span.className = CLS;
      span.textContent = hit.claim;
      span.setAttribute("data-kg-source", hit.path);
      a.insertAdjacentElement("afterend", span);
    }
  }

  rerender() {
    if (this.pending) return;
    this.pending = window.setTimeout(() => {
      this.pending = 0;
      for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
        const view = leaf.view;
        if (view && view.getMode && view.getMode() === "preview" && view.previewMode) {
          view.previewMode.rerender(true);
        }
      }
    }, 250);
  }
};
