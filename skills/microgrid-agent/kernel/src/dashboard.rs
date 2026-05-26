//! Local HTTP dashboard.
//!
//! Serves a lightweight HTTP API for local monitoring and debugging.
//! Accessible from the local network (e.g., a technician's phone
//! connected to the microgrid's Wi-Fi).

use axum::{extract::State, routing::get, Json, Router};
use serde::Serialize;
use std::sync::Arc;
use tracing::info;

use crate::devices::SensorReadings;

// ---------------------------------------------------------------------------
// Shared dashboard state
// ---------------------------------------------------------------------------

/// Shared state exposed to the dashboard HTTP handlers.
///
/// This is a snapshot updated by the main control loop, not a live reference.
/// The dashboard reads from this state; it never writes to the control loop.
pub struct DashboardState {
    /// Latest sensor readings.
    pub latest_readings: std::sync::RwLock<SensorReadings>,
    /// Agent uptime start.
    pub started_at: chrono::DateTime<chrono::Utc>,
    /// Site ID from configuration.
    pub site_id: String,
}

/// JSON response for the /api/status endpoint.
#[derive(Serialize)]
struct StatusResponse {
    site_id: String,
    uptime_seconds: i64,
    readings: ReadingsSnapshot,
}

/// Serializable snapshot of sensor readings for the API.
#[derive(Serialize)]
struct ReadingsSnapshot {
    timestamp: String,
    solar_kw: f64,
    load_kw: f64,
    battery_soc_pct: f64,
    battery_kw: f64,
    diesel_kw: f64,
    irradiance_wm2: f64,
    temperature_c: f64,
}

// ---------------------------------------------------------------------------
// Dashboard server
// ---------------------------------------------------------------------------

/// Start the local HTTP dashboard on the given port.
///
/// Runs an axum server with a basic /api/status endpoint.
/// This function spawns a background task and returns immediately.
pub async fn start_dashboard(
    state: Arc<DashboardState>,
    port: u16,
) -> anyhow::Result<()> {
    let app = Router::new()
        .route("/api/status", get(status_handler))
        .route("/api/health", get(health_handler))
        .with_state(state);

    let addr = std::net::SocketAddr::from(([0, 0, 0, 0], port));
    info!(%addr, "Starting local dashboard");

    let listener = tokio::net::TcpListener::bind(addr).await?;

    tokio::spawn(async move {
        if let Err(e) = axum::serve(listener, app).await {
            tracing::error!(error = %e, "Dashboard server error");
        }
    });

    Ok(())
}

/// Handler for GET /api/status
async fn status_handler(
    State(state): State<Arc<DashboardState>>,
) -> Json<StatusResponse> {
    let readings = state.latest_readings.read().unwrap();
    let uptime = chrono::Utc::now()
        .signed_duration_since(state.started_at)
        .num_seconds();

    Json(StatusResponse {
        site_id: state.site_id.clone(),
        uptime_seconds: uptime,
        readings: ReadingsSnapshot {
            timestamp: readings.timestamp.to_rfc3339(),
            solar_kw: readings.solar_kw,
            load_kw: readings.load_kw,
            battery_soc_pct: readings.battery_soc_pct,
            battery_kw: readings.battery_kw,
            diesel_kw: readings.diesel_kw,
            irradiance_wm2: readings.irradiance_wm2,
            temperature_c: readings.temperature_c,
        },
    })
}

/// Handler for GET /api/health — simple liveness check.
async fn health_handler() -> &'static str {
    "ok"
}

// TODO: Add endpoints:
// - GET /api/history?hours=N — recent sensor history
// - GET /api/decisions?hours=N — recent dispatch decisions
// - GET /api/forecast — current forecast
// - GET / — serve a minimal HTML dashboard (embedded in the binary via include_str!)
// - WebSocket /ws/live — real-time sensor stream
