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
| each need their own branch and worktree (one plan file per peer) | `bstack wave dispatch <plan...>` |
| coordinate in ONE worktree (a roster with `owns` lanes) | `bstack fleet up <roster.jsonl>` |
| are independent in-session subtasks | `Agent` calls in one message (Fanout P5), not a launcher |
| are already running and need managing | not this workflow: [reconcile](reconcile.md), [census](census.md), [close-out](close-out.md) |

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
bstack fleet status <fleet-id>   # per-peer liveness; `unknown`, never clean, when the listing can't be read
```

Every peer must show live, or a terminal state its brief allows.
