# Feedback Loop — design + shipped status

Lens-use telemetry feeds back into lens-rule improvements via the P13
dream cycle. v0.2.0 shipped the capture layer; v0.4.0 shipped the
observability + scaffolding layer. v0.5.0+ adds tuning/proposal
automation; v0.6.0 (M5) ships the full dream cycle.

**See [`observability.md`](observability.md) for the v0.4.0 substrate**
(event schema, `role-x suggest`, `role-x init`, sanitized capture).

## Three hook integration points (M2)

| Hook event | Captured | Storage |
|---|---|---|
| `UserPromptSubmit` | session id, prompt content snapshot (digest only), selected lens(es), mode, escalation reason if any, signals matched | `~/.config/broomva/role/events.jsonl` |
| `PostToolUse` | session id, tool name, lens-loaded context referenced (heuristic: did tool inputs intersect with `context_loaders.files`?) | same file |
| `Stop` | session id, lens-use outcome (CI green? PR merged without changes? user accepted suggestions? bookkeeping score?) | same file |

Events append one-per-line (flock-protected). Schema is intentionally
narrow — no model output content, no PII, just routing decisions and
their downstream signals.

## Dream-cycle consolidation (M4)

`python3 scripts/role-x-replay.py <lens-name>` runs the P13 5-phase dream cycle applied to lens rules:

| Phase | Action |
|---|---|
| **Gather** | Read `events.jsonl` for the lens over a bounded window (default 30 days). Bundle into `~/.config/broomva/role/consolidation-runs/<lens>-<date>/bundle.jsonl`. |
| **Replay** | Re-score each event against a *frozen snapshot* of the lens at bundle-creation time. Compute counterfactuals: what would the lens have done if its rules were updated? |
| **Prune** | Discard events showing no behavior change between live and counterfactual replay, or where outcome metric showed no improvement. |
| **Consolidate** | Emit a YAML diff against the lens's frontmatter (new signals, refined quality_bar entries, new prompt_improvement_patterns). Commit via PR. |
| **Index** | Update `roles/_index.md`; update `~/.config/broomva/role/status.json`. |

Critical: replay does NOT touch the live lens; it computes counterfactuals
against the frozen snapshot. This is the stop-gradient property that
distinguishes dream cycles from shadow dreams.

## Cadence

- Per-50-uses-per-lens (statistically sufficient for rule-change signal)
- OR weekly (whichever fires first)
- Manual invocation always available

## Shipped scope

- **v0.2.0** — `UserPromptSubmit` hook + `role-x intake` subcommand + events.jsonl capture ✓
- **v0.4.0** — `role-x suggest` + `role-x init` + opt-in sanitized prompt capture + privacy-by-default config ✓

## Pipeline status

| Stage | Version | Status |
|---|---|---|
| Capture intake events | v0.2.0 | ✓ shipped |
| Sanitized prompt capture (opt-in) | v0.4.0 | ✓ shipped |
| Analyze + suggest lenses | v0.4.0 | ✓ shipped (`role-x suggest`) |
| Scaffold candidate lenses | v0.4.0 | ✓ shipped (`role-x init`) |
| Propose lens-rule tuning | **v0.5.0** | planned (`role-x tune <lens>`) |
| Generate candidate from cluster | **v0.5.0** | planned (`role-x propose-lens <cluster>`) |
| PostToolUse outcome capture | **v0.7.0** | planned |
| Stop outcome capture (CI green, Nous score) | **v0.7.0** | planned |
| `role-x-replay.py` 5-phase dream cycle | **v0.6.0 (M5)** | planned |
| Auto-promote candidates on positive outcomes | **v0.6.0 (M5)** | planned |
| Frozen-snapshot management under `consolidation-runs/` | **v0.6.0 (M5)** | planned |
| LLM judge integration for counterfactual scoring | **v0.6.0 (M5)** | planned |
| Auto-PR for consolidation diffs | **v0.6.0 (M5)** | planned |
| Lens decay + auto-demotion (unused 90d) | **v0.8.0** | planned
