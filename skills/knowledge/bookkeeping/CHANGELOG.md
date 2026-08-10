# Changelog

## [1.2.0] — 2026-08-10
- Added the typed temporal revision envelope, producer-first: `promote` stamps system-time `recorded_at`; `valid_from` is written only when a source supplies it and is never inferred from prose, page dates, or the ingest timestamp.
- Added `revise` — the explicit correction workflow that emits `supersedes` + `revision_link`; `merge` now records the same envelope on the canonical with the tombstone as its authorizing record.
- Added warning-only, `--temporal`-gated supersession validation (stamp parseability, future `recorded_at`, wikilink form, self-supersession, unresolvable targets, missing authorizing record, timeline inversion). Default `lint` output is unchanged.
- `recorded_at` is excluded from the content-identity guard, so replay stays byte-identical; legacy pages are not backfilled by the update path.
- Contract in `references/temporal-revision-envelope.md`; live-graph parity receipt in `references/temporal-revision-calibration-2026-08-10.json`. No hard gate: the new checks are uncalibrated because no entity yet carries the envelope.

## [1.1.0] — 2026-08-09
- Added opt-in `lint --temporal` warnings for stale `updated` metadata and undated mutable state in catalog-visible claims, headings, and explicit labels.
- Kept temporal findings non-blocking and default lint behavior unchanged; semantic contradiction/supersession remains outside the mechanical linter.
- Added focused boundary tests and a machine-readable clean-workspace calibration receipt over 928 entity pages.

## [1.0.0] — 2026-06-27
- Consolidated into the `broomva/skills` monorepo (BRO-1561); canonical install is now `npx skills add broomva/skills --skill bookkeeping`. The standalone `broomva/bookkeeping` repo remains functional through its deprecation window.
- bstack primitive **P6** — the universal knowledge engine. Implements the LLM Wiki pattern: raw sources → score → promote → entity graph → synthesize.
- Pipeline subcommands: `run`, `score`, `promote`, `synthesize`, `lint`, `index`, `status`, `file`, `query`, `ingest`, `bench`.
- `render` — Category-B lossless MD→HTML projection (Format Discernment / P18 · Audience).
- `replay` — frozen-snapshot scoring for shadow-dream-safe consolidation (P13 · Dream stop-gradient).
- `merge` — durable entity dedup via tombstone mechanism (BRO-1442).
- Two-tier Nous scoring gate (novelty + specificity + relevance, ≥5/9 → Layer 3); alias-indexing in the catalog (BRO-1423).
