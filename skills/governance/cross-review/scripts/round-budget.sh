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
        --ledger=*)       LEDGER_PATH="${arg#*=}" ;;
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

# Trailing REFUTED streak, counted over ROUND rows newest-first.
refuted_streak() {
    read_rows | awk -F'\t' '$1=="ROUND"{print $6}' | awk '
        { rows[NR]=$0 }
        END { n=0; for (i=NR; i>=1; i--) { if (rows[i]=="REFUTED") n++; else break } print n }'
}

# Is the most recent verdict a CONTINUE whose prediction has not been settled by
# a later ROUND row? That is the only state in which a round is pre-authorized.
pending_continue() {
    read_rows | awk -F'\t' '
        $1=="VERDICT" { v=$2; pending=(v=="CONTINUE") ? 1 : 0; next }
        $1=="ROUND"   { pending=0 }
        END { print pending+0 }'
}

case "$COMMAND" in

record-round)
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
    case "$VERDICT" in
        CONTINUE|STOP|STRUCTURAL) ;;
        *) echo "round-budget: --verdict=CONTINUE|STOP|STRUCTURAL required" >&2; exit 2 ;;
    esac

    # Anti-vacuity rule 1. A CONTINUE with nothing to settle cannot be wrong.
    if [ "$VERDICT" = "CONTINUE" ] && [ -z "$(sanitize "$PREDICTION")" ]; then
        echo "round-budget: --verdict=CONTINUE requires a non-empty --prediction." >&2
        echo "  Name the defect class AND location the next round should surface," >&2
        echo "  and the next round settles it. A continuation that cannot be" >&2
        echo "  refuted is not a verdict, it is an opinion." >&2
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
    N=$(count_rounds)
    LAST_ROUND="$(last_row_of ROUND)"
    LAST_ANY="$(last_row_any)"

    if [ "$N" = "0" ]; then
        echo "AUTHORIZED — round 1 of $FREE_ROUNDS free rounds."
        exit 0
    fi

    LAST_SCORE=$(field "$LAST_ROUND" 3)

    # The gate is passed; there is nothing left to authorize.
    if [ "$LAST_SCORE" -ge "$PASS_SCORE" ]; then
        echo "PASSED — last round scored $LAST_SCORE (>= $PASS_SCORE). No further round needed."
        exit 3
    fi

    # Regression halts immediately and is checked BEFORE the free floor: a score
    # that went backwards is the one signal that never warrants another swing,
    # and the reference arc (2,2,6,5 -> closed unmerged) regressed at round 4.
    if [ "$N" -ge 2 ]; then
        PREV_SCORE=$(read_rows | awk -F'\t' '$1=="ROUND"{print $3}' | tail -2 | head -1)
        if [ "$LAST_SCORE" -lt "$PREV_SCORE" ]; then
            echo "STOP — score REGRESSED ($PREV_SCORE -> $LAST_SCORE) at round $N."
            echo "  A regression is not a plateau. Escalate rather than take another swing."
            exit 6
        fi
    fi

    STREAK=$(refuted_streak)
    if [ "$STREAK" -ge 2 ]; then
        echo "STOP — $STREAK consecutive predictions REFUTED."
        echo "  The continuation review has been wrong twice running about what the"
        echo "  next round would find. It has no remaining claim on the budget."
        exit 6
    fi

    if [ "$N" -ge "$HUMAN_CEILING" ]; then
        echo "HUMAN — $N rounds recorded (ceiling $HUMAN_CEILING)."
        echo "  Escalate through the handback contract with the ledger attached."
        echo "  No verdict overrides this: unbounded self-granted budget is the"
        echo "  resource-acquisition pillar the workspace leaves open by design."
        exit 7
    fi

    if [ "$N" -lt "$FREE_ROUNDS" ]; then
        echo "AUTHORIZED — round $((N+1)) of $FREE_ROUNDS free rounds."
        exit 0
    fi

    # Rounds 4..7: a continuation verdict is required, and it must be the most
    # recent row. A verdict recorded BEFORE the latest round has already been
    # settled by it and cannot authorize a second one.
    LAST_TYPE=$(field "$LAST_ANY" 1)
    if [ "$LAST_TYPE" != "VERDICT" ]; then
        echo "REVIEW-REQUIRED — $N rounds recorded; past the $FREE_ROUNDS free rounds."
        echo "  Run the continuation review, then record its verdict:"
        echo "    round-budget.sh record-verdict --run-id=$RUN_ID --verdict=... [--prediction=...]"
        echo "  The brief's default is STOP; the burden is on continuation."
        exit 5
    fi

    LAST_VERDICT=$(field "$LAST_ANY" 2)
    case "$LAST_VERDICT" in
        CONTINUE)
            echo "AUTHORIZED — round $((N+1)), earned by a CONTINUE verdict."
            echo "  Live prediction: $(field "$LAST_ANY" 3)"
            echo "  The next recorded round MUST settle it (--settles=CONFIRMED|REFUTED)."
            exit 0 ;;
        STOP)
            echo "STOP — the continuation review returned STOP at round $N."
            exit 6 ;;
        STRUCTURAL)
            echo "STOP (STRUCTURAL) — another fix round is the wrong move at round $N."
            echo "  Directive: $(field "$LAST_ANY" 4)"
            echo "  The defect stream is repeating in CLASS while moving in LOCATION."
            echo "  Change the shape of the fix, do not take another swing at it."
            exit 6 ;;
    esac
    ;;
esac
