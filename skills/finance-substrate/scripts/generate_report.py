#!/usr/bin/env python3
"""
Comprehensive financial report generator for Colombian persona natural.

Orchestrates tax_projection, budget_planner, patrimonio_calc, and
optimize_deductions into a single Markdown report suitable for
archival, advisor review, or DIAN filing preparation.

This is mode 13 (report) of the finance-substrate skill.

Usage:
    python3 generate_report.py --year 2025
    python3 generate_report.py --year 2025 --output ~/Dropbox/Declaracion/2025/financial-report-2025.md
    python3 generate_report.py --year 2025 --monthly-usd 8000 --anticipo 0
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
from datetime import date
from pathlib import Path

# ────────────────────────────────────────────────────────────────────
# Ensure sibling modules are importable
# ────────────────────────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tax_projection import (
    project_tax,
    load_salary,
    load_planillas,
    load_certificates_agg,
    load_tax_tables,
    SALARY_FILE,
    CERTS_FILE,
    EXOGENA_FILE,
    PLANILLAS_FILE,
)
from patrimonio_calc import compute_patrimonio, to_json as patrimonio_to_json
from optimize_deductions import optimize
from budget_planner import (
    load_current_trm,
    estimate_annual_tax,
    load_tax_tables as bp_load_tax_tables,
)

DATA_DIR = Path.home() / ".finance-substrate"
TRM_FILE = DATA_DIR / "fx" / "trm-history.jsonl"
PROJECTION_CACHE = DATA_DIR / "cache" / "last_projection.json"


# ════════════════════════════════════════════════════════════════════
# Data loaders (augment what the sibling modules provide)
# ════════════════════════════════════════════════════════════════════


def load_salary_detail(year: int) -> list[dict]:
    """Load individual monthly salary records for the detail table."""
    records = []
    if not SALARY_FILE.exists():
        return records
    with open(SALARY_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if not rec.get("date", "").startswith(str(year)):
                continue
            records.append(rec)
    records.sort(key=lambda r: r.get("date", ""))
    return records


def load_trm_stats(year: int) -> dict:
    """Compute TRM statistics for the year."""
    result = {"count": 0, "min": 0, "max": 0, "avg": 0, "latest": 0, "latest_date": ""}
    if not TRM_FILE.exists():
        return result
    rates = []
    latest = None
    with open(TRM_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rec_date = rec.get("date", "")
            if not rec_date.startswith(str(year)):
                continue
            val = rec.get("valor", 0)
            if val > 0:
                rates.append(val)
            if latest is None or rec_date > latest.get("date", ""):
                latest = rec
    if rates:
        result["count"] = len(rates)
        result["min"] = min(rates)
        result["max"] = max(rates)
        result["avg"] = sum(rates) / len(rates)
    if latest:
        result["latest"] = latest.get("valor", 0)
        result["latest_date"] = latest.get("date", "")
    return result


def count_jsonl_records(filepath: Path, year: int, year_key: str = "year") -> int:
    """Count records in a JSONL file for a given year."""
    if not filepath.exists():
        return 0
    count = 0
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                rec_year = rec.get(year_key)
                if rec_year == year:
                    count += 1
                elif isinstance(rec_year, str) and rec_year.startswith(str(year)):
                    count += 1
                # Also check "date" or "periodo" fields
                elif rec.get("date", "").startswith(str(year)):
                    count += 1
                elif str(rec.get("periodo", "")).startswith(str(year)):
                    count += 1
            except (json.JSONDecodeError, AttributeError):
                continue
    return count


def safe_get(d: dict, *keys, default=0) -> float:
    """Safely traverse nested dict keys, returning a numeric value."""
    current = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return float(default)
    if isinstance(current, (int, float)):
        return float(current)
    return float(default)


def fmt_cop(value: float) -> str:
    """Format COP value with $ prefix and comma separators."""
    if value is None or value == 0:
        return "$0"
    return f"${value:,.0f}"


def fmt_pct(value: float, decimals: int = 1) -> str:
    """Format percentage."""
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}%"


def month_name_es(month_num: int) -> str:
    """Return Spanish month name."""
    names = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
    }
    return names.get(month_num, f"Mes {month_num}")


# ════════════════════════════════════════════════════════════════════
# Core report generation
# ════════════════════════════════════════════════════════════════════


def generate_report(
    year: int,
    monthly_usd: float = 8000,
    anticipo_anterior: float = 0,
    retenciones_est: float = 1_400_000,
    parafiscales_monthly: float = 2_360_000,
    vol_pension_annual: float = 20_000_000,
    fixed_deductions: float = 4_600_000,
    nit_suffix: str | None = None,
    months_to_deadline: int = 12,
) -> str:
    """Generate complete financial report as Markdown string."""

    lines: list[str] = []

    def w(text: str = ""):
        lines.append(text)

    # ────────────────────────────────────────────────────────────────
    # 1. Run all computations
    # ────────────────────────────────────────────────────────────────

    # Tax projection
    try:
        projection = project_tax(year, anticipo_anterior=anticipo_anterior, nit_suffix=nit_suffix)
    except SystemExit:
        projection = None

    # Cache the projection for downstream tools
    if projection:
        cache_dir = DATA_DIR / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "last_projection.json").write_text(
            json.dumps(projection, indent=2, ensure_ascii=False)
        )

    # Prior year projection for YoY comparison
    try:
        prior_projection = project_tax(year - 1, anticipo_anterior=0)
    except (SystemExit, Exception):
        prior_projection = None

    # Salary detail
    salary_records = load_salary_detail(year)
    salary_agg = load_salary(year) if projection else {"total_usd": 0, "total_gross_cop": 0, "payments": 0, "avg_rate": 0}

    # Planillas
    planillas = load_planillas(year)
    prior_planillas = load_planillas(year - 1)

    # Certificates
    certs = load_certificates_agg(year)

    # TRM stats
    trm_stats = load_trm_stats(year)
    current_trm = load_current_trm()

    # Patrimonio
    try:
        patrimonio = compute_patrimonio(year)
        patrimonio_json = patrimonio_to_json(patrimonio)
    except Exception:
        patrimonio = None
        patrimonio_json = None

    # Prior year patrimonio for comparison
    try:
        prior_patrimonio = compute_patrimonio(year - 1)
    except Exception:
        prior_patrimonio = None

    # Deduction optimizer
    opt_result = None
    if projection:
        try:
            tables = load_tax_tables(year)
            uvt = tables.get("uvt_value", 47065)
            brackets = tables.get("brackets_renta", [])
            f210 = projection.get("form_210", {})
            rt = f210.get("rentas_trabajo", {})

            gross = rt.get("R32_ingresos_brutos", 0)
            incr = rt.get("R33_incr", 0)
            otras_ded = rt.get("R39_otras_deducciones", 0)

            opt_result = optimize(
                gross_income=gross,
                social_security_incr=incr,
                medicina_prepagada=otras_ded,
                gmf=0,
                einvoice_1pct=0,
                uvt=uvt,
                brackets=brackets,
            )
        except Exception:
            opt_result = None

    # Budget planner
    budget_result = None
    try:
        tables = bp_load_tax_tables(year)
        uvt = tables.get("uvt_value", 47065)
        brackets = tables.get("brackets_renta", [])
        trm = current_trm if current_trm > 0 else 4000.0

        monthly_cop = monthly_usd * trm
        annual_cop = monthly_cop * 12
        ss_annual = parafiscales_monthly * 12

        # Compute optimal AFC
        renta_liq = annual_cop - ss_annual - vol_pension_annual
        exempt_25 = min(renta_liq * 0.25, 790 * uvt)
        cap = min(renta_liq * 0.40, 1340 * uvt)
        headroom = max(0, cap - exempt_25 - fixed_deductions)
        afc_annual = min(headroom, annual_cop * 0.30, 3800 * uvt - vol_pension_annual)
        afc_annual = max(0, afc_annual)
        afc_monthly = afc_annual / 12
        vol_pension_monthly = vol_pension_annual / 12

        tax_est = estimate_annual_tax(
            annual_cop, ss_annual + vol_pension_annual,
            afc_annual, vol_pension_annual,
            fixed_deductions, uvt, brackets,
        )

        saldo_pagar = max(0, tax_est["tax"] + tax_est["anticipo_next"] - anticipo_anterior - retenciones_est)
        monthly_tax_savings = saldo_pagar / max(1, months_to_deadline)
        available = monthly_cop - parafiscales_monthly - afc_monthly - vol_pension_monthly - monthly_tax_savings

        budget_result = {
            "monthly_usd": monthly_usd,
            "trm": trm,
            "monthly_cop": monthly_cop,
            "annual_cop": annual_cop,
            "parafiscales_monthly": parafiscales_monthly,
            "afc_monthly": afc_monthly,
            "afc_annual": afc_annual,
            "vol_pension_monthly": vol_pension_monthly,
            "vol_pension_annual": vol_pension_annual,
            "monthly_tax_savings": monthly_tax_savings,
            "saldo_pagar": saldo_pagar,
            "available": available,
            "tax_est": tax_est,
        }
    except Exception:
        budget_result = None

    # ────────────────────────────────────────────────────────────────
    # 2. Assemble the report
    # ────────────────────────────────────────────────────────────────

    gen_date = date.today().isoformat()
    trm_display = f"{current_trm:,.2f}" if current_trm else "N/A"
    salary_count = len(salary_records)
    planillas_count = planillas.get("months", 0)
    certs_count = count_jsonl_records(CERTS_FILE, year)
    exogena_count = count_jsonl_records(EXOGENA_FILE, year)

    w(f"# Informe Financiero y Proyeccion Tributaria -- AG {year}")
    w()
    w(f"> Generado: {gen_date} | TRM vigente: ${trm_display} COP/USD")
    w(f"> Datos: {salary_count} pagos salariales, {planillas_count * 2} planillas PILA, {certs_count} certificados tributarios, {exogena_count} reportes exogena")
    w()
    w("---")
    w()

    # ── Section 1: Executive Summary ──────────────────────────────
    w("## Resumen Ejecutivo")
    w()

    curr_gross_usd = salary_agg.get("total_usd", 0)
    curr_gross_cop = safe_get(projection, "form_210", "rentas_trabajo", "R32_ingresos_brutos") if projection else 0
    curr_avg_rate = salary_agg.get("avg_rate", 0)
    curr_tax = safe_get(projection, "form_210", "impuesto", "R121_impuesto_rentas") if projection else 0
    curr_patrimonio = patrimonio.r31_patrimonio_liquido if patrimonio else 0

    prior_gross_usd = 0
    prior_gross_cop = 0
    prior_tax = 0
    prior_avg_rate = 0
    prior_patr = 0
    if prior_projection:
        prior_gross_cop = safe_get(prior_projection, "form_210", "rentas_trabajo", "R32_ingresos_brutos")
        prior_gross_usd = safe_get(prior_projection, "salary_detail", "total_usd")
        prior_tax = safe_get(prior_projection, "form_210", "impuesto", "R121_impuesto_rentas")
        prior_avg_rate = safe_get(prior_projection, "salary_detail", "avg_rate")
    if prior_patrimonio:
        prior_patr = prior_patrimonio.r31_patrimonio_liquido

    def yoy(current: float, prior: float) -> str:
        if prior and prior > 0 and current:
            delta = (current - prior) / prior * 100
            sign = "+" if delta >= 0 else ""
            return f"{sign}{delta:.1f}%"
        return "--"

    curr_tax = float(curr_tax) if curr_tax else 0
    curr_gross_cop = float(curr_gross_cop) if curr_gross_cop else 0
    prior_tax = float(prior_tax) if prior_tax else 0
    prior_gross_cop = float(prior_gross_cop) if prior_gross_cop else 0
    prior_gross_usd = float(prior_gross_usd) if prior_gross_usd else 0
    curr_gross_usd = float(curr_gross_usd) if curr_gross_usd else 0
    prior_avg_rate = float(prior_avg_rate) if prior_avg_rate else 0
    curr_avg_rate = float(curr_avg_rate) if curr_avg_rate else 0
    curr_eff_rate = (curr_tax / curr_gross_cop * 100) if curr_gross_cop > 0 else 0
    prior_eff_rate = (prior_tax / prior_gross_cop * 100) if prior_gross_cop > 0 else 0
    monthly_usd_avg = curr_gross_usd / max(1, salary_agg.get("payments", 1))

    w(f"| Indicador | AG {year - 1} | AG {year} (Proy.) | Delta |")
    w("|-----------|---------|-----------------|---|")
    w(f"| Ingreso bruto (USD) | {fmt_cop(prior_gross_usd) if prior_gross_usd else 'N/A'} | {fmt_cop(curr_gross_usd)} | {yoy(curr_gross_usd, prior_gross_usd)} |")
    w(f"| Ingreso bruto (COP) | {fmt_cop(prior_gross_cop) if prior_gross_cop else 'N/A'} | {fmt_cop(curr_gross_cop)} | {yoy(curr_gross_cop, prior_gross_cop)} |")
    w(f"| Salario mensual (USD) | {fmt_cop(prior_gross_usd / 12) if prior_gross_usd else 'N/A'} avg | {fmt_cop(monthly_usd_avg)} | {yoy(monthly_usd_avg, prior_gross_usd / 12 if prior_gross_usd else 0)} |")
    w(f"| TRM promedio ponderado | {prior_avg_rate:,.2f} | {curr_avg_rate:,.2f} | {yoy(curr_avg_rate, prior_avg_rate)} |")
    w(f"| Impuesto estimado | {fmt_cop(prior_tax) if prior_tax else 'N/A'} | {fmt_cop(curr_tax)} | {yoy(curr_tax, prior_tax)} |")
    w(f"| Tasa efectiva tributacion | {fmt_pct(prior_eff_rate) if prior_eff_rate else 'N/A'} | {fmt_pct(curr_eff_rate)} | -- |")
    w(f"| Patrimonio liquido | {fmt_cop(prior_patr) if prior_patr else 'N/A'} | {fmt_cop(curr_patrimonio) if curr_patrimonio else '~est.'} | {yoy(curr_patrimonio, prior_patr)} |")
    w()

    # Key changes
    w(f"### Cambios clave respecto a {year - 1}")
    w()
    if curr_gross_usd > 0 and prior_gross_usd > 0:
        salary_delta = (curr_gross_usd - prior_gross_usd) / prior_gross_usd * 100
        w(f"1. **Variacion salarial del {salary_delta:+.1f}%** -- de ~${prior_gross_usd / 12:,.0f}/mes a ~${monthly_usd_avg:,.0f}/mes USD")
    else:
        w(f"1. **Ingreso bruto AG {year}:** {fmt_cop(curr_gross_usd)} USD ({salary_count} pagos)")

    if trm_stats["count"] > 0:
        trm_change = (trm_stats["min"] - trm_stats["max"]) / trm_stats["max"] * 100 if trm_stats["max"] else 0
        w(f"2. **TRM rango {year}:** ${trm_stats['max']:,.0f} (max) a ${trm_stats['min']:,.0f} (min), variacion {trm_change:+.1f}% YTD")
    else:
        w(f"2. **TRM:** Datos no disponibles para {year}")

    if projection:
        renta_grav = safe_get(projection, "form_210", "cedula_general", "R93_renta_grav_cedula_gen")
        w(f"3. **Base gravable:** Renta liquida gravable cedula general = {fmt_cop(renta_grav)}")
    else:
        w(f"3. **Proyeccion tributaria:** No disponible (datos insuficientes)")

    w(f"4. **Patrimonio:** R31 = {fmt_cop(curr_patrimonio) if curr_patrimonio else 'pendiente calculo'}")
    w()
    w("---")
    w()

    # ── Section 2: Monthly Salary Detail ─────────────────────────
    w("## 1. Ingresos -- Detalle Mensual")
    w()

    if salary_records:
        w(f"### Salario {year} (Foreign Services)")
        w()
        w("| Mes | USD | TRM | Bruto COP | Variacion TRM |")
        w("|-----|-----|-----|-----------|---------------|")

        prev_rate = None
        for rec in salary_records:
            rec_date = rec.get("date", "")
            try:
                month_num = int(rec_date.split("-")[1])
                month_label = month_name_es(month_num)
            except (IndexError, ValueError):
                month_label = rec_date[:7]

            usd = rec.get("amount_usd", 0)
            rate = rec.get("exchange_rate", 0)
            gross_cop = rec.get("gross_cop", 0)

            if prev_rate and prev_rate > 0:
                trm_var = (rate - prev_rate) / prev_rate * 100
                trm_var_str = f"{trm_var:+.1f}%"
            else:
                trm_var_str = "--"

            w(f"| {month_label} | ${usd:,.0f} | {rate:,.2f} | {fmt_cop(gross_cop)} | {trm_var_str} |")
            prev_rate = rate

        # Total row
        total_usd = salary_agg.get("total_usd", 0)
        total_cop = salary_agg.get("total_gross_cop", 0)
        avg_rate = salary_agg.get("avg_rate", 0)
        if trm_stats["count"] > 0 and trm_stats["max"] > 0:
            ytd_var = (trm_stats["min"] - trm_stats["max"]) / trm_stats["max"] * 100
            ytd_str = f"{ytd_var:+.1f}% YTD"
        else:
            ytd_str = "--"
        w(f"| **TOTAL** | **${total_usd:,.0f}** | **{avg_rate:,.2f} avg** | **{fmt_cop(total_cop)}** | **{ytd_str}** |")
        w()
    else:
        w(f"*No hay datos salariales disponibles para AG {year}.*")
        w()

    # Capital income
    if certs:
        rend_grav = certs.get("rendimientos_gravados", 0)
        rend_no_grav = certs.get("rendimientos_no_gravados", 0)
        rend_vol = certs.get("rendimientos_voluntaria", 0)
        rend_ces = certs.get("rendimientos_cesantias", 0)
        total_rend = rend_grav + rend_no_grav + rend_vol + rend_ces
        if total_rend > 0:
            w("### Rentas de capital")
            w()
            w("| Concepto | COP | Fuente |")
            w("|----------|-----|--------|")
            if rend_grav:
                w(f"| Rendimientos financieros (gravados) | {fmt_cop(rend_grav)} | Certificados |")
            if rend_no_grav:
                w(f"| Rendimientos financieros (no gravados) | {fmt_cop(rend_no_grav)} | Certificados |")
            if rend_vol:
                w(f"| Rendimientos pension voluntaria | {fmt_cop(rend_vol)} | Certificados |")
            if rend_ces:
                w(f"| Rendimientos cesantias | {fmt_cop(rend_ces)} | Certificados |")
            w(f"| **Total rentas de capital bruto** | **{fmt_cop(total_rend)}** | |")
            if rend_no_grav:
                w(f"| INCR (componente inflacionario) | -{fmt_cop(rend_no_grav)} | Art. 40-1 ET |")
                w(f"| **Renta capital gravable** | **{fmt_cop(total_rend - rend_no_grav)}** | |")
            w()

    w("---")
    w()

    # ── Section 3: Social Security (PILA) ────────────────────────
    w("## 2. Seguridad Social -- Parafiscales PILA")
    w()

    if planillas and planillas.get("months", 0) > 0:
        p = planillas
        ibc_monthly = 8_000_000  # Standard IBC
        w(f"Cotizacion como **independiente** con IBC = ${ibc_monthly:,.0f} COP/mes.")
        w()
        w("| Concepto | Mensual (COP) | Anual {year} | % del IBC |".format(year=year))
        w("|----------|---------------|------------|-----------|")

        months = p["months"]
        salud_m = p["salud"] / months if months else 0
        pension_m = p["pension"] / months if months else 0
        arl_m = p["arl"] / months if months else 0
        fsp_m = p["fsp"] / months if months else 0
        total_m = p["total"] / months if months else 0

        w(f"| Salud (EPS) | {fmt_cop(salud_m)} | {fmt_cop(p['salud'])} | {salud_m / ibc_monthly * 100:.1f}% |")
        w(f"| Pension obligatoria | {fmt_cop(pension_m)} | {fmt_cop(p['pension'])} | {pension_m / ibc_monthly * 100:.1f}% |")
        w(f"| ARL (Nivel I) | {fmt_cop(arl_m)} | {fmt_cop(p['arl'])} | {arl_m / ibc_monthly * 100:.1f}% |")
        w(f"| FSP (Solidaridad + Subsistencia) | {fmt_cop(fsp_m)} | {fmt_cop(p['fsp'])} | {fsp_m / ibc_monthly * 100:.1f}% |")
        w(f"| **Total PILA** | **{fmt_cop(total_m)}** | **{fmt_cop(p['total'])}** | **{total_m / ibc_monthly * 100:.1f}%** |")
        w()

        # YoY comparison
        if prior_planillas and prior_planillas.get("months", 0) > 0:
            pp = prior_planillas
            w(f"### Comparativo PILA {year - 1} vs {year}")
            w()
            w(f"| | {year - 1} | {year} | Delta |")
            w("|---|------|------|---|")
            w(f"| Meses pagados | {pp['months']} | {p['months']} | {'+' if p['months'] >= pp['months'] else ''}{p['months'] - pp['months']} |")
            w(f"| Total anual | {fmt_cop(pp['total'])} | {fmt_cop(p['total'])} | {yoy(p['total'], pp['total'])} |")
            w(f"| IBC mensual | ${ibc_monthly:,.0f} | ${ibc_monthly:,.0f} | = |")
            w()
    else:
        w(f"*No hay datos de planillas PILA disponibles para AG {year}.*")
        w()

    w("---")
    w()

    # ── Section 4: Patrimonio Breakdown ──────────────────────────
    w(f"## 3. Patrimonio (R29-R31) -- AG {year}")
    w()

    if patrimonio and patrimonio_json:
        pj = patrimonio_json
        r29 = pj["form_210"]["R29_patrimonio_bruto"]
        r30 = pj["form_210"]["R30_deudas"]
        r31 = pj["form_210"]["R31_patrimonio_liquido"]

        # Assets
        w(f"### Activos (R29): {fmt_cop(r29)}")
        w()
        w("| Categoria | Entidad | Valor (COP) | Fuente |")
        w("|-----------|---------|-------------|--------|")
        for asset in pj.get("assets", []):
            name = asset.get("name", "")
            value = asset.get("value", 0)
            source = asset.get("source", "")
            entity_part = asset.get("entity", "")
            # Extract category label
            cat = asset.get("category", "otros")
            overlap_note = " *" if asset.get("overlap") else ""
            w(f"| {cat.replace('_', ' ').title()} | {entity_part[:30]} | {fmt_cop(value)}{overlap_note} | {source.title()} |")
        w()

        # Debts
        w(f"### Deudas (R30): {fmt_cop(r30)}")
        w()
        if pj.get("debts"):
            w("| Concepto | Entidad | Valor (COP) |")
            w("|----------|---------|-------------|")
            for debt in pj["debts"]:
                w(f"| {debt.get('name', '')[:40]} | {debt.get('entity', '')[:25]} | {fmt_cop(debt.get('value', 0))} |")
            w()
        else:
            w("*(Ninguna deuda registrada)*")
            w()

        w(f"### Patrimonio liquido (R31): {fmt_cop(r31)}")
        w()

        if pj.get("overlaps"):
            w(f"> **Solapamientos detectados ({len(pj['overlaps'])}):** Se aplicaron reglas de deduplicacion entre certificados y exogena. Revisar detalle con `patrimonio_calc.py --detail`.")
            w()
    else:
        w(f"*Datos de patrimonio no disponibles para AG {year}. Ejecutar `patrimonio_calc.py --year {year}` cuando los datos esten completos.*")
        w()

    w("---")
    w()

    # ── Section 5: Form 210 Projection ───────────────────────────
    w(f"## 4. Declaracion de Renta Proyectada -- Form 210 AG {year}")
    w()

    if projection:
        f210 = projection["form_210"]
        uvt_val = projection.get("uvt", 0)
        rt = f210["rentas_trabajo"]
        rc = f210["rentas_capital"]
        cg = f210["cedula_general"]
        imp = f210["impuesto"]
        dd = projection.get("deduction_detail", {})

        w(f"### Cedula de rentas de trabajo (R32-R42)")
        w()
        w("| Casilla | Concepto | Valor (COP) | Base legal |")
        w("|---------|----------|-------------|------------|")
        w(f"| R32 | Ingresos brutos | {fmt_cop(rt['R32_ingresos_brutos'])} | Art. 103 ET |")
        w(f"| R33 | INCR (aportes obligatorios) | {fmt_cop(rt['R33_incr'])} | Art. 55-56 ET |")
        w(f"| R34 | Renta liquida de trabajo | {fmt_cop(rt['R34_renta_liquida'])} | R32 - R33 |")
        w(f"| R35 | Aportes AFC + vol. pension | {fmt_cop(rt['R35_aportes_afc'])} | Art. 126-1, 126-4 ET |")
        w(f"| R36 | Otras rentas exentas (25%) | {fmt_cop(rt['R36_otras_rentas_exentas'])} | Art. 206 Num. 10 ET |")
        w(f"| R37 | Total rentas exentas | {fmt_cop(rt['R37_total_rentas_exentas'])} | R35 + R36 |")
        w(f"| R38 | Intereses credito vivienda | {fmt_cop(rt['R38_intereses_vivienda'])} | Art. 119 ET |")
        w(f"| R39 | Otras deducciones | {fmt_cop(rt['R39_otras_deducciones'])} | Art. 387, 115, 336.5 ET |")
        w(f"| R40 | Total deducciones | {fmt_cop(rt['R40_total_deducciones'])} | |")
        w(f"| R41 | Exentas + Deduc. (limitadas) | {fmt_cop(rt['R41_exentas_deduc_limitadas'])} | Min(R37+R40, 40%xR34, 1340 UVT) |")
        w(f"| R42 | Renta liquida ordinaria | {fmt_cop(rt['R42_renta_liq_ordinaria'])} | R34 - R41 |")
        w()

        # Deduction detail
        if rt["R39_otras_deducciones"] > 0:
            w("### Detalle de deducciones (R39)")
            w()
            w("| Concepto | Valor (COP) | Base legal |")
            w("|----------|-------------|------------|")
            med_prep = certs.get("medicina_prepagada_r39", 0)
            gmf_ded = certs.get("gmf_deducible", 0)
            einv = projection.get("einvoices", {}).get("deduccion_1pct", 0)
            if med_prep:
                w(f"| Medicina prepagada | {fmt_cop(med_prep)} | Art. 387 ET (16 UVT/mes cap) |")
            if gmf_ded:
                w(f"| GMF deducible 50% | {fmt_cop(gmf_ded)} | Art. 115 ET |")
            if einv:
                w(f"| E-invoicing 1% | {fmt_cop(einv)} | Art. 336 Num. 5 ET |")
            w(f"| **Total R39** | **{fmt_cop(rt['R39_otras_deducciones'])}** | |")
            w()

        # Rentas de capital
        w("### Cedula de rentas de capital (R58-R73)")
        w()
        w("| Casilla | Concepto | Valor (COP) |")
        w("|---------|----------|-------------|")
        w(f"| R58 | Ingresos brutos capital | {fmt_cop(rc['R58_ingresos_brutos'])} |")
        w(f"| R59 | INCR capital (inflacionario) | {fmt_cop(rc['R59_incr'])} |")
        w(f"| R61 | Renta liquida capital | {fmt_cop(rc['R61_renta_liquida'])} |")
        w(f"| R73 | Renta gravable capital | {fmt_cop(rc['R73_renta_gravable'])} |")
        w()

        # Cedula general
        w("### Cedula general (R91-R97)")
        w()
        w("| Casilla | Concepto | Valor (COP) |")
        w("|---------|----------|-------------|")
        w(f"| R91 | Renta liquida cedula general | {fmt_cop(cg['R91_renta_liquida'])} |")
        w(f"| R92 | Exentas + deducciones limitadas | {fmt_cop(cg['R92_exentas_ded_limitadas'])} |")
        w(f"| R93 | Renta gravable cedula general | {fmt_cop(cg['R93_renta_grav_cedula_gen'])} |")
        w(f"| R97 | Renta gravable total | {fmt_cop(cg['R93_renta_grav_cedula_gen'])} ({cg.get('renta_grav_uvt', 0):,.1f} UVT) |")
        w()

        # Tax liquidation
        w("### Liquidacion del impuesto (R121-R136)")
        w()
        w("| Casilla | Concepto | Valor (COP) |")
        w("|---------|----------|-------------|")
        w(f"| R121 | Impuesto sobre rentas | {fmt_cop(imp['R121_impuesto_rentas'])} |")
        w(f"| R126 | Impuesto neto | {fmt_cop(imp['R126_impuesto_neto'])} |")
        w(f"| R129 | Total impuesto a cargo | {fmt_cop(imp['R129_total_impuesto_cargo'])} |")
        w(f"| R130 | Anticipo anterior (AG {year - 1}) | {fmt_cop(imp['R130_anticipo_anterior'])} |")
        w(f"| R132 | Retenciones {year} | {fmt_cop(imp['R132_retenciones'])} |")
        w(f"| R133 | Anticipo siguiente (AG {year + 1}) | {fmt_cop(imp['R133_anticipo_siguiente'])} |")
        saldo = imp.get("R134_saldo_pagar", 0)
        saldo_favor = imp.get("R137_total_saldo_favor", 0)
        if saldo > 0:
            w(f"| **R134** | **SALDO A PAGAR** | **{fmt_cop(saldo)}** |")
        if saldo_favor > 0:
            w(f"| **R137** | **SALDO A FAVOR** | **{fmt_cop(saldo_favor)}** |")
        w()

        # Effective rate
        w("### Tasa efectiva")
        w()
        w("| Metrica | Valor |")
        w("|---------|-------|")
        eff_rate_brutos = (imp["R121_impuesto_rentas"] / rt["R32_ingresos_brutos"] * 100) if rt["R32_ingresos_brutos"] else 0
        eff_rate_liq = (imp["R121_impuesto_rentas"] / rt["R34_renta_liquida"] * 100) if rt["R34_renta_liquida"] else 0
        monthly_salary_cop = rt["R32_ingresos_brutos"] / 12 if rt["R32_ingresos_brutos"] else 1
        months_salary = saldo / monthly_salary_cop if saldo and monthly_salary_cop else 0
        saldo_usd = saldo / current_trm if current_trm and saldo else 0
        w(f"| Impuesto / Ingresos brutos | {fmt_pct(eff_rate_brutos)} |")
        w(f"| Impuesto / Renta liquida | {fmt_pct(eff_rate_liq)} |")
        w(f"| Saldo a pagar / Ingreso mensual | {months_salary:.1f} meses de salario |")
        w(f"| Saldo a pagar en USD (TRM {current_trm:,.0f}) | ~${saldo_usd:,.0f} USD |")
        w()

        # Deduction caps detail
        w("### Detalle de topes de deducciones")
        w()
        w("```")
        w(f"Rentas exentas + deducciones:       {fmt_cop(dd.get('raw_exentas_deducciones', 0))}  (raw)")
        w(f"Cap 40% de renta liquida:           {fmt_cop(dd.get('cap_40pct_of_R34', 0))}")
        cap_1340 = dd.get("cap_1340uvt", 0)
        applied = dd.get("applied_cap", 0)
        binding = "BINDING" if applied == cap_1340 and cap_1340 > 0 else ""
        w(f"Cap 1,340 UVT (Art. 336):           {fmt_cop(cap_1340)}  {f'<- {binding} CONSTRAINT' if binding else ''}")
        w(f"Aplicado (R41):                     {fmt_cop(applied)}")
        w("```")
        w()
    else:
        w(f"*Proyeccion tributaria no disponible para AG {year}. Datos insuficientes.*")
        w()

    w("---")
    w()

    # ── Section 6: Deduction Optimization ────────────────────────
    w("## 5. Analisis de Optimizacion Fiscal")
    w()

    curr_afc = 0.0
    if opt_result and projection:
        baseline = opt_result["baseline"]
        optimal = opt_result["optimal"]
        savings = baseline["impuesto"] - optimal["impuesto"]

        w("### Estado actual de las deducciones")
        w()
        w("```")
        raw = safe_get(projection, "deduction_detail", "raw_exentas_deducciones")
        cap_40 = safe_get(projection, "deduction_detail", "cap_40pct_of_R34")
        cap_1340 = safe_get(projection, "deduction_detail", "cap_1340uvt")
        applied = safe_get(projection, "deduction_detail", "applied_cap")
        w(f"Rentas exentas + deducciones:       {fmt_cop(raw)}  (raw)")
        w(f"Cap 40% de renta liquida:           {fmt_cop(cap_40)}")
        binding_str = "<- BINDING CONSTRAINT" if applied == cap_1340 and cap_1340 > 0 else ""
        w(f"Cap 1,340 UVT (Art. 336):           {fmt_cop(cap_1340)}  {binding_str}")
        w(f"Aplicado (R41):                     {fmt_cop(applied)}")
        w("```")
        w()

        w("### Analisis de contribuciones optimas")
        w()
        w("| Escenario | AFC + Vol. Pension | Impuesto | Ahorro vs. base |")
        w("|-----------|-------------------|----------|-----------------|")
        w(f"| Sin aportes voluntarios | $0 | {fmt_cop(baseline['impuesto'])} | -- |")

        # Current state from projection
        curr_afc = safe_get(projection, "form_210", "rentas_trabajo", "R35_aportes_afc")
        curr_tax_imp = safe_get(projection, "form_210", "impuesto", "R121_impuesto_rentas")
        if curr_afc > 0:
            w(f"| Actual ({fmt_cop(curr_afc)}) | {fmt_cop(curr_afc)} | {fmt_cop(curr_tax_imp)} | -- |")

        opt_total = optimal.get("total_combined", 0)
        w(f"| **Optimo (max. util)** | **{fmt_cop(opt_total)}** | **{fmt_cop(optimal['impuesto'])}** | **{fmt_cop(savings)}** |")
        w()

        if opt_total > 0 and curr_afc > opt_total:
            excess = curr_afc - opt_total
            w(f"> **Insight:** Los aportes actuales ({fmt_cop(curr_afc)}) **exceden** el maximo util ({fmt_cop(opt_total)}) en {fmt_cop(excess)}. El excedente no genera beneficio tributario adicional (el cap de 1,340 UVT ya esta saturado). Ese excedente es ahorro puro -- bueno para patrimonio, pero sin efecto fiscal.")
            w()

        # Marginal analysis
        useful_marginals = [m for m in opt_result.get("marginal_analysis", []) if m["tax_savings"] > 0]
        if useful_marginals:
            w("### Beneficio marginal por tramo")
            w()
            w("| Rango contribucion | Monto adicional | Ahorro fiscal | Tasa marginal |")
            w("|-------------------|-----------------|---------------|---------------|")
            for m in useful_marginals:
                w(f"| {fmt_cop(m['from_cop'])} -> {fmt_cop(m['to_cop'])} | {fmt_cop(m['additional_contribution'])} | {fmt_cop(m['tax_savings'])} | {m['marginal_rate']:.1f}% |")
            w()

        if optimal.get("at_global_cap"):
            w(f"> **Nota:** Se alcanza el tope global de 1,340 UVT ({fmt_cop(1340 * projection.get('uvt', 47065))}). El tope es la restriccion vinculante, no el limite de 30%/3,800 UVT de contribuciones.")
            w()
    else:
        w(f"*Analisis de optimizacion no disponible. Ejecutar `optimize_deductions.py --from-projection` despues de la proyeccion.*")
        w()

    w("---")
    w()

    # ── Section 7: Monthly Budget Plan ───────────────────────────
    w(f"## 6. Plan Presupuestal Mensual {year}")
    w()

    if budget_result:
        b = budget_result
        trm = b["trm"]
        mcop = b["monthly_cop"]

        w(f"Basado en ${b['monthly_usd']:,.0f} USD/mes x TRM {trm:,.2f} = {fmt_cop(mcop)} COP/mes")
        w()
        w("| Categoria | COP/mes | USD/mes | % Ingreso |")
        w("|-----------|---------|---------|-----------|")

        items = [
            ("Parafiscales PILA", b["parafiscales_monthly"]),
            (f"AFC ({fmt_cop(b['afc_annual'])}/ano)", b["afc_monthly"]),
            (f"Pension voluntaria ({fmt_cop(b['vol_pension_annual'])}/ano)", b["vol_pension_monthly"]),
            (f"Ahorro para renta", b["monthly_tax_savings"]),
        ]
        for label, cop_val in items:
            usd_val = cop_val / trm if trm else 0
            pct = cop_val / mcop * 100 if mcop else 0
            w(f"| {label} | {fmt_cop(cop_val)} | ${usd_val:,.0f} | {pct:.1f}% |")

        avail = b["available"]
        avail_usd = avail / trm if trm else 0
        avail_pct = avail / mcop * 100 if mcop else 0
        w(f"| **Disponible** | **{fmt_cop(avail)}** | **${avail_usd:,.0f}** | **{avail_pct:.1f}%** |")
        w()

        # Distribution bar
        w("### Distribucion visual")
        w()
        w("```")
        bar_width = 40
        for label, val in [
            ("PILA", b["parafiscales_monthly"]),
            (" AFC", b["afc_monthly"]),
            (" Vol", b["vol_pension_monthly"]),
            ("Rent", b["monthly_tax_savings"]),
            ("Disp", b["available"]),
        ]:
            pct = val / mcop * 100 if mcop else 0
            filled = max(0, int(bar_width * pct / 100))
            bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
            w(f"{label:>5s} {bar} {pct:5.1f}%")
        w("```")
        w()

        # Tax savings fund
        w("### Fondo de ahorro para renta")
        w()
        w("| Concepto | Valor |")
        w("|----------|-------|")
        saldo_to_pay = b["saldo_pagar"]
        w(f"| Saldo a pagar estimado | {fmt_cop(saldo_to_pay)} |")
        w(f"| (-) Anticipo anterior | {fmt_cop(anticipo_anterior)} |")
        w(f"| (-) Retenciones acreditables | {fmt_cop(retenciones_est)} |")
        effective_cash = max(0, saldo_to_pay)
        w(f"| = Efectivo requerido | {fmt_cop(effective_cash)} |")
        w(f"| Meses para ahorrar | {months_to_deadline} |")
        w(f"| **Ahorro mensual necesario** | **{fmt_cop(b['monthly_tax_savings'])}** |")
        w()

        if avail < 0:
            w(f"> **ALERTA:** El presupuesto esta en deficit por {fmt_cop(abs(avail))} COP/mes. Considere reducir AFC o pension voluntaria.")
            w()
    else:
        w(f"*Datos insuficientes para generar plan presupuestal. Especificar --monthly-usd.*")
        w()

    w("---")
    w()

    # ── Section 8: Calendar and Next Actions ─────────────────────
    w("## 7. Calendario y Proximas Acciones")
    w()

    filing_year = year + 1
    w(f"### Fechas clave -- AG {year}")
    w()
    w("| Fecha | Obligacion | Estado |")
    w("|-------|-----------|--------|")
    w(f"| Ene-Mar {filing_year} | Recopilar certificados tributarios de todas las instituciones | Pendiente |")
    w(f"| Mar {filing_year} | DIAN publica borrador de renta AG {year} | Pendiente |")
    w(f"| Abr {filing_year} | Informacion exogena AG {year} disponible en MUISCA | Pendiente |")
    w(f"| Ago-Oct {filing_year} | Ventana de presentacion renta persona natural | Pendiente |")
    w()

    # Filing deadline
    if projection and projection.get("filing_deadline"):
        w(f"> **Fecha limite de presentacion:** {projection['filing_deadline']}")
        w()

    w(f"### Checklist de certificados AG {year}")
    w()
    w("| Institucion | Certificado | Recolectado |")
    w("|-------------|-------------|-------------|")
    certificates_checklist = [
        ("Skandia", "Pension obligatoria"),
        ("Skandia", "Pension voluntaria"),
        ("Skandia", "Cesantias"),
        ("Banco Davivienda", "Certificado tributario (cuentas + AFC)"),
        ("Nu Colombia", "Certificado tributario"),
        ("Nequi", "Certificado tributario"),
        ("RappiPay / RappiCard", "Certificado tributario"),
        ("Colmedica", "Medicina prepagada"),
        ("Banco Falabella", "Certificado tributario"),
        ("Acciones & Valores", "Bursatil + fondos"),
        ("Banco de Bogota", "Intereses credito"),
        ("Compensar", "Planilla PILA (12 meses)"),
        ("DIAN", "Exogena XLSX"),
        ("DIAN", "E-facturas recibidas XLSX"),
    ]
    for inst, cert in certificates_checklist:
        w(f"| {inst} | {cert} | ? |")
    w()

    w("### Acciones recomendadas inmediatas")
    w()
    action_num = 1

    if budget_result and budget_result["saldo_pagar"] > 0:
        w(f"{action_num}. **Empezar fondo de ahorro para renta ahora** -- {fmt_cop(budget_result['saldo_pagar'])} es significativo; iniciar separacion mensual reduce presion financiera")
        action_num += 1

    if opt_result and curr_afc > 0:
        opt_total = opt_result["optimal"].get("total_combined", 0)
        if curr_afc > opt_total:
            excess = curr_afc - opt_total
            w(f"{action_num}. **Reevaluar aportes voluntarios** -- aportes actuales ({fmt_cop(curr_afc)}) superan el maximo util ({fmt_cop(opt_total)}); los {fmt_cop(excess)} extra se pueden redirigir a ahorro liquido")
            action_num += 1

    w(f"{action_num}. **Solicitar certificados** en enero-febrero cuando esten disponibles")
    action_num += 1
    w(f"{action_num}. **Validar datos de patrimonio** -- confirmar saldos a Dic 31/{year} de todas las cuentas")
    action_num += 1
    w(f"{action_num}. **Ejecutar self_heal.py** -- validar integridad de los datos antes de declarar")
    action_num += 1
    w()

    w("---")
    w()

    # ── Section 9: Data Sources Inventory ────────────────────────
    w("## 8. Fuentes de Datos")
    w()

    salary_count_total = count_jsonl_records(SALARY_FILE, year, year_key="date") if SALARY_FILE.exists() else 0
    planillas_count_total = count_jsonl_records(PLANILLAS_FILE, year, year_key="periodo") if PLANILLAS_FILE.exists() else 0
    trm_count = trm_stats.get("count", 0)

    w("| Fuente | Registros | Cobertura |")
    w("|--------|-----------|-----------|")
    w(f"| Salary history (JSONL) | {salary_count} pagos | AG {year} {'completo' if salary_count >= 12 else 'parcial'} |")
    w(f"| Planillas PILA (JSONL) | {planillas.get('months', 0)} meses | AG {year} {'completo' if planillas.get('months', 0) >= 12 else 'parcial'} |")
    w(f"| Certificados tributarios | {certs_count} | AG {year} {'verificar' if certs_count < 10 else 'completo'} |")
    w(f"| Exogena DIAN (JSONL) | {exogena_count} reportes | AG {year} {'disponible' if exogena_count > 0 else 'pendiente'} |")
    w(f"| TRM history (JSONL) | {trm_count} dias {year} | {'Cobertura diaria' if trm_count > 200 else 'Parcial'} |")
    w(f"| E-invoices | {count_jsonl_records(DATA_DIR / 'invoices' / 'received' / 'e-invoices.jsonl', year) if (DATA_DIR / 'invoices' / 'received' / 'e-invoices.jsonl').exists() else 0} facturas | AG {year} |")
    w()

    w("### Scripts disponibles")
    w()
    w("```bash")
    w("# Actualizar TRM")
    w("python3 scripts/fetch_trm.py")
    w()
    w("# Recopilar documentos de Gmail")
    w(f"python3 scripts/gmail_collector.py --year {year} --download-attachments")
    w()
    w("# Importar certificados nuevos")
    w(f"python3 scripts/import_certificates.py --year {year} --password <CC>")
    w()
    w("# Proyeccion actualizada")
    w(f"python3 scripts/tax_projection.py --year {year}")
    w()
    w("# Budget mensual")
    w(f"python3 scripts/budget_planner.py --monthly-usd {monthly_usd:.0f} --year {year}")
    w()
    w("# Optimizacion de deducciones")
    w(f"python3 scripts/optimize_deductions.py --from-projection")
    w()
    w("# Patrimonio")
    w(f"python3 scripts/patrimonio_calc.py --year {year} --detail")
    w()
    w("# Validacion")
    w(f"python3 scripts/self_heal.py --year {year}")
    w()
    w("# Generar este informe")
    w(f"python3 scripts/generate_report.py --year {year}")
    w("```")
    w()
    w("---")
    w()
    w(f"*Generado por finance-substrate -- generate_report.py | {gen_date}*")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Generate comprehensive financial report (mode 13: report).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --year 2025
  %(prog)s --year 2025 --output ~/Dropbox/Declaracion/2025/financial-report-2025.md
  %(prog)s --year 2025 --monthly-usd 8000 --anticipo 0
        """,
    )
    parser.add_argument("--year", type=int, default=2025, help="Tax year (ano gravable)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output file path (default: stdout)")
    parser.add_argument("--monthly-usd", type=float, default=8000,
                        help="Monthly salary in USD (for budget planner)")
    parser.add_argument("--anticipo", type=float, default=0,
                        help="Anticipo renta from prior year (R130)")
    parser.add_argument("--retenciones", type=float, default=1_400_000,
                        help="Estimated annual retenciones (COP)")
    parser.add_argument("--parafiscales", type=float, default=2_360_000,
                        help="Monthly PILA payment (COP)")
    parser.add_argument("--vol-pension", type=float, default=20_000_000,
                        help="Annual voluntary pension contribution (COP)")
    parser.add_argument("--fixed-deductions", type=float, default=4_600_000,
                        help="Annual fixed deductions (medicina + GMF + e-inv) (COP)")
    parser.add_argument("--nit-suffix", type=str, default=None,
                        help="Last 2 digits of CC/NIT for filing deadline lookup")
    parser.add_argument("--months-to-deadline", type=int, default=12,
                        help="Months until filing deadline (for budget savings calc)")
    args = parser.parse_args()

    # Suppress stderr noise from sibling module warnings during report generation
    report = generate_report(
        year=args.year,
        monthly_usd=args.monthly_usd,
        anticipo_anterior=args.anticipo,
        retenciones_est=args.retenciones,
        parafiscales_monthly=args.parafiscales,
        vol_pension_annual=args.vol_pension,
        fixed_deductions=args.fixed_deductions,
        nit_suffix=args.nit_suffix,
        months_to_deadline=args.months_to_deadline,
    )

    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"Report written to {output_path}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
