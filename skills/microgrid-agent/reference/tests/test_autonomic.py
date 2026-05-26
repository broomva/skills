"""
Tests for the autonomic safety controller.

Covers:
- SOC floor blocks discharge
- SOC ceiling blocks charge
- Diesel auto-start advisory on high unserved
- Diesel auto-stop (cooldown logic)
- Normal decisions pass through without override
- Override flag is set on corrected decisions
"""

import time

import pytest

from src.autonomic import AutonomicController, SafetyConfig, SafetyOverride
from src.dispatch import DispatchDecision, MicrogridState


def _make_state(**overrides) -> MicrogridState:
    """Build a default MicrogridState, overriding any field."""
    defaults = dict(
        solar_available_kw=5.0,
        demand_kw=5.0,
        battery_soc_pct=50.0,
        battery_capacity_kwh=10.0,
        battery_max_charge_kw=5.0,
        battery_max_discharge_kw=5.0,
        diesel_max_kw=5.0,
        diesel_min_kw=1.0,
        diesel_running=False,
        priority_loads_kw=0.0,
    )
    defaults.update(overrides)
    return MicrogridState(**defaults)


def _make_decision(**overrides) -> DispatchDecision:
    """Build a default DispatchDecision, overriding any field."""
    defaults = dict(
        solar_kw=3.0,
        battery_kw=0.0,
        diesel_kw=0.0,
        curtailed_kw=0.0,
        unserved_kw=0.0,
        soc_pct=50.0,
        method="lp",
    )
    defaults.update(overrides)
    return DispatchDecision(**defaults)


# ===========================================================================
# SOC Floor Tests
# ===========================================================================

class TestMinSocBlocksDischarge:
    """SOC at min should block battery discharge."""

    def test_discharge_blocked_at_min_soc(self):
        """When SOC is below hard minimum, battery discharge must be zeroed."""
        ctrl = AutonomicController(SafetyConfig(min_soc_pct=15.0))
        decision = _make_decision(battery_kw=3.0, soc_pct=10.0)  # discharging at low SOC
        state = _make_state(battery_soc_pct=10.0)

        corrected, overrides = ctrl.enforce(decision, state)

        assert corrected.battery_kw == 0.0, "Discharge must be blocked at min SOC"
        assert len(overrides) >= 1
        assert any(o.field_name == "battery_kw" for o in overrides)

    def test_discharge_blocked_at_exact_min(self):
        """At exactly min SOC, discharge should still be blocked."""
        ctrl = AutonomicController(SafetyConfig(min_soc_pct=15.0))
        decision = _make_decision(battery_kw=2.0, soc_pct=14.9)
        state = _make_state(battery_soc_pct=14.9)

        corrected, overrides = ctrl.enforce(decision, state)
        assert corrected.battery_kw == 0.0

    def test_soc_clamped_to_min(self):
        """SOC should be clamped to at least min_soc_pct after override."""
        ctrl = AutonomicController(SafetyConfig(min_soc_pct=15.0))
        decision = _make_decision(battery_kw=5.0, soc_pct=10.0)
        state = _make_state(battery_soc_pct=10.0)

        corrected, _ = ctrl.enforce(decision, state)
        assert corrected.soc_pct >= 15.0


# ===========================================================================
# SOC Ceiling Tests
# ===========================================================================

class TestMaxSocBlocksCharge:
    """SOC at max should block battery charge."""

    def test_charge_blocked_at_max_soc(self):
        """When SOC is above hard maximum, battery charge must be zeroed."""
        ctrl = AutonomicController(SafetyConfig(max_soc_pct=98.0))
        # battery_kw < 0 means charging in DispatchDecision convention
        decision = _make_decision(battery_kw=-3.0, soc_pct=99.0)
        state = _make_state(battery_soc_pct=99.0)

        corrected, overrides = ctrl.enforce(decision, state)

        assert corrected.battery_kw == 0.0, "Charge must be blocked at max SOC"
        assert len(overrides) >= 1
        assert any(o.field_name == "battery_kw" for o in overrides)

    def test_charge_allowed_below_max(self):
        """Charging should be allowed when SOC is below max."""
        ctrl = AutonomicController(SafetyConfig(max_soc_pct=98.0))
        decision = _make_decision(battery_kw=-3.0, soc_pct=80.0)
        state = _make_state(battery_soc_pct=80.0)

        corrected, overrides = ctrl.enforce(decision, state)
        assert corrected.battery_kw == -3.0, "Charging should be allowed below max SOC"
        # No SOC-related override expected
        soc_overrides = [o for o in overrides if "SOC" in o.reason and "above" in o.reason]
        assert len(soc_overrides) == 0


# ===========================================================================
# Diesel Auto-Start / Auto-Stop
# ===========================================================================

class TestDieselAutostart:
    """Low SOC / high unserved triggers diesel advisory."""

    def test_diesel_advisory_on_high_unserved(self):
        """When unserved exceeds threshold and diesel is off, a warning should fire."""
        config = SafetyConfig(max_unserved_before_diesel_start=0.5)
        ctrl = AutonomicController(config)
        # Decision has high unserved but diesel at 0
        decision = _make_decision(diesel_kw=0.0, unserved_kw=2.0)
        state = _make_state(diesel_max_kw=5.0)

        # The autonomic controller logs a warning but does NOT override
        # (it's advisory per the code). We verify no diesel override occurs
        # but the decision passes through.
        corrected, overrides = ctrl.enforce(decision, state)
        # No diesel override (the controller only logs a warning)
        diesel_overrides = [o for o in overrides if o.field_name == "diesel_kw"]
        assert len(diesel_overrides) == 0
        assert corrected.unserved_kw == 2.0


class TestDieselAutostop:
    """Diesel runtime limit should stop diesel after max continuous hours."""

    def test_diesel_stopped_after_max_hours(self):
        """Diesel should be forced off after exceeding max continuous runtime."""
        config = SafetyConfig(max_diesel_continuous_hours=8.0)
        ctrl = AutonomicController(config)
        # Simulate that diesel has been running for a long time
        ctrl._diesel_start_time = time.time() - (9 * 3600)  # 9 hours ago

        decision = _make_decision(diesel_kw=3.0)
        state = _make_state()

        corrected, overrides = ctrl.enforce(decision, state)
        assert corrected.diesel_kw == 0.0, "Diesel must stop after max continuous hours"
        assert any(o.field_name == "diesel_kw" for o in overrides)

    def test_diesel_allowed_within_limit(self):
        """Diesel should keep running within the time limit."""
        config = SafetyConfig(max_diesel_continuous_hours=8.0)
        ctrl = AutonomicController(config)
        ctrl._diesel_start_time = time.time() - (2 * 3600)  # 2 hours ago

        decision = _make_decision(diesel_kw=3.0)
        state = _make_state()

        corrected, overrides = ctrl.enforce(decision, state)
        assert corrected.diesel_kw == 3.0
        diesel_overrides = [o for o in overrides if o.field_name == "diesel_kw"]
        assert len(diesel_overrides) == 0

    def test_diesel_cooldown_blocks_restart(self):
        """Diesel should not restart during cooldown period."""
        config = SafetyConfig(diesel_cooldown_minutes=5.0)
        ctrl = AutonomicController(config)
        ctrl._diesel_stop_time = time.time() - 60  # stopped 1 minute ago

        decision = _make_decision(diesel_kw=3.0)
        state = _make_state()

        corrected, overrides = ctrl.enforce(decision, state)
        assert corrected.diesel_kw == 0.0, "Diesel must wait for cooldown"
        assert any("cooldown" in o.reason.lower() for o in overrides)


# ===========================================================================
# Normal Pass-Through
# ===========================================================================

class TestNoOverrideNormal:
    """Safe decisions should pass through without modification."""

    def test_normal_decision_unchanged(self):
        """A decision within all safety limits should not be modified."""
        ctrl = AutonomicController(SafetyConfig())
        decision = _make_decision(
            solar_kw=3.0, battery_kw=1.0, diesel_kw=0.0,
            curtailed_kw=0.0, unserved_kw=0.0, soc_pct=50.0,
        )
        state = _make_state(battery_soc_pct=50.0)

        corrected, overrides = ctrl.enforce(decision, state)
        assert len(overrides) == 0, "No overrides expected for safe decision"
        assert corrected.solar_kw == 3.0
        assert corrected.battery_kw == 1.0
        assert corrected.diesel_kw == 0.0

    def test_fallback_stored_after_enforce(self):
        """After enforce(), get_fallback_dispatch() should return last decision."""
        ctrl = AutonomicController(SafetyConfig())
        assert ctrl.get_fallback_dispatch() is None  # initially empty

        decision = _make_decision(solar_kw=4.0)
        state = _make_state()
        corrected, _ = ctrl.enforce(decision, state)

        fallback = ctrl.get_fallback_dispatch()
        assert fallback is not None
        assert fallback is corrected


# ===========================================================================
# Override Flag
# ===========================================================================

class TestOverrideFlagSet:
    """Overridden decisions should be marked with SafetyOverride entries."""

    def test_override_has_required_fields(self):
        """Each SafetyOverride should have timestamp, field_name, original, corrected, reason."""
        ctrl = AutonomicController(SafetyConfig(min_soc_pct=15.0))
        decision = _make_decision(battery_kw=5.0, soc_pct=10.0)
        state = _make_state(battery_soc_pct=10.0)

        _, overrides = ctrl.enforce(decision, state)
        assert len(overrides) >= 1

        o = overrides[0]
        assert isinstance(o.timestamp, float)
        assert isinstance(o.field_name, str)
        assert isinstance(o.original_value, float)
        assert isinstance(o.corrected_value, float)
        assert isinstance(o.reason, str)
        assert len(o.reason) > 0

    def test_override_records_original_value(self):
        """Override should capture the original value before correction."""
        ctrl = AutonomicController(SafetyConfig(min_soc_pct=15.0))
        decision = _make_decision(battery_kw=4.5, soc_pct=10.0)
        state = _make_state(battery_soc_pct=10.0)

        _, overrides = ctrl.enforce(decision, state)
        battery_override = [o for o in overrides if o.field_name == "battery_kw"][0]
        assert battery_override.original_value == 4.5
        assert battery_override.corrected_value == 0.0

    def test_recent_overrides_returns_history(self):
        """recent_overrides() should return a list of override dicts."""
        ctrl = AutonomicController(SafetyConfig(min_soc_pct=15.0))
        decision = _make_decision(battery_kw=5.0, soc_pct=10.0)
        state = _make_state(battery_soc_pct=10.0)

        ctrl.enforce(decision, state)
        history = ctrl.recent_overrides(limit=10)
        assert len(history) >= 1
        assert "field" in history[0]
        assert "reason" in history[0]

    def test_multiple_overrides_accumulate(self):
        """Multiple enforce calls should accumulate overrides in history."""
        ctrl = AutonomicController(SafetyConfig(min_soc_pct=15.0, max_soc_pct=98.0))

        # First: SOC floor violation
        d1 = _make_decision(battery_kw=5.0, soc_pct=10.0)
        s1 = _make_state(battery_soc_pct=10.0)
        ctrl.enforce(d1, s1)

        # Second: SOC ceiling violation
        d2 = _make_decision(battery_kw=-3.0, soc_pct=99.0)
        s2 = _make_state(battery_soc_pct=99.0)
        ctrl.enforce(d2, s2)

        history = ctrl.recent_overrides(limit=50)
        assert len(history) >= 2
