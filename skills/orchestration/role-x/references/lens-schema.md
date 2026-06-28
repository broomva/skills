# Lens Schema Reference

Each lens lives at `roles/<name>.md` and consists of YAML frontmatter
(machine-readable) + Markdown body (prose detail).

## Required frontmatter fields

| Field | Type | Description |
|---|---|---|
| `name` | string | unique identifier (kebab-case); must match filename basename (`roles/rust-systems.md` → `name: rust-systems`) |
| `status` | enum | `active` (lens applies in selection), `candidate` (logged but not applied), `deprecated` (kept for history) |
| `extends` | string or `null` | parent lens name; `null` only for `_meta`; defaults to `_meta` if omitted |
| `signals.paths` | list of glob patterns | path patterns evaluated against current branch's touched files |
| `signals.prompt_keywords` | list of strings | case-insensitive token match in user prompt |
| `signals.branch_patterns` | list of glob patterns | current-branch name patterns |
| `signals.linear_labels` | list of strings | optional Linear ticket labels |
| `context_loaders.files` | list of strings | workspace-relative file paths to surface in working context |
| `context_loaders.entities` | list of strings | workspace-relative KG entity page paths; intake surfaces each entity's `core_claim` one-liner in working context (v0.4.2) |
| `context_loaders.skills` | list of strings | skill identifiers flagged as "in scope" |
| `context_loaders.glob_hints` | list of glob patterns | globs to surface as "likely relevant" |
| `default_mode` | enum | `augment` / `rewrite` / `decompose` |
| `quality_bar` | list of strings | domain-specific P14 dep-chain checklist |
| `prompt_improvement_patterns` | list of `{signal, suggestion}` objects | optional improvements, surfaced not auto-applied |
| `mode_escalation.rewrite_when` | list of strings | triggers for `augment → rewrite` |
| `mode_escalation.decompose_when` | list of strings | triggers for `* → decompose` |
| `out_of_scope` | list of strings | what this lens explicitly delegates to other lenses |
| `related_lenses` | list of strings | commonly-composed lens names |
| `created` | ISO date | YYYY-MM-DD |
| `updated` | ISO date | YYYY-MM-DD |

## Optional fields (v0.3.0+)

| Field | Type | Default | Description |
|---|---|---|---|
| `threshold` | int (≥1) | `2` | Per-lens score threshold. Specialist lenses (e.g. `security-review`) can set 3 to reduce false positives; broad lenses can set 1 to fire on a single strong signal. |
| `signals.weights.paths` | int (≥0) | `1` | Multiplier on path-glob match count |
| `signals.weights.prompt_keywords` | int (≥0) | `1` | Multiplier on prompt keyword match count |
| `signals.weights.branch_patterns` | int (≥0) | `1` | Multiplier on branch pattern match count |
| `signals.weights.linear_labels` | int (≥0) | `1` | Multiplier on Linear label match count (note: `linear_labels` signal source is currently stubbed to 0 at runtime regardless of weight) |

Setting a weight to `0` disables that signal type for the lens without removing the declaration. All weight values must be **non-negative integers**.

### Example — strict specialist lens with branch-amplified scoring

```yaml
---
name: security-review
status: active
extends: _meta
threshold: 3
signals:
  paths: ["**/auth/**", "**/credentials*"]
  prompt_keywords: ["auth", "secret", "credential", "JWT", "OAuth"]
  branch_patterns: ["feat/auth-*", "feat/security-*"]
  linear_labels: ["topic:security"]
  weights:
    branch_patterns: 3
    prompt_keywords: 1
    paths: 1
context_loaders:
  files: ["docs/security/checklist.md"]
  …
---
```

Resolution at intake:
- Prompt = "rotate the JWT signing key" on branch `feat/auth-rotate`
- Raw counts: prompt_keywords=1 ("JWT"), branch_patterns=1 (matches `feat/auth-*`), paths=0
- Weighted total: 1×1 + 1×3 + 0×1 = **4**
- Threshold: 3 → **lens fires** ✓

### When to use which strategy

| Need | Use |
|---|---|
| Lens fires too easily on weak signals | Raise `threshold` to 3+ |
| Lens needs to fire on a single strong domain word | Lower `threshold` to 1 |
| One signal type matters far more (branch name, ticket label) | Raise that type's weight to 2-3 |
| Lens has a path that's noisy/incidental | Set `signals.weights.paths: 0` and rely on keywords/branch |
| Lens covers a very narrow domain (rare false fires acceptable) | `threshold: 1` + 1-2 highly specific keywords |

## Body content

The Markdown body is for the agent's reasoning context when the lens
fires. Typical sections:

- **Workspace conventions** specific to this domain
- **Common anti-patterns** the lens flags
- **Composition triggers** — when this lens commonly composes with others
- **Reference docs** — links to authoritative sources

The body is human-readable but agent-consumed — assume an agent will be
reading it before responding to a user prompt in this domain.

## Validation

Run `python3 scripts/role-x.py validate roles/<name>.md`
to check frontmatter against schema. CI gate (M2+) enforces validation
in pre-commit.

## Example: minimal valid lens

```yaml
---
name: example
status: active
extends: _meta
signals:
  paths: ["**/*.example"]
  prompt_keywords: ["example"]
  branch_patterns: []
  linear_labels: []
context_loaders:
  files: []
  entities: []
  skills: []
  glob_hints: []
default_mode: augment
quality_bar: []
prompt_improvement_patterns: []
mode_escalation:
  rewrite_when: []
  decompose_when: []
out_of_scope: []
related_lenses: []
created: 2026-05-13
updated: 2026-05-13
---

# example lens
```
