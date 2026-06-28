#!/usr/bin/env python3
"""
Form 210 filler — generates agent-browser commands to fill the DIAN MUISCA
Form 210 wizard from tax projection output.

Reads the projection from tax_projection.py (or a saved JSON file) and emits
a shell script with agent-browser commands that navigate the 15-step wizard,
snapshot each step to get fresh field refs, and fill every editable casilla.

Usage:
    # Run projection inline and generate fill script:
    python3 fill_form210.py --year 2024 > fill.sh

    # Use a previously saved projection JSON:
    python3 fill_form210.py --input projection.json > fill.sh

    # Override defaults:
    python3 fill_form210.py --year 2024 --genero 2 --ciiu 6201 --anticipo 0

    # Dry-run: print the mapping without generating shell commands:
    python3 fill_form210.py --year 2024 --dry-run
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
import textwrap
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SCHEMA_FILE = SCRIPT_DIR.parent / "templates" / "form-210-schema.json"

# ---------------------------------------------------------------------------
# Mapping: tax_projection output key  -->  (casilla, wizard step index)
#
# Only EDITABLE casillas that have a data_source in tax_projection are mapped.
# Auto-calculated (disabled) casillas are skipped by the filler.
# ---------------------------------------------------------------------------

PROJECTION_MAP = {
    # Step 3 — Patrimonio
    "form_210.patrimonio.R29_patrimonio_bruto":       (29, 2),
    # R30 deudas — not in current projection; defaults to 0
    # R31 auto-calculated

    # Step 4 — Rentas de trabajo
    "form_210.rentas_trabajo.R32_ingresos_brutos":    (32, 3),
    "form_210.rentas_trabajo.R33_incr":               (33, 3),
    # R34 auto-calculated
    "form_210.rentas_trabajo.R35_aportes_afc":        (35, 3),
    "form_210.rentas_trabajo.R36_otras_rentas_exentas": (36, 3),
    # R37 auto-calculated
    "form_210.rentas_trabajo.R38_intereses_vivienda": (38, 3),
    "form_210.rentas_trabajo.R39_otras_deducciones":  (39, 3),
    # R40, R41, R42 auto-calculated

    # Step 6 — Rentas de capital
    "form_210.rentas_capital.R58_ingresos_brutos":    (58, 5),
    "form_210.rentas_capital.R59_incr":               (59, 5),
    # R61, R73 auto-calculated

    # Step 11 — Liquidacion
    "form_210.impuesto.R130_anticipo_anterior":       (130, 10),
    "form_210.impuesto.R132_retenciones":             (132, 10),
}


def resolve_projection_value(projection: dict, dotpath: str):
    """Traverse a nested dict using a dotted path like 'form_210.patrimonio.R29_...'."""
    parts = dotpath.split(".")
    node = projection
    for p in parts:
        if isinstance(node, dict) and p in node:
            node = node[p]
        else:
            return None
    return node


def dian_round(value) -> int:
    """DIAN rounds all values to nearest thousand (no decimals)."""
    if value is None:
        return 0
    v = int(round(float(value), -3))
    return max(v, 0)


def load_projection(args) -> dict:
    """Load or compute the tax projection."""
    if args.input:
        with open(args.input) as f:
            return json.load(f)

    # Import and run tax_projection inline
    sys.path.insert(0, str(SCRIPT_DIR))
    from tax_projection import project_tax
    return project_tax(
        year=args.year,
        uvt_override=args.uvt,
        anticipo_anterior=args.anticipo,
        nit_suffix=args.nit_suffix,
    )


def load_schema() -> dict:
    """Load the form-210-schema.json."""
    with open(SCHEMA_FILE) as f:
        return json.load(f)


def build_fill_plan(projection: dict, genero: str, ciiu: str) -> list:
    """
    Build an ordered list of fill actions grouped by wizard step.

    Each action is a dict:
      {step, casilla, label, field_type, value, action}
    where action is one of: fill_text, select_combo, select_radio.
    """
    plan = []

    # ── Step 1: Datos Declarante ──────────────────────────────────
    plan.append({
        "step": 0, "casilla": 286,
        "label": "Genero",
        "field_type": "combobox",
        "value": genero,
        "action": "select_combo",
    })
    plan.append({
        "step": 0, "casilla": 24,
        "label": "Actividad economica principal",
        "field_type": "combobox",
        "value": ciiu,
        "action": "select_combo",
    })

    # ── Step 2: Deduccion imputable sin limitantes ────────────────
    einvoices = projection.get("einvoices", {})
    has_einvoices = einvoices.get("count", 0) > 0
    total_facturado = dian_round(einvoices.get("total_facturado", 0))

    plan.append({
        "step": 1, "casilla": 299,
        "label": "Factura electronica",
        "field_type": "radio",
        "value": "Si" if has_einvoices else "No",
        "action": "select_radio",
    })
    if has_einvoices:
        plan.append({
            "step": 1, "casilla": 297,
            "label": "Valor compras con factura electronica",
            "field_type": "textbox",
            "value": total_facturado,
            "action": "fill_text",
        })

    # Default No for the remaining yes/no questions
    for cas, label in [
        (245, "Victima del conflicto armado"),
        (247, "Beneficiario convenio doble tributacion"),
        (249, "Residente fiscal"),
        (251, "Obligado a llevar contabilidad"),
    ]:
        plan.append({
            "step": 1, "casilla": cas,
            "label": label,
            "field_type": "radio",
            "value": "No",
            "action": "select_radio",
        })

    # ── Steps 3-14: Mapped casillas from projection ──────────────
    for dotpath, (casilla, step_idx) in sorted(PROJECTION_MAP.items(), key=lambda x: (x[1][1], x[1][0])):
        raw = resolve_projection_value(projection, dotpath)
        value = dian_round(raw)
        # Extract the label from the key (e.g. R32_ingresos_brutos -> R32 Ingresos brutos)
        key_tail = dotpath.rsplit(".", 1)[-1]
        label = key_tail.replace("_", " ")
        plan.append({
            "step": step_idx,
            "casilla": casilla,
            "label": label,
            "field_type": "textbox",
            "value": value,
            "action": "fill_text",
        })

    return plan


def emit_shell_script(plan: list, dry_run: bool = False):
    """
    Emit a bash script with agent-browser commands.

    The generated script:
    1. Groups actions by wizard step
    2. Clicks the step counter to navigate
    3. Snapshots to get fresh field refs
    4. Fills each field
    5. Clicks Siguiente to advance

    The script is idempotent — re-running skips already-filled fields
    (agent-browser type commands overwrite field content).
    """
    lines = []
    lines.append("#!/usr/bin/env bash")
    lines.append("# ================================================================")
    lines.append("# DIAN Form 210 Filler — Auto-generated by fill_form210.py")
    lines.append("# ================================================================")
    lines.append("#")
    lines.append("# INSTRUCTIONS:")
    lines.append("#   1. Open the DIAN MUISCA Form 210 wizard in agent-browser")
    lines.append("#   2. Run this script (or paste commands one step at a time)")
    lines.append("#   3. Review each step before clicking Siguiente")
    lines.append("#   4. Field refs change between sessions — if a ref fails,")
    lines.append("#      re-run the snapshot command for that step and update the ref")
    lines.append("#")
    lines.append("# This script uses placeholder refs (<REF_casilla_NNN>).")
    lines.append("# After each snapshot, replace them with the actual refs from")
    lines.append("# the snapshot output.")
    lines.append("#")
    lines.append("# DIAN rounds all values to nearest thousand (no decimals).")
    lines.append("# ================================================================")
    lines.append("")
    lines.append("set -euo pipefail")
    lines.append("")

    if dry_run:
        lines.append("# DRY RUN — no commands will be executed")
        lines.append("")

    # Group by step
    steps = {}
    for action in plan:
        s = action["step"]
        steps.setdefault(s, []).append(action)

    step_titles = {
        0: "Datos del Declarante",
        1: "Deduccion Imputable sin limitantes",
        2: "Patrimonio",
        3: "Rentas de trabajo",
        4: "Rentas de trabajo no relacion laboral",
        5: "Rentas de capital",
        6: "Rentas no laborales",
        7: "Cedula general",
        8: "Cedula de pensiones",
        9: "Dividendos y participaciones",
        10: "Liquidacion privada",
        11: "Ganancias ocasionales",
        12: "Anticipo y saldo a favor",
        13: "Saldo a pagar o a favor",
        14: "Firmar y presentar",
    }

    for step_idx in sorted(steps.keys()):
        actions = steps[step_idx]
        title = step_titles.get(step_idx, f"Step {step_idx + 1}")

        lines.append(f"# ── Step {step_idx + 1}: {title} {'─' * max(1, 50 - len(title))}")
        lines.append("")

        # Navigate to step
        lines.append(f"# Navigate to step {step_idx + 1}")
        lines.append(f'agent-browser js "document.querySelectorAll(\'.step-counter\')[{step_idx}].click()"')
        lines.append("")

        # Snapshot to get field refs
        lines.append(f"# Snapshot step {step_idx + 1} to get field refs")
        lines.append("agent-browser snapshot")
        lines.append("")

        lines.append("# Fill fields (replace <REF_casilla_NNN> with actual refs from snapshot)")

        for act in actions:
            cas = act["casilla"]
            label = act["label"]
            value = act["value"]
            field_type = act["field_type"]
            ref_placeholder = f"<REF_casilla_{cas}>"

            lines.append(f"# Casilla {cas}: {label}")

            if act["action"] == "fill_text":
                if dry_run:
                    lines.append(f"#   -> Would fill casilla {cas} with {value}")
                else:
                    lines.append(f'agent-browser click "{ref_placeholder}"')
                    lines.append(f'agent-browser clear-and-type "{ref_placeholder}" "{value}"')
            elif act["action"] == "select_combo":
                if dry_run:
                    lines.append(f"#   -> Would select '{value}' in combobox casilla {cas}")
                else:
                    lines.append(f'agent-browser click "{ref_placeholder}"')
                    lines.append(f'agent-browser select "{ref_placeholder}" "{value}"')
            elif act["action"] == "select_radio":
                if dry_run:
                    lines.append(f"#   -> Would select radio '{value}' for casilla {cas}")
                else:
                    # Radio buttons: click the option matching the value
                    lines.append(f'agent-browser click "{ref_placeholder}_{value}"')
            lines.append("")

        # Advance to next step
        lines.append(f"# Advance from step {step_idx + 1}")
        lines.append('agent-browser click "Siguiente"')
        lines.append("")

    return "\n".join(lines)


def print_dry_run_table(plan: list):
    """Print a human-readable table of all fill actions."""
    print(f"\n{'='*80}")
    print("  FORM 210 FILL PLAN (dry run)")
    print(f"{'='*80}")
    print(f"  {'Step':>4}  {'Casilla':>7}  {'Action':<14}  {'Value':>15}  Label")
    print(f"  {'─'*4}  {'─'*7}  {'─'*14}  {'─'*15}  {'─'*30}")
    for act in plan:
        step_display = act["step"] + 1
        value_str = str(act["value"])
        if isinstance(act["value"], (int, float)) and act["value"] > 0:
            value_str = f"${act['value']:,.0f}"
        print(f"  {step_display:>4}  {act['casilla']:>7}  {act['action']:<14}  {value_str:>15}  {act['label']}")
    print(f"\n  Total actions: {len(plan)}")
    print()


def print_mapping_json(plan: list):
    """Print the fill plan as JSON for programmatic consumption."""
    output = []
    for act in plan:
        output.append({
            "step": act["step"] + 1,
            "casilla": act["casilla"],
            "label": act["label"],
            "field_type": act["field_type"],
            "value": act["value"],
            "action": act["action"],
        })
    print(json.dumps(output, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="Generate agent-browser commands to fill DIAN Form 210"
    )
    parser.add_argument("--year", type=int, default=2024,
                        help="Tax year (default: 2024)")
    parser.add_argument("--uvt", type=float,
                        help="Override UVT value")
    parser.add_argument("--anticipo", type=float, default=0,
                        help="Anticipo renta from prior year (R130)")
    parser.add_argument("--nit-suffix",
                        help="Last 2 digits of CC/NIT for deadline lookup")
    parser.add_argument("--input", type=str,
                        help="Path to a saved tax projection JSON (skip running projection)")
    parser.add_argument("--genero", type=str, default="2 - Masculino",
                        help="Casilla 286 value (default: '2 - Masculino')")
    parser.add_argument("--ciiu", type=str, default="6201",
                        help="Casilla 24 CIIU code (default: 6201 — software development)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print fill plan table without generating shell commands")
    parser.add_argument("--json", action="store_true",
                        help="Output fill plan as JSON")
    parser.add_argument("--output", type=str,
                        help="Write shell script to file instead of stdout")

    args = parser.parse_args()

    # Load or compute projection
    projection = load_projection(args)

    # Build fill plan
    plan = build_fill_plan(projection, genero=args.genero, ciiu=args.ciiu)

    if args.dry_run:
        print_dry_run_table(plan)
        return

    if args.json:
        print_mapping_json(plan)
        return

    # Generate shell script
    script = emit_shell_script(plan)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(script)
        out_path.chmod(0o755)
        print(f"Fill script written to {out_path}", file=sys.stderr)
    else:
        print(script)


if __name__ == "__main__":
    main()
