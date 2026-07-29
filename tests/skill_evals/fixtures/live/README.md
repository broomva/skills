# Live fixtures — recorded from the real CLI, not hand-authored

These are `--record` output from actual model runs. They are what makes
*"this skill passes its evals"* a claim anything backs, and until the first of them
landed (BRO-2030) it was not one: CI replayed only the synthetic `harness-selftest`
set, which grades the harness and says nothing about any skill.

The structural difference from the synthetic fixtures is machine-checkable rather
than a matter of trust: these carry `"provenance": "live-record"`, so replaying them
needs **no** `--allow-synthetic-fixtures`. That flag is exactly what a hand-authored
fixture requires, so the absence of it in a command is the proof.

```bash
python3 scripts/skill_evals/runner.py --skill checkit \
  --replay tests/skill_evals/fixtures/live/checkit --trials 3
```

## checkit — first live run, 2026-07-29

CLI 2.1.220, model `haiku`, 17 cases × 3 trials, env-jail ON, **$3.65**.

| | |
|---|---|
| positives | **1 / 33** (0.030) |
| negatives | **16 / 18** (0.889) |
| trigger rate on positives | **16 / 33** (48%) |
| errors | 5 (3 timeouts at 300s, 2 "prompt is too long") |
| verdict | **FAIL** — the positive arm is far below the 0.80 bar |

**This is a real result, and it is not a good one.** Read it with three things in
mind before concluding anything about `checkit` itself:

1. **The model is `haiku`** (the harness default). `checkit` describes a multi-stage
   research pipeline — contextualize, verify every source, connect, document. Whether
   haiku completes that in 300 seconds is a different question from whether the
   description routes correctly, and this run conflates them.
2. **Where the failures land says which question failed.** Of 33 positive trials: 16
   triggered, 14 did not, 3 timed out. So the *description* fires about half the
   time. Of the 16 that fired, 15 then failed an outcome check — and 12 of those were
   `documents_finding` alone.
3. **`documents_finding` wants a write to a doc-shaped path** (`research/notes/…`,
   `docs/…`). The case workspace is an empty temp directory with no repo in it. A run
   that behaves perfectly may have nowhere sensible to write a finding, so this check
   may be measuring the sandbox rather than the skill.

The honest summary: **the harness works and discriminates** — negatives pass 89%
while positives fail, which is not the shape of a vacuous suite — and the first thing
it found is that our most-asserted outcome check may not be answerable inside the
sandbox we run it in. That is worth knowing before spending on four more skills.

## What this run also found in the harness

`--record` writes a fixture for a trial that ERRORED, and a timeout produces an
*empty* one. Replaying that reported a **fixture integrity failure** (exit 3,
"fixtures unusable") rather than reproducing the ERROR (exit 1) — a different claim
about a different thing, and one that would have kept live fixtures out of CI
entirely. Fixed in the same PR: an empty fixture whose meta records a non-zero exit
or a stderr replays as the failure it was; empty plus a *clean* exit is still refused
as a broken recording.

Replay now reproduces the live run exactly, including the exit code.
