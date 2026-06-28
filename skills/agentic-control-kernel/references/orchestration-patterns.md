---
tags:
  - broomva
  - control-kernel
  - architecture
type: reference
status: active
area: orchestration
created: 2026-03-17
---

# Orchestration Patterns

Multi-agent orchestration based on the Symphony daemon architecture.
Use these patterns when your control system requires concurrent agents,
workspace isolation, or long-running supervisory loops.

## Symphony Architecture Summary

Symphony implements: **poll → dispatch → per-issue worker → reconcile**

```
Start daemon
  │
  ▼
[Poll Loop: configurable interval]
  ├─ Reconcile: kill stalled, check states, clean terminals
  ├─ Dispatch: fetch candidates, sort by priority, check eligibility
  ├─ Spawn workers (one per issue, isolated workspace)
  │   └─ Per-worker:
  │       ├─ Create/reuse workspace (path-contained)
  │       ├─ before_run hook (abort on failure)
  │       ├─ Render prompt template (Liquid)
  │       ├─ Spawn agent subprocess (JSON-RPC protocol)
  │       ├─ Turn loop (up to max_turns)
  │       ├─ after_run hook (log-only on failure)
  │       └─ Exit handler: accumulate tokens, schedule retry
  ├─ Publish snapshot to HTTP API
  └─ Sleep (wake on refresh/shutdown signal)
```

## Safety Invariants (Mandatory)

From Symphony's workspace safety:

1. **Path containment**: workspace path must start_with(workspace_root) after canonicalization
2. **CWD validation**: verify workspace_path.is_dir() before agent spawn
3. **Identifier sanitization**: keep only `[A-Za-z0-9._-]`, replace others with `_`
4. **Hook safety**:
   - `before_run` failure → abort worker (fatal)
   - `after_run` failure → log only (non-fatal)
   - All hooks have enforced timeouts
5. **Approval posture**: must resolve or fail-closed, never stall indefinitely
6. **Bounded queues**: overload → error requiring retry with exponential backoff

## When to Use Orchestration

| Scenario | Pattern | Why |
|---|---|---|
| Single agent, single plant | No orchestration needed | Direct control loop suffices |
| Multiple plants, independent | Symphony-style parallel dispatch | Workspace isolation per plant |
| Hierarchical control | Nested loops with different rates | Inner/outer loop separation |
| EGRI over multiple artifacts | Portfolio mode (autoany) | Budget allocation across subproblems |
| CI/CD-driven improvement | Event-triggered dispatch | Poll issue tracker / PR queue |

## Orchestration + Control Kernel Integration

### Pattern: Orchestrated Controller Tuning

```
Symphony polls issue tracker for "tune-controller" tickets
  │
  ▼
Per-ticket worker:
  1. Create isolated workspace (clone repo + twin config)
  2. Load problem-spec.control.yaml
  3. Run EGRI loop (autoany) within workspace
  4. If improved: create PR with new controller params
  5. If failed: log to ledger, close ticket with findings
```

### Pattern: Multi-Plant Supervisory Control

```
Symphony polls plant registry for active plants
  │
  ▼
Per-plant worker:
  1. Observe plant state
  2. LLM reasons about directive θ_t
  3. Controller proposes, shield filters
  4. Apply safe action
  5. Log trace
  6. Report status to orchestrator
```

### Pattern: Incident Response

```
Symphony polls monitoring for alerts
  │
  ▼
Per-alert worker:
  1. Diagnose: observe plant, check recent traces
  2. Plan: LLM proposes corrective directive
  3. Contain: apply safe action (conservative mode)
  4. Verify: check plant state post-action
  5. Escalate if unresolved after N turns
```

## State Surface

Symphony exposes runtime state via HTTP:

| Endpoint | Method | Purpose |
|---|---|---|
| `/healthz` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe |
| `/api/v1/state` | GET | Full orchestrator snapshot |
| `/api/v1/refresh` | POST | Trigger immediate poll |
| `/api/v1/shutdown` | POST | Graceful shutdown |
| `/metrics` | GET | Prometheus metrics |

Use these for observability dashboards and integration with CI/CD.

## Symphony + Arcan Runtime

The realized stack replaces Symphony's default subprocess-based agent spawning
with dispatch via Arcan HTTP sessions. This is configured in WORKFLOW.md:

```yaml
runtime:
  kind: arcan           # "subprocess" (default) | "arcan"
  base_url: "http://localhost:3000"
  policy:
    allow_capabilities: ["fs:read:**", "fs:write:**", "exec:*"]
```

### How it works

The `symphony-arcan` adapter crate (`symphony/crates/symphony-arcan/`) implements
Symphony's `Runtime` trait by translating dispatch calls into Arcan HTTP requests:

1. **Session creation** — each worker maps to an Arcan session with scoped capabilities
2. **Turn loop** — Symphony drives turns via Arcan's session API instead of JSON-RPC subprocess
3. **Lifecycle** — session cleanup, timeout enforcement, and token accounting handled by Arcan
4. **Observability** — Arcan events flow to Lago automatically via `arcan-lago`, giving
   Symphony workers a unified audit trail without extra instrumentation

### When to use Arcan runtime vs subprocess

| Scenario | Runtime | Why |
|----------|---------|-----|
| Local development, simple agents | `subprocess` | Lower overhead, no Life dependency |
| Production, multi-agent, auditable | `arcan` | Capability scoping, Lago journal, Autonomic gating |
| EGRI loops over controller artifacts | `arcan` | Trial isolation + automatic ledger via `autoany-lago` |
| Distributed agents across machines | `arcan` + Spaces | Arcan sessions can span nodes via Spaces networking |
