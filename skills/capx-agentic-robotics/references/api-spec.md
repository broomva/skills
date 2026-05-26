# CaP-X API Specification

## Table of Contents

1. [Perception APIs](#perception-apis)
2. [Control APIs](#control-apis)
3. [API Abstraction Levels](#api-abstraction-levels)
4. [Gymnasium Interface](#gymnasium-interface)
5. [Skill Library Format](#skill-library-format)

---

## Perception APIs

All perception modules run as HTTP microservices. Standard request/response pattern.

### SAM3 Segmentation (port 8114)

Language-conditioned segmentation. Given a text query, return pixel masks.

```python
# Agent code calls:
masks = perception.segment("red cube")
# Returns: list of binary masks with confidence scores
# Each mask: {"mask": np.ndarray, "score": float, "bbox": [x1, y1, x2, y2]}
```

### Molmo 2 Pointing (port 8117)

Open-vocabulary pointing. Given a text query, return 2D pixel coordinates.

```python
points = perception.point("handle of the mug")
# Returns: list of (x, y) pixel coordinates with confidence
```

### ContactGraspNet (port 8115)

6-DOF grasp planning from point clouds.

```python
grasps = perception.plan_grasps(point_cloud, target_mask=mask)
# Returns: list of SE(3) grasp poses ranked by predicted success
# Each: {"position": [x,y,z], "quaternion": [w,x,y,z], "score": float, "width": float}
```

### OWL-ViT Detection (port 8118)

Open-vocabulary object detection.

```python
detections = perception.detect(["red cube", "green platform", "robot gripper"])
# Returns: list of {"label": str, "bbox": [x1,y1,x2,y2], "score": float}
```

### Depth and Point Clouds

```python
depth_map = perception.get_depth()          # H x W float32 in meters
point_cloud = perception.get_point_cloud()  # N x 3 float32 in world frame
rgb = perception.get_rgb()                  # H x W x 3 uint8
```

---

## Control APIs

### Core Interface (all robots)

Every robot control API implements:

```python
class RobotControlApi:
    def goto_pose(self, position: list[float], quaternion: list[float],
                  speed: float = 0.5) -> bool:
        """Move end-effector to target pose via IK. Returns success."""

    def grasp(self) -> bool:
        """Close gripper with force control. Returns success."""

    def open_gripper(self) -> bool:
        """Open gripper fully."""

    def close_gripper(self) -> bool:
        """Close gripper (no force feedback)."""

    def get_ee_pose(self) -> dict:
        """Return {"position": [x,y,z], "quaternion": [w,x,y,z]}."""

    def get_joint_positions(self) -> list[float]:
        """Return current joint angles in radians."""

    def goto_joints(self, joints: list[float], speed: float = 0.5) -> bool:
        """Move to target joint configuration."""

    def get_gripper_state(self) -> dict:
        """Return {"width": float, "is_grasping": bool}."""
```

### Franka-Specific Extensions

```python
class FrankaControlApi(RobotControlApi):
    def goto_pose(self, position, quaternion, speed=0.5,
                  return_bbox_extent=False) -> bool | dict:
        """Extended: if return_bbox_extent=True, also return object bbox for verification."""

    def get_workspace_bounds(self) -> dict:
        """Return {"min": [x,y,z], "max": [x,y,z]} of reachable workspace."""
```

### R1Pro Humanoid Extensions

```python
class R1ProControlApi(RobotControlApi):
    def navigate_to(self, x: float, y: float, theta: float) -> bool:
        """Drive wheeled base to target position and heading."""

    def get_base_pose(self) -> dict:
        """Return {"x": float, "y": float, "theta": float}."""

    # Left and right arm control
    def goto_pose_left(self, position, quaternion) -> bool: ...
    def goto_pose_right(self, position, quaternion) -> bool: ...
```

---

## API Abstraction Levels

Each level progressively removes human-designed priors:

| Level | Perception | Control | Examples | Skill Library |
|-------|-----------|---------|----------|--------------|
| `ControlApi` | Full stack | High-level IK | Yes | No |
| `ControlPrivilegedApi` | Ground-truth state | High-level IK | Yes | No |
| `ControlReducedApi` | Full stack | Low-level | No | No |
| `ControlReducedExamplelessApi` | Full stack | Low-level | No | No |
| `ControlReducedSkillLibraryApi` | Full stack | Low-level | No | Yes |

Lower abstraction = harder for LLM but more generalizable. CaP-RL trains on `PrivilegedApi` (S1) for stable rewards, transfers to `ControlApi` (S2) and real world.

---

## Gymnasium Interface

CaP-Gym wraps all tasks as standard Gymnasium environments:

```python
import gymnasium as gym

env = gym.make("capx/CubeLift-v0", render_mode="rgb_array")
obs, info = env.reset()

# Agent generates code string
code = llm.generate(prompt=env.get_task_prompt(), context=obs)

# Execute generated code
result = env.step(code)
# result: (obs, reward, terminated, truncated, info)
# reward: float in [0, 1] — verifiable environment reward
# info: {"code_compiled": bool, "execution_error": str|None, "skill_trace": list}
```

### Task Registration

```python
from capx.envs import register_task

@register_task("my_suite/my_task")
class MyTask:
    metadata = {
        "robot": "franka",
        "perception": ["sam3", "depth"],
        "control_api": "FrankaControlApi",
        "max_steps": 10,
        "reward_type": "sparse",  # or "dense"
    }
```

---

## Skill Library Format

Auto-synthesized skills are Python functions with metadata:

```python
# skills/rotation_utils.py
"""Auto-synthesized from successful traces on cube_lift, cube_stack."""

def rotation_matrix_to_quaternion(R: np.ndarray) -> np.ndarray:
    """Convert 3x3 rotation matrix to [w, x, y, z] quaternion."""
    # ... implementation ...

def filter_grasps_by_approach(grasps: list, approach_dir: np.ndarray,
                               threshold: float = 0.8) -> list:
    """Filter grasp candidates by approach direction alignment."""
    # ... implementation ...

# Metadata for library management
__skill_meta__ = {
    "source_tasks": ["cube_lift", "cube_stack"],
    "success_rate_contribution": 0.12,  # avg improvement when included
    "discovered_iteration": 23,
    "hash": "sha256:a1b2c3...",
}
```

Compile new skills from evaluation traces:

```bash
python scripts/skill_library_compilation/compile.py \
  --eval_outputs results/ \
  --output skills/ \
  --min_reuse_count 3 \
  --min_success_contribution 0.05
```
