#!/usr/bin/env python3
"""
Monthly budget planner for Colombian residents earning USD salary.

Allocates income across parafiscales, AFC/pension contributions,
tax savings fund, and living expenses.

Usage:
    python3 budget_planner.py --monthly-usd 8000 --year 2025
    python3 budget_planner.py --monthly-usd 8000 --year 2025 --deadline 2026-10-01
    python3 budget_planner.py --monthly-usd 8000 --year 2025 --parafiscales 2360000
"""


# --- Python version guard (PEP 604 union syntax requires >= 3.10) ---
import sys

if sys.version_info < (3, 10):
    raise SystemExit(
        f"finance-substrate requires Python >= 3.10. "
        f"Got {sys.version_info.major}.{sys.version_info.minor}. "
        f"Install via `brew install python@3.11` or `pyenv install 3.11 && pyenv local 3.11`."
    )
# --- end guard ---

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
DATA_DIR = Path.home() / ".finance-substrate"


def load_current_trm() -> float:
    """Get the most recent TRM from cache."""
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


def load_tax_tables(year: int) -> dict:
    tables_file = TEMPLATES_DIR / f"tax-tables-{year}.json"
    if not tables_file.exists():
        candidates = sorted(TEMPLATES_DIR.glob("tax-tables-*.json"), reverse=True)
        if candidates:
            tables_file = candidates[0]
        else:
            return {"uvt_value": 47065}
    with open(tables_file) as f:
        return json.load(f)


def calculate_tax(taxable_uvt: float, brackets: list) -> float:
    tax = 0.0
    for bracket in brackets:
        lower = bracket["from_uvt"]
        upper = bracket.get("to_uvt", float("inf"))
        rate = bracket["rate"]
        base_tax = bracket.get("base_tax_uvt", 0)
        if taxable_uvt > lower:
            taxable_in_bracket = min(taxable_uvt, upper) - lower
            tax = base_tax + (taxable_in_bracket * rate)
    return tax


def estimate_annual_tax(
    gross_annual_cop: float,
    ss_incr: float,
    afc_annual: float,
    vol_pension_annual: float,
    fixed_deductions: float,
    uvt: float,
    brackets: list,
) -> dict:
    """Quick tax estimate without full projection."""
    renta_liquida = max(0, gross_annual_cop - ss_incr - vol_pension_annual)
    exempt_25pct = min(renta_liquida * 0.25, 790 * uvt)
    total_exentas = afc_annual + exempt_25pct
    total_deducciones = fixed_deductions
    raw = total_exentas + total_deducciones
    cap = min(renta_liquida * 0.40, 1340 * uvt)
    limited = min(raw, cap)
    taxable = max(0, renta_liquida - limited)
    taxable_uvt = taxable / uvt
    tax_uvt = calculate_tax(taxable_uvt, brackets)
    tax_cop = tax_uvt * uvt
    anticipo = max(0, tax_cop * 0.75)
    return {
        "gross_annual": round(gross_annual_cop),
        "renta_liquida": round(renta_liquida),
        "exentas_limited": round(limited),
        "taxable": round(taxable),
        "tax": round(tax_cop),
        "anticipo_next": round(anticipo),
        "total_to_pay": round(tax_cop + anticipo),
    }


def main():
    parser = argparse.ArgumentParser(description="Monthly budget planner")
    parser.add_argument("--monthly-usd", type=float, required=True, help="Monthly salary in USD")
    parser.add_argument("--year", type=int, default=2025, help="Tax year")
    parser.add_argument("--parafiscales", type=float, default=2360000, help="Monthly PILA payment (COP)")
    parser.add_argument("--afc-annual", type=float, default=0, help="Annual AFC target (0 = auto from optimizer)")
    parser.add_argument("--vol-pension-annual", type=float, default=20000000, help="Annual voluntary pension")
    parser.add_argument("--fixed-deductions", type=float, default=4600000, help="Annual fixed deductions (medicina + GMF + e-inv)")
    parser.add_argument("--anticipo-anterior", type=float, default=0, help="Anticipo from prior year")
    parser.add_argument("--retenciones", type=float, default=1400000, help="Estimated annual retenciones")
    parser.add_argument("--deadline", type=str, default=None, help="Filing deadline date (YYYY-MM-DD), auto-computes months remaining")
    parser.add_argument("--months-to-deadline", type=int, default=12, help="Months until filing deadline (fallback if --deadline not given)")
    parser.add_argument("--trm", type=float, default=0, help="Override TRM rate (0 = use latest)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    # Resolve months to deadline: --deadline takes precedence over --months-to-deadline
    deadline_date = None
    if args.deadline:
        try:
            deadline_date = datetime.strptime(args.deadline, "%Y-%m-%d").date()
        except ValueError:
            print(f"Error: --deadline must be YYYY-MM-DD, got '{args.deadline}'", file=sys.stderr)
            sys.exit(1)
        today = date.today()
        if deadline_date <= today:
            print(f"Error: --deadline {args.deadline} is in the past", file=sys.stderr)
            sys.exit(1)
        months_remaining = (deadline_date.year - today.year) * 12 + (deadline_date.month - today.month)
        # Count partial months as a full month
        if today.day > 1 and deadline_date.day >= today.day:
            pass  # already counted
        months_remaining = max(1, months_remaining)
        args.months_to_deadline = months_remaining

    tables = load_tax_tables(args.year)
    uvt = tables.get("uvt_value", 47065)
    brackets = tables.get("brackets_renta", [])
    trm = args.trm if args.trm > 0 else load_current_trm()

    monthly_cop = args.monthly_usd * trm
    annual_cop = monthly_cop * 12

    # Social security INCR
    ss_monthly = args.parafiscales
    ss_annual = ss_monthly * 12

    # Auto-compute optimal AFC if not specified
    if args.afc_annual == 0:
        # Simplified optimizer: fill up to 1,340 UVT cap
        renta_liq = annual_cop - ss_annual - args.vol_pension_annual
        exempt_25 = min(renta_liq * 0.25, 790 * uvt)
        cap = min(renta_liq * 0.40, 1340 * uvt)
        headroom = max(0, cap - exempt_25 - args.fixed_deductions)
        afc_annual = min(headroom, annual_cop * 0.30, 3800 * uvt - args.vol_pension_annual)
        afc_annual = max(0, afc_annual)
    else:
        afc_annual = args.afc_annual

    afc_monthly = afc_annual / 12
    vol_pension_monthly = args.vol_pension_annual / 12

    # Tax estimate
    tax_est = estimate_annual_tax(
        annual_cop, ss_annual + args.vol_pension_annual,
        afc_annual, args.vol_pension_annual,
        args.fixed_deductions, uvt, brackets,
    )

    saldo_pagar = max(0, tax_est["tax"] + tax_est["anticipo_next"] - args.anticipo_anterior - args.retenciones)
    monthly_tax_savings = saldo_pagar / max(1, args.months_to_deadline)

    available = monthly_cop - ss_monthly - afc_monthly - vol_pension_monthly - monthly_tax_savings

    result = {
        "monthly_usd": args.monthly_usd,
        "trm": round(trm, 2),
        "monthly_cop": round(monthly_cop),
        "annual_cop": round(annual_cop),
        "uvt": uvt,
        "allocations": {
            "parafiscales": {"cop": round(ss_monthly), "usd": round(ss_monthly / trm), "pct": round(ss_monthly / monthly_cop * 100, 1)},
            "afc": {"cop": round(afc_monthly), "usd": round(afc_monthly / trm), "pct": round(afc_monthly / monthly_cop * 100, 1), "annual": round(afc_annual)},
            "vol_pension": {"cop": round(vol_pension_monthly), "usd": round(vol_pension_monthly / trm), "pct": round(vol_pension_monthly / monthly_cop * 100, 1), "annual": round(args.vol_pension_annual)},
            "tax_savings": {"cop": round(monthly_tax_savings), "usd": round(monthly_tax_savings / trm), "pct": round(monthly_tax_savings / monthly_cop * 100, 1), "total": round(saldo_pagar)},
            "available": {"cop": round(available), "usd": round(available / trm), "pct": round(available / monthly_cop * 100, 1)},
        },
        "tax_estimate": tax_est,
        "saldo_pagar": round(saldo_pagar),
        "months_to_deadline": args.months_to_deadline,
        "deadline": deadline_date.isoformat() if deadline_date else None,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    a = result["allocations"]
    print(f"\n{'='*65}")
    print(f"  PLAN PRESUPUESTAL MENSUAL — {args.year}")
    if deadline_date:
        print(f"  Fecha límite: {deadline_date.isoformat()}")
    print(f"{'='*65}")
    print(f"  Ingreso: ${args.monthly_usd:,.0f} USD × TRM {trm:,.2f} = ${monthly_cop:,.0f} COP")
    print(f"  UVT {args.year}: ${uvt:,.0f}")
    print()

    print(f"  {'Categoría':<30s} {'COP':>12s} {'USD':>8s} {'%':>6s}")
    print(f"  {'-'*58}")
    for name, label in [
        ("parafiscales", "Parafiscales PILA"),
        ("afc", f"AFC (${a['afc']['annual']:,.0f}/año)"),
        ("vol_pension", f"Pensión vol. (${a['vol_pension']['annual']:,.0f}/año)"),
        ("tax_savings", f"Ahorro renta (${a['tax_savings']['total']:,.0f} total)"),
        ("available", "** Disponible **"),
    ]:
        d = a[name]
        marker = ">>>" if name == "available" else "   "
        print(f"{marker} {label:<30s} ${d['cop']:>11,.0f} ${d['usd']:>7,.0f} {d['pct']:>5.1f}%")

    print(f"\n  {'─'*58}")
    print(f"    TOTAL                        ${monthly_cop:>11,.0f} ${args.monthly_usd:>7,.0f} 100.0%")

    print(f"\n  Impuesto estimado AG {args.year}: ${tax_est['tax']:,.0f}")
    print(f"  Anticipo siguiente: ${tax_est['anticipo_next']:,.0f}")
    print(f"  Saldo a pagar proyectado: ${saldo_pagar:,.0f}")
    print(f"  Meses para ahorrar: {args.months_to_deadline}")

    if args.months_to_deadline < 6:
        print(f"\n  ⚠ ALERTA: Plazo ajustado — solo {args.months_to_deadline} meses para acumular ${saldo_pagar:,.0f} COP")

    if available < 0:
        print(f"\n  ⚠ ALERTA: El presupuesto está en déficit por ${abs(available):,.0f} COP/mes")
        print(f"  Considere reducir AFC o pensión voluntaria.")


if __name__ == "__main__":
    main()
