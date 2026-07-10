#!/bin/bash
# tick.sh — the portable scheduler of a governed autonomy loop.
#
# A generalized, adapter-parameterized descendant of the proven ticket-dispatch
# durable-tick (BRO-1740 + BRO-1833). A periodic poker — launchd (macOS), a
# systemd --user timer (Linux), cron, or a k8s CronJob — fires this as a CHEAP
# GATE: it only really fires when now >= next-fire-at, then self-reschedules.
# The DECISIONS live in the runner-prompt the governor session interprets; this
# script only schedules, locks, logs, and spawns. It never touches the tracker
# (that is the governor's job, via its MCP) — the Kanon seam holds here too.
#
# INSTANCE PARAMETERS (env, all optional — Mac-style defaults resolve identically
# on the reference host; a runtime unit overrides via Environment=):
#   GAL_STATE_DIR        durable state dir (default ~/.config/broomva/<loop>)
#   GAL_REPO             dir holding the runner-prompt + scripts (tracker-visible root)
#   GAL_WORKDIR          cwd for git/worktree work (may differ from REPO — nested repo)
#   GAL_CLAUDE_BIN       agent binary (set to `echo` for a spawnless smoke)
#   GAL_RUNNER_PROMPT    path to the controller prompt the governor executes
#   GAL_CONFIG_TEMPLATE  seed template for the first-run config.env
#   GAL_DENYLIST_FILE    tracker denylist adapter (JSON: governor_dry_denylist[])
#   GAL_PARTITION_TAG    partition discriminator (e.g. "life") — seed guard + label
#   GAL_CHILD            recursion guard (set on every spawned child; do not set)
#
# Runtime overrides (manual / validation runs):
#   DRY_RUN=1   governor reports; tracker write tools blocked via --disallowedTools
#   FORCE=1     bypass the fire gate + quiet hours; do NOT persist the schedule
#               (validation runs leave the durable schedule alone). Does NOT
#               bypass the kill switch.
set -uo pipefail

# ── recursion guard (runaway-spawn shield) ───────────────────────────────────
# The governor and every arc it spawns inherit GAL_CHILD=1 (env inheritance is
# transitive). Any child that re-enters the tick exits here.
if [ -n "${GAL_CHILD:-}" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── OS portability shim (BSD/macOS vs GNU/Linux) ─────────────────────────────
# Detect the coreutils dialect ONCE by behaviour (a GNU-only stat flag), not
# uname, then route the calls that differ. Default BSD. bash 3.2-safe.
if stat -c %Y / >/dev/null 2>&1; then
  _OS=gnu
else
  _OS=bsd
fi
file_mtime() { if [ "$_OS" = gnu ]; then stat -c %Y "$1" 2>/dev/null; else stat -f %m "$1" 2>/dev/null; fi; }
now_epoch() { date +%s; }
epoch_to_local() { if [ "$_OS" = gnu ]; then date -d "@$1" "$2"; else date -r "$1" "$2"; fi; }

# ── instance paths (env overrides beat every default) ────────────────────────
STATE_DIR="${GAL_STATE_DIR:-$HOME/.config/broomva/governed-autonomy-loop}"
REPO_DIR="${GAL_REPO:-$SCRIPT_DIR/..}"
WORKDIR="${GAL_WORKDIR:-$REPO_DIR}"
CLAUDE_BIN="${GAL_CLAUDE_BIN:-$HOME/.local/bin/claude}"
RUNNER_PROMPT="${GAL_RUNNER_PROMPT:-$REPO_DIR/templates/runner-prompt.template.md}"
CONFIG_TEMPLATE="${GAL_CONFIG_TEMPLATE:-$REPO_DIR/templates/config.env.template}"
DENYLIST_FILE="${GAL_DENYLIST_FILE:-$REPO_DIR/templates/denylist.linear.json}"
PARTITION_TAG="${GAL_PARTITION_TAG:-}"

CONFIG="$STATE_DIR/config.env"
NEXT_FILE="$STATE_DIR/next-fire-at"
LOG="$STATE_DIR/tick.log"
JSONL="$STATE_DIR/loop-log.jsonl"
LOCK="$STATE_DIR/.tick.lock"
COUNTER="$STATE_DIR/run-counter"
NOTICE="$STATE_DIR/.disabled-notice"
INNER_NEXT_FILE="$STATE_DIR/next-inner-fire-at"

mkdir -p "$STATE_DIR/arcs"
log() { echo "[$(date -u +%FT%TZ)] $*" >> "$LOG"; }

# num_or VALUE DEFAULT — echo VALUE if a plain non-negative integer, else DEFAULT.
num_or() { case "$1" in (*[!0-9]*|"") echo "$2" ;; (*) echo $((10#$1)) ;; esac; }

# count_in_flight — dogfood the extracted deterministic reducer (loop_state.py).
# ONLY a cheap gate on whether an inner resume tick is worth a governor; the
# governor recomputes in-flight authoritatively. Prints an integer (0 on error).
count_in_flight() {
  python3 "$SCRIPT_DIR/loop_state.py" in-flight "$JSONL" 2>/dev/null || echo 0
}

# ── seed + load config (fail-CLOSED) ─────────────────────────────────────────
if [ ! -f "$CONFIG" ]; then
  if [ -f "$STATE_DIR/.seeded" ]; then
    if [ ! -f "$NOTICE" ]; then
      log "config.env missing but seeded before — failing CLOSED (restore config.env to resume)"
      touch "$NOTICE" 2>/dev/null
    fi
    exit 0
  fi
  # Partition-seed guard: a partitioned STATE_DIR (basename ends -<tag>) must be
  # seeded ONLY from a template carrying <tag> — else it inherits the wrong LABEL
  # and two governors collide on the same queue. Fails CLOSED on mismatch.
  if [ -n "$PARTITION_TAG" ]; then
    case "${STATE_DIR%/}" in
      (*-"$PARTITION_TAG")
        case "$CONFIG_TEMPLATE" in
          (*"$PARTITION_TAG"*) : ;;
          (*)
            if [ ! -f "$NOTICE" ]; then
              log "REFUSING to seed a -$PARTITION_TAG STATE_DIR from a non-$PARTITION_TAG template ($CONFIG_TEMPLATE) — set GAL_CONFIG_TEMPLATE. Failing CLOSED."
              touch "$NOTICE" 2>/dev/null
            fi
            exit 0 ;;
        esac ;;
    esac
  fi
  if [ -f "$CONFIG_TEMPLATE" ] && cp "$CONFIG_TEMPLATE" "$CONFIG" 2>/dev/null; then
    touch "$STATE_DIR/.seeded"
    log "seeded config.env from $CONFIG_TEMPLATE (DRY_RUN=1 posture)"
  else
    if [ ! -f "$NOTICE" ]; then
      log "cannot seed config.env (template missing or state dir unwritable) — failing CLOSED"
      touch "$NOTICE" 2>/dev/null
    fi
    exit 0
  fi
else
  [ -f "$STATE_DIR/.seeded" ] || touch "$STATE_DIR/.seeded"
fi

# Env overrides beat the file — capture BEFORE sourcing, re-apply after.
ENV_DRY_RUN="${DRY_RUN:-}"
ENV_FORCE="${FORCE:-}"
SAVED_STATE_DIR="$STATE_DIR"

if [ -f "$CONFIG" ]; then
  # shellcheck disable=SC1090,SC1091
  if ! . "$CONFIG"; then
    log "config.env failed to source — failing CLOSED (no fire)"
    exit 0
  fi
fi

# Re-derive every state path from the pre-source STATE_DIR: a stray config line
# reassigning LOCK/NEXT_FILE/etc. must never redirect the rm -rf lock path.
STATE_DIR="$SAVED_STATE_DIR"
CONFIG="$STATE_DIR/config.env"
NEXT_FILE="$STATE_DIR/next-fire-at"
LOG="$STATE_DIR/tick.log"
JSONL="$STATE_DIR/loop-log.jsonl"
LOCK="$STATE_DIR/.tick.lock"
COUNTER="$STATE_DIR/run-counter"
NOTICE="$STATE_DIR/.disabled-notice"
INNER_NEXT_FILE="$STATE_DIR/next-inner-fire-at"

# ── kill switch (strict file parse, before anything can fire) ────────────────
KILL_RAW=""
if [ -f "$CONFIG" ]; then
  KILL_RAW=$(grep -E '^DISPATCH_ENABLED=' "$CONFIG" | tail -1 | cut -d= -f2- | tr -d '[:space:]')
fi
if [ "$KILL_RAW" != "1" ]; then
  if [ ! -f "$NOTICE" ]; then
    log "loop DISABLED (DISPATCH_ENABLED='${KILL_RAW:-<unset>}') — no fires until set to exactly 1"
    touch "$NOTICE"
  fi
  exit 0
fi
rm -f "$NOTICE"

# ── defaults + sanitization (config may override) ────────────────────────────
DRY_RUN="${DRY_RUN:-1}"
WIP_CAP=$(num_or "${WIP_CAP:-}" 3)
LABEL="${LABEL:-agent-ok}"
STALL_HOURS=$(num_or "${STALL_HOURS:-}" 4)
RECONCILE_QUIET_HOURS=$(num_or "${RECONCILE_QUIET_HOURS:-}" 24)
FIRE_INTERVAL_HOURS=$(num_or "${FIRE_INTERVAL_HOURS:-}" 2)
ACTIVE_START=$(num_or "${ACTIVE_START:-}" 7)
ACTIVE_END=$(num_or "${ACTIVE_END:-}" 23)
MAX_DISPATCH_PER_TICK=$(num_or "${MAX_DISPATCH_PER_TICK:-}" 1)
LABEL_MAX_PER_TICK=$(num_or "${LABEL_MAX_PER_TICK:-}" 5)
RECONCILE_MAX=$(num_or "${RECONCILE_MAX:-}" 40)
SWEEP_IDLE_DAYS=$(num_or "${SWEEP_IDLE_DAYS:-}" 7)
RUNNER_TIMEOUT_MIN=$(num_or "${RUNNER_TIMEOUT_MIN:-}" 45)
[ "$RUNNER_TIMEOUT_MIN" -lt 1 ] && RUNNER_TIMEOUT_MIN=1
RESUME_ENABLED="${RESUME_ENABLED:-0}"
[ "$RESUME_ENABLED" != "1" ] && RESUME_ENABLED=0
INNER_INTERVAL_MIN=$(num_or "${INNER_INTERVAL_MIN:-}" 10)
[ "$INNER_INTERVAL_MIN" -lt 1 ] && INNER_INTERVAL_MIN=1
INNER_TIMEOUT_MIN=$(num_or "${INNER_TIMEOUT_MIN:-}" 15)
[ "$INNER_TIMEOUT_MIN" -lt 1 ] && INNER_TIMEOUT_MIN=1
RESEED_TURN_CAP=$(num_or "${RESEED_TURN_CAP:-}" 8)
[ "$RESEED_TURN_CAP" -lt 1 ] && RESEED_TURN_CAP=1
RESEED_MAX_GENERATIONS=$(num_or "${RESEED_MAX_GENERATIONS:-}" 3)
[ "$RESEED_MAX_GENERATIONS" -lt 0 ] && RESEED_MAX_GENERATIONS=0
[ -n "$ENV_DRY_RUN" ] && DRY_RUN="$ENV_DRY_RUN"
FORCE="${ENV_FORCE:-0}"
# DRY_RUN fails toward DRY: live requires exactly 0.
[ "$DRY_RUN" != "0" ] && DRY_RUN=1

NOW=$(now_epoch)

# ── quiet hours: defer to next active-window start ───────────────────────────
HOUR=$((10#$(date +%H)))
if [ "$FORCE" != "1" ] && { [ "$HOUR" -lt "$ACTIVE_START" ] || [ "$HOUR" -ge "$ACTIVE_END" ]; }; then
  NEXT_ACTIVE=$(python3 -c "import datetime as d
n = d.datetime.now()
t = n.replace(hour=$ACTIVE_START, minute=0, second=0, microsecond=0)
if n >= t:
    t += d.timedelta(days=1)
print(int(t.timestamp()))")
  case "$NEXT_ACTIVE" in (*[!0-9]*|"") NEXT_ACTIVE=$((NOW + 3600)) ;; esac
  echo "$NEXT_ACTIVE" > "$NEXT_FILE"
  log "quiet hours (hour=$HOUR, active ${ACTIVE_START}-${ACTIVE_END}) — deferred to $(epoch_to_local "$NEXT_ACTIVE" +%FT%T%z)"
  exit 0
fi

# ── mode decision: OUTER (dispatch/reconcile) vs INNER (resume) ──────────────
NEXT=$(cat "$NEXT_FILE" 2>/dev/null || echo 0)
case "$NEXT" in (*[!0-9]*|"") NEXT=0 ;; esac
TICK_MODE=outer
if [ "$FORCE" != "1" ] && [ "$NOW" -lt "$NEXT" ]; then
  [ "$RESUME_ENABLED" = "1" ] || exit 0
  INEXT=$(cat "$INNER_NEXT_FILE" 2>/dev/null || echo 0)
  case "$INEXT" in (*[!0-9]*|"") INEXT=0 ;; esac
  [ "$NOW" -ge "$INEXT" ] || exit 0
  IN_FLIGHT=$(count_in_flight)
  case "$IN_FLIGHT" in (*[!0-9]*|"") IN_FLIGHT=0 ;; esac
  if [ "$IN_FLIGHT" -eq 0 ]; then
    echo $((NOW + INNER_INTERVAL_MIN * 60)) > "$INNER_NEXT_FILE"
    exit 0
  fi
  TICK_MODE=inner
fi

# ── overlap lock: one governor at a time ─────────────────────────────────────
# Held for the ENTIRE session. $LOCK/pid = this tick; $LOCK/runner-pid = the
# governor. Stale only when BOTH pids are dead; atomic mv reclaim (one winner).
if ! mkdir "$LOCK" 2>/dev/null; then
  TICK_PID=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  RPID=$(cat "$LOCK/runner-pid" 2>/dev/null || echo "")
  if [ -n "$TICK_PID" ] && kill -0 "$TICK_PID" 2>/dev/null; then
    log "tick skipped — fire already in progress (tick pid $TICK_PID)"; exit 0
  fi
  if [ -n "$RPID" ] && kill -0 "$RPID" 2>/dev/null; then
    log "tick skipped — governor still running (runner pid $RPID)"; exit 0
  fi
  LOCK_MTIME=$(file_mtime "$LOCK" 2>/dev/null); [ -n "$LOCK_MTIME" ] || LOCK_MTIME="$NOW"
  if [ $((NOW - LOCK_MTIME)) -lt 120 ]; then exit 0; fi
  if ! mv "$LOCK" "$LOCK.stale.$$" 2>/dev/null; then exit 0; fi
  rm -rf "$LOCK.stale.$$"
  mkdir "$LOCK" 2>/dev/null || exit 0
  log "reclaimed stale lock (holders tick=${TICK_PID:-?} runner=${RPID:-?} both dead)"
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

# ── self-reschedule FIRST (crash-robust) ─────────────────────────────────────
if [ "$TICK_MODE" = "inner" ]; then
  NEW_NEXT=$((NOW + INNER_INTERVAL_MIN * 60))
  [ "$FORCE" = "1" ] || echo "$NEW_NEXT" > "$INNER_NEXT_FILE"
else
  NEW_NEXT=$((NOW + FIRE_INTERVAL_HOURS * 3600))
  [ "$FORCE" = "1" ] || echo "$NEW_NEXT" > "$NEXT_FILE"
fi

# ── run counter + tick record ────────────────────────────────────────────────
N=$(cat "$COUNTER" 2>/dev/null || echo 0)
case "$N" in (*[!0-9]*|"") N=0 ;; esac
N=$((N + 1))
echo "$N" > "$COUNTER"

DRYBOOL=false
[ "$DRY_RUN" = "1" ] && DRYBOOL=true
printf '{"ts":"%s","run":%s,"action":"tick_fire","dry_run":%s,"mode":"%s","next_fire_at":%s,"forced":%s}\n' \
  "$(date -u +%FT%TZ)" "$N" "$DRYBOOL" "$TICK_MODE" "$NEW_NEXT" "$([ "$FORCE" = "1" ] && echo true || echo false)" >> "$JSONL"
log "FIRING run $N mode=$TICK_MODE (dry_run=$DRY_RUN force=$FORCE); next $TICK_MODE at $(epoch_to_local "$NEW_NEXT" +%FT%T%z)"

# ── mechanical dry-run enforcement (denylist from the tracker adapter) ───────
# DRY_RUN=1 blocks every tracker WRITE tool at the harness level, from the
# adapter's governor_dry_denylist[] — so "dry never writes" is mechanical.
DRY_FLAGS=()
if [ "$DRY_RUN" = "1" ] && [ -f "$DENYLIST_FILE" ]; then
  DRY_FLAGS=(--disallowedTools)
  while IFS= read -r _tool; do
    [ -n "$_tool" ] && DRY_FLAGS=("${DRY_FLAGS[@]}" "$_tool")
  done <<EOF
$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(chr(10).join(d.get('governor_dry_denylist',[])))" "$DENYLIST_FILE" 2>/dev/null)
EOF
  # If the adapter yielded no tools, drop the bare --disallowedTools flag.
  [ "${#DRY_FLAGS[@]}" -le 1 ] && DRY_FLAGS=()
fi

# ── spawn the governor session ───────────────────────────────────────────────
cd "$REPO_DIR" || { log "ERR: cannot cd $REPO_DIR"; exit 1; }
PROMPT="Read $RUNNER_PROMPT and execute it to completion. Runtime parameters: RUN_N=$N; TICK_MODE=$TICK_MODE; DRY_RUN=$DRY_RUN; WIP_CAP=$WIP_CAP; LABEL=$LABEL; STALL_HOURS=$STALL_HOURS; RECONCILE_QUIET_HOURS=$RECONCILE_QUIET_HOURS; MAX_DISPATCH_PER_TICK=$MAX_DISPATCH_PER_TICK; LABEL_MAX_PER_TICK=$LABEL_MAX_PER_TICK; RECONCILE_MAX=$RECONCILE_MAX; SWEEP_IDLE_DAYS=$SWEEP_IDLE_DAYS; RESEED_TURN_CAP=$RESEED_TURN_CAP; RESEED_MAX_GENERATIONS=$RESEED_MAX_GENERATIONS; STATE_DIR=$STATE_DIR; REPO_DIR=$REPO_DIR; WORKDIR=$WORKDIR; CLAUDE_BIN=$CLAUDE_BIN; DENYLIST_FILE=$DENYLIST_FILE; PARTITION_TAG=$PARTITION_TAG. The runner-prompt's intro defines what each TICK_MODE runs."

GAL_CHILD=1 "$CLAUDE_BIN" -p "$PROMPT" --dangerously-skip-permissions \
  ${DRY_FLAGS[@]+"${DRY_FLAGS[@]}"} >> "$LOG" 2>&1 &
RUNNER_PID=$!
echo "$RUNNER_PID" > "$LOCK/runner-pid"
# The governor's lifetime is bound to this tick: TERM the tick -> the EXIT trap
# takes the governor down WITH the lock (a released lock can never coexist with a
# live orphaned governor). Detached arcs are grandchildren and survive.
trap 'kill "$RUNNER_PID" 2>/dev/null; rm -rf "$LOCK"' EXIT

# ── wall-clock watchdog (TERM, then KILL 30s later) ──────────────────────────
# The subshell's fds go to $LOG (NOT the caller's stdout) so a captured-pipe
# parent — a test harness, a `claude -p` capture — never blocks on the watchdog's
# sleep holding the pipe open. The sleep is a reap-able child: on TERM (the
# EXIT-trap kill below) the trap reaps it, so no 45-min orphan is left behind.
EFFECTIVE_TIMEOUT_MIN=$RUNNER_TIMEOUT_MIN
[ "$TICK_MODE" = "inner" ] && EFFECTIVE_TIMEOUT_MIN=$INNER_TIMEOUT_MIN
(
  # Arm the trap BEFORE forking the sleep so a TERM in the fork/trap window can
  # never orphan it: on TERM, kill all of this subshell's background jobs (the
  # sleep) and exit. This closes the trap-install race the parent-side belt can't.
  trap 'kill $(jobs -p) 2>/dev/null; exit 0' TERM
  sleep $((EFFECTIVE_TIMEOUT_MIN * 60)) &
  wait
  if kill -0 "$RUNNER_PID" 2>/dev/null; then
    kill "$RUNNER_PID" 2>/dev/null
    echo "[$(date -u +%FT%TZ)] runner run $N ($TICK_MODE) exceeded ${EFFECTIVE_TIMEOUT_MIN}m — sent TERM" >> "$LOG"
    sleep 30
    if kill -0 "$RUNNER_PID" 2>/dev/null; then
      kill -9 "$RUNNER_PID" 2>/dev/null
      echo "[$(date -u +%FT%TZ)] runner run $N ($TICK_MODE) ignored TERM — sent KILL" >> "$LOG"
    fi
  fi
) >> "$LOG" 2>&1 &
WATCHDOG=$!

wait "$RUNNER_PID"
RC=$?
# Reap the watchdog AND its sleep child. Belt (capture the child BEFORE killing —
# after kill the subshell is gone and the sleep is reparented, so pgrep -P can no
# longer find it) plus the in-subshell TERM trap (suspenders); together they close
# the trap-install race that would otherwise orphan a full-timeout sleep.
WCHILD=$(pgrep -P "$WATCHDOG" 2>/dev/null || true)
kill "$WATCHDOG" 2>/dev/null
[ -n "$WCHILD" ] && kill $WCHILD 2>/dev/null
wait "$WATCHDOG" 2>/dev/null

printf '{"ts":"%s","run":%s,"action":"runner_exit","dry_run":%s,"exit_code":%s}\n' \
  "$(date -u +%FT%TZ)" "$N" "$DRYBOOL" "$RC" >> "$JSONL"
log "run $N runner exited rc=$RC"
