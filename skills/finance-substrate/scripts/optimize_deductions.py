#!/usr/bin/env python3
"""
Deduction optimizer for Colombian persona natural (cedular system).

Finds the optimal AFC + voluntary pension contribution split to minimize
income tax on rentas de trabajo, subject to Estatuto Tributario constraints.

Constraints (post-Ley 2277/2022):
  1. AFC + voluntary pension combined <= 30% of gross income (Art. 126-1 + 126-4 ET)
  2. AFC + voluntary pension combined <= 3,800 UVT (Art. 126-1 ET)
  3. Total exentas + deducciones <= 40% of renta liquida (Art. 336 Num. 3)
  4. Total exentas + deducciones <= 1,340 UVT (Art. 336 Num. 3, Ley 2277/2022)
  5. 25% renta exenta <= 790 UVT/year (Art. 206 Num. 10, Ley 2277/2022)
  6. Voluntary pension permanence >= 10 years (Art. 126-1 ET)

Usage:
    python3 optimize_deductions.py --gross-income 285000000 --year 2024 \\
        --social-security-incr 49280000 --medicina-prepagada 4051404 \\
        --gmf 373290 --einvoice-1pct 326024

    python3 optimize_deductions.py --from-projection
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
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
PROJECTION_CACHE = Path.home() / ".finance-substrate" / "cache" / "last_projection.json"


# ════════════════════════════════════════════════════════════════════════════
# Tax table loading (reused from tax_projection.py)
# ════════════════════════════════════════════════════════════════════════════


def load_tax_tables(year: int) -> dict:
    """Load tax brackets from templates/tax-tables-YYYY.json."""
    tables_file = TEMPLATES_DIR / f"tax-tables-{year}.json"
    if not tables_file.exists():
        candidates = sorted(TEMPLATES_DIR.glob("tax-tables-*.json"), reverse=True)
        if not candidates:
            print("Error: No tax tables found in templates/", file=sys.stderr)
            sys.exit(1)
        tables_file = candidates[0]
        print(f"Warning: No tables for {year}, using {tables_file.name}", file=sys.stderr)
    with open(tables_file) as f:
        return json.load(f)


def calculate_tax(taxable_uvt: float, brackets: list) -> float:
    """Calculate tax in UVT using progressive bracket table (Art. 241 ET)."""
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


# ════════════════════════════════════════════════════════════════════════════
# Core optimizer
# ════════════════════════════════════════════════════════════════════════════


def compute_tax_for_contributions(
    gross_income: float,
    social_security_incr: float,
    afc: float,
    voluntary_pension: float,
    medicina_prepagada: float,
    gmf: float,
    einvoice_1pct: float,
    uvt: float,
    brackets: list,
) -> dict:
    """
    Compute total income tax for a given AFC + voluntary pension combination.

    Flow mirrors Form 210 rows R32-R42, R121 for rentas de trabajo only.
    """
    # R32: Ingresos brutos
    ingresos_brutos = gross_income

    # R33: INCR — social security is INCR; voluntary pension goes to R35 as exenta
    incr = social_security_incr

    # R34: Renta liquida
    renta_liquida = max(0, ingresos_brutos - incr)

    # ── Rentas exentas ───────────────────────────────────────────────
    # R35: AFC + voluntary pension (exenta, not INCR per Art. 126-1 ET)
    voluntary_contributions = afc + voluntary_pension

    # Constraint 1+2: Combined cap = min(30% gross, 3,800 UVT)
    cap_30pct = gross_income * 0.30
    cap_3800_uvt = 3800 * uvt
    contributions_cap = min(cap_30pct, cap_3800_uvt)
    voluntary_contributions_limited = min(voluntary_contributions, contributions_cap)

    # R36: 25% renta exenta (Art. 206 Num. 10)
    # Applied on renta liquida AFTER INCR but BEFORE other deductions
    exempt_25pct_raw = renta_liquida * 0.25
    exempt_25pct_cap = 790 * uvt  # Art. 206 Num. 10, Ley 2277/2022
    otras_rentas_exentas = min(exempt_25pct_raw, exempt_25pct_cap)

    # R37: Total rentas exentas
    total_rentas_exentas = voluntary_contributions_limited + otras_rentas_exentas

    # ── Deducciones ──────────────────────────────────────────────────
    # R39: Fixed deductions from certificates
    total_deducciones = medicina_prepagada + gmf + einvoice_1pct

    # ── R41: Global limitation (Art. 336 Num. 3) ────────────────────
    raw_exentas_deducciones = total_rentas_exentas + total_deducciones
    cap_40pct = renta_liquida * 0.40
    cap_1340_uvt = 1340 * uvt
    global_cap = min(cap_40pct, cap_1340_uvt)
    exentas_deduc_limitadas = min(raw_exentas_deducciones, global_cap)

    # R42: Renta liquida ordinaria
    renta_liq_ordinaria = max(0, renta_liquida - exentas_deduc_limitadas)

    # R121: Tax calculation
    taxable_uvt = renta_liq_ordinaria / uvt
    tax_uvt = calculate_tax(taxable_uvt, brackets)
    impuesto = tax_uvt * uvt

    return {
        "gross_income": gross_income,
        "incr": incr,
        "renta_liquida": renta_liquida,
        "afc": afc,
        "voluntary_pension": voluntary_pension,
        "voluntary_contributions_raw": voluntary_contributions,
        "voluntary_contributions_limited": voluntary_contributions_limited,
        "contributions_cap": contributions_cap,
        "exempt_25pct": otras_rentas_exentas,
        "total_rentas_exentas": total_rentas_exentas,
        "total_deducciones": total_deducciones,
        "raw_exentas_deducciones": raw_exentas_deducciones,
        "global_cap": global_cap,
        "exentas_deduc_limitadas": exentas_deduc_limitadas,
        "renta_liq_ordinaria": renta_liq_ordinaria,
        "taxable_uvt": taxable_uvt,
        "impuesto": impuesto,
        "at_global_cap": raw_exentas_deducciones >= global_cap,
    }


def optimize(
    gross_income: float,
    social_security_incr: float,
    medicina_prepagada: float,
    gmf: float,
    einvoice_1pct: float,
    uvt: float,
    brackets: list,
    step: int = 1_000_000,
) -> dict:
    """
    Search for optimal AFC + voluntary pension split to minimize tax.

    Strategy: iterate AFC from 0 to max in steps. For each AFC value,
    compute the max useful voluntary pension. Pick the combination with
    lowest tax.

    Since AFC and voluntary pension are fungible under the combined cap
    (Art. 126-1 + 126-4), the total amount matters more than the split.
    However, we search both dimensions because:
      - AFC is more liquid (can be withdrawn after 10 years OR for housing)
      - Voluntary pension has stricter permanence rules
      - The marginal benefit analysis helps the user decide the split
    """
    # Maximum combined AFC + voluntary pension
    cap_30pct = gross_income * 0.30
    cap_3800_uvt = 3800 * uvt
    max_combined = min(cap_30pct, cap_3800_uvt)

    # But the effective useful amount is bounded by the global 1,340 UVT cap
    # because additional contributions beyond what fills the global cap have
    # zero marginal tax benefit.
    renta_liquida = max(0, gross_income - social_security_incr)
    cap_40pct = renta_liquida * 0.40
    cap_1340_uvt = 1340 * uvt
    global_cap = min(cap_40pct, cap_1340_uvt)

    # Fixed deductions + 25% exenta eat into the global cap
    fixed_deductions = medicina_prepagada + gmf + einvoice_1pct
    exempt_25pct = min(renta_liquida * 0.25, 790 * uvt)

    # Effective headroom for AFC + voluntary pension
    headroom = max(0, global_cap - exempt_25pct - fixed_deductions)
    effective_max = min(max_combined, headroom)

    # If the combined cap is below the useful amount, we can still search up
    # to the combined cap (some might spill into non-deductible territory but
    # that's the user's choice for liquidity reasons).
    search_max = int(min(max_combined, effective_max + step))

    best = None
    results = []

    # Tax with ZERO voluntary contributions (baseline)
    baseline = compute_tax_for_contributions(
        gross_income, social_security_incr,
        0, 0, medicina_prepagada, gmf, einvoice_1pct,
        uvt, brackets,
    )

    # Search: since AFC and voluntary pension are interchangeable under the cap,
    # we search by total combined amount, then show split recommendations.
    for total in range(0, search_max + step, step):
        result = compute_tax_for_contributions(
            gross_income, social_security_incr,
            total, 0,  # Treat everything as AFC for now; split comes later
            medicina_prepagada, gmf, einvoice_1pct,
            uvt, brackets,
        )
        result["total_combined"] = total
        results.append(result)
        if best is None or result["impuesto"] < best["impuesto"]:
            best = result

    # Also check the exact effective_max value (may not align with step)
    for exact_point in [effective_max, max_combined, global_cap]:
        exact_int = int(round(exact_point))
        if exact_int > 0:
            result = compute_tax_for_contributions(
                gross_income, social_security_incr,
                exact_int, 0,
                medicina_prepagada, gmf, einvoice_1pct,
                uvt, brackets,
            )
            result["total_combined"] = exact_int
            results.append(result)
            if result["impuesto"] < best["impuesto"]:
                best = result

    # Sort results for marginal analysis
    results.sort(key=lambda r: r["total_combined"])

    # Remove duplicates by total_combined
    seen = set()
    unique_results = []
    for r in results:
        if r["total_combined"] not in seen:
            seen.add(r["total_combined"])
            unique_results.append(r)
    results = unique_results

    # Marginal benefit analysis
    marginal = []
    for i in range(1, len(results)):
        prev = results[i - 1]
        curr = results[i]
        delta_contribution = curr["total_combined"] - prev["total_combined"]
        delta_tax = prev["impuesto"] - curr["impuesto"]
        if delta_contribution > 0:
            marginal.append({
                "from_cop": prev["total_combined"],
                "to_cop": curr["total_combined"],
                "additional_contribution": delta_contribution,
                "tax_savings": round(delta_tax),
                "marginal_rate": round(delta_tax / delta_contribution * 100, 2) if delta_contribution else 0,
            })

    return {
        "baseline": baseline,
        "optimal": best,
        "max_combined_cap": max_combined,
        "global_cap_1340uvt": cap_1340_uvt,
        "effective_headroom": headroom,
        "effective_max_useful": effective_max,
        "marginal_analysis": marginal,
        "all_scenarios": results,
    }


# ════════════════════════════════════════════════════════════════════════════
# Output
# ════════════════════════════════════════════════════════════════════════════


def print_optimization_report(opt: dict, uvt: float, year: int):
    """Print human-readable optimization report."""
    baseline = opt["baseline"]
    best = opt["optimal"]
    savings = baseline["impuesto"] - best["impuesto"]

    print(f"\n{'='*74}")
    print(f"  DEDUCTION OPTIMIZER — Año Gravable {year}")
    print(f"{'='*74}")
    print(f"  UVT {year}: ${uvt:,.0f} COP")
    print()

    print(f"  ── INPUTS ─────────────────────────────────────────────────────")
    print(f"  Gross income (rentas de trabajo):   ${baseline['gross_income']:>18,.0f}")
    print(f"  Social security INCR:               ${baseline['incr']:>18,.0f}")
    print(f"  Renta liquida (R34):                ${baseline['renta_liquida']:>18,.0f}")
    print(f"  Medicina prepagada:                 ${baseline['total_deducciones'] - (best['total_deducciones'] - baseline['total_deducciones'] if False else 0):>18,.0f}")
    print(f"  Fixed deductions (med+gmf+einv):    ${baseline['total_deducciones']:>18,.0f}")
    print()

    print(f"  ── CAPS ───────────────────────────────────────────────────────")
    print(f"  AFC+Vol.pension cap (30%/3,800 UVT):${opt['max_combined_cap']:>18,.0f}")
    print(f"  Global cap (40%/1,340 UVT):         ${opt['global_cap_1340uvt']:>18,.0f}")
    print(f"  25% renta exenta (auto):            ${best['exempt_25pct']:>18,.0f}")
    print(f"  Effective headroom for AFC+VP:      ${opt['effective_headroom']:>18,.0f}")
    print(f"  Max useful contribution:            ${opt['effective_max_useful']:>18,.0f}")
    print()

    print(f"  ── BASELINE (no AFC/vol. pension) ─────────────────────────────")
    print(f"  Exentas+Deduc. (limited):           ${baseline['exentas_deduc_limitadas']:>18,.0f}")
    print(f"  Renta liq. ordinaria (R42):         ${baseline['renta_liq_ordinaria']:>18,.0f}")
    print(f"  Taxable UVT:                         {baseline['taxable_uvt']:>17,.1f}")
    print(f"  IMPUESTO (R121):                    ${baseline['impuesto']:>18,.0f}")
    print()

    print(f"  ── OPTIMAL RESULT ─────────────────────────────────────────────")
    print(f"  Optimal total AFC + vol. pension:   ${best['total_combined']:>18,.0f}")
    at_cap_note = "  ** AT GLOBAL CAP **" if best["at_global_cap"] else ""
    print(f"  Exentas+Deduc. (limited):           ${best['exentas_deduc_limitadas']:>18,.0f}{at_cap_note}")
    print(f"  Renta liq. ordinaria (R42):         ${best['renta_liq_ordinaria']:>18,.0f}")
    print(f"  Taxable UVT:                         {best['taxable_uvt']:>17,.1f}")
    print(f"  IMPUESTO (R121):                    ${best['impuesto']:>18,.0f}")
    print()
    print(f"  TAX SAVINGS:                        ${savings:>18,.0f}")
    if baseline["impuesto"] > 0:
        pct = savings / baseline["impuesto"] * 100
        print(f"  Savings rate:                        {pct:>17.1f}%")
    print()

    # Recommended split
    total = best["total_combined"]
    if total > 0:
        print(f"  ── RECOMMENDED SPLIT ──────────────────────────────────────────")
        print(f"  The total optimal contribution is ${total:,.0f}.")
        print(f"  AFC and voluntary pension are interchangeable under the combined")
        print(f"  cap (Art. 126-1 + 126-4 ET). Choose your split based on:")
        print(f"    - AFC: more liquid, 10-year lock or housing withdrawal")
        print(f"    - Vol. pension: 10-year lock, pension age, or housing/death/disability")
        print(f"  Both require permanence for the tax benefit to hold (Art. 126-1 ET).")
        # Suggest a balanced split
        suggested_afc = min(total, total // 2)
        suggested_vp = total - suggested_afc
        print(f"\n  Example balanced split:")
        print(f"    AFC:                              ${suggested_afc:>18,.0f}")
        print(f"    Voluntary pension:                ${suggested_vp:>18,.0f}")
        print(f"    Monthly AFC:                      ${suggested_afc / 12:>18,.0f}")
        print(f"    Monthly vol. pension:             ${suggested_vp / 12:>18,.0f}")
        print()

    # Marginal analysis
    marginals = opt["marginal_analysis"]
    useful_marginals = [m for m in marginals if m["tax_savings"] > 0]
    if useful_marginals:
        print(f"  ── MARGINAL BENEFIT ANALYSIS ──────────────────────────────────")
        print(f"  {'Contribution range':>30s}  {'+ Amount':>12s}  {'Tax saved':>12s}  {'Marginal %':>10s}")
        print(f"  {'─'*30}  {'─'*12}  {'─'*12}  {'─'*10}")
        for m in useful_marginals:
            rng = f"${m['from_cop']:,.0f} -> ${m['to_cop']:,.0f}"
            print(f"  {rng:>30s}  ${m['additional_contribution']:>11,.0f}  ${m['tax_savings']:>11,.0f}  {m['marginal_rate']:>9.1f}%")
        print()

    # Show where contributions stop being useful
    zero_marginals = [m for m in marginals if m["tax_savings"] == 0]
    if zero_marginals and zero_marginals[0]["from_cop"] <= opt["max_combined_cap"]:
        cutoff = zero_marginals[0]["from_cop"]
        print(f"  WARNING: Contributions above ${cutoff:,.0f} yield ZERO additional")
        print(f"  tax benefit (global 1,340 UVT cap reached). Any amount above")
        print(f"  this is purely for savings/investment purposes, not tax optimization.")
        print()

    if best["at_global_cap"]:
        print(f"  NOTE: You are at the 1,340 UVT global cap (${1340 * uvt:,.0f}).")
        print(f"  The cap is the binding constraint, not the 30%/3,800 UVT contribution limit.")
        print()


def load_from_projection() -> dict:
    """Load inputs from last tax projection cache."""
    if not PROJECTION_CACHE.exists():
        print(f"Error: No projection cache found at {PROJECTION_CACHE}", file=sys.stderr)
        print("Run tax_projection.py first, or provide --gross-income explicitly.", file=sys.stderr)
        sys.exit(1)
    with open(PROJECTION_CACHE) as f:
        proj = json.load(f)

    form = proj.get("form_210", {})
    rt = form.get("rentas_trabajo", {})
    dd = proj.get("deduction_detail", {})

    gross = rt.get("R32_ingresos_brutos", 0)
    incr = rt.get("R33_incr", 0)

    # Extract fixed deductions from the projection
    # R39 contains medicina_prepagada + gmf + einvoice_1pct already summed
    otras_deducciones = rt.get("R39_otras_deducciones", 0)

    return {
        "gross_income": gross,
        "social_security_incr": incr,
        "year": proj.get("year", 2024),
        "uvt": proj.get("uvt", 47065),
        # When loading from projection, we treat all fixed deductions as one lump
        "medicina_prepagada": otras_deducciones,
        "gmf": 0,
        "einvoice_1pct": 0,
    }


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Optimize AFC + voluntary pension contributions to minimize Colombian income tax.",
        epilog=(
            "Legal basis: Art. 126-1, 126-4, 206 Num. 10, 336 Num. 3 ET; Ley 2277/2022.\n"
            "This tool does NOT constitute tax advice. Consult a licensed contador."
        ),
    )
    parser.add_argument("--gross-income", type=float,
                        help="Annual gross income (rentas de trabajo) in COP")
    parser.add_argument("--year", type=int, default=2024,
                        help="Tax year (default: 2024)")
    parser.add_argument("--uvt", type=float,
                        help="Override UVT value (default: from tax tables)")
    parser.add_argument("--social-security-incr", type=float, default=0,
                        help="Total social security INCR (pension+salud+ARL+FSP) in COP")
    parser.add_argument("--medicina-prepagada", type=float, default=0,
                        help="Annual medicina prepagada deduction in COP")
    parser.add_argument("--gmf", type=float, default=0,
                        help="Annual GMF 50%% deduction in COP")
    parser.add_argument("--einvoice-1pct", type=float, default=0,
                        help="Annual e-invoice 1%% deduction in COP")
    parser.add_argument("--step", type=int, default=1_000_000,
                        help="Search step size in COP (default: 1,000,000)")
    parser.add_argument("--from-projection", action="store_true",
                        help="Load inputs from last tax projection output")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON instead of formatted report")
    args = parser.parse_args()

    if args.from_projection:
        inputs = load_from_projection()
        gross_income = inputs["gross_income"]
        social_security_incr = inputs["social_security_incr"]
        year = inputs["year"]
        uvt_override = inputs["uvt"]
        medicina_prepagada = inputs["medicina_prepagada"]
        gmf = inputs["gmf"]
        einvoice_1pct = inputs["einvoice_1pct"]
    else:
        if not args.gross_income:
            parser.error("--gross-income is required (or use --from-projection)")
        gross_income = args.gross_income
        social_security_incr = args.social_security_incr
        year = args.year
        uvt_override = args.uvt
        medicina_prepagada = args.medicina_prepagada
        gmf = args.gmf
        einvoice_1pct = args.einvoice_1pct

    tables = load_tax_tables(year)
    uvt = uvt_override or tables.get("uvt_value", 47065)
    brackets = tables.get("brackets_renta", [])

    opt = optimize(
        gross_income=gross_income,
        social_security_incr=social_security_incr,
        medicina_prepagada=medicina_prepagada,
        gmf=gmf,
        einvoice_1pct=einvoice_1pct,
        uvt=uvt,
        brackets=brackets,
        step=args.step,
    )

    if args.json:
        # Strip large scenario list for cleaner JSON output
        output = {
            "year": year,
            "uvt": uvt,
            "inputs": {
                "gross_income": gross_income,
                "social_security_incr": social_security_incr,
                "medicina_prepagada": medicina_prepagada,
                "gmf": gmf,
                "einvoice_1pct": einvoice_1pct,
            },
            "baseline_tax": round(opt["baseline"]["impuesto"]),
            "optimal": {
                "total_afc_plus_voluntary": round(opt["optimal"]["total_combined"]),
                "tax": round(opt["optimal"]["impuesto"]),
                "savings": round(opt["baseline"]["impuesto"] - opt["optimal"]["impuesto"]),
                "at_global_cap": opt["optimal"]["at_global_cap"],
            },
            "caps": {
                "combined_30pct_3800uvt": round(opt["max_combined_cap"]),
                "global_1340uvt": round(opt["global_cap_1340uvt"]),
                "effective_headroom": round(opt["effective_headroom"]),
                "effective_max_useful": round(opt["effective_max_useful"]),
            },
            "marginal_analysis": opt["marginal_analysis"],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_optimization_report(opt, uvt, year)


if __name__ == "__main__":
    main()
