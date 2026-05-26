#!/bin/bash
# Self-Monitor — autonomous health and improvement loop
# Run via cron or systemd timer: every 6 hours on deployed nodes
#
# This script IS the agent's self-awareness at the infrastructure level.
# It checks its own health, evaluates its performance, and can trigger
# corrective actions without human intervention.

set -euo pipefail
cd "$(dirname "$0")/.."

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_DIR="data/self-monitor"
mkdir -p "$LOG_DIR"
REPORT="$LOG_DIR/report-$(date +%Y%m%d-%H%M%S).json"

echo "{ \"timestamp\": \"$TIMESTAMP\"," > "$REPORT"

# ─── 1. SYSTEM HEALTH ────────────────────────────────
echo "  \"system\": {" >> "$REPORT"

# CPU temperature (RPi)
if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    CPU_TEMP=$(awk '{printf "%.1f", $1/1000}' /sys/class/thermal/thermal_zone0/temp)
else
    CPU_TEMP="null"
fi
echo "    \"cpu_temp_c\": $CPU_TEMP," >> "$REPORT"

# Memory
MEM_TOTAL=$(free -m | awk '/Mem:/{print $2}')
MEM_USED=$(free -m | awk '/Mem:/{print $3}')
echo "    \"mem_total_mb\": $MEM_TOTAL," >> "$REPORT"
echo "    \"mem_used_mb\": $MEM_USED," >> "$REPORT"

# Disk
DISK_USED=$(df -h / | awk 'NR==2{print $5}' | tr -d '%')
echo "    \"disk_used_pct\": $DISK_USED," >> "$REPORT"

# Uptime
UPTIME_S=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo "0")
echo "    \"uptime_seconds\": $UPTIME_S" >> "$REPORT"
echo "  }," >> "$REPORT"

# ─── 2. AGENT HEALTH ─────────────────────────────────
echo "  \"agent\": {" >> "$REPORT"

# Is the agent process running?
if systemctl is-active --quiet microgrid-agent 2>/dev/null; then
    AGENT_STATUS="running"
elif pgrep -f "microgrid-agent" > /dev/null 2>&1; then
    AGENT_STATUS="running_manual"
else
    AGENT_STATUS="stopped"
fi
echo "    \"status\": \"$AGENT_STATUS\"," >> "$REPORT"

# Event journal size
if [ -f data/events.redb ]; then
    JOURNAL_SIZE=$(du -h data/events.redb | awk '{print $1}')
else
    JOURNAL_SIZE="none"
fi
echo "    \"journal_size\": \"$JOURNAL_SIZE\"," >> "$REPORT"

# Sync queue depth
QUEUE_DEPTH=$(find data/sync-queue -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
echo "    \"sync_queue_depth\": $QUEUE_DEPTH," >> "$REPORT"

# Model age (days since last update)
if [ -f data/models/solar-forecast.tflite ]; then
    MODEL_AGE=$(( ($(date +%s) - $(stat -c %Y data/models/solar-forecast.tflite 2>/dev/null || stat -f %m data/models/solar-forecast.tflite 2>/dev/null || echo "0")) / 86400 ))
else
    MODEL_AGE="null"
fi
echo "    \"model_age_days\": $MODEL_AGE" >> "$REPORT"
echo "  }," >> "$REPORT"

# ─── 3. EGRI EVALUATION ──────────────────────────────
echo "  \"egri\": {" >> "$REPORT"

# Count EGRI entries
if [ -f .control/egri-journal.jsonl ]; then
    EGRI_COUNT=$(wc -l < .control/egri-journal.jsonl | tr -d ' ')
    LAST_EVAL=$(tail -1 .control/egri-journal.jsonl)
else
    EGRI_COUNT=0
    LAST_EVAL="{}"
fi
echo "    \"evaluation_count\": $EGRI_COUNT," >> "$REPORT"
echo "    \"last_evaluation\": $LAST_EVAL" >> "$REPORT"
echo "  }," >> "$REPORT"

# ─── 4. CORRECTIVE ACTIONS ───────────────────────────
echo "  \"actions\": [" >> "$REPORT"
ACTIONS=()

# Action: restart agent if stopped
if [ "$AGENT_STATUS" = "stopped" ]; then
    ACTIONS+=("\"restart_agent: systemctl restart microgrid-agent\"")
    sudo systemctl restart microgrid-agent 2>/dev/null || true
fi

# Action: drain old sync queue (>30 days)
if [ "$QUEUE_DEPTH" -gt 10000 ]; then
    ACTIONS+=("\"drain_queue: removing entries older than 30 days\"")
    find data/sync-queue -name "*.json" -mtime +30 -delete 2>/dev/null || true
fi

# Action: compact journal if >1GB
if [ -f data/events.redb ]; then
    JOURNAL_BYTES=$(stat -c %s data/events.redb 2>/dev/null || stat -f %z data/events.redb 2>/dev/null || echo "0")
    if [ "$JOURNAL_BYTES" -gt 1073741824 ]; then
        ACTIONS+=("\"compact_journal: journal exceeds 1GB\"")
    fi
fi

# Action: warn if disk >90%
if [ "$DISK_USED" -gt 90 ]; then
    ACTIONS+=("\"disk_warning: usage at ${DISK_USED}%\"")
fi

# Write actions
if [ ${#ACTIONS[@]} -eq 0 ]; then
    echo "    \"none\"" >> "$REPORT"
else
    echo "    $(IFS=,; echo "${ACTIONS[*]}")" >> "$REPORT"
fi

echo "  ]" >> "$REPORT"
echo "}" >> "$REPORT"

echo "Self-monitor report: $REPORT"
cat "$REPORT"
