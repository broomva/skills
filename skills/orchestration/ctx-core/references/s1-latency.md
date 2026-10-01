# System 1 hook latency, measured

`tests/s1_latency_bench.py`: 200 invocations per stage of `/bin/sh
ctx-s1-hook.sh <stage>`, each timed from outside the process (shell,
interpreter start-up, imports, the decision, the state write, the log line,
the exit), against a cache of the real workspace (1,532 items, 31,862 keys) and
the candidate floors, on the owner's machine (macOS, Python 3.14), 2026-09-30.
CI does not run it: a p99 on a shared runner measures the runner.

At load average 9 to 10 (the machine was shared with about eight agent
sessions):

| stage | off p50 / p99 | on p50 / p99 | budget |
|---|---|---|---|
| pre-edit | 4.7 / 5.3 ms | 29.4 / 38.5 ms | 100 ms |
| post-read | 4.8 / 9.3 | 31.5 / 47.3 | 100 |
| post-bash | 4.7 / 5.5 | 27.4 / 45.2 | 100 |
| prompt | 4.2 / 10.4 | 29.7 / 58.4 | 500 |
| session-start | 4.5 / 5.3 | 27.6 / 38.3 | 500 |
| compact | 4.6 / 8.1 | 27.1 / 33.3 | 500 |
| subagent | 4.4 / 5.4 | 27.3 / 37.2 | 200 |

The floor is a bare `python3 -I -S -c pass` at 12.6 / 29.7 ms. The decision
itself, inside the interpreter, took 1 to 4 ms at p50 and at most 17 ms at p99
(the decisions log's `ms`). So most of each figure is interpreter start-up and
imports, which a shell-only path would remove only for events that abstain.

Under heavy load (load average 34 to 67, earlier the same day) the tool stages'
p99 rose to 87 to 94 ms, and post-bash to 212 ms. At that load
`/bin/sh -c 'exit 0'` alone had a p99 of 291 ms: the tail is process spawn, not
the gate. A stage that is off costs one `/bin/sh` (about 5 ms) and starts no
interpreter (a test pins that).

The tool stages' 70 ms self-deadline starts once the interpreter is up, so it
does not bound start-up, and nothing caps the wall time at 100 ms: these
figures are what was measured, under the loads stated.
Workspace#840's round-7 follow-up (the wrapper timestamps interpreter start and
re-derives the budget from it) is pending its spec text.
