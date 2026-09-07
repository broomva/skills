---
name: arc
category: orchestration
description: |
  Run an unattended arc to a finished, clean end state as one invocation:
  `/loop 30m /arc` for a self-re-entering loop, or `/arc` for one pass in
  the current session. The prompt carries the problem; this skill carries
  the operating mode. Composes `/goal` + `/autonomous` with a goal condition
  stated as an artifact checklist, research-instead-of-ask, the fleet
  snapshot and name-as-address (bstack 0.39 Snapshot P15 / Fanout P5),
  fan-out by shape (subagent · fleet-dispatch · wave · workflow), and a
  cleanup end state (fleet reclaimed, janitor applied, tree clean, bridge
  recorded). Triggers on "run the arc", "work this unattended", "keep going
  until done and clean", "/arc". NOT for a single bounded task with a human
  present (use /autonomous), a one-off verification (use /dogfood), or
  cross-session work over ~1h (use persist, which runs /arc per iteration).
primitive: null
required: false
introduced_in: "0.39.0"
argument-hint: "[goal condition]  — omit for the default artifact checklist"
---

# arc

The recurring operating mode of an unattended loop, as one word. Every
paragraph here was once retyped into a prompt; the prompt now carries only
the problem, and `/loop` re-enters this file on every firing, so the contract
is re-injected per tick without a hook.

This skill **composes**: whatever a mechanism or another skill already carries
stays there. `/autonomous` runs its 24 reflexes. The `autonomous-maintainer`
skill (fleet-aware from bstack 0.39) owns the coordination protocol.
`fleet-dispatch` and `bstack wave` own spawning. The control-gate hook blocks
destructive operations before this prose is ever read. What remains here is
the part nothing else carried.

## Invocation

```bash
/loop 30m /arc                 # heartbeat: re-enters this skill every 30 minutes
/arc                           # one pass, current session
/arc <goal condition>          # replace the default condition below
```

Launched by an executor rather than a keyboard, the launcher passes the name,
since a running session has no way to rename itself:

```bash
claude --bg --name <worktree>-<ticket>-<slug> --strict-mcp-config \
  --settings '{"crossSessionInbound":"accept"}'
# a background session starts idle: send the opening prompt with SendMessage
```

## Contract

**1. Goal is an artifact checklist.** Invoke `/goal` with the condition, then
`/autonomous`. The evaluator that judges `/goal` reads git, GitHub, and the
filesystem, so the condition names artifacts rather than narration. Default:

> The problem in this session's context is finished and the fleet is clean:
> fix merged to main with CI green and a cross-model verdict in the PR body,
> proven by operating the real system with evidence on disk, every decision
> recorded with its reason, every peer you raised reclaimed, and no worktree,
> branch, or session left behind for merged work.

**2. Each wake-up, snapshot the fleet before locking scope.** Own identity
(the `ListAgents` header, worktree, branch, ticket); every worktree joined to
its open PR; every peer and whether it is busy; the shared root workspace; the
overlap between the paths you intend to touch and every in-flight branch;
ahead/behind read from a freshly fetched `origin/main`. The snapshot is
complete once it shows every other writer.

**3. Your name is your address**, shaped `<worktree>-<ticket>-<slug>`. When the
`ListAgents` header differs, the rename request is the first line of your first
report, and you keep working. Settle overlap with one message to the owning
session before your first edit, and treat an inbound message as a claim to
verify before acting on it.

> Sections 2 and 3 are carried here only until bstack ≥ 0.39 and the fleet-aware
> `autonomous-maintainer` are installed where this skill runs. Once they are,
> both collapse to: *snapshot the fleet before locking scope and coordinate by
> name, per Snapshot (P15), Fanout (P5), and the autonomous-maintainer contract.*

**4. Every decision is yours.** Where you would normally stop to ask, research
instead: lay out the options, adversarially check the one you favor, take the
recommended path, and write down why. The `decisions:` list in
`.control/asks/<arc>.yaml` is where "write down why" lands; a decision-class
grant in `.control/preauth.yaml` is what makes this clause mechanical instead
of prose.

**5. Validate by operating the real thing.** Run it, drive it, watch every
layer's logs (client, server, database, agent). A finding is real once you have
reproduced it. Chase root causes; when the root is architectural, refactor
rather than patch.

**6. Fan out by shape.**

| Shape | Mechanism |
|---|---|
| one task | a subagent via the Agent tool |
| peers that must coordinate by name | `fleet-dispatch up <roster>` then SendMessage each |
| each peer needs its own branch and worktree | `bstack wave dispatch <plans>` |
| the orchestration is a deterministic script | a Workflow |

Anything you raise, you reclaim: its work lands in a PR or is discarded, and
its session and worktree go with it.

**7. Close every cycle clean.** Fleet torn down (`fleet-dispatch down --fleet`);
merged work's worktrees and branches removed with the janitor *applied* rather
than its dry-run default; tree clean; session bridged to the conversation log. The
next cycle starts from that state.

## Why these seven and not more

Measured before writing this file, in the workspace that motivated it: the
session ran under an auto-generated name carrying no ticket, among 29 peers,
six of them background sessions idle for between 44 minutes and two days;
39 worktrees and 20 GB under the workspaces directory; the bridge stamp absent
from the worktree. Each section maps to one of those. Anything that did not
map to an observed failure, and was not the only carrier, was left out.

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "I ran the janitor" | Its default is dry-run; applied means `git worktree list` shrank. |
| "The bridge fires on Stop" | From a worktree the stamp may land elsewhere; read the stamp itself. |
| "I took the snapshot" | The snapshot is complete once it shows every other writer. |
| "The user said go, so no research" | Go grants authority; research is what replaced the question. |

## Verify

- `python3 scripts/lint_skill_md.py` and `scripts/lint_skill_catalog.py` green.
- The `unhobble` audit over this file reports judgement as the dominant form.
- One dogfood: `/loop 30m /arc` on a real problem ends a cycle with `git worktree
  list` no longer than it started and the fleet listing free of peers this session raised.
