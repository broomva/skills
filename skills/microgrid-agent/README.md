# microgrid-agent

**Open-source edge AI agent for autonomous renewable energy microgrid management.**

![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Rust](https://img.shields.io/badge/Kernel-Rust-orange.svg)
![Python 3.11+](https://img.shields.io/badge/ML-Python%203.11%2B-blue.svg)
![Platform: RPi 4/5](https://img.shields.io/badge/Platform-RPi%204%2F5-red.svg)
![Status: Active Development](https://img.shields.io/badge/Status-Active%20Development-yellow.svg)

## Three-Layer Architecture

```
kernel/      — Rust daemon (always-on, no GC, ~15MB binary)
               Sensors, dispatch, safety, journal, dashboard, fleet sync
               Agentic reasoning core via BitNet 2B LLM on-device
forecast/    — Python forecast worker (spawned on demand by kernel)
               TFLite LSTM forecasting, model retraining
reference/   — Frozen Python reference implementation
               Full agent in Python for validation and testing
simulation/  — Simulation & benchmarking framework (Python)
               Scenario definitions, controller comparison, metrics
```

---

## The Problem

An estimated 1.9 million people in Colombia's Zonas No Interconectadas (ZNI) lack access to reliable electricity. These communities -- scattered across the Pacific coast, the Amazon basin, the Orinoco plains, and island territories -- depend on isolated microgrids that run predominantly on imported diesel fuel. Roughly 78% of ZNI energy comes from diesel generators, driving electricity costs 3-5x higher than the national interconnected grid. The fuel itself must travel by river or air, arriving weeks late during rainy season, leaving entire communities in the dark.

Existing solutions fall into two camps, and neither works. Commercial microgrid controllers (Schneider, ABB, Siemens) cost $15,000-50,000 per node, require proprietary software licenses, and assume reliable internet connectivity for cloud-based optimization -- assumptions that collapse in a community reachable only by a six-hour boat ride from the nearest cellular tower. On the academic side, dozens of simulation papers propose sophisticated multi-agent optimization algorithms for microgrids, but they run on MATLAB or cloud GPUs, never touching real hardware or surviving a week of actual operation in the field.

No system exists today that provides autonomous, ML-based energy management optimized for disconnected, resource-constrained environments -- a system that can run on a $35 single-board computer, make intelligent dispatch decisions without any internet connection, and cost less than a single month of diesel savings to deploy.

## The Solution

`microgrid-agent` is an edge-first AI agent that runs entirely on a Raspberry Pi. It reads power from solar panels, batteries, and diesel generators via standard industrial protocols (Modbus RTU, Victron VE.Direct), forecasts demand and solar generation using lightweight ML models, and dispatches energy to minimize diesel consumption while protecting critical community loads.

**Total node cost: ~$650 USD** (Raspberry Pi + RS-485 HAT + sensors + enclosure).

```
Architecture Overview
=====================

                          +------------------+
                          |   Fleet Broker   |
                          |  (MQTT, cloud)   |
                          +--------+---------+
                                   |  store-and-forward
                                   |  (works offline)
            +----------------------+----------------------+
            |                      |                      |
    +-------+-------+     +-------+-------+      +-------+-------+
    | Site: Guainia  |     | Site: Choco   |      | Site: Vaupes  |
    | RPi 5 (8GB)   |     | RPi 4 (4GB)   |      | RPi 5 (4GB)   |
    +-------+-------+     +-------+-------+      +-------+-------+
            |                      |                      |
    +-------+-------+     +-------+-------+      +-------+-------+
    | Agent Core    |     | Agent Core    |      | Agent Core    |
    | +----------+  |     | +----------+  |      | +----------+  |
    | | LLM      |  |     | | LLM      |  |      | | LLM      |  |
    | | Reasoning|  |     | | Reasoning|  |      | | Reasoning|  |
    | +----------+  |     | +----------+  |      | +----------+  |
    | | Tools:   |  |     | | Tools:   |  |      | | Tools:   |  |
    | | LSTM, LP |  |     | | LSTM, LP |  |      | | LSTM, LP |  |
    | +----------+  |     | +----------+  |      | +----------+  |
    | | Autonomic|  |     | | Autonomic|  |      | | Autonomic|  |
    | | (safety) |  |     | | (safety) |  |      | | (safety) |  |
    | +----------+  |     | +----------+  |      | +----------+  |
    +-------+-------+     +-------+-------+      +-------+-------+
            |                      |                      |
    +-------+-------+     +-------+-------+      +-------+-------+
    | Modbus / VE.D |     | Modbus / VE.D |      | Modbus / VE.D |
    | Solar  Batt   |     | Solar  Batt   |      | Solar  Batt   |
    | Diesel Loads  |     | Diesel Loads  |      | Diesel Loads  |
    +---------------+     +---------------+      +---------------+
```

### Key Capabilities

- **Agentic Reasoning Core**: LLM-based decision making (BitNet 2B on-device, ~0.4 GB RAM, 29ms decode latency) with tiered escalation to larger models. The LLM reasons about the situation and calls tools; it IS the controller, not an add-on.
- **ML Forecasting Tools**: TensorFlow Lite LSTM models for solar irradiance and demand prediction. Inference in <0.5ms on RPi 5. Used as a tool by the reasoning core.
- **LP Dispatch Optimization**: Linear programming solver prioritizes solar, then battery, then diesel -- minimizing fuel consumption while meeting all loads.
- **Knowledge Graph**: SQLite-backed territorial context (<100MB) encodes community patterns -- market days, festivals, rainy seasons -- improving forecast accuracy.
- **Autonomic Safety Layer**: Hard safety constraints (SOC limits, diesel runtime caps, load shedding priority) enforced in deterministic Rust code. The LLM reasoning core can NEVER override these gates.
- **Fleet Sync**: MQTT-based store-and-forward telemetry. Queues data locally during connectivity outages, syncs when a link is available.
- **EGRI Self-Improvement**: Evaluator-governed recursive improvement -- the agent compares its predictions to outcomes and adjusts its own setpoints over time.
- **100% Offline Operation**: Every feature works without internet. Connectivity is optional and used only for fleet coordination.

## Quick Start

### Prototype Mode (Python — quickest way to explore)

```bash
# Clone the repository
git clone https://github.com/broomva/microgrid-agent.git
cd microgrid-agent

# Install in development mode
pip install -e ".[dev]"

# Run in simulation mode (no hardware needed)
make simulate

# Or run the simulation framework directly
python -m simulation.run
```

Simulation mode creates virtual solar panels, batteries, a diesel generator, and community loads with realistic diurnal patterns. You can explore the full control loop without any physical hardware.

### Kernel Mode (Rust — production target)

```bash
cd kernel
cargo build --release
# The ~15MB static binary runs on RPi with no runtime dependencies
```

## Hardware Setup

For deploying on a real microgrid, see the [DIY Guide](docs/diy-guide.md) for step-by-step instructions.

### Bill of Materials (Minimum Viable Node)

| Component | Model | Approx. Cost |
|-----------|-------|-------------|
| Single-board computer | Raspberry Pi 5 (8GB) | $80 |
| RS-485 HAT | Waveshare RS485 CAN HAT | $15 |
| Current transformers (x4) | SCT-013-030 (30A) | $40 |
| Irradiance sensor | BH1750 I2C lux sensor | $5 |
| Temperature sensor | DS18B20 waterproof | $5 |
| MicroSD card | 64GB A2 rated | $12 |
| Enclosure | IP65 junction box | $20 |
| Power supply | 5V 5A USB-C (solar-powered) | $15 |
| Wiring and connectors | Misc terminals, cable | $30 |
| **Total** | | **~$220** |

Add the cost of a Victron MPPT controller (~$200) and a small inverter (~$230) if not already installed, bringing a complete new-install node to ~$650.

### Wiring Overview

- **RS-485**: Connects to inverters and charge controllers via Modbus RTU (2-wire, half-duplex)
- **VE.Direct**: Connects to Victron MPPT controllers via serial TTL cable
- **I2C**: Irradiance sensor (BH1750) and temperature sensor (DS18B20)
- **Current Transformers**: Clamp-on CTs on AC distribution lines for load measurement

See [docs/architecture.md](docs/architecture.md) for detailed wiring diagrams and pinout tables.

## Configuration

The agent is configured via two TOML files:

### `config/site.toml`

Defines the site identity, grid topology, equipment specifications, autonomic controller setpoints, and community context. Copy `config/site.example.toml` to get started:

```toml
[site]
id = "site-guainia-001"
name = "Demo Microgrid -- Guainia"
latitude = 3.8653
longitude = -67.9239

[grid]
type = "hybrid"           # solar + battery + diesel
peak_load_kw = 45.0

[autonomic]
min_soc_pct = 15          # load shedding threshold
diesel_start_soc = 20     # diesel auto-start
renewable_target = 0.85   # 85% renewable fraction goal
```

### `config/devices.toml`

Defines each physical (or simulated) device on the microgrid bus. Supports `modbus_rtu`, `vedirect`, and `simulated` protocols:

```toml
[[device]]
id = "solar-array-1"
name = "PV Array North"
type = "solar"
protocol = "modbus_rtu"
port = "/dev/ttyUSB0"
slave_id = 1
```

## Architecture

> **Agentic-native framing**: The microgrid agent is not an ML model with a control loop
> bolted on. It is an autonomous AI agent (a Life/Arcan instance) with an LLM reasoning
> core, tools for sensing/dispatch/KG, and deterministic safety gates. The LSTM and LP
> solver are tools the agent uses, not the agent itself. See
> [docs/architecture.md](docs/architecture.md) for the full rationale.

```
Multi-Rate Control Loop
=======================

    +----------+     +----------+     +----------+
    | 100ms    |     | 1s       |     | 5min     |
    | Safety   |---->| Device   |---->| Agent    |
    | Reflex   |     | Polling  |     | Reasoning|
    | (Tier 1) |     |          |     | (Tier 2) |
    +----------+     +----------+     +----------+
         |                |                |
         v                v                v
    Hard limits      Read sensors     LLM reasons
    SOC bounds       Update state     Calls tools
    Fault detect     Log telemetry    Autonomic validates
    Emergency shed   Dashboard push   Sync fleet
```

```
Module Map
==========

    kernel/src/              Rust daemon (always-on, ~15MB binary)
    +-- main.rs              Tokio async runtime & control loop
    +-- devices.rs           Hardware abstraction (Modbus, VE.Direct)
    +-- dispatch.rs          LP optimizer (good_lp)
    +-- autonomic.rs         Safety gates & homeostasis
    +-- knowledge.rs         Knowledge graph (rusqlite)
    +-- journal.rs           Event journal (redb, crash-safe)
    +-- ml_bridge.rs         IPC bridge to Python ML worker
    +-- dashboard.rs         Local dashboard (axum + HTMX)
    +-- sync.rs              MQTT fleet sync (rumqttc)
    +-- config.rs            TOML config loader
    +-- tools/               Modbus RTU & VE.Direct protocol drivers

    forecast/                Forecast ML worker (spawned on demand)
    +-- forecast.py          TFLite LSTM inference
    +-- worker.py            IPC worker process

    reference/src/           Frozen Python reference implementation
    +-- agent.py             Main control loop & orchestrator
    +-- devices.py           Hardware abstraction (simulated + Modbus)
    +-- dispatch.py          LP optimizer (scipy.optimize.linprog)
    +-- knowledge.py         SQLite knowledge graph
    +-- autonomic.py         Safety constraints
    +-- dashboard.py         Local web dashboard (FastAPI)
    +-- sync.py              MQTT fleet sync

    simulation/              Simulation & benchmarking framework
    +-- run.py               Simulation runner
    +-- scenario.py          Scenario definitions
    +-- controllers.py       Control strategies for benchmarking
    +-- metrics.py           Performance metrics & comparison
```

For the full technical architecture reference, see [docs/architecture.md](docs/architecture.md) -- consolidated design document covering agentic-native philosophy, three-plane system map, protocol details, LP formulation, fleet sync, and security.

## DIY Guide

Want to build your own microgrid agent node? The [DIY Guide](docs/diy-guide.md) walks you through the entire process:

1. **Hardware Assembly** -- component selection, wiring, enclosure
2. **OS Setup** -- Raspberry Pi OS configuration, read-only rootfs
3. **Software Installation** -- clone, install, configure
4. **Equipment Connection** -- RS-485, VE.Direct, sensor wiring
5. **Calibration** -- device health checks, SOC baseline
6. **Shadow Mode** -- observe AI decisions before giving it control
7. **Go Live** -- switch to active mode with monitoring

No prior experience with energy systems required. The simulation mode lets you learn the system before touching any hardware.

## Development

```bash
# Install Python dev dependencies
pip install -e ".[dev]"

# Run Python tests (prototype + ML)
make test

# Lint & format Python code
make lint
make format

# Run simulation
make simulate

# Build Rust kernel
cd kernel && cargo build --release

# Run sim framework for benchmarking
python -m simulation.run
```

## Contributing

Contributions are welcome. This project exists to make autonomous energy management accessible to communities that need it most.

### How to Contribute

1. **Fork** the repository
2. **Create a branch** for your feature (`git checkout -b feature/my-feature`)
3. **Write tests** for any new functionality
4. **Run the linter** (`make lint`) and **tests** (`make test`) before submitting
5. **Open a Pull Request** with a clear description of the change

### Areas Where Help is Needed

- **Device drivers**: Support for additional inverters, charge controllers, and meters
- **Forecasting models**: Better solar irradiance and demand prediction for tropical climates
- **Fleet protocols**: Satellite-based sync for sites with no cellular coverage
- **Documentation**: Translations to Spanish for ZNI community deployment
- **Field testing**: Real-world validation data from microgrid deployments

### Code Standards

- **Rust kernel**: stable Rust, tokio async runtime, tracing for structured logging
- **Python (reference/forecast)**: Python 3.11+ with type hints on all functions, asyncio for I/O
- Ruff for Python linting and formatting
- pytest for Python testing
- Structured JSON logging (no print statements)

## License

MIT License. See [LICENSE](LICENSE) for details.

This is open-source software. Use it, modify it, deploy it. If it saves a community from burning diesel, that is the point.

## Acknowledgments

- Research conducted at **Universidad de los Andes**
- Supported by the **TICSw research group** (A1 classification, Minciencias)
- Inspired by the **Husk Power Systems** fleet intelligence model for distributed mini-grid management
- Built on Colombia's ZNI electrification data from **IPSE** (Instituto de Planificacion y Promocion de Soluciones Energeticas)
- Solar irradiance data from **IDEAM** (Instituto de Hidrologia, Meteorologia y Estudios Ambientales)
