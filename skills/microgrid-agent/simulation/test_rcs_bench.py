"""Tests for the RCS controller + bench infrastructure on microgrid."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation import rcs_bench
from simulation.controllers import DispatchAction, RuleBasedController
from simulation.perturbations import (
    PerturbationInjector,
    cloud_burst_perturbation,
    standard_perturbation_battery,
)
from simulation.rcs_controller import (
    RCSController,
)
from simulation.rcs_lyapunov import (
    fit_lambda,
    v0,
)
from simulation.scenario import INIRIDA, ScenarioEngine


# ---------------------------------------------------------------------------
# RCSController integration
# ---------------------------------------------------------------------------
def test_rcs_controller_imports_cleanly():
    ctrl = RCSController(level=2, site=INIRIDA)
    assert ctrl.name() in ("rcs-flat", "rcs-+autonomic", "rcs-+meta", "rcs-full")


def test_rcs_controller_levels_named_correctly():
    assert RCSController(level=0, site=INIRIDA).name() == "rcs-flat"
    assert RCSController(level=1, site=INIRIDA).name() == "rcs-+autonomic"
    assert RCSController(level=2, site=INIRIDA).name() == "rcs-+meta"
    assert RCSController(level=3, site=INIRIDA).name() == "rcs-full"


def test_rcs_controller_level0_is_pure_passthrough(tmp_path):
    """level=0 should produce identical dispatch to the bare base controller."""
    site = rcs_bench.TEST_VILLAGE
    scen1 = ScenarioEngine(site, seed=42)
    scen2 = ScenarioEngine(site, seed=42)

    base = RuleBasedController()
    base.reset()
    rcs = RCSController(level=0, site=site, base=RuleBasedController())
    rcs.reset()

    for _ in range(24):
        s1 = next(iter(scen1))
        s2 = next(iter(scen2))
        a_base = base.dispatch(s1)
        a_rcs = rcs.dispatch(s2)
        # diesel and battery dispatch identical
        assert abs(a_base.diesel_kw - a_rcs.diesel_kw) < 1e-9
        assert abs(a_base.battery_discharge_kw - a_rcs.battery_discharge_kw) < 1e-9
        scen1.apply_dispatch(a_base.diesel_kw,
                              a_base.solar_to_battery_kw - a_base.battery_discharge_kw)
        scen2.apply_dispatch(a_rcs.diesel_kw,
                              a_rcs.solar_to_battery_kw - a_rcs.battery_discharge_kw)


def test_rcs_controller_emits_dispatch_events():
    ctrl = RCSController(level=1, site=INIRIDA)
    scen = ScenarioEngine(INIRIDA, seed=42)
    for _ in range(10):
        state = next(iter(scen))
        ctrl.dispatch(state)
        scen.apply_dispatch(0.0, 0.0)
    trace = ctrl.trace()
    assert any(ev.get("kind") == "dispatch" for ev in trace), \
        "RCSController.trace() must include 'dispatch' events"


def test_rcs_controller_invalid_level_rejected():
    with pytest.raises(ValueError):
        RCSController(level=5, site=INIRIDA)


# ---------------------------------------------------------------------------
# Lyapunov functions
# ---------------------------------------------------------------------------
class _FakeState:
    def __init__(self, soc=50.0, load=10.0):
        self.battery_soc_pct = soc
        self.load_demand_kw = load


def test_v0_zero_at_setpoint():
    """V_0 should be 0 when SOC is at setpoint and no load shed."""
    site = rcs_bench.TEST_VILLAGE
    state = _FakeState(soc=50.0, load=10.0)
    action = DispatchAction(load_shed_kw=0.0)
    assert v0(state, action, site, soc_setpoint=50.0) < 1e-9


def test_v0_increases_with_deviation():
    site = rcs_bench.TEST_VILLAGE
    s_close = _FakeState(soc=45.0)
    s_far = _FakeState(soc=20.0)
    a = DispatchAction(load_shed_kw=0.0)
    assert v0(s_close, a, site, soc_setpoint=50.0) < v0(s_far, a, site, soc_setpoint=50.0)


def test_fit_lambda_handles_constant_input():
    """Constant V over time → should not crash; returns 0 or nan deterministically."""
    lam, std = fit_lambda([0.0, 1.0, 2.0], [0.5, 0.5, 0.5])
    # Either zero slope or nan — both are acceptable for a degenerate case
    assert lam == 0.0 or (lam != lam)  # NaN check via lam != lam


def test_fit_lambda_recovers_known_decay():
    """Synthetic V(t) = exp(-0.5 t) → λ̂ ≈ 0.5."""
    import math
    times = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    vs = [math.exp(-0.5 * t) for t in times]
    lam, std = fit_lambda(times, vs)
    assert abs(lam - 0.5) < 0.05


# ---------------------------------------------------------------------------
# Perturbations
# ---------------------------------------------------------------------------
def test_cloud_burst_reduces_solar():
    site = rcs_bench.TEST_VILLAGE
    scen = ScenarioEngine(site, seed=42)
    injector = PerturbationInjector(
        scen, [cloud_burst_perturbation(start_hour=10, duration_hours=1, amplitude=0.9)],
    )
    states = []
    for s in injector:
        states.append(s)
        if s.hour >= 12:
            break
    # Hour 10 should have reduced solar; hour 11 should be normal again
    s10 = next(s for s in states if s.hour == 10)
    s11 = next(s for s in states if s.hour == 11)
    # solar_available_kw at hour 10 should be much smaller than hour 11 (assuming both daytime)
    if s11.solar_available_kw > 1.0:
        assert s10.solar_available_kw < s11.solar_available_kw


def test_perturbation_active_window():
    site = rcs_bench.TEST_VILLAGE
    scen = ScenarioEngine(site, seed=42)
    event = cloud_burst_perturbation(start_hour=240, duration_hours=2, amplitude=0.5)
    injector = PerturbationInjector(scen, [event])
    assert injector.perturbation_active(239) is None
    assert injector.perturbation_active(240) is not None
    assert injector.perturbation_active(241) is not None
    assert injector.perturbation_active(242) is None  # half-open window


def test_standard_perturbation_battery_4_events():
    events = standard_perturbation_battery()
    assert len(events) == 4
    kinds = {e.kind for e in events}
    assert kinds == {"cloud_burst", "demand_spike", "diesel_outage", "battery_fault"}


# ---------------------------------------------------------------------------
# Bench runner integration
# ---------------------------------------------------------------------------
def test_run_condition_produces_metrics():
    site = rcs_bench.TEST_VILLAGE
    result = rcs_bench.run_condition(site, condition="flat", seed=42, hours=24)
    assert result.condition == "flat"
    assert result.hours_simulated == 24
    assert result.metrics.controller_name.startswith("rcs-flat")
    # Should have V_0 trajectory
    assert len(result.v0_trajectory) == 24
    assert all(v >= 0 for _, v in result.v0_trajectory)


def test_run_condition_unknown_rejected():
    with pytest.raises(ValueError):
        rcs_bench.run_condition(rcs_bench.TEST_VILLAGE, "garbage", seed=42, hours=10)


def test_aggregate_per_condition_handles_multiple_seeds():
    site = rcs_bench.TEST_VILLAGE
    rs = [
        rcs_bench.run_condition(site, "flat", seed=42, hours=24),
        rcs_bench.run_condition(site, "flat", seed=43, hours=24),
        rcs_bench.run_condition(site, "+autonomic", seed=42, hours=24),
    ]
    agg = rcs_bench.aggregate_per_condition(rs)
    assert "flat" in agg and "+autonomic" in agg
    assert agg["flat"]["n_seeds"] == 2
    assert agg["+autonomic"]["n_seeds"] == 1
    assert "diesel_liters" in agg["flat"]
    assert "mean" in agg["flat"]["diesel_liters"]


def test_test_village_produces_nonzero_diesel():
    """TEST_VILLAGE is sized so diesel actually fires (unlike Inirida default)."""
    result = rcs_bench.run_condition(
        rcs_bench.TEST_VILLAGE, "flat", seed=42, hours=168,
    )
    assert result.metrics.diesel_liters_consumed > 0, \
        "TEST_VILLAGE should produce nonzero diesel — otherwise simulation isn't exercising the controller"
    assert result.metrics.total_unserved_kwh < result.metrics.total_load_kwh, \
        "should serve at least some load"


def test_write_report_creates_json(tmp_path):
    out = tmp_path / "bench.json"
    rcs_bench.write_report(
        aggregate={"flat": {"n_seeds": 1, "diesel_liters": {"mean": 100, "std": 0}}},
        perturbation_results={},
        out_path=out,
    )
    assert out.exists()
    data = json.loads(out.read_text())
    assert "per_condition_aggregate" in data
    assert "paper_lambda_0_target" in data
    assert abs(data["paper_lambda_0_target"] - 1.4554) < 1e-3
