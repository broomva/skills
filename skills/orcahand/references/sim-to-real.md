# Sim-to-Real Transfer

## Table of Contents
- Joint Reordering Map
- Domain Randomization
- Action Scaling
- Validation Protocol
- Common Failure Modes
- Zero-Shot vs Fine-Tuned

## Joint Reordering Map

Simulation joint ordering differs from physical motor ordering. Apply this map when deploying sim-trained policies to real hardware:

```python
# Sim index → Real index (from rwr_system)
SIM_TO_REAL = [0, 13, 14, 15, 16, 10, 11, 12, 4, 5, 6, 1, 2, 3, 7, 8, 9]

def reorder_sim_to_real(sim_actions):
    """Reorder action vector from sim ordering to real motor ordering."""
    return [sim_actions[i] for i in SIM_TO_REAL]
```

**Why they differ**: Simulation models joints by kinematic chain (thumb → index → middle → ring → pinky), while the physical motor IDs follow the wiring daisy-chain topology.

## Domain Randomization

Randomize these parameters during training to improve transfer robustness:

| Parameter | Sim Default | Randomization Range | Why |
|-----------|-------------|-------------------|-----|
| Joint friction | 0.01 | [0.005, 0.05] | Real tendons have variable friction |
| Tendon stiffness | 100 | [50, 200] | Tendon tension varies with age |
| Motor delay | 0ms | [0, 20ms] | Serial bus latency |
| Observation noise | 0 | N(0, 0.5°) | Encoder quantization |
| Object mass | varies | [0.5x, 2x] | Grasp diverse objects |
| Object friction | 1.0 | [0.3, 1.5] | Surface variability |

Apply in your training script:
```python
# Randomize at episode reset
env.model.geom_friction[:] *= np.random.uniform(0.5, 1.5)
env.model.dof_damping[:] *= np.random.uniform(0.5, 2.0)
```

## Action Scaling

Simulation actions are in actuator control range. Convert to degrees for `OrcaHand.set_joint_pos()`:

```python
def sim_action_to_degrees(action, joint_roms):
    """Scale normalized [-1, 1] action to joint ROM in degrees."""
    degrees = {}
    for i, (joint, (lo, hi)) in enumerate(joint_roms.items()):
        degrees[joint] = lo + (action[i] + 1) / 2 * (hi - lo)
    return degrees
```

## Validation Protocol

Before deploying a sim-trained policy to physical hardware:

1. **Sim evaluation** (automated):
   - Run 100 episodes in sim with deterministic policy
   - Record success rate, average reward, episode length
   - Threshold: success rate > 85%

2. **Supervised real evaluation** (human present):
   - Run 20 grasps on physical hand
   - Human monitors for anomalies (servo overheating, tendon issues)
   - Record success rate, compare to sim

3. **Gap metric**:
   ```
   sim_to_real_gap = abs(sim_success_rate - real_success_rate)
   ```
   - Gap < 15%: deploy
   - Gap 15-30%: more domain randomization needed
   - Gap > 30%: fundamental sim-real mismatch, investigate

## Common Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Policy works in sim, fails on real | Insufficient domain randomization | Increase friction/mass randomization |
| Fingers overshoot on real hand | Action scaling mismatch | Check joint ROM mapping, reduce step_size |
| Grasp unstable on real hand | Tendon friction not modeled | Add tendon damping to sim, re-train |
| Servo overheating during policy | Policy uses too much current | Add energy penalty to reward, reduce max_current |
| Policy ignores certain fingers | Training reward doesn't penalize | Add per-finger activity regularization |

## Zero-Shot vs Fine-Tuned

**Zero-shot**: Train only in sim with heavy domain randomization. Directly deploy to real. Simpler pipeline, works for robust policies.

**Fine-tuned**: Train in sim, then collect real-world episodes and fine-tune. Better performance, requires data collection infrastructure (rwr_system).

**Recommendation**: Start zero-shot. Only fine-tune if the sim-to-real gap exceeds 15% after thorough domain randomization.
