---
tags:
  - broomva
  - control-kernel
  - architecture
type: spec
status: active
area: world-model
created: 2026-03-17
---

# World Models

Learned dynamics, digital twins, and data-driven prediction methods
that serve as the "plant model" for MPC-style controllers.

## Koopman Methods

Lift nonlinear dynamics into higher-dimensional observable space where
linear predictors enable efficient MPC.

### Agent Integration
- **Artifact**: Koopman lift function (EDMD variants) — updatable via EGRI
- **Controller**: Koopman-MPC using lifted linear system
- **LLM role**: Decide when to relearn lifts, curate datasets, interpret
  model mismatch indicators, pick robust strategies
- **Verification**: Error bounds on approximation, closed-loop stability checks

### When to Use
- System has underlying structure that linearizes in lifted coordinates
- Computational budget allows offline lift learning
- Need fast online MPC (linear system → fast QP)

## Data-Driven MPC / DeePC

Uses input/output trajectory data (Hankel matrices) for prediction and
optimization without an explicit parametric model.

### Agent Integration
- **Harness**: Dataset store + experiment runner (collect trajectories)
- **Controller**: DeePC optimizer (QP/convex program) as a tool
- **LLM role**: Choose excitation experiments, select horizons/regularization,
  interpret results, update constraints
- **Safety**: Wrap DeePC output with CBF-QP shield or robust constraint tightening

### Robust DeePC
Regularized and distributionally robust formulations interpret regularization
as DRO and provide probabilistic robustness guarantees. Use when data is noisy
or distribution shifts are expected.

## Digital Twins

Real-time virtual replicas supporting monitoring, simulation, prediction, optimization.

### Agent Integration
- **Role**: Provides the harness for safe experimentation and scenario evaluation
- **EGRI integration**: Twin is the execution backend for controller improvement trials
- **LLM role**: Orchestrate simulation experiments, interpret mismatches between
  twin predictions and real plant observations
- **Calibration**: Twin validity metrics are a first-class evaluator input

### Digital Twin as EGRI Backend

```yaml
# In problem-spec.yaml
execution:
  backend: simulator
  command: "python3 twin/run_scenario.py --config {{scenario}}"
  timeout_s: 60
  sandbox: true  # Twin runs are inherently sandboxed
```

## Learned Dynamics (Neural, GP, etc.)

Model-based approaches that learn environment models from data.

### Agent Integration
- **Artifact**: Model weights/parameters — improved via EGRI loops
- **Controller**: Model-based MPC using learned predictions
- **LLM role**: Select model architectures, design training harnesses,
  interpret training curves, gate deployment
- **Safety**: Prediction uncertainty estimates feed into robust MPC constraints

## Method Selection Guide

| Scenario | Recommended | Reasoning |
|----------|-------------|-----------|
| Linear/weakly nonlinear, fast MPC needed | Koopman + MPC | Fast QP solves, good approximation |
| No parametric model, good data available | DeePC | Model-free, direct from data |
| Complex nonlinear, simulation available | Digital twin + EGRI | Safe offline optimization |
| Distribution shift expected | Robust DeePC or DRO-MPC | Built-in robustness guarantees |
| Cyber plant (code/workflows) | Learned heuristics + EGRI | LLM curates, evaluator judges |
