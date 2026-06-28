# Selection Algorithm

When the first-touch agent receives a substantive user input, it executes:

## Step 1: Snapshot signals

- `current_branch` — `git rev-parse --abbrev-ref HEAD`
- `touched_files` — `git diff --name-only HEAD~1 HEAD` + `git diff --name-only` (uncommitted)
- `prompt_tokens` — case-insensitive tokenization of user prompt
- `linear_labels` — from active Linear ticket if discoverable from branch name

## Step 2: Load lens registry

- Read `roles/_meta.md` (always)
- Read all `roles/*.md` where `status: active`
- Cache at session start; reload only on session restart

## Step 3: Score each lens

For each lens L (v0.3.0+):

```
raw_counts = {
  paths:           count(glob in L.signals.paths        : any fnmatch(f, glob) for f in touched_files),
  prompt_keywords: count(kw   in L.signals.prompt_keywords : kw.lower() in prompt_tokens),
  branch_patterns: count(pat  in L.signals.branch_patterns : fnmatch(current_branch, pat)),
  linear_labels:   count(lbl  in L.signals.linear_labels   : lbl in linear_labels),
}

# v0.3.0 — per-signal-type weights. Each lens may declare
# signals.weights.<type>: <int>. Missing entries default to 1.
weights = L.signals.weights ∪ {paths: 1, prompt_keywords: 1, branch_patterns: 1, linear_labels: 1}

score(L) = Σ raw_counts[type] × weights[type]   for each signal type
```

Raw counts are preserved separately for backward-compat with v0.2.0 event-log
schema (`events.jsonl` records counts, not weighted scores). The weighted total
is only used for selection.

## Step 4: Select lens(es)

- **Threshold (v0.3.0)**: per-lens via `L.threshold` (top-level frontmatter
  field); falls back to `DEFAULT_THRESHOLD = 2` if not declared.
- Selection: `selected = [L for L in lenses if score(L) >= L.effective_threshold]`
- Composition: if multiple lenses pass, apply all in descending score order
- Fallback: if no lens passes, apply `_meta` only

### v0.3.0 design notes

- `signals.weights.<type>: 0` is the supported way to disable a signal type for
  a specific lens without removing its declaration.
- A lens's `threshold` cannot be less than 1 (validated at schema check).
- The `_meta` lens is excluded from scoring — it's always applied as the base
  via the `extends:` resolution.
- The `linear_labels` signal source is still stubbed (always returns 0 raw
  count) — declaring a weight on it has no runtime effect until Linear MCP is
  wired (v0.4.0+ planned).

## Step 5: Resolve extension chain

For each selected lens, walk `extends:` back to `_meta`:

```
chain(L) = [L, L.extends, L.extends.extends, ..., _meta]
```

Merge `context_loaders` + `quality_bar` + `prompt_improvement_patterns`
with **child overrides parent** semantics (a child lens can override a
parent's entry by re-stating it with new content).

## Step 6: Decide mode

See `mode-selection.md` for the mode-decision tree.

## Step 7: Emit event

Log to `~/.config/broomva/role/events.jsonl`:

```json
{"ts":"<ISO>","event":"intake","session":"<id>","prompt_digest":"sha256:<hash>","lenses_selected":["<names>"],"lenses_extended":["<chain>"],"mode":"<mode>","signals_matched":{"paths":N,"prompt_keywords":N,"branch_patterns":N,"linear_labels":N}}
```

M1: reasoning-enforced (agent appends manually). M2: hook-driven via
UserPromptSubmit Claude Code hook.

## Reasoning-enforced caveat

The algorithm above is the *contract*. Agents implement it via
reasoning, not via a deterministic script — same pattern as P10, P14,
P15, P16. The Python CLI (`role-x.py`) validates lens schemas and
generates the discovery index but does NOT run selection at runtime.

A future enhancement (M2+) may add `role-x select --prompt "..."` for
deterministic scoring, which would let the agent verify its
reasoning-enforced choice against the algorithm. Not in M1 scope.
