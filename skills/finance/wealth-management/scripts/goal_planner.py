#!/usr/bin/env python3
"""
Goal-based financial planner.

Given a target amount and date, computes required monthly savings,
probability of success, and recommended asset allocation.

Usage:
    python3 goal_planner.py --target-usd 500000 --target-date 2035-12-31
    python3 goal_planner.py --target-cop 1000000000 --target-date 2040-01-01 --risk moderate
"""

import argparse
import json
import math
import random
from datetime import date
from pathlib import Path

DATA_DIR = Path.home() / ".finance-substrate"

RISK_RETURNS = {
    "conservative": {"real": 0.03, "vol": 0.08},
    "moderate": {"real": 0.05, "vol": 0.12},
    "aggressive": {"real": 0.07, "vol": 0.18},
}


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


def required_monthly_savings(target: float, current: float, years: float, annual_return: float) -> float:
    """Compute required monthly contribution to reach target."""
    if years <= 0:
        return max(0, target - current)
    r_monthly = (1 + annual_return) ** (1 / 12) - 1
    n = int(years * 12)
    fv_current = current * (1 + r_monthly) ** n
    gap = target - fv_current
    if gap <= 0:
        return 0  # Already on track with no contributions
    if r_monthly == 0:
        return gap / n
    return gap * r_monthly / ((1 + r_monthly) ** n - 1)


def required_return(target: float, current: float, years: float, monthly_contrib: float) -> float:
    """Find the annual return needed to reach target with given contributions."""
    if current >= target:
        return 0
    # Binary search for the required return
    lo, hi = -0.05, 0.30
    for _ in range(100):
        mid = (lo + hi) / 2
        r_monthly = (1 + mid) ** (1 / 12) - 1
        n = int(years * 12)
        fv = current * (1 + r_monthly) ** n
        if r_monthly != 0:
            fv += monthly_contrib * ((1 + r_monthly) ** n - 1) / r_monthly
        else:
            fv += monthly_contrib * n
        if fv < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def monte_carlo_probability(
    target: float, current: float, monthly_contrib: float,
    years: float, real_return: float, volatility: float,
    simulations: int = 5000,
) -> dict:
    """Run Monte Carlo simulation to estimate probability of reaching target."""
    n_months = int(years * 12)
    monthly_return = (1 + real_return) ** (1 / 12) - 1
    monthly_vol = volatility / math.sqrt(12)
    successes = 0
    final_values = []

    random.seed(42)  # Reproducible
    for _ in range(simulations):
        value = current
        for _ in range(n_months):
            r = random.gauss(monthly_return, monthly_vol)
            value = value * (1 + r) + monthly_contrib
            value = max(0, value)  # Floor at zero
        final_values.append(value)
        if value >= target:
            successes += 1

    final_values.sort()
    return {
        "probability_pct": round(successes / simulations * 100, 1),
        "p10": round(final_values[int(simulations * 0.10)]),
        "p25": round(final_values[int(simulations * 0.25)]),
        "p50": round(final_values[int(simulations * 0.50)]),
        "p75": round(final_values[int(simulations * 0.75)]),
        "p90": round(final_values[int(simulations * 0.90)]),
        "worst": round(final_values[0]),
        "best": round(final_values[-1]),
    }


def main():
    parser = argparse.ArgumentParser(description="Goal-based financial planner")
    parser.add_argument("--target-usd", type=float, default=0)
    parser.add_argument("--target-cop", type=float, default=0)
    parser.add_argument("--target-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--current-savings", type=float, default=0, help="Current savings COP (0=auto)")
    parser.add_argument("--monthly-savings", type=float, default=0, help="Current monthly savings COP")
    parser.add_argument("--risk", choices=["conservative", "moderate", "aggressive"], default="moderate")
    parser.add_argument("--simulations", type=int, default=5000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    trm = load_current_trm()
    profile = RISK_RETURNS[args.risk]

    # Target
    if args.target_cop > 0:
        target_cop = args.target_cop
    elif args.target_usd > 0:
        target_cop = args.target_usd * trm
    else:
        print("Error: provide --target-usd or --target-cop", file=__import__("sys").stderr)
        raise SystemExit(1)
    target_usd = target_cop / trm

    # Timeline
    target_dt = date.fromisoformat(args.target_date)
    today = date.today()
    years = (target_dt - today).days / 365.25
    if years <= 0:
        print("Error: target date must be in the future", file=__import__("sys").stderr)
        raise SystemExit(1)

    # Current savings
    current = args.current_savings if args.current_savings > 0 else load_patrimonio()
    if current <= 0:
        current = 29_000_000

    # Required savings
    req_monthly = required_monthly_savings(target_cop, current, years, profile["real"])
    req_return = required_return(target_cop, current, years, args.monthly_savings) if args.monthly_savings > 0 else None

    # Monte Carlo
    mc = monte_carlo_probability(
        target_cop, current, args.monthly_savings or req_monthly,
        years, profile["real"], profile["vol"], args.simulations,
    )

    # Gap analysis
    if args.monthly_savings > 0:
        # Project with current savings rate
        r_m = (1 + profile["real"]) ** (1 / 12) - 1
        n = int(years * 12)
        projected = current * (1 + r_m) ** n
        if r_m != 0:
            projected += args.monthly_savings * ((1 + r_m) ** n - 1) / r_m
        gap = target_cop - projected
        status = "on_track" if gap <= 0 else ("behind" if gap > target_cop * 0.1 else "close")
    else:
        projected = 0
        gap = 0
        status = "planning"

    result = {
        "goal": {
            "target_cop": round(target_cop),
            "target_usd": round(target_usd),
            "target_date": args.target_date,
            "years_remaining": round(years, 1),
        },
        "current": {
            "savings_cop": round(current),
            "savings_usd": round(current / trm),
            "monthly_savings_cop": round(args.monthly_savings),
        },
        "required": {
            "monthly_cop": round(req_monthly),
            "monthly_usd": round(req_monthly / trm),
            "annual_cop": round(req_monthly * 12),
        },
        "risk_profile": args.risk,
        "expected_return": profile["real"],
        "monte_carlo": mc,
        "gap_analysis": {
            "projected_cop": round(projected) if projected else None,
            "gap_cop": round(gap) if gap else None,
            "status": status,
        },
        "required_return_no_savings": round(required_return(target_cop, current, years, 0) * 100, 1),
    }
    if req_return is not None:
        result["required_return_with_savings"] = round(req_return * 100, 1)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    # Human-readable
    print(f"\n{'='*70}")
    print(f"  GOAL PLANNER — {args.target_date}")
    print(f"{'='*70}")
    print(f"  Target:           ${target_cop:>15,.0f} COP (${target_usd:>10,.0f} USD)")
    print(f"  Time horizon:     {years:.1f} years")
    print(f"  Current savings:  ${current:>15,.0f} COP (${current/trm:>10,.0f} USD)")
    print(f"  Risk profile:     {args.risk.capitalize()} ({profile['real']*100:.0f}% expected real return)")
    print()

    print(f"  ── REQUIRED SAVINGS ──────────────────────────────────────────")
    print(f"  Monthly:  ${req_monthly:>12,.0f} COP (${req_monthly/trm:>8,.0f} USD)")
    print(f"  Annual:   ${req_monthly*12:>12,.0f} COP")
    print()

    if args.monthly_savings > 0 and status != "planning":
        print(f"  ── GAP ANALYSIS ──────────────────────────────────────────────")
        print(f"  Current monthly:  ${args.monthly_savings:>12,.0f} COP")
        print(f"  Projected value:  ${projected:>12,.0f} COP")
        if gap > 0:
            print(f"  Gap:              ${gap:>12,.0f} COP (BEHIND)")
        else:
            print(f"  Surplus:          ${abs(gap):>12,.0f} COP (ON TRACK)")
        print()

    print(f"  ── RETURN ANALYSIS ───────────────────────────────────────────")
    rr = required_return(target_cop, current, years, 0) * 100
    print(f"  Return needed (no contributions):     {rr:.1f}%")
    if req_return is not None:
        print(f"  Return needed (with current savings): {req_return*100:.1f}%")
    print()

    print(f"  ── MONTE CARLO ({args.simulations:,d} simulations) ─────────────────────")
    print(f"  Probability of success: {mc['probability_pct']:.1f}%")
    print(f"  P10 (pessimistic):  ${mc['p10']:>15,.0f}")
    print(f"  P25:                ${mc['p25']:>15,.0f}")
    print(f"  P50 (median):       ${mc['p50']:>15,.0f}")
    print(f"  P75:                ${mc['p75']:>15,.0f}")
    print(f"  P90 (optimistic):   ${mc['p90']:>15,.0f}")
    print()

    # Recommended profiles
    print(f"  ── SAVINGS BY RISK PROFILE ────────────────────────────────────")
    for rp, rv in RISK_RETURNS.items():
        ms = required_monthly_savings(target_cop, current, years, rv["real"])
        marker = " <<<" if rp == args.risk else ""
        print(f"  {rp.capitalize():<14s} ({rv['real']*100:.0f}% return): ${ms:>12,.0f} COP/month{marker}")


if __name__ == "__main__":
    main()
