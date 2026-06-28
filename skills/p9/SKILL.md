---
name: p9
description: |
  P9 — Broomva productive-wait primitive (the wait optimizer). Convert any
  blocking external operation — PR CI checks, push-triggered deploys, builds,
  long-running index ops — into work on the next priority. The reference
  implementation is a PR CI watcher: drains a context-scoped deferred-work
  queue while `gh pr checks --watch` runs in the background, classifies
  failures, and self-heals known categories. Non-PR waits (today) get a
  single direct check after kicking off next-priority work — wiring those
  into `p9 watch` is on the roadmap. Merge authorization stays with the
  existing control metalayer (.control/policy.yaml).
when_to_use: |
  Automatically after every `git push` that opens or updates a PR. After a
  push that triggers a non-PR deploy: do one direct check after next work,
  never `sleep`. Hard rule: the agent MUST apply productive-wait discipline
  before `sleep` is ever an option.
---

# P9 — Productive Wait (Wait-Optimizer Skill)

## Cardinal rule

> **Never `sleep` on a blocking wait.** Whether you're waiting on PR CI,
> a push-triggered deploy, a long build, or an index sync — convert the
> wait into productive work on the next priority. For PR CI, `p9 watch <pr>`
> spawns the observer in the background and the agent pulls work from the
> wait-queue. For non-PR waits (today), do *one* direct check on completion
> after kicking off next work. Sleep is a footgun — it burns clock time the
> agent could be
> using to validate definitions, refresh the knowledge graph, or draft the
> next slice.

## When to invoke

| Trigger | Action |
|---|---|
| `git push` opens or updates a PR | `p9 watch <pr> --background` immediately |
| `run_in_background` task notification fires for the watcher | `p9 status --pr <n>` to read terminal state |
| `gh pr checks` returned non-zero | `p9 heal <pr> --classify` to inspect failure |
| About to `sleep` | **Don't.** Pull from `p9 wait-queue pop` instead |

## Parallel agent sessions (BRO-1529)

P9 state lives in one shared dir (`~/.config/broomva/p9/`). Concurrent agents
stay collision-free by **scoping every record to a session id**.

> **Contract:** each parallel agent session/worktree/wave-plan MUST export
> `BROOMVA_P9_SESSION=<stable-unique-id>` before calling `p9`. Fanout (P5)
> worktrees, `bstack wave` plans, and autonomous runs each set their own.
> If unset, p9 falls back to a single persisted id (`session-default.id`) —
> i.e. backward-compatible **global** behavior, *not* isolation. No env var ⇒
> no parallel safety.

What the session id buys you:

| Dimension | Behavior |
|---|---|
| **Concurrency ceiling** | `max_concurrent_prs` is counted **per session** — N agents each hold their own watcher. A session's *own* second watch still blocks at the ceiling. |
| **PR identity** | Keyed by `(repo, pr)` — the same PR number in two repos never collides. |
| **Wait-queue** | `pop`/`list`/`clear` default to the **current session's** view (its items + legacy-unowned). `--all` crosses sessions. This is what "context-scoped" finally means in code. |
| **Watcher de-dup** | A second `p9 watch` on a PR that already has a **live** watcher is refused (`--force` to supersede). A **dead** watcher is superseded automatically once aged, or now via `--adopt`. |

### Lifecycle / self-healing

- **`p9 reap`** — reconcile dead-watcher rows (pid gone) to `ABANDONED`,
  freeing the concurrency slot a crashed/closed session would otherwise hold
  forever. `--now` ignores the grace window; `--no-reconcile` skips the gh
  enrichment query. `watch` and `status` run a liveness-only reap as a cheap
  preflight, so the ceiling self-heals without manual `cleanup`.
- **`p9 watch <pr> --adopt`** — re-watch a PR whose prior watcher pid is gone
  (orphan recovery after a session ends mid-watch).
- **Queue TTL** — items are pruned once their PR reaches a terminal state, or
  after `BROOMVA_P9_QUEUE_TTL_DAYS` (default 14).
- **`p9 heal <pr> --apply`** — run the classified `heal_command` under
  `heal.lock` (serialized workspace-wide, so a heal in a parallel session can't
  race on shared codegen/cache). Auto-classifiable failures only; `--dry-run`
  prints the command. `--classify` stays read-only.

## Wait-time work selection (priority order)

When the watcher is running, drain work from these sources in priority order
(higher = pulled first):

1. **session** — TODOs already on the agent's TaskList tagged `wait_ok=true`.
2. **memory** — items from `~/.claude/.../memory/MEMORY.md` flagged "needs
   follow-up" within the last 24h.
3. **graph** — knowledge-graph entities adjacent to files-touched-in-PR
   (BFS depth 1 via `bookkeeping.py query`).
4. **docs** — cross-refs from the current PR's diff (mentioned files not
   yet updated).
5. **linear** — tickets in the current cycle, label-matched to PR's Linear ID.

### Isolation tier (per spec §5.5)

Each pop returns the inferred isolation tier:

| Work type | Tier | Where it happens |
|---|---|---|
| research, docs, knowledge-graph mutations, Linear updates | `none` | current worktree, no separate branch |
| code that's independent of the in-flight PR | `worktree` | new P5 worktree off main |
| code that depends on the in-flight PR | `stacked_branch` | branch off `feat/X+1` from `feat/X` HEAD |
| anything touching `CLAUDE.md` / `AGENTS.md` / `.control/` | `blocked` | **not** auto-handled; surface to user |

## Wakeup protocol

When the bg task notification fires:

```text
1. p9 status --pr <n> --json
2. parse `to_state`:
   - GREEN          → p9 merge-ready <n>; defer to control metalayer
   - RED_CLASSIFIED → p9 heal <n> --classify; if classified+evaluator-positive,
                      apply heal_command (in PR scope only); push amend; loop
   - RED_UNCLASSIFIED, ESCALATED → notify user via Linear ticket; stop healing,
                                    keep watcher alive in case human pushes a fix
   - ABANDONED      → surface failure to user; remove watcher; skip cleanup
```

### The watcher exit code is necessary-not-sufficient (BRO-1489)

`GREEN` only means `gh pr checks --watch` exited 0 — which it does on a *subset*
of checks (required-only) and *before* async bot reviews (CodeRabbit) settle.
Observed three times on bstack PR #78: exit 0 while the PR was `UNSTABLE` / had a
pending review.

`p9 merge-ready` therefore **verifies the real merge predicate** before marking
`MERGE_READY`: it queries `gh pr view --json mergeable,mergeStateStatus,reviewDecision`
plus a best-effort `gh api graphql` unresolved-thread count, and is ready iff
`mergeStateStatus ∈ {CLEAN, UNSTABLE}` with no `CHANGES_REQUESTED` and zero
unresolved review threads. `BLOCKED`/`DIRTY`/`BEHIND`/`DRAFT`/`UNKNOWN`, an open
thread, or any gh error → refused (fail-safe). Pass `--no-verify` to skip
(test/offline only).

Query it directly without transitioning state:

```text
p9 merge-status <n> [--json]   # exit 0 iff merge-ready; prints the verdict + reason
```

## Termination conditions

The agent exits the heal loop when **any** of:

- `to_state ∈ {MERGED, ESCALATED, ABANDONED}` (terminal)
- `attempt ≥ ci_heal.max_attempts` (default 5)
- evaluator returned `stalled=true` for two consecutive cycles
- user interrupt (Ctrl-C in terminal, or chat message)
- session ends (the `Stop` hook leaves watchers running for next session pickup)

## Examples

### Example 1 — Green on first try (happy path)

```bash
$ git push origin feat/my-change
$ gh pr create ... ; PR=42
$ p9 watch $PR --background
watcher_id=ab12cd34ef56 pid=78901 pr=42 repo=broomva/workspace

# Run watcher in foreground/background; meanwhile drain queue
$ p9 wait-queue pop
{"id": "...", "source": "graph", "item": "verify entities adjacent to ...", "isolation_tier": "none"}

# ... agent does the work ...

# bg task notification fires; check terminal state
$ p9 status --pr 42 --json
{"open_prs": [{"pr": 42, "to_state": "GREEN", ...}]}

$ p9 merge-ready 42
PR #42 marked MERGE_READY (control metalayer authorizes merge)

# control-gate-hook authorizes; agent runs `gh pr merge`
```

### Example 2 — Lint-failure self-heal

```bash
$ p9 status --pr 42 --json
{"open_prs": [{"pr": 42, "to_state": "RED_CLASSIFIED", "attempt": 0}]}

$ p9 heal 42 --classify
{"failure_type": "lint", "classified": true, "confidence": 0.8, "heal_command": "bun run lint:fix", "rationale": "matched lint at confidence 0.80"}

# agent runs heal_command, scoped to PR diff files
$ bun run lint:fix
$ git commit -am "fix(lint): heal CI"
$ git push --force-with-lease   # only if existing P6 policy permits
$ p9 watch 42 --background       # new WATCHING cycle; attempt=1
```

### Example 3 — Unclassified-failure escalation

```bash
$ p9 heal 42 --classify
{"failure_type": "unclassified", "classified": false, "confidence": 0.0, "heal_command": null, "rationale": "no rubric pattern matched"}

# Agent does NOT attempt to heal. Creates a Linear ticket via MCP:
#   title: "[P9 ESCALATION] PR #42: feat/my-change"
#   body:  failure signature + log excerpt
#   label: ci-heal-escalation
# Watcher stays running — if a human pushes a fix, watcher resumes and
# the next green check transitions to MERGE_READY.
```

## Cardinal invariant (hard rule)

> **P9 never silently drops state.** Every failure produces (a) a
> `state.jsonl` event, (b) a Linear ticket, or (c) both. If P9 cannot
> write to `state.jsonl` AND cannot reach Linear, it crashes loudly
> (exit 99) — degraded silent operation is forbidden.

## See also

- Spec: `docs/superpowers/specs/2026-05-04-p9-ci-watcher-design.md`
- Rubric: `references/scoring-rubric.md`
- CLI: `scripts/p9.py` (run `python3 scripts/p9.py --help`)
- Related primitives: P1 (Conversation Bridge), P2 (Control Gate),
  P3 (Linear Tickets), P4 (PR Pipeline), P5 (Parallel Agents),
  P6 (Knowledge Bookkeeping), P8 (Branch + Worktree Janitor),
  P10 (Worktree Hygiene Discipline), P11 (Empirical Feedback Loop).
