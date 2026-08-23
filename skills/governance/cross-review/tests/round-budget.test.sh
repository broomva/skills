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
RC_FORCE=$(rb reset --run-id=t39 --ledger="$LED" --force)
if [ "$RC_PLAIN" = "6" ] && [ "$RC_FORCE" = "0" ] && [ ! -f "$LED" ]; then
    ok "T39: refused without --force, archived with it"
else
    fail "T39: corrupt reset gating" "plain=$RC_PLAIN (want 6), force=$RC_FORCE (want 0), present=$([ -f "$LED" ] && echo yes || echo no)"
fi

# ── T41: corrupting a LIVE ledger must not launder it ─────────────────────
echo "T41. junk appended to a live ledger does not buy a reset"
LED=$(newledger t41)
printf 'ROUND\t1\t5\tyes\t\t-\nROUND\t2\t5\tyes\t\t-\nJUNK\n' > "$LED"
RC=$(rb reset --run-id=t41 --ledger="$LED")
if [ "$RC" = "6" ]; then ok "T41: corrupt-then-reset refused"; else fail "T41: corrupt-then-reset" "exit $RC, want 6"; fi

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

echo ""
echo "── round-budget: $PASS passed, $FAIL failed ──"
if [ "$FAIL" -gt 0 ]; then printf '  failed: %s\n' "${FAILED[@]}"; exit 1; fi
exit 0
