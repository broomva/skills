---
tags:
  - broomva
  - control-kernel
  - architecture
  - security
type: spec
status: active
area: safety
created: 2026-03-17
---

# Safety Shields

Two distinct safety layers protect agent-controlled systems:
**pre-action safety** (policy gates) and **control-theoretic safety** (runtime shields).

## Layer 1: Policy Gates (Pre-Action Safety)

"Is this action allowed?" — checked before any actuation.

### Gate Types

| Gate | Severity | On violation |
|------|----------|-------------|
| **Hard gate** | blocking | Reject action, log, escalate |
| **Soft gate** | warning | Log warning, allow action |
| **Budget gate** | blocking | Halt if budget exhausted |
| **Approval gate** | blocking | Pause until human approves |

### Policy Gate Contract

```yaml
# .control/policy.yaml
gates:
  - id: "no-direct-plant-access"
    type: hard
    rule: "LLM tool calls must target Controller or MetaController, never Plant directly"
    measurement: "tool_call.target not in ['Plant.apply', 'Plant.reset']"

  - id: "action-budget"
    type: budget
    rule: "Max 50 control actions per EGRI trial"
    measurement: "trial_action_count <= 50"

  - id: "destructive-action-approval"
    type: approval
    rule: "Destructive actions require human confirmation"
    measurement: "action.destructive == false OR human_approved == true"
```

### Approval Policy Rules (from Symphony)

1. Approval must resolve or fail closed — never stall indefinitely
2. Timeout on approval → reject action + log
3. Sandbox mode: execute in isolation, promote only with approval
4. Default posture: fail-closed (deny if uncertain)

## Layer 2: Control-Theoretic Safety (Runtime Shields)

Ensure state remains in safe set S during runtime execution.

### CBF-QP Shield (Canonical Pattern)

Control Barrier Functions encode safety as barrier constraints.
A QP minimally modifies the nominal action while ensuring forward invariance:

```
u_safe = argmin_u ||u - u_proposed||²
         s.t.  ∂h/∂x · f(x,u) + α(h(x)) ≥ 0   (CBF constraint)
               u_min ≤ u ≤ u_max                   (actuation limits)
```

Where h(x) > 0 defines the safe set, α is a class-K function.

### Shield Integration Pattern

```
proposed_action = Controller.propose(belief, directive)
                        │
                        ▼
              SafetyShield.filter(proposed, belief)
                        │
               ┌────────┴────────┐
               │                 │
          feasible           infeasible
               │                 │
          safe_action      SafetyShield.fallback(belief)
               │                 │
               ▼                 ▼
          Plant.apply()    Plant.apply(emergency)
               │                 │
               ▼                 ▼
          log(nominal)     log(shield_intervention, severity=high)
```

### Shield Saturation Monitoring

Track `||u_safe - u_proposed||` over time:
- Low modification: controller is operating safely, shield is passive
- Rising modification: controller is pushing boundaries, investigate
- Sustained high modification: controller may be poorly tuned, trigger EGRI review
- Infeasibility: emergency fallback, halt, escalate

### Containment Invariants (from Symphony)

For any plant adapter, enforce workspace-style containment:

1. **Path containment**: all plant interactions scoped to declared namespace
2. **CWD validation**: verify execution context before any actuation
3. **Identifier sanitization**: plant/action IDs cleaned of injection vectors
4. **Hook safety**: before_action hooks can abort; after_action hooks are logged-only

## Failure Modes and Mitigations

| Failure | Symptom | Mitigation |
|---------|---------|-----------|
| Spec/constraint hallucination | LLM invents constraints or misreads units | JSON-schema strict outputs + policy gates + allowed-tools |
| Unsafe exploration | Aggressive identification experiments | EGRI budgets + CBF shield + sandbox mode |
| Latency spikes | Tool runtimes reject/queue requests | Multi-rate design + fallback controllers + backoff |
| Evaluator gaming | Agent exploits metric loopholes | Holdout scenarios + adversarial tests + immutable evaluator |
| Tool-call side effects | Destructive actions without approval | Approval gates + fail-closed policy |
| Shield infeasibility | No safe action exists | Emergency fallback + halt + human escalation |

## Combining Both Layers

```
LLM proposes action
  │
  ▼
Policy Gate Check (Layer 1)
  │
  ├─ DENIED → log + escalate
  │
  ▼ ALLOWED
Controller.propose()
  │
  ▼
CBF-QP Shield (Layer 2)
  │
  ├─ INFEASIBLE → fallback + escalate
  │
  ▼ FEASIBLE
Plant.apply(safe_action)
  │
  ▼
Trace logged with: proposed, safe, certificate, gate_results
```

Both layers are mandatory. Policy gates catch semantic/business constraint violations.
CBF-QP shields catch dynamic/physical constraint violations. Neither alone is sufficient.
