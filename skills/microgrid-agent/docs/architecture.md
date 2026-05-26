# Architecture Reference

> The microgrid agent is not a deterministic system that occasionally calls an ML model.
> It is an autonomous AI agent -- an instance of Life/Arcan -- that reasons about its
> environment using an LLM and acts on the physical world through tools.
> The LSTM, the LP solver, the KG -- these are tools the agent uses, not the agent itself.

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [The Three Planes](#2-the-three-planes)
3. [Agent as Controller](#3-agent-as-controller)
4. [Tiered Reasoning Hierarchy](#4-tiered-reasoning-hierarchy)
5. [BitNet: Edge Reasoning](#5-bitnet-edge-reasoning)
6. [Control Loop Timing](#6-control-loop-timing)
7. [Data Flow -- From Photon to Decision](#7-data-flow----from-photon-to-decision)
8. [Hardware Abstraction Layer](#8-hardware-abstraction-layer)
9. [Dispatch Optimizer (LP Formulation)](#9-dispatch-optimizer-lp-formulation)
10. [Knowledge Graph](#10-knowledge-graph)
11. [Forecasting Engine](#11-forecasting-engine)
12. [EGRI Self-Improvement Loop](#12-egri-self-improvement-loop)
13. [Fleet Architecture](#13-fleet-architecture)
14. [Fleet Sync Protocol](#14-fleet-sync-protocol)
15. [Security](#15-security)
16. [Deployment Architecture](#16-deployment-architecture)
17. [Technology Stack](#17-technology-stack)
18. [Standards Alignment](#18-standards-alignment)
19. [Continuous Progress](#19-continuous-progress)

---

## 1. Design Philosophy

### The Conceptual Shift

**What we had (ML-centric framing):**
```
Rust control loop -> calls LSTM for forecast -> calls LP for dispatch -> actuates
The LLM is an afterthought, bolted on for "smart features"
```

**What we actually mean (agentic-native framing):**
```
Life/Arcan agent -> reasons about the microgrid -> uses tools to sense, predict,
optimize, and actuate -> learns from outcomes -> adapts its own behavior
The LLM IS the reasoning core. Everything else is a tool.
```

This maps directly onto the Life Agent OS stack:
- **Arcan** = agent runtime (manages lifecycle, tools, memory)
- **Praxis** = tool execution (the agent's hands -- Modbus, LP solver, KG queries)
- **Lago** = event journal (the agent's episodic memory)
- **Autonomic** = homeostasis (the agent's brainstem -- safety reflexes that override reasoning)
- **The LLM** = the agent's cortex -- reasons about what to do given context

The microgrid agent is a Life agent with energy-domain tools. The LLM doesn't "assist" the control loop -- it IS the decision maker, constrained by Autonomic safety gates.

### Design Principles

1. **Edge-first**: Every feature must work on a Raspberry Pi with no internet connection. Cloud is optional.
2. **Safety-absolute**: The autonomic safety layer has unconditional veto over all ML/optimizer decisions.
3. **Fail-open-safe**: Any component failure degrades to a safe state (diesel backup or load shedding), never to uncontrolled operation.
4. **Store-and-forward**: All telemetry is persisted locally first, synced to fleet when connectivity allows. No data loss.
5. **Minimal footprint**: Total memory <512MB, disk <1GB, CPU <5% during normal operation on RPi 5.

### Why LLM-as-Controller, Not ML-as-Feature

| Dimension | ML-as-Feature (old framing) | LLM-as-Controller (agentic) |
|-----------|---------------------------|---------------------------|
| **Decision maker** | LP solver (deterministic) | LLM (reasons about context) |
| **LSTM forecast** | The brain | A tool the brain uses |
| **KG query** | Feature extraction | The agent asking itself a question |
| **Anomaly response** | Threshold -> alert | Agent reasons about cause + action |
| **Adaptation** | Retrain model daily | Agent adjusts own setpoints based on EGRI |
| **Novel situations** | Fails (not in training data) | Reasons from first principles |
| **Explanation** | None (black box) | Natural language: "I started diesel because..." |
| **Community interface** | Dashboard with numbers | Conversation in Spanish |

**The killer example -- a novel failure:**

```
Scenario: Solar output drops 40% despite clear sky. Never happened before.

ML-as-Feature response:
  LSTM: "Forecast was 350W/m2, actual is 210W/m2" (observes, can't explain)
  LP solver: starts diesel (correct but doesn't know why solar dropped)
  System: logs anomaly, waits for technician

LLM-as-Controller response:
  Agent reasons:
    "Solar is at 60% of expected despite clear sky and 32C.
     Possible causes I can check:
     1. Panel soiling -- use get_weather() to check if dust storm recently
     2. Inverter derating -- read_sensors() shows inverter at 85C (high!)
     3. Partial shading -- time is 16:00, tree shadow possible at this angle

     Inverter temperature is 85C, threshold is 65C for derating.
     This explains the 40% drop -- thermal derating.

     Action: reduce load to lower inverter stress, alert maintenance
     to check ventilation, log finding for pattern detection."

  -> set_dispatch(reduce_solar_draw=True)
  -> alert("warning", "Inverter thermal derating -- check cooling")
  -> log_insight("Thermal derating at 85C explains 40% solar loss")
```

No LSTM or LP solver can do this. It requires causal reasoning across domains (weather + hardware + physics + operations).

---

## 2. The Three Planes

The system operates across three planes, each with different time horizons,
failure modes, and language choices:

```
+===============================================================================+
|                                                                               |
|  PLANE 3: INTELLIGENCE (cloud/IPSE server)         TypeScript + Python        |
|  +------------------------------------------------------------------------+   |
|  |  Fleet Dashboard (Next.js)  |  LLM Briefings (Claude API)             |   |
|  |  Transfer Learning Engine   |  Diesel Logistics Optimizer              |   |
|  |  Anomaly Detection (fleet)  |  Predictive Maintenance                  |   |
|  |  Time Series DB (DuckDB)    |  MQTT Broker (NanoMQ)                    |   |
|  +--------------------------------------+---------------------------------+   |
|                                         |                                     |
|  - - - - - - - - MQTT/TLS - - - - - - -+- - - INTERMITTENT - - - - - - - -   |
|                                         |                                     |
|  PLANE 2: ADAPTATION (on-device)                    Python subprocess         |
|  +------------------------------------------------------------------------+   |
|  |  ML Forecasting (TFLite)    |  Model Retraining (daily)                |   |
|  |  Data Processing Pipeline   |  Knowledge Graph Learning                |   |
|  |  Fleet Sync Daemon          |  Anomaly Flagging (local)                |   |
|  +--------------------------------------+---------------------------------+   |
|                                         | IPC (Unix socket / subprocess)      |
|  PLANE 1: CONTROL (on-device, always running)       Rust kernel daemon        |
|  +------------------------------------------------------------------------+   |
|  |  Sensor Reading (Modbus/UART)|  LP Dispatch Optimization               |   |
|  |  Autonomic Safety Gates      |  Event Journal (redb)                   |   |
|  |  Actuator Commands           |  Local Dashboard (axum + HTMX)          |   |
|  |  Watchdog (systemd/HW)       |  KG Query (rusqlite)                    |   |
|  +------------------------------------------------------------------------+   |
|                                         |                                     |
|  - - - - - - - - - - RS-485 / UART / GPIO - - - - - - - - - - - - - - - -    |
|                                         |                                     |
|  PLANE 0: PHYSICS                                   Wires and photons         |
|  +------------------------------------------------------------------------+   |
|  |  Solar Panels  |  Battery Bank  |  Diesel Generator  |  Loads          |   |
|  |  Inverters     |  Charge Ctrl   |  Genset Controller  |  Meters        |   |
|  +------------------------------------------------------------------------+   |
|                                                                               |
+===============================================================================+
```

### Failure Isolation Between Planes

```
If Plane 3 dies (cloud/fleet):
  -> Plane 2 continues (local ML, local learning)
  -> Plane 1 continues (dispatch, safety)
  -> Lights stay on

If Plane 2 dies (Python ML worker):
  -> Plane 1 continues with last-known-good forecast
  -> Falls back to persistence prediction (yesterday=today)
  -> Falls back to rule-based dispatch
  -> Lights stay on

If Plane 1 dies (Rust kernel):
  -> systemd restarts in 5s (WatchdogSec=30s)
  -> If 4 crashes in 3 min -> full RPi reboot
  -> During restart: last dispatch commands hold (inverter keeps state)
  -> Lights stay on (briefly degraded)

If Plane 0 dies (hardware failure):
  -> Kernel detects via sensor timeout
  -> Flags anomaly, notifies fleet
  -> Requires physical maintenance
  -> This is the only failure that affects power
```

---

## 3. Agent as Controller

```
+======================================================================+
|                                                                      |
|  LIFE/ARCAN AGENT INSTANCE                                           |
|  (one per microgrid site, running on RPi)                            |
|                                                                      |
|  +----------------------------------------------------------------+  |
|  |  REASONING CORE (LLM -- BitNet 2B or Qwen 2.5 3B)             |  |
|  |                                                                |  |
|  |  System prompt:                                                |  |
|  |    "You are an autonomous energy agent managing a {solar_kwp}  |  |
|  |     kWp solar + {battery_kwh} kWh battery + {diesel_kw} kW    |  |
|  |     diesel microgrid at {site_name}. Your goal is to           |  |
|  |     maximize renewable energy use, minimize diesel, and        |  |
|  |     ensure priority loads never lose power."                   |  |
|  |                                                                |  |
|  |  Context window (4096 tokens):                                 |  |
|  |    - Current state: SOC, solar, load, diesel fuel, time        |  |
|  |    - Recent history: last 4h of readings (compressed)          |  |
|  |    - KG context: community calendar, equipment relations       |  |
|  |    - Last 3 decisions + outcomes (EGRI feedback)               |  |
|  |    - Active alerts and anomalies                               |  |
|  |                                                                |  |
|  |  Reasoning cycle (every 5 minutes):                            |  |
|  |    1. read_sensors() -> current state                          |  |
|  |    2. get_forecast() -> next 24h (LSTM tool)                   |  |
|  |    3. query_kg("what affects operations now?")                 |  |
|  |    4. THINK about the situation                                |  |
|  |    5. Call dispatch tool OR adjust setpoints OR flag anomaly   |  |
|  |    6. Log reasoning to journal                                 |  |
|  +----------------------------------------------------------------+  |
|                    | tool calls                                      |
|                    v                                                  |
|  +----------------------------------------------------------------+  |
|  |  PRAXIS -- Tool Execution Layer                                |  |
|  |                                                                |  |
|  |  SENSE tools (read-only):                                      |  |
|  |    read_sensors()      -> SensorReadings (Modbus/VE.Direct)    |  |
|  |    get_forecast()      -> 24h generation + demand (LSTM)       |  |
|  |    query_kg(question)  -> graph traversal result               |  |
|  |    get_battery_health()-> degradation estimate                 |  |
|  |    get_fuel_level()    -> diesel tank status                   |  |
|  |    get_weather()       -> temperature, irradiance, rain        |  |
|  |                                                                |  |
|  |  ACT tools (write, validated by Autonomic):                    |  |
|  |    set_dispatch(solar, battery, diesel, shed)                  |  |
|  |    adjust_setpoint(key, value)  -> modify autonomic params     |  |
|  |    start_diesel() / stop_diesel()                              |  |
|  |    set_load_priority(ordered_list)                             |  |
|  |                                                                |  |
|  |  COMMUNICATE tools:                                            |  |
|  |    alert(severity, message)     -> fleet + local dashboard     |  |
|  |    log_insight(text)            -> reasoning journal           |  |
|  |    request_maintenance(what)    -> fleet maintenance queue     |  |
|  |    answer_operator(question)    -> local dashboard response    |  |
|  |                                                                |  |
|  |  FORBIDDEN (no tool exists):                                   |  |
|  |    override_safety()  <- DOES NOT EXIST. Cannot be called.     |  |
|  |    modify_autonomic_gates() <- DOES NOT EXIST.                 |  |
|  |    The agent literally cannot bypass safety.                   |  |
|  +----------------------------------------------------------------+  |
|                    | every tool call validated                        |
|                    v                                                  |
|  +----------------------------------------------------------------+  |
|  |  AUTONOMIC -- Safety Gates (Rust, deterministic, not LLM)      |  |
|  |                                                                |  |
|  |  G1: SOC >= min_soc_pct          -> block discharge            |  |
|  |  G2: SOC <= max_soc_pct          -> block charge               |  |
|  |  G3: diesel_hours < max/day      -> block diesel start         |  |
|  |  G4: priority_loads_served       -> block non-essential shed   |  |
|  |  G5: setpoint_in_safe_range      -> reject unsafe adjustments  |  |
|  |                                                                |  |
|  |  Autonomic is NOT an LLM. It is Rust code with hard limits.    |  |
|  |  The LLM reasons. Autonomic enforces. This is the harness.     |  |
|  +----------------------------------------------------------------+  |
|                                                                      |
|  +----------------------------------------------------------------+  |
|  |  LAGO -- Event Journal (redb, crash-safe)                      |  |
|  |                                                                |  |
|  |  Every reasoning cycle logged:                                 |  |
|  |    { timestamp, state, tools_called, reasoning, decision,      |  |
|  |      outcome_after_5min, autonomic_overrides }                 |  |
|  |                                                                |  |
|  |  This is the agent's episodic memory. Fed back into the        |  |
|  |  LLM context as "last 3 decisions + outcomes" for EGRI.        |  |
|  +----------------------------------------------------------------+  |
|                                                                      |
+======================================================================+
```

---

## 4. Tiered Reasoning Hierarchy

```
+-----------------------------------------------------------+
|  TIER 1: REFLEX (Rust, <1ms, always available)             |
|                                                            |
|  Autonomic safety gates. No reasoning. Pure constraint     |
|  enforcement. SOC < 20% -> diesel starts. Period.          |
|  This is the brainstem.                                    |
+------------------------------------------------------------+
|  TIER 2: FAST REASONING (BitNet 2B, ~30ms, on-device)      |
|                                                            |
|  Every 5 minutes: "given current state and forecast,       |
|  what's the right dispatch?" Tool calling, structured      |
|  output, simple anomaly detection.                         |
|                                                            |
|  0.4 GB RAM. 0.028 J/token. Runs on solar power.          |
|  This is the fast, intuitive brain.                        |
+------------------------------------------------------------+
|  TIER 3: DEEP REASONING (Qwen 3B, ~150ms, on-device)      |
|                                                            |
|  Triggered by anomalies, daily EGRI evaluation, complex    |
|  situations. Multi-step causal reasoning. Can swap in      |
|  when BitNet flags uncertainty.                            |
|                                                            |
|  2.2 GB RAM. Only loaded when needed. Sleeps otherwise.    |
|  This is the deliberate, analytical brain.                 |
+------------------------------------------------------------+
|  TIER 4: STRATEGIC (Claude API, when connected)            |
|                                                            |
|  Fleet-level analysis. Cross-site patterns. Natural        |
|  language reports. Policy recommendations. Deep EGRI       |
|  evaluation across the entire fleet.                       |
|                                                            |
|  Unlimited capability. Only available when online.         |
|  This is the collective intelligence.                      |
+------------------------------------------------------------+
```

Each tier can operate independently. If Tier 4 is offline, Tier 3 handles complex reasoning. If Tier 3 isn't loaded, Tier 2 handles routine dispatch. If even Tier 2 crashes, Tier 1 (Autonomic) keeps the lights on with pure Rust reflex rules.

**Control-theoretic hierarchy applied to cognition:**
- Inner loop (fast, deterministic) -> Autonomic
- Mid loop (adaptive, learned) -> BitNet 2B
- Outer loop (deliberate, analytical) -> Qwen 3B
- Meta loop (strategic, reflective) -> Claude

Faster loops override slower ones on safety. Slower loops improve faster ones over time.

---

## 5. BitNet: Edge Reasoning

The core challenge: LLMs are large. RPi 5 has 8GB RAM. How do we fit a capable reasoning core?

### BitNet -- 1.58-bit Ternary Models

Microsoft's BitNet uses weights of {-1, 0, +1} instead of floating point:
- **No floating-point multiplication** -- just addition/subtraction
- **1.58 bits per weight** vs 4 bits (Q4) or 16 bits (FP16)
- **Optimized kernels** for ARM NEON (RPi's instruction set)

### Performance on Edge Hardware

| Model | Weights | Memory | Decode Latency | Energy/token | Quality (ARC) |
|-------|---------|--------|---------------|-------------|---------------|
| **BitNet 2B** | 1.58-bit | **0.4 GB** | **29 ms** | **0.028 J** | 49.9 |
| Qwen 2.5 1.5B Q4 | 4-bit | 1.2 GB | ~80 ms | ~0.25 J | 46.3 |
| Llama 3.2 3B Q4 | 4-bit | 2.0 GB | ~150 ms | ~0.40 J | ~50 |
| Qwen 2.5 3B Q4 | 4-bit | 2.2 GB | ~170 ms | ~0.45 J | ~55 |

**BitNet 2B uses 3x less memory, is 3-5x faster, and uses 9x less energy per token than comparable quantized models.** On a solar-powered RPi where every watt matters, this is transformative.

### What BitNet 2B Can and Can't Do

| Task | Feasible at 2B? | Notes |
|------|-----------------|-------|
| Tool selection ("which tool do I call?") | YES | Routing/classification works at small scale |
| Structured output (JSON dispatch decisions) | YES | Format following is good |
| Anomaly classification ("is this normal?") | YES | Pattern matching works |
| Simple causal reasoning | PARTIAL | 1-2 hop reasoning OK, complex chains fail |
| Natural language operator Q&A | PARTIAL | Short answers OK, long explanations weak |
| EGRI self-evaluation | PARTIAL | Can compare predicted vs actual, weak at deep analysis |
| Complex novel situation reasoning | NO | Need 3B+ for multi-step causal chains |

---

## 6. Control Loop Timing

### Multi-Rate Control Loop

```
+------------------------------------------------------------------+
|                                                                  |
|   +------------------+                                           |
|   | 100ms Loop       |  SAFETY MONITOR                          |
|   |  autonomic       |  - Check SOC bounds                      |
|   |                  |  - Detect device faults                   |
|   |                  |  - Emergency load shedding                |
|   |                  |  - Diesel runtime limits                  |
|   +--------+---------+                                           |
|            | safety_ok?                                           |
|            v                                                     |
|   +------------------+                                           |
|   | 1s Loop          |  DEVICE POLLING                           |
|   |  devices         |  - Read all Modbus/VE.Direct devices      |
|   |  telemetry       |  - Update in-memory state                 |
|   |                  |  - Append to telemetry journal             |
|   |                  |  - Push to local dashboard                 |
|   +--------+---------+                                           |
|            | state_snapshot                                       |
|            v                                                     |
|   +------------------+                                           |
|   | 5min Loop        |  AGENT REASONING (Tier 2 LLM)             |
|   |  reasoning core  |  - Build context from state + KG + history|
|   |  dispatch        |  - LLM reasons + calls tools               |
|   |  knowledge       |  - Autonomic validates every tool call     |
|   |                  |  - Log reasoning to Lago journal           |
|   +------------------+  - Enqueue telemetry for fleet sync        |
|                                                                  |
+------------------------------------------------------------------+
```

### Loop Timing Guarantees

| Loop | Period | Max Jitter | Deadline Miss Action |
|------|--------|-----------|---------------------|
| Safety | 100ms | 50ms | Log warning, continue next tick |
| Polling | 1s | 500ms | Skip failed devices, mark OFFLINE |
| Reasoning | 5min | 30s | Use previous dispatch plan |

### Timing Diagram

```
         1s        5s        1min       15min      1hr       1day
         |         |          |           |          |          |
SAFETY   ############################################################
         | Always on. HW watchdog. Never stops.                |
         |                                                      |
SENSE    #-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
         | 1 Hz sensor polling. Ring buffer fills.              |
         |                                                      |
DISPATCH ---#----#----#----#----#----#----#----#----#----#----#--
         |   5s cycle. LP or rules. Uses latest forecast.       |
         |                                                      |
PUBLISH  ----------#----------#----------#----------#----------#
         |         60s metric publish to fleet (or queue).      |
         |                                                      |
FORECAST --------------------------#----------------------------#
         |                        15min. Spawn Python. TFLite.  |
         |                                                      |
LEARN    ---------------------------------------------------------#-
         |                                                  24h|
         |                        Fine-tune model. Update KG.  |
         |                                                      |
FLEET    - - - - -#- - - - - - - - - - -#- - - - - - - - - - - -
         |   Opportunistic. When connectivity exists.           |
```

The safety loop runs as a high-priority task. If a device read blocks (e.g., Modbus timeout), the safety loop continues independently because it reads from in-memory state, not directly from hardware.

---

## 7. Data Flow -- From Photon to Decision

```
TIME ---------------------------------------------------------------->

t=0s        t=0.1s      t=0.5s       t=1s         t=5s
PHOTON      SENSOR      KERNEL       JOURNAL      DISPATCH
  |           |           |            |             |
  v           v           v            v             v
+-----+   +------+   +-------+   +--------+   +----------+
|Solar|-->|Modbus|-->|Parse  |-->|Append  |-->|LP solve  |
|panel|   |read  |   |decode |   |to redb |   |min diesel|
|     |   |reg   |   |->State|   |journal |   |+ unserved|
+-----+   |40071 |   |Vector |   |        |   |          |
          +------+   +---+---+   +--------+   +----+-----+
                         |                          |
                         v                          v
                    +----------+              +----------+
                    |Ring      |              |Autonomic |
                    |buffer    |              |check:    |
                    |(last 24h)|              |SOC ok?   |
                    |for ML    |              |diesel ok?|
                    +----------+              |loads ok? |
                                              +----+-----+
                                                   |
                                                   v
t=5s         t=5.1s       t=60s          t=900s         t=86400s
ACTUATE      DASHBOARD    PUBLISH        FORECAST        RETRAIN
  |            |            |               |               |
  v            v            v               v               v
+------+   +-------+   +--------+   +-----------+   +----------+
|Modbus|   |Update |   |MQTT    |   |Spawn      |   |Spawn     |
|write |   |status |   |publish |   |Python:    |   |Python:   |
|setpts|   |page   |   |metrics |   |TFLite     |   |fine-tune |
|      |   |       |   |to fleet|   |LSTM       |   |last 2    |
|Start |   |SOC: 45|   |or queue|   |inference  |   |layers    |
|diesel|   |Gen: 12|   |if off- |   |24h ahead  |   |with      |
|at 3kW|   |Load: 8|   |line    |   |           |   |7d data   |
+------+   +-------+   +--------+   +-----------+   +----------+
```

---

## 8. Hardware Abstraction Layer

All device interaction goes through the `EnergyDevice` trait (Rust) / ABC (Python):

```
                        EnergyDevice (trait/ABC)
                        +------------------+
                        | read_power_kw()  |
                        | read_energy_kwh()|
                        | read_status()    |
                        | set_power_limit()|
                        | start() / stop() |
                        +--------+---------+
                                 |
                +----------------+----------------+
                |                |                |
        ModbusRtuDevice   VeDirectDevice   SimulatedDevice
        (RS-485)          (Serial TTL)     (Software)
```

### Protocol Details

**Modbus RTU:**
- Half-duplex RS-485 bus, 9600 baud default
- 32-bit values read as two consecutive 16-bit registers (big-endian)
- Configurable register addresses per device (power, energy, status, control)
- Async client via `tokio-modbus` (Rust) / `pymodbus.client.AsyncModbusSerialClient` (Python)
- 3-second timeout per read, retry once on failure

**VE.Direct:**
- Victron proprietary text protocol over 19200 baud serial
- Continuous streaming of key-value frames (`KEY\tVALUE\r\n`)
- Parsed in a background async task, latest values stored in-memory
- Read-only protocol: no control commands available via VE.Direct text mode
- Key registers: `PPV` (panel power), `V` (voltage), `I` (current), `CS` (state), `H19` (yield)

**Simulated:**
- Software-only device for testing and development
- Solar: sinusoidal curve peaking at noon, proportional to `base_power_kw`
- Load: diurnal pattern (40% baseline, 100% during 07:00-22:00)
- Battery: tracks energy integral over time
- Gaussian noise added at configurable `noise_pct` level

### Device Registry

The `DeviceRegistry` loads `config/devices.toml` and instantiates the correct device type for each entry:
- `read_all()`: Concurrent async reads of all devices, returns `dict[str, DeviceReading]`
- `by_type(type)`: Filter devices by type (solar, battery, diesel, load)
- `get(id)`: Retrieve a specific device by ID

---

## 9. Dispatch Optimizer (LP Formulation)

### Problem Formulation

At each dispatch interval, the dispatcher solves a linear program:

```
Minimize:
    w_diesel * P_diesel + w_battery_wear * |P_battery| + w_shed * sum(P_shed)

Subject to:
    P_solar + P_battery_discharge + P_diesel = P_demand - P_shed    (power balance)
    0 <= P_solar <= forecast_solar                                   (solar availability)
    -C_charge <= P_battery <= C_discharge                            (battery C-rates)
    0 <= P_diesel <= diesel_capacity                                 (diesel limits)
    SOC_min <= SOC + integral(P_battery) <= SOC_max                  (SOC bounds)
    P_shed >= 0                                                      (non-negative shedding)
    shed respects priority order                                     (priority constraint)
```

### Priority Stack

The dispatcher follows a strict priority order:

1. **Solar** (zero marginal cost, always preferred)
2. **Battery discharge** (finite cycles, small wear cost)
3. **Diesel** (highest cost: fuel + maintenance + emissions)
4. **Load shedding** (last resort, follows `priority_loads` order from `site.toml`)

### Solver

Uses `good_lp` (Rust) / `scipy.optimize.linprog` (Python) with the HiGHS solver backend. Typical solve time: <10ms for a single-interval problem, <100ms for a 24-hour rolling horizon (96 intervals).

---

## 10. Knowledge Graph

### Purpose

The knowledge graph stores territorial context that improves forecasting accuracy. Unlike generic weather APIs, it encodes local patterns specific to each community: when the market operates, which months bring festivals, how fishing seasons affect electricity demand.

### Schema

Stored in SQLite (`data/knowledge.db`), total size <100MB even after years of operation.

```sql
-- Community calendar events that affect demand
CREATE TABLE calendar_events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,  -- 'market', 'festival', 'holiday', 'custom'
    name TEXT,
    recurrence TEXT,           -- cron-like pattern or 'once'
    demand_factor REAL,        -- multiplier on baseline demand (e.g., 1.3 = +30%)
    start_hour INTEGER,
    end_hour INTEGER
);

-- Weather patterns learned from local observations
CREATE TABLE weather_patterns (
    id INTEGER PRIMARY KEY,
    month INTEGER NOT NULL,
    avg_irradiance_kwh_m2 REAL,
    avg_cloud_cover_pct REAL,
    avg_temperature_c REAL,
    rain_probability REAL
);

-- Device performance degradation tracking
CREATE TABLE device_performance (
    device_id TEXT NOT NULL,
    date TEXT NOT NULL,
    expected_output_kwh REAL,
    actual_output_kwh REAL,
    efficiency_ratio REAL,
    PRIMARY KEY (device_id, date)
);

-- Operational decisions and outcomes (for model training)
CREATE TABLE dispatch_log (
    timestamp REAL PRIMARY KEY,
    solar_kw REAL,
    battery_kw REAL,
    diesel_kw REAL,
    demand_kw REAL,
    shed_kw REAL,
    soc_pct REAL,
    forecast_error_pct REAL,
    decision_source TEXT  -- 'optimizer', 'safety_override', 'manual'
);
```

### Feature Engineering from KG

| Feature | Source | Impact |
|---------|--------|--------|
| Market days | `calendar_events` | +15-30% demand spike |
| Festival months | `calendar_events` | +20-40% demand spike |
| Rainy season | `weather_patterns` | -20-40% solar output |
| Economic activity | community config | Shapes daily load profile |
| Population | community config | Scales absolute demand |

---

## 11. Forecasting Engine

### Model Architecture

Two TFLite LSTM models run on-device:

**Solar Irradiance Forecast:**
- Input: 72 hours of historical irradiance + time features (hour, day-of-year, cloud-proxy)
- Output: 24-hour irradiance prediction at 15-minute resolution (96 values)
- Size: ~200KB quantized INT8
- Inference time: <0.5ms on RPi 5

**Demand Forecast:**
- Input: 168 hours (1 week) of historical load + calendar features (day-of-week, market-day, festival)
- Output: 24-hour demand prediction at 15-minute resolution (96 values)
- Size: ~150KB quantized INT8
- Inference time: <0.3ms on RPi 5

### On-Device Retraining

Every 7 days, the agent retrains the LSTM models on accumulated local data:

1. Export last 30 days of telemetry from SQLite journal
2. Run incremental training (5 epochs, frozen early layers)
3. Evaluate on held-out last 3 days
4. Deploy new model only if MAPE improves by >2%
5. Keep previous model as fallback

Training runs during low-activity hours (02:00-05:00) to avoid CPU contention with the control loop.

---

## 12. EGRI Self-Improvement Loop

This is the control-theoretic governance framework (Idea G) applied to a real system:

```
                    +---------------------------------+
                    |         EGRI EVALUATOR           |
                    |   (runs daily, uses the LLM)     |
                    |                                   |
                    |   Reads last 24h from Lago:       |
                    |   - What did I predict?            |
                    |   - What actually happened?        |
                    |   - Where was I wrong?             |
                    |   - Did Autonomic override me?     |
                    |   - Did my setpoint changes help?  |
                    |                                   |
                    |   Produces:                        |
                    |   - Forecast bias correction       |
                    |   - Setpoint adjustment proposals  |
                    |   - Self-assessment score          |
                    +----------+-------------+----------+
                               |             |
                     +---------v---+   +-----v----------+
                     | ADJUST      |   | ESCALATE       |
                     | (if safe)   |   | (if uncertain) |
                     |             |   |                 |
                     | Lower       |   | "I've been      |
                     | diesel_start|   |  wrong 3 days   |
                     | from 25->22 |   |  in a row about |
                     |             |   |  afternoon      |
                     | Validated   |   |  demand. Request |
                     | by Autonomic|   |  fleet model    |
                     | (22 > 20 OK)|   |  update."       |
                     +-------------+   +----------------+
```

**This is homeostasis.** The agent maintains operational stability not through fixed rules but through continuous self-evaluation and adaptation -- the same way biological organisms maintain temperature, blood sugar, pH. The setpoints are the "desired state." The EGRI loop is the feedback mechanism. Autonomic is the brainstem that prevents lethal excursions.

### How Idea G Lives Inside Candidate E

| Idea G Concept | Where It Lives in the Microgrid Agent |
|---------------|--------------------------------------|
| Homeostasis | Autonomic controller with setpoints and feedback |
| Predictive coding | LLM anticipates future state, Lago records prediction error |
| Hierarchical Bayesian inference | Tiered reasoning (BitNet -> Qwen -> Claude) |
| Lyapunov stability | Autonomic gates ensure bounded state (SOC in [min, max]) |
| Feedback loops | EGRI: predicted vs actual -> parameter adjustment |
| Multi-rate control | Tier 1 (ms) -> Tier 2 (min) -> Tier 3 (hr) -> Tier 4 (day) |
| Self-regulation | Agent adjusts own setpoints based on outcomes |

---

## 13. Fleet Architecture

### Fleet Topology -- N Nodes

```
                                    FLEET SERVER
                              (cloud / IPSE datacenter)
                    +-------------------------------------+
                    |                                      |
                    |  +----------+  +------------------+  |
                    |  | NanoMQ   |  | DuckDB           |  |
                    |  | MQTT     |  | Time Series      |  |
                    |  | Broker   |  | + Fleet KG       |  |
                    |  +----+-----+  +----+-------------+  |
                    |       |             |                  |
                    |  +----v-------------v--------------+  |
                    |  |  FLEET ENGINE (Rust or Python)   |  |
                    |  |                                  |  |
                    |  |  Aggregator --- collects metrics  |  |
                    |  |  Clusterer --- groups by climate  |  |
                    |  |  Trainer ----- fleet-wide models  |  |
                    |  |  Detector --- cross-site anomaly  |  |
                    |  |  Optimizer -- diesel logistics    |  |
                    |  |  Predictor -- maintenance needs   |  |
                    |  +----+-----------------------------+  |
                    |       |                                 |
                    |  +----v-----------------------------+  |
                    |  |  INTELLIGENCE (TypeScript + LLM)  |  |
                    |  |                                   |  |
                    |  |  Next.js Dashboard -- map + alerts|  |
                    |  |  Claude API ------- NL briefings  |  |
                    |  |  Query Engine ----- "show me..."  |  |
                    |  |  Report Gen ------- daily digest  |  |
                    |  +----------------------------------+  |
                    +-----------+----------+-----------------+
                                |          |
           +--------------------+          +------------------+
           |                                                   |
    MQTT/TLS (intermittent)                          MQTT/TLS (intermittent)
           |                                                   |
    +------v--------------------------+   +--------------------v------+
    | CLIMATE ZONE: ORINOQUIA         |   | CLIMATE ZONE: PACIFICO    |
    |                                  |   |                            |
    |  +--------+  +--------+         |   |  +--------+  +--------+   |
    |  |Inirida |  |Mitu    |         |   |  |Coqui   |  |Quibdo  |   |
    |  |2.47 MW |  |200 kW  |         |   |  |101 kVA |  |500 kW  |   |
    |  |online  |  |online  |         |   |  |online  |  |offline |   |
    |  +--------+  +--------+         |   |  +--------+  +--------+   |
    |  +--------+  +--------+         |   |  +--------+  +--------+   |
    |  |Caruru  |  |P.Carreno|        |   |  |Tado    |  |Istmina |   |
    |  |50 kW   |  |300 kW  |         |   |  |80 kW   |  |150 kW  |   |
    |  |offline |  |online  |         |   |  |online  |  |online  |   |
    |  +--------+  +--------+         |   |  +--------+  +--------+   |
    |                                  |   |                            |
    |  Shared base model: v4.2         |   |  Shared base model: v3.7   |
    |  Irradiance: 5.0-5.5 kWh/m2     |   |  Irradiance: 3.0-3.5 kWh/m2|
    +----------------------------------+   +----------------------------+
```

### Fleet Compounding -- How Intelligence Grows

```
MONTH 1 (10 nodes)         MONTH 3 (50 nodes)         MONTH 12 (200+ nodes)

Each site learns           Sites grouped by           Fleet intelligence
independently.             climate zone.              is self-reinforcing.
Cold start.                Transfer: A helps B.       NEW site X gets model v12
No transfer learning.      Anomaly: D+E correlated.   on DAY ONE. No cold start.

Value per node: LOW        Value per node: MEDIUM     Value per node: HIGH
```

**Compounding mechanisms:**
1. **Transfer learning** -- new site inherits from cluster
2. **Anomaly detection** -- fleet sees what 1 site can't
3. **Diesel logistics** -- 1 boat serves 3 river sites
4. **Predictive maintenance** -- 500 battery curves -> patterns
5. **Failure prevention** -- 0 kWh detected in days, not 8 years (Puerto Narino)

---

## 14. Fleet Sync Protocol

### Design Goals

- **No data loss**: All telemetry is persisted locally before any sync attempt
- **Bandwidth efficient**: Delta compression + aggregation for constrained links
- **Secure**: TLS + per-node API keys
- **Resilient**: Operates correctly with minutes, hours, or days between sync windows

### Protocol

```
Site Agent                          Fleet Broker (MQTT)
    |                                     |
    |-- [1s] Write to local journal ---+  |
    |                                  |  |
    |-- [5min] Check connectivity -----|  |
    |                                  |  |
    |   if online:                     |  |
    |-- MQTT CONNECT (TLS) -----------|->|
    |-- PUBLISH telemetry/site-id ----|->|  (compressed JSONL batch)
    |<- PUBACK ------------------------|--|
    |-- Mark batch as synced ----------|  |
    |                                  |  |
    |   if offline:                    |  |
    |-- Append to sync queue ----------|  |
    |   (SQLite WAL in data/sync-queue)|  |
    |                                     |
    |-- [next window] Drain queue ------->|
    |                                     |
```

### MQTT Topics

| Topic | Direction | Payload |
|-------|-----------|---------|
| `telemetry/{site_id}` | Agent -> Broker | Compressed JSONL batch of readings |
| `commands/{site_id}` | Broker -> Agent | Remote configuration updates |
| `alerts/{site_id}` | Agent -> Broker | Critical alerts (fault, low SOC) |
| `status/{site_id}` | Agent -> Broker | Heartbeat every sync interval |
| `fleet/models/{zone}` | Broker -> Agent | Weight updates |
| `fleet/config/{id}` | Broker -> Agent | Config changes |
| `fleet/alerts` | Broker -> Agent | Fleet-wide notices |

### Queue Management

The sync queue in `data/sync-queue/` uses SQLite in WAL mode for concurrent read/write. Records are batched by 5-minute windows and compressed with gzip before transmission. After successful MQTT PUBACK, the batch is marked as synced and eligible for cleanup. The queue retains up to 30 days of unsynced data (~50MB).

---

## 15. Security

### Trust Zones

```
+--------------------------------------------------------------+
| TRUST ZONE 1: Physical (highest trust)                        |
| Hardware interfaces, sensor readings, actuator commands        |
| Attack surface: physical access to RS-485 bus                 |
| Mitigation: IP65 enclosure, tamper detection                  |
+--------------------------------------------------------------+
| TRUST ZONE 2: Local (high trust)                              |
| Kernel daemon, event journal, knowledge graph                 |
| Attack surface: local dashboard (WiFi AP), SSH                |
| Mitigation: WPA2 on AP, SSH key-only, no root login           |
+--------------------------------------------------------------+
| TRUST ZONE 3: Network (medium trust)                          |
| MQTT fleet sync, model downloads                              |
| Attack surface: cellular/satellite uplink                     |
| Mitigation: MQTT over TLS, client certificates                |
| Model integrity: SHA-256 checksum verification                |
+--------------------------------------------------------------+
| TRUST ZONE 4: Fleet (lowest trust from node perspective)      |
| Cloud infrastructure, dashboard, LLM API                      |
| Attack surface: internet-facing services                      |
| Mitigation: standard cloud security                           |
| Key principle: node NEVER trusts fleet for safety decisions    |
| Fleet can suggest, kernel decides, autonomic overrides all     |
+--------------------------------------------------------------+
```

### Threat Model and Mitigations

The primary deployment environment is a physically accessible device in a remote community:

| Threat | Mitigation |
|--------|------------|
| Accidental unsafe dispatch | Autonomic safety gates with hard limits that cannot be configured away |
| Physical SD card removal | Read-only rootfs; data on separate partition with encryption at rest |
| MQTT man-in-the-middle | TLS required for all MQTT connections; broker certificate pinning |
| Unauthorized remote commands | Per-node API keys; command signing with HMAC-SHA256 |
| Dependency supply chain | Pinned dependencies with hash verification; minimal dependency set |
| Diesel runaway (stuck relay) | Hardware watchdog timer; independent diesel runtime counter |

### Safety Invariants

These are enforced in code and cannot be overridden by configuration:

1. Battery SOC never commanded below physical minimum (protects cells from deep discharge)
2. Diesel generator never runs continuously for more than 8 hours without a mandatory cooldown
3. Load shedding always respects the priority order -- critical loads (health post, water pump) are shed last
4. Any device fault triggers immediate isolation of the faulted device
5. The safety monitor loop runs independently of the optimizer -- a stuck optimizer does not block safety checks

---

## 16. Deployment Architecture

### Single Node

```
+---[ Raspberry Pi ]-------------------------------+
|                                                  |
|  systemd service: microgrid-agent.service         |
|  +--------------------------------------------+ |
|  | Rust kernel (single static binary, ~15MB)   | |
|  |                                             | |
|  |  main.rs (tokio async control loop)         | |
|  |    +-- devices.rs (HAL: Modbus, VE.Direct)  | |
|  |    +-- dispatch.rs (LP solver: good_lp)     | |
|  |    +-- autonomic.rs (safety gates)          | |
|  |    +-- knowledge.rs (SQLite KG: rusqlite)   | |
|  |    +-- journal.rs (event journal: redb)     | |
|  |    +-- ml_bridge.rs (IPC to Python ML)      | |
|  |    +-- dashboard.rs (axum + HTMX :8080)     | |
|  |    +-- sync.rs (MQTT: rumqttc)              | |
|  +--------------------------------------------+ |
|  | Python ML worker (spawned on demand)        | |
|  |    +-- forecast.py (TFLite LSTM)            | |
|  |    +-- worker.py (IPC process)              | |
|  +--------------------------------------------+ |
|                                                  |
|  /var/lib/microgrid-agent/                       |
|    +-- journal.redb    (event journal)           |
|    +-- knowledge.db    (community context)       |
|    +-- sync-queue.db   (outbound queue)          |
|    +-- models/         (TFLite + BitNet weights)  |
|                                                  |
+--------------------------------------------------+
    |           |           |           |
    | RS-485    | VE.Direct | I2C       | USB
    |           |           |           |
  Inverter   Victron     Sensors     USB-serial
  BMS        MPPT        BH1750     adapters
  Genset                 DS18B20
```

### Fleet (Multiple Nodes)

```
+----------+    +----------+    +----------+
| Site A   |    | Site B   |    | Site C   |
| (RPi)    |    | (RPi)    |    | (RPi)    |
+----+-----+    +----+-----+    +----+-----+
     |               |               |
     | cellular      | satellite     | cellular
     |               |               |
+----+---------------+---------------+-----+
|              MQTT Broker                  |
|         (NanoMQ / Mosquitto)              |
+----+----------------------------------+---+
     |                                  |
+----+--------+               +---------+---+
| Fleet       |               | Grafana     |
| Dashboard   |               | Monitoring  |
| (Next.js)   |               | (optional)  |
+-------------+               +-------------+
```

Each site operates fully autonomously. The fleet broker and dashboards are optional infrastructure that provide aggregate visibility but are never required for site-level operation.

### Bill of Materials -- Agentic Node

| Component | Purpose | Cost |
|-----------|---------|------|
| RPi 5 8GB | Agent runtime + BitNet 2B (0.4GB) + kernel (0.1GB) + KG (0.1GB) = 7.4GB free | $80 |
| NVMe 256GB | Lago journal + models + sync queue | $30 |
| UPS HAT | Survive power outages | $50 |
| RS-485 HAT | Modbus to inverters/genset | $15 |
| Sensors | CTs, irradiance, temperature, SOC | $175 |
| Connectivity | 4G modem + satellite fallback | $150 |
| **Total** | **Full agentic node** | **~$650** |

BitNet 2B adds **0.4 GB RAM and 0.028 J per token** to the existing node. No hardware change needed.

---

## 17. Technology Stack

```
+--------------------------------------------------------------+
|                        TECHNOLOGY CHOICES                      |
+----------+--------------+------------------------------------+
| Layer    | Language     | Key Libraries / Tools               |
+----------+--------------+------------------------------------+
| PHYSICS  | Wires        | Modbus RTU (RS-485), VE.Direct     |
|          |              | SunSpec register maps, DSE/ComAp   |
+----------+--------------+------------------------------------+
| KERNEL   | Rust         | tokio (async), tokio-modbus,       |
| (daemon) |              | rumqttc, redb (journal),           |
|          |              | rusqlite (KG), axum (dashboard),   |
|          |              | good_lp (dispatch), sd-notify,     |
|          |              | tracing, serde + toml              |
|          |              | Binary: ~15MB static, no deps      |
|          |              | RAM: ~50MB runtime                 |
|          |              | Startup: <100ms                    |
+----------+--------------+------------------------------------+
| ML       | Python       | tflite-runtime (inference),        |
| (worker) |              | numpy, scipy, openpyxl             |
|          |              | Called via subprocess, not always-on|
|          |              | Model: <1MB TFLite, <20MB RAM      |
|          |              | Inference: <0.5ms per forecast     |
+----------+--------------+------------------------------------+
| REASONING| BitNet /     | BitNet 2B (1.58-bit, 0.4 GB)       |
| CORE     | llama.cpp    | ARM NEON optimized kernels          |
|          |              | Qwen 2.5 3B Q4 (fallback, 2.2 GB) |
+----------+--------------+------------------------------------+
| FLEET    | Rust/Python  | NanoMQ (MQTT broker),              |
| ENGINE   |              | DuckDB (time series),              |
|          |              | Flower (federated learning)        |
+----------+--------------+------------------------------------+
| FLEET    | TypeScript   | Next.js (dashboard UI),            |
| DASHBOARD|              | Claude API (NL briefings),         |
|          |              | Mapbox/Leaflet (site map),         |
|          |              | shadcn/ui (component library)      |
+----------+--------------+------------------------------------+
| DEPLOY   | Shell/Docker | systemd (process management),      |
|          |              | OverlayFS (read-only root),        |
|          |              | RAUC/Mender (A/B updates),         |
|          |              | Docker (CI/simulation)             |
+----------+--------------+------------------------------------+
```

---

## 18. Standards Alignment

```
IEEE 2030.7 Microgrid Controller Layers
----------------------------------------

+----------------------------------+
| Layer 4: Grid Interactive        |  <- NOT APPLICABLE (ZNI = islanded)
| (utility coordination)          |
+----------------------------------+
| Layer 3: Supervisory             |  <- FLEET ENGINE
| (fleet optimization, scheduling) |     Transfer learning, diesel logistics,
|                                  |     anomaly detection, LLM briefings
+----------------------------------+
| Layer 2: Local Area              |  <- RUST KERNEL
| (microgrid-level control)        |     LP dispatch, autonomic safety,
|                                  |     ML forecasting, KG queries
+----------------------------------+
| Layer 1: Device                  |  <- HARDWARE ABSTRACTION
| (individual asset control)       |     Modbus/VE.Direct adapters,
|                                  |     inverter setpoints, genset start/stop
+----------------------------------+
```

---

## 19. Continuous Progress

The agentic-native architecture benefits from every improvement in the field without architectural changes.

### 2024-2026: What Already Happened

| Year | Advance | Impact on This Architecture |
|------|---------|---------------------------|
| 2024 | Qwen 2.5 small models with tool calling | Made agentic reasoning feasible at 1.5-3B |
| 2024 | BitNet 1.58-bit ternary quantization | 9x energy reduction, 3x memory reduction |
| 2025 | llama.cpp ARM NEON optimization | 1.37-5.07x speedup on RPi |
| 2025 | LoRA/QLoRA for edge fine-tuning | Site-specific adaptation without full retraining |
| 2025 | Flower federated learning on RPi | Proven multi-device FL |
| 2026 | Control-theoretic foundations for agentic systems | Formal framework validates our approach |
| 2026 | BitNet 2B (b1.58-2B-4T) | First research-quality 1-bit model |

### 2026-2028: What's Coming (conservative projection)

| Expected Advance | Impact |
|-----------------|--------|
| BitNet 7B+ models | Deep reasoning on RPi 8GB at 0.4 GB memory |
| Sub-1-bit quantization research | Even smaller, even faster |
| ARM v9 with matrix extensions (RPi 6?) | 2-4x inference speedup |
| Agentic tool-calling fine-tunes at 1-3B | Purpose-built models for IoT agent use |
| Federated fine-tuning with ternary weights | Fleet-wide learning at 1-bit efficiency |
| RISC-V with BitNet acceleration | Custom silicon for 1-bit inference |

**The architecture doesn't change.** The Arcan agent runtime, the Praxis tools, the Autonomic safety gates, the Lago journal -- all stay the same. Only the model in the reasoning core gets swapped for a better one. This is the separation of concerns that Life provides: the agent runtime is independent of the model powering it.

### Implementation: Deterministic vs Agentic Control Loop

```rust
// Current: deterministic loop
loop {
    tokio::select! {
        _ = sensor_interval.tick() => { self.devices.read_all().await; }
        _ = dispatch_interval.tick() => { self.dispatcher.solve(&state).await; }
        _ = forecast_interval.tick() => { self.ml.request_forecast().await; }
    }
}

// Agentic: LLM reasoning loop
loop {
    tokio::select! {
        // Tier 1: Autonomic reflexes (always, deterministic)
        _ = sensor_interval.tick() => {
            let readings = self.devices.read_all().await;
            self.autonomic.check_reflexes(&readings).await;
        }
        // Tier 2: Agent reasoning cycle (every 5 min)
        _ = reasoning_interval.tick() => {
            let context = self.build_context(&state).await;
            let response = self.llm.reason(context, &self.tools).await;
            for tool_call in response.tool_calls {
                let validated = self.autonomic.validate(&tool_call);
                if validated.allowed {
                    self.praxis.execute(tool_call).await;
                } else {
                    self.journal.log_override(tool_call, validated.reason);
                }
            }
            self.journal.log_reasoning(context, response, outcomes);
        }
        // Tier 1: Watchdog (always)
        _ = watchdog_interval.tick() => {
            sd_notify::notify(false, &[sd_notify::NotifyState::Watchdog]);
        }
    }
}
```

### Research Trajectory

```
PHASE 1 (2026-2028):
  BitNet 2B on RPi -> prove agentic dispatch > rule-based
  MAPE comparison across 3 climate zones
  EGRI loop validation: does the agent improve over 30 days?

PHASE 2 (2028+):
  BitNet 7B+ -> deeper reasoning, fewer escalations to Tier 3/4
  Custom fine-tune on ZNI operational data -> domain-specific agent
  Fleet of 100+ agents with federated learning
  Formal stability proofs connecting Autonomic gates to Lyapunov theory

LONG-TERM VISION:
  Every microgrid in the developing world runs a Life agent
  The model keeps improving. The architecture is already right.
  1-bit models make it economically viable at any scale.
```

The research contribution isn't "AI for microgrids" (engineering) or "AI safety theory" (pure theory). It's **demonstrating that an autonomous AI agent can safely and effectively manage critical physical infrastructure at the edge, governed by a control-theoretic framework inspired by biological homeostasis, using 1-bit LLMs that run on solar-powered hardware costing less than a boat trip.**
