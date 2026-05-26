# microgrid-agent

## Project Context

Open-source edge AI agent for autonomous renewable energy microgrid management. Targets Raspberry Pi 4/5 deployment in Colombia's Zonas No Interconectadas (ZNI) -- disconnected communities with solar+battery+diesel hybrid microgrids.

- **Languages**: Rust (kernel daemon, production), Python 3.11+ (reference implementation, forecast worker, simulation)
- **Runtime**: Raspberry Pi OS Lite (64-bit), ARM64
- **Design principle**: Agentic-native — the LLM IS the reasoning core, tools for sensing/dispatch/KG, deterministic safety gates. Edge-first, offline-capable. No cloud dependency in the critical control path.
- **Agentic architecture**: See [docs/architecture.md](docs/architecture.md) for the authoritative design doc (BitNet 2B for edge reasoning, tiered reasoning hierarchy, EGRI self-improvement loop).
- **Research context**: Universidad de los Andes, TICSw research group (A1, Minciencias)

## Architecture

### Module Map

```
kernel/src/              Rust daemon (production target, ~15MB binary)
+-- main.rs              Tokio async runtime & agentic control loop
+-- devices.rs           Hardware abstraction (Modbus RTU, VE.Direct)
+-- dispatch.rs          LP optimizer (good_lp)
+-- autonomic.rs         Safety gates & homeostasis controller
+-- knowledge.rs         Knowledge graph (rusqlite/SQLite)
+-- journal.rs           Event journal (redb, crash-safe — Lago equivalent)
+-- ml_bridge.rs         IPC bridge to Python ML worker
+-- dashboard.rs         Local dashboard (axum + HTMX)
+-- sync.rs              MQTT fleet sync (rumqttc)
+-- config.rs            TOML config loader (serde)
+-- tools/               Protocol drivers (modbus.rs, vedirect.rs)

forecast/                Forecast ML worker (spawned on demand by kernel)
+-- forecast.py          TFLite LSTM inference (solar & demand)
+-- worker.py            IPC worker process (stdin/stdout or Unix socket)

reference/src/           Frozen Python reference implementation (read-only)
+-- agent.py             Main async control loop & orchestrator
+-- devices.py           Hardware abstraction (Modbus RTU, VE.Direct, simulated)
+-- dispatch.py          LP optimizer via scipy.optimize.linprog
+-- knowledge.py         SQLite knowledge graph for territorial context
+-- sync.py              MQTT fleet sync with store-and-forward queue
+-- autonomic.py         Safety constraints & homeostasis controller
+-- dashboard.py         Local web dashboard (FastAPI, lightweight)

reference/tests/         pytest test suite for reference implementation

simulation/              Simulation & benchmarking framework
+-- run.py               Simulation runner
+-- scenario.py          Scenario definitions (climate zones, equipment configs)
+-- controllers.py       Control strategies for benchmarking
+-- metrics.py           Performance metrics & comparison

config/
+-- site.example.toml    Site identity, grid topology, autonomic setpoints
+-- devices.toml         Device registry (per-deployment, not committed)

data/                    Runtime data (gitignored)
+-- models/              TFLite model files
+-- sync-queue/          Offline MQTT queue (SQLite WAL)

.control/                Control metalayer
+-- policy.yaml          Machine-readable setpoints, gates, monitors
+-- commands.yaml        Canonical command catalog
+-- topology.yaml        Repository module map
+-- egri-journal.jsonl   EGRI evaluation log
+-- schemas/             Typed JSON schemas + knowledge graph SQL
+-- evals/               Evaluation metric definitions

deploy/                  Systemd units, Dockerfile, install scripts
scripts/                 Hooks, health checks, utilities
docs/                    Architecture, genome, conversations
```

### Control Loop Hierarchy

The agent runs three nested control loops at different rates:

| Loop | Rate | Responsibility |
|------|------|----------------|
| Safety monitor | 100ms | SOC bounds, fault detection, emergency load shedding |
| Device polling | 1s | Read all sensors/devices, update state, log telemetry |
| Forecast + dispatch | 15min | ML inference, LP optimization, schedule next interval |

The safety monitor always runs fastest and can override any dispatch decision. This is the core invariant -- safety constraints are never relaxed by the optimizer.

### Data Flow

```
Sensors (Modbus/VE.Direct)
    |
    v
DeviceRegistry.read_all()  -- 1s poll
    |
    v
TelemetryLogger.record()   -- append to SQLite journal
    |
    +---> Forecaster.predict()  -- every 15 min
    |         |
    |         v
    |    Dispatcher.optimize()  -- LP solver
    |         |
    |         v
    |    DispatchPlan { solar_kw, battery_kw, diesel_kw, shed_loads }
    |         |
    +---> AutonomicController.validate(plan)  -- safety gate
              |
              v
         DeviceRegistry.apply(validated_plan)
              |
              v
         SyncClient.enqueue(telemetry)  -- store-and-forward to MQTT
```

## Conventions

### Code

- **Type hints** on all function signatures and return types
- **asyncio** for all I/O (device reads, network, file writes)
- **Structured JSON logging** via Python `logging` + JSON formatter. No `print()` statements.
- **TOML** for all configuration files
- **SQLite** for persistence (knowledge graph, telemetry journal, sync queue)
- **No cloud dependencies** in the core control path. Cloud features (fleet sync, remote dashboard) are optional modules that degrade gracefully.

### Naming

- Modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Config keys: `snake_case` (TOML convention)

### Error Handling

- Device read failures return a zero-power reading with `DeviceStatus.OFFLINE` -- never crash the control loop
- Network failures queue data locally -- never block the agent
- Safety constraint violations trigger immediate load shedding -- never wait for the optimizer

### Dependencies

**Rust kernel** (see `kernel/Cargo.toml`):
- `tokio` -- async runtime
- `tokio-modbus` -- Modbus RTU communication
- `rumqttc` -- MQTT client for fleet sync
- `redb` -- event journal (crash-safe embedded DB)
- `rusqlite` -- knowledge graph (SQLite)
- `axum` -- local dashboard
- `good_lp` -- LP dispatch optimizer
- `serde` + `toml` -- config parsing
- `tracing` -- structured logging
- `sd-notify` -- systemd watchdog integration

**Python reference/forecast** (must run on RPi):
- `numpy` -- numerical operations
- `scipy` -- LP solver (`scipy.optimize.linprog`)
- `tflite-runtime` -- ML inference (not full TensorFlow)
- `pymodbus` -- Modbus RTU communication
- `paho-mqtt` -- MQTT client for fleet sync
- `fastapi` + `uvicorn` -- local dashboard
- `aiosqlite` -- async SQLite access

Optional:
- `serial-asyncio` -- VE.Direct serial protocol
- `RPi.GPIO` -- GPIO access on Raspberry Pi

Dev:
- `pytest` + `pytest-asyncio` -- testing
- `ruff` -- linting and formatting
- `mypy` -- type checking

## Bstack Primitives

Mapping the 7 bstack primitives to this project:

| # | Primitive | Implementation | Status |
|---|-----------|----------------|--------|
| P1 | Conversation Bridge | `docs/conversations/` -- session logs indexed here | Active |
| P2 | Control Gate | `autonomic.rs` / `autonomic.py` -- safety constraints as the control gate. SOC limits, diesel runtime caps, load shedding priority are hard gates that the ML optimizer cannot override. | Active |
| P3 | Spaces Integration | N/A -- standalone edge project, no SpacetimeDB dependency | N/A |
| P4 | Asset Delivery | N/A -- no web assets to deliver | N/A |
| P5 | Linear Tickets | GitHub Issues for task tracking | Active |
| P6 | PR Pipeline | GitHub Actions CI -- pytest + ruff on every PR | Active |
| P7 | Parallel Agents | Simulation mode supports multiple simulated sites running concurrently for fleet testing | Active |

## Control Kernel Integration

The Autonomic module (`kernel/src/autonomic.rs` in Rust, `reference/src/autonomic.py` in Python) IS the control kernel for this project. It implements a homeostasis controller inspired by biological autonomic nervous systems. In the agentic architecture, Autonomic is Tier 1 (deterministic reflex) -- it validates every tool call from the LLM reasoning core (Tier 2) and has absolute veto power. See [docs/architecture.md](docs/architecture.md) for the tiered reasoning hierarchy (Tier 1: Reflex, Tier 2: BitNet 2B, Tier 3: Qwen 3B, Tier 4: Claude API).

### Setpoints

Defined in `site.toml` under `[autonomic]`:

```toml
[autonomic]
min_soc_pct = 15          # Hard floor -- load shedding below this
max_soc_pct = 95          # Hard ceiling -- curtail charging above this
diesel_start_soc = 20     # Diesel auto-start threshold
diesel_stop_soc = 60      # Diesel auto-stop threshold
renewable_target = 0.85   # Target renewable fraction
```

### Safety Gates

| Gate | Trigger | Action | Override |
|------|---------|--------|----------|
| G1: SOC Floor | SOC < `min_soc_pct` | Shed non-priority loads in order | NEVER |
| G2: SOC Ceiling | SOC > `max_soc_pct` | Curtail solar charging | NEVER |
| G3: Diesel Limit | Runtime > 8h/day | Force diesel stop, shed if needed | NEVER |
| G4: Fault Isolate | Device fault detected | Disconnect faulted device | NEVER |

### Feedback Loop

```
Predicted (forecast)  vs  Actual (telemetry)
         |                      |
         +-------> Error -------+
                     |
                     v
            Model Adaptation
            (retrain LSTM weights on-device, weekly)
```

### Invariant

**Safety constraints are NEVER overridden by ML predictions or optimizer outputs.** The autonomic controller has absolute veto power over any dispatch plan. This is the single most important design principle in the system.

## Testing

```bash
# Run all tests (Rust + Python)
make test

# Run with verbose output
pytest reference/tests/ -v

# Run specific test module
pytest reference/tests/test_devices.py

# Run Rust kernel tests
cd kernel && cargo test

# Run in simulation mode for integration testing
make simulate

# Run simulation framework benchmarks
python -m simulation.run
```

### Test Strategy

- **Unit tests**: Each module tested in isolation with simulated devices
- **Integration tests**: Full control loop running in simulation mode
- **No hardware required for CI**: All device interactions go through `SimulatedDevice` in test/CI environments
- **Deterministic randomness**: Tests seed the random number generator for reproducible simulated readings

## Self-Governance

This project is a **self-governing autonomous agent**. See [docs/genome.md](docs/genome.md) for the full specification.

### Governance Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Invariants, architecture, conventions (this file) |
| `AGENTS.md` | Operational rules, boundaries, self-improvement protocol |
| `.control/policy.yaml` | Machine-readable setpoints, gates, monitors, EGRI config |
| `.claude/settings.json` | Claude Code hooks (session start/stop, control gates) |
| `docs/genome.md` | Complete genome specification for autonomous operation |

### Hooks (Claude Code Integration)

| Event | Hook | Purpose |
|-------|------|---------|
| `SessionStart` | `scripts/hooks/session-start.sh` | Ground agent in current state (tests, build, git, EGRI) |
| `Stop` | `scripts/hooks/session-stop.sh` | Log EGRI evaluation metrics to journal |
| `PreToolUse` | `scripts/hooks/control-gate.sh` | Block force push, warn on secrets/safety edits |

### Control Loops

| Loop | Rate | Script/Module | Purpose |
|------|------|---------------|---------|
| L0 | 20s | systemd watchdog | Heartbeat — restart on hang |
| L1 | 5s | `kernel/src/main.rs` | Dispatch — sense→predict→optimize→actuate |
| L2 | 6h | `scripts/self-monitor.sh` | Self-monitor — system + agent + EGRI health |
| L3 | daily | EGRI in `session-stop.sh` | Evaluate — predicted vs actual |
| L4 | weekly | ML retrain | Adapt — fine-tune models on local data |
| L5 | opportunistic | `sync.rs` | Fleet sync — when connected |
| L6 | weekly/on-demand | Claude Code session | Meta-reason — "Am I improving?" |

### EGRI Journal

Metrics logged to `.control/egri-journal.jsonl` after each session:
- `test_count`: total passing tests (Rust + Python)
- `kernel_warnings`: cargo check warning count
- `todo_count`: remaining TODOs in Rust kernel
- `files_changed`: files modified in session

Direction: test_count↑, kernel_warnings↓, todo_count↓

## Commands

```bash
make test            # All tests (39 Rust + 116 Python)
make test-rust       # Rust kernel tests only
make test-python     # Python reference tests only
make sim             # Simulation comparison (3 sites x 3 controllers)
make simulate        # Run reference agent in simulation mode
make control-audit   # Verify metalayer compliance
make bstack-check    # Full harness validation
make lint            # Ruff linter
make kernel-check    # Verify Rust kernel compiles
make kernel-build    # Build Rust kernel (release)
make deploy-rpi      # Deploy to RPi via SSH
make health          # Run health-check.sh
make help            # Show all targets
```
