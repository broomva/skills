#!/usr/bin/env bash
# telegram-session-manager.sh — Spawn and track per-chat Claude Code sessions for Telegram

set -euo pipefail

TELEGRAM_MAIN_DIR="$HOME/.claude/channels/telegram"
SESSIONS_DIR="$HOME/.claude/telegram-sessions"
SESSIONS_REGISTRY="$SESSIONS_DIR/sessions.json"
CONFIG_FILE="$SESSIONS_DIR/config.env"
TMUX_PREFIX="tg"

# ── Load config ──────────────────────────────────────────────────────────

[[ -f "$CONFIG_FILE" ]] && { set -a; source "$CONFIG_FILE"; set +a; }

ALLOWED_USER_ID="${TELEGRAM_ALLOWED_USER_ID:-}"
WORKDIR="${TELEGRAM_SESSION_WORKDIR:-$HOME}"

_require_config() {
  [[ -n "$ALLOWED_USER_ID" ]] || { echo "ERROR: TELEGRAM_ALLOWED_USER_ID not set in $CONFIG_FILE"; exit 1; }
}

# ── Helpers ──────────────────────────────────────────────────────────────

_require_main_config() {
  [[ -f "$TELEGRAM_MAIN_DIR/.env" ]] || { echo "ERROR: No Telegram bot token at $TELEGRAM_MAIN_DIR/.env"; echo "Run: /telegram:configure <token>"; exit 1; }
}

_session_name() { echo "${TMUX_PREFIX}-${1}"; }
_state_dir()    { echo "${SESSIONS_DIR}/${1}"; }

_ensure_dirs() {
  mkdir -p "$SESSIONS_DIR"
  [[ -f "$SESSIONS_REGISTRY" ]] || echo '{}' > "$SESSIONS_REGISTRY"
}

_ensure_state_dir() {
  local id="$1"
  local dir
  dir="$(_state_dir "$id")"
  mkdir -p "$dir/approved"
  [[ -L "$dir/.env" ]] || ln -sf "$TELEGRAM_MAIN_DIR/.env" "$dir/.env"

  cat > "$dir/access.json" <<EOF
{
  "dmPolicy": "allowlist",
  "allowFrom": ["$ALLOWED_USER_ID"],
  "groups": {},
  "pending": {}
}
EOF
}

_registry_set() {
  local id="$1" name="$2"
  _ensure_dirs
  python3 -c "
import json, datetime
with open('$SESSIONS_REGISTRY') as f: reg = json.load(f)
reg['$id'] = {
    'name': '$name',
    'tmux': '$(_session_name "$id")',
    'created': datetime.datetime.now().isoformat(timespec='seconds')
}
with open('$SESSIONS_REGISTRY', 'w') as f: json.dump(reg, f, indent=2)
"
}

_registry_remove() {
  local id="$1"
  python3 -c "
import json
with open('$SESSIONS_REGISTRY') as f: reg = json.load(f)
reg.pop('$id', None)
with open('$SESSIONS_REGISTRY', 'w') as f: json.dump(reg, f, indent=2)
"
}

_is_alive() { tmux has-session -t "$(_session_name "$1")" 2>/dev/null; }

_spawn_tmux() {
  local id="$1" name="$2" workdir="${3:-$WORKDIR}"
  local session_name state_dir claude_cmd
  session_name="$(_session_name "$id")"
  state_dir="$(_state_dir "$id")"

  claude_cmd="TELEGRAM_STATE_DIR='$state_dir' claude"
  claude_cmd+=" --channels plugin:telegram@claude-plugins-official"
  claude_cmd+=" --dangerously-skip-permissions"
  claude_cmd+=" --name '${name}'"

  echo "$workdir" > "$state_dir/.workdir"

  tmux new-session -d -s "$session_name" -c "$workdir" "bash -c '${claude_cmd}'"
  echo "$session_name"
}

# ── Commands ─────────────────────────────────────────────────────────────

cmd_spawn() {
  local chat_id="" label="" workdir=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --name)    label="$2"; shift 2 ;;
      --workdir) workdir="$2"; shift 2 ;;
      *)         chat_id="$1"; shift ;;
    esac
  done
  [[ -n "$chat_id" ]] || { echo "Usage: spawn <chat_id> [--name <label>] [--workdir <path>]"; exit 1; }

  _require_main_config
  _require_config
  _ensure_dirs

  if _is_alive "$chat_id"; then
    echo "ALIVE  $(_session_name "$chat_id")"
    return 0
  fi

  local name="${label:-tg-${chat_id: -6}}"
  _ensure_state_dir "$chat_id"
  _spawn_tmux "$chat_id" "$name" "$workdir"
  _registry_set "$chat_id" "$name"

  echo "SPAWNED  $(_session_name "$chat_id")  name=$name  workdir=${workdir:-$WORKDIR}"
}

cmd_list() {
  _ensure_dirs
  echo "Telegram Sessions:"
  python3 -c "
import json, subprocess
with open('$SESSIONS_REGISTRY') as f: reg = json.load(f)
if not reg: print('  (none)'); exit()
for cid, info in sorted(reg.items(), key=lambda x: x[1].get('created','')):
    alive = subprocess.run(['tmux', 'has-session', '-t', info['tmux']], capture_output=True).returncode == 0
    status = 'UP' if alive else 'DOWN'
    print(f'  [{status:4}]  {info[\"tmux\"]:25}  {info[\"name\"]}')
"
}

cmd_kill() {
  local id="${1:?Usage: kill <chat_id>}"
  local sn
  sn="$(_session_name "$id")"
  if _is_alive "$id"; then
    tmux kill-session -t "$sn"
    echo "KILLED  $sn"
  fi
  _registry_remove "$id"
}

cmd_kill_all() {
  _ensure_dirs
  local killed=0
  for sn in $(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep "^${TMUX_PREFIX}-" || true); do
    tmux kill-session -t "$sn"; echo "KILLED  $sn"; killed=$((killed + 1))
  done
  echo '{}' > "$SESSIONS_REGISTRY"
  echo "Total: $killed"
}

cmd_respawn_dead() {
  _ensure_dirs
  python3 -c "
import json
with open('$SESSIONS_REGISTRY') as f: reg = json.load(f)
for cid, info in reg.items():
    print(f'{cid} {info[\"name\"]}')
" | while IFS=' ' read -r cid name; do
    if ! _is_alive "$cid"; then
      echo "RESPAWNING $(_session_name "$cid") ($name)"
      _ensure_state_dir "$cid"
      local wd=""
      [[ -f "$(_state_dir "$cid")/.workdir" ]] && wd="$(cat "$(_state_dir "$cid")/.workdir")"
      _spawn_tmux "$cid" "$name" "$wd"
    fi
  done
}

cmd_status() {
  echo "Telegram Session Manager"
  echo "════════════════════════"
  [[ -f "$TELEGRAM_MAIN_DIR/.env" ]] && echo "Bot token: configured" || echo "Bot token: MISSING"
  echo "Sessions dir: $SESSIONS_DIR"
  echo ""
  cmd_list
}

cmd_init() {
  _ensure_dirs
  echo "Telegram Sessions — Setup"
  echo "========================="
  echo ""
  if [[ -f "$CONFIG_FILE" ]]; then
    echo "Config exists at $CONFIG_FILE"
    cat "$CONFIG_FILE"
    echo ""
    read -p "Overwrite? [y/N] " -r
    [[ "$REPLY" =~ ^[Yy]$ ]] || { echo "Kept existing config."; return 0; }
  fi

  read -p "Your Telegram user ID (from @userinfobot): " uid
  read -p "Default workdir [$HOME]: " wd
  wd="${wd:-$HOME}"

  cat > "$CONFIG_FILE" <<EOF
TELEGRAM_ALLOWED_USER_ID="$uid"
TELEGRAM_SESSION_WORKDIR="$wd"
EOF

  echo ""
  echo "Config saved to $CONFIG_FILE"
  echo "Next: ./scripts/telegram-session-manager.sh spawn <chat_id> --name my-chat"
}

# ── Main ─────────────────────────────────────────────────────────────────

case "${1:-help}" in
  spawn)         shift; cmd_spawn "$@" ;;
  list)          cmd_list ;;
  kill)          shift; cmd_kill "$@" ;;
  kill-all)      cmd_kill_all ;;
  respawn-dead)  cmd_respawn_dead ;;
  status)        cmd_status ;;
  init)          cmd_init ;;
  help|--help|-h)
    cat <<'HELP'
Telegram Session Manager — per-chat Claude Code sessions via tmux

  init              Setup — configure user ID and workdir
  spawn <chat_id> [--name <label>] [--workdir <path>]
  list              List sessions with UP/DOWN status
  kill <id>         Kill and deregister a session
  kill-all          Kill all Telegram sessions
  respawn-dead      Respawn any DOWN sessions (used by watchdog)
  status            Overview

Note: Telegram Bot API has no chat listing endpoint.
Sessions must be spawned manually by chat ID.
Get your chat ID by messaging @userinfobot on Telegram.
HELP
    ;;
  *) echo "Unknown: $1 (try --help)"; exit 1 ;;
esac
