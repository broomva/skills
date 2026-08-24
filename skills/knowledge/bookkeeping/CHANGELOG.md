# Changelog

## [1.3.0] — 2026-08-10
- Added `backfill-revisions`: replays supersessions the graph already recorded (merge tombstones) into the typed envelope, stamping `recorded_at` with the HISTORICAL `merged_at` rather than the migration date. Idempotent; refuses to invent a date; never derives supersessions from `aliases:` (those are `aka` search synonyms) or from prose.
- `_apply_revision_envelope` accepts an explicit `recorded_at`; the unchanged predicate distinguishes a SUPPLIED stamp from a defaulted one, so ordinary replay stays byte-identical across days.
- Calibrated the supersession audit on the corpus that migration produces: zero envelope findings on every migrated page, 13/13 audit branches reachable. Positive controls are now permanent tests, each matched on its own message — zero findings on a clean corpus is otherwise indistinguishable from a checker that never fires, and asserting only the field is vacuous when several branches share one.
- **Decision: no hard gate.** 10 of 13 checks are DEFINITIONAL (the predicate *is* the property, so asking its false-positive rate asks whether `x == x`); only 3 are proxies with a gap a rate could measure, and the corpus measures none of them; and 5 pages could not bound a rate anyway. The 1 genuine heuristic is unmeasurable on real data (tombstones carry no `recorded_at`), and 5 of 943 pages carrying the envelope is too little to gate on. Receipt: `references/supersession-calibration-2026-08-10.json`.

## [1.2.1] — 2026-08-10
- `revise`/`merge` now write `updated` QUOTED. Emitting it bare un-quoted a page that already had `updated: "YYYY-MM-DD"`, so the repo's own unquoted-date lint warned on every page the command touched — the writer failing the gate it is supposed to satisfy. Found by dogfooding the merged CLI, not by the suite.
- `valid_from` is written after `recorded_at` exists, so its `after=` anchor resolves instead of silently landing at the end of the frontmatter.

## [1.2.0] — 2026-08-10
- Added the typed temporal revision envelope, producer-first: `promote` stamps system-time `recorded_at`; `valid_from` is written only when a source supplies it and is never inferred from prose, page dates, or the ingest timestamp.
- Added `revise` — the explicit correction workflow that emits `supersedes` + `revision_link`; `merge` now records the same envelope on the canonical with the tombstone as its authorizing record.
- Added warning-only, `--temporal`-gated supersession validation (stamp parseability, future `recorded_at`, wikilink form, self-supersession, unresolvable targets, missing authorizing record, timeline inversion). Default `lint` output is unchanged.
- `recorded_at` is excluded from the content-identity guard, so replay stays byte-identical; legacy pages are not backfilled by the update path.
- `revision_link` is a LIST (one entry per authorizing record); both correction workflows REFUSE rather than repair a malformed or duplicated envelope, and `merge` aborts instead of half-merging.
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
