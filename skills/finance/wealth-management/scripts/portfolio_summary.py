#!/usr/bin/env python3
"""
Portfolio health dashboard — descriptive analytics.

Aggregates holdings from finance-substrate (certificates, patrimonio, exogena)
and user portfolio data into a comprehensive wealth summary.

Usage:
    python3 portfolio_summary.py --year 2025
    python3 portfolio_summary.py --year 2025 --json
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

DATA_DIR = Path.home() / ".finance-substrate"
WM_DIR = Path.home() / ".wealth-management"
CERTS_FILE = DATA_DIR / "tax" / "certificates.jsonl"
EXOGENA_FILE = DATA_DIR / "tax" / "exogena.jsonl"
SALARY_FILE = DATA_DIR / "tax" / "salary-history.jsonl"

# Import patrimonio calculator from finance-substrate
FINANCE_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "finance-substrate" / "scripts"
if str(FINANCE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FINANCE_SCRIPTS))

try:
    from patrimonio_calc import compute_patrimonio
except ImportError:
    compute_patrimonio = None


@dataclass
class AssetClass:
    name: str
    value_cop: float = 0
    value_usd: float = 0
    pct: float = 0
    items: list = field(default_factory=list)


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


def load_certificates(year: int) -> list:
    if not CERTS_FILE.exists():
        return []
    certs = []
    with open(CERTS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("year") == year:
                certs.append(rec)
    return certs


def load_exogena(year: int) -> list:
    if not EXOGENA_FILE.exists():
        return []
    recs = []
    with open(EXOGENA_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("year") == year:
                recs.append(rec)
    return recs


def load_salary_summary(year: int) -> dict:
    if not SALARY_FILE.exists():
        return {"total_usd": 0, "total_cop": 0, "payments": 0, "avg_rate": 0}
    total_usd = 0
    total_cop = 0
    payments = 0
    rates = []
    with open(SALARY_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["date"].startswith(str(year)):
                total_usd += rec.get("amount_usd", 0)
                total_cop += rec.get("gross_cop", 0)
                payments += 1
                if rec.get("exchange_rate"):
                    rates.append(rec["exchange_rate"])
    return {
        "total_usd": total_usd,
        "total_cop": total_cop,
        "payments": payments,
        "avg_rate": sum(rates) / len(rates) if rates else 0,
    }


def load_user_portfolio() -> list:
    """Load user-maintained portfolio holdings."""
    portfolio_file = WM_DIR / "portfolio.json"
    if not portfolio_file.exists():
        return []
    with open(portfolio_file) as f:
        return json.load(f)


def classify_holdings(certs: list, exogena: list, user_portfolio: list, trm: float) -> dict:
    """Classify all holdings into asset classes."""
    classes = {
        "cash": AssetClass(name="Cash & Savings (COP)"),
        "cash_usd": AssetClass(name="Cash & Savings (USD)"),
        "fixed_income": AssetClass(name="Fixed Income (CDT, FIC, AFC)"),
        "equities": AssetClass(name="Equities (Stocks, Funds)"),
        "pension": AssetClass(name="Pension (Obligatoria + Voluntaria)"),
        "real_estate": AssetClass(name="Real Estate"),
        "other": AssetClass(name="Other"),
    }

    # From certificates
    for cert in certs:
        ts = cert.get("tax_summary", {})
        entity = cert.get("entity", "Unknown")

        # Bank accounts → cash
        cuenta = ts.get("patrimonio_cuenta", ts.get("patrimonio_cuentas", 0))
        if cuenta:
            classes["cash"].value_cop += cuenta
            classes["cash"].items.append({"entity": entity, "value": cuenta, "type": "cuenta bancaria"})

        # AFC → fixed income (tax-deferred)
        afc = ts.get("aportes_afc_r35", 0)
        if afc:
            classes["fixed_income"].value_cop += afc
            classes["fixed_income"].items.append({"entity": entity, "value": afc, "type": "AFC"})

        # Pension voluntaria → pension
        vol = ts.get("patrimonio_voluntaria", 0)
        if vol:
            classes["pension"].value_cop += vol
            classes["pension"].items.append({"entity": entity, "value": vol, "type": "pension voluntaria"})

        # Cesantías → pension
        ces = ts.get("patrimonio_cesantias", 0)
        if ces:
            classes["pension"].value_cop += ces
            classes["pension"].items.append({"entity": entity, "value": ces, "type": "cesantias"})

        # Acciones → equities
        acc = ts.get("patrimonio_acciones", 0)
        if acc:
            classes["equities"].value_cop += acc
            classes["equities"].items.append({"entity": entity, "value": acc, "type": "acciones"})

        # Fondos → equities
        fondos = ts.get("patrimonio_fondos", 0)
        if fondos:
            classes["equities"].value_cop += fondos
            classes["equities"].items.append({"entity": entity, "value": fondos, "type": "FIC"})

        # Deudas (negative)
        deuda = ts.get("deuda_patrimonio", 0)
        if deuda:
            classes["other"].value_cop -= deuda
            classes["other"].items.append({"entity": entity, "value": -deuda, "type": "deuda TC"})

    # From exogena
    for rec in exogena:
        detail = rec.get("detail", "").lower()
        value = rec.get("amount", rec.get("value", 0))
        reporter = rec.get("reporter_name", "")

        if "vehiculo" in detail or "avaluo" in detail:
            classes["real_estate"].value_cop += value
            classes["real_estate"].items.append({"entity": reporter, "value": value, "type": "vehiculo"})
        elif "cuenta" in detail and "cobrar" in detail and value > 10_000_000:
            # Large receivables (e.g. Marval real estate)
            if "marval" in reporter.lower():
                classes["real_estate"].value_cop += value
                classes["real_estate"].items.append({"entity": reporter, "value": value, "type": "inmueble"})
            else:
                classes["other"].value_cop += value
                classes["other"].items.append({"entity": reporter, "value": value, "type": "cuenta por cobrar"})
        elif "inversion" in detail or "fondo" in detail:
            classes["equities"].value_cop += value
            classes["equities"].items.append({"entity": reporter, "value": value, "type": "inversion"})

    # From user portfolio
    for holding in user_portfolio:
        cls = holding.get("asset_class", "other")
        value = holding.get("value_cop", holding.get("value_usd", 0) * trm)
        if cls in classes:
            classes[cls].value_cop += value
            classes[cls].items.append({
                "entity": holding.get("name", "User holding"),
                "value": value,
                "type": holding.get("type", "manual"),
            })

    # Compute totals and percentages
    total = sum(c.value_cop for c in classes.values())
    for c in classes.values():
        c.value_usd = round(c.value_cop / trm) if trm > 0 else 0
        c.pct = round(c.value_cop / total * 100, 1) if total > 0 else 0

    return {"classes": classes, "total_cop": total, "total_usd": round(total / trm)}


def main():
    parser = argparse.ArgumentParser(description="Portfolio health dashboard")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    trm = load_current_trm()
    certs = load_certificates(args.year)
    exogena = load_exogena(args.year)
    user_portfolio = load_user_portfolio()
    salary = load_salary_summary(args.year)

    holdings = classify_holdings(certs, exogena, user_portfolio, trm)
    classes = holdings["classes"]

    # Concentration risk
    concentration_warnings = []
    total = holdings["total_cop"]
    for cls_name, cls in classes.items():
        for item in cls.items:
            if total > 0 and item["value"] / total > 0.25:
                concentration_warnings.append({
                    "item": f"{item['entity']} ({item['type']})",
                    "value": item["value"],
                    "pct": round(item["value"] / total * 100, 1),
                })

    # Liquidity analysis
    liquid = classes["cash"].value_cop + classes["cash_usd"].value_cop
    monthly_expenses = salary["total_cop"] / 12 * 0.6 if salary["total_cop"] > 0 else 15_000_000
    liquid_months = liquid / monthly_expenses if monthly_expenses > 0 else 0

    # Currency exposure
    cop_exposure = sum(c.value_cop for name, c in classes.items() if name != "cash_usd")
    usd_exposure = classes["cash_usd"].value_cop

    result = {
        "year": args.year,
        "trm": round(trm, 2),
        "total_cop": round(total),
        "total_usd": holdings["total_usd"],
        "allocation": {name: {"value_cop": round(c.value_cop), "pct": c.pct, "items": len(c.items)}
                       for name, c in classes.items() if c.value_cop != 0},
        "concentration_warnings": concentration_warnings,
        "liquidity": {
            "liquid_cop": round(liquid),
            "monthly_expenses_est": round(monthly_expenses),
            "months_covered": round(liquid_months, 1),
        },
        "currency_exposure": {
            "cop_pct": round(cop_exposure / total * 100, 1) if total > 0 else 100,
            "usd_pct": round(usd_exposure / total * 100, 1) if total > 0 else 0,
        },
        "income": salary,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    # Human-readable
    print(f"\n{'='*70}")
    print(f"  PORTFOLIO SUMMARY — AG {args.year}")
    print(f"{'='*70}")
    print(f"  Net worth:   ${total:>15,.0f} COP (${total/trm:>10,.0f} USD)")
    print(f"  TRM:         {trm:,.2f}")
    if salary["total_usd"] > 0:
        print(f"  Income:      ${salary['total_usd']:>10,.0f} USD ({salary['payments']} payments)")
    print()

    print(f"  ── ASSET ALLOCATION ──────────────────────────────────────────")
    print(f"  {'Asset Class':<35s} {'Value (COP)':>15s} {'USD':>10s} {'%':>6s}")
    print(f"  {'-'*68}")
    for name, cls in sorted(classes.items(), key=lambda x: -x[1].value_cop):
        if cls.value_cop == 0 and not cls.items:
            continue
        print(f"  {cls.name:<35s} ${cls.value_cop:>14,.0f} ${cls.value_usd:>9,.0f} {cls.pct:>5.1f}%")
        for item in cls.items:
            print(f"    {item['entity'][:40]:<40s} ${item['value']:>12,.0f} ({item['type']})")
    print(f"  {'-'*68}")
    print(f"  {'TOTAL':<35s} ${total:>14,.0f} ${total/trm:>9,.0f} 100.0%")
    print()

    if concentration_warnings:
        print(f"  ── CONCENTRATION RISK ────────────────────────────────────────")
        for w in concentration_warnings:
            print(f"  WARNING: {w['item']} = {w['pct']}% of portfolio (>${total*0.25:,.0f})")
        print()

    print(f"  ── LIQUIDITY ─────────────────────────────────────────────────")
    print(f"  Liquid assets:       ${liquid:>12,.0f} COP")
    print(f"  Est. monthly expenses: ${monthly_expenses:>10,.0f} COP")
    print(f"  Months covered:      {liquid_months:>5.1f}")
    if liquid_months < 6:
        print(f"  WARNING: Emergency fund below 6-month target ({liquid_months:.1f} months)")
    print()

    print(f"  ── CURRENCY EXPOSURE ─────────────────────────────────────────")
    cop_pct = cop_exposure / total * 100 if total > 0 else 100
    usd_pct = usd_exposure / total * 100 if total > 0 else 0
    print(f"  COP: {cop_pct:>5.1f}%  |  USD: {usd_pct:>5.1f}%")


if __name__ == "__main__":
    main()
