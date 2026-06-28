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
# Max 3 fix rounds before escalating to user.
#
# Usage:
#   cross-review pre-push                 # default: gate before push
#   cross-review pre-push --strata auto   # explicit auto-detect
#   cross-review pre-push --strata A      # force Codex cross-vendor
#   cross-review pre-push --strata B      # force subagent
#   cross-review pre-push --strata C      # composed skills only
#   cross-review plan --spec PATH         # plan-stage gate
#   cross-review audit --target PATH      # audit-on-demand
#   cross-review --help

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
MAX_ROUNDS=3
RUBRIC="anti-slop"
OUTPUT_FORMAT="pr-comment"

# ─── Arg parsing ──────────────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    echo "cross-review: no command. Run with --help" >&2
    exit 2
fi

COMMAND="$1"
shift

case "$COMMAND" in
    --help|-h|help)
        sed -n '/^# Usage:/,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
        exit 0
        ;;
    pre-push|plan|audit|version)
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
        --max-rounds=*) MAX_ROUNDS="${arg#*=}" ;;
        --rubric=*) RUBRIC="${arg#*=}" ;;
        --output=*) OUTPUT_FORMAT="${arg#*=}" ;;
        *) echo "cross-review: unknown flag '$arg'" >&2; exit 2 ;;
    esac
done

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
    echo "  Max fix rounds:   $MAX_ROUNDS"
    echo ""

    # Compute changed files + size to enforce substantive-threshold rule
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        echo "[cross-review] not inside a git repo; exiting" >&2
        exit 2
    fi

    CHANGED_FILES=$(git diff --name-only "$DIFF_BASE"...HEAD 2>/dev/null | wc -l | tr -d ' ')
    ADDITIONS=$(git diff --shortstat "$DIFF_BASE"...HEAD 2>/dev/null | grep -oE '[0-9]+ insertion' | head -1 | grep -oE '[0-9]+' || echo "0")
    [ -z "$ADDITIONS" ] && ADDITIONS=0

    echo "  Diff scope:       $CHANGED_FILES file(s), $ADDITIONS insertion(s)"
    echo ""

    # Substantive-threshold test (the agent's reflexive trigger)
    SUBSTANTIVE=0
    [ "$ADDITIONS" -gt 200 ] && SUBSTANTIVE=1
    [ "$CHANGED_FILES" -gt 3 ] && SUBSTANTIVE=1
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

    # Strata A — true cross-vendor via Codex
    if [ "$SELECTED_STRATA" = "A" ] || [ "$SELECTED_STRATA" = "auto" ] && command -v codex >/dev/null 2>&1; then
        echo "  ─── Strata A: cross-vendor (Codex CLI) ──────────────────"
        echo ""
        echo "  [TODO-AGENT] The agent runs the following pattern:"
        echo "    1. Capture the diff: git diff $DIFF_BASE...HEAD > /tmp/cross-review-diff.patch"
        echo "    2. Invoke Codex with the adversarial brief from references/rubric.md"
        echo "       codex exec -m gpt-5.4 \\"
        echo "         --prompt-file references/codex-prompt.md \\"
        echo "         --attach /tmp/cross-review-diff.patch"
        echo "    3. Parse Codex's response: score (0-10) + reasoning per rubric dim"
        echo "    4. If score >=7: pass (echo verdict, exit 0)"
        echo "    5. If score <7: fix the specific deductions, rescore"
        echo "       Loop max $MAX_ROUNDS rounds, then escalate"
        echo ""
        echo "  (This script enforces the structure; the agent runs the Codex call)"
    fi

    # Strata B — fresh subagent
    if [ "$SELECTED_STRATA" = "B" ] || [ "$SELECTED_STRATA" = "auto" ] && ! command -v codex >/dev/null 2>&1; then
        echo "  ─── Strata B: fresh-context subagent under devil's-advocate brief ──"
        echo ""
        echo "  [TODO-AGENT] The agent runs the following pattern:"
        echo "    1. Capture diff + rubric"
        echo "    2. Dispatch a sub-Agent via Claude Code's Agent tool"
        echo "       with subagent_type='general-purpose' and the prompt:"
        echo "       'You are reviewing diff X against rubric Y as a devil's"
        echo "        advocate. Read references/rubric.md. Score each dimension"
        echo "        and report verdict.'"
        echo "    3. Parse the subagent's response"
        echo "    4. Same loop: ≥7 pass, <7 fix-rescore, max $MAX_ROUNDS rounds"
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
