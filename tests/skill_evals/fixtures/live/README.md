# Live fixtures — recorded from the real CLI, not hand-authored

These are `--record` output from actual model runs. They are what makes *"this skill
passes its evals"* a claim anything backs, and until they landed (BRO-2030) it was not
one: CI replayed only the synthetic `harness-selftest` set, which grades the harness
and says nothing about any skill.

The difference from the synthetic fixtures is machine-checkable rather than a matter
of trust: these carry `"provenance": "live-record"`, so replaying them needs **no**
`--allow-synthetic-fixtures`. That flag is exactly what a hand-authored fixture
requires, so its absence from a command is the proof.

```bash
python3 scripts/skill_evals/runner.py --skill handoff \
  --replay tests/skill_evals/fixtures/live/handoff --trials 3

python3 scripts/skill_evals/live_summary.py /tmp/live-evals   # the table below
```

## The first full sweep — 2026-07-29

CLI 2.1.220, model `haiku`, 3 trials per case, env-jail ON. 216 trials, **$16.37**.

| skill | trigger rate | positives | negatives | errors | delivered |
|---|---|---|---|---|---|
| `handoff` | **30/33 (91%)** | 21/33 | 18/18 | 0 | FULL |
| `checkit` | 16/33 (48%) | 1/33 | 16/18 | 5 | FULL |
| `skillify` | 11/30 (37%) | 1/30 | 24/24 | 1 | FULL |
| `kg` | 9/27 (33%) | 9/27 | 21/21 | 0 | TRUNCATED |
| `dogfood` | 7/33 (21%) | 5/33 | 18/18 | 2 | TRUNCATED |
| `autonomous` | 3/30 (10%) | 3/30 | 18/18 | 0 | FULL |
| `p9` | **0/30 (0%)** | 0/30 | 18/18 | 0 | FULL |

**Six of seven descriptions do not route.** Only `handoff` reliably fires on prompts
that describe its job without naming it.

**The suite discriminates**, which is what makes the above readable at all: negatives
are near-perfect everywhere (135 of 136 across the sweep). A suite that failed
everything would prove nothing; this one fails positives while passing negatives.

### Delivery is necessary but not sufficient

BRO-2014 established that most skills never receive a description. This sweep shows
that receiving one is not enough:

- `p9` arrives **FULL** and fires **0%**.
- `handoff` arrives **FULL** and fires **91%**.

So there are two independent failure modes, and a coverage number that ignores either
is misleading. A skill can be invisible (BARE), or visible and still unroutable.

### The sharpest single result

`autonomous` is the most-invoked skill in the corpus — **73 real invocations** — and
its description fires on **1 of 10** golden cases. It works because people type
`/autonomous`. The description does almost no routing.

The one case that fires is about CI/PR mechanics ("keep an eye on the checks, answer
whatever the reviewer left, land it once the gates are green"). The ones that do not
are about carrying implementation to completion ("pick it up and run it the whole
way: the retry wrapper, a test that proves it stops at the cap, the readme line").

Its description is dense in merge/CI vocabulary — *merge autonomously, automerge, all
green, address PR comments* — and thin in the *run it the rest of the way* framing
that is most of what it is actually used for. That is a specific, testable edit.

### `documents_finding` is the dominant outcome failure, and it is partly the sandbox

31 of the 45 check failures across the sweep are `documents_finding`, and for
`handoff` it is **all nine**. Reading a transcript rather than assuming: the agent
fired the skill correctly and then asked for the inputs it lacked — *"I need a few
quick details: 1. Repo name 2. Current branch 3. Merge SHAs"*. The case workspace is
an empty temp directory, so a skill whose deliverable is repo-relative genuinely has
nothing to work from.

The check is not wrong — no artifact was produced. The **workspace** is the confound.
Two honest options, neither taken here: seed the case workspace with a realistic repo,
or put the context in the prompt. Note also that the withdrawn
`no_clarifying_question_bounced_back` check would have named this exactly.

### Errors are reported, not hidden

8 of 216 trials produced no signal — 5 timeouts at 300s (all `checkit`, its cases are
the heaviest) and 3 "prompt is too long". They are excluded from the pass rates by
`graded_trials`, not silently counted as failures.

## What this sweep found in the harness itself

`--record` writes a fixture for a trial that ERRORED, and a timeout produces an
*empty* one. Replaying that reported a **fixture integrity failure** (exit 3,
"fixtures unusable") rather than reproducing the ERROR (exit 1) — a different claim
about a different thing, and one that would have kept live fixtures out of CI
entirely. Fixed in the same PR: an empty fixture whose meta records a non-zero exit or
a stderr replays as the failure it was; empty plus a *clean* exit is still refused as
a broken recording. Replay now reproduces each live run exactly, including exit codes.
