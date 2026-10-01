# E1: BM25 against the PPR prototype

Both rankers replay the same private snapshot `b4f8d7973941` (scope broomva, 14 days to 2026-10-01, 214 sessions, 527 needed fetches) with the same parameters, BM25's tune proposal (`candidate-b4f8d797-s1-t84`), so the ranker is the only difference. PPR is the one-hop personalized-PageRank prototype in `ctx_s2_ppr.py`, an eval arm only. Each ranker was also tuned on its own from `--params default` (84 trials, seed 1, strict F0.5, at least two strict train hits to accept): BM25 accepted 1 of 76 trials (floor prompt None -> 0.5), PPR 1 of 84 (floor post-bash None -> 15); neither change clears the bar on test (`tune-ledger.jsonl`). Cells: injections · hits (easy) · strict precision · strict recall · strict F0.5.

## Validation split

| arm | stage | BM25 | PPR |
|---|---|---|---|
| gate | all | 96 · 4 (3) · 0.006 · 0.013 · 0.007 | 96 · 3 (2) · 0.010 · 0.013 · 0.010 |
| stage:prompt | prompt | 96 · 4 (3) · 0.006 · 0.017 · 0.007 | 96 · 3 (2) · 0.010 · 0.017 · 0.011 |
| always | all | 1329 · 12 (9) · 0.001 · 0.038 · 0.002 | 1377 · 10 (6) · 0.002 · 0.051 · 0.003 |
| wrong-key | all | 96 · 0 (0) · 0.000 · 0.000 · 0.000 | 96 · 0 (0) · 0.000 · 0.000 · 0.000 |

## Test split

| arm | stage | BM25 | PPR |
|---|---|---|---|
| gate | all | 82 · 1 (1) · 0.000 · 0.000 · 0.000 | 82 · 0 (0) · 0.000 · 0.000 · 0.000 |
| stage:prompt | prompt | 82 · 1 (1) · 0.000 · 0.000 · 0.000 | 82 · 0 (0) · 0.000 · 0.000 · 0.000 |
| always | all | 1765 · 8 (6) · 0.001 · 0.022 · 0.001 | 1886 · 9 (6) · 0.001 · 0.034 · 0.001 |
| wrong-key | all | 83 · 0 (0) · 0.000 · 0.000 · 0.000 | 83 · 0 (0) · 0.000 · 0.000 · 0.000 |

## Reading

Neither ranker clears the spec's bar (strict precision >= 0.30 over >= 50 injections on test, stage alone) at any stage, and neither gate makes a strict hit on test (BM25 0, PPR 0), so on this snapshot the two cannot be told apart. BM25 stays the default; PPR stays an eval arm. Regenerate with `ctx-s1 eval --ranker ppr` on the same snapshot (`ctx-s1 build` alone refuses the PPR ranker unless CTX_S2_ALLOW_EVAL_RANKER=1).
