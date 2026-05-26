#!/usr/bin/env python3
"""
Compound growth wealth projector.

Projects long-term wealth accumulation with configurable assumptions
for return rates, inflation, contributions, and tax drag.

Reads starting capital from finance-substrate patrimonio data.

Usage:
    python3 project_wealth.py --years 20 --monthly-contribution-usd 2000
    python3 project_wealth.py --years 30 --risk aggressive --json
    python3 project_wealth.py --years 10 --starting-capital 200000000
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

DATA_DIR = Path.home() / ".finance-substrate"
WM_DIR = Path.home() / ".wealth-management"
SALARY_FILE = DATA_DIR / "tax" / "salary-history.jsonl"

# ────────────────────────────────────────────────────────────────────
# Risk profiles: expected real returns (after inflation, before tax)
# ────────────────────────────────────────────────────────────────────

RISK_PROFILES = {
    "conservative": {
        "label": "Conservative",
        "expected_real_return": 0.03,
        "volatility": 0.08,
        "allocation": {"equities": 30, "fixed_income": 50, "real_estate": 10, "cash_afc": 10},
    },
    "moderate": {
        "label": "Moderate",
        "expected_real_return": 0.05,
        "volatility": 0.12,
        "allocation": {"equities": 55, "fixed_income": 25, "real_estate": 10, "cash_afc": 10},
    },
    "aggressive": {
        "label": "Aggressive",
        "expected_real_return": 0.07,
        "volatility": 0.18,
        "allocation": {"equities": 75, "fixed_income": 10, "real_estate": 10, "cash_afc": 5},
    },
}


@dataclass
class YearProjection:
    year: int
    age: int
    starting_value: float
    contribution: float
    growth: float
    tax_drag: float
    ending_value: float
    ending_real: float  # inflation-adjusted
    cumulative_contributions: float
    cumulative_growth: float
    contribution_pct: float  # % of ending value from contributions


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


def load_patrimonio_liquido(year: int) -> float:
    """Try to load patrimonio from finance-substrate cache."""
    cache = DATA_DIR / "cache" / "last_projection.json"
    if cache.exists():
        with open(cache) as f:
            proj = json.load(f)
        return proj.get("form_210", {}).get("patrimonio", {}).get("R31_patrimonio_liquido", 0)
    return 0


def load_salary_trajectory() -> dict:
    """Load salary history to estimate income growth."""
    if not SALARY_FILE.exists():
        return {"monthly_usd": 0, "years": {}}
    years = {}
    with open(SALARY_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            yr = rec["date"][:4]
            if yr not in years:
                years[yr] = {"total_usd": 0, "count": 0}
            years[yr]["total_usd"] += rec.get("amount_usd", 0)
            years[yr]["count"] += 1
    latest_yr = max(years.keys()) if years else None
    monthly = 0
    if latest_yr and years[latest_yr]["count"] > 0:
        monthly = years[latest_yr]["total_usd"] / years[latest_yr]["count"]
    return {"monthly_usd": monthly, "years": years}


def project(
    starting_capital: float,
    annual_contribution: float,
    years: int,
    real_return: float,
    tax_drag_pct: float,
    inflation: float,
    starting_age: int = 30,
) -> list:
    """Run compound growth projection."""
    results = []
    value = starting_capital
    cumulative_contrib = 0
    cumulative_growth = 0
    after_tax_return = real_return * (1 - tax_drag_pct / 100)

    for y in range(1, years + 1):
        growth = value * after_tax_return
        tax_on_growth = abs(growth * tax_drag_pct / 100) if growth > 0 else 0
        net_growth = growth
        value_before = value
        value = value + net_growth + annual_contribution
        cumulative_contrib += annual_contribution
        cumulative_growth += net_growth
        # Inflation-adjusted value
        real_value = value / ((1 + inflation) ** y)
        contrib_pct = (cumulative_contrib / value * 100) if value > 0 else 0

        results.append(YearProjection(
            year=y,
            age=starting_age + y,
            starting_value=round(value_before),
            contribution=round(annual_contribution),
            growth=round(net_growth),
            tax_drag=round(tax_on_growth),
            ending_value=round(value),
            ending_real=round(real_value),
            cumulative_contributions=round(cumulative_contrib),
            cumulative_growth=round(cumulative_growth),
            contribution_pct=round(contrib_pct, 1),
        ))

    return results


def find_milestones(projections: list, currency: str = "COP") -> list:
    """Find when portfolio crosses key milestones."""
    if currency == "COP":
        targets = [100_000_000, 500_000_000, 1_000_000_000, 2_000_000_000, 5_000_000_000]
        labels = ["$100M", "$500M", "$1B", "$2B", "$5B"]
    else:
        targets = [50_000, 100_000, 250_000, 500_000, 1_000_000]
        labels = ["$50K", "$100K", "$250K", "$500K", "$1M"]

    milestones = []
    for target, label in zip(targets, labels):
        for p in projections:
            if p.ending_value >= target:
                milestones.append({
                    "label": label,
                    "year": p.year,
                    "age": p.age,
                    "value": p.ending_value,
                })
                break
    return milestones


def crossover_year(projections: list) -> int:
    """Find when cumulative growth exceeds cumulative contributions."""
    for p in projections:
        if p.cumulative_growth > p.cumulative_contributions:
            return p.year
    return 0


def main():
    parser = argparse.ArgumentParser(description="Compound wealth projector")
    parser.add_argument("--years", type=int, default=20, help="Projection horizon")
    parser.add_argument("--monthly-contribution-usd", type=float, default=0,
                        help="Monthly contribution in USD (0 = auto from budget available)")
    parser.add_argument("--monthly-contribution-cop", type=float, default=0,
                        help="Monthly contribution in COP")
    parser.add_argument("--starting-capital", type=float, default=0,
                        help="Starting capital in COP (0 = from patrimonio)")
    parser.add_argument("--risk", choices=["conservative", "moderate", "aggressive"],
                        default="moderate", help="Risk profile")
    parser.add_argument("--tax-drag", type=float, default=2.0, help="Annual tax drag %%")
    parser.add_argument("--inflation", type=float, default=5.5, help="Annual inflation %%")
    parser.add_argument("--age", type=int, default=30, help="Current age")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    profile = RISK_PROFILES[args.risk]
    trm = load_current_trm()

    # Starting capital
    if args.starting_capital > 0:
        starting = args.starting_capital
    else:
        starting = load_patrimonio_liquido(2025)
        if starting <= 0:
            starting = 29_000_000  # Fallback estimate

    # Monthly contribution
    if args.monthly_contribution_cop > 0:
        monthly_cop = args.monthly_contribution_cop
    elif args.monthly_contribution_usd > 0:
        monthly_cop = args.monthly_contribution_usd * trm
    else:
        # Auto: estimate from salary available (assume 20% savings rate)
        salary = load_salary_trajectory()
        if salary["monthly_usd"] > 0:
            monthly_cop = salary["monthly_usd"] * trm * 0.20
        else:
            monthly_cop = 5_000_000  # Default ~$1,300 USD

    annual_contribution = monthly_cop * 12

    projections = project(
        starting_capital=starting,
        annual_contribution=annual_contribution,
        years=args.years,
        real_return=profile["expected_real_return"],
        tax_drag_pct=args.tax_drag,
        inflation=args.inflation / 100,
        starting_age=args.age,
    )

    milestones_cop = find_milestones(projections, "COP")
    milestones_usd = find_milestones(
        [YearProjection(**{**asdict(p), "ending_value": round(p.ending_value / trm)})
         for p in projections],
        "USD"
    )
    crossover = crossover_year(projections)

    result = {
        "parameters": {
            "starting_capital_cop": round(starting),
            "starting_capital_usd": round(starting / trm),
            "monthly_contribution_cop": round(monthly_cop),
            "monthly_contribution_usd": round(monthly_cop / trm),
            "annual_contribution_cop": round(annual_contribution),
            "risk_profile": args.risk,
            "expected_real_return": profile["expected_real_return"],
            "tax_drag_pct": args.tax_drag,
            "inflation_pct": args.inflation,
            "horizon_years": args.years,
            "trm": round(trm, 2),
        },
        "projections": [asdict(p) for p in projections],
        "milestones_cop": milestones_cop,
        "milestones_usd": milestones_usd,
        "crossover_year": crossover,
        "final_value_cop": projections[-1].ending_value if projections else 0,
        "final_value_usd": round(projections[-1].ending_value / trm) if projections else 0,
        "final_real_cop": projections[-1].ending_real if projections else 0,
        "total_contributed": projections[-1].cumulative_contributions if projections else 0,
        "total_growth": projections[-1].cumulative_growth if projections else 0,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    # Human-readable output
    params = result["parameters"]
    print(f"\n{'='*75}")
    print(f"  WEALTH PROJECTION — {args.years} Years ({profile['label']} Profile)")
    print(f"{'='*75}")
    print(f"  Starting capital:     ${starting:>15,.0f} COP (${starting/trm:>10,.0f} USD)")
    print(f"  Monthly contribution: ${monthly_cop:>15,.0f} COP (${monthly_cop/trm:>10,.0f} USD)")
    print(f"  Expected real return: {profile['expected_real_return']*100:.1f}%")
    print(f"  Tax drag:             {args.tax_drag:.1f}%")
    print(f"  Inflation:            {args.inflation:.1f}%")
    print(f"  TRM:                  {trm:,.2f}")
    print()

    # Year-by-year table (key years only)
    show_years = [1, 2, 3, 5, 7, 10, 15, 20, 25, 30]
    show_years = [y for y in show_years if y <= args.years]
    if args.years not in show_years:
        show_years.append(args.years)

    print(f"  {'Yr':>3s} {'Age':>4s} {'Value (COP)':>18s} {'Value (USD)':>14s} {'Real (COP)':>16s} {'Contrib%':>8s}")
    print(f"  {'-'*69}")
    for p in projections:
        if p.year in show_years:
            print(f"  {p.year:>3d} {p.age:>4d} ${p.ending_value:>17,.0f} ${p.ending_value/trm:>13,.0f} ${p.ending_real:>15,.0f} {p.contribution_pct:>7.1f}%")

    print()

    # Milestones
    if milestones_cop:
        print(f"  ── MILESTONES (COP) ──────────────────────────────────────────")
        for m in milestones_cop:
            print(f"  {m['label']:>8s} → Year {m['year']:>2d} (age {m['age']})")
        print()

    if milestones_usd:
        print(f"  ── MILESTONES (USD) ──────────────────────────────────────────")
        for m in milestones_usd:
            print(f"  {m['label']:>8s} → Year {m['year']:>2d} (age {m['age']})")
        print()

    if crossover > 0:
        print(f"  ── CROSSOVER ─────────────────────────────────────────────────")
        print(f"  Growth exceeds contributions at Year {crossover}")
        print(f"  After this point, your money works harder than you do.")
        print()

    # Summary
    final = projections[-1]
    print(f"  ── SUMMARY ───────────────────────────────────────────────────")
    print(f"  Final value:              ${final.ending_value:>15,.0f} COP (${final.ending_value/trm:>10,.0f} USD)")
    print(f"  Inflation-adjusted:       ${final.ending_real:>15,.0f} COP")
    print(f"  Total contributed:        ${final.cumulative_contributions:>15,.0f} COP")
    print(f"  Total growth:             ${final.cumulative_growth:>15,.0f} COP")
    print(f"  Growth multiple:          {final.ending_value / starting:.1f}x")
    print(f"  CAGR (nominal):           {((final.ending_value / starting) ** (1/args.years) - 1) * 100:.1f}%")

    # Sensitivity
    print()
    print(f"  ── SENSITIVITY (Final value at different returns) ─────────")
    for delta in [-2, -1, 0, 1, 2]:
        alt_return = profile["expected_real_return"] + delta / 100
        if alt_return <= 0:
            continue
        alt = project(starting, annual_contribution, args.years, alt_return, args.tax_drag, args.inflation / 100, args.age)
        marker = " <<<" if delta == 0 else ""
        print(f"  {alt_return*100:>5.1f}% return → ${alt[-1].ending_value:>15,.0f} COP{marker}")


if __name__ == "__main__":
    main()
