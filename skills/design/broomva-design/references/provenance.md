# Provenance and curation

## Source

- User-provided archive: `Broomva Design System (7).zip`
- Archive SHA-256: `4723551c5f514845fcf5c172438c40b1ba999a303e702f3cbd093148262d6d26`
- Audit date: 2026-08-09
- Archive inventory: 241 files, 5,974,216 uncompressed bytes
- Text traversal: 228 UTF-8-readable files, 1,911,100 bytes, 41,345 lines, zero decode failures
- Visual traversal: every PNG and thumbnail inspected in a contact sheet

The archive's own manifest identifies namespace `BroomvaDesignSystem_5727d9`, 31 public component exports, two templates, light/dark themes, and an opt-in Cal Sans display theme.

## Curated into the skill

- Canonical modular tokens and root styles
- One-file essentials stylesheet
- Component implementations, declarations, prompt contracts, and specimen cards
- Guideline specimens
- App-shell and landing-page templates
- Desktop UI kit
- Blackhole logo
- Cal Sans SemiBold font with its official OFL 1.1 license
- Design-system and styling-essentials HTML specimens
- Manifest and Oxlint adherence profile
- Browser bundle retained for standalone HTML specimens; editable JSX remains canonical
- Original readme and look-spec references used by the visual specimens
- Maestro reference app as full-profile evidence

All 178 files in `assets/system/` remain the hash-pinned curated archive evidence. The `full` profile materializes that tree unchanged alongside the portable contract and extension references.

## Authored portability layer

`assets/portable/` is a deliberately authored adapter, not archive evidence. It separates the reusable brand foundation from the archive's agentic-work examples:

- `broomva-foundation.css` is a standalone, framework-free web expression of the product-neutral contract.
- `tokens.json` carries the same semantic roles in an OKLCH-first, machine-readable format for native and non-web adapter generation.
- `styles.css` is the neutral web entrypoint and imports only `broomva-foundation.css`; archived modular tokens stay in the agentic and evidence profiles because their comments and feature tokens encode that source product's work domain.
- `manifest.json`, `index.js`, and `index.d.ts` expose 22 general React exports across core, forms, navigation, and overlays.
- `manifest.agentic-work.json` declares the 31 exports and CSS files that the focused extension actually ships, without advertising full-profile cards or templates.
- Profile-specific component overrides remove archived agentic examples and the `Card.running` dependency from the general web adapter while leaving the archive-derived implementations byte-exact for `agentic-work` and `full`.
- `adherence.oxlintrc.json` checks public imports, token use, and general component enums without referencing work components.
- `SHA256SUMS` pins every portability-layer asset independently from the archive-derived inventory.

The materializer owns the boundary: `foundation` is platform-neutral guidance plus a standalone web stylesheet, `web` adds general React primitives, `agentic-work` adds the domain extension, and `full` preserves all source evidence. `essentials` and `tokens` retain their original archive-era path layouts for existing automation; new products should not use those compatibility profiles as neutrality boundaries.

Profile changes are closed-world for owned paths. Verification rejects artifacts left by another Broomva profile, and the explicit `--prune` flag removes only known managed paths. Modified managed files require the separate `--force` authorization.

## Deliberately excluded

- `design_handoff_maestro/` because it duplicates the canonical tokens, components, font, and logo
- `uploads/` because its four reference artifacts are unrelated to materializing the reusable system
- The archive's `SKILL.md` because a nested skill contract would be independently discovered and conflict with this skill; visual links point to the curated look spec instead

No source TODO or FIXME markers were present. The duplicate tree was confirmed by content hashes, not filenames alone.

The manifest's one duplicate card entry under `design_handoff_maestro/` was removed. All remaining manifest paths, HTML/CSS local references, the 22-export general entry point, and the 31-export full entry point are checked by `verify-source`.
`assets/system/SHA256SUMS` and `assets/portable/SHA256SUMS` pin their respective assets, so a content change or unregistered file fails the source gate until the inventory is deliberately regenerated and reviewed.

## Known source constraint

The Maestro example's `concepts.css` references `--bv-dur-med`, which is not part of the canonical token set. It is retained only in the full-profile reference app and must not be promoted into the system without deciding whether `--bv-dur-common` or a new duration token is intended.

## Font license

`assets/system/fonts/CalSans-SemiBold.ttf` is distributed under the SIL Open Font License 1.1. The required notice is adjacent at `assets/system/fonts/OFL.txt`, sourced from the official Cal Sans repository: https://github.com/calcom/sans/blob/main/OFL.txt
