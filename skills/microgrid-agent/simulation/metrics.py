"""Metrics collector and comparison report generator.

Tracks per-hour operational metrics across controller runs
and produces side-by-side comparison tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .controllers import DispatchAction
from .scenario import HourState, SiteProfile


@dataclass
class SimMetrics:
    """Accumulated metrics for one controller × one site × one year."""

    controller_name: str = ""
    site_name: str = ""

    # Energy (kWh over simulation period)
    total_load_kwh: float = 0.0
    total_solar_kwh: float = 0.0
    total_wind_kwh: float = 0.0
    total_diesel_kwh: float = 0.0
    total_battery_charge_kwh: float = 0.0
    total_battery_discharge_kwh: float = 0.0
    total_unserved_kwh: float = 0.0

    # Diesel
    diesel_liters_consumed: float = 0.0
    diesel_starts: int = 0
    diesel_runtime_hours: float = 0.0

    # Battery
    battery_cycles: float = 0.0  # equivalent full cycles
    min_soc_reached: float = 100.0
    avg_soc: float = 0.0
    _soc_sum: float = field(default=0.0, repr=False)

    # Service quality
    hours_with_shed: int = 0
    hours_without_power: int = 0  # load_shed == load_demand (total blackout)
    priority_load_uptime_hours: int = 0

    # Emissions
    co2_kg: float = 0.0

    # Counters
    _hours_counted: int = field(default=0, repr=False)
    _diesel_was_on: bool = field(default=False, repr=False)

    def record(self, state: HourState, action: DispatchAction, site: SiteProfile):
        """Record one hour of simulation results."""
        self._hours_counted += 1

        # Energy totals (1 hour timestep = kW == kWh)
        self.total_load_kwh += state.load_demand_kw
        self.total_solar_kwh += action.solar_to_load_kw + action.solar_to_battery_kw
        self.total_wind_kwh += action.wind_to_load_kw
        self.total_diesel_kwh += action.diesel_kw
        self.total_unserved_kwh += action.load_shed_kw

        if action.solar_to_battery_kw > 0:
            self.total_battery_charge_kwh += action.solar_to_battery_kw
        if action.battery_discharge_kw > 0:
            self.total_battery_discharge_kwh += action.battery_discharge_kw

        # Diesel
        if action.diesel_kw > 0:
            fuel = action.diesel_kw * site.diesel_consumption_l_per_kwh
            self.diesel_liters_consumed += fuel
            self.diesel_runtime_hours += 1.0
            self.co2_kg += fuel * 2.68  # kg CO2 per liter diesel

            if not self._diesel_was_on:
                self.diesel_starts += 1
                self._diesel_was_on = True
        else:
            self._diesel_was_on = False

        # Battery cycles (simplified: total throughput / 2 / capacity)
        throughput = action.solar_to_battery_kw + action.battery_discharge_kw
        self.battery_cycles += throughput / (2 * site.battery_capacity_kwh) if site.battery_capacity_kwh > 0 else 0

        # SOC tracking
        self.min_soc_reached = min(self.min_soc_reached, state.battery_soc_pct)
        self._soc_sum += state.battery_soc_pct

        # Service quality
        if action.load_shed_kw > 0.1:
            self.hours_with_shed += 1
        if action.load_shed_kw >= state.load_demand_kw * 0.95:
            self.hours_without_power += 1

        # Priority load uptime (assume 10% of load is priority)
        priority_threshold = state.load_demand_kw * 0.10
        served = state.load_demand_kw - action.load_shed_kw
        if served >= priority_threshold:
            self.priority_load_uptime_hours += 1

    def finalize(self):
        """Compute derived metrics after simulation completes."""
        if self._hours_counted > 0:
            self.avg_soc = self._soc_sum / self._hours_counted

    @property
    def renewable_fraction(self) -> float:
        total_gen = self.total_solar_kwh + self.total_wind_kwh + self.total_diesel_kwh
        if total_gen == 0:
            return 0.0
        return (self.total_solar_kwh + self.total_wind_kwh) / total_gen

    @property
    def service_availability(self) -> float:
        if self._hours_counted == 0:
            return 0.0
        return (self._hours_counted - self.hours_with_shed) / self._hours_counted

    @property
    def diesel_cost_cop(self) -> float:
        """Diesel cost in Colombian pesos (COP ~3,000/liter in ZNI)."""
        return self.diesel_liters_consumed * 3000.0


def compare(results: dict[str, SimMetrics]) -> str:
    """Generate a comparison table from multiple controller results.

    Args:
        results: {controller_name: SimMetrics}

    Returns:
        Formatted comparison table as a string.
    """
    if not results:
        return "No results to compare."

    site_name = next(iter(results.values())).site_name
    controllers = list(results.keys())

    lines = [
        f"\n{'='*72}",
        f"  COMPARISON REPORT — {site_name}",
        "  Simulation: 8,760 hours (1 year)",
        f"{'='*72}",
        "",
        f"  {'Metric':<30s}" + "".join(f"  {c:>14s}" for c in controllers),
        f"  {'─'*30}" + "".join(f"  {'─'*14}" for _ in controllers),
    ]

    def row(label: str, values: list[float], fmt: str = ".0f", unit: str = ""):
        vals = "".join(f"  {v:>14{fmt}}" for v in values)
        return f"  {label:<30s}{vals}  {unit}"

    def delta_row(label: str, values: list[float], fmt: str = ".1f"):
        deltas = []
        for v in values:
            if baseline_val := values[0]:
                pct = ((v - baseline_val) / abs(baseline_val)) * 100
                deltas.append(f"{pct:+.1f}%")
            else:
                deltas.append("—")
        return f"  {label:<30s}" + "".join(f"  {d:>14s}" for d in deltas)

    metrics = results.values()

    lines.append(row("Diesel consumed", [m.diesel_liters_consumed for m in metrics], ".0f", "liters"))
    lines.append(row("Diesel cost", [m.diesel_cost_cop / 1e6 for m in metrics], ".1f", "M COP"))
    lines.append(row("Diesel runtime", [m.diesel_runtime_hours for m in metrics], ".0f", "hours"))
    lines.append(row("Diesel starts", [m.diesel_starts for m in metrics], ".0f", ""))
    lines.append(row("CO₂ emissions", [m.co2_kg / 1000 for m in metrics], ".1f", "tons"))
    lines.append("")
    lines.append(row("Renewable fraction", [m.renewable_fraction * 100 for m in metrics], ".1f", "%"))
    lines.append(row("Solar used", [m.total_solar_kwh / 1000 for m in metrics], ".0f", "MWh"))
    lines.append(row("Wind used", [m.total_wind_kwh / 1000 for m in metrics], ".0f", "MWh"))
    lines.append("")
    lines.append(row("Unserved energy", [m.total_unserved_kwh for m in metrics], ".0f", "kWh"))
    lines.append(row("Hours with shedding", [m.hours_with_shed for m in metrics], ".0f", ""))
    lines.append(row("Service availability", [m.service_availability * 100 for m in metrics], ".1f", "%"))
    lines.append(row("Priority load uptime", [m.priority_load_uptime_hours for m in metrics], ".0f", "hours"))
    lines.append("")
    lines.append(row("Battery cycles", [m.battery_cycles for m in metrics], ".0f", ""))
    lines.append(row("Min SOC reached", [m.min_soc_reached for m in metrics], ".1f", "%"))
    lines.append(row("Avg SOC", [m.avg_soc for m in metrics], ".1f", "%"))

    lines.append("")
    lines.append(f"  {'─'*30}" + "".join(f"  {'─'*14}" for _ in controllers))

    # Delta vs baseline
    if len(controllers) > 1:
        lines.append(f"\n  Improvement vs. {controllers[0]}:")
        bl = results[controllers[0]]
        for name, m in results.items():
            if name == controllers[0]:
                continue
            diesel_delta = ((m.diesel_liters_consumed - bl.diesel_liters_consumed) / bl.diesel_liters_consumed * 100) if bl.diesel_liters_consumed else 0
            renew_delta = (m.renewable_fraction - bl.renewable_fraction) * 100
            shed_delta = ((m.total_unserved_kwh - bl.total_unserved_kwh) / bl.total_unserved_kwh * 100) if bl.total_unserved_kwh else 0
            lines.append(f"  {name:>14s}:  diesel {diesel_delta:+.1f}%,  renewable {renew_delta:+.1f}pp,  shedding {shed_delta:+.1f}%")

    lines.append(f"\n{'='*72}\n")
    return "\n".join(lines)
