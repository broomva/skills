# Observability — data substrate for organic lens growth

v0.4.0+ ships the telemetry primitives that let the `roles/` registry grow from real data instead of speculative authoring. This file documents the data flow, schema, and the v0.5.0+ pipeline this substrate enables.

## Pipeline overview

```
UserPromptSubmit
      ↓ (role-x intake — v0.2.0)
events.jsonl  ← prompt_digest + signals_matched + lenses_selected + mode
      ↓ (role-x suggest — v0.4.0)
analysis report  ← fire-rate + per-lens drift + emergent keyword clusters
      ↓ (role-x init — v0.4.0)
roles/<name>.md (status: candidate)
      ↓ (rule-of-three positive outcomes — P16)
roles/<name>.md (status: active)
      ↓ (role-x tune — v0.5.0, planned)
PR diff with proposed keyword/threshold/weight updates
      ↓ (role-x-replay.py — v0.6.0, M5, planned)
auto-promote / auto-demote based on counterfactual replay against frozen snapshots
```

Each transition is human-reviewable (the lens file diff is the artifact). The system makes proposals; humans accept/reject via PR.

## Event schema (current, backward-compat preserved)

Every intake appends one line to `~/.config/broomva/role/events.jsonl`:

```json
{
  "ts": "2026-05-14T12:30:35.150348+00:00",
  "event": "intake",
  "session": "<claude-session-id>",
  "prompt_digest": "sha256:<64-hex-chars>",
  "prompt_word_count": 12,
  "lenses_selected": ["rust-systems"],
  "lenses_extended": ["rust-systems", "_meta"],
  "mode": "augment",
  "mode_escalation_reason": null,
  "signals_matched": {
    "paths": 0,
    "prompt_keywords": 4,
    "branch_patterns": 0,
    "linear_labels": 0
  },
  "prompt_sanitized": {                    // ← v0.4.0 optional
    "strategy": "keywords",
    "value": ["rust", "cargo", "tokio", "async"]
  }
}
```

Fields:

| Field | Since | Purpose |
|---|---|---|
| `ts` | v0.2.0 | ISO-8601 UTC timestamp |
| `event` | v0.2.0 | Always `"intake"` in this file; reserved for future event types |
| `session` | v0.2.0 | Claude Code session id (or `"unknown"`) — same session can fire many intakes |
| `prompt_digest` | v0.2.0 | `sha256:<hex>` of the raw prompt. Privacy-preserving fingerprint for deduplication. |
| `prompt_word_count` | v0.2.0 | Length signal — informs the carve-out threshold check |
| `lenses_selected` | v0.2.0 | Lens names that scored ≥ effective threshold (empty list = `_meta`-only) |
| `lenses_extended` | v0.2.0 | Full extension chain including `_meta` |
| `mode` | v0.2.0 | One of `augment` / `rewrite` / `decompose` |
| `mode_escalation_reason` | v0.2.0 | Why we escalated beyond `augment` (or `null`) |
| `signals_matched` | v0.2.0 | **Raw counts** (not weighted) — preserved for cross-version comparability |
| `prompt_sanitized` | **v0.4.0** | **Optional**; absent unless config opts in. Two strategies — see below |

## Sanitized prompt capture (v0.4.0, opt-in)

### Privacy invariant

> Absent config = no sanitized capture. Existing installations from
> v0.1.0/v0.2.0/v0.3.0 with no config file behave identically to before —
> only `prompt_digest` (sha256) is recorded. Any sanitization is **opt-in
> per workstation** via `~/.config/broomva/role/config.json`.

### Config file

`~/.config/broomva/role/config.json`:

```json
{
  "capture_sanitized_prompt": true,
  "sanitization_strategy": "keywords",
  "sanitization_top_n_keywords": 5,
  "sanitization_first_chars": 80
}
```

Defaults (when keys missing): `capture_sanitized_prompt: false`, `sanitization_strategy: "keywords"`, `sanitization_top_n_keywords: 5`. Unknown values fall back to defaults silently.

### Strategy: `keywords` (recommended)

Extracts the top-N **unique** alphanumeric tokens (length > 2) from the prompt, in order of first appearance, lowercased. Excludes 1- and 2-character words.

Input: `"Implement rust cargo tokio runtime support with proper error handling"`
Output: `["implement", "rust", "cargo", "tokio", "runtime"]` (N=5)

- **Pros**: useful for cluster discovery; resilient to typos in long prompts (frequency washes out noise); easy to scan visually
- **Cons**: loses structure (sentence boundaries, modifiers); won't catch multi-word concepts like "next.js"

### Strategy: `first_chars`

Captures the first N characters of the raw prompt.

Input: `"Implement rust cargo tokio runtime"` (configured `n=20`)
Output: `"Implement rust cargo"`

- **Pros**: higher fidelity for debugging; preserves phrasing
- **Cons**: more PII-sensitive; sensitive to prompt-opening boilerplate; less useful for clustering

## `role-x suggest` analysis

Three sections in every `suggest` report:

### 1. Window summary

```
[role-x suggest] window: --since 7d, events: 247
  fired ≥1 lens: 89 (36%)
  _meta only:    158 (64%)
```

Coverage ratio (lens-fired %) is the primary health metric. If it's < 30%, the registry doesn't cover what users are actually working on — author more lenses. If it's > 90%, lenses may be over-firing (false positives) — raise thresholds.

### 2. Emergent keyword clusters (requires sanitized capture)

Greedy clustering: take the top-frequency keyword among `_meta`-only events, find its co-occurring keywords, group events that share ≥2 of them. Cluster size threshold via `--threshold N` (default 2).

If sanitized capture is off, this section is replaced with a config-enablement hint.

### 3. Per-active-lens drift summary

For each lens that fired in the window: fire count, distinct session count, average prompt word count. v0.5.0 will extend this with keyword drift (top co-occurring keywords NOT in the lens's `prompt_keywords` list) and threshold drift (% events that fired vs missed by 1-2 signals).

## Privacy guarantees

| What | Stored where | When |
|---|---|---|
| Full prompt text | **NOWHERE** by default | Never recorded |
| `prompt_digest` (sha256) | `events.jsonl` | Always (v0.2.0+) — enables deduplication without revealing content |
| `prompt_sanitized` (5 keywords / 80 chars) | `events.jsonl` | Only when config opts in |
| Session id | `events.jsonl` | Always — links related intakes; doesn't traverse to identity |
| File paths (touched files signal) | Not in events directly | Path *match counts* recorded under `signals_matched.paths`; raw paths NOT stored |
| Branch name | Not in events directly | Match count recorded under `signals_matched.branch_patterns`; raw branch NOT stored |

The sha256 digest is irreversible. Even with sanitized capture on, only the top-N keywords (lowercase, deduped) appear in events — not the original prompt text or its structure.

## Operational notes

- **Log rotation**: `events.jsonl` grows ~1 line per substantive prompt. At ~50-200 prompts/day, expect ~1-5MB per quarter. No auto-rotation today; if it becomes a concern, archive with `mv events.jsonl events.jsonl.YYYY-MM-DD && touch events.jsonl`.
- **Concurrent writes**: the intake hook writes in append-only mode with one line per event. Brief contention between concurrent sessions is benign — line boundaries are preserved.
- **Schema migrations**: any future schema change must be **backward-additive** (new optional fields only). `role-x suggest` is designed to tolerate older event lines missing newer fields.

## Future (v0.5.0+)

- `role-x tune <lens>` — analyze the event log for an active lens; propose YAML diffs to its `prompt_keywords`, `paths`, `threshold`, `signals.weights`. Output is a PR-ready diff; never auto-applies.
- `role-x propose-lens <cluster-name>` — take a cluster from `suggest` output; generate a fully-scaffolded candidate lens with signals pre-populated from cluster keywords.
- `PostToolUse` outcome hook — record whether the agent actually referenced the lens's `context_loaders.files` during the session. This bridges "lens fired" to "lens fired AND was useful".
- `Stop` outcome hook — record session-end outcomes: did the PR merge green? Did Nous score the resulting entity ≥5? These are the quality signals that drive auto-promotion in v0.6.0.
- `role-x-replay.py` (M5 / v0.6.0) — full P13 dream cycle: gather events → replay against frozen lens snapshots → prune events with no behavior change → consolidate as YAML PR → re-index registry. Auto-promote candidates after rule-of-three positive outcomes; auto-demote unused lenses after 90 days.

## See also

- [`feedback-loop.md`](feedback-loop.md) — the M5 dream-cycle architecture this telemetry feeds
- [`selection-algorithm.md`](selection-algorithm.md) — how raw counts in `signals_matched` get computed
- [`lens-schema.md`](lens-schema.md) — the lens fields that `role-x init` scaffolds and `role-x tune` will modify
