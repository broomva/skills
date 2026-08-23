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

SRCDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Mutate a COPY, never the tracked tree. The first version edited the real file
# and reverted with `git checkout --`, so anything reading the repo while the
# sweep ran -- another agent, a hook, a concurrent test -- saw a mutated
# artifact, and an interrupted run left one behind. A reviewer observed exactly
# that: FREE_ROUNDS=99 live in the tracked file mid-review.
#
# Working on a copy also removes the clean-tree precondition: there is nothing
# left to destroy, so the sweep no longer has to refuse on a dirty tree.
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
cp -R "$SRCDIR/." "$SCRATCH/"
CRDIR="$SCRATCH"
TARGET="$CRDIR/scripts/round-budget.sh"
SUITE="$CRDIR/tests/round-budget.test.sh"
PRISTINE="$SCRATCH/.pristine-round-budget.sh"
cp "$TARGET" "$PRISTINE"

cd "$CRDIR" || { echo "mutation: cannot cd to $CRDIR" >&2; exit 2; }

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
        cp "$PRISTINE" "$TARGET"
        return 0
    fi

    local out rc
    out=$(bash "$SUITE" 2>&1); rc=$?
    cp "$PRISTINE" "$TARGET"

    # The id is matched WITH ITS COLON. An unanchored substring match made an
    # expectation of "T1" satisfiable by "[FAIL] T13" / "T15" / "T19" -- and it
    # silently was: this sweep reported "free-round floor 3->99 -> T1 went red"
    # when the tests that actually reddened were T4 and T13. The bias runs toward
    # FALSE KILLED, which is the direction that hides survivors.
    if echo "$out" | grep -q "\[FAIL\] ${expect}:"; then
        echo "  [KILLED]   $label  ->  $expect went red"
        KILLED=$((KILLED+1))
    else
        echo "  [SURVIVED] $label  ->  $expect still passed (suite exit $rc)"
        SURVIVED=$((SURVIVED+1)); SURVIVORS+=("$label expected $expect")
    fi
}

echo "── per-rule mutations ────────────────────────────────────────"

# The bounds.
# T4, not T1. The unanchored match credited this with killing T1 for three
# commits. T1 is pinned by the defect-streak mutation below, which a reviewer
# independently confirmed does redden it.
mutate "free-round floor 3->99"  "T4" 'FREE_ROUNDS=3'   'FREE_ROUNDS=99'
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
    'if [ "$LG_PENDING" = "1" ]; then' \
    'if [ "$LG_PENDING" = "9" ]; then'
mutate "rule4 stacking allowed" "T10" \
    'if [ "$VERDICT" = "CONTINUE" ] && [ "$LG_PENDING" = "1" ]; then' \
    'if [ "$VERDICT" = "CONTINUE" ] && [ "$LG_PENDING" = "9" ]; then'

# Field-separator sanitising.
mutate "sanitize passes tabs" "T14" \
    "tr '\\t\\n' '  '" \
    "tr '\\n' ' '"

# The fail-open guard. An unreadable ledger returning zero rows reads as
# "no rounds yet", which authorizes -- the one direction this controller
# must never fail in. Mutating the refusal to a success restores that.
# A bare `exit 6` at this indent occurs three times, so the anchor carries the
# comment above it. A non-unique anchor is refused by the guard rather than
# applied to whichever site came first.
mutate "unreadable ledger fails open" "T15" \
    $'ledger exists at $LEDGER but cannot be read." >&2\n            exit 6' \
    $'ledger exists at $LEDGER but cannot be read." >&2\n            exit 0'

# ─── The structures the hoist introduced, each with its own proof ─────────
# The pre-hoist note here said ordering "cannot be expressed as a value
# mutation". The hoist made that false -- ordering IS a value now, and declining
# the proof on an invalidated rationale is how a new shape ships unmutated.
mutate "PASSED reordered above the stops" "T31" \
    'PRECEDENCE="regressed:6 refuted:6 nodefect:6 terminal:6 passed:3' \
    'PRECEDENCE="passed:3 regressed:6 refuted:6 nodefect:6 terminal:6'
mutate "earned admits any VERDICT row" "T37" \
    '[ "$LG_LAST_VERDICT" = "CONTINUE" ] || return 1' \
    '[ "$LG_LAST_VERDICT" != "IMPOSSIBLE" ] || return 1'
mutate "ROUND arity unchecked" "T38" \
    'if (NF != 6) { badrow=1 }' 'if (NF != 99) { badrow=0 }'
mutate "corrupt ledger cannot be reset" "T39" \
    'if ! ( load_ledger ) >/dev/null 2>&1; then' 'if false; then'
mutate "archive clobbers a prior one" "T40" \
    'while [ -e "$ARCHIVE" ]; do' 'while false; do' 


# The stale-verdict rule: a spent verdict must not re-authorize.
mutate "stale verdict re-authorizes" "T13" \
    '[ "$LG_LAST_TYPE" != "VERDICT" ] || return 1' \
    '[ "$LG_LAST_TYPE" = "NEVERMATCHES" ] || return 1'

# ─── The absorbing stops and the fail-closed guards ───────────────────────
# Each of these was escapable or silent in the first version, so each gets its
# own proof that the test pinning it can actually fail.
mutate "defect streak 2->99"        "T1"  '[ "$LG_MAXNOD" -ge 2 ] || return 1' '[ "$LG_MAXNOD" -ge 99 ] || return 1'
mutate "refuted no longer absorbing" "T21" '[ "$LG_MAXREF" -ge 2 ] || return 1' '[ "$LG_MAXREF" -ge 99 ] || return 1'
mutate "terminal verdict ignored"    "T19" '[ -n "$LG_TERMINAL" ] || return 1' '[ -z "$LG_TERMINAL" ] || return 1'
mutate "regression check disabled"   "T5"  '[ "$LG_REGRESSED" != "0" ] || return 1' '[ "$LG_REGRESSED" = "IMPOSSIBLE" ] || return 1'
mutate "bad score fails open"        "T23" '[ "$badscore" != "0" ] || [ "$badrow" != "0" ] || [ -n "$badverdict" ]' '[ "$badscore" = "IMPOSSIBLE" ]'
mutate "structural directive optional" "T24" 'if [ "$VERDICT" = "STRUCTURAL" ] && [ -z "$(sanitize "$DIRECTIVE")" ]; then' 'if [ "$VERDICT" = "NEVER" ] && [ -z "$(sanitize "$DIRECTIVE")" ]; then'
# Both arms now live in prediction_is_valid(), which is called from the recorder
# AND from budget. One definition, so one mutation each.
mutate "prediction length arm dead"   "T27" '[ "${#pred}" -ge 12 ] || return 1' '[ "${#pred}" -ge 0 ] || return 1'
mutate "prediction location arm dead" "T25" \
    "printf '%s' \"\$pred\" | grep -qE '[A-Za-z0-9_-]+\\.[A-Za-z]+|/|:[0-9]+'" \
    "printf '%s' \"\$pred\" | grep -qE ''" 
mutate "ledger seam ungated"           "T26" 'if [ "${ROUND_BUDGET_TEST_LEDGER:-0}" != "1" ]; then' 'if [ "${ROUND_BUDGET_TEST_LEDGER:-0}" = "IMPOSSIBLE" ]; then'

mutate "row arity unchecked" "T28" 'if (NF != 4) { badrow=1 }' 'if (NF != 99) { badrow=0 }'

mutate "read-time prediction check off" "T29" 'if ! prediction_is_valid "$vpred"; then' 'if false; then'
# NOTE: the recorder's corrupt-ledger guard has no separate mutation any more.
# It is the SAME check as "bad score fails open" now that every command passes
# through load_ledger -- one site, one proof. That single mutation reddens T23
# and T30 together, which is the hoist working rather than coverage lost.

mutate "blank predictions skipped again" "T33" 'vpred=${row#P:}' 'vpred=${row#P:}; [ -n "$vpred" ] || continue'

# $'...' so the newline is a REAL newline: a plain single-quoted "\n" is a
# literal backslash-n and matches nothing, which the accounting then reports
# as an ANCHOR ERROR rather than letting it pass silently.
mutate "record-verdict may pass a terminal" "T35" \
    $'record-verdict)\n    with_lock\n    load_ledger\n    refuse_past_terminal' \
    $'record-verdict)\n    with_lock\n    load_ledger'

# ─── Rules that must hold against the STORED ledger, not only at write ────
mutate "rule2 not enforced at read" "T36" \
    'if (pending==1 && $6=="-") badhistory="a round follows a CONTINUE without settling its prediction"' \
    'if (0) badhistory="x"'
mutate "rule4 not enforced at read" "T36" \
    'if (pending==1) badhistory="two CONTINUE verdicts stack with no round between them"' \
    'if (0) badhistory="x"'
mutate "reset ungated (laundering)" "T34" \
    'if [ -z "$LG_TERMINAL" ] && { [ "$LG_N" = "0" ] || [ "$LG_SCORE" -lt "$PASS_SCORE" ]; }; then' \
    'if false; then'

echo ""
echo "── mutation: $KILLED killed, $SURVIVED survived ──"
if [ "$SURVIVED" -gt 0 ]; then
    printf '  survivor: %s\n' "${SURVIVORS[@]}"
    exit 1
fi
exit 0
