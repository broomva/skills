# fleet · rollover: a fresh successor instead of a heavy context

> Workflow of the [`fleet`](../SKILL.md) skill. It is a procedure, not code in
> this skill. **The canonical text is bstack's base protocol, §11**, and for
> the broomva coordinator's own rollover, its overlay's Rollover section:
>
> ```bash
> git -C ~/broomva/bstack fetch -q origin main
> git -C ~/broomva/bstack show origin/main:references/orchestrator-tick.md   # §11 Rollover
> git -C ~/broomva show origin/main:.broomva/loops/prompts/coordinator-tick.md   # ## Rollover
> ```
>
> If this page and those disagree, they win.

## Trigger

The snapshot's `sessions` section (`context_k`: input + cache read + cache
creation of the last main-thread turn, in thousands):

- **A driven session** in `sessions.successor_due` (over 600k): launch a
  successor instead of resuming it.
- **The coordinator itself**, `sessions.self.context_k` over
  `sessions.handoff_k` (400), or a context past use (repeated compaction).
  The coordinator runs its own rollover; it is never an owner ask (owner,
  2026-10-13: "rollovers shouldn't be something i handle").

## Steps

**A driven session** (base §11):
1. Launch a fresh session in the same worktree, seeded with a handoff note:
   the ticket, the branch, the PRs and their heads, the old session's final
   message, and the one next step.
2. [Close out](close-out.md) the old session. A successor is not held by
   `hold_launches` but counts toward `max_driven`; while it can't launch, the
   old session stays unresumed and unarchived, named in `open`.

**The coordinator** (overlay, ## Rollover):
1. Write `state.yaml`; close the tick with `outcome: partial` and
   `data.handoff: true`.
2. `create_agent` the successor in the same workspace (`claude`, Opus),
   seeded with the overlay, the base, `state.yaml` and memory, and nothing
   else, plus the cutover steps: its own heartbeat under the same name, one
   verified tick, `loop.rollover.completed`, archive the predecessor,
   `loops-live.ts`, tell the SRI coordinator.
3. At once, `update_agent` the successor's `paseo.parent-agent-id` to `""`
   and re-read its registry file. Otherwise archiving the predecessor
   cascades and kills the successor.
4. Stop. The successor archives the predecessor once its heartbeat and tick
   verify. Never archive the coordinator any other way: Paseo completes every
   schedule that targets an archived agent, and restoring revives none.

## Check

With `<succ>` the successor's 8-hex id:

```bash
python3 - <succ> <<'PY'
import glob, json, os, sys
(a,) = [json.load(open(f)) for f in glob.glob(os.path.expanduser("~/.paseo/agents/*/%s*.json" % sys.argv[1]))]
print(repr((a.get("labels") or {}).get("paseo.parent-agent-id")))   # '' or None: no parent to cascade from
PY
bun ~/broomva/apps/maestro-paseo/scripts/dogfood/loops-live.ts | grep coordinator-tick   # a row, `on` and `ok`
```

The first line must print `''` or `None`. The second must show the
`coordinator-tick` row `on` and `ok` (measured 2026-10-15:
`coordinator-tick  paseo-heartbeat  broomva  active  on  ok`), not
`ACTIVE_BUT_ABSENT`.
