#!/usr/bin/env bash
# =============================================================================
# Microgrid Agent — System Health Diagnostic
# =============================================================================
# Checks all subsystems and outputs a structured JSON report.
# Designed to be called by the watchdog, fleet server, or cron.
#
# Usage:
#   ./scripts/health-check.sh [--verbose]
#
# Exit codes:
#   0 — All checks passed
#   1 — One or more checks failed (see JSON output for details)
# =============================================================================
set -uo pipefail

INSTALL_DIR="${MICROGRID_INSTALL_DIR:-/opt/microgrid-agent}"
DATA_DIR="${MICROGRID_DATA_DIR:-/var/lib/microgrid-agent}"
CONFIG_DIR="${INSTALL_DIR}/config"
VERBOSE=false

for arg in "$@"; do
    case "$arg" in
        --verbose) VERBOSE=true ;;
    esac
done

# Accumulator for overall status
OVERALL_OK=true
CHECKS="[]"

# Helper: append a check result to the JSON array
add_check() {
    local name="$1"
    local status="$2"   # "ok", "warn", "fail"
    local detail="$3"

    if [ "$status" = "fail" ]; then
        OVERALL_OK=false
    fi

    CHECKS=$(echo "$CHECKS" | python3 -c "
import sys, json
checks = json.load(sys.stdin)
checks.append({
    'name': '${name}',
    'status': '${status}',
    'detail': '''${detail}'''
})
json.dump(checks, sys.stdout)
" 2>/dev/null || echo "$CHECKS")
}

# ---- fallback: use jq if python3 unavailable ----
if ! command -v python3 >/dev/null 2>&1; then
    add_check() {
        local name="$1" status="$2" detail="$3"
        [ "$status" = "fail" ] && OVERALL_OK=false
        CHECKS=$(echo "$CHECKS" | jq --arg n "$name" --arg s "$status" --arg d "$detail" \
            '. + [{"name":$n,"status":$s,"detail":$d}]')
    }
fi

# =============================================================================
# 1. Modbus devices — check serial ports are present
# =============================================================================
check_modbus_devices() {
    local devices_config="${CONFIG_DIR}/devices.toml"
    if [ ! -f "$devices_config" ]; then
        add_check "modbus_devices" "warn" "devices.toml not found; using example config"
        devices_config="${CONFIG_DIR}/devices.example.toml"
    fi

    if [ ! -f "$devices_config" ]; then
        add_check "modbus_devices" "fail" "No device configuration found"
        return
    fi

    # Extract serial ports from config
    local ports
    ports=$(grep -E '^\s*port\s*=' "$devices_config" | grep -v 'none' | sed 's/.*"\(.*\)".*/\1/' | sort -u)

    local all_ok=true
    local missing=""
    for port in $ports; do
        if [ ! -e "$port" ]; then
            all_ok=false
            missing="${missing} ${port}"
        fi
    done

    if [ "$all_ok" = true ]; then
        add_check "modbus_devices" "ok" "All serial ports present"
    else
        add_check "modbus_devices" "fail" "Missing serial ports:${missing}"
    fi
}

# =============================================================================
# 2. Disk space
# =============================================================================
check_disk_space() {
    local usage
    usage=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')

    if [ "$usage" -ge 90 ]; then
        add_check "disk_space" "fail" "Root filesystem ${usage}% full"
    elif [ "$usage" -ge 75 ]; then
        add_check "disk_space" "warn" "Root filesystem ${usage}% full"
    else
        add_check "disk_space" "ok" "Root filesystem ${usage}% used"
    fi

    # Check data directory separately if on different mount
    if mountpoint -q "${DATA_DIR}" 2>/dev/null; then
        local data_usage
        data_usage=$(df -h "${DATA_DIR}" | awk 'NR==2 {print $5}' | tr -d '%')
        if [ "$data_usage" -ge 90 ]; then
            add_check "disk_space_data" "fail" "Data partition ${data_usage}% full"
        else
            add_check "disk_space_data" "ok" "Data partition ${data_usage}% used"
        fi
    fi
}

# =============================================================================
# 3. CPU temperature
# =============================================================================
check_cpu_temp() {
    local temp_file="/sys/class/thermal/thermal_zone0/temp"
    if [ -f "$temp_file" ]; then
        local temp_raw
        temp_raw=$(cat "$temp_file")
        local temp_c=$((temp_raw / 1000))

        if [ "$temp_c" -ge 80 ]; then
            add_check "cpu_temp" "fail" "CPU temperature ${temp_c}C (throttling likely)"
        elif [ "$temp_c" -ge 70 ]; then
            add_check "cpu_temp" "warn" "CPU temperature ${temp_c}C (elevated)"
        else
            add_check "cpu_temp" "ok" "CPU temperature ${temp_c}C"
        fi
    else
        add_check "cpu_temp" "warn" "Temperature sensor not available"
    fi
}

# =============================================================================
# 4. Memory usage
# =============================================================================
check_memory() {
    local mem_info
    mem_info=$(free -m | awk 'NR==2 {printf "%d %d", $3, $2}')
    local used=$(echo "$mem_info" | awk '{print $1}')
    local total=$(echo "$mem_info" | awk '{print $2}')
    local pct=0
    if [ "$total" -gt 0 ]; then
        pct=$((used * 100 / total))
    fi

    if [ "$pct" -ge 90 ]; then
        add_check "memory" "fail" "Memory usage ${used}MB / ${total}MB (${pct}%)"
    elif [ "$pct" -ge 75 ]; then
        add_check "memory" "warn" "Memory usage ${used}MB / ${total}MB (${pct}%)"
    else
        add_check "memory" "ok" "Memory usage ${used}MB / ${total}MB (${pct}%)"
    fi
}

# =============================================================================
# 5. MQTT connection status
# =============================================================================
check_mqtt() {
    local site_config="${CONFIG_DIR}/site.toml"
    [ ! -f "$site_config" ] && site_config="${CONFIG_DIR}/site.example.toml"

    if [ ! -f "$site_config" ]; then
        add_check "mqtt" "warn" "No site config found"
        return
    fi

    local broker
    broker=$(grep -E '^\s*mqtt_broker\s*=' "$site_config" | head -1 | sed 's/.*"\(.*\)".*/\1/')

    if [ -z "$broker" ] || [ "$broker" = "" ]; then
        add_check "mqtt" "ok" "MQTT not configured (offline mode)"
        return
    fi

    # Extract host and port from mqtt://host:port
    local host port
    host=$(echo "$broker" | sed 's|.*://||' | cut -d: -f1)
    port=$(echo "$broker" | sed 's|.*://||' | cut -d: -f2)
    [ -z "$port" ] && port=1883

    # Quick TCP connectivity check (2 second timeout)
    if timeout 2 bash -c "echo >/dev/tcp/${host}/${port}" 2>/dev/null; then
        add_check "mqtt" "ok" "MQTT broker reachable at ${host}:${port}"
    else
        add_check "mqtt" "warn" "MQTT broker unreachable at ${host}:${port} (operating offline)"
    fi
}

# =============================================================================
# 6. Model files present and recent
# =============================================================================
check_models() {
    local model_dir="${DATA_DIR}/models"

    if [ ! -d "$model_dir" ]; then
        add_check "models" "warn" "Model directory not found"
        return
    fi

    local model_count
    model_count=$(find "$model_dir" -name "*.tflite" -o -name "*.onnx" -o -name "*.pkl" 2>/dev/null | wc -l)

    if [ "$model_count" -eq 0 ]; then
        add_check "models" "warn" "No model files found (using rule-based dispatch)"
        return
    fi

    # Check age of newest model
    local newest_age
    newest_age=$(find "$model_dir" -type f \( -name "*.tflite" -o -name "*.onnx" -o -name "*.pkl" \) \
        -printf '%T@\n' 2>/dev/null | sort -rn | head -1)

    if [ -n "$newest_age" ]; then
        local now
        now=$(date +%s)
        local age_days=$(( (now - ${newest_age%.*}) / 86400 ))

        if [ "$age_days" -gt 90 ]; then
            add_check "models" "warn" "Newest model is ${age_days} days old (consider updating)"
        else
            add_check "models" "ok" "${model_count} model file(s), newest is ${age_days} days old"
        fi
    else
        add_check "models" "ok" "${model_count} model file(s) found"
    fi
}

# =============================================================================
# 7. Event journal size
# =============================================================================
check_journal() {
    local db_file="${DATA_DIR}/db/knowledge.db"

    if [ ! -f "$db_file" ]; then
        add_check "journal" "warn" "Knowledge graph database not found"
        return
    fi

    local db_size_mb
    db_size_mb=$(du -m "$db_file" 2>/dev/null | awk '{print $1}')

    # Count recent readings (last 24 hours)
    local recent_count
    recent_count=$(sqlite3 "$db_file" \
        "SELECT COUNT(*) FROM readings WHERE timestamp > datetime('now', '-1 day');" 2>/dev/null || echo "0")

    # Count total decisions
    local decision_count
    decision_count=$(sqlite3 "$db_file" \
        "SELECT COUNT(*) FROM decisions;" 2>/dev/null || echo "0")

    if [ "$db_size_mb" -ge 500 ]; then
        add_check "journal" "warn" "Database is ${db_size_mb}MB (consider pruning old readings)"
    else
        add_check "journal" "ok" "Database ${db_size_mb}MB, ${recent_count} readings (24h), ${decision_count} decisions total"
    fi
}

# =============================================================================
# 8. Agent process running
# =============================================================================
check_agent_process() {
    if systemctl is-active --quiet microgrid-agent 2>/dev/null; then
        local uptime
        uptime=$(systemctl show microgrid-agent --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2)
        add_check "agent_process" "ok" "Service active since ${uptime}"
    elif pgrep -f "microgrid.*main" >/dev/null 2>&1; then
        add_check "agent_process" "ok" "Agent process running (not via systemd)"
    else
        add_check "agent_process" "fail" "Agent process not running"
    fi
}

# =============================================================================
# Run all checks
# =============================================================================
check_modbus_devices
check_disk_space
check_cpu_temp
check_memory
check_mqtt
check_models
check_journal
check_agent_process

# =============================================================================
# Output JSON report
# =============================================================================
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
HOSTNAME=$(hostname)

if [ "$OVERALL_OK" = true ]; then
    STATUS="healthy"
    EXIT_CODE=0
else
    STATUS="degraded"
    EXIT_CODE=1
fi

python3 -c "
import json, sys

report = {
    'timestamp': '${TIMESTAMP}',
    'hostname': '${HOSTNAME}',
    'status': '${STATUS}',
    'checks': json.loads('''${CHECKS}''')
}

json.dump(report, sys.stdout, indent=2)
print()
" 2>/dev/null || {
    # Fallback if python3 is unavailable
    echo "{\"timestamp\":\"${TIMESTAMP}\",\"hostname\":\"${HOSTNAME}\",\"status\":\"${STATUS}\",\"checks\":${CHECKS}}"
}

exit $EXIT_CODE
