# Formal model of p9's P20 verdict gate

`P9Lifecycle.tla` models `_p20_verdict()` in `../scripts/p9.py`: a PASS verdict
names a commit, and it carries forward to a later head only if no later commit
touches a reviewed file or a current PR file.

**Property (`SafeMerge`), stated over content, not over the rule:** whatever
merges is what the reviewer read. Every authored PR file holds the reviewed
content, and every generated PR file is generator output of the merged content.

## Run

    bash check.sh      # exit 0 iff every configuration produced its expected outcome

TLA+ tools v1.7.4 are pinned by sha256 and cached in `~/.cache/tlaplus/`; Java 11+
is required. A run takes about five seconds.

## What each configuration shows

| Config | Gate | Expected |
|---|---|---|
| `p9.cfg` | as implemented | `SafeMerge` holds, and a PR never merges after a base update without a new review |
| `exempt.cfg` | + changes to generated files do not void a verdict, with a CI check that they equal regeneration | `SafeMerge` holds |
| `exempt_probe.cfg` | same | a merge after a base update is reachable (the exemption does its job) |
| `exempt_unchecked.cfg` | exemption without the CI check | counterexample: a hand-edited generated file merges unreviewed |
| `anypass.cfg` | any PASS on the PR clears it | counterexample |
| `reviewedonly.cfg` | only reviewed files void it | counterexample: a file added after review merges unreviewed |

A broken variant that stops producing a counterexample fails the run, so the
model cannot silently lose its ability to fail.

**Reading a counterexample:** TLC prints states in order; follow `hist` (what
each commit changed), `verdict.reviewed` (what the reviewer read) and `pr`. For
`reviewedonly.cfg` the story is: change `a`, review, add `b`, merge with `b` unread.

## Kept in step with the code

`sync.json` records the sha256 of `_p20_verdict`'s source and the commit at which
the model was last confirmed against it. `check.sh` fails when the function
changes. Then re-read the function, update the model if the rule changed, and only
then move `sha256` and `confirmed_at` forward.

## Scope

The model abstracts files to three (`a`, `b`, a generated `idx`) and runs at most
four commits. It covers the verdict-binding rule only: not marker parsing, author
trust, score thresholds or GitHub's merge state, which have their own tests.
