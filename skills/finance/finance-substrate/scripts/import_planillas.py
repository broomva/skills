#!/usr/bin/env python3
"""
Import PILA planillas (monthly social security payment slips) from PDFs.

These provide the exact salud, pensión, ARL, and FSP amounts paid each month,
which make up the INCR (Ingresos No Constitutivos de Renta) on Form 210 R33.

Usage:
    python3 import_planillas.py --year 2024
    python3 import_planillas.py --year 2024 --dir ~/Dropbox/Declaracion/2024/Planillas
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
import hashlib
import json
import os
import re
from pathlib import Path

DATA_DIR = Path.home() / ".finance-substrate"
PLANILLAS_FILE = DATA_DIR / "tax" / "planillas.jsonl"

sys_path_added = False
try:
    from parse_engine import load_parsers, parse_certificate, extract_pdf_text, parse_co_amount
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from parse_engine import load_parsers, parse_certificate, parse_co_amount

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


def ensure_dirs():
    (DATA_DIR / "tax").mkdir(parents=True, exist_ok=True)
    if not PLANILLAS_FILE.exists():
        PLANILLAS_FILE.touch()


def extract_pdf_text_local(path: str, password: str | None = None) -> str:
    if not HAS_FITZ:
        return ""
    try:
        doc = fitz.open(path)
        if doc.is_encrypted:
            if password and not doc.authenticate(password):
                doc.close()
                return ""
            elif not password:
                doc.close()
                return ""
        text = ""
        for i in range(len(doc)):
            text += doc[i].get_text() + "\n"
        doc.close()
        return text
    except Exception:
        return ""


def parse_planilla(text: str, year: int) -> dict | None:
    """Extract social security data from a PILA planilla PDF text."""
    if "PLANILLA INTEGRADA" not in text and "AUTOLIQUIDACION" not in text.upper():
        return None

    # Period
    m = re.search(r"(\d{4}-\d{2})", text)
    periodo = m.group(1) if m else ""
    if not periodo.startswith(str(year)):
        return None

    # Fecha pago
    m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    fecha_pago = m.group(1) if m else ""

    # Subsystem totals
    salud = 0.0
    m = re.search(r"Salud\n\d+\n([\d.]+)", text)
    if m:
        salud = parse_co_amount(m.group(1))

    pension = 0.0
    m = re.search(r"Pensión\n\d+\n([\d.]+)", text)
    if m:
        pension = parse_co_amount(m.group(1))

    arl = 0.0
    m = re.search(r"Riesgos Laborales\n\d+\n([\d.]+)", text)
    if m:
        arl = parse_co_amount(m.group(1))

    # Total
    total = 0.0
    m = re.search(r"TOTALES\n\d+\n[\d.]+\n([\d.]+)", text)
    if m:
        total = parse_co_amount(m.group(1))

    # IBC
    ibc = 0.0
    m = re.search(r"230901\n([\d.]+)", text)
    if m:
        ibc = parse_co_amount(m.group(1))

    # FSP — from pension detail row after AFP NIT
    # Pattern: NIT\n<cotiz_oblig>\n<vol_afil>\n<vol_aport>\n<fsp_sol>\n<fsp_sub>
    fsp_solidaridad = 0.0
    fsp_subsistencia = 0.0
    m = re.search(r"TOTALES PENSIÓN.*?\d{6,}-\d\n([\d.]+)\n([\d.]+)\n([\d.]+)\n([\d.]+)\n([\d.]+)", text, re.DOTALL)
    if m:
        # groups: 1=cotiz_oblig, 2=vol_afil, 3=vol_aport, 4=fsp_sol, 5=fsp_sub
        fsp_solidaridad = parse_co_amount(m.group(4))
        fsp_subsistencia = parse_co_amount(m.group(5))

    pid = hashlib.sha256(f"{year}|planilla|{periodo}".encode()).hexdigest()[:16]

    return {
        "id": pid,
        "year": year,
        "periodo": periodo,
        "fecha_pago": fecha_pago,
        "ibc": ibc,
        "salud": salud,
        "pension": pension,
        "arl": arl,
        "fsp_solidaridad": fsp_solidaridad,
        "fsp_subsistencia": fsp_subsistencia,
        "total": total,
    }


def import_planillas(year: int, planillas_dir: Path, password: str | None = None) -> dict:
    ensure_dirs()

    pdf_files = sorted(planillas_dir.glob("Planilla*.pdf"))
    if not pdf_files:
        return {"error": f"No planilla PDFs found in {planillas_dir}", "count": 0}

    existing = set()
    if PLANILLAS_FILE.exists():
        with open(PLANILLAS_FILE) as f:
            for line in f:
                if line.strip():
                    existing.add(json.loads(line.strip()).get("id", ""))

    records = []
    totals = {"salud": 0, "pension": 0, "arl": 0, "fsp": 0, "total": 0}

    for pdf_path in pdf_files:
        text = extract_pdf_text_local(str(pdf_path), password)
        if not text:
            continue

        planilla = parse_planilla(text, year)
        if not planilla:
            continue

        records.append(planilla)
        totals["salud"] += planilla["salud"]
        totals["pension"] += planilla["pension"]
        totals["arl"] += planilla["arl"]
        totals["fsp"] += planilla["fsp_solidaridad"] + planilla["fsp_subsistencia"]
        totals["total"] += planilla["total"]

    # Save new records
    new_count = 0
    with open(PLANILLAS_FILE, "a") as f:
        for rec in records:
            if rec["id"] not in existing:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                existing.add(rec["id"])
                new_count += 1

    return {
        "count": len(records),
        "new": new_count,
        "totals": totals,
        "incr_r33": totals["salud"] + totals["pension"] + totals["arl"] + totals["fsp"],
    }


def main():
    parser = argparse.ArgumentParser(description="Import PILA planillas (social security)")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--dir", help="Directory with planilla PDFs")
    parser.add_argument("--password", help="PDF password if needed")
    args = parser.parse_args()

    planillas_dir = Path(args.dir) if args.dir else Path.home() / "Dropbox" / "Declaracion" / str(args.year) / "Planillas"
    if not planillas_dir.exists():
        print(f"Error: {planillas_dir} does not exist")
        return

    print(f"=== Importing planillas for {args.year} from {planillas_dir} ===\n")
    result = import_planillas(args.year, planillas_dir, args.password)

    if "error" in result:
        print(f"  {result['error']}")
        return

    t = result["totals"]
    print(f"  Parsed {result['count']} planillas ({result['new']} new)\n")
    print(f"  Annual Social Security Summary:")
    print(f"    Salud (EPS):          ${t['salud']:>15,.0f}")
    print(f"    Pensión obligatoria:  ${t['pension']:>15,.0f}")
    print(f"    ARL:                  ${t['arl']:>15,.0f}")
    print(f"    FSP (Sol+Sub):        ${t['fsp']:>15,.0f}")
    print(f"    Total planillas:      ${t['total']:>15,.0f}")
    print(f"    ─────────────────────────────────")
    print(f"    INCR (R33) from SS:   ${result['incr_r33']:>15,.0f}")

    print(f"\n  Saved to: {PLANILLAS_FILE}")


if __name__ == "__main__":
    main()
