#!/usr/bin/env python3
"""Run the microgrid simulation comparison.

Executes all controllers against all pilot sites and produces
a comparison report. This is the primary validation deliverable.

Usage:
    python -m sim.run                    # all sites, all controllers
    python -m sim.run --site inirida     # single site
    python -m sim.run --seed 42 --seed 43 --seed 44  # Monte Carlo (3 runs)
"""

from __future__ import annotations

import argparse
import time

from .controllers import Controller, ForecastController, KGForecastController, RuleBasedController
from .metrics import SimMetrics, compare
from .scenario import COQUI, INIRIDA, PILOT_SITES, PROVIDENCIA, ScenarioEngine, SiteProfile


def run_simulation(
    site: SiteProfile,
    controller: Controller,
    seed: int = 42,
) -> SimMetrics:
    """Run one controller on one site for one year."""
    scenario = ScenarioEngine(site, seed=seed)
    controller.reset()
    metrics = SimMetrics(controller_name=controller.name(), site_name=site.name)

    for state in scenario:
        action = controller.dispatch(state)

        # Apply dispatch to scenario state (updates SOC, fuel level)
        net_battery = action.solar_to_battery_kw - action.battery_discharge_kw
        scenario.apply_dispatch(action.diesel_kw, net_battery)

        metrics.record(state, action, site)

    metrics.finalize()
    return metrics


def run_all(sites: list[SiteProfile], seeds: list[int] | None = None):
    """Run all controllers on all sites and print comparison reports."""
    if seeds is None:
        seeds = [42]

    controllers: list[Controller] = [
        RuleBasedController(),
        ForecastController(),
    ]

    for site in sites:
        # Add KG controller with site-specific profile
        kg_controller = KGForecastController(site_profile=site)

        all_controllers = controllers + [kg_controller]

        print(f"\n{'#'*72}")
        print(f"#  SITE: {site.name} ({site.region})")
        print(f"#  Solar: {site.solar_capacity_kwp} kWp | "
              f"GHI: {site.avg_ghi_kwh_m2_day} kWh/m²/day | "
              f"Cloud: {site.cloud_fraction*100:.0f}%")
        print(f"#  Battery: {site.battery_capacity_kwh} kWh | "
              f"Diesel: {site.diesel_capacity_kw} kW")
        print(f"{'#'*72}")

        for seed in seeds:
            if len(seeds) > 1:
                print(f"\n  Seed: {seed}")

            results: dict[str, SimMetrics] = {}
            for ctrl in all_controllers:
                t0 = time.time()
                m = run_simulation(site, ctrl, seed=seed)
                elapsed = time.time() - t0
                results[ctrl.name()] = m
                print(f"  {ctrl.name():>14s}: {elapsed:.1f}s  "
                      f"diesel={m.diesel_liters_consumed:.0f}L  "
                      f"renewable={m.renewable_fraction*100:.1f}%  "
                      f"shed={m.hours_with_shed}h")

            print(compare(results))


def main():
    parser = argparse.ArgumentParser(description="Microgrid simulation comparison")
    parser.add_argument("--site", choices=["inirida", "coqui", "providencia", "all"],
                        default="all", help="Site to simulate")
    parser.add_argument("--seed", type=int, nargs="*", default=[42],
                        help="Random seeds for Monte Carlo runs")
    args = parser.parse_args()

    site_map = {"inirida": INIRIDA, "coqui": COQUI, "providencia": PROVIDENCIA}

    if args.site == "all":
        sites = PILOT_SITES
    else:
        sites = [site_map[args.site]]

    print("=" * 72)
    print("  MICROGRID AGENT — CONTROLLER COMPARISON SIMULATION")
    print(f"  Sites: {', '.join(s.name for s in sites)}")
    print(f"  Seeds: {args.seed}")
    print("  Controllers: rule-based, forecast, forecast+kg")
    print("=" * 72)

    run_all(sites, args.seed)


if __name__ == "__main__":
    main()
