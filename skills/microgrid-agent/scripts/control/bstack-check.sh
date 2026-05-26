#!/bin/bash
# bstack-check — full harness validation for microgrid-agent
# Checks: governance files, hooks, EGRI, conversations, control audit

set -euo pipefail
cd "$(dirname "$0")/../.."

PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo "  [OK] $desc"
        PASS=$((PASS + 1))
    else
        echo "  [!!] $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "┌──────────────────────────────────────────────────┐"
echo "│  bstack-check — microgrid-agent                  │"
echo "└──────────────────────────────────────────────────┘"
echo ""

# Governance (5 files)
echo "Governance:"
check "CLAUDE.md" test -f CLAUDE.md
check "AGENTS.md" test -f AGENTS.md
check "METALAYER.md" test -f METALAYER.md
check ".control/policy.yaml" test -f .control/policy.yaml
check ".control/schemas/ directory" test -d .control/schemas
echo ""

# Hooks (3 Claude Code + 1 git)
echo "Hooks:"
check "SessionStart hook" test -f scripts/hooks/session-start.sh
check "Stop hook" test -f scripts/hooks/session-stop.sh
check "PreToolUse gate" test -f scripts/hooks/control-gate.sh
check "pre-commit hook" test -f .githooks/pre-commit
echo ""

# EGRI
echo "EGRI:"
check "EGRI journal exists" test -f .control/egri-journal.jsonl
ENTRIES=$(wc -l < .control/egri-journal.jsonl 2>/dev/null | tr -d ' ')
echo "  Entries: ${ENTRIES:-0}"
echo ""

# Conversations
echo "Conversations:"
check "conversations/ directory" test -d docs/conversations
check "Conversations.md index" test -f docs/conversations/Conversations.md
echo ""

# Control audit
echo "Control audit:"
if bash scripts/control/control-audit.sh > /dev/null 2>&1; then
    echo "  [OK] Full control audit passes"
    PASS=$((PASS + 1))
else
    echo "  [!!] Control audit has failures"
    FAIL=$((FAIL + 1))
fi
echo ""

echo "────────────────────────────────────"
TOTAL=$((PASS + FAIL))
echo "bstack-check: $PASS/$TOTAL passed"
if [ $FAIL -gt 0 ]; then
    echo "Action needed: $FAIL items require attention"
    exit 1
else
    echo "All clear."
fi
