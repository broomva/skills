# Mode Selection

After lens(es) are selected, the agent decides the operating mode.

## The three modes

### `augment` (default)

Lens context is loaded silently. User prompt passes verbatim to the
working agent. Quality-bar checklist is the P14 dep-chain template
for the response.

**Chosen when:**
- Prompt is clear and single-domain
- No obvious missing constraints
- Work fits in a single agent's scope

**User-facing surface:** minimal — agent proceeds with the request.
Quality-bar checklist appears as the agent's dep-chain enumeration in
the response per P14.

### `rewrite` (surfaced)

Agent produces a refined version of the user prompt with explicit
constraints (the lens's `prompt_improvement_patterns` applied). Surfaces
both original and rewritten to the user. Proceeds with whichever the
user accepts (default: rewritten).

**Chosen when:**
- Prompt is ambiguous about scope, target, or constraint
- The lens's `mode_escalation.rewrite_when` triggers fire
- The request implicitly assumes context the user didn't state

**User-facing surface:**

```
I'm applying lens(es): rust-systems (signals: 3 path matches, 2 keyword matches)

Your prompt was ambiguous about MSRV — the rust-systems quality_bar
requires it. Suggested rewrite:

  Original: "Add async support to the auth module"

  Rewritten: "Add tokio-based async support to the auth module in
  core/life/crates/anima, honoring workspace MSRV 1.85, with Send-bound
  futures, thiserror-based error type, and a conformance test."

Proceed with rewritten, original, or edit?
```

### `decompose` (surfaced)

Agent produces a parallel-agent plan: N sub-tasks, each with its own
lens, scoped boundaries, and merge instructions. User approves the
plan; P5 dispatches the parallel agents. Each sub-agent runs role-x
recursively at its scope.

**Chosen when:**
- Prompt spans ≥2 independent domains
- Independent sub-tasks emit no cross-references
- The lens's `mode_escalation.decompose_when` triggers fire

**User-facing surface:**

```
I'm applying lens(es): rust-systems + ts-nextjs + infra-deploy

Your prompt spans 3 independent domains. Proposed parallel plan:

  Sub-agent 1 (lens: rust-systems): refactor auth handler in core/life/crates/anima
    Worktree: .worktrees/auth-rust
    Owns: core/life/crates/anima/**

  Sub-agent 2 (lens: ts-nextjs): update chatOS auth UI in apps/chatOS
    Worktree: .worktrees/auth-ts
    Owns: apps/chatOS/app/**

  Sub-agent 3 (lens: infra-deploy): update Vercel env vars
    Worktree: .worktrees/auth-deploy
    Owns: apps/chatOS/vercel.json + ops/vercel-config/**

Merge order: 1 → 2 → 3 (TS depends on Rust API; deploy depends on TS build).

Approve? (yes / edit / cancel)
```

## Mode escalation rules

- `augment` can escalate to `rewrite` or `decompose`
- `rewrite` can escalate to `decompose`
- **Never** escalate in reverse within a single intake pass — prevents thrashing
- Sub-agents start fresh with `augment` default at their scope

## When a lens has `default_mode: rewrite` or `default_mode: decompose`

Lens authors can override the workspace default of `augment` per lens.
Example: a hypothetical `migration` lens might default to `decompose`
because migration work naturally fans out.

Escalation rules still apply — a lens with `default_mode: rewrite` can
still escalate to `decompose` per `mode_escalation.decompose_when`.
