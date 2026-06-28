# Changelog — colombia-conflict

## 0.1.0 — 2026-06-28

Initial release. Distilled (via `/skillify`, BRO-1578) from the Colombian Truth
Commission final report *Hay Futuro Si Hay Verdad* (2022), after downloading and
fan-out-digesting all 24 PDFs (~8,900 pp / ~3.67M words).

- **Substrate** — 12 per-volume sourced digests + master synthesis + lexicon in
  `references/`.
- **Data** — `statistics.json`, `actors.json`, `recommendations.json` (67 recs /
  8 blocks), `concepts.json`.
- **Engine** — `scripts/cc.py`: two-tier kg `load`, `rec`/`stat`/`actor`/`concept`
  queries, the `align` non-repetition scorer, and the `index` catalog generator.
- **Tests** — `tests/test_cc.py`: 17 unit + data-integrity tests (stdlib, no network).
- **Architecture** — kg / LLM-wiki (LLM-as-index): substrate + catalog projection
  + body-grep fallback + agent-as-query-engine.
