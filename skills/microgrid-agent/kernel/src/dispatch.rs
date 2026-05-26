//! Dispatch optimizer.
//!
//! Computes the optimal power dispatch decision for each control cycle.
//! Uses a rule-based priority strategy (solar -> battery -> diesel) with
//! a placeholder for LP optimization via `good_lp`.

use tracing::info;

use crate::config::SiteConfig;
use crate::knowledge::KnowledgeGraph;

// ---------------------------------------------------------------------------
// Dispatch decision — the canonical "action" type for the control loop
// ---------------------------------------------------------------------------

/// A dispatch decision produced by the optimizer and potentially modified
/// by the autonomic safety controller.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DispatchDecision {
    /// Solar power to deliver (kW).
    pub solar_kw: f64,
    /// Battery power (kW). Positive = charging, negative = discharging.
    pub battery_kw: f64,
    /// Diesel generator output (kW).
    pub diesel_kw: f64,
    /// Load shed (kW) — demand that cannot be met.
    pub load_shed_kw: f64,
    /// Whether to start the diesel generator.
    pub diesel_start: bool,
    /// Whether to stop the diesel generator.
    pub diesel_stop: bool,
    /// Human-readable reasoning for this decision.
    pub reasoning: String,
    /// Whether the autonomic controller overrode the optimizer's decision.
    pub overridden: bool,
}

impl Default for DispatchDecision {
    fn default() -> Self {
        Self {
            solar_kw: 0.0,
            battery_kw: 0.0,
            diesel_kw: 0.0,
            load_shed_kw: 0.0,
            diesel_start: false,
            diesel_stop: false,
            reasoning: String::new(),
            overridden: false,
        }
    }
}

// ---------------------------------------------------------------------------
// Dispatcher
// ---------------------------------------------------------------------------

/// The dispatch optimizer. Computes power allocation each control cycle.
pub struct Dispatcher {
    solar_capacity_kwp: f64,
    battery_capacity_kwh: f64,
    diesel_capacity_kw: f64,
    max_dod: f64,
}

impl Dispatcher {
    /// Create a new dispatcher from the site configuration.
    pub fn new(config: &SiteConfig) -> Self {
        Self {
            solar_capacity_kwp: config.solar.capacity_kwp,
            battery_capacity_kwh: config.battery.capacity_kwh,
            diesel_capacity_kw: config.diesel.capacity_kw,
            max_dod: config.battery.max_dod,
        }
    }

    /// Compute the dispatch decision for the current state.
    ///
    /// Priority order: solar -> battery discharge -> diesel.
    /// Excess solar charges the battery.
    ///
    /// The `_kg` parameter is available for knowledge-graph-informed
    /// dispatch (e.g. priority loads, market days) but is not used yet.
    pub async fn solve(
        &self,
        state: &crate::AgentState,
        _kg: &KnowledgeGraph,
    ) -> DispatchDecision {
        let readings = &state.latest_readings;
        let load = readings.load_kw;
        let solar = readings.solar_kw;
        let soc = readings.battery_soc_pct;

        // --- Rule-based dispatch (solar -> battery -> diesel) ---

        let mut decision = DispatchDecision::default();
        let mut remaining_load = load;

        // 1. Use all available solar
        let solar_to_load = solar.min(remaining_load);
        decision.solar_kw = solar_to_load;
        remaining_load -= solar_to_load;

        // Excess solar charges battery
        let excess_solar = solar - solar_to_load;
        if excess_solar > 0.0 && soc < 95.0 {
            decision.battery_kw = excess_solar; // positive = charging
        }

        // 2. Discharge battery to cover remaining load
        let min_soc = (1.0 - self.max_dod) * 100.0;
        if remaining_load > 0.0 && soc > min_soc {
            let max_battery_discharge = self.battery_capacity_kwh * 0.5; // C/2 rate limit
            let battery_discharge = remaining_load.min(max_battery_discharge);
            decision.battery_kw = -battery_discharge; // negative = discharging
            remaining_load -= battery_discharge;
        }

        // 3. Start diesel if still unmet load
        if remaining_load > 0.5 {
            // >500W threshold to avoid hunting
            let diesel_output = remaining_load.min(self.diesel_capacity_kw);
            decision.diesel_kw = diesel_output;
            decision.diesel_start = true;
            remaining_load -= diesel_output;
        }

        // 4. Any remaining = load shed
        if remaining_load > 0.01 {
            decision.load_shed_kw = remaining_load;
        }

        // Build reasoning string
        decision.reasoning = format!(
            "Rule-based: solar={:.1}kW to load, battery={:.1}kW, diesel={:.1}kW, shed={:.1}kW (SOC={:.0}%)",
            decision.solar_kw, decision.battery_kw, decision.diesel_kw, decision.load_shed_kw, soc
        );

        if decision.load_shed_kw > 0.0 {
            tracing::warn!(
                shed_kw = decision.load_shed_kw,
                "Load shedding required — insufficient generation"
            );
        }

        info!(
            solar = decision.solar_kw,
            battery = decision.battery_kw,
            diesel = decision.diesel_kw,
            reasoning = %decision.reasoning,
            "Dispatch computed"
        );

        // TODO: Replace rule-based dispatch with LP optimization using good_lp.
        //       The LP formulation should minimize:
        //         cost = diesel_fuel_cost + battery_degradation_cost + load_shed_penalty
        //       Subject to:
        //         solar + battery_discharge + diesel - battery_charge = load - shed
        //         0 <= shed <= load
        //         0 <= diesel <= diesel_capacity
        //         min_soc <= soc_next <= max_soc
        //       Use KnowledgeGraph to query priority loads and adjust shed penalties.

        decision
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::SiteConfig;
    use crate::devices::SensorReadings;
    use crate::AgentState;

    /// Build a minimal SiteConfig from a TOML string for testing.
    fn make_test_config(solar_kwp: f64, battery_kwh: f64, diesel_kw: f64, max_dod: f64) -> SiteConfig {
        let toml_str = format!(
            r#"
[site]
id = "test"

[solar]
capacity_kwp = {solar_kwp}

[battery]
capacity_kwh = {battery_kwh}
max_dod = {max_dod}

[diesel]
capacity_kw = {diesel_kw}
"#
        );
        toml::from_str(&toml_str).unwrap()
    }

    fn make_state(solar_kw: f64, load_kw: f64, soc: f64) -> AgentState {
        AgentState {
            latest_readings: SensorReadings {
                solar_kw,
                load_kw,
                battery_soc_pct: soc,
                ..SensorReadings::default()
            },
            history: vec![],
            forecast: None,
        }
    }

    #[tokio::test]
    async fn test_solar_covers_load() {
        let config = make_test_config(10.0, 20.0, 10.0, 0.8);
        let dispatcher = Dispatcher::new(&config);
        let kg = KnowledgeGraph::open(&std::env::temp_dir().join("mg_test_dispatch_kg1.db")).await.unwrap();

        let state = make_state(5.0, 3.0, 50.0); // solar > load
        let decision = dispatcher.solve(&state, &kg).await;

        assert!((decision.solar_kw - 3.0).abs() < 0.01, "Solar to load should equal load");
        assert!(decision.diesel_kw < 0.01, "No diesel needed");
        assert!(decision.load_shed_kw < 0.01, "No load shedding needed");
    }

    #[tokio::test]
    async fn test_battery_covers_shortfall() {
        let config = make_test_config(10.0, 20.0, 10.0, 0.8);
        let dispatcher = Dispatcher::new(&config);
        let kg = KnowledgeGraph::open(&std::env::temp_dir().join("mg_test_dispatch_kg2.db")).await.unwrap();

        // min_soc = (1 - 0.8) * 100 = 20. SOC 50 > 20, so battery can discharge.
        let state = make_state(2.0, 5.0, 50.0); // solar < load
        let decision = dispatcher.solve(&state, &kg).await;

        assert!(decision.battery_kw < 0.0, "Battery should discharge (negative kW)");
        assert!(decision.diesel_kw < 0.01, "No diesel needed when battery can cover");
    }

    #[tokio::test]
    async fn test_diesel_starts_when_needed() {
        let config = make_test_config(10.0, 5.0, 10.0, 0.8);
        let dispatcher = Dispatcher::new(&config);
        let kg = KnowledgeGraph::open(&std::env::temp_dir().join("mg_test_dispatch_kg3.db")).await.unwrap();

        // SOC at min (20% = (1-0.8)*100), so battery cannot discharge.
        // Solar = 0, load = 8 => all unmet by solar/battery, diesel should start
        let state = make_state(0.0, 8.0, 20.0);
        let decision = dispatcher.solve(&state, &kg).await;

        assert!(decision.diesel_kw > 0.0, "Diesel should start to cover load");
        assert!(decision.diesel_start, "diesel_start should be true");
    }

    #[tokio::test]
    async fn test_load_shedding() {
        // Very small diesel capacity
        let config = make_test_config(0.0, 5.0, 2.0, 0.8);
        let dispatcher = Dispatcher::new(&config);
        let kg = KnowledgeGraph::open(&std::env::temp_dir().join("mg_test_dispatch_kg4.db")).await.unwrap();

        // No solar, SOC at min, load = 10 >> diesel capacity (2)
        let state = make_state(0.0, 10.0, 20.0);
        let decision = dispatcher.solve(&state, &kg).await;

        assert!(decision.load_shed_kw > 0.0, "Load shedding should occur when all sources are insufficient");
    }

    #[tokio::test]
    async fn test_excess_solar_charges_battery() {
        let config = make_test_config(20.0, 20.0, 10.0, 0.8);
        let dispatcher = Dispatcher::new(&config);
        let kg = KnowledgeGraph::open(&std::env::temp_dir().join("mg_test_dispatch_kg5.db")).await.unwrap();

        let state = make_state(10.0, 3.0, 50.0); // excess solar = 7
        let decision = dispatcher.solve(&state, &kg).await;

        assert!(decision.battery_kw > 0.0, "Excess solar should charge battery (positive kW)");
    }

    #[tokio::test]
    async fn test_dispatch_decision_serialization() {
        let decision = DispatchDecision {
            solar_kw: 5.5,
            battery_kw: -2.1,
            diesel_kw: 3.0,
            load_shed_kw: 0.5,
            diesel_start: true,
            diesel_stop: false,
            reasoning: "Test reasoning".into(),
            overridden: true,
        };
        let json = serde_json::to_string(&decision).unwrap();
        let deserialized: DispatchDecision = serde_json::from_str(&json).unwrap();
        assert!((deserialized.solar_kw - 5.5).abs() < f64::EPSILON);
        assert!((deserialized.battery_kw - (-2.1)).abs() < f64::EPSILON);
        assert!((deserialized.diesel_kw - 3.0).abs() < f64::EPSILON);
        assert!((deserialized.load_shed_kw - 0.5).abs() < f64::EPSILON);
        assert!(deserialized.diesel_start);
        assert!(!deserialized.diesel_stop);
        assert_eq!(deserialized.reasoning, "Test reasoning");
        assert!(deserialized.overridden);
    }
}
