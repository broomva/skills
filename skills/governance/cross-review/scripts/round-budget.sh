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
# WHICH PANEL SCORED IT. A round records the strata that produced its score,
# because the strata are not equal and a bare integer hides which ones ran.
# Stratum A is the only cross-vendor verdict and the only one where "cannot
# write" is literally true; B and C are the same model as the writer, so a 7
# from A+B+C and a 7 from C alone are different evidence carrying the same
# number. The field makes the two distinguishable in the record; it does not
# score them differently, and this file does not read it in any rule.
#
# Omitting --strata writes the literal `unrecorded` rather than an empty field.
# "Nobody wrote down which strata ran" and "only Stratum C ran" must not
# serialize to the same bytes -- absence read as an answer is the failure this
# field exists to remove, so absence is given a name instead of a blank.
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
# THE BOUNDARY. These bind the LEDGER. Stops are absorbing: they cannot be
# cleared by appending, by re-running pre-push, or by a rebase, and `reset`
# archives only a ledger that DECLARED ITSELF finished. Discarding a stop that
# nothing declared over takes `reset --force`, which names the stop it discarded
# on stdout. That sentence used to read "cannot be cleared" full stop, and was
# false the day it shipped: `reset` reused the budget's own precedence, under
# which every NONTERMINAL absorbing stop counts as "finished", so one plain
# `reset` cleared a regression and the next `budget` said "round 1 of 3 free".
# These do NOT compel anyone to run `budget`, `--ledger` behind
# ROUND_BUDGET_TEST_LEDGER still repoints the path, and the ledger is a plain
# file this agent can delete. This removes ACCIDENTAL drift — the miscounted
# round, the stop quietly walked back — which is what actually went wrong on the
# long arcs. SKILL.md states it in full.
#
# STRUCTURE. Every command that DECIDES on the history passes through one gate
# (`load_ledger`) -- `show` only renders and takes neither the gate nor the lock.
# The
# budget's precedence is one ordered list. Both are deliberate: three review
# rounds each found a guard living at one caller and not its sibling, or an
# ordering wrong in one of six sequential branches. One site is one place to be
# wrong.
#
# Usage:
#   round-budget.sh record-round   --run-id=ID --score=N/10 --defect=yes|no \
#                                  [--axes=a,b,c,d,e]  # 5 dims 0-2; a ZERO caps \
#                                                      # the stored score below the bar \
#                                  [--stratum=L:N/10:PASS|FAIL ...] \
#                                  [--fingerprints=a,b] [--settles=CONFIRMED|REFUTED] \
#                                  [--strata=A,B,C|unrecorded]
#
#   Every score carries its scale, and the scale must be the ledger's (/10).
#   A round scoring >= 7 must carry one --stratum per stratum that scored it,
#   each PASS, and the round score may not exceed the lowest of them.
#   --stratum and --strata are exclusive: with --stratum the panel is derived.
#   round-budget.sh record-verdict --run-id=ID --verdict=CONTINUE|STOP|STRUCTURAL \
#                                  [--prediction=TEXT] [--directive=TEXT]
#   round-budget.sh budget         --run-id=ID     # may another round run?
#   round-budget.sh show           --run-id=ID
#   round-budget.sh reset          --run-id=ID [--force]
#
# `reset` archives the ledger of an arc that DECLARED ITSELF finished — a
# recorded STOP/STRUCTURAL verdict, or a passing score carrying its verdicts. `--force` archives one
# that did not: a ledger sitting on a nonterminal stop, one at the round ceiling,
# or one that no longer parses. It applies to `reset` and to nothing else.
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
# The ledger's one scale (BRO-2615). A bare integer used to be accepted, and this
# same skill grades design docs on a /15 rubric that passes at 11: a 7/15 --
# a FAIL -- was recorded as `7` and came back PASSED over two strata that both
# said FAIL. A number without its unit is not a score, so the unit is required at
# every door and a foreign one is refused, never converted.
LEDGER_SCALE=10
# The anti-slop rubric's shape (BRO-2636): five dimensions at 2 points each.
# axes_are_valid asserts RUBRIC_AXES * RUBRIC_AXIS_MAX == LEDGER_SCALE, so these
# three cannot drift apart silently.
RUBRIC_AXES=5
RUBRIC_AXIS_MAX=2
# One producer for the "no panel was written down" token. It is written by the
# recorder, accepted by the validator, and rendered by `show`; spelling it at
# three sites is three places for them to disagree about what absence looks like.
STRATA_UNRECORDED=unrecorded

COMMAND="${1:-}"
[ -n "$COMMAND" ] || { echo "round-budget: no command. Try --help" >&2; exit 2; }
shift || true

case "$COMMAND" in
    --help|-h|help)
        # `\?` is a GNU extension: BSD sed reads it as a literal '?', so the pattern
        # never matched and --help printed every line with its leading '#' still on
        # it -- on the one platform this is developed on. `\{0,1\}` is POSIX BRE and
        # means the same thing to both.
        sed -n '/^# Usage:/,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
        exit 0 ;;
    record-round|record-verdict|budget|show|reset) ;;
    *) echo "round-budget: unknown command '$COMMAND'" >&2; exit 2 ;;
esac

RUN_ID=""; SCORE=""; DEFECT=""; FINGERPRINTS=""; SETTLES=""
VERDICT=""; PREDICTION=""; DIRECTIVE=""; LEDGER_PATH=""; RESET_FORCE=0
# STRATA_SET, not `-n "$STRATA"`. `--strata=` given with an empty value is a
# MALFORMED claim and must fail closed; the flag omitted entirely is no claim at
# all and records `unrecorded`. Keyed on the value alone the two are the same
# state, which is the distinction this whole field exists to keep.
STRATA=""; STRATA_SET=0
AXES=""
AXES_SET=0
# Per-stratum verdicts, `L:N/10:PASS|FAIL`, comma-joined across repeated flags.
STRATUM_VERDICTS=""; STRATUM_SET=0

for arg in "$@"; do
    case "$arg" in
        --run-id=*)       RUN_ID="${arg#*=}" ;;
        --score=*)        SCORE="${arg#*=}" ;;
        --defect=*)       DEFECT="${arg#*=}" ;;
        --fingerprints=*) FINGERPRINTS="${arg#*=}" ;;
        --settles=*)      SETTLES="${arg#*=}" ;;
        --strata=*)       STRATA="${arg#*=}"; STRATA_SET=1 ;;
        --axes=*)         AXES="${arg#*=}"; AXES_SET=1 ;;
        # Joined on STRATUM_SET, not on the value being non-empty: `--stratum=`
        # must survive as an empty ENTRY (and be refused) wherever it sits, not
        # vanish when it happens to come first.
        --stratum=*)      if [ "$STRATUM_SET" = "1" ]; then STRATUM_VERDICTS="$STRATUM_VERDICTS,${arg#*=}"
                          else STRATUM_VERDICTS="${arg#*=}"; fi; STRATUM_SET=1 ;;
        --verdict=*)      VERDICT="${arg#*=}" ;;
        --prediction=*)   PREDICTION="${arg#*=}" ;;
        --directive=*)    DIRECTIVE="${arg#*=}" ;;
        --force)          RESET_FORCE=1 ;;
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

# Parsed in the shared loop above, so `budget --force` and `record-round --force`
# were both accepted and both did nothing. A flag accepted where it has no
# meaning reads as a flag that had one.
if [ "$RESET_FORCE" = "1" ] && [ "$COMMAND" != "reset" ]; then
    echo "round-budget: --force applies to 'reset' only, not '$COMMAND'." >&2
    exit 2
fi

# Same reason, for the same class of mistake: `budget --strata=A,C` would
# otherwise report success having recorded nothing, and "I recorded the panel"
# vs "the panel went unrecorded" is exactly the pair this field must keep apart.
# The older value flags (--score, --defect, --settles) are NOT scoped this way;
# that is a pre-existing gap this does not close, not a convention being
# followed.
if [ "$STRATA_SET" = "1" ] && [ "$COMMAND" != "record-round" ]; then
    echo "round-budget: --strata applies to 'record-round' only, not '$COMMAND'." >&2
    exit 2
fi
if [ "$STRATUM_SET" = "1" ] && [ "$COMMAND" != "record-round" ]; then
    echo "round-budget: --stratum applies to 'record-round' only, not '$COMMAND'." >&2
    exit 2
fi
# Same scope as the panel flags: a flag accepted where it has no meaning reads
# as a flag that had one.
if [ "$AXES_SET" = "1" ] && [ "$COMMAND" != "record-round" ]; then
    echo "round-budget: --axes applies to 'record-round' only, not '$COMMAND'." >&2
    exit 2
fi

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

# One archiver, both callers. The corrupt path wrote `$LEDGER.archived.corrupt.$$`
# with no never-clobber loop while the healthy path four lines below it had one —
# and a pid is reused. "It archives rather than deletes" holds only if the
# archive it writes is not a previous archive.
ARCHIVE=""
archive_ledger() {
    local tag="${1:-}" base n=0 lines
    # The ledger may be UNREADABLE rather than merely unparsable -- a chmod 000,
    # a bad ACL -- and that is one of the cases --force exists to serve. Deriving
    # the name by READING it aborts the whole script under `set -e` before the
    # archive ever happens, so the one loud archiving path becomes no path at
    # all and the operator is left with `rm`. Linking needs write+search on the
    # DIRECTORY, not read on the file, so the archive is still available when
    # the count is not.
    # Braces around the redirect: `wc -l < f 2>/dev/null` silences WC, but the
    # "Permission denied" is bash's own, emitted before wc ever runs.
    lines=$( { wc -l < "$LEDGER"; } 2>/dev/null | tr -d ' ' ) || lines=""
    [ -n "$lines" ] || lines="unknown"
    base="$LEDGER.archived${tag:+.$tag}.$lines"
    ARCHIVE="$base"
    # Choosing a free name is the whole job, and the destination can be in more
    # states than "file or nothing". The whole space, enumerated, because fixing
    # these one at a time produced three rounds of adjacent-edge regressions
    # here:
    #
    #   absent            -> take it
    #   regular file      -> step aside
    #   DIRECTORY         -> step aside. `mv src dir` does not fail; it moves
    #                        INTO the directory. So does `ln`. The archive would
    #                        land at $ARCHIVE/<basename> while the message named
    #                        $ARCHIVE -- telling the operator where it went, and
    #                        telling them wrong.
    #   symlink, any kind -> step aside. `-e` FOLLOWS the link, so a dangling one
    #                        reads as absent; `-L` sees the entry itself.
    #   fifo/socket/dev   -> step aside (`-e`)
    #
    # This is a check-then-act, and it is not pretending otherwise: between the
    # test and the `mv`, something could take the name and the rename would
    # replace it. `reset` holds the per-ledger lock (`mkdir "$LEDGER.lock"`) for
    # its whole run, so no other round-budget can be that something; a foreign
    # writer in this directory can, and is the same class as "the ledger is a
    # plain file this agent can delete" in THE BOUNDARY.
    #
    # An `ln`-then-`rm` reservation closes that window and was tried here. It
    # cost more than it bought, and all three are reproduced in the tests or the
    # review: `ln` links INTO a directory rather than failing, so it cannot be
    # the only test; `rm -f "$LEDGER"` resolves the source name a SECOND time and
    # would delete a ledger installed there after the link -- archiving the old
    # budget while destroying the new one, exit 0; and it requires hard-link
    # support, which `mv` within one directory does not. `rename(2)` resolves
    # both names in one syscall, so it has no source race at all. The window it
    # leaves is the one the lock already covers.
    while [ -e "$ARCHIVE" ] || [ -L "$ARCHIVE" ]; do n=$((n+1)); ARCHIVE="$base.$n"; done
    mv "$LEDGER" "$ARCHIVE"
}

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

# The panel that produced a round's score. Same contract as the predicate above,
# and for the same reason: one definition, called at write AND at read, because
# a rule enforced only at the entry point is one a hand-edited row walks past.
#
# Accepted: a comma-separated set drawn from A, B, C -- or the literal
# `unrecorded`, which is the ONLY way to say the panel is unknown. Rejected:
# an empty value, an unknown letter, and a repeated one. `A,A` has the right
# shape and names no set, and a description that cannot be read back as a panel
# is garbage the ledger should refuse rather than store.
strata_is_valid() {
    local s="$1" n u
    if [ "$s" = "$STRATA_UNRECORDED" ]; then return 0; fi
    # Glob `case`, deliberately NOT `grep -qE`. grep matches LINE BY LINE, so
    # a value carrying a newline is checked one line at a time, the line reading
    # `A` would match, and the whole value would pass -- writing a RECORD
    # SEPARATOR into the field and splitting the row in two, which is the
    # injection `sanitize` exists to stop everywhere else. A glob matches the
    # whole string, newline included. The arms, in order: empty; a character
    # outside the alphabet (this is the one a newline hits); a leading, trailing
    # or doubled comma.
    # One arm per claim, on its own line, so each carries its own mutation
    # proof. Fused into a single alternation they were one anchor, and a
    # kill on any of them read as a kill on all three.
    case "$s" in
        '') return 1 ;;
        *[!ABC,]*) return 1 ;;
        ,*|*,|*,,*) return 1 ;;
    esac
    # `A,A` has the right shape and names no set. Fail closed rather than store
    # a panel description that cannot be read back as one.
    # printf '%s\n', not '%s': `wc -l` counts newlines, so an unterminated last
    # field would be counted by neither side and every set would look
    # duplicate-free.
    n=$(printf '%s\n' "$s" | tr ',' '\n' | wc -l | tr -d ' ')
    u=$(printf '%s\n' "$s" | tr ',' '\n' | sort -u | wc -l | tr -d ' ')
    [ "$n" = "$u" ]
}

# ─── Scores carry their scale (BRO-2615) ─────────────────────────────────
#
# One definition, called at write AND at read, like the two predicates above.
#
# The verdict is the EXIT STATUS, and only an explicit `return 0` at the end is
# a pass. The first version printed its reason and signalled "valid" by printing
# NOTHING -- so a predicate that crashed (`10#x` is a fatal arithmetic error)
# also printed nothing, and read as valid. Status-as-verdict makes a crash a
# refusal. Callers use `if ! reason=$(pred ...)`, never `[ -n "$reason" ]`.
#
# Checked, in order: a scale is present; the score is an integer; the scale is
# the ledger's; the score is inside it. One arm per line, one mutation per arm.
score_is_valid() {
    local v="$1" num den
    case "$v" in
        */*) ;;
        *) echo "'$v' carries no scale; write it as N/$LEDGER_SCALE"; return 1 ;;
    esac
    num=${v%%/*}; den=${v#*/}
    case "$num" in ''|*[!0-9]*) echo "'$v' has a non-integer score"; return 1 ;; esac
    # One spelling per value. `07` means 7 to `10#` and to awk, so it decided
    # nothing -- but a stored `A:07/10` is text no canonical reader expects,
    # and the recorder normalized --score while storing --stratum verbatim.
    case "$num" in 0?*) echo "'$v' has a leading zero; write it as ${num#"${num%%[!0]*}"}/$LEDGER_SCALE"; return 1 ;; esac
    # String equality, not arithmetic: it refuses a non-integer scale too, so a
    # separate integer check on the denominator could never be the one refusing.
    if [ "$den" != "$LEDGER_SCALE" ]; then
        echo "'$v' is on a /$den scale; this ledger is /$LEDGER_SCALE and does not convert"; return 1
    fi
    # Length first: bash arithmetic wraps silently at 2^64, so 18446744073709551621
    # evaluates to 5 and would compare as in range.
    if [ "${#num}" -gt 2 ] || [ "$((10#$num))" -gt "$LEDGER_SCALE" ]; then
        echo "'$v' is outside 0-$LEDGER_SCALE"; return 1
    fi
    return 0
}

# ─── The effective score (BRO-2636) ───────────────────────────────────────
#
# THE INVARIANT: a round whose rubric has a zeroed dimension cannot reach the
# bar, whatever its total. `2+2+2+2+0 = 8` must not pass while "tests cover the
# change" is unmet.
#
# This is expressed by DERIVING the score rather than by guarding the consumers.
# An earlier attempt added a floor beside each mechanism that reads a score, and
# the review found a fresh unguarded one every round -- PRECEDENCE, then the
# nodefect streak, then the --defect field, then the regressed compare. Four
# guards, four rounds, flat score. The mechanisms were never the problem; the
# score was, because a sum that contains a zero does not mean what every
# consumer assumes a score means.
#
# So the ledger stores the EFFECTIVE score, and there is exactly one place that
# computes it. Every consumer reads the score field and needs no floor of its
# own:
#
#   rule_passed            effective < PASS_SCORE, so it simply does not pass
#   regressed compare      compares effective to effective -- a floored 8 reads
#                          as 6, so the honest fix round at 7 is an IMPROVEMENT,
#                          not the regression it used to look like
#   stratum admissibility  effective < PASS_SCORE, so a FAIL stratum is legal
#                          and no per-stratum PASS is demanded
#   nodefect streak        the round was never a pass, so --defect=no is honest
#                          and the streak stays a real signal
#
# A CAP, not a zero. Zeroing would erase the ordering among floored rounds and
# make two different failures look identical; capping keeps every comparison
# below the bar meaningful. The cost is stated rather than hidden: among floored
# rounds ABOVE the bar the ordering collapses to the cap. That is deliberate --
# the claim is "cannot reach the bar", and it is the only claim this derivation
# makes.
#
# Concretely, the ONLY reachable collapse is raw 8 <-> raw 7, because a zero plus
# four axes capped at 2 tops out at 8. Its consequence, stated because it is not
# obvious: between two floored rounds the absorbing REGRESSION stop cannot fire,
# since both store the cap -- a fall from raw 8 to raw 7 with a zero on both
# reads as flat.
effective_score() {
    local raw="$1" axes="$2"
    if [ -z "$axes" ] || [ "$axes" = "-" ]; then printf '%s' "$raw"; return 0; fi
    case ",$axes," in
        *,0,*) ;;
        *) printf '%s' "$raw"; return 0 ;;
    esac
    if [ "$raw" -ge "$PASS_SCORE" ]; then printf '%s' "$((PASS_SCORE - 1))"; else printf '%s' "$raw"; fi
}

# The one place a written axis list becomes numbers. Returns the sum, or -1 if
# any entry is not a single digit -- LENGTH before arithmetic, because
# `$((10#$a))` WRAPS on a long digit run and 2^64 would otherwise sum as ZERO,
# satisfy the total check, and never be seen as a zero by the derivation.
axes_sum() (
    IFS=,; set -f
    total=0
    for a in $1; do
        case "$a" in ''|*[!0-9]*) printf '%s' -1; exit 0 ;; esac
        if [ "${#a}" -gt 1 ]; then printf '%s' -1; exit 0; fi
        total=$((total + 10#$a))
    done
    printf '%s' "$total"
)

# The rubric's five axes, as written (`a,b,c,d,e`), against the RAW total they
# must sum to. `-` means the round declared none and never reaches here.
#
# A subshell body for the same reason round_is_admissible is one: the IFS and
# noglob it sets cannot leak, and a fatal expansion exits non-zero as a refusal.
axes_are_valid() (
    axes="$1"; want="$2"
    if [ "$((RUBRIC_AXES * RUBRIC_AXIS_MAX))" != "$LEDGER_SCALE" ]; then
        echo "the rubric ($RUBRIC_AXES axes x $RUBRIC_AXIS_MAX) does not sum to the ledger scale /$LEDGER_SCALE"
        exit 1
    fi
    # A trailing comma drops silently under word splitting, exactly as it did for
    # the verdict list, so it is named before the count can be fooled by it.
    case "$axes" in
        *,) echo "'$axes' ends in an empty axis"; exit 1 ;;
    esac
    # THE DIGIT/LENGTH RULE LIVES IN axes_sum, AND ONLY THERE. This function used
    # to carry its own copy, and the two MASKED EACH OTHER: gutting either left
    # the other to refuse, so neither could be killed by a mutant and both read
    # as covered while neither was independently reachable. Two guards enforcing
    # one rule is one guard and one decoy.
    sum=$(axes_sum "$axes")
    if [ "$sum" -lt 0 ]; then
        echo "'$axes' contains an entry that is not a single digit 0-$RUBRIC_AXIS_MAX"; exit 1
    fi
    n=0
    IFS=,; set -f
    for a in $axes; do
        n=$((n + 1))
        # Range only. The digit class and the length are already settled by
        # axes_sum, so `10#$a` here is a single digit and cannot wrap.
        if [ "$((10#$a))" -gt "$RUBRIC_AXIS_MAX" ]; then
            echo "axis $n ('$a') is above the per-axis maximum of $RUBRIC_AXIS_MAX"; exit 1
        fi
    done
    if [ "$n" != "$RUBRIC_AXES" ]; then
        echo "'$axes' carries $n axes; the rubric has $RUBRIC_AXES"; exit 1
    fi
    # The arithmetic tie to the RAW total. Without it the axes are decoration:
    # any five values could sit beside any score and the derivation would be
    # computing from numbers that describe a different round.
    if [ "$sum" != "$want" ]; then
        echo "the axes '$axes' sum to $sum but the round's raw total is $want/$LEDGER_SCALE"; exit 1
    fi
    exit 0
)

# A whole ROUND row's score against the verdicts it claims to summarize. The
# recorder calls it on the row it is about to write; load_ledger calls it on
# every stored eight-field row. Args: the round score AS WRITTEN (`N/10`), the
# panel field, the verdicts field (`-` = none recorded).
#
#   - the round score carries the ledger's scale and lies inside it
#   - with no verdicts, the round cannot pass -- that is the whole of the rule
#     for a verdictless row
#   - every verdict entry is `L:N/10:PASS|FAIL`; the letters form a set from A,B,C
#   - a stratum cannot say PASS below the bar; it MAY say FAIL above it (a
#     reviewer who scored 7 and still blocked), and the FAIL is what counts
#   - the panel field is exactly the verdicts' letters
#   - the round score never exceeds the lowest stratum score
#   - a passing round score over any FAIL stratum is refused
#
# A subshell body, so the IFS / noglob it sets cannot leak on an early return,
# and so a fatal expansion inside it exits the SUBSHELL non-zero -- a refusal.
#
# No separate shape arms. An entry with too few or too many colons, an empty
# entry, or a newline all leave a scored half that score_is_valid refuses or a
# letter the set check refuses -- so each was a guard no input could reach, and
# three were written and deleted here for that reason.
round_is_admissible() (
    rscore="$1"; strata="$2"; verdicts="$3"; axes="${4:--}"
    if ! err=$(score_is_valid "$rscore"); then echo "round score: $err"; exit 1; fi
    score=$((10#${rscore%%/*}))
    # The stored score must BE the derived one. The row carries the axes, so the
    # derivation is reproducible from the row itself -- this is the same
    # one-predicate-two-callers shape the panel and the verdicts already use, so
    # a hand-edited row cannot claim a score its own axes do not produce.
    if [ "$axes" != "-" ]; then
        # ONE parse, because an earlier draft re-implemented the digit/length
        # walk here -- a second place to be wrong about what an axis is.
        #
        # Note what this does NOT buy: axes_are_valid's sum check IS tautological
        # on this path, and sharing the parse does not change that. It cannot be
        # otherwise -- the read door has no independently-declared total to check
        # against, so it derives one. The real read-door tie is the next check,
        # `score == effective(rawsum, axes)`; axes_are_valid is called here for
        # its SHAPE rules (count, range, length), not its arithmetic.
        rawsum=$(axes_sum "$axes")
        if [ "$rawsum" -lt 0 ]; then echo "rubric axes '$axes' are not $RUBRIC_AXES single digits"; exit 1; fi
        # axes_are_valid re-derives the same sum internally; passing rawsum makes
        # its arithmetic tie a no-op HERE by construction. That is fine and is
        # stated rather than dressed up: on this path it is called for its COUNT
        # and RANGE rules. The real read-door tie is the derivation check below.
        if ! err=$(axes_are_valid "$axes" "$rawsum"); then echo "rubric axes: $err"; exit 1; fi
        want=$(effective_score "$rawsum" "$axes")
        if [ "$score" != "$want" ]; then
            echo "round score $rscore is not the score its axes '$axes' derive ($want/$LEDGER_SCALE): a zeroed dimension caps the round below the $PASS_SCORE/$LEDGER_SCALE bar"
            exit 1
        fi
    fi
    if [ "$verdicts" = "-" ]; then
        if [ "$score" -ge "$PASS_SCORE" ]; then
            echo "round score $rscore would PASS with no per-stratum verdicts; a pass must carry one --stratum=L:N/$LEDGER_SCALE:PASS|FAIL per stratum that scored it"
            exit 1
        fi
        exit 0
    fi
    # A TRAILING comma only. Word splitting on IFS=, drops a trailing empty
    # field, so a stored `A:8/10:PASS,` validated as `A:8/10:PASS` while the
    # recorder refused the same text. A leading or doubled comma leaves an empty
    # entry INSIDE the list, which score_is_valid refuses, so those arms could
    # never decide and are not written.
    case "$verdicts" in
        *,) echo "the verdict list '$verdicts' ends in an empty entry"; exit 1 ;;
    esac
    letters=""; min=""; failed=0
    IFS=,; set -f
    for entry in $verdicts; do
        letter=${entry%%:*}; rest=${entry#*:}; verdict=${rest##*:}; scored=${rest%:*}
        # The letter on its own, BEFORE any set check. strata_is_valid answers a
        # different question -- "is this a PANEL?" -- and accepts the literal
        # `unrecorded` as a whole value, so reused here it passed
        # `unrecorded:9/10:PASS` as a stratum and `budget` said PASSED with no
        # A, B or C behind it (continuation review before round 4). An earlier
        # round deleted this arm as unreachable; it was reachable by that token.
        case "$letter" in
            A|B|C) ;;
            *) echo "stratum '$letter' is not one of A, B, C"; exit 1 ;;
        esac
        if ! err=$(score_is_valid "$scored"); then echo "stratum '$letter': $err"; exit 1; fi
        num=$((10#${scored%%/*}))
        case "$verdict" in
            PASS)
                if [ "$num" -lt "$PASS_SCORE" ]; then
                    echo "stratum $letter says PASS at $scored, below the $PASS_SCORE/$LEDGER_SCALE bar"; exit 1
                fi ;;
            FAIL) failed=1 ;;
            *) echo "stratum '$letter' carries verdict '$verdict'; want PASS or FAIL"; exit 1 ;;
        esac
        letters="${letters:+$letters,}$letter"
        if [ -z "$min" ] || [ "$num" -lt "$min" ]; then min=$num; fi
    done
    # Letters are already A|B|C each; what is left for the set check is REPEATS.
    if ! strata_is_valid "$letters"; then
        echo "the verdicts' strata '$letters' are not a set drawn from A, B, C"; exit 1
    fi
    if [ "$strata" != "$letters" ]; then
        echo "the panel field '$strata' disagrees with the verdicts' strata '$letters'"; exit 1
    fi
    if [ "$score" -gt "$min" ]; then
        echo "round score $rscore exceeds the lowest stratum ($min/$LEDGER_SCALE)"; exit 1
    fi
    if [ "$score" -ge "$PASS_SCORE" ] && [ "$failed" = "1" ]; then
        echo "round score $rscore would PASS over a stratum that said FAIL"; exit 1
    fi
    exit 0
)

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
# ROUND   n score defect fingerprints settles [strata] [verdicts] [axes]
#                                                       (6, 7, 8 or 9 fields)
# VERDICT verdict prediction directive                   (4 fields)
analyze() {
    read_rows | awk -F'\t' '
        BEGIN { rounds=0; prev=-1; last=-1; regressed=0
                ref=0; maxref=0; nod=0; maxnod=0
                terminal=""; directive=""; badscore=0; badverdict=""; badrow=0; pending=0
                badhistory=""; lastverified=0; prevkind=""; sawscaled=0; lastaxes="-" }
        $1=="ROUND" {
            # 6 OR 7. Field 7 (strata) is optional ON READ: every ledger
            # written before the field existed has six-field ROUND rows, and
            # refusing those would fail closed on arcs that are perfectly
            # valid -- a refusal that blocks real work is a regression, not
            # caution. Its VALUE is checked in load_ledger, against the same
            # predicate the recorder uses.
            #
            # The `!= 6` half is the honest statement of the shape and NOT an
            # independently reachable check: any NF<6 row leaves $6 empty, and
            # the settles arm below sets badrow on it first. The mutation that
            # would have proved a floor here survives for that reason, and
            # round-budget.mutation.sh records that rather than citing a kill
            # the input never reaches.
            # 8 = a round carrying per-stratum verdicts (BRO-2615); its
            # contents are checked in load_ledger by round_is_admissible.
            # 9 = a round that also declares its rubric axes (BRO-2636).
            if (NF != 6 && NF != 7 && NF != 8 && NF != 9) { badrow=1 }
            # NF==8 alone: an eight-field row at a passing score with no
            # verdicts (`-`) is refused outright by round_is_admissible, so a
            # `$8!="-"` half here could never be the check that decided.
            # NF>=8, deliberately, and the residual it leaves is named rather
            # than papered over.
            #
            # A nine-field row whose field 9 is DELETED is byte-identical to a
            # legitimate pre-BRO-2636 eight-field row, so no rule can tell them
            # apart, and the derivation check is skipped for it. `NF>=9` was
            # tried: it closes that forgery and breaks TEN existing assertions,
            # because it also stops every pre-existing eight-field ledger from
            # ever passing -- a refusal that blocks real work mid-arc, which this
            # doctrine in this file rates worse than the caution it buys.
            #
            # It is not worth its cost because the forgery buys nothing that is
            # not already available by a shorter route: an agent willing to edit
            # the ledger can simply omit `--axes` and take an unfloored pass,
            # which is disclosed in SKILL.md and announced by `budget` itself.
            # BLANKING field 9 is still refused (load_ledger), because a blank is
            # a shape no recorder ever writes and costs nothing to reject.
            lastverified=(NF>=8)
            lastaxes=(NF>=9 ? $9 : "-")
            rounds++
            # An eight-field row stores `N/10`. Its scale -- including a bare
            # integer where `N/10` belongs -- is checked in load_ledger by
            # round_is_admissible; only the numerator is compared here.
            sc=$3
            if (NF>=8) sub(/\/.*/, "", sc)   # >=8, not ==8: as `==` this left the /10 in the numeric compare -> badscore
            # Regression compares like with like. A pre-BRO-2615 row holds a
            # bare integer on an UNSTATED scale -- the incident row was a bare 7
            # that meant 7/15 -- so it is not comparable to a scaled one, and an
            # honest 6/10 after it must not read as a fall. Across the boundary
            # the comparison restarts; within either kind it holds as before.
            kind=(NF>=8) ? "scaled" : "bare"   # >=8, not ==8: as `==` this classified the row bare -> a false hand-edit error
            if (kind != prevkind) prev=-1
            prevkind=kind
            # ...and the boundary is crossed ONCE, bare -> scaled. The recorder
            # writes only scaled rows, so a bare row AFTER a scaled one is a
            # hand edit -- and without this it reset the comparison above and
            # turned a regression STOP into a PASS (review round 3).
            if (kind == "bare" && sawscaled) badhistory="a bare-integer round follows a scaled one; the recorder writes only N/10 rows"
            if (kind == "scaled") sawscaled=1
            if (sc !~ /^[0-9]+$/ || sc+0 > 10) { badscore=1 }
            else {
                if (prev >= 0 && sc+0 < prev) regressed=1
                prev=sc+0; last=sc+0
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
        END { print rounds"\t"last"\t"regressed"\t"maxref"\t"maxnod"\t"terminal"\t"badscore"\t"badverdict"\t"pending"\t"directive"\t"badrow"\t"badhistory"\t"lastverified"\t"lastaxes }'
}

# ─── The one gate ─────────────────────────────────────────────────────────
#
# Every command passes through here. Three review rounds each found a guard
# living at one caller and not its sibling — corrupt-check in `budget` but not
# the recorders, terminal-check in `record-round` but not `record-verdict`,
# prediction validation at write but not at read. One site makes that class of
# defect unrepresentable, and collapses four redundant `analyze` passes into one.
LG_N=""; LG_SCORE=""; LG_REGRESSED=""; LG_MAXREF=""; LG_MAXNOD=""
LG_TERMINAL=""; LG_PENDING=""; LG_DIRECTIVE=""; LG_LAST_VERIFIED=""; LG_LAST_AXES=""
# Snapshotted in load_ledger so the RULES never re-read the file. This bounds the
# inconsistency; it does not remove it. load_ledger itself still reads the ledger
# more than once (analyze, the tail, the CONTINUE rows) and `budget` takes no
# lock, so a concurrent append between those reads can still pair an old LG_N
# with a newer tail. Stated rather than implied: the recorders lock, the reader
# does not.
LG_LAST_TYPE=""; LG_LAST_VERDICT=""; LG_LAST_PRED=""

# The last row's standing. Two questions again, and rule_unusable_verdict is
# exactly the case where the first is true and the second is false — so the type
# check is load-bearing in every caller, including rule_earned: field 2 of a
# hand-written `ROUND` row is an unvalidated round number, and one reading
# `CONTINUE` would otherwise earn a round with no verdict at all.
# Spelling the CONTINUE test inline at both rules made ONE rule live at TWO
# sites, each individually deletable with the suite green. Redundancy no test can
# tell apart from correctness is not defence in depth; it is a second place to be
# wrong.
last_row_is_verdict()   { [ "$LG_LAST_TYPE" = "VERDICT" ]; }
verdict_earns_a_round() { [ "$LG_LAST_VERDICT" = "CONTINUE" ]; }
load_ledger() {
    local a
    # A NUL byte is not a character any recorder writes, and the readers do not
    # agree about it: BSD awk ends the record there and bash drops the byte, so
    # `A:8/10:PASS<NUL>,B:3/10:FAIL` validated as a lone PASS. Refused whole.
    if [ -f "$LEDGER" ] && [ -r "$LEDGER" ] && \
       [ "$(tr -d '\000' < "$LEDGER" | wc -c | tr -d ' ')" != "$(wc -c < "$LEDGER" | tr -d ' ')" ]; then
        echo "STOP — $LEDGER contains a NUL byte. No recorder writes one; refusing to read it."
        exit 6
    fi
    a="$(analyze)" || exit 6
    LG_N=$(printf '%s' "$a" | cut -f1)
    LG_SCORE=$(printf '%s' "$a" | cut -f2)
    LG_REGRESSED=$(printf '%s' "$a" | cut -f3)
    LG_MAXREF=$(printf '%s' "$a" | cut -f4)
    LG_MAXNOD=$(printf '%s' "$a" | cut -f5)
    LG_TERMINAL=$(printf '%s' "$a" | cut -f6)
    LG_PENDING=$(printf '%s' "$a" | cut -f9)
    LG_DIRECTIVE=$(printf '%s' "$a" | cut -f10)
    LG_LAST_VERIFIED=$(printf '%s' "$a" | cut -f13)
    LG_LAST_AXES=$(printf '%s' "$a" | cut -f14)
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
    local preds row vpred old_ifs stratarows srow vstrata
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

    # Field 7, against the SAME predicate the recorder applies -- the rule above
    # is enforced at read for exactly this reason. Rows carry an "S:" prefix so
    # an EMPTY field survives as a line rather than vanishing; a blank panel is
    # the value that must not slip through, because a reader would take it for
    # `unrecorded` while nothing wrote it.
    #
    # Only NF==7 rows are collected. A six-field row predates the field, carries
    # no claim about the panel, and has nothing here to validate.
    if ! stratarows=$(read_rows | awk -F'\t' '$1=="ROUND" && NF>=7 {print "S:" $7}'); then
        echo "STOP — could not read the ROUND rows of $LEDGER to validate them."
        exit 6
    fi
    old_ifs=$IFS
    IFS='
'
    set -f
    for srow in $stratarows; do
        vstrata=${srow#S:}
        if ! strata_is_valid "$vstrata"; then
            set +f; IFS=$old_ifs
            echo "STOP — a ROUND row in $LEDGER records a panel that would not pass"
            echo "  the recorder: '$vstrata'"
            echo "  Strata are a set drawn from A, B, C, or the literal"
            echo "  '$STRATA_UNRECORDED'. Anything else names no panel, and a panel"
            echo "  that cannot be read back cannot be told apart from none."
            exit 6
        fi
    done
    set +f
    IFS=$old_ifs

    # Field 9, the rubric axes, by the same "A:" prefix trick field 7 uses and
    # for the same reason: an EMPTY field survives as a line rather than
    # vanishing under word splitting.
    #
    # A BLANK field 9 is the value that must not slip through, and it is the
    # forgery this whole design would otherwise permit. The recorder ALWAYS
    # writes `-` when no axes were declared, so a blank one was written by
    # something else -- and because the read path reads an empty field 9 as
    # "absent", blanking it ERASES the derivation check. Restore the score to
    # its raw total, blank the axes, and a floored round reads as a pass. The
    # write door already refuses `--axes=` for the same reason; this is its
    # other half, and without it the stored-row contract is forgeable.
    local axrows axrow vaxes
    if ! axrows=$(read_rows | awk -F'\t' '$1=="ROUND" && NF>=9 {print "A:" $9}'); then
        echo "STOP — could not read the ROUND rows of $LEDGER to validate them."
        exit 6
    fi
    old_ifs=$IFS
    IFS='
'
    set -f
    for axrow in $axrows; do
        vaxes=${axrow#A:}
        if [ -z "$vaxes" ]; then
            set +f; IFS=$old_ifs
            echo "STOP — a ROUND row in $LEDGER carries a BLANK rubric-axes field."
            echo "  The recorder writes '-' when a round declares no axes, never a"
            echo "  blank, so nothing wrote this. A blank reads as 'no axes', which"
            echo "  would skip the check that the stored score is the one its axes"
            echo "  derive — the single thing this field exists to make unforgeable."
            exit 6
        fi
    done
    set +f
    IFS=$old_ifs

    # Field 8, the per-stratum verdicts, against the SAME predicate the recorder
    # applies. A hand-edited `A:7/15:PASS` is the incident this exists for.
    local vrows vrow verr
    if ! vrows=$(read_rows | awk -F'\t' '$1=="ROUND" && NF>=8'); then
        echo "STOP — could not read the ROUND rows of $LEDGER to validate them."
        exit 6
    fi
    old_ifs=$IFS
    IFS='
'
    set -f
    for vrow in $vrows; do
        if ! verr=$(round_is_admissible "$(field "$vrow" 3)" "$(field "$vrow" 7)" "$(field "$vrow" 8)" "$(field "$vrow" 9)"); then
            set +f; IFS=$old_ifs
            echo "STOP — a ROUND row in $LEDGER records verdicts the recorder would refuse:"
            echo "  ${verr:-the check failed without a reason; refusing rather than guessing}"
            echo "  A score is only comparable to the bar on the ledger's own scale, and"
            echo "  a round cannot claim more than the strata it summarizes."
            exit 6
        fi
    done
    set +f
    IFS=$old_ifs
}

# The ledger must not grow past its own terminal state. Both recorders, one site.
refuse_past_terminal() {
    # Was: "is a terminal VERDICT recorded?". That let the ledger grow past every
    # NONTERMINAL absorbing stop -- two no-defect rounds, a regression, two
    # refuted -- and a trailing passing round then read as "finished" to reset.
    # Now: whatever `budget` would say. One predicate, every caller.
    local entry code
    entry="$(first_rule)"
    [ -n "$entry" ] || return 0
    code=${entry##*:}
    arc_closed_code "$code" || return 0
    echo "round-budget: this arc is CLOSED — ${entry%%:*} (exit $code)." >&2
    echo "  Recording more does not clear it; run 'budget' for the full reason." >&2
    echo "" >&2
    echo "  If this arc is FINISHED and the branch is being reused, archive it:" >&2
    echo "    round-budget.sh reset --run-id=$RUN_ID" >&2
    exit 6
}

# ─── The decision, at module scope ───────────────────────────────────────
#
# Hoisted out of the `budget` arm so the RECORDERS and `reset` decide
# live-vs-finished from the SAME precedence. They each had their own notion
# before, which is how a ledger grew past its own absorbing stop and a
# trailing passing round then read as "finished" to reset. Same class as
# every other defect in this arc: one predicate, two implementations.
# ONE source of truth for both the ORDER and the EXIT CODE. Keeping names in
# a list and codes in a separate `case` wrote each rule in three places —
# list, function name, case arm — which could disagree.
PRECEDENCE="regressed:6 refuted:6 nodefect:6 terminal:6 passed:3 ceiling:7 free:0 unusable_verdict:6 review_required:5 earned:0"

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
# PASSED needs the verdicts it claims to summarize. A round row without them --
# every row written before BRO-2615 -- carries a bare integer on an unstated
# scale, which is exactly what passed a 7/15 as a 7/10. It is not read as a pass;
# the arc records one more round, with verdicts.
rule_passed() {
    [ "$LG_SCORE" -ge "$PASS_SCORE" ] || return 1
    [ "$LG_LAST_VERIFIED" = "1" ] || return 1
    echo "PASSED — last round scored $LG_SCORE (>= $PASS_SCORE). No further round needed."
    # A checked round and an unchecked one must not report the same thing. SKILL.md
    # claims the pass says when it was unfloored; without this it did not, and
    # only `show` carried the information.
    if [ -z "${LG_LAST_AXES:-}" ] || [ "$LG_LAST_AXES" = "-" ]; then
        echo "  NOTE: this round declared no rubric axes, so no per-axis cap was applied."
        echo "  A pass on the total alone cannot tell 2,2,2,1,1 from 2,2,2,2,0."
        echo "  Record the axes to get the cap: record-round ... --axes=a,b,c,d,e"
    fi
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
# Fires when the last row is a VERDICT that is neither terminal (handled
# above) nor CONTINUE — i.e. an empty or unrecognised token. It needs its own
# rule because a rule's exit code comes from PRECEDENCE: signalling this from
# inside rule_earned would have exited 0, which is the bug being fixed.
rule_unusable_verdict() {
    last_row_is_verdict || return 1
    ! verdict_earns_a_round || return 1
    echo "STOP — the last row is a VERDICT carrying an unusable token: '$LG_LAST_VERDICT'"
    echo "  Only CONTINUE earns a round. An EMPTY token is not a bad one to"
    echo "  analyze (absent, not invalid), so it reached the earned path and"
    echo "  bought a round. Admission is positive now: CONTINUE or nothing."
    return 0
}

rule_review_required() {
    ! last_row_is_verdict || return 1
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
    last_row_is_verdict || return 1
    # ...and it must be a CONTINUE. STOP/STRUCTURAL exit at rule_terminal, so
    # "it is a VERDICT row" LOOKED sufficient. It is not: an EMPTY token is
    # not a bad one -- analyze records badverdict=$2, and "" is absent rather
    # than invalid -- so `VERDICT\t\t\t` passed arity, set no terminal, set
    # no pending, was skipped by the CONTINUE-only re-validation, and bought
    # a round. The pre-hoist code caught it in an explicit default arm that
    # the comment sweep deleted along with the comment explaining why it
    # existed. Admission is now positive: only CONTINUE earns a round.
    verdict_earns_a_round || return 1
    echo "AUTHORIZED — round $((LG_N+1)), earned by a $LG_LAST_VERDICT verdict."
    echo "  Live prediction: $LG_LAST_PRED"
    echo "  The next recorded round MUST settle it (--settles=CONFIRMED|REFUTED)."
    return 0
}
# Each rule prints its own outcome and returns 0 when it fires. Exit codes
# are keyed off the rule name so the mapping is visible in one place.

# ─── Two questions, two predicates ───────────────────────────────────────
#
#   `budget` asks   "may another ROUND RUN?"
#   `reset`  asks   "may this LEDGER BE DISCARDED?"
#
# These were one function, and they are not the same question. Every NONTERMINAL
# absorbing stop — a regression, two REFUTED, two no-defect, an unusable verdict
# token — and the round-8 human ceiling all answer "no, another round may not
# run", so arc_closed_code reports every one of them as CLOSED. Read as "may this
# be discarded?" that is exactly backwards: those are the states whose remedy is
# ESCALATION, and one plain `reset` cleared each of them — no --force, no
# corruption — after which `budget` said "AUTHORIZED — round 1 of 3 free rounds".
#
# Five review rounds each fixed the input they were handed and opened the same
# hole one caller over, because each added a caller to a predicate answering a
# different question. So both are written down here, separately, once.

# May another ROUND RUN? Codes that mean the arc is over; anything else is live.
arc_closed_code() { case "$1" in 3|6|7) return 0 ;; *) return 1 ;; esac; }

# May this LEDGER BE DISCARDED? Strictly narrower, and deliberately not keyed on
# the exit code. The ledger must DECLARE ITSELF finished, which happens two ways
# and no third:
#
#   - a terminal verdict was recorded. Someone performed the act of ending the
#     arc; `refuse_past_terminal` then blocks every append, so it is the last
#     row too and its position adds nothing to check.
#   - the budget's own answer is PASSED. The arc ended by succeeding.
#
# The pass arm reads the RULE NAME, not `LG_SCORE >= PASS_SCORE`. That is what
# keeps the OLDER defect fixed: a passing round appended after a regression
# gives first_rule=regressed, so a trailing self-reported 9 cannot launder the
# stop it was appended past.
#
# A bare nonterminal stop and the ceiling are absent on purpose. Neither is a
# finished arc; each names a remedy — escalate, hand back, change the shape of
# the fix — and discarding the ledger performs none of them. They stay
# discardable through --force, which is a different sentence than a plain reset.
arc_declared_finished() {
    local rule="$1"
    if [ -n "$LG_TERMINAL" ]; then return 0; fi
    if [ "$rule" = "passed" ]; then return 0; fi
    return 1
}

# Name:code of the first firing rule, with the rule's own output suppressed.
first_rule() {
    local entry rule
    for entry in $PRECEDENCE; do
        rule=${entry%%:*}
        if ! declare -F "rule_$rule" >/dev/null 2>&1; then
            echo "round-budget: PRECEDENCE names '$rule' but rule_$rule does not exist." >&2
            exit 6
        fi
        if "rule_$rule" >/dev/null 2>&1; then printf '%s' "$entry"; return 0; fi
    done
    printf ''
}

decide_and_exit() {
    local entry rule code
    entry="$(first_rule)"
    if [ -z "$entry" ]; then
        echo "STOP — no precedence rule matched for $LEDGER; refusing to guess." >&2
        exit 6
    fi
    rule=${entry%%:*}; code=${entry##*:}
    "rule_$rule"          # re-run for its message
    # Say WHY a passing-looking score did not pass, rather than leave a pre-
    # BRO-2615 ledger reading "REVIEW-REQUIRED" or "AUTHORIZED" with no reason.
    # Only where another round CAN be recorded (0 authorized, 5 review first);
    # under a stop or the ceiling "record a round" is advice the recorder
    # refuses. No verified-row test: a passing score on a verified row IS
    # rule_passed (exit 3), so at 0/5 a score >= the bar is always unverified.
    case "$code" in
        0|5)
            if [ -n "$LG_SCORE" ] && [ "$LG_SCORE" -ge "$PASS_SCORE" ]; then
                echo "  Note: the last round scored $LG_SCORE with no per-stratum verdicts on"
                echo "  an unstated scale, so it is not read as a pass. The next round is"
                echo "  recorded as --score=N/$LEDGER_SCALE with one --stratum=L:N/$LEDGER_SCALE:PASS|FAIL per stratum."
            fi ;;
    esac
    exit "$code"
}

case "$COMMAND" in

record-round)
    with_lock
    load_ledger
    refuse_past_terminal
    [ -n "$SCORE" ]  || { echo "round-budget: --score=N/$LEDGER_SCALE required" >&2; exit 2; }
    if ! SCORE_ERR=$(score_is_valid "$SCORE"); then
        echo "round-budget: --score $SCORE_ERR." >&2
        echo "  The bar is $PASS_SCORE/$LEDGER_SCALE. A score from another rubric (the" >&2
        echo "  design-doc rubric is /15) does not belong in this ledger." >&2
        exit 2
    fi
    SCORE_INT=$((10#${SCORE%%/*}))
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

    # Which panel produced this score. Validated only when CLAIMED; omitted, it
    # records `unrecorded` EXPLICITLY. Writing an empty field instead would put
    # "nobody said" and "C alone" one indistinguishable blank apart, which is
    # the read this field is here to prevent -- and `-` is already spoken for by
    # `settles`, so absence would be spelled two ways in one row.
    if [ "$STRATUM_SET" = "1" ]; then
        if [ "$STRATA_SET" = "1" ]; then
            echo "round-budget: --strata and --stratum are exclusive; with --stratum the" >&2
            echo "  panel is derived from the verdicts, so it cannot disagree with them." >&2
            exit 2
        fi
        ROUND_STRATA=$(printf '%s\n' "$STRATUM_VERDICTS" | tr ',' '\n' | cut -d: -f1 | paste -sd, -)
        ROUND_VERDICTS="$STRATUM_VERDICTS"
    elif [ "$STRATA_SET" = "1" ]; then
        if ! strata_is_valid "$STRATA"; then
            echo "round-budget: --strata must be a comma-separated set drawn from" >&2
            echo "  A, B, C -- the strata that actually produced this score -- with no" >&2
            echo "  repeats, or the literal '$STRATA_UNRECORDED'. Got: '$STRATA'" >&2
            exit 2
        fi
        ROUND_STRATA="$STRATA"
    else
        ROUND_STRATA="$STRATA_UNRECORDED"
    fi
    if [ "$STRATUM_SET" != "1" ]; then ROUND_VERDICTS="-"; fi

    # Every row this recorder writes has eight fields and stores its score WITH
    # its scale, so no row written from here on is a bare integer. The row is
    # checked by the same predicate load_ledger applies to it later -- one site,
    # so the door and the stored artifact cannot disagree about what passes.
    # `-` when unset, so the stored row always has nine fields and the reader
    # never has to tell "absent" from "empty" by counting. Joined on AXES_SET,
    # not on the value being non-empty -- an explicit `--axes=` is a MALFORMED
    # flag, not a declaration of none, and the read path legitimately reads an
    # empty field 9 as absent, so the door must separate them.
    if [ "$AXES_SET" = "1" ]; then
        [ -n "$AXES" ] || {
            echo "round-budget: --axes= is empty; give $RUBRIC_AXES values 0-$RUBRIC_AXIS_MAX (e.g. --axes=2,2,2,1,1) or omit the flag" >&2
            exit 2; }
        # `-` is the LEDGER's sentinel for "declared none", not a value a caller
        # may write. Accepting it made a third spelling of absence reachable from
        # the CLI -- `--axes=` refused, `--axes=-` silently uncapped -- and two
        # spellings of one state is the thing this field exists to prevent.
        [ "$AXES" != "-" ] || {
            echo "round-budget: --axes=- is the ledger's own marker for 'no axes declared'; omit the flag instead" >&2
            exit 2; }
        ROUND_AXES="$AXES"
    else
        ROUND_AXES="-"
    fi

    # THE ONE DERIVATION SITE. --score is the reviewer's RAW total; what the
    # ledger stores is the effective score. Everything downstream reads the
    # stored field and needs no floor of its own.
    if [ "$ROUND_AXES" != "-" ]; then
        if ! AX_ERR=$(axes_are_valid "$ROUND_AXES" "$SCORE_INT"); then
            echo "round-budget: --axes $AX_ERR." >&2
            echo "  --score is the RAW total the five axes sum to; a zeroed dimension then caps" >&2
            echo "  the STORED score below the $PASS_SCORE/$LEDGER_SCALE bar." >&2
            exit 2
        fi
        EFFECTIVE=$(effective_score "$SCORE_INT" "$ROUND_AXES")
    else
        EFFECTIVE="$SCORE_INT"
    fi
    ROUND_SCORE="$EFFECTIVE/$LEDGER_SCALE"
    if ! VERDICT_ERR=$(round_is_admissible "$ROUND_SCORE" "$ROUND_STRATA" "$ROUND_VERDICTS" "$ROUND_AXES"); then
        echo "round-budget: refusing this round: ${VERDICT_ERR:-the check failed without a reason}." >&2
        exit 2
    fi

    N=$(( LG_N + 1 ))
    printf 'ROUND\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$N" "$ROUND_SCORE" "$DEFECT" "$(sanitize "$FINGERPRINTS")" "${SETTLES:--}" "$ROUND_STRATA" "$ROUND_VERDICTS" "$ROUND_AXES" >> "$LEDGER"
    echo "round-budget: recorded round $N (score $EFFECTIVE/$LEDGER_SCALE, defect=$DEFECT, settles=${SETTLES:--}, strata=$ROUND_STRATA, verdicts=$ROUND_VERDICTS, axes=$ROUND_AXES) -> $LEDGER"
    if [ "$ROUND_AXES" != "-" ] && [ "$EFFECTIVE" != "$SCORE_INT" ]; then
        echo "  A rubric axis is ZERO, so the raw total $SCORE_INT/$LEDGER_SCALE was CAPPED to $EFFECTIVE/$LEDGER_SCALE."
        echo "  A zeroed dimension cannot reach the $PASS_SCORE/$LEDGER_SCALE bar on the strength of the others."
    fi
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
    # deletes" is evidence after the fact, not a control.
    #
    # The gate is arc_declared_finished, NOT budget's arc_closed_code — see "Two
    # questions, two predicates". Everything it refuses is refused for one of two
    # reasons, and the reason decides whether --force applies:
    #
    #   CLOSED but not declared finished — a nonterminal stop, or the ceiling.
    #     --force. There is no in-band way out: refuse_past_terminal blocks the
    #     very verdict that would declare the arc over, so with no hatch here the
    #     only discard left is `rm` — the silent unlogged one this command exists
    #     to replace.
    #   LIVE — the budget authorizes, or asks for the continuation review.
    #     No hatch, and none is needed: record the arc's verdict and it is
    #     declared finished in band. --force does not open this.
    #
    # That ordering is the one the shipped version had backwards. An UNREADABLE
    # ledger, whose stop cannot even be read, demanded --force; a READABLE one
    # carrying a demonstrated regression demanded nothing.
    with_lock
    if [ ! -f "$LEDGER" ]; then
        echo "round-budget: no ledger at $LEDGER — nothing to reset."
        exit 0
    fi
    # A CORRUPT ledger is exactly the case reset must still serve: `budget` tells
    # the operator to "fix or discard it", and routing reset through the same
    # fail-closed gate left `rm` as the only discard -- turning the one loud,
    # archiving escape hatch into a silent unlogged deletion. So: corruption is
    # a reason to PERMIT the archive, not to refuse it.
    # Probed in a SUBSHELL: load_ledger exits rather than returning, so a bare
    # `if ! load_ledger` would take the whole script down with it.
    if ! ( load_ledger ) >/dev/null 2>&1; then
        # A corrupt ledger must stay discardable -- `budget` says "fix or discard
        # it", and refusing here would leave `rm` as the only discard, turning the
        # one loud archiving path into a silent deletion. But archiving it
        # AUTOMATICALLY made corruption a bypass of the live-arc gate: append one
        # junk line to a live ledger and the budget restarts. So the remedy stays
        # reachable and becomes DELIBERATE.
        if [ "$RESET_FORCE" != "1" ]; then
            echo "round-budget: $LEDGER does not parse." >&2
            echo "  Archiving it is the remedy, but discarding an unreadable ledger" >&2
            echo "  is a deliberate act: whatever budget it held cannot be read, so" >&2
            echo "  this cannot distinguish a finished arc from a live one that was" >&2
            echo "  corrupted. Re-run with --force to archive it anyway." >&2
            exit 6
        fi
        archive_ledger corrupt
        echo "round-budget: archived (forced, unreadable) -> $ARCHIVE"
        exit 0
    fi
    load_ledger
    RESET_ENTRY="$(first_rule)"
    RESET_RULE=${RESET_ENTRY%%:*}
    RESET_CODE=${RESET_ENTRY##*:}
    if [ -z "$RESET_ENTRY" ] || ! arc_declared_finished "$RESET_RULE"; then
        if [ -n "$RESET_ENTRY" ] && arc_closed_code "$RESET_CODE"; then
            if [ "$RESET_FORCE" != "1" ]; then
                echo "round-budget: refusing to reset a STOPPED arc." >&2
                echo "  budget says: $RESET_RULE (exit $RESET_CODE)." >&2
                echo "  That is a stop, not a finished arc, and nothing declared it" >&2
                echo "  over. Its remedy is the one the stop names — escalate, hand" >&2
                echo "  back, change the shape of the fix — and archiving the ledger" >&2
                echo "  performs none of them: budget never reads the archive, so the" >&2
                echo "  next round starts from round 1 as though the stop never was." >&2
                echo "  Discard it anyway with --force, which says so where it lands." >&2
                exit 6
            fi
            archive_ledger forced
            echo "round-budget: archived (FORCED past $RESET_RULE) -> $ARCHIVE"
            echo "  A stop was discarded without being acted on. The next round on"
            echo "  this arc id starts from round 1."
            exit 0
        fi
        echo "round-budget: refusing to reset a LIVE arc." >&2
        echo "  budget says: ${RESET_RULE:-none} (exit ${RESET_CODE:-none})." >&2
        echo "  reset retires an arc that DECLARED ITSELF finished — a recorded" >&2
        echo "  STOP/STRUCTURAL verdict, or a passing score with verdicts. --force does not open" >&2
        echo "  this one, because nothing here is blocked: a live arc has an in-band" >&2
        echo "  way to end. Record its verdict." >&2
        exit 6
    fi
    archive_ledger
    echo "round-budget: archived -> $ARCHIVE"
    echo "  The next round on this arc id starts from round 1."
    ;;

show)
    if [ ! -f "$LEDGER" ]; then echo "round-budget: no ledger at $LEDGER"; exit 0; fi
    echo "  Ledger: $LEDGER"
    echo ""
    # awk ends a record at a NUL, so the rows below would render whatever came
    # before it -- a lone PASS where the stored row also held a FAIL. `budget`
    # refuses such a ledger; `show` says so before rendering anything.
    if [ "$(tr -d '\000' < "$LEDGER" | wc -c | tr -d ' ')" != "$(wc -c < "$LEDGER" | tr -d ' ')" ]; then
        echo "  MALFORMED: this ledger contains a NUL byte; rows below may be truncated"
        echo "  and budget refuses it."
        echo ""
    fi
    # `unrec` is passed in rather than spelled here: one producer for the token,
    # or `show` and the recorder could disagree about what absence is called.
    #
    # THREE states, not two. An earlier version rendered a six-field row and a
    # seven-field row with a BLANK field as the same `unrecorded`, which
    # contradicted `load_ledger` forty lines up: a blank panel is the one value
    # that must not slip through, and the gate exits 6 on it. `show` takes no
    # gate, so it was the surface where a refused ledger rendered as a clean row
    # naming no defect -- the operator whose `budget` just said "does not parse"
    # ran `show` to find out why and was told the panel was merely unrecorded.
    # That laundered a fail-closed condition into a legitimate value, which is
    # the same absence-as-value defect this whole field exists to remove.
    #
    #   NF<7            -> pre-strata row, a real and legitimate absence
    #   NF>=7, non-blank-> the recorded panel (validity is the gate's job)
    #   NF>=7, blank    -> MALFORMED: nothing wrote it, and it must not read
    #                      like something that did
    awk -F'\t' -v unrec="$STRATA_UNRECORDED" '
        $1=="ROUND"   { printf "  round %-3s score %-5s defect=%-4s settles=%-10s strata=%-12s %s%s%s\n", \
                               $2,$3,$4,$6,(NF<7 ? unrec : ($7!="" ? $7 : "MALFORMED")),$5, \
                               (NF>=8 ? "  [verdicts: " ($8=="-" ? "none" : ($8=="" ? "MALFORMED" : $8)) "]" : ""), \
                               (NF>=9 ? "  [axes: " ($9=="-" ? "none" : ($9=="" ? "MALFORMED" : $9)) "]" : "") }
        $1=="VERDICT" { printf "  verdict %-11s %s%s\n", $2, $3, ($4!="" ? "  [directive: " $4 "]" : "") }
    ' "$LEDGER"
    ;;

budget)
    load_ledger

    # The empty-ledger case was hand-rolled here, above the precedence that
    # already decides it: with zero rounds, rule_terminal fires on a recorded
    # verdict (exit 6) and rule_free on everything else (exit 0, "round 1 of 3"),
    # in that order, with those codes. Two decision sites survived a refactor
    # whose entire thesis was one, so the copy is deleted rather than kept in
    # sync with a precedence it duplicated.
    #
    # ─── Precedence, as data ──────────────────────────────────────────────
    #
    # Ordering encoded ONCE, in this list, rather than in six sequential `if`
    # blocks. Two of the three review rounds landed on ordering defects — a
    # ceiling checked in the wrong place, then PASSED checked above the stops —
    # and six branches are six places to get the order wrong.
    #
    # Stops come before PASSED because the score is the agent's OWN SELF-REPORT:
    # if a pass outranked a stop, every stop would cost one integer to escape.
    decide_and_exit
    ;;
esac
