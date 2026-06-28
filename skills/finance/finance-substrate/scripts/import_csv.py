#!/usr/bin/env python3
"""
Bank transaction importer — parses CSV/OFX from Colombian banks into a unified JSONL ledger.

Usage:
    python3 import_csv.py --bank davivienda --file ~/Downloads/extracto.csv
    python3 import_csv.py --bank nubank --file ~/Downloads/nubank-2026-03.csv
    python3 import_csv.py --bank nequi --file ~/Downloads/nequi-movimientos.csv
    python3 import_csv.py --bank arq --file ~/Downloads/arq-export.csv
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
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.home() / ".finance-substrate"
LEDGER_FILE = DATA_DIR / "ledger" / "transactions.jsonl"
RULES_FILE = DATA_DIR / "ledger" / "rules.json"
IMPORTERS_DIR = Path(__file__).parent.parent / "importers"


def ensure_data_dirs():
    """Create data directory structure on first run."""
    for subdir in [
        "ledger",
        "tax",
        "tax/projections",
        "fx",
        "invoices/issued",
        "invoices/received",
    ]:
        (DATA_DIR / subdir).mkdir(parents=True, exist_ok=True)

    if not LEDGER_FILE.exists():
        LEDGER_FILE.touch()

    if not RULES_FILE.exists():
        RULES_FILE.write_text("[]")

    accounts_file = DATA_DIR / "ledger" / "accounts.json"
    if not accounts_file.exists():
        accounts_file.write_text(
            json.dumps(
                {
                    "davivienda": {
                        "type": "checking",
                        "currency": "COP",
                        "label": "Davivienda Cuenta de Ahorros",
                    },
                    "nubank": {
                        "type": "credit-card",
                        "currency": "COP",
                        "label": "Nu Colombia Tarjeta de Credito",
                    },
                    "nequi": {
                        "type": "wallet",
                        "currency": "COP",
                        "label": "Nequi",
                    },
                    "arq": {
                        "type": "checking",
                        "currency": "USD",
                        "label": "ARQ (ex-DolarApp) USD Account",
                    },
                },
                indent=2,
            )
        )


def load_importer_profile(bank: str) -> dict:
    """Load bank-specific column mappings from importers/*.json."""
    profile_path = IMPORTERS_DIR / f"{bank}.json"
    if not profile_path.exists():
        print(f"Error: No importer profile found at {profile_path}", file=sys.stderr)
        sys.exit(1)
    with open(profile_path) as f:
        return json.load(f)


def tx_hash(date: str, amount: float, description: str, bank: str) -> str:
    """Generate deterministic transaction ID."""
    raw = f"{date}|{amount}|{description}|{bank}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_existing_ids() -> set:
    """Load existing transaction IDs for deduplication."""
    ids = set()
    if LEDGER_FILE.exists():
        with open(LEDGER_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    tx = json.loads(line)
                    ids.add(tx["id"])
    return ids


def load_rules() -> list:
    """Load categorization rules."""
    if RULES_FILE.exists():
        with open(RULES_FILE) as f:
            return json.load(f)
    return []


def apply_rules(description: str, rules: list) -> str | None:
    """Match description against rules, return category or None."""
    desc_upper = description.upper()
    for rule in rules:
        pattern = rule.get("pattern", "").upper()
        if pattern and pattern in desc_upper:
            return rule["category"]
        regex = rule.get("regex")
        if regex and re.search(regex, description, re.IGNORECASE):
            return rule["category"]
    return None


def parse_date(date_str: str, fmt: str) -> str:
    """Parse date string to ISO format YYYY-MM-DD."""
    # Handle multiple possible formats
    for f in [fmt, "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"]:
        try:
            return datetime.strptime(date_str.strip(), f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Last resort: return as-is
    return date_str.strip()


def parse_amount(value: str, profile: dict) -> float:
    """Parse amount string handling locale-specific formatting."""
    decimal_sep = profile.get("decimal_separator", ".")
    thousands_sep = profile.get("thousands_separator", ",")

    cleaned = value.strip().replace(thousands_sep, "")
    if decimal_sep != ".":
        cleaned = cleaned.replace(decimal_sep, ".")

    # Remove currency symbols
    cleaned = re.sub(r"[^\d.\-+]", "", cleaned)

    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def import_csv(file_path: str, bank: str) -> dict:
    """Import a CSV file and return stats."""
    profile = load_importer_profile(bank)
    existing_ids = load_existing_ids()
    rules = load_rules()

    col_map = profile["columns"]
    date_format = profile.get("date_format", "%Y-%m-%d")
    encoding = profile.get("encoding", "utf-8")
    delimiter = profile.get("delimiter", ",")
    skip_rows = profile.get("skip_rows", 0)
    currency = profile.get("currency", "COP")

    new_count = 0
    dup_count = 0
    uncat_count = 0
    new_transactions = []

    with open(file_path, encoding=encoding, newline="") as f:
        # Skip header rows if needed
        for _ in range(skip_rows):
            next(f)

        reader = csv.DictReader(f, delimiter=delimiter)

        for row in reader:
            # Extract fields using column mapping
            date_raw = row.get(col_map["date"], "")
            description = row.get(col_map["description"], "").strip()

            # Handle split debit/credit columns
            if "amount" in col_map:
                amount = parse_amount(row.get(col_map["amount"], "0"), profile)
            else:
                debit = parse_amount(row.get(col_map.get("debit", ""), "0") or "0", profile)
                credit = parse_amount(row.get(col_map.get("credit", ""), "0") or "0", profile)
                amount = credit - debit if credit else -debit

            if not date_raw or amount == 0:
                continue

            date = parse_date(date_raw, date_format)
            tid = tx_hash(date, amount, description, bank)

            if tid in existing_ids:
                dup_count += 1
                continue

            category = apply_rules(description, rules)
            if category is None:
                uncat_count += 1

            tx = {
                "id": tid,
                "date": date,
                "amount": amount,
                "currency": currency,
                "description": description,
                "category": category,
                "bank": bank,
                "account": profile.get("default_account", bank),
                "raw": dict(row),
            }

            new_transactions.append(tx)
            existing_ids.add(tid)
            new_count += 1

    # Append to ledger
    if new_transactions:
        with open(LEDGER_FILE, "a") as f:
            for tx in new_transactions:
                f.write(json.dumps(tx, ensure_ascii=False) + "\n")

    return {
        "new": new_count,
        "duplicates": dup_count,
        "uncategorized": uncat_count,
        "total_in_file": new_count + dup_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Import bank CSV/OFX to finance-substrate ledger")
    parser.add_argument("--bank", required=True, choices=["davivienda", "nubank", "nequi", "arq"])
    parser.add_argument("--file", required=True, help="Path to CSV or OFX file")
    args = parser.parse_args()

    ensure_data_dirs()

    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    stats = import_csv(args.file, args.bank)

    print(json.dumps(stats, indent=2))
    print(f"\n{stats['new']} new transactions imported.")
    if stats["duplicates"]:
        print(f"{stats['duplicates']} duplicates skipped.")
    if stats["uncategorized"]:
        print(f"{stats['uncategorized']} transactions need categorization.")


if __name__ == "__main__":
    main()
