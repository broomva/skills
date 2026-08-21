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
  cd "$GUARD_TMP"
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

echo "T17. a file added inside an UNTRACKED DIRECTORY is caught (-uall is load-bearing)"
# T12 covers a top-level untracked file, which plain `git status --porcelain`
# reports anyway — so it never tested what -uall buys. Inside an untracked
# directory, -unormal collapses the whole tree to one '?? newdir/' line that is
# byte-identical no matter what the reviewer puts in it, and `git diff HEAD`
# does not see untracked content at all. -uall is the only thing closing that.
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
echo ""
echo "── results ────────────────────────────────────────────────────"
echo "  $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "  Failed:"
    for t in "${FAILED[@]}"; do echo "    - $t"; done
    exit 1
fi
echo "  all green ✓"
