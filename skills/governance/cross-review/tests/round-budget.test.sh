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

# ── T1: NULL CONTROL — nothing is happening, so do not authorize ──────────
echo "T1. null control: flat score, no reproduced defects -> not authorized"
LED=$(newledger t2)
bash "$RB" record-round --run-id=null --ledger="$LED" --score=5 --defect=no --fingerprints=a.sh:f:x >/dev/null
bash "$RB" record-round --run-id=null --ledger="$LED" --score=5 --defect=no --fingerprints=a.sh:f:x >/dev/null
bash "$RB" record-round --run-id=null --ledger="$LED" --score=5 --defect=no --fingerprints=a.sh:f:x >/dev/null
RC=$(rb budget --run-id=null --ledger="$LED")
if [ "$RC" != "0" ]; then
    ok "T1: null ledger does NOT authorize (exit $RC)"
else
    fail "T1: null ledger does NOT authorize" "got AUTHORIZED (exit 0) on a dead ledger — the reflex is vacuous"
fi

# ── T2: POLARITY CONTROL for T1 — the gate can still say yes ──────────────
echo "T2. polarity control: same ledger + a CONTINUE verdict -> authorized"
bash "$RB" record-verdict --run-id=null --ledger="$LED" --verdict=CONTINUE \
    --prediction="unhandled empty-input branch in parse_args at scripts/foo.sh:88" >/dev/null
RC=$(rb budget --run-id=null --ledger="$LED")
if [ "$RC" = "0" ]; then
    ok "T2: gate authorizes when continuation is earned"
else
    fail "T2: gate authorizes when continuation is earned" "got exit $RC — gate may be always-refuse, voiding T1"
fi

# ── T3: rounds 1-3 are free ───────────────────────────────────────────────
echo "T3. first three rounds need no continuation review"
LED=$(newledger t3)
RC=$(rb budget --run-id=free --ledger="$LED")
[ "$RC" = "0" ] && ok "T3a: round 1 free" || fail "T3a: round 1 free" "exit $RC"
bash "$RB" record-round --run-id=free --ledger="$LED" --score=4 --defect=yes >/dev/null
RC=$(rb budget --run-id=free --ledger="$LED")
[ "$RC" = "0" ] && ok "T3b: round 2 free" || fail "T3b: round 2 free" "exit $RC"
bash "$RB" record-round --run-id=free --ledger="$LED" --score=4 --defect=yes >/dev/null
RC=$(rb budget --run-id=free --ledger="$LED")
[ "$RC" = "0" ] && ok "T3c: round 3 free" || fail "T3c: round 3 free" "exit $RC"

# ── T4: round 4 requires a continuation verdict (exit 5) ──────────────────
echo "T4. round 4 requires a continuation review"
bash "$RB" record-round --run-id=free --ledger="$LED" --score=4 --defect=yes >/dev/null
RC=$(rb budget --run-id=free --ledger="$LED")
[ "$RC" = "5" ] && ok "T4: REVIEW-REQUIRED at round 4" || fail "T4: REVIEW-REQUIRED at round 4" "exit $RC, want 5"

# ── T5: score regression stops immediately ────────────────────────────────
echo "T5. score regression -> STOP"
LED=$(newledger t4)
bash "$RB" record-round --run-id=reg --ledger="$LED" --score=6 --defect=yes >/dev/null
bash "$RB" record-round --run-id=reg --ledger="$LED" --score=5 --defect=yes >/dev/null
RC=$(rb budget --run-id=reg --ledger="$LED")
[ "$RC" = "6" ] && ok "T5: STOP on regression (6->5)" || fail "T5: STOP on regression" "exit $RC, want 6"

# ── T6: two refuted predictions -> STOP, even under a live CONTINUE ───────
echo "T6. two consecutive REFUTED predictions -> STOP"
LED=$(newledger t5)
bash "$RB" record-round --run-id=ref --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-verdict --run-id=ref --ledger="$LED" --verdict=CONTINUE --prediction="p1" >/dev/null
bash "$RB" record-round --run-id=ref --ledger="$LED" --score=5 --defect=yes --settles=REFUTED >/dev/null
bash "$RB" record-verdict --run-id=ref --ledger="$LED" --verdict=CONTINUE --prediction="p2" >/dev/null
bash "$RB" record-round --run-id=ref --ledger="$LED" --score=5 --defect=yes --settles=REFUTED >/dev/null
bash "$RB" record-verdict --run-id=ref --ledger="$LED" --verdict=CONTINUE --prediction="p3" >/dev/null
RC=$(rb budget --run-id=ref --ledger="$LED")
[ "$RC" = "6" ] && ok "T6: STOP after two REFUTED" || fail "T6: STOP after two REFUTED" "exit $RC, want 6 — a live CONTINUE must not override it"

# ── T7: the human ceiling overrides any verdict ───────────────────────────
echo "T7. round ceiling -> HUMAN, whatever the verdict says"
LED=$(newledger t6)
bash "$RB" record-round --run-id=ceil --ledger="$LED" --score=5 --defect=yes >/dev/null
for i in 2 3 4 5 6 7 8; do
    bash "$RB" record-verdict --run-id=ceil --ledger="$LED" --verdict=CONTINUE --prediction="p$i" >/dev/null
    bash "$RB" record-round --run-id=ceil --ledger="$LED" --score=5 --defect=yes --settles=CONFIRMED >/dev/null
done
bash "$RB" record-verdict --run-id=ceil --ledger="$LED" --verdict=CONTINUE --prediction="p9" >/dev/null
RC=$(rb budget --run-id=ceil --ledger="$LED")
[ "$RC" = "7" ] && ok "T7: HUMAN at the ceiling" || fail "T7: HUMAN at the ceiling" "exit $RC, want 7 — a CONTINUE verdict must not buy round 9"

# ── T8: anti-vacuity rule 1 — CONTINUE without a prediction is refused ────
echo "T8. CONTINUE requires a prediction"
LED=$(newledger t7)
RC=$(rb record-verdict --run-id=v1 --ledger="$LED" --verdict=CONTINUE)
[ "$RC" = "2" ] && ok "T8a: bare CONTINUE refused" || fail "T8a: bare CONTINUE refused" "exit $RC, want 2"
RC=$(rb record-verdict --run-id=v1 --ledger="$LED" --verdict=CONTINUE --prediction="   ")
[ "$RC" = "2" ] && ok "T8b: whitespace-only prediction refused" || fail "T8b: whitespace-only prediction refused" "exit $RC, want 2"

# ── T9: anti-vacuity rule 2 — a round after CONTINUE must settle it ───────
echo "T9. a round following CONTINUE must settle the prediction"
LED=$(newledger t8)
bash "$RB" record-round --run-id=s1 --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-verdict --run-id=s1 --ledger="$LED" --verdict=CONTINUE --prediction="p" >/dev/null
RC=$(rb record-round --run-id=s1 --ledger="$LED" --score=5 --defect=yes)
[ "$RC" = "2" ] && ok "T9: unsettled round refused" || fail "T9: unsettled round refused" "exit $RC, want 2 — else the two-refuted stop is unreachable"

# ── T10: anti-vacuity rule 4 — CONTINUE verdicts cannot stack ─────────────
echo "T10. CONTINUE verdicts cannot stack without an intervening round"
LED=$(newledger t9)
bash "$RB" record-round --run-id=st --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-verdict --run-id=st --ledger="$LED" --verdict=CONTINUE --prediction="p1" >/dev/null
RC=$(rb record-verdict --run-id=st --ledger="$LED" --verdict=CONTINUE --prediction="p2")
[ "$RC" = "2" ] && ok "T10: stacked CONTINUE refused" || fail "T10: stacked CONTINUE refused" "exit $RC, want 2"

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
[ "$RC" = "3" ] && ok "T12: PASSED" || fail "T12: PASSED" "exit $RC, want 3"

# ── T13: a stale verdict cannot authorize twice ───────────────────────────
# The verdict must be the MOST RECENT row. One already settled by a later round
# has spent its authority; reusing it is how a single CONTINUE buys three rounds.
echo "T13. a verdict already settled by a later round cannot re-authorize"
LED=$(newledger t12)
for i in 1 2 3; do bash "$RB" record-round --run-id=stale --ledger="$LED" --score=5 --defect=yes >/dev/null; done
bash "$RB" record-verdict --run-id=stale --ledger="$LED" --verdict=CONTINUE --prediction="p1" >/dev/null
bash "$RB" record-round --run-id=stale --ledger="$LED" --score=5 --defect=yes --settles=CONFIRMED >/dev/null
RC=$(rb budget --run-id=stale --ledger="$LED")
[ "$RC" = "5" ] && ok "T13: spent verdict does not re-authorize" || fail "T13: spent verdict does not re-authorize" "exit $RC, want 5"

# ── T14: field separators cannot be smuggled through a prediction ─────────
echo "T14. tabs in a prediction cannot shift the ledger columns"
LED=$(newledger t13)
bash "$RB" record-round --run-id=inj --ledger="$LED" --score=5 --defect=yes >/dev/null
bash "$RB" record-verdict --run-id=inj --ledger="$LED" --verdict=CONTINUE \
    --prediction="$(printf 'evil\tREFUTED\tinjected')" >/dev/null
LINES=$(grep -c . "$LED")
COLS=$(tail -1 "$LED" | awk -F'\t' '{print NF}')
if [ "$LINES" = "2" ] && [ "$COLS" = "4" ]; then
    ok "T14: tab-bearing prediction stays in one field"
else
    fail "T14: tab-bearing prediction stays in one field" "lines=$LINES cols=$COLS (want 2 and 4)"
fi

echo ""
echo "── round-budget: $PASS passed, $FAIL failed ──"
if [ "$FAIL" -gt 0 ]; then printf '  failed: %s\n' "${FAILED[@]}"; exit 1; fi
exit 0
