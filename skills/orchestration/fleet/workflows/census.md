# fleet · census: who is live, and whose is it

> Workflow of the [`fleet`](../SKILL.md) skill. It is a procedure the standing
> coordinator runs, not code in this skill. **The canonical text is bstack's
> base protocol, §4.** Read it from git, as every fire does:
>
> ```bash
> git -C ~/broomva/bstack fetch -q origin main
> git -C ~/broomva/bstack show origin/main:references/orchestrator-tick.md   # §4 Census
> ```
>
> The overlay sets the scope: `.broomva/loops/prompts/coordinator-tick.md` in
> broomva/workspace, §Scope. If this page and the base disagree, the base wins.

## Trigger

Every fire of a standing coordinator: the `every` tier of `coordinator-tick`
(broomva) and of `sri-coordinator-tick` (SRI, its own overlay and scope). The
check below is broomva's snapshot; SRI's census runs from SRI's own overlay.

## Steps

1. Enumerate from Paseo's registry, `~/.paseo/agents/*/*.json`, not
   `list_agents`, which under-reports (6 of 34 on 2026-10-08). Live means
   `archivedAt` is null.
2. Drop every agent outside the overlay's scope. SRI's sessions are SRI's, and
   are never read, prompted or archived from the broomva side.
3. Classify each agent left, first match wins (base §4): `self`, `other` (not
   a model session, another orchestrator or its descendant, or a Maestro run
   in another scope), `arc` (a worker this coordinator or a predecessor
   launched: the `paseo.parent-agent-id` or `dispatched-by` label, or a
   Maestro card it filed), `owner` (everything else). A cleared parent label is
   `""`, and `""` is never a parent.
4. Hand each class to its handling: `arc` to session handling (base §5),
   `owner` to [close-out](close-out.md) once idle over 12 h.

On broomva the snapshot does steps 1 to 3 in one read-only run, and the tick
works from its `census` section.

## Check

```bash
git -C ~/broomva show origin/main:.broomva/loops/checks/coordinator-tick.sh | bash \
  | python3 -c 'import json,sys; c=json.load(sys.stdin)["census"]; assert "error" not in c, c; print(c["counts"])'
```

It must print the four counts (`self`, `other`, `arc`, `owner`), with `self`
equal to 1: the coordinator `state.yaml` names (measured 2026-10-15:
`{'self': 1, 'other': 13, 'arc': 1, 'owner': 14}`). A `census` section holding `error`
means the census did not run, and the tick says so instead of acting on it.

## Not this workflow

The reconcile tick's session classes (`workflows/reconcile.md`, the spec's
class table over `claude agents --json --all`) are a different reading: what
state each Claude Code session is in. The census asks whose a Paseo agent is.
