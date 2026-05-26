#!/usr/bin/env bash
# =============================================================================
# Microgrid Agent — Model Update Script
# =============================================================================
# Downloads or copies new model weights and atomically swaps them in.
# The old model is kept as a rollback backup.
#
# Usage:
#   ./scripts/update-model.sh <source> [--checksum <sha256>]
#
# Source can be:
#   - A local file path:   ./scripts/update-model.sh /tmp/dispatch_v2.tflite
#   - An HTTP/HTTPS URL:   ./scripts/update-model.sh https://fleet.example.com/models/dispatch_v2.tflite
#
# Flags:
#   --checksum <sha256>   Verify file integrity after download (recommended)
#   --model-name <name>   Override the model filename (default: basename of source)
#   --no-signal           Don't signal the agent to reload after swap
# =============================================================================
set -euo pipefail

DATA_DIR="${MICROGRID_DATA_DIR:-/var/lib/microgrid-agent}"
MODEL_DIR="${DATA_DIR}/models"
BACKUP_DIR="${DATA_DIR}/backups"
TEMP_DIR="${DATA_DIR}/.model-update-tmp"

SOURCE=""
CHECKSUM=""
MODEL_NAME=""
SIGNAL_AGENT=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --checksum)
            CHECKSUM="$2"
            shift 2
            ;;
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        --no-signal)
            SIGNAL_AGENT=false
            shift
            ;;
        -h|--help)
            echo "Usage: $0 <source> [--checksum <sha256>] [--model-name <name>] [--no-signal]"
            echo ""
            echo "Source: local file path or HTTP(S) URL"
            echo ""
            echo "The update is atomic: write new file, rename old, rename new."
            echo "Old model is kept in backups/ for rollback."
            exit 0
            ;;
        *)
            SOURCE="$1"
            shift
            ;;
    esac
done

if [ -z "$SOURCE" ]; then
    echo "ERROR: No source specified."
    echo "Usage: $0 <source> [--checksum <sha256>]"
    exit 1
fi

# Determine model filename
if [ -z "$MODEL_NAME" ]; then
    MODEL_NAME=$(basename "$SOURCE")
fi

echo "=== Model Update ==="
echo "Source:     $SOURCE"
echo "Model:     $MODEL_NAME"
echo "Target:    ${MODEL_DIR}/${MODEL_NAME}"
echo "Checksum:  ${CHECKSUM:-none}"
echo ""

# Create directories
mkdir -p "$MODEL_DIR" "$BACKUP_DIR" "$TEMP_DIR"

# -----------------------------------------------------------------------------
# 1. Download or copy the new model to a temp location
# -----------------------------------------------------------------------------
TEMP_FILE="${TEMP_DIR}/${MODEL_NAME}.new"

echo ">>> Downloading/copying model..."
if [[ "$SOURCE" == http://* ]] || [[ "$SOURCE" == https://* ]]; then
    # Download from URL
    if command -v curl >/dev/null 2>&1; then
        curl -fSL --connect-timeout 30 --max-time 600 \
            -o "$TEMP_FILE" "$SOURCE"
    elif command -v wget >/dev/null 2>&1; then
        wget -q --timeout=30 -O "$TEMP_FILE" "$SOURCE"
    else
        echo "ERROR: Neither curl nor wget found. Cannot download."
        exit 1
    fi
else
    # Copy local file
    if [ ! -f "$SOURCE" ]; then
        echo "ERROR: Source file not found: $SOURCE"
        exit 1
    fi
    cp "$SOURCE" "$TEMP_FILE"
fi

# Check file was actually downloaded
if [ ! -f "$TEMP_FILE" ] || [ ! -s "$TEMP_FILE" ]; then
    echo "ERROR: Downloaded file is empty or missing."
    rm -f "$TEMP_FILE"
    exit 1
fi

FILE_SIZE=$(du -h "$TEMP_FILE" | awk '{print $1}')
echo "    Downloaded: ${FILE_SIZE}"

# -----------------------------------------------------------------------------
# 2. Verify checksum
# -----------------------------------------------------------------------------
if [ -n "$CHECKSUM" ]; then
    echo ">>> Verifying checksum..."
    ACTUAL_CHECKSUM=""

    if command -v sha256sum >/dev/null 2>&1; then
        ACTUAL_CHECKSUM=$(sha256sum "$TEMP_FILE" | awk '{print $1}')
    elif command -v shasum >/dev/null 2>&1; then
        ACTUAL_CHECKSUM=$(shasum -a 256 "$TEMP_FILE" | awk '{print $1}')
    else
        echo "WARNING: No SHA-256 tool found. Skipping checksum verification."
    fi

    if [ -n "$ACTUAL_CHECKSUM" ]; then
        if [ "$ACTUAL_CHECKSUM" != "$CHECKSUM" ]; then
            echo "ERROR: Checksum mismatch!"
            echo "  Expected: $CHECKSUM"
            echo "  Got:      $ACTUAL_CHECKSUM"
            rm -f "$TEMP_FILE"
            exit 1
        fi
        echo "    Checksum verified: ${ACTUAL_CHECKSUM:0:16}..."
    fi
fi

# -----------------------------------------------------------------------------
# 3. Atomic swap: write new -> rename old -> rename new
# -----------------------------------------------------------------------------
TARGET_FILE="${MODEL_DIR}/${MODEL_NAME}"
OLD_FILE="${TARGET_FILE}.old"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo ">>> Performing atomic swap..."

# Step 3a: If there's an existing model, back it up
if [ -f "$TARGET_FILE" ]; then
    BACKUP_FILE="${BACKUP_DIR}/${MODEL_NAME}.${TIMESTAMP}"
    echo "    Backing up current model -> ${BACKUP_FILE}"
    cp "$TARGET_FILE" "$BACKUP_FILE"

    # Rename current model to .old
    mv "$TARGET_FILE" "$OLD_FILE"
fi

# Step 3b: Rename new model into place (atomic on same filesystem)
mv "$TEMP_FILE" "$TARGET_FILE"

# Step 3c: Remove the .old file (backup is already in backups/)
if [ -f "$OLD_FILE" ]; then
    rm -f "$OLD_FILE"
fi

echo "    Model installed at ${TARGET_FILE}"

# Clean up temp directory
rmdir "$TEMP_DIR" 2>/dev/null || true

# Prune old backups (keep last 3)
echo ">>> Pruning old backups..."
BACKUP_COUNT=$(ls -1 "${BACKUP_DIR}/${MODEL_NAME}."* 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 3 ]; then
    ls -1t "${BACKUP_DIR}/${MODEL_NAME}."* | tail -n +4 | xargs rm -f
    echo "    Kept 3 most recent backups, removed $((BACKUP_COUNT - 3)) old ones"
else
    echo "    ${BACKUP_COUNT} backup(s) stored"
fi

# -----------------------------------------------------------------------------
# 4. Signal agent to reload model
# -----------------------------------------------------------------------------
if [ "$SIGNAL_AGENT" = true ]; then
    echo ">>> Signaling agent to reload model..."
    AGENT_PID=$(pgrep -f "microgrid.*main" 2>/dev/null | head -1)
    if [ -n "$AGENT_PID" ]; then
        kill -USR1 "$AGENT_PID" 2>/dev/null && \
            echo "    Sent SIGUSR1 to agent (PID $AGENT_PID)" || \
            echo "    WARNING: Failed to signal agent"
    else
        echo "    Agent process not found. Model will be loaded on next restart."
    fi
fi

echo ""
echo "=== Model update complete ==="
echo ""
echo "Rollback: cp '${BACKUP_DIR}/${MODEL_NAME}.${TIMESTAMP}' '${TARGET_FILE}'"
