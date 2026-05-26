#!/bin/bash
# Session Start Hook — runs when a Claude Code session begins
# Purpose: ground the agent in the current state of the system

set -euo pipefail
cd "$(dirname "$0")/../.."

echo "┌──────────────────────────────────────────────────┐"
echo "│  microgrid-agent — Session Start                 │"
echo "└──────────────────────────────────────────────────┘"

# 1. Check test health
echo ""
echo "▸ Test health:"
RUST_RESULT=$(cd kernel && cargo test 2>&1 | tail -1)
PYTHON_RESULT=$(cd reference && python -m pytest tests/ -q --tb=no 2>&1 | tail -1)
echo "  Rust:   $RUST_RESULT"
echo "  Python: $PYTHON_RESULT"

# 2. Check kernel compiles
echo ""
echo "▸ Kernel build:"
if cd kernel && cargo check 2>&1 | grep -q "error"; then
    echo "  ✗ KERNEL HAS COMPILE ERRORS — fix before other work"
else
    echo "  ✓ Kernel compiles clean"
fi
cd ..

# 3. Check git state
echo ""
echo "▸ Git state:"
BRANCH=$(git branch --show-current)
DIRTY=$(git status --short | wc -l | tr -d ' ')
echo "  Branch: $BRANCH"
echo "  Uncommitted changes: $DIRTY"

# 4. Check EGRI journal for last evaluation
echo ""
echo "▸ EGRI state:"
if [ -f .control/egri-journal.jsonl ]; then
    LAST=$(tail -1 .control/egri-journal.jsonl)
    echo "  Last evaluation: $LAST"
else
    echo "  No EGRI evaluations yet"
fi

# 5. Check simulation baseline
echo ""
echo "▸ Quick simulation (Coquí only):"
python -m simulation.run --site coqui 2>&1 | grep -E "(rule-based|forecast)" | head -3

echo ""
echo "──────────────────────────────────────────────────────"
echo "Policy: .control/policy.yaml"
echo "Architecture: docs/architecture.md"
echo "──────────────────────────────────────────────────────"
