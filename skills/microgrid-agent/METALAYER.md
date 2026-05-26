# METALAYER.md — Control-Systems Manifest

> Defines the microgrid-agent as a control system: plant, controller, shields,
> estimators, and feedback loops. This is the bridge between the governance layer
> (CLAUDE.md/AGENTS.md) and the runtime implementation (kernel + prototype).

---

## Plant

The **plant** is the physical microgrid: solar panels, battery bank, diesel generator,
and connected loads. The agent observes the plant through sensors and actuates through
dispatch commands.

### State Vector

```
x_t = {
  solar_kw:     float,    # Current solar generation (kW)
  battery_soc:  float,    # Battery state of charge (0.0 - 1.0)
  battery_kw:   float,    # Battery power flow (+charge/-discharge)
  diesel_kw:    float,    # Diesel generation (kW)
  demand_kw:    float,    # Total load demand (kW)
  grid_freq_hz: float,    # Grid frequency (Hz) — stability indicator
  timestamp:    datetime, # Observation time
}
```

### Action Space

```
u_t = {
  solar_curtail_pct:  float,    # Solar curtailment (0.0 - 1.0)
  battery_setpoint:   float,    # Battery charge/discharge setpoint (kW)
  diesel_on:          bool,     # Diesel generator on/off
  diesel_setpoint:    float,    # Diesel output setpoint (kW)
  shed_loads:         [string], # Load IDs to shed (ordered by priority)
}
```

### Directive Space (LLM output)

The LLM emits typed directives `theta_t`, not raw actuations:

```
theta_t = {
  mode:              enum(normal, conservation, emergency, maintenance),
  renewable_target:  float,    # Desired renewable fraction
  diesel_strategy:   enum(avoid, supplement, primary),
  load_priority:     [string], # Reordered load priority (within constraints)
  forecast_horizon:  int,      # Hours to look ahead
}
```

The deterministic dispatcher converts `theta_t` + `x_t` into `u_t` via LP optimization.

---

## Controller Hierarchy

| Tier | Name | Cadence | LLM? | Implementation |
|------|------|---------|------|----------------|
| T0 | Safety reflex | 100ms | No | `autonomic.rs` / `autonomic.py` — hard gates G1-G4 |
| T1 | Device polling | 1s | No | `devices.rs` / `devices.py` — sensor reads |
| T2 | LP dispatch | 15min | No | `dispatch.rs` / `dispatch.py` — constrained optimizer |
| T3 | Forecast | 15min | No | `forecast/forecast.py` — LSTM inference |
| T4 | Supervisory | 15min | Yes (BitNet 2B) | Edge LLM — mode selection, setpoint tuning |
| T5 | Strategic | hourly | Yes (Qwen 3B) | Deeper reasoning — schedule planning |
| T6 | Meta-reasoning | daily | Yes (Claude API) | EGRI evaluation, self-improvement |

---

## Safety Shields

Shields are **hard filters** applied after every control proposal. They have absolute veto.

| Shield | Gate | Invariant | Implementation |
|--------|------|-----------|----------------|
| SOC Floor | G1 | `battery_soc >= min_soc_pct` | `autonomic.rs:validate_plan()` |
| SOC Ceiling | G2 | `battery_soc <= max_soc_pct` | `autonomic.rs:validate_plan()` |
| Diesel Limit | G3 | `diesel_runtime_today <= 8h` | `autonomic.rs:validate_plan()` |
| Fault Isolate | G4 | `faulted_device.disconnect()` | `autonomic.rs:handle_fault()` |

**Containment invariant**: No control path exists from LLM output to plant actuation
that bypasses the safety shield. This is enforced architecturally — `validate_plan()`
is called on every `DispatchPlan` before `apply()`.

---

## Estimator

The belief state `b_t` combines sensor readings with forecasts:

```
b_t = {
  current:  x_t,                    # Latest sensor readings
  forecast: {solar_kw, demand_kw}[],  # Next 24h predictions
  kg:       knowledge_graph_context,   # Territorial knowledge
  health:   device_health_map,         # Device status/reliability
}
```

Updated every dispatch cycle (15min). Forecasts from LSTM model in `forecast/forecast.py`.

---

## Evaluator (EGRI)

The evaluator scores each session and each dispatch interval:

### Session-Level Metrics (logged to `.control/egri-journal.jsonl`)

| Metric | Direction | Source |
|--------|-----------|--------|
| `test_count` | increase | `make test` |
| `kernel_warnings` | decrease | `cargo check` |
| `todo_count` | decrease | `grep -r TODO kernel/src/` |
| `sim_renewable` | increase | `python -m sim.run` |

### Runtime Metrics (logged to event journal)

| Metric | Direction | Source |
|--------|-----------|--------|
| `renewable_fraction` | increase | `dispatch.py` output |
| `diesel_liters` | decrease | Fuel consumption tracking |
| `load_shed_hours` | decrease | Load shedding events |
| `forecast_mae` | decrease | Predicted vs actual |

---

## Feedback Loops

```
Session EGRI:     predicted(tests, warnings) vs actual → model adaptation
Runtime EGRI:     predicted(solar, demand) vs actual → LSTM retrain
Fleet EGRI:       local performance vs fleet average → parameter sharing
```

---

## Observability

| Signal | Destination | Cadence |
|--------|------------|---------|
| Telemetry | SQLite journal (redb in Rust) | Every device poll (1s) |
| Dispatch decisions | Event journal + knowledge graph | Every dispatch (15min) |
| EGRI evaluations | `.control/egri-journal.jsonl` | End of session |
| Session logs | `docs/conversations/` | End of session |
| Fleet sync | MQTT broker | Opportunistic |
