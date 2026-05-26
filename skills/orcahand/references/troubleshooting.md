# Troubleshooting

## Table of Contents
- Hardware Issues
- Simulation Issues
- Calibration Issues
- Teleoperation Issues
- Common Error Messages

## Hardware Issues

### Motor not found
```
DynamixelError: Motor ID X not found on port /dev/tty.usbserial-XXXXX
```
- Check U2D2 USB connection
- Verify serial port: `ls /dev/tty.usbserial-*` (macOS)
- Verify baudrate matches config.yaml (must be 3000000)
- Run `python scripts/check_motor.py` to scan all IDs
- Check power supply is connected and on (motors need 12V)

### Servo overheating
- Reduce `max_current` in config.yaml (try 150mA)
- Check for tendon friction at routing points — re-route if needed
- Allow cooldown period (temperature shield triggers at 70°C)
- If persistent: check for mechanical binding in the joint

### Tendon snapped
- Replace with Dyneema fishing line (same gauge)
- Re-route through low-friction channels
- Run full calibration after replacement: tension → calibrate → neutral

### Popping joint stuck
- Gently push joint back into socket (designed to pop back)
- If repeatedly stuck: check 3D print quality, reprint at 100% infill

## Simulation Issues

### MuJoCo segfault on macOS
```
Segmentation fault: 11
```
- Use `mjpython` instead of `python` for interactive rendering
- For headless: use `render_mode="rgb_array"` (no display needed)
- Update MuJoCo: `pip install --upgrade mujoco`

### Environment won't load
```
FileNotFoundError: MJCF file not found
```
- Ensure `orcahand_description` is cloned in the expected location
- Check `orca_sim` version matches description version (v1 vs v2)
- Reinstall: `pip install -e orca_sim/`

### Rendering blank/black
- macOS: Must use `mjpython` for `render_mode="human"`
- Remote server: Use `render_mode="rgb_array"` (no display)
- Check: `python -c "import mujoco; print(mujoco.glfw)"` — should not error

## Calibration Issues

### Calibration drift
- Tendons stretch over time — re-tension periodically
- Run `tension.py` → `calibrate.py` weekly during active use
- If drift is severe: replace tendon

### Motor position jumps during calibration
- Motor may be in wrong control mode — ensure `control_mode: 5` in config.yaml
- Check motor daisy-chain wiring for loose connections
- Verify motor IDs match config.yaml ordering

### calibration.yaml not updating
- Check file permissions on the model directory
- Verify `calibrate.py` completed without errors
- Look for `calibrated: false` — indicates calibration failed

## Teleoperation Issues

### Apple Vision Pro not connecting
- Verify AVP and Mac are on the same WiFi network
- Check IP address: `streamer = VisionProStreamer(ip="<correct_IP>")`
- Restart AVP streaming app

### Retargeter output looks wrong
- Check `hand_scheme.yaml` — joint coupling may be misconfigured
- Verify URDF path in retargeter matches your hand version (v1/v2)
- Adjust `mano_adjustments` in `retargeter.yaml` for hand size differences
- Increase optimization steps for better convergence (reduce `lr`)

### High latency during teleoperation
- Reduce `num_steps` in `set_joint_pos` (try 5 instead of 25)
- Check WiFi latency (AVP): should be <10ms
- Serial latency: U2D2 at 3M baud is ~0.5ms per command

## Common Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `PacketError: [TxRxResult] Incorrect status packet!` | Baudrate mismatch | Set baudrate to 3000000 in config.yaml |
| `GroupSyncRead: Parameter length does not match` | Motor count mismatch | Verify 17 motor IDs in config.yaml |
| `PortError: Failed to open port` | Serial port busy or wrong | Check port path, close other serial apps |
| `ImportError: No module named 'dynamixel_sdk'` | SDK not installed | `pip install dynamixel-sdk` |
| `mujoco.FatalError: Nan in simulation` | Physics instability | Reduce step size, check model XML |
