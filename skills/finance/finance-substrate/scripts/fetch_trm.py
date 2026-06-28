#!/usr/bin/env python3
"""
Fetch TRM (Tasa Representativa del Mercado) from datos.gov.co open data API.

Usage:
    python3 fetch_trm.py                          # Today's rate
    python3 fetch_trm.py --date 2026-03-15        # Specific date
    python3 fetch_trm.py --from 2026-03-01 --to 2026-03-19  # Date range
    python3 fetch_trm.py --days 30                # Last N days
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
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path.home() / ".finance-substrate"
TRM_FILE = DATA_DIR / "fx" / "trm-history.jsonl"

API_BASE = "https://www.datos.gov.co/resource/32sa-8pi3.json"


def ensure_dirs():
    (DATA_DIR / "fx").mkdir(parents=True, exist_ok=True)
    if not TRM_FILE.exists():
        TRM_FILE.touch()


def fetch_trm(date_from: str | None = None, date_to: str | None = None, limit: int = 10) -> list:
    """Fetch TRM rates from datos.gov.co."""
    params = {
        "$order": "vigenciadesde DESC",
        "$limit": str(limit),
    }

    if date_from and date_to:
        params["$where"] = (
            f"vigenciadesde >= '{date_from}T00:00:00.000' "
            f"AND vigenciadesde <= '{date_to}T23:59:59.999'"
        )
        params["$limit"] = "1000"
    elif date_from:
        params["$where"] = f"vigenciadesde >= '{date_from}T00:00:00.000'"

    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching TRM: {e}", file=sys.stderr)
        sys.exit(1)

    results = []
    for entry in data:
        rate = {
            "date": entry.get("vigenciadesde", "")[:10],
            "vigencia_hasta": entry.get("vigenciahasta", "")[:10],
            "valor": float(entry.get("valor", 0)),
        }
        results.append(rate)

    return results


def load_existing_dates() -> set:
    """Load dates already in TRM history."""
    dates = set()
    if TRM_FILE.exists():
        with open(TRM_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    dates.add(entry.get("date"))
    return dates


def save_rates(rates: list):
    """Append new rates to TRM history, skip duplicates."""
    existing = load_existing_dates()
    new_count = 0

    with open(TRM_FILE, "a") as f:
        for rate in rates:
            if rate["date"] not in existing:
                f.write(json.dumps(rate, ensure_ascii=False) + "\n")
                existing.add(rate["date"])
                new_count += 1

    return new_count


def main():
    parser = argparse.ArgumentParser(description="Fetch TRM (USD/COP) from datos.gov.co")
    parser.add_argument("--date", help="Specific date (YYYY-MM-DD)")
    parser.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, help="Fetch last N days")
    parser.add_argument("--no-save", action="store_true", help="Print only, don't save to history")
    args = parser.parse_args()

    ensure_dirs()

    if args.date:
        rates = fetch_trm(date_from=args.date, date_to=args.date, limit=1)
    elif args.days:
        d_from = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
        d_to = datetime.now().strftime("%Y-%m-%d")
        rates = fetch_trm(date_from=d_from, date_to=d_to)
    elif args.date_from:
        d_to = args.date_to or datetime.now().strftime("%Y-%m-%d")
        rates = fetch_trm(date_from=args.date_from, date_to=d_to)
    else:
        # Default: latest rate
        rates = fetch_trm(limit=1)

    if not rates:
        print("No TRM data found for the specified date(s).")
        sys.exit(0)

    # Print results
    for r in sorted(rates, key=lambda x: x["date"]):
        print(f"{r['date']}  TRM: ${r['valor']:,.2f} COP/USD")

    # Save to history
    if not args.no_save:
        new = save_rates(rates)
        if new:
            print(f"\n{new} new rate(s) saved to {TRM_FILE}")


if __name__ == "__main__":
    main()
