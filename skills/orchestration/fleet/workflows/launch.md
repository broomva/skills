# fleet · launch: start parallel peers (bstack's launchers)

> Workflow of the [`fleet`](../SKILL.md) skill. **This skill launches
> nothing.** Launching is bstack's: `bstack wave dispatch` and `bstack fleet
> up`, both on `scripts/peer.py`. This page only routes there. The canonical
> rule is bstack's SKILL.md (the `bstack wave` and `bstack fleet` notes) and
> the Orchestrate (P19) cube in the `autonomous` skill:
>
> ```bash
> git -C ~/broomva/bstack fetch -q origin main
> git -C ~/broomva/bstack show origin/main:SKILL.md | grep -n -A3 'bstack fleet` (≥ 0.40.0)'
> ```
>
> `bstack fleet` (the launcher) and this skill's `fleet` CLI are different
> commands in different namespaces; neither is renamed, and this skill puts no
> `fleet` on PATH.

## Trigger

N>1 peers, across sessions, on an external trigger: the cell bstack's rule
decides on the worktree axis.

| The peers… | Use |
|---|---|
| are launched by an orchestrator that runs inside T3 Code (the t3-code MCP tools are present) | T3 `delegate_task` or `t3_thread_launch`, a model chosen per lane: not `bstack wave` or `bstack fleet`. See [Under T3](#under-t3) below |
| each need their own branch and worktree (one plan file per peer) | `bstack wave dispatch <plan...>` |
| coordinate in ONE worktree (a roster with `owns` lanes) | `bstack fleet up <roster.jsonl>` |
| are independent in-session subtasks | `Agent` calls in one message (Fanout P5), not a launcher |
| are already running and need managing | not this workflow: [reconcile](reconcile.md), [census](census.md), [close-out](close-out.md) |

**Under T3.** When the orchestrator runs inside T3 Code, launch through T3 and
not through either bstack launcher. Child work goes through `delegate_task`
(with `isolation: "worktree"` when it needs its own checkout). Continuing an
existing worktree goes through `t3_thread_launch` with `workspaceStrategy
{type: "existing_worktree"}`. Pick provider, model and effort per lane from
`orchestrator_capabilities`: the strongest model for invariant-bearing or
security work, a mid-tier model for UI from precise boards, and a cheap tier
(Haiku 5.5, GPT-6-Luna, Gemini 3.8 Flash) for mechanical, spec-complete work and
checklist verification. Cap concurrent implementing peers by machine memory: on
2026-10-19 a 24 GB Mac crashed under 8 `claude --bg` peers plus a local dev
stack, and those peers had been invisible in T3, all on one model, and stalled
on permission prompts until relaunched in bypass mode.

## Steps

1. Pick the row above, and say which cell you picked.
2. Run the launcher. Every peer is named `<worktree>-<ticket>-<slug>`
   (`scripts/peer.py`), runs unattended (`--strict-mcp-config`,
   `crossSessionInbound: accept`), and is tracked under
   `~/.cache/bstack/{wave,fleet}/<id>/`.
3. From then on the peers are fleet sessions like any other: the census
   classifies them, reconcile's tick reads them, close-out archives them.

## Check

```bash
bstack wave status <wave-id>     # one row per plan, LIVE column joined to its session
bstack fleet status --fleet <fleet-id>   # per-peer liveness; `unknown`, never clean, when the listing can't be read
```

Every peer must show live, or a terminal state its brief allows.
