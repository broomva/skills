//! Microgrid Agent — Edge AI kernel daemon
//!
//! Single-binary Rust daemon for autonomous microgrid management.
//! Reads sensors, optimizes dispatch, enforces safety, logs everything.
//! Calls Python ML worker via subprocess for forecasting.

mod autonomic;
mod config;
mod dashboard;
mod devices;
mod dispatch;
mod journal;
mod knowledge;
mod ml_bridge;
mod sync;
mod tools;

use clap::Parser;
use std::path::PathBuf;
use tracing::{error, info};

#[derive(Parser)]
#[command(name = "microgrid-agent", about = "Edge AI kernel for microgrid management")]
struct Cli {
    /// Path to site configuration file
    #[arg(short, long, default_value = "config/site.toml")]
    config: PathBuf,

    /// Run with simulated devices (no hardware required)
    #[arg(long)]
    simulate: bool,

    /// Shadow mode: read sensors but don't actuate
    #[arg(long)]
    shadow: bool,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize structured logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "microgrid_agent=info,tokio_modbus=warn".into()),
        )
        .json()
        .init();

    let cli = Cli::parse();
    info!(config = %cli.config.display(), simulate = cli.simulate, "Starting microgrid agent");

    // Load configuration
    let config = config::SiteConfig::load(&cli.config)?;
    info!(site_id = %config.site.id, region = %config.site.region, "Site configured");

    // Initialize subsystems
    let journal = journal::EventJournal::open(&config.paths.data_dir.join("events.redb"))?;
    let knowledge = knowledge::KnowledgeGraph::open(&config.paths.db_path).await?;
    let autonomic = autonomic::AutonomicController::new(&config.autonomic);
    let devices = devices::DeviceRegistry::from_config(&config.paths.config_dir, cli.simulate)?;
    let dispatcher = dispatch::Dispatcher::new(&config);
    let ml = ml_bridge::MlBridge::new(&config.paths.model_dir);
    let fleet_sync = sync::FleetSync::new(&config.connectivity, &config.paths.sync_queue_dir);

    // Notify systemd we're ready
    let _ = sd_notify::notify(true, &[sd_notify::NotifyState::Ready]);
    info!("Agent ready — entering control loop");

    // Run the main control loop
    let agent = Agent {
        config,
        journal,
        knowledge,
        autonomic,
        devices,
        dispatcher,
        ml,
        fleet_sync,
        shadow: cli.shadow,
    };

    // Handle shutdown signals
    let shutdown = tokio::signal::ctrl_c();

    tokio::select! {
        result = agent.run() => {
            if let Err(e) = result {
                error!(error = %e, "Agent loop exited with error");
            }
        }
        _ = shutdown => {
            info!("Shutdown signal received");
        }
    }

    let _ = sd_notify::notify(true, &[sd_notify::NotifyState::Stopping]);
    info!("Agent stopped");
    Ok(())
}

struct Agent {
    config: config::SiteConfig,
    journal: journal::EventJournal,
    knowledge: knowledge::KnowledgeGraph,
    autonomic: autonomic::AutonomicController,
    devices: devices::DeviceRegistry,
    dispatcher: dispatch::Dispatcher,
    ml: ml_bridge::MlBridge,
    fleet_sync: sync::FleetSync,
    shadow: bool,
}

impl Agent {
    async fn run(&self) -> anyhow::Result<()> {
        let mut sensor_interval = tokio::time::interval(
            std::time::Duration::from_secs_f64(self.config.site.sensor_interval_s),
        );
        let mut dispatch_interval = tokio::time::interval(
            std::time::Duration::from_secs_f64(self.config.site.dispatch_interval_s),
        );
        let mut forecast_interval = tokio::time::interval(
            std::time::Duration::from_secs_f64(self.config.site.forecast_interval_s),
        );
        let mut watchdog_interval =
            tokio::time::interval(std::time::Duration::from_secs(20)); // 2/3 of WatchdogSec=30s

        let mut state = AgentState::default();

        loop {
            tokio::select! {
                _ = sensor_interval.tick() => {
                    // PERCEIVE: read all sensors
                    if let Ok(readings) = self.devices.read_all().await {
                        state.update_readings(readings);
                        self.journal.append_readings(&state.latest_readings)?;
                    }
                }
                _ = dispatch_interval.tick() => {
                    // OPTIMIZE: compute dispatch
                    let decision = self.dispatcher.solve(&state, &self.knowledge).await;

                    // SAFETY: autonomic check — may override
                    let final_decision = self.autonomic.enforce(decision, &state);

                    // ACTUATE: send commands (unless shadow mode)
                    if !self.shadow {
                        self.devices.actuate(&final_decision).await?;
                    }

                    // LOG: every decision persisted
                    self.journal.append_decision(&final_decision)?;
                }
                _ = forecast_interval.tick() => {
                    // PREDICT: spawn Python ML worker
                    match self.ml.request_forecast(&state.history).await {
                        Ok(forecast) => state.forecast = Some(forecast),
                        Err(e) => {
                            tracing::warn!(error = %e, "ML forecast failed, using fallback");
                            state.forecast = Some(self.ml.persistence_fallback(&state.history));
                        }
                    }
                }
                _ = watchdog_interval.tick() => {
                    // HEARTBEAT: tell systemd we're alive
                    let _ = sd_notify::notify(false, &[sd_notify::NotifyState::Watchdog]);
                }
            }
        }
    }
}

#[derive(Default)]
pub struct AgentState {
    pub latest_readings: devices::SensorReadings,
    pub history: Vec<devices::SensorReadings>,
    pub forecast: Option<ml_bridge::Forecast>,
}

impl AgentState {
    fn update_readings(&mut self, readings: devices::SensorReadings) {
        self.latest_readings = readings.clone();
        self.history.push(readings);
        // Keep last 24h at 1Hz = 86,400 entries
        if self.history.len() > 86_400 {
            self.history.drain(..self.history.len() - 86_400);
        }
    }
}
