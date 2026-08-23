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

    if ! python3 - "$TARGET" "$old" "$new" <<'PY'

import sys
p,old,new=sys.argv[1],sys.argv[2],sys.argv[3]
s=open(p).read()
n=s.count(old)
if n!=1:
    print(f"ANCHOR ERROR: matched {n} times, need exactly 1: {old!r}",file=sys.stderr)
    sys.exit(1)
open(p,'w').write(s.replace(old,new))
PY
    then
        # A stale anchor used to `return 1` here, which counted as NEITHER killed
        # nor survived -- the mutation silently left the accounting, and the
        # summary still read "0 survived". An unapplied mutation is a broken
        # proof, not an absent one.
        echo "  [ERROR]    $label  ->  anchor did not apply; mutation NOT run"
        SURVIVED=$((SURVIVED+1)); SURVIVORS+=("$label ANCHOR ERROR (mutation never applied)")
        $GIT checkout -- "$TARGET"
        return 0
    fi

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

# The anti-vacuity rules. Each is mutated so the guard's CONDITION goes dead
# while the surrounding control flow stays intact.
# rule 1 (a CONTINUE must carry a prediction) has no mutation of its own: the
# empty case is enforced by the SAME length arm as T27, and "prediction length
# arm dead" already kills T8a/T8b along with T27. A separate mutation here would
# have to target a branch that no longer exists, which is why the redundant `-z`
# arm was removed rather than kept for the sake of a proof.
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

# The fail-open guard. An unreadable ledger returning zero rows reads as
# "no rounds yet", which authorizes -- the one direction this controller
# must never fail in. Mutating the refusal to a success restores that.
mutate "unreadable ledger fails open" "T15" '            return 1' '            return 0'

# The stale-verdict rule: a spent verdict must not re-authorize.
mutate "stale verdict re-authorizes" "T13" \
    'if [ "$(field "$LAST_ANY" 1)" != "VERDICT" ]; then' \
    'if [ "$(field "$LAST_ANY" 1)" = "NEVERMATCHES" ]; then'

# ─── The absorbing stops and the fail-closed guards ───────────────────────
# Each of these was escapable or silent in the first version, so each gets its
# own proof that the test pinning it can actually fail.
mutate "defect streak 2->99"        "T1"  'if [ "$MAXNOD" -ge 2 ]; then' 'if [ "$MAXNOD" -ge 99 ]; then'
mutate "refuted no longer absorbing" "T21" 'if [ "$MAXREF" -ge 2 ]; then' 'if [ "$MAXREF" -ge 99 ]; then'
mutate "terminal verdict ignored"    "T19" 'if [ -n "$TERMINAL" ]; then
        if [ "$TERMINAL" = "STRUCTURAL" ]; then' 'if [ -z "$TERMINAL" ] && [ -n "$TERMINAL" ]; then
        if [ "$TERMINAL" = "STRUCTURAL" ]; then'
mutate "regression check disabled"   "T5"  'if [ "$REGRESSED" != "0" ]; then' 'if [ "$REGRESSED" = "IMPOSSIBLE" ]; then'
mutate "bad score fails open"        "T23" '[ "$BADSCORE" != "0" ] || [ "$BADROW" != "0" ] || [ -n "$BADVERDICT" ]' '[ "$BADSCORE" = "IMPOSSIBLE" ]'
mutate "structural directive optional" "T24" 'if [ "$VERDICT" = "STRUCTURAL" ] && [ -z "$(sanitize "$DIRECTIVE")" ]; then' 'if [ "$VERDICT" = "NEVER" ] && [ -z "$(sanitize "$DIRECTIVE")" ]; then'
mutate "prediction length arm dead"   "T27" 'if [ "${#CLEAN_PRED}" -lt 12 ]' 'if [ "${#CLEAN_PRED}" -lt 0 ]'
mutate "prediction location arm dead" "T25" \
    "! printf '%s' \"\$CLEAN_PRED\" | grep -qE '[A-Za-z0-9_-]+\\.[A-Za-z]+|/|:[0-9]+'" \
    "! printf '%s' \"\$CLEAN_PRED\" | grep -qE ''" 
mutate "ledger seam ungated"           "T26" 'if [ "${ROUND_BUDGET_TEST_LEDGER:-0}" != "1" ]; then' 'if [ "${ROUND_BUDGET_TEST_LEDGER:-0}" = "IMPOSSIBLE" ]; then'

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
