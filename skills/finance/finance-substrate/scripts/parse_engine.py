#!/usr/bin/env python3
"""
Generic certificate parser engine — interprets declarative parser definitions
(parsers/*.json) against PDF-extracted text to produce structured tax data.

This replaces hardcoded per-institution parser functions with a data-driven
approach that agents can extend by creating new JSON definitions.

Usage:
    # Parse certificates using definitions
    from parse_engine import load_parsers, parse_certificate

    # CLI: validate all parser definitions
    python3 parse_engine.py --validate

    # CLI: show coverage report
    python3 parse_engine.py --coverage
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
import re
import sys
from pathlib import Path

PARSERS_DIR = Path(__file__).parent.parent / "parsers"
SCHEMA_PATH = Path(__file__).parent.parent / "templates" / "parser-schema.json"
CONTROL_DIR = Path(__file__).parent.parent / ".control"


# ─── Amount Parsing ────────────────────────────────────────────────

def parse_co_amount(s: str) -> float:
    """Parse Colombian-formatted amount: $55.300.000,00 or 1.000.000 or 55,300,000.00."""
    if not s:
        return 0.0
    cleaned = re.sub(r"[$\s]", "", s.strip())
    if not cleaned:
        return 0.0

    # Both separators present: determine which is decimal
    if "," in cleaned and "." in cleaned:
        if cleaned.rindex(",") > cleaned.rindex("."):
            # Colombian: 1.234.567,89 → dots=thousands, comma=decimal
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # US: 1,234,567.89 → commas=thousands
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Only commas: check if it's decimal or thousands
        parts = cleaned.split(",")
        if len(parts[-1]) <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(".") > 1:
        # Multiple dots, no commas: 1.000.000 → dots are thousands separators
        cleaned = cleaned.replace(".", "")
    # Single dot: could be decimal (40.50) or ambiguous
    # If single dot and exactly 3 digits after: likely thousands (40.000 = 40000)
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            # 40.000 → 40000, 1.360 → 1360
            cleaned = cleaned.replace(".", "")

    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_amount(s: str, fmt: str = "co_amount") -> float:
    if fmt == "integer":
        return float(int(parse_co_amount(s)))
    return parse_co_amount(s)


# ─── Parser Definition Loading ─────────────────────────────────────

def load_parsers(parsers_dir: Path | None = None) -> list[dict]:
    """Load all parser definitions, sorted by priority."""
    d = parsers_dir or PARSERS_DIR
    if not d.exists():
        return []
    defs = []
    for f in sorted(d.glob("*.json")):
        with open(f) as fp:
            defn = json.load(fp)
            defn["_source_file"] = f.name
            defs.append(defn)
    defs.sort(key=lambda x: x.get("priority", 999))
    return defs


# ─── Institution Matching ──────────────────────────────────────────

def match_institution(text: str, parser_def: dict) -> bool:
    """Test identification rules against PDF text."""
    ident = parser_def.get("identification", {})
    case_sensitive = ident.get("case_sensitive", False)
    check_text = text if case_sensitive else text.upper()

    require = ident.get("require_any", [])
    reject = ident.get("reject_any", [])

    # Must match at least one require pattern
    matched = False
    for r in require:
        needle = r if case_sensitive else r.upper()
        if needle in check_text:
            matched = True
            break
    if not matched:
        return False

    # Must not match any reject pattern
    for r in reject:
        needle = r if case_sensitive else r.upper()
        if needle in check_text:
            return False

    return True


# ─── Field Extraction Methods ──────────────────────────────────────

def _get_section_text(full_text: str, section: dict) -> str:
    """Locate section anchor and return text from anchor onwards."""
    anchor = section.get("anchor")
    if not anchor:
        return full_text

    pattern = anchor.get("pattern", "")
    anchor_type = anchor.get("type", "string_find")
    flags_str = anchor.get("flags", "")

    if anchor_type == "string_find":
        idx = full_text.find(pattern)
        if idx >= 0:
            return full_text[idx:]
        return ""
    else:
        flags = 0
        if "DOTALL" in flags_str:
            flags |= re.DOTALL
        if "IGNORECASE" in flags_str:
            flags |= re.IGNORECASE
        m = re.search(pattern, full_text, flags)
        if m:
            return full_text[m.start():]
        return ""


def extract_field(text: str, field: dict) -> float:
    """Dispatch to the appropriate extraction method."""
    method = field.get("method", "regex")
    fmt = field.get("format", "co_amount")

    if method == "label_then_amount":
        label = field.get("label", "")
        # Label on line, dollar amount on same or next line
        pattern = re.escape(label) + r"[^\n$]*\$?([\d.,]+)"
        m = re.search(pattern, text)
        if m:
            return parse_amount(m.group(1), fmt)
        # Try: label on one line, amount on next
        pattern2 = re.escape(label) + r"\s*\n\$?([\d.,]+)"
        m = re.search(pattern2, text)
        if m:
            return parse_amount(m.group(1), fmt)
        return 0.0

    elif method == "dollar_amounts_after_anchor":
        idx = field.get("index", 0)
        amounts = re.findall(r"\$([\d.,]+)", text)
        if idx < len(amounts):
            return parse_amount(amounts[idx], fmt)
        return 0.0

    elif method == "regex":
        pattern = field.get("pattern", "")
        group = field.get("group", 1)
        flags = 0
        if "DOTALL" in field.get("flags", ""):
            flags |= re.DOTALL
        if "IGNORECASE" in field.get("flags", ""):
            flags |= re.IGNORECASE
        m = re.search(pattern, text, flags)
        if m and group <= len(m.groups()):
            return parse_amount(m.group(group), fmt)
        return 0.0

    elif method == "line_after_label":
        label = field.get("label", "")
        pattern = re.escape(label) + r"\s*\n([\d.,]+)"
        m = re.search(pattern, text)
        if m:
            return parse_amount(m.group(1), fmt)
        return 0.0

    elif method == "sum_all_regex_matches":
        pattern = field.get("pattern", "")
        group = field.get("group", 1)
        total = 0.0
        for m in re.finditer(pattern, text):
            if group <= len(m.groups()):
                total += parse_amount(m.group(group), fmt)
        return total

    return 0.0


# ─── Expression Evaluator (safe, no eval) ──────────────────────────

def _resolve_path(path: str, context: dict) -> float:
    """Resolve a dotted path like 'sections.afc.aportes_directos'."""
    parts = path.strip().split(".")
    current = context
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part, 0)
        else:
            return 0.0
    try:
        return float(current)
    except (TypeError, ValueError):
        return 0.0


def evaluate_expression(expr: str, context: dict) -> float:
    """Evaluate simple arithmetic: 'a.b + c.d * 0.5'. Safe — no eval()."""
    # Tokenize: numbers, dotted paths, operators
    tokens = re.findall(r"[\d.]+(?:\.\d+)?|[a-z_]+(?:\.[a-z_]+)*|[+\-*/()]", expr.strip(), re.IGNORECASE)

    # Convert to values
    values = []
    for token in tokens:
        if token in "+-*/()":
            values.append(token)
        elif re.match(r"^\d", token):
            try:
                values.append(float(token))
            except ValueError:
                values.append(0.0)
        else:
            values.append(_resolve_path(token, context))

    # Simple left-to-right evaluation with operator precedence
    # Handle * and / first, then + and -
    # First pass: resolve * and /
    i = 0
    reduced = []
    while i < len(values):
        if i + 2 < len(values) and values[i + 1] in ("*", "/"):
            left = float(values[i]) if not isinstance(values[i], str) else 0.0
            right = float(values[i + 2]) if not isinstance(values[i + 2], str) else 0.0
            if values[i + 1] == "*":
                reduced.append(left * right)
            elif values[i + 1] == "/" and right != 0:
                reduced.append(left / right)
            else:
                reduced.append(0.0)
            i += 3
        else:
            reduced.append(values[i])
            i += 1

    # Second pass: resolve + and -
    result = float(reduced[0]) if reduced and not isinstance(reduced[0], str) else 0.0
    i = 1
    while i + 1 < len(reduced):
        op = reduced[i]
        val = float(reduced[i + 1]) if not isinstance(reduced[i + 1], str) else 0.0
        if op == "+":
            result += val
        elif op == "-":
            result -= val
        i += 2

    return result


# ─── Certificate Parsing ──────────────────────────────────────────

def _substitute_templates(field: dict, year: int) -> dict:
    """Replace {year} placeholders in field patterns."""
    result = dict(field)
    for key in ("pattern", "label"):
        if key in result and "{year}" in str(result[key]):
            result[key] = result[key].replace("{year}", str(year))
    return result


def extract_sections(full_text: str, parser_def: dict, year: int = 0) -> dict:
    """Process all sections in a parser definition, return nested field values."""
    result = {}
    for section in parser_def.get("sections", []):
        section_id = section["id"]
        section_text = _get_section_text(full_text, section)
        if not section_text:
            result[section_id] = {}
            continue

        fields = {}
        for field in section.get("fields", []):
            resolved_field = _substitute_templates(field, year) if year else field
            scope = resolved_field.get("scope", "section")
            target_text = full_text if scope == "full_text" else section_text
            fields[resolved_field["key"]] = extract_field(target_text, resolved_field)
        result[section_id] = fields

    return result


def compute_fields(sections: dict, computed: list) -> dict:
    """Evaluate computed field expressions."""
    context = {"sections": sections}
    result = {}
    for cf in computed:
        result[cf["key"]] = evaluate_expression(cf["expression"], context)
    return result


def build_tax_summary(mapping: dict, context: dict) -> dict:
    """Build tax_summary dict from mapping expressions."""
    summary = {}
    for key, expr in mapping.items():
        summary[key] = evaluate_expression(expr, context)
    return summary


def parse_certificate(text: str, year: int, parser_defs: list) -> tuple[dict | None, str | None]:
    """Try each parser definition against the text. Return (cert, parser_id) or (None, None)."""
    from hashlib import sha256

    for pdef in parser_defs:
        if not match_institution(text, pdef):
            continue

        inst = pdef["institution"]
        cert_id = sha256(f"{year}|{inst['id']}|{inst['cert_type']}".encode()).hexdigest()[:16]

        sections = extract_sections(text, pdef, year)
        computed = compute_fields(sections, pdef.get("computed_fields", []))

        context = {"sections": sections, "computed": computed}
        tax_summary = build_tax_summary(pdef.get("tax_summary_mapping", {}), context)

        cert = {
            "id": cert_id,
            "year": year,
            "entity": inst["name"],
            "type": inst["cert_type"],
            "parser": inst["id"],
            "sections": sections,
            "computed": computed,
            "tax_summary": tax_summary,
        }

        return cert, inst["id"]

    return None, None


# ─── Improvement Signals ───────────────────────────────────────────

def log_improvement_signal(event: str, details: dict):
    """Append an improvement signal for agent consumption."""
    log_file = CONTROL_DIR / "improvement-log.jsonl"
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    entry = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **details,
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ─── CLI Commands ──────────────────────────────────────────────────

def cmd_validate():
    """Validate all parser definitions against the schema."""
    defs = load_parsers()
    if not defs:
        print("No parser definitions found.")
        return False

    valid = 0
    errors = 0
    for d in defs:
        name = d.get("_source_file", "?")
        inst = d.get("institution", {})
        issues = []

        if "institution" not in d:
            issues.append("missing 'institution'")
        elif not inst.get("id"):
            issues.append("missing 'institution.id'")
        if "identification" not in d:
            issues.append("missing 'identification'")
        elif not d["identification"].get("require_any"):
            issues.append("empty 'identification.require_any'")
        if "sections" not in d:
            issues.append("missing 'sections'")
        if "tax_summary_mapping" not in d:
            issues.append("missing 'tax_summary_mapping'")
        if "priority" not in d:
            issues.append("missing 'priority'")

        for section in d.get("sections", []):
            if not section.get("id"):
                issues.append(f"section missing 'id'")
            for field in section.get("fields", []):
                if not field.get("key"):
                    issues.append(f"field missing 'key' in section '{section.get('id')}'")
                if not field.get("method"):
                    issues.append(f"field '{field.get('key')}' missing 'method'")

        if issues:
            print(f"  FAIL  {name}: {'; '.join(issues)}")
            errors += 1
        else:
            print(f"  OK    {name} (priority={d.get('priority')}, {len(d.get('sections',[]))} sections)")
            valid += 1

    print(f"\n{valid}/{valid+errors} valid")
    return errors == 0


def cmd_coverage():
    """Report parser coverage."""
    defs = load_parsers()
    print(f"=== Parser Coverage ({len(defs)} definitions) ===\n")

    all_summary_keys = set()
    for d in defs:
        inst = d.get("institution", {})
        mapping = d.get("tax_summary_mapping", {})
        keys = list(mapping.keys())
        all_summary_keys.update(keys)

        sections = d.get("sections", [])
        total_fields = sum(len(s.get("fields", [])) for s in sections)

        print(f"  {inst.get('id', '?'):.<30s} priority={d.get('priority'):>3d}  "
              f"sections={len(sections)}  fields={total_fields}  "
              f"summary_keys={len(keys)}")

    print(f"\n  Unique tax_summary keys across all parsers:")
    for k in sorted(all_summary_keys):
        print(f"    - {k}")


def main():
    parser = argparse.ArgumentParser(description="Certificate parser engine")
    parser.add_argument("--validate", action="store_true", help="Validate all parser definitions")
    parser.add_argument("--coverage", action="store_true", help="Show parser coverage report")
    args = parser.parse_args()

    if args.validate:
        ok = cmd_validate()
        sys.exit(0 if ok else 1)
    elif args.coverage:
        cmd_coverage()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
