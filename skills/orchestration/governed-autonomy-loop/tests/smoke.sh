#!/usr/bin/env bash
# smoke.sh — E2E: a DRY, spawnless tick runs end-to-end with zero side effects.
#
# This is the skillify step-9 smoke: the full scheduler path executes, records a
# well-formed tick_fire + runner_exit, injects the tracker denylist, cleans up its
# lock, and touches nothing outside its isolated state dir. Uses GAL_CLAUDE_BIN=echo
# so no real agent (or tracker, or git) is invoked. Exits non-zero on any failure.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$HERE")"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { echo "✗ smoke FAIL: $*" >&2; exit 1; }

STATE="$TMP/state"
GAL_STATE_DIR="$STATE" GAL_CLAUDE_BIN=echo GAL_REPO="$SKILL_DIR" \
  DRY_RUN=1 FORCE=1 bash "$SKILL_DIR/scripts/tick.sh" || fail "tick exited non-zero"

LOG="$STATE/loop-log.jsonl"
[ -f "$LOG" ] || fail "no loop-log.jsonl written"

grep -q '"action":"tick_fire"'   "$LOG" || fail "no tick_fire record"
grep -q '"action":"runner_exit"' "$LOG" || fail "no runner_exit record"
grep -q '"mode":"outer"'         "$LOG" || fail "tick_fire not outer mode"
grep -q '"exit_code":0'          "$LOG" || fail "runner_exit code != 0"
grep -q '"dry_run":true'         "$LOG" || fail "records not marked dry"

# Zero side effects: the FORCE validation run must not persist the schedule, and
# the lock must be cleaned up.
[ ! -e "$STATE/next-fire-at" ]  || fail "FORCE run persisted the schedule"
[ ! -e "$STATE/.tick.lock" ]    || fail "lock not cleaned up"

# The denylist must have reached the (echoed) spawn command.
grep -q 'disallowedTools' "$STATE/tick.log" || fail "tracker denylist not injected in dry mode"

echo "✓ smoke PASS — DRY tick ran end-to-end, well-formed records, zero side effects."
