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

## Deliberately excluded

- `design_handoff_maestro/` because it duplicates the canonical tokens, components, font, and logo
- `uploads/` because its four reference artifacts are unrelated to materializing the reusable system
- The archive's `SKILL.md` because a nested skill contract would be independently discovered and conflict with this skill; visual links point to the curated look spec instead

No source TODO or FIXME markers were present. The duplicate tree was confirmed by content hashes, not filenames alone.

The manifest's one duplicate card entry under `design_handoff_maestro/` was removed. All remaining manifest paths, HTML/CSS local references, and the 31-export public `index.js` are checked by `verify-source`.
`assets/system/SHA256SUMS` also pins every curated asset, so a content change or unregistered file fails the source gate until the inventory is deliberately regenerated and reviewed.

## Known source constraint

The Maestro example's `concepts.css` references `--bv-dur-med`, which is not part of the canonical token set. It is retained only in the full-profile reference app and must not be promoted into the system without deciding whether `--bv-dur-common` or a new duration token is intended.

## Font license

`assets/system/fonts/CalSans-SemiBold.ttf` is distributed under the SIL Open Font License 1.1. The required notice is adjacent at `assets/system/fonts/OFL.txt`, sourced from the official Cal Sans repository: https://github.com/calcom/sans/blob/main/OFL.txt
