# CaP-RL Training Guide

GRPO (Group Relative Policy Optimization) applied to code-generating LLMs for robot manipulation.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Training Configuration](#training-configuration)
4. [Training Recipe](#training-recipe)
5. [Evaluation](#evaluation)
6. [Sim-to-Real Transfer](#sim-to-real-transfer)
7. [Troubleshooting](#troubleshooting)

---

## Overview

CaP-RL treats robot manipulation as a code generation RL problem:
- **State**: Task prompt + perception API context
- **Action**: Generated Python code
- **Reward**: Binary task success from physics simulation (RLVR — RL with Verifiable Rewards)

The agent learns to write better robot control code through trial-and-error in simulation.

## Prerequisites

- CUDA GPU: H100 (recommended), A100, or RTX 4090
- Python 3.12+
- vLLM for local model serving
- W&B account for experiment tracking
- Base model: `Qwen/Qwen2.5-Coder-7B-Instruct` (default)

```bash
pip install vllm wandb transformers[torch]
```

## Training Configuration

### GRPO Hyperparameters

```python
GRPO_CONFIG = {
    "group_size": 15,           # Rollouts per prompt
    "train_dataset_size": 256,  # Prompts per iteration
    "train_temperature": 1.0,   # Sampling temperature during training
    "learning_rate": 1e-6,
    "kl_coeff": 0.01,           # KL penalty coefficient
    "clip_range": 0.2,          # PPO-style clipping
    "num_iterations": 50,       # Total training iterations
    "eval_interval": 5,         # Evaluate every N iterations
    "eval_trials": 100,         # Trials per evaluation
}
```

### Task-Specific Settings

| Task | Max Code Length | Max Steps | Reward |
|------|----------------|-----------|--------|
| Cube Lift | 512 tokens | 5 | Binary: cube z > threshold |
| Cube Stack | 1024 tokens | 10 | Binary: cube_a on cube_b |
| Spill Wipe | 1024 tokens | 15 | Continuous: % area cleaned |

### Tier Selection

Train on **S1 (Privileged)** for stable convergence:
- Ground-truth object positions (no perception noise)
- High-level control API
- Clean reward signal

Transfer to S2 (noisy perception) and real world after training.

## Training Recipe

### Step 1: Prepare Environment

```bash
# Start simulation environment
python -m capx.envs.robosuite.server --task cube_lift --port 8200

# Start vLLM model server
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B-Instruct \
  --port 8300 \
  --max-model-len 4096
```

### Step 2: Run Training

```bash
python scripts/train_rl.py \
  --task cube_lift \
  --base_model Qwen/Qwen2.5-Coder-7B-Instruct \
  --tier S1 \
  --group_size 15 \
  --train_iterations 50 \
  --wandb_project capx-rl \
  --output_dir checkpoints/cube_lift_rl/
```

### Step 3: Monitor

Track in W&B:
- `train/reward_mean` — Should increase steadily
- `train/code_compile_rate` — Should approach 95%+
- `train/kl_divergence` — Should stay < 5.0
- `eval/success_rate` — Primary metric

### Step 4: Evaluate

```bash
python scripts/eval.py \
  --task cube_lift \
  --model checkpoints/cube_lift_rl/iter_50/ \
  --tier S2 \
  --num_trials 100
```

## Sim-to-Real Transfer

The RL-trained model transfers zero-shot because:
1. Reasoning is over **abstract API calls**, not raw pixels or joint angles
2. The same perception services (SAM3, Molmo) run on real hardware
3. IK solvers handle the low-level motion planning

### Real-World Evaluation

```bash
# Start perception services on the real robot's compute
bash scripts/setup-perception.sh

# Run trained model on real Franka
python scripts/eval_real.py \
  --task cube_lift \
  --model checkpoints/cube_lift_rl/iter_50/ \
  --robot franka \
  --camera zed \
  --num_trials 20
```

## Troubleshooting

**Code compilation rate stays low (<50%)**:
- Reduce `train_temperature` to 0.7
- Increase `group_size` to 20 for more diverse samples
- Check that API documentation is properly formatted in the prompt

**Reward stays flat**:
- Verify simulation environment is running (`curl localhost:8200/health`)
- Check that reward function returns correct values (log a few manually)
- Try training on an easier task first (cube_lift before cube_stack)

**KL divergence explodes**:
- Reduce `learning_rate` to 5e-7
- Increase `kl_coeff` to 0.05
- Restart from a recent checkpoint

**OOM on GPU**:
- Reduce `group_size` (minimum viable: 8)
- Use gradient checkpointing: `--gradient_checkpointing`
- Offload optimizer states: `--offload_optimizer`
