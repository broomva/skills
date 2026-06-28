# Composition — Wiring SDR into Broomva Stack

The interesting question isn't "can we receive satellites" (yes, with $30). It's "what does an SDR pipeline look like as a first-class Rust service in our existing architecture."

This doc maps the SDR stack onto Life Agent OS, Opsis, arcan/sensorium, and Spaces.

## Thread 1 — Satellite passes as Opsis world-state events

Opsis is an AI-native world-state engine: `OpsisEvent` protocol + CesiumJS globe + Rust engine. From `~/broomva/projects/opsis/` (or wherever it lives) — events flow in, the world state updates, the globe renders.

A satellite pass is literally a sequence of georeferenced events. Trivial mapping:

```rust
// Hypothetical sat-opsis-bridge crate
use sgp4;
use opsis_protocol::OpsisEvent;

struct SatPassEvent {
    sat_id: u32,            // NORAD catalog number
    name: String,           // "NOAA 19"
    timestamp: DateTime<Utc>,
    lat: f64,
    lon: f64,
    alt_km: f64,
    velocity_kms: (f64, f64, f64),
    elevation_from_station: Option<f64>,  // None if not over any tracked station
    payload: Option<DecodedPayload>,      // Some when we actually decoded a frame
}

impl From<SatPassEvent> for OpsisEvent {
    fn from(e: SatPassEvent) -> Self {
        OpsisEvent {
            kind: "sat_pass".into(),
            timestamp: e.timestamp,
            geo: Some(Geo { lat: e.lat, lon: e.lon, alt_m: e.alt_km * 1000.0 }),
            metadata: serde_json::to_value(e).unwrap(),
        }
    }
}
```

Two emission modes:
1. **Predicted** — `satkit` propagates TLE forward 24h, emits expected passes. Globe renders predicted ground tracks.
2. **Observed** — when we actually receive a transmission, emit with `payload: Some(...)`. Globe lights up the actual reception point.

The CesiumJS globe already renders georeferenced events, so the visualization comes free. Possibly the lowest-effort, highest-visual-impact integration in the stack.

### Status quo to delta
- **Status quo:** Opsis renders whatever `OpsisEvent` it gets.
- **Delta:** A new crate `sat-opsis-bridge` runs `satkit` for prediction + `SatDump` (called as subprocess or via FFI) for live decode, and emits `OpsisEvent` records. Probably a long weekend's work for a working prototype with NOAA APT + one satellite predicted ahead.

## Thread 2 — SatNOGS network shape ≈ Spaces

`core/life/spaces` is described as "Discord-like communication fabric where agents interact distributedly. WASM server module + CLI client + 5-tier RBAC." A global registry of nodes that can talk to each other and coordinate work.

SatNOGS has exactly the same shape:
- **Network** = global registry + scheduler (`network.satnogs.org`)
- **DB** = capability catalog (which transmitters exist, on which satellites)
- **Client** = per-node daemon that accepts scheduled work
- **Hardware** = the actual antenna + rotator + SDR

If we ever want "a Life node, but it has antennas," the cleanest integration is:

```
Spaces SpacetimeDB tables ←→ SatNOGS Network DB
  ├ agents.sat_capability      (band, polarization, az_range, el_range)
  ├ agents.station_metrics     (uptime, observations, success rate)
  └ tasks.schedule_observation (satellite, pass_window, demands)
                ↓
  Each Spaces node with sat capability runs `satnogs-client` shape
  Receives schedules, executes, returns IQ + decoded payload
```

The shape is already proven by SatNOGS's 600+ stations. We don't have to design it.

### Cross-link
- `pattern/distributed-instrument-network.md` (knowledge graph candidate) — the pattern shared by SatNOGS + Spaces + (potentially) Opsis observer mesh + future arcan sensorium clusters.

## Thread 3 — Sensorium / Prosopon angle

`core/prosopon` is described as "display server for AI agents — Pneuma<L0ToExternal>, sibling of Sensorium." Sensorium = the agent's input substrate.

Radio is a literal sensorium input. An agent that can:
- subscribe to "any APRS packet from station X"
- subscribe to "any ISS SSTV image"
- subscribe to "Meteor-M LRPT pixels over Bogotá"

...has expanded its sensorium beyond the screen. The wiring is the same `OpsisEvent`-style stream, just consumed by an agent instead of a globe renderer.

### Why this might be worth doing
- It's a stress test of the sensorium abstraction: if radio fits cleanly, then microphones, cameras, GPS, IMU, weather stations all fit the same way.
- It's a real-world-grounding signal source for agents — the same way humans use the news. (One commenter on the niko.strength reel called it "adhdmaxxing"; productively channeled, it's exactly the breadth of input human polymaths use to make non-obvious connections.)

## Thread 4 — The arcan agent loop reads from a satellite

Most agent loops are LLM-bound: prompt in, response out. Spec E (agent-loop silicon) reframes this as the InferenceBackend abstraction. If the agent also has a *sensor stream*, the loop can do:

```
loop {
    let satellite_event = sat_sensor.next().await?;
    let response = arcan.process(satellite_event).await?;
    if let Some(action) = response.action {
        action.execute().await?;
    }
}
```

For example: ISS SSTV image arrives → arcan recognizes it (vision-capable model) → posts to Spaces channel → other agents see it. This is a real-world-grounded agent that doesn't just sit in a chat window.

This is speculative — there's no `sat_sensor` trait yet — but the abstraction needed is small. A `SensorStream<T>` trait that any L0 input substrate (radio, camera, mic, GPS) implements.

## What to build first, if we build anything

In order of leverage:

1. **Hardware-light proof:** Wire `satkit` → emit predicted `OpsisEvent` records for the next 24h of NOAA-19 passes. No hardware. Visualization on the globe. ~1 day.
2. **First real sample:** RTL-SDR + SatDump subprocess + `sat-opsis-bridge` crate that emits `OpsisEvent` when an actual NOAA APT image is decoded. ~1 weekend.
3. **Spaces integration:** A `sat-capability` table in Spaces; a Life node that advertises its antenna. Use the SatNOGS API as the reference scheduler shape — don't reinvent. ~1 week.
4. **Sensorium trait:** Promote `SensorStream<T>` to a real trait, with `RadioSensor` as the first implementation, motivating `CameraSensor` / `MicSensor` / `GPSSensor` next. ~1 month including the abstraction refactor.

If we only ever do (1), it's a fun visualization and the lowest-cost demo of "Opsis can render any georeferenced event source." If we get to (4), we've changed how arcan thinks about its input substrate.

## Knowledge graph candidates

Worth filing as separate entities if we go past step 1:

| Slug | Type | Reason |
|---|---|---|
| `tool/satdump.md` | tool | The decode engine |
| `tool/satnogs.md` | tool | Distributed ground-station network |
| `tool/satkit.md` | tool | Rust orbital mechanics — composes with Opsis |
| `tool/sdrpp.md` | tool | The modern receiver UI |
| `pattern/distributed-instrument-network.md` | pattern | Shape shared by SatNOGS + Spaces |
| `concept/satellite-pass-as-world-state-event.md` | concept | The Opsis seed |
| `concept/radio-as-sensorium-input.md` | concept | The sensorium extension thesis |
| `pattern/cross-discipline-obsession-as-identity.md` | pattern | The niko.strength reel framing — gym + radio together |

Scoring against the bookkeeping Nous gate (novelty / specificity / relevance, ≥5/9 to promote) — the `concept/` entries score highest because they propose architectural integrations, not just survey-of-tools facts.
