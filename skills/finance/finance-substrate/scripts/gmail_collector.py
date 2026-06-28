#!/usr/bin/env python3
"""
Collect tax-relevant documents and payment data from Gmail using GWS CLI.

Searches for:
- Bank statements (extractos) from Davivienda, Nu, Nequi
- Tax certificates from all institutions
- DIAN notifications
- Salary payment confirmations from Thera
- Planilla/parafiscales confirmations from Compensar

Usage:
    python3 gmail_collector.py --year 2025
    python3 gmail_collector.py --year 2025 --download-attachments
    python3 gmail_collector.py --year 2025 --source thera  # Just salary payments
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
import base64
import json
import os
import re
import subprocess
from pathlib import Path

DATA_DIR = Path.home() / ".finance-substrate"
DECL_DIR = Path.home() / "Dropbox" / "Declaracion"


def gws_cmd(service: str, resource: str, method: str, params: dict) -> dict:
    """Execute a GWS CLI command and return parsed JSON."""
    # Split resource into separate args (e.g., "users messages" -> "users", "messages")
    cmd = ["gws", service] + resource.split() + [method, "--params", json.dumps(params)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return {"error": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": result.stdout}


def gws_gmail_get(msg_id: str, fmt: str = "metadata") -> dict:
    return gws_cmd("gmail", "users messages", "get", {
        "userId": "me", "id": msg_id, "format": fmt,
    })


def search_messages(query: str, max_results: int = 50) -> list:
    """Search Gmail and return message IDs."""
    data = gws_cmd("gmail", "users messages", "list", {
        "userId": "me", "q": query, "maxResults": max_results,
    })
    return [m["id"] for m in data.get("messages", [])]


def get_message_details(msg_id: str) -> dict:
    """Get message subject, from, date, and attachment info."""
    msg = gws_gmail_get(msg_id, "metadata")
    if "error" in msg:
        return msg

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    parts = msg.get("payload", {}).get("parts", [])
    attachments = []
    for p in parts:
        if p.get("filename"):
            attachments.append({
                "filename": p["filename"],
                "mimeType": p.get("mimeType", ""),
                "size": p.get("body", {}).get("size", 0),
                "attachmentId": p.get("body", {}).get("attachmentId", ""),
            })
        for sp in p.get("parts", []):
            if sp.get("filename"):
                attachments.append({
                    "filename": sp["filename"],
                    "mimeType": sp.get("mimeType", ""),
                    "size": sp.get("body", {}).get("size", 0),
                    "attachmentId": sp.get("body", {}).get("attachmentId", ""),
                })

    return {
        "id": msg_id,
        "date": headers.get("Date", ""),
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "attachments": attachments,
    }


def get_message_body(msg_id: str) -> str:
    """Get plain text body of a message."""
    msg = gws_gmail_get(msg_id, "full")
    if "error" in msg:
        return ""

    parts = msg.get("payload", {}).get("parts", [msg.get("payload", {})])
    for p in (parts if isinstance(parts, list) else [parts]):
        body = p.get("body", {}).get("data", "")
        if body and p.get("mimeType", "").startswith("text/plain"):
            return base64.urlsafe_b64decode(body).decode("utf-8", errors="replace")
        for sp in p.get("parts", []):
            body = sp.get("body", {}).get("data", "")
            if body and sp.get("mimeType", "").startswith("text/plain"):
                return base64.urlsafe_b64decode(body).decode("utf-8", errors="replace")
    return ""


def download_attachment(msg_id: str, attachment_id: str, filename: str, output_dir: Path):
    """Download an email attachment."""
    data = gws_cmd("gmail", "users messages attachments", "get", {
        "userId": "me", "messageId": msg_id, "id": attachment_id,
    })
    if "error" in data:
        print(f"  Error downloading {filename}: {data['error']}")
        return

    file_data = base64.urlsafe_b64decode(data.get("data", ""))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_bytes(file_data)
    print(f"  Downloaded: {output_path} ({len(file_data):,} bytes)")


# ─── Source-specific collectors ────────────────────────────────────

SOURCES = {
    "thera": {
        "query": "from:thera received payment",
        "label": "Thera salary payments",
        "parser": "thera",
    },
    "davivienda": {
        "query": "from:davivienda (extracto OR certificado OR transaccion)",
        "label": "Davivienda bank statements & certificates",
        "parser": "bank",
    },
    "nu": {
        "query": "from:nu.com.co",
        "label": "Nu Colombia notifications",
        "parser": "bank",
    },
    "nequi": {
        "query": "from:nequi",
        "label": "Nequi notifications",
        "parser": "bank",
    },
    "rappi": {
        "query": "from:rappipay OR from:rappicard",
        "label": "RappiPay/RappiCard notifications",
        "parser": "bank",
    },
    "skandia": {
        "query": "from:skandia",
        "label": "Skandia pension notifications",
        "parser": "bank",
    },
    "compensar": {
        "query": "from:compensar (planilla OR pago OR parafiscal)",
        "label": "Compensar PILA confirmations",
        "parser": "pila",
    },
    "dian": {
        "query": "from:dian.gov.co",
        "label": "DIAN notifications",
        "parser": "dian",
    },
    "falabella": {
        "query": "from:falabella (certificado OR extracto)",
        "label": "Banco Falabella certificates",
        "parser": "bank",
    },
}


def parse_thera_payment(body: str) -> dict | None:
    """Extract payment amount from Thera email."""
    m = re.search(r"USD\s+([\d,]+(?:\.\d{2})?)", body)
    if m:
        amount = float(m.group(1).replace(",", ""))
        employer = re.search(r"contract with (.+?) on Thera", body)
        return {
            "amount_usd": amount,
            "employer": employer.group(1) if employer else "Unknown",
        }
    return None


def collect_source(source_key: str, year: int, download: bool = False) -> list:
    """Collect messages from a specific source."""
    source = SOURCES[source_key]
    query = f'{source["query"]} after:{year}/01/01 before:{year + 1}/01/01'

    print(f"\n  [{source_key}] {source['label']}")
    msg_ids = search_messages(query)
    print(f"    Found {len(msg_ids)} messages")

    results = []
    for mid in msg_ids[:20]:  # Cap at 20 per source
        details = get_message_details(mid)
        if "error" in details:
            continue

        entry = {
            "source": source_key,
            "date": details["date"],
            "subject": details["subject"],
            "attachments": len(details["attachments"]),
        }

        # Parse source-specific data
        if source["parser"] == "thera":
            body = get_message_body(mid)
            payment = parse_thera_payment(body)
            if payment:
                entry["payment"] = payment

        results.append(entry)

        # Download attachments if requested
        if download and details["attachments"]:
            output_dir = DECL_DIR / str(year) / "Gmail" / source_key
            for att in details["attachments"]:
                if att["attachmentId"]:
                    download_attachment(mid, att["attachmentId"], att["filename"], output_dir)

    return results


def main():
    parser = argparse.ArgumentParser(description="Collect tax documents from Gmail")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--source", choices=list(SOURCES.keys()) + ["all"], default="all")
    parser.add_argument("--download-attachments", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    print(f"=== Gmail Tax Document Collector — {args.year} ===")

    sources = SOURCES.keys() if args.source == "all" else [args.source]
    all_results = {}

    for source_key in sources:
        results = collect_source(source_key, args.year, args.download_attachments)
        all_results[source_key] = results

        # Show Thera payment summary
        if source_key == "thera":
            payments = [r["payment"] for r in results if "payment" in r]
            if payments:
                total_usd = sum(p["amount_usd"] for p in payments)
                print(f"    Salary total: ${total_usd:,.0f} USD ({len(payments)} payments)")

    if args.json:
        print(json.dumps(all_results, indent=2, default=str))
    else:
        print(f"\n{'='*50}")
        print(f"  Summary — {args.year}")
        print(f"{'='*50}")
        for source_key, results in all_results.items():
            att_count = sum(r["attachments"] for r in results)
            print(f"  {source_key:<15s}: {len(results):>3d} messages, {att_count:>3d} attachments")


if __name__ == "__main__":
    main()
