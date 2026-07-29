#!/usr/bin/env bash
# tests/mutation-proof.test.sh — tests for the mutation-proof runner
#
# Plain bash assertions; no external test framework. Run from the skill root:
#   bash tests/mutation-proof.test.sh
#
# EVERY assertion here either expects a NON-ZERO exit code or asserts on
# specific stdout. That is deliberate. A suite whose every check is "it exited
# 0" passes identically against a dead `exit 0` script — which is precisely the
# defect this tool exists to find, and which it would then be committing itself.
# T15 proves the property rather than asserting it: it stubs THIS runner and
# requires this suite to go red.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MP="$REPO/scripts/mutation-proof.sh"

PASS=0
FAIL=0
FAILED=()

ok() {
    PASS=$((PASS + 1))
    echo "  [pass] $1"
}
fail() {
    FAIL=$((FAIL + 1))
    FAILED+=("$1")
    echo "  [FAIL] $1"
    [ -n "${2:-}" ] && echo "         $2"
}

WORK=$(mktemp -d "${TMPDIR:-/tmp}/mutproof-tests.XXXXXX")
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT

# ── Fixture ───────────────────────────────────────────────────────────────
# A gate that blocks a word, plus three test scripts over it:
#   t/discriminating.sh — exercises the behaviour (3 per-check markers)
#   t/decoration.sh     — only asserts the gate exits 0 (the non-discriminating
#                         shape: "rc 0 + no output" is what a dead script does)
#   t/aborting.sh       — stops at the first failure, so the suite SHAPE changes
make_fixture() {
    local d="$1"
    mkdir -p "$d/src" "$d/t"
    cat >"$d/src/gate.sh" <<'FIX'
#!/usr/bin/env bash
read -r line
case "$line" in *danger*) echo "BLOCK"; exit 0 ;; esac
echo "ALLOW"
FIX
    chmod +x "$d/src/gate.sh"

    cat >"$d/t/discriminating.sh" <<'FIX'
#!/usr/bin/env bash
F=0
c() { if [ "$2" = "$3" ]; then echo "  [ok] $1"; else echo "  [FAIL] $1"; F=$((F + 1)); fi; }
c "danger blocks" "$(echo 'rm danger' | bash src/gate.sh)" "BLOCK"
c "safe allows"   "$(echo 'ls' | bash src/gate.sh)" "ALLOW"
c "empty allows"  "$(echo '' | bash src/gate.sh)" "ALLOW"
[ "$F" -gt 0 ] && exit 1
exit 0
FIX

    cat >"$d/t/decoration.sh" <<'FIX'
#!/usr/bin/env bash
if bash src/gate.sh </dev/null >/dev/null 2>&1; then echo "  [ok] gate runs"; else echo "  [FAIL] gate runs"; exit 1; fi
if [ -f src/gate.sh ]; then echo "  [ok] gate exists"; else echo "  [FAIL] gate exists"; exit 1; fi
exit 0
FIX

    cat >"$d/t/aborting.sh" <<'FIX'
#!/usr/bin/env bash
c() { if [ "$2" = "$3" ]; then echo "  [ok] $1"; else echo "  [FAIL] $1"; exit 1; fi; }
c "danger blocks" "$(echo 'rm danger' | bash src/gate.sh)" "BLOCK"
c "safe allows"   "$(echo 'ls' | bash src/gate.sh)" "ALLOW"
c "empty allows"  "$(echo '' | bash src/gate.sh)" "ALLOW"
exit 0
FIX

    # Silent, discriminating: correct exit code, zero parseable per-check output.
    cat >"$d/t/silent.sh" <<'FIX'
#!/usr/bin/env bash
echo 'rm danger' | bash src/gate.sh | grep -q BLOCK
FIX
}

run_mp() {
    # Runs the runner, capturing combined output in MP_OUT and status in MP_RC.
    MP_OUT=$(bash "$MP" "$@" 2>&1)
    MP_RC=$?
}

echo "── tests/mutation-proof.test.sh ──────────────────────────────"
echo ""

FIX1="$WORK/fix1"
make_fixture "$FIX1"

# ── T1: --help prints usage, de-commented ─────────────────────────────────
echo "T1. --help prints Usage"
run_mp --help
if echo "$MP_OUT" | grep -q "^Usage:" && echo "$MP_OUT" | grep -q -- "--strategy NAME"; then
    ok "T1: help renders"
else
    fail "T1: help renders" "output: $MP_OUT"
fi

# ── T2: version string ────────────────────────────────────────────────────
echo "T2. version prints v0.0.1"
run_mp version
if echo "$MP_OUT" | grep -q "mutation-proof v0.0.1"; then
    ok "T2: version"
else
    fail "T2: version" "$MP_OUT"
fi

# ── T3: unknown command exits 2 ───────────────────────────────────────────
echo "T3. unknown command exits 2"
run_mp bogus-command
if [ "$MP_RC" = "2" ]; then ok "T3: exit 2 on unknown command"; else fail "T3: exit 2 on unknown command" "got $MP_RC"; fi

# ── T4/T5: required flags ─────────────────────────────────────────────────
echo "T4. run without --target exits 2"
run_mp run --test 'true'
if [ "$MP_RC" = "2" ] && echo "$MP_OUT" | grep -q -- "--target"; then
    ok "T4: --target required"
else
    fail "T4: --target required" "rc=$MP_RC out=$MP_OUT"
fi

echo "T5. run without --test exits 2"
run_mp run --target "$FIX1/src/gate.sh"
if [ "$MP_RC" = "2" ] && echo "$MP_OUT" | grep -q -- "--test"; then
    ok "T5: --test required"
else
    fail "T5: --test required" "rc=$MP_RC out=$MP_OUT"
fi

# ── T6: the positive case — stub makes a real suite go red ────────────────
echo "T6. stub on a shell target: PROVEN, exit 0"
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/discriminating.sh'
if [ "$MP_RC" = "0" ] \
    && echo "$MP_OUT" | grep -q "PROVEN — the test discriminates" \
    && echo "$MP_OUT" | grep -q "verdict=PROVEN .*rc_before=0 rc_after=1 flipped=3"; then
    ok "T6: PROVEN with 3 flipped checks"
else
    fail "T6: PROVEN with 3 flipped checks" "rc=$MP_RC out=$MP_OUT"
fi

# ── T7: the negative case — a test that does NOT discriminate ─────────────
# The whole point of the tool. If this ever reports PROVEN, the runner is lying.
echo "T7. non-discriminating test: UNPROVEN, exit 1"
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/decoration.sh'
if [ "$MP_RC" = "1" ] \
    && echo "$MP_OUT" | grep -q "UNPROVEN — the test passed WITH and WITHOUT" \
    && echo "$MP_OUT" | grep -q "verdict=UNPROVEN .*rc_before=0 rc_after=0"; then
    ok "T7: UNPROVEN reported, exit 1"
else
    fail "T7: UNPROVEN reported, exit 1" "rc=$MP_RC out=$MP_OUT"
fi

# ── T8: red baseline is INCONCLUSIVE, never PROVEN ────────────────────────
echo "T8. red baseline: INCONCLUSIVE, exit 3"
run_mp run --root "$FIX1" --target src/gate.sh --test 'exit 7'
if [ "$MP_RC" = "3" ] \
    && echo "$MP_OUT" | grep -q "INCONCLUSIVE — the baseline was not green (exit 7)" \
    && ! echo "$MP_OUT" | grep -q "PROVEN — the test discriminates"; then
    ok "T8: INCONCLUSIVE on red baseline"
else
    fail "T8: INCONCLUSIVE on red baseline" "rc=$MP_RC out=$MP_OUT"
fi

# ── T9: the working tree is never mutated ─────────────────────────────────
# The safety invariant. Mutation happens in the scratch copy only.
#
# "The file did not change" is TRUE OF A RUNNER THAT DOES NOTHING, so on its own
# this check is vacuous — T15 caught it passing against a stubbed runner. The
# verdict assertion is what makes it mean something: the mutation demonstrably
# happened somewhere, and that somewhere was not here.
echo "T9. source tree byte-identical after a run that did mutate"
BEFORE=$(cat "$FIX1/src/gate.sh")
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/discriminating.sh'
AFTER=$(cat "$FIX1/src/gate.sh")
if [ "$BEFORE" = "$AFTER" ] \
    && echo "$MP_OUT" | grep -q "verdict=PROVEN" \
    && ! grep -q "mutation-proof stub" "$FIX1/src/gate.sh"; then
    ok "T9: working tree untouched while the mutation ran"
else
    fail "T9: working tree untouched while the mutation ran" "rc=$MP_RC (target changed on disk, or no mutation ran)"
fi

# ── T10: python stub detection ────────────────────────────────────────────
echo "T10. python target gets a python stub"
PYF="$WORK/py"
mkdir -p "$PYF"
cat >"$PYF/tool.py" <<'FIX'
#!/usr/bin/env python3
import sys
print("REAL" if "--flag" in sys.argv else "NOFLAG")
FIX
cat >"$PYF/check.sh" <<'FIX'
#!/usr/bin/env bash
if [ "$(python3 tool.py --flag)" = "REAL" ]; then echo "  [ok] flag path"; else echo "  [FAIL] flag path"; exit 1; fi
FIX
run_mp run --root "$PYF" --target tool.py --test 'bash check.sh'
if [ "$MP_RC" = "0" ] && echo "$MP_OUT" | grep -q "Mutation:    stub (python)" \
    && echo "$MP_OUT" | grep -q "verdict=PROVEN"; then
    ok "T10: python stub detected and proven"
else
    fail "T10: python stub detected and proven" "rc=$MP_RC out=$MP_OUT"
fi

# ── T11: revert strategy against a pre-fix commit ─────────────────────────
echo "T11. revert to a git ref proves a fix"
GF="$WORK/gitfix"
mkdir -p "$GF"
(
    cd "$GF" || exit 1
    git init -q . && git config user.email t@example.com && git config user.name t
    mkdir -p src t
    cat >src/gate.sh <<'FIX'
#!/usr/bin/env bash
read -r l
case "$l" in *danger*) echo BLOCK; exit 0 ;; esac
echo ALLOW
FIX
    cat >t/run.sh <<'FIX'
#!/usr/bin/env bash
F=0
c() { if [ "$2" = "$3" ]; then echo "  [ok] $1"; else echo "  [FAIL] $1"; F=$((F + 1)); fi; }
c "lowercase blocks" "$(echo 'rm danger' | bash src/gate.sh)" "BLOCK"
c "UPPERCASE blocks" "$(echo 'rm DANGER' | bash src/gate.sh)" "BLOCK"
c "safe allows"      "$(echo 'ls' | bash src/gate.sh)" "ALLOW"
[ "$F" -gt 0 ] && exit 1
exit 0
FIX
    git add -A && git commit -qm "pre-fix: case-sensitive"
    # the fix under proof: casefold the match
    cat >src/gate.sh <<'FIX'
#!/usr/bin/env bash
read -r l
shopt -s nocasematch
case "$l" in *danger*) echo BLOCK; exit 0 ;; esac
echo ALLOW
FIX
    git add -A && git commit -qm "fix: casefold"
) >/dev/null 2>&1
run_mp run --root "$GF" --target src/gate.sh --test 'bash t/run.sh' --strategy revert --ref HEAD~1
if [ "$MP_RC" = "0" ] && echo "$MP_OUT" | grep -q "Mutation:    revert to HEAD~1" \
    && echo "$MP_OUT" | grep -q "verdict=PROVEN .*strategy=revert .*flipped=1"; then
    ok "T11: revert proves the fix (1 check flips)"
else
    fail "T11: revert proves the fix (1 check flips)" "rc=$MP_RC out=$MP_OUT"
fi

echo "T12. revert without --ref exits 2"
run_mp run --root "$FIX1" --target src/gate.sh --test 'true' --strategy revert
if [ "$MP_RC" = "2" ] && echo "$MP_OUT" | grep -q -- "--ref"; then
    ok "T12: revert requires --ref"
else
    fail "T12: revert requires --ref" "rc=$MP_RC out=$MP_OUT"
fi

# ── T13: honest about unparseable output ──────────────────────────────────
# A correct-but-silent suite must not get an invented flip count.
echo "T13. unparseable output reports exit codes only"
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/silent.sh'
if [ "$MP_RC" = "0" ] \
    && echo "$MP_OUT" | grep -q "checks not parseable" \
    && echo "$MP_OUT" | grep -q "output is not parseable as per-check results" \
    && echo "$MP_OUT" | grep -q "flipped=n/a"; then
    ok "T13: no invented count on unparseable output"
else
    fail "T13: no invented count on unparseable output" "rc=$MP_RC out=$MP_OUT"
fi

# ── T14: honest when the suite shape changes ──────────────────────────────
echo "T14. aborting suite reports a shape change, not a flip count"
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/aborting.sh'
if [ "$MP_RC" = "0" ] \
    && echo "$MP_OUT" | grep -q "check count changed 3 → 1" \
    && echo "$MP_OUT" | grep -q "flipped=n/a"; then
    ok "T14: shape change reported honestly"
else
    fail "T14: shape change reported honestly" "rc=$MP_RC out=$MP_OUT"
fi

# ── T15: THE SELF-REFERENTIAL CASE ────────────────────────────────────────
# Stub mutation-proof.sh and require THIS suite to go red. If it stays green,
# every assertion above is decoration and the tool is unfit for its own purpose.
# The runner exports MUTATION_PROOF_ACTIVE=1 into the test command, which is how
# the inner invocation of this file knows to skip this test instead of recursing.
echo "T15. self-referential: stubbing the runner turns this suite red"
if [ "${MUTATION_PROOF_ACTIVE:-0}" = "1" ]; then
    echo "  [skip] T15: inner run under mutation-proof (recursion guard)"
else
    run_mp run --root "$REPO" --target scripts/mutation-proof.sh \
        --test 'bash tests/mutation-proof.test.sh'
    if [ "$MP_RC" = "0" ] && echo "$MP_OUT" | grep -q "verdict=PROVEN .*target=scripts/mutation-proof.sh"; then
        ok "T15: this suite discriminates on its own runner"
    else
        fail "T15: this suite discriminates on its own runner" "rc=$MP_RC out=$MP_OUT"
    fi
fi

# ── T16: --paths guard ────────────────────────────────────────────────────
# Mutating a target outside the copied subset would silently produce a false
# UNPROVEN: the test would never see the mutation.
echo "T16. target outside --paths is rejected"
run_mp run --root "$FIX1" --paths t --target src/gate.sh --test 'bash t/discriminating.sh'
if [ "$MP_RC" = "2" ] && echo "$MP_OUT" | grep -q "not under --paths"; then
    ok "T16: --paths coverage enforced"
else
    fail "T16: --paths coverage enforced" "rc=$MP_RC out=$MP_OUT"
fi

# ── T17: unstubbable file type is an error, not a guess ───────────────────
echo "T17. unknown file type rejected with a remedy"
printf 'key = value\n' >"$FIX1/config.conf"
run_mp run --root "$FIX1" --target config.conf --test 'true'
if [ "$MP_RC" = "2" ] && echo "$MP_OUT" | grep -q "cannot infer a no-op stub" \
    && echo "$MP_OUT" | grep -q -- "--strategy revert"; then
    ok "T17: unknown type errors with a remedy"
else
    fail "T17: unknown type errors with a remedy" "rc=$MP_RC out=$MP_OUT"
fi

# ── T18/T19: wired into cross-review pre-push as a NON-BLOCKING signal ────
# Run from the throwaway git repo built in T11, not from this checkout:
# `pre-push` bails with exit 2 outside a git repo, so running it in the ambient
# cwd would make these two tests depend on where the suite happens to be
# invoked. T15 found exactly that — under the scratch copy (no .git) they went
# red and turned the self-referential run INCONCLUSIVE.
echo "T18. pre-push reports UNPROVEN without failing the gate"
CR_OUT=$(cd "$GF" && FORCE_GATE=1 bash "$REPO/scripts/cross-review.sh" pre-push --strata=C \
    --mutation-root="$FIX1" --mutation-target=src/gate.sh \
    --mutation-test='bash t/decoration.sh' 2>&1)
CR_RC=$?
if [ "$CR_RC" = "0" ] \
    && echo "$CR_OUT" | grep -q "\[signal\] UNPROVEN" \
    && echo "$CR_OUT" | grep -q "non-blocking: pre-push exit code is unaffected"; then
    ok "T18: reported signal, not a gate"
else
    fail "T18: reported signal, not a gate" "rc=$CR_RC out=$CR_OUT"
fi

echo "T19. pre-push without mutation flags says the signal did not run"
CR_OUT=$(cd "$GF" && FORCE_GATE=1 bash "$REPO/scripts/cross-review.sh" pre-push --strata=C 2>&1)
CR_RC=$?
if [ "$CR_RC" = "0" ] && echo "$CR_OUT" | grep -q "\[not run\] no mutation target given"; then
    ok "T19: absence of the signal is stated, not silent"
else
    fail "T19: absence of the signal is stated, not silent" "rc=$CR_RC out=$CR_OUT"
fi

# ── T20: SKILL.md documents the signal and its non-blocking status ────────
echo "T20. SKILL.md documents mutation-proof as a reported signal"
if grep -q "mutation-proof" "$REPO/SKILL.md" \
    && grep -qi "reported signal" "$REPO/SKILL.md" \
    && grep -q "UNPROVEN" "$REPO/SKILL.md"; then
    ok "T20: SKILL.md documents the signal"
else
    fail "T20: SKILL.md documents the signal"
fi

# ── T21-T25: probe receipts (unhobble --probe-receipts schema) ────────────
#
# The receipt exists because unhobble's `anchor_state` cannot verify one: it
# does `all(rec.get(leg) is True ...)`, so hand-written `true`s buy a
# free-to-delete verdict. This runner emits the ONE leg it actually observes.
# The tests below pin that it emits no more than that — the temptation to
# default the other two legs to `true` for a tidier verdict is the identical
# defect in a new costume.
#
# `probe_state_of` replicates the predicate DOCUMENTED in BRO-2035, it does not
# import unhobble's code: that lands on a different branch, and copying it here
# would test our copy rather than the contract.
probe_state_of() {
    python3 - "$1" "$2" <<'PY'
import json, sys
legs = ("fires_on_trigger", "silent_on_non_trigger", "neutered_check_went_red")
rec = json.load(open(sys.argv[1]))["probes"].get(sys.argv[2])
if rec is None:
    print("unresolved")
elif rec.get("fires_on_trigger") is False:
    print("dead")
elif all(rec.get(leg) is True for leg in legs):
    print("fires")
else:
    print("incomplete")
PY
}

RCPT="$WORK/receipts"
mkdir -p "$RCPT"

echo "T21. discriminating run emits neutered_check_went_red=true, other legs ABSENT"
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/discriminating.sh' \
    --emit-receipt "$RCPT/pos.json"
R21=$(python3 - "$RCPT/pos.json" <<'PY'
import json, sys
rec = json.load(open(sys.argv[1]))["probes"]["src/gate.sh"]
print("leg=%r absent=%s rcb=%s rca=%s" % (
    rec.get("neutered_check_went_red"),
    "fires_on_trigger" not in rec and "silent_on_non_trigger" not in rec,
    rec["evidence"]["exit_code_baseline"], rec["evidence"]["exit_code_mutated"]))
PY
)
if [ "$MP_RC" = "0" ] && [ "$R21" = "leg=True absent=True rcb=0 rca=1" ] \
    && [ "$(probe_state_of "$RCPT/pos.json" src/gate.sh)" = "incomplete" ]; then
    ok "T21: one observed leg, two honestly absent, reads as incomplete"
else
    fail "T21: one observed leg, two honestly absent, reads as incomplete" \
        "rc=$MP_RC parsed=[$R21] state=$(probe_state_of "$RCPT/pos.json" src/gate.sh)"
fi

echo "T22. non-discriminating run emits the leg as FALSE, not omitted"
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/decoration.sh' \
    --emit-receipt "$RCPT/neg.json"
R22=$(python3 - "$RCPT/neg.json" <<'PY'
import json, sys
rec = json.load(open(sys.argv[1]))["probes"]["src/gate.sh"]
print("present=%s value=%r" % ("neutered_check_went_red" in rec,
                               rec.get("neutered_check_went_red")))
PY
)
# "I ran it and it did not go red" must be distinguishable from "I did not run it".
if [ "$MP_RC" = "1" ] && [ "$R22" = "present=True value=False" ]; then
    ok "T22: a negative observation is recorded, not omitted"
else
    fail "T22: a negative observation is recorded, not omitted" "rc=$MP_RC parsed=[$R22]"
fi

echo "T23. INCONCLUSIVE writes no receipt at all"
run_mp run --root "$FIX1" --target src/gate.sh --test 'exit 7' --emit-receipt "$RCPT/none.json"
if [ "$MP_RC" = "3" ] && [ ! -e "$RCPT/none.json" ] \
    && echo "$MP_OUT" | grep -q "\[receipt\] nothing written"; then
    ok "T23: nothing observed, nothing claimed"
else
    fail "T23: nothing observed, nothing claimed" "rc=$MP_RC, file exists=$([ -e "$RCPT/none.json" ] && echo yes || echo no)"
fi

echo "T24. merging preserves another producer's legs; a non-receipt file is refused"
cat >"$RCPT/merge.json" <<'FIX'
{"probes": {"src/gate.sh": {"fires_on_trigger": true, "silent_on_non_trigger": true},
            "other/thing.sh": {"fires_on_trigger": true}}}
FIX
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/discriminating.sh' \
    --emit-receipt "$RCPT/merge.json"
R24=$(python3 - "$RCPT/merge.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))["probes"]
print("kept=%s other=%s legs=%s" % (
    d["src/gate.sh"].get("fires_on_trigger"),
    "other/thing.sh" in d,
    d["src/gate.sh"].get("neutered_check_went_red")))
PY
)
printf 'not a receipt\n' >"$RCPT/bad.json"
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/discriminating.sh' \
    --emit-receipt "$RCPT/bad.json"
BAD_RC=$MP_RC
if [ "$R24" = "kept=True other=True legs=True" ] \
    && [ "$(probe_state_of "$RCPT/merge.json" src/gate.sh)" = "fires" ] \
    && [ "$BAD_RC" = "2" ] && [ "$(cat "$RCPT/bad.json")" = "not a receipt" ]; then
    ok "T24: merge preserves foreign legs; malformed file refused, not clobbered"
else
    fail "T24: merge preserves foreign legs; malformed file refused, not clobbered" \
        "parsed=[$R24] bad_rc=$BAD_RC"
fi

echo "T25. --receipt-key overrides the key and refuses to stand for several targets"
# Deliberately unexpanded: unhobble keys a user-scope mechanism by the literal
# `~/...` reference as it is written in the prose, not by its resolved path.
# shellcheck disable=SC2088
USER_SCOPE_KEY='~/broomva/src/gate.sh'
run_mp run --root "$FIX1" --target src/gate.sh --test 'bash t/discriminating.sh' \
    --emit-receipt "$RCPT/keyed.json" --receipt-key "$USER_SCOPE_KEY"
KEYED=$(python3 -c 'import json,sys; print(",".join(sorted(json.load(open(sys.argv[1]))["probes"])))' "$RCPT/keyed.json" 2>/dev/null)
run_mp run --root "$FIX1" --target src/gate.sh,t/discriminating.sh --test 'true' \
    --emit-receipt "$RCPT/multi.json" --receipt-key 'x'
if [ "$KEYED" = "$USER_SCOPE_KEY" ] && [ "$MP_RC" = "2" ] \
    && echo "$MP_OUT" | grep -q "requires exactly one --target"; then
    ok "T25: key override honoured, one key never stands for many targets"
else
    fail "T25: key override honoured, one key never stands for many targets" \
        "keys=[$KEYED] rc=$MP_RC"
fi

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "── results ────────────────────────────────────────────────────"
echo "  $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "  Failed:"
    for t in "${FAILED[@]}"; do echo "    - $t"; done
    exit 1
fi
echo "  all green ✓"
