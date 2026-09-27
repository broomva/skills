#!/usr/bin/env bash
# tests/round-budget.test.sh — the P20 dynamic round budget
#
# The FIRST test here is the null control, and it is the one that matters. A
# continuation reflex asked "should I extend?" answers YES almost always; a
# second model rubber-stamping that is worse than the fixed counter it replaces,
# because it launders the writer's appetite through something that looks
# independent. So: feed it a ledger where nothing is happening and assert it
# does not authorize.
#
# T2 is the control for T1. A gate that ALWAYS refuses passes a null test
# vacuously — "missing polarity self-certifies". T2 proves the gate can say yes,
# which is what makes T1's no meaningful.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RB="$REPO/scripts/round-budget.sh"

# --ledger is gated so it cannot serve as a production budget-reset. The
# tests are its intended consumer, so they opt in explicitly.
export ROUND_BUDGET_TEST_LEDGER=1

PASS=0; FAIL=0; FAILED=()
ok()   { PASS=$((PASS+1)); echo "  [pass] $1"; }
fail() { FAIL=$((FAIL+1)); FAILED+=("$1"); echo "  [FAIL] $1"; [ -n "${2:-}" ] && echo "         $2"; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
# Named per test, NOT a counter. A counter incremented inside a command
# substitution never reaches the parent shell, so every test silently shared one
# ledger and the rows accumulated across them. Five tests failed on that alone --
# bad fixtures, not missing checks.
newledger() { echo "$TMP/ledger.$1.tsv"; }

# "It archives rather than deletes" is the whole claim of `reset`, so a positive
# arm that checks only the exit code -- or only that the original is gone --
# passes a --force that reported success and did nothing, and passes one that
# simply deleted the ledger. Count what actually landed.
# `-type f` because a DIRECTORY or a symlink sitting at an archive name is
# exactly what T53/T54 put there on purpose. Counting those as archives would
# let "the archive landed" be satisfied by the obstacle it was supposed to step
# around.
archives_of() { find "$(dirname "$1")" -maxdepth 1 -type f -name "$(basename "$1").archived.*" 2>/dev/null | wc -l | tr -d ' '; }

# Run round-budget, capture exit code without tripping the outer pipefail.
rb() { local rc=0; bash "$RB" "$@" >/dev/null 2>&1 || rc=$?; echo "$rc"; }
rbout() { bash "$RB" "$@" 2>&1 || true; }

echo "── tests/round-budget.test.sh ────────────────────────────────"
echo ""

# ── T1: NULL CONTROL — a dead arc must stop, and stop FOR THE RIGHT REASON ──
#
# The first version of this test was not a null control and two independent
# reviewers said so with the same proof: it asserted "3 rounds with no fresh
# verdict -> exit 5", which an equally ALIVE ledger (rising score, a defect every
# round) also returns. It measured the round counter, not liveness. It could not
# have measured liveness, because --defect was recorded and read by nothing.
#
# Now --defect is load-bearing, so the null control is real: rounds that
# reproduce nothing STOP, and the arm below distinguishes them from rounds that
# reproduce something at the same score.
echo "T1. null control: rounds that reproduce NO defect stop the arc"
LED=$(newledger t1)
bash "$RB" record-round --run-id=null --ledger="$LED" --score=5 --defect=no >/dev/null
bash "$RB" record-round --run-id=null --ledger="$LED" --score=5 --defect=no >/dev/null
RC=$(rb budget --run-id=null --ledger="$LED")
OUT=$(rbout budget --run-id=null --ledger="$LED")
if [ "$RC" = "6" ] && echo "$OUT" | grep -q "reproduced NO defect"; then
    ok "T1: dead arc STOPs, and names liveness as the reason"
else
    fail "T1: dead arc STOPs, and names liveness as the reason" "exit $RC: $OUT"
fi

# ── T2: POLARITY CONTROL for T1 — same scores, but the rounds are alive ──────
# Identical score series, identical round count, identical everything except
# --defect. If this also stopped, T1 would be measuring the counter again.
echo "T2. polarity control: same flat score, but defects reproduced -> not stopped"
LED=$(newledger t2)
bash "$RB" record-round --run-id=live --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-round --run-id=live --ledger="$LED" --score=5 --defect=yes >/dev/null
RC=$(rb budget --run-id=live --ledger="$LED")
if [ "$RC" = "0" ]; then
    ok "T2: live arc still authorized — T1 discriminates on liveness, not count"
else
    fail "T2: live arc still authorized" "exit $RC — T1 may be measuring the round counter again"
fi

# ── T3: rounds 1-3 are free ───────────────────────────────────────────────
echo "T3. first three rounds need no continuation review"
LED=$(newledger t3)
RC=$(rb budget --run-id=free --ledger="$LED")
if [ "$RC" = "0" ]; then ok "T3a: round 1 free"; else fail "T3a: round 1 free" "exit $RC"; fi
bash "$RB" record-round --run-id=free --ledger="$LED" --score=4 --defect=yes >/dev/null
RC=$(rb budget --run-id=free --ledger="$LED")
if [ "$RC" = "0" ]; then ok "T3b: round 2 free"; else fail "T3b: round 2 free" "exit $RC"; fi
bash "$RB" record-round --run-id=free --ledger="$LED" --score=4 --defect=yes >/dev/null
RC=$(rb budget --run-id=free --ledger="$LED")
if [ "$RC" = "0" ]; then ok "T3c: round 3 free"; else fail "T3c: round 3 free" "exit $RC"; fi

# ── T4: round 4 requires a continuation verdict (exit 5) ──────────────────
echo "T4. round 4 requires a continuation review"
bash "$RB" record-round --run-id=free --ledger="$LED" --score=4 --defect=yes >/dev/null
RC=$(rb budget --run-id=free --ledger="$LED")
if [ "$RC" = "5" ]; then ok "T4: REVIEW-REQUIRED at round 4"; else fail "T4: REVIEW-REQUIRED at round 4" "exit $RC, want 5"; fi

# ── T5: score regression stops immediately ────────────────────────────────
echo "T5. score regression -> STOP"
LED=$(newledger t4)
bash "$RB" record-round --run-id=reg --ledger="$LED" --score=6 --defect=yes >/dev/null
bash "$RB" record-round --run-id=reg --ledger="$LED" --score=5 --defect=yes >/dev/null
RC=$(rb budget --run-id=reg --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T5: STOP on regression (6->5)"; else fail "T5: STOP on regression" "exit $RC, want 6"; fi

# ── T6: two refuted predictions -> STOP, even under a live CONTINUE ───────
echo "T6. two consecutive REFUTED predictions -> STOP"
LED=$(newledger t5)
bash "$RB" record-round --run-id=ref --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-verdict --run-id=ref --ledger="$LED" --verdict=CONTINUE --prediction="empty-input branch in parse_args at scripts/foo.sh:88" >/dev/null
bash "$RB" record-round --run-id=ref --ledger="$LED" --score=5 --defect=yes --settles=REFUTED >/dev/null
bash "$RB" record-verdict --run-id=ref --ledger="$LED" --verdict=CONTINUE --prediction="unquoted expansion in emit() at scripts/bar.sh:12" >/dev/null
bash "$RB" record-round --run-id=ref --ledger="$LED" --score=5 --defect=yes --settles=REFUTED >/dev/null
bash "$RB" record-verdict --run-id=ref --ledger="$LED" --verdict=CONTINUE --prediction="off-by-one in the retry loop at scripts/baz.sh:41" >/dev/null
RC=$(rb budget --run-id=ref --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T6: STOP after two REFUTED"; else fail "T6: STOP after two REFUTED" "exit $RC, want 6 — a live CONTINUE must not override it"; fi

# ── T7: the human ceiling overrides any verdict ───────────────────────────
echo "T7. round ceiling -> HUMAN, whatever the verdict says"
LED=$(newledger t6)
bash "$RB" record-round --run-id=ceil --ledger="$LED" --score=5 --defect=yes >/dev/null
for i in 2 3 4 5 6 7 8; do
    bash "$RB" record-verdict --run-id=ceil --ledger="$LED" --verdict=CONTINUE --prediction="defect class $i at scripts/loop.sh:$i" >/dev/null
    bash "$RB" record-round --run-id=ceil --ledger="$LED" --score=5 --defect=yes --settles=CONFIRMED >/dev/null
done
bash "$RB" record-verdict --run-id=ceil --ledger="$LED" --verdict=CONTINUE --prediction="p9" >/dev/null
RC=$(rb budget --run-id=ceil --ledger="$LED")
if [ "$RC" = "7" ]; then ok "T7: HUMAN at the ceiling"; else fail "T7: HUMAN at the ceiling" "exit $RC, want 7 — a CONTINUE verdict must not buy round 9"; fi

# ── T8: anti-vacuity rule 1 — CONTINUE without a prediction is refused ────
echo "T8. CONTINUE requires a prediction"
LED=$(newledger t7)
RC=$(rb record-verdict --run-id=v1 --ledger="$LED" --verdict=CONTINUE)
if [ "$RC" = "2" ]; then ok "T8a: bare CONTINUE refused"; else fail "T8a: bare CONTINUE refused" "exit $RC, want 2"; fi
RC=$(rb record-verdict --run-id=v1 --ledger="$LED" --verdict=CONTINUE --prediction="   ")
if [ "$RC" = "2" ]; then ok "T8b: whitespace-only prediction refused"; else fail "T8b: whitespace-only prediction refused" "exit $RC, want 2"; fi

# ── T9: anti-vacuity rule 2 — a round after CONTINUE must settle it ───────
echo "T9. a round following CONTINUE must settle the prediction"
LED=$(newledger t8)
bash "$RB" record-round --run-id=s1 --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-verdict --run-id=s1 --ledger="$LED" --verdict=CONTINUE --prediction="missing null guard at scripts/qux.sh:7" >/dev/null
RC=$(rb record-round --run-id=s1 --ledger="$LED" --score=5 --defect=yes)
if [ "$RC" = "2" ]; then ok "T9: unsettled round refused"; else fail "T9: unsettled round refused" "exit $RC, want 2 — else the two-refuted stop is unreachable"; fi

# ── T10: anti-vacuity rule 4 — CONTINUE verdicts cannot stack ─────────────
echo "T10. CONTINUE verdicts cannot stack without an intervening round"
LED=$(newledger t9)
bash "$RB" record-round --run-id=st --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-verdict --run-id=st --ledger="$LED" --verdict=CONTINUE --prediction="empty-input branch in parse_args at scripts/foo.sh:88" >/dev/null
RC=$(rb record-verdict --run-id=st --ledger="$LED" --verdict=CONTINUE --prediction="unquoted expansion in emit() at scripts/bar.sh:12")
if [ "$RC" = "2" ]; then ok "T10: stacked CONTINUE refused"; else fail "T10: stacked CONTINUE refused" "exit $RC, want 2"; fi

# ── T11: STRUCTURAL is a stop, and carries its directive ──────────────────
echo "T11. STRUCTURAL stops the fix loop and names the directive"
LED=$(newledger t10)
for i in 1 2 3 4; do bash "$RB" record-round --run-id=str --ledger="$LED" --score=5 --defect=yes >/dev/null; done
bash "$RB" record-verdict --run-id=str --ledger="$LED" --verdict=STRUCTURAL --directive="hoist the invariant out of the alternation" >/dev/null
RC=$(rb budget --run-id=str --ledger="$LED")
OUT=$(rbout budget --run-id=str --ledger="$LED")
if [ "$RC" = "6" ] && echo "$OUT" | grep -q "hoist the invariant"; then
    ok "T11: STRUCTURAL stops and surfaces the directive"
else
    fail "T11: STRUCTURAL stops and surfaces the directive" "exit $RC: $OUT"
fi

# ── T12: a passing score ends the loop ────────────────────────────────────
echo "T12. score >= 7 ends the loop"
LED=$(newledger t11)
bash "$RB" record-round --run-id=p --ledger="$LED" --score=8 --defect=no >/dev/null
RC=$(rb budget --run-id=p --ledger="$LED")
if [ "$RC" = "3" ]; then ok "T12: PASSED"; else fail "T12: PASSED" "exit $RC, want 3"; fi

# ── T13: a stale verdict cannot authorize twice ───────────────────────────
# The verdict must be the MOST RECENT row. One already settled by a later round
# has spent its authority; reusing it is how a single CONTINUE buys three rounds.
echo "T13. a verdict already settled by a later round cannot re-authorize"
LED=$(newledger t12)
for i in 1 2 3; do bash "$RB" record-round --run-id=stale --ledger="$LED" --score=5 --defect=yes >/dev/null; done
bash "$RB" record-verdict --run-id=stale --ledger="$LED" --verdict=CONTINUE --prediction="empty-input branch in parse_args at scripts/foo.sh:88" >/dev/null
bash "$RB" record-round --run-id=stale --ledger="$LED" --score=5 --defect=yes --settles=CONFIRMED >/dev/null
RC=$(rb budget --run-id=stale --ledger="$LED")
if [ "$RC" = "5" ]; then ok "T13: spent verdict does not re-authorize"; else fail "T13: spent verdict does not re-authorize" "exit $RC, want 5"; fi

# ── T14: field separators cannot be smuggled through a prediction ─────────
echo "T14. tabs in a prediction cannot shift the ledger columns"
LED=$(newledger t13)
bash "$RB" record-round --run-id=inj --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-verdict --run-id=inj --ledger="$LED" --verdict=CONTINUE \
    --prediction="$(printf 'evil\tREFUTED\tinjected at scripts/evil.sh:1')" >/dev/null
LINES=$(grep -c . "$LED")
COLS=$(tail -1 "$LED" | awk -F'\t' '{print NF}')
if [ "$LINES" = "2" ] && [ "$COLS" = "4" ]; then
    ok "T14: tab-bearing prediction stays in one field"
else
    fail "T14: tab-bearing prediction stays in one field" "lines=$LINES cols=$COLS (want 2 and 4)"
fi

# ── T15: an unreadable ledger must not fail OPEN ──────────────────────────
# Zero rows reads as "no rounds yet", which authorizes. An existing-but-
# unreadable ledger must therefore be an error, never an empty history.
echo "T15. unreadable ledger does not authorize"
LED=$(newledger t15)
bash "$RB" record-round --run-id=unread --ledger="$LED" --score=5 --defect=yes >/dev/null
chmod 000 "$LED"
if [ -r "$LED" ]; then
    # running as root, or a filesystem that ignores the mode bits
    ok "T15: skipped (ledger still readable after chmod 000)"
else
    RC=$(rb budget --run-id=unread --ledger="$LED")
    if [ "$RC" != "0" ]; then
        ok "T15: unreadable ledger does not authorize (exit $RC)"
    else
        fail "T15: unreadable ledger does not authorize" "got AUTHORIZED — fail-open on an unreadable ledger"
    fi
fi
chmod 644 "$LED" 2>/dev/null || true

# ─── Absorbing stops. Every one of these was escapable by appending a row. ───

# ── T19: STOP is honoured DURING the free rounds ──────────────────────────
# The free-round fast path used to return AUTHORIZED before ever looking at a
# recorded verdict, so "STOP, no override" was false for rounds 1-3 -- exactly
# the window where an arc is most likely to be told to stop.
echo "T19. a STOP verdict is honoured inside the free rounds"
LED=$(newledger t19)
bash "$RB" record-round  --run-id=t19 --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-verdict --run-id=t19 --ledger="$LED" --verdict=STOP >/dev/null
RC=$(rb budget --run-id=t19 --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T19: STOP beats the free-round path"; else fail "T19: STOP beats the free-round path" "exit $RC, want 6"; fi

# ── T20: a STOP cannot be cleared by appending ────────────────────────────
echo "T20. appending after STOP does not clear it"
bash "$RB" record-verdict --run-id=t19 --ledger="$LED" --verdict=CONTINUE \
    --prediction="another look at scripts/again.sh:5" >/dev/null 2>&1 || true
bash "$RB" record-round --run-id=t19 --ledger="$LED" --score=5 --defect=yes --settles=CONFIRMED >/dev/null 2>&1 || true
RC=$(rb budget --run-id=t19 --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T20: STOP is absorbing"; else fail "T20: STOP is absorbing" "exit $RC, want 6 — a stop you can append your way out of is not a stop"; fi

# ── T21: two REFUTED is absorbing too ─────────────────────────────────────
echo "T21. a later CONFIRMED does not clear two REFUTED"
LED=$(newledger t21)
bash "$RB" record-round  --run-id=t21 --ledger="$LED" --score=5 --defect=yes >/dev/null
for pr in "a at scripts/a.sh:1" "b at scripts/b.sh:2"; do
    bash "$RB" record-verdict --run-id=t21 --ledger="$LED" --verdict=CONTINUE --prediction="$pr" >/dev/null
    bash "$RB" record-round  --run-id=t21 --ledger="$LED" --score=5 --defect=yes --settles=REFUTED >/dev/null
done
bash "$RB" record-verdict --run-id=t21 --ledger="$LED" --verdict=CONTINUE --prediction="c at scripts/c.sh:3" >/dev/null 2>&1 || true
bash "$RB" record-round --run-id=t21 --ledger="$LED" --score=5 --defect=yes --settles=CONFIRMED >/dev/null 2>&1 || true
RC=$(rb budget --run-id=t21 --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T21: two-REFUTED is absorbing"; else fail "T21: two-REFUTED is absorbing" "exit $RC, want 6"; fi

# ── T22: an unknown verdict token must not read as AUTHORIZED ─────────────
# The verdict dispatch was a three-arm `case` with no default: an unrecognised
# token fell off the end and the script's last status was 0, in silence.
echo "T22. an unrecognised verdict token fails closed"
LED=$(newledger t22)
for i in 1 2 3; do bash "$RB" record-round --run-id=t22 --ledger="$LED" --score=5 --defect=yes >/dev/null; done
printf 'VERDICT\tcontinue\tlowercase is not a token\t\n' >> "$LED"
RC=$(rb budget --run-id=t22 --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T22: unknown verdict -> STOP"; else fail "T22: unknown verdict -> STOP" "exit $RC, want 6 — silent AUTHORIZED is the worst failure here"; fi

# ── T23: a malformed score must not fall through to AUTHORIZED ────────────
echo "T23. a non-integer score fails closed"
LED=$(newledger t23)
printf 'ROUND\t1\tten\tyes\t\t-\n' > "$LED"
RC=$(rb budget --run-id=t23 --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T23: corrupt score -> STOP"; else fail "T23: corrupt score -> STOP" "exit $RC, want 6"; fi

# ── T24: STRUCTURAL without a directive is a stop with no instruction ─────
echo "T24. STRUCTURAL requires --directive"
LED=$(newledger t24)
RC=$(rb record-verdict --run-id=t24 --ledger="$LED" --verdict=STRUCTURAL)
if [ "$RC" = "2" ]; then ok "T24: bare STRUCTURAL refused"; else fail "T24: bare STRUCTURAL refused" "exit $RC, want 2"; fi

# ── T25: a prediction must name WHERE to look ─────────────────────────────
echo "T25. a prediction with no location is refused"
LED=$(newledger t25)
RC=$(rb record-verdict --run-id=t25 --ledger="$LED" --verdict=CONTINUE --prediction="one more round should do it")
if [ "$RC" = "2" ]; then ok "T25: locationless prediction refused"; else fail "T25: locationless prediction refused" "exit $RC, want 2 — non-emptiness alone let --prediction=x buy a round"; fi

# ── T26: --ledger is gated so it cannot reset a budget in production ──────
echo "T26. --ledger requires the test opt-in"
LED=$(newledger t26)
RC=$(env -u ROUND_BUDGET_TEST_LEDGER bash "$RB" budget --run-id=t26 --ledger="$LED" >/dev/null 2>&1; echo $?)
if [ "$RC" = "2" ]; then ok "T26: --ledger gated"; else fail "T26: --ledger gated" "exit $RC, want 2 — a fresh path is the cheapest budget reset"; fi

# ── T27: a prediction must also carry enough SUBSTANCE to settle ──────────
# The rule has two arms -- length and location -- and a mutation of the length
# arm alone survived, because the location arm still rejected T25's input. Each
# arm needs its own case, or half the rule is untested.
echo "T27. a located but contentless prediction is refused"
LED=$(newledger t27)
RC=$(rb record-verdict --run-id=t27 --ledger="$LED" --verdict=CONTINUE --prediction="a.sh:1")
if [ "$RC" = "2" ]; then ok "T27: too-short prediction refused"; else fail "T27: too-short prediction refused" "exit $RC, want 2"; fi

# ── T28: rows must have the right ARITY ───────────────────────────────────
# A short ROUND row leaves $6 empty, which silently skips the REFUTED
# accounting -- the two-refuted stop would then be unreachable on a hand-edited
# ledger. A long row means something wrote a separator into a value.
echo "T28. wrong-arity rows fail closed"
LED=$(newledger t28)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\tCONTINUE\tat a.sh:1 a real prediction\t\t\t\n' > "$LED"
RC=$(rb budget --run-id=t28 --ledger="$LED")
LED2=$(newledger t28b)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\tCONTINUE\tat a.sh:1 a real prediction\t\n' > "$LED2"
RC2=$(rb budget --run-id=t28b --ledger="$LED2")
if [ "$RC" = "6" ] && [ "$RC2" = "0" ]; then
    ok "T28: extra-field row STOPs, well-formed row still authorizes"
else
    fail "T28: arity" "extra-field exit=$RC (want 6), well-formed exit=$RC2 (want 0)"
fi

# ── T29: a CONTINUE row must satisfy the rule at READ time too ────────────
# Rule 1 was enforced only in record-verdict, so a row that never passed the
# recorder still bought a round. Validating at the entry point but not against
# the stored artifact is the same shape as computing a stop from the TAIL.
echo "T29. a crafted CONTINUE row with no location does not authorize"
LED=$(newledger t29)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\tCONTINUE\tone more round should do it\t\n' > "$LED"
RC=$(rb budget --run-id=t29 --ledger="$LED")
LED2=$(newledger t29b)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\tCONTINUE\tempty-input branch at scripts/foo.sh:88\t\n' > "$LED2"
RC2=$(rb budget --run-id=t29b --ledger="$LED2")
if [ "$RC" = "6" ] && [ "$RC2" = "0" ]; then
    ok "T29: vacuous CONTINUE row STOPs, located one still authorizes"
else
    fail "T29: read-time prediction check" "vacuous exit=$RC (want 6), located exit=$RC2 (want 0)"
fi

# ── T30: the recorder must not append to a corrupt ledger ─────────────────
# Fail-closed landed in budget and nowhere else, so record-* grew a history that
# no decision could rest on.
echo "T30. record-* refuses to append to a corrupt ledger"
LED=$(newledger t30)
printf 'ROUND\t1\tten\tyes\t\t-\n' > "$LED"
RC=$(rb record-round --run-id=t30 --ledger="$LED" --score=5 --defect=yes)
if [ "$RC" = "6" ]; then ok "T30: corrupt ledger refuses appends"; else fail "T30: corrupt ledger refuses appends" "exit $RC, want 6"; fi

# ── T31: a stop OUTRANKS a passing score ──────────────────────────────────
# `PASSED` used to be checked above the absorbing stops, so every stop was
# cleared by appending one round claiming a 7 -- and the score is the agent's own
# self-report, so the cost of escaping any stop was a single integer.
echo "T31. a self-reported passing score does not clear a stop"
LED=$(newledger t31)
printf 'ROUND\t1\t5\tyes\t\t-\nVERDICT\tSTOP\t\t\nROUND\t2\t9\tyes\t\t-\n' > "$LED"
RC=$(rb budget --run-id=t31 --ledger="$LED")
LED2=$(newledger t31b)
printf 'ROUND\t1\t6\tyes\t\t-\nROUND\t2\t3\tyes\t\t-\nROUND\t3\t8\tyes\t\t-\n' > "$LED2"
RC2=$(rb budget --run-id=t31b --ledger="$LED2")
LED3=$(newledger t31c)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t8\tyes\t\t-\n' > "$LED3"
RC3=$(rb budget --run-id=t31c --ledger="$LED3")
# All FOUR stops, not two. The ordering was pinned for terminal-then-pass and
# regression-then-pass only; moving PASSED above the refuted or no-defect stop
# alone left the suite green. A predicate with four arms needs four cases.
LED4=$(newledger t31d)
{
    printf 'ROUND\t1\t5\tyes\t\t-\n'
    printf 'VERDICT\tCONTINUE\ta at scripts/a.sh:1\t\nROUND\t2\t5\tyes\t\tREFUTED\n'
    printf 'VERDICT\tCONTINUE\tb at scripts/b.sh:2\t\nROUND\t3\t5\tyes\t\tREFUTED\n'
    printf 'ROUND\t4\t9\tyes\t\t-\n'
} > "$LED4"
RC4=$(rb budget --run-id=t31d --ledger="$LED4")
LED5=$(newledger t31e)
printf 'ROUND\t1\t5\tno\t\t-\nROUND\t2\t5\tno\t\t-\nROUND\t3\t9\tyes\t\t-\n' > "$LED5"
RC5=$(rb budget --run-id=t31e --ledger="$LED5")
if [ "$RC" = "6" ] && [ "$RC2" = "6" ] && [ "$RC4" = "6" ] && [ "$RC5" = "6" ] && [ "$RC3" = "3" ]; then
    ok "T31: all four stops outrank a pass; a clean arc still passes"
else
    fail "T31: all four stops outrank a pass" "terminal=$RC regression=$RC2 refuted=$RC4 no-defect=$RC5 (want 6 each), clean=$RC3 (want 3)"
fi

# ── T35: record-verdict is guarded by the terminal state too ──────────────
echo "T35. record-verdict refuses to append past a terminal state"
LED=$(newledger t35)
printf 'ROUND\t1\t5\tyes\t\t-\nVERDICT\tSTOP\t\t\n' > "$LED"
RC=$(rb record-verdict --run-id=t35 --ledger="$LED" --verdict=CONTINUE --prediction="a defect at scripts/x.sh:9")
if [ "$RC" = "6" ]; then ok "T35: no verdict appended past a stop"; else fail "T35: no verdict appended past a stop" "exit $RC, want 6"; fi

# ── T32: the recorder will not append past a terminal state ───────────────
echo "T32. record-round refuses to append after a STOP"
LED=$(newledger t32)
printf 'ROUND\t1\t5\tyes\t\t-\nVERDICT\tSTOP\t\t\n' > "$LED"
RC=$(rb record-round --run-id=t32 --ledger="$LED" --score=9 --defect=yes)
if [ "$RC" = "6" ]; then ok "T32: no appending past a stop"; else fail "T32: no appending past a stop" "exit $RC, want 6"; fi

# ── T33: a BLANK CONTINUE prediction is the emptiest vacuous continuation ──
# The read-time check skipped empty predictions with `[ -n "$v" ] || continue`,
# which is exactly the wrong polarity: the one row carrying no claim at all was
# waved through while a merely weak one was rejected.
echo "T33. a blank CONTINUE prediction does not authorize"
LED=$(newledger t33)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\tCONTINUE\t\t\n' > "$LED"
RC=$(rb budget --run-id=t33 --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T33: blank prediction STOPs"; else fail "T33: blank prediction STOPs" "exit $RC, want 6"; fi

# ── T34: reset archives a finished arc rather than silently inheriting it ──
# Branch-derived ids mean a recycled branch reuses its ledger. That is right
# while an arc is live and wrong once it is done -- a fresh arc must not inherit
# a stale PASSED, which reads as "the gate is already satisfied".
# Reset is GATED. Unguarded it is a laundering path: archiving a live ledger
# clears a STOP without the directive ever being executed, and budget never
# consults the archive. The original T34 blessed exactly that — it reset a live
# two-round ledger and asserted the restart worked.
echo "T34. reset retires a FINISHED arc and refuses a live one"
LED=$(newledger t34)
bash "$RB" record-round --run-id=t34 --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-round --run-id=t34 --ledger="$LED" --score=5 --defect=yes >/dev/null
RC_LIVE=$(rb reset --run-id=t34 --ledger="$LED")
bash "$RB" record-verdict --run-id=t34 --ledger="$LED" --verdict=STRUCTURAL --directive="hoist the invariant" >/dev/null
RC_DONE=$(rb reset --run-id=t34 --ledger="$LED")
OUT=$(rbout budget --run-id=t34 --ledger="$LED")
if [ "$RC_LIVE" = "6" ] && [ "$RC_DONE" = "0" ] && echo "$OUT" | grep -q "round 1 of"; then
    ok "T34: live reset refused, finished reset archives and restarts"
else
    fail "T34: reset gating" "live=$RC_LIVE (want 6), finished=$RC_DONE (want 0), after: $OUT"
fi

# ── T36: rules 2 and 4 hold against the STORED ledger, not only at write ──
echo "T36. an illegal history is refused at read time"
LED=$(newledger t36)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\tCONTINUE\tdefect at scripts/a.sh:1\t\nROUND\t4\t5\tyes\t\t-\n' > "$LED"
RC_UNSETTLED=$(rb budget --run-id=t36 --ledger="$LED")
LED2=$(newledger t36b)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\tCONTINUE\tdefect at scripts/a.sh:1\t\nVERDICT\tCONTINUE\tother at scripts/b.sh:2\t\n' > "$LED2"
RC_STACKED=$(rb budget --run-id=t36b --ledger="$LED2")
if [ "$RC_UNSETTLED" = "6" ] && [ "$RC_STACKED" = "6" ]; then
    ok "T36: unsettled round and stacked verdicts both refused at read time"
else
    fail "T36: read-time history rules" "unsettled=$RC_UNSETTLED stacked=$RC_STACKED (want 6 each)"
fi

# ── T37: only CONTINUE earns a round ──────────────────────────────────────
# An EMPTY verdict token is not a BAD one to analyze -- absent, not invalid -- so
# it passed arity, set no terminal, set no pending, was skipped by the
# CONTINUE-only re-validation, and bought a round. The pre-hoist code caught this
# in a default arm that the comment sweep deleted.
echo "T37. a VERDICT row with an unusable token does not earn a round"
LED=$(newledger t37)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\t\t\t\n' > "$LED"
RC=$(rb budget --run-id=t37 --ledger="$LED")
LED2=$(newledger t37b)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\tCONTINUE\tdefect at scripts/a.sh:1\t\n' > "$LED2"
RC2=$(rb budget --run-id=t37b --ledger="$LED2")
if [ "$RC" = "6" ] && [ "$RC2" = "0" ]; then
    ok "T37: empty token STOPs, CONTINUE still earns"
else
    fail "T37: only CONTINUE earns" "empty=$RC (want 6), continue=$RC2 (want 0)"
fi

# ── T38: ROUND rows are arity-checked too ─────────────────────────────────
# T28 pinned arity with VERDICT fixtures only, so `if (NF != 6)` was a surviving
# mutant: gutting it left all tests green.
echo "T38. a wrong-arity ROUND row fails closed"
LED=$(newledger t38)
printf 'ROUND\t1\t5\tyes\t\t-\tSMUGGLED\tEXTRA\n' > "$LED"
RC=$(rb budget --run-id=t38 --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T38: extra-field ROUND row STOPs"; else fail "T38: ROUND arity" "exit $RC, want 6"; fi

# ── T39: reset still serves the case it exists for ────────────────────────
# Routing reset through the fail-closed gate meant a CORRUPT ledger could not be
# reset -- budget says "fix or discard it" and the only discard left was `rm`,
# turning the one loud archiving path into a silent unlogged deletion.
# Archiving a corrupt ledger AUTOMATICALLY made corruption a bypass of the
# live-arc gate: append one junk line to a live ledger and the budget restarts.
# The remedy stays reachable and becomes deliberate.
echo "T39. a corrupt ledger is archivable, but only deliberately"
LED=$(newledger t39)
printf 'ROUND\t1\tten\tyes\t\t-\n' > "$LED"
RC_PLAIN=$(rb reset --run-id=t39 --ledger="$LED")
# Exit 6 is what a refusal RETURNS, not what it DOES. Checked between the two
# calls, because a reset that archived and then exited 6 leaves the --force call
# with nothing to reset -- "nothing to reset", exit 0 -- and every later
# assertion here still passes.
SURVIVED_PLAIN=$([ -f "$LED" ] && echo yes || echo no)
RC_FORCE=$(rb reset --run-id=t39 --ledger="$LED" --force)
if [ "$RC_PLAIN" = "6" ] && [ "$SURVIVED_PLAIN" = "yes" ] && [ "$RC_FORCE" = "0" ] && [ ! -f "$LED" ]; then
    ok "T39: refused without --force AND left in place, archived with it"
else
    fail "T39: corrupt reset gating" "plain=$RC_PLAIN (want 6), survived plain=$SURVIVED_PLAIN (want yes), force=$RC_FORCE (want 0), present=$([ -f "$LED" ] && echo yes || echo no)"
fi

# ── T41: corrupting a LIVE ledger must not launder it ─────────────────────
echo "T41. junk appended to a live ledger does not buy a reset"
LED=$(newledger t41)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nJUNK\n' > "$LED"
RC=$(rb reset --run-id=t41 --ledger="$LED")
SURVIVED=$([ -f "$LED" ] && echo yes || echo no)
if [ "$RC" = "6" ] && [ "$SURVIVED" = "yes" ]; then
    ok "T41: corrupt-then-reset refused, and the ledger is still there"
else
    fail "T41: corrupt-then-reset" "exit $RC (want 6), survived=$SURVIVED (want yes)"
fi

# ── T42: a trailing pass cannot launder a NONTERMINAL absorbing stop ──────
# The recorders refused only past a terminal VERDICT, so the ledger grew past a
# no-defect / refuted / regression stop and the appended pass then read as
# "finished" to reset. Live-vs-finished now comes from the budget's precedence.
echo "T42. a passing round cannot be appended past a nonterminal stop"
LED=$(newledger t42)
bash "$RB" record-round --run-id=t42 --ledger="$LED" --score=5 --defect=no >/dev/null
bash "$RB" record-round --run-id=t42 --ledger="$LED" --score=5 --defect=no >/dev/null
RC_APPEND=$(rb record-round --run-id=t42 --ledger="$LED" --score=7 --defect=yes)
LED2=$(newledger t42b)
printf 'ROUND\t1\t6\tyes\t\t-\nROUND\t2\t3\tyes\t\t-\n' > "$LED2"
RC_REG=$(rb record-round --run-id=t42b --ledger="$LED2" --score=9 --defect=yes)
if [ "$RC_APPEND" = "6" ] && [ "$RC_REG" = "6" ]; then
    ok "T42: no appending past a nonterminal stop (no-defect and regression)"
else
    fail "T42: nonterminal stop is absorbing for recorders" "nodefect=$RC_APPEND regression=$RC_REG (want 6 each)"
fi

# ── T40: archiving never clobbers a previous archive ──────────────────────
# Keyed on line count alone, two arcs of equal length silently overwrote.
echo "T40. a second archive of equal length does not clobber the first"
LED=$(newledger t40)
printf 'ROUND\t1\t5\tyes\t\t-\nVERDICT\tSTOP\t\t\n' > "$LED"
bash "$RB" reset --run-id=t40 --ledger="$LED" >/dev/null
printf 'ROUND\t1\t9\tyes\t\t-\nVERDICT\tSTOP\t\t\n' > "$LED"
bash "$RB" reset --run-id=t40 --ledger="$LED" >/dev/null
N_ARCH=$(find "$(dirname "$LED")" -name "$(basename "$LED").archived.*" | wc -l | tr -d ' ')
if [ "$N_ARCH" = "2" ]; then ok "T40: both archives survive"; else fail "T40: archive clobber" "$N_ARCH archive(s), want 2"; fi

# ─── reset answers a DIFFERENT question than budget ───────────────────────
#
# `budget` asks "may another ROUND RUN?"; `reset` asks "may this LEDGER BE
# DISCARDED?". reset reused budget's precedence, under which every NONTERMINAL
# absorbing stop and the round-8 ceiling read as "closed", so one plain reset —
# no --force, no corruption — cleared a stop and the next budget said
# "AUTHORIZED — round 1 of 3 free rounds". T34 could not catch it: its live arm
# is a ledger with no stop at all, and its finished arm has an explicit terminal
# verdict. Every case between the two was unpinned.
#
# One test per stop class, because the classes are what the shipped predicate
# conflated, and each carries its own mutation that widens the predicate by
# exactly that one class.
#
# Every one of them asserts BOTH arms -- refused plainly, archived under --force.
# Asserting only the refusal is the vacuity T1/T2 exist to rule out: a gate that
# refuses EVERYTHING passes a refusal-only test while being useless, and the
# --force arm is this file's T2 for each class.

# ── T43: a score regression is a stop, not a finished arc ─────────────────
echo "T43. reset refuses a regression, and --force says what it discarded"
LED=$(newledger t43)
printf 'ROUND\t1\t6\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\n' > "$LED"
RC_PLAIN=$(rb reset --run-id=t43 --ledger="$LED")
STILL=$([ -f "$LED" ] && echo yes || echo no)
# Output and exit code from ONE invocation. Taking them from two calls meant
# the first archived the ledger and the SECOND ran with no ledger at all --
# "nothing to reset", exit 0 -- so the 0 being asserted came from the wrong
# command and would have held even if the archival itself had failed.
OUT=$(bash "$RB" reset --run-id=t43 --ledger="$LED" --force 2>&1); RC_FORCE=$?
ARCH=$(archives_of "$LED")
if [ "$RC_PLAIN" = "6" ] && [ "$STILL" = "yes" ] && [ "$RC_FORCE" = "0" ] && [ "$ARCH" -ge 1 ] && echo "$OUT" | grep -q "FORCED past regressed"; then
    ok "T43: regression refused plainly, discarded only by --force"
else
    fail "T43: regression is not a finished arc" "plain=$RC_PLAIN (want 6), survived=$STILL (want yes), force=$RC_FORCE (want 0), archives=$ARCH (want >=1), out: $OUT"
fi

# ── T44: two REFUTED predictions is a stop, not a finished arc ────────────
echo "T44. reset refuses an arc stopped by two REFUTED predictions"
LED=$(newledger t44)
printf 'ROUND\t1\t5\tyes\t\t-\nVERDICT\tCONTINUE\ta at scripts/a.sh:1\t\nROUND\t2\t5\tyes\t\tREFUTED\nVERDICT\tCONTINUE\tb at scripts/b.sh:2\t\nROUND\t3\t5\tyes\t\tREFUTED\n' > "$LED"
RC=$(rb reset --run-id=t44 --ledger="$LED")
STILL=$([ -f "$LED" ] && echo yes || echo no)
RC_FORCE=$(rb reset --run-id=t44 --ledger="$LED" --force)
ARCH=$(archives_of "$LED")
if [ "$RC" = "6" ] && [ "$STILL" = "yes" ] && [ "$RC_FORCE" = "0" ] && [ "$ARCH" -ge 1 ]; then
    ok "T44: two-REFUTED stop is not resettable, and --force still can"
else
    fail "T44: two-REFUTED stop" "plain=$RC (want 6), survived=$STILL (want yes), force=$RC_FORCE (want 0), archives=$ARCH (want >=1)"
fi

# ── T45: two rounds reproducing nothing is a stop, not a finished arc ─────
echo "T45. reset refuses an arc stopped by two no-defect rounds"
LED=$(newledger t45)
printf 'ROUND\t1\t5\tno\t\t-\nROUND\t2\t5\tno\t\t-\n' > "$LED"
RC=$(rb reset --run-id=t45 --ledger="$LED")
STILL=$([ -f "$LED" ] && echo yes || echo no)
RC_FORCE=$(rb reset --run-id=t45 --ledger="$LED" --force)
ARCH=$(archives_of "$LED")
if [ "$RC" = "6" ] && [ "$STILL" = "yes" ] && [ "$RC_FORCE" = "0" ] && [ "$ARCH" -ge 1 ]; then
    ok "T45: no-defect stop is not resettable, and --force still can"
else
    fail "T45: no-defect stop" "plain=$RC (want 6), survived=$STILL (want yes), force=$RC_FORCE (want 0), archives=$ARCH (want >=1)"
fi

# ── T46: the human ceiling is an escalation, not a finished arc ───────────
# The ceiling exists because unbounded self-granted budget is the resource-
# acquisition pillar the workspace leaves open by design. A reset that clears it
# hands the agent exactly that: hit 8, reset, start again at round 1.
echo "T46. reset refuses an arc at the human ceiling"
LED=$(newledger t46)
for i in 1 2 3 4 5 6 7 8; do printf 'ROUND\t%s\t5\tyes\t\t-\n' "$i"; done > "$LED"
RC_BUDGET=$(rb budget --run-id=t46 --ledger="$LED")
RC=$(rb reset --run-id=t46 --ledger="$LED")
STILL=$([ -f "$LED" ] && echo yes || echo no)
RC_FORCE=$(rb reset --run-id=t46 --ledger="$LED" --force)
ARCH=$(archives_of "$LED")
if [ "$RC_BUDGET" = "7" ] && [ "$RC" = "6" ] && [ "$STILL" = "yes" ] && [ "$RC_FORCE" = "0" ] && [ "$ARCH" -ge 1 ]; then
    ok "T46: the ceiling is not resettable, and --force still can"
else
    fail "T46: ceiling stop" "budget=$RC_BUDGET (want 7), plain=$RC (want 6), survived=$STILL (want yes), force=$RC_FORCE (want 0), archives=$ARCH (want >=1)"
fi

# ── T47: the pass arm reads the RULE, not the score ───────────────────────
# The predicate reset needs is "did this arc END BY PASSING", not "is the last
# score >= 7". Keyed on the score, a self-reported 9 appended after a regression
# reads as a finished arc — which is the older defect this file already pins for
# `budget` at T31, unpinned for `reset` until now. The two arms of this test are
# the same ledger minus the regression, so a gate that simply always refuses
# cannot pass it.
echo "T47. a trailing self-reported pass does not make a stopped arc finished"
LED=$(newledger t47)
printf 'ROUND\t1\t6\tyes\t\t-\nROUND\t2\t3\tyes\t\t-\nROUND\t3\t9\tyes\t\t-\n' > "$LED"
RC_LAUNDER=$(rb reset --run-id=t47 --ledger="$LED")
LED2=$(newledger t47b)
printf 'ROUND\t1\t3\tyes\t\t-\nROUND\t2\t6\tyes\t\t-\nROUND\t3\t9\tyes\t\t-\n' > "$LED2"
RC_CLEAN=$(rb reset --run-id=t47b --ledger="$LED2")
if [ "$RC_LAUNDER" = "6" ] && [ "$RC_CLEAN" = "0" ]; then
    ok "T47: pass-after-regression refused, a clean pass still archives"
else
    fail "T47: pass arm reads the rule" "laundered=$RC_LAUNDER (want 6), clean=$RC_CLEAN (want 0)"
fi

# ── T48: --force is a reset flag, not a global one ────────────────────────
# Parsed in the shared arg loop, `budget --force` and `record-round --force` were
# both accepted and both did nothing. A flag accepted where it has no meaning
# reads as a flag that had one.
echo "T48. --force is refused by every command that is not reset"
LED=$(newledger t48)
RC_BUDGET=$(rb budget --run-id=t48 --ledger="$LED" --force)
RC_ROUND=$(rb record-round --run-id=t48 --ledger="$LED" --score=5 --defect=yes --force)
RC_VERDICT=$(rb record-verdict --run-id=t48 --ledger="$LED" --verdict=STOP --force)
# Polarity: a gate that rejected --force EVERYWHERE would pass the three above.
# It must still be accepted by the one command it belongs to.
LED2=$(newledger t48b)
printf 'ROUND\t1\t6\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\n' > "$LED2"
RC_ACCEPTED=$(rb reset --run-id=t48b --ledger="$LED2" --force)
if [ "$RC_BUDGET" = "2" ] && [ "$RC_ROUND" = "2" ] && [ "$RC_VERDICT" = "2" ] && [ "$RC_ACCEPTED" = "0" ]; then
    ok "T48: --force rejected outside reset, accepted by it"
else
    fail "T48: --force scope" "budget=$RC_BUDGET round=$RC_ROUND verdict=$RC_VERDICT (want 2 each), reset=$RC_ACCEPTED (want 0)"
fi

# ── T49: --force does not open a LIVE arc ─────────────────────────────────
# --force exists because a stopped arc has no in-band way out: refuse_past_terminal
# blocks the very verdict that would declare it over. A LIVE arc has one — record
# its verdict — so the hatch must not reach it, or --force becomes a plain reset
# with an extra word.
echo "T49. --force does not reset a live arc"
LED=$(newledger t49)
printf 'ROUND\t1\t5\tyes\t\t-\n' > "$LED"
RC_PLAIN=$(rb reset --run-id=t49 --ledger="$LED")
RC_FORCE=$(rb reset --run-id=t49 --ledger="$LED" --force)
STILL=$([ -f "$LED" ] && echo yes || echo no)
# Polarity, and the in-band route named in the refusal message: record the
# verdict and the SAME ledger becomes resettable with no --force at all. Both
# arms refusing would otherwise be satisfied by a reset that never says yes.
bash "$RB" record-verdict --run-id=t49 --ledger="$LED" --verdict=STOP >/dev/null 2>&1
RC_AFTER=$(rb reset --run-id=t49 --ledger="$LED")
if [ "$RC_PLAIN" = "6" ] && [ "$RC_FORCE" = "6" ] && [ "$STILL" = "yes" ] && [ "$RC_AFTER" = "0" ]; then
    ok "T49: live arc refuses --force; recording its verdict is the way out"
else
    fail "T49: --force reaches a live arc" "plain=$RC_PLAIN force=$RC_FORCE (want 6 each), survived=$STILL (want yes), after-verdict=$RC_AFTER (want 0)"
fi

# ── T50: the corrupt path never destroys what already sits at its name ────
# The corrupt path wrote "$LEDGER.archived.corrupt.$$" with no never-clobber
# loop while the healthy path four lines below it had one. One archiver, both
# callers — so the collision is forced here at the name the corrupt path picks.
#
# The assertion is PRESERVED BYTES, not a filename. An earlier version required
# ".corrupt.1.1" to exist, and a reviewer showed that killed the pid-based
# mutant for the WRONG reason: a pid namer collides with nothing, so it destroys
# nothing, and the test was reddening on an absent expected NAME rather than on
# any clobber. What must hold is that the entry already there survives and the
# ledger still lands beside it. Its clobber protection is the SAME loop the
# healthy path uses, mutation-proved once at T40 — one site, one proof.
echo "T50. a forced archive does not destroy what already sits at its name"
LED=$(newledger t50)
printf 'ROUND\t1\tten\tyes\t\t-\n' > "$LED"
printf 'SENTINEL\n' > "$LED.archived.corrupt.1"
RC=$(rb reset --run-id=t50 --ledger="$LED" --force)
KEPT=$(cat "$LED.archived.corrupt.1" 2>/dev/null)
ARCH=$(archives_of "$LED")
if [ "$RC" = "0" ] && [ "$KEPT" = "SENTINEL" ] && [ "$ARCH" -ge 2 ]; then
    ok "T50: the occupied name survives and the ledger lands beside it"
else
    fail "T50: corrupt archive clobbers" "exit $RC (want 0), sentinel='$KEPT' (want SENTINEL), archives=$ARCH (want >=2)"
fi

# ── T51: --help is the documentation surface for --force ──────────────────
# The help is this file's own comment block with the markers stripped by sed,
# and the strip used `\?` -- a GNU extension that BSD sed reads as a literal
# '?', so on macOS it matched nothing and every line printed with its '#'. That
# is the platform this is developed on, so the flag documented in the Usage
# block was unreadable exactly where it would be read.
echo "T51. --help renders as text and documents --force"
OUT=$(rbout --help)
HASHED=$(printf '%s\n' "$OUT" | grep -c '^#' || true)
if [ "$HASHED" = "0" ] && printf '%s\n' "$OUT" | grep -q -- "--force"; then
    ok "T51: help is text, and --force is in it"
else
    fail "T51: help renders" "$HASHED line(s) still carry a leading '#'; --force present: $(printf '%s\n' "$OUT" | grep -qc -- "--force" && echo yes || echo no)"
fi

# ── T52: an UNREADABLE ledger is exactly what --force is for ──────────────
# T39 covers UNPARSABLE (readable bytes, bad content). Unreadable is a different
# failure -- chmod 000, a bad ACL -- and it reached the same branch, so it looked
# covered. It was not: consolidating the two archive paths made the corrupt one
# derive its name by READING the ledger, which aborts under `set -e` before the
# mv. The one loud archiving path became no path at all, exit 1 (not even a
# documented code), ledger still in place, `rm` the only remaining discard.
echo "T52. reset --force archives a ledger it cannot read"
LED=$(newledger t52)
printf 'ROUND\t1\t5\tyes\t\t-\n' > "$LED"
chmod 000 "$LED"
if [ -r "$LED" ]; then
    ok "T52: skipped (ledger still readable after chmod 000)"
else
    RC_PLAIN=$(rb reset --run-id=t52 --ledger="$LED")
    SURVIVED_PLAIN=$([ -e "$LED" ] && echo yes || echo no)
    RC_FORCE=$(rb reset --run-id=t52 --ledger="$LED" --force)
    GONE=$([ -e "$LED" ] && echo no || echo yes)
    # "gone" alone is satisfied by DELETION -- the outcome this command exists
    # to replace. The archive must exist.
    ARCH=$(archives_of "$LED")
    if [ "$RC_PLAIN" = "6" ] && [ "$SURVIVED_PLAIN" = "yes" ] && [ "$RC_FORCE" = "0" ] && [ "$GONE" = "yes" ] && [ "$ARCH" -ge 1 ]; then
        ok "T52: unreadable ledger refused plainly, archived under --force"
    else
        fail "T52: unreadable ledger archive" "plain=$RC_PLAIN (want 6), survived plain=$SURVIVED_PLAIN (want yes), force=$RC_FORCE (want 0), gone=$GONE (want yes), archives=$ARCH (want >=1)"
    fi
fi
chmod 644 "$LED" 2>/dev/null || true

# ── T53: "already here" must mean the ENTRY, not what it points at ────────
# `[ -e ]` follows the link. A DANGLING symlink at the chosen archive name tests
# FALSE, so the never-clobber loop stopped there and the mv destroyed that
# entry -- the precise event the loop exists to prevent, in the one case its own
# test could not see.
echo "T53. a dangling symlink at the archive name is not clobbered"
LED=$(newledger t53)
printf 'ROUND\t1\t8\tyes\t\t-\n' > "$LED"
ln -s "$TMP/t53-no-such-target" "$LED.archived.1"
# The fixture must be DANGLING or this test silently exercises `-e` instead of
# `-L` and passes against the defect. `-e` follows the link, so on a dangling
# one it is false while `-L` is true.
DANGLING=$([ ! -e "$LED.archived.1" ] && [ -L "$LED.archived.1" ] && echo yes || echo no)
RC=$(rb reset --run-id=t53 --ledger="$LED")
STILL_LINK=$([ -L "$LED.archived.1" ] && echo yes || echo no)
SIDESTEP=$([ -e "$LED.archived.1.1" ] && echo yes || echo no)
if [ "$DANGLING" = "yes" ] && [ "$RC" = "0" ] && [ "$STILL_LINK" = "yes" ] && [ "$SIDESTEP" = "yes" ]; then
    ok "T53: the symlink survives and the archive steps aside"
else
    fail "T53: dangling symlink clobbered" "fixture dangling=$DANGLING (want yes), exit $RC (want 0), symlink intact=$STILL_LINK (want yes), sidestep=$SIDESTEP (want yes)"
fi

# ── T54: `ln` does not fail on a DIRECTORY — it links into it ─────────────
# `ln src dir` is not a collision to link(1): it places the link INSIDE dir and
# exits 0. So an atomic reservation cannot be the only test. Before the entry
# check was restored, a directory at the chosen name made reset report
# "archived -> $ARCHIVE" while the ledger actually landed at $ARCHIVE/<basename>
# -- the operator told where it went, and told wrong.
echo "T54. a directory at the archive name is stepped over, not linked into"
LED=$(newledger t54)
printf 'ROUND\t1\t8\tyes\t\t-\n' > "$LED"
mkdir "$LED.archived.1"
# One invocation for both, for the reason T43 carries: a second reset would run
# with the ledger already archived -- "nothing to reset", exit 0 -- so its code
# describes a different command than the one being measured.
OUT=$(bash "$RB" reset --run-id=t54 --ledger="$LED" 2>&1); RC=$?
DIR_EMPTY=$([ -d "$LED.archived.1" ] && [ -z "$(ls -A "$LED.archived.1")" ] && echo yes || echo no)
# The path it NAMED must be the path that holds it.
NAMED=$(printf '%s\n' "$OUT" | sed -n 's/^round-budget: archived -> //p' | head -1)
NAMED_IS_FILE=$([ -f "$NAMED" ] && echo yes || echo no)
if [ "$DIR_EMPTY" = "yes" ] && [ "$NAMED_IS_FILE" = "yes" ]; then
    ok "T54: the directory is untouched and the reported path holds the archive"
else
    fail "T54: directory at archive name" "dir left empty=$DIR_EMPTY (want yes), named path '$NAMED' is a file=$NAMED_IS_FILE (want yes), rc=$RC"
fi

# ── T55: an unusable verdict token is a stop class too ────────────────────
# The per-class set covered regression, two-REFUTED, two-no-defect and the
# ceiling, and omitted this one -- so widening reset to treat `unusable_verdict`
# as finished survived the whole suite. It is a NONTERMINAL stop like the other
# four: a VERDICT row carrying a token that is neither CONTINUE nor terminal
# bought a round once, and nothing about it declares the arc over.
echo "T55. an unusable verdict token is not a finished arc"
LED=$(newledger t55)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nROUND\t3\t5\tyes\t\t-\nVERDICT\t\t\t\n' > "$LED"
RC_BUDGET=$(rb budget --run-id=t55 --ledger="$LED")
RC_PLAIN=$(rb reset --run-id=t55 --ledger="$LED")
STILL=$([ -f "$LED" ] && echo yes || echo no)
RC_FORCE=$(rb reset --run-id=t55 --ledger="$LED" --force)
ARCH=$(archives_of "$LED")
if [ "$RC_BUDGET" = "6" ] && [ "$RC_PLAIN" = "6" ] && [ "$STILL" = "yes" ] && [ "$RC_FORCE" = "0" ] && [ "$ARCH" -ge 1 ]; then
    ok "T55: unusable-verdict stop is not resettable, and --force still can"
else
    fail "T55: unusable-verdict stop" "budget=$RC_BUDGET (want 6), plain=$RC_PLAIN (want 6), survived=$STILL (want yes), force=$RC_FORCE (want 0), archives=$ARCH (want >=1)"
fi

# ── T56: corrupting a live ledger IS the way past the live gate ───────────
# T49 pins "--force does not open a LIVE arc". That is true only while the
# ledger still PARSES: append one junk line and it takes the corrupt path, which
# --force is allowed to archive on purpose — a corrupt ledger must stay
# discardable, or `rm` becomes the only escape and that one is silent.
#
# So the hole is real and it is chosen. This test pins it as BEHAVIOUR rather
# than leaving it as an undocumented gap, because SKILL.md used to claim a live
# arc was refused "--force included" full stop, which is false the moment the
# file is corrupted. Both halves are asserted: it goes through, and it lands
# LOUDLY under .archived.corrupt. so the escape is auditable.
echo "T56. corrupting a live ledger routes it to the corrupt path, loudly"
LED=$(newledger t56)
printf 'ROUND\t1\t5\tyes\t\t-\n' > "$LED"
RC_LIVE=$(rb reset --run-id=t56 --ledger="$LED" --force)
printf 'GARBAGE\n' >> "$LED"
RC_CORRUPT_PLAIN=$(rb reset --run-id=t56 --ledger="$LED")
RC_CORRUPT_FORCE=$(rb reset --run-id=t56 --ledger="$LED" --force)
CORRUPT_ARCHIVES=$(find "$(dirname "$LED")" -maxdepth 1 -type f -name "$(basename "$LED").archived.corrupt.*" 2>/dev/null | wc -l | tr -d ' ')
# RC_LIVE=6 is the polarity arm: without it, a reset that archived EVERYTHING
# would satisfy the rest of this test.
if [ "$RC_LIVE" = "6" ] && [ "$RC_CORRUPT_PLAIN" = "6" ] && [ "$RC_CORRUPT_FORCE" = "0" ] && [ "$CORRUPT_ARCHIVES" = "1" ]; then
    ok "T56: live+force refused; corrupt+force archives once, under .corrupt."
else
    fail "T56: corrupt-path escape not as documented" \
        "live+force=$RC_LIVE (want 6), corrupt+plain=$RC_CORRUPT_PLAIN (want 6), corrupt+force=$RC_CORRUPT_FORCE (want 0), corrupt archives=$CORRUPT_ARCHIVES (want 1)"
fi

# ── T57: widening the ROUND arity did not open the SHORT row ─────────────
# ROUND rows are 6 OR 7 fields now (field 7 = the strata that produced the
# score). T38 pins the ceiling with an 8-field row; this pins that the short
# row -- the dangerous direction, because it leaves $6 empty and takes the
# REFUTED accounting with it -- is still refused after the widening.
#
# What actually refuses it is NOT the arity check, and the distinction is
# recorded rather than assumed: widening the arity to admit NF==5 was mutated
# in and SURVIVED this assertion. A five-field row leaves $6 empty, and the
# settles arm reads "" as neither REFUTED, CONFIRMED nor "-" and sets badrow
# first, so nothing can reach the arity floor. The floor stays in the source
# as the honest statement of the row shape; it is not what this test proves,
# and round-budget.mutation.sh says so where the mutation would have gone.
echo "T57. a SHORT ROUND row still fails closed"
LED=$(newledger t57)
printf 'ROUND\t1\t5\tyes\t-\n' > "$LED"
RC=$(rb budget --run-id=t57 --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T57: five-field ROUND row STOPs"; else fail "T57: ROUND arity floor" "exit $RC, want 6"; fi

# ── T58: the strata that produced a score are recorded and surfaced ───────
# A 7/10 from A+B+C and a 7/10 from C alone are different evidence carrying the
# same integer -- Stratum A is the only cross-vendor verdict and the only one
# where "cannot write" is literally true, so a panel of B+C is the writer's own
# model twice. The score alone cannot say which ran.
#
# The SECOND arm is the one that matters and is the reason this is one test
# rather than two: recording nothing must not render as a panel. If omission
# produced a blank -- or worse, a letter -- then "nobody wrote down which strata
# ran" and "only Stratum C ran" would read the same, which is the exact defect
# class ("absence read as a value") this field exists to remove.
echo "T58. show surfaces the panel, and an unrecorded panel is NOT a blank"
LED=$(newledger t58)
bash "$RB" record-round --run-id=t58 --ledger="$LED" --score=5 --defect=yes --strata=A,B,C >/dev/null
bash "$RB" record-round --run-id=t58 --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-round --run-id=t58 --ledger="$LED" --score=5 --defect=yes --strata=C >/dev/null
OUT=$(rbout show --run-id=t58 --ledger="$LED")
FULL=$(printf '%s\n' "$OUT" | grep -c 'round 1 .*strata=A,B,C' || true)
UNREC=$(printf '%s\n' "$OUT" | grep -c 'round 2 .*strata=unrecorded' || true)
CONLY=$(printf '%s\n' "$OUT" | grep -c 'round 3 .*strata=C ' || true)
if [ "$FULL" = "1" ] && [ "$UNREC" = "1" ] && [ "$CONLY" = "1" ]; then
    ok "T58: A,B,C / unrecorded / C each surface distinctly in show"
else
    fail "T58: strata surfaced" "A,B,C=$FULL unrecorded=$UNREC C=$CONLY (want 1 1 1)
$OUT"
fi

# ── T59: BACKWARD COMPATIBILITY — a pre-strata ledger still works ─────────
# Every ROUND row written before this field existed has six fields. If those
# stopped parsing, a valid arc would be refused for a reason that has nothing to
# do with it -- a fail-closed refusal on real work, which is a regression and
# not caution. So field 7 is OPTIONAL ON READ.
#
# Both halves are asserted, because either alone passes a broken implementation:
# an old ledger must still AUTHORIZE (not merely "not crash"), and `show` must
# render its missing panel as the SAME named token an omitted --strata writes.
# Rendering it blank would reintroduce the absence-read-as-a-value defect at the
# one surface a human actually reads.
echo "T59. an OLD-FORMAT (six-field) ledger still parses, authorizes, and reads as unrecorded"
LED=$(newledger t59)
printf 'ROUND\t1\t4\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\n' > "$LED"
RC=$(rb budget --run-id=t59 --ledger="$LED")
OUT=$(rbout show --run-id=t59 --ledger="$LED")
UNREC=$(printf '%s\n' "$OUT" | grep -c 'strata=unrecorded' || true)
BLANK=$(printf '%s\n' "$OUT" | grep -c 'strata= ' || true)
# A six-field ledger must also still ACCEPT an append: the recorder writes a
# seven-field row onto it and the mixed-arity history keeps parsing.
bash "$RB" record-round --run-id=t59 --ledger="$LED" --score=5 --defect=yes --strata=B,C >/dev/null 2>&1
# RC_MIXED=5 is itself the landing check: three rounds is REVIEW-REQUIRED, two
# is a free round (0). MIXED_SHOW then proves the appended row reads BACK -- a
# row that landed but could not be rendered would satisfy the exit code alone.
RC_MIXED=$(rb budget --run-id=t59 --ledger="$LED")
MIXED_SHOW=$(rbout show --run-id=t59 --ledger="$LED" | grep -c 'round 3 .*strata=B,C' || true)
if [ "$RC" = "0" ] && [ "$UNREC" = "2" ] && [ "$BLANK" = "0" ] && \
   [ "$RC_MIXED" = "5" ] && [ "$MIXED_SHOW" = "1" ]; then
    ok "T59: old ledger authorizes, renders as unrecorded, and accepts a new-format append"
else
    fail "T59: old-format ledger" "budget=$RC (want 0), unrecorded rows=$UNREC (want 2), blank=$BLANK (want 0), mixed=$RC_MIXED (want 5), appended row rendered=$MIXED_SHOW (want 1)
$OUT"
fi

# ── T60: a garbage panel is refused at WRITE ──────────────────────────────
# Same polarity as the score check: an unknown letter, an empty value and a
# repeat are all garbage, and garbage fails closed rather than being stored.
# `--strata=` with an EMPTY value is the interesting one -- it is a MALFORMED
# claim, not an absent one, so it must not quietly become `unrecorded`. Keyed on
# the value alone the two states are identical, which is why the recorder tracks
# whether the flag was given at all.
echo "T60. an invalid --strata is refused, and the valid arm still records"
LED=$(newledger t60)
RC_UNKNOWN=$(rb record-round --run-id=t60 --ledger="$LED" --score=5 --defect=yes --strata=D)
RC_EMPTY=$(rb record-round --run-id=t60 --ledger="$LED" --score=5 --defect=yes --strata=)
RC_DUP=$(rb record-round --run-id=t60 --ledger="$LED" --score=5 --defect=yes --strata=A,A)
RC_MIXEDCASE=$(rb record-round --run-id=t60 --ledger="$LED" --score=5 --defect=yes --strata=a,c)
RC_COMMA=$(rb record-round --run-id=t60 --ledger="$LED" --score=5 --defect=yes --strata=A,)
# The separator-injection arm, and the reason the shape check is a glob rather
# than `grep -qE`: grep matches LINE BY LINE, so a value carrying a newline
# passes on its first line while the printf writes a RECORD SEPARATOR into the
# field and splits the row. This is the same attack T14 pins for predictions,
# where `sanitize` is what stops it; the panel is validated instead of
# sanitized, so the validator has to see the whole string.
RC_NEWLINE=$(rb record-round --run-id=t60 --ledger="$LED" --score=5 --defect=yes --strata="$(printf 'A\nD')")
WROTE=$([ -f "$LED" ] && echo yes || echo no)
# Polarity: a validator that refused EVERYTHING would pass every arm above.
RC_OK=$(rb record-round --run-id=t60 --ledger="$LED" --score=5 --defect=yes --strata=A,C)
if [ "$RC_UNKNOWN" = "2" ] && [ "$RC_EMPTY" = "2" ] && [ "$RC_DUP" = "2" ] && \
   [ "$RC_MIXEDCASE" = "2" ] && [ "$RC_COMMA" = "2" ] && [ "$RC_NEWLINE" = "2" ] && \
   [ "$WROTE" = "no" ] && [ "$RC_OK" = "0" ]; then
    ok "T60: unknown/empty/dup/lowercase/trailing-comma/newline refused, nothing written, A,C accepted"
else
    fail "T60: strata write validation" \
        "D=$RC_UNKNOWN empty=$RC_EMPTY dup=$RC_DUP lower=$RC_MIXEDCASE comma=$RC_COMMA newline=$RC_NEWLINE ledger_created=$WROTE ok=$RC_OK (want 2 2 2 2 2 2 no 0)"
fi
# The newline arm above asserts an exit code; this asserts the CONSEQUENCE it
# exists to prevent, because a refusal that still wrote would satisfy the code
# alone. The ledger must hold exactly the one row the valid call added.
T60_LINES=$(grep -c . "$LED" || true)
T60_COLS=$(awk -F"\t" 'END{print NF}' "$LED")
if [ "$T60_LINES" = "1" ] && [ "$T60_COLS" = "7" ]; then
    ok "T60b: one seven-field row landed; no refused call wrote or split a row"
else
    fail "T60b: no row smuggled past the refusals" "lines=$T60_LINES cols=$T60_COLS (want 1 and 7)"
fi

# ── T61: the panel must satisfy the rule at READ time too ─────────────────
# The same claim T29 makes for predictions, for the same reason: a rule enforced
# only at the entry point is one a hand-edited row walks straight past. A stored
# row naming a panel that no recorder could have written is a history that
# cannot be read, and this controller refuses those rather than acting on them.
# The empty arm is the load-bearing one -- a blank field is what a reader would
# take for `unrecorded` while nothing ever wrote it.
echo "T61. a stored panel that would not pass the recorder fails closed"
LED=$(newledger t61)
printf 'ROUND\t1\t5\tyes\t\t-\tD,E\n' > "$LED"
RC_GARBAGE=$(rb budget --run-id=t61 --ledger="$LED")
LED2=$(newledger t61b)
printf 'ROUND\t1\t5\tyes\t\t-\t\n' > "$LED2"
RC_BLANK=$(rb budget --run-id=t61b --ledger="$LED2")
LED3=$(newledger t61c)
printf 'ROUND\t1\t5\tyes\t\t-\tA,C\n' > "$LED3"
RC_GOOD=$(rb budget --run-id=t61c --ledger="$LED3")
LED4=$(newledger t61d)
printf 'ROUND\t1\t5\tyes\t\t-\tunrecorded\n' > "$LED4"
RC_UNREC=$(rb budget --run-id=t61d --ledger="$LED4")
if [ "$RC_GARBAGE" = "6" ] && [ "$RC_BLANK" = "6" ] && [ "$RC_GOOD" = "0" ] && [ "$RC_UNREC" = "0" ]; then
    ok "T61: stored garbage/blank panels STOP; A,C and unrecorded still authorize"
else
    fail "T61: read-time strata validation" \
        "garbage=$RC_GARBAGE blank=$RC_BLANK good=$RC_GOOD unrecorded=$RC_UNREC (want 6 6 0 0)"
fi

# ── T62: --strata means something on ONE command, so it is refused on the rest ──
# `budget --strata=A,C` would otherwise exit 0 having recorded nothing, and a
# flag accepted where it has no meaning reads as a flag that had one -- the same
# failure --force's own scope guard exists to stop. It matters more here than
# elsewhere: the thing silently not recorded IS "which panel scored this".
echo "T62. --strata is scoped to record-round"
LED=$(newledger t62)
bash "$RB" record-round --run-id=t62 --ledger="$LED" --score=5 --defect=yes --strata=A,C >/dev/null
RC_BUDGET=$(rb budget --run-id=t62 --ledger="$LED" --strata=A,C)
RC_SHOW=$(rb show --run-id=t62 --ledger="$LED" --strata=A,C)
RC_VERDICT=$(rb record-verdict --run-id=t62 --ledger="$LED" --verdict=STOP --strata=A,C)
# Polarity: a guard that refused --strata everywhere would pass all three.
RC_RECORD=$(rb record-round --run-id=t62 --ledger="$LED" --score=5 --defect=yes --strata=B)
if [ "$RC_BUDGET" = "2" ] && [ "$RC_SHOW" = "2" ] && [ "$RC_VERDICT" = "2" ] && [ "$RC_RECORD" = "0" ]; then
    ok "T62: --strata refused on budget/show/record-verdict, accepted on record-round"
else
    fail "T62: --strata scope" "budget=$RC_BUDGET show=$RC_SHOW verdict=$RC_VERDICT record=$RC_RECORD (want 2 2 2 0)"
fi

# ── T63: recording a panel changes NO stop and NO authorization ───────────
# This field is bookkeeping. It must not become a fourth way to buy a round or
# a fifth way to lose one, and "I only added a column" is exactly the claim that
# needs checking rather than asserting. Every absorbing stop is re-run on
# SEVEN-field rows carrying a full A,B,C panel -- the strongest panel available,
# which is the direction that would flatter the writer if the field leaked into
# a predicate.
echo "T63. every pre-existing stop still holds on rows that carry a panel"
# regression, on 7-field rows
LED=$(newledger t63a)
printf 'ROUND\t1\t6\tyes\t\t-\tA,B,C\nROUND\t2\t5\tyes\t\t-\tA,B,C\n' > "$LED"
RC_REG=$(rb budget --run-id=t63a --ledger="$LED")
# two consecutive REFUTED, and a later CONFIRMED + passing score clears neither
LED=$(newledger t63b)
{
    printf 'ROUND\t1\t5\tyes\t\t-\tA,B,C\n'
    printf 'VERDICT\tCONTINUE\ta at scripts/a.sh:1\t\nROUND\t2\t5\tyes\t\tREFUTED\tA,B,C\n'
    printf 'VERDICT\tCONTINUE\tb at scripts/b.sh:2\t\nROUND\t3\t5\tyes\t\tREFUTED\tA,B,C\n'
    printf 'ROUND\t4\t9\tyes\t\tCONFIRMED\tA,B,C\n'
} > "$LED"
RC_REF=$(rb budget --run-id=t63b --ledger="$LED")
OUT_REF=$(rbout budget --run-id=t63b --ledger="$LED")
# two no-defect rounds, then a passing round: PASSED must not outrank the stop
LED=$(newledger t63c)
printf 'ROUND\t1\t5\tno\t\t-\tA,B,C\nROUND\t2\t5\tno\t\t-\tA,B,C\nROUND\t3\t9\tyes\t\t-\tA,B,C\n' > "$LED"
RC_NOD=$(rb budget --run-id=t63c --ledger="$LED")
# a terminal verdict, then a passing round appended past it
LED=$(newledger t63d)
printf 'ROUND\t1\t5\tyes\t\t-\tA,B,C\nVERDICT\tSTOP\t\t\nROUND\t2\t9\tyes\t\t-\tA,B,C\n' > "$LED"
RC_TERM=$(rb budget --run-id=t63d --ledger="$LED")
# the human ceiling
LED=$(newledger t63e)
for i in 1 2 3 4 5 6 7 8; do printf 'ROUND\t%s\t5\tyes\t\t-\tA,B,C\n' "$i"; done > "$LED"
RC_CEIL=$(rb budget --run-id=t63e --ledger="$LED")
if [ "$RC_REG" = "6" ] && [ "$RC_REF" = "6" ] && [ "$RC_NOD" = "6" ] && \
   [ "$RC_TERM" = "6" ] && [ "$RC_CEIL" = "7" ] && \
   printf '%s\n' "$OUT_REF" | grep -q "REFUTED"; then
    ok "T63: regression / two REFUTED / two no-defect / terminal / ceiling all still absorbing"
else
    fail "T63: stops on 7-field rows" \
        "reg=$RC_REG ref=$RC_REF nodefect=$RC_NOD terminal=$RC_TERM ceiling=$RC_CEIL (want 6 6 6 6 7)"
fi

echo "T64. a BLANK panel on a 7-field row renders as MALFORMED, never as unrecorded"
# Stratum B finding: `load_ledger` exits 6 on a blank field 7 -- "the value that
# must not slip through" -- while `show` rendered that same byte as
# `unrecorded`. The operator whose `budget` just said "does not parse" ran
# `show` to find out why and was told the panel was merely unrecorded: a
# fail-closed condition laundered into a legitimate value.
LED=$(newledger t64a)
printf 'ROUND\t1\t5\tyes\t\t-\t\n' > "$LED"
OUT_BLANK=$(rbout show --run-id=t64a --ledger="$LED")
RC_BLANK64=$(rb budget --run-id=t64a --ledger="$LED")
# a six-field row is a REAL absence and must still read as unrecorded
LED=$(newledger t64b)
printf 'ROUND\t1\t5\tyes\t\t-\n' > "$LED"
OUT_OLD=$(rbout show --run-id=t64b --ledger="$LED")
# and a real panel still renders verbatim
LED=$(newledger t64c)
printf 'ROUND\t1\t5\tyes\t\t-\tA,C\n' > "$LED"
OUT_REAL=$(rbout show --run-id=t64c --ledger="$LED")
if printf '%s\n' "$OUT_BLANK" | grep -q "MALFORMED" && \
   ! printf '%s\n' "$OUT_BLANK" | grep -q "strata=unrecorded" && \
   [ "$RC_BLANK64" = "6" ] && \
   printf '%s\n' "$OUT_OLD" | grep -q "strata=unrecorded" && \
   printf '%s\n' "$OUT_REAL" | grep -q "strata=A,C"; then
    ok "T64: blank panel reads MALFORMED and still STOPs; six-field still unrecorded; real panel verbatim"
else
    fail "T64: show must not launder a refused blank into unrecorded" \
        "blank=$OUT_BLANK rc=$RC_BLANK64 old=$OUT_OLD real=$OUT_REAL"
fi

# T65 (the pre-push strata hint) is DELIBERATELY NOT TESTED HERE, and that is a
# recorded gap rather than an oversight. The assertion needs `cross-review.sh
# pre-push` to run, which needs real repo context; the mutation harness copies
# this skill to a NON-GIT scratch dir on purpose, so such a test makes the whole
# sweep refuse to run on a red baseline. A test that costs the mutation proof
# is a bad trade. Tracked as a follow-up; the behaviour it would pin is the
# hint derivation at cross-review.sh (STRATA_HINT), and cross-review.test.sh --
# which runs in a real tree -- is where it belongs.

echo ""
echo "── round-budget: $PASS passed, $FAIL failed ──"
if [ "$FAIL" -gt 0 ]; then printf '  failed: %s\n' "${FAILED[@]}"; exit 1; fi
exit 0
