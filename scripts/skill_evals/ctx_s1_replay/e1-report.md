# E1 replay: ctx System 1 gate

Snapshot `b4f8d7973941` (scope broomva, 14 days to 2026-10-01, 214 sessions split {"test": 44, "train": 128, "validation": 42}, 30478 events, 527 needed fetches). Params `candidate-b4f8d797-s1-t84`, ranker bm25, window 10 tool calls (30 for a prompt, start or compaction). Split shown: **test**. Strict precision leaves out easy hits (the event named the item, a search had just listed it, or the item was edited after the event).

| arm | stage | events | inj rate | claims | hits (easy) | precision | strict precision | recall | F0.5 | bytes/session | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gate | all | 5654 | 1.5% | 246 | 1 (1) | 0.006 | 0.000 | 0.011 | 0.006 | 1455.400 | 3.815 |
| gate | session-start | 44 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.204 |
| gate | prompt | 83 | 98.8% | 246 | 1 (1) | 0.006 | 0.000 | 0.016 | 0.007 | 1685.200 | 4.432 |
| gate | pre-edit | 401 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 1.127 |
| gate | post-read | 146 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 1.202 |
| gate | post-bash | 4750 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 2.615 |
| gate | subagent | 228 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.195 |
| gate | compact | 2 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.150 |
| always | all | 5654 | 31.2% | 3578 | 8 (6) | 0.003 | 0.001 | 0.090 | 0.003 | 20929.500 | 3.925 |
| always | session-start | 44 | 18.2% | 11 | 0 (0) | 0.000 | 0.000 | 0.000 | 0.000 | 44.900 | 0.349 |
| always | prompt | 83 | 98.8% | 246 | 1 (1) | 0.006 | 0.000 | 0.016 | 0.007 | 1680.300 | 5.386 |
| always | pre-edit | 401 | 24.4% | 185 | 0 (0) | 0.000 | 0.000 | 0.000 | 0.000 | 2225.800 | 1.113 |
| always | post-read | 146 | 24.7% | 70 | 0 (0) | 0.000 | 0.000 | 0.000 | 0.000 | 699.000 | 1.196 |
| always | post-bash | 4750 | 31.2% | 2879 | 7 (5) | 0.003 | 0.001 | 0.109 | 0.004 | 24723.400 | 2.512 |
| always | subagent | 228 | 25.9% | 177 | 0 (0) | 0.000 | 0.000 | 0.000 | 0.000 | 1904.800 | 0.313 |
| always | compact | 2 | 100.0% | 10 | 0 (0) | 0.000 | 0.000 | 0.000 | 0.000 | 1559.500 | 0.299 |
| never | all | 5654 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.055 |
| never | session-start | 44 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.055 |
| never | prompt | 83 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.056 |
| never | pre-edit | 401 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.030 |
| never | post-read | 146 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.026 |
| never | post-bash | 4750 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.055 |
| never | subagent | 228 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.056 |
| never | compact | 2 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.027 |
| wrong-key | all | 5654 | 1.5% | 248 | 0 (0) | 0.000 | 0.000 | 0.000 | 0.000 | 1541.800 | 4.138 |
| wrong-key | session-start | 44 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.279 |
| wrong-key | prompt | 83 | 100.0% | 248 | 0 (0) | 0.000 | 0.000 | 0.000 | 0.000 | 1785.300 | 9.180 |
| wrong-key | pre-edit | 401 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 1.229 |
| wrong-key | post-read | 146 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 1.258 |
| wrong-key | post-bash | 4750 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 2.942 |
| wrong-key | subagent | 228 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.230 |
| wrong-key | compact | 2 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.125 |
| stage:session-start | session-start | 44 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 0.102 |
| stage:prompt | prompt | 83 | 98.8% | 246 | 1 (1) | 0.006 | 0.000 | 0.016 | 0.007 | 1685.300 | 8.682 |
| stage:pre-edit | pre-edit | 401 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 1.092 |
| stage:post-read | post-read | 146 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 1.414 |
| stage:post-bash | post-bash | 4750 | 0.0% | 0 | 0 (0) | — | — | 0.000 | 0.000 | 0.000 | 2.491 |

Separation on the test split, strict hits: FAIL

- never_injects_nothing: ok
- gate_injects: ok
- gate_hits_strictly: FAILED
- always_injects_more: ok
- always_costs_more_bytes: ok
- always_below_gate_strict_precision: FAILED
- always_below_gate_strict_f05: FAILED
- wrong_key_below_gate_strict_f05: FAILED

| arm (test, all stages) | injections | hits (easy) | strict precision | strict recall | strict F0.5 | bytes |
|---|---|---|---|---|---|---|
| gate | 82 | 1 (1) | 0.000 | 0.000 | 0.000 | 64036 |
| always | 1765 | 8 (6) | 0.001 | 0.022 | 0.001 | 920900 |
| never | 0 | 0 (0) | — | 0.000 | 0.000 | 0 |
| wrong-key | 83 | 0 (0) | 0.000 | 0.000 | 0.000 | 67840 |

Separation fails: the gate makes 0 strict hit(s) in 82 injections on this split, so the replay cannot tell it from the mutant arms here.

The spec's bar, test split, each stage alone (strict precision >= 0.30 over >= 50 injections): no stage passes

| stage | injections | `always` injects | strict precision | bar |
|---|---|---|---|---|
| session-start | 0 | 8 | — | fail |
| prompt | 82 | 82 | 0.000 | fail |
| pre-edit | 0 | 98 | — | fail |
| post-read | 0 | 36 | — | fail |
| post-bash | 0 | 1480 | — | fail |

A stage whose injections equal `always`'s is not gated by its floor.
