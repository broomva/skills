//! Device abstraction layer.
//!
//! Provides a unified interface to read sensors and send actuator commands.
//! Supports both real hardware (Modbus, VE.Direct) and a simulated device
//! for development and CI testing.

use std::path::Path;

use chrono::{DateTime, Utc};
use rand::Rng;
use tracing::info;

use crate::dispatch::DispatchDecision;

// ---------------------------------------------------------------------------
// Sensor readings — the canonical "observation" type for the control loop
// ---------------------------------------------------------------------------

/// A snapshot of all sensor values at a given instant.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SensorReadings {
    /// UTC timestamp of the reading.
    pub timestamp: DateTime<Utc>,
    /// Solar generation (kW).
    pub solar_kw: f64,
    /// Total load demand (kW).
    pub load_kw: f64,
    /// Battery state of charge (0..100%).
    pub battery_soc_pct: f64,
    /// Battery power flow (kW). Positive = charging, negative = discharging.
    pub battery_kw: f64,
    /// Diesel generator output (kW).
    pub diesel_kw: f64,
    /// Global horizontal irradiance (W/m^2).
    pub irradiance_wm2: f64,
    /// Ambient temperature (Celsius).
    pub temperature_c: f64,
}

impl Default for SensorReadings {
    fn default() -> Self {
        Self {
            timestamp: Utc::now(),
            solar_kw: 0.0,
            load_kw: 0.0,
            battery_soc_pct: 50.0,
            battery_kw: 0.0,
            diesel_kw: 0.0,
            irradiance_wm2: 0.0,
            temperature_c: 25.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Simulated device — sinusoidal solar, random load
// ---------------------------------------------------------------------------

/// A simulated device that produces realistic-looking sensor values
/// without any hardware attached. Useful for testing, CI, and shadow mode.
struct SimulatedDevice {
    solar_capacity_kwp: f64,
    base_load_kw: f64,
    battery_soc: std::sync::Mutex<f64>,
}

impl SimulatedDevice {
    fn new(solar_capacity_kwp: f64, base_load_kw: f64) -> Self {
        Self {
            solar_capacity_kwp,
            base_load_kw,
            battery_soc: std::sync::Mutex::new(50.0),
        }
    }

    async fn read(&self) -> anyhow::Result<SensorReadings> {
        let now = Utc::now();
        let hour = now.timestamp() % 86400 / 3600; // 0..23

        // Sinusoidal solar curve peaking at noon
        let solar_factor = if (6..=18).contains(&hour) {
            let t = (hour as f64 - 6.0) / 12.0 * std::f64::consts::PI;
            t.sin()
        } else {
            0.0
        };
        let solar_kw = self.solar_capacity_kwp * solar_factor;

        // Irradiance roughly correlates with solar output
        let irradiance_wm2 = solar_factor * 1000.0;

        // Random load with daily pattern (higher during daytime)
        let mut rng = rand::thread_rng();
        let load_noise: f64 = rng.gen_range(-0.1..0.1);
        let daytime_factor = if (7..=22).contains(&hour) { 1.3 } else { 0.7 };
        let load_kw = (self.base_load_kw * daytime_factor + load_noise).max(0.0);

        // Temperature with daily variation
        let temperature_c = 25.0 + 8.0 * solar_factor + rng.gen_range(-1.0..1.0);

        let battery_soc_pct = *self.battery_soc.lock().unwrap();

        Ok(SensorReadings {
            timestamp: now,
            solar_kw,
            load_kw,
            battery_soc_pct,
            battery_kw: 0.0,   // Updated after dispatch
            diesel_kw: 0.0,    // Updated after dispatch
            irradiance_wm2,
            temperature_c,
        })
    }

    async fn actuate(&self, decision: &DispatchDecision) -> anyhow::Result<()> {
        // Simulate battery SOC change based on dispatch decision
        let mut soc = self.battery_soc.lock().unwrap();
        // Rough approximation: 1 kW for 1 second on a ~10 kWh battery
        let delta = decision.battery_kw * 0.001; // very rough sim
        *soc = (*soc + delta).clamp(0.0, 100.0);

        tracing::debug!(
            solar = decision.solar_kw,
            battery = decision.battery_kw,
            diesel = decision.diesel_kw,
            "Simulated actuation"
        );
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Device registry — manages all devices for the site
// ---------------------------------------------------------------------------

/// Central registry of all devices at a site.
/// Reads sensors from all sources and dispatches actuation commands.
///
/// Currently only supports the `SimulatedDevice` backend. When real
/// hardware drivers are added (Modbus, VE.Direct), this registry will
/// use an enum-dispatch pattern or trait objects with `async-trait`.
pub struct DeviceRegistry {
    /// The active device backend.
    device: SimulatedDevice,
}

impl DeviceRegistry {
    /// Build a device registry from the site configuration directory.
    ///
    /// If `simulate` is true, creates a `SimulatedDevice` instead of
    /// scanning for real hardware.
    pub fn from_config(config_dir: &Path, simulate: bool) -> anyhow::Result<Self> {
        if simulate {
            info!("Using simulated devices");
        } else {
            // TODO: Scan config_dir for device descriptors (Modbus RTU addresses,
            //       VE.Direct serial ports, etc.) and instantiate real device drivers.
            //       For now, fall back to simulated.
            tracing::warn!(
                config_dir = %config_dir.display(),
                "Real device discovery not yet implemented — falling back to simulation"
            );
        }

        // TODO: Read solar_capacity_kwp and base_load_kw from config_dir/devices.toml
        let device = SimulatedDevice::new(10.0, 3.0);
        Ok(Self { device })
    }

    /// Read sensor values from all registered devices and merge them
    /// into a single `SensorReadings` snapshot.
    pub async fn read_all(&self) -> anyhow::Result<SensorReadings> {
        // TODO: When multiple devices are supported, merge/aggregate readings.
        self.device.read().await
    }

    /// Send an actuation command to the appropriate device(s).
    pub async fn actuate(&self, decision: &DispatchDecision) -> anyhow::Result<()> {
        self.device.actuate(decision).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sensor_readings_default() {
        let r = SensorReadings::default();
        assert_eq!(r.solar_kw, 0.0);
        assert_eq!(r.load_kw, 0.0);
        assert_eq!(r.battery_soc_pct, 50.0);
        assert_eq!(r.battery_kw, 0.0);
        assert_eq!(r.diesel_kw, 0.0);
        assert_eq!(r.irradiance_wm2, 0.0);
        assert_eq!(r.temperature_c, 25.0);
        // Default SOC should be mid-range (sane starting point)
        assert!(r.battery_soc_pct > 0.0 && r.battery_soc_pct <= 100.0);
    }

    #[test]
    fn test_sensor_readings_serialization() {
        let r = SensorReadings {
            timestamp: chrono::Utc::now(),
            solar_kw: 5.5,
            load_kw: 3.2,
            battery_soc_pct: 72.0,
            battery_kw: 2.3,
            diesel_kw: 0.0,
            irradiance_wm2: 850.0,
            temperature_c: 31.5,
        };
        let json = serde_json::to_string(&r).unwrap();
        let deserialized: SensorReadings = serde_json::from_str(&json).unwrap();
        assert!((deserialized.solar_kw - 5.5).abs() < f64::EPSILON);
        assert!((deserialized.load_kw - 3.2).abs() < f64::EPSILON);
        assert!((deserialized.battery_soc_pct - 72.0).abs() < f64::EPSILON);
        assert!((deserialized.battery_kw - 2.3).abs() < f64::EPSILON);
        assert!((deserialized.diesel_kw - 0.0).abs() < f64::EPSILON);
        assert!((deserialized.irradiance_wm2 - 850.0).abs() < f64::EPSILON);
        assert!((deserialized.temperature_c - 31.5).abs() < f64::EPSILON);
    }

    #[tokio::test]
    async fn test_simulated_device_solar_curve() {
        let device = SimulatedDevice::new(10.0, 3.0);
        let readings = device.read().await.unwrap();
        // Solar must be >= 0 (never negative)
        assert!(readings.solar_kw >= 0.0);
        // Solar must not exceed capacity
        assert!(readings.solar_kw <= 10.0 + 0.01);
        // Irradiance must be >= 0
        assert!(readings.irradiance_wm2 >= 0.0);
        // Irradiance should not exceed ~1000 W/m^2
        assert!(readings.irradiance_wm2 <= 1001.0);
    }

    #[tokio::test]
    async fn test_simulated_device_soc_bounds() {
        let device = SimulatedDevice::new(10.0, 3.0);
        // Simulate a large discharge
        let decision = DispatchDecision {
            battery_kw: -100.0, // very large discharge
            ..DispatchDecision::default()
        };
        device.actuate(&decision).await.unwrap();
        let soc = *device.battery_soc.lock().unwrap();
        assert!(soc >= 0.0, "SOC must not go below 0");
        assert!(soc <= 100.0, "SOC must not go above 100");

        // Simulate a large charge
        let device2 = SimulatedDevice::new(10.0, 3.0);
        *device2.battery_soc.lock().unwrap() = 99.9;
        let charge_decision = DispatchDecision {
            battery_kw: 100.0, // very large charge
            ..DispatchDecision::default()
        };
        device2.actuate(&charge_decision).await.unwrap();
        let soc2 = *device2.battery_soc.lock().unwrap();
        assert!(soc2 <= 100.0, "SOC must not exceed 100 after charge");
    }

    #[test]
    fn test_device_registry_simulate_mode() {
        let dir = std::env::temp_dir().join("microgrid_test_devices");
        std::fs::create_dir_all(&dir).unwrap();
        let registry = DeviceRegistry::from_config(&dir, true);
        assert!(registry.is_ok(), "from_config with simulate=true should succeed");
    }
}
