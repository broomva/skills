# Changelog

All notable changes to the `liquid-midnight` skill. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions: SemVer.

## [0.1.0] - 2026-10-28

### Added
- `SKILL.md`: when the style fits, how to install, build, check and render; plus the Pencil procedure.
- `DESIGN.md`, vendored from broomva/liquid-midnight: principles, rejections, tokens, materials, recipes, motion, formats, accessibility and checklists.
- `assets/`: tokens (CSS + JSON), `materials.css`, the render kit (`kit/`), fonts (OFL), Pencil shader fills, the specimen, and a starter `templates/scene.html` (keynote, reel and feed; night and day; safe-zone guides; `renderAt(t)`).
- `scripts/materialize.mjs`: install, verify (receipt hashes, staleness) and list.
- `scripts/check_style.mjs`: a linter for the rejected looks (purple cast, arcan-glass, rimless glass, glow orbs, italic emphasis).
- `scripts/render.mjs` + `scripts/serve.mjs`: render pages to PNG at chosen t, formats and modes for visual review.
- `scripts/sync_from_repo.mjs` with `assets/manifest.json`: vendored copies are pinned to a source commit and hash-checked.
- `references/pencil.md`: safe Pencil procedure (the `filePath` trap) and the Pencil material recipes.
