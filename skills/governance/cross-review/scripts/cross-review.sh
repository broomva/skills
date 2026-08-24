#!/usr/bin/env bash
# cross-review.sh — bstack P20 Cross-Model Adversarial Review Gate
#
# Routes substantive PRs through a different evaluator than the writer
# before merge. Three strata, ordered by signal strength:
#   A — Codex CLI cross-vendor (truest cross-model)
#   B — Fresh Agent subagent under devil's-advocate brief (cross-context)
#   C — Composed existing adversarial-review skills (always)
#
# Auto-detects environment: if `codex` CLI is on PATH, fires Strata A;
# otherwise falls back to Strata B. Always runs Strata C in parallel.
#
# Scoring: anti-slop rubric (see references/rubric.md). PASS at ≥7/10.
# Round budget is DYNAMIC: 3 free, 4-7 earned by a continuation verdict
# carrying a falsifiable prediction, >=8 escalates to a human. The budget is
# kept in a ledger by scripts/round-budget.sh -- see `cross-review round`.
#
# Usage:
#   cross-review pre-push                 # default: gate before push
#   cross-review pre-push --strata auto   # explicit auto-detect
#   cross-review pre-push --strata A      # force Codex cross-vendor
#   cross-review pre-push --strata B      # force subagent
#   cross-review pre-push --strata C      # composed skills only
#   cross-review plan --spec PATH         # plan-stage gate
#   cross-review audit --target PATH      # audit-on-demand
#   cross-review reviewer-guard capture   # fingerprint the tree before review
#   cross-review reviewer-guard verify    # fail if the reviewer wrote to it
#   cross-review round budget --run-id=ID # may another fix round run?
#   cross-review round record-round ...   # log a completed round
#   cross-review round record-verdict ... # log a continuation verdict
#   cross-review --help
#
# Mutation-proof (REPORTED SIGNAL on pre-push, never a blocker):
#   cross-review pre-push \
#     --mutation-target=scripts/foo.sh \
#     --mutation-test='bash tests/foo.test.sh'
#   Optional: --mutation-strategy=stub|revert --mutation-ref=REF
#             --mutation-root=DIR --mutation-paths=a,b

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUBRIC_FILE="$REPO/references/rubric.md"

# ─── Defaults ─────────────────────────────────────────────────────────────
COMMAND=""
STRATA="auto"
DIFF_BASE="origin/main"
SPEC=""
TARGET=""
CONCERNS=""
RUBRIC="anti-slop"
OUTPUT_FORMAT="pr-comment"
MUT_TARGET=""
MUT_TEST=""
MUT_STRATEGY="stub"
MUT_REF=""
MUT_ROOT=""
MUT_PATHS=""
GUARD_STATE=""
GUARD_MODE=""
RUN_ID=""
GUARD_FORCE=0

# ─── Arg parsing ──────────────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    echo "cross-review: no command. Run with --help" >&2
    exit 2
fi

COMMAND="$1"
shift

case "$COMMAND" in
    --help|-h|help)
        # `\?` is a GNU extension: BSD sed reads it as a literal '?', so the pattern
        # never matched and --help printed every line with its leading '#' still on
        # it -- on the one platform this is developed on. `\{0,1\}` is POSIX BRE and
        # means the same thing to both.
        sed -n '/^# Usage:/,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    pre-push|plan|audit|version|reviewer-guard)
        ;;
    round)
        # Delegate wholesale: the budget controller owns its own arg surface.
        exec bash "$(dirname "${BASH_SOURCE[0]}")/round-budget.sh" "$@"
        ;;
    *)
        echo "cross-review: unknown command '$COMMAND' (try: pre-push | plan | audit | --help)" >&2
        exit 2
        ;;
esac

for arg in "$@"; do
    case "$arg" in
        --strata=*) STRATA="${arg#*=}" ;;
        --diff-base=*) DIFF_BASE="${arg#*=}" ;;
        --spec=*) SPEC="${arg#*=}" ;;
        --target=*) TARGET="${arg#*=}" ;;
        --concerns=*) CONCERNS="${arg#*=}" ;;
        --max-rounds=*)
            # Accepted-and-ignored for its whole life: pre-push printed it and
            # nothing read it. Failing loudly is the entire point of BRO-2240 --
            # silently honouring a flag that no longer has a meaning would
            # reproduce the defect this change exists to remove.
            echo "cross-review: --max-rounds is retired. The budget is dynamic:" >&2
            echo "  3 free rounds, 4-7 earned by a continuation verdict carrying a" >&2
            echo "  falsifiable prediction, >=8 escalates to a human." >&2
            echo "  Drive it with: cross-review round budget --run-id=ID" >&2
            exit 2 ;;
        --rubric=*) RUBRIC="${arg#*=}" ;;
        --output=*) OUTPUT_FORMAT="${arg#*=}" ;;
        --mutation-target=*) MUT_TARGET="${arg#*=}" ;;
        --mutation-test=*) MUT_TEST="${arg#*=}" ;;
        --mutation-strategy=*) MUT_STRATEGY="${arg#*=}" ;;
        --mutation-ref=*) MUT_REF="${arg#*=}" ;;
        --mutation-root=*) MUT_ROOT="${arg#*=}" ;;
        --mutation-paths=*) MUT_PATHS="${arg#*=}" ;;
        --state=*) GUARD_STATE="${arg#*=}" ;;
        --run-id=*) RUN_ID="${arg#*=}" ;;
        --force) GUARD_FORCE=1 ;;
        capture|verify) GUARD_MODE="$arg" ;;
        *) echo "cross-review: unknown flag '$arg'" >&2; exit 2 ;;
    esac
done

# ─── Reviewer guard: the reviewer must not be able to write ──────────────
#
# A reviewer that can edit the tree does not report findings, it fixes them —
# and a finding that was silently fixed is indistinguishable from one that was
# never found. The gate keeps its authority; the REVIEWER loses its hands.
# (Non-writable observer, authority elsewhere.)
#
# Two layers, because a prose instruction is not a capability:
#   1. dispatch the reviewer with a read-only tool set (see the strata blocks)
#   2. this guard — fingerprint before, verify after. Layer 1 is the control;
#      this is the detector that proves layer 1 held.
#
# fsmonitor is forced off: this repo family sets core.fsmonitor=true, and a dead
# daemon makes `git status` report a CLEAN tree while files are modified — which
# would turn this detector into a rubber stamp exactly when it matters.
guard_fingerprint() {
    # Fail CLOSED. Previously both git calls were 2>/dev/null and their exit codes
    # discarded, so outside a repo (or with git broken) the fingerprint was the
    # hash of the empty string — identical at capture and verify, i.e. a vacuous
    # pass exactly when nothing could be observed.
    local st df untracked
    if ! st=$(git -c core.fsmonitor=false status --porcelain=v1 2>&1); then
        echo "reviewer-guard: git status failed: $st" >&2; return 1
    fi
    if ! df=$(git -c core.fsmonitor=false diff HEAD --no-ext-diff --no-textconv 2>&1); then
        echo "reviewer-guard: git diff failed: $df" >&2; return 1
    fi
    # `status` says nothing about untracked CONTENT and `git diff HEAD` does not
    # see untracked files at all, so a reviewer editing a file that was already
    # untracked at capture was invisible to both. Hashing the bytes closes that —
    # and subsumes `-uall`, which enumerated untracked names inside untracked
    # directories. That flag is deliberately gone: the mutation sweep showed no
    # test could tell it apart from its absence once contents are hashed, and a
    # rule nothing can distinguish is one more thing to maintain, not a defence.
    # NUL-delimited list via a FILE, not a variable: command substitution strips
    # NUL bytes, so `$(git ls-files -z)` silently concatenates every filename
    # into one string and the whole hash becomes meaningless.
    local list rc
    list=$(mktemp) || { echo "reviewer-guard: mktemp failed" >&2; return 1; }
    if ! git -c core.fsmonitor=false ls-files --others --exclude-standard -z > "$list" 2>/dev/null; then
        rm -f "$list"; echo "reviewer-guard: git ls-files failed" >&2; return 1
    fi
    local hashes
    hashes=$(mktemp) || { rm -f "$list"; return 1; }
    # "./" prefix and --: an untracked file literally named "--help" or "-a" would
    # otherwise be read by shasum as an OPTION, producing output independent of
    # that file, so later edits to it stay invisible. Errors fail the fingerprint
    # rather than silently contributing nothing.
    rc=0
    while IFS= read -r -d '' f; do
        [ -n "$f" ] || continue
        if ! shasum -a 256 -- "./$f" >> "$hashes" 2>/dev/null; then
            echo "reviewer-guard: cannot hash untracked file: $f" >&2; rc=1; break
        fi
    done < "$list"
    if [ "$rc" -ne 0 ]; then rm -f "$list" "$hashes"; return 1; fi
    untracked=$(sort < "$hashes")
    rm -f "$list" "$hashes"
    printf '%s\n%s\n%s\n' "$st" "$df" "$untracked" | shasum -a 256 | awk '{print $1}'
}

guard_state_path() {
    if [ -n "$GUARD_STATE" ]; then echo "$GUARD_STATE"; return; fi
    if [ -n "$RUN_ID" ]; then
        local gd2; gd2=$(git rev-parse --git-dir 2>/dev/null) || {
            echo "cross-review: reviewer-guard needs a git repo (or --state=PATH)" >&2; exit 2; }
        echo "$gd2/cross-review-guard.$RUN_ID.state"; return
    fi
    local gd; gd=$(git rev-parse --git-dir 2>/dev/null) || {
        echo "cross-review: reviewer-guard needs a git repo (or pass --state=PATH)" >&2
        exit 2
    }
    echo "$gd/cross-review-guard.state"
}

if [ "$COMMAND" = "reviewer-guard" ]; then
    STATE=$(guard_state_path)
    case "$GUARD_MODE" in
        capture)
            # `guard_fingerprint > "$STATE"` truncated the file BEFORE running, so a
            # failing fingerprint or an unwritable path still left a state file and
            # exited 0 — a baseline that certifies nothing.
            if ! FP=$(guard_fingerprint); then
                echo "reviewer-guard: cannot fingerprint; refusing to capture a baseline" >&2
                exit 4
            fi
            # Refuse to overwrite a live baseline. Auto-capture on pre-push made
            # this reachable: a second review starting in the same worktree used to
            # silently replace the first one's baseline, after which the first
            # review verified against the wrong tree and read as clean.
            if [ -s "$STATE" ] && [ "$GUARD_FORCE" != "1" ]; then
                echo "reviewer-guard: a baseline already exists at $STATE — another" >&2
                echo "  review may be in flight. Pass --run-id to scope this one, or" >&2
                echo "  --force to replace it deliberately." >&2
                exit 4
            fi
            if ! printf '%s\n' "$FP" > "$STATE" 2>/dev/null; then
                echo "reviewer-guard: cannot write state to $STATE" >&2
                exit 4
            fi
            echo "reviewer-guard: captured ${FP:0:16}… -> $STATE"
            exit 0
            ;;
        verify)
            if [ ! -f "$STATE" ]; then
                # "I never captured" and "nothing changed" must not look alike.
                echo "reviewer-guard: NO BASELINE at $STATE — capture before dispatching the" >&2
                echo "  reviewer. An unverifiable review is not a passed review." >&2
                exit 4
            fi
            BEFORE=$(cat "$STATE")
            if ! AFTER=$(guard_fingerprint); then
                echo "reviewer-guard: cannot fingerprint at verify — unverifiable, not clean" >&2
                exit 4
            fi
            if [ -z "$BEFORE" ]; then
                echo "reviewer-guard: baseline at $STATE is EMPTY — unverifiable" >&2
                exit 4
            fi
            if [ "$BEFORE" = "$AFTER" ]; then
                echo "reviewer-guard: tree unchanged across review — verdict is admissible"
                exit 0
            fi
            echo "reviewer-guard: REVIEW INVALID — the tree changed while the reviewer ran." >&2
            echo "  A reviewer that writes is optimising for a clean report, not an honest one." >&2
            echo "  before=$(echo "$BEFORE" | cut -c1-16)… after=$(echo "$AFTER" | cut -c1-16)…" >&2
            git -c core.fsmonitor=false status --porcelain=v1 -uall >&2
            echo "  Discard this verdict, revert the reviewer's writes, re-run the review." >&2
            exit 4
            ;;
        *)
            echo "cross-review: reviewer-guard needs 'capture' or 'verify'" >&2
            exit 2
            ;;
    esac
fi

# ─── Strata auto-detect ──────────────────────────────────────────────────
detect_strata() {
    if [ "$STRATA" != "auto" ]; then
        echo "$STRATA"
        return
    fi
    if command -v codex >/dev/null 2>&1; then
        echo "A"
    else
        echo "B"
    fi
}

# ─── Version ─────────────────────────────────────────────────────────────
if [ "$COMMAND" = "version" ]; then
    echo "cross-review v0.0.1 (bstack P20 Cross-Model Adversarial Review Gate)"
    exit 0
fi

# ─── Pre-push gate (canonical) ───────────────────────────────────────────
if [ "$COMMAND" = "pre-push" ]; then
    SELECTED_STRATA="$(detect_strata)"
    echo "  ┌───────────────────────────────────────────────────────────┐"
    echo "  │  cross-review pre-push — bstack P20 adversarial gate     │"
    echo "  └───────────────────────────────────────────────────────────┘"
    echo ""
    echo "  Strata selected:  $SELECTED_STRATA"
    echo "  Diff base:        $DIFF_BASE"
    echo "  Rubric:           $RUBRIC"
    echo "  Round budget:     3 free / 4-7 earned / >=8 human (cross-review round)"
    echo "  Rubric file:      $RUBRIC_FILE"
    echo "  Verdict format:   $OUTPUT_FORMAT"
    echo ""

    # Compute changed files + size to enforce substantive-threshold rule
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        echo "[cross-review] not inside a git repo; exiting" >&2
        exit 2
    fi

    # An unresolvable diff base is common and must not be fatal: a fork, a
    # non-`main` default branch, or a shallow CI checkout all leave
    # `origin/main` absent. `git diff` then exits 128, and with `pipefail` that
    # aborted the whole run with exit 128.
    #
    # But an unmeasured diff must NEVER render as a small one. Reporting 0
    # files / 0 insertions fed the substantive threshold and produced
    # "[skip] Trivial PR — gate not required", exit 0: P20, the merge gate for
    # the whole stack, silently skipping on a 12-file 1200-line change. That is
    # a worse failure than the crash it replaced — fail-loud became
    # fail-silent-pass. Unknown scope is therefore treated as SUBSTANTIVE.
    SCOPE_UNKNOWN=0
    if git rev-parse --verify --quiet "$DIFF_BASE" >/dev/null 2>&1; then
        CHANGED_FILES=$(git diff --name-only "$DIFF_BASE"...HEAD 2>/dev/null | wc -l | tr -d ' ')
        ADDITIONS=$(git diff --shortstat "$DIFF_BASE"...HEAD 2>/dev/null | grep -oE '[0-9]+ insertion' | head -1 | grep -oE '[0-9]+' || echo "0")
    else
        SCOPE_UNKNOWN=1
        CHANGED_FILES=0
        ADDITIONS=0
        echo "  [warn] diff base '$DIFF_BASE' does not resolve here — diff scope UNKNOWN."
        echo "         Treating the change as SUBSTANTIVE: the gate fires. Pass"
        echo "         --diff-base=<ref> to measure it instead of assuming the worst."
    fi
    [ -z "$ADDITIONS" ] && ADDITIONS=0

    if [ "$SCOPE_UNKNOWN" = "1" ]; then
        echo "  Diff scope:       UNKNOWN (unmeasurable against '$DIFF_BASE')"
    else
        echo "  Diff scope:       $CHANGED_FILES file(s), $ADDITIONS insertion(s)"
    fi
    echo ""

    # Substantive-threshold test (the agent's reflexive trigger)
    SUBSTANTIVE=0
    [ "$ADDITIONS" -gt 200 ] && SUBSTANTIVE=1
    [ "$CHANGED_FILES" -gt 3 ] && SUBSTANTIVE=1
    # "I could not measure it" is not "it is small".
    [ "$SCOPE_UNKNOWN" = "1" ] && SUBSTANTIVE=1
    # (public API + governance-class detection delegated to the agent's
    #  judgment; this script enforces the easy thresholds)

    if [ "$SUBSTANTIVE" = "0" ]; then
        echo "  [info] Diff below substantive threshold (<=200 LOC AND <=3 files)."
        echo "         Gate is OPTIONAL but not forbidden. Pass --force to fire anyway."
        echo ""
        if [ "${FORCE_GATE:-0}" != "1" ]; then
            echo "  [skip] Trivial PR — gate not required by P20 reflexive trigger."
            exit 0
        fi
    fi

    # ─── Reviewer guard: capture before any reviewer runs ────────────────
    echo "  ─── Reviewer guard ──────────────────────────────────────────"
    echo ""
    # Capture here rather than telling the agent to. An instruction printed to
    # stdout is not a baseline: the previous version advertised a guard that
    # nothing in the run actually armed, so every review passed unguarded.
    # Two DIFFERENT identities, because they answer different questions.
    #
    # The reviewer guard is per-INVOCATION: it fingerprints one review, and a
    # second capture under the same id is a collision worth refusing.
    #
    # The round budget is per-ARC: it must survive across invocations, or the
    # whole control is void. `pp$$` is the PID, so re-running pre-push -- which
    # the documented loop does EVERY ROUND -- handed back a fresh empty ledger
    # and reset the budget to "round 1 of 3 free". The round-8 ceiling then cost
    # one changed string to escape, and the CLI changed it for you.
    #
    # Derived from the BRANCH ALONE. The first version appended the merge-base,
    # which looked more precise and was strictly worse: a routine mid-arc
    # `git rebase origin/main` moves the merge-base, so the id changed and the
    # ledger reset. The round-8 ceiling had cost one changed string to escape;
    # keyed on the merge-base it cost one rebase.
    #
    # The branch IS the arc here, so reusing a branch name deliberately reuses
    # its ledger. Detached HEAD has no arc to speak of and falls back to the
    # commit, which is the one case where per-commit is the right grain.
    CR_RUN_ID="pp$$"
    CR_ARC_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo detached)
    if [ "$CR_ARC_BRANCH" = "HEAD" ] || [ -z "$CR_ARC_BRANCH" ]; then
        CR_ARC_BRANCH="detached-$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    fi
    CR_ARC_ID=$(printf 'arc-%s' "$CR_ARC_BRANCH" | tr -c 'A-Za-z0-9._-' '-')
    if bash "${BASH_SOURCE[0]}" reviewer-guard capture --run-id="$CR_RUN_ID"; then
        GUARD_ARMED=1
    else
        GUARD_ARMED=0
        echo "  [warn] could not arm the reviewer guard — the review will be"
        echo "         UNVERIFIABLE. That is not the same as clean."
    fi
    echo ""
    echo "  [TODO-AGENT] The reviewer must not be able to write. Two layers:"
    echo "    1. dispatch it read-only (each stratum below names how)"
    echo "    2. after the review returns, run:"
    echo "         cross-review reviewer-guard verify --run-id=$CR_RUN_ID   # exit 4 = INVALID"
    echo ""
    echo "  Exit 4 is REVIEW INVALID, distinct from a failing score: a verdict"
    echo "  produced by a reviewer that edited the tree is not a low score, it is"
    echo "  no verdict at all. Fix rounds belong to the WRITER, never the reviewer."
    echo ""
    echo "  What the guard does and does not see: it compares the tree before and"
    echo "  after, so it detects writes that PERSIST. A write that is made and then"
    echo "  reverted within the review, a write outside this worktree, and a"
    echo "  reviewer that replaces the baseline file itself all remain invisible."
    echo "  Layer 1 (the read-only tool set) is the control; this is corroboration."
    if [ "$GUARD_ARMED" = "1" ]; then
        echo "  Guard: ARMED. Run \`reviewer-guard verify\` before accepting any verdict."
    else
        echo "  Guard: NOT ARMED. Any verdict from this run is UNVERIFIABLE —"
        echo "  which is not the same as clean, and must be said in the PR."
    fi
    echo ""

    # ─── Round budget ────────────────────────────────────────────────────
    # Printed unconditionally, NOT inside a stratum. It lived in the Strata A
    # block, which only runs when `codex` is on PATH -- so the arc id printed on
    # a developer machine and vanished on a CI runner without Codex, and the test
    # that pinned it passed locally and failed in CI for a reason that had
    # nothing to do with what it was testing. The budget is the same whichever
    # evaluator scores the round.
    echo "  ─── Round budget ────────────────────────────────────────────"
    echo ""
    echo "  Arc id: $CR_ARC_ID   (stable across pre-push runs; the guard id is not)"
    echo ""
    echo "  After each scored round:"
    echo "    cross-review round record-round --run-id=$CR_ARC_ID \\"
    echo "      --score=N --defect=yes|no [--settles=CONFIRMED|REFUTED]"
    echo "    cross-review round budget --run-id=$CR_ARC_ID"
    echo ""
    echo "  budget exits: 0 authorized · 3 passed · 5 continuation review required"
    echo "                6 stop · 7 human. Rounds 1-3 are free; 4-7 are earned by"
    echo "                a CONTINUE verdict carrying a located prediction; >=8 is"
    echo "                a human decision. Stops are absorbing."
    echo ""
    echo "  Paste \`cross-review round show --run-id=$CR_ARC_ID\` into the PR with"
    echo "  the verdict -- the ledger lives in .git/ and is invisible to CI and to"
    echo "  every human reviewer until you do."
    echo ""

    # Strata A — true cross-vendor via Codex
    if [ "$SELECTED_STRATA" = "A" ] || [ "$SELECTED_STRATA" = "auto" ] && command -v codex >/dev/null 2>&1; then
        echo "  ─── Strata A: cross-vendor (Codex CLI) ──────────────────"
        echo ""
        echo "  [TODO-AGENT] The agent runs the following pattern:"
        echo "    1. Capture the diff: git diff $DIFF_BASE...HEAD > /tmp/cross-review-diff.patch"
        echo "    2. Invoke Codex with the adversarial brief from references/rubric.md"
        echo "       codex exec -m gpt-5.4 -c sandbox_mode=read-only \\"
        echo "         --prompt-file references/codex-prompt.md \\"
        echo "         --attach /tmp/cross-review-diff.patch"
        echo "       (read-only is not optional: an unsandboxed reviewer that can"
        echo "        patch the tree stops reporting and starts fixing — the same"
        echo "        defect as dispatching Strata B as 'general-purpose')"
        echo "    3. Parse Codex's response: score (0-10) + reasoning per rubric dim"
        echo "    4. If score >=7: pass (echo verdict, exit 0)"
        echo "    5. If score <7: fix the deductions, rescore, then drive the round"
        echo "       budget (printed above, and identical for every stratum)."
        echo ""
        echo "  (This script enforces the structure; the agent runs the Codex call)"
    fi

    # Strata B — fresh subagent
    if [ "$SELECTED_STRATA" = "B" ] || [ "$SELECTED_STRATA" = "auto" ] && ! command -v codex >/dev/null 2>&1; then
        echo "  ─── Strata B: fresh-context subagent under devil's-advocate brief ──"
        echo ""
        echo "  [TODO-AGENT] The agent runs the following pattern:"
        echo "    1. Capture diff + rubric"
        echo "    2. Dispatch a sub-Agent via Claude Code's Agent tool with a"
        echo "       READ-ONLY agent type — subagent_type='Explore', which carries"
        echo "       every tool EXCEPT Edit/Write/NotebookEdit. Not 'general-purpose':"
        echo "       that is Tools:* , so the reviewer could silently fix what it was"
        echo "       dispatched to report, and a fixed finding is indistinguishable"
        echo "       from one that was never found."
        echo "       Prompt: 'You are reviewing diff X against rubric Y as a devil's"
        echo "        advocate. Read references/rubric.md. Score each dimension"
        echo "        and report verdict. You cannot change code: report, do not fix.'"
        echo "    3. Parse the subagent's response"
        echo "    4. Same loop: ≥7 pass, <7 fix-rescore, then drive the round budget"
        echo "       (printed above, and identical for every stratum)."
        echo ""
        echo "  (This script enforces the structure; the agent dispatches the subagent)"
    fi

    # Strata C — composed existing skills (always)
    echo "  ─── Strata C: composed existing skills (always parallel) ────"
    echo ""
    echo "  [TODO-AGENT] Invoke each applicable skill via the Skill tool:"
    echo "    - superpowers:constructive-dissent  (the adversarial brief)"
    echo "    - devils-advocate                   (challenge assumptions)"
    echo "    - pr-review-toolkit:code-reviewer   (style + best-practices)"
    echo "    - pr-review-toolkit:silent-failure-hunter (catch swallowed errors)"
    echo "    - pr-review-toolkit:type-design-analyzer  (type-system review)"
    echo "    - pr-review-toolkit:comment-analyzer (comment accuracy)"
    echo "    - critique                           (UX/visual quality if frontend)"
    echo "    - premortem                          (imagine this failed)"
    echo "    - plan-design-review / plan-ceo-review / plan-eng-review"
    echo ""
    echo "  Aggregate findings from all skills. Each contributes to the rubric"
    echo "  dimensions. Final score is the consensus minimum (failures count)."
    echo ""

    # ─── Mutation-proof — REPORTED SIGNAL, not a gate ────────────────────
    # Rubric dimension 5 ("tests cover the change") is the one dimension a
    # machine can check directly: neuter the code, and see whether the tests
    # notice. It is REPORTED here, never blocking. Until the false-positive
    # rate on real repos is known, an UNPROVEN verdict must surface in the
    # review, not stop the push. Promotion to a gate is a later, evidenced
    # decision — see SKILL.md §"Mutation-proof".
    echo "  ─── Mutation-proof: do the tests discriminate? ──────────────"
    echo ""
    if [ -n "$MUT_TARGET" ] && [ -n "$MUT_TEST" ]; then
        MUT_SH="$REPO/scripts/mutation-proof.sh"
        if [ ! -f "$MUT_SH" ]; then
            echo "  [warn] $MUT_SH not found — signal skipped."
        else
            MUT_ARGS=(run --target "$MUT_TARGET" --test "$MUT_TEST" --strategy "$MUT_STRATEGY")
            if [ -n "$MUT_REF" ];   then MUT_ARGS+=(--ref "$MUT_REF"); fi
            if [ -n "$MUT_ROOT" ];  then MUT_ARGS+=(--root "$MUT_ROOT"); fi
            if [ -n "$MUT_PATHS" ]; then MUT_ARGS+=(--paths "$MUT_PATHS"); fi

            set +e
            bash "$MUT_SH" "${MUT_ARGS[@]}" 2>&1 | sed 's/^/  /'
            MUT_RC=${PIPESTATUS[0]}
            set -e

            echo ""
            case "$MUT_RC" in
                0) echo "  [signal] PROVEN — the tests go red when the target is neutered." ;;
                1) echo "  [signal] UNPROVEN — a test passed with AND without the target."
                   echo "           Rubric dim 5 is at risk. This is REPORTED, not blocking:"
                   echo "           fix the test, or say in the PR why the coverage is elsewhere." ;;
                # Exit 3 has three causes now — a red baseline, a mutation that
                # changed nothing, and a mutated run that emitted fewer checks.
                # Naming one of them here contradicted the runner's own verdict
                # two lines above.
                3) echo "  [signal] INCONCLUSIVE — nothing was proven; see the verdict above." ;;
                *) echo "  [signal] mutation-proof setup error (exit $MUT_RC) — see output above." ;;
            esac
            echo "           (non-blocking: pre-push exit code is unaffected)"
        fi
    elif [ -n "$MUT_TARGET" ] || [ -n "$MUT_TEST" ]; then
        # Half the pair is a typo, not a decision. Saying "no target given" when
        # the target is present and the TEST flag is misspelled sends the reader
        # to the wrong flag.
        if [ -z "$MUT_TEST" ]; then
            echo "  [incomplete] --mutation-target given but --mutation-test missing."
        else
            echo "  [incomplete] --mutation-test given but --mutation-target missing."
        fi
        echo "  Both are required. The signal did NOT run."
    else
        echo "  [not run] no mutation target given. To include the signal:"
        echo "    cross-review pre-push --mutation-target=PATH --mutation-test='CMD'"
        echo "  Without it, 'tests cover the change' rests on the reviewer's reading"
        echo "  of the diff alone — a test that passes with the code deleted looks"
        echo "  identical to one that does not."
    fi
    echo ""

    echo "  ─── Verdict ─────────────────────────────────────────────────"
    echo ""
    echo "  Format the verdict as a PR comment with:"
    echo "    - Strata used + score per dimension"
    echo "    - Specific deductions (file:line references)"
    echo "    - Fix recommendations or APPROVAL"
    echo "  Paste into PR description or comment. Push only when verdict ≥7."
    echo ""
    exit 0
fi

# ─── Plan-stage gate ─────────────────────────────────────────────────────
if [ "$COMMAND" = "plan" ]; then
    if [ -z "$SPEC" ]; then
        echo "cross-review plan: --spec PATH required" >&2
        exit 2
    fi
    if [ ! -f "$SPEC" ]; then
        echo "cross-review plan: spec file '$SPEC' not found" >&2
        exit 2
    fi
    echo "  Plan-stage gate: $SPEC"
    echo "  Strata C only by default (skill composition on the spec)"
    echo ""
    echo "  [TODO-AGENT] Invoke plan-design-review / plan-ceo-review /"
    echo "    plan-eng-review on the spec. Aggregate findings."
    echo "    Same scoring rubric; APPROVAL means the plan is ready for"
    echo "    implementation; REVISE means specific items to address before code."
    exit 0
fi

# ─── Audit-on-demand ─────────────────────────────────────────────────────
if [ "$COMMAND" = "audit" ]; then
    if [ -z "$TARGET" ]; then
        echo "cross-review audit: --target PATH required" >&2
        exit 2
    fi
    echo "  Audit: $TARGET"
    echo "  Concerns: $CONCERNS"
    echo "  Default Strata A (cross-vendor) — no time pressure"
    echo ""
    echo "  [TODO-AGENT] Same pattern as pre-push but scoped to TARGET"
    echo "    instead of diff. Useful for class-of-issue investigation"
    echo "    across existing code."
    exit 0
fi

echo "cross-review: command '$COMMAND' not implemented yet" >&2
exit 2
