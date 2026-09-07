---
name: arc
category: orchestration
description: |
  Run an unattended arc to a finished, clean end state as one invocation:
  `/loop 30m /arc` for a self-re-entering loop, or `/arc` for one pass in
  the current session. The prompt carries the problem; this skill carries
  the operating mode. Composes `/goal` + `/autonomous` with one goal
  condition stated as an artifact checklist, research-in-place-of-asking
  for decisions, the fleet snapshot and name-as-address (the fleet-aware
  Snapshot (P15) and Fanout (P5) of bstack 0.39.0), fan-out gated on the
  ability to reclaim, and a cleanup end state (peers reclaimed, janitor
  applied, tree clean, bridge recorded). Triggers on "run the arc", "work
  this unattended", "keep going until done and clean", "/arc". NOT for a
  single bounded task with a human present (use /autonomous) or a one-off
  verification (use /dogfood). Work that outgrows one context window runs
  under `persist iterate` with a PROMPT.md whose first line is `/arc`.
primitive: null
required: false
introduced_in: "0.39.0"
argument-hint: "[goal condition]  — omit for the default artifact checklist"
---

# arc

The recurring operating mode of an unattended loop, as one word. Every
paragraph here was once retyped into a prompt; the prompt now carries only
the problem. `/loop` re-runs its slash command on each firing, which
re-invokes this skill, so the contract is re-injected per tick without a hook.

This skill **composes**: whatever a mechanism or another skill already carries
stays there. `/autonomous` runs its 24 reflexes. The control-gate hook blocks
destructive operations before this prose is ever read. The fleet protocol is
defined by bstack 0.39.0's Snapshot (P15) and Fanout (P5) and implemented as
§Locate yourself in the fleet of the `autonomous-maintainer` skill in the
GetStimulus/sri repository (STI-2669), the SRI-side counterpart of that
release; the copy of that skill installed here predates it, so sections 2 and
3 below carry the protocol. What remains here is the part nothing else carried.

## Invocation

```bash
/loop 30m /arc                 # heartbeat: re-runs this skill every 30 minutes
/arc                           # one pass, current session
/arc <goal condition>          # replace the default condition below
```

A session launched by an executor rather than a keyboard is named by the
executor, since a running session has no way to rename itself. This block is
the launcher's, describing how *this* session is started; it is not a way for
the session to raise peers (see section 6):

```bash
claude --bg --name <worktree>-<ticket>-<slug> --strict-mcp-config \
  --settings '{"crossSessionInbound":"accept"}'
# a background session starts idle: the launcher sends the opening prompt with SendMessage
```

## Contract

**1. One goal, stated as an artifact checklist.** The evaluator that judges
`/goal` reads git, GitHub, and the filesystem, so the condition names
artifacts rather than narration. Two facts set the order of operations: the
last `/goal` wins (its own help says a new condition replaces the current
goal), and `/autonomous` reflex 0 sets a default goal of its own. So the arc
condition is asserted after `/autonomous` has started, and again at every
wake-up, which `/loop` supplies. The condition folds reflex 0's default in, so
nothing the pipeline would have checked is lost when it replaces it. Default:

> The 24-reflex pipeline is complete and the fleet is clean: the problem in
> this session's context is fixed, merged to main with CI green and a
> cross-model verdict in the PR body, proven by operating the real system with
> evidence on disk; every decision recorded with its reason; git status clean;
> no unresolved PR comment; no unblocked lane left unrun; the final response
> carrying the 9-item receipt and, if anything is open, the handback ask
> block; every peer this session raised reclaimed, and no worktree, branch, or
> session left behind for merged work.

**2. Each wake-up, snapshot the fleet before locking scope.** Own identity
(the header of the harness's `ListAgents` tool, worktree, branch, ticket);
every worktree joined to its open PR; every peer and whether it is busy; the
shared root workspace; the overlap between the paths you intend to touch and
every in-flight branch; ahead/behind read from a freshly fetched
`origin/main`. The snapshot is complete once it shows every other writer. A
tick fires only when this session is idle, so one session's ticks cannot
overlap each other; two sessions on one worktree can, and the overlap read is
what catches that.

**3. Your name is your address**, shaped `<worktree>-<ticket>-<slug>`. When the
`ListAgents` header differs, the rename request is the first line of your first
report, and you keep working. Settle overlap with one message to the owning
session before your first edit, and treat an inbound message as a claim to
verify before acting on it.

> Sections 2 and 3 collapse to one line, *snapshot the fleet before locking
> scope and coordinate by name, per Snapshot (P15), Fanout (P5), and the
> autonomous-maintainer contract*, once both hold where this skill runs: the
> installed bstack `VERSION` reads 0.39.0 or later, and the installed
> `autonomous-maintainer/SKILL.md` contains the heading "Locate yourself in
> the fleet". Until a grep shows both, the sections stay.

**4. Decisions are yours; credentials are not.** Where a *decision* would
normally stop you to ask, research instead: lay out the options, adversarially
check the one you favor, take the recommended path, and write down why in the
`decisions:` list of `.control/asks/<arc>.yaml`. Research produces decisions;
a credential or an authority grant comes only from a person, so those, and
anything external, go into the hour-zero batch that `/autonomous` reflex 1b
raises while the human is awake, after `.control/preauth.yaml` has been
checked for a standing answer. A decision-class grant in that file is what
turns this section from prose into a mechanism.

**5. Validate by operating the real thing.** Run it, drive it, watch every
layer's logs (client, server, database, agent). A finding is real once you have
reproduced it. Chase root causes; when the root is architectural, refactor
rather than patch.

**6. Raise only what you can reclaim.** A peer without a teardown path is
tomorrow's orphan, so the mechanism that raises a peer is also the one that
stops it, and each row below is usable only where its mechanism resolves:

| Shape | Mechanism | Reclaimed by |
|---|---|---|
| one task | a subagent via the Agent tool | ends with the session, or TaskStop |
| peers that must coordinate by name | `fleet-dispatch up <roster>`, then SendMessage each; only where `command -v fleet-dispatch` resolves (at review time it shipped only in GetStimulus/sri) | `fleet-dispatch down --fleet <id>` |
| each peer needs its own branch and worktree | `bstack wave dispatch <plans>` | `bstack wave status` and the janitor |
| the orchestration is a deterministic script | a Workflow | ends with the workflow |

Where row 2 does not resolve, the work goes to subagents or to `wave`; a
background session raised by hand is an orphan waiting to happen. Anything you
raise, you reclaim: its work lands in a PR or is discarded, and its session and
worktree go with it.

**7. Close every cycle clean.** Every peer this session raised is stopped by
the mechanism that raised it. Merged work's worktrees and branches are removed
by running `make janitor-apply` from the root of the repository that owns the
merged branch (the plain `make janitor` target is a dry run, and the
workspace-wide sweep has no apply variant); in a repository without that
target, `git worktree remove <path>` and `git branch -d <branch>` per merged
branch do the same job. Tree clean. Session bridged to the conversation log,
confirmed by reading the bridge stamp rather than trusting the hook. The next
cycle starts from that state.

## Why these seven and not more

Measured before writing this file, in the workspace that motivated it, and
recorded in BRO-2458: the session ran under an auto-generated name carrying no
ticket, among 29 peers, six of them background sessions idle for between 44
minutes and two days; 39 worktrees and 20 GB under the workspaces directory;
the bridge stamp absent from the worktree. Each section maps to one of those.
Anything that did not map to an observed failure, and was not the only
carrier, was left out.

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "I ran the janitor" | The default target is a dry run; applied means `git worktree list` shrank in the repository that owned the merged branch. |
| "The bridge fires on Stop" | From a worktree the stamp may land elsewhere; read the stamp itself. |
| "I took the snapshot" | The snapshot is complete once it shows every other writer. |
| "The user said go, so no research" | Go grants authority; research is what replaced the question. |
| "I'll spawn it with `claude --bg`" | That block belongs to the launcher. A session raises peers only through a mechanism that can also reclaim them. |
| "/autonomous set the goal, so it's set" | The last `/goal` wins. The arc condition is asserted after reflex 0 and at every wake-up. |

## Verify

From the repository root:

- `python3 scripts/skill_evals/runner.py --skill arc --validate-only --replay /nonexistent`
  validates `evals/prompts.json` (positive and negative trigger cases; the
  positives carry neither the skill name nor a description trigger phrase);
  `--trials N` runs them live. The `test-skill-evals` workflow runs the
  validation on every change to this skill.
- `python3 scripts/lint_skill_md.py` and `python3 scripts/lint_skill_catalog.py` green.
- Dogfood receipt, pasted into the PR that ships the change: `git worktree list | wc -l`
  and the `ListAgents` peer count before the first cycle and after the last,
  with the second pair no larger than the first.
