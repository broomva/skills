# Dependency Graph

## Table of Contents
- Repo Relationships
- Version Matrix
- Install Order
- Python Requirements
- Known Conflicts

## Repo Relationships

```
                    orcahand_description
                    (URDF/MJCF models)
                   /         |          \
                  /          |           \
            orca_sim    orca_retargeter   rwr_system
         (Gymnasium     (Teleoperation    (ROS2 pipeline)
          + MuJoCo)      retargeting)
              |              |                |
              v              v                v
          [RL training]  [Human input]    [Deployment]
                          (AVP/Rokoko)
                              |
                              v
                         orca_core
                     (Hardware control)
                              |
                              v
                    [Physical ORCA Hand]
```

## Version Matrix

| Repo | Latest | Python | Key Dependencies |
|------|--------|--------|------------------|
| orcahand_description | main | N/A | mujoco (viewing only) |
| orca_core | 0.2.1 | 3.10+ | dynamixel-sdk >=3.7.31, fastapi, numpy >=2 |
| orca_sim | 0.1.0 | 3.10+ | gymnasium >=0.29, mujoco >=3.1, numpy >=1.26 |
| orca_retargeter | 0.1.0 | 3.10+ | torch ==2.2.0, pytorch-kinematics >=0.7.5, numpy <2 |
| rwr_system | 0.1.0 | 3.10+ | ROS2, colcon, h5py, depthai, mediapipe |

## Install Order

Must be installed in dependency order:

1. **orcahand_description** — no deps, just `git clone`
2. **orca_sim** — depends on orcahand_description for MJCF models
3. **orca_core** — independent, but install after sim for testing
4. **orca_retargeter** — depends on orcahand_description for URDF
5. **rwr_system** — depends on ROS2, optional

Use `scripts/orcahand_init.py` to automate this.

## Python Requirements

- **Python 3.10+** (all repos)
- **MuJoCo**: `pip install mujoco` (3.1+)
- **PyTorch**: 2.2.0 specifically for orca_retargeter
- **ROS2**: Required only for rwr_system (Humble or newer)

## Known Conflicts

### numpy version conflict
- `orca_core` requires `numpy >=2.2.6`
- `orca_retargeter` requires `numpy <2`
- **Resolution**: Use separate virtual environments, or install in a single env with `numpy==1.26.4` (works for both with a warning from orca_core)

### torch version pinning
- `orca_retargeter` pins `torch ==2.2.0`
- If you need a newer torch for training, use a separate venv for training vs retargeting

### Recommended setup
```bash
# Option A: Single venv (some version warnings)
python -m venv .venv && source .venv/bin/activate
pip install numpy==1.26.4  # compromise version
pip install -e orca_core/ -e orca_sim/

# Option B: Separate venvs (cleaner, recommended)
python -m venv .venv-sim && .venv-sim/bin/pip install -e orca_sim/
python -m venv .venv-core && .venv-core/bin/pip install -e orca_core/
python -m venv .venv-retarget && .venv-retarget/bin/pip install -e orca_retargeter/
```
