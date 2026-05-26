# DIY Guide: Build a Microgrid Agent Node

This guide walks you through building, configuring, and deploying a microgrid-agent node from scratch. No prior experience with energy systems or embedded Linux is required.

> **Two paths**: This guide uses the **Python reference implementation** (`reference/`) for quick setup and experimentation.
> For production deployments, the **Rust kernel** (`kernel/`) provides the same capabilities
> as a single static binary with no runtime dependencies. The Rust kernel also supports
> the agentic reasoning core (BitNet 2B LLM for on-device decision making) -- see
> [architecture.md](architecture.md) for details.

**Time estimate**: 4-6 hours for hardware assembly + software setup. Allow a full day for calibration and shadow mode testing.

**Difficulty**: Intermediate. Basic terminal skills required. Soldering only needed for sensor connections.

---

## Prerequisites

### Hardware You Will Need

- Raspberry Pi 5 (8GB recommended) or Raspberry Pi 4 (4GB minimum)
- A microgrid or solar installation to connect to, **OR** just run in simulation mode to learn the system first
- Basic tools: soldering iron, wire strippers, multimeter, screwdrivers

### Software You Will Need

- A computer to flash the RPi SD card (Mac, Windows, or Linux)
- SSH client (Terminal on Mac/Linux, PuTTY on Windows)
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/)

### Skills

- Comfortable with the Linux command line
- Basic understanding of DC and AC electricity (voltage, current, power)
- Soldering skills for sensor wire connections (through-hole level, nothing surface-mount)

---

## Step 1: Hardware Assembly

### Bill of Materials

| # | Component | Model / Spec | Qty | Approx. Cost | Notes |
|---|-----------|-------------|-----|--------------|-------|
| 1 | Single-board computer | Raspberry Pi 5 (8GB) | 1 | $80 | RPi 4 (4GB) also works |
| 2 | RS-485 HAT | Waveshare RS485 CAN HAT (B) | 1 | $15 | For Modbus RTU to inverters |
| 3 | Current transformers | SCT-013-030 (30A, split-core) | 4 | $40 | Non-invasive AC measurement |
| 4 | ADC for CTs | ADS1115 16-bit I2C ADC | 1 | $10 | Convert CT analog to digital |
| 5 | Irradiance sensor | BH1750 I2C lux sensor | 1 | $5 | Solar irradiance estimation |
| 6 | Temperature sensor | DS18B20 waterproof probe | 2 | $10 | Ambient + panel temperature |
| 7 | MicroSD card | 64GB A2 rated (SanDisk Extreme) | 1 | $12 | A2 rating important for SQLite |
| 8 | Power supply | 5V 5A USB-C | 1 | $15 | Official RPi PSU recommended |
| 9 | Enclosure | IP65 ABS junction box (200x150x75mm) | 1 | $20 | Outdoor-rated |
| 10 | Cable glands | PG9 nylon cable glands | 6 | $5 | Weatherproof cable entry |
| 11 | DIN rail clips | For RPi mounting | 1 | $5 | Optional but clean |
| 12 | Wiring | 22 AWG stranded, terminal blocks | - | $15 | Misc connectors |
| 13 | VE.Direct cable | Victron VE.Direct to USB | 1 | $25 | Only if using Victron gear |

**Total: ~$220-260** (excluding inverter/charge controller)

### Assembly Steps

1. **Mount the Raspberry Pi** inside the IP65 enclosure using DIN rail clips or standoffs. Leave space for the RS-485 HAT on top.

2. **Attach the RS-485 HAT** to the RPi GPIO header. The Waveshare HAT uses pins:
   - GPIO14 (TXD) for transmit
   - GPIO15 (RXD) for receive
   - GPIO4 for RS-485 direction control (some HATs use hardware auto-direction)

3. **Wire the ADS1115 ADC** to the I2C bus:
   - VCC to 3.3V (pin 1)
   - GND to GND (pin 6)
   - SDA to GPIO2 (pin 3)
   - SCL to GPIO3 (pin 5)
   - ADDR to GND (I2C address 0x48)

4. **Connect the BH1750 irradiance sensor** to the same I2C bus:
   - VCC to 3.3V
   - GND to GND
   - SDA to GPIO2 (shared bus)
   - SCL to GPIO3 (shared bus)
   - ADDR floating (I2C address 0x23)

5. **Wire DS18B20 temperature sensors** to the 1-Wire bus:
   - VCC to 3.3V
   - GND to GND
   - DATA to GPIO4 (pin 7) with 4.7k pull-up resistor to 3.3V

6. **Install cable glands** in the enclosure for all cable entries. Seal with silicone if deploying outdoors.

### Enclosure Layout

```
+--------------------------------------------------+
|  [RPi 5]          [RS-485 HAT]                   |
|  +--------+       +----------+                   |
|  |        |       | A  B GND |---> to Modbus bus |
|  |        |       +----------+                   |
|  +--------+                                      |
|                                                  |
|  [ADS1115]    [BH1750]    [Terminal Block]        |
|  CT1 CT2      Lux          DS18B20 x2            |
|  CT3 CT4                                         |
|                                                  |
|  === Cable Glands ===                            |
|  [RS485] [CTs] [Sensors] [Power] [VE.Direct]    |
+--------------------------------------------------+
```

---

## Step 2: OS Setup

### Flash the SD Card

1. Download and install [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Select **Raspberry Pi OS Lite (64-bit)** -- no desktop environment needed
3. Click the gear icon to pre-configure:
   - Set hostname: `microgrid-001` (or your site ID)
   - Enable SSH with password or (preferred) SSH key
   - Configure WiFi if available (not required for operation)
   - Set locale and timezone to `America/Bogota`
4. Flash to the microSD card

### First Boot Configuration

SSH into the Pi and run initial setup:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y \
    python3-pip python3-venv python3-dev \
    git i2c-tools \
    libopenblas-dev libatlas-base-dev \
    mosquitto-clients

# Enable hardware interfaces
sudo raspi-config nonint do_i2c 0      # Enable I2C
sudo raspi-config nonint do_spi 0      # Enable SPI
sudo raspi-config nonint do_serial 2   # Enable serial (disable console)

# Verify I2C devices are detected
i2cdetect -y 1
# Should show 0x48 (ADS1115) and 0x23 (BH1750)

# Reboot to apply
sudo reboot
```

### Read-Only Root Filesystem (Recommended)

For long-term unattended operation, configure a read-only rootfs to prevent SD card corruption from unexpected power loss:

```bash
# Install the overlay filesystem tool
sudo raspi-config
# -> Performance Options -> Overlay File System -> Enable

# Data directories are mounted as tmpfs or on a separate partition
# The agent writes only to /var/lib/microgrid-agent/ (data partition)
```

This is optional for development but strongly recommended for field deployment.

---

## Step 3: Software Installation

### Clone and Install

```bash
# Clone the repository
git clone https://github.com/broomva/microgrid-agent.git
cd microgrid-agent

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the agent and dependencies
pip install -e ".[rpi]"

# Or run the install script (does all of the above + systemd service)
# chmod +x scripts/install.sh
# sudo ./scripts/install.sh
```

### Configure Your Site

```bash
# Copy the example config
cp config/site.example.toml config/site.toml

# Edit with your site details
nano config/site.toml
```

Key fields to customize:

```toml
[site]
id = "your-site-id"          # Unique across fleet
name = "Your Microgrid"
latitude = 3.8653            # Your GPS coordinates
longitude = -67.9239

[solar]
capacity_kwp = 60.0          # Your actual PV capacity

[battery]
capacity_kwh = 120.0         # Your actual battery capacity
chemistry = "lfp"            # lfp, nmc, lead_acid, or flow

[diesel]
capacity_kw = 30.0           # Your genset rating

[community]
population = 850             # Approximate population served
primary_activity = "fishing"  # agriculture, fishing, mining, tourism, mixed
```

### Configure Your Devices

Create `config/devices.toml` with your equipment:

```toml
# Solar inverter via Modbus RTU
[[device]]
id = "solar-inv-1"
name = "Solar Inverter"
type = "solar"
protocol = "modbus_rtu"
port = "/dev/ttyUSB0"
slave_id = 1
baudrate = 9600

# Victron MPPT charge controller
[[device]]
id = "mppt-1"
name = "Victron MPPT 150/60"
type = "solar"
protocol = "vedirect"
port = "/dev/ttyUSB1"

# Battery BMS via Modbus
[[device]]
id = "battery-bms"
name = "Battery Management System"
type = "battery"
protocol = "modbus_rtu"
port = "/dev/ttyUSB0"
slave_id = 2

# Diesel generator controller via Modbus
[[device]]
id = "diesel-gen"
name = "Diesel Generator"
type = "diesel"
protocol = "modbus_rtu"
port = "/dev/ttyUSB0"
slave_id = 3
```

If you don't have hardware yet, use simulated devices:

```toml
[[device]]
id = "sim-solar"
name = "Simulated Solar Array"
type = "solar"
protocol = "simulated"
base_power_kw = 5.0

[[device]]
id = "sim-battery"
name = "Simulated Battery"
type = "battery"
protocol = "simulated"
base_power_kw = 3.0

[[device]]
id = "sim-load"
name = "Simulated Community Load"
type = "load"
protocol = "simulated"
base_power_kw = 4.0
```

---

## Step 4: Connect Equipment

### RS-485 Wiring for Modbus RTU

Modbus RTU uses a 2-wire RS-485 bus. Multiple devices share the same bus with different slave IDs.

```
RS-485 HAT          Inverter          BMS              Genset
+--------+          +-------+         +-------+        +-------+
| A  (+) |---+------| A (+) |----+----| A (+) |---+----| A (+) |
| B  (-) |---+------| B (-) |----+----| B (-) |---+----| B (-) |
| GND    |---+------| GND   |----+----| GND   |---+----| GND   |
+--------+          +-------+         +-------+        +-------+
  Slave:              ID=1             ID=2              ID=3
```

**Wiring notes:**
- Use twisted-pair cable (Cat5e works well) for the A/B lines
- Keep total bus length under 1200 meters
- Add a 120-ohm termination resistor at each end of the bus
- Connect GND between all devices to establish a common reference

### VE.Direct Connection (Victron)

VE.Direct uses a simple 4-pin serial connection at 19200 baud.

```
Victron MPPT                    RPi (via USB adapter)
+------------+                  +-------------------+
| VE.Direct  |                  | USB port          |
| TX   (pin 1) ----[cable]---- | RX                |
| RX   (pin 2) ----[cable]---- | TX                |
| GND  (pin 3) ----[cable]---- | GND               |
| +5V  (pin 4)   (not used)    |                   |
+------------+                  +-------------------+
```

Use a Victron VE.Direct to USB cable ($25) for the simplest connection.

### Sensor Wiring

**Current Transformers (CTs):**
```
CT (SCT-013-030)              ADS1115 ADC
+---------------+             +---------+
| 3.5mm jack    |             | A0      | <- CT1 (solar output)
| Tip  ---------|------------>| A1      | <- CT2 (battery)
| Ring ---------|--+--------->| A2      | <- CT3 (diesel output)
+---------------+  |          | A3      | <- CT4 (total load)
                   |          | GND     |
                   +--------->| GND     |
                              +---------+
```

**Note:** Each CT needs a burden resistor (typically 33 ohm for the SCT-013-030) across its output, plus a DC bias circuit. See the [OpenEnergyMonitor CT sensor guide](https://learn.openenergymonitor.org/electricity-monitoring/ct-sensors/) for the full circuit.

**Irradiance Sensor (BH1750):**
Mount the BH1750 sensor at the same tilt angle as the solar panels, facing the same direction. Protect with a clear polycarbonate dome.

**Temperature Sensors (DS18B20):**
- Sensor 1: Mount on the back of a representative solar panel (panel temperature)
- Sensor 2: Mount in a shaded, ventilated location (ambient temperature)

---

## Step 5: Calibration

### Run the Health Check

```bash
# Activate the virtual environment
source .venv/bin/activate

# Run the health check script
python -m microgrid_agent.health_check --config config/site.toml

# Or via make
make health
```

The health check verifies:
- All configured devices respond
- Sensor readings are within expected ranges
- I2C bus detects all sensors
- SQLite database is writable
- System clock is approximately correct

### Verify Device Readings

```bash
# Read all devices once and display results
python -m microgrid_agent --config config/site.toml --read-once

# Expected output:
# solar-inv-1    | ONLINE  | 3.2 kW  | 45.6 kWh
# battery-bms    | ONLINE  | -1.5 kW | 89.2 kWh (SOC: 72%)
# diesel-gen     | STANDBY | 0.0 kW  | 123.4 kWh
```

If a device shows OFFLINE, check:
1. RS-485 A/B wires are not swapped
2. Slave ID matches the device configuration
3. Baud rate matches (most inverters default to 9600)
4. Termination resistors are installed

### Initial SOC Calibration

The battery SOC estimate needs a baseline. If your BMS reports SOC directly via Modbus, this is automatic. If using voltage-based estimation:

```bash
# Calibrate SOC from a known state
# Run this when battery is fully charged (100% SOC)
python -m microgrid_agent.calibrate --full-charge

# Or when battery is at a known voltage
python -m microgrid_agent.calibrate --voltage 52.8 --soc 80
```

---

## Step 6: Shadow Mode

Shadow mode is critical. The agent reads all sensors and runs the full ML forecasting and LP dispatch pipeline, but does **not** send any control commands to devices. It logs what it *would* have done, so you can compare AI decisions against actual operation.

### Start Shadow Mode

```bash
# Run in shadow mode
python -m microgrid_agent --config config/site.toml --shadow

# Or via systemd (if installed)
sudo systemctl start microgrid-agent-shadow
```

### Review Dispatch Logs

After running shadow mode for at least 24 hours (ideally 3-7 days):

```bash
# View the dispatch log
python -m microgrid_agent.review --last 24h

# Example output:
# 2026-03-30 06:15 | AI: start diesel (SOC 18%) | Actual: diesel already running
# 2026-03-30 07:30 | AI: stop diesel (SOC 45%)  | Actual: diesel stopped at 50%
# 2026-03-30 12:00 | AI: curtail solar (SOC 94%)| Actual: no curtailment
# 2026-03-30 18:45 | AI: shed "community_center"| Actual: no shedding occurred
```

### What to Look For

- **Diesel start/stop timing**: Is the AI's diesel threshold reasonable? Adjust `diesel_start_soc` and `diesel_stop_soc` in `site.toml` if needed.
- **Load shedding decisions**: Would the AI's shedding order protect the right loads? Verify `priority_loads` order in `site.toml`.
- **Forecast accuracy**: Are solar and demand predictions close to actual? The model improves with more local data.
- **No erratic behavior**: The agent should not oscillate rapidly between states.

Spend at least 3 days in shadow mode. A week is better. Adjust configuration based on what you observe before going live.

---

## Step 7: Go Live

Once you are confident in shadow mode results:

### Switch to Active Mode

```bash
# Start in active mode
python -m microgrid_agent --config config/site.toml

# Or enable the systemd service for boot-on-start
sudo systemctl enable microgrid-agent
sudo systemctl start microgrid-agent
```

### Monitor via Local Dashboard

The agent serves a lightweight web dashboard on port 8080:

```
http://microgrid-001.local:8080
```

The dashboard shows:
- Real-time power flows (solar, battery, diesel, loads)
- Battery SOC gauge
- 24-hour forecast vs actual graph
- Diesel runtime counter
- Load shedding status
- Alert log

### Set Up Fleet Sync (Optional)

If you have multiple sites or want remote monitoring:

```toml
# In site.toml
[connectivity]
primary = "cellular"
mqtt_broker = "mqtt://your-broker:1883"
sync_interval = 300  # seconds
```

The agent queues all telemetry locally and pushes to the MQTT broker when connectivity is available. If the connection drops, data accumulates in `data/sync-queue/` and is sent when the link recovers. No data is ever lost.

---

## Troubleshooting

### Device shows OFFLINE

| Symptom | Check | Fix |
|---------|-------|-----|
| All Modbus devices offline | RS-485 wiring | Verify A/B not swapped; check termination resistors |
| One Modbus device offline | Slave ID | Confirm slave ID in device manual matches `devices.toml` |
| VE.Direct device offline | USB port | Try `ls /dev/ttyUSB*`; port number may change after reboot |
| Intermittent timeouts | Cable length | Keep RS-485 bus under 1200m; use twisted pair |

### Agent crashes on startup

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: pymodbus` | Missing dependency | Run `pip install -e ".[rpi]"` |
| `Permission denied: /dev/ttyUSB0` | User not in dialout group | `sudo usermod -aG dialout $USER` then reboot |
| `FileNotFoundError: site.toml` | Config not created | Copy `config/site.example.toml` to `config/site.toml` |
| `I2C bus error` | I2C not enabled | Run `sudo raspi-config nonint do_i2c 0` |

### High CPU usage

The agent should use <5% CPU on RPi 5 during normal operation. If CPU is high:
- Check if TFLite model is too large. Use the quantized INT8 model.
- Reduce device polling rate if many devices are connected.
- Ensure logging level is INFO, not DEBUG in production.

### SD card corruption

If the Pi has been running without a read-only rootfs and loses power:

```bash
# Check filesystem
sudo fsck -y /dev/mmcblk0p2

# If data partition is corrupt, the agent will recreate its SQLite databases
# on next start. Historical data in the sync queue may be lost.
```

Prevention: Enable the read-only overlay filesystem (see Step 2) for any unattended deployment.

### Solar forecast is inaccurate

The LSTM model needs 7-14 days of local data to calibrate. During the first week, it uses a simple clearsky model based on latitude/longitude. Accuracy improves as it learns local cloud patterns and panel-specific performance.

If forecasts remain poor after 2 weeks:
- Verify latitude/longitude in `site.toml`
- Check that the BH1750 irradiance sensor is properly mounted (same angle as panels)
- Verify panel `orientation` and `tilt` values in `site.toml`
- Check for panel shading not accounted for in the model

### MQTT sync not working

```bash
# Test MQTT connectivity manually
mosquitto_pub -h your-broker -t "test" -m "hello"

# Check the sync queue size
ls -la data/sync-queue/

# Force a sync attempt
python -m microgrid_agent.sync --force --config config/site.toml
```

---

## Next Steps

- **Switch to the Rust kernel**: Once comfortable with the Python reference implementation, deploy the Rust kernel (`kernel/`) for production -- it is a single ~15MB binary with no runtime dependencies, lower memory usage, and faster startup. See [architecture.md](architecture.md) for the full three-plane architecture.
- **Enable agentic reasoning**: The Rust kernel supports BitNet 2B as an on-device LLM reasoning core (~0.4 GB RAM, 29ms per token). The agent reasons about the situation and uses the LSTM forecast and LP dispatch as tools, rather than following a fixed control loop. See [architecture.md](architecture.md) for the tiered reasoning architecture.
- **Join the community**: Open issues on GitHub for questions, bug reports, or feature requests
- **Share your data**: Anonymized operational data from field deployments helps improve the forecasting models for everyone
- **Contribute**: See [CONTRIBUTING](../README.md#contributing) in the main README
- **Scale up**: Deploy multiple nodes and connect them via fleet sync for coordinated multi-site management
