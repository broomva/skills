---
tags:
  - broomva
  - control-kernel
  - architecture
type: spec
status: active
area: control-loop
created: 2026-03-17
---

# Multi-Rate Hierarchy

Agent runtimes are message-driven, tool-mediated, and subject to timeouts and
approval workflows. This makes them excellent for supervisory control, not for
hard real-time servo loops.

## The Four Loops

### Inner Loop (Hard Real-Time)
- **Cadence**: milliseconds
- **What runs**: PID, state feedback, MPC at fixed dt, CBF-QP shield
- **LLM involvement**: None — deterministic controllers only
- **Rationale**: Tool-call runtimes cannot guarantee fixed-cycle deadlines

### Mid Loop (Soft Real-Time)
- **Cadence**: tens to hundreds of milliseconds
- **What runs**: MPC planning updates, state estimator resets, drift monitors
- **LLM involvement**: Parameter updates only (no reasoning in the loop)
- **Rationale**: Solver-based; LLM sets weights/horizons offline

### Outer Loop (Supervisory)
- **Cadence**: seconds to minutes
- **What runs**: LLM sets goals/constraints, selects control modules, approves escalations
- **LLM involvement**: Yes — this is where the agent reasons
- **Rationale**: Aligns with tool-driven agents, typed actions, approval workflows

### Meta Loop (EGRI)
- **Cadence**: minutes to days
- **What runs**: Autoany-style recursive improvement of models/controllers
- **LLM involvement**: Yes — problem-spec compilation, evaluator design, strategy
- **Rationale**: Requires evaluator-first + rollback + ledger

## Loop-Rate Suitability Heuristics

| Loop | Typical cadence | LLM here? | What to validate |
|------|----------------|-----------|-----------------|
| Servo stabilization | ms | No | Deterministic deadline guarantees |
| Constrained execution | 10-100ms | No (param only) | QP/NLP solve times, feasibility |
| Supervisory planning | seconds | Yes | Tool-call latency, approval flow |
| Auto-tuning (EGRI) | min-days | Yes | Evaluator reliability, rollback |

**Validate per plant**: these are engineering heuristics, not laws.
Your specific system's latency, compute, and safety criticality determine placement.

## Supervisory Control Design Patterns

### Pattern 1: Setpoint Manager
LLM sets reference trajectories and constraints; inner loop tracks them.
```
LLM → {reference_trajectory, constraint_bounds, horizon} → MPC → CBF → Plant
```

### Pattern 2: Module Selector
LLM selects which controller to activate based on system state.
```
LLM → {active_controller: "mpc_aggressive" | "pid_conservative" | "safe_hover"} → Runtime
```

### Pattern 3: Experiment Designer (Identification)
LLM designs data collection experiments for model learning.
```
LLM → {excitation_signal, duration, safety_bounds} → Plant (via shield) → Dataset → Model update
```

### Pattern 4: EGRI Loop Compiler
LLM compiles improvement goals into formal problem-specs.
```
User goal → LLM → problem-spec.yaml → Autoany harness → Improved controller
```

## When the LLM CAN Be Closer to the Loop

For **slow cyber plants** (cloud ops, workflow routing, code generation):
- Actuation is inherently discrete, typed, and slow
- "Inner loop" is seconds, not milliseconds
- LLM can act as the primary controller

**But still requires**: typed schemas, policy gates, rollback, harness verification.
The control hierarchy flattens, but safety principles remain identical.
