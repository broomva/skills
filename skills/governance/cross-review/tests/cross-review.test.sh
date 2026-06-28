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
bash "$CROSS_REVIEW_SH" bogus-command 2>&1 >/dev/null || EXIT=$?
if [ "$EXIT" = "2" ]; then
    ok "T3: exit 2 on unknown"
else
    fail "T3: exit 2 on unknown" "got exit $EXIT"
fi

# ── T4: missing --spec on plan exits 2 ────────────────────────────────────
echo "T4. plan without --spec exits 2"
EXIT=0
bash "$CROSS_REVIEW_SH" plan 2>&1 >/dev/null || EXIT=$?
if [ "$EXIT" = "2" ]; then
    ok "T4: plan requires --spec"
else
    fail "T4: plan requires --spec" "got exit $EXIT"
fi

# ── T5: missing --target on audit exits 2 ─────────────────────────────────
echo "T5. audit without --target exits 2"
EXIT=0
bash "$CROSS_REVIEW_SH" audit 2>&1 >/dev/null || EXIT=$?
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
