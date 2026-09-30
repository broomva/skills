#!/bin/bash
# tick.sh: one fleet-reconcile tick for one scope (spec §5.3, §5.7).
#
# launchd runs it hourly (templates/launchd.plist.template, installed by the
# owner with scripts/install.sh); the owner can also run it by hand:
#     FLEET_SCOPE=broomva bash scripts/tick.sh
#
# Adapted from governed-autonomy-loop's tick.sh. Kept: the recursion guard
# (FLEET_CHILD=1, inherited by everything the tick starts), the kill switch read
# before anything fires, DRY_RUN falling toward dry, the mkdir lock with stale
# reclaim, the TERM-then-KILL watchdog, and the tick_fire / runner_exit records.
# Not carried over: the fire gate and quiet hours (launchd fires hourly, the
# owner's cadence) and the inner resume tick (phase 2's resume verb).
#
# PHASE 1 runs deterministic code only; no model runs and no session is acted
# on. Per tick: kill switch, config-check, lock, the fleet GH_TOKEN, observe,
# report (classes, count check, the ask batch), the ask notification, the core
# comparison once a day, and the ledger's tick_fire and runner_exit records.
# Phase 2 adds `fleet recover` before the coordinator and the coordinator itself.
#
# Env: FLEET_SCOPE (required); FLEET_CONFIG (default ~/.config/ctx/fleet.json);
# DRY_RUN (any value but 0 forces dry; no value makes a tick live, only the
# config's dry_run 0 does); FLEET_PYTHON.
set -uo pipefail

# ── recursion guard ──────────────────────────────────────────────────────────
if [ -n "${FLEET_CHILD:-}" ]; then
  exit 0
fi
export FLEET_CHILD=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FLEET="$SCRIPT_DIR/fleet"
SCOPE="${FLEET_SCOPE:-}"
case "$SCOPE" in
  ([a-z0-9]*) : ;;
  (*) echo "tick.sh: FLEET_SCOPE is unset or not a scope id" >&2; exit 0 ;;
esac

cfg() { "$FLEET" config-get "$SCOPE" "$1" 2>/dev/null; }

# BSD (macOS) or GNU stat, detected once by behaviour, as governed-autonomy-loop does.
if stat -c %Y / >/dev/null 2>&1; then
  file_mtime() { stat -c %Y "$1" 2>/dev/null; }
  file_mode() { stat -c %a "$1" 2>/dev/null; }
else
  file_mtime() { stat -f %m "$1" 2>/dev/null; }
  file_mode() { stat -f %Lp "$1" 2>/dev/null; }
fi

STATE_DIR=$(cfg state_dir)
[ -n "$STATE_DIR" ] || STATE_DIR="$HOME/.local/state/fleet-reconcile/$SCOPE"
mkdir -p "$STATE_DIR" 2>/dev/null && chmod 700 "$STATE_DIR" 2>/dev/null
LOG="$STATE_DIR/tick.log"
NOTICE="$STATE_DIR/.disabled-notice"
LOCK="$STATE_DIR/.tick.lock"
COUNTER="$STATE_DIR/tick-counter"
log() { echo "[$(date -u +%FT%TZ)] $*" >> "$LOG"; }

# ── kill switch: read before anything fires; an unreadable value is off ──────
KILL=$(cfg dispatch_enabled)
if [ "$KILL" != "1" ]; then
  if [ ! -f "$NOTICE" ]; then
    log "scope $SCOPE DISABLED (dispatch_enabled='${KILL:-<unreadable>}'): no tick until it is exactly 1"
    touch "$NOTICE"
  fi
  exit 0
fi
rm -f "$NOTICE"

if ! "$FLEET" config-check "$SCOPE" >> "$LOG" 2>&1; then
  log "config-check failed for $SCOPE: no tick"
  exit 0
fi

# ── dry run falls toward dry ─────────────────────────────────────────────────
DRY=$(cfg dry_run)
[ "$DRY" = "0" ] || DRY=1
case "${DRY_RUN:-}" in
  (""|0) : ;;
  (*) DRY=1 ;;
esac

# ── lock: one tick per scope at a time ───────────────────────────────────────
NOW=$(date +%s)
if ! mkdir "$LOCK" 2>/dev/null; then
  HOLDER=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  STEP=$(cat "$LOCK/runner-pid" 2>/dev/null || echo "")
  if [ -n "$HOLDER" ] && kill -0 "$HOLDER" 2>/dev/null; then
    log "tick skipped: tick $HOLDER is still running"; exit 0
  fi
  if [ -n "$STEP" ] && kill -0 "$STEP" 2>/dev/null; then
    log "tick skipped: step $STEP is still running"; exit 0
  fi
  MT=$(file_mtime "$LOCK")
  case "$MT" in (""|*[!0-9]*) MT=$NOW ;; esac
  if [ $((NOW - MT)) -lt 120 ]; then exit 0; fi
  if ! mv "$LOCK" "$LOCK.stale.$$" 2>/dev/null; then exit 0; fi
  rm -f "$LOCK.stale.$$/pid" "$LOCK.stale.$$/runner-pid"
  rmdir "$LOCK.stale.$$" 2>/dev/null
  mkdir "$LOCK" 2>/dev/null || exit 0
  log "reclaimed a stale lock (tick ${HOLDER:-?}, step ${STEP:-?}, both gone)"
fi
echo $$ > "$LOCK/pid"
STEP_PID=""
release() {
  [ -n "$STEP_PID" ] && kill "$STEP_PID" 2>/dev/null
  rm -f "$LOCK/pid" "$LOCK/runner-pid"
  rmdir "$LOCK" 2>/dev/null
}
trap release EXIT

# ── tick number ──────────────────────────────────────────────────────────────
N=$(cat "$COUNTER" 2>/dev/null || echo 0)
case "$N" in (*[!0-9]*|"") N=0 ;; esac
N=$((N + 1))
echo "$N" > "$COUNTER"

# ── the fleet GH_TOKEN: read from its 0600 file, never argv, never printed ───
GH_AUTH="keyring"
TOKFILE=$(cfg gh_token_file)
if [ -n "$TOKFILE" ]; then
  if [ -r "$TOKFILE" ]; then
    MODE=$(file_mode "$TOKFILE")
    [ "$MODE" = "600" ] || [ "$MODE" = "400" ] || log "WARN: $TOKFILE has mode $MODE, not 600"
    GH_TOKEN=$(head -c 512 "$TOKFILE" | tr -d '[:space:]')
    export GH_TOKEN
    GH_AUTH="fleet token file"
  else
    GH_AUTH="keyring (token file $TOKFILE unreadable)"
  fi
fi

"$FLEET" ledger-record fire --scope "$SCOPE" --tick "$N" --dry-run "$DRY" --detail "gh: $GH_AUTH" >> "$LOG" 2>&1
log "tick $N scope $SCOPE (dry_run=$DRY, gh: $GH_AUTH)"

# ── steps, each bounded by what is left of the tick's budget ─────────────────
TIMEOUT_MIN=$(cfg tick_timeout_min)
case "$TIMEOUT_MIN" in (*[!0-9]*|""|0) TIMEOUT_MIN=15 ;; esac
BUDGET_S=$((TIMEOUT_MIN * 60))
case "${FLEET_TICK_TIMEOUT_S:-}" in (""|*[!0-9]*) : ;; (*) BUDGET_S=$FLEET_TICK_TIMEOUT_S ;; esac  # tests
DEADLINE=$((NOW + BUDGET_S))

# step NAME CMD... : run CMD in the background under a TERM-then-KILL watchdog;
# sets RC. The watchdog traps TERM and kills its own sleep, so no sleep outlives
# the tick.
step() {
  local name=$1; shift
  local left=$((DEADLINE - $(date +%s)))
  if [ "$left" -le 0 ]; then log "step $name skipped: the tick is out of time"; RC=124; return; fi
  "$@" >> "$LOG" 2>&1 &
  STEP_PID=$!
  echo "$STEP_PID" > "$LOCK/runner-pid"
  (
    trap 'kill $(jobs -p) 2>/dev/null; exit 0' TERM
    sleep "$left" &
    wait
    if kill -0 "$STEP_PID" 2>/dev/null; then
      kill "$STEP_PID" 2>/dev/null
      echo "[$(date -u +%FT%TZ)] step $name over the tick's budget: sent TERM" >> "$LOG"
      # In the background too: bash runs a trap only after a foreground
      # command ends, so a foreground sleep here would hold the reap for 30 s.
      sleep 30 &
      wait
      kill -9 "$STEP_PID" 2>/dev/null
    fi
  ) >> "$LOG" 2>&1 &
  local wd=$!
  wait "$STEP_PID"
  RC=$?
  STEP_PID=""
  kill "$wd" 2>/dev/null
  wait "$wd" 2>/dev/null
  log "step $name rc=$RC"
}

RCS=""
step observe "$FLEET" observe --scope "$SCOPE" --tick "$N"; RCS="observe=$RC"
if [ "$RC" = "0" ]; then
  step report "$FLEET" report --scope "$SCOPE" --tick "$N" --dry-run "$DRY"; RCS="$RCS report=$RC"
fi
step ask "$FLEET" act ask --notify --scope "$SCOPE" --tick "$N" --dry-run "$DRY"; RCS="$RCS ask=$RC"
step compare "$FLEET" core-compare --scope "$SCOPE"; RCS="$RCS compare=$RC"

FINAL=0
case "$RCS" in (*observe=[!0]*|*report=[!0]*|*ask=[!0]*) FINAL=1 ;; esac
"$FLEET" ledger-record exit --scope "$SCOPE" --tick "$N" --dry-run "$DRY" --exit-code "$FINAL" \
  --detail "$RCS" >> "$LOG" 2>&1
log "tick $N done: $RCS"
exit 0
