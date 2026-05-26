# EGRI Controller Improvement Loop

## Table of Contents
- EGRI Overview for OrcaHand
- Problem-Spec Template
- Evaluator Design
- Promotion Policy
- Integration with autoany
- Running an EGRI Cycle

## EGRI Overview for OrcaHand

EGRI (Evaluator-Governed Recursive Improvement) applied to the OrcaHand:

```
Problem-spec → Train in sim (remote GPU) → Evaluate (sim metrics)
                     ↑                            ↓
              Update artifact              Gate: pass/fail?
                     ↑                            ↓
              Rollback if failed     Deploy to physical (human approval)
                                            ↓
                                     Evaluate (real metrics)
                                            ↓
                                     Update sim-to-real gap
```

**Mutable artifacts** (what EGRI improves):
- RL policy weights (`.pt` files)
- Retargeter configuration (`retargeter.yaml` loss_coeffs, lr, mano_adjustments)
- Grasp primitive parameters (pre-defined joint angle sequences)

## Problem-Spec Template

Use `assets/templates/problem-spec.orcahand.yaml` as your starting point. Key sections to customize:

- **objective.metric**: What you're optimizing (grasp_success_rate, reorientation_accuracy, grasp_stability_duration)
- **objective.target**: Threshold for success (0.85 = 85%)
- **artifacts**: Which files the EGRI loop can modify
- **evaluator.outputs**: Metrics to compute and their thresholds
- **execution.budget**: Time and compute limits

## Evaluator Design

**Sim evaluator** (runs on every iteration):
```python
def evaluate_sim(policy, env, n_episodes=100):
    successes = 0
    for _ in range(n_episodes):
        obs, info = env.reset()
        done = False
        while not done:
            action, _ = policy.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
        if info.get("success", False):
            successes += 1
    return {"sim_success_rate": successes / n_episodes}
```

**Real evaluator** (runs only after sim gate passes):
```python
def evaluate_real(policy, hand, n_grasps=20):
    # Requires human supervision
    successes = 0
    for i in range(n_grasps):
        print(f"Trial {i+1}/{n_grasps} — place object and press Enter")
        input()
        # Execute policy...
        result = input("Success? (y/n): ")
        if result.lower() == "y":
            successes += 1
    return {"real_success_rate": successes / n_grasps}
```

**Composite evaluator**:
```python
def evaluate(sim_results, real_results):
    gap = abs(sim_results["sim_success_rate"] - real_results["real_success_rate"])
    return {
        "sim_success_rate": sim_results["sim_success_rate"],
        "real_success_rate": real_results["real_success_rate"],
        "sim_to_real_gap": gap,
        "promoted": sim_results["sim_success_rate"] > 0.85 and gap < 0.15,
    }
```

## Promotion Policy

```
IF sim_success_rate > 0.85:
    → Request human approval for physical trial
    IF human_approved:
        → Run real evaluator (20 grasps, supervised)
        IF sim_to_real_gap < 0.15:
            → PROMOTE: save as production policy
        ELSE:
            → ROLLBACK: revert to previous checkpoint
            → Increase domain randomization, re-train
    ELSE:
        → HOLD: keep training in sim
ELSE:
    → CONTINUE: more training iterations
```

**Human-in-the-loop**: Physical deployment always requires human approval. This is enforced by the `approval: manual` field in the problem-spec.

## Integration with autoany

Wire into the existing autoany EGRI harness:

```bash
# From the autoany workspace
autoany egri run --problem-spec path/to/problem-spec.orcahand.yaml
```

The autoany harness handles:
- Iteration management (train → evaluate → decide)
- Artifact versioning (checkpoint management)
- Ledger persistence (via Lago)
- Budget enforcement (max_trials, max_hours)

## Running an EGRI Cycle

1. **Setup**: Copy problem-spec template, customize objective and budget
2. **Train**: `python train.py --config problem-spec.orcahand.yaml`
3. **Evaluate (sim)**: Automatic after training completes
4. **Gate check**: Script reports pass/fail
5. **Deploy (if passed)**: Human approves, run real-world trials
6. **Record**: All results logged to Lago trace entries
7. **Iterate**: Adjust hyperparameters, domain randomization, re-run
