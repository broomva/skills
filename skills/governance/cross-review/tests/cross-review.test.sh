#!/usr/bin/env bash
# tests/cross-review.test.sh — smoke tests for the cross-review entry point
#
# Plain bash assertions; no external test framework. Run from repo root:
#   bash tests/cross-review.test.sh

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CROSS_REVIEW_SH="$REPO/scripts/cross-review.sh"

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

echo "── tests/cross-review.test.sh ────────────────────────────────"
echo ""

# ── T1: --help prints usage block ─────────────────────────────────────────
echo "T1. --help prints Usage"
OUT=$(bash "$CROSS_REVIEW_SH" --help 2>&1 || true)
if echo "$OUT" | grep -q "Usage:" && echo "$OUT" | grep -q -- "cross-review pre-push"; then
    ok "T1: help renders"
else
    fail "T1: help renders" "output: $OUT"
fi

# ── T2: version prints version string ─────────────────────────────────────
echo "T2. version prints v0.0.1"
OUT=$(bash "$CROSS_REVIEW_SH" version 2>&1 || true)
if echo "$OUT" | grep -q "v0.0.1"; then
    ok "T2: version"
else
    fail "T2: version" "$OUT"
fi

# ── T3: unknown command exits 2 ───────────────────────────────────────────
echo "T3. unknown command exits 2"
EXIT=0
bash "$CROSS_REVIEW_SH" bogus-command >/dev/null 2>&1 || EXIT=$?
if [ "$EXIT" = "2" ]; then
    ok "T3: exit 2 on unknown"
else
    fail "T3: exit 2 on unknown" "got exit $EXIT"
fi

# ── T4: missing --spec on plan exits 2 ────────────────────────────────────
echo "T4. plan without --spec exits 2"
EXIT=0
bash "$CROSS_REVIEW_SH" plan >/dev/null 2>&1 || EXIT=$?
if [ "$EXIT" = "2" ]; then
    ok "T4: plan requires --spec"
else
    fail "T4: plan requires --spec" "got exit $EXIT"
fi

# ── T5: missing --target on audit exits 2 ─────────────────────────────────
echo "T5. audit without --target exits 2"
EXIT=0
bash "$CROSS_REVIEW_SH" audit >/dev/null 2>&1 || EXIT=$?
if [ "$EXIT" = "2" ]; then
    ok "T5: audit requires --target"
else
    fail "T5: audit requires --target" "got exit $EXIT"
fi

# ── T6: rubric.md exists and has the 5 dimensions ─────────────────────────
echo "T6. rubric.md present + has 5 dimensions"
if [ -f "$REPO/references/rubric.md" ] && \
    grep -q "over-engineered abstractions" "$REPO/references/rubric.md" && \
    grep -q "template-paste patterns" "$REPO/references/rubric.md" && \
    grep -q "Correct contracts at boundaries" "$REPO/references/rubric.md" && \
    grep -q "Failure modes named explicitly" "$REPO/references/rubric.md" && \
    grep -q "Tests cover the change" "$REPO/references/rubric.md"; then
    ok "T6: rubric.md complete"
else
    fail "T6: rubric.md complete"
fi

# ── T7: SKILL.md frontmatter valid ────────────────────────────────────────
echo "T7. SKILL.md frontmatter valid"
HEAD=$(head -1 "$REPO/SKILL.md")
NAME_OK=$(awk '/^---$/{f=!f; next} f' "$REPO/SKILL.md" | grep -c "^name: cross-review")
DESC_OK=$(awk '/^---$/{f=!f; next} f' "$REPO/SKILL.md" | grep -c "^description:")
if [ "$HEAD" = "---" ] && [ "$NAME_OK" -ge 1 ] && [ "$DESC_OK" -ge 1 ]; then
    ok "T7: SKILL.md frontmatter"
else
    fail "T7: SKILL.md frontmatter" "head=$HEAD name=$NAME_OK desc=$DESC_OK"
fi

# ── T8: Description starts with bstack/discipline framing ─────────────────
echo "T8. Description has bstack P20 framing"
FIRST_BODY=$(awk '/^---$/{fence++; next} fence==1' "$REPO/SKILL.md")
if echo "$FIRST_BODY" | grep -q "bstack P20"; then
    ok "T8: P20 framing"
else
    fail "T8: P20 framing" "first body line: $FIRST_BODY"
fi

# ── T9-T13: the reviewer guard (BRO-2200) ─────────────────────────────────
#
# The property: a reviewer that writes produces no verdict at all. These tests
# run in a throwaway repo so a real tree is never mutated.

GUARD_TMP=$(mktemp -d)
trap 'rm -rf "$GUARD_TMP"' EXIT
(
  cd "$GUARD_TMP" || exit 1
  git init -q .
  git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  echo "original" > file.txt
  git add file.txt
  git -c user.email=t@t -c user.name=t commit -q -m add
) >/dev/null 2>&1

echo "T9. reviewer-guard capture writes a baseline"
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture 2>&1); RC=$?
if [ "$RC" -eq 0 ] && [ -f "$GUARD_TMP/.git/cross-review-guard.state" ]; then
    ok "T9: capture"
else
    fail "T9: capture" "rc=$RC out=$OUT"
fi

echo "T10. verify on an untouched tree is admissible (exit 0)"
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard verify 2>&1); RC=$?
if [ "$RC" -eq 0 ] && echo "$OUT" | grep -q "unchanged"; then
    ok "T10: clean verify passes"
else
    fail "T10: clean verify passes" "rc=$RC out=$OUT"
fi

echo "T11. a reviewer that edits a tracked file invalidates the review (exit 4)"
(cd "$GUARD_TMP" && echo "the reviewer fixed it" >> file.txt)
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard verify 2>&1); RC=$?
if [ "$RC" -eq 4 ] && echo "$OUT" | grep -q "REVIEW INVALID"; then
    ok "T11: tracked-file write detected"
else
    fail "T11: tracked-file write detected" "rc=$RC out=$OUT"
fi
(cd "$GUARD_TMP" && git checkout -q -- file.txt)

echo "T12. a reviewer that adds an untracked file is also caught"
(cd "$GUARD_TMP" && echo "sneaky" > extra.txt)
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard verify 2>&1); RC=$?
if [ "$RC" -eq 4 ]; then
    ok "T12: untracked write detected"
else
    fail "T12: untracked write detected" "rc=$RC out=$OUT — an -uall-less status would miss this"
fi
(cd "$GUARD_TMP" && rm -f extra.txt)

echo "T13. no baseline is NOT a pass — it is unverifiable (exit 4)"
(cd "$GUARD_TMP" && rm -f .git/cross-review-guard.state)
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard verify 2>&1); RC=$?
if [ "$RC" -eq 4 ] && echo "$OUT" | grep -q "NO BASELINE"; then
    ok "T13: missing baseline is not silence"
else
    fail "T13: missing baseline is not silence" "rc=$RC out=$OUT"
fi

echo "T16. a content change that leaves 'git status' identical is still caught"
# The status line alone cannot see this: the file is modified at capture AND at
# verify, so `git status --porcelain` prints the identical ' M file.txt' both
# times. Only hashing the actual diff distinguishes them. Without this test the
# `git diff HEAD` half of the fingerprint is dead weight nothing exercises —
# which is exactly what the mutation sweep reported before it was added.
(cd "$GUARD_TMP" && echo "reviewer-was-here-A" >> file.txt)
(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture >/dev/null 2>&1)
STATUS_AT_CAPTURE=$(cd "$GUARD_TMP" && git -c core.fsmonitor=false status --porcelain=v1 -uall)
# same status shape, different bytes
(cd "$GUARD_TMP" && sed -i.bak 's/reviewer-was-here-A/reviewer-was-here-B/' file.txt && rm -f file.txt.bak)
STATUS_AT_VERIFY=$(cd "$GUARD_TMP" && git -c core.fsmonitor=false status --porcelain=v1 -uall)
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard verify 2>&1); RC=$?
if [ "$STATUS_AT_CAPTURE" != "$STATUS_AT_VERIFY" ]; then
    fail "T16: precondition" "status differed, so this does not test the diff half"
elif [ "$RC" -eq 4 ]; then
    ok "T16: content change under identical status detected"
else
    fail "T16: content change under identical status detected" "rc=$RC out=$OUT"
fi
(cd "$GUARD_TMP" && git checkout -q -- file.txt && rm -f .git/cross-review-guard.state)

echo "T17. a file added inside an UNTRACKED DIRECTORY is caught"
# Plain `git status --porcelain` collapses an untracked directory to one
# '?? newdir/' line that is byte-identical no matter what the reviewer puts in
# it, and `git diff HEAD` does not see untracked content at all. The untracked
# CONTENT hash is what closes this. (It was briefly `-uall` on status; the sweep
# showed that flag became indistinguishable from its absence once contents were
# hashed, so it was removed rather than left as untested surface.)
(cd "$GUARD_TMP" && mkdir -p newdir && echo a > newdir/a.txt)
(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture >/dev/null 2>&1)
NORMAL_BEFORE=$(cd "$GUARD_TMP" && git -c core.fsmonitor=false status --porcelain=v1)
(cd "$GUARD_TMP" && echo b > newdir/b.txt)
NORMAL_AFTER=$(cd "$GUARD_TMP" && git -c core.fsmonitor=false status --porcelain=v1)
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard verify 2>&1); RC=$?
if [ "$NORMAL_BEFORE" != "$NORMAL_AFTER" ]; then
    fail "T17: precondition" "plain status already differed; this no longer tests -uall"
elif [ "$RC" -eq 4 ]; then
    ok "T17: write inside an untracked directory detected"
else
    fail "T17: write inside an untracked directory detected" "rc=$RC out=$OUT"
fi
(cd "$GUARD_TMP" && rm -rf newdir .git/cross-review-guard.state)

echo "T18. editing a file that was ALREADY untracked at capture is caught"
# status lists untracked PATHS, not their bytes; git diff HEAD does not see
# untracked files at all. Without hashing untracked contents this write was
# invisible to both halves of the fingerprint.
(cd "$GUARD_TMP" && echo "before" > loose.txt)
(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture >/dev/null 2>&1)
ST_BEFORE=$(cd "$GUARD_TMP" && git -c core.fsmonitor=false status --porcelain=v1 -uall)
(cd "$GUARD_TMP" && echo "reviewer edited me" > loose.txt)
ST_AFTER=$(cd "$GUARD_TMP" && git -c core.fsmonitor=false status --porcelain=v1 -uall)
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard verify 2>&1); RC=$?
if [ "$ST_BEFORE" != "$ST_AFTER" ]; then
    fail "T18: precondition" "status differed; this does not test content hashing"
elif [ "$RC" -eq 4 ]; then
    ok "T18: untracked content change detected"
else
    fail "T18: untracked content change detected" "rc=$RC out=$OUT"
fi
(cd "$GUARD_TMP" && rm -f loose.txt .git/cross-review-guard.state)

echo "T19. outside a git repo the guard is unverifiable, not clean"
# The old fingerprint discarded git errors, so both calls returning nothing
# hashed the empty string — identical before and after, a vacuous pass.
NOGIT=$(mktemp -d)
OUT=$(cd "$NOGIT" && bash "$CROSS_REVIEW_SH" reviewer-guard capture --state="$NOGIT/s" 2>&1); RC=$?
if [ "$RC" -ne 0 ]; then
    ok "T19: refuses to capture where nothing can be observed (rc=$RC)"
else
    fail "T19: refuses to capture where nothing can be observed" "rc=0 out=$OUT"
fi
rm -rf "$NOGIT"

echo "T20. an unwritable state path fails closed"
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture --state=/nonexistent-dir/s 2>&1); RC=$?
if [ "$RC" -eq 4 ]; then
    ok "T20: unwritable baseline is exit 4"
else
    fail "T20: unwritable baseline is exit 4" "rc=$RC out=$OUT"
fi

echo "T21. an EMPTY baseline is unverifiable, not a match"
(cd "$GUARD_TMP" && : > .git/cross-review-guard.state)
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard verify 2>&1); RC=$?
if [ "$RC" -eq 4 ] && echo "$OUT" | grep -q "is EMPTY"; then
    ok "T21: empty baseline is diagnosed as unverifiable"
else
    fail "T21: empty baseline is diagnosed as unverifiable" \
         "rc=$RC out=$OUT — exit 4 alone is not enough: the mismatch path also returns 4, so without asserting the DIAGNOSIS this test passes with the empty-baseline check deleted"
fi
(cd "$GUARD_TMP" && rm -f .git/cross-review-guard.state)

echo "T22. a repo with no commits fails closed rather than capturing an empty baseline"
# The only place the DIFF error path is reachable on its own: `git status`
# succeeds in a freshly-init'd repo, `git diff HEAD` does not. Without this, the
# status guard alone satisfied every error test and the diff guard was untested.
NOCOMMIT=$(mktemp -d)
(cd "$NOCOMMIT" && git init -q .) >/dev/null 2>&1
OUT=$(cd "$NOCOMMIT" && bash "$CROSS_REVIEW_SH" reviewer-guard capture --state="$NOCOMMIT/s" 2>&1); RC=$?
if [ "$RC" -eq 4 ] && [ ! -s "$NOCOMMIT/s" ]; then
    ok "T22: no-HEAD repo refuses to capture"
else
    fail "T22: no-HEAD repo refuses to capture" "rc=$RC out=$OUT — a baseline written here would certify nothing"
fi
rm -rf "$NOCOMMIT"

echo "T23. an untracked file whose NAME looks like an option is still hashed by content"
# shasum would read a file called "--help" as a FLAG, emitting output that does
# not depend on the file, so every later edit to it stayed invisible.
(cd "$GUARD_TMP" && printf 'v1' > -- 2>/dev/null; printf 'v1' > ./--help)
(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture >/dev/null 2>&1)
(cd "$GUARD_TMP" && printf 'v2-reviewer-edited' > ./--help)
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard verify 2>&1); RC=$?
if [ "$RC" -eq 4 ]; then
    ok "T23: option-like untracked filename hashed by content"
else
    fail "T23: option-like untracked filename hashed by content" "rc=$RC out=$OUT"
fi
(cd "$GUARD_TMP" && rm -f ./--help ./-- .git/cross-review-guard.state)

echo "T24. capture refuses to clobber a baseline another review is using"
(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture >/dev/null 2>&1)
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture 2>&1); RC=$?
if [ "$RC" -eq 4 ] && echo "$OUT" | grep -q "already exists"; then
    ok "T24: second capture refuses rather than replacing"
else
    fail "T24: second capture refuses rather than replacing" "rc=$RC out=$OUT — auto-capture on pre-push makes this reachable"
fi

echo "T25. --force replaces deliberately, --run-id scopes instead"
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture --force 2>&1); RC=$?
[ "$RC" -eq 0 ] || fail "T25a: --force replaces" "rc=$RC out=$OUT"
OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture --run-id=alpha 2>&1); RC=$?
if [ "$RC" -eq 0 ] && [ -s "$GUARD_TMP/.git/cross-review-guard.alpha.state" ]; then
    ok "T25: --force replaces, --run-id gives a concurrent review its own baseline"
else
    fail "T25: run-scoped baseline" "rc=$RC out=$OUT"
fi
(cd "$GUARD_TMP" && rm -f .git/cross-review-guard*.state)

echo "T26. an unreadable untracked file fails the fingerprint rather than contributing nothing"
# A file that cannot be hashed used to be skipped silently, so its bytes were
# simply absent from the fingerprint — indistinguishable from a file that had
# not changed.
(cd "$GUARD_TMP" && printf 'secret' > locked.txt && chmod 000 locked.txt)
if [ -r "$GUARD_TMP/locked.txt" ]; then
    # running as root, or a filesystem that ignores the mode — the experiment
    # cannot be performed, and saying so beats reporting a pass.
    echo "  [skip] T26: cannot make a file unreadable here (running as root?)"
else
    OUT=$(cd "$GUARD_TMP" && bash "$CROSS_REVIEW_SH" reviewer-guard capture 2>&1); RC=$?
    if [ "$RC" -ne 0 ]; then
        ok "T26: unreadable untracked file fails closed"
    else
        fail "T26: unreadable untracked file fails closed" "rc=$RC out=$OUT"
    fi
fi
(cd "$GUARD_TMP" && chmod 644 locked.txt 2>/dev/null; rm -f locked.txt .git/cross-review-guard*.state)

# ── T14: the dispatch names a read-only agent type ────────────────────────
echo "T14. Strata B dispatches read-only, not general-purpose"
SB=$(sed -n "/Strata B: fresh-context subagent/,/dispatches the subagent/p" "$CROSS_REVIEW_SH")
if echo "$SB" | grep -q "subagent_type='Explore'" \
   && ! echo "$SB" | grep -q "subagent_type='general-purpose'"; then
    ok "T14: read-only dispatch"
else
    fail "T14: read-only dispatch" "Strata B block still names a writable agent type"
fi

echo "T15. Strata A runs Codex sandboxed read-only"
SA=$(sed -n "/Strata A: cross-vendor/,/runs the Codex call/p" "$CROSS_REVIEW_SH")
if echo "$SA" | grep -q "sandbox_mode=read-only"; then
    ok "T15: codex sandboxed"
else
    fail "T15: codex sandboxed" "Strata A does not pin a read-only sandbox"
fi

# ── Summary ───────────────────────────────────────────────────────────────
# ── T16: --max-rounds is retired and fails LOUDLY ─────────────────────────
# The flag was accepted-and-ignored for its whole life. Silently continuing to
# accept it would reproduce the exact defect BRO-2240 removes.
echo "T16. retired --max-rounds exits 2"
EXIT=0
bash "$CROSS_REVIEW_SH" pre-push --max-rounds=5 >/dev/null 2>&1 || EXIT=$?
if [ "$EXIT" = "2" ]; then
    ok "T16: --max-rounds rejected"
else
    fail "T16: --max-rounds rejected" "got exit $EXIT, want 2"
fi

# ── T17: `round` delegates to the budget controller ───────────────────────
echo "T17. round subcommand delegates to round-budget.sh"
TMP17=$(mktemp); trap 'rm -f "$TMP17"' EXIT
OUT=$(ROUND_BUDGET_TEST_LEDGER=1 bash "$CROSS_REVIEW_SH" round budget --run-id=t17 --ledger="$TMP17" 2>&1 || true)
if echo "$OUT" | grep -q "AUTHORIZED"; then
    ok "T17: round delegation"
else
    fail "T17: round delegation" "output: $OUT"
fi

# ── T18: pre-push no longer advertises a fixed cap ────────────────────────
echo "T18. pre-push banner states the dynamic budget"
OUT=$(bash "$CROSS_REVIEW_SH" pre-push --diff-base=HEAD 2>&1 || true)
if echo "$OUT" | grep -q "Round budget:" && ! echo "$OUT" | grep -q "Max fix rounds"; then
    ok "T18: banner shows dynamic budget"
else
    fail "T18: banner shows dynamic budget" "banner still advertises a fixed cap"
fi

# ── T19: the budget's run-id is STABLE across pre-push invocations ────────
# It used to be `pp$$` -- the PID -- so every pre-push handed back a fresh empty
# ledger. The documented loop re-runs pre-push each round, so the round-8 ceiling
# cost one changed string to escape and the CLI changed it for you.
echo "T19. budget run-id is stable across invocations"
A=$(FORCE_GATE=1 bash "$CROSS_REVIEW_SH" pre-push --diff-base=HEAD 2>/dev/null | grep -o 'budget --run-id=[^ ]*' | head -1)
B=$(FORCE_GATE=1 bash "$CROSS_REVIEW_SH" pre-push --diff-base=HEAD 2>/dev/null | grep -o 'budget --run-id=[^ ]*' | head -1)
if [ -n "$A" ] && [ "$A" = "$B" ]; then
    ok "T19: arc id stable ($A)"
else
    fail "T19: arc id stable" "run1='$A' run2='$B' — a per-invocation id resets the budget"
fi

# ── T20: the guard id is NOT stable — it must stay per-invocation ─────────
# Same-id capture twice is a collision the guard is right to refuse, so the two
# identities must not be collapsed into one.
echo "T20. reviewer-guard id stays per-invocation"
GA=$(FORCE_GATE=1 bash "$CROSS_REVIEW_SH" pre-push --diff-base=HEAD 2>/dev/null | grep -o 'reviewer-guard verify --run-id=[^ ]*' | head -1)
GB=$(FORCE_GATE=1 bash "$CROSS_REVIEW_SH" pre-push --diff-base=HEAD 2>/dev/null | grep -o 'reviewer-guard verify --run-id=[^ ]*' | head -1)
if [ -n "$GA" ] && [ "$GA" != "$GB" ]; then
    ok "T20: guard id distinct per run"
else
    fail "T20: guard id distinct per run" "guard ids matched ('$GA') — a second capture would collide"
fi

echo ""
echo "── results ────────────────────────────────────────────────────"
echo "  $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "  Failed:"
    for t in "${FAILED[@]}"; do echo "    - $t"; done
    exit 1
fi
echo "  all green ✓"
