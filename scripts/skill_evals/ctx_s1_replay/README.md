# E1: the replay reports for ctx-core's System 1 gate

The offline eval of the per-stage injection gate
(`skills/orchestration/ctx-core/references/s1-gate.md`). Only aggregate
reports live here. The snapshot they were computed from is derived from the
owner's private transcripts and is kept on their machine, outside any git
checkout.

| File | What |
|---|---|
| `e1-report.json`, `e1-report.md` | every arm's counts and rates per split and stage, from the private snapshot named by its sha256, with `references/s1-params.candidate.json` |
| `e1-report-ppr.json` | the same parameters with the PPR prototype as the ranker |
| `e1-ranker-comparison.md` | BM25 against the one-hop PPR prototype, same parameters |
| `tune-ledger.jsonl` | every `ctx-s1 tune` trial (BM25 and PPR): the parameters tried, their aggregate scores, the verdict |

None of these holds a key, a hash of a key, a claim, a prompt, a path or a
per-event record.

## Where the snapshot is, and why not here

`ctx-s1 snapshot` writes `~/.local/state/ctx/<scope>/e1/snapshot.jsonl.gz`
(mode 0600) and refuses any directory inside a git checkout. Its keys are
HMAC-SHA256-hashed under a local salt (`~/.config/ctx/s1-eval-salt`), but that
is not enough to publish it: each event's keys keep their order (the live gate
cuts prompt words in that order), and Cross-Review round 2 (Stratum C) showed
an ordered sequence of hashed prompt words is a substitution cipher that
frequency analysis can read. The owner decided (2026-10-01) to keep it
private, with exact times, PR items and every repo's items, so the replay sees
the live cache's item set. The salt was rotated when the snapshot moved, and
no earlier snapshot is in this repo's history.

CI checks the harness on a synthetic fixture instead
(`skills/orchestration/ctx-core/tests/test_s1_e1_synthetic.py`): forty
generated sessions in which a working gate exists, replayed through the same
extraction, hashing, cache and arms (the masks and easy-hit classes are
pinned by `test_s1_eval.py`).

## Regenerating, on the owner's machine

```bash
S1="python3 skills/orchestration/ctx-core/scripts/ctx_s1_cli.py"
D=scripts/skill_evals/ctx_s1_replay
$S1 -C ~/broomva snapshot --days 14
$S1 -C ~/broomva tune --params default --trials 84 --seed 1 \
  --ledger $D/tune-ledger.jsonl --write <bar.json> --write-candidate <candidate.json>
$S1 -C ~/broomva tune --params default --trials 84 --seed 1 --ranker ppr \
  --ledger $D/tune-ledger.jsonl --write-candidate <candidate-ppr.json>
$S1 -C ~/broomva eval --params <candidate.json> --out $D
$S1 -C ~/broomva eval --params <candidate.json> --ranker ppr --out <dir>   # -> e1-report-ppr.json
CTX_S1_FROZEN=~/.local/state/ctx/broomva/e1 python3 -m pytest skills/orchestration/ctx-core/tests/test_s1_eval.py -k frozen
```

The last line re-derives both committed reports from the private snapshot and
fails on any difference (timings excepted, floats to 1e-9). A change to how
keys are made (tokenisation, a new channel) needs a new snapshot.
