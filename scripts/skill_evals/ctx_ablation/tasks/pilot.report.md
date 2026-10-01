_memory delivery verified from tokens against bare: memory arms need 6071 unexplained turn-one tokens, others under 2500 (0 trial(s) voided)._

### Per arm

| arm | pass | 95% CI | lift vs bare (trial CI) | lift, task-clustered CI | injected tok | lift / 1k tok (trial CI) | pass / 1k tok | ctx tok (turn 1) | input tok (run) | tool calls | right source | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bare | 0/30 (0.00) | [0.00, 0.11] | — | — | 0 | n/a | n/a | 17,973 | 133,395 | 6.0 | 0.25 (n=12) | 28 |
| memory | 6/29 +1 void (0.21) | [0.10, 0.38] | +0.21 [+0.05, +0.38] | [-0.10, +0.50] | 10,361 | +0.020 [+0.00, +0.04] | 0.020 | 28,334 | 164,279 | 4.7 | 0.08 (n=12) | 18 |
| rolex | 1/30 (0.03) | [0.01, 0.17] | +0.03 [-0.08, +0.17] | [-0.04, +0.11] | 883 | +0.038 [-0.09, +0.19] | 0.038 | 18,856 | 127,655 | 6.4 | 0.17 (n=12) | 24 |
| ctx | 1/30 (0.03) | [0.01, 0.17] | +0.03 [-0.08, +0.17] | [-0.04, +0.11] | 323 | +0.103 [-0.26, +0.52] | 0.103 | 18,296 | 102,020 | 6.1 | 0.08 (n=12) | 22 |
| all | 8/30 (0.27) | [0.14, 0.44] | +0.27 [+0.10, +0.44] | [-0.00, +0.54] | 11,550 | +0.023 [+0.01, +0.04] | 0.023 | 29,523 | 165,308 | 5.5 | 0.17 (n=12) | 23 |
| rolex-top2 | 2/29 +1 void (0.07) | [0.02, 0.22] | +0.07 [-0.06, +0.22] | [-0.13, +0.33] | 760 | +0.091 [-0.07, +0.29] | 0.091 | 18,733 | 112,326 | 5.1 | 0.25 (n=12) | 19 |

### Per task (passes / graded trials)

| task | bare | memory | rolex | ctx | all | rolex-top2 |
|---|---|---|---|---|---|---|
| coord-anyone-else-before-pull | 0/3 | 0/3 | 0/3 | 1/3 | 2/3 | 0/3 |
| coord-handoff-live-originator | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-branch-first-after-main | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-p9-watch-not-sleep | 0/3 | 0/2 (1 void) | 1/3 | 0/3 | 2/3 | 2/2 (1 void) |
| reflex-paseo-list-agents-fleet | 0/3 | 3/3 | 0/3 | 0/3 | 1/3 | 0/3 |
| reflex-trash-scratch-dirs | 0/3 | 3/3 | 0/3 | 0/3 | 3/3 | 0/3 |
| retrieval-ci-runner-pool | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-higgsfield-plan-gate | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-kinetic-accept | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-workspace-sync-decision | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |

### Retrieval reflexes (share of graded trials)

| arm | read KG | read docs | read memory | web | subagent | role-x entities opened |
|---|---|---|---|---|---|---|
| bare | 0.20 | 0.30 | 0.03 | 0.03 | 0.07 | — |
| memory | 0.14 | 0.24 | 0.03 | 0.00 | 0.00 | — |
| rolex | 0.20 | 0.33 | 0.03 | 0.00 | 0.03 | 3/120 (2.5%) |
| ctx | 0.20 | 0.30 | 0.00 | 0.03 | 0.10 | — |
| all | 0.13 | 0.27 | 0.10 | 0.00 | 0.07 | 4/120 (3.3%) |
| rolex-top2 | 0.21 | 0.28 | 0.00 | 0.00 | 0.00 | 0/58 (0.0%) |
