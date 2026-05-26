#!/usr/bin/env bash
# discord-watchdog.sh — Keep Discord tmux sessions alive
#
# Runs as a background daemon. Respawns dead sessions and discovers new
# channels/threads on interval.

set -euo pipefail

SESSIONS_DIR="$HOME/.claude/discord-sessions"
CONFIG_FILE="$SESSIONS_DIR/config.env"

# Load config for interval overrides
[[ -f "$CONFIG_FILE" ]] && { set -a; source "$CONFIG_FILE"; set +a; }

INTERVAL="${DISCORD_WATCHDOG_INTERVAL:-30}"
DISCOVER_INTERVAL="${DISCORD_DISCOVER_INTERVAL:-60}"
CLEANUP_INTERVAL="${DISCORD_CLEANUP_INTERVAL:-300}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANAGER="$SCRIPT_DIR/discord-session-manager.sh"
TMUX_SESSION="dc-watchdog"
SLASH_DAEMON_SESSION="dc-slash-daemon"
PIDFILE="$SESSIONS_DIR/watchdog.pid"

_log() { echo "[$(date +%H:%M:%S)] $*"; }

_ensure_slash_daemon() {
  if ! tmux has-session -t "$SLASH_DAEMON_SESSION" 2>/dev/null; then
    _log "Slash daemon not running — spawning in tmux: $SLASH_DAEMON_SESSION"
    tmux new-session -d -s "$SLASH_DAEMON_SESSION" -c "$SCRIPT_DIR" \
      "bun $SCRIPT_DIR/discord-slash-daemon.ts"
    _log "Slash daemon started"
  fi
}

cmd_run() {
  _log "Watchdog started (interval=${INTERVAL}s, discover=${DISCOVER_INTERVAL}s, cleanup=${CLEANUP_INTERVAL}s, pid=$$)"
  mkdir -p "$SESSIONS_DIR"
  echo $$ > "$PIDFILE"
  trap 'rm -f "$PIDFILE"; _log "Watchdog stopped"; exit 0' INT TERM

  local last_discover=0
  local last_cleanup=0

  while true; do
    local now
    now=$(date +%s)

    if [[ -f "$SESSIONS_DIR/sessions.json" ]]; then
      "$MANAGER" respawn-dead 2>&1 | while read -r line; do
        [[ -n "$line" ]] && _log "$line"
      done
    fi

    # Ensure the slash command daemon is alive
    _ensure_slash_daemon

    if (( now - last_discover >= DISCOVER_INTERVAL )); then
      _log "Discovering new channels and threads..."
      "$MANAGER" discover-all 2>&1 | while read -r line; do
        [[ -n "$line" ]] && _log "$line"
      done
      # Update status channel topic after discovery
      "$MANAGER" set-status 2>/dev/null || true
      last_discover=$now
    fi

    if (( now - last_cleanup >= CLEANUP_INTERVAL )); then
      _log "Running stale session cleanup + idle suspension..."
      "$MANAGER" cleanup-stale 2>&1 | while read -r line; do
        [[ -n "$line" ]] && _log "$line"
      done
      "$MANAGER" suspend-idle 2>&1 | while read -r line; do
        [[ -n "$line" ]] && _log "$line"
      done
      last_cleanup=$now
    fi

    sleep "$INTERVAL"
  done
}

cmd_daemon() {
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "Watchdog already running in tmux session '$TMUX_SESSION'"
    return 0
  fi
  tmux new-session -d -s "$TMUX_SESSION" "$0"
  echo "Watchdog started in tmux session '$TMUX_SESSION'"
  echo "  Attach: tmux attach -t $TMUX_SESSION"
}

cmd_stop() {
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    tmux kill-session -t "$TMUX_SESSION"
    echo "Watchdog stopped"
  elif [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "Watchdog stopped (via pid)"
  else
    echo "Watchdog not running"
  fi
  # Also stop the slash daemon if running
  if tmux has-session -t "$SLASH_DAEMON_SESSION" 2>/dev/null; then
    tmux kill-session -t "$SLASH_DAEMON_SESSION"
    echo "Slash daemon stopped"
  fi
}

cmd_status() {
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "Watchdog: RUNNING (tmux: $TMUX_SESSION)"
  elif [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Watchdog: RUNNING (pid: $(cat "$PIDFILE"))"
  else
    echo "Watchdog: STOPPED"
  fi
  if tmux has-session -t "$SLASH_DAEMON_SESSION" 2>/dev/null; then
    echo "Slash daemon: RUNNING (tmux: $SLASH_DAEMON_SESSION)"
  else
    echo "Slash daemon: STOPPED"
  fi
}

case "${1:-}" in
  --daemon) cmd_daemon ;;
  --stop)   cmd_stop ;;
  --status) cmd_status ;;
  *)        cmd_run ;;
esac
