#!/usr/bin/env bash
#
# The rule_* functions in the budget arm are dispatched indirectly as
# "rule_$rule", so shellcheck reads them as never-invoked (SC2329) and their
# bodies as unreachable (SC2317). That indirection is the point: it is what
# makes the PRECEDENCE list the single place the stop/pass ordering is
# written down. Both are disabled file-wide.
#
# Note both were reported by CI and NOT by shellcheck 0.11.0 locally. The
# runner runs a different version, so local-clean is not CI-clean here and
# has now cost two round-trips; that gap is real and not closed by this file.
# shellcheck disable=SC2329,SC2317
# round-budget.sh — bstack P20 dynamic round budget + continuation ledger
#
# Replaces the fixed `MAX_ROUNDS=3`, which was printed by pre-push and read by
# no conditional. Practice ran past it routinely (BRO-2190 to 21 rounds,
# BRO-2185 to 22, BRO-2079 to 12 and closed unmerged) while the live rule was an
# unwritten controller reconstructed from memory each arc. This is that
# controller, written down.
#
# WHAT IT DECIDES. The bookkeeping and the bounds — never whether a round made
# progress. That judgement belongs to the reviewer; handing it to the writer is
# the failure P20 exists to stop. What this owns is:
#
#   "you claimed CONTINUE at round 4 with prediction P; round 5 recorded P as
#    REFUTED; that is two in a row; STOP."
#
# THE CURRENCY is a reproduced, executable defect in the change — not a score
# bump, not reviewer opinion, and never a finding about the justification for
# the change. Score slope is the wrong signal: BRO-2185 sat at 5-6 for eighteen
# rounds then moved 6->8 once an invariant was hoisted, while BRO-2079 ran twelve
# rounds on an equally flat score and closed unmerged. Same slope, opposite
# correct answer.
#
# BOUNDS
#   rounds 1-3   free
#   rounds 4-7   each earned by a CONTINUE verdict carrying a located prediction
#   round >= 8   human. Unbounded self-granted budget is the resource-acquisition
#                pillar the workspace leaves open by design.
#
# ANTI-VACUITY. "Should I extend?" asked cold answers YES almost always, and a
# second model rubber-stamping that is worse than the counter it replaces. Four
# rules, checked against the ledger rather than recalled:
#   1. CONTINUE requires a prediction naming a location
#   2. a round following CONTINUE must settle it (else rule 3 never fires)
#   3. two consecutive REFUTED end the loop
#   4. CONTINUE verdicts cannot stack without an intervening round
#
# THE BOUNDARY. These bind the LEDGER. Stops are absorbing and cannot be cleared
# by appending, reset by re-running pre-push, or dodged by a rebase. They do NOT
# compel anyone to run `budget`, `--ledger` behind ROUND_BUDGET_TEST_LEDGER still
# repoints the path, and the ledger is a plain file this agent can delete. This
# removes ACCIDENTAL drift — the miscounted round, the stop quietly walked back —
# which is what actually went wrong on the long arcs. SKILL.md states it in full.
#
# STRUCTURE. Every command passes through one gate (`load_ledger`), and the
# budget's precedence is one ordered list. Both are deliberate: three review
# rounds each found a guard living at one caller and not its sibling, or an
# ordering wrong in one of six sequential branches. One site is one place to be
# wrong.
#
# Usage:
#   round-budget.sh record-round   --run-id=ID --score=N --defect=yes|no \
#                                  [--fingerprints=a,b] [--settles=CONFIRMED|REFUTED]
#   round-budget.sh record-verdict --run-id=ID --verdict=CONTINUE|STOP|STRUCTURAL \
#                                  [--prediction=TEXT] [--directive=TEXT]
#   round-budget.sh budget         --run-id=ID     # may another round run?
#   round-budget.sh show           --run-id=ID
#   round-budget.sh reset          --run-id=ID     # archive a finished arc's ledger
#
# Exit codes (0/2/4 are taken by cross-review.sh):
#   0  AUTHORIZED   another round may run
#   2  usage error
#   3  PASSED       score >= 7; the gate is done
#   5  REVIEW-REQ   rounds 4-7 with no continuation verdict recorded
#   6  STOP         regression, refuted twice, no defect twice, STOP/STRUCTURAL,
#                   or an unparsable ledger
#   7  HUMAN        round ceiling reached

set -euo pipefail
export LC_ALL=C

FREE_ROUNDS=3
HUMAN_CEILING=8
PASS_SCORE=7

COMMAND="${1:-}"
[ -n "$COMMAND" ] || { echo "round-budget: no command. Try --help" >&2; exit 2; }
shift || true

case "$COMMAND" in
    --help|-h|help)
        sed -n '/^# Usage:/,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
        exit 0 ;;
    record-round|record-verdict|budget|show|reset) ;;
    *) echo "round-budget: unknown command '$COMMAND'" >&2; exit 2 ;;
esac

RUN_ID=""; SCORE=""; DEFECT=""; FINGERPRINTS=""; SETTLES=""
VERDICT=""; PREDICTION=""; DIRECTIVE=""; LEDGER_PATH=""

for arg in "$@"; do
    case "$arg" in
        --run-id=*)       RUN_ID="${arg#*=}" ;;
        --score=*)        SCORE="${arg#*=}" ;;
        --defect=*)       DEFECT="${arg#*=}" ;;
        --fingerprints=*) FINGERPRINTS="${arg#*=}" ;;
        --settles=*)      SETTLES="${arg#*=}" ;;
        --verdict=*)      VERDICT="${arg#*=}" ;;
        --prediction=*)   PREDICTION="${arg#*=}" ;;
        --directive=*)    DIRECTIVE="${arg#*=}" ;;
        --ledger=*)
            # A test seam, gated so it is not a silent production budget-reset.
            # It is not a barrier — see THE BOUNDARY above.
            if [ "${ROUND_BUDGET_TEST_LEDGER:-0}" != "1" ]; then
                echo "round-budget: --ledger is a test-only seam." >&2
                echo "  Set ROUND_BUDGET_TEST_LEDGER=1 to use it." >&2
                exit 2
            fi
            LEDGER_PATH="${arg#*=}" ;;
        *) echo "round-budget: unknown flag '$arg'" >&2; exit 2 ;;
    esac
done

[ -n "$RUN_ID" ] || { echo "round-budget: --run-id=ID required" >&2; exit 2; }
case "$RUN_ID" in
    *[!A-Za-z0-9._-]*) echo "round-budget: --run-id must be [A-Za-z0-9._-]" >&2; exit 2 ;;
esac

# Keyed per run-id: two reviews in one worktree must not share a history.
ledger_path() {
    if [ -n "$LEDGER_PATH" ]; then echo "$LEDGER_PATH"; return; fi
    local gd
    if ! gd=$(git rev-parse --git-dir 2>/dev/null); then
        echo "round-budget: needs a git repo (or pass --ledger=PATH)" >&2
        exit 2
    fi
    echo "$gd/cross-review-rounds.$RUN_ID.tsv"
}
LEDGER="$(ledger_path)"

# Tabs and newlines are the record separators, so they cannot survive in a field:
# a prediction containing a tab would shift every column to its right.
sanitize() { printf '%s' "${1:-}" | tr '\t\n' '  ' | sed 's/  *$//'; }

# One definition, called at write AND at read. Enforcing at the entry point but
# not against the stored artifact is how a hand-edited row buys a round.
# Deliberately weak: it accepts any path-ish token, and rules out `x`.
prediction_is_valid() {
    local pred="$1"
    [ "${#pred}" -ge 12 ] || return 1
    printf '%s' "$pred" | grep -qE '[A-Za-z0-9_-]+\.[A-Za-z]+|/|:[0-9]+'
}

# mkdir is the portable atomic test-and-set. LOCK_DIR is global so the EXIT trap
# can still resolve it; as a `local` the trap died under `set -u` and never
# released.
LOCK_DIR=""
with_lock() {
    LOCK_DIR="$LEDGER.lock"
    local tries=0
    until mkdir "$LOCK_DIR" 2>/dev/null; do
        if [ ! -d "$LOCK_DIR" ]; then
            echo "round-budget: cannot create $LOCK_DIR — the ledger's directory is" >&2
            echo "  missing or unwritable. This is not lock contention." >&2
            exit 2
        fi
        tries=$((tries+1))
        [ "$tries" -le 50 ] || {
            echo "round-budget: could not acquire $LOCK_DIR after 50 tries." >&2; exit 2; }
        sleep 0.1
    done
    trap 'if [ -n "$LOCK_DIR" ]; then rmdir "$LOCK_DIR" 2>/dev/null || true; fi' EXIT
}

# An existing-but-unreadable ledger is an error, never an empty history: zero
# rows reads as "no rounds yet", which authorizes.
read_rows() {
    if [ -f "$LEDGER" ]; then
        cat "$LEDGER" || {
            echo "round-budget: ledger exists at $LEDGER but cannot be read." >&2
            exit 6
        }
    fi
}
last_row_any() { read_rows | tail -1; }
field() { printf '%s' "$1" | cut -f"$2"; }

# One pass over the WHOLE ledger. Every stop is ABSORBING — computed over all of
# history, so none can be cleared by appending. Malformed input FAILS CLOSED: a
# corrupt ledger must not read as "no reason to stop".
#
# ROUND   n score defect fingerprints settles     (6 fields)
# VERDICT verdict prediction directive            (4 fields)
analyze() {
    read_rows | awk -F'\t' '
        BEGIN { rounds=0; prev=-1; last=-1; regressed=0
                ref=0; maxref=0; nod=0; maxnod=0
                terminal=""; directive=""; badscore=0; badverdict=""; badrow=0; pending=0
                badhistory="" }
        $1=="ROUND" {
            if (NF != 6) { badrow=1 }
            rounds++
            if ($3 !~ /^[0-9]+$/ || $3+0 > 10) { badscore=1 }
            else {
                if (prev >= 0 && $3+0 < prev) regressed=1
                prev=$3+0; last=$3+0
            }
            if ($4=="no")  { nod++; if (nod>maxnod) maxnod=nod } else if ($4=="yes") nod=0; else badrow=1
            if ($6=="REFUTED")   { ref++; if (ref>maxref) maxref=ref }
            else if ($6=="CONFIRMED") ref=0
            else if ($6!="-")    badrow=1
            # Rule 2 against the STORED history: a round following a live
            # CONTINUE must settle it. Enforced only at record-round before, so a
            # hand-edited or older row spent a CONTINUE without ever settling it.
            if (pending==1 && $6=="-") badhistory="a round follows a CONTINUE without settling its prediction"
            pending=0
            next
        }
        $1=="VERDICT" {
            if (NF != 4) { badrow=1 }
            if ($2=="STOP" || $2=="STRUCTURAL") {
                if (terminal=="") { terminal=$2; directive=$4 }
            } else if ($2=="CONTINUE") {
                # Rule 4 against the STORED history: verdicts cannot stack.
                if (pending==1) badhistory="two CONTINUE verdicts stack with no round between them"
                pending=1
            }
            else { badverdict=$2 }
            next
        }
        NF>0 { badrow=1 }
        END { print rounds"\t"last"\t"regressed"\t"maxref"\t"maxnod"\t"terminal"\t"badscore"\t"badverdict"\t"pending"\t"directive"\t"badrow"\t"badhistory }'
}

# ─── The one gate ─────────────────────────────────────────────────────────
#
# Every command passes through here. Three review rounds each found a guard
# living at one caller and not its sibling — corrupt-check in `budget` but not
# the recorders, terminal-check in `record-round` but not `record-verdict`,
# prediction validation at write but not at read. One site makes that class of
# defect unrepresentable, and collapses four redundant `analyze` passes into one.
LG_N=""; LG_SCORE=""; LG_REGRESSED=""; LG_MAXREF=""; LG_MAXNOD=""
LG_TERMINAL=""; LG_PENDING=""; LG_DIRECTIVE=""
# Snapshotted in load_ledger so the rules never re-read the file: rereading mixed
# stale globals with a newer tail whenever anything appended concurrently.
LG_LAST_TYPE=""; LG_LAST_VERDICT=""; LG_LAST_PRED=""
load_ledger() {
    local a
    a="$(analyze)" || exit 6
    LG_N=$(printf '%s' "$a" | cut -f1)
    LG_SCORE=$(printf '%s' "$a" | cut -f2)
    LG_REGRESSED=$(printf '%s' "$a" | cut -f3)
    LG_MAXREF=$(printf '%s' "$a" | cut -f4)
    LG_MAXNOD=$(printf '%s' "$a" | cut -f5)
    LG_TERMINAL=$(printf '%s' "$a" | cut -f6)
    LG_PENDING=$(printf '%s' "$a" | cut -f9)
    LG_DIRECTIVE=$(printf '%s' "$a" | cut -f10)
    local badscore badverdict badrow badhistory last
    badscore=$(printf '%s' "$a" | cut -f7)
    badverdict=$(printf '%s' "$a" | cut -f8)
    badrow=$(printf '%s' "$a" | cut -f11)
    badhistory=$(printf '%s' "$a" | cut -f12)
    last="$(last_row_any)"
    LG_LAST_TYPE=$(field "$last" 1)
    LG_LAST_VERDICT=$(field "$last" 2)
    LG_LAST_PRED=$(field "$last" 3)

    if [ -n "$badhistory" ]; then
        echo "STOP — $LEDGER records a history the recorder would have refused:"
        echo "  $badhistory"
        echo "  A rule the recorder enforces must hold for the STORED ledger too,"
        echo "  or a hand-edited row buys what no command could."
        exit 6
    fi

    if [ "$badscore" != "0" ] || [ "$badrow" != "0" ] || [ -n "$badverdict" ]; then
        echo "STOP — the ledger at $LEDGER does not parse."
        [ "$badscore" != "0" ] && echo "  A round carries a non-integer or out-of-range score."
        [ -n "$badverdict" ]   && echo "  Unrecognised verdict token: '$badverdict'."
        [ "$badrow" != "0" ]   && echo "  A row has the wrong shape or arity."
        echo "  Refusing to act on a history that cannot be read."
        exit 6
    fi

    # Every CONTINUE row must satisfy the rule the recorder applies. Rows carry a
    # "P:" prefix so an EMPTY prediction survives as a line rather than vanishing
    # — the emptiest vacuous continuation is the one that must not slip through.
    local preds row vpred old_ifs
    if ! preds=$(read_rows | awk -F'\t' '$1=="VERDICT" && $2=="CONTINUE" {print "P:" $3}'); then
        echo "STOP — could not read the CONTINUE rows of $LEDGER to validate them."
        exit 6
    fi
    old_ifs=$IFS
    IFS='
'
    set -f
    for row in $preds; do
        vpred=${row#P:}
        if ! prediction_is_valid "$vpred"; then
            set +f; IFS=$old_ifs
            echo "STOP — a CONTINUE row in $LEDGER carries a prediction that would"
            echo "  not pass the recorder: '$vpred'"
            echo "  It names nowhere the next round could check, so it cannot be"
            echo "  settled, so it cannot have earned a round."
            exit 6
        fi
    done
    set +f
    IFS=$old_ifs
}

# The ledger must not grow past its own terminal state. Both recorders, one site.
refuse_past_terminal() {
    [ -n "$LG_TERMINAL" ] || return 0
    echo "round-budget: a $LG_TERMINAL verdict is recorded in $LEDGER." >&2
    echo "  That state is terminal: recording more does not clear it." >&2
    echo "" >&2
    echo "  If this arc is FINISHED and the branch is being reused, archive it:" >&2
    echo "    round-budget.sh reset --run-id=$RUN_ID" >&2
    exit 6
}

case "$COMMAND" in

record-round)
    with_lock
    load_ledger
    refuse_past_terminal
    [ -n "$SCORE" ]  || { echo "round-budget: --score=N required" >&2; exit 2; }
    case "$SCORE" in ''|*[!0-9]*) echo "round-budget: --score must be an integer 0-10" >&2; exit 2 ;; esac
    [ "$SCORE" -le 10 ] || { echo "round-budget: --score must be 0-10" >&2; exit 2; }
    case "$DEFECT" in
        yes|no) ;;
        *) echo "round-budget: --defect=yes|no required (was a reproduced, executable defect found IN THE CHANGE?)" >&2; exit 2 ;;
    esac

    # Rule 2: a round following CONTINUE must settle it, or rule 3 never fires.
    if [ "$LG_PENDING" = "1" ]; then
        case "$SETTLES" in
            CONFIRMED|REFUTED) ;;
            *) echo "round-budget: this round follows a CONTINUE verdict carrying a live" >&2
               echo "  prediction, so --settles=CONFIRMED|REFUTED is required." >&2
               exit 2 ;;
        esac
    else
        case "$SETTLES" in
            ''|CONFIRMED|REFUTED) ;;
            *) echo "round-budget: --settles must be CONFIRMED or REFUTED" >&2; exit 2 ;;
        esac
        [ -z "$SETTLES" ] || {
            echo "round-budget: --settles given but no CONTINUE prediction is live" >&2; exit 2; }
    fi

    N=$(( LG_N + 1 ))
    printf 'ROUND\t%s\t%s\t%s\t%s\t%s\n' \
        "$N" "$SCORE" "$DEFECT" "$(sanitize "$FINGERPRINTS")" "${SETTLES:--}" >> "$LEDGER"
    echo "round-budget: recorded round $N (score $SCORE, defect=$DEFECT, settles=${SETTLES:--}) -> $LEDGER"
    ;;

record-verdict)
    with_lock
    load_ledger
    refuse_past_terminal
    case "$VERDICT" in
        CONTINUE|STOP|STRUCTURAL) ;;
        *) echo "round-budget: --verdict=CONTINUE|STOP|STRUCTURAL required" >&2; exit 2 ;;
    esac

    # Rule 1: a CONTINUE with nothing settleable cannot be wrong, and a verdict
    # that cannot be wrong is an opinion.
    if [ "$VERDICT" = "CONTINUE" ]; then
        CLEAN_PRED="$(sanitize "$PREDICTION")"
        if ! prediction_is_valid "$CLEAN_PRED"; then
            echo "round-budget: --verdict=CONTINUE requires a --prediction that names" >&2
            echo "  WHERE to look -- a path, a file.ext, or a file:line -- and what" >&2
            echo "  class of defect is expected there. Got: '$CLEAN_PRED'" >&2
            exit 2
        fi
    fi

    # STRUCTURAL without a directive is a stop with no instruction.
    if [ "$VERDICT" = "STRUCTURAL" ] && [ -z "$(sanitize "$DIRECTIVE")" ]; then
        echo "round-budget: --verdict=STRUCTURAL requires --directive." >&2
        echo "  Name the move: hoist the invariant | delete the justification |" >&2
        echo "  cut the gate | close unmerged." >&2
        exit 2
    fi

    # Rule 4: verdicts cannot stack without an intervening round.
    if [ "$VERDICT" = "CONTINUE" ] && [ "$LG_PENDING" = "1" ]; then
        echo "round-budget: a CONTINUE verdict is already live and unsettled." >&2
        echo "  Record the round it authorized before recording another." >&2
        exit 2
    fi

    printf 'VERDICT\t%s\t%s\t%s\n' \
        "$VERDICT" "$(sanitize "$PREDICTION")" "$(sanitize "$DIRECTIVE")" >> "$LEDGER"
    echo "round-budget: recorded verdict $VERDICT -> $LEDGER"
    ;;

reset)
    # Arc ids are branch-derived, so a recycled branch reuses its ledger. Right
    # while an arc is live (a rebase must not reset the budget), wrong once it is
    # finished.
    #
    # GATED, because unguarded this is a direct laundering path: archiving a live
    # ledger clears a STOP or STRUCTURAL without the directive ever being
    # executed, and `budget` never consults the archive. "It archives rather than
    # deletes" is evidence after the fact, not a control. A ledger may be reset
    # only once it has REACHED an end state — a terminal verdict, or a passing
    # score. A live arc cannot be reset out from under its own budget.
    with_lock
    if [ ! -f "$LEDGER" ]; then
        echo "round-budget: no ledger at $LEDGER — nothing to reset."
        exit 0
    fi
    load_ledger
    if [ -z "$LG_TERMINAL" ] && { [ "$LG_N" = "0" ] || [ "$LG_SCORE" -lt "$PASS_SCORE" ]; }; then
        echo "round-budget: refusing to reset a LIVE ledger." >&2
        echo "  $LG_N round(s) recorded, last score ${LG_SCORE}, no terminal verdict." >&2
        echo "  reset retires a FINISHED arc — one that reached a STOP or STRUCTURAL" >&2
        echo "  verdict, or a passing score. Resetting a live one clears a budget" >&2
        echo "  nothing has closed, which is the laundering this gate prevents." >&2
        exit 6
    fi
    ARCHIVE="$LEDGER.archived.$(wc -l < "$LEDGER" | tr -d ' ')"
    mv "$LEDGER" "$ARCHIVE"
    echo "round-budget: archived -> $ARCHIVE"
    echo "  The next round on this arc id starts from round 1."
    ;;

show)
    if [ ! -f "$LEDGER" ]; then echo "round-budget: no ledger at $LEDGER"; exit 0; fi
    echo "  Ledger: $LEDGER"
    echo ""
    awk -F'\t' '
        $1=="ROUND"   { printf "  round %-3s score %-3s defect=%-4s settles=%-10s %s\n", $2,$3,$4,$6,$5 }
        $1=="VERDICT" { printf "  verdict %-11s %s%s\n", $2, $3, ($4!="" ? "  [directive: " $4 "]" : "") }
    ' "$LEDGER"
    ;;

budget)
    load_ledger

    if [ "$LG_N" = "0" ]; then
        if [ -n "$LG_TERMINAL" ]; then
            echo "STOP — a $LG_TERMINAL verdict is recorded and no round has run since."
            exit 6
        fi
        echo "AUTHORIZED — round 1 of $FREE_ROUNDS free rounds."
        exit 0
    fi

    # ─── Precedence, as data ──────────────────────────────────────────────
    #
    # Ordering encoded ONCE, in this list, rather than in six sequential `if`
    # blocks. Two of the three review rounds landed on ordering defects — a
    # ceiling checked in the wrong place, then PASSED checked above the stops —
    # and six branches are six places to get the order wrong.
    #
    # Stops come before PASSED because the score is the agent's OWN SELF-REPORT:
    # if a pass outranked a stop, every stop would cost one integer to escape.
    # ONE source of truth for both the ORDER and the EXIT CODE. Keeping names in
    # a list and codes in a separate `case` wrote each rule in three places —
    # list, function name, case arm — which could disagree.
    PRECEDENCE="regressed:6 refuted:6 nodefect:6 terminal:6 passed:3 ceiling:7 free:0 review_required:5 earned:0"

    rule_regressed() {
        [ "$LG_REGRESSED" != "0" ] || return 1
        echo "STOP — the score REGRESSED at some point in this arc."
        echo "  A regression is not a plateau. Escalate rather than swing again."
        return 0
    }
    rule_refuted() {
        [ "$LG_MAXREF" -ge 2 ] || return 1
        echo "STOP — $LG_MAXREF consecutive predictions were REFUTED."
        echo "  The continuation review was wrong twice running about what the next"
        echo "  round would find; this does not clear by recording a later CONFIRMED."
        return 0
    }
    rule_nodefect() {
        [ "$LG_MAXNOD" -ge 2 ] || return 1
        echo "STOP — $LG_MAXNOD consecutive rounds reproduced NO defect in the change."
        echo "  The currency of a continuation is a reproduced, executable defect."
        return 0
    }
    rule_terminal() {
        [ -n "$LG_TERMINAL" ] || return 1
        if [ "$LG_TERMINAL" = "STRUCTURAL" ]; then
            echo "STOP (STRUCTURAL) — another fix round is the wrong move."
            echo "  Directive: $LG_DIRECTIVE"
            echo "  The defect stream is repeating in CLASS while moving in LOCATION."
            echo "  Change the shape of the fix, do not take another swing at it."
        else
            echo "STOP — the continuation review returned STOP."
        fi
        return 0
    }
    rule_passed() {
        [ "$LG_SCORE" -ge "$PASS_SCORE" ] || return 1
        echo "PASSED — last round scored $LG_SCORE (>= $PASS_SCORE). No further round needed."
        return 0
    }
    rule_ceiling() {
        [ "$LG_N" -ge "$HUMAN_CEILING" ] || return 1
        echo "HUMAN — $LG_N rounds recorded (ceiling $HUMAN_CEILING)."
        echo "  Escalate through the handback contract with the ledger attached."
        echo "  No verdict buys another round here."
        return 0
    }
    rule_free() {
        [ "$LG_N" -lt "$FREE_ROUNDS" ] || return 1
        echo "AUTHORIZED — round $((LG_N+1)) of $FREE_ROUNDS free rounds."
        return 0
    }
    # Split from rule_earned so each rule owns ONE outcome. Fused, the rule chose
    # the message while the dispatcher re-evaluated the same condition to choose
    # the exit code -- the same condition in two places, which is the defect class
    # this restructure exists to remove.
    rule_review_required() {
        [ "$LG_LAST_TYPE" != "VERDICT" ] || return 1
        echo "REVIEW-REQUIRED — $LG_N rounds recorded; past the $FREE_ROUNDS free rounds."
        echo "  Run the continuation review, then record its verdict:"
        echo "    round-budget.sh record-verdict --run-id=$RUN_ID --verdict=... [--prediction=...]"
        echo "  The brief's default is STOP; the burden is on continuation."
        return 0
    }
    # STOP/STRUCTURAL are caught by rule_terminal, so CONTINUE is all that can be
    # live here. The verdict must be the MOST RECENT row: one already settled by a
    # later round has spent its authority.
    rule_earned() {
        [ "$LG_LAST_TYPE" = "VERDICT" ] || return 1
        echo "AUTHORIZED — round $((LG_N+1)), earned by a $LG_LAST_VERDICT verdict."
        echo "  Live prediction: $LG_LAST_PRED"
        echo "  The next recorded round MUST settle it (--settles=CONFIRMED|REFUTED)."
        return 0
    }
    # Each rule prints its own outcome and returns 0 when it fires. Exit codes
    # are keyed off the rule name so the mapping is visible in one place.
    for entry in $PRECEDENCE; do
        rule=${entry%%:*}
        code=${entry##*:}
        # A named rule with no function would otherwise surface as "command not
        # found" inside an `if`, i.e. as a silently skipped rule.
        if ! declare -F "rule_$rule" >/dev/null 2>&1; then
            echo "round-budget: PRECEDENCE names '$rule' but rule_$rule does not exist." >&2
            exit 6
        fi
        if "rule_$rule"; then exit "$code"; fi
    done
    echo "STOP — no precedence rule matched for $LEDGER; refusing to guess." >&2
    exit 6
    ;;
esac
