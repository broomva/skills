//! Site configuration — loaded from TOML.

use serde::Deserialize;
use std::path::{Path, PathBuf};

#[derive(Debug, Deserialize)]
pub struct SiteConfig {
    pub site: SiteSection,
    #[serde(default)]
    pub grid: GridSection,
    #[serde(default)]
    pub solar: SolarSection,
    #[serde(default)]
    pub battery: BatterySection,
    #[serde(default)]
    pub diesel: DieselSection,
    #[serde(default)]
    pub connectivity: ConnectivitySection,
    #[serde(default)]
    pub autonomic: AutonomicSection,
    #[serde(default)]
    pub community: CommunitySection,
    #[serde(default)]
    pub paths: PathsSection,
}

impl SiteConfig {
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        let contents = std::fs::read_to_string(path)?;
        let config: SiteConfig = toml::from_str(&contents)?;
        Ok(config)
    }
}

#[derive(Debug, Deserialize)]
pub struct SiteSection {
    pub id: String,
    #[serde(default = "default_name")]
    pub name: String,
    #[serde(default = "default_region")]
    pub region: String,
    #[serde(default)]
    pub latitude: f64,
    #[serde(default)]
    pub longitude: f64,
    #[serde(default = "default_sensor_interval")]
    pub sensor_interval_s: f64,
    #[serde(default = "default_dispatch_interval")]
    pub dispatch_interval_s: f64,
    #[serde(default = "default_forecast_interval")]
    pub forecast_interval_s: f64,
}

#[derive(Debug, Deserialize, Default)]
pub struct GridSection {
    #[serde(default = "default_grid_type")]
    pub grid_type: String,
    #[serde(default = "default_voltage")]
    pub nominal_voltage: f64,
    #[serde(default)]
    pub peak_load_kw: f64,
    #[serde(default)]
    pub priority_loads: Vec<String>,
}

#[derive(Debug, Deserialize, Default)]
pub struct SolarSection {
    pub capacity_kwp: f64,
    #[serde(default)]
    pub panels: u32,
}

#[derive(Debug, Deserialize, Default)]
pub struct BatterySection {
    pub capacity_kwh: f64,
    #[serde(default = "default_max_dod")]
    pub max_dod: f64,
}

#[derive(Debug, Deserialize, Default)]
pub struct DieselSection {
    pub capacity_kw: f64,
    #[serde(default)]
    pub fuel_tank_liters: f64,
    #[serde(default = "default_diesel_consumption")]
    pub consumption_liters_per_kwh: f64,
}

#[derive(Debug, Deserialize, Default)]
pub struct ConnectivitySection {
    #[serde(default = "default_connectivity")]
    pub primary: String,
    #[serde(default = "default_broker")]
    pub mqtt_broker: String,
    #[serde(default = "default_mqtt_port")]
    pub mqtt_port: u16,
    #[serde(default = "default_sync_interval")]
    pub sync_interval_minutes: u32,
    #[serde(default = "default_offline_buffer")]
    pub offline_buffer_days: u32,
}

#[derive(Debug, Deserialize)]
pub struct AutonomicSection {
    #[serde(default = "default_min_soc")]
    pub min_soc_pct: f64,
    #[serde(default = "default_max_soc")]
    pub max_soc_pct: f64,
    #[serde(default = "default_diesel_start_soc")]
    pub diesel_start_soc_pct: f64,
    #[serde(default = "default_diesel_stop_soc")]
    pub diesel_stop_soc_pct: f64,
    #[serde(default = "default_max_diesel_hours")]
    pub max_diesel_hours_per_day: f64,
    #[serde(default = "default_renewable_target")]
    pub renewable_target_fraction: f64,
}

impl Default for AutonomicSection {
    fn default() -> Self {
        Self {
            min_soc_pct: 20.0,
            max_soc_pct: 95.0,
            diesel_start_soc_pct: 25.0,
            diesel_stop_soc_pct: 60.0,
            max_diesel_hours_per_day: 16.0,
            renewable_target_fraction: 0.70,
        }
    }
}

#[derive(Debug, Deserialize, Default)]
pub struct CommunitySection {
    #[serde(default)]
    pub population: u32,
    #[serde(default)]
    pub primary_activity: String,
    #[serde(default)]
    pub market_days: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub struct PathsSection {
    #[serde(default = "default_data_dir")]
    pub data_dir: PathBuf,
    #[serde(default = "default_config_dir")]
    pub config_dir: PathBuf,
    #[serde(default = "default_db_path")]
    pub db_path: PathBuf,
    #[serde(default = "default_model_dir")]
    pub model_dir: PathBuf,
    #[serde(default = "default_sync_queue_dir")]
    pub sync_queue_dir: PathBuf,
}

impl Default for PathsSection {
    fn default() -> Self {
        Self {
            data_dir: PathBuf::from("data"),
            config_dir: PathBuf::from("config"),
            db_path: PathBuf::from("data/knowledge.db"),
            model_dir: PathBuf::from("data/models"),
            sync_queue_dir: PathBuf::from("data/sync-queue"),
        }
    }
}

fn default_name() -> String { "unnamed-site".into() }
fn default_region() -> String { "unknown".into() }
fn default_sensor_interval() -> f64 { 1.0 }
fn default_dispatch_interval() -> f64 { 5.0 }
fn default_forecast_interval() -> f64 { 900.0 }
fn default_grid_type() -> String { "hybrid".into() }
fn default_voltage() -> f64 { 220.0 }
fn default_max_dod() -> f64 { 0.80 }
fn default_diesel_consumption() -> f64 { 0.28 }
fn default_connectivity() -> String { "cellular".into() }
fn default_broker() -> String { "localhost".into() }
fn default_mqtt_port() -> u16 { 1883 }
fn default_sync_interval() -> u32 { 15 }
fn default_offline_buffer() -> u32 { 30 }
fn default_min_soc() -> f64 { 20.0 }
fn default_max_soc() -> f64 { 95.0 }
fn default_diesel_start_soc() -> f64 { 25.0 }
fn default_diesel_stop_soc() -> f64 { 60.0 }
fn default_max_diesel_hours() -> f64 { 16.0 }
fn default_renewable_target() -> f64 { 0.70 }
fn default_data_dir() -> PathBuf { PathBuf::from("data") }
fn default_config_dir() -> PathBuf { PathBuf::from("config") }
fn default_db_path() -> PathBuf { PathBuf::from("data/knowledge.db") }
fn default_model_dir() -> PathBuf { PathBuf::from("data/models") }
fn default_sync_queue_dir() -> PathBuf { PathBuf::from("data/sync-queue") }

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn test_load_example_config() {
        // Build a minimal TOML that matches the Rust struct field names
        let toml_str = r#"
[site]
id = "test-site"
name = "Test Site"
region = "TestRegion"
latitude = 3.86
longitude = -67.92
sensor_interval_s = 1.0
dispatch_interval_s = 5.0
forecast_interval_s = 900.0

[grid]
grid_type = "hybrid"
nominal_voltage = 120.0
peak_load_kw = 45.0
priority_loads = ["health_post", "water_pump"]

[solar]
capacity_kwp = 60.0
panels = 150

[battery]
capacity_kwh = 120.0
max_dod = 0.9

[diesel]
capacity_kw = 30.0
fuel_tank_liters = 500.0
consumption_liters_per_kwh = 0.30

[connectivity]
primary = "cellular"
mqtt_broker = "localhost"
mqtt_port = 1883
sync_interval_minutes = 15
offline_buffer_days = 30

[autonomic]
min_soc_pct = 15.0
max_soc_pct = 95.0
diesel_start_soc_pct = 20.0
diesel_stop_soc_pct = 60.0
max_diesel_hours_per_day = 16.0
renewable_target_fraction = 0.85

[community]
population = 850
primary_activity = "fishing"
market_days = ["Wed", "Sat"]

[paths]
data_dir = "data"
config_dir = "config"
db_path = "data/knowledge.db"
model_dir = "data/models"
sync_queue_dir = "data/sync-queue"
"#;

        let dir = std::env::temp_dir().join("microgrid_test_config");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("test_site.toml");
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(toml_str.as_bytes()).unwrap();

        let config = SiteConfig::load(&path).unwrap();
        assert_eq!(config.site.id, "test-site");
        assert_eq!(config.site.name, "Test Site");
        assert_eq!(config.solar.capacity_kwp, 60.0);
        assert_eq!(config.battery.capacity_kwh, 120.0);
        assert_eq!(config.diesel.capacity_kw, 30.0);
        assert_eq!(config.autonomic.min_soc_pct, 15.0);
        assert_eq!(config.grid.priority_loads.len(), 2);

        // cleanup
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_default_autonomic() {
        let autonomic = AutonomicSection::default();
        assert_eq!(autonomic.min_soc_pct, 20.0);
        assert_eq!(autonomic.max_soc_pct, 95.0);
        assert_eq!(autonomic.diesel_start_soc_pct, 25.0);
        assert_eq!(autonomic.diesel_stop_soc_pct, 60.0);
        assert_eq!(autonomic.max_diesel_hours_per_day, 16.0);
        assert_eq!(autonomic.renewable_target_fraction, 0.70);
        // min < diesel_start < diesel_stop < max
        assert!(autonomic.min_soc_pct < autonomic.diesel_start_soc_pct);
        assert!(autonomic.diesel_start_soc_pct < autonomic.diesel_stop_soc_pct);
        assert!(autonomic.diesel_stop_soc_pct < autonomic.max_soc_pct);
    }

    #[test]
    fn test_missing_config_error() {
        let path = std::path::Path::new("/tmp/nonexistent_microgrid_config_xyz.toml");
        let result = SiteConfig::load(path);
        assert!(result.is_err());
    }
}
