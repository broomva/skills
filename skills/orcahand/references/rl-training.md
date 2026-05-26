# RL Training

## Table of Contents
- Local Training (macOS)
- Remote GPU Setup
- Framework Choice
- Reward Design
- Curriculum Training
- Checkpointing

## Local Training (macOS)

Good for prototyping small policies. Apple Silicon MPS backend available for PyTorch.

```bash
pip install stable-baselines3 torch
```

```python
from stable_baselines3 import PPO
from orca_sim import OrcaHandRightCubeOrientation

env = OrcaHandRightCubeOrientation(version="v2", render_mode="rgb_array")
model = PPO("MlpPolicy", env, verbose=1, device="mps")  # or "cpu"
model.learn(total_timesteps=100_000)
model.save("checkpoints/grasp_policy_v1")
```

**Limitations**: CPU/MPS is 5-20x slower than GPU for training. Fine for <500K timesteps, use remote GPU for serious training.

## Remote GPU Setup

1. **Provision a GPU box** (Lambda, Vast.ai, RunPod, etc.) with CUDA + PyTorch
2. **Mirror the environment**:
   ```bash
   ssh gpu-box "pip install orca_sim stable-baselines3 torch"
   ```
3. **Start training**:
   ```bash
   ssh gpu-box "python train.py --timesteps 10_000_000 --device cuda"
   ```
4. **Sync checkpoints back**:
   ```bash
   rsync -av gpu-box:~/checkpoints/ ./checkpoints/
   ```

**Alternative**: Use a Jupyter notebook on Colab/Lambda for interactive development.

## Framework Choice

| Framework | Strengths | Best for |
|-----------|-----------|----------|
| Stable-Baselines3 | Quick start, well-tested PPO/SAC/TD3 | First experiments |
| CleanRL | Single-file implementations, transparent | Understanding algorithms |
| Custom PyTorch | Full control, custom architectures | Research |

**Recommended**: Start with SB3 PPO, move to CleanRL or custom if you need specific modifications.

## Reward Design

**CubeOrientation task** (built-in):
```python
# orca_sim/task_envs.py reward logic:
# reward = alignment_to_target + lift_bonus - drop_penalty
# terminated on: success (15° tolerance) or drop
```

**Custom grasp rewards** — design principles:
- **Alignment**: Reward reducing angle between current and target object pose
- **Stability**: Reward maintaining grasp over multiple timesteps
- **Efficiency**: Penalize energy (motor current) usage
- **Safety**: Large penalty for exceeding joint ROM or temperature limits

```python
def compute_reward(self):
    alignment = self._compute_alignment()    # 0-1
    stability = self._grasp_duration / 100   # 0-1
    energy = -0.01 * self._total_current     # penalty
    return alignment + 0.5 * stability + energy
```

## Curriculum Training

Progressive difficulty for complex manipulation tasks:

1. **Stage 1**: Large, easy-to-grasp objects (cube, sphere), wide success tolerance
2. **Stage 2**: Smaller objects, tighter tolerance, varied starting positions
3. **Stage 3**: In-hand manipulation (rotation, reorientation)
4. **Stage 4**: Domain randomization (friction, mass, motor delay)

Advance to next stage when success rate > 80% for 1000 episodes.

## Checkpointing

```python
# Save during training
model.save(f"checkpoints/grasp_policy_step_{step}")

# Load for evaluation
model = PPO.load("checkpoints/grasp_policy_v1")
obs, info = env.reset()
action, _ = model.predict(obs, deterministic=True)
```

**Best practice**: Save checkpoints every 100K steps. Keep the last 5 + the best-performing one.

**Evaluation**:
```python
from stable_baselines3.common.evaluation import evaluate_policy
mean_reward, std_reward = evaluate_policy(model, env, n_eval_episodes=100)
print(f"Success rate proxy: {mean_reward:.2f} +/- {std_reward:.2f}")
```
