#!/usr/bin/env bash
#
# shellcheck disable=SC2016
#   The mutation anchors in this file are LITERAL source text and must stay
#   single-quoted. Expanding "$STREAK" would search for its VALUE, match
#   nothing, silently no-op every mutation, and report a false SURVIVED for
#   each -- pointing at a real finding that is not there. SC2016 is exactly
#   backwards for this file, so it is disabled file-wide rather than per line.
# tests/round-budget.mutation.sh — a mutation proof PER RULE, not per file.
#
# `mutation-proof.sh --strategy stub` neuters the whole script and proves the
# suite notices it exists. That is a weaker claim than it looks: 4 of 17 checks
# still passed against a fully stubbed target. This sweep mutates ONE VALUE at a
# time and asserts that a NAMED test flips pass -> FAIL, so every bound and every
# anti-vacuity rule carries its own evidence.
#
# Values, not branches. A mutated branch can make the script CRASH, and red-
# because-it-crashed reads identically to red-because-behaviour-changed while
# proving nothing about the check.
#
# Each mutation asserts its anchor matches EXACTLY ONCE before applying. A stale
# anchor silently no-ops and reports a false SURVIVED, which points at a real
# finding that is not there.
#
# Run:  bash tests/round-budget.mutation.sh

set -uo pipefail
export LC_ALL=C

CRDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$CRDIR/scripts/round-budget.sh"
SUITE="$CRDIR/tests/round-budget.test.sh"

# fsmonitor is forced off: a dead daemon makes `git status` report a CLEAN tree
# while files are modified, which would void this guard exactly when it matters.
GIT="git -c core.fsmonitor=false"

cd "$CRDIR" || { echo "mutation: cannot cd to $CRDIR" >&2; exit 2; }
if [ -n "$($GIT status --porcelain -- "$TARGET")" ]; then
    echo "mutation: REFUSING to run — $TARGET has uncommitted changes." >&2
    echo "  This sweep reverts to HEAD after every mutation and would destroy them." >&2
    exit 2
fi

BASE_OUT=$(bash "$SUITE" 2>&1); BASE_RC=$?
if [ "$BASE_RC" != "0" ]; then
    echo "mutation: REFUSING to run — the baseline suite is already red (exit $BASE_RC)." >&2
    echo "  Every mutant would report KILLED for the wrong reason." >&2
    exit 2
fi
echo "baseline: green ($(echo "$BASE_OUT" | grep -c '\[pass\]') assertions)"
echo ""

KILLED=0; SURVIVED=0; declare -a SURVIVORS=()

# mutate <label> <expected-test-id> <python-old> <python-new>
mutate() {
    local label="$1" expect="$2" old="$3" new="$4"

    python3 - "$TARGET" "$old" "$new" <<'PY' || return 1
import sys
p,old,new=sys.argv[1],sys.argv[2],sys.argv[3]
s=open(p).read()
n=s.count(old)
if n!=1:
    print(f"ANCHOR ERROR: matched {n} times, need exactly 1: {old!r}",file=sys.stderr)
    sys.exit(1)
open(p,'w').write(s.replace(old,new))
PY

    local out rc
    out=$(bash "$SUITE" 2>&1); rc=$?
    $GIT checkout -- "$TARGET"

    if echo "$out" | grep -q "\[FAIL\] $expect"; then
        echo "  [KILLED]   $label  ->  $expect went red"
        KILLED=$((KILLED+1))
    else
        echo "  [SURVIVED] $label  ->  $expect still passed (suite exit $rc)"
        SURVIVED=$((SURVIVED+1)); SURVIVORS+=("$label expected $expect")
    fi
}

echo "── per-rule mutations ────────────────────────────────────────"

# The bounds.
mutate "free-round floor 3->99"  "T1" 'FREE_ROUNDS=3'   'FREE_ROUNDS=99'
mutate "human ceiling 8->999"    "T7" 'HUMAN_CEILING=8' 'HUMAN_CEILING=999'
mutate "pass score 7->99"        "T12" 'PASS_SCORE=7'   'PASS_SCORE=99'

# The stop conditions.
mutate "two-refuted 2->99"       "T6" '[ "$STREAK" -ge 2 ]' '[ "$STREAK" -ge 99 ]'
mutate "regression never fires"  "T5" '[ "$LAST_SCORE" -lt "$PREV_SCORE" ]' '[ "$LAST_SCORE" -lt 0 ]'

# The anti-vacuity rules. Each is mutated so the guard's CONDITION goes dead
# while the surrounding control flow stays intact.
mutate "rule1 prediction optional" "T8a" \
    'if [ "$VERDICT" = "CONTINUE" ] && [ -z "$(sanitize "$PREDICTION")" ]; then' \
    'if [ "$VERDICT" = "XCONTINUE" ] && [ -z "$(sanitize "$PREDICTION")" ]; then'
mutate "rule2 settles optional" "T9" \
    'if [ "$(pending_continue)" = "1" ]; then' \
    'if [ "$(pending_continue)" = "9" ]; then'
mutate "rule4 stacking allowed" "T10" \
    'if [ "$VERDICT" = "CONTINUE" ] && [ "$(pending_continue)" = "1" ]; then' \
    'if [ "$VERDICT" = "CONTINUE" ] && [ "$(pending_continue)" = "9" ]; then'

# Field-separator sanitising.
mutate "sanitize passes tabs" "T14" \
    "tr '\\t\\n' '  '" \
    "tr '\\n' ' '"

# The stale-verdict rule: a spent verdict must not re-authorize.
mutate "stale verdict re-authorizes" "T13" \
    'if [ "$LAST_TYPE" != "VERDICT" ]; then' \
    'if [ "$LAST_TYPE" = "NEVERMATCHES" ]; then'

echo ""
echo "── mutation: $KILLED killed, $SURVIVED survived ──"
if [ -n "$($GIT status --porcelain -- "$TARGET")" ]; then
    echo "mutation: WARNING — target left dirty; reverting." >&2
    $GIT checkout -- "$TARGET"
fi
if [ "$SURVIVED" -gt 0 ]; then
    printf '  survivor: %s\n' "${SURVIVORS[@]}"
    exit 1
fi
exit 0
