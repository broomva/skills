#!/bin/bash
# Control Gate Hook — PreToolUse for Bash commands
# Purpose: prevent destructive operations per .control/policy.yaml

TOOL_INPUT="${1:-}"

# G1: Block force push
if echo "$TOOL_INPUT" | grep -qE "git push.*--force|git push.*-f "; then
    echo "BLOCKED by G1: Force push to main is prohibited"
    echo "Use a PR workflow instead."
    exit 2
fi

# G4: Warn on potential secret exposure
if echo "$TOOL_INPUT" | grep -qiE "(API_KEY|SECRET_KEY|PASSWORD|PRIVATE_KEY).*=.*['\"]"; then
    echo "WARNING (G4): Command may contain secrets. Review before proceeding."
fi

# G5: Warn when editing safety-critical code
if echo "$TOOL_INPUT" | grep -qE "autonomic\.(rs|py)"; then
    echo "WARNING (G5): Editing safety-critical module. Safety gates G1-G4 must NEVER be removed or weakened."
fi

exit 0
