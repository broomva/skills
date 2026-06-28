#!/usr/bin/env python3
"""
Monte Carlo & Stress Testing (Mode 6) — wealth-management skill.

Simulate portfolio outcomes under uncertainty. Runs Monte Carlo simulations
with configurable parameters, historical stress tests, and custom scenarios.
Outputs structured results consumable by autoany EGRI evaluator loops.

Usage:
    python3 scenario_analysis.py --years 20 --simulations 10000
    python3 scenario_analysis.py --years 30 --risk aggressive --goal-cop 2000000000
    python3 scenario_analysis.py --stress-test 2008-gfc --allocation-file allocation.json
    python3 scenario_analysis.py --years 20 --simulations 10000 --egri --goal-cop 1000000000
    python3 scenario_analysis.py --years 20 --json

EGRI evaluator mode (structured JSON output for autoany):
    python3 scenario_analysis.py --egri --goal-cop 1000000000 --years 20 \
        --allocation-file contribution_plan.yaml
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------
_yaml = None
try:
    import yaml as _yaml
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants & data directories
# ---------------------------------------------------------------------------

DATA_DIR = Path.home() / ".finance-substrate"
WM_DIR = Path.home() / ".wealth-management"

# Asset class expected returns and volatility (annualized, real after inflation)
ASSET_CLASSES = {
    "us_equities":       {"return": 0.07, "vol": 0.16, "label": "US Equities (S&P 500)"},
    "intl_equities":     {"return": 0.05, "vol": 0.18, "label": "Intl Equities"},
    "col_equities":      {"return": 0.05, "vol": 0.22, "label": "Colombian Equities (BVC)"},
    "us_bonds":          {"return": 0.02, "vol": 0.06, "label": "US Bonds"},
    "col_fixed_income":  {"return": 0.03, "vol": 0.04, "label": "Colombian CDT/FIC"},
    "real_estate":       {"return": 0.04, "vol": 0.12, "label": "Real Estate"},
    "gold":              {"return": 0.01, "vol": 0.15, "label": "Gold"},
    "crypto":            {"return": 0.10, "vol": 0.60, "label": "Crypto (BTC/ETH)"},
    "pension_vol":       {"return": 0.05, "vol": 0.10, "label": "Pensión Voluntaria"},
    "afc":               {"return": 0.02, "vol": 0.03, "label": "AFC (Davivienda)"},
    "cash":              {"return": 0.00, "vol": 0.01, "label": "Cash"},
}

# Risk profile allocations
RISK_PROFILES = {
    "conservative": {
        "us_equities": 0.15, "intl_equities": 0.05, "col_equities": 0.05,
        "us_bonds": 0.20, "col_fixed_income": 0.25, "real_estate": 0.10,
        "pension_vol": 0.10, "afc": 0.05, "cash": 0.05,
    },
    "moderate": {
        "us_equities": 0.30, "intl_equities": 0.10, "col_equities": 0.05,
        "us_bonds": 0.10, "col_fixed_income": 0.15, "real_estate": 0.10,
        "pension_vol": 0.10, "afc": 0.05, "cash": 0.05,
    },
    "aggressive": {
        "us_equities": 0.40, "intl_equities": 0.15, "col_equities": 0.05,
        "us_bonds": 0.05, "col_fixed_income": 0.05, "real_estate": 0.05,
        "crypto": 0.10, "pension_vol": 0.10, "afc": 0.03, "cash": 0.02,
    },
}

# Correlation matrix (simplified — key pairs)
# In practice, asset correlations shift in crises (correlation = 1 during crashes)
CORRELATIONS = {
    ("us_equities", "intl_equities"): 0.75,
    ("us_equities", "col_equities"): 0.50,
    ("us_equities", "us_bonds"): -0.20,
    ("us_equities", "gold"): -0.05,
    ("us_equities", "crypto"): 0.40,
    ("us_equities", "real_estate"): 0.60,
    ("col_equities", "col_fixed_income"): 0.20,
    ("crypto", "gold"): 0.10,
}

# Historical stress scenarios: monthly returns over crisis period
STRESS_SCENARIOS = {
    "2008-gfc": {
        "label": "2008 Global Financial Crisis",
        "duration_months": 18,
        "shocks": {
            "us_equities": -0.50, "intl_equities": -0.55, "col_equities": -0.40,
            "us_bonds": 0.10, "col_fixed_income": -0.05, "real_estate": -0.30,
            "gold": 0.15, "crypto": -0.80, "pension_vol": -0.20,
            "afc": 0.01, "cash": 0.02,
        },
    },
    "2020-covid": {
        "label": "2020 COVID-19 Crash",
        "duration_months": 3,
        "shocks": {
            "us_equities": -0.34, "intl_equities": -0.35, "col_equities": -0.45,
            "us_bonds": 0.05, "col_fixed_income": -0.02, "real_estate": -0.15,
            "gold": 0.03, "crypto": -0.50, "pension_vol": -0.15,
            "afc": 0.01, "cash": 0.01,
        },
    },
    "2022-rates": {
        "label": "2022 Rate Hiking Cycle",
        "duration_months": 12,
        "shocks": {
            "us_equities": -0.20, "intl_equities": -0.22, "col_equities": -0.15,
            "us_bonds": -0.15, "col_fixed_income": -0.05, "real_estate": -0.10,
            "gold": -0.02, "crypto": -0.65, "pension_vol": -0.10,
            "afc": 0.02, "cash": 0.03,
        },
    },
    "1999-colombia": {
        "label": "1999 Colombian Financial Crisis",
        "duration_months": 24,
        "shocks": {
            "us_equities": 0.10, "intl_equities": 0.05, "col_equities": -0.60,
            "us_bonds": 0.08, "col_fixed_income": -0.20, "real_estate": -0.40,
            "gold": 0.05, "crypto": 0, "pension_vol": -0.30,
            "afc": -0.10, "cash": -0.05,
        },
    },
    "cop-devaluation-30": {
        "label": "COP Devaluation (+30% TRM)",
        "duration_months": 6,
        "shocks": {
            "us_equities": 0.15, "intl_equities": 0.12, "col_equities": -0.20,
            "us_bonds": 0.05, "col_fixed_income": -0.05, "real_estate": -0.10,
            "gold": 0.10, "crypto": 0.05, "pension_vol": -0.08,
            "afc": -0.02, "cash": -0.15,
        },
    },
    "stagflation": {
        "label": "Stagflation (High Inflation + Low Growth, 5 years)",
        "duration_months": 60,
        "shocks": {
            "us_equities": -0.15, "intl_equities": -0.20, "col_equities": -0.25,
            "us_bonds": -0.20, "col_fixed_income": -0.10, "real_estate": 0.10,
            "gold": 0.40, "crypto": -0.30, "pension_vol": -0.15,
            "afc": -0.05, "cash": -0.30,
        },
    },
    "career-disruption": {
        "label": "Career Disruption (0 income for 12 months)",
        "duration_months": 12,
        "shocks": {
            "us_equities": 0, "intl_equities": 0, "col_equities": 0,
            "us_bonds": 0, "col_fixed_income": 0, "real_estate": 0,
            "gold": 0, "crypto": 0, "pension_vol": 0,
            "afc": 0, "cash": 0,
        },
        "income_multiplier": 0,
    },
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScenarioResult:
    """Results from a Monte Carlo simulation or stress test."""
    scenario_type: str  # "monte_carlo" or "stress_test"
    scenario_name: str
    years: int
    simulations: int
    allocation: dict[str, float]
    starting_capital_cop: float
    monthly_contribution_cop: float
    goal_cop: float | None

    # Monte Carlo outcomes
    probability_of_goal_pct: float | None
    percentiles: dict[str, float]  # p5, p10, p25, p50, p75, p90, p95
    mean_final_value: float
    worst_case: float
    best_case: float

    # Risk metrics
    median_max_drawdown_pct: float
    probability_of_ruin_pct: float  # P(portfolio < 0)
    safe_withdrawal_rate_pct: float | None
    sequence_risk_early_bear_pct: float  # P(goal) if bear market in first 5 years
    sequence_risk_late_bear_pct: float   # P(goal) if bear market in last 5 years

    # Stress test specific
    stress_impact_pct: float | None
    stress_recovery_months: int | None

    def to_egri_outcome(self) -> dict:
        """Format as autoany EGRI Outcome for evaluator consumption."""
        score = self.probability_of_goal_pct or 0
        constraints_passed = True
        violations = []

        if self.median_max_drawdown_pct < -25:
            constraints_passed = False
            violations.append(f"median_max_drawdown={self.median_max_drawdown_pct:.1f}% exceeds -25% limit")

        if self.probability_of_ruin_pct > 5:
            constraints_passed = False
            violations.append(f"ruin_probability={self.probability_of_ruin_pct:.1f}% exceeds 5% limit")

        return {
            "score": score,
            "constraints_passed": constraints_passed,
            "violations": violations,
            "metrics": {
                "probability_of_goal_pct": self.probability_of_goal_pct,
                "median_final_value": self.percentiles.get("p50", 0),
                "p10_final_value": self.percentiles.get("p10", 0),
                "p90_final_value": self.percentiles.get("p90", 0),
                "median_max_drawdown_pct": self.median_max_drawdown_pct,
                "probability_of_ruin_pct": self.probability_of_ruin_pct,
                "safe_withdrawal_rate_pct": self.safe_withdrawal_rate_pct,
                "sequence_risk_early_bear_pct": self.sequence_risk_early_bear_pct,
                "sequence_risk_late_bear_pct": self.sequence_risk_late_bear_pct,
            },
        }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_current_trm() -> float:
    trm_file = DATA_DIR / "fx" / "trm-history.jsonl"
    if not trm_file.exists():
        return 4000.0
    latest = None
    with open(trm_file) as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                if latest is None or rec["date"] > latest["date"]:
                    latest = rec
    return latest["valor"] if latest else 4000.0


def load_patrimonio() -> float:
    cache = DATA_DIR / "cache" / "last_projection.json"
    if cache.exists():
        with open(cache) as f:
            proj = json.load(f)
        return proj.get("form_210", {}).get("patrimonio", {}).get("R31_patrimonio_liquido", 0)
    return 0


def load_allocation_file(path: str) -> dict[str, float]:
    """Load allocation from JSON or YAML file (autoany artifact format)."""
    with open(path) as f:
        if path.endswith((".yaml", ".yml")):
            if _yaml:
                data = _yaml.safe_load(f)
            else:
                data = json.load(f)  # fallback
        else:
            data = json.load(f)

    # Support both flat dict and nested "allocation" key
    if "allocation" in data:
        return data["allocation"]
    if "weights" in data:
        return data["weights"]
    return {k: v for k, v in data.items() if isinstance(v, (int, float))}


# ---------------------------------------------------------------------------
# Monte Carlo simulation engine
# ---------------------------------------------------------------------------

def run_monte_carlo(
    allocation: dict[str, float],
    starting_capital: float,
    monthly_contribution: float,
    years: int,
    simulations: int = 10000,
    goal: float | None = None,
    seed: int = 42,
) -> ScenarioResult:
    """Run Monte Carlo simulation with given allocation."""
    random.seed(seed)
    n_months = years * 12

    # Compute portfolio expected return and volatility from allocation
    port_return = sum(
        allocation.get(ac, 0) * ASSET_CLASSES[ac]["return"]
        for ac in ASSET_CLASSES
    )
    # Portfolio vol (simplified — ignores correlations for speed, adds correlation penalty)
    port_var = sum(
        allocation.get(ac, 0) ** 2 * ASSET_CLASSES[ac]["vol"] ** 2
        for ac in ASSET_CLASSES
    )
    # Add cross-correlation terms
    for (a1, a2), corr in CORRELATIONS.items():
        w1 = allocation.get(a1, 0)
        w2 = allocation.get(a2, 0)
        if w1 > 0 and w2 > 0:
            port_var += 2 * w1 * w2 * corr * ASSET_CLASSES[a1]["vol"] * ASSET_CLASSES[a2]["vol"]
    port_vol = math.sqrt(max(0, port_var))

    monthly_return = (1 + port_return) ** (1/12) - 1
    monthly_vol = port_vol / math.sqrt(12)

    final_values = []
    max_drawdowns = []
    successes = 0
    ruins = 0

    # For sequence-of-returns risk
    early_bear_successes = 0
    early_bear_total = 0
    late_bear_successes = 0
    late_bear_total = 0

    for sim in range(simulations):
        value = starting_capital
        peak = value
        max_dd = 0
        has_early_bear = False
        has_late_bear = False
        path = [value]

        for month in range(n_months):
            # Log-normal returns
            r = random.gauss(monthly_return, monthly_vol)
            value = value * (1 + r) + monthly_contribution
            value = max(0, value)
            path.append(value)

            # Track drawdown
            if value > peak:
                peak = value
            dd = (value - peak) / peak if peak > 0 else 0
            max_dd = min(max_dd, dd)

            # Detect bear market (>20% drawdown)
            if dd < -0.20:
                year_of_sim = month // 12
                if year_of_sim < 5:
                    has_early_bear = True
                if year_of_sim >= years - 5:
                    has_late_bear = True

        final_values.append(value)
        max_drawdowns.append(max_dd)

        if value <= 0:
            ruins += 1

        if goal is not None and value >= goal:
            successes += 1
            if has_early_bear:
                early_bear_successes += 1
            if has_late_bear:
                late_bear_successes += 1

        if has_early_bear:
            early_bear_total += 1
        if has_late_bear:
            late_bear_total += 1

    # Sort for percentiles
    final_values.sort()
    max_drawdowns.sort()

    def pct(arr, p):
        idx = int(len(arr) * p / 100)
        idx = max(0, min(idx, len(arr) - 1))
        return round(arr[idx])

    # Safe withdrawal rate (4% rule variant — find rate where 95% of simulations survive)
    swr = None
    if years >= 10:
        for rate_bps in range(600, 0, -10):  # 6% down to 0.1%
            rate = rate_bps / 10000
            annual_withdrawal = starting_capital * rate
            monthly_wd = annual_withdrawal / 12
            survived = 0
            random.seed(seed + 999)
            for _ in range(min(simulations, 2000)):
                val = starting_capital
                pk = val
                for month in range(n_months):
                    r = random.gauss(monthly_return, monthly_vol)
                    val = val * (1 + r) - monthly_wd
                    if val <= 0:
                        break
                if val > 0:
                    survived += 1
            if survived / min(simulations, 2000) >= 0.95:
                swr = rate * 100
                break

    return ScenarioResult(
        scenario_type="monte_carlo",
        scenario_name="Monte Carlo Simulation",
        years=years,
        simulations=simulations,
        allocation=allocation,
        starting_capital_cop=starting_capital,
        monthly_contribution_cop=monthly_contribution,
        goal_cop=goal,
        probability_of_goal_pct=round(successes / simulations * 100, 1) if goal else None,
        percentiles={
            "p5": pct(final_values, 5),
            "p10": pct(final_values, 10),
            "p25": pct(final_values, 25),
            "p50": pct(final_values, 50),
            "p75": pct(final_values, 75),
            "p90": pct(final_values, 90),
            "p95": pct(final_values, 95),
        },
        mean_final_value=round(sum(final_values) / len(final_values)),
        worst_case=round(final_values[0]),
        best_case=round(final_values[-1]),
        median_max_drawdown_pct=round(max_drawdowns[len(max_drawdowns) // 2] * 100, 1),
        probability_of_ruin_pct=round(ruins / simulations * 100, 2),
        safe_withdrawal_rate_pct=round(swr, 2) if swr else None,
        sequence_risk_early_bear_pct=(
            round(early_bear_successes / early_bear_total * 100, 1)
            if early_bear_total > 0 else None
        ),
        sequence_risk_late_bear_pct=(
            round(late_bear_successes / late_bear_total * 100, 1)
            if late_bear_total > 0 else None
        ),
        stress_impact_pct=None,
        stress_recovery_months=None,
    )


# ---------------------------------------------------------------------------
# Stress test engine
# ---------------------------------------------------------------------------

def run_stress_test(
    scenario_key: str,
    allocation: dict[str, float],
    starting_capital: float,
    monthly_contribution: float = 0,
) -> ScenarioResult:
    """Run a historical stress scenario on the portfolio."""
    scenario = STRESS_SCENARIOS[scenario_key]
    duration = scenario["duration_months"]
    shocks = scenario["shocks"]
    income_mult = scenario.get("income_multiplier", 1.0)

    # Compute portfolio-level shock
    portfolio_shock = sum(
        allocation.get(ac, 0) * shocks.get(ac, 0)
        for ac in ASSET_CLASSES
    )

    # Simulate month-by-month decline
    value = starting_capital
    min_value = value
    path = [value]

    for month in range(duration):
        # Distribute shock linearly across months
        monthly_shock = portfolio_shock / duration
        value = value * (1 + monthly_shock) + monthly_contribution * income_mult
        value = max(0, value)
        path.append(value)
        min_value = min(min_value, value)

    # Simulate recovery (assume normal returns resume)
    port_return = sum(
        allocation.get(ac, 0) * ASSET_CLASSES[ac]["return"]
        for ac in ASSET_CLASSES
    )
    monthly_return = (1 + port_return) ** (1/12) - 1
    recovery_months = 0
    recovery_value = value
    while recovery_value < starting_capital and recovery_months < 120:
        recovery_value = recovery_value * (1 + monthly_return) + monthly_contribution
        recovery_months += 1

    impact_pct = (value - starting_capital) / starting_capital * 100

    return ScenarioResult(
        scenario_type="stress_test",
        scenario_name=scenario["label"],
        years=duration // 12,
        simulations=1,
        allocation=allocation,
        starting_capital_cop=starting_capital,
        monthly_contribution_cop=monthly_contribution,
        goal_cop=None,
        probability_of_goal_pct=None,
        percentiles={
            "min_during_stress": round(min_value),
            "end_of_stress": round(value),
        },
        mean_final_value=round(value),
        worst_case=round(min_value),
        best_case=round(value),
        median_max_drawdown_pct=round((min_value - starting_capital) / starting_capital * 100, 1),
        probability_of_ruin_pct=100.0 if value <= 0 else 0.0,
        safe_withdrawal_rate_pct=None,
        sequence_risk_early_bear_pct=None,
        sequence_risk_late_bear_pct=None,
        stress_impact_pct=round(impact_pct, 1),
        stress_recovery_months=recovery_months if recovery_value >= starting_capital else None,
    )


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_monte_carlo(result: ScenarioResult):
    """Pretty-print Monte Carlo results."""
    r = result
    trm = load_current_trm()

    print(f"\n{'='*72}")
    print(f"  MONTE CARLO — {r.simulations:,d} simulations × {r.years} years")
    print(f"{'='*72}")
    print(f"  Starting capital:     ${r.starting_capital_cop:>15,.0f} COP (${r.starting_capital_cop/trm:>10,.0f} USD)")
    print(f"  Monthly contribution: ${r.monthly_contribution_cop:>15,.0f} COP")
    print()

    # Allocation
    print(f"  ── ALLOCATION ────────────────────────────────────────────────")
    for ac, weight in sorted(r.allocation.items(), key=lambda x: -x[1]):
        if weight > 0:
            label = ASSET_CLASSES.get(ac, {}).get("label", ac)
            print(f"    {label:<30s} {weight*100:>5.1f}%")
    print()

    # Goal
    if r.goal_cop and r.probability_of_goal_pct is not None:
        print(f"  ── GOAL ──────────────────────────────────────────────────────")
        print(f"  Target:               ${r.goal_cop:>15,.0f} COP (${r.goal_cop/trm:>10,.0f} USD)")
        bar_len = int(r.probability_of_goal_pct / 2)
        bar = "█" * bar_len + "░" * (50 - bar_len)
        print(f"  Probability:          {r.probability_of_goal_pct:>5.1f}% [{bar}]")
        print()

    # Outcome distribution
    p = r.percentiles
    print(f"  ── OUTCOME DISTRIBUTION ──────────────────────────────────────")
    print(f"  Worst case:           ${r.worst_case:>15,.0f} COP")
    print(f"  P5  (pessimistic):    ${p.get('p5', 0):>15,.0f} COP")
    print(f"  P10:                  ${p.get('p10', 0):>15,.0f} COP")
    print(f"  P25:                  ${p.get('p25', 0):>15,.0f} COP")
    print(f"  P50 (median):         ${p.get('p50', 0):>15,.0f} COP")
    print(f"  P75:                  ${p.get('p75', 0):>15,.0f} COP")
    print(f"  P90 (optimistic):     ${p.get('p90', 0):>15,.0f} COP")
    print(f"  P95:                  ${p.get('p95', 0):>15,.0f} COP")
    print(f"  Best case:            ${r.best_case:>15,.0f} COP")
    print(f"  Mean:                 ${r.mean_final_value:>15,.0f} COP")
    print()

    # Risk
    print(f"  ── RISK METRICS ──────────────────────────────────────────────")
    print(f"  Median Max Drawdown:  {r.median_max_drawdown_pct:>8.1f}%")
    print(f"  Probability of Ruin:  {r.probability_of_ruin_pct:>8.2f}%")
    if r.safe_withdrawal_rate_pct:
        print(f"  Safe Withdrawal Rate: {r.safe_withdrawal_rate_pct:>8.2f}% (95% survival)")
    print()

    # Sequence risk
    if r.sequence_risk_early_bear_pct is not None or r.sequence_risk_late_bear_pct is not None:
        print(f"  ── SEQUENCE-OF-RETURNS RISK ──────────────────────────────────")
        if r.sequence_risk_early_bear_pct is not None:
            print(f"  P(goal | bear in first 5yr):  {r.sequence_risk_early_bear_pct:>5.1f}%")
        if r.sequence_risk_late_bear_pct is not None:
            print(f"  P(goal | bear in last 5yr):   {r.sequence_risk_late_bear_pct:>5.1f}%")


def print_stress_test(result: ScenarioResult):
    """Pretty-print stress test results."""
    r = result
    trm = load_current_trm()

    print(f"\n  ── STRESS TEST: {r.scenario_name} ──")
    print(f"  Starting:    ${r.starting_capital_cop:>15,.0f} COP")
    print(f"  After shock: ${r.mean_final_value:>15,.0f} COP")
    print(f"  Impact:      {r.stress_impact_pct:>+8.1f}%")
    print(f"  Max DD:      {r.median_max_drawdown_pct:>8.1f}%")
    if r.stress_recovery_months is not None:
        print(f"  Recovery:    {r.stress_recovery_months:>8d} months")
    else:
        print(f"  Recovery:    NOT RECOVERED (within 10 years)")
    if r.probability_of_ruin_pct > 0:
        print(f"  RUIN:        YES — portfolio wiped out")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Monte Carlo & Stress Testing — wealth-management skill Mode 6",
    )
    parser.add_argument("--years", type=int, default=20, help="Projection horizon")
    parser.add_argument("--simulations", type=int, default=10000, help="Monte Carlo runs")
    parser.add_argument("--risk", choices=["conservative", "moderate", "aggressive"], default="moderate")
    parser.add_argument("--allocation-file", help="Load allocation from JSON/YAML (autoany artifact)")
    parser.add_argument("--starting-capital", type=float, default=0, help="Starting capital COP (0=auto)")
    parser.add_argument("--monthly-contribution", type=float, default=0, help="Monthly contribution COP")
    parser.add_argument("--monthly-contribution-usd", type=float, default=0, help="Monthly contribution USD")
    parser.add_argument("--goal-cop", type=float, default=0, help="Target portfolio value COP")
    parser.add_argument("--goal-usd", type=float, default=0, help="Target portfolio value USD")
    parser.add_argument("--stress-test", help="Run specific stress test (e.g. 2008-gfc, 2020-covid)")
    parser.add_argument("--all-stress", action="store_true", help="Run all stress scenarios")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--egri", action="store_true",
                        help="Output as EGRI Outcome (for autoany evaluator)")
    args = parser.parse_args()

    trm = load_current_trm()

    # Load allocation
    if args.allocation_file:
        allocation = load_allocation_file(args.allocation_file)
    else:
        allocation = RISK_PROFILES[args.risk]

    # Starting capital
    capital = args.starting_capital
    if capital <= 0:
        capital = load_patrimonio()
    if capital <= 0:
        capital = 50_000_000  # Default ~$12.5K USD

    # Monthly contribution
    monthly = args.monthly_contribution
    if monthly <= 0 and args.monthly_contribution_usd > 0:
        monthly = args.monthly_contribution_usd * trm

    # Goal
    goal = None
    if args.goal_cop > 0:
        goal = args.goal_cop
    elif args.goal_usd > 0:
        goal = args.goal_usd * trm

    results = {}

    # Run Monte Carlo
    mc_result = run_monte_carlo(
        allocation=allocation,
        starting_capital=capital,
        monthly_contribution=monthly,
        years=args.years,
        simulations=args.simulations,
        goal=goal,
        seed=args.seed,
    )
    results["monte_carlo"] = asdict(mc_result)

    # Run stress tests
    stress_results = {}
    if args.stress_test:
        if args.stress_test in STRESS_SCENARIOS:
            sr = run_stress_test(args.stress_test, allocation, capital, monthly)
            stress_results[args.stress_test] = asdict(sr)
        else:
            print(f"Unknown stress test: {args.stress_test}", file=sys.stderr)
            print(f"Available: {', '.join(STRESS_SCENARIOS.keys())}", file=sys.stderr)
            raise SystemExit(1)
    elif args.all_stress:
        for key in STRESS_SCENARIOS:
            sr = run_stress_test(key, allocation, capital, monthly)
            stress_results[key] = asdict(sr)

    if stress_results:
        results["stress_tests"] = stress_results

    # Output
    if args.egri:
        outcome = mc_result.to_egri_outcome()
        print(json.dumps(outcome, indent=2))
    elif args.json:
        print(json.dumps(results, indent=2))
    else:
        print_monte_carlo(mc_result)
        if stress_results:
            print(f"\n{'='*72}")
            print(f"  STRESS TESTS")
            print(f"{'='*72}")
            for key, sr_dict in stress_results.items():
                sr = ScenarioResult(**sr_dict)
                print_stress_test(sr)
        print()

    # Save results
    results_dir = WM_DIR / "scenarios"
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = date.today().isoformat()
    result_file = results_dir / f"scenario-{ts}.json"
    with open(result_file, "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
