---
tags:
  - broomva
  - control-kernel
  - architecture
type: architecture
status: active
area: system
created: 2026-03-17
---

# Architecture

The agentic control kernel organizes agent-controlled systems into five layers,
each with clear responsibilities, typed interfaces, and explicit safety boundaries.

## Realized Crate Dependency Graph

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

See [integration-map.md](integration-map.md) for the full adapter crate table.

## The Five-Layer Stack

| # | Layer | Responsibility | Key Artifacts / Crates |
|---|-------|---------------|------------------------|
| 1 | **Governance** | Setpoints, policy gates, profiles, audit | `.control/policy.yaml`, `METALAYER.md` |
| 2 | **Harness** | Deterministic commands, CI gates, observability | `Makefile.control`, `scripts/control/` |
| 3 | **Control Kernel** | Plant interface, estimators, controllers, shields | `schemas/`, `.control/plant.yaml` |
| 4 | **Orchestration** | Multi-agent dispatch via Arcan, workspace safety, reconciliation | `WORKFLOW.md`, `symphony-arcan`, `symphony-orchestrator` |
| 5 | **Improvement** | EGRI loops via Arcan sessions, ledger via Lago | `autoany-aios`, `autoany-lago`, `autoany_core` |

Cross-cutting: **Consciousness stack** (auto-memory + conversation bridge + knowledge graph)
provides episodic and declarative memory across sessions.

### autoany_core Modules

| Module | Purpose |
|--------|---------|
| `dead_ends.rs` | Dead-end state detection and tracking |
| `stagnation.rs` | Stagnation detection across trial runs |
| `strategy.rs` | Strategy distillation from trial history |
| `inheritance.rs` | Cross-run state and knowledge inheritance |

## Formal Control Law

Let the plant be a partially observed stochastic dynamical system:

```
x_{t+1} = f(x_t, u_t, w_t)     # state transition
y_t = h(x_t) + v_t              # observation
```

The agentic controller operates on a typed belief state:

```
b_t = Filter(b_{t-1}, y_t, a_{t-1}, r_{t-1})
```

The LLM emits a structured **control directive** θ_t:

```
θ_t = π_LLM(b_t; φ)
```

Examples of θ_t:
- MPC weights, horizon, constraints, reference trajectories
- CBF barrier parameters, class-K function tuning
- Model update requests (Koopman lift changes, retraining triggers)
- Controller module selection (switching logic)

A deterministic controller module K produces candidate controls:

```
ũ_{t:t+H-1} = K(b_t, θ_t)
```

A safety shield S projects into the safe set:

```
u_t = S(ũ_t, b_t) = argmin_u ||u - ũ_t||² s.t. SafetyConstraints(b_t, u)
```

The runtime logs trace entry ℓ_t to ledger L and repeats.

## Control-Flow Sequence (Single Tick)

```
Plant ──observe()──▶ Runtime ──update estimator──▶ b_t
                        │
                        ▼
              LLM Agent: decision(b_t)              [via Arcan session]
                        │
                        ▼ θ_t (typed directive)
              Controller: propose(b_t, θ_t)
                        │
                        ▼ proposed u_t
              Safety Shield: filter(u_t, b_t)       [Autonomic advisory gate]
                        │
                        ▼ safe u_t + certificate
              Plant: apply(safe u_t)
                        │
                        ▼ result + y_{t+1}
              Evaluator/Ledger: append trace         [Lago EventKind::Custom]
```

Runtime options:
- `runtime.kind: subprocess` — spawn agent as local subprocess (default, legacy)
- `runtime.kind: arcan` — dispatch via Arcan HTTP sessions (realized stack)

## LLM Roles in the Control Stack

| Role | LLM outputs | Pros | Latency | Safety risk |
|------|-------------|------|---------|-------------|
| Supervisory controller | setpoints, mode switches, constraints | Long-horizon reasoning, goal translation | seconds-minutes | Medium (bounded by shields) |
| Receding-horizon planner | trajectories, cost weights, scenarios | Shapes MPC without doing QP solves | 0.5-5s | Medium-high |
| Meta-controller over tools | controller module selection, ID triggers | Modular, supports policy switching | seconds | Medium |
| Online identifier | data collection decisions, model updates | Experiment design, anomaly interpretation | seconds-minutes | Medium-high |
| Controller synthesizer | code, safety specs, tests | Converts reasoning to deterministic artifacts | minutes-hours | Low-medium if gated |
| EGRI loop compiler | problem-spec, mutation operators, evaluator | Safe closed-loop improvement process | hours-days | Medium |

**Key rule**: In most physical/fast systems, the LLM outputs controller parameters
and plans, not raw u_t. Only in slow cyber plants (cloud ops, workflows) can the
LLM act closer to the control law — and still requires harness + verifiers + rollback.

## Method → Component Mapping

| Control technique | Component | What must be typed/verified | Best LLM use |
|---|---|---|---|
| Data-driven MPC / DeePC | `control/deepc/` | Data provenance, excitation, solver feasibility | Experiment design, config tuning |
| CBF / HOCBF | `safety/shield/` | Constraint set, feasibility, barrier eval | Choose constraints/margins; never bypass |
| Koopman + MPC | `world_models/koopman/` + `control/mpc/` | Lift versioning, error bounds | Dataset curation, retrain triggers |
| MPC-RL hybrids | `control/hybrid/` | RL proposal bounds, safe fallback | Tune MPC weights under evaluator |
| Differentiable control | `learning/diff_control/` | Reproducible training, gradient checks | Write training harness, loss specs |
| DRO / robust | `control/robust/` | Uncertainty set, worst-case eval | Scenario generation, tradeoff selection |
| Digital twins | `twin/` | Twin validity, calibration metrics | Orchestrate sim experiments |
