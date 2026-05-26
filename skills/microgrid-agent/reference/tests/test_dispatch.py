"""
Tests for the dispatch optimizer.

Covers:
- Rule-based fallback when no ML model is available
- LP optimization with simple solar+battery+diesel scenario
- Safety constraint enforcement (SOC limits)
"""

import pytest
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Inline dispatch logic for testing
# (In production, this lives in src/dispatch.py)
# ---------------------------------------------------------------------------

@dataclass
class GridState:
    """Current state of the microgrid."""
    solar_kw: float = 0.0
    load_kw: float = 0.0
    soc_pct: float = 50.0
    battery_capacity_kwh: float = 120.0
    battery_max_charge_kw: float = 60.0
    battery_max_discharge_kw: float = 60.0
    diesel_capacity_kw: float = 30.0
    diesel_available: bool = True

    # Autonomic set-points
    min_soc_pct: float = 15.0
    max_soc_pct: float = 95.0
    diesel_start_soc: float = 20.0
    diesel_stop_soc: float = 60.0


@dataclass
class DispatchAction:
    """Dispatch decision output."""
    battery_kw: float = 0.0         # positive = charging, negative = discharging
    diesel_kw: float = 0.0          # generator output (>= 0)
    curtail_solar_kw: float = 0.0   # solar curtailed (>= 0)
    shed_loads: list = field(default_factory=list)  # list of load names to shed
    reasoning: str = ""


def rule_based_dispatch(state: GridState) -> DispatchAction:
    """
    Simple rule-based dispatch fallback.
    Used when no ML model is available.
    """
    action = DispatchAction()
    net_power = state.solar_kw - state.load_kw  # positive = surplus

    if net_power >= 0:
        # Surplus solar: charge battery
        charge_kw = min(net_power, state.battery_max_charge_kw)

        # Don't charge above max SOC
        if state.soc_pct >= state.max_soc_pct:
            charge_kw = 0.0
            action.curtail_solar_kw = net_power
            action.reasoning = "SOC at max, curtailing solar"
        else:
            action.reasoning = f"Solar surplus {net_power:.1f}kW, charging battery at {charge_kw:.1f}kW"

        action.battery_kw = charge_kw

        # If we can't absorb all surplus, curtail
        remaining_surplus = net_power - charge_kw
        if remaining_surplus > 0:
            action.curtail_solar_kw = remaining_surplus

    else:
        # Deficit: discharge battery
        deficit_kw = abs(net_power)
        discharge_kw = min(deficit_kw, state.battery_max_discharge_kw)

        # Don't discharge below min SOC
        if state.soc_pct <= state.min_soc_pct:
            discharge_kw = 0.0
            action.reasoning = "SOC at minimum, cannot discharge battery"
        else:
            action.reasoning = f"Deficit {deficit_kw:.1f}kW, discharging battery at {discharge_kw:.1f}kW"

        action.battery_kw = -discharge_kw
        remaining_deficit = deficit_kw - discharge_kw

        # Start diesel if SOC is low or battery can't cover deficit
        if remaining_deficit > 0 or state.soc_pct <= state.diesel_start_soc:
            if state.diesel_available:
                action.diesel_kw = min(remaining_deficit if remaining_deficit > 0 else state.diesel_capacity_kw * 0.5,
                                       state.diesel_capacity_kw)
                action.reasoning += f"; diesel at {action.diesel_kw:.1f}kW"

        # If still not enough, shed loads
        total_supply = state.solar_kw + discharge_kw + action.diesel_kw
        if total_supply < state.load_kw:
            action.shed_loads = ["community_center", "residential_cluster_a"]
            action.reasoning += "; shedding non-critical loads"

    return action


def lp_dispatch(state: GridState) -> Optional[DispatchAction]:
    """
    Linear programming based dispatch optimization.
    Minimizes diesel usage while meeting load and respecting SOC constraints.
    Returns None if scipy is not available.
    """
    try:
        from scipy.optimize import linprog
    except ImportError:
        return None

    # Decision variables: [battery_discharge, diesel_output, solar_curtail]
    # All >= 0

    # Objective: minimize diesel + small penalty for curtailment
    c = [0.0, 1.0, 0.1]  # minimize diesel, small cost for curtailment

    net_demand = state.load_kw - state.solar_kw

    # Power balance: battery_discharge + diesel - solar_curtail = net_demand
    # (if net_demand < 0, battery_discharge can be negative = charging)
    A_eq = [[1.0, 1.0, -1.0]]
    b_eq = [max(net_demand, 0.0)]  # only balance the deficit

    # Bounds
    battery_max_discharge = state.battery_max_discharge_kw
    if state.soc_pct <= state.min_soc_pct:
        battery_max_discharge = 0.0

    bounds = [
        (0, battery_max_discharge),           # battery discharge
        (0, state.diesel_capacity_kw if state.diesel_available else 0),  # diesel
        (0, max(state.solar_kw, 0)),          # curtailment (can't curtail more than production)
    ]

    result = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method='highs')

    if not result.success:
        return None

    battery_discharge, diesel, curtail = result.x

    action = DispatchAction(
        battery_kw=-battery_discharge,  # negative = discharging
        diesel_kw=diesel,
        curtail_solar_kw=curtail,
        reasoning=f"LP optimized: battery={-battery_discharge:.1f}kW, diesel={diesel:.1f}kW"
    )

    return action


# ===========================================================================
# Tests
# ===========================================================================

class TestRuleBasedDispatch:
    """Test the rule-based fallback dispatch."""

    def test_solar_surplus_charges_battery(self):
        """When solar exceeds load, battery should charge."""
        state = GridState(solar_kw=40.0, load_kw=20.0, soc_pct=50.0)
        action = rule_based_dispatch(state)

        assert action.battery_kw > 0, "Battery should be charging"
        assert action.battery_kw == 20.0, "Should charge with full surplus"
        assert action.diesel_kw == 0.0, "Diesel should be off"
        assert len(action.shed_loads) == 0, "No loads should be shed"

    def test_solar_deficit_discharges_battery(self):
        """When load exceeds solar, battery should discharge."""
        state = GridState(solar_kw=10.0, load_kw=25.0, soc_pct=60.0)
        action = rule_based_dispatch(state)

        assert action.battery_kw < 0, "Battery should be discharging"
        assert action.battery_kw == -15.0, "Should discharge to cover deficit"
        assert action.diesel_kw == 0.0, "Diesel not needed when battery has capacity"

    def test_no_solar_night_discharge(self):
        """At night with no solar, battery covers load."""
        state = GridState(solar_kw=0.0, load_kw=15.0, soc_pct=70.0)
        action = rule_based_dispatch(state)

        assert action.battery_kw == -15.0
        assert action.diesel_kw == 0.0

    def test_diesel_starts_on_low_soc(self):
        """Diesel should start when SOC is at or below diesel_start_soc."""
        state = GridState(solar_kw=0.0, load_kw=20.0, soc_pct=20.0)
        action = rule_based_dispatch(state)

        assert action.diesel_kw > 0, "Diesel should start on low SOC"

    def test_diesel_not_available(self):
        """When diesel is unavailable, it should not be dispatched."""
        state = GridState(solar_kw=0.0, load_kw=20.0, soc_pct=20.0, diesel_available=False)
        action = rule_based_dispatch(state)

        assert action.diesel_kw == 0.0, "Diesel marked unavailable should not run"

    def test_load_shedding_when_insufficient_supply(self):
        """Loads should be shed when total supply cannot meet demand."""
        state = GridState(
            solar_kw=0.0,
            load_kw=100.0,  # Way more than battery + diesel can supply
            soc_pct=15.0,   # At minimum SOC — battery can't discharge
            diesel_available=True,
        )
        action = rule_based_dispatch(state)

        assert len(action.shed_loads) > 0, "Should shed loads when supply is insufficient"
        assert "community_center" in action.shed_loads, "Non-critical loads should be shed first"

    def test_curtail_solar_at_max_soc(self):
        """Solar should be curtailed when battery is fully charged."""
        state = GridState(solar_kw=50.0, load_kw=20.0, soc_pct=95.0)
        action = rule_based_dispatch(state)

        assert action.curtail_solar_kw > 0, "Should curtail excess solar at max SOC"
        assert action.battery_kw == 0.0, "Should not charge at max SOC"


class TestSafetyConstraints:
    """Test that safety constraints are never violated."""

    def test_soc_min_prevents_discharge(self):
        """Battery must not discharge below min SOC."""
        state = GridState(solar_kw=0.0, load_kw=20.0, soc_pct=15.0)
        action = rule_based_dispatch(state)

        assert action.battery_kw >= 0, "Must not discharge at min SOC"

    def test_soc_max_prevents_charge(self):
        """Battery must not charge above max SOC."""
        state = GridState(solar_kw=50.0, load_kw=10.0, soc_pct=95.0)
        action = rule_based_dispatch(state)

        assert action.battery_kw == 0.0, "Must not charge at max SOC"

    def test_battery_discharge_within_c_rate(self):
        """Battery discharge must not exceed max C-rate."""
        state = GridState(
            solar_kw=0.0,
            load_kw=200.0,  # Huge load
            soc_pct=80.0,
            battery_max_discharge_kw=60.0,
        )
        action = rule_based_dispatch(state)

        assert abs(action.battery_kw) <= 60.0, "Discharge must respect C-rate limit"

    def test_diesel_within_capacity(self):
        """Diesel output must not exceed rated capacity."""
        state = GridState(
            solar_kw=0.0,
            load_kw=200.0,
            soc_pct=15.0,
            diesel_capacity_kw=30.0,
        )
        action = rule_based_dispatch(state)

        assert action.diesel_kw <= 30.0, "Diesel must not exceed rated capacity"


class TestLPDispatch:
    """Test LP-based dispatch optimizer."""

    def test_lp_minimizes_diesel(self):
        """LP should prefer battery over diesel when battery is available."""
        state = GridState(solar_kw=5.0, load_kw=20.0, soc_pct=80.0)
        action = lp_dispatch(state)

        assert action is not None, "LP should return a result with scipy installed"
        # LP should use battery before diesel since diesel has higher cost
        assert action.diesel_kw < 15.0 or abs(action.battery_kw) > 0, \
            "LP should prefer battery over diesel"

    def test_lp_uses_diesel_when_battery_depleted(self):
        """LP should use diesel when battery is at min SOC."""
        state = GridState(solar_kw=0.0, load_kw=20.0, soc_pct=15.0)
        action = lp_dispatch(state)

        assert action is not None
        assert action.diesel_kw > 0, "Must use diesel when battery is depleted"
        assert action.battery_kw >= 0, "Must not discharge battery at min SOC"

    def test_lp_no_curtailment_when_load_matches(self):
        """LP should not curtail solar when it matches load."""
        state = GridState(solar_kw=20.0, load_kw=20.0, soc_pct=50.0)
        action = lp_dispatch(state)

        assert action is not None
        assert action.curtail_solar_kw == pytest.approx(0.0, abs=0.1), \
            "Should not curtail when supply matches demand"

    def test_lp_feasibility_extreme_deficit(self):
        """LP should still return a feasible solution under extreme load."""
        state = GridState(
            solar_kw=0.0,
            load_kw=80.0,
            soc_pct=50.0,
            battery_max_discharge_kw=60.0,
            diesel_capacity_kw=30.0,
        )
        action = lp_dispatch(state)

        # With 60kW battery + 30kW diesel = 90kW capacity, should be feasible
        assert action is not None, "Should find feasible solution for 80kW load"


# ===========================================================================
# Tests for src.dispatch.Dispatcher (production dispatch module)
# ===========================================================================

from src.dispatch import (
    Dispatcher,
    DispatchConfig,
    DispatchDecision as SrcDispatchDecision,
    MicrogridState,
)


def _make_state(**overrides) -> MicrogridState:
    """Build a MicrogridState with sensible defaults."""
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


class TestSrcSolarSurplusChargesBattery:
    """When solar exceeds demand, battery should charge (src.dispatch)."""

    def test_surplus_solar_charges_battery_rule_dispatch(self):
        """Rule-based dispatch with solar surplus should charge battery."""
        config = DispatchConfig(min_soc_pct=20.0, max_soc_pct=95.0)
        dispatcher = Dispatcher(config)
        state = _make_state(
            solar_available_kw=10.0,
            demand_kw=3.0,
            battery_soc_pct=50.0,
        )
        # Rule-based dispatch explicitly charges battery with excess solar
        decision = dispatcher._rule_dispatch(state)
        # battery_kw < 0 means charging in DispatchDecision
        assert decision.battery_kw < 0, \
            "Rule dispatch should charge battery with surplus solar"
        assert decision.solar_kw == pytest.approx(3.0, abs=0.1), \
            "Should use 3 kW solar to meet demand"

    def test_no_diesel_with_surplus(self):
        """No diesel needed when solar covers demand."""
        dispatcher = Dispatcher(DispatchConfig())
        state = _make_state(solar_available_kw=10.0, demand_kw=3.0, battery_soc_pct=50.0)
        decision = dispatcher.dispatch(state)
        assert decision.diesel_kw == pytest.approx(0.0, abs=0.01), \
            "Diesel should not run with solar surplus"


class TestAllSourcesExhaustedShedsLoad:
    """When all sources exhausted, there should be unserved load."""

    def test_unserved_when_sources_insufficient(self):
        """Demand exceeding all supply should produce unserved_kw > 0."""
        dispatcher = Dispatcher(DispatchConfig())
        state = _make_state(
            solar_available_kw=1.0,
            demand_kw=50.0,
            battery_soc_pct=20.0,  # at min SOC limit
            battery_max_discharge_kw=2.0,
            diesel_max_kw=3.0,
        )
        decision = dispatcher.dispatch(state)
        # Total max supply = 1 + 2 + 3 = 6 kW, demand = 50 kW
        assert decision.unserved_kw > 0, "Should have unserved load when demand >> supply"

    def test_zero_supply_all_unserved(self):
        """With zero supply, all demand should be unserved."""
        dispatcher = Dispatcher(DispatchConfig(min_soc_pct=50.0))
        state = _make_state(
            solar_available_kw=0.0,
            demand_kw=5.0,
            battery_soc_pct=50.0,  # at min SOC
            diesel_max_kw=0.0,
        )
        decision = dispatcher.dispatch(state)
        assert decision.unserved_kw == pytest.approx(5.0, abs=0.1)


class TestDispatchDecisionSerialization:
    """DispatchDecision.to_dict() produces valid serializable output."""

    def test_to_dict_keys(self):
        """to_dict should contain all expected keys."""
        d = SrcDispatchDecision(
            solar_kw=3.0, battery_kw=1.0, diesel_kw=0.0,
            curtailed_kw=0.5, unserved_kw=0.0, soc_pct=60.0,
        )
        result = d.to_dict()
        expected_keys = {"solar_kw", "battery_kw", "diesel_kw", "curtailed_kw",
                         "unserved_kw", "soc_pct", "method", "timestamp"}
        assert set(result.keys()) == expected_keys

    def test_to_dict_values_rounded(self):
        """Numeric values should be rounded for clean output."""
        d = SrcDispatchDecision(
            solar_kw=3.14159, battery_kw=-1.23456, diesel_kw=0.0,
            curtailed_kw=0.0, unserved_kw=0.0, soc_pct=50.12345,
        )
        result = d.to_dict()
        assert result["solar_kw"] == 3.142  # 3 decimal places
        assert result["soc_pct"] == 50.12  # 2 decimal places

    def test_to_dict_json_serializable(self):
        """to_dict output should be JSON serializable."""
        import json
        d = SrcDispatchDecision(
            solar_kw=3.0, battery_kw=1.0, diesel_kw=0.0,
            curtailed_kw=0.0, unserved_kw=0.0, soc_pct=60.0,
        )
        serialized = json.dumps(d.to_dict())
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["solar_kw"] == 3.0

    def test_method_field(self):
        """DispatchDecision should carry the method used (lp or rules)."""
        d_lp = SrcDispatchDecision(
            solar_kw=0, battery_kw=0, diesel_kw=0,
            curtailed_kw=0, unserved_kw=0, soc_pct=50, method="lp",
        )
        assert d_lp.to_dict()["method"] == "lp"

        d_rules = SrcDispatchDecision(
            solar_kw=0, battery_kw=0, diesel_kw=0,
            curtailed_kw=0, unserved_kw=0, soc_pct=50, method="rules",
        )
        assert d_rules.to_dict()["method"] == "rules"

    def test_rule_dispatch_fallback(self):
        """Dispatcher._rule_dispatch should work as a fallback."""
        dispatcher = Dispatcher(DispatchConfig())
        state = _make_state(solar_available_kw=5.0, demand_kw=3.0, battery_soc_pct=50.0)
        decision = dispatcher._rule_dispatch(state)
        assert decision.method == "rules"
        assert decision.solar_kw >= 0
        assert decision.unserved_kw >= 0
