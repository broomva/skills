#!/usr/bin/env python3
"""
Colombian tax projection for personas naturales (cedular system).

Calibrated against DIAN Form 210 borrador. Uses actual salary, exogena,
e-invoices, and ledger data from ~/.finance-substrate/.

Usage:
    python3 tax_projection.py --year 2024
    python3 tax_projection.py --year 2024 --uvt 47065
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

DATA_DIR = Path.home() / ".finance-substrate"
LEDGER_FILE = DATA_DIR / "ledger" / "transactions.jsonl"
SALARY_FILE = DATA_DIR / "tax" / "salary-history.jsonl"
WITHHOLDINGS_FILE = DATA_DIR / "tax" / "withholdings.jsonl"
EXOGENA_FILE = DATA_DIR / "tax" / "exogena.jsonl"
CERTS_FILE = DATA_DIR / "tax" / "certificates.jsonl"
PLANILLAS_FILE = DATA_DIR / "tax" / "planillas.jsonl"
INVOICES_FILE = DATA_DIR / "invoices" / "received" / "e-invoices.jsonl"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def load_tax_tables(year: int) -> dict:
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


def load_salary(year: int) -> dict:
    result = {
        "total_usd": 0, "total_gross_cop": 0, "total_net_cop": 0,
        "total_fx_loss": 0, "payments": 0, "avg_rate": 0,
    }
    rates = []
    if not SALARY_FILE.exists():
        return result
    with open(SALARY_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if not rec.get("date", "").startswith(str(year)):
                continue
            result["total_usd"] += rec.get("amount_usd", 0)
            result["total_gross_cop"] += rec.get("gross_cop", 0)
            result["total_net_cop"] += rec.get("net_cop", 0)
            result["total_fx_loss"] += rec.get("fx_loss_cop", 0)
            result["payments"] += 1
            if rec.get("exchange_rate"):
                rates.append(rec["exchange_rate"])
    if rates:
        result["avg_rate"] = sum(rates) / len(rates)
    return result


def load_exogena(year: int) -> dict:
    result = {
        "topes": {},
        "retenciones": [],
        "patrimonio": [],
        "pension_obligatoria": 0,
        "pension_voluntaria": 0,
        "pension_voluntaria_retencion": 0,
        "rendimientos_financieros": 0,
        "retencion_rendimientos": 0,
        "saldo_cuentas": 0,
        "valor_vehiculo": 0,
        "consumo_tc": 0,
        "cesantias": 0,
        "movimientos_cuentas": 0,
    }
    if not EXOGENA_FILE.exists():
        return result
    with open(EXOGENA_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("year") != year:
                continue

            if rec.get("type") == "tope":
                result["topes"][rec["detail"]] = rec["value"]
                continue

            detail = rec.get("detail", "").lower()
            value = rec.get("value", 0)

            if "pensión obligatoria" in detail and "aporte" in detail:
                result["pension_obligatoria"] += value
            elif "pensión voluntaria" in detail and "retención" in detail:
                result["pension_voluntaria_retencion"] += value
            elif "pensión voluntaria" in detail or ("voluntari" in detail and "pensión" in detail):
                result["pension_voluntaria"] += value
            elif "rendimientos financieros" in detail and "retención" not in detail:
                result["rendimientos_financieros"] += value
            elif "retención" in detail and "rendimientos" in detail:
                result["retencion_rendimientos"] += value
            elif "saldo cuentas" in detail:
                result["saldo_cuentas"] += value
                result["patrimonio"].append({
                    "entity": rec.get("reporter_name", ""),
                    "detail": rec.get("detail", ""),
                    "value": value,
                    "info": rec.get("additional_info", ""),
                })
            elif "avalúo vehículo" in detail:
                result["valor_vehiculo"] += value
                result["patrimonio"].append({
                    "entity": rec.get("reporter_name", ""),
                    "detail": rec.get("detail", ""),
                    "value": value,
                })
            elif "consumos" in detail and "tarjeta" in detail:
                result["consumo_tc"] += value
            elif "cesantías" in detail:
                result["cesantias"] += value
            elif "movimientos" in detail and "cuentas" in detail:
                result["movimientos_cuentas"] += value

            # Collect all retenciones
            if "retención" in detail:
                result["retenciones"].append({
                    "entity": rec.get("reporter_name", ""),
                    "nit": rec.get("reporter_nit", ""),
                    "detail": rec.get("detail", ""),
                    "value": value,
                })

            # Collect patrimonio items (R29) that aren't already captured above
            # Excludes: saldo cuentas (already captured), avalúo (already captured),
            # "patrimonio declarado año anterior" (reference only, not an asset)
            tax_use = rec.get("tax_use", "").lower()
            is_r29 = "r29" in tax_use or "patrimonio bruto" in tax_use
            is_already_captured = "saldo cuentas" in detail or "avalúo" in detail
            is_reference = "declarado en el año anterior" in detail
            if is_r29 and not is_already_captured and not is_reference:
                result["patrimonio"].append({
                    "entity": rec.get("reporter_name", ""),
                    "detail": rec.get("detail", ""),
                    "value": value,
                    "tax_use": rec.get("tax_use", ""),
                })

    return result


def load_certificates_agg(year: int) -> dict:
    """Load aggregated certificate data from certificates.jsonl."""
    agg = {
        "rendimientos_gravados": 0, "rendimientos_no_gravados": 0,
        "retencion_renta": 0, "gmf_deducible": 0,
        "patrimonio_cuentas": 0, "patrimonio_inversiones": 0, "deudas": 0,
        "pension_obligatoria_incr": 0, "aportes_afc_r35": 0,
        "pension_voluntaria_r35": 0, "medicina_prepagada_r39": 0,
        "dividendos": 0, "rendimientos_voluntaria": 0, "rendimientos_cesantias": 0,
        "retiro_aportes_capital": 0, "retiro_rendimientos_capital": 0,
    }
    if not CERTS_FILE.exists():
        return agg
    with open(CERTS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            if c.get("year") != year or c.get("type") != "certificado-tributario":
                continue
            ts = c.get("tax_summary", {})
            agg["rendimientos_gravados"] += ts.get("rendimientos_gravados", 0)
            agg["rendimientos_no_gravados"] += ts.get("rendimientos_no_gravados", 0)
            agg["retencion_renta"] += ts.get("retencion_renta", 0) + ts.get("retencion_total", 0)
            agg["gmf_deducible"] += ts.get("gmf_deducible_50pct", 0)
            agg["patrimonio_cuentas"] += ts.get("patrimonio_cuenta", 0) + ts.get("patrimonio_cuentas", 0)
            agg["patrimonio_inversiones"] += (
                ts.get("patrimonio_fondos", 0) + ts.get("patrimonio_caja", 0) +
                ts.get("patrimonio_acciones", 0) + ts.get("patrimonio_cesantias", 0) +
                ts.get("patrimonio_voluntaria", 0)
            )
            agg["deudas"] += ts.get("deuda_patrimonio", 0)
            agg["pension_obligatoria_incr"] += ts.get("pension_oblig_plus_fsp", 0)
            agg["aportes_afc_r35"] += ts.get("aportes_afc_r35", 0)
            agg["pension_voluntaria_r35"] += ts.get("pension_voluntaria_aportes", 0)
            agg["medicina_prepagada_r39"] += ts.get("medicina_prepagada_deduccion_r39", 0)
            agg["dividendos"] += ts.get("dividendos", 0)
            agg["rendimientos_voluntaria"] += ts.get("rendimientos_voluntaria", 0)
            agg["rendimientos_cesantias"] += ts.get("rendimientos_cesantias", 0)
            agg["retiro_aportes_capital"] += ts.get("retiro_aportes_capital_r58", 0)
            agg["retiro_rendimientos_capital"] += ts.get("retiro_rendimientos_capital_r58", 0)
    return agg


def load_planillas(year: int) -> dict:
    """Load annual social security totals from planillas."""
    result = {"salud": 0, "pension": 0, "arl": 0, "fsp": 0, "total": 0, "months": 0}
    if not PLANILLAS_FILE.exists():
        return result
    with open(PLANILLAS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            if not str(p.get("periodo", "")).startswith(str(year)):
                continue
            result["salud"] += p.get("salud", 0)
            result["pension"] += p.get("pension", 0)
            result["arl"] += p.get("arl", 0)
            result["fsp"] += p.get("fsp_solidaridad", 0) + p.get("fsp_subsistencia", 0)
            result["total"] += p.get("total", 0)
            result["months"] += 1
    return result


def load_einvoices_total(year: int) -> dict:
    result = {"total_facturado": 0, "total_neto": 0, "total_beneficio_1pct": 0, "count": 0}
    if not INVOICES_FILE.exists():
        return result
    with open(INVOICES_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("year") != year:
                continue
            result["total_facturado"] += rec.get("valor_facturado", 0)
            result["total_neto"] += rec.get("valor_neto", 0)
            result["total_beneficio_1pct"] += rec.get("valor_beneficio_1pct", 0)
            result["count"] += 1
    return result


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


def project_tax(year: int, uvt_override: float | None = None, anticipo_anterior: float = 0, nit_suffix: str | None = None):
    """Run full tax projection calibrated against DIAN Form 210."""
    tables = load_tax_tables(year)
    uvt = uvt_override or tables.get("uvt_value", 47065)
    brackets = tables.get("brackets_renta", [])

    salary = load_salary(year)
    exogena = load_exogena(year)
    certs = load_certificates_agg(year)
    planillas = load_planillas(year)
    einvoices = load_einvoices_total(year)

    # ════════════════════════════════════════════════════════════════
    # RENTAS DE TRABAJO (Rows 32-42 on Form 210)
    # ════════════════════════════════════════════════════════════════

    # R32: Ingresos brutos rentas de trabajo
    ingresos_brutos_trabajo = salary["total_gross_cop"]

    # R33: Ingresos no constitutivos de renta (INCR)
    # Priority: planillas (exact) > certificates > exogena > estimate
    if planillas["months"] > 0:
        # Exact from PILA planillas
        incr_ss = planillas["salud"] + planillas["pension"] + planillas["arl"] + planillas["fsp"]
    elif certs["pension_obligatoria_incr"] > 0:
        # From certificates: scale pension to include salud/ARL/FSP
        pension = certs["pension_obligatoria_incr"]
        incr_ss = pension * (30.022 / 16)  # Approximate total SS from pension ratio
    else:
        # Fallback: estimate from IBC (40% of gross)
        ibc = ingresos_brutos_trabajo * 0.40
        incr_ss = ibc * 0.30022

    # Voluntary pension CONTRIBUTIONS are INCR under Art. 126-1 ET
    # But only the net contribution (aportes - retiros that return to income)
    # The aportes go to R33 INCR; the retiros go to R58 capital income
    incr_pension_voluntaria = certs["pension_voluntaria_r35"]

    incr_trabajo = incr_ss + incr_pension_voluntaria

    # R34: Renta líquida = R32 - R33
    renta_liquida_trabajo = max(0, ingresos_brutos_trabajo - incr_trabajo)

    # ── Rentas exentas (R35-R37) ────────────────────────────────
    # R35: Aportes AFC + voluntarios pension/AFC (from certificates)
    aportes_afc = certs["aportes_afc_r35"]

    # R36: Otras rentas exentas (25% Art. 206.10 ET)
    exempt_25pct = renta_liquida_trabajo * 0.25
    # Art. 206 Num. 10 (modified by Ley 2277/2022 Art. 2): 790 UVT ANNUAL cap
    # Pre-reform was 240 UVT/month = 2,880 UVT/year. Post-reform: 790 UVT/year flat.
    exempt_25pct_cap = 790 * uvt  # $37,181,350 for UVT 2024
    otras_rentas_exentas = min(exempt_25pct, exempt_25pct_cap)

    # R37: Total rentas exentas
    total_rentas_exentas = aportes_afc + otras_rentas_exentas

    # ── Deducciones (R38-R40) ───────────────────────────────────
    # R38: Intereses de vivienda
    intereses_vivienda = 0

    # R39: Otras deducciones imputables
    einvoice_deduction = einvoices["total_beneficio_1pct"] * 0.01
    medicina_prepagada = certs["medicina_prepagada_r39"]
    gmf_deducible = certs["gmf_deducible"]
    otras_deducciones = einvoice_deduction + medicina_prepagada + gmf_deducible

    # R40: Total deducciones
    total_deducciones = intereses_vivienda + otras_deducciones

    # R41: Rentas exentas y/o deducciones limitadas
    # Art. 336 Numeral 3 (modified by Ley 2277/2022 Art. 7):
    # Cap = min(40% of R34, 1,340 UVT) — reduced from 5,040 UVT by reform
    raw_exentas_deducciones = total_rentas_exentas + total_deducciones
    cap_40pct = renta_liquida_trabajo * 0.40
    cap_uvt = 1340 * uvt  # Art. 336 Num. 3, Ley 2277/2022
    cap = min(cap_40pct, cap_uvt)
    rentas_exentas_limitadas = min(raw_exentas_deducciones, cap)

    # R42: Renta líquida ordinaria trabajo
    renta_liq_ordinaria_trabajo = max(0, renta_liquida_trabajo - rentas_exentas_limitadas)

    # ════════════════════════════════════════════════════════════════
    # RENTAS DE CAPITAL (Rows 58-73 on Form 210)
    # ════════════════════════════════════════════════════════════════

    # R58: Ingresos brutos rentas de capital
    # Includes: bank rendimientos + voluntary pension retiros (Art. 126-1 ET)
    # Retiros from voluntary pension (aportes + rendimientos) are capital income
    rendimientos_financieros = (
        certs["rendimientos_gravados"] + certs["rendimientos_no_gravados"] +
        certs["rendimientos_voluntaria"] + certs["rendimientos_cesantias"]
    )
    retiros_pension_voluntaria = (
        certs["retiro_aportes_capital"] + certs["retiro_rendimientos_capital"]
    )
    rendimientos = rendimientos_financieros + retiros_pension_voluntaria
    if rendimientos == 0:
        rendimientos = exogena["rendimientos_financieros"]

    # R59: INCR capital — non-taxable component (50.88% componente inflacionario)
    # Only applies to financial rendimientos, not pension retiros
    incr_capital = certs["rendimientos_no_gravados"]
    if incr_capital == 0:
        incr_capital = exogena["retencion_rendimientos"]

    # R61: Renta líquida capital
    renta_liq_capital = max(0, rendimientos - incr_capital)

    # R73: Renta líquida gravable capital
    renta_grav_capital = renta_liq_capital

    # ════════════════════════════════════════════════════════════════
    # CÉDULA GENERAL (Rows 91-97)
    # ════════════════════════════════════════════════════════════════

    # R91: Renta líquida cédula general = trabajo + capital + no laboral
    renta_liq_ced_gen = renta_liquida_trabajo + renta_liq_capital

    # R92: Rentas exentas y deducciones imputables limitadas
    ren_ex_ded_limitadas = rentas_exentas_limitadas

    # R93: Renta líquida gravable cédula general
    renta_grav_ced_gen = max(0, renta_liq_ced_gen - ren_ex_ded_limitadas)

    # R97: Renta líquida gravable = R93 (if no presumptive rent)
    renta_grav = renta_grav_ced_gen

    # ════════════════════════════════════════════════════════════════
    # TAX CALCULATION (Rows 121-136)
    # ════════════════════════════════════════════════════════════════

    # R111: Renta líquida gravable (cédula general + dividendos)
    renta_grav_total = renta_grav

    # R121: Total impuesto sobre rentas líquidas gravables
    taxable_uvt = renta_grav_total / uvt
    tax_uvt = calculate_tax(taxable_uvt, brackets)
    impuesto_renta = tax_uvt * uvt

    # R126: Impuesto neto de renta
    impuesto_neto = impuesto_renta

    # R129: Total impuesto a cargo
    total_impuesto_cargo = impuesto_neto

    # R130: Anticipo renta liquidado año gravable anterior
    anticipo_anterior_val = anticipo_anterior

    # R132: Retenciones año gravable a declarar
    # Use certificates (exact) > exogena
    total_retenciones = certs["retencion_renta"]
    if total_retenciones == 0:
        for r in exogena["retenciones"]:
            total_retenciones += r["value"]

    # R133: Anticipo renta para el año gravable siguiente
    # = max(0, 75% of R126 - R132)  [first year: 25%, second year: 50%, then 75%]
    anticipo_siguiente = max(0, impuesto_neto * 0.75 - total_retenciones)

    # R134: Saldo a pagar por impuesto
    saldo_pagar = max(0, total_impuesto_cargo + anticipo_siguiente - anticipo_anterior_val - total_retenciones)

    # R136: Total saldo a pagar
    total_saldo_pagar = saldo_pagar

    # R137: Total saldo a favor
    total_saldo_favor = abs(min(0, total_impuesto_cargo + anticipo_siguiente - anticipo_anterior_val - total_retenciones))

    # ════════════════════════════════════════════════════════════════
    # PATRIMONIO (Rows 29-31)
    # ════════════════════════════════════════════════════════════════

    # R29 Patrimonio bruto — sum ALL exogena R29/patrimonio items
    # Exogena is the authoritative source: it includes bank saldos, vehicle,
    # real estate (Marval), investment funds, pension saldos, shares, etc.
    # Use exogena total rather than certificates to avoid double-counting.
    patrimonio_bruto = exogena["valor_vehiculo"]
    for item in exogena.get("patrimonio", []):
        patrimonio_bruto += item.get("value", 0)

    # If no exogena patrimonio items, fall back to certificates
    if patrimonio_bruto <= exogena["valor_vehiculo"]:
        patrimonio_bruto += certs["patrimonio_cuentas"] + certs["patrimonio_inversiones"]

    # R30 Deudas — from exogena (R30 tagged) + certificates
    deudas = 0
    if EXOGENA_FILE.exists():
        with open(EXOGENA_FILE) as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line:
                    continue
                _rec = json.loads(_line)
                if _rec.get("year") == year and "R30" in str(_rec.get("tax_use", "")):
                    deudas += _rec.get("value", 0)
    if deudas == 0:
        deudas = certs["deudas"]

    # R31
    patrimonio_liquido = max(0, patrimonio_bruto - deudas)

    # Filing deadline
    filing_deadline = None
    if "filing_calendar" in tables:
        deadlines = tables["filing_calendar"].get("deadlines", [])
        # Derive suffix from CC number in salary data or prompt user
        # For now, requires user to check templates/tax-tables-YYYY.json manually
        # User must provide --nit-suffix or it's left unresolved
        if nit_suffix:
            for d in deadlines:
                lo, hi = d["nit_suffix"].split("-")
                if int(lo) <= int(nit_suffix) <= int(hi):
                    filing_deadline = d["date"]
                    break

    # ════════════════════════════════════════════════════════════════
    # OUTPUT (mapped to Form 210 rows)
    # ════════════════════════════════════════════════════════════════

    result = {
        "year": year,
        "uvt": uvt,
        "filing_deadline": filing_deadline,
        "form_210": {
            "patrimonio": {
                "R29_patrimonio_bruto": round(patrimonio_bruto),
                "R31_patrimonio_liquido": round(patrimonio_liquido),
            },
            "rentas_trabajo": {
                "R32_ingresos_brutos": round(ingresos_brutos_trabajo),
                "R33_incr": round(incr_trabajo),
                "R34_renta_liquida": round(renta_liquida_trabajo),
                "R35_aportes_afc": round(aportes_afc),
                "R36_otras_rentas_exentas": round(otras_rentas_exentas),
                "R37_total_rentas_exentas": round(total_rentas_exentas),
                "R38_intereses_vivienda": round(intereses_vivienda),
                "R39_otras_deducciones": round(otras_deducciones),
                "R40_total_deducciones": round(total_deducciones),
                "R41_exentas_deduc_limitadas": round(rentas_exentas_limitadas),
                "R42_renta_liq_ordinaria": round(renta_liq_ordinaria_trabajo),
            },
            "rentas_capital": {
                "R58_ingresos_brutos": round(rendimientos),
                "R59_incr": round(incr_capital),
                "R61_renta_liquida": round(renta_liq_capital),
                "R73_renta_gravable": round(renta_grav_capital),
            },
            "cedula_general": {
                "R91_renta_liquida": round(renta_liq_ced_gen),
                "R92_exentas_ded_limitadas": round(ren_ex_ded_limitadas),
                "R93_renta_grav_cedula_gen": round(renta_grav_ced_gen),
                "R97_renta_grav": round(renta_grav),
                "renta_grav_uvt": round(taxable_uvt, 2),
            },
            "impuesto": {
                "R121_impuesto_rentas": round(impuesto_renta),
                "R126_impuesto_neto": round(impuesto_neto),
                "R129_total_impuesto_cargo": round(total_impuesto_cargo),
                "R130_anticipo_anterior": round(anticipo_anterior_val),
                "R132_retenciones": round(total_retenciones),
                "R133_anticipo_siguiente": round(anticipo_siguiente),
                "R134_saldo_pagar": round(saldo_pagar),
                "R136_total_saldo_pagar": round(total_saldo_pagar),
                "R137_total_saldo_favor": round(total_saldo_favor),
            },
        },
        "salary_detail": {
            "payments": salary["payments"],
            "total_usd": salary["total_usd"],
            "avg_rate": round(salary["avg_rate"], 2),
            "gross_cop": round(salary["total_gross_cop"]),
            "net_cop": round(salary["total_net_cop"]),
            "fx_loss_cop": round(salary["total_fx_loss"]),
        },
        "deduction_detail": {
            "raw_exentas_deducciones": round(raw_exentas_deducciones),
            "cap_40pct_of_R34": round(cap_40pct),
            "cap_1340uvt": round(cap_uvt),
            "applied_cap": round(cap),
        },
        "exogena_data": {
            "topes": exogena["topes"],
            "pension_obligatoria": round(exogena["pension_obligatoria"]),
            "pension_voluntaria": round(exogena.get("pension_voluntaria", 0)),
            "consumo_tc": round(exogena["consumo_tc"]),
            "movimientos_cuentas": round(exogena["movimientos_cuentas"]),
        },
        "einvoices": {
            "count": einvoices["count"],
            "total_facturado": round(einvoices["total_facturado"]),
            "total_neto": round(einvoices["total_neto"]),
            "total_beneficio_eligible": round(einvoices["total_beneficio_1pct"]),
            "deduccion_1pct": round(einvoice_deduction),
        },
    }

    return result


def print_form_210(result: dict):
    """Print output formatted like DIAN Form 210."""
    f = result["form_210"]
    s = result["salary_detail"]
    d = result["deduction_detail"]
    ex = result["exogena_data"]
    ei = result["einvoices"]

    print(f"\n{'='*70}")
    print(f"  DECLARACIÓN DE RENTA — Año Gravable {result['year']}  (Form 210)")
    print(f"{'='*70}")
    print(f"  UVT {result['year']}: ${result['uvt']:,.0f} COP")
    if result.get("filing_deadline"):
        print(f"  Filing deadline (CC ...70): {result['filing_deadline']}")
    print()

    print(f"  ── PATRIMONIO ─────────────────────────────────────────────")
    print(f"  R29  Patrimonio bruto:           ${f['patrimonio']['R29_patrimonio_bruto']:>15,.0f}")
    print(f"  R31  Patrimonio líquido:         ${f['patrimonio']['R31_patrimonio_liquido']:>15,.0f}")
    print()

    rt = f["rentas_trabajo"]
    print(f"  ── RENTAS DE TRABAJO ──────────────────────────────────────")
    print(f"  R32  Ingresos brutos:            ${rt['R32_ingresos_brutos']:>15,.0f}")
    print(f"  R33  INCR:                       ${rt['R33_incr']:>15,.0f}")
    print(f"  R34  Renta líquida:              ${rt['R34_renta_liquida']:>15,.0f}")
    print(f"  R35  Aportes voluntarios:        ${rt['R35_aportes_afc']:>15,.0f}")
    print(f"  R36  Otras rentas exentas (25%): ${rt['R36_otras_rentas_exentas']:>15,.0f}")
    print(f"  R37  Total rentas exentas:       ${rt['R37_total_rentas_exentas']:>15,.0f}")
    print(f"  R39  Otras deducciones:          ${rt['R39_otras_deducciones']:>15,.0f}")
    print(f"  R40  Total deducciones:          ${rt['R40_total_deducciones']:>15,.0f}")
    print(f"  R41  Exentas+Deduc. (limitadas): ${rt['R41_exentas_deduc_limitadas']:>15,.0f}")
    print(f"  R42  Renta líq. ordinaria:       ${rt['R42_renta_liq_ordinaria']:>15,.0f}")
    print()

    rc = f["rentas_capital"]
    print(f"  ── RENTAS DE CAPITAL ──────────────────────────────────────")
    print(f"  R58  Ingresos brutos:            ${rc['R58_ingresos_brutos']:>15,.0f}")
    print(f"  R59  INCR:                       ${rc['R59_incr']:>15,.0f}")
    print(f"  R73  Renta gravable:             ${rc['R73_renta_gravable']:>15,.0f}")
    print()

    cg = f["cedula_general"]
    print(f"  ── CÉDULA GENERAL ─────────────────────────────────────────")
    print(f"  R91  Renta líquida:              ${cg['R91_renta_liquida']:>15,.0f}")
    print(f"  R92  Exentas+Deduc. limitadas:   ${cg['R92_exentas_ded_limitadas']:>15,.0f}")
    print(f"  R93  Renta grav. céd. general:   ${cg['R93_renta_grav_cedula_gen']:>15,.0f}")
    print(f"       ({cg['renta_grav_uvt']:,.1f} UVT)")
    print()

    imp = f["impuesto"]
    print(f"  ── IMPUESTO ───────────────────────────────────────────────")
    print(f"  R121 Impuesto sobre rentas:      ${imp['R121_impuesto_rentas']:>15,.0f}")
    print(f"  R126 Impuesto neto:              ${imp['R126_impuesto_neto']:>15,.0f}")
    print(f"  R129 Total impuesto a cargo:     ${imp['R129_total_impuesto_cargo']:>15,.0f}")
    print(f"  R130 Anticipo anterior:          ${imp['R130_anticipo_anterior']:>15,.0f}")
    print(f"  R132 Retenciones:                ${imp['R132_retenciones']:>15,.0f}")
    print(f"  R133 Anticipo siguiente:         ${imp['R133_anticipo_siguiente']:>15,.0f}")
    print(f"  ─────────────────────────────────────────────────────────")
    if imp["R134_saldo_pagar"] > 0:
        print(f"  R134 SALDO A PAGAR:              ${imp['R134_saldo_pagar']:>15,.0f}  <<<")
    if imp["R137_total_saldo_favor"] > 0:
        print(f"  R137 SALDO A FAVOR:              ${imp['R137_total_saldo_favor']:>15,.0f}  <<<")
    print()

    print(f"  ── SALARY DETAIL ──────────────────────────────────────────")
    print(f"  {s['payments']} payments | ${s['total_usd']:,.0f} USD | avg rate {s['avg_rate']:,.2f}")
    print(f"  Gross COP: ${s['gross_cop']:,.0f} | Net: ${s['net_cop']:,.0f}")
    print(f"  FX loss (deductible): ${s['fx_loss_cop']:,.0f}")
    print()

    print(f"  ── DEDUCTION CAPS ─────────────────────────────────────────")
    print(f"  Raw exentas+deducciones:         ${d['raw_exentas_deducciones']:>15,.0f}")
    print(f"  Cap 40% of R34:                  ${d['cap_40pct_of_R34']:>15,.0f}")
    print(f"  Cap 1,340 UVT (Art.336):          ${d['cap_1340uvt']:>15,.0f}")
    print(f"  Applied cap:                     ${d['applied_cap']:>15,.0f}")
    print()

    print(f"  ── EXOGENA THRESHOLDS ─────────────────────────────────────")
    for k, v in ex["topes"].items():
        print(f"  {k}: ${v:>15,.0f}")
    print(f"  Pension obligatoria (reported):   ${ex['pension_obligatoria']:>15,.0f}")
    print(f"  Pension voluntaria (reported):    ${ex['pension_voluntaria']:>15,.0f}")
    print()

    print(f"  ── E-INVOICES ─────────────────────────────────────────────")
    print(f"  {ei['count']} invoices | Total: ${ei['total_facturado']:,.0f}")
    print(f"  Eligible for 1% deduction: ${ei['total_beneficio_eligible']:,.0f}")
    print(f"  1% deduction value: ${ei['deduccion_1pct']:,.0f}")


def main():
    parser = argparse.ArgumentParser(description="Colombian tax projection (persona natural)")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--uvt", type=float, help="Override UVT value")
    parser.add_argument("--anticipo", type=float, default=0,
                        help="Anticipo renta liquidado año gravable anterior (R130)")
    parser.add_argument("--nit-suffix", help="Last 2 digits of CC/NIT for filing deadline lookup")
    args = parser.parse_args()

    result = project_tax(args.year, args.uvt, args.anticipo, args.nit_suffix)

    # Cache projection for downstream tools (e.g. optimize_deductions --from-projection)
    cache_dir = Path.home() / ".finance-substrate" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "last_projection.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print_form_210(result)


if __name__ == "__main__":
    main()
