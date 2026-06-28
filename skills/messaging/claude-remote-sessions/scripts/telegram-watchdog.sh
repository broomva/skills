#!/usr/bin/env bash
# telegram-watchdog.sh — Keep Telegram tmux sessions alive (respawn only, no discovery)

set -euo pipefail

SESSIONS_DIR="$HOME/.claude/telegram-sessions"
CONFIG_FILE="$SESSIONS_DIR/config.env"

[[ -f "$CONFIG_FILE" ]] && { set -a; source "$CONFIG_FILE"; set +a; }

INTERVAL="${TELEGRAM_WATCHDOG_INTERVAL:-30}"
MANAGER="$(cd "$(dirname "$0")" && pwd)/telegram-session-manager.sh"
TMUX_SESSION="tg-watchdog"
PIDFILE="$SESSIONS_DIR/watchdog.pid"

_log() { echo "[$(date +%H:%M:%S)] $*"; }

cmd_run() {
  _log "Telegram watchdog started (interval=${INTERVAL}s, pid=$$)"
  mkdir -p "$SESSIONS_DIR"
  echo $$ > "$PIDFILE"
  trap 'rm -f "$PIDFILE"; _log "Watchdog stopped"; exit 0' INT TERM

  while true; do
    if [[ -f "$SESSIONS_DIR/sessions.json" ]]; then
      "$MANAGER" respawn-dead 2>&1 | while read -r line; do
        [[ -n "$line" ]] && _log "$line"
      done
    fi
    sleep "$INTERVAL"
  done
}

cmd_daemon() {
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "Telegram watchdog already running in '$TMUX_SESSION'"
    return 0
  fi
  tmux new-session -d -s "$TMUX_SESSION" "$0"
  echo "Telegram watchdog started in tmux '$TMUX_SESSION'"
}

cmd_stop() {
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    tmux kill-session -t "$TMUX_SESSION"
    echo "Telegram watchdog stopped"
  elif [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "Telegram watchdog stopped (via pid)"
  else
    echo "Telegram watchdog not running"
  fi
}

cmd_status() {
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "Telegram watchdog: RUNNING (tmux: $TMUX_SESSION)"
  elif [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Telegram watchdog: RUNNING (pid: $(cat "$PIDFILE"))"
  else
    echo "Telegram watchdog: STOPPED"
  fi
}

case "${1:-}" in
  --daemon) cmd_daemon ;;
  --stop)   cmd_stop ;;
  --status) cmd_status ;;
  *)        cmd_run ;;
esac
