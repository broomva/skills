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

# ── T1: --help prints usage block, as TEXT ────────────────────────────────
# `grep -q "Usage:"` alone could not see the defect it was meant to cover: the
# help is the file's own comment block with the markers stripped by sed, and the
# strip used `\?`, a GNU extension BSD sed reads as a literal '?'. So on macOS
# every line printed with its '#' still on it -- and "# Usage:" contains
# "Usage:", so this test stayed green through it. Assert the stripping.
echo "T1. --help prints Usage as text, not as comments"
OUT=$(bash "$CROSS_REVIEW_SH" --help 2>&1 || true)
HASHED=$(printf '%s\n' "$OUT" | grep -c '^#' || true)
if echo "$OUT" | grep -q "Usage:" && echo "$OUT" | grep -q -- "cross-review pre-push" && [ "$HASHED" = "0" ]; then
    ok "T1: help renders"
else
    fail "T1: help renders" "$HASHED line(s) still carry a leading '#'; output: $OUT"
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

# ── T27-T28: the printed Strata A command, run exactly as printed ─────────
# A stub `codex` records its argv and stdin, so the command an agent would copy
# really executes without contacting anything. It runs from a directory that is
# not a git repo, against a copy of the skill installed under a path with a
# space, so an unquoted rubric path shows up as a broken prompt. The only edit
# to the printed text is the stdin path: the real /tmp/cross-review-diff.patch
# may belong to a review in progress. No trap: T17's would replace it.
CX_TMP=$(mktemp -d)
CX_SKILL="$CX_TMP/skill dir/cross-review"
mkdir -p "$CX_TMP/skill dir" "$CX_TMP/bin" "$CX_TMP/cwd"
cp -R "$REPO" "$CX_SKILL"
cat > "$CX_TMP/bin/codex" <<'STUB'
#!/usr/bin/env bash
printf '%s\0' "$@" > "$CODEX_STUB_ARGV"
cat > "$CODEX_STUB_STDIN"
STUB
chmod +x "$CX_TMP/bin/codex"
printf 'diff --git a/probe b/probe\n+stdin-marker-5821\n' > "$CX_TMP/diff.patch"

# Runs pre-push's step-2 command as printed; fills CX_ARGV from the stub.
# $1 is CROSS_REVIEW_CODEX_MODEL ('' = unset). The command's own exit status
# is ignored on purpose: an injected second command may fail after the stub ran.
run_printed_codex() {
    local cmd a
    CX_ARGV=()
    rm -f "$CX_TMP/argv" "$CX_TMP/stdin"
    cmd=$(PATH="$CX_TMP/bin:$PATH" CROSS_REVIEW_CODEX_MODEL="$1" FORCE_GATE=1 \
            bash "$CX_SKILL/scripts/cross-review.sh" pre-push --diff-base=HEAD 2>/dev/null \
          | sed -n '/^ *codex exec -c/,/cross-review-diff\.patch$/p' | sed 's/^ *//')
    cmd=${cmd//\/tmp\/cross-review-diff.patch/$CX_TMP/diff.patch}
    [ -n "$cmd" ] || return 0
    (cd "$CX_TMP/cwd" && PATH="$CX_TMP/bin:$PATH" CODEX_STUB_ARGV="$CX_TMP/argv" \
        CODEX_STUB_STDIN="$CX_TMP/stdin" bash -c "$cmd") >/dev/null 2>&1
    [ -f "$CX_TMP/argv" ] || return 0
    while IFS= read -r -d '' a; do CX_ARGV+=("$a"); done < "$CX_TMP/argv"
}

echo "T27. a model value containing a space or ';' stays one argument"
CANARY="$CX_TMP/cwd/canary"
MODEL27="gpt-x; touch $CANARY"
run_printed_codex "$MODEL27"
M27=""
for ((i = 0; i < ${#CX_ARGV[@]}; i++)); do
    [ "${CX_ARGV[$i]}" = "-m" ] && M27="${CX_ARGV[$((i + 1))]:-}"
done
if [ ! -e "$CANARY" ] && [ "$M27" = "$MODEL27" ]; then
    ok "T27: model value is quoted"
else
    fail "T27: model value is quoted" "canary created: $([ -e "$CANARY" ] && echo yes || echo no); -m received: '$M27'"
fi

echo "T28. the Codex prompt is the Strata-A preamble, then the rubric"
PREAMBLE=$(awk '/^## Strata-A specific/ {f = 1; next} /^## / {f = 0} f && /^> / {sub(/^> /, ""); print}' "$REPO/references/rubric.md")
run_printed_codex ""
N28=${#CX_ARGV[@]}
PROMPT28=""; FLAGS28=""
if [ "$N28" -gt 0 ]; then
    PROMPT28="${CX_ARGV[$((N28 - 1))]}"
    for ((i = 0; i < N28 - 1; i++)); do FLAGS28="$FLAGS28 ${CX_ARGV[$i]}"; done
fi
case "$PROMPT28" in
    "$PREAMBLE"*) STARTS28=1 ;;
    *) STARTS28=0 ;;
esac
if [ -n "$PREAMBLE" ] && [ "$STARTS28" = "1" ] \
   && printf '%s\n' "$PROMPT28" | grep -q '^# Anti-Slop Rubric' \
   && [ "$FLAGS28" = " exec -c sandbox_mode=read-only" ] \
   && grep -q 'stdin-marker-5821' "$CX_TMP/stdin" 2>/dev/null; then
    ok "T28: prompt composed preamble-first, diff on stdin"
else
    fail "T28: prompt composed preamble-first, diff on stdin" \
        "flags:'$FLAGS28' first line:'$(printf '%s\n' "$PROMPT28" | head -1)' preamble:'$PREAMBLE'"
fi
rm -rf "$CX_TMP"

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
# --diff-base is varied deliberately. Under `HEAD` the merge-base is degenerate,
# so a merge-base-derived id looked stable while actually changing on every
# commit -- the test passed for an id that reset constantly. Running the two
# invocations against DIFFERENT bases pins the property that matters: the id
# depends on the branch and on nothing that moves under a commit or a rebase.
A=$(FORCE_GATE=1 bash "$CROSS_REVIEW_SH" pre-push --diff-base=HEAD 2>/dev/null | grep -o 'budget --run-id=[^ ]*' | head -1)
B=$(FORCE_GATE=1 bash "$CROSS_REVIEW_SH" pre-push --diff-base=HEAD~1 2>/dev/null | grep -o 'budget --run-id=[^ ]*' | head -1)
BRANCH=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -n "$A" ] && [ "$A" = "$B" ]; then
    if [ -n "$BRANCH" ] && [ "$BRANCH" != "HEAD" ] && [ "$A" != "budget --run-id=arc-$(printf '%s' "$BRANCH" | tr -c 'A-Za-z0-9._-' '-')" ]; then
        fail "T19: arc id stable" "id '$A' is not exactly arc-<branch>; something that moves is baked in"
    else
        ok "T19: arc id stable across diff-bases ($A)"
    fi
else
    fail "T19: arc id stable" "base=HEAD gave '$A', base=HEAD~1 gave '$B' — the id moves with the merge-base"
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

# ── T21: the round budget prints even when Codex is absent ────────────────
# It lived inside the Strata A block, which only runs when `codex` is on PATH.
# The arc id therefore printed on a developer machine and vanished on a CI
# runner, and T19 failed there for a reason unrelated to what it tested. Every
# stratum shares one budget, so it must print unconditionally.
echo "T21. round budget prints on a runner without codex"
OUT=$(PATH="/usr/bin:/bin:/usr/sbin:/sbin" FORCE_GATE=1 bash "$CROSS_REVIEW_SH" pre-push --diff-base=HEAD 2>/dev/null | grep -o 'budget --run-id=[^ ]*' | head -1)
if [ -n "$OUT" ]; then
    ok "T21: budget section is stratum-independent ($OUT)"
else
    fail "T21: budget section is stratum-independent" "no arc id printed without codex on PATH"
fi

# ── T22: the SKILL.md enforcement table must not describe retired mechanics ──
# The arc-id row has now been wrong twice: it described `pp$$` after that was
# replaced, then `branch + merge-base` after THAT was replaced -- and the second
# time it was falsified by the very commit that was fixing the first. A doc table
# nothing pins is a doc table that drifts, so the retired mechanics are asserted
# absent rather than trusted to be updated.
echo "T22. SKILL.md does not describe retired arc-id mechanics"
# A POSITIVE assertion on the row, not a banned word. Banning "merge-base"
# outright also flags the row's own account of what it replaced, and a test that
# forbids describing history would push the doc toward saying less, not more.
# What must hold is that the row states the CURRENT derivation.
SKILL="$REPO/SKILL.md"
ROW=$(grep -E '^\| .*ledger id' "$SKILL" | head -1)
if [ -z "$ROW" ]; then
    fail "T22: arc-id row states the current derivation" "no '| ... ledger id' row found in SKILL.md"
elif echo "$ROW" | grep -q 'branch alone'; then
    ok "T22: arc-id row states the current derivation"
else
    fail "T22: arc-id row states the current derivation" "row does not say 'branch alone': $ROW"
fi

# ── T23: every exit code SKILL.md documents is one the script can emit ────
echo "T23. documented exit codes exist in the controller"
RB_SH="$REPO/scripts/round-budget.sh"
# Codes now live in two places: literal `exit N`, and the `name:code` pairs in
# PRECEDENCE. Checking only the first went red the moment the dispatcher moved
# them, which is the test being wrong rather than the code.
MISSING=""
for code in 0 2 3 5 6 7; do
    grep -qE "exit $code" "$RB_SH" || grep -qE ":$code( |\")" "$RB_SH" || MISSING="$MISSING $code"
done
if [ -z "$MISSING" ]; then
    ok "T23: all documented exit codes are reachable"
else
    fail "T23: all documented exit codes are reachable" "documented but never emitted:$MISSING"
fi

# ── S-B: Strata B is not suppressed by codex being installed ─────────────
# `[ A ] || [ B ] && C` parses left-associatively as `(A||B) && C`, so an
# EXPLICIT --strata=B was suppressed whenever codex was on PATH -- silently
# skipping the stratum SKILL.md makes MANDATORY, for exactly the users who have
# the optional one installed. Asserted with codex present, which is the arm that
# was broken; `auto` deferring to codex is unchanged and covered elsewhere.
echo "S-B. an explicit --strata=B prints its block even when codex is installed"
# FORCE_GATE=1: on main (an empty diff vs origin/main) pre-push exits at the
# substantive-threshold skip BEFORE printing any stratum, so without it this
# test passed only on branches and failed on every main build (3fa6584bd).
SB_COUNT=$(FORCE_GATE=1 bash "$CROSS_REVIEW_SH" pre-push --strata=B 2>&1 | grep -c "Strata B")
SB_CODEX=$(command -v codex >/dev/null 2>&1 && echo present || echo absent)
if [ "$SB_COUNT" -ge 1 ]; then
    ok "S-B: --strata=B prints its block (codex $SB_CODEX, $SB_COUNT block(s))"
else
    fail "S-B: Strata B suppressed by operator precedence" "printed=$SB_COUNT with codex $SB_CODEX (want >=1)"
fi

# ── S-RULE: every surface that states the pass rule states the zero clause ──
# THE RECURRENCE THIS CLOSES. The zero clause was added to one surface per round
# for three consecutive rounds -- rubric.md's summary line, then its MUST-emit
# block, then the Strata-A sub-step, then the Strata-B sub-step, then the gate's
# closing "push only when" directive -- and each round the reviewer found the
# next one. Nothing tested them, so reverting ALL of the prose fixes reddened
# zero tests while every code hunk reddened precisely its own.
#
# That is the same defect this PR argues against in the code: a rule spelled once
# per site is forgotten once per site. The answer there was to derive the score
# in one place; the answer here is to ENUMERATE the sites and assert the rule at
# each, so adding a surface without the clause fails rather than waiting for a
# reviewer to notice.
#
# The enumeration is the load-bearing part. A surface added later and not listed
# here is still unguarded -- so the list is grepped from the files rather than
# hand-held where that is possible: any line stating a >=7 threshold must also
# carry the zero clause.
echo "S-RULE. no surface states the >=7 bar without the no-zero clause"
SRULE_BAD=""
for f in "$REPO/scripts/cross-review.sh" "$REPO/references/rubric.md" "$REPO/SKILL.md"; do
    [ -f "$f" ] || { SRULE_BAD="$SRULE_BAD missing:$(basename "$f")"; continue; }
    # Lines that state the THRESHOLD as a rule. The frontmatter description and
    # prose that merely mentions the number in passing are excluded by requiring
    # the line to also carry a pass/push/approve verb.
    # A TWO-LINE WINDOW, because grep is line-oriented and these statements wrap.
    # The first draft flagged two of its own fixes: the clause sat on the
    # continuation line, so the match line looked bare. A claim wrapped across a
    # newline is unmatchable by a line-oriented check, and reformatting the prose
    # to suit the checker would be fixing the corpus instead of the checker.
    while IFS= read -r ln; do
        n=${ln%%:*}
        window=$(sed -n "${n},$((n+1))p" "$f" | tr '\n' ' ')
        case "$window" in
            *"no dimension"*|*"no rubric dimension"*|*"zero"*|*"ZERO"*|*"axes"*|*"axis"*) continue ;;
        esac
        SRULE_BAD="$SRULE_BAD
    $(basename "$f"): $ln"
    done < <(grep -nE 'PASS at (≥7|>=7)|PASS: (≥7|>=7)|Threshold is (≥7|>=7)|Push only when|(≥7|>=7)[^.]*→ APPROVE|(≥7|>=7)( AND[^:]*)?[:]? pass|If score (≥7|>=7)' "$f" 2>/dev/null \
             | grep -vE '^[0-9]+:description:' || true)

    # The pattern above matches lines that state the threshold AS THE PASS RULE.
    # A first draft matched any line pairing ">=7" with a pass-ish word, and it
    # was wrong on half its firings -- SKILL.md's BRO-2615 row says "A round
    # scoring >=7 must carry --stratum=..." which is a PRECONDITION on a passing
    # round, not a statement of what passing is, and adding a zero clause there
    # would have made that sentence wrong. A checker wrong on half its firings
    # gets narrowed, not obeyed.
done
if [ -z "$SRULE_BAD" ]; then
    ok "S-RULE: every pass-rule surface in cross-review.sh, rubric.md and SKILL.md carries the no-zero clause"
else
    fail "S-RULE: a surface states the bar without the zero clause" "$SRULE_BAD"
fi

# ── S-LOOP: every arm's fix instruction covers what its pass rule refuses ──
# Step 4 refuses a round at >=7 with a zero. If step 5 only says "if score <7",
# that round matches NEITHER and the agent is given no instruction for the exact
# state this change introduces. The Strata-B arm folded both into one sentence
# and was fine; the Strata-A arm kept a bare `<7` and was not. Found by review
# after the pass rule itself had been fixed in five places -- the COMPLEMENT of a
# rule is a surface too.
echo "S-LOOP. no arm's fix-rescore instruction is narrower than its pass rule"
SLOOP_BAD=""
while IFS= read -r ln; do
    n=${ln%%:*}
    window=$(sed -n "${n},$((n+3))p" "$CROSS_REVIEW_SH" | tr '\n' ' ')
    case "$window" in
        *"dimension at 0"*|*"dimension scored 0"*|*"any dimension"*|*"with a zero"*|*"zero"*) continue ;;
    esac
    SLOOP_BAD="$SLOOP_BAD
    $ln"
done < <(grep -nE 'If score <7|score <7:|<7: fix|<7 fix' "$CROSS_REVIEW_SH" 2>/dev/null || true)
if [ -z "$SLOOP_BAD" ]; then
    ok "S-LOOP: every fix-rescore instruction covers the zero case its pass rule refuses"
else
    fail "S-LOOP: a fix instruction is narrower than its pass rule" "$SLOOP_BAD"
fi

# ── TIER: stakes tier from the diff's paths (BRO-2844) ────────────────────
echo ""
echo "TIER. knowledge-only diffs get the one-stratum claims review; anything else the full panel"
# A repo whose base commit holds base.txt plus any PRE paths ("pre:path"), and
# whose HEAD adds the other given paths (60 lines each, so every case clears the
# substantive threshold) or renames a pre path ("mv:src:dst").
tier_repo() {
    local dir; dir=$(mktemp -d)
    (
        cd "$dir" && git init -q . && echo base > base.txt
        for f in "$@"; do case "$f" in pre:*) f=${f#pre:}; mkdir -p "$(dirname "$f")"; seq 1 60 > "$f" ;; esac; done
        git add -A && git -c user.email=t@t -c user.name=t commit -qm base
        for f in "$@"; do
            case "$f" in
                pre:*) ;;
                mv:*) src=${f#mv:}; dst=${src#*:}; src=${src%%:*}; mkdir -p "$(dirname "$dst")"; git mv "$src" "$dst" ;;
                *) mkdir -p "$(dirname "$f")"; seq 1 60 > "$f" ;;
            esac
        done
        git add -A && git -c user.email=t@t -c user.name=t commit -qm change
    ) >/dev/null 2>&1
    echo "$dir"
}
# PATH without codex, so the stratum is deterministic (B) unless a test adds a stub.
tier_run() {
    local dir=$1; shift
    (cd "$dir" && PATH="${TIER_PATH:-/usr/bin:/bin:/usr/sbin:/sbin}" bash "$CROSS_REVIEW_SH" pre-push --diff-base=HEAD~1 "$@" 2>&1)
}
has() { printf '%s' "$1" | grep -qF -- "$2"; }
KNOW=$(tier_repo research/notes/a.md research/notes/b.md research/entities/c.md \
    research/imported-documents/X_Checkit/d.txt research/imported-documents/X_Checkit/SHA256SUMS docs/knowledge-index.md)
OUT=$(tier_run "$KNOW")
if has "$OUT" "Stakes tier:      knowledge" && has "$OUT" "Strata C: skipped" \
   && has "$OUT" "Read references/claims-rubric.md" && has "$OUT" "--stratum=B:" \
   && ! has "$OUT" "--stratum=C:" && ! has "$OUT" "Strata C: composed"; then
    ok "TIER1: notes, entities, evidence and the index are the knowledge tier; B alone gets the claims rubric"
else
    fail "TIER1: knowledge-only diff was not given the knowledge tier" "$(printf '%s' "$OUT" | grep -E 'Stakes tier|Strata C|stratum=' | head -4)"
fi
MIXED=$(tier_repo research/notes/a.md research/notes/b.md research/entities/c.md scripts/tool.sh)
OUT=$(tier_run "$MIXED")
if has "$OUT" "Stakes tier:      code" && has "$OUT" "Strata C: composed" && has "$OUT" "Read references/rubric.md"; then
    ok "TIER2: one path outside the knowledge locations makes the whole diff the code tier"
else
    fail "TIER2: a mixed diff was not given the code tier" "$(printf '%s' "$OUT" | grep -E 'Stakes tier|Strata C' | head -3)"
fi
OUT=$(tier_run "$KNOW" --tier=code)
if has "$OUT" "Stakes tier:      code" && has "$OUT" "Strata C: composed"; then
    ok "TIER3: --tier=code escalates a knowledge diff to the full panel"
else
    fail "TIER3: --tier=code did not escalate" "$(printf '%s' "$OUT" | grep -E 'Stakes tier' | head -2)"
fi
OUT=$(tier_run "$KNOW" --tier=knowledge); RC=$?
if [ "$RC" = "2" ] && has "$OUT" "--tier accepts only 'code'"; then
    ok "TIER4: --tier=knowledge is refused with its own message (exit 2)"
else
    fail "TIER4: --tier=knowledge was not refused by the --tier parser" "exit $RC: $(printf '%s' "$OUT" | head -1)"
fi
LOOKALIKE=$(tier_repo research-tools/a.md research/entities-old/b.md docs/knowledge-index.md.bak research/notes/c.md)
OUT=$(tier_run "$LOOKALIKE")
if has "$OUT" "Stakes tier:      code"; then
    ok "TIER5: look-alike paths (research-tools/, research/entities-old/, knowledge-index.md.bak) are not knowledge"
else
    fail "TIER5: a look-alike path was read as knowledge" "$(printf '%s' "$OUT" | grep -E 'Stakes tier' | head -1)"
fi
CODEPROJ=$(tier_repo research/kaggriculture/main.py research/kaggriculture/bots/v5.py research/notes/a.md research/notes/b.md)
OUT=$(tier_run "$CODEPROJ")
if has "$OUT" "Stakes tier:      code"; then
    ok "TIER6: a code project under research/ is the code tier"
else
    fail "TIER6: code under research/ got the knowledge tier" "$(printf '%s' "$OUT" | grep -E 'Stakes tier' | head -1)"
fi
SCRIPTED=$(tier_repo research/imported-documents/Y_Checkit/capture.sh research/notes/a.md research/notes/b.md research/entities/c.md)
OUT=$(tier_run "$SCRIPTED")
if has "$OUT" "Stakes tier:      code"; then
    ok "TIER7: a script inside an evidence folder is the code tier"
else
    fail "TIER7: an evidence-folder script got the knowledge tier" "$(printf '%s' "$OUT" | grep -E 'Stakes tier' | head -1)"
fi
RENAMED=$(tier_repo pre:scripts/t1.sh pre:scripts/t2.sh pre:scripts/t3.sh pre:scripts/t4.sh \
    mv:scripts/t1.sh:research/notes/t1.md mv:scripts/t2.sh:research/notes/t2.md \
    mv:scripts/t3.sh:research/notes/t3.md mv:scripts/t4.sh:research/notes/t4.md)
OUT=$(tier_run "$RENAMED")
if has "$OUT" "Stakes tier:      code"; then
    ok "TIER8: a rename from scripts/ into research/notes/ counts its source path and is the code tier"
else
    fail "TIER8: a rename into research/ hid its source path" "$(printf '%s' "$OUT" | grep -E 'Stakes tier|Diff scope' | head -2)"
fi
UNICODE=$(tier_repo "research/entities/café.md" research/notes/a.md research/notes/b.md research/notes/c.md)
OUT=$(tier_run "$UNICODE")
if has "$OUT" "Stakes tier:      knowledge"; then
    ok "TIER9: a non-ASCII knowledge path is matched (core.quotePath off)"
else
    fail "TIER9: a non-ASCII knowledge path fell to the code tier" "$(printf '%s' "$OUT" | grep -E 'Stakes tier' | head -1)"
fi
CAPTURES=$(tier_repo research/imported-documents/Z_Checkit/IMG_0001.HEIC research/imported-documents/Z_Checkit/frame.JPG \
    research/imported-documents/Z_Checkit/video.en.vtt research/imported-documents/Z_Checkit/events.jsonl)
OUT=$(tier_run "$CAPTURES")
if has "$OUT" "Stakes tier:      knowledge"; then
    ok "TIER9b: phone captures (.HEIC, .JPG), subtitles (.vtt) and .jsonl are knowledge, in any case"
else
    fail "TIER9b: a declarative capture fell to the code tier" "$(printf '%s' "$OUT" | grep -E 'Stakes tier' | head -1)"
fi
OUT=$(cd "$KNOW" && PATH="/usr/bin:/bin:/usr/sbin:/sbin" bash "$CROSS_REVIEW_SH" pre-push --diff-base=no-such-ref 2>&1)
if has "$OUT" "Stakes tier:      code"; then
    ok "TIER10: an unresolvable diff base is the code tier"
else
    fail "TIER10: unknown scope got the knowledge tier" "$(printf '%s' "$OUT" | grep -E 'Stakes tier' | head -1)"
fi
OUT=$(tier_run "$KNOW" --strata=A)
if has "$OUT" "Strata A was requested but" && has "$OUT" "Knowledge-tier stratum: none" && ! has "$OUT" "--stratum=B:"; then
    ok "TIER11: an explicit A without codex is announced and does not silently become B"
else
    fail "TIER11: explicit A without codex was rewritten or unannounced" "$(printf '%s' "$OUT" | grep -E 'NOTE|stratum' | head -3)"
fi
STUB=$(mktemp -d); printf '#!/bin/sh\nexit 0\n' > "$STUB/codex"; chmod +x "$STUB/codex"
OUT=$(TIER_PATH="$STUB:/usr/bin:/bin:/usr/sbin:/sbin" tier_run "$KNOW")
if has "$OUT" "Knowledge-tier stratum: A" && has "$OUT" "Strata A: cross-vendor" \
   && has "$OUT" "claims-rubric.md" && ! has "$OUT" "Strata B: fresh-context" \
   && has "$OUT" "--stratum=A:" && ! has "$OUT" "--stratum=C:"; then
    ok "TIER12: with codex present the knowledge tier runs A alone on the claims rubric"
else
    fail "TIER12: the knowledge tier with codex did not run A alone" "$(printf '%s' "$OUT" | grep -E 'stratum|Strata [ABC]' | head -4)"
fi
rm -rf "$KNOW" "$MIXED" "$LOOKALIKE" "$CODEPROJ" "$SCRIPTED" "$RENAMED" "$UNICODE" "$STUB"

echo ""
echo "── results ────────────────────────────────────────────────────"
echo "  $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "  Failed:"
    for t in "${FAILED[@]}"; do echo "    - $t"; done
    exit 1
fi
echo "  all green ✓"
