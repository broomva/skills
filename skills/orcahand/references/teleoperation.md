# Teleoperation

## Table of Contents
- Architecture Overview
- Apple Vision Pro Setup
- Rokoko Glove Setup
- MediaPipe Webcam Fallback
- Retargeter Configuration
- End-to-End Demo

## Architecture Overview

```
Human hand input → Retargeter → OrcaHand
                   (gradient-based optimization)
                   MANO keypoints → joint angles
```

Three input sources, one retargeter, one output:
1. **Apple Vision Pro** via `avp-stream` — best quality, wireless
2. **Rokoko glove** via ROS2 ingress — professional, wired/wireless
3. **MediaPipe webcam** — no hardware required, lower accuracy

## Apple Vision Pro Setup

```bash
pip install avp-stream
```

```python
from avp_stream import VisionProStreamer
from orca_retargeter import Retargeter
from orca_core import OrcaHand

# Initialize
streamer = VisionProStreamer(ip="<AVP_IP>")
retargeter = Retargeter("orca_retargeter/models/orcahand_v1_right")
hand = OrcaHand("orca_core/models/orcahand_v1_right")
hand.connect()
hand.enable_torque()

# Stream loop
while True:
    avp_data = streamer.get_latest()
    if avp_data is not None:
        joint_angles = retargeter.retarget(avp_data)
        hand.set_joint_pos(joint_angles, num_steps=5, step_size=0.001)
```

**Latency**: ~30-50ms end-to-end (AVP tracking → WiFi → retarget → serial → servo).

## Rokoko Glove Setup

Requires ROS2 and `rwr_system`:

```bash
# In ROS2 workspace
cd ~/ros2_ws/src
git clone https://github.com/orcahand/rwr_system.git
pip install -e .[all]
colcon build --symlink-install
source install/setup.bash

# Run teleoperation
ros2 launch experiments record_demonstration.launch.py
ros2 run experiments run_teleop_rokoko.py
```

**Calibration** (3 steps in the Rokoko teleop script):
1. Robot init — move to neutral
2. Robot calibrate — map joint limits
3. Glove calibrate — map human hand range

**ROS2 topics**:
- `/ingress/mano` (Float32MultiArray, 21x3) — MANO keypoints
- `/ingress/wrist` (PoseStamped) — wrist pose
- `/hand/policy_output` (Float32MultiArray) — joint angles in radians

## MediaPipe Webcam Fallback

No special hardware — just a webcam. Lower accuracy, higher latency.

Available via `rwr_system/ingress/webcam` or standalone with MediaPipe:

```python
import mediapipe as mp
import cv2

mp_hands = mp.solutions.hands.Hands(max_num_hands=1)
cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    results = mp_hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    if results.multi_hand_landmarks:
        landmarks = results.multi_hand_landmarks[0]
        # Convert to MANO format and feed to retargeter
```

**Limitations**: 2D tracking (depth estimated), sensitive to lighting, ~100ms latency.

## Retargeter Configuration

Three config files in `orca_retargeter/models/<model_name>/`:

### `hand_scheme.yaml`
Defines tendon-joint coupling and kinematic structure:
```yaml
gc_tendons:        # tendon → joint coupling matrix
finger_to_tip:     # finger name → tip link name
finger_to_base:    # finger name → base link name
gc_limits_lower:   # generalized coordinate lower bounds
gc_limits_upper:   # generalized coordinate upper bounds
wrist_name: wrist  # wrist joint name
```

### `retargeter.yaml`
Tuning parameters for the optimization:
```yaml
lr: 2.5                      # RMSprop learning rate
use_scalar_distance_palm: true
loss_coeffs:                  # per-finger loss weights
  thumb: 1.0
  index: 1.0
  middle: 0.8
  ring: 0.6
  pinky: 0.4
mano_adjustments:             # per-finger corrections
  thumb:
    translation: [0, 0, 0]
    rotation: [0, 0, 0]
    scale: 1.0
joint_regularizers:           # prevent extreme angles
  thumb_mcp: 0.01
```

### Tuning tips
- Increase `lr` for faster tracking (may overshoot)
- Adjust `loss_coeffs` to prioritize certain fingers (thumb > pinky for most tasks)
- Modify `mano_adjustments` if mapping feels offset for your hand size

## End-to-End Demo

The `ret_demo.py` script in `orca_retargeter/` connects everything:

```bash
cd orca_retargeter
python ret_demo.py --model models/orcahand_v1_right --input avp
```

Options: `--input avp` (Apple Vision Pro), `--input replay` (recorded data).
