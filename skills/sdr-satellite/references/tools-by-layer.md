# SDR & Satellite Tools, by Layer

Full survey from the 2026-05-19 research pass. Layered so you can swap one box without rewriting the rest.

## L0 — Hardware abstraction

The vendor-neutral interface to your dongle.

| Tool | Language | Why pick it |
|---|---|---|
| **SoapySDR** | C (bindings everywhere) | The lingua franca. Abstracts RTL-SDR, HackRF, USRP, LimeSDR, BladeRF, Airspy, PlutoSDR, SDRplay. Every modern framework speaks it. |
| **rtl-sdr-rs** | Rust | Pure-Rust port of Osmocom's rtl-sdr driver. Use when you want the cheap $30 dongle path with zero C deps. |
| **librtlsdr** (Osmocom) | C | Original RTL2832U driver. Reference implementation behind everything else. |
| **UHD** (USRP Hardware Driver) | C++ | If you're using a USRP. RFNoC builds on this for FPGA work. |

## L1 — DSP framework

Where bits become signals (or vice versa).

| Tool | Language | Style | Why pick it |
|---|---|---|---|
| **GNU Radio** | C++ / Python | Block graph, GUI flowgraph editor | The standard. Every modulation, every protocol has a flowgraph somewhere on GitHub. Steep learning curve. |
| **liquid-dsp** | C | Library of DSP primitives, no framework | Lean, embeddable. Use when you don't want a framework. |
| **rustradio** | Rust | GNU-Radio-style block graph | Easier to get right than C++, faster than Python. Best Rust pick if you want graph composition. |
| **radiorust** | Rust | Tokio async, message-passing | Natural fit for Tokio-based services (Life Agent OS stack). |
| **SigDigger DSP (sigutils + Suscan)** | C++ | Multi-core analyzer | ~20% lower CPU than Gqrx. Not built on GNU Radio. |
| **LuaRadio** | Lua | Lightweight block graph | If you want GNU-Radio shape without C++ build pain. |
| **REDHAWK** | C++ | Real-time SDR app framework | DoD / production focus, supports distributed deployments. |

## L2 — Receiver UI / spectrum tools

Eyeballs on the waterfall, live demod.

| Tool | Pros | Cons |
|---|---|---|
| **SDR++** | Modern, fast, cross-platform, clean | Plugin ecosystem still maturing |
| **SDRangel** | Built-in satellite tracking, transmit-capable, kitchen sink | UI density can overwhelm |
| **Gqrx** | Mature, dedicated NOAA APT mode, AM/FM/SSB | Looks dated |
| **CubicSDR** | Consistent cross-platform UX | Less actively developed |
| **SigDigger** | Signal analysis focus, multi-core, beats Gqrx ~20% | Power user; not a casual receiver |
| **SDR#** (SDRSharp) | Polished, Windows-only | Closed-source, Windows-only |

## L3 — Satellite-specific decoders

The piece that knows what a satellite's bits *mean*.

| Tool | Coverage | Notes |
|---|---|---|
| **SatDump** | 90+ satellites: NOAA APT/HRPT, Meteor-M LRPT, GOES HRIT, Elektro-L, Metop, FengYun, Inmarsat Aero, STD-C EGC, etc. | The one decoder you actually need. Outputs calibrated L1b products (SST, microphysics) ready for weather models. Rotator + scheduler built in. |
| **WXtoImg** | NOAA APT only | Classic, freeware, Windows-focused, project abandoned but still works |
| **MeteorDemod** | Meteor-M LRPT | Specialized; SatDump handles same protocol now |
| **goestools** | GOES HRIT/EMWIN | Specialized; SatDump again subsumes |

**SatDump is the answer** unless you're learning the underlying DSP, in which case write the GNU Radio flowgraph yourself.

## L4 — Ground-station orchestration

Schedule passes, drive rotators, manage SDR, decode, store, share.

| Tool | Scope | Notes |
|---|---|---|
| **SatNOGS** (Libre Space Foundation) | Distributed network: ~600 crowd-sourced stations worldwide | Four sub-projects: Network (scheduling), DB (transmitter catalog with API), Client (per-station daemon), Ground Station hardware (3D-printed rotator). The reference design for "distributed instrument network." |
| **Ground Station** (`sgoudelis/ground-station`, new 2026) | Single-station orchestrator | Web UI, wraps SatDump, schedules via SatNOGS API, Hamlib rotator + Doppler, SigMF IQ recording, AI speech-to-text on voice passes. GPL-3. |
| **Hamlib** | Rig + rotator control library | The substrate every orchestrator builds on. Speaks to ~250 commercial radios and rotators. |
| **gpredict** | Pass prediction GUI | TLE-aware, plots passes, drives Hamlib rotators. Standalone, not network-aware. |

## L5 — Orbit mechanics / pass prediction

TLE → pass time → az/el → Doppler shift.

| Tool | Language | Why pick it |
|---|---|---|
| **python-sgp4** (brandon-rhodes) | Python (C++ inside) | De-facto SGP4 standard. Compiles Vallado's reference C++ (2023 May release). 0.1 mm agreement with reference. Loads TLE or OMM. |
| **neuromorphicsystems/sgp4** | Rust | `no_std` capable, sub-µm agreement. WASM wrapper available. Best Rust SGP4. |
| **satkit** | Rust + PyO3 | Full astrodynamics: SGP4 + RK adaptive integrators + EGM96 gravity + ITRF/Geodetic/ENU + sun/moon ephemerides + Vincenty geodesics. Industry-strength. |
| **dSGP4** | Python (differentiable) | Gradient through SGP4. For ML applications, state covariance propagation, gradient-based orbit determination. |
| **heyoka.py SGP4** | Python (differentiable, SIMD) | Differentiability up to arbitrary order. No SDP4 (deep-space). Multi-threaded + SIMD vectorized. |

## Where TLEs come from

- **CelesTrak** (`celestrak.org`) — the canonical public TLE source. Categorized by satellite class. Updated daily.
- **SpaceTrack** (`space-track.org`) — US government's authoritative source. Free account required.
- **SatNOGS DB API** — transmitter info (frequency, modulation, mode) cross-referenced with TLEs.

## Specialized side-quests

| Domain | Tools |
|---|---|
| **Cellular (2G/4G/5G)** | `OpenBTS` (2G), `srsRAN` (4G/5G), `free5GRAN` (5G SA), `LTESniffer` |
| **VITA-49 RF telemetry packets** | `vita49` crate (Rust) — standardized IQ-over-network format |
| **SigMF (signal metadata format)** | Standardized way to record IQ with metadata (frequency, sample rate, satellite info). Native in SatDump + Ground Station. |
| **GNU Radio Companion (GRC)** | The visual flowgraph editor; produces Python out of XML |
| **gr-satellites** (GNU Radio out-of-tree module) | Decodes ~150 amateur satellite signals. SatDump subsumes most. |

## Hardware catalog (cheat-sheet)

| Dongle | Price | Frequency | Use |
|---|---|---|---|
| **RTL-SDR v4** | $30 | 24 MHz – 1.7 GHz | NOAA APT, FM, ADS-B, ham radio. The starter. |
| **Airspy R2** | $170 | 24 MHz – 1.8 GHz | Better dynamic range than RTL-SDR; cleaner for narrowband. |
| **Airspy HF+ Discovery** | $170 | 0.5 kHz – 31 MHz, 60–260 MHz | HF + VHF; for shortwave and HF satellites. |
| **HackRF One** | $300 | 1 MHz – 6 GHz, transmit + receive | TX-capable; for jamming-legal countries 🙏 |
| **LimeSDR Mini** | $180 | 10 MHz – 3.5 GHz, full-duplex | Cellular work, more channels |
| **PlutoSDR** | $230 | 325 MHz – 3.8 GHz, full-duplex | Compact, education-focused |
| **SDRplay RSPdx** | $250 | 1 kHz – 2 GHz | 14-bit ADC; for serious HF DX |
| **USRP X310** | $5K+ | 10 MHz – 6 GHz, FPGA-programmable | Production / research-grade |

## Antenna basics (for the 137 MHz weather satellite band)

- **V-dipole**: two pieces of wire at 120° angle, $5 in materials, works
- **QFH (Quadrifilar Helix)**: better gain pattern at horizon, ~$20 in PVC + wire, 3D-printable hub
- **Turnstile + reflector**: classic SatNOGS baseline
- **Yagi + rotator**: if you want to track and need gain (Meteor-M LRPT, HRPT)
