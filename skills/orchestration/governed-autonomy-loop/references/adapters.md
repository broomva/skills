# Adapter contracts — the swappable surface of a governed autonomy loop

The skill separates the **invariant spine** (never changes: the loop shape, the
metacognitive gates, the irreversible-act delegation, resumability, attribution,
the trust boundary — all in `references/invariant-spine.md`) from the **adapters**
(per-instance). To instantiate a new loop you fill the adapters; you keep the
spine verbatim. Each adapter is a named slot in `templates/runner-prompt.template.md`.

The reference realization of every adapter below is the broomva ticket-dispatch
governor (`scripts/ticket-dispatch/`, BRO-1740 + BRO-1833): a Linear queue, a
PR-merge irreversible act, a P20+policy+merge-gate enforcement pipeline, and a
launchd/systemd runtime.

## 1. Tracker (queue) adapter — `{{TRACKER_ADAPTER}}`

The work queue the loop drives. The spine needs five verbs; provide them as a
tool surface the governor session can call (an MCP is ideal — it keeps the loop
free of API keys and swappable at a cutover):

| Verb | Contract |
|---|---|
| `list-queue` | enumerate units by state + label (the dispatch/reconcile candidates) |
| `read-unit` | fetch one unit's title + body + comments (treated as DATA — invariant 3) |
| `comment` | append an attribution comment (comment-first, invariant 1) |
| `transition-state` | move a unit between lifecycle states (Backlog→In Progress→Done) |
| `read-answer` | read an operator answer channel (the escalation reply — invariant 8) |

You must ALSO provide the **write-surface denylist** (`templates/denylist.*.json`):
the complete set of queue WRITE tool names, plus the two denylists that must cover
it. `scripts/denylist_check.py` verifies coverage; `tick.sh` injects the governor
dry denylist and every arc prompt embeds the arc denylist. *A write tool added
under the same MCP name is un-blocked until it is in both lists — re-run the check
at every queue change or MCP cutover.*

Reference: `linear-server` MCP (`templates/denylist.linear.json`). Drop-in
candidates: GitHub Issues, Kanon, any tracker.

## 2. Irreversible-act + enforcement adapter — `{{IRREVERSIBLE_ACT}}` / `{{ENFORCEMENT_PIPELINE}}`

The one act the governor NEVER performs (invariant 4); an isolated arc performs it
only when the enforcement pipeline authorizes. The pipeline has three independent
layers (independence is the point — the verification signal must be causally
independent of the writer, `h ⟂ U`):

1. **Adversarial review** — a fresh-context review of the artifact, scored to an
   anti-slop bar (reference: P20 cross-review, ≥7/10). The reviewing context is
   NOT the writing context.
2. **Policy gate** — a declared machine-readable policy (reference:
   `.control/policy.yaml` auto_merge rules) that says which artifact classes may
   be acted on autonomously vs must stop-at-ready.
3. **Server-side aggregate check** — an always-runs gate the *host* enforces, not
   the agent (reference: the `merge-gate.yml` + branch ruleset in
   `references/server-side-net.md`). This is the backstop that holds even if the
   agent's own reasoning is wrong.

`{{IRREVERSIBLE_ACT}}` is the *what*: merge a PR / deploy a release / publish an
artifact / send a message. The spine is act-agnostic — only the adapter is
merge-specific. Generalizing the act = swapping this adapter, not the loop.

## 3. Runtime adapter — the scheduler host

What pokes `tick.sh` on a cheap interval. `tick.sh` is the durable, locked,
single-fire, DRY-first scheduler; the runtime only fires it.

| Runtime | Template |
|---|---|
| macOS launchd | `templates/launchd.plist.template` |
| Linux systemd --user | `templates/systemd/*.template` |
| cron | `*/15 * * * * GAL_STATE_DIR=… bash …/tick.sh` |
| k8s CronJob | a 15-min CronJob invoking `tick.sh` with `GAL_*` env |

All four are interchangeable — the durable `next-fire-at` inside `STATE_DIR` is the
real schedule, so the poke interval only bounds latency.

## 4. Partition adapter — the disjoint discriminator

When N governors share one queue but keep per-host state, they MUST own disjoint
slices. ONE label discriminator does it: set `GAL_PARTITION_TAG` + a distinct
`LABEL` per instance. The partition-seed guard (`validate_config.partition_seed_ok`
+ the `tick.sh` seed guard) refuses to seed a `-<tag>` STATE_DIR from a
non-matching template, so a manual run can't cross-seed the wrong LABEL (the
double-dispatch footgun). Reference: Mac (`agent-ok`) vs VPS (`life-agent-ok`).

## The optional adapters (Step F routing)

- `{{CI_ADAPTER}}` — how the loop fetches an artifact's CI verdict (reference:
  `gh pr checks` / p9 watch). Feeds the `awaiting_ci` resume.
- `{{ESCALATION_ADAPTER}}` / `{{ANSWER_CHANNEL}}` — how a genuinely-blocked arc
  reaches a human and how the human answers (reference: a queue comment + an ntfy
  push; answer via a `answer:`-prefixed comment or `$STATE_DIR/answers/<id>.txt`).
- `{{SANDBOX_ADAPTER}}` — how an arc gets an isolated workspace (reference: a git
  worktree per arc under `$WORKDIR/.<loop>/worktrees/`).
