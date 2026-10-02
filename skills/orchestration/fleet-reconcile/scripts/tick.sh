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
# PHASE 1 runs deterministic code only and acts on no session; the owner
# channel's Maestro items each run one model turn. Per tick: kill switch,
# config-check, lock, the tick number, observe, report
# (classes, count check, asks), the core comparison once a day, the owner's
# asks (fleet act ask --show, Maestro work in the Paseo app), and the ledger's
# tick_fire and runner_exit.
# Phase 2 adds `fleet recover` before the coordinator and the coordinator itself.
#
# A tick that fails (a bad config, observe or report failing) raises a Maestro
# item at Needs you in the Paseo app, at most once per 6 h per kind of failure,
# and exits 1 so launchd's last exit shows it. The kill switch set to off is not a failure: exit 0.
#
# Env: FLEET_SCOPE (required); FLEET_CONFIG (default ~/.config/ctx/fleet.json);
# DRY_RUN (any value but 0 forces dry; no value makes a tick live, only the
# config's dry_run 0 with live_accepted does); FLEET_PYTHON. Test seams: FLEET_TICK_TIMEOUT_S,
# FLEET_ALERT_TIMEOUT_S and FLEET_KILL_GRACE_S (the bash fallback's watchdog),
# FLEET_NOTIFY=0, FLEET_MAESTRO_BIN (or FLEET_MAESTRO_BUN and FLEET_MAESTRO_CLI), FLEET_ASK_REPO.
set -uo pipefail

# ── recursion guard ──────────────────────────────────────────────────────────
if [ -n "${FLEET_CHILD:-}" ]; then
  exit 0
fi
export FLEET_CHILD=1
# GitHub is the owner's gh login (owner decision 2026-10-01): a token inherited
# from a shell is dropped before anything runs, the config reads and the alert
# fallback included, so every process this tick starts reads GitHub as it.
unset GH_TOKEN GITHUB_TOKEN

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
else
  file_mtime() { stat -f %m "$1" 2>/dev/null; }
fi

STATE_DIR=$(cfg state_dir)
[ -n "$STATE_DIR" ] || STATE_DIR="$HOME/.local/state/fleet-reconcile/$SCOPE"
mkdir -p "$STATE_DIR" 2>/dev/null && chmod 700 "$STATE_DIR" 2>/dev/null
LOG="$STATE_DIR/tick.log"
NOTICE="$STATE_DIR/.disabled-notice"
LOCK="$STATE_DIR/.tick.lock"
log() { echo "[$(date -u +%FT%TZ)] $*" >> "$LOG" 2>/dev/null; }

# Is the state dir usable? The log, alert stamps, lock and ledger all live here.
# When it can't be written, the alert stamp falls back to TMPDIR so the owner
# hears a failure once per 6 h (not every tick), and an unusable state dir gets
# its own alert kind below rather than being misread as a config-check failure
# (#263 review). The ledger is unwritable either way, so alert() then skips the
# Python path (which needs the ledger) and goes straight to the bash fallback.
STAMP_DIR="$STATE_DIR"
STATE_UNWRITABLE=""
if ( : > "$STATE_DIR/.writable" ) 2>/dev/null; then
  rm -f "$STATE_DIR/.writable" 2>/dev/null
else
  STATE_UNWRITABLE=1
  STAMP_DIR="${TMPDIR:-/tmp}/fleet-reconcile-$SCOPE"
  mkdir -p "$STAMP_DIR" 2>/dev/null
fi

# The owner channel's paths from the config, before any alert can fire (an
# unreadable config leaves the defaults).
for pair in "maestro_cli:FLEET_MAESTRO_CLI" "maestro_bun:FLEET_MAESTRO_BUN" "ask_repo:FLEET_ASK_REPO"; do
  v=$(cfg "${pair%%:*}")
  # shellcheck disable=SC2088  # a literal ~/ from the config, expanded here
  case "$v" in ("~/"*) v="$HOME/${v#\~/}" ;; esac
  [ -n "$v" ] && export "${pair#*:}=$v"
done

# alert KIND MESSAGE: tell the owner in the Paseo app. At most once per 6 h
# per kind. `fleet alert` adopts an open item of the same kind rather than
# raising a second, and the stamp is touched once the item reached the owner
# (ledger.maestro_phase: one still queued is dispatched by the next alert of
# its kind); its own maestro calls are bounded (90 s each, at most four). When
# it can't run at all (the config or Python is what broke), the bash fallback
# raises one; it can't adopt or classify, so any answer from Maestro (made,
# refused, or no clear answer) is stamped, which keeps it to one per 6 h
# whatever Maestro's words. The message is this script's own text, never
# another session's words. When Maestro itself is down, the alert reaches no
# one but this log: that is the channel's one blind spot.
alert() {
  local kind=$1 msg=$2 stamp="$STAMP_DIR/.alert-$1" now last rc
  log "ALERT $kind: $msg"
  now=$(date +%s)
  last=$(file_mtime "$stamp"); case "$last" in (""|*[!0-9]*) last=0 ;; esac
  [ $((now - last)) -ge 21600 ] || return 0
  [ "${FLEET_NOTIFY:-}" = "0" ] && return 0
  if [ -n "$STATE_UNWRITABLE" ]; then
    rc=99  # the Python alert needs the ledger, which lives in the unwritable state dir: use the bash fallback
  else
    "$FLEET" alert --scope "$SCOPE" --kind "$kind" --message "$msg (tick.log: $LOG)" </dev/null >> "$LOG" 2>&1
    rc=$?
  fi
  case "$rc" in
    (0) touch "$stamp" ;;
    (4) log "ALERT $kind NOT delivered: still queued in Maestro (its run cap, or its loop is starting it); the next alert of its kind dispatches it" ;;
    (5) log "ALERT $kind NOT delivered: Maestro failed (above); an item it made is adopted by the next alert of its kind" ;;
    (*)
      maestro_alert "fleet $SCOPE: $kind [fleet-reconcile $SCOPE alert $kind]" "$msg (tick.log: $LOG)"
      rc=$?
      case "$rc" in
        (0) touch "$stamp" ;;
        (1)
          touch "$stamp"
          log "ALERT $kind: the bash fallback's item may or may not exist (Maestro refused or gave no clear answer; above), and it can't look, so the next attempt is in 6 h" ;;
        (*) log "ALERT $kind NOT delivered: nothing reached Maestro; it's in this log only" ;;
      esac ;;
  esac
  return 0
}

# bounded CMD...: run CMD in its own process group under a TERM-then-KILL
# watchdog, as step does: TERM to the group after FLEET_ALERT_TIMEOUT_S (120 s,
# past maestro's own 90 s answer wait), KILL 30 s later, then KILL again for
# children that outlived it, so an alert whose Maestro (or a child of it)
# ignores TERM can't hold the tick. Returns CMD's status (143 or 137 when the
# watchdog ended it).
bounded() {
  local secs=${FLEET_ALERT_TIMEOUT_S:-120} grace=${FLEET_KILL_GRACE_S:-30} pid wd rc
  case "$secs" in (""|*[!0-9]*) secs=120 ;; esac
  case "$grace" in (""|*[!0-9]*) grace=30 ;; esac
  set -m
  "$@" &
  pid=$!
  set +m
  (
    trap 'kill $(jobs -p) 2>/dev/null; exit 0' TERM
    sleep "$secs" &
    wait
    kill -TERM -- "-$pid" 2>/dev/null || exit 0
    sleep "$grace" &
    wait
    kill -KILL -- "-$pid" 2>/dev/null
  ) >/dev/null 2>&1 &
  wd=$!
  wait "$pid"
  rc=$?
  kill -KILL -- "-$pid" 2>/dev/null
  kill "$wd" 2>/dev/null
  wait "$wd" 2>/dev/null
  return "$rc"
}

# maestro_alert TITLE TEXT: the bash fallback, a Maestro work item at Needs you
# in the Paseo app (owner decision 2026-10-01: never a desktop dialog), run in
# the fleet's own scratch repo, bounded. Returns 0 when Maestro made it; 1 when
# Maestro answered otherwise: it refused (exit 1 with the CLI's "maestro: "
# line; a run that couldn't start after it made the item included) or gave no
# clear answer (exit 3; it may have made it); 2 when nothing reached Maestro:
# not listening (exit 2), a CLI that didn't run (bun's own exit 1 has no
# "maestro: " line), no scratch repo, or the watchdog stopped it.
maestro_alert() {
  local title=$1 text=$2 repo="${FLEET_ASK_REPO:-$HOME/.local/state/fleet-reconcile/maestro-asks}"
  if [ ! -d "$repo/.git" ]; then
    mkdir -p "$repo" && git -C "$repo" init -q -b main &&
      git -C "$repo" -c user.name=fleet -c user.email=fleet@localhost commit -q --allow-empty -m "fleet-reconcile ask runs" ||
      return 2
  fi
  local brief="fleet-reconcile alert for scope $SCOPE: $text

Change nothing and run no tools. End your turn at once with exactly two sections: '## Decided' with one bullet, 'nothing', and '## Ask' with two bullets, word for word: the alert above, and 'Approve to dismiss; the tick log has the detail.'"
  if [ -n "${FLEET_MAESTRO_BIN:-}" ]; then
    set -- "$FLEET_MAESTRO_BIN"
  else
    set -- "${FLEET_MAESTRO_BUN:-$HOME/.bun/bin/bun}" "${FLEET_MAESTRO_CLI:-$HOME/broomva/apps/maestro-paseo/bin/maestro.ts}"
  fi
  # To a file, never a command substitution: a Maestro descendant that escaped bounded's process group
  # (setsid/daemonized) would hold the pipe's write end open after bounded returns and hang the tick —
  # which runs outside step()'s watchdog, with the lock held (P20 round 2). The file is the fallback's
  # own (not one in STATE_DIR: the fallback runs when things are broken, and two ticks before the lock
  # can both run it). When mktemp itself fails there is nowhere to capture, so run without capturing and
  # classify by exit code alone; an ambiguous exit 1 is stamped, not retried every tick, the same policy
  # the file branch's exit-1 case uses (#263).
  local out rc cap="" answered=no
  out=$(mktemp "${TMPDIR:-/tmp}/fleet-alert.XXXXXX" 2>/dev/null) || out=""
  if [ -n "$out" ]; then
    bounded "$@" new "$title" --brief "$brief" --repo "$repo" --initiative "fleet-reconcile-$SCOPE" --dispatch --json \
      </dev/null >"$out" 2>&1
    rc=$?
    cap=$(cat "$out" 2>/dev/null)
    rm -f "$out"
    printf '%s\n' "$cap" >> "$LOG" 2>/dev/null
    case "$rc" in
      (0|3) answered=yes ;;
      (1) printf '%s\n' "$cap" | grep -q '^maestro: ' && answered=yes ;;
    esac
  else
    bounded "$@" new "$title" --brief "$brief" --repo "$repo" --initiative "fleet-reconcile-$SCOPE" --dispatch --json \
      </dev/null >/dev/null 2>&1
    rc=$?
    log "ALERT fallback: mktemp failed; classified Maestro exit $rc by code alone (no capture)"
    case "$rc" in (0|3|1) answered=yes ;; esac
  fi
  case "$rc:$answered" in
    (0:yes) return 0 ;;
    (*:yes) return 1 ;;
  esac
  log "ALERT fallback: no answer from Maestro (exit $rc)"
  return 2
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

# A state dir we can't write would make the config-check redirect below fail and
# read as a config-check failure (the wrong reason, raised every tick since its
# stamp can't be written either). Catch it first, with its own kind and a TMPDIR
# stamp, so the owner hears the real reason once per 6 h (#263 review).
if [ -n "$STATE_UNWRITABLE" ]; then
  alert statedir "the state dir for scope $SCOPE can't be written ($STATE_DIR); no tick until it can"
  exit 1
fi

if ! "$FLEET" config-check "$SCOPE" >> "$LOG" 2>&1; then
  alert config "config-check failed for scope $SCOPE; no tick until it passes"
  exit 1
fi

# ── dry run falls toward dry ─────────────────────────────────────────────────
# One source of truth: ask fleet for _dry()'s own answer (it folds in dry_run,
# live_accepted/live_refusal and the DRY_RUN env), so the tick records the same
# dryness every verb acts under, even if the config changed between config-check
# and here (#263 review). Any error reads as dry.
DRY=$("$FLEET" is-dry --scope "$SCOPE" 2>>"$LOG")
case "$DRY" in (0) : ;; (*) DRY=1 ;; esac
# DRY_RUN in the env still forces dry (defence in depth; is-dry already honours it).
case "${DRY_RUN:-}" in (""|0) : ;; (*) DRY=1 ;; esac

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

# ── GitHub: the owner's gh login (owner decision 2026-10-01) ──────────────────
# No fleet token: spec §5.2's non-admin credential is waived, and gh uses the
# owner's keyring login (an inherited token was dropped at the top).
GH_AUTH="keyring (the owner's gh login)"

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
export FLEET_GH_AUTH="$GH_AUTH" FLEET_RELEASE="$RELEASE"
# Intents a dead tick left open are closed first, from what happened (§5.7).
step recover "$FLEET" recover --scope "$SCOPE" --tick "$N"; RCS="recover=$RC"
[ "$RC" = "0" ] || FAILED="recover"
step observe "$FLEET" observe --scope "$SCOPE" --tick "$N"; RCS="$RCS observe=$RC"
[ "$RC" = "0" ] || FAILED="${FAILED:-observe}"
if [ "$RC" = "0" ]; then
  step report "$FLEET" report --scope "$SCOPE" --tick "$N" --dry-run "$DRY"; RCS="$RCS report=$RC"
  [ "$RC" = "0" ] || FAILED="${FAILED:-report}"
fi
# The coordinator, in act mode only, after a clean recover, observe and report;
# it acts only through fleet act. A tool list that fails the posture check
# ends it with exit 4.
MODE=$(cfg mode)
if [ "$MODE" = "act" ] && [ -z "$FAILED" ]; then
  step coordinator "$FLEET" coordinator --scope "$SCOPE" --tick "$N" --dry-run "$DRY"; RCS="$RCS coordinator=$RC"
  [ "$RC" = "0" ] || FAILED="coordinator"
fi
# The core's comparison: a read-only step the kill switch stops with the tick,
# which dry_run and mode don't govern (core §9). Its verdict isn't the tick's.
step compare "$FLEET" core-compare --scope "$SCOPE"; RCS="$RCS compare=$RC"

# The owner channel, inside the lock and the budget: read answers back from
# Maestro and raise new batches there (two ticks can't raise one batch twice).
step ask "$FLEET" act ask --show --scope "$SCOPE" --tick "$N" --dry-run "$DRY"; RCS="$RCS ask=$RC"
[ "$RC" = "0" ] || FAILED="${FAILED:-ask}"

FINAL=0
[ -n "$FAILED" ] && FINAL=1
"$FLEET" ledger-append exit --scope "$SCOPE" --tick "$N" --dry-run "$DRY" --exit "$FINAL" \
  --detail "$RCS" >> "$LOG" 2>&1
log "tick $N done: $RCS"

# The trap goes first: a signal between the two can't run release twice (and
# remove a lock a newer tick took); a lock it leaves is reclaimed as stale.
trap - EXIT
release
echo "[$(date -u +%FT%TZ)] fleet-reconcile $SCOPE tick $N: $RCS"   # launchd's log: one line per run
if [ -n "$FAILED" ]; then
  alert "tick-$FAILED" "tick $N failed at $FAILED ($RCS)"
  exit 1
fi
exit 0
