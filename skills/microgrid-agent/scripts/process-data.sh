#!/usr/bin/env bash
# =============================================================================
# Microgrid Agent — Generic Data Ingestion Script
# =============================================================================
# Accepts CSV, JSON, or XLSX files and ingests them into the SQLite
# knowledge graph. After ingestion, signals the agent to reload.
#
# Usage:
#   ./scripts/process-data.sh <input_file> [--table <table_name>]
#
# Examples:
#   ./scripts/process-data.sh readings_2024.csv
#   ./scripts/process-data.sh weather_forecast.json --table readings
#   ./scripts/process-data.sh community_survey.xlsx --table entities
# =============================================================================
set -euo pipefail

DATA_DIR="${MICROGRID_DATA_DIR:-/var/lib/microgrid-agent}"
DB_FILE="${DATA_DIR}/db/knowledge.db"
VENV_DIR="${MICROGRID_INSTALL_DIR:-/opt/microgrid-agent}/venv"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
INPUT_FILE=""
TABLE_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --table)
            TABLE_NAME="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 <input_file> [--table <table_name>]"
            echo ""
            echo "Supported formats: .csv, .json, .xlsx"
            echo "Default table: auto-detected from file content"
            exit 0
            ;;
        *)
            INPUT_FILE="$1"
            shift
            ;;
    esac
done

if [ -z "$INPUT_FILE" ]; then
    echo "ERROR: No input file specified."
    echo "Usage: $0 <input_file> [--table <table_name>]"
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo "ERROR: File not found: $INPUT_FILE"
    exit 1
fi

if [ ! -f "$DB_FILE" ]; then
    echo "ERROR: Knowledge graph database not found at $DB_FILE"
    echo "Run the install script first to initialize the database."
    exit 1
fi

# -----------------------------------------------------------------------------
# Detect file format
# -----------------------------------------------------------------------------
EXTENSION="${INPUT_FILE##*.}"
EXTENSION=$(echo "$EXTENSION" | tr '[:upper:]' '[:lower:]')

echo "=== Data Ingestion ==="
echo "File:   $INPUT_FILE"
echo "Format: $EXTENSION"
echo "Target: $DB_FILE"
echo ""

# -----------------------------------------------------------------------------
# Activate virtual environment for Python processing
# -----------------------------------------------------------------------------
if [ -d "$VENV_DIR" ]; then
    source "${VENV_DIR}/bin/activate"
fi

# -----------------------------------------------------------------------------
# Process and ingest data
# -----------------------------------------------------------------------------
python3 - "$INPUT_FILE" "$EXTENSION" "$TABLE_NAME" "$DB_FILE" <<'PYTHON_SCRIPT'
import sys
import os
import json
import sqlite3
import csv
from datetime import datetime
from pathlib import Path

input_file = sys.argv[1]
file_format = sys.argv[2]
table_override = sys.argv[3] if sys.argv[3] else None
db_file = sys.argv[4]

def detect_table(columns):
    """Auto-detect target table from column names."""
    col_set = set(c.lower() for c in columns)

    if {'timestamp', 'device_id', 'metric', 'value'} <= col_set:
        return 'readings'
    if {'type', 'name', 'properties'} <= col_set:
        return 'entities'
    if {'source_id', 'relation', 'target_id'} <= col_set:
        return 'relations'
    if {'entity_id', 'pattern_type', 'hour'} <= col_set:
        return 'patterns'
    if {'action', 'reasoning'} <= col_set:
        return 'decisions'

    # Default to readings (most common ingestion target)
    return 'readings'

def validate_readings(rows):
    """Validate readings data has required fields."""
    required = {'timestamp', 'device_id', 'metric', 'value'}
    if rows:
        cols = set(rows[0].keys())
        missing = required - cols
        if missing:
            print(f"WARNING: Missing columns for readings table: {missing}")
            print(f"Available columns: {cols}")
            return False
    return True

def validate_entities(rows):
    """Validate entity data."""
    required = {'type', 'name'}
    if rows:
        cols = set(rows[0].keys())
        missing = required - cols
        if missing:
            print(f"WARNING: Missing columns for entities table: {missing}")
            return False
    return True

def read_csv_file(filepath):
    """Read CSV file into list of dicts."""
    rows = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        # Sniff delimiter
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(f, dialect=dialect)
        for row in reader:
            rows.append(dict(row))
    return rows

def read_json_file(filepath):
    """Read JSON file into list of dicts."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Handle both array of objects and single object
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        # Check if it has a 'data' or 'records' key
        for key in ('data', 'records', 'readings', 'entities', 'results'):
            if key in data and isinstance(data[key], list):
                return data[key]
        # Single object — wrap in list
        return [data]
    else:
        raise ValueError(f"Unexpected JSON structure: {type(data)}")

def read_xlsx_file(filepath):
    """Read XLSX file into list of dicts."""
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl is required for XLSX files.")
        print("Install with: pip install openpyxl")
        sys.exit(1)

    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb.active
    rows = []
    headers = None
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers = [str(c).strip().lower() if c else f"col_{j}" for j, c in enumerate(row)]
            continue
        row_dict = {}
        for j, val in enumerate(row):
            if j < len(headers):
                row_dict[headers[j]] = val
        rows.append(row_dict)
    wb.close()
    return rows

# Read the file
print(f"Reading {file_format.upper()} file...")
try:
    if file_format == 'csv':
        rows = read_csv_file(input_file)
    elif file_format == 'json':
        rows = read_json_file(input_file)
    elif file_format in ('xlsx', 'xls'):
        rows = read_xlsx_file(input_file)
    else:
        print(f"ERROR: Unsupported file format: {file_format}")
        print("Supported formats: csv, json, xlsx")
        sys.exit(1)
except Exception as e:
    print(f"ERROR reading file: {e}")
    sys.exit(1)

if not rows:
    print("WARNING: File contains no data rows.")
    sys.exit(0)

print(f"Read {len(rows)} rows with columns: {list(rows[0].keys())}")

# Determine target table
table = table_override or detect_table(list(rows[0].keys()))
print(f"Target table: {table}")

# Validate
validators = {
    'readings': validate_readings,
    'entities': validate_entities,
}
if table in validators and not validators[table](rows):
    print("WARNING: Validation issues detected. Proceeding with best effort.")

# Insert into database
conn = sqlite3.connect(db_file)
cursor = conn.cursor()
inserted = 0
skipped = 0

try:
    if table == 'readings':
        for row in rows:
            try:
                cursor.execute(
                    "INSERT INTO readings (timestamp, device_id, metric, value) VALUES (?, ?, ?, ?)",
                    (row.get('timestamp', datetime.utcnow().isoformat()),
                     row.get('device_id', 'unknown'),
                     row.get('metric', 'unknown'),
                     float(row.get('value', 0)))
                )
                inserted += 1
            except (ValueError, sqlite3.Error) as e:
                skipped += 1

    elif table == 'entities':
        for row in rows:
            try:
                props = {k: v for k, v in row.items() if k not in ('id', 'type', 'name')}
                cursor.execute(
                    "INSERT INTO entities (type, name, properties) VALUES (?, ?, ?)",
                    (row.get('type', 'unknown'),
                     row.get('name', 'unnamed'),
                     json.dumps(props))
                )
                inserted += 1
            except sqlite3.Error as e:
                skipped += 1

    elif table == 'relations':
        for row in rows:
            try:
                props = {k: v for k, v in row.items()
                         if k not in ('source_id', 'relation', 'target_id', 'weight')}
                cursor.execute(
                    "INSERT INTO relations (source_id, relation, target_id, weight, properties) VALUES (?, ?, ?, ?, ?)",
                    (int(row['source_id']),
                     row['relation'],
                     int(row['target_id']),
                     float(row.get('weight', 1.0)),
                     json.dumps(props))
                )
                inserted += 1
            except (ValueError, KeyError, sqlite3.Error) as e:
                skipped += 1

    elif table == 'decisions':
        for row in rows:
            try:
                cursor.execute(
                    "INSERT INTO decisions (timestamp, action, reasoning, overridden) VALUES (?, ?, ?, ?)",
                    (row.get('timestamp', datetime.utcnow().isoformat()),
                     row.get('action', 'unknown'),
                     json.dumps(row.get('reasoning', {})),
                     bool(row.get('overridden', False)))
                )
                inserted += 1
            except sqlite3.Error as e:
                skipped += 1

    else:
        print(f"ERROR: Unknown table '{table}'. Valid tables: readings, entities, relations, decisions, patterns")
        sys.exit(1)

    conn.commit()
    print(f"\nInserted: {inserted} rows")
    if skipped > 0:
        print(f"Skipped:  {skipped} rows (errors)")

except Exception as e:
    conn.rollback()
    print(f"ERROR during ingestion: {e}")
    sys.exit(1)
finally:
    conn.close()
PYTHON_SCRIPT

# -----------------------------------------------------------------------------
# Signal the agent to reload data
# -----------------------------------------------------------------------------
echo ""
echo ">>> Signaling agent to reload..."

# Find the agent process and send SIGUSR1
AGENT_PID=$(pgrep -f "microgrid.*main" 2>/dev/null | head -1)
if [ -n "$AGENT_PID" ]; then
    kill -USR1 "$AGENT_PID" 2>/dev/null && \
        echo "    Sent SIGUSR1 to agent (PID $AGENT_PID)" || \
        echo "    WARNING: Failed to signal agent (PID $AGENT_PID)"
else
    echo "    Agent process not found. Data will be loaded on next restart."
fi

echo ""
echo "=== Ingestion complete ==="
