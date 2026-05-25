#!/usr/bin/env bash
# Content Engine — Generation Tracking Hook
# Logs generation sessions to ~/.config/content-engine/generation-log.jsonl
# Install as a Stop hook in .claude/settings.json
#
# Usage:
#   ./scripts/content-engine-bridge.sh          # Run from hook
#   ./scripts/content-engine-bridge.sh --status  # Check log status

set -euo pipefail

CONFIG_DIR="${HOME}/.config/content-engine"
LOG_FILE="${CONFIG_DIR}/generation-log.jsonl"
STAMP_FILE="${HOME}/.cache/content-engine-bridge-stamp"
COOLDOWN_SECONDS=120

# Ensure config dir exists
mkdir -p "${CONFIG_DIR}"
mkdir -p "$(dirname "${STAMP_FILE}")"

# Status check
if [[ "${1:-}" == "--status" ]]; then
    if [[ -f "${LOG_FILE}" ]]; then
        entries=$(wc -l < "${LOG_FILE}" | tr -d ' ')
        last=$(tail -1 "${LOG_FILE}" 2>/dev/null | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('timestamp','unknown'))" 2>/dev/null || echo "unknown")
        echo "Content Engine Bridge"
        echo "  Log: ${LOG_FILE}"
        echo "  Entries: ${entries}"
        echo "  Last run: ${last}"
    else
        echo "Content Engine Bridge: No log file yet."
    fi
    exit 0
fi

# Cooldown check
if [[ -f "${STAMP_FILE}" ]]; then
    last_run=$(cat "${STAMP_FILE}")
    now=$(date +%s)
    elapsed=$(( now - last_run ))
    if (( elapsed < COOLDOWN_SECONDS )); then
        exit 0
    fi
fi

# Record timestamp
date +%s > "${STAMP_FILE}"

# Find the content-engine repo
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Check if there are any compiled files or output
compiled_count=$(find "${REPO_DIR}/knowledge/compiled" -name "*.md" -not -name ".gitkeep" 2>/dev/null | wc -l | tr -d ' ')
output_dirs=$(find "${REPO_DIR}/output" -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')

# Log entry
entry=$(python3 -c "
import json, datetime, os
print(json.dumps({
    'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'repo': '${REPO_DIR}',
    'compiled_files': ${compiled_count},
    'output_campaigns': max(0, ${output_dirs} - 1),
    'branch': '$(cd "${REPO_DIR}" && git branch --show-current 2>/dev/null || echo "unknown")',
    'session': os.environ.get('CLAUDE_SESSION_ID', 'unknown')
}))
" 2>/dev/null)

if [[ -n "${entry}" ]]; then
    echo "${entry}" >> "${LOG_FILE}"
fi
