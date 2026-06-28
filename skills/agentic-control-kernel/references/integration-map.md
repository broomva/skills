---
tags:
  - broomva
  - control-kernel
  - architecture
type: reference
status: active
area: integration
created: 2026-03-17
---

# Integration Map

Complete boundary map of the unified BroomVA Agent OS stack.

## Crate Dependency Graph

```
aios-protocol (canonical types — shared vocabulary)
      |
      +-- Life Runtime (Arcan :3000, Lago :3001, Autonomic :3002, Praxis, Spaces)
      |         |
      |   +-----+------------------------------+
      |   |                                     |
      |   v                                     v
      |  autoany-aios (adapter)           symphony-arcan (adapter)
      |   |                                     |
      |   v                                     v
      |  autoany_core                      symphony-orchestrator
      |  (EGRI microkernel)               (dispatch + lifecycle)
      |
      +-- Agentic Control Kernel (skill: schemas + docs reflecting the realized stack)
```

## Adapter Crates

| Adapter | Location | Connects | Direction |
|---------|----------|----------|-----------|
| `symphony-arcan` | `symphony/crates/symphony-arcan/` | Symphony -> Arcan | Orchestration dispatches via Arcan HTTP |
| `autoany-aios` | `autoany/autoany-aios/` | Autoany -> Arcan | EGRI execution via Arcan sessions |
| `autoany-lago` | `autoany/autoany-lago/` | Autoany -> Lago | EGRI trials persisted as EventKind::Custom |
| `arcan-lago` | `life/arcan/crates/arcan-lago/` | Arcan -> Lago | Agent events persisted to journal |
| `arcan-spaces` | `life/arcan/crates/arcan-spaces/` | Arcan -> Spaces | Distributed agent networking |
| `autonomic-lago` | `life/autonomic/crates/autonomic-lago/` | Autonomic -> Lago | Homeostatic events persisted |
| `arcan-aios-adapters` | `life/arcan/crates/arcan-aios-adapters/` | Arcan <- Autonomic | Advisory gating from homeostasis controller |

## Configuration

### Symphony WORKFLOW.md

```yaml
runtime:
  kind: arcan           # "subprocess" (default) | "arcan"
  base_url: "http://localhost:3000"
  policy:
    allow_capabilities: ["fs:read:**", "fs:write:**", "exec:*"]
```

### EGRI Event Convention

- Lago journal entries use `EventKind::Custom` with `"egri."` prefix
- Follows Autonomic's pattern: `"autonomic."` prefix for homeostatic events
- Schema: `schemas/egri-event.schema.json`

## Direction Rule

Adapters depend downward on both the service they wrap AND the consumer they serve.
Core crates (`autoany_core`, `symphony-core`) never depend on Life internals.
