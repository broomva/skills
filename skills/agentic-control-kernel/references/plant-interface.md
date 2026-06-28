---
tags:
  - broomva
  - control-kernel
  - architecture
type: spec
status: active
area: plant
created: 2026-03-17
---

# Plant Interface

Standardized API contracts for the control kernel. Language-agnostic;
implementable in Python, Rust, TypeScript, or any typed language.

## Core Interfaces

### Plant

The system being controlled — physical, cyber-physical, or purely cyber.

```
Plant:
  observe() -> Observation
    # Returns current sensor readings / system state
    # Must include timestamp and observation_id

  apply(action: Action) -> ActuationResult
    # Applies a control action to the system
    # Returns success/failure, new observation, side effects

  reset(seed?: int) -> Observation
    # Reset to initial state (for simulation/testing)
    # Optional seed for reproducibility

  constraints() -> ConstraintSet
    # Returns current hard constraints (state bounds, actuation limits)
    # May be time-varying or mode-dependent
```

### Estimator

Maintains belief state from noisy/partial observations.

```
Estimator:
  update(obs: Observation) -> BeliefState
    # Fuse new observation into belief
    # Returns updated belief with uncertainty estimates

  predict(belief: BeliefState, actions: ActionSequence) -> BeliefTrajectory
    # Optional: predict future belief states given action plan
    # Used by MPC-style planners
```

### Controller

Produces candidate control actions from belief state and directives.

```
Controller:
  propose(
    belief: BeliefState,
    directive: ControlDirective,  # θ_t from LLM
    world_model?: WorldModel,
    constraints?: ConstraintSet
  ) -> ProposedAction
    # Returns candidate action sequence + metadata
    # Metadata includes: solver status, cost, feasibility flag

  configure(params: ControllerParams) -> void
    # Update controller parameters (gains, weights, horizons)
    # Used by LLM to tune without replacing the controller
```

### SafetyShield

Hard safety filter — projects proposed actions into safe set.

```
SafetyShield:
  filter(
    proposed: ProposedAction,
    belief: BeliefState
  ) -> SafeAction
    # Returns: safe_action, certificate, modification_magnitude
    # certificate: proof that safety constraint is satisfied
    # modification_magnitude: ||u_safe - u_proposed|| (monitor for shield saturation)

  feasible(belief: BeliefState) -> bool
    # Check if any safe action exists from current state
    # If false: emergency fallback required

  fallback(belief: BeliefState) -> SafeAction
    # Emergency safe action (e.g., stop, hover, safe state)
    # Must always succeed
```

### Evaluator (Autoany-compatible)

Scores traces for the EGRI improvement loop.

```
Evaluator:
  score(traces: TraceBatch) -> ScoreVector
    # Returns scalar or vector metrics over a batch of traces
    # Must be deterministic for the same input

  promotion_decision(
    score: ScoreVector,
    baseline: ScoreVector,
    constraints_ok: bool
  ) -> Decision
    # Returns: promote | discard | branch | escalate
    # Implements promotion policy from problem-spec
```

### TraceSink

Append-only ledger for audit and improvement.

```
TraceSink:
  append(event: TraceEvent) -> void
    # Append a trace event (observation, action, shield cert, score)
    # Must be durable and ordered

  query(filters: TraceFilter) -> TraceEvent[]
    # Query historical traces for analysis
    # Used by EGRI loop and evaluator
```

## The LLM Never Calls Plant Directly

The runtime mediates all plant interactions:

```
LLM ──(θ_t)──▶ Controller/MetaController tools (strict schemas)
                       │
                   Runtime (trusted)
                       │
                  Plant.apply(safe_u_t)
```

This enforces: "agent gets only as much freedom as we can judge."

## Plant Types

### Physical plant (robotics, process control)
- State: continuous (positions, velocities, temperatures)
- Actions: continuous (torques, voltages, flow rates)
- Latency: hard real-time inner loop (ms), LLM at supervisory (seconds)
- Safety: CBF-QP shield mandatory

### Cyber-physical plant (cloud infra, IoT)
- State: mixed discrete/continuous (pod counts, latencies, error rates)
- Actions: discrete (scale up/down, restart, reroute)
- Latency: soft real-time (seconds-minutes)
- Safety: policy gates + SLO constraints

### Cyber plant (workflows, code, business processes)
- State: discrete (pipeline status, approval state, document versions)
- Actions: discrete (API calls, file edits, approvals)
- Latency: human-scale (seconds-hours)
- Safety: harness gates + rollback + EGRI evaluators

## Plant Configuration

Define in `.control/plant.yaml`:

```yaml
plant:
  name: "my-system"
  type: cyber  # physical | cyber-physical | cyber
  state:
    measured:
      - name: "build_status"
        type: "enum"
        values: ["passing", "failing", "unknown"]
      - name: "test_coverage"
        type: "float"
        bounds: [0.0, 1.0]
    estimated:
      - name: "code_quality_score"
        type: "float"
        bounds: [0.0, 1.0]
    context:
      - name: "active_branch"
        type: "string"
  actions:
    - name: "run_tests"
      type: "discrete"
      parameters: {}
    - name: "apply_fix"
      type: "discrete"
      parameters:
        file: "string"
        diff: "string"
  constraints:
    hard:
      - "test_coverage >= 0.70"
      - "no_security_vulnerabilities"
    soft:
      - "build_time_s <= 120"
  loop_rates:
    inner: null        # No inner loop for cyber plants
    supervisory: 30s   # LLM decision cadence
    improvement: 1h    # EGRI cycle
```
