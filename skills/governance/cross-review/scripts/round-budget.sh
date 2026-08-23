#!/usr/bin/env bash
# round-budget.sh — bstack P20 dynamic round budget + continuation ledger
#
# Replaces the fixed `MAX_ROUNDS=3`, which was never enforced anywhere: it was
# printed by pre-push and read by nobody. Practice ran past it routinely
# (BRO-2190 to 21 rounds, BRO-2185 to 22, BRO-2079 to 12 and closed unmerged)
# while the live rule was an UNWRITTEN controller reconstructed from memory each
# arc. This script is that controller, written down.
#
# ─── What this script decides, and what it refuses to decide ──────────────
#
# It does NOT judge whether a round made progress. That judgement belongs to the
# reviewer, and handing it to the writer is the exact failure P20 exists to stop.
# What it owns is the BOOKKEEPING and the BOUNDS:
#
#   "you claimed CONTINUE at round 4 with prediction P; round 5 recorded P as
#    REFUTED; that is two in a row; STOP."
#
# Bookkeeping is precisely what an agent does badly from recall, and every
# recorded instance of this loop running long shows the same tell — the round
# count and the score trajectory get restated from memory, drift, and stop
# being checkable.
#
# ─── Why not score slope ──────────────────────────────────────────────────
#
# The obvious dynamic rule (extend while the score climbs) is refuted by the
# arcs. BRO-2185 sat at 5-6 for eighteen consecutive rounds, then moved 6->8 in
# one round once the invariant was hoisted; a plateau-stop kills it at ~round 4
# and discards the arc that eventually passed. BRO-2079 ran twelve rounds on an
# equally flat score and closed unmerged. Same slope, opposite correct answer.
#
# The currency is instead a REPRODUCED EXECUTABLE DEFECT IN THE CHANGE. Named,
# without being named, in .control/asks/bro-2190-tier-model.yaml:78 — "Rounds 20
# and 21 each returned an EXECUTABLE false accept or false reject, reproduced by
# construction before being accepted — that is the change, not the account of it."
#
# ─── Bounds ───────────────────────────────────────────────────────────────
#
#   rounds 1-3   free; no continuation review (the old budget, unchanged)
#   rounds 4-7   each earned by a CONTINUE verdict carrying a live prediction
#   round >= 8   human required, whatever the verdict says
#
# The ceiling is deliberate and is not timidity. An agent that grants itself
# unbounded budget by asking itself has started acquiring its own resources;
# the workspace leaves that pillar open BY DESIGN (research/entities/concept/
# rsi-self-growth-readiness.md). Round 8 keeps the human as the authority.
#
# ─── The anti-vacuity rules (the load-bearing part) ───────────────────────
#
# "Should I extend?" asked cold answers YES almost always. A second model
# rubber-stamping that is WORSE than the fixed counter, because it launders the
# writer's appetite through something that looks independent. Four rules, each
# enforced here rather than left to the agent's discipline:
#
#   1. CONTINUE requires a non-empty --prediction. A continuation with nothing
#      to settle cannot be wrong, and a verdict that cannot be wrong is not a
#      verdict.
#   2. A round following a CONTINUE must pass --settles=CONFIRMED|REFUTED. Without
#      it predictions never settle, and rule 3 becomes unreachable — a live
#      check that can never fire.
#   3. Two consecutive REFUTED predictions -> STOP, no override.
#   4. Two CONTINUE verdicts cannot stack without an intervening round. Otherwise
#      budget is inflated by recording the same optimism repeatedly.
#
# Usage:
#   round-budget.sh record-round   --run-id=ID --score=N --defect=yes|no \
#                                  [--fingerprints=a,b] [--settles=CONFIRMED|REFUTED]
#   round-budget.sh record-verdict --run-id=ID --verdict=CONTINUE|STOP|STRUCTURAL \
#                                  [--prediction=TEXT] [--directive=TEXT]
#   round-budget.sh budget         --run-id=ID     # may another round run?
#   round-budget.sh show           --run-id=ID
#
# Exit codes for `budget` (0/2/4 are already taken by cross-review.sh):
#   0  AUTHORIZED  — another round may run
#   2  usage error
#   3  PASSED      — score >= 7; the gate is done, no further round needed
#   5  REVIEW-REQ  — rounds 4-7 with no continuation verdict recorded yet
#   6  STOP        — regression, refuted twice, STOP verdict, or STRUCTURAL
#   7  HUMAN       — round ceiling reached; escalate

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
    record-round|record-verdict|budget|show) ;;
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
            # A test seam, gated so it cannot serve as a production escape
            # hatch: pointing the controller at a fresh path is the cheapest
            # way to reset a budget, and an unadvertised flag that does it is
            # worse than no flag. The ledger is NOT tamper-proof against the
            # agent it governs -- it is bookkeeping that makes drift visible.
            # That boundary is documented rather than pretended away.
            if [ "${ROUND_BUDGET_TEST_LEDGER:-0}" != "1" ]; then
                echo "round-budget: --ledger is a test-only seam." >&2
                echo "  Set ROUND_BUDGET_TEST_LEDGER=1 to use it. In an arc the ledger" >&2
                echo "  path is derived from the run-id so a budget cannot be reset by" >&2
                echo "  pointing at a new file." >&2
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

# ─── Ledger location ──────────────────────────────────────────────────────
# Keyed per run-id, like the reviewer guard's state file. Two reviews in one
# worktree must not share a ledger: a merged round history is not a history.
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

# Tabs and newlines are the record separators, so they cannot survive in a
# field. Stripping them is not cosmetic: a prediction containing a tab would
# silently shift every column to its right and settle the wrong field.
sanitize() { printf '%s' "${1:-}" | tr '\t\n' '  ' | sed 's/  *$//'; }

# A ledger that exists but cannot be read must NEVER render as an empty one.
# The `&& cat || true` this replaces swallowed cat's failure and returned zero
# rows, which `budget` reads as "no rounds yet" -- i.e. AUTHORIZED. An
# unreadable ledger failing OPEN is the one direction this controller must not
# fail in, so an existing-but-unreadable file is an error, not an empty history.
# mkdir is atomic on every POSIX filesystem, so it is the portable test-and-set
# bash has. Without it two concurrent `record-round` calls after one live
# CONTINUE both pass pending_continue() and spend the same earned round twice.
LOCK_DIR=""
with_lock() {
    LOCK_DIR="$LEDGER.lock"
    local tries=0
    # LOCK_DIR is deliberately GLOBAL. As a `local` it was out of scope by the
    # time the EXIT trap fired, so the trap died on `unbound variable` under
    # `set -u`, the lock was never released, and every later call spun out its
    # full retry budget before failing. A lock that is never released is worse
    # than no lock.
    until mkdir "$LOCK_DIR" 2>/dev/null; do
        tries=$((tries+1))
        if [ "$tries" -gt 50 ]; then
            echo "round-budget: could not acquire $LOCK_DIR after 50 tries." >&2
            echo "  If no other run is active, remove it by hand." >&2
            exit 2
        fi
        sleep 0.1
    done
    trap 'if [ -n "$LOCK_DIR" ]; then rmdir "$LOCK_DIR" 2>/dev/null || true; fi' EXIT
}

read_rows() {
    if [ -f "$LEDGER" ]; then
        cat "$LEDGER" || {
            echo "round-budget: ledger exists at $LEDGER but cannot be read." >&2
            echo "  Refusing to treat it as an empty history: that reads as" >&2
            echo "  'no rounds yet' and authorizes another round." >&2
            return 1
        }
    fi
}
count_rounds() { read_rows | awk -F'\t' '$1=="ROUND"' | wc -l | tr -d ' '; }
last_row_of() { read_rows | awk -F'\t' -v t="$1" '$1==t' | tail -1; }
last_row_any() { read_rows | tail -1; }
field() { printf '%s' "$1" | cut -f"$2"; }

# ROUND   round score defect fingerprints settles
# VERDICT verdict prediction directive   (cols 2,3,4)

# ─── One pass over the WHOLE ledger ───────────────────────────────────────
#
# Every stop condition is ABSORBING: once it has held, it keeps holding. The
# first version computed each from the TAIL of the ledger, which made all of
# them escapable by appending -- from a two-REFUTED stop, one CONTINUE plus one
# CONFIRMED round cleared it and the budget resumed. A stop you can leave by
# writing another row is not a stop, and every rule here was reachable that way.
#
# Malformed input FAILS CLOSED. A non-integer score used to reach `[ "$x" -ge 7 ]`,
# print "integer expected" to stderr, and fall through to AUTHORIZED -- a corrupt
# ledger read as "no reason to stop", which is the one direction this must never
# fail in.
analyze() {
    read_rows | awk -F'\t' '
        BEGIN { rounds=0; prev=-1; last=-1; regressed=0
                ref=0; maxref=0; nod=0; maxnod=0
                terminal=""; directive=""; badscore=0; badverdict=""; badrow=0; pending=0 }
        $1=="ROUND" {
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
            pending=0
            next
        }
        $1=="VERDICT" {
            if ($2=="STOP" || $2=="STRUCTURAL") {
                if (terminal=="") { terminal=$2; directive=$4 }
            } else if ($2=="CONTINUE") { pending=1 }
            else { badverdict=$2 }
            next
        }
        NF>0 { badrow=1 }
        END { print rounds"\t"last"\t"regressed"\t"maxref"\t"maxnod"\t"terminal"\t"badscore"\t"badverdict"\t"pending"\t"directive"\t"badrow }'
}

count_rounds_a()   { printf '%s' "$1" | cut -f1; }
pending_continue() {
    local a; a="$(analyze)" || return 1
    printf '%s' "$a" | cut -f9
}

case "$COMMAND" in

record-round)
    with_lock
    [ -n "$SCORE" ]  || { echo "round-budget: --score=N required" >&2; exit 2; }
    case "$SCORE" in ''|*[!0-9]*) echo "round-budget: --score must be an integer 0-10" >&2; exit 2 ;; esac
    [ "$SCORE" -le 10 ] || { echo "round-budget: --score must be 0-10" >&2; exit 2; }
    case "$DEFECT" in
        yes|no) ;;
        *) echo "round-budget: --defect=yes|no required (was a reproduced, executable defect found IN THE CHANGE?)" >&2; exit 2 ;;
    esac

    # Anti-vacuity rule 2. A round that follows a CONTINUE must settle that
    # CONTINUE's prediction. Without this the prediction is decorative and the
    # two-refuted stop can never fire — a check that cannot fail.
    if [ "$(pending_continue)" = "1" ]; then
        case "$SETTLES" in
            CONFIRMED|REFUTED) ;;
            *) echo "round-budget: this round follows a CONTINUE verdict carrying a live" >&2
               echo "  prediction, so --settles=CONFIRMED|REFUTED is required." >&2
               echo "  An unsettled prediction makes the two-refuted stop unreachable." >&2
               exit 2 ;;
        esac
    else
        case "$SETTLES" in
            ''|CONFIRMED|REFUTED) ;;
            *) echo "round-budget: --settles must be CONFIRMED or REFUTED" >&2; exit 2 ;;
        esac
        [ -z "$SETTLES" ] || {
            echo "round-budget: --settles given but no CONTINUE prediction is live to settle" >&2; exit 2; }
    fi

    N=$(( $(count_rounds) + 1 ))
    printf 'ROUND\t%s\t%s\t%s\t%s\t%s\n' \
        "$N" "$SCORE" "$DEFECT" "$(sanitize "$FINGERPRINTS")" "${SETTLES:--}" >> "$LEDGER"
    echo "round-budget: recorded round $N (score $SCORE, defect=$DEFECT, settles=${SETTLES:--}) -> $LEDGER"
    ;;

record-verdict)
    with_lock
    case "$VERDICT" in
        CONTINUE|STOP|STRUCTURAL) ;;
        *) echo "round-budget: --verdict=CONTINUE|STOP|STRUCTURAL required" >&2; exit 2 ;;
    esac

    # Anti-vacuity rule 1. A CONTINUE with nothing to settle cannot be wrong.
    #
    # Non-emptiness alone was too weak: `--prediction=x` bought a round, so the
    # "falsifiable prediction" claim was mostly prose. A prediction must now name
    # somewhere to look -- a path, or a file:line. That is checkable; genuine
    # falsifiability is not, and claiming to enforce it would be the same kind of
    # overclaim. What is enforced is stated exactly, here and in SKILL.md.
    if [ "$VERDICT" = "CONTINUE" ]; then
        CLEAN_PRED="$(sanitize "$PREDICTION")"
        # ONE check, not two. A separate `-z` arm was logically subsumed by the
        # length arm below -- an empty prediction is also a short one -- so no
        # mutation of it could ever kill a test. A branch that cannot be wrong
        # is not a safeguard, it is decoration with an error message attached.
        if [ "${#CLEAN_PRED}" -lt 12 ] || ! printf '%s' "$CLEAN_PRED" | grep -qE '[A-Za-z0-9_-]+\.[A-Za-z]+|/|:[0-9]+'; then
            echo "round-budget: --verdict=CONTINUE requires a --prediction that names" >&2
            echo "  WHERE to look -- a path, a file.ext, or a file:line -- and what" >&2
            echo "  class of defect is expected there. Got: '$CLEAN_PRED'" >&2
            echo "  A continuation the next round cannot settle is an opinion, not a" >&2
            echo "  verdict; that is the whole reason the prediction is mandatory." >&2
            exit 2
        fi
    fi

    # F4. STRUCTURAL says "another fix round is the wrong move" -- without the
    # directive naming WHAT to do instead, it is a stop with no instruction, and
    # the verdict degrades to a blank "Directive:" line in the budget output.
    if [ "$VERDICT" = "STRUCTURAL" ] && [ -z "$(sanitize "$DIRECTIVE")" ]; then
        echo "round-budget: --verdict=STRUCTURAL requires --directive." >&2
        echo "  Name the move: hoist the invariant | delete the justification |" >&2
        echo "  cut the gate | close unmerged. A STRUCTURAL verdict with no" >&2
        echo "  directive is a stop with no instruction." >&2
        exit 2
    fi

    # Anti-vacuity rule 4. Verdicts cannot stack.
    if [ "$VERDICT" = "CONTINUE" ] && [ "$(pending_continue)" = "1" ]; then
        echo "round-budget: a CONTINUE verdict is already live and unsettled." >&2
        echo "  Record the round it authorized before recording another verdict;" >&2
        echo "  stacking CONTINUEs inflates the budget without earning it." >&2
        exit 2
    fi

    printf 'VERDICT\t%s\t%s\t%s\n' \
        "$VERDICT" "$(sanitize "$PREDICTION")" "$(sanitize "$DIRECTIVE")" >> "$LEDGER"
    echo "round-budget: recorded verdict $VERDICT -> $LEDGER"
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
    A="$(analyze)" || exit 6
    N=$(printf '%s' "$A" | cut -f1)
    LAST_SCORE=$(printf '%s' "$A" | cut -f2)
    REGRESSED=$(printf '%s' "$A" | cut -f3)
    MAXREF=$(printf '%s' "$A" | cut -f4)
    MAXNOD=$(printf '%s' "$A" | cut -f5)
    TERMINAL=$(printf '%s' "$A" | cut -f6)
    BADSCORE=$(printf '%s' "$A" | cut -f7)
    BADVERDICT=$(printf '%s' "$A" | cut -f8)
    DIRECTIVE_OUT=$(printf '%s' "$A" | cut -f10)
    BADROW=$(printf '%s' "$A" | cut -f11)

    # ─── Fail closed on anything unparsable ───────────────────────────────
    # An unreadable ledger already refuses to read as empty; a MALFORMED one
    # must refuse just as loudly. "I could not parse it" is not "nothing is
    # wrong", and the old code let a corrupt score fall through to AUTHORIZED.
    if [ "$BADSCORE" != "0" ] || [ "$BADROW" != "0" ] || [ -n "$BADVERDICT" ]; then
        echo "STOP — the ledger at $LEDGER does not parse."
        [ "$BADSCORE" != "0" ]   && echo "  A round carries a non-integer or out-of-range score."
        [ -n "$BADVERDICT" ]     && echo "  Unrecognised verdict token: '$BADVERDICT' (want CONTINUE|STOP|STRUCTURAL)."
        [ "$BADROW" != "0" ]     && echo "  A row has an unrecognised shape."
        echo "  Refusing to authorize against a ledger that cannot be read as a"
        echo "  history. Fix or discard it; do not continue past it."
        exit 6
    fi

    if [ "$N" = "0" ]; then
        # A ledger holding only a STOP verdict and no rounds still stops.
        if [ -n "$TERMINAL" ]; then
            echo "STOP — a $TERMINAL verdict is recorded and no round has run since."
            exit 6
        fi
        echo "AUTHORIZED — round 1 of $FREE_ROUNDS free rounds."
        exit 0
    fi

    # ─── Terminal SUCCESS outranks everything ─────────────────────────────
    # Reaching the bar IS the exit. The round-8 ceiling governs CONTINUATION,
    # not passing: an arc that scores 7 on round 9 is finished, not escalated.
    if [ "$LAST_SCORE" -ge "$PASS_SCORE" ]; then
        echo "PASSED — last round scored $LAST_SCORE (>= $PASS_SCORE). No further round needed."
        exit 3
    fi

    # ─── Absorbing stops, checked before every fast path ──────────────────
    # All four are computed over the WHOLE history, so none can be cleared by
    # appending another row. They sit above the free-round path because rounds
    # 1-3 are exactly when an arc is most likely to be told to stop, and the
    # first version returned AUTHORIZED there without ever looking.
    if [ "$REGRESSED" != "0" ]; then
        echo "STOP — the score REGRESSED at some point in this arc."
        echo "  A regression is not a plateau. Escalate rather than take another swing."
        exit 6
    fi
    if [ "$MAXREF" -ge 2 ]; then
        echo "STOP — $MAXREF consecutive predictions were REFUTED."
        echo "  The continuation review was wrong twice running about what the next"
        echo "  round would find. It has no remaining claim on the budget, and this"
        echo "  does not clear by recording a later CONFIRMED round."
        exit 6
    fi
    if [ "$MAXNOD" -ge 2 ]; then
        echo "STOP — $MAXNOD consecutive rounds reproduced NO defect in the change."
        echo "  The currency of a continuation is a reproduced, executable defect."
        echo "  Rounds that find nothing do not earn more rounds."
        exit 6
    fi
    if [ -n "$TERMINAL" ]; then
        if [ "$TERMINAL" = "STRUCTURAL" ]; then
            echo "STOP (STRUCTURAL) — another fix round is the wrong move."
            echo "  Directive: $DIRECTIVE_OUT"
            echo "  The defect stream is repeating in CLASS while moving in LOCATION."
            echo "  Change the shape of the fix, do not take another swing at it."
        else
            echo "STOP — the continuation review returned STOP."
        fi
        exit 6
    fi

    # ─── Bounds ───────────────────────────────────────────────────────────
    if [ "$N" -ge "$HUMAN_CEILING" ]; then
        echo "HUMAN — $N rounds recorded (ceiling $HUMAN_CEILING)."
        echo "  Escalate through the handback contract with the ledger attached."
        echo "  No verdict buys another round here: unbounded self-granted budget"
        echo "  is the resource-acquisition pillar the workspace leaves open by"
        echo "  design. (A passing score is not a continuation; it exits above.)"
        exit 7
    fi

    if [ "$N" -lt "$FREE_ROUNDS" ]; then
        echo "AUTHORIZED — round $((N+1)) of $FREE_ROUNDS free rounds."
        exit 0
    fi

    # ─── Rounds 4..7: a live CONTINUE is required ─────────────────────────
    # The verdict must be the MOST RECENT row. One already settled by a later
    # round has spent its authority; reusing it is how a single CONTINUE would
    # buy three rounds.
    LAST_ANY="$(last_row_any)"
    if [ "$(field "$LAST_ANY" 1)" != "VERDICT" ]; then
        echo "REVIEW-REQUIRED — $N rounds recorded; past the $FREE_ROUNDS free rounds."
        echo "  Run the continuation review, then record its verdict:"
        echo "    round-budget.sh record-verdict --run-id=$RUN_ID --verdict=... [--prediction=...]"
        echo "  The brief's default is STOP; the burden is on continuation."
        exit 5
    fi

    LAST_VERDICT=$(field "$LAST_ANY" 2)
    if [ "$LAST_VERDICT" = "CONTINUE" ]; then
        echo "AUTHORIZED — round $((N+1)), earned by a CONTINUE verdict."
        echo "  Live prediction: $(field "$LAST_ANY" 3)"
        echo "  The next recorded round MUST settle it (--settles=CONFIRMED|REFUTED)."
        exit 0
    fi

    # Unreachable: STOP/STRUCTURAL exit above, anything else is caught by the
    # parse guard. An explicit arm all the same -- the first version fell off the
    # end of a three-arm `case` with no default and returned 0 = AUTHORIZED in
    # silence, which is the worst possible way for this script to be wrong.
    echo "STOP — unhandled verdict state '$LAST_VERDICT' in $LEDGER." >&2
    exit 6
    ;;
esac
