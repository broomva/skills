# Calibration Pipeline

## Table of Contents
- Serial Port Detection
- 3-Step Pipeline
- config.yaml Schema
- calibration.yaml Output
- When to Re-Calibrate
- Troubleshooting

## Serial Port Detection

```bash
# macOS
ls /dev/tty.usbserial-*

# Linux
ls /dev/ttyUSB*
```

The U2D2 adapter uses FTDI VID `0x0403`. If multiple serial devices, check with:
```bash
# macOS
system_profiler SPUSBDataType | grep -A5 "U2D2"
```

Update `config.yaml` with the detected port path.

## 3-Step Pipeline

Run from the `orca_core/` directory. Each script takes the model path as argument.

### Step 1: Tension Tendons
```bash
python scripts/tension.py orca_core/models/orcahand_v1_right
```
Applies light current to each motor to take up tendon slack. Hold the hand steady during this step.

### Step 2: Auto-Calibrate
```bash
python scripts/calibrate.py orca_core/models/orcahand_v1_right
```
Runs a 28-step flex/extend sequence across all joints. Records motor positions at extreme positions to compute `joint_to_motor_ratios`. Writes results to `calibration.yaml`.

**Important**: The hand will move through its full range of motion. Ensure nothing is blocking the fingers.

### Step 3: Move to Neutral
```bash
python scripts/neutral.py orca_core/models/orcahand_v1_right
```
Moves all joints to the neutral (open hand) position defined in `config.yaml`. Verifies calibration is correct visually.

## config.yaml Schema

```yaml
baudrate: 3000000
port: /dev/tty.usbserial-XXXXX
max_current: 200              # mA
control_mode: 5               # current_based_position (recommended)
motor_ids: [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]
joint_ids: [thumb_mcp, thumb_abd, thumb_pip, thumb_dip,
            index_abd, index_mcp, index_pip,
            middle_abd, middle_mcp, middle_pip,
            ring_abd, ring_mcp, ring_pip,
            pinky_abd, pinky_mcp, pinky_pip, wrist]
joint_to_motor_map:
  thumb_mcp: {motor: 0, sign: 1}
  thumb_abd: {motor: 1, sign: -1}   # negative sign = inverted tendon
  # ... (17 mappings total)
joint_roms:
  thumb_mcp: [0, 90]
  thumb_abd: [-30, 30]
  # ... (17 joint ROMs)
neutral_position:
  thumb_mcp: 0
  thumb_abd: 0
  # ... (17 neutral positions)
```

## calibration.yaml Output

Written by `calibrate.py`:
```yaml
calibrated: true
timestamp: 2026-03-25T10:00:00
motor_limits:
  0: {min: 1024, max: 3072}    # raw Dynamixel positions
  # ... (17 motors)
joint_to_motor_ratios:
  thumb_mcp: 22.75             # degrees per Dynamixel unit
  # ... (17 ratios)
```

## When to Re-Calibrate

- After replacing a tendon
- After significant use (>1000 grasp cycles)
- If grasps feel imprecise or joints drift
- After any mechanical repair
- Weekly if running experiments (calibration drift is real)

## Troubleshooting

**Motor not found**: Check U2D2 connection, verify baudrate matches config, try `scripts/check_motor.py`.

**Calibration drift**: Tendons stretch over time. Re-run `tension.py` + `calibrate.py`. If persistent, replace the tendon.

**Motor overheating**: Reduce `max_current` in config.yaml. Check for tendon friction at routing points.
