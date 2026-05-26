# API Reference

## Table of Contents
- OrcaHand Class
- MockOrcaHand
- FastAPI REST Endpoints
- Joint Naming Convention
- Config File Schemas

## OrcaHand Class

Main controller class in `orca_core/core.py`:

```python
from orca_core import OrcaHand

hand = OrcaHand("orca_core/models/orcahand_v1_right")
```

### Connection
```python
hand.connect()                  # Open serial connection
hand.disconnect()               # Close serial connection
```

### Torque Control
```python
hand.enable_torque()            # Enable all motors
hand.disable_torque()           # Disable all motors (hand goes limp)
```

### Joint Control
```python
# Move specific joints (partial dict OK)
hand.set_joint_pos(
    {"index_mcp": 90, "middle_pip": 30},
    num_steps=25,       # interpolation steps (smoother = more steps)
    step_size=0.001     # seconds between steps
)

# Read current joint positions
positions = hand.get_joint_pos()  # Returns dict: {joint_name: degrees}
```

### Motor Telemetry
```python
motor_pos = hand.get_motor_pos()        # Raw Dynamixel positions
motor_cur = hand.get_motor_current()    # Current draw in mA
motor_tmp = hand.get_motor_temp()       # Temperature in celsius
```

### Calibration
```python
hand.calibrate()                # Run auto-calibration sequence
hand.set_neutral_position()     # Move to neutral (open hand)
hand.set_zero_position()        # Move to zero position
```

### Control Mode
```python
hand.set_control_mode("position")              # Pure position control
hand.set_control_mode("current_based_position") # Recommended: position + current limit
hand.set_max_current(200)                       # Set current limit in mA
```

## MockOrcaHand

For testing without hardware:
```python
from orca_core import MockOrcaHand

hand = MockOrcaHand("orca_core/models/orcahand_v1_right")
hand.connect()  # No serial required
hand.set_joint_pos({"thumb_mcp": 45})  # Simulated, no hardware
```

Same API as OrcaHand. Useful for unit tests and CI.

## FastAPI REST Endpoints

Start server: `python -m orca_core.api.api` (port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/connect` | Open serial connection |
| POST | `/disconnect` | Close connection |
| GET | `/status` | Connection + torque status |
| POST | `/torque/enable` | Enable torque |
| POST | `/torque/disable` | Disable torque |
| GET | `/joints/position` | Get all joint positions |
| POST | `/joints/position` | Set joint positions (JSON body: `{joint_targets, num_steps, step_size}`) |
| GET | `/motors/position` | Get raw motor positions |
| POST | `/calibrate` | Run calibration |

## Joint Naming Convention

Format: `{finger}_{joint_type}`

| Finger | Joints | Total |
|--------|--------|-------|
| thumb | mcp, abd, pip, dip | 4 |
| index | abd, mcp, pip | 3 |
| middle | abd, mcp, pip | 3 |
| ring | abd, mcp, pip | 3 |
| pinky | abd, mcp, pip | 3 |
| wrist | (single joint) | 1 |
| **Total** | | **17** |

Joint types:
- **mcp**: Metacarpophalangeal (knuckle)
- **pip**: Proximal interphalangeal (first bend)
- **dip**: Distal interphalangeal (fingertip bend, thumb only)
- **abd**: Abduction (side-to-side spread)

## Config File Schemas

### `config.yaml` (per model)
Primary configuration. Contains: `baudrate`, `port`, `max_current`, `control_mode`, `motor_ids` (17), `joint_ids` (17), `joint_to_motor_map` (with sign for tendon inversion), `joint_roms`, `neutral_position`, `calibration_sequence`.

### `calibration.yaml` (per model)
Written by `calibrate.py`. Contains: `calibrated` (bool), `timestamp`, `motor_limits`, `joint_to_motor_ratios`.

### `hand_scheme.yaml` (retargeter)
Kinematic structure. Contains: `gc_tendons`, `finger_to_tip`, `finger_to_base`, `gc_limits_lower`, `gc_limits_upper`, `wrist_name`.

### `retargeter.yaml` (retargeter)
Optimization tuning. Contains: `lr`, `use_scalar_distance_palm`, `loss_coeffs`, `mano_adjustments`, `joint_regularizers`.
