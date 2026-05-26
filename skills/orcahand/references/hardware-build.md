# Hardware Build Guide

## Table of Contents
- Bill of Materials
- 3D Printing
- Sourcing Servos
- Assembly
- Wiring
- First Power-On

## Bill of Materials

| Component | Qty | Approx Cost | Source |
|-----------|-----|-------------|--------|
| Dynamixel XC330-T288 servo | 17 | $1,190 | ROBOTIS |
| U2D2 USB-to-serial adapter | 1 | $35 | ROBOTIS |
| U2D2 Power Hub | 1 | $20 | ROBOTIS |
| 3D printed structural parts | 1 set | ~$50 filament | Self-print |
| Tendons (Dyneema fishing line) | ~5m | $10 | Amazon |
| M2/M3 screws + hardware | assorted | $15 | Amazon |
| 12V 5A power supply | 1 | $25 | Amazon |
| **Total (self-build)** | | **~$1,345** | |

**Budget alternative**: Feetech SCS0009 servos (~$8 each vs $70 for Dynamixel). Lower quality, less precise, but functional. Use `FeetechClient` in orca_core.

**Pre-assembled**: $3,500 from orcahand.com or ROBOTIS (orcahand standard).

## 3D Printing

STL files: `orcahand_description/` repo, under `v1/meshes/` or `v2/meshes/`.

**Recommended settings**:
- Material: PLA or PETG (PETG preferred for durability)
- Layer height: 0.2mm
- Infill: 30-40% (structural parts), 20% (cosmetic)
- Supports: required for finger segments and palm
- Estimated print time: ~24-30 hours total

**Key parts**: main tower (~15K faces), base (~2K), finger segments, skin covers.

**Popping joints**: Print these at 100% infill — they must survive repeated dislocation/relocation cycles without deforming.

## Sourcing Servos

- **ROBOTIS direct**: Best price, reliable shipping. Order XC330-T288-T (TTL protocol).
- **Amazon/ROBOTIS resellers**: Faster shipping, slight markup.
- **Feetech alternative**: SCS0009 — budget option, requires `FeetechClient` driver in orca_core.

All 17 servos must be the same model. Do not mix Dynamixel and Feetech.

## Assembly

Official video guides available at [orcahand.com](https://orcahand.com/).

**Key steps**:
1. Assemble finger segments — thread tendons through channels
2. Mount servos into the palm/tower structure
3. Route tendons through low-friction channels at joint rotation centers
4. Attach finger assemblies to palm
5. Wire servo daisy-chain (TTL bus)
6. Connect U2D2 adapter

**Tendon routing**: Route tendons through joint rotation centers to minimize friction. This is the most critical assembly step — poor routing causes tendon wear and calibration drift.

**Assembly time**: ~6-8 hours for first build, ~3-4 hours with experience.

## Wiring

```
12V PSU → U2D2 Power Hub → Servo daisy-chain (TTL bus)
                            Motor 0 → Motor 1 → ... → Motor 16
                                                         |
U2D2 USB adapter ← ─────────────── TTL data bus ─────────┘
     |
  USB to Mac/PC
```

- **Protocol**: Dynamixel Protocol 2.0 (TTL)
- **Baudrate**: 3,000,000 (set via `scripts/configure_motor_chain.py`)
- **Motor IDs**: 0-16, pre-configured or set with `configure_motor_chain.py`

## First Power-On

1. Connect U2D2 USB to your computer
2. Detect serial port: `ls /dev/tty.usbserial-*` (macOS) or `ls /dev/ttyUSB*` (Linux)
3. Update `config.yaml` with your serial port
4. Test motor detection: `python scripts/check_motor.py orca_core/models/orcahand_v1_right`
5. Proceed to calibration: see [calibration-pipeline.md](calibration-pipeline.md)
