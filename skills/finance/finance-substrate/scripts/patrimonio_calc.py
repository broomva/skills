#!/usr/bin/env python3
"""
Patrimonio (net worth) calculator for Colombian Form 210.

Aggregates assets and liabilities from multiple data sources to compute:
  R29 — Patrimonio bruto (gross assets)
  R30 — Deudas (liabilities)
  R31 — Patrimonio líquido (net worth = R29 - R30)

Data sources:
  1. certificates.jsonl  — bank saldos, investment funds, pension, cesantías
  2. exogena.jsonl        — third-party reported assets (real estate, vehicle, stocks)
  3. Manual entries       — cash, foreign accounts, crypto, etc.

Deduplication: when the same asset appears in both certificates AND exogena,
the higher value is used and the overlap is flagged.

Usage:
    python3 patrimonio_calc.py --year 2024
    python3 patrimonio_calc.py --year 2024 --detail
    python3 patrimonio_calc.py --year 2024 --add-asset "Crypto BTC" 5000000
    python3 patrimonio_calc.py --year 2024 --add-debt "Préstamo familiar" 3000000
    python3 patrimonio_calc.py --year 2024 --json
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
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

DATA_DIR = Path.home() / ".finance-substrate"
CERTS_FILE = DATA_DIR / "tax" / "certificates.jsonl"
EXOGENA_FILE = DATA_DIR / "tax" / "exogena.jsonl"

# ────────────────────────────────────────────────────────────────────
# Data model
# ────────────────────────────────────────────────────────────────────

@dataclass
class PatrimonioItem:
    """Single asset or liability line item."""
    name: str
    value: float
    source: str           # "certificate", "exogena", "manual"
    category: str         # e.g. "cuentas", "inversiones", "vehiculo", "deuda"
    entity: str = ""
    detail: str = ""
    overlap: bool = False
    overlap_note: str = ""


@dataclass
class PatrimonioReport:
    """Full patrimonio breakdown."""
    year: int
    assets: list = field(default_factory=list)
    debts: list = field(default_factory=list)
    overlaps: list = field(default_factory=list)
    r29_patrimonio_bruto: float = 0
    r30_deudas: float = 0
    r31_patrimonio_liquido: float = 0


# ────────────────────────────────────────────────────────────────────
# Loaders
# ────────────────────────────────────────────────────────────────────

def load_certificate_patrimonio(year: int) -> list[PatrimonioItem]:
    """Extract patrimonio-related fields from certificates."""
    items: list[PatrimonioItem] = []
    if not CERTS_FILE.exists():
        return items

    # Map tax_summary keys to (category, display_name)
    field_map = {
        "patrimonio_cuentas": ("cuentas", "Cuentas bancarias"),
        "patrimonio_cuenta": ("cuentas", "Cuenta bancaria"),
        "patrimonio_inversiones": ("inversiones", "Inversiones"),
        "patrimonio_fondos": ("fondos", "Fondos de inversión colectiva"),
        "patrimonio_caja": ("caja", "Saldo en caja"),
        "patrimonio_acciones": ("acciones", "Acciones"),
        "patrimonio_cesantias": ("cesantias", "Cesantías"),
        "patrimonio_voluntaria": ("voluntaria", "Pensión voluntaria"),
    }

    with open(CERTS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("year") != year or rec.get("type") != "certificado-tributario":
                continue

            entity = rec.get("entity", "")
            ts = rec.get("tax_summary", {})

            for key, (category, display) in field_map.items():
                val = ts.get(key, 0)
                if val and val > 0:
                    items.append(PatrimonioItem(
                        name=f"{display} ({entity})",
                        value=val,
                        source="certificate",
                        category=category,
                        entity=entity,
                    ))

    return items


def load_certificate_deudas(year: int) -> list[PatrimonioItem]:
    """Extract deuda (liability) fields from certificates."""
    items: list[PatrimonioItem] = []
    if not CERTS_FILE.exists():
        return items

    with open(CERTS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("year") != year or rec.get("type") != "certificado-tributario":
                continue

            entity = rec.get("entity", "")
            ts = rec.get("tax_summary", {})
            val = ts.get("deuda_patrimonio", 0)
            if val and val > 0:
                items.append(PatrimonioItem(
                    name=f"Deuda ({entity})",
                    value=val,
                    source="certificate",
                    category="deuda",
                    entity=entity,
                ))

    return items


def load_exogena_patrimonio(year: int) -> list[PatrimonioItem]:
    """Extract R29 patrimonio items from exogena third-party reports."""
    items: list[PatrimonioItem] = []
    if not EXOGENA_FILE.exists():
        return items

    with open(EXOGENA_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("year") != year:
                continue

            tax_use = str(rec.get("tax_use", ""))
            tax_use_lower = tax_use.lower()
            detail = rec.get("detail", "")
            detail_lower = detail.lower()
            value = rec.get("value", 0)
            entity = rec.get("reporter_name", "")

            # Skip non-patrimonio items and reference-only entries
            is_patrimonio = (
                "r29" in tax_use_lower
                or "patrimonio bruto" in tax_use_lower
                or ("patrimonio" in tax_use_lower and "tope" not in tax_use_lower)
            )
            is_reference = "declarado en el año anterior" in detail_lower
            is_tope_only = tax_use_lower.startswith("tope") and "r29" not in tax_use_lower

            if not is_patrimonio or is_reference or is_tope_only:
                continue
            if value <= 0:
                continue

            # Classify the asset
            category = _classify_exogena_asset(detail_lower)

            items.append(PatrimonioItem(
                name=f"{detail} ({entity})",
                value=value,
                source="exogena",
                category=category,
                entity=entity,
                detail=detail,
            ))

    return items


def load_exogena_deudas(year: int) -> list[PatrimonioItem]:
    """Extract R30 deuda items from exogena."""
    items: list[PatrimonioItem] = []
    if not EXOGENA_FILE.exists():
        return items

    with open(EXOGENA_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("year") != year:
                continue

            tax_use = str(rec.get("tax_use", ""))
            if "R30" not in tax_use:
                continue

            value = rec.get("value", 0)
            if value <= 0:
                continue

            entity = rec.get("reporter_name", "")
            detail = rec.get("detail", "")

            items.append(PatrimonioItem(
                name=f"{detail} ({entity})",
                value=value,
                source="exogena",
                category="deuda",
                entity=entity,
                detail=detail,
            ))

    return items


def _classify_exogena_asset(detail_lower: str) -> str:
    """Classify an exogena patrimonio item into a category."""
    if "saldo cuentas" in detail_lower or "cuenta" in detail_lower:
        return "cuentas"
    if "avalúo vehículo" in detail_lower or "vehículo" in detail_lower:
        return "vehiculo"
    if "inversión" in detail_lower or "colectiva" in detail_lower:
        return "fondos"
    if "acciones" in detail_lower or "accion" in detail_lower:
        return "acciones"
    if "cesantías" in detail_lower:
        return "cesantias"
    if "voluntari" in detail_lower:
        return "voluntaria"
    if "cobrar" in detail_lower or "inmueble" in detail_lower or "bien raíz" in detail_lower:
        return "bienes_raices"
    if "ahorro" in detail_lower and "afc" in detail_lower:
        return "afc"
    return "otros"


# ────────────────────────────────────────────────────────────────────
# Deduplication engine
# ────────────────────────────────────────────────────────────────────

def _normalize_entity(entity: str) -> str:
    """Normalize entity name for overlap matching."""
    e = entity.upper().strip()
    # Remove legal suffixes
    for suffix in [" S.A.S.", " S.A.S", " S.A.", " S.A", " LTDA.", " LTDA"]:
        if e.endswith(suffix):
            e = e[: -len(suffix)]
    # Strip common prefixes that vary between sources
    for prefix in ["BANCO ", "FONDO DE "]:
        if e.startswith(prefix):
            e = e[len(prefix):]
    # Collapse multi-word fund names to their core institution
    # e.g., "SKANDIA FONDO DE PENSIONES VOLUNTARIAS" -> "SKANDIA"
    #        "SKANDIA FONDO DE CESANTIAS" -> "SKANDIA"
    for marker in [" FONDO DE ", " COMPAÑÍA DE ", " COMPAÑIA DE "]:
        if marker in e:
            e = e[: e.index(marker)]
            break
    return e.strip()


def deduplicate_assets(
    cert_items: list[PatrimonioItem],
    exog_items: list[PatrimonioItem],
) -> tuple[list[PatrimonioItem], list[dict]]:
    """
    Deduplicate assets that appear in both certificates and exogena.

    Strategy: match by (normalized_entity, category). When overlap is found,
    keep the higher value and flag both items.

    Returns: (merged_items, overlap_records)
    """
    merged: list[PatrimonioItem] = []
    overlaps: list[dict] = []

    # Index cert items by (entity_norm, category)
    cert_index: dict[tuple[str, str], list[PatrimonioItem]] = {}
    for item in cert_items:
        key = (_normalize_entity(item.entity), item.category)
        cert_index.setdefault(key, []).append(item)

    matched_cert_keys: set[tuple[str, str]] = set()

    for exog_item in exog_items:
        key = (_normalize_entity(exog_item.entity), exog_item.category)
        cert_matches = cert_index.get(key, [])

        if cert_matches:
            # Overlap detected — use highest value from either source
            cert_total = sum(c.value for c in cert_matches)
            if exog_item.value >= cert_total:
                winner = exog_item
                loser_source = "certificate"
                loser_value = cert_total
            else:
                # Use individual cert items (may be more granular)
                winner = PatrimonioItem(
                    name=cert_matches[0].name,
                    value=cert_total,
                    source="certificate",
                    category=cert_matches[0].category,
                    entity=cert_matches[0].entity,
                )
                loser_source = "exogena"
                loser_value = exog_item.value

            winner.overlap = True
            winner.overlap_note = (
                f"OVERLAP: cert={cert_total:,.0f} vs exog={exog_item.value:,.0f} "
                f"-> used {winner.source} ({winner.value:,.0f})"
            )
            merged.append(winner)
            matched_cert_keys.add(key)

            overlaps.append({
                "entity": exog_item.entity,
                "category": exog_item.category,
                "cert_value": cert_total,
                "exog_value": exog_item.value,
                "used_source": winner.source,
                "used_value": winner.value,
            })
        else:
            # No overlap — keep exogena item as-is
            merged.append(exog_item)

    # Add cert items that had no exogena match
    for key, items in cert_index.items():
        if key not in matched_cert_keys:
            merged.extend(items)

    return merged, overlaps


# ────────────────────────────────────────────────────────────────────
# Main calculation
# ────────────────────────────────────────────────────────────────────

def compute_patrimonio(
    year: int,
    manual_assets: Optional[list[tuple[str, float]]] = None,
    manual_debts: Optional[list[tuple[str, float]]] = None,
) -> PatrimonioReport:
    """Compute full patrimonio report for the given year."""

    # 1. Load from certificates
    cert_assets = load_certificate_patrimonio(year)
    cert_debts = load_certificate_deudas(year)

    # 2. Load from exogena
    exog_assets = load_exogena_patrimonio(year)
    exog_debts = load_exogena_deudas(year)

    # 3. Deduplicate assets across sources
    merged_assets, overlaps = deduplicate_assets(cert_assets, exog_assets)

    # 4. Add manual assets
    if manual_assets:
        for name, value in manual_assets:
            merged_assets.append(PatrimonioItem(
                name=name,
                value=value,
                source="manual",
                category="otros",
            ))

    # 5. Merge debts (certificates + exogena, dedup by entity)
    merged_debts, debt_overlaps = deduplicate_assets(cert_debts, exog_debts)

    # 6. Add manual debts
    if manual_debts:
        for name, value in manual_debts:
            merged_debts.append(PatrimonioItem(
                name=name,
                value=value,
                source="manual",
                category="deuda",
            ))

    # 7. Compute totals
    r29 = sum(item.value for item in merged_assets)
    r30 = sum(item.value for item in merged_debts)
    r31 = max(0, r29 - r30)

    return PatrimonioReport(
        year=year,
        assets=merged_assets,
        debts=merged_debts,
        overlaps=overlaps + debt_overlaps,
        r29_patrimonio_bruto=r29,
        r30_deudas=r30,
        r31_patrimonio_liquido=r31,
    )


# ────────────────────────────────────────────────────────────────────
# Output formatters
# ────────────────────────────────────────────────────────────────────

CATEGORY_LABELS = {
    "cuentas": "Cuentas bancarias",
    "fondos": "Fondos de inversión",
    "acciones": "Acciones / participaciones",
    "cesantias": "Cesantías",
    "voluntaria": "Pensión voluntaria",
    "caja": "Efectivo / caja",
    "afc": "Ahorro AFC",
    "vehiculo": "Vehículos",
    "bienes_raices": "Bienes raíces / inmuebles",
    "otros": "Otros activos",
    "deuda": "Deudas",
}


def print_report(report: PatrimonioReport, detail: bool = False):
    """Print formatted patrimonio report."""
    w = 70

    print(f"\n{'=' * w}")
    print(f"  PATRIMONIO — Año Gravable {report.year}  (Form 210: R29-R31)")
    print(f"{'=' * w}")
    print()

    # ── Summary ──
    print(f"  R29  Patrimonio bruto:       ${report.r29_patrimonio_bruto:>18,.0f}")
    print(f"  R30  Deudas:                 ${report.r30_deudas:>18,.0f}")
    print(f"  {'─' * (w - 4)}")
    print(f"  R31  Patrimonio líquido:     ${report.r31_patrimonio_liquido:>18,.0f}")
    print()

    if detail:
        _print_detail(report)


def _print_detail(report: PatrimonioReport):
    """Print detailed breakdown by category and source."""
    w = 70

    # ── Assets by category ──
    print(f"  {'─' * (w - 4)}")
    print(f"  DETALLE ACTIVOS (R29)")
    print(f"  {'─' * (w - 4)}")

    # Group by category
    by_cat: dict[str, list[PatrimonioItem]] = {}
    for item in report.assets:
        by_cat.setdefault(item.category, []).append(item)

    for cat in sorted(by_cat.keys(), key=lambda c: CATEGORY_LABELS.get(c, c)):
        items = by_cat[cat]
        cat_total = sum(i.value for i in items)
        label = CATEGORY_LABELS.get(cat, cat.title())
        print(f"\n  {label} (subtotal: ${cat_total:,.0f})")

        for item in sorted(items, key=lambda i: -i.value):
            src_tag = f"[{item.source[:4].upper()}]"
            overlap_flag = " *OVERLAP*" if item.overlap else ""
            print(f"    {src_tag} {item.name[:45]:<45s} ${item.value:>14,.0f}{overlap_flag}")
            if item.overlap and item.overlap_note:
                print(f"           {item.overlap_note}")

    print()

    # ── Debts ──
    print(f"  {'─' * (w - 4)}")
    print(f"  DETALLE DEUDAS (R30)")
    print(f"  {'─' * (w - 4)}")

    if not report.debts:
        print("    (ninguna deuda registrada)")
    else:
        for item in sorted(report.debts, key=lambda i: -i.value):
            src_tag = f"[{item.source[:4].upper()}]"
            overlap_flag = " *OVERLAP*" if item.overlap else ""
            print(f"    {src_tag} {item.name[:45]:<45s} ${item.value:>14,.0f}{overlap_flag}")
            if item.overlap and item.overlap_note:
                print(f"           {item.overlap_note}")

    print()

    # ── Overlaps summary ──
    if report.overlaps:
        print(f"  {'─' * (w - 4)}")
        print(f"  SOLAPAMIENTOS DETECTADOS ({len(report.overlaps)})")
        print(f"  {'─' * (w - 4)}")
        for ov in report.overlaps:
            diff = abs(ov["cert_value"] - ov["exog_value"])
            print(f"    {ov['entity'][:30]:<30s} [{ov['category']}]")
            print(f"      Certificado: ${ov['cert_value']:>14,.0f}")
            print(f"      Exógena:     ${ov['exog_value']:>14,.0f}")
            print(f"      Diferencia:  ${diff:>14,.0f}  -> usado: {ov['used_source']} (${ov['used_value']:,.0f})")
        print()

    # ── Source summary ──
    print(f"  {'─' * (w - 4)}")
    print(f"  RESUMEN POR FUENTE")
    print(f"  {'─' * (w - 4)}")
    source_totals: dict[str, float] = {}
    for item in report.assets:
        source_totals[item.source] = source_totals.get(item.source, 0) + item.value
    for src, total in sorted(source_totals.items()):
        count = sum(1 for i in report.assets if i.source == src)
        print(f"    {src:<12s}: {count:>3d} items  ${total:>18,.0f}")
    print()


def to_json(report: PatrimonioReport) -> dict:
    """Serialize report to JSON-compatible dict."""
    return {
        "year": report.year,
        "form_210": {
            "R29_patrimonio_bruto": round(report.r29_patrimonio_bruto),
            "R30_deudas": round(report.r30_deudas),
            "R31_patrimonio_liquido": round(report.r31_patrimonio_liquido),
        },
        "assets": [
            {
                "name": a.name,
                "value": round(a.value),
                "source": a.source,
                "category": a.category,
                "entity": a.entity,
                "overlap": a.overlap,
                "overlap_note": a.overlap_note,
            }
            for a in sorted(report.assets, key=lambda x: -x.value)
        ],
        "debts": [
            {
                "name": d.name,
                "value": round(d.value),
                "source": d.source,
                "category": d.category,
                "entity": d.entity,
                "overlap": d.overlap,
                "overlap_note": d.overlap_note,
            }
            for d in sorted(report.debts, key=lambda x: -x.value)
        ],
        "overlaps": report.overlaps,
        "totals_by_category": _category_totals(report),
        "totals_by_source": _source_totals(report),
    }


def _category_totals(report: PatrimonioReport) -> dict:
    totals: dict[str, float] = {}
    for item in report.assets:
        totals[item.category] = totals.get(item.category, 0) + item.value
    return {k: round(v) for k, v in sorted(totals.items(), key=lambda x: -x[1])}


def _source_totals(report: PatrimonioReport) -> dict:
    totals: dict[str, float] = {}
    for item in report.assets:
        totals[item.source] = totals.get(item.source, 0) + item.value
    return {k: round(v) for k, v in sorted(totals.items(), key=lambda x: -x[1])}


# ────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patrimonio (net worth) calculator for Form 210 (R29/R30/R31)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --year 2024
  %(prog)s --year 2024 --detail
  %(prog)s --year 2024 --add-asset "Crypto BTC" 5000000
  %(prog)s --year 2024 --add-debt "Préstamo familiar" 3000000 --detail
  %(prog)s --year 2024 --json
        """,
    )
    parser.add_argument("--year", type=int, required=True, help="Tax year (año gravable)")
    parser.add_argument(
        "--add-asset", nargs=2, action="append", metavar=("NAME", "VALUE"),
        help="Add manual asset entry (repeatable). Example: --add-asset \"Cash\" 1000000",
    )
    parser.add_argument(
        "--add-debt", nargs=2, action="append", metavar=("NAME", "VALUE"),
        help="Add manual debt entry (repeatable). Example: --add-debt \"Loan\" 5000000",
    )
    parser.add_argument("--detail", action="store_true", help="Show full breakdown by source and category")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Machine-readable JSON output")
    return parser.parse_args()


def main():
    args = parse_args()

    # Parse manual entries
    manual_assets = None
    if args.add_asset:
        manual_assets = []
        for name, val_str in args.add_asset:
            try:
                manual_assets.append((name, float(val_str)))
            except ValueError:
                print(f"Error: invalid asset value '{val_str}' for '{name}'", file=sys.stderr)
                sys.exit(1)

    manual_debts = None
    if args.add_debt:
        manual_debts = []
        for name, val_str in args.add_debt:
            try:
                manual_debts.append((name, float(val_str)))
            except ValueError:
                print(f"Error: invalid debt value '{val_str}' for '{name}'", file=sys.stderr)
                sys.exit(1)

    report = compute_patrimonio(
        year=args.year,
        manual_assets=manual_assets,
        manual_debts=manual_debts,
    )

    if args.json_output:
        print(json.dumps(to_json(report), indent=2, ensure_ascii=False))
    else:
        print_report(report, detail=args.detail)


if __name__ == "__main__":
    main()
