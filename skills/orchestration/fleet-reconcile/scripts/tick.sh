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
# on. Per tick: kill switch, config-check, lock, the tick number, the fleet
# token, observe, report (classes, count check, asks), the core comparison once
# a day, the ledger's tick_fire and runner_exit, and, with the lock released,
# the owner's dialog (fleet act ask --show).
# Phase 2 adds `fleet recover` before the coordinator and the coordinator itself.
#
# A tick that fails (a bad config, observe or report failing) notifies the
# owner directly, at most once per 6 h per kind, and exits 1 so launchd's last
# exit shows it. The kill switch set to off is not a failure: exit 0.
#
# Env: FLEET_SCOPE (required); FLEET_CONFIG (default ~/.config/ctx/fleet.json);
# DRY_RUN (any value but 0 forces dry; no value makes a tick live, only the
# config's dry_run 0 does); FLEET_PYTHON. Test seams: FLEET_TICK_TIMEOUT_S,
# FLEET_NOTIFY=0, FLEET_OSASCRIPT_BIN, FLEET_P9_BIN.
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
  (*) echo "tick.sh: FLEET_SCOPE is unset or not a scope id" >&2; exit 2 ;;
esac
case "$SCOPE" in
  (*[!a-z0-9_-]*) echo "tick.sh: FLEET_SCOPE is not a scope id" >&2; exit 2 ;;
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
log() { echo "[$(date -u +%FT%TZ)] $*" >> "$LOG"; }

# alert KIND MESSAGE: tell the owner directly, from bash, so it works when
# Python or the config is what broke: a dialog, since notification banners are
# stored but not shown on this Mac (spec §5.7). At most once per 6 h per kind.
# The message is this script's own text, never another session's words. Call
# it with the lock released: the dialog waits up to 10 minutes.
alert() {
  local kind=$1 msg=$2 stamp="$STATE_DIR/.alert-$1" now last
  log "ALERT $kind: $msg"
  now=$(date +%s)
  last=$(file_mtime "$stamp"); case "$last" in (""|*[!0-9]*) last=0 ;; esac
  [ $((now - last)) -ge 21600 ] || return 0
  touch "$stamp"
  [ "${FLEET_NOTIFY:-}" = "0" ] && return 0
  local title="fleet $SCOPE: tick failed" body="$msg | log: $LOG"
  body=${body//\\/\\\\}; body=${body//\"/\\\"}
  "${FLEET_OSASCRIPT_BIN:-osascript}" -e "display dialog \"$body\" with title \"$title\" buttons {\"OK\"} default button \"OK\" giving up after 600" \
    >/dev/null 2>&1 </dev/null
  local p9="${FLEET_P9_BIN:-$(command -v p9 2>/dev/null)}"
  [ -n "$p9" ] && "$p9" notify "$title" --body "$msg" --kind fleet-alert >/dev/null 2>&1 </dev/null
  return 0
}

# ── kill switch: read before anything fires; an unreadable value is off ──────
# Off by the owner's choice (a value other than 1) exits 0. Off because the
# config can't be read is also off, and is a failure the owner hears about.
KILL=$(cfg dispatch_enabled)
KILL_RC=$?
if [ "$KILL_RC" != "0" ]; then
  alert config "the fleet config can't be read for scope $SCOPE (fleet config-check says why); no tick"
  exit 1
fi
if [ "$KILL" != "1" ]; then
  if [ ! -f "$NOTICE" ]; then
    log "scope $SCOPE DISABLED (dispatch_enabled='${KILL:-<unreadable>}'): no tick until it is exactly 1"
    touch "$NOTICE"
  fi
  exit 0
fi
rm -f "$NOTICE"

if ! "$FLEET" config-check "$SCOPE" >> "$LOG" 2>&1; then
  alert config "config-check failed for scope $SCOPE; no tick until it passes"
  exit 1
fi

# ── dry run falls toward dry ─────────────────────────────────────────────────
DRY=$(cfg dry_run)
[ "$DRY" = "0" ] || DRY=1
case "${DRY_RUN:-}" in
  (""|0) : ;;
  (*) DRY=1 ;;
esac

# ── lock: one tick per scope at a time ───────────────────────────────────────
# A stale lock is reclaimed under a second mkdir mutex, and its holder is
# re-read inside it, so two ticks that both judged it stale can't both run.
NOW=$(date +%s)
if ! mkdir "$LOCK" 2>/dev/null; then
  RECLAIM="$LOCK.reclaim"
  if ! mkdir "$RECLAIM" 2>/dev/null; then
    RT=$(file_mtime "$RECLAIM"); case "$RT" in (""|*[!0-9]*) RT=$NOW ;; esac
    [ $((NOW - RT)) -ge 60 ] && rmdir "$RECLAIM" 2>/dev/null
    exit 0
  fi
  HOLDER=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  STEP=$(cat "$LOCK/runner-pid" 2>/dev/null || echo "")
  MT=$(file_mtime "$LOCK"); case "$MT" in (""|*[!0-9]*) MT=$NOW ;; esac
  if { [ -n "$HOLDER" ] && kill -0 "$HOLDER" 2>/dev/null; } || { [ -n "$STEP" ] && kill -0 "$STEP" 2>/dev/null; } \
     || [ $((NOW - MT)) -lt 120 ]; then
    rmdir "$RECLAIM" 2>/dev/null
    log "tick skipped: a tick holds the lock (tick ${HOLDER:-?}, step ${STEP:-?})"
    # A lock held far past a tick's budget: a hung tick, or a pid reused after
    # a crash. Not reclaimed (the pid is alive); the owner hears about it.
    if [ $((NOW - MT)) -ge 7200 ]; then
      alert lock "the tick lock has been held for $(( (NOW - MT) / 60 )) min by pid ${HOLDER:-?}; ticks are skipped until it goes ($LOCK)"
      exit 1
    fi
    exit 0
  fi
  rm -f "$LOCK/pid" "$LOCK/runner-pid"
  rmdir "$LOCK" 2>/dev/null
  if ! mkdir "$LOCK" 2>/dev/null; then rmdir "$RECLAIM" 2>/dev/null; exit 0; fi
  rmdir "$RECLAIM" 2>/dev/null
  log "reclaimed a stale lock (tick ${HOLDER:-?}, step ${STEP:-?}, both gone)"
fi
echo $$ > "$LOCK/pid"
STEP_PID=""
WD_PID=""
release() {
  [ -n "$STEP_PID" ] && kill -TERM -- "-$STEP_PID" 2>/dev/null
  [ -n "$WD_PID" ] && kill "$WD_PID" 2>/dev/null
  rm -f "$LOCK/pid" "$LOCK/runner-pid"
  rmdir "$LOCK" 2>/dev/null
}
trap release EXIT

# ── tick number: past both the counter and the ledger's last tick ─────────────
N=$("$FLEET" next-tick --scope "$SCOPE" 2>>"$LOG")
case "$N" in
  (""|*[!0-9]*) trap - EXIT; release; alert tick "could not take a tick number for scope $SCOPE"; exit 1 ;;
esac

# The release this tick runs (install.sh pins a copy and writes RELEASE there).
RELEASE=$(head -1 "$SCRIPT_DIR/../../../RELEASE" 2>/dev/null | sed 's/^release //')
[ -n "$RELEASE" ] || RELEASE="checkout"

# ── the fleet token: read from its 0600 file, never argv, never printed ───────
# Exported for the observe step only (gh is the only reader); observe passes it
# to gh and to nothing else.
GH_AUTH="keyring"
TOKEN=""
TOKFILE=$(cfg gh_token_file)
if [ -n "$TOKFILE" ]; then
  if [ -r "$TOKFILE" ]; then
    MODE=$(file_mode "$TOKFILE")
    if [ "$MODE" != "600" ] && [ "$MODE" != "400" ]; then
      GH_AUTH="keyring (the token file has mode $MODE, not 600: not used)"
    else
      TOKEN=$(head -c 512 "$TOKFILE" | tr -d '[:space:]')
      if [ -n "$TOKEN" ]; then GH_AUTH="fleet token file"; else GH_AUTH="keyring (the token file is empty)"; fi
    fi
  else
    GH_AUTH="keyring (the token file is unreadable)"
  fi
fi

"$FLEET" ledger-append fire --scope "$SCOPE" --tick "$N" --dry-run "$DRY" --detail "release: $RELEASE; gh: $GH_AUTH" \
  >> "$LOG" 2>&1
log "tick $N scope $SCOPE (dry_run=$DRY, gh: $GH_AUTH, release: $RELEASE)"

# ── steps, each bounded by what is left of the tick's budget ─────────────────
TIMEOUT_MIN=$(cfg tick_timeout_min)
case "$TIMEOUT_MIN" in (*[!0-9]*|""|0) TIMEOUT_MIN=15 ;; esac
BUDGET_S=$((TIMEOUT_MIN * 60))
case "${FLEET_TICK_TIMEOUT_S:-}" in (""|*[!0-9]*) : ;; (*) BUDGET_S=$FLEET_TICK_TIMEOUT_S ;; esac
DEADLINE=$((NOW + BUDGET_S))

# step NAME CMD... : run CMD in its own process group under a TERM-then-KILL
# watchdog, so a timeout also ends the command's children (claude, gh); sets RC.
step() {
  local name=$1; shift
  local left=$((DEADLINE - $(date +%s)))
  if [ "$left" -le 0 ]; then log "step $name skipped: the tick is out of time"; RC=124; return; fi
  set -m
  "$@" < /dev/null >> "$LOG" 2>&1 &
  STEP_PID=$!
  set +m
  echo "$STEP_PID" > "$LOCK/runner-pid"
  (
    trap 'kill $(jobs -p) 2>/dev/null; exit 0' TERM
    sleep "$left" &
    wait
    if kill -0 "$STEP_PID" 2>/dev/null; then
      kill -TERM -- "-$STEP_PID" 2>/dev/null
      echo "[$(date -u +%FT%TZ)] step $name over the tick's budget: sent TERM to its process group" >> "$LOG"
      # In the background too: bash runs a trap only after a foreground
      # command ends, so a foreground sleep here would hold the reap for 30 s.
      sleep 30 &
      wait
      kill -KILL -- "-$STEP_PID" 2>/dev/null
    fi
  ) >> "$LOG" 2>&1 &
  WD_PID=$!
  wait "$STEP_PID"
  RC=$?
  kill -KILL -- "-$STEP_PID" 2>/dev/null  # children that outlived their leader, TERM-proof ones included
  STEP_PID=""
  kill "$WD_PID" 2>/dev/null
  wait "$WD_PID" 2>/dev/null
  WD_PID=""
  log "step $name rc=$RC"
}

RCS=""
FAILED=""
if [ -n "$TOKEN" ]; then export GH_TOKEN="$TOKEN"; fi
export FLEET_GH_AUTH="$GH_AUTH" FLEET_RELEASE="$RELEASE"
step observe "$FLEET" observe --scope "$SCOPE" --tick "$N"; RCS="observe=$RC"
unset GH_TOKEN TOKEN
[ "$RC" = "0" ] || FAILED="observe"
if [ -z "$FAILED" ]; then
  step report "$FLEET" report --scope "$SCOPE" --tick "$N" --dry-run "$DRY"; RCS="$RCS report=$RC"
  [ "$RC" = "0" ] || FAILED="report"
fi
# The core's comparison: a read-only step the kill switch stops with the tick,
# which dry_run and mode don't govern (core §9). Its verdict isn't the tick's.
step compare "$FLEET" core-compare --scope "$SCOPE"; RCS="$RCS compare=$RC"

FINAL=0
[ -n "$FAILED" ] && FINAL=1
"$FLEET" ledger-append exit --scope "$SCOPE" --tick "$N" --dry-run "$DRY" --exit "$FINAL" \
  --detail "$RCS" >> "$LOG" 2>&1
log "tick $N done: $RCS"

# ── with the lock released: the owner's dialog, which can wait 10 minutes ────
# The trap goes first: a signal between the two can't run release twice (and
# remove a lock a newer tick took); a lock it leaves is reclaimed as stale.
trap - EXIT
release
"$FLEET" act ask --show --scope "$SCOPE" --tick "$N" --dry-run "$DRY" < /dev/null >> "$LOG" 2>&1
ASK_RC=$?
RCS="$RCS ask=$ASK_RC"
[ "$ASK_RC" = "0" ] || FAILED="${FAILED:-ask}"
echo "[$(date -u +%FT%TZ)] fleet-reconcile $SCOPE tick $N: $RCS"   # launchd's log: one line per run
if [ -n "$FAILED" ]; then
  alert tick "tick $N failed at $FAILED ($RCS)"
  exit 1
fi
exit 0
