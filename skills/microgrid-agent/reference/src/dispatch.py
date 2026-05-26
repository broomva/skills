"""LP dispatch optimizer for microgrid energy management.

Minimizes diesel consumption + unserved energy subject to physical constraints.
Falls back to rule-based priority dispatch if LP fails.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog, OptimizeResult

log = logging.getLogger(__name__)


@dataclass
class DispatchDecision:
    solar_kw: float  # solar output to use
    battery_kw: float  # positive = discharge, negative = charge
    diesel_kw: float  # diesel generator output
    curtailed_kw: float  # excess solar curtailed
    unserved_kw: float  # demand not met
    soc_pct: float  # battery state of charge after dispatch
    timestamp: float = field(default_factory=time.time)
    method: str = "lp"  # "lp" or "rules"

    def to_dict(self) -> dict:
        return {
            "solar_kw": round(self.solar_kw, 3),
            "battery_kw": round(self.battery_kw, 3),
            "diesel_kw": round(self.diesel_kw, 3),
            "curtailed_kw": round(self.curtailed_kw, 3),
            "unserved_kw": round(self.unserved_kw, 3),
            "soc_pct": round(self.soc_pct, 2),
            "method": self.method,
            "timestamp": self.timestamp,
        }


@dataclass
class MicrogridState:
    solar_available_kw: float
    demand_kw: float
    battery_soc_pct: float  # 0-100
    battery_capacity_kwh: float
    battery_max_charge_kw: float
    battery_max_discharge_kw: float
    diesel_max_kw: float
    diesel_min_kw: float  # min run power when on
    diesel_running: bool
    priority_loads_kw: float  # critical loads that must be served first


@dataclass
class DispatchConfig:
    """Tuning parameters for the optimizer."""
    min_soc_pct: float = 20.0
    max_soc_pct: float = 95.0
    diesel_cost_per_kwh: float = 0.35  # USD
    unserved_cost_per_kwh: float = 5.0  # very high penalty
    curtailment_cost: float = 0.01  # small cost to prefer using solar
    battery_cycle_cost: float = 0.02  # battery degradation cost
    diesel_ramp_limit_kw_per_s: float = 1.0
    dispatch_interval_s: float = 5.0


class Dispatcher:
    """Solves the single-step dispatch problem via LP."""

    def __init__(self, config: DispatchConfig | None = None):
        self.config = config or DispatchConfig()
        self._last_diesel_kw: float = 0.0

    def dispatch(self, state: MicrogridState) -> DispatchDecision:
        try:
            return self._lp_dispatch(state)
        except Exception as e:
            log.warning("LP dispatch failed (%s), using rule-based fallback", e)
            return self._rule_dispatch(state)

    def _lp_dispatch(self, state: MicrogridState) -> DispatchDecision:
        """Formulate and solve the dispatch LP.

        Decision variables (all >= 0):
          x[0] = solar_used_kw
          x[1] = battery_discharge_kw
          x[2] = battery_charge_kw
          x[3] = diesel_kw
          x[4] = curtailed_kw
          x[5] = unserved_kw
        """
        cfg = self.config
        dt = cfg.dispatch_interval_s / 3600.0  # hours

        # SOC bounds in kWh
        soc_kwh = state.battery_soc_pct / 100.0 * state.battery_capacity_kwh
        min_soc_kwh = cfg.min_soc_pct / 100.0 * state.battery_capacity_kwh
        max_soc_kwh = cfg.max_soc_pct / 100.0 * state.battery_capacity_kwh

        # Max discharge/charge this interval given SOC limits
        max_discharge = min(
            state.battery_max_discharge_kw,
            (soc_kwh - min_soc_kwh) / dt if dt > 0 else 0,
        )
        max_charge = min(
            state.battery_max_charge_kw,
            (max_soc_kwh - soc_kwh) / dt if dt > 0 else 0,
        )

        # Diesel ramp limit
        ramp_limit = cfg.diesel_ramp_limit_kw_per_s * cfg.dispatch_interval_s
        diesel_max = min(state.diesel_max_kw, self._last_diesel_kw + ramp_limit)
        diesel_min_if_on = state.diesel_min_kw

        # Objective: minimize cost
        # c = [solar_cost, discharge_cost, charge_cost, diesel_cost, curtail_cost, unserved_cost]
        c = np.array([
            0.0,  # solar is free
            cfg.battery_cycle_cost,  # discharge
            cfg.battery_cycle_cost,  # charge
            cfg.diesel_cost_per_kwh * dt,  # diesel
            cfg.curtailment_cost,  # curtailment
            cfg.unserved_cost_per_kwh * dt,  # unserved
        ])

        # Equality constraint: solar_used + discharge - charge + diesel + unserved - curtail = demand
        # Rearranged: solar_used + discharge - charge + diesel - curtail + unserved = demand
        # But linprog needs Ax = b with all vars >= 0, so split:
        # solar_used + discharge + diesel + unserved = demand + charge + curtail
        # => solar_used + discharge - charge + diesel - curtail + unserved = demand
        A_eq = np.array([[1.0, 1.0, -1.0, 1.0, -1.0, 1.0]])
        b_eq = np.array([state.demand_kw])

        # Solar + curtailed = available
        # solar_used + curtailed <= solar_available
        A_ub_rows = []
        b_ub_rows = []

        # solar_used + curtailed <= solar_available
        A_ub_rows.append([1.0, 0, 0, 0, 1.0, 0])
        b_ub_rows.append(state.solar_available_kw)

        A_ub = np.array(A_ub_rows) if A_ub_rows else None
        b_ub = np.array(b_ub_rows) if b_ub_rows else None

        bounds = [
            (0, state.solar_available_kw),  # solar_used
            (0, max(0, max_discharge)),  # discharge
            (0, max(0, max_charge)),  # charge
            (0, max(0, diesel_max)),  # diesel
            (0, state.solar_available_kw),  # curtailed
            (0, state.demand_kw),  # unserved
        ]

        result: OptimizeResult = linprog(
            c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
            bounds=bounds, method="highs",
        )

        if not result.success:
            raise RuntimeError(f"LP infeasible: {result.message}")

        x = result.x
        solar_used = x[0]
        discharge = x[1]
        charge = x[2]
        diesel = x[3]
        curtailed = x[4]
        unserved = x[5]

        # Update SOC
        new_soc_kwh = soc_kwh - discharge * dt + charge * dt
        new_soc_pct = (new_soc_kwh / state.battery_capacity_kwh) * 100.0

        self._last_diesel_kw = diesel

        return DispatchDecision(
            solar_kw=solar_used,
            battery_kw=discharge - charge,
            diesel_kw=diesel,
            curtailed_kw=curtailed,
            unserved_kw=unserved,
            soc_pct=new_soc_pct,
            method="lp",
        )

    def _rule_dispatch(self, state: MicrogridState) -> DispatchDecision:
        """Priority-based fallback: solar -> battery -> diesel."""
        cfg = self.config
        dt = cfg.dispatch_interval_s / 3600.0
        demand = state.demand_kw
        remaining = demand

        soc_kwh = state.battery_soc_pct / 100.0 * state.battery_capacity_kwh
        min_soc_kwh = cfg.min_soc_pct / 100.0 * state.battery_capacity_kwh
        max_soc_kwh = cfg.max_soc_pct / 100.0 * state.battery_capacity_kwh

        # 1. Use solar first
        solar_used = min(state.solar_available_kw, remaining)
        remaining -= solar_used

        # 2. Discharge battery
        max_discharge = min(
            state.battery_max_discharge_kw,
            (soc_kwh - min_soc_kwh) / dt if dt > 0 else 0,
        )
        discharge = min(max(0, max_discharge), remaining)
        remaining -= discharge

        # 3. Start diesel if still needed
        diesel = 0.0
        if remaining > 0:
            diesel = min(remaining, state.diesel_max_kw)
            remaining -= diesel

        unserved = max(0, remaining)

        # Charge battery with excess solar
        excess_solar = state.solar_available_kw - solar_used
        max_charge = min(
            state.battery_max_charge_kw,
            (max_soc_kwh - soc_kwh) / dt if dt > 0 else 0,
        )
        charge = min(excess_solar, max(0, max_charge))
        curtailed = excess_solar - charge

        new_soc_kwh = soc_kwh - discharge * dt + charge * dt
        new_soc_pct = (new_soc_kwh / state.battery_capacity_kwh) * 100.0

        self._last_diesel_kw = diesel

        return DispatchDecision(
            solar_kw=solar_used,
            battery_kw=discharge - charge,
            diesel_kw=diesel,
            curtailed_kw=curtailed,
            unserved_kw=unserved,
            soc_pct=new_soc_pct,
            method="rules",
        )
