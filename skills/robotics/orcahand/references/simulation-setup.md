# Simulation Setup

## Table of Contents
- Installation
- MuJoCo on macOS (Apple Silicon)
- Environment Catalog
- Custom Environments
- Version Pinning
- Headless Rendering

## Installation

```bash
# From PyPI (stable)
pip install orca_sim

# From source (dev)
git clone https://github.com/orcahand/orca_sim.git
cd orca_sim && pip install -e .
```

Dependencies: `gymnasium >=0.29`, `mujoco >=3.1`, `numpy >=1.26`.

## MuJoCo on macOS (Apple Silicon)

MuJoCo runs natively on Apple Silicon. For interactive rendering (`render_mode="human"`), use `mjpython`:

```bash
pip install mujoco
# Interactive viewer requires mjpython on macOS:
mjpython your_script.py
```

For headless rendering (`render_mode="rgb_array"`), regular `python` works fine.

**Visualize hand model directly**:
```bash
python -m mujoco.viewer --mjcf=$(pwd)/orcahand_description/v2/scene_combined.xml
```

## Environment Catalog

All environments registered as Gymnasium envs. Default version: `v2`.

| Environment | DoF | Description |
|------------|-----|-------------|
| `OrcaHandRight` | 17 | Right hand, no objects |
| `OrcaHandLeft` | 17 | Left hand, no objects |
| `OrcaHandCombined` | 34 | Both hands |
| `OrcaHandRightExtended` | 17 | Right + camera mount, U2D2, fans |
| `OrcaHandLeftExtended` | 17 | Left extended |
| `OrcaHandCombinedExtended` | 34 | Both extended |
| `OrcaHandRightCubeOrientation` | 17 | Task: reorient cube red-face-up |

**Basic usage**:
```python
from orca_sim import OrcaHandRight

env = OrcaHandRight(version="v2", render_mode="human")
obs, info = env.reset(seed=42)

for _ in range(1000):
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        obs, info = env.reset()

env.close()
```

**Observation space**: `[qpos, qvel]` — joint positions and velocities.
**Action space**: Actuator control range (continuous).
**Frame skip**: 5 physics steps per env step.

## Custom Environments

Subclass `BaseOrcaHandEnv` to create task-specific environments:

```python
from orca_sim.envs import BaseOrcaHandEnv

class MyGraspEnv(BaseOrcaHandEnv):
    def __init__(self, **kwargs):
        super().__init__(hand="right", version="v2", **kwargs)

    def _get_reward(self):
        # Define your reward function
        return 0.0

    def _get_terminated(self):
        # Define termination conditions
        return False
```

Add objects by modifying the MJCF XML or using MuJoCo's runtime API.

## Version Pinning

```python
# Use v1 models (legacy)
env = OrcaHandRight(version="v1")

# Use v2 models (default, recommended)
env = OrcaHandRight(version="v2")

# Check available versions
from orca_sim.versions import list_versions, latest_version
print(list_versions())   # ["v1", "v2"]
print(latest_version())  # "v2"
```

## Headless Rendering

For recording videos or remote servers:
```python
env = OrcaHandRight(render_mode="rgb_array")
obs, info = env.reset()
frame = env.render()  # returns numpy array (H, W, 3)
```

Combine with `imageio` or `cv2` for video recording.
