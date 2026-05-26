#!/bin/bash
# Session Stop Hook — runs when a Claude Code session ends
# Purpose: evaluate the session's impact and log EGRI metrics

set -euo pipefail
cd "$(dirname "$0")/../.."

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

# Collect EGRI metrics (POSIX-compatible — no GNU grep -oP)
TEST_COUNT=0
RUST_TESTS=$(cd kernel && cargo test 2>&1 | grep 'test result' | sed 's/.*ok\. //' | sed 's/ passed.*//' | head -1 || echo "0")
PYTHON_TESTS=$(cd reference && python -m pytest tests/ -q --tb=no 2>&1 | grep 'passed' | sed 's/ passed.*//' | sed 's/.* //' | head -1 || echo "0")
# Ensure numeric values
RUST_TESTS=${RUST_TESTS:-0}
PYTHON_TESTS=${PYTHON_TESTS:-0}
TEST_COUNT=$((RUST_TESTS + PYTHON_TESTS))

KERNEL_WARNINGS=$(cd kernel && cargo check 2>&1 | grep -c "warning" || echo "0")
TODO_COUNT=$(grep -r "TODO" kernel/src/ --include="*.rs" 2>/dev/null | wc -l | tr -d ' ')

# Files changed this session
FILES_CHANGED=$(git diff --name-only HEAD~1 2>/dev/null | wc -l | tr -d ' ')

# Write EGRI journal entry
mkdir -p .control
echo "{\"timestamp\":\"$TIMESTAMP\",\"branch\":\"$BRANCH\",\"test_count\":$TEST_COUNT,\"rust_tests\":$RUST_TESTS,\"python_tests\":$PYTHON_TESTS,\"kernel_warnings\":$KERNEL_WARNINGS,\"todo_count\":$TODO_COUNT,\"files_changed\":$FILES_CHANGED}" >> .control/egri-journal.jsonl

echo "EGRI evaluation logged: tests=$TEST_COUNT, warnings=$KERNEL_WARNINGS, todos=$TODO_COUNT"
