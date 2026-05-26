//! Autonomic safety controller.
//!
//! The last line of defense before actuation. Enforces hard safety
//! constraints on every dispatch decision, overriding the optimizer
//! when necessary to protect equipment and maintain minimum service.
//!
//! Follows the Life Agent OS Autonomic pattern: observe → compare → act.

use tracing::{info, warn};

use crate::config::AutonomicSection;
use crate::dispatch::DispatchDecision;

// ---------------------------------------------------------------------------
// Autonomic controller
// ---------------------------------------------------------------------------

/// Safety controller that enforces operational constraints on dispatch decisions.
///
/// Constraints enforced:
/// - `min_soc_pct`: Never discharge battery below this threshold.
/// - `max_soc_pct`: Stop charging above this threshold.
/// - `diesel_start_soc_pct`: Auto-start diesel when SOC drops below this.
/// - `diesel_stop_soc_pct`: Auto-stop diesel when SOC rises above this.
/// - `max_diesel_hours_per_day`: Limit daily diesel runtime.
pub struct AutonomicController {
    min_soc_pct: f64,
    max_soc_pct: f64,
    diesel_start_soc_pct: f64,
    diesel_stop_soc_pct: f64,
    max_diesel_hours_per_day: f64,
    /// Accumulated diesel runtime today (hours). Reset at midnight.
    diesel_hours_today: std::sync::Mutex<f64>,
}

impl AutonomicController {
    /// Create a new autonomic controller from the site autonomic configuration.
    pub fn new(config: &AutonomicSection) -> Self {
        info!(
            min_soc = config.min_soc_pct,
            max_soc = config.max_soc_pct,
            diesel_start = config.diesel_start_soc_pct,
            diesel_stop = config.diesel_stop_soc_pct,
            max_diesel_hours = config.max_diesel_hours_per_day,
            "Autonomic controller initialized"
        );

        Self {
            min_soc_pct: config.min_soc_pct,
            max_soc_pct: config.max_soc_pct,
            diesel_start_soc_pct: config.diesel_start_soc_pct,
            diesel_stop_soc_pct: config.diesel_stop_soc_pct,
            max_diesel_hours_per_day: config.max_diesel_hours_per_day,
            diesel_hours_today: std::sync::Mutex::new(0.0),
        }
    }

    /// Enforce safety constraints on a dispatch decision.
    ///
    /// Takes the optimizer's decision and the current agent state,
    /// and returns a (possibly modified) decision with safety overrides applied.
    /// All overrides are logged via `tracing`.
    pub fn enforce(
        &self,
        mut decision: DispatchDecision,
        state: &crate::AgentState,
    ) -> DispatchDecision {
        let soc = state.latest_readings.battery_soc_pct;
        let mut was_overridden = false;

        // --- Shield 1: Minimum SOC protection ---
        // Prevent battery discharge when SOC is at or below minimum
        if soc <= self.min_soc_pct && decision.battery_kw < 0.0 {
            warn!(
                soc,
                min_soc = self.min_soc_pct,
                original_battery_kw = decision.battery_kw,
                "OVERRIDE: Blocking battery discharge — SOC at minimum"
            );
            decision.battery_kw = 0.0;
            was_overridden = true;
        }

        // --- Shield 2: Maximum SOC protection ---
        // Prevent overcharging
        if soc >= self.max_soc_pct && decision.battery_kw > 0.0 {
            warn!(
                soc,
                max_soc = self.max_soc_pct,
                original_battery_kw = decision.battery_kw,
                "OVERRIDE: Blocking battery charge — SOC at maximum"
            );
            decision.battery_kw = 0.0;
            was_overridden = true;
        }

        // --- Shield 3: Auto-start diesel on low SOC ---
        if soc <= self.diesel_start_soc_pct && !decision.diesel_start && decision.diesel_kw == 0.0 {
            let diesel_hours = self.diesel_hours_today.lock().unwrap();
            if *diesel_hours < self.max_diesel_hours_per_day {
                warn!(
                    soc,
                    threshold = self.diesel_start_soc_pct,
                    "OVERRIDE: Auto-starting diesel — SOC critically low"
                );
                decision.diesel_start = true;
                // TODO: Set diesel_kw to a reasonable default based on diesel capacity
                decision.diesel_kw = 5.0; // Conservative default
                was_overridden = true;
            } else {
                warn!(
                    diesel_hours = *diesel_hours,
                    max_hours = self.max_diesel_hours_per_day,
                    "Diesel auto-start blocked — daily runtime limit reached"
                );
            }
        }

        // --- Shield 4: Auto-stop diesel on high SOC ---
        if soc >= self.diesel_stop_soc_pct && decision.diesel_kw > 0.0 && !decision.diesel_stop {
            warn!(
                soc,
                threshold = self.diesel_stop_soc_pct,
                "OVERRIDE: Auto-stopping diesel — SOC recovered"
            );
            decision.diesel_kw = 0.0;
            decision.diesel_stop = true;
            decision.diesel_start = false;
            was_overridden = true;
        }

        // --- Shield 5: Daily diesel runtime limit ---
        {
            let mut diesel_hours = self.diesel_hours_today.lock().unwrap();
            if decision.diesel_kw > 0.0 {
                // Approximate: each dispatch cycle adds ~dispatch_interval_s / 3600 hours
                // TODO: Use actual elapsed time between dispatches
                let increment = 5.0 / 3600.0; // Assume 5-second dispatch interval
                *diesel_hours += increment;

                if *diesel_hours >= self.max_diesel_hours_per_day {
                    warn!(
                        diesel_hours = *diesel_hours,
                        max_hours = self.max_diesel_hours_per_day,
                        "OVERRIDE: Shutting down diesel — daily runtime limit reached"
                    );
                    decision.diesel_kw = 0.0;
                    decision.diesel_stop = true;
                    decision.diesel_start = false;
                    was_overridden = true;
                }
            }

            // TODO: Reset diesel_hours_today at midnight (requires a timer or
            //       checking the current date against a stored last-reset date).
        }

        if was_overridden {
            decision.overridden = true;
            decision.reasoning = format!(
                "{} [AUTONOMIC OVERRIDE: soc={:.0}%]",
                decision.reasoning, soc
            );
        }

        decision
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::AutonomicSection;
    use crate::devices::SensorReadings;
    use crate::dispatch::DispatchDecision;
    use crate::AgentState;

    fn make_test_config() -> AutonomicSection {
        AutonomicSection {
            min_soc_pct: 20.0,
            max_soc_pct: 95.0,
            diesel_start_soc_pct: 25.0,
            diesel_stop_soc_pct: 60.0,
            max_diesel_hours_per_day: 16.0,
            renewable_target_fraction: 0.70,
        }
    }

    fn make_test_state(soc: f64) -> AgentState {
        AgentState {
            latest_readings: SensorReadings {
                battery_soc_pct: soc,
                ..SensorReadings::default()
            },
            history: vec![],
            forecast: None,
        }
    }

    #[test]
    fn test_shield_min_soc_blocks_discharge() {
        let ctrl = AutonomicController::new(&make_test_config());
        let decision = DispatchDecision {
            battery_kw: -5.0, // discharging
            ..DispatchDecision::default()
        };
        let state = make_test_state(20.0); // SOC at min
        let result = ctrl.enforce(decision, &state);
        assert_eq!(result.battery_kw, 0.0, "Discharge should be blocked at min SOC");
    }

    #[test]
    fn test_shield_max_soc_blocks_charge() {
        let ctrl = AutonomicController::new(&make_test_config());
        let decision = DispatchDecision {
            battery_kw: 5.0, // charging
            ..DispatchDecision::default()
        };
        let state = make_test_state(95.0); // SOC at max
        let result = ctrl.enforce(decision, &state);
        assert_eq!(result.battery_kw, 0.0, "Charge should be blocked at max SOC");
    }

    #[test]
    fn test_shield_diesel_autostart_on_low_soc() {
        let ctrl = AutonomicController::new(&make_test_config());
        let decision = DispatchDecision {
            diesel_kw: 0.0,
            diesel_start: false,
            ..DispatchDecision::default()
        };
        let state = make_test_state(25.0); // SOC at diesel_start threshold
        let result = ctrl.enforce(decision, &state);
        assert!(result.diesel_start, "Diesel should auto-start when SOC <= diesel_start_soc");
        assert!(result.diesel_kw > 0.0, "Diesel kW should be set when auto-started");
    }

    #[test]
    fn test_shield_diesel_autostop_on_high_soc() {
        let ctrl = AutonomicController::new(&make_test_config());
        let decision = DispatchDecision {
            diesel_kw: 5.0, // diesel running
            diesel_start: true,
            diesel_stop: false,
            ..DispatchDecision::default()
        };
        let state = make_test_state(60.0); // SOC at diesel_stop threshold
        let result = ctrl.enforce(decision, &state);
        assert!(result.diesel_stop, "Diesel should auto-stop when SOC >= diesel_stop_soc");
        assert_eq!(result.diesel_kw, 0.0, "Diesel kW should be zero after auto-stop");
    }

    #[test]
    fn test_no_override_when_safe() {
        let ctrl = AutonomicController::new(&make_test_config());
        let decision = DispatchDecision {
            solar_kw: 5.0,
            battery_kw: -2.0, // discharging
            diesel_kw: 0.0,
            load_shed_kw: 0.0,
            diesel_start: false,
            diesel_stop: false,
            reasoning: "Normal dispatch".into(),
            overridden: false,
        };
        let state = make_test_state(50.0); // healthy SOC
        let result = ctrl.enforce(decision, &state);
        assert!(!result.overridden, "No override expected when operating within safe bounds");
        assert_eq!(result.battery_kw, -2.0, "Battery kW should pass through unchanged");
    }

    #[test]
    fn test_override_sets_flag() {
        let ctrl = AutonomicController::new(&make_test_config());
        let decision = DispatchDecision {
            battery_kw: -5.0,
            reasoning: "Optimizer wants discharge".into(),
            ..DispatchDecision::default()
        };
        let state = make_test_state(15.0); // below min SOC
        let result = ctrl.enforce(decision, &state);
        assert!(result.overridden, "Override flag should be set");
        assert!(
            result.reasoning.contains("OVERRIDE"),
            "Reasoning should mention OVERRIDE, got: {}",
            result.reasoning
        );
    }

    #[test]
    fn test_diesel_runtime_limit() {
        let config = AutonomicSection {
            max_diesel_hours_per_day: 0.001, // very small limit for testing
            ..make_test_config()
        };
        let ctrl = AutonomicController::new(&config);
        // Simulate multiple cycles with diesel running to exceed the limit
        let state = make_test_state(50.0);
        let mut last_result = DispatchDecision::default();
        for _ in 0..100 {
            let decision = DispatchDecision {
                diesel_kw: 5.0,
                diesel_start: true,
                ..DispatchDecision::default()
            };
            last_result = ctrl.enforce(decision, &state);
        }
        // After many cycles the limit should be hit
        assert_eq!(
            last_result.diesel_kw, 0.0,
            "Diesel should be forced to stop after runtime limit"
        );
        assert!(last_result.diesel_stop, "diesel_stop should be set after limit");
    }
}
