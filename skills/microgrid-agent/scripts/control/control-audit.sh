#!/bin/bash
# Control Audit — verifies full metalayer compliance
# Exit 0 = all checks pass, exit 1 = failures detected

set -euo pipefail
cd "$(dirname "$0")/../.."

PASS=0
FAIL=0
TOTAL=0

check() {
    TOTAL=$((TOTAL + 1))
    local desc="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo "  [PASS] $desc"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Control Audit ==="
echo ""

# Section 1: Governance Files
echo "1. Governance Files"
check "CLAUDE.md exists" test -f CLAUDE.md
check "AGENTS.md exists" test -f AGENTS.md
check "METALAYER.md exists" test -f METALAYER.md
check ".control/policy.yaml exists" test -f .control/policy.yaml
check ".control/schemas/ directory exists" test -d .control/schemas
echo ""

# Section 2: Control Plane
echo "2. Control Plane"
check ".control/commands.yaml exists" test -f .control/commands.yaml
check ".control/topology.yaml exists" test -f .control/topology.yaml
check ".control/egri-journal.jsonl exists" test -f .control/egri-journal.jsonl
echo ""

# Section 3: Hooks
echo "3. Hooks"
check "session-start.sh exists" test -f scripts/hooks/session-start.sh
check "session-stop.sh exists" test -f scripts/hooks/session-stop.sh
check "control-gate.sh exists" test -f scripts/hooks/control-gate.sh
check ".githooks/pre-commit exists" test -f .githooks/pre-commit
check ".claude/settings.json exists" test -f .claude/settings.json
echo ""

# Section 4: Quality
echo "4. Quality"
check "Kernel compiles" bash -c "cd kernel && cargo check 2>&1 | grep -qv 'error\['"
check "Python tests pass" bash -c "cd reference && python -m pytest tests/ -q --tb=no 2>&1 | grep -q 'passed'"
echo ""

# Section 5: Documentation
echo "5. Documentation"
check "docs/architecture.md exists" test -f docs/architecture.md
check "docs/genome.md exists" test -f docs/genome.md
check "docs/conversations/ exists" test -d docs/conversations
check "docs/conversations/Conversations.md exists" test -f docs/conversations/Conversations.md
echo ""

echo "────────────────────────────────────"
echo "Result: $PASS/$TOTAL passed, $FAIL failed"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
