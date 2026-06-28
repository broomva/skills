---
tags:
  - broomva
  - control-kernel
  - architecture
  - security
type: reference
status: active
area: safety
created: 2026-03-17
---

# Failure Modes

Catalog of failure modes when LLMs participate in control systems,
with mitigations grounded in the control kernel architecture.

## Specification Failures

### Spec/Constraint Hallucination
- **Symptom**: LLM invents constraints, misreads units, or forgets invariants
- **Mitigation**: JSON-schema structured outputs + strict tool schemas + policy gates
- **Detection**: Schema validation failures, constraint mismatch with plant.yaml
- **Recovery**: Reject directive, request re-generation with explicit constraint list

### Goal Drift
- **Symptom**: LLM gradually shifts objectives away from original setpoints
- **Mitigation**: Setpoints are immutable within a session; changes require explicit approval
- **Detection**: Compare current directives against original setpoint catalog
- **Recovery**: Reset to baseline setpoints, log drift event

## Exploration Failures

### Unsafe Probing
- **Symptom**: LLM runs aggressive identification experiments that stress the plant
- **Mitigation**: EGRI budgets + hard constraints + CBF shield + sandbox mode
- **Detection**: Shield intervention rate spike, constraint violations during exploration
- **Recovery**: Halt experiment, revert to safe operating point

### Evaluator Gaming
- **Symptom**: Agent exploits metric loopholes, score improves but quality degrades
- **Mitigation**: Holdout scenario sets, adversarial tests, immutable evaluator
- **Detection**: Performance on holdout diverges from training scenarios
- **Recovery**: Halt EGRI loop, expand evaluator, add adversarial scenarios

## Runtime Failures

### Latency Spikes
- **Symptom**: Tool runtimes reject/queue requests, bounded queues overflow
- **Mitigation**: Multi-rate design, fallback controllers, exponential backoff
- **Detection**: Response time exceeds turn_timeout, queue depth alerts
- **Recovery**: Activate fallback controller, wait for backoff, resume

### Shield Infeasibility
- **Symptom**: CBF-QP has no feasible solution — no safe action exists
- **Mitigation**: Emergency fallback action (always feasible by design)
- **Detection**: Solver returns infeasible status
- **Recovery**: Execute fallback, halt normal operation, escalate immediately

### Model Mismatch
- **Symptom**: World model predictions diverge from observations
- **Mitigation**: Drift detection monitors, robust/DRO formulations
- **Detection**: Prediction error exceeds threshold over sliding window
- **Recovery**: Widen uncertainty bounds, trigger model retraining, use conservative controller

## Orchestration Failures

### Worker Stall
- **Symptom**: Agent subprocess stops producing output
- **Mitigation**: Stall detection timeout, forced kill + retry
- **Detection**: No protocol message within stall_timeout_ms
- **Recovery**: Kill worker, schedule retry with backoff

### Workspace Escape
- **Symptom**: Agent attempts to access files outside workspace root
- **Mitigation**: Path containment invariant (canonicalize + starts_with check)
- **Detection**: Path validation failure
- **Recovery**: Reject operation, log security event, terminate worker

### Destructive Side Effects
- **Symptom**: Agent executes destructive actions without approval
- **Mitigation**: Approval gates, fail-closed policy, sandbox posture
- **Detection**: Action classification + policy gate check
- **Recovery**: Block action, require explicit human approval

## Improvement Loop Failures

### Budget Exhaustion Without Progress
- **Symptom**: EGRI loop consumes budget with no improvement
- **Mitigation**: Early stopping triggers, budget allocation monitoring
- **Detection**: Budget > 75% consumed with no promotion
- **Recovery**: Halt loop, analyze ledger, adjust mutation strategy or surface

### Regression After Promotion
- **Symptom**: Promoted controller performs worse in deployment than in evaluation
- **Mitigation**: Rollback to last known-good, expand scenario library
- **Detection**: Online metrics degrade after deployment
- **Recovery**: Immediate rollback, add deployment scenario to evaluator

### Evaluator Noise
- **Symptom**: Promoted states oscillate, no stable improvement
- **Mitigation**: Increase evaluation samples, use paired comparisons
- **Detection**: Promotion/rollback frequency exceeds threshold
- **Recovery**: Strengthen evaluator (more samples, statistical tests)

## Severity Classification

| Severity | Response time | Examples |
|----------|--------------|---------|
| **Critical** | Immediate (automated) | Shield infeasibility, workspace escape |
| **High** | Seconds (automated + alert) | Constraint violation, stall detection |
| **Medium** | Minutes (human review) | Evaluator gaming, model mismatch |
| **Low** | Hours (logged) | Budget warnings, drift indicators |
