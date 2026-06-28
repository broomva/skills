#!/usr/bin/env python3
"""
Parse tax certificates from Colombian financial institutions using the
declarative parser engine (parsers/*.json).

Falls back to legacy regex parsers if no declarative definition matches.

Usage:
    python3 import_certificates.py --year 2024 --password <CC_NUMBER>
    python3 import_certificates.py --year 2024 --dir ~/Dropbox/Declaracion/2024
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
from pathlib import Path

DATA_DIR = Path.home() / ".finance-substrate"
CERTS_FILE = DATA_DIR / "tax" / "certificates.jsonl"

try:
    import fitz  # type: ignore[import-untyped]
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

# Import the declarative engine
sys_path_added = False
try:
    from parse_engine import load_parsers, parse_certificate, log_improvement_signal, parse_co_amount
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    sys_path_added = True
    from parse_engine import load_parsers, parse_certificate, log_improvement_signal, parse_co_amount


def ensure_dirs():
    (DATA_DIR / "tax").mkdir(parents=True, exist_ok=True)
    if not CERTS_FILE.exists():
        CERTS_FILE.touch()


def save_cert(cert: dict) -> bool:
    existing = set()
    lines = []
    if CERTS_FILE.exists():
        with open(CERTS_FILE) as f:
            lines = f.readlines()
        for line in lines:
            if line.strip():
                existing.add(json.loads(line.strip()).get("id", ""))

    if cert["id"] in existing:
        with open(CERTS_FILE, "w") as f:
            for line in lines:
                entry = json.loads(line.strip()) if line.strip() else {}
                if entry.get("id") == cert["id"]:
                    f.write(json.dumps(cert, ensure_ascii=False) + "\n")
                else:
                    f.write(line)
        return False
    else:
        with open(CERTS_FILE, "a") as f:
            f.write(json.dumps(cert, ensure_ascii=False) + "\n")
        return True


def extract_pdf_text(path: str, password: str | None = None) -> str:
    if not HAS_FITZ:
        print(f"  Warning: pymupdf not installed, cannot parse {path}")
        return ""
    try:
        doc = fitz.open(path)
        if doc.is_encrypted:
            if password:
                if not doc.authenticate(password):
                    print(f"  Warning: wrong password for {os.path.basename(path)}")
                    doc.close()
                    return ""
            else:
                print(f"  Skipping locked PDF (no password): {os.path.basename(path)}")
                doc.close()
                return ""
        text = ""
        for i in range(len(doc)):
            text += doc[i].get_text() + "\n"
        doc.close()
        return text
    except Exception as e:
        print(f"  Error reading {os.path.basename(path)}: {e}")
        return ""


def aggregate_certificates(year: int) -> dict:
    """Aggregate all certificate tax_summary data into Form 210 inputs."""
    certs = []
    if CERTS_FILE.exists():
        with open(CERTS_FILE) as f:
            for line in f:
                if line.strip():
                    c = json.loads(line.strip())
                    if c.get("year") == year and c.get("type") == "certificado-tributario":
                        certs.append(c)

    agg = {
        "rendimientos_gravados": 0,
        "rendimientos_no_gravados": 0,
        "retencion_renta_total": 0,
        "gmf_deducible_50pct": 0,
        "patrimonio_cuentas": 0,
        "patrimonio_inversiones": 0,
        "deudas": 0,
        "pension_obligatoria_incr": 0,
        "aportes_afc_r35": 0,
        "pension_voluntaria_r35": 0,
        "medicina_prepagada_r39": 0,
        "dividendos": 0,
    }

    for c in certs:
        ts = c.get("tax_summary", {})
        agg["rendimientos_gravados"] += ts.get("rendimientos_gravados", 0)
        agg["rendimientos_no_gravados"] += ts.get("rendimientos_no_gravados", 0)
        agg["retencion_renta_total"] += ts.get("retencion_renta", 0) + ts.get("retencion_total", 0)
        agg["gmf_deducible_50pct"] += ts.get("gmf_deducible_50pct", 0)
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

    return agg


def import_certificates(year: int, cert_dir: Path, password: str | None = None) -> list:
    ensure_dirs()
    results = []

    # Load declarative parser definitions
    parser_defs = load_parsers()
    if parser_defs:
        print(f"  Loaded {len(parser_defs)} parser definitions\n")

    pdf_files = sorted(cert_dir.glob("Certificado*.pdf")) + sorted(cert_dir.glob("Reporte*.pdf"))
    if not pdf_files:
        print(f"  No certificate PDFs found in {cert_dir}")
        return results

    for pdf_path in pdf_files:
        text = extract_pdf_text(str(pdf_path), password)
        if not text:
            continue

        # Try declarative engine first
        cert, parser_id = parse_certificate(text, year, parser_defs)

        if cert:
            is_new = save_cert(cert)
            results.append((cert["entity"], pdf_path.name, "new" if is_new else "updated", parser_id))
        else:
            # Log improvement signal for agent consumption
            log_improvement_signal("unknown_institution", {
                "pdf_filename": pdf_path.name,
                "text_preview": text[:500],
                "text_length": len(text),
            })
            results.append(("Unknown", pdf_path.name, "skipped", None))

    return results


def main():
    parser = argparse.ArgumentParser(description="Import tax certificates from PDFs")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--dir", help="Directory with certificate PDFs")
    parser.add_argument("--password", help="PDF password (usually cédula number)")
    args = parser.parse_args()

    cert_dir = Path(args.dir) if args.dir else Path.home() / "Dropbox" / "Declaracion" / str(args.year)
    if not cert_dir.exists():
        print(f"Error: {cert_dir} does not exist")
        return

    print(f"=== Importing certificates for {args.year} from {cert_dir} ===\n")
    results = import_certificates(args.year, cert_dir, args.password)

    for entry in results:
        entity, filename, status, parser_id = entry
        parser_tag = f" [{parser_id}]" if parser_id else ""
        print(f"  [{status:>7}] {entity}{parser_tag} <- {filename}")

    agg = aggregate_certificates(args.year)
    print(f"\n=== Aggregated Tax Inputs ===")
    for key, val in agg.items():
        print(f"  {key:.<40s} ${val:>15,.0f}")

    print(f"\nCertificates saved to: {CERTS_FILE}")


if __name__ == "__main__":
    main()
