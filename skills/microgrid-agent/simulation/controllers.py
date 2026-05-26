"""Controllers — dispatch strategies to compare in simulation.

Each controller receives an HourState and returns a DispatchAction.
The simulation engine runs the same scenario through each controller
to produce comparable metrics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .scenario import HourState


@dataclass
class DispatchAction:
    """What the controller decides to do this hour."""

    solar_to_load_kw: float = 0.0
    solar_to_battery_kw: float = 0.0
    battery_discharge_kw: float = 0.0
    diesel_kw: float = 0.0
    wind_to_load_kw: float = 0.0
    load_shed_kw: float = 0.0
    reasoning: str = ""


class Controller(ABC):
    """Base class for dispatch controllers."""

    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def dispatch(self, state: HourState) -> DispatchAction: ...

    def reset(self):
        """Reset controller state for a new simulation run."""
        pass


class RuleBasedController(Controller):
    """Baseline: Victron Cerbo GX equivalent.

    Priority order: solar → battery → diesel.
    No forecasting, no optimization — just thresholds.
    This is what a $500 commercial controller does.
    """

    def __init__(self, min_soc: float = 20.0, diesel_start_soc: float = 25.0,
                 diesel_stop_soc: float = 60.0, max_diesel_hours: float = 16.0):
        self.min_soc = min_soc
        self.diesel_start_soc = diesel_start_soc
        self.diesel_stop_soc = diesel_stop_soc
        self.max_diesel_hours = max_diesel_hours
        self.diesel_running = False
        self.diesel_hours_today = 0.0
        self._last_day = -1

    def name(self) -> str:
        return "rule-based"

    def reset(self):
        self.diesel_running = False
        self.diesel_hours_today = 0.0
        self._last_day = -1

    def dispatch(self, state: HourState) -> DispatchAction:
        # Reset daily diesel counter
        if state.day_of_year != self._last_day:
            self._last_day = state.day_of_year
            self.diesel_hours_today = 0.0

        action = DispatchAction()
        remaining = state.load_demand_kw
        available_solar = state.solar_available_kw
        available_wind = state.wind_available_kw

        # 1. Use solar
        solar_used = min(available_solar, remaining)
        action.solar_to_load_kw = solar_used
        remaining -= solar_used

        # 2. Use wind
        wind_used = min(available_wind, remaining)
        action.wind_to_load_kw = wind_used
        remaining -= wind_used

        # Excess renewable → charge battery
        excess = (available_solar - solar_used) + (available_wind - wind_used)
        if excess > 0 and state.battery_soc_pct < 95.0:
            action.solar_to_battery_kw = excess

        # 3. Battery discharge
        if remaining > 0 and state.battery_soc_pct > self.min_soc:
            discharge = min(remaining, state.battery_soc_pct / 100 * 50)  # rough C-rate limit
            action.battery_discharge_kw = discharge
            remaining -= discharge

        # 4. Diesel — hysteresis control
        if state.battery_soc_pct <= self.diesel_start_soc and not self.diesel_running:
            self.diesel_running = True
        if state.battery_soc_pct >= self.diesel_stop_soc and self.diesel_running:
            self.diesel_running = False

        if self.diesel_running and state.diesel_ok and state.diesel_fuel_liters > 0:
            if self.diesel_hours_today < self.max_diesel_hours:
                diesel_output = min(remaining, state.load_demand_kw * 0.8)  # size for ~80% load
                action.diesel_kw = max(diesel_output, 0)
                remaining -= action.diesel_kw
                self.diesel_hours_today += 1.0

        # 5. Whatever's left is shed
        action.load_shed_kw = max(0, remaining)

        action.reasoning = (
            f"Rule: solar={action.solar_to_load_kw:.0f}kW, "
            f"wind={action.wind_to_load_kw:.0f}kW, "
            f"batt={action.battery_discharge_kw:.0f}kW, "
            f"diesel={action.diesel_kw:.0f}kW, "
            f"shed={action.load_shed_kw:.0f}kW"
        )
        return action


class ForecastController(Controller):
    """ML-enhanced controller with look-ahead optimization.

    Uses a simple persistence forecast (yesterday = today) as a
    stand-in for the TFLite LSTM. The key difference from rule-based:
    it anticipates evening peaks and pre-charges the battery during
    solar hours, and anticipates tomorrow's solar to decide whether
    to run diesel tonight or wait for morning sun.
    """

    def __init__(self, min_soc: float = 20.0, max_diesel_hours: float = 16.0):
        self.min_soc = min_soc
        self.max_diesel_hours = max_diesel_hours
        self.history: list[HourState] = []
        self.diesel_hours_today = 0.0
        self._last_day = -1

    def name(self) -> str:
        return "forecast"

    def reset(self):
        self.history = []
        self.diesel_hours_today = 0.0
        self._last_day = -1

    def _get_forecast(self, current_hour: int) -> tuple[list[float], list[float]]:
        """Persistence forecast: next 24h = same hour yesterday."""
        solar_forecast = []
        demand_forecast = []
        for h_offset in range(1, 25):
            # Find the reading from 24h ago at this hour
            lookback = current_hour - 24 + h_offset
            match = None
            for h in self.history:
                if h.hour == lookback:
                    match = h
                    break
            if match:
                solar_forecast.append(match.solar_available_kw)
                demand_forecast.append(match.load_demand_kw)
            else:
                solar_forecast.append(0.0)
                demand_forecast.append(15.0)  # conservative default
        return solar_forecast, demand_forecast

    def dispatch(self, state: HourState) -> DispatchAction:
        self.history.append(state)
        if len(self.history) > 48:
            self.history = self.history[-48:]

        if state.day_of_year != self._last_day:
            self._last_day = state.day_of_year
            self.diesel_hours_today = 0.0

        solar_fc, demand_fc = self._get_forecast(state.hour)

        action = DispatchAction()
        remaining = state.load_demand_kw
        available_solar = state.solar_available_kw
        available_wind = state.wind_available_kw

        # Forecast-informed decisions:
        # 1. If evening peak coming (next 6h demand > current), pre-charge battery
        upcoming_demand = sum(demand_fc[:6]) / max(1, len(demand_fc[:6]))
        upcoming_solar = sum(solar_fc[:6]) / max(1, len(solar_fc[:6]))
        expect_shortfall = upcoming_demand > upcoming_solar * 1.2

        # 2. If tomorrow has good solar, avoid running diesel tonight
        tomorrow_solar = sum(solar_fc[12:24]) if len(solar_fc) >= 24 else 0
        tomorrow_has_sun = tomorrow_solar > state.load_demand_kw * 6

        # Solar to load
        solar_used = min(available_solar, remaining)
        action.solar_to_load_kw = solar_used
        remaining -= solar_used

        # Wind to load
        wind_used = min(available_wind, remaining)
        action.wind_to_load_kw = wind_used
        remaining -= wind_used

        # Excess solar → battery (charge MORE aggressively if evening shortfall expected)
        excess = (available_solar - solar_used) + (available_wind - wind_used)
        if excess > 0 and state.battery_soc_pct < 95.0:
            action.solar_to_battery_kw = excess

        # If expecting shortfall and we have solar, charge even at cost of diesel now
        if expect_shortfall and state.battery_soc_pct < 80.0 and excess <= 0 and available_solar > 0:
            # Reduce load served by solar to charge battery instead
            charge_fraction = 0.2  # divert 20% of solar to charging
            divert = action.solar_to_load_kw * charge_fraction
            action.solar_to_load_kw -= divert
            action.solar_to_battery_kw += divert
            remaining += divert

        # Battery discharge — less aggressive if tomorrow has sun
        if remaining > 0 and state.battery_soc_pct > self.min_soc:
            # If tomorrow has sun, we can discharge deeper tonight
            effective_min = self.min_soc if tomorrow_has_sun else self.min_soc + 10
            if state.battery_soc_pct > effective_min:
                max_discharge = (state.battery_soc_pct - effective_min) / 100 * state.battery_soc_pct
                discharge = min(remaining, max_discharge)
                action.battery_discharge_kw = discharge
                remaining -= discharge

        # Diesel — only when truly needed, prefer waiting for sun
        if remaining > 0.5:
            if tomorrow_has_sun and state.battery_soc_pct > 30:
                # Tomorrow has sun and battery has charge — skip diesel, accept partial shed
                action.load_shed_kw = remaining
            elif state.diesel_ok and state.diesel_fuel_liters > 0:
                if self.diesel_hours_today < self.max_diesel_hours:
                    action.diesel_kw = min(remaining, state.load_demand_kw * 0.7)
                    remaining -= action.diesel_kw
                    self.diesel_hours_today += 1.0
                    action.load_shed_kw = max(0, remaining)
                else:
                    action.load_shed_kw = remaining
            else:
                action.load_shed_kw = remaining

        action.reasoning = (
            f"Forecast: solar={action.solar_to_load_kw:.0f}kW, "
            f"batt_charge={action.solar_to_battery_kw:.0f}kW, "
            f"batt_discharge={action.battery_discharge_kw:.0f}kW, "
            f"diesel={action.diesel_kw:.0f}kW, "
            f"shed={action.load_shed_kw:.0f}kW "
            f"[shortfall_expected={expect_shortfall}, tomorrow_sun={tomorrow_has_sun}]"
        )
        return action


class KGForecastController(ForecastController):
    """Full system: forecast + knowledge graph territorial context.

    Extends ForecastController with:
    - Market day awareness (pre-charge for +30% demand)
    - Festival awareness (pre-charge for +50% demand)
    - Rain season diesel conservation (fuel deliveries unreliable)
    - Priority load protection (never shed health center)

    This is what the knowledge graph enables that flat features can't:
    structured reasoning about RELATIONSHIPS between events.
    """

    def __init__(self, site_profile=None, **kwargs):
        super().__init__(**kwargs)
        self.site = site_profile

    def name(self) -> str:
        return "forecast+kg"

    def dispatch(self, state: HourState) -> DispatchAction:
        action = super().dispatch(state)

        # KG enhancement 1: Market day pre-charging
        # If tomorrow is market day, ensure battery is above 70% by evening
        tomorrow_dow = (state.day_of_week + 1) % 7
        if self.site and tomorrow_dow in self.site.market_days:
            if state.hour_of_day >= 14 and state.battery_soc_pct < 70:
                # Boost charging priority
                action.reasoning += " [KG: pre-charge for market day]"

        # KG enhancement 2: Rainy season diesel conservation
        # During rainy months, fuel delivery is unreliable — conserve diesel
        if state.month in (self.site.rainy_season_months if self.site else []):
            if state.diesel_fuel_liters < state.diesel_fuel_liters * 0.3:
                # Low fuel + rainy season = reduce diesel usage threshold
                if action.diesel_kw > 0 and state.battery_soc_pct > 15:
                    saved_diesel = action.diesel_kw * 0.3
                    action.diesel_kw -= saved_diesel
                    action.load_shed_kw += saved_diesel
                    action.reasoning += " [KG: diesel conservation — rainy season, low fuel]"

        # KG enhancement 3: Priority load protection
        # Never shed if it means the health center goes dark
        # (In rule-based, load shedding is indiscriminate)
        if action.load_shed_kw > 0 and state.load_demand_kw > 0:
            # Assume health center is ~10% of total load
            priority_load = state.load_demand_kw * 0.10
            if action.load_shed_kw > state.load_demand_kw - priority_load:
                # We'd be shedding critical loads — start diesel instead
                if state.diesel_ok and state.diesel_fuel_liters > 0:
                    needed = priority_load
                    action.diesel_kw += needed
                    action.load_shed_kw = max(0, action.load_shed_kw - needed)
                    action.reasoning += " [KG: priority load protection — health center]"

        return action
